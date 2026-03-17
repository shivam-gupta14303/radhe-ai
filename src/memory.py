# memory.py
"""
Thread-safe MemoryManager.

Features:
- Generic text memories (existing behaviour) in `memories` table.
- Long-term personal profile storage in `personal_profile` table:
    - user_id, key, value, metadata, updated_at
    - Example: ("default", "language", "hi"), ("default", "avoid_calls", '["beta","sir"]')

Usage:
- memory = MemoryManager("data/memory.db")

Generic memory (optional, as before):
- memory.store_memory("I talked about quantum physics", {"type": "note"})
- memory.recall_memory("quantum", limit=5)

Personal profile:
- memory.set_profile_value("language", "hi", user_id="default")
- profile = memory.get_profile("default")  # {"language": "hi", "mode": "casual", ...}
- lang = memory.get_profile_value("language", user_id="default")
- memory.delete_profile_value("language", user_id="default")
- memory.clear_profile(user_id="default")
"""

import sqlite3
import json
import datetime
import threading
from typing import List, Dict, Any, Optional

_lock = threading.Lock()


class MemoryManager:
    def __init__(self, db_path: str = "data/memory.db"):
        self.db_path = db_path
        self._init_db()

    def _connect(self):
        # open with check_same_thread=False for safety across threads when needed
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def _init_db(self):
        with _lock, self._connect() as conn:
            cur = conn.cursor()

            # 1) Generic memories table (as you already had)
            cur.execute(
                '''
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    context TEXT,
                    metadata TEXT
                )
                '''
            )

            # 2) Personal profile table (long-term user data)
            #    UNIQUE(user_id, key) so we can upsert on that pair.
            cur.execute(
                '''
                CREATE TABLE IF NOT EXISTS personal_profile (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT,
                    metadata TEXT,
                    updated_at TEXT,
                    UNIQUE(user_id, key)
                )
                '''
            )

            conn.commit()

    # ------------------ GENERIC MEMORY (as before) ------------------ #

    def store_memory(self, context: str, metadata: Dict = None):
        """
        Store a generic memory line with optional metadata.
        This is not necessarily "personal profile", just any text you want to log.
        """
        try:
            meta = json.dumps(metadata or {})
            ts = datetime.datetime.utcnow().isoformat()
            with _lock, self._connect() as conn:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO memories (timestamp, context, metadata) VALUES (?, ?, ?)",
                    (ts, context, meta)
                )
                conn.commit()
        except Exception as e:
            print("Error storing memory:", e)

    def recall_memory(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Simple LIKE-based search over generic memories.
        """
        try:
            with _lock, self._connect() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT timestamp, context, metadata FROM memories "
                    "WHERE context LIKE ? "
                    "ORDER BY timestamp DESC LIMIT ?",
                    (f"%{query}%", limit)
                )
                rows = cur.fetchall()
            return [
                {
                    "timestamp": r[0],
                    "context": r[1],
                    "metadata": json.loads(r[2] or "{}")
                }
                for r in rows
            ]
        except Exception as e:
            print("Error recalling memory:", e)
            return []

    # ------------------ PERSONAL PROFILE (long-term) ------------------ #

    def set_profile_value(
        self,
        key: str,
        value: str,
        user_id: str = "default",
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Set or update a personal profile field.
        Example:
            set_profile_value("language", "hi", "default")
            set_profile_value("mode", "casual", "default")
            set_profile_value("avoid_calls", '["beta","sir"]', "default")
        """
        try:
            meta_json = json.dumps(metadata or {})
            updated_at = datetime.datetime.utcnow().isoformat()
            with _lock, self._connect() as conn:
                cur = conn.cursor()
                # ON CONFLICT works because we have UNIQUE(user_id, key)
                cur.execute(
                    '''
                    INSERT INTO personal_profile (user_id, key, value, metadata, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(user_id, key) DO UPDATE SET
                        value = excluded.value,
                        metadata = excluded.metadata,
                        updated_at = excluded.updated_at
                    ''',
                    (user_id, key, str(value), meta_json, updated_at)
                )
                conn.commit()
        except Exception as e:
            print("Error setting profile value:", e)

    def get_profile(self, user_id: str = "default") -> Dict[str, str]:
        """
        Return full profile for the user as a dict: {key: value, ...}
        """
        try:
            with _lock, self._connect() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT key, value FROM personal_profile WHERE user_id = ?",
                    (user_id,)
                )
                rows = cur.fetchall()
            return {k: v for (k, v) in rows}
        except Exception as e:
            print("Error reading profile:", e)
            return {}

    def get_profile_value(
        self,
        key: str,
        user_id: str = "default",
        default: Optional[str] = None
    ) -> Optional[str]:
        """
        Get a single profile field.
        """
        try:
            with _lock, self._connect() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT value FROM personal_profile WHERE user_id = ? AND key = ?",
                    (user_id, key)
                )
                row = cur.fetchone()
            if row is None:
                return default
            return row[0]
        except Exception as e:
            print("Error getting profile value:", e)
            return default

    def delete_profile_value(self, key: str, user_id: str = "default") -> None:
        """
        Delete a single profile field.
        """
        try:
            with _lock, self._connect() as conn:
                cur = conn.cursor()
                cur.execute(
                    "DELETE FROM personal_profile WHERE user_id = ? AND key = ?",
                    (user_id, key)
                )
                conn.commit()
        except Exception as e:
            print("Error deleting profile value:", e)

    def clear_profile(self, user_id: str = "default") -> None:
        """
        Remove all profile data for one user.
        (Use carefully.)
        """
        try:
            with _lock, self._connect() as conn:
                cur = conn.cursor()
                cur.execute(
                    "DELETE FROM personal_profile WHERE user_id = ?",
                    (user_id,)
                )
                conn.commit()
        except Exception as e:
            print("Error clearing profile:", e)
