"""CLI commands: secret set/get/list/delete."""

from __future__ import annotations

import argparse
import sys

from flux_cli.manifest import load_registry
from flux_cli.secrets import get_backend


def cmd_secret(args: argparse.Namespace) -> None:
    """flux secret set/get/list/delete — manage MCP secrets via pluggable backend."""
    import getpass
    subcmd = args.subcmd
    backend = get_backend()

    if subcmd == "set":
        value = args.value or getpass.getpass(f"Value for {args.mcp}/{args.key}: ")
        backend.set(args.mcp, args.key, value)
        print(f"Stored {args.key} for '{args.mcp}'")
        print("   Run 'flux sync' to inject into .mcp.json")

    elif subcmd == "get":
        value = backend.get(args.mcp, args.key)
        if value is not None:
            print(value)
        else:
            print(f"No secret found for {args.mcp}/{args.key}")
            sys.exit(1)

    elif subcmd == "list":
        index = backend.list_keys(args.mcp if hasattr(args, "mcp") else None)
        if args.mcp:
            keys = index.get(args.mcp, [])
            if keys:
                print(f"Secrets for '{args.mcp}':")
                for k in keys:
                    stored = backend.get(args.mcp, k)
                    masked = ("*" * 8) if stored else "(missing)"
                    print(f"  {k} = {masked}")
            else:
                print(f"No secrets stored for '{args.mcp}'")
        else:
            if index:
                print("Stored Flux secrets (use 'flux secret get <mcp> <key>' to retrieve):")
                for mcp, keys in sorted(index.items()):
                    print(f"\n  [{mcp}]")
                    for k in keys:
                        stored = backend.get(mcp, k)
                        masked = ("*" * 8) if stored else "(missing)"
                        print(f"    {k} = {masked}")
            else:
                print("No secrets stored.")
                reg = load_registry()
                needs_secrets = [
                    (name, data['auth']['env_vars'])
                    for name, data in reg.get('mcp_definitions', {}).items()
                    if data.get('auth', {}).get('env_vars')
                ]
                if needs_secrets:
                    print("\nMCPs that require secrets:")
                    for name, env_vars in needs_secrets:
                        print(f"  {name}: {', '.join(env_vars)}")
                    print("\nExample: flux secret set monica MONICA_API_TOKEN")

    elif subcmd == "delete":
        backend.delete(args.mcp, args.key)
        print(f"Deleted {args.key} for '{args.mcp}'")
        print("   Run 'flux sync' to update .mcp.json")
