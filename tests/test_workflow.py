from src.orchestrator.workflow import StepStatus, WorkflowManager


def test_subworkflow_start_rejects_failed_parent_race():
    manager = WorkflowManager()
    parent = manager.create_workflow("parent")
    parent.status = StepStatus.RUNNING
    parent.attempt = 1
    parent.revision = 7

    captured_attempt = parent.attempt
    captured_revision = parent.revision
    assert manager.mark_failed(parent.id, "upstream step failed")

    child = manager.start_subworkflow(
        parent.id,
        "child",
        parent_attempt=captured_attempt,
        parent_revision=captured_revision,
    )

    assert child is None
    assert manager.get_workflow(parent.id).status == StepStatus.FAILED
    assert len(manager.list_workflows()) == 1
    rejected = manager.audit_events()[-1]
    assert rejected["event"] == "subworkflow_start_rejected"
    assert rejected["workflow_id"] == parent.id
    assert rejected["metadata"]["reason"] == "stale_parent_revision"


def test_subworkflow_start_rejects_non_running_parent_without_mutation():
    manager = WorkflowManager()
    parent = manager.create_workflow("parent")

    child = manager.start_subworkflow(
        parent.id,
        "child",
        parent_attempt=parent.attempt,
        parent_revision=parent.revision,
    )

    assert child is None
    assert manager.get_workflow(parent.id).status == StepStatus.PENDING
    assert len(manager.list_workflows()) == 1
    rejected = manager.audit_events()[-1]
    assert rejected["event"] == "subworkflow_start_rejected"
    assert rejected["metadata"]["reason"] == "parent_not_running"


def test_subworkflow_start_records_parent_revision():
    manager = WorkflowManager()
    parent = manager.create_workflow("parent")
    parent.status = StepStatus.RUNNING
    parent.attempt = 2
    parent.revision = 4

    child = manager.start_subworkflow(
        parent.id,
        "child",
        parent_attempt=2,
        parent_revision=4,
    )

    assert child is not None
    assert child.parent_id == parent.id
    assert child.parent_attempt == 2
    assert child.parent_revision == 4
    assert child.status == StepStatus.RUNNING
    assert manager.get_workflow(parent.id).status == StepStatus.RUNNING
    assert len(manager.list_workflows()) == 2
    assert manager.audit_events()[-1]["event"] == "subworkflow_started"
