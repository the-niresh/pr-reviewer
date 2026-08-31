"""Default-branch instruction files. Off by default. Cannot change review gates."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from pr_reviewer.contracts.github import RepositoryIdentity

ALLOWED_INSTRUCTION_PATHS: tuple[str, ...] = ("CLAUDE.md", "AGENTS.md", ".pr-reviewer.md")
MAX_INSTRUCTION_FILES = 2
MAX_INSTRUCTION_BYTES = 4096
INSTRUCTION_TRUNCATION_MARKER = "\n[truncated]\n"


class ReviewPolicy(BaseModel):
    """Per-repository flags. Same default-off shape as auto-post and specialist mode."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    instructions_enabled: bool = False
    auto_post: bool = False
    specialist_mode: bool = False
    verification_required: bool = True
    public_posting: bool = False
    routing: Literal["queue_for_human"] = "queue_for_human"
    budget_tokens: int = Field(default=128_000, ge=0)


class InstructionSource(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str = Field(min_length=1)
    default_branch: str = Field(min_length=1)
    commit_sha: str = Field(min_length=1)
    content_hash: str = Field(min_length=64, max_length=64)
    byte_size: int = Field(ge=0)
    truncated: bool
    content: str


class InstructionApplication(BaseModel):
    """Focus text only. Gates stay on the unchanged policy object."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    policy: ReviewPolicy
    focus_text: str


class DefaultBranchReader(Protocol):
    def default_branch(self, identity: RepositoryIdentity) -> tuple[str, str]: ...

    def read_file(
        self,
        identity: RepositoryIdentity,
        path: str,
        *,
        commit_sha: str,
    ) -> bytes | None: ...


def default_review_policy() -> ReviewPolicy:
    return ReviewPolicy()


def load_repository_instructions(
    identity: RepositoryIdentity,
    reader: DefaultBranchReader,
    policy: ReviewPolicy,
) -> list[InstructionSource]:
    if not policy.instructions_enabled:
        return []
    branch, sha = reader.default_branch(identity)
    loaded: list[InstructionSource] = []
    for path in ALLOWED_INSTRUCTION_PATHS:
        if len(loaded) >= MAX_INSTRUCTION_FILES:
            break
        raw = reader.read_file(identity, path, commit_sha=sha)
        if raw is None:
            continue
        loaded.append(_source_from_bytes(path, branch, sha, raw))
    return loaded


def apply_instructions(policy: ReviewPolicy, texts: Sequence[str]) -> InstructionApplication:
    return InstructionApplication(policy=policy, focus_text="\n\n".join(texts))


def instruction_event_payloads(
    sources: Sequence[InstructionSource],
) -> list[dict[str, str | int | bool]]:
    return [
        {
            "path": source.path,
            "default_branch": source.default_branch,
            "commit_sha": source.commit_sha,
            "content_hash": source.content_hash,
            "byte_size": source.byte_size,
            "truncated": source.truncated,
        }
        for source in sources
    ]


def _source_from_bytes(
    path: str,
    default_branch: str,
    commit_sha: str,
    raw: bytes,
) -> InstructionSource:
    truncated = len(raw) > MAX_INSTRUCTION_BYTES
    body = raw[:MAX_INSTRUCTION_BYTES] if truncated else raw
    text = body.decode("utf-8", errors="replace")
    content = text + INSTRUCTION_TRUNCATION_MARKER if truncated else text
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return InstructionSource(
        path=path,
        default_branch=default_branch,
        commit_sha=commit_sha,
        content_hash=digest,
        byte_size=len(raw),
        truncated=truncated,
        content=content,
    )
