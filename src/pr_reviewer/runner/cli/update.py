"""CLI wrapper for versioned runner updates (Runtime Task 9)."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from pr_reviewer.runner.update import UpdateError, apply_update


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog="reviewer update")
    parser.add_argument("--install-path", required=True)
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--version", required=True)
    parsed = parser.parse_args(args)
    try:
        apply_update(
            install_path=Path(parsed.install_path),
            artifact_path=Path(parsed.artifact),
            expected_sha256=parsed.sha256,
            version=parsed.version,
        )
    except UpdateError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0
