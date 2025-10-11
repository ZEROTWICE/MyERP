"""add new spec fields to production models

Revision ID: eb1234567890
Revises: c81522b131f7
Create Date: 2025-10-11 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'eb1234567890'
down_revision = 'c81522b131f7'
branch_labels = None
depends_on = None


def upgrade():
    # 为 production_orders 表添加新规格字段
    with op.batch_alter_table('production_orders', schema=None) as batch_op:
        batch_op.add_column(sa.Column('spec_splice_hole', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('spec_gasket_hole', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('anti_corrosion', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('rubber_gasket_material', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('turnout_rail', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('using_unit', sa.String(length=100), nullable=True))
    
    # 为 production_batches 表添加新规格字段
    with op.batch_alter_table('production_batches', schema=None) as batch_op:
        batch_op.add_column(sa.Column('spec_splice_hole', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('spec_gasket_hole', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('anti_corrosion', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('rubber_gasket_material', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('turnout_rail', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('using_unit', sa.String(length=100), nullable=True))
    
    # 为 task_assignment 表添加新规格字段
    with op.batch_alter_table('task_assignment', schema=None) as batch_op:
        batch_op.add_column(sa.Column('spec_splice_hole', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('spec_gasket_hole', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('anti_corrosion', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('rubber_gasket_material', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('turnout_rail', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('using_unit', sa.String(length=100), nullable=True))


def downgrade():
    # 移除 task_assignment 表的新规格字段
    with op.batch_alter_table('task_assignment', schema=None) as batch_op:
        batch_op.drop_column('using_unit')
        batch_op.drop_column('turnout_rail')
        batch_op.drop_column('rubber_gasket_material')
        batch_op.drop_column('anti_corrosion')
        batch_op.drop_column('spec_gasket_hole')
        batch_op.drop_column('spec_splice_hole')
    
    # 移除 production_batches 表的新规格字段
    with op.batch_alter_table('production_batches', schema=None) as batch_op:
        batch_op.drop_column('using_unit')
        batch_op.drop_column('turnout_rail')
        batch_op.drop_column('rubber_gasket_material')
        batch_op.drop_column('anti_corrosion')
        batch_op.drop_column('spec_gasket_hole')
        batch_op.drop_column('spec_splice_hole')
    
    # 移除 production_orders 表的新规格字段
    with op.batch_alter_table('production_orders', schema=None) as batch_op:
        batch_op.drop_column('using_unit')
        batch_op.drop_column('turnout_rail')
        batch_op.drop_column('rubber_gasket_material')
        batch_op.drop_column('anti_corrosion')
        batch_op.drop_column('spec_gasket_hole')
        batch_op.drop_column('spec_splice_hole')

