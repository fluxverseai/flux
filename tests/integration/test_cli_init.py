"""Integration tests: flux init"""
import json

import pytest

from .conftest import run_flux


@pytest.mark.integration
class TestFluxInit:
    def test_creates_project_directory(self, flux_env):
        env, root = flux_env
        run_flux("init", "myproject", env=env, cwd=str(root))
        assert (root / "myproject").is_dir()

    def test_creates_flux_json(self, flux_env):
        env, root = flux_env
        run_flux("init", "myproject", env=env, cwd=str(root))
        flux_json_path = root / "myproject" / "flux.json"
        assert flux_json_path.exists()
        data = json.loads(flux_json_path.read_text())
        assert data["name"] == "myproject"
        assert "mcps" in data
        assert "skills" in data

    def test_creates_gitignore(self, flux_env):
        env, root = flux_env
        run_flux("init", "myproject", env=env, cwd=str(root))
        gitignore = root / "myproject" / ".gitignore"
        assert gitignore.exists()
        assert ".mcp.json" in gitignore.read_text()

    def test_exits_nonzero_if_project_exists(self, flux_env):
        env, root = flux_env
        project = root / "existing"
        project.mkdir(parents=True)
        (project / "flux.json").write_text('{"name": "existing"}')
        result = run_flux("init", "existing", env=env, cwd=str(root))
        assert result.returncode != 0
        assert "already exists" in result.stdout

    def test_success_message_shown(self, flux_env):
        env, root = flux_env
        result = run_flux("init", "myproject", env=env, cwd=str(root))
        assert result.returncode == 0
        assert "myproject" in result.stdout

    def test_init_current_dir(self, flux_env):
        env, root = flux_env
        project = root / "my-app"
        project.mkdir()
        result = run_flux("init", env=env, cwd=str(project))
        assert result.returncode == 0
        assert (project / "flux.json").exists()

    def test_init_registers_project(self, flux_env):
        env, root = flux_env
        run_flux("init", "tracked", env=env, cwd=str(root))
        projects_file = root / "projects.json"
        assert projects_file.exists()
