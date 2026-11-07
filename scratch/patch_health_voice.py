from pathlib import Path

# 1. Update command_parser.py
cp = Path("src/command_parser.py")
content = cp.read_text(encoding="utf-8")

old_marker = '# WhatsApp & Social Messaging (Phase 6)'
new_rules = """# Personal Health Assistant (Phase 9)
_rules("log_water_intake", 0.96,
    r"\\b(?:log|drank|had)\\s+(?P<amount>\\d+)\\s*(?P<unit>ml|l|liters?|glasses?|glass)?\\s*(?:of\\s+)?water\\b",
    r"\\b(?P<amount>\\d+)\\s*(?P<unit>ml|l|liters?|glass|glasses)?\\s*paani\\s+(?:piya|pi liya|log karo)\\b",
    r"\\bpaani\\s+piya\\s+(?P<amount>\\d+)\\s*(?P<unit>ml|l|glass)?\\b")

_rules("get_water_intake", 0.95,
    r"\\b(?:how much water did i drink|what is my water intake|water status|check water)\\b",
    r"\\baaj\\s+(?:kitna\\s+)?paani\\s+piya\\b")

_rules("log_vital_sign", 0.95,
    r"\\blog\\s+(?:my\\s+)?(?:blood\\s+pressure|bp)\\s+(?P<systolic>\\d+)\\s*(?:over|/)\\s*(?P<diastolic>\\d+)\\b",
    r"\\blog\\s+(?:my\\s+)?(?:glucose|sugar)\\s+(?P<value>\\d+)\\b",
    r"\\blog\\s+(?:my\\s+)?(?:weight)\\s+(?P<value>\\d+(?:\\.\\d+)?)\\s*(?P<unit>kg|lbs)?\\b")

_rules("take_medication", 0.96,
    r"\\b(?:took|taken|le li)\\s+(?:my\\s+)?(?:medication|medicine|pill|dawa|dawai)\\s*(?P<name>[A-Za-z0-9_-]+)?\\b",
    r"\\b(?P<name>[A-Za-z0-9_-]+)\\s+(?:dawai|medicine|pill)\\s+le\\s+li\\b")

_rules("list_medications", 0.95,
    r"\\b(?:what medicines do i have|list my medications|show medicines|my medications)\\b",
    r"\\bmeri\\s+(?:dawaiyan|medicines)\\s*(?:dikhao|kya hain)?\\b")

# WhatsApp & Social Messaging (Phase 6)"""

if old_marker in content and "log_water_intake" not in content:
    content = content.replace(old_marker, new_rules, 1)
    cp.write_text(content, encoding="utf-8")
    print("SUCCESS: Added Health rules to command_parser.py")
else:
    print("ALREADY PRESENT OR NOT FOUND in parser")

# 2. Update command_executor.py
ce = Path("src/command_executor.py")
cec = ce.read_text(encoding="utf-8")

old_exec = '        if intent == "schedule_whatsapp_message":'
new_exec = """        if intent == "log_water_intake":
            from health_assistant import health_assistant
            raw_amt = entities.get("amount", "250")
            unit = entities.get("unit", "ml").lower()
            try:
                amt = float(raw_amt)
                if "glass" in unit:
                    amt *= 250.0
                elif "l" in unit and unit != "ml":
                    amt *= 1000.0
            except Exception:
                amt = 250.0
            _, msg = health_assistant.log_water(amt, user_id=user_id)
            return self._resp(msg)

        if intent == "get_water_intake":
            from health_assistant import health_assistant
            total = health_assistant.get_daily_water_total(user_id=user_id)
            return self._resp(f"You have consumed {int(total)}ml of water today out of your 2500ml goal.")

        if intent == "log_vital_sign":
            from health_assistant import health_assistant
            if "systolic" in entities and "diastolic" in entities:
                sys_v = float(entities["systolic"])
                dia_v = float(entities["diastolic"])
                health_assistant.log_vital("systolic", sys_v, unit="mmHg", user_id=user_id)
                health_assistant.log_vital("diastolic", dia_v, unit="mmHg", user_id=user_id)
                return self._resp(f"Logged blood pressure: {int(sys_v)}/{int(dia_v)} mmHg.")
            metric = "glucose" if "glucose" in text.lower() or "sugar" in text.lower() else "weight"
            val = float(entities.get("value", 0))
            health_assistant.log_vital(metric, val, user_id=user_id)
            return self._resp(f"Logged {metric}: {val}.")

        if intent == "take_medication":
            from health_assistant import health_assistant
            med_name = entities.get("name") or "medication"
            ok, msg = health_assistant.log_medication_taken(med_name, user_id=user_id)
            return self._resp(msg)

        if intent == "list_medications":
            from health_assistant import health_assistant
            meds = health_assistant.list_medications(active_only=True, user_id=user_id)
            if not meds:
                return self._resp("You have no active medications registered.")
            lines = [f"• {m['name']} ({m['dosage']}) at {m['schedule_time']} [{m['remaining_doses']} doses left]" for m in meds]
            return self._resp("Your active medications:\\n" + "\\n".join(lines))

        if intent == "schedule_whatsapp_message":"""

if old_exec in cec and "log_water_intake" not in cec:
    cec = cec.replace(old_exec, new_exec, 1)
    ce.write_text(cec, encoding="utf-8")
    print("SUCCESS: Added Health handlers to command_executor.py")
else:
    print("ALREADY PRESENT OR NOT FOUND in executor")
