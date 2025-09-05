"""add draft_part table

Revision ID: 0002_add_draft_part
Revises: 0001_initial
Create Date: 2025-09-05
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0002_add_draft_part'
down_revision = '0001_initial'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        'draft_part',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('part_type', sa.String(length=50), nullable=False),
        sa.Column('internal_external', sa.String(length=20), nullable=True),
        sa.Column('dependencies', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('project_id', sa.Integer(), sa.ForeignKey('project.id'), nullable=True),
        sa.Column('phase_id', sa.Integer(), sa.ForeignKey('phase.id'), nullable=True),
        sa.Column('item_id', sa.Integer(), sa.ForeignKey('item.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False)
    )


def downgrade():
    op.drop_table('draft_part')
