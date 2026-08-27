"""设备、工作中心、煅烧炉次与工件溯源。"""
from datetime import datetime

from flask import current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from werkzeug.exceptions import HTTPException

from app import csrf, db
from app.models import (
    Equipment, EquipmentCapability, EquipmentDowntime, FurnaceLayout, FurnaceLayoutCell,
    HeatLot, HeatLotSlot, ProcessPrice, ProductionBatchItem, RawMaterial,
    WorkCenter, WorkCenterEquipment, Workpiece, WorkpieceEvent,
)
from app.permissions import require_capability
from app.services import mes_service
from . import bp


@bp.route('/equipment')
@login_required
@require_capability('equipment.manage')
def manage_equipment():
    kind = request.args.get('kind', '')
    q = Equipment.query
    if kind:
        q = q.filter_by(kind=kind)
    items = q.order_by(Equipment.kind, Equipment.code).all()
    processes = ProcessPrice.query.filter_by(is_current=True).order_by(ProcessPrice.process_code).all()
    return render_template('main/equipment/list.html', items=items, kind=kind, processes=processes)


@bp.route('/equipment/save', methods=['POST'])
@login_required
@require_capability('equipment.manage')
def save_equipment():
    try:
        eid = request.form.get('id', type=int)
        item = Equipment.query.get(eid) if eid else Equipment()
        item.code = (request.form.get('code') or '').strip()
        item.name = (request.form.get('name') or '').strip()
        item.kind = request.form.get('kind') or 'other'
        item.status = request.form.get('status') or 'running'
        item.length_mm = request.form.get('length_mm', type=float)
        item.width_mm = request.form.get('width_mm', type=float)
        item.height_mm = request.form.get('height_mm', type=float)
        item.notes = request.form.get('notes')
        if not item.code or not item.name:
            flash('编号和名称必填', 'danger')
            return redirect(url_for('main.manage_equipment'))
        if not eid:
            db.session.add(item)
        db.session.flush()
        EquipmentCapability.query.filter_by(equipment_id=item.id).delete()
        for pid in request.form.getlist('process_ids'):
            db.session.add(EquipmentCapability(equipment_id=item.id, process_id=int(pid)))
        db.session.commit()
        flash('设备已保存', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'保存设备失败: {e}')
        flash('保存失败', 'danger')
    return redirect(url_for('main.manage_equipment'))


@bp.route('/equipment/<int:id>/downtime', methods=['POST'])
@login_required
@require_capability('equipment.manage')
def equipment_downtime(id):
    try:
        eq = Equipment.query.get_or_404(id)
        reason = (request.form.get('reason') or '维修').strip()
        down = EquipmentDowntime(equipment_id=eq.id, reason=reason, created_by=current_user.id)
        eq.status = 'maintenance'
        db.session.add(down)
        db.session.commit()
        flash(f'{eq.code} 已进入维修', 'warning')
    except HTTPException:
        raise
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'登记停机失败: {e}')
        flash('操作失败', 'danger')
    return redirect(url_for('main.manage_equipment'))


@bp.route('/equipment/<int:id>/resume', methods=['POST'])
@login_required
@require_capability('equipment.manage')
def equipment_resume(id):
    try:
        eq = Equipment.query.get_or_404(id)
        open_dt = EquipmentDowntime.query.filter_by(equipment_id=eq.id).filter(
            EquipmentDowntime.ended_at.is_(None)
        ).first()
        if open_dt:
            open_dt.ended_at = datetime.utcnow()
        eq.status = 'running'
        db.session.commit()
        flash(f'{eq.code} 已恢复运行', 'success')
    except HTTPException:
        raise
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'恢复设备失败: {e}')
        flash('操作失败', 'danger')
    return redirect(url_for('main.manage_equipment'))


@bp.route('/work_centers')
@login_required
@require_capability('equipment.manage')
def manage_work_centers():
    centers = WorkCenter.query.order_by(WorkCenter.code).all()
    equipment = Equipment.query.filter(Equipment.status != 'retired').order_by(Equipment.code).all()
    return render_template('main/equipment/work_centers.html', centers=centers, equipment=equipment)


@bp.route('/work_centers/save', methods=['POST'])
@login_required
@require_capability('equipment.manage')
def save_work_center():
    try:
        cid = request.form.get('id', type=int)
        item = WorkCenter.query.get(cid) if cid else WorkCenter()
        item.code = (request.form.get('code') or '').strip()
        item.name = (request.form.get('name') or '').strip()
        item.notes = request.form.get('notes')
        if not cid:
            db.session.add(item)
        db.session.flush()
        WorkCenterEquipment.query.filter_by(work_center_id=item.id).delete()
        for eid in request.form.getlist('equipment_ids'):
            db.session.add(WorkCenterEquipment(work_center_id=item.id, equipment_id=int(eid)))
        db.session.commit()
        flash('工作中心已保存', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'保存工作中心失败: {e}')
        flash('保存失败', 'danger')
    return redirect(url_for('main.manage_work_centers'))


@bp.route('/equipment/<int:id>/layout', methods=['GET', 'POST'])
@login_required
@require_capability('equipment.manage')
def furnace_layout(id):
    eq = Equipment.query.get_or_404(id)
    layout = FurnaceLayout.query.filter_by(equipment_id=eq.id).first()
    if request.method == 'POST':
        try:
            if not layout:
                layout = FurnaceLayout(equipment_id=eq.id, name=request.form.get('name') or f'{eq.code}装炉图')
                db.session.add(layout)
                db.session.flush()
            else:
                layout.name = request.form.get('name') or layout.name
            layers = request.form.get('layers', type=int) or 1
            rows = request.form.get('rows', type=int) or 1
            cols = request.form.get('cols', type=int) or 1
            FurnaceLayoutCell.query.filter_by(layout_id=layout.id).delete()
            for layer in range(1, layers + 1):
                for r in range(1, rows + 1):
                    for c in range(1, cols + 1):
                        db.session.add(FurnaceLayoutCell(
                            layout_id=layout.id, layer=layer, row=r, col=c, max_pieces=1
                        ))
            db.session.commit()
            flash('装炉图已生成', 'success')
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'保存装炉图失败: {e}')
            flash('保存失败', 'danger')
        return redirect(url_for('main.furnace_layout', id=eq.id))
    cells = []
    if layout:
        cells = layout.cells.order_by(
            FurnaceLayoutCell.layer, FurnaceLayoutCell.row, FurnaceLayoutCell.col
        ).all()
    return render_template('main/equipment/furnace_layout.html', equipment=eq, layout=layout, cells=cells)


@bp.route('/heat_lots')
@login_required
@require_capability('equipment.manage')
def manage_heat_lots():
    lots = HeatLot.query.order_by(HeatLot.id.desc()).limit(100).all()
    furnaces = Equipment.query.filter_by(kind='furnace').order_by(Equipment.code).all()
    return render_template('main/equipment/heat_lots.html', lots=lots, furnaces=furnaces)


@bp.route('/heat_lots/create', methods=['POST'])
@login_required
@require_capability('equipment.manage')
def create_heat_lot():
    try:
        eid = request.form.get('equipment_id', type=int)
        eq = Equipment.query.get_or_404(eid)
        ok, msg = mes_service.equipment_available(eq)
        if not ok:
            flash(msg, 'danger')
            return redirect(url_for('main.manage_heat_lots'))
        layout = FurnaceLayout.query.filter_by(equipment_id=eq.id).first()
        lot = HeatLot(
            equipment_id=eq.id,
            layout_id=layout.id if layout else None,
            recipe_notes=request.form.get('recipe_notes'),
            operator_id=current_user.id,
            status='charging',
        )
        db.session.add(lot)
        db.session.commit()
        flash('炉次已创建，请装炉', 'success')
        return redirect(url_for('main.heat_lot_detail', id=lot.id))
    except HTTPException:
        raise
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'创建炉次失败: {e}')
        flash('创建失败', 'danger')
        return redirect(url_for('main.manage_heat_lots'))


@bp.route('/heat_lots/<int:id>')
@login_required
@require_capability('equipment.manage')
def heat_lot_detail(id):
    lot = HeatLot.query.get_or_404(id)
    cells = []
    if lot.layout:
        cells = lot.layout.cells.order_by(
            FurnaceLayoutCell.layer, FurnaceLayoutCell.row, FurnaceLayoutCell.col
        ).all()
    occupied = {(s.layer, s.row, s.col): s for s in lot.slots.all()}
    return render_template('main/equipment/heat_lot_detail.html', lot=lot, cells=cells, occupied=occupied)


@bp.route('/heat_lots/<int:id>/charge', methods=['POST'])
@login_required
@require_capability('equipment.manage')
@csrf.exempt
def heat_lot_charge(id):
    try:
        lot = HeatLot.query.get_or_404(id)
        if lot.status != 'charging':
            return jsonify({'success': False, 'message': '当前炉次不可装炉'}), 400
        data = request.get_json() or request.form
        code = (data.get('code') or '').strip()
        layer = int(data.get('layer') or 1)
        row = int(data.get('row') or 0)
        col = int(data.get('col') or 0)
        if not code or not row or not col:
            return jsonify({'success': False, 'message': '必须提供工件编码和炉位坐标'}), 400
        if HeatLotSlot.query.filter_by(heat_lot_id=lot.id, layer=layer, row=row, col=col).first():
            return jsonify({'success': False, 'message': '该炉位已占用'}), 400
        rm = RawMaterial.query.filter_by(internal_number=code).first()
        item = ProductionBatchItem.query.filter_by(product_code=code).first()
        product_id = None
        if item and item.batch and item.batch.production_order:
            product_id = item.batch.production_order.product_id
        wp = mes_service.ensure_workpiece(
            code=code,
            raw_material_id=rm.id if rm else None,
            batch_item_id=item.id if item else None,
            product_id=product_id,
            status='charging',
        )
        wp.status = 'charging'
        slot = HeatLotSlot(
            heat_lot_id=lot.id, workpiece_id=wp.id, layer=layer, row=row, col=col,
            bundle_code=data.get('bundle_code'),
        )
        db.session.add(slot)
        mes_service.log_event(
            wp, 'charged', heat_lot_id=lot.id, equipment_id=lot.equipment_id,
            payload={'layer': layer, 'row': row, 'col': col},
        )
        db.session.commit()
        return jsonify({'success': True, 'message': '已装炉', 'workpiece_id': wp.id})
    except HTTPException:
        raise
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'装炉失败: {e}')
        return jsonify({'success': False, 'message': str(e)}), 500


@bp.route('/heat_lots/<int:id>/fire', methods=['POST'])
@login_required
@require_capability('equipment.manage')
def heat_lot_fire(id):
    try:
        lot = HeatLot.query.get_or_404(id)
        if lot.slots.count() < 1:
            flash('空炉不能开炉', 'danger')
            return redirect(url_for('main.heat_lot_detail', id=lot.id))
        lot.status = 'firing'
        lot.started_at = datetime.utcnow()
        db.session.commit()
        flash('已开炉', 'success')
    except HTTPException:
        raise
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'开炉失败: {e}')
        flash('操作失败', 'danger')
    return redirect(url_for('main.heat_lot_detail', id=id))


@bp.route('/heat_lots/<int:id>/unload', methods=['POST'])
@login_required
@require_capability('equipment.manage')
def heat_lot_unload(id):
    try:
        lot = HeatLot.query.get_or_404(id)
        lot.status = 'unloaded'
        lot.ended_at = datetime.utcnow()
        for slot in lot.slots.all():
            mes_service.log_event(slot.workpiece, 'unloaded', heat_lot_id=lot.id,
                                  equipment_id=lot.equipment_id)
        task = mes_service.create_inspection_task('heat_lot', lot.id, notes=f'炉次 {lot.global_sn} 出炉质检')
        lot.inspection_task_id = task.id
        db.session.commit()
        flash('已出炉并生成煅烧质检任务', 'success')
    except HTTPException:
        raise
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'出炉失败: {e}')
        flash('操作失败', 'danger')
    return redirect(url_for('main.heat_lot_detail', id=id))


@bp.route('/workpieces')
@login_required
@require_capability('equipment.manage', 'production_order.view')
def manage_workpieces():
    search = (request.args.get('search') or '').strip()
    q = Workpiece.query
    if search:
        q = q.filter(Workpiece.code.ilike(f'%{search}%'))
    items = q.order_by(Workpiece.id.desc()).limit(200).all()
    return render_template('main/equipment/workpieces.html', items=items, search=search)


@bp.route('/workpieces/<int:id>')
@login_required
@require_capability('equipment.manage', 'production_order.view', 'quality.view')
def workpiece_detail(id):
    wp = Workpiece.query.get_or_404(id)
    events = wp.events.order_by(WorkpieceEvent.at.desc()).all()
    return render_template('main/equipment/workpiece_detail.html', wp=wp, events=events)
