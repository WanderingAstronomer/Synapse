"""Add event_lake and event_counters tables

Revision ID: 99b1d42a3d9c
Revises:
Create Date: 2026-02-12 14:24:50.332492

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '99b1d42a3d9c'
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create event_lake and event_counters tables per 03B_DATA_LAKE.md."""

    # --- event_lake ---
    op.create_table(
        "event_lake",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("guild_id", sa.BigInteger, nullable=False),
        sa.Column("user_id", sa.BigInteger, nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("channel_id", sa.BigInteger, nullable=True),
        sa.Column("target_id", sa.BigInteger, nullable=True),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("source_id", sa.String(128), nullable=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Primary query pattern indexes (§3B.3)
    op.create_index(
        "idx_event_lake_user_ts", "event_lake",
        ["user_id", sa.text("timestamp DESC")],
    )
    op.create_index(
        "idx_event_lake_type_ts", "event_lake",
        ["event_type", sa.text("timestamp DESC")],
    )
    op.create_index(
        "idx_event_lake_guild_ts", "event_lake",
        ["guild_id", sa.text("timestamp DESC")],
    )
    op.create_index(
        "idx_event_lake_channel_ts", "event_lake",
        ["channel_id", sa.text("timestamp DESC")],
        postgresql_where=sa.text("channel_id IS NOT NULL"),
    )
    # Idempotency: unique partial index on source_id (§3B.3)
    op.create_index(
        "idx_event_lake_source", "event_lake",
        ["source_id"],
        unique=True,
        postgresql_where=sa.text("source_id IS NOT NULL"),
    )

    # --- event_counters ---
    op.create_table(
        "event_counters",
        sa.Column("user_id", sa.BigInteger, nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("zone_id", sa.Integer, nullable=False, server_default="0"),
        sa.Column("period", sa.String(16), nullable=False),
        sa.Column("count", sa.BigInteger, nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("user_id", "event_type", "zone_id", "period"),
    )


def downgrade() -> None:
    """Drop event_lake and event_counters tables."""
    op.drop_table("event_counters")
    op.drop_index("idx_event_lake_source", table_name="event_lake")
    op.drop_index("idx_event_lake_channel_ts", table_name="event_lake")
    op.drop_index("idx_event_lake_guild_ts", table_name="event_lake")
    op.drop_index("idx_event_lake_type_ts", table_name="event_lake")
    op.drop_index("idx_event_lake_user_ts", table_name="event_lake")
    op.drop_table("event_lake")
