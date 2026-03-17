# speech.py
"""
Single speech module:
- TTS (pyttsx3) centralized
- Speech recognition with Vosk offline models and Google as fallback
- Exposed functions:
    - speak(text)
    - listen_for_wake_word(wake_word='radhe', language='en', timeout=1.0)
    - capture_multi_commands(command_lang='en', phrase_limit=15)
    - get_voice_input() -> first captured command or ""
    - start_telegram_bot_if_configured() -> wrapper to import and run telegram bot safely
Notes:
- Keep VOSK models optional: if model folder missing, fallback to Google ASR.
- All audio operations are exception-safe.
"""

import os
import logging
import json
import re
import threading
import time
import speech_recognition as sr
import pyttsx3

from typing import List

_MIC = sr.Microphone()

logger = logging.getLogger("Radhe_Speech")
logger.setLevel(logging.INFO)

# ---- TTS (single engine + lock, fast + safe) ----
_tts_engine = None
_tts_lock = threading.Lock()

def _init_tts():
    global _tts_engine
    if _tts_engine is None:
        _tts_engine = pyttsx3.init()
        _tts_engine.setProperty("rate", 170)
        _tts_engine.setProperty("volume", 1.0)
    return _tts_engine

def speak(text: str):
    """Single shared engine, thread-safe TTS."""
    if not text:
        return

    engine = _init_tts()
    logger.info("TTS: %s", text)

    with _tts_lock:
        try:
            try:
                engine.stop()
            except Exception:
                pass
            engine.say(text)
            engine.runAndWait()
        except Exception as e:
            logger.exception("TTS error: %s", e)

# ---- ASR (Vosk optional + Google fallback) ----
try:
    from vosk import Model, KaldiRecognizer
    VOSK_AVAILABLE = True
except Exception:
    VOSK_AVAILABLE = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VOSK_MODEL_PATH_EN = os.path.join(BASE_DIR, "vosk-model-en")
VOSK_MODEL_PATH_HI = os.path.join(BASE_DIR, "vosk-model-hi")

_model_en = None
_model_hi = None
def _load_vosk_models():
    global _model_en, _model_hi
    if not VOSK_AVAILABLE:
        return
    try:
        if os.path.isdir(VOSK_MODEL_PATH_EN):
            _model_en = Model(VOSK_MODEL_PATH_EN)
            logger.info("Loaded Vosk English model.")
    except Exception as e:
        logger.warning("Failed to load Vosk EN: %s", e)
    try:
        if os.path.isdir(VOSK_MODEL_PATH_HI):
            _model_hi = Model(VOSK_MODEL_PATH_HI)
            logger.info("Loaded Vosk Hindi model.")
    except Exception as e:
        logger.warning("Failed to load Vosk HI: %s", e)

# lazy load models
_load_vosk_models()

def _recognize_with_vosk(raw_data: bytes, language: str) -> str:
    from json import loads
    try:
        model = _model_hi if language.startswith("hi") else _model_en
        if not model:
            return ""
        rec = KaldiRecognizer(model, 16000)
        if rec.AcceptWaveform(raw_data):
            res = loads(rec.Result())
            return res.get("text", "").strip()
        else:
            res = loads(rec.PartialResult())
            return res.get("partial", "").strip()
    except Exception as e:
        logger.warning("Vosk recognition error: %s", e)
        return ""

def _recognize_google(r: sr.Recognizer, audio_data: sr.AudioData, language: str) -> str:
    try:
        lang_code = "en-IN" if language.startswith("en") else "hi-IN"
        return r.recognize_google(audio_data, language=lang_code).lower().strip()
    except Exception as e:
        logger.debug("Google ASR error: %s", e)
        return ""

def recognize_audio_chunk(recognizer: sr.Recognizer, audio_data: sr.AudioData, language: str = "en") -> str:
    try:
        raw = audio_data.get_raw_data(convert_rate=16000, convert_width=2)
        if VOSK_AVAILABLE:
            text = _recognize_with_vosk(raw, language)
            if text:
                return text.lower().strip()
        # fallback to google
        return _recognize_google(recognizer, audio_data, language)
    except Exception as e:
        logger.warning("recognize_audio_chunk failed: %s", e)
        return ""

# ---- Wakeword & capture helpers ----
def listen_for_wake_word(wake_word: str = "radhe", wake_lang: str = "en", chunk_duration: float = 2.5) -> bool:
    r = sr.Recognizer()
    with _MIC as source:
        r.adjust_for_ambient_noise(source, duration=0.5)
        logger.info("Listening for wake word '%s'...", wake_word)
        start = time.time()
        while True:
            if time.time() - start > 60:  # safety timeout to prevent infinite loop
                logger.info("Wake word listening timed out after 60 seconds.")
                return False
            try:
                audio = r.listen(source, timeout=chunk_duration, phrase_time_limit=chunk_duration)
                text = recognize_audio_chunk(r, audio, wake_lang)
                print("Heard:", text)
                if not text:
                    continue
                if "rad" in text.lower():
                    logger.info("Wake word detected: %s", text)
                    return True
            except sr.WaitTimeoutError:
                continue
            except KeyboardInterrupt:
                logger.info("Keyboard interrupt on wake word listening.")
                return False
            except Exception as e:
                logger.exception("Wakeword listening error: %s", e)
                time.sleep(0.5)

def capture_multi_commands(command_lang: str = "en", phrase_limit: int = 12) -> List[str]:
    r = sr.Recognizer()
    with _MIC as source:
        try:
            r.adjust_for_ambient_noise(source, duration=0.4)
            logger.info("Listening for commands...")
            audio = r.listen(source, timeout=2, phrase_time_limit=phrase_limit)
            text = recognize_audio_chunk(r, audio, command_lang)
            if not text:
                return []
            # split by punctuation (.,?) into commands
            commands = [c.strip() for c in re.split(r'[\.|\?|!]', text) if c.strip()]
            return commands[:6]  # limit
        except Exception as e:
            logger.exception("capture_multi_commands failed: %s", e)
            return []

def get_voice_input(wake_word: str = "radhe") -> str:
    try:
        if listen_for_wake_word(wake_word=wake_word):
            cmds = capture_multi_commands(command_lang="en", phrase_limit=8)
            if cmds:
                return cmds[0]
    except Exception as e:
        logger.exception("get_voice_input error: %s", e)
    return ""