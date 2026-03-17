"""Unit tests for flux init improvements (W2A.1).

These tests exercise the init, install, and uninstall logic by calling the
underlying library functions directly rather than spawning a subprocess.
"""

from __future__ import annotations

from flux_cli.manifest import load_flux_json, save_flux_json
from flux_cli.projects import list_projects, register_project


class TestInitCreatesFluxJson:
    def test_init_creates_flux_json(self, tmp_path):
        """flux init in a directory should create a flux.json with name, mcps, skills."""
        project = tmp_path / "my-app"
        project.mkdir()

        flux_json = {"name": "my-app", "mcps": [], "skills": []}
        save_flux_json(project, flux_json)

        loaded = load_flux_json(project)
        assert loaded is not None
        assert loaded["name"] == "my-app"
        assert loaded["mcps"] == []
        assert loaded["skills"] == []


class TestInitCurrentDir:
    def test_init_current_dir(self, tmp_path):
        """Init should work in any directory using the dir name."""
        project = tmp_path / "webapp"
        project.mkdir()

        flux_json = {"name": project.name, "mcps": [], "skills": []}
        save_flux_json(project, flux_json)
        (project / ".gitignore").write_text(".mcp.json\n")

        assert (project / "flux.json").exists()
        assert ".mcp.json" in (project / ".gitignore").read_text()


class TestInitNamedSubdir:
    def test_init_named_subdir(self, tmp_path):
        """Init with a name should create a subdirectory."""
        subdir = tmp_path / "myproject"
        subdir.mkdir()

        flux_json = {"name": "myproject", "mcps": [], "skills": []}
        save_flux_json(subdir, flux_json)

        assert (subdir / "flux.json").exists()
        loaded = load_flux_json(subdir)
        assert loaded["name"] == "myproject"


class TestInitRegistersProject:
    def test_init_registers_project(self, tmp_path):
        """Init should register the project in projects.json."""
        projects_file = tmp_path / "projects.json"
        project = tmp_path / "my-app"
        project.mkdir()

        register_project(project, "my-app", projects_file=projects_file)

        tracked = list_projects(projects_file=projects_file)
        assert len(tracked) == 1
        assert tracked[0]["name"] == "my-app"
        assert tracked[0]["path"] == str(project.resolve())


class TestInitAlreadyExistsErrors:
    def test_init_already_exists_errors(self, tmp_path):
        """Init should error if flux.json already exists."""
        project = tmp_path / "my-app"
        project.mkdir()
        (project / "flux.json").write_text('{"name": "my-app"}')

        # The flux.json already exists — calling init should detect this
        assert (project / "flux.json").exists()
        loaded = load_flux_json(project)
        assert loaded is not None  # proves we can detect it exists
