from pathlib import Path

ce = Path("src/command_executor.py")
content = ce.read_text(encoding="utf-8")

idx = content.find('if intent == "set_reminder":')
end_idx = content.find('if intent == "get_time":')

new_block = """# Reminders, Tasks, Calendar & Daily Briefing (Phase 4)
        from reminder_manager import default_reminder_manager
        rm = ctx.get("reminder_manager") or default_reminder_manager

        if intent == "set_reminder":
            r_text = entities.get("reminder_text") or entities.get("reminder") or text
            r_time = entities.get("time") or ""
            r_prio = entities.get("priority", "medium")
            r_rec  = entities.get("recurrence", "none")
            ok = rm.add_reminder(r_text, r_time, priority=r_prio, recurrence=r_rec)
            if ok:
                return self._resp(self._lang(
                    f"Reminder set for {r_text}.",
                    f"Theek hai, '{r_text}' ka reminder laga diya gaya hai.",
                    f"Reminder set: {r_text}."
                ))
            else:
                return self._resp(self._lang(
                    "Could not understand the reminder time. Please specify when.",
                    "Reminder ka samay samajh nahi aaya. Kripya samay batayein.",
                    "Could not parse the time. Please tell me when."
                ))

        if intent == "list_reminders":
            return self._resp(rm.list_reminders())

        if intent == "cancel_reminder":
            kw = entities.get("keyword") or text
            return self._resp(rm.cancel_reminder(kw))

        if intent == "add_task":
            title = entities.get("title") or text
            task_id = rm.add_task(title=title)
            return self._resp(self._lang(
                f"Added '{title}' to your task list.",
                f"'{title}' ko task list mein add kar diya gaya hai.",
                f"Task added: '{title}'."
            ))

        if intent == "list_tasks":
            tasks = rm.list_tasks(status="pending")
            if not tasks:
                return self._resp(self._lang(
                    "You have no pending tasks. Great job!",
                    "Aapke paas koi pending task nahi hai.",
                    "No pending tasks right now."
                ))
            items = [f"• {t['title']} ({t['priority']})" for t in tasks[:7]]
            body = "\\n".join(items)
            return self._resp(self._lang(
                f"Here are your pending tasks:\\n{body}",
                f"Aapke pending tasks yeh hain:\\n{body}",
                f"Your pending tasks:\\n{body}"
            ))

        if intent == "complete_task":
            target = entities.get("task") or text
            ok = rm.complete_task(target)
            if ok:
                return self._resp(self._lang(
                    f"Marked task '{target}' as completed.",
                    f"Task '{target}' complete mark ho gaya hai.",
                    f"Completed task '{target}'."
                ))
            else:
                return self._resp(self._lang(
                    f"Could not find an active task matching '{target}'.",
                    f"'{target}' se milta koi active task nahi mila.",
                    f"No pending task found matching '{target}'."
                ))

        if intent == "delete_task":
            target = entities.get("task") or text
            ok = rm.delete_task(target)
            if ok:
                return self._resp(self._lang(
                    f"Deleted task '{target}'.",
                    f"Task '{target}' delete kar diya hai.",
                    f"Deleted task '{target}'."
                ))
            else:
                return self._resp(self._lang(
                    f"Could not find task matching '{target}'.",
                    f"'{target}' se milta koi task nahi mila.",
                    f"No task found matching '{target}'."
                ))

        if intent == "create_calendar_event":
            from calendar_manager import calendar_manager
            title = entities.get("title") or "Meeting"
            time_val = entities.get("time") or ""
            res = calendar_manager.create_event(title, time_val)
            if res.get("success"):
                ev = res["event"]
                if res.get("conflicts"):
                    c_title = res["conflicts"][0]["title"]
                    return self._resp(self._lang(
                        f"Event '{title}' scheduled, but note it conflicts with existing event '{c_title}'.",
                        f"Event '{title}' schedule ho gaya, par dhyan dein yeh '{c_title}' se overlap kar raha hai.",
                        f"Scheduled '{title}', warning: overlaps with '{c_title}'."
                    ))
                return self._resp(self._lang(
                    f"Event '{title}' added to your calendar.",
                    f"Event '{title}' aapke calendar mein schedule ho gaya hai.",
                    f"Added event '{title}' to your calendar."
                ))
            else:
                err = res.get("error", "Failed to create event")
                return self._resp(self._lang(f"Could not schedule event: {err}", f"Event schedule nahi ho saka: {err}"))

        if intent == "get_calendar_events":
            from calendar_manager import calendar_manager
            agenda = calendar_manager.format_agenda_text(lang=ctx.get("language", "en"))
            return self._resp(agenda)

        if intent == "get_daily_briefing":
            from daily_briefing import daily_briefing_manager
            briefing = daily_briefing_manager.generate_briefing(user_id=user_id, language=ctx.get("language", "en"))
            return self._resp(briefing["spoken_text"])

        """

content = content[:idx] + new_block + content[end_idx:]
ce.write_text(content, encoding="utf-8")
print("Successfully updated command_executor.py with Phase 4 handlers!")
