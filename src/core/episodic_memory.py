"""
Episodic Memory System — Nexira v9
====================================
Created with love by Xeeker & Claude — February 2026

Implements a two-tier short-term memory pipeline that sits between
raw chat_history and the permanent knowledge_base:

  chat_history (raw)
       ↓  every N messages (background thread)
  episode_summaries (compressed, topic-tagged, week-linked)
       ↓  weekly consolidation (Sunday 3AM)
  knowledge_base (confirmed, confidence-weighted, permanent)

DESIGN PRINCIPLES:
  - All summarization runs in a background thread — zero latency impact
  - build_context() gets richer context with no extra Ollama calls
    (episodes are pre-computed, retrieval is just SQLite queries)
  - Long-term memory accuracy improves because facts must appear in
    multiple episodes before being committed (confirmation_count)
  - Corrections are detected by comparing episode topics across the
    week and flagging contradictions
  - Nothing in chat_history is ever deleted — episodes and weekly
    synthesis are additive layers on top
"""

import json
import re
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple


# ── HELPERS ───────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now().isoformat()

def _week_number(dt: datetime = None) -> int:
    """ISO week number (1-53) for grouping episodes."""
    return (dt or datetime.now()).isocalendar()[1]

def _strip_think(text: str) -> str:
    """Remove <think>...</think> blocks produced by qwen3 and similar."""
    return re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()


# ── EPISODIC MEMORY ───────────────────────────────────────────────────────────

class EpisodicMemory:
    """
    Manages rolling episode summarization and weekly consolidation.

    Wired into:
      ai_engine.py  — log_conversation() triggers summarization check
                    — build_context() pulls episodes into the prompt
      night_consolidation.py — reads episodes instead of raw chat_history
      background_tasks.py    — calls run_weekly_consolidation() on Sundays
    """

    def __init__(self, db_connection, config: Dict, ollama_model: str):
        self.db           = db_connection
        self.config       = config
        self.ollama_model = ollama_model
        self._summarize_lock = threading.Lock()
        self._ensure_tables()

    # ── CONFIG HELPERS ────────────────────────────────────────────────────────

    def _ep_cfg(self, key, default):
        return self.config.get('memory', {}).get('episodic', {}).get(key, default)

    def _wk_cfg(self, key, default):
        return self.config.get('memory', {}).get('weekly_consolidation', {}).get(key, default)

    def _budget(self, key, default):
        return self.config.get('memory', {}).get('context_budget', {}).get(key, default)

    # ── SCHEMA GUARD ──────────────────────────────────────────────────────────

    def _ensure_tables(self):
        """Create tables if this is a fresh DB that hasn't run schema v9 yet."""
        cursor = self.db.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS episode_summaries (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at           TEXT NOT NULL,
                week_number          INTEGER,
                message_range_start  INTEGER,
                message_range_end    INTEGER,
                summary              TEXT NOT NULL,
                topics               TEXT,
                importance           REAL DEFAULT 0.5,
                mention_count        INTEGER DEFAULT 1,
                committed            INTEGER DEFAULT 0,
                archived             INTEGER DEFAULT 0
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS weekly_synthesis (
                id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                week_start            TEXT NOT NULL,
                week_end              TEXT NOT NULL,
                synthesis             TEXT NOT NULL,
                confirmed_topics      TEXT,
                tentative_topics      TEXT,
                corrections           TEXT,
                knowledge_items_added INTEGER DEFAULT 0,
                created_at            TEXT NOT NULL
            )
        """)
        # knowledge_base extra columns (ALTER IF NOT EXISTS pattern)
        for col_def in [
            "ALTER TABLE knowledge_base ADD COLUMN first_seen TEXT",
            "ALTER TABLE knowledge_base ADD COLUMN confirmation_count INTEGER DEFAULT 1",
            "ALTER TABLE knowledge_base ADD COLUMN source_weeks TEXT",
        ]:
            try:
                cursor.execute(col_def)
            except Exception:
                pass  # column already exists

        self.db.commit()

    # ── SUMMARIZATION TRIGGER ─────────────────────────────────────────────────

    def check_and_summarize(self, ai_name: Optional[str] = None):
        """
        Called after every log_conversation().  Checks if enough new messages
        have accumulated since the last episode and fires a background summary
        if so.  Never blocks the calling thread.
        """
        if not self._ep_cfg('enabled', True):
            return
        if not self._ep_cfg('background_summarization', True):
            return

        every_n = self._ep_cfg('summarize_every_n_messages', 20)

        cursor = self.db.cursor()

        # Find the highest chat_history id covered by the last episode
        cursor.execute("""
            SELECT COALESCE(MAX(message_range_end), 0)
            FROM episode_summaries
        """)
        last_covered = cursor.fetchone()[0]

        # Count messages since that point
        cursor.execute("""
            SELECT COUNT(*), MIN(id), MAX(id)
            FROM chat_history
            WHERE id > ?
        """, (last_covered,))
        row = cursor.fetchone()
        count, min_id, max_id = row[0], row[1], row[2]

        if count >= every_n:
            # Fire background thread — caller never waits
            t = threading.Thread(
                target=self._summarize_segment,
                args=(min_id, max_id, ai_name),
                daemon=True
            )
            t.start()

    def _summarize_segment(self, from_id: int, to_id: int,
                           ai_name: Optional[str]):
        """
        Background: fetch messages from_id..to_id, ask Ollama to summarize,
        store the result as an episode_summary row.
        """
        with self._summarize_lock:
            try:
                import ollama
                from core.ai_engine import get_ollama_client, get_ollama_options

                cursor = self.db.cursor()
                cursor.execute("""
                    SELECT role, content FROM chat_history
                    WHERE id BETWEEN ? AND ?
                    ORDER BY id ASC
                """, (from_id, to_id))
                rows = cursor.fetchall()
                if not rows:
                    return

                user_name = self.config.get('ai', {}).get('user_name', 'User') or 'User'
                name      = ai_name or 'AI'

                transcript = '\n'.join(
                    f"{user_name if r[0]=='user' else name}: {r[1][:300]}"
                    for r in rows
                )

                prompt = f"""Summarize this conversation segment between {user_name} and {name}.

Conversation:
{transcript}

Write a 3-5 sentence summary that captures:
- The main topics discussed
- Any decisions made or conclusions reached
- Key facts shared (names, numbers, technical details)
- The emotional tone if notable

Then on a new line write:
TOPICS: comma-separated list of 3-8 key topics from this segment

Be specific. Avoid vague phrases like "they discussed things".
Output the summary first, then the TOPICS line. Nothing else."""

                client   = get_ollama_client(self.config)
                response = client.generate(
                    model=self.ollama_model,
                    prompt=prompt,
                    options=get_ollama_options(self.config)
                )

                raw    = _strip_think(response['response'])
                lines  = raw.strip().split('\n')

                # Split summary from topics line
                topics_line = ''
                summary_lines = []
                for line in lines:
                    if line.upper().startswith('TOPICS:'):
                        topics_line = line.split(':', 1)[1].strip()
                    else:
                        summary_lines.append(line)

                summary = '\n'.join(l for l in summary_lines if l.strip())
                topics  = json.dumps(
                    [t.strip() for t in topics_line.split(',') if t.strip()]
                )

                # Estimate importance from content
                importance = 0.5
                high_words = ['important', 'decided', 'remember', 'agreed',
                              'critical', 'milestone', 'named', 'chose']
                if any(w in summary.lower() for w in high_words):
                    importance = 0.8

                cursor.execute("""
                    INSERT INTO episode_summaries
                    (created_at, week_number, message_range_start,
                     message_range_end, summary, topics, importance)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (_now_iso(), _week_number(), from_id, to_id,
                      summary, topics, importance))
                self.db.commit()
                print(f"[EPISODIC] Episode summary stored "
                      f"(msgs {from_id}–{to_id}, topics: {topics_line[:60]})")

            except Exception as e:
                print(f"[EPISODIC] Summarization error: {e}")

    # ── CONTEXT RETRIEVAL ─────────────────────────────────────────────────────

    def get_recent_episodes(self, limit: int = None) -> List[Dict]:
        """
        Return the most recent uncommitted episode summaries for context
        injection.  Called by build_context() in ai_engine.py.
        """
        if not self._ep_cfg('enabled', True):
            return []

        n = limit or self._ep_cfg('summaries_in_context', 4)
        retention = self._ep_cfg('retention_days', 7)
        cutoff    = (datetime.now() - timedelta(days=retention)).isoformat()

        cursor = self.db.cursor()
        cursor.execute("""
            SELECT id, created_at, summary, topics, importance, week_number
            FROM episode_summaries
            WHERE archived = 0
              AND created_at >= ?
            ORDER BY id DESC
            LIMIT ?
        """, (cutoff, n))
        rows = cursor.fetchall()
        rows.reverse()  # chronological order for prompt readability

        episodes = []
        for row in rows:
            topics = []
            try:
                topics = json.loads(row[3] or '[]')
            except Exception:
                pass
            episodes.append({
                'id':         row[0],
                'created_at': row[1],
                'summary':    row[2],
                'topics':     topics,
                'importance': row[4],
                'week':       row[5],
            })
        return episodes

    def search_episodes_by_topic(self, query: str,
                                 limit: int = 3) -> List[Dict]:
        """
        Keyword search across episode topics and summaries.
        Used to surface relevant older episodes even if they're not
        in the most recent N.
        """
        keywords = [w for w in query.lower().split() if len(w) > 3][:5]
        if not keywords:
            return []

        cursor = self.db.cursor()
        conditions = ' OR '.join(
            ['LOWER(summary) LIKE ? OR LOWER(topics) LIKE ?'] * len(keywords)
        )
        params = []
        for kw in keywords:
            params += [f'%{kw}%', f'%{kw}%']
        params.append(limit)

        cursor.execute(f"""
            SELECT id, created_at, summary, topics, importance
            FROM episode_summaries
            WHERE archived = 0 AND ({conditions})
            ORDER BY importance DESC, id DESC
            LIMIT ?
        """, params)

        rows = cursor.fetchall()
        return [
            {'id': r[0], 'created_at': r[1], 'summary': r[2],
             'topics': json.loads(r[3] or '[]'), 'importance': r[4]}
            for r in rows
        ]

    def format_episodes_for_prompt(self, episodes: List[Dict]) -> str:
        """
        Format episode list into system prompt text.
        Called by build_system_prompt() in ai_engine.py.
        """
        if not episodes:
            return ''

        lines = ['RECENT EPISODE SUMMARIES (what we discussed before right now):']
        for ep in episodes:
            age  = self._relative_time(ep['created_at'])
            tops = ', '.join(ep['topics'][:5]) if ep['topics'] else ''
            lines.append(f"\n[{age}]")
            lines.append(ep['summary'])
            if tops:
                lines.append(f"Topics: {tops}")

        lines.append(
            "\nUse these summaries to maintain continuity. "
            "They represent real conversations you had."
        )
        return '\n'.join(lines)

    # ── WEEKLY CONSOLIDATION ──────────────────────────────────────────────────

    def should_run_weekly(self) -> bool:
        """Check if weekly consolidation has already run this week."""
        if not self._wk_cfg('enabled', True):
            return False
        cursor = self.db.cursor()
        week   = _week_number()
        cursor.execute("""
            SELECT COUNT(*) FROM weekly_synthesis
            WHERE strftime('%W', week_start) = ?
        """, (str(week).zfill(2),))
        return cursor.fetchone()[0] == 0

    def run_weekly_consolidation(self,
                                 ai_name: Optional[str] = None) -> Dict:
        """
        Full weekly consolidation pipeline:
          1. Load all episode summaries from the past 7 days
          2. Extract topic frequency across all episodes
          3. Detect corrections / contradictions
          4. Commit high-confidence topics to knowledge_base
          5. Write weekly synthesis record
          6. Archive processed episodes
          Returns summary dict.
        """
        if not self.should_run_weekly():
            print("[WEEKLY] Already ran this week — skipping.")
            return {}

        print("\n🗓️  Weekly consolidation starting…")
        start  = datetime.now()
        week_n = _week_number()

        cursor = self.db.cursor()

        # ── 1. Load this week's episodes ──────────────────────────────────────
        week_ago = (datetime.now() - timedelta(days=7)).isoformat()
        cursor.execute("""
            SELECT id, created_at, summary, topics, importance
            FROM episode_summaries
            WHERE committed = 0 AND created_at >= ?
            ORDER BY id ASC
        """, (week_ago,))
        episodes = cursor.fetchall()

        if not episodes:
            print("[WEEKLY] No uncommitted episodes — nothing to consolidate.")
            return {}

        print(f"  Processing {len(episodes)} episodes from the past 7 days…")

        # ── 2. Topic frequency analysis ───────────────────────────────────────
        topic_counts: Dict[str, int] = {}
        for ep in episodes:
            try:
                topics = json.loads(ep[3] or '[]')
            except Exception:
                topics = []
            for t in topics:
                t_lower = t.lower().strip()
                if t_lower:
                    topic_counts[t_lower] = topic_counts.get(t_lower, 0) + 1

        min_confirm = self._wk_cfg('min_confirmations_for_longterm', 2)
        confirmed   = {t: c for t, c in topic_counts.items() if c >= min_confirm}
        tentative   = {t: c for t, c in topic_counts.items() if c < min_confirm}

        print(f"  Confirmed topics (≥{min_confirm}x): {len(confirmed)}")
        print(f"  Tentative topics (1x): {len(tentative)}")

        # ── 3. Use Ollama to synthesize the week ─────────────────────────────
        episode_text = '\n\n'.join(
            f"[{ep[1][:16]}] {ep[2]}" for ep in episodes
        )

        synthesis_text, corrections = self._generate_weekly_synthesis(
            episode_text, ai_name, confirmed, tentative
        )

        # ── 4. Commit to knowledge_base ───────────────────────────────────────
        items_added = self._commit_knowledge(
            episodes, confirmed, week_n, ai_name
        )

        # ── 5. Store weekly synthesis record ─────────────────────────────────
        week_start = (datetime.now() - timedelta(days=7)).isoformat()[:10]
        week_end   = datetime.now().isoformat()[:10]

        cursor.execute("""
            INSERT INTO weekly_synthesis
            (week_start, week_end, synthesis, confirmed_topics,
             tentative_topics, corrections, knowledge_items_added, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            week_start, week_end, synthesis_text,
            json.dumps(list(confirmed.keys())),
            json.dumps(list(tentative.keys())),
            json.dumps(corrections),
            items_added, _now_iso()
        ))

        # ── 6. Archive processed episodes ─────────────────────────────────────
        ep_ids = [ep[0] for ep in episodes]
        cursor.execute(f"""
            UPDATE episode_summaries
            SET committed = 1, archived = 1
            WHERE id IN ({','.join('?' * len(ep_ids))})
        """, ep_ids)

        self.db.commit()

        duration = (datetime.now() - start).total_seconds()
        print(f"  ✓ Weekly consolidation complete in {duration:.1f}s")
        print(f"  Knowledge items added: {items_added}")

        return {
            'episodes_processed':   len(episodes),
            'confirmed_topics':     len(confirmed),
            'tentative_topics':     len(tentative),
            'knowledge_items_added': items_added,
            'duration_seconds':     duration,
        }

    def _generate_weekly_synthesis(
        self,
        episode_text: str,
        ai_name: Optional[str],
        confirmed: Dict,
        tentative: Dict
    ) -> Tuple[str, List[str]]:
        """Ask Ollama to write a weekly synthesis and spot corrections."""
        try:
            import ollama
            from core.ai_engine import get_ollama_client, get_ollama_options

            name      = ai_name or 'AI'
            user_name = self.config.get('ai', {}).get('user_name', 'User') or 'User'
            conf_list = ', '.join(list(confirmed.keys())[:20])

            prompt = f"""You are {name}. Review this week's conversation summaries and write a weekly synthesis.

EPISODE SUMMARIES FROM THIS WEEK:
{episode_text[:6000]}

MOST DISCUSSED TOPICS: {conf_list}

Write a cohesive weekly synthesis (5-8 sentences) covering:
- What were the major themes and developments this week?
- What important decisions or conclusions were reached?
- What did you learn about {user_name} or the project?
- Are there any apparent corrections — things that were stated one way
  early in the week but revised or contradicted later?

After the synthesis, on a new line write:
CORRECTIONS: comma-separated list of any topics where earlier statements
were revised or contradicted this week. Write NONE if there are none.

Output only the synthesis and the CORRECTIONS line."""

            client   = get_ollama_client(self.config)
            response = client.generate(
                model=self.ollama_model,
                prompt=prompt,
                options=get_ollama_options(self.config)
            )

            raw   = _strip_think(response['response'])
            lines = raw.strip().split('\n')

            corrections  = []
            synth_lines  = []
            for line in lines:
                if line.upper().startswith('CORRECTIONS:'):
                    corr_raw = line.split(':', 1)[1].strip()
                    if corr_raw.upper() != 'NONE':
                        corrections = [c.strip() for c in corr_raw.split(',')
                                       if c.strip()]
                else:
                    synth_lines.append(line)

            synthesis = '\n'.join(l for l in synth_lines if l.strip())
            return synthesis, corrections

        except Exception as e:
            print(f"[WEEKLY] Synthesis generation error: {e}")
            return f"Weekly synthesis for week {_week_number()}", []

    def _commit_knowledge(
        self,
        episodes: List,
        confirmed_topics: Dict[str, int],
        week_n: int,
        ai_name: Optional[str]
    ) -> int:
        """
        For confirmed topics, extract specific knowledge entries from the
        relevant episodes and commit them to knowledge_base with
        confidence scores based on mention count.
        """
        try:
            import ollama
            from core.ai_engine import get_ollama_client, get_ollama_options

            cursor   = self.db.cursor()
            name     = ai_name or 'AI'
            now      = _now_iso()

            # Only process episodes that have confirmed topics
            relevant_episodes = []
            for ep in episodes:
                try:
                    ep_topics = json.loads(ep[3] or '[]')
                except Exception:
                    ep_topics = []
                ep_lower = [t.lower() for t in ep_topics]
                if any(ct in ep_lower for ct in confirmed_topics):
                    relevant_episodes.append(ep)

            if not relevant_episodes:
                return 0

            episode_text = '\n\n'.join(
                f"[{ep[1][:16]}] {ep[2]}" for ep in relevant_episodes[:10]
            )
            conf_list = ', '.join(
                f"{t} ({c}x)" for t, c in
                sorted(confirmed_topics.items(), key=lambda x: -x[1])[:15]
            )

            prompt = f"""You are {name}. Extract specific, factual knowledge from these episode summaries for long-term memory storage.

EPISODES:
{episode_text[:5000]}

CONFIRMED TOPICS (seen multiple times this week): {conf_list}

Extract 4-10 specific facts worth storing permanently. Focus on confirmed topics.

Each fact must be:
- Specific and named (not vague)
- At least 5 words as a topic
- Genuinely useful for future conversations

Format each as a JSON object on its own line:
{{"topic": "specific topic name", "content": "the actual fact to remember", "confidence": 0.8}}

Only output JSON lines. No other text."""

            client   = get_ollama_client(self.config)
            response = client.generate(
                model=self.ollama_model,
                prompt=prompt,
                options=get_ollama_options(self.config)
            )

            raw   = _strip_think(response['response'])
            added = 0

            for line in raw.strip().split('\n'):
                line = line.strip()
                if not line.startswith('{'):
                    continue
                try:
                    item = json.loads(line)
                    topic      = item.get('topic', '').strip()
                    content    = item.get('content', '').strip()
                    confidence = float(item.get('confidence', 0.6))

                    # Quality filter
                    words = topic.split()
                    if (len(words) < 3 or len(topic) < 12 or
                            len(content) < 25):
                        continue

                    # Boost confidence based on mention count
                    topic_lower = topic.lower()
                    for ct, count in confirmed_topics.items():
                        if ct in topic_lower:
                            if count >= 3:
                                confidence = max(confidence,
                                    self._wk_cfg('confidence_three_plus', 0.85))
                            elif count == 2:
                                confidence = max(confidence,
                                    self._wk_cfg('confidence_twice', 0.65))
                            break

                    # Check if this topic already exists
                    cursor.execute("""
                        SELECT id, confirmation_count, confidence
                        FROM knowledge_base WHERE topic = ?
                    """, (topic,))
                    existing = cursor.fetchone()

                    if existing:
                        # Update — increase confirmation count and confidence
                        new_count  = existing[1] + 1
                        new_conf   = max(existing[2], confidence)
                        weeks      = json.loads('[]')
                        try:
                            cursor.execute(
                                "SELECT source_weeks FROM knowledge_base WHERE id=?",
                                (existing[0],))
                            r = cursor.fetchone()
                            weeks = json.loads(r[0] or '[]') if r else []
                        except Exception:
                            pass
                        if week_n not in weeks:
                            weeks.append(week_n)
                        cursor.execute("""
                            UPDATE knowledge_base
                            SET content = ?, confidence = ?,
                                confirmation_count = ?,
                                source_weeks = ?,
                                last_accessed = ?
                            WHERE id = ?
                        """, (content, new_conf, new_count,
                              json.dumps(weeks), now, existing[0]))
                    else:
                        cursor.execute("""
                            INSERT INTO knowledge_base
                            (topic, content, source, confidence,
                             learned_date, last_accessed,
                             first_seen, confirmation_count, source_weeks)
                            VALUES (?, ?, 'weekly_consolidation', ?,
                                    ?, ?, ?, 1, ?)
                        """, (topic, content, confidence,
                              now, now, now, json.dumps([week_n])))
                        added += 1

                except (json.JSONDecodeError, KeyError, ValueError):
                    continue

            self.db.commit()
            return added

        except Exception as e:
            print(f"[WEEKLY] Knowledge commit error: {e}")
            return 0

    # ── CONTEXT BUDGET MANAGEMENT ─────────────────────────────────────────────

    def get_context_for_prompt(self, message: str) -> Dict:
        """
        Return a dict of episodic context items sized to fit within
        the configured token budget.  Called from build_context().

        Returns:
          {
            'recent_episodes':   List[Dict],   # last N summaries
            'relevant_episodes': List[Dict],   # topic-matched older ones
            'episode_prompt':    str,          # formatted for system prompt
          }
        """
        recent   = self.get_recent_episodes()
        relevant = []

        # Only add topic-matched episodes that aren't already in recent
        recent_ids = {ep['id'] for ep in recent}
        for ep in self.search_episodes_by_topic(message, limit=2):
            if ep['id'] not in recent_ids:
                relevant.append(ep)

        # Merge: relevant first (older context), then recent
        all_episodes = relevant + recent

        # Rough token budget enforcement — 1 token ≈ 4 chars
        budget    = self._budget('episode_summaries_tokens', 3000) * 4
        truncated = []
        used      = 0
        for ep in all_episodes:
            ep_len = len(ep['summary']) + 60  # 60 for header
            if used + ep_len > budget:
                break
            truncated.append(ep)
            used += ep_len

        return {
            'recent_episodes':   recent,
            'relevant_episodes': relevant,
            'episode_prompt':    self.format_episodes_for_prompt(truncated),
        }

    # ── MAINTENANCE ───────────────────────────────────────────────────────────

    def archive_old_episodes(self, retention_days: int = None):
        """
        Archive episodes older than retention_days.
        Called during nightly consolidation.
        """
        days   = retention_days or self._ep_cfg('retention_days', 7)
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        cursor = self.db.cursor()
        cursor.execute("""
            UPDATE episode_summaries
            SET archived = 1
            WHERE created_at < ? AND archived = 0
        """, (cutoff,))
        archived = cursor.rowcount
        self.db.commit()
        if archived:
            print(f"[EPISODIC] Archived {archived} old episodes")
        return archived

    def get_stats(self) -> Dict:
        """Return current episodic memory stats for status display."""
        cursor = self.db.cursor()
        cursor.execute("SELECT COUNT(*) FROM episode_summaries WHERE archived=0")
        active = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM episode_summaries")
        total = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM weekly_synthesis")
        weeks = cursor.fetchone()[0]
        cursor.execute(
            "SELECT MAX(created_at) FROM episode_summaries WHERE archived=0")
        last = cursor.fetchone()[0]
        return {
            'active_episodes': active,
            'total_episodes':  total,
            'weekly_syntheses': weeks,
            'last_episode':    (last or '')[:16],
        }

    # ── UTILITY ───────────────────────────────────────────────────────────────

    @staticmethod
    def _relative_time(iso_str: str) -> str:
        """Convert ISO timestamp to human-readable relative time."""
        try:
            dt    = datetime.fromisoformat(iso_str)
            delta = datetime.now() - dt
            secs  = delta.total_seconds()
            if secs < 3600:
                return f"{int(secs // 60)}m ago"
            elif secs < 86400:
                return f"{int(secs // 3600)}h ago"
            else:
                return f"{int(secs // 86400)}d ago"
        except Exception:
            return iso_str[:16]
