"""add process assignment tables

Revision ID: da_add_process_assignment
Revises: f63ce20582f8
Create Date: 2025-10-08 12:24:30

加固说明（2026-09-18）：本项目的 31 张表由 db.create_all() 建出、不在迁移历史里，
因此在「表已由 create_all 建出、alembic_version 停在旧修订」的库上重放迁移链时，
原来的无条件 create_table 会撞 "table process_assignment_rules already exists"。
现在改为先做存在性判断（sa.inspect().has_table），表已存在就跳过建表与建约束。

注意：这**不等于**整条迁移链可重放。实测继续推进会撞上第二类阻塞 —— alembic 的
batch_alter_table 重建表时不接受 create_all 建出的内联匿名 UNIQUE 约束
（ValueError: Constraint must have a name，alembic/operations/batch.py:670）。
本项目对老库/新库统一走「启动自愈 + flask db stamp p1nonctarget」，
详见 docs/交付说明-P0P1.md §6.2 第 9 项。
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'da_add_process_assignment'
down_revision = 'f63ce20582f8'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())

    if not inspector.has_table('process_assignment_rules'):
        op.create_table(
            'process_assignment_rules',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('global_sn', sa.String(length=8), nullable=False, unique=True),
            sa.Column('process_id', sa.Integer(), sa.ForeignKey('process_price.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('strategy', sa.String(length=20), nullable=False, server_default='round_robin'),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
            sa.Column('notes', sa.Text()),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)')),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)')),
        )
        op.create_unique_constraint('uq_process_assign_rule_process', 'process_assignment_rules', ['process_id'])
    # 表已存在时不重复建表；唯一约束由模型 __table_args__ 在 create_all 时已建立

    if not inspector.has_table('process_assignment_members'):
        op.create_table(
            'process_assignment_members',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('global_sn', sa.String(length=8), nullable=False, unique=True),
            sa.Column('rule_id', sa.Integer(), sa.ForeignKey('process_assignment_rules.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('employee_id', sa.Integer(), sa.ForeignKey('employee.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('weight', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('sequence', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)')),
        )
        op.create_unique_constraint('uq_process_assign_member_unique', 'process_assignment_members', ['rule_id', 'employee_id'])


def downgrade():
    inspector = sa.inspect(op.get_bind())

    if inspector.has_table('process_assignment_members'):
        op.drop_constraint('uq_process_assign_member_unique', 'process_assignment_members', type_='unique')
        op.drop_table('process_assignment_members')

    if inspector.has_table('process_assignment_rules'):
        op.drop_constraint('uq_process_assign_rule_process', 'process_assignment_rules', type_='unique')
        op.drop_table('process_assignment_rules')
