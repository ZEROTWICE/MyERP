"""道岔产销领域服务：工件履历、质检门禁、完工入库、组装扣料、报工扣料归集、来料检处置。"""
from datetime import date, datetime

from flask import current_app
from flask_login import current_user

from app import db
from app.models import (
    AuditLog, Equipment, EquipmentCapability, FinishedProduct, GoodsReceipt, InspectionTemplate,
    InspectionTask, InspectionRecord, MaterialAllocation, NonconformityRecord, ProcessPrice,
    Product, ProductBOM, ProductProcess, ProductionBatch, ProductionBatchItem, ProductionRecord,
    ProductionRecordMaterial, RawMaterial, RawMaterialCategory, SerialNumber, Shipment,
    ShipmentItem, SystemConfig, Consumable, ConsumableCategory, TaskAssignment, TaskWorkpiece,
    User, WorkCenterEquipment, Workpiece, WorkpieceEvent,
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


# B14-07（方案A · 拍板项 4）：模板类型优先级链，`pick_template` 的唯一口径来源。
# `goods_receipt` 有**自己的**模板类型（`type='goods_receipt'`，由初始化 seed 下发），
# 必须优先命中；只有确实没有来料检模板时，才退回生产记录/物料/成品模板。
# 工件/炉次沿用既有回退口径（同一张表，首项即自身类型）。
_TEMPLATE_TYPE_CHAIN = {
    'goods_receipt': ('goods_receipt', 'production_record', 'material', 'product'),
    'workpiece': ('workpiece', 'production_record', 'material', 'product'),
    'heat_lot': ('heat_lot', 'production_record', 'material', 'product'),
}


def pick_template(target_type):
    """按类型取**启用**的质检模板；工件/炉次/来料检按优先级链回退。

    B14-07（方案A）：`goods_receipt` 优先命中 `type='goods_receipt'` 的模板，不再被旧兜底链
    一律绑成 `production_record` 模板 —— 否则质检确认口的类型严格相等校验
    （`app/main/quality.py`）会因「任务 type=goods_receipt、模板 type=production_record」
    而 400，形成"来料检任务永远确认不了"的死锁。

    链上确实一套可用模板都没有时返回 `None`（任务 `template_id` 留空，由检验员手选），
    **不**返回类型不符的模板。
    """
    for candidate in _TEMPLATE_TYPE_CHAIN.get(target_type, (target_type,)):
        template = InspectionTemplate.query.filter_by(type=candidate, is_active=True).first()
        if template is not None:
            return template
    return None


def create_inspection_task(target_type, target_id, notes=''):
    # 模板绑定口径统一由 pick_template 的类型优先级链决定（B14-07），此处不再另写回退分支
    template = pick_template(target_type)
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

    拒绝顺序（`07b` DEC-1 §1.4，**顺序本身是判据**：A2 拦得住、P1 放得行必须同时成立）：

      1. `quality_status ∈ {fail, failed, rejected}` ⇒ 拒（质检不合格）；
      2. `status == 'scrapped'` ⇒ 拒（报废终态，优先级高于 `quality_status`）；
      3. `quality_status ∈ {pending, pending_inspection}` **且确有在办单据** ⇒ 拒（原因含复位动作）；
      4. `record_ids` 存在在办质检任务 / 未闭环不合格记录 ⇒ 拒（本函数真正的「有单据」拒绝路径）；
      5. 工件维度未处置不合格 / 未完成质检 ⇒ 拒；
      6. 以上皆不命中 ⇒ **放行**。

    ⚠ 序 3 是 `07b` DEC-1 §1.4 的**改判点**：`pending` **不再**是无条件拒绝（那正是死锁形态，
    无自动复位路径 ⇒ 不可逆损失）。只有「确有在办单据」时才拒 —— 判定用的是与序 4 **同一套**
    `record_ids`（本函数既有口径，不新增列/不改关联约定）。

    返回 (allowed, message)。
    """
    records = []
    if production_record is not None:
        records.append(production_record)
    if batch_item is not None:
        records.extend(batch_item_production_records(batch_item))
    record_ids = [r.id for r in records if getattr(r, 'id', None)]

    pending_task = None
    open_nc = None
    if record_ids:
        pending_task = InspectionTask.query.filter(
            InspectionTask.target_type == 'production_record',
            InspectionTask.target_id.in_(record_ids),
            InspectionTask.status.in_(['pending', 'in_progress']),
        ).first()
        open_nc = NonconformityRecord.query.filter(
            NonconformityRecord.record_id.in_(record_ids),
            NonconformityRecord.status.in_(['open', 'pending_approval']),
        ).first()
    has_open_documents = pending_task is not None or open_nc is not None

    if batch_item is not None:
        code = batch_item.product_code or f'实例#{batch_item.id}'
        quality_status = (batch_item.quality_status or '').strip().lower()
        if quality_status in ('fail', 'failed', 'rejected'):
            return False, f'实例 {code} 质检不合格，不得入正品库'
        if (batch_item.status or '') == 'scrapped':
            return False, f'实例 {code} 已报废，不得入正品库'
        if quality_status in ('pending', 'pending_inspection') and has_open_documents:
            return False, (
                f'实例 {code} 质检未出结果（存在在办质检任务或未闭环不合格单），不得入正品库；'
                f'请在质检任务完成后重新报工，或由质检处置入口（/quality/nonconformities）完成处置'
            )

    if pending_task is not None:
        return False, '产出存在未完成的质检任务，不得入正品库；请先完成质检任务后重新报工'
    if open_nc is not None:
        return False, '产出存在未处置的不合格记录，不得入正品库；请先在质检处置入口完成处置'

    for wp in workpieces or ():
        if workpiece_blocked(wp):
            return False, f'{wp.code}: 存在未处置的不合格或已报废'
        pending = InspectionTask.query.filter_by(
            target_type='workpiece', target_id=wp.id
        ).filter(InspectionTask.status.in_(['pending', 'in_progress'])).first()
        if pending is not None:
            return False, f'{wp.code}: 存在未完成的质检任务'
    return True, None


def inbound_workpiece(workpiece, stock_kind='fg', inspector_name='系统', product=None, quantity=1):
    """末道通过后入库。stock_kind: fg / wip_part / failed / scrap。

    `quantity`：入库件数。默认 1（工件是单件身份，`models.py` 的 `Workpiece` 无数量列）；
    报废处置时按**本次报废件数**（`07b` DEC-2 §2.4「同步」行：`mes_service.py:225` 原先写死 1）。
    """
    product = product or (Product.query.get(workpiece.product_id) if workpiece.product_id else None)
    status_map = {
        'fg': 'in_stock',
        'wip_part': 'in_stock',
        'failed': 'in_stock',
        'scrap': 'scrapped',
    }
    try:
        inbox_quantity = float(quantity)
    except (TypeError, ValueError):
        inbox_quantity = 1.0
    if inbox_quantity <= 0:
        inbox_quantity = 1.0
    fp = FinishedProduct(
        product_number=workpiece.code,
        production_date=date.today(),
        drawing_number=(product.drawing_number if product else '') or '-',
        model=(product.model if product else '') or '-',
        inspector=inspector_name or '系统',
        quantity=inbox_quantity,
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


def inbound_production_scrap(*, nc=None, batch_item=None, production_record=None,
                             quantity=1, inspector_name=None, notes=''):
    """报工路径（无工件）报废的库存台账行 —— 补 P-09 缺口（沿用既有 `stock_kind='scrap'`）。

    为什么单开一支而不复用 `inbound_workpiece`：那条路径以 `Workpiece` 为身份载体
    （`product_number=workpiece.code`、`workpiece_id=workpiece.id`，再改 `workpiece.status`），
    而报工路径报废的 `NonconformityRecord.workpiece_id IS NULL`
    （`dispose_nonconformity` 的 `wp is None` 分支），原先只扣料 + 置实例状态、**零台账行**。

    归属解析逐级降级、不猜不抛错：`production_record`（缺省由 `nc` 反推）
    → `batch_item_for_production_record` → `batch_item.batch.production_order.product`。
    `notes` 回写不合格单 id，便于从台账行追溯处置单。

    ⚠ 不新建表/列/库位：只写 `finished_product` 既有列，`stock_kind` 沿用 `'scrap'`。
    """
    record = production_record
    if record is None and nc is not None:
        record = production_record_for_nonconformity(nc)
    item = batch_item
    if item is None and record is not None:
        item = batch_item_for_production_record(record)
    order = None
    if item is not None:
        batch = getattr(item, 'batch', None)
        order = getattr(batch, 'production_order', None) if batch is not None else None
    product = getattr(order, 'product', None) if order is not None else None

    try:
        inbox_quantity = float(quantity)
    except (TypeError, ValueError):
        inbox_quantity = 1.0
    if inbox_quantity <= 0:
        inbox_quantity = 1.0

    product_number = ''
    if item is not None and getattr(item, 'product_code', None):
        product_number = item.product_code
    elif order is not None and getattr(order, 'order_number', None):
        product_number = order.order_number
    elif product is not None and getattr(product, 'product_code', None):
        product_number = product.product_code
    nc_id = getattr(nc, 'id', None)
    if not product_number:
        product_number = f'报废单{nc_id}' if nc_id is not None else '报废处置'
        current_app.logger.warning(
            f'报工路径报废：不合格单 {nc_id} 定位不到批次实例/订单 ⇒ 台账行产品号退化为 '
            f'{product_number}（件数仍按 {inbox_quantity:g} 入账，不猜归属）')

    note_text = notes or (
        f'报工路径报废自动入账：不合格单 #{nc_id}，'
        f'实例 {getattr(item, "product_code", None) or "-"}，件数 {inbox_quantity:g}')
    if nc_id is not None and f'#{nc_id}' not in note_text:
        note_text = f'{note_text}；不合格单#{nc_id}'

    fp = FinishedProduct(
        product_number=product_number,
        production_date=date.today(),
        drawing_number=(product.drawing_number if product is not None else '') or '-',
        model=(product.model if product is not None else '') or '-',
        inspector=inspector_name or operator_name() or '系统',
        quantity=inbox_quantity,
        status='scrapped',
        stock_kind='scrap',
        workpiece_id=None,
        product_id=(product.id if product is not None else None),
        notes=note_text,
    )
    db.session.add(fp)
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


def production_records_of_batch_item(batch_item):
    """实例的产出记录集：**任务关联**（`global_sn`，报工链主判据）∪ `notes` 软关联（回退）。

    `07b` DEC-1 §1.7 的正更正：报工端点创建的 `ProductionRecord` **不写 notes**
    （`routes.py:3392-3398`）⇒ 只按 notes 反查会**静默定位失败**。本函数是**读口径**的统一入口；
    写点仍只有 `apply_inspection_result` 一处（§1.2 禁令 ②）。
    """
    if batch_item is None or batch_item.id is None:
        return []
    tasks = TaskAssignment.query.filter_by(batch_item_id=batch_item.id).all()
    sns = {t.global_sn for t in tasks if t.global_sn}
    out = []
    if sns:
        out.extend(ProductionRecord.query.filter(ProductionRecord.global_sn.in_(sns)).all())
    for rec in batch_item_production_records(batch_item):
        if all(getattr(rec, 'id', None) != getattr(r, 'id', None) for r in out):
            out.append(rec)
    return out


def batch_item_for_production_record(production_record):
    """产出 → 批次实例（`07b` DEC-1 §1.7 的**唯一**口径）。

    主判据：`ProductionRecord.global_sn == TaskAssignment.global_sn` → `TaskAssignment.batch_item_id`；
    回退：`ProductionRecord.notes` 内的 `{"batch_item_id": N}`（仅 `production_center.execute_operation`
    写入，属防御性兼容）。两条都未命中 ⇒ `None`（调用方只记 warning 并跳过回写，不抛错、不猜归属）。
    """
    if production_record is None or not production_record.global_sn:
        return None
    linked_task = TaskAssignment.query.filter_by(global_sn=production_record.global_sn).first()
    if linked_task is not None:
        item = task_batch_item(linked_task)
        if item is not None:
            return item
    notes = production_record.notes or ''
    if '"batch_item_id"' in notes:
        raw = notes.split('"batch_item_id"', 1)[1]
        raw = raw.split(':', 1)[1] if ':' in raw else ''
        digits = ''
        for ch in raw.strip().lstrip('"'):
            if ch.isdigit():
                digits += ch
            else:
                break
        if digits:
            return ProductionBatchItem.query.get(int(digits))
    return None


def batch_item_for_nonconformity(nc, workpiece=None):
    """不合格单 → 批次实例（自动复位/字段回写的作用域）。取不到返回 `None`（不猜归属）。"""
    if nc is None:
        return None
    target_type, target_id = nonconformity_target(nc)
    if target_type == 'production_record' and target_id:
        pr = ProductionRecord.query.get(target_id)
        if pr is not None:
            item = batch_item_for_production_record(pr)
            if item is not None:
                return item
    wp = workpiece
    if wp is None and nc.workpiece_id:
        wp = Workpiece.query.get(nc.workpiece_id)
    if wp is not None:
        if getattr(wp, 'batch_item_id', None):
            item = ProductionBatchItem.query.get(wp.batch_item_id)
            if item is not None:
                return item
        for link in TaskWorkpiece.query.filter_by(workpiece_id=wp.id).all():
            task = TaskAssignment.query.get(link.task_id) if link.task_id else None
            if task is not None and task.batch_item_id:
                item = ProductionBatchItem.query.get(task.batch_item_id)
                if item is not None:
                    return item
    return None


def _latest_record(records):
    return max(records, key=lambda r: (r.date or date.min, r.id or 0)) if records else None


def production_record_for_nonconformity(nc, workpiece=None):
    """不合格单的**来源生产记录**（DEC-2 §2.3 返工件数 / §2.4 报废扣料的取值载体）。

    顺序：① 质检记录本身挂在产出上；② 工件所属实例的报工链（任务 `global_sn`）最新一条；
    ③ 工件的任务-工件链接反查（无 `batch_item_id` 时）；④ 取不到 ⇒ `None`。
    """
    if nc is None:
        return None
    record = getattr(nc, 'record', None)
    if record is None and nc.record_id:
        record = InspectionRecord.query.get(nc.record_id)
    task = getattr(record, 'task', None) if record is not None else None
    if task is not None and (task.target_type or '') == 'production_record' and task.target_id:
        pr = ProductionRecord.query.get(task.target_id)
        if pr is not None:
            return pr
    target_type, target_id = nonconformity_target(nc)
    if target_type == 'production_record' and target_id:
        pr = ProductionRecord.query.get(target_id)
        if pr is not None:
            return pr
    wp = workpiece
    if wp is None and nc.workpiece_id:
        wp = Workpiece.query.get(nc.workpiece_id)
    item = None
    if wp is not None and getattr(wp, 'batch_item_id', None):
        item = ProductionBatchItem.query.get(wp.batch_item_id)
    if item is None:
        item = batch_item_for_nonconformity(nc, workpiece=wp)
    if item is not None:
        pr = _latest_record(production_records_of_batch_item(item))
        if pr is not None:
            return pr
    if wp is not None:
        task_ids = [l.task_id for l in TaskWorkpiece.query.filter_by(workpiece_id=wp.id).all()
                    if l.task_id]
        sns = {t.global_sn for t in TaskAssignment.query.filter(
            TaskAssignment.id.in_(task_ids)).all() if t.global_sn} if task_ids else set()
        if sns:
            return _latest_record(ProductionRecord.query.filter(
                ProductionRecord.global_sn.in_(sns)).all())
    return None


def recompute_production_quality_status(batch_item, production_record=None):
    """按 `07b` DEC-1 §1.2 四值语义**复算并写** `quality_status`；返回写入值（无结论可判 ⇒ `None`）。

    - `fail`   ：存在 fail 结论且其不合格单**未闭环**；
    - `pending`：存在在办质检任务 / 未闭环不合格单；
    - `pass`   ：无在办、无未闭环，且**至少有一条结论**（处置闭环后的复位即走这里）；
    - 其余（无结论/无任务/无单据）⇒ **不动字段**（保持 `NULL`；RC-4 / AC-18-NEG）。
    """
    if batch_item is None:
        return None
    records = production_records_of_batch_item(batch_item)
    if production_record is not None and all(
            getattr(production_record, 'id', None) != getattr(r, 'id', None) for r in records):
        records.append(production_record)
    record_ids = [r.id for r in records if getattr(r, 'id', None)]
    tasks = []
    if record_ids:
        tasks = InspectionTask.query.filter(
            InspectionTask.target_type == 'production_record',
            InspectionTask.target_id.in_(record_ids),
        ).all()
    task_ids = [t.id for t in tasks if t.id]
    conclusions = []
    if task_ids:
        conclusions = InspectionRecord.query.filter(InspectionRecord.task_id.in_(task_ids)).all()
    conclusion_ids = [c.id for c in conclusions if c.id]
    open_nc = None
    if conclusion_ids:
        open_nc = NonconformityRecord.query.filter(
            NonconformityRecord.record_id.in_(conclusion_ids),
            NonconformityRecord.status.in_(('open', 'pending_approval')),
        ).first()
    in_process = any((t.status or '') in ('pending', 'in_progress') for t in tasks)
    has_fail = any((c.result or '').strip().lower() in ('fail', 'failed', 'rejected')
                   for c in conclusions)
    if has_fail and open_nc is not None:
        value = 'fail'
    elif in_process or open_nc is not None:
        value = 'pending'
    elif conclusions:
        value = 'pass'
    else:
        return None
    if (batch_item.quality_status or '').strip().lower() != value:
        batch_item.quality_status = value
    return value


def apply_production_record_result(record, task):
    """P-02/P-03：产出（`production_record`）维度的质检结论落地。

    `07b` DEC-1 §1.5：定位产出 → fail 时建不合格单 → 复算并写 `quality_status`（含 pass 回写）。
    返回 `(production_record, batch_item, written_quality_status)`。
    """
    production_record = ProductionRecord.query.get(task.target_id) if task.target_id else None
    if production_record is None:
        current_app.logger.warning(
            f'质检结论落地跳过：生产记录 {task.target_id} 不存在（质检记录 {record.id}）')
        return None, None, None
    item = batch_item_for_production_record(production_record)
    if item is None:
        # RC-7：定位失败不得静默 ⇒ warning + 跳过回写（不抛错、不猜归属）
        current_app.logger.warning(
            f'质检结论落地：生产记录 {production_record.id}'
            f'（global_sn={production_record.global_sn}）定位不到批次实例，'
            f'跳过 quality_status 回写（DEC-1 §1.7：global_sn 链与 notes 反查均未命中）')
        return production_record, None, None
    result = (record.result or '').strip().lower()
    if result in ('fail', 'failed', 'rejected'):
        existing = NonconformityRecord.query.filter_by(record_id=record.id).first()
        if existing is None:
            db.session.add(NonconformityRecord(
                record_id=record.id,
                type='rework',
                handler_id=getattr(current_user, 'id', None) or default_inspector_id(),
                handling_date=date.today(),
                handling_result='待处置',
                notes='质检不合格，等待返工/报废/让步',
                status='open',
                workpiece_id=None,
                target_type='production_record',
                target_id=production_record.id,
            ))
            db.session.flush()
        else:
            current_app.logger.info(
                f'质检结论落地：质检记录 {record.id} 已有不合格单 {existing.id}，不重复建单')
    value = recompute_production_quality_status(item, production_record)
    current_app.logger.info(
        f'质检结论落地：生产记录 {production_record.id} → 实例 {item.id} quality_status={value}')
    return production_record, item, value


def reset_quality_status_after_disposal(nc):
    """P-07b（`07b` DEC-1 §1.5-4）：处置闭环（`done`/`approved`）后对该产出**复算**并写 `pass`。

    **必须是链路自动动作**，不得要求人工 PUT（`routes.py` 的人工通道只作纠正）。
    来料检路径由 `dispose_incoming_nonconformity` 独立闭环，不在本次修复面（`07b` §6）。
    """
    if nc is None or (nc.status or '') not in ('done', 'approved'):
        return None
    target_type, _target_id = nonconformity_target(nc)
    if target_type == 'goods_receipt':
        return None
    workpiece = Workpiece.query.get(nc.workpiece_id) if nc.workpiece_id else None
    item = batch_item_for_nonconformity(nc, workpiece=workpiece)
    if item is None:
        production_record = production_record_for_nonconformity(nc, workpiece=workpiece)
        if production_record is not None:
            item = batch_item_for_production_record(production_record)
    if item is None:
        current_app.logger.warning(
            f'不合格单 {nc.id} 已闭环（{nc.status}），但定位不到批次实例 ⇒ 跳过 quality_status 自动复位')
        return None
    value = recompute_production_quality_status(item)
    current_app.logger.info(
        f'不合格单 {nc.id} 闭环（{nc.status}）后复算：实例 {item.id} quality_status={value}')
    return value


def scrap_material_plan(nc, workpiece=None):
    """报废扣料清单（DEC-2 §2.4 取值链）：返回 `(production_record, [(raw_material_id, 单件量)])`。

    ① `ProductionRecordMaterial` **逐行各自扣自己的 `raw_material_id`**（同料多行则合并求和）；
    ② 无明细行时退回 `ProductionRecord.raw_material_quantity + raw_material_id`（视为单行消耗）；
    ③ 两条都取不到 ⇒ **空清单**（调用方按「不扣料 + 未扣减说明」处理，AC-29d，**不得默认减 1**）。
    """
    production_record = production_record_for_nonconformity(nc, workpiece=workpiece)
    plan = []
    if production_record is not None:
        rows = ProductionRecordMaterial.query.filter_by(
            production_record_id=production_record.id).all()
        merged = {}
        for row in rows:
            if not row.raw_material_id or not row.quantity:
                continue
            merged[row.raw_material_id] = merged.get(row.raw_material_id, 0.0) + float(row.quantity)
        plan = sorted(merged.items())
        if not plan and production_record.raw_material_id and production_record.raw_material_quantity:
            plan = [(production_record.raw_material_id, float(production_record.raw_material_quantity))]
    if not plan:
        hint = ''
        if workpiece is not None and getattr(workpiece, 'raw_material_id', None):
            hint = f'（仅有工件料号 {workpiece.raw_material_id}，无消耗量）'
        current_app.logger.warning(
            f'报废处置未扣减：未找到产出的消耗明细（不合格单 {nc.id if nc else None}，'
            f'生产记录 {getattr(production_record, "id", None)}）{hint}；按 AC-29d 不扣任何料')
    return production_record, plan


def deduct_scrap_materials(plan, pieces=1, nc=None):
    """按计划逐料扣减：`扣量 = 单件量 × 报废件数`；夹紧到 0 并记 warning（AC-29b）。

    返回 `[{raw_material_id, before, requested, after, clamped}]`。
    """
    try:
        pieces = float(pieces)
    except (TypeError, ValueError):
        pieces = 1.0
    if pieces <= 0:
        pieces = 1.0
    applied = []
    for material_id, per_piece in plan:
        material = RawMaterial.query.get(material_id)
        if material is None:
            current_app.logger.warning(
                f'报废扣料跳过：物料 {material_id} 不存在（不合格单 {nc.id if nc else None}）')
            continue
        before = float(material.quantity or 0.0)
        requested = float(per_piece) * pieces
        after = before - requested
        clamped = after < 0
        if clamped:
            after = 0.0
            current_app.logger.warning(
                f'报废扣料夹紧：物料 {material_id} 原量 {before}，请求扣减 {requested}，'
                f'夹紧后 {after}（不合格单 {nc.id if nc else None}，件数 {pieces}）')
        material.quantity = after
        applied.append({'raw_material_id': material_id, 'before': before,
                        'requested': requested, 'after': after, 'clamped': clamped})
    return applied


def apply_inspection_result(record):
    """质检提交后的门禁与不合格处置入口。

    `07b` DEC-1 §1.5：**自动写点唯一**（本函数）。`target_type='production_record'` 的产出维度
    结论落地见 `apply_production_record_result`（在下方早返回之前分派）。
    """
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
    elif task.target_type == 'production_record':
        # P-02/P-03：报工产出维度的结论落地（fail 建不合格单 + 复算 quality_status）。
        # 定位链路按 `07b` §1.7 更正后的口径（global_sn → 任务 → batch_item_id）。
        apply_production_record_result(record, task)
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


def _notify_concession_pending_approval(nc, *, action_label, roles, source_label):
    """B13-08：让步审批转 `pending_approval` 时给审批角色发一条通知。

    接线口径与 B13-06 一致（同一模式，不另起一套）：

    * **提交责任在调用方**：`NotificationService.create_notification` 自 B13-05 起只
      add/flush、不自提交；本函数所在业务路径的调用方都在自身事务边界内 commit
      （`app/main/stock.py` 生产处置入口、`app/main/purchase.py` 来料检处置入口），
      故本函数**不新增任何 commit**。
    * **幂等键**：`trigger_type` 取值 `'concession_approval'`（注册表键
      `CONCESSION_APPROVAL`）+ `related_model='NonconformityRecord'`
      + `related_id=nc.id`，复用 B13-07 的三键查询级去重 —— 同一不合格单重复转待审批
      只会有 1 条通知（永久去重、无时间窗，与 B13-06 已登记偏差同口径）。
    * **接收人**：按 `SystemConfig quality.concession_approver_roles` 逐角色解析
      （`role:<role>`），与审批门槛同一数据源；规则表（NotificationRule）当前 0 行，
      只靠 `_create_receivers_by_rules` 会静默地一个接收人都不建。
    * **不吞异常**：通知写失败即本次事务失败，由调用方 rollback 并回 500
      （不把已记录的处置谎报成功），与 B13-06 接线口径一致。
    * `trigger_type` 走中央注册表 `NotificationService.TRIGGER_TYPES['CONCESSION_APPROVAL']`
      （B13-08 收口时已补键），不再用字面量；键值仍是既有字符串口径
      `'concession_approval'`。
    """
    # 函数内导入：避免 mes_service 与 notification_service 之间出现模块级环形导入。
    from app.services.notification_service import NotificationService

    role_list = [r for r in (roles or []) if isinstance(r, str)] or ['admin']
    return NotificationService.create_notification(
        trigger_type=NotificationService.TRIGGER_TYPES['CONCESSION_APPROVAL'],
        title=f'让步审批待处理 - 不合格单#{nc.id}',
        content=(f'{source_label}处置（{action_label}）需让步审批：不合格单#{nc.id} 已转待审批，'
                 f'请审批角色（{"、".join(role_list)}）复核处理。'),
        notification_type='warning',
        priority='high',
        related_model='NonconformityRecord',
        related_id=nc.id,
        receivers=[f'role:{r}' for r in role_list],
        trigger_data={
            'nonconformity_id': nc.id,
            'action': nc.type,
            'action_label': action_label,
            'source': source_label,
            'roles': role_list,
            'target_type': nc.target_type,
            'target_id': nc.target_id,
            'operator_id': operator_id(),
        },
    )


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
            # B13-08 接线：本函数只 add/flush，提交在调用方
            # （app/main/purchase.py dispose_goods_receipt_nonconformity 的 commit）。
            _notify_concession_pending_approval(
                nc, action_label=INCOMING_NC_LABELS.get(action, action),
                roles=roles, source_label='来料检')
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


def normalize_pieces(value, field='quantity'):
    """件数入参归一：`None`/`''` ⇒ `1.0`；非正整数 ⇒ `ValueError`（走既有 400 通道）。"""
    if value is None or value == '':
        return 1.0
    try:
        pieces = int(value)
    except (TypeError, ValueError):
        raise ValueError(f'{field} 必须为正整数')
    if pieces <= 0:
        raise ValueError(f'{field} 必须为正整数')
    return float(pieces)


def rework_quantity_for(nc, workpiece, explicit=None, production_record=None):
    """返工件数（DEC-2 §2.3）：**显式入参 > 来源生产记录 `quantity` > 兜底 1（必须留痕）**。

    返回 `(件数, 留痕说明)`。禁令：不得**静默**写死 1（`07b` §2.3 / AC-30-c）。
    """
    if explicit is not None and explicit != '':
        try:
            quantity = int(explicit)
        except (TypeError, ValueError):
            raise ValueError('rework_quantity 必须为正整数')
        if quantity <= 0:
            raise ValueError('rework_quantity 必须为正整数')
        return quantity, ''
    if production_record is None:
        production_record = production_record_for_nonconformity(nc, workpiece=workpiece)
    if (production_record is not None and production_record.quantity
            and int(production_record.quantity) > 0):
        return int(production_record.quantity), (
            f'件数取来源生产记录#{production_record.id}（quantity={production_record.quantity}）')
    return 1, '件数取默认值1（未找到来源生产记录）'


def dispose_nonconformity(nc, action, *, notes='', scrap_cost=0, rework_process_id=None,
                          employee_id=None, target_date=None, rework_quantity=None,
                          scrap_quantity=None):
    """不合格处置总入口，按处置对象口径分流。

    生产质检（target_type='workpiece' 或 'production_record'）：action = rework / scrap / accept；
    来料检（target_type='goods_receipt'）：action = return（退货）/ accept（让步接收）/ scrap（报废），
    见 dispose_incoming_nonconformity。

    `rework_quantity` / `scrap_quantity`（DEC-2 §2.3 / §2.4，**两个独立入参，不得合并**，见 `16` §11）：
    显式给出时优先；缺省时返工件数走「来源生产记录 → 兜底 1（留痕）」、报废件数默认 1。
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
            # B13-08 接线：本函数只 add/flush，提交在调用方
            # （app/main/stock.py dispose_nonconformity_api 的 commit）。
            _notify_concession_pending_approval(
                nc, action_label='让步接收', roles=roles, source_label='生产质检')
            return nc
        nc.status = 'approved'
        nc.approver_id = current_user.id
        nc.approved_at = datetime.utcnow()
        if wp:
            wp.status = 'calcined' if wp.status == 'failed' else wp.status
            log_event(wp, 'concession', payload={'nc_id': nc.id})
        reset_quality_status_after_disposal(nc)
        return nc

    if action == 'rework':
        # B14-03：返工**必须**显式给出工序与员工，缺任一项即拒绝（`ValueError` ⇒ 路由层 400）。
        # 旧实现缺参时静默反推：工序取自 TaskWorkpiece / 来源生产记录，员工依次取自来源生产记录、
        # 最后兜底「员工表第一条」——于是「请求没选人」会真的把返工任务派给一个与请求无关的员工。
        # 此处一律要求显式入参，系统不再自动指派。
        missing = []
        if not rework_process_id:
            missing.append('工序 rework_process_id')
        if not employee_id:
            missing.append('员工 employee_id')
        if missing:
            raise ValueError(
                f'返工处置需显式选择{"、".join(missing)}（不合格单 #{nc.id}）；'
                f'请在返工表单中选择工序与员工后重试，系统不再自动指派。'
            )
        # P-05（DEC-2 §2.3）：件数 = 显式入参 > 来源生产记录 quantity > 兜底 1（必须留痕）
        source_record = production_record_for_nonconformity(nc, workpiece=wp)
        quantity, quantity_note = rework_quantity_for(nc, wp, rework_quantity,
                                                     production_record=source_record)
        task_notes = f'返工 不合格单#{nc.id}'
        if quantity_note:
            task_notes = f'{task_notes}；{quantity_note}'
        task = TaskAssignment(
            employee_id=employee_id,
            process_id=rework_process_id,
            target_date=target_date or date.today(),
            quantity=quantity,
            status='pending',
            task_type='auto',
            notes=task_notes,
        )
        db.session.add(task)
        db.session.flush()
        if wp:
            db.session.add(TaskWorkpiece(task_id=task.id, workpiece_id=wp.id, status='pending'))
            wp.status = 'machining'
        nc.rework_task_id = task.id
        if wp:
            log_event(wp, 'rework', task_id=task.id,
                      payload={'nc_id': nc.id, 'quantity': quantity})
        current_app.logger.info(
            f'返工处置：不合格单 {nc.id} 新建返工任务 {task.id}，工序 {rework_process_id}，'
            f'员工 {employee_id}，件数 {quantity}（{quantity_note or "显式入参"}）')
        nc.status = 'done'
        reset_quality_status_after_disposal(nc)
        return nc

    if action == 'scrap':
        pieces = normalize_pieces(scrap_quantity, field='scrap_quantity')
        nc.scrap_cost = scrap_cost or 0
        nc.status = 'done'
        if wp:
            wp.status = 'scrap'
            inbound_workpiece(wp, stock_kind='scrap',
                              inspector_name=getattr(current_user, 'username', '系统'),
                              quantity=pieces)
            log_event(wp, 'scrap', payload={'nc_id': nc.id, 'scrap_cost': nc.scrap_cost,
                                            'pieces': pieces})
        else:
            # P-09 补口：报工路径报废的 workpiece_id IS NULL ⇒ 无 Workpiece 可承载台账行，
            # 原先只扣料 + 置实例状态、库存台账零行。这里按件数补写 stock_kind='scrap'
            # 台账行（notes 回写 nc.id 便于追溯），沿用既有库位，不新建表/列/库位。
            inbound_production_scrap(nc=nc, quantity=pieces, inspector_name=operator_name())
        # P-06（DEC-2 §2.4）：逐行各扣各自物料；取不到消耗数据 ⇒ 不扣料 + 未扣减说明
        _plan_record, plan = scrap_material_plan(nc, workpiece=wp)
        applied = deduct_scrap_materials(plan, pieces=pieces, nc=nc)
        item = batch_item_for_nonconformity(nc, workpiece=wp)
        if item is not None:
            # §1.3：报废是终态 —— 即使 quality_status 复位成 pass，门禁仍必须拒绝（RC-5/RC-11）
            item.status = 'scrapped'
        current_app.logger.info(
            f'报废处置：不合格单 {nc.id} 件数 {pieces}，扣料 {applied}，'
            f'实例状态 {getattr(item, "status", None)}')
        reset_quality_status_after_disposal(nc)
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


# ============================================================================
# 计件工资口径（`07b` DEC-2 §2.2 / §2.5，P-04）
#
# 为什么放在本模块而不是新建 `services/piecework.py`：`check_properties.py` 的**文件计数**
# （`properties_files=23`）被 E-04 的 `run_gates.py` 锁在 `expected_lock` 里，新增一个
# `app/**/*.py` 会让该锁定值漂移、连带 `ci_gates` 的 check_properties 期望行失配。
# DEC-2 §2.5 明确允许「置于 `mes_service` 内只读函数」这一选项，故按该口径落地。
#
# 本段是整个仓库对 `quality.rework_counts_piecework` 的**唯一读取点**，也是「返工记录是否计入
# 计件」的**唯一判定处**；S1（`routes.py` 主表）/ S2（`models.Employee.total_salary`）/
# S3（员工详情当日）/ S4（员工详情当月）一律调用 `piecework_amount`，模板侧不得出现开关判断
# （AC-04-e / AC-04-e2 / RC-17 / RC-19）。
#
# 返工识别（DEC-2 §2.2「反查优先」）：
#   R1 主判据 `NonconformityRecord.rework_task_id == TaskAssignment.id`；
#   R2 次判据 该任务 `global_sn` 与 `ProductionRecord.global_sn` 相等（报工链唯一关联键）；
#   R3 辅助（`task_type=='auto'` 且 notes 以「返工 不合格单#」开头）**只作人工可读提示，不参与判定**
#      —— `07b` 明确否决 `task_type=='auto'` 单判（批次自动派工同用该值，会误伤正常工时 / RC-16）。
# ============================================================================

REWORK_NOTE_PREFIX = '返工 不合格单#'


def rework_counts_piecework():
    """`quality.rework_counts_piecework` 的唯一读取点；行缺失时缺省 `False`（RC-18）。"""
    value = SystemConfig.get('quality.rework_counts_piecework', False)
    if isinstance(value, str):
        return value.strip().lower() in ('1', 'true', 'yes', 'on')
    return bool(value)


def rework_task_ids():
    """R1：被不合格单引用为「返工任务」的 `TaskAssignment.id` 集合。"""
    rows = (NonconformityRecord.query
            .with_entities(NonconformityRecord.rework_task_id)
            .filter(NonconformityRecord.rework_task_id.isnot(None))
            .all())
    return {row[0] for row in rows if row[0]}


def rework_task_global_sns():
    """R1 → R2：返工任务的 `global_sn` 集合（返工任务报工产生的记录会带上该关联键）。"""
    ids = rework_task_ids()
    if not ids:
        return set()
    rows = (TaskAssignment.query.with_entities(TaskAssignment.global_sn)
            .filter(TaskAssignment.id.in_(ids)).all())
    return {row[0] for row in rows if row[0]}


def rework_production_record_ids(records):
    """`records` 中判定为返工的 `ProductionRecord.id` 集合（R1∨R2）。"""
    sns = rework_task_global_sns()
    if not sns:
        return set()
    return {r.id for r in records
            if getattr(r, 'id', None) is not None and (getattr(r, 'global_sn', None) in sns)}


def is_rework_task(task):
    """R1 口径下该任务是否为返工任务（R3 仅作提示、不参与判定）。"""
    if task is None or getattr(task, 'id', None) is None:
        return False
    return task.id in rework_task_ids()


def rework_hint(task):
    """R3：人工可读提示（**不参与判定**）。"""
    if task is None:
        return False
    return ((getattr(task, 'task_type', None) == 'auto')
            and (getattr(task, 'notes', '') or '').startswith(REWORK_NOTE_PREFIX))


def piecework_breakdown(records):
    """把一个生产记录集合拆成 `(计入金额, 被剔除金额, 返工记录 id 集合)`（未乘员工系数）。"""
    records = list(records)
    excluded = set() if rework_counts_piecework() else rework_production_record_ids(records)
    counted = 0.0
    dropped = 0.0
    for record in records:
        amount = record.quantity * record.process.price
        if getattr(record, 'id', None) in excluded:
            dropped += amount
        else:
            counted += amount
    return counted, dropped, excluded


def piecework_amount(records):
    """计件金额（**唯一口径**，未乘系数）：开关开 ⇒ 全含；关 ⇒ 剔除返工记录。

    与既有实现逐字同式（`record.quantity * record.process.price`），只多一层返工过滤
    ⇒ 开关 `True` 时与修复前**完全等价**（回退安全）。
    """
    counted, _dropped, _excluded = piecework_breakdown(records)
    return counted
