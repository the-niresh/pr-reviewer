"""Cross-store trace reconstruction (Runtime Task 5A).

The plan this task comes from wrote reconstruct_trace against three inputs: the JobEnvelope
trace ID (Task 3), hosted connector_runs (master Task 8), and local events (Task 5). Task 8 is
unstarted -- there is no connector_runs table anywhere in this schema -- so this module joins the
two stores that exist today, hosted agent_events and local local_events, through
control_plane.runner_jobs.fetch_hosted_trace and local_store.sqlite.LocalStore.fetch_trace.
reconstruct_trace's signature takes the already-fetched HostedTrace and LocalTrace, not live
connections, so a third source becomes an added parameter later, not a rewrite of the merge
itself.

Neither table records a span_id or a parent_span_id -- that requirement targeted connector_runs,
which does not exist, and no migration is in this task's scope. So this module derives them from
data each store already, genuinely records:

- span_id is deterministic, not random: f"{origin}:{sequence}", where sequence is that table's own
  monotonic counter (agent_events.sequence, local_events.sequence). Two runs over the same rows
  produce the same span ids.
- Within one origin, parent_span_id is the previous span in that same store's own recorded
  sequence -- a real chain, because the sequence itself is real, not a timestamp comparison.
- Across origins, there is exactly one causal fact this codebase currently proves by construction
  rather than by clock: control_plane.runner_jobs.acknowledge_job writes the hosted
  "review_job_acknowledged" event from inside the runner-facing /ack HTTP handler, which by the
  protocol in Task 3 cannot run before the runner's local work has finished and called it. So that
  one hosted event kind is placed after the entire local chain; every other current hosted kind
  (model_call.recorded, review_job_failed, review_job_retry_scheduled) defaults to before it,
  because nothing in this codebase today proves a tighter placement for them -- review_job_failed
  and review_job_retry_scheduled are written by worker/main.py, which predates the runner/local
  split and talks to Neon directly, so they are not provably tied to the runner protocol the way
  the ack path is. Extending _HOSTED_POST_LOCAL_KINDS is the intended way to add a provably-later
  hosted kind later.

  An unproven hosted kind still needs *some* position in the merged list, and "before the local
  chain" is a fine default -- but a default is not a derivation, and the first version of this
  module rendered the two identically: an unproven review_job_failed and a proven
  review_job_acknowledged both just appeared in the list, with nothing distinguishing a placement
  this module knows from one it guessed. That is the same "silently partial" failure
  missing_origins/is_complete exist to prevent, one level down, so TraceSegment.placement fixes it
  the same way: "proven" for local segments (their own recorded sequence orders them) and for a
  hosted segment in _HOSTED_POST_LOCAL_KINDS, "unordered" for every other hosted segment. A
  review_job_failed that really happened after local work still renders above it by default, but
  now says so.

Never sort by wall-clock time anywhere in this module. Two machines, two clocks, and the runner's
may be minutes off; an offline runner that acknowledges hours late must not corrupt ordering, and
it cannot, because timestamps are carried on TraceSegment for display only and never touched by
the merge.

Redaction happens here, not as a convention the caller is trusted to follow. Task 1B already made
a hosted row structurally incapable of holding a secret or a raw patch
(agent_events_payload_is_flat, the ALLOWLIST). local_events has no such constraint -- it is a
lifecycle log on a store that legitimately holds source, diffs, and rationale elsewhere
(local_findings, local_snapshots) -- so this is the boundary on the way out of the local store:
_redact_payload walks every value in every segment's payload, recursively, and strips anything
that looks like a credential outright, regardless of configured level, and strips known-sensitive
content categories (a raw patch, source text, a finding's rationale) at the default "redacted"
level.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Literal

TraceOrigin = Literal["hosted", "local"]
TracePlacement = Literal["proven", "unordered"]
RedactionLevel = Literal["redacted", "debug"]

# The one hosted event kind this codebase can currently prove, by protocol construction rather
# than by clock, always follows the entire local chain for a job. See the module docstring.
_HOSTED_POST_LOCAL_KINDS: frozenset[str] = frozenset({"review_job_acknowledged"})

_SECRET_KEY_MARKERS: tuple[str, ...] = (
    "token",
    "key",
    "secret",
    "password",
    "credential",
    "authorization",
    "bearer",
)

# Content categories the task names explicitly: a raw patch, source text, and finding rationale.
# Stripped at the default "redacted" level; a hard secret (see _SECRET_KEY_MARKERS) is stripped
# regardless of level, because "level" configures how much review detail shows, never whether a
# credential can leak.
_SENSITIVE_CONTENT_KEYS: frozenset[str] = frozenset(
    {
        "patch",
        "diff",
        "source",
        "sourcetext",
        "source_text",
        "content",
        "code",
        "rationale",
        "prompt",
        "output",
        "rawoutput",
        "raw_output",
        "body",
    }
)


class TraceIntegrityError(RuntimeError):
    """Hosted and local report different trace ids for the same job_id.

    The join key is explicit, never inferred: job_id scopes both fetches, and each store also
    carries its own trace_id. If those two ever disagree, that is not something to silently
    resolve by picking one side -- it means the two stores' idea of which trace this job belongs
    to has diverged, which is a correctness bug worth surfacing loudly.
    """


@dataclass(frozen=True)
class HostedTraceEvent:
    sequence: int
    kind: str
    payload: Mapping[str, Any]
    created_at: datetime


@dataclass(frozen=True)
class LocalTraceEvent:
    sequence: int
    kind: str
    payload: Mapping[str, Any]
    created_at: str


@dataclass(frozen=True)
class HostedTrace:
    trace_id: str
    events: tuple[HostedTraceEvent, ...]


@dataclass(frozen=True)
class LocalTrace:
    trace_id: str
    events: tuple[LocalTraceEvent, ...]


@dataclass(frozen=True)
class TraceSegment:
    origin: TraceOrigin
    trace_id: str
    span_id: str
    parent_span_id: str | None
    timestamp: str
    kind: str
    payload: Mapping[str, Any]
    placement: TracePlacement


@dataclass(frozen=True)
class TraceReconstruction:
    job_id: str
    trace_id: str | None
    segments: tuple[TraceSegment, ...]
    missing_origins: frozenset[TraceOrigin]

    @property
    def is_complete(self) -> bool:
        return not self.missing_origins


def reconstruct_trace(
    job_id: str,
    hosted: HostedTrace | None,
    local: LocalTrace | None,
    *,
    redaction_level: RedactionLevel = "redacted",
) -> TraceReconstruction:
    """hosted is None when the hosted store has no record of this job at all (not merely zero
    events); same for local. That distinction is what lets a caller tell "we asked and there is
    nothing" apart from "we could not reach this store", instead of a bare empty list silently
    meaning either.
    """
    missing: set[TraceOrigin] = set()
    if hosted is None:
        missing.add("hosted")
    if local is None:
        missing.add("local")

    if hosted is not None and local is not None and hosted.trace_id != local.trace_id:
        raise TraceIntegrityError(
            f"job {job_id}: hosted trace_id {hosted.trace_id!r} does not match "
            f"local trace_id {local.trace_id!r}"
        )

    trace_id = (
        hosted.trace_id if hosted is not None else (local.trace_id if local is not None else None)
    )

    hosted_segments = _build_hosted_chain(
        trace_id or "", hosted.events if hosted is not None else (), redaction_level
    )
    local_segments = _build_local_chain(
        trace_id or "", local.events if local is not None else (), redaction_level
    )

    pre_local = [
        segment for segment in hosted_segments if segment.kind not in _HOSTED_POST_LOCAL_KINDS
    ]
    post_local = [
        segment for segment in hosted_segments if segment.kind in _HOSTED_POST_LOCAL_KINDS
    ]
    if post_local and local_segments:
        # The real causal edge this codebase can prove: the ack's parent is the local chain's
        # last span, not whichever hosted span happened to precede it in agent_events.sequence.
        post_local[0] = replace(post_local[0], parent_span_id=local_segments[-1].span_id)

    segments = tuple(pre_local) + tuple(local_segments) + tuple(post_local)
    return TraceReconstruction(
        job_id=job_id,
        trace_id=trace_id,
        segments=segments,
        missing_origins=frozenset(missing),
    )


def _build_hosted_chain(
    trace_id: str, events: Sequence[HostedTraceEvent], redaction_level: RedactionLevel
) -> list[TraceSegment]:
    segments: list[TraceSegment] = []
    previous_span_id: str | None = None
    for event in sorted(events, key=lambda item: item.sequence):
        span_id = f"hosted:{event.sequence}"
        segments.append(
            TraceSegment(
                origin="hosted",
                trace_id=trace_id,
                span_id=span_id,
                parent_span_id=previous_span_id,
                timestamp=event.created_at.isoformat(),
                kind=event.kind,
                payload=_redact_payload(dict(event.payload), redaction_level),
                placement="proven" if event.kind in _HOSTED_POST_LOCAL_KINDS else "unordered",
            )
        )
        previous_span_id = span_id
    return segments


def _build_local_chain(
    trace_id: str, events: Sequence[LocalTraceEvent], redaction_level: RedactionLevel
) -> list[TraceSegment]:
    segments: list[TraceSegment] = []
    previous_span_id: str | None = None
    for event in sorted(events, key=lambda item: item.sequence):
        span_id = f"local:{event.sequence}"
        segments.append(
            TraceSegment(
                origin="local",
                trace_id=trace_id,
                span_id=span_id,
                parent_span_id=previous_span_id,
                timestamp=event.created_at,
                kind=event.kind,
                payload=_redact_payload(dict(event.payload), redaction_level),
                placement="proven",
            )
        )
        previous_span_id = span_id
    return segments


_WORD_PATTERN = re.compile(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])")


def _key_words(key: str) -> list[str]:
    """Split camelCase and snake_case into lowercase words, so "inputTokens" is ["input",
    "tokens"] -- a plural token *count*, distinct from the word "token" that flags a credential --
    while "githubToken" is ["github", "token"] and does flag. A substring check would conflate
    the two; this exists so it cannot.
    """
    parts = re.split(r"[_\-]+", key)
    words: list[str] = []
    for part in parts:
        words.extend(match.lower() for match in _WORD_PATTERN.findall(part))
    return words


def _looks_like_secret_key(key: str) -> bool:
    words = set(_key_words(key))
    return bool(words & set(_SECRET_KEY_MARKERS))


def _mask(value: Any, category: Literal["secret", "content"]) -> str:
    if isinstance(value, str):
        return f"<redacted:{category}:{len(value)} chars>"
    return f"<redacted:{category}>"


def _redact_payload(payload: Mapping[str, Any], level: RedactionLevel) -> dict[str, Any]:
    return {key: _redact_field(key, value, level) for key, value in payload.items()}


def _redact_field(key: str, value: Any, level: RedactionLevel) -> Any:
    if _looks_like_secret_key(key):
        return _mask(value, "secret")
    if level == "redacted" and key.lower() in _SENSITIVE_CONTENT_KEYS:
        return _mask(value, "content")
    return _redact_value(value, level)


def _redact_value(value: Any, level: RedactionLevel) -> Any:
    if isinstance(value, Mapping):
        return {key: _redact_field(key, item, level) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_value(item, level) for item in value]
    return value
