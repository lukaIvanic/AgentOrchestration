"""Artifact ingestion service."""

import re
from dataclasses import dataclass
from typing import ClassVar, Dict, Optional, Pattern, Tuple


class ArtifactUploadError(ValueError):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass
class ArtifactIngestionService:
    max_body_bytes: int = 1024 * 1024
    _SAFE_ID: ClassVar[Pattern[str]] = re.compile(
        r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$"
    )

    def __post_init__(self):
        self._artifacts: Dict[Tuple[str, str], bytes] = {}
        self.protected_lookup_count = 0
        self.mutation_count = 0

    def upload(
        self,
        tenant_id: str,
        artifact_id: str,
        body: bytes,
        actor: str,
        declared_body_bytes: Optional[int] = None,
    ) -> Dict[str, object]:
        tenant_id, artifact_id = self.validate_upload_request(
            tenant_id,
            artifact_id,
            actor,
            declared_body_bytes=declared_body_bytes,
        )
        if not body:
            raise ArtifactUploadError(400, "artifact body required")
        if len(body) > self.max_body_bytes:
            raise ArtifactUploadError(413, "artifact body too large")

        key = (tenant_id, artifact_id)
        self.protected_lookup_count += 1
        existed = key in self._artifacts
        self._artifacts[key] = body
        self.mutation_count += 1
        return {
            "artifact_id": artifact_id,
            "tenant_id": tenant_id,
            "bytes": len(body),
            "created": not existed,
        }

    def validate_upload_request(
        self,
        tenant_id: str,
        artifact_id: str,
        actor: str,
        declared_body_bytes: Optional[int] = None,
    ) -> Tuple[str, str]:
        tenant_id = str(tenant_id or "").strip()
        artifact_id = str(artifact_id or "").strip()
        actor = str(actor or "").strip()
        if not actor:
            raise ArtifactUploadError(401, "Unauthorized")
        if not tenant_id or not artifact_id:
            raise ArtifactUploadError(
                400,
                "tenant_id and artifact_id required",
            )
        if not self._SAFE_ID.fullmatch(tenant_id):
            raise ArtifactUploadError(400, "invalid tenant_id")
        if not self._SAFE_ID.fullmatch(artifact_id):
            raise ArtifactUploadError(400, "invalid artifact_id")
        if declared_body_bytes is not None:
            if declared_body_bytes < 0:
                raise ArtifactUploadError(400, "invalid content length")
            if declared_body_bytes > self.max_body_bytes:
                raise ArtifactUploadError(413, "artifact body too large")
        return tenant_id, artifact_id


artifact_ingestion_service = ArtifactIngestionService()
