# Flux — AI Agent Control Plane

Flux is a CLI tool for managing MCP servers, skills, and agent sandboxes.

## Available Commands

- `flux search <query>` — Search the marketplace for MCPs and skills
- `flux add <name>` — Install an MCP or skill from the marketplace
- `flux remove <name>` — Uninstall an MCP or skill
- `flux sync` — Synchronise installed MCPs into `.mcp.json` for Claude Code
- `flux doctor` — Run health checks on all installed MCPs
- `flux run <task>` — Execute a task in an isolated sandbox with selected MCPs
- `flux secret set <mcp> <key> <value>` — Store an API key securely
- `flux secret get <mcp> <key>` — Retrieve a stored secret
- `flux setup` — Initialise or migrate the Flux home directory
- `flux version` — Show version and check for updates
- `flux upgrade` — Update installed MCPs and skills to latest versions

## Usage Notes

- Run `flux setup` first to initialise the `~/.flux/` directory.
- Use `flux search` to discover MCPs, then `flux add` to install them.
- After adding MCPs, run `flux sync` to update your Claude Code configuration.
- Use `flux doctor` to diagnose connectivity or authentication issues.
- Secrets are stored in the system keychain (macOS) or secret-service (Linux).
