"""Unit tests for lib/manifest.py"""
import json

import manifest as m
import pytest

# ---------------------------------------------------------------------------
# Legacy marketplace manifest tests
# ---------------------------------------------------------------------------


class TestLoadManifest:
    def test_returns_dict_with_expected_keys(self, patch_manifest_paths, flux_root):
        result = m.load_manifest()
        assert "mcp_definitions" in result
        assert "skill_definitions" in result

    def test_contains_fixture_mcps(self, patch_manifest_paths):
        result = m.load_manifest()
        assert "memory" in result["mcp_definitions"]
        assert "wikijs-mcp" in result["mcp_definitions"]

    def test_missing_file_exits(self, monkeypatch, tmp_path):
        monkeypatch.setattr(m, "MANIFEST_PATH", tmp_path / "nonexistent.json")
        with pytest.raises(SystemExit) as exc:
            m.load_manifest()
        assert exc.value.code == 1

    def test_invalid_json_raises(self, monkeypatch, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{ not valid json }")
        monkeypatch.setattr(m, "MANIFEST_PATH", bad)
        with pytest.raises(json.JSONDecodeError):
            m.load_manifest()


class TestSaveManifest:
    def test_roundtrip(self, patch_manifest_paths, flux_root, capsys):
        original = m.load_manifest()
        original["mcp_definitions"]["new-mcp"] = {"type": "npm-package", "command": "npx"}
        m.save_manifest(original)
        reloaded = m.load_manifest()
        assert "new-mcp" in reloaded["mcp_definitions"]

    def test_pretty_prints(self, patch_manifest_paths, flux_root):
        data = {"mcp_definitions": {}, "skill_definitions": {}}
        m.save_manifest(data)
        raw = (flux_root / "marketplace" / "marketplace.json").read_text()
        assert "  " in raw  # indent=2


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
        # File should now exist on disk
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
        # File should be written with no temp files left over
        assert reg_path.exists()
        contents = json.loads(reg_path.read_text())
        assert contents["mcp_definitions"]["test-mcp"]["type"] == "uvx-package"
        # No .tmp files should remain
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
