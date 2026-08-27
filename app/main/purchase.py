"""采购：供应商、请购、采购单、到货、对账。完整流程默认可由配置关闭请购审批。"""
from datetime import date, datetime

from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from werkzeug.exceptions import HTTPException

from app import db
from app.models import (
    Consumable, GoodsReceipt, GoodsReceiptItem, PurchaseOrder, PurchaseOrderItem,
    PurchaseRequisition, PurchaseRequisitionItem, PurchaseSettlement, RawMaterial,
    RawMaterialCategory, Supplier, SystemConfig,
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
        po = PurchaseOrder(
            supplier_id=request.form.get('supplier_id', type=int),
            created_by=current_user.id,
            status='confirmed',
            notes=request.form.get('notes'),
            order_date=date.today(),
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
        db.session.commit()
        flash('采购单已保存', 'success')
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
    """检验通过或免检后写入原材料/易耗品库存。"""
    po = receipt.purchase_order
    for line in receipt.items.all():
        poi = line.po_item
        if not poi:
            continue
        if poi.material_type == 'consumable':
            from app.models import ConsumableCategory
            cat = ConsumableCategory.query.first()
            if cat is None:
                cat = ConsumableCategory(name='采购入库', code='PO', created_by=current_user.id)
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
                cat = RawMaterialCategory(name='采购入库', code='PO', created_by=current_user.id)
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


@bp.route('/goods_receipts/<int:id>/putaway', methods=['POST'])
@login_required
@require_capability('purchase.manage')
def putaway_goods_receipt(id):
    try:
        receipt = GoodsReceipt.query.get_or_404(id)
        if receipt.status not in ('accepted', 'pending_inspection'):
            flash('当前到货单不可入库', 'danger')
            return redirect(url_for('main.purchase_order_detail', id=receipt.po_id))
        _putaway_receipt(receipt)
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
