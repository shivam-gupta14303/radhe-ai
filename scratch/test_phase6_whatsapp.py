import sys
from pathlib import Path
import unittest
from datetime import datetime, timedelta

# Ensure src/ is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from contact_manager import ContactManager
from social_media import social_integrator, SocialMediaIntegrator
import social_media
from command_parser import parser
from command_executor import CommandExecutor

class TestPhase6WhatsApp(unittest.TestCase):
    def setUp(self):
        self.test_db = Path("data/test_phase6_contacts.db")
        if self.test_db.exists():
            try:
                self.test_db.unlink()
            except Exception:
                pass
        self.cm = ContactManager(db_path=self.test_db)
        self.integrator = SocialMediaIntegrator()
        social_media.contact_manager = self.cm

    def tearDown(self):
        try:
            if self.test_db.exists():
                self.test_db.unlink()
        except Exception:
            pass

    def test_contact_relationship_lookup(self):
        # Add contact with relationship
        self.cm.add_contact(
            name="Sunita Sharma",
            phone="+919876543210",
            relationship="mother",
            email="sunita@example.com",
            notes="Call in morning"
        )
        
        # Test lookup by direct name
        c1 = self.cm.get_contact("Sunita Sharma")
        self.assertIsNotNone(c1)
        self.assertEqual(c1["relationship"], "mother")
        self.assertEqual(c1["phone"], "919876543210")
        
        # Test lookup by alias/relationship
        c2 = self.cm.get_contact("mother")
        self.assertIsNotNone(c2)
        self.assertEqual(c2["name"], "Sunita Sharma")

        c3 = self.cm.get_contact("mom")
        self.assertIsNotNone(c3)
        self.assertEqual(c3["name"], "Sunita Sharma")

        c4 = self.cm.get_contact("maa")
        self.assertIsNotNone(c4)
        self.assertEqual(c4["name"], "Sunita Sharma")

    def test_scheduled_messages_crud(self):
        target_time = (datetime.now() + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
        msg_id = self.cm.schedule_message("Rahul", "Meeting in 2 hours", target_time)
        self.assertIsInstance(msg_id, int)

        # List scheduled messages
        pending = self.cm.list_scheduled_messages(status="pending")
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["recipient"], "Rahul")
        self.assertEqual(pending[0]["message"], "Meeting in 2 hours")

        # Mark sent
        ok = self.cm.mark_message_sent(msg_id)
        self.assertTrue(ok)
        pending_after = self.cm.list_scheduled_messages(status="pending")
        self.assertEqual(len(pending_after), 0)

        # Schedule another and cancel
        msg_id2 = self.cm.schedule_message("Priya", "Happy Birthday", target_time)
        canceled = self.cm.cancel_scheduled_message(msg_id2)
        self.assertTrue(canceled)
        cancelled_list = self.cm.list_scheduled_messages(status="cancelled")
        self.assertEqual(len(cancelled_list), 1)

    def test_approval_workflow(self):
        executor = CommandExecutor()
        self.integrator.connect_executor(executor)

        # Stage pending reply
        executor.context["pending_whatsapp_approval"] = {
            "sender": "Aman",
            "message": "Are you coming?",
            "draft": "Yes, I will be there by 6 PM.",
            "timestamp": datetime.now().isoformat()
        }
        executor.context["awaiting_whatsapp_approval"] = True

        approvals = self.integrator.get_pending_approvals()
        self.assertEqual(len(approvals), 1)
        self.assertEqual(approvals[0]["contact"], "Aman")

        # Edit pending reply
        edit_msg = self.integrator.edit_pending_reply("Yes, reaching at 6:30 PM.")
        self.assertIn("Updated draft for Aman", edit_msg)
        self.assertEqual(executor.context["pending_whatsapp_approval"]["draft"], "Yes, reaching at 6:30 PM.")

        # Reject reply
        reject_msg = self.integrator.reject_pending_reply()
        self.assertIn("Discarded", reject_msg)
        self.assertIsNone(executor.context.get("pending_whatsapp_approval"))

    def test_social_integrator_scheduling_methods(self):
        res = self.integrator.schedule_whatsapp_message("Vikram", "Don't forget the files", "tomorrow at 10am")
        self.assertIn("Scheduled WhatsApp message", res)

        listing = self.integrator.list_scheduled_whatsapp()
        self.assertIn("Vikram", listing)

        cancel_res = self.integrator.cancel_scheduled_whatsapp("Vikram")
        self.assertIn("Cancelled", cancel_res)

    def test_parser_and_executor(self):
        executor = CommandExecutor()

        # Parse schedule command
        cmd1 = parser.parse("schedule a whatsapp message to Rahul at tomorrow 5pm saying Hello Rahul")
        self.assertEqual(cmd1.get("intent"), "schedule_whatsapp_message")
        self.assertEqual(cmd1.get("entities", {}).get("contact", "").lower(), "rahul")
        self.assertIn("hello rahul", cmd1.get("entities", {}).get("message", "").lower())

        # Parse list command
        cmd2 = parser.parse("show scheduled messages")
        self.assertEqual(cmd2.get("intent"), "list_scheduled_messages")

        # Parse approval commands
        cmd3 = parser.parse("approve reply")
        self.assertEqual(cmd3.get("intent"), "approve_reply")

        cmd4 = parser.parse("mat bhejo")
        self.assertEqual(cmd4.get("intent"), "reject_reply")

        # Execute list scheduled messages
        resp = executor.execute(cmd2, "show scheduled messages")
        self.assertIsNotNone(resp)
        self.assertTrue(isinstance(resp.get("response"), str) or isinstance(resp, str))

if __name__ == "__main__":
    unittest.main()
