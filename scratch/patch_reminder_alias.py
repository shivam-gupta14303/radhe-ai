from pathlib import Path

rm = Path("src/reminder_manager.py")
content = rm.read_text(encoding="utf-8")

if "reminder_manager = default_reminder_manager" not in content:
    content += "\nreminder_manager = default_reminder_manager\n"
    rm.write_text(content, encoding="utf-8")
    print("Added reminder_manager alias")
else:
    print("Already present")
