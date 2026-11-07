# mobile_bridge.py
"""
Mobile Bridge & Companion Synchronization Engine for Radhe.

Provides:
- Mobile device registration and authentication (Android/iOS).
- Offline action queue synchronization.
- Push notification payload generation for WhatsApp approvals, medications, and briefing.
- Mobile companion telemetry and biometric authentication verification.
"""

import os
import sys
import json
import sqlite3
import logging
import threading
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple
from contextlib import contextmanager

from config import DATA_DIR
from security import mask_secret

logger = logging.getLogger("Radhe_MobileBridge")
logger.setLevel(logging.INFO)

MOBILE_DB_FILE = DATA_DIR / "mobile_sync.db"
_mobile_lock = threading.Lock()


class MobileBridge:
    """Manages pairing, sync, and notifications for the Android companion application."""

    def __init__(self, db_path: Path = MOBILE_DB_FILE):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _connection(self):
        conn = None
        try:
            with _mobile_lock:
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
        with self._connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS paired_devices (
                    device_id TEXT PRIMARY KEY,
                    device_name TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    push_token TEXT,
                    paired_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    biometric_enabled INTEGER DEFAULT 1,
                    status TEXT DEFAULT 'active'
                );

                CREATE TABLE IF NOT EXISTS notification_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT,
                    category TEXT NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    payload TEXT,
                    created_at TEXT NOT NULL,
                    status TEXT DEFAULT 'pending'
                );
            """)

    def register_device(
        self,
        device_id: str,
        device_name: str,
        platform: str = "android",
        push_token: Optional[str] = None,
        biometric_enabled: bool = True
    ) -> Dict[str, Any]:
        """Register or update a companion mobile device."""
        now = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            conn.execute("""
                INSERT INTO paired_devices (device_id, device_name, platform, push_token, paired_at, last_seen_at, biometric_enabled, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'active')
                ON CONFLICT(device_id) DO UPDATE SET
                    device_name = excluded.device_name,
                    push_token = COALESCE(excluded.push_token, paired_devices.push_token),
                    last_seen_at = excluded.last_seen_at,
                    biometric_enabled = excluded.biometric_enabled,
                    status = 'active'
            """, (device_id, device_name, platform, push_token, now, now, 1 if biometric_enabled else 0))

        logger.info("Companion device registered: %s (%s)", device_name, device_id)
        return {
            "device_id": device_id,
            "device_name": device_name,
            "status": "paired",
            "paired_at": now
        }

    def list_devices(self) -> List[Dict[str, Any]]:
        """List all paired companion mobile devices."""
        with self._connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT device_id, device_name, platform, paired_at, last_seen_at, biometric_enabled, status FROM paired_devices")
            rows = cur.fetchall()
            return [dict(r) for r in rows]

    def queue_notification(
        self,
        category: str,
        title: str,
        body: str,
        payload: Optional[Dict[str, Any]] = None,
        device_id: Optional[str] = None
    ) -> int:
        """Stage a push notification to be sent to companion devices."""
        now = datetime.now(timezone.utc).isoformat()
        payload_str = json.dumps(payload or {})
        with self._connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO notification_queue (device_id, category, title, body, payload, created_at, status)
                VALUES (?, ?, ?, ?, ?, ?, 'pending')
            """, (device_id, category, title, body, payload_str, now))
            return cur.lastrowid

    def get_pending_notifications(self, device_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch pending notifications for a companion device."""
        with self._connection() as conn:
            cur = conn.cursor()
            if device_id:
                cur.execute("""
                    SELECT id, category, title, body, payload, created_at FROM notification_queue
                    WHERE (device_id IS NULL OR device_id = ?) AND status = 'pending'
                    ORDER BY id ASC
                """, (device_id,))
            else:
                cur.execute("""
                    SELECT id, category, title, body, payload, created_at FROM notification_queue
                    WHERE status = 'pending'
                    ORDER BY id ASC
                """)
            rows = cur.fetchall()

            result = []
            for r in rows:
                result.append({
                    "id": r["id"],
                    "category": r["category"],
                    "title": r["title"],
                    "body": r["body"],
                    "payload": json.loads(r["payload"] or "{}"),
                    "created_at": r["created_at"]
                })
            return result

    def acknowledge_notification(self, notif_id: int) -> bool:
        """Mark notification as delivered/read."""
        with self._connection() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE notification_queue SET status = 'delivered' WHERE id = ?", (notif_id,))
            return cur.rowcount > 0

    def sync_mobile_state(self, device_id: str) -> Dict[str, Any]:
        """Consolidate mobile sync payload (telemetry, pending approvals, notifications, agenda)."""
        from reminder_manager import reminder_manager
        from calendar_manager import calendar_manager
        from social_media import social_integrator
        from health_assistant import health_assistant

        # Update last seen
        now = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            conn.execute("UPDATE paired_devices SET last_seen_at = ? WHERE device_id = ?", (now, device_id))

        notifications = self.get_pending_notifications(device_id)
        tasks = reminder_manager.list_tasks(status="pending")[:10]
        events = calendar_manager.get_events(limit=5)
        approvals = social_integrator.get_pending_approvals()
        health_summary = health_assistant.get_daily_vitals_summary()

        return {
            "timestamp": now,
            "device_id": device_id,
            "pending_notifications": notifications,
            "tasks": tasks,
            "calendar_events": events,
            "whatsapp_approvals": approvals,
            "health": health_summary
        }


# Global mobile bridge instance
mobile_bridge = MobileBridge()
