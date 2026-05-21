"""Authentication and authorization helpers for protected API routes."""

import time
from dataclasses import dataclass, field
from typing import Dict, Iterable, Optional, Set

from starlette.requests import Request


class AuthError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


@dataclass(frozen=True)
class Principal:
    user_id: str
    workspace_id: str
    role: str
    scopes: Set[str]
    credential_id: str
    credential_type: str


@dataclass
class CredentialRecord:
    user_id: str
    workspace_id: str
    role: str
    scopes: Set[str] = field(default_factory=set)
    expires_at: Optional[float] = None
    revoked: bool = False
    disabled: bool = False


class AuthService:
    """Mutable credential store used to revalidate each protected request."""

    def __init__(self, now=None):
        self._now = now or time.time
        self._api_keys: Dict[str, CredentialRecord] = {}
        self._sessions: Dict[str, CredentialRecord] = {}

    def register_api_key(
        self,
        token: str,
        *,
        user_id: str,
        workspace_id: str,
        role: str,
        scopes: Iterable[str],
        expires_at: Optional[float] = None,
        revoked: bool = False,
        disabled: bool = False,
    ) -> None:
        self._api_keys[token] = CredentialRecord(
            user_id=user_id,
            workspace_id=workspace_id,
            role=role,
            scopes=set(scopes),
            expires_at=expires_at,
            revoked=revoked,
            disabled=disabled,
        )

    def register_session(
        self,
        session_id: str,
        *,
        user_id: str,
        workspace_id: str,
        role: str,
        scopes: Iterable[str],
        expires_at: Optional[float] = None,
        revoked: bool = False,
        disabled: bool = False,
    ) -> None:
        self._sessions[session_id] = CredentialRecord(
            user_id=user_id,
            workspace_id=workspace_id,
            role=role,
            scopes=set(scopes),
            expires_at=expires_at,
            revoked=revoked,
            disabled=disabled,
        )

    def revoke_api_key(self, token: str) -> None:
        if token in self._api_keys:
            self._api_keys[token].revoked = True

    def revoke_session(self, session_id: str) -> None:
        if session_id in self._sessions:
            self._sessions[session_id].revoked = True

    def authenticate_request(self, request: Request) -> Principal:
        auth_header = request.headers.get("Authorization", "")
        if auth_header:
            if not auth_header.startswith("Bearer "):
                raise AuthError(401, "Malformed authorization header")
            token = auth_header.removeprefix("Bearer ").strip()
            if not token:
                raise AuthError(401, "Missing bearer token")
            return self._principal_from_record(
                self._api_keys.get(token), token, "api_key"
            )

        session_id = request.cookies.get("ao_session")
        if session_id:
            return self._principal_from_record(
                self._sessions.get(session_id), session_id, "session"
            )

        raise AuthError(401, "Missing credentials")

    def require(
        self,
        principal: Principal,
        *,
        workspace_id: str,
        scopes: Iterable[str],
        roles: Iterable[str],
    ) -> None:
        required_scopes = set(scopes)
        allowed_roles = set(roles)
        if principal.workspace_id != workspace_id:
            raise AuthError(403, "Principal is not a member of this workspace")
        if not required_scopes.issubset(principal.scopes):
            raise AuthError(403, "Principal lacks required scope")
        if principal.role not in allowed_roles:
            raise AuthError(403, "Principal lacks required role")

    def _principal_from_record(
        self,
        record: Optional[CredentialRecord],
        credential_id: str,
        credential_type: str,
    ) -> Principal:
        if record is None:
            raise AuthError(401, "Unknown credential")
        if record.revoked:
            raise AuthError(401, "Credential has been revoked")
        if record.disabled:
            raise AuthError(401, "Credential has been disabled")
        if record.expires_at is not None and record.expires_at <= self._now():
            raise AuthError(401, "Credential has expired")
        return Principal(
            user_id=record.user_id,
            workspace_id=record.workspace_id,
            role=record.role,
            scopes=set(record.scopes),
            credential_id=credential_id,
            credential_type=credential_type,
        )
