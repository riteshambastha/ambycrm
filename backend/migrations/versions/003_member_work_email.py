"""Add work_email to organization_members.

Revision ID: 003
Revises: 002
Create Date: 2026-02-24
"""

from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organization_members",
        sa.Column("work_email", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("organization_members", "work_email")
