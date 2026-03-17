"""Unit tests for flux_cli.secrets — legacy test file.

The old lib/secrets.py module has been superseded by flux_cli.secrets with
the backend system (MacOSKeychainBackend, LinuxSecretServiceBackend,
AgeEncryptedBackend).  Full test coverage is in test_secrets_backends.py.

This file retains only a smoke test to verify the new module is importable.
"""

from flux_cli.secrets import (
    MacOSKeychainBackend,
    SecretsBackend,
    get_backend,
    load_secrets_index,
    save_secrets_index,
)


class TestModuleImportable:
    """Verify the new secrets module can be imported and key symbols exist."""

    def test_backend_protocol_exists(self):
        assert SecretsBackend is not None

    def test_keychain_backend_exists(self):
        assert MacOSKeychainBackend is not None

    def test_get_backend_callable(self):
        assert callable(get_backend)

    def test_index_functions_callable(self):
        assert callable(load_secrets_index)
        assert callable(save_secrets_index)
