# src/ai_providers/__init__.py
"""
Radhe AI Providers Module.
Exports BaseAIProvider, AIProviderManager, and the global singleton instance.
"""

from .base_provider import BaseAIProvider, build_radhe_system_prompt
from .openai_provider import OpenAIProvider
from .anthropic_provider import ClaudeProvider
from .gemini_provider import GeminiProvider
from .groq_provider import GroqProvider
from .ollama_provider import OllamaProvider
from .manager import AIProviderManager, ai_provider_manager

# Alias for brevity
ai_manager = ai_provider_manager

__all__ = [
    "BaseAIProvider",
    "build_radhe_system_prompt",
    "OpenAIProvider",
    "ClaudeProvider",
    "GeminiProvider",
    "GroqProvider",
    "OllamaProvider",
    "AIProviderManager",
    "ai_provider_manager",
    "ai_manager",
]
