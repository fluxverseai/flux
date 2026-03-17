"""mcp_config.py — Utility for enriching MCP server configurations."""

from __future__ import annotations

from typing import Any


def enrich_with_marketplace(servers: dict[str, Any], mcp_registry: dict[str, Any]) -> dict[str, Any]:
    """Merge marketplace auth metadata into server configs from .mcp.json."""
    enriched = {}
    for name, config in servers.items():
        merged = dict(config)
        if name in mcp_registry:
            for k, v in mcp_registry[name].items():
                if k not in merged:
                    merged[k] = v
        enriched[name] = merged
    return enriched
