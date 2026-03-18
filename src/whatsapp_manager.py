# whatsapp_manager.py
"""
WhatsAppManager — Selenium controller for WhatsApp Web.

Fixes applied:
- Removed double message typing (URL param already fills input; only ENTER needed)
- Login detection now waits for the search bar (true logged-in state), not the QR canvas
- Improved reliability with small sleeps after navigation

Future improvement ideas:
- Use a proper incoming message watcher (MutationObserver via JS injection)
  instead of DOM scraping for more reliable message detection.
"""

import os
import time
import logging
import threading
from typing import Optional, Callable
from urllib.parse import quote_plus

logger = logging.getLogger("Radhe_WhatsApp")
logger.setLevel(logging.WARNING)

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_AVAILABLE = True
except Exception:
    SELENIUM_AVAILABLE = False
    logger.warning(
        "selenium / webdriver-manager not installed. "
        "Run: pip install selenium webdriver-manager"
    )

PROFILE_DIR = os.path.join("data", "whatsapp_profile")

# XPath for the WhatsApp Web search bar — only present when fully logged in
_SEARCH_BAR_XPATH = "//div[@contenteditable='true' and @data-tab='3']"

# XPath for the active message input box (bottom of an open chat)
_MSG_INPUT_XPATH  = "//div[@contenteditable='true' and @data-tab='10']"


class WhatsAppManager:

    def __init__(self, profile_dir: str = PROFILE_DIR):
        self.profile_dir  = profile_dir
        self.driver: Optional["webdriver.Chrome"] = None
        self._running     = False
        self._listen_thread: Optional[threading.Thread] = None
        self._callback: Optional[Callable[[str, str], None]] = None
        os.makedirs(self.profile_dir, exist_ok=True)

    # ==================================================================
    # START / STOP
    # ==================================================================

    def start(self) -> bool:
        """
        Open a persistent Chrome session with WhatsApp Web.
        Blocks up to 90 seconds waiting for the user to scan the QR code.
        If already logged in, returns in ~2 seconds.
        """
        if not SELENIUM_AVAILABLE:
            raise RuntimeError(
                "Selenium not available. "
                "Run: pip install selenium webdriver-manager"
            )

        if self.driver:
            logger.debug("WhatsApp Web driver already running.")
            return True

        opts = Options()
        opts.add_argument(f"--user-data-dir={os.path.abspath(self.profile_dir)}")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_experimental_option("detach", True)   # keep Chrome open after Python exits
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])

        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=opts)
        self.driver.get("https://web.whatsapp.com")

        logger.warning("WhatsApp Web opened — waiting for login (scan QR if needed)...")

        # Wait up to 90 seconds for the SEARCH BAR (only visible when logged in)
        try:
            WebDriverWait(self.driver, 90).until(
                EC.presence_of_element_located((By.XPATH, _SEARCH_BAR_XPATH))
            )
            logger.warning("WhatsApp Web: logged in successfully.")
            return True
        except Exception:
            logger.warning(
                "WhatsApp Web: did not detect login within 90 seconds. "
                "You may need to scan the QR code and restart."
            )
            return False

    def stop(self):
        """Close the Chrome driver."""
        try:
            self._running = False
            if self.driver:
                self.driver.quit()
        except Exception:
            pass
        finally:
            self.driver = None

    # ==================================================================
    # SEND MESSAGE
    # ==================================================================

    def send_message(self, phone: str, message: str) -> bool:
        """
        Send a WhatsApp message to a phone number (with country code, e.g. +919876543210).

        Strategy:
        1. Open the wa.me deep-link URL with the message pre-filled.
        2. Wait for the message input box to appear.
        3. Press ENTER only — the URL param already filled the text.
           (Calling send_keys(message) here would type the message TWICE.)
        """
        if not SELENIUM_AVAILABLE:
            logger.error("Selenium not installed.")
            return False

        if not self.driver:
            ok = self.start()
            if not ok:
                return False

        # Normalise phone: remove spaces, dashes, leading '+'
        norm = (phone or "").strip().replace(" ", "").replace("-", "")
        if norm.startswith("+"):
            norm = norm[1:]

        if not norm.isdigit() or len(norm) < 7:
            logger.warning("Invalid phone number: %s", phone)
            return False

        try:
            url = (
                f"https://web.whatsapp.com/send"
                f"?phone={norm}"
                f"&text={quote_plus(message)}"
            )
            self.driver.get(url)

            # Wait for the message input to appear (chat has loaded)
            try:
                input_el = WebDriverWait(self.driver, 25).until(
                    EC.presence_of_element_located((By.XPATH, _MSG_INPUT_XPATH))
                )
            except Exception:
                # Fallback: try the generic contenteditable
                try:
                    input_el = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located(
                            (By.XPATH, "//div[@contenteditable='true' and @data-tab]")
                        )
                    )
                except Exception:
                    logger.warning("Message input box not found for %s", phone)
                    return False

            # Small pause so WhatsApp can finish filling the text from the URL param
            time.sleep(0.8)

            # Press ENTER to send — do NOT call send_keys(message) here
            # (the URL already filled the text; typing it again would duplicate it)
            input_el.click()
            input_el.send_keys(Keys.ENTER)

            # Brief wait so the message actually sends before we navigate away
            time.sleep(1.0)

            logger.warning("Message sent to %s", phone)
            return True

        except Exception as e:
            logger.exception("send_message failed for %s: %s", phone, e)
            return False

    # ==================================================================
    # INCOMING MESSAGE LISTENER
    # ==================================================================

    def _parse_incoming_messages(self) -> list:
        """
        Scrape the chat list for visible contact name + last message snippet.
        Returns a list of (name, snippet) tuples.
        """
        items = []
        if not self.driver:
            return items

        try:
            chats = self.driver.find_elements(
                By.XPATH, "//div[@role='row' or @role='listitem']"
            )
            for ch in chats[:15]:
                try:
                    name_el = ch.find_element(
                        By.XPATH, ".//span[@dir='auto' and @title]"
                    )
                    name = name_el.get_attribute("title") or ""

                    snippet = ""
                    try:
                        # Try several common WhatsApp Web CSS class patterns
                        for cls in ["_21S-L", "_1wjpf", "_1ZMSm", "_2n_2q"]:
                            els = ch.find_elements(
                                By.XPATH, f".//div[contains(@class,'{cls}')]"
                            )
                            if els:
                                snippet = els[-1].text.strip()
                                break
                    except Exception:
                        snippet = ""

                    if name:
                        items.append((name, snippet))
                except Exception:
                    continue
        except Exception:
            pass

        return items

    def set_incoming_callback(self, cb: Callable[[str, str], None]):
        """Register a callback: cb(contact_name, message_snippet)."""
        self._callback = cb

    def listen_incoming(self, poll_interval: float = 3.0):
        """
        Poll the WhatsApp Web chat list in a background thread.
        Fires the registered callback for each new message snippet seen.
        """
        if not SELENIUM_AVAILABLE:
            raise RuntimeError("Selenium not available.")

        if not self.driver:
            self.start()

        if self._running:
            logger.debug("Incoming listener already running.")
            return

        self._running = True
        seen: set = set()

        def _loop():
            logger.warning("WhatsApp incoming listener started.")
            while self._running:
                try:
                    for name, snippet in self._parse_incoming_messages():
                        key = f"{name}:{snippet}"
                        if key not in seen and snippet:
                            seen.add(key)
                            if self._callback:
                                try:
                                    self._callback(name, snippet)
                                except Exception:
                                    logger.exception("Incoming callback error.")
                except Exception:
                    logger.exception("Incoming listener poll error.")
                time.sleep(poll_interval)

        self._listen_thread = threading.Thread(
            target=_loop, name="WAIncomingListener", daemon=True
        )
        self._listen_thread.start()


# ── Global instance ───────────────────────────────────────────────────
whatsapp_manager = WhatsAppManager()