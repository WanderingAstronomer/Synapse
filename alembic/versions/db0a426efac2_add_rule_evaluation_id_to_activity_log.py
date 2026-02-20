"""add_rule_evaluation_id_to_activity_log

Revision ID: db0a426efac2
Revises: f0be0607f872
Create Date: 2026-02-19 16:51:43.782307

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "db0a426efac2"
down_revision: str | Sequence[str] | None = "f0be0607f872"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "activity_log",
        sa.Column("rule_evaluation_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "fk_activity_log_rule_eval",
        "activity_log",
        "rule_evaluations",
        ["rule_evaluation_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("fk_activity_log_rule_eval", "activity_log", type_="foreignkey")
    op.drop_column("activity_log", "rule_evaluation_id")

