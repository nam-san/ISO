"""add after_control to risk_improvements

Revision ID: 6275367b41be
Revises: 74c1c3eeeae3
Create Date: 2026-07-10 14:52:20.047144

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6275367b41be'
down_revision = '74c1c3eeeae3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('risk_improvements', schema=None) as batch_op:
        batch_op.add_column(sa.Column('after_control', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('risk_improvements', schema=None) as batch_op:
        batch_op.drop_column('after_control')
