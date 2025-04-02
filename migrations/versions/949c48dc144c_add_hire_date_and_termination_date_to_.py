"""add hire_date and termination_date to employee

Revision ID: 949c48dc144c
Revises: d63a1e23c848
Create Date: 2024-03-20 10:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime

# revision identifiers, used by Alembic.
revision = '949c48dc144c'
down_revision = 'd63a1e23c848'
branch_labels = None
depends_on = None

def upgrade():
    # 使用批量操作添加列
    with op.batch_alter_table('employee', schema=None) as batch_op:
        # 先添加可空列
        batch_op.add_column(sa.Column('hire_date', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('termination_date', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('is_active', sa.Boolean(), nullable=True))

    # 更新现有记录的hire_date为当前日期，is_active为True
    op.execute("UPDATE employee SET hire_date = '{}', is_active = 1".format(datetime.now().date()))

    # 将hire_date和is_active设为非空
    with op.batch_alter_table('employee', schema=None) as batch_op:
        batch_op.alter_column('hire_date',
                            existing_type=sa.Date(),
                            nullable=False)
        batch_op.alter_column('is_active',
                            existing_type=sa.Boolean(),
                            nullable=False)

def downgrade():
    with op.batch_alter_table('employee', schema=None) as batch_op:
        batch_op.drop_column('is_active')
        batch_op.drop_column('termination_date')
        batch_op.drop_column('hire_date')
