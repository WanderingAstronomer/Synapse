"""add expires_at to marketplace_items

Revision ID: a9c2d4e6f8b1
Revises: c8a034d6e30e
Create Date: 2026-02-19 00:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "a9c2d4e6f8b1"
down_revision = "c8a034d6e30e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "marketplace_items",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("marketplace_items", "expires_at")
