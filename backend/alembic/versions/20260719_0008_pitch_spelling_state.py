"""Persist current key detection and enharmonic spelling state."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260719_0008"
down_revision: str | None = "20260718_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("projects") as batch_op:
        batch_op.add_column(sa.Column("key_tonic_step", sa.String(length=1), nullable=True))
        batch_op.add_column(sa.Column("key_tonic_alter", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "key_mode",
                sa.Enum("MAJOR", "MINOR", name="keymode", native_enum=False),
                nullable=True,
            )
        )
        batch_op.add_column(sa.Column("key_confidence", sa.Float(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "key_ambiguity_reason",
                sa.Enum(
                    "INSUFFICIENT_NOTES",
                    "AMBIGUOUS_KEY",
                    name="keyambiguityreason",
                    native_enum=False,
                ),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "key_source",
                sa.Enum("ESTIMATED", "OVERRIDE", name="keysource", native_enum=False),
                nullable=True,
            )
        )
        batch_op.add_column(sa.Column("current_spelling_run_id", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "spelling_revision",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )
        batch_op.create_check_constraint(
            "ck_projects_spelling_revision_nonnegative",
            "spelling_revision >= 0",
        )
        batch_op.create_check_constraint(
            "ck_projects_key_tonic_step",
            "key_tonic_step IS NULL OR key_tonic_step IN ('A', 'B', 'C', 'D', 'E', 'F', 'G')",
        )
        batch_op.create_check_constraint(
            "ck_projects_key_tonic_alter",
            "key_tonic_alter IS NULL OR key_tonic_alter BETWEEN -1 AND 1",
        )
        batch_op.create_check_constraint(
            "ck_projects_key_confidence",
            "key_confidence IS NULL OR key_confidence BETWEEN 0 AND 1",
        )
        batch_op.create_check_constraint(
            "ck_projects_key_state",
            "(key_tonic_step IS NULL AND key_tonic_alter IS NULL "
            "AND key_mode IS NULL AND key_confidence IS NULL "
            "AND key_ambiguity_reason IS NULL AND key_source IS NULL "
            "AND current_spelling_run_id IS NULL) OR "
            "(key_tonic_step IS NOT NULL AND key_tonic_alter IS NOT NULL "
            "AND key_mode IS NOT NULL AND key_confidence IS NOT NULL "
            "AND key_ambiguity_reason IS NULL AND key_source = 'ESTIMATED' "
            "AND current_spelling_run_id IS NOT NULL) OR "
            "(key_tonic_step IS NULL AND key_tonic_alter IS NULL "
            "AND key_mode IS NULL AND key_confidence IS NOT NULL "
            "AND key_ambiguity_reason IS NOT NULL AND key_source = 'ESTIMATED' "
            "AND current_spelling_run_id IS NOT NULL) OR "
            "(key_tonic_step IS NOT NULL AND key_tonic_alter IS NOT NULL "
            "AND key_mode IS NOT NULL AND key_confidence IS NULL "
            "AND key_ambiguity_reason IS NULL AND key_source = 'OVERRIDE' "
            "AND current_spelling_run_id IS NOT NULL)",
        )

    with op.batch_alter_table("note_events") as batch_op:
        batch_op.add_column(sa.Column("spelled_step", sa.String(length=1), nullable=True))
        batch_op.add_column(sa.Column("spelled_alter", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("spelled_octave", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("spelling_confidence", sa.Float(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "spelling_ambiguity_reason",
                sa.Enum(
                    "UNKNOWN_KEY",
                    "CLOSE_ALTERNATIVE",
                    name="spellingambiguityreason",
                    native_enum=False,
                ),
                nullable=True,
            )
        )
        batch_op.create_check_constraint(
            "ck_note_events_spelled_step",
            "spelled_step IS NULL OR spelled_step IN ('A', 'B', 'C', 'D', 'E', 'F', 'G')",
        )
        batch_op.create_check_constraint(
            "ck_note_events_spelled_alter",
            "spelled_alter IS NULL OR spelled_alter BETWEEN -2 AND 2",
        )
        batch_op.create_check_constraint(
            "ck_note_events_spelled_octave",
            "spelled_octave IS NULL OR spelled_octave BETWEEN -2 AND 9",
        )
        batch_op.create_check_constraint(
            "ck_note_events_spelling_confidence",
            "spelling_confidence IS NULL OR spelling_confidence BETWEEN 0 AND 1",
        )
        batch_op.create_check_constraint(
            "ck_note_events_spelling_state",
            "(spelled_step IS NULL AND spelled_alter IS NULL "
            "AND spelled_octave IS NULL AND spelling_confidence IS NULL "
            "AND spelling_ambiguity_reason IS NULL) OR "
            "(spelled_step IS NOT NULL AND spelled_alter IS NOT NULL "
            "AND spelled_octave IS NOT NULL AND spelling_confidence IS NOT NULL "
            "AND spelling_ambiguity_reason IS NULL) OR "
            "(spelled_step IS NULL AND spelled_alter IS NULL "
            "AND spelled_octave IS NULL AND spelling_confidence IS NOT NULL "
            "AND spelling_ambiguity_reason IS NOT NULL)",
        )


def downgrade() -> None:
    with op.batch_alter_table("note_events") as batch_op:
        batch_op.drop_constraint("ck_note_events_spelling_state", type_="check")
        batch_op.drop_constraint("ck_note_events_spelling_confidence", type_="check")
        batch_op.drop_constraint("ck_note_events_spelled_octave", type_="check")
        batch_op.drop_constraint("ck_note_events_spelled_alter", type_="check")
        batch_op.drop_constraint("ck_note_events_spelled_step", type_="check")
        batch_op.drop_column("spelling_ambiguity_reason")
        batch_op.drop_column("spelling_confidence")
        batch_op.drop_column("spelled_octave")
        batch_op.drop_column("spelled_alter")
        batch_op.drop_column("spelled_step")

    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_constraint("ck_projects_key_state", type_="check")
        batch_op.drop_constraint("ck_projects_key_confidence", type_="check")
        batch_op.drop_constraint("ck_projects_key_tonic_alter", type_="check")
        batch_op.drop_constraint("ck_projects_key_tonic_step", type_="check")
        batch_op.drop_constraint("ck_projects_spelling_revision_nonnegative", type_="check")
        batch_op.drop_column("spelling_revision")
        batch_op.drop_column("current_spelling_run_id")
        batch_op.drop_column("key_source")
        batch_op.drop_column("key_ambiguity_reason")
        batch_op.drop_column("key_confidence")
        batch_op.drop_column("key_mode")
        batch_op.drop_column("key_tonic_alter")
        batch_op.drop_column("key_tonic_step")
