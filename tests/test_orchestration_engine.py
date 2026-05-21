import asyncio

from src.agent import AgentStatus
from src.orchestrator.engine import OrchestrationEngine


class TestOrchestrationEngine:
    def test_required_permission_is_rechecked_before_lifecycle_change(
        self,
    ):
        engine = OrchestrationEngine()
        agent_id = engine.registry.register(
            "test-agent",
            "worker.processor",
            {"permissions": ["tasks.execute"]},
        )
        task = {
            "id": "task-1",
            "target_agent": agent_id,
            "required_permission": "tasks.execute",
            "principal": "scheduler",
        }

        assert (
            engine.registry.resolve_authorized(
                agent_id,
                "tasks.execute",
                principal="scheduler",
            )["id"]
            == agent_id
        )
        assert engine.registry.set_permissions(agent_id, [])

        asyncio.run(engine._execute_task(task))

        agent = engine.registry.get(agent_id)
        assert agent["status"] == AgentStatus.PENDING.value
        events = engine.registry.audit_events()
        assert events[-1]["event"] == "auth_denied"
        assert events[-1]["metadata"]["reason"] == "permission_revoked"
        assert not any(
            event["event"] == "status_changed"
            and event["metadata"]["status"] == AgentStatus.RUNNING.value
            for event in events
        )
