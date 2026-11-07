# scratch/fix_indent.py

with open("src/command_parser.py", "r", encoding="utf-8") as f:
    text = f.read().replace("\r\n", "\n")

old_block = '''    if best_intent == "change_mode":
        casual = {"normal", "casual", "informal", "normally", "casually"}
        best_entities["target_mode"] = "casual" if any(w in text for w in casual) else "formal"
        if best_intent == "set_ai_provider":
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
        best_entities["provider"] = p_val'''

new_block = '''    if best_intent == "change_mode":
        casual = {"normal", "casual", "informal", "normally", "casually"}
        best_entities["target_mode"] = "casual" if any(w in text for w in casual) else "formal"

    if best_intent == "set_ai_provider":
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
        best_entities["provider"] = p_val'''

assert old_block in text, "old_block not found in command_parser.py"
text = text.replace(old_block, new_block, 1)

with open("src/command_parser.py", "w", encoding="utf-8") as f:
    f.write(text)
print("[OK] command_parser.py indentation fixed.")
