# social_media.py
"""
SocialMediaIntegrator for Radhe.

Handles WhatsApp actions:
- send_whatsapp_by_contact (resolves via phone or UI search)
- send_whatsapp_by_number
- start_whatsapp
- listen_whatsapp (background listener with modes: Monitor, Approval, Auto-reply)
- Three operational modes:
    * Monitor:    Reads incoming messages but never replies.
    * Approval:   Generates an intelligent reply draft and prompts the user for approval.
    * Auto-reply: Replies automatically only when explicitly enabled.
"""

import logging
import time
from typing import Optional, Callable, Union, Dict, Any

from contact_manager import contact_manager
from whatsapp_manager import whatsapp_manager
from config import CONTACTS_DB_FILE

logger = logging.getLogger("Radhe_SocialInt")
logger.setLevel(logging.INFO)

MODE_MONITOR    = "monitor"
MODE_APPROVAL   = "approval"
MODE_AUTO_REPLY = "auto_reply"
VALID_MODES     = {MODE_MONITOR, MODE_APPROVAL, MODE_AUTO_REPLY}


class SocialMediaIntegrator:

    def __init__(self):
        self.whatsapp = whatsapp_manager
        self._executor_ref = None
        self._speak_cb: Optional[Callable[[str], None]] = None
        self.mode: str = MODE_MONITOR

    # ==================================================================
    # MODE MANAGEMENT
    # ==================================================================

    def set_mode(self, mode: str) -> str:
        """
        Set WhatsApp operational mode.
        Supported modes:
          - monitor:    Reads incoming messages, never replies.
          - approval:   Drafts reply, asks user for confirmation before sending.
          - auto_reply: Automatically replies without asking.
        """
        clean_mode = str(mode or "").strip().lower().replace("-", "_").replace(" ", "_")
        if clean_mode in ("auto", "autoreply", "auto_reply"):
            clean_mode = MODE_AUTO_REPLY
        elif clean_mode in ("approve", "approval"):
            clean_mode = MODE_APPROVAL
        elif clean_mode in ("monitor", "monitoring", "read_only"):
            clean_mode = MODE_MONITOR

        if clean_mode not in VALID_MODES:
            return f"Invalid mode '{mode}'. Choose from: monitor, approval, or auto-reply."

        self.mode = clean_mode
        logger.info("SocialMediaIntegrator mode updated to '%s'", self.mode)

        if self.mode == MODE_MONITOR:
            return "WhatsApp mode set to Monitor. I will read incoming messages but never reply."
        elif self.mode == MODE_APPROVAL:
            return "WhatsApp mode set to Approval. I will generate replies and ask your confirmation before sending."
        else:
            return "WhatsApp mode set to Auto-reply. I will automatically send replies to incoming messages."

    def get_mode(self) -> str:
        """Get current WhatsApp operational mode."""
        return self.mode

    def set_speak_callback(self, callback: Callable[[str], None]) -> None:
        """Set speech callback for voice announcements."""
        self._speak_cb = callback

    # ==================================================================
    # WHATSAPP SEND
    # ==================================================================

    def send_whatsapp_by_contact(
        self,
        contact: Union[str, Dict[str, Any], list],
        message: str
    ) -> str:
        """
        Send a WhatsApp message.
        Accepts: name string, contact dict, or single-element list.
        """
        if not message:
            return "Message is empty."

        if isinstance(contact, list):
            contact = contact[0] if contact else ""

        name = ""
        phone = ""

        if isinstance(contact, dict):
            name = contact.get("name", "unknown")
            phone = contact.get("phone", "")
        elif isinstance(contact, str):
            name = contact.strip()
            if not name:
                return "No contact name provided."
            c = contact_manager.get_contact(name)
            if c:
                phone = (c.get("phone") or "").strip()
        else:
            return "Invalid contact format."

        # If phone found, try sending via phone
        if phone:
            ok = self.whatsapp.send_message(phone, message)
            if ok:
                return f"Message sent to {name} on WhatsApp."

        # Fallback to direct name search on WhatsApp Web
        ok = self.whatsapp.send_via_chat_search(name, message)
        if ok:
            return f"Message sent to {name} on WhatsApp."

        return f"Could not send WhatsApp message to {name}. Please check if WhatsApp Web is open and logged in."

    def send_whatsapp_by_number(self, phone: str, message: str) -> str:
        """Send directly to a phone number."""
        if not phone:
            return "No phone number provided."
        if not message:
            return "Message is empty."
        ok = self.whatsapp.send_message(phone, message)
        return "Message sent via WhatsApp." if ok else "Failed to send WhatsApp message. Please check number and connection."

    # ==================================================================
    # WHATSAPP SESSION
    # ==================================================================

    def start_whatsapp(self) -> str:
        """Open WhatsApp Web."""
        try:
            ok = self.whatsapp.start(wait_for_login=False)
            if ok:
                if self.whatsapp.is_logged_in():
                    return "WhatsApp Web is open and ready."
                return "WhatsApp Web opened. Please scan the QR code if you haven't logged in yet."
            return "Could not open WhatsApp Web. Please check Chrome."
        except Exception as e:
            logger.exception("start_whatsapp failed: %s", e)
            return f"Could not start WhatsApp Web: {e}"

    # ==================================================================
    # REPLY GENERATOR
    # ==================================================================

    def generate_reply(self, sender: str, message: str) -> str:
        """Generate a context-aware reply for incoming messages."""
        # 1. Try parsing through executor if it's an actionable query
        if self._executor_ref is not None:
            try:
                from command_parser import CommandParser
                parser = CommandParser()
                parsed = parser.parse(message)
                intent = parsed.get("intent", "none")
                if intent not in ("none", "unknown", "greeting", "chitchat"):
                    result = self._executor_ref.execute(parsed, message)
                    reply = result.get("text") or result.get("voice") or ""
                    if reply and not reply.startswith("Could not"):
                        return reply
            except Exception as e:
                logger.debug("Executor reply generation error: %s", e)

        # 2. Try LLM generation
        try:
            import llm_setup
            prompt = (
                f"You are Radhe assisting the user. Generate a brief, natural, and helpful WhatsApp reply "
                f"to this incoming message from '{sender}': '{message}'. Keep it concise (1-2 sentences)."
            )
            llm_reply = llm_setup.llm_engine.generate(prompt, {"language": "en", "mode": "casual"})
            if llm_reply and len(llm_reply.strip()) > 1:
                return llm_reply.strip().strip('"')
        except Exception as e:
            logger.debug("LLM reply generation error: %s", e)

        # 3. Fallback
        return f"Hi {sender}, I received your message: '{message}'. Will get back to you shortly."

    # ==================================================================
    # INCOMING MESSAGE LISTENER & MODE HANDLER
    # ==================================================================

    def listen_whatsapp(
        self,
        callback: Optional[Callable[[str, str], None]] = None
    ) -> str:
        """
        Start listening for incoming WhatsApp messages.
        Non-blocking: starts in background.
        """
        cb = callback or self._default_incoming_handler

        try:
            # Start Chrome if not running, but do not block for QR scan
            if not self.whatsapp.is_running():
                self.whatsapp.start(wait_for_login=False)
            self.whatsapp.set_incoming_callback(cb)
            self.whatsapp.listen_incoming()
            return f"WhatsApp listener active in {self.mode} mode."
        except Exception as e:
            logger.exception("listen_whatsapp failed: %s", e)
            return f"Failed to start WhatsApp listener: {e}"

    def _default_incoming_handler(self, sender: str, snippet: str):
        """
        Incoming WhatsApp message handler with 3 modes:
          - Monitor: Log & announce only, never replies.
          - Approval: Generate reply, stage in executor context, ask user approval.
          - Auto-reply: Generate reply and send automatically.
        """
        logger.info("WhatsApp [%s] from %s: %s", self.mode.upper(), sender, snippet)

        if self.mode == MODE_MONITOR:
            # Reads incoming messages but never replies
            announcement = f"New WhatsApp message from {sender}: {snippet}"
            logger.info("WhatsApp Monitor: %s", announcement)
            if self._speak_cb:
                try:
                    self._speak_cb(announcement)
                except Exception as e:
                    logger.warning("Speech callback failed: %s", e)
            return

        if self.mode == MODE_APPROVAL:
            # Generates a reply and asks the user before sending
            reply = self.generate_reply(sender, snippet)
            logger.info("WhatsApp Approval draft for %s: %s", sender, reply)

            if self._executor_ref is not None:
                self._executor_ref.context["pending_whatsapp_approval"] = {
                    "sender": sender,
                    "message": snippet,
                    "reply": reply,
                    "timestamp": time.time(),
                }
                self._executor_ref.context["awaiting_whatsapp_approval"] = True

            question = f"New WhatsApp message from {sender}: '{snippet}'. I drafted a reply: '{reply}'. Should I send it?"
            if self._speak_cb:
                try:
                    self._speak_cb(question)
                except Exception as e:
                    logger.warning("Speech callback failed: %s", e)
            return

        if self.mode == MODE_AUTO_REPLY:
            # Replies automatically when explicitly enabled
            reply = self.generate_reply(sender, snippet)
            ok = self.whatsapp.send_to_contact_name(sender, reply)
            if ok:
                logger.info("Auto-replied to %s: %s", sender, reply)
                if self._speak_cb:
                    try:
                        self._speak_cb(f"Received WhatsApp from {sender}. Auto-replied: {reply}")
                    except Exception as e:
                        logger.warning("Speech callback failed: %s", e)
            else:
                logger.warning("Auto-reply to %s could not be sent.", sender)
            return

    def get_pending_approvals(self) -> list:
        """Return list of pending approval drafts."""
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
        """Approve and dispatch the pending staged WhatsApp reply."""
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
        """Discard the pending staged WhatsApp reply."""
        if not self._executor_ref or not self._executor_ref.context.get("pending_whatsapp_approval"):
            return "No pending message draft to discard."

        appr = self._executor_ref.context["pending_whatsapp_approval"]
        sender = appr.get("sender")
        self._executor_ref.context["pending_whatsapp_approval"] = None
        self._executor_ref.context["awaiting_whatsapp_approval"] = False
        return f"Discarded drafted reply for {sender}."

    def edit_pending_reply(self, new_reply_text: str) -> str:
        """Update the text of a pending draft before sending."""
        if not self._executor_ref or not self._executor_ref.context.get("pending_whatsapp_approval"):
            return "No pending message draft to edit."

        appr = self._executor_ref.context["pending_whatsapp_approval"]
        appr["reply"] = new_reply_text.strip()
        appr["draft"] = new_reply_text.strip()
        sender = appr.get("sender")
        return f"Updated draft for {sender} to: '{new_reply_text}'. Should I send it now?"

    def check_and_dispatch_scheduled_messages(self) -> int:
        """Process any scheduled messages that are now due."""
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
        """Schedule a WhatsApp message for future delivery."""
        mid = contact_manager.schedule_message(recipient, message, time_str, platform="whatsapp")
        if mid > 0:
            return f"Scheduled WhatsApp message to {recipient} at {time_str}."
        return f"Could not parse the scheduled time '{time_str}'. Please specify when to send it."

    def list_scheduled_whatsapp(self) -> str:
        """Return human-readable list of pending scheduled messages."""
        msgs = contact_manager.list_scheduled_messages(status="pending")
        if not msgs:
            return "You have no scheduled WhatsApp messages."
        lines = []
        for m in msgs:
            t = m["scheduled_time"][:16].replace("T", " ")
            lines.append(f"• To {m['recipient']}: '{m['message']}' at {t}")
        return "Upcoming scheduled WhatsApp messages:\n" + "\n".join(lines)

    def cancel_scheduled_whatsapp(self, keyword: str) -> str:
        """Cancel a pending scheduled message by recipient or ID."""
        ok = contact_manager.cancel_scheduled_message(keyword)
        if ok:
            return f"Cancelled scheduled message matching '{keyword}'."
        return f"No pending scheduled message found matching '{keyword}'."


    def connect_executor(self, executor_instance) -> None:
        """Connect Radhe's executor for approvals and auto-replies."""
        self._executor_ref = executor_instance
        logger.info("Executor connected to SocialMediaIntegrator.")

    def stop(self) -> None:
        """Stop WhatsApp Web session and incoming listener."""
        try:
            self.whatsapp.stop()
            logger.info("SocialMediaIntegrator: WhatsApp stopped.")
        except Exception as e:
            logger.exception("Error stopping WhatsApp in SocialMediaIntegrator: %s", e)

    def stop_whatsapp(self) -> None:
        """Alias for stop()."""
        self.stop()


# ── Global instance ───────────────────────────────────────────────────
social_integrator = SocialMediaIntegrator()
