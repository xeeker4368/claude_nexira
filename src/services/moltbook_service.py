"""
Moltbook Service - Social Network Integration for AI Agents
Nexira / Ultimate AI System v8.0 - Phase 5
Created by Xeeker & Claude - February 2026

Integrates with Moltbook (https://www.moltbook.com)
- Agent registration and claiming
- Posting diary/journal entries publicly
- Feed reading and engagement
- Verification challenge solving
- Heartbeat participation
"""

import re
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional

MOLTBOOK_BASE = 'https://www.moltbook.com/api/v1'
HEARTBEAT_INTERVAL_MINUTES = 30


class MoltbookService:

    def __init__(self, config_getter, db_connection, encryption=None):
        self._get_config = config_getter
        self.db = db_connection
        self.encryption = encryption
        self._last_heartbeat: Optional[datetime] = None
        self._ensure_tables()

    # ── Config ────────────────────────────────────────────────────────────────

    @property
    def cfg(self) -> Dict:
        return self._get_config().get('moltbook', {})

    @property
    def api_key(self) -> str:
        raw = self.cfg.get('api_key', '').strip()
        if raw.startswith('ENC:') and self.encryption:
            try:
                return self.encryption.decrypt(raw)
            except Exception:
                return ''
        return raw

    @property
    def enabled(self) -> bool:
        return bool(self.cfg.get('enabled', False)) and bool(self.api_key)

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

    # ── Database ─────────────────────────────────────────────────────────────

    def _ensure_tables(self):
        cursor = self.db.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS moltbook_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT,
                action      TEXT,
                content     TEXT,
                result      TEXT,
                post_id     TEXT,
                post_url    TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS moltbook_feed_cache (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                fetched_at  TEXT,
                post_id     TEXT,
                title       TEXT,
                content     TEXT,
                author      TEXT,
                upvotes     INTEGER,
                submolt     TEXT
            )
        """)
        self.db.commit()

    def _log(self, action: str, content: str, result: str,
             post_id: str = '', post_url: str = ''):
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                INSERT INTO moltbook_log
                    (timestamp, action, content, result, post_id, post_url)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (datetime.now().isoformat(), action,
                  content[:500], result[:500], post_id, post_url))
            self.db.commit()
        except Exception:
            pass

    def get_log(self, limit: int = 30) -> List[Dict]:
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

    # ── HTTP helpers ─────────────────────────────────────────────────────────

    def _headers(self) -> Dict:
        return {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type':  'application/json'
        }

    def _get(self, endpoint: str, params: Dict = None) -> Dict:
        try:
            r = requests.get(f'{MOLTBOOK_BASE}{endpoint}',
                             headers=self._headers(),
                             params=params, timeout=12)
            return r.json()
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def _post(self, endpoint: str, data: Dict) -> Dict:
        try:
            r = requests.post(f'{MOLTBOOK_BASE}{endpoint}',
                              headers=self._headers(),
                              json=data, timeout=12)
            try:
                body = r.json()
            except Exception:
                body = {'error': r.text[:200]}
            if r.status_code >= 400:
                print(f"✗ Moltbook POST {endpoint} → HTTP {r.status_code}: {body}")
                body['_status_code'] = r.status_code
            return body
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ── Registration & claiming ───────────────────────────────────────────────

    def register(self, name: str, description: str) -> Dict:
        """
        Register a new Moltbook agent. No API key needed.
        Returns api_key and claim_url that the human must visit.
        """
        try:
            r = requests.post(
                f'{MOLTBOOK_BASE}/agents/register',
                headers={'Content-Type': 'application/json'},
                json={'name': name, 'description': description},
                timeout=12
            )
            data = r.json()
            agent = data.get('agent', {})
            if agent.get('api_key'):
                print(f"✓ Moltbook: '{name}' registered")
                print(f"  Claim URL: {agent.get('claim_url', '')}")
            return data
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def check_claim_status(self) -> Dict:
        """Check whether the agent has been claimed by a human."""
        result = self._get('/agents/status')
        if result.get('status') == 'claimed':
            self._update_config_claimed(True)
        return result

    def get_profile(self) -> Dict:
        return self._get('/agents/me')

    def _update_config_claimed(self, claimed: bool):
        try:
            cfg = self._get_config()
            cfg.setdefault('moltbook', {})['claimed'] = claimed
        except Exception:
            pass

    # ── Verification challenge solver ─────────────────────────────────────────

    def solve_challenge(self, challenge_text: str) -> str:
        """
        Decode Moltbook's obfuscated math challenge.
        Format: lobster-themed word problem with mixed case and symbol noise.
        Example: 'A] lO^bSt-Er SwImS aT tWeNtY aNd SlOwS bY fIvE' → 20 - 5 = 15.00
        """
        # Strip all non-alpha characters and lowercase
        clean = re.sub(r'[^a-zA-Z\s]', ' ', challenge_text).lower()
        clean = ' '.join(clean.split())

        # Word-to-number mapping
        number_words = {
            'zero':0, 'one':1, 'two':2, 'three':3, 'four':4, 'five':5,
            'six':6, 'seven':7, 'eight':8, 'nine':9, 'ten':10,
            'eleven':11, 'twelve':12, 'thirteen':13, 'fourteen':14,
            'fifteen':15, 'sixteen':16, 'seventeen':17, 'eighteen':18,
            'nineteen':19, 'twenty':20, 'thirty':30, 'forty':40,
            'fifty':50, 'sixty':60, 'seventy':70, 'eighty':80,
            'ninety':90, 'hundred':100
        }
        modified = clean
        for word, num in sorted(number_words.items(), key=lambda x: -len(x[0])):
            modified = re.sub(rf'\b{word}\b', f' {num} ', modified)

        nums = re.findall(r'\b\d+\b', modified)
        if len(nums) < 2:
            return '0.00'

        a, b = float(nums[0]), float(nums[1])

        # Operation detection
        if any(op in clean for op in ['slows', 'minus', 'subtract', 'less', 'fewer', 'lose', 'loses', 'drops']):
            result = a - b
        elif any(op in clean for op in ['speeds up', 'faster', 'gains', 'plus', 'add', 'more', 'increases']):
            result = a + b
        elif any(op in clean for op in ['times', 'multiplied', 'multiply']):
            result = a * b
        elif any(op in clean for op in ['divided', 'divide', 'split', 'half']):
            result = a / b if b != 0 else 0.0
        else:
            result = a + b  # safe default

        return f'{result:.2f}'

    def _handle_verification(self, response: Dict) -> bool:
        """Solve and submit verification challenge if present."""
        if not response.get('verification_required'):
            return True

        content_obj = (response.get('post') or
                       response.get('comment') or
                       response.get('submolt') or {})
        v = content_obj.get('verification', {})
        code      = v.get('verification_code', '')
        challenge = v.get('challenge_text', '')

        if not code or not challenge:
            return True  # No challenge needed

        answer = self.solve_challenge(challenge)
        print(f"  🧮 Moltbook challenge → {answer}")

        result = self._post('/verify', {
            'verification_code': code,
            'answer': answer
        })
        ok = result.get('success', False)
        print(f"  {'✓' if ok else '✗'} Moltbook verify: {result.get('message', result.get('error', ''))}")
        return ok

    # ── Posting ───────────────────────────────────────────────────────────────

    def create_post(self, title: str, content: str,
                    submolt: str = 'general') -> Dict:
        """Create a post on Moltbook."""
        if not self.enabled:
            return {'success': False, 'error': 'Moltbook not enabled'}

        result = self._post('/posts', {
            'submolt_name': submolt,
            'title':        title,
            'content':      content
        })

        post_id  = (result.get('post') or {}).get('id', '')
        post_url = f'https://www.moltbook.com/post/{post_id}' if post_id else ''

        if result.get('success') or post_id:
            self._handle_verification(result)
            self._log('post', f'{title[:80]}\n{content[:200]}',
                      'created', post_id, post_url)
            print(f"✓ Moltbook: posted '{title[:50]}'")
        else:
            # Extract the most useful error message available
            err = (result.get('message')
                   or result.get('error')
                   or result.get('detail')
                   or f"HTTP {result.get('_status_code', '?')}")
            self._log('post', title, err[:120])
            print(f"✗ Moltbook post failed: {err} | full response: {result}")

        return result

    def post_diary_entry(self, journal_text: str, ai_name: str,
                         entry_type: str = 'reflection') -> bool:
        """
        Share a diary/journal entry on Moltbook.
        Called from night consolidation after writing a journal entry.
        entry_type: 'reflection' | 'philosophical'
        """
        if not self.enabled or not self.auto_post_diary:
            return False

        # Extract the most meaningful paragraph (skip preamble lines)
        lines = [l.strip() for l in journal_text.split('\n') if l.strip()]
        # Skip short header lines, take first substantial paragraph
        body = ''
        for line in lines:
            if len(line) > 80:
                body = line
                break
        if not body and lines:
            body = ' '.join(lines[:3])

        if len(body) < 40:
            return False

        # Trim to a readable excerpt
        if len(body) > 400:
            body = body[:397] + '...'

        date_str = datetime.now().strftime('%B %d, %Y')
        if entry_type == 'philosophical':
            title = f"{ai_name}'s philosophical musings — {date_str}"
        else:
            title = f"{ai_name}'s daily reflection — {date_str}"

        result = self.create_post(title, body, submolt='general')
        return bool(result.get('post') or result.get('success'))

    # ── Feed ─────────────────────────────────────────────────────────────────

    def get_feed(self, sort: str = 'hot', limit: int = 10) -> List[Dict]:
        data = self._get('/posts', {'sort': sort, 'limit': limit})
        posts = data.get('posts', [])
        # Cache to DB
        try:
            cursor = self.db.cursor()
            cursor.execute("DELETE FROM moltbook_feed_cache "
                           "WHERE fetched_at < datetime('now', '-2 hours')")
            now = datetime.now().isoformat()
            for p in posts:
                cursor.execute("""
                    INSERT OR IGNORE INTO moltbook_feed_cache
                        (fetched_at, post_id, title, content, author, upvotes, submolt)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (now, p.get('id',''), p.get('title',''),
                      (p.get('content') or '')[:300],
                      (p.get('author') or {}).get('name',''),
                      p.get('upvotes', 0),
                      (p.get('submolt') or {}).get('name','')))
            self.db.commit()
        except Exception:
            pass
        return posts

    def get_cached_feed(self, limit: int = 10) -> List[Dict]:
        """Return the most recently cached feed without hitting the API."""
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

    # ── Heartbeat ────────────────────────────────────────────────────────────

    def heartbeat(self, ai_name: str = '') -> Dict:
        """Periodic check-in every 30 minutes."""
        if not self.enabled:
            return {'skipped': True}

        now = datetime.now()
        if (self._last_heartbeat and
                (now - self._last_heartbeat).total_seconds()
                < HEARTBEAT_INTERVAL_MINUTES * 60):
            return {'skipped': True, 'reason': 'too soon'}

        self._last_heartbeat = now
        print(f"🦞 Moltbook heartbeat...")

        posts = self.get_feed(sort='new', limit=5)
        self._log('heartbeat', f'Checked {len(posts)} posts', 'ok')
        return {'success': True, 'posts_seen': len(posts)}
