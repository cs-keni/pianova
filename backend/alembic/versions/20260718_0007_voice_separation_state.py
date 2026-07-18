"""Persist current notation-voice separation state."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260718_0007"
down_revision: str | None = "20260716_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("projects") as batch_op:
        batch_op.add_column(sa.Column("current_voice_run_id", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "voice_revision",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )
        batch_op.create_check_constraint(
            "ck_projects_voice_revision_nonnegative",
            "voice_revision >= 0",
        )

    with op.batch_alter_table("note_events") as batch_op:
        batch_op.add_column(sa.Column("voice", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("voice_confidence", sa.Float(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "voice_ambiguity_reason",
                sa.Enum(
                    "UNRESOLVED_STAFF",
                    "VOICE_CAPACITY_EXCEEDED",
                    "CROSSING",
                    "CLOSE_ALTERNATIVE",
                    name="voiceambiguityreason",
                    native_enum=False,
                ),
                nullable=True,
            )
        )
        batch_op.create_check_constraint(
            "ck_note_events_voice_positive",
            "voice IS NULL OR voice >= 1",
        )
        batch_op.create_check_constraint(
            "ck_note_events_voice_confidence",
            "voice_confidence IS NULL OR (voice_confidence >= 0 AND voice_confidence <= 1)",
        )
        batch_op.create_check_constraint(
            "ck_note_events_voice_state",
            "(voice IS NULL AND voice_confidence IS NULL "
            "AND voice_ambiguity_reason IS NULL) OR "
            "(voice IS NOT NULL AND voice_confidence IS NOT NULL "
            "AND voice_ambiguity_reason IS NULL) OR "
            "(voice IS NULL AND voice_confidence IS NOT NULL "
            "AND voice_ambiguity_reason IS NOT NULL)",
        )


def downgrade() -> None:
    with op.batch_alter_table("note_events") as batch_op:
        batch_op.drop_constraint("ck_note_events_voice_state", type_="check")
        batch_op.drop_constraint("ck_note_events_voice_confidence", type_="check")
        batch_op.drop_constraint("ck_note_events_voice_positive", type_="check")
        batch_op.drop_column("voice_ambiguity_reason")
        batch_op.drop_column("voice_confidence")
        batch_op.drop_column("voice")

    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_constraint("ck_projects_voice_revision_nonnegative", type_="check")
        batch_op.drop_column("voice_revision")
        batch_op.drop_column("current_voice_run_id")
