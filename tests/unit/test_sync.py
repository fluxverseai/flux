"""Unit tests for flux_cli.lib.sync — sync engine, launcher generation, .mcp.json."""

from __future__ import annotations

import json
import platform
import stat
from unittest.mock import patch

from flux_cli.lib.sync import (
    _secret_lookup_command,
    generate_launcher,
    sync_project,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_registry(mcps=None, skills=None):
    """Build a minimal registry dict."""
    return {
        "version": "1.0.0",
        "mcp_definitions": mcps or {},
        "skill_definitions": skills or {},
    }


def _make_flux_json(project_dir, name="test-project", mcps=None, skills=None):
    """Write a flux.json into project_dir and return the dict."""
    data = {"name": name, "mcps": mcps or [], "skills": skills or []}
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "flux.json").write_text(json.dumps(data, indent=2))
    return data


# ---------------------------------------------------------------------------
# W2A.4: sync_project
# ---------------------------------------------------------------------------


class TestSyncGeneratesMcpJson:
    def test_sync_generates_mcp_json(self, tmp_path):
        project = tmp_path / "proj"
        _make_flux_json(project, mcps=["memory"])
        registry = _make_registry(mcps={
            "memory": {
                "type": "npm-package",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-memory"],
            }
        })

        success, issues = sync_project(project, registry)
        assert success
        assert issues == []

        mcp_json = project / ".mcp.json"
        assert mcp_json.exists()
        data = json.loads(mcp_json.read_text())
        assert "mcpServers" in data
        assert "memory" in data["mcpServers"]

    def test_sync_mcp_json_format_valid(self, tmp_path):
        project = tmp_path / "proj"
        _make_flux_json(project, mcps=["memory"])
        registry = _make_registry(mcps={
            "memory": {"command": "npx", "args": ["-y", "pkg"]},
        })

        sync_project(project, registry)
        data = json.loads((project / ".mcp.json").read_text())

        # Must have the Claude Code format: {"mcpServers": {...}}
        assert isinstance(data, dict)
        assert "mcpServers" in data
        server = data["mcpServers"]["memory"]
        assert "command" in server

    def test_sync_missing_mcp_errors(self, tmp_path):
        project = tmp_path / "proj"
        _make_flux_json(project, mcps=["nonexistent"])
        registry = _make_registry()

        success, issues = sync_project(project, registry)
        assert success  # sync still writes .mcp.json
        assert any("nonexistent" in i and "not found" in i for i in issues)

    def test_sync_empty_mcps(self, tmp_path):
        project = tmp_path / "proj"
        _make_flux_json(project, mcps=[])
        registry = _make_registry()

        success, issues = sync_project(project, registry)
        assert success
        assert issues == []
        data = json.loads((project / ".mcp.json").read_text())
        assert data["mcpServers"] == {}


class TestSyncGeneratesLauncher:
    def test_sync_generates_launcher_for_auth_mcp(self, tmp_path):
        project = tmp_path / "proj"
        launcher_dir = tmp_path / "launchers"
        _make_flux_json(project, mcps=["authed-mcp"])
        registry = _make_registry(mcps={
            "authed-mcp": {
                "command": "npx",
                "args": ["-y", "some-pkg"],
                "auth": {"env_vars": ["API_KEY"]},
            }
        })

        sync_project(project, registry, launcher_base=launcher_dir)

        launcher = launcher_dir / "authed-mcp.sh"
        assert launcher.exists()
        content = launcher.read_text()
        assert "API_KEY" in content

    def test_sync_launcher_no_embedded_secrets(self, tmp_path):
        project = tmp_path / "proj"
        launcher_dir = tmp_path / "launchers"
        _make_flux_json(project, mcps=["authed-mcp"])
        registry = _make_registry(mcps={
            "authed-mcp": {
                "command": "npx",
                "args": [],
                "auth": {"env_vars": ["SECRET_TOKEN"]},
            }
        })

        sync_project(project, registry, launcher_base=launcher_dir)

        launcher = launcher_dir / "authed-mcp.sh"
        content = launcher.read_text()
        # The script must use keystore lookup commands, not embed values
        assert "secret_value" not in content.lower()
        # Must contain lookup command
        if platform.system() == "Darwin":
            assert "security find-generic-password" in content
        else:
            assert "secret-tool lookup" in content


class TestSyncAllTrackedProjects:
    def test_sync_all_tracked_projects(self, tmp_path):
        """Verify sync_project works on multiple project dirs."""
        registry = _make_registry(mcps={
            "memory": {"command": "npx", "args": ["-y", "pkg"]},
        })

        projects = []
        for name in ("proj-a", "proj-b"):
            p = tmp_path / name
            _make_flux_json(p, name=name, mcps=["memory"])
            projects.append(p)

        for p in projects:
            success, issues = sync_project(p, registry)
            assert success
            assert issues == []
            assert (p / ".mcp.json").exists()


# ---------------------------------------------------------------------------
# W2A.5: Launcher script generation
# ---------------------------------------------------------------------------


class TestLauncherMacosUsesSecurity:
    @patch("flux_cli.lib.sync.platform.system", return_value="Darwin")
    def test_launcher_macos_uses_security(self, mock_sys, tmp_path):
        launcher_dir = tmp_path / "launchers"
        mcp_data = {
            "command": "npx",
            "args": ["-y", "pkg"],
            "auth": {"env_vars": ["MY_TOKEN"]},
        }
        path = generate_launcher("test-mcp", mcp_data, launcher_base=launcher_dir)
        assert path is not None
        content = path.read_text()
        assert "security find-generic-password" in content
        assert "flux.test-mcp" in content
        assert "MY_TOKEN" in content


class TestLauncherLinuxUsesSecretTool:
    @patch("flux_cli.lib.sync.platform.system", return_value="Linux")
    def test_launcher_linux_uses_secret_tool(self, mock_sys, tmp_path):
        launcher_dir = tmp_path / "launchers"
        mcp_data = {
            "command": "node",
            "args": ["server.js"],
            "auth": {"env_vars": ["API_KEY"]},
        }
        path = generate_launcher("linux-mcp", mcp_data, launcher_base=launcher_dir)
        assert path is not None
        content = path.read_text()
        assert "secret-tool lookup" in content
        assert "flux.linux-mcp" in content
        assert "API_KEY" in content


class TestLauncherExecutable:
    def test_launcher_executable(self, tmp_path):
        launcher_dir = tmp_path / "launchers"
        mcp_data = {
            "command": "npx",
            "args": [],
            "auth": {"env_vars": ["K"]},
        }
        path = generate_launcher("test-mcp", mcp_data, launcher_base=launcher_dir)
        assert path is not None
        mode = path.stat().st_mode
        assert mode & stat.S_IXUSR

    def test_launcher_returns_none_without_auth(self, tmp_path):
        launcher_dir = tmp_path / "launchers"
        mcp_data = {"command": "npx", "args": []}
        path = generate_launcher("test-mcp", mcp_data, launcher_base=launcher_dir)
        assert path is None


class TestLauncherScriptDirRelative:
    def test_launcher_script_dir_relative(self, tmp_path):
        launcher_dir = tmp_path / "launchers"
        source_dir = tmp_path / "mcps" / "my-mcp"
        source_dir.mkdir(parents=True)
        mcp_data = {
            "command": "uv",
            "args": ["run", "--directory", "{source_dir}", "serve"],
            "source_dir": str(source_dir),
            "auth": {"env_vars": ["K"]},
        }
        path = generate_launcher("my-mcp", mcp_data, launcher_base=launcher_dir)
        content = path.read_text()
        assert "$SCRIPT_DIR/" in content
        assert "{source_dir}" not in content


# ---------------------------------------------------------------------------
# Secret lookup command (platform-specific)
# ---------------------------------------------------------------------------


class TestSecretLookupCommand:
    @patch("flux_cli.lib.sync.platform.system", return_value="Darwin")
    def test_macos_uses_security(self, _mock):
        cmd = _secret_lookup_command("my-mcp", "API_KEY")
        assert "security find-generic-password" in cmd
        assert "flux.my-mcp" in cmd
        assert "API_KEY" in cmd

    @patch("flux_cli.lib.sync.platform.system", return_value="Linux")
    def test_linux_uses_secret_tool(self, _mock):
        cmd = _secret_lookup_command("my-mcp", "API_KEY")
        assert "secret-tool lookup" in cmd
        assert "flux.my-mcp" in cmd
