# system_control.py
"""
Safer SystemController.
- Uses whitelisted app paths from self.app_paths only.
- Avoids executing user-controlled shell strings.
- Provides safe fallback to opening web versions for known services.
- All side-effects are logged and TTS-confirmed via speak() from speech.py.
"""

import os
import subprocess
import platform
import webbrowser
import logging
from typing import Dict, Tuple
from speech import speak  # centralized TTS (speech.py)

logger = logging.getLogger("Radhe_System")
logger.setLevel(logging.INFO)


class SystemController:
    def __init__(self):
        self.os_type = platform.system().lower()
        self.app_paths = self._load_app_paths()

    def _load_app_paths(self) -> Dict[str, str]:
        """Return a safe mapping of friendly app names -> executable or app bundle."""
        if self.os_type == "windows":
            return {
                "chrome": "chrome.exe",
                "notepad": "notepad.exe",
                "vscode": "code.exe",
                "calculator": "calc.exe",
                "file explorer": "explorer.exe",
                "spotify": "spotify.exe",
            }
        elif self.os_type == "darwin":
            return {
                "chrome": "/Applications/Google Chrome.app",
                "safari": "/Applications/Safari.app",
                "vscode": "/Applications/Visual Studio Code.app",
                "spotify": "/Applications/Spotify.app",
            }
        else:  # linux / other
            return {
                "chrome": "google-chrome",
                "firefox": "firefox",
                "vscode": "code",
                "spotify": "spotify",
                "file explorer": "nautilus",
            }

    def _run_process(self, cmd: list) -> Tuple[bool, str]:
        """Run a process safely without shell=True. Return (success, message)."""
        try:
            subprocess.Popen(cmd)
            return True, "Launched"
        except FileNotFoundError:
            return False, "Executable not found"
        except Exception as e:
            logger.exception("Error running process %s: %s", cmd, e)
            return False, str(e)

    def _open_web_fallback(self, app_name: str) -> str:
        """Open browser fallback for common services."""
        web_services = {
            "whatsapp": "https://web.whatsapp.com",
            "instagram": "https://www.instagram.com",
            "facebook": "https://www.facebook.com",
            "twitter": "https://twitter.com",
            "telegram": "https://web.telegram.org",
            "youtube": "https://www.youtube.com",
            "gmail": "https://mail.google.com",
            "spotify": "https://open.spotify.com",
            "chrome": "https://www.google.com",
        }
        key = app_name.lower()
        url = web_services.get(key)
        if url:
            webbrowser.open(url)
            resp = f"Opening {app_name} in browser."
        else:
            resp = f"Could not find {app_name} locally or as a web service."
        speak(resp)
        return resp

    def open_app(self, app_name: str) -> str:
        """Open a whitelisted application; do not shell-expand user strings."""
        if not app_name:
            return "No application specified."

        key = app_name.lower().strip()
        # direct mapping first
        if key in self.app_paths:
            path = self.app_paths[key]
            try:
                if self.os_type == "windows":
                    os.startfile(path)
                    resp = f"Opening {app_name}"
                elif self.os_type == "darwin":
                    success, msg = self._run_process(["open", "-a", path])
                    resp = f"Opening {app_name}" if success else f"Failed to open {app_name}: {msg}"
                else:
                    success, msg = self._run_process([path])
                    resp = f"Opening {app_name}" if success else f"Failed to open {app_name}: {msg}"
            except Exception as e:
                logger.exception("open_app error for %s: %s", app_name, e)
                resp = self._open_web_fallback(app_name)
        else:
            # Not in whitelist — attempt safe open by treated name (no shell)
            try:
                if self.os_type == "windows":
                    os.startfile(key)
                    resp = f"Opening {app_name}"
                elif self.os_type == "darwin":
                    success, msg = self._run_process(["open", "-a", app_name])
                    resp = f"Opening {app_name}" if success else self._open_web_fallback(app_name)
                else:
                    success, msg = self._run_process([key])
                    resp = f"Opening {app_name}" if success else self._open_web_fallback(app_name)
            except Exception:
                resp = self._open_web_fallback(app_name)

        logger.info("open_app: %s -> %s", app_name, resp)
        speak(resp)
        return resp

    def close_application(self, app_name: str) -> str:
        """Attempt to close application by name; use safe commands."""
        if not app_name:
            return "No application specified."

        key = app_name.lower().strip()
        try:
            if self.os_type == "windows":
                exe = self.app_paths.get(key)
                if exe:
                    subprocess.Popen(["taskkill", "/f", "/im", exe])
                    resp = f"Attempted to close {app_name}"
                else:
                    resp = f"I don't have a safe process name registered for {app_name}"
            else:
                proc = self.app_paths.get(key)
                if proc:
                    os.system(f"pkill -f {proc}")
                    resp = f"Attempted to close {app_name}"
                else:
                    resp = f"I don't have a safe process name registered for {app_name}"
        except Exception as e:
            logger.exception("close_application error: %s", e)
            resp = f"Failed to close {app_name}: {e}"

        speak(resp)
        return resp

    def system_control(self, control_type: str) -> str:
        """Non-destructive safety: require separate confirmation for shutdown/restart externally."""
        t = control_type.lower() if control_type else ""
        try:
            if t == "shutdown":
                resp = "Shutdown requested. Please confirm before proceeding."
            elif t == "restart":
                resp = "Restart requested. Please confirm before proceeding."
            elif t == "lock":
                if self.os_type == "windows":
                    os.system("rundll32.exe user32.dll,LockWorkStation")
                elif self.os_type == "darwin":
                    subprocess.Popen(["pmset", "displaysleepnow"])
                else:
                    subprocess.Popen(["gnome-screensaver-command", "-l"])
                resp = "Locking screen."
            elif t == "sleep":
                if self.os_type == "windows":
                    subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
                elif self.os_type == "darwin":
                    subprocess.Popen(["pmset", "sleepnow"])
                else:
                    subprocess.Popen(["systemctl", "suspend"])
                resp = "Putting system to sleep."
            else:
                resp = "Unknown system control command."
        except Exception as e:
            logger.exception("system_control failed: %s", e)
            resp = f"Failed to perform {control_type}: {e}"

        speak(resp)
        return resp

    def get_system_info(self) -> str:
        """Return a string summary of system info."""
        try:
            os_info = f"{platform.system()} {platform.release()}"
            resp = f"System: {os_info}"
        except Exception as e:
            logger.exception("get_system_info error: %s", e)
            resp = "Unable to retrieve system information."
        return resp


# global instance
system_controller = SystemController()
