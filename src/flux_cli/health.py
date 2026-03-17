"""health.py — MCP server health probing via JSON-RPC handshake and environment diagnostics."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# MCP server probing
# ---------------------------------------------------------------------------


def probe_mcp_server(config: dict[str, Any]) -> tuple[str, str]:
    """Probe an MCP server via MCP initialize + tools/list handshake.
    Returns (status, reason).
    """
    result = probe_mcp_server_detailed(config)
    return result["status"], result["detail"]


def probe_mcp_server_detailed(config: dict[str, Any]) -> dict[str, Any]:
    """Extended probe returning a dict with status, detail, tools_count, server_info."""
    command = config.get('command', '')
    args_list = config.get('args', [])
    env_overrides = config.get('env', {})
    auth = config.get('auth', {})

    if not shutil.which(command):
        return {"status": "failed", "detail": f"command not found: '{command}'",
                "tools_count": None, "server_info": None}

    if command.startswith('http://') or command.startswith('https://'):
        return {"status": "! needs authentication", "detail": command,
                "tools_count": None, "server_info": None}

    if auth.get('check_cmd'):
        try:
            result = subprocess.run(auth['check_cmd'], capture_output=True, timeout=5)  # noqa: S603
            if result.returncode != 0:
                return {"status": "auth_required",
                        "detail": auth.get('fix_description', 'authentication required'),
                        "tools_count": None, "server_info": None}
        except Exception:
            return {"status": "auth_required",
                    "detail": auth.get('fix_description', 'authentication check failed'),
                    "tools_count": None, "server_info": None}

    env = os.environ.copy()
    env.update(env_overrides)
    full_cmd = [command] + [str(a) for a in args_list]

    messages = (
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "flux", "version": "0.1.0"}
        }}) + "\n" +
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}) + "\n"
    )

    try:
        proc = subprocess.Popen(  # noqa: S603
            full_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, env=env
        )
        stdout, _ = proc.communicate(input=messages.encode(), timeout=10)
        lines = [line for line in stdout.decode().splitlines() if line.strip()]

        server_info_detail = None
        tools_count = None
        for line in lines:
            try:
                resp = json.loads(line)
            except json.JSONDecodeError:
                continue
            if resp.get("id") == 1 and "result" in resp:
                si = resp["result"].get("serverInfo", {})
                name = si.get("name", "")
                version = si.get("version", "")
                server_info_detail = f"{name} {version}".strip() if name else "connected"
            if resp.get("id") == 2:
                if "error" in resp:
                    msg = resp["error"].get("message", "")
                    auth_keywords = ["auth", "login", "credential", "token", "unauthorized", "permission"]
                    if any(k in msg.lower() for k in auth_keywords):
                        return {"status": "auth_required", "detail": msg,
                                "tools_count": None, "server_info": server_info_detail}
                    return {"status": "error", "detail": msg,
                            "tools_count": None, "server_info": server_info_detail}
                if "result" in resp:
                    tools = resp["result"].get("tools", [])
                    tools_count = len(tools)
                    return {"status": "connected",
                            "detail": server_info_detail or "connected",
                            "tools_count": tools_count,
                            "server_info": server_info_detail}

        return {"status": "running",
                "detail": server_info_detail or " ".join(full_cmd),
                "tools_count": None, "server_info": server_info_detail}

    except subprocess.TimeoutExpired:
        proc.kill()
        return {"status": "timeout",
                "detail": "server started but did not respond in time",
                "tools_count": None, "server_info": None}
    except Exception as e:
        return {"status": "failed", "detail": str(e),
                "tools_count": None, "server_info": None}


# ---------------------------------------------------------------------------
# Environment diagnostic checks for `flux doctor`
# ---------------------------------------------------------------------------


class CheckResult:
    """Single diagnostic check result."""

    __slots__ = ("label", "passed", "warning", "fix_hint")

    def __init__(self, label: str, *, passed: bool, warning: bool = False, fix_hint: str | None = None):
        self.label = label
        self.passed = passed
        self.warning = warning
        self.fix_hint = fix_hint

    def __repr__(self) -> str:
        mark = "PASS" if self.passed else ("WARN" if self.warning else "FAIL")
        return f"CheckResult({mark}: {self.label})"


def check_python_version(min_version: tuple[int, int] = (3, 11)) -> CheckResult:
    """Check that the running Python meets the minimum version."""
    current = sys.version_info[:2]
    ok = current >= min_version
    label = f"Python >= {min_version[0]}.{min_version[1]} (found {current[0]}.{current[1]})"
    return CheckResult(label, passed=ok,
                       fix_hint=f"Install Python {min_version[0]}.{min_version[1]}+: https://python.org")


def check_tool_installed(name: str, *, fix_hint: str | None = None) -> CheckResult:
    """Check that an external tool is on PATH."""
    found = shutil.which(name) is not None
    label = f"{name} installed"
    return CheckResult(label, passed=found, fix_hint=fix_hint)


def check_directory_structure(flux_root: Path) -> list[CheckResult]:
    """Verify that essential Flux directories exist."""
    checks = []
    expected = [
        (flux_root, "Flux root exists"),
        (flux_root / "marketplace", "marketplace/ directory"),
        (flux_root / "marketplace" / "mcps", "marketplace/mcps/ directory"),
        (flux_root / "marketplace" / "skills", "marketplace/skills/ directory"),
        (flux_root / "src", "src/ directory"),
    ]
    for path, label in expected:
        checks.append(CheckResult(label, passed=path.is_dir(),
                                  fix_hint=f"mkdir -p {path}"))
    return checks


def check_registry_valid(registry_path: Path) -> CheckResult:
    """Verify the registry JSON is valid and parseable."""
    if not registry_path.exists():
        return CheckResult("Registry JSON exists", passed=False,
                           fix_hint=f"File not found: {registry_path}")
    try:
        with open(registry_path) as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return CheckResult("Registry JSON valid", passed=False,
                               fix_hint="Registry is not a JSON object")
        return CheckResult("Registry JSON valid", passed=True)
    except (json.JSONDecodeError, OSError) as e:
        return CheckResult("Registry JSON valid", passed=False,
                           fix_hint=f"Parse error: {e}")


def check_mcp_sources_present(flux_root: Path, mcp_definitions: dict[str, Any]) -> list[CheckResult]:
    """Check that cloned MCP source directories exist on disk."""
    checks = []
    for mcp_name, defn in mcp_definitions.items():
        source_dir = defn.get("source_dir")
        if source_dir:
            full = flux_root / source_dir
            checks.append(CheckResult(
                f"MCP source: {mcp_name} ({source_dir})",
                passed=full.is_dir(),
                fix_hint=f"Run: flux add {mcp_name}",
            ))
    return checks


def check_build_artifacts(flux_root: Path, mcp_definitions: dict[str, Any]) -> list[CheckResult]:
    """Check that MCPs with build_cmd have their build artifacts."""
    checks = []
    for mcp_name, defn in mcp_definitions.items():
        build_cmd = defn.get("build_cmd")
        source_dir = defn.get("source_dir")
        if build_cmd and source_dir:
            src = flux_root / source_dir
            has_artifacts = (
                (src / "node_modules").is_dir()
                or (src / "dist").is_dir()
                or (src / ".venv").is_dir()
                or (src / "build").is_dir()
            )
            checks.append(CheckResult(
                f"Build artifacts: {mcp_name}",
                passed=has_artifacts,
                warning=not has_artifacts,
                fix_hint=f"Run: cd {src} && {build_cmd}",
            ))
    return checks


def check_secrets_consistency(
    secrets_index: dict[str, Any],
    mcp_definitions: dict[str, Any],
) -> list[CheckResult]:
    """Check that MCPs requiring auth have corresponding secrets configured."""
    checks = []
    for mcp_name, defn in mcp_definitions.items():
        auth = defn.get("auth", {})
        env_vars = auth.get("env_vars", [])
        if not env_vars:
            continue
        stored = secrets_index.get(mcp_name, [])
        missing = [v for v in env_vars if v not in stored]
        if missing:
            checks.append(CheckResult(
                f"Secrets for {mcp_name}: missing {', '.join(missing)}",
                passed=False,
                fix_hint=f"Run: flux secret set {mcp_name} <KEY> <VALUE>",
            ))
        else:
            checks.append(CheckResult(
                f"Secrets for {mcp_name}: all configured",
                passed=True,
            ))
    return checks


def check_flux_in_path() -> CheckResult:
    """Check that the flux binary is on PATH."""
    found = shutil.which("flux") is not None
    return CheckResult("flux binary in PATH", passed=found,
                       fix_hint='Add flux bin/ to PATH in ~/.zshrc')


def run_doctor_checks(
    flux_root: Path,
    registry_path: Path | None = None,
    mcp_definitions: dict[str, Any] | None = None,
    secrets_index: dict[str, Any] | None = None,
) -> list[CheckResult]:
    """Run all doctor checks and return a flat list of results."""
    results: list[CheckResult] = []

    results.append(check_python_version())
    results.append(check_tool_installed("uv", fix_hint="curl -LsSf https://astral.sh/uv/install.sh | sh"))
    results.append(check_tool_installed("git", fix_hint="Install git: https://git-scm.com"))
    results.append(check_tool_installed("node", fix_hint="Install Node.js: https://nodejs.org"))
    results.append(check_tool_installed("npm", fix_hint="Install Node.js (npm is bundled)"))
    results.append(check_tool_installed("claude", fix_hint="Install Claude CLI: https://docs.anthropic.com/en/docs/claude-cli"))

    results.extend(check_directory_structure(flux_root))

    if registry_path is not None:
        results.append(check_registry_valid(registry_path))

    if mcp_definitions:
        results.extend(check_mcp_sources_present(flux_root, mcp_definitions))
        results.extend(check_build_artifacts(flux_root, mcp_definitions))

    if mcp_definitions and secrets_index is not None:
        results.extend(check_secrets_consistency(secrets_index, mcp_definitions))

    results.append(check_flux_in_path())

    return results
