from fastapi.testclient import TestClient

from src.api import routes
from src.api.event_stream import InMemoryRunEventStore, RunEventStreamService
from src.api.server import create_app


def make_client():
    store = InMemoryRunEventStore()
    routes.event_stream_service = RunEventStreamService(store)
    return TestClient(create_app()), routes.event_stream_service


def test_authorized_run_events_use_bounded_window():
    client, service = make_client()
    service.store.replace_events(
        "tenant-a",
        "run-1",
        [
            {"sequence": 1, "type": "started"},
            {"sequence": 2, "type": "finished"},
        ],
    )

    response = client.get(
        "/api/v2/runs/run-1/events?tenant_id=tenant-a&cursor=0&limit=2",
        headers={"Authorization": "Bearer tenant:tenant-a"},
    )

    assert response.status_code == 200
    assert response.json()["events"] == [
        {"sequence": 1, "type": "started"},
        {"sequence": 2, "type": "finished"},
    ]
    assert service.store.lookup_count == 1


def test_run_events_reject_unauthorized_tenant_before_lookup():
    client, service = make_client()
    service.store.replace_events("tenant-a", "run-1", [{"sequence": 1}])

    response = client.get(
        "/api/v2/runs/run-1/events?tenant_id=tenant-a&cursor=0&limit=1",
        headers={"Authorization": "Bearer tenant:tenant-b"},
    )

    assert response.status_code == 403
    assert "not authorized" in response.json()["detail"]
    assert service.store.lookup_count == 0


def test_run_events_reject_missing_bearer_before_route_lookup():
    client, service = make_client()

    response = client.get(
        "/api/v2/runs/run-1/events?tenant_id=tenant-a&cursor=0&limit=1"
    )

    assert response.status_code == 401
    assert service.store.lookup_count == 0


def test_run_events_reject_malformed_pagination_before_lookup():
    client, service = make_client()

    response = client.get(
        "/api/v2/runs/run-1/events?tenant_id=tenant-a&cursor=-1&limit=1",
        headers={"Authorization": "Bearer tenant:tenant-a"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "cursor must be non-negative"
    assert service.store.lookup_count == 0


def test_run_events_reject_over_window_pagination_before_lookup():
    client, service = make_client()

    response = client.get(
        "/api/v2/runs/run-1/events?tenant_id=tenant-a&cursor=950&limit=75",
        headers={"Authorization": "Bearer tenant:tenant-a"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "event window must not exceed 1000"
    assert service.store.lookup_count == 0


def test_run_events_allow_exact_window_boundary():
    client, service = make_client()
    service.store.replace_events(
        "tenant-a",
        "run-1",
        [{"sequence": index} for index in range(1000)],
    )

    response = client.get(
        "/api/v2/runs/run-1/events?tenant_id=tenant-a&cursor=900&limit=100",
        headers={"Authorization": "Bearer tenant:tenant-a"},
    )

    assert response.status_code == 200
    assert response.json()["next_cursor"] == 1000
    assert len(response.json()["events"]) == 100
    assert service.store.lookup_count == 1


def test_run_events_reject_one_past_window_before_lookup():
    client, service = make_client()

    response = client.get(
        "/api/v2/runs/run-1/events?tenant_id=tenant-a&cursor=901&limit=100",
        headers={"Authorization": "Bearer tenant:tenant-a"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "event window must not exceed 1000"
    assert service.store.lookup_count == 0


def test_run_events_reject_non_integer_pagination_before_lookup():
    client, service = make_client()

    response = client.get(
        "/api/v2/runs/run-1/events?tenant_id=tenant-a&cursor=abc&limit=100",
        headers={"Authorization": "Bearer tenant:tenant-a"},
    )

    assert response.status_code == 422
    assert service.store.lookup_count == 0
