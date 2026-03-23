# reminder_manager.py
"""
ReminderManager — SQLite-backed reminder system for Radhe.

Fixes applied vs previous version:
- Separated the status-update commit from the cleanup-DELETE commit
  so a cleanup failure never rolls back the spoken reminders.
- Added get_upcoming_reminders() return type annotation.
- Added list_reminders() convenience method for "what reminders do I have?"
- Added cancel_reminder() so the user can cancel by task keyword.

Goal-aligned improvements:
- Radhe can now answer "what reminders do I have?" by calling list_reminders()
- Radhe can cancel a reminder by keyword ("cancel meeting reminder")
"""

import sqlite3
import threading
import time
import datetime
import logging
from typing import List, Tuple, Optional, Callable

from time_parser import parse_time

logger = logging.getLogger("Radhe_Reminder")
logger.setLevel(logging.INFO)

DB_PATH = "data/reminders.db"
_lock   = threading.Lock()
_CHECK_INTERVAL = 5  # seconds between checks


class ReminderManager:

    def __init__(self, speak_function: Callable[[str], None], db_path: str = DB_PATH):
        self.db_path = db_path
        self.speak   = speak_function
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self._init_db()

    # ==================================================================
    # DB SETUP
    # ==================================================================

    def _connect(self):
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def _init_db(self):
        with _lock, self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS reminders (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    task       TEXT    NOT NULL,
                    due_time   TEXT    NOT NULL,
                    created_at TEXT    DEFAULT CURRENT_TIMESTAMP,
                    status     TEXT    DEFAULT 'pending'
                )
            """)
            conn.commit()

    # ==================================================================
    # ADD
    # ==================================================================

    def add_reminder(self, task: str, time_str: str) -> bool:
        """
        Parse time_str, save to DB.
        Returns True on success, False if time could not be parsed.
        """
        task     = (task     or "").strip()
        time_str = (time_str or "").strip()

        if not task:
            logger.warning("add_reminder: empty task.")
            return False

        dt = parse_time(time_str)
        if not dt:
            logger.error("Could not parse reminder time: '%s'", time_str)
            return False

        iso = dt.isoformat()

        with _lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO reminders (task, due_time) VALUES (?, ?)",
                (task, iso)
            )
            conn.commit()

        logger.info("Reminder set: '%s' at %s", task, iso)
        return True

    # ==================================================================
    # LIST
    # ==================================================================

    def get_upcoming_reminders(self, limit: int = 10) -> List[Tuple[int, str, str]]:
        """Return up to `limit` pending reminders as (id, task, due_time)."""
        with _lock, self._connect() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT id, task, due_time
                FROM reminders
                WHERE status = 'pending'
                ORDER BY due_time
                LIMIT ?
            """, (limit,))
            return cur.fetchall()

    def list_reminders(self) -> str:
        """
        Human-readable summary of upcoming reminders.
        Used when Radhe answers "what reminders do I have?"
        """
        rows = self.get_upcoming_reminders()
        if not rows:
            return "You have no upcoming reminders."

        lines = []
        for _, task, due_iso in rows:
            try:
                dt   = datetime.datetime.fromisoformat(due_iso)
                when = dt.strftime("%I:%M %p on %d %b")
            except Exception:
                when = due_iso
            lines.append(f"• {task} at {when}")

        return "Your upcoming reminders:\n" + "\n".join(lines)

    # ==================================================================
    # CANCEL
    # ==================================================================

    def cancel_reminder(self, keyword: str) -> str:
        """
        Cancel the first pending reminder whose task contains `keyword`.
        Returns a friendly status string.
        """
        keyword = (keyword or "").strip().lower()
        if not keyword:
            return "Please tell me which reminder to cancel."

        try:
            with _lock, self._connect() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT id, task FROM reminders WHERE status='pending'"
                )
                rows = cur.fetchall()

                for rid, task in rows:
                    if keyword in (task or "").lower():
                        cur.execute(
                            "UPDATE reminders SET status='cancelled' WHERE id=?",
                            (rid,)
                        )
                        conn.commit()
                        logger.info("Cancelled reminder id=%d: %s", rid, task)
                        return f"Cancelled reminder: {task}"

            return f"No pending reminder found matching '{keyword}'."

        except Exception as e:
            logger.exception("cancel_reminder failed: %s", e)
            return "Could not cancel reminder due to an error."

    # ==================================================================
    # BACKGROUND CHECKER
    # ==================================================================

    def _check_loop(self):
        logger.info("Reminder checker started.")

        while self.running:
            try:
                now_iso = datetime.datetime.now().isoformat()

                # ── Step 1: Find and speak due reminders ──────────────
                with _lock, self._connect() as conn:
                    cur = conn.cursor()
                    cur.execute("""
                        SELECT id, task FROM reminders
                        WHERE status = 'pending' AND due_time <= ?
                    """, (now_iso,))
                    due_rows = cur.fetchall()

                    for rid, task in due_rows:
                        try:
                            self.speak(f"Reminder: {task}")
                        except Exception:
                            logger.exception("Failed to speak reminder id=%d", rid)

                        cur.execute(
                            "UPDATE reminders SET status='completed' WHERE id=?",
                            (rid,)
                        )

                    # Commit completions immediately — separate from cleanup
                    conn.commit()

                # ── Step 2: Cleanup old completed reminders ───────────
                # Separate commit block so a cleanup failure never rolls
                # back the status updates above.
                with _lock, self._connect() as conn:
                    conn.execute("""
                        DELETE FROM reminders
                        WHERE status = 'completed'
                        AND due_time < datetime('now', '-7 days')
                    """)
                    conn.commit()

            except Exception as e:
                logger.exception("Reminder loop error: %s", e)

            time.sleep(_CHECK_INTERVAL)

    # ==================================================================
    # START / STOP
    # ==================================================================

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread  = threading.Thread(
            target=self._check_loop,
            name="ReminderChecker",
            daemon=True
        )
        self.thread.start()
        logger.info("ReminderManager started.")

    def stop(self):
        if not self.running:
            return
        self.running = False
        if self.thread:
            self.thread.join(timeout=3)
        logger.info("ReminderManager stopped.")
    
    def set(self, task: str, time_str: str) -> bool:
        return self.add_reminder(task, time_str)

    def list_all(self) -> str:
        return self.list_reminders()