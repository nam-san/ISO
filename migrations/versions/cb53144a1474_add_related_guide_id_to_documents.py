"""add related_guide_id to documents

Revision ID: cb53144a1474
Revises: 0efdc89c0fdd
Create Date: 2026-08-10 10:34:28.863748

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'cb53144a1474'
down_revision = '0efdc89c0fdd'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.add_column(sa.Column('related_guide_id', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.drop_column('related_guide_id')
