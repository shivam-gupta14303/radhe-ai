# scratch/update_radhe_clarify.py

with open("src/radhe.py", "r", encoding="utf-8") as f:
    text = f.read().replace("\r\n", "\n")

old_block = '''                    engine_result = engine.handle(text)
                    if engine_result and not engine_result.silent_skipped:
                        action = engine_result.action
                        if action.get("intent") == "clarify":
                            reply          = action.get("entities", {}).get("question", "Thoda aur batao?")
                            awaiting_reply = True
                            awaiting_prompt = reply
                            speak(reply)
                            break
                        else:
                            awaiting_reply = False
                            awaiting_prompt = ""
                            reply = action.get("entities", {}).get("_output", "")
                            if not reply:
                                result = executor.execute(action, text)
                                reply  = result.get("voice") or result.get("text", "")

                            if not executor.context.get("onboarding_complete", True):
                                awaiting_reply = True
                                awaiting_prompt = reply
                            if executor.context.get("awaiting_contact") or executor.context.get("awaiting_message"):
                                awaiting_reply = True
                                awaiting_prompt = reply

                            if reply:
                                speak(reply)'''

new_block = '''                    engine_result = engine.handle(text)
                    if engine_result and not engine_result.silent_skipped:
                        action = engine_result.action
                        if action.get("intent") == "clarify":
                            reply          = action.get("question") or action.get("entities", {}).get("question", "Thoda aur batao?")
                            awaiting_reply = True
                            awaiting_prompt = reply
                            speak(reply)
                            break
                        else:
                            awaiting_reply = False
                            awaiting_prompt = ""
                            reply = action.get("entities", {}).get("_output", "")
                            if not reply:
                                result = executor.execute(action, text)
                                reply  = result.get("voice") or result.get("text", "")

                            if not executor.context.get("onboarding_complete", True):
                                awaiting_reply = True
                                awaiting_prompt = reply
                            if executor.context.get("awaiting_contact") or executor.context.get("awaiting_message"):
                                awaiting_reply = True
                                awaiting_prompt = reply

                            if reply:
                                speak(reply)
                    else:
                        parsed_action = parser.parse(text)
                        result = executor.execute(parsed_action, text)
                        reply = result.get("voice") or result.get("text", "")
                        if executor.context.get("awaiting_contact") or executor.context.get("awaiting_message"):
                            awaiting_reply = True
                            awaiting_prompt = reply
                        if reply:
                            speak(reply)'''

assert old_block in text, "old_block not found in radhe.py"
text = text.replace(old_block, new_block, 1)
with open("src/radhe.py", "w", encoding="utf-8") as f:
    f.write(text)
print("[OK] src/radhe.py updated.")
