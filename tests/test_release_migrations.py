import subprocess
import sys

import pytest

from src.release.migrations import (
    MigrationGateError,
    build_migration_summary,
    evaluate_migration_gate,
    load_release_manifest,
)


def test_completed_compatible_migrations_allow_traffic():
    result = evaluate_migration_gate(
        {
            "release": {"reversible": True},
            "migrations": [
                {
                    "name": "001_add_task_attempt",
                    "status": "completed",
                    "backward_compatible": True,
                }
            ],
        }
    )

    assert result["traffic_allowed"] is True
    assert result["prior_version_serving"] is False
    assert result["compatibility"] == [
        {
            "name": "001_add_task_attempt",
            "backward_compatible": True,
            "checked": True,
        }
    ]


def test_failed_migration_blocks_rollout_and_keeps_prior_version():
    result = evaluate_migration_gate(
        {
            "release": {"reversible": True},
            "migrations": [
                {
                    "name": "002_backfill_state",
                    "status": "failed",
                    "backward_compatible": True,
                }
            ],
        }
    )

    assert result["traffic_allowed"] is False
    assert result["prior_version_serving"] is True
    assert (
        "002_backfill_state: migration status is not successful"
        in result["errors"]
    )
    assert "Prior version serving: yes" in build_migration_summary(result)


def test_reversible_release_requires_compatibility_check():
    result = evaluate_migration_gate(
        {
            "release": {"reversible": True},
            "migrations": [
                {"name": "003_drop_legacy_column", "status": "completed"}
            ],
        }
    )

    assert result["traffic_allowed"] is False
    assert (
        "003_drop_legacy_column: missing backward compatibility check"
        in result["errors"]
    )


def test_reversible_release_blocks_non_compatible_migration():
    result = evaluate_migration_gate(
        {
            "release": {"reversible": True},
            "migrations": [
                {
                    "name": "004_rename_state_column",
                    "status": "completed",
                    "compatibility": {"backward_compatible": False},
                }
            ],
        }
    )

    assert result["traffic_allowed"] is False
    assert (
        "004_rename_state_column: not backward compatible for "
        "reversible release"
        in result["errors"]
    )


def test_migration_results_override_manifest_status():
    result = evaluate_migration_gate(
        {
            "release": {"reversible": True},
            "migrations": [
                {
                    "name": "005_expand_task_state",
                    "status": "pending",
                    "backwardCompatible": True,
                }
            ],
            "migration_results": {
                "005_expand_task_state": {"status": "succeeded"}
            },
        }
    )

    assert result["traffic_allowed"] is True


def test_load_manifest_rejects_non_object(tmp_path):
    path = tmp_path / "release.yaml"
    path.write_text("- not-an-object\n")

    with pytest.raises(MigrationGateError, match="release manifest"):
        load_release_manifest(str(path))


def test_cli_deploy_stops_before_traffic_on_migration_failure(tmp_path):
    manifest = tmp_path / "release.yaml"
    manifest.write_text(
        """
release:
  reversible: true
migrations:
  - name: 006_schema_change
    status: failed
    backward_compatible: true
""".lstrip()
    )

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.cli.main",
            "deploy",
            str(manifest),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    assert "Traffic allowed: no" in completed.stdout
    assert "Prior version serving: yes" in completed.stdout
    assert (
        "Rollout stopped before new application pods receive traffic"
        in completed.stderr
    )
