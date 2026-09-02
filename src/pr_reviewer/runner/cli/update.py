"""CLI wrapper for versioned runner updates (Runtime Task 9)."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from pr_reviewer.runner.update import UpdateError, apply_update


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        prog="reviewer update",
        description="Apply a runner update artifact after checking its SHA-256.",
        epilog=(
            "Output: no output on success. Errors are printed to stderr.\n\n"
            "exit codes:\n"
            "  0  update applied\n"
            "  1  update failed or checksum did not match\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--install-path", required=True, help="Installed runner directory.")
    parser.add_argument("--artifact", required=True, help="Update artifact path.")
    parser.add_argument("--sha256", required=True, help="Expected artifact SHA-256.")
    parser.add_argument("--version", required=True, help="Version being installed.")
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
