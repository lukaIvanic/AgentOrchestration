from fastapi.testclient import TestClient

from src.api import routes
from src.api.event_stream import InMemoryRunEventStore, RunEventStreamService
from src.api.server import create_app


def make_client():
    store = InMemoryRunEventStore()
    routes.event_stream_service = RunEventStreamService(store)
    return TestClient(create_app()), routes.event_stream_service


def auth_headers(tenant_id="tenant-a", workspace_id="workspace-a"):
    return {
        "Authorization": f"Bearer tenant:{tenant_id}",
        "X-Workspace-Id": workspace_id,
    }


def test_authorized_run_events_use_bounded_window():
    client, service = make_client()
    service.store.replace_events(
        "workspace-a",
        "tenant-a",
        "run-1",
        [
            {"sequence": 1, "type": "started"},
            {"sequence": 2, "type": "finished"},
        ],
    )

    response = client.get(
        "/api/v2/runs/run-1/events?tenant_id=tenant-a&cursor=0&limit=2",
        headers=auth_headers(),
    )

    assert response.status_code == 200
    assert response.json()["events"] == [
        {"sequence": 1, "type": "started"},
        {"sequence": 2, "type": "finished"},
    ]
    assert response.json()["workspace_id"] == "workspace-a"
    assert service.store.lookup_count == 1


def test_authorized_run_events_accept_offset_alias():
    client, service = make_client()
    service.store.replace_events(
        "workspace-a",
        "tenant-a",
        "run-1",
        [{"sequence": 1}, {"sequence": 2}, {"sequence": 3}],
    )

    response = client.get(
        "/api/v2/runs/run-1/events?tenant_id=tenant-a&offset=1&limit=1",
        headers=auth_headers(),
    )

    assert response.status_code == 200
    assert response.json()["events"] == [{"sequence": 2}]
    assert response.json()["offset"] == 1
    assert response.json()["next_offset"] == 2
    assert service.store.lookup_count == 1


def test_run_events_reject_unauthorized_tenant_before_lookup():
    client, service = make_client()
    service.store.replace_events(
        "workspace-a",
        "tenant-a",
        "run-1",
        [{"sequence": 1}],
    )

    response = client.get(
        "/api/v2/runs/run-1/events?tenant_id=tenant-a&cursor=0&limit=1",
        headers=auth_headers(tenant_id="tenant-b"),
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


def test_run_events_reject_blank_bearer_before_lookup():
    client, service = make_client()

    response = client.get(
        "/api/v2/runs/run-1/events?tenant_id=tenant-a&offset=0&limit=1",
        headers={"Authorization": "Bearer ", "X-Workspace-Id": "workspace-a"},
    )

    assert response.status_code == 401
    assert (
        response.json()["detail"] == "authorization bearer token is required"
    )
    assert service.store.lookup_count == 0


def test_run_events_reject_negative_offset_before_lookup():
    client, service = make_client()

    response = client.get(
        "/api/v2/runs/run-1/events?tenant_id=tenant-a&offset=-1&limit=1",
        headers=auth_headers(),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "cursor must be non-negative"
    assert service.store.lookup_count == 0


def test_run_events_reject_zero_limit_before_lookup():
    client, service = make_client()

    response = client.get(
        "/api/v2/runs/run-1/events?tenant_id=tenant-a&offset=0&limit=0",
        headers=auth_headers(),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "limit must be at least 1"
    assert service.store.lookup_count == 0


def test_run_events_reject_oversized_limit_before_lookup():
    client, service = make_client()

    response = client.get(
        "/api/v2/runs/run-1/events?tenant_id=tenant-a&offset=0&limit=101",
        headers=auth_headers(),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "limit must not exceed 100"
    assert service.store.lookup_count == 0


def test_run_events_reject_over_window_pagination_before_lookup():
    client, service = make_client()

    response = client.get(
        "/api/v2/runs/run-1/events?tenant_id=tenant-a&offset=950&limit=75",
        headers=auth_headers(),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "event window must not exceed 1000"
    assert service.store.lookup_count == 0


def test_run_events_allow_exact_window_boundary():
    client, service = make_client()
    service.store.replace_events(
        "workspace-a",
        "tenant-a",
        "run-1",
        [{"sequence": index} for index in range(1000)],
    )

    response = client.get(
        "/api/v2/runs/run-1/events?tenant_id=tenant-a&cursor=900&limit=100",
        headers=auth_headers(),
    )

    assert response.status_code == 200
    assert response.json()["next_cursor"] == 1000
    assert len(response.json()["events"]) == 100
    assert service.store.lookup_count == 1


def test_run_events_scope_lookup_by_workspace():
    client, service = make_client()
    service.store.replace_events(
        "workspace-a",
        "tenant-a",
        "run-1",
        [{"sequence": 1, "workspace": "a"}],
    )
    service.store.replace_events(
        "workspace-b",
        "tenant-a",
        "run-1",
        [{"sequence": 1, "workspace": "b"}],
    )

    response = client.get(
        "/api/v2/runs/run-1/events?tenant_id=tenant-a&offset=0&limit=10",
        headers=auth_headers(workspace_id="workspace-b"),
    )

    assert response.status_code == 200
    assert response.json()["workspace_id"] == "workspace-b"
    assert response.json()["events"] == [{"sequence": 1, "workspace": "b"}]
    assert service.store.lookup_count == 1


def test_run_events_reject_missing_workspace_before_lookup():
    client, service = make_client()

    response = client.get(
        "/api/v2/runs/run-1/events?tenant_id=tenant-a&offset=0&limit=1",
        headers={"Authorization": "Bearer tenant:tenant-a"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "workspace_id is required"
    assert service.store.lookup_count == 0


def test_run_events_reject_blank_workspace_before_lookup():
    client, service = make_client()

    response = client.get(
        "/api/v2/runs/run-1/events?tenant_id=tenant-a&offset=0&limit=1",
        headers=auth_headers(workspace_id=" "),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "workspace_id is required"
    assert service.store.lookup_count == 0


def test_run_events_reject_one_past_window_before_lookup():
    client, service = make_client()

    response = client.get(
        "/api/v2/runs/run-1/events?tenant_id=tenant-a&cursor=901&limit=100",
        headers=auth_headers(),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "event window must not exceed 1000"
    assert service.store.lookup_count == 0


def test_run_events_reject_conflicting_cursor_and_offset_before_lookup():
    client, service = make_client()

    response = client.get(
        "/api/v2/runs/run-1/events?tenant_id=tenant-a&cursor=1&offset=2",
        headers=auth_headers(),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "cursor and offset must match when both are provided"
    )
    assert service.store.lookup_count == 0


def test_run_events_reject_non_integer_pagination_before_lookup():
    client, service = make_client()

    response = client.get(
        "/api/v2/runs/run-1/events?tenant_id=tenant-a&cursor=abc&limit=100",
        headers=auth_headers(),
    )

    assert response.status_code == 422
    assert service.store.lookup_count == 0


def test_run_events_reject_non_integer_offset_before_lookup():
    client, service = make_client()

    response = client.get(
        "/api/v2/runs/run-1/events?tenant_id=tenant-a&offset=abc&limit=1",
        headers=auth_headers(),
    )

    assert response.status_code == 422
    assert service.store.lookup_count == 0


def test_run_events_reject_non_integer_limit_before_lookup():
    client, service = make_client()

    response = client.get(
        "/api/v2/runs/run-1/events?tenant_id=tenant-a&cursor=0&limit=abc",
        headers=auth_headers(),
    )

    assert response.status_code == 422
    assert service.store.lookup_count == 0
