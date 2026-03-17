"""Unit tests for flux_cli.lib.sandbox — extended sandbox lifecycle.

Covers: sandbox creation, scoped mcp.json, run-meta, agent execution,
run listing, run cleanup, and manifest loading.
"""

from __future__ import annotations

import json
import re
from unittest.mock import MagicMock

import pytest

from flux_cli.lib.sandbox import (
    clean_runs,
    create_sandbox,
    generate_run_id,
    list_runs,
    load_run_manifest,
    run_agent,
    update_run_meta,
    write_run_meta,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sandbox_home(tmp_path, monkeypatch):
    """Point flux_home / sandbox_dir to a temp directory."""
    monkeypatch.setattr("flux_cli.lib.paths._resolve_flux_home", lambda: tmp_path)
    (tmp_path / "sandbox").mkdir(exist_ok=True)
    return tmp_path


@pytest.fixture()
def simple_registry():
    """A minimal registry with one no-auth npm MCP."""
    return {
        "version": "1.0.0",
        "mcp_definitions": {
            "memory": {
                "type": "npm-package",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-memory"],
            },
        },
        "skill_definitions": {},
    }


# ---------------------------------------------------------------------------
# W3B.2: Sandbox creation
# ---------------------------------------------------------------------------


class TestSandboxCreatesDirectory:
    def test_sandbox_creates_directory(self, sandbox_home, simple_registry):
        path = create_sandbox(
            "20260316-abcd", ["memory"], registry=simple_registry, skip_preflight=True
        )
        assert path.is_dir()
        assert (path / "workspace").is_dir()
        assert path.name == "20260316-abcd"

    def test_sandbox_path_under_flux_sandbox(self, sandbox_home, simple_registry):
        path = create_sandbox(
            "20260316-1234", ["memory"], registry=simple_registry, skip_preflight=True
        )
        assert path.parent == sandbox_home / "sandbox"


class TestSandboxScopedMcpJson:
    def test_sandbox_scoped_mcp_json(self, sandbox_home, simple_registry):
        path = create_sandbox(
            "20260316-abcd", ["memory"], registry=simple_registry, skip_preflight=True
        )
        mcp_json = json.loads((path / ".mcp.json").read_text())
        assert "mcpServers" in mcp_json
        assert "memory" in mcp_json["mcpServers"]
        server = mcp_json["mcpServers"]["memory"]
        assert server.get("command") or server.get("args") is not None

    def test_sandbox_empty_mcps(self, sandbox_home, simple_registry):
        path = create_sandbox(
            "20260316-abcd", [], registry=simple_registry, skip_preflight=True
        )
        mcp_json = json.loads((path / ".mcp.json").read_text())
        assert mcp_json["mcpServers"] == {}


class TestSandboxRunMeta:
    def test_sandbox_run_meta(self, sandbox_home, simple_registry):
        path = create_sandbox(
            "20260316-abcd", ["memory"], registry=simple_registry, skip_preflight=True
        )
        meta = write_run_meta(path, "20260316-abcd", "do stuff", ["memory"])
        assert meta["id"] == "20260316-abcd"
        assert meta["task"] == "do stuff"
        assert meta["mcps"] == ["memory"]
        assert meta["status"] == "running"
        assert "started_at" in meta

        stored = json.loads((path / "run-meta.json").read_text())
        assert stored["id"] == "20260316-abcd"

    def test_update_meta_merges(self, sandbox_home, simple_registry):
        path = create_sandbox(
            "20260316-abcd", [], registry=simple_registry, skip_preflight=True
        )
        write_run_meta(path, "20260316-abcd", "task", [])
        update_run_meta(path, status="done", exit_code=0)
        stored = json.loads((path / "run-meta.json").read_text())
        assert stored["status"] == "done"
        assert stored["exit_code"] == 0
        assert stored["task"] == "task"  # original preserved


class TestSandboxRunIdFormat:
    def test_sandbox_run_id_format(self):
        run_id = generate_run_id()
        assert re.match(r"^\d{8}-[0-9a-f]{4}$", run_id)

    def test_run_id_uniqueness(self):
        ids = {generate_run_id() for _ in range(50)}
        assert len(ids) >= 40


# ---------------------------------------------------------------------------
# W3B.3: Agent execution
# ---------------------------------------------------------------------------


class TestRunInvokesClaude:
    def test_run_invokes_claude(self, sandbox_home, simple_registry, mocker):
        """run_agent calls claude with correct args (mocked)."""
        path = create_sandbox(
            "20260316-abcd", ["memory"], registry=simple_registry, skip_preflight=True
        )
        write_run_meta(path, "20260316-abcd", "test task", ["memory"])

        mocker.patch("flux_cli.lib.sandbox.shutil.which", return_value="/usr/local/bin/claude")
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate.return_value = ("", "")
        mock_popen = mocker.patch("flux_cli.lib.sandbox.subprocess.Popen", return_value=mock_proc)

        exit_code = run_agent(path, "test task")

        assert exit_code == 0
        mock_popen.assert_called_once()
        call_args = mock_popen.call_args
        cmd = call_args[0][0]
        assert cmd[0] == "/usr/local/bin/claude"
        assert "--print" in cmd
        assert "test task" in cmd
        assert "--mcp-config" in cmd


def _mock_popen(mocker, returncode=0):
    """Helper to mock subprocess.Popen for run_agent tests."""
    mock_proc = MagicMock()
    mock_proc.returncode = returncode
    mock_proc.communicate.return_value = ("", "")
    mock_proc.pid = 12345
    mocker.patch("flux_cli.lib.sandbox.shutil.which", return_value="/usr/local/bin/claude")
    mocker.patch("flux_cli.lib.sandbox.subprocess.Popen", return_value=mock_proc)
    return mock_proc


class TestRunCapturesExitCode:
    def test_run_captures_exit_code(self, sandbox_home, simple_registry, mocker):
        path = create_sandbox(
            "20260316-abcd", [], registry=simple_registry, skip_preflight=True
        )
        write_run_meta(path, "20260316-abcd", "fail task", [])
        _mock_popen(mocker, returncode=42)

        exit_code = run_agent(path, "fail task")
        assert exit_code == 42

    def test_run_exit_zero_on_success(self, sandbox_home, simple_registry, mocker):
        path = create_sandbox(
            "20260316-abcd", [], registry=simple_registry, skip_preflight=True
        )
        write_run_meta(path, "20260316-abcd", "ok task", [])
        _mock_popen(mocker, returncode=0)

        assert run_agent(path, "ok task") == 0


class TestRunUpdatesMeta:
    def test_run_updates_meta(self, sandbox_home, simple_registry, mocker):
        path = create_sandbox(
            "20260316-abcd", [], registry=simple_registry, skip_preflight=True
        )
        write_run_meta(path, "20260316-abcd", "task", [])
        _mock_popen(mocker, returncode=0)

        run_agent(path, "task")

        meta = json.loads((path / "run-meta.json").read_text())
        assert meta["status"] == "done"
        assert meta["exit_code"] == 0
        assert "ended_at" in meta
        assert "duration_seconds" in meta

    def test_run_updates_meta_on_failure(self, sandbox_home, simple_registry, mocker):
        path = create_sandbox(
            "20260316-abcd", [], registry=simple_registry, skip_preflight=True
        )
        write_run_meta(path, "20260316-abcd", "task", [])
        _mock_popen(mocker, returncode=1)

        run_agent(path, "task")

        meta = json.loads((path / "run-meta.json").read_text())
        assert meta["status"] == "failed"
        assert meta["exit_code"] == 1


class TestRunTimeoutKillsProcess:
    def test_run_timeout_kills_process(self, sandbox_home, simple_registry, mocker):
        import subprocess as sp

        path = create_sandbox(
            "20260316-abcd", [], registry=simple_registry, skip_preflight=True
        )
        write_run_meta(path, "20260316-abcd", "slow task", [])

        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.communicate.side_effect = sp.TimeoutExpired(cmd=["claude"], timeout=5)
        mock_proc.wait.return_value = None
        mocker.patch("flux_cli.lib.sandbox.shutil.which", return_value="/usr/local/bin/claude")
        mocker.patch("flux_cli.lib.sandbox.subprocess.Popen", return_value=mock_proc)
        mocker.patch("os.getpgid", return_value=12345)
        mocker.patch("os.killpg")

        exit_code = run_agent(path, "slow task", timeout=5)
        assert exit_code == 124

        meta = json.loads((path / "run-meta.json").read_text())
        assert meta["status"] == "timeout"
        assert meta["exit_code"] == 124


# ---------------------------------------------------------------------------
# W3B.4: flux run list
# ---------------------------------------------------------------------------


class TestRunListShowsRecent:
    def test_run_list_shows_recent(self, sandbox_home):
        base = sandbox_home / "sandbox"
        for i, run_id in enumerate(["20260315-0001", "20260316-0002"]):
            d = base / run_id
            d.mkdir(parents=True)
            meta = {
                "id": run_id,
                "task": f"task-{i}",
                "status": "done",
                "started_at": f"2026-03-1{5 + i}T10:00:00",
            }
            (d / "run-meta.json").write_text(json.dumps(meta))

        runs = list_runs()
        assert len(runs) == 2
        # Newest first
        assert runs[0]["id"] == "20260316-0002"
        assert runs[1]["id"] == "20260315-0001"

    def test_run_list_includes_task_and_status(self, sandbox_home):
        d = sandbox_home / "sandbox" / "20260316-abcd"
        d.mkdir(parents=True)
        meta = {
            "id": "20260316-abcd",
            "task": "Build a widget",
            "status": "done",
            "started_at": "2026-03-16T10:00:00",
            "duration_seconds": 42.5,
        }
        (d / "run-meta.json").write_text(json.dumps(meta))

        runs = list_runs()
        assert len(runs) == 1
        assert runs[0]["task"] == "Build a widget"
        assert runs[0]["status"] == "done"
        assert runs[0]["duration_seconds"] == 42.5


class TestRunListEmpty:
    def test_run_list_empty(self, sandbox_home):
        runs = list_runs()
        assert runs == []

    def test_run_list_empty_no_sandbox_dir(self, tmp_path, monkeypatch):
        """list_runs returns empty when sandbox dir doesn't exist."""
        monkeypatch.setattr("flux_cli.lib.paths._resolve_flux_home", lambda: tmp_path / "nonexistent")
        runs = list_runs()
        assert runs == []


# ---------------------------------------------------------------------------
# W3B.5: flux run clean
# ---------------------------------------------------------------------------


class TestRunCleanRemovesCompleted:
    def test_run_clean_removes_completed(self, sandbox_home):
        base = sandbox_home / "sandbox"
        # Create 7 completed runs
        for i in range(7):
            d = base / f"20260310-{i:04x}"
            d.mkdir(parents=True)
            meta = {"id": d.name, "status": "done", "started_at": f"2026-03-10T{i:02d}:00:00"}
            (d / "run-meta.json").write_text(json.dumps(meta))

        # Create 1 running run
        running = base / "20260316-run0"
        running.mkdir(parents=True)
        (running / "run-meta.json").write_text(
            json.dumps({"id": "20260316-run0", "status": "running"})
        )

        removed = clean_runs(keep=5)
        # Should remove 2 oldest completed (7 - 5 = 2), keep running
        assert removed == 2
        assert running.exists()
        # 5 completed remain + 1 running
        remaining = list(base.iterdir())
        assert len(remaining) == 6


class TestRunCleanForce:
    def test_run_clean_force(self, sandbox_home):
        base = sandbox_home / "sandbox"
        for name in ["run-a", "run-b", "run-c"]:
            (base / name).mkdir(parents=True)

        removed = clean_runs(force=True)
        assert removed == 3
        assert list(base.iterdir()) == []

    def test_run_clean_force_removes_running(self, sandbox_home):
        base = sandbox_home / "sandbox"
        d = base / "running-run"
        d.mkdir(parents=True)
        (d / "run-meta.json").write_text(json.dumps({"status": "running"}))

        removed = clean_runs(force=True)
        assert removed == 1


class TestRunCleanKeepsRecent:
    def test_run_clean_keeps_recent(self, sandbox_home):
        base = sandbox_home / "sandbox"
        # Create exactly 5 completed
        for i in range(5):
            d = base / f"20260310-{i:04x}"
            d.mkdir(parents=True)
            (d / "run-meta.json").write_text(
                json.dumps({"id": d.name, "status": "done"})
            )

        removed = clean_runs(keep=5)
        assert removed == 0  # nothing to remove, exactly at limit

    def test_run_clean_empty_sandbox(self, sandbox_home):
        removed = clean_runs()
        assert removed == 0


# ---------------------------------------------------------------------------
# W3B.6: Run manifest
# ---------------------------------------------------------------------------


class TestRunFromManifest:
    def test_run_from_manifest(self, tmp_path):
        manifest = {
            "name": "my-run",
            "task": "Analyze the codebase",
            "mcps": ["memory"],
            "skills": [],
            "timeout": 120,
        }
        path = tmp_path / "run.json"
        path.write_text(json.dumps(manifest))

        loaded = load_run_manifest(path)
        assert loaded["task"] == "Analyze the codebase"
        assert loaded["mcps"] == ["memory"]
        assert loaded["timeout"] == 120

    def test_run_from_manifest_minimal(self, tmp_path):
        """Only 'task' is required."""
        path = tmp_path / "run.json"
        path.write_text(json.dumps({"task": "do it"}))

        loaded = load_run_manifest(path)
        assert loaded["task"] == "do it"


class TestRunInvalidManifestErrors:
    def test_run_invalid_manifest_errors_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="not found"):
            load_run_manifest(tmp_path / "nonexistent.json")

    def test_run_invalid_manifest_errors_bad_json(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("{ not valid json }")
        with pytest.raises(ValueError, match="Invalid JSON"):
            load_run_manifest(path)

    def test_run_invalid_manifest_errors_not_object(self, tmp_path):
        path = tmp_path / "array.json"
        path.write_text(json.dumps([1, 2, 3]))
        with pytest.raises(ValueError, match="JSON object"):
            load_run_manifest(path)

    def test_run_invalid_manifest_errors_missing_task(self, tmp_path):
        path = tmp_path / "no-task.json"
        path.write_text(json.dumps({"name": "test", "mcps": []}))
        with pytest.raises(ValueError, match="task"):
            load_run_manifest(path)
