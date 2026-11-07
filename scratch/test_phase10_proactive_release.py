import sys
from pathlib import Path
import unittest
import tempfile
from datetime import datetime, timedelta

# Ensure src/ is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cost_tracker import CostTracker
from proactive_engine import ProactiveEngine
from calendar_manager import calendar_manager
from health_assistant import health_assistant
from mobile_bridge import mobile_bridge
import build_installer

class TestPhase10ProactiveRelease(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.stats_file = Path(self.temp_dir.name) / "test_usage.json"
        self.tracker = CostTracker(stats_file=self.stats_file)
        self.engine = ProactiveEngine()

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_cost_tracker_calculations_and_breakdown(self):
        # 1. Record OpenAI usage (1000 prompt tokens, 500 completion tokens on gpt-4o)
        res1 = self.tracker.record_usage("openai", "gpt-4o", 1000, 500)
        self.assertEqual(res1["provider"], "openai")
        self.assertEqual(res1["tokens"], 1500)
        self.assertGreater(res1["cost_usd"], 0.0)
        self.assertGreater(res1["cost_inr"], 0.0)

        # 2. Record Ollama usage (Free / Local)
        res2 = self.tracker.record_usage("ollama", "llama3.1", 2000, 1000)
        self.assertEqual(res2["cost_usd"], 0.0)
        self.assertEqual(res2["cost_inr"], 0.0)

        # 3. Summary breakdown
        summary = self.tracker.get_summary()
        self.assertEqual(summary["lifetime_tokens"], 4500)
        self.assertIn("openai", summary["providers"])
        self.assertIn("ollama", summary["providers"])

    def test_proactive_engine_evaluations(self):
        # 1. Add upcoming meeting starting in 10 minutes
        start_time = (datetime.now() + timedelta(minutes=10)).isoformat()
        end_time = (datetime.now() + timedelta(minutes=40)).isoformat()
        calendar_manager.create_event(
            title="Strategic Review",
            start_time=start_time,
            end_time=end_time,
            location="Room 3B"
        )

        meeting_alerts = self.engine.check_upcoming_meetings(window_minutes=15)
        self.assertTrue(len(meeting_alerts) >= 1)
        self.assertEqual(meeting_alerts[0]["title"], "Strategic Review")
        self.assertIn("starting in", meeting_alerts[0]["message"])

        # 2. Run evaluate_all and verify integration with mobile bridge queue
        all_alerts = self.engine.evaluate_all()
        self.assertTrue(len(all_alerts) >= 1)

    def test_build_installer_preflight_and_dist_package(self):
        # 1. Verify preflight check passes on entire codebase
        preflight_ok = build_installer.preflight_check()
        self.assertTrue(preflight_ok)

        # 2. Verify release package creation
        dist_path = build_installer.create_release_package()
        self.assertTrue(dist_path.exists())
        self.assertTrue((dist_path / "run_gui.bat").exists())
        self.assertTrue((dist_path / "run_web.bat").exists())
        self.assertTrue((dist_path / "run_backend_api.bat").exists())
        self.assertTrue((dist_path / "setup_env.bat").exists())
        self.assertTrue((dist_path / "Radhe.spec").exists())
        self.assertTrue((dist_path / "RELEASE_NOTES_v2.0.md").exists())

        # Verify release notes text
        notes = (dist_path / "RELEASE_NOTES_v2.0.md").read_text(encoding="utf-8")
        self.assertIn("RADHE AI ASSISTANT — VERSION 2.0.0 RELEASE NOTES", notes)
        self.assertIn("Phase 10: Proactive Intelligence", notes)

if __name__ == "__main__":
    unittest.main()
