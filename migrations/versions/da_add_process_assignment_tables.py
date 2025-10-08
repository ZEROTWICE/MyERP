"""add process assignment tables

Revision ID: da_add_process_assignment
Revises: f63ce20582f8
Create Date: 2025-10-08 12:24:30
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'da_add_process_assignment'
down_revision = 'f63ce20582f8'
branch_labels = None
depends_on = None


def upgrade():
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
    op.drop_constraint('uq_process_assign_member_unique', 'process_assignment_members', type_='unique')
    op.drop_table('process_assignment_members')
    op.drop_constraint('uq_process_assign_rule_process', 'process_assignment_rules', type_='unique')
    op.drop_table('process_assignment_rules')


