import inspect

import pytest

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
    ]
    for method in repository_methods:
        signature = inspect.signature(method)
        assert "workspace_id" in signature.parameters


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
