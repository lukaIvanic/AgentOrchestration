"""Run event stream service with bounded pagination guards."""

from dataclasses import dataclass
from typing import Dict, List, Tuple


MAX_RUN_EVENT_LIMIT = 100
MAX_RUN_EVENT_WINDOW = 1000


class RunEventStreamError(ValueError):
    """Base error for deterministic event stream rejections."""

    status_code = 400


class RunEventUnauthorizedError(RunEventStreamError):
    status_code = 403


class RunEventPaginationError(RunEventStreamError):
    status_code = 400


@dataclass(frozen=True)
class RunEventPage:
    run_id: str
    tenant_id: str
    cursor: int
    limit: int
    next_cursor: int
    events: List[Dict]


class InMemoryRunEventStore:
    def __init__(self):
        self._events: Dict[Tuple[str, str], List[Dict]] = {}
        self.lookup_count = 0

    def replace_events(
        self,
        tenant_id: str,
        run_id: str,
        events: List[Dict],
    ) -> None:
        self._events[(tenant_id, run_id)] = list(events)

    def list_events(
        self,
        tenant_id: str,
        run_id: str,
        cursor: int,
        limit: int,
    ) -> List[Dict]:
        self.lookup_count += 1
        events = self._events.get((tenant_id, run_id), [])
        return events[cursor:cursor + limit]


class RunEventStreamService:
    def __init__(self, store: InMemoryRunEventStore = None):
        self.store = store or InMemoryRunEventStore()

    def list_run_events(
        self,
        authorization: str,
        tenant_id: str,
        run_id: str,
        cursor: int = 0,
        limit: int = 50,
    ) -> RunEventPage:
        self._validate_request(authorization, tenant_id, run_id, cursor, limit)
        events = self.store.list_events(tenant_id, run_id, cursor, limit)
        return RunEventPage(
            run_id=run_id,
            tenant_id=tenant_id,
            cursor=cursor,
            limit=limit,
            next_cursor=cursor + len(events),
            events=events,
        )

    def _validate_request(
        self,
        authorization: str,
        tenant_id: str,
        run_id: str,
        cursor: int,
        limit: int,
    ) -> None:
        if not tenant_id or not tenant_id.strip():
            raise RunEventPaginationError("tenant_id is required")
        if not run_id or not run_id.strip():
            raise RunEventPaginationError("run_id is required")
        self._authorize(authorization, tenant_id)
        if cursor < 0:
            raise RunEventPaginationError("cursor must be non-negative")
        if limit < 1:
            raise RunEventPaginationError("limit must be at least 1")
        if limit > MAX_RUN_EVENT_LIMIT:
            raise RunEventPaginationError(
                f"limit must not exceed {MAX_RUN_EVENT_LIMIT}"
            )
        if cursor + limit > MAX_RUN_EVENT_WINDOW:
            raise RunEventPaginationError(
                f"event window must not exceed {MAX_RUN_EVENT_WINDOW}"
            )

    def _authorize(self, authorization: str, tenant_id: str) -> None:
        if not authorization.startswith("Bearer "):
            raise RunEventUnauthorizedError(
                "authorization bearer token is required"
            )
        expected = f"Bearer tenant:{tenant_id}"
        if authorization != expected:
            raise RunEventUnauthorizedError(
                "tenant is not authorized for this run event stream"
            )
