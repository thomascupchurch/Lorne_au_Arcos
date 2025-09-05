"""make draft_part.part_type nullable

Revision ID: 0009_make_draft_part_type_nullable
Revises: 0008_drop_legacy_image_fk_columns
Create Date: 2025-09-05
"""
from alembic import op
import sqlalchemy as sa

revision = '0009_make_draft_part_type_nullable'
down_revision = '0008_drop_legacy_image_fk_columns'
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table('draft_part') as batch:
        batch.alter_column('part_type', existing_type=sa.String(length=20), nullable=True)

def downgrade():
    # Backfill NULLs with placeholder then set non-nullable
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE draft_part SET part_type='phase' WHERE part_type IS NULL"))
    with op.batch_alter_table('draft_part') as batch:
        batch.alter_column('part_type', existing_type=sa.String(length=20), nullable=False)
