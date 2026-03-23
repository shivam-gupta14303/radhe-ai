# radhe_engine.py  —  Radhe Intelligence Engine
"""
Fixes in this version:

  Fix 1: ExecutionGovernor  — hard constraints, AI planner only when justified
  Fix 2: Three execution modes — SINGLE / CHAIN / AGENT, no over-engineering
  Fix 3: Decision memory direct injection — entities mutated, not just hinted
  Fix 4: Tool feedback auto-reasoning — weather/search output → message body
  Fix 5: PlanScorer — score + choose best plan, not first plan
  Fix 6: Deep context in planner prompt — causal chain + task continuity
  Fix 7: Failure memory — learn from failures, try alternate channels

NLP integration (preserved from previous version):
  language detection, translation, sentiment, keyword extraction
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable

import sys
sys.path.insert(0, str(Path(__file__).parent))

from command_parser import (
    CommandParser, ParsedAction, ClarificationRequest, SessionState,
    ExecutionPlan, ActionHistory, RecoveryAction,
    normalize_contact, normalize, needs_ai_reasoning,
    AIReasoningLayer, RADHE, ConvState,
    _boost_store, _extract_memory,
)

try:
    from nlp import nlp_manager as _nlp
    _NLP_AVAILABLE = True
except Exception:
    _nlp = None
    _NLP_AVAILABLE = False

logger = logging.getLogger("Radhe.Engine")
logger.setLevel(logging.INFO)

_parser = CommandParser()

# ── file paths ─────────────────────────────────────────────────────────
_DM_FILE      = Path(__file__).parent / "decision_memory.json"
_FAILURE_FILE = Path(__file__).parent / "failure_memory.json"

# ── agent loop limits ──────────────────────────────────────────────────
MAX_AGENT_ITERATIONS = 3
MAX_REPLAN_ATTEMPTS  = 1
GOAL_TIMEOUT_SECS    = 20

# ── simple intents that NEVER need the agent loop ─────────────────────
_SIMPLE_INTENTS = frozenset({
    "get_time", "get_date", "get_battery", "take_screenshot",
    "check_internet", "set_volume", "get_weather", "get_news",
    "conversation_smalltalk", "persona_query", "greeting",
    "goodbye", "thanks", "ask_question", "change_language",
    "change_mode", "user_boundary", "none", "cancelled",
    "ai_fallback", "clarify", "open_app", "close_app",
    "start_stopwatch", "stop_stopwatch", "file_search",
    "recent_files", "summarize_text", "sentiment_check",
    "keyword_extract", "open_website", "open_file",
    "analyze_screen", "describe_screen",
})

# ── intents complex enough to potentially need AI planning ────────────
_COMPLEX_INTENTS = frozenset({
    "send_message", "call_contact", "set_reminder", "set_timer",
    "search_web", "youtube_search", "play_music", "get_directions",
    "run_automation",
})

# ── execution modes ────────────────────────────────────────────────────
MODE_SINGLE = "single"
MODE_CHAIN  = "chain"
MODE_AGENT  = "agent"

# ── intents that should never be executed (no-op) ─────────────────────
_NO_EXEC_INTENTS = frozenset({
    "none", "cancelled", "ai_fallback", "clarify",
    "conversation_smalltalk", "persona_query",
    "greeting", "goodbye", "thanks", "ask_question",
    "change_language", "change_mode", "user_boundary",
})


# ======================================================================
#  ENGINE RESULT
# ======================================================================

@dataclass
class EngineResult:
    action:         dict[str, Any]
    suggestions:    list[str]             = field(default_factory=list)
    emotion:        dict[str, Any]        = field(default_factory=dict)
    tool_choice:    str                   = ""
    memory_used:    list[str]             = field(default_factory=list)
    goal:           str                   = ""
    plan:           dict[str, Any] | None = None
    context_size:   int                   = 0
    silent_skipped: bool                  = False
    language:       str                   = "en"
    sentiment:      dict[str, Any]        = field(default_factory=dict)
    agent_result:   dict[str, Any] | None = None
    execution_mode: str                   = MODE_SINGLE

    def to_dict(self) -> dict:
        return asdict(self)


# ======================================================================
#  AGENT LOOP DATA MODELS
# ======================================================================

class AgentStatus(str, Enum):
    RUNNING      = "running"
    ACHIEVED     = "achieved"
    PARTIAL      = "partial"
    FAILED       = "failed"
    WAITING_USER = "waiting_user"


@dataclass
class StepResult:
    success:  bool
    output:   str            = ""
    error:    str            = ""
    feedback: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AgentStep:
    step_id:      int
    intent:       str
    entities:     dict[str, Any]    = field(default_factory=dict)
    condition:    str               = ""
    check_tool:   str               = ""
    depends_on:   int | None        = None
    can_parallel: bool              = False
    result:       StepResult | None = None
    status:       str               = "pending"

    def to_dict(self) -> dict:
        return {
            "step_id":      self.step_id,
            "intent":       self.intent,
            "entities":     self.entities,
            "condition":    self.condition,
            "check_tool":   self.check_tool,
            "depends_on":   self.depends_on,
            "can_parallel": self.can_parallel,
            "status":       self.status,
            "result":       self.result.to_dict() if self.result else None,
        }


@dataclass
class AgentPlan:
    goal:         str
    steps:        list[AgentStep]  = field(default_factory=list)
    iteration:    int              = 0
    replan_count: int              = 0
    reasoning:    str              = ""
    status:       AgentStatus      = AgentStatus.RUNNING

    def pending_steps(self) -> list[AgentStep]:
        return [s for s in self.steps if s.status == "pending"]

    def ready_steps(self) -> list[AgentStep]:
        done_ids = {s.step_id for s in self.steps if s.status == "done"}
        return [
            s for s in self.pending_steps()
            if s.depends_on is None or s.depends_on in done_ids
        ]

    def failed_steps(self) -> list[AgentStep]:
        return [s for s in self.steps if s.status == "failed"]

    def is_complete(self) -> bool:
        return all(
            s.status in ("done", "skipped", "conditional_skip")
            for s in self.steps
        )

    def step_by_id(self, step_id: int) -> AgentStep | None:
        return next((s for s in self.steps if s.step_id == step_id), None)

    def to_dict(self) -> dict:
        return {
            "goal":         self.goal,
            "iteration":    self.iteration,
            "replan_count": self.replan_count,
            "status":       self.status.value,
            "reasoning":    self.reasoning,
            "steps":        [s.to_dict() for s in self.steps],
        }


@dataclass
class AgentResult:
    goal:         str
    status:       AgentStatus
    plan:         AgentPlan
    final_output: str       = ""
    suggestions:  list[str] = field(default_factory=list)
    iterations:   int       = 0
    elapsed_ms:   int       = 0

    def to_dict(self) -> dict:
        return {
            "goal":         self.goal,
            "status":       self.status.value,
            "final_output": self.final_output,
            "suggestions":  self.suggestions,
            "iterations":   self.iterations,
            "elapsed_ms":   self.elapsed_ms,
            "plan":         self.plan.to_dict(),
        }


# ======================================================================
#  FIX 1 — EXECUTION GOVERNOR
#  Hard gate. AI planner only fires when ALL three conditions pass.
# ======================================================================

class ExecutionGovernor:
    """
    Fix 1 — Hard constraints before any AI call.

    should_use_ai_planner() requires ALL three:
      1. Intent is in _COMPLEX_INTENTS
      2. Has at least one real (non-internal) entity
      3. Complexity score >= 0.6

    decide_mode() routes to SINGLE / CHAIN / AGENT.
    Complexity is scored purely from text — zero LLM calls.
    """

    _CONDITIONAL_RE = re.compile(
        r"\b(agar|if|when|jab|unless|tab hi)\b", re.IGNORECASE
    )
    _MULTI_STEP_RE = re.compile(
        r"\b(aur|and|then|phir|uske baad|after that|also|saath hi)\b",
        re.IGNORECASE,
    )
    _VAGUE_RE = re.compile(
        r"\b(jo|woh|wala|whatever|same as before|last time|jaise kaha)\b",
        re.IGNORECASE,
    )

    @classmethod
    def complexity_score(cls, text: str, entities: dict) -> float:
        score = 0.0
        if cls._CONDITIONAL_RE.search(text): score += 0.35
        if cls._MULTI_STEP_RE.search(text):  score += 0.25
        if cls._VAGUE_RE.search(text):       score += 0.20
        if len(entities) >= 2:               score += 0.10
        if len(text.split()) > 10:           score += 0.10
        return round(min(score, 1.0), 2)

    @classmethod
    def should_use_ai_planner(
        cls, intent: str, entities: dict, context: dict, text: str
    ) -> bool:
        if intent not in _COMPLEX_INTENTS:
            return False
        real_ent = {k: v for k, v in entities.items() if not k.startswith("_")}
        if not real_ent:
            return False
        if cls.complexity_score(text, entities) < 0.6:
            return False
        return True

    @classmethod
    def decide_mode(
        cls, intent: str, text: str, entities: dict, context: dict
    ) -> str:
        if intent in _SIMPLE_INTENTS:
            return MODE_SINGLE

        score = cls.complexity_score(text, entities)

        if score < 0.3:
            return MODE_SINGLE

        if cls._CONDITIONAL_RE.search(text):
            return MODE_AGENT

        if cls._VAGUE_RE.search(text):
            return MODE_AGENT

        if cls._MULTI_STEP_RE.search(text):
            return MODE_CHAIN

        return MODE_SINGLE


# ======================================================================
#  FIX 7 — FAILURE MEMORY
#  Learns from failures: "whatsapp failed → try telegram"
# ======================================================================

class FailureMemory:
    """
    Fix 7 — Persistent failure patterns with channel fallback.

    Stores failure counts per (intent, platform).
    Before execution: checks if primary channel has failed before,
    and redirects to a known alternate.
    """

    _CHANNEL_FALLBACK: dict[str, list[str]] = {
        "whatsapp":  ["telegram", "sms", "email"],
        "telegram":  ["whatsapp", "sms"],
        "sms":       ["whatsapp", "telegram"],
        "email":     ["whatsapp"],
        "gmail":     ["whatsapp", "telegram"],
        "instagram": ["whatsapp"],
        "spotify":   ["jiosaavn", "gaana", "youtube"],
        "jiosaavn":  ["spotify", "gaana", "youtube"],
        "gaana":     ["spotify", "jiosaavn", "youtube"],
    }

    def __init__(self, user_id: str, path: Path = _FAILURE_FILE) -> None:
        self.user_id = user_id
        self._path   = path
        self._data: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        try:
            if self._path.exists():
                self._data = json.loads(self._path.read_text())
        except Exception:
            self._data = {}

    def _save(self) -> None:
        try:
            self._path.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False)
            )
        except Exception:
            pass

    def _user(self) -> dict:
        return self._data.setdefault(self.user_id, {})

    def record_failure(self, intent: str, entities: dict) -> None:
        platform = entities.get("platform", "")
        if not platform:
            return
        key = f"{intent}_{platform}_failed"
        u   = self._user()
        rec = u.setdefault(key, {"count": 0, "last_ts": ""})
        rec["count"]  += 1
        rec["last_ts"] = datetime.now().isoformat(timespec="seconds")
        self._save()
        logger.debug("FailureMemory: %s count=%d", key, rec["count"])

    def get_alternate(self, intent: str, entities: dict) -> str | None:
        platform = entities.get("platform", "")
        if not platform:
            return None
        key = f"{intent}_{platform}_failed"
        u   = self._user()
        if u.get(key, {}).get("count", 0) == 0:
            return None
        for alt in self._CHANNEL_FALLBACK.get(platform, []):
            alt_key = f"{intent}_{alt}_failed"
            if u.get(alt_key, {}).get("count", 0) == 0:
                logger.info(
                    "FailureMemory: %s failed → switching to %s", platform, alt
                )
                return alt
        return None

    def failure_count(self, intent: str, platform: str) -> int:
        return self._user().get(f"{intent}_{platform}_failed", {}).get("count", 0)


# ======================================================================
#  FIX 3 — DECISION MEMORY WITH DIRECT INJECTION
#  Mutates entities directly. No soft hints.
# ======================================================================

class DecisionMemory:
    """
    Fix 3 — Direct entity injection from behavioral patterns.

    OLD: hints.append("User usually uses Spotify")
    NEW: entities["platform"] = "spotify"
         entities["_decision_source"] = "memory_bias"

    The executor always sees the right value without any prompt magic.
    """

    def __init__(self, user_id: str, path: Path = _DM_FILE) -> None:
        self.user_id = user_id
        self._path   = path
        self._data: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        try:
            if self._path.exists():
                self._data = json.loads(self._path.read_text())
        except Exception:
            self._data = {}

    def _save(self) -> None:
        try:
            self._path.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False)
            )
        except Exception:
            pass

    def _user(self) -> dict:
        return self._data.setdefault(self.user_id, {
            "tool_preferences": {},
            "contact_habits":   {},
            "time_habits":      {},
            "outcome_log":      [],
        })

    def record_outcome(self, intent: str, entities: dict, success: bool) -> None:
        u        = self._user()
        platform = entities.get("platform", "")
        if platform and intent in ("send_message", "play_music", "youtube_search"):
            tp = u["tool_preferences"].setdefault(intent, {})
            tp[platform] = tp.get(platform, 0) + (1 if success else -1)

        contacts = entities.get("contact", [])
        if contacts:
            c  = contacts[0] if isinstance(contacts, list) else contacts
            ch = u["contact_habits"].setdefault(c, {"call": 0, "message": 0})
            if intent == "call_contact":   ch["call"]    += 1
            elif intent == "send_message": ch["message"] += 1

        hour   = datetime.now().hour
        period = (
            "morning"   if 6  <= hour < 12 else
            "afternoon" if 12 <= hour < 17 else
            "evening"   if 17 <= hour < 21 else "night"
        )
        th = u["time_habits"].setdefault(intent, {})
        th[period] = th.get(period, 0) + 1

        u["outcome_log"].append({
            "intent": intent, "success": success,
            "ts": datetime.now().isoformat(timespec="seconds"),
        })
        u["outcome_log"] = u["outcome_log"][-100:]
        self._save()

    def preferred_platform(self, intent: str) -> str | None:
        tp = self._user()["tool_preferences"].get(intent, {})
        if not tp:
            return None
        best = max(tp, key=lambda k: tp[k])
        return best if tp[best] > 0 else None

    def preferred_channel(self, contact: str) -> str:
        ch = self._user()["contact_habits"].get(contact, {})
        return "call" if ch.get("call", 0) > ch.get("message", 0) else "message"

    def inject_into_entities(
        self, intent: str, entities: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Fix 3 — Directly mutate entities with learned preferences.
        Only injects when entity is missing — never overrides explicit input.
        """
        entities = dict(entities)

        if intent in ("send_message", "play_music", "youtube_search"):
            if not entities.get("platform"):
                plat = self.preferred_platform(intent)
                if plat:
                    entities["platform"]         = plat
                    entities["_decision_source"] = "memory_bias"
                    logger.debug("DecisionMemory injected platform=%s", plat)

        contacts = entities.get("contact", [])
        if contacts and intent in ("send_message", "call_contact"):
            c = contacts[0] if isinstance(contacts, list) else contacts
            entities["_preferred_channel"] = self.preferred_channel(c)

        return entities

    def get_planner_hints(self, intent: str, entities: dict) -> list[str]:
        """Precise hints for the AI planner prompt (Fix 6)."""
        hints: list[str] = []
        plat = self.preferred_platform(intent)
        if plat:
            hints.append(f"PREFERRED PLATFORM for {intent}: {plat}")
        contacts = entities.get("contact", [])
        if contacts:
            c = contacts[0] if isinstance(contacts, list) else contacts
            hints.append(f"PREFERRED CHANNEL for {c}: {self.preferred_channel(c)}")
        return hints


# ======================================================================
#  FIX 6 — DEEP CONTEXT
#  Causal chains + task continuity injected into planner prompt
# ======================================================================

@dataclass
class CausalLink:
    cause_intent:  str
    effect_intent: str
    reason:        str
    ts: str = field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TaskContinuity:
    task_id:   str
    goal:      str
    remaining: list[str] = field(default_factory=list)
    done:      list[str] = field(default_factory=list)
    ts: str = field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )

    def is_complete(self) -> bool:
        return not self.remaining

    def to_dict(self) -> dict:
        return asdict(self)


class DeepContext:
    """
    Fix 6 — Causal chains + task continuity.

    to_planner_block() returns a formatted string injected directly
    into the AI planner system prompt — not metadata, actual prompt text.
    """

    def __init__(self) -> None:
        self.causal_chain:   list[CausalLink]       = []
        self.active_tasks:   list[TaskContinuity]   = []
        self.goal_awareness: dict[str, AgentStatus] = {}

    def record_cause_effect(self, cause: str, effect: str, reason: str) -> None:
        self.causal_chain.append(CausalLink(cause, effect, reason))
        self.causal_chain = self.causal_chain[-20:]

    def register_task(self, goal: str, steps: list[str]) -> str:
        task_id = f"task_{int(time.time())}"
        self.active_tasks.append(
            TaskContinuity(task_id=task_id, goal=goal, remaining=list(steps))
        )
        return task_id

    def complete_step(self, goal: str, step: str) -> None:
        for t in self.active_tasks:
            if t.goal == goal and step in t.remaining:
                t.remaining.remove(step)
                t.done.append(step)

    def get_incomplete_task(self, goal: str) -> TaskContinuity | None:
        return next(
            (t for t in self.active_tasks
             if t.goal == goal and not t.is_complete()),
            None,
        )

    def update_goal_status(self, goal: str, status: AgentStatus) -> None:
        self.goal_awareness[goal] = status

    def to_context_dict(self) -> dict:
        return {
            "causal_chain":   [c.to_dict() for c in self.causal_chain[-5:]],
            "active_tasks":   [t.to_dict() for t in self.active_tasks
                               if not t.is_complete()],
            "goal_awareness": {k: v.value for k, v in self.goal_awareness.items()},
        }

    def to_planner_block(self) -> str:
        """
        Fix 6 — Formatted block injected into AI planner system prompt.
        """
        lines: list[str] = ["IMPORTANT CONTEXT (use to shape your plan):"]

        if self.causal_chain:
            lines.append("User previously did:")
            for link in self.causal_chain[-3:]:
                lines.append(
                    f"  - {link.cause_intent} → {link.effect_intent} ({link.reason})"
                )
            lines.append("Prefer continuing these patterns.")

        incomplete = [t for t in self.active_tasks if not t.is_complete()]
        if incomplete:
            lines.append("Incomplete tasks this session:")
            for t in incomplete[:2]:
                lines.append(
                    f"  - Goal: '{t.goal}' | Done: {t.done} | Remaining: {t.remaining}"
                )
            lines.append("Prioritise completing these first.")

        active = [g for g, s in self.goal_awareness.items()
                  if s == AgentStatus.RUNNING]
        if active:
            lines.append(f"Active goals: {active}")

        return "\n".join(lines) if len(lines) > 1 else ""


# ======================================================================
#  CONDITIONAL EVALUATOR
# ======================================================================

_CONDITION_CHECK_MAP: dict[str, str] = {
    "online":    "check_online_status",
    "connected": "check_internet",
    "charging":  "get_battery",
    "battery":   "get_battery",
    "available": "check_online_status",
    "busy":      "check_online_status",
    "internet":  "check_internet",
}

_CONDITION_SIGNAL_RE = re.compile(
    r"\b(agar|if|jab|when|unless|tab hi|tabhi|provided)\b", re.IGNORECASE
)
_CONDITION_EXTRACT_RE = re.compile(
    r"\b(?:agar|if|when|jab)\s+"
    r"(?P<subject>[\w\s]{1,25}?)\s+"
    r"(?P<predicate>online|offline|busy|available|charging|connected|disconnected)\b",
    re.IGNORECASE,
)


class ConditionalEvaluator:
    @staticmethod
    def has_condition(text: str) -> bool:
        return bool(_CONDITION_SIGNAL_RE.search(text))

    @staticmethod
    def extract_condition(text: str) -> tuple[str, str]:
        m = _CONDITION_EXTRACT_RE.search(text)
        if not m:
            return "unknown condition", ""
        subject   = m.group("subject").strip()
        predicate = m.group("predicate").strip().lower()
        tool      = next(
            (v for k, v in _CONDITION_CHECK_MAP.items() if k in predicate), ""
        )
        return f"{subject} is {predicate}", tool

    @staticmethod
    def evaluate(condition: str, check_tool: str, bridge: "ExecutorBridge") -> bool:
        if not check_tool:
            return True
        result = bridge.execute({"intent": check_tool, "entities": {}})
        if not result.success:
            return True
        out  = result.output.lower()
        cond = condition.lower()
        if "online"    in cond: return "online"    in out
        if "connected" in cond: return "connected" in out or "yes" in out
        if "busy"      in cond: return "busy"      in out
        if "charging"  in cond: return "charging"  in out
        return True


# ======================================================================
#  FIX 4 — TOOL FEEDBACK WITH AUTO-REASONING
# ======================================================================

class ToolFeedbackLoop:
    """
    Fix 4 — Parse tool output into structured feedback,
    then auto-generate message content for downstream send_message steps.

    weather → "Mausam: 28°C, Sunny"  injected as message body
    battery → "Battery 82% hai."      injected as message body
    search  → "Search result: ..."    injected as message body
    """

    _NUMBER_RE = re.compile(r"(\d+)")

    @classmethod
    def extract(cls, intent: str, output: str, success: bool) -> dict[str, Any]:
        out = output.lower()
        if intent == "get_battery":
            nums = cls._NUMBER_RE.findall(out)
            return {"battery_level": int(nums[0]) if nums else None,
                    "charging": "charging" in out, "_summary": output.strip()}
        if intent == "get_weather":
            nums = cls._NUMBER_RE.findall(out)
            cond = ("rainy" if "rain" in out else "sunny" if "sunny" in out
                    else "cloudy" if "cloud" in out else "clear")
            return {"temperature": int(nums[0]) if nums else None,
                    "condition": cond, "_summary": output.strip()}
        if intent in ("search_web", "youtube_search"):
            return {"top_result": output[:200], "_summary": output[:200]}
        if intent == "check_internet":
            return {"connected": "connected" in out or "yes" in out,
                    "_summary": output.strip()}
        if intent == "get_time":
            return {"current_time": output.strip(), "_summary": output.strip()}
        return {"_summary": output[:200]}

    @classmethod
    def inject_smart(
        cls, feedback: dict[str, Any], next_step: AgentStep, source_intent: str
    ) -> None:
        """
        Fix 4 — Auto-fill message body from previous tool output.
        Only injects if next step is send_message with no existing message.
        """
        if next_step.intent != "send_message":
            return
        if next_step.entities.get("message"):
            return

        summary = feedback.get("_summary", "")
        if not summary:
            return

        if source_intent == "get_weather":
            temp = feedback.get("temperature")
            cond = feedback.get("condition", "")
            msg  = (f"Mausam: {temp}°C, {cond}." if temp
                    else f"Mausam update: {summary}")
        elif source_intent == "get_battery":
            lvl = feedback.get("battery_level")
            msg = (f"Battery {lvl}% hai." if lvl is not None
                   else f"Battery: {summary}")
        elif source_intent in ("search_web", "youtube_search"):
            msg = f"Search result: {summary[:120]}"
        elif source_intent == "get_time":
            msg = f"Time: {summary}"
        else:
            msg = summary[:150]

        next_step.entities["message"]       = msg
        next_step.entities["_auto_message"] = True
        logger.debug("ToolFeedbackLoop auto-message: %r", msg)


# ======================================================================
#  FIX 5 — PLAN SCORER
# ======================================================================

class PlanScorer:
    """
    Fix 5 — Score plans numerically. Choose best, not first.

    Score = 10 base
      - 0.5 per step      (shorter is better)
      + 3   if has parallel steps
      - 5   per no-exec intent step
      + 2   if first step is a real executable
      - 2   per conditional step (uncertainty cost)
    """

    @classmethod
    def score(cls, plan: AgentPlan) -> float:
        s = 10.0
        s -= len(plan.steps) * 0.5
        if any(step.can_parallel for step in plan.steps):
            s += 3.0
        for step in plan.steps:
            if step.intent in _NO_EXEC_INTENTS: s -= 5.0
            if step.condition:                  s -= 2.0
        if plan.steps and plan.steps[0].intent not in _NO_EXEC_INTENTS:
            s += 2.0
        return round(s, 2)

    @classmethod
    def choose_best(cls, plans: list[AgentPlan]) -> AgentPlan:
        if not plans:
            raise ValueError("No plans to score")
        best = max(plans, key=cls.score)
        logger.debug("PlanScorer: best=%.2f from %d candidates", cls.score(best), len(plans))
        return best


# ======================================================================
#  AI PLANNER  (Fix 6: deep context block in system prompt)
# ======================================================================

_PLANNER_SYSTEM_TEMPLATE = """\
You are Radhe's execution planner. Produce a precise JSON execution plan.

{deep_context_block}

Behavioral hints (apply directly to entity defaults):
{hints_block}

Return ONLY this JSON structure:
{{
  "goal": "short goal",
  "reasoning": "why these steps",
  "steps": [
    {{
      "step_id": 1,
      "intent": "<known intent>",
      "entities": {{}},
      "condition": "",
      "check_tool": "",
      "depends_on": null,
      "can_parallel": false
    }}
  ]
}}

Known intents: send_message, call_contact, set_reminder, set_timer, open_app,
close_app, search_web, youtube_search, play_music, get_weather, get_battery,
take_screenshot, get_time, get_date, check_internet, check_online_status

Rules:
- Max 5 steps. Prefer fewer.
- Conditional steps: set condition + check_tool.
- Parallel-safe steps: can_parallel=true.
- Dependent steps: set depends_on=<step_id>.
- Return ONLY valid JSON. No markdown.
"""


class AIPlanner:
    """Fix 6: Deep context injected into planner prompt as plain text."""

    _TIMEOUT = 8

    @classmethod
    def plan(
        cls,
        goal:           str,
        context:        dict,
        decision_hints: list[str],
        deep_ctx:       DeepContext,
        fallback_plan:  AgentPlan | None = None,
    ) -> AgentPlan:
        deep_block = deep_ctx.to_planner_block()
        hints_text = "\n".join(f"  {h}" for h in decision_hints) or "  None"

        system = _PLANNER_SYSTEM_TEMPLATE.format(
            deep_context_block = deep_block or "No prior context.",
            hints_block        = hints_text,
        )
        user_msg = (
            f"Goal: {goal}\n"
            f"Context: {json.dumps(context, ensure_ascii=False, default=str)}"
        )

        for call_fn in (cls._call_anthropic, cls._call_groq):
            try:
                raw = call_fn(system, user_msg)
                if raw:
                    return cls._parse_response(goal, raw, fallback_plan)
            except Exception as e:
                logger.debug("AIPlanner backend failed: %s", e)

        logger.warning("AIPlanner: all backends failed, using fallback")
        return fallback_plan or AgentPlan(goal=goal)

    @classmethod
    def _call_anthropic(cls, system: str, user_msg: str) -> str | None:
        import urllib.request
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            return None
        payload = json.dumps({
            "model": "claude-sonnet-4-5", "max_tokens": 800,
            "system": system,
            "messages": [{"role": "user", "content": user_msg}],
        }).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data    = payload,
            headers = {"Content-Type": "application/json",
                       "anthropic-version": "2023-06-01",
                       "x-api-key": api_key},
            method  = "POST",
        )
        with urllib.request.urlopen(req, timeout=cls._TIMEOUT) as resp:
            raw = json.loads(resp.read())
        return "".join(
            b.get("text", "") for b in raw.get("content", [])
            if b.get("type") == "text"
        ) or None

    @classmethod
    def _call_groq(cls, system: str, user_msg: str) -> str | None:
        import urllib.request
        api_key = os.environ.get("GROQ_API_KEY", "")
        if not api_key:
            return None
        payload = json.dumps({
            "model": "llama3-8b-8192", "temperature": 0.1, "max_tokens": 600,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user_msg}],
        }).encode()
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data    = payload,
            headers = {"Content-Type": "application/json",
                       "Authorization": f"Bearer {api_key}"},
            method  = "POST",
        )
        with urllib.request.urlopen(req, timeout=cls._TIMEOUT) as resp:
            raw = json.loads(resp.read())
        return raw["choices"][0]["message"]["content"] or None

    @classmethod
    def _parse_response(
        cls, goal: str, raw: str, fallback: AgentPlan | None
    ) -> AgentPlan:
        try:
            clean = re.sub(r"```(?:json)?|```", "", raw).strip()
            data  = json.loads(clean)
            steps = [
                AgentStep(
                    step_id      = s.get("step_id", i + 1),
                    intent       = s.get("intent", "ask_question"),
                    entities     = s.get("entities", {}),
                    condition    = s.get("condition", ""),
                    check_tool   = s.get("check_tool", ""),
                    depends_on   = s.get("depends_on"),
                    can_parallel = s.get("can_parallel", False),
                )
                for i, s in enumerate(data.get("steps", []))
            ]
            return AgentPlan(
                goal=data.get("goal", goal), steps=steps,
                reasoning=data.get("reasoning", ""),
            )
        except Exception as e:
            logger.warning("AIPlanner parse error: %s", e)
            return fallback or AgentPlan(goal=goal)


# ======================================================================
#  PLAN EXECUTOR  (Fix 4 + Fix 7)
# ======================================================================

class PlanExecutor:
    """
    Iterates steps:
    - Conditional evaluation
    - Tool feedback → auto-message injection (Fix 4)
    - Failure memory → alternate channel redirect (Fix 7)
    - Retry on failure
    """

    def __init__(
        self,
        bridge:       "ExecutorBridge",
        deep_ctx:     DeepContext,
        decision_mem: DecisionMemory,
        failure_mem:  FailureMemory,
        max_retries:  int = 1,
    ) -> None:
        self._bridge       = bridge
        self._deep_ctx     = deep_ctx
        self._decision_mem = decision_mem
        self._failure_mem  = failure_mem
        self._max_retries  = max_retries

    def execute_plan(self, plan: AgentPlan) -> AgentPlan:
        accumulated: dict[str, Any] = {}
        last_source: str            = ""

        while plan.ready_steps() and not plan.is_complete():
            for step in plan.ready_steps():

                # Fix 4: inject smart feedback before executing
                if accumulated:
                    ToolFeedbackLoop.inject_smart(accumulated, step, last_source)

                self._execute_step(step)

                if step.result:
                    fb = ToolFeedbackLoop.extract(
                        step.intent, step.result.output, step.result.success
                    )
                    accumulated.update(fb)
                    last_source = step.intent

                    for future in plan.pending_steps():
                        existing = future.entities.get("_tool_feedback", {})
                        existing.update(fb)
                        future.entities["_tool_feedback"] = existing

                    if step.status == "done":
                        prev = next(
                            (s.intent for s in reversed(plan.steps)
                             if s.status == "done" and s.step_id != step.step_id),
                            None,
                        )
                        if prev:
                            self._deep_ctx.record_cause_effect(
                                prev, step.intent,
                                f"step {step.step_id} followed step {step.depends_on}",
                            )

                    self._decision_mem.record_outcome(
                        step.intent, step.entities, step.result.success
                    )
                    if not step.result.success:
                        self._failure_mem.record_failure(step.intent, step.entities)

        return plan

    def _execute_step(self, step: AgentStep) -> None:
        if step.condition:
            met = ConditionalEvaluator.evaluate(
                step.condition, step.check_tool, self._bridge
            )
            if not met:
                step.status = "conditional_skip"
                step.result = StepResult(
                    success=True,
                    output=f"Skipped: '{step.condition}' not met",
                )
                return

        # Fix 7: check failure memory before executing
        alt = self._failure_mem.get_alternate(step.intent, step.entities)
        if alt:
            step.entities = dict(step.entities)
            step.entities["platform"]          = alt
            step.entities["_failure_redirect"] = True
            logger.info("FailureMemory redirect: → %s", alt)

        for attempt in range(1 + self._max_retries):
            res = self._bridge.execute({
                "intent":   step.intent,
                "entities": step.entities,
            })
            step.result = StepResult(
                success=res.success, output=res.output, error=res.error
            )
            if res.success:
                step.status = "done"
                return
            logger.warning(
                "Step %d (%s) attempt %d failed: %s",
                step.step_id, step.intent, attempt + 1, res.error,
            )
        step.status = "failed"


# ======================================================================
#  AGENT LOOP  (Fix 1 + Fix 5)
# ======================================================================

class AgentLoop:
    """
    Fix 1: Governed — only runs when ExecutionGovernor approves.
    Fix 5: Uses PlanScorer to choose best plan when replanning.
    """

    def __init__(
        self,
        bridge:       "ExecutorBridge",
        decision_mem: DecisionMemory,
        failure_mem:  FailureMemory,
        deep_ctx:     DeepContext,
    ) -> None:
        self._bridge       = bridge
        self._decision_mem = decision_mem
        self._failure_mem  = failure_mem
        self._deep_ctx     = deep_ctx
        self._executor     = PlanExecutor(
            bridge, deep_ctx, decision_mem, failure_mem
        )

    def run(
        self, goal: str, context: dict, intent: str, entities: dict
    ) -> AgentResult:
        start  = time.monotonic()
        plan   = self._build_initial_plan(goal, context, intent, entities)
        result = AgentResult(goal=goal, status=AgentStatus.RUNNING, plan=plan)

        self._deep_ctx.register_task(goal, [s.intent for s in plan.steps])

        for iteration in range(MAX_AGENT_ITERATIONS):
            if time.monotonic() - start > GOAL_TIMEOUT_SECS:
                plan.status = AgentStatus.PARTIAL
                break

            plan.iteration = iteration + 1
            plan = self._executor.execute_plan(plan)
            done, status = self._evaluate(plan)

            if done:
                plan.status = status
                break

            if plan.failed_steps() and plan.replan_count < MAX_REPLAN_ATTEMPTS:
                plan = self._replan(plan, context)
            elif not plan.ready_steps():
                plan.status = (
                    AgentStatus.ACHIEVED if not plan.failed_steps()
                    else AgentStatus.PARTIAL
                )
                break

        self._deep_ctx.update_goal_status(goal, plan.status)
        for s in plan.steps:
            if s.status == "done":
                self._deep_ctx.complete_step(goal, s.intent)

        elapsed_ms = round((time.monotonic() - start) * 1000)
        result.status       = plan.status
        result.plan         = plan
        result.final_output = self._summarise(plan)
        result.iterations   = plan.iteration
        result.elapsed_ms   = elapsed_ms
        return result

    def _evaluate(self, plan: AgentPlan) -> tuple[bool, AgentStatus]:
        if plan.is_complete():
            return True, (
                AgentStatus.PARTIAL if plan.failed_steps()
                else AgentStatus.ACHIEVED
            )
        if not plan.ready_steps() and not plan.pending_steps():
            return True, AgentStatus.FAILED
        return False, AgentStatus.RUNNING

    def _replan(self, plan: AgentPlan, context: dict) -> AgentPlan:
        failed  = [s.intent for s in plan.failed_steps()]
        hints   = self._decision_mem.get_planner_hints(
            failed[0] if failed else "", {}
        )
        # Fix 5: generate two candidates and score them
        ai_plan = AIPlanner.plan(
            goal           = f"{plan.goal} — retrying: {failed}",
            context        = context,
            decision_hints = hints,
            deep_ctx       = self._deep_ctx,
            fallback_plan  = plan,
        )
        reset_plan = AgentPlan(goal=plan.goal, steps=list(plan.steps))
        for s in reset_plan.steps:
            if s.status == "failed":
                s.status = "pending"
                s.result = None
        best             = PlanScorer.choose_best([ai_plan, reset_plan])
        best.replan_count = plan.replan_count + 1
        best.iteration    = plan.iteration
        return best

    def _build_initial_plan(
        self, goal: str, context: dict, intent: str, entities: dict
    ) -> AgentPlan:
        hints = self._decision_mem.get_planner_hints(intent, entities)

        try:
            cp = _parser.plan(goal, context)
            fallback = AgentPlan(
                goal  = cp.goal,
                steps = [
                    AgentStep(
                        step_id      = s.step_id,
                        intent       = s.action.get("intent", "ask_question"),
                        entities     = s.action.get("entities", {}),
                        depends_on   = s.depends_on,
                        can_parallel = s.can_parallel,
                    )
                    for s in cp.steps
                ],
            )
        except Exception:
            fallback = AgentPlan(
                goal  = goal,
                steps = [AgentStep(step_id=1, intent=intent, entities=entities)],
            )

        # Fix 1: Governor gates AI planner
        if ExecutionGovernor.should_use_ai_planner(intent, entities, context, goal):
            ai_plan = AIPlanner.plan(
                goal=goal, context=context,
                decision_hints=hints, deep_ctx=self._deep_ctx,
                fallback_plan=fallback,
            )
            # Fix 5: score both candidates
            return PlanScorer.choose_best([ai_plan, fallback])

        return fallback

    def _summarise(self, plan: AgentPlan) -> str:
        parts   = [s.result.output for s in plan.steps
                   if s.status == "done" and s.result and s.result.output]
        failed  = [s.intent for s in plan.steps if s.status == "failed"]
        skipped = [s.intent for s in plan.steps if "skip" in s.status]
        out     = "\n".join(parts) if parts else "Done."
        if failed:  out += f"\n\nNahi hua: {', '.join(failed)}."
        if skipped: out += f"\nSkipped: {', '.join(skipped)}."
        return out.strip()


# ======================================================================
#  MODULE 1 — MEMORY RESOLVER
# ======================================================================

class _MemoryBackend:
    def add(self, user_id: str, key: str, value: Any) -> None: ...
    def get(self, user_id: str, key: str) -> Any: ...
    def search_contacts(self, user_id: str, partial: str) -> list[dict]: ...
    def get_preferences(self, user_id: str) -> dict: ...
    def record_usage(self, user_id: str, intent: str, contact: str | None) -> None: ...
    def top_contacts(self, user_id: str, n: int = 3) -> list[str]: ...


class _LocalMemoryBackend(_MemoryBackend):
    _FILE = Path(__file__).parent / "radhe_memory.json"

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        try:
            if self._FILE.exists():
                self._data = json.loads(self._FILE.read_text())
        except Exception:
            self._data = {}

    def _save(self) -> None:
        try:
            self._FILE.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False)
            )
        except Exception:
            pass

    def _user(self, user_id: str) -> dict:
        return self._data.setdefault(user_id, {
            "contacts": {}, "preferences": {}, "intent_counts": {}, "kv": {}
        })

    def add(self, user_id: str, key: str, value: Any) -> None:
        self._user(user_id)["kv"][key] = value
        self._save()

    def get(self, user_id: str, key: str) -> Any:
        return self._user(user_id)["kv"].get(key)

    def search_contacts(self, user_id: str, partial: str) -> list[dict]:
        contacts = self._user(user_id)["contacts"]
        p = partial.lower()
        return [
            {"name": n, "count": i.get("count", 0),
             "platform": i.get("platform", "whatsapp")}
            for n, i in contacts.items() if p in n.lower()
        ]

    def get_preferences(self, user_id: str) -> dict:
        return dict(self._user(user_id)["preferences"])

    def record_usage(self, user_id: str, intent: str, contact: str | None) -> None:
        u = self._user(user_id)
        u["intent_counts"][intent] = u["intent_counts"].get(intent, 0) + 1
        if contact:
            c = u["contacts"]
            if contact not in c:
                c[contact] = {"count": 0, "platform": "whatsapp", "last_seen": ""}
            c[contact]["count"]    += 1
            c[contact]["last_seen"] = datetime.now().isoformat(timespec="seconds")
        self._save()

    def top_contacts(self, user_id: str, n: int = 3) -> list[str]:
        contacts = self._user(user_id)["contacts"]
        ranked   = sorted(
            contacts.items(), key=lambda x: x[1].get("count", 0), reverse=True
        )
        return [name for name, _ in ranked[:n]]

    def set_preference(self, user_id: str, key: str, value: Any) -> None:
        self._user(user_id)["preferences"][key] = value
        self._save()


try:
    import mem0
    class _Mem0Backend(_MemoryBackend):
        def __init__(self) -> None:
            self._client = mem0.MemoryClient(
                api_key=os.environ.get("MEM0_API_KEY", "")
            )
            self._local = _LocalMemoryBackend()

        def add(self, user_id: str, key: str, value: Any) -> None:
            self._client.add(
                [{"role": "user", "content": f"{key}: {json.dumps(value)}"}],
                user_id=user_id,
            )

        def get(self, user_id: str, key: str) -> Any:
            r = self._client.search(key, user_id=user_id, limit=1)
            return r[0].get("memory") if r else None

        def search_contacts(self, user_id: str, partial: str) -> list[dict]:
            return self._local.search_contacts(user_id, partial)

        def get_preferences(self, user_id: str) -> dict:
            return self._local.get_preferences(user_id)

        def record_usage(self, user_id: str, intent: str, contact: str | None) -> None:
            self._local.record_usage(user_id, intent, contact)
            self._client.add(
                [{"role": "user",
                  "content": f"Used {intent}" + (f" with {contact}" if contact else "")}],
                user_id=user_id,
            )

        def top_contacts(self, user_id: str, n: int = 3) -> list[str]:
            return self._local.top_contacts(user_id, n)

    _MEM_BACKEND: _MemoryBackend = _Mem0Backend()
    logger.info("Using mem0 memory backend")
except Exception:
    _MEM_BACKEND = _LocalMemoryBackend()
    logger.info("Using local JSON memory backend")


class MemoryResolver:
    def __init__(self, user_id: str, backend: _MemoryBackend = _MEM_BACKEND) -> None:
        self.user_id = user_id
        self._db     = backend

    def resolve_contact(self, raw_names: list[str]) -> list[str]:
        resolved = []
        for name in raw_names:
            matches = self._db.search_contacts(self.user_id, name)
            if matches:
                best = sorted(matches, key=lambda x: x["count"], reverse=True)[0]
                resolved.append(best["name"])
            else:
                resolved.append(name)
        return resolved

    def get_default_platform(self) -> str:
        return self._db.get_preferences(self.user_id).get("default_platform", "whatsapp")

    def suggest_contacts(self, partial: str = "") -> list[str]:
        if partial:
            return [m["name"] for m in
                    self._db.search_contacts(self.user_id, partial)[:3]]
        return self._db.top_contacts(self.user_id)

    def enrich_action(self, action: dict) -> tuple[dict, list[str]]:
        notes  = []
        ent    = dict(action.get("entities", {}))
        intent = action.get("intent", "")

        if intent in ("send_message", "call_contact"):
            contacts = ent.get("contact", [])
            if isinstance(contacts, str):
                contacts = [contacts]
            if contacts:
                resolved = self.resolve_contact(contacts)
                if resolved != contacts:
                    notes.append(f"contact resolved: {contacts} → {resolved}")
                ent["contact"] = resolved
            else:
                top = self.suggest_contacts()
                if top:
                    ent["_contact_suggestions"] = top
                    notes.append(f"suggestions: {top}")
            if not ent.get("platform"):
                ent["platform"] = self.get_default_platform()
                notes.append(f"platform defaulted: {ent['platform']}")

        action = dict(action)
        action["entities"] = ent
        return action, notes

    def record(self, action: dict) -> None:
        intent   = action.get("intent", "")
        contacts = action.get("entities", {}).get("contact", [])
        contact  = contacts[0] if isinstance(contacts, list) and contacts else None
        self._db.record_usage(self.user_id, intent, contact)

    def save_preference(self, key: str, value: Any) -> None:
        if hasattr(self._db, "set_preference"):
            self._db.set_preference(self.user_id, key, value)


# ======================================================================
#  MODULE 2 — EXECUTOR BRIDGE
# ======================================================================

ExecutorFn = Callable[[dict[str, Any]], "ExecutorResult"]


@dataclass
class ExecutorResult:
    success:  bool
    output:   str            = ""
    error:    str            = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class ExecutorBridge:
    def __init__(self) -> None:
        self._map: dict[str, ExecutorFn] = {}

    def register(self, intent: str, fn: ExecutorFn) -> None:
        self._map[intent] = fn

    def execute(self, action: dict) -> ExecutorResult:
        intent = action.get("intent", "")
        fn     = self._map.get(intent)
        if fn is None:
            return ExecutorResult(
                success=False, error=f"no executor for '{intent}'",
                metadata={"intent": intent},
            )
        try:
            result = fn(action.get("entities", {}))
            if isinstance(result, dict):
                return ExecutorResult(
                    success  = result.get("success", True),
                    output   = result.get("output", ""),
                    error    = result.get("error", ""),
                    metadata = result,
                )
            return ExecutorResult(success=True, output=str(result))
        except Exception as exc:
            logger.exception("Executor error intent=%s", intent)
            return ExecutorResult(success=False, error=str(exc))

    def registered(self) -> list[str]:
        return list(self._map.keys())


def _mock_send_message(e: dict) -> dict:
    return {"success": True,
            "output": f"[MOCK] Sent to {e.get('contact')} on {e.get('platform','wa')}: {e.get('message','')}"}
def _mock_call(e: dict) -> dict:
    return {"success": True, "output": f"[MOCK] Calling {e.get('contact')}..."}
def _mock_open_app(e: dict) -> dict:
    return {"success": True, "output": f"[MOCK] Opening {e.get('application')}"}
def _mock_timer(e: dict) -> dict:
    return {"success": True, "output": f"[MOCK] Timer: {e.get('duration')}"}
def _mock_reminder(e: dict) -> dict:
    return {"success": True,
            "output": f"[MOCK] Reminder: {e.get('reminder_text')} at {e.get('time')}"}
def _mock_screenshot(e: dict) -> dict:
    return {"success": True, "output": "[MOCK] Screenshot saved"}
def _mock_battery(e: dict) -> dict:
    return {"success": True, "output": "[MOCK] Battery: 82% (not charging)"}
def _mock_weather(e: dict) -> dict:
    return {"success": True,
            "output": f"[MOCK] Weather in {e.get('location','here')}: 28 degrees, Sunny"}
def _mock_play_music(e: dict) -> dict:
    return {"success": True, "output": f"[MOCK] Playing: {e.get('query')}"}
def _mock_youtube(e: dict) -> dict:
    return {"success": True, "output": f"[MOCK] YouTube: {e.get('query')}"}
def _mock_search_web(e: dict) -> dict:
    return {"success": True, "output": "[MOCK] Search result: top restaurants near you"}
def _mock_check_internet(e: dict) -> dict:
    return {"success": True, "output": "[MOCK] Internet: connected"}
def _mock_check_online(e: dict) -> dict:
    return {"success": True, "output": "[MOCK] Status: online"}


def build_default_bridge() -> ExecutorBridge:
    b = ExecutorBridge()
    b.register("send_message",        _mock_send_message)
    b.register("call_contact",        _mock_call)
    b.register("open_app",            _mock_open_app)
    b.register("set_timer",           _mock_timer)
    b.register("set_reminder",        _mock_reminder)
    b.register("take_screenshot",     _mock_screenshot)
    b.register("get_battery",         _mock_battery)
    b.register("get_weather",         _mock_weather)
    b.register("play_music",          _mock_play_music)
    b.register("youtube_search",      _mock_youtube)
    b.register("search_web",          _mock_search_web)
    b.register("check_internet",      _mock_check_internet)
    b.register("check_online_status", _mock_check_online)
    return b


# ======================================================================
#  MODULE 3 — GROQ AI LAYER
# ======================================================================

class GroqAILayer:
    _URL     = "https://api.groq.com/openai/v1/chat/completions"
    _MODEL   = "llama3-8b-8192"
    _TIMEOUT = 6
    _SYSTEM  = ("You are Radhe's intent parser. Return a JSON array of ParsedAction "
                "objects: intent, entities, confidence (0-1), routing. No markdown.")

    @classmethod
    def reason(
        cls, text: str, context: dict | None = None, fallback: dict | None = None,
    ) -> dict[str, Any]:
        api_key = os.environ.get("GROQ_API_KEY", "")
        if not api_key:
            return {"handled": False, "actions": []}
        try:
            import urllib.request
            payload = json.dumps({
                "model": cls._MODEL, "temperature": 0.1, "max_tokens": 400,
                "messages": [
                    {"role": "system", "content": cls._SYSTEM},
                    {"role": "user",
                     "content": f"Command: {text!r}\nContext: {json.dumps(context or {})}"},
                ],
            }).encode()
            req = urllib.request.Request(
                cls._URL, data=payload,
                headers={"Content-Type": "application/json",
                         "Authorization": f"Bearer {api_key}"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=cls._TIMEOUT) as resp:
                raw = json.loads(resp.read())
            text_out = raw["choices"][0]["message"]["content"]
            clean    = re.sub(r"```(?:json)?|```", "", text_out).strip()
            actions  = json.loads(clean)
            if not isinstance(actions, list):
                actions = [actions]
            for a in actions:
                a.pop("reasoning", None)
            return {"handled": True, "actions": actions}
        except Exception as exc:
            logger.debug("GroqAILayer: %s", exc)
            return {"handled": False, "actions": []}


# ======================================================================
#  MODULE 4 — TOOL SELECTOR
# ======================================================================

_TOOL_PREFS: dict[str, list[str]] = {
    "play_music":     ["spotify", "jiosaavn", "gaana", "youtube"],
    "youtube_search": ["youtube"],
    "search_web":     ["google", "bing"],
    "get_weather":    ["openweathermap"],
    "get_directions": ["google_maps", "ola_maps"],
}
_TOOL_HINTS: dict[str, str] = {
    "youtube": "youtube", "spotify": "spotify", "jiosaavn": "jiosaavn",
    "gaana": "gaana", "wynk": "wynk", "google": "google",
    "maps": "google_maps", "ola": "ola_maps",
}


class ToolSelector:
    def __init__(self, memory: MemoryResolver) -> None:
        self._mem = memory

    def select(self, action: dict) -> str:
        intent   = action.get("intent", "")
        query    = (action.get("entities", {}).get("query") or "").lower()
        platform = (action.get("entities", {}).get("platform") or "").lower()
        if platform and platform in ("spotify", "youtube", "gaana", "jiosaavn", "wynk"):
            return platform
        for hint, tool in _TOOL_HINTS.items():
            if hint in query:
                return tool
        return _TOOL_PREFS.get(intent, ["default"])[0]


# ======================================================================
#  MODULE 5 — CONTEXT WINDOW
# ======================================================================

class ContextWindow:
    def __init__(self, window_size: int = 5) -> None:
        self._window: list[dict] = []
        self._size   = window_size
        self._freq:   dict[str, int] = defaultdict(int)

    def push(self, action: dict) -> None:
        intent = action.get("intent", "")
        if intent in ("none", "ai_fallback", "clarify"):
            return
        self._window.append(action)
        if len(self._window) > self._size:
            self._window.pop(0)
        self._freq[intent] += 1

    def to_context(self) -> dict:
        ctx: dict[str, Any] = {}
        ctx["recent_actions"] = [
            {"intent": a.get("intent"),
             "contact": a.get("entities", {}).get("contact")}
            for a in self._window
        ]
        for a in reversed(self._window):
            for k, v in _extract_memory(a).items():
                ctx.setdefault(k, v)
        ctx["intent_frequency"] = dict(self._freq)
        return ctx


# ======================================================================
#  MODULE 6 — EMOTION DETECTOR
# ======================================================================

_EMOTION_COMPILED = [
    (re.compile(p, re.IGNORECASE), e, i) for p, e, i in [
        (r"\byaar\b.*\bjaldi\b|\bjaldi\b.*\byaar\b",    "frustrated_urgency", 0.8),
        (r"\bplease\b.*\bjaldi\b|\bjaldi\b.*\bplease\b","polite_urgency",     0.6),
        (r"\b(kab tak|kitna wait|kab hoga)\b",           "impatient",          0.7),
        (r"\b(shukriya|thank you|thanks|bahut acha)\b",  "grateful",           0.9),
        (r"\b(ugh|argh|frustrating|irritating)\b",       "frustrated",         0.8),
        (r"\b(amazing|awesome|great|bahut badhiya)\b",   "happy",              0.9),
        (r"\b(sad|dukh|bura lag|upset|depressed)\b",     "sad",                0.7),
        (r"!!+",                                          "high_excitement",    0.7),
        (r"\b(abhi|turant|immediately|right now)\b",     "urgent",             0.9),
    ]
]


@dataclass
class EmotionResult:
    dominant:       str       = "neutral"
    intensity:      float     = 0.0
    all_detected:   list[str] = field(default_factory=list)
    sentiment:      str       = "NEUTRAL"
    sentiment_conf: float     = 0.5

    def to_dict(self) -> dict:
        return asdict(self)


class EmotionToneDetector:
    @staticmethod
    def detect(text: str) -> EmotionResult:
        found = [(e, i) for p, e, i in _EMOTION_COMPILED if p.search(text)]
        if not found:
            return EmotionResult()
        found.sort(key=lambda x: x[1], reverse=True)
        d, ti = found[0]
        return EmotionResult(dominant=d, intensity=ti,
                             all_detected=[e for e, _ in found])


# ======================================================================
#  MODULE 7 — HINDI DEEP PARSER
# ======================================================================

_VIBHAKTI = {
    "ko": "dative", "ne": "ergative", "se": "ablative",
    "mein": "locative", "par": "locative", "ke": "genitive",
    "ki": "genitive", "ka": "genitive",
}
_HINDI_VERB_MAP = {
    "bhej": "send", "bhejna": "send", "bol": "tell", "batao": "tell",
    "karo": "do", "kar": "do", "laga": "set", "lagao": "set",
    "khol": "open", "band": "close", "dhundo": "search",
    "bajao": "play", "sunao": "play", "call karo": "call",
}


def parse_hindi_grammar(text: str) -> dict:
    words  = text.lower().split()
    result = {
        "agent": None, "recipient": None, "location": None,
        "action_verb": None, "vibhakti_map": {}, "raw_verbs": [],
    }
    for i, w in enumerate(words):
        vib = _VIBHAKTI.get(w)
        if vib and i > 0:
            s = words[i - 1]
            result["vibhakti_map"][s] = vib
            if vib == "dative"  and not result["recipient"]: result["recipient"] = s
            if vib == "ergative": result["agent"]    = s
            if vib == "locative": result["location"] = s
        if w in _HINDI_VERB_MAP:
            result["raw_verbs"].append(w)
            if not result["action_verb"]:
                result["action_verb"] = _HINDI_VERB_MAP[w]
    return result


# ======================================================================
#  MODULE 8 — INTENT MEMORY BIAS
# ======================================================================

class IntentMemoryBias:
    @staticmethod
    def apply(user_id: str, backend: _MemoryBackend = _MEM_BACKEND) -> dict[str, float]:
        if not hasattr(backend, "_user"):
            return {}
        counts = backend._user(user_id).get("intent_counts", {})
        total  = sum(counts.values()) or 1
        applied: dict[str, float] = {}
        for intent, count in counts.items():
            boost = round(min(count / total * 0.10, 0.05), 3)
            if boost > 0.005:
                _boost_store.update(intent, success=True)
                applied[intent] = boost
        return applied


# ======================================================================
#  MODULE 9 — GOAL PERSISTENCE
# ======================================================================

_GOAL_SUGGEST: dict[str, list[str]] = {
    "communicate": ["Rahul se baat ho gayi? Call bhi kar du?"],
    "schedule":    ["Reminder set — koi aur time chahiye?"],
    "media":       ["Song chal raha — playlist banani hai?"],
    "browse":      ["Search complete — koi aur page?"],
}


@dataclass
class GoalState:
    goal:              str       = ""
    steps_done:        list[str] = field(default_factory=list)
    steps_remaining:   list[str] = field(default_factory=list)
    contacts_involved: list[str] = field(default_factory=list)

    def is_complete(self) -> bool:
        return bool(self.steps_done) and not self.steps_remaining


class GoalPersistence:
    def __init__(self) -> None:
        self._goals: list[GoalState] = []

    def update(self, plan_goal: str, intent: str,
               contacts: list[str]) -> GoalState | None:
        if plan_goal and plan_goal != "general task":
            active = next((g for g in self._goals if g.goal == plan_goal), None)
            if not active:
                active = GoalState(goal=plan_goal, contacts_involved=contacts)
                self._goals.append(active)
            if intent not in active.steps_done:
                active.steps_done.append(intent)
            return active
        return None

    def suggest_next(self, goal: str) -> list[str]:
        return _GOAL_SUGGEST.get(goal, [])

    def active_goals(self) -> list[GoalState]:
        return [g for g in self._goals if not g.is_complete()]


# ======================================================================
#  MODULE 10 — AUTO SUGGEST
# ======================================================================

_POST_SUGGESTS: dict[str, list[str]] = {
    "send_message":  ["Call bhi kar du?", "Reminder set karna hai?"],
    "call_contact":  ["Message bhej du?"],
    "play_music":    ["Volume adjust?", "Next song?"],
    "set_reminder":  ["Timer bhi set karni hai?"],
    "search_web":    ["Result summarize karu?"],
    "take_screenshot": ["Share karna hai?"],
}


class AutoSuggest:
    @staticmethod
    def suggest(action: dict, emotion: EmotionResult,
                goal_state: GoalState | None = None) -> list[str]:
        intent = action.get("intent", "")
        sugg   = list(_POST_SUGGESTS.get(intent, []))
        if emotion.dominant in ("frustrated", "frustrated_urgency"):
            sugg = ["Ho gaya! Kuch aur chahiye?"] + sugg[:1]
        elif emotion.dominant == "grateful":
            sugg = []
        if goal_state and not goal_state.is_complete():
            sugg = _GOAL_SUGGEST.get(goal_state.goal, [])[:1] + sugg[:1]
        return sugg[:2]


# ======================================================================
#  MODULE 11 — AUTO FEEDBACK
# ======================================================================

class AutoFeedbackLoop:
    def __init__(self, history: ActionHistory) -> None:
        self._hist = history

    def record(self, action: dict, result: ExecutorResult,
               raw_input: str = "") -> None:
        status = "success" if result.success else "failed"
        _parser.feedback(action.get("intent", ""), success=result.success)
        self._hist.record(action=action, status=status,
                          error=result.error, raw_input=raw_input)


# ======================================================================
#  MODULE 12 — SILENT MODE
# ======================================================================

class SilentMode:
    def __init__(self, threshold: float = 0.88,
                 wake_words: list[str] = None,
                 always_fire: set[str] = None) -> None:
        self.threshold   = threshold
        self.wake_words  = [w.lower() for w in (wake_words or ["radhe", "hey radhe"])]
        self.always_fire = always_fire or {"system_control", "user_boundary"}
        self.active      = False

    def should_fire(self, text: str, confidence: float, intent: str) -> bool:
        if not self.active:
            return True
        if any(w in text.lower() for w in self.wake_words):
            return True
        if intent in self.always_fire:
            return True
        from command_parser import detect_urgency
        if detect_urgency(text) == "high":
            return True
        return confidence >= self.threshold


# ======================================================================
#  RADHE ENGINE — Main Orchestrator
# ======================================================================

class RadheEngine:
    """
    Radhe Intelligence Engine.

    Fix 1: ExecutionGovernor gates all AI planner calls.
    Fix 2: Three modes — SINGLE / CHAIN / AGENT. No wasted compute.
    Fix 3: DecisionMemory injects directly into entities.
    Fix 4: ToolFeedbackLoop auto-fills message from tool output.
    Fix 5: PlanScorer chooses best candidate plan.
    Fix 6: DeepContext injected as plain text into planner prompt.
    Fix 7: FailureMemory redirects to alternate channels on failure.
    """

    def __init__(
        self,
        user_id:          str            = "default",
        bridge:           ExecutorBridge = None,
        window_size:      int            = 5,
        silent_threshold: float          = 0.88,
        auto_apply_bias:  bool           = True,
        translate_hindi:  bool           = False,
    ) -> None:
        self.user_id         = user_id
        self.session         = SessionState()
        self.history         = ActionHistory()
        self.translate_hindi = translate_hindi

        self.memory         = MemoryResolver(user_id)
        self.bridge         = bridge or build_default_bridge()
        self.tool_selector  = ToolSelector(self.memory)
        self.context_window = ContextWindow(window_size)
        self.emotion_det    = EmotionToneDetector()
        self.goal_tracker   = GoalPersistence()
        self.auto_feedback  = AutoFeedbackLoop(self.history)
        self.silent_mode    = SilentMode(threshold=silent_threshold)
        self.suggester      = AutoSuggest()
        self.silent_mode.active = False

        self.decision_mem = DecisionMemory(user_id)
        self.failure_mem  = FailureMemory(user_id)
        self.deep_ctx     = DeepContext()
        self.agent_loop   = AgentLoop(
            bridge       = self.bridge,
            decision_mem = self.decision_mem,
            failure_mem  = self.failure_mem,
            deep_ctx     = self.deep_ctx,
        )

        if auto_apply_bias:
            IntentMemoryBias.apply(user_id)

    def handle(self, text: str) -> EngineResult | None:
        start = time.monotonic()

        # NLP: language
        language = "en"
        if _NLP_AVAILABLE:
            language = _nlp.detect_language(text)

        # NLP: translation
        parse_text = text
        if _NLP_AVAILABLE and self.translate_hindi and language == "hi":
            t = _nlp.translate_text(text, dest_lang="en")
            if t and t != text:
                parse_text = t

        # Emotion
        emotion = self.emotion_det.detect(text)

        # NLP: sentiment
        sentiment_dict: dict[str, Any] = {"sentiment": "NEUTRAL", "confidence": 0.5}
        if _NLP_AVAILABLE:
            sentiment_dict         = _nlp.detect_sentiment(text)
            emotion.sentiment      = sentiment_dict["sentiment"]
            emotion.sentiment_conf = float(sentiment_dict.get("confidence", 0.5))

        # Context
        ctx = self.context_window.to_context()
        ctx.update(self.session.context)
        ctx.update(self.deep_ctx.to_context_dict())

        if _NLP_AVAILABLE:
            kw = _nlp.extract_keywords(text, num_keywords=5)
            if kw:
                ctx["keywords"] = kw

        self.session.context = ctx

        # Parse
        result      = _parser.step(parse_text, self.session)
        action_dict = result.to_dict()
        intent = action_dict.get("intent") or action_dict.get("partial_intent", "unknown")
        conf   = float(action_dict.get("confidence", 0.0))

        # Silent mode
        if not self.silent_mode.should_fire(text, conf, intent):
            return EngineResult(
                action=action_dict, silent_skipped=True,
                language=language, sentiment=sentiment_dict,
            )

        # Groq fallback for ambiguous commands
        if needs_ai_reasoning(parse_text, intent) and intent not in _COMPLEX_INTENTS:
            ai = GroqAILayer.reason(parse_text, ctx, action_dict)
            if ai["handled"] and ai["actions"]:
                action_dict = ai["actions"][0]
                intent      = action_dict.get("intent", intent)
                conf        = float(action_dict.get("confidence", conf))

        # Memory enrichment
        memory_notes: list[str] = []
        if intent not in ("clarify", "ai_fallback", "none", "cancelled"):
            action_dict, memory_notes = self.memory.enrich_action(action_dict)

        # Fix 3: direct entity injection from decision memory
        entities = action_dict.get("entities", {})
        entities = self.decision_mem.inject_into_entities(intent, entities)
        action_dict["entities"] = entities

        tool = self.tool_selector.select(action_dict)

        if intent == "clarify":
            return EngineResult(
                action=action_dict, emotion=emotion.to_dict(),
                memory_used=memory_notes, tool_choice=tool,
                context_size=len(ctx.get("recent_actions", [])),
                language=language, sentiment=sentiment_dict,
            )

        # ── Fix 2: EXECUTION MODE ROUTING ─────────────────────────────
        mode              = ExecutionGovernor.decide_mode(intent, parse_text, entities, ctx)
        exec_result: ExecutorResult | None = None
        agent_result_dict: dict | None     = None

        if mode == MODE_AGENT:
            agent_res         = self.agent_loop.run(
                goal=parse_text, context=ctx,
                intent=intent, entities=entities,
            )
            agent_result_dict = agent_res.to_dict()
            if agent_res.plan.steps:
                last_done = next(
                    (s for s in reversed(agent_res.plan.steps) if s.status == "done"),
                    agent_res.plan.steps[0],
                )
                action_dict = {
                    "intent": last_done.intent, "entities": last_done.entities,
                    "confidence": conf, "routing": "execute",
                }
                intent = last_done.intent
            exec_result = ExecutorResult(
                success = agent_res.status in (AgentStatus.ACHIEVED, AgentStatus.PARTIAL),
                output  = agent_res.final_output,
            )

        elif mode == MODE_CHAIN:
            try:
                cp = _parser.plan(parse_text, ctx)
                chain_plan = AgentPlan(
                    goal  = cp.goal,
                    steps = [
                        AgentStep(
                            step_id=s.step_id,
                            intent=s.action.get("intent", "ask_question"),
                            entities=s.action.get("entities", {}),
                            depends_on=s.depends_on,
                            can_parallel=s.can_parallel,
                        )
                        for s in cp.steps
                    ],
                )
                executor = PlanExecutor(
                    self.bridge, self.deep_ctx,
                    self.decision_mem, self.failure_mem,
                )
                chain_plan  = executor.execute_plan(chain_plan)
                outputs     = [
                    s.result.output for s in chain_plan.steps
                    if s.status == "done" and s.result
                ]
                exec_result = ExecutorResult(
                    success = any(s.status == "done" for s in chain_plan.steps),
                    output  = "\n".join(outputs),
                )
                if chain_plan.steps:
                    last = next(
                        (s for s in reversed(chain_plan.steps) if s.status == "done"),
                        chain_plan.steps[0],
                    )
                    action_dict = {
                        "intent": last.intent, "entities": last.entities,
                        "confidence": conf, "routing": "execute",
                    }
                    intent = last.intent
            except Exception as e:
                logger.warning("Chain mode failed: %s", e)
                exec_result = self.bridge.execute(action_dict)

        else:
            if intent not in _NO_EXEC_INTENTS:
                exec_result = self.bridge.execute(action_dict)

        # Feedback + memory
        if exec_result:
            self.auto_feedback.record(action_dict, exec_result, raw_input=text)
            self.memory.record(action_dict)
            self.decision_mem.record_outcome(intent, entities, exec_result.success)
            if not exec_result.success:
                self.failure_mem.record_failure(intent, entities)

        self.context_window.push(action_dict)

        cp_plan    = _parser.plan(parse_text, ctx)
        opt_plan   = _parser.optimize(cp_plan)
        contacts   = action_dict.get("entities", {}).get("contact", [])
        goal_state = self.goal_tracker.update(
            cp_plan.goal, intent,
            contacts if isinstance(contacts, list) else [],
        )
        self.deep_ctx.update_goal_status(
            cp_plan.goal,
            AgentStatus.ACHIEVED if (exec_result and exec_result.success)
            else AgentStatus.FAILED,
        )

        suggestions: list[str] = []
        if exec_result and exec_result.success:
            suggestions = self.suggester.suggest(action_dict, emotion, goal_state)
        if goal_state:
            suggestions += self.goal_tracker.suggest_next(goal_state.goal)
        suggestions = list(dict.fromkeys(suggestions))[:3]

        elapsed_ms = round((time.monotonic() - start) * 1000)

        return EngineResult(
            action         = action_dict,
            suggestions    = suggestions,
            emotion        = emotion.to_dict(),
            tool_choice    = tool,
            memory_used    = memory_notes,
            goal           = cp_plan.goal,
            plan           = opt_plan.to_dict() if opt_plan.total > 1 else None,
            context_size   = len(ctx.get("recent_actions", [])),
            language       = language,
            sentiment      = sentiment_dict,
            agent_result   = agent_result_dict,
            execution_mode = mode,
        )

    def get_history(self, n: int = 10) -> list[dict]:
        return [e.to_dict() for e in self.history.recent(n)]

    def get_stats(self) -> dict:
        return {
            "intent_stats":  self.history.intent_stats(),
            "intent_boosts": _boost_store.all(),
            "active_goals":  [g.goal for g in self.goal_tracker.active_goals()],
            "top_contacts":  self.memory.suggest_contacts(),
            "context_size":  len(self.context_window._window),
            "nlp_available": _NLP_AVAILABLE,
            "deep_ctx":      self.deep_ctx.to_context_dict(),
        }
