import json

import pytest

from src.cli.main import cli
from src.common.metrics_cardinality import validate_metrics_schema


def test_metrics_schema_accepts_documented_bounded_labels():
    report = validate_metrics_schema(
        {
            "metrics": [
                {
                    "name": "task_events_total",
                    "labels": [
                        {
                            "name": "event_type",
                            "owner": "observability",
                            "values": ["queued", "started", "completed"],
                        },
                        {
                            "name": "worker_pool",
                            "owner": "runtime",
                            "values": ["default", "gpu"],
                        },
                    ],
                },
            ],
        },
    )

    assert report.passed
    assert report.checked_labels == 2


def test_metrics_schema_blocks_unbounded_label_without_exception():
    report = validate_metrics_schema(
        {
            "metrics": [
                {
                    "name": "worker_events_total",
                    "labels": [
                        {
                            "name": "worker_id",
                            "owner": "runtime",
                        },
                    ],
                },
            ],
        },
    )

    assert not report.passed
    assert report.violations[0].metric == "worker_events_total"
    assert report.violations[0].label == "worker_id"


def test_metrics_schema_allows_unbounded_label_with_approved_exception():
    report = validate_metrics_schema(
        {
            "metrics": [
                {
                    "name": "worker_events_total",
                    "labels": [
                        {
                            "name": "worker_id",
                            "owner": "runtime",
                        },
                    ],
                },
            ],
            "exceptions": [
                {
                    "metric": "worker_events_total",
                    "label": "worker_id",
                    "owner": "observability",
                    "approved_by": "sre-lead",
                    "reason": "Temporary rollout debugging for one release.",
                },
            ],
        },
    )

    assert report.passed


def test_metrics_schema_blocks_labels_over_cardinality_budget():
    report = validate_metrics_schema(
        {
            "metrics": [
                {
                    "name": "task_events_total",
                    "labels": [
                        {
                            "name": "queue",
                            "owner": "runtime",
                            "values": ["q1", "q2", "q3"],
                        },
                    ],
                },
            ],
        },
        max_allowed_values=2,
    )

    assert not report.passed
    assert "cardinality budget" in report.violations[0].reason


def test_deploy_blocks_rollout_when_metrics_schema_fails(
    tmp_path,
    monkeypatch,
    capsys,
):
    manifest = tmp_path / "agent.json"
    manifest.write_text("{}", encoding="utf-8")
    metrics_schema = tmp_path / "metrics.json"
    metrics_schema.write_text(
        json.dumps(
            {
                "metrics": [
                    {
                        "name": "worker_events_total",
                        "labels": [
                            {
                                "name": "session_id",
                                "owner": "runtime",
                            },
                        ],
                    },
                ],
            },
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "ao",
            "deploy",
            str(manifest),
            "--metrics-schema",
            str(metrics_schema),
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        cli()

    assert exc_info.value.code == 2
    assert "metrics cardinality check failed" in capsys.readouterr().err


def test_deploy_continues_when_metrics_schema_passes(
    tmp_path,
    monkeypatch,
    capsys,
):
    manifest = tmp_path / "agent.json"
    manifest.write_text("{}", encoding="utf-8")
    metrics_schema = tmp_path / "metrics.json"
    metrics_schema.write_text(
        json.dumps(
            {
                "metrics": [
                    {
                        "name": "task_events_total",
                        "labels": [
                            {
                                "name": "event_type",
                                "owner": "observability",
                                "values": ["queued", "completed"],
                            },
                        ],
                    },
                ],
            },
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "ao",
            "deploy",
            str(manifest),
            "--metrics-schema",
            str(metrics_schema),
        ],
    )

    cli()

    output = capsys.readouterr().out
    assert "metrics cardinality check passed" in output
    assert "Deploying agent from manifest" in output


def test_deploy_checks_metrics_schema_declared_by_manifest(
    tmp_path,
    monkeypatch,
    capsys,
):
    metrics_schema = tmp_path / "metrics.json"
    metrics_schema.write_text(
        json.dumps(
            {
                "metrics": [
                    {
                        "name": "worker_events_total",
                        "labels": [
                            {
                                "name": "worker_id",
                                "owner": "runtime",
                            },
                        ],
                    },
                ],
            },
        ),
        encoding="utf-8",
    )
    manifest = tmp_path / "agent.json"
    manifest.write_text(
        json.dumps({"metrics_schema": metrics_schema.name}),
        encoding="utf-8",
    )
    monkeypatch.setattr("sys.argv", ["ao", "deploy", str(manifest)])

    with pytest.raises(SystemExit) as exc_info:
        cli()

    assert exc_info.value.code == 2
    assert "worker_events_total.worker_id" in capsys.readouterr().err


def test_deploy_checks_metrics_embedded_in_manifest(
    tmp_path,
    monkeypatch,
    capsys,
):
    manifest = tmp_path / "agent.json"
    manifest.write_text(
        json.dumps(
            {
                "metrics": [
                    {
                        "name": "task_events_total",
                        "labels": [
                            {
                                "name": "event_type",
                                "owner": "observability",
                                "values": ["queued", "completed"],
                            },
                        ],
                    },
                ],
            },
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("sys.argv", ["ao", "deploy", str(manifest)])

    cli()

    assert "metrics cardinality check passed" in capsys.readouterr().out
