"""Template clone authorization and service layer."""

import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional


class TemplateCloneError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


@dataclass
class Principal:
    principal_id: str
    workspace_id: str
    role: str
    scopes: List[str]
    disabled: bool = False
    revoked: bool = False
    expires_at: Optional[float] = None


@dataclass
class TemplateCloneService:
    principals: Dict[str, Principal] = field(default_factory=dict)
    templates: Dict[str, Dict] = field(default_factory=dict)
    audit_events: List[Dict] = field(default_factory=list)
    template_read_count: int = 0
    clone_mutation_count: int = 0

    allowed_roles = {"owner", "admin", "editor"}

    def reset(self) -> None:
        self.principals.clear()
        self.templates.clear()
        self.audit_events.clear()
        self.template_read_count = 0
        self.clone_mutation_count = 0

    def register_principal(self, token: str, principal: Principal) -> None:
        self.principals[token] = principal

    def register_template(
        self,
        workspace_id: str,
        template_id: str,
        definition: Optional[Dict] = None,
    ) -> None:
        self.templates[f"{workspace_id}:{template_id}"] = definition or {}

    def clone(
        self,
        workspace_id: str,
        template_id: str,
        authorization: str,
        target_name: str,
    ) -> Dict:
        principal = self._authorize(workspace_id, authorization)

        self.template_read_count += 1
        template = self.templates.get(f"{workspace_id}:{template_id}")
        if template is None:
            self._audit("missing_template", principal, workspace_id)
            raise TemplateCloneError(404, "Template not found")

        self.clone_mutation_count += 1
        clone_id = str(uuid.uuid4())
        self._audit("clone_created", principal, workspace_id)
        return {
            "clone_id": clone_id,
            "template_id": template_id,
            "workspace_id": workspace_id,
            "name": target_name,
            "definition": template,
        }

    def _authorize(self, workspace_id: str, authorization: str) -> Principal:
        if not authorization.startswith("Bearer "):
            self._audit("missing_auth", None, workspace_id)
            raise TemplateCloneError(401, "Unauthorized")

        token = authorization.removeprefix("Bearer ").strip()
        if not token:
            self._audit("blank_token", None, workspace_id)
            raise TemplateCloneError(401, "Unauthorized")

        principal = self.principals.get(token)
        if principal is None:
            self._audit("unknown_token", None, workspace_id)
            raise TemplateCloneError(401, "Unauthorized")
        if principal.revoked or principal.disabled:
            self._audit("inactive_principal", principal, workspace_id)
            raise TemplateCloneError(401, "Unauthorized")
        if (
            principal.expires_at is not None
            and principal.expires_at <= time.time()
        ):
            self._audit("expired_principal", principal, workspace_id)
            raise TemplateCloneError(401, "Unauthorized")
        if principal.workspace_id != workspace_id:
            self._audit("wrong_workspace", principal, workspace_id)
            raise TemplateCloneError(403, "Forbidden")
        if "templates:clone" not in principal.scopes:
            self._audit("missing_scope", principal, workspace_id)
            raise TemplateCloneError(403, "Forbidden")
        if principal.role not in self.allowed_roles:
            self._audit("insufficient_role", principal, workspace_id)
            raise TemplateCloneError(403, "Forbidden")

        self._audit("authorized", principal, workspace_id)
        return principal

    def _audit(
        self,
        decision: str,
        principal: Optional[Principal],
        workspace_id: str,
    ) -> None:
        self.audit_events.append({
            "decision": decision,
            "principal_id": principal.principal_id if principal else None,
            "workspace_id": workspace_id,
            "role": principal.role if principal else None,
        })


template_clone_service = TemplateCloneService()
