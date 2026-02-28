"""add_member_login_fields

Revision ID: 02e9d06d99f5
Revises: 006
Create Date: 2026-02-28 09:57:54.879419

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '02e9d06d99f5'
down_revision: Union[str, None] = '006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('org_employees', sa.Column('password_hash', sa.String(length=255), nullable=True))
    op.add_column('org_employees', sa.Column('is_login_enabled', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('org_employees', sa.Column('sessions_invalidated_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('conversations', sa.Column('employee_id', sa.UUID(), nullable=True))
    op.alter_column('conversations', 'user_id', existing_type=sa.UUID(), nullable=True)


def downgrade() -> None:
    op.alter_column('conversations', 'user_id', existing_type=sa.UUID(), nullable=False)
    op.drop_column('conversations', 'employee_id')
    op.drop_column('org_employees', 'sessions_invalidated_at')
    op.drop_column('org_employees', 'is_login_enabled')
    op.drop_column('org_employees', 'password_hash')
