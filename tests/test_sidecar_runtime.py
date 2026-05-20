import pytest

from src.agent.sidecar_runtime import (
    SidecarRuntimeError,
    load_compose_file,
    validate_sidecar_services,
)


def test_repo_sidecars_use_read_only_roots_with_explicit_tmpfs():
    compose = load_compose_file("infra/docker-compose.yml")

    validate_sidecar_services(compose)


def test_rejects_sidecar_without_read_only_root():
    compose = {
        "services": {
            "metrics-sidecar": {
                "image": "busybox:1.36",
                "tmpfs": ["/tmp/ao:rw,noexec,nosuid,size=8m"],
                "cap_drop": ["ALL"],
                "security_opt": ["no-new-privileges:true"],
            }
        }
    }

    with pytest.raises(SidecarRuntimeError, match="read_only must be true"):
        validate_sidecar_services(compose)


def test_rejects_sidecar_without_bounded_noexec_tmpfs():
    compose = {
        "services": {
            "log-forwarder": {
                "image": "busybox:1.36",
                "labels": {"ao.role": "sidecar"},
                "read_only": True,
                "tmpfs": ["/tmp/ao"],
                "cap_drop": ["ALL"],
                "security_opt": ["no-new-privileges:true"],
            }
        }
    }

    with pytest.raises(SidecarRuntimeError, match="tmpfs"):
        validate_sidecar_services(compose)


def test_rejects_writable_sidecar_bind_mounts():
    compose = {
        "services": {
            "metrics-sidecar": {
                "image": "busybox:1.36",
                "read_only": True,
                "tmpfs": ["/tmp/ao:rw,noexec,nosuid,size=8m"],
                "volumes": ["metrics-cache:/cache"],
                "cap_drop": ["ALL"],
                "security_opt": ["no-new-privileges:true"],
            }
        }
    }

    with pytest.raises(SidecarRuntimeError, match="volumes must be read-only"):
        validate_sidecar_services(compose)


def test_rejects_sidecar_without_runtime_privilege_guards():
    compose = {
        "services": {
            "metrics-sidecar": {
                "image": "busybox:1.36",
                "read_only": True,
                "tmpfs": ["/tmp/ao:rw,noexec,nosuid,size=8m"],
            }
        }
    }

    with pytest.raises(SidecarRuntimeError, match="cap_drop.*security_opt"):
        validate_sidecar_services(compose)


def test_ignores_non_sidecar_services():
    compose = {
        "services": {
            "agent-worker": {
                "image": "python:3.11-slim",
                "volumes": ["workspace:/workspace"],
            }
        }
    }

    validate_sidecar_services(compose)
