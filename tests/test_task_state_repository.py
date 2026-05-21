import sqlite3

import pytest

from scripts.check_task_state_scope import unsafe_task_state_queries
from src.storage.task_state import TaskStateRepository, TaskStateScopeError


def make_repository():
    return TaskStateRepository(sqlite3.connect(":memory:"))


def test_task_id_collisions_are_scoped_by_workspace():
    repository = make_repository()

    repository.upsert(
        "workspace-a",
        "task-1",
        "running",
        retries=1,
        payload={"owner": "a"},
    )
    repository.upsert(
        "workspace-b",
        "task-1",
        "queued",
        retries=0,
        payload={"owner": "b"},
    )

    assert repository.get("workspace-a", "task-1")["state"] == "running"
    assert repository.get("workspace-a", "task-1")["payload"] == {"owner": "a"}
    assert repository.get("workspace-b", "task-1")["state"] == "queued"
    assert repository.get("workspace-b", "task-1")["payload"] == {"owner": "b"}


def test_updates_require_workspace_scope_and_do_not_cross_boundaries():
    repository = make_repository()
    repository.upsert("workspace-a", "task-1", "running")
    repository.upsert("workspace-b", "task-1", "running")

    assert repository.update_state(
        "workspace-a",
        "task-1",
        "failed",
        retries=2,
    )

    assert repository.get("workspace-a", "task-1")["state"] == "failed"
    assert repository.get("workspace-a", "task-1")["retries"] == 2
    assert repository.get("workspace-b", "task-1")["state"] == "running"


def test_deletes_require_workspace_scope_and_leave_other_workspace_rows():
    repository = make_repository()
    repository.upsert("workspace-a", "task-1", "running")
    repository.upsert("workspace-b", "task-1", "running")

    assert repository.delete("workspace-a", "task-1")

    assert repository.get("workspace-a", "task-1") is None
    assert repository.get("workspace-b", "task-1") is not None


def test_empty_workspace_or_task_id_is_rejected():
    repository = make_repository()

    with pytest.raises(TaskStateScopeError, match="workspace_id is required"):
        repository.get("", "task-1")

    with pytest.raises(TaskStateScopeError, match="task_id is required"):
        repository.get("workspace-a", "")


def test_internal_guard_blocks_unscoped_task_state_predicates():
    repository = make_repository()

    with pytest.raises(TaskStateScopeError):
        repository._assert_scoped_sql("SELECT * FROM task_state")

    with pytest.raises(TaskStateScopeError):
        repository._assert_scoped_sql(
            "SELECT workspace_id, task_id "
            "FROM task_state "
            "WHERE task_id = ?"
        )

    with pytest.raises(TaskStateScopeError):
        repository._assert_scoped_sql(
            "UPDATE task_state "
            "SET state = ? "
            "WHERE task_id = ?"
        )

    with pytest.raises(TaskStateScopeError):
        repository._assert_scoped_sql(
            "INSERT INTO task_state (task_id, state) "
            "VALUES (?, ?)"
        )


def test_internal_guard_allows_workspace_predicates_and_scoped_inserts():
    repository = make_repository()

    repository._assert_scoped_sql(
        "SELECT workspace_id, task_id "
        "FROM task_state "
        "WHERE workspace_id = ? AND task_id = ?"
    )
    repository._assert_scoped_sql(
        "INSERT INTO task_state (workspace_id, task_id, state) "
        "VALUES (?, ?, ?)"
    )


def test_static_checker_requires_workspace_predicate(tmp_path):
    unsafe = tmp_path / "unsafe_queries.py"
    unsafe.write_text(
        '''
BAD_SELECT = """
SELECT workspace_id, task_id
FROM task_state
WHERE task_id = ?
"""

BAD_INSERT = """
INSERT INTO task_state (task_id, state)
VALUES (?, ?)
"""
''',
        encoding="utf-8",
    )
    safe = tmp_path / "safe_queries.py"
    safe.write_text(
        '''
GOOD_SELECT = """
SELECT workspace_id, task_id
FROM task_state
WHERE workspace_id = ? AND task_id = ?
"""

GOOD_INSERT = """
INSERT INTO task_state (workspace_id, task_id, state)
VALUES (?, ?, ?)
"""
''',
        encoding="utf-8",
    )

    failures = list(unsafe_task_state_queries(tmp_path))

    assert [path.name for path, _ in failures] == [
        "unsafe_queries.py",
        "unsafe_queries.py",
    ]
