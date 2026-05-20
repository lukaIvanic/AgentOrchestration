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
        )

    assert not accepted
    assert workflow.status == StepStatus.FAILED
    assert late_step.status == StepStatus.PENDING
    assert workflow.audit_events == [
        {
            "workflow_id": workflow.id,
            "step_id": late_step.id,
            "workflow_status": "failed",
            "attempted_status": "completed",
            "reason": "parent_workflow_failed",
        }
    ]
    assert "Rejected stale child workflow transition" in caplog.text
    assert "not logged" not in caplog.text


def test_workflow_execution_still_completes_successful_steps():
    manager = WorkflowManager()
    workflow = manager.create_workflow("successful workflow")
    workflow.add_step(WorkflowStep("first", lambda: "ok"))

    assert manager.execute_workflow(workflow.id)
    assert workflow.status == StepStatus.COMPLETED
    assert workflow.steps[0].status == StepStatus.COMPLETED
    assert workflow.steps[0].result == "ok"
