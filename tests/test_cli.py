import sys

import pytest

from src.cli import main


def run_cli(monkeypatch, args):
    monkeypatch.setattr(sys, "argv", ["ao", *args])
    main.cli()


def test_deploy_dry_run_validates_manifest_without_deploying(
    tmp_path,
    monkeypatch,
    capsys,
):
    manifest = tmp_path / "agent.yaml"
    manifest.write_text("name: worker\nimage: worker:latest\n")
    deployed = []
    monkeypatch.setattr(
        main,
        "_deploy_agent",
        lambda path, parsed: deployed.append((path, parsed)),
    )

    run_cli(monkeypatch, ["deploy", str(manifest), "--dry-run"])

    assert deployed == []
    output = capsys.readouterr().out
    assert "Dry-run valid manifest" in output
    assert "image, name" in output


def test_deploy_dry_run_rejects_missing_manifest(monkeypatch):
    with pytest.raises(SystemExit, match="Manifest not found"):
        run_cli(monkeypatch, ["deploy", "missing.yaml", "--dry-run"])


def test_deploy_dry_run_rejects_non_mapping_manifest(tmp_path, monkeypatch):
    manifest = tmp_path / "agent.yaml"
    manifest.write_text("- worker\n")

    with pytest.raises(SystemExit, match="Manifest must be a mapping"):
        run_cli(monkeypatch, ["deploy", str(manifest), "--dry-run"])


def test_deploy_without_dry_run_invokes_backend(
    tmp_path,
    monkeypatch,
):
    manifest = tmp_path / "agent.yaml"
    manifest.write_text("name: worker\n")
    deployed = []
    monkeypatch.setattr(
        main,
        "_deploy_agent",
        lambda path, parsed: deployed.append((path, parsed)),
    )

    run_cli(monkeypatch, ["deploy", str(manifest)])

    assert deployed == [(str(manifest), {"name": "worker"})]
