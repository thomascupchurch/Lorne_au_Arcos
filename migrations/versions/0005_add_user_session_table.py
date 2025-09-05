"""add user_session table

Revision ID: 0005_add_user_session_table
Revises: 0004_add_user_last_seen
Create Date: 2025-09-05
"""
from alembic import op
import sqlalchemy as sa

revision = '0005_add_user_session_table'
down_revision = '0004_add_user_last_seen'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('user_session',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id'), nullable=False),
        sa.Column('session_uuid', sa.String(length=64), nullable=False, unique=True),
        sa.Column('last_seen', sa.DateTime(), nullable=True, index=True)
    )
    op.create_index('ix_user_session_last_seen', 'user_session', ['last_seen'])


def downgrade():
    op.drop_index('ix_user_session_last_seen', table_name='user_session')
    op.drop_table('user_session')
