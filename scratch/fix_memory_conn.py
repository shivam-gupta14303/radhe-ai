from pathlib import Path

p = Path("src/memory.py")
content = p.read_text(encoding="utf-8")

if "from contextlib import contextmanager" not in content:
    content = "from contextlib import contextmanager\n" + content

conn_method = """    @contextmanager
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
"""

old_conn = """    def _connect(self):
        return sqlite3.connect(self.db_path, check_same_thread=False)"""

if old_conn in content:
    content = content.replace(old_conn, conn_method, 1)

content = content.replace("with _lock, self._connect() as conn:", "with self._connection() as conn:")

p.write_text(content, encoding="utf-8")
print("Updated memory.py with safe connection contextmanager and classify_memory_type method.")
