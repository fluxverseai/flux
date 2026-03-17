"""Flux setup — fresh install and migration from old layout.

Provides ``run_setup()`` which:
  1. Creates the ``~/.flux/`` directory structure.
  2. Writes ``config.toml`` with platform defaults.
  3. Installs the bundled Flux skill to ``~/.claude/skills/flux/SKILL.md``.
  4. Detects and reports missing external dependencies.
  5. Optionally migrates data from the old ``marketplace/`` repo layout.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from flux_cli.config import default_config, save_config
from flux_cli.paths import (
    config_path,
    flux_home,
    launchers_dir,
    mcps_dir,
    sandbox_dir,
    skills_dir,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_PYTHON = (3, 11)
REQUIRED_TOOLS = ("uv", "git", "node", "claude")

_BUNDLED_SKILL = Path(__file__).resolve().parent / "data" / "skills" / "flux" / "SKILL.md"


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class SetupResult:
    """Collects everything ``run_setup`` did so callers can report it."""

    dirs_created: list[str] = field(default_factory=list)
    config_written: bool = False
    skill_installed: bool = False
    missing_deps: list[str] = field(default_factory=list)
    migration: MigrationResult | None = None


@dataclass
class MigrationResult:
    """Summary of what the migration step copied."""

    detected: bool = False
    mcps_copied: list[str] = field(default_factory=list)
    skills_copied: list[str] = field(default_factory=list)
    registry_entries: int = 0


# ---------------------------------------------------------------------------
# Directory creation
# ---------------------------------------------------------------------------

def _ensure_dirs(result: SetupResult) -> None:
    dirs = [
        flux_home(),
        mcps_dir(),
        launchers_dir(),
        skills_dir(),
        sandbox_dir(),
    ]
    for d in dirs:
        if not d.exists():
            d.mkdir(parents=True, exist_ok=True)
            result.dirs_created.append(str(d))


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def _ensure_config(result: SetupResult) -> None:
    target = config_path()
    if not target.exists():
        cfg = default_config()
        save_config(cfg, path=target)
        result.config_written = True


# ---------------------------------------------------------------------------
# Skill installation
# ---------------------------------------------------------------------------

def _claude_skill_dir() -> Path:
    return Path.home() / ".claude" / "skills" / "flux"


def install_skill(
    *,
    bundled_path: Path | None = None,
    target_dir: Path | None = None,
) -> bool:
    """Copy the bundled Flux skill to the Claude skills directory."""
    src = bundled_path or _BUNDLED_SKILL
    dest_dir = target_dir or _claude_skill_dir()

    if not src.exists():
        return False

    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest_dir / "SKILL.md")
    return True


# ---------------------------------------------------------------------------
# Dependency detection
# ---------------------------------------------------------------------------

def check_dependencies() -> list[str]:
    """Return a list of missing required tools."""
    import sys

    missing: list[str] = []

    if sys.version_info < MIN_PYTHON:
        missing.append(f"python>={MIN_PYTHON[0]}.{MIN_PYTHON[1]}")

    for tool in REQUIRED_TOOLS:
        if shutil.which(tool) is None:
            missing.append(tool)

    return missing


# ---------------------------------------------------------------------------
# Migration from old layout
# ---------------------------------------------------------------------------

def _find_old_marketplace(search_path: Path | None = None) -> Path | None:
    if search_path is not None:
        candidate = search_path / "marketplace" / "marketplace.json"
        return candidate if candidate.exists() else None

    repo_root = Path(__file__).resolve().parent.parent.parent
    candidate = repo_root / "marketplace" / "marketplace.json"
    return candidate if candidate.exists() else None


def _convert_entry(entry: dict[str, Any]) -> dict[str, Any]:
    new = dict(entry)
    if new.get("type") == "git-submodule":
        new["type"] = "github"
        source_dir = new.get("source_dir", "")
        parts = source_dir.split("/")
        if parts:
            new.setdefault("repo", parts[-1])
    return new


def _migrate_old_layout(
    result: SetupResult,
    *,
    search_path: Path | None = None,
) -> None:
    mig = MigrationResult()
    result.migration = mig

    old_manifest_path = _find_old_marketplace(search_path=search_path)
    if old_manifest_path is None:
        return

    mig.detected = True
    old_root = old_manifest_path.parent

    with open(old_manifest_path) as f:
        old_data = json.load(f)

    new_registry: dict[str, Any] = {"mcp_definitions": {}, "skill_definitions": {}}

    for name, entry in old_data.get("mcp_definitions", {}).items():
        converted = _convert_entry(entry)
        new_registry["mcp_definitions"][name] = converted

        source_dir = entry.get("source_dir", "")
        if source_dir:
            base = search_path if search_path is not None else old_manifest_path.parent.parent
            src = (base / source_dir).resolve()
            if not src.is_relative_to(base.resolve()):
                continue
            dest = mcps_dir() / Path(name).name
            if src.is_dir() and not dest.exists():
                shutil.copytree(src, dest, dirs_exist_ok=True)
                mig.mcps_copied.append(name)

    for name, entry in old_data.get("skill_definitions", {}).items():
        converted = _convert_entry(entry)
        new_registry["skill_definitions"][name] = converted

        source_dir = entry.get("source_dir", "")
        if source_dir:
            base = search_path if search_path is not None else old_manifest_path.parent.parent
            src = (base / source_dir).resolve()
            if not src.is_relative_to(base.resolve()):
                continue
            dest = skills_dir() / Path(name).name
            if src.is_dir() and not dest.exists():
                shutil.copytree(src, dest, dirs_exist_ok=True)
                mig.skills_copied.append(name)

    old_launchers = old_root / "mcps" / "launchers"
    if old_launchers.is_dir():
        for launcher_file in old_launchers.iterdir():
            dest = launchers_dir() / launcher_file.name
            if not dest.exists():
                shutil.copy2(launcher_file, dest)

    total_entries = len(new_registry["mcp_definitions"]) + len(new_registry["skill_definitions"])
    mig.registry_entries = total_entries

    if total_entries > 0:
        registry_file = flux_home() / "registry.json"
        existing: dict[str, Any] = {}
        if registry_file.exists():
            with open(registry_file) as f:
                existing = json.load(f)

        for section in ("mcp_definitions", "skill_definitions"):
            merged = existing.get(section, {})
            merged.update(new_registry[section])
            existing[section] = merged

        with open(registry_file, "w") as f:
            json.dump(existing, f, indent=2)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_setup(
    *,
    search_path: Path | None = None,
    skill_target_dir: Path | None = None,
    bundled_skill_path: Path | None = None,
) -> SetupResult:
    """Run the full Flux setup sequence."""
    result = SetupResult()

    _ensure_dirs(result)
    _ensure_config(result)

    result.skill_installed = install_skill(
        bundled_path=bundled_skill_path,
        target_dir=skill_target_dir,
    )

    result.missing_deps = check_dependencies()
    _migrate_old_layout(result, search_path=search_path)

    return result
