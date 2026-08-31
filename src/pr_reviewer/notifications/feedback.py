"""Append-only human decisions. One row never rewrites prompts."""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Literal

from pr_reviewer.local_store.sqlite import LocalStore

FeedbackAction = Literal["approved", "rejected", "disputed", "edited"]


def record_human_feedback(
    store: LocalStore,
    *,
    finding_id: str,
    actor: str,
    action: FeedbackAction,
    note: str | None,
    original_hash: str,
    edited_hash: str,
    prompts: MutableMapping[str, str] | None = None,
) -> None:
    del prompts
    store.human_decisions.record(
        finding_id,
        action,
        actor,
        note,
        original_hash=original_hash,
        edited_hash=edited_hash,
    )
