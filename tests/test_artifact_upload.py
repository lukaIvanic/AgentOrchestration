from fastapi.testclient import TestClient

from src.api.artifacts import ArtifactUploadError, artifact_ingestion_service
from src.api.server import create_app


class TestArtifactUpload:
    def setup_method(self):
        artifact_ingestion_service.__post_init__()
        self.client = TestClient(create_app())

    def test_authorized_upload_records_artifact(self):
        response = self.client.post(
            "/api/v2/artifacts/report/upload?tenant_id=tenant-a",
            content=b"artifact-bytes",
            headers={"Authorization": "Bearer user-1"},
        )

        assert response.status_code == 200
        assert response.json()["bytes"] == len(b"artifact-bytes")
        assert artifact_ingestion_service.protected_lookup_count == 1
        assert artifact_ingestion_service.mutation_count == 1

    def test_unauthorized_upload_fails_before_lookup_or_mutation(self):
        response = self.client.post(
            "/api/v2/artifacts/report/upload?tenant_id=tenant-a",
            content=b"artifact-bytes",
        )

        assert response.status_code == 401
        assert artifact_ingestion_service.protected_lookup_count == 0
        assert artifact_ingestion_service.mutation_count == 0

    def test_malformed_upload_fails_before_lookup_or_mutation(self):
        response = self.client.post(
            "/api/v2/artifacts/report/upload?tenant_id=tenant-a",
            content=b"",
            headers={"Authorization": "Bearer user-1"},
        )

        assert response.status_code == 400
        assert artifact_ingestion_service.protected_lookup_count == 0
        assert artifact_ingestion_service.mutation_count == 0

    def test_oversized_upload_fails_before_lookup_or_mutation(self):
        body = b"x" * (artifact_ingestion_service.max_body_bytes + 1)

        response = self.client.post(
            "/api/v2/artifacts/report/upload?tenant_id=tenant-a",
            content=body,
            headers={"Authorization": "Bearer user-1"},
        )

        assert response.status_code == 413
        assert artifact_ingestion_service.protected_lookup_count == 0
        assert artifact_ingestion_service.mutation_count == 0

    def test_declared_oversized_upload_fails_before_body_handling(self):
        response = self.client.post(
            "/api/v2/artifacts/report/upload?tenant_id=tenant-a",
            content=b"x",
            headers={
                "Authorization": "Bearer user-1",
                "Content-Length": str(
                    artifact_ingestion_service.max_body_bytes + 1
                ),
            },
        )

        assert response.status_code == 413
        assert artifact_ingestion_service.protected_lookup_count == 0
        assert artifact_ingestion_service.mutation_count == 0

    def test_invalid_artifact_id_fails_before_lookup_or_mutation(self):
        response = self.client.post(
            "/api/v2/artifacts/bad@id/upload?tenant_id=tenant-a",
            content=b"artifact-bytes",
            headers={"Authorization": "Bearer user-1"},
        )

        assert response.status_code == 400
        assert artifact_ingestion_service.protected_lookup_count == 0
        assert artifact_ingestion_service.mutation_count == 0

    def test_workspace_upload_records_artifact(self):
        response = self.client.post(
            "/api/v2/workspaces/workspace-a/artifacts/report/upload",
            content=b"artifact-bytes",
            headers={"Authorization": "Bearer user-1"},
        )

        assert response.status_code == 200
        assert response.json()["tenant_id"] == "workspace-a"
        assert response.json()["bytes"] == len(b"artifact-bytes")
        assert artifact_ingestion_service.protected_lookup_count == 1
        assert artifact_ingestion_service.mutation_count == 1

    def test_declared_oversized_guard_is_in_shared_service(self):
        try:
            artifact_ingestion_service.validate_upload_request(
                tenant_id="tenant-a",
                artifact_id="report",
                actor="user-1",
                declared_body_bytes=(
                    artifact_ingestion_service.max_body_bytes + 1
                ),
            )
        except ArtifactUploadError as exc:
            assert exc.status_code == 413
        else:
            raise AssertionError("declared oversized upload was not rejected")

        assert artifact_ingestion_service.protected_lookup_count == 0
        assert artifact_ingestion_service.mutation_count == 0
