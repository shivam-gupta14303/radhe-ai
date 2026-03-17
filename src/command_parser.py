"""
command_parser.py
------------------
- Returns: {intent, entities, confidence}
- No side effects.
- Flow:
    1) High-priority meta detection (boundaries, language/mode changes, smalltalk, persona).
    2) Try Brain.interpret_intent() if LLM (Ollama) connected.
    3) If low confidence / no brain -> regex + heuristics.
"""

import re
import logging
from typing import Dict, Any, Optional


logger = logging.getLogger("Radhe_CommandParser")
logger.setLevel(logging.INFO)


INTENTS = [
    # ---- SMALL / META ----
    {
        "id": "greeting",
        "patterns": [
            r"\bhi\b",
            r"\bhello\b",
            r"\bhey\b",
            r"\bnamaste\b",
            r"\bsalam\b",
            r"\bhey radhe\b",
            r"\bhello radhe\b",
            r"\bhi radhe\b",
        ],
        "slots": []
    },
    {
        "id": "thanks",
        "patterns": [
            r"\bthank(s| you)\b",
            r"\bshukriya\b",
            r"\bthanks a lot\b"
        ],
        "slots": []
    },
    {
        "id": "goodbye",
        "patterns": [
            r"\bbye\b",
            r"\bgoodbye\b",
            r"\bsee you\b",
            r"\bphir milte\b"
        ],
        "slots": []
    },
    {
        "id": "conversation_smalltalk",
        "patterns": [
            r"\bhow are you\b",
            r"\bhow're you\b",
            r"\bhow r u\b",
            r"\bhru\b",
            r"\bhow's your day\b",
            r"\bhow is your day\b",
            r"\bhow have you been\b",
            r"\bhow's it going\b",
            r"\bwhat's up\b",
            r"\bwhats up\b",
            r"\bkaisa hai\b",
            r"\bkaisi ho\b",
            r"\bdin kaisa (tha|gaya|raha)\b",
        ],
        "slots": []
    },
    {
        "id": "persona_query",
        "patterns": [
            r"\bwho are you\b",
            r"\bwhat are you\b",
            r"\bwhat can you do\b",
            r"\btell me about you\b",
            r"\btell me something about you\b",
            r"\babout yourself\b",
            r"\babout you\b",
            r"\bwhat is your name\b",
            r"\bintroduce yourself\b",
            r"\bwho exactly are you\b",
        ],
        "slots": []
    },
    {
        "id": "change_language",
        "patterns": [
            r"\b(can you|please)?\s*(talk|speak|reply|respond)\s*(in)?\s*hindi\b",
            r"\bhindi mein baat karo\b",
            r"\bhindi me baat karo\b",
            r"\bhindi me bolo\b",
            r"\bhindi mein bolo\b",
            r"\b(can you|please)?\s*(talk|speak|reply|respond)\s*(in)?\s*english\b",
            r"\benglish mein baat karo\b",
            r"\benglish me baat karo\b",
            r"\benglish me bolo\b",
        ],
        "slots": ["target_language"]
    },
    {
        "id": "change_mode",
        "patterns": [
            r"\bcan we talk normally\b",
            r"\btalk normally\b",
            r"\bnormal talk\b",
            r"\bcasual talk\b",
            r"\bbaat normal karo\b",
            r"\bzyada formal mat ho\b",
            r"\bdon't be so formal\b",
            r"\bspeak casually\b",
            r"\bformal mode\b",
            r"\bformal baat\b",
        ],
        "slots": ["target_mode"]
    },
    {
        "id": "user_boundary",
        "patterns": [
            r"\bdon't call me\s+(?P<disallowed_term>[^\s,.!?]+)",
            r"\bdo not call me\s+(?P<disallowed_term>[^\s,.!?]+)",
            r"\bmujhe\s+(?P<disallowed_term>[^\s,.!?]+)\s+mat bolo\b",
            r"\bmujhe\s+(?P<disallowed_term>[^\s,.!?]+)\s+mat kehna\b",
        ],
        "slots": ["disallowed_term"]
    },

    # ---- TIME / DATE ----
    {
        "id": "get_time",
        "patterns": [
            r"\bwhat(?:'s| is)? the time\b",
            r"\bkya time\b",
            r"\bcurrent time\b",
            r"\btime bata\b"
        ],
        "slots": []
    },
    {
        "id": "get_date",
        "patterns": [
            r"\bwhat(?:'s| is)? the date\b",
            r"\baaj ki date\b",
            r"\bdate bata\b",
            r"\bwhich day is today\b"
        ],
        "slots": []
    },

    # ---- APPS / WEB ----
    {
        "id": "open_app",
        "patterns": [
            r"\bopen (?:the )?(?P<application>[\w\s\-\.]+)",
            r"\blaunch (?P<application>[\w\s\-\.]+)"
        ],
        "slots": ["application"]
    },
    {
        "id": "close_app",
        "patterns": [
            r"\b(close|kill|terminate)\s+(?P<application>[\w\s\-\.]+)"
        ],
        "slots": ["application"]
    },
    {
        "id": "open_website",
        "patterns": [
            r"\b(open|go to|visit)\s+(?P<website>[\w\.\-]+(?:\s[\w\.\-]+)*)"
        ],
        "slots": ["website"]
    },
    {
        "id": "search_web",
        "patterns": [
            r"\b(search for|find|look up)\s+(?P<query>.+)"
        ],
        "slots": ["query"]
    },

    # ---- REMINDER ----
    {
        "id": "set_reminder",
        "patterns": [
            r"\b(remind me to|set a reminder to)\s+(?P<reminder_text>.+?)(?: at | on | in |$)(?P<time>.*)",
            r"\bremind me in\s+(?P<time>.+?)\s+to\s+(?P<reminder_text>.+)"
        ],
        "slots": ["reminder_text", "time"]
    },

    # ---- MESSAGING ----
    {
        "id": "send_message",
        "patterns": [
            r"\b(send|message)\s+(?P<contact>[\w\s]+)\s+(?:on|via)?\s*(?P<platform>[\w]+)?\s*(?:saying|:)?\s*(?P<message>.+)",
            r"(?P<platform>whatsapp|telegram|instagram|twitter|snapchat|sms|email|gmail)?\s*(?:pe|par)?\s*(?P<contact>[\w\s]+)\s+ko\s+(?:bol|message|msg)\s+(?P<message>.+)"
        ],
        "slots": ["contact", "platform", "message"]
    },

    # ---- SYSTEM CONTROL ----
    {
        "id": "system_control",
        "patterns": [
            r"\b(?P<control_type>shutdown|restart|reboot|sleep|hibernate|lock|logout|sign out)\b"
        ],
        "slots": ["control_type"]
    },

    # ---- NLP / TEXT TOOLS ----
    {
        "id": "summarize_text",
        "patterns": [
            r"\bsummarize\b",
            r"\bsummary\b",
            r"\bsum up\b",
            r"\bsaaransh\b",
            r"\bsaransh\b",
        ],
        "slots": []
    },
    {
        "id": "sentiment_check",
        "patterns": [
            r"\bsentiment\b",
            r"\bemotion check\b",
            r"\bfeeling check\b",
            r"\bmood check\b",
            r"\bhow does this feel\b",
        ],
        "slots": []
    },
    {
        "id": "keyword_extract",
        "patterns": [
            r"\bkeywords?\b",
            r"\bimportant words\b",
            r"\btopic extract\b",
        ],
        "slots": []
    },

    # ---- GENERIC QUESTION / Q&A ----
    {
        "id": "ask_question",
        "patterns": [
            r"^(?P<question>.+\?)$",
            r"^(?P<question>(what|who|how|when|where|why)\b.*)",
        ],
        "slots": ["question"]
    }
]

# compile regex once
for intent in INTENTS:
    intent["compiled"] = [re.compile(p, flags=re.IGNORECASE) for p in intent["patterns"]]


class CommandParser:
    """
    Pure parser:
    - parse(text, user_id) -> {intent, entities, confidence}
    - Uses Brain (Ollama / LLM) if available,
      with guardrails for core conversational behaviours.
    """

    def __init__(self):
         # lazy import to avoid circular import
        from src.ai_knowledge import brain
        self.brain = brain  # global brain from ai_knowledge

    # ---------- HIGH PRIORITY META DETECTOR ----------
    def _detect_meta_intent(self, norm: str, lower: str) -> Optional[Dict[str, Any]]:
        """
        Hand-crafted rules for:
        - smalltalk ("how are you")
        - persona ("who are you")
        - language switch ("talk in hindi/english")
        - mode switch ("talk normally")
        - user boundary ("don't call me beta")
        These fire BEFORE LLM + regex, so behaviour is consistent and not limited.
        """

        # 1) User boundary
        if ("don't call me" in lower) or ("do not call me" in lower) or ("mat bolo" in lower) or ("mat kehna" in lower):
            m = re.search(r"(?:don't call me|do not call me)\s+([^\s,.!?]+)", lower)
            term = None
            if m:
                term = m.group(1)
            else:
                m2 = re.search(r"mujhe\s+([^\s,.!?]+)\s+mat (?:bolo|kehna)", lower)
                if m2:
                    term = m2.group(1)

            entities = {}
            if term:
                entities["disallowed_term"] = term
            return {
                "intent": "user_boundary",
                "entities": entities,
                "confidence": 0.98
            }

        # 2) Language change
        if "hindi" in lower and any(w in lower for w in ["talk", "speak", "baat", "bolo", "respond", "reply"]):
            return {
                "intent": "change_language",
                "entities": {"target_language": "hi"},
                "confidence": 0.96
            }
        if "english" in lower and any(w in lower for w in ["talk", "speak", "baat", "bolo", "respond", "reply"]):
            return {
                "intent": "change_language",
                "entities": {"target_language": "en"},
                "confidence": 0.96
            }

        # 3) Mode change (formal / casual / normal talk)
        if ("talk normally" in lower or
            "can we talk normally" in lower or
            "normal talk" in lower or
            "casual talk" in lower or
            "baat normal" in lower or
            "bina formal" in lower or
            "don't be so formal" in lower):
            target = "casual"
            if any(w in lower for w in ["formal mode", "formal baat", "be formal"]):
                target = "formal"
            return {
                "intent": "change_mode",
                "entities": {"target_mode": target},
                "confidence": 0.95
            }

        # 4) Smalltalk
        if ("how are you" in lower or
            "how're you" in lower or
            "how r u" in lower or
            "hru" in lower or
            "how's your day" in lower or
            "how is your day" in lower or
            "how have you been" in lower or
            "how's it going" in lower or
            "what's up" in lower or
            "whats up" in lower or
            "kaisa hai" in lower or
            "kaisi ho" in lower or
            "din kaisa" in lower):
            return {
                "intent": "conversation_smalltalk",
                "entities": {},
                "confidence": 0.93
            }

        # 5) Persona query
        if ("who are you" in lower or
            "what are you" in lower or
            "what can you do" in lower or
            "tell me about you" in lower or
            "tell me something about you" in lower or
            "about yourself" in lower or
            "about you" in lower or
            "introduce yourself" in lower or
            "your name" in lower):
            return {
                "intent": "persona_query",
                "entities": {},
                "confidence": 0.94
            }

        return None

    def parse(self, text: str, user_id: str = "default") -> Dict[str, Any]:
        text = (text or "").strip()
        if not text:
            return {"intent": "none", "entities": {}, "confidence": 0.0}

        norm = re.sub(r"\s+", " ", text).strip()
        lower = norm.lower()

        # 0) HIGH PRIORITY META HANDLING
        meta = self._detect_meta_intent(norm, lower)
        if meta:
            return meta

        # 1) TRY BRAIN FIRST (if LLM configured, e.g. Ollama)
        if self.brain and getattr(self.brain, "llm_client", None):
            try:
                brain_result = self.brain.interpret_intent(norm, user_id=user_id) or {}
                b_intent = brain_result.get("intent")
                b_conf = float(brain_result.get("confidence", 0.0))

                # safety: if brain mislabels smalltalk/persona as greeting
                if b_intent == "greeting" and (
                    "how are you" in lower or
                    "who are you" in lower or
                    "about you" in lower or
                    "about yourself" in lower
                ):
                    b_intent = "conversation_smalltalk"
                    b_conf = max(b_conf, 0.7)

                if b_intent and b_conf >= 0.55:
                    return {
                        "intent": b_intent,
                        "entities": brain_result.get("entities", {}) or {},
                        "confidence": b_conf
                    }
            except Exception as e:
                logger.exception("Brain interpret_intent error: %s", e)

        # 2) Regex-based INTENTS (fallback / offline)
        best_match: Optional[Dict[str, Any]] = None

        for intent in INTENTS:
            for comp in intent["compiled"]:
                m = comp.search(norm)
                if m:
                    entities = {
                        k: v.strip()
                        for k, v in (m.groupdict() or {}).items()
                        if v
                    }

                    # post-process for language/mode defaults
                    if intent["id"] == "change_language" and "target_language" not in entities:
                        if "hindi" in lower:
                            entities["target_language"] = "hi"
                        elif "english" in lower:
                            entities["target_language"] = "en"
                    if intent["id"] == "change_mode" and "target_mode" not in entities:
                        if "casual" in lower or "normal" in lower:
                            entities["target_mode"] = "casual"
                        elif "formal" in lower:
                            entities["target_mode"] = "formal"

                    for s in intent.get("slots", []):
                        entities.setdefault(s, "")

                    best_match = {
                        "intent": intent["id"],
                        "entities": entities,
                        "confidence": 1.0
                    }
                    break
            if best_match:
                break

        # 3) Heuristic fallback
        if not best_match:
            if any(w in lower for w in ["thank", "thanks", "shukriya"]):
                best_match = {"intent": "thanks", "entities": {}, "confidence": 0.8}
            elif any(w in lower for w in ["hi", "hello", "hey", "namaste"]) and not any(
                q in lower for q in ["how are you", "who are you", "about yourself", "talk normally", "hindi", "english"]
            ):
                best_match = {"intent": "greeting", "entities": {}, "confidence": 0.8}
            elif any(w in lower for w in ["bye", "goodbye", "see you"]):
                best_match = {"intent": "goodbye", "entities": {}, "confidence": 0.8}
            elif any(w in lower for w in ["summarize", "summary", "saransh", "saaransh"]):
                best_match = {"intent": "summarize_text", "entities": {}, "confidence": 0.75}
            elif "sentiment" in lower or "mood" in lower or "emotion" in lower:
                best_match = {"intent": "sentiment_check", "entities": {}, "confidence": 0.75}
            elif "keyword" in lower or "important words" in lower:
                best_match = {"intent": "keyword_extract", "entities": {}, "confidence": 0.75}
            elif lower.endswith("?") or any(lower.startswith(q) for q in ("what", "who", "how", "when", "where", "why")):
                best_match = {
                    "intent": "ask_question",
                    "entities": {"question": norm},
                    "confidence": 0.6
                }
            else:
                best_match = {"intent": "unknown", "entities": {}, "confidence": 0.25}

        return best_match


# global instance
parser = CommandParser()
