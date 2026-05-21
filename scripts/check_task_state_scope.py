"""Fail CI when task_state SQL omits workspace predicates."""

import re
import sys
from pathlib import Path


TASK_STATE_QUERY = re.compile(
    r"(select\s+.+?\s+from|update|delete\s+from)\s+task_state\b",
    re.IGNORECASE | re.DOTALL,
)
SQL_LITERAL = re.compile(r'("""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\')')


def unsafe_task_state_queries(root: Path):
    for path in root.rglob("*.py"):
        if ".venv" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for literal in SQL_LITERAL.finditer(text):
            sql = literal.group(0).strip("\"'")
            normalized = " ".join(sql.lower().split())
            if not TASK_STATE_QUERY.search(normalized):
                continue
            if "workspace_id" not in normalized:
                yield path, literal.start()


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
