"""Unified `reviewer` console script. Lazy-imports each subcommand after the name is known.

This module is deliberately not part of either cli/ (operator/debug tools, needs the hosted
database) or runner/cli/ (ships to and runs continuously on the user's machine, must never reach
it) -- it is the thin router between them, and the property worth protecting is that routing to
one side never drags in the other. Each branch below imports its target module only after the
subcommand name is already known, not at module load time. Importing pr_reviewer.cli.trace
eagerly here would pull pr_reviewer.db.client into every `reviewer doctor` invocation on an end
user's machine, even though doctor's own code never touches it -- exactly the contamination the
cli/ vs runner/cli/ package split exists to prevent, just one layer further out. A dict of
eagerly-imported subcommand callables would have the same problem; the if/elif below with imports
inside each branch is the point, not an accident of style.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence

_USAGE = (
    "usage: reviewer <setup|doctor|trace|start|stop|status|open|update|uninstall"
    "|mcp|a2a|acp> [args...]"
)


def main(argv: Sequence[str] | None = None) -> int:
    # config.get_settings() loads .env, but the TUI connect path reads os.environ
    # directly and never calls it, so PR_REVIEWER_HOSTED_ORIGIN and GITHUB_APP_SLUG
    # were invisible and the connect screen could only ever raise. Loading here, at
    # the one entry every subcommand and the TUI share, fixes all of them at once.
    # load_dotenv does not overwrite variables already in the environment.
    from dotenv import load_dotenv

    load_dotenv()

    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        if sys.stdin.isatty():
            from pr_reviewer.tui.app import run_tui

            return run_tui()
        print(_USAGE, file=sys.stderr)
        return 1

    subcommand, rest = args[0], args[1:]

    if subcommand == "setup":
        from pr_reviewer.cli.main import main as setup_main

        return setup_main(rest)

    if subcommand == "doctor":
        from pr_reviewer.runner.cli.doctor import main as doctor_main

        return doctor_main(rest)

    if subcommand == "trace":
        from pr_reviewer.cli.trace import main as trace_main

        return trace_main(rest)

    if subcommand in {"start", "stop", "status", "open"}:
        from pr_reviewer.runner.cli.service import main as service_main

        return service_main([subcommand, *rest])

    if subcommand == "update":
        from pr_reviewer.runner.cli.update import main as update_main

        return update_main(rest)

    if subcommand == "uninstall":
        from pr_reviewer.runner.cli.uninstall import main as uninstall_main

        return uninstall_main(rest)

    if subcommand == "mcp":
        from pr_reviewer.runner.cli.mcp import main as mcp_main

        return mcp_main(rest)

    if subcommand == "a2a":
        from pr_reviewer.runner.cli.a2a import main as a2a_main

        return a2a_main(rest)

    if subcommand == "acp":
        from pr_reviewer.runner.cli.acp import main as acp_main

        return acp_main(rest)

    print(f"reviewer: unknown subcommand {subcommand!r}\n{_USAGE}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
