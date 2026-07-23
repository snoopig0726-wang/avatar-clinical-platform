"""Add the provider-independent Avatar generation state machine."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260722_0005"
down_revision: str | None = "20260722_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    generation_mode = sa.Enum(
        "INITIAL",
        "SAME_FEATURES_REGENERATE",
        "FEATURE_UPDATE",
        "PATIENT_ADJUSTMENT",
        name="generation_mode_enum",
        native_enum=False,
    )
    generation_status = sa.Enum(
        "QUEUED",
        "GENERATING",
        "CHECKING",
        "PENDING_DOCTOR_REVIEW",
        "APPROVED",
        "REJECTED",
        "FAILED",
        "CANCELLED",
        name="generation_status_enum",
        native_enum=False,
    )
    op.add_column(
        "avatar_versions",
        sa.Column("generation_mode", generation_mode, nullable=False, server_default="INITIAL"),
    )
    op.add_column(
        "avatar_versions",
        sa.Column(
            "generation_status",
            generation_status,
            nullable=False,
            server_default="APPROVED",
        ),
    )
    op.add_column(
        "avatar_versions",
        sa.Column("provider_model", sa.String(100), nullable=False, server_default="legacy-mock"),
    )
    op.add_column("avatar_versions", sa.Column("provider_request_id", sa.String(200)))
    op.add_column(
        "avatar_versions",
        sa.Column(
            "prompt_template_version", sa.String(100), nullable=False, server_default="legacy-v0"
        ),
    )
    op.add_column(
        "avatar_versions",
        sa.Column(
            "prompt_sha256",
            sa.LargeBinary(),
            nullable=False,
            server_default=sa.text("decode('', 'hex')"),
        ),
    )
    op.add_column("avatar_versions", sa.Column("output_mime_type", sa.String(50)))
    op.add_column("avatar_versions", sa.Column("image_width", sa.Integer()))
    op.add_column("avatar_versions", sa.Column("image_height", sa.Integer()))
    op.add_column("avatar_versions", sa.Column("failure_code", sa.String(100)))
    op.add_column("avatar_versions", sa.Column("source_adjustment_request_id", sa.Uuid()))
    op.add_column(
        "avatar_versions", sa.Column("started_at", sa.DateTime(timezone=True))
    )
    op.add_column(
        "avatar_versions", sa.Column("completed_at", sa.DateTime(timezone=True))
    )
    op.create_foreign_key(
        "fk_avatar_versions_source_adjustment_request_id_adjustments",
        "avatar_versions",
        "adjustment_requests",
        ["source_adjustment_request_id"],
        ["request_id"],
    )
    op.create_index(
        "ix_avatar_versions_case_status",
        "avatar_versions",
        ["case_id", "generation_status"],
    )
    op.alter_column("avatar_versions", "generation_mode", server_default=None)
    op.alter_column("avatar_versions", "generation_status", server_default=None)
    op.alter_column("avatar_versions", "provider_model", server_default=None)
    op.alter_column("avatar_versions", "prompt_template_version", server_default=None)
    op.alter_column("avatar_versions", "prompt_sha256", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_avatar_versions_case_status", table_name="avatar_versions")
    op.drop_constraint(
        "fk_avatar_versions_source_adjustment_request_id_adjustments",
        "avatar_versions",
        type_="foreignkey",
    )
    for name in (
        "completed_at",
        "started_at",
        "source_adjustment_request_id",
        "failure_code",
        "image_height",
        "image_width",
        "output_mime_type",
        "prompt_sha256",
        "prompt_template_version",
        "provider_request_id",
        "provider_model",
        "generation_status",
        "generation_mode",
    ):
        op.drop_column("avatar_versions", name)
