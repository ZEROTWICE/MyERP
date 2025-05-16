from flask import render_template, redirect, url_for, flash, request, jsonify, current_app, send_file
from flask_login import login_required, current_user
from app import db, csrf
from app.models import (
    InspectionTemplate, InspectionBaseItem, InspectionItem,
    InspectionTask, InspectionRecord, AuditLog, User, Employee,
    SerialNumber
)
from datetime import datetime
from . import bp

@bp.route('/quality')
@login_required
def quality_management():
    """质量管理主页"""
    if current_user.role not in ['admin', 'manager', 'inspector']:
        flash('权限不足', 'danger')
        return redirect(url_for('main.index'))
    
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
def quality_templates():
    """质检模板列表"""
    if current_user.role not in ['admin', 'manager']:
        flash('权限不足', 'danger')
        return redirect(url_for('main.index'))
    
    return render_template('main/quality/templates.html')

@bp.route('/quality/tasks', methods=['GET'])
@login_required
def quality_tasks():
    """质检任务列表"""
    if current_user.role not in ['admin', 'manager', 'inspector']:
        flash('权限不足', 'danger')
        return redirect(url_for('main.index'))
    
    return render_template('main/quality/tasks.html')

@bp.route('/quality/records', methods=['GET'])
@login_required
def quality_records():
    """质检记录列表"""
    if current_user.role not in ['admin', 'manager', 'inspector']:
        flash('权限不足', 'danger')
        return redirect(url_for('main.index'))
    
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

# API路由
@bp.route('/api/quality/templates', methods=['GET'])
@login_required
def get_templates():
    """获取质检模板列表"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
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
@csrf.exempt  # 对API请求豁免CSRF保护
def create_template():
    """创建质检模板"""
    if current_user.role not in ['admin', 'manager']:
        return jsonify({'success': False, 'message': '权限不足'}), 403

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
@csrf.exempt
def manage_template(template_id):
    """管理质检模板（更新/删除）"""
    if current_user.role not in ['admin', 'manager']:
        return jsonify({'success': False, 'message': '权限不足'}), 403

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
def get_tasks():
    """获取质检任务列表"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
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
                'inspector_name': t.inspector.name,
                'status': t.status,
                'inspection_date': t.inspection_date.strftime('%Y-%m-%d') if t.inspection_date else None
            } for t in tasks],
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
            'pages': pagination.pages
        }
    })

@bp.route('/api/quality/tasks/<int:task_id>', methods=['GET'])
@login_required
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
            'inspection_target': get_inspection_target_name(task),
            'inspector_name': task.inspector.name,
            'status': task.status,
            'completed_quantity': task.completed_quantity,
            'total_quantity': task.total_quantity,
            'inspection_date': task.inspection_date.strftime('%Y-%m-%d') if task.inspection_date else None,
            'notes': task.notes
        }
    })

@bp.route('/api/quality/tasks', methods=['POST'])
@login_required
@csrf.exempt  # 对API请求豁免CSRF保护
def create_task():
    """创建质检任务"""
    if current_user.role not in ['admin', 'manager']:
        return jsonify({'success': False, 'message': '权限不足'}), 403

    try:
        data = request.get_json()
        
        # 创建任务
        task = InspectionTask(
            global_sn=SerialNumber.get_next_number(),
            template_id=data['template_id'],
            target_type=data['type'],
            inspector_id=data['inspector_id'],
            total_quantity=data['total_quantity'],
            inspection_date=datetime.strptime(data['inspection_date'], '%Y-%m-%d').date() if data['inspection_date'] else None,
            notes=data.get('notes', ''),
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
@csrf.exempt  # 对API请求豁免CSRF保护
def manage_task(task_id):
    """管理质检任务（更新/删除）"""
    if current_user.role not in ['admin', 'manager', 'inspector']:
        return jsonify({'success': False, 'message': '权限不足'}), 403

    if request.method == 'DELETE':
        return delete_inspection_task(task_id)
    else:
        return update_task(task_id)

@bp.route('/api/quality/inspectors', methods=['GET'])
@login_required
def get_inspectors():
    """获取质检员列表"""
    try:
        # 查询具有inspector角色的用户
        inspectors = User.query.join(Employee).filter(
            User.role.in_(['inspector', 'admin', 'manager'])
        ).all()
        
        return jsonify({
            'success': True,
            'data': [{
                'id': inspector.id,
                'name': inspector.employee.name if inspector.employee else inspector.username,
                'employee_id': inspector.employee.employee_id if inspector.employee else None,
                'department': inspector.employee.department if inspector.employee else None
            } for inspector in inspectors]
        })
    except Exception as e:
        current_app.logger.error(f'获取质检员列表失败: {str(e)}')
        return jsonify({'success': False, 'message': f'获取质检员列表失败：{str(e)}'}), 500

def get_inspection_target_name(task):
    """获取检验对象名称"""
    if task.target_type == 'process':
        return f'工序：{task.process.process_name}'
    elif task.target_type == 'product':
        return f'成品：{task.product.product_number}'
    elif task.target_type == 'material':
        return f'原材料：{task.material.material_name}'
    return '未知'