# utilities.py
"""
UtilityManager for Radhe.

Provides:
- get_time() / get_date()
- set_timer(duration)
- start_stopwatch() / stop_stopwatch()
- get_weather() placeholder

Improvements vs previous version:
- get_time() / get_date() return human-friendly strings.
- Timer speaks remaining time warning at halfway point.
- Multiple named stopwatches supported.
"""

import time
import datetime
import threading
import logging

logger = logging.getLogger("Radhe_Utilities")
logger.setLevel(logging.INFO)


class UtilityManager:

    def __init__(self):
        self._timers:      list  = []
        self._stopwatches: dict  = {}
        self._speak_fn             = None   # injected lazily

    def _speak(self, text: str):
        """Lazy-import speak to avoid circular import at module level."""
        if self._speak_fn is None:
            try:
                from speech import speak
                self._speak_fn = speak
            except Exception:
                self._speak_fn = lambda t: logger.info("TTS: %s", t)
        try:
            self._speak_fn(text)
        except Exception as e:
            logger.warning("speak failed in utility: %s", e)

    # ==================================================================
    # TIME / DATE
    # ==================================================================

    def get_time(self) -> str:
        now = datetime.datetime.now()
        return now.strftime("The time is %I:%M %p")

    def get_date(self) -> str:
        now = datetime.datetime.now()
        return now.strftime("Today is %A, %B %d, %Y")

    # ==================================================================
    # TIMER
    # ==================================================================

    def set_timer(self, duration: str) -> str:
        """
        Set a countdown timer.
        duration examples: "5 minutes", "30 seconds", "2 hours", "10"
        """
        try:
            seconds = self._parse_duration(duration)
            if seconds <= 0:
                return "Please specify a valid duration like '5 minutes'."

            timer_id = len(self._timers)
            end_time = time.time() + seconds
            self._timers.append({"end_time": end_time, "active": True})

            threading.Thread(
                target=self._run_timer,
                args=(timer_id, seconds),
                daemon=True
            ).start()

            mins = int(seconds // 60)
            secs = int(seconds  % 60)
            if mins > 0:
                return f"Timer set for {mins} minute{'s' if mins > 1 else ''}" + \
                       (f" {secs} seconds" if secs else "") + "."
            return f"Timer set for {secs} second{'s' if secs > 1 else ''}."

        except Exception as e:
            logger.exception("set_timer error: %s", e)
            return "Could not set the timer."

    def _parse_duration(self, text: str) -> int:
        """Parse a duration string to seconds."""
        import re
        text = (text or "").lower().strip()

        # Try regex first
        m = re.search(r"(\d+)\s*(second|sec|minute|min|hour|hr)?s?", text)
        if m:
            val  = int(m.group(1))
            unit = (m.group(2) or "minute").lower()
            if unit.startswith(("sec",)):
                return val
            if unit.startswith(("min",)):
                return val * 60
            if unit.startswith(("hour","hr")):
                return val * 3600
            # bare number → assume minutes
            return val * 60

        # Try plain integer
        try:
            return int(text) * 60
        except Exception:
            return 0

    def _run_timer(self, timer_id: int, total_seconds: int):
        timer = self._timers[timer_id]

        # Halfway warning for timers > 60 seconds
        if total_seconds > 60:
            halfway = total_seconds / 2
            time.sleep(halfway)
            if timer["active"]:
                mins_left = int((timer["end_time"] - time.time()) // 60) + 1
                self._speak(f"{mins_left} minute{'s' if mins_left > 1 else ''} remaining.")
            remaining = timer["end_time"] - time.time()
            if remaining > 0:
                time.sleep(remaining)
        else:
            remaining = timer["end_time"] - time.time()
            if remaining > 0:
                time.sleep(remaining)

        if timer["active"]:
            self._speak("Timer finished!")
            timer["active"] = False

    # ==================================================================
    # STOPWATCH
    # ==================================================================

    def start_stopwatch(self, name: str = "default") -> str:
        self._stopwatches[name] = {"start": time.time(), "running": True}
        return f"Stopwatch '{name}' started."

    def stop_stopwatch(self, name: str = "default") -> str:
        if name not in self._stopwatches or not self._stopwatches[name].get("running"):
            return f"Stopwatch '{name}' is not running."
        elapsed  = time.time() - self._stopwatches[name]["start"]
        minutes  = int(elapsed // 60)
        seconds  = int(elapsed  % 60)
        self._stopwatches[name]["running"] = False
        if minutes > 0:
            return f"Elapsed time: {minutes} minute{'s' if minutes != 1 else ''} and {seconds} second{'s' if seconds != 1 else ''}."
        return f"Elapsed time: {seconds} second{'s' if seconds != 1 else ''}."

    # ==================================================================
    # WEATHER PLACEHOLDER
    # ==================================================================

    def get_weather(self, location: str = "") -> str:
        if location:
            return f"Let me check the weather for {location}."
        return "Let me check the current weather."


# ── Global instance ───────────────────────────────────────────────────
utility_manager = UtilityManager()