# proactive_engine.py
"""
Proactive Background Intelligence Engine for Radhe.

Evaluates user routines, calendar agenda, pending tasks, medication schedules,
and hydration targets to proactively propose timely actions and alerts.
"""

import os
import sys
import time
import logging
import threading
from pathlib import Path
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, List, Callable

from calendar_manager import calendar_manager
from reminder_manager import reminder_manager
from health_assistant import health_assistant
from mobile_bridge import mobile_bridge

logger = logging.getLogger("Radhe_ProactiveEngine")
logger.setLevel(logging.INFO)

_engine_lock = threading.Lock()


class ProactiveEngine:
    """Evaluates context and routines to generate proactive suggestions."""

    def __init__(self):
        self._alerted_cache: Dict[str, str] = {}
        self._notify_cb: Optional[Callable[[str], None]] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def register_notification_callback(self, cb: Callable[[str], None]) -> None:
        """Register voice/TTS or UI callback for proactive speech."""
        self._notify_cb = cb

    def check_upcoming_meetings(self, window_minutes: int = 15) -> List[Dict[str, Any]]:
        """Alert for calendar events starting in the next N minutes."""
        now = datetime.now()
        horizon = now + timedelta(minutes=window_minutes)
        events = calendar_manager.get_events()
        alerts = []

        for e in events:
            try:
                start_dt = datetime.fromisoformat(e["start_time"].replace("Z", ""))
                # If event starts between now and horizon
                if now <= start_dt <= horizon:
                    alert_key = f"event_{e['id']}_{start_dt.strftime('%Y%m%d%H%M')}"
                    if alert_key not in self._alerted_cache:
                        mins_left = max(1, int((start_dt - now).total_seconds() / 60))
                        msg = f"Heads up! '{e['title']}' is starting in {mins_left} minutes"
                        if e.get("location"):
                            msg += f" at {e['location']}."
                        else:
                            msg += "."
                        self._alerted_cache[alert_key] = now.isoformat()
                        alerts.append({
                            "type": "meeting",
                            "title": e["title"],
                            "message": msg,
                            "starts_in_minutes": mins_left
                        })
            except Exception as ex:
                logger.debug("Date parsing error for event: %s", ex)

        return alerts

    def check_hydration_needed(self) -> Optional[Dict[str, Any]]:
        """Remind user to drink water during waking hours (09:00 - 21:00)."""
        now = datetime.now()
        if not (9 <= now.hour < 21):
            return None

        today_str = date.today().isoformat()
        alert_key = f"hydration_{today_str}_{now.hour // 3}" # Once every 3 hours
        if alert_key in self._alerted_cache:
            return None

        total_ml = health_assistant.get_daily_water_total()
        target_ml = 2500.0

        # If halfway through day and less than 1000ml, prompt
        if now.hour >= 14 and total_ml < 1000.0:
            self._alerted_cache[alert_key] = now.isoformat()
            return {
                "type": "hydration",
                "message": f"Time for some water! You've had {int(total_ml)}ml today out of your 2500ml target."
            }
        return None

    def check_pending_medications(self) -> List[Dict[str, Any]]:
        """Check for scheduled medications that have not been logged today."""
        now = datetime.now()
        meds = health_assistant.list_medications(active_only=True)
        alerts = []

        for m in meds:
            sched_time_str = m.get("schedule_time", "")
            try:
                # Compare HH:MM
                parts = sched_time_str.split(":")
                if len(parts) >= 2:
                    sched_hour = int(parts[0])
                    sched_min = int(parts[1][:2])
                    # If current time is past schedule time
                    if (now.hour > sched_hour) or (now.hour == sched_hour and now.minute >= sched_min):
                        alert_key = f"med_{m['id']}_{date.today().isoformat()}"
                        if alert_key not in self._alerted_cache:
                            self._alerted_cache[alert_key] = now.isoformat()
                            alerts.append({
                                "type": "medication",
                                "name": m["name"],
                                "dosage": m["dosage"],
                                "message": f"Reminder: It's time to take your {m['name']} ({m['dosage']})."
                            })
            except Exception:
                pass

        return alerts

    def check_overdue_tasks(self) -> List[Dict[str, Any]]:
        """Check for overdue high/urgent priority tasks."""
        tasks = reminder_manager.list_tasks(status="pending")
        now_str = date.today().isoformat()
        alerts = []

        for t in tasks:
            if t.get("priority") in ("high", "urgent") and t.get("due_date"):
                if t["due_date"] < now_str:
                    alert_key = f"task_{t['id']}_{now_str}"
                    if alert_key not in self._alerted_cache:
                        self._alerted_cache[alert_key] = now_str
                        alerts.append({
                            "type": "task",
                            "title": t["title"],
                            "message": f"Overdue Task: '{t['title']}' was due on {t['due_date']}."
                        })

        return alerts

    def evaluate_all(self) -> List[Dict[str, Any]]:
        """Run all proactive intelligence evaluators and dispatch notifications."""
        with _engine_lock:
            all_alerts: List[Dict[str, Any]] = []

            # 1. Meetings
            meeting_alerts = self.check_upcoming_meetings()
            all_alerts.extend(meeting_alerts)

            # 2. Hydration
            hyd_alert = self.check_hydration_needed()
            if hyd_alert:
                all_alerts.append(hyd_alert)

            # 3. Medications
            med_alerts = self.check_pending_medications()
            all_alerts.extend(med_alerts)

            # 4. Overdue tasks
            task_alerts = self.check_overdue_tasks()
            all_alerts.extend(task_alerts)

            # Forward each alert to mobile companion push queue and speech callback
            for a in all_alerts:
                msg = a.get("message", "")
                cat = a.get("type", "general")
                mobile_bridge.queue_notification(category=cat, title=f"Radhe {cat.capitalize()} Alert", body=msg, payload=a)
                if self._notify_cb:
                    try:
                        self._notify_cb(msg)
                    except Exception as e:
                        logger.warning("Notification callback failed: %s", e)

            return all_alerts


# Global proactive engine instance
proactive_engine = ProactiveEngine()
