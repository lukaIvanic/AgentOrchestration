import subprocess
from unittest.mock import Mock

from src.agent.runtime import AgentRuntime, RuntimeState


class FakeProcess:
    pid = 1234

    def __init__(self, returncode=None, timeout_on_wait=False):
        self.returncode = returncode
        self.timeout_on_wait = timeout_on_wait
        self.signals = []
        self.killed = False

    def poll(self):
        return self.returncode

    def send_signal(self, sig):
        self.signals.append(sig)

    def wait(self, timeout=None):
        if self.timeout_on_wait:
            self.timeout_on_wait = False
            raise subprocess.TimeoutExpired(cmd="agent", timeout=timeout)
        self.returncode = 0
        return self.returncode

    def kill(self):
        self.killed = True
        self.returncode = -9


def test_stop_records_terminal_outcome_before_shutdown_signal(monkeypatch):
    process = FakeProcess()
    runtime = AgentRuntime()
    monkeypatch.setattr(subprocess, "Popen", Mock(return_value=process))

    assert runtime.start("agent-1", ["worker"])
    assert runtime.stop("agent-1")

    assert process.signals
    assert runtime.get_state("agent-1") == RuntimeState.STOPPED
    assert runtime.get_terminal_outcome("agent-1") == {
        "state": "stopped",
        "reason": "worker_shutdown_requested",
        "returncode": None,
    }


def test_shutdown_outcome_is_idempotent_when_forced_kill_follows(monkeypatch):
    process = FakeProcess(timeout_on_wait=True)
    runtime = AgentRuntime()
    monkeypatch.setattr(subprocess, "Popen", Mock(return_value=process))

    assert runtime.start("agent-1", ["worker"])
    assert runtime.stop("agent-1", timeout=0)

    assert process.killed
    assert runtime.get_terminal_outcome("agent-1")["reason"] == (
        "worker_shutdown_requested"
    )
    assert runtime.get_state("agent-1") == RuntimeState.STOPPED
    assert runtime.get_terminal_outcome("agent-1")["reason"] == (
        "worker_shutdown_requested"
    )


def test_process_exit_records_one_durable_failure_reason(monkeypatch):
    process = FakeProcess(returncode=2)
    runtime = AgentRuntime()
    monkeypatch.setattr(subprocess, "Popen", Mock(return_value=process))

    assert runtime.start("agent-1", ["worker"])

    assert runtime.get_state("agent-1") == RuntimeState.CRASHED
    assert runtime.get_terminal_outcome("agent-1") == {
        "state": "crashed",
        "reason": "process_exited: returncode=2",
        "returncode": 2,
    }

    process.returncode = 3
    assert runtime.get_state("agent-1") == RuntimeState.CRASHED
    assert runtime.get_terminal_outcome("agent-1")["returncode"] == 2


def test_start_failure_records_terminal_outcome(monkeypatch):
    runtime = AgentRuntime()
    monkeypatch.setattr(
        subprocess,
        "Popen",
        Mock(side_effect=OSError("missing executable")),
    )

    assert not runtime.start("agent-1", ["missing-worker"])

    outcome = runtime.get_terminal_outcome("agent-1")
    assert outcome["state"] == "crashed"
    assert outcome["reason"] == "start_failed: missing executable"
