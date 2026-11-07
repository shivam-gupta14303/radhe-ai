# scratch/update_speech.py
import re

with open('src/speech.py', 'r', encoding='utf-8') as f:
    content = f.read()

target_start = 'def recognize_audio_chunk('
target_end = '# ======================================================================'

start_idx = content.find(target_start)
end_idx = content.find(target_end, start_idx + 100)
# We want the SECOND separator after target_start which is COMMAND CAPTURE
sep2_idx = content.find(target_end, end_idx + 50)

if start_idx == -1 or sep2_idx == -1:
    print('Failed to find markers', start_idx, sep2_idx)
    exit(1)

replacement = '''def recognize_audio_chunk(
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
            if text and len(text) > 2:
                return text

        raw = audio_data.get_raw_data(convert_rate=16000, convert_width=2)

        if VOSK_AVAILABLE:
            text = _recognize_vosk(raw, language)
            if text:
                return text.lower().strip()

        text = _recognize_google(recognizer, audio_data, language)
        if text:
            return text.lower().strip()

        # Offline fallback: if Whisper is loaded, attempt Whisper when Vosk & Google fail
        if not use_whisper and _whisper_model is not None:
            text = _recognize_whisper(audio_data)
            if text and len(text) > 2:
                return text.lower().strip()

        return ""

    except Exception as e:
        logger.warning("recognize_audio_chunk failed: %s", e)
        return ""


# ======================================================================
#  WAKE WORD  (Vosk/Google only - Whisper too slow for hot-word)
# ======================================================================

def is_wake_word_match(text: str, wake_word: str = "radhe") -> bool:
    """
    Check if the transcribed audio text contains the wake word.
    Supports English & Hindi phonetic variations of 'radhe' / 'hey radhe'.
    """
    if not text:
        return False

    cleaned = text.lower().strip()
    target = wake_word.lower().strip()

    # Hindi script direct check
    if "\u0930\u093e\u0927\u0947" in text or "\u0930\u093e\u0927\u093e" in text:
        return True

    # If target is radhe/radha or hey radhe
    if "radhe" in target or "radha" in target:
        # Regex matching wake variations with word boundaries
        # Matches: radhe, radha, radhey, raade, raadha, radhika, raddhe, etc.
        # with optional greeting prefix like hey, hi, hello, ok, sun, suno, are, arre, oye
        pattern = r"\\b(?:hey|hi|hello|ok|sun|suno|are|arre|oye)?\s*(radhe|radha|radhey|raade|raadha|radhika|raddhe)\\b"
        if re.search(pattern, cleaned):
            return True

        if "radhe" in cleaned or "radha" in cleaned:
            return True

    # Generic wake word matching (for custom wake words)
    target_clean = re.sub(r"[^\w\s]", "", target)
    cleaned_no_punct = re.sub(r"[^\w\s]", "", cleaned)

    if re.search(rf"\\b{re.escape(target_clean)}\\b", cleaned_no_punct):
        return True

    if " " in target_clean and target_clean in cleaned_no_punct:
        return True

    return False


def listen_for_wake_word(
    wake_word:      str   = "radhe",
    wake_lang:      str   = "en",
    chunk_duration: float = 2.5,
    stop_condition: Optional[Callable[[], bool]] = None,
) -> bool:
    """
    Listen continuously until wake word detected.
    Returns True on detection, False on KeyboardInterrupt or stop_condition.
    Whisper is OFF here - Vosk/Google used for fast continuous polling.
    """
    r = sr.Recognizer()

    with _MIC as source:
        r.adjust_for_ambient_noise(source, duration=0.5)
        logger.info("Listening for wake word '%s'...", wake_word)

        while True:
            if stop_condition and stop_condition():
                logger.debug("Wake word listening aborted by stop_condition.")
                return False

            try:
                audio = r.listen(
                    source,
                    timeout          = chunk_duration,
                    phrase_time_limit= chunk_duration,
                )
                # use_whisper=False for fast wake-word polling
                text = recognize_audio_chunk(r, audio, wake_lang, use_whisper=False)

                if not text:
                    continue

                logger.debug("Heard: %s", text)

                if is_wake_word_match(text, wake_word):
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


'''

new_content = content[:start_idx] + replacement + content[sep2_idx:]
with open('src/speech.py', 'w', encoding='utf-8') as f:
    f.write(new_content)
print('Successfully updated src/speech.py')
