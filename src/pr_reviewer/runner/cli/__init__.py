"""Commands that run on the user's machine as part of the installed runner (Runtime Task 6).

This package is nested inside runner/, not a sibling top-level package, on purpose:
tests/test_package_boundaries.py's collect_imports walks a guarded package's directory
recursively, so everything under runner/cli/ is already covered by runner/'s existing forbidden-
import rule (no pr_reviewer.db, no pr_reviewer.control_plane, no pr_reviewer.cli) with no new
entry needed in GUARDED_PACKAGES. A sibling top-level cli/runner/ would need a second, separate
rule carved out for just that subset of some cli package -- the exact "one package, two
contradictory dependency needs" problem this split exists to avoid, one level down.

pr_reviewer.cli (top-level) is the operator/debug package -- it holds `reviewer trace`, which
legitimately needs the hosted database. Nothing under here may import it, by the same rule that
already forbids pr_reviewer.db and pr_reviewer.control_plane: importing the operator package
would grant the same hosted access through a side door.
"""
