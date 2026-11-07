import re
from pathlib import Path

p = Path("src/command_parser.py")
content = p.read_text(encoding="utf-8")

# 1. Add rules for memory
old_rule = '_rules("test_ai_connection", 0.98,\n    r"\\b(?:test|check)\\s+(?:ai\\s+)?(?:connection|health|api)\\b",\n    r"\\bai\\s+(?:connection|api)\\s+test\\s*(?:karo)?\\b")'
if old_rule not in content:
    old_rule = '_rules("test_ai_connection", 0.98,\r\n    r"\\b(?:test|check)\\s+(?:ai\\s+)?(?:connection|health|api)\\b",\r\n    r"\\bai\\s+(?:connection|api)\\s+test\\s*(?:karo)?\\b")'

new_rules = """_rules("test_ai_connection", 0.98,
    r"\\b(?:test|check)\\s+(?:ai\\s+)?(?:connection|health|api)\\b",
    r"\\bai\\s+(?:connection|api)\\s+test\\s*(?:karo)?\\b")

# Memory Management & Recall
_rules("remember_fact", 0.95,
    r"\\b(?:remember|note down|save to memory|yad rakhna|yaad rakhna)\\s+(?:that\\s+)?(?P<fact>.+)",
    r"\\b(?:yad|yaad)\\s+rakho\\s+(?:ki\\s+)?(?P<fact>.+)",
    r"\\bmera\\s+(?P<fact>.+?)\\s+(?:yaad|yad)\\s+rakhna\\b")

_rules("recall_memory", 0.94,
    r"\\b(?:what do you remember|what do you know|recall|show memories|list memories)\\s*(?:about\\s+(?P<query>.+))?\\b",
    r"\\b(?:kya yaad hai|meri memories|kya jante ho)\\s*(?:mere bare mein|about\\s+(?P<query>.+))?\\b",
    r"\\b(?:what are my|show my|tell me my)\\s+(?:preferences|memories|profile|saved facts)\\b")

_rules("forget_memory", 0.95,
    r"\\b(?:forget|delete memory|remove memory|bhul jao|bhula do)\\s*(?:about\\s+)?(?P<query>.+)?\\b",
    r"\\b(?:clear|delete)\\s+(?:all\\s+)?memories\\b")

_rules("export_memory", 0.96,
    r"\\b(?:export|backup|download)\\s+(?:my\\s+)?(?:data|memories|profile|memory)\\b",
    r"\\b(?:data|memories)\\s+export\\s*(?:karo)?\\b")"""

if old_rule in content:
    content = content.replace(old_rule, new_rules)
    print("Added memory rules successfully.")
else:
    print("Could not find old_rule!")

# 2. Add normalization and deduplicate set_whatsapp_mode
dup_pattern = r'(    if best_intent == "set_whatsapp_mode":[\s\S]+?best_entities\["mode"\] = mode_val\n)+'
match = re.search(dup_pattern, content)
if match:
    single_block = """    if best_intent == "set_whatsapp_mode":
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
        best_entities["mode"] = mode_val

    if best_intent == "remember_fact":
        f = best_entities.get("fact", "")
        f = re.sub(r"^(?:that|ki)\\s+", "", f, flags=re.I).strip()
        best_entities["fact"] = f

    if best_intent == "recall_memory":
        q = best_entities.get("query", "")
        q = re.sub(r"^(?:about|mere baare mein|mere bare mein)\\s+", "", q, flags=re.I).strip()
        best_entities["query"] = q

    if best_intent == "forget_memory":
        q = best_entities.get("query", "")
        q = re.sub(r"^(?:about|that|ki)\\s+", "", q, flags=re.I).strip()
        best_entities["query"] = q
"""
    content = content[:match.start()] + single_block + content[match.end():]
    print("Normalized and deduplicated set_whatsapp_mode and added memory entities.")

p.write_text(content, encoding="utf-8")
print("Updated command_parser.py successfully.")
