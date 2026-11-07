# whatsapp_bridge.py
"""
WhatsApp AI Bridge for Radhe.
Runs Radhe as a WhatsApp companion / auto-responder.

Incoming messages on WhatsApp Web are parsed through CommandParser,
executed via CommandExecutor, and the generated response is replied
back directly to the sender on WhatsApp.
"""

import time
import logging
from typing import Optional

from whatsapp_manager import whatsapp_manager
from command_parser import CommandParser
from command_executor import executor

logger = logging.getLogger("Radhe_WhatsAppBridge")
logger.setLevel(logging.INFO)

_parser = CommandParser()


def incoming_handler(sender: str, message: str) -> None:
    """Handle incoming message from a WhatsApp contact."""
    logger.info("Incoming WhatsApp from [%s]: %s", sender, message)

    try:
        # Parse incoming message as a user command
        parsed = _parser.parse(message)

        # Execute command through Radhe's brain
        result = executor.execute(parsed, message)
        reply_text = result.get("text") or result.get("voice") or ""

        if reply_text:
            logger.info("Replying to [%s]: %s", sender, reply_text)
            ok = whatsapp_manager.send_to_contact_name(sender, reply_text)
            if not ok:
                logger.warning("Failed to deliver reply to [%s]", sender)
        else:
            logger.info("No reply generated for [%s]", sender)

    except Exception as e:
        logger.exception("Error processing WhatsApp message from [%s]: %s", sender, e)


def start_whatsapp_ai(wait_for_login: bool = True) -> bool:
    """
    Start WhatsApp Web and attach Radhe AI message listener.
    """
    logger.info("Starting Radhe WhatsApp AI Bridge...")
    started = whatsapp_manager.start(wait_for_login=wait_for_login, timeout=60)
    if not started:
        logger.warning("WhatsApp Web could not be started or login timed out.")
        return False

    whatsapp_manager.set_incoming_callback(incoming_handler)
    whatsapp_manager.listen_incoming(poll_interval=3.0)
    logger.info("Radhe WhatsApp AI Bridge is active and listening.")
    return True


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    print("Starting Radhe WhatsApp Assistant...")
    if start_whatsapp_ai(wait_for_login=True):
        print("WhatsApp AI Assistant is running. Press Ctrl+C to exit.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down WhatsApp Assistant...")
            whatsapp_manager.stop()
    else:
        print("Could not start WhatsApp Assistant.")
