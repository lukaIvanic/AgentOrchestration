"""Validation for sidecar runtime compose hardening."""

from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml


class SidecarRuntimeError(ValueError):
    """Raised when a sidecar compose service is not runtime-hardened."""


def load_compose_file(path: str) -> Mapping[str, Any]:
    """Load a compose file and return its mapping structure."""

    with Path(path).open(encoding="utf-8") as compose_file:
        data = yaml.safe_load(compose_file)
    if not isinstance(data, Mapping):
        raise SidecarRuntimeError("compose file must contain a mapping")
    return data


def validate_sidecar_compose_file(path: str) -> None:
    """Validate sidecar services in a compose file."""

    validate_sidecar_services(load_compose_file(path))


def validate_sidecar_services(compose: Mapping[str, Any]) -> None:
    """Reject sidecars without read-only roots and explicit writable tmpfs."""

    services = compose.get("services")
    if not isinstance(services, Mapping):
        raise SidecarRuntimeError("compose services must be a mapping")

    violations = []
    for service_name, service in services.items():
        if not _is_sidecar(service_name, service):
            continue
        if not isinstance(service, Mapping):
            violations.append(f"{service_name}: service must be a mapping")
            continue

        if service.get("read_only") is not True:
            violations.append(f"{service_name}: read_only must be true")
        if not _valid_tmpfs(service.get("tmpfs")):
            violations.append(
                f"{service_name}: tmpfs must declare writable noexec paths "
                "with size limits"
            )
        if _has_writable_volume(service.get("volumes")):
            violations.append(
                f"{service_name}: volumes must be read-only; "
                "writable mounts belong in tmpfs"
            )
        if not _drops_all_capabilities(service.get("cap_drop")):
            violations.append(f"{service_name}: cap_drop must include ALL")
        if not _has_no_new_privileges(service.get("security_opt")):
            violations.append(
                f"{service_name}: security_opt must include "
                "no-new-privileges:true"
            )

    if violations:
        raise SidecarRuntimeError("; ".join(violations))


def _is_sidecar(name: str, service: Any) -> bool:
    if "sidecar" in name:
        return True
    if not isinstance(service, Mapping):
        return False

    labels = service.get("labels", {})
    if isinstance(labels, Mapping):
        return labels.get("ao.role") == "sidecar"
    if isinstance(labels, Iterable) and not isinstance(labels, (str, bytes)):
        return "ao.role=sidecar" in labels
    return False


def _valid_tmpfs(tmpfs: Any) -> bool:
    if not isinstance(tmpfs, list) or not tmpfs:
        return False
    return all(_valid_tmpfs_entry(entry) for entry in tmpfs)


def _valid_tmpfs_entry(entry: Any) -> bool:
    if not isinstance(entry, str):
        return False
    parts = [part.strip() for part in entry.split(":") if part.strip()]
    if len(parts) < 2 or not parts[0].startswith("/"):
        return False
    options = set()
    for option_group in parts[1:]:
        options.update(option.strip() for option in option_group.split(","))
    return (
        "rw" in options
        and "noexec" in options
        and "nosuid" in options
        and any(option.startswith("size=") for option in options)
    )


def _has_writable_volume(volumes: Any) -> bool:
    if volumes is None:
        return False
    if not isinstance(volumes, list):
        return True
    for volume in volumes:
        if isinstance(volume, str):
            parts = volume.split(":")
            if len(parts) < 3 or parts[-1] != "ro":
                return True
        elif isinstance(volume, Mapping):
            if volume.get("read_only") is not True:
                return True
        else:
            return True
    return False


def _drops_all_capabilities(cap_drop: Any) -> bool:
    return isinstance(cap_drop, list) and "ALL" in cap_drop


def _has_no_new_privileges(security_opt: Any) -> bool:
    return (
        isinstance(security_opt, list)
        and "no-new-privileges:true" in security_opt
    )
