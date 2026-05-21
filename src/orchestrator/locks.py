"""Advisory lock helpers for orchestration runs."""

from contextlib import contextmanager
from threading import RLock
import time
from typing import Any, Callable, Dict, List, Optional


class AdvisoryLockError(RuntimeError):
    pass


class AdvisoryLockManager:
    def __init__(self):
        self._lock = RLock()
        self._held: Dict[str, str] = {}
        self._outcomes: Dict[str, Dict[str, Any]] = {}
        self._audit_events: List[Dict[str, Any]] = []

    @contextmanager
    def acquire(self, lock_id: str, owner: str):
        lock_id = str(lock_id)
        owner = str(owner)
        with self._lock:
            existing_owner = self._held.get(lock_id)
            if existing_owner and existing_owner != owner:
                self._audit(
                    "lock_acquire_rejected",
                    lock_id,
                    owner=owner,
                    existing_owner=existing_owner,
                )
                raise AdvisoryLockError("advisory lock already held")
            self._held[lock_id] = owner
            self._audit("lock_acquired", lock_id, owner=owner)
        try:
            yield
        finally:
            self.release(lock_id, owner)

    def run_with_lock(
        self,
        lock_id: str,
        owner: str,
        run_id: str,
        operation: Callable[[], Any],
    ) -> Any:
        with self.acquire(lock_id, owner):
            try:
                result = operation()
            except Exception as exc:
                self.record_terminal_outcome(
                    run_id,
                    "failed",
                    reason=str(exc),
                )
                raise
            self.record_terminal_outcome(run_id, "completed")
            return result

    def release(self, lock_id: str, owner: str) -> bool:
        with self._lock:
            if self._held.get(lock_id) != owner:
                return False
            self._held.pop(lock_id, None)
            self._audit("lock_released", lock_id, owner=owner)
            return True

    def is_locked(self, lock_id: str) -> bool:
        with self._lock:
            return lock_id in self._held

    def record_terminal_outcome(
        self,
        run_id: str,
        status: str,
        reason: Optional[str] = None,
    ) -> bool:
        with self._lock:
            if run_id in self._outcomes:
                self._audit(
                    "terminal_outcome_ignored",
                    run_id,
                    status=status,
                )
                return False
            self._outcomes[run_id] = {
                "status": status,
                "reason": reason,
                "recorded_at": time.time(),
            }
            self._audit(
                "terminal_outcome_recorded",
                run_id,
                status=status,
                reason=reason,
            )
            return True

    def terminal_outcome(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._outcomes.get(run_id)

    def audit_events(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._audit_events)

    def _audit(self, event: str, lock_id: str, **metadata: Any) -> None:
        self._audit_events.append(
            {
                "event": event,
                "lock_id": lock_id,
                "metadata": metadata,
                "timestamp": time.time(),
            }
        )
