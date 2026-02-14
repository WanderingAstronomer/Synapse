"""Drop brand_configs table

Revision ID: f3a7b9d2e1c6
Revises: e2f4a8c1d3b5
Create Date: 2026-02-14 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "f3a7b9d2e1c6"
down_revision = "e2f4a8c1d3b5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Drop the brand_configs table.

    Brand fields have been redistributed:
    - site_name / site_subtitle → hero card card_config (title / subtitle)
    - hero_image_url → hero card card_config (background_image)
    - favicon_url / primary_color → settings table (category: appearance)
    - banner_image_url → deleted (unused)
    """
    op.drop_table("brand_configs")


def downgrade() -> None:
    """Recreate brand_configs table for rollback."""
    op.create_table(
        "brand_configs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("guild_id", sa.BigInteger, nullable=False, unique=True),
        sa.Column("site_name", sa.String(100), nullable=False, server_default="Synapse"),
        sa.Column("site_subtitle", sa.String(200), nullable=False, server_default="Community Dashboard"),
        sa.Column("favicon_url", sa.String(500), nullable=True),
        sa.Column("hero_image_url", sa.String(500), nullable=True),
        sa.Column("banner_image_url", sa.String(500), nullable=True),
        sa.Column("primary_color", sa.String(20), nullable=True),
        sa.Column("updated_by", sa.BigInteger, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
