import sys
import os
import unittest
import datetime
from pathlib import Path

# Ensure src is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "src"))

from reminder_manager import ReminderManager
from calendar_manager import CalendarManager
from daily_briefing import DailyBriefingManager
from command_parser import parser
from command_executor import CommandExecutor
from memory import MemoryManager

TEST_REMINDERS_DB = BASE_DIR / "data" / "test_reminders_phase4.db"
TEST_CALENDAR_DB  = BASE_DIR / "data" / "test_calendar_phase4.db"
TEST_MEMORY_DB    = BASE_DIR / "data" / "test_memory_phase4.db"


class TestPhase4TasksAndCalendar(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        for p in (TEST_REMINDERS_DB, TEST_CALENDAR_DB, TEST_MEMORY_DB):
            if p.exists():
                try:
                    p.unlink()
                except Exception:
                    pass

        cls.rm = ReminderManager(db_path=str(TEST_REMINDERS_DB))
        cls.cm = CalendarManager(db_path=TEST_CALENDAR_DB)
        cls.mem = MemoryManager(db_path=str(TEST_MEMORY_DB))
        cls.briefing = DailyBriefingManager()

    @classmethod
    def tearDownClass(cls):
        del cls.rm
        del cls.cm
        del cls.mem
        import gc; gc.collect()
        for p in (TEST_REMINDERS_DB, TEST_CALENDAR_DB, TEST_MEMORY_DB):
            if p.exists():
                try:
                    p.unlink()
                except Exception:
                    pass

    def test_01_reminder_priorities_and_recurrence_calc(self):
        """Test priority levels and recurrence interval calculations."""
        # 1. Recurrence calculation
        dt_str = "2026-11-09T10:00:00"  # Monday
        next_daily = self.rm._calculate_next_occurrence(dt_str, "daily")
        self.assertEqual(next_daily, "2026-11-10T10:00:00")

        next_weekly = self.rm._calculate_next_occurrence(dt_str, "weekly")
        self.assertEqual(next_weekly, "2026-11-16T10:00:00")

        # Friday to Monday weekday recurrence
        fri_str = "2026-11-13T10:00:00"  # Friday
        next_weekday = self.rm._calculate_next_occurrence(fri_str, "weekdays")
        self.assertEqual(next_weekday, "2026-11-16T10:00:00")  # Skips Sat & Sun

        # 2. Add reminder with priority and recurrence
        ok = self.rm.add_reminder("Take heart medication", "tomorrow at 8am", priority="urgent", recurrence="daily")
        self.assertTrue(ok)

        rems = self.rm.get_upcoming_reminders()
        self.assertGreater(len(rems), 0)
        self.assertEqual(rems[0][1], "Take heart medication")

    def test_02_task_crud_and_priorities(self):
        """Test task creation, listing, completion, and deletion."""
        t1_id = self.rm.add_task("Submit quarterly financial report", priority="urgent", category="work")
        t2_id = self.rm.add_task("Buy groceries for dinner", priority="low", category="personal")
        t3_id = self.rm.add_task("Review pull request #42", priority="high", category="work")

        self.assertGreater(t1_id, 0)
        self.assertGreater(t2_id, 0)
        self.assertGreater(t3_id, 0)

        # List pending tasks (should be sorted by priority: urgent first)
        tasks = self.rm.list_tasks(status="pending")
        self.assertGreaterEqual(len(tasks), 3)
        self.assertEqual(tasks[0]["priority"], "urgent")
        self.assertEqual(tasks[0]["title"], "Submit quarterly financial report")

        # Complete task by keyword
        done_ok = self.rm.complete_task("financial report")
        self.assertTrue(done_ok)

        # Check status updated
        pending_after = self.rm.list_tasks(status="pending")
        titles = [t["title"] for t in pending_after]
        self.assertNotIn("Submit quarterly financial report", titles)

        # Delete task
        del_ok = self.rm.delete_task(t2_id)
        self.assertTrue(del_ok)

        # Summary
        summary = self.rm.get_tasks_summary()
        self.assertGreaterEqual(summary["completed"], 1)

    def test_03_calendar_creation_and_conflict_detection(self):
        """Test interval-based conflict detection (A_start < B_end and A_end > B_start)."""
        now = datetime.datetime.now()
        tomorrow = now + datetime.timedelta(days=1)
        t_10am = tomorrow.replace(hour=10, minute=0, second=0).strftime("%Y-%m-%d %H:%M")
        t_11am = tomorrow.replace(hour=11, minute=0, second=0).strftime("%Y-%m-%d %H:%M")
        t_1030 = tomorrow.replace(hour=10, minute=30, second=0).strftime("%Y-%m-%d %H:%M")
        t_1130 = tomorrow.replace(hour=11, minute=30, second=0).strftime("%Y-%m-%d %H:%M")
        t_2pm  = tomorrow.replace(hour=14, minute=0, second=0).strftime("%Y-%m-%d %H:%M")

        # 1. Create primary event (10:00 - 11:00)
        res1 = self.cm.create_event("Product Strategy Sync", t_10am, end_time=t_11am, location="Room 3B")
        self.assertTrue(res1["success"])
        self.assertFalse(res1["event"]["has_conflict"])

        # 2. Create overlapping event (10:30 - 11:30 overlaps with 10:00 - 11:00)
        res2 = self.cm.create_event("Client Quick Catchup", t_1030, end_time=t_1130)
        self.assertTrue(res2["success"])
        self.assertTrue(res2["event"]["has_conflict"])
        self.assertEqual(len(res2["conflicts"]), 1)
        self.assertEqual(res2["conflicts"][0]["title"], "Product Strategy Sync")

        # 3. Create non-overlapping event (14:00 - 15:00)
        res3 = self.cm.create_event("Team Standup", t_2pm)
        self.assertTrue(res3["success"])
        self.assertFalse(res3["event"]["has_conflict"])

        # List events
        events = self.cm.get_events(limit=10)
        self.assertGreaterEqual(len(events), 3)

        # Delete event
        del_ev = self.cm.delete_event("Client Quick Catchup")
        self.assertTrue(del_ev)

    def test_04_daily_briefing_generation(self):
        """Test morning daily briefing generation across languages."""
        self.mem.set_profile_value("user_name", "Vikram")

        # English briefing
        b_en = self.briefing.generate_briefing(language="en", memory_mgr=self.mem, calendar_mgr=self.cm, reminder_mgr=self.rm)
        self.assertIn("Vikram", b_en["spoken_text"])
        self.assertIn("Good morning", b_en["spoken_text"])

        # Hindi briefing
        b_hi = self.briefing.generate_briefing(language="hi", memory_mgr=self.mem, calendar_mgr=self.cm, reminder_mgr=self.rm)
        self.assertIn("Vikram", b_hi["spoken_text"])
        self.assertIn("Shubh prabhat", b_hi["spoken_text"])

        # Hinglish briefing
        b_mixed = self.briefing.generate_briefing(language="mixed", memory_mgr=self.mem, calendar_mgr=self.cm, reminder_mgr=self.rm)
        self.assertIn("Vikram", b_mixed["spoken_text"])
        self.assertIn("Good morning", b_mixed["spoken_text"])

    def test_05_voice_parser_phase4_intents(self):
        """Test voice intent parsing for Phase 4 intents."""
        p1 = parser.parse("Radhe good morning")
        self.assertEqual(p1["intent"], "get_daily_briefing")

        p2 = parser.parse("schedule a meeting with Sharmaji tomorrow at 3pm")
        self.assertEqual(p2["intent"], "create_calendar_event")
        self.assertIn("sharmaji", p2["entities"].get("title", "").lower())

        p3 = parser.parse("what's on my calendar")
        self.assertEqual(p3["intent"], "get_calendar_events")

        p4 = parser.parse("add task prepare presentation slides")
        self.assertEqual(p4["intent"], "add_task")
        self.assertIn("prepare presentation slides", p4["entities"].get("title", ""))

        p5 = parser.parse("what are my tasks")
        self.assertEqual(p5["intent"], "list_tasks")

        p6 = parser.parse("complete task prepare presentation slides")
        self.assertEqual(p6["intent"], "complete_task")
        self.assertIn("prepare presentation slides", p6["entities"].get("task", ""))

        p7 = parser.parse("delete task prepare presentation slides")
        self.assertEqual(p7["intent"], "delete_task")

        p8 = parser.parse("cancel reminder for doctor")
        self.assertEqual(p8["intent"], "cancel_reminder")

    def test_06_command_executor_phase4_execution(self):
        """Test command execution for Phase 4 features."""
        executor = CommandExecutor()
        executor.context["reminder_manager"] = self.rm

        # 1. Add Task
        r1 = executor.execute({"intent": "add_task", "entities": {"title": "Update resume"}}, "add task Update resume")
        self.assertTrue(r1["success"])
        self.assertIn("Update resume", r1["response"])

        # 2. List Tasks
        r2 = executor.execute({"intent": "list_tasks", "entities": {}}, "what are my tasks")
        self.assertTrue(r2["success"])
        self.assertIn("Update resume", r2["response"])

        # 3. Complete Task
        r3 = executor.execute({"intent": "complete_task", "entities": {"task": "Update resume"}}, "complete task Update resume")
        self.assertTrue(r3["success"])
        self.assertIn("completed", r3["response"].lower())

        # 4. Schedule Calendar Event
        r4 = executor.execute({
            "intent": "create_calendar_event",
            "entities": {"title": "Doctor Checkup", "time": "tomorrow at 5pm"}
        }, "schedule a meeting Doctor Checkup tomorrow at 5pm")
        self.assertTrue(r4["success"])
        self.assertIn("calendar", r4["response"].lower())

        # 5. Get Daily Briefing
        r5 = executor.execute({"intent": "get_daily_briefing", "entities": {}}, "good morning")
        self.assertTrue(r5["success"])
        self.assertTrue("morning" in r5["response"].lower() or "prabhat" in r5["response"].lower())


if __name__ == "__main__":
    unittest.main()
