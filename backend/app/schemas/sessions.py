from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import InviteStatus, SessionStatus


class CreateInviteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expires_in_hours: int = Field(default=24, ge=1, le=72)


class InviteResponse(BaseModel):
    invite_id: UUID
    session_id: UUID | None = None
    code: str | None = None
    code_mask: str
    status: InviteStatus
    created_at: datetime
    expires_at: datetime


class InviteListResponse(BaseModel):
    items: list[InviteResponse]


class RedeemInviteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=8, max_length=20)
    device_binding: str = Field(min_length=16, max_length=200)


class RedeemInviteResponse(BaseModel):
    session_id: UUID
    patient_session_token: str
    status: SessionStatus
    expires_at: datetime


class SessionControlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=100)


class StartSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    consent_confirmed: bool
    consent_version: str = Field(default="v1", min_length=1, max_length=50)


class AdjustmentUsage(BaseModel):
    used: int = 0
    limit: int = 3
    has_pending: bool = False


class SessionResponse(BaseModel):
    session_id: UUID
    case_id: UUID
    study_code: str | None = None
    status: SessionStatus
    stage: str
    current_authorized_version_id: UUID | None = None
    adjustments: AdjustmentUsage
    created_at: datetime
    started_at: datetime | None = None
    paused_at: datetime | None = None
    ended_at: datetime | None = None
    expires_at: datetime
