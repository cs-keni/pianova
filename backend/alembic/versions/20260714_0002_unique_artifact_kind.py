"""Allow one artifact of each kind per project."""

from collections.abc import Sequence

from alembic import op

revision: str = "20260714_0002"
down_revision: str | None = "20260714_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("artifacts") as batch_op:
        batch_op.create_unique_constraint("uq_artifact_project_kind", ["project_id", "kind"])


def downgrade() -> None:
    with op.batch_alter_table("artifacts") as batch_op:
        batch_op.drop_constraint("uq_artifact_project_kind", type_="unique")
