"""Failing tests for reciprocal rank fusion (master Task 13).

k defaults to 60. Ties are deterministic. Imports of new modules stay inside
test bodies.
"""

from __future__ import annotations


def test_rrf_default_k_is_sixty() -> None:
    import inspect

    from pr_reviewer.retrieval.rrf import reciprocal_rank_fusion

    assert inspect.signature(reciprocal_rank_fusion).parameters["k"].default == 60


def test_rrf_prefers_items_ranked_high_in_both_lists() -> None:
    from pr_reviewer.retrieval.rrf import reciprocal_rank_fusion

    fused = reciprocal_rank_fusion(
        [
            ["shared", "only-vector"],
            ["shared", "only-text"],
        ]
    )
    assert fused[0] == "shared"
    assert set(fused) == {"shared", "only-vector", "only-text"}


def test_rrf_rank_ties_are_deterministic() -> None:
    from pr_reviewer.retrieval.rrf import reciprocal_rank_fusion

    fused = reciprocal_rank_fusion([["alpha", "beta"], ["beta", "alpha"]])
    assert fused == ["alpha", "beta"]
    again = reciprocal_rank_fusion([["alpha", "beta"], ["beta", "alpha"]])
    assert again == fused
