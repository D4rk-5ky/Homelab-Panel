"""Side-effect-free CLI inspection shared by the project entry points."""

import argparse
from pathlib import Path


def add_version_argument(parser: argparse.ArgumentParser) -> None:
    """Expose the packaged VERSION without copying version strings into programs."""
    version = (Path(__file__).resolve().parents[1] / "VERSION").read_text(encoding="utf-8").strip()
    parser.add_argument("--version", action="version", version=f"%(prog)s {version}",
                        help="show the packaged Homelab Panel version and exit without starting work")


def parse_service_cli(description: str) -> None:
    """Exit for inspection/errors before service config, imports or background I/O."""
    parser = argparse.ArgumentParser(
        description=description,
        epilog="Run with no arguments to start. Runtime settings come from the configuration files; no dry-run mode is provided.",
        allow_abbrev=False,
    )
    add_version_argument(parser)
    parser.parse_args()
