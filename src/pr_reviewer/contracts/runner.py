from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

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
    verify_installation_access, which calls GitHub's /user/installations with the user's own
    OAuth token), enforced by
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
