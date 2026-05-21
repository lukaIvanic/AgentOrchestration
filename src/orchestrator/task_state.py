"""Workspace-scoped task state storage."""

import copy
from dataclasses import dataclass, field
import time
from typing import Any, Dict, List, Optional, Tuple


class TaskStateScopeError(ValueError):
    """Raised when task state is accessed without a workspace scope."""


class UnscopedTaskStateAccessError(TaskStateScopeError):
    """Raised when legacy task-id-only helpers are called."""

    def __init__(self, method: str):
        super().__init__(
            f"{method} is not allowed; task state access requires workspace_id"
        )


def require_workspace_id(workspace_id: Optional[str]) -> str:
    if not isinstance(workspace_id, str) or not workspace_id.strip():
        raise TaskStateScopeError(
            "workspace_id is required for task state access"
        )
    return workspace_id.strip()


@dataclass
class TaskState:
    workspace_id: str
    task_id: str
    status: str
    task: Dict[str, Any] = field(default_factory=dict)
    queue: str = "default"
    priority: int = 0
    retries: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def clone(self) -> "TaskState":
        return TaskState(
            workspace_id=self.workspace_id,
            task_id=self.task_id,
            status=self.status,
            task=copy.deepcopy(self.task),
            queue=self.queue,
            priority=self.priority,
            retries=self.retries,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

    def snapshot(self) -> Dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "task_id": self.task_id,
            "status": self.status,
            "task": copy.deepcopy(self.task),
            "queue": self.queue,
            "priority": self.priority,
            "retries": self.retries,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class ScopedTaskStateRepository:
    """In-memory task state repository keyed by workspace and task id.

    The same task id can exist in multiple workspaces without reads, writes, or
    deletes crossing tenant boundaries.
    """

    def __init__(self):
        self._records: Dict[Tuple[str, str], TaskState] = {}

    def save(
        self,
        workspace_id: str,
        task_id: str,
        task: Dict[str, Any],
        *,
        status: str,
        queue: str = "default",
        priority: int = 0,
        retries: int = 0,
    ) -> TaskState:
        workspace_id = require_workspace_id(workspace_id)
        now = time.time()
        key = (workspace_id, task_id)
        existing = self._records.get(key)
        created_at = existing.created_at if existing else now
        state = TaskState(
            workspace_id=workspace_id,
            task_id=task_id,
            status=status,
            task=copy.deepcopy(task),
            queue=queue,
            priority=priority,
            retries=retries,
            created_at=created_at,
            updated_at=now,
        )
        self._records[key] = state
        return state

    def get(self, workspace_id: str, task_id: str) -> Optional[TaskState]:
        workspace_id = require_workspace_id(workspace_id)
        state = self._records.get((workspace_id, task_id))
        return state.clone() if state else None

    def update(
        self,
        workspace_id: str,
        task_id: str,
        *,
        status: Optional[str] = None,
        task: Optional[Dict[str, Any]] = None,
        queue: Optional[str] = None,
        priority: Optional[int] = None,
        retries: Optional[int] = None,
    ) -> bool:
        workspace_id = require_workspace_id(workspace_id)
        state = self._records.get((workspace_id, task_id))
        if not state:
            return False
        if status is not None:
            state.status = status
        if task is not None:
            state.task = copy.deepcopy(task)
        if queue is not None:
            state.queue = queue
        if priority is not None:
            state.priority = priority
        if retries is not None:
            state.retries = retries
        state.updated_at = time.time()
        return True

    def delete(self, workspace_id: str, task_id: str) -> bool:
        workspace_id = require_workspace_id(workspace_id)
        return self._records.pop((workspace_id, task_id), None) is not None

    def list(
        self,
        workspace_id: str,
        *,
        status: Optional[str] = None,
    ) -> List[TaskState]:
        workspace_id = require_workspace_id(workspace_id)
        states = [
            state for (scope, _), state in self._records.items()
            if scope == workspace_id
        ]
        if status is not None:
            states = [state for state in states if state.status == status]
        return [state.clone() for state in states]

    def exists(self, workspace_id: str, task_id: str) -> bool:
        workspace_id = require_workspace_id(workspace_id)
        return (workspace_id, task_id) in self._records

    def count_for_workspace(self, workspace_id: str) -> int:
        workspace_id = require_workspace_id(workspace_id)
        return sum(1 for scope, _ in self._records if scope == workspace_id)

    def get_by_task_id(self, task_id: str) -> Optional[TaskState]:
        raise UnscopedTaskStateAccessError("get_by_task_id")

    def update_by_task_id(self, task_id: str, **changes: Any) -> bool:
        raise UnscopedTaskStateAccessError("update_by_task_id")

    def delete_by_task_id(self, task_id: str) -> bool:
        raise UnscopedTaskStateAccessError("delete_by_task_id")


def postgres_workspace_rls_policy_sql(
    table_name: str = "task_state",
    workspace_column: str = "workspace_id",
    setting_name: str = "app.current_workspace_id",
) -> str:
    """Return PostgreSQL RLS SQL for the active workspace setting."""
    for value, label in (
        (table_name, "table_name"),
        (workspace_column, "workspace_column"),
        (setting_name, "setting_name"),
    ):
        if not value.replace("_", "").replace(".", "").isalnum():
            raise ValueError(f"{label} contains unsupported characters")

    return "\n".join(
        [
            f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY;",
            f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY;",
            (
                "DROP POLICY IF EXISTS task_state_workspace_scope ON "
                f"{table_name};"
            ),
            (
                f"CREATE POLICY task_state_workspace_scope ON {table_name} "
                f"USING ({workspace_column} = "
                f"current_setting('{setting_name}', true)) "
                f"WITH CHECK ({workspace_column} = "
                f"current_setting('{setting_name}', true));"
            ),
        ]
    )
