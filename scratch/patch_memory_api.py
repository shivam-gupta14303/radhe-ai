from pathlib import Path

p = Path("src/memory.py")
content = p.read_text(encoding="utf-8")

methods = '''
    def get_stats(self) -> dict:
        """Return memory statistics by tier."""
        return {
            "total": self.count(),
            "summary": self.get_memories_summary(),
        }

    def get_all_memories(self, memory_type=None, limit: int = 200) -> list:
        """Return all stored memories with optional type filter."""
        return self.recall_memory("", memory_type=memory_type, limit=limit)

    def get_context_prompt(self, query: str = "") -> str:
        """Return formatted memory context for LLM prompt."""
        return self.get_relevant_context(query)

    def export_memories(self, format: str = "json") -> str:
        """Export memories as JSON or Markdown string."""
        return self.export_data(format=format)
'''

target = "    def get_recent_conversation(self"

if target in content and "def get_stats" not in content:
    content = content.replace(target, methods + "\n" + target, 1)
    p.write_text(content, encoding="utf-8")
    print("SUCCESS: Added API helper methods to MemoryManager")
else:
    print("ALREADY PRESENT OR TARGET NOT FOUND")
