from enum import StrEnum


class Role(StrEnum):
    DOCTOR = "doctor"
    INVITED_PATIENT = "invited_patient"
    ADMIN = "admin"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class CaseStatus(StrEnum):
    DRAFT = "draft"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class SessionStatus(StrEnum):
    WAITING_DOCTOR = "waiting_doctor"
    ACTIVE = "active"
    PAUSED = "paused"
    ENDED = "ended"
    EXPIRED = "expired"


class InviteStatus(StrEnum):
    ISSUED = "issued"
    REDEEMED_WAITING = "redeemed_waiting"
    ACTIVE = "active"
    ENDED = "ended"
    REVOKED = "revoked"
    EXPIRED = "expired"


class AuditActorType(StrEnum):
    DOCTOR = "doctor"
    ADMIN = "admin"
    PATIENT = "patient"
    SYSTEM = "system"


class AuditResult(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    BLOCKED = "blocked"


class RiskRuleType(StrEnum):
    DIRECT = "direct"
    CONTEXT = "context"
    PII = "pii"


class AuthorizationStatus(StrEnum):
    AUTHORIZED = "authorized"
    REVOKED = "revoked"


class RetentionStatus(StrEnum):
    SCHEDULED = "scheduled"
    RUNNING = "running"
    RETRYING = "retrying"
    COMPLETED = "completed"
    FAILED = "failed"


class GenerationStatus(StrEnum):
    QUEUED = "queued"
    GENERATING = "generating"
    CHECKING = "checking"
    PENDING_DOCTOR_REVIEW = "pending_doctor_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AdjustmentStatus(StrEnum):
    PENDING_DOCTOR_REVIEW = "pending_doctor_review"
    APPROVED_AS_IS = "approved_as_is"
    APPROVED_EDITED = "approved_edited"
    REJECTED = "rejected"
    GENERATING = "generating"
    APPLIED = "applied"
    GENERATION_FAILED = "generation_failed"
    CANCELLED = "cancelled"


class GenerationMode(StrEnum):
    INITIAL = "initial"
    SAME_FEATURES_REGENERATE = "same_features_regenerate"
    FEATURE_UPDATE = "feature_update"
    PATIENT_ADJUSTMENT = "patient_adjustment"
