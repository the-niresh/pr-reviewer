"""Generated registry of places where the reviewer refuses to guess."""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Self

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True, order=True)
class RefusalEntry:
    id: str
    source: str
    reason: str

    @classmethod
    def from_row(cls, row: tuple[str, str, str]) -> Self:
        return cls(id=row[0], source=row[1], reason=row[2])

    def as_row(self) -> tuple[str, str, str]:
        return (self.id, self.source, self.reason)


CHECKED_IN_REGISTRY: tuple[tuple[str, str, str], ...] = (
    (
        "eval-baselineblocked-contract",
        "src/pr_reviewer/evals/run_eval.py:BaselineBlocked",
        "Holdout is empty. Refusing to publish a baseline number.",
    ),
    (
        "eval-run-context-source-comparison-empty-holdout",
        "src/pr_reviewer/evals/run_eval.py:run_context_source_comparison",
        "holdout is empty; refusing to report a context-source comparison",
    ),
    (
        "eval-run-diff-only-baseline-empty-holdout",
        "src/pr_reviewer/evals/run_eval.py:run_diff_only_baseline",
        "holdout is empty; refusing to report a baseline",
    ),
    (
        "eval-run-retrieval-comparison-empty-holdout",
        "src/pr_reviewer/evals/run_eval.py:run_retrieval_comparison",
        "holdout is empty; refusing to report a retrieval comparison",
    ),
    (
        "eval-run-specialist-comparison-empty-holdout",
        "src/pr_reviewer/evals/run_eval.py:run_specialist_comparison",
        "holdout is empty; refusing to report a specialist comparison",
    ),
    (
        "eval-run-useful-findings-per-dollar-zero-cost",
        "src/pr_reviewer/evals/run_eval.py:useful_findings_per_dollar",
        "cost_usd is zero; refusing to report useful findings per dollar",
    ),
    (
        "feedback-candidates-unknown-age-decays",
        "src/pr_reviewer/evals/feedback_candidates.py:_event_is_fresh",
        "Feedback with no observed_at is too old to promote.",
    ),
    (
        "notification-confidentiality-default-restricted",
        "src/pr_reviewer/contracts/notification.py:NotificationChannel.confidentiality",
        "Unset confidentiality defaults to restricted.",
    ),
    (
        "reliability-budget-unset-denies",
        "src/pr_reviewer/reliability/budget.py:require_configured",
        "unset",
    ),
    (
        "reliability-circuit-unreadable-denies",
        "src/pr_reviewer/reliability/circuit.py:UNKNOWN_CIRCUIT_STATE",
        "Unreadable circuit state becomes open, which denies new calls.",
    ),
)


class RefusalRegistryDrift(Exception):
    """The checked-in refusal registry no longer matches the source."""


def generate_registry(root: Path = ROOT) -> tuple[RefusalEntry, ...]:
    entries = [
        *_baseline_blocked_entries(root),
        _budget_unset_entry(root),
        _unreadable_circuit_entry(root),
        _restricted_confidentiality_entry(root),
        _unknown_age_feedback_entry(root),
    ]
    return tuple(sorted(entries))


def checked_in_registry() -> tuple[RefusalEntry, ...]:
    return tuple(RefusalEntry.from_row(row) for row in CHECKED_IN_REGISTRY)


def assert_registry_current(root: Path = ROOT) -> None:
    generated = generate_registry(root)
    checked = checked_in_registry()
    if generated != checked:
        raise RefusalRegistryDrift(_format_drift(generated, checked))


def render_registry(entries: tuple[RefusalEntry, ...] | None = None) -> str:
    registry = entries or checked_in_registry()
    lines = [
        "| Refusal | Source | Reason |",
        "|---|---|---|",
    ]
    for entry in registry:
        lines.append(f"| `{entry.id}` | `{entry.source}` | {entry.reason} |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if args == ["--check"]:
        try:
            assert_registry_current()
        except RefusalRegistryDrift as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print("refusal registry is up to date.")
        return 0
    if args:
        print("usage: python -m pr_reviewer.refusals [--check]", file=sys.stderr)
        return 2
    print(render_registry(generate_registry()))
    return 0


def _baseline_blocked_entries(root: Path) -> tuple[RefusalEntry, ...]:
    relative = Path("src/pr_reviewer/evals/run_eval.py")
    module = _parse(root / relative)
    entries: list[RefusalEntry] = []
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == "BaselineBlocked":
            reason = ast.get_docstring(node)
            if not reason:
                raise ValueError("BaselineBlocked must explain the refusal")
            entries.append(
                RefusalEntry(
                    id="eval-baselineblocked-contract",
                    source=f"{relative}:BaselineBlocked",
                    reason=reason,
                )
            )
            break
    for function_name, reason in _raise_messages(module, "BaselineBlocked"):
        entries.append(
            RefusalEntry(
                id=_baseline_id(function_name, reason),
                source=f"{relative}:{function_name}",
                reason=reason,
            )
        )
    return tuple(entries)


def _budget_unset_entry(root: Path) -> RefusalEntry:
    relative = Path("src/pr_reviewer/reliability/budget.py")
    module = _parse(root / relative)
    for function_name, reason in _raise_messages(module, "BudgetDenied"):
        if function_name == "require_configured" and reason == "unset":
            return RefusalEntry(
                id="reliability-budget-unset-denies",
                source=f"{relative}:require_configured",
                reason=reason,
            )
    raise ValueError("require_configured must raise BudgetDenied('unset')")


def _unreadable_circuit_entry(root: Path) -> RefusalEntry:
    relative = Path("src/pr_reviewer/reliability/circuit.py")
    module = _parse(root / relative)
    for node in module.body:
        if isinstance(node, ast.AnnAssign) and _name(node.target) == "UNKNOWN_CIRCUIT_STATE":
            if not isinstance(node.value, ast.Constant) or node.value.value != "open":
                raise ValueError("unreadable circuit state must deny by becoming open")
            return RefusalEntry(
                id="reliability-circuit-unreadable-denies",
                source=f"{relative}:UNKNOWN_CIRCUIT_STATE",
                reason="Unreadable circuit state becomes open, which denies new calls.",
            )
    raise ValueError("UNKNOWN_CIRCUIT_STATE is missing")


def _restricted_confidentiality_entry(root: Path) -> RefusalEntry:
    relative = Path("src/pr_reviewer/contracts/notification.py")
    module = _parse(root / relative)
    for node in ast.walk(module):
        if not isinstance(node, ast.ClassDef) or node.name != "NotificationChannel":
            continue
        for child in node.body:
            if (
                isinstance(child, ast.AnnAssign)
                and _name(child.target) == "confidentiality"
                and isinstance(child.value, ast.Constant)
                and child.value.value == "restricted"
            ):
                return RefusalEntry(
                    id="notification-confidentiality-default-restricted",
                    source=f"{relative}:NotificationChannel.confidentiality",
                    reason="Unset confidentiality defaults to restricted.",
                )
    raise ValueError("NotificationChannel.confidentiality must default to restricted")


def _unknown_age_feedback_entry(root: Path) -> RefusalEntry:
    relative = Path("src/pr_reviewer/evals/feedback_candidates.py")
    module = _parse(root / relative)
    for node in ast.walk(module):
        if isinstance(node, ast.FunctionDef) and node.name == "_event_is_fresh":
            for child in ast.walk(node):
                if _returns_false_when_observed_at_is_none(child):
                    return RefusalEntry(
                        id="feedback-candidates-unknown-age-decays",
                        source=f"{relative}:_event_is_fresh",
                        reason="Feedback with no observed_at is too old to promote.",
                    )
    raise ValueError("_event_is_fresh must drop feedback with unknown age")


def _returns_false_when_observed_at_is_none(node: ast.AST) -> bool:
    if not isinstance(node, ast.If):
        return False
    test = node.test
    if not isinstance(test, ast.Compare):
        return False
    if not _is_event_observed_at(test.left):
        return False
    if len(test.ops) != 1 or not isinstance(test.ops[0], ast.Is):
        return False
    if len(test.comparators) != 1 or not isinstance(test.comparators[0], ast.Constant):
        return False
    if test.comparators[0].value is not None:
        return False
    return any(
        isinstance(child, ast.Return)
        and isinstance(child.value, ast.Constant)
        and child.value.value is False
        for child in node.body
    )


def _raise_messages(module: ast.Module, exception_name: str) -> tuple[tuple[str, str], ...]:
    messages: list[tuple[str, str]] = []
    for node in module.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        for child in ast.walk(node):
            if not isinstance(child, ast.Raise):
                continue
            call = child.exc
            if not isinstance(call, ast.Call) or _name(call.func) != exception_name:
                continue
            if not call.args or not isinstance(call.args[0], ast.Constant):
                raise ValueError(f"{exception_name} in {node.name} must use a literal reason")
            reason = call.args[0].value
            if not isinstance(reason, str):
                raise ValueError(f"{exception_name} in {node.name} must use a string reason")
            messages.append((node.name, reason))
    return tuple(messages)


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _is_event_observed_at(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "observed_at"
        and isinstance(node.value, ast.Name)
        and node.value.id == "event"
    )


def _slug(value: str) -> str:
    return value.replace("_", "-")


def _baseline_id(function_name: str, reason: str) -> str:
    suffix = _baseline_reason_suffix(reason)
    return f"eval-run-{_slug(function_name.removeprefix('run_'))}-{suffix}"


def _baseline_reason_suffix(reason: str) -> str:
    if "useful findings per dollar" in reason:
        return "zero-cost"
    if "context-source comparison" in reason:
        return "empty-holdout"
    if "retrieval comparison" in reason:
        return "empty-holdout"
    if "specialist comparison" in reason:
        return "empty-holdout"
    if "baseline" in reason:
        return "empty-holdout"
    return "changed"


def _format_drift(generated: tuple[RefusalEntry, ...], checked: tuple[RefusalEntry, ...]) -> str:
    generated_rows = [entry.as_row() for entry in generated]
    checked_rows = [entry.as_row() for entry in checked]
    return (
        "refusal registry is out of date\n"
        f"generated: {generated_rows!r}\n"
        f"checked in: {checked_rows!r}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
