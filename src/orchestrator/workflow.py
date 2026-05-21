"""Workflow Manager — Defines and executes multi-step agent workflows."""

from enum import Enum
import time
from threading import RLock
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4


class StepStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class WorkflowStep:
    def __init__(
        self,
        name: str,
        handler: Callable,
        retries: int = 0,
        timeout: int = 300,
    ):
        self.id = str(uuid4())
        self.name = name
        self.handler = handler
        self.retries = retries
        self.timeout = timeout
        self.status = StepStatus.PENDING
        self.result: Any = None
        self.error: Optional[str] = None


class Workflow:
    def __init__(
        self,
        name: str,
        description: str = "",
        parent_id: Optional[str] = None,
    ):
        self.id = str(uuid4())
        self.name = name
        self.description = description
        self.parent_id = parent_id
        self.attempt = 0
        self.revision = 0
        self.steps: List[WorkflowStep] = []
        self._step_map: Dict[str, WorkflowStep] = {}
        self.status = StepStatus.PENDING

    def add_step(self, step: WorkflowStep) -> "Workflow":
        self.steps.append(step)
        self._step_map[step.id] = step
        return self

    def get_step(self, step_id: str) -> Optional[WorkflowStep]:
        return self._step_map.get(step_id)


class WorkflowManager:
    def __init__(self):
        self._lock = RLock()
        self._workflows: Dict[str, Workflow] = {}
        self._audit_events: List[Dict[str, Any]] = []

    def create_workflow(self, name: str, description: str = "") -> Workflow:
        with self._lock:
            workflow = Workflow(name, description)
            self._workflows[workflow.id] = workflow
            self._audit("workflow_created", workflow.id)
            return workflow

    def get_workflow(self, workflow_id: str) -> Optional[Workflow]:
        with self._lock:
            return self._workflows.get(workflow_id)

    def list_workflows(self) -> List[Workflow]:
        with self._lock:
            return list(self._workflows.values())

    def delete_workflow(self, workflow_id: str) -> bool:
        with self._lock:
            deleted = self._workflows.pop(workflow_id, None) is not None
            if deleted:
                self._audit("workflow_deleted", workflow_id)
            return deleted

    def start_workflow(self, workflow_id: str) -> bool:
        with self._lock:
            workflow = self._workflows.get(workflow_id)
            if not workflow or workflow.status == StepStatus.FAILED:
                return False
            workflow.attempt += 1
            workflow.revision += 1
            workflow.status = StepStatus.RUNNING
            self._audit(
                "workflow_started",
                workflow_id,
                attempt=workflow.attempt,
                revision=workflow.revision,
            )
            return True

    def fail_workflow(self, workflow_id: str, reason: str = "") -> bool:
        with self._lock:
            workflow = self._workflows.get(workflow_id)
            if not workflow:
                return False
            workflow.status = StepStatus.FAILED
            workflow.revision += 1
            self._audit(
                "workflow_failed",
                workflow_id,
                revision=workflow.revision,
                reason=reason,
            )
            return True

    def subworkflow_context(
        self,
        parent_workflow_id: str,
    ) -> Optional[Dict[str, Any]]:
        with self._lock:
            parent = self._workflows.get(parent_workflow_id)
            if not parent:
                return None
            return {
                "parent_workflow_id": parent.id,
                "parent_attempt": parent.attempt,
                "parent_revision": parent.revision,
            }

    def start_subworkflow(
        self,
        parent_workflow_id: str,
        name: str,
        description: str = "",
        parent_attempt: Optional[int] = None,
        parent_revision: Optional[int] = None,
    ) -> Optional[Workflow]:
        with self._lock:
            parent = self._workflows.get(parent_workflow_id)
            if not parent:
                self._audit(
                    "subworkflow_rejected",
                    None,
                    parent_workflow_id=parent_workflow_id,
                    reason="missing_parent",
                )
                return None

            expected_attempt = (
                parent.attempt if parent_attempt is None else parent_attempt
            )
            expected_revision = (
                parent.revision if parent_revision is None else parent_revision
            )
            reject_reason = self._subworkflow_reject_reason(
                parent,
                expected_attempt,
                expected_revision,
            )
            if reject_reason:
                self._audit(
                    "subworkflow_rejected",
                    None,
                    parent_workflow_id=parent.id,
                    parent_status=parent.status.value,
                    parent_attempt=parent.attempt,
                    parent_revision=parent.revision,
                    expected_attempt=expected_attempt,
                    expected_revision=expected_revision,
                    reason=reject_reason,
                )
                return None

            subworkflow = Workflow(name, description, parent_id=parent.id)
            subworkflow.attempt = 1
            subworkflow.revision = 1
            subworkflow.status = StepStatus.RUNNING
            self._workflows[subworkflow.id] = subworkflow
            self._audit(
                "subworkflow_started",
                subworkflow.id,
                parent_workflow_id=parent.id,
                parent_attempt=parent.attempt,
                parent_revision=parent.revision,
            )
            return subworkflow

    def execute_workflow(self, workflow_id: str) -> bool:
        workflow = self.get_workflow(workflow_id)
        if not workflow:
            return False

        if not self.start_workflow(workflow_id):
            return False
        for step in workflow.steps:
            step.status = StepStatus.RUNNING
            try:
                result = step.handler()
                step.result = result
                step.status = StepStatus.COMPLETED
            except Exception as e:
                step.error = str(e)
                step.status = StepStatus.FAILED
                self.fail_workflow(workflow_id, str(e))
                return False

        with self._lock:
            workflow.status = StepStatus.COMPLETED
            workflow.revision += 1
            self._audit(
                "workflow_completed",
                workflow_id,
                revision=workflow.revision,
            )
        return True

    def audit_events(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._audit_events)

    def _subworkflow_reject_reason(
        self,
        parent: Workflow,
        expected_attempt: int,
        expected_revision: int,
    ) -> Optional[str]:
        if parent.status != StepStatus.RUNNING:
            return "parent_not_running"
        if parent.attempt != expected_attempt:
            return "stale_parent_attempt"
        if parent.revision != expected_revision:
            return "stale_parent_revision"
        return None

    def _audit(
        self,
        event: str,
        workflow_id: Optional[str],
        **metadata: Any,
    ) -> None:
        self._audit_events.append(
            {
                "event": event,
                "workflow_id": workflow_id,
                "metadata": metadata,
                "timestamp": time.time(),
            }
        )

# 2019-03-27T19:58:07 update

# 2019-05-09T09:42:56 update

# 2019-12-03T10:07:42 update

# 2020-01-16T18:43:28 update

# 2020-03-20T10:40:15 update

# 2020-04-17T15:36:50 update

# 2020-05-04T14:44:01 update

# 2020-06-16T13:17:31 update

# 2020-08-05T17:00:24 update

# 2020-09-04T08:29:23 update

# 2020-09-09T17:52:02 update

# 2020-10-23T10:57:44 update

# 2020-12-05T20:55:47 update

# 2021-01-15T19:23:40 update

# 2021-02-03T20:43:12 update

# 2021-03-16T12:26:47 update

# 2021-04-20T14:33:28 update

# 2021-10-14T15:03:32 update

# 2021-10-21T17:24:55 update

# 2021-11-16T17:01:08 update

# 2021-11-22T09:51:21 update

# 2021-12-21T16:15:47 update

# 2022-03-23T16:52:27 update

# 2022-12-21T09:25:50 update

# 2023-01-09T09:55:25 update

# 2023-01-13T11:06:15 update

# 2023-01-26T11:00:59 update

# 2023-02-23T08:56:54 update

# 2023-05-17T08:07:16 update

# 2023-06-06T17:09:34 update

# 2023-06-13T10:35:28 update

# 2023-08-24T20:36:06 update

# 2023-10-30T19:10:13 update

# 2024-01-02T08:27:25 update

# 2024-01-24T12:13:15 update

# 2024-02-08T13:35:49 update

# 2024-05-07T16:09:24 update

# 2024-05-11T09:48:46 update

# 2024-05-21T19:25:41 update

# 2024-06-05T12:00:30 update

# 2024-06-25T09:40:26 update

# 2024-09-17T13:49:39 update

# 2024-10-14T17:39:35 update

# 2024-11-27T20:14:35 update

# 2024-12-25T19:31:41 update

# 2025-01-16T13:15:09 update

# 2025-02-05T14:06:59 update

# 2025-02-17T20:55:11 update

# 2025-04-30T19:36:53 update

# 2025-07-17T10:14:40 update

# 2025-08-29T12:13:15 update

# 2025-09-03T13:51:11 update

# 2025-09-19T16:08:24 update

# 2025-11-27T08:38:12 update

# 2026-01-27T13:23:38 update

# 2026-01-28T11:22:50 update
