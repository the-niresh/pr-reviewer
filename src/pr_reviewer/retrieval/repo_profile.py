"""Inferred repository profile. Never merged with asserted instruction files."""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, Protocol
from uuid import uuid4

from psycopg import Connection
from pydantic import BaseModel, ConfigDict, Field

from pr_reviewer.security.instruction_sources import (
    InstructionApplication,
    InstructionSource,
    PromptBlock,
    ReviewPolicy,
    instruction_prompt_block,
)

PROFILE_BLOCK_WEIGHT: Literal["inferred"] = "inferred"
PROFILE_PROMPT_VERSION = "repo-profile-v1"
PROFILE_POLICY_WINDOW = timedelta(days=14)
_RECENCY_LAMBDA = 0.05
_MIN_GENERATION_TOKENS = 32


class ProfileStale(Exception):
    """The profile is older than the policy window and must not be used."""


class ProfileBudgetExceeded(Exception):
    """Profile generation would charge the wrong budget or exceed it."""


@dataclass(frozen=True)
class ProfileBudget:
    tokens: int
    scope: Literal["repository", "pull_request"] = "repository"


class ProfileModel(Protocol):
    def generate_claims(self, corpus: str) -> list[dict[str, str]]: ...


class ProfileClaim(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str = Field(min_length=1)
    text: str = Field(min_length=1)
    supporting_paths: tuple[str, ...] = ()
    status: Literal["candidate", "promoted"]


class RepoProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    repository_id: int
    commit_sha: str = Field(min_length=40, max_length=40)
    model: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    generated_at: datetime
    content_hash: str = Field(min_length=64, max_length=64)
    claims: tuple[ProfileClaim, ...]


def apply_profile(policy: ReviewPolicy, profile: RepoProfile) -> InstructionApplication:
    focus = "\n".join(claim.text for claim in profile.claims)
    return InstructionApplication(policy=policy, focus_text=focus)


def assemble_prompt_blocks(
    instructions: Sequence[InstructionSource],
    profile: RepoProfile,
) -> tuple[PromptBlock, PromptBlock]:
    asserted = instruction_prompt_block(instructions)
    inferred = PromptBlock(
        weight=PROFILE_BLOCK_WEIGHT,
        texts=tuple(claim.text for claim in profile.claims),
    )
    return asserted, inferred


def apply_claim_write(
    existing: Sequence[ProfileClaim],
    incoming: ProfileClaim,
    *,
    decide: Callable[[Sequence[ProfileClaim], ProfileClaim], str],
) -> tuple[ProfileClaim, ...]:
    action = decide(existing, incoming)
    if action == "ADD":
        return tuple(existing) + (incoming,)
    if action == "NOOP":
        return tuple(existing)
    if action == "UPDATE":
        if not existing:
            return (incoming,)
        return (incoming,) + tuple(existing[1:])
    if action == "REPLACE":
        return (incoming,)
    raise ValueError(f"unknown claim write action {action!r}")


def promote_claim(claim: ProfileClaim) -> ProfileClaim:
    return claim.model_copy(update={"status": "promoted"})


def generate_repo_profile(
    repo_path: Path,
    model: ProfileModel,
    budget: ProfileBudget,
    *,
    repository_id: int,
    record_profile: Callable[[dict[str, object]], None] | None = None,
    now: datetime | None = None,
) -> RepoProfile:
    if budget.scope != "repository":
        raise ProfileBudgetExceeded("profile generation is charged to the repository budget")
    if budget.tokens < _MIN_GENERATION_TOKENS:
        raise ProfileBudgetExceeded(
            f"repository profile budget {budget.tokens} is below {_MIN_GENERATION_TOKENS}"
        )
    generated_at = now or datetime.now(tz=UTC)
    commit_sha = _head_sha(repo_path)
    drafts = model.generate_claims(_corpus_excerpt(repo_path))
    claims = tuple(_candidate_claim(draft) for draft in drafts)
    canonical = json.dumps(
        [claim.model_dump() for claim in claims],
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    model_name = str(getattr(model, "model_name", None) or type(model).__name__)
    profile = RepoProfile(
        repository_id=repository_id,
        commit_sha=commit_sha,
        model=model_name,
        prompt_version=PROFILE_PROMPT_VERSION,
        generated_at=generated_at,
        content_hash=digest,
        claims=claims,
    )
    if record_profile is not None:
        record_profile(
            {
                "repository_id": repository_id,
                "commit_sha": commit_sha,
                "content_hash": digest,
                "count": len(claims),
            }
        )
    return profile


def usable_profile(
    profile: RepoProfile,
    *,
    now: datetime,
    head_sha: str | None = None,
    window: timedelta = PROFILE_POLICY_WINDOW,
) -> RepoProfile:
    del head_sha
    generated = profile.generated_at
    if generated.tzinfo is None:
        generated = generated.replace(tzinfo=UTC)
    if now - generated > window:
        raise ProfileStale("profile is older than its policy window")
    return profile


def claim_recency_weight(generated_at: datetime, *, now: datetime) -> float:
    days = (now - generated_at).total_seconds() / 86400.0
    if days < 0:
        days = 0.0
    return math.exp(-_RECENCY_LAMBDA * days)


def store_repo_profile(conn: Connection[Any], profile: RepoProfile) -> str:
    profile_id = str(uuid4())
    conn.execute(
        """
        insert into repo_profiles (
          id, repository_id, commit_sha, model_name, prompt_version,
          generated_at, content_hash
        ) values (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            profile_id,
            profile.repository_id,
            profile.commit_sha,
            profile.model,
            profile.prompt_version,
            profile.generated_at,
            profile.content_hash,
        ),
    )
    for claim in profile.claims:
        conn.execute(
            """
            insert into profile_claims (
              profile_id, kind, text, supporting_paths, status
            ) values (%s, %s, %s, %s, %s)
            """,
            (
                profile_id,
                claim.kind,
                claim.text,
                list(claim.supporting_paths),
                claim.status,
            ),
        )
    conn.commit()
    return profile_id


def _candidate_claim(draft: dict[str, str]) -> ProfileClaim:
    return ProfileClaim(
        kind=str(draft.get("kind") or "focus"),
        text=str(draft.get("text") or ""),
        supporting_paths=_supporting_paths(draft),
        status="candidate",
    )


def _supporting_paths(draft: dict[str, str]) -> tuple[str, ...]:
    raw = draft.get("supporting_paths")
    if isinstance(raw, list | tuple):
        return tuple(str(item) for item in raw)
    return ()


def _head_sha(repo_path: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_path), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    sha = result.stdout.strip()
    if result.returncode != 0 or len(sha) != 40:
        raise RuntimeError(f"failed to read HEAD for {repo_path}")
    return sha


def _corpus_excerpt(repo_path: Path) -> str:
    return str(repo_path)
