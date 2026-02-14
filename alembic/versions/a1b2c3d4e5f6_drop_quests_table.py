"""Drop quests table and quest_status_enum

Revision ID: a1b2c3d4e5f6
Revises: f23a21896dfa
Create Date: 2026-02-14 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "f23a21896dfa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("quests")
    # Drop the PostgreSQL enum type created for quest status
    op.execute("DROP TYPE IF EXISTS quest_status_enum")


def downgrade() -> None:
    # Re-create the enum type
    quest_status_enum = sa.Enum("open", name="quest_status_enum")
    quest_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "quests",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("guild_id", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("xp_reward", sa.Integer(), server_default="50"),
        sa.Column("gold_reward", sa.Integer(), server_default="0"),
        sa.Column(
            "status",
            sa.Enum("open", name="quest_status_enum"),
            server_default="open",
        ),
        sa.Column("github_issue_url", sa.String(500), nullable=True),
        sa.Column("active", sa.Boolean(), server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
