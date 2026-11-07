from pathlib import Path

cp = Path("src/command_parser.py")
content = cp.read_text(encoding="utf-8")

target = """            if intent_id == "send_message":
                c_test = (ents.get("contact") or "").lower()
                if any(w in c_test.split() for w in ("mode", "settings", "setting", "monitor", "approval")):
                    continue"""

replacement = """            if intent_id == "send_message":
                c_test = (ents.get("contact") or "").lower()
                if any(w in c_test.split() for w in ("mode", "settings", "setting", "monitor", "approval", "at", "for")):
                    continue
                if re.search(r"\\b(?:schedule|scheduled)\\b", text, re.IGNORECASE):
                    continue"""

if target in content:
    content = content.replace(target, replacement, 1)
    cp.write_text(content, encoding="utf-8")
    print("SUCCESS")
else:
    print("TARGET NOT FOUND")
