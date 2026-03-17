"""Unit tests for lib/registry.py"""

import json
import sys
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))
from flux_cli.registry import (
    best_package,
    display_name,
    get_server,
    github_slug,
    remote_url,
    search_servers,
    suggest_flux_add,
)

# --- Fixtures ---

def _make_response(payload):
    """Return a mock urlopen response with the given payload dict."""
    body = json.dumps(payload).encode()
    mock_resp = MagicMock()
    mock_resp.read.return_value = body
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


GITHUB_SERVER = {
    "name": "io.example/my-server",
    "title": "My Server",
    "description": "Does something useful",
    "repository": {"url": "https://github.com/example/my-server", "source": "github"},
}

NPM_SERVER = {
    "name": "io.example/npm-server",
    "title": "NPM Server",
    "description": "An npm-based MCP",
    "packages": [
        {"registry_name": "npm", "name": "@example/npm-server", "version": "1.0.0"}
    ],
}

REMOTE_SERVER = {
    "name": "io.example/remote-server",
    "description": "A hosted remote MCP",
    "remotes": [{"type": "streamable-http", "url": "https://mcp.example.com/mcp"}],
}

MINIMAL_SERVER = {
    "name": "io.example/minimal",
}


# --- search_servers ---

class TestSearchServers:
    def test_unwraps_server_key(self):
        payload = {
            "servers": [
                {"server": GITHUB_SERVER, "_meta": {}},
                {"server": NPM_SERVER, "_meta": {}},
            ]
        }
        with patch("urllib.request.urlopen", return_value=_make_response(payload)):
            results = search_servers(query="test")
        assert results == [GITHUB_SERVER, NPM_SERVER]

    def test_skips_items_without_server_key(self):
        payload = {"servers": [{"_meta": {}}, {"server": GITHUB_SERVER, "_meta": {}}]}
        with patch("urllib.request.urlopen", return_value=_make_response(payload)):
            results = search_servers()
        assert results == [GITHUB_SERVER]

    def test_empty_response(self):
        payload = {"servers": []}
        with patch("urllib.request.urlopen", return_value=_make_response(payload)):
            results = search_servers(query="nothing")
        assert results == []

    def test_network_error_raises_runtime_error(self):
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timeout")):
            try:
                search_servers(query="test")
                raise AssertionError("expected RuntimeError")
            except RuntimeError as e:
                assert "Registry unavailable" in str(e)

    def test_query_included_in_url(self):
        payload = {"servers": []}
        captured = {}
        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            return _make_response(payload)
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            search_servers(query="alpaca", limit=5)
        assert "q=alpaca" in captured["url"]
        assert "limit=5" in captured["url"]


# --- get_server ---

class TestGetServer:
    def test_unwraps_server_key(self):
        payload = {"server": GITHUB_SERVER}
        with patch("urllib.request.urlopen", return_value=_make_response(payload)):
            result = get_server("io.example/my-server")
        assert result == GITHUB_SERVER

    def test_falls_back_to_raw_if_no_server_key(self):
        with patch("urllib.request.urlopen", return_value=_make_response(GITHUB_SERVER)):
            result = get_server("io.example/my-server")
        assert result == GITHUB_SERVER


# --- display_name ---

class TestDisplayName:
    def test_prefers_title(self):
        assert display_name({"title": "My Title", "name": "io.x/y"}) == "My Title"

    def test_falls_back_to_name(self):
        assert display_name({"name": "io.x/y"}) == "io.x/y"

    def test_empty_server(self):
        assert display_name({}) == ""


# --- github_slug ---

class TestGithubSlug:
    def test_extracts_owner_repo(self):
        assert github_slug(GITHUB_SERVER) == "example/my-server"

    def test_handles_trailing_slash(self):
        srv = {"repository": {"url": "https://github.com/owner/repo/"}}
        assert github_slug(srv) == "owner/repo"

    def test_handles_git_extension(self):
        srv = {"repository": {"url": "https://github.com/owner/repo.git"}}
        assert github_slug(srv) == "owner/repo"

    def test_handles_subfolder_strips_to_owner_repo(self):
        srv = {"repository": {"url": "https://github.com/owner/repo", "subfolder": "packages/foo"}}
        assert github_slug(srv) == "owner/repo"

    def test_no_repository_returns_none(self):
        assert github_slug({}) is None

    def test_non_github_url_returns_none(self):
        srv = {"repository": {"url": "https://gitlab.com/owner/repo"}}
        assert github_slug(srv) is None


# --- best_package ---

class TestBestPackage:
    def test_prefers_npm(self):
        reg, pkg = best_package(NPM_SERVER)
        assert reg == "npm"
        assert pkg == "@example/npm-server"

    def test_prefers_npm_over_pypi(self):
        srv = {
            "packages": [
                {"registry_name": "pypi", "name": "my-server"},
                {"registry_name": "npm", "name": "@x/my-server"},
            ]
        }
        reg, pkg = best_package(srv)
        assert reg == "npm"

    def test_falls_back_to_pypi(self):
        srv = {"packages": [{"registry_name": "pypi", "name": "my-server"}]}
        reg, pkg = best_package(srv)
        assert reg == "pypi"
        assert pkg == "my-server"

    def test_no_packages_returns_none_none(self):
        reg, pkg = best_package(REMOTE_SERVER)
        assert reg is None
        assert pkg is None

    def test_empty_server(self):
        assert best_package({}) == (None, None)


# --- remote_url ---

class TestRemoteUrl:
    def test_returns_first_remote_url(self):
        assert remote_url(REMOTE_SERVER) == "https://mcp.example.com/mcp"

    def test_no_remotes_returns_none(self):
        assert remote_url(GITHUB_SERVER) is None

    def test_empty_server(self):
        assert remote_url({}) is None


# --- suggest_flux_add ---

class TestSuggestFluxAdd:
    def test_npm_package(self):
        cmd = suggest_flux_add("npm-server", NPM_SERVER)
        assert cmd == "flux add mcp npm-server --npx @example/npm-server"

    def test_github_fallback(self):
        cmd = suggest_flux_add("my-server", GITHUB_SERVER)
        assert cmd == "flux add mcp my-server --github example/my-server"

    def test_remote_only_returns_none(self):
        assert suggest_flux_add("remote-server", REMOTE_SERVER) is None

    def test_minimal_server_returns_none(self):
        assert suggest_flux_add("minimal", MINIMAL_SERVER) is None

    def test_npm_takes_precedence_over_github(self):
        srv = {**NPM_SERVER, "repository": {"url": "https://github.com/x/y"}}
        cmd = suggest_flux_add("mixed", srv)
        assert "--npx" in cmd
