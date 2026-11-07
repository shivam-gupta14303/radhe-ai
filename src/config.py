from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

DATA_DIR.mkdir(parents=True, exist_ok=True)

# Database and state files
RADHE_MEMORY_FILE    = DATA_DIR / "radhe_memory.json"
INTENT_BOOST_FILE    = DATA_DIR / "intent_boost.json"
DECISION_MEMORY_FILE = DATA_DIR / "decision_memory.json"
FAILURE_MEMORY_FILE  = DATA_DIR / "failure_memory.json"
CONTACTS_DB_FILE     = DATA_DIR / "contacts.db"
MEMORY_DB_FILE       = DATA_DIR / "memory.db"
REMINDERS_DB_FILE    = DATA_DIR / "reminders.db"

# WhatsApp persistent browser profile directory
WHATSAPP_PROFILE_DIR = DATA_DIR / "whatsapp_profile"
WHATSAPP_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
