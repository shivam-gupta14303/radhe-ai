from pathlib import Path

# 1. Update command_parser.py
cp = Path("src/command_parser.py")
content = cp.read_text(encoding="utf-8")

old_send = '_rules("send_message", 0.94,'
new_rules = """# WhatsApp & Social Messaging (Phase 6)
_rules("schedule_whatsapp_message", 0.96,
    r"\\b(?:schedule|bhejna)\\s+(?:a\\s+)?(?:whatsapp\\s+)?message\\s+(?:to\\s+)?(?P<contact>[A-Za-z][\\w\\s]*?)\\s+(?:at|on|for)\\s+(?P<time>[^,\\n]+?)\\s+(?:saying|message|that|ki)\\s+(?P<message>.+)",
    r"\\b(?P<contact>[A-Za-z][\\w\\s]*?)\\s+ko\\s+(?P<time>[^,\\n]+?)\\s+(?:whatsapp\\s+)?message\\s+(?:bhejna|karo)\\s+(?:ki\\s+)?(?P<message>.+)")

_rules("list_scheduled_messages", 0.95,
    r"\\b(?:what messages are scheduled|show scheduled messages|list scheduled messages)\\b",
    r"\\bscheduled messages\\s*(?:dikhao|kya hai)?\\b")

_rules("cancel_scheduled_message", 0.95,
    r"\\b(?:cancel|delete)\\s+scheduled\\s+message\\s*(?:to\\s+(?P<keyword>.+))?\\b")

_rules("approve_reply", 0.97,
    r"\\b(?:yes send it|approve reply|send the reply|approve and send|haan bhej do|bhej do reply|approve kar do)\\b")

_rules("reject_reply", 0.97,
    r"\\b(?:no don.t send|reject reply|discard reply|mat bhejo|cancel reply|discard kar do)\\b")

_rules("send_message", 0.94,"""

if old_send in content:
    content = content.replace(old_send, new_rules, 1)
    cp.write_text(content, encoding="utf-8")
    print("Updated command_parser.py with Phase 6 rules.")
else:
    print("old_send not found in command_parser.py")

# 2. Update command_executor.py
ce = Path("src/command_executor.py")
cec = ce.read_text(encoding="utf-8")

old_wa_mode = '        if intent == "set_whatsapp_mode":'
new_exec_rules = """        if intent == "schedule_whatsapp_message":
            contact = entities.get("contact", "").strip()
            message = entities.get("message", "").strip()
            time_str = entities.get("time", "").strip()
            from social_media import social_integrator
            res = social_integrator.schedule_whatsapp_message(contact, message, time_str)
            return self._resp(res)

        if intent == "list_scheduled_messages":
            from social_media import social_integrator
            return self._resp(social_integrator.list_scheduled_whatsapp())

        if intent == "cancel_scheduled_message":
            kw = entities.get("keyword") or text
            from social_media import social_integrator
            return self._resp(social_integrator.cancel_scheduled_whatsapp(kw))

        if intent == "approve_reply":
            from social_media import social_integrator
            ok, msg = social_integrator.approve_pending_reply()
            return self._resp(msg)

        if intent == "reject_reply":
            from social_media import social_integrator
            return self._resp(social_integrator.reject_pending_reply())

        if intent == "set_whatsapp_mode":"""

if old_wa_mode in cec:
    cec = cec.replace(old_wa_mode, new_exec_rules, 1)
    ce.write_text(cec, encoding="utf-8")
    print("Updated command_executor.py with Phase 6 handlers.")
else:
    print("old_wa_mode not found in command_executor.py")
