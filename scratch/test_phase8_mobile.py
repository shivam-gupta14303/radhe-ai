import sys
from pathlib import Path
import unittest
import tempfile

# Ensure src/ is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mobile_bridge import MobileBridge
from backend_api import sync_companion_state, register_companion_device

class TestPhase8Mobile(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_mobile.db"
        self.bridge = MobileBridge(db_path=self.db_path)

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_device_registration_and_listing(self):
        reg = self.bridge.register_device(
            device_id="android_pixel_8_pro",
            device_name="Gupta's Pixel 8",
            platform="android",
            push_token="fcm_token_xyz_12345",
            biometric_enabled=True
        )
        self.assertEqual(reg["device_id"], "android_pixel_8_pro")
        self.assertEqual(reg["status"], "paired")

        devices = self.bridge.list_devices()
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0]["device_name"], "Gupta's Pixel 8")
        self.assertEqual(devices[0]["biometric_enabled"], 1)

    def test_notification_staging_and_ack(self):
        nid = self.bridge.queue_notification(
            category="whatsapp_approval",
            title="WhatsApp Draft Ready",
            body="Reply drafted for Rahul: 'Yes, on my way'",
            payload={"sender": "Rahul", "action": "approve_or_reject"},
            device_id="android_pixel_8_pro"
        )
        self.assertIsInstance(nid, int)

        pending = self.bridge.get_pending_notifications("android_pixel_8_pro")
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["title"], "WhatsApp Draft Ready")
        self.assertEqual(pending[0]["payload"]["sender"], "Rahul")

        # Acknowledge
        ok = self.bridge.acknowledge_notification(nid)
        self.assertTrue(ok)
        pending_after = self.bridge.get_pending_notifications("android_pixel_8_pro")
        self.assertEqual(len(pending_after), 0)

    def test_sync_mobile_state(self):
        # Register device
        self.bridge.register_device("test_dev_01", "Samsung S24")

        # Sync state
        state = self.bridge.sync_mobile_state("test_dev_01")
        self.assertEqual(state["device_id"], "test_dev_01")
        self.assertIn("tasks", state)
        self.assertIn("calendar_events", state)
        self.assertIn("whatsapp_approvals", state)
        self.assertIn("health", state)

    def test_fastapi_mobile_endpoints(self):
        # 1. Register endpoint
        reg = register_companion_device({
            "device_id": "test_galaxy",
            "device_name": "Galaxy Fold 6",
            "platform": "android"
        })
        self.assertEqual(reg["device_id"], "test_galaxy")

        # 2. Sync endpoint
        sync = sync_companion_state(device_id="test_galaxy")
        self.assertEqual(sync["device_id"], "test_galaxy")
        self.assertIn("tasks", sync)

    def test_android_architecture_files_exist(self):
        mobile_dir = Path("mobile")
        android_dir = mobile_dir / "android"

        self.assertTrue((mobile_dir / "README.md").exists())
        self.assertTrue((android_dir / "AndroidManifest.xml").exists())
        self.assertTrue((android_dir / "RadheApiService.kt").exists())
        self.assertTrue((android_dir / "MainActivity.kt").exists())
        self.assertTrue((android_dir / "VoiceRecorder.kt").exists())
        self.assertTrue((android_dir / "SyncWorker.kt").exists())

        # Verify manifest content
        manifest_text = (android_dir / "AndroidManifest.xml").read_text(encoding="utf-8")
        self.assertIn("RECORD_AUDIO", manifest_text)
        self.assertIn("USE_BIOMETRIC", manifest_text)

if __name__ == "__main__":
    unittest.main()
