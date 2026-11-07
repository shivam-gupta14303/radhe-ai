# reminder_manager.py
"""
ReminderManager — Unified SQLite-backed reminder and task management system for Radhe.

Features:
- Safe, non-locking SQLite connection contextmanager for Windows.
- Time parsing with automatic recurrence (daily, weekly, weekdays).
- Priority levels: low, medium, high, urgent.
- Task management (CRUD, status tracking, categories).
- Clean background loop with graceful shutdown.
"""

import sqlite3
import threading
import time
import datetime
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import List, Tuple, Optional, Callable, Dict, Any
from config import REMINDERS_DB_FILE
from time_parser import parse_time

logger = logging.getLogger("Radhe_Reminder")
logger.setLevel(logging.INFO)

DB_PATH = str(REMINDERS_DB_FILE)
_lock   = threading.Lock()
_CHECK_INTERVAL = 5  # seconds between checks


class ReminderManager:

    def __init__(self, speak_function: Optional[Callable[[str], None]] = None, db_path: str = DB_PATH):
        self.db_path = str(db_path)
        self.speak   = speak_function or (lambda msg: logger.info("Radhe Spoken: %s", msg))
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self._init_db()

    # ==================================================================
    # DB SETUP & CONNECTION MANAGEMENT
    # ==================================================================

    @contextmanager
    def _connection(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        try:
            with _lock, conn:
                yield conn
        finally:
            conn.close()

    def _connect(self):
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def _init_db(self):
        """Initialize reminders and tasks tables with schema migrations."""
        with self._connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS reminders (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    task       TEXT    NOT NULL,
                    due_time   TEXT    NOT NULL,
                    created_at TEXT    DEFAULT CURRENT_TIMESTAMP,
                    status     TEXT    DEFAULT 'pending',
                    priority   TEXT    DEFAULT 'medium',
                    recurrence TEXT    DEFAULT 'none'
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    title        TEXT    NOT NULL,
                    description  TEXT    DEFAULT '',
                    priority     TEXT    DEFAULT 'medium',
                    due_date     TEXT,
                    status       TEXT    DEFAULT 'pending',
                    category     TEXT    DEFAULT 'general',
                    created_at   TEXT    DEFAULT CURRENT_TIMESTAMP,
                    completed_at TEXT
                )
            """)

            # Safe schema migrations for existing databases
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(reminders)")
            cols = [col[1] for col in cur.fetchall()]
            if "priority" not in cols:
                conn.execute("ALTER TABLE reminders ADD COLUMN priority TEXT DEFAULT 'medium'")
            if "recurrence" not in cols:
                conn.execute("ALTER TABLE reminders ADD COLUMN recurrence TEXT DEFAULT 'none'")

            conn.commit()

    # ==================================================================
    # REMINDER CRUD
    # ==================================================================

    def add_reminder(
        self,
        task: str,
        time_str: str,
        priority: str = "medium",
        recurrence: str = "none"
    ) -> bool:
        """
        Parse time_str and save reminder to database.
        Returns True on success, False if time could not be parsed.
        """
        task     = (task or "").strip()
        time_str = (time_str or "").strip()

        if not task:
            logger.warning("add_reminder: empty task.")
            return False

        dt = parse_time(time_str)
        if not dt:
            logger.error("Could not parse reminder time: '%s'", time_str)
            return False

        iso = dt.isoformat()
        prio = priority.lower().strip() if priority else "medium"
        rec = recurrence.lower().strip() if recurrence else "none"

        try:
            with self._connection() as conn:
                conn.execute("""
                    INSERT INTO reminders (task, due_time, priority, recurrence)
                    VALUES (?, ?, ?, ?)
                """, (task, iso, prio, rec))
                conn.commit()

            logger.info("Reminder set: '%s' at %s (Priority: %s, Recurrence: %s)", task, iso, prio, rec)
            return True
        except Exception as e:
            logger.exception("add_reminder error: %s", e)
            return False

    def get_upcoming_reminders(self, limit: int = 10) -> List[Tuple[int, str, str]]:
        """Return up to `limit` pending reminders as (id, task, due_time)."""
        try:
            with self._connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT id, task, due_time
                    FROM reminders
                    WHERE status = 'pending'
                    ORDER BY due_time ASC
                    LIMIT ?
                """, (limit,))
                return cur.fetchall()
        except Exception as e:
            logger.exception("get_upcoming_reminders error: %s", e)
            return []

    def list_reminders(self) -> str:
        """
        Human-readable summary of upcoming reminders.
        Used when Radhe answers 'what reminders do I have?'
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

    def cancel_reminder(self, keyword: str) -> str:
        """
        Cancel the first pending reminder whose task contains `keyword`.
        Returns a friendly status string.
        """
        keyword = (keyword or "").strip().lower()
        if not keyword:
            return "Please tell me which reminder to cancel."

        try:
            with self._connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT id, task FROM reminders WHERE status='pending'")
                rows = cur.fetchall()

                for rid, task in rows:
                    if keyword in (task or "").lower():
                        cur.execute("UPDATE reminders SET status='cancelled' WHERE id=?", (rid,))
                        conn.commit()
                        logger.info("Cancelled reminder id=%d: %s", rid, task)
                        return f"Cancelled reminder: {task}"

            return f"No pending reminder found matching '{keyword}'."
        except Exception as e:
            logger.exception("cancel_reminder failed: %s", e)
            return "Could not cancel reminder due to an error."

    # ==================================================================
    # TASK MANAGEMENT (Phase 4 Deliverable)
    # ==================================================================

    def add_task(
        self,
        title: str,
        priority: str = "medium",
        due_date: Optional[str] = None,
        category: str = "general",
        description: str = ""
    ) -> int:
        """Add a new task item and return its ID."""
        title = (title or "").strip()
        if not title:
            return 0

        prio = priority.lower().strip() if priority in ("low", "medium", "high", "urgent") else "medium"
        cat = category.strip() or "general"

        parsed_due = None
        if due_date:
            dt = parse_time(due_date)
            parsed_due = dt.isoformat() if dt else due_date

        try:
            with self._connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO tasks (title, description, priority, due_date, status, category)
                    VALUES (?, ?, ?, ?, 'pending', ?)
                """, (title, description.strip(), prio, parsed_due, cat))
                new_id = cur.lastrowid
                conn.commit()

            logger.info("Task created [id=%d, prio=%s]: %s", new_id, prio, title)
            return new_id
        except Exception as e:
            logger.exception("add_task failed: %s", e)
            return 0

    def list_tasks(
        self,
        status: str = "pending",
        category: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """List tasks filtered by status and category."""
        try:
            with self._connection() as conn:
                cur = conn.cursor()
                clauses = []
                params: List[Any] = []

                if status and str(status).lower() != "all":
                    clauses.append("status = ?")
                    params.append(str(status).lower())

                if category and category.lower() != "all":
                    clauses.append("category = ?")
                    params.append(category)

                where_stmt = f"WHERE {' AND '.join(clauses)}" if clauses else ""
                sql = f"""
                    SELECT id, title, description, priority, due_date, status, category, created_at, completed_at
                    FROM tasks
                    {where_stmt}
                    ORDER BY 
                        CASE priority 
                            WHEN 'urgent' THEN 1 
                            WHEN 'high' THEN 2 
                            WHEN 'medium' THEN 3 
                            ELSE 4 
                        END, 
                        due_date ASC, created_at DESC
                    LIMIT ?
                """
                params.append(limit)
                cur.execute(sql, params)
                rows = cur.fetchall()

            tasks = []
            for r in rows:
                tasks.append({
                    "id": r[0],
                    "title": r[1],
                    "description": r[2],
                    "priority": r[3],
                    "due_date": r[4],
                    "status": r[5],
                    "category": r[6],
                    "created_at": r[7],
                    "completed_at": r[8]
                })
            return tasks
        except Exception as e:
            logger.exception("list_tasks failed: %s", e)
            return []

    def complete_task(self, identifier: Any) -> bool:
        """Mark a task completed by ID or title substring."""
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        try:
            with self._connection() as conn:
                cur = conn.cursor()
                if isinstance(identifier, int) or (isinstance(identifier, str) and identifier.isdigit()):
                    cur.execute("""
                        UPDATE tasks SET status = 'completed', completed_at = ?
                        WHERE id = ? AND status != 'completed'
                    """, (now_iso, int(identifier)))
                else:
                    kw = str(identifier).strip().lower()
                    cur.execute("""
                        UPDATE tasks SET status = 'completed', completed_at = ?
                        WHERE id IN (
                            SELECT id FROM tasks 
                            WHERE LOWER(title) LIKE ? AND status != 'completed' 
                            LIMIT 1
                        )
                    """, (now_iso, f"%{kw}%"))

                changed = cur.rowcount > 0
                conn.commit()
                return changed
        except Exception as e:
            logger.exception("complete_task failed: %s", e)
            return False

    def delete_task(self, identifier: Any) -> bool:
        """Permanently delete a task by ID or title substring."""
        try:
            with self._connection() as conn:
                cur = conn.cursor()
                if isinstance(identifier, int) or (isinstance(identifier, str) and identifier.isdigit()):
                    cur.execute("DELETE FROM tasks WHERE id = ?", (int(identifier),))
                else:
                    kw = str(identifier).strip().lower()
                    cur.execute("""
                        DELETE FROM tasks WHERE id IN (
                            SELECT id FROM tasks WHERE LOWER(title) LIKE ? LIMIT 1
                        )
                    """, (f"%{kw}%",))

                changed = cur.rowcount > 0
                conn.commit()
                return changed
        except Exception as e:
            logger.exception("delete_task failed: %s", e)
            return False

    def get_tasks_summary(self) -> Dict[str, Any]:
        """Return task statistics for briefings and dashboard."""
        summary = {"total": 0, "pending": 0, "completed": 0, "by_priority": {}}
        try:
            with self._connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT status, COUNT(*) FROM tasks GROUP BY status")
                for st, count in cur.fetchall():
                    if st in summary:
                        summary[st] = count
                    summary["total"] += count

                cur.execute("""
                    SELECT priority, COUNT(*) FROM tasks 
                    WHERE status = 'pending' 
                    GROUP BY priority
                """)
                for prio, count in cur.fetchall():
                    summary["by_priority"][prio] = count

            return summary
        except Exception as e:
            logger.exception("get_tasks_summary failed: %s", e)
            return summary

    # ==================================================================
    # BACKGROUND CHECKER & RECURRENCE ENGINE
    # ==================================================================

    def _calculate_next_occurrence(self, due_iso: str, recurrence: str) -> Optional[str]:
        """Compute the next ISO due time for recurring reminders."""
        try:
            current_dt = datetime.datetime.fromisoformat(due_iso)
            rec = recurrence.lower().strip()

            if rec == "daily":
                next_dt = current_dt + datetime.timedelta(days=1)
            elif rec == "weekly":
                next_dt = current_dt + datetime.timedelta(weeks=1)
            elif rec == "weekdays":
                # Monday-Friday
                next_dt = current_dt + datetime.timedelta(days=1)
                while next_dt.weekday() >= 5:  # 5=Sat, 6=Sun
                    next_dt += datetime.timedelta(days=1)
            else:
                return None

            return next_dt.isoformat()
        except Exception as e:
            logger.error("Error calculating next occurrence: %s", e)
            return None

    def _check_loop(self):
        logger.info("Reminder checker started.")

        while self.running:
            try:
                now_iso = datetime.datetime.now().isoformat()

                with self._connection() as conn:
                    cur = conn.cursor()
                    cur.execute("""
                        SELECT id, task, due_time, recurrence, priority
                        FROM reminders
                        WHERE status = 'pending' AND due_time <= ?
                    """, (now_iso,))
                    due_rows = cur.fetchall()

                    for rid, task, due_time, rec, prio in due_rows:
                        try:
                            prefix = "Urgent Reminder" if prio == "urgent" else "Reminder"
                            self.speak(f"{prefix}: {task}")
                        except Exception:
                            logger.exception("Failed to speak reminder id=%d", rid)

                        next_due = self._calculate_next_occurrence(due_time, rec)
                        if next_due:
                            cur.execute(
                                "UPDATE reminders SET due_time = ? WHERE id = ?",
                                (next_due, rid)
                            )
                            logger.info("Rescheduled recurring reminder id=%d to %s", rid, next_due)
                        else:
                            cur.execute(
                                "UPDATE reminders SET status='completed' WHERE id=?",
                                (rid,)
                            )

                    conn.commit()

                # Clean up completed reminders older than 7 days
                with self._connection() as conn:
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
    # START / STOP / LEGACY COMPATIBILITY
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


# ── Global singleton ───────────────────────────────────────────────────
default_reminder_manager = ReminderManager()

reminder_manager = default_reminder_manager
