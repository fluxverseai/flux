"""Integration tests: flux list"""
import pytest

from .conftest import run_flux


@pytest.mark.integration
class TestFluxList:
    def test_shows_mcp_names(self, flux_env):
        env, _ = flux_env
        result = run_flux("list", env=env)
        assert result.returncode == 0
        assert "memory" in result.stdout
        assert "wikijs-mcp" in result.stdout
        assert "github-mcp" in result.stdout

    def test_shows_skill_names(self, flux_env):
        env, _ = flux_env
        result = run_flux("list", env=env)
        assert "claude-xlsx" in result.stdout

    def test_shows_mcp_type(self, flux_env):
        env, _ = flux_env
        result = run_flux("list", env=env)
        assert "npm-package" in result.stdout
        assert "git-submodule" in result.stdout

    def test_shows_tags(self, flux_env):
        env, _ = flux_env
        result = run_flux("list", env=env)
        assert "memory" in result.stdout
        assert "wiki" in result.stdout

    def test_exits_zero(self, flux_env):
        env, _ = flux_env
        result = run_flux("list", env=env)
        assert result.returncode == 0
