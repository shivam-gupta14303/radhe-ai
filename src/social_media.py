# social_media.py
"""
SocialMediaIntegrator for Radhe.

Fix applied vs previous version:
- send_whatsapp_by_contact() previously resolved the contact internally,
  but messaging_service.py was already passing a resolved dict.
  Now accepts EITHER a name string OR a pre-resolved contact dict —
  handles both cases cleanly so neither caller breaks.

Goal-aligned improvements:
- listen_whatsapp() convenience method wraps the full listener setup.
- incoming_message_handler() is a default callback that passes incoming
  WhatsApp messages to Radhe's executor automatically — foundation for
  "read and reply to my WhatsApp messages by voice".
"""

import logging
from typing import Optional, Callable, Union, Dict, Any

from contact_manager import contact_manager
from whatsapp_manager import whatsapp_manager

logger = logging.getLogger("Radhe_SocialInt")
logger.setLevel(logging.INFO)


class SocialMediaIntegrator:

    def __init__(self):
        self.whatsapp = whatsapp_manager
        self._executor_ref = None   # set by executor after init if needed

    # ==================================================================
    # WHATSAPP SEND
    # ==================================================================

    def send_whatsapp_by_contact(
        self,
        contact: Union[str, Dict[str, Any]],
        message: str
    ) -> str:
        """
        Send a WhatsApp message.

        `contact` can be:
          - a name string  ("Shivam")  → looked up in ContactManager
          - a contact dict {"name":..., "phone":...}  → used directly

        Fix: previous version always expected a name string, but
        messaging_service.py was passing the resolved dict.
        Now handles both so neither caller breaks.
        """
        if not message:
            return "Message is empty."

        # ── Resolve contact ───────────────────────────────────────────
        if isinstance(contact, dict):
            # Already resolved — use directly
            c    = contact
            name = c.get("name", "unknown")
        elif isinstance(contact, str):
            name = contact.strip()
            if not name:
                return "No contact name provided."
            c = contact_manager.get_contact(name)
            if not c:
                return (
                    f"I don't have {name}'s number saved. "
                    "Please provide the phone number so I can save it and send the message."
                )
        else:
            return "Invalid contact format."

        phone = (c.get("phone") or "").strip()
        if not phone:
            return f"{name} has no phone number saved."

        ok = self.whatsapp.send_message(phone, message)
        if ok:
            return f"Message sent to {name} on WhatsApp."
        return f"Failed to send WhatsApp message to {name}. Please check if WhatsApp Web is open."

    def send_whatsapp_by_number(self, phone: str, message: str) -> str:
        """Send directly to a phone number (no contact lookup needed)."""
        if not phone:
            return "No phone number provided."
        if not message:
            return "Message is empty."
        ok = self.whatsapp.send_message(phone, message)
        return "Message sent via WhatsApp." if ok else "Failed to send WhatsApp message."

    # ==================================================================
    # WHATSAPP SESSION
    # ==================================================================

    def start_whatsapp(self) -> str:
        """Open WhatsApp Web and wait for login."""
        try:
            ok = self.whatsapp.start()
            if ok:
                return "WhatsApp Web is ready."
            return "WhatsApp Web opened — please scan the QR code to log in."
        except Exception as e:
            logger.exception("start_whatsapp failed: %s", e)
            return f"Could not start WhatsApp Web: {e}"

    # ==================================================================
    # INCOMING MESSAGE LISTENER
    # Goal: Radhe reads and optionally auto-replies to WhatsApp messages
    # ==================================================================

    def listen_whatsapp(
        self,
        callback: Optional[Callable[[str, str], None]] = None
    ) -> str:
        """
        Start listening for incoming WhatsApp messages.

        If no callback is provided, uses the default handler which
        logs incoming messages and (if executor is connected) passes
        them to Radhe's executor for intelligent replies.

        Usage in radhe.py:
            social_integrator.listen_whatsapp()
        """
        cb = callback or self._default_incoming_handler

        try:
            self.whatsapp.set_incoming_callback(cb)
            self.whatsapp.listen_incoming()
            return "Listening for incoming WhatsApp messages."
        except Exception as e:
            logger.exception("listen_whatsapp failed: %s", e)
            return f"Failed to start WhatsApp listener: {e}"

    def _default_incoming_handler(self, sender: str, snippet: str):
        """
        Default handler for incoming WhatsApp messages.

        Currently: logs the message.
        Future: pass to executor → generate reply → send back automatically.
        """
        logger.info("Incoming WhatsApp from %s: %s", sender, snippet)

        # ── Plug into executor for auto-reply (when executor is connected) ──
        if self._executor_ref is not None:
            try:
                from src.command_parser import CommandParser
                parser = CommandParser()

                # Treat incoming message as a user command
                parsed = parser.parse(snippet)
                result = self._executor_ref.execute(parsed, snippet)
                reply  = result.get("text", "")

                if reply:
                    self.send_whatsapp_by_contact(sender, reply)
                    logger.info("Auto-replied to %s: %s", sender, reply)

            except Exception as e:
                logger.exception("Auto-reply failed: %s", e)

    def connect_executor(self, executor_instance) -> None:
        """
        Connect Radhe's executor so incoming WhatsApp messages can be
        processed and auto-replied automatically.

        Call from radhe.py:
            social_integrator.connect_executor(executor)
        """
        self._executor_ref = executor_instance
        logger.info("Executor connected to SocialMediaIntegrator.")


# ── Global instance ───────────────────────────────────────────────────
social_integrator = SocialMediaIntegrator()