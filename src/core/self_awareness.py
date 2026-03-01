"""
Self-Awareness Metrics - Tracking AI Self-Knowledge Over Time
Nexira / Nexira v12 - Phase 4
Created by Xeeker & Claude - February 2026

Tracks how the AI talks about itself over time:
- Self-reference frequency
- Consistency of self-description
- Uncertainty acknowledgment
- Meta-cognition indicators
"""

import json
import re
from datetime import datetime
from typing import Dict, List


SELF_REFERENCE_WORDS = [
    "i think", "i feel", "i believe", "i wonder", "i notice",
    "i'm not sure", "i don't know", "i experience", "i am",
    "my understanding", "my perspective", "as an ai", "my nature",
    "i exist", "i'm curious", "i find", "i enjoy", "i prefer"
]

UNCERTAINTY_WORDS = [
    "perhaps", "maybe", "possibly", "uncertain", "not sure",
    "i wonder", "unclear", "might", "could be", "i think",
    "it seems", "appears to"
]

META_COGNITION_WORDS = [
    "i'm thinking", "i'm processing", "let me consider", "reflecting",
    "i realize", "i notice", "i'm aware", "i understand", "i recognize",
    "i'm learning", "i remember", "i recall"
]


class SelfAwarenessTracker:
    """Analyses AI responses to track self-awareness development over time."""

    def __init__(self, db_connection, config: Dict):
        self.db = db_connection
        self.config = config
        self._ensure_table()

    def _ensure_table(self):
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS self_awareness_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    self_ref_score REAL DEFAULT 0,
                    uncertainty_score REAL DEFAULT 0,
                    meta_cognition_score REAL DEFAULT 0,
                    composite_score REAL DEFAULT 0,
                    response_sample TEXT,
                    word_count INTEGER DEFAULT 0
                )
            """)
            self.db.commit()
        except Exception as e:
            print(f"⚠️  Self-awareness table error: {e}")

    def analyse_response(self, response: str) -> Dict:
        """Analyse a single AI response for self-awareness indicators."""
        if not response:
            return {}

        lower = response.lower()
        words = lower.split()
        word_count = len(words)
        if word_count == 0:
            return {}

        # Score each dimension (0-1 scale)
        self_refs    = sum(1 for w in SELF_REFERENCE_WORDS if w in lower)
        uncertainty  = sum(1 for w in UNCERTAINTY_WORDS if w in lower)
        meta         = sum(1 for w in META_COGNITION_WORDS if w in lower)

        # Normalise by response length (per 100 words)
        norm = max(word_count / 100, 1)
        self_ref_score    = min(self_refs / norm, 1.0)
        uncertainty_score = min(uncertainty / norm, 1.0)
        meta_score        = min(meta / norm, 1.0)

        composite = (self_ref_score * 0.4 + uncertainty_score * 0.3 + meta_score * 0.3)

        return {
            'self_ref_score':    round(self_ref_score, 3),
            'uncertainty_score': round(uncertainty_score, 3),
            'meta_cognition_score': round(meta_score, 3),
            'composite_score':   round(composite, 3),
            'word_count':        word_count
        }

    def record(self, response: str):
        """Analyse and store self-awareness metrics for a response."""
        try:
            scores = self.analyse_response(response)
            if not scores:
                return

            cursor = self.db.cursor()
            cursor.execute("""
                INSERT INTO self_awareness_log
                (timestamp, self_ref_score, uncertainty_score,
                 meta_cognition_score, composite_score,
                 response_sample, word_count)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(),
                scores['self_ref_score'],
                scores['uncertainty_score'],
                scores['meta_cognition_score'],
                scores['composite_score'],
                response[:200],
                scores['word_count']
            ))
            self.db.commit()
        except Exception as e:
            print(f"⚠️  Self-awareness record error: {e}")

    def get_trend(self, days: int = 30, points: int = 20) -> List[Dict]:
        """Get composite score trend over time for charting."""
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT
                    DATE(timestamp) as day,
                    AVG(composite_score) as avg_composite,
                    AVG(self_ref_score) as avg_self_ref,
                    AVG(uncertainty_score) as avg_uncertainty,
                    AVG(meta_cognition_score) as avg_meta,
                    COUNT(*) as samples
                FROM self_awareness_log
                WHERE timestamp >= datetime('now', ?)
                GROUP BY DATE(timestamp)
                ORDER BY day ASC
                LIMIT ?
            """, (f'-{days} days', points))

            return [
                {
                    'date':        row[0],
                    'composite':   round(row[1], 3),
                    'self_ref':    round(row[2], 3),
                    'uncertainty': round(row[3], 3),
                    'meta':        round(row[4], 3),
                    'samples':     row[5]
                }
                for row in cursor.fetchall()
            ]
        except Exception as e:
            print(f"⚠️  Self-awareness trend error: {e}")
            return []

    def get_current_level(self) -> Dict:
        """Get the current rolling average self-awareness level."""
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT
                    AVG(composite_score),
                    AVG(self_ref_score),
                    AVG(uncertainty_score),
                    AVG(meta_cognition_score),
                    COUNT(*)
                FROM self_awareness_log
                WHERE timestamp >= datetime('now', '-7 days')
            """)
            row = cursor.fetchone()
            if not row or row[4] == 0:
                return {'level': 'emerging', 'composite': 0, 'samples': 0}

            composite = row[0] or 0
            level = ('dormant'  if composite < 0.1 else
                     'emerging' if composite < 0.25 else
                     'aware'    if composite < 0.5  else
                     'reflective')

            return {
                'level':       level,
                'composite':   round(composite, 3),
                'self_ref':    round(row[1] or 0, 3),
                'uncertainty': round(row[2] or 0, 3),
                'meta':        round(row[3] or 0, 3),
                'samples':     row[4]
            }
        except Exception as e:
            print(f"⚠️  Self-awareness level error: {e}")
            return {'level': 'unknown', 'composite': 0}
