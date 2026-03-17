"""Unit tests for lib/sandbox.py"""

import json
import re

import pytest

import sandbox as sb

# ---------------------------------------------------------------------------
# generate_run_id
# ---------------------------------------------------------------------------

class TestGenerateRunId:
    def test_format_matches_pattern(self):
        run_id = sb.generate_run_id()
        assert re.match(r"^\d{8}-[0-9a-f]{4}$", run_id)

    def test_uniqueness(self):
        ids = {sb.generate_run_id() for _ in range(50)}
        # Very unlikely to have fewer than 40 unique IDs from 50 calls
        assert len(ids) >= 40


# ---------------------------------------------------------------------------
# create_sandbox
# ---------------------------------------------------------------------------

class TestCreateSandbox:
    def test_creates_sandbox_and_workspace_dirs(self, patch_sandbox_paths, flux_root, patch_mcp_config_paths, mocker):
        mocker.patch("mcp_config.build_mcp_server_config", return_value={"command": "npx", "args": []})
        path = sb.create_sandbox("20260315-abcd", ["memory"], {"mcp_definitions": {"memory": {}}})
        assert path.is_dir()
        assert (path / "workspace").is_dir()

    def test_writes_mcp_json(self, patch_sandbox_paths, flux_root, mocker):
        mocker.patch("mcp_config.build_mcp_server_config", return_value={"command": "npx", "args": []})
        path = sb.create_sandbox("20260315-abcd", ["memory"], {"mcp_definitions": {"memory": {}}})
        mcp_json = json.loads((path / ".mcp.json").read_text())
        assert "mcpServers" in mcp_json
        assert "memory" in mcp_json["mcpServers"]

    def test_empty_mcps_writes_empty_servers(self, patch_sandbox_paths, flux_root):
        path = sb.create_sandbox("20260315-abcd", [], {"mcp_definitions": {}})
        mcp_json = json.loads((path / ".mcp.json").read_text())
        assert mcp_json["mcpServers"] == {}

    def test_unknown_mcp_exits_and_cleans_up(self, patch_sandbox_paths, flux_root):
        with pytest.raises(SystemExit):
            sb.create_sandbox("20260315-abcd", ["nonexistent"], {"mcp_definitions": {}})
        # sandbox dir should be cleaned up
        assert not (flux_root / "sandbox" / "20260315-abcd").exists()


# ---------------------------------------------------------------------------
# write_run_meta / update_run_meta
# ---------------------------------------------------------------------------

class TestRunMeta:
    def test_write_creates_meta_file(self, patch_sandbox_paths, flux_root):
        sandbox_path = flux_root / "sandbox" / "run1"
        sandbox_path.mkdir(parents=True)
        sb.write_run_meta(sandbox_path, "run1", "do something", ["memory"])
        assert (sandbox_path / "run-meta.json").exists()

    def test_write_includes_all_fields(self, patch_sandbox_paths, flux_root):
        sandbox_path = flux_root / "sandbox" / "run1"
        sandbox_path.mkdir(parents=True)
        meta = sb.write_run_meta(sandbox_path, "run1", "my task", ["memory", "wikijs-mcp"], name="friendly-name")
        assert meta["id"] == "run1"
        assert meta["task"] == "my task"
        assert meta["mcps"] == ["memory", "wikijs-mcp"]
        assert meta["name"] == "friendly-name"
        assert meta["status"] == "running"
        assert "started_at" in meta

    def test_write_uses_run_id_as_default_name(self, patch_sandbox_paths, flux_root):
        sandbox_path = flux_root / "sandbox" / "run1"
        sandbox_path.mkdir(parents=True)
        meta = sb.write_run_meta(sandbox_path, "run1", "task", [])
        assert meta["name"] == "run1"

    def test_update_partial(self, patch_sandbox_paths, flux_root):
        sandbox_path = flux_root / "sandbox" / "run1"
        sandbox_path.mkdir(parents=True)
        sb.write_run_meta(sandbox_path, "run1", "task", [])
        sb.update_run_meta(sandbox_path, status="done", exit_code=0)
        meta = json.loads((sandbox_path / "run-meta.json").read_text())
        assert meta["status"] == "done"
        assert meta["exit_code"] == 0
        assert meta["task"] == "task"  # original field preserved

    def test_update_creates_file_if_missing(self, patch_sandbox_paths, flux_root):
        sandbox_path = flux_root / "sandbox" / "run1"
        sandbox_path.mkdir(parents=True)
        sb.update_run_meta(sandbox_path, status="done")
        meta = json.loads((sandbox_path / "run-meta.json").read_text())
        assert meta["status"] == "done"


# ---------------------------------------------------------------------------
# cleanup_sandbox
# ---------------------------------------------------------------------------

class TestCleanupSandbox:
    def test_removes_directory(self, flux_root):
        d = flux_root / "sandbox" / "toclean"
        d.mkdir(parents=True)
        sb.cleanup_sandbox(d)
        assert not d.exists()

    def test_noop_if_already_missing(self, flux_root):
        d = flux_root / "sandbox" / "missing"
        sb.cleanup_sandbox(d)  # should not raise


# ---------------------------------------------------------------------------
# list_runs
# ---------------------------------------------------------------------------

class TestListRuns:
    def test_empty_sandbox_returns_empty_list(self, patch_sandbox_paths, flux_root):
        assert sb.list_runs() == []

    def test_returns_metadata_dicts(self, patch_sandbox_paths, flux_root):
        for run_id in ["run1", "run2"]:
            d = flux_root / "sandbox" / run_id
            d.mkdir(parents=True)
            meta = {"id": run_id, "task": f"task-{run_id}", "status": "done"}
            (d / "run-meta.json").write_text(json.dumps(meta))
        runs = sb.list_runs()
        assert len(runs) == 2
        assert any(r["id"] == "run1" for r in runs)

    def test_skips_dirs_without_meta_json(self, patch_sandbox_paths, flux_root):
        d = flux_root / "sandbox" / "no-meta"
        d.mkdir(parents=True)
        assert sb.list_runs() == []

    def test_skips_corrupt_json(self, patch_sandbox_paths, flux_root):
        d = flux_root / "sandbox" / "corrupt"
        d.mkdir(parents=True)
        (d / "run-meta.json").write_text("{ not json }")
        assert sb.list_runs() == []

    def test_skips_non_directories(self, patch_sandbox_paths, flux_root):
        (flux_root / "sandbox" / "stray-file.txt").write_text("hello")
        assert sb.list_runs() == []


# ---------------------------------------------------------------------------
# clean_runs
# ---------------------------------------------------------------------------

class TestCleanRuns:
    def test_force_removes_all_sandbox_dirs(self, patch_sandbox_paths, flux_root):
        for name in ["a", "b", "c"]:
            (flux_root / "sandbox" / name).mkdir(parents=True)
        count = sb.clean_runs(force=True)
        assert count == 3
        assert list((flux_root / "sandbox").iterdir()) == []

    def test_preserves_claude_dir(self, patch_sandbox_paths, flux_root):
        (flux_root / "sandbox" / ".claude").mkdir(parents=True)
        (flux_root / "sandbox" / "sandbox1").mkdir()
        count = sb.clean_runs(force=True)
        assert count == 1
        assert (flux_root / "sandbox" / ".claude").exists()

    def test_empty_sandbox_returns_zero(self, patch_sandbox_paths, flux_root):
        assert sb.clean_runs(force=True) == 0

    def test_interactive_confirm_yes(self, patch_sandbox_paths, flux_root, mocker):
        (flux_root / "sandbox" / "sandbox1").mkdir()
        mocker.patch("builtins.input", return_value="y")
        count = sb.clean_runs(force=False)
        assert count == 1

    def test_interactive_abort_on_no(self, patch_sandbox_paths, flux_root, mocker):
        (flux_root / "sandbox" / "sandbox1").mkdir()
        mocker.patch("builtins.input", return_value="n")
        count = sb.clean_runs(force=False)
        assert count == -1
        assert (flux_root / "sandbox" / "sandbox1").exists()


# ---------------------------------------------------------------------------
# load_run_manifest
# ---------------------------------------------------------------------------

class TestLoadRunManifest:
    def test_loads_valid_file(self, tmp_path):
        data = {"name": "test", "task": "do it", "mcps": ["memory"]}
        f = tmp_path / "run.json"
        f.write_text(json.dumps(data))
        result = sb.load_run_manifest(str(f))
        assert result["name"] == "test"

    def test_missing_file_exits(self, tmp_path):
        with pytest.raises(SystemExit):
            sb.load_run_manifest(str(tmp_path / "nonexistent.json"))
