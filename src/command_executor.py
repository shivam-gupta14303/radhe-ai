# command_executor.py
import logging
import time
import re
import json
from typing import Dict, Any

from system_control import system_controller
from web_control import web_controller
from social_media import social_integrator
from src.ai_knowledge import ai_knowledge
from utilities import utility_manager
from contact_manager import contact_manager
from memory import MemoryManager
from nlp import nlp_manager  # <- NLP integration

logger = logging.getLogger("Radhe_CommandExecutor")
logger.setLevel(logging.INFO)

SUPPORTED_PLATFORMS = {
    "whatsapp",
    "telegram",
    "instagram",
    "twitter",
    "gmail",
    "email",
    "sms"
}

MAX_HISTORY_LEN = 40  # sliding window for chat history (short-term)


class CommandExecutor:
    def __init__(self):
        # DB-based memory manager (for personal profile etc.)
        self.memory = MemoryManager("data/memory.db")

        # simple in-memory context — can be per-user later (via user_id)
        self.context: Dict[str, Any] = {
            "last_command": "",
            "last_intent": "",
            "conversation_history": [],
            "emotional_state": "neutral",
            "user_name": "User",
            "mode": "neutral",          # neutral / formal / casual
            "language": "en",           # en / hi / mixed
            "has_greeted": False,       # to avoid greeting spam
            "user_boundaries": {
                "avoid_calls": []       # e.g. ["beta", "sir"]
            },
            "awaiting_contact": None,
            "profile_loaded": False,
        }

        # Load personal profile from DB into context
        self._load_profile_into_context(self.context, user_id="default")

        logger.info("Command Executor initialized")

    # ---------- INTERNAL HELPERS: CONTEXT / MEMORY ----------

    def _load_profile_into_context(self, context: Dict[str, Any], user_id: str = "default") -> None:
        """
        Load long-term personal data from DB into runtime context.
        This runs once per executor (or per user) when needed.
        """
        try:
            profile = self.memory.get_profile(user_id=user_id) or {}
        except Exception as e:
            logger.exception("Error loading profile from memory: %s", e)
            profile = {}

        # language
        lang = profile.get("language")
        if lang in ("en", "hi", "mixed"):
            context["language"] = lang

        # mode
        mode = profile.get("mode")
        if mode in ("neutral", "formal", "casual"):
            context["mode"] = mode

        # user_name (optional, if you ever store it)
        if "user_name" in profile:
            context["user_name"] = profile["user_name"]

        # avoid_calls boundary list
        avoid_raw = profile.get("avoid_calls")
        avoid_list = []
        if avoid_raw:
            try:
                parsed = json.loads(avoid_raw)
                if isinstance(parsed, list):
                    avoid_list = [str(x) for x in parsed]
                else:
                    avoid_list = [str(avoid_raw)]
            except Exception:
                avoid_list = [str(avoid_raw)]

        context["user_boundaries"] = {
            "avoid_calls": avoid_list
        }

        context["profile_loaded"] = True

    def _save_profile_from_context(self, context: Dict[str, Any], user_id: str = "default") -> None:
        """
        Save selected context fields back to personal_profile table via MemoryManager.
        Called when language/mode/boundaries change.
        """
        try:
            # language
            lang = context.get("language")
            if lang in ("en", "hi", "mixed"):
                self.memory.set_profile_value("language", lang, user_id=user_id)

            # mode
            mode = context.get("mode")
            if mode in ("neutral", "formal", "casual"):
                self.memory.set_profile_value("mode", mode, user_id=user_id)

            # user name (optional)
            user_name = context.get("user_name")
            if user_name:
                self.memory.set_profile_value("user_name", str(user_name), user_id=user_id)

            # avoid_calls boundary list
            boundaries = context.get("user_boundaries", {})
            avoid_calls = boundaries.get("avoid_calls", [])
            try:
                avoid_json = json.dumps(avoid_calls)
            except Exception:
                avoid_json = "[]"
            self.memory.set_profile_value("avoid_calls", avoid_json, user_id=user_id)

        except Exception as e:
            logger.exception("Error saving profile to memory: %s", e)

    def _append_history(self, context: Dict[str, Any], role: str, text: str, meta: Dict[str, Any] = None) -> None:
        """
        Append a message to conversation_history with a sliding window.
        role: "user" or "assistant"
        """
        if "conversation_history" not in context or not isinstance(context["conversation_history"], list):
            context["conversation_history"] = []

        entry = {
            "role": role,
            "text": text,
            "time": time.time()
        }
        if meta:
            entry.update(meta)

        context["conversation_history"].append(entry)

        # Sliding window – keep only last MAX_HISTORY_LEN entries
        if len(context["conversation_history"]) > MAX_HISTORY_LEN:
            context["conversation_history"] = context["conversation_history"][-MAX_HISTORY_LEN:]

    # ---------- INTERNAL HELPERS: BEHAVIOUR / TONE ----------

    def _choose_by_lang(self, context: Dict[str, Any], text_en: str, text_hi: str = None) -> str:
        lang = context.get("language", "en")
        if lang == "hi":
            if text_hi:
                return text_hi
            return text_en
        if lang == "mixed" and text_hi:
            return f"{text_hi} ({text_en})"
        return text_en

    def _ack_greeting(self, context: Dict[str, Any]) -> str:
        """
        Greeting logic with:
        - first time full intro
        - later short 'I'm listening' style
        - respects mode + language
        """
        has_greeted = context.get("has_greeted", False)
        mode = context.get("mode", "neutral")

        if not has_greeted:
            context["has_greeted"] = True
            return self._choose_by_lang(
                context,
                "Hello! Radhe here. How can I help?",
                "Namaste! Main Radhe hoon. Batao, kya help kar sakta hoon?"
            )

        # Already greeted -> no intro spam
        if mode == "casual":
            return self._choose_by_lang(
                context,
                "Yeah, I'm here. Tell me.",
                "Haan bol na, sun raha hoon."
            )
        elif mode == "formal":
            return self._choose_by_lang(
                context,
                "Yes, I'm listening.",
                "Ji, main sun raha hoon."
            )
        else:
            return self._choose_by_lang(
                context,
                "Yes, how can I help?",
                "Haan ji, batao? Kya help chahiye?"
            )

    def _handle_smalltalk(self, context: Dict[str, Any], original_text: str) -> str:
        """
        For 'how are you', 'how's your day', etc.
        No reset, just natural conversation.
        """
        mode = context.get("mode", "neutral")

        if mode == "casual":
            return self._choose_by_lang(
                context,
                "I'm all good, always online for you. How are YOU doing?",
                "Main bilkul theek hoon, hamesha online. Tum batao, tumhara din kaisa ja raha hai?"
            )
        elif mode == "formal":
            return self._choose_by_lang(
                context,
                "I'm functioning well. Thank you for asking. How has your day been?",
                "Main bilkul theek kaam kar raha hoon. Poochne ke liye dhanyavaad. Aapka din kaisa raha?"
            )
        else:
            return self._choose_by_lang(
                context,
                "I'm doing fine, processing code and thoughts. How's your day going?",
                "Main theek hoon, code aur queries handle kar raha hoon. Tumhara din kaisa ja raha hai?"
            )

    def _handle_persona_query(self, context: Dict[str, Any]) -> str:
        """
        'Who are you', 'tell me about yourself', etc.
        No intro spam, no reset. Stable identity.
        """
        description = None
        try:
            if hasattr(ai_knowledge, "describe_self"):
                description = ai_knowledge.describe_self()
        except Exception as e:
            logger.exception("ai_knowledge.describe_self error: %s", e)

        if not description:
            description_en = (
                "I'm Radhe, your personal AI assistant running on your own system. "
                "I can open apps, search the web, set reminders, send WhatsApp messages, "
                "control basic system functions, and answer questions using an AI model."
            )
            description_hi = (
                "Main Radhe hoon, tumhara personal AI assistant jo tumhare system par hi chal raha hai. "
                "Main apps khol sakta hoon, web search kar sakta hoon, reminders set kar sakta hoon, "
                "WhatsApp message bhej sakta hoon, system ko control kar sakta hoon, "
                "aur AI model ki madad se tumhare sawaalon ka jawaab de sakta hoon."
            )
            return self._choose_by_lang(context, description_en, description_hi)

        return self._choose_by_lang(context, description, description)

    def _handle_language_change(self, context: Dict[str, Any], entities: Dict[str, Any], original_text: str, user_id: str) -> str:
        target = (entities.get("target_language") or "").strip().lower()
        if not target:
            lower = original_text.lower()
            if "hindi" in lower:
                target = "hi"
            elif "english" in lower:
                target = "en"

        if target not in ("en", "hi", "mixed"):
            return self._choose_by_lang(
                context,
                "I didn't fully catch which language you want. English or Hindi?",
                "Mujhe samajh nahi aaya ki kaunsi language chahiye. English ya Hindi?"
            )

        context["language"] = target
        self._save_profile_from_context(context, user_id=user_id)

        if target == "hi":
            return "Theek hai, ab main Hindi mein baat karunga."
        elif target == "en":
            return "Alright, I'll talk in English now."
        else:  # mixed
            return "Thik hai, ab thoda Hindi aur thoda English milakar baat karte hain."

    def _handle_mode_change(self, context: Dict[str, Any], entities: Dict[str, Any], original_text: str, user_id: str) -> str:
        target_mode = (entities.get("target_mode") or "").strip().lower()
        lower = original_text.lower()

        if not target_mode:
            if any(w in lower for w in ["casual", "normally", "normal talk", "bina formal", "zyada formal mat ho"]):
                target_mode = "casual"
            elif "formal" in lower or "respectful" in lower:
                target_mode = "formal"
            else:
                target_mode = "neutral"

        context["mode"] = target_mode
        self._save_profile_from_context(context, user_id=user_id)

        if target_mode == "casual":
            return self._choose_by_lang(
                context,
                "Okay, I'll keep it more casual and normal now.",
                "Theek hai, ab thoda normal aur casual tareeke se baat karunga."
            )
        elif target_mode == "formal":
            return self._choose_by_lang(
                context,
                "Understood. I will talk in a more formal and respectful tone.",
                "Samajh gaya. Ab main thoda zyada formal aur respectful tareeke se baat karunga."
            )
        else:
            return self._choose_by_lang(
                context,
                "Alright, I'll keep the tone balanced and neutral.",
                "Theek hai, main tone ko balanced aur neutral rakhoonga."
            )

    def _handle_user_boundary(self, context: Dict[str, Any], entities: Dict[str, Any], original_text: str, user_id: str) -> str:
        """
        For things like:
        - don't call me beta
        - mujhe sir mat bolo
        Saves preference and acknowledges politely.
        """
        lower = original_text.lower()
        term = (entities.get("disallowed_term") or "").strip().lower()

        if not term:
            m = re.search(r"(?:don't call me|do not call me)\s+([^\s,.!?]+)", lower)
            if m:
                term = m.group(1)
            else:
                m2 = re.search(r"mujhe\s+([^\s,.!?]+)\s+mat (?:bolo|kehna)", lower)
                if m2:
                    term = m2.group(1)

        boundaries = context.get("user_boundaries", {})
        avoid_calls = boundaries.get("avoid_calls", [])
        if term and term not in avoid_calls:
            avoid_calls.append(term)
        boundaries["avoid_calls"] = avoid_calls
        context["user_boundaries"] = boundaries

        self._save_profile_from_context(context, user_id=user_id)

        if term:
            return self._choose_by_lang(
                context,
                f"Got it. I won't call you '{term}' anymore.",
                f"Theek hai, ab se main tumhe '{term}' nahi bulaunga."
            )
        else:
            return self._choose_by_lang(
                context,
                "Understood. I'll avoid calling you things you don't like.",
                "Theek hai, main aapko waise nahi bulaunga jaise aapko pasand nahi hai."
            )

    # ---------- PUBLIC EXECUTE ----------

    def execute(
        self,
        parsed_command: Dict[str, Any],
        original_text: str,
        context: Dict[str, Any] = None,
        user_id: str = "default"
    ) -> Dict[str, Any]:
        """
        parsed_command: dict {intent, entities, confidence}
        original_text: original string from user
        context: optional user-specific context (for Telegram, voice sessions)
        user_id: for personal profile (defaults to "default")
        """
        if context is None:
            context = self.context

        if not context.get("profile_loaded"):
            self._load_profile_into_context(context, user_id=user_id)

        intent = parsed_command.get("intent", "unknown")

        # Save user message to history (before processing)
        self._append_history(
            context,
            role="user",
            text=original_text,
            meta={"parsed_intent": intent}
        )

        context["last_command"] = original_text

        entities = parsed_command.get("entities", {}) or {}

        response_text = "Sorry, I didn't understand that."
        response_voice = response_text

        logger.debug("Executing intent: %s | entities: %s", intent, entities)

        try:
            # ---------- BASIC INTENTS ----------
            if intent == "greeting":
                response_text = self._ack_greeting(context)

            elif intent == "thanks":
                response_text = self._choose_by_lang(
                    context,
                    "You're welcome!",
                    "Aapka swagat hai!"
                )

            elif intent == "goodbye":
                response_text = self._choose_by_lang(
                    context,
                    "Goodbye! Radhe signing off.",
                    "Theek hai, phir milte hain. Radhe signing off."
                )

            # ---------- HIGH-LEVEL CONVERSATION / META ----------
            elif intent == "conversation_smalltalk":
                response_text = self._handle_smalltalk(context, original_text)

            elif intent == "persona_query":
                response_text = self._handle_persona_query(context)

            elif intent == "change_language":
                response_text = self._handle_language_change(context, entities, original_text, user_id=user_id)

            elif intent == "change_mode":
                response_text = self._handle_mode_change(context, entities, original_text, user_id=user_id)

            elif intent == "user_boundary":
                response_text = self._handle_user_boundary(context, entities, original_text, user_id=user_id)

            # ---------- TIME / DATE ----------
            elif intent == "get_time":
                response_text = utility_manager.get_time()

            elif intent == "get_date":
                response_text = utility_manager.get_date()

            # ---------- APPS / WEB ----------
            elif intent == "open_app":
                app = entities.get("application", "").strip()
                response_text = (
                    system_controller.open_app(app)
                    if app else self._choose_by_lang(
                        context,
                        "Which app should I open?",
                        "Kaunsi app kholun?"
                    )
                )

            elif intent == "close_app":
                app = entities.get("application", "").strip()
                if app:
                    response_text = system_controller.close_application(app)
                else:
                    response_text = self._choose_by_lang(
                        context,
                        "Which application should I close?",
                        "Kaunsi application band karun?"
                    )

            elif intent == "search_web":
                query = entities.get("query", original_text).strip()
                response_text = web_controller.google_search(query)

            elif intent == "open_website":
                website = entities.get("website", "").strip()
                if website:
                    response_text = web_controller.open_website(website)
                else:
                    response_text = self._choose_by_lang(
                        context,
                        "Please tell me which website to open.",
                        "Kaunsi website kholun, batao."
                    )

            # ---------- REMINDER ----------
            elif intent == "set_reminder":

                time_str = entities.get("time", "").strip()
                reminder_text = entities.get("reminder_text", original_text).strip()

                rm = context.get("reminder_manager")

                if not rm:
                    response_text = self._choose_by_lang(
                        context,
                        "Reminder system is not available.",
                        "Reminder system abhi available nahi hai."
                    )

                else:
                    ok = rm.add_reminder(reminder_text, time_str)

                    if ok:
                        response_text = self._choose_by_lang(
                            context,
                            f"Reminder set: {reminder_text}",
                            f"Reminder set ho gaya: {reminder_text}"
                        )
                    else:
                        response_text = self._choose_by_lang(
                            context,
                            "I could not understand the reminder time.",
                            "Mujhe reminder ka time samajh nahi aaya."
                        )

            # ---------- NLP / TEXT TOOLS ----------
            elif intent == "summarize_text":
                summary = nlp_manager.summarize_text(original_text)
                response_text = self._choose_by_lang(
                    context,
                    f"Here is a short summary:\n{summary}",
                    f"Ye chhota sa saaransh hai:\n{summary}"
                )

            elif intent == "sentiment_check":
                result = nlp_manager.detect_sentiment(original_text)
                sentiment = result.get("sentiment", "NEUTRAL")
                conf = result.get("confidence", 0.5)
                response_text = self._choose_by_lang(
                    context,
                    f"Sentiment: {sentiment} (confidence {conf:.2f}).",
                    f"Mood: {sentiment} (vishwas {conf:.2f})."
                )

            elif intent == "keyword_extract":
                keywords = nlp_manager.extract_keywords(original_text)
                if keywords:
                    response_text = self._choose_by_lang(
                        context,
                        "Top keywords: " + ", ".join(keywords),
                        "Mukhya shabd: " + ", ".join(keywords)
                    )
                else:
                    response_text = self._choose_by_lang(
                        context,
                        "I couldn't extract any strong keywords from that.",
                        "Is text se mujhe koi khaas keywords nahi mile."
                    )

            # ---------- QUESTION ANSWERING / ChatGPT-style ----------
            elif intent == "ask_question":
                q = entities.get("question", original_text)
                try:
                    response_text = ai_knowledge.answer_question(
                        q,
                        history=context.get("conversation_history", []),
                        profile=self.memory.get_profile(user_id=user_id),
                        mode=context.get("mode", "neutral"),
                        language=context.get("language", "en"),
                        last_intent=context.get("last_intent", "")
                    )
                except TypeError:
                    response_text = ai_knowledge.answer_question(q)

            # ---------- MESSAGING (multi-platform) ----------
            elif intent == "send_message":
                def _to_text(value) -> str:
                        if value is None:
                            return ""
                        if isinstance(value, str):
                            return value
                        if isinstance(value, dict):
                            for key in ("text", "value", "content", "message"):
                                v = value.get(key)
                                if isinstance(v, str):
                                    return v
                            try:
                                return json.dumps(value, ensure_ascii=False)
                            except Exception:
                                return str(value)
                        if isinstance(value, (list, tuple)):
                            parts = []
                            for item in value:
                                if isinstance(item, str):
                                    parts.append(item)
                                elif isinstance(item, dict):
                                    for key in ("text", "value", "content", "message"):
                                        v = item.get(key)
                                        if isinstance(v, str):
                                            parts.append(v)
                                            break
                                    else:
                                        parts.append(str(item))
                                else:
                                    parts.append(str(item))
                            return " ".join(parts)
                        return str(value)

                platform_raw = entities.get("platform")
                contact_raw = entities.get("contact")
                message_raw = entities.get("message")

                platform = (_to_text(platform_raw) or "whatsapp").lower().strip()
                contact = _to_text(contact_raw).strip()
                message = _to_text(message_raw).strip()

                # fallback extraction if NLP didn't detect message entity
                if not message:

                    lower = original_text.lower()

                    if "saying" in lower:
                        message = original_text.split("saying", 1)[1].strip()

                    elif "that" in lower:
                        message = original_text.split("that", 1)[1].strip()

                # final validation
                if not message:
                    response_text = self._choose_by_lang(
                        context,
                        "What message should I send?",
                        "Kya message bhejna hai?"
                    )
                return {"text": response_text, "voice": response_text, "context": context}

                if not contact:
                    response_text = self._choose_by_lang(
                        context,
                        "Please tell me who you want to send the message to.",
                        "Kise message bhejna hai, ye batao."
                    )
                else:
                    c = contact_manager.get_contact(contact)
                    if c:
                        if platform == "whatsapp":
                            response_text = social_integrator.send_whatsapp_by_contact(contact, message)
                        elif platform in SUPPORTED_PLATFORMS:
                            response_text = self._choose_by_lang(
                                context,
                                f"Sending via {platform} is planned but not implemented yet.",
                                f"{platform} par bhejna planned hai, lekin abhi implement nahi hua."
                            )
                        else:
                            response_text = self._choose_by_lang(
                                context,
                                f"I don't know how to send messages on '{platform}' yet.",
                                f"Abhi mujhe '{platform}' par message bhejna nahi aata."
                            )
                    else:
                        context["awaiting_contact"] = {
                            "contact_name": contact,
                            "message": message,
                            "platform": platform
                        }
                        response_text = self._choose_by_lang(
                            context,
                            (
                                f"I don't have {contact}'s number saved. "
                                "Please provide the phone number (international format like +919...) "
                                "so I can save it and send the message."
                            ),
                            (
                                f"Mere paas {contact} ka number saved nahi hai. "
                                "Kripya phone number do (international format jaise +919...) "
                                "taaki main usse save karke message bhej sakun."
                            )
                        )

            # ---------- SYSTEM CONTROL ----------
            elif intent == "system_control":
                control_type = entities.get("control_type", original_text).strip()
                if control_type.lower() == "reboot":
                    control_type = "restart"
                response_text = system_controller.system_control(control_type)

            # ---------- FALLBACK: use AI knowledge for any unknown / not handled intent ----------
            else:
                try:
                    response_text = ai_knowledge.answer_question(
                        original_text,
                        history=context.get("conversation_history", []),
                        profile=self.memory.get_profile(user_id=user_id),
                        mode=context.get("mode", "neutral"),
                        language=context.get("language", "en"),
                        last_intent=context.get("last_intent", "")
                    )
                except TypeError:
                    response_text = ai_knowledge.answer_question(original_text)

            # --- POST-PROCESS: avoid repeated "Hello! Radhe here..." after first greeting ---
            if context.get("has_greeted") and isinstance(response_text, str):
                cleaned = re.sub(
                    r"^hello!\s*radhe here\.?\s*how can i help\?\s*",
                    "",
                    response_text.strip(),
                    flags=re.IGNORECASE
                ).strip()

                if cleaned != "":
                    response_text = cleaned
                else:
                    response_text = self._choose_by_lang(
                        context,
                        "I'm here. What do you want to do next?",
                        "Main yahin hoon. Ab kya karna hai?"
                    )

        except Exception as e:
            logger.exception("Execution error: %s", e)
            response_text = self._choose_by_lang(
                context,
                "Sorry, something went wrong while processing that.",
                "Maaf kijiye, is request ko process karte waqt kuch error aa gaya."
            )

        # update last_intent in context
        context["last_intent"] = intent

        # append assistant reply to history
        self._append_history(context, role="assistant", text=response_text)

        # ensure profile changes (if any) are persisted
        self._save_profile_from_context(context, user_id=user_id)

        response_voice = response_text  # your TTS layer will speak this
        return {"text": response_text, "voice": response_voice, "context": context}


# global instance
executor = CommandExecutor()
