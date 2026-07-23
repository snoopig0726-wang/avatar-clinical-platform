"""Add mock authorization, risk rules and patient adjustments."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260721_0003"
down_revision: str | None = "20260721_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "avatar_versions",
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("source_visual_feature_id", sa.Uuid()),
        sa.Column("generation_round", sa.Integer(), nullable=False),
        sa.Column("image_object_key", sa.String(512)),
        sa.Column("provider_kind", sa.String(50), nullable=False),
        sa.Column("safety_status", sa.String(32), nullable=False),
        sa.Column("doctor_review_status", sa.String(32), nullable=False),
        sa.Column("is_current_candidate", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["case_id"], ["cases.case_id"], name="fk_avatar_versions_case_id_cases"
        ),
        sa.ForeignKeyConstraint(
            ["source_visual_feature_id"],
            ["visual_features.visual_feature_id"],
            name="fk_avatar_versions_source_visual_feature_id_visual_features",
        ),
        sa.PrimaryKeyConstraint("version_id", name="pk_avatar_versions"),
    )
    op.create_index("ix_avatar_versions_case_created", "avatar_versions", ["case_id", "created_at"])
    op.create_table(
        "session_avatar_authorizations",
        sa.Column("authorization_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("AUTHORIZED", "REVOKED", name="authorization_status_enum", native_enum=False),
            nullable=False,
        ),
        sa.Column("authorized_by", sa.Uuid(), nullable=False),
        sa.Column("authorized_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revoke_reason", sa.String(100)),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["patient_sessions.session_id"],
            name="fk_session_avatar_authorizations_session_id_patient_sessions",
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["avatar_versions.version_id"],
            name="fk_session_avatar_authorizations_version_id_avatar_versions",
        ),
        sa.ForeignKeyConstraint(
            ["authorized_by"],
            ["users.user_id"],
            name="fk_session_avatar_authorizations_authorized_by_users",
        ),
        sa.PrimaryKeyConstraint("authorization_id", name="pk_session_avatar_authorizations"),
    )
    op.create_index(
        "ix_authorizations_session_status",
        "session_avatar_authorizations",
        ["session_id", "status"],
    )
    op.create_table(
        "risk_rules",
        sa.Column("rule_id", sa.Uuid(), nullable=False),
        sa.Column("rule_code", sa.String(20), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column(
            "rule_type",
            sa.Enum("DIRECT", "CONTEXT", "PII", name="risk_rule_type_enum", native_enum=False),
            nullable=False,
        ),
        sa.Column("trigger_terms", sa.JSON(), nullable=False),
        sa.Column("context_terms", sa.JSON()),
        sa.Column("exclusion_terms", sa.JSON()),
        sa.Column("patient_message_type", sa.String(32), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("rule_id", name="pk_risk_rules"),
        sa.UniqueConstraint("rule_code", name="uq_risk_rules_rule_code"),
    )
    op.create_index("ix_risk_rules_enabled_type", "risk_rules", ["is_enabled", "rule_type"])
    op.create_table(
        "adjustment_requests",
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("submitted_text_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("risk_status", sa.String(32), nullable=False),
        sa.Column("risk_rule_version", sa.String(32), nullable=False),
        sa.Column(
            "doctor_status",
            sa.Enum(
                "PENDING_DOCTOR_REVIEW",
                "APPROVED_AS_IS",
                "APPROVED_EDITED",
                "REJECTED",
                "GENERATING",
                "APPLIED",
                "GENERATION_FAILED",
                "CANCELLED",
                name="adjustment_status_enum",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("reviewed_instruction_encrypted", sa.LargeBinary()),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("reviewed_by", sa.Uuid()),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["case_id"], ["cases.case_id"], name="fk_adjustment_requests_case_id_cases"
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["patient_sessions.session_id"],
            name="fk_adjustment_requests_session_id_patient_sessions",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"], ["users.user_id"], name="fk_adjustment_requests_reviewed_by_users"
        ),
        sa.PrimaryKeyConstraint("request_id", name="pk_adjustment_requests"),
        sa.UniqueConstraint("case_id", "sequence_no", name="uq_adjustment_case_sequence"),
    )
    op.create_index(
        "ix_adjustment_case_status", "adjustment_requests", ["case_id", "doctor_status"]
    )
    op.create_index(
        "ix_adjustment_session_submitted",
        "adjustment_requests",
        ["session_id", "submitted_at"],
    )


def downgrade() -> None:
    op.drop_table("adjustment_requests")
    op.drop_table("risk_rules")
    op.drop_table("session_avatar_authorizations")
    op.drop_table("avatar_versions")
