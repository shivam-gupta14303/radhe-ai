# whatsapp_manager.py
"""
WhatsAppManager - Selenium controller for WhatsApp Web
- Stores a persistent Chrome profile under data/whatsapp_profile
- Provides send_message(phone, message)
- Can listen for incoming messages via callback.
"""

import os
import time
import logging
import threading
from typing import Optional, Callable
from urllib.parse import quote_plus

logger = logging.getLogger("Radhe_WhatsApp")
# Pehle INFO tha, ab WARNING: DEBUG/INFO logs console pe nahi aayenge
logger.setLevel(logging.WARNING)

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_AVAILABLE = True
except Exception:
    SELENIUM_AVAILABLE = False
    logger.warning(
        "selenium/webdriver-manager not installed. "
        "Install them with: pip install selenium webdriver-manager"
    )

PROFILE_DIR = os.path.join("data", "whatsapp_profile")


class WhatsAppManager:
    def __init__(self, profile_dir: str = PROFILE_DIR):
        self.profile_dir = profile_dir
        self.driver: Optional["webdriver.Chrome"] = None
        self._running = False
        self._listen_thread: Optional[threading.Thread] = None
        self._callback: Optional[Callable[[str, str], None]] = None
        os.makedirs(self.profile_dir, exist_ok=True)

    def start(self) -> bool:
        """
        Start a persistent WhatsApp Web session.
        - Uses a dedicated Chrome user profile folder (data/whatsapp_profile)
        - Uses detach=True so Chrome window does NOT auto-close when Python exits.
        """
        if not SELENIUM_AVAILABLE:
            raise RuntimeError("Selenium not available.")

        if self.driver:
            logger.debug("WhatsApp Web driver already running.")
            return True

        opts = Options()
        opts.add_argument(f"--user-data-dir={os.path.abspath(self.profile_dir)}")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_experimental_option("detach", True)

        logger.debug("Launching Chrome for WhatsApp Web...")

        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=opts)

        self.driver.get("https://web.whatsapp.com")

        logger.debug("WhatsApp Web opened — wait for login (scan QR if needed)")

        timeout = 60
        for _ in range(timeout):
            try:
                if (
                    self.driver.find_elements(
                        By.XPATH, "//div[@contenteditable='true' and @data-tab]"
                    )
                    or self.driver.find_elements(By.TAG_NAME, "canvas")
                ):
                    logger.debug("WhatsApp Web appears to be loaded.")
                    break
            except Exception:
                pass
            time.sleep(1)

        logger.debug("WhatsApp Web load attempt finished.")
        return True

    def stop(self):
        """Stop driver (if we ever need to explicitly close from code)."""
        try:
            self._running = False
            if self.driver:
                logger.debug("Closing WhatsApp Web driver.")
                self.driver.quit()
        except Exception:
            pass
        finally:
            self.driver = None

    def send_message(self, phone: str, message: str) -> bool:
        """
        Send a WhatsApp message to a raw phone number string.
        `phone` should include country code, e.g. +911234567890
        """
        if not SELENIUM_AVAILABLE:
            logger.error("Selenium not installed.")
            return False

        if not self.driver:
            self.start()

        norm = (phone or "").strip().replace(" ", "").replace("-", "")
        if norm.startswith("+"):
            norm = norm[1:]

        if not norm:
            logger.warning("Empty phone number given to send_message.")
            return False

        try:
            url = f"https://web.whatsapp.com/send?phone={norm}&text={quote_plus(message)}"
            logger.debug("Opening chat URL: %s", url)
            self.driver.get(url)

            timeout = 20
            for _ in range(timeout):
                try:
                    el = self.driver.find_element(
                        By.XPATH, "//div[@contenteditable='true' and @data-tab]"
                    )
                    if el:
                        el.click()
                        el.send_keys(message)
                        el.send_keys(Keys.ENTER)
                        logger.debug("Sent message to %s", phone)
                        return True
                except Exception:
                    pass
                time.sleep(1)

            logger.warning("Could not find message input to send message.")
            return False
        except Exception as e:
            logger.exception("send_message failed: %s", e)
            return False

    def _parse_incoming_messages(self) -> list:
        """
        Scrape visible chats and last message snippet.
        Returns: list of tuples (name, snippet)
        """
        items = []
        if not self.driver:
            return items

        try:
            chats = self.driver.find_elements(By.XPATH, "//div[contains(@role,'row')]")
            for ch in chats[:10]:
                try:
                    name_el = ch.find_element(
                        By.XPATH, ".//span[@dir='auto' and @title]"
                    )
                    name = name_el.get_attribute("title") or ""
                    snippet = ""
                    try:
                        snippet_els = ch.find_elements(
                            By.XPATH,
                            ".//div[contains(@class,'_1wjpf') or "
                            "contains(@class,'_1ZMSm') or "
                            "contains(@class,'_2n_2q')]",
                        )
                        if snippet_els:
                            snippet = snippet_els[-1].text
                    except Exception:
                        snippet = ""
                    items.append((name, snippet))
                except Exception:
                    continue
        except Exception:
            pass
        return items

    def set_incoming_callback(self, cb: Callable[[str, str], None]):
        """Register callback for each detected chat snippet: cb(name, snippet)."""
        self._callback = cb

    def listen_incoming(self, poll_interval: float = 2.0):
        """
        Start background polling of chat list & call callback on new snippets.
        """
        if not SELENIUM_AVAILABLE:
            raise RuntimeError("Selenium not available.")

        if not self.driver:
            self.start()

        if self._running:
            logger.debug("Incoming listener already running.")
            return

        self._running = True
        seen = set()

        def _loop():
            logger.debug("WhatsApp incoming listener started.")
            while self._running:
                try:
                    items = self._parse_incoming_messages()
                    for name, snippet in items:
                        key = f"{name}:{snippet}"
                        if key not in seen:
                            seen.add(key)
                            if self._callback and snippet:
                                try:
                                    self._callback(name, snippet)
                                except Exception:
                                    logger.exception("Incoming callback failed.")
                    time.sleep(poll_interval)
                except Exception:
                    logger.exception("Incoming listen error")
                    time.sleep(poll_interval)

        self._listen_thread = threading.Thread(target=_loop, daemon=True)
        self._listen_thread.start()


# Global instance for easy import
whatsapp_manager = WhatsAppManager()
