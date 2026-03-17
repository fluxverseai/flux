"""CLI commands: init, install, uninstall, sync, status."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from flux_cli.health import probe_mcp_server_detailed
from flux_cli.manifest import load_flux_json, load_registry, save_flux_json
from flux_cli.mcp_config import enrich_with_marketplace
from flux_cli.paths import skills_dir as v1_skills_dir_fn
from flux_cli.projects import list_projects, register_project
from flux_cli.sync import sync_project


def cmd_init(args: argparse.Namespace) -> None:
    """flux init [name] — scaffold a new project."""
    name = getattr(args, "name", None)

    if name:
        project_dir = Path.cwd() / name
    else:
        project_dir = Path.cwd()
        name = project_dir.name

    if (project_dir / "flux.json").exists():
        print(f"\u274c flux.json already exists at {project_dir / 'flux.json'}")
        sys.exit(1)

    project_dir.mkdir(parents=True, exist_ok=True)

    flux_json = {
        "name": name,
        "mcps": [],
        "skills": [],
    }
    save_flux_json(project_dir, flux_json)

    gitignore_path = project_dir / ".gitignore"
    if gitignore_path.exists():
        content = gitignore_path.read_text()
        if ".mcp.json" not in content:
            with open(gitignore_path, "a") as f:
                f.write("\n.mcp.json\n")
    else:
        gitignore_path.write_text(".mcp.json\n")

    register_project(project_dir, name)

    print(f"\u2705 Created project '{name}' at {project_dir}")
    print(f"   Edit {project_dir}/flux.json to declare MCPs and skills")
    print("   Then run: flux sync")


def cmd_sync(args: argparse.Namespace) -> None:
    """flux sync [--all] — generate .mcp.json for the current project or all tracked projects."""
    reg = load_registry()

    combined_registry = {
        "version": reg.get("version", "1.0.0"),
        "mcp_definitions": dict(reg.get('mcp_definitions', {})),
        "skill_definitions": dict(reg.get('skill_definitions', {})),
    }

    sync_all = getattr(args, 'all', False)

    if sync_all:
        projects = list_projects()
        if not projects:
            print("No tracked projects. Run 'flux init' in a project directory.")
            return

        print(f"\nSyncing {len(projects)} tracked project(s)...\n")
        synced, errors_count = 0, 0
        for proj in projects:
            project_dir = Path(proj["path"])
            if not project_dir.exists():
                print(f"  Warning: {proj['name']} \u2014 path no longer exists ({proj['path']})")
                errors_count += 1
                continue
            success, issues = sync_project(project_dir, combined_registry)
            if not success:
                print(f"  Skipped: {proj['name']} \u2014 {'; '.join(issues)}")
                continue
            if issues:
                errors_count += 1
                print(f"  Warning: {proj['name']}")
                for issue in issues:
                    print(f"    {issue}")
            else:
                synced += 1
                print(f"  Synced: {proj['name']}")
        print(f"\n  {synced} synced, {errors_count} with issues\n")
    else:
        target_dir = Path.cwd()
        flux_json_path = target_dir / "flux.json"

        if flux_json_path.exists():
            success, issues = sync_project(target_dir, combined_registry)
            if issues:
                for issue in issues:
                    print(f"Error: {issue}")
                sys.exit(1)
            flux_json = load_flux_json(target_dir)
            mcps_count = len(flux_json.get('mcps', [])) if flux_json else 0
            skills_count = len(flux_json.get('skills', [])) if flux_json else 0
            print(f"Synced {target_dir.name} \u2014 {mcps_count} MCP(s), {skills_count} skill(s)")
        else:
            print("No flux.json in current directory.")
            print("Run 'flux init' to create a project, or 'flux sync --all' to sync all tracked projects.")
            sys.exit(1)


def cmd_install(args: argparse.Namespace) -> None:
    """flux install <name> [name ...] — add MCPs/skills to the current project and sync."""
    reg = load_registry()
    names = args.names
    target_dir = Path.cwd()

    mcp_defs = dict(reg.get('mcp_definitions', {}))
    skill_defs = dict(reg.get('skill_definitions', {}))

    flux_json = load_flux_json(target_dir)
    if flux_json is None:
        flux_json = {"name": target_dir.name, "mcps": [], "skills": []}

    any_changed = False
    has_errors = False

    for name in names:
        if name not in mcp_defs and name not in skill_defs:
            all_names = sorted(list(mcp_defs.keys()) + list(skill_defs.keys()))
            print(f"Error: '{name}' not found in registry.")
            if all_names:
                print(f"   Available: {', '.join(all_names)}")
            has_errors = True
            continue

        if name in mcp_defs:
            if name in flux_json.setdefault('mcps', []):
                print(f"Skipped: MCP '{name}' already installed")
                continue
            flux_json['mcps'].append(name)
            print(f"Added MCP '{name}' to flux.json")
            any_changed = True
        else:
            if name in flux_json.setdefault('skills', []):
                print(f"Skipped: skill '{name}' already installed")
                continue
            flux_json['skills'].append(name)

            skill_data = skill_defs[name]
            source_dir = skill_data.get('source_dir', '')
            source_path = Path(source_dir) if source_dir and Path(source_dir).is_absolute() else (
                v1_skills_dir_fn() / name
            )
            dest_path = target_dir / ".claude" / "skills" / name
            if source_path.exists():
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                if dest_path.exists():
                    shutil.rmtree(dest_path)
                shutil.copytree(source_path, dest_path)
            print(f"Added skill '{name}' to flux.json")
            any_changed = True

    if has_errors and not any_changed:
        sys.exit(1)

    if any_changed:
        save_flux_json(target_dir, flux_json)
        register_project(target_dir, flux_json.get("name", target_dir.name))

    combined_registry = {
        "version": reg.get("version", "1.0.0"),
        "mcp_definitions": mcp_defs,
        "skill_definitions": skill_defs,
    }
    print(f"Syncing {target_dir.name}...")
    success, issues = sync_project(target_dir, combined_registry)
    if issues:
        for issue in issues:
            print(f"  Warning: {issue}")
    else:
        print(f"Synced {target_dir.name}")


def cmd_uninstall(args: argparse.Namespace) -> None:
    """flux uninstall <name> [name ...] — remove MCPs/skills from current project and sync."""
    reg = load_registry()
    names = args.names
    target_dir = Path.cwd()

    flux_json = load_flux_json(target_dir)
    if flux_json is None:
        print(f"Error: No flux.json found in {target_dir}")
        sys.exit(1)

    mcp_defs = dict(reg.get('mcp_definitions', {}))
    skill_defs = dict(reg.get('skill_definitions', {}))

    any_changed = False
    has_errors = False

    for name in names:
        in_mcps = name in flux_json.get('mcps', [])
        in_skills = name in flux_json.get('skills', [])

        if not in_mcps and not in_skills:
            print(f"Error: '{name}' is not installed in this project")
            has_errors = True
            continue

        if in_mcps:
            flux_json['mcps'].remove(name)
            print(f"Removed MCP '{name}' from flux.json")
            any_changed = True

        if in_skills:
            flux_json['skills'].remove(name)
            safe_name = Path(name).name
            skills_parent = target_dir / ".claude" / "skills"
            skill_dir = skills_parent / safe_name
            if skill_dir.exists() and skill_dir.resolve().is_relative_to(skills_parent.resolve()):
                shutil.rmtree(skill_dir)
            print(f"Removed skill '{name}' from flux.json")
            any_changed = True

    if has_errors and not any_changed:
        sys.exit(1)

    if any_changed:
        save_flux_json(target_dir, flux_json)

    combined_registry = {
        "version": reg.get("version", "1.0.0"),
        "mcp_definitions": mcp_defs,
        "skill_definitions": skill_defs,
    }
    print(f"Syncing {target_dir.name}...")
    success, issues = sync_project(target_dir, combined_registry)
    if issues:
        for issue in issues:
            print(f"  Warning: {issue}")
    else:
        print(f"Synced {target_dir.name}")


STATUS_STYLE = {
    "connected": "[bold green]connected[/]",
    "running": "[yellow]running[/]",
    "auth_required": "[bold red]auth_required[/]",
    "timeout": "[red]timeout[/]",
    "error": "[red]error[/]",
    "failed": "[bold red]failed[/]",
}


def _status_table(title: str, rows: list[dict]) -> None:
    from rich.console import Console
    from rich.table import Table

    console = Console()
    table = Table(title=title, show_lines=False)
    table.add_column("MCP Name", style="cyan", no_wrap=True)
    table.add_column("Status")
    table.add_column("Tools", justify="right")
    table.add_column("Detail")

    for r in rows:
        styled = STATUS_STYLE.get(r["status"], r["status"])
        tools_str = str(r["tools_count"]) if r["tools_count"] is not None else "-"
        table.add_row(r["name"], styled, tools_str, r.get("detail", ""))
    console.print(table)


def cmd_status(args: argparse.Namespace) -> None:
    """flux status — show MCP server health for current project or all projects."""

    print("\nChecking MCP server health...\n")
    reg = load_registry()
    mcp_registry = reg.get('mcp_definitions', {})

    if args.all:
        tracked = list_projects()
        if not tracked:
            print("No tracked projects. Run 'flux init' in a project directory.")
            return

        found_any = False
        for entry in tracked:
            project = Path(entry["path"])
            if not project.exists():
                print(f"\U0001f4c1 {entry['name']} \u2014 path no longer exists ({entry['path']})")
                print()
                continue
            flux_json = load_flux_json(project)
            label = flux_json.get('name', project.name) if flux_json else entry['name']
            declared = flux_json.get('mcps', []) if flux_json else []
            has_mcp_file = (project / ".mcp.json").exists()

            if flux_json or has_mcp_file:
                if declared and not has_mcp_file:
                    print(f"  {label}: Declares MCPs but no .mcp.json \u2014 run: flux sync\n")
                else:
                    rows = _probe_project_servers(project, mcp_registry)
                    if rows:
                        _status_table(label, rows)
                    else:
                        print(f"  {label}: no MCP servers configured\n")
                found_any = True

        if not found_any:
            print("No projects found. Run: flux init <name>")
    else:
        target_dir = Path.cwd()
        mcp_file = target_dir / ".mcp.json"
        flux_json = load_flux_json(target_dir)

        if flux_json and not mcp_file.exists():
            print("flux.json found but no .mcp.json \u2014 run: flux sync")
            return

        if not mcp_file.exists():
            print(f"No .mcp.json in {target_dir.name}/ \u2014 run: flux install <name>")
            return

        with open(mcp_file) as f:
            mcp_config = json.load(f)
        servers = mcp_config.get('mcpServers', {})
        rows = []
        for name, config in enrich_with_marketplace(servers, mcp_registry).items():
            result = probe_mcp_server_detailed(config)
            rows.append({"name": name, "status": result["status"],
                          "tools_count": result["tools_count"],
                          "detail": result["detail"]})
        if rows:
            _status_table(target_dir.name, rows)
    print()


def _probe_project_servers(project_dir: Path, mcp_registry: dict) -> list[dict]:

    mcp_file = project_dir / ".mcp.json"
    if not mcp_file.exists():
        return []
    with open(mcp_file) as f:
        mcp_config = json.load(f)
    servers = mcp_config.get('mcpServers', {})
    if not servers:
        return []
    rows = []
    for name, config in enrich_with_marketplace(servers, mcp_registry).items():
        result = probe_mcp_server_detailed(config)
        rows.append({"name": name, "status": result["status"],
                      "tools_count": result["tools_count"],
                      "detail": result["detail"]})
    return rows
