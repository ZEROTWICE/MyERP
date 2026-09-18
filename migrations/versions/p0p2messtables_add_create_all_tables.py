"""create the 31 tables that until now only existed via db.create_all()

Revision ID: p0p2messtables
Revises: p0p2mergeheads
Create Date: 2026-08-28

背景（docs/继续开发准备报告.md 第二节 E 组）
------------------------------------------
仓库里 31 张表（仓库 8 / 设备-工件-炉次 12 / 采购 8 / 发货 3）历史上一律由
app/__init__.py 的 db.create_all() 建出，从没进过迁移链。它们的表结构在这里
按 app/models.py 的当前定义冻结成一份显式清单，并由 upgrade() 用存在性判断
落库：

* 表不存在 -> op.create_table(...) 建整表（含索引）；
* 表已存在（老库 / 线上库由 create_all 建出）-> 只补缺失的非主键列与索引，
  不重建、不删数据；补列一律按 nullable 落库（SQLite 不能给已有数据的表加
  NOT NULL 列，与 c2mespg001 的处理保持一致）。

因此本迁移是老库和 create_all 库都能安全走的幂等收敛，替代了不允许运行的
``flask db migrate``（autogenerate 会把 31 张表全部纳入并与线上库冲突）。

downgrade() 故意留空：这些表的生命周期归 db.create_all() 管，回退时 drop
会把本迁移出现之前就存在的数据一起删掉。

历史碎片说明（报告 E 组第 20 条）
--------------------------------
``delivery_schedules`` 与 ``sales_order_delivery_batches`` 只在
011e395c1aa4 / a3f28e475446 里 create/alter/drop 过，净结果为「两张表都不存在」，
app/models.py 里也没有对应模型（实测 app.db 中确实没有这两张表）。它们是历史
分支的中间产物，不属于本迁移要补的表，也无需清理——保留原迁移不动，避免为了
一个已经收敛的中间状态去改写已应用的历史修订。
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'p0p2messtables'
down_revision = 'p0p2mergeheads'
branch_labels = None
depends_on = None


# 31 张表的结构快照：表名 -> {columns, constraints, indexes}
# 取自 app/models.py（生成于 2026-08-28），冻结在此，不再跟随模型变化。
_TABLES = {
    'consumable_categories': {
        'columns': [
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=100), nullable=False),
            sa.Column('code', sa.String(length=20), nullable=False),
            sa.Column('description', sa.Text()),
            sa.Column('is_active', sa.Boolean()),
            sa.Column('requires_approval', sa.Boolean()),
            sa.Column('created_at', sa.DateTime()),
            sa.Column('updated_at', sa.DateTime()),
            sa.Column('created_by', sa.Integer()),
        ],
        'constraints': [
            sa.ForeignKeyConstraint(['created_by'], ['user.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('code'),
            sa.UniqueConstraint('name'),
        ],
        'indexes': [
        ],
    },
    'consumables': {
        'columns': [
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('global_sn', sa.String(length=16), nullable=False),
            sa.Column('supplier', sa.String(length=100), nullable=False),
            sa.Column('category_id', sa.Integer(), nullable=False),
            sa.Column('specification', sa.String(length=200)),
            sa.Column('supplier_number', sa.String(length=100), nullable=False),
            sa.Column('storage_date', sa.DateTime(), nullable=False),
            sa.Column('internal_number', sa.String(length=100), nullable=False),
            sa.Column('quantity', sa.Float(), nullable=False),
            sa.Column('unit', sa.String(length=20)),
            sa.Column('unit_price', sa.Float()),
            sa.Column('total_price', sa.Float()),
            sa.Column('expiry_date', sa.Date()),
            sa.Column('storage_location', sa.String(length=100)),
            sa.Column('min_stock_level', sa.Float()),
            sa.Column('notes', sa.Text()),
            sa.Column('created_at', sa.DateTime()),
            sa.Column('status', sa.String(length=20), nullable=False),
            sa.Column('is_archived', sa.Boolean()),
        ],
        'constraints': [
            sa.ForeignKeyConstraint(['category_id'], ['consumable_categories.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('global_sn'),
            sa.UniqueConstraint('global_sn', name='uq_consumable_global_sn'),
            sa.UniqueConstraint('internal_number', name='uq_consumable_internal_number'),
        ],
        'indexes': [
            ('ix_consumables_status', ['status'], False),
        ],
    },
    'equipment': {
        'columns': [
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('global_sn', sa.String(length=16), nullable=False),
            sa.Column('code', sa.String(length=50), nullable=False),
            sa.Column('name', sa.String(length=100), nullable=False),
            sa.Column('kind', sa.String(length=20), nullable=False),
            sa.Column('status', sa.String(length=20), nullable=False),
            sa.Column('length_mm', sa.Float()),
            sa.Column('width_mm', sa.Float()),
            sa.Column('height_mm', sa.Float()),
            sa.Column('notes', sa.Text()),
            sa.Column('created_at', sa.DateTime()),
        ],
        'constraints': [
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('global_sn'),
        ],
        'indexes': [
            ('ix_equipment_code', ['code'], True),
            ('ix_equipment_kind', ['kind'], False),
            ('ix_equipment_status', ['status'], False),
        ],
    },
    'equipment_capabilities': {
        'columns': [
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('equipment_id', sa.Integer(), nullable=False),
            sa.Column('process_id', sa.Integer(), nullable=False),
        ],
        'constraints': [
            sa.ForeignKeyConstraint(['equipment_id'], ['equipment.id'], ondelete='CASCADE', ),
            sa.ForeignKeyConstraint(['process_id'], ['process_price.id'], ondelete='CASCADE', ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('equipment_id', 'process_id', name='uq_equipment_process'),
        ],
        'indexes': [
        ],
    },
    'equipment_downtime': {
        'columns': [
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('equipment_id', sa.Integer(), nullable=False),
            sa.Column('started_at', sa.DateTime(), nullable=False),
            sa.Column('ended_at', sa.DateTime()),
            sa.Column('reason', sa.String(length=200), nullable=False),
            sa.Column('created_by', sa.Integer()),
        ],
        'constraints': [
            sa.ForeignKeyConstraint(['created_by'], ['user.id'], ),
            sa.ForeignKeyConstraint(['equipment_id'], ['equipment.id'], ondelete='CASCADE', ),
            sa.PrimaryKeyConstraint('id'),
        ],
        'indexes': [
        ],
    },
    'furnace_layouts': {
        'columns': [
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('equipment_id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=100), nullable=False),
            sa.Column('notes', sa.Text()),
        ],
        'constraints': [
            sa.ForeignKeyConstraint(['equipment_id'], ['equipment.id'], ondelete='CASCADE', ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('equipment_id'),
        ],
        'indexes': [
        ],
    },
    'heat_lots': {
        'columns': [
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('global_sn', sa.String(length=16), nullable=False),
            sa.Column('equipment_id', sa.Integer(), nullable=False),
            sa.Column('layout_id', sa.Integer()),
            sa.Column('status', sa.String(length=20), nullable=False),
            sa.Column('recipe_notes', sa.Text()),
            sa.Column('started_at', sa.DateTime()),
            sa.Column('ended_at', sa.DateTime()),
            sa.Column('operator_id', sa.Integer()),
            sa.Column('inspection_task_id', sa.Integer()),
            sa.Column('created_at', sa.DateTime()),
        ],
        'constraints': [
            sa.ForeignKeyConstraint(['layout_id'], ['furnace_layouts.id'], ondelete='SET NULL', ),
            sa.ForeignKeyConstraint(['equipment_id'], ['equipment.id'], ondelete='RESTRICT', ),
            sa.ForeignKeyConstraint(['operator_id'], ['user.id'], ),
            sa.ForeignKeyConstraint(['inspection_task_id'], ['inspection_tasks.id'], ondelete='SET NULL', ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('global_sn'),
        ],
        'indexes': [
            ('ix_heat_lots_status', ['status'], False),
        ],
    },
    'inventory_counts': {
        'columns': [
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('global_sn', sa.String(length=16), nullable=False),
            sa.Column('count_number', sa.String(length=50), nullable=False),
            sa.Column('count_name', sa.String(length=100), nullable=False),
            sa.Column('count_type', sa.String(length=20)),
            sa.Column('count_scope', sa.String(length=50)),
            sa.Column('warehouse_location', sa.String(length=100)),
            sa.Column('status', sa.String(length=20)),
            sa.Column('planned_date', sa.Date(), nullable=False),
            sa.Column('start_date', sa.DateTime()),
            sa.Column('end_date', sa.DateTime()),
            sa.Column('created_by', sa.Integer(), nullable=False),
            sa.Column('count_team', sa.JSON()),
            sa.Column('notes', sa.Text()),
            sa.Column('created_at', sa.DateTime()),
            sa.Column('updated_at', sa.DateTime()),
        ],
        'constraints': [
            sa.ForeignKeyConstraint(['created_by'], ['user.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('global_sn', name='uq_inventory_count_global_sn'),
            sa.UniqueConstraint('global_sn'),
            sa.UniqueConstraint('count_number', name='uq_inventory_count_number'),
        ],
        'indexes': [
            ('ix_inventory_count_date', ['planned_date'], False),
            ('ix_inventory_count_status', ['status'], False),
            ('ix_inventory_counts_count_number', ['count_number'], True),
        ],
    },
    'material_requisitions': {
        'columns': [
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('global_sn', sa.String(length=16), nullable=False),
            sa.Column('requisition_number', sa.String(length=50), nullable=False),
            sa.Column('employee_id', sa.Integer(), nullable=False),
            sa.Column('department', sa.String(length=50), nullable=False),
            sa.Column('purpose', sa.String(length=200), nullable=False),
            sa.Column('project_code', sa.String(length=50)),
            sa.Column('production_order_id', sa.Integer()),
            sa.Column('status', sa.String(length=20)),
            sa.Column('priority', sa.String(length=20)),
            sa.Column('requested_date', sa.DateTime()),
            sa.Column('required_date', sa.Date(), nullable=False),
            sa.Column('approved_by', sa.Integer()),
            sa.Column('approved_at', sa.DateTime()),
            sa.Column('issued_by', sa.Integer()),
            sa.Column('issued_at', sa.DateTime()),
            sa.Column('notes', sa.Text()),
            sa.Column('created_at', sa.DateTime()),
            sa.Column('updated_at', sa.DateTime()),
        ],
        'constraints': [
            sa.ForeignKeyConstraint(['approved_by'], ['user.id'], ),
            sa.ForeignKeyConstraint(['production_order_id'], ['production_orders.id'], ),
            sa.ForeignKeyConstraint(['employee_id'], ['employee.id'], ),
            sa.ForeignKeyConstraint(['issued_by'], ['user.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('requisition_number', name='uq_material_requisition_number'),
            sa.UniqueConstraint('global_sn', name='uq_material_requisition_global_sn'),
            sa.UniqueConstraint('global_sn'),
        ],
        'indexes': [
            ('ix_material_requisition_date', ['requested_date'], False),
            ('ix_material_requisition_status', ['status'], False),
            ('ix_material_requisitions_requisition_number', ['requisition_number'], True),
        ],
    },
    'material_returns': {
        'columns': [
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('global_sn', sa.String(length=16), nullable=False),
            sa.Column('return_number', sa.String(length=50), nullable=False),
            sa.Column('employee_id', sa.Integer(), nullable=False),
            sa.Column('department', sa.String(length=50), nullable=False),
            sa.Column('return_reason', sa.String(length=200), nullable=False),
            sa.Column('original_requisition_id', sa.Integer()),
            sa.Column('status', sa.String(length=20)),
            sa.Column('returned_date', sa.DateTime()),
            sa.Column('confirmed_by', sa.Integer()),
            sa.Column('confirmed_at', sa.DateTime()),
            sa.Column('notes', sa.Text()),
            sa.Column('created_at', sa.DateTime()),
            sa.Column('updated_at', sa.DateTime()),
        ],
        'constraints': [
            sa.ForeignKeyConstraint(['employee_id'], ['employee.id'], ),
            sa.ForeignKeyConstraint(['confirmed_by'], ['user.id'], ),
            sa.ForeignKeyConstraint(['original_requisition_id'], ['material_requisitions.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('return_number', name='uq_material_return_number'),
            sa.UniqueConstraint('global_sn', name='uq_material_return_global_sn'),
            sa.UniqueConstraint('global_sn'),
        ],
        'indexes': [
            ('ix_material_return_date', ['returned_date'], False),
            ('ix_material_return_status', ['status'], False),
            ('ix_material_returns_return_number', ['return_number'], True),
        ],
    },
    'purchase_requisitions': {
        'columns': [
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('global_sn', sa.String(length=16), nullable=False),
            sa.Column('req_no', sa.String(length=50), nullable=False),
            sa.Column('status', sa.String(length=20)),
            sa.Column('requested_by', sa.Integer()),
            sa.Column('approved_by', sa.Integer()),
            sa.Column('notes', sa.Text()),
            sa.Column('created_at', sa.DateTime()),
        ],
        'constraints': [
            sa.ForeignKeyConstraint(['requested_by'], ['user.id'], ),
            sa.ForeignKeyConstraint(['approved_by'], ['user.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('global_sn'),
        ],
        'indexes': [
            ('ix_purchase_requisitions_req_no', ['req_no'], True),
            ('ix_purchase_requisitions_status', ['status'], False),
        ],
    },
    'shipments': {
        'columns': [
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('global_sn', sa.String(length=16), nullable=False),
            sa.Column('shipment_no', sa.String(length=50), nullable=False),
            sa.Column('sales_order_id', sa.Integer(), nullable=False),
            sa.Column('status', sa.String(length=20)),
            sa.Column('shipped_at', sa.DateTime()),
            sa.Column('shipped_by', sa.Integer()),
            sa.Column('notes', sa.Text()),
            sa.Column('created_at', sa.DateTime()),
        ],
        'constraints': [
            sa.ForeignKeyConstraint(['sales_order_id'], ['sales_orders.id'], ),
            sa.ForeignKeyConstraint(['shipped_by'], ['user.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('global_sn'),
        ],
        'indexes': [
            ('ix_shipments_shipment_no', ['shipment_no'], True),
            ('ix_shipments_status', ['status'], False),
        ],
    },
    'suppliers': {
        'columns': [
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('global_sn', sa.String(length=16), nullable=False),
            sa.Column('code', sa.String(length=50), nullable=False),
            sa.Column('name', sa.String(length=100), nullable=False),
            sa.Column('contact', sa.String(length=50)),
            sa.Column('phone', sa.String(length=50)),
            sa.Column('address', sa.String(length=200)),
            sa.Column('is_active', sa.Boolean()),
            sa.Column('notes', sa.Text()),
            sa.Column('created_at', sa.DateTime()),
        ],
        'constraints': [
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('global_sn'),
        ],
        'indexes': [
            ('ix_suppliers_code', ['code'], True),
        ],
    },
    'work_centers': {
        'columns': [
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('global_sn', sa.String(length=16), nullable=False),
            sa.Column('code', sa.String(length=50), nullable=False),
            sa.Column('name', sa.String(length=100), nullable=False),
            sa.Column('notes', sa.Text()),
            sa.Column('is_active', sa.Boolean()),
            sa.Column('created_at', sa.DateTime()),
        ],
        'constraints': [
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('global_sn'),
        ],
        'indexes': [
            ('ix_work_centers_code', ['code'], True),
        ],
    },
    'workpieces': {
        'columns': [
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('global_sn', sa.String(length=16), nullable=False),
            sa.Column('code', sa.String(length=100), nullable=False),
            sa.Column('parent_code', sa.String(length=100)),
            sa.Column('status', sa.String(length=30), nullable=False),
            sa.Column('raw_material_id', sa.Integer()),
            sa.Column('batch_item_id', sa.Integer()),
            sa.Column('product_id', sa.Integer()),
            sa.Column('current_process_id', sa.Integer()),
            sa.Column('current_equipment_id', sa.Integer()),
            sa.Column('notes', sa.Text()),
            sa.Column('created_at', sa.DateTime()),
        ],
        'constraints': [
            sa.ForeignKeyConstraint(['batch_item_id'], ['production_batch_items.id'], ondelete='SET NULL', ),
            sa.ForeignKeyConstraint(['raw_material_id'], ['raw_material.id'], ondelete='SET NULL', ),
            sa.ForeignKeyConstraint(['current_equipment_id'], ['equipment.id'], ondelete='SET NULL', ),
            sa.ForeignKeyConstraint(['current_process_id'], ['process_price.id'], ondelete='SET NULL', ),
            sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='SET NULL', ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('global_sn'),
        ],
        'indexes': [
            ('ix_workpieces_code', ['code'], True),
            ('ix_workpieces_parent_code', ['parent_code'], False),
            ('ix_workpieces_status', ['status'], False),
        ],
    },
    'furnace_layout_cells': {
        'columns': [
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('layout_id', sa.Integer(), nullable=False),
            sa.Column('layer', sa.Integer(), nullable=False),
            sa.Column('row', sa.Integer(), nullable=False),
            sa.Column('col', sa.Integer(), nullable=False),
            sa.Column('zone_name', sa.String(length=50)),
            sa.Column('max_pieces', sa.Integer()),
            sa.Column('max_length_mm', sa.Float()),
            sa.Column('max_weight_kg', sa.Float()),
        ],
        'constraints': [
            sa.ForeignKeyConstraint(['layout_id'], ['furnace_layouts.id'], ondelete='CASCADE', ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('layout_id', 'layer', 'row', 'col', name='uq_furnace_cell'),
        ],
        'indexes': [
        ],
    },
    'heat_lot_slots': {
        'columns': [
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('heat_lot_id', sa.Integer(), nullable=False),
            sa.Column('workpiece_id', sa.Integer(), nullable=False),
            sa.Column('layer', sa.Integer(), nullable=False),
            sa.Column('row', sa.Integer(), nullable=False),
            sa.Column('col', sa.Integer(), nullable=False),
            sa.Column('bundle_code', sa.String(length=50)),
        ],
        'constraints': [
            sa.ForeignKeyConstraint(['workpiece_id'], ['workpieces.id'], ondelete='RESTRICT', ),
            sa.ForeignKeyConstraint(['heat_lot_id'], ['heat_lots.id'], ondelete='CASCADE', ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('heat_lot_id', 'layer', 'row', 'col', name='uq_heat_lot_cell'),
            sa.UniqueConstraint('heat_lot_id', 'workpiece_id', name='uq_heat_lot_workpiece'),
        ],
        'indexes': [
        ],
    },
    'inventory_count_items': {
        'columns': [
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('global_sn', sa.String(length=16), nullable=False),
            sa.Column('count_id', sa.Integer(), nullable=False),
            sa.Column('material_type', sa.String(length=20), nullable=False),
            sa.Column('material_id', sa.Integer(), nullable=False),
            sa.Column('system_quantity', sa.Float(), nullable=False),
            sa.Column('actual_quantity', sa.Float()),
            sa.Column('variance_quantity', sa.Float()),
            sa.Column('variance_reason', sa.String(length=200)),
            sa.Column('counted_by', sa.Integer()),
            sa.Column('counted_at', sa.DateTime()),
            sa.Column('verified_by', sa.Integer()),
            sa.Column('verified_at', sa.DateTime()),
            sa.Column('adjustment_applied', sa.Boolean()),
            sa.Column('notes', sa.Text()),
            sa.Column('created_at', sa.DateTime()),
        ],
        'constraints': [
            sa.ForeignKeyConstraint(['count_id'], ['inventory_counts.id'], ondelete='CASCADE', ),
            sa.ForeignKeyConstraint(['verified_by'], ['user.id'], ),
            sa.ForeignKeyConstraint(['counted_by'], ['user.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('global_sn', name='uq_inventory_count_item_global_sn'),
            sa.UniqueConstraint('global_sn'),
        ],
        'indexes': [
            ('ix_inventory_count_item_material', ['material_type', 'material_id'], False),
            ('ix_inventory_count_item_variance', ['variance_quantity'], False),
        ],
    },
    'material_requisition_items': {
        'columns': [
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('global_sn', sa.String(length=16), nullable=False),
            sa.Column('requisition_id', sa.Integer(), nullable=False),
            sa.Column('material_type', sa.String(length=20), nullable=False),
            sa.Column('material_id', sa.Integer(), nullable=False),
            sa.Column('quantity', sa.Float(), nullable=False),
            sa.Column('issued_quantity', sa.Float()),
            sa.Column('unit', sa.String(length=20)),
            sa.Column('notes', sa.Text()),
            sa.Column('created_at', sa.DateTime()),
        ],
        'constraints': [
            sa.ForeignKeyConstraint(['requisition_id'], ['material_requisitions.id'], ondelete='CASCADE', ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('global_sn', name='uq_material_requisition_item_global_sn'),
            sa.UniqueConstraint('global_sn'),
        ],
        'indexes': [
            ('ix_material_requisition_item_material', ['material_type', 'material_id'], False),
        ],
    },
    'material_return_items': {
        'columns': [
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('global_sn', sa.String(length=16), nullable=False),
            sa.Column('return_id', sa.Integer(), nullable=False),
            sa.Column('material_type', sa.String(length=20), nullable=False),
            sa.Column('material_id', sa.Integer(), nullable=False),
            sa.Column('quantity', sa.Float(), nullable=False),
            sa.Column('condition', sa.String(length=20)),
            sa.Column('unit', sa.String(length=20)),
            sa.Column('notes', sa.Text()),
            sa.Column('created_at', sa.DateTime()),
        ],
        'constraints': [
            sa.ForeignKeyConstraint(['return_id'], ['material_returns.id'], ondelete='CASCADE', ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('global_sn', name='uq_material_return_item_global_sn'),
            sa.UniqueConstraint('global_sn'),
        ],
        'indexes': [
            ('ix_material_return_item_material', ['material_type', 'material_id'], False),
        ],
    },
    'purchase_orders': {
        'columns': [
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('global_sn', sa.String(length=16), nullable=False),
            sa.Column('po_no', sa.String(length=50), nullable=False),
            sa.Column('supplier_id', sa.Integer(), nullable=False),
            sa.Column('requisition_id', sa.Integer()),
            sa.Column('status', sa.String(length=20)),
            sa.Column('order_date', sa.Date()),
            sa.Column('created_by', sa.Integer()),
            sa.Column('notes', sa.Text()),
            sa.Column('created_at', sa.DateTime()),
        ],
        'constraints': [
            sa.ForeignKeyConstraint(['requisition_id'], ['purchase_requisitions.id'], ondelete='SET NULL', ),
            sa.ForeignKeyConstraint(['created_by'], ['user.id'], ),
            sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('global_sn'),
        ],
        'indexes': [
            ('ix_purchase_orders_po_no', ['po_no'], True),
            ('ix_purchase_orders_status', ['status'], False),
        ],
    },
    'purchase_requisition_items': {
        'columns': [
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('requisition_id', sa.Integer(), nullable=False),
            sa.Column('material_type', sa.String(length=20)),
            sa.Column('material_name', sa.String(length=100), nullable=False),
            sa.Column('spec', sa.String(length=200)),
            sa.Column('quantity', sa.Float(), nullable=False),
            sa.Column('unit', sa.String(length=20)),
            sa.Column('notes', sa.Text()),
        ],
        'constraints': [
            sa.ForeignKeyConstraint(['requisition_id'], ['purchase_requisitions.id'], ondelete='CASCADE', ),
            sa.PrimaryKeyConstraint('id'),
        ],
        'indexes': [
        ],
    },
    'purchase_settlements': {
        'columns': [
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('global_sn', sa.String(length=16), nullable=False),
            sa.Column('po_id', sa.Integer(), nullable=False),
            sa.Column('amount', sa.Float(), nullable=False),
            sa.Column('status', sa.String(length=20)),
            sa.Column('paid_at', sa.DateTime()),
            sa.Column('notes', sa.Text()),
            sa.Column('created_at', sa.DateTime()),
        ],
        'constraints': [
            sa.ForeignKeyConstraint(['po_id'], ['purchase_orders.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('global_sn'),
        ],
        'indexes': [
            ('ix_purchase_settlements_status', ['status'], False),
        ],
    },
    'shipment_items': {
        'columns': [
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('shipment_id', sa.Integer(), nullable=False),
            sa.Column('sales_order_item_id', sa.Integer()),
            sa.Column('finished_product_id', sa.Integer()),
            sa.Column('workpiece_id', sa.Integer()),
            sa.Column('quantity', sa.Float(), nullable=False),
        ],
        'constraints': [
            sa.ForeignKeyConstraint(['workpiece_id'], ['workpieces.id'], ondelete='SET NULL', ),
            sa.ForeignKeyConstraint(['finished_product_id'], ['finished_product.id'], ondelete='SET NULL', ),
            sa.ForeignKeyConstraint(['shipment_id'], ['shipments.id'], ondelete='CASCADE', ),
            sa.ForeignKeyConstraint(['sales_order_item_id'], ['sales_order_items.id'], ondelete='SET NULL', ),
            sa.PrimaryKeyConstraint('id'),
        ],
        'indexes': [
        ],
    },
    'shipment_receipts': {
        'columns': [
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('shipment_id', sa.Integer(), nullable=False),
            sa.Column('signed_at', sa.DateTime()),
            sa.Column('signed_by_name', sa.String(length=100), nullable=False),
            sa.Column('notes', sa.Text()),
            sa.Column('attachment_path', sa.String(length=300)),
        ],
        'constraints': [
            sa.ForeignKeyConstraint(['shipment_id'], ['shipments.id'], ondelete='CASCADE', ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('shipment_id'),
        ],
        'indexes': [
        ],
    },
    'task_workpieces': {
        'columns': [
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('task_id', sa.Integer(), nullable=False),
            sa.Column('workpiece_id', sa.Integer(), nullable=False),
            sa.Column('status', sa.String(length=20)),
        ],
        'constraints': [
            sa.ForeignKeyConstraint(['workpiece_id'], ['workpieces.id'], ondelete='RESTRICT', ),
            sa.ForeignKeyConstraint(['task_id'], ['task_assignment.id'], ondelete='CASCADE', ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('task_id', 'workpiece_id', name='uq_task_workpiece'),
        ],
        'indexes': [
        ],
    },
    'work_center_equipment': {
        'columns': [
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('work_center_id', sa.Integer(), nullable=False),
            sa.Column('equipment_id', sa.Integer(), nullable=False),
        ],
        'constraints': [
            sa.ForeignKeyConstraint(['work_center_id'], ['work_centers.id'], ondelete='CASCADE', ),
            sa.ForeignKeyConstraint(['equipment_id'], ['equipment.id'], ondelete='CASCADE', ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('work_center_id', 'equipment_id', name='uq_work_center_equipment'),
        ],
        'indexes': [
        ],
    },
    'workpiece_events': {
        'columns': [
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('workpiece_id', sa.Integer(), nullable=False),
            sa.Column('event_type', sa.String(length=40), nullable=False),
            sa.Column('at', sa.DateTime()),
            sa.Column('user_id', sa.Integer()),
            sa.Column('heat_lot_id', sa.Integer()),
            sa.Column('equipment_id', sa.Integer()),
            sa.Column('inspection_record_id', sa.Integer()),
            sa.Column('task_id', sa.Integer()),
            sa.Column('payload', sa.JSON()),
        ],
        'constraints': [
            sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
            sa.ForeignKeyConstraint(['equipment_id'], ['equipment.id'], ondelete='SET NULL', ),
            sa.ForeignKeyConstraint(['workpiece_id'], ['workpieces.id'], ondelete='CASCADE', ),
            sa.ForeignKeyConstraint(['task_id'], ['task_assignment.id'], ondelete='SET NULL', ),
            sa.ForeignKeyConstraint(['inspection_record_id'], ['inspection_records.id'], ondelete='SET NULL', ),
            sa.ForeignKeyConstraint(['heat_lot_id'], ['heat_lots.id'], ondelete='SET NULL', ),
            sa.PrimaryKeyConstraint('id'),
        ],
        'indexes': [
            ('ix_workpiece_events_at', ['at'], False),
            ('ix_workpiece_events_event_type', ['event_type'], False),
            ('ix_workpiece_events_workpiece_id', ['workpiece_id'], False),
        ],
    },
    'goods_receipts': {
        'columns': [
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('global_sn', sa.String(length=16), nullable=False),
            sa.Column('receipt_no', sa.String(length=50), nullable=False),
            sa.Column('po_id', sa.Integer(), nullable=False),
            sa.Column('status', sa.String(length=30)),
            sa.Column('received_at', sa.DateTime()),
            sa.Column('received_by', sa.Integer()),
            sa.Column('inspection_task_id', sa.Integer()),
            sa.Column('notes', sa.Text()),
        ],
        'constraints': [
            sa.ForeignKeyConstraint(['received_by'], ['user.id'], ),
            sa.ForeignKeyConstraint(['inspection_task_id'], ['inspection_tasks.id'], ondelete='SET NULL', ),
            sa.ForeignKeyConstraint(['po_id'], ['purchase_orders.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('global_sn'),
        ],
        'indexes': [
            ('ix_goods_receipts_receipt_no', ['receipt_no'], True),
            ('ix_goods_receipts_status', ['status'], False),
        ],
    },
    'purchase_order_items': {
        'columns': [
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('po_id', sa.Integer(), nullable=False),
            sa.Column('material_type', sa.String(length=20)),
            sa.Column('category_id', sa.Integer()),
            sa.Column('name', sa.String(length=100), nullable=False),
            sa.Column('spec', sa.String(length=200)),
            sa.Column('quantity', sa.Float(), nullable=False),
            sa.Column('received_qty', sa.Float()),
            sa.Column('unit_price', sa.Float()),
            sa.Column('unit', sa.String(length=20)),
        ],
        'constraints': [
            sa.ForeignKeyConstraint(['po_id'], ['purchase_orders.id'], ondelete='CASCADE', ),
            sa.PrimaryKeyConstraint('id'),
        ],
        'indexes': [
        ],
    },
    'goods_receipt_items': {
        'columns': [
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('receipt_id', sa.Integer(), nullable=False),
            sa.Column('po_item_id', sa.Integer()),
            sa.Column('quantity', sa.Float(), nullable=False),
        ],
        'constraints': [
            sa.ForeignKeyConstraint(['po_item_id'], ['purchase_order_items.id'], ondelete='SET NULL', ),
            sa.ForeignKeyConstraint(['receipt_id'], ['goods_receipts.id'], ondelete='CASCADE', ),
            sa.PrimaryKeyConstraint('id'),
        ],
        'indexes': [
        ],
    },
}

# 建表顺序：被外键引用的表排在前面（Postgres 需要引用表先存在）。
_CREATION_ORDER = [
    'consumable_categories',
    'consumables',
    'equipment',
    'equipment_capabilities',
    'equipment_downtime',
    'furnace_layouts',
    'heat_lots',
    'inventory_counts',
    'material_requisitions',
    'material_returns',
    'purchase_requisitions',
    'shipments',
    'suppliers',
    'work_centers',
    'workpieces',
    'furnace_layout_cells',
    'heat_lot_slots',
    'inventory_count_items',
    'material_requisition_items',
    'material_return_items',
    'purchase_orders',
    'purchase_requisition_items',
    'purchase_settlements',
    'shipment_items',
    'shipment_receipts',
    'task_workpieces',
    'work_center_equipment',
    'workpiece_events',
    'goods_receipts',
    'purchase_order_items',
    'goods_receipt_items',
]


def _nullable(column):
    """补列专用的副本：老库已有数据，只能按可空列追加。"""
    return sa.Column(column.name, column.type, nullable=True)


def _ensure_table(name, spec):
    inspector = sa.inspect(op.get_bind())
    if name not in inspector.get_table_names():
        op.create_table(name, *spec['columns'], *spec['constraints'])
        for index_name, columns, unique in spec['indexes']:
            op.create_index(index_name, name, columns, unique=unique)
        return

    present_columns = {c['name'] for c in inspector.get_columns(name)}
    missing_columns = [c for c in spec['columns']
                       if c.name not in present_columns and not c.primary_key]
    if missing_columns:
        with op.batch_alter_table(name, schema=None) as batch_op:
            for column in missing_columns:
                batch_op.add_column(_nullable(column))

    present_indexes = {i['name'] for i in inspector.get_indexes(name)}
    for index_name, columns, unique in spec['indexes']:
        if index_name not in present_indexes:
            op.create_index(index_name, name, columns, unique=unique)


def upgrade():
    for name in _CREATION_ORDER:
        _ensure_table(name, _TABLES[name])


def downgrade():
    # 见模块 docstring：这些表的所有权在 db.create_all()，回退不做破坏性删除。
    pass
