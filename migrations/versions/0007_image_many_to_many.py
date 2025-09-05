"""introduce image many-to-many association tables

Revision ID: 0007_image_many_to_many
Revises: 0006_add_project_id_to_image
Create Date: 2025-09-05
"""
from alembic import op
import sqlalchemy as sa

revision = '0007_image_many_to_many'
down_revision = '0006_add_project_id_to_image'
branch_labels = None
depends_on = None

def upgrade():
    # Create association tables if they don't exist
    for name, left, right in [
        ('image_phase','image','phase'),
        ('image_item','image','item'),
        ('image_subitem','image','sub_item')
    ]:
        op.create_table(
            name,
            sa.Column('image_id', sa.Integer(), sa.ForeignKey(f'{left}.id', ondelete='CASCADE'), primary_key=True),
            sa.Column(f'{right}_id', sa.Integer(), sa.ForeignKey(f'{right}.id', ondelete='CASCADE'), primary_key=True)
        )
    # (Optional) Data migration from old single FK columns into new link tables
    conn = op.get_bind()
    try:
        # Phase links
        res = conn.execute(sa.text('SELECT id, phase_id FROM image WHERE phase_id IS NOT NULL'))
        rows = res.fetchall()
        for r in rows:
            conn.execute(sa.text('INSERT INTO image_phase (image_id, phase_id) VALUES (:iid, :pid)'), {'iid': r.id, 'pid': r.phase_id})
        # Item links
        res = conn.execute(sa.text('SELECT id, item_id FROM image WHERE item_id IS NOT NULL'))
        rows = res.fetchall()
        for r in rows:
            conn.execute(sa.text('INSERT INTO image_item (image_id, item_id) VALUES (:iid, :iid2)'), {'iid': r.id, 'iid2': r.item_id})
        # SubItem links
        res = conn.execute(sa.text('SELECT id, subitem_id FROM image WHERE subitem_id IS NOT NULL'))
        rows = res.fetchall()
        for r in rows:
            conn.execute(sa.text('INSERT INTO image_subitem (image_id, subitem_id) VALUES (:iid, :sid)'), {'iid': r.id, 'sid': r.subitem_id})
    except Exception:
        pass
    # NOTE: We intentionally keep legacy columns for backward compatibility; can drop in later migration.

def downgrade():
    for tbl in ('image_subitem','image_item','image_phase'):
        try:
            op.drop_table(tbl)
        except Exception:
            pass
