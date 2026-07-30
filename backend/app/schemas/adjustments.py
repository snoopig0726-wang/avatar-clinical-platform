from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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
    instruction: str
    status: AdjustmentStatus
    rejection_reason: str | None = None
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
    controlled_instruction: str | None = None
    clinician_edited_instruction: str | None = None
    suggested_controlled_instruction: str
    controlled_options: list[str]


class DoctorAdjustmentListResponse(BaseModel):
    items: list[DoctorAdjustmentResponse]
    used: int
    limit: int = 3
    has_pending: bool
    controlled_options: list[str]


class RemapAdjustmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clinician_edited_instruction: str = Field(min_length=2, max_length=300)

    @field_validator("clinician_edited_instruction")
    @classmethod
    def normalize_edited_instruction(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 2:
            raise ValueError("clinician_edited_instruction must contain at least two characters")
        return stripped


class AdjustmentRemapResponse(BaseModel):
    clinician_edited_instruction: str
    suggested_controlled_instruction: str
    controlled_options: list[str]


class ReviewAdjustmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approve_as_is", "approve_edited", "reject"]
    clinician_edited_instruction: str | None = Field(default=None, max_length=300)
    controlled_instruction: str | None = Field(default=None, max_length=200)
    rejection_reason: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def validate_decision_details(self) -> ReviewAdjustmentRequest:
        if self.decision == "reject":
            reason = (self.rejection_reason or "").strip()
            if len(reason) < 2:
                raise ValueError("rejection_reason is required when rejecting")
            self.rejection_reason = reason
        elif self.rejection_reason is not None:
            raise ValueError("rejection_reason is only allowed when rejecting")

        if self.decision == "approve_edited":
            edited = (self.clinician_edited_instruction or "").strip()
            if edited:
                if len(edited) < 2:
                    raise ValueError(
                        "clinician_edited_instruction must contain at least two characters"
                    )
                self.clinician_edited_instruction = edited
            elif not self.controlled_instruction:
                raise ValueError(
                    "clinician_edited_instruction is required when approving an edit"
                )
            else:
                self.clinician_edited_instruction = None
        elif self.clinician_edited_instruction is not None:
            raise ValueError(
                "clinician_edited_instruction is only allowed when approving an edit"
            )
        return self


class PatientAvatarResponse(BaseModel):
    version_id: UUID
    authorization_status: Literal["authorized"] = "authorized"
    display_mode: Literal["image", "mock_placeholder"]
    image_url: str | None = None
    message: str | None = None
