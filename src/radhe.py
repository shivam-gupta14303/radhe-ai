# radhe.py

import logging
from threading import Thread
import time
import requests
import os
from dotenv import load_dotenv

from src.command_parser import CommandParser
from src.command_executor import executor
from speech import speak, listen_for_wake_word, capture_multi_commands
from reminder_manager import ReminderManager

# Google contacts sync optional
try:
    from src.google_contacts import sync_to_local
except Exception:
    sync_to_local = None

from src.ai_knowledge import brain

# ---------------------------
# ENV LOAD (for API keys)
# ---------------------------
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# ---------------------------
# LOGGING
# ---------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("Radhe_Main")

# ---------------------------
# LOCAL LLM (Ollama)
# ---------------------------
def local_llm(prompt: str, meta: dict) -> str:
    try:
        resp = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "llama3.1",
                "prompt": prompt,
                "stream": False
            },
            timeout=60
        )

        if resp.status_code != 200:
            logger.error("Ollama HTTP %s: %s", resp.status_code, resp.text[:200])
            return ""

        data = resp.json()
        response = data.get("response", "").strip()

        if not response:
            return "I couldn't generate a response."

        return response

    except Exception as e:
        logger.error("local_llm error: %s", e)
        return ""

# ---------------------------
# CLOUD LLM (Groq)
# ---------------------------
def cloud_llm(prompt: str, meta: dict) -> str:
    if not GROQ_API_KEY:
        return ""

    try:
        url = "https://api.groq.com/openai/v1/chat/completions"

        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }

        data = {
            "model": "llama3-70b-8192",
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }

        resp = requests.post(url, headers=headers, json=data, timeout=20)
        result = resp.json()

        return result["choices"][0]["message"]["content"]

    except Exception as e:
        logger.error("cloud_llm error: %s", e)
        return ""

# ---------------------------
# SMART LLM (Hybrid)
# ---------------------------
def smart_llm(prompt: str, meta: dict) -> str:
    # 1️⃣ Try cloud first
    response = cloud_llm(prompt, meta)
    if response:
        return response

    # 2️⃣ fallback to local
    return local_llm(prompt, meta)

# Attach brain
brain.llm_client = smart_llm

# ---------------------------
# VOICE LOOP
# ---------------------------
def voice_command_loop(wake_word: str = "radhe"):

    parser = CommandParser()
    logger.info("Voice command loop ready. Say '%s' to wake me.", wake_word)

    while True:
        try:
            # Wake word
            if not listen_for_wake_word(wake_word=wake_word):
                continue

            # Capture command
            commands = capture_multi_commands(command_lang="en", phrase_limit=15)
            if not commands:
                continue

            text = (commands[0] or "").strip()
            if not text:
                continue

            logger.info("Heard command: %s", text)

            # Parse
            parsed = parser.parse(text)

            # Execute
            result = executor.execute(parsed, text, executor.context)

            # Speak
            reply_voice = result.get("voice") or result.get("text", "")
            if reply_voice:
                speak(reply_voice)

            logger.info("Response: %s", result.get("text", ""))

            time.sleep(0.3)

        except KeyboardInterrupt:
            logger.info("Stopping Radhe...")
            break
        except Exception as e:
            logger.exception("Voice loop error: %s", e)
            speak("Something went wrong. Please try again.")
            time.sleep(1)

# ---------------------------
# MAIN
# ---------------------------
if __name__ == "__main__":
    logger.info("Starting Radhe...")

    # Google contacts sync
    if sync_to_local is not None:
        def auto_sync_contacts():
            try:
                logger.info("📇 Syncing Google contacts...")
                count = sync_to_local()
                logger.info("📇 Synced %d contacts", count)
            except Exception as e:
                logger.error("Contacts sync failed: %s", e)

        Thread(target=auto_sync_contacts, daemon=True).start()

    # Reminder manager
    rm = ReminderManager(speak)
    rm.start()
    executor.context["reminder_manager"] = rm

    # Startup voice
    speak("Hello Shivam, Radhe is ready.")

    # Start voice loop
    voice_command_loop("radhe")