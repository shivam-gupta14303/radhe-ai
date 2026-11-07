import re
from pathlib import Path

p = Path("src/memory.py")
content = p.read_text(encoding="utf-8")

# 1. Update classify_memory_type: schedule before contact, include appointment/flight
old_sched = """    # Schedule / Dates / Routines
    if any(w in t for w in ("birthday", "anniversary", "every day", "daily", "routine", "every morning", "every week", "schedule", "subah", "shaam")):
        return MemoryType.SCHEDULE"""

new_sched = """    # Schedule / Dates / Routines / Appointments
    if any(w in t for w in ("appointment", "meeting", "flight", "birthday", "anniversary", "every day", "daily", "routine", "every morning", "every week", "schedule", "subah", "shaam", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "tomorrow", "pm", "am")):
        return MemoryType.SCHEDULE"""

content = content.replace(old_sched, new_sched)

# 2. Update get_memory_by_id to handle dict/int and add is_active
old_get_mem = """    def get_memory_by_id(self, memory_id: int) -> Optional[Dict[str, Any]]:
        \"\"\"Retrieve a specific memory by its ID.\"\"\"
        try:
            with self._connection() as conn:
                cur = conn.cursor()
                cur.execute(\"\"\"
                    SELECT id, user_id, timestamp, context, type, category, status, confidence, metadata
                    FROM memories WHERE id = ?
                \"\"\", (memory_id,))
                row = cur.fetchone()
                if row:
                    meta = json.loads(row[8] or "{}")
                    return {
                        "id": row[0],
                        "user_id": row[1],
                        "timestamp": row[2],
                        "text": row[3],
                        "type": row[4],
                        "category": row[5],
                        "status": row[6],
                        "confidence": row[7],
                        "metadata": meta
                    }"""

new_get_mem = """    def get_memory_by_id(self, memory_id: Any) -> Optional[Dict[str, Any]]:
        \"\"\"Retrieve a specific memory by its ID.\"\"\"
        if isinstance(memory_id, dict):
            memory_id = memory_id.get("id")
        try:
            with self._connection() as conn:
                cur = conn.cursor()
                cur.execute(\"\"\"
                    SELECT id, user_id, timestamp, context, type, category, status, confidence, metadata
                    FROM memories WHERE id = ?
                \"\"\", (int(memory_id),))
                row = cur.fetchone()
                if row:
                    meta = json.loads(row[8] or "{}")
                    return {
                        "id": row[0],
                        "user_id": row[1],
                        "timestamp": row[2],
                        "text": row[3],
                        "type": row[4],
                        "category": row[5],
                        "status": row[6],
                        "is_active": 1 if row[6] == 'active' else 0,
                        "confidence": row[7],
                        "metadata": meta
                    }"""

content = content.replace(old_get_mem, new_get_mem)

# 3. Update edit_memory and delete_memory_by_id to handle dict/int
old_edit = """    def edit_memory(self, memory_id: int, new_text: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        \"\"\"Edit the content or metadata of an existing memory entry.\"\"\"
        clean = new_text.strip()
        try:
            with self._connection() as conn:"""

new_edit = """    def edit_memory(self, memory_id: Any, new_text: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        \"\"\"Edit the content or metadata of an existing memory entry.\"\"\"
        if isinstance(memory_id, dict):
            memory_id = memory_id.get("id")
        memory_id = int(memory_id)
        clean = new_text.strip()
        try:
            with self._connection() as conn:"""

content = content.replace(old_edit, new_edit)

old_del = """    def delete_memory_by_id(self, memory_id: int) -> bool:
        \"\"\"Permanently delete a memory record by ID.\"\"\"
        try:
            with self._connection() as conn:"""

new_del = """    def delete_memory_by_id(self, memory_id: Any) -> bool:
        \"\"\"Permanently delete a memory record by ID.\"\"\"
        if isinstance(memory_id, dict):
            memory_id = memory_id.get("id")
        memory_id = int(memory_id)
        try:
            with self._connection() as conn:"""

content = content.replace(old_del, new_del)

# 4. Update get_memories_summary to include profile
old_summ = """    def get_memories_summary(self, user_id: str = "default") -> Dict[str, Any]:
        \"\"\"Return counts of memories per category and active status.\"\"\"
        summary = {"total": 0, "by_type": {}}"""

new_summ = """    def get_memories_summary(self, user_id: str = "default") -> Dict[str, Any]:
        \"\"\"Return counts of memories per category and active status.\"\"\"
        summary = {"total": 0, "by_type": {}, "profile": self.get_profile(user_id=user_id)}"""

content = content.replace(old_summ, new_summ)

# 5. Update export_data to accept format and optionally write to file
old_export = """    def export_data(self, user_id: str = "default", export_format: str = "json") -> str:
        \"\"\"Export user profile and memories as JSON or readable text report.\"\"\"
        memories = self.search_memories(user_id=user_id, query="", limit=1000)
        profile = self.get_profile(user_id=user_id)
        summary = self.get_memories_summary(user_id=user_id)

        data = {
            "exported_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "user_id": user_id,
            "summary": summary,
            "profile": profile,
            "memories": memories
        }

        if export_format.lower() == "json":
            return json.dumps(data, indent=2, ensure_ascii=False)

        # Markdown format report
        lines = [
            f"# Radhe Personal Data & Memory Export ({user_id})",
            f"Exported: {data['exported_at']}",
            f"Total Active Memories: {summary['total']}\\n",
            "## Personal Profile",
        ]
        for k, v in profile.items():
            lines.append(f"- **{k.capitalize()}**: {v}")

        lines.append("\\n## Saved Memories by Category")
        for m in memories:
            lines.append(f"- **[{m['type'].upper()}]** {m['text']} *(Added: {m['timestamp'][:10]})*")

        return "\\n".join(lines)"""

new_export = """    def export_data(self, user_id: str = "default", export_format: str = "json", format: Optional[str] = None, save_to_file: bool = True) -> str:
        \"\"\"Export user profile and memories as JSON or readable text report.\"\"\"
        fmt = (format or export_format).lower()
        memories = self.search_memories(user_id=user_id, query="", limit=1000)
        profile = self.get_profile(user_id=user_id)
        summary = self.get_memories_summary(user_id=user_id)

        data = {
            "exported_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "user_id": user_id,
            "summary": summary,
            "profile": profile,
            "memories": memories
        }

        if fmt == "json":
            content = json.dumps(data, indent=2, ensure_ascii=False)
        else:
            lines = [
                f"# Radhe Personal Data & Memory Export ({user_id})",
                f"Exported: {data['exported_at']}",
                f"Total Active Memories: {summary['total']}\\n",
                "## Personal Profile",
            ]
            for k, v in profile.items():
                lines.append(f"- **{k.capitalize()}**: {v}")

            lines.append("\\n## Saved Memories by Category")
            for m in memories:
                lines.append(f"- **[{m['type'].upper()}]** {m['text']} *(Added: {m['timestamp'][:10]})*")

            content = "\\n".join(lines)

        if save_to_file:
            ext = "json" if fmt == "json" else "md"
            ts_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            export_path = Path("data") / f"radhe_export_{ts_str}.{ext}"
            export_path.parent.mkdir(parents=True, exist_ok=True)
            export_path.write_text(content, encoding="utf-8")
            return str(export_path)

        return content"""

content = content.replace(old_export, new_export)

p.write_text(content, encoding="utf-8")
print("Patched memory.py successfully.")
