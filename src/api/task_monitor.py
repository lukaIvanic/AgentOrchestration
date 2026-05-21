"""Protected task monitor state."""

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class TaskState:
    task_id: str
    workspace_id: str
    status: str
    events: list = field(default_factory=list)
    protected_reads: int = 0


class TaskMonitor:
    def __init__(self):
        self._tasks: Dict[str, TaskState] = {}

    def upsert(self, task_id: str, *, workspace_id: str, status: str) -> None:
        self._tasks[task_id] = TaskState(
            task_id=task_id,
            workspace_id=workspace_id,
            status=status,
        )

    def exists(self, task_id: str) -> bool:
        return task_id in self._tasks

    def workspace_for(self, task_id: str) -> str:
        return self._tasks[task_id].workspace_id

    def read(self, task_id: str) -> Dict:
        task = self._tasks[task_id]
        task.protected_reads += 1
        return {
            "task_id": task.task_id,
            "workspace_id": task.workspace_id,
            "status": task.status,
            "events": list(task.events),
            "protected_reads": task.protected_reads,
        }

    def protected_reads(self, task_id: str) -> int:
        return self._tasks[task_id].protected_reads
