from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import GenerationMode, GenerationStatus


class CreateAvatarGenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["initial", "same_features_regenerate", "feature_update"]


class CancelAvatarGenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str | None = Field(default=None, max_length=100)


class AvatarVersionResponse(BaseModel):
    version_id: UUID
    case_id: UUID
    generation_round: int
    generation_mode: GenerationMode
    generation_status: GenerationStatus
    safety_status: str
    doctor_review_status: str
    provider_kind: str
    provider_model: str
    prompt_template_version: str
    image_url: str | None = None
    failure_code: str | None = None
    is_current_candidate: bool
    is_authorized: bool = False
    snapshot_available: bool = False
    doctor_reviewed_at: datetime | None = None
    source_adjustment_request_id: UUID | None = None
    created_at: datetime
    completed_at: datetime | None = None


class AvatarVersionListResponse(BaseModel):
    items: list[AvatarVersionResponse]


class AvatarVersionDetailResponse(AvatarVersionResponse):
    voice_features_snapshot: dict[str, object] | None = None
    visual_features_snapshot: dict[str, object] | None = None


class ReviewAvatarRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "reject"]


class AuthorizeAvatarRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: UUID


class RollbackAvatarRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: UUID | None = None
    reason: str | None = None


class RevokeAvatarAuthorizationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: UUID
    reason: str | None = None


class RevokeAvatarAuthorizationResponse(BaseModel):
    status: Literal["revoked"] = "revoked"
    revoked_count: int
