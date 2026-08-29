"""Tests for runner secret storage (Runtime Task 5).

Two code paths, two test suites, not one test with a branch:

- `TestFileSecretStoreFallback` exercises the mode-0600 file fallback against a real temporary
  directory and real filesystem permission bits.
- `TestKeyringSecretStoreBackend` exercises the OS-secret-store wrapper against an injected fake
  backend, not a real OS keyring service. This host has no Secret Service, KWallet, or Keychain
  daemon running, so a test that required one would be untestable here and would silently stop
  proving anything the day CI moved to a different sandbox. The wrapper is the part we own and
  must prove; the real `keyring` package's own backends are not our code to test.

`get_secret_store` selection (prefer OS store, fall back to file) is a third, separate case: it is
about which store gets picked, not about either store's own read/write correctness.

Runner credential, model keys, GitHub tokens, and the Slack secret must never enter
`os.environ`. `SecretStore.get` reads its backend fresh on every call -- no name-to-value cache --
so a rotated secret is visible on the very next call, not after a restart.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path


class FakeKeyringBackend:
    """An in-memory stand-in for keyring.backend.KeyringBackend, used because this sandbox has no
    live OS secret service. Records every call so tests can assert freshness and service scoping,
    not just final values.
    """

    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}
        self.get_calls: list[tuple[str, str]] = []
        self.set_calls: list[tuple[str, str, str]] = []
        self.delete_calls: list[tuple[str, str]] = []

    def get_password(self, service: str, name: str) -> str | None:
        self.get_calls.append((service, name))
        return self.values.get((service, name))

    def set_password(self, service: str, name: str, value: str) -> None:
        self.set_calls.append((service, name, value))
        self.values[(service, name)] = value

    def delete_password(self, service: str, name: str) -> None:
        self.delete_calls.append((service, name))
        self.values.pop((service, name), None)


class ExplodingKeyringBackend:
    def get_password(self, service: str, name: str) -> str | None:
        raise RuntimeError("no OS secret service available")

    def set_password(self, service: str, name: str, value: str) -> None:
        raise RuntimeError("no OS secret service available")

    def delete_password(self, service: str, name: str) -> None:
        raise RuntimeError("no OS secret service available")


def test_file_secret_store_round_trips_a_value(tmp_path: Path) -> None:
    from pr_reviewer.runner.secrets import FileSecretStore

    store = FileSecretStore(tmp_path / "secrets")
    store.set("runner_credential", "cred-abc-123")

    assert store.get("runner_credential") == "cred-abc-123"


def test_file_secret_store_get_of_unknown_name_returns_none(tmp_path: Path) -> None:
    from pr_reviewer.runner.secrets import FileSecretStore

    store = FileSecretStore(tmp_path / "secrets")

    assert store.get("never_set") is None


def test_file_secret_store_writes_secret_files_with_mode_0600(tmp_path: Path) -> None:
    from pr_reviewer.runner.secrets import FileSecretStore

    directory = tmp_path / "secrets"
    store = FileSecretStore(directory)
    store.set("model_key", "sk-example-key")

    secret_files = [path for path in directory.rglob("*") if path.is_file()]
    assert secret_files, "expected FileSecretStore to have written at least one file"
    for path in secret_files:
        mode = path.stat().st_mode & 0o777
        assert mode == 0o600, f"{path} has mode {oct(mode)}, expected 0600"


def test_file_secret_store_creates_its_directory_with_restrictive_permissions(
    tmp_path: Path,
) -> None:
    from pr_reviewer.runner.secrets import FileSecretStore

    directory = tmp_path / "secrets"
    assert not directory.exists()

    store = FileSecretStore(directory)
    store.set("github_token", "ghs_example")

    assert directory.is_dir()
    mode = directory.stat().st_mode & 0o777
    assert mode == 0o700, f"{directory} has mode {oct(mode)}, expected 0700"


def test_file_secret_store_delete_is_idempotent_and_clears_the_value(tmp_path: Path) -> None:
    from pr_reviewer.runner.secrets import FileSecretStore

    store = FileSecretStore(tmp_path / "secrets")
    store.set("slack_secret", "xoxb-example")

    store.delete("slack_secret")
    assert store.get("slack_secret") is None

    store.delete("slack_secret")  # deleting an already-gone secret must not raise


def test_file_secret_store_round_trips_values_with_newlines_and_symbols(tmp_path: Path) -> None:
    from pr_reviewer.runner.secrets import FileSecretStore

    store = FileSecretStore(tmp_path / "secrets")
    tricky_value = "line-one\nline-two\ttab-and-'quotes\"-{\"json\": true}"
    store.set("tricky", tricky_value)

    assert store.get("tricky") == tricky_value


def test_keyring_secret_store_round_trips_through_the_injected_backend() -> None:
    from pr_reviewer.runner.secrets import KeyringSecretStore

    backend = FakeKeyringBackend()
    store = KeyringSecretStore(backend=backend)

    store.set("runner_credential", "cred-xyz-789")
    assert store.get("runner_credential") == "cred-xyz-789"

    store.delete("runner_credential")
    assert store.get("runner_credential") is None


def test_keyring_secret_store_reads_the_backend_fresh_on_every_call() -> None:
    """No name-to-value cache at the SecretStore layer: a value changed underneath the store
    (rotation, or another process writing to the same keyring entry) must be visible on the very
    next get(), not only after the process restarts.
    """
    from pr_reviewer.runner.secrets import KeyringSecretStore

    backend = FakeKeyringBackend()
    store = KeyringSecretStore(backend=backend)
    store.set("model_key", "sk-first")

    assert store.get("model_key") == "sk-first"
    backend.values[(store.service_name, "model_key")] = "sk-rotated"
    assert store.get("model_key") == "sk-rotated"

    assert len(backend.get_calls) == 2, "get() must hit the backend every call, not cache"


def test_keyring_secret_store_scopes_every_secret_under_one_service_namespace() -> None:
    from pr_reviewer.runner.secrets import KeyringSecretStore

    backend = FakeKeyringBackend()
    store = KeyringSecretStore(backend=backend)

    store.set("github_token", "ghs_example")

    assert backend.set_calls == [(store.service_name, "github_token", "ghs_example")]
    assert store.service_name, "service name must be a real, non-empty namespace"


def test_get_secret_store_prefers_keyring_when_it_is_available(tmp_path: Path) -> None:
    from pr_reviewer.runner.secrets import KeyringSecretStore, get_secret_store

    backend = FakeKeyringBackend()
    store = get_secret_store(
        file_fallback_directory=tmp_path / "secrets", keyring_backend=backend
    )

    assert isinstance(store, KeyringSecretStore)


def test_get_secret_store_falls_back_to_file_store_when_keyring_is_unavailable(
    tmp_path: Path,
) -> None:
    from pr_reviewer.runner.secrets import FileSecretStore, get_secret_store

    store = get_secret_store(
        file_fallback_directory=tmp_path / "secrets",
        keyring_backend=ExplodingKeyringBackend(),
    )

    assert isinstance(store, FileSecretStore)
    # The fallback must actually work, not just be selected.
    store.set("runner_credential", "cred-fallback")
    assert store.get("runner_credential") == "cred-fallback"


def test_secret_value_never_appears_in_os_environ_or_a_spawned_childs_environment(
    tmp_path: Path,
) -> None:
    """A child process inherits the parent's environment, so an in-process os.environ check
    alone is not proof that nothing leaked a secret into it. This spawns a real child and inspects
    what it actually inherited.
    """
    from pr_reviewer.runner.secrets import FileSecretStore

    marker = "sk-marker-" + uuid.uuid4().hex
    store = FileSecretStore(tmp_path / "secrets")
    store.set("model_key", marker)

    before = dict(os.environ)
    fetched = store.get("model_key")
    assert fetched == marker
    assert dict(os.environ) == before, "reading a secret must never mutate os.environ"

    child = subprocess.run(
        [sys.executable, "-c", "import os, sys; sys.stdout.write(repr(dict(os.environ)))"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert marker not in child.stdout, "secret leaked into a spawned child's environment"
