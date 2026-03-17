"""Unit tests for flux_cli.lib.version — version display and PyPI update check."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from flux_cli.lib.version import (
    check_pypi_version,
    current_version,
    format_version_output,
)


class TestVersionShowsVersion:
    def test_version_shows_version(self):
        """flux version prints the installed version."""
        from flux_cli import __version__

        assert current_version() == __version__

    def test_format_version_no_check(self):
        """Without --check, only the local version is shown."""
        result = format_version_output(check=False)
        assert result.startswith("flux-cli v")
        assert current_version() in result


class TestVersionCheckNewerAvailable:
    def test_version_check_newer_available(self):
        """--check shows upgrade instructions when a newer version exists on PyPI."""
        fake_response = MagicMock()
        fake_response.read.return_value = json.dumps(
            {"info": {"version": "1.0.0"}}
        ).encode()
        fake_response.__enter__ = lambda s: s
        fake_response.__exit__ = MagicMock(return_value=False)

        with patch("flux_cli.lib.version.urllib.request.urlopen", return_value=fake_response):
            result = format_version_output(check=True)

        assert "Update available" in result
        assert "v1.0.0" in result
        assert "uv tool upgrade flux-cli" in result


class TestVersionCheckUpToDate:
    def test_version_check_up_to_date(self):
        """--check shows 'up to date' when PyPI version matches local."""
        local = current_version()
        fake_response = MagicMock()
        fake_response.read.return_value = json.dumps(
            {"info": {"version": local}}
        ).encode()
        fake_response.__enter__ = lambda s: s
        fake_response.__exit__ = MagicMock(return_value=False)

        with patch("flux_cli.lib.version.urllib.request.urlopen", return_value=fake_response):
            result = format_version_output(check=True)

        assert "up to date" in result
        assert f"v{local}" in result


class TestVersionCheckPypiUnreachable:
    def test_version_check_pypi_unreachable(self):
        """--check shows graceful fallback when PyPI is unreachable."""
        import urllib.error

        with patch(
            "flux_cli.lib.version.urllib.request.urlopen",
            side_effect=urllib.error.URLError("Network unreachable"),
        ):
            result = format_version_output(check=True)

        assert "could not check for updates" in result
        assert f"v{current_version()}" in result

    def test_check_pypi_version_returns_none_on_error(self):
        """check_pypi_version returns None when PyPI is down."""
        import urllib.error

        with patch(
            "flux_cli.lib.version.urllib.request.urlopen",
            side_effect=urllib.error.URLError("timeout"),
        ):
            assert check_pypi_version() is None
