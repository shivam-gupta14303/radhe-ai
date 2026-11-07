# src/ai_providers/ollama_provider.py
"""
Local Ollama provider adapter for Radhe.
Supports 100% offline intelligence with models like llama3.1, mistral, phi3, qwen2.5, gemma2.
"""

import os
import time
import logging
from typing import Dict, Any, List, Optional
import requests

from .base_provider import BaseAIProvider, build_radhe_system_prompt

logger = logging.getLogger("Radhe_Ollama")

COMMON_OLLAMA_MODELS = [
    "llama3.1",
    "mistral",
    "phi3",
    "qwen2.5",
    "gemma2",
]


class OllamaProvider(BaseAIProvider):

    def __init__(self, api_base: Optional[str] = None):
        super().__init__(
            name="ollama",
            default_model="llama3.1",
            supported_models=COMMON_OLLAMA_MODELS
        )
        self.api_base = api_base or os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate").replace("/api/generate", "")

    def _format_history_for_prompt(self, history: List[Dict]) -> str:
        lines = []
        for entry in history[-10:]:
            role = entry.get("role", "user").capitalize()
            text = (entry.get("text") or "").strip()
            if text:
                lines.append(f"{role}: {text}")
        return "\n".join(lines)

    def list_supported_models(self) -> List[str]:
        """Try fetching locally installed models dynamically from Ollama runtime."""
        try:
            resp = requests.get(f"{self.api_base}/api/tags", timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("name", "").split(":")[0] for m in data.get("models", []) if m.get("name")]
                if models:
                    # Update local list while preserving common defaults
                    for m in models:
                        if m not in self.supported_models:
                            self.supported_models.append(m)
                    return list(self.supported_models)
        except Exception:
            pass
        return list(self.supported_models)

    def generate(self, prompt: str, meta: Optional[Dict[str, Any]] = None) -> str:
        meta = meta or {}
        language = meta.get("language", "en")
        mode = meta.get("mode", "neutral")
        history = meta.get("history", [])

        system_msg = build_radhe_system_prompt(language, mode, meta.get("memory_context"))
        history_str = self._format_history_for_prompt(history)

        full_prompt = system_msg + "\n\n"
        if history_str:
            full_prompt += f"Conversation context:\n{history_str}\n\n"
        full_prompt += f"User: {prompt}\nRadhe:"

        try:
            resp = requests.post(
                f"{self.api_base}/api/generate",
                json={
                    "model": self.selected_model,
                    "prompt": full_prompt,
                    "stream": False
                },
                timeout=60
            )
            resp.raise_for_status()
            return resp.json().get("response", "").strip()
        except requests.exceptions.ConnectionError:
            logger.warning("Ollama daemon is not running on %s", self.api_base)
            return ""
        except Exception as e:
            logger.error("Ollama generate error: %s", e)
            return ""

    def check_health(self) -> Dict[str, Any]:
        start = time.time()
        try:
            resp = requests.get(f"{self.api_base}/api/tags", timeout=4)
            latency = round((time.time() - start) * 1000, 1)
            if resp.status_code == 200:
                installed = [m.get("name") for m in resp.json().get("models", [])]
                return {
                    "status": "connected",
                    "message": f"Ollama active (Installed: {', '.join(installed[:3]) if installed else 'None'})",
                    "latency_ms": latency
                }
            return {"status": "error", "message": f"Ollama HTTP {resp.status_code}", "latency_ms": latency}
        except Exception as e:
            return {"status": "disconnected", "message": f"Ollama not running on {self.api_base}", "latency_ms": 0}
