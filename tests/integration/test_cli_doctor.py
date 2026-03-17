"""Integration tests: flux doctor"""
import pytest

from .conftest import run_flux


@pytest.mark.integration
class TestFluxDoctor:
    def test_structure_checks_pass_with_valid_tree(self, flux_env):
        env, _ = flux_env
        result = run_flux("doctor", env=env)
        # Should mention the structure section
        assert "Flux Structure" in result.stdout

    def test_reports_missing_src_dir(self, flux_env):
        env, root = flux_env
        import shutil
        shutil.rmtree(root / "src")
        result = run_flux("doctor", env=env)
        # Doctor auto-fixes src/ — either shows fixed or the check passes
        assert result.returncode == 0
        # src/ should be recreated by auto-fix
        assert (root / "src").exists()

    def test_reports_missing_marketplace_json(self, flux_env):
        env, root = flux_env
        (root / "marketplace" / "marketplace.json").unlink()
        result = run_flux("doctor", env=env)
        # marketplace.json missing should be flagged
        assert "marketplace.json" in result.stdout

    def test_runtime_dependencies_checked(self, flux_env):
        env, _ = flux_env
        result = run_flux("doctor", env=env)
        assert "node" in result.stdout
        assert "npx" in result.stdout
        assert "uv" in result.stdout
        assert "git" in result.stdout

    def test_exits_zero_in_healthy_env(self, flux_env):
        env, _ = flux_env
        result = run_flux("doctor", env=env)
        assert result.returncode == 0
