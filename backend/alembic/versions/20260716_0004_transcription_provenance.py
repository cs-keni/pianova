"""Persist raw transcription evidence and model provenance."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260716_0004"
down_revision: str | None = "20260716_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("note_events") as batch_op:
        batch_op.add_column(sa.Column("confidence", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("pitch_bends_json", sa.Text(), nullable=True))

    with op.batch_alter_table("processing_runs") as batch_op:
        batch_op.add_column(sa.Column("model_name", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("model_version", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("model_runtime", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("configuration_json", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("processing_runs") as batch_op:
        batch_op.drop_column("configuration_json")
        batch_op.drop_column("model_runtime")
        batch_op.drop_column("model_version")
        batch_op.drop_column("model_name")

    with op.batch_alter_table("note_events") as batch_op:
        batch_op.drop_column("pitch_bends_json")
        batch_op.drop_column("confidence")
