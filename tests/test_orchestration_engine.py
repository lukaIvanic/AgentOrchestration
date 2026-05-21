import asyncio

from src.agent import AgentStatus
from src.orchestrator.engine import OrchestrationEngine


def test_engine_rejects_unhealthy_target_before_execution():
    engine = OrchestrationEngine()
    agent_id = engine.registry.register(
        "agent-1",
        "worker.processor",
        {"capabilities": ["summarize"]},
    )
    engine.registry.update_status(agent_id, AgentStatus.RUNNING)
    engine.registry.update_health(
        agent_id,
        healthy=False,
        accepting_tasks=False,
        reason="rolling_deploy",
    )
    calls = []

    async def run_agent_task(agent, task):
        calls.append((agent, task))
        return {"status": "completed"}

    engine._run_agent_task = run_agent_task

    asyncio.run(engine._execute_task({
        "id": "task-1",
        "target_agent": agent_id,
        "required_capability": "summarize",
    }))

    assert calls == []
    assert engine.registry.get(agent_id)["status"] == "running"
    assert engine.registry.routing_audit[-1]["decision"] == "deferred"
    assert engine.registry.routing_audit[-1]["healthy"] is False
    assert "config" not in engine.registry.routing_audit[-1]


def test_engine_routes_healthy_target_through_registry_guard():
    engine = OrchestrationEngine()
    agent_id = engine.registry.register(
        "agent-1",
        "worker.processor",
        {"capabilities": ["summarize"]},
    )
    engine.registry.update_status(agent_id, AgentStatus.RUNNING)
    calls = []

    async def run_agent_task(agent, task):
        calls.append((agent["id"], task["id"]))
        return {"status": "completed"}

    engine._run_agent_task = run_agent_task

    asyncio.run(engine._execute_task({
        "id": "task-2",
        "target_agent": agent_id,
        "required_capability": "summarize",
    }))

    assert calls == [(agent_id, "task-2")]
    assert engine.registry.get(agent_id)["status"] == "paused"
    assert engine.registry.routing_audit[-1]["decision"] == "selected"
