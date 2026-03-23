# memory.py
"""
Thread-safe MemoryManager — SQLite backend.

Tables:
- memories         : generic text memory log
- personal_profile : long-term per-user key-value store
- contacts         : contact name → phone mapping  ✅ NEW

Fix vs previous version:
- print() replaced with logger throughout.
"""

import sqlite3
import json
import datetime
import threading
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("Radhe_Memory")
logger.setLevel(logging.INFO)

_lock = threading.Lock()


class MemoryManager:

    def __init__(self, db_path: str = "data/memory.db"):
        self.db_path = db_path
        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def _init_db(self):
        try:
            with _lock, self._connect() as conn:
                cur = conn.cursor()

                # EXISTING TABLES
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS memories (
                        id        INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT,
                        context   TEXT,
                        metadata  TEXT
                    )
                """)

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS personal_profile (
                        id         INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id    TEXT NOT NULL,
                        key        TEXT NOT NULL,
                        value      TEXT,
                        metadata   TEXT,
                        updated_at TEXT,
                        UNIQUE(user_id, key)
                    )
                """)

                # ✅ NEW: CONTACTS TABLE
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS contacts (
                        name TEXT PRIMARY KEY,
                        phone TEXT
                    )
                """)

                conn.commit()
        except Exception as e:
            logger.exception("Failed to initialise memory DB: %s", e)

    # ==================================================================
    # GENERIC MEMORY
    # ==================================================================

    def store_memory(self, context: str, metadata: Dict = None) -> None:
        try:
            meta = json.dumps(metadata or {})
            ts   = datetime.datetime.utcnow().isoformat()
            with _lock, self._connect() as conn:
                conn.execute(
                    "INSERT INTO memories (timestamp, context, metadata) VALUES (?, ?, ?)",
                    (ts, context, meta)
                )
                conn.commit()
        except Exception as e:
            logger.exception("store_memory failed: %s", e)

    def recall_memory(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        try:
            with _lock, self._connect() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT timestamp, context, metadata FROM memories "
                    "WHERE context LIKE ? ORDER BY timestamp DESC LIMIT ?",
                    (f"%{query}%", limit)
                )
                rows = cur.fetchall()
            return [
                {"timestamp": r[0], "context": r[1], "metadata": json.loads(r[2] or "{}")}
                for r in rows
            ]
        except Exception as e:
            logger.exception("recall_memory failed: %s", e)
            return []

    # ==================================================================
    # PERSONAL PROFILE
    # ==================================================================

    def set_profile_value(
        self,
        key:      str,
        value:    str,
        user_id:  str = "default",
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        try:
            meta_json  = json.dumps(metadata or {})
            updated_at = datetime.datetime.utcnow().isoformat()
            with _lock, self._connect() as conn:
                conn.execute("""
                    INSERT INTO personal_profile (user_id, key, value, metadata, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(user_id, key) DO UPDATE SET
                        value      = excluded.value,
                        metadata   = excluded.metadata,
                        updated_at = excluded.updated_at
                """, (user_id, key, str(value), meta_json, updated_at))
                conn.commit()
        except Exception as e:
            logger.exception("set_profile_value failed: %s", e)

    def get_profile(self, user_id: str = "default") -> Dict[str, str]:
        try:
            with _lock, self._connect() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT key, value FROM personal_profile WHERE user_id = ?",
                    (user_id,)
                )
                return {k: v for k, v in cur.fetchall()}
        except Exception as e:
            logger.exception("get_profile failed: %s", e)
            return {}

    def get_profile_value(
        self,
        key:     str,
        user_id: str = "default",
        default: Optional[str] = None
    ) -> Optional[str]:
        try:
            with _lock, self._connect() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT value FROM personal_profile WHERE user_id = ? AND key = ?",
                    (user_id, key)
                )
                row = cur.fetchone()
            return row[0] if row else default
        except Exception as e:
            logger.exception("get_profile_value failed: %s", e)
            return default

    def delete_profile_value(self, key: str, user_id: str = "default") -> None:
        try:
            with _lock, self._connect() as conn:
                conn.execute(
                    "DELETE FROM personal_profile WHERE user_id = ? AND key = ?",
                    (user_id, key)
                )
                conn.commit()
        except Exception as e:
            logger.exception("delete_profile_value failed: %s", e)

    def clear_profile(self, user_id: str = "default") -> None:
        try:
            with _lock, self._connect() as conn:
                conn.execute(
                    "DELETE FROM personal_profile WHERE user_id = ?",
                    (user_id,)
                )
                conn.commit()
        except Exception as e:
            logger.exception("clear_profile failed: %s", e)

    # ==================================================================
    # ✅ CONTACT STORAGE (CRITICAL FIX)
    # ==================================================================

    def save_contact(self, name: str, phone: str):
        try:
            with _lock, self._connect() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO contacts (name, phone) VALUES (?, ?)",
                    (name.lower(), phone)
                )
                conn.commit()
        except Exception as e:
            logger.exception("save_contact failed: %s", e)

    def get_contact(self, name: str):
        try:
            with _lock, self._connect() as conn:
                cur = conn.execute(
                    "SELECT phone FROM contacts WHERE name=?",
                    (name.lower(),)
                )
                row = cur.fetchone()
                return row[0] if row else None
        except Exception as e:
            logger.exception("get_contact failed: %s", e)
            return None