import inspect

import pytest

from scripts.check_task_state_scope import unsafe_task_state_queries
from src.orchestrator.task_state import (
    ScopedTaskStateRepository,
    TaskStateScopeError,
    UnscopedTaskStateAccessError,
    postgres_workspace_rls_policy_sql,
)


def test_task_id_collisions_are_isolated_by_workspace():
    repository = ScopedTaskStateRepository()

    repository.save(
        "workspace-a",
        "task-123",
        {"id": "task-123", "payload": "alpha"},
        status="queued",
    )
    repository.save(
        "workspace-b",
        "task-123",
        {"id": "task-123", "payload": "beta"},
        status="queued",
    )

    assert repository.get("workspace-a", "task-123").task["payload"] == "alpha"
    assert repository.get("workspace-b", "task-123").task["payload"] == "beta"

    assert repository.update(
        "workspace-a",
        "task-123",
        status="completed",
    )
    assert repository.get("workspace-a", "task-123").status == "completed"
    assert repository.get("workspace-b", "task-123").status == "queued"


def test_repository_reads_return_defensive_copies():
    repository = ScopedTaskStateRepository()
    original = {"id": "task-1", "payload": {"secret": "original"}}

    repository.save("workspace-a", "task-1", original, status="queued")
    original["payload"]["secret"] = "mutated after save"

    first_read = repository.get("workspace-a", "task-1")
    first_read.status = "completed"
    first_read.task["payload"]["secret"] = "mutated after read"

    second_read = repository.get("workspace-a", "task-1")

    assert second_read.status == "queued"
    assert second_read.task["payload"]["secret"] == "original"


def test_repository_list_returns_defensive_copies():
    repository = ScopedTaskStateRepository()
    repository.save(
        "workspace-a",
        "task-1",
        {"id": "task-1", "payload": {"value": 1}},
        status="queued",
    )

    listed = repository.list("workspace-a")
    listed[0].status = "completed"
    listed[0].task["payload"]["value"] = 99

    stored = repository.get("workspace-a", "task-1")

    assert stored.status == "queued"
    assert stored.task["payload"]["value"] == 1


def test_workspace_scope_is_required_for_all_repository_access():
    repository = ScopedTaskStateRepository()

    with pytest.raises(TaskStateScopeError):
        repository.save("", "task-1", {"id": "task-1"}, status="queued")
    with pytest.raises(TaskStateScopeError):
        repository.get(None, "task-1")
    with pytest.raises(TaskStateScopeError):
        repository.update(" ", "task-1", status="completed")
    with pytest.raises(TaskStateScopeError):
        repository.delete("", "task-1")
    with pytest.raises(TaskStateScopeError):
        repository.list("")


def test_unscoped_task_id_helpers_are_blocked():
    repository = ScopedTaskStateRepository()

    with pytest.raises(UnscopedTaskStateAccessError):
        repository.get_by_task_id("task-1")
    with pytest.raises(UnscopedTaskStateAccessError):
        repository.update_by_task_id("task-1", status="completed")
    with pytest.raises(UnscopedTaskStateAccessError):
        repository.delete_by_task_id("task-1")


def test_task_state_contract_requires_workspace_id_parameter():
    repository_methods = [
        ScopedTaskStateRepository.save,
        ScopedTaskStateRepository.get,
        ScopedTaskStateRepository.update,
        ScopedTaskStateRepository.delete,
        ScopedTaskStateRepository.list,
        ScopedTaskStateRepository.exists,
        ScopedTaskStateRepository.count_for_workspace,
    ]
    for method in repository_methods:
        signature = inspect.signature(method)
        assert "workspace_id" in signature.parameters


def test_scoped_exists_and_count_do_not_cross_workspaces():
    repository = ScopedTaskStateRepository()
    repository.save(
        "workspace-a",
        "shared-task",
        {"id": "shared-task"},
        status="queued",
    )
    repository.save(
        "workspace-b",
        "shared-task",
        {"id": "shared-task"},
        status="queued",
    )
    repository.save(
        "workspace-b",
        "other-task",
        {"id": "other-task"},
        status="queued",
    )

    assert repository.exists("workspace-a", "shared-task")
    assert repository.exists("workspace-b", "shared-task")
    assert not repository.exists("workspace-a", "other-task")
    assert repository.count_for_workspace("workspace-a") == 1
    assert repository.count_for_workspace("workspace-b") == 2

    with pytest.raises(TaskStateScopeError):
        repository.exists("", "shared-task")
    with pytest.raises(TaskStateScopeError):
        repository.count_for_workspace("")


def test_postgres_rls_policy_scopes_reads_and_writes():
    sql = postgres_workspace_rls_policy_sql()

    assert "ENABLE ROW LEVEL SECURITY" in sql
    assert "FORCE ROW LEVEL SECURITY" in sql
    using_clause = (
        "USING (workspace_id = "
        "current_setting('app.current_workspace_id', true))"
    )
    check_clause = (
        "WITH CHECK (workspace_id = "
        "current_setting('app.current_workspace_id', true))"
    )
    assert using_clause in sql
    assert check_clause in sql


def test_static_checker_requires_workspace_predicate(tmp_path):
    unsafe = tmp_path / "unsafe_queries.py"
    unsafe.write_text(
        '''
BAD_SELECT = """
SELECT workspace_id, task_id
FROM task_state
WHERE task_id = ?
"""

BAD_UPDATE = """
UPDATE task_state
SET status = ?
WHERE task_id = ?
"""

BAD_INSERT = """
INSERT INTO task_state (task_id, status)
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

GOOD_UPDATE = """
UPDATE task_state
SET status = ?
WHERE workspace_id = ? AND task_id = ?
"""

GOOD_INSERT = """
INSERT INTO task_state (workspace_id, task_id, status)
VALUES (?, ?, ?)
"""
''',
        encoding="utf-8",
    )

    failures = list(unsafe_task_state_queries(tmp_path))

    assert [path.name for path, _ in failures] == [
        "unsafe_queries.py",
        "unsafe_queries.py",
        "unsafe_queries.py",
    ]


def test_static_checker_scans_sql_files(tmp_path):
    unsafe = tmp_path / "unsafe_task_state.sql"
    unsafe.write_text(
        "SELECT task_id, status\n"
        "FROM task_" "state\n"
        "WHERE task_id = ?;\n",
        encoding="utf-8",
    )
    safe = tmp_path / "safe_task_state.sql"
    safe.write_text(
        "SELECT task_id, status\n"
        "FROM task_" "state\n"
        "WHERE workspace_id = ? AND task_id = ?;\n",
        encoding="utf-8",
    )

    failures = list(unsafe_task_state_queries(tmp_path))

    assert [(path.name, offset) for path, offset in failures] == [
        ("unsafe_task_state.sql", 0)
    ]
