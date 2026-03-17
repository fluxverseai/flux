"""Project tracking for Flux — register, list, and prune tracked projects.

Tracked projects are stored in ``~/.flux/projects.json`` with the schema::

    {"projects": [{"path": "...", "name": "...", "registered_at": "..."}]}
"""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from flux_cli.lib.paths import projects_path


def _load_projects_file(path: Path | None = None) -> dict[str, Any]:
    """Load the projects index, returning an empty structure if missing."""
    path = path or projects_path()
    if not path.exists():
        return {"projects": []}
    with open(path) as f:
        return json.load(f)


def _save_projects_file(data: dict[str, Any], path: Path | None = None) -> None:
    """Atomically write the projects index."""
    path = path or projects_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with open(fd, "w") as f:
            json.dump(data, f, indent=2)
        Path(tmp).replace(path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def register_project(project_path: Path, name: str, *, projects_file: Path | None = None) -> None:
    """Register a project path. No-op if already registered."""
    data = _load_projects_file(projects_file)
    abs_path = str(project_path.resolve())

    # Skip if already registered
    for entry in data["projects"]:
        if entry["path"] == abs_path:
            return

    data["projects"].append({
        "path": abs_path,
        "name": name,
        "registered_at": datetime.now(tz=UTC).isoformat(),
    })
    _save_projects_file(data, projects_file)


def list_projects(*, projects_file: Path | None = None) -> list[dict[str, Any]]:
    """Return all tracked projects."""
    data = _load_projects_file(projects_file)
    return data["projects"]


def detect_stale_projects(*, projects_file: Path | None = None) -> list[dict[str, Any]]:
    """Return tracked projects whose paths no longer exist on disk."""
    projects = list_projects(projects_file=projects_file)
    return [p for p in projects if not Path(p["path"]).exists()]


def remove_stale_projects(*, projects_file: Path | None = None) -> list[dict[str, Any]]:
    """Remove all stale projects and return the removed entries."""
    data = _load_projects_file(projects_file)
    stale = [p for p in data["projects"] if not Path(p["path"]).exists()]
    if stale:
        stale_paths = {p["path"] for p in stale}
        data["projects"] = [p for p in data["projects"] if p["path"] not in stale_paths]
        _save_projects_file(data, projects_file)
    return stale
