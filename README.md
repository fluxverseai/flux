# Flux

**The package manager for AI agent tooling.**

[![CI](https://github.com/fluxverseai/flux/actions/workflows/ci.yml/badge.svg)](https://github.com/fluxverseai/flux/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/flux-cli)](https://pypi.org/project/flux-cli/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Flux is a CLI tool that manages MCP servers and Claude Code skills across your projects. It gives each project exactly the tools it needs, keeps credentials in your OS keystore instead of config files, and lets you run agents in isolated sandboxes.

Think `package.json` for your AI tooling.

## The Problem

You're building AI-powered workflows. You have 30 MCP servers across 8 projects. Each one needs a different subset. Your API keys are scattered across `.env` files. Your research agent accidentally called your trading API because all MCPs were globally visible.

Flux solves this:

```bash
flux init my-project          # Declare what this project needs
flux install wikijs filesystem # Add specific MCPs
flux secret set wikijs KEY    # Credentials stay in your keystore
flux sync                     # Generate scoped .mcp.json
```

Now your project has exactly the tools it needs. Nothing more.

## Installation

```bash
# Install via uv (recommended) or pipx
uv tool install flux-cli
# or: pipx install flux-cli

# Initialize Flux
flux setup
```

Requires Python 3.11+. Works on macOS and Linux.

## Setup

`flux setup` creates the `~/.flux/` directory, detects your platform, configures the secrets backend, and installs the Flux skill for Claude Code.

```bash
$ flux setup

  Created ~/.flux/ directory structure
  Wrote config.toml (secrets backend: keychain)
  Installed Flux skill to ~/.claude/skills/flux/
  Dependencies: Python 3.12 ✓  uv ✓  git ✓  node ✓  claude ✓
```

## Usage

### Register MCPs and Skills

Add tools from npm, PyPI, GitHub, or local paths:

```bash
# npm packages (runs via npx)
flux add mcp filesystem --npx @modelcontextprotocol/server-filesystem
flux add mcp memory --npx @modelcontextprotocol/server-memory

# GitHub repos (cloned and built automatically)
flux add mcp wikijs --github jaalbin24/wikijs-mcp-server \
  --command uv --args "run {source_dir} serve" \
  --keychain WIKIJS_URL WIKIJS_API_KEY

# Skills
flux add skill autoresearch --github user/autoresearch

# Browse what's available
flux search "knowledge base"
flux list
```

### Manage Secrets

Credentials are stored in your OS keystore — never in files:

```bash
flux secret set wikijs WIKIJS_URL https://wiki.example.com
flux secret set wikijs WIKIJS_API_KEY          # Prompts securely
flux secret list                                # Shows keys (values masked)
```

When you run `flux sync`, launcher scripts are generated that fetch secrets at runtime:

```bash
# Auto-generated launcher — keystore lookups, not embedded values
export WIKIJS_API_KEY=$(security find-generic-password -s flux.wikijs -a WIKIJS_API_KEY -w)
exec uv run --directory "$SCRIPT_DIR/../wikijs" wikijs-mcp-server "$@"
```

### Create and Configure Projects

```bash
flux init my-agent                    # Creates flux.json
cd my-agent
flux install wikijs filesystem memory # Adds to project, auto-syncs
```

Your `flux.json` is committed to git. The generated `.mcp.json` is gitignored:

```json
{
  "name": "my-agent",
  "mcps": ["wikijs", "filesystem", "memory"],
  "skills": ["autoresearch"]
}
```

### Run Agents in Sandboxes

Execute tasks with controlled MCP access:

```bash
# Ad-hoc task
flux run "analyze this repo and update the wiki" --mcps wikijs filesystem

# From a saved manifest
flux run --file tasks/weekly-research.json

# Manage runs
flux run list
flux run clean
```

Pre-flight validation checks 6 conditions before execution — missing MCPs, secrets, auth, skills, and build artifacts — and fails fast with the exact command to fix each issue.

### Monitor Health

```bash
flux status              # MCP health for current project
flux status --all        # All tracked projects
flux doctor              # Full environment diagnostic (12 checks)
```

## Claude Code Skill

Flux ships with a built-in Claude Code skill. After `flux setup`, you can talk to Claude about Flux operations in natural language:

> "Add the filesystem MCP to my project and set it up"

> "Show me which MCPs need credentials configured"

The skill is installed to `~/.claude/skills/flux/` and is always available.

## Platform Support

| Platform | Secrets Backend |
|----------|----------------|
| macOS | Keychain via `security` CLI |
| Linux (desktop) | Secret Service via `secretstorage` |
| Linux (headless) | age-encrypted file with identity key |

## Architecture

```
~/.flux/
├── registry.json           # Single source of truth for available tools
├── config.toml             # Platform configuration
├── mcps/                   # Cloned sources + generated launchers
├── skills/                 # Cloned skill sources
├── sandbox/                # Ephemeral agent run directories
├── projects.json           # Tracked project paths
└── secrets.json            # Key names index (values in keystore)
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, testing, and PR guidelines.

```bash
git clone https://github.com/fluxverseai/flux
cd flux
uv pip install -e ".[dev]"
uv run pytest tests/ -v --cov=lib
```

## License

[MIT](LICENSE)
