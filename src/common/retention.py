"""Retention deletion helpers for primary and derived data."""

from dataclasses import dataclass, field
from typing import Dict, List, Set


@dataclass
class DeletionRecord:
    store: str
    requested: List[str]
    deleted: List[str] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)
    verified: bool = False


class RetentionStore:
    def __init__(self):
        self.primary_artifacts: Set[str] = set()
        self.embeddings: Dict[str, Set[str]] = {}
        self.vector_indexes: Dict[str, Set[str]] = {}
        self.search_indexes: Dict[str, Set[str]] = {}
        self.completions: List[DeletionRecord] = []

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
        records = [
            self._delete_primary(artifact_ids),
            self._delete_derived("embeddings", self.embeddings, artifact_ids),
            self._delete_derived(
                "vector_indexes",
                self.vector_indexes,
                artifact_ids,
            ),
            self._delete_derived(
                "search_indexes",
                self.search_indexes,
                artifact_ids,
            ),
        ]
        self.completions.extend(records)
        return records

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
            return []
        return self.delete_artifacts(stale_sources)

    def _delete_primary(self, artifact_ids: List[str]) -> DeletionRecord:
        record = DeletionRecord("primary_artifacts", sorted(artifact_ids))
        for artifact_id in sorted(artifact_ids):
            if artifact_id in self.primary_artifacts:
                self.primary_artifacts.remove(artifact_id)
                record.deleted.append(artifact_id)
            else:
                record.missing.append(artifact_id)
        record.verified = not any(
            artifact_id in self.primary_artifacts
            for artifact_id in artifact_ids
        )
        return record

    def _delete_derived(
        self,
        store_name: str,
        store: Dict[str, Set[str]],
        source_ids: List[str],
    ) -> DeletionRecord:
        requested = sorted(source_ids)
        record = DeletionRecord(store_name, requested)
        for source_id in requested:
            values = store.pop(source_id, None)
            if values:
                record.deleted.extend(sorted(values))
            else:
                record.missing.append(source_id)
        record.verified = not any(
            source_id in store for source_id in requested
        )
        return record
