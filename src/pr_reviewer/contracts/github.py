from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class OmissionReason(StrEnum):
    """Why a changed file has no usable patch. Task 10A consumes this set.

    Closed like ReviewJobErrorClass: a str field would let the next caller invent a
    value and nothing would notice. An unknown reason cannot be represented.
    """

    TOKEN_BUDGET = "token_budget"
    PATCH_OMITTED_BY_GITHUB = "patch_omitted_by_github"
    PATCH_TRUNCATED_BY_GITHUB = "patch_truncated_by_github"
    BINARY = "binary"
    GENERATED = "generated"
    IGNORED_PATH = "ignored_path"
    FILE_SIZE_LIMIT = "file_size_limit"
    CLONE_TIMEOUT = "clone_timeout"


class RepositoryIdentity(BaseModel):
    model_config = ConfigDict(frozen=True)

    installation_id: int = Field(gt=0)
    repository_id: int = Field(gt=0)
    owner: str = Field(min_length=1)
    name: str = Field(min_length=1)


class PullRequestRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    owner: str = Field(min_length=1)
    repository: str = Field(min_length=1)
    number: int = Field(gt=0)


class GitHubDelivery(BaseModel):
    model_config = ConfigDict(frozen=True)

    delivery_id: str = Field(min_length=1)
    event: str = Field(min_length=1)
    action: str = Field(min_length=1)
    repository_identity: RepositoryIdentity
    pull_request: PullRequestRef
    draft: bool = False
    base_sha: str = Field(min_length=1)
    head_sha: str = Field(min_length=1)
    repository: str = ""

    @model_validator(mode="before")
    @classmethod
    def default_repository(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        if data.get("repository"):
            return data
        identity = data.get("repository_identity")
        if isinstance(identity, RepositoryIdentity):
            return {
                **data,
                "repository": f"{identity.owner}/{identity.name}",
            }
        if isinstance(identity, dict):
            owner = identity.get("owner")
            name = identity.get("name")
            if isinstance(owner, str) and isinstance(name, str):
                return {**data, "repository": f"{owner}/{name}"}
        return data
