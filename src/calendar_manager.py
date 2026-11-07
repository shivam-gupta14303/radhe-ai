# calendar_manager.py
"""
CalendarManager — Unified Google Calendar and Local Offline-First Calendar for Radhe.

Features:
- Offline-first SQLite local store: calendar always works offline or without Google keys.
- Optional Google Calendar OAuth 2.0 sync via official google-api-python-client.
- Automatic interval-based conflict detection (A_start < B_end and A_end > B_start).
- Smart default duration (1 hour if end time omitted).
- Agenda generator for morning briefings and daily schedules.
"""

import sqlite3
import threading
import datetime
import logging
import json
from contextlib import contextmanager
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from time_parser import parse_time

logger = logging.getLogger("Radhe_Calendar")
logger.setLevel(logging.INFO)

DB_PATH = Path("data/calendar.db")
_lock   = threading.Lock()
SCOPES  = ["https://www.googleapis.com/auth/calendar"]


def _parse_event_time(val: Any) -> Optional[datetime.datetime]:
    if isinstance(val, datetime.datetime):
        return val
    s = str(val).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(s, fmt)
        except Exception:
            pass
    try:
        return datetime.datetime.fromisoformat(s)
    except Exception:
        pass
    return parse_time(s)


class CalendarManager:

    def __init__(self, db_path: Path = DB_PATH, token_path: Path = Path("data/calendar_token.json")):
        self.db_path    = Path(db_path)
        self.token_path = Path(token_path)
        self.service    = None
        self._init_db()
        self._try_init_google_service()

    # ==================================================================
    # DB SETUP & CONNECTION MANAGEMENT
    # ==================================================================

    @contextmanager
    def _connection(self):
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        try:
            with _lock, conn:
                yield conn
        finally:
            conn.close()

    def _init_db(self):
        """Initialize the local calendar_events table."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS calendar_events (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    google_id   TEXT    UNIQUE,
                    title       TEXT    NOT NULL,
                    start_time  TEXT    NOT NULL,
                    end_time    TEXT    NOT NULL,
                    location    TEXT    DEFAULT '',
                    description TEXT    DEFAULT '',
                    attendees   TEXT    DEFAULT '',
                    status      TEXT    DEFAULT 'confirmed',
                    is_synced   INTEGER DEFAULT 0,
                    created_at  TEXT    DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    # ==================================================================
    # GOOGLE CALENDAR AUTH & CONNECTION
    # ==================================================================

    def _try_init_google_service(self):
        """Silently initialize Google Calendar client if token exists."""
        if not self.token_path.exists():
            return
        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build

            creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)
            if creds and creds.valid:
                self.service = build("calendar", "v3", credentials=creds)
                logger.info("Google Calendar client connected.")
        except Exception as e:
            logger.debug("Google Calendar silent init skipped: %s", e)

    def is_connected(self) -> bool:
        """Return True if active Google Calendar connection exists."""
        return self.service is not None

    def connect_google(self, credentials_path: Optional[str] = None) -> Tuple[bool, str]:
        """
        Authenticate with Google Calendar via OAuth flow.
        Looks for credentials in credentials_path, data/credentials.json, or root.
        """
        cred_candidates = [
            Path(credentials_path) if credentials_path else None,
            Path("data/credentials.json"),
            Path("credentials.json"),
        ]
        chosen = None
        for c in cred_candidates:
            if c and c.exists():
                chosen = c
                break

        if not chosen:
            return False, "Google credentials file not found. Place credentials.json in data/ folder."

        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build

            flow = InstalledAppFlow.from_client_secrets_file(str(chosen), SCOPES)
            creds = flow.run_local_server(port=0)

            self.token_path.parent.mkdir(parents=True, exist_ok=True)
            self.token_path.write_text(creds.to_json(), encoding="utf-8")
            self.service = build("calendar", "v3", credentials=creds)
            logger.info("Google Calendar connected successfully.")
            return True, "Google Calendar connected and authorized."
        except Exception as e:
            logger.exception("Google Calendar OAuth error: %s", e)
            return False, f"Connection failed: {e}"

    # ==================================================================
    # CONFLICT DETECTION (Phase 4 Deliverable)
    # ==================================================================

    def detect_conflicts(
        self,
        start_iso: str,
        end_iso: str,
        exclude_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Detect overlapping calendar events.
        Interval condition: existing.start < new.end AND existing.end > new.start
        """
        try:
            with self._connection() as conn:
                cur = conn.cursor()
                sql = """
                    SELECT id, title, start_time, end_time, location
                    FROM calendar_events
                    WHERE status = 'confirmed'
                      AND start_time < ? 
                      AND end_time > ?
                """
                params: List[Any] = [end_iso, start_iso]
                if exclude_id:
                    sql += " AND id != ?"
                    params.append(exclude_id)

                cur.execute(sql, params)
                rows = cur.fetchall()

            conflicts = []
            for r in rows:
                conflicts.append({
                    "id": r[0],
                    "title": r[1],
                    "start_time": r[2],
                    "end_time": r[3],
                    "location": r[4]
                })
            return conflicts
        except Exception as e:
            logger.exception("Conflict detection error: %s", e)
            return []

    # ==================================================================
    # EVENT CRUD
    # ==================================================================

    def create_event(
        self,
        title: str,
        start_time: str,
        end_time: Optional[str] = None,
        location: str = "",
        description: str = "",
        attendees: Optional[List[str]] = None,
        check_conflicts: bool = True
    ) -> Dict[str, Any]:
        """
        Create a new calendar event with automatic conflict detection.
        Defaults to 1 hour duration if end_time is not provided.
        """
        title = (title or "").strip()
        if not title:
            return {"success": False, "error": "Event title is required."}

        # Parse start time
        start_dt = _parse_event_time(start_time)
        if not start_dt:
            return {"success": False, "error": f"Could not parse start time: '{start_time}'."}

        # Parse or default end time (1 hour later)
        if end_time:
            end_dt = _parse_event_time(end_time)
            if not end_dt or end_dt <= start_dt:
                end_dt = start_dt + datetime.timedelta(hours=1)
        else:
            end_dt = start_dt + datetime.timedelta(hours=1)

        start_iso = start_dt.isoformat()
        end_iso   = end_dt.isoformat()

        # Conflict detection
        conflicts = []
        if check_conflicts:
            conflicts = self.detect_conflicts(start_iso, end_iso)

        att_str = json.dumps(attendees or [])

        # 1. Save to local SQLite
        google_id = None
        is_synced = 0
        try:
            with self._connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO calendar_events 
                    (title, start_time, end_time, location, description, attendees, status, is_synced)
                    VALUES (?, ?, ?, ?, ?, ?, 'confirmed', ?)
                """, (title, start_iso, end_iso, location.strip(), description.strip(), att_str, is_synced))
                local_id = cur.lastrowid
                conn.commit()
        except Exception as e:
            logger.exception("Failed to insert event into local db: %s", e)
            return {"success": False, "error": f"Database error: {e}"}

        # 2. Sync to Google Calendar if connected
        if self.service:
            try:
                g_event = {
                    "summary": title,
                    "location": location,
                    "description": description,
                    "start": {"dateTime": start_iso, "timeZone": "UTC"},
                    "end": {"dateTime": end_iso, "timeZone": "UTC"},
                }
                if attendees:
                    g_event["attendees"] = [{"email": a} for a in attendees]

                created = self.service.events().insert(calendarId="primary", body=g_event).execute()
                google_id = created.get("id")
                with self._connection() as conn:
                    conn.execute("UPDATE calendar_events SET google_id = ?, is_synced = 1 WHERE id = ?", (google_id, local_id))
                    conn.commit()
                logger.info("Event synced to Google Calendar: %s", google_id)
            except Exception as e:
                logger.warning("Google Calendar online sync failed: %s", e)

        event_data = {
            "id": local_id,
            "google_id": google_id,
            "title": title,
            "start_time": start_iso,
            "end_time": end_iso,
            "location": location,
            "description": description,
            "has_conflict": len(conflicts) > 0,
            "conflicts": conflicts
        }

        logger.info("Calendar event created: '%s' (%s to %s)", title, start_iso, end_iso)
        return {"success": True, "event": event_data, "conflicts": conflicts}

    def get_events(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 15
    ) -> List[Dict[str, Any]]:
        """Retrieve calendar events ordered chronologically."""
        try:
            with self._connection() as conn:
                cur = conn.cursor()
                clauses = ["status = 'confirmed'"]
                params: List[Any] = []

                if start_date:
                    dt_start = _parse_event_time(start_date)
                    if dt_start:
                        clauses.append("start_time >= ?")
                        params.append(dt_start.isoformat())

                if end_date:
                    dt_end = _parse_event_time(end_date)
                    if dt_end:
                        clauses.append("start_time <= ?")
                        params.append(dt_end.isoformat())

                sql = f"""
                    SELECT id, google_id, title, start_time, end_time, location, description, attendees
                    FROM calendar_events
                    WHERE {' AND '.join(clauses)}
                    ORDER BY start_time ASC
                    LIMIT ?
                """
                params.append(limit)
                cur.execute(sql, params)
                rows = cur.fetchall()

            events = []
            for r in rows:
                events.append({
                    "id": r[0],
                    "google_id": r[1],
                    "title": r[2],
                    "start_time": r[3],
                    "end_time": r[4],
                    "location": r[5],
                    "description": r[6],
                    "attendees": json.loads(r[7] or "[]")
                })
            return events
        except Exception as e:
            logger.exception("get_events error: %s", e)
            return []

    def get_today_agenda(self) -> List[Dict[str, Any]]:
        """Return all confirmed events occurring today."""
        now = datetime.datetime.now()
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        end_of_day   = now.replace(hour=23, minute=59, second=59, microsecond=999999).isoformat()

        try:
            with self._connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT id, google_id, title, start_time, end_time, location, description
                    FROM calendar_events
                    WHERE status = 'confirmed'
                      AND start_time >= ? AND start_time <= ?
                    ORDER BY start_time ASC
                """, (start_of_day, end_of_day))
                rows = cur.fetchall()

            agenda = []
            for r in rows:
                agenda.append({
                    "id": r[0],
                    "google_id": r[1],
                    "title": r[2],
                    "start_time": r[3],
                    "end_time": r[4],
                    "location": r[5],
                    "description": r[6]
                })
            return agenda
        except Exception as e:
            logger.exception("get_today_agenda error: %s", e)
            return []

    def delete_event(self, identifier: Any) -> bool:
        """Cancel an event by ID or title substring."""
        try:
            with self._connection() as conn:
                cur = conn.cursor()
                if isinstance(identifier, int) or (isinstance(identifier, str) and identifier.isdigit()):
                    cur.execute("UPDATE calendar_events SET status = 'cancelled' WHERE id = ?", (int(identifier),))
                else:
                    kw = str(identifier).strip().lower()
                    cur.execute("""
                        UPDATE calendar_events SET status = 'cancelled'
                        WHERE id IN (
                            SELECT id FROM calendar_events 
                            WHERE LOWER(title) LIKE ? AND status = 'confirmed' 
                            LIMIT 1
                        )
                    """, (f"%{kw}%",))

                changed = cur.rowcount > 0
                conn.commit()
                return changed
        except Exception as e:
            logger.exception("delete_event failed: %s", e)
            return False

    def format_agenda_text(self, events: Optional[List[Dict[str, Any]]] = None, lang: str = "en") -> str:
        """Format an agenda list into a clean, spoken or readable string."""
        ev_list = events if events is not None else self.get_today_agenda()
        if not ev_list:
            if lang == "hi":
                return "Aaj aapka schedule bilkul khaali hai, koi meeting nahi hai."
            return "You have no scheduled events for today."

        items = []
        for ev in ev_list:
            try:
                dt = datetime.datetime.fromisoformat(ev["start_time"])
                t_str = dt.strftime("%I:%M %p")
            except Exception:
                t_str = ev["start_time"]
            loc = f" at {ev['location']}" if ev.get("location") else ""
            items.append(f"• {ev['title']} at {t_str}{loc}")

        if lang == "hi":
            return f"Aaj aapke {len(ev_list)} events hain:\n" + "\n".join(items)
        return f"Here is your agenda ({len(ev_list)} events):\n" + "\n".join(items)


# ── Global singleton ───────────────────────────────────────────────────
calendar_manager = CalendarManager()
