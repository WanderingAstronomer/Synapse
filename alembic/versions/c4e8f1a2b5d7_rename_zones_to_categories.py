"""rename zones to categories

Revision ID: c4e8f1a2b5d7
Revises: b3f7a92c1d4e
Create Date: 2026-02-12 00:00:00.000000

"""
from alembic import op

# revision identifiers
revision = "c4e8f1a2b5d7"
down_revision = "b3f7a92c1d4e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Rename tables ---
    op.rename_table("zones", "categories")
    op.rename_table("zone_channels", "category_channels")
    op.rename_table("zone_multipliers", "category_multipliers")

    # --- Rename columns ---
    # category_channels.zone_id → category_id
    op.alter_column("category_channels", "zone_id", new_column_name="category_id")
    # category_multipliers.zone_id → category_id
    op.alter_column("category_multipliers", "zone_id", new_column_name="category_id")
    # activity_log.zone_id → category_id
    op.alter_column("activity_log", "zone_id", new_column_name="category_id")
    # event_counters.zone_id → category_id
    op.alter_column("event_counters", "zone_id", new_column_name="category_id")

    # --- Rename indexes ---
    op.execute("ALTER INDEX IF EXISTS ix_zone_channels_channel_id RENAME TO ix_category_channels_channel_id")
    op.execute("ALTER INDEX IF EXISTS ix_activity_log_zone_time RENAME TO ix_activity_log_category_time")

    # --- Rename constraints ---
    op.execute("ALTER TABLE categories RENAME CONSTRAINT uq_zones_guild_name TO uq_categories_guild_name")
    op.execute("ALTER TABLE category_multipliers RENAME CONSTRAINT uq_zone_mult_zone_type TO uq_category_mult_category_type")


def downgrade() -> None:
    # --- Revert constraint renames ---
    op.execute("ALTER TABLE category_multipliers RENAME CONSTRAINT uq_category_mult_category_type TO uq_zone_mult_zone_type")
    op.execute("ALTER TABLE categories RENAME CONSTRAINT uq_categories_guild_name TO uq_zones_guild_name")

    # --- Revert index renames ---
    op.execute("ALTER INDEX IF EXISTS ix_activity_log_category_time RENAME TO ix_activity_log_zone_time")
    op.execute("ALTER INDEX IF EXISTS ix_category_channels_channel_id RENAME TO ix_zone_channels_channel_id")

    # --- Revert column renames ---
    op.alter_column("event_counters", "category_id", new_column_name="zone_id")
    op.alter_column("activity_log", "category_id", new_column_name="zone_id")
    op.alter_column("category_multipliers", "category_id", new_column_name="zone_id")
    op.alter_column("category_channels", "category_id", new_column_name="zone_id")

    # --- Revert table renames ---
    op.rename_table("category_multipliers", "zone_multipliers")
    op.rename_table("category_channels", "zone_channels")
    op.rename_table("categories", "zones")
