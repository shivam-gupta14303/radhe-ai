import re
from pathlib import Path

# 1. Update command_parser.py
cp = Path("src/command_parser.py")
content = cp.read_text(encoding="utf-8")

old_reminders = """# Reminders
_rules("list_reminders",  0.90, r"\\b(what reminders|show reminders|list reminders|my reminders|upcoming reminders|reminders dikhao)\\b")
_rules("cancel_reminder", 0.90,
    r"\\b(cancel|delete|remove|hatao)\\s+(?:my\\s+)?(?P<keyword>[\\w\\s]+?)\\s+reminder\\b",
    r"\\breminder cancel karo\\s+(?P<keyword>[\\w\\s]+)")
_rules("set_reminder",    0.88,
    r"\\b(remind me to|set a reminder to|reminder for)\\s+(?P<reminder_text>.+?)\\s+(?:at|on|in)\\s+(?P<time>.+)",
    r"\\bremind me in\\s+(?P<time>.+?)\\s+to\s+(?P<reminder_text>.+)",
    r"\\breminder\\s+(?P<reminder_text>.+)\\s+at\\s+(?P<time>.+)",
    r"\\b(?P<time>[\\w\\s]+?)\\s+(?:ka\\s+)?alarm\\s+(?:laga|set|laga dena|lagao)\\b",
    r"\\balarm\\s+(?:laga|set|lagao)\\s+(?P<time>[\\w\\s]+)",
    r"\\balarm\\b")"""

new_tasks_and_calendar = """# Reminders, Tasks & Calendar (Phase 4)
_rules("get_daily_briefing", 0.98,
    r"\\b(?:good morning|shubh prabhat|morning briefing|daily briefing)\\b",
    r"\\b(?:what is|show|give me|tell me)\\s+(?:today.s|my)\\s+(?:briefing|schedule|agenda|day)\\b",
    r"\\baaj ka (?:schedule|plan|briefing|din) kya hai\\b")

_rules("create_calendar_event", 0.95,
    r"\\b(?:schedule|add to calendar|create event|book)\\s+(?:a\\s+)?(?:meeting|event|appointment|call)?\\s*(?:with\\s+(?P<with_whom>[\\w\\s]+?))?\\s*(?:on|at|for)\\s+(?P<time>.+)",
    r"\\b(?:calendar mein add karo|meeting schedule karo)\\s+(?P<title>.+?)(?:\\s+(?:at|on|ko)\\s+(?P<time>.+))?$",
    r"\\b(?:calendar event|add event)\\s+(?P<title>.+?)(?:\\s+(?:at|on|for)\\s+(?P<time>.+))?$")

_rules("get_calendar_events", 0.94,
    r"\\b(?:what.s on my calendar|check calendar|show calendar|calendar events|show agenda|calendar schedule)\\b",
    r"\\bcalendar\\s+(?:check karo|dekho|dikhao)\\b")

_rules("add_task", 0.94,
    r"\\b(?:add task|add to todo|add to to-do|new task)\\s+(?:to\\s+)?(?P<title>.+)",
    r"\\b(?:task add karo|naya task)\\s+(?P<title>.+)",
    r"\\b(?:add|put)\\s+(?P<title>.+?)\\s+(?:to|on)\\s+my\\s+(?:todo|tasks?|to-do)\\s+list\\b")

_rules("list_tasks", 0.94,
    r"\\b(?:what are my tasks|show tasks|list tasks|show todo|show to-do|my tasks)\\b",
    r"\\b(?:pending tasks|todo list|task list)\\s*(?:dikhao|kya hai)?\\b")

_rules("complete_task", 0.94,
    r"\\b(?:complete task|mark task as done|finish task|done with task|completed task)\\s+(?P<task>.+)",
    r"\\btask\\s+(?P<task>.+?)\\s+(?:complete|done|khatam)\\s*(?:ho gaya|karo)?\\b")

_rules("delete_task", 0.94,
    r"\\b(?:delete task|remove task)\\s+(?P<task>.+)",
    r"\\btask\\s+(?P<task>.+?)\\s+(?:delete|hata)\\s*(?:do|karo)\\b")

# Reminders
_rules("list_reminders",  0.90, r"\\b(what reminders|show reminders|list reminders|my reminders|upcoming reminders|reminders dikhao)\\b")
_rules("cancel_reminder", 0.92,
    r"\\b(?:cancel|delete|remove|hatao)\\s+(?:my\\s+)?(?:the\\s+)?reminder\\s*(?:for\\s+(?P<keyword>.+)|about\\s+(?P<keyword>.+)|(?P<alt_kw>[\\w\\s]+))?\\b",
    r"\\breminder cancel karo\\s*(?P<keyword>[\\w\\s]*)")
_rules("set_reminder",    0.88,
    r"\\b(remind me to|set a reminder to|reminder for)\\s+(?P<reminder_text>.+?)\\s+(?:at|on|in)\\s+(?P<time>.+)",
    r"\\bremind me in\\s+(?P<time>.+?)\\s+to\\s+(?P<reminder_text>.+)",
    r"\\breminder\\s+(?P<reminder_text>.+)\\s+at\\s+(?P<time>.+)",
    r"\\b(?P<time>[\\w\\s]+?)\\s+(?:ka\\s+)?alarm\\s+(?:laga|set|laga dena|lagao)\\b",
    r"\\balarm\\s+(?:laga|set|lagao)\\s+(?P<time>[\\w\\s]+)",
    r"\\balarm\\b")"""

if old_reminders in content:
    content = content.replace(old_reminders, new_tasks_and_calendar)
    print("Added Phase 4 rules to command_parser.py")
else:
    print("Could not find old_reminders in command_parser.py")

# Add entity normalization
norm_target = '    if best_intent == "forget_memory":'
norm_block = """    if best_intent == "add_task":
        t = best_entities.get("title", "")
        t = re.sub(r"^(?:that|to)\\s+", "", t, flags=re.I).strip()
        best_entities["title"] = t

    if best_intent == "complete_task":
        best_entities["task"] = best_entities.get("task", "").strip()

    if best_intent == "delete_task":
        best_entities["task"] = best_entities.get("task", "").strip()

    if best_intent == "create_calendar_event":
        w = best_entities.get("with_whom")
        if w and not best_entities.get("title"):
            best_entities["title"] = f"Meeting with {w.strip()}"
        if not best_entities.get("title"):
            best_entities["title"] = "Meeting"

    if best_intent == "cancel_reminder":
        kw = best_entities.get("keyword") or best_entities.get("alt_kw") or ""
        best_entities["keyword"] = kw.strip()

    if best_intent == "forget_memory":"""

if norm_target in content:
    content = content.replace(norm_target, norm_block, 1)
    print("Added Phase 4 entity normalizations to command_parser.py")

cp.write_text(content, encoding="utf-8")
