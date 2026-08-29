"""Container runtime contract (Runtime Task 6).

Docker is the only v1 implementation (ADR-004, docs/phases/phase-1-system-architecture.md), and
ADR-004 has no reversal trigger: there is no acceptable configuration in which untrusted PR code
runs on the host. Nothing in this package may fall back to running a command outside a container.

This package is runner-side: it never imports pr_reviewer.db, pr_reviewer.control_plane, or
pr_reviewer.cli (see tests/test_package_boundaries.py). The hosted control plane cannot review and
has no business starting containers.
"""
