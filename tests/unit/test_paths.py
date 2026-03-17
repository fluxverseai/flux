"""Tests for flux_cli.lib.paths — Flux home directory path resolution."""

from pathlib import Path

from flux_cli.lib.paths import (
    config_path,
    flux_home,
    launchers_dir,
    mcps_dir,
    projects_path,
    registry_path,
    sandbox_dir,
    secrets_path,
    skills_dir,
)


class TestFluxHome:
    """Tests for flux_home() resolution."""

    def test_default_is_dot_flux(self, monkeypatch):
        monkeypatch.delenv("FLUX_HOME", raising=False)
        monkeypatch.delenv("FLUX_TEST_ROOT", raising=False)
        result = flux_home()
        assert result == Path.home() / ".flux"

    def test_flux_home_env_override(self, monkeypatch):
        monkeypatch.delenv("FLUX_TEST_ROOT", raising=False)
        monkeypatch.setenv("FLUX_HOME", "/custom/flux")
        assert flux_home() == Path("/custom/flux")

    def test_flux_test_root_takes_precedence(self, monkeypatch):
        monkeypatch.setenv("FLUX_HOME", "/custom/flux")
        monkeypatch.setenv("FLUX_TEST_ROOT", "/tmp/test-root")
        assert flux_home() == Path("/tmp/test-root")

    def test_flux_test_root_without_flux_home(self, monkeypatch):
        monkeypatch.delenv("FLUX_HOME", raising=False)
        monkeypatch.setenv("FLUX_TEST_ROOT", "/tmp/test-root")
        assert flux_home() == Path("/tmp/test-root")


class TestPathConstants:
    """All path helpers should return paths under flux_home()."""

    def test_registry_path(self, monkeypatch):
        monkeypatch.setenv("FLUX_TEST_ROOT", "/tmp/fx")
        monkeypatch.delenv("FLUX_HOME", raising=False)
        assert registry_path() == Path("/tmp/fx/registry.json")

    def test_mcps_dir(self, monkeypatch):
        monkeypatch.setenv("FLUX_TEST_ROOT", "/tmp/fx")
        monkeypatch.delenv("FLUX_HOME", raising=False)
        assert mcps_dir() == Path("/tmp/fx/mcps")

    def test_launchers_dir(self, monkeypatch):
        monkeypatch.setenv("FLUX_TEST_ROOT", "/tmp/fx")
        monkeypatch.delenv("FLUX_HOME", raising=False)
        assert launchers_dir() == Path("/tmp/fx/mcps/launchers")

    def test_skills_dir(self, monkeypatch):
        monkeypatch.setenv("FLUX_TEST_ROOT", "/tmp/fx")
        monkeypatch.delenv("FLUX_HOME", raising=False)
        assert skills_dir() == Path("/tmp/fx/skills")

    def test_sandbox_dir(self, monkeypatch):
        monkeypatch.setenv("FLUX_TEST_ROOT", "/tmp/fx")
        monkeypatch.delenv("FLUX_HOME", raising=False)
        assert sandbox_dir() == Path("/tmp/fx/sandbox")

    def test_projects_path(self, monkeypatch):
        monkeypatch.setenv("FLUX_TEST_ROOT", "/tmp/fx")
        monkeypatch.delenv("FLUX_HOME", raising=False)
        assert projects_path() == Path("/tmp/fx/projects.json")

    def test_secrets_path(self, monkeypatch):
        monkeypatch.setenv("FLUX_TEST_ROOT", "/tmp/fx")
        monkeypatch.delenv("FLUX_HOME", raising=False)
        assert secrets_path() == Path("/tmp/fx/secrets.json")

    def test_config_path(self, monkeypatch):
        monkeypatch.setenv("FLUX_TEST_ROOT", "/tmp/fx")
        monkeypatch.delenv("FLUX_HOME", raising=False)
        assert config_path() == Path("/tmp/fx/config.toml")


class TestTestIsolation:
    """FLUX_TEST_ROOT should fully isolate all paths."""

    def test_all_paths_under_test_root(self, monkeypatch, tmp_path):
        monkeypatch.setenv("FLUX_TEST_ROOT", str(tmp_path))
        monkeypatch.delenv("FLUX_HOME", raising=False)
        paths = [
            flux_home(),
            registry_path(),
            mcps_dir(),
            launchers_dir(),
            skills_dir(),
            sandbox_dir(),
            projects_path(),
            secrets_path(),
            config_path(),
        ]
        for p in paths:
            assert str(p).startswith(str(tmp_path)), f"{p} is not under {tmp_path}"
