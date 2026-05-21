from src.orchestrator.workflow import StepStatus, WorkflowManager


class TestWorkflowManager:
    def test_start_subworkflow_uses_parent_attempt_and_revision(self):
        manager = WorkflowManager()
        parent = manager.create_workflow("parent")
        assert manager.start_workflow(parent.id)
        context = manager.subworkflow_context(parent.id)

        child = manager.start_subworkflow(
            parent.id,
            "child",
            parent_attempt=context["parent_attempt"],
            parent_revision=context["parent_revision"],
        )

        assert child is not None
        assert child.parent_id == parent.id
        assert child.status is StepStatus.RUNNING
        assert child.attempt == 1
        assert child.revision == 1

    def test_rejects_subworkflow_start_after_parent_failure_race(self):
        manager = WorkflowManager()
        parent = manager.create_workflow("parent")
        assert manager.start_workflow(parent.id)
        context = manager.subworkflow_context(parent.id)

        assert manager.fail_workflow(parent.id, "upstream task failed")
        child = manager.start_subworkflow(
            parent.id,
            "orphaned-child",
            parent_attempt=context["parent_attempt"],
            parent_revision=context["parent_revision"],
        )

        assert child is None
        assert manager.get_workflow(parent.id).status is StepStatus.FAILED
        assert manager.list_workflows() == [parent]
        rejection = manager.audit_events()[-1]
        assert rejection["event"] == "subworkflow_rejected"
        assert rejection["metadata"]["reason"] == "parent_not_running"
        assert rejection["metadata"]["parent_revision"] != context[
            "parent_revision"
        ]

    def test_rejects_stale_parent_revision_before_starting_subworkflow(self):
        manager = WorkflowManager()
        parent = manager.create_workflow("parent")
        assert manager.start_workflow(parent.id)
        context = manager.subworkflow_context(parent.id)

        parent.revision += 1
        child = manager.start_subworkflow(
            parent.id,
            "stale-child",
            parent_attempt=context["parent_attempt"],
            parent_revision=context["parent_revision"],
        )

        assert child is None
        assert manager.get_workflow(parent.id).status is StepStatus.RUNNING
        assert len(manager.list_workflows()) == 1
        assert manager.audit_events()[-1]["metadata"]["reason"] == (
            "stale_parent_revision"
        )
