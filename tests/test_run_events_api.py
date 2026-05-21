from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import run_events
from src.api.routes import router


class RecordingRunEventStore:
    def __init__(self):
        self.calls = []

    def list_run_events(self, run_id, offset, limit):
        self.calls.append({"run_id": run_id, "offset": offset, "limit": limit})
        return [{"id": "event-1", "type": "started"}]


def make_client(store, monkeypatch):
    app = FastAPI()
    app.include_router(router)
    monkeypatch.setattr(run_events, "run_event_store", store)
    return TestClient(app)


def test_authorized_run_events_request_reads_store(monkeypatch):
    store = RecordingRunEventStore()
    client = make_client(store, monkeypatch)

    response = client.get(
        "/runs/run-123/events?offset=10&limit=25",
        headers={"Authorization": "Bearer valid-token"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "run_id": "run-123",
        "events": [{"id": "event-1", "type": "started"}],
        "offset": 10,
        "limit": 25,
        "count": 1,
    }
    assert store.calls == [{"run_id": "run-123", "offset": 10, "limit": 25}]


def test_unauthorized_run_events_request_skips_store(monkeypatch):
    store = RecordingRunEventStore()
    client = make_client(store, monkeypatch)

    response = client.get("/runs/run-123/events?offset=0&limit=25")

    assert response.status_code == 401
    assert store.calls == []


def test_blank_bearer_token_skips_store(monkeypatch):
    store = RecordingRunEventStore()
    client = make_client(store, monkeypatch)

    response = client.get(
        "/runs/run-123/events?offset=0&limit=25",
        headers={"Authorization": "Bearer "},
    )

    assert response.status_code == 401
    assert store.calls == []


def test_limit_above_cap_skips_store(monkeypatch):
    store = RecordingRunEventStore()
    client = make_client(store, monkeypatch)

    response = client.get(
        "/runs/run-123/events?offset=0&limit=101",
        headers={"Authorization": "Bearer valid-token"},
    )

    assert response.status_code == 400
    assert store.calls == []


def test_pagination_window_above_cap_skips_store(monkeypatch):
    store = RecordingRunEventStore()
    client = make_client(store, monkeypatch)

    response = client.get(
        "/runs/run-123/events?offset=950&limit=51",
        headers={"Authorization": "Bearer valid-token"},
    )

    assert response.status_code == 400
    assert store.calls == []


def test_negative_offset_skips_store(monkeypatch):
    store = RecordingRunEventStore()
    client = make_client(store, monkeypatch)

    response = client.get(
        "/runs/run-123/events?offset=-1&limit=25",
        headers={"Authorization": "Bearer valid-token"},
    )

    assert response.status_code == 400
    assert store.calls == []


def test_zero_limit_skips_store(monkeypatch):
    store = RecordingRunEventStore()
    client = make_client(store, monkeypatch)

    response = client.get(
        "/runs/run-123/events?offset=0&limit=0",
        headers={"Authorization": "Bearer valid-token"},
    )

    assert response.status_code == 400
    assert store.calls == []
