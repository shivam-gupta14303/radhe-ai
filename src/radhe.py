# src/interfaces/radhe.py
"""
Radhe — Voice Interface Entry Point.

Updates vs previous version:
- WhatsApp listener wired in via social_integrator.
- Executor connected to social_integrator for auto-reply capability.
- Graceful KeyboardInterrupt / shutdown handling.
"""

import time
import logging

from src.command_parser import CommandParser
from src.command_executor import executor
from speech import speak, listen_for_wake_word, capture_multi_commands
from reminder_manager import ReminderManager
from social_media import social_integrator

# 🔥 LLM engine — attaches brain.llm_client (must run before any ai_knowledge call)
import src.llm_setup  # noqa: F401

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(levelname)s]  %(name)s — %(message)s"
)
logger = logging.getLogger("Radhe_Main")

WAKE_WORD = "radhe"
COOLDOWN  = 1.5   # seconds between commands


def run():
    parser = CommandParser()

    # ── Reminder manager ──────────────────────────────────────────────
    rm = ReminderManager(speak)
    rm.start()
    executor.context["reminder_manager"] = rm
    logger.info("Reminder manager started.")

    # ── WhatsApp listener ─────────────────────────────────────────────
    # Connects executor so incoming WA messages can be auto-replied to.
    try:
        social_integrator.connect_executor(executor)
        social_integrator.listen_whatsapp()
        logger.info("WhatsApp listener started.")
    except Exception as e:
        logger.warning("WhatsApp listener could not start: %s", e)

    # ── Startup ───────────────────────────────────────────────────────
    speak("Radhe is ready. Say Radhe to wake me.")
    logger.info("Voice loop started. Wake word: '%s'", WAKE_WORD)

    last_execution_time = 0.0

    while True:
        try:

            # Cooldown between commands
            if time.time() - last_execution_time < COOLDOWN:
                time.sleep(0.2)
                continue

            # Wait for wake word
            if not listen_for_wake_word(WAKE_WORD):
                continue

            # Capture command
            cmds = capture_multi_commands()
            if not cmds:
                speak("I didn't catch that. Please try again.")
                continue

            text = cmds[0].strip()
            if not text:
                continue

            logger.info("Command: %s", text)

            # Parse → Execute → Speak
            parsed = parser.parse(text)
            result = executor.execute(parsed, text)

            reply = result.get("voice") or result.get("text", "")
            if reply:
                speak(reply)

            last_execution_time = time.time()

        except KeyboardInterrupt:
            logger.info("Shutting down Radhe...")
            speak("Goodbye!")
            rm.stop()
            break

        except Exception as e:
            logger.exception("Voice loop error: %s", e)
            speak("Something went wrong. Please try again.")
            time.sleep(1)


if __name__ == "__main__":
    run()