"""add system_configs table and task_assignment.completed_at

Revision ID: b1a01systemcfg
Revises: 0e97d0ec34b4
Create Date: 2026-08-11

手写迁移：仅包含本批次的两项变更。
仓库中 material_requisitions、inventory_counts、consumables 等表已由
db.create_all() 建出但缺少迁移记录，因此不使用 autogenerate，避免生成
与线上库冲突的巨大脚本。
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b1a01systemcfg'
down_revision = '0e97d0ec34b4'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if 'system_configs' not in inspector.get_table_names():
        op.create_table(
            'system_configs',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('key', sa.String(length=100), nullable=False),
            sa.Column('value', sa.Text(), nullable=True),
            sa.Column('value_type', sa.String(length=20), nullable=False, server_default='string'),
            sa.Column('category', sa.String(length=50), nullable=True),
            sa.Column('label', sa.String(length=200), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('updated_by', sa.Integer(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['updated_by'], ['user.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('key', name='uq_system_config_key'),
        )
        with op.batch_alter_table('system_configs', schema=None) as batch_op:
            batch_op.create_index('ix_system_configs_key', ['key'], unique=True)
            batch_op.create_index('ix_system_configs_category', ['category'], unique=False)

    task_columns = {c['name'] for c in inspector.get_columns('task_assignment')}
    if 'completed_at' not in task_columns:
        with op.batch_alter_table('task_assignment', schema=None) as batch_op:
            batch_op.add_column(sa.Column('completed_at', sa.DateTime(), nullable=True))
            batch_op.create_index('ix_task_assignment_completed_at', ['completed_at'], unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    task_columns = {c['name'] for c in inspector.get_columns('task_assignment')}
    if 'completed_at' in task_columns:
        with op.batch_alter_table('task_assignment', schema=None) as batch_op:
            batch_op.drop_index('ix_task_assignment_completed_at')
            batch_op.drop_column('completed_at')

    if 'system_configs' in inspector.get_table_names():
        op.drop_table('system_configs')
