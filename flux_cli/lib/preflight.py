"""Pre-flight validation for sandbox creation.

Runs 6 checks that ALL must pass before a sandbox is created:
1. MCP exists in registry
2. MCP source available on disk (for cloned types)
3. Auth satisfied (all env_vars have secrets in keystore)
4. Auth pre-flight passes (check_cmd succeeds)
5. Skill exists in registry and on disk
6. Build artifacts present (for MCPs with build_cmd)
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from flux_cli.lib.paths import flux_home, registry_path, skills_dir
from flux_cli.lib.secrets import load_secrets_index

# Types that require a cloned source directory on disk
_CLONED_TYPES = {"github", "git-submodule", "local"}


@dataclass
class PreflightResult:
    """Result of all pre-flight checks."""

    ok: bool
    errors: list[str] = field(default_factory=list)


def run_preflight(
    mcps: list[str],
    skills: list[str],
    registry: dict[str, Any] | None = None,
) -> PreflightResult:
    """Run all pre-flight checks and return the result.

    Parameters
    ----------
    mcps : list[str]
        MCP names required for the run.
    skills : list[str]
        Skill names required for the run.
    registry : dict, optional
        Pre-loaded registry dict.  If ``None``, loaded from disk.

    Returns
    -------
    PreflightResult
        ``.ok`` is True only when every check passes.
    """
    if registry is None:
        registry = _load_registry()

    mcp_defs = registry.get("mcp_definitions", {})
    skill_defs = registry.get("skill_definitions", {})
    errors: list[str] = []

    for mcp_name in mcps:
        _check_mcp_exists(mcp_name, mcp_defs, errors)
        if mcp_name in mcp_defs:
            mcp_data = mcp_defs[mcp_name]
            _check_mcp_source(mcp_name, mcp_data, errors)
            _check_auth_secrets(mcp_name, mcp_data, errors)
            _check_auth_preflight(mcp_name, mcp_data, errors)
            _check_build_artifacts(mcp_name, mcp_data, errors)

    for skill_name in skills:
        _check_skill(skill_name, skill_defs, errors)

    return PreflightResult(ok=len(errors) == 0, errors=errors)


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def _check_mcp_exists(
    name: str,
    mcp_defs: dict[str, Any],
    errors: list[str],
) -> None:
    """Check 1: MCP exists in registry."""
    if name not in mcp_defs:
        available = ", ".join(sorted(mcp_defs.keys())) or "(none)"
        errors.append(
            f"MCP '{name}' not found in registry. "
            f"Available: {available}. "
            f"Fix: flux add mcp {name} --npx <package>"
        )


def _check_mcp_source(
    name: str,
    mcp_data: dict[str, Any],
    errors: list[str],
) -> None:
    """Check 2: MCP source directory present on disk (for cloned types)."""
    mcp_type = mcp_data.get("type", "")
    if mcp_type not in _CLONED_TYPES:
        return

    source_dir = mcp_data.get("source_dir", "")
    if not source_dir:
        return

    source_path = Path(source_dir)
    if not source_path.is_absolute():
        source_path = flux_home().parent / source_dir

    if not source_path.exists():
        errors.append(
            f"MCP '{name}' source directory missing: {source_path}. "
            f"Fix: flux add mcp {name} --github <repo>"
        )


def _check_auth_secrets(
    name: str,
    mcp_data: dict[str, Any],
    errors: list[str],
) -> None:
    """Check 3: All required env_vars have secrets in the keystore."""
    auth = mcp_data.get("auth", {})
    env_vars = auth.get("env_vars", [])
    if not env_vars:
        return

    secrets_index = load_secrets_index()
    stored_keys = secrets_index.get(name, [])

    for var in env_vars:
        if var not in stored_keys:
            errors.append(
                f"MCP '{name}' missing secret '{var}'. "
                f"Fix: flux secret set {name} {var} <value>"
            )


def _check_auth_preflight(
    name: str,
    mcp_data: dict[str, Any],
    errors: list[str],
) -> None:
    """Check 4: Auth check_cmd succeeds (e.g. ``gh auth status``)."""
    auth = mcp_data.get("auth", {})
    check_cmd = auth.get("check_cmd")
    if not check_cmd:
        return

    try:
        result = subprocess.run(  # noqa: S603
            check_cmd,
            capture_output=True,
            timeout=10,
        )
        if result.returncode != 0:
            fix_desc = auth.get("fix_description", f"Run: {' '.join(auth.get('fix_cmd', []))}")
            errors.append(
                f"MCP '{name}' auth check failed (exit {result.returncode}). "
                f"Fix: {fix_desc}"
            )
    except FileNotFoundError:
        fix_desc = auth.get("fix_description", f"Install {check_cmd[0]}")
        errors.append(
            f"MCP '{name}' auth check command not found: {check_cmd[0]}. "
            f"Fix: {fix_desc}"
        )
    except subprocess.TimeoutExpired:
        errors.append(
            f"MCP '{name}' auth check timed out after 10s."
        )


def _check_skill(
    name: str,
    skill_defs: dict[str, Any],
    errors: list[str],
) -> None:
    """Check 5: Skill exists in registry and source is on disk."""
    if name not in skill_defs:
        available = ", ".join(sorted(skill_defs.keys())) or "(none)"
        errors.append(
            f"Skill '{name}' not found in registry. "
            f"Available: {available}. "
            f"Fix: flux add skill {name} --github <repo>"
        )
        return

    skill_data = skill_defs[name]
    source_dir = skill_data.get("source_dir", "")
    if source_dir:
        source_path = Path(source_dir)
        if not source_path.is_absolute():
            # Try skills_dir first, then flux_home parent
            candidate = skills_dir() / name
            if not candidate.exists():
                candidate = flux_home().parent / source_dir
            source_path = candidate
        if not source_path.exists():
            errors.append(
                f"Skill '{name}' source missing at {source_path}. "
                f"Fix: flux add skill {name} --github <repo>"
            )


def _check_build_artifacts(
    name: str,
    mcp_data: dict[str, Any],
    errors: list[str],
) -> None:
    """Check 6: Build artifacts present (for MCPs with build_cmd)."""
    build_cmd = mcp_data.get("build_cmd")
    if not build_cmd:
        return

    source_dir = mcp_data.get("source_dir", "")
    if not source_dir:
        return

    source_path = Path(source_dir)
    if not source_path.is_absolute():
        source_path = flux_home().parent / source_dir

    # Check for common build output directories
    build_indicators = ["node_modules", "dist", "build", ".build", "__pycache__"]
    has_artifacts = any((source_path / ind).exists() for ind in build_indicators)

    if source_path.exists() and not has_artifacts:
        errors.append(
            f"MCP '{name}' appears unbuilt (no build artifacts in {source_path}). "
            f"Fix: cd {source_path} && {build_cmd}"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_registry() -> dict[str, Any]:
    """Load the registry from disk."""
    import json

    path = registry_path()
    if not path.exists():
        return {"version": "1.0.0", "mcp_definitions": {}, "skill_definitions": {}}
    with open(path) as f:
        return json.load(f)
