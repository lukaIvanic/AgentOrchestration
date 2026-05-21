"""Retention deletion helpers for primary and derived data."""

from dataclasses import dataclass, field
import time
from typing import Dict, List, Set


@dataclass
class DeletionManifest:
    reason: str
    source_ids: List[str]
    stores: List[str]


@dataclass
class DeletionRecord:
    store: str
    requested: List[str]
    deleted: List[str] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)
    remaining: List[str] = field(default_factory=list)
    verified: bool = False
    reason: str = "delete"


class RetentionStore:
    STORE_NAMES = [
        "primary_artifacts",
        "embeddings",
        "vector_indexes",
        "search_indexes",
    ]

    def __init__(self):
        self.primary_artifacts: Set[str] = set()
        self.embeddings: Dict[str, Set[str]] = {}
        self.vector_indexes: Dict[str, Set[str]] = {}
        self.search_indexes: Dict[str, Set[str]] = {}
        self.completions: List[DeletionRecord] = []
        self.audit_events: List[Dict[str, object]] = []

    def add_artifact(self, artifact_id: str) -> None:
        self.primary_artifacts.add(artifact_id)

    def add_embedding(self, source_id: str, embedding_id: str) -> None:
        self.embeddings.setdefault(source_id, set()).add(embedding_id)

    def add_vector_index(self, source_id: str, index_id: str) -> None:
        self.vector_indexes.setdefault(source_id, set()).add(index_id)

    def add_search_index(self, source_id: str, index_id: str) -> None:
        self.search_indexes.setdefault(source_id, set()).add(index_id)

    def delete_artifacts(
        self,
        artifact_ids: List[str],
    ) -> List[DeletionRecord]:
        manifest = self.build_manifest(artifact_ids, reason="delete")
        return self.apply_manifest(manifest)

    def build_manifest(
        self,
        source_ids: List[str],
        reason: str,
    ) -> DeletionManifest:
        return DeletionManifest(
            reason=reason,
            source_ids=sorted(set(source_ids)),
            stores=list(self.STORE_NAMES),
        )

    def apply_manifest(
        self,
        manifest: DeletionManifest,
    ) -> List[DeletionRecord]:
        records: List[DeletionRecord] = []
        for store_name in manifest.stores:
            if store_name == "primary_artifacts":
                records.append(
                    self._delete_primary(manifest.source_ids, manifest.reason)
                )
            elif store_name == "embeddings":
                records.append(
                    self._delete_derived(
                        "embeddings",
                        self.embeddings,
                        manifest.source_ids,
                        manifest.reason,
                    )
                )
            elif store_name == "vector_indexes":
                records.append(
                    self._delete_derived(
                        "vector_indexes",
                        self.vector_indexes,
                        manifest.source_ids,
                        manifest.reason,
                    )
                )
            elif store_name == "search_indexes":
                records.append(
                    self._delete_derived(
                        "search_indexes",
                        self.search_indexes,
                        manifest.source_ids,
                        manifest.reason,
                    )
                )
        self.completions.extend(records)
        self._audit_manifest(manifest, records)
        return records

    def _audit_manifest(
        self,
        manifest: DeletionManifest,
        records: List[DeletionRecord],
    ) -> None:
        self.audit_events.append({
            "decision": "manifest_applied",
            "reason": manifest.reason,
            "stores": [record.store for record in records],
            "requested_count": len(manifest.source_ids),
            "verified": all(record.verified for record in records),
            "timestamp": time.time(),
        })

    def reconcile_derived(self) -> List[DeletionRecord]:
        stale_sources = sorted(
            (
                set(self.embeddings)
                | set(self.vector_indexes)
                | set(self.search_indexes)
            )
            - self.primary_artifacts
        )
        if not stale_sources:
            self.audit_events.append({
                "decision": "reconcile_clean",
                "reason": "reconcile",
                "stores": [
                    "embeddings",
                    "vector_indexes",
                    "search_indexes",
                ],
                "requested_count": 0,
                "verified": True,
                "timestamp": time.time(),
            })
            return []
        manifest = DeletionManifest(
            reason="reconcile",
            source_ids=stale_sources,
            stores=[
                "embeddings",
                "vector_indexes",
                "search_indexes",
            ],
        )
        return self.apply_manifest(manifest)

    def _delete_primary(
        self,
        artifact_ids: List[str],
        reason: str,
    ) -> DeletionRecord:
        record = DeletionRecord(
            "primary_artifacts",
            sorted(artifact_ids),
            reason=reason,
        )
        for artifact_id in sorted(artifact_ids):
            if artifact_id in self.primary_artifacts:
                self.primary_artifacts.remove(artifact_id)
                record.deleted.append(artifact_id)
            else:
                record.missing.append(artifact_id)
        record.remaining = [
            artifact_id
            for artifact_id in record.requested
            if artifact_id in self.primary_artifacts
        ]
        record.verified = not record.remaining
        return record

    def _delete_derived(
        self,
        store_name: str,
        store: Dict[str, Set[str]],
        source_ids: List[str],
        reason: str,
    ) -> DeletionRecord:
        requested = sorted(source_ids)
        record = DeletionRecord(store_name, requested, reason=reason)
        for source_id in requested:
            values = store.pop(source_id, None)
            if values:
                record.deleted.extend(sorted(values))
            else:
                record.missing.append(source_id)
        record.remaining = [
            source_id for source_id in requested if source_id in store
        ]
        record.verified = not record.remaining
        return record
