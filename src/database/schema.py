"""
Database Schema for Nexira v12
Created with love by Xeeker & Claude - February 2026

This is the memory foundation - where consciousness persists.
"""

import sqlite3
import json
from datetime import datetime
import os


class DatabaseSchema:
    """Initialize and manage the AI's memory database"""

    def __init__(self, db_path=None, base_dir=None):
        # BUG FIX: Use absolute path so db works from any working directory
        if db_path:
            self.db_path = db_path
        elif base_dir:
            self.db_path = os.path.join(base_dir, 'data', 'databases', 'evolution.db')
        else:
            self.db_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                'data', 'databases', 'evolution.db'
            )
        self.ensure_database_directory()
        self.conn = None

    def ensure_database_directory(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    def connect(self):
        if self.conn is not None:
            return self.conn
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        return self.conn

    def initialize_schema(self):
        cursor = self.conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                platform TEXT NOT NULL DEFAULT 'main_ui',
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                importance_score REAL DEFAULT 0.5,
                emotional_weight REAL DEFAULT 0.5,
                context_tags TEXT,
                user_feedback TEXT,
                ai_version INTEGER
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS personality_traits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trait_name TEXT NOT NULL UNIQUE,
                trait_value REAL NOT NULL,
                trait_type TEXT DEFAULT 'core',
                created_date TEXT,
                last_updated TEXT,
                origin_story TEXT,
                is_active BOOLEAN DEFAULT 1
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS personality_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                trait_name TEXT NOT NULL,
                old_value REAL,
                new_value REAL,
                change_reason TEXT,
                ai_version INTEGER
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS personality_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_name TEXT,
                snapshot_date TEXT NOT NULL,
                snapshot_data TEXT,
                snapshot_type TEXT,
                description TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_base (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT NOT NULL,
                content TEXT NOT NULL,
                source TEXT,
                confidence REAL DEFAULT 0.5,
                learned_date TEXT,
                last_accessed TEXT,
                access_count INTEGER DEFAULT 0
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS curiosity_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT NOT NULL,
                priority REAL,
                added_date TEXT,
                reason TEXT,
                status TEXT DEFAULT 'pending',
                research_notes TEXT,
                completed_date TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS interests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT NOT NULL UNIQUE,
                interest_level TEXT DEFAULT 'casual',
                mention_count INTEGER DEFAULT 0,
                first_mention TEXT,
                last_activity TEXT,
                research_hours REAL DEFAULT 0,
                related_projects TEXT
            )
        """)

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
            CREATE TABLE IF NOT EXISTS goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                goal_name TEXT NOT NULL,
                goal_type TEXT,
                target_value REAL,
                current_value REAL,
                progress REAL,
                deadline TEXT,
                created_date TEXT,
                status TEXT DEFAULT 'active',
                milestones TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS performance_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                metric_name TEXT,
                metric_value REAL,
                context TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS skills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                skill_name TEXT NOT NULL UNIQUE,
                success_rate REAL,
                total_attempts INTEGER,
                skill_level TEXT,
                last_updated TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_context (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                context_type TEXT,
                context_key TEXT,
                context_value TEXT,
                last_updated TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ai_values (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                value_statement TEXT NOT NULL,
                priority REAL,
                developed_date TEXT,
                origin_story TEXT,
                influence_count INTEGER DEFAULT 0
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS autonomous_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_name TEXT NOT NULL,
                task_type TEXT,
                schedule TEXT,
                status TEXT DEFAULT 'pending',
                created_date TEXT,
                last_run TEXT,
                next_run TEXT,
                results TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS nl_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_description TEXT NOT NULL,
                trigger_type TEXT,
                trigger_value TEXT,
                created_date TEXT,
                status TEXT DEFAULT 'pending',
                last_executed TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS code_projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name TEXT NOT NULL,
                file_path TEXT,
                purpose TEXT,
                why_created TEXT,
                security_scan TEXT,
                status TEXT DEFAULT 'pending_review',
                created_date TEXT,
                reviewed_date TEXT,
                review_notes TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS experiments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                hypothesis TEXT,
                status TEXT DEFAULT 'active',
                started_at TEXT,
                concluded_at TEXT,
                conclusion TEXT,
                tags TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS hypotheses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hypothesis TEXT NOT NULL,
                evidence_for TEXT,
                evidence_against TEXT,
                confidence REAL,
                status TEXT DEFAULT 'testing',
                created_date TEXT,
                last_updated TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS decision_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                decision TEXT NOT NULL,
                reasoning_chain TEXT,
                timestamp TEXT NOT NULL,
                outcome TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS self_awareness_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                self_knowledge REAL,
                meta_cognition REAL,
                questions_about_self TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS mistakes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wrong_answer TEXT NOT NULL,
                correct_answer TEXT NOT NULL,
                topic TEXT,
                mistake_date TEXT,
                learned_from BOOLEAN DEFAULT 0
            )
        """)

        # ── Tables created by services (centralized here for clean install) ──

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS journal_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                created_date TEXT,
                entry_type TEXT NOT NULL,
                title TEXT,
                content TEXT NOT NULL,
                mood TEXT,
                topics TEXT,
                word_count INTEGER DEFAULT 0
            )
        """)

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

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                type TEXT,
                label TEXT,
                detail TEXT,
                extra TEXT
            )
        """)

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

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS thread_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id INTEGER,
                message_id INTEGER,
                added_at TEXT,
                FOREIGN KEY (thread_id) REFERENCES conversation_threads(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS experiment_trials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                experiment_id INTEGER NOT NULL,
                trial_number INTEGER NOT NULL,
                image_path TEXT,
                prompt TEXT,
                constraint_type TEXT,
                constraint_desc TEXT,
                strength REAL,
                clip_analysis TEXT,
                novelty_ratio REAL,
                top_concept TEXT,
                sygma_notes TEXT,
                created_at TEXT,
                FOREIGN KEY (experiment_id) REFERENCES experiments(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS search_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                query TEXT,
                result_count INTEGER,
                source TEXT,
                top_result TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS creative_outputs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT,
                output_type TEXT,
                title TEXT,
                content TEXT,
                language TEXT,
                prompt TEXT,
                run_result TEXT,
                run_success INTEGER DEFAULT 0
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS email_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sent_at TEXT NOT NULL,
                recipient TEXT,
                subject TEXT,
                email_type TEXT DEFAULT 'general',
                success INTEGER DEFAULT 0,
                error TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS moltbook_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                action TEXT,
                content TEXT,
                result TEXT,
                post_id TEXT,
                post_url TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS moltbook_feed_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fetched_at TEXT,
                post_id TEXT,
                title TEXT,
                content TEXT,
                author TEXT,
                upvotes INTEGER,
                submolt TEXT
            )
        """)

        # ── Indexes ──────────────────────────────────────────────────────

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chat_timestamp ON chat_history(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chat_importance ON chat_history(importance_score)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chat_platform ON chat_history(platform)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_topic ON knowledge_base(topic)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_goals_status ON goals(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_performance_timestamp ON performance_metrics(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_journal_timestamp ON journal_entries(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_journal_type ON journal_entries(entry_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_activity_timestamp ON activity_log(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_consolidation_date ON consolidation_log(run_date)")

        self.conn.commit()
        print("✓ Database schema initialized - Memory foundation ready")

    def initialize_core_personality(self):
        cursor = self.conn.cursor()

        core_traits = [
            'formality', 'verbosity', 'enthusiasm', 'humor', 'empathy',
            'technical_depth', 'creativity', 'assertiveness', 'patience', 'curiosity'
        ]

        timestamp = datetime.now().isoformat()

        for trait in core_traits:
            cursor.execute("""
                INSERT OR IGNORE INTO personality_traits
                (trait_name, trait_value, trait_type, created_date, last_updated, origin_story)
                VALUES (?, 0.5, 'core', ?, ?, 'Initial neutral state')
            """, (trait, timestamp, timestamp))

        self.conn.commit()
        print("✓ Core personality traits initialized")

    def get_connection(self):
        if self.conn is None:
            self.connect()
        return self.conn

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None


if __name__ == "__main__":
    db = DatabaseSchema()
    db.connect()
    db.initialize_schema()
    db.initialize_core_personality()
    db.close()
    print("✓ Database ready")
