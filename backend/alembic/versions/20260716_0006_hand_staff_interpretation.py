"""Persist current hand and notation-staff interpretation."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260716_0006"
down_revision: str | None = "20260716_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("projects") as batch_op:
        batch_op.add_column(sa.Column("current_interpretation_run_id", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "interpretation_revision",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )
        batch_op.create_check_constraint(
            "ck_projects_interpretation_revision_nonnegative",
            "interpretation_revision >= 0",
        )

    ambiguity_reason = sa.Enum(
        "CLOSE_ALTERNATIVE",
        "MIDDLE_REGISTER",
        "WIDE_CHORD",
        "CROSSING",
        "INSUFFICIENT_CONTEXT",
        name="assignmentambiguityreason",
        native_enum=False,
    )
    with op.batch_alter_table("note_events") as batch_op:
        batch_op.add_column(
            sa.Column(
                "staff",
                sa.Enum("TREBLE", "BASS", "UNKNOWN", name="staff", native_enum=False),
                nullable=False,
                server_default="UNKNOWN",
            )
        )
        batch_op.add_column(sa.Column("hand_confidence", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("staff_confidence", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("hand_ambiguity_reason", ambiguity_reason, nullable=True))
        batch_op.add_column(
            sa.Column(
                "staff_ambiguity_reason",
                sa.Enum(
                    "CLOSE_ALTERNATIVE",
                    "MIDDLE_REGISTER",
                    "WIDE_CHORD",
                    "CROSSING",
                    "INSUFFICIENT_CONTEXT",
                    name="assignmentambiguityreason",
                    native_enum=False,
                ),
                nullable=True,
            )
        )
        batch_op.create_check_constraint(
            "ck_note_events_hand_confidence",
            "hand_confidence IS NULL OR (hand_confidence >= 0 AND hand_confidence <= 1)",
        )
        batch_op.create_check_constraint(
            "ck_note_events_staff_confidence",
            "staff_confidence IS NULL OR (staff_confidence >= 0 AND staff_confidence <= 1)",
        )


def downgrade() -> None:
    with op.batch_alter_table("note_events") as batch_op:
        batch_op.drop_constraint("ck_note_events_staff_confidence", type_="check")
        batch_op.drop_constraint("ck_note_events_hand_confidence", type_="check")
        batch_op.drop_column("staff_ambiguity_reason")
        batch_op.drop_column("hand_ambiguity_reason")
        batch_op.drop_column("staff_confidence")
        batch_op.drop_column("hand_confidence")
        batch_op.drop_column("staff")

    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_constraint("ck_projects_interpretation_revision_nonnegative", type_="check")
        batch_op.drop_column("interpretation_revision")
        batch_op.drop_column("current_interpretation_run_id")
