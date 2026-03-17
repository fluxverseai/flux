"""Extended sandbox lifecycle — creation, agent execution, listing, and cleanup.

Builds on ``lib/sandbox.py`` (run-id generation, meta helpers) and adds:
- Pre-flight validation via ``flux_cli.lib.preflight``
- Scoped ``.mcp.json`` generation via ``flux_cli.lib.sync``
- Agent invocation (``claude --print``) with timeout support
- ``flux run list`` and ``flux run clean`` with keep-recent logic
- Manifest-file loading for ``flux run --file``
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from flux_cli.lib.paths import sandbox_dir
from flux_cli.lib.preflight import run_preflight
from flux_cli.lib.sync import _build_server_entry, _load_registry_for_sync

# ---------------------------------------------------------------------------
# Run ID
# ---------------------------------------------------------------------------


def _token_hex(n: int) -> str:
    """Generate n random bytes as a hex string without importing secrets."""
    return os.urandom(n).hex()


def generate_run_id() -> str:
    """Generate a run ID: YYYYMMDD-XXXX (e.g. 20260315-a3f2)."""
    date_part = datetime.now().strftime("%Y%m%d")
    hex_part = _token_hex(2)  # 4 hex chars
    return f"{date_part}-{hex_part}"


# ---------------------------------------------------------------------------
# Sandbox creation
# ---------------------------------------------------------------------------


def create_sandbox(
    run_id: str,
    mcps: list[str],
    skills: list[str] | None = None,
    registry: dict[str, Any] | None = None,
    *,
    skip_preflight: bool = False,
) -> Path:
    """Create ``~/.flux/sandbox/<run-id>/`` with scoped .mcp.json and workspace.

    Layout::

        sandbox/<run-id>/
            .mcp.json      -- scoped to this run's MCPs only
            workspace/     -- scratch dir (cwd for claude)
            run-meta.json  -- written later by write_run_meta()

    Returns the sandbox path.

    Raises
    ------
    PreflightError
        If any pre-flight check fails (unless *skip_preflight* is True).
    """
    skills = skills or []

    if registry is None:
        registry = _load_registry_for_sync()

    # Pre-flight validation
    if not skip_preflight:
        result = run_preflight(mcps, skills, registry=registry)
        if not result.ok:
            msg = "Pre-flight checks failed:\n" + "\n".join(f"  - {e}" for e in result.errors)
            raise PreflightError(msg, errors=result.errors)

    base = sandbox_dir()
    # Validate run_id to prevent path traversal
    if "/" in run_id or "\\" in run_id or run_id.startswith("."):
        msg = f"Invalid run_id: {run_id!r}"
        raise ValueError(msg)
    sandbox_path = base / run_id
    workspace = sandbox_path / "workspace"

    sandbox_path.mkdir(parents=True, exist_ok=True)
    workspace.mkdir(exist_ok=True)

    # Build scoped .mcp.json using sync engine's _build_server_entry
    mcp_defs = registry.get("mcp_definitions", {})
    mcp_servers: dict[str, Any] = {}
    for mcp_name in mcps:
        if mcp_name in mcp_defs:
            mcp_servers[mcp_name] = _build_server_entry(mcp_name, mcp_defs[mcp_name])

    mcp_config = {"mcpServers": mcp_servers}
    (sandbox_path / ".mcp.json").write_text(json.dumps(mcp_config, indent=2))

    return sandbox_path


class PreflightError(Exception):
    """Raised when pre-flight checks fail."""

    def __init__(self, message: str, errors: list[str] | None = None) -> None:
        super().__init__(message)
        self.errors = errors or []


# ---------------------------------------------------------------------------
# Run metadata
# ---------------------------------------------------------------------------


def write_run_meta(
    sandbox_path: Path,
    run_id: str,
    task: str,
    mcps: list[str],
    status: str = "running",
    name: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Write initial run-meta.json."""
    meta: dict[str, Any] = {
        "id": run_id,
        "name": name or run_id,
        "task": task,
        "mcps": mcps,
        "status": status,
        "started_at": datetime.now().isoformat(),
    }
    meta.update(extra)
    _atomic_json_write(sandbox_path / "run-meta.json", meta)
    return meta


def update_run_meta(sandbox_path: Path, **kwargs: Any) -> None:
    """Merge kwargs into the existing run-meta.json."""
    meta_path = sandbox_path / "run-meta.json"
    meta: dict[str, Any] = {}
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
    meta.update(kwargs)
    _atomic_json_write(meta_path, meta)


def _atomic_json_write(path: Path, data: dict[str, Any]) -> None:
    """Write JSON atomically via temp file + rename."""
    import tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with open(fd, "w") as f:
            json.dump(data, f, indent=2)
        Path(tmp).replace(path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


# ---------------------------------------------------------------------------
# Agent execution
# ---------------------------------------------------------------------------


def _find_claude() -> str | None:
    """Locate the claude binary."""
    found = shutil.which("claude")
    if found:
        return found
    fallback = os.path.expanduser("~/.local/bin/claude")
    if os.path.exists(fallback):
        return fallback
    return None


def run_agent(
    sandbox_path: Path,
    task: str,
    *,
    timeout: int | None = None,
    run_id: str | None = None,
) -> int:
    """Invoke ``claude --print <task> --mcp-config <path>`` as a subprocess.

    Captures exit code, updates run-meta.json with status and timing.
    If *timeout* is set, kills the process after that many seconds.

    Returns the process exit code.
    """
    mcp_config_path = sandbox_path / ".mcp.json"
    workspace = sandbox_path / "workspace"
    run_id = run_id or sandbox_path.name

    claude_bin = _find_claude()
    if not claude_bin:
        update_run_meta(sandbox_path, status="failed", exit_code=1)
        return 1

    cmd = [
        claude_bin,
        "--print", task,
        "--mcp-config", str(mcp_config_path),
    ]

    start = time.monotonic()
    try:
        # Use Popen with start_new_session so we can kill the entire process group on timeout
        proc = subprocess.Popen(  # noqa: S603
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(workspace),
            start_new_session=True,
        )
        try:
            proc.communicate(timeout=timeout)
            exit_code = proc.returncode
        except subprocess.TimeoutExpired:
            # Kill entire process group (claude + any child MCP servers)
            import os
            import signal
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                proc.wait(timeout=5)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                proc.wait()
            exit_code = 124  # standard timeout exit code
    except OSError:
        exit_code = 1
    elapsed = time.monotonic() - start

    status = "done" if exit_code == 0 else "failed"
    if exit_code == 124:
        status = "timeout"

    update_run_meta(
        sandbox_path,
        status=status,
        exit_code=exit_code,
        ended_at=datetime.now().isoformat(),
        duration_seconds=round(elapsed, 2),
    )
    return exit_code


# ---------------------------------------------------------------------------
# Run listing (flux run list)
# ---------------------------------------------------------------------------


def list_runs() -> list[dict[str, Any]]:
    """Return list of run metadata dicts, sorted by start time (newest first)."""
    base = sandbox_dir()
    runs: list[dict[str, Any]] = []
    if not base.exists():
        return runs

    for entry in sorted(base.iterdir()):
        if not entry.is_dir():
            continue
        meta_path = entry / "run-meta.json"
        if meta_path.exists():
            try:
                runs.append(json.loads(meta_path.read_text()))
            except (json.JSONDecodeError, OSError):
                continue

    # Sort newest first
    runs.sort(key=lambda r: r.get("started_at", ""), reverse=True)
    return runs


# ---------------------------------------------------------------------------
# Run cleanup (flux run clean)
# ---------------------------------------------------------------------------

_DEFAULT_KEEP = 5


def clean_runs(*, force: bool = False, keep: int = _DEFAULT_KEEP) -> int:
    """Remove completed sandboxes.

    - Default: remove completed/failed runs, keeping the *keep* most recent.
    - ``--force``: remove ALL runs regardless of status.

    Returns the number of directories removed.
    """
    base = sandbox_dir()
    if not base.exists():
        return 0

    dirs = sorted(
        [d for d in base.iterdir() if d.is_dir()],
        key=lambda d: d.name,
    )
    if not dirs:
        return 0

    if force:
        count = 0
        for d in dirs:
            shutil.rmtree(d)
            count += 1
        return count

    # Partition: completed vs running
    completed: list[Path] = []
    for d in dirs:
        meta_path = d / "run-meta.json"
        status = "unknown"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text())
                status = meta.get("status", "unknown")
            except (json.JSONDecodeError, OSError):
                pass
        if status in ("done", "failed", "timeout", "unknown"):
            completed.append(d)

    # Keep the most recent `keep` completed runs
    to_remove = completed[: max(0, len(completed) - keep)]
    for d in to_remove:
        shutil.rmtree(d)
    return len(to_remove)


# ---------------------------------------------------------------------------
# Run manifest (flux run --file)
# ---------------------------------------------------------------------------


def load_run_manifest(file_path: str | Path) -> dict[str, Any]:
    """Load and validate a run manifest JSON file.

    Required fields: ``task``.

    Raises ValueError for invalid manifests.
    """
    path = Path(file_path)
    if not path.exists():
        msg = f"Manifest file not found: {file_path}"
        raise FileNotFoundError(msg)

    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        msg = f"Invalid JSON in manifest: {e}"
        raise ValueError(msg) from e

    if not isinstance(data, dict):
        msg = "Manifest must be a JSON object"
        raise ValueError(msg)

    if "task" not in data:
        msg = "Manifest missing required field: 'task'"
        raise ValueError(msg)

    return data
