"""Input validation for Flux CLI.

Provides validation functions for MCP/skill names, registry schema,
and flux.json project files.
"""

from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Name validation
# ---------------------------------------------------------------------------

_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")
_MIN_NAME_LEN = 2
_MAX_NAME_LEN = 50


def validate_name(name: str) -> tuple[bool, str]:
    """Validate an MCP or skill name.

    Rules:
    - Lowercase alphanumeric characters and hyphens only
    - Must start and end with an alphanumeric character
    - Between 2 and 50 characters inclusive

    Returns (True, "") on success, or (False, reason) on failure.
    """
    if len(name) < _MIN_NAME_LEN:
        return False, f"Name must be at least {_MIN_NAME_LEN} characters, got {len(name)}"
    if len(name) > _MAX_NAME_LEN:
        return False, f"Name must be at most {_MAX_NAME_LEN} characters, got {len(name)}"
    if name != name.lower():
        return False, "Name must be lowercase"
    if not _NAME_PATTERN.match(name):
        return False, (
            "Name must contain only lowercase alphanumeric characters and hyphens,"
            " and start/end with alphanumeric"
        )
    return True, ""


# ---------------------------------------------------------------------------
# Registry schema validation
# ---------------------------------------------------------------------------

_VALID_MCP_TYPES = {"npm-package", "uvx-package", "github", "local"}
_VALID_SKILL_TYPES = {"github", "local"}


def validate_registry(data: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate registry.json structure."""
    errors: list[str] = []

    if not isinstance(data, dict):
        return False, ["Registry must be a JSON object"]

    if "version" not in data:
        errors.append("Missing required field: version")

    for name, defn in data.get("mcp_definitions", {}).items():
        ok, reason = validate_name(name)
        if not ok:
            errors.append(f"Invalid MCP name '{name}': {reason}")
        if not isinstance(defn, dict):
            errors.append(f"MCP '{name}' definition must be an object")
            continue
        mcp_type = defn.get("type")
        if mcp_type and mcp_type not in _VALID_MCP_TYPES:
            errors.append(f"MCP '{name}' has invalid type '{mcp_type}' (valid: {', '.join(sorted(_VALID_MCP_TYPES))})")

    for name, defn in data.get("skill_definitions", {}).items():
        ok, reason = validate_name(name)
        if not ok:
            errors.append(f"Invalid skill name '{name}': {reason}")
        if not isinstance(defn, dict):
            errors.append(f"Skill '{name}' definition must be an object")

    return len(errors) == 0, errors


# ---------------------------------------------------------------------------
# flux.json schema validation
# ---------------------------------------------------------------------------

def validate_flux_json(data: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate a project's flux.json structure."""
    errors: list[str] = []

    if not isinstance(data, dict):
        return False, ["flux.json must be a JSON object"]

    if "name" not in data:
        errors.append("Missing required field: name")

    mcps = data.get("mcps")
    if mcps is not None and not isinstance(mcps, list):
        errors.append("'mcps' must be a list")

    skills = data.get("skills")
    if skills is not None and not isinstance(skills, list):
        errors.append("'skills' must be a list")

    return len(errors) == 0, errors
