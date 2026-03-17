"""Unit tests for flux_cli.mcp_config — enrich_with_marketplace."""

import flux_cli.mcp_config as mc


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
