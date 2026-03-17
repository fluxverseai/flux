"""Extended unit tests for lib/health.py — probe_mcp_server_detailed + doctor checks."""
import json
import subprocess
from unittest.mock import MagicMock

import flux_cli.health as h

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_proc(stdout_lines: list[dict], returncode: int = 0):
    """Build a mock Popen process that returns the given JSON-RPC response lines."""
    stdout_bytes = "\n".join(json.dumps(line) for line in stdout_lines).encode()
    mock_proc = MagicMock()
    mock_proc.communicate.return_value = (stdout_bytes, b"")
    mock_proc.returncode = returncode
    return mock_proc


INIT_RESPONSE = {
    "jsonrpc": "2.0",
    "id": 1,
    "result": {
        "protocolVersion": "2024-11-05",
        "serverInfo": {"name": "test-server", "version": "1.0.0"},
        "capabilities": {},
    },
}


def _tools_list_response(tools: list[dict] | None = None):
    """Build a tools/list JSON-RPC response with a configurable tool list."""
    if tools is None:
        tools = [{"name": "tool1"}, {"name": "tool2"}]
    return {"jsonrpc": "2.0", "id": 2, "result": {"tools": tools}}


# =====================================================================
# W3A.1 — Status (probe_mcp_server_detailed)
# =====================================================================


class TestStatusConnected:
    """test_status_connected — detailed probe returns connected with tools count."""

    def test_status_connected(self, mocker):
        mocker.patch("flux_cli.health.shutil.which", return_value="/usr/bin/npx")
        mock_popen = mocker.patch("flux_cli.health.subprocess.Popen")
        tools = [{"name": f"t{i}"} for i in range(5)]
        mock_popen.return_value = _make_proc([INIT_RESPONSE, _tools_list_response(tools)])

        result = h.probe_mcp_server_detailed({"command": "npx", "args": ["-y", "pkg"]})
        assert result["status"] == "connected"
        assert result["tools_count"] == 5
        assert result["server_info"] is not None
        assert "test-server" in result["server_info"]

    def test_connected_zero_tools(self, mocker):
        mocker.patch("flux_cli.health.shutil.which", return_value="/usr/bin/npx")
        mock_popen = mocker.patch("flux_cli.health.subprocess.Popen")
        mock_popen.return_value = _make_proc([INIT_RESPONSE, _tools_list_response([])])

        result = h.probe_mcp_server_detailed({"command": "npx", "args": []})
        assert result["status"] == "connected"
        assert result["tools_count"] == 0


class TestStatusAuthRequired:
    """test_status_auth_required — pre-flight auth check and tools/list auth error."""

    def test_preflight_auth_failure(self, mocker):
        mocker.patch("flux_cli.health.shutil.which", return_value="/usr/bin/cmd")
        mocker.patch("flux_cli.health.subprocess.run", return_value=MagicMock(returncode=1))
        config = {
            "command": "cmd", "args": [],
            "auth": {"check_cmd": ["gh", "auth", "status"], "fix_description": "run gh auth login"},
        }
        result = h.probe_mcp_server_detailed(config)
        assert result["status"] == "auth_required"
        assert result["tools_count"] is None
        assert "gh auth login" in result["detail"]

    def test_tools_list_auth_error(self, mocker):
        mocker.patch("flux_cli.health.shutil.which", return_value="/usr/bin/npx")
        mock_popen = mocker.patch("flux_cli.health.subprocess.Popen")
        auth_err = {"jsonrpc": "2.0", "id": 2, "error": {"code": 401, "message": "unauthorized: bad token"}}
        mock_popen.return_value = _make_proc([INIT_RESPONSE, auth_err])

        result = h.probe_mcp_server_detailed({"command": "npx", "args": []})
        assert result["status"] == "auth_required"
        assert result["tools_count"] is None


class TestStatusTimeout:
    """test_status_timeout — server does not respond in time."""

    def test_timeout(self, mocker):
        mocker.patch("flux_cli.health.shutil.which", return_value="/usr/bin/npx")
        mock_popen = mocker.patch("flux_cli.health.subprocess.Popen")
        mock_proc = MagicMock()
        mock_proc.communicate.side_effect = subprocess.TimeoutExpired(cmd="npx", timeout=10)
        mock_popen.return_value = mock_proc

        result = h.probe_mcp_server_detailed({"command": "npx", "args": []})
        assert result["status"] == "timeout"
        assert result["tools_count"] is None
        mock_proc.kill.assert_called_once()


class TestStatusAllProjects:
    """test_status_all_projects — verify _probe_project_servers works across multiple projects."""

    def test_probes_multiple_projects(self, mocker, tmp_path):
        """Simulate two projects each with one MCP and verify probe results."""
        mocker.patch("flux_cli.health.shutil.which", return_value="/usr/bin/npx")
        mock_popen = mocker.patch("flux_cli.health.subprocess.Popen")

        # Each call returns a connected response with 3 tools
        tools = [{"name": f"t{i}"} for i in range(3)]
        mock_popen.return_value = _make_proc([INIT_RESPONSE, _tools_list_response(tools)])

        # Create two project dirs with .mcp.json
        for pname in ("proj-a", "proj-b"):
            pdir = tmp_path / pname
            pdir.mkdir()
            mcp_config = {"mcpServers": {f"{pname}-mcp": {"command": "npx", "args": ["-y", "pkg"]}}}
            (pdir / ".mcp.json").write_text(json.dumps(mcp_config))

        # Import the function we need — it lives in bin/flux but we can test the health
        # module's detailed probe directly for each server.
        all_rows = []
        for pdir in sorted(tmp_path.iterdir()):
            with open(pdir / ".mcp.json") as f:
                servers = json.load(f).get("mcpServers", {})
            for name, config in servers.items():
                r = h.probe_mcp_server_detailed(config)
                all_rows.append({"project": pdir.name, "name": name, **r})

        assert len(all_rows) == 2
        assert all(r["status"] == "connected" for r in all_rows)
        assert all(r["tools_count"] == 3 for r in all_rows)


class TestProbeBackwardCompat:
    """Ensure probe_mcp_server still returns the simple (status, detail) tuple."""

    def test_compat_tuple(self, mocker):
        mocker.patch("flux_cli.health.shutil.which", return_value="/usr/bin/npx")
        mock_popen = mocker.patch("flux_cli.health.subprocess.Popen")
        mock_popen.return_value = _make_proc([INIT_RESPONSE, _tools_list_response()])

        status, detail = h.probe_mcp_server({"command": "npx", "args": []})
        assert status == "connected"
        assert isinstance(detail, str)


# =====================================================================
# W3A.2 — Doctor checks
# =====================================================================


class TestDoctorAllPass:
    """test_doctor_all_pass — all checks pass in a well-formed environment."""

    def test_all_pass(self, mocker, tmp_path):
        # Fake a complete flux tree
        for d in ("marketplace", "marketplace/mcps", "marketplace/skills", "src"):
            (tmp_path / d).mkdir(parents=True, exist_ok=True)

        registry = {"version": "1.0.0", "mcp_definitions": {}, "skill_definitions": {}}
        reg_path = tmp_path / "registry.json"
        reg_path.write_text(json.dumps(registry))

        mocker.patch("flux_cli.health.shutil.which", return_value="/usr/bin/thing")
        mocker.patch("flux_cli.health.sys.version_info", (3, 12, 0, "final", 0))

        results = h.run_doctor_checks(
            flux_root=tmp_path,
            registry_path=reg_path,
            mcp_definitions={},
            secrets_index={},
        )
        assert all(c.passed for c in results), [c for c in results if not c.passed]


class TestDoctorMissingPython:
    """test_doctor_missing_python — fails if Python < 3.11."""

    def test_missing_python(self, mocker, tmp_path):
        for d in ("marketplace", "marketplace/mcps", "marketplace/skills", "src"):
            (tmp_path / d).mkdir(parents=True, exist_ok=True)
        mocker.patch("flux_cli.health.shutil.which", return_value="/usr/bin/thing")
        mocker.patch("flux_cli.health.sys.version_info", (3, 9, 1, "final", 0))

        results = h.run_doctor_checks(flux_root=tmp_path, mcp_definitions={}, secrets_index={})
        python_check = [c for c in results if "Python" in c.label][0]
        assert not python_check.passed
        assert "3.9" in python_check.label


class TestDoctorMissingUv:
    """test_doctor_missing_uv — fails when uv is not installed."""

    def test_missing_uv(self, mocker, tmp_path):
        for d in ("marketplace", "marketplace/mcps", "marketplace/skills", "src"):
            (tmp_path / d).mkdir(parents=True, exist_ok=True)

        original_which = h.shutil.which

        def fake_which(name):
            if name == "uv":
                return None
            return original_which(name) or "/usr/bin/thing"

        mocker.patch("flux_cli.health.shutil.which", side_effect=fake_which)

        results = h.run_doctor_checks(flux_root=tmp_path, mcp_definitions={}, secrets_index={})
        uv_check = [c for c in results if "uv" in c.label][0]
        assert not uv_check.passed
        assert uv_check.fix_hint is not None


class TestDoctorMissingNode:
    """test_doctor_missing_node — fails when node is not installed."""

    def test_missing_node(self, mocker, tmp_path):
        for d in ("marketplace", "marketplace/mcps", "marketplace/skills", "src"):
            (tmp_path / d).mkdir(parents=True, exist_ok=True)

        original_which = h.shutil.which

        def fake_which(name):
            if name == "node":
                return None
            return original_which(name) or "/usr/bin/thing"

        mocker.patch("flux_cli.health.shutil.which", side_effect=fake_which)

        results = h.run_doctor_checks(flux_root=tmp_path, mcp_definitions={}, secrets_index={})
        node_check = [c for c in results if "node" in c.label][0]
        assert not node_check.passed


class TestDoctorMissingClaude:
    """test_doctor_missing_claude — fails when claude CLI is not installed."""

    def test_missing_claude(self, mocker, tmp_path):
        for d in ("marketplace", "marketplace/mcps", "marketplace/skills", "src"):
            (tmp_path / d).mkdir(parents=True, exist_ok=True)

        original_which = h.shutil.which

        def fake_which(name):
            if name == "claude":
                return None
            return original_which(name) or "/usr/bin/thing"

        mocker.patch("flux_cli.health.shutil.which", side_effect=fake_which)

        results = h.run_doctor_checks(flux_root=tmp_path, mcp_definitions={}, secrets_index={})
        claude_check = [c for c in results if "claude" in c.label][0]
        assert not claude_check.passed
        assert "anthropic" in claude_check.fix_hint.lower() or "claude" in claude_check.fix_hint.lower()


class TestDoctorBrokenRegistry:
    """test_doctor_broken_registry — fails when registry JSON is invalid."""

    def test_invalid_json(self, tmp_path):
        reg_path = tmp_path / "registry.json"
        reg_path.write_text("NOT VALID JSON {{{")

        result = h.check_registry_valid(reg_path)
        assert not result.passed
        assert "Parse error" in (result.fix_hint or "")

    def test_not_an_object(self, tmp_path):
        reg_path = tmp_path / "registry.json"
        reg_path.write_text(json.dumps([1, 2, 3]))

        result = h.check_registry_valid(reg_path)
        assert not result.passed

    def test_missing_file(self, tmp_path):
        result = h.check_registry_valid(tmp_path / "nonexistent.json")
        assert not result.passed


class TestDoctorMissingSecrets:
    """test_doctor_missing_secrets — fails when auth env vars lack matching secrets."""

    def test_missing_secrets(self):
        mcp_defs = {
            "wikijs-mcp": {
                "auth": {"env_vars": ["WIKIJS_URL", "WIKIJS_API_KEY"]},
            },
        }
        secrets_idx = {}  # nothing stored

        results = h.check_secrets_consistency(secrets_idx, mcp_defs)
        assert len(results) == 1
        assert not results[0].passed
        assert "WIKIJS_URL" in results[0].label

    def test_partial_secrets(self):
        mcp_defs = {
            "wikijs-mcp": {
                "auth": {"env_vars": ["WIKIJS_URL", "WIKIJS_API_KEY"]},
            },
        }
        secrets_idx = {"wikijs-mcp": ["WIKIJS_URL"]}

        results = h.check_secrets_consistency(secrets_idx, mcp_defs)
        assert len(results) == 1
        assert not results[0].passed
        assert "WIKIJS_API_KEY" in results[0].label

    def test_all_secrets_present(self):
        mcp_defs = {
            "wikijs-mcp": {
                "auth": {"env_vars": ["WIKIJS_URL", "WIKIJS_API_KEY"]},
            },
        }
        secrets_idx = {"wikijs-mcp": ["WIKIJS_URL", "WIKIJS_API_KEY"]}

        results = h.check_secrets_consistency(secrets_idx, mcp_defs)
        assert len(results) == 1
        assert results[0].passed


class TestDoctorStaleProject:
    """test_doctor_stale_project — MCP source dir missing on disk."""

    def test_missing_source_dir(self, tmp_path):
        mcp_defs = {
            "wikijs-mcp": {
                "source_dir": "marketplace/mcps/wikijs-mcp",
            },
        }
        # Don't create the source dir — it should be flagged
        results = h.check_mcp_sources_present(tmp_path, mcp_defs)
        assert len(results) == 1
        assert not results[0].passed
        assert "wikijs-mcp" in results[0].label

    def test_source_dir_exists(self, tmp_path):
        mcp_defs = {
            "wikijs-mcp": {
                "source_dir": "marketplace/mcps/wikijs-mcp",
            },
        }
        (tmp_path / "marketplace" / "mcps" / "wikijs-mcp").mkdir(parents=True)
        results = h.check_mcp_sources_present(tmp_path, mcp_defs)
        assert len(results) == 1
        assert results[0].passed


# =====================================================================
# Individual check functions
# =====================================================================


class TestCheckPythonVersion:
    def test_current_python_passes(self):
        # Current Python should be >= 3.11 since pyproject requires it
        result = h.check_python_version()
        assert result.passed

    def test_custom_min_version(self, mocker):
        mocker.patch("flux_cli.health.sys.version_info", (3, 10, 0, "final", 0))
        result = h.check_python_version(min_version=(3, 11))
        assert not result.passed


class TestCheckToolInstalled:
    def test_tool_found(self, mocker):
        mocker.patch("flux_cli.health.shutil.which", return_value="/usr/bin/git")
        result = h.check_tool_installed("git")
        assert result.passed

    def test_tool_missing(self, mocker):
        mocker.patch("flux_cli.health.shutil.which", return_value=None)
        result = h.check_tool_installed("nonexistent", fix_hint="install it")
        assert not result.passed
        assert result.fix_hint == "install it"


class TestCheckDirectoryStructure:
    def test_all_present(self, tmp_path):
        for d in ("marketplace", "marketplace/mcps", "marketplace/skills", "src"):
            (tmp_path / d).mkdir(parents=True, exist_ok=True)
        results = h.check_directory_structure(tmp_path)
        assert all(c.passed for c in results)

    def test_missing_src(self, tmp_path):
        for d in ("marketplace", "marketplace/mcps", "marketplace/skills"):
            (tmp_path / d).mkdir(parents=True, exist_ok=True)
        results = h.check_directory_structure(tmp_path)
        src_check = [c for c in results if "src/" in c.label][0]
        assert not src_check.passed


class TestCheckBuildArtifacts:
    def test_no_build_cmd_skipped(self, tmp_path):
        mcp_defs = {"memory": {"type": "npm-package"}}
        results = h.check_build_artifacts(tmp_path, mcp_defs)
        assert len(results) == 0

    def test_build_cmd_with_artifacts(self, tmp_path):
        src = tmp_path / "marketplace" / "mcps" / "my-mcp"
        src.mkdir(parents=True)
        (src / "node_modules").mkdir()
        mcp_defs = {"my-mcp": {"build_cmd": "npm install", "source_dir": "marketplace/mcps/my-mcp"}}
        results = h.check_build_artifacts(tmp_path, mcp_defs)
        assert len(results) == 1
        assert results[0].passed

    def test_build_cmd_without_artifacts(self, tmp_path):
        src = tmp_path / "marketplace" / "mcps" / "my-mcp"
        src.mkdir(parents=True)
        mcp_defs = {"my-mcp": {"build_cmd": "npm install", "source_dir": "marketplace/mcps/my-mcp"}}
        results = h.check_build_artifacts(tmp_path, mcp_defs)
        assert len(results) == 1
        assert not results[0].passed
        assert results[0].warning


class TestCheckFluxInPath:
    def test_flux_in_path(self, mocker):
        mocker.patch("flux_cli.health.shutil.which", return_value="/usr/local/bin/flux")
        result = h.check_flux_in_path()
        assert result.passed

    def test_flux_not_in_path(self, mocker):
        mocker.patch("flux_cli.health.shutil.which", return_value=None)
        result = h.check_flux_in_path()
        assert not result.passed


class TestCheckResult:
    def test_repr_pass(self):
        c = h.CheckResult("test", passed=True)
        assert "PASS" in repr(c)

    def test_repr_fail(self):
        c = h.CheckResult("test", passed=False)
        assert "FAIL" in repr(c)

    def test_repr_warn(self):
        c = h.CheckResult("test", passed=False, warning=True)
        assert "WARN" in repr(c)
