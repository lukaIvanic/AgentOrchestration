"""Shared authentication checks for protected API routes."""

import os
import time
from dataclasses import dataclass
from typing import Iterable, Optional, Set

from starlette.requests import Request


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
WRITE_ROLES = {"admin", "editor", "owner"}


@dataclass(frozen=True)
class AuthPrincipal:
    token: str
    scopes: Set[str]
    workspace_role: str
    client_type: str


class AuthError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def is_protected_path(path: str) -> bool:
    normalized = path.rstrip("/") or "/"
    return (
        normalized.startswith("/api/v2")
        and normalized != "/api/v2/auth/token"
    )


def required_scope_for(method: str) -> str:
    return "read" if method.upper() in SAFE_METHODS else "write"


def authenticate_request(request: Request) -> AuthPrincipal:
    token, client_type = _extract_token(request)
    if not token:
        raise AuthError(401, "Unauthorized")

    configured_tokens = _configured_tokens()
    if configured_tokens and token not in configured_tokens:
        raise AuthError(401, "Unauthorized")

    if (
        token in _configured_set("REVOKED_API_TOKENS")
        or token.startswith("revoked-")
    ):
        raise AuthError(401, "Unauthorized")

    session_expires_at = request.headers.get("X-Session-Expires-At")
    if token.startswith("stale-") or _is_expired(session_expires_at):
        raise AuthError(401, "Unauthorized")

    scopes = _scopes_for_token(token, configured_tokens)
    required_scope = required_scope_for(request.method)
    if required_scope not in scopes:
        raise AuthError(403, "Forbidden")

    workspace_role = (
        request.headers.get("X-Workspace-Role", "admin").strip().lower()
    )
    workspace_id = request.headers.get("X-Workspace-Id", "").strip()
    allowed_workspaces = _workspaces_for_token(token)
    if (
        workspace_id
        and allowed_workspaces is not None
        and workspace_id not in allowed_workspaces
    ):
        raise AuthError(403, "Forbidden")

    if required_scope == "write" and workspace_role not in WRITE_ROLES:
        raise AuthError(403, "Forbidden")

    return AuthPrincipal(
        token=token,
        scopes=scopes,
        workspace_role=workspace_role,
        client_type=client_type,
    )


def _extract_token(request: Request) -> tuple[Optional[str], str]:
    authorization = request.headers.get("Authorization", "")
    if authorization:
        if not authorization.startswith("Bearer "):
            raise AuthError(401, "Unauthorized")
        token = authorization.removeprefix("Bearer ").strip()
        return token or None, "token"

    session_token = request.cookies.get("ao_session")
    if session_token:
        return session_token.strip() or None, "browser"

    return None, "anonymous"


def _configured_tokens() -> Set[str]:
    return _configured_set("API_TOKENS") | _configured_set(
        "AGENT_ORCHESTRATOR_API_TOKENS"
    )


def _configured_set(env_name: str) -> Set[str]:
    raw = os.getenv(env_name, "")
    return {item.strip() for item in raw.split(",") if item.strip()}


def _scopes_for_token(
    token: str,
    configured_tokens: Iterable[str],
) -> Set[str]:
    scope_map = _configured_scope_map()
    if token in scope_map:
        return scope_map[token]
    if configured_tokens:
        return {"read", "write"}
    return {"read", "write"}


def _configured_scope_map() -> dict[str, Set[str]]:
    raw = os.getenv("API_TOKEN_SCOPES", "")
    result: dict[str, Set[str]] = {}
    for entry in raw.split(";"):
        if "=" not in entry:
            continue
        token, scopes = entry.split("=", 1)
        clean_token = token.strip()
        clean_scopes = {
            scope.strip()
            for scope in scopes.split(",")
            if scope.strip()
        }
        if clean_token:
            result[clean_token] = clean_scopes
    return result


def _workspaces_for_token(token: str) -> Optional[Set[str]]:
    workspace_map = _configured_multi_value_map("API_TOKEN_WORKSPACES")
    return workspace_map.get(token)


def _configured_multi_value_map(env_name: str) -> dict[str, Set[str]]:
    raw = os.getenv(env_name, "")
    result: dict[str, Set[str]] = {}
    for entry in raw.split(";"):
        if "=" not in entry:
            continue
        key, values = entry.split("=", 1)
        clean_key = key.strip()
        clean_values = {
            value.strip()
            for value in values.split(",")
            if value.strip()
        }
        if clean_key:
            result[clean_key] = clean_values
    return result


def _is_expired(raw_expires_at: Optional[str]) -> bool:
    if raw_expires_at is None:
        return False
    try:
        return float(raw_expires_at) <= time.time()
    except ValueError:
        return True
