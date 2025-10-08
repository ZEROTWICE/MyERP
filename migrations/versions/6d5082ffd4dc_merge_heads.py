"""merge heads

Revision ID: 6d5082ffd4dc
Revises: 33c7d77643c1, 9f02bbbbd492, c117632ece3d, da_add_process_assignment
Create Date: 2025-10-08 12:34:26.715022

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6d5082ffd4dc'
down_revision = ('33c7d77643c1', '9f02bbbbd492', 'c117632ece3d', 'da_add_process_assignment')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
