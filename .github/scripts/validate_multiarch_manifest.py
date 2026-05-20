#!/usr/bin/env python3
"""Validate per-architecture image digests before manifest publication."""

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from src.release.multiarch import (  # noqa: E402
    MultiArchManifestError,
    build_release_summary,
    load_digest_manifest,
    validate_architecture_digests,
    write_validated_manifest,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate architecture digests before manifest push."
    )
    parser.add_argument("manifest", help="Input JSON/YAML digest manifest")
    parser.add_argument(
        "--arch",
        action="append",
        dest="architectures",
        help="Required architecture. Can be repeated.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path for the validated manifest-push digest manifest.",
    )
    parser.add_argument(
        "--summary",
        default=None,
        help="Optional GitHub step summary path.",
    )
    args = parser.parse_args()

    try:
        manifest = load_digest_manifest(args.manifest)
        validated = validate_architecture_digests(
            manifest,
            required_architectures=args.architectures,
        )
    except MultiArchManifestError as exc:
        print(f"multi-arch validation failed: {exc}", file=sys.stderr)
        return 2

    write_validated_manifest(validated, args.output)
    summary = build_release_summary(validated)
    print(summary)

    summary_path = args.summary or os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with Path(summary_path).open("a", encoding="utf8") as handle:
            handle.write("### Multi-architecture manifest validation\n\n")
            handle.write(summary)
            handle.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
