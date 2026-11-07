# whatsapp_manager.py
"""
WhatsAppManager — High-reliability Selenium controller for WhatsApp Web.

Features:
- Robust ChromeDriver lifecycle management using Selenium 4 + webdriver-manager fallback
- Thread-safe driver calls with threading.Lock()
- Persistent user profile in data/whatsapp_profile for saved logins
- Fast login detection without blocking the assistant
- Multiple resilient selectors for all WhatsApp Web UI elements
- Send message by phone number (with invalid phone popup detection)
- Send message by contact name (via contact_manager phone lookup OR direct WhatsApp search)
- Read unread messages from chat list
- Read message history from active or specified chat
- Background incoming message listener with deduplication
"""

import os
import sys
import time
import logging
import threading
from typing import Optional, Callable, Dict, Any, List, Tuple
from urllib.parse import quote_plus
from pathlib import Path

from config import WHATSAPP_PROFILE_DIR, CONTACTS_DB_FILE

logger = logging.getLogger("Radhe_WhatsApp")
logger.setLevel(logging.INFO)

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import (
        WebDriverException,
        TimeoutException,
        NoSuchElementException,
        StaleElementReferenceException,
        SessionNotCreatedException,
    )
    SELENIUM_AVAILABLE = True
except Exception:
    SELENIUM_AVAILABLE = False
    logger.warning("Selenium not installed. Install via: pip install selenium webdriver-manager")

try:
    from webdriver_manager.chrome import ChromeDriverManager
    WDM_AVAILABLE = True
except Exception:
    WDM_AVAILABLE = False


# ======================================================================
# UI SELECTORS (Multi-fallback for WhatsApp Web resilience)
# ======================================================================

_SEARCH_BAR_XPATHS = [
    "//div[@id='side']//div[@contenteditable='true']",
    "//div[@contenteditable='true' and @data-tab='3']",
    "//div[@role='textbox' and (contains(@title, 'Search') or contains(@aria-label, 'Search'))]",
    "//div[contains(@class, 'selectable-text') and @data-tab='3']",
]

_MSG_INPUT_XPATHS = [
    "//footer//div[@contenteditable='true']",
    "//footer//div[@role='textbox']",
    "//div[@contenteditable='true' and @data-tab='10']",
    "//footer//p[contains(@class, 'selectable-text')]",
    "//div[@contenteditable='true' and contains(@class, 'selectable-text')]",
]

_SEND_BTN_XPATHS = [
    "//button[@aria-label='Send' or @data-tab='11']",
    "//span[@data-icon='send']/parent::button",
    "//span[@data-icon='send-refreshed']/parent::button",
    "//button[contains(@aria-label, 'Send')]",
    "//footer//button[.//span[@data-icon]]",
]

_CHAT_LIST_XPATH = "//div[@id='pane-side']"
_CHAT_ROW_XPATH = "//div[@id='pane-side']//div[@role='row' or @role='listitem']"


class WhatsAppManager:

    def __init__(self, profile_dir: Optional[str] = None):
        self.profile_dir = Path(profile_dir) if profile_dir else WHATSAPP_PROFILE_DIR
        self.profile_dir.mkdir(parents=True, exist_ok=True)

        self.driver: Optional["webdriver.Chrome"] = None
        self._driver_lock = threading.Lock()
        self._running = False
        self._listen_thread: Optional[threading.Thread] = None
        self._callback: Optional[Callable[[str, str], None]] = None
        self._seen_messages: set = set()

    # ==================================================================
    # DRIVER LIFECYCLE
    # ==================================================================

    def is_running(self) -> bool:
        """Check if Chrome driver is active and responsive."""
        if not self.driver:
            return False
        try:
            _ = self.driver.current_url
            return True
        except Exception:
            self.driver = None
            return False

    def is_logged_in(self) -> bool:
        """Fast check (1s) to see if WhatsApp Web is logged in."""
        if not self.is_running():
            return False
        try:
            with self._driver_lock:
                # Check for QR canvas
                qr_elements = self.driver.find_elements(By.XPATH, "//canvas | //div[@data-ref]")
                if qr_elements:
                    return False

                # Check for chat pane or search bar
                pane = self.driver.find_elements(By.XPATH, _CHAT_LIST_XPATH)
                if pane:
                    return True

                for xpath in _SEARCH_BAR_XPATHS:
                    if self.driver.find_elements(By.XPATH, xpath):
                        return True
            return False
        except Exception:
            return False

    def start(self, wait_for_login: bool = False, timeout: int = 45) -> bool:
        """
        Launch Chrome with persistent profile and navigate to WhatsApp Web.
        If already running, brings up window and returns True.
        """
        if not SELENIUM_AVAILABLE:
            logger.error("Selenium not installed. Run: pip install selenium webdriver-manager")
            return False

        if self.is_running():
            logger.info("WhatsApp Web Chrome instance is already running.")
            return True

        with self._driver_lock:
            try:
                opts = Options()
                opts.add_argument(f"--user-data-dir={os.path.abspath(str(self.profile_dir))}")
                opts.add_argument("--disable-notifications")
                opts.add_argument("--no-sandbox")
                opts.add_argument("--disable-dev-shm-usage")
                opts.add_argument("--disable-blink-features=AutomationControlled")
                opts.add_argument("--start-maximized")
                opts.add_experimental_option("detach", True)
                opts.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
                opts.add_experimental_option("useAutomationExtension", False)

                try:
                    # Selenium 4 built-in Selenium Manager
                    self.driver = webdriver.Chrome(options=opts)
                except Exception as ex1:
                    logger.warning("Default Selenium Chrome init failed (%s), trying ChromeDriverManager...", ex1)
                    if WDM_AVAILABLE:
                        service = Service(ChromeDriverManager().install())
                        self.driver = webdriver.Chrome(service=service, options=opts)
                    else:
                        raise ex1

                self.driver.set_page_load_timeout(60)
                self.driver.get("https://web.whatsapp.com")
                logger.info("WhatsApp Web opened.")

            except SessionNotCreatedException as e:
                logger.error("Could not start Chrome: Profile in use by another Chrome instance. Please close other Chrome windows using this profile: %s", e)
                return False
            except Exception as e:
                logger.exception("Failed to start WhatsApp Web driver: %s", e)
                return False

        if wait_for_login:
            return self.wait_for_login(timeout)
        return True

    def wait_for_login(self, timeout: int = 60) -> bool:
        """Wait for the user to be logged in (QR scanned)."""
        logger.info("Waiting up to %d seconds for WhatsApp Web login...", timeout)
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.is_logged_in():
                logger.info("WhatsApp Web: logged in successfully.")
                return True
            time.sleep(1.5)
        logger.warning("WhatsApp Web login not detected within %d seconds.", timeout)
        return False

    def stop(self):
        """Cleanly shut down incoming listener and Chrome driver."""
        self._running = False
        with self._driver_lock:
            try:
                if self.driver:
                    self.driver.quit()
            except Exception:
                pass
            finally:
                self.driver = None
        logger.info("WhatsApp Web driver stopped.")

    # ==================================================================
    # ELEMENT FINDERS (Resilient)
    # ==================================================================

    def _find_msg_input(self, timeout: float = 12.0):
        if not self.driver:
            return None
        start = time.time()
        while time.time() - start < timeout:
            for xpath in _MSG_INPUT_XPATHS:
                try:
                    els = self.driver.find_elements(By.XPATH, xpath)
                    for el in els:
                        if el.is_displayed():
                            return el
                except Exception:
                    pass
            time.sleep(0.5)
        return None

    def _find_search_bar(self, timeout: float = 8.0):
        if not self.driver:
            return None
        start = time.time()
        while time.time() - start < timeout:
            for xpath in _SEARCH_BAR_XPATHS:
                try:
                    els = self.driver.find_elements(By.XPATH, xpath)
                    for el in els:
                        if el.is_displayed():
                            return el
                except Exception:
                    pass
            time.sleep(0.5)
        return None

    def _click_send_btn(self) -> bool:
        if not self.driver:
            return False
        for xpath in _SEND_BTN_XPATHS:
            try:
                btns = self.driver.find_elements(By.XPATH, xpath)
                for btn in btns:
                    if btn.is_displayed() and btn.is_enabled():
                        btn.click()
                        return True
            except Exception:
                pass
        return False

    def _check_invalid_phone_popup(self) -> bool:
        """Check if WhatsApp shows 'Phone number shared via url is invalid' popup."""
        if not self.driver:
            return False
        try:
            dialogs = self.driver.find_elements(By.XPATH, "//div[@role='dialog'] | //div[contains(@class, 'modal')]")
            for dlg in dialogs:
                txt = dlg.text.lower()
                if "invalid" in txt or "phone number" in txt:
                    try:
                        ok_btn = dlg.find_element(By.XPATH, ".//button")
                        ok_btn.click()
                    except Exception:
                        pass
                    return True
        except Exception:
            pass
        return False

    # ==================================================================
    # SEND MESSAGE BY PHONE
    # ==================================================================

    def send_message(self, phone: str, message: str) -> bool:
        """
        Send a WhatsApp message to a phone number.
        Normalises number, opens send URL, handles input and clicks send.
        """
        if not SELENIUM_AVAILABLE:
            logger.error("Selenium not installed.")
            return False

        message = (message or "").strip()
        if not message:
            logger.warning("send_message: message is empty.")
            return False

        norm = (phone or "").strip().replace(" ", "").replace("-", "")
        if norm.startswith("+"):
            norm = norm[1:]
        elif norm.startswith("0") and len(norm) == 11:
            norm = "91" + norm[1:]
        elif len(norm) == 10 and norm.isdigit():
            norm = "91" + norm  # Default India country code for 10-digit numbers

        if not norm.isdigit() or len(norm) < 7:
            logger.warning("Invalid phone number: %s", phone)
            return False

        if not self.is_running():
            ok = self.start(wait_for_login=True, timeout=30)
            if not ok:
                return False

        with self._driver_lock:
            try:
                url = f"https://web.whatsapp.com/send?phone={norm}&text={quote_plus(message)}"
                self.driver.get(url)

                time.sleep(1.5)

                # Check if invalid number popup appeared
                if self._check_invalid_phone_popup():
                    logger.warning("WhatsApp reported phone number is invalid: %s", phone)
                    return False

                input_el = self._find_msg_input(timeout=20.0)

                # Check invalid popup again if input not found quickly
                if not input_el and self._check_invalid_phone_popup():
                    logger.warning("WhatsApp reported phone number is invalid: %s", phone)
                    return False

                if not input_el:
                    logger.warning("Message input box not found for %s", phone)
                    return False

                time.sleep(0.5)

                # Try clicking the send button first (URL text param pre-populates it)
                sent = self._click_send_btn()
                if not sent:
                    # Fallback: click input box and press ENTER
                    input_el.click()
                    time.sleep(0.3)

                    # If box is empty (URL text didn't populate), type it via send_keys
                    box_text = input_el.text or ""
                    if not box_text.strip():
                        # Use JavaScript or send_keys
                        self.driver.execute_script(
                            "arguments[0].focus(); document.execCommand('insertText', false, arguments[1]);",
                            input_el, message
                        )
                        time.sleep(0.3)

                    input_el.send_keys(Keys.ENTER)
                    time.sleep(0.5)
                    self._click_send_btn()

                time.sleep(1.0)
                logger.info("Message sent successfully to %s", phone)
                return True

            except Exception as e:
                logger.exception("send_message failed for %s: %s", phone, e)
                return False

    # ==================================================================
    # SEND MESSAGE BY CONTACT NAME
    # ==================================================================

    def send_to_contact_name(self, name: str, message: str) -> bool:
        """
        Send message using contact name.
        1. Attempts to resolve phone number via ContactManager.
        2. If found, sends via phone number URL.
        3. If not found or phone send fails, searches contact in WhatsApp Web directly.
        """
        name = (name or "").strip()
        message = (message or "").strip()
        if not name or not message:
            return False

        # Step 1: Look up phone in ContactManager
        try:
            from contact_manager import contact_manager
            contact = contact_manager.get_contact(name)
            if contact and contact.get("phone"):
                phone = contact["phone"]
                logger.info("Resolved contact '%s' to phone %s", name, phone)
                ok = self.send_message(phone, message)
                if ok:
                    return True
        except Exception as e:
            logger.warning("ContactManager lookup failed for %s: %s", name, e)

        # Step 2: Fallback — search contact name directly in WhatsApp Web UI
        logger.info("Attempting direct WhatsApp Web UI search for '%s'...", name)
        return self.send_via_chat_search(name, message)

    def send_via_chat_search(self, name: str, message: str) -> bool:
        """
        Open chat by typing contact name in WhatsApp search box, then send message.
        Works without needing the contact's phone number saved locally.
        """
        if not self.is_running():
            ok = self.start(wait_for_login=True, timeout=30)
            if not ok:
                return False

        with self._driver_lock:
            try:
                # Open main page if not already there
                if "web.whatsapp.com" not in self.driver.current_url:
                    self.driver.get("https://web.whatsapp.com")
                    time.sleep(2.0)

                search_bar = self._find_search_bar(timeout=10.0)
                if not search_bar:
                    logger.warning("Search bar not found in WhatsApp Web.")
                    return False

                search_bar.click()
                time.sleep(0.3)
                # Clear search bar (Ctrl+A -> Backspace)
                search_bar.send_keys(Keys.CONTROL + "a")
                search_bar.send_keys(Keys.BACKSPACE)
                time.sleep(0.2)

                # Type name into search
                search_bar.send_keys(name)
                time.sleep(1.5)

                # Look for matching chat in search results
                chat_found = False
                chats = self.driver.find_elements(By.XPATH, _CHAT_ROW_XPATH)
                for ch in chats[:8]:
                    try:
                        title_els = ch.find_elements(By.XPATH, ".//span[@title] | .//span[@dir='auto']")
                        for t in title_els:
                            t_text = t.get_attribute("title") or t.text or ""
                            if name.lower() in t_text.lower():
                                ch.click()
                                chat_found = True
                                break
                    except Exception:
                        pass
                    if chat_found:
                        break

                if not chat_found:
                    # Press Enter on search bar to select first match
                    search_bar.send_keys(Keys.ENTER)
                    time.sleep(1.0)

                # Find message input box in the opened chat
                input_el = self._find_msg_input(timeout=10.0)
                if not input_el:
                    logger.warning("Could not find message input for chat '%s'", name)
                    return False

                input_el.click()
                time.sleep(0.3)

                # Insert text
                self.driver.execute_script(
                    "arguments[0].focus(); document.execCommand('insertText', false, arguments[1]);",
                    input_el, message
                )
                time.sleep(0.3)

                # Send
                if not self._click_send_btn():
                    input_el.send_keys(Keys.ENTER)

                time.sleep(1.0)
                logger.info("Sent message to '%s' via chat search.", name)
                return True

            except Exception as e:
                logger.exception("send_via_chat_search failed for '%s': %s", name, e)
                return False

    # ==================================================================
    # READ UNREAD MESSAGES
    # ==================================================================

    def get_unread_messages(self) -> List[Dict[str, Any]]:
        """
        Scan chat list for chats with unread messages.
        Returns list of dicts: [{"sender": name, "count": count, "snippet": snippet}]
        """
        items: List[Dict[str, Any]] = []
        if not self.is_running():
            return items

        with self._driver_lock:
            try:
                chats = self.driver.find_elements(By.XPATH, _CHAT_ROW_XPATH)
                for ch in chats[:25]:
                    try:
                        # Check for unread badge
                        badge_els = ch.find_elements(
                            By.XPATH,
                            ".//span[contains(@aria-label, 'unread')] | "
                            ".//div[contains(@aria-label, 'unread')] | "
                            ".//span[@data-icon='unread-count'] | "
                            ".//span[contains(@class, 'badge')]"
                        )
                        unread_count = 1
                        if badge_els:
                            try:
                                count_text = badge_els[0].text.strip()
                                if count_text.isdigit():
                                    unread_count = int(count_text)
                            except Exception:
                                pass
                        else:
                            # Not unread
                            continue

                        # Extract name
                        name = ""
                        title_els = ch.find_elements(By.XPATH, ".//span[@title]")
                        if title_els:
                            name = title_els[0].get_attribute("title") or title_els[0].text.strip()

                        # Extract snippet
                        snippet = ""
                        snippet_els = ch.find_elements(
                            By.XPATH,
                            ".//span[contains(@class, 'selectable-text')] | .//span[@dir='ltr']"
                        )
                        if snippet_els:
                            snippet = snippet_els[-1].text.strip()

                        if name:
                            items.append({
                                "sender": name,
                                "count": unread_count,
                                "snippet": snippet,
                            })
                    except Exception:
                        continue
            except Exception as e:
                logger.warning("get_unread_messages scan error: %s", e)

        return items

    # ==================================================================
    # READ CHAT HISTORY
    # ==================================================================

    def read_latest_messages(self, contact_name: Optional[str] = None, count: int = 5) -> List[Dict[str, Any]]:
        """
        Read the last `count` messages from the active or specified chat.
        Returns list of dicts: [{"text": text, "is_outgoing": bool, "time": timestamp}]
        """
        messages: List[Dict[str, Any]] = []
        if not self.is_running():
            return messages

        with self._driver_lock:
            try:
                if contact_name:
                    # Search and open chat
                    search_bar = self._find_search_bar(timeout=5.0)
                    if search_bar:
                        search_bar.click()
                        search_bar.send_keys(Keys.CONTROL + "a")
                        search_bar.send_keys(Keys.BACKSPACE)
                        search_bar.send_keys(contact_name)
                        time.sleep(1.0)
                        search_bar.send_keys(Keys.ENTER)
                        time.sleep(1.0)

                # Scan message bubbles in the main conversation view
                bubbles = self.driver.find_elements(
                    By.XPATH,
                    "//div[contains(@class, 'message-in') or contains(@class, 'message-out') or @role='row']"
                )
                for b in bubbles[-count:]:
                    try:
                        text_els = b.find_elements(By.XPATH, ".//span[contains(@class, 'selectable-text')]")
                        if not text_els:
                            continue
                        msg_text = text_els[0].text.strip()
                        if not msg_text:
                            continue

                        b_class = b.get_attribute("class") or ""
                        is_out = "message-out" in b_class

                        time_els = b.find_elements(By.XPATH, ".//div[contains(@class, 'copyable-text')]")
                        msg_time = ""
                        if time_els:
                            msg_time = time_els[0].get_attribute("data-pre-plain-text") or ""

                        messages.append({
                            "text": msg_text,
                            "is_outgoing": is_out,
                            "time_info": msg_time,
                        })
                    except Exception:
                        continue

            except Exception as e:
                logger.warning("read_latest_messages error: %s", e)

        return messages

    # ==================================================================
    # INCOMING MESSAGE LISTENER
    # ==================================================================

    def set_incoming_callback(self, cb: Callable[[str, str], None]):
        self._callback = cb

    def listen_incoming(self, poll_interval: float = 3.0):
        """Start background daemon thread that checks for incoming WhatsApp messages."""
        if not SELENIUM_AVAILABLE:
            raise RuntimeError("Selenium not available.")

        if self._running:
            logger.info("WhatsApp incoming listener is already running.")
            return

        self._running = True

        def _loop():
            logger.info("WhatsApp incoming listener thread started.")
            while self._running:
                try:
                    if self.is_logged_in():
                        unread_list = self.get_unread_messages()
                        for item in unread_list:
                            sender = item.get("sender", "")
                            snippet = item.get("snippet", "")
                            key = f"{sender}:{snippet}"

                            if key not in self._seen_messages and snippet:
                                self._seen_messages.add(key)
                                if len(self._seen_messages) > 1000:
                                    self._seen_messages.clear()

                                if self._callback:
                                    try:
                                        self._callback(sender, snippet)
                                    except Exception as cb_err:
                                        logger.exception("Incoming callback error: %s", cb_err)

                except Exception as loop_err:
                    logger.debug("Incoming listener iteration: %s", loop_err)

                time.sleep(poll_interval)

        self._listen_thread = threading.Thread(
            target=_loop, name="WAIncomingListener", daemon=True
        )
        self._listen_thread.start()


# ── Global instance ───────────────────────────────────────────────────
whatsapp_manager = WhatsAppManager()
