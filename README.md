# Flux

**The control plane for AI agents.**

[![CI](https://github.com/fluxverseai/flux/actions/workflows/ci.yml/badge.svg)](https://github.com/fluxverseai/flux/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/flux-cli)](https://pypi.org/project/flux-cli/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

AI agents are only as powerful as the tools they can reach. Flux gives you one place to manage every MCP server and skill your agents depend on — across every project, with credentials that never touch a file.

Stop copy-pasting `.mcp.json` between repos. Stop leaking API keys into config files. Stop guessing which MCP servers are healthy. Flux handles all of it.

## Why Flux

- **One registry, every project.** Add an MCP once, install it into any project with a single command. No more per-repo configuration drift.
- **Secrets that stay secret.** Credentials live in your OS keystore (macOS Keychain, Linux Secret Service, or age-encrypted vault). Generated launcher scripts fetch them at runtime — nothing is ever written to disk.
- **Health visibility.** Probe every MCP server with a real JSON-RPC handshake. Know instantly what's connected, what needs auth, and what's down.
- **Isolated execution.** Run agents in scoped sandboxes where only the MCPs you declare are available. No ambient access, no surprise tool calls.
- **Environment confidence.** `flux doctor` validates your entire setup — Python, Node, git, Claude CLI, registry integrity, secret consistency — and auto-fixes what it can.
- **Works with Claude Code.** Generates the `.mcp.json` that Claude Code expects. Flux is the missing layer between your tool ecosystem and your agent runtime.

## Install

```bash
uv tool install flux-cli
flux setup
```

## Get Started in 30 Seconds

```bash
# Discover and add an MCP from the official registry
flux search filesystem
flux add mcp filesystem --npx @modelcontextprotocol/server-filesystem

# Create a project and wire it up
flux init my-agent && cd my-agent
flux install filesystem
flux status
```

That's it. Your project now has a `.mcp.json` ready for Claude Code, backed by a registry you control.

## Features

### Registry Management
Maintain a single source of truth for all your MCP servers and skills. Add from npm, PyPI, GitHub, or local directories. Search the official MCP Registry to discover new tools.

```bash
flux add mcp memory --npx @modelcontextprotocol/server-memory
flux add mcp my-tool --github user/repo
flux search slack
flux list
```

### Project Scoping
Each project declares exactly which MCPs and skills it needs in a simple `flux.json`. Flux generates the right `.mcp.json` automatically.

```bash
flux init my-project
flux install memory filesystem
flux sync
```

### Secrets Management
Store API keys and tokens in your OS keystore with a pluggable backend system. Supports macOS Keychain, Linux Secret Service (D-Bus), and age-encrypted files for headless environments.

```bash
flux secret set wikijs-mcp WIKIJS_API_KEY
flux sync   # Generates launcher with keystore lookups — no secrets in files
```

### Health Monitoring
Probe MCP servers via real JSON-RPC handshake. Check auth status, tool counts, and server info across all your projects at once.

```bash
flux status          # Current project
flux status --all    # All tracked projects
flux doctor          # Full environment health check with auto-fix
```

### Sandboxed Execution
Run agents in isolated sandboxes with only the MCPs you explicitly declare. Pre-flight validation ensures everything is configured before execution starts.

```bash
flux run "Analyze the codebase" --mcps memory filesystem
flux run --file manifest.json
flux run list
```

## Commands

| Command | Description |
|---------|-------------|
| `flux setup` | Initialize `~/.flux/` and environment |
| `flux doctor` | Diagnose and auto-fix environment issues |
| `flux add` | Register an MCP or skill (npm, PyPI, GitHub, local) |
| `flux remove` | Unregister an MCP or skill |
| `flux list` | List everything in the registry |
| `flux search` | Search the official MCP Registry |
| `flux upgrade` | Update cloned sources to latest |
| `flux init` | Create a new project with `flux.json` |
| `flux install` | Add MCPs/skills to a project and sync |
| `flux uninstall` | Remove MCPs/skills from a project and sync |
| `flux sync` | Generate `.mcp.json` from `flux.json` |
| `flux status` | Show MCP server health |
| `flux secret` | Manage credentials (set, get, list, delete) |
| `flux run` | Execute agents in isolated sandboxes |
| `flux version` | Show version and check for updates |

## Security

- Secrets never appear in any file on disk — only in your OS keystore
- Launcher scripts contain keystore lookup commands, not values
- Each sandbox gets only the MCPs explicitly declared for that run
- Generated `.mcp.json` never contains credentials
- Path traversal protections on all file operations

## Development

```bash
git clone https://github.com/fluxverseai/flux
cd flux
uv sync --extra dev
uv run pytest tests/ -v
uv run ruff check src/flux_cli/ tests/
```

## License

[MIT](LICENSE)
