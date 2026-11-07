# contact_manager.py
"""
ContactManager — SQLite-backed contact store and message scheduler for Radhe.

Features:
- Safe non-locking SQLite connection contextmanager for Windows.
- Emoji- and case-insensitive name matching ("Mummy ❤️" and "mummy" both match).
- Unicode mathematical font normalisation ("𝓟𝓪𝓹𝓪" -> "Papa").
- Relationship mapping (mother, father, boss, sister, brother, friend).
- Phone number normalisation (strips spaces / dashes / leading +91 variants).
- Full CRUD: add, get, update, remove, list.
- Message Scheduling Engine: schedule WhatsApp messages for future delivery.
"""

import sqlite3
import threading
import logging
import re
import datetime
import unicodedata
from contextlib import contextmanager
from typing import Optional, Dict, Any, List, Union
from pathlib import Path
from config import CONTACTS_DB_FILE
from time_parser import parse_time

logger = logging.getLogger("Radhe_ContactManager")
logger.setLevel(logging.INFO)

DB      = str(CONTACTS_DB_FILE)
_lock   = threading.Lock()

# Relationship alias mapping
_RELATIONSHIP_ALIASES = {
    "mother":  {"mother", "mom", "mummy", "maa", "mataji", "ammi"},
    "father":  {"father", "dad", "papa", "pitaji", "abbu"},
    "brother": {"brother", "bro", "bhai", "bhaiya", "bhaiji"},
    "sister":  {"sister", "sis", "behen", "didi"},
    "boss":    {"boss", "manager", "lead", "sir", "team lead"},
    "friend":  {"friend", "dost", "yaar", "buddy"},
    "wife":    {"wife", "patni", "biwi"},
    "husband": {"husband", "pati"},
}


# ==================================================================
# HELPERS
# ==================================================================

def _normalize_name(text: str) -> str:
    """Strip emojis, symbols, fancy fonts, and lowercase for comparison."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", str(text))
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _normalize_phone(phone: str) -> str:
    """Normalise a phone number to digits-only with country code."""
    if not phone:
        return ""
    digits = re.sub(r"[^\d]", "", str(phone))
    if digits.startswith("0") and len(digits) == 11:
        digits = "91" + digits[1:]
    return digits


# ==================================================================
# CONTACT MANAGER
# ==================================================================

class ContactManager:

    def __init__(self, db_path: str = DB):
        self.db_path = str(db_path)
        self._init_db()

    # ------------------------------------------------------------------
    # DB SETUP & CONNECTION MANAGEMENT
    # ------------------------------------------------------------------

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
        try:
            with self._connection() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS contacts (
                        id              INTEGER PRIMARY KEY AUTOINCREMENT,
                        name            TEXT    UNIQUE,
                        phone           TEXT,
                        platform        TEXT    DEFAULT 'whatsapp',
                        metadata        TEXT    DEFAULT '{}',
                        relationship    TEXT    DEFAULT '',
                        secondary_phone TEXT    DEFAULT '',
                        email           TEXT    DEFAULT '',
                        notes           TEXT    DEFAULT ''
                    )
                """)

                conn.execute("""
                    CREATE TABLE IF NOT EXISTS scheduled_messages (
                        id             INTEGER PRIMARY KEY AUTOINCREMENT,
                        recipient      TEXT    NOT NULL,
                        message        TEXT    NOT NULL,
                        scheduled_time TEXT    NOT NULL,
                        status         TEXT    DEFAULT 'pending',
                        platform       TEXT    DEFAULT 'whatsapp',
                        created_at     TEXT    DEFAULT CURRENT_TIMESTAMP,
                        sent_at        TEXT
                    )
                """)

                # Safe migrations for existing contacts databases
                cur = conn.cursor()
                cur.execute("PRAGMA table_info(contacts)")
                cols = [col[1] for col in cur.fetchall()]
                for c in ["relationship", "secondary_phone", "email", "notes"]:
                    if c not in cols:
                        conn.execute(f"ALTER TABLE contacts ADD COLUMN {c} TEXT DEFAULT ''")

                conn.commit()
        except Exception as e:
            logger.exception("Failed to initialise contacts DB: %s", e)

    # ------------------------------------------------------------------
    # ADD / UPDATE
    # ------------------------------------------------------------------

    def add_contact(
        self,
        name:            str,
        phone:           str,
        platform:        str = "whatsapp",
        metadata:        str = "{}",
        relationship:    str = "",
        secondary_phone: str = "",
        email:           str = "",
        notes:           str = ""
    ) -> bool:
        """Save or update a contact with optional relationship tag and secondary details."""
        name  = (name or "").strip()
        phone = _normalize_phone(phone)
        plat  = (platform or "whatsapp").strip().lower()
        rel   = (relationship or "").strip().lower()
        sec   = _normalize_phone(secondary_phone)

        if not name or not phone:
            logger.warning("add_contact: name or phone is empty.")
            return False

        try:
            with self._connection() as conn:
                conn.execute("""
                    INSERT INTO contacts (name, phone, platform, metadata, relationship, secondary_phone, email, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(name) DO UPDATE SET
                        phone           = excluded.phone,
                        platform        = excluded.platform,
                        metadata        = excluded.metadata,
                        relationship    = excluded.relationship,
                        secondary_phone = excluded.secondary_phone,
                        email           = excluded.email,
                        notes           = excluded.notes
                """, (name, phone, plat, metadata, rel, sec, email.strip(), notes.strip()))
                conn.commit()
            logger.info("Saved contact: %s → %s (Relationship: %s)", name, phone, rel or "none")
            return True
        except Exception as e:
            logger.exception("add_contact failed: %s", e)
            return False

    # ------------------------------------------------------------------
    # GET (MULTI-PASS MATCHING + RELATIONSHIP LOOKUP)
    # ------------------------------------------------------------------

    def get_contact(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Look up a contact by name or relationship using a multi-pass strategy:
        Pass 1 — exact normalised match ("mummy" finds "Mummy ❤️")
        Pass 2 — raw case-insensitive
        Pass 3 — relationship alias match ("mom" or "mother" finds contact tagged as mother)
        Pass 4 — substring / fuzzy partial match
        """
        raw = (name or "").strip()
        if not raw:
            return None

        norm_query = _normalize_name(raw)

        try:
            with self._connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT name, phone, platform, metadata, relationship, secondary_phone, email, notes
                    FROM contacts
                """)
                rows = cur.fetchall()

            # Pass 1: normalised exact name match
            for r in rows:
                if _normalize_name(r[0]) == norm_query:
                    return self._row_to_dict(r)

            # Pass 2: raw case-insensitive name match
            for r in rows:
                if (r[0] or "").lower().strip() == raw.lower():
                    return self._row_to_dict(r)

            # Pass 3: Relationship alias lookup
            query_lower = raw.lower()
            for canon_rel, aliases in _RELATIONSHIP_ALIASES.items():
                if query_lower in aliases:
                    for r in rows:
                        stored_rel = (r[4] or "").lower().strip()
                        if stored_rel and (stored_rel in aliases or stored_rel == canon_rel):
                            logger.info("Resolved contact '%s' via relationship '%s'", r[0], raw)
                            return self._row_to_dict(r)

            # Pass 4: Partial substring match
            for r in rows:
                if norm_query and norm_query in _normalize_name(r[0]):
                    return self._row_to_dict(r)

            return None
        except Exception as e:
            logger.exception("get_contact failed: %s", e)
            return None

    def get_contact_by_relationship(self, relationship: str) -> Optional[Dict[str, Any]]:
        """Direct lookup by relationship (e.g. 'mother', 'boss')."""
        return self.get_contact(relationship)

    def find_contact_by_phone(self, phone: str) -> Optional[Dict[str, Any]]:
        """Look up a contact by primary or secondary phone number."""
        norm = _normalize_phone(phone)
        if not norm:
            return None
        try:
            with self._connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT name, phone, platform, metadata, relationship, secondary_phone, email, notes
                    FROM contacts
                    WHERE phone = ? OR secondary_phone = ?
                """, (norm, norm))
                row = cur.fetchone()
                return self._row_to_dict(row) if row else None
        except Exception as e:
            logger.exception("find_contact_by_phone failed: %s", e)
            return None

    # ------------------------------------------------------------------
    # LIST & SEARCH
    # ------------------------------------------------------------------

    def list_contacts(self) -> List[Dict[str, Any]]:
        """Return all saved contacts sorted alphabetically by name."""
        try:
            with self._connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT name, phone, platform, metadata, relationship, secondary_phone, email, notes
                    FROM contacts ORDER BY name ASC
                """)
                return [self._row_to_dict(r) for r in cur.fetchall()]
        except Exception as e:
            logger.exception("list_contacts failed: %s", e)
            return []

    # ------------------------------------------------------------------
    # UPDATE & REMOVE
    # ------------------------------------------------------------------

    def update_contact(
        self,
        name:            str,
        phone:           Optional[str] = None,
        platform:        Optional[str] = None,
        metadata:        Optional[str] = None,
        relationship:    Optional[str] = None,
        secondary_phone: Optional[str] = None,
        email:           Optional[str] = None,
        notes:           Optional[str] = None,
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
        if relationship is not None:
            updates.append("relationship = ?")
            params.append(relationship.strip().lower())
        if secondary_phone is not None:
            updates.append("secondary_phone = ?")
            params.append(_normalize_phone(secondary_phone))
        if email is not None:
            updates.append("email = ?")
            params.append(email.strip())
        if notes is not None:
            updates.append("notes = ?")
            params.append(notes.strip())

        if not updates:
            return False

        params.append(name)
        try:
            with self._connection() as conn:
                cur = conn.execute(
                    f"UPDATE contacts SET {', '.join(updates)} WHERE lower(name) = lower(?)",
                    params
                )
                conn.commit()
                return cur.rowcount > 0
        except Exception as e:
            logger.exception("update_contact failed: %s", e)
            return False

    def remove_contact(self, name: str) -> bool:
        """Delete a contact by name."""
        raw = (name or "").strip()
        if not raw:
            return False

        norm = _normalize_name(raw)
        try:
            with self._connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT name FROM contacts")
                rows = cur.fetchall()

                target_name = None
                for (stored_name,) in rows:
                    if _normalize_name(stored_name) == norm:
                        target_name = stored_name
                        break

                if not target_name:
                    return False

                cur.execute("DELETE FROM contacts WHERE name = ?", (target_name,))
                conn.commit()
                logger.info("Removed contact: %s", target_name)
                return True
        except Exception as e:
            logger.exception("remove_contact failed: %s", e)
            return False

    # ------------------------------------------------------------------
    # MESSAGE SCHEDULING ENGINE (Phase 6 Deliverable)
    # ------------------------------------------------------------------

    def schedule_message(
        self,
        recipient: str,
        message: str,
        time_str: str,
        platform: str = "whatsapp"
    ) -> int:
        """Schedule a message to be sent at a future time."""
        recipient = (recipient or "").strip()
        message   = (message or "").strip()
        time_str  = (time_str or "").strip()

        if not recipient or not message or not time_str:
            logger.warning("schedule_message: missing required arguments.")
            return 0

        dt = parse_time(time_str)
        if not dt:
            logger.error("Could not parse schedule time: '%s'", time_str)
            return 0

        iso_time = dt.isoformat()
        try:
            with self._connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO scheduled_messages (recipient, message, scheduled_time, status, platform)
                    VALUES (?, ?, ?, 'pending', ?)
                """, (recipient, message, iso_time, platform))
                msg_id = cur.lastrowid
                conn.commit()

            logger.info("Scheduled message id=%d to '%s' at %s", msg_id, recipient, iso_time)
            return msg_id
        except Exception as e:
            logger.exception("schedule_message failed: %s", e)
            return 0

    def list_scheduled_messages(self, status: str = "pending") -> List[Dict[str, Any]]:
        """List scheduled messages filtered by status."""
        try:
            with self._connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT id, recipient, message, scheduled_time, status, platform, created_at, sent_at
                    FROM scheduled_messages
                    WHERE status = ?
                    ORDER BY scheduled_time ASC
                """, (status,))
                rows = cur.fetchall()

            messages = []
            for r in rows:
                messages.append({
                    "id":             r[0],
                    "recipient":      r[1],
                    "message":        r[2],
                    "scheduled_time": r[3],
                    "status":         r[4],
                    "platform":       r[5],
                    "created_at":     r[6],
                    "sent_at":        r[7]
                })
            return messages
        except Exception as e:
            logger.exception("list_scheduled_messages failed: %s", e)
            return []

    def cancel_scheduled_message(self, identifier: Any) -> bool:
        """Cancel a pending scheduled message by ID or recipient substring."""
        try:
            with self._connection() as conn:
                cur = conn.cursor()
                if isinstance(identifier, int) or (isinstance(identifier, str) and identifier.isdigit()):
                    cur.execute("""
                        UPDATE scheduled_messages SET status = 'cancelled'
                        WHERE id = ? AND status = 'pending'
                    """, (int(identifier),))
                else:
                    kw = str(identifier).strip().lower()
                    cur.execute("""
                        UPDATE scheduled_messages SET status = 'cancelled'
                        WHERE LOWER(recipient) LIKE ? AND status = 'pending'
                    """, (f"%{kw}%",))

                changed = cur.rowcount > 0
                conn.commit()
                return changed
        except Exception as e:
            logger.exception("cancel_scheduled_message failed: %s", e)
            return False

    def get_due_messages(self) -> List[Dict[str, Any]]:
        """Retrieve pending messages that are scheduled on or before current time."""
        now_iso = datetime.datetime.now().isoformat()
        try:
            with self._connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT id, recipient, message, scheduled_time, platform
                    FROM scheduled_messages
                    WHERE status = 'pending' AND scheduled_time <= ?
                """, (now_iso,))
                rows = cur.fetchall()

            due = []
            for r in rows:
                due.append({
                    "id":             r[0],
                    "recipient":      r[1],
                    "message":        r[2],
                    "scheduled_time": r[3],
                    "platform":       r[4]
                })
            return due
        except Exception as e:
            logger.exception("get_due_messages failed: %s", e)
            return []

    def mark_message_sent(self, msg_id: int) -> bool:
        """Mark a scheduled message as sent."""
        now_iso = datetime.datetime.now().isoformat()
        try:
            with self._connection() as conn:
                conn.execute("""
                    UPDATE scheduled_messages SET status = 'sent', sent_at = ?
                    WHERE id = ?
                """, (now_iso, msg_id))
                conn.commit()
            return True
        except Exception as e:
            logger.exception("mark_message_sent failed: %s", e)
            return False

    # ------------------------------------------------------------------
    # ROW PARSER
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_dict(row) -> Dict[str, Any]:
        return {
            "name":            row[0],
            "phone":           row[1],
            "platform":        row[2],
            "metadata":        row[3],
            "relationship":    row[4] if len(row) > 4 else "",
            "secondary_phone": row[5] if len(row) > 5 else "",
            "email":           row[6] if len(row) > 6 else "",
            "notes":           row[7] if len(row) > 7 else ""
        }


# ── Global instance ───────────────────────────────────────────────────
contact_manager = ContactManager()
