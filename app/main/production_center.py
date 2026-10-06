from flask import render_template, request, jsonify, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from app import db, csrf
from app.permissions import require_capability
from . import bp
from sqlalchemy import or_, and_
from datetime import datetime, date

from app.models import (
    Product, ProductionOrder, ProductionBatch, ProductionBatchItem,
    TaskAssignment, ProcessPrice, Employee, ProductionRecord, ProductionRecordMaterial,
    SerialNumber, AuditLog
)


@bp.route('/production_center', methods=['GET'])
@login_required
@require_capability('production_center.use')
def production_center():
    """生产中心首页（以产品实例为中心的视图）"""

    # 查询参数
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    if per_page not in [20, 50, 100]:
        per_page = 20
    search = (request.args.get('search') or '').strip()
    status = (request.args.get('status') or '').strip()

    # 基础查询：按实例（ProductionBatchItem）
    query = db.session.query(ProductionBatchItem).join(ProductionBatch).join(ProductionOrder)

    if search:
        like = f"%{search}%"
        query = query.filter(or_(
            ProductionBatchItem.product_code.like(like),
            ProductionOrder.order_number.like(like)
        ))

    if status:
        query = query.filter(ProductionBatchItem.status == status)

    query = query.order_by(ProductionBatchItem.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    items = pagination.items

    return render_template(
        'main/production_center.html',
        items=items,
        pagination=pagination,
        current_status=status,
        search=search
    )


@bp.route('/production_center/items/<int:item_id>', methods=['GET'])
@login_required
@require_capability('production_center.use')
def production_center_item_detail(item_id: int):
    """实例详情页：展示该成品实例的工序、进度与执行记录"""

    item = ProductionBatchItem.query.get_or_404(item_id)

    # 关联任务：优先按 batch_item_id，其次包含批次级任务（production_batch_id）
    tasks = TaskAssignment.query.filter(
        db.or_(
            TaskAssignment.batch_item_id == item.id,
            TaskAssignment.production_batch_id == item.batch_id
        )
    ).order_by(TaskAssignment.target_date.asc()).all()

    # 关联执行记录（通过 notes 中的 batch_item_id 软关联）
    # 说明：为保持兼容性，不新增字段，使用 notes JSON 标记 {"batch_item_id": <id>}
    like_flag = f'"batch_item_id": {item.id}'
    records = ProductionRecord.query.filter(ProductionRecord.notes.contains(like_flag))\
        .order_by(ProductionRecord.date.desc(), ProductionRecord.id.desc()).all()

    return render_template(
        'main/production_center_item.html',
        item=item,
        tasks=tasks,
        records=records
    )


# ------------------- JSON API（前缀 /api/...） -------------------

@bp.route('/api/production_center/create_instances', methods=['POST'])
@login_required
@require_capability('production_center.use')
@csrf.exempt
def api_create_instances():
    """使用生产订单数据创建成品实例（生成批次与批次项）"""

    try:
        data = request.get_json() or {}
        order_id = data.get('production_order_id')
        batch_quantity = int(data.get('quantity') or 0)
        notes = (data.get('notes') or '').strip()

        if not order_id or batch_quantity <= 0:
            return jsonify({'success': False, 'message': '参数无效：缺少订单或数量不正确'}), 400

        order = ProductionOrder.query.get_or_404(order_id)

        # 创建批次并继承规格信息（校验可下达余量）
        remaining_schedulable = order.remaining_to_schedule if hasattr(order, 'remaining_to_schedule') else order.remaining_quantity
        if batch_quantity > remaining_schedulable:
            return jsonify({'success': False, 'message': f'批次数量不能超过剩余可下达数量({remaining_schedulable})'}), 400

        batch = ProductionBatch(
            production_order_id=order.id,
            batch_quantity=batch_quantity,
            status='pending',
            start_date=None,
            end_date=None,
            notes=notes,
            spec_extended=order.spec_extended,
            spec_gasket=order.spec_gasket,
            spec_joint=order.spec_joint,
            spec_drilling=order.spec_drilling,
            spec_other=order.spec_other,
            spec_other_desc=order.spec_other_desc,
            direction=order.direction
        )
        db.session.add(batch)
        db.session.flush()

        # 生成实例（批次项）
        ok = batch.generate_product_codes()
        if not ok:
            db.session.rollback()
            return jsonify({'success': False, 'message': '生成产品编码失败：编码规则未配置或生成异常'}), 400

        # 审计日志
        log = AuditLog(
            user_id=current_user.id,
            action='创建生产中心实例',
            details=f'订单 {order.order_number} 创建批次 {batch.batch_number}，数量 {batch_quantity}',
            can_rollback=True,
            rollback_type='add',
            target_model='ProductionBatch',
            target_id=batch.id,
            new_data={'production_order_id': order_id, 'batch_quantity': batch_quantity}
        )
        db.session.add(log)

        db.session.commit()

        # 返回创建的批次与批次项
        items = ProductionBatchItem.query.filter_by(batch_id=batch.id).order_by(ProductionBatchItem.item_sequence).all()
        return jsonify({
            'success': True,
            'message': '创建成功',
            'data': {
                'batch': {
                    'id': batch.id,
                    'batch_number': batch.batch_number,
                    'status': batch.status,
                },
                'items': [{'id': i.id, 'product_code': i.product_code, 'status': i.status} for i in items]
            }
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'创建生产中心实例失败: {str(e)}')
        return jsonify({'success': False, 'message': f'创建失败：{str(e)}'}), 500


@bp.route('/api/production_center/items/<int:item_id>/tech_decomposition', methods=['POST'])
@login_required
@require_capability('production_center.use')
@csrf.exempt
def api_save_tech_decomposition(item_id: int):
    """保存实例级技术拆解（存入 notes JSON，不改动表结构）"""

    try:
        item = ProductionBatchItem.query.get_or_404(item_id)
        payload = request.get_json() or {}

        # 以 JSON 形式写入 notes，遵循 {"decomposition": {...}} 约定
        # 若原 notes 有内容，保留其他信息，仅替换/合并 decomposition 字段
        import json as _json
        existing = {}
        try:
            if item.notes:
                existing = _json.loads(item.notes)
                if not isinstance(existing, dict):
                    existing = {}
        except Exception:
            existing = {}

        existing['decomposition'] = payload
        existing['batch_item_id'] = item.id

        item.notes = _json.dumps(existing, ensure_ascii=False)

        log = AuditLog(
            user_id=current_user.id,
            action='保存技术拆解',
            details=f'批次项 {item.product_code} 技术拆解更新',
            can_rollback=True,
            rollback_type='edit',
            target_model='ProductionBatchItem',
            target_id=item.id,
            new_data=payload
        )
        db.session.add(log)
        db.session.commit()

        return jsonify({'success': True, 'message': '保存成功'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'保存技术拆解失败: {str(e)}')
        return jsonify({'success': False, 'message': f'保存失败：{str(e)}'}), 500


@bp.route('/api/production_center/items/<int:item_id>/detail', methods=['GET'])
@login_required
@require_capability('production_center.use')
def api_item_detail(item_id: int):
    """实例级详情（用于前端可视化）：基本信息、任务、执行记录与物料消耗"""

    try:
        item = ProductionBatchItem.query.get_or_404(item_id)

        # 任务
        tasks = TaskAssignment.query.filter(TaskAssignment.batch_item_id == item.id).all()

        # 执行记录（通过 notes 中的 batch_item_id 匹配）
        like_flag = f'"batch_item_id": {item.id}'
        records = ProductionRecord.query.filter(ProductionRecord.notes.contains(like_flag)).all()

        def _task_dict(t: TaskAssignment):
            return {
                'id': t.id,
                'process_id': t.process_id,
                'process_name': t.process.process_name if t.process else None,
                'quantity': t.quantity,
                'completed_quantity': t.completed_quantity,
                'status': t.status,
                'target_date': t.target_date.strftime('%Y-%m-%d') if t.target_date else None
            }

        def _record_dict(r: ProductionRecord):
            mats = [
                {
                    'raw_material_id': m.raw_material_id,
                    'quantity': m.quantity
                } for m in r.materials
            ]
            return {
                'id': r.id,
                'global_sn': r.global_sn,
                'employee_id': r.employee_id,
                'employee_name': r.employee.name if r.employee else None,
                'process_id': r.process_id,
                'process_name': r.process.process_name if r.process else None,
                'quantity': r.quantity,
                'date': r.date.strftime('%Y-%m-%d'),
                'materials': mats,
                'notes': r.notes or ''
            }

        # 解析技术拆解（notes JSON）
        import json as _json
        deco = None
        try:
            if item.notes:
                parsed = _json.loads(item.notes)
                if isinstance(parsed, dict):
                    deco = parsed.get('decomposition')
        except Exception:
            deco = None

        return jsonify({
            'success': True,
            'data': {
                'item': {
                    'id': item.id,
                    'product_code': item.product_code,
                    'status': item.status,
                    'quality_status': item.quality_status,
                    'notes': item.notes or ''
                },
                'tasks': [_task_dict(t) for t in tasks],
                'records': [_record_dict(r) for r in records],
                'tech_decomposition': deco
            }
        })
    except Exception as e:
        current_app.logger.error(f'获取实例详情失败: {str(e)}')
        return jsonify({'success': False, 'message': f'获取失败：{str(e)}'}), 500


@bp.route('/api/production_center/items/<int:item_id>/execute_operation', methods=['POST'])
@login_required
@require_capability('production_center.use')
@csrf.exempt
def api_execute_operation(item_id: int):
    """记录工序执行（操作者与物料消耗），并更新相关任务进度"""

    try:
        item = ProductionBatchItem.query.get_or_404(item_id)
        data = request.get_json() or {}

        employee_id = data.get('employee_id')
        process_id = data.get('process_id')
        quantity = int(data.get('quantity') or 0)
        record_date = data.get('date')  # YYYY-MM-DD
        materials = data.get('materials') or []  # [{raw_material_id, quantity}]

        if not employee_id or not process_id or quantity <= 0:
            return jsonify({'success': False, 'message': '参数无效：缺少员工/工序或数量不正确'}), 400

        exec_date = datetime.strptime(record_date, '%Y-%m-%d').date() if record_date else date.today()

        # 创建生产记录，并在 notes 中写入 batch_item_id 软关联
        import json as _json
        record_notes = _json.dumps({'batch_item_id': item.id}, ensure_ascii=False)

        prod_record = ProductionRecord(
            global_sn=SerialNumber.get_next_number(),
            employee_id=employee_id,
            process_id=process_id,
            quantity=quantity,
            date=exec_date,
            notes=record_notes
        )
        db.session.add(prod_record)
        db.session.flush()

        # 记录物料消耗
        for m in materials:
            try:
                rm_id = int(m.get('raw_material_id'))
                rm_qty = float(m.get('quantity'))
            except Exception:
                continue
            if rm_id and rm_qty and rm_qty > 0:
                pr_m = ProductionRecordMaterial(
                    production_record_id=prod_record.id,
                    raw_material_id=rm_id,
                    quantity=rm_qty
                )
                db.session.add(pr_m)

        # 如果存在与该实例和工序匹配的任务，则同步进度
        # 优先匹配实例级任务；若无则回退匹配批次级任务
        task = TaskAssignment.query.filter(
            and_(TaskAssignment.batch_item_id == item.id, TaskAssignment.process_id == process_id)
        ).first()
        if not task:
            task = TaskAssignment.query.filter(
                and_(TaskAssignment.production_batch_id == item.batch_id, TaskAssignment.process_id == process_id)
            ).first()
        if task:
            task.completed_quantity = (task.completed_quantity or 0) + quantity
            if task.completed_quantity >= task.quantity:
                task.status = 'completed'
            elif task.completed_quantity > 0:
                task.status = 'in_progress'

        # 审计日志
        log = AuditLog(
            user_id=current_user.id,
            action='记录工序执行',
            details=f'实例 {item.product_code} 执行工序，记录 {prod_record.global_sn}',
            can_rollback=True,
            rollback_type='add',
            target_model='ProductionRecord',
            target_id=prod_record.id,
            new_data=data
        )
        db.session.add(log)

        db.session.commit()
        return jsonify({'success': True, 'message': '记录成功', 'data': {'record_id': prod_record.id}})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'记录工序执行失败: {str(e)}')
        return jsonify({'success': False, 'message': f'记录失败：{str(e)}'}), 500


@bp.route('/api/production/generate-codes', methods=['POST'])
@login_required
@require_capability('production_center.use')
def generate_batch_product_codes():
    """为指定生产批次补生成产品编码。

    前端入口：main/production_batch_detail.html 的「生成产品编码」按钮。
    复用 ProductionBatch.generate_product_codes()，不另写编码规则逻辑。
    幂等：该方法每次都无条件插入批次项，因此已有批次项时直接返回、不重复生成。
    """
    try:
        payload = request.get_json(silent=True) or request.form or {}
        raw_id = payload.get('batch_id') or payload.get('id')
        if raw_id in (None, ''):
            return jsonify({'success': False, 'message': '缺少批次 id'}), 400
        try:
            batch_id = int(raw_id)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'message': '批次 id 必须是整数'}), 400

        batch = ProductionBatch.query.get(batch_id)
        if batch is None:
            return jsonify({'success': False, 'message': f'批次 {batch_id} 不存在'}), 404

        existing = ProductionBatchItem.query.filter_by(batch_id=batch.id).order_by(
            ProductionBatchItem.item_sequence).all()
        if existing:
            return jsonify({
                'success': True,
                'message': f'该批次已有 {len(existing)} 条产品编码，未重复生成',
                'data': [{'id': it.id, 'product_code': it.product_code} for it in existing],
            })

        if not batch.generate_product_codes():
            db.session.rollback()
            return jsonify({
                'success': False,
                'message': '生成产品编码失败：产品的编码规则未配置或生成异常',
            }), 400
        db.session.commit()

        items = ProductionBatchItem.query.filter_by(batch_id=batch.id).order_by(
            ProductionBatchItem.item_sequence).all()
        return jsonify({
            'success': True,
            'message': f'已生成 {len(items)} 条产品编码',
            'data': [{'id': it.id, 'product_code': it.product_code} for it in items],
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'生成批次产品编码失败: {str(e)}')
        return jsonify({'success': False, 'message': f'生成失败：{str(e)}'}), 500


