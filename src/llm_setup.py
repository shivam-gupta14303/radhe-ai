# llm_setup.py
"""
LLM Engine for Radhe.

Fixes applied:
- meta dict is now USED: passes conversation history, language, mode to the LLM
- System prompt added so Radhe has a consistent personality and identity
- Groq API error handling fixed — no more KeyError crashes on API errors
- Conversation history is now sent to Groq as a proper multi-turn messages array
- Local Ollama also receives history formatted into the prompt string

Import once at startup (side effect: attaches brain.llm_client):
    import brain.llm_setup
"""

import os
import logging
import requests
from typing import List, Dict, Any

from dotenv import load_dotenv
from ai_knowledge import brain

load_dotenv()

logger        = logging.getLogger("Radhe_LLM")
GROQ_API_KEY  = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL    = "llama-3.1-70b-versatile"
OLLAMA_MODEL  = "llama3.1"
OLLAMA_URL    = "http://localhost:11434/api/generate"
GROQ_URL      = "https://api.groq.com/openai/v1/chat/completions"

# Max history turns sent to LLM (keeps prompt size reasonable)
MAX_HISTORY_TURNS = 10


# ==================================================================
# SYSTEM PROMPT  (Radhe's personality and identity)
# ==================================================================

def _build_system_prompt(language: str = "en", mode: str = "neutral") -> str:
    """
    Build Radhe's system prompt based on language and mode.
    This gives Radhe a consistent personality across every conversation.
    """
    base = (
        "You are Radhe, a personal AI companion and assistant. "
        "You are warm, helpful, intelligent, and speak naturally like a close friend — "
        "not a formal assistant or a robot. "
        "You run locally on the user's own system. "
        "You can open apps, search the web, set reminders, send WhatsApp messages, "
        "answer questions, and have genuine conversations. "
        "Keep responses concise and conversational unless the user needs detail. "
        "Never say you are an AI language model or mention GPT, OpenAI, or Anthropic. "
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
            "the way young Indians actually speak."
        )
    else:
        base += " Respond in clear, natural English."

    if mode == "casual":
        base += " Keep the tone casual, friendly, and relaxed."
    elif mode == "formal":
        base += " Keep the tone polite and professional."

    return base


# ==================================================================
# HISTORY FORMATTERS
# ==================================================================

def _format_history_for_groq(history: List[Dict]) -> List[Dict[str, str]]:
    """
    Convert Radhe's internal history to Groq's messages array format.
    Groq expects: [{"role": "user"|"assistant", "content": "..."}]
    """
    messages = []
    for entry in history[-MAX_HISTORY_TURNS:]:
        role = entry.get("role", "user")
        text = (entry.get("text") or "").strip()
        if role in ("user", "assistant") and text:
            messages.append({"role": role, "content": text})
    return messages


def _format_history_for_ollama(history: List[Dict]) -> str:
    """
    Flatten conversation history into a readable string for Ollama.
    """
    lines = []
    for entry in history[-MAX_HISTORY_TURNS:]:
        role = entry.get("role", "user").capitalize()
        text = (entry.get("text") or "").strip()
        if text:
            lines.append(f"{role}: {text}")
    return "\n".join(lines)


# ==================================================================
# LLM ENGINE
# ==================================================================

class LLMEngine:

    def __init__(self):
        if GROQ_API_KEY:
            logger.warning("Groq API key loaded — cloud LLM enabled.")
        else:
            logger.warning(
                "GROQ_API_KEY not set — cloud LLM disabled. "
                "Using local Ollama only."
            )

    # ------------------------------------------------------------------
    # CLOUD  (Groq)
    # ------------------------------------------------------------------

    def cloud_llm(self, prompt: str, meta: dict) -> str:
        if not GROQ_API_KEY:
            return ""

        language = meta.get("language", "en")
        mode     = meta.get("mode",     "neutral")
        history  = meta.get("history",  [])

        # Build messages: system prompt + history + current user message
        messages  = [{"role": "system", "content": _build_system_prompt(language, mode)}]
        messages += _format_history_for_groq(history)
        messages.append({"role": "user", "content": prompt})

        try:
            resp = requests.post(
                GROQ_URL,
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type":  "application/json"
                },
                json={
                    "model":       GROQ_MODEL,
                    "messages":    messages,
                    "max_tokens":  1024,
                    "temperature": 0.7,
                },
                timeout=20
            )
            resp.raise_for_status()

            data    = resp.json()
            choices = data.get("choices")

            # Safe extraction — never crash on unexpected API response shape
            if not choices:
                logger.error(
                    "Groq returned no choices. Full response: %s",
                    str(data)[:300]
                )
                return ""

            content = choices[0].get("message", {}).get("content", "").strip()
            return content

        except requests.exceptions.Timeout:
            logger.warning("Groq request timed out.")
            return ""
        except requests.exceptions.HTTPError as e:
            logger.error(
                "Groq HTTP %s: %s",
                e.response.status_code,
                e.response.text[:200]
            )
            return ""
        except Exception as e:
            logger.error("cloud_llm error: %s", e)
            return ""

    # ------------------------------------------------------------------
    # LOCAL  (Ollama)
    # ------------------------------------------------------------------

    def local_llm(self, prompt: str, meta: dict) -> str:
        language    = meta.get("language", "en")
        mode        = meta.get("mode",     "neutral")
        history     = meta.get("history",  [])

        system      = _build_system_prompt(language, mode)
        history_str = _format_history_for_ollama(history)

        # Inject system prompt + history into a single prompt string
        full_prompt = system + "\n\n"
        if history_str:
            full_prompt += f"Conversation so far:\n{history_str}\n\n"
        full_prompt += f"User: {prompt}\nRadhe:"

        try:
            resp = requests.post(
                OLLAMA_URL,
                json={
                    "model":  OLLAMA_MODEL,
                    "prompt": full_prompt,
                    "stream": False
                },
                timeout=60
            )
            resp.raise_for_status()
            return resp.json().get("response", "").strip()

        except requests.exceptions.ConnectionError:
            logger.warning("Ollama not running on localhost:11434.")
            return ""
        except requests.exceptions.Timeout:
            logger.warning("Ollama request timed out.")
            return ""
        except Exception as e:
            logger.error("local_llm error: %s", e)
            return ""

    # ------------------------------------------------------------------
    # SMART  (cloud → local fallback)
    # ------------------------------------------------------------------

    def generate(self, prompt: str, meta: dict) -> str:
        """
        Main entry point.  Try Groq first, fall back to local Ollama.

        `meta` should contain:
            language  : "en" | "hi" | "mixed"
            mode      : "neutral" | "casual" | "formal"
            history   : list of {"role": str, "text": str} dicts
        """
        if not isinstance(meta, dict):
            meta = {}

        response = self.cloud_llm(prompt, meta)
        if response:
            return response

        logger.info("Cloud LLM unavailable — falling back to local Ollama.")
        return self.local_llm(prompt, meta)


# ── Single global instance ────────────────────────────────────────────
llm_engine = LLMEngine()

# ── Attach to brain so ai_knowledge.answer_question() uses it ─────────
brain.llm_client = llm_engine.generate
logger.warning("LLM engine attached to brain.llm_client.")