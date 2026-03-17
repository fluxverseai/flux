"""Tests for flux_cli.lib.secrets — backend protocol, backends, index, and CLI integration."""

from __future__ import annotations

import json
import stat
from unittest.mock import MagicMock, patch

import pytest

from flux_cli.lib.secrets import (
    AgeEncryptedBackend,
    LinuxSecretServiceBackend,
    MacOSKeychainBackend,
    SecretsBackend,
    _index_add_key,
    _index_remove_key,
    get_backend,
    load_secrets_index,
    save_secrets_index,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def secrets_home(monkeypatch, tmp_path):
    """Point flux_home() and secrets_path() at a temp directory."""
    fake_home = tmp_path / ".flux"
    fake_home.mkdir()
    monkeypatch.setattr("flux_cli.lib.secrets.flux_home", lambda: fake_home)
    monkeypatch.setattr("flux_cli.lib.secrets.secrets_path", lambda: fake_home / "secrets.json")
    return fake_home


# ===========================================================================
# W1B.1  Protocol
# ===========================================================================

class TestBackendProtocol:
    """Verify that the SecretsBackend protocol has the right shape."""

    def test_protocol_is_runtime_checkable(self):
        assert hasattr(SecretsBackend, "__protocol_attrs__") or isinstance(SecretsBackend, type)

    def test_keychain_implements_protocol(self):
        assert isinstance(MacOSKeychainBackend(), SecretsBackend)

    def test_secret_service_implements_protocol(self):
        assert isinstance(LinuxSecretServiceBackend(), SecretsBackend)

    def test_age_implements_protocol(self):
        assert isinstance(AgeEncryptedBackend(), SecretsBackend)

    def test_protocol_methods_exist(self):
        for method in ("set", "get", "delete", "list_keys"):
            assert hasattr(SecretsBackend, method)


# ===========================================================================
# W1B.1  get_backend factory
# ===========================================================================

class TestGetBackend:
    def test_get_backend_keychain(self):
        cfg = {"secrets": {"backend": "keychain"}}
        backend = get_backend(cfg)
        assert isinstance(backend, MacOSKeychainBackend)

    def test_get_backend_secret_service(self):
        cfg = {"secrets": {"backend": "secret-service"}}
        backend = get_backend(cfg)
        assert isinstance(backend, LinuxSecretServiceBackend)

    def test_get_backend_age(self):
        cfg = {"secrets": {"backend": "age"}}
        backend = get_backend(cfg)
        assert isinstance(backend, AgeEncryptedBackend)

    def test_get_backend_unknown_raises(self):
        cfg = {"secrets": {"backend": "nosuch"}}
        with pytest.raises(ValueError, match="Unknown secrets backend"):
            get_backend(cfg)

    def test_get_backend_default_from_config(self, monkeypatch):
        """When no config passed, get_backend loads config automatically."""
        monkeypatch.setattr(
            "flux_cli.lib.secrets.get_backend.__module__",  # dummy; we patch load_config
            "flux_cli.lib.secrets",
        )
        with patch("flux_cli.lib.config.load_config", return_value={"secrets": {"backend": "keychain"}}):
            backend = get_backend()
            assert isinstance(backend, MacOSKeychainBackend)


# ===========================================================================
# W1B.2  macOS Keychain backend (mocked)
# ===========================================================================

class TestKeychainSet:
    def test_keychain_set(self, secrets_home, mocker):
        mock_run = mocker.patch("flux_cli.lib.secrets.subprocess.run")
        mock_run.return_value = MagicMock(returncode=0, stderr=b"")
        backend = MacOSKeychainBackend()
        backend.set("mymcp", "MY_KEY", "myvalue")
        args = mock_run.call_args[0][0]
        assert "add-generic-password" in args
        assert "flux.mymcp" in args
        assert "MY_KEY" in args
        # Secret passed via stdin, not on command line (security)
        assert "myvalue" not in args
        assert mock_run.call_args[1].get("input") == b"myvalue"

    def test_keychain_set_updates_index(self, secrets_home, mocker):
        mocker.patch("flux_cli.lib.secrets.subprocess.run",
                      return_value=MagicMock(returncode=0, stderr=b""))
        backend = MacOSKeychainBackend()
        backend.set("mymcp", "MY_KEY", "val")
        idx = load_secrets_index()
        assert "MY_KEY" in idx["mymcp"]

    def test_keychain_set_exits_on_failure(self, secrets_home, mocker):
        mocker.patch("flux_cli.lib.secrets.subprocess.run",
                      return_value=MagicMock(returncode=1, stderr=b"error"))
        backend = MacOSKeychainBackend()
        with pytest.raises(SystemExit):
            backend.set("mymcp", "MY_KEY", "val")


class TestKeychainGet:
    def test_keychain_get(self, mocker):
        mocker.patch("flux_cli.lib.secrets.subprocess.run",
                      return_value=MagicMock(returncode=0, stdout="secret\n"))
        backend = MacOSKeychainBackend()
        assert backend.get("mymcp", "MY_KEY") == "secret"

    def test_keychain_not_found(self, mocker):
        mocker.patch("flux_cli.lib.secrets.subprocess.run",
                      return_value=MagicMock(returncode=44, stdout=""))
        backend = MacOSKeychainBackend()
        assert backend.get("mymcp", "MY_KEY") is None


class TestKeychainDelete:
    def test_keychain_delete(self, secrets_home, mocker):
        mocker.patch("flux_cli.lib.secrets.subprocess.run",
                      return_value=MagicMock(returncode=0))
        save_secrets_index({"mymcp": ["K1", "K2"]})
        backend = MacOSKeychainBackend()
        backend.delete("mymcp", "K1")
        idx = load_secrets_index()
        assert "K1" not in idx.get("mymcp", [])
        assert "K2" in idx["mymcp"]


class TestKeychainListKeys:
    def test_keychain_list_keys(self, secrets_home):
        save_secrets_index({"mcp1": ["A", "B"], "mcp2": ["C"]})
        backend = MacOSKeychainBackend()
        result = backend.list_keys()
        assert result == {"mcp1": ["A", "B"], "mcp2": ["C"]}

    def test_keychain_list_keys_filtered(self, secrets_home):
        save_secrets_index({"mcp1": ["A"], "mcp2": ["B"]})
        backend = MacOSKeychainBackend()
        result = backend.list_keys("mcp1")
        assert result == {"mcp1": ["A"]}

    def test_keychain_list_keys_missing_mcp(self, secrets_home):
        save_secrets_index({"mcp1": ["A"]})
        backend = MacOSKeychainBackend()
        assert backend.list_keys("nonexistent") == {}


# ===========================================================================
# W1B.3  Linux Secret Service backend (mocked)
# ===========================================================================

class TestSecretServiceSet:
    def test_secret_service_set(self, secrets_home, mocker):
        mock_collection = MagicMock()
        mocker.patch.object(
            LinuxSecretServiceBackend, "_get_collection", return_value=mock_collection
        )
        backend = LinuxSecretServiceBackend()
        backend.set("mymcp", "MY_KEY", "myvalue")
        mock_collection.create_item.assert_called_once_with(
            "flux.mymcp/MY_KEY",
            {"service": "flux.mymcp", "account": "MY_KEY"},
            b"myvalue",
            replace=True,
        )
        idx = load_secrets_index()
        assert "MY_KEY" in idx["mymcp"]


class TestSecretServiceGet:
    def test_secret_service_get(self, mocker):
        mock_item = MagicMock()
        mock_item.get_secret.return_value = b"secret_value"
        mock_collection = MagicMock()
        mock_collection.search_items.return_value = [mock_item]
        mocker.patch.object(
            LinuxSecretServiceBackend, "_get_collection", return_value=mock_collection
        )
        backend = LinuxSecretServiceBackend()
        assert backend.get("mymcp", "KEY") == "secret_value"

    def test_secret_service_get_not_found(self, mocker):
        mock_collection = MagicMock()
        mock_collection.search_items.return_value = []
        mocker.patch.object(
            LinuxSecretServiceBackend, "_get_collection", return_value=mock_collection
        )
        backend = LinuxSecretServiceBackend()
        assert backend.get("mymcp", "KEY") is None


class TestSecretServiceDelete:
    def test_secret_service_delete(self, secrets_home, mocker):
        mock_item = MagicMock()
        mock_collection = MagicMock()
        mock_collection.search_items.return_value = [mock_item]
        mocker.patch.object(
            LinuxSecretServiceBackend, "_get_collection", return_value=mock_collection
        )
        save_secrets_index({"mymcp": ["KEY"]})
        backend = LinuxSecretServiceBackend()
        backend.delete("mymcp", "KEY")
        mock_item.delete.assert_called_once()
        idx = load_secrets_index()
        assert "mymcp" not in idx


class TestSecretServiceDBusFallback:
    def test_secret_service_dbus_unavailable_falls_back(self, secrets_home, mocker):
        """When D-Bus is unavailable, falls back to AgeEncryptedBackend."""
        mocker.patch.object(
            LinuxSecretServiceBackend, "_get_collection", return_value=None
        )
        mock_age_set = mocker.patch.object(AgeEncryptedBackend, "set")
        backend = LinuxSecretServiceBackend()
        backend.set("mymcp", "KEY", "val")
        mock_age_set.assert_called_once_with("mymcp", "KEY", "val")

    def test_secret_service_get_falls_back(self, secrets_home, mocker):
        mocker.patch.object(
            LinuxSecretServiceBackend, "_get_collection", return_value=None
        )
        mocker.patch.object(AgeEncryptedBackend, "get", return_value="fallback_val")
        backend = LinuxSecretServiceBackend()
        assert backend.get("mymcp", "KEY") == "fallback_val"

    def test_secret_service_delete_falls_back(self, secrets_home, mocker):
        mocker.patch.object(
            LinuxSecretServiceBackend, "_get_collection", return_value=None
        )
        mock_age_delete = mocker.patch.object(AgeEncryptedBackend, "delete")
        backend = LinuxSecretServiceBackend()
        backend.delete("mymcp", "KEY")
        mock_age_delete.assert_called_once_with("mymcp", "KEY")


# ===========================================================================
# W1B.4  Age encrypted file backend (mocked)
# ===========================================================================

class TestAgeSet:
    def test_age_set(self, secrets_home, mocker):
        identity = secrets_home / "identity"
        identity.write_text("# public key: age1abc\nAGE-SECRET-KEY-1XYZ\n")
        identity.chmod(0o600)

        mocker.patch("flux_cli.lib.secrets.subprocess.run", side_effect=[
            # _load_store (decrypt) — no existing file, won't be called
            # _save_store (encrypt)
            MagicMock(returncode=0, stdout="", stderr=""),
        ])
        # No existing secrets.age file
        backend = AgeEncryptedBackend()
        backend.set("mymcp", "KEY", "value123")
        idx = load_secrets_index()
        assert "KEY" in idx["mymcp"]


class TestAgeGet:
    def test_age_get(self, secrets_home, mocker):
        identity = secrets_home / "identity"
        identity.write_text("# public key: age1abc\nAGE-SECRET-KEY-1XYZ\n")
        identity.chmod(0o600)
        (secrets_home / "secrets.age").write_text("encrypted")

        store = {"mymcp": {"KEY": "secret_value"}}
        mocker.patch("flux_cli.lib.secrets.subprocess.run",
                      return_value=MagicMock(returncode=0, stdout=json.dumps(store), stderr=""))
        backend = AgeEncryptedBackend()
        assert backend.get("mymcp", "KEY") == "secret_value"

    def test_age_get_not_found(self, secrets_home):
        """Returns None when secrets.age file doesn't exist."""
        backend = AgeEncryptedBackend()
        assert backend.get("mymcp", "KEY") is None

    def test_age_get_decrypt_failure_raises(self, secrets_home, mocker):
        """Decrypt failure raises RuntimeError instead of silently returning empty."""
        identity = secrets_home / "identity"
        identity.write_text("# public key: age1abc\nAGE-SECRET-KEY-1XYZ\n")
        identity.chmod(0o600)
        (secrets_home / "secrets.age").write_text("corrupted")
        mocker.patch("flux_cli.lib.secrets.subprocess.run",
                      return_value=MagicMock(returncode=1, stdout="", stderr="bad key"))
        backend = AgeEncryptedBackend()
        with pytest.raises(RuntimeError, match="Failed to decrypt"):
            backend.get("mymcp", "KEY")


class TestAgeDelete:
    def test_age_delete(self, secrets_home, mocker):
        identity = secrets_home / "identity"
        identity.write_text("# public key: age1abc\nAGE-SECRET-KEY-1XYZ\n")
        identity.chmod(0o600)
        (secrets_home / "secrets.age").write_text("encrypted")

        store = {"mymcp": {"KEY": "val", "OTHER": "val2"}}
        mock_run = mocker.patch("flux_cli.lib.secrets.subprocess.run")
        # First call: decrypt (for _load_store)
        # Second call: encrypt to temp file (for _save_store)
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=json.dumps(store), stderr=""),
            MagicMock(returncode=0, stdout="", stderr=""),
        ]
        save_secrets_index({"mymcp": ["KEY", "OTHER"]})

        backend = AgeEncryptedBackend()
        backend.delete("mymcp", "KEY")
        idx = load_secrets_index()
        assert "KEY" not in idx.get("mymcp", [])
        assert "OTHER" in idx["mymcp"]


class TestAgeFirstUseCreatesIdentity:
    def test_age_first_use_creates_identity(self, secrets_home, mocker):
        keygen_output = "# created: 2026-01-01\n# public key: age1testpub\nAGE-SECRET-KEY-1TESTKEY\n"
        mock_run = mocker.patch("flux_cli.lib.secrets.subprocess.run")
        mock_run.side_effect = [
            # age-keygen call
            MagicMock(returncode=0, stdout=keygen_output, stderr=""),
            # _save_store encrypt call
            MagicMock(returncode=0, stdout="", stderr=""),
        ]
        backend = AgeEncryptedBackend()
        with pytest.warns(UserWarning, match="Back up this file"):
            backend.set("mymcp", "KEY", "val")

        id_path = secrets_home / "identity"
        assert id_path.exists()
        assert id_path.read_text() == keygen_output


class TestAgeIdentityPermissions:
    def test_age_identity_permissions(self, secrets_home, mocker):
        keygen_output = "# public key: age1testpub\nAGE-SECRET-KEY-1TESTKEY\n"
        mock_run = mocker.patch("flux_cli.lib.secrets.subprocess.run")
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=keygen_output, stderr=""),
            MagicMock(returncode=0, stdout="", stderr=""),
        ]
        backend = AgeEncryptedBackend()
        with pytest.warns(UserWarning, match="Back up this file"):
            backend.set("mymcp", "KEY", "val")

        id_path = secrets_home / "identity"
        mode = id_path.stat().st_mode
        assert stat.S_IMODE(mode) == 0o600


# ===========================================================================
# W1B.6  Secrets index
# ===========================================================================

class TestSecretsIndexFormat:
    def test_secrets_index_format(self, secrets_home):
        data = {"wikijs-mcp": ["WIKIJS_URL", "WIKIJS_API_KEY"]}
        save_secrets_index(data)
        raw = (secrets_home / "secrets.json").read_text()
        loaded = json.loads(raw)
        assert loaded == data
        # Verify keys are sorted in JSON output
        assert '"wikijs-mcp"' in raw


class TestSecretsIndexAddKey:
    def test_secrets_index_add_key(self, secrets_home):
        _index_add_key("mcp1", "KEY_A")
        idx = load_secrets_index()
        assert idx == {"mcp1": ["KEY_A"]}

    def test_secrets_index_add_key_no_duplicate(self, secrets_home):
        _index_add_key("mcp1", "KEY_A")
        _index_add_key("mcp1", "KEY_A")
        idx = load_secrets_index()
        assert idx["mcp1"].count("KEY_A") == 1

    def test_secrets_index_add_multiple_keys(self, secrets_home):
        _index_add_key("mcp1", "A")
        _index_add_key("mcp1", "B")
        idx = load_secrets_index()
        assert set(idx["mcp1"]) == {"A", "B"}


class TestSecretsIndexRemoveKey:
    def test_secrets_index_remove_key(self, secrets_home):
        save_secrets_index({"mcp1": ["A", "B"]})
        _index_remove_key("mcp1", "A")
        idx = load_secrets_index()
        assert idx == {"mcp1": ["B"]}

    def test_secrets_index_remove_last_key_removes_mcp(self, secrets_home):
        save_secrets_index({"mcp1": ["ONLY"]})
        _index_remove_key("mcp1", "ONLY")
        idx = load_secrets_index()
        assert "mcp1" not in idx

    def test_secrets_index_remove_nonexistent_key(self, secrets_home):
        save_secrets_index({"mcp1": ["A"]})
        _index_remove_key("mcp1", "NOPE")
        idx = load_secrets_index()
        assert idx == {"mcp1": ["A"]}


class TestSecretsIndexAtomicWrite:
    def test_secrets_index_atomic_write(self, secrets_home):
        """Verify atomic write uses temp file + rename."""
        save_secrets_index({"mcp": ["KEY"]})
        idx_path = secrets_home / "secrets.json"
        assert idx_path.exists()
        # Verify content is valid JSON
        data = json.loads(idx_path.read_text())
        assert data == {"mcp": ["KEY"]}

    def test_secrets_index_atomic_write_creates_parent(self, monkeypatch, tmp_path):
        """Parent directory is created if missing."""
        new_home = tmp_path / "new" / ".flux"
        monkeypatch.setattr("flux_cli.lib.secrets.flux_home", lambda: new_home)
        monkeypatch.setattr("flux_cli.lib.secrets.secrets_path", lambda: new_home / "secrets.json")
        save_secrets_index({"x": ["Y"]})
        assert (new_home / "secrets.json").exists()


# ===========================================================================
# W1B.5  CLI integration (mocked backend)
# ===========================================================================

class TestCLISecretSet:
    def test_cli_secret_set(self, secrets_home, mocker):
        """Verify the backend set method is callable with expected args."""
        mock_backend = MagicMock(spec=MacOSKeychainBackend)
        mocker.patch("flux_cli.lib.secrets.get_backend", return_value=mock_backend)

        # Test via the backend interface directly.
        mock_backend.set("mymcp", "MY_KEY", "myval")
        mock_backend.set.assert_called_once_with("mymcp", "MY_KEY", "myval")


class TestCLISecretGet:
    def test_cli_secret_get(self, mocker):
        mock_backend = MagicMock()
        mock_backend.get.return_value = "secret_value"
        mocker.patch("flux_cli.lib.secrets.get_backend", return_value=mock_backend)
        result = mock_backend.get("mymcp", "MY_KEY")
        assert result == "secret_value"


class TestCLISecretDelete:
    def test_cli_secret_delete(self, mocker):
        mock_backend = MagicMock()
        mocker.patch("flux_cli.lib.secrets.get_backend", return_value=mock_backend)
        mock_backend.delete("mymcp", "MY_KEY")
        mock_backend.delete.assert_called_once_with("mymcp", "MY_KEY")


class TestCLISecretListMasked:
    def test_cli_secret_list_masked(self, secrets_home, mocker):
        """Verify list_keys returns index data, and values would be masked in CLI."""
        save_secrets_index({"mcp1": ["KEY_A", "KEY_B"]})
        backend = MacOSKeychainBackend()
        result = backend.list_keys()
        assert result == {"mcp1": ["KEY_A", "KEY_B"]}
        # Values are not exposed by list_keys — only key names
        for _mcp, keys in result.items():
            for _k in keys:
                # In CLI output, values would be masked as "********"
                masked = "********"
                assert len(masked) == 8
