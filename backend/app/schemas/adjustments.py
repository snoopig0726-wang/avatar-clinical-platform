from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.enums import AdjustmentStatus


class SubmitAdjustmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instruction: str = Field(min_length=2, max_length=300)

    @field_validator("instruction")
    @classmethod
    def reject_blank_instruction(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 2:
            raise ValueError("instruction must contain at least two characters")
        return stripped


class PatientAdjustmentResponse(BaseModel):
    request_id: UUID
    sequence_no: int
    status: AdjustmentStatus
    submitted_at: datetime
    reviewed_at: datetime | None = None


class SubmitAdjustmentResponse(PatientAdjustmentResponse):
    used: int
    limit: int = 3
    patient_message: str = "已提交，等待医生审核"


class PatientAdjustmentListResponse(BaseModel):
    items: list[PatientAdjustmentResponse]
    used: int
    limit: int = 3
    has_pending: bool


class DoctorAdjustmentResponse(PatientAdjustmentResponse):
    instruction: str
    controlled_instruction: str | None = None


class DoctorAdjustmentListResponse(BaseModel):
    items: list[DoctorAdjustmentResponse]
    used: int
    limit: int = 3
    has_pending: bool
    controlled_options: list[str]


class ReviewAdjustmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approve_as_is", "approve_edited", "reject"]
    controlled_instruction: str | None = Field(default=None, max_length=200)


class PatientAvatarResponse(BaseModel):
    version_id: UUID
    authorization_status: Literal["authorized"] = "authorized"
    display_mode: Literal["image", "mock_placeholder"]
    image_url: str | None = None
    message: str | None = None
