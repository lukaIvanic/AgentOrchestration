import time

from fastapi.testclient import TestClient

from src.api.auth import AuthService
from src.api.server import create_app
from src.api.task_monitor import TaskMonitor


def make_client():
    auth = AuthService()
    monitor = TaskMonitor()
    monitor.upsert("task-1", workspace_id="workspace-a", status="running")
    app = create_app({"auth_service": auth, "task_monitor": monitor})
    return TestClient(app), auth, monitor


def register_key(auth, token, **overrides):
    options = {
        "user_id": "user-1",
        "workspace_id": "workspace-a",
        "role": "operator",
        "scopes": {"task_monitor:read"},
        "expires_at": time.time() + 3600,
    }
    options.update(overrides)
    auth.register_api_key(token, **options)


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def test_task_monitor_denies_anonymous_before_state_read():
    client, _, monitor = make_client()

    response = client.get("/api/v2/tasks/task-1/monitor")

    assert response.status_code == 401
    assert monitor.protected_reads("task-1") == 0


def test_task_monitor_denies_malformed_authorization_header():
    client, _, monitor = make_client()

    response = client.get(
        "/api/v2/tasks/task-1/monitor",
        headers={"Authorization": "Token not-bearer"},
    )

    assert response.status_code == 401
    assert monitor.protected_reads("task-1") == 0


def test_task_monitor_revalidates_revoked_key_on_every_poll():
    client, auth, monitor = make_client()
    register_key(auth, "live-token")

    first = client.get(
        "/api/v2/tasks/task-1/monitor",
        headers=auth_header("live-token"),
    )
    auth.revoke_api_key("live-token")
    second = client.get(
        "/api/v2/tasks/task-1/monitor",
        headers=auth_header("live-token"),
    )

    assert first.status_code == 200
    assert first.json()["protected_reads"] == 1
    assert second.status_code == 401
    assert monitor.protected_reads("task-1") == 1


def test_task_monitor_denies_disabled_and_expired_keys():
    client, auth, monitor = make_client()
    register_key(auth, "disabled-token", disabled=True)
    register_key(auth, "expired-token", expires_at=time.time() - 1)

    disabled = client.get(
        "/api/v2/tasks/task-1/monitor",
        headers=auth_header("disabled-token"),
    )
    expired = client.get(
        "/api/v2/tasks/task-1/monitor",
        headers=auth_header("expired-token"),
    )

    assert disabled.status_code == 401
    assert expired.status_code == 401
    assert monitor.protected_reads("task-1") == 0


def test_task_monitor_denies_missing_scope_role_and_workspace():
    client, auth, monitor = make_client()
    register_key(auth, "no-scope", scopes={"agents:read"})
    register_key(auth, "viewer", role="viewer")
    register_key(auth, "other-workspace", workspace_id="workspace-b")

    no_scope = client.get(
        "/api/v2/tasks/task-1/monitor",
        headers=auth_header("no-scope"),
    )
    viewer = client.get(
        "/api/v2/tasks/task-1/monitor",
        headers=auth_header("viewer"),
    )
    other_workspace = client.get(
        "/api/v2/tasks/task-1/monitor",
        headers=auth_header("other-workspace"),
    )

    assert no_scope.status_code == 403
    assert viewer.status_code == 403
    assert other_workspace.status_code == 403
    assert monitor.protected_reads("task-1") == 0


def test_task_monitor_allows_authorized_api_key_and_session_clients():
    client, auth, monitor = make_client()
    register_key(auth, "api-token")
    auth.register_session(
        "session-1",
        user_id="user-2",
        workspace_id="workspace-a",
        role="admin",
        scopes={"task_monitor:read"},
        expires_at=time.time() + 3600,
    )

    api_response = client.get(
        "/api/v2/tasks/task-1/monitor",
        headers=auth_header("api-token"),
    )
    client.cookies.set("ao_session", "session-1")
    session_response = client.get("/api/v2/tasks/task-1/monitor")

    assert api_response.status_code == 200
    assert api_response.json()["status"] == "running"
    assert session_response.status_code == 200
    assert session_response.json()["protected_reads"] == 2
    assert monitor.protected_reads("task-1") == 2
