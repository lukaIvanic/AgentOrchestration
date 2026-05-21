import time

from fastapi.testclient import TestClient

from src.api.server import create_app
from src.api.templates import Principal, template_clone_service


class TestTemplateCloneAuth:
    def setup_method(self):
        template_clone_service.reset()
        template_clone_service.register_template(
            "workspace-1",
            "template-1",
            {"agent_type": "worker.processor"},
        )
        template_clone_service.register_principal(
            "good-token",
            Principal(
                principal_id="user-1",
                workspace_id="workspace-1",
                role="editor",
                scopes=["templates:clone"],
            ),
        )
        self.client = TestClient(create_app())

    def test_authorized_editor_can_clone_template(self):
        response = self.client.post(
            "/api/v2/workspaces/workspace-1/templates/template-1/clone",
            headers={"Authorization": "Bearer good-token"},
            json={"name": "copied-template"},
        )

        assert response.status_code == 200
        assert response.json()["name"] == "copied-template"
        assert template_clone_service.template_read_count == 1
        assert template_clone_service.clone_mutation_count == 1
        assert template_clone_service.audit_events[-1]["decision"] == (
            "clone_created"
        )

    def test_unknown_token_fails_before_template_read_or_mutation(self):
        response = self.client.post(
            "/api/v2/workspaces/workspace-1/templates/template-1/clone",
            headers={"Authorization": "Bearer missing-token"},
            json={"name": "copy"},
        )

        assert response.status_code == 401
        assert template_clone_service.template_read_count == 0
        assert template_clone_service.clone_mutation_count == 0
        assert template_clone_service.audit_events[-1]["decision"] == (
            "unknown_token"
        )

    def test_revoked_principal_fails_before_template_read_or_mutation(self):
        template_clone_service.register_principal(
            "revoked-token",
            Principal(
                principal_id="user-2",
                workspace_id="workspace-1",
                role="admin",
                scopes=["templates:clone"],
                revoked=True,
            ),
        )

        response = self.client.post(
            "/api/v2/workspaces/workspace-1/templates/template-1/clone",
            headers={"Authorization": "Bearer revoked-token"},
            json={"name": "copy"},
        )

        assert response.status_code == 401
        assert template_clone_service.template_read_count == 0
        assert template_clone_service.clone_mutation_count == 0
        assert template_clone_service.audit_events[-1]["decision"] == (
            "inactive_principal"
        )

    def test_expired_principal_fails_before_template_read_or_mutation(self):
        template_clone_service.register_principal(
            "expired-token",
            Principal(
                principal_id="user-3",
                workspace_id="workspace-1",
                role="admin",
                scopes=["templates:clone"],
                expires_at=time.time() - 1,
            ),
        )

        response = self.client.post(
            "/api/v2/workspaces/workspace-1/templates/template-1/clone",
            headers={"Authorization": "Bearer expired-token"},
            json={"name": "copy"},
        )

        assert response.status_code == 401
        assert template_clone_service.template_read_count == 0
        assert template_clone_service.clone_mutation_count == 0
        assert template_clone_service.audit_events[-1]["decision"] == (
            "expired_principal"
        )

    def test_wrong_workspace_fails_before_template_read_or_mutation(self):
        template_clone_service.register_principal(
            "wrong-workspace-token",
            Principal(
                principal_id="user-4",
                workspace_id="workspace-2",
                role="admin",
                scopes=["templates:clone"],
            ),
        )

        response = self.client.post(
            "/api/v2/workspaces/workspace-1/templates/template-1/clone",
            headers={"Authorization": "Bearer wrong-workspace-token"},
            json={"name": "copy"},
        )

        assert response.status_code == 403
        assert template_clone_service.template_read_count == 0
        assert template_clone_service.clone_mutation_count == 0
        assert template_clone_service.audit_events[-1]["decision"] == (
            "wrong_workspace"
        )

    def test_missing_scope_fails_before_template_read_or_mutation(self):
        template_clone_service.register_principal(
            "missing-scope-token",
            Principal(
                principal_id="user-5",
                workspace_id="workspace-1",
                role="admin",
                scopes=["templates:read"],
            ),
        )

        response = self.client.post(
            "/api/v2/workspaces/workspace-1/templates/template-1/clone",
            headers={"Authorization": "Bearer missing-scope-token"},
            json={"name": "copy"},
        )

        assert response.status_code == 403
        assert template_clone_service.template_read_count == 0
        assert template_clone_service.clone_mutation_count == 0
        assert template_clone_service.audit_events[-1]["decision"] == (
            "missing_scope"
        )

    def test_viewer_role_fails_before_template_read_or_mutation(self):
        template_clone_service.register_principal(
            "viewer-token",
            Principal(
                principal_id="user-6",
                workspace_id="workspace-1",
                role="viewer",
                scopes=["templates:clone"],
            ),
        )

        response = self.client.post(
            "/api/v2/workspaces/workspace-1/templates/template-1/clone",
            headers={"Authorization": "Bearer viewer-token"},
            json={"name": "copy"},
        )

        assert response.status_code == 403
        assert template_clone_service.template_read_count == 0
        assert template_clone_service.clone_mutation_count == 0
        assert template_clone_service.audit_events[-1]["decision"] == (
            "insufficient_role"
        )
