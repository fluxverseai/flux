"""Integration tests: flux doctor"""
import pytest

from .conftest import run_flux


@pytest.mark.integration
class TestFluxDoctor:
    def test_environment_checks_header(self, flux_env):
        env, _ = flux_env
        result = run_flux("doctor", env=env)
        assert "Environment" in result.stdout

    def test_reports_missing_src_dir(self, flux_env):
        env, root = flux_env
        import shutil
        shutil.rmtree(root / "src")
        result = run_flux("doctor", env=env)
        assert result.returncode == 0

    def test_runtime_dependencies_checked(self, flux_env):
        env, _ = flux_env
        result = run_flux("doctor", env=env)
        assert "node" in result.stdout
        assert "uv" in result.stdout
        assert "git" in result.stdout

    def test_exits_zero_in_healthy_env(self, flux_env):
        env, _ = flux_env
        result = run_flux("doctor", env=env)
        assert result.returncode == 0
