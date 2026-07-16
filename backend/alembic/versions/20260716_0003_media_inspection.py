"""Persist inspected media and stream metadata."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260716_0003"
down_revision: str | None = "20260714_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("projects") as batch_op:
        batch_op.add_column(sa.Column("duration_seconds", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("container_format", sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column("source_bit_rate", sa.Integer(), nullable=True))

    op.create_table(
        "media_streams",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("stream_index", sa.Integer(), nullable=False),
        sa.Column(
            "stream_type",
            sa.Enum("AUDIO", "VIDEO", "OTHER", name="mediastreamtype", native_enum=False),
            nullable=False,
        ),
        sa.Column("codec_name", sa.String(length=100), nullable=True),
        sa.Column("codec_long_name", sa.String(length=255), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("bit_rate", sa.Integer(), nullable=True),
        sa.Column("sample_rate", sa.Integer(), nullable=True),
        sa.Column("channels", sa.Integer(), nullable=True),
        sa.Column("channel_layout", sa.String(length=100), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("frame_rate", sa.String(length=50), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "stream_index",
            name="uq_media_stream_project_index",
        ),
    )


def downgrade() -> None:
    op.drop_table("media_streams")
    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_column("source_bit_rate")
        batch_op.drop_column("container_format")
        batch_op.drop_column("duration_seconds")
