"""Secrets management for Flux — pluggable backend system.

Provides a SecretsBackend protocol and concrete implementations:
  - MacOSKeychainBackend  (macOS Keychain via `security` CLI)
  - LinuxSecretServiceBackend (freedesktop Secret Service via `secretstorage`)
  - AgeEncryptedBackend   (age-encrypted JSON file for headless Linux)

The active backend is determined by config.toml [secrets] backend = "...".
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from flux_cli.lib.paths import flux_home, secrets_path

# ---------------------------------------------------------------------------
# Secrets index (tracks key names per MCP — not values)
# ---------------------------------------------------------------------------

def load_secrets_index() -> dict[str, list[str]]:
    """Load the secrets index from disk, returning empty dict if absent."""
    idx_path = secrets_path()
    if idx_path.exists():
        with open(idx_path) as f:
            return json.load(f)
    return {}


def save_secrets_index(index: dict[str, list[str]]) -> None:
    """Atomically write the secrets index to disk (temp file + rename)."""
    idx_path = secrets_path()
    idx_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=idx_path.parent, suffix=".tmp")
    try:
        with open(fd, "w") as f:
            json.dump(index, f, indent=2, sort_keys=True)
            f.write("\n")
        Path(tmp).replace(idx_path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _index_add_key(mcp_name: str, key: str) -> None:
    """Add a key to the secrets index for the given MCP."""
    index = load_secrets_index()
    index.setdefault(mcp_name, [])
    if key not in index[mcp_name]:
        index[mcp_name].append(key)
    save_secrets_index(index)


def _index_remove_key(mcp_name: str, key: str) -> None:
    """Remove a key from the secrets index for the given MCP."""
    index = load_secrets_index()
    if mcp_name in index:
        index[mcp_name] = [k for k in index[mcp_name] if k != key]
        if not index[mcp_name]:
            del index[mcp_name]
    save_secrets_index(index)


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class SecretsBackend(Protocol):
    """Protocol that all secrets backends must implement."""

    def set(self, mcp_name: str, key: str, value: str) -> None:  # noqa: A003
        """Store a secret value."""
        ...

    def get(self, mcp_name: str, key: str) -> str | None:  # noqa: A003
        """Retrieve a secret value, or None if not found."""
        ...

    def delete(self, mcp_name: str, key: str) -> None:
        """Delete a secret."""
        ...

    def list_keys(self, mcp_name: str | None = None) -> dict[str, list[str]]:
        """Return {mcp: [keys]} for one or all MCPs."""
        ...


# ---------------------------------------------------------------------------
# macOS Keychain backend
# ---------------------------------------------------------------------------

class MacOSKeychainBackend:
    """Secrets backend using macOS Keychain via the ``security`` CLI."""

    @staticmethod
    def _service(mcp_name: str) -> str:
        return f"flux.{mcp_name}"

    def set(self, mcp_name: str, key: str, value: str) -> None:  # noqa: A003
        service = self._service(mcp_name)
        # Use stdin (-w with no arg) to avoid exposing secret on command line (visible via ps)
        cmd = ["security", "add-generic-password", "-s", service, "-a", key, "-w", "-U"]  # noqa: S607
        result = subprocess.run(cmd, input=value.encode(), capture_output=True)  # noqa: S603
        if result.returncode != 0:
            msg = result.stderr.decode().strip() if result.stderr else "unknown error"
            print(f"Keychain write failed: {msg}", file=sys.stderr)
            sys.exit(1)
        _index_add_key(mcp_name, key)

    def get(self, mcp_name: str, key: str) -> str | None:  # noqa: A003
        cmd = ["security", "find-generic-password", "-s", self._service(mcp_name), "-a", key, "-w"]  # noqa: S607
        result = subprocess.run(cmd, capture_output=True, text=True)  # noqa: S603
        if result.returncode == 0:
            return result.stdout.strip()
        return None

    def delete(self, mcp_name: str, key: str) -> None:
        cmd = ["security", "delete-generic-password", "-s", self._service(mcp_name), "-a", key]  # noqa: S607
        subprocess.run(cmd, capture_output=True)  # noqa: S603
        _index_remove_key(mcp_name, key)

    def list_keys(self, mcp_name: str | None = None) -> dict[str, list[str]]:
        index = load_secrets_index()
        if mcp_name:
            keys = index.get(mcp_name, [])
            return {mcp_name: keys} if keys else {}
        return index


# ---------------------------------------------------------------------------
# Linux Secret Service backend (D-Bus)
# ---------------------------------------------------------------------------

class LinuxSecretServiceBackend:
    """Secrets backend using freedesktop.org Secret Service (via secretstorage).

    Falls back to AgeEncryptedBackend if D-Bus is unavailable.
    """

    def __init__(self) -> None:
        self._connection: Any = None
        self._available: bool | None = None

    def _ensure_connection(self) -> Any:
        """Lazily connect to D-Bus. Returns the connection or None."""
        if self._available is False:
            return None
        if self._connection is not None:
            return self._connection
        try:
            import secretstorage  # noqa: S413
            self._connection = secretstorage.dbus_init()
            self._available = True
            return self._connection
        except Exception:  # noqa: BLE001
            self._available = False
            return None

    def _get_collection(self) -> Any:
        conn = self._ensure_connection()
        if conn is None:
            return None
        import secretstorage
        return secretstorage.get_default_collection(conn)

    def _fallback(self) -> AgeEncryptedBackend:
        return AgeEncryptedBackend()

    def set(self, mcp_name: str, key: str, value: str) -> None:  # noqa: A003
        collection = self._get_collection()
        if collection is None:
            self._fallback().set(mcp_name, key, value)
            return
        label = f"flux.{mcp_name}/{key}"
        attrs = {"service": f"flux.{mcp_name}", "account": key}
        collection.create_item(label, attrs, value.encode(), replace=True)
        _index_add_key(mcp_name, key)

    def get(self, mcp_name: str, key: str) -> str | None:  # noqa: A003
        collection = self._get_collection()
        if collection is None:
            return self._fallback().get(mcp_name, key)
        attrs = {"service": f"flux.{mcp_name}", "account": key}
        items = list(collection.search_items(attrs))
        if items:
            return items[0].get_secret().decode()
        return None

    def delete(self, mcp_name: str, key: str) -> None:
        collection = self._get_collection()
        if collection is None:
            self._fallback().delete(mcp_name, key)
            return
        attrs = {"service": f"flux.{mcp_name}", "account": key}
        items = list(collection.search_items(attrs))
        for item in items:
            item.delete()
        _index_remove_key(mcp_name, key)

    def list_keys(self, mcp_name: str | None = None) -> dict[str, list[str]]:
        index = load_secrets_index()
        if mcp_name:
            keys = index.get(mcp_name, [])
            return {mcp_name: keys} if keys else {}
        return index


# ---------------------------------------------------------------------------
# Age encrypted file backend (headless Linux / fallback)
# ---------------------------------------------------------------------------

class AgeEncryptedBackend:
    """Secrets backend using age-encrypted JSON file.

    Identity key: ~/.flux/identity  (permissions 0o600)
    Secrets file: ~/.flux/secrets.age
    """

    def _identity_path(self) -> Path:
        return flux_home() / "identity"

    def _secrets_age_path(self) -> Path:
        return flux_home() / "secrets.age"

    def _ensure_identity(self) -> Path:
        """Create an age identity key if one does not exist."""
        id_path = self._identity_path()
        if id_path.exists():
            return id_path
        flux_home().mkdir(parents=True, exist_ok=True)
        cmd = ["age-keygen"]  # noqa: S607
        result = subprocess.run(cmd, capture_output=True, text=True)  # noqa: S603
        if result.returncode != 0:
            print("Failed to generate age identity. Is 'age' installed?", file=sys.stderr)
            sys.exit(1)
        id_path.write_text(result.stdout)
        id_path.chmod(0o600)
        warnings.warn(
            f"Created new age identity at {id_path}. "
            "Back up this file — losing it means losing access to your secrets.",
            stacklevel=2,
        )
        return id_path

    def _recipient(self) -> str:
        """Extract the public key (recipient) from the identity file."""
        id_path = self._ensure_identity()
        for line in id_path.read_text().splitlines():
            if line.startswith("# public key:"):
                return line.split(":", 1)[1].strip()
        # Fallback: derive from identity
        cmd = ["age-keygen", "-y", str(id_path)]  # noqa: S607
        result = subprocess.run(cmd, capture_output=True, text=True)  # noqa: S603
        return result.stdout.strip()

    def _load_store(self) -> dict[str, dict[str, str]]:
        """Decrypt and load the secrets store. Returns {} if file missing."""
        age_path = self._secrets_age_path()
        if not age_path.exists():
            return {}
        id_path = self._identity_path()
        cmd = ["age", "--decrypt", "-i", str(id_path), str(age_path)]  # noqa: S607
        result = subprocess.run(cmd, capture_output=True, text=True)  # noqa: S603
        if result.returncode != 0:
            msg = f"Failed to decrypt secrets: {result.stderr.strip()}"
            raise RuntimeError(msg)
        return json.loads(result.stdout)

    def _save_store(self, store: dict[str, dict[str, str]]) -> None:
        """Encrypt and atomically write the secrets store (temp file + rename)."""
        age_path = self._secrets_age_path()
        age_path.parent.mkdir(parents=True, exist_ok=True)
        recipient = self._recipient()
        plaintext = json.dumps(store, indent=2, sort_keys=True)
        fd, tmp = tempfile.mkstemp(dir=age_path.parent, suffix=".tmp")
        os.close(fd)
        try:
            cmd = ["age", "--encrypt", "-r", recipient, "-o", tmp]  # noqa: S607
            result = subprocess.run(cmd, input=plaintext, text=True, capture_output=True)  # noqa: S603
            if result.returncode != 0:
                msg = f"Failed to encrypt secrets: {result.stderr.strip()}"
                raise RuntimeError(msg)
            Path(tmp).replace(age_path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def set(self, mcp_name: str, key: str, value: str) -> None:  # noqa: A003
        self._ensure_identity()
        store = self._load_store()
        store.setdefault(mcp_name, {})
        store[mcp_name][key] = value
        self._save_store(store)
        _index_add_key(mcp_name, key)

    def get(self, mcp_name: str, key: str) -> str | None:  # noqa: A003
        store = self._load_store()
        return store.get(mcp_name, {}).get(key)

    def delete(self, mcp_name: str, key: str) -> None:
        store = self._load_store()
        if mcp_name in store:
            store[mcp_name].pop(key, None)
            if not store[mcp_name]:
                del store[mcp_name]
        self._save_store(store)
        _index_remove_key(mcp_name, key)

    def list_keys(self, mcp_name: str | None = None) -> dict[str, list[str]]:
        index = load_secrets_index()
        if mcp_name:
            keys = index.get(mcp_name, [])
            return {mcp_name: keys} if keys else {}
        return index


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_BACKENDS: dict[str, type] = {
    "keychain": MacOSKeychainBackend,
    "secret-service": LinuxSecretServiceBackend,
    "age": AgeEncryptedBackend,
}


def get_backend(config: dict[str, Any] | None = None) -> SecretsBackend:
    """Return the appropriate SecretsBackend based on configuration.

    Parameters
    ----------
    config : dict, optional
        A loaded config dict (from ``load_config()``).  If omitted, the
        backend is chosen via platform detection.
    """
    if config is None:
        from flux_cli.lib.config import load_config
        config = load_config()

    name = config.get("secrets", {}).get("backend", "keychain")
    cls = _BACKENDS.get(name)
    if cls is None:
        msg = f"Unknown secrets backend {name!r}. Known: {', '.join(_BACKENDS)}"
        raise ValueError(msg)
    return cls()
