from src.common.metrics_policy import (
    validate_manifest_metrics,
    validate_metrics_schema,
)


def test_bounded_labels_pass_cardinality_policy():
    violations = validate_metrics_schema([
        {
            "name": "task_events_total",
            "labels": {
                "status": ["pending", "running", "completed", "failed"],
                "queue": ["default", "priority"],
            },
        }
    ])

    assert violations == []


def test_unbounded_label_blocks_rollout_without_exception():
    violations = validate_metrics_schema([
        {
            "name": "task_events_total",
            "labels": {"task_id": None},
        }
    ])

    assert len(violations) == 1
    assert violations[0].metric == "task_events_total"
    assert violations[0].label == "task_id"


def test_approved_owner_exception_allows_unbounded_label():
    violations = validate_metrics_schema(
        [
            {
                "name": "task_debug_total",
                "labels": {"task_id": None},
            }
        ],
        exceptions=[
            {
                "metric": "task_debug_total",
                "label": "task_id",
                "approved": True,
                "owner": "observability",
                "reason": "temporary debug-only rollout",
            }
        ],
    )

    assert violations == []


def test_manifest_metrics_exceptions_are_checked():
    manifest = {
        "metrics": [
            {
                "name": "worker_events_total",
                "labels": [
                    {
                        "name": "worker_type",
                        "allowed_values": ["processor", "analyzer"],
                    },
                    {"name": "request_id"},
                ],
            }
        ],
        "metrics_cardinality_exceptions": [
            {
                "metric": "worker_events_total",
                "label": "request_id",
                "approved": True,
                "owner": "platform",
                "reason": "one-release incident correlation",
            }
        ],
    }

    assert validate_manifest_metrics(manifest) == []
