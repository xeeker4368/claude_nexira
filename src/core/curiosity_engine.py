"""
Curiosity Engine - Autonomous Topic Discovery
Nexira / Ultimate AI System v8.0 - Phase 2
Created by Xeeker & Claude - February 2026

The AI notices things it doesn't know and wants to learn more about.
Topics get added to the curiosity queue and researched during idle time.
"""

import json
import os
from datetime import datetime
from typing import List, Dict, Optional
import sqlite3


class CuriosityEngine:
    """
    Drives autonomous learning by detecting knowledge gaps
    and managing the research queue.
    """

    def __init__(self, db_connection, config: Dict):
        self.db = db_connection
        self.config = config

        # Keywords that signal genuine curiosity / uncertainty
        self.curiosity_triggers = [
            "i wonder", "what is", "how does", "why does", "i don't know",
            "not sure", "interesting", "never heard", "tell me more",
            "what about", "curious", "fascinating", "strange", "weird",
            "how come", "explain", "what if"
        ]

        # Topics we already know well enough to skip
        self._skip_topics = set()
        self._load_known_topics()

    def _load_known_topics(self):
        """Cache topics already in knowledge base to avoid re-queuing"""
        try:
            cursor = self.db.cursor()
            cursor.execute("SELECT LOWER(topic) FROM knowledge_base")
            self._skip_topics = {row[0] for row in cursor.fetchall()}
        except Exception:
            self._skip_topics = set()

    def extract_curious_topics(self, message: str, response: str) -> List[str]:
        """
        Analyse a conversation exchange and pull out topics
        the AI expressed uncertainty or curiosity about.
        """
        topics = []
        combined = (message + " " + response).lower()

        # Look for curiosity trigger phrases followed by a topic
        import re
        patterns = [
            r"i wonder (?:about |if |why |how )?([a-z][a-z\s]{3,40})",
            r"what (?:is|are) ([a-z][a-z\s]{3,30})\?",
            r"how does ([a-z][a-z\s]{3,30}) work",
            r"(?:not sure|uncertain) about ([a-z][a-z\s]{3,30})",
            r"i(?:'m| am) curious about ([a-z][a-z\s]{3,30})",
            r"fascinating (?:topic|idea|concept)[:\s]+([a-z][a-z\s]{3,30})",
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, combined):
                topic = match.group(1).strip().rstrip('.,!?')
                if len(topic) > 3 and topic.lower() not in self._skip_topics:
                    topics.append(topic)

        # Also check if any curiosity trigger appears near a noun phrase
        words = combined.split()
        for i, word in enumerate(words):
            for trigger in self.curiosity_triggers:
                if trigger in combined:
                    # Grab the 2-3 words after the trigger as a potential topic
                    trigger_words = trigger.split()
                    try:
                        idx = words.index(trigger_words[0], max(0, i - 2))
                        candidate = ' '.join(words[idx + len(trigger_words): idx + len(trigger_words) + 3])
                        candidate = candidate.strip().rstrip('.,!?')
                        if len(candidate) > 3 and candidate.lower() not in self._skip_topics:
                            if candidate not in topics:
                                topics.append(candidate)
                    except (ValueError, IndexError):
                        pass
                    break

        return list(set(topics))[:5]  # Max 5 topics per exchange

    def add_to_queue(self, topic: str, reason: str = "", priority: float = 0.5):
        """Add a topic to the curiosity research queue"""
        try:
            cursor = self.db.cursor()

            # Don't add duplicates
            cursor.execute(
                "SELECT id FROM curiosity_queue WHERE LOWER(topic)=? AND status='pending'",
                (topic.lower(),)
            )
            if cursor.fetchone():
                return  # Already queued

            cursor.execute("""
                INSERT INTO curiosity_queue
                (topic, priority, added_date, reason, status)
                VALUES (?, ?, ?, ?, 'pending')
            """, (topic, priority, datetime.now().isoformat(), reason))
            self.db.commit()

            # Update skip set
            self._skip_topics.add(topic.lower())

            print(f"🤔 Curiosity queued: '{topic}'")

        except Exception as e:
            print(f"⚠️  Error adding to curiosity queue: {e}")

    def process_exchange(self, message: str, response: str):
        """
        Called after every chat exchange.
        Detects curiosity and adds topics to the queue.
        """
        topics = self.extract_curious_topics(message, response)
        for topic in topics:
            self.add_to_queue(
                topic,
                reason=f"Detected curiosity during conversation about: {message[:80]}",
                priority=0.6
            )

    def get_pending_topics(self, limit: int = 5) -> List[Dict]:
        """Get highest-priority pending research topics"""
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT id, topic, priority, reason, added_date
                FROM curiosity_queue
                WHERE status = 'pending'
                ORDER BY priority DESC, added_date ASC
                LIMIT ?
            """, (limit,))
            return [
                {
                    'id': row[0], 'topic': row[1],
                    'priority': row[2], 'reason': row[3],
                    'added_date': row[4]
                }
                for row in cursor.fetchall()
            ]
        except Exception as e:
            print(f"⚠️  Error fetching curiosity queue: {e}")
            return []

    def mark_researched(self, topic_id: int, notes: str = ""):
        """Mark a topic as researched"""
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                UPDATE curiosity_queue
                SET status='completed', completed_date=?, research_notes=?
                WHERE id=?
            """, (datetime.now().isoformat(), notes, topic_id))
            self.db.commit()
        except Exception as e:
            print(f"⚠️  Error marking topic as researched: {e}")

    def get_queue_summary(self) -> Dict:
        """Return stats about the curiosity queue"""
        try:
            cursor = self.db.cursor()
            cursor.execute("SELECT status, COUNT(*) FROM curiosity_queue GROUP BY status")
            counts = {row[0]: row[1] for row in cursor.fetchall()}
            return {
                'pending': counts.get('pending', 0),
                'completed': counts.get('completed', 0),
                'total': sum(counts.values())
            }
        except Exception:
            return {'pending': 0, 'completed': 0, 'total': 0}
