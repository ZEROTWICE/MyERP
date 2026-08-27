"""半成品/未通过/报废库、组装扣料、不合格处置。"""
from flask import current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from werkzeug.exceptions import HTTPException

from app import csrf, db
from app.models import FinishedProduct, NonconformityRecord, Product, Workpiece
from app.permissions import require_capability
from app.services import mes_service
from . import bp


@bp.route('/stock/<kind>')
@login_required
@require_capability('inventory.view')
def stock_by_kind(kind):
    if kind not in ('fg', 'wip_part', 'failed', 'scrap'):
        flash('未知库别', 'danger')
        return redirect(url_for('main.manage_inventory'))
    items = FinishedProduct.query.filter_by(stock_kind=kind).order_by(FinishedProduct.id.desc()).limit(200).all()
    labels = {'fg': '成品库', 'wip_part': '半成品库', 'failed': '未通过库', 'scrap': '报废库'}
    return render_template('main/stock/list.html', items=items, kind=kind, title=labels[kind])


@bp.route('/assembly', methods=['GET'])
@login_required
@require_capability('production_order.manage')
def assemble_index():
    products = Product.query.filter_by(status='active').order_by(Product.product_code).all()
    return render_template('main/stock/assemble.html', products=products, product=None)


@bp.route('/assembly/<int:product_id>', methods=['GET', 'POST'])
@login_required
@require_capability('production_order.manage')
def assemble_product(product_id):
    product = Product.query.get_or_404(product_id)
    if request.method == 'POST':
        try:
            qty = request.form.get('quantity', type=int) or 1
            codes = [c.strip() for c in (request.form.get('workpiece_codes') or '').split(',') if c.strip()]
            wp_ids = []
            for code in codes:
                wp = Workpiece.query.filter_by(code=code).first()
                if wp:
                    wp_ids.append(wp.id)
            consumed, shortages = mes_service.consume_bom_for_assembly(product, qty, wp_ids)
            if shortages:
                db.session.rollback()
                flash('缺料：' + ', '.join(f"{s['name']}×{s['qty']}" for s in shortages), 'danger')
                return redirect(url_for('main.assemble_product', product_id=product.id))
            from app.models import SerialNumber
            for i in range(qty):
                wp = mes_service.ensure_workpiece(
                    code=f'{product.product_code}-A{SerialNumber.get_next_number()}',
                    product_id=product.id,
                    status='assembled',
                )
                wp.status = 'assembled'
                task = mes_service.create_inspection_task('workpiece', wp.id, notes=f'组装末道质检 {product.product_code}')
                mes_service.log_event(wp, 'assembled', payload={'inspection_task_id': task.id})
            db.session.commit()
            flash('组装完成，已生成末道质检', 'success')
            return redirect(url_for('main.assemble_product', product_id=product.id))
        except HTTPException:
            raise
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'组装失败: {e}')
            flash(f'组装失败：{e}', 'danger')
    return render_template('main/stock/assemble.html', product=product)


@bp.route('/api/quality/nonconformities/<int:id>/dispose', methods=['POST'])
@login_required
@require_capability('quality.inspect')
@csrf.exempt
def dispose_nonconformity_api(id):
    try:
        nc = NonconformityRecord.query.get_or_404(id)
        data = request.get_json() or request.form
        action = data.get('action') or data.get('type')
        proc = data.get('rework_process_id')
        emp = data.get('employee_id')
        mes_service.dispose_nonconformity(
            nc, action,
            notes=data.get('notes') or '',
            scrap_cost=float(data.get('scrap_cost') or 0),
            rework_process_id=int(proc) if proc else None,
            employee_id=int(emp) if emp else None,
        )
        db.session.commit()
        return jsonify({'success': True, 'message': '处置已记录', 'status': nc.status})
    except HTTPException:
        raise
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'不合格处置失败: {e}')
        return jsonify({'success': False, 'message': str(e)}), 500


@bp.route('/quality/nonconformities')
@login_required
@require_capability('quality.view')
def manage_nonconformities():
    items = NonconformityRecord.query.order_by(NonconformityRecord.id.desc()).limit(200).all()
    return render_template('main/stock/nonconformities.html', items=items)
