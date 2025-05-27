"""add_status_field_to_raw_material

Revision ID: 4e52ed7126be
Revises: 22b8de65652a
Create Date: 2025-05-27 17:03:03.364507

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4e52ed7126be'
down_revision = '22b8de65652a'
branch_labels = None
depends_on = None


def upgrade():
    # 为原材料表添加状态字段
    op.add_column('raw_material', sa.Column('status', sa.String(20), nullable=False, server_default='in_stock'))
    
    # 创建索引
    op.create_index('ix_raw_material_status', 'raw_material', ['status'])


def downgrade():
    # 删除索引
    op.drop_index('ix_raw_material_status', 'raw_material')
    
    # 删除状态字段
    op.drop_column('raw_material', 'status')
