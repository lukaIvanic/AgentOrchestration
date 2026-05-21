from src.common.retention import DeletionManifest, RetentionStore


def test_delete_artifacts_cascades_to_derived_stores():
    store = RetentionStore()
    store.add_artifact("artifact-1")
    store.add_embedding("artifact-1", "embedding-1")
    store.add_vector_index("artifact-1", "vector-1")
    store.add_search_index("artifact-1", "search-1")

    records = store.delete_artifacts(["artifact-1"])

    assert store.primary_artifacts == set()
    assert store.embeddings == {}
    assert store.vector_indexes == {}
    assert store.search_indexes == {}
    assert [record.store for record in records] == [
        "primary_artifacts",
        "embeddings",
        "vector_indexes",
        "search_indexes",
    ]
    assert all(record.verified for record in records)


def test_delete_artifacts_is_idempotent_with_completion_records():
    store = RetentionStore()
    store.add_artifact("artifact-1")
    store.add_embedding("artifact-1", "embedding-1")

    first = store.delete_artifacts(["artifact-1"])
    second = store.delete_artifacts(["artifact-1"])

    assert first[0].deleted == ["artifact-1"]
    assert second[0].missing == ["artifact-1"]
    assert second[1].missing == ["artifact-1"]
    assert all(record.verified for record in second)
    assert len(store.completions) == 8


def test_reconcile_derived_removes_stale_records_only():
    store = RetentionStore()
    store.add_artifact("live-artifact")
    store.add_embedding("live-artifact", "live-embedding")
    store.add_embedding("stale-artifact", "stale-embedding")
    store.add_vector_index("stale-artifact", "stale-vector")
    store.add_search_index("stale-artifact", "stale-search")

    records = store.reconcile_derived()

    assert store.primary_artifacts == {"live-artifact"}
    assert store.embeddings == {"live-artifact": {"live-embedding"}}
    assert store.vector_indexes == {}
    assert store.search_indexes == {}
    assert [record.store for record in records] == [
        "embeddings",
        "vector_indexes",
        "search_indexes",
    ]
    assert records[0].deleted == ["stale-embedding"]
    assert records[1].deleted == ["stale-vector"]
    assert records[2].deleted == ["stale-search"]
    assert all(record.reason == "reconcile" for record in records)


def test_manifest_records_empty_derived_store_completion():
    store = RetentionStore()
    store.add_artifact("artifact-1")

    records = store.delete_artifacts(["artifact-1"])

    assert records[1].store == "embeddings"
    assert records[1].requested == ["artifact-1"]
    assert records[1].missing == ["artifact-1"]
    assert records[1].remaining == []
    assert records[1].verified
    assert [record.store for record in store.completions] == [
        "primary_artifacts",
        "embeddings",
        "vector_indexes",
        "search_indexes",
    ]


def test_apply_manifest_can_target_only_derived_store():
    store = RetentionStore()
    store.add_artifact("artifact-1")
    store.add_artifact("artifact-2")
    store.add_embedding("artifact-1", "embedding-1")

    manifest = DeletionManifest(
        reason="reconcile",
        source_ids=["artifact-1"],
        stores=["embeddings"],
    )
    records = store.apply_manifest(manifest)

    assert records[0].requested == ["artifact-1"]
    assert records[0].deleted == ["embedding-1"]
    assert records[0].remaining == []
    assert records[0].reason == "reconcile"
    assert store.primary_artifacts == {"artifact-1", "artifact-2"}


def test_build_manifest_sorts_and_deduplicates_sources():
    store = RetentionStore()

    manifest = store.build_manifest(
        ["artifact-2", "artifact-1", "artifact-2"],
        reason="delete",
    )

    assert manifest.source_ids == ["artifact-1", "artifact-2"]
    assert manifest.stores == [
        "primary_artifacts",
        "embeddings",
        "vector_indexes",
        "search_indexes",
    ]


def test_audit_events_are_sanitized_and_show_verification():
    store = RetentionStore()
    store.add_artifact("artifact-1")
    store.add_embedding("artifact-1", "secret-derived-value")

    store.delete_artifacts(["artifact-1"])

    audit = store.audit_events[-1]
    assert audit["decision"] == "manifest_applied"
    assert audit["stores"] == [
        "primary_artifacts",
        "embeddings",
        "vector_indexes",
        "search_indexes",
    ]
    assert audit["requested_count"] == 1
    assert audit["verified"] is True
    assert "artifact-1" not in str(audit)
    assert "secret-derived-value" not in str(audit)


def test_reconcile_clean_records_sanitized_noop():
    store = RetentionStore()
    store.add_artifact("artifact-1")
    store.add_embedding("artifact-1", "embedding-1")

    assert store.reconcile_derived() == []

    assert store.audit_events[-1]["decision"] == "reconcile_clean"
    assert store.audit_events[-1]["verified"] is True
