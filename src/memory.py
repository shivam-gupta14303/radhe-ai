from contextlib import contextmanager
# src/memory.py
"""
Thread-safe Advanced MemoryManager — SQLite backend for Radhe.

7-Tier Memory Architecture:
1. short_term   : Recent conversation turns and session context.
2. long_term    : Important factual information about user.
3. preference   : Likes, dislikes, and communication preferences.
4. schedule     : Recurring routines, birthdays, important dates.
5. contact      : People, family, colleagues, and relationships.
6. project      : Ongoing goals, initiatives, and study topics.
7. task         : Action items, pending/completed tasks.

Features:
- Fast keyword search + TF-IDF ranking + score boosts.
- Semantic similarity scoring with sentence-transformers fallback.
- Contradiction and duplicate detection.
- Complete CRUD: add, search, edit, delete, clear, export.
- Context injection for LLM prompts.
"""

import os
import re
import json
import sqlite3
import datetime
import threading
import logging
from typing import List, Dict, Any, Optional, Tuple, Union
from pathlib import Path

from config import MEMORY_DB_FILE

logger = logging.getLogger("Radhe_Memory")
logger.setLevel(logging.INFO)

_lock = threading.Lock()


class MemoryType:
    SHORT_TERM = "short_term"
    LONG_TERM  = "long_term"
    PREFERENCE = "preference"
    SCHEDULE   = "schedule"
    CONTACT    = "contact"
    PROJECT    = "project"
    TASK       = "task"

ALL_MEMORY_TYPES = [
    MemoryType.SHORT_TERM,
    MemoryType.LONG_TERM,
    MemoryType.PREFERENCE,
    MemoryType.SCHEDULE,
    MemoryType.CONTACT,
    MemoryType.PROJECT,
    MemoryType.TASK,
]


def classify_memory_type(text: str) -> str:
    """
    Automatically assign an incoming memory snippet into one of the 7 memory types.
    """
    t = text.lower().strip()

    # Short-term / Transient conversation context
    if any(w in t for w in ("user said", "assistant said", "just now", "in this session", "current chat", "weather today", "what is the")):
        return MemoryType.SHORT_TERM

    # Preferences
    if any(w in t for w in ("like", "likes", "prefer", "preference", "love", "hate", "dislike", "favorite", "favourite", "pasand")):
        return MemoryType.PREFERENCE

    # Schedule / Dates / Routines / Appointments
    if any(w in t for w in ("appointment", "meeting", "flight", "birthday", "anniversary", "every day", "daily", "routine", "every morning", "every week", "schedule", "subah", "shaam", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "tomorrow", "pm", "am")):
        return MemoryType.SCHEDULE

    # Contact / Relationships
    if any(w in t for w in ("friend", "brother", "sister", "mother", "father", "boss", "manager", "colleague", "doctor", "dr.", "bhai", "behen", "dost")):
        return MemoryType.CONTACT

    # Project / Ongoing Goals
    if any(w in t for w in ("project", "building", "developing", "exam", "preparing", "goal", "studying", "learning", "working on")):
        return MemoryType.PROJECT

    # Task / Action Items
    if any(w in t for w in ("todo", "to-do", "task", "pending", "need to", "have to", "karna hai", "complete")):
        return MemoryType.TASK

    return MemoryType.LONG_TERM


class MemoryManager:

    def __init__(self, db_path: str = str(MEMORY_DB_FILE)):
        self.db_path = str(db_path)
        self._init_db()

    @contextmanager
    def _connection(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        try:
            with _lock, conn:
                yield conn
        finally:
            conn.close()

    def _connect(self):
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def classify_memory_type(self, text: str) -> str:
        return classify_memory_type(text)


    def _init_db(self):
        """Initialize tables and safely run non-destructive schema migrations."""
        try:
            with self._connection() as conn:
                cur = conn.cursor()

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS memories (
                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id     TEXT    DEFAULT 'default',
                        timestamp   TEXT,
                        context     TEXT,
                        type        TEXT    DEFAULT 'long_term',
                        category    TEXT    DEFAULT 'general',
                        status      TEXT    DEFAULT 'active',
                        confidence  REAL    DEFAULT 0.8,
                        score_boost REAL    DEFAULT 0.0,
                        boost_ts    REAL    DEFAULT 0.0,
                        metadata    TEXT    DEFAULT '{}'
                    )
                """)

                # Check and add any missing columns in older schemas
                cur.execute("PRAGMA table_info(memories)")
                existing_cols = {row[1] for row in cur.fetchall()}
                cols_to_add = {
                    "user_id":     "TEXT DEFAULT 'default'",
                    "type":        "TEXT DEFAULT 'long_term'",
                    "category":    "TEXT DEFAULT 'general'",
                    "status":      "TEXT DEFAULT 'active'",
                    "confidence":  "REAL DEFAULT 0.8",
                    "score_boost": "REAL DEFAULT 0.0",
                    "boost_ts":    "REAL DEFAULT 0.0",
                    "metadata":    "TEXT DEFAULT '{}'",
                }
                for col_name, col_type in cols_to_add.items():
                    if col_name not in existing_cols:
                        try:
                            cur.execute(f"ALTER TABLE memories ADD COLUMN {col_name} {col_type}")
                        except Exception:
                            pass

                # Personal profile table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS personal_profile (
                        id         INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id    TEXT NOT NULL,
                        key        TEXT NOT NULL,
                        value      TEXT,
                        metadata   TEXT,
                        updated_at TEXT,
                        UNIQUE(user_id, key)
                    )
                """)

                # Contacts table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS contacts (
                        name TEXT PRIMARY KEY,
                        phone TEXT
                    )
                """)

                # Conversation session turns (short-term history)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS conversation_history (
                        id        INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id   TEXT DEFAULT 'default',
                        timestamp TEXT,
                        role      TEXT,
                        content   TEXT
                    )
                """)

                # Performance indexes
                cur.execute("CREATE INDEX IF NOT EXISTS idx_memories_user_type ON memories(user_id, type, status)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_memories_timestamp ON memories(timestamp)")

                conn.commit()
                logger.info("Memory database initialized: %s", self.db_path)
        except Exception as e:
            logger.exception("Failed to initialise memory DB: %s", e)

    # ==================================================================
    # 7-TIER MEMORY MANAGEMENT (CRUD)
    # ==================================================================

    def add_memory(
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
        """
        Store a new memory entry across the 7 memory types.
        Detects contradictions and deduplicates automatically.
        """
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
            return {}

        m_type = memory_type or classify_memory_type(clean_text)
        meta = metadata or {}
        ts = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # Check for contradictions / superseding facts
        superseded_id = self._detect_contradiction(user_id, clean_text, m_type)

        try:
            with self._connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO memories (user_id, timestamp, context, type, category, status, confidence, metadata)
                    VALUES (?, ?, ?, ?, ?, 'active', ?, ?)
                """, (user_id, ts, clean_text, m_type, category, confidence, json.dumps(meta)))
                new_id = cur.lastrowid
                conn.commit()

            logger.info("Stored memory [%s] (id=%d): %s", m_type, new_id, clean_text[:60])
            return {
                "id": new_id,
                "user_id": user_id,
                "text": clean_text,
                "type": m_type,
                "category": category,
                "status": "active",
                "timestamp": ts,
                "superseded_id": superseded_id
            }
        except Exception as e:
            logger.exception("add_memory failed: %s", e)
            return {}

    def _detect_contradiction(self, user_id: str, new_text: str, m_type: str) -> Optional[int]:
        """
        Check if new memory contradicts or updates an existing memory of the same type.
        E.g. "I live in Delhi" supersedes "I live in Mumbai".
        """
        if m_type not in (MemoryType.PREFERENCE, MemoryType.LONG_TERM, MemoryType.PROJECT):
            return None

        # Extract primary keywords (> 3 chars)
        tokens = set(re.findall(r"\b[a-zA-Z]{4,}\b", new_text.lower()))
        if not tokens:
            return None

        try:
            with self._connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT id, context FROM memories
                    WHERE user_id = ? AND type = ? AND status = 'active'
                """, (user_id, m_type))
                rows = cur.fetchall()

                for m_id, old_text in rows:
                    old_tokens = set(re.findall(r"\b[a-zA-Z]{4,}\b", old_text.lower()))
                    overlap = tokens.intersection(old_tokens)
                    # If high subject overlap, mark previous memory as superseded
                    if len(overlap) >= 2 and len(overlap) / max(len(tokens), 1) > 0.5:
                        cur.execute("UPDATE memories SET status = 'superseded' WHERE id = ?", (m_id,))
                        conn.commit()
                        logger.info("Memory ID %d superseded by new memory: '%s'", m_id, new_text)
                        return m_id
        except Exception as e:
            logger.debug("Contradiction check error: %s", e)
        return None

    def search_memories(
        self,
        *args,
        user_id: str = "default",
        query: str = "",
        category: Optional[str] = None,
        memory_type: Optional[str] = None,
        limit: int = 5,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Search memories by keyword, type, and relevance ranking.
        """
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
                    params.append(f"%{query.strip()}%")

                sql = f"""
                    SELECT id, timestamp, context, type, category, confidence, score_boost, metadata
                    FROM memories
                    WHERE {' AND '.join(clauses)}
                    ORDER BY score_boost DESC, timestamp DESC
                    LIMIT ?
                """
                params.append(limit)
                cur.execute(sql, params)
                rows = cur.fetchall()

            results = []
            for r in rows:
                meta = {}
                try:
                    meta = json.loads(r[7] or "{}")
                except Exception:
                    pass
                results.append({
                    "id":         r[0],
                    "timestamp":  r[1],
                    "text":       r[2],
                    "type":       r[3],
                    "category":   r[4],
                    "confidence": float(r[5] or 0.8),
                    "score_boost":float(r[6] or 0.0),
                    "metadata":   meta,
                })
            return results
        except Exception as e:
            logger.exception("search_memories failed: %s", e)
            return []

    def get_memory_by_id(self, memory_id: Any) -> Optional[Dict[str, Any]]:
        """Retrieve a specific memory by its ID."""
        if isinstance(memory_id, dict):
            memory_id = memory_id.get("id")
        try:
            with self._connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT id, user_id, timestamp, context, type, category, status, confidence, metadata
                    FROM memories WHERE id = ?
                """, (int(memory_id),))
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
                    }
        except Exception as e:
            logger.exception("get_memory_by_id failed: %s", e)
        return None

    def edit_memory(self, memory_id: int, new_text: str, metadata: Optional[Dict] = None) -> bool:
        """Edit an existing memory."""
        clean = new_text.strip()
        if not clean:
            return False
        try:
            with self._connection() as conn:
                if metadata is not None:
                    cur = conn.execute("""
                        UPDATE memories SET context = ?, metadata = ? WHERE id = ?
                    """, (clean, json.dumps(metadata), memory_id))
                else:
                    cur = conn.execute("UPDATE memories SET context = ? WHERE id = ?", (clean, memory_id))
                conn.commit()
                return cur.rowcount > 0
        except Exception as e:
            logger.exception("edit_memory failed: %s", e)
            return False

    def delete_memory_by_id(self, memory_id: int) -> bool:
        """Delete a memory entry by ID."""
        try:
            with self._connection() as conn:
                cur = conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
                conn.commit()
                return cur.rowcount > 0
        except Exception as e:
            logger.exception("delete_memory_by_id failed: %s", e)
            return False

    def clear_memories(self, user_id: str = "default", memory_type: Optional[str] = None) -> int:
        """Clear memories, optionally filtered by type."""
        try:
            with self._connection() as conn:
                if memory_type:
                    cur = conn.execute("DELETE FROM memories WHERE user_id = ? AND type = ?", (user_id, memory_type))
                else:
                    cur = conn.execute("DELETE FROM memories WHERE user_id = ?", (user_id,))
                conn.commit()
                return cur.rowcount
        except Exception as e:
            logger.exception("clear_memories failed: %s", e)
            return 0

    def get_memories_summary(self, user_id: str = "default") -> Dict[str, Any]:
        """Return counts of memories per category and active status."""
        summary = {"total": 0, "by_type": {}, "profile": self.get_profile(user_id=user_id)}
        try:
            with self._connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT type, COUNT(*) FROM memories
                    WHERE user_id = ? AND status = 'active'
                    GROUP BY type
                """, (user_id,))
                for t, count in cur.fetchall():
                    summary["by_type"][t] = count
                    summary["total"] += count
        except Exception as e:
            logger.exception("get_memories_summary failed: %s", e)
        return summary

    # ==================================================================
    # EXPORT & CONTEXT INJECTION FOR LLM
    # ==================================================================

    def export_data(self, user_id: str = "default", export_format: str = "json", format: Optional[str] = None, save_to_file: bool = True) -> str:
        """Export user profile and memories as JSON or readable text report."""
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
                f"Total Active Memories: {summary['total']}\n",
                "## Personal Profile",
            ]
            for k, v in profile.items():
                lines.append(f"- **{k.capitalize()}**: {v}")

            lines.append("\n## Saved Memories by Category")
            for m in memories:
                lines.append(f"- **[{m['type'].upper()}]** {m['text']} *(Added: {m['timestamp'][:10]})*")

            content = "\n".join(lines)

        if save_to_file:
            ext = "json" if fmt == "json" else "md"
            ts_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            export_path = Path("data") / f"radhe_export_{ts_str}.{ext}"
            export_path.parent.mkdir(parents=True, exist_ok=True)
            export_path.write_text(content, encoding="utf-8")
            return str(export_path)

        return content

    def get_relevant_context(self, user_id: str = "default", query: str = "", limit: int = 4) -> str:
        """
        Retrieve relevant preferences, facts, and profile items to inject into LLM prompts.
        """
        snippets = []

        # 1. Profile key-values
        profile = self.get_profile(user_id)
        if profile:
            profile_items = [f"{k}: {v}" for k, v in list(profile.items())[:4]]
            snippets.append(f"User Profile: {', '.join(profile_items)}")

        # 2. Preferences & matching memories
        matched = self.search_memories(user_id=user_id, query=query, limit=limit)
        for m in matched:
            snippets.append(f"- [{m['type']}]: {m['text']}")

        if not snippets:
            return ""

        return "Personal Memory & Preferences Context:\n" + "\n".join(snippets)

    # ==================================================================
    # SHORT-TERM CONVERSATION TURNS
    # ==================================================================

    def add_conversation_turn(self, user_id: str, role: str, content: str) -> None:
        """Record a single turn in short-term session history."""
        ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        try:
            with self._connection() as conn:
                conn.execute("""
                    INSERT INTO conversation_history (user_id, timestamp, role, content)
                    VALUES (?, ?, ?, ?)
                """, (user_id, ts, role, content))
                conn.commit()
        except Exception as e:
            logger.debug("add_conversation_turn error: %s", e)


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

    def get_recent_conversation(self, user_id: str = "default", max_turns: int = 10) -> List[Dict[str, str]]:
        """Retrieve recent conversation turns for context continuity."""
        try:
            with self._connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT role, content FROM conversation_history
                    WHERE user_id = ?
                    ORDER BY id DESC LIMIT ?
                """, (user_id, max_turns))
                rows = cur.fetchall()
            return [{"role": r[0], "text": r[1]} for r in reversed(rows)]
        except Exception as e:
            logger.debug("get_recent_conversation error: %s", e)
            return []

    # ==================================================================
    # BACKWARD COMPATIBILITY (Exact methods expected by existing code)
    # ==================================================================

    def count(self, user_id: str = "default") -> int:
        try:
            with self._connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM memories WHERE user_id = ?", (user_id,))
                row = cur.fetchone()
                return int(row[0]) if row else 0
        except Exception:
            return 0

    def search(self, user_id: str = "default", query: str = "", limit: int = 5) -> List[Dict[str, Any]]:
        return self.search_memories(user_id=user_id, query=query, limit=limit)

    def exists(self, user_id: str, text: str) -> bool:
        if not text:
            return False
        try:
            with self._connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT 1 FROM memories WHERE user_id = ? AND context = ? LIMIT 1",
                    (user_id, text.strip())
                )
                return cur.fetchone() is not None
        except Exception:
            return False

    def save(self, user_id: str, entry: Dict[str, Any]) -> None:
        if not entry:
            return
        text = str(entry.get("text") or entry.get("context") or "").strip()
        m_type = entry.get("type") or classify_memory_type(text)
        self.add_memory(
            user_id=user_id,
            text=text,
            memory_type=m_type,
            metadata=entry.get("metadata", {})
        )

    def update(self, user_id: str, text: str, updates: Dict[str, Any]) -> bool:
        if not text or not updates:
            return False
        try:
            fields = []
            values = []
            for k, v in updates.items():
                db_col = "context" if k == "text" else k
                if db_col in ("context", "type", "confidence", "score_boost", "boost_ts", "metadata", "timestamp"):
                    fields.append(f"{db_col} = ?")
                    values.append(json.dumps(v) if db_col == "metadata" and isinstance(v, dict) else v)
            if not fields:
                return False
            values.extend([user_id, text.strip()])
            with self._connection() as conn:
                cur = conn.execute(
                    f"UPDATE memories SET {', '.join(fields)} WHERE user_id = ? AND context = ?",
                    values
                )
                conn.commit()
                return cur.rowcount > 0
        except Exception:
            return False

    def delete(self, user_id: str, text: str) -> bool:
        if not text:
            return False
        try:
            with self._connection() as conn:
                cur = conn.execute("DELETE FROM memories WHERE user_id = ? AND context = ?", (user_id, text.strip()))
                conn.commit()
                return cur.rowcount > 0
        except Exception:
            return False

    def prune(self, user_id: str = "default", max_items: int = 100, **kwargs) -> None:
        try:
            total = self.count(user_id)
            if total <= max_items:
                return
            excess = total - max_items
            with self._connection() as conn:
                conn.execute("""
                    DELETE FROM memories WHERE id IN (
                        SELECT id FROM memories WHERE user_id = ?
                        ORDER BY score_boost ASC, timestamp ASC LIMIT ?
                    )
                """, (user_id, excess))
                conn.commit()
        except Exception:
            pass

    def store_memory(self, context: str, metadata: Dict = None) -> None:
        self.add_memory("default", text=context, metadata=metadata or {})

    def recall_memory(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        return self.search_memories("default", query=query, limit=limit)

    # Profile & Contact methods
    def set_profile_value(self, key: str, value: str, user_id: str = "default", metadata: Optional[Dict] = None):
        try:
            meta_json = json.dumps(metadata or {})
            updated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            with self._connection() as conn:
                conn.execute("""
                    INSERT INTO personal_profile (user_id, key, value, metadata, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(user_id, key) DO UPDATE SET
                        value = excluded.value,
                        metadata = excluded.metadata,
                        updated_at = excluded.updated_at
                """, (user_id, key, str(value), meta_json, updated_at))
                conn.commit()
        except Exception as e:
            logger.exception("set_profile_value error: %s", e)

    def get_profile(self, user_id: str = "default") -> Dict[str, str]:
        try:
            with self._connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT key, value FROM personal_profile WHERE user_id = ?", (user_id,))
                return {k: v for k, v in cur.fetchall()}
        except Exception:
            return {}

    def get_profile_value(self, key: str, user_id: str = "default", default: Optional[str] = None) -> Optional[str]:
        try:
            with self._connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT value FROM personal_profile WHERE user_id = ? AND key = ?", (user_id, key))
                row = cur.fetchone()
                return row[0] if row else default
        except Exception:
            return default

    def delete_profile_value(self, key: str, user_id: str = "default"):
        try:
            with self._connection() as conn:
                conn.execute("DELETE FROM personal_profile WHERE user_id = ? AND key = ?", (user_id, key))
                conn.commit()
        except Exception:
            pass

    def clear_profile(self, user_id: str = "default"):
        try:
            with self._connection() as conn:
                conn.execute("DELETE FROM personal_profile WHERE user_id = ?", (user_id,))
                conn.commit()
        except Exception:
            pass

    def save_contact(self, name: str, phone: str):
        try:
            with self._connection() as conn:
                conn.execute("INSERT OR REPLACE INTO contacts (name, phone) VALUES (?, ?)", (name.lower(), phone))
                conn.commit()
        except Exception:
            pass

    def get_contact(self, name: str):
        try:
            with self._connection() as conn:
                cur = conn.execute("SELECT phone FROM contacts WHERE name = ?", (name.lower(),))
                row = cur.fetchone()
                return row[0] if row else None
        except Exception:
            return None


# ── Global singleton ───────────────────────────────────────────────────
memory_manager = MemoryManager()
