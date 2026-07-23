from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import CaseStatus


class CreateCaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    study_code: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{2,99}$")


class ArchiveCaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=100)


class CaseResponse(BaseModel):
    case_id: UUID
    study_code: str
    status: CaseStatus
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None
    retention_due_at: datetime | None = None
    active_session_count: int = 0


class CaseListResponse(BaseModel):
    items: list[CaseResponse]
    page: int
    page_size: int
    total: int
