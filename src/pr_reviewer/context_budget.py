"""Token windows for packing. This module must not import settings or secrets."""

from __future__ import annotations

from pr_reviewer.contracts.review_context import ContextBudget

# (context_window, output_allowance). The packer only ever sees window minus allowance.
MODEL_CONTEXT_WINDOWS: dict[str, tuple[int, int]] = {
    "gpt-4o-mini": (128_000, 16_384),
    "claude-3-5-haiku-latest": (200_000, 8_192),
}


def context_budget_for_model(model: str) -> ContextBudget:
    try:
        context_window, output_allowance = MODEL_CONTEXT_WINDOWS[model]
    except KeyError as exc:
        raise KeyError(model) from exc
    return ContextBudget.from_window(context_window, output_allowance)
