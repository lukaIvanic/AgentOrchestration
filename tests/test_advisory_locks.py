import pytest

from src.orchestrator.locks import AdvisoryLockError, AdvisoryLockManager


class TestAdvisoryLockManager:
    def setup_method(self):
        self.manager = AdvisoryLockManager()

    def test_releases_lock_and_records_failure_on_exception(self):
        def operation():
            raise RuntimeError("worker crashed")

        with pytest.raises(RuntimeError):
            self.manager.run_with_lock(
                "task:1",
                "worker-a",
                "run-1",
                operation,
            )

        assert not self.manager.is_locked("task:1")
        assert self.manager.terminal_outcome("run-1")["status"] == "failed"
        events = [event["event"] for event in self.manager.audit_events()]
        assert events == [
            "lock_acquired",
            "terminal_outcome_recorded",
            "lock_released",
        ]

    def test_success_records_one_terminal_outcome_and_releases_lock(self):
        result = self.manager.run_with_lock(
            "task:1",
            "worker-a",
            "run-1",
            lambda: "ok",
        )

        assert result == "ok"
        assert not self.manager.is_locked("task:1")
        assert self.manager.terminal_outcome("run-1")["status"] == "completed"

    def test_terminal_outcome_is_idempotent_under_retry(self):
        assert self.manager.record_terminal_outcome("run-1", "failed")
        assert not self.manager.record_terminal_outcome("run-1", "completed")

        outcome = self.manager.terminal_outcome("run-1")
        assert outcome["status"] == "failed"
        assert [
            event["event"] for event in self.manager.audit_events()
        ] == [
            "terminal_outcome_recorded",
            "terminal_outcome_ignored",
        ]

    def test_concurrent_owner_cannot_steal_held_lock(self):
        with self.manager.acquire("task:1", "worker-a"):
            with pytest.raises(AdvisoryLockError):
                with self.manager.acquire("task:1", "worker-b"):
                    pass

        assert not self.manager.is_locked("task:1")
        assert self.manager.audit_events()[-1]["event"] == "lock_released"
