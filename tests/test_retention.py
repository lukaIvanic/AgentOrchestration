from src.common.retention import RetentionStore


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
    assert records[1].deleted == ["stale-embedding"]
    assert records[2].deleted == ["stale-vector"]
    assert records[3].deleted == ["stale-search"]
