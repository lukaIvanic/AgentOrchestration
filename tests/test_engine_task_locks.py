import asyncio

from src.orchestrator.engine import OrchestrationEngine


def test_engine_releases_task_lock_and_records_failure_on_exception():
    engine = OrchestrationEngine()
    agent_id = engine.registry.register("agent-1", "worker.processor")

    async def run_agent_task(agent, task):
        raise RuntimeError("worker crashed")

    engine._run_agent_task = run_agent_task

    asyncio.run(engine._execute_task({
        "id": "task-1",
        "target_agent": agent_id,
    }))

    assert not engine.locks.is_locked("task:task-1")
    assert engine.locks.terminal_outcome("task-1")["status"] == "failed"
    events = [event["event"] for event in engine.locks.audit_events()]
    assert events == [
        "lock_acquired",
        "terminal_outcome_recorded",
        "lock_released",
    ]


def test_engine_skips_duplicate_active_dispatch_before_side_effects():
    engine = OrchestrationEngine()
    agent_id = engine.registry.register("agent-1", "worker.processor")
    calls = []

    async def pre_execute(task):
        calls.append("pre_execute")

    async def run_agent_task(agent, task):
        calls.append("run_agent_task")
        return {"status": "completed"}

    engine.register_hook("pre_execute", pre_execute)
    engine._run_agent_task = run_agent_task

    with engine.locks.acquire("task:task-1", "agent:other"):
        asyncio.run(engine._execute_task({
            "id": "task-1",
            "target_agent": agent_id,
        }))

    assert calls == []
    assert engine.locks.terminal_outcome("task-1") is None
    assert not engine.locks.is_locked("task:task-1")
    assert [
        event["event"] for event in engine.locks.audit_events()
    ] == [
        "lock_acquired",
        "lock_acquire_rejected",
        "lock_released",
    ]


def test_engine_records_success_once_and_releases_task_lock():
    engine = OrchestrationEngine()
    agent_id = engine.registry.register("agent-1", "worker.processor")

    async def run_agent_task(agent, task):
        return {"status": "completed"}

    engine._run_agent_task = run_agent_task

    asyncio.run(engine._execute_task({
        "id": "task-1",
        "target_agent": agent_id,
    }))

    assert not engine.locks.is_locked("task:task-1")
    assert engine.locks.terminal_outcome("task-1")["status"] == "completed"
