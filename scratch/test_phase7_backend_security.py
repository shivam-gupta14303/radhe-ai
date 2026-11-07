import sys
from pathlib import Path
import unittest
import json
import tempfile
import os

# Ensure src/ is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from security import SecretVault, AuditLogger, mask_secret
from dal import DatabaseAdapter
from backend_api import (
    get_system_status, get_ai_providers, select_ai_provider,
    set_provider_api_key, create_task, list_tasks, get_daily_briefing,
    verify_audit_integrity, SelectAIRequest, SetAPIKeyRequest, TaskCreateRequest
)

class TestPhase7BackendSecurity(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault_file = Path(self.temp_dir.name) / "test_vault.enc"
        self.audit_file = Path(self.temp_dir.name) / "test_audit.jsonl"
        self.db_file = Path(self.temp_dir.name) / "test_dal.db"

        self.vault = SecretVault(vault_path=self.vault_file, master_password="test_secure_password_123")
        self.audit = AuditLogger(log_path=self.audit_file)
        self.dal = DatabaseAdapter(sqlite_path=self.db_file)

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_mask_secret(self):
        self.assertEqual(mask_secret("sk-1234567890abcdef"), "sk-...cdef")
        self.assertEqual(mask_secret("short"), "***")
        self.assertEqual(mask_secret(""), "")
        self.assertEqual(mask_secret(None), "")

    def test_encrypted_vault_crud_and_persistence(self):
        # 1. Set secrets
        self.vault.set_secret("openai_api_key", "sk-proj-test123456789")
        self.vault.set_secret("claude_api_key", "sk-ant-test987654321")

        # 2. Retrieve secrets
        k1 = self.vault.get_secret("openai_api_key", check_env=False)
        self.assertEqual(k1, "sk-proj-test123456789")

        keys = self.vault.list_keys()
        self.assertIn("openai_api_key", keys)
        self.assertIn("claude_api_key", keys)

        # 3. Masked map
        masked = self.vault.get_masked_map()
        self.assertIn("openai_api_key", masked)
        self.assertIn("...", masked["openai_api_key"])
        self.assertNotIn("test123456789", masked["openai_api_key"])

        # 4. Persistence: New vault instance with same master password
        vault2 = SecretVault(vault_path=self.vault_file, master_password="test_secure_password_123")
        k2 = vault2.get_secret("openai_api_key", check_env=False)
        self.assertEqual(k2, "sk-proj-test123456789")

        # 5. Delete secret
        deleted = self.vault.delete_secret("openai_api_key")
        self.assertTrue(deleted)
        self.assertIsNone(self.vault.get_secret("openai_api_key", check_env=False))

    def test_cryptographic_audit_trail_and_tamper_detection(self):
        # Log several actions
        h1 = self.audit.log_action("login", "user", "success")
        h2 = self.audit.log_action("api_key_update", "user", "success", {"key": "openai_api_key"})
        h3 = self.audit.log_action("file_delete", "assistant", "success", {"file": "report.pdf"})

        self.assertEqual(len(h1), 64)
        self.assertEqual(len(h2), 64)
        self.assertEqual(len(h3), 64)

        # Verify integrity
        valid, count, msg = self.audit.verify_integrity()
        self.assertTrue(valid)
        self.assertEqual(count, 3)

        # Query recent
        entries = self.audit.query(limit=2)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[-1]["action"], "file_delete")

        # Intentional Tampering Test: modify a line in the log file
        with open(self.audit_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        tampered_entry = json.loads(lines[1])
        tampered_entry["action"] = "tampered_action"
        lines[1] = json.dumps(tampered_entry) + "\n"
        with open(self.audit_file, "w", encoding="utf-8") as f:
            f.writelines(lines)

        # Integrity verification must catch the tamper
        valid_after_tamper, index, err = self.audit.verify_integrity()
        self.assertFalse(valid_after_tamper)
        self.assertIn("Tampered entry detected", err)

    def test_database_abstraction_layer(self):
        self.dal.execute_script("""
            CREATE TABLE IF NOT EXISTS test_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                email TEXT
            );
        """)

        # Insert
        row_id = self.dal.execute("INSERT INTO test_users (username, email) VALUES (?, ?)", ("radhe_user", "radhe@example.com"))
        self.assertIsInstance(row_id, int)

        # Fetch one
        user = self.dal.fetch_one("SELECT * FROM test_users WHERE username = ?", ("radhe_user",))
        self.assertIsNotNone(user)
        self.assertEqual(user["email"], "radhe@example.com")

        # Fetch all
        all_users = self.dal.fetch_all("SELECT * FROM test_users")
        self.assertEqual(len(all_users), 1)

        # Backup
        backup_path = Path(self.temp_dir.name) / "backup.db"
        ok = self.dal.backup_to_file(backup_path)
        self.assertTrue(ok)
        self.assertTrue(backup_path.exists())

    def test_fastapi_endpoints(self):
        # 1. System status
        st = get_system_status()
        self.assertEqual(st["status"], "online")
        self.assertIn("ai", st)

        # 2. AI Providers
        provs = get_ai_providers()
        self.assertIn("groq", provs["providers"])

        # 3. Switch provider
        sw = select_ai_provider(SelectAIRequest(provider="ollama"))
        self.assertTrue(sw["success"])

        # 4. Set API key
        ak = set_provider_api_key(SetAPIKeyRequest(provider="openai", api_key="sk-test-byok-key-999"))
        self.assertTrue(ak["success"])

        # 5. Tasks CRUD via API
        tc = create_task(TaskCreateRequest(title="Test FastAPI Task", priority="high"))
        self.assertTrue(tc["success"])
        task_id = tc["task_id"]

        tl = list_tasks(status="all")
        self.assertTrue(any(t["id"] == task_id for t in tl))

        # 6. Briefing API
        br = get_daily_briefing(language="en")
        briefing_text = br["briefing"].get("spoken_text", "") if isinstance(br["briefing"], dict) else str(br["briefing"])
        self.assertIn("Good", briefing_text)

        # 7. Security audit integrity
        v = verify_audit_integrity()
        self.assertTrue(v["valid"])

if __name__ == "__main__":
    unittest.main()
