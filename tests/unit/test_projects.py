"""Unit tests for flux_cli.projects — project tracking CRUD."""

from __future__ import annotations

import json

from flux_cli.projects import (
    detect_stale_projects,
    list_projects,
    register_project,
    remove_stale_projects,
)


class TestRegisterProject:
    def test_register_project(self, tmp_path):
        projects_file = tmp_path / "projects.json"
        project_dir = tmp_path / "my-app"
        project_dir.mkdir()

        register_project(project_dir, "my-app", projects_file=projects_file)

        data = json.loads(projects_file.read_text())
        assert len(data["projects"]) == 1
        assert data["projects"][0]["name"] == "my-app"
        assert data["projects"][0]["path"] == str(project_dir.resolve())
        assert "registered_at" in data["projects"][0]

    def test_register_project_idempotent(self, tmp_path):
        projects_file = tmp_path / "projects.json"
        project_dir = tmp_path / "my-app"
        project_dir.mkdir()

        register_project(project_dir, "my-app", projects_file=projects_file)
        register_project(project_dir, "my-app", projects_file=projects_file)

        data = json.loads(projects_file.read_text())
        assert len(data["projects"]) == 1

    def test_register_multiple_projects(self, tmp_path):
        projects_file = tmp_path / "projects.json"
        for name in ("app-a", "app-b", "app-c"):
            d = tmp_path / name
            d.mkdir()
            register_project(d, name, projects_file=projects_file)

        data = json.loads(projects_file.read_text())
        assert len(data["projects"]) == 3


class TestListTrackedProjects:
    def test_list_tracked_projects(self, tmp_path):
        projects_file = tmp_path / "projects.json"
        d = tmp_path / "proj"
        d.mkdir()
        register_project(d, "proj", projects_file=projects_file)

        result = list_projects(projects_file=projects_file)
        assert len(result) == 1
        assert result[0]["name"] == "proj"

    def test_list_empty(self, tmp_path):
        projects_file = tmp_path / "projects.json"
        result = list_projects(projects_file=projects_file)
        assert result == []


class TestStaleProjectDetection:
    def test_stale_project_detection(self, tmp_path):
        projects_file = tmp_path / "projects.json"

        # Register a project, then delete its directory
        d = tmp_path / "gone"
        d.mkdir()
        register_project(d, "gone", projects_file=projects_file)
        d.rmdir()

        stale = detect_stale_projects(projects_file=projects_file)
        assert len(stale) == 1
        assert stale[0]["name"] == "gone"

    def test_no_stale_when_all_exist(self, tmp_path):
        projects_file = tmp_path / "projects.json"
        d = tmp_path / "exists"
        d.mkdir()
        register_project(d, "exists", projects_file=projects_file)

        stale = detect_stale_projects(projects_file=projects_file)
        assert stale == []


class TestRemoveStaleProject:
    def test_remove_stale_project(self, tmp_path):
        projects_file = tmp_path / "projects.json"

        d1 = tmp_path / "alive"
        d1.mkdir()
        register_project(d1, "alive", projects_file=projects_file)

        d2 = tmp_path / "dead"
        d2.mkdir()
        register_project(d2, "dead", projects_file=projects_file)
        d2.rmdir()

        removed = remove_stale_projects(projects_file=projects_file)
        assert len(removed) == 1
        assert removed[0]["name"] == "dead"

        # Verify only "alive" remains
        remaining = list_projects(projects_file=projects_file)
        assert len(remaining) == 1
        assert remaining[0]["name"] == "alive"
