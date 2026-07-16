"""Persist current global timing and quantized chord evidence."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260716_0005"
down_revision: str | None = "20260716_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("projects") as batch_op:
        batch_op.add_column(sa.Column("estimated_tempo_bpm", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("selected_tempo_bpm", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("tempo_source", sa.String(length=9), nullable=True))
        batch_op.add_column(sa.Column("measure_origin_seconds", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("measure_origin_source", sa.String(length=8), nullable=True))
        batch_op.add_column(sa.Column("meter_numerator", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("meter_denominator", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("meter_source", sa.String(length=8), nullable=True))
        batch_op.add_column(sa.Column("current_quantization_run_id", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "quantization_revision",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )
        batch_op.create_check_constraint(
            "ck_projects_estimated_tempo_positive",
            "estimated_tempo_bpm IS NULL OR estimated_tempo_bpm > 0",
        )
        batch_op.create_check_constraint(
            "ck_projects_selected_tempo_positive",
            "selected_tempo_bpm IS NULL OR selected_tempo_bpm > 0",
        )
        batch_op.create_check_constraint(
            "ck_projects_simple_meter",
            (
                "(meter_numerator IS NULL AND meter_denominator IS NULL) OR "
                "(meter_numerator IN (2, 3, 4) AND meter_denominator = 4)"
            ),
        )
        batch_op.create_check_constraint(
            "ck_projects_quantization_revision_nonnegative",
            "quantization_revision >= 0",
        )
        batch_op.create_check_constraint(
            "ck_projects_quantization_metadata_complete",
            (
                "("
                "selected_tempo_bpm IS NULL AND tempo_source IS NULL AND "
                "measure_origin_seconds IS NULL AND measure_origin_source IS NULL AND "
                "meter_numerator IS NULL AND meter_denominator IS NULL AND "
                "meter_source IS NULL AND current_quantization_run_id IS NULL"
                ") OR ("
                "selected_tempo_bpm IS NOT NULL AND tempo_source IS NOT NULL AND "
                "measure_origin_seconds IS NOT NULL AND measure_origin_source IS NOT NULL AND "
                "meter_numerator IS NOT NULL AND meter_denominator IS NOT NULL AND "
                "meter_source IS NOT NULL AND current_quantization_run_id IS NOT NULL"
                ")"
            ),
        )

    with op.batch_alter_table("note_events") as batch_op:
        batch_op.add_column(sa.Column("chord_group", sa.Integer(), nullable=True))
        batch_op.create_check_constraint(
            "ck_note_events_chord_group_positive",
            "chord_group IS NULL OR chord_group > 0",
        )


def downgrade() -> None:
    with op.batch_alter_table("note_events") as batch_op:
        batch_op.drop_constraint("ck_note_events_chord_group_positive", type_="check")
        batch_op.drop_column("chord_group")

    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_constraint("ck_projects_quantization_metadata_complete", type_="check")
        batch_op.drop_constraint("ck_projects_quantization_revision_nonnegative", type_="check")
        batch_op.drop_constraint("ck_projects_simple_meter", type_="check")
        batch_op.drop_constraint("ck_projects_selected_tempo_positive", type_="check")
        batch_op.drop_constraint("ck_projects_estimated_tempo_positive", type_="check")
        batch_op.drop_column("quantization_revision")
        batch_op.drop_column("current_quantization_run_id")
        batch_op.drop_column("meter_source")
        batch_op.drop_column("meter_denominator")
        batch_op.drop_column("meter_numerator")
        batch_op.drop_column("measure_origin_source")
        batch_op.drop_column("measure_origin_seconds")
        batch_op.drop_column("tempo_source")
        batch_op.drop_column("selected_tempo_bpm")
        batch_op.drop_column("estimated_tempo_bpm")
