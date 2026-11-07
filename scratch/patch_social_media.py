from pathlib import Path

sm = Path("src/social_media.py")
content = sm.read_text(encoding="utf-8")

old_get_appr = """    def get_pending_approvals(self) -> list:
        \"\"\"Return list of pending approval drafts.\"\"\"
        if self._executor_ref and self._executor_ref.context.get("pending_whatsapp_approval"):
            appr = self._executor_ref.context["pending_whatsapp_approval"]
            return [{
                "contact": appr.get("sender"),
                "incoming": appr.get("message"),
                "draft": appr.get("draft")
            }]
        return []"""

new_methods = """    def get_pending_approvals(self) -> list:
        \"\"\"Return list of pending approval drafts.\"\"\"
        if self._executor_ref and self._executor_ref.context.get("pending_whatsapp_approval"):
            appr = self._executor_ref.context["pending_whatsapp_approval"]
            draft_text = appr.get("reply") or appr.get("draft") or ""
            return [{
                "contact": appr.get("sender"),
                "incoming": appr.get("message"),
                "draft": draft_text
            }]
        return []

    def approve_pending_reply(self) -> tuple[bool, str]:
        \"\"\"Approve and dispatch the pending staged WhatsApp reply.\"\"\"
        if not self._executor_ref or not self._executor_ref.context.get("pending_whatsapp_approval"):
            return False, "No pending message draft to approve."

        appr = self._executor_ref.context["pending_whatsapp_approval"]
        sender = appr.get("sender")
        reply = appr.get("reply") or appr.get("draft")

        ok = self.whatsapp.send_to_contact_name(sender, reply)
        self._executor_ref.context["pending_whatsapp_approval"] = None
        self._executor_ref.context["awaiting_whatsapp_approval"] = False

        if ok:
            return True, f"Sent approved reply to {sender}: '{reply}'."
        return False, f"Failed to send approved reply to {sender} via WhatsApp."

    def reject_pending_reply(self) -> str:
        \"\"\"Discard the pending staged WhatsApp reply.\"\"\"
        if not self._executor_ref or not self._executor_ref.context.get("pending_whatsapp_approval"):
            return "No pending message draft to discard."

        appr = self._executor_ref.context["pending_whatsapp_approval"]
        sender = appr.get("sender")
        self._executor_ref.context["pending_whatsapp_approval"] = None
        self._executor_ref.context["awaiting_whatsapp_approval"] = False
        return f"Discarded drafted reply for {sender}."

    def edit_pending_reply(self, new_reply_text: str) -> str:
        \"\"\"Update the text of a pending draft before sending.\"\"\"
        if not self._executor_ref or not self._executor_ref.context.get("pending_whatsapp_approval"):
            return "No pending message draft to edit."

        appr = self._executor_ref.context["pending_whatsapp_approval"]
        appr["reply"] = new_reply_text.strip()
        appr["draft"] = new_reply_text.strip()
        sender = appr.get("sender")
        return f"Updated draft for {sender} to: '{new_reply_text}'. Should I send it now?"

    def check_and_dispatch_scheduled_messages(self) -> int:
        \"\"\"Process any scheduled messages that are now due.\"\"\"
        due = contact_manager.get_due_messages()
        sent_count = 0
        for m in due:
            try:
                ok = self.whatsapp.send_to_contact_name(m["recipient"], m["message"])
                if ok:
                    contact_manager.mark_message_sent(m["id"])
                    sent_count += 1
                    logger.info("Dispatched scheduled message id=%d to %s", m["id"], m["recipient"])
            except Exception as e:
                logger.warning("Error dispatching scheduled message id=%d: %s", m["id"], e)
        return sent_count

    def schedule_whatsapp_message(self, recipient: str, message: str, time_str: str) -> str:
        \"\"\"Schedule a WhatsApp message for future delivery.\"\"\"
        mid = contact_manager.schedule_message(recipient, message, time_str, platform="whatsapp")
        if mid > 0:
            return f"Scheduled WhatsApp message to {recipient} at {time_str}."
        return f"Could not parse the scheduled time '{time_str}'. Please specify when to send it."

    def list_scheduled_whatsapp(self) -> str:
        \"\"\"Return human-readable list of pending scheduled messages.\"\"\"
        msgs = contact_manager.list_scheduled_messages(status="pending")
        if not msgs:
            return "You have no scheduled WhatsApp messages."
        lines = []
        for m in msgs:
            t = m["scheduled_time"][:16].replace("T", " ")
            lines.append(f"• To {m['recipient']}: '{m['message']}' at {t}")
        return "Upcoming scheduled WhatsApp messages:\n" + "\n".join(lines)

    def cancel_scheduled_whatsapp(self, keyword: str) -> str:
        \"\"\"Cancel a pending scheduled message by recipient or ID.\"\"\"
        ok = contact_manager.cancel_scheduled_message(keyword)
        if ok:
            return f"Cancelled scheduled message matching '{keyword}'."
        return f"No pending scheduled message found matching '{keyword}'."
"""

if old_get_appr in content:
    content = content.replace(old_get_appr, new_methods, 1)
    sm.write_text(content, encoding="utf-8")
    print("Updated social_media.py with approval workflows and message scheduling.")
else:
    print("old_get_appr not found in social_media.py")
