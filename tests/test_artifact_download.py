from fastapi.testclient import TestClient

from src.api.artifacts import artifact_service
from src.api.server import create_app


class TestArtifactDownload:
    def setup_method(self):
        artifact_service.reset()
        artifact_service.store(
            "workspace-a",
            "project-a",
            "artifact-1",
            b"report",
        )
        self.client = TestClient(create_app())

    def download(
        self,
        workspace_id="workspace-a",
        project_id="project-a",
        artifact_id="artifact-1",
        role="viewer",
        token="user-1",
    ):
        headers = {"X-Workspace-Role": role}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return self.client.get(
            (
                f"/api/v2/workspaces/{workspace_id}/projects/"
                f"{project_id}/artifacts/{artifact_id}"
            ),
            headers=headers,
        )

    def test_authorized_download_returns_artifact_metadata(self):
        response = self.download()

        assert response.status_code == 200
        assert response.json()["bytes"] == len(b"report")
        assert artifact_service.protected_lookup_count == 1
        assert artifact_service.download_count == 1

    def test_unauthorized_download_fails_before_lookup(self):
        response = self.download(token="")

        assert response.status_code == 401
        assert artifact_service.protected_lookup_count == 0
        assert artifact_service.download_count == 0

    def test_malformed_download_fails_before_lookup(self):
        response = self.download(artifact_id=" ")

        assert response.status_code == 400
        assert artifact_service.protected_lookup_count == 0
        assert artifact_service.download_count == 0

    def test_malformed_project_fails_before_lookup(self):
        response = self.download(project_id="bad project")

        assert response.status_code == 400
        assert artifact_service.protected_lookup_count == 0
        assert artifact_service.download_count == 0

    def test_cross_project_lookup_returns_404_before_lookup(self):
        response = self.download(project_id="project-b")

        assert response.status_code == 404
        assert artifact_service.protected_lookup_count == 0
        assert artifact_service.download_count == 0

    def test_missing_artifact_in_valid_project_404s_after_scoped_lookup(self):
        response = self.download(artifact_id="artifact-missing")

        assert response.status_code == 404
        assert artifact_service.protected_lookup_count == 1
        assert artifact_service.download_count == 0

    def test_insufficient_role_fails_before_lookup(self):
        response = self.download(role="disabled")

        assert response.status_code == 403
        assert artifact_service.protected_lookup_count == 0
        assert artifact_service.download_count == 0
