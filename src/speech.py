# speech.py
"""
Speech module for Radhe — TTS + ASR.

Improvements vs previous version:
- speak() queues speech so it never overlaps (thread-safe queue-based TTS).
- listen_for_wake_word() resets the 60s timeout on each loop iteration
  so the assistant listens indefinitely without returning False.
- Language auto-detection hint passed to ASR.
- get_voice_input() is a simple convenience wrapper.
"""

import os
import logging
import json
import re
import threading
import time
import queue
import speech_recognition as sr
import pyttsx3

from typing import List, Optional

logger = logging.getLogger("Radhe_Speech")
logger.setLevel(logging.INFO)

# ── Microphone (singleton) ────────────────────────────────────────────
_MIC = sr.Microphone()

# ======================================================================
#  TTS  —  queue-based, thread-safe, non-overlapping
# ======================================================================

_tts_engine: Optional[pyttsx3.Engine] = None
_tts_lock   = threading.Lock()
_tts_queue: queue.Queue = queue.Queue()
_tts_thread: Optional[threading.Thread] = None


def _init_tts() -> pyttsx3.Engine:
    global _tts_engine
    if _tts_engine is None:
        _tts_engine = pyttsx3.init()
        _tts_engine.setProperty("rate",   170)
        _tts_engine.setProperty("volume", 1.0)
    return _tts_engine


def _tts_worker():
    """Background thread that serialises all speech."""
    engine = _init_tts()
    while True:
        text = _tts_queue.get()
        if text is None:     # poison pill — shut down
            break
        with _tts_lock:
            try:
                engine.stop()
            except Exception:
                pass
            try:
                engine.say(text)
                engine.runAndWait()
            except Exception as e:
                logger.exception("TTS error: %s", e)
        _tts_queue.task_done()


def _ensure_tts_thread():
    global _tts_thread
    if _tts_thread is None or not _tts_thread.is_alive():
        _tts_thread = threading.Thread(target=_tts_worker, daemon=True)
        _tts_thread.start()


def speak(text: str) -> None:
    """Queue text for speech. Returns immediately (non-blocking)."""
    if not text:
        return
    logger.info("TTS queued: %s", text)
    _ensure_tts_thread()
    _tts_queue.put(text)


# ======================================================================
#  ASR  —  Vosk offline + Google fallback
# ======================================================================

try:
    from vosk import Model, KaldiRecognizer
    VOSK_AVAILABLE = True
except Exception:
    VOSK_AVAILABLE = False

BASE_DIR           = os.path.dirname(os.path.abspath(__file__))
VOSK_MODEL_PATH_EN = os.path.join(BASE_DIR, "vosk-model-en")
VOSK_MODEL_PATH_HI = os.path.join(BASE_DIR, "vosk-model-hi")

_model_en: Optional["Model"] = None
_model_hi: Optional["Model"] = None


def _load_vosk_models():
    global _model_en, _model_hi
    if not VOSK_AVAILABLE:
        return
    if os.path.isdir(VOSK_MODEL_PATH_EN):
        try:
            _model_en = Model(VOSK_MODEL_PATH_EN)
            logger.info("Vosk English model loaded.")
        except Exception as e:
            logger.warning("Vosk EN load failed: %s", e)
    if os.path.isdir(VOSK_MODEL_PATH_HI):
        try:
            _model_hi = Model(VOSK_MODEL_PATH_HI)
            logger.info("Vosk Hindi model loaded.")
        except Exception as e:
            logger.warning("Vosk HI load failed: %s", e)


_load_vosk_models()


def _recognize_vosk(raw: bytes, language: str) -> str:
    try:
        model = _model_hi if language.startswith("hi") else _model_en
        if not model:
            return ""
        rec = KaldiRecognizer(model, 16000)
        if rec.AcceptWaveform(raw):
            return json.loads(rec.Result()).get("text", "").strip()
        return json.loads(rec.PartialResult()).get("partial", "").strip()
    except Exception as e:
        logger.warning("Vosk error: %s", e)
        return ""


def _recognize_google(r: sr.Recognizer, audio: sr.AudioData, language: str) -> str:
    try:
        lang_code = "hi-IN" if language.startswith("hi") else "en-IN"
        return r.recognize_google(audio, language=lang_code).lower().strip()
    except Exception as e:
        logger.debug("Google ASR error: %s", e)
        return ""


def recognize_audio_chunk(
    recognizer: sr.Recognizer,
    audio_data: sr.AudioData,
    language:   str = "en"
) -> str:
    try:
        raw = audio_data.get_raw_data(convert_rate=16000, convert_width=2)
        if VOSK_AVAILABLE:
            text = _recognize_vosk(raw, language)
            if text:
                return text.lower().strip()
        return _recognize_google(recognizer, audio_data, language)
    except Exception as e:
        logger.warning("recognize_audio_chunk failed: %s", e)
        return ""


# ======================================================================
#  WAKE WORD
# ======================================================================

def listen_for_wake_word(
    wake_word:      str   = "radhe",
    wake_lang:      str   = "en",
    chunk_duration: float = 2.5
) -> bool:
    """
    Listen continuously until the wake word is detected.
    Returns True when detected, False only on KeyboardInterrupt.

    Fix vs previous version:
    - Removed the 60-second timeout that returned False — the assistant
      should listen indefinitely. The caller controls when to stop.
    """
    r = sr.Recognizer()

    with _MIC as source:
        r.adjust_for_ambient_noise(source, duration=0.5)
        logger.info("Listening for wake word '%s'...", wake_word)

        while True:
            try:
                audio = r.listen(source, timeout=chunk_duration,
                                 phrase_time_limit=chunk_duration)
                text  = recognize_audio_chunk(r, audio, wake_lang)

                if not text:
                    continue

                logger.debug("Heard: %s", text)

                if wake_word.lower()[:3] in text.lower():   # tolerant match ("rad" in "radhe")
                    logger.info("Wake word detected in: '%s'", text)
                    return True

            except sr.WaitTimeoutError:
                continue   # normal — just no speech in this chunk

            except KeyboardInterrupt:
                logger.info("Wake word listener interrupted.")
                return False

            except Exception as e:
                logger.exception("Wake word listen error: %s", e)
                time.sleep(0.5)


# ======================================================================
#  COMMAND CAPTURE
# ======================================================================

def capture_multi_commands(
    command_lang: str = "en",
    phrase_limit: int = 12
) -> List[str]:
    """
    Capture a spoken command after wake word detection.
    Returns a list of command strings (split on punctuation).
    """
    r = sr.Recognizer()

    with _MIC as source:
        try:
            r.adjust_for_ambient_noise(source, duration=0.4)
            logger.info("Listening for command...")
            audio = r.listen(source, timeout=4, phrase_time_limit=phrase_limit)
            text  = recognize_audio_chunk(r, audio, command_lang)

            if not text:
                return []

            commands = [c.strip() for c in re.split(r"[\.?!]", text) if c.strip()]
            return commands[:6]

        except sr.WaitTimeoutError:
            return []
        except Exception as e:
            logger.exception("capture_multi_commands failed: %s", e)
            return []


def get_voice_input(wake_word: str = "radhe") -> str:
    """Convenience: wait for wake word then return first captured command."""
    try:
        if listen_for_wake_word(wake_word=wake_word):
            cmds = capture_multi_commands()
            return cmds[0] if cmds else ""
    except Exception as e:
        logger.exception("get_voice_input error: %s", e)
    return ""