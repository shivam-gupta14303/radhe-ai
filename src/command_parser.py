# src/command_parser.py
"""
CommandParser for Radhe.

Updated with ALL new intents:
- list_reminders, cancel_reminder
- get_battery, set_volume, take_screenshot, analyze_screen
- youtube_search, get_directions, get_weather, get_news
- set_timer, start_stopwatch, stop_stopwatch
- file_search
- check_internet
"""

import re
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("Radhe_CommandParser")
logger.setLevel(logging.INFO)


# ======================================================================
#  INTENT DEFINITIONS
# ======================================================================

INTENTS = [

    # ── META / CONVERSATION ───────────────────────────────────────────
    {
        "id": "greeting",
        "patterns": [
            r"\bhi\b", r"\bhello\b", r"\bhey\b",
            r"\bnamaste\b", r"\bsalam\b",
            r"\bhey radhe\b", r"\bhello radhe\b", r"\bhi radhe\b",
        ],
        "slots": []
    },
    {
        "id": "thanks",
        "patterns": [
            r"\bthank(s| you)\b", r"\bshukriya\b", r"\bthanks a lot\b"
        ],
        "slots": []
    },
    {
        "id": "goodbye",
        "patterns": [
            r"\bbye\b", r"\bgoodbye\b", r"\bsee you\b", r"\bphir milte\b"
        ],
        "slots": []
    },
    {
        "id": "conversation_smalltalk",
        "patterns": [
            r"\bhow are you\b", r"\bhow're you\b", r"\bhow r u\b", r"\bhru\b",
            r"\bhow.s your day\b", r"\bhow is your day\b",
            r"\bhow have you been\b", r"\bhow.s it going\b",
            r"\bwhat.s up\b", r"\bwhats up\b",
            r"\bkaisa hai\b", r"\bkaisi ho\b", r"\bdin kaisa\b",
        ],
        "slots": []
    },
    {
        "id": "persona_query",
        "patterns": [
            r"\bwho are you\b", r"\bwhat are you\b", r"\bwhat can you do\b",
            r"\btell me about you\b", r"\babout yourself\b", r"\babout you\b",
            r"\bwhat is your name\b", r"\bintroduce yourself\b",
        ],
        "slots": []
    },
    {
        "id": "change_language",
        "patterns": [
            r"\b(talk|speak|reply|respond)\s*(in)?\s*hindi\b",
            r"\bhindi mein baat karo\b", r"\bhindi me bolo\b",
            r"\b(talk|speak|reply|respond)\s*(in)?\s*english\b",
            r"\benglish mein baat karo\b",
        ],
        "slots": ["target_language"]
    },
    {
        "id": "change_mode",
        "patterns": [
            r"\bcan we talk normally\b", r"\btalk normally\b",
            r"\bnormal talk\b", r"\bcasual talk\b",
            r"\bdon.t be so formal\b", r"\bspeak casually\b",
            r"\bformal mode\b", r"\bformal baat\b",
        ],
        "slots": ["target_mode"]
    },
    {
        "id": "user_boundary",
        "patterns": [
            r"\bdon.t call me\s+(?P<disallowed_term>[^\s,.!?]+)",
            r"\bdo not call me\s+(?P<disallowed_term>[^\s,.!?]+)",
            r"\bmujhe\s+(?P<disallowed_term>[^\s,.!?]+)\s+mat bolo\b",
            r"\bmujhe\s+(?P<disallowed_term>[^\s,.!?]+)\s+mat kehna\b",
        ],
        "slots": ["disallowed_term"]
    },

    # ── TIME / DATE ───────────────────────────────────────────────────
    {
        "id": "get_time",
        "patterns": [
            r"\bwhat.s the time\b", r"\bwhat is the time\b",
            r"\bcurrent time\b", r"\btime bata\b", r"\bkya time hai\b",
        ],
        "slots": []
    },
    {
        "id": "get_date",
        "patterns": [
            r"\bwhat.s the date\b", r"\bwhat is the date\b",
            r"\baaj ki date\b", r"\bdate bata\b",
            r"\bwhich day is today\b", r"\baaj kaun sa din hai\b",
        ],
        "slots": []
    },

    # ── APPS / WEBSITES ───────────────────────────────────────────────
    {
        "id": "open_app",
        "patterns": [
            r"\bopen (?:the )?(?P<application>[\w\s\-\.]+)",
            r"\blaunch (?P<application>[\w\s\-\.]+)",
            r"\bstart (?P<application>[\w\s\-\.]+)",
        ],
        "slots": ["application"]
    },
    {
        "id": "close_app",
        "patterns": [
            r"\b(close|kill|terminate|quit|band karo)\s+(?P<application>[\w\s\-\.]+)",
        ],
        "slots": ["application"]
    },
    {
        "id": "open_website",
        "patterns": [
            r"\b(open|go to|visit|jaao)\s+(?P<website>[\w\.\-]+(?:\s[\w\.\-]+)*)",
        ],
        "slots": ["website"]
    },

    # ── WEB SEARCH ────────────────────────────────────────────────────
    {
        "id": "search_web",
        "patterns": [
            r"\b(search for|find|look up|google)\s+(?P<query>.+)",
            r"\bsearch\s+(?P<query>.+)\s+on google\b",
        ],
        "slots": ["query"]
    },
    {
        "id": "youtube_search",
        "patterns": [
            r"\b(search|find|play|look up)\s+(?P<query>.+)\s+on youtube\b",
            r"\byoutube search\s+(?P<query>.+)",
            r"\byoutube pe\s+(?P<query>.+)\s+(dhundo|search karo)\b",
            r"\bsearch youtube for\s+(?P<query>.+)",
        ],
        "slots": ["query"]
    },

    # ── NAVIGATION ────────────────────────────────────────────────────
    {
        "id": "get_directions",
        "patterns": [
            r"\b(directions|route|how to go|rasta)\s+from\s+(?P<origin>[\w\s]+)\s+to\s+(?P<destination>[\w\s]+)",
            r"\bget directions to\s+(?P<destination>[\w\s]+)",
            r"\bnavigate to\s+(?P<destination>[\w\s]+)",
        ],
        "slots": ["origin", "destination"]
    },

    # ── WEATHER ───────────────────────────────────────────────────────
    {
        "id": "get_weather",
        "patterns": [
            r"\b(what.s the weather|weather in|mausam|weather forecast)\s*(?:in|for)?\s*(?P<location>[\w\s]*)",
            r"\bhow.s the weather\b",
            r"\bwill it rain\b",
        ],
        "slots": ["location"]
    },

    # ── NEWS ──────────────────────────────────────────────────────────
    {
        "id": "get_news",
        "patterns": [
            r"\b(show me news|latest news|what.s happening|news today|khabar)\b",
            r"\bnews about\s+(?P<topic>[\w\s]+)",
        ],
        "slots": ["topic"]
    },

    # ── REMINDERS ─────────────────────────────────────────────────────
    {
        "id": "set_reminder",
        "patterns": [
            r"\b(remind me to|set a reminder to|reminder for)\s+(?P<reminder_text>.+?)\s+(?:at|on|in)\s+(?P<time>.+)",
            r"\bremind me in\s+(?P<time>.+?)\s+to\s+(?P<reminder_text>.+)",
            r"\bset reminder\s+(?P<reminder_text>.+)\s+at\s+(?P<time>.+)",
        ],
        "slots": ["reminder_text", "time"]
    },
    {
        "id": "list_reminders",
        "patterns": [
            r"\b(what reminders|show reminders|list reminders|my reminders)\b",
            r"\b(kaun se reminders|reminders dikhao|kya reminder)\b",
            r"\bupcoming reminders\b",
        ],
        "slots": []
    },
    {
        "id": "cancel_reminder",
        "patterns": [
            r"\b(cancel|delete|remove|hatao)\s+(?:my\s+)?(?P<keyword>[\w\s]+)\s+reminder\b",
            r"\breminder cancel karo\s+(?P<keyword>[\w\s]+)",
        ],
        "slots": ["keyword"]
    },

    # ── MESSAGING ─────────────────────────────────────────────────────
    {
        "id": "send_message",
        "patterns": [
            r"\b(send|message|msg)\s+(?P<contact>[\w\s]+)\s+(?:on|via)?\s*(?P<platform>[\w]+)?\s*(?:saying|that|:)?\s*(?P<message>.+)",
            r"(?P<platform>whatsapp|telegram|instagram|sms|email|gmail)?\s*(?:pe|par)?\s*(?P<contact>[\w\s]+)\s+ko\s+(?:bol|message|msg)\s+(?P<message>.+)",
        ],
        "slots": ["contact", "platform", "message"]
    },

    # ── SYSTEM CONTROL ────────────────────────────────────────────────
    {
        "id": "system_control",
        "patterns": [
            r"\b(?P<control_type>shutdown|restart|reboot|sleep|hibernate|lock|logout)\b",
        ],
        "slots": ["control_type"]
    },
    {
        "id": "get_battery",
        "patterns": [
            r"\b(battery|battery status|battery level|how much battery|kitni battery)\b",
            r"\bcharging status\b",
        ],
        "slots": []
    },
    {
        "id": "set_volume",
        "patterns": [
            r"\b(set volume|volume set|volume ko)\s+(?:to\s+)?(?P<level>\d+)\s*(?:percent|%)?",
            r"\b(volume up|increase volume|louder|zyada awaz)\b",
            r"\b(volume down|decrease volume|quieter|kam awaz)\b",
        ],
        "slots": ["level"]
    },
    {
        "id": "take_screenshot",
        "patterns": [
            r"\b(take a screenshot|screenshot lo|capture screen|screenshot)\b",
        ],
        "slots": []
    },
    {
        "id": "analyze_screen",
        "patterns": [
            r"\b(what.s on my screen|read my screen|screen pe kya hai|describe screen)\b",
            r"\b(analyze screen|screen analyze karo)\b",
        ],
        "slots": []
    },

    # ── TIMER / STOPWATCH ─────────────────────────────────────────────
    {
        "id": "set_timer",
        "patterns": [
            r"\b(set a? timer|timer set karo)\s+(?:for\s+)?(?P<duration>[\d\w\s]+)",
            r"\b(timer for|timer of)\s+(?P<duration>[\d\w\s]+)",
        ],
        "slots": ["duration"]
    },
    {
        "id": "start_stopwatch",
        "patterns": [
            r"\b(start stopwatch|stopwatch start|stopwatch chalu)\b",
        ],
        "slots": []
    },
    {
        "id": "stop_stopwatch",
        "patterns": [
            r"\b(stop stopwatch|stopwatch stop|stopwatch band)\b",
        ],
        "slots": []
    },

    # ── FILE SEARCH ───────────────────────────────────────────────────
    {
        "id": "file_search",
        "patterns": [
            r"\b(find file|search file|file dhundo|look for file)\s+(?P<pattern>[\w\s\.\*]+)",
            r"\bwhere is\s+(?P<pattern>[\w\s\.\*]+\.[\w]+)\b",
        ],
        "slots": ["pattern"]
    },

    # ── INTERNET CHECK ────────────────────────────────────────────────
    {
        "id": "check_internet",
        "patterns": [
            r"\b(am i connected|internet connected|is internet working|check internet)\b",
            r"\b(do i have internet|internet hai|net chal raha hai)\b",
        ],
        "slots": []
    },

    # ── NLP TOOLS ─────────────────────────────────────────────────────
    {
        "id": "summarize_text",
        "patterns": [
            r"\b(summarize|summary|sum up|saaransh|saransh)\b",
        ],
        "slots": []
    },
    {
        "id": "sentiment_check",
        "patterns": [
            r"\b(sentiment|emotion check|mood check|how does this feel)\b",
        ],
        "slots": []
    },
    {
        "id": "keyword_extract",
        "patterns": [
            r"\b(keywords?|important words|topic extract)\b",
        ],
        "slots": []
    },

    # ── GENERIC Q&A ───────────────────────────────────────────────────
    {
        "id": "ask_question",
        "patterns": [
            r"^(?P<question>.+\?)$",
            r"^(?P<question>(what|who|how|when|where|why)\b.*)",
        ],
        "slots": ["question"]
    },
]

# Compile all patterns once at import time
for _intent in INTENTS:
    _intent["compiled"] = [
        re.compile(p, flags=re.IGNORECASE) for p in _intent["patterns"]
    ]


# ======================================================================
#  CommandParser
# ======================================================================

class CommandParser:
    """
    Three-pass parser:
    1. High-priority meta detection (boundary/language/mode/smalltalk/persona).
    2. LLM brain (if attached).
    3. Regex + heuristic fallback.
    """

    def __init__(self):
        from src.ai_knowledge import brain   # lazy import — avoids circular at module load
        self.brain = brain

    # ------------------------------------------------------------------
    # Pass 1 — High-priority meta rules (always beat LLM)
    # ------------------------------------------------------------------

    def _detect_meta(self, lower: str) -> Optional[Dict[str, Any]]:

        # User boundary
        if any(p in lower for p in ["don't call me", "do not call me", "mat bolo", "mat kehna"]):
            m    = re.search(r"(?:don.t call me|do not call me)\s+([^\s,.!?]+)", lower)
            term = m.group(1) if m else None
            if not term:
                m2   = re.search(r"mujhe\s+([^\s,.!?]+)\s+mat (?:bolo|kehna)", lower)
                term = m2.group(1) if m2 else None
            return {"intent": "user_boundary",
                    "entities": {"disallowed_term": term} if term else {},
                    "confidence": 0.98}

        # Language switch
        if "hindi" in lower and any(w in lower for w in ["talk","speak","baat","bolo","respond","reply"]):
            return {"intent": "change_language", "entities": {"target_language": "hi"}, "confidence": 0.96}
        if "english" in lower and any(w in lower for w in ["talk","speak","baat","bolo","respond","reply"]):
            return {"intent": "change_language", "entities": {"target_language": "en"}, "confidence": 0.96}

        # Mode switch
        if any(p in lower for p in ["talk normally","can we talk normally","normal talk",
                                     "casual talk","don't be so formal","speak casually"]):
            return {"intent": "change_mode", "entities": {"target_mode": "casual"}, "confidence": 0.95}
        if "formal mode" in lower or "be formal" in lower:
            return {"intent": "change_mode", "entities": {"target_mode": "formal"}, "confidence": 0.95}

        # Smalltalk
        if any(p in lower for p in ["how are you","how're you","how r u","hru",
                                     "how's your day","how is your day","how have you been",
                                     "how's it going","what's up","whats up",
                                     "kaisa hai","kaisi ho","din kaisa"]):
            return {"intent": "conversation_smalltalk", "entities": {}, "confidence": 0.93}

        # Persona
        if any(p in lower for p in ["who are you","what are you","what can you do",
                                     "tell me about you","about yourself",
                                     "introduce yourself","your name"]):
            return {"intent": "persona_query", "entities": {}, "confidence": 0.94}

        return None

    # ------------------------------------------------------------------
    # Pass 3 — Heuristic fallback
    # ------------------------------------------------------------------

    def _heuristic(self, lower: str, norm: str) -> Dict[str, Any]:
        if any(w in lower for w in ["thank","thanks","shukriya"]):
            return {"intent": "thanks",       "entities": {}, "confidence": 0.8}
        if any(w in lower for w in ["bye","goodbye","see you"]):
            return {"intent": "goodbye",      "entities": {}, "confidence": 0.8}
        if any(w in lower for w in ["hi","hello","hey","namaste"]):
            return {"intent": "greeting",     "entities": {}, "confidence": 0.8}
        if any(w in lower for w in ["summarize","summary","saransh"]):
            return {"intent": "summarize_text","entities": {}, "confidence": 0.75}
        if "sentiment" in lower or "mood" in lower:
            return {"intent": "sentiment_check","entities": {}, "confidence": 0.75}
        if "keyword" in lower:
            return {"intent": "keyword_extract","entities": {}, "confidence": 0.75}
        if "battery" in lower:
            return {"intent": "get_battery",  "entities": {}, "confidence": 0.80}
        if "screenshot" in lower:
            return {"intent": "take_screenshot","entities": {},"confidence": 0.85}
        if "internet" in lower or "connected" in lower:
            return {"intent": "check_internet","entities": {}, "confidence": 0.80}
        if "timer" in lower:
            return {"intent": "set_timer",    "entities": {}, "confidence": 0.78}
        if "stopwatch" in lower:
            return {"intent": "start_stopwatch","entities": {},"confidence": 0.78}
        if "reminder" in lower and any(w in lower for w in ["list","show","what","kaun"]):
            return {"intent": "list_reminders","entities": {}, "confidence": 0.80}
        if any(w in lower for w in ["news","khabar"]):
            return {"intent": "get_news",     "entities": {}, "confidence": 0.75}
        if "weather" in lower or "mausam" in lower:
            return {"intent": "get_weather",  "entities": {}, "confidence": 0.75}
        if "youtube" in lower:
            return {"intent": "youtube_search","entities": {}, "confidence": 0.80}
        if lower.endswith("?") or any(lower.startswith(q) for q in
                                       ("what","who","how","when","where","why")):
            return {"intent": "ask_question", "entities": {"question": norm}, "confidence": 0.6}
        return {"intent": "unknown", "entities": {}, "confidence": 0.25}

    # ------------------------------------------------------------------
    # Main parse
    # ------------------------------------------------------------------

    def parse(self, text: str, user_id: str = "default") -> Dict[str, Any]:
        text = (text or "").strip()
        if not text:
            return {"intent": "none", "entities": {}, "confidence": 0.0}

        norm  = re.sub(r"\s+", " ", text).strip()
        lower = norm.lower()

        # Pass 1 — meta
        meta = self._detect_meta(lower)
        if meta:
            return meta

        # Pass 2 — LLM brain
        if self.brain and getattr(self.brain, "llm_client", None):
            try:
                result = self.brain.interpret_intent(norm, user_id=user_id) or {}
                intent = result.get("intent")
                conf   = float(result.get("confidence", 0.0))

                # Guard: LLM sometimes mislabels smalltalk as greeting
                if intent == "greeting" and any(p in lower for p in
                        ["how are you","who are you","about you","about yourself"]):
                    intent = "conversation_smalltalk"
                    conf   = max(conf, 0.7)

                if intent and conf >= 0.55:
                    return {
                        "intent":     intent,
                        "entities":   result.get("entities", {}) or {},
                        "confidence": conf,
                    }
            except Exception as e:
                logger.exception("Brain interpret_intent error: %s", e)

        # Pass 3 — Regex
        for intent_def in INTENTS:
            for pattern in intent_def["compiled"]:
                m = pattern.search(norm)
                if m:
                    entities = {k: v.strip() for k, v in (m.groupdict() or {}).items() if v}

                    # Fill language/mode defaults
                    if intent_def["id"] == "change_language" and "target_language" not in entities:
                        entities["target_language"] = "hi" if "hindi" in lower else "en"
                    if intent_def["id"] == "change_mode" and "target_mode" not in entities:
                        entities["target_mode"] = "casual" if any(
                            w in lower for w in ["casual","normal"]) else "formal"

                    for slot in intent_def.get("slots", []):
                        entities.setdefault(slot, "")

                    return {"intent": intent_def["id"], "entities": entities, "confidence": 1.0}

        # Pass 4 — Heuristic
        return self._heuristic(lower, norm)


# ── Global instance ───────────────────────────────────────────────────
parser = CommandParser()