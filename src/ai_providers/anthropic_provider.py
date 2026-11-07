# src/ai_providers/anthropic_provider.py
"""
Anthropic (Claude) provider adapter for Radhe.
Supports claude-3-5-sonnet-20241022, claude-3-5-haiku-20241022, claude-3-opus-20240229.
"""

import os
import time
import logging
from typing import Dict, Any, List, Optional
import requests

from .base_provider import BaseAIProvider, build_radhe_system_prompt

logger = logging.getLogger("Radhe_Anthropic")

ANTHROPIC_MODELS = [
    "claude-3-5-sonnet-20241022",
    "claude-3-5-haiku-20241022",
    "claude-3-opus-20240229",
]


class ClaudeProvider(BaseAIProvider):

    def __init__(self, api_key: Optional[str] = None):
        super().__init__(
            name="anthropic",
            default_model="claude-3-5-sonnet-20241022",
            supported_models=ANTHROPIC_MODELS
        )
        self._api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "").strip() or None
        self.endpoint = "https://api.anthropic.com/v1/messages"

    def get_api_key(self) -> Optional[str]:
        if not self._api_key:
            self._api_key = os.getenv("ANTHROPIC_API_KEY", "").strip() or None
        return self._api_key

    def generate(self, prompt: str, meta: Optional[Dict[str, Any]] = None) -> str:
        key = self.get_api_key()
        if not key:
            logger.warning("Anthropic API key not configured.")
            return ""

        meta = meta or {}
        language = meta.get("language", "en")
        mode = meta.get("mode", "neutral")
        history = meta.get("history", [])

        system_msg = build_radhe_system_prompt(language, mode, meta.get("memory_context"))
        messages = self.format_history_as_messages(history)
        messages.append({"role": "user", "content": prompt})

        headers = {
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        payload = {
            "model": self.selected_model,
            "system": system_msg,
            "messages": messages,
            "max_tokens": 1024,
            "temperature": 0.7
        }

        try:
            resp = requests.post(self.endpoint, headers=headers, json=payload, timeout=25)
            resp.raise_for_status()
            data = resp.json()
            content_blocks = data.get("content", [])
            for block in content_blocks:
                if block.get("type") == "text":
                    return block.get("text", "").strip()
            return ""
        except requests.exceptions.HTTPError as e:
            logger.error("Anthropic HTTP error: %s - %s", e.response.status_code, e.response.text[:200])
            return ""
        except Exception as e:
            logger.error("Anthropic request error: %s", e)
            return ""

    def check_health(self) -> Dict[str, Any]:
        key = self.get_api_key()
        if not key:
            return {"status": "disconnected", "message": "API key missing. Enter key in AI Settings.", "latency_ms": 0}

        start = time.time()
        headers = {
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        payload = {
            "model": self.selected_model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 5
        }
        try:
            resp = requests.post(self.endpoint, headers=headers, json=payload, timeout=8)
            latency = round((time.time() - start) * 1000, 1)
            if resp.status_code == 200:
                return {"status": "connected", "message": f"Connected to Anthropic ({self.selected_model})", "latency_ms": latency}
            elif resp.status_code == 401:
                return {"status": "error", "message": "Invalid Anthropic API key.", "latency_ms": latency}
            return {"status": "error", "message": f"HTTP {resp.status_code}: {resp.text[:100]}", "latency_ms": latency}
        except Exception as e:
            return {"status": "error", "message": f"Connection failed: {e}", "latency_ms": 0}
