"""Run event listing service."""

from typing import Any, Dict, List, Optional, Protocol

from fastapi import HTTPException


MAX_RUN_EVENT_LIMIT = 100
MAX_RUN_EVENT_WINDOW = 1000
DEFAULT_RUN_EVENT_LIMIT = 50


class RunEventStore(Protocol):
    def list_run_events(
        self,
        run_id: str,
        offset: int,
        limit: int,
    ) -> List[Dict[str, Any]]:
        ...


class InMemoryRunEventStore:
    def __init__(self) -> None:
        self._events: Dict[str, List[Dict[str, Any]]] = {}

    def add_event(self, run_id: str, event: Dict[str, Any]) -> None:
        self._events.setdefault(run_id, []).append(dict(event))

    def list_run_events(
        self,
        run_id: str,
        offset: int,
        limit: int,
    ) -> List[Dict[str, Any]]:
        window = self._events.get(run_id, [])[offset:offset + limit]
        return [dict(event) for event in window]


run_event_store = InMemoryRunEventStore()


def _require_bearer_token(authorization: Optional[str]) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    if not authorization.removeprefix("Bearer ").strip():
        raise HTTPException(status_code=401, detail="Unauthorized")


def _validate_pagination(offset: int, limit: int) -> None:
    if offset < 0:
        raise HTTPException(
            status_code=400,
            detail="offset must be greater than or equal to 0",
        )
    if limit < 1:
        raise HTTPException(
            status_code=400,
            detail="limit must be greater than 0",
        )
    if limit > MAX_RUN_EVENT_LIMIT:
        raise HTTPException(
            status_code=400,
            detail=f"limit must be at most {MAX_RUN_EVENT_LIMIT}",
        )
    if offset + limit > MAX_RUN_EVENT_WINDOW:
        raise HTTPException(
            status_code=400,
            detail=f"offset plus limit must be at most {MAX_RUN_EVENT_WINDOW}",
        )


def list_run_events(
    run_id: str,
    authorization: Optional[str],
    offset: int = 0,
    limit: int = DEFAULT_RUN_EVENT_LIMIT,
    store: Optional[RunEventStore] = None,
) -> Dict[str, Any]:
    _require_bearer_token(authorization)
    _validate_pagination(offset, limit)

    event_store = store or run_event_store
    events = event_store.list_run_events(run_id, offset=offset, limit=limit)
    return {
        "run_id": run_id,
        "events": events,
        "offset": offset,
        "limit": limit,
        "count": len(events),
    }
