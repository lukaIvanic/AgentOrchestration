"""Metrics label cardinality validation for deployment manifests."""

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence


DEFAULT_CARDINALITY_LIMIT = 20

ALLOWED_LABEL_VALUES: Dict[str, Sequence[str]] = {
    "agent_type": ("worker", "monitor", "scheduler", "gateway"),
    "environment": ("dev", "staging", "prod"),
    "event": ("enqueue", "dequeue", "complete", "fail", "retry"),
    "outcome": ("success", "failure", "timeout", "skipped"),
    "priority": ("low", "normal", "high", "critical"),
    "queue": ("default", "priority", "dead_letter"),
    "region": ("local", "us-east", "us-west", "eu", "apac"),
    "status": (
        "pending",
        "running",
        "completed",
        "failed",
        "paused",
        "stopped",
    ),
    "worker_type": ("processor", "analyzer", "watcher", "executor"),
}

HIGH_CARDINALITY_LABELS = {
    "agent_id",
    "email",
    "host",
    "ip",
    "job_id",
    "path",
    "request_id",
    "run_id",
    "session_id",
    "task_id",
    "timestamp",
    "trace_id",
    "url",
    "user_id",
    "worker_id",
}


@dataclass(frozen=True)
class MetricsPolicyViolation:
    metric: str
    label: str
    reason: str

    def format(self) -> str:
        return f"{self.metric}.{self.label}: {self.reason}"


def validate_manifest_metrics(
    manifest: Mapping[str, Any],
) -> List[MetricsPolicyViolation]:
    """Validate metrics declared by a deployment manifest."""
    metrics = manifest.get("metrics", [])
    exceptions = manifest.get("metrics_cardinality_exceptions", [])
    return validate_metrics_schema(metrics, exceptions=exceptions)


def validate_metrics_schema(
    metrics: Iterable[Mapping[str, Any]],
    *,
    exceptions: Iterable[Mapping[str, Any]] = (),
    max_values: int = DEFAULT_CARDINALITY_LIMIT,
) -> List[MetricsPolicyViolation]:
    """Return cardinality violations for metric labels."""
    approved_exceptions = list(exceptions)
    violations: List[MetricsPolicyViolation] = []

    for metric in metrics:
        metric_name = str(metric.get("name", "<unnamed>"))
        for label_name, values in _iter_labels(metric.get("labels", {})):
            if _has_approved_exception(
                approved_exceptions, metric_name, label_name
            ):
                continue
            violation = _validate_label(
                metric_name, label_name, values, max_values
            )
            if violation:
                violations.append(violation)

    return violations


def _validate_label(
    metric_name: str,
    label_name: str,
    values: Optional[Sequence[Any]],
    max_values: int,
) -> Optional[MetricsPolicyViolation]:
    normalized = label_name.lower()
    if normalized in HIGH_CARDINALITY_LABELS:
        return MetricsPolicyViolation(
            metric_name,
            label_name,
            "high-cardinality label requires an approved owner exception",
        )

    if values is None:
        if normalized in ALLOWED_LABEL_VALUES:
            return None
        return MetricsPolicyViolation(
            metric_name,
            label_name,
            "label has no bounded allowed_values and is not in the "
            "approved label policy",
        )

    unique_values = {str(value) for value in values}
    if not unique_values:
        return MetricsPolicyViolation(
            metric_name,
            label_name,
            "label allowed_values cannot be empty",
        )
    if len(unique_values) > max_values:
        return MetricsPolicyViolation(
            metric_name,
            label_name,
            f"label declares {len(unique_values)} values, above the "
            f"{max_values} value budget",
        )
    return None


def _iter_labels(
    raw_labels: Any,
) -> Iterable[tuple[str, Optional[Sequence[Any]]]]:
    if isinstance(raw_labels, Mapping):
        for name, values in raw_labels.items():
            yield str(name), _normalize_values(values)
        return

    if isinstance(raw_labels, list):
        for item in raw_labels:
            if isinstance(item, str):
                yield item, None
            elif isinstance(item, Mapping):
                name = item.get("name") or item.get("label")
                if name:
                    yield str(name), _normalize_values(
                        item.get("allowed_values")
                    )


def _normalize_values(values: Any) -> Optional[Sequence[Any]]:
    if values is None:
        return None
    if isinstance(values, str):
        return (values,)
    if isinstance(values, Sequence):
        return values
    return (values,)


def _has_approved_exception(
    exceptions: Iterable[Mapping[str, Any]],
    metric_name: str,
    label_name: str,
) -> bool:
    for exception in exceptions:
        if not exception.get("approved"):
            continue
        if not exception.get("owner") or not exception.get("reason"):
            continue
        if exception.get("label") != label_name:
            continue
        if exception.get("metric") in (None, "*", metric_name):
            return True
    return False
