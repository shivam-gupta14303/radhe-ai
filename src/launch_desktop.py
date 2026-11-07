# launch_desktop.py
"""
Radhe Desktop Launcher.

Usage:
    python src/launch_desktop.py         # Launches Native Desktop GUI
    python src/launch_desktop.py --gui   # Launches Native Desktop GUI (Tkinter)
    python src/launch_desktop.py --web   # Launches Flask Web Server on http://localhost:5000
    python src/launch_desktop.py --app   # Launches Flask Web Server and opens standalone Desktop App window
"""

import sys
import os
import argparse
import subprocess
import webbrowser
import time
from pathlib import Path

# Ensure src in sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from flask_server import start_flask_server


def open_browser_app(url: str = "http://127.0.0.1:5000"):
    """Try opening in frameless standalone app mode via Edge or Chrome."""
    edge_paths = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"
    ]
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")
    ]

    for p in edge_paths + chrome_paths:
        if os.path.exists(p):
            try:
                subprocess.Popen([p, f"--app={url}", "--window-size=1080,720"])
                return
            except Exception:
                pass

    # Fallback to standard default browser
    webbrowser.open(url)


def main():
    parser = argparse.ArgumentParser(description="Radhe Desktop Assistant Launcher")
    parser.add_argument("--gui", action="store_true", help="Launch native Tkinter desktop interface")
    parser.add_argument("--web", action="store_true", help="Launch web application server only")
    parser.add_argument("--app", action="store_true", help="Launch standalone desktop web app window")
    args = parser.parse_args()

    if args.web:
        print("Starting Radhe Web Server on http://127.0.0.1:5000...")
        import flask_server
        flask_server.app.run(host="127.0.0.1", port=5000, debug=False)
        return

    if args.app:
        print("Starting Radhe Desktop App...")
        start_flask_server(host="127.0.0.1", port=5000)
        time.sleep(1)
        open_browser_app("http://127.0.0.1:5000")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down Radhe Desktop.")
            return

    # Default: Native Desktop GUI
    try:
        from desktop_gui import launch_gui
        launch_gui()
    except Exception as e:
        print(f"Native GUI failed ({e}). Falling back to Web App mode...")
        start_flask_server(host="127.0.0.1", port=5000)
        open_browser_app("http://127.0.0.1:5000")


if __name__ == "__main__":
    main()
