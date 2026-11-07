import sys
import os
import unittest
import json
from pathlib import Path

# Ensure src in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "src"))

import tkinter as tk
from desktop_gui import RadheDesktopApp
from flask_server import app


class TestPhase5DesktopApplication(unittest.TestCase):

    def setUp(self):
        self.client = app.test_client()

    def test_01_desktop_gui_instantiation_and_tabs(self):
        """Test Tkinter desktop GUI structure and tab navigation."""
        try:
            root = tk.Tk()
            root.withdraw()  # headless / hide window during test
            app_gui = RadheDesktopApp(root)

            # Check all 6 tabs exist
            expected_tabs = ["dashboard", "chat", "ai_settings", "memory", "whatsapp", "calendar"]
            for tab in expected_tabs:
                self.assertIn(tab, app_gui.frames)
                self.assertIn(tab, app_gui.nav_buttons)

            # Test tab switching
            app_gui._show_tab("chat")
            self.assertEqual(app_gui.nav_buttons["chat"].cget("fg"), app_gui.colors["accent"])

            app_gui._show_tab("ai_settings")
            self.assertEqual(app_gui.nav_buttons["ai_settings"].cget("fg"), app_gui.colors["accent"])

            root.destroy()
        except tk.TclError as e:
            # If no display server available in some environments, skip GUI rendering
            self.skipTest(f"Tcl/Tk display not available: {e}")

    def test_02_flask_spa_homepage(self):
        """Test desktop web application is served at GET /."""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"RADHE", res.data)
        self.assertIn(b"Personal AI Assistant", res.data)
        self.assertIn(b"BRIEFING", res.data)

    def test_03_flask_status_and_command(self):
        """Test REST status and text command execution."""
        # Status
        res_st = self.client.get("/status")
        self.assertEqual(res_st.status_code, 200)
        data_st = res_st.get_json()
        self.assertEqual(data_st["status"], "running")

        # Command
        res_cmd = self.client.post("/command", json={"command": "what time is it"})
        self.assertEqual(res_cmd.status_code, 200)
        data_cmd = res_cmd.get_json()
        self.assertTrue(data_cmd.get("success"))
        self.assertTrue(len(data_cmd.get("response", "")) > 0)

    def test_04_flask_ai_endpoints(self):
        """Test AI provider status, switching, and connection testing."""
        # Get all providers
        res_ai = self.client.get("/api/ai")
        self.assertEqual(res_ai.status_code, 200)
        data_ai = res_ai.get_json()
        self.assertIn("providers", data_ai)
        self.assertIn("groq", data_ai["providers"])
        self.assertIn("ollama", data_ai["providers"])

        # Select provider
        res_sel = self.client.post("/api/ai/select", json={"provider": "groq", "model": "llama-3.3-70b-versatile"})
        self.assertEqual(res_sel.status_code, 200)
        self.assertTrue(res_sel.get_json()["success"])

        # Test connection
        res_test = self.client.post("/api/ai/test", json={"provider": "ollama"})
        self.assertEqual(res_test.status_code, 200)
        self.assertIn("status", res_test.get_json())

    def test_05_flask_memory_endpoints(self):
        """Test memory CRUD via REST API."""
        # Add memory
        res_add = self.client.post("/api/memory", json={"text": "User loves exploring national parks", "category": "preference"})
        self.assertEqual(res_add.status_code, 201)
        data_add = res_add.get_json()
        mem_id = data_add.get("id")
        self.assertGreater(mem_id, 0)

        # Search memory
        res_search = self.client.get("/api/memory?query=national+parks")
        self.assertEqual(res_search.status_code, 200)
        list_search = res_search.get_json()
        self.assertTrue(len(list_search) > 0)
        self.assertIn("national parks", list_search[0]["text"])

        # Delete memory
        res_del = self.client.delete(f"/api/memory/{mem_id}")
        self.assertEqual(res_del.status_code, 200)

        # Export memory
        res_exp = self.client.get("/api/memory/export")
        self.assertEqual(res_exp.status_code, 200)
        self.assertTrue(res_exp.get_json()["success"])

    def test_06_flask_tasks_and_calendar_endpoints(self):
        """Test tasks and calendar APIs."""
        # Add task
        res_t = self.client.post("/api/tasks", json={"title": "Prepare desktop release package", "priority": "high"})
        self.assertEqual(res_t.status_code, 201)
        tid = res_t.get_json()["id"]

        # List tasks
        res_list = self.client.get("/api/tasks")
        self.assertEqual(res_list.status_code, 200)
        tasks = res_list.get_json()
        self.assertTrue(any(t["id"] == tid for t in tasks))

        # Complete task
        res_done = self.client.post(f"/api/tasks/{tid}/complete")
        self.assertEqual(res_done.status_code, 200)

        # Calendar event
        res_cal = self.client.post("/api/calendar", json={"title": "Desktop App Review", "time": "tomorrow at 3pm"})
        self.assertEqual(res_cal.status_code, 201)
        cal_data = res_cal.get_json()
        self.assertTrue(cal_data["success"])

        # Daily Briefing
        res_brief = self.client.get("/api/briefing")
        self.assertEqual(res_brief.status_code, 200)
        self.assertIn("spoken_text", res_brief.get_json())

    def test_07_flask_whatsapp_endpoints(self):
        """Test WhatsApp mode endpoints."""
        res_wa = self.client.get("/api/whatsapp")
        self.assertEqual(res_wa.status_code, 200)

        res_set = self.client.post("/api/whatsapp/mode", json={"mode": "approval"})
        self.assertEqual(res_set.status_code, 200)
        self.assertEqual(res_set.get_json()["mode"], "approval")


if __name__ == "__main__":
    unittest.main()
