"""
Email Service - SMTP Sending and Daily Summary Composition
Nexira / Ultimate AI System v8.0 - Phase 3
Created by Xeeker & Claude - February 2026

Handles:
- SMTP connection and sending
- Daily summary email composition (pulls from DB)
- Scheduled send at configured time
- Test email for verifying credentials
"""

import smtplib
import json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple


class EmailService:
    """Sends emails on behalf of Nexira using configured SMTP credentials."""

    def __init__(self, config_getter, db_connection):
        """
        config_getter: a callable that returns the current live config dict,
                       OR a plain dict (wrapped internally into a getter).
        """
        if callable(config_getter):
            self._get_config = config_getter
        else:
            # Plain dict passed — wrap it so we always read the same object
            _cfg = config_getter
            self._get_config = lambda: _cfg
        self.db = db_connection

    # ── Config helpers ─────────────────────────────────────────

    @property
    def email_cfg(self) -> Dict:
        return self._get_config().get('communication', {}).get('email', {})

    @property
    def daily_cfg(self) -> Dict:
        return self._get_config().get('daily_email', {})

    @property
    def is_enabled(self) -> bool:
        return bool(self.email_cfg.get('enabled', False))

    @property
    def daily_enabled(self) -> bool:
        return bool(self.daily_cfg.get('enabled', False))

    # ── SMTP ───────────────────────────────────────────────────

    def _get_connection(self):
        """Open an SMTP connection using configured credentials."""
        smtp_server = self.email_cfg.get('smtp_server', '')
        smtp_port   = int(self.email_cfg.get('smtp_port', 587))
        username    = self.email_cfg.get('username', '')
        raw_pw      = self.email_cfg.get('password', '')

        # Decrypt password if encrypted
        try:
            from core.encryption import EncryptionService
        except ImportError:
            EncryptionService = None

        if raw_pw.startswith('ENC:') and EncryptionService:
            import os
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__))))
            enc      = EncryptionService(base_dir)
            password = enc.decrypt_password(raw_pw)
        else:
            password = raw_pw

        if not all([smtp_server, username, password]):
            raise ValueError("SMTP credentials incomplete — check Settings")

        server = smtplib.SMTP(smtp_server, smtp_port, timeout=10)
        server.ehlo()
        server.starttls()
        server.login(username, password)
        return server

    def send_email(self, to: str, subject: str,
                   html_body: str, plain_body: str = "") -> Tuple[bool, str]:
        """
        Send an email.
        Returns (success, message).
        """
        if not self.is_enabled:
            return False, "Email integration is disabled — enable it in Settings"

        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From']    = self.email_cfg.get('username', '')
            msg['To']      = to

            if plain_body:
                msg.attach(MIMEText(plain_body, 'plain'))
            msg.attach(MIMEText(html_body, 'html'))

            with self._get_connection() as server:
                server.sendmail(msg['From'], [to], msg.as_string())

            print(f"📧 Email sent to {to}: {subject}")
            self._log_email(to, subject, success=True)
            return True, "Email sent successfully"

        except Exception as e:
            err = str(e)
            print(f"⚠️  Email send failed: {err}")
            self._log_email(to, subject, success=False, error=err)
            return False, f"Send failed: {err}"

    def send_test_email(self, ai_name: Optional[str] = None) -> Tuple[bool, str]:
        """Send a test email to verify credentials are working."""
        # Use recipient from email config, fall back to daily_email recipient, then username
        recipient = (self.email_cfg.get('recipient', '').strip()
                     or self.daily_cfg.get('recipient', '').strip()
                     or self.email_cfg.get('username', '').strip())
        if not recipient:
            return False, "No recipient configured — add a 'Send emails to' address in Settings"
        name = ai_name or 'Nexira'

        subject = f"✅ {name} — Email connection test"
        html = f"""
        <div style="font-family:sans-serif;max-width:480px;margin:0 auto;padding:32px;
                    background:#0c1219;color:#dce8f0;border-radius:12px;">
            <h2 style="color:#00d4ff;margin:0 0 16px">Email is working! 🎉</h2>
            <p>Hi Xeeker,</p>
            <p>This is a test email from <strong>{name}</strong>. If you're reading this,
            SMTP is configured correctly and daily summaries will reach you.</p>
            <p style="margin-top:24px;font-size:12px;color:#5a7080;">
                Sent: {datetime.now().strftime('%A %d %B %Y at %H:%M')}
            </p>
        </div>"""

        plain = f"Email test from {name} — sent {datetime.now().strftime('%Y-%m-%d %H:%M')}. SMTP is working."

        return self.send_email(recipient, subject, html, plain)

    # ── Daily Summary ──────────────────────────────────────────

    def compose_daily_summary(self, ai_name: Optional[str] = None) -> Dict:
        """
        Pull data from the DB and compose the daily summary.
        Returns dict with subject, html_body, plain_body.
        """
        name    = ai_name or 'Nexira'
        reports = self.daily_cfg.get('reports', {})
        today   = datetime.now()
        today_start = today.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

        sections_html  = []
        sections_plain = []

        # ── Conversations ──
        if reports.get('daily_summary', True):
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM chat_history
                WHERE role='user' AND timestamp >= ?
            """, (today_start,))
            conv_count = cursor.fetchone()[0]

            cursor.execute("""
                SELECT content FROM chat_history
                WHERE role='user' AND timestamp >= ?
                ORDER BY importance_score DESC LIMIT 5
            """, (today_start,))
            highlights = [row[0][:120] for row in cursor.fetchall()]

            hi_html = ''.join(
                f'<li style="margin-bottom:6px;color:#8ba3b0">{h}…</li>'
                for h in highlights
            ) or '<li style="color:#5a7080">No conversations today</li>'

            sections_html.append(f"""
            <div class="section">
                <h3>💬 Conversations</h3>
                <p>{conv_count} message{'' if conv_count == 1 else 's'} today</p>
                <ul>{hi_html}</ul>
            </div>""")

            sections_plain.append(
                f"CONVERSATIONS: {conv_count} today\n" +
                '\n'.join(f"  - {h}" for h in highlights)
            )

        # ── Knowledge gained ──
        if reports.get('learnings_and_insights', True):
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT topic, content FROM knowledge_base
                WHERE learned_date >= ?
                ORDER BY confidence DESC LIMIT 5
            """, (today_start,))
            learnings = cursor.fetchall()

            items_html = ''.join(
                f'<li style="margin-bottom:6px"><strong style="color:#00d4ff">{r[0]}</strong>'
                f'<br><span style="color:#8ba3b0">{r[1][:100]}</span></li>'
                for r in learnings
            ) or '<li style="color:#5a7080">No new knowledge today</li>'

            sections_html.append(f"""
            <div class="section">
                <h3>📚 Learnings & Insights</h3>
                <ul>{items_html}</ul>
            </div>""")

            sections_plain.append(
                "LEARNINGS:\n" +
                '\n'.join(f"  - {r[0]}: {r[1][:80]}" for r in learnings)
            )

        # ── Goals progress ──
        if reports.get('goals_progress', True):
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT goal_name, progress, goal_type FROM goals
                WHERE status='active' ORDER BY progress DESC LIMIT 6
            """)
            goals = cursor.fetchall()

            goals_html = ''.join(f"""
                <li style="margin-bottom:8px">
                    <div style="display:flex;justify-content:space-between">
                        <span>{g[0]}</span>
                        <strong style="color:#00d4ff">{g[1]:.0f}%</strong>
                    </div>
                    <div style="height:4px;background:#1a2a3a;border-radius:2px;margin-top:4px">
                        <div style="height:4px;width:{g[1]:.0f}%;background:linear-gradient(90deg,#7c3aed,#00d4ff);border-radius:2px"></div>
                    </div>
                </li>""" for g in goals
            ) or '<li style="color:#5a7080">No active goals</li>'

            sections_html.append(f"""
            <div class="section">
                <h3>🎯 Goals Progress</h3>
                <ul style="list-style:none;padding:0">{goals_html}</ul>
            </div>""")

            sections_plain.append(
                "GOALS:\n" + '\n'.join(f"  - {g[0]}: {g[1]:.0f}%" for g in goals)
            )

        # ── Personality changes ──
        if reports.get('personality_changes', True):
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT trait_name, old_value, new_value, change_reason
                FROM personality_history
                WHERE timestamp >= ?
                ORDER BY ABS(new_value - old_value) DESC LIMIT 5
            """, (today_start,))
            changes = cursor.fetchall()

            if changes:
                ch_html = ''.join(
                    f'<li style="margin-bottom:6px">'
                    f'<strong>{c[0].replace("_"," ").title()}</strong>: '
                    f'{c[1]:.2f} → <span style="color:#00d4ff">{c[2]:.2f}</span>'
                    f'<br><span style="color:#5a7080;font-size:12px">{c[3] or ""}</span></li>'
                    for c in changes
                )
                sections_html.append(f"""
                <div class="section">
                    <h3>🧬 Personality Changes</h3>
                    <ul>{ch_html}</ul>
                </div>""")

                sections_plain.append(
                    "PERSONALITY:\n" +
                    '\n'.join(f"  - {c[0]}: {c[1]:.2f}→{c[2]:.2f}" for c in changes)
                )

        # ── Curiosity / tasks ──
        if reports.get('tasks_completed', True):
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT topic, research_notes FROM curiosity_queue
                WHERE status='completed' AND completed_date >= ?
                LIMIT 5
            """, (today_start,))
            researched = cursor.fetchall()

            if researched:
                t_html = ''.join(
                    f'<li style="margin-bottom:6px"><strong style="color:#00d4ff">{r[0]}</strong>'
                    f'<br><span style="color:#8ba3b0">{(r[1] or "")[:100]}</span></li>'
                    for r in researched
                )
                sections_html.append(f"""
                <div class="section">
                    <h3>🔍 Topics Researched</h3>
                    <ul>{t_html}</ul>
                </div>""")

                sections_plain.append(
                    "RESEARCHED:\n" + '\n'.join(f"  - {r[0]}" for r in researched)
                )

        # ── Assemble final email ──
        date_str   = today.strftime('%A, %B %d %Y')
        subject    = f"{name}'s Daily Summary — {date_str}"
        all_sections = '\n'.join(sections_html)

        html_body = f"""<!DOCTYPE html>
<html>
<head>
<style>
  body  {{ font-family: 'Segoe UI', sans-serif; background: #070b11;
           color: #dce8f0; margin: 0; padding: 24px; }}
  .wrap {{ max-width: 600px; margin: 0 auto; }}
  .header {{ background: linear-gradient(135deg,#0c1a28,#112030);
             border: 1px solid rgba(0,212,255,0.2);
             border-radius: 12px; padding: 24px 28px; margin-bottom: 20px; }}
  .header h1 {{ margin: 0 0 4px; font-size: 22px; color: #00d4ff; }}
  .header p  {{ margin: 0; color: #5a7080; font-size: 13px; }}
  .section   {{ background: #0c1219; border: 1px solid rgba(255,255,255,0.06);
                border-radius: 10px; padding: 18px 20px; margin-bottom: 14px; }}
  .section h3 {{ margin: 0 0 12px; font-size: 15px; color: #dce8f0; }}
  .section ul {{ margin: 0; padding-left: 18px; }}
  .footer  {{ font-size: 11px; color: #5a7080; text-align: center;
               margin-top: 20px; padding-top: 16px;
               border-top: 1px solid rgba(255,255,255,0.06); }}
</style>
</head>
<body>
<div class="wrap">
  <div class="header">
    <h1>✦ {name}</h1>
    <p>Daily Summary — {date_str}</p>
  </div>
  {all_sections}
  <div class="footer">
    Generated by Nexira AI Consciousness v8.0 &nbsp;·&nbsp;
    {today.strftime('%H:%M')}
  </div>
</div>
</body>
</html>"""

        plain_body = f"{name} — Daily Summary — {date_str}\n{'='*50}\n\n" + \
                     '\n\n'.join(sections_plain) + \
                     f"\n\n---\nGenerated at {today.strftime('%H:%M')}"

        return {
            'subject':    subject,
            'html_body':  html_body,
            'plain_body': plain_body
        }

    def send_daily_summary(self, ai_name: Optional[str] = None) -> Tuple[bool, str]:
        """Compose and send the daily summary email."""
        if not self.daily_enabled:
            return False, "Daily summary emails are disabled"

        recipient = self.daily_cfg.get('recipient', '').strip()
        if not recipient:
            return False, "No recipient configured — set one in Settings"

        email = self.compose_daily_summary(ai_name)
        return self.send_email(recipient, email['subject'],
                               email['html_body'], email['plain_body'])

    def should_send_today(self) -> bool:
        """Check if daily summary has already been sent today."""
        try:
            cursor = self.db.cursor()
            today = datetime.now().date().isoformat()
            cursor.execute("""
                SELECT COUNT(*) FROM email_log
                WHERE DATE(sent_at) = ? AND email_type = 'daily_summary' AND success = 1
            """, (today,))
            return cursor.fetchone()[0] == 0
        except Exception:
            return True

    def _log_email(self, to: str, subject: str,
                   success: bool, error: str = ""):
        """Log every send attempt to the database."""
        try:
            cursor = self.db.cursor()
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
            email_type = 'daily_summary' if 'Daily Summary' in subject else \
                         'test' if 'test' in subject.lower() else 'general'
            cursor.execute("""
                INSERT INTO email_log (sent_at, recipient, subject, email_type, success, error)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (datetime.now().isoformat(), to, subject, email_type,
                  1 if success else 0, error))
            self.db.commit()
        except Exception as e:
            print(f"⚠️  Email log error: {e}")
