"""manifest.py — Load and save the v1 registry and per-project flux.json files."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from flux_cli.paths import registry_path

REGISTRY_VERSION = "1.0.0"


def _empty_registry() -> dict[str, Any]:
    """Return an empty v1 registry structure."""
    return {
        "version": REGISTRY_VERSION,
        "mcp_definitions": {},
        "skill_definitions": {},
    }


# ---------------------------------------------------------------------------
# v1 registry (at ~/.flux/registry.json via paths.registry_path())
# ---------------------------------------------------------------------------


def load_registry(path: Path | None = None) -> dict[str, Any]:
    """Load the v1 registry from *path*.

    If *path* is ``None``, uses the canonical registry_path() location.
    When the file does not exist an empty registry is created on disk and returned.
    """
    if path is None:
        path = registry_path()

    if not path.exists():
        reg = _empty_registry()
        save_registry(reg, path)
        return reg

    with open(path) as f:
        data = json.load(f)
    if not isinstance(data, dict):
        msg = f"Registry at {path} is not a JSON object — got {type(data).__name__}"
        raise ValueError(msg)
    return data


def save_registry(data: dict[str, Any], path: Path | None = None) -> None:
    """Atomically write the v1 registry to *path*."""
    if path is None:
        path = registry_path()

    _atomic_json_write(path, data)


# ---------------------------------------------------------------------------
# Per-project flux.json
# ---------------------------------------------------------------------------


def load_flux_json(project_dir: Path) -> dict[str, Any] | None:
    """Load a project's flux.json, returning None if it doesn't exist."""
    path = project_dir / "flux.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def save_flux_json(project_dir: Path, data: dict[str, Any]) -> None:
    """Atomically write a project's flux.json."""
    _atomic_json_write(project_dir / "flux.json", data)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _atomic_json_write(path: Path, data: dict[str, Any]) -> None:
    """Write JSON data to a file atomically via temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with open(fd, "w") as f:
            json.dump(data, f, indent=2)
        Path(tmp).replace(path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
