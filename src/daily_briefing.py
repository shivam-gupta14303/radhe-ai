# daily_briefing.py
"""
DailyBriefing — Morning briefing and proactive daily overview for Radhe.

Aggregates:
- User profile & personalized greeting.
- Current date, time, and day.
- Today's calendar schedule from CalendarManager.
- Urgent & high-priority pending tasks from ReminderManager.
- Upcoming reminders due today.
- WhatsApp unread messages overview from SocialMediaIntegrator.
- Warm closing thought.
"""

import datetime
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("Radhe_DailyBriefing")
logger.setLevel(logging.INFO)


class DailyBriefingManager:

    def __init__(self):
        pass

    def generate_briefing(
        self,
        user_id: str = "default",
        language: str = "en",
        memory_mgr: Optional[Any] = None,
        calendar_mgr: Optional[Any] = None,
        reminder_mgr: Optional[Any] = None
    ) -> Dict[str, Any]:
        """Compile complete daily briefing data from memory, calendar, and tasks."""
        now = datetime.datetime.now()
        date_str = now.strftime("%A, %d %B %Y")
        time_str = now.strftime("%I:%M %p")

        # 1. User Name & Profile
        user_name = "there"
        try:
            m_mgr = memory_mgr
            if not m_mgr:
                from memory import memory_manager as m_mgr
            prof_name = m_mgr.get_profile_value("user_name", user_id=user_id)
            if prof_name:
                user_name = str(prof_name)
        except Exception as e:
            logger.debug("Briefing profile fetch skipped: %s", e)

        # 2. Calendar Agenda
        agenda = []
        try:
            from calendar_manager import calendar_manager
            agenda = calendar_manager.get_today_agenda()
        except Exception as e:
            logger.debug("Briefing calendar fetch skipped: %s", e)

        # 3. Tasks
        tasks = []
        try:
            from reminder_manager import default_reminder_manager
            tasks = default_reminder_manager.list_tasks(status="pending", limit=5)
        except Exception as e:
            logger.debug("Briefing tasks fetch skipped: %s", e)

        # 4. Reminders
        reminders = []
        try:
            from reminder_manager import default_reminder_manager
            raw_rems = default_reminder_manager.get_upcoming_reminders(limit=5)
            today_str = now.strftime("%Y-%m-%d")
            for rid, t_name, due in raw_rems:
                if due.startswith(today_str):
                    reminders.append({"id": rid, "task": t_name, "due_time": due})
        except Exception as e:
            logger.debug("Briefing reminders fetch skipped: %s", e)

        # 5. WhatsApp Status
        whatsapp_mode = "monitor"
        unread_count = 0
        try:
            from social_media import social_integrator
            whatsapp_mode = social_integrator.get_mode()
            if social_integrator.whatsapp and social_integrator.whatsapp.driver:
                unread = social_integrator.whatsapp.get_unread_chats()
                unread_count = len(unread)
        except Exception:
            pass

        data = {
            "user_name": user_name,
            "date": date_str,
            "time": time_str,
            "agenda": agenda,
            "pending_tasks": tasks,
            "reminders": reminders,
            "whatsapp_mode": whatsapp_mode,
            "unread_whatsapp_count": unread_count,
        }

        spoken_text = self._format_spoken_text(data, language)
        data["spoken_text"] = spoken_text
        return data

    def _format_spoken_text(self, data: Dict[str, Any], language: str) -> str:
        """Format briefing into natural speech based on language."""
        name = data["user_name"]
        date_str = data["date"]
        agenda = data["agenda"]
        tasks = data["pending_tasks"]
        reminders = data["reminders"]

        if language == "hi":
            # Hindi Briefing
            greeting = f"Shubh prabhat {name if name != 'there' else ''}! Aaj {date_str} hai."
            lines = [greeting]

            if agenda:
                lines.append(f"Aaj aapke schedule mein {len(agenda)} events hain.")
                for ev in agenda[:3]:
                    lines.append(f"• {ev['title']}")
            else:
                lines.append("Aaj aapka calendar bilkul free hai.")

            urgent_tasks = [t for t in tasks if t.get("priority") in ("high", "urgent")]
            if urgent_tasks:
                lines.append(f"Aapke paas {len(urgent_tasks)} zaroori tasks pending hain: {urgent_tasks[0]['title']}.")
            elif tasks:
                lines.append(f"Aapke to-do list mein {len(tasks)} tasks hain.")

            if reminders:
                lines.append(f"Aaj ke liye {len(reminders)} reminders scheduled hain.")

            lines.append("Aapka din shubh ho! Agar kisi cheez ki zaroorat ho toh batana.")
            return " ".join(lines)

        elif language == "mixed":
            # Hinglish Briefing
            greeting = f"Good morning {name if name != 'there' else ''}! Aaj {date_str} hai."
            lines = [greeting]

            if agenda:
                lines.append(f"Aaj aapke calendar mein {len(agenda)} events hain.")
                for ev in agenda[:3]:
                    lines.append(f"• {ev['title']}")
            else:
                lines.append("Calendar completely free hai aaj.")

            urgent_tasks = [t for t in tasks if t.get("priority") in ("high", "urgent")]
            if urgent_tasks:
                lines.append(f"Aapke {len(urgent_tasks)} priority tasks hain: {urgent_tasks[0]['title']}.")
            elif tasks:
                lines.append(f"{len(tasks)} tasks pending hain aapki list mein.")

            if reminders:
                lines.append(f"Aaj ke {len(reminders)} reminders set hain.")

            lines.append("Have a great day ahead! Main yahin hoon agar kuch chahiye.")
            return " ".join(lines)

        else:
            # English Briefing
            greeting = f"Good morning, {name}! Today is {date_str}."
            lines = [greeting]

            if agenda:
                ev_str = ", ".join(ev['title'] for ev in agenda[:3])
                lines.append(f"You have {len(agenda)} scheduled events today: {ev_str}.")
            else:
                lines.append("Your calendar is completely open today.")

            urgent_tasks = [t for t in tasks if t.get("priority") in ("high", "urgent")]
            if urgent_tasks:
                lines.append(f"You have {len(urgent_tasks)} high-priority tasks pending, starting with: {urgent_tasks[0]['title']}.")
            elif tasks:
                lines.append(f"You have {len(tasks)} tasks pending on your to-do list.")

            if reminders:
                lines.append(f"{len(reminders)} reminders are set for today.")

            lines.append("Have a wonderful and productive day ahead! Let me know if you need anything.")
            return " ".join(lines)


# ── Global singleton ───────────────────────────────────────────────────
daily_briefing_manager = DailyBriefingManager()

briefing_manager = daily_briefing_manager
