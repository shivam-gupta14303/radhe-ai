# src/core/command_executor.py
"""
Central command executor for Radhe.

Fixes applied vs submitted version:
- Restored all missing intents (smalltalk, persona, thanks, goodbye,
  change_language, change_mode, battery, volume, screenshot,
  list/cancel reminders, youtube, internet, directions, nlp tools)
- set_reminder now uses entities.get("reminder_text") not raw text
- ask_question and fallback now pass history/language/mode to LLM
- awaiting_contact cleared only on genuine success (not just "not found" check)
- _looks_like_phone has word-count guard to avoid false triggers
"""

import logging
import time
import re
from typing import Dict, Any, Optional

from system_control import system_controller
from web_control    import web_controller
from utilities      import utility_manager
from src.ai_knowledge import ai_knowledge
from memory         import MemoryManager
from nlp            import nlp_manager
from vision         import vision_manager
from src.messaging_service import messaging_service

logger     = logging.getLogger("Radhe_Executor")
MAX_HISTORY = 40

# Signals that indicate a send failed and awaiting_contact should be kept
_FAILURE_SIGNALS = ("not found", "failed", "not open", "wrong", "empty", "missing", "error")


class CommandExecutor:

    def __init__(self):
        self.memory = MemoryManager("data/memory.db")

        self.context: Dict[str, Any] = {
            "history":          [],
            "last_intent":      "",
            "last_command":     "",
            "language":         "en",
            "mode":             "neutral",
            "has_greeted":      False,
            "reminder_manager": None,
            "awaiting_contact": None,
            "profile_loaded":   False,
        }

        self._load_profile()

    # ==================================================================
    # PROFILE
    # ==================================================================

    def _load_profile(self, user_id: str = "default") -> None:
        try:
            profile = self.memory.get_profile(user_id=user_id) or {}
            lang = profile.get("language", "en")
            mode = profile.get("mode",     "neutral")
            if lang in ("en", "hi", "mixed"):
                self.context["language"] = lang
            if mode in ("neutral", "casual", "formal"):
                self.context["mode"] = mode
        except Exception as e:
            logger.warning("Profile load failed: %s", e)
        finally:
            self.context["profile_loaded"] = True

    def _save_profile(self, user_id: str = "default") -> None:
        try:
            self.memory.set_profile_value("language", self.context["language"], user_id)
            self.memory.set_profile_value("mode",     self.context["mode"],     user_id)
        except Exception:
            pass

    # ==================================================================
    # HISTORY
    # ==================================================================

    def _log(self, role: str, text: str) -> None:
        self.context["history"].append({
            "role": role,
            "text": text,
            "time": time.time()
        })
        self.context["history"] = self.context["history"][-MAX_HISTORY:]

    # ==================================================================
    # HELPERS
    # ==================================================================

    def _resp(self, text: str) -> Dict[str, Any]:
        text = (text or "Something went wrong.").strip()
        self._log("assistant", text)
        return {"text": text, "voice": text}

    def _lang(self, en: str, hi: str = "") -> str:
        lang = self.context.get("language", "en")
        if lang == "hi"    and hi: return hi
        if lang == "mixed" and hi: return f"{hi} ({en})"
        return en

    def _ai(self, text: str, ctx: Dict) -> str:
        """Call ai_knowledge with full context. Falls back gracefully."""
        try:
            return ai_knowledge.answer_question(
                text,
                history  = ctx.get("history",  []),
                language = ctx.get("language", "en"),
                mode     = ctx.get("mode",     "neutral")
            )
        except TypeError:
            return ai_knowledge.answer_question(text)

    # ==================================================================
    # EXECUTE  (public entry point)
    # ==================================================================

    def execute(
        self,
        parsed:   Dict[str, Any],
        text:     str,
        context:  Optional[Dict[str, Any]] = None,
        user_id:  str = "default"
    ) -> Dict[str, Any]:

        ctx      = context if context is not None else self.context
        intent   = (parsed.get("intent") or "unknown").strip()
        entities = parsed.get("entities") or {}

        self._log("user", text)
        ctx["last_intent"]  = intent
        ctx["last_command"] = text

        try:
            result = self._route(intent, entities, text, ctx)
        except Exception as e:
            logger.exception("Unhandled executor error: %s", e)
            result = self._resp(self._lang(
                "Something went wrong. Please try again.",
                "Kuch gadbad ho gayi. Dobara try karo."
            ))

        self._save_profile(user_id)
        return result

    # ==================================================================
    # ROUTER
    # ==================================================================

    def _route(
        self,
        intent:   str,
        entities: Dict[str, Any],
        text:     str,
        ctx:      Dict[str, Any]
    ) -> Dict[str, Any]:

        # ── GREETING ──────────────────────────────────────────────────
        if intent == "greeting":
            if not ctx.get("has_greeted"):
                ctx["has_greeted"] = True
                return self._resp(self._lang(
                    "Hello! Radhe here. How can I help you?",
                    "Namaste! Main Radhe hoon. Kya help kar sakta hoon?"
                ))
            return self._resp(self._lang("Yes, I'm listening.", "Haan, bol."))

        # ── SMALLTALK ─────────────────────────────────────────────────
        elif intent == "conversation_smalltalk":
            return self._resp(self._lang(
                "I'm doing well! Always here for you. How's your day going?",
                "Main theek hoon! Hamesha tumhare liye hoon. Tumhara din kaisa ja raha hai?"
            ))

        # ── PERSONA ───────────────────────────────────────────────────
        elif intent == "persona_query":
            return self._resp(self._lang(
                "I'm Radhe, your personal AI companion. I can open apps, search the web, "
                "set reminders, send WhatsApp messages, answer questions, and more.",
                "Main Radhe hoon, tumhara personal AI companion. Main apps khol sakta hoon, "
                "web search, reminders, WhatsApp messages, aur bahut kuch."
            ))

        # ── THANKS ────────────────────────────────────────────────────
        elif intent == "thanks":
            return self._resp(self._lang("You're welcome!", "Aapka swagat hai!"))

        # ── GOODBYE ───────────────────────────────────────────────────
        elif intent == "goodbye":
            return self._resp(self._lang("Goodbye! Take care.", "Theek hai, phir milte hain."))

        # ── LANGUAGE CHANGE ───────────────────────────────────────────
        elif intent == "change_language":
            target = (entities.get("target_language") or "").lower()
            if not target:
                lower = text.lower()
                if "hindi" in lower:  target = "hi"
                elif "english" in lower: target = "en"
                else: target = "en"

            if target not in ("en", "hi", "mixed"):
                return self._resp("I didn't catch which language. English or Hindi?")

            ctx["language"] = target
            self.context["language"] = target

            if target == "hi":
                return self._resp("Theek hai, ab main Hindi mein baat karunga.")
            elif target == "en":
                return self._resp("Alright, switching to English.")
            return self._resp("Thik hai, ab Hinglish mein baat karte hain.")

        # ── MODE CHANGE ───────────────────────────────────────────────
        elif intent == "change_mode":
            target = (entities.get("target_mode") or "").lower()
            lower  = text.lower()
            if not target:
                if any(w in lower for w in ["casual", "normal", "bina formal"]): target = "casual"
                elif "formal" in lower: target = "formal"
                else: target = "neutral"

            ctx["mode"] = target
            self.context["mode"] = target
            return self._resp(self._lang(
                f"Switched to {target} mode.",
                f"Theek hai, {target} mode mein baat karte hain."
            ))

        # ── TIME / DATE ───────────────────────────────────────────────
        elif intent == "get_time":
            return self._resp(utility_manager.get_time())

        elif intent == "get_date":
            return self._resp(utility_manager.get_date())

        # ── APPS ──────────────────────────────────────────────────────
        elif intent == "open_app":
            app = (entities.get("application") or "").strip()
            if not app:
                return self._resp(self._lang("Which app should I open?", "Kaunsi app kholun?"))
            return self._resp(system_controller.open_app(app))

        elif intent == "close_app":
            app = (entities.get("application") or "").strip()
            if not app:
                return self._resp(self._lang("Which app should I close?", "Kaunsi app band karun?"))
            return self._resp(system_controller.close_application(app))

        # ── WEB ───────────────────────────────────────────────────────
        elif intent == "search_web":
            query = (entities.get("query") or text).strip()
            return self._resp(web_controller.google_search(query))

        elif intent == "open_website":
            site = (entities.get("website") or "").strip()
            if not site:
                return self._resp(self._lang("Which website?", "Kaunsi website kholun?"))
            return self._resp(web_controller.open_website(site))

        elif intent == "youtube_search":
            query = (entities.get("query") or text).strip()
            return self._resp(web_controller.youtube_search(query))

        elif intent == "get_directions":
            origin = (entities.get("origin")      or "").strip()
            dest   = (entities.get("destination") or "").strip()
            return self._resp(web_controller.get_maps(origin=origin, dest=dest))

        elif intent == "check_internet":
            return self._resp(web_controller.check_internet())
        # ADD inside _route() (place under WEB section or nearby)

        elif intent == "news_search":
            topic = (entities.get("topic") or "").strip()
            return self._resp(web_controller.news_search(topic))

        elif intent == "get_weather":
            location = (entities.get("location") or "").strip()
            return self._resp(web_controller.get_weather(location))

        # ── SYSTEM ────────────────────────────────────────────────────
        elif intent == "system_control":
            ctrl = (entities.get("control_type") or "").strip()
            return self._resp(system_controller.system_control(ctrl))

        elif intent == "get_battery":
            return self._resp(system_controller.get_battery_status())

        elif intent == "set_volume":
            level = entities.get("level", 50)
            try:
                level = int(level)
            except (TypeError, ValueError):
                level = 50
            return self._resp(system_controller.set_volume(level))

        elif intent == "take_screenshot":
            path = system_controller.take_screenshot()
            if path:
                return self._resp(f"Screenshot saved to {path}.")
            return self._resp("Screenshot failed.")

        # ── REMINDER ─────────────────────────────────────────────────
        elif intent == "set_reminder":
            rm = ctx.get("reminder_manager")
            if not rm:
                return self._resp(self._lang(
                    "Reminder system is not available.",
                    "Reminder system available nahi hai."
                ))
            task     = (entities.get("reminder_text") or text).strip()
            time_str = (entities.get("time")          or "").strip()
            ok = rm.add_reminder(task, time_str)
            if ok:
                return self._resp(self._lang(
                    f"Reminder set: {task}",
                    f"Reminder set ho gaya: {task}"
                ))
            return self._resp(self._lang(
                "I couldn't understand the time for that reminder.",
                "Reminder ka time samajh nahi aaya."
            ))

        elif intent == "list_reminders":
            rm = ctx.get("reminder_manager")
            if not rm:
                return self._resp("Reminder system not available.")
            return self._resp(rm.list_reminders())

        elif intent == "cancel_reminder":
            rm      = ctx.get("reminder_manager")
            keyword = (entities.get("keyword") or text).strip()
            if not rm:
                return self._resp("Reminder system not available.")
            return self._resp(rm.cancel_reminder(keyword))

        # ── MESSAGING ────────────────────────────────────────────────
        elif intent == "send_message":
            return self._handle_message(entities, text, ctx)

        elif intent == "start_whatsapp":
            return self._resp(messaging_service.start_whatsapp_session())

        elif intent == "whatsapp_status":
            return self._resp(messaging_service.get_status())

        # ── NLP TOOLS ────────────────────────────────────────────────
        elif intent == "summarize_text":
            summary = nlp_manager.summarize_text(text)
            return self._resp(self._lang(
                f"Here's a summary: {summary}",
                f"Yeh summary hai: {summary}"
            ))

        elif intent == "sentiment_check":
            result     = nlp_manager.detect_sentiment(text)
            sentiment  = result.get("sentiment",  "NEUTRAL")
            confidence = result.get("confidence", 0.5)
            return self._resp(self._lang(
                f"Sentiment: {sentiment} (confidence {confidence:.2f})",
                f"Mood: {sentiment} (vishwas {confidence:.2f})"
            ))

        elif intent == "keyword_extract":
            keywords = nlp_manager.extract_keywords(text)
            if keywords:
                return self._resp(self._lang(
                    "Top keywords: " + ", ".join(keywords),
                    "Mukhya shabd: "  + ", ".join(keywords)
                ))
            return self._resp(self._lang(
                "No strong keywords found.",
                "Koi khaas keywords nahi mile."
            ))

        # ── VISION ───────────────────────────────────────────────────
        elif intent == "analyze_screen":
            result = vision_manager.capture_screen_and_analyze()
            return self._resp(result)

        elif intent == "analyze_image":
            path = (entities.get("path") or "").strip()
            if not path:
                return self._resp("Please tell me which image file to analyze.")
            return self._resp(vision_manager.analyze_image(path))

        # ── Q&A ───────────────────────────────────────────────────────
        elif intent == "ask_question":
            return self._resp(self._ai(text, ctx))

        # ── FALLBACK ──────────────────────────────────────────────────
        else:
            return self._resp(self._ai(text, ctx))

    # ==================================================================
    # MESSAGE HANDLER
    # ==================================================================

    def _handle_message(
        self,
        entities: Dict[str, Any],
        text:     str,
        ctx:      Dict[str, Any]
    ) -> Dict[str, Any]:

        # ── If we're waiting for a phone number, handle that first ────
        awaiting = ctx.get("awaiting_contact")
        if awaiting and _looks_like_phone(text):
            return self._handle_awaiting_contact(text, ctx)

        platform = (entities.get("platform") or "whatsapp").lower().strip()
        contact  = (entities.get("contact")  or "").strip()
        message  = (entities.get("message")  or "").strip()

        # Fallback message extraction from raw text
        if not message:
            lower = text.lower()
            for kw in ("saying", "that", "message"):
                if kw in lower:
                    part = text.split(kw, 1)[1].strip()
                    if part:
                        message = part
                        break

        if not message:
            return self._resp(self._lang(
                "What message should I send?",
                "Kya message bhejna hai?"
            ))

        if not contact:
            return self._resp(self._lang(
                "Who should I send it to?",
                "Kise bhejna hai?"
            ))

        # Store pending state in case contact is not found
        ctx["awaiting_contact"] = {
            "contact_name": contact,
            "message":      message,
            "platform":     platform
        }

        result = messaging_service.send(platform, contact, message)

        # Clear pending state only on genuine success
        if not any(s in result.lower() for s in _FAILURE_SIGNALS):
            ctx["awaiting_contact"] = None

        return self._resp(result)

    # ==================================================================
    # AWAITING CONTACT HANDLER
    # ==================================================================

    def _handle_awaiting_contact(
        self,
        text: str,
        ctx:  Dict[str, Any]
    ) -> Dict[str, Any]:
        """Complete a pending send by saving the phone number the user just provided."""

        awaiting     = ctx.get("awaiting_contact", {})
        contact_name = awaiting.get("contact_name", "")
        message      = awaiting.get("message",      "")
        platform     = awaiting.get("platform",     "whatsapp")

        phone = re.sub(r"[^\d+]", "", text).strip()

        if not phone or len(re.sub(r"[^\d]", "", phone)) < 7:
            return self._resp(self._lang(
                "That doesn't look like a valid phone number. "
                "Please give it in international format, like +919876543210.",
                "Yeh valid phone number nahi lagta. "
                "Please +919876543210 jaise format mein do."
            ))

        result = messaging_service.save_and_send(
            contact_name, phone, message, platform
        )

        # Always clear after attempting save_and_send
        ctx["awaiting_contact"] = None

        return self._resp(result)


# ==================================================================
# MODULE-LEVEL HELPER
# ==================================================================

def _looks_like_phone(text: str) -> bool:
    """
    Return True if text looks like a phone number response.
    Word count guard prevents a normal sentence containing a number
    from triggering the phone-number handler.
    """
    digits     = re.sub(r"[^\d]", "", text)
    word_count = len(text.strip().split())
    return len(digits) >= 7 and word_count <= 3


# ==================================================================
# GLOBAL INSTANCE
# ==================================================================

executor = CommandExecutor()