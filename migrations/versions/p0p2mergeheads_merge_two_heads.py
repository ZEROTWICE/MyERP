"""merge the two remaining heads (c2mespg001 + f179636cecf0)

Revision ID: p0p2mergeheads
Revises: c2mespg001, f179636cecf0
Create Date: 2026-08-28

收敛前迁移图有两条互不相交的尾链，``flask db heads`` 输出两个 head：

    0e97d0ec34b4 ── b1a01systemcfg ── c2mespg001        （MES 设备/工件列）
                 └─ eb1234567890 ── f179636cecf0        （规格列 + 合并）

app.db 实测停在 f179636cecf0，所以本合并迁移会让 alembic 先把
b1a01systemcfg / c2mespg001 这两处「加表加列」补跑一遍（两者都带存在性
判断，对 create_all 建出的库是空操作），再前进到 31 张 create_all 表的
收敛迁移 p0p2messtables。合并之后 ``flask db heads`` 只剩一个 head。

合并迁移本身没有 schema 变更；downgrade() 留空是 alembic 合并修订的常规
做法（无法判断要退回哪一支，且两支都是幂等补列）。
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'p0p2mergeheads'
down_revision = ('c2mespg001', 'f179636cecf0')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
