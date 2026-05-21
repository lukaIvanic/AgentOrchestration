import sqlite3

import pytest

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
            "SELECT * FROM task_state WHERE task_id = ?"
        )
