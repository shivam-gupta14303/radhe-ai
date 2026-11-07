# src/ai_providers/openai_provider.py
"""
OpenAI (ChatGPT) provider adapter for Radhe.
Supports gpt-4o, gpt-4o-mini, gpt-4-turbo, gpt-3.5-turbo.
"""

import os
import time
import logging
from typing import Dict, Any, List, Optional, Generator
import requests

from .base_provider import BaseAIProvider, build_radhe_system_prompt

logger = logging.getLogger("Radhe_OpenAI")

OPENAI_MODELS = [
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4-turbo",
    "gpt-3.5-turbo",
]


class OpenAIProvider(BaseAIProvider):

    def __init__(self, api_key: Optional[str] = None):
        super().__init__(
            name="openai",
            default_model="gpt-4o-mini",
            supported_models=OPENAI_MODELS
        )
        self._api_key = api_key or os.getenv("OPENAI_API_KEY", "").strip() or None
        self.endpoint = "https://api.openai.com/v1/chat/completions"

    def get_api_key(self) -> Optional[str]:
        if not self._api_key:
            self._api_key = os.getenv("OPENAI_API_KEY", "").strip() or None
        return self._api_key

    def generate(self, prompt: str, meta: Optional[Dict[str, Any]] = None) -> str:
        key = self.get_api_key()
        if not key:
            logger.warning("OpenAI API key not configured.")
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
            "temperature": 0.7,
            "max_tokens": 1024
        }

        try:
            resp = requests.post(self.endpoint, headers=headers, json=payload, timeout=25)
            resp.raise_for_status()
            data = resp.json()
            choices = data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "").strip()
            return ""
        except requests.exceptions.HTTPError as e:
            logger.error("OpenAI HTTP error: %s - %s", e.response.status_code, e.response.text[:200])
            return ""
        except Exception as e:
            logger.error("OpenAI request error: %s", e)
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
        # Lightweight test request
        payload = {
            "model": self.selected_model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 2
        }
        try:
            resp = requests.post(self.endpoint, headers=headers, json=payload, timeout=8)
            latency = round((time.time() - start) * 1000, 1)
            if resp.status_code == 200:
                return {"status": "connected", "message": f"Connected to OpenAI ({self.selected_model})", "latency_ms": latency}
            elif resp.status_code == 401:
                return {"status": "error", "message": "Invalid OpenAI API key.", "latency_ms": latency}
            return {"status": "error", "message": f"HTTP {resp.status_code}: {resp.text[:100]}", "latency_ms": latency}
        except Exception as e:
            return {"status": "error", "message": f"Connection failed: {e}", "latency_ms": 0}
