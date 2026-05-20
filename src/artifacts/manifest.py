"""Artifact manifest reader with digest integrity enforcement."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Optional


@dataclass(frozen=True)
class IntegrityAlert:
    artifact_id: str
    blob_path: str
    expected_digest: str
    actual_digest: str
    alert_type: str = "artifact_digest_mismatch"
    severity: str = "critical"

    def as_dict(self) -> Dict[str, str]:
        return {
            "alert_type": self.alert_type,
            "severity": self.severity,
            "artifact_id": self.artifact_id,
            "blob_path": self.blob_path,
            "expected_digest": self.expected_digest,
            "actual_digest": self.actual_digest,
        }


class ArtifactIntegrityError(Exception):
    def __init__(self, alert: IntegrityAlert):
        super().__init__(
            "Artifact digest mismatch for "
            f"{alert.artifact_id}: expected {alert.expected_digest}, "
            f"got {alert.actual_digest}"
        )
        self.alert = alert


class QuarantinedArtifactError(Exception):
    def __init__(self, blob_path: Path):
        super().__init__(f"Artifact blob is quarantined: {blob_path}")
        self.blob_path = blob_path


class QuarantineStore:
    def __init__(self):
        self._quarantined: Dict[Path, IntegrityAlert] = {}

    def quarantine(self, blob_path: Path, alert: IntegrityAlert) -> None:
        self._quarantined[blob_path.resolve()] = alert

    def is_quarantined(self, blob_path: Path) -> bool:
        return blob_path.resolve() in self._quarantined

    def alert_for(self, blob_path: Path) -> Optional[IntegrityAlert]:
        return self._quarantined.get(blob_path.resolve())


class ArtifactManifestReader:
    def __init__(
        self,
        root: Path,
        alert_sink: Optional[Callable[[IntegrityAlert], None]] = None,
        quarantine_store: Optional[QuarantineStore] = None,
    ):
        self.root = Path(root)
        self.alert_sink = alert_sink or (lambda alert: None)
        self.quarantine_store = quarantine_store or QuarantineStore()

    def read(self, manifest_path: Path) -> bytes:
        manifest_file = self._resolve_path(manifest_path)
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        blob_path = self._resolve_blob_path(
            manifest_file,
            manifest["blob_path"],
        )

        if self.quarantine_store.is_quarantined(blob_path):
            raise QuarantinedArtifactError(blob_path)

        content = blob_path.read_bytes()
        expected_digest = self._normalize_digest(manifest["digest"])
        actual_digest = hashlib.sha256(content).hexdigest()

        if actual_digest != expected_digest:
            alert = IntegrityAlert(
                artifact_id=manifest.get("artifact_id", manifest_file.stem),
                blob_path=str(blob_path),
                expected_digest=expected_digest,
                actual_digest=actual_digest,
            )
            self.quarantine_store.quarantine(blob_path, alert)
            self.alert_sink(alert)
            raise ArtifactIntegrityError(alert)

        return content

    def _resolve_path(self, path: Path) -> Path:
        path = Path(path)
        if path.is_absolute():
            return path
        return self.root / path

    def _resolve_blob_path(self, manifest_file: Path, blob_path: str) -> Path:
        path = Path(blob_path)
        if path.is_absolute():
            return path
        return manifest_file.parent / path

    def _normalize_digest(self, digest: str) -> str:
        if digest.startswith("sha256:"):
            return digest.split(":", 1)[1]
        return digest
