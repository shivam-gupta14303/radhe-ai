# speech.py
"""
Speech module for Radhe — TTS + ASR.

Fixes vs previous version:
  - ElevenLabs: correct API is text_to_speech.convert() not generate()
  - Whisper:    Windows-safe temp file path (WinError 2 fix)
  - speak():    text cleaned before TTS — removes emoji, slash, brackets
                so pyttsx3 never reads "haan slash nahi" or "tick slash cross"
  - Vosk + Google fallback preserved
"""

import os
import imageio_ffmpeg as ffmpeg
os.environ["FFMPEG_BINARY"] = ffmpeg.get_ffmpeg_exe()
os.environ["PATH"] += os.pathsep + os.path.dirname(ffmpeg.get_ffmpeg_exe())
import re
import json
import logging
import queue
import tempfile
import threading
import time
from typing import List, Optional

import pyttsx3
import speech_recognition as sr
logger = logging.getLogger("Radhe_Speech")
logger.setLevel(logging.INFO)

# ── ENV ───────────────────────────────────────────────────────────────
ELEVEN_API_KEY  = os.getenv("ELEVEN_API_KEY",  "")
ELEVEN_VOICE_ID = os.getenv("ELEVEN_VOICE_ID", "")

# ── ElevenLabs client (optional) ─────────────────────────────────────
_eleven_client = None
if ELEVEN_API_KEY:
    try:
        from elevenlabs.client import ElevenLabs
        from elevenlabs import play as eleven_play       
        _eleven_client = ElevenLabs(api_key=ELEVEN_API_KEY)
        logger.info("ElevenLabs client initialised.")
    except Exception as e:
        logger.warning("ElevenLabs init failed: %s", e)

# ── Whisper model (optional) ─────────────────────────────────────────
_whisper_model = None
try:
    import whisper as _whisper_lib
    _whisper_model = _whisper_lib.load_model("small")
    logger.info("Whisper model loaded.")
except Exception as e:
    logger.warning("Whisper load failed: %s", e)

# ── Microphone singleton ──────────────────────────────────────────────
_MIC = sr.Microphone()


# ======================================================================
#  TEXT CLEANER  — strips anything pyttsx3 reads wrong
# ======================================================================

# Emoji pattern
_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"   # emoticons
    "\U0001F300-\U0001F5FF"   # symbols & pictographs
    "\U0001F680-\U0001F6FF"   # transport & map
    "\U0001F1E0-\U0001F1FF"   # flags
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "]+",
    flags=re.UNICODE,
)


def _clean_for_tts(text: str) -> str:
    """
    Remove or replace characters that pyttsx3 reads literally.

    Examples fixed:
      "haan/nahi"          → "haan ya nahi"
      "[haan/nahi]"        → "haan ya nahi"
      "✅/❌"               → ""
      "⚠️ Confirm karo"    → "Confirm karo"
      "Ho gaya! {detail}"  → "Ho gaya! {detail}"   (braces kept — may be formatted)
    """
    if not text:
        return ""

    # Remove emoji
    text = _EMOJI_RE.sub("", text)

    # Replace slash between words with " ya " (natural Hindi/English)
    text = re.sub(r"\b(\w+)\s*/\s*(\w+)\b", r"\1 ya \2", text)

    # Remove remaining slashes
    text = text.replace("/", " ")

    # Remove square brackets
    text = re.sub(r"\[|\]", "", text)

    # Remove Unicode symbols that aren't letters/numbers/punctuation
    text = re.sub(r"[^\w\s\.,!?।\-\'\"():;%@+]", "", text)

    # Collapse extra whitespace
    text = re.sub(r"\s+", " ", text).strip()

    return text


# ======================================================================
#  TTS  —  queue-based, thread-safe
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
    engine = _init_tts()
    while True:
        text = _tts_queue.get()
        if text is None:
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
                logger.exception("pyttsx3 error: %s", e)
        _tts_queue.task_done()


def _ensure_tts_thread():
    global _tts_thread
    if _tts_thread is None or not _tts_thread.is_alive():
        _tts_thread = threading.Thread(target=_tts_worker, daemon=True)
        _tts_thread.start()


def speak(text: str) -> None:
    """
    Speak text aloud.
    - Cleans text first (removes emoji, slash, brackets).
    - Tries ElevenLabs first, falls back to pyttsx3.
    - Non-blocking: returns immediately.
    """
    if not text:
        return

    clean = _clean_for_tts(text)
    if not clean:
        return

    logger.info("TTS: %s", clean)

    # ── ElevenLabs ─────────────────────────
    if _eleven_client and ELEVEN_VOICE_ID:
        try:
            audio_stream = _eleven_client.text_to_speech.convert(
                text=clean,
                voice_id=ELEVEN_VOICE_ID,
                model_id="eleven_multilingual_v2",
            )

            # convert stream → bytes
            audio_bytes = b"".join(audio_stream)

            eleven_play(audio_bytes)
            return

        except Exception as e:
            logger.warning("ElevenLabs failed, using pyttsx3: %s", e)

    # ── pyttsx3 fallback ─────────────────────────────────────────────
    _ensure_tts_thread()
    _tts_queue.put(clean)


# ======================================================================
#  WHISPER  (Fix: Windows-safe temp file)
# ======================================================================

def _recognize_whisper(audio_data: sr.AudioData) -> str:
    if not _whisper_model:
        return ""
    try:
        import tempfile
        tmp_path = os.path.join(tempfile.gettempdir(), "radhe_audio.wav")

        with open(tmp_path, "wb") as f:
            f.write(audio_data.get_wav_data())

        result = _whisper_model.transcribe(tmp_path)

        try:
            os.remove(tmp_path)
        except Exception:
            pass

        return result.get("text", "").lower().strip()

    except Exception as e:
        logger.warning("Whisper error: %s", e)
        return ""


# ======================================================================
#  VOSK  (offline, no internet)
# ======================================================================

try:
    from vosk import Model, KaldiRecognizer
    VOSK_AVAILABLE = True
except Exception:
    VOSK_AVAILABLE = False

BASE_DIR           = os.path.dirname(os.path.abspath(__file__))
VOSK_MODEL_PATH_EN = os.path.join(BASE_DIR, "vosk-model-en")
VOSK_MODEL_PATH_HI = os.path.join(BASE_DIR, "vosk-model-hi")

_model_en = None
_model_hi = None


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


# ======================================================================
#  GOOGLE FALLBACK
# ======================================================================

def _recognize_google(r: sr.Recognizer, audio: sr.AudioData, language: str) -> str:
    try:
        lang_code = "hi-IN" if language.startswith("hi") else "en-IN"
        return r.recognize_google(audio, language=lang_code).lower().strip()
    except Exception as e:
        logger.debug("Google ASR error: %s", e)
        return ""


# ======================================================================
#  MASTER ASR  —  Whisper → Vosk → Google
# ======================================================================

def recognize_audio_chunk(
    recognizer:  sr.Recognizer,
    audio_data:  sr.AudioData,
    language:    str  = "en",
    use_whisper: bool = True,
) -> str:
    """
    ASR pipeline:
      1. Whisper  (best accuracy, Hindi-English mixed)
      2. Vosk     (offline fallback)
      3. Google   (online fallback)
    """
    try:
        if use_whisper:
            text = _recognize_whisper(audio_data)
            if text:
                return text

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
#  WAKE WORD  (Vosk/Google only — Whisper too slow for hot-word)
# ======================================================================

def listen_for_wake_word(
    wake_word:      str   = "radhe",
    wake_lang:      str   = "en",
    chunk_duration: float = 2.5,
) -> bool:
    """
    Listen continuously until wake word detected.
    Returns True on detection, False on KeyboardInterrupt only.
    Whisper is OFF here — too slow for continuous wake-word polling.
    """
    r = sr.Recognizer()

    with _MIC as source:
        r.adjust_for_ambient_noise(source, duration=0.5)
        logger.info("Listening for wake word '%s'...", wake_word)

        while True:
            try:
                audio = r.listen(
                    source,
                    timeout          = chunk_duration,
                    phrase_time_limit= chunk_duration,
                )
                # use_whisper=False for speed
                text = recognize_audio_chunk(r, audio, wake_lang, use_whisper=False)

                if not text:
                    continue

                logger.debug("Heard: %s", text)

                if wake_word.lower()[:3] in text.lower():
                    logger.info("Wake word detected: '%s'", text)
                    return True

            except sr.WaitTimeoutError:
                continue

            except KeyboardInterrupt:
                logger.info("Wake word listener interrupted.")
                return False

            except Exception as e:
                logger.exception("Wake word listen error: %s", e)
                time.sleep(0.5)


# ======================================================================
#  COMMAND CAPTURE  (Whisper ON for accuracy)
# ======================================================================

def capture_multi_commands(
    command_lang: str = "en",
    phrase_limit: int = 12,
) -> List[str]:
    """
    Capture a spoken command after wake word.
    Whisper is ON here for best accuracy.
    Returns list of command strings split on sentence-ending punctuation.
    """
    r = sr.Recognizer()

    with _MIC as source:
        try:
            r.adjust_for_ambient_noise(source, duration=0.4)
            logger.info("Listening for command...")

            audio = r.listen(source, timeout=4, phrase_time_limit=phrase_limit)

            # use_whisper=True for command accuracy
            text = recognize_audio_chunk(r, audio, command_lang, use_whisper=True)

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
    """Convenience: wake word → first captured command."""
    try:
        if listen_for_wake_word(wake_word=wake_word):
            cmds = capture_multi_commands()
            return cmds[0] if cmds else ""
    except Exception as e:
        logger.exception("get_voice_input error: %s", e)
    return ""