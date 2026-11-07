# scratch/apply_whatsapp_updates.py
import re

# ======================================================================
# 1. UPDATE COMMAND_PARSER.PY
# ======================================================================
print("Updating src/command_parser.py...")
with open("src/command_parser.py", "r", encoding="utf-8") as f:
    cp_text = f.read()

cp_text_norm = cp_text.replace("\r\n", "\n")

rules_target = '_rules("read_messages", 0.96,\n    r"\\b(?:read|check|show|get)\\s+(?:my\\s+)?(?:unread\\s+)?(?:whatsapp\\s+)?messages?\\b",\n    r"\\b(?:check|read|open)\\s+(?:my\\s+)?whatsapp\\s+messages?\\b",\n    r"\\bread\\s+(?:messages?|chats?)\\s+from\\s+(?P<contact>[A-Za-z0-9_\\u0900-\\u097F]+)\\b",\n    r"\\b(?:koi|kiska)\\s+(?:naya\\s+)?(?:whatsapp\\s+)?message\\s+(?:aaya|hai)\\b",\n    r"\\bwhatsapp\\s+(?:messages?|check karo|padho|dekho)\\b",\n    r"\\bunread\\s+messages?\\b")'

whatsapp_mode_rules = '''_rules("read_messages", 0.96,
    r"\\b(?:read|check|show|get)\\s+(?:my\\s+)?(?:unread\\s+)?(?:whatsapp\\s+)?messages?\\b",
    r"\\b(?:check|read|open)\\s+(?:my\\s+)?whatsapp\\s+messages?\\b",
    r"\\bread\\s+(?:messages?|chats?)\\s+from\\s+(?P<contact>[A-Za-z0-9_\\u0900-\\u097F]+)\\b",
    r"\\b(?:koi|kiska)\\s+(?:naya\\s+)?(?:whatsapp\\s+)?message\\s+(?:aaya|hai)\\b",
    r"\\bwhatsapp\\s+(?:messages?|check karo|padho|dekho)\\b",
    r"\\bunread\\s+messages?\\b")

_rules("set_whatsapp_mode", 0.96,
    r"\\b(?:set|change|switch)\\s+(?:whatsapp\\s+)?mode\\s+(?:to\\s+)?(?P<mode>monitor|approval|auto[\\s\\-_]?reply)\\b",
    r"\\b(?:turn\\s+on|enable|activate)\\s+(?:whatsapp\\s+)?(?P<mode>auto[\\s\\-_]?reply|approval|monitor)(?:\\s+mode)?\\b",
    r"\\b(?:turn\\s+off|disable|deactivate)\\s+(?:whatsapp\\s+)?auto[\\s\\-_]?reply(?:\\s+mode)?\\b",
    r"\\bwhatsapp\\s+mode\\s+(?:to\\s+)?(?P<mode>monitor|approval|auto[\\s\\-_]?reply)\\b",
    r"\\bwhatsapp\\s+(?:pe\\s+)?(?P<mode>monitor|approval|auto[\\s\\-_]?reply)\\s+mode(?:\\s+(?:karo|on\\s+karo|lagao))?\\b",
    r"\\bwhatsapp\\s+(?:auto[\\s\\-_]?reply|monitor|approval)\\s+(?:on|karo|lagao)\\b")

_rules("get_whatsapp_mode", 0.96,
    r"\\b(?:what\\s+is|check|show|get)\\s+(?:the\\s+)?whatsapp\\s+mode\\b",
    r"\\bwhatsapp\\s+mode\\s+(?:kya\\s+hai|check\\s+karo|status)\\b")'''

if rules_target in cp_text_norm:
    cp_text_norm = cp_text_norm.replace(rules_target, whatsapp_mode_rules, 1)

norm_target = '''    if best_intent == "change_mode":
        casual = {"normal", "casual", "informal", "normally", "casually"}
        best_entities["target_mode"] = "casual" if any(w in text for w in casual) else "formal"'''

norm_replacement = '''    if best_intent == "change_mode":
        casual = {"normal", "casual", "informal", "normally", "casually"}
        best_entities["target_mode"] = "casual" if any(w in text for w in casual) else "formal"
    if best_intent == "set_whatsapp_mode":
        mode_val = best_entities.get("mode", "").lower()
        if not mode_val:
            if any(w in text.lower() for w in ("disable", "turn off", "deactivate", "stop")):
                mode_val = "monitor"
            elif any(w in text.lower() for w in ("auto reply", "autoreply", "auto_reply", "auto")):
                mode_val = "auto_reply"
            elif "approval" in text.lower() or "approve" in text.lower():
                mode_val = "approval"
            elif "monitor" in text.lower():
                mode_val = "monitor"
            else:
                mode_val = "monitor"
        else:
            if "auto" in mode_val:
                mode_val = "auto_reply"
            elif "approv" in mode_val:
                mode_val = "approval"
            else:
                mode_val = "monitor"
        best_entities["mode"] = mode_val'''

if norm_target in cp_text_norm and "set_whatsapp_mode" not in norm_target:
    cp_text_norm = cp_text_norm.replace(norm_target, norm_replacement, 1)

with open("src/command_parser.py", "w", encoding="utf-8") as f:
    f.write(cp_text_norm)
print("[OK] src/command_parser.py processed.")


# ======================================================================
# 2. UPDATE COMMAND_EXECUTOR.PY
# ======================================================================
print("Updating src/command_executor.py...")
with open("src/command_executor.py", "r", encoding="utf-8") as f:
    ce_text = f.read()

ce_text_norm = ce_text.replace("\r\n", "\n")

cancel_block = '''        # Check for explicit cancellation
        clean_text_lower = text.strip().lower()
        if intent in ("cancel", "cancelled", "stop") or clean_text_lower in (
            "cancel", "stop", "nevermind", "ruk", "nahi", "exit", "quit", "chhod do", "mat bhejo", "cancel karo"
        ):
            ctx.pop("awaiting_message", None)
            ctx.pop("awaiting_contact", None)
            return self._resp(self._lang(
                "Okay, cancelled.",
                "Theek hai, cancel kar diya.",
                "Okay, cancel.",
            ))'''

cancel_replacement = '''        # Check for explicit cancellation
        clean_text_lower = text.strip().lower()
        if intent in ("cancel", "cancelled", "stop") or clean_text_lower in (
            "cancel", "stop", "nevermind", "ruk", "nahi", "exit", "quit", "chhod do", "mat bhejo", "cancel karo", "no", "don't send", "discard"
        ):
            ctx.pop("awaiting_message", None)
            ctx.pop("awaiting_contact", None)
            if ctx.pop("pending_whatsapp_approval", None):
                ctx.pop("awaiting_whatsapp_approval", None)
                return self._resp(self._lang(
                    "Okay, discarded WhatsApp reply.",
                    "Theek hai, WhatsApp reply cancel kar diya.",
                    "Okay, WhatsApp reply discard kar diya.",
                ))
            return self._resp(self._lang(
                "Okay, cancelled.",
                "Theek hai, cancel kar diya.",
                "Okay, cancel.",
            ))

        # Pending WhatsApp approval resolution
        if ctx.get("pending_whatsapp_approval"):
            pending = ctx.pop("pending_whatsapp_approval")
            ctx.pop("awaiting_whatsapp_approval", None)
            affirmative_words = (
                "yes", "send", "send it", "bhej do", "bhejo", "haan", "ha", "kar do",
                "karo", "confirm", "approve", "theek", "sure", "okay", "ok"
            )
            if any(w in clean_text_lower for w in affirmative_words) or intent in ("confirm", "send_message"):
                sender = pending.get("sender", "")
                reply = pending.get("reply", "")
                res = messaging_service.send(platform="whatsapp", contact_name=sender, message=reply)
                return self._resp(res)
            else:
                return self._resp(self._lang(
                    "Okay, WhatsApp reply discarded.",
                    "Theek hai, WhatsApp reply cancel kar diya.",
                    "Okay, discarded.",
                ))'''

if cancel_block in ce_text_norm:
    ce_text_norm = ce_text_norm.replace(cancel_block, cancel_replacement, 1)

read_msg_block = '''        if intent in ("read_messages", "check_messages"):
            contact = entities.get("contact") or entities.get("contact_name") or ""
            if isinstance(contact, list):
                contact = contact[0] if contact else ""
            contact = str(contact or "").strip()
            if contact:
                return self._resp(messaging_service.read_messages(contact))
            return self._resp(messaging_service.get_unread_messages())'''

read_msg_replacement = '''        if intent in ("read_messages", "check_messages"):
            contact = entities.get("contact") or entities.get("contact_name") or ""
            if isinstance(contact, list):
                contact = contact[0] if contact else ""
            contact = str(contact or "").strip()
            if contact:
                return self._resp(messaging_service.read_messages(contact))
            return self._resp(messaging_service.get_unread_messages())

        if intent == "set_whatsapp_mode":
            mode = entities.get("mode", "monitor")
            from social_media import social_integrator
            return self._resp(social_integrator.set_mode(mode))

        if intent in ("get_whatsapp_mode", "check_whatsapp_mode"):
            from social_media import social_integrator
            return self._resp(f"WhatsApp mode is currently set to {social_integrator.get_mode()}.")'''

if read_msg_block in ce_text_norm:
    ce_text_norm = ce_text_norm.replace(read_msg_block, read_msg_replacement, 1)

with open("src/command_executor.py", "w", encoding="utf-8") as f:
    f.write(ce_text_norm)
print("[OK] src/command_executor.py processed.")


# ======================================================================
# 3. UPDATE RADHE.PY
# ======================================================================
print("Updating src/radhe.py...")
with open("src/radhe.py", "r", encoding="utf-8") as f:
    radhe_text = f.read()

radhe_text_norm = radhe_text.replace("\r\n", "\n")

# Connect speech callback
wa_init_target = '''    try:
        social_integrator.connect_executor(executor)
        social_integrator.listen_whatsapp()
        logger.info("WhatsApp listener started.")
    except Exception as e:'''

wa_init_replacement = '''    try:
        social_integrator.connect_executor(executor)
        social_integrator.set_speak_callback(speak)
        social_integrator.listen_whatsapp()
        logger.info("WhatsApp listener started.")
    except Exception as e:'''

if wa_init_target in radhe_text_norm:
    radhe_text_norm = radhe_text_norm.replace(wa_init_target, wa_init_replacement, 1)

# Wake word loop check
wake_loop_target = '''                # Skip wake word if we're mid-clarification, slot filling, or onboarding
                if not awaiting_reply:
                    if not listen_for_wake_word(WAKE_WORD):
                        continue'''

wake_loop_replacement = '''                # If an incoming message in Approval mode needs confirmation, activate awaiting_reply
                if executor.context.get("awaiting_whatsapp_approval"):
                    awaiting_reply = True
                    awaiting_prompt = "Should I send the WhatsApp reply? Please say yes or cancel."
                    executor.context.pop("awaiting_whatsapp_approval", None)

                # Skip wake word if we're mid-clarification, slot filling, onboarding, or WhatsApp approval
                if not awaiting_reply:
                    if not listen_for_wake_word(
                        WAKE_WORD,
                        stop_condition=lambda: bool(executor.context.get("awaiting_whatsapp_approval"))
                    ):
                        continue'''

if wake_loop_target in radhe_text_norm:
    radhe_text_norm = radhe_text_norm.replace(wake_loop_target, wake_loop_replacement, 1)

# Pop pending state on silence timeout
silence_timeout_target = '''                            executor.context.pop("awaiting_contact", None)
                            executor.context.pop("awaiting_message", None)'''

silence_timeout_replacement = '''                            executor.context.pop("awaiting_contact", None)
                            executor.context.pop("awaiting_message", None)
                            executor.context.pop("pending_whatsapp_approval", None)
                            executor.context.pop("awaiting_whatsapp_approval", None)'''

if silence_timeout_target in radhe_text_norm:
    radhe_text_norm = radhe_text_norm.replace(silence_timeout_target, silence_timeout_replacement, 1)

# Pop pending state on explicit cancel
cancel_timeout_target = '''                        executor.context.pop("awaiting_contact", None)
                        executor.context.pop("awaiting_message", None)'''

cancel_timeout_replacement = '''                        executor.context.pop("awaiting_contact", None)
                        executor.context.pop("awaiting_message", None)
                        executor.context.pop("pending_whatsapp_approval", None)
                        executor.context.pop("awaiting_whatsapp_approval", None)'''

if cancel_timeout_target in radhe_text_norm:
    radhe_text_norm = radhe_text_norm.replace(cancel_timeout_target, cancel_timeout_replacement, 1)

# Route pending approval before slot check
slot_dispatch_target = '''                    # If we're awaiting a follow-up slot (message text or contact name)
                    if executor.context.get("awaiting_message") or executor.context.get("awaiting_contact"):'''

slot_dispatch_replacement = '''                    # If we're awaiting confirmation for a drafted WhatsApp reply
                    if executor.context.get("pending_whatsapp_approval"):
                        awaiting_reply = False
                        awaiting_prompt = ""
                        result = executor.execute({"intent": "confirm_whatsapp_reply", "entities": {}}, text)
                        reply = result.get("voice") or result.get("text", "")
                        if reply:
                            speak(reply)
                        continue

                    # If we're awaiting a follow-up slot (message text or contact name)
                    if executor.context.get("awaiting_message") or executor.context.get("awaiting_contact"):'''

if slot_dispatch_target in radhe_text_norm:
    radhe_text_norm = radhe_text_norm.replace(slot_dispatch_target, slot_dispatch_replacement, 1)

with open("src/radhe.py", "w", encoding="utf-8") as f:
    f.write(radhe_text_norm)
print("[OK] src/radhe.py processed.")
