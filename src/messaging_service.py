# src/services/messaging_service.py
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

Usage:
    from src.services.messaging_service import messaging_service
    result = messaging_service.send("whatsapp", "Shivam", "Hello!")
    result = messaging_service.save_and_send("Shivam", "+919876543210", "Hello!", "whatsapp")
"""

import logging
from typing import Optional

from contact_manager import contact_manager
from social_media    import social_integrator
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
        """
        Send a message to a contact on the given platform.
        Returns a human-readable result string in all cases.
        """
        platform     = (platform     or "whatsapp").lower().strip()
        contact_name = (contact_name or "").strip()
        message      = (message      or "").strip()

        # ── Validate inputs ───────────────────────────────────────────
        if not message:
            return "The message is empty. Please tell me what to send."

        if not contact_name:
            return "I don't know who to send it to. Please give me a contact name."

        if platform not in KNOWN_PLATFORMS:
            return (
                f"I don't support '{platform}' yet. "
                f"Supported platforms: {', '.join(sorted(WORKING_PLATFORMS))}."
            )

        # ── Check if platform is implemented ──────────────────────────
        if platform not in WORKING_PLATFORMS:
            return (
                f"{platform.capitalize()} messaging is coming soon. "
                f"For now I can send via WhatsApp."
            )

        # ── Check WhatsApp session before contact lookup ──────────────
        if platform == "whatsapp":
            session_ok = self._ensure_whatsapp_ready()
            if not session_ok:
                return (
                    "WhatsApp Web is not open. "
                    "Please say 'open WhatsApp' first, scan the QR code if needed, "
                    "then try sending the message again."
                )

        # ── Look up contact ───────────────────────────────────────────
        contact = contact_manager.get_contact(contact_name)

        if not contact:
            return (
                f"I don't have {contact_name}'s number saved. "
                f"Please tell me their phone number (like +919876543210) "
                f"and I'll save it and send the message."
            )

        # ── Route to platform ─────────────────────────────────────────
        return self._route(platform, contact_name, message)

    # ==================================================================
    # SAVE AND SEND  (completes the awaiting_contact flow)
    # ==================================================================

    def save_and_send(
        self,
        contact_name: str,
        phone:        str,
        message:      str,
        platform:     str = "whatsapp"
    ) -> str:
        """
        Called when:
        1. User tried to send a message but contact was not found.
        2. Radhe asked for the phone number.
        3. User provided the phone number.

        This method saves the contact and immediately sends the message.
        The executor should call this when context['awaiting_contact'] is set
        and the user's next message looks like a phone number.
        """
        contact_name = (contact_name or "").strip()
        phone        = (phone        or "").strip()
        message      = (message      or "").strip()
        platform     = (platform     or "whatsapp").lower().strip()

        if not contact_name or not phone or not message:
            return "Missing contact name, phone number, or message."

        # Save the contact
        saved = contact_manager.add_contact(contact_name, phone, platform)
        if not saved:
            return (
                f"I couldn't save {contact_name}'s number. "
                "Please check the format (e.g. +919876543210) and try again."
            )

        logger.info("Saved new contact: %s → %s", contact_name, phone)

        # Now send
        result = self._route(platform, contact_name, message)
        return f"Saved {contact_name}'s number. {result}"

    # ==================================================================
    # WHATSAPP SESSION CHECK
    # ==================================================================

    def _ensure_whatsapp_ready(self) -> bool:
        """
        Check if WhatsApp Web driver is already running and logged in.
        Does NOT block waiting for QR — just returns False if not ready.
        The user should say "open WhatsApp" to start the session explicitly.
        """
        try:
            driver = whatsapp_manager.driver
            if driver is None:
                return False

            # Quick check: can we find the search bar (logged-in indicator)?
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
        """
        Explicitly start WhatsApp Web.
        Call this when user says 'open WhatsApp'.
        Returns a message to speak to the user.
        """
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
        """Human-readable WhatsApp connection status."""
        if self._ensure_whatsapp_ready():
            return "WhatsApp Web is connected and ready."
        if whatsapp_manager.driver is not None:
            return "WhatsApp Web is open but may not be fully logged in."
        return "WhatsApp Web is not running. Say 'open WhatsApp' to start it."

    # ==================================================================
    # ROUTE TO PLATFORM
    # ==================================================================

    def _route(self, platform: str, contact_name: str, message: str) -> str:
        """Send via the appropriate platform handler."""
        try:
            if platform == "whatsapp":
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