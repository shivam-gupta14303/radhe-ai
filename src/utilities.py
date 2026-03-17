"""
UtilityManager

Provides simple utility tools for Radhe:
- timer
- stopwatch
- time
- date
- placeholder weather
"""

import time
import datetime
import threading
import logging
from speech import speak  # for timer notifications

logger = logging.getLogger("Radhe_Utilities")
logger.setLevel(logging.INFO)


class UtilityManager:

    def __init__(self):

        self.timers = []
        self.stopwatches = {}

    def set_timer(self, duration: str) -> str:

        try:

            parts = duration.lower().split()

            if not parts or not parts[0].isdigit():
                return "Please specify duration like '5 minutes'."

            value = int(parts[0])

            if len(parts) > 1 and parts[1].startswith("hour"):
                seconds = value * 3600

            elif len(parts) > 1 and parts[1].startswith("minute"):
                seconds = value * 60

            elif len(parts) > 1 and parts[1].startswith("second"):
                seconds = value

            else:
                seconds = value * 60

            timer_id = len(self.timers)

            self.timers.append({
                "duration": seconds,
                "end_time": time.time() + seconds,
                "active": True
            })

            threading.Thread(
                target=self._run_timer,
                args=(timer_id,),
                daemon=True
            ).start()

            return f"Timer set for {duration}."

        except Exception as e:

            logger.exception("Timer error: %s", e)
            return "Could not set timer."

    def _run_timer(self, timer_id):

        timer = self.timers[timer_id]

        remaining = timer["end_time"] - time.time()

        if remaining > 0:
            time.sleep(remaining)

        if timer["active"]:

            speak("Timer finished")

            timer["active"] = False

    def start_stopwatch(self, name="default"):

        self.stopwatches[name] = {
            "start": time.time(),
            "running": True
        }

        return f"Stopwatch {name} started."

    def stop_stopwatch(self, name="default"):

        if name not in self.stopwatches:
            return "Stopwatch not running."

        elapsed = time.time() - self.stopwatches[name]["start"]

        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)

        self.stopwatches[name]["running"] = False

        return f"Elapsed {minutes} minutes {seconds} seconds."

    def get_time(self):

        now = datetime.datetime.now()

        return now.strftime("%H:%M:%S")

    def get_date(self):

        now = datetime.datetime.now()

        return now.strftime("%A, %B %d, %Y")

    def get_weather(self, location=""):

        if location:
            return f"Weather for {location} not implemented yet."

        return "Weather service not implemented."


utility_manager = UtilityManager()