"""
Error Logger - Structured Error Logging to DB
Nexira v12 Bug Resilience Foundation
Created by Xeeker & Claude - February 2026

Captures errors from anywhere in the system and writes them to
the error_log table so they're visible in the UI rather than
disappearing into terminal output.

Usage:
    from services.error_logger import ErrorLogger
    err = ErrorLogger(db_connection)
    err.log('ai_engine', 'Ollama timeout', details=str(e))
    err.warn('curiosity_engine', 'No results returned for query')
    err.info('backup', 'Nightly backup completed')
"""

from datetime import datetime


class ErrorLogger:
    """
    Writes structured error records to the error_log table.
    Safe to call from any module — silently swallows its own
    failures so a logging error never crashes the system.
    """

    def __init__(self, db_connection):
        self.conn = db_connection

    # ── Public API ────────────────────────────────────────────────────────

    def log(self, source: str, message: str, details: str = None):
        """Log an error (red — something went wrong)."""
        self._write('error', source, message, details)

    def warn(self, source: str, message: str, details: str = None):
        """Log a warning (amber — something unusual but non-fatal)."""
        self._write('warning', source, message, details)

    def info(self, source: str, message: str, details: str = None):
        """Log an info event (blue — notable system event)."""
        self._write('info', source, message, details)

    def resolve(self, error_id: int):
        """Mark an error as resolved."""
        try:
            self.conn.execute(
                "UPDATE error_log SET resolved = 1 WHERE id = ?",
                (error_id,)
            )
            self.conn.commit()
        except Exception:
            pass

    def get_recent(self, limit: int = 50, include_resolved: bool = False) -> list:
        """Return recent error log entries as a list of dicts."""
        try:
            sql = """
                SELECT id, timestamp, level, source, message, details, resolved
                FROM error_log
                {where}
                ORDER BY timestamp DESC
                LIMIT ?
            """.format(where="" if include_resolved else "WHERE resolved = 0")
            rows = self.conn.execute(sql, (limit,)).fetchall()
            return [
                {
                    'id':       r[0],
                    'timestamp': r[1],
                    'level':    r[2],
                    'source':   r[3],
                    'message':  r[4],
                    'details':  r[5],
                    'resolved': bool(r[6])
                }
                for r in rows
            ]
        except Exception:
            return []

    def get_summary(self) -> dict:
        """Return counts by level for the health check."""
        try:
            row = self.conn.execute("""
                SELECT
                    SUM(CASE WHEN level='error'   AND resolved=0 THEN 1 ELSE 0 END),
                    SUM(CASE WHEN level='warning' AND resolved=0 THEN 1 ELSE 0 END),
                    SUM(CASE WHEN resolved=0 THEN 1 ELSE 0 END)
                FROM error_log
            """).fetchone()
            return {
                'errors':   row[0] or 0,
                'warnings': row[1] or 0,
                'total_unresolved': row[2] or 0
            }
        except Exception:
            return {'errors': 0, 'warnings': 0, 'total_unresolved': 0}

    # ── Internal ──────────────────────────────────────────────────────────

    def _write(self, level: str, source: str, message: str, details: str = None):
        """Write a record — silently swallows failures."""
        try:
            self.conn.execute(
                """INSERT INTO error_log (timestamp, level, source, message, details)
                   VALUES (?, ?, ?, ?, ?)""",
                (datetime.now().isoformat(), level, source, message, details)
            )
            self.conn.commit()
        except Exception:
            pass  # Never let logging crash the system
