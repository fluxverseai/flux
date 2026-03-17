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
        project = _make_project(root, "proj1", mcps=["memory"])
        result = run_flux("sync", env=env, cwd=str(project))
        assert result.returncode == 0, result.stdout
        mcp_json_path = project / ".mcp.json"
        assert mcp_json_path.exists()
        data = json.loads(mcp_json_path.read_text())
        assert "memory" in data["mcpServers"]

    def test_mcp_json_has_command_field(self, flux_env):
        env, root = flux_env
        project = _make_project(root, "proj1", mcps=["memory"])
        run_flux("sync", env=env, cwd=str(project))
        data = json.loads((project / ".mcp.json").read_text())
        assert "command" in data["mcpServers"]["memory"]

    def test_reports_unknown_mcp(self, flux_env):
        env, root = flux_env
        project = _make_project(root, "proj1", mcps=["nonexistent-mcp"])
        result = run_flux("sync", env=env, cwd=str(project))
        assert "nonexistent-mcp" in result.stdout

    def test_syncs_all_tracked_projects(self, flux_env):
        """flux sync --all syncs all registered projects."""
        env, root = flux_env
        p1 = _make_project(root, "proj1", mcps=["memory"])
        p2 = _make_project(root, "proj2", mcps=["memory"])
        # Register them via flux init (which writes to projects.json)
        run_flux("init", env=env, cwd=str(p1))
        run_flux("init", env=env, cwd=str(p2))
        # Now sync --all should work (but projects already have flux.json so init will fail)
        # Instead, register them manually
        projects_data = {
            "projects": [
                {"path": str(p1), "name": "proj1", "registered_at": "2026-01-01"},
                {"path": str(p2), "name": "proj2", "registered_at": "2026-01-01"},
            ]
        }
        (root / "projects.json").write_text(json.dumps(projects_data))
        result = run_flux("sync", "--all", env=env)
        assert result.returncode == 0, result.stdout
        assert "2 synced" in result.stdout

    def test_no_flux_json_exits_nonzero(self, flux_env):
        env, root = flux_env
        empty_dir = root / "emptydir"
        empty_dir.mkdir()
        result = run_flux("sync", env=env, cwd=str(empty_dir))
        assert result.returncode != 0

    def test_no_projects_shows_message(self, flux_env):
        env, root = flux_env
        empty_dir = root / "emptydir"
        empty_dir.mkdir()
        result = run_flux("sync", env=env, cwd=str(empty_dir))
        assert "No flux.json" in result.stdout or "no" in result.stdout.lower()
