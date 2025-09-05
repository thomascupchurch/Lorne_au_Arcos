"""add optional scheduling fields to draft_part

Revision ID: 0011_add_draft_scheduling
Revises: 0010_rename_item_to_feature_and_subitem_to_item
Create Date: 2025-09-05
"""
from alembic import op
import sqlalchemy as sa

revision = '0011_add_draft_scheduling'
down_revision = '0010_rename_item_to_feature_and_subitem_to_item'
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table('draft_part') as batch:
        batch.add_column(sa.Column('start_date', sa.Date(), nullable=True))
        batch.add_column(sa.Column('duration', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('is_milestone', sa.Boolean(), nullable=True))


def downgrade():
    with op.batch_alter_table('draft_part') as batch:
        batch.drop_column('is_milestone')
        batch.drop_column('duration')
        batch.drop_column('start_date')
