"""Integration tests: flux add / flux remove"""
import json
import os

import pytest

from .conftest import run_flux


def _mock_git_env(env, tmp_path):
    """Add a fake git that always succeeds, so tests don't touch the real repo."""
    fake_bin = tmp_path / "fakebin"
    fake_bin.mkdir(exist_ok=True)
    fake_git = fake_bin / "git"
    fake_git.write_text("#!/bin/bash\nexit 0\n")
    fake_git.chmod(0o755)
    env = dict(env)
    env["PATH"] = str(fake_bin) + os.pathsep + env.get("PATH", "")
    return env


@pytest.mark.integration
class TestFluxAddMcp:
    def test_add_npm_package(self, flux_env, tmp_path):
        env, root = flux_env
        result = run_flux(
            "add", "mcp", "new-mcp",
            "--npx", "@test/new-mcp",
            "--tags", "test",
            env=env,
        )
        assert result.returncode == 0
        manifest = json.loads((root / "marketplace" / "marketplace.json").read_text())
        assert "new-mcp" in manifest["mcp_definitions"]
        assert manifest["mcp_definitions"]["new-mcp"]["command"] == "npx"

    def test_add_npm_package_has_correct_args(self, flux_env):
        env, root = flux_env
        run_flux("add", "mcp", "new-mcp", "--npx", "@test/new-mcp", env=env)
        manifest = json.loads((root / "marketplace" / "marketplace.json").read_text())
        assert "@test/new-mcp" in manifest["mcp_definitions"]["new-mcp"]["args"]

    def test_add_duplicate_exits_nonzero(self, flux_env):
        env, _ = flux_env
        result = run_flux("add", "mcp", "memory", "--npx", "@test/memory", env=env)
        assert result.returncode != 0
        assert "already exists" in result.stdout

    def test_add_without_source_exits_nonzero(self, flux_env):
        env, _ = flux_env
        result = run_flux("add", "mcp", "new-mcp", "--tags", "test", env=env)
        assert result.returncode != 0

    def test_add_with_tags(self, flux_env):
        env, root = flux_env
        run_flux("add", "mcp", "tagged-mcp", "--npx", "@test/pkg", "--tags", "a,b,c", env=env)
        manifest = json.loads((root / "marketplace" / "marketplace.json").read_text())
        assert set(manifest["mcp_definitions"]["tagged-mcp"]["tags"]) == {"a", "b", "c"}


@pytest.mark.integration
class TestFluxRemoveMcp:
    def test_remove_existing_npm_mcp(self, flux_env):
        env, root = flux_env
        # First add it
        run_flux("add", "mcp", "to-remove", "--npx", "@test/pkg", env=env)
        # Then remove it
        result = run_flux("remove", "to-remove", env=env)
        assert result.returncode == 0
        manifest = json.loads((root / "marketplace" / "marketplace.json").read_text())
        assert "to-remove" not in manifest["mcp_definitions"]

    def test_remove_nonexistent_exits_nonzero(self, flux_env):
        env, _ = flux_env
        result = run_flux("remove", "does-not-exist", env=env)
        assert result.returncode != 0

    def test_remove_shows_sync_reminder(self, flux_env):
        env, _ = flux_env
        run_flux("add", "mcp", "to-remove", "--npx", "@test/pkg", env=env)
        result = run_flux("remove", "to-remove", env=env)
        assert "sync" in result.stdout.lower()
