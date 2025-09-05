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
    """Drop legacy single-link columns (phase_id, item_id, subitem_id) if present.

    The earlier migration created many-to-many link tables but left these
    foreign key columns (with auto-generated FK constraint names on SQLite).
    Prior version tried to drop constraints by hard-coded names causing
    failures. We instead:
      1. Reflect existing columns.
      2. If any legacy columns remain, recreate the table dropping them.
    This is safe & idempotent; reruns become no-ops once columns are gone.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    try:
        existing_cols = {c['name'] for c in inspector.get_columns('image')}
    except Exception:
        # Table missing? Nothing to do.
        return
    to_drop = [c for c in ('phase_id','item_id','subitem_id') if c in existing_cols]
    if not to_drop:
        return
    # Force recreate to ensure any lingering FK constraints are removed cleanly (SQLite friendly)
    with op.batch_alter_table('image', recreate='always') as batch_op:
        for col in to_drop:
            batch_op.drop_column(col)


def downgrade():
    # Recreate columns (nullable) without foreign keys for simplicity
    with op.batch_alter_table('image') as batch_op:
        for col, target in (('phase_id','phase'),('item_id','item'),('subitem_id','sub_item')):
            try:
                batch_op.add_column(sa.Column(col, sa.Integer(), nullable=True))
                batch_op.create_foreign_key(f'fk_image_{target}', target, ['phase_id' if col=='phase_id' else col], ['id'])
            except Exception:
                pass
