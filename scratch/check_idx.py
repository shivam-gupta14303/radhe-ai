from pathlib import Path
c = Path("src/command_executor.py").read_text(encoding="utf-8")
idx = c.find('if intent == "set_reminder":')
end_idx = c.find('if intent == "get_time":')
print(repr(c[idx:end_idx]))
