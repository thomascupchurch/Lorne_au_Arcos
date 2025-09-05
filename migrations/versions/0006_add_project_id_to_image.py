"""add project_id to image

Revision ID: 0006_add_project_id_to_image
Revises: 0005_add_user_session_table
Create Date: 2025-09-05
"""
from alembic import op
import sqlalchemy as sa

revision = '0006_add_project_id_to_image'
down_revision = '0005_add_user_session_table'
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table('image') as batch_op:
        batch_op.add_column(sa.Column('project_id', sa.Integer(), nullable=True))
        try:
            batch_op.create_foreign_key('fk_image_project','project',['project_id'],['id'])
        except Exception:
            pass


def downgrade():
    with op.batch_alter_table('image') as batch_op:
        try:
            batch_op.drop_constraint('fk_image_project', type_='foreignkey')
        except Exception:
            pass
        batch_op.drop_column('project_id')
