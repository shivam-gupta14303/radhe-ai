from pathlib import Path

p = Path("src/reminder_manager.py")
content = p.read_text(encoding="utf-8")

old_code = """        try:
            with self._connection() as conn:
                cur = conn.cursor()
                clauses = ["status = ?"]
                params: List[Any] = [status]

                if category and category.lower() != "all":
                    clauses.append("category = ?")
                    params.append(category)

                sql = f\"\"\"
                    SELECT id, title, description, priority, due_date, status, category, created_at, completed_at
                    FROM tasks
                    WHERE {' AND '.join(clauses)}"""

new_code = """        try:
            with self._connection() as conn:
                cur = conn.cursor()
                clauses = []
                params: List[Any] = []

                if status and str(status).lower() != "all":
                    clauses.append("status = ?")
                    params.append(str(status).lower())

                if category and category.lower() != "all":
                    clauses.append("category = ?")
                    params.append(category)

                where_stmt = f"WHERE {' AND '.join(clauses)}" if clauses else ""
                sql = f\"\"\"
                    SELECT id, title, description, priority, due_date, status, category, created_at, completed_at
                    FROM tasks
                    {where_stmt}"""

if old_code in content:
    content = content.replace(old_code, new_code, 1)
    p.write_text(content, encoding="utf-8")
    print("SUCCESS: Updated list_tasks to handle 'all' status")
else:
    print("ERROR: old_code not found")
