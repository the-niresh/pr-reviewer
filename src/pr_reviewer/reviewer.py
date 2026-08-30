"""The single `reviewer` console script (Runtime Task 6), deferred from Task 5A until this task
had a second subcommand to unify with.

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

_USAGE = "usage: reviewer <doctor|trace|start|stop|status|open> [args...]"


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(_USAGE, file=sys.stderr)
        return 1

    subcommand, rest = args[0], args[1:]

    if subcommand == "doctor":
        from pr_reviewer.runner.cli.doctor import main as doctor_main

        return doctor_main(rest)

    if subcommand == "trace":
        from pr_reviewer.cli.trace import main as trace_main

        return trace_main(rest)

    if subcommand in {"start", "stop", "status", "open"}:
        from pr_reviewer.runner.cli.service import main as service_main

        return service_main([subcommand, *rest])

    print(f"reviewer: unknown subcommand {subcommand!r}\n{_USAGE}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
