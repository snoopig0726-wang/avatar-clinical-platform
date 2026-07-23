from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import ApprovalStatus, Role


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginRequest(StrictModel):
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=8, max_length=200)


class DoctorApplicationRequest(StrictModel):
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=12, max_length=200)
    display_name: str = Field(min_length=2, max_length=100)


class DoctorApplicationResponse(BaseModel):
    status: str = "verification_required"
    message: str
    development_verification_token: str | None = None


class VerifyEmailRequest(StrictModel):
    token: str = Field(min_length=32, max_length=200)


class VerifyEmailResponse(BaseModel):
    status: str = "verified"
    approval_status: ApprovalStatus
    message: str


class StaffSummary(BaseModel):
    user_id: UUID
    role: Role
    display_name: str
    email: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_at: datetime
    user: StaffSummary


class LogoutResponse(BaseModel):
    status: str
