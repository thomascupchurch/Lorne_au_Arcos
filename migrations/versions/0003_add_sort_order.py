"""add sort_order columns

Revision ID: 0003_add_sort_order
Revises: 0002_add_draft_part
Create Date: 2025-09-05
"""
from alembic import op
import sqlalchemy as sa

revision = '0003_add_sort_order'
down_revision = '0002_add_draft_part'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('phase', sa.Column('sort_order', sa.Integer(), server_default='0', nullable=False))
    op.add_column('item', sa.Column('sort_order', sa.Integer(), server_default='0', nullable=False))
    op.add_column('sub_item', sa.Column('sort_order', sa.Integer(), server_default='0', nullable=False))


def downgrade():
    op.drop_column('phase', 'sort_order')
    op.drop_column('item', 'sort_order')
    op.drop_column('sub_item', 'sort_order')
