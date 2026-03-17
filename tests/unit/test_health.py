"""Unit tests for lib/health.py — all subprocess calls mocked."""
import json
import shutil
import subprocess
from unittest.mock import MagicMock

import health as h
import pytest


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

TOOLS_LIST_RESPONSE = {
    "jsonrpc": "2.0",
    "id": 2,
    "result": {"tools": [{"name": "tool1"}]},
}


class TestProbeMcpServer:
    # --- command not found ---

    def test_command_not_found(self, mocker):
        mocker.patch("health.shutil.which", return_value=None)
        status, reason = h.probe_mcp_server({"command": "nonexistent", "args": []})
        assert status == "failed"
        assert "nonexistent" in reason

    # --- http url shortcircuit ---

    def test_http_url_returns_needs_auth(self, mocker):
        mocker.patch("health.shutil.which", return_value="/usr/bin/curl")
        status, _ = h.probe_mcp_server({"command": "http://example.com/mcp", "args": []})
        assert "authentication" in status

    # --- auth check_cmd ---

    def test_auth_check_cmd_failure_returns_auth_required(self, mocker):
        mocker.patch("health.shutil.which", return_value="/usr/bin/cmd")
        mocker.patch("health.subprocess.run", return_value=MagicMock(returncode=1))
        config = {
            "command": "cmd",
            "args": [],
            "auth": {
                "check_cmd": ["gh", "auth", "status"],
                "fix_description": "run gh auth login",
            },
        }
        status, reason = h.probe_mcp_server(config)
        assert status == "auth_required"
        assert "gh auth login" in reason

    def test_auth_check_cmd_timeout_returns_auth_required(self, mocker):
        mocker.patch("health.shutil.which", return_value="/usr/bin/cmd")
        mocker.patch(
            "health.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="gh", timeout=5),
        )
        config = {
            "command": "cmd",
            "args": [],
            "auth": {"check_cmd": ["gh", "auth", "status"], "fix_description": "fix it"},
        }
        status, _ = h.probe_mcp_server(config)
        assert status == "auth_required"

    # --- successful handshake ---

    def test_connected_on_successful_handshake(self, mocker):
        mocker.patch("health.shutil.which", return_value="/usr/bin/npx")
        mock_popen = mocker.patch("health.subprocess.Popen")
        mock_popen.return_value = _make_proc([INIT_RESPONSE, TOOLS_LIST_RESPONSE])
        status, detail = h.probe_mcp_server({"command": "npx", "args": ["-y", "pkg"]})
        assert status == "connected"
        assert "test-server" in detail

    def test_running_when_no_tools_list_response(self, mocker):
        mocker.patch("health.shutil.which", return_value="/usr/bin/npx")
        mock_popen = mocker.patch("health.subprocess.Popen")
        mock_popen.return_value = _make_proc([INIT_RESPONSE])  # no tools/list response
        status, _ = h.probe_mcp_server({"command": "npx", "args": []})
        assert status == "running"

    # --- error responses ---

    def test_auth_error_in_tools_list(self, mocker):
        mocker.patch("health.shutil.which", return_value="/usr/bin/npx")
        mock_popen = mocker.patch("health.subprocess.Popen")
        tools_auth_error = {
            "jsonrpc": "2.0",
            "id": 2,
            "error": {"code": 401, "message": "unauthorized: invalid token"},
        }
        mock_popen.return_value = _make_proc([INIT_RESPONSE, tools_auth_error])
        status, reason = h.probe_mcp_server({"command": "npx", "args": []})
        assert status == "auth_required"
        assert "token" in reason.lower()

    def test_generic_error_in_tools_list(self, mocker):
        mocker.patch("health.shutil.which", return_value="/usr/bin/npx")
        mock_popen = mocker.patch("health.subprocess.Popen")
        tools_error = {
            "jsonrpc": "2.0",
            "id": 2,
            "error": {"code": 500, "message": "internal server error"},
        }
        mock_popen.return_value = _make_proc([INIT_RESPONSE, tools_error])
        status, _ = h.probe_mcp_server({"command": "npx", "args": []})
        assert status == "error"

    # --- timeout + exceptions ---

    def test_process_timeout_returns_timeout(self, mocker):
        mocker.patch("health.shutil.which", return_value="/usr/bin/npx")
        mock_popen = mocker.patch("health.subprocess.Popen")
        mock_proc = MagicMock()
        mock_proc.communicate.side_effect = subprocess.TimeoutExpired(cmd="npx", timeout=10)
        mock_popen.return_value = mock_proc
        status, _ = h.probe_mcp_server({"command": "npx", "args": []})
        assert status == "timeout"
        mock_proc.kill.assert_called_once()

    def test_popen_exception_returns_failed(self, mocker):
        mocker.patch("health.shutil.which", return_value="/usr/bin/npx")
        mocker.patch("health.subprocess.Popen", side_effect=OSError("no such file"))
        status, reason = h.probe_mcp_server({"command": "npx", "args": []})
        assert status == "failed"

    # --- env overrides ---

    def test_env_overrides_passed_to_subprocess(self, mocker):
        mocker.patch("health.shutil.which", return_value="/usr/bin/npx")
        mock_popen = mocker.patch("health.subprocess.Popen")
        mock_popen.return_value = _make_proc([INIT_RESPONSE, TOOLS_LIST_RESPONSE])
        h.probe_mcp_server({"command": "npx", "args": [], "env": {"MY_VAR": "myval"}})
        call_kwargs = mock_popen.call_args[1]
        assert call_kwargs["env"]["MY_VAR"] == "myval"

    # --- non-JSON lines ---

    def test_non_json_lines_skipped(self, mocker):
        mocker.patch("health.shutil.which", return_value="/usr/bin/npx")
        mock_popen = mocker.patch("health.subprocess.Popen")
        mixed_stdout = (
            b"Starting server...\n"
            + json.dumps(INIT_RESPONSE).encode() + b"\n"
            + b"Some log line\n"
            + json.dumps(TOOLS_LIST_RESPONSE).encode() + b"\n"
        )
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (mixed_stdout, b"")
        mock_popen.return_value = mock_proc
        status, _ = h.probe_mcp_server({"command": "npx", "args": []})
        assert status == "connected"

    # --- real subprocess (optional, skipped if npx unavailable) ---

    @pytest.mark.slow
    @pytest.mark.skipif(not shutil.which("npx"), reason="npx not available")
    def test_real_memory_mcp_probe(self):
        config = {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-memory"]}
        status, _ = h.probe_mcp_server(config)
        assert status in ("connected", "running")
