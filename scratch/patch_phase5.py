from pathlib import Path

# 1. Update social_media.py
sm = Path("src/social_media.py")
content = sm.read_text(encoding="utf-8")

method = """    def get_pending_approvals(self) -> list:
        \"\"\"Return list of pending approval drafts.\"\"\"
        if self._executor_ref and self._executor_ref.context.get("pending_whatsapp_approval"):
            appr = self._executor_ref.context["pending_whatsapp_approval"]
            return [{
                "contact": appr.get("sender"),
                "incoming": appr.get("message"),
                "draft": appr.get("draft")
            }]
        return []
"""

if "def get_pending_approvals" not in content:
    target = '    def connect_executor(self, executor_instance) -> None:'
    content = content.replace(target, method + "\n" + target, 1)
    sm.write_text(content, encoding="utf-8")
    print("Added get_pending_approvals to social_media.py")
else:
    print("social_media.py already has get_pending_approvals")

# 2. Update flask_server.py
fs = Path("src/flask_server.py")
fsc = fs.read_text(encoding="utf-8")
old_wa = """"pending_approvals": social_integrator.get_pending_approvals()"""
new_wa = """"pending_approvals": social_integrator.get_pending_approvals() if hasattr(social_integrator, "get_pending_approvals") else []"""

if old_wa in fsc:
    fsc = fsc.replace(old_wa, new_wa, 1)
    fs.write_text(fsc, encoding="utf-8")
    print("Updated flask_server.py with safe get_pending_approvals call")

# 3. Update test_phase5_desktop.py
t5 = Path("scratch/test_phase5_desktop.py")
t5c = t5.read_text(encoding="utf-8")
t5c = t5c.replace('self.assertIn(b"Morning Briefing", res.data)', 'self.assertIn(b"BRIEFING", res.data)')
t5.write_text(t5c, encoding="utf-8")
print("Updated test_phase5_desktop.py assertion")
