from flask import render_template, redirect, url_for, flash, request, jsonify, current_app, send_file
from flask_login import login_required, current_user
from app import db, csrf
from app.models import (
    InspectionTemplate, InspectionBaseItem, InspectionItem,
    InspectionTask, InspectionRecord, InspectionBaseItemRecord, 
    InspectionItemRecord, NonconformityRecord, AuditLog, User, Employee,
    SerialNumber, ProcessPrice, FinishedProduct, RawMaterial, ProductionRecord
)
from app.permissions import require_capability
from datetime import datetime, timedelta
from . import bp

# 分页白名单：与全站 handle_pagination_args（app/main/routes.py）的 per_page 口径逐值一致
# （非数字 / 不在白名单 → 20）。这三个端点是 JSON API，且 routes.py 不在本模块的可改范围内，
# 故在本地按同一口径校验，不引入会 flash 的装饰器。
PAGE_SIZE_WHITELIST = (20, 50, 100)


def _validated_per_page(default=20):
    """从查询串取 per_page 并按白名单回落（缺省/非数字/不在 (20,50,100) → default）。"""
    raw = request.args.get('per_page', default)
    try:
        per_page = int(raw)
    except (TypeError, ValueError):
        return default
    return per_page if per_page in PAGE_SIZE_WHITELIST else default

@bp.route('/quality')
@login_required
@require_capability('quality.view')
def quality_management():
    """质量管理主页"""
    
    # 获取质检任务统计信息
    query = InspectionTask.query
    if current_user.role == 'inspector':
        query = query.filter(InspectionTask.inspector_id == current_user.id)
    
    inspection_tasks_pending = query.filter(InspectionTask.status == 'pending').count()
    inspection_tasks_completed = query.filter(InspectionTask.status == 'completed').count()
    templates_count = InspectionTemplate.query.filter_by(is_active=True).count()
    
    return render_template('main/quality/index.html',
                         inspection_tasks_pending=inspection_tasks_pending,
                         inspection_tasks_completed=inspection_tasks_completed,
                         templates_count=templates_count)

@bp.route('/quality/templates', methods=['GET'])
@login_required
@require_capability('quality.template.manage')
def quality_templates():
    """质检模板列表"""
    
    return render_template('main/quality/templates.html')

@bp.route('/quality/tasks', methods=['GET'])
@login_required
@require_capability('quality.view')
def quality_tasks():
    """质检任务列表"""
    
    return render_template('main/quality/tasks.html')

@bp.route('/quality/records', methods=['GET'])
@login_required
@require_capability('quality.view')
def quality_records():
    """质检记录列表"""
    
    # 获取质检任务统计信息
    query = InspectionTask.query
    if current_user.role == 'inspector':
        query = query.filter(InspectionTask.inspector_id == current_user.id)
    
    inspection_tasks_pending = query.filter(InspectionTask.status == 'pending').count()
    inspection_tasks_completed = query.filter(InspectionTask.status == 'completed').count()
    templates_count = InspectionTemplate.query.filter_by(is_active=True).count()
    
    return render_template('main/quality/records.html',
                         inspection_tasks_pending=inspection_tasks_pending,
                         inspection_tasks_completed=inspection_tasks_completed,
                         templates_count=templates_count)

@bp.route('/quality/tasks/<int:task_id>')
@login_required
@require_capability('quality.view')
def quality_task_detail(task_id):
    """质检任务详情页面"""
    
    # 获取质检任务
    task = InspectionTask.query.get_or_404(task_id)
    
    # 检查权限
    if current_user.role == 'inspector' and task.inspector_id != current_user.id:
        flash('只能查看分配给自己的质检任务', 'danger')
        return redirect(url_for('main.quality_tasks'))
    
    return render_template('main/quality/task_detail.html', task=task)

@bp.route('/quality/inspection/<int:record_id>')
@login_required
@require_capability('quality.view')
def quality_inspection(record_id):
    """质检执行页面"""
    
    # 获取质检记录
    record = InspectionRecord.query.get_or_404(record_id)
    
    # 检查权限
    if current_user.role == 'inspector' and record.inspector_id != current_user.id:
        flash('只能执行分配给自己的质检任务', 'danger')
        return redirect(url_for('main.quality_tasks'))
    
    return render_template('main/quality/inspection.html', record=record)

# API路由
@bp.route('/api/quality/templates', methods=['GET'])
@login_required
@require_capability('quality.view')
def get_templates():
    """获取质检模板列表"""
    page = request.args.get('page', 1, type=int)
    per_page = _validated_per_page()
    search = request.args.get('search', '')
    template_type = request.args.get('type', '')
    is_active = request.args.get('is_active', None, type=lambda x: x.lower() == 'true' if x else None)

    # 构建查询
    query = InspectionTemplate.query

    # 应用过滤条件
    if search:
        query = query.filter(db.or_(
            InspectionTemplate.template_code.like(f'%{search}%'),
            InspectionTemplate.name.like(f'%{search}%'),
            InspectionTemplate.description.like(f'%{search}%')
        ))
    if template_type:
        query = query.filter(InspectionTemplate.type == template_type)
    if is_active is not None:
        query = query.filter(InspectionTemplate.is_active == is_active)

    # 排序
    query = query.order_by(InspectionTemplate.created_at.desc())

    # 分页
    pagination = query.paginate(page=page, per_page=per_page)
    templates = pagination.items

    # 构建响应数据
    return jsonify({
        'success': True,
        'data': {
            'items': [{
                'id': t.id,
                'template_code': t.template_code,
                'name': t.name,
                'type': t.type,
                'description': t.description,
                'is_active': t.is_active,
                'created_at': t.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'base_items_count': t.base_items.count(),
                'items_count': t.items.count()
            } for t in templates],
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
            'pages': pagination.pages
        }
    })

@bp.route('/api/quality/templates/<int:template_id>', methods=['GET'])
@login_required
@require_capability('quality.template.manage')
def get_template_detail(template_id):
    """获取质检模板详情"""
    template = InspectionTemplate.query.get_or_404(template_id)
    
    return jsonify({
        'success': True,
        'data': {
            'id': template.id,
            'template_code': template.template_code,
            'name': template.name,
            'type': template.type,
            'description': template.description,
            'is_active': template.is_active,
            'created_at': template.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'base_items': [{
                'id': item.id,
                'name': item.name,
                'description': item.description,
                'notes': item.notes,
                'input_type': item.input_type,
                'default_value': item.default_value,
                'options': item.options,
                'is_required': item.is_required,
                'validation_rules': item.validation_rules,
                'order_num': item.order_num
            } for item in template.base_items.order_by(InspectionBaseItem.order_num)],
            'items': [{
                'id': item.id,
                'name': item.name,
                'description': item.description,
                'notes': item.notes,
                'inspection_method': item.inspection_method,
                'standard': item.standard,
                'standard_value': item.standard_value,
                'linked_base_item_id': item.linked_base_item_id,
                'use_linked_value': item.use_linked_value,
                'value_extraction_rule': item.value_extraction_rule,
                'deviation_type': item.deviation_type,
                'upper_deviation_value': item.upper_deviation_value,
                'lower_deviation_value': item.lower_deviation_value,
                'upper_deviation_percentage': item.upper_deviation_percentage,
                'lower_deviation_percentage': item.lower_deviation_percentage,
                'unit': item.unit,
                'order_num': item.order_num
            } for item in template.items.order_by(InspectionItem.order_num)]
        }
    })

@bp.route('/api/quality/templates', methods=['POST'])
@login_required
@require_capability('quality.template.manage')
@csrf.exempt  # 对API请求豁免CSRF保护
def create_template():
    """创建质检模板"""

    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': '请求数据为空'}), 400
            
        # 验证必需字段
        required_fields = ['template_code', 'name', 'type']
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify({
                'success': False,
                'message': f'缺少必需字段：{", ".join(missing_fields)}'
            }), 400
        
        # 检查模板代码是否已存在
        if InspectionTemplate.query.filter_by(template_code=data['template_code']).first():
            return jsonify({
                'success': False,
                'message': '模板代码已存在'
            }), 400
        
        # 创建模板
        template = InspectionTemplate(
            template_code=data['template_code'],
            name=data['name'],
            type=data['type'],
            description=data.get('description', ''),
            is_active=data.get('is_active', True),
            created_by=current_user.id
        )
        db.session.add(template)
        db.session.flush()  # 获取template.id

        # 创建基本信息项目
        for item_data in data.get('base_items', []):
            base_item = InspectionBaseItem(
                template_id=template.id,
                name=item_data['name'],
                description=item_data.get('description', ''),
                notes=item_data.get('notes', ''),
                input_type=item_data['input_type'],
                default_value=item_data.get('default_value', ''),
                options=item_data.get('options', None),
                is_required=item_data.get('is_required', True),
                validation_rules=item_data.get('validation_rules', None),
                order_num=item_data.get('order_num', 0)
            )
            db.session.add(base_item)

        # 创建检验项目
        for item_data in data.get('items', []):
            item = InspectionItem(
                template_id=template.id,
                name=item_data['name'],
                description=item_data.get('description', ''),
                notes=item_data.get('notes', ''),
                inspection_method=item_data.get('inspection_method', ''),
                standard=item_data.get('standard', ''),
                standard_value=item_data.get('standard_value'),
                linked_base_item_id=item_data.get('linked_base_item_id'),
                use_linked_value=item_data.get('use_linked_value', False),
                value_extraction_rule=item_data.get('value_extraction_rule'),
                deviation_type=item_data.get('deviation_type'),
                upper_deviation_value=item_data.get('upper_deviation_value'),
                lower_deviation_value=item_data.get('lower_deviation_value'),
                upper_deviation_percentage=item_data.get('upper_deviation_percentage'),
                lower_deviation_percentage=item_data.get('lower_deviation_percentage'),
                unit=item_data.get('unit', ''),
                order_num=item_data.get('order_num', 0)
            )
            db.session.add(item)

        # 记录审计日志
        log = AuditLog(
            user_id=current_user.id,
            action='创建质检模板',
            details=f'创建质检模板：{template.name}',
            can_rollback=True,
            rollback_type='add',
            target_model='InspectionTemplate',
            target_id=template.id,
            new_data=data
        )
        db.session.add(log)

        db.session.commit()
        return jsonify({
            'success': True,
            'message': '模板创建成功',
            'data': {'id': template.id}
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'创建质检模板失败: {str(e)}')
        return jsonify({'success': False, 'message': f'创建失败：{str(e)}'}), 500

@bp.route('/api/quality/templates/<int:template_id>', methods=['PUT', 'DELETE'])
@login_required
@require_capability('quality.template.manage')
@csrf.exempt
def manage_template(template_id):
    """管理质检模板（更新/删除）"""

    try:
        template = InspectionTemplate.query.get_or_404(template_id)
        
        if request.method == 'DELETE':
            # 检查是否有关联的质检任务
            if template.tasks.count() > 0:
                return jsonify({
                    'success': False,
                    'message': '该模板已被质检任务使用，无法删除'
                }), 400
                
            # 保存旧数据用于审计日志
            old_data = {
                'template_code': template.template_code,
                'name': template.name,
                'type': template.type,
                'description': template.description,
                'is_active': template.is_active,
                'base_items': [{
                    'id': item.id,
                    'name': item.name,
                    'description': item.description,
                    'input_type': item.input_type,
                    'order_num': item.order_num
                } for item in template.base_items],
                'items': [{
                    'id': item.id,
                    'name': item.name,
                    'description': item.description,
                    'standard': item.standard
                } for item in template.items]
            }
            
            # 删除关联的检验项目
            template.items.delete()
            
            # 删除关联的基本信息项目
            template.base_items.delete()
            
            # 删除模板本身
            db.session.delete(template)
            
            # 记录审计日志
            log = AuditLog(
                user_id=current_user.id,
                action='删除质检模板',
                details=f'删除质检模板：{template.name}',
                can_rollback=True,
                rollback_type='delete',
                target_model='InspectionTemplate',
                target_id=template_id,
                old_data=old_data
            )
            db.session.add(log)
            
            db.session.commit()
            return jsonify({
                'success': True,
                'message': '模板删除成功'
            })
        else:  # PUT
            data = request.get_json()

            # 保存旧数据用于审计日志
            old_data = {
                'template_code': template.template_code,
                'name': template.name,
                'type': template.type,
                'description': template.description,
                'is_active': template.is_active
            }

            # 更新模板基本信息
            template.template_code = data['template_code']
            template.name = data['name']
            template.type = data['type']
            template.description = data.get('description', '')
            template.is_active = data.get('is_active', True)

            # 更新基本信息项目
            if 'base_items' in data:
                # 删除旧的基本信息项目
                template.base_items.delete()
                
                # 创建新的基本信息项目
                for item_data in data['base_items']:
                    base_item = InspectionBaseItem(
                        template_id=template.id,
                        name=item_data['name'],
                        description=item_data.get('description', ''),
                        notes=item_data.get('notes', ''),
                        input_type=item_data['input_type'],
                        default_value=item_data.get('default_value', ''),
                        options=item_data.get('options', None),
                        is_required=item_data.get('is_required', True),
                        validation_rules=item_data.get('validation_rules', None),
                        order_num=item_data.get('order_num', 0)
                    )
                    db.session.add(base_item)

            # 更新检验项目
            if 'items' in data:
                # 删除旧的检验项目
                template.items.delete()
                
                # 创建新的检验项目
                for item_data in data['items']:
                    item = InspectionItem(
                        template_id=template.id,
                        name=item_data['name'],
                        description=item_data.get('description', ''),
                        notes=item_data.get('notes', ''),
                        inspection_method=item_data.get('inspection_method', ''),
                        standard=item_data.get('standard', ''),
                        standard_value=item_data.get('standard_value'),
                        linked_base_item_id=item_data.get('linked_base_item_id'),
                        use_linked_value=item_data.get('use_linked_value', False),
                        value_extraction_rule=item_data.get('value_extraction_rule'),
                        deviation_type=item_data.get('deviation_type'),
                        upper_deviation_value=item_data.get('upper_deviation_value'),
                        lower_deviation_value=item_data.get('lower_deviation_value'),
                        upper_deviation_percentage=item_data.get('upper_deviation_percentage'),
                        lower_deviation_percentage=item_data.get('lower_deviation_percentage'),
                        unit=item_data.get('unit', ''),
                        order_num=item_data.get('order_num', 0)
                    )
                    db.session.add(item)

            # 记录审计日志
            log = AuditLog(
                user_id=current_user.id,
                action='更新质检模板',
                details=f'更新质检模板：{template.name}',
                can_rollback=True,
                rollback_type='edit',
                target_model='InspectionTemplate',
                target_id=template.id,
                old_data=old_data,
                new_data=data
            )
            db.session.add(log)

            db.session.commit()
            return jsonify({
                'success': True,
                'message': '模板更新成功'
            })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'管理质检模板失败: {str(e)}')
        return jsonify({'success': False, 'message': f'操作失败：{str(e)}'}), 500

@bp.route('/api/quality/tasks', methods=['GET'])
@login_required
@require_capability('quality.view')
def get_tasks():
    """获取质检任务列表"""
    page = request.args.get('page', 1, type=int)
    per_page = _validated_per_page()
    search = request.args.get('search', '')
    task_type = request.args.get('type', '')
    status = request.args.get('status', '')

    # 构建查询
    query = InspectionTask.query

    # 应用过滤条件
    if search:
        query = query.join(InspectionTemplate).filter(db.or_(
            InspectionTask.global_sn.like(f'%{search}%'),
            InspectionTemplate.name.like(f'%{search}%')
        ))
    if task_type:
        query = query.filter(InspectionTask.target_type == task_type)
    if status:
        query = query.filter(InspectionTask.status == status)

    # 根据角色过滤
    if current_user.role == 'inspector':
        query = query.filter(InspectionTask.inspector_id == current_user.id)

    # 排序
    query = query.order_by(InspectionTask.created_at.desc())

    # 分页
    pagination = query.paginate(page=page, per_page=per_page)
    tasks = pagination.items

    # 构建响应数据
    return jsonify({
        'success': True,
        'data': {
            'items': [{
                'id': t.id,
                'task_code': t.global_sn,
                'type': t.target_type,
                'inspection_target': get_inspection_target_name(t),
                'inspector_name': (t.inspector.employee.name if t.inspector and t.inspector.employee else 
                                 t.inspector.username if t.inspector else '未分配'),
                'created_at': t.created_at.strftime('%Y-%m-%d %H:%M'),
                'planned_completion_time': t.deadline.strftime('%Y-%m-%d %H:%M') if t.deadline else None,
                'status': t.status
            } for t in tasks],
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
            'pages': pagination.pages
        }
    })

@bp.route('/api/quality/tasks/<int:task_id>', methods=['GET'])
@login_required
@require_capability('quality.view')
def get_task_detail(task_id):
    """获取质检任务详情"""
    task = InspectionTask.query.get_or_404(task_id)
    
    return jsonify({
        'success': True,
        'data': {
            'id': task.id,
            'task_code': task.global_sn,
            'template_id': task.template_id,
            'type': task.target_type,
            'target_id': task.target_id,
            'inspector_id': task.inspector_id,
            'inspection_target': get_inspection_target_name(task),
            'inspector_name': (task.inspector.employee.name if task.inspector and task.inspector.employee else 
                             task.inspector.username if task.inspector else '未分配'),
            'status': task.status,
            'priority': task.priority,
            'planned_completion_time': task.deadline.strftime('%Y-%m-%dT%H:%M') if task.deadline else None,
            'notes': task.notes or '',
            'created_at': task.created_at.strftime('%Y-%m-%d %H:%M'),
            'completed_at': task.completed_at.strftime('%Y-%m-%d %H:%M') if task.completed_at else None
        }
    })

@bp.route('/api/quality/tasks', methods=['POST'])
@login_required
@require_capability('quality.task.manage')
@csrf.exempt  # 对API请求豁免CSRF保护
def create_task():
    """创建质检任务"""

    try:
        data = request.get_json()
        
        # 创建任务
        task = InspectionTask(
            global_sn=SerialNumber.get_next_number(),
            template_id=data.get('template_id'),  # 模板ID现在是可选的
            target_type=data['type'],
            target_id=data['inspection_target_id'],
            inspector_id=data['inspector_id'],
            priority=int(data.get('priority', 1)),  # 直接使用数字优先级
            deadline=datetime.strptime(data['planned_completion_time'], '%Y-%m-%dT%H:%M') if data.get('planned_completion_time') else None,
            notes=data.get('notes', ''),
            created_by=current_user.id,
            status='pending'
        )
        db.session.add(task)

        # 记录审计日志
        log = AuditLog(
            user_id=current_user.id,
            action='创建质检任务',
            details=f'创建质检任务：{task.global_sn}',
            can_rollback=True,
            rollback_type='add',
            target_model='InspectionTask',
            target_id=task.id,
            new_data=data
        )
        db.session.add(log)

        db.session.commit()
        return jsonify({
            'success': True,
            'message': '任务创建成功',
            'data': {'id': task.id}
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'创建质检任务失败: {str(e)}')
        return jsonify({'success': False, 'message': f'创建失败：{str(e)}'}), 500

@bp.route('/api/quality/tasks/<int:task_id>', methods=['PUT', 'DELETE'])
@login_required
@require_capability('quality.task.manage')
@csrf.exempt  # 对API请求豁免CSRF保护
def manage_task(task_id):
    """管理质检任务（更新/删除）"""

    if request.method == 'DELETE':
        return delete_inspection_task(task_id)
    else:
        return update_task(task_id)

@bp.route('/api/quality/inspectors', methods=['GET'])
@login_required
@require_capability('quality.view')
def get_inspectors():
    """获取质检员列表"""
    try:
        # 查询具有inspector角色或相关职位的用户
        inspectors = User.query.join(Employee).filter(
            db.or_(
                User.role.in_(['inspector', 'admin']),
                Employee.position.in_(['质检员', '管理员'])
            )
        ).all()
        
        return jsonify({
            'success': True,
            'inspectors': [{
                'id': inspector.id,
                'name': inspector.employee.name if inspector.employee else inspector.username,
                'employee_id': inspector.employee.employee_id if inspector.employee else None,
                'department': inspector.employee.department if inspector.employee else None
            } for inspector in inspectors]
        })
    except Exception as e:
        current_app.logger.error(f'获取质检员列表失败: {str(e)}')
        return jsonify({'success': False, 'message': f'获取质检员列表失败：{str(e)}'}), 500

@bp.route('/api/quality/processes', methods=['GET'])
@login_required
@require_capability('quality.view')
def get_processes():
    """获取工序列表"""
    try:
        # 获取当前有效的工序价格（最新版本）
        today = datetime.now().date()
        
        # 子查询：获取每个工序编号的最新有效日期
        latest_versions = db.session.query(
            ProcessPrice.process_code,
            db.func.max(ProcessPrice.effective_date).label('max_date')
        ).filter(ProcessPrice.effective_date <= today + timedelta(days=1))\
        .group_by(ProcessPrice.process_code)\
        .subquery()
        
        # 主查询：获取最新版本的工序
        processes = ProcessPrice.query.join(
            latest_versions,
            db.and_(
                ProcessPrice.process_code == latest_versions.c.process_code,
                ProcessPrice.effective_date == latest_versions.c.max_date
            )
        ).order_by(ProcessPrice.process_code).all()
        
        return jsonify({
            'success': True,
            'data': [{
                'id': process.id,
                'process_code': process.process_code,
                'process_name': process.process_name,
                'component': process.component,
                'drawing_no': process.drawing_no,
                'model_no': process.model_no,
                'price': process.price,
                'needs_inspection': process.needs_inspection
            } for process in processes]
        })
    except Exception as e:
        current_app.logger.error(f'获取工序列表失败: {str(e)}')
        return jsonify({'success': False, 'message': f'获取工序列表失败：{str(e)}'}), 500

@bp.route('/api/quality/finished-products', methods=['GET'])
@login_required
@require_capability('quality.view')
def get_finished_products():
    """获取成品列表"""
    try:
        # 获取未存档的成品（与发货路径同一口径：NULL 也视为「未存档」，避免历史行被漏掉）
        products = FinishedProduct.query.filter(
            db.or_(FinishedProduct.is_archived.is_(False), FinishedProduct.is_archived.is_(None))
        ).order_by(FinishedProduct.created_at.desc()).all()
        
        return jsonify({
            'success': True,
            'data': [{
                'id': product.id,
                'product_number': product.product_number,
                'drawing_number': product.drawing_number,
                'model': product.model,
                'production_date': product.production_date.strftime('%Y-%m-%d'),
                'inspector': product.inspector,
                'quantity': product.quantity,
                'status': product.status
            } for product in products]
        })
    except Exception as e:
        current_app.logger.error(f'获取成品列表失败: {str(e)}')
        return jsonify({'success': False, 'message': f'获取成品列表失败：{str(e)}'}), 500

@bp.route('/api/quality/production-records', methods=['GET'])
@login_required
@require_capability('quality.view')
def get_production_records():
    """获取生产记录列表"""
    try:
        # 获取最近的生产记录，按日期倒序排列
        records = ProductionRecord.query.join(Employee).join(ProcessPrice).order_by(
            ProductionRecord.date.desc(),
            ProductionRecord.id.desc()
        ).limit(200).all()  # 限制返回最近200条记录
        
        return jsonify({
            'success': True,
            'data': [{
                'id': record.id,
                'global_sn': record.global_sn,
                'employee_name': record.employee.name,
                'employee_id': record.employee.employee_id,
                'process_name': record.process.process_name,
                'process_code': record.process.process_code,
                'quantity': record.quantity,
                'date': record.date.strftime('%Y-%m-%d'),
                'notes': record.notes or '',
                'component': record.process.component or '',
                'drawing_no': record.process.drawing_no or ''
            } for record in records]
        })
    except Exception as e:
        current_app.logger.error(f'获取生产记录列表失败: {str(e)}')
        return jsonify({'success': False, 'message': f'获取生产记录列表失败：{str(e)}'}), 500

@bp.route('/api/quality/tasks/<int:task_id>/start-inspection', methods=['POST'])
@login_required
@require_capability('quality.inspect')
@csrf.exempt
def start_inspection(task_id):
    """开始质检任务"""
    try:
        task = InspectionTask.query.get_or_404(task_id)
        data = request.get_json()
        
        
        # 检查任务状态
        if task.status not in ['pending', 'in_progress']:
            status_names = {
                'pending': '待处理',
                'in_progress': '进行中', 
                'completed': '已完成',
                'cancelled': '已取消'
            }
            current_status = status_names.get(task.status, task.status)
            return jsonify({
                'success': False, 
                'message': f'任务状态不允许开始质检，当前状态：{current_status}。只有待处理或进行中的任务可以开始质检。'
            }), 400
        
        # 检查是否是指定的检验员
        if current_user.role == 'inspector' and task.inspector_id != current_user.id:
            return jsonify({'success': False, 'message': '只能执行分配给自己的质检任务'}), 403
        
        # 获取模板
        template_id = data.get('template_id')
        if not template_id:
            return jsonify({'success': False, 'message': '请选择质检模板'}), 400
        
        template = InspectionTemplate.query.get(template_id)
        if not template:
            return jsonify({'success': False, 'message': '质检模板不存在'}), 404
        
        if not template.is_active:
            return jsonify({'success': False, 'message': '质检模板已禁用'}), 400
        
        # 检查模板类型是否匹配
        if template.type != task.target_type:
            return jsonify({'success': False, 'message': '质检模板类型与任务类型不匹配'}), 400
        
        # 更新任务状态和模板
        task.status = 'in_progress'
        task.template_id = template_id
        
        # 检查是否已有质检记录
        existing_record = InspectionRecord.query.filter_by(task_id=task.id).first()
        if existing_record:
            # 如果已有记录，更新模板ID和备注
            existing_record.template_id = template_id
            existing_record.notes = data.get('notes', existing_record.notes)
            record = existing_record
        else:
            # 创建新的质检记录
            record = InspectionRecord(
                global_sn=SerialNumber.get_next_number(),
                task_id=task.id,
                template_id=template_id,
                inspector_id=current_user.id,
                inspection_date=datetime.now().date(),
                result='pending',  # 初始状态为待检验
                notes=data.get('notes', '')
            )
            db.session.add(record)
        
        # 记录审计日志
        log = AuditLog(
            user_id=current_user.id,
            action='开始质检任务',
            details=f'开始质检任务：{task.global_sn}，使用模板：{template.template_code}',
            can_rollback=False,
            target_model='InspectionTask',
            target_id=task.id,
            new_data={
                'template_id': template_id,
                'status': 'in_progress',
                'record_id': record.id
            }
        )
        db.session.add(log)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': '质检任务已开始',
            'record_id': record.id
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'开始质检任务失败: {str(e)}')
        return jsonify({'success': False, 'message': f'开始质检失败：{str(e)}'}), 500

@bp.route('/api/quality/records/<int:record_id>/submit', methods=['POST'])
@login_required
@require_capability('quality.inspect')
@csrf.exempt
def submit_inspection_record(record_id):
    """提交质检记录"""
    try:
        record = InspectionRecord.query.get_or_404(record_id)
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'message': '请求数据为空'}), 400
        
        
        # 检查是否是指定的检验员
        if current_user.role == 'inspector' and record.inspector_id != current_user.id:
            return jsonify({'success': False, 'message': '只能提交分配给自己的质检记录'}), 403
        
        # 验证必需字段
        if not data.get('result'):
            return jsonify({'success': False, 'message': '请选择检验结果'}), 400
        
        # 更新质检记录
        record.result = data.get('result')
        record.notes = data.get('notes', '')
        
        # 保存基本信息项目记录
        base_items = data.get('base_items', {})
        if base_items:
            for item_id, value in base_items.items():
                if value and str(value).strip():  # 只保存有值的项目
                    try:
                        base_record = InspectionBaseItemRecord(
                            record_id=record.id,
                            base_item_id=int(item_id),
                            value=str(value).strip()
                        )
                        db.session.add(base_record)
                    except (ValueError, TypeError) as e:
                        current_app.logger.warning(f'保存基本信息项目记录失败: item_id={item_id}, error={str(e)}')
                        continue
        
        # 保存检验项目记录
        items = data.get('items', {})
        if items:
            for item_id, item_data in items.items():
                if not isinstance(item_data, dict):
                    continue
                    
                measured_value = item_data.get('value')
                if measured_value is not None and str(measured_value).strip():  # 只保存有实测值的项目
                    try:
                        item_record = InspectionItemRecord(
                            record_id=record.id,
                            item_id=int(item_id),
                            measured_value=float(measured_value),
                            is_qualified=bool(int(item_data.get('qualified', 0))),
                            notes=item_data.get('notes', '')
                        )
                        db.session.add(item_record)
                    except (ValueError, TypeError) as e:
                        current_app.logger.warning(f'保存检验项目记录失败: item_id={item_id}, error={str(e)}')
                        continue
        
        # 更新任务状态
        task = record.task
        if task:
            task.status = 'completed'
            task.completed_at = datetime.now()
        
        # 记录审计日志
        log = AuditLog(
            user_id=current_user.id,
            action='提交质检记录',
            details=f'提交质检记录：{record.global_sn}，结果：{record.result}',
            can_rollback=False,
            target_model='InspectionRecord',
            target_id=record.id,
            new_data=data
        )
        db.session.add(log)
        
        db.session.commit()
        
        from app.services import mes_service
        mes_service.apply_inspection_result(record)
        if task and task.target_type == 'goods_receipt' and record.result == 'pass':
            # 来料检合格：到货单已由 apply_inspection_result 置 accepted，这里按既有口径入库
            # （库存写入归 mes_service；不合格结论由 apply_inspection_result 生成不合格单并拒收）
            from app.models import GoodsReceipt
            receipt = GoodsReceipt.query.get(task.target_id)
            if receipt:
                receipt.status = 'accepted'
                mes_service.putaway_goods_receipt(receipt)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': '质检记录提交成功'
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'提交质检记录失败: {str(e)}')
        return jsonify({'success': False, 'message': f'提交失败：{str(e)}'}), 500

def get_inspection_target_name(task):
    """获取检验对象名称"""
    try:
        if task.target_type == 'production_record':
            record = ProductionRecord.query.get(task.target_id)
            if record:
                return f'生产记录：{record.global_sn} - {record.employee.name} - {record.process.process_name}'
            else:
                return '生产记录：未知'
        elif task.target_type == 'product':
            product = FinishedProduct.query.get(task.target_id)
            return f'成品：{product.product_number}' if product else '成品：未知'
        elif task.target_type == 'material':
            material = RawMaterial.query.get(task.target_id)
            return f'原材料：{material.material_name}' if material else '原材料：未知'
        return '未知'
    except Exception as e:
        current_app.logger.error(f'获取检验对象名称失败: {str(e)}')
        return '未知'

def delete_inspection_task(task_id):
    """删除质检任务"""
    try:
        task = InspectionTask.query.get_or_404(task_id)
        
        
        # 检查任务状态
        if task.status in ['in_progress', 'completed']:
            return jsonify({'success': False, 'message': '进行中或已完成的任务不能删除'}), 400
        
        # 保存旧数据用于审计日志
        old_data = {
            'global_sn': task.global_sn,
            'template_id': task.template_id,
            'target_type': task.target_type,
            'target_id': task.target_id,
            'inspector_id': task.inspector_id,
            'status': task.status
        }
        
        # 记录审计日志
        log = AuditLog(
            user_id=current_user.id,
            action='删除质检任务',
            details=f'删除质检任务：{task.global_sn}',
            can_rollback=True,
            rollback_type='delete',
            target_model='InspectionTask',
            target_id=task.id,
            old_data=old_data
        )
        db.session.add(log)
        
        # 删除任务
        db.session.delete(task)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': '任务删除成功'
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'删除质检任务失败: {str(e)}')
        return jsonify({'success': False, 'message': f'删除失败：{str(e)}'}), 500

def update_task(task_id):
    """更新质检任务"""
    try:
        task = InspectionTask.query.get_or_404(task_id)
        data = request.get_json()
        
        
        # 保存旧数据用于审计日志
        old_data = {
            'template_id': task.template_id,
            'target_type': task.target_type,
            'target_id': task.target_id,
            'inspector_id': task.inspector_id,
            'status': task.status,
            'priority': task.priority,
            'deadline': task.deadline.isoformat() if task.deadline else None,
            'notes': task.notes
        }
        
        # 更新任务 - 支持两种字段名格式以保持兼容性
        if 'template_id' in data:
            task.template_id = data['template_id']
        if 'inspector_id' in data:
            task.inspector_id = data['inspector_id']
        
        # 支持两种字段名：target_id 和 inspection_target_id
        if 'target_id' in data:
            task.target_id = data['target_id']
        elif 'inspection_target_id' in data:
            task.target_id = data['inspection_target_id']
            
        # 支持两种字段名：target_type 和 type
        if 'target_type' in data:
            task.target_type = data['target_type']
        elif 'type' in data:
            task.target_type = data['type']
            
        if 'priority' in data:
            task.priority = data['priority']
            
        # 支持两种字段名：deadline 和 planned_completion_time
        if 'deadline' in data and data['deadline']:
            task.deadline = datetime.strptime(data['deadline'], '%Y-%m-%dT%H:%M')
        elif 'planned_completion_time' in data and data['planned_completion_time']:
            task.deadline = datetime.strptime(data['planned_completion_time'], '%Y-%m-%dT%H:%M')
            
        if 'notes' in data:
            task.notes = data['notes']
        
        # 记录审计日志
        log = AuditLog(
            user_id=current_user.id,
            action='更新质检任务',
            details=f'更新质检任务：{task.global_sn}',
            can_rollback=True,
            rollback_type='edit',
            target_model='InspectionTask',
            target_id=task.id,
            old_data=old_data,
            new_data=data
        )
        db.session.add(log)
        
        db.session.commit()
        return jsonify({
            'success': True,
            'message': '任务更新成功'
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'更新质检任务失败: {str(e)}')
        return jsonify({'success': False, 'message': f'更新失败：{str(e)}'}), 500

@bp.route('/api/quality/records', methods=['GET'])
@login_required
@require_capability('quality.view')
def get_inspection_records():
    """获取质检记录列表API"""
    try:
        # 获取查询参数
        search = request.args.get('search', '').strip()
        type_filter = request.args.get('type', '').strip()
        result_filter = request.args.get('result', '').strip()
        inspector_id = request.args.get('inspector', '').strip()
        start_date = request.args.get('start_date', '').strip()
        end_date = request.args.get('end_date', '').strip()
        page = request.args.get('page', 1, type=int)
        per_page = _validated_per_page()
        
        # 构建查询
        query = InspectionRecord.query
        
        # 搜索条件
        if search:
            query = query.filter(
                db.or_(
                    InspectionRecord.global_sn.like(f'%{search}%'),
                    InspectionRecord.notes.like(f'%{search}%')
                )
            )
        
        # 类型筛选
        if type_filter:
            query = query.join(InspectionTask).filter(InspectionTask.target_type == type_filter)
        
        # 结果筛选
        if result_filter:
            query = query.filter(InspectionRecord.result == result_filter)
        
        # 检验员筛选
        if inspector_id:
            query = query.filter(InspectionRecord.inspector_id == int(inspector_id))
        
        # 日期范围筛选
        if start_date:
            try:
                start_dt = datetime.strptime(start_date, '%Y-%m-%d')
                query = query.filter(InspectionRecord.created_at >= start_dt)
            except ValueError:
                pass
        
        if end_date:
            try:
                end_dt = datetime.strptime(end_date, '%Y-%m-%d')
                end_dt = end_dt.replace(hour=23, minute=59, second=59)
                query = query.filter(InspectionRecord.created_at <= end_dt)
            except ValueError:
                pass
        
        # 权限控制
        if current_user.role == 'inspector':
            query = query.filter(InspectionRecord.inspector_id == current_user.id)
        
        # 排序
        query = query.order_by(InspectionRecord.created_at.desc())
        
        # 分页
        pagination = query.paginate(
            page=page, 
            per_page=per_page, 
            error_out=False
        )
        
        # 构造返回数据
        records = []
        for record in pagination.items:
            # 获取检验对象名称
            target_name = '未知'
            if record.task:
                target_name = get_inspection_target_name(record.task)
            
            # 获取检验员名称
            inspector_name = record.inspector.employee.name if record.inspector and record.inspector.employee else (record.inspector.username if record.inspector else '未知')
            
            records.append({
                'id': record.id,
                'record_code': record.global_sn,
                'type': record.task.target_type if record.task else 'unknown',
                'inspection_target': target_name,
                'inspector_name': inspector_name,
                'inspection_time': record.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'result': record.result or 'pending',
                'notes': record.notes or ''
            })
        
        return jsonify({
            'success': True,
            'data': {
                'items': records,
                'page': page,
                'pages': pagination.pages,
                'per_page': per_page,
                'total': pagination.total
            }
        })
        
    except Exception as e:
        current_app.logger.error(f'获取质检记录列表失败: {str(e)}')
        return jsonify({'success': False, 'message': f'获取记录列表失败：{str(e)}'}), 500


@bp.route('/api/quality/records/<int:record_id>', methods=['GET'])
@login_required
@require_capability('quality.view')
def get_inspection_record_detail(record_id):
    """获取质检记录详情API"""
    try:
        record = InspectionRecord.query.get_or_404(record_id)
        
        # 权限控制
        if current_user.role == 'inspector' and record.inspector_id != current_user.id:
            return jsonify({'success': False, 'message': '权限不足'}), 403
        
        # 获取检验对象名称
        target_name = '未知'
        if record.task:
            target_name = get_inspection_target_name(record.task)
        
        # 获取检验员名称
        inspector_name = record.inspector.employee.name if record.inspector and record.inspector.employee else (record.inspector.username if record.inspector else '未知')
        
        # 获取检验项目记录
        items = []
        for item_record in record.item_records:
            item = item_record.item
            items.append({
                'id': item.id,
                'item_name': item.item_name,
                'unit': item.unit or '',
                'standard_value': item.standard_value or '',
                'tolerance': item.tolerance or '',
                'measured_value': item_record.measured_value,
                'is_qualified': item_record.is_qualified,
                'notes': item_record.notes or ''
            })
        
        # 获取基本信息项目记录
        base_items = []
        for base_record in record.base_item_records:
            base_item = base_record.base_item
            base_items.append({
                'id': base_item.id,
                'item_name': base_item.item_name,
                'value': base_record.value
            })
        
        record_data = {
            'id': record.id,
            'record_code': record.global_sn,
            'type': record.task.target_type if record.task else 'unknown',
            'inspection_target': target_name,
            'inspector_name': inspector_name,
            'inspection_time': record.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'result': record.result or 'pending',
            'notes': record.notes or '',
            'items': items,
            'base_items': base_items
        }
        
        return jsonify({
            'success': True,
            'data': record_data
        })
        
    except Exception as e:
        current_app.logger.error(f'获取质检记录详情失败: {str(e)}')
        return jsonify({'success': False, 'message': f'获取记录详情失败：{str(e)}'}), 500

@bp.route('/api/quality/records/<int:record_id>/print', methods=['GET'])
@login_required
@require_capability('quality.view')
def print_inspection_record(record_id):
    """打印质检记录"""
    try:
        record = InspectionRecord.query.get_or_404(record_id)
        
        # 权限控制
        
        if current_user.role == 'inspector' and record.inspector_id != current_user.id:
            return jsonify({'success': False, 'message': '权限不足'}), 403
        
        # 模板直接读取 ORM 关系，这里只补两个模板取不到的派生名称
        target_name = get_inspection_target_name(record.task) if record.task else '未知'
        inspector_name = record.inspector.employee.name if record.inspector and record.inspector.employee else (record.inspector.username if record.inspector else '未知')

        return render_template(
            'main/quality/print_record.html',
            record=record,
            target_name=target_name,
            inspector_name=inspector_name
        )
        
    except Exception as e:
        current_app.logger.error(f'打印质检记录失败: {str(e)}')
        return f'打印失败：{str(e)}', 500


@bp.route('/api/quality/records/export', methods=['GET'])
@login_required
@require_capability('quality.export')
def export_inspection_records():
    """导出质检记录"""
    try:
        
        # 获取查询参数（与列表查询相同的参数）
        search = request.args.get('search', '').strip()
        type_filter = request.args.get('type', '').strip()
        result_filter = request.args.get('result', '').strip()
        inspector_id = request.args.get('inspector', '').strip()
        start_date = request.args.get('start_date', '').strip()
        end_date = request.args.get('end_date', '').strip()
        
        # 构建查询（不分页，获取所有记录）
        query = InspectionRecord.query
        
        # 搜索条件
        if search:
            query = query.filter(
                db.or_(
                    InspectionRecord.global_sn.like(f'%{search}%'),
                    InspectionRecord.notes.like(f'%{search}%')
                )
            )
        
        # 类型筛选
        if type_filter:
            query = query.join(InspectionTask).filter(InspectionTask.target_type == type_filter)
        
        # 结果筛选
        if result_filter:
            query = query.filter(InspectionRecord.result == result_filter)
        
        # 检验员筛选
        if inspector_id:
            query = query.filter(InspectionRecord.inspector_id == int(inspector_id))
        
        # 日期范围筛选
        if start_date:
            try:
                start_dt = datetime.strptime(start_date, '%Y-%m-%d')
                query = query.filter(InspectionRecord.created_at >= start_dt)
            except ValueError:
                pass
        
        if end_date:
            try:
                end_dt = datetime.strptime(end_date, '%Y-%m-%d')
                end_dt = end_dt.replace(hour=23, minute=59, second=59)
                query = query.filter(InspectionRecord.created_at <= end_dt)
            except ValueError:
                pass
        
        # 排序
        query = query.order_by(InspectionRecord.created_at.desc())
        
        # 获取所有记录
        records = query.all()
        
        # 准备Excel数据
        import pandas as pd
        from io import BytesIO
        
        data = []
        for record in records:
            # 获取检验对象名称
            target_name = '未知'
            if record.task:
                target_name = get_inspection_target_name(record.task)
            
            # 获取检验员名称
            inspector_name = record.inspector.employee.name if record.inspector and record.inspector.employee else (record.inspector.username if record.inspector else '未知')
            
            # 获取类型名称
            type_names = {
                'production_record': '生产记录质检',
                'product': '成品质检',
                'material': '原材料质检'
            }
            type_name = type_names.get(record.task.target_type if record.task else 'unknown', '未知')
            
            data.append({
                '记录编号': record.global_sn,
                '检验类型': type_name,
                '检验对象': target_name,
                '检验员': inspector_name,
                '检验时间': record.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                '检验结果': '合格' if record.result == 'pass' else '不合格',
                '备注': record.notes or ''
            })
        
        # 创建DataFrame
        df = pd.DataFrame(data)
        
        # 创建Excel文件
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='质检记录', index=False)
        
        output.seek(0)
        
        # 生成文件名
        from datetime import datetime
        filename = f'质检记录_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        
        # 返回文件
        from flask import send_file
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        current_app.logger.error(f'导出质检记录失败: {str(e)}')
        return jsonify({'success': False, 'message': f'导出失败：{str(e)}'}), 500


# ---------------------------------------------------------------------------
# 质检任务：导出 / 导入模板 / 导入
# 前端入口在 main/quality/tasks.html。导出与模板一律内存生成，不落临时文件
# （本仓库在 Windows 上出现过 send_file 之后临时文件被占用、WinError 32 删不掉的问题）。
# ---------------------------------------------------------------------------

TASK_IMPORT_COL_TYPE = '检验类型(product/production_record/material)'
TASK_IMPORT_COL_TARGET = '检验对象ID'
TASK_IMPORT_COL_INSPECTOR = '检验员用户名'
TASK_IMPORT_COL_PRIORITY = '优先级'
TASK_IMPORT_COL_DEADLINE = '截止时间(YYYY-MM-DD)'
TASK_IMPORT_COL_NOTES = '备注'

_TASK_TYPE_NAMES = {
    'product': '成品质检',
    'production_record': '生产记录质检',
    'material': '原材料质检',
}
_VALID_TASK_TYPES = ('product', 'production_record', 'material')


def _task_export_rows(query):
    """把质检任务查询结果整理成导出行（列名与导入模板保持同一套）。"""
    rows = []
    for task in query.order_by(InspectionTask.created_at.desc()).all():
        inspector = task.inspector
        inspector_name = ''
        if inspector is not None:
            employee = getattr(inspector, 'employee', None)
            inspector_name = employee.name if employee else inspector.username
        rows.append({
            '任务编号': task.global_sn,
            '检验类型': _TASK_TYPE_NAMES.get(task.target_type, task.target_type or ''),
            '检验对象ID': task.target_id,
            '状态': task.status,
            '优先级': task.priority or 0,
            '检验员': inspector_name,
            '截止时间': task.deadline.strftime('%Y-%m-%d %H:%M') if task.deadline else '',
            '创建时间': task.created_at.strftime('%Y-%m-%d %H:%M:%S') if task.created_at else '',
            '备注': task.notes or '',
        })
    return rows


@bp.route('/api/quality/tasks/export', methods=['GET'])
@login_required
@require_capability('quality.export')
def export_inspection_tasks():
    """导出质检任务清单（xlsx，内存生成）。"""
    try:
        import pandas as pd
        from io import BytesIO

        query = InspectionTask.query
        search = request.args.get('search', '').strip()
        if search:
            query = query.filter(db.or_(
                InspectionTask.global_sn.like(f'%{search}%'),
                InspectionTask.notes.like(f'%{search}%'),
            ))
        status_filter = request.args.get('status', '').strip()
        if status_filter:
            query = query.filter(InspectionTask.status == status_filter)
        target_type = request.args.get('target_type', '').strip()
        if target_type:
            query = query.filter(InspectionTask.target_type == target_type)
        inspector_id = request.args.get('inspector', '').strip()
        if inspector_id.isdigit():
            query = query.filter(InspectionTask.inspector_id == int(inspector_id))

        rows = _task_export_rows(query)
        df = pd.DataFrame(rows)
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='质检任务', index=False)
        output.seek(0)

        filename = f'质检任务_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename,
        )
    except Exception as e:
        current_app.logger.error(f'导出质检任务失败: {str(e)}')
        flash('导出失败，请重试', 'danger')
        return redirect(url_for('main.quality_tasks'))


@bp.route('/api/quality/tasks/template', methods=['GET'])
@login_required
@require_capability('quality.export')
def download_inspection_task_template():
    """下载质检任务导入模板（列名与导入解析严格一致）。"""
    try:
        import pandas as pd
        from io import BytesIO

        df = pd.DataFrame([{
            TASK_IMPORT_COL_TYPE: 'production_record',
            TASK_IMPORT_COL_TARGET: 1,
            TASK_IMPORT_COL_INSPECTOR: 'inspector01',
            TASK_IMPORT_COL_PRIORITY: 0,
            TASK_IMPORT_COL_DEADLINE: '',
            TASK_IMPORT_COL_NOTES: '示例行：导入前请删除',
        }])
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='质检任务导入模板', index=False)
        output.seek(0)
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name='质检任务导入模板.xlsx',
        )
    except Exception as e:
        current_app.logger.error(f'下载质检任务导入模板失败: {str(e)}')
        flash('下载模板失败，请重试', 'danger')
        return redirect(url_for('main.quality_tasks'))


@bp.route('/api/quality/tasks/import', methods=['POST'])
@login_required
@require_capability('quality.task.manage')
def import_inspection_tasks():
    """从 xlsx 导入质检任务。

    行级容错：坏行只记「第 N 行：…」并跳过，不整体 500（与 import_tasks 同一口径）；
    文本日期用 pandas.to_datetime 兜底。
    """
    file = request.files.get('file')
    if file is None or not file.filename:
        flash('请选择要导入的 Excel 文件', 'warning')
        return redirect(url_for('main.quality_tasks'))

    try:
        import pandas as pd
    except Exception as e:
        current_app.logger.error(f'导入质检任务时加载 pandas 失败: {str(e)}')
        flash('导入失败：运行环境缺少 pandas 依赖', 'danger')
        return redirect(url_for('main.quality_tasks'))

    try:
        df = pd.read_excel(file)
    except Exception as e:
        current_app.logger.error(f'质检任务导入文件解析失败: {str(e)}')
        flash(f'文件解析失败：{str(e)}', 'danger')
        return redirect(url_for('main.quality_tasks'))

    required_cols = (TASK_IMPORT_COL_TYPE, TASK_IMPORT_COL_TARGET, TASK_IMPORT_COL_INSPECTOR)
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        flash(f'文件缺少必需的列：{", ".join(missing)}（请先下载导入模板）', 'danger')
        return redirect(url_for('main.quality_tasks'))

    def _is_blank(value):
        return value is None or (isinstance(value, float) and pd.isna(value))

    created = 0
    errors = []
    try:
        for idx, row in df.iterrows():
            lineno = idx + 2  # 第 1 行是表头
            target_type = str(row.get(TASK_IMPORT_COL_TYPE, '') or '').strip()
            if target_type not in _VALID_TASK_TYPES:
                errors.append(f'第 {lineno} 行：检验类型必须是 product / production_record / material')
                continue

            raw_target = row.get(TASK_IMPORT_COL_TARGET)
            if _is_blank(raw_target):
                errors.append(f'第 {lineno} 行：检验对象ID 不能为空')
                continue
            try:
                target_id = int(raw_target)
            except (TypeError, ValueError):
                errors.append(f'第 {lineno} 行：检验对象ID 必须是整数')
                continue

            username = str(row.get(TASK_IMPORT_COL_INSPECTOR, '') or '').strip()
            if not username:
                errors.append(f'第 {lineno} 行：检验员用户名不能为空')
                continue
            inspector = User.query.filter_by(username=username).first()
            if inspector is None:
                errors.append(f'第 {lineno} 行：检验员用户名 {username} 不存在')
                continue

            deadline = None
            if TASK_IMPORT_COL_DEADLINE in df.columns:
                raw_deadline = row.get(TASK_IMPORT_COL_DEADLINE)
                if not _is_blank(raw_deadline):
                    text = str(raw_deadline).strip()
                    if text:
                        try:
                            deadline = pd.to_datetime(text).to_pydatetime()
                        except Exception:
                            errors.append(f'第 {lineno} 行：截止时间格式错误（应为 YYYY-MM-DD）')
                            continue

            priority = 0
            if TASK_IMPORT_COL_PRIORITY in df.columns:
                raw_priority = row.get(TASK_IMPORT_COL_PRIORITY)
                if not _is_blank(raw_priority):
                    try:
                        priority = int(raw_priority)
                    except (TypeError, ValueError):
                        priority = 0

            notes = ''
            if TASK_IMPORT_COL_NOTES in df.columns:
                raw_notes = row.get(TASK_IMPORT_COL_NOTES)
                if not _is_blank(raw_notes):
                    notes = str(raw_notes).strip()

            db.session.add(InspectionTask(
                global_sn=SerialNumber.get_next_number(),
                template_id=None,  # 模板由检验员开始检验时再选（沿用既有流程）
                inspector_id=inspector.id,
                target_type=target_type,
                target_id=target_id,
                status='pending',
                priority=priority,
                deadline=deadline,
                notes=notes,
                created_by=current_user.id,
            ))
            created += 1
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'导入质检任务失败: {str(e)}')
        flash(f'导入失败：{str(e)}', 'danger')
        return redirect(url_for('main.quality_tasks'))

    if created:
        flash(f'成功导入 {created} 条质检任务' + (f'，{len(errors)} 行被跳过' if errors else ''), 'success')
    else:
        flash(f'没有导入任何数据（{len(errors)} 行被跳过）', 'warning')
    for message in errors[:20]:
        flash(message, 'warning')
    if len(errors) > 20:
        flash(f'另有 {len(errors) - 20} 行错误未逐条显示', 'warning')
    return redirect(url_for('main.quality_tasks'))