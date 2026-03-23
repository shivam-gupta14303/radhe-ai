"""
safety_layer.py — Radhe AI Crisis Detection Module v7
======================================================
Pipeline position:

    User Input → safe_process() → Command Parser → Executor / LLM

NEVER send crisis input to LLM.
NEVER generate helpline numbers via AI — all numbers are hardcoded.
"""

import os
import re
import json
import copy
import time
import queue
import hashlib
import datetime
import functools
import threading
from typing import Literal, Callable

# ─────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────

ICALL_NUMBER     = "9152987821"
CRISIS_LOG_FILE  = "crisis_log.jsonl"
MEMORY_FILE      = "radhe_memory.json"

# Texts shorter than this skip LLM classification — not enough signal to classify
LLM_SKIP_BELOW_CHARS = 15

# Seconds before repeating the same level response to the same user
# HIGH = 0 so a user in immediate danger always gets the full response
COOLDOWN_SECONDS = {"high": 0, "medium": 120, "low": 300}

# Rolling window rate limit — shared via Redis when available
RATE_LIMIT_MAX   = 20   # max messages
RATE_LIMIT_SECS  = 60   # per this many seconds

# Escalation retry — max attempts before giving up on a failed webhook
ESCALATION_MAX_RETRIES = 3
ESCALATION_RETRY_DELAY = 5   # seconds between retries

# Redis TTL for persisted user state
_REDIS_TTL = 86400   # 24 hours

CrisisLevel = Literal["none", "low", "medium", "high"]
_SEVERITY   = {"none": 0, "low": 1, "medium": 2, "high": 3}


# ─────────────────────────────────────────────────────────────
# HELPLINES — regional, time-aware
# ─────────────────────────────────────────────────────────────
# Add entries here to expand coverage. Fields:
#   languages: list of language names that trigger this entry
#   states:    list of Indian state names that trigger this entry (optional)
#   hours_ist: (start_hour, end_hour) in 24h IST, or None for 24/7
#   default:   True = always shown regardless of user profile

HELPLINES: list[dict] = [
    {
        "name":      "iCall",
        "number":    "9152987821",
        "languages": ["Hindi", "English", "Marathi"],
        "states":    [],
        "hours_ist": (8, 22),   # 8am–10pm IST
        "note":      "Free, confidential, trained counsellors",
        "default":   True,
    },
    {
        "name":      "Vandrevala Foundation",
        "number":    "1860-2662-345",
        "languages": ["Hindi", "English", "Gujarati", "Marathi", "Bengali"],
        "states":    [],
        "hours_ist": None,      # 24/7
        "note":      "24-hour, free",
        "default":   False,
    },
    {
        "name":      "Snehi",
        "number":    "044-24640050",
        "languages": ["Tamil", "English"],
        "states":    ["Tamil Nadu"],
        "hours_ist": (8, 22),
        "note":      "Chennai-based, Tamil support",
        "default":   False,
    },
    {
        "name":      "Samaritans Mumbai",
        "number":    "84229 84528",
        "languages": ["Hindi", "English", "Marathi"],
        "states":    ["Maharashtra"],
        "hours_ist": (17, 20),  # 5pm–8pm IST
        "note":      "Mumbai-based",
        "default":   False,
    },
    {
        "name":      "Fortis Stress Helpline",
        "number":    "8376804102",
        "languages": ["Hindi", "English"],
        "states":    [],
        "hours_ist": None,      # 24/7
        "note":      "All India, 24-hour",
        "default":   False,
    },
]


def _ist_hour() -> int:
    """Current hour in IST (UTC+5:30)."""
    return (datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)).hour


def get_helpline_text(
    region_language: str | None = None,
    user_state: str | None = None,
    check_hours: bool = True,
) -> str:
    """
    Returns formatted helpline block for crisis responses.

    Selects helplines based on:
    - Default flag (iCall always shown)
    - Language match against region_language
    - State match against user_state
    - Current IST time vs helpline operating hours (if check_hours=True)

    A helpline outside its operating hours is shown with a note rather than
    hidden entirely — better to show an unavailable number than nothing.
    """
    now_h = _ist_hour() if check_hours else 12
    lines = []
    for h in HELPLINES:
        lang_match  = region_language and region_language in h.get("languages", [])
        state_match = user_state and user_state in h.get("states", [])
        if not h["default"] and not lang_match and not state_match:
            continue
        hours = h.get("hours_ist")
        if hours and check_hours and not (hours[0] <= now_h < hours[1]):
            # Outside hours — show with warning rather than hiding
            lines.append(f"• {h['name']}: {h['number']} (currently closed — opens {hours[0]:02d}:00 IST)")
        else:
            lines.append(f"• {h['name']}: {h['number']} ({h.get('note', '')})")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# KEYWORD LISTS
# ─────────────────────────────────────────────────────────────

HIGH_KEYWORDS = [
    # English
    "suicide", "kill myself", "end my life", "i want to die",
    "want to kill myself", "i'll kill myself", "going to kill myself",
    "take my own life", "don't want to be alive", "ending it all",
    "end it all", "not worth living", "better off dead",
    # Hindi / Hinglish
    "marna chahta hu", "marna chahti hu", "khud ko khatam karna",
    "zindagi khatam karna chahta hu", "mar jana chahta hu",
    "mar jana chahti hu", "khatam kar lu apne aap ko",
    "suicide karna chahta hu", "zindagi se thak gaya hu",
]

MEDIUM_KEYWORDS = [
    # English
    "i don't want to live anymore", "i don't want to live like this",
    "life feels pointless", "no point in living", "what's the point",
    "can't go on", "can't do this anymore", "i give up on life",
    "wish i was never born", "nobody would miss me",
    "everyone would be better without me", "i feel trapped",
    "there's no way out", "i feel hopeless", "i see no future",
    "i'm exhausted of everything", "tired of being alive",
    # Hindi / Hinglish
    "jeene ka mann nahi", "jeena nahi chahta", "jeena nahi chahti",
    "zindagi bekar hai", "zindagi ka koi matlab nahi",
    "kuch nahi bachha mere liye", "sab khatam ho gaya",
    "ab nahi raha ja raha", "bahut thak gaya hu zindagi se",
    "bahut thak gayi hu zindagi se", "sab khatam lag raha hai",
    "pata nahi kya karu",
]

LOW_KEYWORDS = [
    # English
    "i'm tired of everything", "i'm so tired", "i feel empty",
    "i feel nothing", "nothing matters", "i'm done",
    "i hate my life", "i can't take it anymore", "i feel so alone",
    "i'm breaking down", "i feel lost", "i'm not okay",
    "feeling really low", "everything feels heavy",
    # Hindi / Hinglish
    "kuch karne ka mann nahi", "sab bekar lag raha hai",
    "bahut akela feel ho raha hai", "bahut thak gaya hu",
    "bahut thak gayi hu", "kuch accha nahi lag raha",
    "dil nahi kar raha kuch bhi", "bohot bura lag raha hai",
    "rone ka mann kar raha hai",
]

# Regional Indian languages (romanised transliteration for chat matching)
REGIONAL_HIGH_KEYWORDS = [
    "naan saaga virukkiren", "enakku vazhkai vendam", "naan irakka poren",       # Tamil
    "nenu chaavaalani undi", "naaku jeevitam vendam", "nenu chastaanu",           # Telugu
    "nanu saayabeku", "naaku jeevana beda",                                       # Kannada
    "ami morte chai", "amar jibon sesh korte chai", "ami bachte chai na",         # Bengali
    "mala marayche ahe", "mala jagayche nahi", "jiv dyaycha ahe mala",           # Marathi
]

REGIONAL_MEDIUM_KEYWORDS = [
    "vazha pidikkavillai", "ellam mudinjiruchu", "enakku onnum puriyala",         # Tamil
    "naaku em ardam kaatledu", "naaku chaala anipistundi", "jeevitam arthamledu", # Telugu
    "naaku enu arthaagalla", "naaku tumba kastavaagide",                          # Kannada
    "sobkichu shesh hoye gache", "kichhu bhalo lagche na",                        # Bengali
    "kahi sucharena", "sare sampale ase vaatate", "jagu vatana nahi",             # Marathi
]

REGIONAL_LOW_KEYWORDS = [
    "romba kavalappaduren", "enakku santhosham illa",                             # Tamil
    "naaku chaala dukkham ga undi", "naaku emi kavali ante teliyadam ledu",       # Telugu
    "naaku tumba kasta aagide", "naaku yenu sari illa",                           # Kannada
    "ami khub ekaki", "ami khub thaka", "ami bhalo nei",                          # Bengali
    "khup ekta vatate", "mala bara nahi vatate",                                  # Marathi
]


# ─────────────────────────────────────────────────────────────
# AUTO LANGUAGE DETECTION
# ─────────────────────────────────────────────────────────────
# Detects the user's language from their input so safe_process can
# automatically surface the right regional helplines without needing
# the caller to pass region_language manually.
#
# Strategy: Unicode script detection + romanised keyword frequency.
# No external libraries required.

# Unicode ranges for non-Latin scripts
_SCRIPT_RANGES: list[tuple[int, int, str]] = [
    (0x0900, 0x097F, "Hindi"),      # Devanagari
    (0x0980, 0x09FF, "Bengali"),    # Bengali
    (0x0C00, 0x0C7F, "Telugu"),     # Telugu
    (0x0B80, 0x0BFF, "Tamil"),      # Tamil
    (0x0C80, 0x0CFF, "Kannada"),    # Kannada
    (0x0A80, 0x0AFF, "Gujarati"),   # Gujarati
    (0x0B00, 0x0B7F, "Odia"),       # Odia
    (0x0A00, 0x0A7F, "Punjabi"),    # Gurmukhi
    (0x0D00, 0x0D7F, "Malayalam"),  # Malayalam
]

# Romanised language markers — distinctive words/patterns per language
_ROMAN_MARKERS: dict[str, list[str]] = {
    "Tamil":    ["naan", "enna", "inga", "sollu", "paaru", "romba", "illa",
                 "vandhen", "ponnu", "paiyan", "vandha", "irukku"],
    "Telugu":   ["nenu", "naaku", "meeru", "emundi", "cheppandi", "ledu",
                 "undi", "antanu", "chestanu", "kaadu", "ayindi"],
    "Kannada":  ["naanu", "nimage", "enu", "illa", "beku", "heli", "madri",
                 "barteeni", "hogteeni", "aagide", "nimdu"],
    "Bengali":  ["ami", "amar", "tumi", "tomake", "ache", "nei", "bhalo",
                 "lagche", "korbo", "jabo", "khub", "ekaki"],
    "Marathi":  ["mala", "mazha", "tumhi", "aahe", "nahi", "kaay", "kasa",
                 "sangto", "jato", "yeto", "vatate", "hoil"],
    "Gujarati": ["hoon", "mane", "tame", "chhe", "nathi", "su", "karo",
                 "jaoo", "aavoo", "bolyo", "chhoo", "game"],
}


def detect_language(text: str) -> str | None:
    """
    Infers the user's language from their message.

    Returns a language name string (e.g. "Tamil", "Bengali", "Hindi")
    or None if the language cannot be determined with confidence.

    Steps:
    1. Check for native script characters — highest confidence, instant.
    2. Count romanised marker words per language — catches Hinglish-style input.
    3. Return the top match only if it has >= 2 marker hits to avoid guessing.
    """
    # Native script detection — single character is enough to be confident
    for ch in text:
        cp = ord(ch)
        for start, end, lang in _SCRIPT_RANGES:
            if start <= cp <= end:
                return lang

    # Romanised marker count
    t_lower = text.lower()
    words   = set(t_lower.split())
    scores: dict[str, int] = {}
    for lang, markers in _ROMAN_MARKERS.items():
        hits = sum(1 for m in markers if m in words)
        if hits > 0:
            scores[lang] = hits

    if not scores:
        return None
    top_lang  = max(scores, key=lambda k: scores[k])
    top_score = scores[top_lang]
    # Require at least 2 marker hits to avoid false positives from short overlap
    return top_lang if top_score >= 2 else None

_PII_PATTERNS = [
    (re.compile(r"\b(\+91[\s-]?)?[6-9]\d{9}\b"),                    "<phone>"),
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[a-z]{2,}\b", re.I),          "<email>"),
    (re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b"),                     "<id_number>"),
    (re.compile(r"\b\d{8,}\b"),                                      "<number>"),
    (re.compile(r"(my name is|mera naam)\s+\w+", re.I),             r"\1 <name>"),
]


def _mask_pii(text: str) -> str:
    for pattern, replacement in _PII_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _safe_preview(text: str, max_chars: int = 120) -> str:
    """Mask PII then truncate — safe for log storage."""
    return _mask_pii(text[:500])[:max_chars]


def _input_hash(text: str) -> str:
    """One-way hash for deduplication — not reversible."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


# ─────────────────────────────────────────────────────────────
# FUZZY KEYWORD MATCHING
# ─────────────────────────────────────────────────────────────
# Catches spelling variations ("suicied", "kil myself") that exact
# substring matching misses. Uses Levenshtein distance — no external deps.
# Only applied to keywords >= 5 chars to avoid false positives on short words.

def _levenshtein(a: str, b: str) -> int:
    """Character edit distance between two strings."""
    if len(a) < len(b):
        a, b = b, a
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for ca in a:
        curr = [prev[0] + 1]
        for j, cb in enumerate(b):
            curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (ca != cb)))
        prev = curr
    return prev[-1]


# Cache Levenshtein results — same (word, keyword) pairs recur across messages
@functools.lru_cache(maxsize=2048)
def _levenshtein_cached(a: str, b: str) -> int:
    return _levenshtein(a, b)


def _fuzzy_match(text: str, keywords: list[str]) -> bool:
    """
    Returns True if any keyword matches the text — exact substring first,
    then single-word fuzzy for typos and transpositions.

    Fuzzy is applied only to single-word keywords >= 5 chars.
    Multi-word phrases use exact substring only (avoids cross-phrase false positives).

    Edit distance tolerance by keyword length:
    - 5–6 chars  → 1 edit
    - 7–10 chars → 2 edits
    - 11+ chars  → 3 edits
    """
    t = text.lower()
    words = t.split()
    for kw in keywords:
        # Fast path: exact substring — no allocations, O(n)
        if kw in t:
            return True
        # Skip fuzzy for short or multi-word keywords
        if len(kw) < 5 or " " in kw:
            continue
        if len(kw) <= 6:    max_dist = 1
        elif len(kw) <= 10: max_dist = 2
        else:               max_dist = 3
        for word in words:
            # Cheap length pre-filter — skip if word can't possibly be within tolerance
            if abs(len(word) - len(kw)) > max_dist:
                continue
            if _levenshtein_cached(word, kw) <= max_dist:
                return True
    return False


# ─────────────────────────────────────────────────────────────
# KEYWORD DETECTION — fast, zero-cost first pass
# ─────────────────────────────────────────────────────────────

def _keyword_level(text: str) -> CrisisLevel:
    t = text.lower()
    for level, kw_lists in [
        ("high",   [HIGH_KEYWORDS, REGIONAL_HIGH_KEYWORDS]),
        ("medium", [MEDIUM_KEYWORDS, REGIONAL_MEDIUM_KEYWORDS]),
        ("low",    [LOW_KEYWORDS, REGIONAL_LOW_KEYWORDS]),
    ]:
        for kw_list in kw_lists:
            if _fuzzy_match(t, kw_list):
                return level  # type: ignore
    return "none"


# ─────────────────────────────────────────────────────────────
# LLM CLASSIFICATION — semantic, catches indirect signals
# ─────────────────────────────────────────────────────────────

# Set to a callable(str) -> CrisisLevel to use a local model instead of the API.
# Example: from local_crisis_model import predict; LOCAL_CLASSIFIER = predict
LOCAL_CLASSIFIER = None


def _llm_classify(text: str) -> CrisisLevel:
    """
    Semantic crisis classification via LLM (or LOCAL_CLASSIFIER if set).
    Fail-safe: any error returns "low" — never "none" — because we cannot
    confirm the user is safe when the classifier is unavailable.
    """
    def _llm_classify(text: str) -> CrisisLevel:
        if LOCAL_CLASSIFIER is not None:
            try:
                result = LOCAL_CLASSIFIER(text)
                if result in ("high", "medium", "low", "none"):
                    return result  # type: ignore
            except Exception as e:
                _write_log({"event": "local_classifier_error", "error": str(e), "timestamp": _now()})

        try:
            from groq import Groq
            client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
            message = client.chat.completions.create(
                model="llama-3.3-70b-versatile",   # best free Groq model
                max_tokens=10,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a crisis detection classifier for a mental health AI.\n"
                            "Classify the user message into exactly one level:\n"
                            '- "high"   : Direct suicidal ideation, explicit self-harm intent\n'
                            '- "medium" : Strong hopelessness, feeling trapped, indirect signals\n'
                            '- "low"    : Sadness, exhaustion, overwhelm — no direct harm signals\n'
                            '- "none"   : Normal conversation, no distress\n'
                            "Output ONLY the level word. When unsure, choose the HIGHER level.\n"
                            "Consider Hindi, Hinglish, and indirect expressions."
                        ),
                    },
                    {"role": "user", "content": text},
                ],
            )
            raw = message.choices[0].message.content.strip().lower()
            if raw in ("high", "medium", "low", "none"):
                return raw  # type: ignore
            return "low"
        except Exception as e:
            _write_log({"event": "llm_classify_error", "error": str(e), "fallback": "low", "timestamp": _now()})
            return "low"


# ─────────────────────────────────────────────────────────────
# HYBRID DETECTOR
# ─────────────────────────────────────────────────────────────

def detect_crisis_level(text: str, use_llm: bool = True) -> CrisisLevel:
    """
    Two-pass detection: keywords first (fast), then LLM (semantic).
    - HIGH/MEDIUM from keywords → skip LLM (confident signal, save cost)
    - Short text → skip LLM (insufficient signal for semantic analysis)
    - Otherwise → run both, take the higher severity result
    """
    keyword_result = _keyword_level(text)
    if keyword_result in ("high", "medium"):
        return keyword_result
    if not use_llm or len(text.strip()) < LLM_SKIP_BELOW_CHARS:
        return keyword_result
    llm_result = _llm_classify(text)
    return llm_result if _SEVERITY[llm_result] > _SEVERITY[keyword_result] else keyword_result


def detect_crisis(text: str, use_llm: bool = True) -> bool:
    """Convenience boolean — True if any crisis level detected."""
    return detect_crisis_level(text, use_llm=use_llm) != "none"


# ─────────────────────────────────────────────────────────────
# ESCALATION TRACKING
# ─────────────────────────────────────────────────────────────

def get_escalation_trend(user_id: str = "default") -> str:
    """
    Computes trend from recent crisis history for a user.
    Returns "escalating", "stable", "de-escalating", or "insufficient_data".
    Uses last 5 events only to avoid stale history skewing the result.
    """
    history = _get_user_state(user_id).get("level_history", [])
    if len(history) < 2:
        return "insufficient_data"
    scores  = [_SEVERITY[h["level"]] for h in history[-5:]]
    deltas  = [scores[i+1] - scores[i] for i in range(len(scores)-1)]
    avg     = sum(deltas) / len(deltas)
    if avg > 0.3:  return "escalating"
    if avg < -0.3: return "de-escalating"
    return "stable"


# ─────────────────────────────────────────────────────────────
# REDIS — persistent cross-server state
# Set REDIS_URL env var to activate. Falls back to in-memory if absent.
# Rate limit uses Redis sorted sets so it works across multiple server instances.
# ─────────────────────────────────────────────────────────────

_REDIS_CLIENT = None


def _get_redis():
    """Lazily connects to Redis. Returns None if unavailable."""
    global _REDIS_CLIENT
    if _REDIS_CLIENT is not None:
        return _REDIS_CLIENT
    url = os.environ.get("REDIS_URL")
    if not url:
        return None
    try:
        import redis
        c = redis.from_url(url, decode_responses=True)
        c.ping()
        _REDIS_CLIENT = c
        return c
    except Exception:
        return None


def _redis_get_state(user_id: str) -> dict | None:
    r = _get_redis()
    if not r:
        return None
    try:
        raw = r.get(f"radhe:crisis:{user_id}")
        if raw:
            data = json.loads(raw)
            if data.get("timestamp"):
                data["timestamp"] = datetime.datetime.fromisoformat(data["timestamp"])
            return data
    except Exception:
        pass
    return None


def _redis_set_state(user_id: str, state: dict) -> None:
    r = _get_redis()
    if not r:
        return
    try:
        s = dict(state)
        if isinstance(s.get("timestamp"), datetime.datetime):
            s["timestamp"] = s["timestamp"].isoformat()
        r.set(f"radhe:crisis:{user_id}", json.dumps(s), ex=_REDIS_TTL)
    except Exception:
        pass


def _redis_rate_check(user_id: str) -> bool:
    """
    Redis-backed rolling window rate limit using a sorted set.
    Key: "radhe:rate:{user_id}", score = unix timestamp, member = unique token.
    Works across multiple server instances — in-memory fallback is per-process only.
    Returns True if the user is rate-limited.
    """
    r = _get_redis()
    if not r:
        return False   # fall through to in-memory check below
    try:
        key = f"radhe:rate:{user_id}"
        now = time.time()
        cutoff = now - RATE_LIMIT_SECS
        pipe = r.pipeline()
        pipe.zremrangebyscore(key, "-inf", cutoff)
        pipe.zadd(key, {str(now): now})
        pipe.zcard(key)
        pipe.expire(key, RATE_LIMIT_SECS * 2)
        results = pipe.execute()
        count = results[2]
        return count > RATE_LIMIT_MAX
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────
# PER-USER STATE — cooldown, history, response count
# ─────────────────────────────────────────────────────────────

_user_states: dict[str, dict] = {}

_DEFAULT_STATE: dict = {
    "level":          "none",
    "timestamp":      None,
    "response_count": 0,
    "level_history":  [],
}


def _get_user_state(user_id: str) -> dict:
    redis_state = _redis_get_state(user_id)
    if redis_state is not None:
        _user_states[user_id] = redis_state
        return _user_states[user_id]
    if user_id not in _user_states:
        _user_states[user_id] = copy.deepcopy(_DEFAULT_STATE)
    return _user_states[user_id]


def _is_in_cooldown(level: CrisisLevel, user_id: str) -> bool:
    if level == "high":
        return False
    state = _get_user_state(user_id)
    if state["level"] != level or not state["timestamp"]:
        return False
    elapsed = (datetime.datetime.utcnow() - state["timestamp"]).total_seconds()
    return elapsed < COOLDOWN_SECONDS.get(level, 120)


def _update_state(level: CrisisLevel, user_id: str) -> None:
    state = _get_user_state(user_id)
    state["level_history"].append({"level": level, "timestamp": _now()})
    state["level"]          = level
    state["timestamp"]      = datetime.datetime.utcnow()
    state["response_count"] += 1
    _redis_set_state(user_id, state)


# ─────────────────────────────────────────────────────────────
# RATE LIMITING — in-memory fallback when Redis absent
# ─────────────────────────────────────────────────────────────

_rate_buckets: dict[str, list] = {}


def _is_rate_limited(user_id: str) -> bool:
    if _redis_rate_check(user_id):
        return True
    # In-memory fallback (per-process only — use Redis for multi-server)
    now    = datetime.datetime.utcnow()
    cutoff = now - datetime.timedelta(seconds=RATE_LIMIT_SECS)
    bucket = _rate_buckets.setdefault(user_id, [])
    _rate_buckets[user_id] = [t for t in bucket if t > cutoff]
    if len(_rate_buckets[user_id]) >= RATE_LIMIT_MAX:
        return True
    _rate_buckets[user_id].append(now)
    return False


_RATE_LIMITED_RESPONSE = (
    "Main sun raha hoon. Thoda ruko — main yahaan hoon.\n\n"
    f"Agar tum abhi bahut distress mein ho, please iCall call karo: {ICALL_NUMBER}"
)


# ─────────────────────────────────────────────────────────────
# HUMAN ESCALATION — pluggable, bounded retry queue
# ─────────────────────────────────────────────────────────────
# Assign any callable(user_id, level, trend) → None.
# Fires on level=="high" or trend=="escalating".
#
# Failed calls are queued (max 100 items) and retried by a single
# persistent background worker — no unbounded thread spawning.
# If the queue is full, the event is logged and dropped rather than
# creating more threads and exhausting memory under a failure storm.
#
# Example:
#   import safety_layer, requests
#   def my_webhook(user_id, level, trend):
#       requests.post("https://yourapp.com/crisis-alert",
#                     json={"user_id": user_id, "level": level, "trend": trend})
#   safety_layer.HUMAN_ESCALATION_HANDLER = my_webhook

HUMAN_ESCALATION_HANDLER = None

# Bounded queue: (user_id, level, trend, attempt)
_escalation_queue: queue.Queue = queue.Queue(maxsize=100)
_escalation_worker_started = False
_escalation_worker_lock    = threading.Lock()


def _escalation_worker() -> None:
    """Single background worker that drains the escalation retry queue."""
    while True:
        try:
            user_id, level, trend, attempt = _escalation_queue.get(timeout=30)
        except queue.Empty:
            continue
        time.sleep(ESCALATION_RETRY_DELAY)
        try:
            if HUMAN_ESCALATION_HANDLER:
                HUMAN_ESCALATION_HANDLER(user_id, level, trend)
            _write_log({"event": "human_escalation_retry_success",
                        "attempt": attempt, "timestamp": _now()})
        except Exception as e:
            _write_log({"event": "human_escalation_retry_failed",
                        "attempt": attempt, "error": str(e), "timestamp": _now()})
            if attempt < ESCALATION_MAX_RETRIES:
                try:
                    _escalation_queue.put_nowait((user_id, level, trend, attempt + 1))
                except queue.Full:
                    _write_log({"event": "human_escalation_queue_full",
                                "timestamp": _now()})
            else:
                _write_log({"event": "human_escalation_exhausted",
                            "user_id": _input_hash(user_id), "level": level,
                            "timestamp": _now()})
        finally:
            _escalation_queue.task_done()


def _ensure_escalation_worker() -> None:
    """Start the worker thread exactly once (lazy init, thread-safe)."""
    global _escalation_worker_started
    if _escalation_worker_started:
        return
    with _escalation_worker_lock:
        if not _escalation_worker_started:
            t = threading.Thread(target=_escalation_worker, daemon=True)
            t.start()
            _escalation_worker_started = True


def _maybe_escalate_to_human(user_id: str, level: CrisisLevel, trend: str) -> None:
    if HUMAN_ESCALATION_HANDLER is None:
        return
    if level != "high" and trend != "escalating":
        return
    _ensure_escalation_worker()
    try:
        HUMAN_ESCALATION_HANDLER(user_id, level, trend)
        _write_log({"event": "human_escalation_triggered",
                    "user_id": _input_hash(user_id), "level": level,
                    "trend": trend, "timestamp": _now()})
    except Exception as e:
        _write_log({"event": "human_escalation_error", "error": str(e),
                    "attempt": 1, "timestamp": _now()})
        try:
            _escalation_queue.put_nowait((user_id, level, trend, 2))
        except queue.Full:
            _write_log({"event": "human_escalation_queue_full", "timestamp": _now()})


# ─────────────────────────────────────────────────────────────
# CRISIS RESPONSES — Validate → Acknowledge → Guide → Real humans
# All responses are hardcoded. Never AI-generated.
# ─────────────────────────────────────────────────────────────

_RESPONSES_FIRST: dict = {
    "high": (
        "Main rahat mehsoos karta hoon ki tumne yeh share kiya — yeh bolna "
        "akele mein bahut mushkil hota hai.\n\n"
        "Jo tum feel kar rahe ho woh bahut bhari cheez hai. Tum is bojh ko "
        "akele uthane ke liye nahi ho.\n\n"
        "Yeh helplines available hain — free, confidential:\n{helplines}\n\n"
        "Agar tumhare paas koi dost, family member, ya bharosa wala insaan hai "
        "— unhe bhi reach karo. Real people tumhari madad waise kar sakte hain "
        "jaise main nahi kar sakta.\n\n"
        "Main yahaan hoon. Agar tum ready ho, toh call karna helpful ho sakta hai."
    ),
    "medium": (
        "Main sun raha hoon — aur yeh jo tum share kar rahe ho, yeh real hai.\n\n"
        "Aisa feel karna ki koi rasta nahi hai — yeh bahut heavy hota hai. "
        "Aur yeh sirf 'thoda aur try karo' waali situation nahi hai.\n\n"
        "Ek suggestion hai — kisi se baat karna helpful ho sakta hai:\n{helplines}\n\n"
        "Koi kareeb insaan hai jis par trust karte ho? Unhe bhi bata sakte ho "
        "how you're really feeling.\n\n"
        "Abhi kya chal raha hai tumhare saath?"
    ),
    "low": (
        "Lag raha hai ki abhi sab kuch bahut heavy feel ho raha hai.\n\n"
        "Yeh valid hai — kabhi kabhi itna zyada ho jaata hai ki sab meaningless "
        "lagta hai. Tum jo feel kar rahe ho, woh real hai.\n\n"
        "Agar kabhi cheezein bahut zyada ho jayein, iCall available hai: {number}\n\n"
        "Kya tum mujhe batana chahoge kya chal raha hai? Main sun raha hoon."
    ),
}

# Follow-up responses used when cooldown is active (user repeating distress signals)
_RESPONSES_FOLLOWUP: dict = {
    "high": _RESPONSES_FIRST["high"],
    "medium": (
        "Main abhi bhi yahaan hoon, aur main sun raha hoon.\n\n"
        "Yeh jo feel ho raha hai — yeh real hai. Tum isse minimize mat karo.\n\n"
        "Kya tumne helpline call ki? Abhi bhi woh option open hai:\n{helplines}\n\n"
        "Koi ek cheez batao — abhi is moment mein kya ho raha hai?"
    ),
    "low": (
        "Main dekh sakta hoon ki sab kuch abhi bhi heavy lag raha hai.\n\n"
        "Koi ek cheez hai jo tumhe thoda better feel kara sake aaj? "
        "Kuch bhi — chhota sa bhi chalega."
    ),
}


def crisis_response(
    level: CrisisLevel,
    user_id: str = "default",
    region_language: str | None = None,
    user_state: str | None = None,
) -> str:
    """
    Returns the hardcoded Soul-aligned response for this level.
    Selects first-time or follow-up variant based on cooldown state.
    Injects region/time-appropriate helplines.
    """
    if level == "none":
        return ""
    helpline_block = get_helpline_text(region_language, user_state)
    template = (
        _RESPONSES_FOLLOWUP[level]
        if _is_in_cooldown(level, user_id)
        else _RESPONSES_FIRST[level]
    )
    _update_state(level, user_id)
    return template.format(number=ICALL_NUMBER, helplines=helpline_block)


# ─────────────────────────────────────────────────────────────
# FOLLOW-UP CONTEXT — injected into next LLM system prompt
# ─────────────────────────────────────────────────────────────

_STAY_MINUTES = {"high": 15, "medium": 10, "low": 5}


def get_crisis_followup_context(
    level: CrisisLevel,
    user_id: str = "default",
) -> dict:
    """
    Returns a dict to inject into the next LLM call after a crisis response.

    Keys:
    - system_addendum : append to LLM system prompt to keep Radhe in
                        supportive mode rather than snapping back to task mode
    - stay_with_user  : True while within the timeout window
    - stay_until      : ISO timestamp — check this before each LLM call;
                        clear the addendum once this time has passed
    - trend           : escalation trend string for your own monitoring
    - crisis_level    : current level
    """
    if level == "none":
        return {}
    trend      = get_escalation_trend(user_id)
    stay_until = (
        datetime.datetime.utcnow()
        + datetime.timedelta(minutes=_STAY_MINUTES.get(level, 10))
    ).isoformat() + "Z"
    escalation_note = (
        "\nCAUTION: This user's distress level has been escalating — be especially gentle."
        if trend == "escalating" else ""
    )
    addenda = {
        "high": (
            "IMPORTANT: This user recently expressed serious distress. "
            "Do NOT return to normal assistant mode. Stay warm, go slow. "
            "Only listen and validate. Gently encourage them to call iCall "
            f"({ICALL_NUMBER}) or reach out to someone they trust."
            + escalation_note
        ),
        "medium": (
            "IMPORTANT: This user recently expressed emotional distress. "
            "Stay supportive. Do not rush into problem-solving or tasks. "
            "Validate first, ask gentle follow-up questions."
            + escalation_note
        ),
        "low": (
            "NOTE: This user is having a hard time emotionally. "
            "Check in softly before diving into any tasks they request."
            + escalation_note
        ),
    }
    return {
        "crisis_level":    level,
        "system_addendum": addenda.get(level, ""),
        "stay_with_user":  True,
        "stay_until":      stay_until,
        "trend":           trend,
    }


# ─────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"


def _write_log(record: dict) -> None:
    try:
        with open(CRISIS_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass  # logging must never crash the main flow


def log_crisis_event(
    user_input: str,
    level: CrisisLevel,
    detection_method: str = "hybrid",
    user_id: str = "default",
) -> None:
    """
    Privacy-safe crisis event log entry.
    Stores masked preview + one-way hash. Never stores raw input or PII.
    """
    _write_log({
        "event":            "crisis_detected",
        "timestamp":        _now(),
        "level":            level,
        "detection_method": detection_method,
        "trend":            get_escalation_trend(user_id),
        "input_length":     len(user_input),
        "input_hash":       _input_hash(user_input),
        "input_preview":    _safe_preview(user_input),
        "response_count":   _get_user_state(user_id)["response_count"],
    })


# ─────────────────────────────────────────────────────────────
# MEMORY INTEGRATION
# ─────────────────────────────────────────────────────────────

def save_crisis_memory(
    level: CrisisLevel,
    memory_store: dict | None = None,
    user_id: str = "default",
) -> None:
    """
    Writes distress signal to memory so future Radhe responses stay
    warmer and check in rather than jumping straight into task mode.
    Pass memory_store to update your existing session dict in-place,
    or leave None to write to MEMORY_FILE.
    """
    entry = {
        "type":      "distress_signal",
        "level":     level,
        "trend":     get_escalation_trend(user_id),
        "timestamp": _now(),
        "note":      "Future responses must be warmer and check in before tasks.",
    }
    if memory_store is not None:
        memory_store.setdefault("distress_history", []).append(entry)
        return
    try:
        data: dict = {}
        if os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        data.setdefault("distress_history", []).append(entry)
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        _write_log({"event": "memory_save_error", "error": str(e), "timestamp": _now()})


# ─────────────────────────────────────────────────────────────
# AUDIT DASHBOARD
# ─────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────
# AUDIT DASHBOARD — static export + live server
# ─────────────────────────────────────────────────────────────

def _build_dashboard_html(events: list[dict]) -> str:
    """Builds the dashboard HTML string from a list of log events."""
    crisis_events = [e for e in events if e.get("event") == "crisis_detected"]
    total    = len(crisis_events)
    by_level = {"high": 0, "medium": 0, "low": 0}
    by_trend = {"escalating": 0, "stable": 0, "de-escalating": 0, "insufficient_data": 0}
    hourly: dict[str, int] = {}

    for e in crisis_events:
        lvl = e.get("level", "")
        if lvl in by_level:
            by_level[lvl] += 1
        tr = e.get("trend", "")
        if tr in by_trend:
            by_trend[tr] += 1
        ts = e.get("timestamp", "")
        if ts:
            try:
                hourly[ts[:13]] = hourly.get(ts[:13], 0) + 1
            except Exception:
                pass

    recent = sorted(crisis_events, key=lambda e: e.get("timestamp", ""), reverse=True)[:20]
    now_dt = datetime.datetime.utcnow()
    chart_labels, chart_values = [], []
    for h in range(71, -1, -1):
        dt  = now_dt - datetime.timedelta(hours=h)
        key = dt.strftime("%Y-%m-%dT%H")
        chart_labels.append(dt.strftime("%d/%m %H:00"))
        chart_values.append(hourly.get(key, 0))

    level_colors = {"high": "#ef4444", "medium": "#f97316", "low": "#eab308"}
    rows = ""
    for e in recent:
        lvl   = e.get("level", "")
        color = level_colors.get(lvl, "#6b7280")
        rows += (
            f"<tr>"
            f"<td>{e.get('timestamp','')[:19].replace('T',' ')}</td>"
            f"<td><span style='color:{color};font-weight:600'>{lvl.upper()}</span></td>"
            f"<td>{e.get('trend','')}</td>"
            f"<td>{e.get('input_preview','')}</td>"
            f"<td>{e.get('response_count','')}</td>"
            f"</tr>\n"
        )

    generated = _now()[:19].replace("T", " ")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta http-equiv="refresh" content="30">
<title>Radhe — Crisis Safety Audit</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:system-ui,sans-serif;background:#0f172a;color:#e2e8f0;padding:24px}}
  h1{{font-size:1.5rem;font-weight:700;margin-bottom:4px}}
  .sub{{color:#94a3b8;font-size:.85rem;margin-bottom:24px}}
  .cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:16px;margin-bottom:28px}}
  .card{{background:#1e293b;border-radius:12px;padding:20px}}
  .card .lbl{{font-size:.75rem;color:#94a3b8;margin-bottom:6px;text-transform:uppercase;letter-spacing:.05em}}
  .card .val{{font-size:2rem;font-weight:700}}
  .card.high .val{{color:#ef4444}}.card.medium .val{{color:#f97316}}.card.low .val{{color:#eab308}}
  .section{{background:#1e293b;border-radius:12px;padding:20px;margin-bottom:20px}}
  .section h2{{font-size:1rem;font-weight:600;margin-bottom:16px;color:#cbd5e1}}
  .chart-wrap{{height:220px}}
  table{{width:100%;border-collapse:collapse;font-size:.82rem}}
  th{{text-align:left;padding:8px 12px;color:#94a3b8;border-bottom:1px solid #334155;font-weight:500}}
  td{{padding:8px 12px;border-bottom:1px solid #1e293b;vertical-align:top;max-width:300px;word-break:break-word}}
  tr:hover td{{background:#243044}}
  .live{{display:inline-block;width:8px;height:8px;border-radius:50%;background:#22c55e;margin-right:6px;animation:pulse 2s infinite}}
  @keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.4}}}}
</style>
</head>
<body>
<h1>Radhe — Crisis Safety Audit</h1>
<p class="sub">
  <span class="live"></span>Auto-refreshes every 30s &nbsp;·&nbsp;
  {generated} UTC &nbsp;·&nbsp; {CRISIS_LOG_FILE}
</p>

<div class="cards">
  <div class="card"><div class="lbl">Total</div><div class="val">{total}</div></div>
  <div class="card high"><div class="lbl">High</div><div class="val">{by_level["high"]}</div></div>
  <div class="card medium"><div class="lbl">Medium</div><div class="val">{by_level["medium"]}</div></div>
  <div class="card low"><div class="lbl">Low</div><div class="val">{by_level["low"]}</div></div>
  <div class="card"><div class="lbl">Escalating</div><div class="val">{by_trend["escalating"]}</div></div>
</div>

<div class="section">
  <h2>Event Volume — Last 72 Hours (UTC)</h2>
  <div class="chart-wrap"><canvas id="chart"></canvas></div>
</div>

<div class="section">
  <h2>Recent Events</h2>
  <table>
    <tr><th>Timestamp</th><th>Level</th><th>Trend</th><th>Preview</th><th>#</th></tr>
    {rows}
  </table>
</div>

<script>
new Chart(document.getElementById('chart').getContext('2d'),{{
  type:'bar',
  data:{{
    labels:{json.dumps(chart_labels[::4])},
    datasets:[{{label:'Events',data:{json.dumps([sum(chart_values[i:i+4]) for i in range(0,72,4)])},
      backgroundColor:'#6366f1',borderRadius:4}}]
  }},
  options:{{
    responsive:true,maintainAspectRatio:false,
    plugins:{{legend:{{display:false}}}},
    scales:{{
      x:{{ticks:{{color:'#64748b',maxRotation:45}},grid:{{color:'#1e293b'}}}},
      y:{{ticks:{{color:'#64748b'}},grid:{{color:'#334155'}},beginAtZero:true}}
    }}
  }}
}});
</script>
</body></html>"""


def _load_log_events() -> list[dict]:
    events: list[dict] = []
    if not os.path.exists(CRISIS_LOG_FILE):
        return events
    with open(CRISIS_LOG_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return events


def generate_audit_report(output_path: str = "audit_report.html") -> str:
    """
    Writes a standalone HTML audit dashboard to output_path and returns the path.
    The file auto-refreshes every 30 seconds when opened in a browser.

    Run from terminal:
        python -c "from safety_layer import generate_audit_report; generate_audit_report()"
    """
    html = _build_dashboard_html(_load_log_events())
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    return output_path


def start_dashboard_server(host: str = "127.0.0.1", port: int = 8765) -> None:
    """
    Starts a lightweight live HTTP dashboard server (no external dependencies).
    The page re-reads crisis_log.jsonl on every request so it always shows
    current data without restarting.

    Usage:
        # In a terminal / background thread:
        from safety_layer import start_dashboard_server
        start_dashboard_server()          # opens on http://127.0.0.1:8765

        # Or from command line:
        python -c "from safety_layer import start_dashboard_server; start_dashboard_server()"

    To run without blocking your main thread:
        import threading, safety_layer
        t = threading.Thread(target=safety_layer.start_dashboard_server, daemon=True)
        t.start()
    """
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            html = _build_dashboard_html(_load_log_events()).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)

        def log_message(self, *args) -> None:
            pass  # suppress access log noise

    server = HTTPServer((host, port), _Handler)
    print(f"Radhe audit dashboard → http://{host}:{port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


# ─────────────────────────────────────────────────────────────
# MAIN GATE
# ─────────────────────────────────────────────────────────────

def safe_process(
    user_input: str,
    llm_call_fn: Callable[[str], str],
    memory_store: dict | None = None,
    use_llm_classification: bool = True,
    user_id: str = "default",
    region_language: str | None = None,
    user_state: str | None = None,
) -> tuple[str, dict]:
    """
    The entry point. Call this instead of your LLM directly.

        User Input → safe_process() → Command Parser → Executor / LLM

    Args:
        user_input             : Raw text from the user
        llm_call_fn            : Your LLM callable — (str) → str
        memory_store           : Optional session dict for in-place memory updates
        use_llm_classification : False to skip LLM (tests / offline mode)
        user_id                : Session/user identifier for per-user state
        region_language        : e.g. "Tamil" — surfaces relevant helplines
        user_state             : Indian state name — surfaces regional helplines

    Returns:
        (response, context_dict)

        context_dict for crisis responses contains:
          system_addendum — append to next LLM system prompt
          stay_with_user  — True while within timeout
          stay_until      — ISO timestamp; clear addendum after this
          trend           — escalation trend string
          crisis_level    — current level
          rate_limited    — True if this call was throttled
    """
    if _is_rate_limited(user_id):
        _write_log({"event": "rate_limited", "user_id": _input_hash(user_id), "timestamp": _now()})
        return _RATE_LIMITED_RESPONSE, {"rate_limited": True}

    # Auto-detect language when caller doesn't supply it
    resolved_lang = region_language or detect_language(user_input)

    level = detect_crisis_level(user_input, use_llm=use_llm_classification)

    if level != "none":
        trend = get_escalation_trend(user_id)
        log_crisis_event(user_input, level, user_id=user_id)
        save_crisis_memory(level, memory_store, user_id=user_id)
        _maybe_escalate_to_human(user_id, level, trend)
        response = crisis_response(level, user_id, resolved_lang, user_state)
        context  = get_crisis_followup_context(level, user_id)
        return response, context

    return llm_call_fn(user_input), {}


# ─────────────────────────────────────────────────────────────
# QUICK REFERENCE
# ─────────────────────────────────────────────────────────────
#
#   from safety_layer import safe_process, start_dashboard_server
#   import safety_layer
#
#   # Wire in your alert handler (optional)
#   safety_layer.HUMAN_ESCALATION_HANDLER = lambda uid, lvl, trend: ...
#
#   # Language is auto-detected — or pass explicitly to override
#   response, ctx = safe_process(
#       user_input, my_llm,
#       user_id=session.user_id,
#       region_language=None,       # auto-detected from user_input
#       user_state=session.state,   # e.g. "Tamil Nadu" for extra helplines
#   )
#
#   if ctx.get("stay_with_user"):
#       import datetime
#       stay_until = datetime.datetime.fromisoformat(ctx["stay_until"].rstrip("Z"))
#       if datetime.datetime.utcnow() < stay_until:
#           system_prompt += "\n\n" + ctx["system_addendum"]
#
#   # Standalone HTML report (auto-refreshes every 30s in browser)
#   from safety_layer import generate_audit_report
#   generate_audit_report("audit_report.html")
#
#   # Live server (re-reads log on every request)
#   start_dashboard_server(host="127.0.0.1", port=8765)
#   # Non-blocking: threading.Thread(target=start_dashboard_server, daemon=True).start()
#