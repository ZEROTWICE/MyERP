"""采购：供应商、请购、采购单、到货、来料检处置、对账。完整流程默认可由配置关闭请购审批。"""
from datetime import date, datetime

from flask import current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from werkzeug.exceptions import HTTPException

from app import db
from app.models import (
    AuditLog, GoodsReceipt, GoodsReceiptItem, InspectionRecord, NonconformityRecord,
    PurchaseOrder, PurchaseOrderItem, PurchaseRequisition, PurchaseRequisitionItem,
    PurchaseSettlement, Supplier, SystemConfig,
)
from app.permissions import require_capability
from app.services import mes_service
from . import bp


def _full_workflow():
    return bool(SystemConfig.get('purchase.full_workflow_enabled', False))


def _settlement_on():
    return bool(SystemConfig.get('purchase.settlement_enabled', False))


def _incoming_qc():
    return bool(SystemConfig.get('purchase.incoming_inspection_required', True))


# 可转采购单的请购单状态：已审批（approved）或已转过（converted，允许分批再来一张）
_CONVERTIBLE_REQUISITION_STATUSES = ('approved', 'converted')
# 到货单可入库的状态：只有来料检结论为合格才行（pending_inspection 的后门已封）
_PUTAWAY_ALLOWED_STATUSES = ('accepted',)
_PUTAWAY_BLOCK_REASONS = {
    'pending_inspection': '到货单尚未完成来料检验，不能入库（请先完成来料检并按结论处置）',
    'rejected': '到货单来料检不合格且未处置，不能入库（请先完成退货/让步接收/报废处置）',
    'returned': '到货单已退货，不能入库',
    'scrapped': '到货单已报废，不能入库',
}


def _log_purchase(action, details, target_model='PurchaseOrder', target_id=None, new_data=None):
    db.session.add(AuditLog(
        user_id=current_user.id,
        action=action,
        details=details,
        can_rollback=False,
        target_model=target_model,
        target_id=target_id,
        new_data=new_data,
    ))


def _requisition_for_po(requisition_id):
    """取可用于转采购单的请购单；不可用时返回 (None, 原因)。"""
    if not requisition_id:
        return None, None
    req = PurchaseRequisition.query.get(requisition_id)
    if req is None:
        return None, f'请购单 #{requisition_id} 不存在'
    if (req.status or '') not in _CONVERTIBLE_REQUISITION_STATUSES:
        return None, f'请购单 {req.req_no} 当前状态为 {req.status}，仅已审批的请购单可转采购单'
    return req, None


def _open_incoming_nonconformity(receipt):
    """到货单上待处置的来料检不合格单。

    主口径是 NonconformityRecord.target_type='goods_receipt' + target_id=到货单 id；
    对 target 列出现前写入的记录，按该到货单质检任务对应的质检记录回退查找。
    """
    open_statuses = ('open', 'pending_approval')
    nc = NonconformityRecord.query.filter(
        NonconformityRecord.target_type == 'goods_receipt',
        NonconformityRecord.target_id == receipt.id,
        NonconformityRecord.status.in_(open_statuses),
    ).order_by(NonconformityRecord.id.desc()).first()
    if nc is not None:
        return nc
    if receipt.inspection_task_id:
        record_ids = [r.id for r in InspectionRecord.query.filter_by(
            task_id=receipt.inspection_task_id).all()]
        if record_ids:
            return NonconformityRecord.query.filter(
                NonconformityRecord.record_id.in_(record_ids),
                NonconformityRecord.status.in_(open_statuses),
            ).order_by(NonconformityRecord.id.desc()).first()
    return None


@bp.route('/suppliers')
@login_required
@require_capability('purchase.manage')
def manage_suppliers():
    items = Supplier.query.order_by(Supplier.code).all()
    return render_template('main/purchase/suppliers.html', items=items)


@bp.route('/suppliers/save', methods=['POST'])
@login_required
@require_capability('purchase.manage')
def save_supplier():
    try:
        sid = request.form.get('id', type=int)
        item = Supplier.query.get(sid) if sid else Supplier()
        item.code = (request.form.get('code') or '').strip()
        item.name = (request.form.get('name') or '').strip()
        item.contact = request.form.get('contact')
        item.phone = request.form.get('phone')
        item.address = request.form.get('address')
        item.notes = request.form.get('notes')
        item.is_active = request.form.get('is_active') == '1'
        if not item.code or not item.name:
            flash('编码和名称必填', 'danger')
            return redirect(url_for('main.manage_suppliers'))
        if not sid:
            db.session.add(item)
        db.session.commit()
        flash('供应商已保存', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'保存供应商失败: {e}')
        flash('保存失败', 'danger')
    return redirect(url_for('main.manage_suppliers'))


@bp.route('/purchase_requisitions')
@login_required
@require_capability('purchase.manage')
def manage_purchase_requisitions():
    if not _full_workflow():
        flash('完整请购流程未启用，可直接建采购单', 'info')
        return redirect(url_for('main.manage_purchase_orders'))
    items = PurchaseRequisition.query.order_by(PurchaseRequisition.id.desc()).all()
    return render_template('main/purchase/requisitions.html', items=items)


@bp.route('/purchase_requisitions/save', methods=['POST'])
@login_required
@require_capability('purchase.manage')
def save_purchase_requisition():
    try:
        req = PurchaseRequisition(requested_by=current_user.id, status='pending', notes=request.form.get('notes'))
        db.session.add(req)
        db.session.flush()
        names = request.form.getlist('item_name')
        qtys = request.form.getlist('item_qty')
        for name, qty in zip(names, qtys):
            if not name.strip():
                continue
            db.session.add(PurchaseRequisitionItem(
                requisition_id=req.id, material_name=name.strip(),
                quantity=float(qty or 1), spec=request.form.get('item_spec'),
            ))
        db.session.commit()
        flash('请购单已提交', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'保存请购单失败: {e}')
        flash('保存失败', 'danger')
    return redirect(url_for('main.manage_purchase_requisitions'))


@bp.route('/purchase_requisitions/<int:id>/approve', methods=['POST'])
@login_required
@require_capability('purchase.manage')
def approve_purchase_requisition(id):
    try:
        req = PurchaseRequisition.query.get_or_404(id)
        req.status = 'approved' if request.form.get('decision') != 'reject' else 'rejected'
        req.approved_by = current_user.id
        db.session.commit()
        flash('已审批', 'success')
    except HTTPException:
        raise
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'审批请购失败: {e}')
        flash('操作失败', 'danger')
    return redirect(url_for('main.manage_purchase_requisitions'))


@bp.route('/purchase_requisitions/<int:id>/convert', methods=['POST'])
@login_required
@require_capability('purchase.manage')
def convert_purchase_requisition(id):
    """决策 4：已审批请购单转采购单，写入 PurchaseOrder.requisition_id，来源可追溯。

    支持表单与 JSON 两种入参（supplier_id / notes / price_<明细id>）：
      - 表单：重定向回采购单详情页；
      - JSON：返回 {success, po_id, po_no, requisition_id, items}。
    完整流程开关（purchase.full_workflow_enabled）只控制 UI 是否暴露请购入口；
    本入口作用于「已审批」的请购单，不再二次受开关限制，否则关闭开关的库里
    已审批请购单会永久卡死（开关默认 false，见决策 3/4 的约束）。
    """
    wants_json = request.is_json
    try:
        req = PurchaseRequisition.query.get_or_404(id)
        data = request.get_json(silent=True) if wants_json else None
        supplier_id = (data or {}).get('supplier_id') or request.form.get('supplier_id', type=int)
        if (req.status or '') not in _CONVERTIBLE_REQUISITION_STATUSES:
            message = f'请购单 {req.req_no} 当前状态为 {req.status}，仅已审批的请购单可转采购单'
            if wants_json:
                return jsonify({'success': False, 'message': message}), 400
            flash(message, 'danger')
            return redirect(url_for('main.manage_purchase_orders'))
        if not supplier_id:
            message = '转采购单需要选择供应商'
            if wants_json:
                return jsonify({'success': False, 'message': message}), 400
            flash(message, 'danger')
            return redirect(url_for('main.manage_purchase_orders'))
        items = req.items.all()
        if not items:
            message = f'请购单 {req.req_no} 没有明细，无法转采购单'
            if wants_json:
                return jsonify({'success': False, 'message': message}), 400
            flash(message, 'danger')
            return redirect(url_for('main.manage_purchase_orders'))

        po = PurchaseOrder(
            supplier_id=int(supplier_id),
            created_by=current_user.id,
            status='confirmed',
            order_date=date.today(),
            notes=(data or {}).get('notes') or request.form.get('notes') or f'由请购单 {req.req_no} 转入',
            requisition_id=req.id,
        )
        db.session.add(po)
        db.session.flush()
        for item in items:
            unit_price = None
            if data:
                prices = data.get('prices') or {}
                unit_price = prices.get(str(item.id)) if isinstance(prices, dict) else None
            if unit_price is None:
                unit_price = request.form.get(f'price_{item.id}', type=float)
            db.session.add(PurchaseOrderItem(
                po_id=po.id,
                name=item.material_name,
                spec=item.spec,
                quantity=item.quantity or 0,
                unit_price=float(unit_price or 0),
                material_type=item.material_type or 'raw',
                unit=item.unit or '件',
            ))
        req.status = 'converted'
        _log_purchase(
            '请购单转采购单',
            f'请购单 {req.req_no} 转为采购单 {po.po_no}（{len(items)} 条明细）',
            target_id=po.id,
            new_data={'requisition_id': req.id, 'po_no': po.po_no, 'item_count': len(items)},
        )
        db.session.commit()
        current_app.logger.info(f'请购单 {req.req_no} 已转采购单 {po.po_no}（requisition_id={req.id}）')
        if wants_json:
            return jsonify({
                'success': True,
                'message': f'请购单 {req.req_no} 已转为采购单 {po.po_no}',
                'data': {'po_id': po.id, 'po_no': po.po_no, 'requisition_id': req.id,
                         'item_count': len(items)},
            })
        flash(f'请购单 {req.req_no} 已转为采购单 {po.po_no}', 'success')
        return redirect(url_for('main.purchase_order_detail', id=po.id))
    except HTTPException:
        raise
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'请购单转采购单失败: {e}')
        if wants_json:
            return jsonify({'success': False, 'message': f'转采购单失败：{e}'}), 500
        flash('操作失败', 'danger')
        return redirect(url_for('main.manage_purchase_orders'))


@bp.route('/purchase_orders')
@login_required
@require_capability('purchase.manage')
def manage_purchase_orders():
    items = PurchaseOrder.query.order_by(PurchaseOrder.id.desc()).all()
    suppliers = Supplier.query.filter_by(is_active=True).all()
    return render_template(
        'main/purchase/orders.html', items=items, suppliers=suppliers,
        full_workflow=_full_workflow(), settlement_on=_settlement_on(),
    )


@bp.route('/purchase_orders/save', methods=['POST'])
@login_required
@require_capability('purchase.manage')
def save_purchase_order():
    try:
        # 决策 4：可把采购单挂到已审批请购单上（表单/URL 参数 requisition_id），来源可追溯
        requisition_id = (request.form.get('requisition_id', type=int)
                          or request.args.get('requisition_id', type=int))
        requisition, reason = _requisition_for_po(requisition_id)
        if requisition_id and requisition is None:
            flash(reason, 'danger')
            return redirect(url_for('main.manage_purchase_orders'))
        po = PurchaseOrder(
            supplier_id=request.form.get('supplier_id', type=int),
            created_by=current_user.id,
            status='confirmed',
            notes=request.form.get('notes'),
            order_date=date.today(),
            requisition_id=requisition.id if requisition else None,
        )
        db.session.add(po)
        db.session.flush()
        names = request.form.getlist('item_name')
        qtys = request.form.getlist('item_qty')
        prices = request.form.getlist('item_price')
        types = request.form.getlist('item_type')
        for i, name in enumerate(names):
            if not name.strip():
                continue
            db.session.add(PurchaseOrderItem(
                po_id=po.id,
                name=name.strip(),
                quantity=float(qtys[i] if i < len(qtys) else 1),
                unit_price=float(prices[i] if i < len(prices) else 0),
                material_type=(types[i] if i < len(types) else 'raw') or 'raw',
            ))
        if requisition is not None:
            requisition.status = 'converted'
            _log_purchase(
                '采购单关联请购单',
                f'采购单 {po.po_no} 挂到请购单 {requisition.req_no}',
                target_id=po.id,
                new_data={'requisition_id': requisition.id, 'po_no': po.po_no},
            )
        db.session.commit()
        flash('采购单已保存' + (f'（来源请购单 {requisition.req_no}）' if requisition else ''), 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'保存采购单失败: {e}')
        flash('保存失败', 'danger')
    return redirect(url_for('main.manage_purchase_orders'))


@bp.route('/purchase_orders/<int:id>')
@login_required
@require_capability('purchase.manage')
def purchase_order_detail(id):
    po = PurchaseOrder.query.get_or_404(id)
    return render_template(
        'main/purchase/order_detail.html', po=po,
        incoming_qc=_incoming_qc(), settlement_on=_settlement_on(),
    )


@bp.route('/purchase_orders/<int:id>/receive', methods=['POST'])
@login_required
@require_capability('purchase.manage')
def receive_purchase_order(id):
    try:
        po = PurchaseOrder.query.get_or_404(id)
        receipt = GoodsReceipt(po_id=po.id, received_by=current_user.id, notes=request.form.get('notes'))
        if _incoming_qc():
            receipt.status = 'pending_inspection'
        else:
            receipt.status = 'accepted'
        db.session.add(receipt)
        db.session.flush()
        for item in po.items.all():
            qty = request.form.get(f'qty_{item.id}', type=float)
            if not qty:
                continue
            db.session.add(GoodsReceiptItem(receipt_id=receipt.id, po_item_id=item.id, quantity=qty))
            item.received_qty = (item.received_qty or 0) + qty
        if _incoming_qc():
            task = mes_service.create_inspection_task('goods_receipt', receipt.id, notes=f'到货 {receipt.receipt_no} 来料检验')
            receipt.inspection_task_id = task.id
        else:
            _putaway_receipt(receipt)
        po.status = 'received'
        db.session.commit()
        flash('到货已登记' + ('，请完成来料检验' if _incoming_qc() else '并已入库'), 'success')
        return redirect(url_for('main.purchase_order_detail', id=po.id))
    except HTTPException:
        raise
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'到货失败: {e}')
        flash('操作失败', 'danger')
        return redirect(url_for('main.purchase_order_detail', id=id))


def _putaway_receipt(receipt):
    """兼容包装：入库写入已上移到 mes_service.putaway_goods_receipt（库存写入归服务层）。"""
    return mes_service.putaway_goods_receipt(receipt)


@bp.route('/goods_receipts/<int:id>/putaway', methods=['POST'])
@login_required
@require_capability('purchase.manage')
def putaway_goods_receipt(id):
    """到货入库：只有来料检结论合格（status='accepted'）的到货单才能入库。

    P1-3：原先允许 pending_inspection 直接入库，等于绕开来料检结论；现在一律拒绝，
    并写 logger.warning + AuditLog（以免「被拒」这件事本身没有痕迹）。
    """
    try:
        receipt = GoodsReceipt.query.get_or_404(id)
        if receipt.status not in _PUTAWAY_ALLOWED_STATUSES:
            reason = _PUTAWAY_BLOCK_REASONS.get(receipt.status or '')
            if reason:
                current_app.logger.warning(
                    f'拒绝到货入库：到货单 {receipt.receipt_no} 状态为 {receipt.status}，{reason}'
                )
                _log_purchase(
                    '拒绝到货入库',
                    f'到货单 {receipt.receipt_no}（状态 {receipt.status}）被拒入库：{reason}',
                    target_model='GoodsReceipt', target_id=receipt.id,
                    new_data={'status': receipt.status, 'reason': reason},
                )
                db.session.commit()
                flash(reason, 'danger')
            elif receipt.status == 'putaway':
                flash('该到货单已入库', 'info')
            else:
                flash('当前到货单不可入库', 'danger')
            return redirect(url_for('main.purchase_order_detail', id=receipt.po_id))
        mes_service.putaway_goods_receipt(receipt)
        db.session.commit()
        flash('已入库', 'success')
        return redirect(url_for('main.purchase_order_detail', id=receipt.po_id))
    except HTTPException:
        raise
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'入库失败: {e}')
        flash('操作失败', 'danger')
        return redirect(url_for('main.manage_purchase_orders'))


@bp.route('/goods_receipts/<int:id>/nonconformity', methods=['POST'])
@login_required
@require_capability('quality.inspect')
def dispose_goods_receipt_nonconformity(id):
    """决策 3：来料检不合格处置入口——退货（return）/ 让步接收（accept）/ 报废（scrap）。

    处置结果落在 NonconformityRecord（target_type='goods_receipt'，与生产质检的
    target_type='workpiece' 明确区分）；让步接收按检验结论放行入库，退货/报废不入库。
    入参兼容 JSON 与表单（action/type、notes、scrap_cost）。
    """
    try:
        receipt = GoodsReceipt.query.get_or_404(id)
        data = request.get_json(silent=True) or request.form
        action = (data.get('action') or data.get('type') or '').strip()
        nc = _open_incoming_nonconformity(receipt)
        if nc is None:
            return jsonify({'success': False,
                            'message': f'到货单 {receipt.receipt_no} 没有待处置的来料检不合格单'}), 404
        mes_service.dispose_incoming_nonconformity(
            nc, action,
            notes=data.get('notes') or '',
            scrap_cost=float(data.get('scrap_cost') or 0),
        )
        db.session.commit()
        return jsonify({
            'success': True,
            'message': '处置已记录',
            'data': {'nonconformity_id': nc.id, 'action': nc.type, 'status': nc.status,
                     'receipt_status': receipt.status,
                     'target_type': nc.target_type, 'target_id': nc.target_id},
        })
    except HTTPException:
        raise
    except ValueError as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'来料检不合格处置失败: {e}')
        return jsonify({'success': False, 'message': f'处置失败：{e}'}), 500


@bp.route('/purchase_orders/<int:id>/settle', methods=['POST'])
@login_required
@require_capability('purchase.manage')
def settle_purchase_order(id):
    if not _settlement_on():
        flash('对账付款未启用', 'warning')
        return redirect(url_for('main.purchase_order_detail', id=id))
    try:
        po = PurchaseOrder.query.get_or_404(id)
        amount = sum((i.quantity or 0) * (i.unit_price or 0) for i in po.items.all())
        st = PurchaseSettlement(po_id=po.id, amount=amount, status='paid', paid_at=datetime.utcnow(),
                                notes=request.form.get('notes'))
        db.session.add(st)
        db.session.commit()
        flash(f'已登记付款 {amount}', 'success')
    except HTTPException:
        raise
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'对账失败: {e}')
        flash('操作失败', 'danger')
    return redirect(url_for('main.purchase_order_detail', id=id))
