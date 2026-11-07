from pathlib import Path

cp = Path("src/command_parser.py")
content = cp.read_text(encoding="utf-8")

old_cancel = """_rules("cancel_reminder", 0.92,
    r"\\b(?:cancel|delete|remove|hatao)\\s+(?:my\\s+)?(?:the\\s+)?reminder\\s*(?:for\\s+(?P<keyword>.+)|about\\s+(?P<keyword>.+)|(?P<alt_kw>[\\w\\s]+))?\\b",
    r"\\breminder cancel karo\\s*(?P<keyword>[\\w\\s]*)")"""

new_cancel = """_rules("cancel_reminder", 0.92,
    r"\\b(?:cancel|delete|remove|hatao)\\s+(?:my\\s+)?(?:the\\s+)?reminder\\s+for\\s+(?P<keyword>.+)",
    r"\\b(?:cancel|delete|remove|hatao)\\s+(?:my\\s+)?(?:the\\s+)?reminder\\s+about\\s+(?P<keyword>.+)",
    r"\\b(?:cancel|delete|remove|hatao)\\s+(?:my\\s+)?(?P<keyword>[\\w\\s]+?)\\s+reminder\\b",
    r"\\breminder cancel karo\\s*(?P<keyword>[\\w\\s]*)")"""

if old_cancel in content:
    content = content.replace(old_cancel, new_cancel, 1)
    cp.write_text(content, encoding="utf-8")
    print("Fixed cancel_reminder regex in command_parser.py")
else:
    print("old_cancel not found")
