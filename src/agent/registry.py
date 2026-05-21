"""Agent Registry — Manages agent lifecycle and metadata."""

import time
import uuid
from enum import Enum
from threading import RLock
from typing import Any, Dict, List, Optional, Set, Tuple


class AgentStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    FAILED = "failed"
    TERMINATED = "terminated"


class AgentRegistry:
    TERMINAL_STATUSES = {
        AgentStatus.STOPPED.value,
        AgentStatus.FAILED.value,
        AgentStatus.TERMINATED.value,
    }

    def __init__(self, storage_backend: str = "memory"):
        self.storage_backend = storage_backend
        self._agents: Dict[str, Dict[str, Any]] = {}
        self._index: Dict[str, List[str]] = {}
        self._auth_cache: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        self._permission_versions: Dict[str, int] = {}
        self._audit_events: List[Dict[str, Any]] = []
        self._lock = RLock()

    def register(
        self,
        name: str,
        agent_type: str,
        config: Optional[Dict] = None,
    ) -> str:
        with self._lock:
            agent_id = str(uuid.uuid4())
            timestamp = time.time()
            config = dict(config or {})
            config["permissions"] = sorted(
                self._normalize_permissions(config.get("permissions", []))
            )
            self._agents[agent_id] = {
                "id": agent_id,
                "name": name,
                "type": agent_type,
                "status": AgentStatus.PENDING.value,
                "config": config,
                "created_at": timestamp,
                "updated_at": timestamp,
                "version": "1.0.0",
                "metrics": {"tasks_completed": 0, "errors": 0, "uptime": 0},
            }
            self._permission_versions[agent_id] = 0
            group = agent_type.split(".")[0]
            if group not in self._index:
                self._index[group] = []
            self._index[group].append(agent_id)
            self._audit(
                "agent_registered",
                agent_id,
                permissions=config["permissions"],
            )
            return agent_id

    def get(self, agent_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._agents.get(agent_id)

    def list(
        self,
        status: Optional[AgentStatus] = None,
        group: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self._lock:
            agents = self._agents.values()
            if status:
                agents = [a for a in agents if a["status"] == status.value]
            if group:
                agent_ids = self._index.get(group, [])
                agents = [a for a in agents if a["id"] in agent_ids]
            return list(agents)

    def update_status(self, agent_id: str, status: AgentStatus) -> bool:
        with self._lock:
            return self._set_status(agent_id, status)

    def update_status_if_authorized(
        self,
        agent_id: str,
        status: AgentStatus,
        permission: str,
        principal: str = "*",
        allowed_statuses: Optional[Set[AgentStatus]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Atomically recheck authorization and commit a lifecycle change."""
        with self._lock:
            agent = self.resolve_authorized(
                agent_id,
                permission,
                principal=principal,
                allowed_statuses=allowed_statuses,
            )
            if not agent:
                return None
            if not self._set_status(agent_id, status):
                return None
            self._audit(
                "authorized_status_changed",
                agent_id,
                permission=self._normalize_permission(permission),
                principal=str(principal or "*"),
                status=status.value,
            )
            return self._agents[agent_id]

    def delete(self, agent_id: str) -> bool:
        with self._lock:
            if agent_id not in self._agents:
                return False
            agent = self._agents.pop(agent_id)
            group = agent["type"].split(".")[0]
            if group in self._index and agent_id in self._index[group]:
                self._index[group].remove(agent_id)
            self._permission_versions.pop(agent_id, None)
            self._invalidate_auth_cache(agent_id)
            self._audit("agent_deleted", agent_id)
            return True

    def count(self) -> int:
        with self._lock:
            return len(self._agents)

    def set_permissions(self, agent_id: str, permissions: List[str]) -> bool:
        with self._lock:
            agent = self._agents.get(agent_id)
            if not agent:
                return False
            normalized = sorted(self._normalize_permissions(permissions))
            agent["config"]["permissions"] = normalized
            agent["updated_at"] = time.time()
            self._permission_versions[agent_id] = (
                self._permission_versions.get(agent_id, 0) + 1
            )
            self._invalidate_auth_cache(agent_id)
            self._audit(
                "permissions_changed",
                agent_id,
                permission_version=self._permission_versions[agent_id],
                permissions=normalized,
            )
            return True

    def resolve_authorized(
        self,
        agent_id: str,
        permission: str,
        principal: str = "*",
        allowed_statuses: Optional[Set[AgentStatus]] = None,
    ) -> Optional[Dict[str, Any]]:
        with self._lock:
            normalized_permission = self._normalize_permission(permission)
            normalized_principal = str(principal or "*")
            allowed = {
                status.value
                for status in (allowed_statuses or set(AgentStatus))
            }
            cache_key = (agent_id, normalized_principal, normalized_permission)
            permission_version = self._permission_versions.get(agent_id, 0)
            cached = self._auth_cache.get(cache_key)
            if cached and cached["permission_version"] == permission_version:
                agent = self._agents.get(agent_id)
                if self._is_authorized(agent, normalized_permission, allowed):
                    self._audit(
                        "auth_cache_hit",
                        agent_id,
                        permission=normalized_permission,
                        principal=normalized_principal,
                    )
                    return agent
                self._auth_cache.pop(cache_key, None)
                self._audit(
                    "auth_cache_stale",
                    agent_id,
                    permission=normalized_permission,
                    principal=normalized_principal,
                )

            agent = self._agents.get(agent_id)
            if not agent:
                self._audit(
                    "auth_denied",
                    agent_id,
                    permission=normalized_permission,
                    reason="missing_agent",
                )
                return None
            if agent["status"] not in allowed or agent["status"] in (
                self.TERMINAL_STATUSES
            ):
                self._audit(
                    "auth_deferred",
                    agent_id,
                    permission=normalized_permission,
                    status=agent["status"],
                )
                return None
            if not self._has_permission(agent, normalized_permission):
                self._audit(
                    "auth_denied",
                    agent_id,
                    permission=normalized_permission,
                    reason="permission_revoked",
                )
                return None

            self._auth_cache[cache_key] = {
                "permission_version": permission_version,
                "cached_at": time.time(),
            }
            self._audit(
                "auth_resolved",
                agent_id,
                permission=normalized_permission,
                principal=normalized_principal,
            )
            return agent

    def audit_events(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._audit_events)

    def _set_status(self, agent_id: str, status: AgentStatus) -> bool:
        if agent_id not in self._agents:
            return False
        self._agents[agent_id]["status"] = status.value
        self._agents[agent_id]["updated_at"] = time.time()
        self._invalidate_auth_cache(agent_id)
        self._audit("status_changed", agent_id, status=status.value)
        return True

    def _is_authorized(
        self,
        agent: Optional[Dict[str, Any]],
        permission: str,
        allowed_statuses: Set[str],
    ) -> bool:
        return bool(
            agent
            and agent["status"] in allowed_statuses
            and agent["status"] not in self.TERMINAL_STATUSES
            and self._has_permission(agent, permission)
        )

    def _has_permission(self, agent: Dict[str, Any], permission: str) -> bool:
        permissions = set(agent["config"].get("permissions", []))
        return "*" in permissions or permission in permissions

    def _normalize_permissions(self, permissions: List[str]) -> Set[str]:
        return {
            permission
            for permission in (
                self._normalize_permission(value) for value in permissions
            )
            if permission
        }

    def _normalize_permission(self, permission: str) -> str:
        return str(permission).strip().casefold()

    def _invalidate_auth_cache(self, agent_id: str) -> None:
        self._auth_cache = {
            key: value
            for key, value in self._auth_cache.items()
            if key[0] != agent_id
        }

    def _audit(
        self,
        event: str,
        agent_id: Optional[str],
        **metadata: Any,
    ) -> None:
        with self._lock:
            self._audit_events.append(
                {
                    "event": event,
                    "agent_id": agent_id,
                    "metadata": metadata,
                    "timestamp": time.time(),
                }
            )

# 2019-01-29T11:24:49 update

# 2019-04-09T13:38:38 update

# 2019-04-11T11:24:12 update

# 2019-06-26T17:03:48 update

# 2019-07-03T14:55:48 update

# 2019-07-18T18:18:47 update

# 2019-11-05T11:27:19 update

# 2019-11-20T11:35:05 update

# 2019-11-23T15:28:54 update

# 2020-03-13T09:23:07 update

# 2020-03-30T19:31:18 update

# 2020-04-22T15:03:30 update

# 2020-07-21T10:00:48 update

# 2020-09-10T09:02:08 update

# 2020-09-10T13:39:12 update

# 2020-09-22T16:27:52 update

# 2020-10-15T10:33:14 update

# 2021-05-13T11:15:56 update

# 2021-07-07T14:57:13 update

# 2021-07-13T15:15:19 update

# 2021-07-27T10:18:16 update

# 2022-03-11T15:24:11 update

# 2022-09-22T13:24:20 update

# 2022-11-01T12:20:40 update

# 2023-01-30T12:32:27 update

# 2023-03-10T09:43:50 update

# 2023-05-10T14:28:01 update

# 2023-05-11T20:04:46 update

# 2023-05-30T17:00:59 update

# 2023-07-13T17:54:32 update

# 2023-07-20T19:04:20 update

# 2023-07-31T17:00:02 update

# 2023-09-05T19:42:07 update

# 2024-01-02T10:29:47 update

# 2024-09-17T12:45:29 update

# 2024-09-17T11:51:01 update

# 2024-11-06T18:20:15 update

# 2025-01-12T15:13:14 update

# 2025-01-14T20:24:39 update

# 2025-03-26T20:21:27 update

# 2025-04-10T18:27:06 update

# 2025-06-19T20:34:58 update

# 2025-06-21T20:23:53 update

# 2025-06-24T20:30:30 update

# 2025-07-03T13:28:03 update

# 2025-07-24T17:42:21 update

# 2025-08-19T17:42:23 update

# 2025-08-21T11:06:52 update

# 2025-10-24T09:10:08 update

# 2025-12-18T19:34:38 update

# 2026-02-06T11:22:22 update

# 2026-02-13T15:42:04 update

# 2026-04-10T08:16:30 update

# 2026-04-29T18:16:11 update
