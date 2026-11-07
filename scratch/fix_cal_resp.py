from pathlib import Path

ce = Path("src/command_executor.py")
content = ce.read_text(encoding="utf-8")

old_text = "Event '{title}' scheduled, but note it conflicts with existing event '{c_title}'."
new_text = "Event '{title}' added to your calendar, but note it conflicts with existing event '{c_title}'."

if old_text in content:
    content = content.replace(old_text, new_text, 1)
    ce.write_text(content, encoding="utf-8")
    print("Updated conflict response string in command_executor.py")
else:
    print("old_text not found")
