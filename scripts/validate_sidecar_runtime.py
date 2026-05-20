"""Validate sidecar compose hardening from CI or a shell."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agent.sidecar_runtime import (  # noqa: E402
    validate_sidecar_compose_file,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate sidecar compose hardening"
    )
    parser.add_argument("compose_file", help="Path to docker-compose.yml")
    args = parser.parse_args()

    validate_sidecar_compose_file(args.compose_file)


if __name__ == "__main__":
    main()
