"""CLI command: version."""

from __future__ import annotations

import argparse


def cmd_version(args: argparse.Namespace) -> None:
    """flux version [--check] — show installed version and optionally check for updates."""
    from flux_cli.version import format_version_output

    check = getattr(args, "check", False)
    print(format_version_output(check=check))
