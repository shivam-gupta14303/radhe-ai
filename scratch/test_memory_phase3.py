import sys
import os
import unittest
from pathlib import Path

# Ensure src is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "src"))

from memory import MemoryManager, classify_memory_type
from command_parser import parser
from command_executor import CommandExecutor
from ai_providers.base_provider import build_radhe_system_prompt

TEST_DB = BASE_DIR / "data" / "test_memory_phase3.db"

class TestPhase3MemorySystem(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if TEST_DB.exists():
            try:
                TEST_DB.unlink()
            except Exception:
                pass
        cls.mem = MemoryManager(db_path=str(TEST_DB))

    @classmethod
    def tearDownClass(cls):
        del cls.mem
        import gc; gc.collect()
        if TEST_DB.exists():
            try:
                TEST_DB.unlink()
            except Exception:
                pass

    def setUp(self):
        self.mem.clear_memories()
        self.mem.clear_profile()

    def test_01_seven_tiers_and_classification(self):
        """Test auto-classification across tiers."""
        t1 = self.mem.classify_memory_type("I love eating paneer tikka and spicy food")
        self.assertEqual(t1, "preference")

        t2 = self.mem.classify_memory_type("Doctor appointment on Monday at 3pm")
        self.assertEqual(t2, "schedule")

        t3 = self.mem.classify_memory_type("Rahul is my colleague and frontend lead")
        self.assertEqual(t3, "contact")

        t4 = self.mem.classify_memory_type("Currently developing project Radhe AI desktop app")
        self.assertEqual(t4, "project")

        t5 = self.mem.classify_memory_type("Need to submit the report and buy groceries")
        self.assertEqual(t5, "task")

        t6 = self.mem.classify_memory_type("User said what is the weather today")
        self.assertEqual(t6, "short_term")

        t7 = self.mem.classify_memory_type("My hometown is Jaipur and I studied at Delhi University")
        self.assertEqual(t7, "long_term")

    def test_02_add_and_search_memories(self):
        """Test adding memories and semantic/keyword search."""
        m1 = self.mem.add_memory("My favorite food is Biryani", category="preference")
        m2 = self.mem.add_memory("Meeting with Sharmaji on Friday 4 PM", category="schedule")
        m3 = self.mem.add_memory("Working on the Android client for Radhe", category="project")

        self.assertGreater(m1["id"], 0)
        self.assertGreater(m2["id"], 0)
        self.assertGreater(m3["id"], 0)

        # Search for biryani
        res = self.mem.search_memories("biryani")
        self.assertTrue(len(res) > 0)
        self.assertIn("Biryani", res[0]["text"])

        # Category filtered search
        sched_res = self.mem.search_memories("Sharmaji", category="schedule")
        self.assertTrue(len(sched_res) > 0)
        self.assertEqual(sched_res[0]["category"], "schedule")

    def test_03_contradiction_handling(self):
        """Test contradiction detection and auto-superseding."""
        m1 = self.mem.add_memory("My favorite programming language is Python", category="preference")
        mem1 = self.mem.get_memory_by_id(m1["id"])
        self.assertEqual(mem1["is_active"], 1)

        # Later user says their favorite language is Rust
        m2 = self.mem.add_memory("My favorite programming language is Rust", category="preference")
        mem1_after = self.mem.get_memory_by_id(m1["id"])
        mem2 = self.mem.get_memory_by_id(m2["id"])

        # Old memory should be superseded or updated
        self.assertEqual(mem1_after["is_active"], 0)
        self.assertEqual(mem2["is_active"], 1)

    def test_04_edit_and_delete_and_clear(self):
        """Test editing, deleting and clearing memories."""
        m = self.mem.add_memory("Remember to buy organic milk", category="task")
        mid = m["id"]
        self.mem.edit_memory(mid, "Remember to buy almond milk")
        updated = self.mem.get_memory_by_id(mid)
        self.assertEqual(updated["text"], "Remember to buy almond milk")

        # Delete by ID
        del_ok = self.mem.delete_memory_by_id(mid)
        self.assertTrue(del_ok)
        self.assertIsNone(self.mem.get_memory_by_id(mid))

        # Clear all
        self.mem.add_memory("Fact 1")
        self.mem.add_memory("Fact 2")
        cleared_count = self.mem.clear_memories()
        self.assertEqual(cleared_count, 2)
        self.assertEqual(self.mem.count(), 0)

    def test_05_export_data(self):
        """Test JSON and Markdown export."""
        self.mem.add_memory("User prefers dark mode in all applications", category="preference")
        self.mem.add_memory("Working on Radhe assistant v2.0", category="project")
        self.mem.set_profile_value("user_name", "Aakash")

        json_path = Path(self.mem.export_data(format="json"))
        md_path = Path(self.mem.export_data(format="markdown"))

        self.assertTrue(json_path.exists())
        self.assertTrue(md_path.exists())

        json_content = json_path.read_text(encoding="utf-8")
        self.assertIn("dark mode", json_content)
        self.assertIn("Aakash", json_content)

        md_content = md_path.read_text(encoding="utf-8")
        self.assertIn("Radhe assistant v2.0", md_content)

        # Clean up export files
        try:
            json_path.unlink()
            md_path.unlink()
        except Exception:
            pass

    def test_06_profile_and_summary(self):
        """Test user profile key-values and memory stats summary."""
        self.mem.set_profile_value("location", "Mumbai")
        self.mem.set_profile_value("role", "Engineer")
        self.assertEqual(self.mem.get_profile_value("location"), "Mumbai")
        self.assertEqual(self.mem.get_profile_value("role"), "Engineer")

        summary = self.mem.get_memories_summary()
        self.assertEqual(summary["profile"]["location"], "Mumbai")

    def test_07_voice_command_parsing(self):
        """Test command parsing for memory intents."""
        p1 = parser.parse("Radhe remember that my flight is at 7 am tomorrow")
        self.assertEqual(p1["intent"], "remember_fact")
        self.assertIn("flight is at 7 am tomorrow", p1["entities"].get("fact", ""))

        p2 = parser.parse("what do you remember about my flight")
        self.assertEqual(p2["intent"], "recall_memory")
        self.assertIn("flight", p2["entities"].get("query", ""))

        p3 = parser.parse("Radhe clear all memories")
        self.assertEqual(p3["intent"], "forget_memory")

        p4 = parser.parse("Radhe export my data")
        self.assertEqual(p4["intent"], "export_memory")

    def test_08_command_executor_memory_intents(self):
        """Test execution of memory intents in CommandExecutor."""
        executor = CommandExecutor()
        executor.memory = self.mem  # use test instance

        # 1. Remember fact
        r1 = executor.execute({"intent": "remember_fact", "entities": {"fact": "my sister's birthday is on October 12"}}, "remember that my sister's birthday is on October 12")
        self.assertTrue(r1["success"])
        self.assertTrue("yaad" in r1["response"].lower() or "saved" in r1["response"].lower() or "done" in r1["response"].lower())

        # 2. Recall memory
        r2 = executor.execute({"intent": "recall_memory", "entities": {"query": "birthday"}}, "what do you remember about birthday")
        self.assertTrue(r2["success"])
        self.assertIn("October 12", r2["response"])

        # 3. Recall memory general summary
        r3 = executor.execute({"intent": "recall_memory", "entities": {}}, "show my memories")
        self.assertTrue(r3["success"])
        self.assertIn("1", r3["response"])

        # 4. Export memory
        r4 = executor.execute({"intent": "export_memory", "entities": {"format": "json"}}, "export my data")
        self.assertTrue(r4["success"])
        self.assertIn(".json", r4["response"])

        # 5. Forget memory
        r5 = executor.execute({"intent": "forget_memory", "entities": {"query": "all"}}, "clear all memories")
        self.assertTrue(r5["success"])
        self.assertEqual(self.mem.count(), 0)

    def test_09_prompt_context_injection(self):
        """Test build_radhe_system_prompt context injection."""
        ctx_text = "- Preference: User prefers vegan food\n- Schedule: Gym at 6am"
        prompt = build_radhe_system_prompt(language="en", mode="casual", memory_context=ctx_text)
        self.assertIn("[RELEVANT USER MEMORY & PROFILE]", prompt)
        self.assertIn("vegan food", prompt)
        self.assertIn("Gym at 6am", prompt)

if __name__ == "__main__":
    unittest.main()
