#radhe.py
"""
Radhe — Voice Interface Entry Point.

Updates vs previous version:
- WhatsApp listener wired in via social_integrator.
- Executor connected to social_integrator for auto-reply capability.
- Graceful KeyboardInterrupt / shutdown handling.
"""

import time
import logging
import llm_setup

from command_parser import CommandParser
from command_executor import executor
from speech import speak, listen_for_wake_word, capture_multi_commands
from reminder_manager import ReminderManager
from social_media import social_integrator
from radhe_engine import RadheEngine
engine = RadheEngine(user_id="default")

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

    awaiting_reply = False   # add this before the while loop

    while True:
        try:
            if time.time() - last_execution_time < COOLDOWN:
                time.sleep(0.2)
                continue

            # skip wake word if we're mid-clarification or mid-onboarding
            if not awaiting_reply:
                if not listen_for_wake_word(WAKE_WORD):
                    continue

            cmds = capture_multi_commands()
            if not cmds:
                speak("I didn't catch that. Please try again.")
                awaiting_reply = False
                continue

            for text in cmds:
                text = text.strip()
                if not text:
                    continue

                logger.info("Command: %s", text)

                engine_result = engine.handle(text)
                if engine_result and not engine_result.silent_skipped:
                    action = engine_result.action
                    if action.get("intent") == "clarify":
                        reply          = action.get("entities", {}).get("question", "Thoda aur batao?")
                        awaiting_reply = True
                        speak(reply)
                        break
                    else:
                        awaiting_reply = False
                        reply = action.get("entities", {}).get("_output", "")
                        if not reply:
                            result = executor.execute(action, text)
                            reply  = result.get("voice") or result.get("text", "")
                        if not executor.context.get("onboarding_complete", True):
                            awaiting_reply = True
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
            awaiting_reply = False
            time.sleep(1)


if __name__ == "__main__":
    run()