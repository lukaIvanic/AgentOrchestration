"""Integration auth guard for protected webhook management."""

import time
from dataclasses import dataclass
from typing import Dict, List, Optional


class IntegrationAuthError(PermissionError):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass
class Principal:
    user_id: str
    workspace_id: str
    role: str
    scopes: List[str]
    disabled: bool = False
    revoked: bool = False
    expires_at: Optional[float] = None


class IntegrationAuthService:
    def __init__(self):
        self._tokens: Dict[str, Principal] = {}
        self.protected_action_count = 0

    def register_token(self, token: str, principal: Principal) -> None:
        self._tokens[token] = principal

    def reset(self) -> None:
        self._tokens.clear()
        self.protected_action_count = 0

    def require_webhook_manager(
        self,
        authorization: str,
        integration_session: str,
        browser_session: str,
        workspace_id: str,
    ) -> Principal:
        token = self._extract_credential(
            authorization,
            integration_session,
            browser_session,
        )
        if not token:
            raise IntegrationAuthError(401, "Anonymous principals denied")
        principal = self._tokens.get(token)
        if not principal:
            raise IntegrationAuthError(401, "Unknown integration token")
        if principal.revoked:
            self._tokens.pop(token, None)
            raise IntegrationAuthError(401, "Revoked principal denied")
        if principal.disabled:
            raise IntegrationAuthError(403, "Disabled user denied")
        if (
            principal.expires_at is not None
            and principal.expires_at <= time.time()
        ):
            self._tokens.pop(token, None)
            raise IntegrationAuthError(401, "Expired principal denied")
        if principal.workspace_id != workspace_id:
            raise IntegrationAuthError(403, "Workspace access denied")
        if "webhooks:manage" not in principal.scopes:
            raise IntegrationAuthError(403, "Insufficient scope")
        if principal.role not in {"admin", "operator"}:
            raise IntegrationAuthError(403, "Insufficient workspace role")
        return principal

    def create_webhook(
        self,
        authorization: str,
        integration_session: str,
        browser_session: str,
        workspace_id: str,
        target_url: str,
    ) -> Dict[str, str]:
        principal = self.require_webhook_manager(
            authorization,
            integration_session,
            browser_session,
            workspace_id,
        )
        self.protected_action_count += 1
        return {
            "status": "created",
            "workspace_id": workspace_id,
            "created_by": principal.user_id,
            "target_url": target_url,
        }

    def _extract_credential(
        self,
        authorization: str,
        integration_session: str,
        browser_session: str,
    ) -> str:
        return (
            self._extract_bearer(authorization)
            or str(integration_session or "").strip()
            or str(browser_session or "").strip()
        )

    def _extract_bearer(self, authorization: str) -> str:
        authorization = str(authorization or "").strip()
        if not authorization.startswith("Bearer "):
            return ""
        return authorization.removeprefix("Bearer ").strip()


integration_auth_service = IntegrationAuthService()
