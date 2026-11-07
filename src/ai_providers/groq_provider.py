# src/ai_providers/groq_provider.py
"""
Groq provider adapter for Radhe.
Supports llama-3.3-70b-versatile, llama-3.1-8b-instant, mixtral-8x7b-32768.
"""

import os
import time
import logging
from typing import Dict, Any, List, Optional
import requests

from .base_provider import BaseAIProvider, build_radhe_system_prompt

logger = logging.getLogger("Radhe_Groq")

GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "mixtral-8x7b-32768",
]


class GroqProvider(BaseAIProvider):

    def __init__(self, api_key: Optional[str] = None):
        super().__init__(
            name="groq",
            default_model="llama-3.3-70b-versatile",
            supported_models=GROQ_MODELS
        )
        self._api_key = api_key or os.getenv("GROQ_API_KEY", "").strip() or None
        self.endpoint = "https://api.groq.com/openai/v1/chat/completions"

    def get_api_key(self) -> Optional[str]:
        if not self._api_key:
            self._api_key = os.getenv("GROQ_API_KEY", "").strip() or None
        return self._api_key

    def generate(self, prompt: str, meta: Optional[Dict[str, Any]] = None) -> str:
        key = self.get_api_key()
        if not key:
            logger.warning("Groq API key not configured.")
            return ""

        meta = meta or {}
        language = meta.get("language", "en")
        mode = meta.get("mode", "neutral")
        history = meta.get("history", [])

        system_msg = build_radhe_system_prompt(language, mode, meta.get("memory_context"))
        messages = [{"role": "system", "content": system_msg}]
        messages.extend(self.format_history_as_messages(history))
        messages.append({"role": "user", "content": prompt})

        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.selected_model,
            "messages": messages,
            "max_tokens": 1024,
            "temperature": 0.7
        }

        try:
            resp = requests.post(self.endpoint, headers=headers, json=payload, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            choices = data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "").strip()
            return ""
        except requests.exceptions.HTTPError as e:
            logger.error("Groq HTTP error: %s - %s", e.response.status_code, e.response.text[:200])
            return ""
        except Exception as e:
            logger.error("Groq request error: %s", e)
            return ""

    def check_health(self) -> Dict[str, Any]:
        key = self.get_api_key()
        if not key:
            return {"status": "disconnected", "message": "API key missing. Enter key in AI Settings.", "latency_ms": 0}

        start = time.time()
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.selected_model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 2
        }
        try:
            resp = requests.post(self.endpoint, headers=headers, json=payload, timeout=8)
            latency = round((time.time() - start) * 1000, 1)
            if resp.status_code == 200:
                return {"status": "connected", "message": f"Connected to Groq ({self.selected_model})", "latency_ms": latency}
            elif resp.status_code == 401:
                return {"status": "error", "message": "Invalid Groq API key.", "latency_ms": latency}
            return {"status": "error", "message": f"HTTP {resp.status_code}: {resp.text[:100]}", "latency_ms": latency}
        except Exception as e:
            return {"status": "error", "message": f"Connection failed: {e}", "latency_ms": 0}
