"""
Interest Tracker - Developing Genuine Interests Over Time
Nexira / Ultimate AI System v8.0 - Phase 2
Created by Xeeker & Claude - February 2026

Topics mentioned repeatedly get promoted to interests with increasing depth.
Casual mention → Casual interest → Deep interest → Passion
"""

import re
from datetime import datetime
from typing import Dict, List, Tuple


# Mention thresholds for each interest level
INTEREST_LEVELS = {
    'casual':    (1,  4),   # 1–4 mentions
    'interested': (5, 14),  # 5–14 mentions
    'deep':      (15, 29),  # 15–29 mentions
    'passion':   (30, 9999) # 30+ mentions
}


class InterestTracker:
    """
    Monitors conversations and builds up a picture of what
    the AI genuinely cares about over time.
    """

    def __init__(self, db_connection, config: Dict):
        self.db = db_connection
        self.config = config

        # Simple stop words for topic extraction
        self._stop_words = {
            'the', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
            'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
            'could', 'should', 'may', 'might', 'shall', 'can', 'need',
            'a', 'an', 'and', 'but', 'or', 'so', 'yet', 'for', 'nor',
            'in', 'on', 'at', 'to', 'from', 'with', 'by', 'about',
            'that', 'this', 'these', 'those', 'it', 'its', 'of', 'not',
            'what', 'how', 'why', 'when', 'where', 'who', 'which',
            'just', 'very', 'really', 'also', 'more', 'some', 'any',
            'think', 'know', 'like', 'want', 'get', 'make', 'see',
            'you', 'your', 'me', 'my', 'we', 'our', 'they', 'them',
            'sure', 'okay', 'yes', 'yes', 'no', 'well', 'now', 'then'
        }

    def _extract_topics(self, text: str) -> List[str]:
        """Extract meaningful noun-like topics from text"""
        # Remove punctuation and split
        clean = re.sub(r'[^\w\s]', ' ', text.lower())
        words = clean.split()

        # Filter stop words and short words
        candidates = [w for w in words if w not in self._stop_words and len(w) > 4]

        # Also grab 2-word phrases (bigrams)
        bigrams = [f"{candidates[i]} {candidates[i+1]}"
                   for i in range(len(candidates) - 1)]

        return (candidates + bigrams)[:20]

    def process_exchange(self, message: str, response: str):
        """
        Called after every chat exchange.
        Tracks topic mentions and updates interest levels.
        """
        topics = self._extract_topics(message + " " + response)

        for topic in set(topics):  # deduplicate
            self._record_mention(topic)

    def _record_mention(self, topic: str):
        """Record a topic mention and update interest level"""
        try:
            cursor = self.db.cursor()
            now = datetime.now().isoformat()

            # Check if topic already tracked
            cursor.execute(
                "SELECT id, mention_count FROM interests WHERE LOWER(topic)=?",
                (topic.lower(),)
            )
            row = cursor.fetchone()

            if row:
                topic_id, count = row[0], row[1]
                new_count = count + 1
                new_level = self._calculate_level(new_count)

                cursor.execute("""
                    UPDATE interests
                    SET mention_count=?, interest_level=?, last_activity=?
                    WHERE id=?
                """, (new_count, new_level, now, topic_id))

                # Log level-up
                old_level = self._calculate_level(count)
                if new_level != old_level:
                    print(f"⭐ Interest level up: '{topic}' → {new_level} ({new_count} mentions)")

            else:
                # New topic
                cursor.execute("""
                    INSERT INTO interests
                    (topic, interest_level, mention_count, first_mention, last_activity)
                    VALUES (?, 'casual', 1, ?, ?)
                """, (topic, now, now))

            self.db.commit()

        except Exception as e:
            print(f"⚠️  Error recording interest mention: {e}")

    def _calculate_level(self, mention_count: int) -> str:
        for level, (low, high) in INTEREST_LEVELS.items():
            if low <= mention_count <= high:
                return level
        return 'passion'

    def get_top_interests(self, limit: int = 10, min_level: str = 'casual') -> List[Dict]:
        """Return top interests sorted by mention count"""
        level_order = list(INTEREST_LEVELS.keys())
        min_idx = level_order.index(min_level) if min_level in level_order else 0

        try:
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT topic, interest_level, mention_count, first_mention, last_activity
                FROM interests
                ORDER BY mention_count DESC
                LIMIT ?
            """, (limit * 3,))  # fetch more, filter below

            results = []
            for row in cursor.fetchall():
                level = row[1]
                if level in level_order and level_order.index(level) >= min_idx:
                    results.append({
                        'topic': row[0],
                        'level': level,
                        'mentions': row[2],
                        'first_seen': row[3],
                        'last_seen': row[4]
                    })

            return results[:limit]

        except Exception as e:
            print(f"⚠️  Error fetching interests: {e}")
            return []

    def get_interests_summary(self) -> str:
        """Return a human-readable summary of current interests"""
        interests = self.get_top_interests(limit=5, min_level='interested')
        if not interests:
            return "No strong interests developed yet."

        lines = []
        for i in interests:
            lines.append(f"- {i['topic'].title()} ({i['level']}, {i['mentions']} mentions)")
        return "\n".join(lines)
