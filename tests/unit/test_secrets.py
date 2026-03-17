"""Unit tests for lib/secrets.py"""
import json
from unittest.mock import MagicMock

import pytest

import secrets as s


class TestKeychainServiceName:
    def test_format(self):
        assert s._keychain_service("my-mcp") == "flux.my-mcp"

    def test_different_names(self):
        assert s._keychain_service("foo") != s._keychain_service("bar")


class TestSecretsIndex:
    def test_returns_empty_dict_when_no_file(self, patch_secrets_paths):
        result = s._load_secrets_index()
        assert result == {}

    def test_reads_existing_index(self, patch_secrets_paths, tmp_path):
        data = {"wikijs-mcp": ["WIKIJS_URL", "WIKIJS_API_KEY"]}
        index_path = tmp_path / ".flux" / "secrets.json"
        index_path.parent.mkdir(parents=True)
        index_path.write_text(json.dumps(data))
        result = s._load_secrets_index()
        assert result == data

    def test_save_creates_flux_home_dir(self, patch_secrets_paths, tmp_path):
        flux_home = tmp_path / ".flux"
        assert not flux_home.exists()
        s._save_secrets_index({"mcp": ["KEY"]})
        assert flux_home.exists()

    def test_save_roundtrip(self, patch_secrets_paths):
        data = {"foo": ["BAR", "BAZ"]}
        s._save_secrets_index(data)
        assert s._load_secrets_index() == data


class TestKeychainSet:
    def test_calls_security_with_correct_args(self, patch_secrets_paths, mocker):
        mock_run = mocker.patch("secrets.subprocess.run")
        mock_run.return_value = MagicMock(returncode=0, stderr=b"")
        s.keychain_set("mymcp", "MY_KEY", "myvalue")
        call_args = mock_run.call_args[0][0]
        assert "add-generic-password" in call_args
        assert "flux.mymcp" in call_args
        assert "MY_KEY" in call_args
        assert "myvalue" in call_args

    def test_updates_index(self, patch_secrets_paths, mocker):
        mocker.patch("secrets.subprocess.run", return_value=MagicMock(returncode=0, stderr=b""))
        s.keychain_set("mymcp", "MY_KEY", "val")
        index = s._load_secrets_index()
        assert "MY_KEY" in index.get("mymcp", [])

    def test_deduplicates_index_entries(self, patch_secrets_paths, mocker):
        mocker.patch("secrets.subprocess.run", return_value=MagicMock(returncode=0, stderr=b""))
        s.keychain_set("mymcp", "MY_KEY", "val1")
        s.keychain_set("mymcp", "MY_KEY", "val2")
        index = s._load_secrets_index()
        assert index["mymcp"].count("MY_KEY") == 1

    def test_exits_on_failure(self, patch_secrets_paths, mocker):
        mocker.patch("secrets.subprocess.run", return_value=MagicMock(returncode=1, stderr=b"error"))
        with pytest.raises(SystemExit) as exc:
            s.keychain_set("mymcp", "MY_KEY", "val")
        assert exc.value.code == 1


class TestKeychainGet:
    def test_returns_value_on_success(self, mocker):
        mocker.patch("secrets.subprocess.run", return_value=MagicMock(returncode=0, stdout="secret\n"))
        assert s.keychain_get("mymcp", "MY_KEY") == "secret"

    def test_returns_none_on_failure(self, mocker):
        mocker.patch("secrets.subprocess.run", return_value=MagicMock(returncode=44, stdout=""))
        assert s.keychain_get("mymcp", "MY_KEY") is None

    def test_strips_trailing_newline(self, mocker):
        mocker.patch("secrets.subprocess.run", return_value=MagicMock(returncode=0, stdout="value\n"))
        assert s.keychain_get("mymcp", "K") == "value"


class TestKeychainDelete:
    def test_removes_key_from_index(self, patch_secrets_paths, mocker):
        mocker.patch("secrets.subprocess.run", return_value=MagicMock(returncode=0, stderr=b""))
        s._save_secrets_index({"mymcp": ["K1", "K2"]})
        mocker.patch("secrets.subprocess.run", return_value=MagicMock(returncode=0))
        s.keychain_delete("mymcp", "K1")
        assert "K1" not in s._load_secrets_index().get("mymcp", [])

    def test_removes_mcp_entry_when_last_key(self, patch_secrets_paths, mocker):
        mocker.patch("secrets.subprocess.run", return_value=MagicMock(returncode=0, stderr=b""))
        s._save_secrets_index({"mymcp": ["ONLY_KEY"]})
        s.keychain_delete("mymcp", "ONLY_KEY")
        assert "mymcp" not in s._load_secrets_index()


class TestGetKeychainEnv:
    def test_returns_all_present_vars(self, mocker):
        def fake_get(mcp, key):
            return {"URL": "http://example.com", "KEY": "abc123"}.get(key)
        mocker.patch("secrets.keychain_get", side_effect=fake_get)
        result = s.get_keychain_env("mymcp", ["URL", "KEY"])
        assert result == {"URL": "http://example.com", "KEY": "abc123"}

    def test_omits_missing_vars(self, mocker):
        mocker.patch("secrets.keychain_get", return_value=None)
        result = s.get_keychain_env("mymcp", ["MISSING"])
        assert result == {}

    def test_empty_env_vars_list(self, mocker):
        result = s.get_keychain_env("mymcp", [])
        assert result == {}
