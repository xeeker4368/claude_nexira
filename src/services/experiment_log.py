"""
Experiment Log Service
Nexira / Ultimate AI System v8.0
Created by Xeeker & Claude - February 2026

Gives Sygma a structured way to log, track, and retrieve
her creativity/constraint experiments. Each experiment records:
- The hypothesis being tested
- Images generated (with prompts and constraints)
- CLIP analysis results
- Sygma's own observations and conclusions

This is her personal research journal — separate from her
regular journal entries, focused on self-directed scientific inquiry.
"""

import json
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional


class ExperimentLog:
    """
    Persistent log for Sygma's self-directed experiments.
    Stored in the main evolution.db database.
    """

    def __init__(self, db_connection: sqlite3.Connection):
        self.db = db_connection
        self._init_tables()

    def _init_tables(self):
        cursor = self.db.cursor()

        # Migration: detect old schema (has 'experiment_name' instead of 'title')
        cursor.execute("PRAGMA table_info(experiments)")
        cols = [row[1] for row in cursor.fetchall()]
        if cols and 'title' not in cols:
            print("⚠️  Experiments: migrating table from old schema")
            cursor.execute("DROP TABLE IF EXISTS experiment_trials")
            cursor.execute("DROP TABLE IF EXISTS experiments")

        # Main experiment record
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS experiments (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                title           TEXT NOT NULL,
                hypothesis      TEXT,
                status          TEXT DEFAULT 'active',
                started_at      TEXT,
                concluded_at    TEXT,
                conclusion      TEXT,
                tags            TEXT
            )
        """)

        # Individual trials within an experiment
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS experiment_trials (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                experiment_id   INTEGER NOT NULL,
                trial_number    INTEGER NOT NULL,
                image_path      TEXT,
                prompt          TEXT,
                constraint_type TEXT,
                constraint_desc TEXT,
                strength        REAL,
                clip_analysis   TEXT,
                novelty_ratio   REAL,
                top_concept     TEXT,
                sygma_notes     TEXT,
                created_at      TEXT,
                FOREIGN KEY (experiment_id) REFERENCES experiments(id)
            )
        """)

        self.db.commit()
        print("✓ Experiment log tables ready")

    # ── Experiments ───────────────────────────────────────────────────

    def start_experiment(self, title: str, hypothesis: str,
                         tags: List[str] = None) -> int:
        """
        Start a new experiment. Returns the experiment ID.
        Sygma should call this when she begins a new line of inquiry.
        """
        cursor = self.db.cursor()
        cursor.execute("""
            INSERT INTO experiments (title, hypothesis, status, started_at, tags)
            VALUES (?, ?, 'active', ?, ?)
        """, (
            title, hypothesis,
            datetime.now().isoformat(),
            json.dumps(tags or [])
        ))
        self.db.commit()
        exp_id = cursor.lastrowid
        print(f"  🔬 Experiment #{exp_id} started: '{title}'")
        return exp_id

    def conclude_experiment(self, experiment_id: int,
                            conclusion: str) -> bool:
        """
        Mark an experiment as concluded with Sygma's findings.
        """
        cursor = self.db.cursor()
        cursor.execute("""
            UPDATE experiments
            SET status='concluded', concluded_at=?, conclusion=?
            WHERE id=?
        """, (datetime.now().isoformat(), conclusion, experiment_id))
        self.db.commit()
        print(f"  ✓ Experiment #{experiment_id} concluded")
        return cursor.rowcount > 0

    def get_experiment(self, experiment_id: int) -> Optional[Dict]:
        cursor = self.db.cursor()
        cursor.execute("SELECT * FROM experiments WHERE id=?",
                       (experiment_id,))
        row = cursor.fetchone()
        if not row:
            return None
        exp = dict(row)
        exp['tags'] = json.loads(exp.get('tags') or '[]')
        exp['trials'] = self.get_trials(experiment_id)
        return exp

    def list_experiments(self, status: str = None,
                         limit: int = 10) -> List[Dict]:
        cursor = self.db.cursor()
        if status:
            cursor.execute(
                "SELECT * FROM experiments WHERE status=? ORDER BY started_at DESC LIMIT ?",
                (status, limit)
            )
        else:
            cursor.execute(
                "SELECT * FROM experiments ORDER BY started_at DESC LIMIT ?",
                (limit,)
            )
        rows = cursor.fetchall()
        results = []
        for row in rows:
            exp = dict(row)
            exp['tags'] = json.loads(exp.get('tags') or '[]')
            # Get trial count without loading all trials
            cursor.execute(
                "SELECT COUNT(*) FROM experiment_trials WHERE experiment_id=?",
                (exp['id'],)
            )
            exp['trial_count'] = cursor.fetchone()[0]
            results.append(exp)
        return results

    # ── Trials ────────────────────────────────────────────────────────

    def log_trial(self, experiment_id: int,
                  image_path: str,
                  prompt: str,
                  constraint_type: str = "none",
                  constraint_desc: str = "",
                  strength: float = 0.0,
                  clip_analysis: Dict = None,
                  sygma_notes: str = "") -> int:
        """
        Log a single trial within an experiment.

        constraint_type: "none", "style_transfer", "negative_prompt",
                         "guidance_scale", "reduced_steps", "custom"
        strength: constraint intensity (0.0 = unconstrained, 1.0 = maximum)
        clip_analysis: dict from ImageGenService.analyze()
        """
        cursor = self.db.cursor()

        # Get next trial number for this experiment
        cursor.execute(
            "SELECT COUNT(*) FROM experiment_trials WHERE experiment_id=?",
            (experiment_id,)
        )
        trial_num = cursor.fetchone()[0] + 1

        novelty = None
        top_concept = None
        if clip_analysis and 'error' not in clip_analysis:
            novelty     = clip_analysis.get('novelty_ratio')
            top_concept = clip_analysis.get('top_concept')

        cursor.execute("""
            INSERT INTO experiment_trials
            (experiment_id, trial_number, image_path, prompt, constraint_type,
             constraint_desc, strength, clip_analysis, novelty_ratio,
             top_concept, sygma_notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            experiment_id, trial_num, image_path, prompt,
            constraint_type, constraint_desc, strength,
            json.dumps(clip_analysis or {}),
            novelty, top_concept, sygma_notes,
            datetime.now().isoformat()
        ))
        self.db.commit()

        print(f"  📊 Trial #{trial_num} logged "
              f"(constraint={constraint_type}, novelty={novelty:.3f if novelty else 'N/A'})")
        return cursor.lastrowid

    def get_trials(self, experiment_id: int) -> List[Dict]:
        cursor = self.db.cursor()
        cursor.execute("""
            SELECT * FROM experiment_trials
            WHERE experiment_id=?
            ORDER BY trial_number ASC
        """, (experiment_id,))
        rows = cursor.fetchall()
        trials = []
        for row in rows:
            t = dict(row)
            t['clip_analysis'] = json.loads(t.get('clip_analysis') or '{}')
            trials.append(t)
        return trials

    # ── Analysis helpers ──────────────────────────────────────────────

    def get_novelty_trend(self, experiment_id: int) -> Dict:
        """
        Summarise how novelty changes across trials.
        Useful for Sygma to understand the effect of constraints.
        """
        trials = self.get_trials(experiment_id)
        scored = [(t['trial_number'], t['novelty_ratio'], t['constraint_type'])
                  for t in trials if t['novelty_ratio'] is not None]

        if not scored:
            return {"message": "No scored trials yet"}

        avg_novelty    = sum(s[1] for s in scored) / len(scored)
        by_constraint  = {}
        for _, novelty, ctype in scored:
            if ctype not in by_constraint:
                by_constraint[ctype] = []
            by_constraint[ctype].append(novelty)

        avg_by_constraint = {
            k: round(sum(v) / len(v), 4)
            for k, v in by_constraint.items()
        }

        return {
            "trial_count":        len(scored),
            "average_novelty":    round(avg_novelty, 4),
            "by_constraint_type": avg_by_constraint,
            "trend":              [
                {"trial": t, "novelty": round(n, 4), "constraint": c}
                for t, n, c in scored
            ]
        }

    def get_summary(self, experiment_id: int) -> str:
        """
        Return a plain-English summary of experiment findings,
        suitable for Sygma to reference in conversation or journal.
        """
        exp    = self.get_experiment(experiment_id)
        if not exp:
            return f"Experiment #{experiment_id} not found."

        trials = exp['trials']
        trend  = self.get_novelty_trend(experiment_id)

        lines = [
            f"Experiment: {exp['title']}",
            f"Hypothesis: {exp['hypothesis']}",
            f"Status: {exp['status']}",
            f"Trials completed: {len(trials)}",
        ]

        if isinstance(trend, dict) and 'average_novelty' in trend:
            lines.append(
                f"Average novelty score: {trend['average_novelty']:.1%}"
            )
            if trend['by_constraint_type']:
                lines.append("Novelty by constraint type:")
                for ctype, avg in trend['by_constraint_type'].items():
                    lines.append(f"  {ctype}: {avg:.1%}")

        if exp.get('conclusion'):
            lines.append(f"Conclusion: {exp['conclusion']}")

        return '\n'.join(lines)
