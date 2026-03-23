# automation.py
"""
AutomationManager for Radhe.

Improvements vs previous version:
- Searches in user home directory by default (more useful than cwd).
- Results sorted by modification time (newest first).
- directory parameter can be a list of paths to search multiple locations.
- Added open_file() so Radhe can open a found file directly.
- Added list_recent_files() — "what files did I work on recently?"
"""

import os
import logging
from pathlib import Path
from typing import List, Union

logger = logging.getLogger("Radhe_Automation")
logger.setLevel(logging.INFO)

# Common places to search (user home + Desktop + Documents + Downloads)
DEFAULT_SEARCH_DIRS = [
    str(Path.home()),
    str(Path.home() / "Desktop"),
    str(Path.home() / "Documents"),
    str(Path.home() / "Downloads"),
]


class AutomationManager:

    def __init__(self):
        pass

    # ==================================================================
    # FILE SEARCH
    # ==================================================================

    def automate_file_search(
        self,
        directory: Union[str, List[str]] = None,
        pattern:   str = "*",
        max_results: int = 50
    ) -> List[str]:
        """
        Search for files matching a glob pattern in one or more directories.

        directory: a single path string, a list of paths, or None (uses defaults).
        pattern:   glob pattern e.g. "*.pdf", "report*", "*.py"
        Returns:   list of absolute path strings, newest-first, up to max_results.
        """
        if directory is None:
            dirs = DEFAULT_SEARCH_DIRS
        elif isinstance(directory, list):
            dirs = directory
        else:
            dirs = [directory]

        results: List[Path] = []

        for d in dirs:
            p = Path(d)
            if not p.exists():
                continue
            try:
                found = list(p.rglob(pattern))
                results.extend(found)
            except PermissionError:
                logger.debug("Permission denied: %s", d)
            except Exception as e:
                logger.warning("Search error in %s: %s", d, e)

        # Sort newest-first, deduplicate, limit
        unique = list({str(f): f for f in results}.values())
        try:
            unique.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        except Exception:
            pass

        return [str(f) for f in unique[:max_results]]

    # ==================================================================
    # OPEN FILE
    # ==================================================================

    def open_file(self, file_path: str) -> str:
        """
        Open a file with the system's default application.
        """
        path = Path(file_path)
        if not path.exists():
            return f"File not found: {file_path}"

        try:
            import subprocess, platform
            system = platform.system().lower()

            if system == "windows":
                os.startfile(str(path))
            elif system == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])

            return f"Opening {path.name}."

        except Exception as e:
            logger.exception("open_file error: %s", e)
            return f"Could not open {path.name}."

    # ==================================================================
    # RECENT FILES
    # ==================================================================

    def list_recent_files(self, hours: int = 24, max_results: int = 10) -> List[str]:
        """
        Return files modified in the last `hours` hours across default search dirs.
        Useful for "what did I work on recently?"
        """
        import time
        cutoff  = time.time() - hours * 3600
        results = []

        for d in DEFAULT_SEARCH_DIRS:
            p = Path(d)
            if not p.exists():
                continue
            try:
                for f in p.rglob("*"):
                    if f.is_file():
                        try:
                            if f.stat().st_mtime >= cutoff:
                                results.append(f)
                        except Exception:
                            pass
            except Exception:
                pass

        results.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        return [str(f) for f in results[:max_results]]
    
    # ===============================================================================
    # RUN AUTOMATION
    # ===============================================================================

    def run(self, task: str) -> str:
        task = (task or "").lower().strip()

        # 📂 Recent files
        if "recent" in task:
            files = self.list_recent_files()
            if not files:
                return "No recent files found."
            return "Recent files:\n" + "\n".join(files[:5])

        # 🔍 File search
        if any(k in task for k in ["find", "search", "dhundo", "khojo"]):
            pattern = (
                task.replace("find", "")
                    .replace("search", "")
                    .strip() or "*"
            )

            files = self.automate_file_search(pattern=pattern)

            if not files:
                return f"No files found matching '{pattern}'."

            return "Found:\n" + "\n".join(files[:5])

        # 📄 Open file
        if "open" in task:
            filename = task.replace("open", "").strip()
            if not filename:
                return "Please specify the file name to open."
            return self.open_file(filename)

        # ⚙️ Default fallback
        return f"Running automation: {task}"


# ── Global instance ───────────────────────────────────────────────────
automation_manager = AutomationManager()