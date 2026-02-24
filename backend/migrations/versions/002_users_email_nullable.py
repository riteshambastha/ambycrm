"""make users.email nullable

Revision ID: 002
Revises: 001
Create Date: 2026-02-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Clerk JWTs don't include email by default, so the column must be nullable.
    # Clear any empty-string placeholders first (safe in dev).
    op.execute("UPDATE users SET email = NULL WHERE email = ''")
    op.alter_column("users", "email", existing_type=sa.String(255), nullable=True)


def downgrade() -> None:
    op.execute("UPDATE users SET email = '' WHERE email IS NULL")
    op.alter_column("users", "email", existing_type=sa.String(255), nullable=False)
