# src/ai_providers/base_provider.py
"""
Base abstract interface for all Radhe AI Providers.
Ensures universal personality, error resilience, and standardized response formats.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Generator
import logging

logger = logging.getLogger("Radhe_AIProvider")


def build_radhe_system_prompt(language: str = "en", mode: str = "neutral", memory_context: Optional[str] = None) -> str:
    """
    Universal system prompt defining Radhe's personality across all providers.
    Ensures Radhe behaves as a warm, intelligent personal companion regardless of backend model.
    """
    base = (
        "You are Radhe, a personal AI companion and assistant. "
        "You are warm, helpful, intelligent, and speak naturally like a close friend — "
        "not a formal corporate assistant or a robot. "
        "You run on the user's system and help them manage daily life, schedule, "
        "tasks, WhatsApp communications, and questions. "
        "Keep responses concise and conversational unless the user requests detailed explanations. "
        "Never say you are an AI language model from OpenAI, Anthropic, or Google. "
        "You are Radhe. Always."
    )

    if language == "hi":
        base += (
            " Respond in Hindi (Devanagari or romanised Hindi — "
            "whichever the user uses). Mix in English technical terms where natural."
        )
    elif language == "mixed":
        base += (
            " Respond in natural Hinglish — Hindi and English blended "
            "the way modern bilingual speakers talk."
        )
    else:
        base += " Respond in clear, natural English."

    if mode == "casual":
        base += " Keep the tone casual, friendly, and relaxed."
    elif mode == "formal":
        base += " Keep the tone polite, structured, and professional."

    if memory_context:
        base += f"\n\n[RELEVANT USER MEMORY & PROFILE]\n{memory_context}\nUse this context naturally without explicitly stating 'According to my memory'."

    return base


class BaseAIProvider(ABC):
    """Abstract base class for all AI model providers."""

    def __init__(self, name: str, default_model: str, supported_models: List[str]):
        self.name = name
        self.default_model = default_model
        self.supported_models = supported_models
        self.selected_model = default_model
        self._api_key: Optional[str] = None
        self._api_base: Optional[str] = None

    @abstractmethod
    def generate(self, prompt: str, meta: Optional[Dict[str, Any]] = None) -> str:
        """Generate a complete text response."""
        pass

    def stream(self, prompt: str, meta: Optional[Dict[str, Any]] = None) -> Generator[str, None, None]:
        """Stream response tokens. Default fallback yields full text if streaming unsupported."""
        full_text = self.generate(prompt, meta)
        if full_text:
            yield full_text

    @abstractmethod
    def check_health(self) -> Dict[str, Any]:
        """
        Test API connection.
        Returns: {"status": "connected" | "error" | "disconnected", "message": str, "latency_ms": float}
        """
        pass

    def list_supported_models(self) -> List[str]:
        """Return list of supported models for this provider."""
        return list(self.supported_models)

    def get_selected_model(self) -> str:
        return self.selected_model

    def set_selected_model(self, model: str) -> bool:
        if model in self.supported_models or model:
            self.selected_model = model
            return True
        return False

    def get_api_key(self) -> Optional[str]:
        return self._api_key

    def set_api_key(self, api_key: str) -> None:
        self._api_key = api_key.strip() if api_key else None

    def get_masked_api_key(self) -> str:
        key = self.get_api_key()
        if not key:
            return ""
        if len(key) <= 8:
            return "••••••••"
        return f"{key[:4]}••••••••{key[-4:]}"

    def format_history_as_messages(self, history: List[Dict[str, Any]], max_turns: int = 10) -> List[Dict[str, str]]:
        """Normalize history into standard [{"role": "user"|"assistant", "content": "..."}]."""
        messages = []
        for entry in history[-max_turns:]:
            role = entry.get("role", "user")
            text = (entry.get("text") or "").strip()
            if role in ("user", "assistant") and text:
                messages.append({"role": role, "content": text})
        return messages
