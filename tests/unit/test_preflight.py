"""Unit tests for flux_cli.preflight — pre-flight validation."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from flux_cli.preflight import run_preflight

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def base_registry(tmp_path):
    """Return a registry dict with known MCPs and skills."""
    # Create source dirs that the checks expect
    mcp_source = tmp_path / "mcps" / "wikijs-mcp"
    mcp_source.mkdir(parents=True)
    # Add a build artifact so build check passes
    (mcp_source / "node_modules").mkdir()

    skill_source = tmp_path / "skills" / "claude-xlsx"
    skill_source.mkdir(parents=True)

    return {
        "version": "1.0.0",
        "mcp_definitions": {
            "memory": {
                "type": "npm-package",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-memory"],
            },
            "wikijs-mcp": {
                "type": "git-submodule",
                "source_dir": str(mcp_source),
                "command": "uv",
                "args": ["run", "--directory", "{source_dir}", "wikijs-mcp-server"],
                "auth": {
                    "type": "keychain",
                    "env_vars": ["WIKIJS_URL", "WIKIJS_API_KEY"],
                },
            },
            "github-mcp": {
                "type": "npm-package",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-github"],
                "auth": {
                    "type": "github-cli",
                    "check_cmd": ["gh", "auth", "status"],
                    "fix_cmd": ["gh", "auth", "login"],
                    "fix_description": "Authenticate with GitHub CLI",
                },
            },
            "needs-build": {
                "type": "github",
                "source_dir": str(tmp_path / "mcps" / "needs-build"),
                "command": "node",
                "args": ["index.js"],
                "build_cmd": "npm install && npm run build",
            },
        },
        "skill_definitions": {
            "claude-xlsx": {
                "type": "git-submodule",
                "source_dir": str(skill_source),
            },
        },
    }


@pytest.fixture()
def _patch_secrets_index(monkeypatch, tmp_path):
    """Patch secrets index to use a temporary file."""
    secrets_file = tmp_path / "secrets.json"
    monkeypatch.setattr("flux_cli.paths._resolve_flux_home", lambda: tmp_path)
    return secrets_file


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPreflightMissingMcp:
    def test_preflight_missing_mcp(self, base_registry):
        """MCP not in registry triggers an error with fix command."""
        result = run_preflight(["nonexistent"], [], registry=base_registry)
        assert not result.ok
        assert any("nonexistent" in e and "not found" in e for e in result.errors)
        assert any("flux add mcp" in e for e in result.errors)


class TestPreflightMissingAuth:
    def test_preflight_missing_auth(self, base_registry, _patch_secrets_index):
        """MCP with env_vars but no stored secrets triggers an error."""
        result = run_preflight(["wikijs-mcp"], [], registry=base_registry)
        assert not result.ok
        assert any("WIKIJS_URL" in e for e in result.errors)
        assert any("flux secret set" in e for e in result.errors)


class TestPreflightAuthCheckFails:
    def test_preflight_auth_check_fails(self, base_registry, mocker):
        """MCP with check_cmd that fails triggers an error."""
        mock_run = mocker.patch("flux_cli.preflight.subprocess.run")
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_run.return_value = mock_result

        result = run_preflight(["github-mcp"], [], registry=base_registry)
        assert not result.ok
        assert any("auth check failed" in e for e in result.errors)
        assert any("Authenticate with GitHub CLI" in e for e in result.errors)

    def test_preflight_auth_check_cmd_not_found(self, base_registry, mocker):
        """MCP with check_cmd where binary is missing triggers an error."""
        mocker.patch(
            "flux_cli.preflight.subprocess.run",
            side_effect=FileNotFoundError,
        )
        result = run_preflight(["github-mcp"], [], registry=base_registry)
        assert not result.ok
        assert any("not found" in e for e in result.errors)


class TestPreflightMissingSkill:
    def test_preflight_missing_skill(self, base_registry):
        """Skill not in registry triggers an error with fix command."""
        result = run_preflight([], ["nonexistent-skill"], registry=base_registry)
        assert not result.ok
        assert any("nonexistent-skill" in e and "not found" in e for e in result.errors)
        assert any("flux add skill" in e for e in result.errors)

    def test_preflight_skill_source_missing(self, base_registry, tmp_path):
        """Skill in registry but source dir missing triggers an error."""
        base_registry["skill_definitions"]["missing-src"] = {
            "type": "github",
            "source_dir": str(tmp_path / "nonexistent-dir"),
        }
        result = run_preflight([], ["missing-src"], registry=base_registry)
        assert not result.ok
        assert any("source missing" in e for e in result.errors)


class TestPreflightUnbuiltMcp:
    def test_preflight_unbuilt_mcp(self, base_registry, tmp_path):
        """MCP with build_cmd but no build artifacts triggers an error."""
        # Create source dir without build artifacts
        source = tmp_path / "mcps" / "needs-build"
        source.mkdir(parents=True)

        result = run_preflight(["needs-build"], [], registry=base_registry)
        assert not result.ok
        assert any("unbuilt" in e for e in result.errors)
        assert any("npm install" in e for e in result.errors)


class TestPreflightAllPass:
    def test_preflight_all_pass(self, base_registry, _patch_secrets_index, tmp_path):
        """All checks pass for a correctly configured MCP (npm-package, no auth)."""
        result = run_preflight(["memory"], [], registry=base_registry)
        assert result.ok
        assert result.errors == []

    def test_preflight_all_pass_with_auth(
        self, base_registry, _patch_secrets_index, tmp_path
    ):
        """All checks pass when secrets are stored for authed MCP."""
        # Write secrets index with the required keys
        secrets_file = tmp_path / "secrets.json"
        secrets_file.write_text(
            json.dumps({"wikijs-mcp": ["WIKIJS_URL", "WIKIJS_API_KEY"]})
        )

        result = run_preflight(["wikijs-mcp"], [], registry=base_registry)
        assert result.ok
        assert result.errors == []

    def test_preflight_empty_lists(self, base_registry):
        """No MCPs or skills to check always passes."""
        result = run_preflight([], [], registry=base_registry)
        assert result.ok
        assert result.errors == []
