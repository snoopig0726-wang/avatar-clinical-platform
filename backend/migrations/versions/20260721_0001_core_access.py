"""Create core staff, case, invite, session and audit tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260721_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(100)),
        sa.Column(
            "role",
            sa.Enum("DOCTOR", "INVITED_PATIENT", "ADMIN", name="role_enum", native_enum=False),
            nullable=False,
        ),
        sa.Column("email_verified", sa.Boolean(), nullable=False),
        sa.Column(
            "approval_status",
            sa.Enum(
                "PENDING", "APPROVED", "REJECTED", name="approval_status_enum", native_enum=False
            ),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("user_id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index(
        "ix_users_role_approval_active", "users", ["role", "approval_status", "is_active"]
    )
    op.create_table(
        "staff_access_sessions",
        sa.Column("access_session_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_id_hash", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], name="fk_access_user"),
        sa.PrimaryKeyConstraint("access_session_id", name="pk_staff_access_sessions"),
        sa.UniqueConstraint("token_id_hash", name="uq_staff_access_token_hash"),
    )
    op.create_table(
        "cases",
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("owner_doctor_id", sa.Uuid(), nullable=False),
        sa.Column("study_code", sa.String(100), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "DRAFT",
                "IN_PROGRESS",
                "COMPLETED",
                "ARCHIVED",
                name="case_status_enum",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.Column("retention_started_at", sa.DateTime(timezone=True)),
        sa.Column("retention_due_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_doctor_id"], ["users.user_id"], name="fk_case_owner"),
        sa.PrimaryKeyConstraint("case_id", name="pk_cases"),
        sa.UniqueConstraint("owner_doctor_id", "study_code", name="uq_cases_doctor_study_code"),
    )
    op.create_index(
        "ix_cases_owner_status_updated", "cases", ["owner_doctor_id", "status", "updated_at"]
    )
    op.create_index("ix_cases_retention_due", "cases", ["retention_due_at"])
    op.create_table(
        "session_invites",
        sa.Column("invite_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("issuing_doctor_id", sa.Uuid(), nullable=False),
        sa.Column("code_hash", sa.LargeBinary(), nullable=False),
        sa.Column("code_mask", sa.String(32), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "ISSUED",
                "REDEEMED_WAITING",
                "ACTIVE",
                "ENDED",
                "REVOKED",
                "EXPIRED",
                name="invite_status_enum",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("redeemed_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["case_id"], ["cases.case_id"], name="fk_invite_case"),
        sa.ForeignKeyConstraint(["issuing_doctor_id"], ["users.user_id"], name="fk_invite_doctor"),
        sa.PrimaryKeyConstraint("invite_id", name="pk_session_invites"),
        sa.UniqueConstraint("code_hash", name="uq_session_invites_code_hash"),
    )
    op.create_index("ix_session_invites_case_status", "session_invites", ["case_id", "status"])
    op.create_table(
        "patient_sessions",
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("invite_id", sa.Uuid(), nullable=False),
        sa.Column("supervising_doctor_id", sa.Uuid(), nullable=False),
        sa.Column("device_binding_hash", sa.LargeBinary(), nullable=False),
        sa.Column("patient_session_token_hash", sa.LargeBinary(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "WAITING_DOCTOR",
                "ACTIVE",
                "PAUSED",
                "ENDED",
                "EXPIRED",
                name="session_status_enum",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("consent_confirmed_by", sa.Uuid()),
        sa.Column("consent_confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("consent_version", sa.String(50)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("paused_at", sa.DateTime(timezone=True)),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["case_id"], ["cases.case_id"], name="fk_session_case"),
        sa.ForeignKeyConstraint(
            ["invite_id"], ["session_invites.invite_id"], name="fk_session_invite"
        ),
        sa.ForeignKeyConstraint(
            ["supervising_doctor_id"], ["users.user_id"], name="fk_session_doctor"
        ),
        sa.ForeignKeyConstraint(
            ["consent_confirmed_by"], ["users.user_id"], name="fk_session_consent_doctor"
        ),
        sa.PrimaryKeyConstraint("session_id", name="pk_patient_sessions"),
        sa.UniqueConstraint("invite_id", name="uq_patient_sessions_invite_id"),
        sa.UniqueConstraint("patient_session_token_hash", name="uq_patient_session_token_hash"),
    )
    op.create_index("ix_patient_sessions_case_status", "patient_sessions", ["case_id", "status"])
    op.create_table(
        "idempotency_records",
        sa.Column("idempotency_id", sa.Uuid(), nullable=False),
        sa.Column("actor_scope", sa.String(100), nullable=False),
        sa.Column("operation", sa.String(100), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.LargeBinary(), nullable=False),
        sa.Column("resource_id", sa.Uuid()),
        sa.Column("response_snapshot", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("idempotency_id", name="pk_idempotency_records"),
        sa.UniqueConstraint(
            "actor_scope", "operation", "key", name="uq_idempotency_scope_operation_key"
        ),
    )
    op.create_table(
        "audit_logs",
        sa.Column("audit_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("actor_user_id", sa.Uuid()),
        sa.Column(
            "actor_type",
            sa.Enum(
                "DOCTOR",
                "ADMIN",
                "PATIENT",
                "SYSTEM",
                name="audit_actor_type_enum",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("case_id", sa.Uuid()),
        sa.Column("invite_id", sa.Uuid()),
        sa.Column("session_id", sa.Uuid()),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column(
            "result",
            sa.Enum("SUCCESS", "FAILED", "BLOCKED", name="audit_result_enum", native_enum=False),
            nullable=False,
        ),
        sa.Column("metadata_json", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.user_id"], name="fk_audit_actor"),
        sa.ForeignKeyConstraint(["case_id"], ["cases.case_id"], name="fk_audit_case"),
        sa.ForeignKeyConstraint(
            ["invite_id"], ["session_invites.invite_id"], name="fk_audit_invite"
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["patient_sessions.session_id"], name="fk_audit_session"
        ),
        sa.PrimaryKeyConstraint("audit_id", name="pk_audit_logs"),
    )
    op.create_index("ix_audit_logs_case_created", "audit_logs", ["case_id", "created_at"])
    op.create_index("ix_audit_logs_actor_created", "audit_logs", ["actor_user_id", "created_at"])
    op.create_index("ix_audit_logs_action_created", "audit_logs", ["action", "created_at"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("idempotency_records")
    op.drop_table("patient_sessions")
    op.drop_table("session_invites")
    op.drop_table("cases")
    op.drop_table("staff_access_sessions")
    op.drop_table("users")
