"""Log the local runner out: best-effort revoke it hosted-side, then forget it locally.

The network call is best-effort on purpose: an unreachable hosted plane must never block
someone from signing out of their own terminal. If it fails, the local credential is still
deleted -- the only thing left behind is a runner row on the hosted plane that stays valid
until a person revokes it some other way (the manual /dashboard path, or reinstalling the App).
"""

from __future__ import annotations

import contextlib

from pr_reviewer.runner.client import RunnerClient
from pr_reviewer.runner.secrets import SecretStore

# Same literal as tui/auth_state.RUNNER_CREDENTIAL_SECRET -- not imported from there, since
# this module lives on the runner side and that one is tui-side; both name the same secret.
RUNNER_CREDENTIAL_SECRET = "runner_credential"


def log_out(secrets: SecretStore, *, runner_client: RunnerClient | None = None) -> None:
    if runner_client is not None:
        # See module docstring: this must never block logout.
        with contextlib.suppress(Exception):
            runner_client.log_out()
    secrets.delete(RUNNER_CREDENTIAL_SECRET)
