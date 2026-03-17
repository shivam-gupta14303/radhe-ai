# contact_manager.py
"""
ContactManager
- SQLite-backed contact store
- Handles storing, updating, listing, and retrieving contacts.
- Name matching is emoji- and case-insensitive:
  - Contact can be saved as "Mummy ❤️🥰"
  - You can just say/type "mummy" and it will still match.
"""

import sqlite3
import threading
import logging
import re
from typing import Optional, Dict, Any, List
from pathlib import Path

logger = logging.getLogger("Radhe_ContactManager")
logger.setLevel(logging.INFO)

Path("data").mkdir(parents=True, exist_ok=True)
DB = "data/contacts.db"
_lock = threading.Lock()


def _normalize_name(text: str) -> str:
    """
    Normalize a contact name for matching:
    - lowercase
    - remove emojis and special symbols (keep only a–z, 0–9 and spaces)
    Example:
        "Mummy ❤️🥰" -> "mummy"
        "Shikha_123!!" -> "shikha 123"
    """
    if not text:
        return ""
    text = text.lower()
    # keep only letters, digits and spaces
    text = re.sub(r"[^a-z0-9\s]", "", text)
    # collapse multiple spaces
    text = re.sub(r"\s+", " ", text).strip()
    return text


class ContactManager:
    def __init__(self, db_path: str = DB):
        self.db_path = db_path
        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def _init_db(self):
        """Initialize contacts table"""
        try:
            with _lock, self._connect() as conn:
                c = conn.cursor()
                c.execute(
                    """
                    CREATE TABLE IF NOT EXISTS contacts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT UNIQUE,
                        phone TEXT,
                        platform TEXT,
                        metadata TEXT
                    )
                """
                )
                conn.commit()
        except Exception as e:
            logger.exception("Failed to initialize contacts DB: %s", e)

    def add_contact(
        self, name: str, phone: str, platform: str = "whatsapp", metadata: str = "{}"
    ) -> bool:
        """
        Save or update a contact.

        NOTE:
        - We keep the original name (with emojis / caps) as-is in DB.
        - Matching will use normalized form (see _normalize_name).
        """
        name = (name or "").strip()
        phone = (phone or "").strip()
        platform = (platform or "").strip().lower()

        if not name or not phone:
            return False

        try:
            with _lock, self._connect() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                        INSERT INTO contacts (name, phone, platform, metadata)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(name) DO UPDATE SET
                        phone = excluded.phone,
                        platform = excluded.platform,
                        metadata = excluded.metadata
                    """,
                    (name, phone, platform, metadata),
                )
                conn.commit()
            logger.info("Saved contact: %s -> %s", name, phone)
            return True
        except Exception as e:
            logger.exception("add_contact failed: %s", e)
            return False

    def get_contact(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Fetch a contact by name.

        Matching strategy:
        1. Normalize input name (remove emojis/symbols, lowercase)
        2. Normalize each stored contact name and try exact normalized match
        3. If nothing matches, fallback to simple case-insensitive equality
        """
        raw = (name or "").strip()
        if not raw:
            return None

        norm_query = _normalize_name(raw)

        try:
            with _lock, self._connect() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT name, phone, platform, metadata FROM contacts"
                )
                rows = cur.fetchall()

            best_row = None

            # First pass: normalized match
            for r in rows:
                db_name = r[0] or ""
                if _normalize_name(db_name) == norm_query:
                    best_row = r
                    break

            # Second pass: simple case-insensitive fallback (if needed)
            if not best_row:
                for r in rows:
                    db_name = r[0] or ""
                    if db_name.lower().strip() == raw.lower():
                        best_row = r
                        break

            if best_row:
                return {
                    "name": best_row[0],
                    "phone": best_row[1],
                    "platform": best_row[2],
                    "metadata": best_row[3],
                }
            return None

        except Exception as e:
            logger.exception("get_contact failed: %s", e)
            return None

    def find_contact_by_phone(self, phone: str) -> Optional[Dict[str, Any]]:
        """Fetch contact by phone number (exact phone match)."""
        phone = (phone or "").strip()
        if not phone:
            return None

        try:
            with _lock, self._connect() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT name, phone, platform, metadata FROM contacts WHERE phone = ?",
                    (phone,),
                )
                row = cur.fetchone()
                if row:
                    return {
                        "name": row[0],
                        "phone": row[1],
                        "platform": row[2],
                        "metadata": row[3],
                    }
                return None
        except Exception as e:
            logger.exception("find_contact_by_phone failed: %s", e)
            return None

    def list_contacts(self) -> List[Dict[str, Any]]:
        """Get all saved contacts."""
        try:
            with _lock, self._connect() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT name, phone, platform, metadata FROM contacts ORDER BY name"
                )
                rows = cur.fetchall()
                return [
                    {
                        "name": r[0],
                        "phone": r[1],
                        "platform": r[2],
                        "metadata": r[3],
                    }
                    for r in rows
                ]
        except Exception as e:
            logger.exception("list_contacts failed: %s", e)
            return []

    def remove_contact(self, name: str) -> bool:
        """Delete a contact by name (case-insensitive, raw)."""
        name = (name or "").strip()
        if not name:
            return False
        try:
            with _lock, self._connect() as conn:
                cur = conn.cursor()
                cur.execute("DELETE FROM contacts WHERE lower(name) = lower(?)", (name,))
                conn.commit()
                return True
        except Exception as e:
            logger.exception("remove_contact failed: %s", e)
            return False

    def update_contact(
        self,
        name: str,
        phone: Optional[str] = None,
        platform: Optional[str] = None,
        metadata: Optional[str] = None,
    ) -> bool:
        """Update fields of an existing contact."""
        name = (name or "").strip()
        if not name:
            return False

        try:
            updates = []
            params: List[Any] = []

            if phone:
                updates.append("phone = ?")
                params.append(phone.strip())

            if platform:
                updates.append("platform = ?")
                params.append(platform.strip().lower())

            if metadata:
                updates.append("metadata = ?")
                params.append(metadata)

            if not updates:
                return False

            params.append(name)

            with _lock, self._connect() as conn:
                cur = conn.cursor()
                cur.execute(
                    f"UPDATE contacts SET {', '.join(updates)} WHERE lower(name) = lower(?)",
                    params,
                )
                conn.commit()
                return True

        except Exception as e:
            logger.exception("update_contact failed: %s", e)
            return False


# Global instance for easy importing
contact_manager = ContactManager()
