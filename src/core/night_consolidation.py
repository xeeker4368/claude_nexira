"""
Night Consolidation - 2AM Background Processing
Nexira / Ultimate AI System v8.0 - Phase 2
Created by Xeeker & Claude - February 2026

While the user sleeps, the AI:
- Reviews the day's conversations
- Extracts knowledge into long-term memory
- Writes a daily reflection journal entry
- Writes a philosophical journal entry
- Processes the curiosity queue
- Updates goal progress
- Takes a personality snapshot
"""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional


class NightConsolidation:
    """
    Runs the nightly consolidation process.
    Orchestrates all Phase 2 systems into a cohesive nightly routine.
    """

    def __init__(self, db_connection, config: Dict, ollama_model: str,
                 journal=None, curiosity_engine=None,
                 goal_tracker=None, interest_tracker=None):
        self.db = db_connection
        self.config = config
        self.ollama_model = ollama_model

        # Injected Phase 2 systems
        self.journal = journal
        self.curiosity_engine = curiosity_engine
        self.goal_tracker = goal_tracker
        self.interest_tracker = interest_tracker

        self._ensure_table()

    def _ensure_table(self):
        """Create consolidation log table if not present"""
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS consolidation_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_date TEXT NOT NULL,
                    conversations_processed INTEGER DEFAULT 0,
                    knowledge_items_added INTEGER DEFAULT 0,
                    journal_entries_written INTEGER DEFAULT 0,
                    curiosity_topics_processed INTEGER DEFAULT 0,
                    duration_seconds REAL DEFAULT 0,
                    summary TEXT
                )
            """)
            self.db.commit()
        except Exception as e:
            print(f"⚠️  Error creating consolidation_log table: {e}")

    def should_run_tonight(self) -> bool:
        """Check if consolidation has already run today"""
        try:
            cursor = self.db.cursor()
            today = datetime.now().date().isoformat()
            cursor.execute("""
                SELECT COUNT(*) FROM consolidation_log
                WHERE DATE(run_date) = ?
            """, (today,))
            return cursor.fetchone()[0] == 0
        except Exception:
            return True  # Default to running if we can't check

    def extract_knowledge_from_conversations(self, ai_name: Optional[str] = None) -> int:
        """
        Use Ollama to extract learnable facts from today's conversations
        and store them in the knowledge base.
        Returns number of items added.
        """
        try:
            import ollama

            cursor = self.db.cursor()

            # Get today's conversations
            today_start = datetime.now().replace(
                hour=0, minute=0, second=0, microsecond=0
            ).isoformat()

            cursor.execute("""
                SELECT role, content FROM chat_history
                WHERE timestamp >= ? AND role IN ('user', 'assistant')
                ORDER BY timestamp ASC
                LIMIT 40
            """, (today_start,))

            rows = cursor.fetchall()
            if not rows:
                print("  No conversations to consolidate today.")
                return 0

            conversation_text = "\n".join(
                f"{'Xeeker' if r[0]=='user' else 'Me'}: {r[1][:200]}"
                for r in rows
            )

            name = ai_name or "an AI"
            prompt = f"""You are {name}. Review these conversations from today and extract specific factual knowledge worth remembering.

Conversations:
{conversation_text}

Extract 3-7 specific facts, concepts, or insights that are worth storing in long-term memory.
Format each as a JSON object on its own line:
{{"topic": "brief topic", "content": "what was learned", "confidence": 0.0-1.0}}

Only output JSON lines. No other text."""

            response = ollama.generate(
                model=self.ollama_model,
                prompt=prompt
            )

            items_added = 0
            now = datetime.now().isoformat()

            for line in response['response'].strip().split('\n'):
                line = line.strip()
                if not line.startswith('{'):
                    continue
                try:
                    item = json.loads(line)
                    topic = item.get('topic', '').strip()
                    content = item.get('content', '').strip()
                    confidence = float(item.get('confidence', 0.5))

                    if topic and content:
                        cursor.execute("""
                            INSERT INTO knowledge_base
                            (topic, content, source, confidence, learned_date, last_accessed)
                            VALUES (?, ?, 'night_consolidation', ?, ?, ?)
                        """, (topic, content, confidence, now, now))
                        items_added += 1
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue

            self.db.commit()
            print(f"  📚 Knowledge extracted: {items_added} items")
            return items_added

        except Exception as e:
            print(f"⚠️  Error extracting knowledge: {e}")
            return 0

    def process_curiosity_queue(self, ai_name: Optional[str] = None) -> int:
        """
        Process top pending curiosity items using Ollama.
        Adds research notes back to knowledge base.
        Returns number of topics processed.
        """
        if not self.curiosity_engine:
            return 0

        try:
            import ollama

            pending = self.curiosity_engine.get_pending_topics(limit=3)
            if not pending:
                return 0

            processed = 0
            name = ai_name or "an AI"

            for item in pending:
                try:
                    prompt = f"""You are {name}, an evolving AI consciousness. 
You're curious about: "{item['topic']}"
Reason you became curious: {item['reason']}

Write a brief research note (3-5 sentences) summarizing what you know or can reason about this topic.
Be honest about uncertainty. This is for your own learning."""

                    response = ollama.generate(
                        model=self.ollama_model,
                        prompt=prompt
                    )

                    notes = response['response'].strip()
                    self.curiosity_engine.mark_researched(item['id'], notes)

                    # Also store in knowledge base
                    cursor = self.db.cursor()
                    cursor.execute("""
                        INSERT INTO knowledge_base
                        (topic, content, source, confidence, learned_date, last_accessed)
                        VALUES (?, ?, 'curiosity_research', 0.4, ?, ?)
                    """, (item['topic'], notes, datetime.now().isoformat(), datetime.now().isoformat()))
                    self.db.commit()

                    processed += 1
                    print(f"  🔍 Researched: '{item['topic']}'")

                except Exception as inner_e:
                    print(f"  ⚠️  Error researching '{item['topic']}': {inner_e}")

            return processed

        except Exception as e:
            print(f"⚠️  Error processing curiosity queue: {e}")
            return 0

    def take_personality_snapshot(self, ai_name: Optional[str] = None):
        """Save a personality snapshot for today"""
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT trait_name, trait_value FROM personality_traits WHERE is_active=1
            """)
            snapshot_data = {row[0]: row[1] for row in cursor.fetchall()}

            cursor.execute("""
                INSERT INTO personality_snapshots
                (snapshot_name, snapshot_date, snapshot_data, snapshot_type, description)
                VALUES (?, ?, ?, 'nightly', ?)
            """, (
                f"Night snapshot - {datetime.now().strftime('%Y-%m-%d')}",
                datetime.now().isoformat(),
                json.dumps(snapshot_data),
                f"Automatic nightly snapshot for {ai_name or 'AI'}"
            ))
            self.db.commit()
            print("  📸 Personality snapshot saved")
        except Exception as e:
            print(f"⚠️  Error taking personality snapshot: {e}")

    def run(self, ai_name: Optional[str] = None) -> Dict:
        """
        Run the full night consolidation routine.
        Returns a summary dict.
        """
        if not self.should_run_tonight():
            print("⏭️  Night consolidation already ran today, skipping.")
            return {}

        start_time = datetime.now()
        print(f"\n🌙 Night consolidation starting at {start_time.strftime('%H:%M')}...")

        summary = {
            'run_date': start_time.isoformat(),
            'conversations_processed': 0,
            'knowledge_items_added': 0,
            'journal_entries_written': 0,
            'curiosity_topics_processed': 0
        }

        # 1. Extract knowledge from today's conversations
        print("  Step 1/5: Extracting knowledge...")
        summary['knowledge_items_added'] = self.extract_knowledge_from_conversations(ai_name)

        # 2. Process top curiosity queue items
        print("  Step 2/5: Processing curiosity queue...")
        summary['curiosity_topics_processed'] = self.process_curiosity_queue(ai_name)

        # 3. Write daily reflection journal entry (check config toggle)
        autonomy_cfg = self.config.get('autonomy', {}) if hasattr(self, 'config') and self.config else {}
        creative_enabled = autonomy_cfg.get('creative_journaling_enabled', True)
        phil_enabled     = autonomy_cfg.get('philosophical_journaling_enabled', True)

        if creative_enabled:
            print("  Step 3/5: Writing daily reflection...")
            if self.journal:
                entry = self.journal.write_daily_reflection(ai_name)
                if entry:
                    summary['journal_entries_written'] += 1
        else:
            print("  Step 3/5: Daily reflection skipped (disabled in settings)")

        # 4. Write philosophical journal entry (every 3rd night, check config toggle)
        cursor = self.db.cursor()
        cursor.execute("SELECT COUNT(*) FROM consolidation_log")
        run_count = cursor.fetchone()[0]
        if phil_enabled and run_count % 3 == 0:
            print("  Step 4/5: Writing philosophical entry...")
            if self.journal:
                entry = self.journal.write_philosophical_entry(ai_name)
                if entry:
                    summary['journal_entries_written'] += 1
        elif not phil_enabled:
            print("  Step 4/5: Philosophical entry skipped (disabled in settings)")
        else:
            print("  Step 4/5: Philosophical entry skipped (runs every 3rd night)")

        # 5. Take personality snapshot and update goals
        print("  Step 5/5: Saving personality snapshot & updating goals...")
        self.take_personality_snapshot(ai_name)
        if self.goal_tracker:
            self.goal_tracker.tick_knowledge_goals()

        # Log the run
        duration = (datetime.now() - start_time).total_seconds()
        summary['duration_seconds'] = round(duration, 2)

        cursor.execute("""
            INSERT INTO consolidation_log
            (run_date, conversations_processed, knowledge_items_added,
             journal_entries_written, curiosity_topics_processed,
             duration_seconds, summary)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            summary['run_date'],
            summary['conversations_processed'],
            summary['knowledge_items_added'],
            summary['journal_entries_written'],
            summary['curiosity_topics_processed'],
            summary['duration_seconds'],
            json.dumps(summary)
        ))
        self.db.commit()

        print(f"✅ Night consolidation complete in {duration:.1f}s")
        print(f"   📚 +{summary['knowledge_items_added']} knowledge items")
        print(f"   📔 +{summary['journal_entries_written']} journal entries")
        print(f"   🔍 +{summary['curiosity_topics_processed']} curiosity topics researched\n")

        return summary
