#ai_knowledge.py

"""
----------------
Single merged intelligence module for Radhe.

Includes:
- RadheMemory: simple JSON-based long-term memory (habits, profile).
- RadheBrain: main brain (LLM + optional image/audio clients).
    * chat()                  -> ChatGPT-style conversation
    * interpret_intent()      -> intent + entities for commands
    * analyze_text_emotion()  -> mood from text
    * describe_image()        -> what is in an image
    * analyze_image_emotion() -> emotion from image (hook)
    * analyze_audio_emotion() -> tone/emotion from audio (hook)
- AIKnowledgeFacade (ai_knowledge):
    * answer_question()
    * wikipedia_search()
    * analyze_emotion()
    * describe_image()
    * analyze_audio_emotion()
"""

import json
import logging
import os
import random
from typing import Optional, Callable, Dict, Any

import wikipedia

logger = logging.getLogger("Radhe_AI")
logger.setLevel(logging.INFO)
wikipedia.set_lang("en")

DEFAULT_MEMORY_FILE = "radhe_memory.json"


# ========================
#  RadheMemory
# ========================

class RadheMemory:
    """
    Very simple JSON-based memory:
    - Stores per-user profile, habits, preferences.
    - You can later replace this with SQLite easily.
    """

    def __init__(self, path: str = DEFAULT_MEMORY_FILE):
        self.path = path
        self._data: Dict[str, Any] = {}
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except Exception:
                self._data = {}
        else:
            self._data = {}

    def _save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.exception("Failed to save memory: %s", e)

    def _ensure_user(self, user_id: str):
        if user_id not in self._data:
            self._data[user_id] = {
                "profile": {},
                "history": []
            }

    def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        self._ensure_user(user_id)
        return self._data[user_id].get("profile", {})

    def update_user_profile(self, user_id: str, updates: Dict[str, Any]):
        self._ensure_user(user_id)
        self._data[user_id]["profile"].update(updates)
        self._save()

    def add_history_event(self, user_id: str, event: Dict[str, Any]):
        self._ensure_user(user_id)
        self._data[user_id]["history"].append(event)
        self._save()


# ========================
#  RadheBrain
# ========================

class RadheBrain:
    """
    Radhe Brain:
    - Wraps LLM + optional vision/audio clients.
    - Handles intent, Q&A, emotion, and memory.
    """

    def __init__(
        self,
        llm_client: Optional[Callable[[str, Dict[str, Any]], str]] = None,
        vision_client: Optional[Callable[[Any, str, Dict[str, Any]], Any]] = None,
        audio_client: Optional[Callable[[Any, str, Dict[str, Any]], Any]] = None,
        memory: Optional[RadheMemory] = None,
    ):
        """
        llm_client(prompt:str, meta:dict) -> str
            meta may contain: {"mode": "chat/intent/emotion", "user_id": "..."}
        vision_client(image, task:str, meta:dict) -> Any
        audio_client(audio, task:str, meta:dict) -> Any
        """
        self.llm_client = llm_client
        self.vision_client = vision_client
        self.audio_client = audio_client
        self.memory = memory or RadheMemory()

    # ---- LLM helper ----

    def _call_llm(self, prompt: str, mode: str, user_id: str, extra: Optional[Dict[str, Any]] = None) -> Optional[str]:
        if not self.llm_client:
            return None
        meta = {"mode": mode, "user_id": user_id}
        if extra:
            meta.update(extra)
        try:
            return self.llm_client(prompt, meta)
        except Exception as e:
            logger.exception("LLM client error: %s", e)
            return None

    # ---- Memory helpers ----

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

    # ---- Chat ----

    def chat(self, message: str, user_id: str = "default", extra_context: Optional[str] = None) -> str:
        """
        High-level chat interface.
        If LLM is available, this is where you get ChatGPT-style replies.
        Otherwise simple fallback is used.
        """
        message = (message or "").strip()
        if not message:
            return "I didn't receive anything to respond to."

        profile = self.get_profile(user_id)
        profile_text = json.dumps(profile, ensure_ascii=False)

        base_prompt = f"""
You are Radhe, a helpful personal AI assistant.

User profile (from memory, may be partial):
{profile_text}

User says: \"{message}\"

If the user is emotional, respond calmly and supportively.
If the user asks for facts, be clear and structured.
If you don't know something exactly, admit it politely.

Respond in a natural tone, mixing Hindi+English if user does so.
"""

        if extra_context:
            base_prompt += f"\nAdditional context:\n{extra_context}\n"

        llm_response = self._call_llm(base_prompt, mode="chat", user_id=user_id)
        if llm_response:
            self.add_history(user_id, {"type": "chat", "user": message, "radhe": llm_response})
            return llm_response.strip()

        # Fallback if no LLM configured
        self.add_history(user_id, {"type": "chat", "user": message, "radhe": "fallback"})
        return f"(Brain offline fallback) You said: {message}"

    # ---- Intent + entities ----

    def interpret_intent(self, text: str, user_id: str = "default") -> Dict[str, Any]:
        """
        Ask Brain to convert free text into structured intent/entities.
        Expected output format from LLM should be JSON.
        """
        text = (text or "").strip()
        if not text:
            return {"intent": "none", "entities": {}, "confidence": 0.0}

        prompt = f"""
You are the intent engine for Radhe.

User message: \"{text}\"

Return a JSON object with:
- "intent": one of ["greeting","thanks","goodbye","open_app","close_app",
                    "open_website","search_web","set_reminder","send_message",
                    "system_control","ask_question","unknown"]
- "entities": a JSON object with keys depending on intent:
    - open_app:        application
    - close_app:       application
    - open_website:    website
    - search_web:      query
    - set_reminder:    reminder_text, time
    - send_message:    platform, contact, message
    - system_control:  control_type
    - ask_question:    question
- "confidence": a number between 0 and 1.

If unsure, use intent "unknown" with confidence <= 0.4.

Respond ONLY with JSON. No extra text.
"""

        llm_response = self._call_llm(prompt, mode="intent", user_id=user_id)
        if not llm_response:
            return {"intent": "unknown", "entities": {}, "confidence": 0.0}

        try:
            data = json.loads(llm_response)
            intent = data.get("intent", "unknown")
            entities = data.get("entities", {}) or {}
            confidence = float(data.get("confidence", 0.4))
            return {"intent": intent, "entities": entities, "confidence": confidence}
        except Exception:
            logger.debug("Failed to parse Brain intent JSON: %s", llm_response)
            return {"intent": "unknown", "entities": {}, "confidence": 0.0}

    # ---- Text emotion ----

    def analyze_text_emotion(self, text: str, user_id: str = "default") -> Dict[str, Any]:
        """
        Analyze emotion from plain text.
        If LLM present, ask it. Otherwise simple keyword-based fallback.
        """
        text = (text or "").strip()
        if not text:
            return {"emotion": "neutral", "confidence": 0.0, "source": "none"}

        # If LLM present, ask for emotion
        if self.llm_client:
            prompt = f"""
User text: \"{text}\"

Classify the primary emotion as one of:
["happy","sad","angry","fear","surprise","disgust","neutral","stressed","confused"].

Return a JSON object:
{{
  "emotion": "<one label>",
  "confidence": 0.0-1.0,
  "reason": "<short explanation>"
}}

Respond ONLY with JSON.
"""
            resp = self._call_llm(prompt, mode="text_emotion", user_id=user_id)
            if resp:
                try:
                    data = json.loads(resp)
                    return {
                        "emotion": data.get("emotion", "neutral"),
                        "confidence": float(data.get("confidence", 0.7)),
                        "reason": data.get("reason", ""),
                        "source": "llm"
                    }
                except Exception:
                    pass

        # Fallback simple keyword-based
        lower = text.lower()
        if any(w in lower for w in ["sad", "depressed", "tired", "hurt", "cry"]):
            emotion = "sad"
        elif any(w in lower for w in ["angry", "frustrated", "rage", "gussa"]):
            emotion = "angry"
        elif any(w in lower for w in ["scared", "afraid", "fear", "dar", "anxious"]):
            emotion = "fear"
        elif any(w in lower for w in ["happy", "excited", "great", "awesome", "mast"]):
            emotion = "happy"
        elif any(w in lower for w in ["confused", "don't understand", "samajh ny aa rha"]):
            emotion = "confused"
        else:
            emotion = "neutral"

        return {"emotion": emotion, "confidence": 0.6, "source": "keyword"}

    # ---- Image understanding ----

    def describe_image(self, image_source: Any, user_id: str = "default") -> str:
        """
        Describe what is in an image.
        image_source: file path / URL / bytes (depends on your vision_client).
        """
        if not self.vision_client:
            return "Image understanding is not configured yet."

        try:
            result = self.vision_client(image_source, task="describe", meta={"user_id": user_id})
            if isinstance(result, str):
                return result
            if isinstance(result, dict) and "description" in result:
                return result["description"]
            return str(result)
        except Exception as e:
            logger.exception("vision_client describe error: %s", e)
            return "I failed to analyze the image."

    def analyze_image_emotion(self, image_source: Any, user_id: str = "default") -> Dict[str, Any]:
        """
        Analyze emotion / mood from an image (e.g., face).
        """
        if not self.vision_client:
            return {"emotion": "neutral", "confidence": 0.0, "error": "vision_client not configured"}

        try:
            result = self.vision_client(image_source, task="emotion", meta={"user_id": user_id})
            if isinstance(result, dict):
                result.setdefault("source", "vision_client")
                return result
            return {"emotion": "unknown", "confidence": 0.0, "raw": str(result), "source": "vision_client"}
        except Exception as e:
            logger.exception("vision_client emotion error: %s", e)
            return {"emotion": "unknown", "confidence": 0.0, "error": str(e)}

    # ---- Audio emotion ----

    def analyze_audio_emotion(self, audio_source: Any, user_id: str = "default") -> Dict[str, Any]:
        """
        Analyze emotion / tone from an audio clip (voice).
        audio_source can be a file path, URL, or bytes.
        """
        if not self.audio_client:
            return {"emotion": "neutral", "confidence": 0.0, "error": "audio_client not configured"}

        try:
            result = self.audio_client(audio_source, task="emotion", meta={"user_id": user_id})
            if isinstance(result, dict):
                result.setdefault("source", "audio_client")
                return result
            return {"emotion": "unknown", "confidence": 0.0, "raw": str(result), "source": "audio_client"}
        except Exception as e:
            logger.exception("audio_client error: %s", e)
            return {"emotion": "unknown", "confidence": 0.0, "error": str(e)}


# ========================
#  AIKnowledgeFacade
# ========================

class AIKnowledgeFacade:
    """
    Thin wrapper for RadheBrain + Wikipedia + small-talk.
    Backward compatible:
    - ai_knowledge.answer_question()
    - ai_knowledge.wikipedia_search()
    - ai_knowledge.analyze_emotion()
    """

    def __init__(self, brain: RadheBrain):
        self.brain = brain

        self.common = {
            "greeting": [
                "Hello! How can I help you today?",
                "Hi there! Radhe here.",
                "Namaste! What can I do for you?"
            ],
            "thanks": [
                "You're welcome!",
                "Happy to help!",
                "No problem, anytime."
            ],
            "goodbye": [
                "Goodbye! Take care.",
                "See you later!",
                "Radhe signing off, bye!"
            ],
            "unknown": [
                "I'm not fully sure about that yet. Want me to search Wikipedia for you?",
                "I don't have a perfect answer yet, but I can try checking Wikipedia.",
                "I'm still learning this. Let me try a quick knowledge lookup."
            ]
        }

    def _small_talk(self, q: str) -> Optional[str]:
        text = (q or "").lower()

        if any(w in text for w in ("hello", "hi", "hey", "namaste", "good morning", "good evening")):
            return random.choice(self.common["greeting"])

        if any(w in text for w in ("thank", "thanks", "thx", "shukriya")):
            return random.choice(self.common["thanks"])

        if any(w in text for w in ("bye", "goodbye", "see you", "good night")):
            return random.choice(self.common["goodbye"])

        if "how are you" in text or "kaisa hai" in text:
            return "I'm doing great and always ready to help you. How are you?"

        return None

    def _wiki_answer(self, question: str) -> Optional[str]:
        try:
            results = wikipedia.search(question)
            if not results:
                return None
            summary = wikipedia.summary(results[0], sentences=2)
            return f"According to Wikipedia: {summary}"
        except wikipedia.DisambiguationError as e:
            opts = ", ".join(e.options[:3])
            return f"There are multiple possible results on Wikipedia: {opts}."
        except Exception as e:
            logger.debug("Wikipedia error: %s", e)
            return None

    # ---- Public methods ----

    def answer_question(self, question: str, user_id: str = "default") -> str:
        q = (question or "").strip()
        if not q:
            return "I didn't receive any question. Can you repeat that?"

        # Small talk first
        st = self._small_talk(q)
        if st:
            return st

        # Brain chat
        try:
            ans = self.brain.chat(q, user_id=user_id)
            if ans:
                return ans
        except Exception as e:
            logger.exception("Error in brain.chat: %s", e)

        # Wikipedia fallback
        wiki_ans = self._wiki_answer(q)
        if wiki_ans:
            return wiki_ans

        return random.choice(self.common["unknown"])

    def wikipedia_search(self, topic: str) -> str:
        topic = (topic or "").strip()
        if not topic:
            return "Please tell me what topic to search on Wikipedia."

        try:
            results = wikipedia.search(topic)
            if not results:
                return f"I couldn't find anything about '{topic}' on Wikipedia."
            summary = wikipedia.summary(results[0], sentences=3)
            return f"Here's what I found on Wikipedia: {summary}"
        except wikipedia.DisambiguationError as e:
            opts = ", ".join(e.options[:5])
            return f"There are multiple pages for '{topic}'. Some options are: {opts}."
        except Exception as e:
            logger.exception("wikipedia_search error: %s", e)
            return "Wikipedia search failed due to an error."

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


# ================
# Global instances
# ================

_memory = RadheMemory()
brain = RadheBrain(memory=_memory)
ai_knowledge = AIKnowledgeFacade(brain)
# Now ai_knowledge can be imported and used elsewhere