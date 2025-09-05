"""add last_seen to user

Revision ID: 0004_add_user_last_seen
Revises: 0003_add_sort_order
Create Date: 2025-09-05
"""
from alembic import op
import sqlalchemy as sa

revision = '0004_add_user_last_seen'
down_revision = '0003_add_sort_order'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('user', sa.Column('last_seen', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('user', 'last_seen')
