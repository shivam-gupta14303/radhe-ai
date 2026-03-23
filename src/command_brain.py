import re

class CommandBrain:

    def __init__(self):
        pass

    def process(self, text: str):
        text = text.lower().strip()

        # ---------- WHATSAPP ----------
        if "whatsapp" in text:
            return {
                "intent": "open_whatsapp",
                "entities": {
                    "platform": "web" if "chrome" in text or "browser" in text else "app"
                }
            }

        # ---------- OPEN APP ----------
        if text.startswith("open "):
            app_name = text.replace("open ", "").strip()
            return {
                "intent": "open_app",
                "entities": {
                    "app_name": app_name
                }
            }

        # ---------- OPEN FOLDER ----------
        if "folder" in text:
            match = re.search(r"open (.+?) folder", text)
            if match:
                return {
                    "intent": "open_folder",
                    "entities": {
                        "folder_name": match.group(1)
                    }
                }

        # ---------- DEFAULT ----------
        return {
            "intent": "unknown",
            "entities": {
                "text": text
            }
        }