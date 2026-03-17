"""sandbox.py — sandbox lifecycle + claude subprocess management for flux run"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
from collections.abc import Generator
from datetime import datetime
from pathlib import Path
from typing import Any


def _token_hex(n: int) -> str:
    """Generate n random bytes as a hex string without importing secrets."""
    return os.urandom(n).hex()


FLUX_ROOT = Path(__file__).resolve().parent.parent
SANDBOX_DIR = FLUX_ROOT / "sandbox"


# ---------------------------------------------------------------------------
# Run ID + directory helpers
# ---------------------------------------------------------------------------


def generate_run_id() -> str:
    """Generate a run ID: YYYYMMDD-XXXX (e.g. 20260315-a3f2)."""
    date_part = datetime.now().strftime("%Y%m%d")
    hex_part = _token_hex(2)  # 4 hex chars
    return f"{date_part}-{hex_part}"


# ---------------------------------------------------------------------------
# Sandbox lifecycle
# ---------------------------------------------------------------------------

def create_sandbox(run_id: str, mcps: list[str], manifest: dict[str, Any]) -> Path:
    """
    Create the sandbox directory structure and write .mcp.json for this run.

    Layout:
        sandbox/<run-id>/
            .mcp.json      — generated for this run only
            workspace/     — scratch dir (cwd for claude)
            run-meta.json  — written by write_run_meta()
    """
    from mcp_config import build_mcp_server_config

    sandbox_path = SANDBOX_DIR / run_id
    workspace_path = sandbox_path / "workspace"

    sandbox_path.mkdir(parents=True, exist_ok=True)
    workspace_path.mkdir(exist_ok=True)

    # Build .mcp.json scoped to this run
    mcp_registry = manifest.get('mcp_definitions', {})
    mcp_servers = {}
    missing = []
    for mcp_name in mcps:
        if mcp_name in mcp_registry:
            mcp_servers[mcp_name] = build_mcp_server_config(mcp_name, mcp_registry[mcp_name])
        else:
            missing.append(mcp_name)

    if missing:
        import sys
        print(f"❌ Unknown MCP(s): {', '.join(missing)}")
        print(f"   Available: {', '.join(sorted(mcp_registry.keys()))}")
        shutil.rmtree(sandbox_path)
        sys.exit(1)

    mcp_config_path = sandbox_path / ".mcp.json"
    mcp_config_path.write_text(json.dumps({"mcpServers": mcp_servers}, indent=2))

    return sandbox_path


def write_run_meta(
    sandbox_path: Path, run_id: str, task: str, mcps: list[str],
    status: str = "running", name: str | None = None, **extra: Any,
) -> dict[str, Any]:
    """Write initial run-meta.json."""
    meta = {
        "id": run_id,
        "name": name or run_id,
        "task": task,
        "mcps": mcps,
        "status": status,
        "started_at": datetime.now().isoformat(),
    }
    meta.update(extra)
    (sandbox_path / "run-meta.json").write_text(json.dumps(meta, indent=2))
    return meta


def update_run_meta(sandbox_path: Path, **kwargs: Any) -> None:
    """Merge kwargs into the existing run-meta.json (creates if missing)."""
    meta_path = sandbox_path / "run-meta.json"
    meta: dict[str, Any] = {}
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
    meta.update(kwargs)
    meta_path.write_text(json.dumps(meta, indent=2))


def cleanup_sandbox(sandbox_path: str | Path) -> None:
    """Remove the sandbox directory."""
    if Path(sandbox_path).exists():
        shutil.rmtree(sandbox_path)


# ---------------------------------------------------------------------------
# Claude subprocess
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


def stream_claude(sandbox_path: str | Path, task: str) -> Generator[dict[str, Any], None, None]:
    """
    Invoke claude in sandbox/workspace/, streaming JSONL events.
    Yields parsed event dicts. The last item yielded is a special
    {"type": "_exit", "code": <int>} sentinel with the process exit code.
    """
    sandbox_path = Path(sandbox_path)
    mcp_config_path = sandbox_path / ".mcp.json"
    workspace_path = sandbox_path / "workspace"

    claude_bin = _find_claude()
    if not claude_bin:
        import sys
        print("❌ claude CLI not found. Install from: https://claude.ai/claude-code")
        sys.exit(1)

    cmd = [
        claude_bin,
        "--print", task,
        "--mcp-config", str(mcp_config_path),
        "--output-format", "stream-json",
        "--dangerously-skip-permissions",
    ]

    proc = subprocess.Popen(  # noqa: S603
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(workspace_path),
        text=True,
        bufsize=1,
    )

    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            yield {"type": "raw_text", "text": line}

    proc.wait()
    yield {"type": "_exit", "code": proc.returncode}


# ---------------------------------------------------------------------------
# Agent runner (with Rich display)
# ---------------------------------------------------------------------------

def run_agent(
    sandbox_path: str | Path, task: str, keep: bool = False, stream: bool = True,
    run_id: str | None = None, mcps: list[str] | None = None,
) -> int:
    """
    Run claude in the sandbox, stream output via Rich, update run-meta on
    completion. Returns the process exit code.
    """
    from rich.console import Console

    console = Console()
    sandbox_path = Path(sandbox_path)
    mcps = mcps or []
    run_id = run_id or sandbox_path.name

    console.print(f"\n[bold cyan]▶ flux run[/bold cyan]  [dim]{run_id}[/dim]")
    if mcps:
        console.print(f"  [dim]MCPs:[/dim] {', '.join(mcps)}")
    console.print(f"  [dim]Task:[/dim] {task}\n")

    exit_code = 0
    had_output = False

    try:
        for event in stream_claude(sandbox_path, task):
            etype = event.get("type", "")

            if etype == "_exit":
                exit_code = event.get("code", 0)

            elif etype == "assistant":
                content = event.get("message", {}).get("content", [])
                for block in content:
                    if block.get("type") == "text":
                        text = block.get("text", "")
                        if text and stream:
                            console.print(text, end="", highlight=False)
                            had_output = True

            elif etype == "result":
                result_text = event.get("result", "")
                is_error = event.get("is_error", False)
                if is_error:
                    exit_code = 1
                # Print result only if we haven't already streamed assistant text
                if result_text and not had_output and stream:
                    console.print(result_text, highlight=False)
                    had_output = True

            elif etype == "tool_use" and stream:
                tool_name = event.get("name", "unknown")
                console.print(f"\n  [dim cyan]⚙ {tool_name}[/dim cyan]", end="")

            elif etype == "raw_text" and stream:
                console.print(event.get("text", ""), highlight=False)
                had_output = True

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")
        exit_code = 130
    except Exception as e:
        console.print(f"\n[red]Error:[/red] {e}")
        exit_code = 1

    if had_output:
        console.print()  # trailing newline

    status = "done" if exit_code == 0 else "failed"
    console.print(f"\n[{'green' if exit_code == 0 else 'red'}]{status}[/] "
                  f"[dim](exit {exit_code})[/dim]")

    update_run_meta(
        sandbox_path,
        status=status,
        ended_at=datetime.now().isoformat(),
        exit_code=exit_code,
    )

    if not keep:
        cleanup_sandbox(sandbox_path)

    return exit_code


# ---------------------------------------------------------------------------
# Wave 2: run history + manifest helpers
# ---------------------------------------------------------------------------

def list_runs() -> list[dict[str, Any]]:
    """Return list of run metadata dicts from sandbox/*/run-meta.json."""
    runs: list[dict[str, Any]] = []
    if not SANDBOX_DIR.exists():
        return runs
    for entry in sorted(SANDBOX_DIR.iterdir()):
        if not entry.is_dir():
            continue
        meta_path = entry / "run-meta.json"
        if meta_path.exists():
            with contextlib.suppress(json.JSONDecodeError, OSError):
                runs.append(json.loads(meta_path.read_text()))
    return runs


def clean_runs(force: bool = False) -> int:
    """
    Remove all sandbox dirs from sandbox/ (except .claude/).
    Returns count of dirs removed, or -1 if aborted.
    """
    if not SANDBOX_DIR.exists():
        return 0

    dirs = [d for d in sorted(SANDBOX_DIR.iterdir())
            if d.is_dir() and d.name != ".claude"]
    if not dirs:
        return 0

    if not force:
        print(f"About to remove {len(dirs)} sandbox(es) from {SANDBOX_DIR}")
        answer = input("Confirm? [y/N] ").strip().lower()
        if answer != "y":
            return -1

    for d in dirs:
        shutil.rmtree(d)
    return len(dirs)


def load_run_manifest(file_path: str | Path) -> dict[str, Any]:
    """Load a run.json manifest file, exiting if not found."""
    path = Path(file_path)
    if not path.exists():
        import sys
        print(f"\u274c File not found: {file_path}")
        sys.exit(1)
    return json.loads(path.read_text())


RUN_JSON_TEMPLATE = {
    "name": "{name}",
    "task": "Describe your task here",
    "mcps": [],
    "skills": [],
    "workspace": "scratch",
    "output": "output.md",
    "timeout": 300,
}
