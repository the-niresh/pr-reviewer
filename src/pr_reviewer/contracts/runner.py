from __future__ import annotations

import uuid
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
