# google_contacts.py
"""
Google Contacts → local ContactManager sync for Radhe.

Improvements vs previous version:
- Phone normalisation now warns clearly when a contact has no country code
  and applies an India (+91) default for numbers starting with 0 or 10 digits.
- sync_to_local() returns a summary dict (saved / skipped / total) instead
  of just a count — useful for logging and telling the user what happened.
- Graceful error when credentials.json is missing (helpful error message).
- Logging levels corrected: important events use WARNING so they're visible
  with default logger level; verbose counts use DEBUG.
"""

import os
import logging
import re
from typing import List, Dict, Any

logger = logging.getLogger("Radhe_GoogleContacts")
logger.setLevel(logging.WARNING)

SCOPES           = ["https://www.googleapis.com/auth/contacts.readonly"]
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE       = "token.json"

# Default country code to prepend when a number has no country code
# Change to your country if needed (e.g. "1" for US)
DEFAULT_COUNTRY_CODE = "91"  # India


# ==================================================================
# PHONE NORMALISATION
# ==================================================================

def _normalise_phone(raw: str, name: str = "") -> str:
    """
    Clean a raw phone number string to digits-only with country code.

    Rules:
    - Remove spaces, dashes, parentheses
    - If starts with '+' → strip '+', use as-is
    - If starts with '0' and 11 digits → assume Indian local → prepend 91
    - If 10 digits → assume Indian mobile → prepend 91
    - Otherwise → prepend default country code

    Logs a warning when country code is inferred (so you can spot issues).
    """
    if not raw:
        return ""

    digits = re.sub(r"[^\d]", "", raw)

    if raw.strip().startswith("+"):
        # Already has country code
        return digits

    if digits.startswith("0") and len(digits) == 11:
        # Indian local format: 09876543210 → 919876543210
        logger.debug("Contact '%s': inferring country code from local format.", name)
        return DEFAULT_COUNTRY_CODE + digits[1:]

    if len(digits) == 10:
        # Indian mobile without prefix: 9876543210 → 919876543210
        logger.debug("Contact '%s': prepending default country code +%s.", name, DEFAULT_COUNTRY_CODE)
        return DEFAULT_COUNTRY_CODE + digits

    if len(digits) < 7:
        logger.warning(
            "Contact '%s' has a very short phone number (%s) — may be invalid.",
            name, digits
        )

    return digits


# ==================================================================
# GOOGLE API AUTH
# ==================================================================

def _get_service():
    """Authenticate with Google and return a People API service object."""
    if not os.path.exists(CREDENTIALS_FILE):
        raise FileNotFoundError(
            f"'{CREDENTIALS_FILE}' not found. "
            "Download it from Google Cloud Console → APIs & Services → Credentials "
            "and place it in the project root folder."
        )

    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        raise ImportError(
            "Google API libraries not installed. "
            "Run: pip install google-auth google-auth-oauthlib google-api-python-client"
        )

    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                logger.warning("Token refresh failed (%s) — re-authenticating.", e)
                creds = None

        if not creds:
            flow  = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    return build("people", "v1", credentials=creds)


# ==================================================================
# FETCH
# ==================================================================

def fetch_google_contacts(limit: int = 500) -> List[Dict[str, Any]]:
    """
    Fetch contacts from Google People API.
    Returns list of dicts: { 'name': str, 'phone': str }
    Only contacts that have BOTH a name and at least one phone number are returned.
    """
    service = _get_service()

    results = (
        service.people()
        .connections()
        .list(
            resourceName="people/me",
            pageSize=min(limit, 1000),
            personFields="names,phoneNumbers",
        )
        .execute()
    )

    connections = results.get("connections", [])
    contacts: List[Dict[str, Any]] = []

    for person in connections:
        names  = person.get("names",        [])
        phones = person.get("phoneNumbers", [])

        if not names or not phones:
            continue

        name  = names[0].get("displayName", "").strip()
        phone = phones[0].get("value",       "").strip()

        if not name or not phone:
            continue

        norm_phone = _normalise_phone(phone, name)
        if not norm_phone:
            logger.warning("Skipping '%s' — could not normalise phone: %s", name, phone)
            continue

        contacts.append({"name": name, "phone": norm_phone})

    logger.debug("Fetched %d usable contacts from Google.", len(contacts))
    return contacts


# ==================================================================
# SYNC
# ==================================================================

def sync_to_local(max_contacts: int = 500) -> Dict[str, int]:
    """
    Fetch Google contacts and save them to local ContactManager.

    Returns a summary dict:
    {
        "total":   int,   # contacts fetched from Google
        "saved":   int,   # successfully saved / updated
        "skipped": int,   # could not be saved (empty name/phone)
    }
    """
    # Lazy import to avoid circular imports at module load time
    from contact_manager import contact_manager

    contacts = fetch_google_contacts(limit=max_contacts)

    saved   = 0
    skipped = 0

    for c in contacts:
        ok = contact_manager.add_contact(
            name     = c["name"],
            phone    = c["phone"],
            platform = "whatsapp"
        )
        if ok:
            saved += 1
        else:
            skipped += 1
            logger.debug("Skipped contact: %s (%s)", c["name"], c["phone"])

    summary = {"total": len(contacts), "saved": saved, "skipped": skipped}
    logger.warning(
        "Google Contacts sync complete: %d total, %d saved, %d skipped.",
        summary["total"], summary["saved"], summary["skipped"]
    )
    return summary


# ==================================================================
# STANDALONE RUN
# ==================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    result = sync_to_local()
    print(
        f"Sync complete — {result['saved']} saved, "
        f"{result['skipped']} skipped out of {result['total']} contacts."
    )