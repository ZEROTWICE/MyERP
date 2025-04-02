"""add process price subtotal and group

Revision ID: f37eb3b3e47f
Revises: 949c48dc144c
Create Date: 2024-03-20 11:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f37eb3b3e47f'
down_revision = '949c48dc144c'
branch_labels = None
depends_on = None


def upgrade():
    # 使用批量操作添加列
    with op.batch_alter_table('process_price', schema=None) as batch_op:
        # 先添加可空列
        batch_op.add_column(sa.Column('price_type', sa.String(length=20), nullable=True))

    # 更新现有记录的price_type为'normal'
    op.execute("UPDATE process_price SET price_type = 'normal'")

    # 将price_type设为非空
    with op.batch_alter_table('process_price', schema=None) as batch_op:
        batch_op.alter_column('price_type',
                            existing_type=sa.String(length=20),
                            nullable=False)

    # 创建工序价格小计关系表
    op.create_table('process_price_group',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('serial_number', sa.String(length=8), nullable=False),
        sa.Column('subtotal_id', sa.Integer(), nullable=False),
        sa.Column('process_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['process_id'], ['process_price.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['subtotal_id'], ['process_price.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('serial_number', name='uq_process_price_group_serial_number'),
        sa.UniqueConstraint('subtotal_id', 'process_id', name='uq_subtotal_process')
    )


def downgrade():
    # 删除工序价格小计关系表
    op.drop_table('process_price_group')

    # 删除price_type列
    with op.batch_alter_table('process_price', schema=None) as batch_op:
        batch_op.drop_column('price_type')
