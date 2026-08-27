"""道岔产销领域服务：工件履历、质检门禁、完工入库、组装扣料。"""
from datetime import date, datetime

from flask import current_app
from flask_login import current_user

from app import db
from app.models import (
    AuditLog, Equipment, EquipmentCapability, FinishedProduct, InspectionTemplate, InspectionTask,
    MaterialAllocation, NonconformityRecord, ProcessPrice, Product, ProductBOM,
    ProductProcess, ProductionRecord, RawMaterial, SerialNumber, SystemConfig,
    TaskAssignment, TaskWorkpiece, User, WorkCenterEquipment, Workpiece, WorkpieceEvent,
)


WORKPIECE_STATUSES = (
    'raw', 'charging', 'calcined', 'machining', 'assembled',
    'fg', 'sold_as_part', 'failed', 'scrap',
)


def log_event(workpiece, event_type, **kwargs):
    ev = WorkpieceEvent(
        workpiece_id=workpiece.id,
        event_type=event_type,
        user_id=getattr(current_user, 'id', None) if current_user else None,
        **kwargs
    )
    db.session.add(ev)
    return ev


def ensure_workpiece(*, code, product_id=None, raw_material_id=None, batch_item_id=None,
                     parent_code=None, status='raw'):
    wp = Workpiece.query.filter_by(code=code).first()
    if wp:
        return wp
    wp = Workpiece(
        code=code,
        product_id=product_id,
        raw_material_id=raw_material_id,
        batch_item_id=batch_item_id,
        parent_code=parent_code,
        status=status,
    )
    db.session.add(wp)
    db.session.flush()
    log_event(wp, 'created', payload={'status': status})
    return wp


def default_inspector_id():
    user = User.query.filter(User.role.in_(['inspector', 'admin'])).first()
    return user.id if user else (getattr(current_user, 'id', None) or 1)


def pick_template(target_type):
    """质检任务尽量绑模板，避免检验员每次手选。"""
    return InspectionTemplate.query.filter_by(type=target_type, is_active=True).first()


def create_inspection_task(target_type, target_id, notes=''):
    template = pick_template(target_type)
    # 模板类型可能只有 production_record/material/product，工件/炉次复用最近的生产记录模板
    if template is None and target_type in ('workpiece', 'heat_lot', 'goods_receipt'):
        template = pick_template('production_record') or pick_template('material') or pick_template('product')
    inspector_id = default_inspector_id()
    task = InspectionTask(
        global_sn=SerialNumber.get_next_number(),
        template_id=template.id if template else None,
        inspector_id=inspector_id,
        target_type=target_type,
        target_id=target_id,
        status='pending',
        notes=notes,
        created_by=getattr(current_user, 'id', None) or inspector_id,
    )
    db.session.add(task)
    db.session.flush()
    return task


def workpiece_blocked(workpiece):
    """未闭环的不合格或未通过质检则不得进入下一工作中心。"""
    if workpiece.status in ('failed', 'scrap'):
        return True
    open_nc = NonconformityRecord.query.filter_by(
        workpiece_id=workpiece.id
    ).filter(NonconformityRecord.status.in_(['open', 'pending_approval'])).first()
    return open_nc is not None


def qc_gate_allows(workpiece, next_stage=None):
    if workpiece_blocked(workpiece):
        return False, '工件存在未处置的不合格或已报废'
    pending = InspectionTask.query.filter_by(
        target_type='workpiece', target_id=workpiece.id
    ).filter(InspectionTask.status.in_(['pending', 'in_progress'])).first()
    if pending:
        return False, '存在未完成的质检任务'
    return True, None


def inbound_workpiece(workpiece, stock_kind='fg', inspector_name='系统', product=None):
    """末道通过后入库。stock_kind: fg / wip_part / failed / scrap。"""
    product = product or (Product.query.get(workpiece.product_id) if workpiece.product_id else None)
    status_map = {
        'fg': 'in_stock',
        'wip_part': 'in_stock',
        'failed': 'in_stock',
        'scrap': 'scrapped',
    }
    fp = FinishedProduct(
        product_number=workpiece.code,
        production_date=date.today(),
        drawing_number=(product.drawing_number if product else '') or '-',
        model=(product.model if product else '') or '-',
        inspector=inspector_name or '系统',
        quantity=1,
        status=status_map.get(stock_kind, 'in_stock'),
        stock_kind=stock_kind,
        workpiece_id=workpiece.id,
        product_id=workpiece.product_id,
        notes=f'由工件 {workpiece.code} 自动入库',
    )
    db.session.add(fp)
    if stock_kind == 'fg':
        workpiece.status = 'fg'
    elif stock_kind == 'wip_part':
        workpiece.status = 'machining'
    elif stock_kind == 'failed':
        workpiece.status = 'failed'
    elif stock_kind == 'scrap':
        workpiece.status = 'scrap'
    log_event(workpiece, 'inbound', payload={'stock_kind': stock_kind, 'finished_product_id': None})
    db.session.flush()
    return fp


def apply_inspection_result(record):
    """质检提交后的门禁与不合格处置入口。"""
    task = record.task
    if not task:
        return
    workpiece = None
    if task.target_type == 'workpiece':
        workpiece = Workpiece.query.get(task.target_id)
    elif task.target_type == 'heat_lot':
        from app.models import HeatLotSlot
        for slot in HeatLotSlot.query.filter_by(heat_lot_id=task.target_id).all():
            apply_lot_item_result(slot.workpiece, record)
        return
    elif task.target_type == 'goods_receipt':
        return

    if workpiece is None:
        return

    log_event(workpiece, 'inspection', inspection_record_id=record.id,
              payload={'result': record.result})

    if record.result == 'pass':
        if workpiece.status in ('raw', 'charging'):
            workpiece.status = 'calcined'
            return
        if workpiece.status == 'assembled':
            inbound_workpiece(workpiece, stock_kind='fg',
                              inspector_name=getattr(current_user, 'username', '系统'))
            return
        workpiece.status = 'machining'
        routing = ProductProcess.query.filter_by(product_id=workpiece.product_id).order_by(ProductProcess.sequence).all()
        current_seq = None
        for pp in routing:
            if workpiece.current_process_id and pp.process_id == workpiece.current_process_id:
                current_seq = pp.sequence
        later = [pp for pp in routing if current_seq is not None and pp.sequence > current_seq]
        if current_seq is None and routing:
            later = routing[1:]
        if not later:
            inbound_workpiece(workpiece, stock_kind='fg',
                              inspector_name=getattr(current_user, 'username', '系统'))
        elif later and all((pp.process_stage or 'machine') == 'assemble' for pp in later):
            inbound_workpiece(workpiece, stock_kind='wip_part',
                              inspector_name=getattr(current_user, 'username', '系统'))
        return

    if record.result == 'fail':
        workpiece.status = 'failed'
        nc = NonconformityRecord(
            record_id=record.id,
            type='rework',
            handler_id=getattr(current_user, 'id', None) or default_inspector_id(),
            handling_date=date.today(),
            handling_result='待处置',
            notes='质检不合格，等待返工/报废/让步',
            status='open',
            workpiece_id=workpiece.id,
        )
        db.session.add(nc)
        inbound_workpiece(workpiece, stock_kind='failed',
                          inspector_name=getattr(current_user, 'username', '系统'))


def apply_lot_item_result(workpiece, record):
    log_event(workpiece, 'inspection', inspection_record_id=record.id,
              payload={'result': record.result, 'source': 'heat_lot'})
    if record.result == 'pass':
        workpiece.status = 'calcined'
    elif record.result == 'fail':
        workpiece.status = 'failed'


def dispose_nonconformity(nc, action, *, notes='', scrap_cost=0, rework_process_id=None,
                          employee_id=None, target_date=None):
    """action: rework / scrap / accept。"""
    nc.type = action
    nc.handling_result = notes or nc.handling_result
    nc.notes = notes or nc.notes
    nc.handling_date = date.today()
    wp = Workpiece.query.get(nc.workpiece_id) if nc.workpiece_id else None

    if action == 'accept':
        roles = SystemConfig.get('quality.concession_approver_roles', ['admin', 'manager']) or ['admin', 'manager']
        if getattr(current_user, 'role', None) not in roles:
            nc.status = 'pending_approval'
            return nc
        nc.status = 'approved'
        nc.approver_id = current_user.id
        nc.approved_at = datetime.utcnow()
        if wp:
            wp.status = 'calcined' if wp.status == 'failed' else wp.status
            log_event(wp, 'concession', payload={'nc_id': nc.id})
        return nc

    if action == 'rework':
        if not wp:
            nc.status = 'done'
            return nc
        process_id = rework_process_id
        if not process_id:
            last = TaskWorkpiece.query.filter_by(workpiece_id=wp.id).order_by(TaskWorkpiece.id.desc()).first()
            process_id = last.task.process_id if last and last.task else None
        if not process_id:
            raise ValueError('返工需要指定工序')
        emp_id = employee_id
        if not emp_id:
            from app.models import Employee
            emp = Employee.query.filter_by(user_id=current_user.id).first() or Employee.query.first()
            emp_id = emp.id if emp else None
        if not emp_id:
            raise ValueError('返工需要指定员工')
        task = TaskAssignment(
            employee_id=emp_id,
            process_id=process_id,
            target_date=target_date or date.today(),
            quantity=1,
            status='pending',
            task_type='auto',
            notes=f'返工 不合格单#{nc.id}',
        )
        db.session.add(task)
        db.session.flush()
        db.session.add(TaskWorkpiece(task_id=task.id, workpiece_id=wp.id, status='pending'))
        nc.rework_task_id = task.id
        nc.status = 'done'
        wp.status = 'machining'
        log_event(wp, 'rework', task_id=task.id, payload={'nc_id': nc.id})
        return nc

    if action == 'scrap':
        nc.scrap_cost = scrap_cost or 0
        nc.status = 'done'
        if wp:
            wp.status = 'scrap'
            inbound_workpiece(wp, stock_kind='scrap',
                              inspector_name=getattr(current_user, 'username', '系统'))
            if wp.raw_material_id:
                mat = RawMaterial.query.get(wp.raw_material_id)
                if mat and mat.quantity > 0:
                    mat.quantity = max(0, mat.quantity - 1)
            log_event(wp, 'scrap', payload={'nc_id': nc.id, 'scrap_cost': nc.scrap_cost})
        return nc

    raise ValueError('未知处置类型')


def consume_bom_for_assembly(product, quantity=1, scanned_workpiece_ids=None):
    """组装：自制件扫码出库，标准件按数量扣。"""
    scanned = set(scanned_workpiece_ids or [])
    consumed = []
    shortages = []
    for bom in product.bom_items:
        need = (bom.quantity or 1) * quantity
        if bom.material_type == 'product':
            # 自制件：从半成品库按扫码扣
            remaining = need
            for wp_id in list(scanned):
                if remaining <= 0:
                    break
                wp = Workpiece.query.get(wp_id)
                if not wp or wp.product_id != bom.material_id:
                    continue
                fp = FinishedProduct.query.filter_by(
                    workpiece_id=wp.id, stock_kind='wip_part', status='in_stock'
                ).first()
                if not fp:
                    continue
                fp.status = 'used'
                wp.status = 'assembled'
                remaining -= 1
                scanned.discard(wp_id)
                consumed.append({'workpiece': wp.code, 'bom_id': bom.id})
                log_event(wp, 'assembled_into', payload={'product_id': product.id})
            if remaining > 0:
                shortages.append({'bom_id': bom.id, 'name': bom.material_name, 'qty': remaining})
        else:
            if bom.material_type == 'raw':
                mat = RawMaterial.query.get(bom.material_id)
                if not mat or mat.quantity < need:
                    shortages.append({'bom_id': bom.id, 'name': bom.material_name, 'qty': need})
                else:
                    mat.quantity -= need
                    consumed.append({'material_id': mat.id, 'qty': need})
                    alloc = MaterialAllocation.query.filter_by(
                        material_type='raw', material_id=mat.id
                    ).order_by(MaterialAllocation.id.desc()).first()
                    if alloc:
                        alloc.consumed_quantity = (alloc.consumed_quantity or 0) + need
            else:
                from app.models import Consumable
                item = Consumable.query.get(bom.material_id)
                if not item or item.quantity < need:
                    shortages.append({'bom_id': bom.id, 'name': bom.material_name, 'qty': need})
                else:
                    item.quantity -= need
                    consumed.append({'consumable_id': item.id, 'qty': need})
    return consumed, shortages


def write_consumed_allocation(production_order_id, material_type, material_id, qty):
    alloc = MaterialAllocation.query.filter_by(
        production_order_id=production_order_id,
        material_type=material_type,
        material_id=material_id,
    ).first()
    if alloc:
        alloc.consumed_quantity = (alloc.consumed_quantity or 0) + qty
        if alloc.allocated_quantity is None or alloc.allocated_quantity == 0:
            alloc.allocated_quantity = qty
    return alloc


def equipment_available(equipment):
    if equipment is None:
        return False, '未指定设备'
    if equipment.status != 'running':
        return False, f'设备 {equipment.code} 当前状态为 {equipment.status}'
    return True, None


def product_has_routing(product):
    return product is not None and product.process_items.count() > 0


def get_stock_row(material_type, material_id):
    from app.models import Consumable
    if material_type == 'raw':
        return RawMaterial.query.get(material_id)
    if material_type == 'consumable':
        return Consumable.query.get(material_id)
    if material_type == 'finished':
        return FinishedProduct.query.get(material_id)
    return None


def line_requires_approval(material_type, material_id):
    """原材料默认要审批；易耗品默认免审；成品一律审批。NULL 列走默认。"""
    row = get_stock_row(material_type, material_id)
    if row is None:
        raise ValueError('物料不存在')
    if material_type == 'finished':
        return True
    cat = getattr(row, 'category', None)
    if material_type == 'raw':
        if cat is None or cat.requires_approval is None:
            return True
        return bool(cat.requires_approval)
    if material_type == 'consumable':
        if cat is None or cat.requires_approval is None:
            return False
        return bool(cat.requires_approval)
    return True


def deduct_stock(material_type, material_id, qty, production_order_id=None):
    row = get_stock_row(material_type, material_id)
    if row is None:
        raise ValueError('物料不存在')
    available = row.quantity or 0
    if material_type == 'finished' and getattr(row, 'status', None) != 'in_stock':
        raise ValueError('成品不在库')
    if available < qty:
        raise ValueError('库存不足')
    row.quantity = available - qty
    if row.quantity <= 0:
        row.status = 'used'
    if production_order_id:
        write_consumed_allocation(production_order_id, material_type, material_id, qty)
    return row


def restock(material_type, material_id, qty):
    row = get_stock_row(material_type, material_id)
    if row is None:
        raise ValueError('物料不存在')
    row.quantity = (row.quantity or 0) + qty
    row.status = 'in_stock'
    return row


def issue_requisition(requisition, user_id):
    if not requisition.can_issue:
        raise ValueError('当前状态不可发料')
    items = requisition.items.all()
    for item in items:
        row = get_stock_row(item.material_type, item.material_id)
        if row is None:
            raise ValueError(f'{item.material_name} 不存在')
        available = row.quantity or 0
        if item.material_type == 'finished' and getattr(row, 'status', None) != 'in_stock':
            raise ValueError(f'{item.material_name} 不在库')
        if available < item.quantity:
            raise ValueError(f'{item.material_name} 库存不足')
    for item in items:
        deduct_stock(
            item.material_type, item.material_id, item.quantity,
            production_order_id=requisition.production_order_id,
        )
        item.issued_quantity = item.quantity
    requisition.status = 'completed'
    requisition.issued_by = user_id
    requisition.issued_at = datetime.utcnow()
    return requisition


def confirm_return(ret, user_id):
    if not ret.can_confirm:
        raise ValueError('当前状态不可确认归还')
    for item in ret.items.all():
        if (item.condition or 'good') == 'good':
            restock(item.material_type, item.material_id, item.quantity)
    ret.status = 'confirmed'
    ret.confirmed_by = user_id
    ret.confirmed_at = datetime.utcnow()
    return ret


def snapshot_inventory_count(count):
    from app.models import Consumable, InventoryCountItem
    scope = count.count_scope or 'all'
    kinds = ['raw', 'consumable', 'finished'] if scope == 'all' else [scope]
    if 'raw' in kinds:
        for m in RawMaterial.query.filter_by(is_archived=False, status='in_stock').all():
            db.session.add(InventoryCountItem(
                count_id=count.id, material_type='raw', material_id=m.id,
                system_quantity=m.quantity or 0,
            ))
    if 'consumable' in kinds:
        for m in Consumable.query.filter_by(is_archived=False, status='in_stock').all():
            db.session.add(InventoryCountItem(
                count_id=count.id, material_type='consumable', material_id=m.id,
                system_quantity=m.quantity or 0,
            ))
    if 'finished' in kinds:
        for m in FinishedProduct.query.filter_by(is_archived=False, status='in_stock').all():
            db.session.add(InventoryCountItem(
                count_id=count.id, material_type='finished', material_id=m.id,
                system_quantity=m.quantity or 0,
            ))


def apply_inventory_count(count):
    if count.status != 'counting':
        raise ValueError('仅盘点中的单据可以完成调账')
    if count.total_items > 0 and count.completed_items != count.total_items:
        raise ValueError('尚有未录入实盘数量的明细')
    for item in count.items.all():
        if item.adjustment_applied:
            continue
        actual = item.actual_quantity if item.actual_quantity is not None else item.system_quantity
        item.variance_quantity = (actual or 0) - (item.system_quantity or 0)
        row = get_stock_row(item.material_type, item.material_id)
        if row is not None:
            row.quantity = actual or 0
            if item.material_type == 'finished':
                row.status = 'in_stock' if (actual or 0) > 0 else 'scrapped'
            else:
                row.status = 'in_stock' if (actual or 0) > 0 else 'used'
        item.adjustment_applied = True
    count.status = 'completed'
    count.end_date = datetime.utcnow()
    return count


def pick_equipment_for_process(process_id, work_center_id=None):
    q = Equipment.query.filter_by(status='running')
    if work_center_id:
        from app.models import WorkCenterEquipment
        ids = [m.equipment_id for m in WorkCenterEquipment.query.filter_by(work_center_id=work_center_id).all()]
        if ids:
            q = q.filter(Equipment.id.in_(ids))
    capable_ids = [c.equipment_id for c in
                   EquipmentCapability.query.filter_by(process_id=process_id).all()]
    if capable_ids:
        q = q.filter(Equipment.id.in_(capable_ids))
    return q.first()
