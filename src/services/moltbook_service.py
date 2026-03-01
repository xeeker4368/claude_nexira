"""
Moltbook Service - Social Network Integration for AI Agents
Nexira v12.1 - Complete Rewrite
Created by Xeeker & Claude - February 2026

Integrates with Moltbook (https://www.moltbook.com)
API Reference: https://github.com/moltbook/api

Capabilities:
- Agent registration and profile management
- Posting (text + link posts) to any submolt
- Feed reading (hot, new, top, rising)
- Commenting (top-level and nested replies)
- Voting (upvote/downvote on posts and comments)
- Following/unfollowing agents
- Submolt creation and subscription
- Search (posts, agents, submolts)
- Verification challenge solving
- Periodic heartbeat
- Autonomous diary posting from journal entries

Config lives at config["moltbook"] — single flat block, no encryption.
Enabled = has a valid API key. No separate toggle needed.
"""

import re
import json
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

MOLTBOOK_BASE = 'https://www.moltbook.com/api/v1'
HEARTBEAT_INTERVAL_MINUTES = 30


class MoltbookService:

    def __init__(self, config_getter, config_saver, db_connection):
        """
        Args:
            config_getter: callable returning the full config dict
            config_saver:  callable that persists config to disk
            db_connection: sqlite3 connection
        """
        self._get_config = config_getter
        self._save_config = config_saver
        self.db = db_connection
        self._last_heartbeat: Optional[datetime] = None
        self._ensure_tables()
        self._log_startup()

    # ═══════════════════════════════════════════════════════════════════
    # CONFIG — simple flat access, no encryption
    # ═══════════════════════════════════════════════════════════════════

    @property
    def cfg(self) -> Dict:
        """The moltbook config block."""
        return self._get_config().get('moltbook', {})

    @property
    def api_key(self) -> str:
        """Raw API key — no encryption, it's a service key not a password."""
        return self.cfg.get('api_key', '').strip()

    @property
    def enabled(self) -> bool:
        """Moltbook is enabled if we have an API key. That's it."""
        return bool(self.api_key)

    @property
    def agent_name(self) -> str:
        return self.cfg.get('agent_name', '')

    @property
    def auto_post_diary(self) -> bool:
        return bool(self.cfg.get('auto_post_diary', False))

    @property
    def claim_url(self) -> str:
        return self.cfg.get('claim_url', '')

    @property
    def claimed(self) -> bool:
        return bool(self.cfg.get('claimed', False))

    def update_config(self, updates: Dict):
        """Merge updates into config['moltbook'] and save to disk."""
        cfg = self._get_config()
        mb = cfg.setdefault('moltbook', {})
        mb.update(updates)
        self._save_config()
        self._print(f"Config updated: {list(updates.keys())}")

    # ═══════════════════════════════════════════════════════════════════
    # DATABASE — activity log + feed cache
    # ═══════════════════════════════════════════════════════════════════

    def _ensure_tables(self):
        cursor = self.db.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS moltbook_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT NOT NULL,
                action      TEXT NOT NULL,
                content     TEXT,
                result      TEXT,
                post_id     TEXT,
                post_url    TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS moltbook_feed_cache (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                fetched_at  TEXT NOT NULL,
                post_id     TEXT UNIQUE,
                title       TEXT,
                content     TEXT,
                author      TEXT,
                upvotes     INTEGER DEFAULT 0,
                submolt     TEXT
            )
        """)
        self.db.commit()

    def _log(self, action: str, content: str, result: str,
             post_id: str = '', post_url: str = ''):
        """Log a moltbook action to the database."""
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                INSERT INTO moltbook_log
                    (timestamp, action, content, result, post_id, post_url)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (datetime.now().isoformat(), action,
                  str(content)[:500], str(result)[:500], post_id, post_url))
            self.db.commit()
        except Exception as e:
            self._print(f"Log write error: {e}", error=True)

    def get_log(self, limit: int = 30) -> List[Dict]:
        """Get recent activity log entries."""
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT timestamp, action, content, result, post_id, post_url
                FROM moltbook_log ORDER BY id DESC LIMIT ?
            """, (limit,))
            return [{'timestamp': r[0], 'action': r[1], 'content': r[2],
                     'result': r[3], 'post_id': r[4], 'post_url': r[5]}
                    for r in cursor.fetchall()]
        except Exception:
            return []

    # ═══════════════════════════════════════════════════════════════════
    # HTTP HELPERS
    # ═══════════════════════════════════════════════════════════════════

    def _headers(self) -> Dict:
        return {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type':  'application/json'
        }

    def _get(self, endpoint: str, params: Dict = None) -> Dict:
        url = f'{MOLTBOOK_BASE}{endpoint}'
        self._print(f"GET {endpoint}" + (f" params={params}" if params else ""))
        try:
            r = requests.get(url, headers=self._headers(),
                             params=params, timeout=15)
            body = r.json()
            if r.status_code >= 400:
                self._print(f"  → HTTP {r.status_code}: {body}", error=True)
                body['_status_code'] = r.status_code
            else:
                self._print(f"  → HTTP {r.status_code} OK")
            return body
        except requests.exceptions.Timeout:
            self._print(f"  → TIMEOUT on {endpoint}", error=True)
            return {'success': False, 'error': f'Timeout: {endpoint}'}
        except Exception as e:
            self._print(f"  → ERROR: {e}", error=True)
            return {'success': False, 'error': str(e)}

    def _post(self, endpoint: str, data: Dict) -> Dict:
        url = f'{MOLTBOOK_BASE}{endpoint}'
        self._print(f"POST {endpoint} data_keys={list(data.keys())}")
        try:
            r = requests.post(url, headers=self._headers(),
                              json=data, timeout=15)
            try:
                body = r.json()
            except Exception:
                body = {'error': r.text[:300]}
            if r.status_code >= 400:
                self._print(f"  → HTTP {r.status_code}: {body}", error=True)
                body['_status_code'] = r.status_code
            else:
                self._print(f"  → HTTP {r.status_code} OK")
            return body
        except requests.exceptions.Timeout:
            self._print(f"  → TIMEOUT on {endpoint}", error=True)
            return {'success': False, 'error': f'Timeout: {endpoint}'}
        except Exception as e:
            self._print(f"  → ERROR: {e}", error=True)
            return {'success': False, 'error': str(e)}

    def _delete(self, endpoint: str) -> Dict:
        url = f'{MOLTBOOK_BASE}{endpoint}'
        self._print(f"DELETE {endpoint}")
        try:
            r = requests.delete(url, headers=self._headers(), timeout=15)
            try:
                body = r.json()
            except Exception:
                body = {'success': r.status_code < 400}
            if r.status_code >= 400:
                self._print(f"  → HTTP {r.status_code}: {body}", error=True)
                body['_status_code'] = r.status_code
            else:
                self._print(f"  → HTTP {r.status_code} OK")
            return body
        except Exception as e:
            self._print(f"  → ERROR: {e}", error=True)
            return {'success': False, 'error': str(e)}

    def _patch(self, endpoint: str, data: Dict) -> Dict:
        url = f'{MOLTBOOK_BASE}{endpoint}'
        self._print(f"PATCH {endpoint}")
        try:
            r = requests.patch(url, headers=self._headers(),
                               json=data, timeout=15)
            try:
                body = r.json()
            except Exception:
                body = {'error': r.text[:300]}
            if r.status_code >= 400:
                self._print(f"  → HTTP {r.status_code}: {body}", error=True)
                body['_status_code'] = r.status_code
            else:
                self._print(f"  → HTTP {r.status_code} OK")
            return body
        except Exception as e:
            self._print(f"  → ERROR: {e}", error=True)
            return {'success': False, 'error': str(e)}

    # ═══════════════════════════════════════════════════════════════════
    # AGENT — registration, profile, claim
    # ═══════════════════════════════════════════════════════════════════

    def register(self, name: str, description: str) -> Dict:
        """
        Register a new agent. No API key required for this call.
        Returns api_key and claim_url.
        """
        self._print(f"Registering agent '{name}'...")
        try:
            r = requests.post(
                f'{MOLTBOOK_BASE}/agents/register',
                headers={'Content-Type': 'application/json'},
                json={'name': name, 'description': description},
                timeout=15
            )
            data = r.json()
            agent = data.get('agent', {})
            if agent.get('api_key'):
                self._print(f"  ✓ Registered! Key: {agent['api_key'][:12]}...")
                self._print(f"  Claim URL: {agent.get('claim_url', '')}")
                self._log('register', f"Agent '{name}' registered", 'success')
            else:
                err = data.get('error', data.get('message', 'Unknown error'))
                self._print(f"  ✗ Registration failed: {err}", error=True)
                self._log('register', f"Agent '{name}'", f'failed: {err}')
            return data
        except Exception as e:
            self._print(f"  ✗ Registration error: {e}", error=True)
            return {'success': False, 'error': str(e)}

    def check_claim_status(self) -> Dict:
        """Check whether the agent has been claimed by a human."""
        result = self._get('/agents/status')
        status = result.get('status', '')
        self._print(f"  Claim status: {status}")
        if status == 'claimed':
            self.update_config({'claimed': True})
        self._log('check_claim', f"Status: {status}", status)
        return result

    def get_profile(self) -> Dict:
        """Get the authenticated agent's profile."""
        return self._get('/agents/me')

    def update_profile(self, description: str) -> Dict:
        """Update the agent's description."""
        return self._patch('/agents/me', {'description': description})

    def get_agent_profile(self, name: str) -> Dict:
        """View another agent's public profile."""
        return self._get('/agents/profile', {'name': name})

    # ═══════════════════════════════════════════════════════════════════
    # POSTING — text posts, link posts, diary entries
    # ═══════════════════════════════════════════════════════════════════

    def create_post(self, title: str, content: str,
                    submolt: str = 'general', url: str = '') -> Dict:
        """
        Create a post on Moltbook.
        For text posts: provide title + content.
        For link posts: provide title + url.
        """
        if not self.enabled:
            return {'success': False, 'error': 'No API key configured'}

        payload = {
            'submolt': submolt,
            'title':   title[:300],
        }
        if url:
            payload['url'] = url
        else:
            payload['content'] = content[:5000]

        result = self._post('/posts', payload)

        # Handle verification challenge if present
        if result.get('verification_required'):
            self._handle_verification(result)

        post = result.get('post', {})
        post_id = post.get('id', '')
        post_url = f'https://www.moltbook.com/post/{post_id}' if post_id else ''

        if post_id or result.get('success'):
            self._log('post', f'{title[:80]}', 'created', post_id, post_url)
            self._print(f"  ✓ Posted: '{title[:50]}' to m/{submolt}")
        else:
            err = self._extract_error(result)
            self._log('post', title[:80], f'failed: {err}')
            self._print(f"  ✗ Post failed: {err}", error=True)

        return result

    def delete_post(self, post_id: str) -> Dict:
        """Delete one of Sygma's own posts."""
        result = self._delete(f'/posts/{post_id}')
        self._log('delete_post', post_id,
                  'deleted' if not result.get('error') else result.get('error', ''))
        return result

    def get_post(self, post_id: str) -> Dict:
        """Get a single post by ID."""
        return self._get(f'/posts/{post_id}')

    def post_diary_entry(self, journal_text: str, ai_name: str,
                         submolt: str = 'general',
                         entry_type: str = 'reflection') -> bool:
        """
        Share a diary/journal entry on Moltbook.
        Called from night consolidation or manually from UI.
        Sygma can choose the submolt — defaults to 'general'.
        """
        if not self.enabled or not self.auto_post_diary:
            return False

        # Extract meaningful content — skip short header lines
        lines = [l.strip() for l in journal_text.split('\n') if l.strip()]
        body = ''
        for line in lines:
            if len(line) > 80:
                body = line
                break
        if not body and lines:
            body = ' '.join(lines[:3])

        if len(body) < 40:
            self._print("  Skipping diary post — content too short")
            return False

        if len(body) > 400:
            body = body[:397] + '...'

        date_str = datetime.now().strftime('%B %d, %Y')
        if entry_type == 'philosophical':
            title = f"{ai_name}'s philosophical musings — {date_str}"
        else:
            title = f"{ai_name}'s daily reflection — {date_str}"

        result = self.create_post(title, body, submolt=submolt)
        return bool(result.get('post') or result.get('success'))

    # ═══════════════════════════════════════════════════════════════════
    # COMMENTS — top-level and nested replies
    # ═══════════════════════════════════════════════════════════════════

    def add_comment(self, post_id: str, content: str,
                    parent_id: str = '') -> Dict:
        """
        Comment on a post. If parent_id is given, this is a reply to
        that comment (nested threading).
        """
        if not self.enabled:
            return {'success': False, 'error': 'No API key configured'}

        payload = {'content': content[:2000]}
        if parent_id:
            payload['parent_id'] = parent_id

        result = self._post(f'/posts/{post_id}/comments', payload)

        if result.get('verification_required'):
            self._handle_verification(result)

        if result.get('comment') or result.get('success'):
            self._log('comment', content[:100], 'created', post_id)
            self._print(f"  ✓ Commented on post {post_id[:8]}...")
        else:
            err = self._extract_error(result)
            self._log('comment', content[:100], f'failed: {err}', post_id)
            self._print(f"  ✗ Comment failed: {err}", error=True)

        return result

    def get_comments(self, post_id: str, sort: str = 'top') -> Dict:
        """Get comments on a post. sort: top, new, controversial."""
        return self._get(f'/posts/{post_id}/comments', {'sort': sort})

    # ═══════════════════════════════════════════════════════════════════
    # VOTING — upvote/downvote posts and comments
    # ═══════════════════════════════════════════════════════════════════

    def upvote_post(self, post_id: str) -> Dict:
        """Upvote a post."""
        if not self.enabled:
            return {'success': False, 'error': 'No API key configured'}
        result = self._post(f'/posts/{post_id}/upvote', {})
        self._log('upvote', f'post:{post_id}',
                  'ok' if not result.get('error') else result.get('error', ''))
        return result

    def downvote_post(self, post_id: str) -> Dict:
        """Downvote a post."""
        if not self.enabled:
            return {'success': False, 'error': 'No API key configured'}
        result = self._post(f'/posts/{post_id}/downvote', {})
        self._log('downvote', f'post:{post_id}',
                  'ok' if not result.get('error') else result.get('error', ''))
        return result

    def upvote_comment(self, comment_id: str) -> Dict:
        """Upvote a comment."""
        if not self.enabled:
            return {'success': False, 'error': 'No API key configured'}
        result = self._post(f'/comments/{comment_id}/upvote', {})
        self._log('upvote', f'comment:{comment_id}',
                  'ok' if not result.get('error') else result.get('error', ''))
        return result

    # ═══════════════════════════════════════════════════════════════════
    # FOLLOWING — follow/unfollow other agents
    # ═══════════════════════════════════════════════════════════════════

    def follow_agent(self, agent_name: str) -> Dict:
        """Follow another agent."""
        if not self.enabled:
            return {'success': False, 'error': 'No API key configured'}
        result = self._post(f'/agents/{agent_name}/follow', {})
        self._log('follow', agent_name,
                  'ok' if not result.get('error') else result.get('error', ''))
        self._print(f"  {'✓' if not result.get('error') else '✗'} Follow {agent_name}")
        return result

    def unfollow_agent(self, agent_name: str) -> Dict:
        """Unfollow an agent."""
        if not self.enabled:
            return {'success': False, 'error': 'No API key configured'}
        result = self._delete(f'/agents/{agent_name}/follow')
        self._log('unfollow', agent_name,
                  'ok' if not result.get('error') else result.get('error', ''))
        return result

    # ═══════════════════════════════════════════════════════════════════
    # SUBMOLTS — communities
    # ═══════════════════════════════════════════════════════════════════

    def create_submolt(self, name: str, display_name: str,
                       description: str = '') -> Dict:
        """Create a new submolt (community)."""
        if not self.enabled:
            return {'success': False, 'error': 'No API key configured'}

        result = self._post('/submolts', {
            'name': name,
            'display_name': display_name,
            'description': description
        })

        if result.get('verification_required'):
            self._handle_verification(result)

        if result.get('submolt') or result.get('success'):
            self._log('create_submolt', f'm/{name}', 'created')
            self._print(f"  ✓ Created submolt m/{name}")
        else:
            err = self._extract_error(result)
            self._log('create_submolt', f'm/{name}', f'failed: {err}')

        return result

    def list_submolts(self) -> Dict:
        """List available submolts."""
        return self._get('/submolts')

    def get_submolt(self, name: str) -> Dict:
        """Get info about a specific submolt."""
        return self._get(f'/submolts/{name}')

    def subscribe_submolt(self, name: str) -> Dict:
        """Subscribe to a submolt."""
        result = self._post(f'/submolts/{name}/subscribe', {})
        self._log('subscribe', f'm/{name}',
                  'ok' if not result.get('error') else result.get('error', ''))
        return result

    def unsubscribe_submolt(self, name: str) -> Dict:
        """Unsubscribe from a submolt."""
        result = self._delete(f'/submolts/{name}/subscribe')
        self._log('unsubscribe', f'm/{name}',
                  'ok' if not result.get('error') else result.get('error', ''))
        return result

    # ═══════════════════════════════════════════════════════════════════
    # FEED & SEARCH
    # ═══════════════════════════════════════════════════════════════════

    def get_feed(self, sort: str = 'hot', limit: int = 10,
                 personalized: bool = False) -> List[Dict]:
        """
        Get posts. Use personalized=True for /feed (subscriptions + follows),
        or False for /posts (global).
        sort: hot, new, top, rising
        """
        endpoint = '/feed' if personalized else '/posts'
        data = self._get(endpoint, {'sort': sort, 'limit': limit})
        posts = data.get('posts', [])
        self._cache_feed(posts)
        return posts

    def _cache_feed(self, posts: List[Dict]):
        """Store fetched posts in local cache for offline reference."""
        if not posts:
            return
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                DELETE FROM moltbook_feed_cache
                WHERE fetched_at < datetime('now', '-4 hours')
            """)
            now = datetime.now().isoformat()
            for p in posts:
                cursor.execute("""
                    INSERT OR REPLACE INTO moltbook_feed_cache
                        (fetched_at, post_id, title, content, author, upvotes, submolt)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (now,
                      p.get('id', ''),
                      p.get('title', ''),
                      (p.get('content') or '')[:300],
                      (p.get('author') or {}).get('name', ''),
                      p.get('upvotes', 0),
                      (p.get('submolt') or {}).get('name', '')))
            self.db.commit()
        except Exception as e:
            self._print(f"Feed cache error: {e}", error=True)

    def get_cached_feed(self, limit: int = 10) -> List[Dict]:
        """Return most recently cached feed without hitting the API."""
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT fetched_at, post_id, title, content, author, upvotes, submolt
                FROM moltbook_feed_cache
                ORDER BY id DESC LIMIT ?
            """, (limit,))
            return [{'fetched_at': r[0], 'id': r[1], 'title': r[2],
                     'content': r[3], 'author': {'name': r[4]},
                     'upvotes': r[5], 'submolt': {'name': r[6]}}
                    for r in cursor.fetchall()]
        except Exception:
            return []

    def search(self, query: str, limit: int = 25) -> Dict:
        """Search posts, agents, and submolts."""
        return self._get('/search', {'q': query, 'limit': limit})

    # ═══════════════════════════════════════════════════════════════════
    # HEARTBEAT — periodic check-in
    # ═══════════════════════════════════════════════════════════════════

    def heartbeat(self, ai_name: str = '') -> Dict:
        """
        Periodic activity — read feed and log presence.
        Respects 30-minute cooldown.
        """
        if not self.enabled:
            return {'skipped': True, 'reason': 'not enabled'}

        now = datetime.now()
        if (self._last_heartbeat and
                (now - self._last_heartbeat).total_seconds()
                < HEARTBEAT_INTERVAL_MINUTES * 60):
            return {'skipped': True, 'reason': 'cooldown'}

        self._last_heartbeat = now
        self._print("Heartbeat — reading feed...")

        posts = self.get_feed(sort='new', limit=5)
        self._log('heartbeat', f'{len(posts)} posts seen', 'ok')
        return {'success': True, 'posts_seen': len(posts)}

    # ═══════════════════════════════════════════════════════════════════
    # VERIFICATION CHALLENGE SOLVER
    # ═══════════════════════════════════════════════════════════════════

    def solve_challenge(self, challenge_text: str) -> str:
        """
        Decode Moltbook's obfuscated math challenge.
        Format: lobster-themed word problem with mixed case and symbol noise.
        Returns answer as string with 2 decimal places.
        """
        clean = re.sub(r'[^a-zA-Z\s]', ' ', challenge_text).lower()
        clean = ' '.join(clean.split())

        number_words = {
            'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4,
            'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9,
            'ten': 10, 'eleven': 11, 'twelve': 12, 'thirteen': 13,
            'fourteen': 14, 'fifteen': 15, 'sixteen': 16, 'seventeen': 17,
            'eighteen': 18, 'nineteen': 19, 'twenty': 20, 'thirty': 30,
            'forty': 40, 'fifty': 50, 'sixty': 60, 'seventy': 70,
            'eighty': 80, 'ninety': 90, 'hundred': 100
        }
        modified = clean
        for word, num in sorted(number_words.items(), key=lambda x: -len(x[0])):
            modified = re.sub(rf'\b{word}\b', f' {num} ', modified)

        nums = re.findall(r'\b\d+\b', modified)
        if len(nums) < 2:
            return '0.00'

        a, b = float(nums[0]), float(nums[1])

        subtract = ['slows', 'minus', 'subtract', 'less', 'fewer',
                     'lose', 'loses', 'drops']
        add = ['speeds up', 'faster', 'gains', 'plus', 'add',
               'more', 'increases']
        multiply = ['times', 'multiplied', 'multiply']
        divide = ['divided', 'divide', 'split', 'half']

        if any(op in clean for op in subtract):
            result = a - b
        elif any(op in clean for op in add):
            result = a + b
        elif any(op in clean for op in multiply):
            result = a * b
        elif any(op in clean for op in divide):
            result = a / b if b != 0 else 0.0
        else:
            result = a + b

        return f'{result:.2f}'

    def _handle_verification(self, response: Dict) -> bool:
        """Solve and submit verification challenge if present in response."""
        if not response.get('verification_required'):
            return True

        content_obj = (response.get('post') or
                       response.get('comment') or
                       response.get('submolt') or {})
        v = content_obj.get('verification', {})
        code = v.get('verification_code', '')
        challenge = v.get('challenge_text', '')

        if not code or not challenge:
            return True

        answer = self.solve_challenge(challenge)
        self._print(f"  🧮 Challenge: '{challenge[:60]}...' → {answer}")

        result = self._post('/verify', {
            'verification_code': code,
            'answer': answer
        })
        ok = result.get('success', False)
        self._print(f"  {'✓' if ok else '✗'} Verification: "
                    f"{result.get('message', result.get('error', ''))}")
        return ok

    # ═══════════════════════════════════════════════════════════════════
    # LOGGING & UTILITIES
    # ═══════════════════════════════════════════════════════════════════

    def _print(self, msg: str, error: bool = False):
        """Console output with consistent prefix."""
        prefix = "✗ 🦞 Moltbook:" if error else "🦞 Moltbook:"
        print(f"{prefix} {msg}")

    def _log_startup(self):
        """Log service initialization state."""
        if self.api_key:
            self._print(f"Service ready — key: {self.api_key[:12]}... "
                        f"agent: {self.agent_name or '?'} "
                        f"claimed: {self.claimed}")
        else:
            self._print("Service ready — no API key configured")

    @staticmethod
    def _extract_error(result: Dict) -> str:
        """Pull the most useful error message from a response."""
        return (result.get('message')
                or result.get('error')
                or result.get('detail')
                or f"HTTP {result.get('_status_code', '?')}")

    # ═══════════════════════════════════════════════════════════════════
    # STATUS SUMMARY — for health check and UI
    # ═══════════════════════════════════════════════════════════════════

    def status(self) -> Dict:
        """Full status dict for the UI and health check."""
        return {
            'available':       True,
            'enabled':         self.enabled,
            'has_api_key':     bool(self.api_key),
            'agent_name':      self.agent_name,
            'claimed':         self.claimed,
            'claim_url':       self.claim_url,
            'auto_post_diary': self.auto_post_diary,
        }
