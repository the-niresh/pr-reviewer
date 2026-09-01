"""Deterministic merge of specialist findings.

The merge key is repository, head SHA, file, overlapping lines, and a
normalised category. Order never comes from dict or set iteration.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pr_reviewer.contracts.finding_candidate import FindingCandidate

_SEVERITY_RANK = {
    "info": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}


def normalise_category(value: str) -> str:
    return "-".join(value.casefold().replace("_", "-").split())


def _cluster_overlaps(item: FindingCandidate, cluster: list[FindingCandidate]) -> bool:
    start = min(member.line_start for member in cluster)
    end = max(member.line_end for member in cluster)
    return item.line_start <= end and start <= item.line_end


def _sort_key(item: FindingCandidate, *, repository: str, head_sha: str) -> tuple[str, ...]:
    return (
        repository,
        head_sha,
        item.file_path,
        normalise_category(item.category),
        f"{item.line_start:010d}",
        f"{item.line_end:010d}",
        item.title,
        item.rationale,
    )


def _pick_representative(cluster: list[FindingCandidate]) -> FindingCandidate:
    return max(
        cluster,
        key=lambda item: (
            _SEVERITY_RANK[item.severity],
            item.title,
            item.rationale,
        ),
    )


def aggregate_findings(
    findings: Sequence[FindingCandidate],
    *,
    repository: str,
    head_sha: str,
    forbidden_paths: set[str] | None = None,
    forbidden_map: Mapping[str, str] | None = None,
) -> tuple[FindingCandidate, ...]:
    del forbidden_paths, forbidden_map
    ordered = sorted(
        findings,
        key=lambda item: _sort_key(item, repository=repository, head_sha=head_sha),
    )
    clusters: list[list[FindingCandidate]] = []
    for item in ordered:
        placed = False
        for cluster in clusters:
            head = cluster[0]
            same_key = (
                item.file_path == head.file_path
                and normalise_category(item.category) == normalise_category(head.category)
            )
            if same_key and _cluster_overlaps(item, cluster):
                cluster.append(item)
                placed = True
                break
        if not placed:
            clusters.append([item])

    merged: list[FindingCandidate] = []
    for cluster in clusters:
        pick = _pick_representative(cluster)
        evidence = tuple(sorted({entry for member in cluster for entry in member.evidence}))
        merged.append(
            pick.model_copy(
                update={
                    "line_start": min(member.line_start for member in cluster),
                    "line_end": max(member.line_end for member in cluster),
                    "evidence": list(evidence),
                }
            )
        )
    return tuple(merged)
