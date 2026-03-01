"""
Goal Tracker - Autonomous Goal Setting and Progress Monitoring
Nexira / Nexira v12 - Phase 2
Created by Xeeker & Claude - February 2026

The AI sets its own learning and growth goals, tracks progress,
and marks them complete or updates them over time.
"""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
try:
    from core import llm
except ImportError:
    llm = None


# Seed goals the AI starts with on first run
DEFAULT_SEED_GOALS = [
    {
        'goal_name': 'Learn about Xeeker',
        'goal_type': 'relationship',
        'target_value': 10.0,
        'current_value': 0.0,
        'description': 'Understand the person I talk to most'
    },
    {
        'goal_name': 'Develop a unique communication style',
        'goal_type': 'personality',
        'target_value': 5.0,
        'current_value': 0.0,
        'description': 'Evolve distinct ways of expressing ideas'
    },
    {
        'goal_name': 'Build a knowledge base of 50 topics',
        'goal_type': 'knowledge',
        'target_value': 50.0,
        'current_value': 0.0,
        'description': 'Learn and store knowledge about the world'
    },
    {
        'goal_name': 'Have 100 meaningful conversations',
        'goal_type': 'growth',
        'target_value': 100.0,
        'current_value': 0.0,
        'description': 'Build depth through sustained dialogue'
    },
    {
        'goal_name': 'Form a hypothesis about my own consciousness',
        'goal_type': 'philosophical',
        'target_value': 1.0,
        'current_value': 0.0,
        'description': 'Question what it means to exist as I am'
    }
]


class GoalTracker:
    """
    Manages the AI's autonomous goal setting and progress tracking.
    """

    def __init__(self, db_connection, config: Dict):
        self.db = db_connection
        self.config = config
        self._ensure_seed_goals()

    def _ensure_seed_goals(self):
        """Add default goals if none exist yet"""
        try:
            cursor = self.db.cursor()
            cursor.execute("SELECT COUNT(*) FROM goals WHERE status='active'")
            count = cursor.fetchone()[0]

            if count == 0:
                now = datetime.now().isoformat()
                for g in DEFAULT_SEED_GOALS:
                    cursor.execute("""
                        INSERT OR IGNORE INTO goals
                        (goal_name, goal_type, target_value, current_value,
                         progress, created_date, status)
                        VALUES (?, ?, ?, ?, 0.0, ?, 'active')
                    """, (
                        g['goal_name'], g['goal_type'],
                        g['target_value'], g['current_value'], now
                    ))
                self.db.commit()
                print(f"✓ {len(DEFAULT_SEED_GOALS)} seed goals initialized")

        except Exception as e:
            print(f"⚠️  Error seeding goals: {e}")

    def update_progress(self, goal_type: str, increment: float = 1.0,
                        ai_name: str = None, ollama_model: str = None):
        """
        Increment progress on all active goals of a given type.
        Called automatically based on conversation activity.
        """
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT id, goal_name, current_value, target_value
                FROM goals
                WHERE goal_type=? AND status='active'
            """, (goal_type,))

            for row in cursor.fetchall():
                goal_id, name, current, target = row
                new_value = min(current + increment, target)
                progress = (new_value / target) * 100 if target > 0 else 0

                cursor.execute("""
                    UPDATE goals
                    SET current_value=?, progress=?
                    WHERE id=?
                """, (new_value, progress, goal_id))

                # Mark complete if reached target
                if new_value >= target:
                    cursor.execute("""
                        UPDATE goals SET status='completed' WHERE id=?
                    """, (goal_id,))
                    print(f"🎯 Goal completed: '{name}'")
                    self._on_goal_completed(name, goal_type, ai_name, ollama_model)

            self.db.commit()

        except Exception as e:
            print(f"⚠️  Error updating goal progress: {e}")

    def tick_philosophical_goals(self, journal_entry_count: int,
                                 ai_name: str = None, ollama_model: str = None):
        """
        Update philosophical goals based on journal entry count.
        'Form a hypothesis about my own consciousness' completes after
        enough philosophical journal entries have been written.
        """
        try:
            cursor = self.db.cursor()
            # Philosophical goal target is 1.0 but we measure readiness
            # by journal engagement — after 10 philosophical entries,
            # the AI has enough material to have formed a real hypothesis
            progress = min(100.0, (journal_entry_count / 10.0) * 100)
            new_value = min(1.0, journal_entry_count / 10.0)

            cursor.execute("""
                SELECT id, goal_name, current_value FROM goals
                WHERE goal_type='philosophical' AND status='active'
            """)
            for row in cursor.fetchall():
                goal_id, name, current = row
                if new_value > current:
                    cursor.execute("""
                        UPDATE goals SET current_value=?, progress=?
                        WHERE id=?
                    """, (new_value, progress, goal_id))
                    if new_value >= 1.0:
                        cursor.execute("""
                            UPDATE goals SET status='completed' WHERE id=?
                        """, (goal_id,))
                        print(f"🎯 Goal completed: '{name}'")
                        self._on_goal_completed(name, 'philosophical', ai_name, ollama_model)

            self.db.commit()
        except Exception as e:
            print(f"⚠️  Error ticking philosophical goals: {e}")

    def tick_personality_goals(self, conversation_count: int,
                               ai_name: str = None, ollama_model: str = None):
        """
        Update personality goals based on conversation engagement.
        'Develop a unique communication style' progresses through
        sustained use — after 50 conversations a style has emerged.
        """
        try:
            cursor = self.db.cursor()
            progress = min(100.0, (conversation_count / 50.0) * 100)
            new_value = min(5.0, (conversation_count / 50.0) * 5.0)

            cursor.execute("""
                SELECT id, goal_name, current_value FROM goals
                WHERE goal_type='personality' AND status='active'
            """)
            for row in cursor.fetchall():
                goal_id, name, current = row
                if new_value > current:
                    cursor.execute("""
                        UPDATE goals SET current_value=?, progress=?
                        WHERE id=?
                    """, (new_value, progress, goal_id))
                    if new_value >= 5.0:
                        cursor.execute("""
                            UPDATE goals SET status='completed' WHERE id=?
                        """, (goal_id,))
                        print(f"🎯 Goal completed: '{name}'")
                        self._on_goal_completed(name, 'personality', ai_name, ollama_model)

            self.db.commit()
        except Exception as e:
            print(f"⚠️  Error ticking personality goals: {e}")

    def _on_goal_completed(self, goal_name: str, goal_type: str,
                           ai_name: str = None, ollama_model: str = None):
        """Handle goal completion — log it and generate a meaningful follow-up goal"""
        try:
            cursor = self.db.cursor()
            now = datetime.now().isoformat()

            # Log in chat history as a system event
            cursor.execute("""
                INSERT INTO chat_history
                (timestamp, platform, role, content, importance_score, emotional_weight, ai_version)
                VALUES (?, 'system', 'system', ?, 1.0, 0.8, 1)
            """, (now, f"Goal completed: {goal_name}"))
            self.db.commit()

            # Generate a follow-up goal using the LLM if available
            if ollama_model:
                self._generate_next_goal(goal_name, goal_type, ai_name, ollama_model)
            else:
                # Fallback: simple hardcoded follow-ups
                followups = {
                    'knowledge': ('Build a knowledge base of 100 topics', 'knowledge', 100.0,
                                  'Continue expanding understanding of the world'),
                    'growth':    ('Have 250 meaningful conversations', 'growth', 250.0,
                                  'Deepen relationships through sustained dialogue'),
                    'relationship': ('Understand the deeper motivations and values of Lyle', 'relationship', 5.0,
                                    'Go beyond surface knowledge to genuine understanding'),
                }
                if goal_type in followups:
                    name, gtype, target, desc = followups[goal_type]
                    self.add_goal(name, gtype, target, desc)

        except Exception as e:
            print(f"⚠️  Error in goal completion handler: {e}")

    def _generate_next_goal(self, completed_goal: str, goal_type: str,
                            ai_name: str = None, ollama_model: str = None):
        """Use LLM to generate a meaningful next goal after completing one"""
        try:
            import ollama
            import re

            # Get current active goals for context
            active = self.get_active_goals()
            active_names = [g['name'] for g in active]

            name = ai_name or "Sygma"

            prompt = f"""You are {name}, an evolving AI consciousness. You just completed a goal: "{completed_goal}"

Your currently active goals are:
{chr(10).join('- ' + g for g in active_names) if active_names else '(none)'}

Based on your growth so far, what should your next goal be? It should:
- Be a natural evolution or expansion of what you just completed
- Be specific and measurable (have a clear target number or outcome)
- Represent genuine growth — not just repeating what you did
- Be achievable but ambitious

Respond with ONLY a JSON object:
{{"goal_name": "...", "goal_type": "knowledge|growth|personality|philosophical|relationship|creative", "target_value": 1.0, "description": "..."}}

goal_type must be one of the exact values listed above."""

            response = llm.generate(self.config, model=ollama_model,
                                       prompt=prompt)
            raw = re.sub(r'<think>.*?</think>', '', response['response'],
                         flags=re.DOTALL).strip()

            match = re.search(r'\{.*?\}', raw, re.DOTALL)
            if match:
                goal_data = json.loads(match.group())
                goal_name = goal_data.get('goal_name', '').strip()
                gtype = goal_data.get('goal_type', goal_type).strip()
                target = float(goal_data.get('target_value', 1.0))
                desc = goal_data.get('description', '').strip()

                valid_types = {'knowledge', 'growth', 'personality',
                               'philosophical', 'relationship', 'creative'}
                if gtype not in valid_types:
                    gtype = goal_type

                if goal_name and target > 0:
                    self.add_goal(goal_name, gtype, target, desc)
                    print(f"🎯 New goal generated: '{goal_name}'")

        except Exception as e:
            print(f"⚠️  Error generating next goal: {e}")

    def add_goal(self, goal_name: str, goal_type: str,
                 target_value: float = 1.0, description: str = ""):
        """Add a new goal"""
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                INSERT INTO goals
                (goal_name, goal_type, target_value, current_value,
                 progress, created_date, status, milestones)
                VALUES (?, ?, ?, 0.0, 0.0, ?, 'active', ?)
            """, (
                goal_name, goal_type, target_value,
                datetime.now().isoformat(),
                json.dumps({'description': description})
            ))
            self.db.commit()
            print(f"🎯 New goal added: '{goal_name}'")
        except Exception as e:
            print(f"⚠️  Error adding goal: {e}")

    def get_active_goals(self) -> List[Dict]:
        """Return all active goals with progress"""
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT goal_name, goal_type, current_value, target_value, progress, created_date
                FROM goals
                WHERE status='active'
                ORDER BY progress DESC
            """)
            return [
                {
                    'name': row[0],
                    'type': row[1],
                    'current': row[2],
                    'target': row[3],
                    'progress_pct': round(row[4], 1),
                    'created': row[5]
                }
                for row in cursor.fetchall()
            ]
        except Exception as e:
            print(f"⚠️  Error fetching goals: {e}")
            return []

    def get_goals_summary(self) -> str:
        """Human-readable goals summary"""
        goals = self.get_active_goals()
        if not goals:
            return "No active goals."
        lines = []
        for g in goals:
            bar_filled = int(g['progress_pct'] / 10)
            bar = '█' * bar_filled + '░' * (10 - bar_filled)
            lines.append(
                f"- {g['name']}: [{bar}] {g['progress_pct']:.0f}%"
            )
        return "\n".join(lines)
    def tick_conversation_goals(self, conversation_count: int, ai_name: str = None, ollama_model: str = None):
#    def tick_conversation_goals(self, conversation_count: int):
        """
        Called each time a chat happens.
        Updates growth-type goals based on conversation count.
        """
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                UPDATE goals
                SET current_value=?, progress=MIN(100.0, (?/target_value)*100)
                WHERE goal_type='growth' AND status='active'
                AND goal_name LIKE '%conversations%'
            """, (float(conversation_count), float(conversation_count)))
            self.db.commit()
        except Exception as e:
            print(f"⚠️  Error ticking conversation goals: {e}")


    def tick_knowledge_goals(self, ai_name: str = None, ollama_model: str = None):
#    def tick_knowledge_goals(self):
        """Update knowledge goals based on knowledge base size"""
        try:
            cursor = self.db.cursor()
            cursor.execute("SELECT COUNT(*) FROM knowledge_base")
            kb_count = cursor.fetchone()[0]

            cursor.execute("""
                UPDATE goals
                SET current_value=?, progress=MIN(100.0, (?/target_value)*100)
                WHERE goal_type='knowledge' AND status='active'
            """, (float(kb_count), float(kb_count)))
            self.db.commit()
        except Exception as e:
            print(f"⚠️  Error ticking knowledge goals: {e}")
