"""Whole-file diff packing. Output allowance is not visible to this function."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Mapping, Set

from pr_reviewer.contracts.github import OmissionReason
from pr_reviewer.contracts.review_context import (
    PACKING_STRATEGY_VERSION,
    ContextBudget,
    FilePatch,
    OmittedFile,
    PackedDiff,
    ReviewContextItem,
    ReviewResult,
)
from pr_reviewer.github.pull_request import PullRequestFile, PullRequestSnapshot
from pr_reviewer.reviewer.hunk_format import render_hunks

TokenCounter = Callable[[str], int]
_NEW_LINE = re.compile(r"^(\d+)\| ")


def pack_diff(
    snapshot: PullRequestSnapshot,
    budget: ContextBudget,
    count_tokens: TokenCounter,
    *,
    sensitivity: Mapping[str, float] | None = None,
    generated_paths: Set[str] | None = None,
    ignored_paths: Set[str] | None = None,
) -> PackedDiff:
    ordered = sorted(
        snapshot.files,
        key=lambda file: _sort_key(file, sensitivity),
    )
    remaining = budget.tokens
    items: list[ReviewContextItem] = []
    included: list[str] = []
    omitted: list[OmittedFile] = []
    for file in ordered:
        reason = _classify(file, generated_paths, ignored_paths)
        size = change_size(file.patch)
        if reason is not None:
            omitted.append(OmittedFile(path=file.path, reason=reason, change_size=size))
            continue
        assert file.patch is not None
        content = render_hunks(
            FilePatch(path=file.path, patch=file.patch, previous_path=file.previous_path)
        )
        tokens = count_tokens(content)
        if tokens > remaining:
            omitted.append(
                OmittedFile(path=file.path, reason=OmissionReason.TOKEN_BUDGET, change_size=size)
            )
            continue
        remaining -= tokens
        line_start, line_end = _line_range(content)
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        items.append(
            ReviewContextItem(
                source_kind="diff_file",
                file_path=file.path,
                line_start=line_start,
                line_end=line_end,
                content=content,
                content_hash=digest,
            )
        )
        included.append(file.path)
    return PackedDiff(
        packing_strategy_version=PACKING_STRATEGY_VERSION,
        items=tuple(items),
        included_files=tuple(included),
        omitted_files=tuple(omitted),
        prompt_tokens=sum(count_tokens(item.content) for item in items),
        covers_all_changed_files=not omitted,
    )


def change_size(patch: str | None) -> int:
    if not patch:
        return 0
    count = 0
    for line in patch.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+") or line.startswith("-"):
            count += 1
    return count


def omission_prompt_section(packed: PackedDiff) -> str:
    lines = ["Omitted files:"]
    lines.extend(f"{item.path}: {item.reason.value}" for item in packed.omitted_files)
    return "\n".join(lines)


def omission_event_payloads(packed: PackedDiff) -> list[dict[str, str | int]]:
    return [
        {"path": item.path, "reason": item.reason.value, "change_size": item.change_size}
        for item in packed.omitted_files
    ]


def review_result_from_packed(packed: PackedDiff) -> ReviewResult:
    return ReviewResult(
        omitted_files=packed.omitted_files,
        covers_all_changed_files=packed.covers_all_changed_files,
    )


def _sort_key(
    file: PullRequestFile,
    sensitivity: Mapping[str, float] | None,
) -> tuple[float, int, str]:
    score = 0.0 if sensitivity is None else float(sensitivity.get(file.path, 0.0))
    return (-score, -change_size(file.patch), file.path)


def _classify(
    file: PullRequestFile,
    generated_paths: Set[str] | None,
    ignored_paths: Set[str] | None,
) -> OmissionReason | None:
    if file.omission_reason is not None:
        return file.omission_reason
    if file.binary:
        return OmissionReason.BINARY
    if generated_paths is not None and file.path in generated_paths:
        return OmissionReason.GENERATED
    if ignored_paths is not None and file.path in ignored_paths:
        return OmissionReason.IGNORED_PATH
    if file.truncated:
        return OmissionReason.PATCH_TRUNCATED_BY_GITHUB
    if not file.patch:
        return OmissionReason.PATCH_OMITTED_BY_GITHUB
    return None


def _line_range(content: str) -> tuple[int, int]:
    in_new = False
    collected: list[int] = []
    for line in content.splitlines():
        if line.startswith("NEW "):
            in_new = True
            continue
        if line.startswith("OLD "):
            in_new = False
            continue
        if not in_new:
            continue
        match = _NEW_LINE.match(line)
        if match is not None:
            collected.append(int(match.group(1)))
    if not collected:
        return 0, 0
    return collected[0], collected[-1]
