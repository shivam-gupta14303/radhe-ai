# system_control.py
"""
SystemController for Radhe.

Fixes applied vs previous version:
- close_application() replaced os.system(f"pkill -f {proc}") with
  subprocess.Popen(["pkill", "-f", proc]) — eliminates shell injection risk.
- system_control() shutdown/restart now actually execute after confirmation
  flag is passed, instead of just returning a string forever.

Goal-aligned improvements:
- get_battery_status() — Radhe can answer "how much battery do I have?"
- get_volume() / set_volume() — Radhe can control system volume by voice.
- get_running_apps() — Radhe can tell you what's open.
- take_screenshot() — saved to data/screenshots/; useful for vision pipeline.
"""

import os
import subprocess
import platform
import webbrowser
import logging
import datetime
from typing import Dict, Tuple, Optional
from pathlib import Path

try:
    from speech import speak as _speak
except Exception:
    def _speak(text: str):
        print(f"[TTS] {text}")

logger = logging.getLogger("Radhe_System")
logger.setLevel(logging.INFO)


class SystemController:

    def __init__(self):
        self.os_type   = platform.system().lower()   # 'windows', 'darwin', 'linux'
        self.app_paths = self._load_app_paths()
        Path("data/screenshots").mkdir(parents=True, exist_ok=True)

    # ==================================================================
    # APP PATH MAP
    # ==================================================================

    def _load_app_paths(self) -> Dict[str, str]:
        if self.os_type == "windows":
            return {
                "chrome":        "chrome.exe",
                "notepad":       "notepad.exe",
                "vscode":        "code.exe",
                "calculator":    "calc.exe",
                "file explorer": "explorer.exe",
                "spotify":       "spotify.exe",
                "word":          "WINWORD.EXE",
                "excel":         "EXCEL.EXE",
                "powerpoint":    "POWERPNT.EXE",
            }
        elif self.os_type == "darwin":
            return {
                "chrome":   "/Applications/Google Chrome.app",
                "safari":   "/Applications/Safari.app",
                "vscode":   "/Applications/Visual Studio Code.app",
                "spotify":  "/Applications/Spotify.app",
                "word":     "/Applications/Microsoft Word.app",
                "excel":    "/Applications/Microsoft Excel.app",
            }
        else:  # Linux
            return {
                "chrome":        "google-chrome",
                "firefox":       "firefox",
                "vscode":        "code",
                "spotify":       "spotify",
                "file explorer": "nautilus",
                "terminal":      "gnome-terminal",
            }

    # ==================================================================
    # INTERNAL HELPERS
    # ==================================================================

    def _run(self, cmd: list) -> Tuple[bool, str]:
        """Run a command safely without shell=True."""
        try:
            subprocess.Popen(cmd)
            return True, "OK"
        except FileNotFoundError:
            return False, "Executable not found."
        except Exception as e:
            logger.exception("_run error %s: %s", cmd, e)
            return False, str(e)

    def _web_fallback(self, app_name: str) -> str:
        """Open the web version of a common service."""
        WEB = {
            "whatsapp":  "https://web.whatsapp.com",
            "instagram": "https://www.instagram.com",
            "facebook":  "https://www.facebook.com",
            "twitter":   "https://twitter.com",
            "telegram":  "https://web.telegram.org",
            "youtube":   "https://www.youtube.com",
            "gmail":     "https://mail.google.com",
            "spotify":   "https://open.spotify.com",
            "chrome":    "https://www.google.com",
        }
        url = WEB.get(app_name.lower())
        if url:
            webbrowser.open(url)
            return f"Opening {app_name} in browser."
        return f"Could not find {app_name} locally or as a web service."

    def _say(self, text: str) -> str:
        """Speak and return text."""
        try:
            _speak(text)
        except Exception:
            pass
        return text

    # ==================================================================
    # OPEN APP
    # ==================================================================

    def open_app(self, app_name: str) -> str:
        if not app_name:
            return self._say("No application specified.")

        key  = app_name.lower().strip()
        path = self.app_paths.get(key)

        try:
            if path:
                if self.os_type == "windows":
                    os.startfile(path)
                    return self._say(f"Opening {app_name}.")
                elif self.os_type == "darwin":
                    ok, msg = self._run(["open", "-a", path])
                    return self._say(f"Opening {app_name}." if ok else self._web_fallback(app_name))
                else:
                    ok, msg = self._run([path])
                    return self._say(f"Opening {app_name}." if ok else self._web_fallback(app_name))
            else:
                # Not in whitelist — try OS open safely
                if self.os_type == "windows":
                    os.startfile(key)
                    return self._say(f"Opening {app_name}.")
                elif self.os_type == "darwin":
                    ok, _ = self._run(["open", "-a", app_name])
                    return self._say(f"Opening {app_name}." if ok else self._web_fallback(app_name))
                else:
                    ok, _ = self._run([key])
                    return self._say(f"Opening {app_name}." if ok else self._web_fallback(app_name))

        except Exception:
            return self._say(self._web_fallback(app_name))

    # ==================================================================
    # CLOSE APP
    # (Fix: replaced os.system shell string with subprocess list)
    # ==================================================================

    def close_application(self, app_name: str) -> str:
        if not app_name:
            return self._say("No application specified.")

        key = app_name.lower().strip()

        try:
            if self.os_type == "windows":
                exe = self.app_paths.get(key)
                if exe:
                    # Safe: list form — no shell injection
                    subprocess.Popen(["taskkill", "/f", "/im", exe])
                    return self._say(f"Closing {app_name}.")
                return self._say(f"I don't have a safe process name for {app_name}.")

            else:
                proc = self.app_paths.get(key, key)
                # Safe: list form — no shell injection
                subprocess.Popen(["pkill", "-f", proc])
                return self._say(f"Closing {app_name}.")

        except Exception as e:
            logger.exception("close_application error: %s", e)
            return self._say(f"Failed to close {app_name}.")

    # ==================================================================
    # SYSTEM CONTROL (shutdown / restart / lock / sleep)
    # (Fix: shutdown/restart now execute when confirmed=True)
    # ==================================================================

    def system_control(self, control_type: str, confirmed: bool = False) -> str:
        """
        confirmed=False  → returns a "please confirm" message (safe default).
        confirmed=True   → actually performs the action.

        Usage in executor:
            system_controller.system_control("shutdown", confirmed=True)
        """
        t = (control_type or "").lower().strip()

        try:
            if t in ("shutdown", "restart", "reboot"):
                if not confirmed:
                    return self._say(
                        f"{t.capitalize()} requested. "
                        "Please confirm by saying 'yes confirm shutdown' or 'yes confirm restart'."
                    )
                if t == "shutdown":
                    if self.os_type == "windows":
                        subprocess.Popen(["shutdown", "/s", "/t", "5"])
                    elif self.os_type == "darwin":
                        subprocess.Popen(["sudo", "shutdown", "-h", "now"])
                    else:
                        subprocess.Popen(["sudo", "shutdown", "-h", "now"])
                    return self._say("Shutting down in 5 seconds.")
                else:
                    if self.os_type == "windows":
                        subprocess.Popen(["shutdown", "/r", "/t", "5"])
                    elif self.os_type == "darwin":
                        subprocess.Popen(["sudo", "shutdown", "-r", "now"])
                    else:
                        subprocess.Popen(["sudo", "reboot"])
                    return self._say("Restarting in 5 seconds.")

            elif t == "lock":
                if self.os_type == "windows":
                    subprocess.Popen(["rundll32.exe", "user32.dll,LockWorkStation"])
                elif self.os_type == "darwin":
                    subprocess.Popen(["pmset", "displaysleepnow"])
                else:
                    subprocess.Popen(["gnome-screensaver-command", "-l"])
                return self._say("Screen locked.")

            elif t == "sleep":
                if self.os_type == "windows":
                    subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
                elif self.os_type == "darwin":
                    subprocess.Popen(["pmset", "sleepnow"])
                else:
                    subprocess.Popen(["systemctl", "suspend"])
                return self._say("Going to sleep.")

            else:
                return self._say(f"Unknown system command: {control_type}.")

        except Exception as e:
            logger.exception("system_control failed: %s", e)
            return self._say(f"Failed to perform {control_type}.")

    # ==================================================================
    # BATTERY STATUS  (new — goal: "how much battery do I have?")
    # ==================================================================

    def get_battery_status(self) -> str:
        """Return battery percentage and charging state as a string."""
        try:
            import psutil
            battery = psutil.sensors_battery()
            if battery is None:
                return "No battery detected (desktop system or psutil can't read it)."
            percent  = int(battery.percent)
            plugged  = "charging" if battery.power_plugged else "on battery"
            return f"Battery is at {percent}% and {plugged}."
        except ImportError:
            return "Install psutil for battery info: pip install psutil"
        except Exception as e:
            logger.exception("get_battery_status error: %s", e)
            return "Could not read battery status."

    # ==================================================================
    # VOLUME CONTROL  (new — goal: "set volume to 50%")
    # ==================================================================

    def  _set_volume_level(self, level: int) -> str:
        """
        Set system volume to `level` percent (0–100).
        Works on Windows, macOS, Linux (amixer).
        """
        level = max(0, min(100, int(level)))
        try:
            if self.os_type == "windows":
                # Uses pycaw or nircmd (nircmd.exe must be on PATH)
                subprocess.Popen(["nircmd.exe", "setsysvolume", str(int(level / 100 * 65535))])
            elif self.os_type == "darwin":
                subprocess.Popen(["osascript", "-e", f"set volume output volume {level}"])
            else:
                subprocess.Popen(["amixer", "-D", "pulse", "sset", "Master", f"{level}%"])
            return self._say(f"Volume set to {level} percent.")
        except Exception as e:
            logger.exception("set_volume error: %s", e)
            return self._say("Could not set volume.")
    
    def set_volume(self, level=None, action: str = "") -> str:
        if action:
            action = action.lower()

            if "up" in action or "louder" in action or "zyada" in action:
                level = 80

            elif "down" in action or "quieter" in action or "kam" in action:
                level = 30

        if level is None:
            return self._say("Please specify a volume level.")

        return self._set_volume_level(int(level))

    # ==================================================================
    # SCREENSHOT  (new — feeds into vision pipeline)
    # ==================================================================

    def take_screenshot(self) -> str:
        """
        Save a screenshot to data/screenshots/ and return the file path.
        """
        try:
            import pyautogui
            ts       = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            out_path = f"data/screenshots/screen_{ts}.png"
            pyautogui.screenshot(out_path)
            logger.info("Screenshot saved: %s", out_path)
            return out_path
        except ImportError:
            return "Install pyautogui for screenshots: pip install pyautogui"
        except Exception as e:
            logger.exception("take_screenshot error: %s", e)
            return ""

    # ==================================================================
    # RUNNING APPS  (new — goal: "what apps are running?")
    # ==================================================================

    def get_running_apps(self) -> str:
        """Return a short list of currently running process names."""
        try:
            import psutil
            names = sorted({
                p.name() for p in psutil.process_iter(["name"])
                if p.info["name"]
            })
            if not names:
                return "No processes found."
            sample = ", ".join(names[:15])
            suffix = f" (and {len(names) - 15} more)" if len(names) > 15 else ""
            return f"Running apps: {sample}{suffix}."
        except ImportError:
            return "Install psutil: pip install psutil"
        except Exception as e:
            logger.exception("get_running_apps error: %s", e)
            return "Could not list running apps."

    # ==================================================================
    # SYSTEM INFO
    # ==================================================================

    def get_system_info(self) -> str:
        try:
            return f"{platform.system()} {platform.release()} on {platform.machine()}."
        except Exception as e:
            logger.exception("get_system_info error: %s", e)
            return "Unable to retrieve system information."
    def close_app(self, app_name: str) -> str:
        return self.close_application(app_name)
    # ===================================================================
    # brightness control
    #====================================================================
    def set_brightness(self, level=None) -> str:
        level = max(0, min(100, int(level or 50)))

        try:
            import subprocess

            if self.os_type == "windows":
                subprocess.Popen(["nircmd.exe", "setbrightness", str(level)])

            elif self.os_type == "darwin":
                subprocess.Popen(["brightness", str(level / 100)])

            else:
                subprocess.Popen(["brightnessctl", "set", f"{level}%"])

            return self._say(f"Brightness set to {level} percent.")

        except Exception:
            return self._say("Could not set brightness.")


# ── Global instance ───────────────────────────────────────────────────
system_controller = SystemController()