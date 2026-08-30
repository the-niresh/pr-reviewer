from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

RunnerMode = Literal["analysis_only", "full"]

AuthorizationDenialReason = Literal[
    "unknown_installation",
    "revoked_installation",
    "unknown_repository",
    "unknown_runner",
    "revoked_runner",
    "runner_not_assigned_to_repository",
]

# Runtime Task 2: one-time runner pairing and credential auth. A caller presenting a pairing code
# and a PKCE proof is not authorised to learn whether that code never existed, already expired,
# was already used, or belongs to someone else's device: any of those told apart would let an
# attacker guessing codes confirm a hit before also having the matching verifier. So all four
# collapse into invalid_or_expired_code (docs/phases/phase-2-security-design-gate.md, section 6).
PairingDenialReason = Literal[
    "invalid_or_expired_code",
    "repository_not_in_installation",
    "revoked_installation",
    "unknown_installation",
]

# A caller presenting a runner credential already possesses evidence of prior legitimate
# issuance, unlike pairing where the caller might only be guessing. So, unlike PairingDenialReason,
# these two are allowed to be distinguishable: "this credential never matched any runner" and
# "this credential matched a runner that has since been revoked" are both about the caller's own
# credential, not a cross-tenant read.
RunnerAuthDenialReason = Literal["unknown_credential", "revoked_runner"]


class RunnerCapabilities(BaseModel):
    model_config = ConfigDict(frozen=True)

    mode: RunnerMode
    docker_available: bool
    retrieval_available: bool
    verification_available: bool
    platform: str = Field(min_length=1)
    version: str = Field(min_length=1)


class RunnerRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    runner_id: uuid.UUID
    device_name: str = Field(min_length=1)


class RepositoryAuthorization(BaseModel):
    model_config = ConfigDict(frozen=True)

    installation_id: int
    github_repository_id: int
    repository_id: uuid.UUID
    runner_id: uuid.UUID


class AuthorizationDenied(BaseModel):
    model_config = ConfigDict(frozen=True)

    reason: AuthorizationDenialReason


class AssignmentGranted(BaseModel):
    model_config = ConfigDict(frozen=True)

    repository_id: uuid.UUID
    runner_id: uuid.UUID


class AssignmentRefused(BaseModel):
    model_config = ConfigDict(frozen=True)

    repository_id: uuid.UUID
    active_runner: RunnerRef


class VerifiedInstallationAccess(BaseModel):
    """Proof that github_user_id controls installation_id, plus the repositories GitHub said that
    installation covers.

    This has exactly one construction site in src/ (control_plane/github_oauth.py's
    verify_installation_access). That function either proves control with a live GitHub
    /user/installations call, or consumes a LiveInstallationAssertion captured from that same
    call at sign-in. Enforced by
    test_verified_installation_access_construction_site_is_exactly_github_oauth in
    tests/test_github_oauth.py. It cannot be built from three loose values wherever one is
    convenient: approve_pairing takes this object, not a github_user_id and an installation_id
    and a repositories dict as three separate parameters a caller could mismatch. repositories
    maps github_repository_id to name exactly as GitHub's own response would, so approve_pairing
    never has to trust a caller-supplied name for a caller-supplied id.
    """

    model_config = ConfigDict(frozen=True)

    github_user_id: int
    installation_id: int
    repositories: dict[int, str]


class PairingChallenge(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    expires_at: datetime


class PairingApproved(BaseModel):
    model_config = ConfigDict(frozen=True)

    installation_id: int
    repository_ids: tuple[uuid.UUID, ...]


class PairingDenied(BaseModel):
    model_config = ConfigDict(frozen=True)

    reason: PairingDenialReason


class RunnerCredential(BaseModel):
    """The runner's credential in the clear. Returned exactly once, at exchange, and never stored
    or logged anywhere in this form; only hash_runner_credential(credential) goes in the
    database.
    """

    model_config = ConfigDict(frozen=True)

    runner_id: uuid.UUID
    credential: str = Field(min_length=1)


class AuthenticatedRunner(BaseModel):
    model_config = ConfigDict(frozen=True)

    runner_id: uuid.UUID
    device_name: str = Field(min_length=1)
    mode: RunnerMode


class RunnerAuthDenied(BaseModel):
    model_config = ConfigDict(frozen=True)

    reason: RunnerAuthDenialReason


JobLeaseDenialReason = Literal["invalid_or_expired"]
JobTerminalState = Literal["succeeded", "failed"]


class JobBudget(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_tokens: int = Field(ge=0)
    max_cost_usd: Decimal = Field(ge=0)


class JobEnvelope(BaseModel):
    """Typed identifiers and policy for one leased review. No command strings.

    lease_token is minted at claim and bound to the claiming runner in the same
    statement. Heartbeat and acknowledge must present it; it is not a job field
    GitHub supplied, it is the capability that proves this runner holds the lease.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    job_id: uuid.UUID
    installation_id: int
    repository_id: int
    pull_request_number: int = Field(gt=0)
    base_sha: str = Field(min_length=1)
    head_sha: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    budget: JobBudget
    trace_id: uuid.UUID
    lease_token: str = Field(min_length=1)

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)


class NoJob(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class LeaseState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["active", "invalid_or_expired"]


class JobAcknowledgement(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    terminal_state: JobTerminalState
    error_class: str | None = None
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cost_usd: Decimal = Field(ge=0)
    latency_ms: int = Field(ge=0)
    local_result_hash: str = Field(min_length=1)

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)


class JobProtocolDenied(Exception):
    """Wrong lease, expired lease, and unknown job collapse to one reason."""

    def __init__(self, reason: JobLeaseDenialReason = "invalid_or_expired") -> None:
        self.reason = reason
        super().__init__(reason)


class GitHubJobToken(BaseModel):
    """A short-lived GitHub installation token, scoped to one job's repository and to read-only
    permissions (Runtime Task 4).

    Minted by issue_job_token in exchange for a valid job lease -- the same lease_token JobEnvelope
    carries, checked the same way acknowledge_job already checks it. Returned once, over
    authenticated HTTPS, and never written to Neon or to local disk: there is no column or table
    anywhere that holds it, by construction, not by redaction.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    token: str = Field(min_length=1)
    github_repository_id: int
    expires_at: datetime
