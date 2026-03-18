# src/ai_knowledge.py
"""
Radhe Intelligence Layer — single consolidated module.

Contains:
- RadheMemory       : JSON long-term memory (habits, profile).
- RadheBrain        : LLM + vision + audio wrapper.
- AIKnowledgeFacade : Public API used by command_executor and command_parser.

Fixes vs previous versions:
- answer_question() accepts history, mode, language kwargs from executor.
- interpret_intent() intent list updated to include all new intents.
- describe_self() added.
- JSON fence stripping added to interpret_intent().
- All print() replaced with logger.
"""

import json
import logging
import os
import random
from typing import Optional, Callable, Dict, Any, List

import wikipedia

logger = logging.getLogger("Radhe_AI")
logger.setLevel(logging.INFO)
wikipedia.set_lang("en")

DEFAULT_MEMORY_FILE = "radhe_memory.json"


# ======================================================================
#  RadheMemory
# ======================================================================

class RadheMemory:
    def __init__(self, path: str = DEFAULT_MEMORY_FILE):
        self.path  = path
        self._data: Dict[str, Any] = {}
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except Exception as e:
                logger.warning("Could not load memory file: %s", e)
                self._data = {}

    def _save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.exception("Failed to save memory: %s", e)

    def _ensure_user(self, user_id: str):
        if user_id not in self._data:
            self._data[user_id] = {"profile": {}, "history": []}

    def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        self._ensure_user(user_id)
        return self._data[user_id].get("profile", {})

    def update_user_profile(self, user_id: str, updates: Dict[str, Any]):
        self._ensure_user(user_id)
        self._data[user_id]["profile"].update(updates)
        self._save()

    def add_history_event(self, user_id: str, event: Dict[str, Any]):
        self._ensure_user(user_id)
        history = self._data[user_id].setdefault("history", [])
        history.append(event)
        if len(history) > 100:
            self._data[user_id]["history"] = history[-100:]
        self._save()


# ======================================================================
#  RadheBrain
# ======================================================================

class RadheBrain:
    """
    Core brain: wraps LLM, vision, audio clients.
    All clients are optional — Radhe degrades gracefully when offline.
    """

    KNOWN_INTENTS = [
        "greeting", "thanks", "goodbye",
        "conversation_smalltalk", "persona_query",
        "change_language", "change_mode", "user_boundary",
        "get_time", "get_date",
        "open_app", "close_app", "open_website",
        "search_web", "youtube_search",
        "get_directions", "get_weather", "get_news",
        "set_reminder", "list_reminders", "cancel_reminder",
        "send_message",
        "system_control", "get_battery", "set_volume",
        "take_screenshot", "analyze_screen",
        "set_timer", "start_stopwatch", "stop_stopwatch",
        "file_search",
        "summarize_text", "sentiment_check", "keyword_extract",
        "ask_question", "unknown",
    ]

    def __init__(
        self,
        llm_client:    Optional[Callable] = None,
        vision_client: Optional[Callable] = None,
        audio_client:  Optional[Callable] = None,
        memory:        Optional[RadheMemory] = None,
    ):
        self.llm_client    = llm_client
        self.vision_client = vision_client
        self.audio_client  = audio_client
        self.memory        = memory or RadheMemory()

    def _call_llm(self, prompt: str, mode: str, user_id: str, extra: Optional[Dict] = None) -> Optional[str]:
        if not self.llm_client:
            return None
        meta = {"mode": mode, "user_id": user_id}
        if extra:
            meta.update(extra)
        try:
            return self.llm_client(prompt, meta)
        except Exception as e:
            logger.exception("LLM call error: %s", e)
            return None

    # ── Memory ────────────────────────────────────────────────────────

    def get_profile(self, user_id: str) -> Dict[str, Any]:
        return self.memory.get_user_profile(user_id)

    def update_profile(self, user_id: str, updates: Dict[str, Any]):
        self.memory.update_user_profile(user_id, updates)

    def remember_preference(self, user_id: str, key: str, value: Any):
        profile = self.get_profile(user_id)
        profile[key] = value
        self.update_profile(user_id, profile)

    def add_history(self, user_id: str, event: Dict[str, Any]):
        self.memory.add_history_event(user_id, event)

    # ── Chat ──────────────────────────────────────────────────────────

    def chat(
        self,
        message:       str,
        user_id:       str = "default",
        history:       Optional[List[Dict]] = None,
        mode:          str = "neutral",
        language:      str = "en",
        extra_context: Optional[str] = None,
    ) -> str:
        message = (message or "").strip()
        if not message:
            return "I didn't receive anything to respond to."

        profile      = self.get_profile(user_id)
        profile_text = json.dumps(profile, ensure_ascii=False)

        history_text = ""
        if history:
            lines = []
            for entry in (history or [])[-6:]:
                role = entry.get("role", "user")
                text = entry.get("text", "")
                lines.append(f"{role.capitalize()}: {text}")
            history_text = "\n".join(lines)

        lang_note = {
            "hi":    "Respond in Hindi (Devanagari or romanised Hindi).",
            "mixed": "Respond in natural Hinglish (mix of Hindi and English).",
        }.get(language, "Respond in English.")

        mode_note = {
            "casual": "Tone: friendly and casual, like talking to a close friend.",
            "formal": "Tone: respectful and formal.",
        }.get(mode, "Tone: natural and balanced.")

        prompt = f"""You are Radhe, a warm and intelligent personal AI companion.

User profile:
{profile_text}

Recent conversation:
{history_text}

Instructions:
- {lang_note}
- {mode_note}
- If the user seems stressed or emotional, respond with empathy first.
- Be honest when you don't know something.
- Keep responses concise unless detail is needed.

User says: "{message}"

Your response:"""

        if extra_context:
            prompt += f"\n\nAdditional context:\n{extra_context}"

        response = self._call_llm(prompt, mode="chat", user_id=user_id)
        if response:
            self.add_history(user_id, {"type": "chat", "user": message, "radhe": response})
            return response.strip()

        return ""   # caller handles empty

    # ── Intent interpretation ─────────────────────────────────────────

    def interpret_intent(self, text: str, user_id: str = "default") -> Dict[str, Any]:
        text = (text or "").strip()
        if not text:
            return {"intent": "none", "entities": {}, "confidence": 0.0}

        intents_str = ", ".join(f'"{i}"' for i in self.KNOWN_INTENTS)

        prompt = f"""You are the intent classifier for Radhe AI assistant.

User message: "{text}"

Return a JSON object with:
- "intent": exactly one of [{intents_str}]
- "entities": object with relevant keys only:
    application, website, query, reminder_text, time, keyword,
    platform, contact, message, control_type, level,
    origin, destination, location, duration, pattern, question,
    target_language, target_mode, disallowed_term
- "confidence": float 0.0-1.0

If unsure, use "ask_question" with confidence 0.5.
Respond ONLY with valid JSON. No markdown, no extra text."""

        response = self._call_llm(prompt, mode="intent", user_id=user_id)
        if not response:
            return {"intent": "unknown", "entities": {}, "confidence": 0.0}

        # Strip markdown fences if present
        cleaned = response.strip()
        for fence in ("```json", "```"):
            if cleaned.startswith(fence):
                cleaned = cleaned[len(fence):]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        try:
            data       = json.loads(cleaned)
            intent     = data.get("intent", "unknown")
            entities   = {k: v for k, v in (data.get("entities") or {}).items() if v}
            confidence = float(data.get("confidence", 0.4))

            if intent not in self.KNOWN_INTENTS:
                intent     = "ask_question"
                confidence = 0.5

            return {"intent": intent, "entities": entities, "confidence": confidence}

        except Exception:
            logger.debug("Could not parse intent JSON: %s", response[:200])
            return {"intent": "unknown", "entities": {}, "confidence": 0.0}

    # ── Text emotion ──────────────────────────────────────────────────

    def analyze_text_emotion(self, text: str, user_id: str = "default") -> Dict[str, Any]:
        text = (text or "").strip()
        if not text:
            return {"emotion": "neutral", "confidence": 0.0, "source": "none"}

        if self.llm_client:
            prompt = f"""Classify the emotion in: "{text}"
Choose one: happy, sad, angry, fear, surprise, disgust, neutral, stressed, confused.
Return JSON only: {{"emotion":"<label>","confidence":0.0-1.0,"reason":"<short>"}}"""
            resp = self._call_llm(prompt, mode="text_emotion", user_id=user_id)
            if resp:
                try:
                    d = json.loads(resp.strip())
                    return {
                        "emotion":    d.get("emotion", "neutral"),
                        "confidence": float(d.get("confidence", 0.7)),
                        "reason":     d.get("reason", ""),
                        "source":     "llm"
                    }
                except Exception:
                    pass

        lower = text.lower()
        if any(w in lower for w in ["sad","depressed","tired","hurt","cry","dukh"]):
            return {"emotion": "sad",     "confidence": 0.65, "source": "keyword"}
        if any(w in lower for w in ["angry","frustrated","rage","gussa","hate"]):
            return {"emotion": "angry",   "confidence": 0.65, "source": "keyword"}
        if any(w in lower for w in ["scared","afraid","fear","dar","anxious"]):
            return {"emotion": "fear",    "confidence": 0.65, "source": "keyword"}
        if any(w in lower for w in ["happy","excited","great","awesome","mast","khushi"]):
            return {"emotion": "happy",   "confidence": 0.65, "source": "keyword"}
        if any(w in lower for w in ["confused","samajh nahi","don't understand"]):
            return {"emotion": "confused","confidence": 0.60, "source": "keyword"}
        return {"emotion": "neutral", "confidence": 0.5, "source": "keyword"}

    # ── Vision ────────────────────────────────────────────────────────

    def describe_image(self, image_source: Any, user_id: str = "default") -> str:
        if not self.vision_client:
            return "Image understanding is not configured yet."
        try:
            result = self.vision_client(image_source, task="describe", meta={"user_id": user_id})
            return result if isinstance(result, str) else result.get("description", str(result))
        except Exception as e:
            logger.exception("vision describe error: %s", e)
            return "I failed to analyse the image."

    def analyze_image_emotion(self, image_source: Any, user_id: str = "default") -> Dict[str, Any]:
        if not self.vision_client:
            return {"emotion": "neutral", "confidence": 0.0, "error": "not configured"}
        try:
            result = self.vision_client(image_source, task="emotion", meta={"user_id": user_id})
            if isinstance(result, dict):
                result.setdefault("source", "vision_client")
                return result
            return {"emotion": "unknown", "confidence": 0.0, "raw": str(result)}
        except Exception as e:
            logger.exception("vision emotion error: %s", e)
            return {"emotion": "unknown", "confidence": 0.0, "error": str(e)}

    # ── Audio ─────────────────────────────────────────────────────────

    def analyze_audio_emotion(self, audio_source: Any, user_id: str = "default") -> Dict[str, Any]:
        if not self.audio_client:
            return {"emotion": "neutral", "confidence": 0.0, "error": "not configured"}
        try:
            result = self.audio_client(audio_source, task="emotion", meta={"user_id": user_id})
            if isinstance(result, dict):
                result.setdefault("source", "audio_client")
                return result
            return {"emotion": "unknown", "confidence": 0.0, "raw": str(result)}
        except Exception as e:
            logger.exception("audio emotion error: %s", e)
            return {"emotion": "unknown", "confidence": 0.0, "error": str(e)}


# ======================================================================
#  AIKnowledgeFacade  —  stable public API
# ======================================================================

class AIKnowledgeFacade:

    SMALL_TALK = {
        "greeting": ["Hello! How can I help?", "Hi! Radhe here.", "Namaste! What can I do for you?"],
        "thanks":   ["You're welcome!", "Happy to help!", "Anytime!"],
        "goodbye":  ["Goodbye! Take care.", "See you later!", "Radhe signing off, bye!"],
        "unknown":  ["I'm not fully sure. Want me to search Wikipedia?",
                     "I'm still learning this one."],
    }

    def __init__(self, brain: RadheBrain):
        self.brain = brain

    def describe_self(self) -> str:
        return (
            "I'm Radhe, your personal AI companion running on your own system. "
            "I can open apps, search the web, set reminders, send WhatsApp messages, "
            "answer questions, control your system, check your screen, and much more."
        )

    def _small_talk(self, q: str) -> Optional[str]:
        text = (q or "").lower()
        if any(w in text for w in ("hello", "hi ", "hey", "namaste")):
            return random.choice(self.SMALL_TALK["greeting"])
        if any(w in text for w in ("thank", "thanks", "thx", "shukriya")):
            return random.choice(self.SMALL_TALK["thanks"])
        if any(w in text for w in ("bye", "goodbye", "see you", "good night")):
            return random.choice(self.SMALL_TALK["goodbye"])
        if "how are you" in text or "kaisa hai" in text:
            return "I'm doing great and always ready to help. How are you?"
        return None

    def _wiki_answer(self, question: str) -> Optional[str]:
        try:
            results = wikipedia.search(question)
            if not results:
                return None
            summary = wikipedia.summary(results[0], sentences=2)
            return f"According to Wikipedia: {summary}"
        except wikipedia.DisambiguationError as e:
            return f"Multiple Wikipedia results: {', '.join(e.options[:3])}."
        except Exception:
            return None

    def answer_question(
        self,
        question:    str,
        user_id:     str = "default",
        history:     Optional[List[Dict]] = None,
        mode:        str = "neutral",
        language:    str = "en",
        last_intent: str = "",
        profile:     Optional[Dict] = None,
    ) -> str:
        q = (question or "").strip()
        if not q:
            return "I didn't catch that. Could you repeat?"

        # 1) LLM (richest response)
        try:
            ans = self.brain.chat(q, user_id=user_id, history=history or [],
                                  mode=mode, language=language)
            if ans:
                return ans
        except Exception as e:
            logger.exception("brain.chat error: %s", e)

        # 2) Small-talk fallback
        st = self._small_talk(q)
        if st:
            return st

        # 3) Wikipedia fallback
        wiki = self._wiki_answer(q)
        if wiki:
            return wiki

        return random.choice(self.SMALL_TALK["unknown"])

    def wikipedia_search(self, topic: str) -> str:
        topic = (topic or "").strip()
        if not topic:
            return "Please tell me what to search on Wikipedia."
        try:
            results = wikipedia.search(topic)
            if not results:
                return f"Nothing found for '{topic}' on Wikipedia."
            summary = wikipedia.summary(results[0], sentences=3)
            return f"Here's what I found: {summary}"
        except wikipedia.DisambiguationError as e:
            return f"Multiple pages for '{topic}': {', '.join(e.options[:5])}."
        except Exception as e:
            logger.exception("wikipedia_search error: %s", e)
            return "Wikipedia search failed."

    def analyze_emotion(self, text: str, user_id: str = "default") -> Dict[str, Any]:
        try:
            return self.brain.analyze_text_emotion(text, user_id=user_id)
        except Exception as e:
            logger.exception("analyze_emotion error: %s", e)
            return {"emotion": "neutral", "confidence": 0.0, "source": "error"}

    def describe_image(self, image_source: Any, user_id: str = "default") -> str:
        return self.brain.describe_image(image_source, user_id=user_id)

    def analyze_image_emotion(self, image_source: Any, user_id: str = "default") -> Dict[str, Any]:
        return self.brain.analyze_image_emotion(image_source, user_id=user_id)

    def analyze_audio_emotion(self, audio_source: Any, user_id: str = "default") -> Dict[str, Any]:
        return self.brain.analyze_audio_emotion(audio_source, user_id=user_id)


# ======================================================================
#  Global instances
# ======================================================================

_memory      = RadheMemory()
brain        = RadheBrain(memory=_memory)
ai_knowledge = AIKnowledgeFacade(brain)