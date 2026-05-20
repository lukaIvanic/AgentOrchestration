"""Multi-architecture release manifest validation."""

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

import yaml


_DIGEST_RE = re.compile(r"^sha256:[0-9a-fA-F]{64}$")
_PASS_VALUES = {True, "pass", "passed", "success", "succeeded", "ok"}


class MultiArchManifestError(ValueError):
    """Raised when a release manifest is unsafe to publish."""


def load_digest_manifest(path: str) -> Dict[str, Any]:
    """Load a JSON or YAML digest validation manifest from disk."""

    manifest_path = Path(path)
    with manifest_path.open() as handle:
        if manifest_path.suffix.lower() in {".yaml", ".yml"}:
            data = yaml.safe_load(handle)
        else:
            data = json.load(handle)

    if not isinstance(data, dict):
        raise MultiArchManifestError("digest manifest must be an object")
    return data


def validate_architecture_digests(
    manifest: Mapping[str, Any],
    required_architectures: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    """Validate architecture digests before manifest push."""

    entries = _extract_entries(manifest)
    required = set(
        required_architectures
        or manifest.get("required_architectures")
        or []
    )
    seen = set()
    validated: List[Dict[str, Any]] = []
    errors: List[str] = []

    for index, entry in enumerate(entries):
        if not isinstance(entry, Mapping):
            errors.append(f"entry {index} must be an object")
            continue

        arch = str(
            entry.get("architecture") or entry.get("arch") or ""
        ).strip()
        digest = str(entry.get("digest") or "").strip()
        if not arch:
            errors.append(f"entry {index} is missing architecture")
            continue
        if arch in seen:
            errors.append(f"{arch}: duplicate architecture entry")
            continue
        seen.add(arch)

        if not _DIGEST_RE.match(digest):
            errors.append(f"{arch}: missing or invalid sha256 digest")
            continue

        gates = entry.get("validation") or entry.get("validations") or {}
        gate_errors = _validate_required_gates(arch, digest, gates)
        if gate_errors:
            errors.extend(gate_errors)
            continue

        validated.append(
            {
                "architecture": arch,
                "digest": digest,
                "validation": _normalize_gates(gates),
            }
        )

    missing = sorted(required - {entry["architecture"] for entry in validated})
    for arch in missing:
        errors.append(f"{arch}: missing validated architecture digest")

    if errors:
        raise MultiArchManifestError("; ".join(errors))
    return validated


def build_release_summary(
    validated_entries: Iterable[Mapping[str, Any]]
) -> str:
    """Build a digest and validation release summary."""

    lines = ["Architecture | Digest | Tests | Scan", "--- | --- | --- | ---"]
    sorted_entries = sorted(
        validated_entries,
        key=lambda item: str(item["architecture"]),
    )
    for entry in sorted_entries:
        gates = entry.get("validation") or {}
        lines.append(
            " | ".join(
                [
                    str(entry["architecture"]),
                    str(entry["digest"]),
                    str(gates.get("tests", "passed")),
                    str(gates.get("scan", "passed")),
                ]
            )
        )
    return "\n".join(lines)


def build_validated_manifest(
    validated_entries: Iterable[Mapping[str, Any]]
) -> Dict[str, Any]:
    """Build the manifest-push input from validated architecture digests."""

    images = []
    for entry in sorted(
        validated_entries,
        key=lambda item: str(item["architecture"]),
    ):
        images.append(
            {
                "architecture": str(entry["architecture"]),
                "digest": str(entry["digest"]),
            }
        )
    return {"images": images}


def write_validated_manifest(
    validated_entries: Iterable[Mapping[str, Any]],
    output_path: str,
) -> None:
    """Write only validated architecture digests for manifest publication."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(build_validated_manifest(validated_entries), indent=2)
        + "\n",
        encoding="utf8",
    )


def _extract_entries(manifest: Mapping[str, Any]) -> Sequence[Any]:
    entries = manifest.get("architectures")
    if entries is None:
        entries = manifest.get("images")
    if not isinstance(entries, list):
        raise MultiArchManifestError(
            "digest manifest must include an architectures or images list"
        )
    return entries


def _validate_required_gates(
    arch: str, digest: str, gates: Any
) -> List[str]:
    if not isinstance(gates, Mapping):
        return [f"{arch}: validation gates must be an object"]

    errors = []
    for gate_name in ("tests", "scan"):
        gate = gates.get(gate_name)
        if gate is None:
            errors.append(f"{arch}: missing {gate_name} validation")
            continue
        if not _gate_passed(gate):
            errors.append(f"{arch}: {gate_name} validation did not pass")
            continue
        gate_digest = _gate_digest(gate)
        if gate_digest and gate_digest != digest:
            errors.append(
                f"{arch}: {gate_name} digest does not match image digest"
            )
    return errors


def _gate_passed(gate: Any) -> bool:
    if isinstance(gate, Mapping):
        status = gate.get("status", gate.get("passed"))
    else:
        status = gate
    if isinstance(status, str):
        status = status.strip().lower()
    return status in _PASS_VALUES


def _gate_digest(gate: Any) -> Optional[str]:
    if isinstance(gate, Mapping):
        digest = gate.get("digest") or gate.get("image_digest")
        if digest:
            return str(digest).strip()
    return None


def _normalize_gates(gates: Mapping[str, Any]) -> Dict[str, str]:
    return {
        name: "passed"
        for name in ("tests", "scan")
        if _gate_passed(gates[name])
    }
