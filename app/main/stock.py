"""半成品/未通过/报废库、组装扣料、不合格处置。"""
from flask import current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from werkzeug.exceptions import HTTPException

from app import db
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
def dispose_nonconformity_api(id):
    """不合格处置：生产质检（返工/报废/让步）与来料检（退货/让步接收/报废）共用一个入口。

    P1-3：本端点由 templates/main/stock/nonconformities.html 的真实 HTML 表单 POST 调用，
    表单已渲染 csrf_token，原先的 @csrf.exempt 等于对跨站表单完全不设防，已删除。
    处置对象口径（target_type=workpiece / goods_receipt）由 mes_service.dispose_nonconformity
    按单据自动分流，动作不适用时返回 400 与明确提示。
    """
    try:
        nc = NonconformityRecord.query.get_or_404(id)
        data = request.get_json(silent=True) or request.form
        action = (data.get('action') or data.get('type') or '').strip()
        proc = data.get('rework_process_id')
        emp = data.get('employee_id')
        # DEC-2 §2.3/§2.4：返工件数与报废件数是**两个独立可选入参**（`16` §11 补记：不得合并）。
        # 缺省即各自走默认口径；非法值（0/负数/非整数）由 mes_service 抛 ValueError ⇒ 下方 400。
        rework_qty = data.get('rework_quantity')
        scrap_qty = data.get('scrap_quantity')
        mes_service.dispose_nonconformity(
            nc, action,
            notes=data.get('notes') or '',
            scrap_cost=float(data.get('scrap_cost') or 0),
            rework_process_id=int(proc) if proc else None,
            employee_id=int(emp) if emp else None,
            rework_quantity=int(rework_qty) if rework_qty not in (None, '') else None,
            scrap_quantity=int(scrap_qty) if scrap_qty not in (None, '') else None,
        )
        db.session.commit()
        target_type, target_id = mes_service.nonconformity_target(nc)
        return jsonify({'success': True, 'message': '处置已记录', 'status': nc.status,
                        'target_type': target_type, 'target_id': target_id})
    except HTTPException:
        raise
    except ValueError as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400
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
