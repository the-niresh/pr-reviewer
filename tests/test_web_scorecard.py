"""Task 31.2: the public scorecard page reads generated, never-hand-edited artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from pr_reviewer.contracts.finding_candidate import FindingCandidate
from pr_reviewer.evals.feature_flags import generate_feature_flags
from pr_reviewer.evals.scorecard import generate_scorecard
from pr_reviewer.evals.types import EvalCase

REPO = Path(__file__).resolve().parent.parent
PAGE = REPO / "apps" / "web" / "src" / "app" / "scorecard" / "page.tsx"
SCORECARD_JSON = REPO / "docs" / "reports" / "scorecard.json"
FEATURE_FLAGS_JSON = REPO / "docs" / "reports" / "feature_flags.json"


def _unreachable_reviewer(_case: EvalCase) -> list[FindingCandidate]:
    raise AssertionError("reviewer called despite an empty holdout")


def test_scorecard_json_matches_a_fresh_real_generation() -> None:
    on_disk = json.loads(SCORECARD_JSON.read_text(encoding="utf-8"))
    fresh = generate_scorecard(_unreachable_reviewer).model_dump()
    assert on_disk == fresh


def test_feature_flags_json_matches_a_fresh_real_generation() -> None:
    on_disk = json.loads(FEATURE_FLAGS_JSON.read_text(encoding="utf-8"))
    fresh = [flag.model_dump() for flag in generate_feature_flags()]
    assert on_disk == fresh


def test_page_reads_the_generated_files_at_render_time() -> None:
    source = PAGE.read_text(encoding="utf-8")
    assert "docs/reports/scorecard.json" in source
    assert "docs/reports/feature_flags.json" in source
    assert "readFileSync" in source


def test_page_never_hides_a_refusal_behind_a_placeholder() -> None:
    source = PAGE.read_text(encoding="utf-8")
    for placeholder in ("N/A", "TBD", "Coming soon", "--"):
        assert placeholder not in source, f"found placeholder text {placeholder!r} in the page"
