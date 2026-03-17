"""secrets.py — macOS Keychain integration for MCP server credentials."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

FLUX_HOME = Path.home() / ".flux"
SECRETS_INDEX = FLUX_HOME / "secrets.json"


def _keychain_service(mcp_name: str) -> str:
    """Return the Keychain service name for a given MCP."""
    return f"flux.{mcp_name}"


def _load_secrets_index() -> dict[str, Any]:
    """Load the secrets index from disk, returning empty dict if absent."""
    if SECRETS_INDEX.exists():
        with open(SECRETS_INDEX) as f:
            return json.load(f)
    return {}


def _save_secrets_index(index: dict[str, Any]) -> None:
    """Atomically write the secrets index to disk."""
    FLUX_HOME.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=FLUX_HOME, suffix=".tmp")
    try:
        with open(fd, "w") as f:
            json.dump(index, f, indent=2)
        Path(tmp).replace(SECRETS_INDEX)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def keychain_set(mcp_name: str, key: str, value: str) -> None:
    """Store a secret in macOS Keychain and update the secrets index."""
    import sys
    service = _keychain_service(mcp_name)
    result = subprocess.run(  # noqa: S603, S607
        ["security", "add-generic-password", "-s", service, "-a", key, "-w", value, "-U"],  # noqa: S607
        capture_output=True
    )
    if result.returncode != 0:
        print(f"\u274c Keychain write failed: {result.stderr.decode().strip()}")
        sys.exit(1)
    index = _load_secrets_index()
    index.setdefault(mcp_name, [])
    if key not in index[mcp_name]:
        index[mcp_name].append(key)
    _save_secrets_index(index)


def keychain_get(mcp_name: str, key: str) -> str | None:
    """Retrieve a secret from macOS Keychain, or None if not found."""
    result = subprocess.run(  # noqa: S603
        ["security", "find-generic-password", "-s", _keychain_service(mcp_name), "-a", key, "-w"],  # noqa: S607
        capture_output=True, text=True
    )
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def keychain_delete(mcp_name: str, key: str) -> None:
    """Remove a secret from macOS Keychain and update the secrets index."""
    subprocess.run(  # noqa: S603
        ["security", "delete-generic-password", "-s", _keychain_service(mcp_name), "-a", key],  # noqa: S607
        capture_output=True
    )
    index = _load_secrets_index()
    if mcp_name in index:
        index[mcp_name] = [k for k in index[mcp_name] if k != key]
        if not index[mcp_name]:
            del index[mcp_name]
    _save_secrets_index(index)


def get_keychain_env(mcp_name: str, env_vars: list[str]) -> dict[str, str]:
    """Return {var: value} for all keychain-stored secrets for an MCP."""
    env = {}
    for var in env_vars:
        value = keychain_get(mcp_name, var)
        if value:
            env[var] = value
    return env
