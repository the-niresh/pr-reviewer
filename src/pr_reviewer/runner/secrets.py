"""Runner secret storage (Runtime Task 5).

Runner credential, model keys, GitHub tokens, and the Slack secret never enter os.environ and
never enter local_store's SQLite file. KeyringSecretStore wraps the OS secret store (macOS
Keychain, Windows Credential Manager, Linux Secret Service or KWallet via the `keyring` package)
behind an injectable KeyringBackend so it can be tested without a live OS secret service --
this host has none running. FileSecretStore is the mode-0600 fallback for a host with no usable
OS secret store at all.

Every get() reads its backend fresh, with no name-to-value cache at this layer: a rotated secret
must be visible on the very next call, not only after a restart.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path
from typing import Protocol

SERVICE_NAME = "pr-reviewer"


class SecretStore(Protocol):
    def set(self, name: str, value: str) -> None: ...
    def get(self, name: str) -> str | None: ...
    def delete(self, name: str) -> None: ...


class KeyringBackend(Protocol):
    """Matches the shape of the `keyring` module's own top-level functions, so the real module
    can be passed in directly without an adapter.
    """

    def get_password(self, service: str, name: str) -> str | None: ...
    def set_password(self, service: str, name: str, value: str) -> None: ...
    def delete_password(self, service: str, name: str) -> None: ...


class KeyringSecretStore:
    def __init__(
        self, backend: KeyringBackend | None = None, service_name: str = SERVICE_NAME
    ) -> None:
        self._backend = backend if backend is not None else _real_keyring_backend()
        self.service_name = service_name

    def set(self, name: str, value: str) -> None:
        self._backend.set_password(self.service_name, name, value)

    def get(self, name: str) -> str | None:
        return self._backend.get_password(self.service_name, name)

    def delete(self, name: str) -> None:
        # Deleting an already-absent secret is a no-op, same as FileSecretStore.
        with contextlib.suppress(Exception):
            self._backend.delete_password(self.service_name, name)


class FileSecretStore:
    """One file per secret name, mode 0600, under a directory kept at mode 0700."""

    def __init__(self, directory: str | Path) -> None:
        self._directory = Path(directory)
        self._directory.mkdir(parents=True, exist_ok=True)
        os.chmod(self._directory, 0o700)

    def _path_for(self, name: str) -> Path:
        safe_name = name.replace("/", "_").replace("\\", "_")
        return self._directory / f"{safe_name}.secret"

    def set(self, name: str, value: str) -> None:
        path = self._path_for(name)
        path.write_text(value, encoding="utf-8")
        os.chmod(path, 0o600)

    def get(self, name: str) -> str | None:
        path = self._path_for(name)
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def delete(self, name: str) -> None:
        self._path_for(name).unlink(missing_ok=True)


def _real_keyring_backend() -> KeyringBackend:
    import keyring

    return keyring


def get_secret_store(
    *,
    file_fallback_directory: str | Path,
    keyring_backend: KeyringBackend | None = None,
) -> SecretStore:
    """Prefer the OS secret store; fall back to the mode-0600 file store if it is unavailable.

    A probe read (never a write) against a name this process never sets is enough to surface
    "no secret service reachable" before any real secret is at stake.
    """
    backend = keyring_backend if keyring_backend is not None else _real_keyring_backend()
    try:
        backend.get_password(SERVICE_NAME, "__pr_reviewer_probe__")
    except Exception:
        return FileSecretStore(file_fallback_directory)
    return KeyringSecretStore(backend=backend)
