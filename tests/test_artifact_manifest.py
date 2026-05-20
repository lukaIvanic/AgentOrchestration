import hashlib
import json

import pytest

from src.artifacts import (
    ArtifactIntegrityError,
    ArtifactManifestReader,
    QuarantinedArtifactError,
    QuarantineStore,
)


def write_manifest(tmp_path, digest):
    manifest = {
        "artifact_id": "artifact-123",
        "blob_path": "blob.bin",
        "digest": digest,
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path


def test_manifest_reader_returns_content_when_digest_matches(tmp_path):
    blob = tmp_path / "blob.bin"
    blob.write_bytes(b"valid artifact")
    digest = hashlib.sha256(b"valid artifact").hexdigest()
    manifest_path = write_manifest(tmp_path, f"sha256:{digest}")
    alerts = []

    reader = ArtifactManifestReader(tmp_path, alert_sink=alerts.append)

    assert reader.read(manifest_path) == b"valid artifact"
    assert alerts == []


def test_digest_mismatch_emits_integrity_alert_and_quarantines_blob(tmp_path):
    blob = tmp_path / "blob.bin"
    blob.write_bytes(b"tampered artifact")
    manifest_path = write_manifest(tmp_path, "sha256:" + "0" * 64)
    alerts = []
    quarantine_store = QuarantineStore()
    reader = ArtifactManifestReader(
        tmp_path,
        alert_sink=alerts.append,
        quarantine_store=quarantine_store,
    )

    with pytest.raises(ArtifactIntegrityError) as exc_info:
        reader.read(manifest_path)

    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.alert_type == "artifact_digest_mismatch"
    assert alert.severity == "critical"
    assert alert.artifact_id == "artifact-123"
    assert alert.expected_digest == "0" * 64
    actual_digest = hashlib.sha256(b"tampered artifact").hexdigest()
    assert alert.actual_digest == actual_digest
    assert exc_info.value.alert == alert
    assert quarantine_store.is_quarantined(blob)


def test_quarantined_blob_is_blocked_before_cache_reuse(tmp_path):
    blob = tmp_path / "blob.bin"
    blob.write_bytes(b"tampered artifact")
    manifest_path = write_manifest(tmp_path, "sha256:" + "0" * 64)
    quarantine_store = QuarantineStore()
    reader = ArtifactManifestReader(
        tmp_path,
        quarantine_store=quarantine_store,
    )

    with pytest.raises(ArtifactIntegrityError):
        reader.read(manifest_path)

    with pytest.raises(QuarantinedArtifactError):
        reader.read(manifest_path)
