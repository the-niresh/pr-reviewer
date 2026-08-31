"""Static enforcement of Phase 1's dependency rule.

See docs/phases/phase-1-system-architecture.md, section 4.

This walks the import graph with `ast`, it never imports the packages it inspects. Importing them
would run their module-level code and could pull in the very hosted settings or private key this
test exists to keep out of the local runner.

Vacuous-pass problem: of the nine packages this test originally guarded, only `contracts` existed
at first. A test that only checks packages it finds on disk would pass against nothing, today, and
would keep passing the day someone adds `runner/github_access.py` with a forbidden import, right up
until a human happens to look. That is a green build lying to you.

The fix is `EXPECTED_EXISTING_PACKAGES` below. It is a hardcoded snapshot of which guarded packages
exist right now. `test_guarded_package_inventory_matches_snapshot` fails the moment the real
inventory drifts from that snapshot, in either direction: a new package appears, or one is removed.
There is no way to add `runner/` without this test breaking first, and the only fix for that
specific failure is to edit this file: update the snapshot and confirm the new package is wired into
an actual assertion below. The rule can never silently keep skipping a package that starts existing.

`observability/` and `cli/` (Runtime Task 5A) shipped before this file's guard list was updated for
them -- they existed on disk, unguarded, by omission rather than by decision, which is the same
vacuous-pass problem one level down: a name absent from `GUARDED_PACKAGES` entirely is
indistinguishable from a name present but never checked. Runtime Task 6 closes that gap and adds
`containers/` while
it is at it:

- `observability/` imports nothing of ours except `contracts` (it is pure merge/redaction logic
  over data its callers already fetched -- see observability/__init__.py).
- `cli/` (top-level, operator/debug tools such as `reviewer trace`) legitimately needs the hosted
  database, so no outbound rule applies to it. Its rule is inbound instead: nothing runner-side may
  import it, folded into `RUNNER_SIDE_FORBIDDEN_MODULES` below, because importing it would grant the
  same hosted access through a side door.
- `containers/` (Docker sandbox runtime) is runner-side by the same logic as `runner/` and
  `local_store/`: it must never reach Neon, so it joins `RUNNER_SIDE_PACKAGES`.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "pr_reviewer"

# The full set of packages this file assigns a dependency rule to. contracts through notifications
# are Phase 1 section 4's original list; observability and cli were added by this file once Runtime
# Task 6 closed the gap described in the module docstring above.
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
        "observability",
        "cli",
        "web",
        "github",
        "connectors",
        "evals",
        "models",
        "prompts",
    }
)

# Snapshot of which guarded packages exist on disk today. Update this set in the same commit that
# adds one of the packages above, and only after confirming its rule is enforced below.
EXPECTED_EXISTING_PACKAGES = frozenset(
    {
        "contracts",
        "control_plane",
        "runner",
        "local_store",
        "containers",
        "observability",
        "cli",
        "web",
        "github",
        "connectors",
        "evals",
        "models",
        "prompts",
        "reviewer",
    }
)

# control_plane/* must not reach into any package that can review, retrieve, verify, or run
# untrusted code. The control plane cannot review (Phase 1, section 4).
CONTROL_PLANE_FORBIDDEN_TARGETS = frozenset(
    {"runner", "models", "local_store", "reviewer", "retrieval", "verification", "containers"}
)

# The package(s) that import nothing of ours except contracts -- the shared vocabulary every
# package may depend on. contracts itself has its own dedicated test below because it is imported
# by everything and this loop only handles the "importer" side of that rule.
IMPORTS_ONLY_CONTRACTS_PACKAGES = frozenset({"observability"})

# runner/*, models/ (adapters that hold the user's model key), local_store/*,
# notifications/*, and containers/* must never be able to reach the
# hosted database client (the only current handle onto hosted-only settings: Neon credentials, the
# webhook secret, and, once it exists, the GitHub App private key), the hosted control plane
# itself, or pr_reviewer.cli -- the operator/debug package that legitimately holds that same
# database access, so importing it would grant it through a side door.
RUNNER_SIDE_PACKAGES = frozenset(
    {"runner", "models", "local_store", "notifications", "containers"}
)
RUNNER_SIDE_FORBIDDEN_MODULES = frozenset(
    {"pr_reviewer.db", "pr_reviewer.control_plane", "pr_reviewer.cli"}
)

# web/ is the hosted FastAPI re-export (web/app.py is two lines pointing at control_plane.app).
# It is hosted-side: it may import the control plane, and it must not import runner-side packages
# where the user's model key will live. The same forbidden targets as control_plane, so a new
# onboarding route cannot grow a back-door import into runner/web/local_auth.
HOSTED_SIDE_PACKAGES = frozenset({"web", "connectors"})
HOSTED_SIDE_FORBIDDEN_TARGETS = CONTROL_PLANE_FORBIDDEN_TARGETS


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
    return _imports_matching_prefix(imports, f"pr_reviewer.{forbidden_package}")


def _imports_matching_prefix(imports: set[str], prefix: str) -> set[str]:
    """`prefix` also forbids every submodule of it. A plain `imports & {prefix}` set intersection
    (this file's original RUNNER_SIDE_FORBIDDEN_MODULES check) would miss `from
    pr_reviewer.control_plane.runner_jobs import x`, which resolves to the dotted path
    "pr_reviewer.control_plane.runner_jobs", not "pr_reviewer.control_plane" -- an exact-string
    forbidden list is vacuous against that whole style of import. Reusing the same prefix logic
    CONTROL_PLANE_FORBIDDEN_TARGETS already relied on closes that gap for every forbidden entry,
    not just the ones added for this task.
    """
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


def test_runner_side_packages_boundary() -> None:
    """Covers runner/, models/, local_store/, notifications/, and containers/: none of them may
    reach the hosted database, the hosted control plane, or pr_reviewer.cli (the operator package
    that holds that same hosted access -- see the module docstring). collect_imports walks each
    package's directory recursively, so a nested subpackage such as runner/cli/ is already
    covered here with no separate entry needed.
    """
    existing = [name for name in RUNNER_SIDE_PACKAGES if (SRC_ROOT / name).is_dir()]
    if not existing:
        assert not (RUNNER_SIDE_PACKAGES & EXPECTED_EXISTING_PACKAGES)
        return

    for package_name in existing:
        imports = collect_imports(SRC_ROOT / package_name)
        hits: set[str] = set()
        for forbidden in RUNNER_SIDE_FORBIDDEN_MODULES:
            hits |= _imports_matching_prefix(imports, forbidden)
        assert not hits, (
            f"{package_name}/* must not import the hosted database, the control plane, or the "
            f"operator cli package, found: {sorted(hits)}"
        )


def test_hosted_side_packages_boundary() -> None:
    """Covers web/: the hosted API surface. Same outbound rule as control_plane/."""
    existing = [name for name in HOSTED_SIDE_PACKAGES if (SRC_ROOT / name).is_dir()]
    if not existing:
        assert not (HOSTED_SIDE_PACKAGES & EXPECTED_EXISTING_PACKAGES)
        return

    for package_name in existing:
        imports = collect_imports(SRC_ROOT / package_name)
        for forbidden in HOSTED_SIDE_FORBIDDEN_TARGETS:
            hits = _imports_targeting(imports, forbidden)
            assert not hits, (
                f"{package_name}/* must not import {forbidden}/*, found: {sorted(hits)}"
            )


def test_observability_imports_only_contracts() -> None:
    for package_name in IMPORTS_ONLY_CONTRACTS_PACKAGES:
        package_dir = SRC_ROOT / package_name
        if not package_dir.is_dir():
            # Guarded by test_guarded_package_inventory_matches_snapshot, same pattern as
            # test_control_plane_boundary above.
            assert package_name not in EXPECTED_EXISTING_PACKAGES
            continue

        imports = collect_imports(package_dir)
        foreign = {
            module
            for module in imports
            if module.startswith("pr_reviewer.") and not module.startswith("pr_reviewer.contracts")
        }
        assert not foreign, (
            f"{package_name}/* must import nothing of ours except contracts, found: "
            f"{sorted(foreign)}"
        )


def test_github_package_is_guarded_and_must_not_import_hosted_or_runner_stores() -> None:
    """github/ is shared like contracts/: control_plane, runner, and local_store all import it.

    It was missing from every guard set. The rule is: no pr_reviewer.db, db.client,
    control_plane, runner, or local_store. A Protocol may live here. Clone logic may not.
    """
    assert "github" in GUARDED_PACKAGES
    assert "github" in EXPECTED_EXISTING_PACKAGES
    package_dir = SRC_ROOT / "github"
    assert package_dir.is_dir()
    imports = collect_imports(package_dir)
    forbidden = (
        "pr_reviewer.db",
        "pr_reviewer.control_plane",
        "pr_reviewer.runner",
        "pr_reviewer.local_store",
    )
    hits: set[str] = set()
    for prefix in forbidden:
        hits |= _imports_matching_prefix(imports, prefix)
    assert not hits, f"github/* must not import hosted or runner stores, found: {sorted(hits)}"


def test_connectors_package_is_hosted_and_must_not_import_runner_side() -> None:
    """connectors/ wraps hosted GitHub App calls and writes connector_runs to Neon.

    It is hosted-side, same outbound rule as web/: no runner, local_store, reviewer,
    retrieval, verification, or containers. A Protocol in github/ is fine. Clone logic
    is not.
    """
    assert "connectors" in GUARDED_PACKAGES
    assert "connectors" in EXPECTED_EXISTING_PACKAGES
    assert "connectors" in HOSTED_SIDE_PACKAGES
    package_dir = SRC_ROOT / "connectors"
    assert package_dir.is_dir()
    imports = collect_imports(package_dir)
    for forbidden in HOSTED_SIDE_FORBIDDEN_TARGETS:
        hits = _imports_targeting(imports, forbidden)
        assert not hits, f"connectors/* must not import {forbidden}/*, found: {sorted(hits)}"


def test_evals_package_must_not_import_hosted_stores() -> None:
    """evals/ is a local harness. It scores fixtures. It does not write Neon."""
    assert "evals" in GUARDED_PACKAGES
    assert "evals" in EXPECTED_EXISTING_PACKAGES
    assert "evals" not in HOSTED_SIDE_PACKAGES
    package_dir = SRC_ROOT / "evals"
    assert package_dir.is_dir()
    imports = collect_imports(package_dir)
    for prefix in ("pr_reviewer.models", "pr_reviewer.db", "pr_reviewer.control_plane"):
        hits = _imports_matching_prefix(imports, prefix)
        assert not hits, f"evals/* must not import {prefix}, found: {sorted(hits)}"


def test_prompts_package_is_shared_and_must_not_import_hosted_or_runner_stores() -> None:
    """prompts/ is shared like github/: both hosted and runner import the in-process registry.

    It must not grow a Neon handle or a model-key adapter. The hosted insert writer lives in
    events/record_prompt_version.py.
    """
    assert "prompts" in GUARDED_PACKAGES
    assert "prompts" in EXPECTED_EXISTING_PACKAGES
    package_dir = SRC_ROOT / "prompts"
    assert package_dir.is_dir()
    imports = collect_imports(package_dir)
    forbidden = (
        "pr_reviewer.db",
        "pr_reviewer.control_plane",
        "pr_reviewer.runner",
        "pr_reviewer.local_store",
    )
    hits: set[str] = set()
    for prefix in forbidden:
        hits |= _imports_matching_prefix(imports, prefix)
    assert not hits, f"prompts/* must not import hosted or runner stores, found: {sorted(hits)}"


def test_reviewer_packer_modules_must_not_import_hosted_stores() -> None:
    """The packer is pure. The CLI router still fans out to cli and runner."""
    assert "reviewer" in GUARDED_PACKAGES
    assert "reviewer" in EXPECTED_EXISTING_PACKAGES
    package_dir = SRC_ROOT / "reviewer"
    assert package_dir.is_dir()
    forbidden = (
        "pr_reviewer.db",
        "pr_reviewer.control_plane",
        "pr_reviewer.cli",
        "pr_reviewer.local_store",
    )
    for filename in ("hunk_format.py", "diff_budget.py"):
        file_path = package_dir / filename
        assert file_path.is_file()
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import | ast.ImportFrom):
                imports.update(_resolve_import(file_path, node))
        hits: set[str] = set()
        for prefix in forbidden:
            hits |= _imports_matching_prefix(imports, prefix)
        assert not hits, f"reviewer/{filename} must not import hosted stores, found: {sorted(hits)}"
