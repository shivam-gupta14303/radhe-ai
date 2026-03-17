"""
ReminderManager

Central reminder system for Radhe.

Features:
- Stores reminders in SQLite
- Uses time_parser.parse_time
- Background thread checks reminders
- Speaks reminders using injected speak function
"""

import sqlite3
import threading
import time
import datetime
import logging
from time_parser import parse_time


logger = logging.getLogger("Radhe_Reminder")
logger.setLevel(logging.INFO)

DB_PATH = "data/reminders.db"
_lock = threading.Lock()


class ReminderManager:

    def __init__(self, speak_function, db_path: str = DB_PATH):

        self.db_path = db_path
        self.speak = speak_function
        self.running = False
        self.thread = None

        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def _init_db(self):

        with _lock, self._connect() as conn:

            cur = conn.cursor()

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task TEXT NOT NULL,
                    due_time TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'pending'
                )
                """
            )

            conn.commit()

    def add_reminder(self, task: str, time_str: str) -> bool:

        dt = parse_time(time_str)

        if not dt:
            logger.error("Could not parse time: %s", time_str)
            return False

        iso = dt.isoformat()

        with _lock, self._connect() as conn:

            cur = conn.cursor()

            cur.execute(
                "INSERT INTO reminders (task, due_time) VALUES (?, ?)",
                (task, iso),
            )

            conn.commit()

        logger.info("Reminder set: %s at %s", task, iso)

        return True

    def get_upcoming_reminders(self, limit=10):

        with _lock, self._connect() as conn:

            cur = conn.cursor()

            cur.execute(
                """
                SELECT id, task, due_time
                FROM reminders
                WHERE status='pending'
                ORDER BY due_time
                LIMIT ?
                """,
                (limit,),
            )

            return cur.fetchall()

    def _check_loop(self):

        logger.info("Reminder checker started")

        while self.running:

            try:

                now_iso = datetime.datetime.now().isoformat()

                with _lock, self._connect() as conn:

                    cur = conn.cursor()

                    cur.execute(
                        """
                        SELECT id, task
                        FROM reminders
                        WHERE status='pending' AND due_time <= ?
                        """,
                        (now_iso,),
                    )

                    rows = cur.fetchall()

                    for rid, task in rows:

                        try:
                            self.speak(f"Reminder: {task}")
                        except Exception:
                            logger.exception("Failed to speak reminder")

                        cur.execute(
                            "UPDATE reminders SET status='completed' WHERE id=?",
                            (rid,),
                        )
                    # cleanup old reminders
                    cur.execute(
                        """
                        DELETE FROM reminders
                        WHERE status='completed'
                        AND due_time < datetime('now','-7 days')
                        """
                    )

                    conn.commit()

            except Exception as e:
                logger.exception("Reminder loop error: %s", e)

            time.sleep(5)

    def start(self):

        if self.running:
            return

        self.running = True
        self.thread = threading.Thread(target=self._check_loop, daemon=True)
        self.thread.start()

        logger.info("ReminderManager started")

    def stop(self):

        if not self.running:
            return

        self.running = False

        if self.thread:
            self.thread.join(timeout=3)

        logger.info("ReminderManager stopped")