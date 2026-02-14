"""Channel-first reward rules redesign

Drop the 6-table category/group/rule hierarchy and replace with
ChannelTypeDefault + ChannelOverride.  Also removes category_id from
activity_log and event_counters.

Revision ID: e2f4a8c1d3b5
Revises: d1a9e5c7f2b1
Create Date: 2026-02-13 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "e2f4a8c1d3b5"
down_revision = "d1a9e5c7f2b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Drop old tables (order matters for FK deps) ---
    op.drop_table("channel_group_members")
    op.drop_table("channel_groups")
    op.drop_table("category_multipliers")
    op.drop_table("category_channels")
    op.drop_table("reward_rules")

    # ActivityLog FK + index must go before categories table
    op.drop_index("ix_activity_log_category_time", table_name="activity_log")
    op.drop_constraint(
        "activity_log_category_id_fkey", "activity_log", type_="foreignkey"
    )
    op.drop_column("activity_log", "category_id")

    op.drop_table("categories")

    # --- Recreate event_counters without category_id ---
    op.drop_table("event_counters")
    op.create_table(
        "event_counters",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("period", sa.String(16), nullable=False),
        sa.Column("count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("user_id", "event_type", "period"),
    )

    # --- Create new tables ---
    op.create_table(
        "channel_type_defaults",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("guild_id", sa.BigInteger(), nullable=False),
        sa.Column("channel_type", sa.String(20), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("xp_multiplier", sa.Float(), server_default="1.0"),
        sa.Column("star_multiplier", sa.Float(), server_default="1.0"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "guild_id", "channel_type", "event_type",
            name="uq_type_defaults_guild_type_event",
        ),
    )
    op.create_index("ix_type_defaults_guild", "channel_type_defaults", ["guild_id"])

    op.create_table(
        "channel_overrides",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("guild_id", sa.BigInteger(), nullable=False),
        sa.Column("channel_id", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("xp_multiplier", sa.Float(), server_default="1.0"),
        sa.Column("star_multiplier", sa.Float(), server_default="1.0"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "guild_id", "channel_id", "event_type",
            name="uq_overrides_guild_channel_event",
        ),
    )
    op.create_index("ix_overrides_channel", "channel_overrides", ["channel_id"])

    # Drop the old RuleScope enum type if it exists (PG only)
    op.execute("DROP TYPE IF EXISTS rulescope")


def downgrade() -> None:
    # Not implementing downgrade — nuking is fine at this stage
    raise NotImplementedError("Downgrade not supported for channel-first migration")
