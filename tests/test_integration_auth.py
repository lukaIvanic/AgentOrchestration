import time

from fastapi.testclient import TestClient

from src.api.integration_auth import Principal, integration_auth_service
from src.api.server import create_app


class TestIntegrationAuth:
    def setup_method(self):
        integration_auth_service.reset()
        self.client = TestClient(create_app())

    def register(
        self,
        token="token-ok",
        **overrides,
    ):
        principal = Principal(
            user_id=overrides.pop("user_id", "user-1"),
            workspace_id=overrides.pop("workspace_id", "workspace-a"),
            role=overrides.pop("role", "admin"),
            scopes=overrides.pop("scopes", ["webhooks:manage"]),
            **overrides,
        )
        integration_auth_service.register_token(token, principal)
        return token

    def create(
        self,
        token=None,
        workspace_id="workspace-a",
        headers=None,
        cookies=None,
    ):
        headers = dict(headers or {})
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return self.client.post(
            f"/api/v2/workspaces/{workspace_id}/webhooks",
            params={"target_url": "https://example.com/hook"},
            headers=headers,
            cookies=cookies or {},
        )

    def test_authorized_webhook_manager_succeeds(self):
        token = self.register()

        response = self.create(token)

        assert response.status_code == 200
        assert response.json()["created_by"] == "user-1"
        assert integration_auth_service.protected_action_count == 1

    def test_anonymous_principal_is_denied_before_action(self):
        response = self.create()

        assert response.status_code == 401
        assert integration_auth_service.protected_action_count == 0

    def test_revoked_principal_is_denied_before_action(self):
        token = self.register(revoked=True)

        response = self.create(token)

        assert response.status_code == 401
        assert integration_auth_service.protected_action_count == 0

    def test_disabled_user_is_denied_before_webhook_management(self):
        token = self.register(disabled=True)

        response = self.create(token)

        assert response.status_code == 403
        assert response.json()["detail"] == "Disabled user denied"
        assert integration_auth_service.protected_action_count == 0

    def test_expired_principal_is_denied_before_action(self):
        token = self.register(expires_at=time.time() - 1)

        response = self.create(token)

        assert response.status_code == 401
        assert integration_auth_service.protected_action_count == 0

        retry = self.create(token)

        assert retry.status_code == 401
        assert retry.json()["detail"] == "Unknown integration token"
        assert integration_auth_service.protected_action_count == 0

    def test_insufficient_scope_is_denied_before_action(self):
        token = self.register(scopes=["webhooks:read"])

        response = self.create(token)

        assert response.status_code == 403
        assert integration_auth_service.protected_action_count == 0

    def test_insufficient_workspace_role_is_denied_before_action(self):
        token = self.register(role="viewer")

        response = self.create(token)

        assert response.status_code == 403
        assert integration_auth_service.protected_action_count == 0

    def test_disabled_integration_session_header_is_denied_before_action(self):
        token = self.register("session-disabled", disabled=True)

        response = self.create(
            headers={"X-Integration-Session": token},
        )

        assert response.status_code == 403
        assert response.json()["detail"] == "Disabled user denied"
        assert integration_auth_service.protected_action_count == 0

    def test_expired_browser_session_cookie_is_invalidated(self):
        token = self.register("session-expired", expires_at=time.time() - 1)

        response = self.create(cookies={"ao_session": token})

        assert response.status_code == 401
        assert integration_auth_service.protected_action_count == 0

        retry = self.create(cookies={"ao_session": token})

        assert retry.status_code == 401
        assert retry.json()["detail"] == "Unknown integration token"
        assert integration_auth_service.protected_action_count == 0

    def test_valid_session_header_overrides_stale_cookie(self):
        stale_cookie = self.register("session-stale-cookie", disabled=True)
        valid_session = self.register("session-valid-header")

        response = self.create(
            headers={"X-Integration-Session": valid_session},
            cookies={"ao_session": stale_cookie},
        )

        assert response.status_code == 200
        assert response.json()["created_by"] == "user-1"
        assert integration_auth_service.protected_action_count == 1
