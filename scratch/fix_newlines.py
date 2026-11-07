from pathlib import Path

sm = Path("src/social_media.py")
content = sm.read_text(encoding="utf-8")
content = content.replace('return "Upcoming scheduled WhatsApp messages:\n" + "\n".join(lines)', 'return "Upcoming scheduled WhatsApp messages:\\n" + "\\n".join(lines)')
content = content.replace('return "Upcoming scheduled WhatsApp messages:\r\n" + "\r\n".join(lines)', 'return "Upcoming scheduled WhatsApp messages:\\n" + "\\n".join(lines)')
sm.write_text(content, encoding="utf-8")
print("Fixed raw newlines in social_media.py")
