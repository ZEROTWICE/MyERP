"""道岔产销领域服务：工件履历、质检门禁、完工入库、组装扣料、报工扣料归集、来料检处置。"""
from datetime import date, datetime

from flask import current_app
from flask_login import current_user

from app import db
from app.models import (
    AuditLog, Equipment, EquipmentCapability, FinishedProduct, GoodsReceipt, InspectionTemplate,
    InspectionTask, MaterialAllocation, NonconformityRecord, ProcessPrice, Product, ProductBOM,
    ProductProcess, ProductionBatch, ProductionBatchItem, ProductionRecord, RawMaterial,
    RawMaterialCategory, SerialNumber, Shipment, ShipmentItem, SystemConfig, Consumable,
    ConsumableCategory, TaskAssignment, TaskWorkpiece, User, WorkCenterEquipment, Workpiece,
    WorkpieceEvent,
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


def operator_name(inspector_name=None):
    """履历/入库单上的操作人：优先调用方给定；无请求上下文（脚本、后台任务）时退回默认值。"""
    if inspector_name:
        return inspector_name
    try:
        return getattr(current_user, 'username', None) or '系统'
    except Exception:
        return '系统'


def operator_id(default=None):
    """当前操作用户 id；无请求上下文（脚本、后台任务）时退回默认值。"""
    try:
        return getattr(current_user, 'id', None) or default
    except Exception:
        return default


def current_role():
    """当前用户角色；无请求上下文时返回 None（供角色门槛判断，避免 LocalProxy 抛异常）。"""
    try:
        return getattr(current_user, 'role', None)
    except Exception:
        return None


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


def is_last_process(product_id, process_id):
    """process_id 是否为该产品工艺路线的末道工序（与 apply_inspection_result 的判定同口径）。

    无工艺路线（没有后续工序）视为末道；process_id 不在路线里时，只有单工序路线才算末道。
    """
    if not product_id or not process_id:
        return False
    routing = ProductProcess.query.filter_by(product_id=product_id).order_by(ProductProcess.sequence).all()
    if not routing:
        return True
    for index, pp in enumerate(routing):
        if pp.process_id == process_id:
            return index == len(routing) - 1
    return len(routing) <= 1


def batch_item_production_records(batch_item):
    """实例关联的生产记录：按 notes 里的 {"batch_item_id": N} 软关联（与生产中心同约定，不新增列）。"""
    if batch_item is None or batch_item.id is None:
        return []
    return ProductionRecord.query.filter(
        ProductionRecord.notes.contains(f'"batch_item_id": {batch_item.id}')
    ).all()


def qc_gate_allows_output(batch_item=None, workpieces=None, production_record=None):
    """报工/批次产出的入库门禁：与 qc_gate_allows 同口径，但没有工件也能判。

    拒绝条件（依据既有 qc_gate_allows / apply_inspection_result 口径）：
      1. 批次实例已判定不合格（quality_status=fail）或质检未出结果（pending）；
      2. 关联工件存在未处置的不合格或已报废（复用 workpiece_blocked）；
      3. 产出对应的生产记录存在未完成的质检任务，或存在未闭环的不合格记录。

    返回 (allowed, message)。
    """
    if batch_item is not None:
        code = batch_item.product_code or f'实例#{batch_item.id}'
        quality_status = (batch_item.quality_status or '').strip().lower()
        if quality_status in ('fail', 'failed', 'rejected'):
            return False, f'实例 {code} 质检不合格，不得入正品库'
        if quality_status in ('pending', 'pending_inspection'):
            return False, f'实例 {code} 质检未出结果，不得入正品库'
        if (batch_item.status or '') == 'scrapped':
            return False, f'实例 {code} 已报废，不得入正品库'

    records = []
    if production_record is not None:
        records.append(production_record)
    if batch_item is not None:
        records.extend(batch_item_production_records(batch_item))
    record_ids = [r.id for r in records if getattr(r, 'id', None)]

    if record_ids:
        pending = InspectionTask.query.filter(
            InspectionTask.target_type == 'production_record',
            InspectionTask.target_id.in_(record_ids),
            InspectionTask.status.in_(['pending', 'in_progress']),
        ).first()
        if pending is not None:
            return False, '产出存在未完成的质检任务，不得入正品库'
        open_nc = NonconformityRecord.query.filter(
            NonconformityRecord.record_id.in_(record_ids),
            NonconformityRecord.status.in_(['open', 'pending_approval']),
        ).first()
        if open_nc is not None:
            return False, '产出存在未处置的不合格记录，不得入正品库'

    for wp in workpieces or ():
        if workpiece_blocked(wp):
            return False, f'{wp.code}: 存在未处置的不合格或已报废'
        pending = InspectionTask.query.filter_by(
            target_type='workpiece', target_id=wp.id
        ).filter(InspectionTask.status.in_(['pending', 'in_progress'])).first()
        if pending is not None:
            return False, f'{wp.code}: 存在未完成的质检任务'
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


def task_batch_item(task):
    """报工任务挂接的批次实例（batch_item_id），没有则 None。"""
    if task is None or not getattr(task, 'batch_item_id', None):
        return None
    return ProductionBatchItem.query.get(task.batch_item_id)


def task_workpieces(task):
    """报工任务关联的工件（经任务-工件关联表），用于补工件履历。"""
    if task is None:
        return []
    links = task.workpiece_links.all()
    return [link.workpiece for link in links if link.workpiece is not None]


def batch_item_workpieces(batch_item):
    """实例关联的工件：经该实例下任务的任务-工件关联表取（无工件时返回空表）。"""
    if batch_item is None or batch_item.id is None:
        return []
    links = (TaskWorkpiece.query
             .join(TaskAssignment, TaskWorkpiece.task_id == TaskAssignment.id)
             .filter(TaskAssignment.batch_item_id == batch_item.id).all())
    return [link.workpiece for link in links if link.workpiece is not None]


def inbound_production_output(*, production_order=None, batch=None, batch_item=None,
                              task=None, product=None, product_number=None,
                              quantity=None, process_id=None, inspector_name=None,
                              notes='', production_date=None, workpieces=None,
                              skip_duplicate=True):
    """报工/批次路径的成品入库（不依赖 Workpiece）。

    与 inbound_workpiece 等价，但入口是生产订单 / 生产批次 / 批次实例：/my_tasks 报工路径
    没有工件，末道工序完成后用本函数把产出计入正品库（FinishedProduct.stock_kind='fg'）。

    - 产出标识 product_number：显式 > 实例 product_code > 订单号；
    - 数量 quantity：显式 > 1（实例按单件）> 订单剩余待产数量 > 1；
    - 门禁：先过 qc_gate_allows_output，质检不合格 / 未出结果 / 有未完成质检任务 /
      有未闭环不合格记录一律不入正品库，返回 (None, 原因)；
    - 末道校验：传了 process_id 时要求它是该产品工艺路线的末道工序，否则拒绝入库；
    - 幂等：同一 product_number 已在正品库时不重复建行（skip_duplicate=False 关闭）；
    - 履历：关联工件按既有 log_event 写法补 'inbound' 事件并置为 fg；无工件时不写工件履历
      （WorkpieceEvent.workpiece_id 非空，报工路径本就无工件可写）。

    不提交也不回滚事务：与 mes_service 既有约定一致（ensure_workpiece / inbound_workpiece /
    dispose_nonconformity 同样只管写），由调用方（路由层）commit，异常时 rollback 并记日志。
    返回 (finished_product, message)：入库成功为 (fp, None)；被门禁或校验拒绝为 (None, 原因)；
    已入库为 (已有行, 说明)。
    """
    item = batch_item
    if item is None:
        item = task_batch_item(task)
    if batch is None and item is not None:
        batch = item.batch
    if batch is None and task is not None and getattr(task, 'production_batch_id', None):
        batch = ProductionBatch.query.get(task.production_batch_id)
    if production_order is None and batch is not None:
        production_order = batch.production_order
    if production_order is None and item is None:
        return None, '缺少生产订单/批次/实例，无法定位报工产出'

    if product is None and production_order is not None:
        product = production_order.product

    label = (item.product_code if item is not None and item.product_code
             else (f'批次 {batch.batch_number}' if batch is not None and batch.batch_number
                   else (f'订单 {production_order.order_number}' if production_order is not None else '未知产出')))

    if process_id is not None:
        product_id = getattr(product, 'id', None) or getattr(production_order, 'product_id', None)
        if not is_last_process(product_id, process_id):
            reason = '当前工序不是末道工序，产出不入正品库'
            current_app.logger.warning(f'报工入库被拒（{label}）：{reason}')
            return None, reason

    if workpieces is None:
        workpieces = task_workpieces(task) if task is not None else []
    if not workpieces and item is not None:
        workpieces = batch_item_workpieces(item)

    allowed, reason = qc_gate_allows_output(batch_item=item, workpieces=workpieces)
    if not allowed:
        current_app.logger.warning(f'报工入库被门禁拒绝（{label}）：{reason}')
        return None, reason

    code = (product_number or '').strip() if product_number else ''
    if not code:
        if item is not None and item.product_code:
            code = item.product_code
        elif production_order is not None:
            code = production_order.order_number
    if not code:
        return None, '缺少产出编号，无法入库'

    if quantity is None:
        remaining = production_order.remaining_quantity if production_order is not None else 0
        quantity = 1 if item is not None else (remaining if remaining and remaining > 0 else 1)
    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        return None, '入库数量无效'
    if quantity <= 0:
        return None, '入库数量必须大于 0'

    if skip_duplicate:
        existing = FinishedProduct.query.filter_by(
            product_number=code, stock_kind='fg', status='in_stock'
        ).first()
        if existing is not None:
            message = f'产出 {code} 已在正品库，未重复入库'
            current_app.logger.info(f'报工入库跳过（{label}）：{message}')
            return existing, message

    operator = operator_name(inspector_name)
    order_suffix = f'，订单 {production_order.order_number}' if production_order is not None else ''
    fp = FinishedProduct(
        product_number=code,
        production_date=production_date or date.today(),
        drawing_number=(getattr(product, 'drawing_number', '') or '-'),
        model=(getattr(product, 'model', '') or '-'),
        inspector=operator,
        quantity=quantity,
        status='in_stock',
        stock_kind='fg',
        product_id=(product.id if product is not None
                    else getattr(production_order, 'product_id', None)),
        notes=notes or f'报工路径末道入库：{label}{order_suffix}',
    )
    db.session.add(fp)
    db.session.flush()

    if item is not None:
        if (item.status or '') != 'completed':
            item.status = 'completed'
        if not item.production_date:
            item.production_date = fp.production_date
        if not item.inspector:
            item.inspector = operator
        if item.completed_at is None:
            item.completed_at = datetime.now()

    for wp in workpieces or ():
        wp.status = 'fg'
        log_event(
            wp, 'inbound',
            task_id=(getattr(task, 'id', None) if task is not None else None),
            payload={
                'stock_kind': 'fg',
                'source': 'report',
                'finished_product_id': fp.id,
                'batch_item_id': item.id if item is not None else None,
                'production_order_id': production_order.id if production_order is not None else None,
            },
        )
    return fp, None


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
        # 来料检结论落到到货单：pass→可入库；fail→生成未闭环不合格单并拒收待处置
        apply_goods_receipt_result(task, record)
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
            target_type='workpiece',
            target_id=workpiece.id,
        )
        db.session.add(nc)
        inbound_workpiece(workpiece, stock_kind='failed',
                          inspector_name=getattr(current_user, 'username', '系统'))


# ---------------------------------------------------------------- 来料检（goods_receipt）

INCOMING_NC_ACTIONS = ('return', 'accept', 'scrap')
INCOMING_NC_LABELS = {'return': '退货', 'accept': '让步接收', 'scrap': '报废'}


def nonconformity_target(nc):
    """不合格单的处置对象口径：(target_type, target_id)。

    优先读 P1-3 新增的显式列；老数据（两列为 NULL）按工件 / 质检记录所属任务回退。
    返回值形如 ('workpiece', 12) / ('goods_receipt', 3) / (None, None)。
    """
    if nc is None:
        return None, None
    if nc.target_type:
        return nc.target_type, nc.target_id
    if nc.workpiece_id:
        return 'workpiece', nc.workpiece_id
    record = nc.record
    task = getattr(record, 'task', None) if record is not None else None
    if task is not None and task.target_type:
        return task.target_type, task.target_id
    return None, None


def putaway_goods_receipt(receipt):
    """检验通过或让步接收后把到货单写入原材料/易耗品库存。

    原 app/main/purchase.py::_putaway_receipt 上移到领域服务（库存写入归服务层，
    避免蓝图之间互相 import 私有函数），逻辑逐字保留：易耗品进 Consumable，
    其余进 RawMaterial，最后把到货单置 putaway。
    """
    po = receipt.purchase_order
    for line in receipt.items.all():
        poi = line.po_item
        if not poi:
            continue
        if poi.material_type == 'consumable':
            cat = ConsumableCategory.query.first()
            if cat is None:
                cat = ConsumableCategory(name='采购入库', code='PO', created_by=operator_id())
                db.session.add(cat)
                db.session.flush()
            db.session.add(Consumable(
                supplier=po.supplier.name if po.supplier else '',
                category_id=cat.id,
                specification=poi.spec or '',
                supplier_number='-',
                internal_number=f'C{poi.id}-{receipt.id}',
                quantity=line.quantity,
                unit=poi.unit or '件',
            ))
        else:
            cat = RawMaterialCategory.query.first()
            if cat is None:
                cat = RawMaterialCategory(name='采购入库', code='PO', created_by=operator_id())
                db.session.add(cat)
                db.session.flush()
            db.session.add(RawMaterial(
                supplier=po.supplier.name if po.supplier else '',
                category_id=cat.id,
                internal_number=f'R{poi.id}-{receipt.id}-{int(line.quantity)}',
                quantity=line.quantity,
                storage_date=date.today(),
                melt_number='-',
                supplier_number='-',
            ))
    receipt.status = 'putaway'
    return receipt


def apply_goods_receipt_result(task, record):
    """来料检结论落到到货单（与生产质检同口径）。

    - pass：到货单转 accepted，由调用方（quality.py）随后入库；
    - fail：生成未闭环 NonconformityRecord（target_type='goods_receipt'，
      target_id=到货单 id），到货单转 rejected，只有完成退货/让步/报废处置后状态才会再变。
    """
    receipt = GoodsReceipt.query.get(task.target_id)
    if receipt is None:
        return None
    if record.result == 'pass':
        receipt.status = 'accepted'
        return None
    if record.result != 'fail':
        return None
    nc = NonconformityRecord(
        record_id=record.id,
        type='return',  # 处置前登记的建议动作（退货），实际以处置动作为准
        handler_id=operator_id(default=default_inspector_id()),
        handling_date=date.today(),
        handling_result='待处置',
        notes='来料检不合格，等待退货/让步接收/报废处置',
        status='open',
        target_type='goods_receipt',
        target_id=receipt.id,
        workpiece_id=None,
    )
    db.session.add(nc)
    db.session.flush()
    receipt.status = 'rejected'
    current_app.logger.warning(
        f'来料检不合格：到货单 {receipt.receipt_no} 转拒收待处置，不合格单 #{nc.id} 待处置'
    )
    return nc


def _log_incoming_disposal(nc, action, status):
    db.session.add(AuditLog(
        user_id=operator_id(),
        action='来料检不合格处置',
        details=(f'不合格单#{nc.id}（来料检/到货单{nc.target_id}）处置：'
                 f'{INCOMING_NC_LABELS.get(action, action)}，状态：{status}'),
        can_rollback=False,
        target_model='NonconformityRecord',
        target_id=nc.id,
        new_data={'action': action, 'status': status,
                  'target_type': nc.target_type, 'target_id': nc.target_id},
    ))


def dispose_incoming_nonconformity(nc, action, *, notes='', scrap_cost=0):
    """来料检不合格处置：return（退货）/ accept（让步接收）/ scrap（报废）。

    - 处置动作写在 NonconformityRecord.type，处置对象口径由 target_type/target_id 明确；
    - 让步接收沿用生产让步的角色门槛（SystemConfig quality.concession_approver_roles），
      无权限时单据转 pending_approval 且不动库存、不动到货单状态；
    - 退货 / 报废都不产生库存入库，到货单分别置 returned / scrapped；
    - 写 AuditLog（can_rollback=False，不进入审计回滚的反射机制）。
    返回 nc。
    """
    if nc is None:
        raise ValueError('不合格单不存在')
    if action not in INCOMING_NC_ACTIONS:
        raise ValueError('来料检不合格仅支持退货/让步接收/报废处置')
    target_type, target_id = nonconformity_target(nc)
    if target_type != 'goods_receipt':
        raise ValueError('该不合格单不是来料检处置对象')
    receipt = GoodsReceipt.query.get(target_id) if target_id else None

    nc.type = action
    nc.handling_result = notes or f'{INCOMING_NC_LABELS[action]}'
    nc.handling_date = date.today()
    if notes:
        nc.notes = notes

    if action == 'accept':
        roles = SystemConfig.get('quality.concession_approver_roles', ['admin', 'manager']) or ['admin', 'manager']
        if current_role() not in roles:
            nc.status = 'pending_approval'
            _log_incoming_disposal(nc, action, nc.status)
            return nc
        nc.status = 'approved'
        nc.approver_id = operator_id()
        nc.approved_at = datetime.utcnow()
        if receipt is not None:
            receipt.status = 'accepted'
            putaway_goods_receipt(receipt)
    elif action == 'return':
        nc.status = 'done'
        if receipt is not None:
            receipt.status = 'returned'
    else:  # scrap
        nc.scrap_cost = scrap_cost or 0
        nc.status = 'done'
        if receipt is not None:
            receipt.status = 'scrapped'

    _log_incoming_disposal(nc, action, nc.status)
    return nc


def apply_lot_item_result(workpiece, record):
    log_event(workpiece, 'inspection', inspection_record_id=record.id,
              payload={'result': record.result, 'source': 'heat_lot'})
    if record.result == 'pass':
        workpiece.status = 'calcined'
    elif record.result == 'fail':
        workpiece.status = 'failed'


def dispose_nonconformity(nc, action, *, notes='', scrap_cost=0, rework_process_id=None,
                          employee_id=None, target_date=None):
    """不合格处置总入口，按处置对象口径分流。

    生产质检（target_type='workpiece' 或老数据带 workpiece_id）：action = rework / scrap / accept；
    来料检（target_type='goods_receipt'）：action = return（退货）/ accept（让步接收）/ scrap（报废），
    见 dispose_incoming_nonconformity。
    """
    target_type, _target_id = nonconformity_target(nc)
    if target_type == 'goods_receipt':
        return dispose_incoming_nonconformity(nc, action, notes=notes, scrap_cost=scrap_cost)

    nc.type = action
    nc.handling_result = notes or nc.handling_result
    nc.notes = notes or nc.notes
    nc.handling_date = date.today()
    wp = Workpiece.query.get(nc.workpiece_id) if nc.workpiece_id else None
    # 顺手把口径列补齐（老数据两列为 NULL），便于后续按 target 查询/区分
    if not nc.target_type and nc.workpiece_id:
        nc.target_type = 'workpiece'
        nc.target_id = nc.workpiece_id

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


def order_id_from_workpieces(workpiece_ids):
    """从工件的批次实例反推生产订单；多订单或定位不到时返回 None（宁可不回写，也不猜归属）。"""
    order_ids = set()
    for wp_id in workpiece_ids or ():
        wp = Workpiece.query.get(wp_id)
        if wp is None or not wp.batch_item_id:
            continue
        item = ProductionBatchItem.query.get(wp.batch_item_id)
        batch = item.batch if item is not None else None
        if batch is not None and batch.production_order_id:
            order_ids.add(batch.production_order_id)
    if len(order_ids) == 1:
        return order_ids.pop()
    return None


def consume_bom_for_assembly(product, quantity=1, scanned_workpiece_ids=None, production_order_id=None):
    """组装：自制件扫码出库，标准件按数量扣。

    消耗回写 MaterialAllocation 时按 production_order_id + material_type + material_id 精确定位，
    不再取「最新一条」；未显式给出订单时尝试从扫码工件反推，推不出来就不回写——宁可漏记，
    也不把消耗记到别的订单头上。
    """
    scanned = set(scanned_workpiece_ids or [])
    order_id = production_order_id or order_id_from_workpieces(scanned)
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
                    if order_id:
                        alloc = write_consumed_allocation(order_id, 'raw', mat.id, need)
                        if alloc is None:
                            current_app.logger.warning(
                                f'组装扣料未回写分配行：订单 {order_id} 原材料 {mat.id} 无计划行'
                            )
                    else:
                        current_app.logger.warning(
                            f'组装扣料未回写分配行：无法定位生产订单（原材料 {mat.id}），'
                            f'不按「最新一条」猜归属'
                        )
            else:
                from app.models import Consumable
                item = Consumable.query.get(bom.material_id)
                if not item or item.quantity < need:
                    shortages.append({'bom_id': bom.id, 'name': bom.material_name, 'qty': need})
                else:
                    item.quantity -= need
                    consumed.append({'consumable_id': item.id, 'qty': need})
    return consumed, shortages


def resolve_task_production_order_id(task):
    """报工任务所属生产订单：批次任务（production_batch_id）与实例任务（batch_item_id）两种挂接都能定位。"""
    if task is None:
        return None
    batch_id = getattr(task, 'production_batch_id', None)
    if batch_id:
        batch = ProductionBatch.query.get(batch_id)
        if batch is not None:
            return batch.production_order_id
    item = task_batch_item(task)
    batch = item.batch if item is not None else None
    if batch is not None:
        return batch.production_order_id
    return None


def write_consumed_allocation(production_order_id, material_type, material_id, qty):
    """按生产订单 + 物料精确定位分配行并累加已消耗数量。

    定位不到就不臆造分配行（MaterialAllocation.required_quantity 非空，凭空建行等于编造计划），
    返回 None；调用方按返回值决定是否提示。
    """
    if not production_order_id:
        current_app.logger.warning(
            f'已消耗数量未回写：缺少生产订单（{material_type}/{material_id} × {qty}）'
        )
        return None
    alloc = MaterialAllocation.query.filter_by(
        production_order_id=production_order_id,
        material_type=material_type,
        material_id=material_id,
    ).order_by(MaterialAllocation.id.asc()).first()
    if alloc:
        alloc.consumed_quantity = (alloc.consumed_quantity or 0) + qty
        if alloc.allocated_quantity is None or alloc.allocated_quantity == 0:
            alloc.allocated_quantity = qty
    return alloc


def write_task_consumed_allocation(task, material_type, material_id, qty):
    """报工扣料回写：生产订单由任务推导，定位口径与 write_consumed_allocation 完全一致。"""
    order_id = resolve_task_production_order_id(task)
    if not order_id:
        current_app.logger.warning(
            f'报工扣料未回写：任务 {getattr(task, "id", None)} 未挂生产批次/批次实例'
        )
        return None
    return write_consumed_allocation(order_id, material_type, material_id, qty)


def record_task_material_consumption(task, materials, material_type='raw'):
    """报工扣料回写入口：按任务所属生产订单归集 MaterialAllocation.consumed_quantity。

    materials 与 /tasks/<id>/update_status 的入参同形：[{'raw_material_id': 1, 'quantity': 2.0}, ...]，
    也接受 [{'material_type': 'raw', 'material_id': 1, 'quantity': 2.0}, ...]。
    数量非正、字段缺失的条目只跳过并记日志，不阻断整批报工。

    返回 {'production_order_id': int|None, 'written': [...], 'missing': [...], 'invalid': [...],
    'message': str|None}；missing 表示该订单下没有对应分配行（物料账没有计划行，不臆造）。
    """
    result = {'production_order_id': resolve_task_production_order_id(task),
              'written': [], 'missing': [], 'invalid': [], 'message': None}
    if result['production_order_id'] is None:
        result['message'] = '任务未挂生产批次/批次实例，无法归集物料消耗'
        current_app.logger.warning(
            f'报工扣料归集跳过：任务 {getattr(task, "id", None)} 未挂生产批次/批次实例'
        )
        return result

    for material in materials or ():
        if not isinstance(material, dict):
            result['invalid'].append(material)
            continue
        if 'material_id' in material:
            mtype = (material.get('material_type') or material_type or 'raw')
            mid = material.get('material_id')
        else:
            mtype = material_type or 'raw'
            mid = material.get('raw_material_id')
        try:
            mid = int(mid)
            qty = float(material.get('quantity'))
        except (TypeError, ValueError):
            result['invalid'].append(material)
            continue
        if qty <= 0:
            result['invalid'].append(material)
            continue
        alloc = write_consumed_allocation(result['production_order_id'], mtype, mid, qty)
        if alloc is None:
            result['missing'].append({'material_type': mtype, 'material_id': mid, 'quantity': qty})
        else:
            result['written'].append({
                'allocation_id': alloc.id,
                'material_type': mtype,
                'material_id': mid,
                'quantity': qty,
                'consumed_quantity': alloc.consumed_quantity,
            })
    return result


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


# ---------------------------------------------------------------- 发货出库（销售订单 → 发货单）
# 2026-09-18 用户定口径：
#   1) 「一条成品行 = 一个发货单位」改为按需拆分成品行；
#   2) 整单模式与按行模式统一校验「本次发货数量 = min(订单行剩余待发量, 该成品可用在库件数)」；
#   3) 完成判定按订单行逐行累计（见 app/main/shipping.py::confirm_shipment）。

SHIPPABLE_STOCK_KINDS = ('fg', 'wip_part')
# 占用订单行额度/成品行的发货单状态：draft 未出库也算占用，避免两张草稿单重复计入同一成品行
SHIPMENT_OPEN_STATUSES = ('draft', 'shipped', 'signed')
# 已实际出库的发货单状态：只有这些才计入「已发数量」
SHIPMENT_SHIPPED_STATUSES = ('shipped', 'signed')


def _to_quantity(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def shipment_product_matches_line(fp, line):
    """成品是否属于该订单行：同产品 id，或图号一致（与发货详情页列示口径相同）。"""
    if fp is None or line is None:
        return False
    if line.product_id and fp.product_id == line.product_id:
        return True
    drawing = getattr(line.product, 'drawing_number', None) or ''
    return bool(drawing) and fp.drawing_number == drawing


def shipment_allocated_product_ids():
    """已被未取消发货单占用的成品行 id（draft 草稿单占用也算，防止重复计入两张草稿单）。"""
    rows = db.session.query(ShipmentItem.finished_product_id).join(
        Shipment, ShipmentItem.shipment_id == Shipment.id
    ).filter(
        ShipmentItem.finished_product_id.isnot(None),
        Shipment.status.in_(SHIPMENT_OPEN_STATUSES),
    ).all()
    return {row[0] for row in rows}


def shipment_order_line_allocated_quantity(line_id, statuses=SHIPMENT_OPEN_STATUSES):
    """该订单行已登记到发货单的件数（默认含 draft 草稿占用）。"""
    if not line_id:
        return 0.0
    total = db.session.query(db.func.coalesce(db.func.sum(ShipmentItem.quantity), 0.0)).join(
        Shipment, ShipmentItem.shipment_id == Shipment.id
    ).filter(
        ShipmentItem.sales_order_item_id == line_id,
        Shipment.status.in_(tuple(statuses)),
    ).scalar()
    return _to_quantity(total)


def shipment_order_line_shipped_quantity(line_id):
    """该订单行已实际出库件数（只算已出库/已签收的发货单，用于完成判定）。"""
    return shipment_order_line_allocated_quantity(line_id, statuses=SHIPMENT_SHIPPED_STATUSES)


def shipment_order_line_remaining_quantity(line):
    """订单行剩余待发量 = 订购数量 - 已登记件数（含 draft 草稿占用），不小于 0。"""
    if line is None:
        return 0.0
    return max(0.0, _to_quantity(line.quantity) - shipment_order_line_allocated_quantity(line.id))


def shipment_candidate_stock(line):
    """订单行当前可发的在库成品行（按 id 升序）。

    口径：in_stock + stock_kind in (fg, wip_part) + 成品与订单行同产品/图号；
    并剔除已被未取消发货单占用的行，使第二张草稿单「取不到该行」。
    """
    if line is None:
        return []
    query = FinishedProduct.query.filter(
        FinishedProduct.status == 'in_stock',
        FinishedProduct.stock_kind.in_(SHIPPABLE_STOCK_KINDS),
        # 已存档的成品行不再参与配货；NULL 视为未存档，与下方登记判断（只拦显式 True）
        # 保持同一口径，避免出现「候选里看不到、强行指定 id 却能发」的两套语义
        db.or_(FinishedProduct.is_archived.is_(False),
               FinishedProduct.is_archived.is_(None)),
    )
    if line.product_id:
        drawing = getattr(line.product, 'drawing_number', None) or ''
        query = query.filter(db.or_(
            FinishedProduct.product_id == line.product_id,
            FinishedProduct.drawing_number == drawing,
        ))
    taken = shipment_allocated_product_ids()
    return [fp for fp in query.order_by(FinishedProduct.id.asc()).all()
            if _to_quantity(fp.quantity) > 0 and fp.id not in taken]


def shipment_take_finished_product(fp, quantity):
    """按需拆分成品行，返回实际用于发货的成品行（不提交事务，调用方负责 commit/rollback）。

    - quantity == fp.quantity：整行发货，返回原行；
    - quantity < fp.quantity 且未绑定工件：原行 quantity -= quantity 留在库，
      另建一条 quantity = quantity 的成品行（新流水号）作为实际发货对象；
    - 绑定工件（1 件 1 行，不可拆）：只允许整行发，数量不等时抛 ValueError。
    数量必须是正整数件：小数（如 1.5）会拆出小数库存行，一律抛 ValueError。
    """
    if fp is None:
        raise ValueError('成品行不存在')
    available = _to_quantity(fp.quantity)
    take = _to_quantity(quantity)
    if take <= 0:
        raise ValueError('发货数量必须大于 0')
    if abs(take - round(take)) > 1e-9:
        raise ValueError('发货数量必须是整数件')
    if take > available:
        raise ValueError(f'库存 {fp.serial_number} 只有 {int(available)} 件，不能发 {int(take)} 件')
    if abs(take - available) < 1e-9:
        return fp
    if fp.workpiece_id:
        code = getattr(fp.workpiece, 'code', None) or fp.workpiece_id
        raise ValueError(
            f'库存 {fp.serial_number} 已绑定工件 {code}，只能整行发 {int(available)} 件，'
            f'不能拆成 {int(take)} 件'
        )
    fp.quantity = available - take
    new_fp = FinishedProduct(
        serial_number=SerialNumber.get_next_number(),
        global_sn=SerialNumber.get_next_number(),
        product_number=fp.product_number,
        production_date=fp.production_date,
        drawing_number=fp.drawing_number,
        model=fp.model,
        inspector=fp.inspector,
        quantity=int(take),
        status='in_stock',
        stock_kind=fp.stock_kind,
        product_id=fp.product_id,
        notes=f'{fp.notes or ""}（由 {fp.serial_number} 按 {int(take)} 件拆分）',
        is_archived=fp.is_archived,
    )
    db.session.add(new_fp)
    db.session.flush()
    return new_fp


def shipment_register_finished_product(ship, line, *, finished_product, quantity=None):
    """整单/按行两条路径的**统一**登记入口：把成品（按需拆分）登记到发货明细。

    校验：本次发货数量 = min(订单行剩余待发量, 该成品可用在库件数)，且不得超过订单行剩余待发量；
    成品行已被任何未取消发货单占用（含本单）时拒绝；绑定工件的成品行只允许整行发。
    返回 (ShipmentItem, None) 或 (None, 可读原因)。不提交事务。
    """
    if ship is None or line is None:
        return None, '缺少发货单或销售订单行'
    if line.sales_order_id != ship.sales_order_id:
        return None, '所选订单行不属于本发货单的销售订单'
    if finished_product is None:
        return None, '请选择要发货的库存'
    if finished_product.status != 'in_stock':
        return None, f'库存 {finished_product.serial_number} 不在库'
    if finished_product.stock_kind not in SHIPPABLE_STOCK_KINDS:
        return None, f'库存 {finished_product.serial_number} 不是可发货的成品/自制件'
    if _to_quantity(finished_product.quantity) <= 0:
        return None, f'库存 {finished_product.serial_number} 没有可发件数'
    if finished_product.is_archived:
        # 已存档视为不再对外发货（NULL 按未存档处理，只拦显式 True）
        return None, f'库存 {finished_product.serial_number} 已存档，不能发货'
    if finished_product.id in shipment_allocated_product_ids():
        return None, f'库存 {finished_product.serial_number} 已加入发货单，不能重复发货'
    if not shipment_product_matches_line(finished_product, line):
        return None, f'库存 {finished_product.serial_number} 与所选订单行的产品不一致'

    remaining = shipment_order_line_remaining_quantity(line)
    if remaining <= 0:
        return None, (f'订单行已发满（订购 {int(_to_quantity(line.quantity))} 件），'
                      f'不能超过剩余待发量')
    requested = None if quantity is None else _to_quantity(quantity)
    if requested is not None and requested <= 0:
        return None, '发货数量必须大于 0'
    # 成品按整件发货：1.5 件会拆出小数库存行，直接拒绝（整单路径不传数量，不受影响）
    if requested is not None and abs(requested - round(requested)) > 1e-9:
        return None, '发货数量必须是整数件'

    row_qty = _to_quantity(finished_product.quantity)
    if finished_product.workpiece_id:
        # 绑定工件：1 件 1 行，不可拆；数量不等时拒绝，绝不静默按整行发
        target = row_qty if requested is None else requested
        if abs(target - row_qty) >= 1e-9:
            return None, (f'库存 {finished_product.serial_number} 已绑定工件，只能整行发 '
                          f'{int(row_qty)} 件，不能发 {int(target)} 件')
        if row_qty > remaining:
            return None, (f'库存 {finished_product.serial_number} 已绑定工件需整行发 '
                          f'{int(row_qty)} 件，超过订单行剩余待发量 {int(remaining)} 件')
    else:
        target = min(remaining, row_qty) if requested is None else min(requested, remaining, row_qty)
    if target <= 0:
        return None, '可发数量为 0，无法发货'

    try:
        shipped_fp = shipment_take_finished_product(finished_product, target)
    except ValueError as exc:
        return None, str(exc)

    item = ShipmentItem(
        shipment_id=ship.id,
        sales_order_item_id=line.id,
        finished_product_id=shipped_fp.id,
        workpiece_id=shipped_fp.workpiece_id,
        quantity=int(target),
    )
    db.session.add(item)
    db.session.flush()
    return item, None


def shipment_fill_order_line(ship, line):
    """整单模式：把订单行剩余待发量按**件数**配到在库成品上（按需拆分）。

    返回 (本次登记件数, 提示列表)；库存不足以发满时只登记能发的部分并给出提示，
    绝不按成品行条数超发。
    """
    remaining = shipment_order_line_remaining_quantity(line)
    messages = []
    shipped = 0.0
    if remaining <= 0:
        if _to_quantity(line.quantity) > 0:
            messages.append(f'订单行（订购 {int(_to_quantity(line.quantity))} 件）已发满，不再配货')
        return shipped, messages
    for fp in shipment_candidate_stock(line):
        if remaining <= 0:
            break
        row_qty = _to_quantity(fp.quantity)
        if fp.workpiece_id and row_qty > remaining + 1e-9:
            messages.append(f'库存 {fp.serial_number} 绑定工件需整行发 {int(row_qty)} 件，'
                            f'超过剩余待发量 {int(remaining)} 件，已跳过')
            continue
        item, error = shipment_register_finished_product(ship, line, finished_product=fp)
        if item is None:
            messages.append(error)
            continue
        shipped += _to_quantity(item.quantity)
        remaining -= _to_quantity(item.quantity)
    return shipped, messages


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
