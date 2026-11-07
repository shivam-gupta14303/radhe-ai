# cost_tracker.py
"""
AI Usage & Cost Tracker for Radhe.

Tracks:
- Prompt and completion token counts per AI provider.
- Estimated expenditure in USD and INR.
- Daily, monthly, and lifetime consumption statistics.
- Storage in data/usage_stats.json.
"""

import os
import sys
import json
import logging
import threading
from pathlib import Path
from datetime import datetime, date
from typing import Optional, Dict, Any, List

from config import DATA_DIR

logger = logging.getLogger("Radhe_CostTracker")
logger.setLevel(logging.INFO)

USAGE_FILE = DATA_DIR / "usage_stats.json"
_usage_lock = threading.Lock()

USD_TO_INR_RATE = 85.0

# Pricing in USD per 1,000,000 tokens (Input / Output)
PROVIDER_RATES = {
    # OpenAI
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},

    # Claude
    "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
    "claude-3-5-haiku-20241022": {"input": 0.80, "output": 4.00},
    "claude-3-opus-20240229": {"input": 15.00, "output": 75.00},

    # Gemini
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
    "gemini-1.5-pro": {"input": 1.25, "output": 5.00},
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},

    # Groq (Hosted open models)
    "llama-3.3-70b-versatile": {"input": 0.59, "output": 0.79},
    "llama-3.1-8b-instant": {"input": 0.05, "output": 0.08},
    "mixtral-8x7b-32768": {"input": 0.24, "output": 0.24},

    # Ollama (Local machine)
    "llama3.1": {"input": 0.0, "output": 0.0},
    "mistral": {"input": 0.0, "output": 0.0},
    "phi3": {"input": 0.0, "output": 0.0},
    "qwen2.5": {"input": 0.0, "output": 0.0},
    "gemma2": {"input": 0.0, "output": 0.0},
}


class CostTracker:
    """Manages AI token usage monitoring and estimated cost accounting."""

    def __init__(self, stats_file: Path = USAGE_FILE):
        self.stats_file = Path(stats_file)
        self.stats_file.parent.mkdir(parents=True, exist_ok=True)
        self._data: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        with _usage_lock:
            if not self.stats_file.exists():
                return {
                    "total_tokens": 0,
                    "total_cost_usd": 0.0,
                    "total_cost_inr": 0.0,
                    "providers": {},
                    "daily": {}
                }
            try:
                with open(self.stats_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("Could not read usage_stats.json: %s", e)
                return {
                    "total_tokens": 0,
                    "total_cost_usd": 0.0,
                    "total_cost_inr": 0.0,
                    "providers": {},
                    "daily": {}
                }

    def _save(self) -> None:
        with _usage_lock:
            try:
                with open(self.stats_file, "w", encoding="utf-8") as f:
                    json.dump(self._data, f, indent=2)
            except Exception as e:
                logger.error("Failed to save usage_stats.json: %s", e)

    def record_usage(
        self,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int
    ) -> Dict[str, Any]:
        """Record a single interaction's token consumption and compute cost."""
        prov = provider.strip().lower()
        mod = model.strip().lower()

        # Rates per 1M tokens
        rates = PROVIDER_RATES.get(mod, {"input": 0.50, "output": 1.50})
        cost_usd = (prompt_tokens * rates["input"] / 1_000_000.0) + (completion_tokens * rates["output"] / 1_000_000.0)
        cost_inr = cost_usd * USD_TO_INR_RATE
        total_tokens = prompt_tokens + completion_tokens

        today_str = date.today().isoformat()

        with _usage_lock:
            self._data["total_tokens"] = self._data.get("total_tokens", 0) + total_tokens
            self._data["total_cost_usd"] = round(self._data.get("total_cost_usd", 0.0) + cost_usd, 6)
            self._data["total_cost_inr"] = round(self._data.get("total_cost_inr", 0.0) + cost_inr, 4)

            # Provider stats
            prov_map = self._data.setdefault("providers", {})
            prov_stat = prov_map.setdefault(prov, {
                "total_tokens": 0, "prompt_tokens": 0, "completion_tokens": 0,
                "cost_usd": 0.0, "cost_inr": 0.0, "models": {}
            })
            prov_stat["total_tokens"] += total_tokens
            prov_stat["prompt_tokens"] += prompt_tokens
            prov_stat["completion_tokens"] += completion_tokens
            prov_stat["cost_usd"] = round(prov_stat["cost_usd"] + cost_usd, 6)
            prov_stat["cost_inr"] = round(prov_stat["cost_inr"] + cost_inr, 4)

            # Model stats
            mod_stat = prov_stat["models"].setdefault(mod, {"tokens": 0, "cost_usd": 0.0})
            mod_stat["tokens"] += total_tokens
            mod_stat["cost_usd"] = round(mod_stat["cost_usd"] + cost_usd, 6)

            # Daily stats
            daily_map = self._data.setdefault("daily", {})
            d_stat = daily_map.setdefault(today_str, {"tokens": 0, "cost_usd": 0.0, "cost_inr": 0.0})
            d_stat["tokens"] += total_tokens
            d_stat["cost_usd"] = round(d_stat["cost_usd"] + cost_usd, 6)
            d_stat["cost_inr"] = round(d_stat["cost_inr"] + cost_inr, 4)

        self._save()
        return {
            "provider": prov,
            "model": mod,
            "tokens": total_tokens,
            "cost_usd": round(cost_usd, 6),
            "cost_inr": round(cost_inr, 4),
        }

    def estimate_tokens_from_text(self, text: str) -> int:
        """Rough estimation: ~4 characters per token for English/Hinglish text."""
        if not text:
            return 0
        return max(1, len(text) // 4)

    def get_summary(self) -> Dict[str, Any]:
        """Return high-level usage and cost breakdown."""
        with _usage_lock:
            today_str = date.today().isoformat()
            today_stat = self._data.get("daily", {}).get(today_str, {"tokens": 0, "cost_usd": 0.0, "cost_inr": 0.0})
            return {
                "lifetime_tokens": self._data.get("total_tokens", 0),
                "lifetime_cost_usd": self._data.get("total_cost_usd", 0.0),
                "lifetime_cost_inr": self._data.get("total_cost_inr", 0.0),
                "today": today_stat,
                "providers": self._data.get("providers", {})
            }


# Global cost tracker instance
cost_tracker = CostTracker()
