"""Central API authentication and workspace permission checks."""

import time
from dataclasses import dataclass
from typing import Dict, Iterable, Optional

from starlette.requests import Request


WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@dataclass(frozen=True)
class Principal:
    subject: str
    workspaces: Dict[str, str]
    expires_at: float
    revoked: bool = False
    scopes: frozenset = frozenset()

    def workspace_role(self, workspace_id: str) -> Optional[str]:
        return self.workspaces.get(workspace_id)


class AuthenticationError(Exception):
    pass


class PermissionDenied(Exception):
    pass


class AuthService:
    def __init__(self, principals: Optional[Dict[str, Principal]] = None):
        self._principals = principals or default_principals()

    def authenticate_request(self, request: Request) -> Principal:
        token = self._extract_token(request)
        principal = self.authenticate_token(token)
        self.authorize_request(request, principal)
        return principal

    def authenticate_token(self, token: str) -> Principal:
        if not token:
            raise AuthenticationError("missing credentials")
        principal = self._principals.get(token)
        if principal is None:
            raise AuthenticationError("invalid credentials")
        if principal.revoked:
            raise AuthenticationError("revoked credentials")
        if principal.expires_at <= time.time():
            raise AuthenticationError("stale credentials")
        return principal

    def authorize_request(
        self,
        request: Request,
        principal: Principal,
    ) -> None:
        workspace_id = request.headers.get("X-Workspace-ID", "default")
        role = principal.workspace_role(workspace_id)
        if role is None:
            raise PermissionDenied("workspace access denied")
        if (
            request.method.upper() in WRITE_METHODS
            and role not in {"admin", "operator"}
        ):
            raise PermissionDenied("insufficient workspace role")

    def _extract_token(self, request: Request) -> str:
        authorization = request.headers.get("Authorization", "")
        if authorization:
            scheme, _, value = authorization.partition(" ")
            if scheme != "Bearer" or not value.strip():
                raise AuthenticationError("malformed authorization header")
            return value.strip()

        return request.cookies.get("ao_session", "")


def default_principals() -> Dict[str, Principal]:
    future = time.time() + 3600
    past = time.time() - 1
    return {
        "valid-admin-token": Principal(
            subject="api-admin",
            workspaces={"default": "admin", "workspace-a": "admin"},
            expires_at=future,
            scopes=frozenset({"agents:read", "agents:write"}),
        ),
        "valid-operator-token": Principal(
            subject="api-operator",
            workspaces={"default": "operator"},
            expires_at=future,
            scopes=frozenset({"agents:read", "agents:write"}),
        ),
        "browser-admin-session": Principal(
            subject="browser-admin",
            workspaces={"default": "admin"},
            expires_at=future,
            scopes=frozenset({"agents:read", "agents:write"}),
        ),
        "read-only-token": Principal(
            subject="api-viewer",
            workspaces={"default": "viewer"},
            expires_at=future,
            scopes=frozenset({"agents:read"}),
        ),
        "stale-token": Principal(
            subject="expired-user",
            workspaces={"default": "admin"},
            expires_at=past,
            scopes=frozenset({"agents:read", "agents:write"}),
        ),
        "revoked-token": Principal(
            subject="revoked-user",
            workspaces={"default": "admin"},
            expires_at=future,
            revoked=True,
            scopes=frozenset({"agents:read", "agents:write"}),
        ),
    }


def build_principal(
    subject: str,
    workspace_roles: Dict[str, str],
    expires_at: float,
    scopes: Iterable[str] = (),
    revoked: bool = False,
) -> Principal:
    return Principal(
        subject=subject,
        workspaces=dict(workspace_roles),
        expires_at=expires_at,
        revoked=revoked,
        scopes=frozenset(scopes),
    )
