"""Add oauth_states and admin_rate_limit_events tables

Revision ID: d1a9e5c7f2b1
Revises: b3f7a92c1d4e
Create Date: 2026-02-13 12:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d1a9e5c7f2b1"
down_revision: str | Sequence[str] | None = "c4e8f1a2b5d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create durable state tables for auth and admin rate-limiting."""
    op.create_table(
        "oauth_states",
        sa.Column("state", sa.String(128), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_oauth_states_created_at", "oauth_states", ["created_at"])

    op.create_table(
        "admin_rate_limit_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("admin_id", sa.String(64), nullable=False),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_admin_rate_limit_admin_ts",
        "admin_rate_limit_events",
        ["admin_id", "timestamp"],
    )
    op.create_index(
        "ix_admin_rate_limit_ts",
        "admin_rate_limit_events",
        ["timestamp"],
    )


def downgrade() -> None:
    """Drop auth/rate-limit durable state tables."""
    op.drop_index("ix_admin_rate_limit_ts", table_name="admin_rate_limit_events")
    op.drop_index("ix_admin_rate_limit_admin_ts", table_name="admin_rate_limit_events")
    op.drop_table("admin_rate_limit_events")

    op.drop_index("ix_oauth_states_created_at", table_name="oauth_states")
    op.drop_table("oauth_states")
