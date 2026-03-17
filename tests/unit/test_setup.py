"""Unit tests for flux_cli.lib.setup — fresh install and migration."""

import json
from pathlib import Path
from unittest.mock import patch

from flux_cli.lib.setup import (
    _convert_entry,
    _find_old_marketplace,
    check_dependencies,
    install_skill,
    run_setup,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_old_layout(root: Path, *, with_sources: bool = True) -> Path:
    """Build a fake old marketplace layout under *root* and return *root*.

    Creates ``marketplace/marketplace.json`` with a mix of npm-package and
    git-submodule entries, plus skill definitions.
    """
    mp = root / "marketplace"
    mp.mkdir(parents=True, exist_ok=True)

    manifest = {
        "name": "flux-test-marketplace",
        "owner": {"name": "test"},
        "metadata": {"description": "test", "version": "0.1.0"},
        "mcp_definitions": {
            "memory": {
                "type": "npm-package",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-memory"],
                "tags": ["memory"],
            },
            "wikijs-mcp": {
                "type": "git-submodule",
                "source_dir": "marketplace/mcps/wikijs-mcp",
                "command": "uv",
                "args": ["run", "--directory", "{source_dir}", "wikijs-mcp-server"],
                "tags": ["wiki"],
            },
            "unraid-mcp": {
                "type": "git-submodule",
                "source_dir": "marketplace/mcps/unraid-mcp",
                "command": "uv",
                "args": ["run", "--directory", "{source_dir}", "unraid-mcp"],
                "tags": ["unraid"],
            },
        },
        "skill_definitions": {
            "claude-xlsx": {
                "type": "git-submodule",
                "source_dir": "marketplace/skills/xlsx",
                "tags": ["excel"],
            },
        },
    }
    (mp / "marketplace.json").write_text(json.dumps(manifest, indent=2))

    if with_sources:
        # Create source directories so migration can copy them
        for mcp_name in ("wikijs-mcp", "unraid-mcp"):
            mcp_src = root / "marketplace" / "mcps" / mcp_name
            mcp_src.mkdir(parents=True, exist_ok=True)
            (mcp_src / "README.md").write_text(f"# {mcp_name}")

        skill_src = root / "marketplace" / "skills" / "xlsx"
        skill_src.mkdir(parents=True, exist_ok=True)
        (skill_src / "index.js").write_text("// xlsx skill")

        # A launcher file
        launcher_dir = root / "marketplace" / "mcps" / "launchers"
        launcher_dir.mkdir(parents=True, exist_ok=True)
        (launcher_dir / "wikijs-mcp.sh").write_text("#!/bin/bash\nexec uv run wikijs")

    return root


def _make_bundled_skill(tmp_path: Path) -> Path:
    """Create a fake bundled SKILL.md and return its path."""
    skill = tmp_path / "bundled" / "SKILL.md"
    skill.parent.mkdir(parents=True, exist_ok=True)
    skill.write_text("# Flux Skill\nTest content.")
    return skill


# ---------------------------------------------------------------------------
# W4A.1 — Fresh install
# ---------------------------------------------------------------------------

class TestSetupCreatesStructure:
    """run_setup creates the ~/.flux/ directory tree."""

    def test_setup_creates_structure(self, monkeypatch, tmp_path):
        flux_dir = tmp_path / ".flux"
        monkeypatch.setenv("FLUX_TEST_ROOT", str(flux_dir))
        monkeypatch.delenv("FLUX_HOME", raising=False)
        skill = _make_bundled_skill(tmp_path)

        result = run_setup(
            search_path=tmp_path / "nonexistent",  # no old layout
            skill_target_dir=tmp_path / "claude_skills",
            bundled_skill_path=skill,
        )

        assert flux_dir.is_dir()
        assert (flux_dir / "mcps").is_dir()
        assert (flux_dir / "mcps" / "launchers").is_dir()
        assert (flux_dir / "skills").is_dir()
        assert (flux_dir / "sandbox").is_dir()
        assert len(result.dirs_created) > 0


class TestSetupWritesConfig:
    """run_setup writes config.toml with platform defaults."""

    def test_setup_writes_config(self, monkeypatch, tmp_path):
        flux_dir = tmp_path / ".flux"
        monkeypatch.setenv("FLUX_TEST_ROOT", str(flux_dir))
        monkeypatch.delenv("FLUX_HOME", raising=False)
        skill = _make_bundled_skill(tmp_path)

        result = run_setup(
            search_path=tmp_path / "nonexistent",
            skill_target_dir=tmp_path / "claude_skills",
            bundled_skill_path=skill,
        )

        config = flux_dir / "config.toml"
        assert config.exists()
        assert result.config_written is True
        content = config.read_text()
        assert "backend" in content
        assert "flux_home" in content


class TestSetupInstallsSkill:
    """run_setup copies the bundled skill to the Claude skills directory."""

    def test_setup_installs_skill(self, monkeypatch, tmp_path):
        flux_dir = tmp_path / ".flux"
        monkeypatch.setenv("FLUX_TEST_ROOT", str(flux_dir))
        monkeypatch.delenv("FLUX_HOME", raising=False)
        skill = _make_bundled_skill(tmp_path)
        target = tmp_path / "claude_skills"

        result = run_setup(
            search_path=tmp_path / "nonexistent",
            skill_target_dir=target,
            bundled_skill_path=skill,
        )

        assert result.skill_installed is True
        installed = target / "SKILL.md"
        assert installed.exists()
        assert "Flux Skill" in installed.read_text()


class TestSetupDetectsDependencies:
    """run_setup reports missing external tools."""

    def test_setup_detects_dependencies(self, monkeypatch, tmp_path):
        flux_dir = tmp_path / ".flux"
        monkeypatch.setenv("FLUX_TEST_ROOT", str(flux_dir))
        monkeypatch.delenv("FLUX_HOME", raising=False)
        skill = _make_bundled_skill(tmp_path)

        # Make shutil.which return None for everything
        with patch("flux_cli.lib.setup.shutil.which", return_value=None):
            result = run_setup(
                search_path=tmp_path / "nonexistent",
                skill_target_dir=tmp_path / "claude_skills",
                bundled_skill_path=skill,
            )

        assert "uv" in result.missing_deps
        assert "git" in result.missing_deps
        assert "node" in result.missing_deps
        assert "claude" in result.missing_deps

    def test_no_missing_when_all_present(self, monkeypatch, tmp_path):
        flux_dir = tmp_path / ".flux"
        monkeypatch.setenv("FLUX_TEST_ROOT", str(flux_dir))
        monkeypatch.delenv("FLUX_HOME", raising=False)
        skill = _make_bundled_skill(tmp_path)

        with patch("flux_cli.lib.setup.shutil.which", return_value="/usr/bin/fake"):
            result = run_setup(
                search_path=tmp_path / "nonexistent",
                skill_target_dir=tmp_path / "claude_skills",
                bundled_skill_path=skill,
            )

        # Python version check might still flag, but external tools should not
        tool_names = {"uv", "git", "node", "claude"}
        assert tool_names.isdisjoint(set(result.missing_deps))


class TestSetupIdempotent:
    """Running setup twice produces the same result."""

    def test_setup_idempotent(self, monkeypatch, tmp_path):
        flux_dir = tmp_path / ".flux"
        monkeypatch.setenv("FLUX_TEST_ROOT", str(flux_dir))
        monkeypatch.delenv("FLUX_HOME", raising=False)
        skill = _make_bundled_skill(tmp_path)
        kwargs = dict(
            search_path=tmp_path / "nonexistent",
            skill_target_dir=tmp_path / "claude_skills",
            bundled_skill_path=skill,
        )

        run_setup(**kwargs)
        second = run_setup(**kwargs)

        # Second run should not create dirs (already exist)
        assert len(second.dirs_created) == 0
        # Config should not be rewritten
        assert second.config_written is False
        # Skill still installed (overwritten, but that's fine)
        assert second.skill_installed is True


# ---------------------------------------------------------------------------
# W4A.2 — Migration from old layout
# ---------------------------------------------------------------------------

class TestSetupDetectsOldLayout:
    """Migration detects the old marketplace/marketplace.json."""

    def test_setup_detects_old_layout(self, monkeypatch, tmp_path):
        flux_dir = tmp_path / ".flux"
        monkeypatch.setenv("FLUX_TEST_ROOT", str(flux_dir))
        monkeypatch.delenv("FLUX_HOME", raising=False)
        old_root = _make_old_layout(tmp_path / "old_repo")
        skill = _make_bundled_skill(tmp_path)

        result = run_setup(
            search_path=old_root,
            skill_target_dir=tmp_path / "claude_skills",
            bundled_skill_path=skill,
        )

        assert result.migration is not None
        assert result.migration.detected is True

    def test_no_old_layout_means_no_migration(self, monkeypatch, tmp_path):
        flux_dir = tmp_path / ".flux"
        monkeypatch.setenv("FLUX_TEST_ROOT", str(flux_dir))
        monkeypatch.delenv("FLUX_HOME", raising=False)
        skill = _make_bundled_skill(tmp_path)

        result = run_setup(
            search_path=tmp_path / "nonexistent",
            skill_target_dir=tmp_path / "claude_skills",
            bundled_skill_path=skill,
        )

        assert result.migration is not None
        assert result.migration.detected is False


class TestSetupMigratesMcps:
    """Migration copies MCP source directories to ~/.flux/mcps/."""

    def test_setup_migrates_mcps(self, monkeypatch, tmp_path):
        flux_dir = tmp_path / ".flux"
        monkeypatch.setenv("FLUX_TEST_ROOT", str(flux_dir))
        monkeypatch.delenv("FLUX_HOME", raising=False)
        old_root = _make_old_layout(tmp_path / "old_repo")
        skill = _make_bundled_skill(tmp_path)

        result = run_setup(
            search_path=old_root,
            skill_target_dir=tmp_path / "claude_skills",
            bundled_skill_path=skill,
        )

        assert "wikijs-mcp" in result.migration.mcps_copied
        assert "unraid-mcp" in result.migration.mcps_copied
        # npm-package type MCPs have no source_dir, so should NOT be copied
        assert "memory" not in result.migration.mcps_copied

        # Verify files actually exist
        assert (flux_dir / "mcps" / "wikijs-mcp" / "README.md").exists()


class TestSetupMigratesSkills:
    """Migration copies skill source directories to ~/.flux/skills/."""

    def test_setup_migrates_skills(self, monkeypatch, tmp_path):
        flux_dir = tmp_path / ".flux"
        monkeypatch.setenv("FLUX_TEST_ROOT", str(flux_dir))
        monkeypatch.delenv("FLUX_HOME", raising=False)
        old_root = _make_old_layout(tmp_path / "old_repo")
        skill = _make_bundled_skill(tmp_path)

        result = run_setup(
            search_path=old_root,
            skill_target_dir=tmp_path / "claude_skills",
            bundled_skill_path=skill,
        )

        assert "claude-xlsx" in result.migration.skills_copied
        assert (flux_dir / "skills" / "claude-xlsx" / "index.js").exists()


class TestSetupConvertsTypeField:
    """Migration converts git-submodule type to github."""

    def test_setup_converts_type_field(self, monkeypatch, tmp_path):
        flux_dir = tmp_path / ".flux"
        monkeypatch.setenv("FLUX_TEST_ROOT", str(flux_dir))
        monkeypatch.delenv("FLUX_HOME", raising=False)
        old_root = _make_old_layout(tmp_path / "old_repo")
        skill = _make_bundled_skill(tmp_path)

        run_setup(
            search_path=old_root,
            skill_target_dir=tmp_path / "claude_skills",
            bundled_skill_path=skill,
        )

        registry = json.loads((flux_dir / "registry.json").read_text())
        # git-submodule entries should be converted to github
        assert registry["mcp_definitions"]["wikijs-mcp"]["type"] == "github"
        assert registry["mcp_definitions"]["unraid-mcp"]["type"] == "github"
        # npm-package entries should remain unchanged
        assert registry["mcp_definitions"]["memory"]["type"] == "npm-package"
        # Skills too
        assert registry["skill_definitions"]["claude-xlsx"]["type"] == "github"


class TestSetupPreservesAllEntries:
    """Migration preserves every entry from the old manifest."""

    def test_setup_preserves_all_entries(self, monkeypatch, tmp_path):
        flux_dir = tmp_path / ".flux"
        monkeypatch.setenv("FLUX_TEST_ROOT", str(flux_dir))
        monkeypatch.delenv("FLUX_HOME", raising=False)
        old_root = _make_old_layout(tmp_path / "old_repo")
        skill = _make_bundled_skill(tmp_path)

        result = run_setup(
            search_path=old_root,
            skill_target_dir=tmp_path / "claude_skills",
            bundled_skill_path=skill,
        )

        registry = json.loads((flux_dir / "registry.json").read_text())
        # All 3 MCPs + 1 skill = 4 entries
        assert result.migration.registry_entries == 4
        assert "memory" in registry["mcp_definitions"]
        assert "wikijs-mcp" in registry["mcp_definitions"]
        assert "unraid-mcp" in registry["mcp_definitions"]
        assert "claude-xlsx" in registry["skill_definitions"]


class TestSetupMigrationIdempotent:
    """Running migration twice does not duplicate data."""

    def test_setup_migration_idempotent(self, monkeypatch, tmp_path):
        flux_dir = tmp_path / ".flux"
        monkeypatch.setenv("FLUX_TEST_ROOT", str(flux_dir))
        monkeypatch.delenv("FLUX_HOME", raising=False)
        old_root = _make_old_layout(tmp_path / "old_repo")
        skill = _make_bundled_skill(tmp_path)
        kwargs = dict(
            search_path=old_root,
            skill_target_dir=tmp_path / "claude_skills",
            bundled_skill_path=skill,
        )

        run_setup(**kwargs)
        result2 = run_setup(**kwargs)

        # Second run should not re-copy MCP dirs (they already exist)
        assert len(result2.migration.mcps_copied) == 0
        assert len(result2.migration.skills_copied) == 0

        # Registry should still have exactly the same entries
        registry = json.loads((flux_dir / "registry.json").read_text())
        assert len(registry["mcp_definitions"]) == 3
        assert len(registry["skill_definitions"]) == 1


class TestSetupMigrationNeverDeletesOriginal:
    """Migration copies but never deletes the original files."""

    def test_setup_migration_never_deletes_original(self, monkeypatch, tmp_path):
        flux_dir = tmp_path / ".flux"
        monkeypatch.setenv("FLUX_TEST_ROOT", str(flux_dir))
        monkeypatch.delenv("FLUX_HOME", raising=False)
        old_root = _make_old_layout(tmp_path / "old_repo")
        skill = _make_bundled_skill(tmp_path)

        run_setup(
            search_path=old_root,
            skill_target_dir=tmp_path / "claude_skills",
            bundled_skill_path=skill,
        )

        # Original marketplace structure must still be intact
        assert (old_root / "marketplace" / "marketplace.json").exists()
        assert (old_root / "marketplace" / "mcps" / "wikijs-mcp" / "README.md").exists()
        assert (old_root / "marketplace" / "skills" / "xlsx" / "index.js").exists()
        assert (old_root / "marketplace" / "mcps" / "launchers" / "wikijs-mcp.sh").exists()


# ---------------------------------------------------------------------------
# W4A.3 — Bundled skill
# ---------------------------------------------------------------------------

class TestSkillBundledInPackage:
    """The skill file exists in the package data directory."""

    def test_skill_bundled_in_package(self):
        from flux_cli.lib.setup import _BUNDLED_SKILL

        assert _BUNDLED_SKILL.exists(), f"Bundled skill not found at {_BUNDLED_SKILL}"
        content = _BUNDLED_SKILL.read_text()
        assert "flux" in content.lower()
        assert "search" in content.lower()


class TestSetupCopiesSkillToClaude:
    """install_skill copies the bundled file to the target directory."""

    def test_setup_copies_skill_to_claude(self, tmp_path):
        skill = _make_bundled_skill(tmp_path)
        target = tmp_path / "claude" / "skills" / "flux"

        installed = install_skill(bundled_path=skill, target_dir=target)

        assert installed is True
        dest = target / "SKILL.md"
        assert dest.exists()
        assert "Flux Skill" in dest.read_text()

    def test_install_skill_returns_false_when_missing(self, tmp_path):
        missing = tmp_path / "nonexistent" / "SKILL.md"
        target = tmp_path / "target"

        installed = install_skill(bundled_path=missing, target_dir=target)

        assert installed is False


# ---------------------------------------------------------------------------
# Unit tests for internal helpers
# ---------------------------------------------------------------------------

class TestConvertEntry:
    """_convert_entry transforms git-submodule to github."""

    def test_git_submodule_becomes_github(self):
        entry = {"type": "git-submodule", "source_dir": "marketplace/mcps/wikijs-mcp"}
        result = _convert_entry(entry)
        assert result["type"] == "github"
        assert result["repo"] == "wikijs-mcp"

    def test_npm_package_unchanged(self):
        entry = {"type": "npm-package", "command": "npx"}
        result = _convert_entry(entry)
        assert result["type"] == "npm-package"

    def test_does_not_mutate_original(self):
        entry = {"type": "git-submodule", "source_dir": "marketplace/mcps/foo"}
        _convert_entry(entry)
        assert entry["type"] == "git-submodule"
        assert "repo" not in entry


class TestCheckDependencies:
    """check_dependencies reports missing tools."""

    def test_all_present(self):
        with patch("flux_cli.lib.setup.shutil.which", return_value="/usr/bin/x"):
            missing = check_dependencies()
        tools = {"uv", "git", "node", "claude"}
        assert tools.isdisjoint(set(missing))

    def test_all_missing(self):
        with patch("flux_cli.lib.setup.shutil.which", return_value=None):
            missing = check_dependencies()
        assert "uv" in missing
        assert "git" in missing
        assert "node" in missing
        assert "claude" in missing


class TestFindOldMarketplace:
    """_find_old_marketplace locates the old manifest."""

    def test_finds_when_present(self, tmp_path):
        mp = tmp_path / "marketplace"
        mp.mkdir()
        (mp / "marketplace.json").write_text("{}")
        assert _find_old_marketplace(search_path=tmp_path) is not None

    def test_returns_none_when_absent(self, tmp_path):
        assert _find_old_marketplace(search_path=tmp_path) is None
