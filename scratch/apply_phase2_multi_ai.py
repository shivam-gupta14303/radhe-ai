# scratch/apply_phase2_multi_ai.py

with open("src/command_parser.py", "r", encoding="utf-8") as f:
    cp_text = f.read().replace("\r\n", "\n")

# 1. Clean duplicated rules in command_parser.py and add AI Provider rules
dup_marker_start = '_rules("set_whatsapp_mode", 0.96,'
media_marker = '# Media\n_rules("youtube_search"'

start_idx = cp_text.find(dup_marker_start)
end_idx = cp_text.find(media_marker)

if start_idx != -1 and end_idx != -1:
    clean_replacement = '''_rules("set_whatsapp_mode", 0.96,
    r"\\b(?:set|change|switch)\\s+(?:whatsapp\\s+)?mode\\s+(?:to\\s+)?(?P<mode>monitor|approval|auto[\\s\\-_]?reply)\\b",
    r"\\b(?:turn\\s+on|enable|activate)\\s+(?:whatsapp\\s+)?(?P<mode>auto[\\s\\-_]?reply|approval|monitor)(?:\\s+mode)?\\b",
    r"\\b(?:turn\\s+off|disable|deactivate)\\s+(?:whatsapp\\s+)?auto[\\s\\-_]?reply(?:\\s+mode)?\\b",
    r"\\bwhatsapp\\s+mode\\s+(?:to\\s+)?(?P<mode>monitor|approval|auto[\\s\\-_]?reply)\\b",
    r"\\bwhatsapp\\s+(?:pe\\s+)?(?P<mode>monitor|approval|auto[\\s\\-_]?reply)\\s+mode(?:\\s+(?:karo|on\\s+karo|lagao))?\\b",
    r"\\bwhatsapp\\s+(?:auto[\\s\\-_]?reply|monitor|approval)\\s+(?:on|karo|lagao)\\b")

_rules("get_whatsapp_mode", 0.96,
    r"\\b(?:what\\s+is|check|show|get)\\s+(?:the\\s+)?whatsapp\\s+mode\\b",
    r"\\bwhatsapp\\s+mode\\s+(?:kya\\s+hai|check\\s+karo|status)\\b")

# AI Provider Selection & Management
_rules("set_ai_provider", 0.98,
    r"\\b(?:switch|set|change|use)\\s+(?:ai\\s+)?(?:provider|model)?\\s*(?:to\\s+)?(?P<provider>openai|chatgpt|gpt|anthropic|claude|gemini|google|groq|ollama)\\b",
    r"\\b(?:use|switch to|set to)\\s+(?P<provider>openai|chatgpt|claude|gemini|groq|ollama)\\b",
    r"\\b(?P<provider>openai|chatgpt|claude|gemini|groq|ollama)\\s+(?:use karo|chalao|lagao)\\b",
    r"\\b(?:switch to|use)\\s+local\\s+(?:ai|models?|ollama)\\b")

_rules("get_ai_provider", 0.98,
    r"\\b(?:what|which)\\s+(?:ai\\s+)?(?:provider|model)\\s+(?:are you using|is active)\\b",
    r"\\b(?:check|show|get)\\s+(?:active\\s+)?(?:ai\\s+)?(?:provider|model|status)\\b",
    r"\\bai\\s+(?:provider|model)\\s+(?:status|check|kya hai)\\b")

_rules("test_ai_connection", 0.98,
    r"\\b(?:test|check)\\s+(?:ai\\s+)?(?:connection|health|api)\\b",
    r"\\bai\\s+(?:connection|api)\\s+test\\s*(?:karo)?\\b")

'''
    cp_text = cp_text[:start_idx] + clean_replacement + cp_text[end_idx:]
    print("[OK] Deduplicated whatsapp rules and added AI Provider rules in command_parser.py")

# Add normalization for set_ai_provider
norm_anchor = 'if best_intent == "set_whatsapp_mode":'
norm_idx = cp_text.find(norm_anchor)
if norm_idx != -1 and 'if best_intent == "set_ai_provider":' not in cp_text:
    ai_norm = '''    if best_intent == "set_ai_provider":
        p_val = best_entities.get("provider", "").lower()
        if "chatgpt" in text.lower() or "gpt" in text.lower() or "openai" in text.lower():
            p_val = "openai"
        elif "claude" in text.lower() or "anthropic" in text.lower():
            p_val = "anthropic"
        elif "gemini" in text.lower() or "google" in text.lower():
            p_val = "gemini"
        elif "groq" in text.lower():
            p_val = "groq"
        elif "ollama" in text.lower() or "local" in text.lower():
            p_val = "ollama"
        best_entities["provider"] = p_val
    '''
    cp_text = cp_text[:norm_idx] + ai_norm + cp_text[norm_idx:]
    print("[OK] Added set_ai_provider normalization in command_parser.py")

with open("src/command_parser.py", "w", encoding="utf-8") as f:
    f.write(cp_text)


# ======================================================================
# 2. UPDATE COMMAND_EXECUTOR.PY
# ======================================================================
with open("src/command_executor.py", "r", encoding="utf-8") as f:
    ce_text = f.read().replace("\r\n", "\n")

ce_anchor = 'if intent in ("get_whatsapp_mode", "check_whatsapp_mode"):'
ce_idx = ce_text.find(ce_anchor)

if ce_idx != -1 and 'if intent == "set_ai_provider":' not in ce_text:
    # Find end of this if block
    end_of_block = ce_text.find("\n\n", ce_idx)
    ai_handlers = '''

        if intent == "set_ai_provider":
            provider = entities.get("provider", "groq")
            model = entities.get("model")
            from ai_providers import ai_provider_manager
            ok, msg = ai_provider_manager.set_active_provider(provider, model)
            return self._resp(msg)

        if intent == "get_ai_provider":
            from ai_providers import ai_provider_manager
            active_p = ai_provider_manager.get_active_provider_name().capitalize()
            active_m = ai_provider_manager.get_active_model()
            return self._resp(f"Radhe is currently powered by {active_p} (Model: {active_m}).")

        if intent == "test_ai_connection":
            from ai_providers import ai_provider_manager
            active_p = ai_provider_manager.get_active_provider_name()
            health = ai_provider_manager.test_provider(active_p)
            status = health.get("status", "unknown")
            msg = health.get("message", "")
            lat = health.get("latency_ms", 0)
            return self._resp(f"AI Provider Test ({active_p.capitalize()}): {status.upper()} - {msg} ({lat}ms).")'''

    ce_text = ce_text[:end_of_block] + ai_handlers + ce_text[end_of_block:]
    with open("src/command_executor.py", "w", encoding="utf-8") as f:
        f.write(ce_text)
    print("[OK] Added AI provider intent execution in command_executor.py")


# ======================================================================
# 3. UPDATE LLM_SETUP.PY
# ======================================================================
with open("src/llm_setup.py", "r", encoding="utf-8") as f:
    llm_text = f.read().replace("\r\n", "\n")

llm_gen_anchor = '    def generate(self, prompt: str, meta: dict) -> str:'
llm_gen_idx = llm_text.find(llm_gen_anchor)

if llm_gen_idx != -1 and 'ai_provider_manager' not in llm_text:
    new_generate = '''    def generate(self, prompt: str, meta: dict) -> str:
        """
        Main entry point for Radhe intelligence.
        Delegates to AIProviderManager across OpenAI, Claude, Gemini, Groq, and Ollama.
        """
        if not isinstance(meta, dict):
            meta = {}

        try:
            from ai_providers import ai_provider_manager
            response = ai_provider_manager.generate(prompt, meta)
            if response:
                return response
        except Exception as e:
            logger.error("AIProviderManager generation error: %s", e)

        # Legacy fallback
        response = self.cloud_llm(prompt, meta)
        if response:
            return response

        logger.info("Cloud LLM unavailable - falling back to local Ollama.")
        return self.local_llm(prompt, meta)'''

    # Find the end of generate function before llm_engine = LLMEngine()
    end_gen_idx = llm_text.find("\n\n# ── Single global instance", llm_gen_idx)
    llm_text = llm_text[:llm_gen_idx] + new_generate + llm_text[end_gen_idx:]
    with open("src/llm_setup.py", "w", encoding="utf-8") as f:
        f.write(llm_text)
    print("[OK] Updated llm_setup.py to delegate to AIProviderManager")

print("Phase 2 core wiring complete.")
