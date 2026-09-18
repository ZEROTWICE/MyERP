"""add nonconformity target columns

Revision ID: p1nonctarget
Revises: p0p2messtables
Create Date: 2026-09-18 12:00:00.000000

P1-3 变更：给 ``nonconformity_records`` 补 ``target_type`` / ``target_id`` 两列，
用来把「生产质检不合格（锚在工件）」与「来料检不合格（锚在到货单）」两类记录分开，
不再靠 workpiece_id 是否为空来猜。

纪律（沿用 P0-2 结论）：
  - 手写幂等迁移，upgrade() 内做存在性判断，不跑 ``flask db migrate``；
  - 两列可空，老数据保持 NULL（回退判定见 NonconformityRecord.target_label /
    mes_service.nonconformity_target）；
  - 同步登记在 app/__init__.py 的 ``_ENSURED_COLUMNS``，schema 由 create_all()
    建出的库在启动时也能自愈；
  - 接在已收敛的单 head ``p0p2messtables`` 之后，不制造第二个 head。

刻意不给两列建索引：自愈通道（_ENSURED_COLUMNS / _ensure_schema）只补列不补索引，
若一边建索引一边不建，两条升级路径的 schema 会漂移；本表体量小，全表扫描足够。
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'p1nonctarget'
down_revision = 'p0p2messtables'
branch_labels = None
depends_on = None


_TABLE = 'nonconformity_records'
_TARGET_COLUMNS = [
    ('target_type', sa.String(length=20)),
    ('target_id', sa.Integer()),
]


def _missing_columns(inspector):
    if _TABLE not in inspector.get_table_names():
        return []
    present = {c['name'] for c in inspector.get_columns(_TABLE)}
    return [(name, type_) for name, type_ in _TARGET_COLUMNS if name not in present]


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    missing = _missing_columns(inspector)
    if not missing:
        return
    with op.batch_alter_table(_TABLE, schema=None) as batch_op:
        for name, type_ in missing:
            batch_op.add_column(sa.Column(name, type_, nullable=True))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in inspector.get_table_names():
        return
    present = {c['name'] for c in inspector.get_columns(_TABLE)}
    existing = [name for name, _ in _TARGET_COLUMNS if name in present]
    if not existing:
        return
    with op.batch_alter_table(_TABLE, schema=None) as batch_op:
        for name in reversed(existing):
            batch_op.drop_column(name)
