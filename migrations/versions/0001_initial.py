"""initial schema including notes columns

Revision ID: 0001_initial
Revises: 
Create Date: 2025-09-04
"""
from alembic import op
import sqlalchemy as sa

revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('user',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('username', sa.String(80), nullable=False, unique=True),
        sa.Column('password_hash', sa.String(128), nullable=False),
        sa.Column('is_admin', sa.Boolean, default=False)
    )
    op.create_table('project',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('title', sa.String(120), nullable=False),
        sa.Column('owner_id', sa.Integer, sa.ForeignKey('user.id'), nullable=False)
    )
    op.create_table('phase',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('title', sa.String(120), nullable=False),
        sa.Column('start_date', sa.Date, nullable=False),
        sa.Column('duration', sa.Integer, nullable=False),
        sa.Column('is_milestone', sa.Boolean, default=False),
        sa.Column('internal_external', sa.String(20), default='internal'),
        sa.Column('project_id', sa.Integer, sa.ForeignKey('project.id'), nullable=False),
        sa.Column('notes', sa.Text)
    )
    op.create_table('item',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('title', sa.String(120), nullable=False),
        sa.Column('start_date', sa.Date, nullable=False),
        sa.Column('duration', sa.Integer, nullable=False),
        sa.Column('dependencies', sa.String(256)),
        sa.Column('is_milestone', sa.Boolean, default=False),
        sa.Column('internal_external', sa.String(20), default='internal'),
        sa.Column('phase_id', sa.Integer, sa.ForeignKey('phase.id'), nullable=False),
        sa.Column('notes', sa.Text)
    )
    op.create_table('sub_item',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('title', sa.String(120), nullable=False),
        sa.Column('start_date', sa.Date, nullable=False),
        sa.Column('duration', sa.Integer, nullable=False),
        sa.Column('dependencies', sa.String(256)),
        sa.Column('is_milestone', sa.Boolean, default=False),
        sa.Column('internal_external', sa.String(20), default='internal'),
        sa.Column('item_id', sa.Integer, sa.ForeignKey('item.id'), nullable=False),
        sa.Column('notes', sa.Text)
    )
    op.create_table('image',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('filename', sa.String(256), nullable=False),
        sa.Column('phase_id', sa.Integer, sa.ForeignKey('phase.id')),
        sa.Column('item_id', sa.Integer, sa.ForeignKey('item.id')),
        sa.Column('subitem_id', sa.Integer, sa.ForeignKey('sub_item.id'))
    )

def downgrade():
    op.drop_table('image')
    op.drop_table('sub_item')
    op.drop_table('item')
    op.drop_table('phase')
    op.drop_table('project')
    op.drop_table('user')
