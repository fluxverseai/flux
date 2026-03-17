"""Entry point for the flux CLI."""

from __future__ import annotations

import argparse


def main() -> None:
    """Parse CLI arguments and dispatch to the appropriate command handler."""
    from flux_cli.cli.commands.doctor import cmd_doctor, cmd_setup
    from flux_cli.cli.commands.project import cmd_init, cmd_install, cmd_status, cmd_sync, cmd_uninstall
    from flux_cli.cli.commands.registry import cmd_add, cmd_list, cmd_remove, cmd_search, cmd_upgrade
    from flux_cli.cli.commands.sandbox import cmd_run
    from flux_cli.cli.commands.secrets import cmd_secret
    from flux_cli.cli.commands.version import cmd_version

    parser = argparse.ArgumentParser(description="Flux OS \u2014 Agentic AI control plane")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # flux search <query>
    p = subparsers.add_parser("search", help="Search the official MCP Registry")
    p.add_argument("query", help="Search query (e.g. 'github', 'slack', 'filesystem')")
    p.add_argument("--limit", type=int, default=20, metavar="N", help="Max results (default: 20)")
    p.add_argument("--add", action="store_true", help="Interactively add a result")
    p.set_defaults(func=cmd_search)

    # flux list
    p = subparsers.add_parser("list", help="List available MCPs and skills")
    p.add_argument("--json", dest="json_output", action="store_true", help="Output as JSON")
    p.add_argument("--type", choices=["mcp", "skill"], help="Filter by type")
    p.set_defaults(func=cmd_list)

    # flux init [name]
    p = subparsers.add_parser("init", help="Scaffold a new project")
    p.add_argument("name", nargs="?", default=None, help="Project name")
    p.set_defaults(func=cmd_init)

    # flux install <name> [name ...]
    p = subparsers.add_parser("install", help="Add MCPs/skills to current project and sync")
    p.add_argument("names", nargs="+", help="Names of MCPs or skills to install")
    p.set_defaults(func=cmd_install)

    # flux uninstall <name> [name ...]
    p = subparsers.add_parser("uninstall", help="Remove MCPs/skills from current project and sync")
    p.add_argument("names", nargs="+", help="Names of MCPs or skills to uninstall")
    p.set_defaults(func=cmd_uninstall)

    # flux sync
    p = subparsers.add_parser("sync", help="Sync projects: read flux.json, generate .mcp.json")
    p.add_argument("--all", action="store_true", help="Sync all tracked projects")
    p.set_defaults(func=cmd_sync)

    # flux add mcp/skill
    p = subparsers.add_parser("add", help="Register a new MCP or skill")
    p.add_argument("entry_type", choices=["mcp", "skill"], help="Type to register")
    p.add_argument("name", help="Name for the registry entry")
    p.add_argument("--uvx",       help="PyPI package to run via uvx")
    p.add_argument("--npx",       help="npm package")
    p.add_argument("--github",    help="GitHub repo (e.g. user/repo)")
    p.add_argument("--local",     help="Local directory path")
    p.add_argument("--command",   help="Command to run the MCP")
    p.add_argument("--args",      help="Args for the command, space-separated")
    p.add_argument("--tags",      help="Comma-separated tags")
    p.add_argument("--keychain",  help="Comma-separated env var names for keychain auth")
    p.add_argument("--build-cmd", dest="build_cmd", help="Build command after clone")
    p.add_argument("--setup-cmd", dest="setup_cmd", help="Setup command after registration")
    p.set_defaults(func=cmd_add)

    # flux upgrade
    p = subparsers.add_parser("upgrade", help="Update cloned repos")
    p.add_argument("names", nargs="*", help="Specific names to upgrade (default: all)")
    p.add_argument("--dry-run", action="store_true", help="Show what would be updated")
    p.set_defaults(func=cmd_upgrade)

    # flux remove <name>
    p = subparsers.add_parser("remove", help="Unregister an MCP or skill")
    p.add_argument("name", help="Name to remove")
    p.set_defaults(func=cmd_remove)

    # flux status
    p = subparsers.add_parser("status", help="Show MCP server health")
    p.add_argument("--all", action="store_true", help="All tracked projects")
    p.set_defaults(func=cmd_status)

    # flux doctor
    subparsers.add_parser("doctor", help="Check Flux environment health").set_defaults(func=cmd_doctor)

    # flux secret
    p = subparsers.add_parser("secret", help="Manage MCP secrets")
    secret_sub = p.add_subparsers(dest="subcmd", required=True)
    p.set_defaults(func=cmd_secret)

    ps = secret_sub.add_parser("set", help="Store a secret")
    ps.add_argument("mcp", help="MCP name")
    ps.add_argument("key", help="Env var name")
    ps.add_argument("value", nargs="?", help="Secret value (omit to be prompted)")

    ps = secret_sub.add_parser("get", help="Retrieve a secret")
    ps.add_argument("mcp", help="MCP name")
    ps.add_argument("key", help="Env var name")

    ps = secret_sub.add_parser("list", help="List stored secrets")
    ps.add_argument("mcp", nargs="?", help="Filter by MCP name")

    ps = secret_sub.add_parser("delete", help="Remove a secret")
    ps.add_argument("mcp", help="MCP name")
    ps.add_argument("key", help="Env var name")

    # flux setup [mcp]
    p = subparsers.add_parser("setup", help="Initialise ~/.flux/")
    p.add_argument("name", nargs="?", default=None, help="MCP name (omit for full setup)")
    p.set_defaults(func=cmd_setup)

    # flux run
    p = subparsers.add_parser("run", help="Run an agent in an isolated sandbox")
    p.add_argument("task_or_sub", nargs="?", metavar="task|init|list|clean",
                   help="Task string or subcommand")
    p.add_argument("init_name", nargs="?", metavar="name",
                   help="Name for 'flux run init <name>'")
    p.add_argument("--mcps", nargs="*", default=[], metavar="mcp",
                   help="MCPs to enable")
    p.add_argument("--keep", action="store_true",
                   help="Keep sandbox after run")
    p.add_argument("--no-stream", dest="no_stream", action="store_true",
                   help="Collect output instead of streaming")
    p.add_argument("--file", "-f", metavar="run.json",
                   help="Load from manifest file")
    p.add_argument("--force", action="store_true",
                   help="Skip confirmation for clean")
    p.set_defaults(func=cmd_run)

    # flux version
    p = subparsers.add_parser("version", help="Show flux-cli version")
    p.add_argument("--check", action="store_true", help="Check for updates")
    p.set_defaults(func=cmd_version)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
