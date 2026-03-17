"""
registry.py — Query the official MCP Registry at registry.modelcontextprotocol.io

Registry API notes:
- Each item in the "servers" list wraps the actual data under a "server" key
- The "q" param filters by name prefix, not full-text keyword
- Packages (npm/pypi) are not always present; many servers use hosted "remotes" instead
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

REGISTRY_BASE = "https://registry.modelcontextprotocol.io/v0"


def search_servers(query: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    """Search the official MCP Registry. Returns list of unwrapped server dicts."""
    params = {"limit": str(limit)}
    if query:
        params["q"] = query
    url = f"{REGISTRY_BASE}/servers?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "flux-cli/1.0"})  # noqa: S310
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            data = json.loads(resp.read().decode())
            # Each item is {"server": {...}, "_meta": {...}} — unwrap the inner "server"
            return [item["server"] for item in data.get("servers", []) if "server" in item]
    except urllib.error.URLError as e:
        raise RuntimeError(f"Registry unavailable: {e}") from e


def get_server(server_id: str) -> dict[str, Any]:
    """Fetch full details for a specific server by ID. Returns unwrapped server dict."""
    url = f"{REGISTRY_BASE}/servers/{urllib.parse.quote(server_id, safe='')}"
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "flux-cli/1.0"})  # noqa: S310
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            data = json.loads(resp.read().decode())
            return data.get("server", data)
    except urllib.error.URLError as e:
        raise RuntimeError(f"Registry unavailable: {e}") from e


def display_name(server: dict[str, Any]) -> str:
    """Return the best human-readable name for display."""
    return server.get("title") or server.get("name") or ""


def github_slug(server: dict[str, Any]) -> str | None:
    """Extract 'owner/repo' from a server's repository URL, or None."""
    url = (server.get("repository") or {}).get("url", "")
    if "github.com/" in url:
        parts = url.rstrip("/").split("github.com/", 1)
        if len(parts) == 2:
            slug = parts[1].rstrip(".git")
            if slug.count("/") >= 1:
                # Strip any subfolder beyond owner/repo
                return "/".join(slug.split("/")[:2])
    return None


def best_package(server: dict[str, Any]) -> tuple[str | None, str | None]:
    """Return (registry_name, package_name) for the most useful package, or (None, None).

    The registry schema stores installable packages in server["packages"] (if present).
    Many servers in the current registry are hosted-only (remotes) with no packages.
    """
    packages = server.get("packages") or []
    for preferred in ("npm", "pypi"):
        for pkg in packages:
            if pkg.get("registry_name") == preferred and pkg.get("name"):
                return preferred, pkg["name"]
    for pkg in packages:
        if pkg.get("name"):
            return pkg.get("registry_name", ""), pkg["name"]
    return None, None


def remote_url(server: dict[str, Any]) -> str | None:
    """Return the primary hosted remote URL, if any."""
    remotes = server.get("remotes") or []
    for r in remotes:
        if r.get("url"):
            return r["url"]
    return None


def suggest_flux_add(safe_name: str, server: dict[str, Any]) -> str | None:
    """Return the best `flux add mcp` command string for a registry server, or None."""
    reg, pkg = best_package(server)
    if reg == "npm":
        return f"flux add mcp {safe_name} --npx {pkg}"
    slug = github_slug(server)
    if slug:
        return f"flux add mcp {safe_name} --github {slug}"
    return None
