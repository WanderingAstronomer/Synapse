"""add evaluated_at index to rule_evaluations

Revision ID: e1f2a3b4c5d6
Revises: db0a426efac2
Create Date: 2026-02-19

Adds a single-column B-tree index on rule_evaluations.evaluated_at to support
global time-window scans that do not always filter on guild_id.  The existing
composite index (guild_id, evaluated_at) is preserved — this is an additive
change.

References: KNOWN_ISSUES.md P12-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e1f2a3b4c5d6"
down_revision: str | Sequence[str] | None = "db0a426efac2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_rule_evaluations_evaluated_at",
        "rule_evaluations",
        ["evaluated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_rule_evaluations_evaluated_at",
        table_name="rule_evaluations",
    )
