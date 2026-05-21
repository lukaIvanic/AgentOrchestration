"""Workspace-scoped artifact service."""

import re
from dataclasses import dataclass
from typing import ClassVar, Dict, Pattern, Set, Tuple


class ArtifactAccessError(ValueError):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass
class StoredArtifact:
    workspace_id: str
    project_id: str
    artifact_id: str
    body: bytes


class ArtifactService:
    _SAFE_ID: ClassVar[Pattern[str]] = re.compile(
        r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$"
    )

    def __init__(self):
        self._artifacts: Dict[Tuple[str, str, str], StoredArtifact] = {}
        self._workspace_projects: Dict[str, Set[str]] = {}
        self.protected_lookup_count = 0
        self.download_count = 0

    def reset(self) -> None:
        self._artifacts.clear()
        self._workspace_projects.clear()
        self.protected_lookup_count = 0
        self.download_count = 0

    def store(
        self,
        workspace_id: str,
        project_id: str,
        artifact_id: str,
        body: bytes,
    ) -> None:
        workspace_id = str(workspace_id or "").strip()
        project_id = str(project_id or "").strip()
        artifact_id = str(artifact_id or "").strip()
        self._workspace_projects.setdefault(workspace_id, set()).add(
            project_id
        )
        self._artifacts[(workspace_id, project_id, artifact_id)] = (
            StoredArtifact(workspace_id, project_id, artifact_id, body)
        )

    def download(
        self,
        workspace_id: str,
        project_id: str,
        artifact_id: str,
        actor: str,
        role: str,
    ) -> Dict[str, object]:
        workspace_id = str(workspace_id or "").strip()
        project_id = str(project_id or "").strip()
        artifact_id = str(artifact_id or "").strip()
        actor = str(actor or "").strip()
        role = str(role or "").strip()
        if not actor:
            raise ArtifactAccessError(401, "Unauthorized")
        if not workspace_id or not project_id or not artifact_id:
            raise ArtifactAccessError(400, "Malformed artifact request")
        if not self._is_safe_id(workspace_id):
            raise ArtifactAccessError(400, "Malformed artifact request")
        if not self._is_safe_id(project_id):
            raise ArtifactAccessError(400, "Malformed artifact request")
        if not self._is_safe_id(artifact_id):
            raise ArtifactAccessError(400, "Malformed artifact request")
        if role not in {"admin", "operator", "viewer"}:
            raise ArtifactAccessError(403, "Insufficient workspace role")
        if project_id not in self._workspace_projects.get(workspace_id, set()):
            raise ArtifactAccessError(404, "Artifact not found")

        self.protected_lookup_count += 1
        artifact = self._artifacts.get((workspace_id, project_id, artifact_id))
        if not artifact:
            raise ArtifactAccessError(404, "Artifact not found")

        self.download_count += 1
        return {
            "artifact_id": artifact.artifact_id,
            "workspace_id": artifact.workspace_id,
            "project_id": artifact.project_id,
            "bytes": len(artifact.body),
        }

    def _is_safe_id(self, value: str) -> bool:
        return bool(self._SAFE_ID.fullmatch(value))


artifact_service = ArtifactService()
