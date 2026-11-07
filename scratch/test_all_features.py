# scratch/test_all_features.py
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from speech import is_wake_word_match, listen_for_wake_word
from social_media import (
    SocialMediaIntegrator,
    MODE_MONITOR,
    MODE_APPROVAL,
    MODE_AUTO_REPLY,
)
from command_parser import CommandParser
from command_executor import CommandExecutor


class TestWakeWord(unittest.TestCase):
    def test_wake_word_matches(self):
        positive = [
            "radhe", "Radhe", "HEY RADHE", "hey radhe",
            "hello radhe", "ok radhe", "radha", "hey radha",
            "radhey", "hello radhey", "sun radhe", "\u0930\u093e\u0927\u0947", "\u0930\u093e\u0927\u093e"
        ]
        for p in positive:
            self.assertTrue(is_wake_word_match(p, "radhe"), f"Expected '{p}' to match wake word")

    def test_wake_word_false_positives(self):
        negative = [
            "parade", "radio", "trade", "already", "brad", "i am ready", ""
        ]
        for p in negative:
            self.assertFalse(is_wake_word_match(p, "radhe"), f"Expected '{p}' NOT to match wake word")

    def test_listen_wake_word_stop_condition(self):
        called = False
        def should_stop():
            nonlocal called
            called = True
            return True

        # When stop_condition is True, listen_for_wake_word returns False without blocking
        with patch("speech._MIC"):
            with patch("speech.sr.Recognizer"):
                res = listen_for_wake_word(wake_word="radhe", stop_condition=should_stop)
                self.assertFalse(res)
                self.assertTrue(called)


class TestWhatsAppModes(unittest.TestCase):
    def setUp(self):
        self.integrator = SocialMediaIntegrator()
        self.mock_wa = MagicMock()
        self.integrator.whatsapp = self.mock_wa
        self.executor = CommandExecutor()
        self.integrator.connect_executor(self.executor)
        self.spoken = []
        self.integrator.set_speak_callback(lambda msg: self.spoken.append(msg))

    def test_default_mode_is_monitor(self):
        self.assertEqual(self.integrator.get_mode(), MODE_MONITOR)

    def test_mode_switching(self):
        self.integrator.set_mode("approval")
        self.assertEqual(self.integrator.get_mode(), MODE_APPROVAL)

        self.integrator.set_mode("auto-reply")
        self.assertEqual(self.integrator.get_mode(), MODE_AUTO_REPLY)

        self.integrator.set_mode("monitor")
        self.assertEqual(self.integrator.get_mode(), MODE_MONITOR)

    def test_mode_monitor_never_replies(self):
        self.integrator.set_mode(MODE_MONITOR)
        self.integrator._default_incoming_handler("Alice", "Hello there!")

        # WhatsApp send should NEVER be called
        self.mock_wa.send_to_contact_name.assert_not_called()
        self.mock_wa.send_message.assert_not_called()
        # Announcement spoken to user
        self.assertTrue(any("Alice" in s for s in self.spoken))

    def test_mode_approval_stages_reply_and_sends_on_confirm(self):
        self.integrator.set_mode(MODE_APPROVAL)
        self.integrator.generate_reply = MagicMock(return_value="Drafted reply text")

        self.integrator._default_incoming_handler("Bob", "Are you available?")

        # In Approval mode, WhatsApp send is NOT called yet
        self.mock_wa.send_to_contact_name.assert_not_called()

        # Approval draft is staged in executor context
        pending = self.executor.context.get("pending_whatsapp_approval")
        self.assertIsNotNone(pending)
        self.assertEqual(pending["sender"], "Bob")
        self.assertEqual(pending["reply"], "Drafted reply text")
        self.assertTrue(self.executor.context.get("awaiting_whatsapp_approval"))

        # User confirms: "yes send it"
        with patch("command_executor.messaging_service.send") as mock_msg_send:
            mock_msg_send.return_value = "Message sent to Bob on WhatsApp."
            res = self.executor.execute({"intent": "confirm_whatsapp_reply"}, "yes send it")
            mock_msg_send.assert_called_once_with(platform="whatsapp", contact_name="Bob", message="Drafted reply text")
            self.assertIn("Message sent to Bob", res.get("text", ""))

        # Context is now cleared
        self.assertNotIn("pending_whatsapp_approval", self.executor.context)
        self.assertNotIn("awaiting_whatsapp_approval", self.executor.context)

    def test_mode_approval_discards_on_cancel(self):
        self.integrator.set_mode(MODE_APPROVAL)
        self.integrator.generate_reply = MagicMock(return_value="Drafted reply text")

        self.integrator._default_incoming_handler("Bob", "Are you available?")
        self.assertIsNotNone(self.executor.context.get("pending_whatsapp_approval"))

        # User cancels: "no, don't send"
        with patch("command_executor.messaging_service.send") as mock_msg_send:
            res = self.executor.execute({"intent": "cancel"}, "no don't send")
            mock_msg_send.assert_not_called()
            self.assertIn("discarded", res.get("text", "").lower())

        self.assertNotIn("pending_whatsapp_approval", self.executor.context)

    def test_mode_auto_reply_sends_automatically(self):
        self.integrator.set_mode(MODE_AUTO_REPLY)
        self.integrator.generate_reply = MagicMock(return_value="Automated reply text")
        self.mock_wa.send_to_contact_name.return_value = True

        self.integrator._default_incoming_handler("Charlie", "Hello Radhe")

        # Automatically sent
        self.mock_wa.send_to_contact_name.assert_called_once_with("Charlie", "Automated reply text")
        self.assertTrue(any("Auto-replied" in s for s in self.spoken))


class TestParserAndExecutorModeCommands(unittest.TestCase):
    def setUp(self):
        self.parser = CommandParser()
        self.executor = CommandExecutor()

    def test_parser_set_whatsapp_mode(self):
        p1 = self.parser.parse("set whatsapp mode to approval")
        self.assertEqual(p1.get("intent"), "set_whatsapp_mode")
        self.assertEqual(p1.get("entities", {}).get("mode"), "approval")

        p2 = self.parser.parse("enable auto reply")
        self.assertEqual(p2.get("intent"), "set_whatsapp_mode")
        self.assertEqual(p2.get("entities", {}).get("mode"), "auto_reply")

        p3 = self.parser.parse("disable auto reply")
        self.assertEqual(p3.get("intent"), "set_whatsapp_mode")
        self.assertEqual(p3.get("entities", {}).get("mode"), "monitor")

        p4 = self.parser.parse("check whatsapp mode")
        self.assertEqual(p4.get("intent"), "get_whatsapp_mode")

    def test_executor_set_and_get_whatsapp_mode(self):
        from social_media import social_integrator

        # Test setting mode to approval
        res1 = self.executor.execute({"intent": "set_whatsapp_mode", "entities": {"mode": "approval"}}, "set mode to approval")
        self.assertEqual(social_integrator.get_mode(), "approval")
        self.assertIn("Approval", res1.get("text", ""))

        # Test querying mode
        res2 = self.executor.execute({"intent": "get_whatsapp_mode", "entities": {}}, "what is the whatsapp mode")
        self.assertIn("approval", res2.get("text", "").lower())

        # Reset back to default monitor
        self.executor.execute({"intent": "set_whatsapp_mode", "entities": {"mode": "monitor"}}, "set mode to monitor")
        self.assertEqual(social_integrator.get_mode(), "monitor")


class TestShutdownAndSilenceState(unittest.TestCase):
    @patch("radhe.social_integrator")
    @patch("radhe.ReminderManager")
    @patch("radhe.speak")
    @patch("radhe.listen_for_wake_word")
    def test_bug1_shutdown_cleanup(self, mock_listen, mock_speak, mock_rm_cls, mock_social):
        mock_rm_inst = MagicMock()
        mock_rm_cls.return_value = mock_rm_inst
        mock_listen.side_effect = KeyboardInterrupt

        import radhe
        radhe.run()

        # Both reminder manager and social integrator must have stop() called
        mock_rm_inst.stop.assert_called_once()
        mock_social.stop.assert_called_once()

    @patch("radhe.social_integrator")
    @patch("radhe.ReminderManager")
    @patch("radhe.speak")
    @patch("radhe.listen_for_wake_word")
    @patch("radhe.capture_multi_commands")
    def test_bug2_silence_retry_preserves_state(self, mock_capture, mock_listen, mock_speak, mock_rm_cls, mock_social):
        mock_listen.return_value = True
        # Turn 1: user initiates sending message without contact
        # Turn 2: silence (empty list) -> should retry and keep state
        # Turn 3: user provides contact
        # Turn 4: user provides message
        # Turn 5: KeyboardInterrupt to exit
        mock_capture.side_effect = [
            ["send message"],
            [],
            ["Rohit"],
            ["Hello Rohit"],
            KeyboardInterrupt
        ]

        import radhe
        with patch.object(radhe.engine, "handle") as mock_engine_handle:
            mock_engine_handle.return_value = None
            radhe.run()

        # Check spoken messages
        spoken_calls = [c[0][0] for c in mock_speak.call_args_list]
        # Should ask who to send to
        self.assertTrue(any("Who should I send" in s or "Kisko" in s for s in spoken_calls))
        # Silence retry should have occurred without immediately cancelling
        self.assertNotIn("No response received. Cancelled.", spoken_calls)


if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if not result.wasSuccessful():
        sys.exit(1)
