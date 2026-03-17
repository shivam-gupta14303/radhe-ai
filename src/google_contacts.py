# google_contacts.py
"""
Google Contacts → local ContactManager sync
- Reads contacts from your Google account using People API
- Saves them into data/contacts.db via ContactManager
"""

import logging
from typing import List

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from src.contact_manager import contact_manager

logger = logging.getLogger("Radhe_GoogleContacts")
# Pehle INFO tha, ab WARNING ki wajah se Info/Debug logs console pe nahi aayenge.
logger.setLevel(logging.WARNING)

# Only need read-only access to contacts
SCOPES = ["https://www.googleapis.com/auth/contacts.readonly"]

CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"


def _get_service():
    """Authenticate and return People API service."""
    creds = None
    try:
        # Load saved token if exists
        from google.auth.transport.requests import Request
        import os

        if os.path.exists(TOKEN_FILE):
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        # If no valid creds, do OAuth flow
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    CREDENTIALS_FILE, SCOPES
                )
                creds = flow.run_local_server(port=0)
            with open(TOKEN_FILE, "w") as token:
                token.write(creds.to_json())

        service = build("people", "v1", credentials=creds)
        return service
    except Exception as e:
        logger.exception("Failed to build People API service: %s", e)
        raise


def fetch_google_contacts(limit: int = 500) -> List[dict]:
    """
    Fetch contacts from Google People API.
    Returns list of dicts: { 'name': ..., 'phone': ... }
    """
    service = _get_service()
    results = (
        service.people()
        .connections()
        .list(
            resourceName="people/me",
            pageSize=limit,
            personFields="names,phoneNumbers",
        )
        .execute()
    )
    connections = results.get("connections", [])
    contacts = []

    for person in connections:
        names = person.get("names", [])
        phones = person.get("phoneNumbers", [])
        if not phones or not names:
            continue

        name = names[0].get("displayName", "").strip()
        phone = phones[0].get("value", "").strip()
        phone = phone.replace(" ", "").replace("-", "")

        if not name or not phone:
            continue

        contacts.append({"name": name, "phone": phone})

    # Pehle INFO tha, ab DEBUG (aur logger WARNING pe hai, to ye dikhega hi nahi)
    logger.debug("Fetched %d contacts from Google", len(contacts))
    return contacts


def sync_to_local(max_contacts: int = 500) -> int:
    """
    Fetch contacts from Google and store in local ContactManager.
    Returns number of contacts successfully saved/updated.
    """
    contacts = fetch_google_contacts(limit=max_contacts)
    saved = 0
    for c in contacts:
        name = c["name"]
        phone = c["phone"]
        # Normalize name: lowercase for lookup
        ok = contact_manager.add_contact(name, phone, "whatsapp")
        if ok:
            saved += 1

    # Ye bhi DEBUG kar diya
    logger.debug("Synced %d contacts into local DB", saved)
    return saved


if __name__ == "__main__":
    count = sync_to_local()
    # Debug level, default run me ye bhi console pe nahi dikhega
    logger.debug("Total contacts synced: %d", count)
