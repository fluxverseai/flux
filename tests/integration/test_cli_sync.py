"""Integration tests: flux sync"""
import json

import pytest

from .conftest import run_flux


def _make_project(root, name, mcps=None, skills=None):
    project = root / "src" / name
    project.mkdir(parents=True, exist_ok=True)
    flux_json = {"name": name, "version": "0.1.0", "mcps": mcps or [], "skills": skills or []}
    (project / "flux.json").write_text(json.dumps(flux_json))
    return project


@pytest.mark.integration
class TestFluxSync:
    def test_generates_mcp_json_for_project(self, flux_env):
        env, root = flux_env
        _make_project(root, "proj1", mcps=["memory"])
        result = run_flux("sync", env=env)
        assert result.returncode == 0
        mcp_json_path = root / "src" / "proj1" / ".mcp.json"
        assert mcp_json_path.exists()
        data = json.loads(mcp_json_path.read_text())
        assert "memory" in data["mcpServers"]

    def test_mcp_json_has_command_field(self, flux_env):
        env, root = flux_env
        _make_project(root, "proj1", mcps=["memory"])
        run_flux("sync", env=env)
        data = json.loads((root / "src" / "proj1" / ".mcp.json").read_text())
        assert "command" in data["mcpServers"]["memory"]

    def test_skips_project_without_flux_json(self, flux_env):
        env, root = flux_env
        (root / "src" / "no-config").mkdir(parents=True)
        result = run_flux("sync", env=env)
        assert result.returncode == 0
        assert "skipped" in result.stdout

    def test_reports_unknown_mcp(self, flux_env):
        env, root = flux_env
        _make_project(root, "proj1", mcps=["nonexistent-mcp"])
        result = run_flux("sync", env=env)
        assert "nonexistent-mcp" in result.stdout
        assert "issues" in result.stdout.lower() or "❌" in result.stdout

    def test_syncs_multiple_projects(self, flux_env):
        env, root = flux_env
        _make_project(root, "proj1", mcps=["memory"])
        _make_project(root, "proj2", mcps=["memory"])
        result = run_flux("sync", env=env)
        assert "2 synced" in result.stdout

    def test_no_src_dir_exits_nonzero(self, flux_env):
        env, root = flux_env
        import shutil
        shutil.rmtree(root / "src")
        result = run_flux("sync", env=env)
        assert result.returncode != 0

    def test_no_projects_shows_message(self, flux_env):
        env, root = flux_env
        result = run_flux("sync", env=env)
        assert result.returncode == 0
        assert "No projects found" in result.stdout
