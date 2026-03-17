"""Unit tests for flux_cli.sandbox — sandbox lifecycle."""
import json
import re

import pytest

import flux_cli.sandbox as sb

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
    def test_creates_sandbox_and_workspace_dirs(self, patch_sandbox_paths, flux_root):
        registry = {
            "version": "1.0.0",
            "mcp_definitions": {"memory": {"type": "npm-package", "command": "npx", "args": ["-y", "pkg"]}},
            "skill_definitions": {},
        }
        path = sb.create_sandbox("20260315-abcd", ["memory"], registry=registry, skip_preflight=True)
        assert path.is_dir()
        assert (path / "workspace").is_dir()

    def test_writes_mcp_json(self, patch_sandbox_paths, flux_root):
        registry = {
            "version": "1.0.0",
            "mcp_definitions": {"memory": {"type": "npm-package", "command": "npx", "args": ["-y", "pkg"]}},
            "skill_definitions": {},
        }
        path = sb.create_sandbox("20260315-abcd", ["memory"], registry=registry, skip_preflight=True)
        mcp_json = json.loads((path / ".mcp.json").read_text())
        assert "mcpServers" in mcp_json
        assert "memory" in mcp_json["mcpServers"]

    def test_empty_mcps_writes_empty_servers(self, patch_sandbox_paths, flux_root):
        registry = {"version": "1.0.0", "mcp_definitions": {}, "skill_definitions": {}}
        path = sb.create_sandbox("20260315-abcd", [], registry=registry, skip_preflight=True)
        mcp_json = json.loads((path / ".mcp.json").read_text())
        assert mcp_json["mcpServers"] == {}

    def test_unknown_mcp_skipped_silently(self, patch_sandbox_paths, flux_root):
        registry = {"version": "1.0.0", "mcp_definitions": {}, "skill_definitions": {}}
        path = sb.create_sandbox("20260315-abcd", ["nonexistent"], registry=registry, skip_preflight=True)
        mcp_json = json.loads((path / ".mcp.json").read_text())
        assert mcp_json["mcpServers"] == {}


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

    def test_force_removes_all_dirs(self, patch_sandbox_paths, flux_root):
        (flux_root / "sandbox" / "sandbox1").mkdir()
        (flux_root / "sandbox" / "sandbox2").mkdir()
        count = sb.clean_runs(force=True)
        assert count == 2

    def test_empty_sandbox_returns_zero(self, patch_sandbox_paths, flux_root):
        assert sb.clean_runs(force=True) == 0

    def test_keep_recent_preserves_latest(self, patch_sandbox_paths, flux_root):
        """Non-force mode keeps the most recent 5 completed runs."""
        for i in range(7):
            d = flux_root / "sandbox" / f"run{i:03d}"
            d.mkdir(parents=True)
            meta = {"status": "done"}
            (d / "run-meta.json").write_text(json.dumps(meta))
        count = sb.clean_runs(force=False, keep=5)
        assert count == 2  # 7 - 5 kept = 2 removed

    def test_no_force_keeps_running(self, patch_sandbox_paths, flux_root):
        d = flux_root / "sandbox" / "sandbox1"
        d.mkdir(parents=True)
        (d / "run-meta.json").write_text(json.dumps({"status": "running"}))
        count = sb.clean_runs(force=False, keep=0)
        assert count == 0
        assert d.exists()


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

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises((SystemExit, FileNotFoundError)):
            sb.load_run_manifest(str(tmp_path / "nonexistent.json"))
