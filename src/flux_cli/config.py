"""Configuration management for Flux using TOML files.

Reads/writes ~/.flux/config.toml (or wherever paths.config_path() points).
"""

from __future__ import annotations

import platform
import tempfile
import tomllib
from pathlib import Path
from typing import Any

from flux_cli.paths import config_path, flux_home

# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

def detect_secrets_backend() -> str:
    """Return 'keychain' on macOS, 'secret-service' on Linux, 'plaintext' otherwise."""
    system = platform.system().lower()
    if system == "darwin":
        return "keychain"
    if system == "linux":
        return "secret-service"
    return "plaintext"


# ---------------------------------------------------------------------------
# Default config
# ---------------------------------------------------------------------------

def default_config() -> dict[str, Any]:
    """Return the default configuration dict."""
    return {
        "secrets": {
            "backend": detect_secrets_backend(),
        },
        "paths": {
            "flux_home": str(flux_home()),
        },
    }


# ---------------------------------------------------------------------------
# Load / save
# ---------------------------------------------------------------------------

def load_config(path: Path | None = None) -> dict[str, Any]:
    """Load configuration from TOML, merging file values over defaults."""
    cfg = default_config()
    target = path or config_path()

    if target.exists():
        with open(target, "rb") as f:
            file_cfg = tomllib.load(f)
        _deep_merge(cfg, file_cfg)

    return cfg


def save_config(cfg: dict[str, Any], path: Path | None = None) -> None:
    """Atomically write configuration to a TOML file."""
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
    try:
        with open(fd, "w") as f:
            f.write(_to_toml(cfg))
        Path(tmp).replace(target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> None:
    """Recursively merge *override* into *base* in place."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def _to_toml(cfg: dict[str, Any], _prefix: str = "") -> str:
    """Minimal TOML serializer for flat/one-level-nested dicts."""
    lines: list[str] = []
    for key, value in cfg.items():
        if not isinstance(value, dict):
            lines.append(f"{key} = {_toml_value(value)}")

    for key, value in cfg.items():
        if isinstance(value, dict):
            section = f"{_prefix}{key}" if not _prefix else f"{_prefix}.{key}"
            lines.append(f"\n[{section}]")
            for k, v in value.items():
                lines.append(f"{k} = {_toml_value(v)}")

    return "\n".join(lines) + "\n"


def _toml_value(v: Any) -> str:
    """Format a single value as TOML."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, str):
        escaped = v.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return f'"{v}"'
