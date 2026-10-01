"""Project version and shared information-only CLI helpers."""

import argparse
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = PROJECT_ROOT / "VERSION"


def get_project_version() -> str:
    """Return the release version from the root VERSION file."""
    try:
        version = VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"
    return version or "unknown"


def build_info_parser(description: str) -> argparse.ArgumentParser:
    """Build a no-runtime-options parser with safe help and version output."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {get_project_version()}",
        help="show the Homelab Panel project version and exit",
    )
    return parser


def add_version_argument(parser: argparse.ArgumentParser) -> None:
    """Add the shared --version flag to a parser that owns other options."""
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {get_project_version()}",
        help="show the Homelab Panel project version and exit",
    )
