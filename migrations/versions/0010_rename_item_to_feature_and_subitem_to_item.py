"""rename item->feature and sub_item->item; update image link tables; add draft_part.feature_id

Revision ID: 0010_rename_item_to_feature_and_subitem_to_item
Revises: 0009_make_draft_part_type_nullable
Create Date: 2025-09-05
"""
from alembic import op
import sqlalchemy as sa

revision = '0010_rename_item_to_feature_and_subitem_to_item'
down_revision = '0009_make_draft_part_type_nullable'
branch_labels = None
depends_on = None


def _has_table(conn, name: str) -> bool:
    res = conn.execute(sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name=:n"), {'n': name}).fetchone()
    return res is not None


def upgrade():
    conn = op.get_bind()
    # 1) Rename item -> feature (mid-level). Be resilient if 'feature' already exists (e.g., from create_all).
    if _has_table(conn, 'item'):
        if _has_table(conn, 'feature'):
            # If 'feature' already exists but is empty, drop it so we can rename legacy 'item' -> 'feature'.
            try:
                count = conn.execute(sa.text('SELECT COUNT(*) FROM feature')).scalar() or 0
            except Exception:
                count = 0
            if count == 0:
                op.drop_table('feature')
                op.rename_table('item', 'feature')
            # else: both exist with data; skip rename to avoid conflict
        else:
            op.rename_table('item', 'feature')
    # phase_id FK remains the same, table is now feature

    # 2) Rename sub_item -> item (leaf). Avoid conflict if an empty 'item' table exists (from create_all).
    if _has_table(conn, 'sub_item'):
        if _has_table(conn, 'item'):
            # If current 'item' table exists but is empty, drop it before rename.
            try:
                leaf_count = conn.execute(sa.text('SELECT COUNT(*) FROM item')).scalar() or 0
            except Exception:
                leaf_count = 0
            if leaf_count == 0:
                op.drop_table('item')
        op.rename_table('sub_item', 'item')
    # Column item_id in new item table refers to feature(id) after step 1; need to rename FK column
    if _has_table(conn, 'item'):
        with op.batch_alter_table('item') as batch:
            insp = sa.inspect(conn)
            cols = [c['name'] for c in insp.get_columns('item')]
            if 'item_id' in cols:
                batch.alter_column('item_id', new_column_name='feature_id', existing_type=sa.Integer())

    # 3) Update image_* many-to-many tables
    # Drop legacy single-link columns if still present (safety on fresh DBs)
    if _has_table(conn, 'image'):
        insp = sa.inspect(conn)
        cols = [c['name'] for c in insp.get_columns('image')]
        to_drop = [c for c in ('phase_id','item_id','subitem_id') if c in cols]
        for col in to_drop:
            with op.batch_alter_table('image') as batch:
                batch.drop_column(col)

    # Ensure image_phase exists
    if not _has_table(conn, 'image_phase'):
        op.create_table('image_phase',
            sa.Column('image_id', sa.Integer, sa.ForeignKey('image.id'), primary_key=True),
            sa.Column('phase_id', sa.Integer, sa.ForeignKey('phase.id'), primary_key=True)
        )
    # Rename image_item -> image_feature
    if _has_table(conn, 'image_item'):
        op.rename_table('image_item', 'image_feature')
        # Rename column item_id -> feature_id if present
        with op.batch_alter_table('image_feature') as batch:
            insp = sa.inspect(conn)
            cols = [c['name'] for c in insp.get_columns('image_feature')]
            if 'item_id' in cols:
                batch.alter_column('item_id', new_column_name='feature_id', existing_type=sa.Integer())
    # Rename image_subitem -> image_item
    if _has_table(conn, 'image_subitem'):
        op.rename_table('image_subitem', 'image_item')
        with op.batch_alter_table('image_item') as batch:
            insp = sa.inspect(conn)
            cols = [c['name'] for c in insp.get_columns('image_item')]
            if 'subitem_id' in cols:
                batch.alter_column('subitem_id', new_column_name='item_id', existing_type=sa.Integer())

    # 4) Draft part: add feature_id column if missing (no FK constraint on SQLite to avoid ALTER issues)
    if _has_table(conn, 'draft_part'):
        insp = sa.inspect(conn)
        cols = [c['name'] for c in insp.get_columns('draft_part')]
        if 'feature_id' not in cols:
            with op.batch_alter_table('draft_part') as batch:
                batch.add_column(sa.Column('feature_id', sa.Integer(), nullable=True))


def downgrade():
    conn = op.get_bind()
    # Reverse draft_part feature_id
    insp = sa.inspect(conn)
    if _has_table(conn, 'draft_part'):
        cols = [c['name'] for c in insp.get_columns('draft_part')]
        if 'feature_id' in cols:
            with op.batch_alter_table('draft_part') as batch:
                batch.drop_column('feature_id')

    # Reverse image_* renames
    if _has_table(conn, 'image_item'):
        with op.batch_alter_table('image_item') as batch:
            cols = [c['name'] for c in insp.get_columns('image_item')]
            if 'item_id' in cols:
                batch.alter_column('item_id', new_column_name='subitem_id', existing_type=sa.Integer())
        op.rename_table('image_item', 'image_subitem')
    if _has_table(conn, 'image_feature'):
        with op.batch_alter_table('image_feature') as batch:
            cols = [c['name'] for c in insp.get_columns('image_feature')]
            if 'feature_id' in cols:
                batch.alter_column('feature_id', new_column_name='item_id', existing_type=sa.Integer())
        op.rename_table('image_feature', 'image_item')

    # Recreate legacy single-link columns on image (nullable)
    if _has_table(conn, 'image'):
        with op.batch_alter_table('image') as batch:
            batch.add_column(sa.Column('phase_id', sa.Integer(), nullable=True))
            batch.add_column(sa.Column('item_id', sa.Integer(), nullable=True))
            batch.add_column(sa.Column('subitem_id', sa.Integer(), nullable=True))

    # Reverse sub_item/item rename
    if _has_table(conn, 'item'):
        with op.batch_alter_table('item') as batch:
            cols = [c['name'] for c in insp.get_columns('item')]
            if 'feature_id' in cols:
                batch.alter_column('feature_id', new_column_name='item_id', existing_type=sa.Integer())
        op.rename_table('item', 'sub_item')

    # Reverse item/feature rename
    if _has_table(conn, 'feature'):
        op.rename_table('feature', 'item')
