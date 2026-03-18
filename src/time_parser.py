# time_parser.py
"""
Centralised time parser for Radhe.

Strategy:
1. Try hand-written regex rules (fast, offline, covers common patterns).
2. Fall back to `dateparser` library (handles complex phrasing).

Supported inputs:
  now, right now
  in 10 minutes / after 2 hours / in 3 days
  tomorrow / day after tomorrow
  next monday
  6 pm / 6:30 / 18:30
  at 9am tomorrow
  9 baje / kal subah 9 baje  (basic Hindi romanised)

Returns: datetime (timezone-naive, local time) or None if unparseable.
"""

import re
import datetime
from datetime import timedelta
import logging

logger = logging.getLogger("Radhe_TimeParser")

try:
    import dateparser
    DATEPARSER_AVAILABLE = True
except ImportError:
    dateparser = None
    DATEPARSER_AVAILABLE = False
    logger.warning("dateparser not installed. Run: pip install dateparser")

_WEEKDAYS = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]


def parse_time(text: str) -> datetime.datetime | None:
    """
    Parse a natural language time string and return a datetime.
    Returns None if the string cannot be interpreted.
    """
    if not text:
        return None

    original = text
    text     = text.lower().strip()
    now      = datetime.datetime.now()

    # ── Immediate ─────────────────────────────────────────────────────
    if text in ("now", "right now", "abhi", "abhi abhi"):
        return now

    # ── Relative: "in X unit" / "after X unit" ────────────────────────
    m = re.match(
        r"(?:in|after|baad)\s+(\d+)\s*"
        r"(second|seconds|sec|minute|minutes|min|hour|hours|hr|day|days|din)s?",
        text
    )
    if m:
        val  = int(m.group(1))
        unit = m.group(2)
        if unit.startswith(("sec",)):
            return now + timedelta(seconds=val)
        if unit.startswith(("min",)):
            return now + timedelta(minutes=val)
        if unit.startswith(("hour","hr")):
            return now + timedelta(hours=val)
        if unit.startswith(("day","din")):
            return now + timedelta(days=val)

    # ── Day offsets ───────────────────────────────────────────────────
    if "day after tomorrow" in text or "parso" in text:
        return (now + timedelta(days=2)).replace(hour=9, minute=0, second=0, microsecond=0)

    if "tomorrow" in text or "kal" in text:
        base = (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
        # Check for time hint after "tomorrow"
        time_part = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", text)
        if time_part:
            base = _apply_time_hint(base, time_part)
        return base

    # ── Next weekday ──────────────────────────────────────────────────
    m = re.search(r"next\s+(\w+)", text)
    if m and m.group(1) in _WEEKDAYS:
        weekday    = _WEEKDAYS.index(m.group(1))
        days_ahead = (weekday - now.weekday() + 7) % 7 or 7
        return (now + timedelta(days=days_ahead)).replace(
            hour=9, minute=0, second=0, microsecond=0
        )

    # ── Absolute time: "6 pm", "6:30", "18:30", "at 9am" ─────────────
    m = re.search(r"(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", text)
    if m:
        candidate = _build_candidate(now, m)
        if candidate:
            return candidate

    # ── HH:MM fallback ────────────────────────────────────────────────
    try:
        t = datetime.datetime.strptime(text, "%H:%M")
        candidate = t.replace(year=now.year, month=now.month, day=now.day,
                               second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate
    except Exception:
        pass

    # ── dateparser fallback (handles complex / locale-aware phrasing) ──
    if DATEPARSER_AVAILABLE:
        try:
            result = dateparser.parse(
                original,
                settings={
                    "PREFER_DATES_FROM": "future",
                    "RETURN_AS_TIMEZONE_AWARE": False,
                }
            )
            if result:
                # Reject results in the past
                if result > now:
                    return result
        except Exception as e:
            logger.debug("dateparser failed: %s", e)

    logger.warning("Could not parse time from: '%s'", original)
    return None


# ── Helpers ───────────────────────────────────────────────────────────

def _build_candidate(
    now: datetime.datetime,
    m: re.Match
) -> datetime.datetime | None:
    try:
        hour   = int(m.group(1))
        minute = int(m.group(2) or 0)
        ampm   = (m.group(3) or "").lower()

        if ampm == "pm" and hour < 12:
            hour += 12
        if ampm == "am" and hour == 12:
            hour = 0

        if hour > 23 or minute > 59:
            return None

        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate
    except Exception:
        return None


def _apply_time_hint(
    base: datetime.datetime,
    m: re.Match
) -> datetime.datetime:
    try:
        hour   = int(m.group(1))
        minute = int(m.group(2) or 0)
        ampm   = (m.group(3) or "").lower()

        if ampm == "pm" and hour < 12:
            hour += 12
        if ampm == "am" and hour == 12:
            hour = 0

        return base.replace(hour=hour, minute=minute, second=0, microsecond=0)
    except Exception:
        return base