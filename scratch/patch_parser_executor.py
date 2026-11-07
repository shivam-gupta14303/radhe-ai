from pathlib import Path

# 1. command_parser.py
cp = Path("src/command_parser.py")
content = cp.read_text(encoding="utf-8")

old_rules = """# Memory Management & Recall
_rules("remember_fact", 0.95,
    r"\\b(?:remember|note down|save to memory|yad rakhna|yaad rakhna)\\s+(?:that\\s+)?(?P<fact>.+)",
    r"\\b(?:yad|yaad)\\s+rakho\\s+(?:ki\\s+)?(?P<fact>.+)",
    r"\\bmera\\s+(?P<fact>.+?)\\s+(?:yaad|yad)\\s+rakhna\\b")

_rules("recall_memory", 0.94,
    r"\\b(?:what do you remember|what do you know|recall|show memories|list memories)\\s*(?:about\\s+(?P<query>.+))?\\b",
    r"\\b(?:kya yaad hai|meri memories|kya jante ho)\\s*(?:mere bare mein|about\\s+(?P<query>.+))?\\b",
    r"\\b(?:what are my|show my|tell me my)\\s+(?:preferences|memories|profile|saved facts)\\b")"""

new_rules = """# Memory Management & Recall
_rules("recall_memory", 0.99,
    r"\\b(?:what do you remember|what do you know|recall|show memories|list memories)\\s*(?:about\\s+(?P<query>.+))?\\b",
    r"\\b(?:kya yaad hai|meri memories|kya jante ho)\\s*(?:mere bare mein|about\\s+(?P<query>.+))?\\b",
    r"\\b(?:what are my|show my|tell me my)\\s+(?:preferences|memories|profile|saved facts)\\b")

_rules("remember_fact", 0.95,
    r"(?<!what do you )(?<!do you )\\b(?:remember|note down|save to memory|yad rakhna|yaad rakhna)\\s+(?:that\\s+)?(?P<fact>.+)",
    r"\\b(?:yad|yaad)\\s+rakho\\s+(?:ki\\s+)?(?P<fact>.+)",
    r"\\bmera\\s+(?P<fact>.+?)\\s+(?:yaad|yad)\\s+rakhna\\b")"""

content = content.replace(old_rules, new_rules)
cp.write_text(content, encoding="utf-8")
print("Updated command_parser rules.")

# 2. command_executor.py
ce = Path("src/command_executor.py")
cec = ce.read_text(encoding="utf-8")
old_resp = 'return {"text": text, "voice": text}'
new_resp = 'return {"text": text, "voice": text, "response": text, "success": True}'

if old_resp in cec:
    cec = cec.replace(old_resp, new_resp, 1)
    ce.write_text(cec, encoding="utf-8")
    print("Updated command_executor _resp.")
else:
    print("command_executor _resp already updated or not found")
