"""Add Q1-Q8 sound descriptions and mapped visual features."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260721_0002"
down_revision: str | None = "20260721_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sound_descriptions",
        sa.Column("sound_description_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("voice_gender", sa.String(32)),
        sa.Column("age_sense", sa.String(32)),
        sa.Column("pitch_level", sa.Integer()),
        sa.Column("speaking_rate_level", sa.Integer()),
        sa.Column("timbre", sa.String(32)),
        sa.Column("emotions", sa.JSON()),
        sa.Column("power_level", sa.Integer()),
        sa.Column("malice_level", sa.Integer()),
        sa.Column("answered_questions", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["case_id"], ["cases.case_id"], name="fk_sound_descriptions_case_id_cases"
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["patient_sessions.session_id"],
            name="fk_sound_descriptions_session_id_patient_sessions",
        ),
        sa.PrimaryKeyConstraint("sound_description_id", name="pk_sound_descriptions"),
        sa.UniqueConstraint("session_id", name="uq_sound_descriptions_session_id"),
    )
    op.create_index(
        "ix_sound_descriptions_case_updated",
        "sound_descriptions",
        ["case_id", "updated_at"],
    )
    op.create_index("ix_sound_descriptions_session", "sound_descriptions", ["session_id"])

    op.create_table(
        "visual_features",
        sa.Column("visual_feature_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("source_sound_description_id", sa.Uuid(), nullable=False),
        sa.Column("system_result_json", sa.JSON(), nullable=False),
        sa.Column("doctor_edited_json", sa.JSON()),
        sa.Column("effective_json", sa.JSON(), nullable=False),
        sa.Column("mapping_explanation", sa.JSON()),
        sa.Column("mapping_version", sa.String(100), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("confirmed_by", sa.Uuid()),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["case_id"], ["cases.case_id"], name="fk_visual_features_case_id_cases"
        ),
        sa.ForeignKeyConstraint(
            ["source_sound_description_id"],
            ["sound_descriptions.sound_description_id"],
            name="fk_visual_features_source_sound_description",
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_by"], ["users.user_id"], name="fk_visual_features_confirmed_by_users"
        ),
        sa.PrimaryKeyConstraint("visual_feature_id", name="pk_visual_features"),
    )
    op.create_index("ix_visual_features_case_current", "visual_features", ["case_id", "is_current"])
    op.create_index("ix_visual_features_source", "visual_features", ["source_sound_description_id"])


def downgrade() -> None:
    op.drop_table("visual_features")
    op.drop_table("sound_descriptions")
