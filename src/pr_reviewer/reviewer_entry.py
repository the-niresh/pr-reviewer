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
    "usage: reviewer <setup|login|logout|doctor|trace|start|stop|status|open|update|uninstall"
    "|review|mcp|a2a|acp> [args...]"
)

_HELP = """\
usage: reviewer <command> [args...]

Commands:
  reviewer                      Open the terminal UI when stdin is a terminal. Signing in
                                 (GitHub pairing) happens here, interactively -- there is
                                 no headless equivalent, since it needs a browser.
  reviewer login                Alias for bare `reviewer`: open the terminal UI to sign in.
  reviewer logout               Revoke this terminal's pairing and forget its credential.
                                 Requires --yes. Non-interactive counterpart to the TUI's
                                 `l` key.
  reviewer setup                Store a local model key.
  reviewer doctor               Check local Docker isolation.
  reviewer trace                Join hosted and local trace events for one job.
  reviewer start                Start the local onboarding server.
  reviewer stop                 Stop the local onboarding server.
  reviewer status               Print whether the local onboarding server is running.
  reviewer open                 Open or print the local onboarding URL.
  reviewer update               Apply a checked runner update artifact.
  reviewer uninstall            Remove the local runner, preserving data by default.
  reviewer review owner/repo#pr --json
                                Run a PR review from the terminal.
  reviewer mcp                  Serve MCP tools over newline JSON-RPC on stdio.
  reviewer a2a                  Serve A2A JSON-RPC on stdio.
  reviewer acp                  Serve ACP messages on stdio.

Agent JSON:
  JSON result statuses: ok, refused, error
  ok:      {"status": "ok", "result": {...}}
  refused: {"status": "refused", "refusal": {"code": "...", "message": "...", "action": "..."}}
  error:   {"status": "error", "error": {"code": "...", "message": "...", "action": "..."}}

reviewer review exit codes:
  0  review completed, no findings
  1  review completed, findings present
  2  refused, such as GitHub not connected or provider out of tokens
  3  failure

Use `reviewer <command> --help` for arguments and per-command output details.
"""


def main(argv: Sequence[str] | None = None) -> int:
    # config.get_settings() loads .env, but the TUI connect path reads os.environ
    # directly and never calls it, so PR_REVIEWER_HOSTED_ORIGIN and GITHUB_APP_SLUG
    # were invisible and the connect screen could only ever raise. Loading here, at
    # the one entry every subcommand and the TUI share, fixes all of them at once.
    # load_dotenv does not overwrite variables already in the environment.
    from dotenv import load_dotenv

    load_dotenv()

    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in {"-h", "--help"}:
        print(_HELP)
        return 0
    if not args:
        if sys.stdin.isatty():
            from pr_reviewer.tui.app import run_tui

            return run_tui()
        print(_USAGE, file=sys.stderr)
        return 1

    subcommand, rest = args[0], args[1:]

    if subcommand == "login":
        # Not a distinct flow: signing in only ever happens through the interactive TUI
        # (it needs a browser), so this is the same bare-`reviewer` entry point under a
        # name people look for out of habit (gh auth login, etc).
        if sys.stdin.isatty():
            from pr_reviewer.tui.app import run_tui

            return run_tui()
        print("reviewer login: needs a terminal (stdin is not a tty)", file=sys.stderr)
        return 1

    if subcommand == "logout":
        from pr_reviewer.runner.cli.logout import main as logout_main

        return logout_main(rest)

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

    if subcommand == "review":
        from pr_reviewer.runner.cli.review import main as review_main

        return review_main(rest)

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
