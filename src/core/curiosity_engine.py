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
try:
    from core.ai_engine import get_ollama_options
except ImportError:
    def get_ollama_options(config):
        hw = config.get('hardware', {})
        opts = {'num_ctx': hw.get('context_window', 4096), 'num_thread': hw.get('num_threads', 4)}
        if hw.get('gpu_enabled', True) and hw.get('num_gpu', 1) > 0:
            opts['num_gpu'] = 999
        else:
            opts['num_gpu'] = 0
        return opts


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

    def extract_curious_topics(self, message: str, response: str,
                               ollama_model: str = None) -> List[str]:
        """
        Use the LLM to intelligently identify genuine intellectual topics
        worth researching — not sentence fragments or conversational phrases.
        Falls back to regex patterns if ollama is unavailable.
        """
        # Try LLM-based extraction first
        if ollama_model:
            try:
                from core.ai_engine import get_ollama_client
                import re

                prompt = f"""Review this conversation exchange and identify any specific intellectual topics, concepts, or subjects that would be worth researching.

User said: {message[:300]}
AI responded: {response[:300]}

List only REAL, RESEARCHABLE TOPICS — things like:
- Named concepts (e.g. "reconstructive memory", "confabulation", "quantum entanglement")
- Fields of study (e.g. "neuroscience of memory", "AI consciousness research")
- Specific questions about how something works (e.g. "how neural networks learn")
- Named events, phenomena, or entities worth knowing more about

DO NOT include:
- Sentence fragments or partial phrases
- Conversational filler ("way to convey", "been thinking")
- Vague references ("that thing", "what you said")
- Topics already fully explained in the conversation

If there are no genuinely researchable topics, return an empty list.

Return ONLY a JSON array of short topic strings (3-8 words each). Example:
["reconstructive memory neuroscience", "AI consciousness theories", "quantum entanglement basics"]

Return [] if nothing qualifies."""

                client = get_ollama_client(self.config)
                response_obj = client.generate(model=ollama_model, prompt=prompt,
                                               options=get_ollama_options(self.config))
                raw = re.sub(r'<think>.*?</think>', '', response_obj['response'],
                             flags=re.DOTALL).strip()

                # Extract JSON array
                match = re.search(r'\[.*?\]', raw, re.DOTALL)
                if match:
                    topics = json.loads(match.group())
                    # Filter against known topics and validate quality
                    valid = []
                    for t in topics:
                        t = str(t).strip()
                        words = t.split()
                        if (len(words) >= 2 and len(t) >= 10 and
                                t.lower() not in self._skip_topics):
                            valid.append(t)
                    return valid[:3]  # Max 3 high-quality topics per exchange
            except Exception as e:
                print(f"  ⚠️  LLM curiosity extraction failed, using fallback: {e}")

        # Fallback: conservative regex patterns only
        import re
        topics = []
        combined = (message + " " + response).lower()

        patterns = [
            r"i(?:'m| am) curious about ([a-z][a-z\s]{4,35}?)(?:\.|,|\?|$)",
            r"i wonder (?:about |why |how )([a-z][a-z\s]{4,35}?)(?:\.|,|\?|$)",
            r"(?:fascinating|intriguing) (?:concept|idea|topic)[:\s]+([a-z][a-z\s]{4,35}?)(?:\.|,|\?|$)",
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, combined):
                topic = match.group(1).strip().rstrip('.,!?')
                words = topic.split()
                if (len(words) >= 2 and len(topic) >= 10 and
                        topic.lower() not in self._skip_topics):
                    topics.append(topic)

        return list(set(topics))[:3]

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

    def process_exchange(self, message: str, response: str,
                         ollama_model: str = None):
        """
        Called after every chat exchange.
        Detects curiosity and adds topics to the queue.
        """
        topics = self.extract_curious_topics(message, response, ollama_model)
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

    def scan_hub_replica(self, replica_path: str):
        """
        Scan a newly received hub_replica.db for topics worth researching.

        Called automatically when Nexira receives a replica push from the Hub.
        Extracts topics from hub conversations and decisions, adds them to
        the curiosity queue tagged as source='hub_collaboration'.

        This is how the AI becomes naturally aware of and curious about
        content from hub sessions — through the same curiosity pipeline
        it uses for everything else.
        """
        import sqlite3 as _sqlite3
        import os

        if not os.path.exists(replica_path):
            print(f"[CURIOSITY] Hub replica not found at {replica_path}")
            return

        try:
            conn = _sqlite3.connect(replica_path)
            conn.execute("PRAGMA query_only = ON")  # enforce read-only
            c = conn.cursor()

            topics_added = 0

            # Scan recent messages for researchable content
            try:
                c.execute("""
                    SELECT content FROM messages
                    WHERE sender != 'system'
                    ORDER BY timestamp DESC
                    LIMIT 100
                """)
                messages = [row[0] for row in c.fetchall()]
                for msg in messages:
                    extracted = self._extract_topics_from_text(msg)
                    for topic in extracted:
                        if self._add_to_queue(topic, source='hub_collaboration', priority=3):
                            topics_added += 1
            except Exception as e:
                print(f"[CURIOSITY] Replica message scan error: {e}")

            # Scan decisions for follow-up topics
            try:
                c.execute("""
                    SELECT summary, open_questions, next_steps FROM decisions
                    WHERE status = 'active'
                    ORDER BY timestamp DESC
                    LIMIT 20
                """)
                decisions = c.fetchall()
                for decision in decisions:
                    for field in decision:
                        if field:
                            extracted = self._extract_topics_from_text(field)
                            for topic in extracted:
                                if self._add_to_queue(topic, source='hub_collaboration', priority=4):
                                    topics_added += 1
            except Exception:
                pass  # decisions table may not exist in older replicas

            conn.close()
            print(f"[CURIOSITY] Hub replica scan complete — {topics_added} topics added")

        except Exception as e:
            print(f"[CURIOSITY] Hub replica scan failed: {e}")

    def _extract_topics_from_text(self, text: str) -> list:
        """Extract potentially researchable topics from text."""
        if not text or len(text) < 20:
            return []
        stop_words = {
            'the', 'is', 'at', 'which', 'on', 'a', 'an', 'and', 'or', 'but',
            'in', 'with', 'to', 'for', 'that', 'this', 'was', 'are', 'be',
            'have', 'has', 'had', 'from', 'they', 'you', 'we', 'it', 'not',
            'what', 'when', 'how', 'why', 'who', 'will', 'can', 'would', 'could'
        }
        words = text.lower().split()
        topics = [w.strip('.,!?;:') for w in words
                  if w not in stop_words and len(w) > 4 and w.isalpha()]
        # Return unique topics, limit to avoid flooding the queue
        seen = set()
        result = []
        for t in topics:
            if t not in seen:
                seen.add(t)
                result.append(t)
            if len(result) >= 3:
                break
        return result

    def _add_to_queue(self, topic: str, source: str = 'curiosity',
                      priority: int = 5) -> bool:
        """
        Add a topic to the curiosity queue if not already present.
        Returns True if added, False if duplicate.
        """
        try:
            cursor = self.db.cursor()
            # Check if already in queue (pending)
            cursor.execute("""
                SELECT id FROM curiosity_queue
                WHERE LOWER(topic) = LOWER(?) AND status = 'pending'
            """, (topic,))
            if cursor.fetchone():
                return False
            cursor.execute("""
                INSERT INTO curiosity_queue
                (topic, source, priority, status, added_date)
                VALUES (?, ?, ?, 'pending', ?)
            """, (topic, source, priority, datetime.now().isoformat()))
            self.db.commit()
            return True
        except Exception:
            return False
