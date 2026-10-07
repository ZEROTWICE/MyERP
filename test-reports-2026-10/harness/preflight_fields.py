"""t4 预检：确认写断言用到的模型字段/关系确实存在（防止断言因拼错字段而假失败）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402

sys.path.insert(0, _env.REPO_ROOT)

CHECKS = {
    'Equipment': ['length_mm', 'height_mm', 'code', 'name', 'kind', 'status', 'notes', 'width_mm'],
    'EquipmentDowntime': ['equipment_id', 'reason', 'ended_at', 'created_by'],
    'HeatLot': ['equipment_id', 'status', 'recipe_notes'],
    'Shipment': ['sales_order_id', 'status', 'signed_by_name', 'shipped_at', 'shipped_by', 'notes'],    'ShipmentItem': ['shipment_id', 'finished_product_id', 'quantity'],
    'Notification': ['user_id', 'title', 'content', 'is_read'],
    'PurchaseRequisition': ['notes', 'status'],
    'PurchaseOrder': ['supplier_id', 'notes', 'status'],
    'GoodsReceipt': ['status'],
    'InspectionTemplate': ['base_items', 'is_active', 'template_code', 'type'],
    'RawMaterial': ['is_archived', 'internal_number', 'category_id', 'quantity'],
    'Consumable': ['quantity', 'status', 'specification', 'unit_price'],
    'InspectionTask': ['priority', 'inspector_id', 'status', 'notes', 'template_id'],
    'InspectionRecord': ['result', 'notes', 'task_id', 'inspector_id'],
    'TaskAssignment': ['completed_quantity', 'completed_at', 'notes', 'status', 'quantity'],
    'ProductionOrder': ['planned_quantity', 'status', 'notes', 'product_id'],
    'ProductionBatch': ['batch_quantity', 'status', 'production_order_id'],
    'ProductionBatchItem': ['quality_status', 'status', 'batch_id', 'item_sequence',
                            'product_code'],
    'ProductBOM': ['product_id', 'material_type', 'material_id'],
    'ProductProcess': ['product_id', 'process_id', 'sequence'],
    'CodeRule': ['rule_name', 'prefix'],
    'MaterialRequisition': ['purpose', 'status', 'items', 'employee_id'],
    'Customer': ['name'],
    'Product': ['product_code', 'product_name', 'unit', 'specification'],
    'FinishedProduct': ['product_number', 'drawing_number', 'quantity', 'status', 'stock_kind'],
    'SalesOrder': ['customer_id', 'order_number'],
    'SalesOrderItem': ['order_id', 'product_id', 'quantity', 'unit_price'],
    'Supplier': ['code', 'name'],
    'RawMaterialCategory': ['name', 'code', 'is_active'],
}

BAD = 0
for cls_name, fields in CHECKS.items():
    cls = getattr(__import__('app.models', fromlist=['x']), cls_name, None)
    if cls is None:
        print(f'MODEL-MISSING {cls_name}')
        BAD += 1
        continue
    cols = {c.name for c in cls.__table__.columns}
    missing = [f for f in fields if f not in cols and not hasattr(cls, f)]
    rel = [f for f in fields if f not in cols and hasattr(cls, f)]
    status = 'OK' if not missing else 'MISSING'
    if missing:
        BAD += 1
    print(f'{status:8s} {cls_name:26s} cols={len(cols):3d} relations={rel} missing={missing}')
    if missing:
        print(f'         ALLCOLS={sorted(cols)}')
print(f'\n结论：字段问题 {BAD} 处')
sys.exit(0)
