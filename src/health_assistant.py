# health_assistant.py
"""
Personal Health Assistant Module for Radhe.

Provides:
- Daily vitals logging (water intake, sleep, steps, blood pressure, blood glucose, weight).
- Medication management and adherence tracking with recurring reminders.
- Safe symptom triage with strict medical guardrails, emergency hotlines, and disclaimers.
- Fully offline-first SQLite database (data/health.db).
"""

import os
import sys
import json
import sqlite3
import logging
import threading
from pathlib import Path
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, List, Tuple
from contextlib import contextmanager

from config import DATA_DIR
from reminder_manager import reminder_manager

logger = logging.getLogger("Radhe_Health")
logger.setLevel(logging.INFO)

HEALTH_DB_FILE = DATA_DIR / "health.db"
_health_lock = threading.Lock()

DISCLAIMER_EN = (
    "Disclaimer: I am an AI companion, not a medical doctor. This information is for general "
    "wellness guidance only and should not replace professional medical advice, diagnosis, or treatment."
)

DISCLAIMER_HI = (
    "Dhyan dein: Main ek AI companion hoon, doctor nahi. Yeh jaankari kewal general guidance ke liye hai, "
    "kisi bhi bimari ya dava ke liye kripya certified doctor se consult karein."
)

EMERGENCY_HOTLINES = [
    {"service": "National Emergency Helpline", "number": "112"},
    {"service": "Ambulance / Medical Emergency", "number": "108"},
    {"service": "Mental Health & Distress (Kiran)", "number": "1800-599-0019"},
    {"service": "iCall Psychosocial Helpline", "number": "9152987821"},
]

RED_FLAG_SYMPTOMS = [
    "chest pain", "shortness of breath", "difficulty breathing",
    "sudden numbness", "loss of speech", "coughing blood",
    "unconscious", "fainting", "severe head injury", "poisoning",
    "chhati mein dard", "saans lene mein takleef", "behosh"
]


class HealthAssistant:
    """Manages daily wellness vitals, medication adherence, and safe triage."""

    def __init__(self, db_path: Path = HEALTH_DB_FILE):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _connection(self):
        """Thread-safe SQLite connection context with explicit cleanup."""
        conn = None
        try:
            with _health_lock:
                conn = sqlite3.connect(self.db_path, check_same_thread=False)
                conn.row_factory = sqlite3.Row
                with conn:
                    yield conn
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def _init_db(self) -> None:
        """Create tables for vitals and medications."""
        with self._connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS vitals_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL DEFAULT 'default',
                    metric TEXT NOT NULL,
                    value REAL NOT NULL,
                    unit TEXT,
                    notes TEXT,
                    logged_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_vitals_user_date ON vitals_log (user_id, logged_at);

                CREATE TABLE IF NOT EXISTS medications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL DEFAULT 'default',
                    name TEXT NOT NULL,
                    dosage TEXT NOT NULL,
                    schedule_time TEXT NOT NULL,
                    instructions TEXT,
                    remaining_doses INTEGER DEFAULT 30,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS medication_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL DEFAULT 'default',
                    medication_id INTEGER,
                    medication_name TEXT NOT NULL,
                    scheduled_at TEXT NOT NULL,
                    taken_at TEXT,
                    status TEXT NOT NULL DEFAULT 'taken'
                );
            """)

    # ==================================================================
    # VITALS LOGGING
    # ==================================================================

    def log_vital(
        self,
        metric: str,
        value: float,
        unit: Optional[str] = None,
        notes: str = "",
        user_id: str = "default",
        logged_at: Optional[str] = None
    ) -> int:
        """Log a health vital record (e.g. water_ml, sleep_hours, systolic, glucose)."""
        clean_metric = metric.strip().lower().replace(" ", "_")
        now_str = logged_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Default units
        default_units = {
            "water": "ml", "water_ml": "ml", "sleep": "hours", "sleep_hours": "hours",
            "steps": "steps", "systolic": "mmHg", "diastolic": "mmHg",
            "glucose": "mg/dL", "heart_rate": "bpm", "weight": "kg"
        }
        resolved_unit = unit or default_units.get(clean_metric, "")

        with self._connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO vitals_log (user_id, metric, value, unit, notes, logged_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, clean_metric, float(value), resolved_unit, notes, now_str))
            return cur.lastrowid

    def log_water(self, amount_ml: float, user_id: str = "default") -> Tuple[float, str]:
        """Convenience method to log water intake and return today's total."""
        self.log_vital("water_ml", amount_ml, unit="ml", user_id=user_id)
        today_total = self.get_daily_water_total(user_id=user_id)
        target = 2500.0
        msg = f"Logged {int(amount_ml)}ml water. Today's total: {int(today_total)}ml / {int(target)}ml."
        if today_total >= target:
            msg += " Great job! You reached your daily hydration goal!"
        return today_total, msg

    def get_daily_water_total(self, target_date: Optional[str] = None, user_id: str = "default") -> float:
        """Calculate total water consumed on a given date (default today)."""
        d = target_date or date.today().isoformat()
        with self._connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT SUM(value) FROM vitals_log
                WHERE user_id = ? AND metric IN ('water', 'water_ml') AND logged_at LIKE ?
            """, (user_id, f"{d}%"))
            row = cur.fetchone()
            return float(row[0] or 0.0)

    def get_daily_vitals_summary(self, target_date: Optional[str] = None, user_id: str = "default") -> Dict[str, Any]:
        """Return all logged vitals for a specific day."""
        d = target_date or date.today().isoformat()
        with self._connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT metric, value, unit, notes, logged_at FROM vitals_log
                WHERE user_id = ? AND logged_at LIKE ?
                ORDER BY logged_at ASC
            """, (user_id, f"{d}%"))
            rows = cur.fetchall()

        summary: Dict[str, Any] = {
            "date": d,
            "water_ml": 0.0,
            "sleep_hours": None,
            "steps": 0,
            "blood_pressure": None,
            "glucose": None,
            "weight_kg": None,
            "raw_entries": []
        }

        systolic = None
        diastolic = None

        for r in rows:
            m = r["metric"]
            val = r["value"]
            summary["raw_entries"].append({
                "metric": m, "value": val, "unit": r["unit"], "time": r["logged_at"]
            })
            if m in ("water", "water_ml"):
                summary["water_ml"] += val
            elif m in ("sleep", "sleep_hours"):
                summary["sleep_hours"] = val
            elif m == "steps":
                summary["steps"] += int(val)
            elif m == "systolic":
                systolic = int(val)
            elif m == "diastolic":
                diastolic = int(val)
            elif m == "glucose":
                summary["glucose"] = val
            elif m == "weight":
                summary["weight_kg"] = val

        if systolic and diastolic:
            summary["blood_pressure"] = f"{systolic}/{diastolic} mmHg"

        return summary

    # ==================================================================
    # MEDICATION MANAGEMENT
    # ==================================================================

    def add_medication(
        self,
        name: str,
        dosage: str,
        schedule_time: str,
        instructions: str = "",
        remaining_doses: int = 30,
        user_id: str = "default"
    ) -> int:
        """Register a medication with dosage and schedule."""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO medications (user_id, name, dosage, schedule_time, instructions, remaining_doses, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'active', ?)
            """, (user_id, name.strip(), dosage.strip(), schedule_time.strip(), instructions.strip(), remaining_doses, now_str))
            med_id = cur.lastrowid

        # Also schedule a reminder in reminder_manager
        try:
            reminder_manager.add_reminder(
                task=f"Take medication: {name} ({dosage}) {instructions}".strip(),
                time_str=schedule_time,
                recurrence="daily"
            )
        except Exception as e:
            logger.warning("Could not auto-schedule medication reminder: %s", e)

        return med_id

    def list_medications(self, active_only: bool = True, user_id: str = "default") -> List[Dict[str, Any]]:
        """List user medications."""
        with self._connection() as conn:
            cur = conn.cursor()
            if active_only:
                cur.execute("SELECT * FROM medications WHERE user_id = ? AND status = 'active' ORDER BY name ASC", (user_id,))
            else:
                cur.execute("SELECT * FROM medications WHERE user_id = ? ORDER BY name ASC", (user_id,))
            rows = cur.fetchall()
            return [dict(r) for r in rows]

    def log_medication_taken(self, medication_name: str, user_id: str = "default") -> Tuple[bool, str]:
        """Mark a dose of medication as taken, updating inventory."""
        meds = self.list_medications(active_only=True, user_id=user_id)
        target = None
        for m in meds:
            if medication_name.lower() in m["name"].lower():
                target = m
                break

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if not target:
            # Still record the entry even if not pre-registered
            with self._connection() as conn:
                conn.execute("""
                    INSERT INTO medication_logs (user_id, medication_id, medication_name, scheduled_at, taken_at, status)
                    VALUES (?, NULL, ?, ?, ?, 'taken')
                """, (user_id, medication_name, now_str, now_str))
            return True, f"Logged {medication_name} as taken."

        # Update remaining inventory
        new_remaining = max(0, target["remaining_doses"] - 1)
        with self._connection() as conn:
            conn.execute("UPDATE medications SET remaining_doses = ? WHERE id = ?", (new_remaining, target["id"]))
            conn.execute("""
                INSERT INTO medication_logs (user_id, medication_id, medication_name, scheduled_at, taken_at, status)
                VALUES (?, ?, ?, ?, ?, 'taken')
            """, (user_id, target["id"], target["name"], target["schedule_time"], now_str))

        refill_warning = ""
        if new_remaining <= 5:
            refill_warning = f" (Refill Alert: Only {new_remaining} doses remaining!)"

        return True, f"Great! Marked {target['name']} ({target['dosage']}) as taken.{refill_warning}"

    # ==================================================================
    # SYMPTOM TRIAGE & SAFETY
    # ==================================================================

    def triage_symptoms(self, query: str, language: str = "en") -> Dict[str, Any]:
        """
        Evaluate reported symptoms with strict safety boundaries,
        emergency red flag alerts, and medical disclaimers.
        """
        q_lower = query.lower()
        is_emergency = any(rf in q_lower for rf in RED_FLAG_SYMPTOMS)
        disclaimer = DISCLAIMER_HI if language == "hi" else DISCLAIMER_EN

        if is_emergency:
            return {
                "is_emergency": True,
                "urgency": "critical",
                "message": (
                    "CRITICAL HEALTH ALERT: The symptoms you described may indicate a serious medical emergency. "
                    "Please do not wait. Immediately call emergency services or go to the nearest hospital."
                ),
                "hotlines": EMERGENCY_HOTLINES,
                "disclaimer": disclaimer,
            }

        guidance = (
            f"I have noted your symptoms: '{query}'. "
            "To help your doctor understand better, make note of: "
            "1) When the symptoms started, 2) Severity on a 1-10 scale, and 3) Any accompanying fever or pain. "
            "If your symptoms worsen or persist, please consult a healthcare professional."
        )

        return {
            "is_emergency": False,
            "urgency": "routine",
            "message": guidance,
            "hotlines": EMERGENCY_HOTLINES,
            "disclaimer": disclaimer,
        }


# Global health assistant instance
health_assistant = HealthAssistant()
