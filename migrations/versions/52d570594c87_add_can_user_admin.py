"""add can_user_admin

Revision ID: 52d570594c87
Revises: 39754d12eb62
Create Date: 2026-08-21 15:37:20.357901

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '52d570594c87'
down_revision = '39754d12eb62'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('can_user_admin', sa.Boolean(), nullable=True))


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('can_user_admin')
