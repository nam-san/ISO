"""add document numbering/revision fields

Revision ID: 0efdc89c0fdd
Revises: 47600f699ad5
Create Date: 2026-08-07 15:22:48.059269

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0efdc89c0fdd'
down_revision = '47600f699ad5'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.add_column(sa.Column('enactment_date', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('revision_no', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('guide_code', sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column('is_dept_doc', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('dept_code', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('part_code', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('related_procedure_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('supersedes_id', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('documents', schema=None) as batch_op:
        for c in ['supersedes_id', 'related_procedure_id', 'part_code', 'dept_code',
                  'is_dept_doc', 'guide_code', 'revision_no', 'enactment_date']:
            batch_op.drop_column(c)
