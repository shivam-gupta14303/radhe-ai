# src/ai_providers/gemini_provider.py
"""
Google (Gemini) provider adapter for Radhe.
Supports gemini-1.5-flash, gemini-1.5-pro, gemini-2.0-flash via official Google Generative Language REST API.
"""

import os
import time
import logging
from typing import Dict, Any, List, Optional
import requests

from .base_provider import BaseAIProvider, build_radhe_system_prompt

logger = logging.getLogger("Radhe_Gemini")

GEMINI_MODELS = [
    "gemini-1.5-flash",
    "gemini-1.5-pro",
    "gemini-2.0-flash",
]


class GeminiProvider(BaseAIProvider):

    def __init__(self, api_key: Optional[str] = None):
        super().__init__(
            name="gemini",
            default_model="gemini-1.5-flash",
            supported_models=GEMINI_MODELS
        )
        self._api_key = api_key or os.getenv("GEMINI_API_KEY", "").strip() or os.getenv("GOOGLE_API_KEY", "").strip() or None

    def get_api_key(self) -> Optional[str]:
        if not self._api_key:
            self._api_key = os.getenv("GEMINI_API_KEY", "").strip() or os.getenv("GOOGLE_API_KEY", "").strip() or None
        return self._api_key

    def _get_endpoint(self) -> str:
        key = self.get_api_key() or ""
        return f"https://generativelanguage.googleapis.com/v1beta/models/{self.selected_model}:generateContent?key={key}"

    def generate(self, prompt: str, meta: Optional[Dict[str, Any]] = None) -> str:
        key = self.get_api_key()
        if not key:
            logger.warning("Gemini API key not configured.")
            return ""

        meta = meta or {}
        language = meta.get("language", "en")
        mode = meta.get("mode", "neutral")
        history = meta.get("history", [])

        system_msg = build_radhe_system_prompt(language, mode, meta.get("memory_context"))

        # Convert history to Gemini contents format
        contents = []
        for entry in history[-10:]:
            role = entry.get("role", "user")
            gemini_role = "user" if role == "user" else "model"
            text = (entry.get("text") or "").strip()
            if text:
                contents.append({"role": gemini_role, "parts": [{"text": text}]})

        contents.append({"role": "user", "parts": [{"text": prompt}]})

        payload = {
            "system_instruction": {
                "parts": [{"text": system_msg}]
            },
            "contents": contents,
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 1024
            }
        }

        try:
            resp = requests.post(
                self._get_endpoint(),
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=25
            )
            resp.raise_for_status()
            data = resp.json()
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "").strip()
            return ""
        except requests.exceptions.HTTPError as e:
            logger.error("Gemini HTTP error: %s - %s", e.response.status_code, e.response.text[:200])
            return ""
        except Exception as e:
            logger.error("Gemini request error: %s", e)
            return ""

    def check_health(self) -> Dict[str, Any]:
        key = self.get_api_key()
        if not key:
            return {"status": "disconnected", "message": "API key missing. Enter key in AI Settings.", "latency_ms": 0}

        start = time.time()
        payload = {
            "contents": [{"role": "user", "parts": [{"text": "ping"}]}],
            "generationConfig": {"maxOutputTokens": 2}
        }
        try:
            resp = requests.post(
                self._get_endpoint(),
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=8
            )
            latency = round((time.time() - start) * 1000, 1)
            if resp.status_code == 200:
                return {"status": "connected", "message": f"Connected to Google Gemini ({self.selected_model})", "latency_ms": latency}
            elif resp.status_code in (400, 403):
                return {"status": "error", "message": "Invalid Google Gemini API key or quota exceeded.", "latency_ms": latency}
            return {"status": "error", "message": f"HTTP {resp.status_code}: {resp.text[:100]}", "latency_ms": latency}
        except Exception as e:
            return {"status": "error", "message": f"Connection failed: {e}", "latency_ms": 0}
