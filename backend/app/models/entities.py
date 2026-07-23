from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import (
    AdjustmentStatus,
    ApprovalStatus,
    AuditActorType,
    AuditResult,
    AuthorizationStatus,
    CaseStatus,
    GenerationMode,
    GenerationStatus,
    InviteStatus,
    RetentionStatus,
    RiskRuleType,
    Role,
    SessionStatus,
)
from app.models.base import Base


def enum_column(enum_type: type, name: str) -> Enum:
    return Enum(enum_type, name=name, native_enum=False, validate_strings=True)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class StaffUser(Base):
    __tablename__ = "users"

    user_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(100))
    role: Mapped[Role] = mapped_column(enum_column(Role, "role_enum"), nullable=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    approval_status: Mapped[ApprovalStatus] = mapped_column(
        enum_column(ApprovalStatus, "approval_status_enum"),
        default=ApprovalStatus.PENDING,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    cases: Mapped[list[ClinicalCase]] = relationship(back_populates="owner_doctor")

    __table_args__ = (
        Index("ix_users_role_approval_active", "role", "approval_status", "is_active"),
    )


class StaffAccessSession(Base):
    __tablename__ = "staff_access_sessions"

    access_session_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    token_id_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EmailVerificationToken(Base):
    __tablename__ = "email_verification_tokens"

    verification_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_email_verification_user_expiry", "user_id", "expires_at"),)


class ClinicalCase(Base, TimestampMixin):
    __tablename__ = "cases"

    case_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_doctor_id: Mapped[UUID] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    study_code: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[CaseStatus] = mapped_column(
        enum_column(CaseStatus, "case_status_enum"), default=CaseStatus.DRAFT, nullable=False
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retention_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retention_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    owner_doctor: Mapped[StaffUser] = relationship(back_populates="cases")
    invites: Mapped[list[SessionInvite]] = relationship(back_populates="case")
    sessions: Mapped[list[PatientSession]] = relationship(back_populates="case")

    __table_args__ = (
        UniqueConstraint("owner_doctor_id", "study_code", name="uq_cases_doctor_study_code"),
        Index("ix_cases_owner_status_updated", "owner_doctor_id", "status", "updated_at"),
        Index("ix_cases_retention_due", "retention_due_at"),
    )


class SessionInvite(Base):
    __tablename__ = "session_invites"

    invite_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.case_id"), nullable=False)
    issuing_doctor_id: Mapped[UUID] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    code_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True, nullable=False)
    code_mask: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[InviteStatus] = mapped_column(
        enum_column(InviteStatus, "invite_status_enum"),
        default=InviteStatus.ISSUED,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    case: Mapped[ClinicalCase] = relationship(back_populates="invites")
    patient_session: Mapped[PatientSession | None] = relationship(back_populates="invite")

    __table_args__ = (Index("ix_session_invites_case_status", "case_id", "status"),)


class PatientSession(Base):
    __tablename__ = "patient_sessions"

    session_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.case_id"), nullable=False)
    invite_id: Mapped[UUID] = mapped_column(
        ForeignKey("session_invites.invite_id"), unique=True, nullable=False
    )
    supervising_doctor_id: Mapped[UUID] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    device_binding_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    patient_session_token_hash: Mapped[bytes] = mapped_column(
        LargeBinary, unique=True, nullable=False
    )
    status: Mapped[SessionStatus] = mapped_column(
        enum_column(SessionStatus, "session_status_enum"),
        default=SessionStatus.WAITING_DOCTOR,
        nullable=False,
    )
    consent_confirmed_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.user_id"))
    consent_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consent_version: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    case: Mapped[ClinicalCase] = relationship(back_populates="sessions")
    invite: Mapped[SessionInvite] = relationship(back_populates="patient_session")

    __table_args__ = (Index("ix_patient_sessions_case_status", "case_id", "status"),)


class SoundDescription(Base):
    __tablename__ = "sound_descriptions"

    sound_description_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.case_id"), nullable=False)
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("patient_sessions.session_id"), unique=True, nullable=False
    )
    voice_gender: Mapped[str | None] = mapped_column(String(32))
    age_sense: Mapped[str | None] = mapped_column(String(32))
    pitch_level: Mapped[int | None]
    speaking_rate_level: Mapped[int | None]
    timbre: Mapped[str | None] = mapped_column(String(32))
    emotions: Mapped[list[str] | None] = mapped_column(JSON)
    power_level: Mapped[int | None]
    malice_level: Mapped[int | None]
    answered_questions: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_sound_descriptions_case_updated", "case_id", "updated_at"),
        Index("ix_sound_descriptions_session", "session_id"),
    )


class VisualFeature(Base):
    __tablename__ = "visual_features"

    visual_feature_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.case_id"), nullable=False)
    source_sound_description_id: Mapped[UUID] = mapped_column(
        ForeignKey("sound_descriptions.sound_description_id"), nullable=False
    )
    system_result_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    doctor_edited_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    effective_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    mapping_explanation: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    mapping_version: Mapped[str] = mapped_column(String(100), nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    confirmed_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.user_id"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_visual_features_case_current", "case_id", "is_current"),
        Index("ix_visual_features_source", "source_sound_description_id"),
    )


class AvatarVersion(Base):
    __tablename__ = "avatar_versions"

    version_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.case_id"), nullable=False)
    source_visual_feature_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("visual_features.visual_feature_id")
    )
    voice_features_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    visual_features_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    generation_round: Mapped[int] = mapped_column(nullable=False)
    generation_mode: Mapped[GenerationMode] = mapped_column(
        enum_column(GenerationMode, "generation_mode_enum"), nullable=False
    )
    generation_status: Mapped[GenerationStatus] = mapped_column(
        enum_column(GenerationStatus, "generation_status_enum"), nullable=False
    )
    image_object_key: Mapped[str | None] = mapped_column(String(512))
    provider_kind: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_model: Mapped[str] = mapped_column(String(100), nullable=False)
    provider_request_id: Mapped[str | None] = mapped_column(String(200))
    prompt_template_version: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_sha256: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    output_mime_type: Mapped[str | None] = mapped_column(String(50))
    image_width: Mapped[int | None]
    image_height: Mapped[int | None]
    failure_code: Mapped[str | None] = mapped_column(String(100))
    source_adjustment_request_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("adjustment_requests.request_id")
    )
    safety_status: Mapped[str] = mapped_column(String(32), nullable=False)
    semantic_safety_provider: Mapped[str | None] = mapped_column(String(50))
    semantic_safety_model: Mapped[str | None] = mapped_column(String(100))
    semantic_safety_request_id: Mapped[str | None] = mapped_column(String(200))
    semantic_safety_categories_json: Mapped[list[str] | None] = mapped_column(JSON)
    doctor_review_status: Mapped[str] = mapped_column(String(32), nullable=False)
    doctor_reviewed_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.user_id"))
    doctor_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_current_candidate: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_avatar_versions_case_created", "case_id", "created_at"),
        Index("ix_avatar_versions_case_status", "case_id", "generation_status"),
    )


class SessionAvatarAuthorization(Base):
    __tablename__ = "session_avatar_authorizations"

    authorization_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("patient_sessions.session_id"), nullable=False
    )
    version_id: Mapped[UUID] = mapped_column(
        ForeignKey("avatar_versions.version_id"), nullable=False
    )
    status: Mapped[AuthorizationStatus] = mapped_column(
        enum_column(AuthorizationStatus, "authorization_status_enum"), nullable=False
    )
    authorized_by: Mapped[UUID] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    authorized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoke_reason: Mapped[str | None] = mapped_column(String(100))

    __table_args__ = (Index("ix_authorizations_session_status", "session_id", "status"),)


class RiskRule(Base):
    __tablename__ = "risk_rules"

    rule_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    rule_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    rule_type: Mapped[RiskRuleType] = mapped_column(
        enum_column(RiskRuleType, "risk_rule_type_enum"), nullable=False
    )
    trigger_terms: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    context_terms: Mapped[list[str] | None] = mapped_column(JSON)
    exclusion_terms: Mapped[list[str] | None] = mapped_column(JSON)
    patient_message_type: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_risk_rules_enabled_type", "is_enabled", "rule_type"),)


class AdjustmentRequest(Base):
    __tablename__ = "adjustment_requests"

    request_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.case_id"), nullable=False)
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("patient_sessions.session_id"), nullable=False
    )
    sequence_no: Mapped[int] = mapped_column(nullable=False)
    submitted_text_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    risk_status: Mapped[str] = mapped_column(String(32), nullable=False)
    risk_rule_version: Mapped[str] = mapped_column(String(32), nullable=False)
    doctor_status: Mapped[AdjustmentStatus] = mapped_column(
        enum_column(AdjustmentStatus, "adjustment_status_enum"), nullable=False
    )
    reviewed_instruction_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.user_id"))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("case_id", "sequence_no", name="uq_adjustment_case_sequence"),
        Index("ix_adjustment_case_status", "case_id", "doctor_status"),
        Index("ix_adjustment_session_submitted", "session_id", "submitted_at"),
    )


class RetentionJob(Base):
    __tablename__ = "retention_jobs"

    retention_job_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    case_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("cases.case_id", ondelete="SET NULL"), unique=True
    )
    case_reference_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True, nullable=False)
    retention_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    retention_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[RetentionStatus] = mapped_column(
        enum_column(RetentionStatus, "retention_status_enum"), nullable=False
    )
    attempt_count: Mapped[int] = mapped_column(default=0, nullable=False)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_categories_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    last_error_code: Mapped[str | None] = mapped_column(String(100))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_retention_jobs_due_status", "retention_due_at", "status"),)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"

    idempotency_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    actor_scope: Mapped[str] = mapped_column(String(100), nullable=False)
    operation: Mapped[str] = mapped_column(String(100), nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    resource_id: Mapped[UUID | None] = mapped_column(Uuid)
    response_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "actor_scope", "operation", "key", name="uq_idempotency_scope_operation_key"
        ),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    audit_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    actor_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.user_id"))
    actor_type: Mapped[AuditActorType] = mapped_column(
        enum_column(AuditActorType, "audit_actor_type_enum"), nullable=False
    )
    case_id: Mapped[UUID | None] = mapped_column(ForeignKey("cases.case_id"))
    invite_id: Mapped[UUID | None] = mapped_column(ForeignKey("session_invites.invite_id"))
    session_id: Mapped[UUID | None] = mapped_column(ForeignKey("patient_sessions.session_id"))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    result: Mapped[AuditResult] = mapped_column(
        enum_column(AuditResult, "audit_result_enum"), nullable=False
    )
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_audit_logs_case_created", "case_id", "created_at"),
        Index("ix_audit_logs_actor_created", "actor_user_id", "created_at"),
        Index("ix_audit_logs_action_created", "action", "created_at"),
    )
