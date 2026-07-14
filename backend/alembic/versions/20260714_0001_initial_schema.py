"""Create the initial Pianova schema."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260714_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column(
            "status",
            sa.Enum("CREATED", "UPLOADED", "FAILED", name="projectstatus", native_enum=False),
            nullable=False,
        ),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("media_type", sa.String(length=100), nullable=True),
        sa.Column("source_size_bytes", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "artifacts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "SOURCE",
                "NORMALIZED_AUDIO",
                "NOTE_EVENTS",
                "RAW_MIDI",
                "CLEAN_MIDI",
                "MUSICXML",
                "PDF",
                name="artifactkind",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("relative_path", sa.String(length=500), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "note_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("pitch", sa.Integer(), nullable=False),
        sa.Column("velocity", sa.Integer(), nullable=False),
        sa.Column("raw_start_seconds", sa.Float(), nullable=False),
        sa.Column("raw_end_seconds", sa.Float(), nullable=False),
        sa.Column("symbolic_start_beats", sa.Float(), nullable=True),
        sa.Column("symbolic_duration_beats", sa.Float(), nullable=True),
        sa.Column(
            "hand",
            sa.Enum("LEFT", "RIGHT", "UNKNOWN", name="hand", native_enum=False),
            nullable=False,
        ),
        sa.Column(
            "source",
            sa.Enum(
                "AUDIO",
                "VIDEO",
                "AUDIO_AND_VIDEO",
                "MANUAL",
                name="detectionsource",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "processing_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("stage", sa.String(length=100), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "RUNNING",
                "SUCCEEDED",
                "FAILED",
                name="processingstatus",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("processing_runs")
    op.drop_table("note_events")
    op.drop_table("artifacts")
    op.drop_table("projects")
