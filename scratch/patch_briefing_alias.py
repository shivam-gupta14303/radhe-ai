from pathlib import Path

db = Path("src/daily_briefing.py")
content = db.read_text(encoding="utf-8")

if "briefing_manager = daily_briefing_manager" not in content:
    content += "\nbriefing_manager = daily_briefing_manager\n"
    db.write_text(content, encoding="utf-8")
    print("Added briefing_manager alias")
else:
    print("Already present")
