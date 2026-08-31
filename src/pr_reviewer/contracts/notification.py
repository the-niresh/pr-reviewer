from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Confidentiality = Literal["restricted", "ordinary"]
ChannelPurpose = Literal["security_alert", "review_ping"]
TransportName = Literal["slack", "telegram", "discord"]


class NotificationChannel(BaseModel):
    """Operator-declared destination. Confidentiality is never inferred from transport."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    transport: TransportName
    purpose: ChannelPurpose
    confidentiality: Confidentiality = "restricted"
    revoked: bool = False

    @field_validator("confidentiality", mode="before")
    @classmethod
    def unset_confidentiality_is_restricted(cls, value: object) -> object:
        if value is None or value == "":
            return "restricted"
        return value


class NotificationPreview(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str = Field(min_length=1)
    body: str = Field(min_length=1)
    confidentiality: Confidentiality
