"""Workspace-scoped task state persistence.

All public repository methods require both ``workspace_id`` and ``task_id``.
This keeps callers from depending on task ids being globally unique and makes
the workspace predicate part of the data-layer contract.
"""

import json
import sqlite3
import time
from typing import Any, Dict, Iterable, Optional


class TaskStateScopeError(ValueError):
    """Raised when task state access is attempted without workspace scope."""


class TaskStateRepository:
    """Persist task state behind mandatory workspace predicates."""

    def __init__(self, connection: sqlite3.Connection):
        self._connection = connection
        self._connection.row_factory = sqlite3.Row
        self._ensure_schema()

    def upsert(
        self,
        workspace_id: str,
        task_id: str,
        state: str,
        retries: int = 0,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        workspace_id = self._require_scope("workspace_id", workspace_id)
        task_id = self._require_scope("task_id", task_id)
        now = time.time()
        payload_json = json.dumps(payload or {}, sort_keys=True)

        self._execute_scoped(
            """
            INSERT INTO task_state (
                workspace_id,
                task_id,
                state,
                retries,
                payload,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(workspace_id, task_id) DO UPDATE SET
                state = excluded.state,
                retries = excluded.retries,
                payload = excluded.payload,
                updated_at = excluded.updated_at
            """,
            (
                workspace_id,
                task_id,
                state,
                int(retries),
                payload_json,
                now,
                now,
            ),
        )
        self._connection.commit()
        return self.get(workspace_id, task_id)

    def get(self, workspace_id: str, task_id: str) -> Optional[Dict[str, Any]]:
        workspace_id = self._require_scope("workspace_id", workspace_id)
        task_id = self._require_scope("task_id", task_id)
        cursor = self._execute_scoped(
            """
            SELECT workspace_id, task_id, state, retries, payload,
                   created_at, updated_at
            FROM task_state
            WHERE workspace_id = ? AND task_id = ?
            """,
            (workspace_id, task_id),
        )
        row = cursor.fetchone()
        return self._deserialize(row) if row else None

    def update_state(
        self,
        workspace_id: str,
        task_id: str,
        state: str,
        retries: Optional[int] = None,
    ) -> bool:
        workspace_id = self._require_scope("workspace_id", workspace_id)
        task_id = self._require_scope("task_id", task_id)
        if retries is None:
            cursor = self._execute_scoped(
                """
                UPDATE task_state
                SET state = ?, updated_at = ?
                WHERE workspace_id = ? AND task_id = ?
                """,
                (state, time.time(), workspace_id, task_id),
            )
        else:
            cursor = self._execute_scoped(
                """
                UPDATE task_state
                SET state = ?, retries = ?, updated_at = ?
                WHERE workspace_id = ? AND task_id = ?
                """,
                (state, int(retries), time.time(), workspace_id, task_id),
            )
        self._connection.commit()
        return cursor.rowcount > 0

    def delete(self, workspace_id: str, task_id: str) -> bool:
        workspace_id = self._require_scope("workspace_id", workspace_id)
        task_id = self._require_scope("task_id", task_id)
        cursor = self._execute_scoped(
            """
            DELETE FROM task_state
            WHERE workspace_id = ? AND task_id = ?
            """,
            (workspace_id, task_id),
        )
        self._connection.commit()
        return cursor.rowcount > 0

    def list_for_workspace(
        self,
        workspace_id: str,
    ) -> Iterable[Dict[str, Any]]:
        workspace_id = self._require_scope("workspace_id", workspace_id)
        cursor = self._execute_scoped(
            """
            SELECT workspace_id, task_id, state, retries, payload,
                   created_at, updated_at
            FROM task_state
            WHERE workspace_id = ?
            ORDER BY updated_at DESC
            """,
            (workspace_id,),
        )
        return [self._deserialize(row) for row in cursor.fetchall()]

    def _ensure_schema(self) -> None:
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS task_state (
                workspace_id TEXT NOT NULL,
                task_id TEXT NOT NULL,
                state TEXT NOT NULL,
                retries INTEGER NOT NULL DEFAULT 0,
                payload TEXT NOT NULL DEFAULT '{}',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                PRIMARY KEY (workspace_id, task_id)
            )
            """
        )
        self._connection.commit()

    def _execute_scoped(self, sql: str, params: tuple) -> sqlite3.Cursor:
        self._assert_scoped_sql(sql)
        return self._connection.execute(sql, params)

    def _assert_scoped_sql(self, sql: str) -> None:
        normalized = " ".join(sql.lower().split())
        if "task_state" not in normalized:
            return
        if "insert into task_state" in normalized:
            insert_columns = normalized.split("values", 1)[0]
            if "workspace_id" in insert_columns:
                return
            raise TaskStateScopeError(
                "task_state inserts must include workspace_id scope"
            )
        mutates_or_reads_task_state = any(
            marker in normalized
            for marker in (
                "from task_state",
                "update task_state",
                "delete from task_state",
            )
        )
        if not mutates_or_reads_task_state:
            return
        if " where " not in normalized:
            raise TaskStateScopeError(
                "task_state queries must include workspace_id predicate"
            )
        predicate = normalized.rsplit(" where ", 1)[1]
        if "workspace_id" not in predicate:
            raise TaskStateScopeError(
                "task_state queries must include workspace_id predicate"
            )

    def _require_scope(self, field: str, value: str) -> str:
        if value is None or str(value).strip() == "":
            raise TaskStateScopeError(
                f"{field} is required for task state access"
            )
        return str(value)

    def _deserialize(self, row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "workspace_id": row["workspace_id"],
            "task_id": row["task_id"],
            "state": row["state"],
            "retries": row["retries"],
            "payload": json.loads(row["payload"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
