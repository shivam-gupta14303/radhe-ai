#radhe.py
"""
Radhe — Voice Interface Entry Point.

Features:
- WhatsApp listener wired in via social_integrator (non-blocking).
- Conversational follow-ups for slot filling (message/contact) and clarifications
  without requiring repeated wake words.
- Resilient state machine: pending clarification/slot state is NOT dropped on
  momentary silence; retries gracefully before cancelling cleanly.
- Guaranteed clean shutdown handling via try/finally: stops reminder manager,
  terminates WhatsApp listener threads and closes Selenium browser instances.
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
from config import RADHE_MEMORY_FILE

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(levelname)s]  %(name)s — %(message)s"
)
logger = logging.getLogger("Radhe_Main")

WAKE_WORD = "radhe"
COOLDOWN  = 1.5   # seconds between commands
MAX_AWAITING_RETRIES = 2  # number of silent listening attempts before timing out


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
        social_integrator.set_speak_callback(speak)
        social_integrator.listen_whatsapp()
        logger.info("WhatsApp listener started.")
    except Exception as e:
        logger.warning("WhatsApp listener could not start: %s", e)

    # ── Startup ───────────────────────────────────────────────────────
    speak("Radhe is ready. Say Radhe to wake me.")
    logger.info("Voice loop started. Wake word: '%s'", WAKE_WORD)

    last_execution_time = 0.0

    awaiting_reply = False
    awaiting_prompt = ""
    silence_retries = 0

    try:
        while True:
            try:
                if time.time() - last_execution_time < COOLDOWN:
                    time.sleep(0.2)
                    continue

                # If an incoming message in Approval mode needs confirmation, activate awaiting_reply
                if executor.context.get("awaiting_whatsapp_approval"):
                    awaiting_reply = True
                    awaiting_prompt = "Should I send the WhatsApp reply? Please say yes or cancel."
                    executor.context.pop("awaiting_whatsapp_approval", None)

                # Skip wake word if we're mid-clarification, slot filling, onboarding, or WhatsApp approval
                if not awaiting_reply:
                    if not listen_for_wake_word(
                        WAKE_WORD,
                        stop_condition=lambda: bool(executor.context.get("awaiting_whatsapp_approval"))
                    ):
                        continue

                cmds = capture_multi_commands()

                # Handle silence / empty input
                if not cmds:
                    if awaiting_reply:
                        silence_retries += 1
                        if silence_retries < MAX_AWAITING_RETRIES:
                            logger.info(
                                "Silence detected during awaiting_reply (%d/%d). Prompting user again.",
                                silence_retries, MAX_AWAITING_RETRIES
                            )
                            if awaiting_prompt:
                                speak(awaiting_prompt)
                            else:
                                speak("I'm listening. Please reply or say cancel.")
                            continue
                        else:
                            # Max retries reached — gracefully cancel and clear pending state
                            logger.info("Clarification/slot-filling timed out after silence. Clearing pending state.")
                            speak("No response received. Cancelled.")
                            awaiting_reply = False
                            awaiting_prompt = ""
                            silence_retries = 0
                            executor.context.pop("awaiting_contact", None)
                            executor.context.pop("awaiting_message", None)
                            executor.context.pop("pending_whatsapp_approval", None)
                            executor.context.pop("awaiting_whatsapp_approval", None)
                            if hasattr(parser, "_session") and parser._session:
                                parser._session.reset()
                            continue
                    else:
                        speak("I didn't catch that. Please try again.")
                        continue

                # User spoke — reset silence retry counter
                silence_retries = 0

                for text in cmds:
                    text = text.strip()
                    if not text:
                        continue

                    logger.info("Command: %s", text)

                    # Handle explicit cancel keyword during dialogue
                    if text.lower() in ("cancel", "stop", "nevermind", "ruk", "nahi", "exit", "quit", "chhod do"):
                        speak("Okay, cancelled.")
                        awaiting_reply = False
                        awaiting_prompt = ""
                        executor.context.pop("awaiting_contact", None)
                        executor.context.pop("awaiting_message", None)
                        executor.context.pop("pending_whatsapp_approval", None)
                        executor.context.pop("awaiting_whatsapp_approval", None)
                        if hasattr(parser, "_session") and parser._session:
                            parser._session.reset()
                        break

                    # If we're awaiting confirmation for a drafted WhatsApp reply
                    if executor.context.get("pending_whatsapp_approval"):
                        awaiting_reply = False
                        awaiting_prompt = ""
                        result = executor.execute({"intent": "confirm_whatsapp_reply", "entities": {}}, text)
                        reply = result.get("voice") or result.get("text", "")
                        if reply:
                            speak(reply)
                        continue

                    # If we're awaiting a follow-up slot (message text or contact name)
                    if executor.context.get("awaiting_message") or executor.context.get("awaiting_contact"):
                        awaiting_reply = False
                        awaiting_prompt = ""
                        result = executor.execute({"intent": "send_message", "entities": {}}, text)
                        reply = result.get("voice") or result.get("text", "")
                        if executor.context.get("awaiting_contact") or executor.context.get("awaiting_message"):
                            awaiting_reply = True
                            awaiting_prompt = reply
                        if reply:
                            speak(reply)
                        continue

                    engine_result = engine.handle(text)
                    if engine_result and not engine_result.silent_skipped:
                        action = engine_result.action
                        if action.get("intent") == "clarify":
                            reply          = action.get("question") or action.get("entities", {}).get("question", "Thoda aur batao?")
                            awaiting_reply = True
                            awaiting_prompt = reply
                            speak(reply)
                            break
                        else:
                            awaiting_reply = False
                            awaiting_prompt = ""
                            reply = action.get("entities", {}).get("_output", "")
                            if not reply:
                                result = executor.execute(action, text)
                                reply  = result.get("voice") or result.get("text", "")

                            if not executor.context.get("onboarding_complete", True):
                                awaiting_reply = True
                                awaiting_prompt = reply
                            if executor.context.get("awaiting_contact") or executor.context.get("awaiting_message"):
                                awaiting_reply = True
                                awaiting_prompt = reply

                            if reply:
                                speak(reply)
                    else:
                        parsed_action = parser.parse(text)
                        result = executor.execute(parsed_action, text)
                        reply = result.get("voice") or result.get("text", "")
                        if executor.context.get("awaiting_contact") or executor.context.get("awaiting_message"):
                            awaiting_reply = True
                            awaiting_prompt = reply
                        if reply:
                            speak(reply)

                last_execution_time = time.time()

            except KeyboardInterrupt:
                raise

            except Exception as e:
                logger.exception("Voice loop error: %s", e)
                speak("Something went wrong. Please try again.")
                awaiting_reply = False
                awaiting_prompt = ""
                silence_retries = 0
                executor.context.pop("awaiting_contact", None)
                executor.context.pop("awaiting_message", None)
                time.sleep(1)

    except KeyboardInterrupt:
        logger.info("Shutting down Radhe...")
        speak("Goodbye!")

    finally:
        # Complete shutdown handling for both reminder manager and WhatsApp session
        logger.info("Performing clean shutdown of all background services...")
        try:
            rm.stop()
            logger.info("Reminder manager stopped.")
        except Exception as e:
            logger.warning("Error stopping reminder manager: %s", e)

        try:
            social_integrator.stop()
            logger.info("WhatsApp listener and browser session stopped.")
        except Exception as e:
            logger.warning("Error stopping WhatsApp session: %s", e)


if __name__ == "__main__":
    run()
