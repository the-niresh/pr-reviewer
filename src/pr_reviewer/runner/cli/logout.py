"""reviewer logout: the TUI's `l` binding, for headless or scripted use.

Revoking is one-way (control_plane.repository_policy.revoke_runner has no un-revoke), the
same reason reviewer uninstall --delete-data requires --confirm-delete: --yes is required
here so this can never fire by accident from a script or a copy-pasted command.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from pr_reviewer.runner.client import RunnerClient
from pr_reviewer.runner.logout import RUNNER_CREDENTIAL_SECRET, log_out
from pr_reviewer.runner.secrets import default_config_dir, get_secret_store
from pr_reviewer.tui.github_connect import HostedOriginError, resolved_hosted_origin


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        prog="reviewer logout",
        description="Revoke this terminal's pairing and forget its credential.",
        epilog=(
            "Output: no output on success. Refusals are printed to stderr.\n\n"
            "exit codes:\n"
            "  0  logged out\n"
            "  1  refused: --yes not given, or nothing to log out of\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--yes", action="store_true", help="Required: confirms the one-way revoke."
    )
    parsed = parser.parse_args(args)

    secrets = get_secret_store(file_fallback_directory=default_config_dir())
    credential = secrets.get(RUNNER_CREDENTIAL_SECRET)
    if not credential:
        print("reviewer logout: not signed in", file=sys.stderr)
        return 1
    if not parsed.yes:
        print("reviewer logout: refusing without --yes (this cannot be undone)", file=sys.stderr)
        return 1

    runner_client: RunnerClient | None = None
    try:
        hosted_origin = resolved_hosted_origin()
    except HostedOriginError:
        hosted_origin = None
    if hosted_origin is not None:
        runner_client = RunnerClient(hosted_origin, credential)

    log_out(secrets, runner_client=runner_client)
    return 0
