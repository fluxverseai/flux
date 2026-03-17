"""CLI commands: run (init/list/clean/task)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from flux_cli.manifest import load_registry
from flux_cli.sandbox import (
    clean_runs,
    create_sandbox,
    generate_run_id,
    list_runs,
    load_run_manifest,
    run_agent,
    write_run_meta,
)


def cmd_run(args: argparse.Namespace) -> None:
    """Dispatch flux run subcommands or execute a task."""
    sub = getattr(args, 'task_or_sub', None)

    if sub == 'init':
        _cmd_run_init(args.init_name)
    elif sub == 'list':
        _cmd_run_list()
    elif sub == 'clean':
        _cmd_run_clean(force=getattr(args, 'force', False))
    elif sub is not None or getattr(args, 'file', None):
        _cmd_run_task(args)
    else:
        print("flux run: specify a task string, --file run.json, or a subcommand (init/list/clean)")
        sys.exit(1)


def _cmd_run_task(args: argparse.Namespace) -> None:
    """Execute a task — from inline string or run.json manifest."""
    reg = load_registry()

    run_file = getattr(args, 'file', None)
    task_or_sub = getattr(args, 'task_or_sub', None)

    if run_file:
        run_manifest = load_run_manifest(run_file)
        task = run_manifest.get('task', '')
        mcps = run_manifest.get('mcps', [])
        name = run_manifest.get('name')
        timeout = run_manifest.get('timeout', 300)
    else:
        task = task_or_sub
        mcps = getattr(args, 'mcps', []) or []
        name = None
        timeout = None

    if not task:
        print("\u274c No task specified. Provide a task string or a run.json with a 'task' field.")
        sys.exit(1)

    run_id = generate_run_id()
    sandbox_path = create_sandbox(
        run_id, mcps, registry=reg, skip_preflight=False,
    )
    write_run_meta(sandbox_path, run_id, task, mcps, name=name)

    exit_code = run_agent(
        sandbox_path,
        task,
        timeout=timeout,
        run_id=run_id,
    )
    sys.exit(exit_code)


def _cmd_run_init(name: str | None = None) -> None:
    """Scaffold a run.json template in the current directory."""
    name = name or "my-run"
    output_path = Path.cwd() / "run.json"

    if output_path.exists():
        print(f"\u274c run.json already exists at {output_path}")
        sys.exit(1)

    reg = load_registry()
    available_mcps = sorted(reg.get('mcp_definitions', {}).keys())

    template = {
        "name": name,
        "task": "Describe your task here",
        "mcps": [],
        "skills": [],
        "workspace": "scratch",
        "output": "output.md",
        "timeout": 300,
    }
    output_path.write_text(json.dumps(template, indent=2) + "\n")

    print(f"\u2705 Created run.json for '{name}'")
    print("   Edit the 'task' field, then run: flux run --file run.json")
    if available_mcps:
        print(f"   Available MCPs: {', '.join(available_mcps)}")


def _cmd_run_list() -> None:
    """Show all past/active runs from sandbox/."""
    from rich.console import Console
    from rich.table import Table

    runs = list_runs()
    console = Console()

    if not runs:
        console.print("[dim]No runs found in sandbox/[/dim]")
        return

    table = Table(title="flux run history", show_lines=False)
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Name", style="bold")
    table.add_column("Status", no_wrap=True)
    table.add_column("MCPs", style="dim")
    table.add_column("Task", max_width=50, overflow="ellipsis")

    status_colors = {
        "done":    "[green]done[/green]",
        "failed":  "[red]failed[/red]",
        "running": "[yellow]running[/yellow]",
    }

    for run in runs:
        status = run.get("status", "?")
        status_str = status_colors.get(status, status)
        mcps_str = ", ".join(run.get("mcps", [])) or "\u2014"
        task = run.get("task", "")
        name = run.get("name", run.get("id", ""))
        table.add_row(run.get("id", ""), name, status_str, mcps_str, task)

    console.print(table)


def _cmd_run_clean(force: bool = False) -> None:
    """Remove completed sandboxes."""
    count = clean_runs(force=force)
    if count == 0:
        print("sandbox/ is already empty.")
    else:
        print(f"\u2705 Removed {count} sandbox(es)")
