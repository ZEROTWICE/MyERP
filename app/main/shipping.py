"""发货出库与签收回执。

发货数量口径（2026-09-18 用户拍板）：
- 一条成品行不再等于一个发货单位：发货 N 件时按需拆分成品行（见 mes_service.shipment_take_finished_product），
  绑定工件的成品行不可拆，只能整行发；
- 整单（create_shipment）与按行（shipment_add_item）两条路径共用 mes_service.shipment_register_finished_product，
  统一校验「本次发货数量 = min(订单行剩余待发量, 该成品可用在库件数)」，且不得超过订单行剩余待发量；
- 完成判定在 confirm_shipment 中按订单行逐行累计（该行已发 vs 该行订购），不再用全局求和掩盖单行超发/漏发。
"""
from datetime import datetime

from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from werkzeug.exceptions import HTTPException

from app import db
from app.models import (
    FinishedProduct, SalesOrder, Shipment, ShipmentItem, ShipmentReceipt, Workpiece,
)
from app.permissions import require_capability
from app.services import mes_service
from . import bp


def _shipment_line_for_product(order, fp, preferred_line_id=None):
    """发货明细要挂的销售订单行：优先表单给定，否则按成品与订单行的产品/图号推断。

    返回 (line, None) 或 (None, 可读原因)。推断不出或给定行不属于该订单时拒绝，
    避免把成品记到别的订单行上（记错行会连带把完成判定算错）。
    """
    if order is None:
        return None, '发货单没有关联销售订单，无法匹配订单行'
    lines = list(order.order_items)
    if preferred_line_id:
        for line in lines:
            if line.id == preferred_line_id:
                return line, None
        return None, '所选销售订单行不属于该发货单的销售订单'
    matched = [line for line in lines if mes_service.shipment_product_matches_line(fp, line)]
    if not matched:
        return None, f'库存 {fp.serial_number} 与订单 {order.order_number} 的任何订单行都不匹配'
    for line in matched:
        # 优先挂到仍有剩余待发量的订单行，其次才是已发满的行（由统一校验给出可读拒绝）
        if mes_service.shipment_order_line_remaining_quantity(line) > 0:
            return line, None
    return matched[0], None


@bp.route('/shipments')
@login_required
@require_capability('shipment.manage')
def manage_shipments():
    items = Shipment.query.order_by(Shipment.id.desc()).limit(100).all()
    orders = SalesOrder.query.filter(SalesOrder.status.in_(['confirmed', 'in_production', 'completed'])).order_by(
        SalesOrder.id.desc()
    ).limit(50).all()
    return render_template('main/shipping/list.html', items=items, orders=orders)


@bp.route('/shipments/create', methods=['POST'])
@login_required
@require_capability('shipment.manage')
def create_shipment():
    try:
        oid = request.form.get('sales_order_id', type=int)
        order = SalesOrder.query.get_or_404(oid)
        if order.status == 'cancelled':
            flash('已取消的销售订单不能发货', 'danger')
            return redirect(url_for('main.manage_shipments'))
        ship = Shipment(sales_order_id=order.id, shipped_by=current_user.id, notes=request.form.get('notes'))
        db.session.add(ship)
        db.session.flush()
        whole = request.form.get('whole') == '1'
        if whole:
            # 整单配货：按订单行剩余待发量累计【件数】（原实现 limit(订单行数量) 限的是成品行条数，
            # 一条成品行往往有 5 件、1 件 1 行才正确，于是 3 件订单发走了 11 件）
            # 销售订单行的真实关系名是 order_items（lazy='dynamic'，只可迭代，不要 len()/下标）
            shipped_pieces = 0.0
            messages = []
            for line in order.order_items:
                pieces, line_messages = mes_service.shipment_fill_order_line(ship, line)
                shipped_pieces += pieces
                messages.extend(line_messages)
            if messages:
                flash('部分订单行未能配满：' + '；'.join(messages[:3]), 'warning')
            if shipped_pieces <= 0:
                db.session.rollback()
                flash('没有可配货的在库成品，未创建发货单', 'danger')
                return redirect(url_for('main.manage_shipments'))
        db.session.commit()
        flash('发货单已创建', 'success')
        return redirect(url_for('main.shipment_detail', id=ship.id))
    except HTTPException:
        raise
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'创建发货单失败: {e}')
        flash('创建失败', 'danger')
        return redirect(url_for('main.manage_shipments'))


@bp.route('/shipments/<int:id>')
@login_required
@require_capability('shipment.manage')
def shipment_detail(id):
    ship = Shipment.query.get_or_404(id)
    available = []
    seen_ids = set()
    if ship.sales_order:
        for line in ship.sales_order.order_items:
            # 已被任何未取消发货单（含本单）占用的成品行不再列出：第二张草稿单取不到该行
            for fp in mes_service.shipment_candidate_stock(line)[:50]:
                if fp.id in seen_ids:
                    continue
                seen_ids.add(fp.id)
                available.append(fp)
    return render_template('main/shipping/detail.html', ship=ship, available=available)


@bp.route('/shipments/<int:id>/add_item', methods=['POST'])
@login_required
@require_capability('shipment.manage')
def shipment_add_item(id):
    try:
        ship = Shipment.query.get_or_404(id)
        if ship.status != 'draft':
            flash('只有草稿状态的发货单可以加入明细', 'danger')
            return redirect(url_for('main.shipment_detail', id=ship.id))
        fp = FinishedProduct.query.get_or_404(request.form.get('finished_product_id', type=int))
        line, error = _shipment_line_for_product(
            ship.sales_order, fp, request.form.get('sales_order_item_id', type=int))
        if line is None:
            flash(error, 'danger')
            return redirect(url_for('main.shipment_detail', id=ship.id))
        # 表单未给数量时按 min(订单行剩余待发量, 该成品可用在库件数) 取，不再整行发走
        quantity = request.form.get('quantity', type=float)
        item, error = mes_service.shipment_register_finished_product(
            ship, line, finished_product=fp, quantity=quantity)
        if item is None:
            # 拒绝分支不得留下任何数据变更（成品行、发货明细、流水号都不动）
            db.session.rollback()
            flash(error, 'danger')
            return redirect(url_for('main.shipment_detail', id=ship.id))
        db.session.commit()
        flash(f'已加入发货单 {int(item.quantity or 0)} 件', 'success')
    except HTTPException:
        raise
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'加入发货明细失败: {e}')
        flash('操作失败', 'danger')
    return redirect(url_for('main.shipment_detail', id=id))


@bp.route('/shipments/<int:id>/ship', methods=['POST'])
@login_required
@require_capability('shipment.manage')
def confirm_shipment(id):
    try:
        ship = Shipment.query.get_or_404(id)
        if ship.status != 'draft':
            flash('该发货单已出库，不能重复出库', 'danger')
            return redirect(url_for('main.shipment_detail', id=ship.id))
        items = ship.items.all()
        if len(items) < 1:
            flash('发货单没有明细', 'danger')
            return redirect(url_for('main.shipment_detail', id=ship.id))
        for it in items:
            # 明细在登记时已按件数拆分，明细数量 == 成品行数量；只把明细指向的成品行置 shipped，
            # 不会把仍有余量的成品行整行置 shipped
            if it.finished_product_id:
                fp = FinishedProduct.query.get(it.finished_product_id)
                if fp:
                    fp.status = 'shipped'
            if it.workpiece_id:
                wp = Workpiece.query.get(it.workpiece_id)
                if wp:
                    wp.status = 'sold_as_part' if (it.finished_product and it.finished_product.stock_kind == 'wip_part') else 'fg'
                    mes_service.log_event(wp, 'shipped', payload={'shipment_id': ship.id})
        ship.status = 'shipped'
        ship.shipped_at = datetime.utcnow()
        order = ship.sales_order
        if order:
            db.session.flush()
            # 完成判定：逐订单行比较「该行已发数量 vs 该行订购数量」，全部行达标才 completed
            # （原实现用全局 shipped_qty >= ordered 求和，单行超发会把整单掩盖成已完成）
            lines = list(order.order_items)
            completed = bool(lines)
            shipped_total = 0.0
            ordered_total = 0.0
            for line in lines:
                ordered = float(line.quantity or 0)
                shipped = mes_service.shipment_order_line_shipped_quantity(line.id)
                shipped_total += shipped
                ordered_total += ordered
                if shipped + 1e-9 < ordered:
                    completed = False
            current_app.logger.info(
                f'订单 {order.order_number} 发货完成判定：已发 {shipped_total}/{ordered_total} 件，'
                f'completed={completed}'
            )
            if completed:
                order.status = 'completed'
            elif order.status == 'confirmed':
                order.status = 'in_production'
        db.session.commit()
        flash('已出库发货', 'success')
    except HTTPException:
        raise
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'发货失败: {e}')
        flash('操作失败', 'danger')
    return redirect(url_for('main.shipment_detail', id=id))


@bp.route('/shipments/<int:id>/sign', methods=['POST'])
@login_required
@require_capability('shipment.manage')
def sign_shipment(id):
    try:
        ship = Shipment.query.get_or_404(id)
        name = (request.form.get('signed_by_name') or '').strip()
        if not name:
            flash('签收人姓名必填', 'danger')
            return redirect(url_for('main.shipment_detail', id=ship.id))
        rec = ShipmentReceipt(
            shipment_id=ship.id,
            signed_by_name=name,
            notes=request.form.get('notes'),
        )
        db.session.add(rec)
        ship.status = 'signed'
        db.session.commit()
        flash('签收已登记', 'success')
    except HTTPException:
        raise
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'签收失败: {e}')
        flash('操作失败', 'danger')
    return redirect(url_for('main.shipment_detail', id=id))
