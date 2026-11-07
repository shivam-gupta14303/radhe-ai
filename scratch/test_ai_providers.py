# scratch/test_ai_providers.py
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ai_providers import (
    ai_provider_manager,
    BaseAIProvider,
    OpenAIProvider,
    ClaudeProvider,
    GeminiProvider,
    GroqProvider,
    OllamaProvider,
)
from command_parser import CommandParser
from command_executor import CommandExecutor
from llm_setup import llm_engine


class TestMultiAIProviders(unittest.TestCase):

    def setUp(self):
        self.mgr = ai_provider_manager

    def test_providers_registration(self):
        providers = self.mgr.providers
        self.assertIn("openai", providers)
        self.assertIn("anthropic", providers)
        self.assertIn("gemini", providers)
        self.assertIn("groq", providers)
        self.assertIn("ollama", providers)

    def test_hot_switching_providers(self):
        # Switch to OpenAI / ChatGPT
        ok, msg = self.mgr.set_active_provider("openai")
        self.assertTrue(ok)
        self.assertEqual(self.mgr.get_active_provider_name(), "openai")
        self.assertIn("Openai", msg)

        # Switch to Anthropic / Claude
        ok, msg = self.mgr.set_active_provider("claude")
        self.assertTrue(ok)
        self.assertEqual(self.mgr.get_active_provider_name(), "anthropic")

        # Switch to Gemini
        ok, msg = self.mgr.set_active_provider("gemini")
        self.assertTrue(ok)
        self.assertEqual(self.mgr.get_active_provider_name(), "gemini")

        # Switch to local Ollama
        ok, msg = self.mgr.set_active_provider("ollama")
        self.assertTrue(ok)
        self.assertEqual(self.mgr.get_active_provider_name(), "ollama")

        # Switch back to Groq
        ok, _ = self.mgr.set_active_provider("groq")
        self.assertTrue(ok)
        self.assertEqual(self.mgr.get_active_provider_name(), "groq")

    def test_model_selection(self):
        ok, msg = self.mgr.set_model("gpt-4o", "openai")
        self.assertTrue(ok)
        self.assertEqual(self.mgr.providers["openai"].get_selected_model(), "gpt-4o")

        ok, msg = self.mgr.set_model("claude-3-5-haiku-20241022", "anthropic")
        self.assertTrue(ok)
        self.assertEqual(self.mgr.providers["anthropic"].get_selected_model(), "claude-3-5-haiku-20241022")

    def test_byok_key_management_and_masking(self):
        self.mgr.set_api_key("anthropic", "sk-ant-api03-abcdef1234567890xyz")
        masked = self.mgr.providers["anthropic"].get_masked_api_key()
        self.assertTrue(masked.startswith("sk-a"))
        self.assertTrue(masked.endswith("0xyz"))
        self.assertIn("••••••••", masked)
        # Verify secret is not exposed in status
        status = self.mgr.get_all_provider_status()
        self.assertEqual(status["providers"]["anthropic"]["masked_key"], masked)

        # Remove key
        self.mgr.remove_api_key("anthropic")
        self.assertFalse(self.mgr.providers["anthropic"].get_api_key())

    def test_fallback_mechanism(self):
        self.mgr.set_active_provider("openai")
        self.mgr.enable_fallback = True
        self.mgr.fallback_provider_name = "groq"

        # Mock primary (OpenAI) failure and fallback (Groq) success
        with patch.object(self.mgr.providers["openai"], "generate", return_value=""):
            with patch.object(self.mgr.providers["groq"], "generate", return_value="Fallback response from Groq"):
                response = self.mgr.generate("Hello Radhe")
                self.assertEqual(response, "Fallback response from Groq")

        # Reset active provider
        self.mgr.set_active_provider("groq")


class TestAIParserAndExecutorIntegration(unittest.TestCase):

    def setUp(self):
        self.parser = CommandParser()
        self.executor = CommandExecutor()

    def test_parsing_provider_commands(self):
        p1 = self.parser.parse("switch AI to ChatGPT")
        self.assertEqual(p1.get("intent"), "set_ai_provider")
        self.assertEqual(p1.get("entities", {}).get("provider"), "openai")

        p2 = self.parser.parse("set AI provider to Claude")
        self.assertEqual(p2.get("intent"), "set_ai_provider")
        self.assertEqual(p2.get("entities", {}).get("provider"), "anthropic")

        p3 = self.parser.parse("use Gemini")
        self.assertEqual(p3.get("intent"), "set_ai_provider")
        self.assertEqual(p3.get("entities", {}).get("provider"), "gemini")

        p4 = self.parser.parse("switch to local ollama")
        self.assertEqual(p4.get("intent"), "set_ai_provider")
        self.assertEqual(p4.get("entities", {}).get("provider"), "ollama")

        p5 = self.parser.parse("which AI model are you using?")
        self.assertEqual(p5.get("intent"), "get_ai_provider")

        p6 = self.parser.parse("test AI connection")
        self.assertEqual(p6.get("intent"), "test_ai_connection")

    def test_executing_provider_commands(self):
        # Execute switch to Claude
        res = self.executor.execute({"intent": "set_ai_provider", "entities": {"provider": "anthropic"}}, "switch to claude")
        self.assertEqual(ai_provider_manager.get_active_provider_name(), "anthropic")
        self.assertIn("Anthropic", res.get("text", ""))

        # Execute get active provider
        res2 = self.executor.execute({"intent": "get_ai_provider", "entities": {}}, "which AI are you using")
        self.assertIn("Anthropic", res2.get("text", ""))

        # Execute switch back to Groq
        self.executor.execute({"intent": "set_ai_provider", "entities": {"provider": "groq"}}, "switch to groq")
        self.assertEqual(ai_provider_manager.get_active_provider_name(), "groq")

    def test_llm_engine_delegates_to_ai_provider_manager(self):
        with patch.object(ai_provider_manager, "generate", return_value="Delegated response via Manager") as mock_gen:
            res = llm_engine.generate("Tell me a fact", {"language": "en", "mode": "casual"})
            mock_gen.assert_called_once()
            self.assertEqual(res, "Delegated response via Manager")


if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if not result.wasSuccessful():
        sys.exit(1)
