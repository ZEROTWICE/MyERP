"""发货出库与签收回执。"""
from datetime import datetime

from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from werkzeug.exceptions import HTTPException

from app import db
from app.models import (
    FinishedProduct, SalesOrder, SalesOrderItem, Shipment, ShipmentItem, ShipmentReceipt,
    Workpiece,
)
from app.permissions import require_capability
from app.services import mes_service
from . import bp


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
        ship = Shipment(sales_order_id=order.id, shipped_by=current_user.id, notes=request.form.get('notes'))
        db.session.add(ship)
        db.session.flush()
        whole = request.form.get('whole') == '1'
        if whole:
            for line in order.items:
                fps = FinishedProduct.query.filter_by(
                    product_id=line.product_id, stock_kind='fg', status='in_stock'
                ).limit(int(line.quantity or 0)).all()
                for fp in fps:
                    db.session.add(ShipmentItem(
                        shipment_id=ship.id, sales_order_item_id=line.id,
                        finished_product_id=fp.id, workpiece_id=fp.workpiece_id, quantity=fp.quantity or 1,
                    ))
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
    if ship.sales_order:
        for line in ship.sales_order.items:
            fps = FinishedProduct.query.filter(
                FinishedProduct.status == 'in_stock',
                FinishedProduct.stock_kind.in_(['fg', 'wip_part']),
            )
            if line.product_id:
                fps = fps.filter(db.or_(
                    FinishedProduct.product_id == line.product_id,
                    FinishedProduct.drawing_number == (line.product.drawing_number if line.product else ''),
                ))
            available.extend(fps.limit(50).all())
    return render_template('main/shipping/detail.html', ship=ship, available=available)


@bp.route('/shipments/<int:id>/add_item', methods=['POST'])
@login_required
@require_capability('shipment.manage')
def shipment_add_item(id):
    try:
        ship = Shipment.query.get_or_404(id)
        fp = FinishedProduct.query.get_or_404(request.form.get('finished_product_id', type=int))
        if fp.status != 'in_stock':
            flash('该库存不在库', 'danger')
            return redirect(url_for('main.shipment_detail', id=ship.id))
        db.session.add(ShipmentItem(
            shipment_id=ship.id,
            sales_order_item_id=request.form.get('sales_order_item_id', type=int),
            finished_product_id=fp.id,
            workpiece_id=fp.workpiece_id,
            quantity=fp.quantity or 1,
        ))
        db.session.commit()
        flash('已加入发货单', 'success')
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
        if ship.items.count() < 1:
            flash('发货单没有明细', 'danger')
            return redirect(url_for('main.shipment_detail', id=ship.id))
        for it in ship.items.all():
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
            remaining = FinishedProduct.query.filter_by(status='in_stock').count()
            # 若订单行均已发完则完成
            shipped_qty = sum(i.quantity or 0 for sh in order.shipments for i in sh.items)
            ordered = sum(i.quantity or 0 for i in order.items)
            if shipped_qty >= ordered:
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
