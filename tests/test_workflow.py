from src.orchestrator.workflow import (
    StepStatus,
    Workflow,
    WorkflowManager,
    WorkflowStep,
)


def test_late_child_success_does_not_overwrite_parent_failure(caplog):
    workflow = Workflow("critical workflow")
    failed_step = WorkflowStep("parent failure", lambda: None)
    late_step = WorkflowStep("late child", lambda: None)
    workflow.add_step(failed_step).add_step(late_step)

    assert workflow.apply_step_update(failed_step.id, StepStatus.FAILED)
    assert workflow.status == StepStatus.FAILED

    with caplog.at_level("WARNING"):
        accepted = workflow.apply_step_update(
            late_step.id,
            StepStatus.COMPLETED,
            result={"internal": "not logged"},
            expected_step_revision=late_step.revision,
        )

    assert not accepted
    assert workflow.status == StepStatus.FAILED
    assert late_step.status == StepStatus.PENDING
    assert workflow.audit_events == [
        {
            "workflow_id": workflow.id,
            "step_id": late_step.id,
            "step_revision": 0,
            "attempt": 1,
            "workflow_status": "failed",
            "workflow_revision": 1,
            "attempted_status": "completed",
            "reason": "parent_workflow_failed",
        }
    ]
    assert "Rejected stale child workflow transition" in caplog.text
    assert "not logged" not in caplog.text


def test_stale_revision_child_event_is_rejected_before_commit():
    workflow = Workflow("revision guarded workflow")
    step = WorkflowStep("child", lambda: None)
    workflow.add_step(step)

    assert workflow.apply_step_update(
        step.id,
        StepStatus.RUNNING,
        expected_step_revision=0,
    )

    accepted = workflow.apply_step_update(
        step.id,
        StepStatus.COMPLETED,
        result="stale",
        expected_step_revision=0,
    )

    assert not accepted
    assert step.status == StepStatus.RUNNING
    assert step.result is None
    assert step.revision == 1
    assert workflow.audit_events[-1]["reason"] == "stale_step_revision"


def test_wrong_attempt_child_event_is_rejected_before_commit():
    workflow = Workflow("attempt guarded workflow")
    step = WorkflowStep("child", lambda: None)
    workflow.add_step(step)

    accepted = workflow.apply_step_update(
        step.id,
        StepStatus.COMPLETED,
        attempt=2,
    )

    assert not accepted
    assert step.status == StepStatus.PENDING
    assert step.revision == 0
    assert workflow.audit_events[-1]["reason"] == "attempt_mismatch"


def test_workflow_execution_still_completes_successful_steps():
    manager = WorkflowManager()
    workflow = manager.create_workflow("successful workflow")
    workflow.add_step(WorkflowStep("first", lambda: "ok"))

    assert manager.execute_workflow(workflow.id)
    assert workflow.status == StepStatus.COMPLETED
    assert workflow.steps[0].status == StepStatus.COMPLETED
    assert workflow.steps[0].result == "ok"
