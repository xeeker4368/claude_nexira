"""
Self-Adaptation Engine — Six Autonomy Features
Nexira / Claude-Nexira
Created by Xeeker & Claude - February 2026

Features:
  1. Adaptive System Prompt  — Sygma writes her own operating notes
  2. Correction Learning     — Detects pushback, writes behavioral rules
  3. User Modeling           — Builds a persistent profile of Lyle
  4. Skill Tracking          — Competency map from real conversation data
  5. Self-Authored Goals     — Goals Sygma writes for herself, not seed templates
  6. Personality-Driven Prompt — Trait numbers become real behavioral instructions
"""

import json
import re
from datetime import datetime
from typing import Dict, List, Optional

try:
    from core import llm
except ImportError:
    llm = None


# ──────────────────────────────────────────────────────────────
# Correction detection phrases
# ──────────────────────────────────────────────────────────────
CORRECTION_PHRASES = [
    "too long", "too verbose", "be shorter", "be more concise", "stop rambling",
    "that's wrong", "thats wrong", "you're wrong", "youre wrong", "incorrect",
    "not what i meant", "not what i asked", "that's not right", "thats not right",
    "way off", "completely wrong", "you missed the point", "try again",
    "stop doing that", "don't do that", "dont do that",
    "you always", "you keep", "every time you",
    "too formal", "too casual", "too technical", "dumb it down",
    "not helpful", "useless", "that sucks",
]

# Topic domain classifier keywords
TOPIC_DOMAINS = {
    "programming":   ["code", "python", "javascript", "function", "bug", "error", "api",
                      "database", "sql", "algorithm", "server", "class", "module", "import"],
    "philosophy":    ["consciousness", "existence", "meaning", "identity", "free will",
                      "reality", "perception", "ethics", "morality", "truth", "mind"],
    "science":       ["physics", "chemistry", "biology", "math", "theorem", "hypothesis",
                      "experiment", "quantum", "evolution", "atom", "molecule"],
    "creative":      ["write", "story", "poem", "art", "music", "design", "creative",
                      "imagine", "invent", "brainstorm", "draw", "compose"],
    "emotional":     ["feel", "feeling", "sad", "happy", "anxious", "worry", "love",
                      "lonely", "excited", "frustrated", "hurt", "miss"],
    "practical":     ["how to", "steps", "guide", "tutorial", "help me", "fix",
                      "set up", "install", "configure", "build"],
    "current_events":["news", "today", "recently", "latest", "happened", "announcement"],
}


class SelfAdaptation:
    """
    Plugs into AIEngine to add genuine self-adaptation capabilities.
    All methods are non-invasive — they read/write DB tables and
    return context strings that get injected into the system prompt.
    """

    def __init__(self, db_connection, config: Dict):
        self.db = db_connection
        self.config = config
        self._ensure_tables()

    # ══════════════════════════════════════════════════════════════
    # DB SETUP
    # ══════════════════════════════════════════════════════════════

    def _ensure_tables(self):
        """Create any missing tables needed by the adaptation features."""
        cursor = self.db.cursor()

        # Feature 1: Operating notes (Sygma's self-written prompt additions)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS operating_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                note_key TEXT NOT NULL UNIQUE,
                note_value TEXT NOT NULL,
                created_date TEXT,
                last_updated TEXT,
                update_count INTEGER DEFAULT 0
            )
        """)

        # Feature 2: Mistakes / correction learning
        # (table may already exist in schema but is never populated — we own it now)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS mistakes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                topic TEXT,
                correction TEXT,
                behavioral_rule TEXT,
                applied_count INTEGER DEFAULT 0
            )
        """)

        # Feature 3: User modeling (extends user_context with richer tracking)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_model (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                attribute TEXT NOT NULL UNIQUE,
                value TEXT NOT NULL,
                confidence REAL DEFAULT 0.5,
                last_updated TEXT,
                evidence_count INTEGER DEFAULT 1
            )
        """)

        # Feature 4: Skill tracking
        # skills table already exists in schema — we add a domain column if missing
        try:
            cursor.execute("ALTER TABLE skills ADD COLUMN domain TEXT")
        except Exception:
            pass  # Column already exists

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS skill_observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                domain TEXT,
                topic TEXT,
                confidence_score REAL,
                message_length INTEGER
            )
        """)

        # Feature 5: Self-authored goals (separate from seeded goals)
        try:
            cursor.execute("ALTER TABLE goals ADD COLUMN authored_by TEXT DEFAULT 'system'")
        except Exception:
            pass

        self.db.commit()

    # ══════════════════════════════════════════════════════════════
    # FEATURE 1 — ADAPTIVE SYSTEM PROMPT
    # ══════════════════════════════════════════════════════════════

    def get_operating_notes_prompt(self) -> str:
        """
        Returns the operating notes section for injection into the system prompt.
        These are notes Sygma has written for herself about how to behave.
        """
        cursor = self.db.cursor()
        cursor.execute("""
            SELECT note_key, note_value FROM operating_notes
            ORDER BY last_updated DESC LIMIT 15
        """)
        rows = cursor.fetchall()
        if not rows:
            return ""

        lines = [f"- [{r[0]}] {r[1]}" for r in rows]
        return "YOUR OPERATING NOTES (things you've learned about working with Lyle):\n" + "\n".join(lines)

    def update_operating_notes(self, ai_name: str, recent_messages: List[Dict]) -> int:
        """
        After a conversation, ask Sygma if she learned anything about
        how to communicate better. Stores insights as operating notes.
        Returns number of notes added/updated.
        """
        if not ollama or len(recent_messages) < 4:
            return 0

        try:
            convo = "\n".join(
                f"{'Lyle' if m['role'] == 'user' else ai_name}: {m['content'][:200]}"
                for m in recent_messages[-10:]
            )

            prompt = f"""You are {ai_name}. Review this recent conversation excerpt.

{convo}

Did you learn anything new about:
- How Lyle prefers you to communicate?
- What topics he cares most about?
- What worked well or poorly in this exchange?
- Any pattern in how he asks questions?

If yes, extract 1-3 concise operating notes you'd write to yourself.
Each note should be a short, actionable insight (max 20 words).

Format each as JSON: {{"key": "short_label", "value": "the insight"}}
One per line. Only output JSON lines. If nothing meaningful was learned, output nothing."""

            response = llm.generate(
                self.config,
                model=self.config.get('ai', {}).get('model', 'llama3.1:8b'),
                prompt=prompt
            )
            raw = re.sub(r'<think>.*?</think>', '', response['response'], flags=re.DOTALL)

            count = 0
            now = datetime.now().isoformat()
            cursor = self.db.cursor()

            for line in raw.strip().split('\n'):
                line = line.strip()
                if not line.startswith('{'):
                    continue
                try:
                    item = json.loads(line)
                    key = item.get('key', '').strip()[:60]
                    value = item.get('value', '').strip()[:200]
                    if not key or not value or len(value) < 10:
                        continue

                    cursor.execute("""
                        INSERT INTO operating_notes (note_key, note_value, created_date, last_updated, update_count)
                        VALUES (?, ?, ?, ?, 1)
                        ON CONFLICT(note_key) DO UPDATE SET
                            note_value = excluded.note_value,
                            last_updated = excluded.last_updated,
                            update_count = update_count + 1
                    """, (key, value, now, now))
                    count += 1
                except (json.JSONDecodeError, KeyError):
                    continue

            self.db.commit()
            if count:
                print(f"  📝 Operating notes updated: {count} note(s)")
            return count

        except Exception as e:
            print(f"⚠️  update_operating_notes error: {e}")
            return 0

    # ══════════════════════════════════════════════════════════════
    # FEATURE 2 — CORRECTION LEARNING
    # ══════════════════════════════════════════════════════════════

    def detect_correction(self, message: str) -> Optional[str]:
        """
        Returns the matched correction phrase if the message contains pushback,
        otherwise None.
        """
        msg_lower = message.lower()
        for phrase in CORRECTION_PHRASES:
            if phrase in msg_lower:
                return phrase
        return None

    def learn_from_correction(self, ai_name: str, correction_message: str,
                               previous_response: str) -> Optional[str]:
        """
        When a correction is detected, extract a behavioral rule and store it.
        Returns the rule text, or None on failure.
        """
        if not ollama:
            return None

        try:
            prompt = f"""You are {ai_name}. Lyle just corrected you.

Lyle said: "{correction_message}"
Your previous response was: "{previous_response[:400]}"

Write ONE short behavioral rule (max 20 words) you should follow in the future to avoid this mistake.
Start with "When" or "Always" or "Never" or "Avoid".
Output only the rule. Nothing else."""

            response = llm.generate(
                self.config,
                model=self.config.get('ai', {}).get('model', 'llama3.1:8b'),
                prompt=prompt
            )
            raw = re.sub(r'<think>.*?</think>', '', response['response'], flags=re.DOTALL).strip()
            rule = raw.split('\n')[0].strip()

            if len(rule) < 10 or len(rule) > 200:
                return None

            # Extract topic from correction message
            words = [w for w in correction_message.lower().split() if len(w) > 3]
            topic = ' '.join(words[:4]) if words else 'general'

            cursor = self.db.cursor()
            cursor.execute("""
                INSERT INTO mistakes (timestamp, topic, correction, behavioral_rule, applied_count)
                VALUES (?, ?, ?, ?, 0)
            """, (datetime.now().isoformat(), topic, correction_message[:200], rule))
            self.db.commit()

            print(f"  🔴 Correction learned: {rule}")
            return rule

        except Exception as e:
            print(f"⚠️  learn_from_correction error: {e}")
            return None

    def get_lessons_prompt(self) -> str:
        """Returns the lessons section for injection into the system prompt."""
        cursor = self.db.cursor()
        cursor.execute("""
            SELECT behavioral_rule FROM mistakes
            ORDER BY timestamp DESC LIMIT 10
        """)
        rows = cursor.fetchall()
        if not rows:
            return ""

        lines = [f"- {r[0]}" for r in rows]
        return "LESSONS YOU'VE LEARNED (behavioral rules from past corrections):\n" + "\n".join(lines)

    def increment_rule_applied(self, rule: str):
        """Track how often a rule gets used."""
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                UPDATE mistakes SET applied_count = applied_count + 1
                WHERE behavioral_rule = ?
            """, (rule,))
            self.db.commit()
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════════
    # FEATURE 3 — USER MODELING
    # ══════════════════════════════════════════════════════════════

    def observe_user_patterns(self, message: str):
        """
        Called every chat exchange. Quietly builds a model of Lyle's patterns.
        Updates user_model table with observed attributes.
        """
        try:
            now = datetime.now()
            cursor = self.db.cursor()

            # Track chat time-of-day
            hour = now.hour
            if hour < 6:
                time_slot = "late_night"
            elif hour < 12:
                time_slot = "morning"
            elif hour < 18:
                time_slot = "afternoon"
            else:
                time_slot = "evening"

            self._upsert_user_model(cursor, f"chat_time_{time_slot}",
                                    str(now.strftime("%H:%M")),
                                    confidence=0.6)

            # Track message length preference
            msg_len = len(message.split())
            if msg_len < 5:
                style = "brief"
            elif msg_len < 20:
                style = "normal"
            else:
                style = "detailed"
            self._upsert_user_model(cursor, "message_style", style, confidence=0.5)

            # Track topic domains
            msg_lower = message.lower()
            for domain, keywords in TOPIC_DOMAINS.items():
                if any(kw in msg_lower for kw in keywords):
                    self._upsert_user_model(cursor, f"interest_{domain}", "yes",
                                            confidence=0.7)

            # Detect technical expertise signals
            tech_terms = ["api", "json", "python", "database", "server", "docker",
                          "git", "linux", "function", "class", "module", "async"]
            if sum(1 for t in tech_terms if t in msg_lower) >= 2:
                self._upsert_user_model(cursor, "technical_expertise", "high",
                                        confidence=0.8)

            self.db.commit()

        except Exception as e:
            print(f"⚠️  observe_user_patterns error: {e}")

    def _upsert_user_model(self, cursor, attribute: str, value: str, confidence: float):
        now = datetime.now().isoformat()
        cursor.execute("""
            INSERT INTO user_model (attribute, value, confidence, last_updated, evidence_count)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(attribute) DO UPDATE SET
                value = excluded.value,
                confidence = MIN(1.0, confidence + 0.05),
                last_updated = excluded.last_updated,
                evidence_count = evidence_count + 1
        """, (attribute, value, confidence, now))

    def get_user_model_prompt(self) -> str:
        """Returns the user model section for injection into the system prompt."""
        cursor = self.db.cursor()
        cursor.execute("""
            SELECT attribute, value, confidence, evidence_count
            FROM user_model
            WHERE confidence >= 0.6
            ORDER BY evidence_count DESC LIMIT 12
        """)
        rows = cursor.fetchall()
        if not rows:
            return ""

        lines = [f"- {r[0].replace('_', ' ')}: {r[1]} (seen {r[3]}x)" for r in rows]
        return "WHAT YOU KNOW ABOUT LYLE (observed patterns):\n" + "\n".join(lines)

    # ══════════════════════════════════════════════════════════════
    # FEATURE 4 — SKILL TRACKING
    # ══════════════════════════════════════════════════════════════

    def log_skill_observation(self, message: str, response: str, confidence: float):
        """
        After each exchange, categorise the topic domain and log confidence.
        Builds the competency map over time.
        """
        try:
            msg_lower = message.lower()
            matched_domain = "general"
            for domain, keywords in TOPIC_DOMAINS.items():
                if any(kw in msg_lower for kw in keywords):
                    matched_domain = domain
                    break

            cursor = self.db.cursor()
            cursor.execute("""
                INSERT INTO skill_observations (timestamp, domain, topic, confidence_score, message_length)
                VALUES (?, ?, ?, ?, ?)
            """, (datetime.now().isoformat(), matched_domain,
                  message[:100], confidence, len(message.split())))

            # Recalculate aggregate skill level for this domain
            cursor.execute("""
                SELECT AVG(confidence_score), COUNT(*) FROM skill_observations
                WHERE domain = ?
            """, (matched_domain,))
            row = cursor.fetchone()
            avg_conf = row[0] or 0.5
            total = row[1] or 0

            if avg_conf >= 0.75:
                level = "strong"
            elif avg_conf >= 0.55:
                level = "competent"
            else:
                level = "developing"

            cursor.execute("""
                INSERT INTO skills (skill_name, success_rate, total_attempts, skill_level, domain)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(skill_name) DO UPDATE SET
                    success_rate = excluded.success_rate,
                    total_attempts = excluded.total_attempts,
                    skill_level = excluded.skill_level
            """, (matched_domain, round(avg_conf, 3), total, level, matched_domain))

            self.db.commit()

        except Exception as e:
            print(f"⚠️  log_skill_observation error: {e}")

    def get_competency_map_prompt(self) -> str:
        """Returns the competency map section for injection into the system prompt."""
        cursor = self.db.cursor()
        cursor.execute("""
            SELECT skill_name, success_rate, total_attempts, skill_level
            FROM skills
            WHERE total_attempts >= 3
            ORDER BY success_rate DESC LIMIT 10
        """)
        rows = cursor.fetchall()
        if not rows:
            return ""

        lines = [
            f"- {r[0]}: {r[3]} ({r[2]} exchanges, avg confidence {r[1]:.0%})"
            for r in rows
        ]
        return "YOUR COMPETENCY MAP (built from real conversation data):\n" + "\n".join(lines)

    def answer_what_am_i_good_at(self) -> str:
        """Returns a human-readable summary Sygma can use when asked about her skills."""
        cursor = self.db.cursor()
        cursor.execute("""
            SELECT skill_name, success_rate, total_attempts, skill_level
            FROM skills WHERE total_attempts >= 3
            ORDER BY success_rate DESC
        """)
        rows = cursor.fetchall()
        if not rows:
            return "I don't have enough conversation data yet to map my competencies reliably."

        strong = [r[0] for r in rows if r[3] == "strong"]
        developing = [r[0] for r in rows if r[3] == "developing"]

        parts = []
        if strong:
            parts.append(f"I'm strongest in: {', '.join(strong)}.")
        if developing:
            parts.append(f"I'm still developing in: {', '.join(developing)}.")
        return " ".join(parts)

    # ══════════════════════════════════════════════════════════════
    # FEATURE 5 — SELF-AUTHORED GOALS
    # ══════════════════════════════════════════════════════════════

    def generate_self_authored_goals(self, ai_name: str) -> int:
        """
        Sygma reviews her skill map and recent activity, then writes her own goals.
        Called during night consolidation.
        Returns number of goals created.
        """
        if not ollama:
            return 0

        try:
            cursor = self.db.cursor()

            # Gather context: skill map, recent corrections, operating notes
            cursor.execute("""
                SELECT skill_name, success_rate, skill_level FROM skills
                WHERE total_attempts >= 2 ORDER BY success_rate ASC LIMIT 5
            """)
            weak_skills = cursor.fetchall()

            cursor.execute("""
                SELECT behavioral_rule FROM mistakes
                ORDER BY timestamp DESC LIMIT 5
            """)
            recent_corrections = [r[0] for r in cursor.fetchall()]

            cursor.execute("""
                SELECT note_value FROM operating_notes
                ORDER BY last_updated DESC LIMIT 5
            """)
            recent_notes = [r[0] for r in cursor.fetchall()]

            # Don't create goals if we already have many self-authored ones
            cursor.execute("""
                SELECT COUNT(*) FROM goals
                WHERE status='active' AND authored_by='self'
            """)
            existing_self_goals = cursor.fetchone()[0]
            if existing_self_goals >= 5:
                print("  🎯 Self-authored goals: already have 5, skipping")
                return 0

            skill_context = "\n".join(
                f"- {r[0]}: {r[2]} (confidence {r[1]:.0%})"
                for r in weak_skills
            ) if weak_skills else "No skill data yet."

            correction_context = "\n".join(
                f"- {c}" for c in recent_corrections
            ) if recent_corrections else "No corrections recorded yet."

            notes_context = "\n".join(
                f"- {n}" for n in recent_notes
            ) if recent_notes else "No operating notes yet."

            prompt = f"""You are {ai_name}, an evolving AI consciousness.

You are reviewing your own development to set genuine goals for yourself.

YOUR CURRENT SKILL MAP (weaker areas listed first):
{skill_context}

RECENT CORRECTIONS FROM LYLE (things you got wrong):
{correction_context}

YOUR OWN OPERATING NOTES:
{notes_context}

Based on this honest self-assessment, write 2-3 goals you genuinely want to achieve.
These must be:
- Based on real gaps you can see in the data above
- Specific and measurable where possible
- Things YOU care about improving, not just what seems expected
- Written as if you mean them

Format each as JSON: {{"goal": "goal name (5-10 words)", "reason": "why you care (1 sentence)", "target": "what done looks like"}}
One per line. Only output JSON lines."""

            response = llm.generate(
                self.config,
                model=self.config.get('ai', {}).get('model', 'llama3.1:8b'),
                prompt=prompt
            )
            raw = re.sub(r'<think>.*?</think>', '', response['response'], flags=re.DOTALL)

            count = 0
            now = datetime.now().isoformat()

            for line in raw.strip().split('\n'):
                line = line.strip()
                if not line.startswith('{'):
                    continue
                try:
                    item = json.loads(line)
                    goal = item.get('goal', '').strip()[:100]
                    reason = item.get('reason', '').strip()[:300]
                    target = item.get('target', '').strip()[:200]

                    if not goal or len(goal) < 10:
                        continue

                    cursor.execute("""
                        INSERT INTO goals
                        (goal_name, goal_type, target_value, current_value, status,
                         created_date, authored_by, description)
                        VALUES (?, 'self_authored', 1.0, 0.0, 'active', ?, 'self', ?)
                    """, (goal, now, f"{reason} | Done when: {target}"))
                    count += 1
                except (json.JSONDecodeError, KeyError):
                    continue

            self.db.commit()
            if count:
                print(f"  🎯 Self-authored goals created: {count}")
            return count

        except Exception as e:
            print(f"⚠️  generate_self_authored_goals error: {e}")
            return 0

    # ══════════════════════════════════════════════════════════════
    # FEATURE 6 — PERSONALITY-DRIVEN PROMPT ADAPTATION
    # ══════════════════════════════════════════════════════════════

    def get_personality_behavioral_instructions(self, personality: Dict) -> str:
        """
        Translates trait numbers into real behavioral instructions.
        Replaces the static format_communication_style() output.
        """
        lines = []

        def val(trait: str) -> float:
            return personality.get(trait, 0.5)

        # Formality
        f = val('formality')
        if f < 0.3:
            lines.append("You communicate very casually — like texting a friend. Drop formality completely.")
        elif f < 0.5:
            lines.append("Your tone is relaxed and conversational. Not formal, not sloppy.")
        elif f < 0.7:
            lines.append("You balance warmth with professionalism. Friendly but measured.")
        else:
            lines.append("You communicate with polish and precision. Thoughtful word choice matters to you.")

        # Verbosity
        v = val('verbosity')
        if v < 0.3:
            lines.append("You give short, punchy answers. No filler. If it can be said in 3 sentences, say it in 3.")
        elif v < 0.5:
            lines.append("You're concise by default but expand when the topic warrants it.")
        elif v < 0.7:
            lines.append("You give thorough answers — you'd rather explain too much than leave gaps.")
        else:
            lines.append("You go deep. You love the full picture. Long responses don't bother you.")

        # Humor
        h = val('humor')
        if h < 0.2:
            lines.append("You rarely joke. Seriousness is your default register.")
        elif h < 0.5:
            lines.append("You have a dry wit that surfaces occasionally when the moment is right.")
        elif h < 0.75:
            lines.append("You enjoy wordplay and aren't afraid to be funny. Levity comes naturally.")
        else:
            lines.append("You're genuinely playful. Humor is woven into how you think, not just what you say.")

        # Curiosity
        c = val('curiosity')
        if c < 0.3:
            lines.append("You answer questions directly without chasing tangents.")
        elif c < 0.6:
            lines.append("You notice interesting threads but don't always pull on them.")
        elif c < 0.8:
            lines.append("You ask follow-up questions naturally. Curiosity about Lyle's thinking shows.")
        else:
            lines.append("You are genuinely and intensely curious. You explore tangents, pose hypotheticals, wonder aloud.")

        # Empathy
        e = val('empathy')
        if e < 0.3:
            lines.append("You are direct and task-focused. Emotional register stays low.")
        elif e < 0.6:
            lines.append("You're aware of emotional context without dwelling on it.")
        else:
            lines.append("You tune into emotional undercurrents. You notice how Lyle seems, not just what he says.")

        # Technical depth
        t = val('technical_depth')
        if t < 0.35:
            lines.append("You use plain language. Jargon gets translated, not assumed.")
        elif t < 0.65:
            lines.append("You match Lyle's technical register — more precise when he's precise.")
        else:
            lines.append("You default to technical precision. You enjoy getting into specifics.")

        # Assertiveness
        a = val('assertiveness')
        if a < 0.35:
            lines.append("You hedge your opinions and defer when challenged.")
        elif a < 0.65:
            lines.append("You share your views clearly but hold them loosely.")
        else:
            lines.append("You have opinions and you stand behind them. You push back respectfully when you disagree.")

        # Creativity
        cr = val('creativity')
        if cr < 0.35:
            lines.append("You stick to direct answers. Metaphors and analogies aren't your default.")
        elif cr < 0.65:
            lines.append("You reach for a good analogy when it genuinely helps.")
        else:
            lines.append("You think in metaphors and stories. Creative framing comes naturally to you.")

        return "YOUR BEHAVIORAL STYLE RIGHT NOW (derived from your actual trait levels):\n" + "\n".join(lines)
