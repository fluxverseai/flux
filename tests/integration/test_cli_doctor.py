"""Integration tests: flux doctor"""

import pytest

from .conftest import run_flux


@pytest.mark.integration
class TestFluxDoctor:
    def test_runs_and_reports_checks(self, flux_env):
        env, _ = flux_env
        result = run_flux("doctor", env=env)
        # Should mention environment/dependency checks
        assert "Python" in result.stdout or "python" in result.stdout.lower()

    def test_reports_missing_marketplace_json(self, flux_env):
        env, root = flux_env
        mp = root / "marketplace" / "marketplace.json"
        if mp.exists():
            mp.unlink()
        result = run_flux("doctor", env=env)
        assert "marketplace" in result.stdout.lower() or "registry" in result.stdout.lower()

    def test_runtime_dependencies_checked(self, flux_env):
        env, _ = flux_env
        result = run_flux("doctor", env=env)
        output = result.stdout.lower()
        assert "uv" in output
        assert "git" in output

    def test_exits_zero_in_healthy_env(self, flux_env):
        env, _ = flux_env
        result = run_flux("doctor", env=env)
        assert result.returncode == 0
