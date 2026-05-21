from src.orchestrator.workflow import (
    StepStatus,
    WorkflowManager,
    WorkflowStep,
)


def test_partial_rollback_blocks_downstream_steps():
    events = []
    manager = WorkflowManager()
    workflow = manager.create_workflow("deploy")

    workflow.add_step(
        WorkflowStep(
            "reserve",
            lambda: events.append("reserve"),
            compensation=lambda: (_ for _ in ()).throw(
                RuntimeError("reservation rollback failed")
            ),
        )
    )
    workflow.add_step(
        WorkflowStep(
            "publish",
            lambda: (_ for _ in ()).throw(RuntimeError("publish failed")),
        )
    )
    workflow.add_step(WorkflowStep("notify", lambda: events.append("notify")))

    assert manager.execute_workflow(workflow.id) is False

    assert events == ["reserve"]
    assert workflow.status == StepStatus.BLOCKED
    assert workflow.blocked_reason == "partial_rollback_blocks_downstream"
    assert workflow.steps[0].status == StepStatus.COMPLETED
    assert workflow.steps[1].status == StepStatus.FAILED
    assert workflow.steps[2].status == StepStatus.BLOCKED
    assert workflow.steps[2].blocked_reason == (
        "upstream_compensation_incomplete"
    )


def test_successful_compensation_still_blocks_later_dispatch():
    events = []
    manager = WorkflowManager()
    workflow = manager.create_workflow("deploy")

    workflow.add_step(
        WorkflowStep(
            "reserve",
            lambda: events.append("reserve"),
            compensation=lambda: events.append("rollback-reserve"),
        )
    )
    workflow.add_step(
        WorkflowStep(
            "publish",
            lambda: (_ for _ in ()).throw(RuntimeError("publish failed")),
        )
    )
    workflow.add_step(WorkflowStep("notify", lambda: events.append("notify")))

    assert manager.execute_workflow(workflow.id) is False

    assert events == ["reserve", "rollback-reserve"]
    assert workflow.status == StepStatus.FAILED
    assert workflow.steps[0].status == StepStatus.COMPENSATED
    assert workflow.steps[2].status == StepStatus.BLOCKED


def test_compensation_audit_uses_bounded_metadata_only():
    manager = WorkflowManager()
    workflow = manager.create_workflow("deploy")

    workflow.add_step(
        WorkflowStep(
            "reserve",
            lambda: {"private_payload": "secret"},
            compensation=lambda: (_ for _ in ()).throw(
                RuntimeError("rollback failed")
            ),
        )
    )
    workflow.add_step(
        WorkflowStep(
            "publish",
            lambda: (_ for _ in ()).throw(RuntimeError("publish failed")),
        )
    )

    assert manager.execute_workflow(workflow.id) is False

    audit = manager.audit_log()
    assert [entry["event"] for entry in audit] == [
        "step_failed",
        "compensation_failed",
        "downstream_blocked",
    ]
    assert all("private_payload" not in entry for entry in audit)
    assert audit[-1]["reason"] == "partial_rollback_blocks_downstream"
