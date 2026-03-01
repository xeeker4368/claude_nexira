"""
Background Task Scheduler - Phase 2 Autonomous Systems
Nexira / Nexira v12 - Phase 2
Created by Xeeker & Claude - February 2026

Runs in a daemon thread and orchestrates all Phase 2 background activity:
- 2 AM: Night consolidation
- Every chat: Curiosity detection, interest tracking, goal updates
- Idle time: Curiosity queue processing
"""

import time
import threading
from datetime import datetime
from typing import Dict, Optional, TYPE_CHECKING

from .curiosity_engine import CuriosityEngine
from .interest_tracker import InterestTracker
from .goal_tracker import GoalTracker
from .journal import JournalSystem
from .night_consolidation import NightConsolidation

# Phase 3: Email (graceful fallback if not present)
try:
    from services.email_service import EmailService
    EMAIL_AVAILABLE = True
except ImportError:
    EmailService = None
    EMAIL_AVAILABLE = False

# Phase 4 systems (graceful fallback)
try:
    from .backup_manager    import BackupManager
    from .self_awareness    import SelfAwarenessTracker
    from .threading_engine  import ThreadingEngine
    from .encryption        import EncryptionService
    PHASE4_AVAILABLE = True
except ImportError as _p4e:
    BackupManager = SelfAwarenessTracker = ThreadingEngine = EncryptionService = None
    PHASE4_AVAILABLE = False
    print(f"⚠️  Phase 4 modules not found: {_p4e}")

# Phase 5: Moltbook (graceful fallback)
try:
    from moltbook_service import MoltbookService
    MOLTBOOK_AVAILABLE = True
except ImportError as _mbe:
    MoltbookService = None
    MOLTBOOK_AVAILABLE = False


class BackgroundTaskScheduler:
    """
    Initialises and coordinates all Phase 2 autonomous systems.
    Runs as a background daemon thread.
    """

    def __init__(self, db_connection, config: Dict, ollama_model: str, base_dir: str = ""):
        self.db = db_connection
        self.config = config
        self.ollama_model = ollama_model
        self._stop_event = threading.Event()

        # Instantiate all Phase 2 systems
        self.curiosity_engine = CuriosityEngine(db_connection, config)
        self.interest_tracker = InterestTracker(db_connection, config)
        self.goal_tracker = GoalTracker(db_connection, config)
        self.journal = JournalSystem(db_connection, config, ollama_model)

        # NightConsolidation created after Moltbook so it can be passed in
        # moltbook set below after phase5 init; we patch it in after
        self.night_consolidation = NightConsolidation(
            db_connection=db_connection,
            config=config,
            ollama_model=ollama_model,
            journal=self.journal,
            curiosity_engine=self.curiosity_engine,
            goal_tracker=self.goal_tracker,
            interest_tracker=self.interest_tracker
        )

        # Phase 3: Email service
        if EMAIL_AVAILABLE:
            # Pass a getter so EmailService always reads the live config dict
            self.email_service = EmailService(lambda: config, db_connection)
            print("✓ Phase 3 email service initialised")
        else:
            self.email_service = None

        print("✓ Phase 2 background systems initialised")

        # Phase 4 systems
        if PHASE4_AVAILABLE:
            self.encryption   = EncryptionService(base_dir)
            self.backup       = BackupManager(base_dir)
            self.self_aware   = SelfAwarenessTracker(db_connection, config)
            self.threading    = ThreadingEngine(db_connection)
            # Pass encryption to journal module
            try:
                from . import journal as journal_module
                journal_module.set_encryption(self.encryption)
            except Exception:
                pass
            print("✓ Phase 4 systems initialised (backup, self-awareness, threading, encryption)")
        else:
            self.encryption = self.backup = self.self_aware = self.threading = None

        # Phase 5: Moltbook
        if MOLTBOOK_AVAILABLE:
            self.moltbook = MoltbookService(lambda: config, db_connection,
                                            encryption=self.encryption)
            print("✓ Phase 5 Moltbook service initialised")
            self.night_consolidation.moltbook = self.moltbook
        else:
            self.moltbook = None

        # Phase 6 services — injected later via inject_phase6_services()
        self.web_search  = None
        self.creative_svc = None

        # Idle activity tracking
        self._last_idle_research_hour = -1
        self._last_moltbook_read_hour = -1

    def inject_phase6_services(self, web_search, creative_svc):
        """Called after Phase 6 initialisation to wire services into background systems."""
        self.web_search   = web_search
        self.creative_svc = creative_svc
        # Also inject into night consolidation so curiosity research can use web search
        self.night_consolidation.web_search  = web_search
        self.night_consolidation.creative_svc = creative_svc
        print("✓ Phase 6 services wired into background scheduler")

    def on_chat_exchange(self, message: str, response: str,
                         ai_name: Optional[str] = None,
                         conversation_count: int = 0):
        """
        Called by AIEngine after every successful chat exchange.
        Runs all per-conversation Phase 2 updates.
        """
        try:
            # Curiosity detection — LLM-based extraction
            self.curiosity_engine.process_exchange(message, response,
                                                   ollama_model=self.ollama_model)

            # Interest tracking
            self.interest_tracker.process_exchange(message, response)

            # Goal progress
            self.goal_tracker.tick_conversation_goals(conversation_count,
                                                      ai_name=ai_name,
                                                      ollama_model=self.ollama_model)
            self.goal_tracker.update_progress('relationship', increment=0.1,
                                              ai_name=ai_name,
                                              ollama_model=self.ollama_model)

        except Exception as e:
            print(f"⚠️  Background on_chat_exchange error: {e}")

    def start(self, ai_name_getter=None):
        """
        Start the background scheduler thread.
        ai_name_getter is an optional callable that returns the current AI name.
        """
        self._ai_name_getter = ai_name_getter

        thread = threading.Thread(
            target=self._scheduler_loop,
            daemon=True,
            name="NexiraBackgroundScheduler"
        )
        thread.start()
        print("✓ Background scheduler thread started")
        return thread

    def stop(self):
        self._stop_event.set()

    def _get_ai_name(self) -> Optional[str]:
        if self._ai_name_getter and callable(self._ai_name_getter):
            return self._ai_name_getter()
        return None

    def _scheduler_loop(self):
        """Main loop - checks every 60 seconds for scheduled tasks"""
        consolidation_hour = int(
            self.config.get('intelligence', {})
            .get('night_consolidation_time', '02:00')
            .split(':')[0]
        )

        print(f"📅 Scheduler: night consolidation set for {consolidation_hour:02d}:00")

        last_minute_checked = -1

        while not self._stop_event.is_set():
            try:
                now = datetime.now()

                # Only process once per minute
                if now.minute == last_minute_checked:
                    time.sleep(10)
                    continue

                last_minute_checked = now.minute

                # 2 AM (or configured time): Night consolidation
                if now.hour == consolidation_hour and now.minute == 0:
                    ai_name = self._get_ai_name()
                    print(f"\n⏰ Scheduled: Night consolidation ({now.strftime('%H:%M')})")
                    self.night_consolidation.run(ai_name)

                # Every hour on the quarter: refresh all goal tracking
                if now.minute == 15:
                    ai_name = self._get_ai_name()
                    self.goal_tracker.tick_knowledge_goals(
                        ai_name=ai_name, ollama_model=self.ollama_model)
                    try:
                        cursor = self.db.cursor()
                        cursor.execute(
                            "SELECT COUNT(*) FROM journal_entries WHERE entry_type='philosophical'")
                        phil_count = cursor.fetchone()[0]
                        cursor.execute("SELECT COUNT(*) FROM chat_history")
                        convo_count = cursor.fetchone()[0]
                        self.goal_tracker.tick_philosophical_goals(
                            phil_count, ai_name=ai_name, ollama_model=self.ollama_model)
                        self.goal_tracker.tick_personality_goals(
                            convo_count, ai_name=ai_name, ollama_model=self.ollama_model)
                    except Exception as ge:
                        print(f"⚠️  Goal tick error: {ge}")

                # Moltbook heartbeat every 30 minutes
                if self.moltbook and now.minute in (0, 30):
                    ai_name = self._get_ai_name()
                    self.moltbook.heartbeat(ai_name or '')

                # Daily summary email at configured send time
                if self.email_service and self.email_service.daily_enabled:
                    send_time = self.config.get('daily_email', {}).get('send_time', '20:00')
                    send_hour, send_min = map(int, send_time.split(':'))
                    if now.hour == send_hour and now.minute == send_min:
                        if self.email_service.should_send_today():
                            ai_name = self._get_ai_name()
                            print(f"\n📧 Sending daily summary email...")
                            success, msg = self.email_service.send_daily_summary(ai_name)
                            print(f"   {'✓' if success else '✗'} {msg}")

                # Phase 4: nightly backup — runs once per night at consolidation hour + 5 min
                if self.backup and now.hour == consolidation_hour and now.minute == 5:
                    result = self.backup.run_backup()
                    print(f"   {'✓' if result['success'] else '✗'} Backup: {result.get('filename','?')} ({result.get('size_kb',0)} KB)")

                # ── Phase 6: Idle autonomous activity ─────────────────
                # Every 4 hours: process curiosity queue with web search
                if self.web_search and now.hour % 4 == 0 and now.minute == 30:
                    if now.hour != self._last_idle_research_hour:
                        self._last_idle_research_hour = now.hour
                        ai_name = self._get_ai_name()
                        print(f"\n🔬 Idle research cycle ({now.strftime('%H:%M')})")
                        try:
                            count = self.night_consolidation.process_curiosity_queue(ai_name)
                            if count:
                                print(f"   ✓ Researched {count} topics autonomously")
                        except Exception as e:
                            print(f"   ⚠️  Idle research error: {e}")

                # Every 6 hours: read Moltbook feed (absorb what other agents are saying)
                if self.moltbook and now.hour % 6 == 0 and now.minute == 45:
                    if now.hour != self._last_moltbook_read_hour:
                        self._last_moltbook_read_hour = now.hour
                        ai_name = self._get_ai_name()
                        print(f"\n📖 Reading Moltbook feed ({now.strftime('%H:%M')})")
                        try:
                            self._autonomous_moltbook_read(ai_name)
                        except Exception as e:
                            print(f"   ⚠️  Moltbook read error: {e}")

            except Exception as e:
                print(f"⚠️  Scheduler loop error: {e}")

            time.sleep(30)

    def _autonomous_moltbook_read(self, ai_name: Optional[str] = None):
        """
        Autonomously read the Moltbook feed and optionally respond to interesting posts.
        Called every 6 hours during idle time.
        """
        try:
            feed = self.moltbook.get_feed(limit=5)
            if not feed:
                return

            # Log the reading activity
            cursor = self.db.cursor()
            try:
                cursor.execute("""
                    INSERT INTO activity_log (timestamp, type, label, detail, extra)
                    VALUES (?, 'moltbook', 'Read Feed', ?, ?)
                """, (datetime.now().isoformat(),
                      f'{len(feed)} posts read from Moltbook feed',
                      '; '.join(
                          (p.get('author') or {}).get('name', '?')
                          for p in feed[:3]
                      )))
                self.db.commit()
            except Exception:
                pass

            print(f"   📖 Read {len(feed)} posts from Moltbook feed")

        except Exception as e:
            print(f"   ⚠️  Moltbook feed read error: {e}")

    def get_status(self) -> Dict:
        """Return current status of all Phase 2/3/6 systems"""
        status = {
            'curiosity_queue': self.curiosity_engine.get_queue_summary(),
            'top_interests': self.interest_tracker.get_top_interests(limit=5),
            'active_goals': self.goal_tracker.get_active_goals(),
            'journal_counts': self.journal.get_entry_count(),
            'email_available': self.email_service is not None,
            'email_enabled': self.email_service.is_enabled if self.email_service else False,
            'daily_summary_enabled': self.email_service.daily_enabled if self.email_service else False,
            'web_search_available': self.web_search is not None,
            'creative_svc_available': self.creative_svc is not None,
        }
        return status
