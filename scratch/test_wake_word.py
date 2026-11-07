import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from speech import is_wake_word_match

tests = [
    ("radhe", True),
    ("hey radhe", True),
    ("radha", True),
    ("hey radha", True),
    ("hello radhey", True),
    ("ok radhe", True),
    ("\u0930\u093e\u0927\u0947", True),
    ("\u0930\u093e\u0927\u093e", True),
    ("sun radhe suno", True),
    ("parade", False),
    ("radio station", False),
    ("trade mark", False),
    ("i am ready", False),
]

all_passed = True
for phrase, expected in tests:
    res = is_wake_word_match(phrase, "radhe")
    status = "[OK]" if res == expected else "[FAIL]"
    safe_phrase = phrase.encode("ascii", errors="backslashreplace").decode("ascii")
    print(f"{status} phrase: '{safe_phrase}' -> {res} (expected {expected})")
    if res != expected:
        all_passed = False

if all_passed:
    print("[ALL PASS] Wake word matching works correctly!")
else:
    sys.exit(1)
