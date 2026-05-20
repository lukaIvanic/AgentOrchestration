"""Metrics label cardinality validation for deployment gates."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional


UNBOUNDED_LABEL_HINTS = (
    "address",
    "email",
    "id",
    "path",
    "request",
    "session",
    "timestamp",
    "token",
    "url",
    "uuid",
)


@dataclass(frozen=True)
class CardinalityViolation:
    metric: str
    label: str
    reason: str


@dataclass(frozen=True)
class CardinalityReport:
    violations: List[CardinalityViolation] = field(default_factory=list)
    checked_labels: int = 0

    @property
    def passed(self) -> bool:
        return not self.violations

    def format(self) -> str:
        if self.passed:
            return (
                "metrics cardinality check passed "
                f"({self.checked_labels} labels)"
            )

        lines = ["metrics cardinality check failed:"]
        for violation in self.violations:
            lines.append(
                f"- {violation.metric}.{violation.label}: {violation.reason}",
            )
        return "\n".join(lines)


def validate_metrics_schema_file(
    path: Path,
    *,
    max_allowed_values: int = 25,
) -> CardinalityReport:
    schema = json.loads(Path(path).read_text(encoding="utf-8"))
    return validate_metrics_schema(
        schema,
        max_allowed_values=max_allowed_values,
    )


def validate_metrics_schema(
    schema: Dict,
    *,
    max_allowed_values: int = 25,
) -> CardinalityReport:
    exceptions = _index_exceptions(schema.get("exceptions", []))
    violations: List[CardinalityViolation] = []
    checked_labels = 0

    for metric in schema.get("metrics", []):
        metric_name = metric["name"]
        for label in metric.get("labels", []):
            checked_labels += 1
            label_name = label["name"]
            exception = exceptions.get((metric_name, label_name))
            violation = _validate_label(
                metric_name,
                label,
                exception,
                max_allowed_values=max_allowed_values,
            )
            if violation is not None:
                violations.append(violation)

    return CardinalityReport(
        violations=violations,
        checked_labels=checked_labels,
    )


def _validate_label(
    metric_name: str,
    label: Dict,
    exception: Optional[Dict],
    *,
    max_allowed_values: int,
) -> Optional[CardinalityViolation]:
    label_name = label["name"]
    allowed_values = label.get("values")

    if _has_approved_exception(exception):
        return None

    if not label.get("owner"):
        return CardinalityViolation(
            metric=metric_name,
            label=label_name,
            reason="label owner is required",
        )

    if _looks_unbounded(label_name) and not allowed_values:
        return CardinalityViolation(
            metric=metric_name,
            label=label_name,
            reason="label looks unbounded and has no approved exception",
        )

    if not allowed_values:
        return CardinalityViolation(
            metric=metric_name,
            label=label_name,
            reason="allowed label values must be documented",
        )

    if len(set(allowed_values)) > max_allowed_values:
        return CardinalityViolation(
            metric=metric_name,
            label=label_name,
            reason=(
                "allowed label values exceed "
                f"cardinality budget of {max_allowed_values}"
            ),
        )

    return None


def _index_exceptions(exceptions: Iterable[Dict]) -> Dict:
    return {
        (exception["metric"], exception["label"]): exception
        for exception in exceptions
    }


def _has_approved_exception(exception: Optional[Dict]) -> bool:
    if exception is None:
        return False

    required_fields = ("owner", "approved_by", "reason")
    return all(exception.get(field) for field in required_fields)


def _looks_unbounded(label_name: str) -> bool:
    normalized = label_name.lower()
    return any(hint in normalized for hint in UNBOUNDED_LABEL_HINTS)
