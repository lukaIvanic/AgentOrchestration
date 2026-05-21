"""Database migration gates for application rollout."""

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping

import yaml


_PASS_VALUES = {
    True,
    "applied",
    "complete",
    "completed",
    "ok",
    "passed",
    "success",
    "succeeded",
}


class MigrationGateError(ValueError):
    """Raised when a release must not roll forward."""


def load_release_manifest(path: str) -> Dict[str, Any]:
    """Load a JSON or YAML release manifest."""

    manifest_path = Path(path)
    with manifest_path.open(encoding="utf8") as handle:
        if manifest_path.suffix.lower() in {".yaml", ".yml"}:
            data = yaml.safe_load(handle)
        else:
            data = json.load(handle)

    if not isinstance(data, dict):
        raise MigrationGateError("release manifest must be an object")
    return data


def evaluate_migration_gate(manifest: Mapping[str, Any]) -> Dict[str, Any]:
    """Evaluate whether application rollout can receive traffic."""

    migrations = _migration_entries(manifest)
    result_overrides = _migration_results(manifest)
    reversible = _release_is_reversible(manifest)
    errors: List[str] = []
    compatibility = []
    audit_events = []

    for index, migration in enumerate(migrations):
        if not isinstance(migration, Mapping):
            errors.append(f"migration {index} must be an object")
            audit_events.append(
                _audit_event(
                    "migration_rejected",
                    f"migration-{index}",
                    "invalid migration record",
                )
            )
            continue

        name = str(
            migration.get("name")
            or migration.get("id")
            or f"migration-{index}"
        ).strip()
        status = _effective_status(name, migration, result_overrides)
        if not _passed(status):
            errors.append(f"{name}: migration status is not successful")
            audit_events.append(
                _audit_event(
                    "migration_rejected",
                    name,
                    "migration status is not successful",
                )
            )
        else:
            audit_events.append(
                _audit_event("migration_completed", name, "status passed")
            )

        has_compatibility_check = _has_compatibility_check(migration)
        backward_compatible = _is_backward_compatible(migration)
        compatibility.append(
            {
                "name": name,
                "backward_compatible": backward_compatible,
                "checked": has_compatibility_check,
            }
        )

        if reversible and not has_compatibility_check:
            errors.append(f"{name}: missing backward compatibility check")
            audit_events.append(
                _audit_event(
                    "migration_rejected",
                    name,
                    "missing backward compatibility check",
                )
            )
        elif reversible and not backward_compatible:
            errors.append(
                f"{name}: not backward compatible for reversible release"
            )
            audit_events.append(
                _audit_event(
                    "migration_rejected",
                    name,
                    "not backward compatible for reversible release",
                )
            )
        elif has_compatibility_check:
            audit_events.append(
                _audit_event(
                    "compatibility_checked",
                    name,
                    "backward compatible"
                    if backward_compatible
                    else "not backward compatible",
                )
            )

    traffic_allowed = not errors
    audit_events.append(
        {
            "event": "rollout_decision",
            "decision": (
                "allow_traffic" if traffic_allowed else "keep_prior_version"
            ),
            "migration_count": len(migrations),
            "reversible": reversible,
        }
    )
    return {
        "traffic_allowed": traffic_allowed,
        "prior_version_serving": not traffic_allowed,
        "reversible": reversible,
        "compatibility": compatibility,
        "errors": errors,
        "audit_events": audit_events,
    }


def build_migration_summary(result: Mapping[str, Any]) -> str:
    """Build a concise release-gate summary for logs and CI output."""

    lines = [
        f"Traffic allowed: {'yes' if result.get('traffic_allowed') else 'no'}",
        "Prior version serving: "
        f"{'yes' if result.get('prior_version_serving') else 'no'}",
        f"Reversible release: {'yes' if result.get('reversible') else 'no'}",
    ]

    compatibility = result.get("compatibility") or []
    if compatibility:
        lines.append("Migration compatibility:")
        for item in compatibility:
            status = (
                "backward-compatible"
                if item["backward_compatible"]
                else "not backward-compatible"
            )
            checked = "checked" if item["checked"] else "unchecked"
            lines.append(f"- {item['name']}: {status} ({checked})")

    errors = result.get("errors") or []
    if errors:
        lines.append("Blocked rollout:")
        lines.extend(f"- {error}" for error in errors)
    return "\n".join(lines)


def _audit_event(
    event: str,
    migration_name: str,
    reason: str,
) -> Dict[str, Any]:
    return {
        "event": event,
        "migration": migration_name,
        "reason": reason,
    }


def _migration_entries(manifest: Mapping[str, Any]) -> List[Any]:
    migrations = manifest.get(
        "migrations",
        manifest.get("database_migrations", []),
    )
    if migrations is None:
        return []
    if not isinstance(migrations, list):
        raise MigrationGateError("migrations must be a list")
    return migrations


def _migration_results(manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    results = manifest.get("migration_results", {})
    if results is None:
        return {}
    if not isinstance(results, Mapping):
        raise MigrationGateError("migration_results must be an object")
    return results


def _release_is_reversible(manifest: Mapping[str, Any]) -> bool:
    release = manifest.get("release", {})
    rollout = manifest.get("rollout", {})
    for section in (release, rollout):
        if isinstance(section, Mapping) and "reversible" in section:
            return bool(section["reversible"])
    return bool(manifest.get("reversible", False))


def _effective_status(
    name: str,
    migration: Mapping[str, Any],
    results: Mapping[str, Any],
) -> Any:
    override = results.get(name)
    if isinstance(override, Mapping):
        return override.get("status", override.get("passed"))
    if override is not None:
        return override
    return migration.get("status", migration.get("passed"))


def _passed(status: Any) -> bool:
    if isinstance(status, str):
        status = status.strip().lower()
    return status in _PASS_VALUES


def _has_compatibility_check(migration: Mapping[str, Any]) -> bool:
    compatibility = migration.get("compatibility")
    if "backward_compatible" in migration or "backwardCompatible" in migration:
        return True
    return (
        isinstance(compatibility, Mapping)
        and "backward_compatible" in compatibility
    )


def _is_backward_compatible(migration: Mapping[str, Any]) -> bool:
    compatibility = migration.get("compatibility")
    if (
        isinstance(compatibility, Mapping)
        and "backward_compatible" in compatibility
    ):
        return bool(compatibility["backward_compatible"])
    if "backward_compatible" in migration:
        return bool(migration["backward_compatible"])
    if "backwardCompatible" in migration:
        return bool(migration["backwardCompatible"])
    return False
