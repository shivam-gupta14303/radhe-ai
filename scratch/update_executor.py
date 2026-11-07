from pathlib import Path

p = Path("src/command_executor.py")
content = p.read_text(encoding="utf-8")

target = '        if intent == "set_whatsapp_mode":'

handlers = """        if intent == "remember_fact":
            fact = entities.get("fact") or text
            fact_clean = re.sub(r"^(?:remember\\s+(?:that\\s+)?|note\\s+down\\s+(?:that\\s+)?|save\\s+to\\s+memory\\s+|yad\\s+rakhna\\s+(?:ki\\s+)?|yaad\\s+rakhna\\s+(?:ki\\s+)?|yaad\\s+rakho\\s+(?:ki\\s+)?|mera\\s+)", "", str(fact), flags=re.I).strip()
            if not fact_clean:
                fact_clean = str(fact)
            mem_id = self.memory.add_memory(text=fact_clean, user_id=user_id)
            return self._resp(self._lang(
                "Got it. I have saved that to my memory.",
                "Theek hai, maine yaad rakh liya hai.",
                f"Done, yaad rakh liya: {fact_clean}.",
            ))

        if intent == "recall_memory":
            query = entities.get("query", "").strip()
            if query:
                results = self.memory.search_memories(query=query, user_id=user_id, limit=3)
                if results:
                    items = [r.get("text", "") for r in results]
                    joined = "; ".join(items)
                    return self._resp(self._lang(
                        f"Here is what I remember about {query}: {joined}",
                        f"{query} ke baare mein mujhe yeh yaad hai: {joined}",
                        f"Found this about {query}: {joined}",
                    ))
                else:
                    return self._resp(self._lang(
                        f"I don't have any specific memories about {query}.",
                        f"Mujhe {query} ke baare mein kuch yaad nahi hai.",
                        f"No memories found for {query}.",
                    ))
            else:
                summary = self.memory.get_memories_summary(user_id=user_id)
                total = summary.get("total", 0)
                by_type = summary.get("by_type", {})
                types_str = ", ".join(f"{count} {t}" for t, count in by_type.items() if count > 0)
                return self._resp(self._lang(
                    f"I currently have {total} memories saved ({types_str or 'none'}).",
                    f"Mere paas {total} yaadein saved hain ({types_str or 'kuch nahi'}).",
                    f"You have {total} memories in Radhe ({types_str or 'empty'}).",
                ))

        if intent == "forget_memory":
            query = entities.get("query", "").strip().lower()
            if not query or "all" in query or "everything" in query or "sab" in query:
                self.memory.clear_memories(user_id=user_id)
                return self._resp(self._lang(
                    "All memories have been cleared.",
                    "Maine saari yaadein mita di hain.",
                    "All memories cleared successfully.",
                ))
            else:
                deleted = self.memory.delete(user_id, query)
                if deleted:
                    return self._resp(self._lang(
                        f"Removed memory matching '{query}'.",
                        f"'{query}' se judi memory hata di hai.",
                        f"Deleted memory related to '{query}'.",
                    ))
                else:
                    return self._resp(self._lang(
                        f"No memory found matching '{query}'.",
                        f"'{query}' se judi koi memory nahi mili.",
                        f"Couldn't find any memory matching '{query}'.",
                    ))

        if intent == "export_memory":
            fmt = entities.get("format", "json")
            path = self.memory.export_data(user_id=user_id, format=fmt)
            return self._resp(self._lang(
                f"Your data has been exported successfully to {path}.",
                f"Aapka data safalta-purvak export ho gaya hai: {path}.",
                f"Exported your memories to {path}.",
            ))

        if intent == "set_whatsapp_mode":"""

if target in content:
    content = content.replace(target, handlers, 1)
    p.write_text(content, encoding="utf-8")
    print("Added memory intent handlers to command_executor.py")
else:
    print("Target not found in command_executor.py")
