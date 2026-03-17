"""Canonical path constants for Flux's ~/.flux/ home directory.

All paths respect two environment variables:
  - FLUX_HOME      Override the default ~/.flux/ root
  - FLUX_TEST_ROOT If set, ALL paths are rooted under this directory
                   instead of ~/.flux/ (used for test isolation)
"""

from __future__ import annotations

import os
from pathlib import Path


def _resolve_flux_home() -> Path:
    """Determine the Flux home directory, respecting env overrides."""
    test_root = os.environ.get("FLUX_TEST_ROOT")
    if test_root:
        return Path(test_root)

    env_home = os.environ.get("FLUX_HOME")
    if env_home:
        return Path(env_home)

    return Path.home() / ".flux"


def flux_home() -> Path:
    """Return the resolved Flux home directory."""
    return _resolve_flux_home()


def registry_path() -> Path:
    """Path to the local plugin/MCP registry."""
    return flux_home() / "registry.json"


def mcps_dir() -> Path:
    """Directory containing installed MCP server configurations."""
    return flux_home() / "mcps"


def launchers_dir() -> Path:
    """Directory containing generated MCP launcher scripts."""
    return flux_home() / "mcps" / "launchers"


def skills_dir() -> Path:
    """Directory containing installed skills."""
    return flux_home() / "skills"


def sandbox_dir() -> Path:
    """Directory containing run sandboxes."""
    return flux_home() / "sandbox"


def projects_path() -> Path:
    """Path to the projects index file."""
    return flux_home() / "projects.json"


def secrets_path() -> Path:
    """Path to the secrets index file."""
    return flux_home() / "secrets.json"


def config_path() -> Path:
    """Path to the user configuration file."""
    return flux_home() / "config.toml"
