# social_media.py
"""
Integration wrapper that uses ContactManager and WhatsAppManager for messaging.
This file exposes a stable global instance `social_integrator`
which other modules (executor, telegram_bot) import.
"""

import logging
from typing import Optional
# import our local managers
from src.contact_manager import contact_manager
from whatsapp_manager import whatsapp_manager

logger = logging.getLogger("Radhe_SocialInt")
logger.setLevel(logging.INFO)

class SocialMediaIntegrator:
    def __init__(self):
        self.whatsapp = whatsapp_manager

    def send_whatsapp_by_contact(self, contact_name: str, message: str) -> str:
        """
        Send a WhatsApp message using a saved contact name.
        Returns a friendly status string.
        """
        if not contact_name:
            return "No contact name provided."
        c = contact_manager.get_contact(contact_name)
        if not c:
            return f"I don't have contact {contact_name}. Please provide the phone number to save."
        phone = c.get("phone")
        if not phone:
            return f"{contact_name} has no phone number saved."
        ok = self.whatsapp.send_message(phone, message)
        return "Message sent via WhatsApp." if ok else "Failed to send WhatsApp message."

    def send_whatsapp_by_number(self, phone: str, message: str) -> str:
        """Send a WhatsApp message directly by phone number."""
        if not phone:
            return "No phone number provided."
        ok = self.whatsapp.send_message(phone, message)
        return "Message sent via WhatsApp." if ok else "Failed to send WhatsApp message."

    def start_whatsapp(self) -> str:
        """Start WhatsApp Web session via the underlying manager."""
        try:
            self.whatsapp.start()
            return "WhatsApp Web started. Scan QR if not logged in."
        except Exception as e:
            logger.exception("start_whatsapp failed: %s", e)
            return f"Could not start WhatsApp Web: {e}"

    def listen_and_register_callback(self, callback):
        """
        Register a callback for incoming chat snippets and start a background listener.
        Callback signature: callback(name: str, snippet: str) -> None
        """
        try:
            self.whatsapp.set_incoming_callback(callback)
            self.whatsapp.listen_incoming()
            return "Listening for incoming WhatsApp messages."
        except Exception as e:
            logger.exception("listen_and_register_callback failed: %s", e)
            return f"Failed to start listener: {e}"

# global instance used by other modules
social_integrator = SocialMediaIntegrator()
