"""reviewer setup. Hidden input only. No hosted-plane secrets."""

from __future__ import annotations

import argparse
import getpass
import sys
from collections.abc import Callable, Sequence

from pr_reviewer.runner.secrets import SecretStore

_SECRET_FLAGS = (
    "--model-key",
    "--neon",
    "--webhook-secret",
    "--github-app-private-key",
    "--pat",
)


def run_setup(
    *,
    hosted_origin: str,
    secrets: SecretStore,
    read_secret: Callable[[str], str] | None = None,
    argv: Sequence[str] | None = None,
) -> int:
    del hosted_origin
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "setup":
        args = args[1:]
    for flag in _SECRET_FLAGS:
        if flag in args:
            raise SystemExit(f"refusing secret flag {flag}")
    parser = argparse.ArgumentParser(
        prog="reviewer setup",
        description="Store the local model key for the runner.",
        epilog=(
            "Output: prompts for the model key with hidden input. No JSON mode.\n\n"
            "exit codes:\n"
            "  0  key stored\n"
            "  1  setup failed or refused an unsafe argument\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--hosted-origin",
        required=True,
        help="Hosted control plane origin. Must start with https://.",
    )
    parsed = parser.parse_args(args)
    if not str(parsed.hosted_origin).startswith("https://"):
        raise SystemExit("hosted origin must be https")
    reader = read_secret if read_secret is not None else (lambda prompt: getpass.getpass(prompt))
    key = reader("Model API key")
    secrets.set("model_key", key)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return run_setup(
        hosted_origin="",
        secrets=_default_secrets(),
        argv=list(sys.argv[1:] if argv is None else argv),
    )


def _default_secrets() -> SecretStore:
    from pr_reviewer.runner.secrets import default_config_dir, get_secret_store

    return get_secret_store(file_fallback_directory=default_config_dir())
