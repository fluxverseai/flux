"""Unit tests for lib/mcp_config.py"""
import stat

import flux_cli.mcp_config as mc

# ---------------------------------------------------------------------------
# generate_launcher
# ---------------------------------------------------------------------------

class TestGenerateLauncher:
    def test_returns_none_without_auth_env_vars(self, patch_mcp_config_paths):
        mcp_data = {"type": "npm-package", "command": "npx", "args": ["-y", "some-pkg"]}
        assert mc.generate_launcher("mymcp", mcp_data) is None

    def test_creates_sh_file(self, patch_mcp_config_paths, flux_root):
        mcp_data = {
            "command": "npx",
            "args": ["-y", "some-pkg"],
            "auth": {"env_vars": ["MY_KEY"]},
        }
        path = mc.generate_launcher("mymcp", mcp_data)
        assert path is not None
        assert path.exists()
        assert path.suffix == ".sh"
        assert path.name == "mymcp.sh"

    def test_script_is_executable(self, patch_mcp_config_paths, flux_root):
        mcp_data = {
            "command": "npx",
            "args": ["-y", "pkg"],
            "auth": {"env_vars": ["K"]},
        }
        path = mc.generate_launcher("mymcp", mcp_data)
        mode = path.stat().st_mode
        assert mode & stat.S_IXUSR  # owner execute bit

    def test_script_contains_security_export(self, patch_mcp_config_paths, flux_root):
        mcp_data = {
            "command": "npx",
            "args": [],
            "auth": {"env_vars": ["SECRET_KEY"]},
        }
        path = mc.generate_launcher("mymcp", mcp_data)
        content = path.read_text()
        assert "security find-generic-password" in content
        assert "SECRET_KEY" in content
        assert "flux.mymcp" in content

    def test_script_has_shebang(self, patch_mcp_config_paths, flux_root):
        mcp_data = {"command": "npx", "args": [], "auth": {"env_vars": ["K"]}}
        path = mc.generate_launcher("mymcp", mcp_data)
        assert path.read_text().startswith("#!/bin/bash")

    def test_resolves_source_dir_placeholder(self, patch_mcp_config_paths, flux_root):
        # Create a fake source dir so relpath is meaningful
        fake_src = flux_root / "marketplace" / "mcps" / "mymcp"
        fake_src.mkdir(parents=True)
        mcp_data = {
            "source_dir": "marketplace/mcps/mymcp",
            "command": "uv",
            "args": ["run", "--directory", "{source_dir}", "serve"],
            "auth": {"env_vars": ["K"]},
        }
        path = mc.generate_launcher("mymcp", mcp_data)
        content = path.read_text()
        assert "$SCRIPT_DIR/" in content
        assert "{source_dir}" not in content

    def test_multiple_env_vars(self, patch_mcp_config_paths, flux_root):
        mcp_data = {
            "command": "node",
            "args": [],
            "auth": {"env_vars": ["TOKEN", "BASE_URL", "EXTRA"]},
        }
        path = mc.generate_launcher("mymcp", mcp_data)
        content = path.read_text()
        for var in ["TOKEN", "BASE_URL", "EXTRA"]:
            assert var in content


# ---------------------------------------------------------------------------
# build_mcp_server_config
# ---------------------------------------------------------------------------

class TestBuildMcpServerConfig:
    def test_npm_no_auth_returns_command_and_args(self, patch_mcp_config_paths):
        mcp_data = {"type": "npm-package", "command": "npx", "args": ["-y", "pkg"]}
        result = mc.build_mcp_server_config("mymcp", mcp_data)
        assert result["command"] == "npx"
        assert "-y" in result["args"]

    def test_npm_with_auth_returns_launcher_path(self, patch_mcp_config_paths, flux_root):
        mcp_data = {
            "type": "npm-package",
            "command": "npx",
            "args": ["-y", "pkg"],
            "auth": {"env_vars": ["KEY"]},
        }
        result = mc.build_mcp_server_config("mymcp", mcp_data)
        assert result["command"].endswith("mymcp.sh")
        assert result["args"] == []

    def test_extra_args_appended_no_auth(self, patch_mcp_config_paths):
        mcp_data = {"command": "npx", "args": ["-y", "pkg"]}
        result = mc.build_mcp_server_config("mymcp", mcp_data, extra_args=["--port", "3000"])
        assert "--port" in result["args"]
        assert "3000" in result["args"]

    def test_source_dir_placeholder_resolved(self, patch_mcp_config_paths, flux_root):
        fake_src = flux_root / "marketplace" / "mcps" / "mymcp"
        fake_src.mkdir(parents=True)
        mcp_data = {
            "type": "git-submodule",
            "source_dir": "marketplace/mcps/mymcp",
            "command": "uv",
            "args": ["run", "--directory", "{source_dir}", "serve"],
        }
        result = mc.build_mcp_server_config("mymcp", mcp_data)
        assert "{source_dir}" not in result.get("args", [])
        assert str(flux_root / "marketplace" / "mcps" / "mymcp") in result.get("args", [])

    def test_env_key_preserved(self, patch_mcp_config_paths):
        mcp_data = {"command": "node", "args": [], "env": {"FOO": "bar"}}
        result = mc.build_mcp_server_config("mymcp", mcp_data)
        assert result.get("env") == {"FOO": "bar"}


# ---------------------------------------------------------------------------
# enrich_with_marketplace
# ---------------------------------------------------------------------------

class TestEnrichWithMarketplace:
    def test_merges_missing_auth_key(self):
        servers = {"mymcp": {"command": "npx", "args": []}}
        registry = {"mymcp": {"auth": {"type": "keychain", "env_vars": ["K"]}}}
        result = mc.enrich_with_marketplace(servers, registry)
        assert "auth" in result["mymcp"]

    def test_does_not_overwrite_existing_key(self):
        servers = {"mymcp": {"command": "npx", "args": [], "auth": {"type": "custom"}}}
        registry = {"mymcp": {"auth": {"type": "keychain"}}}
        result = mc.enrich_with_marketplace(servers, registry)
        assert result["mymcp"]["auth"]["type"] == "custom"

    def test_unknown_mcp_passed_through(self):
        servers = {"unknown": {"command": "foo", "args": []}}
        result = mc.enrich_with_marketplace(servers, {})
        assert result["unknown"]["command"] == "foo"

    def test_empty_inputs(self):
        assert mc.enrich_with_marketplace({}, {}) == {}

    def test_multiple_servers(self):
        servers = {
            "a": {"command": "cmd-a"},
            "b": {"command": "cmd-b"},
        }
        registry = {
            "a": {"type": "npm-package"},
            "b": {"type": "git-submodule"},
        }
        result = mc.enrich_with_marketplace(servers, registry)
        assert result["a"]["type"] == "npm-package"
        assert result["b"]["type"] == "git-submodule"
