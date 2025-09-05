"""drop legacy single-link columns from image

Revision ID: 0008_drop_legacy_image_fk_columns
Revises: 0007_image_many_to_many
Create Date: 2025-09-05
"""
from alembic import op
import sqlalchemy as sa

revision = '0008_drop_legacy_image_fk_columns'
down_revision = '0007_image_many_to_many'
branch_labels = None
depends_on = None

def upgrade():
    # Safely drop old single-association columns if they still exist
    with op.batch_alter_table('image') as batch_op:
        for col in ('phase_id','item_id','subitem_id'):
            try:
                batch_op.drop_constraint(f'fk_image_{col[:-3]}', type_='foreignkey')
            except Exception:
                pass
        for col in ('phase_id','item_id','subitem_id'):
            try:
                batch_op.drop_column(col)
            except Exception:
                pass


def downgrade():
    # Recreate columns (nullable) without foreign keys for simplicity
    with op.batch_alter_table('image') as batch_op:
        for col, target in (('phase_id','phase'),('item_id','item'),('subitem_id','sub_item')):
            try:
                batch_op.add_column(sa.Column(col, sa.Integer(), nullable=True))
                batch_op.create_foreign_key(f'fk_image_{target}', target, ['phase_id' if col=='phase_id' else col], ['id'])
            except Exception:
                pass
