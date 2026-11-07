# scratch/fix_speech_and_parser.py
import re

# ======================================================================
# 1. FIX SPEECH.PY DUPLICATE LISTEN_FOR_WAKE_WORD
# ======================================================================
print("Cleaning duplicate in speech.py...")
with open("src/speech.py", "r", encoding="utf-8") as f:
    speech_text = f.read().replace("\r\n", "\n")

# Find all occurrences of "def listen_for_wake_word"
occurrences = [m.start() for m in re.finditer(r"def listen_for_wake_word\(", speech_text)]
print(f"Found {len(occurrences)} occurrences of listen_for_wake_word.")

if len(occurrences) > 1:
    second_idx = occurrences[1]
    # The second occurrence ends right before #  COMMAND CAPTURE
    end_marker = "# ======================================================================\n#  COMMAND CAPTURE"
    end_idx = speech_text.find(end_marker, second_idx)
    if end_idx != -1:
        # Find the comment block preceding second_idx
        prev_comment_idx = speech_text.rfind("# ======================================================================", 0, second_idx)
        if prev_comment_idx != -1 and prev_comment_idx > occurrences[0]:
            cut_start = prev_comment_idx
        else:
            cut_start = second_idx
        speech_text = speech_text[:cut_start] + speech_text[end_idx:]
        with open("src/speech.py", "w", encoding="utf-8") as f:
            f.write(speech_text)
        print("[OK] Duplicate listen_for_wake_word removed.")

# ======================================================================
# 2. FIX COMMAND_PARSER.PY
# ======================================================================
print("Updating command_parser.py...")
with open("src/command_parser.py", "r", encoding="utf-8") as f:
    cp_text = f.read().replace("\r\n", "\n")

# Add mode words to _BAD_CONTACTS
bad_target = '"instagram", "sms", "email", "gmail", "app", "saying", "that", "ki", "please",'
bad_replacement = '"instagram", "sms", "email", "gmail", "app", "saying", "that", "ki", "please", "mode", "settings", "setting", "monitor", "approval", "reply",'

if bad_target in cp_text:
    cp_text = cp_text.replace(bad_target, bad_replacement, 1)

# In _parse_action, check if any word in candidate contact is in _BAD_CONTACTS or "mode"
# Also ensure set_whatsapp_mode and get_whatsapp_mode have high confidence
score_check_target = '''            if score > best_score:
                best_score, best_intent, best_entities = score, intent_id, ents'''

score_check_replacement = '''            # Prevent false send_message when candidate contact contains bad contact tokens (e.g. "mode to")
            if intent_id == "send_message":
                c_test = (ents.get("contact") or "").lower()
                if any(w in c_test.split() for w in ("mode", "settings", "setting", "monitor", "approval")):
                    continue

            if score > best_score:
                best_score, best_intent, best_entities = score, intent_id, ents'''

if score_check_target in cp_text:
    cp_text = cp_text.replace(score_check_target, score_check_replacement, 1)

with open("src/command_parser.py", "w", encoding="utf-8") as f:
    f.write(cp_text)
print("[OK] command_parser.py updated.")
