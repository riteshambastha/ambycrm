"""Add account_contacts and linkedin_posts tables for LinkedIn enrichment.

Revision ID: 006
Revises: 005
Create Date: 2026-02-26
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "account_contacts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("salesforce_contact_id", sa.String(50), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(100), nullable=True),
        sa.Column("account_id", sa.String(50), nullable=True),
        sa.Column("account_name", sa.String(255), nullable=True),
        sa.Column("account_industry", sa.String(255), nullable=True),
        sa.Column("linkedin_url", sa.String(500), nullable=True),
        sa.Column("linkedin_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "salesforce_synced_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("org_id", "salesforce_contact_id", name="uq_org_sf_contact"),
    )
    op.create_index("ix_account_contacts_org", "account_contacts", ["org_id"])
    op.create_index("ix_account_contacts_email", "account_contacts", ["org_id", "email"])

    op.create_table(
        "linkedin_posts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "contact_id",
            UUID(as_uuid=True),
            sa.ForeignKey("account_contacts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("post_url", sa.String(500), nullable=True),
        sa.Column("post_text", sa.Text, nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_linkedin_posts_contact", "linkedin_posts", ["contact_id"])


def downgrade() -> None:
    op.drop_index("ix_linkedin_posts_contact", table_name="linkedin_posts")
    op.drop_table("linkedin_posts")
    op.drop_index("ix_account_contacts_email", table_name="account_contacts")
    op.drop_index("ix_account_contacts_org", table_name="account_contacts")
    op.drop_table("account_contacts")
