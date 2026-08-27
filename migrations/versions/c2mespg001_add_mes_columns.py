"""add turnout mes columns and leave new tables to create_all

Revision ID: c2mespg001
Revises: b1a01systemcfg
Create Date: 2026-08-26

手写、幂等：只补已有表上的新列。设备/工件/炉次/采购/发货等新表由
app/__init__.py 的 db.create_all() 在启动时创建，避免 autogenerate 把
历史上 create_all 出来的库存表再次纳入迁移链。
"""
from alembic import op
import sqlalchemy as sa


revision = 'c2mespg001'
down_revision = 'b1a01systemcfg'
branch_labels = None
depends_on = None


def _add_columns(table, columns):
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return
    present = {c['name'] for c in inspector.get_columns(table)}
    with op.batch_alter_table(table, schema=None) as batch_op:
        for name, col in columns:
            if name not in present:
                batch_op.add_column(col)


def upgrade():
    _add_columns('task_assignment', [
        ('equipment_id', sa.Column('equipment_id', sa.Integer(), nullable=True)),
        ('work_center_id', sa.Column('work_center_id', sa.Integer(), nullable=True)),
    ])
    _add_columns('products', [
        ('sellable_as_part', sa.Column('sellable_as_part', sa.Boolean(), nullable=True)),
    ])
    _add_columns('product_processes', [
        ('process_stage', sa.Column('process_stage', sa.String(length=20), nullable=True)),
        ('work_center_id', sa.Column('work_center_id', sa.Integer(), nullable=True)),
    ])
    _add_columns('finished_product', [
        ('stock_kind', sa.Column('stock_kind', sa.String(length=20), nullable=True)),
        ('workpiece_id', sa.Column('workpiece_id', sa.Integer(), nullable=True)),
        ('product_id', sa.Column('product_id', sa.Integer(), nullable=True)),
    ])
    _add_columns('nonconformity_records', [
        ('status', sa.Column('status', sa.String(length=20), nullable=True)),
        ('approver_id', sa.Column('approver_id', sa.Integer(), nullable=True)),
        ('approved_at', sa.Column('approved_at', sa.DateTime(), nullable=True)),
        ('rework_task_id', sa.Column('rework_task_id', sa.Integer(), nullable=True)),
        ('scrap_cost', sa.Column('scrap_cost', sa.Float(), nullable=True)),
        ('workpiece_id', sa.Column('workpiece_id', sa.Integer(), nullable=True)),
    ])
    _add_columns('raw_material_categories', [
        ('requires_approval', sa.Column('requires_approval', sa.Boolean(), nullable=True)),
    ])
    _add_columns('consumable_categories', [
        ('requires_approval', sa.Column('requires_approval', sa.Boolean(), nullable=True)),
    ])


def downgrade():
    pass
