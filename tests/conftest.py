"""Shared fixtures for all flux tests."""
import json
import shutil
from pathlib import Path
from unittest.mock import MagicMock

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Filesystem fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def flux_root(tmp_path):
    """
    Create a minimal Flux directory tree in tmp_path and populate it with
    the minimal marketplace fixture. Returns the tmp_path root.
    """
    marketplace_dir = tmp_path / "marketplace"
    mcp_dir = marketplace_dir / "mcps"
    launchers_dir = mcp_dir / "launchers"
    skills_dir = marketplace_dir / "skills"
    src_dir = tmp_path / "src"
    sandbox_dir = tmp_path / "sandbox"

    for d in [marketplace_dir, mcp_dir, launchers_dir, skills_dir, src_dir, sandbox_dir]:
        d.mkdir(parents=True)

    shutil.copy(
        FIXTURES_DIR / "marketplace_minimal.json",
        marketplace_dir / "marketplace.json",
    )
    return tmp_path


@pytest.fixture
def minimal_manifest():
    """Return the minimal marketplace fixture as a dict."""
    with open(FIXTURES_DIR / "marketplace_minimal.json") as f:
        return json.load(f)


@pytest.fixture
def project_dir(flux_root, minimal_manifest):
    """Create a src/myproject/ with a flux.json referencing known MCPs."""
    project = flux_root / "src" / "myproject"
    project.mkdir(parents=True)
    flux_json = {
        "name": "myproject",
        "version": "0.1.0",
        "mcps": ["memory"],
        "skills": [],
    }
    (project / "flux.json").write_text(json.dumps(flux_json, indent=2))
    return project


# ---------------------------------------------------------------------------
# Module-constant patching
# ---------------------------------------------------------------------------

@pytest.fixture
def patch_manifest_paths(monkeypatch, flux_root):
    """Redirect manifest module constants to the temp flux_root."""
    import flux_cli.manifest as m
    monkeypatch.setattr(m, "REGISTRY_VERSION", "1.0.0")



@pytest.fixture
def patch_sandbox_paths(monkeypatch, flux_root):
    """Redirect sandbox module paths to the temp flux_root via FLUX_TEST_ROOT."""
    monkeypatch.setenv("FLUX_TEST_ROOT", str(flux_root))


@pytest.fixture
def patch_secrets_paths(monkeypatch, tmp_path):
    """Redirect secrets module paths to a temp dir."""
    monkeypatch.setenv("FLUX_TEST_ROOT", str(tmp_path))


# ---------------------------------------------------------------------------
# Keychain mock
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_keychain(mocker):
    """
    Mock macOS `security` binary calls so keychain tests run on any platform.
    Returns a dict that tests can inspect/mutate to simulate different responses.
    """
    store = {}  # simulate in-memory keychain

    def fake_run(cmd, **kwargs):
        result = MagicMock()
        result.returncode = 0
        result.stderr = b""
        result.stdout = ""

        if "add-generic-password" in cmd:
            idx = cmd.index("-s")
            svc = cmd[idx + 1]
            idx = cmd.index("-a")
            account = cmd[idx + 1]
            idx = cmd.index("-w")
            val = cmd[idx + 1]
            store[(svc, account)] = val

        elif "find-generic-password" in cmd:
            idx = cmd.index("-s")
            svc = cmd[idx + 1]
            idx = cmd.index("-a")
            account = cmd[idx + 1]
            val = store.get((svc, account))
            if val:
                result.stdout = val + "\n"
            else:
                result.returncode = 44

        elif "delete-generic-password" in cmd:
            idx = cmd.index("-s")
            svc = cmd[idx + 1]
            idx = cmd.index("-a")
            account = cmd[idx + 1]
            store.pop((svc, account), None)

        return result

    mocker.patch("flux_cli.secrets.subprocess.run", side_effect=fake_run)
    return store
