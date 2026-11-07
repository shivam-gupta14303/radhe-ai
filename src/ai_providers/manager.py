# src/ai_providers/manager.py
"""
AIProviderManager for Radhe.

Features:
- Unified routing across OpenAI, Anthropic, Gemini, Groq, and Ollama.
- Runtime provider & model switching without application restart.
- BYOK (Bring Your Own Key) management with masked display and local persistence.
- Automatic fallback system with transparency and user consent controls.
- Health checks and connection status reporting.
"""

import os
import json
import logging
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from config import DATA_DIR
from .base_provider import BaseAIProvider
from .openai_provider import OpenAIProvider
from .anthropic_provider import ClaudeProvider
from .gemini_provider import GeminiProvider
from .groq_provider import GroqProvider
from .ollama_provider import OllamaProvider

logger = logging.getLogger("Radhe_AIManager")
logger.setLevel(logging.INFO)

AI_SETTINGS_FILE = DATA_DIR / "ai_settings.json"
_lock = threading.Lock()


class AIProviderManager:

    def __init__(self, settings_file: Path = AI_SETTINGS_FILE):
        self.settings_file = Path(settings_file)
        self.providers: Dict[str, BaseAIProvider] = {
            "openai":    OpenAIProvider(),
            "anthropic": ClaudeProvider(),
            "gemini":    GeminiProvider(),
            "groq":      GroqProvider(),
            "ollama":    OllamaProvider(),
        }

        # Defaults
        self.active_provider_name = "groq"
        self.default_provider_name = "groq"
        self.enable_fallback = True
        self.fallback_provider_name = "ollama"
        self.task_routing: Dict[str, str] = {
            "general": "default",
            "reasoning": "anthropic",
            "vision": "gemini",
            "fast": "groq",
            "offline": "ollama",
        }

        self._load_settings()

    # ==================================================================
    # SETTINGS PERSISTENCE
    # ==================================================================

    def _load_settings(self) -> None:
        """Load user configurations from ai_settings.json or apply defaults."""
        if not self.settings_file.exists():
            self._save_settings()
            return

        with _lock:
            try:
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                self.active_provider_name = data.get("active_provider", "groq")
                self.default_provider_name = data.get("default_provider", "groq")
                self.enable_fallback = data.get("enable_fallback", True)
                self.fallback_provider_name = data.get("fallback_provider", "ollama")
                self.task_routing.update(data.get("task_routing", {}))

                prov_data = data.get("providers", {})
                for name, p_inst in self.providers.items():
                    p_info = prov_data.get(name, {})
                    sel_model = p_info.get("selected_model")
                    if sel_model:
                        p_inst.set_selected_model(sel_model)
                    key = p_info.get("api_key")
                    if not key:
                        try:
                            from security import vault
                            key = vault.get_secret(f"{name}_api_key")
                        except Exception:
                            key = None
                    if key:
                        p_inst.set_api_key(key)

                logger.info(
                    "AIProviderManager loaded. Active: %s (%s)",
                    self.active_provider_name,
                    self.get_active_model()
                )
            except Exception as e:
                logger.warning("Could not read ai_settings.json, using defaults: %s", e)

    def _save_settings(self) -> None:
        """Persist current settings to ai_settings.json."""
        with _lock:
            try:
                data = {
                    "active_provider": self.active_provider_name,
                    "default_provider": self.default_provider_name,
                    "enable_fallback": self.enable_fallback,
                    "fallback_provider": self.fallback_provider_name,
                    "task_routing": self.task_routing,
                    "providers": {}
                }
                for name, p_inst in self.providers.items():
                    data["providers"][name] = {
                        "selected_model": p_inst.get_selected_model(),
                        "api_key": p_inst.get_api_key() or ""
                    }

                self.settings_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self.settings_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4)
            except Exception as e:
                logger.error("Failed to save ai_settings.json: %s", e)

    # ==================================================================
    # PROVIDER & MODEL SELECTION (HOT-SWITCHING)
    # ==================================================================

    def get_active_provider(self) -> BaseAIProvider:
        """Return the currently active provider instance."""
        return self.providers.get(self.active_provider_name) or self.providers["groq"]

    def get_active_provider_name(self) -> str:
        return self.active_provider_name

    def get_active_model(self) -> str:
        return self.get_active_provider().get_selected_model()

    def set_active_provider(self, provider_name: str, model_name: Optional[str] = None) -> Tuple[bool, str]:
        """
        Switch active AI provider at runtime without restarting Radhe.
        """
        clean_name = provider_name.strip().lower()
        # Aliases
        if clean_name in ("chatgpt", "gpt"):
            clean_name = "openai"
        elif clean_name in ("claude",):
            clean_name = "anthropic"
        elif clean_name in ("google",):
            clean_name = "gemini"

        if clean_name not in self.providers:
            available = ", ".join(self.providers.keys())
            return False, f"Unknown AI provider '{provider_name}'. Available providers: {available}."

        self.active_provider_name = clean_name
        prov = self.providers[clean_name]

        if model_name:
            prov.set_selected_model(model_name)

        self._save_settings()
        msg = f"Radhe AI provider switched to {clean_name.capitalize()} (Model: {prov.get_selected_model()})."
        logger.info(msg)
        return True, msg

    def set_model(self, model_name: str, provider_name: Optional[str] = None) -> Tuple[bool, str]:
        """Change the selected model for a provider (defaults to active provider)."""
        target_name = (provider_name or self.active_provider_name).strip().lower()
        if target_name not in self.providers:
            return False, f"Unknown provider '{target_name}'."

        prov = self.providers[target_name]
        ok = prov.set_selected_model(model_name)
        if ok:
            self._save_settings()
            return True, f"Model for {target_name.capitalize()} set to '{model_name}'."
        return False, f"Invalid model '{model_name}' for {target_name.capitalize()}."

    # ==================================================================
    # BYOK (API KEY) MANAGEMENT
    # ==================================================================

    def set_api_key(self, provider_name: str, api_key: str) -> Tuple[bool, str]:
        """Set user API key for a provider."""
        p_name = provider_name.strip().lower()
        if p_name not in self.providers:
            return False, f"Provider '{provider_name}' not found."

        self.providers[p_name].set_api_key(api_key)
        try:
            from security import vault
            vault.set_secret(f"{p_name}_api_key", api_key)
        except Exception:
            pass
        self._save_settings()
        return True, f"API key for {p_name.capitalize()} updated securely."

    def remove_api_key(self, provider_name: str) -> Tuple[bool, str]:
        """Remove API key for a provider."""
        p_name = provider_name.strip().lower()
        if p_name not in self.providers:
            return False, f"Provider '{provider_name}' not found."

        self.providers[p_name].set_api_key("")
        try:
            from security import vault
            vault.delete_secret(f"{p_name}_api_key")
        except Exception:
            pass
        self._save_settings()
        return True, f"API key for {p_name.capitalize()} removed."

    # ==================================================================
    # HEALTH CHECK & STATUS REPORT
    # ==================================================================

    def test_provider(self, provider_name: str) -> Dict[str, Any]:
        """Test API connection to a specific provider."""
        p_name = provider_name.strip().lower()
        if p_name not in self.providers:
            return {"status": "error", "message": f"Unknown provider '{provider_name}'", "latency_ms": 0}
        return self.providers[p_name].check_health()

    def get_all_provider_status(self) -> Dict[str, Any]:
        """Return comprehensive status for all providers for UI & settings."""
        out = {
            "active_provider": self.active_provider_name,
            "default_provider": self.default_provider_name,
            "enable_fallback": self.enable_fallback,
            "fallback_provider": self.fallback_provider_name,
            "providers": {}
        }
        for name, p in self.providers.items():
            out["providers"][name] = {
                "name": name,
                "display_name": {
                    "openai": "OpenAI (ChatGPT)",
                    "anthropic": "Anthropic (Claude)",
                    "gemini": "Google (Gemini)",
                    "groq": "Groq (Hosted LLaMA)",
                    "ollama": "Ollama (Local Models)",
                }.get(name, name.capitalize()),
                "selected_model": p.get_selected_model(),
                "supported_models": p.list_supported_models(),
                "has_key": bool(p.get_api_key()),
                "masked_key": p.get_masked_api_key(),
                "is_active": (name == self.active_provider_name)
            }
        return out

    # ==================================================================
    # CORE GENERATION & FALLBACK PIPELINE
    # ==================================================================

    def generate(self, prompt: str, meta: Optional[Dict[str, Any]] = None, task_type: Optional[str] = None) -> str:
        """
        Unified generation pipeline:
        1. Selects primary provider (via task_routing or active_provider).
        2. Calls primary provider.
        3. If primary fails and enable_fallback is True, executes fallback.
        """
        meta = meta or {}
        if "memory_context" not in meta:
            try:
                from memory import memory_manager
                u_id = meta.get("user_id", "default")
                mem_ctx = memory_manager.get_relevant_context(prompt, user_id=u_id)
                if mem_ctx:
                    meta["memory_context"] = mem_ctx
            except Exception as me:
                logger.debug("Memory context fetch skipped: %s", me)
        # Route to appropriate provider based on task type if configured
        target_name = self.active_provider_name
        if task_type and task_type in self.task_routing:
            route_val = self.task_routing[task_type]
            if route_val != "default" and route_val in self.providers:
                target_name = route_val

        primary_provider = self.providers.get(target_name) or self.get_active_provider()
        response = primary_provider.generate(prompt, meta)

        if response:
            return response

        # If primary failed, check fallback
        if self.enable_fallback and self.fallback_provider_name:
            fallback_provider = self.providers.get(self.fallback_provider_name)
            if fallback_provider and fallback_provider.name != primary_provider.name:
                logger.warning(
                    "Primary AI provider '%s' failed to generate response. Triggering fallback to '%s'.",
                    primary_provider.name,
                    self.fallback_provider_name
                )
                fb_response = fallback_provider.generate(prompt, meta)
                if fb_response:
                    return fb_response

        # Final safety fallback to local Ollama if primary was cloud
        if primary_provider.name != "ollama" and self.enable_fallback:
            ollama = self.providers["ollama"]
            logger.info("Executing final offline fallback to local Ollama.")
            return ollama.generate(prompt, meta)

        return ""


# ── Global singleton ───────────────────────────────────────────────────
ai_provider_manager = AIProviderManager()
