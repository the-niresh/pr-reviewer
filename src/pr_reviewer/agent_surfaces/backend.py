"""The one concrete AgentReviewBackend: a live, synchronous, diff-only review.

Every agent surface (cli_json, mcp_server, a2a, acp) is driven by an AgentReviewBackend Protocol
(core.py), so any of them can be tested against a fake. This module is the real implementation
they share when actually invoked -- `reviewer review`, `reviewer mcp`, `reviewer a2a` and
`reviewer acp` all construct one of these, never a second competing implementation.

It never touches the hosted database or control plane, and it never imports pr_reviewer.cli (the
operator package): it only ever calls GitHub with a token the caller already holds
(PR_REVIEWER_GITHUB_TOKEN) and the user's own model provider key (ANTHROPIC_API_KEY or
OPENAI_API_KEY), matching the product's hard rule that source, diffs and keys never cross to the
hosted plane. It reuses the same diff packer and diff-only reviewer the rest of the runner uses
(reviewer.diff_budget.pack_diff, reviewer.review_pull_request.review_pull_request) rather than
building a second review pipeline.
"""

from __future__ import annotations

import os
import uuid

from pr_reviewer.agent_surfaces.core import (
    AgentReviewRequest,
    AgentSurfaceRefusal,
    GitHubConnectionState,
    RemediationPrompt,
    SurfaceFinding,
    SurfaceReview,
    remediation_prompt_for_finding,
)
from pr_reviewer.contracts.github import PullRequestRef
from pr_reviewer.contracts.review_context import ContextBudget
from pr_reviewer.github.pull_request import fetch_pull_request
from pr_reviewer.models.anthropic_provider import AnthropicProvider
from pr_reviewer.models.openai_provider import OpenAIProvider
from pr_reviewer.models.provider import ModelProvider
from pr_reviewer.models.providers import ProviderName
from pr_reviewer.reviewer.diff_budget import pack_diff
from pr_reviewer.reviewer.review_pull_request import review_pull_request

GITHUB_TOKEN_ENV = "PR_REVIEWER_GITHUB_TOKEN"
ANTHROPIC_KEY_ENV = "ANTHROPIC_API_KEY"
OPENAI_KEY_ENV = "OPENAI_API_KEY"

# ponytail: a plain 4-chars-per-token heuristic, not a real tokenizer. This only decides how much
# diff the packer includes before the same budget the model itself will enforce; swap for a real
# tokenizer (tiktoken) if packing gets measurably too eager or too conservative.
DEFAULT_CONTEXT_WINDOW = 128_000
DEFAULT_OUTPUT_ALLOWANCE = 4_000


class _StaticTokenProvider:
    """Hands back one token regardless of installation_id.

    fetch_pull_request is written for the hosted GitHub App flow (installation_id ->
    token_provider.create_installation_token(installation_id)). A CLI-triggered review has no
    installation and no token broker -- just the token the caller already put in the environment
    -- so this adapter satisfies the same Protocol without pretending to mint anything.
    """

    def __init__(self, token: str) -> None:
        self._token = token

    def create_installation_token(self, installation_id: int) -> str:
        del installation_id
        return self._token


def resolve_model_provider() -> tuple[ProviderName, ModelProvider] | None:
    anthropic_key = os.environ.get(ANTHROPIC_KEY_ENV)
    if anthropic_key:
        return "anthropic", AnthropicProvider(anthropic_key)
    openai_key = os.environ.get(OPENAI_KEY_ENV)
    if openai_key:
        return "openai", OpenAIProvider(openai_key)
    return None


def _count_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class LiveAgentReviewBackend:
    """Fetches one real PR diff over the network and runs the diff-only reviewer against it."""

    def __init__(self) -> None:
        self._reviews: dict[str, SurfaceReview] = {}

    def github_connection_state(self) -> GitHubConnectionState:
        if not os.environ.get(GITHUB_TOKEN_ENV):
            return GitHubConnectionState(
                connected=False,
                reason=f"{GITHUB_TOKEN_ENV} is not set.",
            )
        return GitHubConnectionState(connected=True)

    def start_review(self, request: AgentReviewRequest) -> SurfaceReview:
        provider_choice = resolve_model_provider()
        if provider_choice is None:
            raise AgentSurfaceRefusal(
                "no_model_key",
                f"Set {ANTHROPIC_KEY_ENV} or {OPENAI_KEY_ENV} before requesting a review.",
            )
        provider_name, model = provider_choice
        del provider_name

        token = os.environ[GITHUB_TOKEN_ENV]
        snapshot = fetch_pull_request(
            PullRequestRef(
                owner=request.owner,
                repository=request.repository,
                number=request.pull_request,
            ),
            installation_id=0,
            token_provider=_StaticTokenProvider(token),
        )

        budget = ContextBudget.from_window(DEFAULT_CONTEXT_WINDOW, DEFAULT_OUTPUT_ALLOWANCE)
        packed = pack_diff(snapshot, budget, _count_tokens)

        outcome = review_pull_request(snapshot, packed, [], model)

        findings = tuple(
            SurfaceFinding(
                id=str(uuid.uuid4()),
                concern=candidate.concern,
                severity=candidate.severity,
                category=candidate.category,
                file_path=candidate.file_path,
                line_start=candidate.line_start,
                line_end=candidate.line_end,
                title=candidate.title,
                rationale=candidate.rationale,
                evidence=tuple(candidate.evidence),
                confidence=candidate.confidence,
                verified=False,
            )
            for candidate in outcome.candidates
        )
        review = SurfaceReview(
            review_id=str(uuid.uuid4()),
            owner=request.owner,
            repository=request.repository,
            pull_request=request.pull_request,
            head_sha=snapshot.head_sha,
            status="cancelled" if outcome.cancelled else "complete",
            findings=findings,
            remediation_prompts=tuple(remediation_prompt_for_finding(f) for f in findings),
        )
        self._reviews[review.review_id] = review
        return review

    def list_findings(self, review_id: str) -> tuple[SurfaceFinding, ...]:
        return self._existing_review(review_id).findings

    def list_remediation_prompts(self, review_id: str) -> tuple[RemediationPrompt, ...]:
        return self._existing_review(review_id).remediation_prompts

    def _existing_review(self, review_id: str) -> SurfaceReview:
        review = self._reviews.get(review_id)
        if review is None:
            raise AgentSurfaceRefusal(
                "unknown_review",
                f"No review found for id {review_id!r}. Run a review first.",
            )
        return review
