"""add ghs label fields to msds

Revision ID: 2e525c1b5c3d
Revises: 15a4cd0132bb
Create Date: 2026-08-10 11:58:12.573212

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2e525c1b5c3d'
down_revision = '15a4cd0132bb'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('msds', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ghs_pictograms', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('signal_word', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('hazard_statements', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('precaution_statements', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('supplier_info', sa.String(length=300), nullable=True))


def downgrade():
    with op.batch_alter_table('msds', schema=None) as batch_op:
        for c in ['supplier_info','precaution_statements','hazard_statements','signal_word','ghs_pictograms']:
            batch_op.drop_column(c)
