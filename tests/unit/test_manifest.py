"""Unit tests for flux_cli.manifest — registry and flux.json I/O."""
import json

import flux_cli.manifest as m

# ---------------------------------------------------------------------------
# flux.json tests
# ---------------------------------------------------------------------------


class TestLoadFluxJson:
    def test_returns_none_when_missing(self, tmp_path):
        assert m.load_flux_json(tmp_path) is None

    def test_returns_dict_when_present(self, tmp_path):
        data = {"name": "test", "mcps": ["memory"]}
        (tmp_path / "flux.json").write_text(json.dumps(data))
        result = m.load_flux_json(tmp_path)
        assert result["name"] == "test"
        assert result["mcps"] == ["memory"]


class TestSaveFluxJson:
    def test_creates_file(self, tmp_path):
        m.save_flux_json(tmp_path, {"name": "proj", "mcps": []})
        assert (tmp_path / "flux.json").exists()

    def test_overwrites_existing(self, tmp_path):
        (tmp_path / "flux.json").write_text(json.dumps({"name": "old"}))
        m.save_flux_json(tmp_path, {"name": "new"})
        result = json.loads((tmp_path / "flux.json").read_text())
        assert result["name"] == "new"

    def test_roundtrip_with_load(self, tmp_path):
        data = {"name": "x", "version": "0.1.0", "mcps": ["a", "b"], "skills": []}
        m.save_flux_json(tmp_path, data)
        assert m.load_flux_json(tmp_path) == data


# ---------------------------------------------------------------------------
# v1 Registry tests
# ---------------------------------------------------------------------------


class TestLoadRegistry:
    def test_load_registry_valid(self, tmp_path):
        reg_path = tmp_path / "registry.json"
        data = {
            "version": "1.0.0",
            "mcp_definitions": {"my-mcp": {"type": "npm-package"}},
            "skill_definitions": {},
        }
        reg_path.write_text(json.dumps(data))
        result = m.load_registry(path=reg_path)
        assert result["version"] == "1.0.0"
        assert "my-mcp" in result["mcp_definitions"]

    def test_load_registry_missing_creates_empty(self, tmp_path):
        reg_path = tmp_path / "registry.json"
        assert not reg_path.exists()
        result = m.load_registry(path=reg_path)
        assert result["version"] == "1.0.0"
        assert result["mcp_definitions"] == {}
        assert result["skill_definitions"] == {}
        assert reg_path.exists()

    def test_load_registry_creates_parent_dirs(self, tmp_path):
        reg_path = tmp_path / "deep" / "nested" / "registry.json"
        result = m.load_registry(path=reg_path)
        assert result["version"] == "1.0.0"
        assert reg_path.exists()


class TestSaveRegistry:
    def test_save_registry_atomic(self, tmp_path):
        reg_path = tmp_path / "registry.json"
        data = {
            "version": "1.0.0",
            "mcp_definitions": {"test-mcp": {"type": "uvx-package"}},
            "skill_definitions": {},
        }
        m.save_registry(data, path=reg_path)
        assert reg_path.exists()
        contents = json.loads(reg_path.read_text())
        assert contents["mcp_definitions"]["test-mcp"]["type"] == "uvx-package"
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert tmp_files == []

    def test_registry_roundtrip(self, tmp_path):
        reg_path = tmp_path / "registry.json"
        data = {
            "version": "1.0.0",
            "mcp_definitions": {
                "alpha-mcp": {"type": "npm-package", "command": "npx", "args": ["-y", "alpha"]},
                "beta-mcp": {"type": "uvx-package", "command": "uvx", "args": ["beta"]},
            },
            "skill_definitions": {
                "my-skill": {"type": "github", "source": "user/repo"},
            },
        }
        m.save_registry(data, path=reg_path)
        reloaded = m.load_registry(path=reg_path)
        assert reloaded == data

    def test_save_registry_overwrites(self, tmp_path):
        reg_path = tmp_path / "registry.json"
        m.save_registry({"version": "1.0.0", "mcp_definitions": {"old": {}}, "skill_definitions": {}}, path=reg_path)
        m.save_registry({"version": "1.0.0", "mcp_definitions": {"new": {}}, "skill_definitions": {}}, path=reg_path)
        result = m.load_registry(path=reg_path)
        assert "new" in result["mcp_definitions"]
        assert "old" not in result["mcp_definitions"]
