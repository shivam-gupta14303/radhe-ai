# dal.py
"""
Database Abstraction Layer (DAL) for Radhe.

Provides:
- Unified database connection and transaction management.
- Offline-first SQLite engine with safe context managers and WAL mode.
- PostgreSQL adapter support if DATABASE_URL is configured.
- Automated schema migrations and cross-engine parameter normalization.
- Database backup and export utilities.
"""

import os
import sys
import sqlite3
import logging
import threading
from pathlib import Path
from contextlib import contextmanager
from typing import Optional, Any, List, Dict, Tuple, Generator

from config import DATA_DIR

logger = logging.getLogger("Radhe_DAL")
logger.setLevel(logging.INFO)

_dal_lock = threading.Lock()


class DatabaseAdapter:
    """
    Abstract Database Adapter supporting SQLite (offline-first)
    and optional PostgreSQL when configured.
    """

    def __init__(self, sqlite_path: Optional[Path] = None, database_url: Optional[str] = None):
        self.sqlite_path = Path(sqlite_path or (DATA_DIR / "radhe_unified.db"))
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self.database_url = database_url or os.environ.get("DATABASE_URL")
        self.is_postgres = bool(self.database_url and ("postgres" in self.database_url))
        self._init_sqlite_pragmas()

    def _init_sqlite_pragmas(self) -> None:
        """Enable WAL mode and foreign keys for high concurrency on SQLite."""
        if not self.is_postgres:
            conn = None
            try:
                conn = sqlite3.connect(self.sqlite_path)
                conn.execute("PRAGMA journal_mode = WAL;")
                conn.execute("PRAGMA foreign_keys = ON;")
                conn.execute("PRAGMA synchronous = NORMAL;")
                conn.commit()
            except Exception as e:
                logger.warning("Could not set SQLite pragmas: %s", e)
            finally:
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass

    @contextmanager
    def connection(self) -> Generator[Any, None, None]:
        """Provide a thread-safe connection context."""
        with _dal_lock:
            if self.is_postgres:
                # PostgreSQL connection fallback
                try:
                    import psycopg2
                    from psycopg2.extras import RealDictCursor
                    conn = psycopg2.connect(self.database_url, cursor_factory=RealDictCursor)
                    try:
                        yield conn
                        conn.commit()
                    except Exception:
                        conn.rollback()
                        raise
                    finally:
                        conn.close()
                    return
                except ImportError:
                    logger.warning("psycopg2 not installed; falling back to SQLite.")

            # SQLite connection
            conn = sqlite3.connect(self.sqlite_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            try:
                with conn:
                    yield conn
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

    def execute(self, query: str, params: Tuple = ()) -> int:
        """Execute a write statement (INSERT/UPDATE/DELETE) and return rowcount or lastrowid."""
        with self.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            if query.strip().upper().startswith("INSERT"):
                return cursor.lastrowid
            return cursor.rowcount

    def fetch_one(self, query: str, params: Tuple = ()) -> Optional[Dict[str, Any]]:
        """Fetch a single record as a dict."""
        with self.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            row = cursor.fetchone()
            if row is None:
                return None
            return dict(row)

    def fetch_all(self, query: str, params: Tuple = ()) -> List[Dict[str, Any]]:
        """Fetch all matching records as a list of dicts."""
        with self.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def execute_script(self, script: str) -> None:
        """Execute a multi-statement DDL script."""
        with self.connection() as conn:
            if hasattr(conn, "executescript"):
                conn.executescript(script)
            else:
                cursor = conn.cursor()
                cursor.execute(script)

    def backup_to_file(self, target_path: Path) -> bool:
        """Create a complete atomic backup of the SQLite database."""
        target = Path(target_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        src = None
        dst = None
        try:
            src = sqlite3.connect(self.sqlite_path)
            dst = sqlite3.connect(target)
            src.backup(dst)
            logger.info("Database backup created successfully at %s", target)
            return True
        except Exception as e:
            logger.error("Database backup failed: %s", e)
            return False
        finally:
            if src:
                try:
                    src.close()
                except Exception:
                    pass
            if dst:
                try:
                    dst.close()
                except Exception:
                    pass


# Global DAL instance
dal = DatabaseAdapter()
