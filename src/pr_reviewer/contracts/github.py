from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PullRequestRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    owner: str = Field(min_length=1)
    repository: str = Field(min_length=1)
    number: int = Field(gt=0)


class GitHubDelivery(BaseModel):
    model_config = ConfigDict(frozen=True)

    delivery_id: str = Field(min_length=1)
    event: str = Field(min_length=1)
    repository: str = Field(min_length=1)
    pull_request: PullRequestRef
