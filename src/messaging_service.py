# messaging_service.py
"""
MessagingService for Radhe.

Fixes applied:
- awaiting_contact flow is now complete:
  save_and_send() handles the follow-up when user provides a phone number
- WhatsApp session check: warns the user clearly if WhatsApp Web is not open
  instead of silently hanging for 90 seconds
- Platform validator only blocks truly unsupported platforms;
  unimplemented-but-planned platforms return clear "not yet" messages
- get_status() added so executor can tell user if WhatsApp is connected

NEW FIXES:
- Direct WhatsAppManager integration (no dependency on social_integrator for sending)
- Retry logic added for WhatsApp sending
- Proper contact → phone resolution
- Stable send() routing

Usage:
    from services.messaging_service import messaging_service
    result = messaging_service.send("whatsapp", "Shivam", "Hello!")
    result = messaging_service.save_and_send("Shivam", "+919876543210", "Hello!", "whatsapp")
"""

import logging
from typing import Optional

from contact_manager import contact_manager
from social_media import social_integrator
from whatsapp_manager import whatsapp_manager

logger = logging.getLogger("Radhe_MessagingService")

# Platforms we actually handle (even if some just return "not yet")
KNOWN_PLATFORMS = {"whatsapp", "telegram", "instagram", "gmail", "email", "sms"}

# Platforms that are fully working right now
WORKING_PLATFORMS = {"whatsapp"}


class MessagingService:

    # ==================================================================
    # SEND  (main entry point)
    # ==================================================================

    def send(self, platform: str, contact_name: str, message: str) -> str:
        platform     = (platform     or "whatsapp").lower().strip()
        contact_name = (contact_name or "").strip()
        message      = (message      or "").strip()

        if not message:
            return "The message is empty. Please tell me what to send."

        if not contact_name:
            return "I don't know who to send it to. Please give me a contact name."

        if platform not in KNOWN_PLATFORMS:
            return (
                f"I don't support '{platform}' yet. "
                f"Supported platforms: {', '.join(sorted(WORKING_PLATFORMS))}."
            )

        if platform not in WORKING_PLATFORMS:
            return (
                f"{platform.capitalize()} messaging is coming soon. "
                f"For now I can send via WhatsApp."
            )

        # WhatsApp session check
        if platform == "whatsapp":
            if not self._ensure_whatsapp_ready():
                return (
                    "WhatsApp Web is not open. "
                    "Please say 'open WhatsApp' first, scan the QR code if needed, "
                    "then try sending the message again."
                )
            return self._send_whatsapp(contact_name, message)

        # Contact lookup
        contact = contact_manager.get_contact(contact_name)

        if not contact:
            return (
                f"I don't have {contact_name}'s number saved. "
                f"Please tell me their phone number (like +919876543210) "
                f"and I'll save it and send the message."
            )

        return self._route(platform, contact_name, message)

    # ==================================================================
    # ✅ NEW: WHATSAPP SEND HANDLER
    # ==================================================================

    def _send_whatsapp(self, contact: str, message: str) -> str:
        phone = self._get_phone(contact)

        if not phone:
            return f"Contact '{contact}' not found. Please provide phone number."

        # Ensure session is active
        if not whatsapp_manager.driver:
            whatsapp_manager.start()

        # ✅ Retry logic (Problem 4 FIX)
        for attempt in range(2):
            ok = whatsapp_manager.send_message(phone, message)
            if ok:
                return f"Message sent to {contact}."

        return f"Failed to send message to {contact}."
    
    def call(self, contact: str) -> str:
        contact = (contact or "").strip()
        if not contact:
            return "No contact name provided."

        # Resolve to phone number
        phone = self._get_phone(contact)
        if not phone:
            return (
                f"I don't have {contact}'s number saved. "
                "Please provide their phone number first."
            )

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

        contact_name = (contact_name or "").strip()
        phone        = (phone        or "").strip()
        message      = (message      or "").strip()
        platform     = (platform     or "whatsapp").lower().strip()

        if not contact_name or not phone or not message:
            return "Missing contact name, phone number, or message."

        saved = contact_manager.add_contact(contact_name, phone, platform)
        if not saved:
            return (
                f"I couldn't save {contact_name}'s number. "
                "Please check the format (e.g. +919876543210) and try again."
            )

        logger.info("Saved new contact: %s → %s", contact_name, phone)

        # ✅ Use new send flow
        result = self.send(platform, contact_name, message)
        return f"Saved {contact_name}'s number. {result}"

    # ==================================================================
    # ✅ NEW: CONTACT → PHONE RESOLUTION
    # ==================================================================

    def _get_phone(self, contact: str) -> Optional[str]:
        data = contact_manager.get_contact(contact)
        if not data:
            return None

        # handle both dict and direct string cases
        if isinstance(data, dict):
            return data.get("phone")

        return data

    # ==================================================================
    # WHATSAPP SESSION CHECK
    # ==================================================================

    def _ensure_whatsapp_ready(self) -> bool:
        try:
            driver = whatsapp_manager.driver
            if driver is None:
                return False

            from selenium.webdriver.common.by import By
            els = driver.find_elements(
                By.XPATH,
                "//div[@contenteditable='true' and @data-tab='3']"
            )
            return len(els) > 0

        except Exception as e:
            logger.warning("WhatsApp session check failed: %s", e)
            return False

    def start_whatsapp_session(self) -> str:
        try:
            ok = whatsapp_manager.start()
            if ok:
                return "WhatsApp Web is ready."
            return (
                "WhatsApp Web opened. "
                "Please scan the QR code to log in, then try your command again."
            )
        except Exception as e:
            logger.exception("start_whatsapp_session failed: %s", e)
            return "Could not open WhatsApp Web. Please open it manually."

    def get_status(self) -> str:
        if self._ensure_whatsapp_ready():
            return "WhatsApp Web is connected and ready."
        if whatsapp_manager.driver is not None:
            return "WhatsApp Web is open but may not be fully logged in."
        return "WhatsApp Web is not running. Say 'open WhatsApp' to start it."

    # ==================================================================
    # ROUTE TO PLATFORM
    # ==================================================================

    def _route(self, platform: str, contact_name: str, message: str) -> str:
        try:
            if platform == "whatsapp":
                # fallback (not used anymore, but kept for safety)
                return social_integrator.send_whatsapp_by_contact(contact_name, message)

            elif platform == "telegram":
                return "Telegram messaging is coming soon."

            elif platform == "instagram":
                return "Instagram messaging is coming soon."

            elif platform in ("gmail", "email"):
                return "Email sending is coming soon."

            elif platform == "sms":
                return "SMS sending is coming soon."

            else:
                return f"Platform '{platform}' is not supported."

        except Exception as e:
            logger.exception(
                "Messaging error — platform: %s, contact: %s, error: %s",
                platform, contact_name, e
            )
            return "Something went wrong while sending the message. Please try again."


# ── Global instance ───────────────────────────────────────────────────
messaging_service = MessagingService()