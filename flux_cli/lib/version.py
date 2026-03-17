"""Version checking for Flux — local version and PyPI update checks."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from packaging.version import InvalidVersion, Version

from flux_cli import __version__

_VERSION_RE = re.compile(r"^\d+[\d.]*\d+$")

PYPI_URL = "https://pypi.org/pypi/flux-cli/json"


def current_version() -> str:
    """Return the currently installed version string."""
    return __version__


def check_pypi_version(*, timeout: float = 5.0) -> str | None:
    """Query PyPI for the latest flux-cli version.

    Returns the version string on success, or ``None`` if PyPI is unreachable.
    """
    try:
        req = urllib.request.Request(PYPI_URL, headers={"Accept": "application/json"})  # noqa: S310
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            data = json.loads(resp.read().decode())
        ver = data["info"]["version"]
        # Sanitize: reject anything that doesn't look like a version string
        if not isinstance(ver, str) or not _VERSION_RE.match(ver):
            return None
        return ver
    except (urllib.error.URLError, OSError, KeyError, json.JSONDecodeError, ValueError):
        return None


def format_version_output(*, check: bool = False) -> str:
    """Build the human-readable version string.

    When *check* is ``True``, queries PyPI and appends update information.
    """
    local = current_version()

    if not check:
        return f"flux-cli v{local}"

    latest = check_pypi_version()

    if latest is None:
        return f"flux-cli v{local} (could not check for updates)"

    try:
        local_ver = Version(local)
        latest_ver = Version(latest)
    except InvalidVersion:
        # Fall back to string comparison if parsing fails
        if latest != local:
            return f"Update available: v{local} → v{latest}. Run: uv tool upgrade flux-cli"
        return f"flux-cli v{local} (up to date)"

    if latest_ver > local_ver:
        return f"Update available: v{local} → v{latest}. Run: uv tool upgrade flux-cli"
    if local_ver > latest_ver:
        return f"flux-cli v{local} (ahead of PyPI v{latest})"

    return f"flux-cli v{local} (up to date)"
