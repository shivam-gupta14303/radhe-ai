# command_parser.py

from __future__ import annotations
import json
import re
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger("Radhe.Parser")
logger.setLevel(logging.INFO)


# ======================================================================
#  DATA MODELS
# ======================================================================

@dataclass
class ParsedAction:
    intent:     str
    entities:   dict[str, Any] = field(default_factory=dict)
    confidence: float          = 0.0
    raw:        str            = ""
    routing:    str            = "execute"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ClarificationRequest:
    intent:           str            = "clarify"
    question:         str            = ""
    missing_slot:     str            = ""
    partial_intent:   str            = ""
    partial_entities: dict[str, Any] = field(default_factory=dict)
    raw:              str            = ""
    routing:          str            = "clarify"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ExecutionStep:
    step_id:         int
    action:          dict[str, Any]
    depends_on:      int | None  = None
    can_parallel:    bool        = False
    shared_entities: list[str]   = field(default_factory=list)


@dataclass
class ExecutionPlan:
    goal:   str                 = ""
    steps:  list[ExecutionStep] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.steps)

    def to_dict(self) -> dict:
        return {
            "goal":  self.goal,
            "total": self.total,
            "steps": [
                {
                    "step_id":         s.step_id,
                    "depends_on":      s.depends_on,
                    "can_parallel":    s.can_parallel,
                    "shared_entities": s.shared_entities,
                    "action":          s.action,
                }
                for s in self.steps
            ],
        }


@dataclass
class RecoveryAction:
    strategy:    str
    suggestions: list[str]      = field(default_factory=list)
    message:     str            = ""
    original:    dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# ======================================================================
#  LAYER 0 — PRONOUN RESOLVER
# ======================================================================

_CONTACT_PRONOUNS = {
    "usko", "usse", "isko", "isse", "inhe", "unhe", "use", "ise", "woh", "vo",
}
_LOCATION_PRONOUNS = {"wahan", "wahaan", "udhar", "wahan pe", "udhar pe"}

_CONTACT_PRN_RE = re.compile(
    r"\b(" + "|".join(re.escape(p) for p in
                      sorted(_CONTACT_PRONOUNS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)
_LOCATION_PRN_RE = re.compile(
    r"\b(" + "|".join(re.escape(p) for p in
                      sorted(_LOCATION_PRONOUNS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


def resolve_pronouns(text: str, context: dict | None) -> tuple[str, bool]:
    if not context:
        return text, False
    resolved, changed = text, False

    contacts = context.get("last_contact", [])
    if contacts and _CONTACT_PRN_RE.search(resolved):
        sub      = contacts[0] if len(contacts) == 1 else " aur ".join(contacts)
        resolved = _CONTACT_PRN_RE.sub(sub, resolved)
        changed  = True

    location = context.get("last_location", "")
    if location and _LOCATION_PRN_RE.search(resolved):
        resolved = _LOCATION_PRN_RE.sub(location, resolved)
        changed  = True

    return resolved, changed


def _extract_memory(action_dict: dict[str, Any]) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    ent    = action_dict.get("entities", {})
    intent = action_dict.get("intent", "")

    contacts = ent.get("contact")
    if contacts:
        updates["last_contact"] = [contacts] if isinstance(contacts, str) else list(contacts)

    loc = ent.get("location") or ent.get("destination")
    if loc:
        updates["last_location"] = loc

    if intent not in ("unknown", "ai_fallback", "clarify", "none"):
        updates["last_intent"]   = intent
        updates["last_entities"] = ent

    return updates


# ======================================================================
#  LAYER 1 — NORMALIZER
# ======================================================================

_HINGLISH_MAP: dict[str, str] = {
    "bje": "baje",   "bjae": "baje",   "subhaa": "subah",  "subhe": "subah",
    "pls": "please", "plz":  "please", "plzz":   "please",
    "thx": "thanks", "ty":   "thank you",
    "k":   "ok",     "kk":   "ok",     "hm":     "haan",
    "yep": "yes",    "nope": "no",
    "kr":  "kar",    "kro":  "karo",   "krna":   "karna",
    "bta": "bata",   "btao": "batao",  "lgao":   "lagao",
    "lgana": "lagana", "dikha": "dikhao",
    "msg": "message", "msgs": "messages", "snd": "send",
    "pic": "photo",  "pics": "photos", "vid":  "video",   "vids": "videos",
    "yt":  "youtube","fb":   "facebook","insta":"instagram",
    "wa":  "whatsapp","wp":  "whatsapp",
    "tmrw":"tomorrow","tmr": "tomorrow","2day": "today",   "2mrw": "tomorrow",
    "min": "minute", "mins": "minutes","sec":  "second",  "secs": "seconds",
    "hr":  "hour",   "hrs":  "hours",
}

_FILLER_WORDS = {"please", "zara", "baar", "thoda"}


def normalize(text: str) -> str:
    text = text.lower().strip()
    for shortcut, canonical in _HINGLISH_MAP.items():
        text = re.sub(rf"\b{re.escape(shortcut)}\b", canonical, text)
    words = [w for w in text.split() if w not in _FILLER_WORDS]
    return re.sub(r"\s+", " ", " ".join(words)).strip()


# ======================================================================
#  LAYER 2 — SMART MULTI-COMMAND SPLITTER
# ======================================================================

_SPLIT_TOKENS = [
    r"\baur\b", r"\band\b", r"\bthen\b", r"\bphir\b",
    r"\buske baad\b", r"\bafter that\b", r"\balso\b",
    r",\s+", r"\bsaath hi\b",
]
_SPLIT_PAT = re.compile("|".join(_SPLIT_TOKENS), flags=re.IGNORECASE)

_NOUN_GUARD = re.compile(
    r"\b[A-Za-z]+(?:\s+[A-Za-z]+)?\s+(?:aur|and)\s+[A-Za-z]+(?:\s+[A-Za-z]+)?\s+ko\b",
    re.IGNORECASE,
)
_POSS_GUARD = re.compile(
    r"\b\w+\s+(?:aur|and)\s+\w+\s+(?:ka|ki|ke)\b", re.IGNORECASE
)


def split_commands(text: str) -> list[str]:
    if _NOUN_GUARD.search(text) or _POSS_GUARD.search(text):
        return [text]
    parts = _SPLIT_PAT.split(text)
    return [p.strip() for p in parts if p.strip()]


# ======================================================================
#  LAYER 3 — INTENT RULES
# ======================================================================

_INTENT_RULES: list[tuple[str, float, list[re.Pattern]]] = []


def _rules(intent_id: str, base_conf: float, *patterns: str) -> None:
    _INTENT_RULES.append(
        (intent_id, base_conf, [re.compile(p, re.IGNORECASE) for p in patterns])
    )


# System
_rules("system_control",  0.95,
    r"\b(?P<control_type>shutdown|restart|reboot|sleep|hibernate|lock|logout)\b",
    r"\b(?P<control_type>turn off|switch off|band karo|system band|pc band)\b")
_rules("get_battery",     0.92, r"\b(battery|battery status|battery level|kitni battery|charging status)\b")
_rules("set_volume",      0.92,
    r"\b(set volume|volume set|volume ko)\s+(?:to\s+)?(?P<level>\d+)\s*(?:percent|%)?",
    r"\bvolume\s+(?:to\s+)?(?P<level>\d+)\s*(?:percent|%)?\b",
    r"\b(?P<direction>volume up|increase volume|louder|zyada awaz|volume down|decrease volume|quieter|kam awaz)\b")
_rules("take_screenshot", 0.93, r"\b(take a screenshot|screenshot lo|capture screen|screenshot)\b")
_rules("analyze_screen",  0.90, r"\b(what.s on my screen|read my screen|screen pe kya hai|describe screen|analyze screen)\b")
_rules("check_internet",  0.90, r"\b(am i connected|internet connected|is internet working|check internet|do i have internet|net chal raha)\b")

# Timer / Stopwatch
_rules("set_timer",       0.93,
    r"\b(set a? timer|timer set karo|timer for|timer of)\s+(?:for\s+)?(?P<duration>[\d][\w\s]*)",
    r"\b(?P<duration>\d+\s*(?:minute|minutes|min|second|seconds|sec|hour|hours|hr)s?)\s+(?:ka\s+)?timer\b",
    r"\b(set a? timer|timer lagao|timer set)\b")
_rules("start_stopwatch", 0.90, r"\b(start stopwatch|stopwatch start|stopwatch chalu)\b")
_rules("stop_stopwatch",  0.90, r"\b(stop stopwatch|stopwatch stop|stopwatch band)\b")

# Reminders
_rules("list_reminders",  0.90, r"\b(what reminders|show reminders|list reminders|my reminders|upcoming reminders|reminders dikhao)\b")
_rules("cancel_reminder", 0.90,
    r"\b(cancel|delete|remove|hatao)\s+(?:my\s+)?(?P<keyword>[\w\s]+?)\s+reminder\b",
    r"\breminder cancel karo\s+(?P<keyword>[\w\s]+)")
_rules("set_reminder",    0.88,
    r"\b(remind me to|set a reminder to|reminder for)\s+(?P<reminder_text>.+?)\s+(?:at|on|in)\s+(?P<time>.+)",
    r"\bremind me in\s+(?P<time>.+?)\s+to\s+(?P<reminder_text>.+)",
    r"\breminder\s+(?P<reminder_text>.+)\s+at\s+(?P<time>.+)",
    r"\b(?P<time>[\w\s]+?)\s+(?:ka\s+)?alarm\s+(?:laga|set|laga dena|lagao)\b",
    r"\balarm\s+(?:laga|set|lagao)\s+(?P<time>[\w\s]+)",
    r"\balarm\b")

# Calling
_rules("call_contact",    0.93,
    r"\b(call|ring|phone|dial|call karo|baat karo)\s+(?P<contact>[A-Za-z][\w\s]{1,30}?)(?:\s+(?:on|via|pe|par)\s+(?P<platform>[\w]+))?\s*$",
    r"\b(?P<contact>[A-Za-z][\w\s]{1,30}?)\s+ko\s+(?:call|ring|phone)\s*(?:karo|lagao)?\b",
    r"\b(?P<contact>[A-Za-z][\w\s]{1,30}?)\s+se\s+baat\s+(?:karo|karni hai|karwao)\b",
    r"\b(?P<contact>[A-Za-z][A-Za-z\s]{2,25}?)\s+call\s+(?:karo|lagao|karna|please)?\b",
    r"\b(?:call karo|call lagao|ek call karo|call please|please call)\b",
    r"^(?:call|ring)$")

# Messaging
_rules("send_message",    0.88,
    r"\b(send|message|msg)\s+(?P<contact>[\w\s]+?)\s+(?:on|via)?\s*(?P<platform>whatsapp|telegram|instagram|sms|email|gmail)?\s*(?:saying|that|:)?\s*(?P<message>.+)",
    r"(?P<platform>whatsapp|telegram|instagram|sms|gmail)\s*(?:pe|par|ko)?\s*(?P<contact>[\w\s]+?)\s+ko\s+(?:bol|message|msg|bhej)\s+(?P<message>.+)",
    r"\b(?P<contact>[A-Za-z]+(?:\s+[A-Za-z]+)?)\s+ko\s+(?:\w+\s+){0,2}?(?:message|msg|bhej|bol)\s+(?P<message>.+)",
    r"\b(?P<contact>[A-Za-z][A-Za-z\s]{1,30}?)\s+ko\s+(?:message|msg|bhej|bol)\s+(?P<message>.+)",
    r"\b(?:message|msg|bhej)\s+(?P<contact>[A-Za-z][A-Za-z\s]{1,30}?)\s+ko\b(?:\s+(?P<message>.+))?",
    r"\b(?:send|bhej)\s+(?:a\s+)?message\b",
    r"\bmessage\s+(?:karo|bhejo|bhejni hai|bhejdo)\b")

# Media
_rules("youtube_search",  0.92,
    r"\b(?:search|find|play|look up|dekh)\s+(?P<query>.+?)\s+on\s+youtube\b",
    r"\byoutube\s+(?:pe|par|search|par\s+dekh)\s+(?P<query>.+)",
    r"\bsearch youtube for\s+(?P<query>.+)")
_rules("play_music",      0.90,
    r"\b(?:play|bajao)\s+(?P<query>[\w\s\-]+?)(?:\s+on\s+(?P<platform>spotify|gaana|jiosaavn|wynk))?\s*$",
    r"\b(?P<query>.+?)\s+(?:song|gaana|track)\s+(?:play|bajao)\b")

# Navigation
_rules("get_directions",  0.90,
    r"\b(?:directions|route|how to go|rasta)\s+from\s+(?P<origin>[\w\s]+?)\s+to\s+(?P<destination>[\w\s]+)",
    r"\b(?:get directions|navigate|directions)\s+to\s+(?P<destination>[\w\s]+)")

# Weather / News
_rules("get_weather",     0.88,
    r"\b(?:weather in|mausam|weather forecast)\s+(?:in|for)?\s*(?P<location>[\w\s]+)",
    r"\b(?:what.s the weather|how.s the weather|will it rain)\b")
_rules("get_news",        0.85,
    r"\bnews about\s+(?P<topic>[\w\s]+)",
    r"\b(?:show me news|latest news|what.s happening|news today|khabar)\b")

# File / App
_rules("file_search",     0.88,
    r"\b(?:find file|search file|file dhundo|look for file)\s+(?P<pattern>[\w\s\.\*]+)",
    r"\bwhere is\s+(?P<pattern>[\w\s\.\*]+\.\w+)\b")
_rules("recent_files",    0.88, r"\b(?:recent files|last files|what did i work on)\b")
_rules("open_website",    0.87, r"\b(?:open|go to|visit|jaao)\s+(?P<website>[\w\.\-]+\.\w{2,}(?:\s[\w\.\-]+)*)")
_rules("close_app",       0.90, r"\b(?:close|kill|terminate|quit|band karo)\s+(?P<application>[\w\s\-\.]+)")
_rules("open_app",        0.88, r"\b(?:open|launch|start|khol)\s+(?:the\s+)?(?P<application>[\w\s\-\.]+)")
_rules("open_file",       0.87, r"\b(?:open file|open)\s+(?P<path>[\w\s\.\-\/\\]+\.\w+)")
_rules("search_web",      0.85,
    r"\b(?:search for|find|look up|google)\s+(?P<query>.+)",
    r"\bsearch\s+(?P<query>.+)\s+on google\b")

# NLP
_rules("summarize_text",  0.85, r"\b(?:summarize|summary|sum up|saaransh|saransh)\b")
_rules("sentiment_check", 0.85, r"\b(?:sentiment|emotion check|mood check|how does this feel)\b")
_rules("keyword_extract", 0.85, r"\b(?:keywords?|important words|topic extract)\b")

# Time / Date
_rules("get_time",        0.95, r"\b(?:what.s the time|what is the time|current time|time bata|kya time hai)\b")
_rules("get_date",        0.95, r"\b(?:what.s the date|what is the date|aaj ki date|date bata|which day is today|aaj kaun sa din)\b")

# Meta
_rules("user_boundary",   0.98,
    r"\b(?:don.t call me|do not call me)\s+(?P<disallowed_term>\S+)",
    r"\bmujhe\s+(?P<disallowed_term>\S+)\s+mat (?:bolo|kehna)\b")
_rules("change_language", 0.96, r"\b(?:talk|speak|reply|respond|baat|bolo)\s*(?:in|mein|me)?\s*(?P<target_language>hindi|english)\b")
_rules("change_mode",     0.95,
    r"\b(?:talk normally|normal talk|casual talk|don.t be so formal|speak casually)\b",
    r"\b(?:formal mode|be formal|formal baat)\b")
_rules("conversation_smalltalk", 0.93,
    r"\b(?:how are you|how.re you|how r u|hru|how.s your day|how is your day|how have you been|how.s it going|what.s up|whats up|kaisa hai|kaisi ho|din kaisa)\b")
_rules("persona_query",   0.94,
    r"\b(?:who are you|what are you|what can you do|tell me about you|about yourself|introduce yourself|your name)\b")
_rules("thanks",          0.90, r"\b(?:thank you|thanks|thanks a lot|shukriya)\b")
_rules("goodbye",         0.90, r"\b(?:bye|goodbye|see you|phir milte)\b")
_rules("greeting",        0.88, r"\b(?:hi|hello|hey|namaste|salam)\b(?:\s+radhe)?\b")
_rules("ask_question",    0.65,
    r"^(?P<question>(?:what|who|how|when|where|why)\b.+)",
    r"^(?P<question>.+\?)$")


# ======================================================================
#  PERSISTENT BOOST STORE
# ======================================================================

_BOOST_FILE = Path(__file__).parent / "intent_boost.json"
_BOOST_MAX, _BOOST_MIN = 0.10, -0.05


class BoostStore:
    def __init__(self, path: Path = _BOOST_FILE) -> None:
        self._path = path
        self._data: dict[str, float] = {}
        self._load()

    def _load(self) -> None:
        try:
            if self._path.exists():
                self._data = {k: float(v)
                              for k, v in json.loads(self._path.read_text()).items()}
        except Exception as e:
            logger.warning("BoostStore load failed (%s) — starting fresh", e)

    def _save(self) -> None:
        try:
            self._path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning("BoostStore save failed: %s", e)

    def get(self, intent: str) -> float:
        return self._data.get(intent, 0.0)

    def update(self, intent: str, success: bool) -> float:
        cur = self._data.get(intent, 0.0)
        new = max(_BOOST_MIN, min(_BOOST_MAX, cur + (0.01 if success else -0.01)))
        self._data[intent] = new
        self._save()
        return new

    def all(self) -> dict[str, float]:
        return dict(self._data)

    def reset(self, intent: str | None = None) -> None:
        if intent:
            self._data.pop(intent, None)
        else:
            self._data.clear()
        self._save()


_boost_store = BoostStore()


# ======================================================================
#  INTENT DETECTION + CONFIDENCE ROUTER
# ======================================================================

def detect_intent(text: str) -> tuple[str, float, dict[str, Any]]:
    best_intent:   str            = "unknown"
    best_score:    float          = 0.0
    best_entities: dict[str, Any] = {}
    text_len = max(len(text), 1)

    for intent_id, base_conf, patterns in _INTENT_RULES:
        boost = _boost_store.get(intent_id)
        for pat in patterns:
            m = pat.search(text)
            if not m:
                continue
            ents  = {k: v.strip() for k, v in (m.groupdict() or {}).items() if v}
            mlen  = len(m.group(0))
            score = (base_conf + boost
                     + 0.02 * len(ents)
                     + 0.03 * (mlen / text_len)
                     - (0.05 if mlen < 4 else 0.0))
            if score > best_score:
                best_score, best_intent, best_entities = score, intent_id, ents

    if best_intent == "change_language" and "target_language" in best_entities:
        lang = best_entities["target_language"]
        best_entities["target_language"] = "hi" if "hindi" in lang else "en"
    if best_intent == "change_mode":
        casual = {"normal", "casual", "informal", "normally", "casually"}
        best_entities["target_mode"] = "casual" if any(w in text for w in casual) else "formal"

    return best_intent, round(best_score, 4), best_entities


def confidence_routing(conf: float) -> str:
    if conf >= 0.85:
        return "execute"
    if conf >= 0.60:
        return "confirm"
    return "clarify"


# ======================================================================
#  URGENCY DETECTOR
# ======================================================================

_URGENCY_MAP: dict[str, str] = {
    "abhi":        "high",   "turant":      "high",  "urgent":        "high",
    "asap":        "high",   "immediately": "high",  "right now":     "high",
    "emergency":   "high",   "furan":       "high",
    "jaldi":       "medium", "soon":        "medium","quickly":       "medium",
    "jaldi se":    "medium", "jaldi karo":  "medium",
}

_URGENCY_RE = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in sorted(_URGENCY_MAP, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

_URGENCY_EXEC: dict[str, dict[str, Any]] = {
    "high":   {"skip_confirmation": True,  "priority": "high",   "notify_immediately": True},
    "medium": {"skip_confirmation": False, "priority": "medium", "notify_immediately": False},
}


def detect_urgency(text: str) -> str:
    levels = [_URGENCY_MAP.get(m.group(1).lower(), "normal")
              for m in _URGENCY_RE.finditer(text)]
    if "high"   in levels: return "high"
    if "medium" in levels: return "medium"
    return "normal"


def strip_urgency(text: str) -> str:
    return re.sub(r"\s{2,}", " ", _URGENCY_RE.sub("", text)).strip()


# ======================================================================
#  LAYER 5 — ENTITY EXTRACTOR
# ======================================================================

_DAY_NORM    = {"kal": "tomorrow", "aaj": "today", "parso": "day-after-tomorrow",
                "tomorrow": "tomorrow", "today": "today"}
_PERIOD_NORM = {"subah": "morning", "shaam": "evening", "raat": "night",
                "dopahar": "afternoon", "morning": "morning", "evening": "evening",
                "night": "night", "afternoon": "afternoon"}
_TIME_PATS = [
    re.compile(r"\bin\s+(?P<amount>\d+)\s+(?P<unit>minute|minutes|hour|hours|second|seconds|min|mins|hr|hrs)\b", re.I),
    re.compile(r"\b(?P<hour>\d{1,2}):(?P<minute>\d{2})\s*(?P<ampm>am|pm)?\b", re.I),
    re.compile(r"\b(?P<hour>\d{1,2})\s*(?P<ampm>baje|am|pm)\b", re.I),
    re.compile(r"\b(?P<day>kal|aaj|parso|tomorrow|today)\s+(?P<period>subah|shaam|raat|dopahar|morning|evening|night|afternoon)\b", re.I),
]


def parse_time(text: str) -> dict[str, Any] | None:
    """
    Parse time expressions from text.
    Returns a structured dict (with keys: raw, hour, minute, ampm, day, period,
    relative_amount, relative_unit) or None if no time expression found.

    Used internally by enrich_entities() and _apply_slot_reply().
    reminder_manager.py uses time_parser.parse_time() which returns datetime.
    """
    result: dict[str, Any] = {}
    for pat in _TIME_PATS:
        m = pat.search(text)
        if not m:
            continue
        gd = m.groupdict()
        result["raw"] = m.group(0).strip()
        if gd.get("amount"):
            result["relative_amount"] = int(gd["amount"])
            result["relative_unit"]   = gd["unit"].rstrip("s")
            return result
        if gd.get("day"):    result["day"]    = _DAY_NORM.get(gd["day"].lower(), gd["day"])
        if gd.get("period"): result["period"] = _PERIOD_NORM.get(gd["period"].lower(), gd["period"])
        if gd.get("hour"):
            result["hour"]   = int(gd["hour"])
            result["minute"] = int(gd.get("minute") or 0)
            ampm = (gd.get("ampm") or "").lower()
            if ampm and ampm != "baje":
                result["ampm"] = ampm
        if result:
            return result
    return None


_PERIOD_HOUR = {"morning": 8, "afternoon": 13, "evening": 18, "night": 21}
_UNIT_KW     = {"minute": "minutes", "second": "seconds", "hour": "hours"}


def to_datetime(parsed: dict[str, Any], now: datetime | None = None) -> datetime | None:
    """Convert a parse_time() dict to a datetime object."""
    if not parsed: return None
    now = now or datetime.now()
    if "relative_amount" in parsed:
        kw = _UNIT_KW.get(parsed.get("relative_unit", ""), "minutes")
        return now + timedelta(**{kw: parsed["relative_amount"]})
    offset = {"today": 0, "tomorrow": 1, "day-after-tomorrow": 2}.get(parsed.get("day", "today"), 0)
    target = now.date() + timedelta(days=offset)
    hour   = parsed.get("hour")
    minute = parsed.get("minute", 0)
    ampm   = parsed.get("ampm", "")
    period = parsed.get("period", "")
    if hour is None:
        hour, minute = _PERIOD_HOUR.get(period, 9), 0
    if ampm == "pm" and hour < 12:  hour += 12
    if ampm == "am" and hour == 12: hour  = 0
    try:
        dt = datetime(target.year, target.month, target.day, hour, minute)
    except ValueError:
        return None
    if dt <= now and "day" not in parsed:
        dt += timedelta(days=1)
    return dt


def extract_duration(text: str) -> str | None:
    m = re.search(r"(?P<amount>\d+)\s*(?P<unit>minute|minutes|min|second|seconds|sec|hour|hours|hr)", text, re.I)
    return f"{m.group('amount')} {m.group('unit')}" if m else None


def normalize_contact(name: str) -> str:
    return " ".join(w.capitalize() for w in name.strip().split())


def _dedupe(names: list[str]) -> list[str]:
    seen: set[str] = set()
    out:  list[str] = []
    for n in names:
        if n.lower() not in seen:
            seen.add(n.lower())
            out.append(n)
    return out


_BAD_CONTACTS = {
    "mujhe", "use", "unhe", "hume", "tumhe", "aap", "usse", "vo", "woh",
    "message", "msg", "call", "send", "bhej", "bol", "ring",
    "karo", "karna", "lagao", "laga", "karein", "dijiye", "dena",
    "the", "a", "an", "my", "your", "his", "her",
}
_NC = r"[A-Za-z]+(?:\s+[A-Za-z]+)?"


def extract_contact(text: str) -> list[str] | None:
    # Tier 1
    multi = re.findall(rf"\b({_NC})\s+(?:aur|and)\s+({_NC})\s+ko\b", text, re.I)
    if multi:
        names = [normalize_contact(n) for pair in multi for n in pair
                 if n.strip().lower() not in _BAD_CONTACTS and len(n.strip()) > 1]
        names = _dedupe(names)
        if names: return names

    # Tier 2
    singles = re.findall(rf"\b({_NC})\s+ko\b", text, re.I)
    singles = [normalize_contact(s) for s in singles
               if s.strip().lower() not in _BAD_CONTACTS and len(s.strip()) > 1]
    singles = _dedupe(singles)
    if singles: return singles

    # Tier 3
    m = re.search(rf"\bto\s+({_NC})(?:\s+(?:on|via|pe|par)|$)", text, re.I)
    if m: return [normalize_contact(m.group(1))]

    # Tier 4
    m = re.search(rf"\b(?:message|msg|call|ring|bhej|bol|send)\s+({_NC})\b", text, re.I)
    if m:
        c = normalize_contact(m.group(1))
        if c.lower() not in _BAD_CONTACTS:
            return [c]
    return None


def extract_message(text: str) -> str | None:
    for marker in ("saying", "that", "ki", ":"):
        idx = text.find(marker)
        if idx != -1:
            msg = text[idx + len(marker):].strip()
            if msg: return msg
    m = re.search(
        r"\b(?:bol|bhej|message)\b"
        r"(?:\s+[A-Za-z]+(?:\s+[A-Za-z]+)?\s+ko)?"
        r"\s+(?P<msg>[\w\'\"\-\s\u0900-\u097F]{3,})",
        text, re.I)
    if m:
        cand = m.group("msg").strip()
        if len(cand.split()) >= 2 or len(cand) >= 5:
            return cand
    m = re.search(r"\bbhej\b\s+(?P<tail>.{4,})", text, re.I)
    if m:
        tail = m.group("tail").strip()
        if len(tail.split()) >= 2: return tail
    return None


def extract_application(text: str) -> str | None:
    m = re.search(r"\b(?:open|launch|start|close|kill|quit|band karo|khol)\s+(?:the\s+)?(?P<app>[\w\s\-\.]+)", text, re.I)
    return m.group("app").strip() if m else None


def extract_query(text: str) -> str | None:
    for marker in ("search for", "find", "look up", "play", "search"):
        m = re.search(rf"\b{marker}\s+(?P<q>.+?)(?:\s+on\s|\s+in\s|$)", text, re.I)
        if m: return m.group("q").strip()
    return None


_MSG_VERB_STARTS = {"bhej", "bol", "message", "msg", "send", "bhejna", "ki"}


def enrich_entities(intent: str, entities: dict[str, Any], text: str) -> dict[str, Any]:
    urgency    = detect_urgency(text)
    clean_text = strip_urgency(text)

    if urgency != "normal":
        entities["urgency"] = urgency
        flags = _URGENCY_EXEC.get(urgency)
        if flags:
            entities["_exec"] = flags

    if intent in ("set_reminder", "set_alarm"):
        parsed = parse_time(entities.get("time") or text)
        if parsed:
            entities["time_parsed"] = parsed
            if not entities.get("time"):
                entities["time"] = parsed.get("raw", "")
            dt = to_datetime(parsed)
            if dt:
                entities["datetime_iso"] = dt.isoformat()

    if intent == "set_timer" and not entities.get("duration"):
        d = extract_duration(text)
        if d: entities["duration"] = d

    if intent == "send_message":
        raw_c = entities.get("contact")
        if raw_c and isinstance(raw_c, str):
            raw_c = strip_urgency(raw_c).strip()
        if raw_c and isinstance(raw_c, str) and raw_c.strip().lower() in _BAD_CONTACTS:
            raw_c = None
            entities.pop("contact", None)
        if raw_c and isinstance(raw_c, str):
            multi = re.findall(rf"\b({_NC})\s+(?:aur|and)\s+({_NC})\b", raw_c, re.I)
            if multi:
                entities["contact"] = _dedupe([normalize_contact(n)
                                               for pair in multi for n in pair
                                               if n.strip().lower() not in _BAD_CONTACTS])
            else:
                entities["contact"] = [normalize_contact(raw_c)]
        if not entities.get("contact"):
            c = extract_contact(clean_text)
            if c: entities["contact"] = c
        raw_msg = entities.get("message", "")
        if raw_msg and raw_msg.split()[0].lower() in _MSG_VERB_STARTS:
            better = extract_message(text)
            if better and better != raw_msg:
                entities["message"] = better
        elif not raw_msg:
            msg = extract_message(text)
            if msg: entities["message"] = msg
        if not entities.get("platform"):
            entities["platform"] = "whatsapp"

    if intent == "call_contact":
        raw_c = entities.get("contact")
        if raw_c and isinstance(raw_c, str):
            raw_c = strip_urgency(raw_c).strip()
            if raw_c.lower() in _BAD_CONTACTS:
                raw_c = None
                entities.pop("contact", None)
        if raw_c and isinstance(raw_c, str):
            entities["contact"] = [normalize_contact(raw_c)]
        if not entities.get("contact"):
            c = extract_contact(clean_text)
            if c: entities["contact"] = c

    if intent in ("open_app", "close_app") and not entities.get("application"):
        app = extract_application(clean_text)
        if app: entities["application"] = app

    if intent in ("search_web", "youtube_search", "play_music") and not entities.get("query"):
        q = extract_query(text)
        if q: entities["query"] = q

    return entities


# ======================================================================
#  LAYER 6 — ENTITY VALIDATOR
# ======================================================================

KNOWN_APPS: set[str] = {
    "chrome", "firefox", "edge", "brave", "safari", "opera",
    "notepad", "word", "excel", "powerpoint", "onenote", "outlook",
    "vscode", "visual studio code", "sublime", "atom", "pycharm",
    "spotify", "vlc", "youtube", "netflix", "prime video",
    "gaana", "jiosaavn", "wynk",
    "whatsapp", "telegram", "instagram", "discord", "zoom", "teams",
    "skype", "gmail", "slack",
    "calculator", "calendar", "clock", "camera", "gallery", "files",
    "settings", "terminal", "cmd", "powershell", "file manager",
    "task manager", "paint",
    "paytm", "phonepe", "gpay", "google pay", "swiggy", "zomato",
    "flipkart", "amazon", "maps", "google maps",
}


def validate_entities(intent: str, entities: dict[str, Any]) -> tuple[bool, str]:
    if intent in ("open_app", "close_app"):
        app = (entities.get("application") or "").strip().lower()
        if not app:               return False, "no application name"
        if app not in KNOWN_APPS: return False, f"unknown application '{app}'"
    if intent == "send_message":
        contacts = entities.get("contact") or []
        if isinstance(contacts, str): contacts = [contacts]
        if not contacts or any(len(c.strip()) < 2 for c in contacts):
            return False, "no_contact"
    if intent == "call_contact":
        contacts = entities.get("contact") or []
        if isinstance(contacts, str): contacts = [contacts]
        if not contacts or not any(len(c.strip()) >= 2 for c in contacts):
            return False, "no_contact"
    if intent in ("search_web", "youtube_search", "play_music"):
        if len((entities.get("query") or "").strip()) < 2:
            return False, "query too short"
    if intent == "set_reminder":
        if not entities.get("time") and not entities.get("time_parsed"):
            return False, "no_time"
    if intent == "set_timer":
        if not entities.get("duration"):
            return False, "no_duration"
    return True, ""


# ======================================================================
#  ERROR RECOVERY
# ======================================================================

def _edit_distance(a: str, b: str) -> int:
    m, n = len(a), len(b)
    dp   = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[:]
        dp[0] = i
        for j in range(1, n + 1):
            cost  = 0 if a[i-1] == b[j-1] else 1
            dp[j] = min(dp[j]+1, dp[j-1]+1, prev[j-1]+cost)
    return dp[n]


class ErrorRecovery:
    _FUZZY_THRESH = 3

    @classmethod
    def fuzzy_match_app(cls, name: str) -> list[str]:
        name = name.lower().strip()
        scored = sorted([(app, _edit_distance(name, app)) for app in KNOWN_APPS],
                        key=lambda x: x[1])
        return [app for app, dist in scored if dist <= cls._FUZZY_THRESH][:3]

    @classmethod
    def build(cls, failed_action: dict[str, Any], error_reason: str) -> RecoveryAction:
        intent   = failed_action.get("intent", "")
        entities = failed_action.get("entities", {})

        if error_reason in ("app_not_found", "unknown_app"):
            app  = (entities.get("application") or "").lower()
            alts = cls.fuzzy_match_app(app)
            if alts:
                return RecoveryAction(
                    strategy="suggest", suggestions=alts,
                    message=f"'{app}' nahi mila. Kya aap yeh chaahte hain: {', '.join(alts)}?",
                    original=failed_action)
            return RecoveryAction(strategy="fallback",
                message=f"'{app}' koi app nahi mila. Naam dobara batayein.",
                original=failed_action)

        if error_reason in ("contact_not_found", "unknown_contact"):
            c    = (entities.get("contact") or ["?"])
            name = c[0] if isinstance(c, list) else c
            return RecoveryAction(strategy="clarify",
                message=f"'{name}' contacts mein nahi mila. Pura naam ya number?",
                original=failed_action)

        if error_reason in ("network_error", "timeout", "service_unavailable"):
            return RecoveryAction(strategy="retry",
                message="Network issue. Dobara try kar raha hoon...",
                original=failed_action)

        return RecoveryAction(strategy="fallback",
            message=f"'{intent}' execute nahi ho saka ({error_reason}). Dobara try karein.",
            original=failed_action)


# ======================================================================
#  CLARIFICATION LAYER
# ======================================================================

_REQUIRED_SLOTS: dict[str, list[str]] = {
    "send_message":   ["contact"],
    "call_contact":   ["contact"],
    "set_reminder":   ["time"],
    "set_timer":      ["duration"],
    "get_directions": ["destination"],
    "search_web":     ["query"],
    "youtube_search": ["query"],
    "play_music":     ["query"],
    "cancel_reminder":["keyword"],
}

_QUESTIONS: dict[tuple[str, str], str] = {
    ("send_message",   "contact"):       "Kisko message bhejna hai? Who should I message?",
    ("send_message",   "message"):       "Kya likhna hai? What is the message?",
    ("call_contact",   "contact"):       "Kisko call karna hai? Who should I call?",
    ("set_reminder",   "time"):          "Kab yaad dilana hai? When should I remind you?",
    ("set_reminder",   "reminder_text"): "Kiska reminder? Reminder for what?",
    ("set_timer",      "duration"):      "Kitni der ka timer? How long a timer?",
    ("get_directions", "destination"):   "Kahan jaana hai? Where to?",
    ("search_web",     "query"):         "Kya search karna hai? What to search?",
    ("youtube_search", "query"):         "YouTube pe kya dhundhna hai? What to search?",
    ("play_music",     "query"):         "Kaun sa gaana bajana hai? Which song?",
    ("cancel_reminder","keyword"):       "Kaun sa reminder cancel karna hai? Which one?",
}

_SENTINEL_SLOT = {"no_contact": "contact", "no_time": "time", "no_duration": "duration"}


def _try_clarify(intent: str, entities: dict[str, Any], raw: str, reason: str) -> ClarificationRequest | None:
    slot = _SENTINEL_SLOT.get(reason)
    if not slot:
        for s in _REQUIRED_SLOTS.get(intent, []):
            val = entities.get(s)
            if val is None or val == "" or (isinstance(val, list) and not val):
                slot = s
                break
    if not slot:
        return None
    question = _QUESTIONS.get((intent, slot), f"'{slot}' missing. Can you clarify?")
    return ClarificationRequest(question=question, missing_slot=slot,
                                partial_intent=intent, partial_entities=entities, raw=raw)


# ======================================================================
#  ACTION BUILDER
# ======================================================================

def _merge_entities(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for k, v in override.items():
        if k in merged and isinstance(merged[k], list) and isinstance(v, list):
            seen = set(map(str, merged[k]))
            merged[k] = merged[k] + [x for x in v if str(x) not in seen]
        else:
            merged[k] = v
    return merged


def build_action(raw_fragment: str, context: dict | None = None) -> ParsedAction | ClarificationRequest:
    resolved, was_resolved = resolve_pronouns(raw_fragment, context)

    norm              = normalize(resolved)
    intent, conf, ent = detect_intent(norm)
    ent               = enrich_entities(intent, ent, norm)

    if was_resolved:
        ent["_pronoun_resolved"] = True
        ent["_original_text"]   = raw_fragment.strip()

    if intent == "unknown" and context:
        last_intent   = context.get("last_intent", "")
        last_entities = context.get("last_entities", {})
        if last_intent and last_intent not in ("unknown", "none", "ai_fallback"):
            intent = last_intent
            conf   = max(conf, 0.45)
            ent    = enrich_entities(intent, ent, norm)
            ent    = _merge_entities(last_entities, ent)
            ent["_inherited_from_context"] = True

    routing = confidence_routing(conf)

    if intent not in ("unknown", "ai_fallback", "none"):
        valid, reason = validate_entities(intent, ent)
        if not valid:
            clarify = _try_clarify(intent, ent, raw_fragment, reason)
            if clarify:
                return clarify
            ent = {"text": norm, "possible_intent": intent, "validation_error": reason}
            if context:
                ent["previous_entities"] = context.get("last_entities", {})
            intent, conf, routing = "ai_fallback", 0.30, "clarify"

    if intent == "unknown":
        hint: dict[str, Any] = {"text": norm}
        if context:
            hint["possible_intent"]   = context.get("last_intent", "")
            hint["previous_entities"] = context.get("last_entities", {})
        return ParsedAction(intent="ai_fallback", entities=hint, confidence=0.30,
                            raw=raw_fragment.strip(), routing="clarify")

    return ParsedAction(intent=intent, entities=ent, confidence=conf,
                        raw=raw_fragment.strip(), routing=routing)


# ======================================================================
#  EXECUTION PLANNER
# ======================================================================

_COMMUNICATION_INTENTS = {"send_message", "call_contact"}
_INDEPENDENT_INTENTS   = {"set_reminder", "set_timer", "set_alarm",
                           "play_music", "get_weather", "get_news",
                           "open_app", "search_web", "youtube_search",
                           "take_screenshot", "get_battery"}


def _plan_steps(actions: list[dict[str, Any]]) -> list[ExecutionStep]:
    steps:        list[ExecutionStep] = []
    last_comm_id: int | None          = None

    for i, action in enumerate(actions):
        intent   = action.get("intent", "")
        step_id  = i + 1
        dep      = None
        parallel = False
        shared   = []

        if intent in _COMMUNICATION_INTENTS and last_comm_id is not None:
            dep    = last_comm_id
            shared = ["contact"]
        elif intent in _INDEPENDENT_INTENTS:
            parallel = True

        step = ExecutionStep(step_id=step_id, action=action,
                             depends_on=dep, can_parallel=parallel,
                             shared_entities=shared)
        steps.append(step)

        if intent in _COMMUNICATION_INTENTS:
            last_comm_id = step_id

    return steps


# ======================================================================
#  GOAL INFERENCE
# ======================================================================

_GOAL_PATTERNS: list[tuple[frozenset[str], str]] = [
    (frozenset({"send_message", "call_contact"}),  "communicate"),
    (frozenset({"send_message"}),                   "message"),
    (frozenset({"call_contact"}),                   "call"),
    (frozenset({"set_reminder", "set_timer"}),      "schedule"),
    (frozenset({"play_music", "youtube_search"}),   "media"),
    (frozenset({"open_app", "search_web"}),         "browse"),
    (frozenset({"get_weather", "get_directions"}),  "navigate"),
]


def infer_goal(actions: list[dict[str, Any]]) -> str:
    intents = frozenset(a.get("intent", "") for a in actions
                        if a.get("intent") not in ("unknown", "ai_fallback", "clarify"))

    best_goal    = ""
    best_overlap = 0
    for pattern, label in _GOAL_PATTERNS:
        overlap = len(intents & pattern)
        if overlap > best_overlap:
            best_overlap = overlap
            best_goal    = label

    if not best_goal:
        return "general task"

    contacts: list[str] = []
    for a in actions:
        c = a.get("entities", {}).get("contact")
        if c:
            contacts.extend(c if isinstance(c, list) else [c])
    contacts = list(dict.fromkeys(contacts))

    if contacts:
        return f"{best_goal} with {' and '.join(contacts)}"
    return best_goal


# ======================================================================
#  RADHE PERSONALITY
#  No emoji, no slashes — safe for pyttsx3 TTS
# ======================================================================

@dataclass
class RadhePersonality:
    name:              str  = "Radhe"
    language_default:  str  = "hinglish"
    tone:              str  = "casual"
    use_emoji:         bool = False
    confirm_before_action: bool = True

    always_confirm: frozenset[str] = field(default_factory=lambda: frozenset({
        "system_control", "send_message", "call_contact",
    }))

    templates: dict[str, str] = field(default_factory=lambda: {
        "greeting":      "Haan bolo, main {name} hoon! Kya karna hai?",
        "confirm_action":"Kya main {intent} ke liye kar doon? Haan ya nahi?",
        "clarify":       "{question}",
        "success":       "Ho gaya! {detail}",
        "failure":       "Kuch gadbad ho gayi. {detail}. Dobara try karein?",
        "unknown":       "Yeh samajh nahi aaya. Thoda aur explain karein?",
        "urgency_high":  "Haan, abhi karta hoon!",
        "urgency_medium":"Theek hai, jaldi karta hoon.",
        "goodbye":       "Alvida! Phir milenge.",
    })

    def get_template(self, key: str, **kwargs: str) -> str:
        tmpl = self.templates.get(key, "{key} response not configured")
        kwargs.setdefault("name", self.name)
        kwargs.setdefault("key",  key)
        try:
            return tmpl.format(**kwargs)
        except KeyError:
            return tmpl


RADHE = RadhePersonality()


# ======================================================================
#  PUBLIC API — CommandParser
# ======================================================================

class CommandParser:
    """
    Main entry point.

    parse()  → single dict, radhe.py / executor compatible
    step()   → state machine for multi-turn slot filling
    plan()   → execution plan with dependency links
    """

    def _parse_list(
        self, text: str, context: dict | None = None
    ) -> list[ParsedAction | ClarificationRequest]:
        """Internal — returns list. Used by step() and plan()."""
        if not text or not text.strip():
            return [ParsedAction(intent="none", confidence=0.0, raw="")]
        norm      = normalize(text)
        fragments = split_commands(norm)
        actions   = [build_action(frag, context) for frag in fragments]
        if context is not None:
            for a in actions:
                if isinstance(a, ParsedAction) and a.intent not in ("none", "ai_fallback"):
                    context.update(_extract_memory(a.to_dict()))
        return actions

    def parse(self, text: str, context: dict | None = None) -> dict:
        """
        Returns a single dict for executor.execute() compatibility.
        Maintains internal SessionState for transparent multi-turn slot filling.
        Clarification question surfaced in entities["question"].
        """
        if not hasattr(self, "_session") or self._session is None:
            self._session = SessionState()

        result = self.step(text, self._session)
        d      = result.to_dict()

        if d.get("intent") == "clarify" and d.get("question"):
            d.setdefault("entities", {})["question"] = d["question"]

        return d

    def parse_dict(self, text: str, context: dict | None = None) -> list[dict]:
        """Returns list of dicts — used by radhe_engine."""
        return [a.to_dict() for a in self._parse_list(text, context)]

    def step(
        self, text: str, session: "SessionState"
    ) -> "ParsedAction | ClarificationRequest":
        """Single turn through the full state machine."""

        if session.state in _STATE_RESOLVES:
            completed = _apply_slot_reply(session, text)
            decision  = SafetyGate.check(completed.to_dict())
            if not decision.safe:
                session.state          = ConvState.awaiting_confirm
                session.pending_action = completed.to_dict()
                return ClarificationRequest(
                    question=decision.question, missing_slot="_confirm",
                    partial_intent=completed.intent,
                    partial_entities=completed.entities, raw=text)
            return completed

        if session.state == ConvState.awaiting_confirm:
            confirmed = SafetyGate.resolve_confirmation(text, session)
            if confirmed is True:
                ad = session.pending_action or {}
                session.reset()
                session.state = ConvState.executing
                return ParsedAction(intent=ad.get("intent", "unknown"),
                                    entities=ad.get("entities", {}),
                                    confidence=float(ad.get("confidence", 0.8)),
                                    raw=text, routing="execute")
            elif confirmed is False:
                session.reset()
                return ParsedAction(intent="cancelled", entities={},
                                    confidence=1.0, raw=text, routing="execute")
            else:
                pending  = session.pending_action or {}
                decision = SafetyGate.check(pending)
                return ClarificationRequest(
                    question=decision.question + " Sirf haan ya nahi bolein.",
                    missing_slot="_confirm",
                    partial_intent=pending.get("intent", ""), raw=text)

        if session.state == ConvState.error_recovery:
            session.reset()

        session.state = ConvState.idle
        actions = self._parse_list(text, session.context)
        if not actions:
            return ParsedAction(intent="none", confidence=0.0, raw=text)
        first = actions[0]

        if isinstance(first, ClarificationRequest):
            session.state          = _SLOT_TO_STATE.get(first.missing_slot, ConvState.awaiting_contact)
            session.pending_action = first.to_dict()
            session.pending_slot   = first.missing_slot
            return first

        decision = SafetyGate.check(first.to_dict())
        if not decision.safe:
            session.state          = ConvState.awaiting_confirm
            session.pending_action = first.to_dict()
            return ClarificationRequest(
                question=decision.question, missing_slot="_confirm",
                partial_intent=first.intent,
                partial_entities=first.entities, raw=text)

        session.state = ConvState.executing
        return first

    @staticmethod
    def check_safety(action: dict[str, Any]) -> "SafetyDecision":
        return SafetyGate.check(action)

    def plan(self, text: str, context: dict | None = None) -> ExecutionPlan:
        actions = [a.to_dict() for a in self._parse_list(text, context)]
        return ExecutionPlan(goal=infer_goal(actions), steps=_plan_steps(actions))

    def plan_dict(self, text: str, context: dict | None = None) -> dict:
        return self.plan(text, context).to_dict()

    @staticmethod
    def optimize(plan: ExecutionPlan) -> ExecutionPlan:
        return optimize_plan(plan)

    @staticmethod
    def make_context(actions: list[ParsedAction | ClarificationRequest]) -> dict:
        ctx: dict[str, Any] = {}
        for a in actions:
            if isinstance(a, ParsedAction):
                ctx.update(_extract_memory(a.to_dict()))
        return ctx

    def feedback(self, intent: str, success: bool) -> float:
        new_boost = _boost_store.update(intent, success)
        logger.debug("feedback: %s success=%s boost=%.3f", intent, success, new_boost)
        return new_boost

    @staticmethod
    def recover(failed_action: dict[str, Any], error_reason: str) -> RecoveryAction:
        return ErrorRecovery.build(failed_action, error_reason)


# ── Single clean singleton ────────────────────────────────────────────
parser = CommandParser()


# ======================================================================
#  MODULE 1: CONVERSATION STATE MACHINE
# ======================================================================

from enum import Enum


class ConvState(Enum):
    idle             = "idle"
    awaiting_contact = "awaiting_contact"
    awaiting_message = "awaiting_message"
    awaiting_time    = "awaiting_time"
    awaiting_query   = "awaiting_query"
    awaiting_confirm = "awaiting_confirm"
    executing        = "executing"
    error_recovery   = "error_recovery"


_SLOT_TO_STATE: dict[str, ConvState] = {
    "contact":       ConvState.awaiting_contact,
    "message":       ConvState.awaiting_message,
    "time":          ConvState.awaiting_time,
    "reminder_text": ConvState.awaiting_time,
    "duration":      ConvState.awaiting_time,
    "query":         ConvState.awaiting_query,
    "destination":   ConvState.awaiting_query,
    "keyword":       ConvState.awaiting_query,
}

_STATE_RESOLVES: dict[ConvState, str] = {
    ConvState.awaiting_contact: "contact",
    ConvState.awaiting_message: "message",
    ConvState.awaiting_time:    "time",
    ConvState.awaiting_query:   "query",
}


@dataclass
class SessionState:
    state:          ConvState               = field(default=ConvState.idle)
    pending_action: dict[str, Any] | None   = field(default=None)
    pending_slot:   str                     = field(default="")
    context:        dict[str, Any]          = field(default_factory=dict)

    def reset(self) -> None:
        self.state          = ConvState.idle
        self.pending_action = None
        self.pending_slot   = ""

    def to_dict(self) -> dict:
        return {
            "state":          self.state.value,
            "pending_action": self.pending_action,
            "pending_slot":   self.pending_slot,
        }


def _apply_slot_reply(session: SessionState, raw_text: str) -> ParsedAction:
    """User replied to a clarification question — patch the missing slot."""
    slot   = session.pending_slot
    base   = session.pending_action or {}
    intent = base.get("intent") or base.get("partial_intent", "unknown")
    if intent == "clarify":
        intent = base.get("partial_intent", "unknown")
    ent    = dict(base.get("entities") or base.get("partial_entities") or {})

    if slot == "contact":
        names = [normalize_contact(n)
                 for n in re.split(r"\s+(?:aur|and)\s+", raw_text, flags=re.I)]
        ent["contact"] = [n for n in names if n]

    elif slot == "message":
        ent["message"] = raw_text.strip()

    elif slot in ("time", "duration", "reminder_text"):
        ent[slot] = raw_text.strip()
        if slot == "time":
            parsed = parse_time(raw_text)
            if parsed:
                ent["time_parsed"] = parsed
                dt = to_datetime(parsed)
                if dt:
                    ent["datetime_iso"] = dt.isoformat()

    elif slot == "query":
        ent["query"] = raw_text.strip()

    if intent == "send_message" and not ent.get("platform"):
        ent["platform"] = "whatsapp"

    conf    = float(base.get("confidence", 0.75))
    routing = confidence_routing(conf)
    session.reset()
    return ParsedAction(intent=intent, entities=ent, confidence=conf,
                        raw=raw_text, routing=routing)


# ======================================================================
#  MODULE 2: SAFETY GATE
#  No emoji, no slashes — safe for pyttsx3 TTS
# ======================================================================

HIGH_RISK_INTENTS: frozenset[str] = frozenset({
    "system_control",
    "send_message",
    "call_contact",
    "cancel_reminder",
    "close_app",
})

DESTRUCTIVE_INTENTS: frozenset[str] = frozenset({
    "system_control",
})

_CONFIRM_QUESTIONS: dict[str, str] = {
    "system_control": "Confirm karo: '{detail}' karna hai? Haan ya nahi?",
    "send_message":   "Confirm: '{contact}' ko '{platform}' pe '{message}' bhejna hai? Haan ya nahi?",
    "call_contact":   "Confirm: '{contact}' ko call karna hai? Haan ya nahi?",
    "cancel_reminder":"Confirm: '{keyword}' reminder delete karna hai? Haan ya nahi?",
    "close_app":      "Confirm: '{application}' band karna hai? Haan ya nahi?",
}

_CONFIRM_YES = {"haan", "ha", "yes", "y", "ok", "theek", "kar", "karo", "confirm", "bilkul"}
_CONFIRM_NO  = {"nahi", "no", "n", "mat", "cancel", "rukh", "ruk", "nope", "band karo"}


@dataclass
class SafetyDecision:
    safe:     bool
    question: str = ""
    action:   dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class SafetyGate:
    @classmethod
    def check(cls, action: dict[str, Any]) -> SafetyDecision:
        intent = action.get("intent", "")
        if intent not in HIGH_RISK_INTENTS:
            return SafetyDecision(safe=True, action=action)

        ent  = action.get("entities", {})
        tmpl = _CONFIRM_QUESTIONS.get(intent, "Confirm karo? Haan ya nahi?")

        contacts    = ent.get("contact", [])
        contact_str = ", ".join(contacts) if isinstance(contacts, list) else str(contacts or "?")

        fill = {
            "detail":      ent.get("control_type", intent),
            "contact":     contact_str,
            "platform":    ent.get("platform", "whatsapp"),
            "message":     (ent.get("message") or "")[:60] + ("..." if len(ent.get("message") or "") > 60 else ""),
            "keyword":     ent.get("keyword", "?"),
            "application": ent.get("application", "?"),
        }
        try:
            question = tmpl.format(**fill)
        except KeyError:
            question = f"Confirm: {intent}? Haan ya nahi?"

        return SafetyDecision(safe=False, question=question, action=action)

    @classmethod
    def resolve_confirmation(cls, reply: str, session: SessionState) -> bool | None:
        r = reply.strip().lower()
        if any(w in r for w in _CONFIRM_YES): return True
        if any(w in r for w in _CONFIRM_NO):  return False
        return None


# ======================================================================
#  MODULE 3: ACTION HISTORY
# ======================================================================

@dataclass
class HistoryEntry:
    timestamp:  str
    intent:     str
    entities:   dict[str, Any]
    status:     str
    error:      str = ""
    raw_input:  str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class ActionHistory:
    def __init__(self, max_entries: int = 200) -> None:
        self._log: list[HistoryEntry] = []
        self._max  = max_entries

    def record(self, action: dict[str, Any], status: str,
               error: str = "", raw_input: str = "") -> HistoryEntry:
        entry = HistoryEntry(
            timestamp = datetime.now().isoformat(timespec="seconds"),
            intent    = action.get("intent", "unknown"),
            entities  = dict(action.get("entities", {})),
            status    = status,
            error     = error,
            raw_input = raw_input,
        )
        self._log.append(entry)
        if len(self._log) > self._max:
            self._log.pop(0)
        return entry

    def last_failed(self) -> HistoryEntry | None:
        for e in reversed(self._log):
            if e.status == "failed":
                return e
        return None

    def last_success(self) -> HistoryEntry | None:
        for e in reversed(self._log):
            if e.status == "success":
                return e
        return None

    def intent_stats(self) -> dict[str, dict[str, int]]:
        stats: dict[str, dict[str, int]] = {}
        for e in self._log:
            s = stats.setdefault(e.intent, {"success": 0, "failed": 0, "cancelled": 0, "pending": 0})
            s[e.status] = s.get(e.status, 0) + 1
        return stats

    def recent(self, n: int = 5) -> list[HistoryEntry]:
        return list(reversed(self._log[-n:]))

    def all_dicts(self) -> list[dict]:
        return [e.to_dict() for e in self._log]


# ======================================================================
#  MODULE 4: PLAN OPTIMIZER
# ======================================================================

_INTENT_COST: dict[str, int] = {
    "call_contact": 1, "send_message": 2, "set_reminder": 3,
    "play_music":   4, "open_app":     5, "search_web":   6,
}


def optimize_plan(plan: ExecutionPlan) -> ExecutionPlan:
    if plan.total <= 1:
        return plan

    actions     = [s.action for s in plan.steps]
    independent = [a for a in actions if a.get("intent", "") in _INDEPENDENT_INTENTS]
    dependent   = [a for a in actions if a.get("intent", "") not in _INDEPENDENT_INTENTS]
    dependent.sort(key=lambda a: _INTENT_COST.get(a.get("intent", ""), 99))
    reordered = independent + dependent

    original_order = [a.get("intent") for a in actions]
    new_order      = [a.get("intent") for a in reordered]

    if new_order != original_order:
        for a in reordered:
            if actions.index(a) != reordered.index(a):
                a.setdefault("entities", {})["_optimization_note"] = "reordered by optimizer"

    return ExecutionPlan(goal=plan.goal, steps=_plan_steps(reordered))


# ======================================================================
#  MODULE 5: AI REASONING LAYER
# ======================================================================

_CONDITIONAL_SIGNALS = re.compile(
    r"\b(agar|if|jab|when|unless|jab tak|tab tak|nahi to|otherwise"
    r"|maybe|shayad|ho sake to)\b",
    re.IGNORECASE,
)
_VAGUE_SIGNALS = re.compile(
    r"\b(jo|woh|wala|waali|jo bhi|whatever|kuch bhi|pehle wala|same as before"
    r"|previous|last time|jaise kaha|jaise bataya)\b",
    re.IGNORECASE,
)


def needs_ai_reasoning(text: str, parsed_intent: str) -> bool:
    if parsed_intent == "ai_fallback":
        return True
    if _CONDITIONAL_SIGNALS.search(text):
        return True
    if _VAGUE_SIGNALS.search(text):
        return True
    return False


@dataclass
class AIReasoningResult:
    handled:      bool
    actions:      list[dict[str, Any]] = field(default_factory=list)
    reasoning:    str                  = ""
    raw_response: str                  = ""


class AIReasoningLayer:
    _SYSTEM_PROMPT = """You are Radhe's intent parser. The user has given a command that is too complex for rule-based parsing.

Your task: analyse the command and return a JSON array of ParsedAction objects.

Each ParsedAction must have:
  - "intent": one of the known intents (send_message, call_contact, set_reminder, set_timer, open_app, search_web, youtube_search, play_music, get_weather, get_news, get_time, get_date, take_screenshot, get_battery, system_control, ask_question, ai_fallback)
  - "entities": dict of extracted slot values
  - "confidence": 0.0-1.0
  - "routing": "execute" | "confirm" | "clarify"
  - "reasoning": brief note explaining why you parsed it this way

If you cannot parse the command, return: [{"intent": "ai_fallback", "entities": {"text": "<original>"}, "confidence": 0.3, "routing": "clarify"}]

Return ONLY valid JSON. No markdown, no preamble."""

    @classmethod
    def reason(
        cls,
        text:            str,
        context:         dict | None           = None,
        fallback_action: dict[str, Any] | None = None,
    ) -> AIReasoningResult:
        try:
            import urllib.request

            user_msg = f"Command: {text!r}\nContext: {json.dumps(context or {}, ensure_ascii=False)}"
            payload  = json.dumps({
                "model":      "claude-sonnet-4-5",
                "max_tokens": 1000,
                "system":     cls._SYSTEM_PROMPT,
                "messages":   [{"role": "user", "content": user_msg}],
            }).encode()

            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data    = payload,
                headers = {"Content-Type": "application/json",
                           "anthropic-version": "2023-06-01"},
                method  = "POST",
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                raw = json.loads(resp.read())

            content_blocks = raw.get("content", [])
            text_out = "".join(b.get("text", "") for b in content_blocks if b.get("type") == "text")

            clean   = re.sub(r"```(?:json)?|```", "", text_out).strip()
            actions = json.loads(clean)
            if not isinstance(actions, list):
                actions = [actions]

            reasoning = " | ".join(a.pop("reasoning", "") for a in actions if "reasoning" in a)

            return AIReasoningResult(
                handled=True, actions=actions,
                reasoning=reasoning, raw_response=text_out,
            )

        except Exception as exc:
            logger.debug("AIReasoningLayer unavailable: %s", exc)
            return AIReasoningResult(
                handled  = False,
                actions  = [fallback_action] if fallback_action else [],
                reasoning= f"AI layer unavailable: {exc}",
            )