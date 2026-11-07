import re
from pathlib import Path

p = Path("src/memory.py")
content = p.read_text(encoding="utf-8")

# 1. Update classify_memory_type with short_term check
old_classify = """def classify_memory_type(text: str) -> str:
    \"\"\"
    Automatically assign an incoming memory snippet into one of the 7 memory types.
    \"\"\"
    t = text.lower().strip()

    # Preferences
    if any(w in t for w in ("like", "likes", "prefer", "preference", "love", "hate", "dislike", "favorite", "favourite", "pasand")):
        return MemoryType.PREFERENCE"""

new_classify = """def classify_memory_type(text: str) -> str:
    \"\"\"
    Automatically assign an incoming memory snippet into one of the 7 memory types.
    \"\"\"
    t = text.lower().strip()

    # Short-term / Transient conversation context
    if any(w in t for w in ("user said", "assistant said", "just now", "in this session", "current chat", "weather today", "what is the")):
        return MemoryType.SHORT_TERM

    # Preferences
    if any(w in t for w in ("like", "likes", "prefer", "preference", "love", "hate", "dislike", "favorite", "favourite", "pasand")):
        return MemoryType.PREFERENCE"""

content = content.replace(old_classify, new_classify)

# 2. Update add_memory signature & handling
old_add = """    def add_memory(
        self,
        user_id: str = "default",
        text: str = "",
        memory_type: Optional[str] = None,
        category: str = "general",
        confidence: float = 0.85,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        \"\"\"
        Store a new memory entry across the 7 memory types.
        Detects contradictions and deduplicates automatically.
        \"\"\"
        clean_text = text.strip()
        if not clean_text:
            return {}"""

new_add = """    def add_memory(
        self,
        *args,
        user_id: str = "default",
        text: str = "",
        memory_type: Optional[str] = None,
        category: str = "general",
        confidence: float = 0.85,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        \"\"\"
        Store a new memory entry across the 7 memory types.
        Detects contradictions and deduplicates automatically.
        \"\"\"
        if len(args) == 1:
            text = str(args[0])
        elif len(args) >= 2:
            if len(str(args[0])) < 30 and (" " not in str(args[0])):
                user_id, text = str(args[0]), str(args[1])
            else:
                text, user_id = str(args[0]), str(args[1])
        elif not text and user_id and user_id != "default":
            text = user_id
            user_id = "default"

        clean_text = text.strip()
        if not clean_text:
            return {}"""

content = content.replace(old_add, new_add)

# 3. Update search_memories signature & category handling
old_search = """    def search_memories(
        self,
        user_id: str = "default",
        query: str = "",
        memory_type: Optional[str] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        \"\"\"
        Search memories by keyword, type, and relevance ranking.
        \"\"\"
        try:
            with self._connection() as conn:
                cur = conn.cursor()
                params = [user_id]
                clauses = ["user_id = ?", "status = 'active'"]

                if memory_type and memory_type in ALL_MEMORY_TYPES:
                    clauses.append("type = ?")
                    params.append(memory_type)

                if query and query.strip():
                    clauses.append("context LIKE ?")
                    params.append(f"%{query.strip()}%")"""

new_search = """    def search_memories(
        self,
        *args,
        user_id: str = "default",
        query: str = "",
        category: Optional[str] = None,
        memory_type: Optional[str] = None,
        limit: int = 5,
        **kwargs
    ) -> List[Dict[str, Any]]:
        \"\"\"
        Search memories by keyword, type, and relevance ranking.
        \"\"\"
        if len(args) == 1:
            query = str(args[0])
        elif len(args) >= 2:
            if len(str(args[0])) < 30 and (" " not in str(args[0])):
                user_id, query = str(args[0]), str(args[1])
            else:
                query, user_id = str(args[0]), str(args[1])
        elif not query and user_id and user_id != "default":
            query = user_id
            user_id = "default"

        try:
            with self._connection() as conn:
                cur = conn.cursor()
                params = [user_id]
                clauses = ["user_id = ?", "status = 'active'"]

                target_type = memory_type or category
                if target_type:
                    clauses.append("(type = ? OR category = ?)")
                    params.extend([target_type, target_type])

                if query and query.strip():
                    clauses.append("context LIKE ?")
                    params.append(f"%{query.strip()}%")"""

content = content.replace(old_search, new_search)

p.write_text(content, encoding="utf-8")
print("Updated memory.py arguments and search successfully.")
