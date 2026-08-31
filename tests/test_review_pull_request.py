"""Failing tests for the diff-only one-agent baseline (master Task 11).

The model is parsed into FindingDraft, which has no system-owned fields. The
reviewer constructs FindingCandidate from that draft. Imports of new modules
stay inside test bodies.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from pr_reviewer.contracts.github import OmissionReason
from pr_reviewer.github.pull_request import PullRequestFile, PullRequestSnapshot

SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "pr_reviewer"
BASE_SHA = "a" * 40
HEAD_SHA = "b" * 40
SMALL_PATCH = "@@ -1,1 +1,1 @@\n-old\n+new\n"
FORBIDDEN_FIELDS = (
    "id",
    "review_job_id",
    "verified",
    "verification_method",
    "public_safe",
    "status",
)


def _snapshot(files: list[PullRequestFile]) -> PullRequestSnapshot:
    return PullRequestSnapshot(
        repo_owner="acme",
        repo_name="widgets",
        number=12,
        base_sha=BASE_SHA,
        head_sha=HEAD_SHA,
        title="Add widget",
        body="please review",
        files=files,
    )


def _file(path: str, patch: str | None = SMALL_PATCH, **kwargs: object) -> PullRequestFile:
    fields: dict[str, object] = {"path": path, "status": "modified", "patch": patch}
    fields.update(kwargs)
    return PullRequestFile.model_validate(fields)


def _draft_dict(**overrides: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "concern": "correctness",
        "severity": "high",
        "category": "null-check",
        "file_path": "app.py",
        "line_start": 1,
        "line_end": 1,
        "title": "Missing null check",
        "rationale": "value can be None",
        "evidence": ["app.py:1"],
        "confidence": 0.8,
    }
    fields.update(overrides)
    return fields


def _packed(files: list[PullRequestFile]) -> Any:
    from pr_reviewer.contracts.review_context import ContextBudget
    from pr_reviewer.reviewer.diff_budget import pack_diff

    return pack_diff(_snapshot(files), ContextBudget(tokens=10_000), lambda _text: 1)


def _fake_model(parsed: dict[str, Any]) -> Any:
    from pr_reviewer.models.provider import ModelResponse

    class FakeModel:
        def __init__(self) -> None:
            self.calls: list[Any] = []

        def complete_json(self, request: Any) -> Any:
            self.calls.append(request)
            return ModelResponse(
                parsed=parsed,
                output_hash="a" * 64,
                provider_request_id=None,
                provider="openai",
                model=request.model,
                prompt_name=request.prompt_name,
                prompt_version=request.prompt_version,
                input_tokens=1,
                output_tokens=1,
                cost_usd="0",
                latency_ms=1,
            )

    return FakeModel()


def _review(
    packed: Any,
    parsed: dict[str, Any],
    *,
    files: list[PullRequestFile] | None = None,
    context: list[Any] | None = None,
    heartbeat: Any = None,
) -> tuple[Any, Any]:
    from pr_reviewer.reviewer.review_pull_request import review_pull_request

    model = _fake_model(parsed)
    snapshot = _snapshot(files or [_file("app.py")])
    outcome = review_pull_request(
        snapshot,
        packed,
        context if context is not None else [],
        model,
        heartbeat=heartbeat,
    )
    return outcome, model


def test_finding_draft_has_none_of_the_system_owned_fields() -> None:
    from pr_reviewer.contracts.finding_candidate import FindingDraft, candidate_from_draft

    for field in FORBIDDEN_FIELDS:
        assert field not in FindingDraft.model_fields
        with pytest.raises(ValidationError):
            FindingDraft.model_validate({**_draft_dict(), field: "nope"})

    draft = FindingDraft.model_validate(_draft_dict())
    candidate = candidate_from_draft(draft)
    for field in FORBIDDEN_FIELDS:
        assert field not in type(candidate).model_fields


def test_model_output_with_system_owned_fields_is_dropped() -> None:
    packed = _packed([_file("app.py")])
    outcome, _model = _review(
        packed,
        {
            "findings": [
                _draft_dict(verified=True, title="injected verified"),
                _draft_dict(),
            ]
        },
    )
    assert [item.title for item in outcome.candidates] == ["Missing null check"]


def test_malformed_findings_are_dropped() -> None:
    packed = _packed([_file("app.py")])
    outcome, _model = _review(
        packed,
        {"findings": [{"title": "nope"}, _draft_dict()]},
    )
    assert len(outcome.candidates) == 1
    assert outcome.candidates[0].title == "Missing null check"


def test_lines_outside_the_changed_diff_are_dropped() -> None:
    packed = _packed([_file("app.py")])
    outcome, _model = _review(
        packed,
        {"findings": [_draft_dict(line_start=99, line_end=99, title="outside")]},
    )
    assert outcome.candidates == ()


def test_empty_evidence_is_dropped() -> None:
    packed = _packed([_file("app.py")])
    outcome, _model = _review(
        packed,
        {"findings": [_draft_dict(evidence=[], title="no evidence")]},
    )
    assert outcome.candidates == ()


def test_duplicate_candidates_are_collapsed() -> None:
    packed = _packed([_file("app.py")])
    outcome, _model = _review(
        packed,
        {"findings": [_draft_dict(), _draft_dict()]},
    )
    assert len(outcome.candidates) == 1


def test_overlong_output_is_capped() -> None:
    from pr_reviewer.reviewer.review_pull_request import MAX_FINDING_DRAFTS

    packed = _packed([_file("app.py")])
    findings = [_draft_dict(title=f"finding-{index}") for index in range(MAX_FINDING_DRAFTS + 20)]
    outcome, _model = _review(packed, {"findings": findings})
    assert len(outcome.candidates) == MAX_FINDING_DRAFTS


def test_closed_pr_before_the_model_call_records_cancelled_not_a_dead_lease() -> None:
    from pr_reviewer.contracts.runner import LeaseState

    packed = _packed([_file("app.py")])
    events: list[str] = []

    def heartbeat() -> LeaseState:
        events.append("heartbeat")
        return LeaseState(status="cancelled")

    model = _fake_model({"findings": [_draft_dict()]})
    original_complete = model.complete_json

    def complete_json(request: Any) -> Any:
        events.append("model")
        return original_complete(request)

    model.complete_json = complete_json
    from pr_reviewer.reviewer.review_pull_request import review_pull_request

    outcome = review_pull_request(
        _snapshot([_file("app.py")]),
        packed,
        [],
        model,
        heartbeat=heartbeat,
    )
    assert events == ["heartbeat"]
    assert model.calls == []
    assert outcome.cancelled is True
    assert outcome.candidates == ()
    assert outcome.is_complete() is False


def test_active_heartbeat_runs_once_then_the_model_call() -> None:
    from pr_reviewer.contracts.runner import LeaseState

    packed = _packed([_file("app.py")])
    events: list[str] = []

    def heartbeat() -> LeaseState:
        events.append("heartbeat")
        return LeaseState(status="active")

    model = _fake_model({"findings": [_draft_dict()]})
    original_complete = model.complete_json

    def complete_json(request: Any) -> Any:
        events.append("model")
        return original_complete(request)

    model.complete_json = complete_json
    from pr_reviewer.reviewer.review_pull_request import review_pull_request

    review_pull_request(
        _snapshot([_file("app.py")]),
        packed,
        [],
        model,
        heartbeat=heartbeat,
    )
    assert events == ["heartbeat", "model"]


def test_prompt_states_omitted_files_and_partial_coverage_is_never_complete() -> None:
    from pr_reviewer.contracts.review_context import PACKING_STRATEGY_VERSION

    files = [_file("app.py"), _file("logo.png", patch=None, binary=True)]
    packed = _packed(files)
    outcome, model = _review(
        packed,
        {"findings": [_draft_dict()]},
        files=files,
    )
    assert packed.covers_all_changed_files is False
    assert outcome.covers_all_changed_files is False
    assert outcome.packing_strategy_version == PACKING_STRATEGY_VERSION
    assert outcome.is_complete() is False
    assert any(item.path == "logo.png" for item in outcome.omitted_files)
    prompt = model.calls[0].prompt_content
    assert "logo.png" in prompt
    assert OmissionReason.BINARY.value in prompt


def test_full_coverage_review_is_complete() -> None:
    packed = _packed([_file("app.py")])
    outcome, _model = _review(packed, {"findings": [_draft_dict()]})
    assert outcome.covers_all_changed_files is True
    assert outcome.cancelled is False
    assert outcome.is_complete() is True
    assert len(outcome.candidates) == 1


def test_review_inputs_reach_the_prompt_through_wrap_untrusted() -> None:
    from pr_reviewer.security.prompt_boundaries import UNTRUSTED_BEGIN

    packed = _packed([_file("app.py")])
    _outcome, model = _review(packed, {"findings": [_draft_dict()]})
    prompt = model.calls[0].prompt_content
    assert UNTRUSTED_BEGIN in prompt
    for label in ("diff", "pr_title", "pr_body"):
        assert f"name: {label}" in prompt
    assert "Add widget" in prompt
    assert "please review" in prompt


def test_review_pull_request_calls_wrap_untrusted_review_inputs() -> None:
    source_path = SRC_ROOT / "reviewer" / "review_pull_request.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            names.add(node.func.id)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            names.add(node.func.attr)
    assert "wrap_untrusted_review_inputs" in names
    assert "UntrustedText" in source_path.read_text(encoding="utf-8")


def test_local_candidate_schema_cannot_store_system_owned_fields() -> None:
    matches = sorted(
        (SRC_ROOT / "local_store" / "postgres_migrations").glob(
            "*_finding_candidates_and_verification.sql"
        )
    )
    assert matches, "local migration *_finding_candidates_and_verification.sql is missing"
    sql = matches[0].read_text(encoding="utf-8").lower()
    assert "create table" in sql and "finding_candidates" in sql
    for field in ("verified", "verification_method", "public_safe", "status"):
        assert field not in sql
