# messaging_service.py
"""
MessagingService for Radhe.

Provides unified messaging interface:
- Flexible send() supporting platform routing, contact-name or phone number, list/string inputs
- Deep WhatsAppManager integration (send by contact name, phone, UI search)
- Read unread messages & chat history
- WhatsApp session check & auto-launch
"""

import logging
from typing import Optional, Any, Union, Dict, List

from contact_manager import contact_manager
from whatsapp_manager import whatsapp_manager
from config import CONTACTS_DB_FILE

logger = logging.getLogger("Radhe_MessagingService")
logger.setLevel(logging.INFO)

KNOWN_PLATFORMS = {"whatsapp", "telegram", "instagram", "gmail", "email", "sms"}
WORKING_PLATFORMS = {"whatsapp"}


class MessagingService:

    # ==================================================================
    # SEND (Main entry point)
    # ==================================================================

    def send(
        self,
        platform: str = "whatsapp",
        contact_name: Any = "",
        message: str = "",
        contact: Any = None,
        **kwargs
    ) -> str:
        """
        Send a message through the requested platform (defaults to WhatsApp).
        Extremely tolerant to arg variations (positional, keyword, list contacts).
        """
        # Handle 'contact' alias
        if contact is not None and not contact_name:
            contact_name = contact

        # If platform was omitted and first arg is contact: e.g. send("Shivam", "Hello!")
        if platform and platform.lower().strip() not in KNOWN_PLATFORMS and not message:
            message = str(contact_name)
            contact_name = platform
            platform = "whatsapp"

        platform = (platform or "whatsapp").lower().strip()

        # Handle list contacts (e.g. ['Shivam'])
        if isinstance(contact_name, list):
            contact_name = contact_name[0] if contact_name else ""
        elif isinstance(contact_name, dict):
            contact_name = contact_name.get("name") or contact_name.get("phone") or ""

        contact_name = str(contact_name or "").strip()
        message = str(message or "").strip()

        if not contact_name:
            return "I don't know who to send the message to. Please provide a contact name."

        if not message:
            return f"The message is empty. What would you like to send to {contact_name}?"

        if platform not in KNOWN_PLATFORMS:
            return f"I don't support '{platform}' yet. Supported platforms: {', '.join(sorted(WORKING_PLATFORMS))}."

        if platform not in WORKING_PLATFORMS:
            return f"{platform.capitalize()} messaging is coming soon. For now I can send via WhatsApp."

        if platform == "whatsapp":
            return self._send_whatsapp(contact_name, message)

        return self._route(platform, contact_name, message)

    # ==================================================================
    # WHATSAPP SEND HANDLER
    # ==================================================================

    def _send_whatsapp(self, contact: str, message: str) -> str:
        # Ensure driver is running
        if not whatsapp_manager.is_running():
            logger.info("WhatsApp Web not running. Launching...")
            whatsapp_manager.start(wait_for_login=False)

        # Retry logic
        for attempt in range(2):
            ok = whatsapp_manager.send_to_contact_name(contact, message)
            if ok:
                return f"Message sent to {contact} on WhatsApp."
            time_delay = 1.0 * (attempt + 1)
            import time
            time.sleep(time_delay)

        return (
            f"Could not send WhatsApp message to {contact}. "
            "Please check that WhatsApp Web is open and logged in."
        )

    # ==================================================================
    # READ / UNREAD MESSAGES
    # ==================================================================

    def get_unread_messages(self) -> str:
        """Fetch and summarize all unread WhatsApp messages."""
        if not whatsapp_manager.is_running():
            return "WhatsApp Web is not open. Say 'open WhatsApp' to connect."

        if not whatsapp_manager.is_logged_in():
            return "WhatsApp Web is not logged in. Please scan the QR code first."

        unread = whatsapp_manager.get_unread_messages()
        if not unread:
            return "You have no unread WhatsApp messages."

        count = len(unread)
        lines = [f"You have {count} unread chat{'s' if count > 1 else ''}:"]
        for u in unread[:5]:
            sender = u.get("sender", "Unknown")
            c = u.get("count", 1)
            snip = u.get("snippet", "")
            lines.append(f"- {sender} ({c} new): \"{snip}\"")

        return "\n".join(lines)

    def read_messages(self, contact_name: str, count: int = 5) -> str:
        """Read recent messages from a specific WhatsApp contact."""
        if not whatsapp_manager.is_running():
            return "WhatsApp Web is not open. Say 'open WhatsApp' to connect."

        msgs = whatsapp_manager.read_latest_messages(contact_name, count=count)
        if not msgs:
            return f"No recent messages found for {contact_name}."

        lines = [f"Recent messages with {contact_name}:"]
        for m in msgs:
            prefix = "You" if m.get("is_outgoing") else contact_name
            text = m.get("text", "")
            lines.append(f"{prefix}: {text}")

        return "\n".join(lines)

    # ==================================================================
    # CALL HANDLER
    # ==================================================================

    def call(self, contact: Any) -> str:
        if isinstance(contact, list):
            contact = contact[0] if contact else ""
        contact = str(contact or "").strip()

        if not contact:
            return "No contact name provided."

        phone = self._get_phone(contact)
        if not phone:
            return f"I don't have {contact}'s number saved. Please provide their phone number first."

        try:
            import webbrowser
            webbrowser.open(f"tel:{phone}")
            return f"Calling {contact}."
        except Exception as e:
            logger.warning("Call failed: %s", e)
            return f"Could not call {contact}. Please dial {phone} manually."

    # ==================================================================
    # SAVE AND SEND
    # ==================================================================

    def save_and_send(
        self,
        contact_name: str,
        phone: str,
        message: str,
        platform: str = "whatsapp"
    ) -> str:
        contact_name = str(contact_name or "").strip()
        phone = str(phone or "").strip()
        message = str(message or "").strip()

        if not contact_name or not phone or not message:
            return "Missing contact name, phone number, or message."

        saved = contact_manager.add_contact(contact_name, phone, platform)
        if not saved:
            return f"I couldn't save {contact_name}'s number. Please check the format."

        result = self.send(platform, contact_name, message)
        return f"Saved {contact_name}'s number. {result}"

    def _get_phone(self, contact: str) -> Optional[str]:
        data = contact_manager.get_contact(contact)
        if not data:
            return None
        if isinstance(data, dict):
            return data.get("phone")
        return str(data)

    def start_whatsapp_session(self) -> str:
        try:
            ok = whatsapp_manager.start(wait_for_login=False)
            if ok:
                if whatsapp_manager.is_logged_in():
                    return "WhatsApp Web is open and connected."
                return "WhatsApp Web opened. Please scan the QR code to log in."
            return "Could not open WhatsApp Web. Please check Chrome."
        except Exception as e:
            logger.exception("start_whatsapp_session failed: %s", e)
            return f"Could not open WhatsApp Web: {e}"

    def get_status(self) -> str:
        if whatsapp_manager.is_logged_in():
            return "WhatsApp Web is connected and ready."
        if whatsapp_manager.is_running():
            return "WhatsApp Web is open but awaiting login. Please scan QR code."
        return "WhatsApp Web is not running. Say 'open WhatsApp' to start it."

    def _route(self, platform: str, contact_name: str, message: str) -> str:
        return f"Messaging via '{platform}' is not yet supported."


# ── Global instance ───────────────────────────────────────────────────
messaging_service = MessagingService()
