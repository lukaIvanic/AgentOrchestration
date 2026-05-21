import time

from fastapi.testclient import TestClient

from src.api.auth import AuthService, build_principal
from src.api.server import create_app


def build_client() -> TestClient:
    now = time.time()
    auth_service = AuthService(
        {
            "admin-token": build_principal(
                "admin",
                {"workspace-a": "admin"},
                now + 3600,
                scopes={"agents:read", "agents:write"},
            ),
            "browser-token": build_principal(
                "browser-admin",
                {"workspace-a": "admin"},
                now + 3600,
                scopes={"agents:read", "agents:write"},
            ),
            "viewer-token": build_principal(
                "viewer",
                {"workspace-a": "viewer"},
                now + 3600,
                scopes={"agents:read"},
            ),
            "stale-token": build_principal(
                "stale",
                {"workspace-a": "admin"},
                now - 1,
                scopes={"agents:read", "agents:write"},
            ),
            "revoked-token": build_principal(
                "revoked",
                {"workspace-a": "admin"},
                now + 3600,
                scopes={"agents:read", "agents:write"},
                revoked=True,
            ),
        }
    )
    return TestClient(create_app({"auth_service": auth_service}))


def auth_headers(token: str, workspace_id: str = "workspace-a") -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "X-Workspace-ID": workspace_id,
    }


class TestApiAuth:
    def test_anonymous_trailing_slash_request_fails_closed(self):
        response = build_client().get(
            "/api/v2/agents/",
            follow_redirects=False,
        )

        assert response.status_code == 401
        assert "location" not in response.headers

    def test_malformed_token_client_is_denied(self):
        response = build_client().get(
            "/api/v2/agents",
            headers={
                "Authorization": "Bearer",
                "X-Workspace-ID": "workspace-a",
            },
        )

        assert response.status_code == 401

    def test_stale_token_is_denied_before_route_handling(self):
        response = build_client().get(
            "/api/v2/agents",
            headers=auth_headers("stale-token"),
        )

        assert response.status_code == 401

    def test_revoked_token_is_denied_before_route_handling(self):
        response = build_client().get(
            "/api/v2/agents",
            headers=auth_headers("revoked-token"),
        )

        assert response.status_code == 401

    def test_insufficient_workspace_role_is_denied_for_mutation(self):
        response = build_client().post(
            "/api/v2/agents",
            params={"name": "worker", "agent_type": "worker.processor"},
            headers=auth_headers("viewer-token"),
        )

        assert response.status_code == 403

    def test_wrong_workspace_is_denied(self):
        response = build_client().get(
            "/api/v2/agents",
            headers=auth_headers("admin-token", workspace_id="workspace-b"),
        )

        assert response.status_code == 403

    def test_authorized_token_client_can_complete_workflow(self):
        client = build_client()

        created = client.post(
            "/api/v2/agents",
            params={"name": "worker", "agent_type": "worker.processor"},
            headers=auth_headers("admin-token"),
        )
        assert created.status_code == 200
        agent_id = created.json()["agent_id"]

        fetched = client.get(
            f"/api/v2/agents/{agent_id}",
            headers=auth_headers("admin-token"),
        )
        assert fetched.status_code == 200
        assert fetched.json()["name"] == "worker"

    def test_authorized_browser_session_can_complete_workflow(self):
        client = build_client()

        response = client.get(
            "/api/v2/agents",
            cookies={"ao_session": "browser-token"},
            headers={"X-Workspace-ID": "workspace-a"},
        )

        assert response.status_code == 200
        assert "agents" in response.json()
