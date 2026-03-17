"""
time_parser.py

Centralized time parser for Radhe.

Returns a timezone-naive datetime in local time.

Supports:
- now
- in 10 minutes
- after 2 hours
- tomorrow
- day after tomorrow
- next monday
- 6 pm
- 6:30
- 18:30
"""

import re
import datetime
from datetime import timedelta


def parse_time(text: str):
    if not text:
        return None

    text = text.lower().strip()
    now = datetime.datetime.now()

    if text in ("now", "right now"):
        return now

    # relative time
    m = re.match(r"(?:in|after)\s+(\d+)\s*(second|seconds|minute|minutes|hour|hours|day|days)", text)
    if m:
        val = int(m.group(1))
        unit = m.group(2)

        if unit.startswith("second"):
            return now + timedelta(seconds=val)

        if unit.startswith("minute"):
            return now + timedelta(minutes=val)

        if unit.startswith("hour"):
            return now + timedelta(hours=val)

        if unit.startswith("day"):
            return now + timedelta(days=val)

    # tomorrow
    if "day after tomorrow" in text:
        return (now + timedelta(days=2)).replace(hour=9, minute=0, second=0, microsecond=0)

    if "tomorrow" in text:
        return (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)

    # next weekday
    m = re.search(r"next (\w+)", text)
    if m:
        weekdays = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]

        if m.group(1) in weekdays:
            weekday = weekdays.index(m.group(1))
            days_ahead = (weekday - now.weekday() + 7) % 7
            days_ahead = days_ahead if days_ahead != 0 else 7

            return (now + timedelta(days=days_ahead)).replace(
                hour=9, minute=0, second=0, microsecond=0
            )

    # absolute time
    m = re.search(r"(\d{1,2})(?::|\.?)(\d{2})?\s*(am|pm)?", text)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        ampm = m.group(3)

        if ampm:
            ampm = ampm.lower()

            if ampm == "pm" and hour < 12:
                hour += 12

            if ampm == "am" and hour == 12:
                hour = 0

        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

        if candidate <= now:
            candidate += timedelta(days=1)

        return candidate

    # fallback HH:MM
    try:
        candidate = datetime.datetime.strptime(text, "%H:%M")
        candidate = candidate.replace(year=now.year, month=now.month, day=now.day)

        if candidate <= now:
            candidate += timedelta(days=1)

        return candidate

    except Exception:
        return None