from pathlib import Path

p = Path("src/ai_providers/manager.py")
t = p.read_text(encoding="utf-8")

old_load = """                    key = p_info.get("api_key")
                    if key:
                        p_inst.set_api_key(key)"""

new_load = """                    key = p_info.get("api_key")
                    if not key:
                        try:
                            from security import vault
                            key = vault.get_secret(f"{name}_api_key")
                        except Exception:
                            key = None
                    if key:
                        p_inst.set_api_key(key)"""

old_set = """        self.providers[p_name].set_api_key(api_key)
        self._save_settings()
        return True, f"API key for {p_name.capitalize()} updated securely.\""""

new_set = """        self.providers[p_name].set_api_key(api_key)
        try:
            from security import vault
            vault.set_secret(f"{p_name}_api_key", api_key)
        except Exception:
            pass
        self._save_settings()
        return True, f"API key for {p_name.capitalize()} updated securely.\""""

old_rem = """        self.providers[p_name].set_api_key("")
        self._save_settings()
        return True, f"API key for {p_name.capitalize()} removed.\""""

new_rem = """        self.providers[p_name].set_api_key("")
        try:
            from security import vault
            vault.delete_secret(f"{p_name}_api_key")
        except Exception:
            pass
        self._save_settings()
        return True, f"API key for {p_name.capitalize()} removed.\""""

if old_load in t and old_set in t and old_rem in t:
    t = t.replace(old_load, new_load, 1)
    t = t.replace(old_set, new_set, 1)
    t = t.replace(old_rem, new_rem, 1)
    p.write_text(t, encoding="utf-8")
    print("SUCCESS: AIProviderManager connected to SecretVault")
else:
    print("ERROR: Patterns not found in manager.py")
