"""Add page_layouts, card_configs, and brand_configs tables

Revision ID: b3f7a92c1d4e
Revises: 99b1d42a3d9c
Create Date: 2026-02-12 18:45:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3f7a92c1d4e"
down_revision: str | Sequence[str] | None = "99b1d42a3d9c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create page_layouts, card_configs, and brand_configs tables for the
    edit-mode card system (Phase 3).
    """

    # --- page_layouts ---
    op.create_table(
        "page_layouts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("guild_id", sa.BigInteger, nullable=False),
        sa.Column("page_slug", sa.String(50), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("layout_json", postgresql.JSONB, nullable=True),
        sa.Column("updated_by", sa.BigInteger, nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_unique_constraint(
        "uq_page_layouts_guild_slug", "page_layouts",
        ["guild_id", "page_slug"],
    )

    # --- card_configs ---
    op.create_table(
        "card_configs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "page_layout_id", sa.String(36),
            sa.ForeignKey("page_layouts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("card_type", sa.String(50), nullable=False),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        sa.Column("grid_span", sa.Integer, nullable=False, server_default="1"),
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column("subtitle", sa.String(500), nullable=True),
        sa.Column("config_json", postgresql.JSONB, nullable=True),
        sa.Column("visible", sa.Boolean, server_default=sa.text("true")),
    )
    op.create_index(
        "ix_card_configs_page_layout", "card_configs",
        ["page_layout_id", "position"],
    )

    # --- brand_configs ---
    op.create_table(
        "brand_configs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("guild_id", sa.BigInteger, nullable=False, unique=True),
        sa.Column(
            "site_name", sa.String(100), nullable=False,
            server_default="Synapse",
        ),
        sa.Column(
            "site_subtitle", sa.String(200), nullable=False,
            server_default="Community Dashboard",
        ),
        sa.Column("favicon_url", sa.String(500), nullable=True),
        sa.Column("hero_image_url", sa.String(500), nullable=True),
        sa.Column("banner_image_url", sa.String(500), nullable=True),
        sa.Column("primary_color", sa.String(20), nullable=True),
        sa.Column("updated_by", sa.BigInteger, nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    """Drop the Phase 3 tables in reverse order."""
    op.drop_table("card_configs")
    op.drop_table("page_layouts")
    op.drop_table("brand_configs")
