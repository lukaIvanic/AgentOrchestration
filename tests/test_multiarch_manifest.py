import json
import subprocess
import sys

import pytest

from src.release.multiarch import (
    MultiArchManifestError,
    build_release_summary,
    build_validated_manifest,
    validate_architecture_digests,
)


VALID_AMD64 = "sha256:" + "a" * 64
VALID_ARM64 = "sha256:" + "b" * 64


def test_validates_required_architectures_before_manifest_push():
    manifest = {
        "required_architectures": ["linux/amd64", "linux/arm64"],
        "architectures": [
            {
                "architecture": "linux/amd64",
                "digest": VALID_AMD64,
                "validation": {
                    "tests": {"status": "passed", "digest": VALID_AMD64},
                    "scan": {"status": "passed", "digest": VALID_AMD64},
                },
            },
            {
                "architecture": "linux/arm64",
                "digest": VALID_ARM64,
                "validation": {
                    "tests": {"status": "success", "digest": VALID_ARM64},
                    "scan": {"status": "ok", "digest": VALID_ARM64},
                },
            },
        ],
    }

    validated = validate_architecture_digests(manifest)

    assert [entry["architecture"] for entry in validated] == [
        "linux/amd64",
        "linux/arm64",
    ]
    assert [entry["digest"] for entry in validated] == [
        VALID_AMD64,
        VALID_ARM64,
    ]


def test_missing_architecture_gate_fails_release():
    manifest = {
        "required_architectures": ["linux/amd64", "linux/arm64"],
        "architectures": [
            {
                "architecture": "linux/amd64",
                "digest": VALID_AMD64,
                "validation": {
                    "tests": {"status": "passed", "digest": VALID_AMD64},
                    "scan": {"status": "passed", "digest": VALID_AMD64},
                },
            }
        ],
    }

    with pytest.raises(MultiArchManifestError, match="linux/arm64"):
        validate_architecture_digests(manifest)


def test_stale_validation_digest_fails_release():
    manifest = {
        "architectures": [
            {
                "architecture": "linux/amd64",
                "digest": VALID_AMD64,
                "validation": {
                    "tests": {"status": "passed", "digest": VALID_ARM64},
                    "scan": {"status": "passed", "digest": VALID_AMD64},
                },
            }
        ],
    }

    with pytest.raises(MultiArchManifestError, match="tests digest"):
        validate_architecture_digests(manifest)


def test_failed_scan_excludes_digest_from_manifest():
    manifest = {
        "architectures": [
            {
                "architecture": "linux/arm64",
                "digest": VALID_ARM64,
                "validation": {
                    "tests": {"status": "passed", "digest": VALID_ARM64},
                    "scan": {"status": "failed", "digest": VALID_ARM64},
                },
            }
        ],
    }

    with pytest.raises(
        MultiArchManifestError,
        match="scan validation did not pass",
    ):
        validate_architecture_digests(manifest)


def test_release_summary_lists_architecture_digest_and_status():
    summary = build_release_summary(
        [
            {
                "architecture": "linux/arm64",
                "digest": VALID_ARM64,
                "validation": {"tests": "passed", "scan": "passed"},
            },
            {
                "architecture": "linux/amd64",
                "digest": VALID_AMD64,
                "validation": {"tests": "passed", "scan": "passed"},
            },
        ]
    )

    assert "Architecture | Digest | Tests | Scan" in summary
    assert f"linux/amd64 | {VALID_AMD64} | passed | passed" in summary
    assert f"linux/arm64 | {VALID_ARM64} | passed | passed" in summary


def test_validated_manifest_contains_only_push_safe_digests():
    validated = [
        {
            "architecture": "linux/arm64",
            "digest": VALID_ARM64,
            "validation": {"tests": "passed", "scan": "passed"},
        },
        {
            "architecture": "linux/amd64",
            "digest": VALID_AMD64,
            "validation": {"tests": "passed", "scan": "passed"},
        },
    ]

    manifest = build_validated_manifest(validated)

    assert manifest == {
        "images": [
            {"architecture": "linux/amd64", "digest": VALID_AMD64},
            {"architecture": "linux/arm64", "digest": VALID_ARM64},
        ]
    }


def test_actions_script_writes_validated_manifest_and_summary(tmp_path):
    input_path = tmp_path / "digests.json"
    output_path = tmp_path / "validated.json"
    summary_path = tmp_path / "summary.md"
    input_path.write_text(
        json.dumps(
            {
                "required_architectures": ["linux/amd64", "linux/arm64"],
                "architectures": [
                    {
                        "architecture": "linux/amd64",
                        "digest": VALID_AMD64,
                        "validation": {
                            "tests": {
                                "status": "passed",
                                "digest": VALID_AMD64,
                            },
                            "scan": {
                                "status": "passed",
                                "digest": VALID_AMD64,
                            },
                        },
                    },
                    {
                        "architecture": "linux/arm64",
                        "digest": VALID_ARM64,
                        "validation": {
                            "tests": {
                                "status": "passed",
                                "digest": VALID_ARM64,
                            },
                            "scan": {
                                "status": "passed",
                                "digest": VALID_ARM64,
                            },
                        },
                    },
                ],
            }
        ),
        encoding="utf8",
    )

    result = subprocess.run(
        [
            sys.executable,
            ".github/scripts/validate_multiarch_manifest.py",
            str(input_path),
            "--output",
            str(output_path),
            "--summary",
            str(summary_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert f"linux/amd64 | {VALID_AMD64} | passed | passed" in result.stdout
    assert json.loads(output_path.read_text(encoding="utf8")) == {
        "images": [
            {"architecture": "linux/amd64", "digest": VALID_AMD64},
            {"architecture": "linux/arm64", "digest": VALID_ARM64},
        ]
    }
    assert "Multi-architecture manifest validation" in summary_path.read_text(
        encoding="utf8"
    )


def test_actions_script_fails_before_output_on_unscanned_digest(tmp_path):
    input_path = tmp_path / "digests.json"
    output_path = tmp_path / "validated.json"
    input_path.write_text(
        json.dumps(
            {
                "architectures": [
                    {
                        "architecture": "linux/amd64",
                        "digest": VALID_AMD64,
                        "validation": {
                            "tests": {
                                "status": "passed",
                                "digest": VALID_AMD64,
                            },
                            "scan": {
                                "status": "failed",
                                "digest": VALID_AMD64,
                            },
                        },
                    }
                ],
            }
        ),
        encoding="utf8",
    )

    result = subprocess.run(
        [
            sys.executable,
            ".github/scripts/validate_multiarch_manifest.py",
            str(input_path),
            "--output",
            str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "scan validation did not pass" in result.stderr
    assert not output_path.exists()
