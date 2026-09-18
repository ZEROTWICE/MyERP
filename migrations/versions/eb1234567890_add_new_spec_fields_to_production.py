"""add new spec fields to production models

Revision ID: eb1234567890
Revises: c81522b131f7
Create Date: 2025-10-11 14:00:00.000000

P0-2 变更：给三张表补规格列时加上存在性判断（原先是无条件 add_column）。
这份修订在 app.db 上已应用，所以这段改动对它是空操作；它保护的是那些
schema 由 db.create_all() 建出、alembic 版本还停在 c81522b131f7 及更早的老库
——那些库里六列本来就在，无条件 add_column 会直接抛 duplicate column 让
``flask db upgrade`` 中断（部署脚本又把错误吞成警告）。行为与 c2mespg001 一致。
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'eb1234567890'
down_revision = 'c81522b131f7'
branch_labels = None
depends_on = None


_SPEC_COLUMNS = [
    ('spec_splice_hole', sa.String(length=100)),
    ('spec_gasket_hole', sa.String(length=100)),
    ('anti_corrosion', sa.String(length=100)),
    ('rubber_gasket_material', sa.String(length=100)),
    ('turnout_rail', sa.String(length=100)),
    ('using_unit', sa.String(length=100)),
]


def _add_spec_columns(table):
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return
    present = {c['name'] for c in inspector.get_columns(table)}
    missing = [(name, type_) for name, type_ in _SPEC_COLUMNS if name not in present]
    if not missing:
        return
    with op.batch_alter_table(table, schema=None) as batch_op:
        for name, type_ in missing:
            batch_op.add_column(sa.Column(name, type_, nullable=True))


def _drop_spec_columns(table):
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return
    present = {c['name'] for c in inspector.get_columns(table)}
    existing = [name for name, _ in _SPEC_COLUMNS if name in present]
    if not existing:
        return
    with op.batch_alter_table(table, schema=None) as batch_op:
        for name in reversed(existing):
            batch_op.drop_column(name)


def upgrade():
    for table in ('production_orders', 'production_batches', 'task_assignment'):
        _add_spec_columns(table)


def downgrade():
    for table in ('task_assignment', 'production_batches', 'production_orders'):
        _drop_spec_columns(table)
