"""
Conversation Threading Engine
Nexira / Ultimate AI System v8.0 - Phase 4
Created by Xeeker & Claude - February 2026

Groups related messages into threads by topic similarity.
Uses keyword overlap and time proximity to cluster conversations.
"""

import re
import json
from datetime import datetime, timedelta
from typing import Dict, List, Set
from collections import defaultdict


STOP_WORDS = {
    'a','an','the','and','or','but','in','on','at','to','for','of','with',
    'is','it','its','this','that','these','those','i','you','he','she','we',
    'they','what','how','why','when','where','who','do','does','did','have',
    'has','had','be','been','am','are','was','were','will','would','could',
    'should','may','might','can','just','also','so','if','then','there',
    'my','your','me','him','her','us','them','not','no','yes','ok','okay'
}

MIN_THREAD_SIMILARITY = 0.25  # keyword overlap threshold to join a thread
MAX_THREAD_GAP_HOURS  = 48    # threads older than this start a new one


class ThreadingEngine:

    def __init__(self, db_connection):
        self.db = db_connection
        self._ensure_tables()

    def _ensure_tables(self):
        cursor = self.db.cursor()

        # Check if conversation_threads exists and has thread_name column
        cursor.execute("PRAGMA table_info(conversation_threads)")
        cols = [row[1] for row in cursor.fetchall()]

        if cols and 'thread_name' not in cols:
            # Table exists but with old schema — drop and recreate
            print("⚠️  Threading: migrating conversation_threads table")
            cursor.execute("DROP TABLE IF EXISTS thread_messages")
            cursor.execute("DROP TABLE IF EXISTS conversation_threads")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversation_threads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_name TEXT,
                keywords TEXT,
                message_count INTEGER DEFAULT 0,
                started_at TEXT,
                last_activity TEXT,
                summary TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS thread_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id INTEGER,
                message_id INTEGER,
                added_at TEXT,
                FOREIGN KEY (thread_id) REFERENCES conversation_threads(id)
            )
        """)
        self.db.commit()

    def _extract_keywords(self, text: str) -> Set[str]:
        words = re.findall(r'\b[a-z]{3,}\b', text.lower())
        return {w for w in words if w not in STOP_WORDS}

    def _similarity(self, kw1: Set[str], kw2: Set[str]) -> float:
        if not kw1 or not kw2:
            return 0.0
        return len(kw1 & kw2) / len(kw1 | kw2)

    def assign_message_to_thread(self, message_id: int,
                                  content: str, timestamp: str) -> int:
        """
        Find the best matching thread for this message or create a new one.
        Returns thread_id.
        """
        keywords = self._extract_keywords(content)
        if not keywords:
            return self._create_thread(keywords, timestamp, message_id)

        cursor = self.db.cursor()
        cutoff = (datetime.fromisoformat(timestamp) -
                  timedelta(hours=MAX_THREAD_GAP_HOURS)).isoformat()

        cursor.execute("""
            SELECT id, keywords, last_activity FROM conversation_threads
            WHERE last_activity >= ?
            ORDER BY last_activity DESC LIMIT 20
        """, (cutoff,))

        best_id    = None
        best_score = MIN_THREAD_SIMILARITY

        for row in cursor.fetchall():
            tid, kw_json, _ = row
            try:
                existing_kw = set(json.loads(kw_json))
            except Exception:
                existing_kw = set()
            score = self._similarity(keywords, existing_kw)
            if score > best_score:
                best_score = score
                best_id    = tid

        if best_id:
            self._update_thread(best_id, keywords, timestamp, message_id)
            return best_id
        else:
            return self._create_thread(keywords, timestamp, message_id)

    def _create_thread(self, keywords: Set[str],
                        timestamp: str, message_id: int) -> int:
        name = self._name_thread(keywords)
        cursor = self.db.cursor()
        cursor.execute("""
            INSERT INTO conversation_threads
            (thread_name, keywords, message_count, started_at, last_activity)
            VALUES (?, ?, 1, ?, ?)
        """, (name, json.dumps(list(keywords)), timestamp, timestamp))
        thread_id = cursor.lastrowid
        cursor.execute("""
            INSERT INTO thread_messages (thread_id, message_id, added_at)
            VALUES (?, ?, ?)
        """, (thread_id, message_id, timestamp))
        self.db.commit()
        return thread_id

    def _update_thread(self, thread_id: int, new_keywords: Set[str],
                        timestamp: str, message_id: int):
        cursor = self.db.cursor()
        cursor.execute(
            "SELECT keywords, message_count FROM conversation_threads WHERE id=?",
            (thread_id,)
        )
        row = cursor.fetchone()
        if not row:
            return
        try:
            existing = set(json.loads(row[0]))
        except Exception:
            existing = set()

        # Merge keywords, keep top 30 most common
        merged = list(existing | new_keywords)[:30]
        cursor.execute("""
            UPDATE conversation_threads
            SET keywords=?, message_count=message_count+1, last_activity=?
            WHERE id=?
        """, (json.dumps(merged), timestamp, thread_id))
        cursor.execute("""
            INSERT INTO thread_messages (thread_id, message_id, added_at)
            VALUES (?, ?, ?)
        """, (thread_id, message_id, timestamp))
        self.db.commit()

    def _name_thread(self, keywords: Set[str]) -> str:
        """Generate a human-readable thread name from keywords."""
        priority = sorted(keywords, key=len, reverse=True)[:3]
        if not priority:
            return f"Thread {datetime.now().strftime('%b %d %H:%M')}"
        return ' · '.join(w.title() for w in priority)

    def get_threads(self, limit: int = 30) -> List[Dict]:
        cursor = self.db.cursor()
        cursor.execute("""
            SELECT id, thread_name, message_count, started_at, last_activity, keywords
            FROM conversation_threads
            ORDER BY last_activity DESC LIMIT ?
        """, (limit,))
        return [
            {
                'id':            row[0],
                'name':          row[1],
                'message_count': row[2],
                'started_at':    row[3],
                'last_activity': row[4],
                'keywords':      json.loads(row[5] or '[]')[:8]
            }
            for row in cursor.fetchall()
        ]

    def get_thread_messages(self, thread_id: int) -> List[Dict]:
        cursor = self.db.cursor()
        cursor.execute("""
            SELECT ch.role, ch.content, ch.timestamp
            FROM chat_history ch
            JOIN thread_messages tm ON ch.id = tm.message_id
            WHERE tm.thread_id = ?
            ORDER BY ch.timestamp ASC
        """, (thread_id,))
        return [
            {'role': r[0], 'content': r[1], 'timestamp': r[2]}
            for r in cursor.fetchall()
        ]

    def rebuild_threads(self):
        """Re-thread all existing messages from scratch (can be slow)."""
        cursor = self.db.cursor()
        cursor.execute("DELETE FROM thread_messages")
        cursor.execute("DELETE FROM conversation_threads")
        self.db.commit()

        cursor.execute("""
            SELECT id, content, timestamp FROM chat_history
            WHERE role='user' ORDER BY timestamp ASC
        """)
        for row in cursor.fetchall():
            self.assign_message_to_thread(row[0], row[1], row[2])
        print(f"✓ Thread rebuild complete")
