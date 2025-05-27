"""update_quality_template_type_from_process_to_production_record

Revision ID: 8c3931690539
Revises: 4e52ed7126be
Create Date: 2025-05-28 03:30:37.477874

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8c3931690539'
down_revision = '4e52ed7126be'
branch_labels = None
depends_on = None


def upgrade():
    # 更新质检模板中的类型从 'process' 改为 'production_record'
    op.execute(
        "UPDATE inspection_templates SET type = 'production_record' WHERE type = 'process'"
    )
    
    # 更新质检任务中的目标类型从 'process' 改为 'production_record'
    op.execute(
        "UPDATE inspection_tasks SET target_type = 'production_record' WHERE target_type = 'process'"
    )


def downgrade():
    # 回滚：将 'production_record' 改回 'process'
    op.execute(
        "UPDATE inspection_templates SET type = 'process' WHERE type = 'production_record'"
    )
    
    op.execute(
        "UPDATE inspection_tasks SET target_type = 'process' WHERE target_type = 'production_record'"
    )
