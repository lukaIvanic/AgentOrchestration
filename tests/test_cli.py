import pytest

from src.cli.main import cli


def test_deploy_blocks_unbounded_metrics_label(tmp_path, capsys, monkeypatch):
    manifest = tmp_path / "agent.yaml"
    manifest.write_text(
        """
name: worker
metrics:
  - name: task_events_total
    labels:
      task_id:
"""
    )

    monkeypatch.setattr("sys.argv", ["ao", "deploy", str(manifest)])

    with pytest.raises(SystemExit) as exc:
        cli()

    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert "metrics label cardinality policy failed" in captured.err
    assert "task_events_total.task_id" in captured.err


def test_deploy_allows_bounded_metrics_label(tmp_path, capsys, monkeypatch):
    manifest = tmp_path / "agent.yaml"
    manifest.write_text(
        """
name: worker
metrics:
  - name: task_events_total
    labels:
      status: [pending, running, completed, failed]
      queue: [default, priority]
"""
    )

    monkeypatch.setattr("sys.argv", ["ao", "deploy", str(manifest)])

    cli()

    captured = capsys.readouterr()
    assert "Metrics label cardinality check passed" in captured.out
    assert f"Deploying agent from manifest: {manifest}" in captured.out
