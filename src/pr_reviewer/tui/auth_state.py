"""Whether the local runner is paired with GitHub."""

from __future__ import annotations

from pr_reviewer.runner.secrets import SecretStore

RUNNER_CREDENTIAL_SECRET = "runner_credential"


def is_github_connected(secrets: SecretStore) -> bool:
    credential = secrets.get(RUNNER_CREDENTIAL_SECRET)
    return bool(credential and credential.strip())
