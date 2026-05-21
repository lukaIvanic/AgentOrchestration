import time

from fastapi.testclient import TestClient

from src.api.server import create_app


def client():
    return TestClient(create_app())


def test_protected_route_rejects_anonymous_before_handler():
    response = client().get("/api/v2/agents")

    assert response.status_code == 401


def test_trailing_slash_protected_route_rejects_anonymous_before_redirect():
    response = client().get("/api/v2/agents/", follow_redirects=False)

    assert response.status_code == 401


def test_rejects_malformed_bearer_token():
    response = client().get(
        "/api/v2/agents",
        headers={"Authorization": "Token bad"},
    )

    assert response.status_code == 401


def test_rejects_stale_browser_session_cookie():
    response = client().get(
        "/api/v2/agents",
        cookies={"ao_session": "browser-session"},
        headers={"X-Session-Expires-At": str(time.time() - 1)},
    )

    assert response.status_code == 401


def test_rejects_revoked_token(monkeypatch):
    monkeypatch.setenv("REVOKED_API_TOKENS", "known-bad")

    response = client().get(
        "/api/v2/agents",
        headers={"Authorization": "Bearer known-bad"},
    )

    assert response.status_code == 401


def test_rejects_read_only_token_for_mutation(monkeypatch):
    monkeypatch.setenv("API_TOKEN_SCOPES", "reader=read")

    response = client().post(
        "/api/v2/agents",
        params={"name": "worker-1", "agent_type": "worker.processor"},
        headers={
            "Authorization": "Bearer reader",
            "X-Workspace-Role": "admin",
        },
    )

    assert response.status_code == 403


def test_rejects_insufficient_workspace_role_for_mutation():
    response = client().post(
        "/api/v2/agents",
        params={"name": "worker-1", "agent_type": "worker.processor"},
        headers={
            "Authorization": "Bearer valid-token",
            "X-Workspace-Role": "viewer",
        },
    )

    assert response.status_code == 403


def test_rejects_wrong_workspace_for_token(monkeypatch):
    monkeypatch.setenv("API_TOKEN_WORKSPACES", "valid-token=workspace-a")

    response = client().get(
        "/api/v2/agents",
        headers={
            "Authorization": "Bearer valid-token",
            "X-Workspace-Id": "workspace-b",
        },
    )

    assert response.status_code == 403


def test_authorized_token_read_and_write_still_work():
    test_client = client()

    create_response = test_client.post(
        "/api/v2/agents",
        params={"name": "worker-1", "agent_type": "worker.processor"},
        headers={
            "Authorization": "Bearer valid-token",
            "X-Workspace-Role": "editor",
        },
    )
    list_response = test_client.get(
        "/api/v2/agents",
        headers={"Authorization": "Bearer valid-token"},
    )

    assert create_response.status_code == 200
    assert create_response.json()["status"] == "registered"
    assert list_response.status_code == 200
    assert len(list_response.json()["agents"]) >= 1


def test_authorized_browser_session_read_still_works():
    response = client().get(
        "/api/v2/agents",
        cookies={"ao_session": "browser-session"},
    )

    assert response.status_code == 200
