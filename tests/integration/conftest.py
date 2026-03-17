"""Fixtures for integration tests — runs flux as a real subprocess."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

FLUX_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES_DIR = FLUX_ROOT / "tests" / "fixtures"


@pytest.fixture
def flux_env(tmp_path):
    """
    Create a minimal Flux tree in tmp_path and return an env dict suitable for
    passing to subprocess.run so that flux uses this tree for all I/O.
    """
    marketplace_dir = tmp_path / "marketplace"
    mcp_dir = marketplace_dir / "mcps"
    (mcp_dir / "launchers").mkdir(parents=True)
    (marketplace_dir / "skills").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "sandbox").mkdir()

    shutil.copy(
        FIXTURES_DIR / "marketplace_minimal.json",
        marketplace_dir / "marketplace.json",
    )

    # Also seed registry.json from the marketplace fixture for the new CLI
    with open(FIXTURES_DIR / "marketplace_minimal.json") as f:
        manifest = json.load(f)
    registry = {
        "version": "1.0.0",
        "mcp_definitions": manifest.get("mcp_definitions", {}),
        "skill_definitions": manifest.get("skill_definitions", {}),
    }
    (tmp_path / "registry.json").write_text(json.dumps(registry, indent=2))

    env = os.environ.copy()
    env["FLUX_TEST_ROOT"] = str(tmp_path)
    return env, tmp_path


def run_flux(*args, env, cwd=None, input=None):
    """Run flux CLI with the given args and test env. Returns CompletedProcess."""
    return subprocess.run(
        [sys.executable, "-m", "flux_cli.cli.main", *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
        input=input,
    )
