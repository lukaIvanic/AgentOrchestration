"""Fail CI when task_state SQL omits workspace predicates."""

import re
import sys
from pathlib import Path


TASK_STATE_QUERY = re.compile(
    r"(select\s+.+?\s+from|update|delete\s+from|insert\s+into)"
    r"\s+task_state\b",
    re.IGNORECASE | re.DOTALL,
)
SQL_LITERAL = re.compile(r'("""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\')')


def unsafe_task_state_queries(root: Path):
    for pattern in ("*.py", "*.sql"):
        yield from _unsafe_task_state_queries_for_pattern(root, pattern)


def _unsafe_task_state_queries_for_pattern(root: Path, pattern: str):
    for path in root.rglob(pattern):
        if ".venv" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".sql":
            queries = [(text, 0)]
        else:
            queries = [
                (literal.group(0).strip("\"'"), literal.start())
                for literal in SQL_LITERAL.finditer(text)
            ]
        for sql, offset in queries:
            if is_unscoped_task_state_sql(sql):
                yield path, offset


def is_unscoped_task_state_sql(sql: str) -> bool:
    normalized = " ".join(sql.lower().split())
    if not TASK_STATE_QUERY.search(normalized):
        return False
    if "insert into task_state" in normalized:
        insert_columns = normalized.split("values", 1)[0]
        return "workspace_id" not in insert_columns
    if " where " not in normalized:
        return True
    predicate = normalized.rsplit(" where ", 1)[1]
    return "workspace_id" not in predicate


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    failures = list(unsafe_task_state_queries(root))
    for path, offset in failures:
        line = path.read_text(encoding="utf-8")[:offset].count("\n") + 1
        print(
            f"{path}:{line}: "
            "task_state query missing workspace_id predicate"
        )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
