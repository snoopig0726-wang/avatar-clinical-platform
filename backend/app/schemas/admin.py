from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.enums import (
    ApprovalStatus,
    AuditActorType,
    AuditResult,
    RetentionStatus,
    RiskRuleType,
)


class AdminDoctorResponse(BaseModel):
    user_id: UUID
    email: str
    display_name: str
    email_verified: bool
    approval_status: ApprovalStatus
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None = None


class AdminDoctorListResponse(BaseModel):
    items: list[AdminDoctorResponse]
    total: int


class UpdateDoctorAccessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approval_status: ApprovalStatus | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def require_change(self):
        if self.approval_status is None and self.is_active is None:
            raise ValueError("at least one account field must change")
        return self


class AdminRiskRuleResponse(BaseModel):
    rule_id: UUID
    rule_code: str
    category: str
    rule_type: RiskRuleType
    trigger_terms: list[str]
    context_terms: list[str] | None = None
    exclusion_terms: list[str] | None = None
    patient_message_type: str
    version: str
    is_enabled: bool
    updated_at: datetime


class AdminRiskRuleListResponse(BaseModel):
    items: list[AdminRiskRuleResponse]


class UpdateRiskRuleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str | None = Field(default=None, min_length=2, max_length=100)
    trigger_terms: list[str] | None = Field(default=None, min_length=1, max_length=100)
    context_terms: list[str] | None = Field(default=None, max_length=100)
    exclusion_terms: list[str] | None = Field(default=None, max_length=50)
    patient_message_type: str | None = Field(default=None, pattern="^(risk|identity|crisis)$")
    is_enabled: bool | None = None
    version: str = Field(min_length=3, max_length=32)

    @field_validator("trigger_terms", "context_terms", "exclusion_terms")
    @classmethod
    def validate_terms(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        normalized = list(dict.fromkeys(term.strip() for term in value if term.strip()))
        if any(len(term) > 50 for term in normalized):
            raise ValueError("risk terms must be 50 characters or fewer")
        return normalized


class AdminAuditResponse(BaseModel):
    audit_id: int
    actor_type: AuditActorType
    actor_user_id: UUID | None = None
    action: str
    result: AuditResult
    metadata: dict[str, object] | None = None
    created_at: datetime


class AdminAuditListResponse(BaseModel):
    items: list[AdminAuditResponse]
    page: int
    page_size: int
    total: int


class OperationalAlertResponse(BaseModel):
    code: str
    severity: str = Field(pattern="^(info|warning|critical)$")
    message: str
    count: int = Field(ge=1)


class AdminStatsResponse(BaseModel):
    doctors: dict[str, int]
    cases: dict[str, int]
    sessions: dict[str, int]
    adjustments: dict[str, int]
    risk_blocks: int
    retention_jobs: dict[str, int]
    generations: dict[str, int]
    generation_success_rate: float | None = None
    average_generation_seconds: float | None = None
    alerts: list[OperationalAlertResponse]


class AdminArchivedCaseResponse(BaseModel):
    case_id: UUID
    study_code: str
    archived_at: datetime
    retention_due_at: datetime
    restorable: bool


class AdminArchivedCaseListResponse(BaseModel):
    items: list[AdminArchivedCaseResponse]


class RestoreCaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=100)


class RestoreCaseResponse(BaseModel):
    case_id: UUID
    status: str
    retention_due_at: datetime
    old_sessions_restored: bool = False


class DeleteArchivedCaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation: Literal["PERMANENTLY_DELETE_ARCHIVED_CASE"]
    reason: str | None = Field(default=None, max_length=100)


class DeleteArchivedCaseResponse(BaseModel):
    case_id: UUID
    retention_job_id: UUID
    status: Literal[RetentionStatus.SCHEDULED, RetentionStatus.RUNNING]


class RetentionJobResponse(BaseModel):
    retention_job_id: UUID
    status: RetentionStatus
    retention_started_at: datetime
    retention_due_at: datetime
    attempt_count: int
    last_attempt_at: datetime | None = None
    deleted_categories: dict[str, object] | None = None
    last_error_code: str | None = None
    completed_at: datetime | None = None


class RetentionJobListResponse(BaseModel):
    items: list[RetentionJobResponse]
