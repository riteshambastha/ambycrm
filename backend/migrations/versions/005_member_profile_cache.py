"""Add member_profile_cache table for pre-cached connector data.

Revision ID: 005
Revises: 004
Create Date: 2026-02-25
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "member_profile_cache",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", UUID(as_uuid=True), nullable=False),
        sa.Column("work_email", sa.String(255), nullable=False),
        sa.Column("section", sa.String(50), nullable=False),
        sa.Column("connector_key", sa.String(100), nullable=False),
        sa.Column("results", JSONB, nullable=False, server_default="[]"),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("item_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "last_viewed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("org_id", "work_email", "section", name="uq_member_cache"),
    )
    op.create_index("ix_member_cache_org_email", "member_profile_cache", ["org_id", "work_email"])
    op.create_index("ix_member_cache_expires", "member_profile_cache", ["expires_at"])
    op.create_index("ix_member_cache_last_viewed", "member_profile_cache", ["last_viewed_at"])


def downgrade() -> None:
    op.drop_index("ix_member_cache_last_viewed", table_name="member_profile_cache")
    op.drop_index("ix_member_cache_expires", table_name="member_profile_cache")
    op.drop_index("ix_member_cache_org_email", table_name="member_profile_cache")
    op.drop_table("member_profile_cache")
