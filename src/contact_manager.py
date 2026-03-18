# contact_manager.py
"""
ContactManager — SQLite-backed contact store for Radhe.

Features:
- Emoji- and case-insensitive name matching
  ("Mummy ❤️" and "mummy" both resolve to the same contact)
- Fuzzy partial matching (say "mum" and it finds "Mummy ❤️")
- Phone number normalisation (strips spaces / dashes / leading +91 variants)
- Thread-safe with a module-level lock
- Full CRUD: add, get, update, remove, list

Fixes applied vs previous version:
- remove_contact now uses _normalize_name for consistent emoji-safe deletion
- Added partial/fuzzy name matching so "mum" finds "Mummy ❤️"
- Phone normalisation helper added
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
DB      = "data/contacts.db"
_lock   = threading.Lock()


# ==================================================================
# HELPERS
# ==================================================================

def _normalize_name(text: str) -> str:
    """
    Strip emojis / symbols and lowercase for comparison.
    "Mummy ❤️🥰"  → "mummy"
    "Shikha_123!!" → "shikha 123"
    """
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _normalize_phone(phone: str) -> str:
    """
    Normalise a phone number to digits-only with country code.
    "+91 98765-43210" → "919876543210"
    "09876543210"     → "919876543210"  (assumes India if starts with 0)
    """
    if not phone:
        return ""
    digits = re.sub(r"[^\d]", "", phone)  # keep digits only
    if digits.startswith("0") and len(digits) == 11:
        digits = "91" + digits[1:]         # Indian local → international
    return digits


# ==================================================================
# CONTACT MANAGER
# ==================================================================

class ContactManager:

    def __init__(self, db_path: str = DB):
        self.db_path = db_path
        self._init_db()

    # ------------------------------------------------------------------
    # DB SETUP
    # ------------------------------------------------------------------

    def _connect(self):
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def _init_db(self):
        try:
            with _lock, self._connect() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS contacts (
                        id       INTEGER PRIMARY KEY AUTOINCREMENT,
                        name     TEXT    UNIQUE,
                        phone    TEXT,
                        platform TEXT    DEFAULT 'whatsapp',
                        metadata TEXT    DEFAULT '{}'
                    )
                """)
                conn.commit()
        except Exception as e:
            logger.exception("Failed to initialise contacts DB: %s", e)

    # ------------------------------------------------------------------
    # ADD / UPDATE
    # ------------------------------------------------------------------

    def add_contact(
        self,
        name:     str,
        phone:    str,
        platform: str = "whatsapp",
        metadata: str = "{}"
    ) -> bool:
        """
        Save or update a contact.
        Keeps the original name (with emojis / caps) in the DB.
        Normalises the phone number before saving.
        """
        name     = (name     or "").strip()
        phone    = _normalize_phone(phone)
        platform = (platform or "whatsapp").strip().lower()

        if not name or not phone:
            logger.warning("add_contact: name or phone is empty.")
            return False

        try:
            with _lock, self._connect() as conn:
                conn.execute("""
                    INSERT INTO contacts (name, phone, platform, metadata)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(name) DO UPDATE SET
                        phone    = excluded.phone,
                        platform = excluded.platform,
                        metadata = excluded.metadata
                """, (name, phone, platform, metadata))
                conn.commit()
            logger.info("Saved contact: %s → %s", name, phone)
            return True
        except Exception as e:
            logger.exception("add_contact failed: %s", e)
            return False

    # ------------------------------------------------------------------
    # GET (single contact)
    # ------------------------------------------------------------------

    def get_contact(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Look up a contact by name using a three-pass strategy:

        Pass 1 — exact normalised match   ("mummy" finds "Mummy ❤️")
        Pass 2 — raw case-insensitive     ("MUMMY" finds "Mummy")
        Pass 3 — partial/fuzzy match      ("mum"   finds "Mummy ❤️")
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

            # Pass 1: normalised exact
            for r in rows:
                if _normalize_name(r[0]) == norm_query:
                    return self._row_to_dict(r)

            # Pass 2: raw case-insensitive
            for r in rows:
                if (r[0] or "").lower().strip() == raw.lower():
                    return self._row_to_dict(r)

            # Pass 3: partial match (query is a substring of stored name)
            for r in rows:
                if norm_query and norm_query in _normalize_name(r[0]):
                    return self._row_to_dict(r)

            return None

        except Exception as e:
            logger.exception("get_contact failed: %s", e)
            return None

    # ------------------------------------------------------------------
    # GET BY PHONE
    # ------------------------------------------------------------------

    def find_contact_by_phone(self, phone: str) -> Optional[Dict[str, Any]]:
        """Look up a contact by normalised phone number."""
        norm = _normalize_phone(phone)
        if not norm:
            return None
        try:
            with _lock, self._connect() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT name, phone, platform, metadata "
                    "FROM contacts WHERE phone = ?",
                    (norm,)
                )
                row = cur.fetchone()
                return self._row_to_dict(row) if row else None
        except Exception as e:
            logger.exception("find_contact_by_phone failed: %s", e)
            return None

    # ------------------------------------------------------------------
    # LIST
    # ------------------------------------------------------------------

    def list_contacts(self) -> List[Dict[str, Any]]:
        """Return all saved contacts sorted by name."""
        try:
            with _lock, self._connect() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT name, phone, platform, metadata "
                    "FROM contacts ORDER BY name"
                )
                return [self._row_to_dict(r) for r in cur.fetchall()]
        except Exception as e:
            logger.exception("list_contacts failed: %s", e)
            return []

    # ------------------------------------------------------------------
    # UPDATE
    # ------------------------------------------------------------------

    def update_contact(
        self,
        name:     str,
        phone:    Optional[str] = None,
        platform: Optional[str] = None,
        metadata: Optional[str] = None,
    ) -> bool:
        """Update one or more fields of an existing contact."""
        name = (name or "").strip()
        if not name:
            return False

        updates: List[str] = []
        params:  List[Any] = []

        if phone is not None:
            updates.append("phone = ?")
            params.append(_normalize_phone(phone))

        if platform is not None:
            updates.append("platform = ?")
            params.append(platform.strip().lower())

        if metadata is not None:
            updates.append("metadata = ?")
            params.append(metadata)

        if not updates:
            return False

        params.append(name)

        try:
            with _lock, self._connect() as conn:
                conn.execute(
                    f"UPDATE contacts SET {', '.join(updates)} "
                    f"WHERE lower(name) = lower(?)",
                    params
                )
                conn.commit()
            return True
        except Exception as e:
            logger.exception("update_contact failed: %s", e)
            return False

    # ------------------------------------------------------------------
    # REMOVE
    # ------------------------------------------------------------------

    def remove_contact(self, name: str) -> bool:
        """
        Delete a contact by name.
        Uses _normalize_name for consistent emoji-safe matching
        (fixes previous version that used plain lower() and missed emoji names).
        """
        raw = (name or "").strip()
        if not raw:
            return False

        norm = _normalize_name(raw)

        try:
            with _lock, self._connect() as conn:
                cur = conn.cursor()

                # Fetch all to find the canonical stored name
                cur.execute("SELECT name FROM contacts")
                rows = cur.fetchall()

                target_name = None
                for (stored_name,) in rows:
                    if _normalize_name(stored_name) == norm:
                        target_name = stored_name
                        break

                if not target_name:
                    logger.warning("remove_contact: '%s' not found.", name)
                    return False

                cur.execute("DELETE FROM contacts WHERE name = ?", (target_name,))
                conn.commit()
                logger.info("Removed contact: %s", target_name)
                return True

        except Exception as e:
            logger.exception("remove_contact failed: %s", e)
            return False

    # ------------------------------------------------------------------
    # HELPER
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_dict(row) -> Dict[str, Any]:
        return {
            "name":     row[0],
            "phone":    row[1],
            "platform": row[2],
            "metadata": row[3],
        }


# ── Global instance ───────────────────────────────────────────────────
contact_manager = ContactManager()