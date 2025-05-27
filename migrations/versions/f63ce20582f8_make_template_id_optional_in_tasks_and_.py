"""make_template_id_optional_in_tasks_and_add_to_records

Revision ID: f63ce20582f8
Revises: 8c3931690539
Create Date: 2025-05-28 03:34:05.244330

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f63ce20582f8'
down_revision = '8c3931690539'
branch_labels = None
depends_on = None


def upgrade():
    # 修改质检任务表，使template_id可为空
    with op.batch_alter_table('inspection_tasks', schema=None) as batch_op:
        batch_op.alter_column('template_id',
                              existing_type=sa.Integer(),
                              nullable=True)
    
    # 在质检记录表中添加template_id字段
    with op.batch_alter_table('inspection_records', schema=None) as batch_op:
        batch_op.add_column(sa.Column('template_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_inspection_records_template_id', 'inspection_templates', ['template_id'], ['id'])


def downgrade():
    # 回滚：删除质检记录表中的template_id字段
    with op.batch_alter_table('inspection_records', schema=None) as batch_op:
        batch_op.drop_constraint('fk_inspection_records_template_id', type_='foreignkey')
        batch_op.drop_column('template_id')
    
    # 回滚：将质检任务表的template_id改回必需
    with op.batch_alter_table('inspection_tasks', schema=None) as batch_op:
        batch_op.alter_column('template_id',
                              existing_type=sa.Integer(),
                              nullable=False)
