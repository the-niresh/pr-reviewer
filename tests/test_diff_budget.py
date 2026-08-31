"""Failing tests for diff budgeting and omission reporting (master Task 10A).

The packing unit is the whole file. Output allowance is reserved off the top.
Every changed file is included or omitted with a closed-set reason. Imports of
new modules stay inside test bodies.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from pr_reviewer.contracts.github import OmissionReason
from pr_reviewer.github.pull_request import PullRequestFile, PullRequestSnapshot

SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "pr_reviewer"
BASE_SHA = "a" * 40
HEAD_SHA = "b" * 40
SMALL_PATCH = "@@ -1,1 +1,1 @@\n-old\n+new\n"
TWO_HUNK_PATCH = (
    "@@ -1,1 +1,2 @@\n"
    " alpha\n"
    "+beta\n"
    "@@ -10,1 +11,2 @@\n"
    " omega\n"
    "+zeta\n"
)


class _NoIterateMap(dict[str, float]):
    def __iter__(self) -> Iterator[str]:
        raise AssertionError("do not iterate the sensitivity map to decide order")


class _NoIterateSet(set[str]):
    def __iter__(self) -> Iterator[str]:
        raise AssertionError("do not iterate path sets to decide order")


def _snapshot(files: list[PullRequestFile]) -> PullRequestSnapshot:
    return PullRequestSnapshot(
        repo_owner="acme",
        repo_name="widgets",
        number=12,
        base_sha=BASE_SHA,
        head_sha=HEAD_SHA,
        title="Add widget",
        body="",
        files=files,
    )


def _file(path: str, patch: str | None = SMALL_PATCH, **kwargs: object) -> PullRequestFile:
    fields: dict[str, object] = {"path": path, "status": "modified", "patch": patch}
    fields.update(kwargs)
    return PullRequestFile.model_validate(fields)


def _count_by_path(sizes: dict[str, int]) -> Callable[[str], int]:
    def count_tokens(text: str) -> int:
        for path, size in sizes.items():
            if f"NEW {path}" in text or path in text.splitlines()[0]:
                return size
        return 1

    return count_tokens


def test_under_budget_packs_every_changed_file() -> None:
    from pr_reviewer.contracts.review_context import ContextBudget
    from pr_reviewer.reviewer.diff_budget import pack_diff

    snapshot = _snapshot([_file("a.py"), _file("b.py")])
    packed = pack_diff(snapshot, ContextBudget(tokens=1000), lambda _text: 10)
    assert packed.covers_all_changed_files is True
    assert [item.file_path for item in packed.items] == ["a.py", "b.py"]
    assert packed.omitted_files == ()
    assert packed.included_files == ("a.py", "b.py")
    assert packed.prompt_tokens == 20


def test_over_budget_omits_whole_files_with_token_budget() -> None:
    from pr_reviewer.contracts.review_context import ContextBudget
    from pr_reviewer.reviewer.diff_budget import pack_diff

    snapshot = _snapshot([_file("a.py"), _file("b.py"), _file("c.py")])
    packed = pack_diff(
        snapshot,
        ContextBudget(tokens=15),
        _count_by_path({"a.py": 10, "b.py": 10, "c.py": 10}),
    )
    assert packed.covers_all_changed_files is False
    included = set(packed.included_files)
    omitted = {item.path: item.reason for item in packed.omitted_files}
    assert included | set(omitted) == {"a.py", "b.py", "c.py"}
    assert not (included & set(omitted))
    assert set(omitted.values()) == {OmissionReason.TOKEN_BUDGET}


def test_one_file_larger_than_the_budget_is_omitted_whole() -> None:
    from pr_reviewer.contracts.review_context import ContextBudget
    from pr_reviewer.reviewer.diff_budget import pack_diff

    snapshot = _snapshot([_file("huge.py"), _file("tiny.py")])
    packed = pack_diff(
        snapshot,
        ContextBudget(tokens=50),
        _count_by_path({"huge.py": 80, "tiny.py": 10}),
    )
    assert packed.included_files == ("tiny.py",)
    assert [(item.path, item.reason) for item in packed.omitted_files] == [
        ("huge.py", OmissionReason.TOKEN_BUDGET)
    ]
    assert all(item.file_path != "huge.py" for item in packed.items)


def test_zero_token_budget_omits_every_packable_file() -> None:
    from pr_reviewer.contracts.review_context import ContextBudget
    from pr_reviewer.reviewer.diff_budget import pack_diff

    snapshot = _snapshot([_file("a.py"), _file("b.py")])
    packed = pack_diff(snapshot, ContextBudget(tokens=0), lambda _text: 10)
    assert packed.items == ()
    assert packed.covers_all_changed_files is False
    assert {item.reason for item in packed.omitted_files} == {OmissionReason.TOKEN_BUDGET}


def test_binary_generated_ignored_and_renamed_files() -> None:
    from pr_reviewer.contracts.review_context import ContextBudget
    from pr_reviewer.reviewer.diff_budget import pack_diff

    snapshot = _snapshot(
        [
            _file("logo.png", patch=None, binary=True),
            _file("dist/app.js"),
            _file("tmp/cache.dat"),
            _file(
                "new.py",
                status="renamed",
                previous_path="old.py",
            ),
        ]
    )
    packed = pack_diff(
        snapshot,
        ContextBudget(tokens=1000),
        lambda _text: 10,
        generated_paths=_NoIterateSet({"dist/app.js"}),
        ignored_paths=_NoIterateSet({"tmp/cache.dat"}),
    )
    by_path = {item.path: item.reason for item in packed.omitted_files}
    assert by_path["logo.png"] == OmissionReason.BINARY
    assert by_path["dist/app.js"] == OmissionReason.GENERATED
    assert by_path["tmp/cache.dat"] == OmissionReason.IGNORED_PATH
    assert packed.included_files == ("new.py",)
    assert packed.items[0].file_path == "new.py"
    assert "old.py" in packed.items[0].content


def test_never_drops_a_changed_file_silently() -> None:
    from pr_reviewer.contracts.review_context import ContextBudget
    from pr_reviewer.reviewer.diff_budget import pack_diff

    snapshot = _snapshot(
        [
            _file("kept.py"),
            _file("missing.py", patch=None, omission_reason=OmissionReason.PATCH_OMITTED_BY_GITHUB),
            _file("huge.py"),
        ]
    )
    packed = pack_diff(
        snapshot,
        ContextBudget(tokens=10),
        _count_by_path({"kept.py": 10, "huge.py": 50, "missing.py": 10}),
    )
    accounted = set(packed.included_files) | {item.path for item in packed.omitted_files}
    assert accounted == {"kept.py", "missing.py", "huge.py"}


def test_github_omission_keeps_a_different_reason_from_budget() -> None:
    from pr_reviewer.contracts.review_context import ContextBudget
    from pr_reviewer.reviewer.diff_budget import pack_diff

    snapshot = _snapshot(
        [
            _file(
                "missing.py",
                patch=None,
                omission_reason=OmissionReason.PATCH_OMITTED_BY_GITHUB,
            ),
            _file("huge.py"),
        ]
    )
    packed = pack_diff(
        snapshot,
        ContextBudget(tokens=5),
        _count_by_path({"huge.py": 50, "missing.py": 1}),
    )
    by_path = {item.path: item.reason for item in packed.omitted_files}
    assert by_path["missing.py"] == OmissionReason.PATCH_OMITTED_BY_GITHUB
    assert by_path["huge.py"] == OmissionReason.TOKEN_BUDGET


def test_packing_is_deterministic_across_repeated_runs() -> None:
    from pr_reviewer.contracts.review_context import ContextBudget
    from pr_reviewer.reviewer.diff_budget import pack_diff

    snapshot = _snapshot([_file("z.py"), _file("a.py"), _file("m.py")])
    budget = ContextBudget(tokens=20)
    count = _count_by_path({"z.py": 10, "a.py": 10, "m.py": 10})
    first = pack_diff(snapshot, budget, count)
    for _ in range(7):
        packed = pack_diff(snapshot, budget, count)
        assert [item.file_path for item in packed.items] == [
            item.file_path for item in first.items
        ]
        assert [(item.path, item.reason) for item in packed.omitted_files] == [
            (item.path, item.reason) for item in first.omitted_files
        ]


def test_ordering_is_sensitivity_then_change_size_then_path() -> None:
    from pr_reviewer.contracts.review_context import PACKING_STRATEGY_VERSION, ContextBudget
    from pr_reviewer.reviewer.diff_budget import pack_diff

    small = "@@ -1,1 +1,1 @@\n-a\n+b\n"
    medium = "@@ -1,2 +1,2 @@\n-a\n-b\n+c\n+d\n"
    snapshot = _snapshot(
        [
            _file("z.py", patch=medium),
            _file("a.py", patch=medium),
            _file("m.py", patch=small),
        ]
    )
    packed = pack_diff(
        snapshot,
        ContextBudget(tokens=1000),
        lambda _text: 10,
        sensitivity=_NoIterateMap({"m.py": 9.0, "z.py": 1.0, "a.py": 1.0}),
    )
    assert packed.packing_strategy_version == PACKING_STRATEGY_VERSION
    assert packed.packing_strategy_version == "v1-sensitivity-desc-change-size-desc-path-asc"
    assert [item.file_path for item in packed.items] == ["m.py", "a.py", "z.py"]


def test_high_sensitivity_file_resists_eviction() -> None:
    from pr_reviewer.contracts.review_context import ContextBudget
    from pr_reviewer.reviewer.diff_budget import pack_diff

    snapshot = _snapshot([_file("boring.py"), _file("danger.py")])
    packed = pack_diff(
        snapshot,
        ContextBudget(tokens=10),
        _count_by_path({"boring.py": 10, "danger.py": 10}),
        sensitivity=_NoIterateMap({"danger.py": 5.0, "boring.py": 0.0}),
    )
    assert packed.included_files == ("danger.py",)
    assert packed.omitted_files[0].path == "boring.py"
    assert packed.omitted_files[0].reason == OmissionReason.TOKEN_BUDGET


def test_whole_file_is_included_or_omitted_never_half() -> None:
    from pr_reviewer.contracts.review_context import ContextBudget
    from pr_reviewer.reviewer.diff_budget import pack_diff

    snapshot = _snapshot([_file("mod.py", patch=TWO_HUNK_PATCH)])
    full = pack_diff(snapshot, ContextBudget(tokens=50), lambda _text: 50)
    assert full.covers_all_changed_files is True
    assert "alpha" in full.items[0].content
    assert "zeta" in full.items[0].content
    omitted = pack_diff(snapshot, ContextBudget(tokens=49), lambda _text: 50)
    assert omitted.items == ()
    assert omitted.omitted_files[0].reason == OmissionReason.TOKEN_BUDGET


def test_output_allowance_is_reserved_off_the_top() -> None:
    from pr_reviewer.contracts.review_context import ContextBudget
    from pr_reviewer.reviewer.diff_budget import pack_diff

    budget = ContextBudget.from_window(context_window=100, output_allowance=40)
    assert budget.tokens == 60
    assert "context_window" not in ContextBudget.model_fields
    assert "output_allowance" not in ContextBudget.model_fields
    snapshot = _snapshot([_file("app.py")])
    packed = pack_diff(snapshot, budget, lambda _text: 70)
    assert packed.omitted_files[0].reason == OmissionReason.TOKEN_BUDGET
    assert packed.items == ()


def test_default_context_budget_per_model() -> None:
    from pr_reviewer.context_budget import context_budget_for_model
    from pr_reviewer.contracts.review_context import ContextBudget

    mini = context_budget_for_model("gpt-4o-mini")
    haiku = context_budget_for_model("claude-3-5-haiku-latest")
    assert mini == ContextBudget.from_window(128_000, 16_384)
    assert haiku == ContextBudget.from_window(200_000, 8_192)
    assert mini.tokens == 128_000 - 16_384
    with pytest.raises((KeyError, ValueError)):
        context_budget_for_model("unknown-model")


def test_omission_list_reaches_prompt_events_and_review_result() -> None:
    from test_events_and_models import create_review_job

    from pr_reviewer.contracts.review_context import ContextBudget
    from pr_reviewer.events.list_events_for_job import list_events_for_job
    from pr_reviewer.events.record_event import JsonObject, record_event, serialize_json_object
    from pr_reviewer.reviewer.diff_budget import (
        omission_event_payloads,
        omission_prompt_section,
        pack_diff,
        review_result_from_packed,
    )

    snapshot = _snapshot(
        [
            _file("kept.py"),
            _file("logo.png", patch=None, binary=True),
            _file(
                "missing.py",
                patch=None,
                omission_reason=OmissionReason.PATCH_OMITTED_BY_GITHUB,
            ),
        ]
    )
    packed = pack_diff(snapshot, ContextBudget(tokens=10), lambda _text: 10)
    prompt = omission_prompt_section(packed)
    assert "logo.png" in prompt
    assert "missing.py" in prompt
    assert OmissionReason.BINARY.value in prompt
    assert OmissionReason.PATCH_OMITTED_BY_GITHUB.value in prompt

    payloads = omission_event_payloads(packed)
    assert {item["path"] for item in payloads} == {"logo.png", "missing.py"}
    for payload in payloads:
        flat: JsonObject = {
            "path": str(payload["path"]),
            "reason": str(payload["reason"]),
            "change_size": int(payload["change_size"]),
        }
        serialize_json_object(flat)

    result = review_result_from_packed(packed)
    assert result.omitted_files == packed.omitted_files
    assert result.covers_all_changed_files is False

    job_id = create_review_job()
    for payload in payloads:
        event_payload: JsonObject = {
            "path": str(payload["path"]),
            "reason": str(payload["reason"]),
            "change_size": int(payload["change_size"]),
        }
        record_event(job_id, "diff_file_omitted", event_payload)
    events = list_events_for_job(job_id)
    omitted_events = [item for item in events if item.event_type == "diff_file_omitted"]
    assert {item.payload["path"] for item in omitted_events} == {"logo.png", "missing.py"}


def test_omission_reason_is_reused_not_redefined() -> None:
    source = (SRC_ROOT / "contracts" / "review_context.py").read_text(encoding="utf-8")
    assert "class OmissionReason" not in source
    from pr_reviewer.contracts.github import OmissionReason as GithubReason
    from pr_reviewer.contracts.review_context import OmittedFile

    omitted = OmittedFile(path="a.py", reason=GithubReason.TOKEN_BUDGET, change_size=4)
    assert omitted.reason is GithubReason.TOKEN_BUDGET


def test_omitted_file_records_change_size() -> None:
    from pr_reviewer.contracts.review_context import ContextBudget
    from pr_reviewer.reviewer.diff_budget import pack_diff

    patch = "@@ -1,3 +1,1 @@\n-a\n-b\n-c\n+d\n"
    packed = pack_diff(
        _snapshot([_file("a.py", patch=patch)]),
        ContextBudget(tokens=0),
        lambda _text: 10,
    )
    assert packed.omitted_files[0].change_size == 4
