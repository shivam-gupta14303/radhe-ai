from pathlib import Path

# 1. base_provider.py
base_p = Path("src/ai_providers/base_provider.py")
content = base_p.read_text(encoding="utf-8")
old_def = 'def build_radhe_system_prompt(language: str = "en", mode: str = "neutral") -> str:'
new_def = 'def build_radhe_system_prompt(language: str = "en", mode: str = "neutral", memory_context: Optional[str] = None) -> str:'

if old_def in content:
    content = content.replace(old_def, new_def)
    # append memory injection before return base
    ret_target = "    return base"
    mem_block = """    if memory_context:
        base += f"\\n\\n[RELEVANT USER MEMORY & PROFILE]\\n{memory_context}\\nUse this context naturally without explicitly stating 'According to my memory'."

    return base"""
    content = content.replace(ret_target, mem_block, 1)
    base_p.write_text(content, encoding="utf-8")
    print("Updated base_provider.py")
else:
    print("base_provider.py already updated or not found")

# 2. Update each provider to pass memory_context
for fname in ["openai_provider.py", "anthropic_provider.py", "gemini_provider.py", "groq_provider.py", "ollama_provider.py"]:
    p = Path(f"src/ai_providers/{fname}")
    c = p.read_text(encoding="utf-8")
    old_call = "system_msg = build_radhe_system_prompt(language, mode)"
    new_call = 'system_msg = build_radhe_system_prompt(language, mode, meta.get("memory_context"))'
    if old_call in c:
        c = c.replace(old_call, new_call)
        p.write_text(c, encoding="utf-8")
        print(f"Updated {fname}")
    else:
        print(f"{fname}: target not found")

# 3. manager.py - auto fetch memory context
mgr_p = Path("src/ai_providers/manager.py")
mc = mgr_p.read_text(encoding="utf-8")
target_gen = "        meta = meta or {}"
gen_block = """        meta = meta or {}
        if "memory_context" not in meta:
            try:
                from memory import memory_manager
                u_id = meta.get("user_id", "default")
                mem_ctx = memory_manager.get_relevant_context(prompt, user_id=u_id)
                if mem_ctx:
                    meta["memory_context"] = mem_ctx
            except Exception as me:
                logger.debug("Memory context fetch skipped: %s", me)"""

if target_gen in mc and 'from memory import memory_manager' not in mc:
    mc = mc.replace(target_gen, gen_block, 1)
    mgr_p.write_text(mc, encoding="utf-8")
    print("Updated manager.py")
else:
    print("manager.py already updated or target not found")
