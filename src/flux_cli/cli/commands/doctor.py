"""CLI commands: setup, doctor."""

from __future__ import annotations

import argparse
import subprocess
import sys

from flux_cli.health import run_doctor_checks
from flux_cli.manifest import load_registry
from flux_cli.paths import flux_home
from flux_cli.secrets import load_secrets_index


def cmd_doctor(args: argparse.Namespace) -> None:
    """flux doctor — check the Flux environment."""
    print("\n\U0001fa7a FLUX DOCTOR \u2014 Environment Health Check\n")

    reg = load_registry()
    mcp_defs = reg.get('mcp_definitions', {})

    try:
        secrets_idx = load_secrets_index()
    except Exception:
        secrets_idx = {}

    fh = flux_home()
    reg_path = fh / "registry.json"

    checks = run_doctor_checks(
        flux_root=fh,
        registry_path=reg_path if reg_path.exists() else None,
        mcp_definitions=mcp_defs,
        secrets_index=secrets_idx,
    )

    all_ok = True
    print("  \U0001f4e6 Environment & Dependencies")
    for c in checks:
        if c.passed:
            print(f"  \u2705 {c.label}")
        elif c.warning:
            all_ok = False
            print(f"  \u26a0\ufe0f  {c.label}")
            if c.fix_hint:
                print(f"     Fix: {c.fix_hint}")
        else:
            all_ok = False
            print(f"  \u274c {c.label}")
            if c.fix_hint:
                print(f"     Fix: {c.fix_hint}")

    print()
    if all_ok:
        print("\u2705 All checks passed \u2014 Flux environment is healthy!\n")
    else:
        print("\u26a0\ufe0f  Some issues were found.\n")


def cmd_setup(args: argparse.Namespace) -> None:
    """flux setup — initialise ~/.flux/ or run setup_cmd for a specific MCP."""
    name = getattr(args, 'name', None)

    if not name:
        from flux_cli.setup_flux import run_setup

        print("\n  FLUX SETUP\n")
        result = run_setup()

        if result.dirs_created:
            print(f"  Created directories: {len(result.dirs_created)}")
            for d in result.dirs_created:
                print(f"    {d}")

        if result.config_written:
            print("  Wrote config.toml with platform defaults")
        else:
            print("  config.toml already exists \u2014 skipped")

        if result.skill_installed:
            print("  Installed Flux skill to ~/.claude/skills/flux/SKILL.md")
        else:
            print("  Flux skill not installed (bundled data missing)")

        if result.missing_deps:
            print(f"\n  Missing dependencies: {', '.join(result.missing_deps)}")
        else:
            print("  All dependencies found")

        mig = result.migration
        if mig and mig.detected:
            print("\n  Migration from old layout:")
            print(f"    Registry entries: {mig.registry_entries}")
            if mig.mcps_copied:
                print(f"    MCPs copied: {', '.join(mig.mcps_copied)}")
            if mig.skills_copied:
                print(f"    Skills copied: {', '.join(mig.skills_copied)}")
        elif mig and not mig.detected:
            print("  No old marketplace layout detected \u2014 nothing to migrate")

        print("\n  Setup complete.\n")
        return

    reg = load_registry()
    entry = reg.get('mcp_definitions', {}).get(name)
    if not entry:
        print(f"\u274c MCP '{name}' not found in registry")
        sys.exit(1)

    setup_cmd = entry.get('auth', {}).get('setup_cmd')
    if not setup_cmd:
        print(f"\u2139\ufe0f  '{name}' has no setup_cmd configured \u2014 nothing to run")
        return

    print(f"\U0001f527 Running setup for '{name}': {' '.join(setup_cmd)}")
    result = subprocess.run(setup_cmd)  # noqa: S603
    if result.returncode == 0:
        print(f"\u2705 Setup complete for '{name}'")
    else:
        print(f"\u26a0\ufe0f  Setup failed (exit {result.returncode})")
        sys.exit(result.returncode)
