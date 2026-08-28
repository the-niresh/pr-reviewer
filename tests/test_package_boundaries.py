"""Static enforcement of Phase 1's dependency rule.

See docs/phases/phase-1-system-architecture.md, section 4.

This walks the import graph with `ast`, it never imports the packages it inspects. Importing them
would run their module-level code and could pull in the very hosted settings or private key this
test exists to keep out of the local runner.

Vacuous-pass problem: of the nine packages this test guards, only `contracts` exists today.
`control_plane`, `runner`, `local_store`, `reviewer`, `retrieval`, `verification`, `containers`, and
`notifications` do not exist yet. A test that only checks packages it finds on disk would pass
against nothing, today, and would keep passing the day someone adds `runner/github_access.py` with
a forbidden import, right up until a human happens to look. That is a green build lying to you.

The fix is `EXPECTED_EXISTING_PACKAGES` below. It is a hardcoded snapshot of which guarded packages
exist right now. `test_guarded_package_inventory_matches_snapshot` fails the moment the real
inventory drifts from that snapshot, in either direction: a new package appears, or one is removed.
There is no way to add `runner/` without this test breaking first, and the only fix for that
specific failure is to edit this file: update the snapshot and confirm the new package is wired into
`test_control_plane_boundary` or `test_runner_and_local_store_boundary` below. The rule can never
silently keep skipping a package that starts existing.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "pr_reviewer"

# The full set of packages Phase 1 section 4 assigns a dependency rule to.
GUARDED_PACKAGES = frozenset(
    {
        "contracts",
        "control_plane",
        "runner",
        "local_store",
        "reviewer",
        "retrieval",
        "verification",
        "containers",
        "notifications",
    }
)

# Snapshot of which guarded packages exist on disk today. Update this set in the same commit that
# adds one of the packages above, and only after confirming its rule is enforced below.
EXPECTED_EXISTING_PACKAGES = frozenset({"contracts", "control_plane"})

# control_plane/* must not reach into any package that can review, retrieve, verify, or run
# untrusted code. The control plane cannot review (Phase 1, section 4).
CONTROL_PLANE_FORBIDDEN_TARGETS = frozenset(
    {"runner", "local_store", "reviewer", "retrieval", "verification", "containers"}
)

# runner/*, local_store/*, and notifications/* must never be able to reach the hosted database
# client, which is the only current handle onto hosted-only settings (Neon credentials, the
# webhook secret, and, once it exists, the GitHub App private key).
RUNNER_SIDE_PACKAGES = frozenset({"runner", "local_store", "notifications"})
RUNNER_SIDE_FORBIDDEN_MODULES = frozenset({"pr_reviewer.db.client", "pr_reviewer.db"})


def _module_name_for_file(file_path: Path) -> str:
    relative = file_path.relative_to(SRC_ROOT.parent).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _resolve_import(file_path: Path, node: ast.Import | ast.ImportFrom) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]

    if node.level == 0:
        return [node.module] if node.module else []

    own_module = _module_name_for_file(file_path)
    own_parts = own_module.split(".")
    package_parts = own_parts[:-1] if file_path.name != "__init__.py" else own_parts
    trimmed = (
        package_parts[: len(package_parts) - (node.level - 1)] if node.level > 1 else package_parts
    )
    if node.module:
        trimmed = trimmed + node.module.split(".")
    return [".".join(trimmed)]


def collect_imports(package_dir: Path) -> set[str]:
    """Return every module dotted-path imported under package_dir, via static AST parsing."""
    imports: set[str] = set()
    for file_path in sorted(package_dir.rglob("*.py")):
        if "__pycache__" in file_path.parts:
            continue
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import | ast.ImportFrom):
                imports.update(_resolve_import(file_path, node))
    return imports


def _existing_guarded_packages() -> set[str]:
    return {name for name in GUARDED_PACKAGES if (SRC_ROOT / name).is_dir()}


def _imports_targeting(imports: set[str], forbidden_package: str) -> set[str]:
    prefix = f"pr_reviewer.{forbidden_package}"
    return {module for module in imports if module == prefix or module.startswith(prefix + ".")}


def test_guarded_package_inventory_matches_snapshot() -> None:
    existing = _existing_guarded_packages()
    assert existing == EXPECTED_EXISTING_PACKAGES, (
        "The set of guarded packages on disk has changed. Do not silently accept this: expected "
        f"{sorted(EXPECTED_EXISTING_PACKAGES)}, found {sorted(existing)}. Update "
        "EXPECTED_EXISTING_PACKAGES in this file only after confirming the new package's "
        "dependency rule is actually enforced by a check in this file."
    )


def test_contracts_imports_nothing_of_ours() -> None:
    package_dir = SRC_ROOT / "contracts"
    assert package_dir.is_dir(), "contracts/ is expected to exist, this check must not go vacuous"

    imports = collect_imports(package_dir)
    foreign = {
        module
        for module in imports
        if module.startswith("pr_reviewer.") and not module.startswith("pr_reviewer.contracts")
    }
    assert not foreign, f"contracts/* must import nothing of ours, found: {sorted(foreign)}"


def test_control_plane_boundary() -> None:
    package_dir = SRC_ROOT / "control_plane"
    if not package_dir.is_dir():
        # Guarded by test_guarded_package_inventory_matches_snapshot: this branch cannot start
        # silently covering nothing once control_plane/ is added, because that test fails first.
        assert "control_plane" not in EXPECTED_EXISTING_PACKAGES
        return

    imports = collect_imports(package_dir)
    for forbidden in CONTROL_PLANE_FORBIDDEN_TARGETS:
        hits = _imports_targeting(imports, forbidden)
        assert not hits, f"control_plane/* must not import {forbidden}/*, found: {sorted(hits)}"


def test_runner_and_local_store_boundary() -> None:
    existing = [name for name in RUNNER_SIDE_PACKAGES if (SRC_ROOT / name).is_dir()]
    if not existing:
        assert not (RUNNER_SIDE_PACKAGES & EXPECTED_EXISTING_PACKAGES)
        return

    for package_name in existing:
        imports = collect_imports(SRC_ROOT / package_name)
        hits = imports & RUNNER_SIDE_FORBIDDEN_MODULES
        assert not hits, (
            f"{package_name}/* must not import the hosted database client, found: {sorted(hits)}"
        )
