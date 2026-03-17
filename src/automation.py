"""
AutomationManager

Handles automation tasks like file search.
"""

from pathlib import Path
from typing import List


class AutomationManager:

    def __init__(self):
        pass

    def automate_file_search(self, directory: str, pattern: str) -> List[str]:

        try:

            path = Path(directory)

            files = list(path.rglob(pattern))[:200]

            return [str(f) for f in files]

        except Exception as e:

            print(f"File search error: {e}")

            return []