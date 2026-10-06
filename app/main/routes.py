from sqlalchemy.exc import SQLAlchemyError
from flask import render_template, redirect, url_for, flash, request, jsonify, current_app, send_file
from flask_login import login_required, current_user
from app import db, csrf
from app.permissions import allowed_search_types, require_capability, can, can_any
from app.models import Employee, ProcessPrice, ProductionRecord, BonusPenalty, AuditLog, ProcessPrice, User, TaskAssignment, SerialNumber, SalaryChange, CoefficientChange, EmployeeSalaryHistory, EmployeeCoefficientHistory, ProcessPriceGroup, FinishedProduct, RawMaterial, CodeRule, CodeGenerationLog, ProductionRecordMaterial, InspectionTemplate, InspectionBaseItem, InspectionItem, InspectionTask, InspectionRecord, Product, ProductBOM, ProductProcess, ProductionOrder, MaterialAllocation, ProductionBatch, ProductionBatchItem, Customer, CustomerAddress, SalesOrder, SalesOrderItem, SalesOrder, SalesOrderItem, ProcessAssignmentRule, ProcessAssignmentMember, SystemConfig, RawMaterialCategory, WorkCenter
from datetime import datetime, timedelta, date
from . import bp
from app.main.forms import (
    EmployeeForm, ProcessPriceForm, ProductionRecordForm, BonusPenaltyForm,
    SalaryCalculationForm, AuditLogSearchForm, ProcessPriceSearchForm,
    ProductionRecordSearchForm, TaskAssignmentForm, TaskSearchForm,
    BonusPenaltySearchForm, ExportEmployeeForm, ExportProcessForm,
    ExportProductionRecordForm, ExportBonusPenaltyForm, ExportTaskForm,
    CustomerForm, CustomerAddressForm, SalesOrderForm, SalesOrderItemForm,
    ProductionOrderForm, NotificationRuleForm, NotificationTemplateForm,
    GlobalSearchForm, AdvancedSearchForm, ExportProductForm, ProductImportForm
)
from sqlalchemy import desc, or_
from app.utils.excel_generator import ExcelGenerator
import io
import os
import time
from werkzeug.utils import secure_filename
from werkzeug.datastructures import FileStorage
from werkzeug.exceptions import HTTPException
from typing import Optional
from functools import wraps
import tempfile
from flask_paginate import Pagination
import pandas as pd
import numpy as np
from werkzeug.datastructures import FileStorage
from typing import List, Dict, Any, Optional, Union
import shutil
from openpyxl import Workbook
import json
from io import BytesIO
from openpyxl import load_workbook

# 导入质量管理路由
from .quality import *
from .production_center import *
from . import equipment, purchase, shipping, stock

from app.services.search_service import SearchService


def _reraise_http(exc):
    """get_or_404 / abort 抛出的 HTTPException 是 Exception 子类，
    被 except Exception 捕获后会变成 500 或带错误文案的 200。"""
    if isinstance(exc, HTTPException):
        raise


def _wants_json_body():
    if request.is_json:
        return True
    accept = request.accept_mimetypes.best or ''
    return accept.startswith('application/json')


def _warehouse_reply(ok, message, redirect_to, extra=None, status=200):
    """表单提交走 flash+redirect，JSON/测试客户端走 {success, message}。"""
    payload = {'success': bool(ok), 'message': message}
    if extra:
        payload.update(extra)
    if _wants_json_body():
        return jsonify(payload), (status if ok else (status if status != 200 else 400))
    flash(message, 'success' if ok else 'danger')
    return redirect(redirect_to)


def _parse_flag(data, key, default=None):
    if not data or key not in data:
        return default
    val = data[key]
    if isinstance(val, bool):
        return val
    if val is None or val == '':
        return default
    return str(val).lower() in ('1', 'true', 'on', 'yes')


def _coerce_excel_date(value, label='日期'):
    """把 Excel 单元格里的真日期/文本日期统一成日期类型。

    openpyxl 对「真日期单元格」给 datetime/date，对文本日期给 str；把 str 直接塞进
    Date/DateTime 列时 SQLite 方言会抛 TypeError（t7 门禁实测：导入任务与奖惩逐行失败）。
    真日期原样返回（保留原有口径），文本用 pandas 兜底解析。返回 (值, 错误原因)。
    """
    if isinstance(value, datetime):
        return value, None
    if isinstance(value, date):
        return value, None
    if value is None or (isinstance(value, str) and not value.strip()):
        return None, f'{label}不能为空'
    try:
        parsed = pd.to_datetime(str(value).strip(), errors='coerce')
    except (ValueError, TypeError, OverflowError):
        parsed = None
    if parsed is None or pd.isna(parsed):
        return None, f'{label}格式错误（{value}）'
    return parsed.to_pydatetime(), None


def _resolve_raw_material_category(name, created_by=None):
    """把「品名」解析成原材料品类并返回真实记录。

    RawMaterial.material_name 是取 category.name 的 @property，**不是数据库列**，
    不能当作构造函数参数或查询条件；RawMaterial.category_id 又是 NOT NULL，
    所以入库必须落到真实品类上。品类名不存在时按需建一个
    （与采购入库自动建「采购入库」品类的既有做法一致）。
    """
    category_name = (name or '').strip() or '未分类'
    category = RawMaterialCategory.query.filter_by(name=category_name).first()
    if category is None:
        category = RawMaterialCategory(
            name=category_name,
            code=SerialNumber.get_next_number(),
            created_by=created_by,
        )
        db.session.add(category)
        db.session.flush()
    return category


@bp.route('/process_assignment', methods=['GET'])
@login_required
@require_capability('process_assignment.manage')
def process_assignment_page():
    processes = ProcessPrice.query.order_by(ProcessPrice.process_code).all()
    employees = Employee.query.filter_by(is_active=True).order_by(Employee.name).all()
    employees_data = [{'id': e.id, 'employee_id': e.employee_id, 'name': e.name} for e in employees]
    return render_template('main/process_assignment_bulk.html', processes=processes, employees=employees_data, employees_json=employees_data)

@bp.route('/api/process_assignment/<int:process_id>', methods=['GET'])
@login_required
@require_capability('process_assignment.manage')
def get_process_assignment(process_id):
    try:
        rule = ProcessAssignmentRule.query.filter_by(process_id=process_id).first()
        if not rule:
            return jsonify({'success': True, 'data': None})
        members = rule.members.filter_by(is_active=True).order_by(ProcessAssignmentMember.sequence).all()
        return jsonify({'success': True, 'data': {
            'id': rule.id,
            'strategy': rule.strategy,
            'is_active': rule.is_active,
            'members': [{'employee_id': m.employee_id, 'sequence': m.sequence, 'weight': m.weight, 'employee_name': m.employee.name} for m in members]
        }})
    except Exception as e:
        # 兼容：当迁移未执行导致表不存在时返回空配置，避免500
        if 'no such table' in str(e).lower():
            return jsonify({'success': True, 'data': None, 'message': '规则表未初始化，请先执行数据库迁移'}), 200
        current_app.logger.error(f'读取工序分配规则失败: {str(e)}')
        return jsonify({'success': False, 'message': f'读取失败：{str(e)}'}), 500

@bp.route('/api/process_assignment', methods=['GET'])
@login_required
@require_capability('process_assignment.manage')
def list_process_assignments():
    try:
        rules = ProcessAssignmentRule.query.all()
        data = {}
        for r in rules:
            members = r.members.filter_by(is_active=True).order_by(ProcessAssignmentMember.sequence).all()
            data[r.process_id] = {
                'strategy': r.strategy,
                'is_active': r.is_active,
                'members': [{'employee_id': m.employee_id, 'sequence': m.sequence, 'weight': m.weight} for m in members]
            }
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        if 'no such table' in str(e).lower():
            return jsonify({'success': True, 'data': {}, 'message': '规则表未初始化，请先执行数据库迁移'}), 200
        current_app.logger.error(f'列出工序分配规则失败: {str(e)}')
        return jsonify({'success': False, 'message': f'读取失败：{str(e)}'}), 500

@bp.route('/api/process_assignment/<int:process_id>', methods=['POST'])
@login_required
@require_capability('process_assignment.manage')
@csrf.exempt
def save_process_assignment(process_id):
    try:
        data = request.get_json() or {}
        strategy = (data.get('strategy') or 'round_robin').strip()
        is_active = bool(data.get('is_active', True))
        members = data.get('members') or []

        rule = ProcessAssignmentRule.query.filter_by(process_id=process_id).first()
        if not rule:
            rule = ProcessAssignmentRule(process_id=process_id, strategy=strategy, is_active=is_active)
            db.session.add(rule)
            db.session.flush()
        else:
            rule.strategy = strategy
            rule.is_active = is_active

        ProcessAssignmentMember.query.filter_by(rule_id=rule.id).delete()
        for i, m in enumerate(members):
            try:
                emp_id = int(m.get('employee_id'))
            except (TypeError, ValueError):
                continue
            member = ProcessAssignmentMember(
                rule_id=rule.id,
                employee_id=emp_id,
                sequence=int(m.get('sequence') or i),
                weight=int(m.get('weight') or 1),
                is_active=True
            )
            db.session.add(member)

        log = AuditLog(
            user_id=current_user.id,
            action='保存工序分配规则',
            details=f'工序ID {process_id} 策略 {strategy}，成员 {len(members)}',
            can_rollback=True,
            rollback_type='edit',
            target_model='ProcessAssignmentRule',
            target_id=rule.id,
            new_data=data
        )
        db.session.add(log)
        db.session.commit()
        return jsonify({'success': True, 'message': '保存成功'})
    except Exception as e:
        db.session.rollback()
        # 兼容：当迁移未执行导致表不存在时，明确提示
        if 'no such table' in str(e).lower():
            return jsonify({'success': False, 'message': '规则表未初始化，请先执行数据库迁移（flask db upgrade）'}), 400
        current_app.logger.error(f'保存工序分配规则失败: {str(e)}')
        return jsonify({'success': False, 'message': f'保存失败：{str(e)}'}), 500

@bp.route('/api/process_assignment/bulk', methods=['POST'])
@login_required
@require_capability('process_assignment.manage')
@csrf.exempt
def save_process_assignment_bulk():
    try:
        payload = request.get_json() or {}
        # payload: { process_id: {strategy, is_active, members: [{employee_id, sequence, weight}]}, ... }
        for pid_str, cfg in payload.items():
            try:
                pid = int(pid_str)
            except (TypeError, ValueError):
                continue
            strategy = (cfg.get('strategy') or 'round_robin').strip()
            is_active = bool(cfg.get('is_active', True))
            members = cfg.get('members') or []

            rule = ProcessAssignmentRule.query.filter_by(process_id=pid).first()
            if not rule:
                rule = ProcessAssignmentRule(process_id=pid, strategy=strategy, is_active=is_active)
                db.session.add(rule)
                db.session.flush()
            else:
                rule.strategy = strategy
                rule.is_active = is_active

            ProcessAssignmentMember.query.filter_by(rule_id=rule.id).delete()
            for i, m in enumerate(members):
                try:
                    emp_id = int(m.get('employee_id'))
                except (TypeError, ValueError):
                    continue
                member = ProcessAssignmentMember(
                    rule_id=rule.id,
                    employee_id=emp_id,
                    sequence=int(m.get('sequence') or i),
                    weight=int(m.get('weight') or 1),
                    is_active=True
                )
                db.session.add(member)

        db.session.commit()
        return jsonify({'success': True, 'message': '批量保存成功'})
    except Exception as e:
        db.session.rollback()
        if 'no such table' in str(e).lower():
            return jsonify({'success': False, 'message': '规则表未初始化，请先执行数据库迁移（flask db upgrade）'}), 400
        current_app.logger.error(f'批量保存工序分配规则失败: {str(e)}')
        return jsonify({'success': False, 'message': f'保存失败：{str(e)}'}), 500

def handle_pagination_args(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            # 获取并验证分页参数
            page = request.args.get('page', 1, type=int)
            per_page = int(request.args.get('per_page', '20'))
            
            # 确保分页参数在合理范围内
            if page < 1:
                page = 1
            if per_page not in [20, 50, 100]:
                per_page = 20
                
            # 将验证后的参数存储在request对象中
            request.validated_page = page
            request.validated_per_page = per_page
            
            return f(*args, **kwargs)
        except (ValueError, TypeError):
            flash('分页参数无效，已使用默认值', 'warning')
            request.validated_page = 1
            request.validated_per_page = 20
            return f(*args, **kwargs)
    return decorated_function

# 角色 -> 登录后的默认落地端点；未列出的角色落到通用欢迎页
ROLE_LANDING_ENDPOINTS = {
    'user': 'main.user_dashboard',
    'inspector': 'main.quality_management',
    'hr': 'main.manage_employees',
    'accountant': 'main.salary_calculation',
    'sales': 'main.manage_sales_orders',
}


@bp.route('/')
@login_required
def index():
    """按角色分流到各自的落地页。

    这里不能重定向到任何可能再跳回 index 的端点，否则会形成重定向死循环
    （hr/accountant/sales 曾因此完全无法登录）。
    """
    if current_user.role in ('admin', 'manager'):
        return render_template('main/admin_dashboard.html')

    endpoint = ROLE_LANDING_ENDPOINTS.get(current_user.role)
    if endpoint:
        return redirect(url_for(endpoint))

    return render_template('main/welcome.html')

@bp.route('/user_dashboard')
@login_required
def user_dashboard():
    current_app.logger.debug(
        f'user_dashboard accessed by user {current_user.id} ({current_user.username}) role={current_user.role}'
    )

    # 以下两处直接渲染欢迎页而不是重定向回 index，避免与 index 互相跳转。
    # 「有工作台」的角色 = 员工自助(my_tasks.use) + 生产/质检视角，由能力表推导，
    # 不再手写角色名，避免与 permissions.py 漂移
    if not can_any('my_tasks.use', 'production_order.view', 'quality.view'):
        return render_template(
            'main/welcome.html',
            message='当前角色没有员工工作台，请从导航栏进入所需功能。'
        )
    
    # 获取当前用户的员工信息
    employee = Employee.query.filter_by(user_id=current_user.id).first()
    if not employee:
        current_app.logger.debug(f'未找到用户 {current_user.username} 对应的员工信息')
        return render_template(
            'main/welcome.html',
            message='您的账号尚未关联员工信息，请联系管理员完成关联后再使用工作台。'
        )

    # 获取待完成任务（最多5个）
    pending_tasks = TaskAssignment.query.filter_by(employee_id=employee.id)\
        .filter(TaskAssignment.status.in_(['pending', 'in_progress']))\
        .order_by(TaskAssignment.assigned_date.desc())\
        .limit(5).all()

    # 获取已完成任务（最多5个）
    completed_tasks = TaskAssignment.query.filter_by(employee_id=employee.id)\
        .filter(TaskAssignment.status == 'completed')\
        .order_by(TaskAssignment.assigned_date.desc())\
        .limit(5).all()

    # 获取最近的生产记录（最多5个）
    recent_records = ProductionRecord.query.filter_by(employee_id=employee.id)\
        .order_by(ProductionRecord.date.desc())\
        .limit(5).all()

    # 获取最近的奖惩记录（最多5个）
    recent_bonuses = BonusPenalty.query.filter_by(employee_id=employee.id)\
        .order_by(BonusPenalty.date.desc())\
        .limit(5).all()

    # 工资计算
    from datetime import datetime, date
    today = date.today()
    current_month_start = date(today.year, today.month, 1)

    # 计算当日工资
    daily_production = ProductionRecord.query.filter_by(employee_id=employee.id, date=today).all()
    daily_piecework = sum(record.quantity * record.process.price for record in daily_production)
    daily_bonuses = BonusPenalty.query.filter_by(employee_id=employee.id)\
        .filter(db.func.date(BonusPenalty.date) == today).all()
    daily_adjustments = sum(bp.amount if bp.type == 'bonus' else -bp.amount for bp in daily_bonuses)
    daily_salary = daily_piecework * employee.coefficient + daily_adjustments

    # 计算当月工资
    monthly_production = ProductionRecord.query.filter_by(employee_id=employee.id)\
        .filter(ProductionRecord.date >= current_month_start).all()
    monthly_piecework = sum(record.quantity * record.process.price for record in monthly_production)
    monthly_bonuses = BonusPenalty.query.filter_by(employee_id=employee.id)\
        .filter(BonusPenalty.date >= datetime.combine(current_month_start, datetime.min.time())).all()
    monthly_adjustments = sum(bp.amount if bp.type == 'bonus' else -bp.amount for bp in monthly_bonuses)
    monthly_salary = employee.base_salary + monthly_piecework * employee.coefficient + monthly_adjustments
    
    # 质检员相关数据 - 基于员工职位检查
    inspection_tasks = []
    pending_inspections = 0
    # 检查员工职位是否包含"质检"
    is_inspector = employee.position and ('质检' in employee.position)
    
    if is_inspector:
        from app.models import InspectionTask
        # 获取分配给当前质检员的任务（最多5个）
        inspection_tasks = InspectionTask.query.filter_by(inspector_id=current_user.id)\
            .order_by(InspectionTask.created_at.desc())\
            .limit(5).all()
        
        # 获取待处理的质检任务数量
        pending_inspections = InspectionTask.query.filter_by(
            inspector_id=current_user.id,
            status='pending'
        ).count()
    
    from datetime import datetime
    
    return render_template('main/user_dashboard.html',
                         employee=employee,
                         pending_tasks=pending_tasks,
                         completed_tasks=completed_tasks,
                         recent_records=recent_records,
                         recent_bonuses=recent_bonuses,
                         inspection_tasks=inspection_tasks,
                         pending_inspections=pending_inspections,
                         current_time=datetime.now(),
                         is_inspector=is_inspector,
                         daily_salary=daily_salary,
                         monthly_salary=monthly_salary)

@bp.route('/employees')
@login_required
@require_capability('employee.view')
@handle_pagination_args
def manage_employees():
    
    search_form = ProductionRecordSearchForm()
    
    # 构建基础查询
    query = Employee.query
    
    # 处理搜索
    if search_form.search.data:
        search_term = f"%{search_form.search.data}%"
        query = query.filter(db.or_(
            Employee.name.like(search_term),
            Employee.employee_id.like(search_term),
            Employee.department.like(search_term),
            Employee.position.like(search_term)
        ))
    
    # 分页
    page = request.validated_page
    pagination = query.paginate(page=page, per_page=request.validated_per_page)
    employees = pagination.items
    
    return render_template('main/employees.html',
                         employees=employees,
                         pagination=pagination,
                         search_form=search_form)

@bp.route('/employee/<int:id>', methods=['DELETE'])
@login_required
@require_capability('employee.delete')
def delete_employee(id):
    
    try:
        employee = Employee.query.get_or_404(id)
        
        # 保存旧数据用于回滚
        old_data = {
            'employee_id': employee.employee_id,
            'name': employee.name,
            'position': employee.position,
            'base_salary': employee.base_salary,
            'coefficient': employee.coefficient,
            'department': employee.department,
            'user_id': employee.user_id
        }
        
        # 记录可回滚的审计日志
        log = AuditLog(
            user_id=current_user.id,
            action='删除员工',
            details=f'删除员工：{employee.name}（工号：{employee.employee_id}）',
            can_rollback=True,
            rollback_type='delete',
            target_model='Employee',
            target_id=employee.id,
            old_data=old_data
        )
        db.session.add(log)
        
        # 级联删除相关记录
        ProductionRecord.query.filter_by(employee_id=id).delete()
        BonusPenalty.query.filter_by(employee_id=id).delete()
        
        db.session.delete(employee)
        db.session.commit()
        return jsonify({'success': True, 'message': '员工删除成功'})
    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(f'删除员工失败: {str(e)}')
        return jsonify({'success': False, 'message': '删除失败，请重试'}), 500

@bp.route('/employee/add', methods=['GET', 'POST'])
@login_required
@require_capability('employee.manage')
def add_employee():
    
    form = EmployeeForm()
    if form.validate_on_submit():
        # 检查工号是否已存在
        if Employee.query.filter_by(employee_id=form.employee_id.data).first():
            flash('工号已存在', 'danger')
            return render_template('main/employee_form.html', form=form, title='新增员工')
        
        # 检查用户名是否已存在
        if User.query.filter_by(username=form.employee_id.data).first():
            flash('该工号已被用作其他用户的用户名，请使用其他工号', 'danger')
            return render_template('main/employee_form.html', form=form, title='新增员工')
        
        # 创建用户账号
        user = User(
            username=form.employee_id.data,
            role='admin' if form.is_admin.data else 'user'
        )
        user.set_password(form.password.data or form.employee_id.data)  # 如果没有设置密码，使用工号作为密码
        db.session.add(user)
        
        # 创建员工记录
        employee = Employee(
            global_sn=SerialNumber.get_next_number(),
            employee_id=form.employee_id.data,
            name=form.name.data,
            position=form.position.data,
            base_salary=form.base_salary.data,
            coefficient=form.coefficient.data,
            department=form.department.data,
            hire_date=form.hire_date.data,
            termination_date=form.termination_date.data,
            is_active=True if not form.termination_date.data or form.termination_date.data > datetime.now().date() else False,
            user=user  # 关联用户账号
        )
        db.session.add(employee)
        db.session.flush()
        
        try:
            # 记录可回滚的审计日志
            log = AuditLog(
                user_id=current_user.id,
                action='添加员工',
                details=f'添加员工：{employee.name}（工号：{employee.employee_id}）',
                can_rollback=True,
                rollback_type='add',
                target_model='Employee',
                target_id=employee.id,
                new_data={
                    'employee_id': employee.employee_id,
                    'name': employee.name,
                    'position': employee.position,
                    'base_salary': employee.base_salary,
                    'coefficient': employee.coefficient,
                    'department': employee.department,
                    'hire_date': employee.hire_date.strftime('%Y-%m-%d'),
                    'termination_date': employee.termination_date.strftime('%Y-%m-%d') if employee.termination_date else None,
                    'is_active': employee.is_active,
                    'user_id': user.id
                }
            )
            db.session.add(log)
            db.session.commit()
            
            flash('员工添加成功', 'success')
            return redirect(url_for('main.manage_employees'))
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f'添加员工失败: {str(e)}')
            flash('操作失败，请重试', 'danger')
            return render_template('main/employee_form.html', form=form, title='新增员工')
    
    return render_template('main/employee_form.html', form=form, title='新增员工')

@bp.route('/employees/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@require_capability('employee.manage')
def edit_employee(id):
    
    employee = Employee.query.get_or_404(id)
    form = EmployeeForm()
    
    if form.validate_on_submit():
        try:
            # 检查工号是否已存在（排除当前员工）
            existing_employee = Employee.query.filter(
                Employee.employee_id == form.employee_id.data,
                Employee.id != id
            ).first()
            if existing_employee:
                flash('工号已存在', 'danger')
                return redirect(url_for('main.manage_employees'))
            
            # 保存旧数据用于回滚
            old_data = {
                'employee_id': employee.employee_id,
                'name': employee.name,
                'position': employee.position,
                'base_salary': employee.base_salary,
                'coefficient': employee.coefficient,
                'department': employee.department,
                'hire_date': employee.hire_date.strftime('%Y-%m-%d') if employee.hire_date else None,
                'termination_date': employee.termination_date.strftime('%Y-%m-%d') if employee.termination_date else None,
                'is_active': employee.is_active
            }
            
            # 检查工资是否变更
            salary_changed = employee.base_salary != form.base_salary.data
            coefficient_changed = employee.coefficient != form.coefficient.data
            
            # 更新数据
            employee.employee_id = form.employee_id.data
            employee.name = form.name.data
            employee.department = form.department.data
            employee.position = form.position.data
            employee.base_salary = form.base_salary.data
            employee.coefficient = form.coefficient.data
            employee.hire_date = form.hire_date.data
            employee.termination_date = form.termination_date.data
            employee.update_active_status()  # 根据入职和离职时间更新状态
            
            # 如果设置了新密码
            if form.password.data:
                employee.user.set_password(form.password.data)
            
            # 更新用户角色
            if current_user.role == 'admin':
                employee.user.role = 'admin' if form.is_admin.data else 'user'
            
            # 记录工资变更历史
            if salary_changed:
                salary_history = EmployeeSalaryHistory(
                    employee_id=employee.id,
                    old_salary=old_data['base_salary'],
                    new_salary=employee.base_salary,
                    effective_date=datetime.now().date(),
                    reason='员工信息更新',
                    created_by=current_user.id
                )
                db.session.add(salary_history)
            
            # 记录系数变更历史
            if coefficient_changed:
                coefficient_history = EmployeeCoefficientHistory(
                    employee_id=employee.id,
                    old_coefficient=old_data['coefficient'],
                    new_coefficient=employee.coefficient,
                    effective_date=datetime.now().date(),
                    reason='员工信息更新',
                    created_by=current_user.id
                )
                db.session.add(coefficient_history)
            
            # 记录审计日志
            log = AuditLog(
                user_id=current_user.id,
                action='编辑员工信息',
                details=f'编辑员工：{employee.name}（工号：{employee.employee_id}）',
                can_rollback=True,
                rollback_type='edit',
                target_model='Employee',
                target_id=employee.id,
                old_data=old_data,
                new_data={
                    'employee_id': employee.employee_id,
                    'name': employee.name,
                    'position': employee.position,
                    'base_salary': employee.base_salary,
                    'coefficient': employee.coefficient,
                    'department': employee.department,
                    'hire_date': employee.hire_date.strftime('%Y-%m-%d'),
                    'termination_date': employee.termination_date.strftime('%Y-%m-%d') if employee.termination_date else None,
                    'is_active': employee.is_active
                }
            )
            db.session.add(log)
            db.session.commit()
            
            flash('员工信息更新成功', 'success')
            return redirect(url_for('main.manage_employees'))
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f'更新员工信息失败: {str(e)}')
            flash('操作失败，请重试', 'danger')
    
    # GET请求时，填充表单数据
    if request.method == 'GET':
        form.employee_id.data = employee.employee_id
        form.name.data = employee.name
        form.department.data = employee.department
        form.position.data = employee.position
        form.base_salary.data = employee.base_salary
        form.coefficient.data = employee.coefficient
        form.hire_date.data = employee.hire_date
        form.termination_date.data = employee.termination_date
        if employee.user:
            form.is_admin.data = employee.user.role == 'admin'
    
    return render_template('main/employee_form.html', form=form, title='编辑员工信息', employee=employee)

@bp.route('/process_prices', methods=['GET'])
@login_required
@require_capability('process.view')
@handle_pagination_args
def process_prices():
    search_form = ProcessPriceSearchForm()
    
    # 从请求参数获取搜索条件
    search_form.search.data = request.args.get('search', '')
    search_form.show_all.data = request.args.get('show_all') == 'y'
    
    # 使用验证后的分页参数
    page = request.validated_page
    per_page = request.validated_per_page
    
    # 基本查询
    query = ProcessPrice.query

    # 处理搜索
    if search_form.search.data:
        search_term = f"%{search_form.search.data}%"
        query = query.filter(db.or_(
            ProcessPrice.process_code.like(search_term),
            ProcessPrice.process_name.like(search_term),
            ProcessPrice.component.like(search_term),
            ProcessPrice.drawing_no.like(search_term),
            ProcessPrice.model_no.like(search_term)
        ))

    # 如果不显示所有工序，则只显示当前生效的工序
    if not search_form.show_all.data:
        today = datetime.now().date()
        
        # 创建子查询，获取每个工序编号的最新生效版本
        latest_versions = db.session.query(
            ProcessPrice.process_code,
            db.func.max(ProcessPrice.effective_date).label('max_date')
        ).filter(ProcessPrice.effective_date <= today + timedelta(days=1))\
         .group_by(ProcessPrice.process_code)\
         .subquery()
        
        # 将主查询与子查询关联
        query = query.join(
            latest_versions,
            db.and_(
                ProcessPrice.process_code == latest_versions.c.process_code,
                ProcessPrice.effective_date == latest_versions.c.max_date
            )
        )

    # 处理排序
    sort_column = request.args.get('sort', 'process_code')
    sort_direction = request.args.get('direction', 'asc')
    
    if sort_column in ['process_code', 'process_name', 'component', 'drawing_no', 'model_no', 'price', 'effective_date']:
        column = getattr(ProcessPrice, sort_column)
        if sort_direction == 'desc':
            column = column.desc()
        query = query.order_by(column)
    else:
        query = query.order_by(ProcessPrice.process_code)

    pagination = query.paginate(page=page, per_page=per_page)
    process_prices = pagination.items

    # 获取每个工序的最新版本信息
    today = datetime.now().date()
    latest_versions = {}
    for process in process_prices:
        if process.process_code not in latest_versions:
            latest_version = ProcessPrice.query\
                .filter(ProcessPrice.process_code == process.process_code)\
                .filter(ProcessPrice.effective_date <= today + timedelta(days=1))\
                .order_by(ProcessPrice.effective_date.desc())\
                .first()
            latest_versions[process.process_code] = latest_version.id if latest_version else None

    return render_template('main/process_prices.html', 
                         process_prices=process_prices, 
                         pagination=pagination,
                         search_form=search_form,
                         current_sort=sort_column,
                         current_direction=sort_direction,
                         latest_versions=latest_versions,
                         today=today)
@bp.route('/add_process_price', methods=['GET', 'POST'])
@login_required
@require_capability('process.manage')
def add_process_price():
    """添加工序价格"""
    
    form = ProcessPriceForm()
    
    # 获取所有普通工序供小计选择
    normal_processes = ProcessPrice.query.filter_by(price_type='normal', is_current=True).all()
    form.included_processes.choices = [(p.id, f"{p.process_code} - {p.process_name} (单价: {p.price}元)") for p in normal_processes]
    
    # 获取可用的编码规则
    finished_rules = CodeRule.query.filter_by(code_type='product', is_active=True).all()
    raw_rules = CodeRule.query.filter_by(code_type='material', is_active=True).all()
    # 将编码规则数据传递给模板
    finished_rules_json = [{'id': r.id, 'name': r.name} for r in finished_rules]
    raw_rules_json = [{'id': r.id, 'name': r.name} for r in raw_rules]
    
    # 设置编码规则选项 - 修改此处，包含所有可能的选项
    all_rules = [(0, '请选择')]
    all_rules.extend([(r.id, r.name) for r in finished_rules])
    all_rules.extend([(r.id, r.name) for r in raw_rules])
    form.code_rule_id.choices = all_rules
    
    if form.validate_on_submit():
        try:
            # 如果是小计类型，计算总价
            price = form.price.data
            if form.price_type.data == 'subtotal':
                price = 0
                for process_id in form.included_processes.data:
                    process = ProcessPrice.query.get(process_id)
                    if process:
                        price += process.price

            # 创建新的工序价格记录
            process_price = ProcessPrice(
                global_sn=SerialNumber.get_next_number(),
                process_code=form.process_code.data,
                process_name=form.process_name.data,
                component=form.component.data,
                drawing_no=form.drawing_no.data,
                model_no=form.model_no.data,
                price=price,
                effective_date=form.effective_date.data,
                notes=form.notes.data,
                version=1,  # 新工序的初始版本为1
                is_current=True,  # 新工序默认为当前生效
                price_type=form.price_type.data,
                has_output=form.has_output.data,
                output_type=form.output_type.data if form.has_output.data else None,
                code_rule_id=form.code_rule_id.data if form.has_output.data and form.code_rule_id.data != 0 else None,
                needs_inspection=form.needs_inspection.data
            )
            db.session.add(process_price)
            db.session.flush()  # 获取process_price.id
            
            # 如果是小计类型，创建与普通工序的关联
            if form.price_type.data == 'subtotal' and form.included_processes.data:
                for process_id in form.included_processes.data:
                    group = ProcessPriceGroup(
                        subtotal_id=process_price.id,
                        process_id=process_id
                    )
                    db.session.add(group)
            
                # 记录可回滚的审计日志
            log = AuditLog(
            user_id=current_user.id,
            action='添加工序价格',
                details=f'添加工序：{process_price.process_name}，编号：{process_price.process_code}',
                can_rollback=True,
                rollback_type='add',
                target_model='ProcessPrice',
                target_id=process_price.id,
                new_data={
                    'process_code': process_price.process_code,
                    'process_name': process_price.process_name,
                    'component': process_price.component,
                    'drawing_no': process_price.drawing_no,
                    'model_no': process_price.model_no,
                    'price': process_price.price,
                    'version': process_price.version,
                    'effective_date': process_price.effective_date.isoformat() if process_price.effective_date else None,
                    'notes': process_price.notes,
                    'is_current': process_price.is_current,
                    'price_type': process_price.price_type,
                    'has_output': process_price.has_output,
                    'output_type': process_price.output_type,
                    'code_rule_id': process_price.code_rule_id,
                    'needs_inspection': process_price.needs_inspection
                }
        )
            db.session.add(log)
            db.session.commit()
            flash('工序价格添加成功', 'success')
            return redirect(url_for('main.process_prices'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'添加工序价格失败: {str(e)}')
            flash('操作失败，请重试', 'danger')
            return render_template('main/process_price_form.html', 
                                form=form, 
                                title='新增工序价格',
                                finished_rules_json=finished_rules_json,
                                raw_rules_json=raw_rules_json)
    
    return render_template('main/process_price_form.html', 
                         form=form, 
                         title='新增工序价格',
                         finished_rules_json=finished_rules_json,
                         raw_rules_json=raw_rules_json)
@bp.route('/process_prices/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@require_capability('process.manage')
def edit_process_price(id):
    
    process_price = ProcessPrice.query.get_or_404(id)
    form = ProcessPriceForm()
    
    # 获取所有普通工序供小计选择（排除当前工序）
    normal_processes = ProcessPrice.query.filter(
        ProcessPrice.price_type == 'normal',
        ProcessPrice.id != id,
        ProcessPrice.is_current == True
    ).all()
    form.included_processes.choices = [(p.id, f"{p.process_code} - {p.process_name} (单价: {p.price}元)") for p in normal_processes]
    
    # 获取可用的编码规则
    finished_rules = CodeRule.query.filter_by(code_type='product', is_active=True).all()
    raw_rules = CodeRule.query.filter_by(code_type='material', is_active=True).all()
    # 将编码规则数据传递给模板
    finished_rules_json = [{'id': r.id, 'name': r.name} for r in finished_rules]
    raw_rules_json = [{'id': r.id, 'name': r.name} for r in raw_rules]
    
    # 设置编码规则选项 - 修改此处，包含所有可能的选项
    all_rules = [(0, '请选择')]
    all_rules.extend([(r.id, r.name) for r in finished_rules])
    all_rules.extend([(r.id, r.name) for r in raw_rules])
    form.code_rule_id.choices = all_rules
    
    if form.validate_on_submit():
        try:
            # 保存旧数据用于回滚
            old_data = {
                'process_code': process_price.process_code,
                'process_name': process_price.process_name,
                'component': process_price.component,
                'drawing_no': process_price.drawing_no,
                'model_no': process_price.model_no,
                'price': process_price.price,
                'effective_date': process_price.effective_date.isoformat() if process_price.effective_date else None,
                'notes': process_price.notes,
                'version': process_price.version,
                'is_current': process_price.is_current,
                'price_type': process_price.price_type,
                'has_output': process_price.has_output,
                'output_type': process_price.output_type,
                'code_rule_id': process_price.code_rule_id,
                'needs_inspection': process_price.needs_inspection
            }
            
            # 如果是小计类型，计算总价
            price = form.price.data
            if form.price_type.data == 'subtotal':
                price = 0
                for process_id in form.included_processes.data:
                    process = ProcessPrice.query.get(process_id)
                    if process:
                        price += process.price
            
            # 更新数据
            process_price.process_code = form.process_code.data
            process_price.process_name = form.process_name.data
            process_price.component = form.component.data
            process_price.drawing_no = form.drawing_no.data
            process_price.model_no = form.model_no.data
            process_price.price = price
            process_price.effective_date = form.effective_date.data
            process_price.notes = form.notes.data
            process_price.price_type = form.price_type.data
            process_price.has_output = form.has_output.data
            process_price.output_type = form.output_type.data if form.has_output.data else None
            process_price.code_rule_id = form.code_rule_id.data if form.has_output.data and form.code_rule_id.data != 0 else None
            process_price.needs_inspection = form.needs_inspection.data
            
            # 更新小计关联
            if form.price_type.data == 'subtotal':
                # 删除旧的关联
                ProcessPriceGroup.query.filter_by(subtotal_id=id).delete()
                # 创建新的关联
                for process_id in form.included_processes.data:
                    group = ProcessPriceGroup(
                        subtotal_id=id,
                        process_id=process_id
                    )
                    db.session.add(group)
            
            # 记录可回滚的审计日志
            log = AuditLog(
                user_id=current_user.id,
                action='修改工序价格',
                details=f'修改工序 {process_price.process_name}（编号：{process_price.process_code}）的价格信息',
                can_rollback=True,
                rollback_type='edit',
                target_model='ProcessPrice',
                target_id=process_price.id,
                old_data=old_data,
                new_data={
                    'process_code': process_price.process_code,
                    'process_name': process_price.process_name,
                    'component': process_price.component,
                    'drawing_no': process_price.drawing_no,
                    'model_no': process_price.model_no,
                    'price': process_price.price,
                    'effective_date': process_price.effective_date.isoformat() if process_price.effective_date else None,
                    'notes': process_price.notes,
                    'version': process_price.version,
                    'is_current': process_price.is_current,
                    'price_type': process_price.price_type,
                    'has_output': process_price.has_output,
                    'output_type': process_price.output_type,
                    'code_rule_id': process_price.code_rule_id,
                    'needs_inspection': process_price.needs_inspection
                }
            )
            db.session.add(log)
            db.session.commit()
            
            flash('工序价格修改成功', 'success')
            return redirect(url_for('main.process_prices'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'修改工序价格失败: {str(e)}')
            flash('操作失败，请重试', 'danger')
            return render_template('main/process_price_form.html', 
                                form=form, 
                                title='编辑工序价格', 
                                employee=process_price,
                                finished_rules_json=finished_rules_json,
                                raw_rules_json=raw_rules_json)
    
    # 如果是GET请求，填充表单数据
    if request.method == 'GET':
        form.process_code.data = process_price.process_code
        form.process_name.data = process_price.process_name
        form.component.data = process_price.component
        form.drawing_no.data = process_price.drawing_no
        form.model_no.data = process_price.model_no
        form.price.data = process_price.price
        form.effective_date.data = process_price.effective_date
        form.notes.data = process_price.notes
        form.price_type.data = process_price.price_type
        form.has_output.data = process_price.has_output
        form.output_type.data = process_price.output_type or ''
        form.code_rule_id.data = process_price.code_rule_id or 0
        form.needs_inspection.data = process_price.needs_inspection

        # 如果是小计，获取包含的工序
        if process_price.price_type == 'subtotal':
            included_process_ids = [group.process_id for group in process_price.included_processes]
            form.included_processes.data = included_process_ids
            
    # 添加代码规则ID初始值，传递给JS使用
    code_rule_id_initial = process_price.code_rule_id if process_price.code_rule_id else 0
    
    return render_template(
        'main/process_price_form.html',
        title='编辑工序价格',
        form=form,
        process_price=process_price,
        finished_rules_json=finished_rules_json,
        raw_rules_json=raw_rules_json,
        code_rule_id_initial=code_rule_id_initial
    )

@bp.route('/process_price/<int:id>', methods=['DELETE'])
@login_required
@require_capability('process.delete')
def delete_process_price(id):
    
    try:
        process = ProcessPrice.query.get_or_404(id)
        
        # 保存旧数据用于回滚
        old_data = {
            'process_code': process.process_code,
            'process_name': process.process_name,
            'component': process.component,
            'drawing_no': process.drawing_no,
            'model_no': process.model_no,
            'price': process.price,
            'version': process.version,
            'effective_date': process.effective_date.isoformat() if process.effective_date else None,
            'notes': process.notes,
            'is_current': process.is_current,
            'output_type': process.output_type,
            'code_rule_id': process.code_rule_id,
            'needs_inspection': process.needs_inspection
        }
        
        # 记录可回滚的审计日志
        log = AuditLog(
            user_id=current_user.id,
            action='删除工序价格',
            details=f'删除工序：{process.process_name}（编号：{process.process_code}）',
            can_rollback=True,
            rollback_type='delete',
            target_model='ProcessPrice',
            target_id=process.id,
            old_data=old_data
        )
        db.session.add(log)
        
        db.session.delete(process)
        db.session.commit()
        return jsonify({'success': True, 'message': '工序删除成功'})
    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(f'删除工序失败: {str(e)}')
        return jsonify({'success': False, 'message': '删除失败，请重试'}), 500

@bp.route('/salary/<int:employee_id>')
@login_required
@require_capability('salary.view')
def salary_details(employee_id):
    employee = Employee.query.get_or_404(employee_id)
    production_records = ProductionRecord.query.filter_by(employee_id=employee_id).all()
    bonuses_penalties = BonusPenalty.query.filter_by(employee_id=employee_id).all()
    return render_template('main/salary_details.html',
                         employee=employee,
                         production_records=production_records,
                         bonuses_penalties=bonuses_penalties,
                         total_salary=employee.total_salary)

@bp.route('/production_records', methods=['GET', 'POST'])
@login_required
@require_capability('production_record.view')
@handle_pagination_args
def manage_production_records():
    """管理生产记录"""
    form = ProductionRecordForm()
    search_form = ProductionRecordSearchForm(request.args)
    
    # 获取所有员工
    employees = Employee.query.filter_by(is_active=True).all()
    form.employee_id.choices = [(0, '请选择员工')] + [(e.id, f"{e.employee_id} - {e.name} ({e.department})") for e in employees]

    # 获取所有当前生效的工序
    today = datetime.now().date()
    
    # 创建子查询，获取每个工序编号的最新生效版本
    latest_versions = db.session.query(
        ProcessPrice.process_code,
        db.func.max(ProcessPrice.effective_date).label('max_date')
    ).filter(ProcessPrice.effective_date <= today + timedelta(days=1))\
     .group_by(ProcessPrice.process_code)\
     .subquery()
    
    # 获取当前生效的工序
    current_processes = ProcessPrice.query.join(
        latest_versions,
        db.and_(
            ProcessPrice.process_code == latest_versions.c.process_code,
            ProcessPrice.effective_date == latest_versions.c.max_date
        )
    ).order_by(ProcessPrice.process_code).all()
    
    # 设置工序选项
    form.process_id.choices = [(0, '请选择工序')] + [(p.id, f"{p.process_code} - {p.process_name} ({p.component or ''} {p.drawing_no or ''} {p.model_no or ''})".strip()) for p in current_processes]

    # 获取可用的原材料列表 - 用于前端展示
    available_raw_materials = RawMaterial.query.filter(RawMaterial.quantity > 0).all()
    raw_materials_json = [{
        'id': m.id,
        'name': m.material_name,
        'quantity': m.quantity
    } for m in available_raw_materials]

    if form.validate_on_submit():
        try:
            # 验证选择的值
            if form.employee_id.data == 0:
                flash('请选择员工', 'danger')
                return redirect(url_for('main.manage_production_records'))
            if form.process_id.data == 0:
                flash('请选择工序', 'danger')
                return redirect(url_for('main.manage_production_records'))
            
            record = ProductionRecord(
                global_sn=SerialNumber.get_next_number(),
                employee_id=form.employee_id.data,
                process_id=form.process_id.data,
                quantity=form.quantity.data,
                date=form.date.data,
                notes=form.notes.data
            )
            
            if form.inspector.data:
                # 获取工序信息
                process = ProcessPrice.query.get(form.process_id.data)
                
                # 生成产品编号
                if process and process.code_rule_id:
                    # 如果工序有关联的编码规则，使用该规则生成编号
                    code_rule = CodeRule.query.get(process.code_rule_id)
                    if code_rule and code_rule.is_active:
                        product_number = code_rule.generate_code()
                    else:
                        product_number = SerialNumber.get_next_number()
                else:
                    product_number = SerialNumber.get_next_number()
                
                # 如果提供了检验员信息，创建成品记录
                finished_product = FinishedProduct(
                    global_sn=SerialNumber.get_next_number(),
                    serial_number=SerialNumber.get_next_number(),
                    product_number=product_number,  # 使用生成的产品编号
                    production_date=form.date.data,  # 使用生产记录的日期
                    drawing_number=process.drawing_no if process and process.drawing_no else "未知",  # 使用工序的图号
                    model=process.model_no if process and process.model_no else "未知",  # 使用工序的型号
                    inspector=form.inspector.data,
                    quantity=1,  # 默认数量为1
                    status='in_stock'  # 默认状态为在库
                )
                db.session.add(finished_product)
                db.session.flush()  # 获取成品ID
                record.finished_product_id = finished_product.id
            
            db.session.add(record)
            db.session.flush()  # 获取生产记录ID
            
            # 处理多个原材料
            material_data = []
            for key, value in request.form.items():
                if key.startswith('material_data_'):
                    try:
                        data = json.loads(value)
                        material_data.append(data)
                    except (json.JSONDecodeError, ValueError) as e:
                        current_app.logger.error(f"解析材料数据失败: {str(e)}")
                        continue
            
            # 添加原材料关联记录
            for data in material_data:
                material_id = data.get('id')
                quantity = data.get('quantity')
                
                if material_id and quantity:
                    # 获取原材料
                    raw_material = RawMaterial.query.get(material_id)
                    if raw_material:
                        # 检查库存是否足够
                        if raw_material.quantity >= float(quantity):
                            # 创建关联记录
                            record_material = ProductionRecordMaterial(
                                production_record_id=record.id,
                                raw_material_id=material_id,
                                quantity=float(quantity)
                            )
                            db.session.add(record_material)
                            
                            # 更新原材料库存
                            old_quantity = raw_material.quantity
                            raw_material.quantity -= float(quantity)
                            
                            # 如果原材料数量耗尽（小于等于0），将状态修改为已使用
                            if raw_material.quantity <= 0:
                                raw_material.status = 'used'
                                # 记录状态变更的审计日志
                                status_log = AuditLog(
                                    user_id=current_user.id,
                                    action='自动更新原材料状态',
                                    details=f'原材料 {raw_material.material_name} 数量耗尽，状态自动更新为已使用',
                                    can_rollback=True,
                                    rollback_type='edit',
                                    target_model='RawMaterial',
                                    target_id=raw_material.id,
                                    old_data={'status': 'in_stock', 'quantity': old_quantity},
                                    new_data={'status': 'used', 'quantity': raw_material.quantity}
                                )
                                db.session.add(status_log)
                        else:
                            db.session.rollback()
                            flash(f'原材料 {raw_material.material_name} 库存不足！', 'danger')
                            return redirect(url_for('main.manage_production_records'))
            
            # 添加审计日志
            log = AuditLog(
            user_id=current_user.id,
            action='添加生产记录',
                details=f'添加生产记录：员工 {Employee.query.get(form.employee_id.data).name}，工序 {ProcessPrice.query.get(form.process_id.data).process_name}，数量 {form.quantity.data}',
                can_rollback=True,
                rollback_type='add',
                target_model='ProductionRecord',
                target_id=record.id
        )
            db.session.add(log)

            db.session.commit()
            flash('生产记录添加成功', 'success')
            return redirect(url_for('main.manage_production_records'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'添加生产记录失败: {str(e)}')
            flash(f'添加失败：{str(e)}', 'danger')
            return redirect(url_for('main.manage_production_records'))

    # 处理搜索和排序
    query = ProductionRecord.query.join(Employee).join(ProcessPrice)
    
    # 获取搜索参数
    search_term_input = request.args.get('search', '').strip()
    if search_term_input:
        search_term = f"%{search_term_input}%"
        
        # 构建基本搜索条件
        search_conditions = [
            ProductionRecord.global_sn.like(search_term),
            Employee.name.like(search_term),
            Employee.employee_id.like(search_term),
            ProcessPrice.process_code.like(search_term),
            ProcessPrice.process_name.like(search_term),
            ProcessPrice.component.like(search_term),
            ProcessPrice.drawing_no.like(search_term),
            ProcessPrice.model_no.like(search_term)
        ]
        
        # 添加原材料搜索条件
        try:
            # 搜索通过 ProductionRecordMaterial 关联的原材料
            material_ids = db.session.query(ProductionRecordMaterial.production_record_id).join(
                RawMaterial, ProductionRecordMaterial.raw_material_id == RawMaterial.id
            ).join(
                RawMaterialCategory, RawMaterial.category_id == RawMaterialCategory.id
            ).filter(db.or_(
                RawMaterialCategory.name.like(search_term),
                RawMaterial.internal_number.like(search_term)
            )).distinct().all()
            
            if material_ids:
                material_record_ids = [row[0] for row in material_ids]
                search_conditions.append(ProductionRecord.id.in_(material_record_ids))
            
            # 搜索直接关联的原材料
            direct_material_ids = db.session.query(ProductionRecord.id).join(
                RawMaterial, ProductionRecord.raw_material_id == RawMaterial.id
            ).join(
                RawMaterialCategory, RawMaterial.category_id == RawMaterialCategory.id
            ).filter(db.or_(
                RawMaterialCategory.name.like(search_term),
                RawMaterial.internal_number.like(search_term)
            )).distinct().all()
            
            if direct_material_ids:
                direct_record_ids = [row[0] for row in direct_material_ids]
                search_conditions.append(ProductionRecord.id.in_(direct_record_ids))
                
        except Exception as e:
            current_app.logger.error(f'原材料搜索失败: {str(e)}')
            # 如果原材料搜索失败，继续使用基本搜索条件
        
        query = query.filter(db.or_(*search_conditions))

    # 处理排序
    sort_column = request.args.get('sort', 'date')
    sort_direction = request.args.get('direction', 'desc')
    
    # 定义排序映射
    sort_mapping = {
        'global_sn': ProductionRecord.global_sn,
        'date': ProductionRecord.date,
        'employee_name': Employee.name,
        'process_code': ProcessPrice.process_code,
        'process_name': ProcessPrice.process_name,
        'component': ProcessPrice.component,
        'quantity': ProductionRecord.quantity
    }
    
    # 应用排序
    if sort_column in sort_mapping:
        column = sort_mapping[sort_column]
        if sort_direction == 'desc':
            column = column.desc()
        query = query.order_by(column)
    else:
        # 默认按日期降序排序
        query = query.order_by(ProductionRecord.date.desc())

    # 分页
    page = request.validated_page
    pagination = query.paginate(page=page, per_page=request.validated_per_page)
    records = pagination.items

    return render_template('main/production_records.html',
                         form=form,
                         search_form=search_form,
                         records=records,
                         pagination=pagination,
                         current_sort=sort_column,
                         current_direction=sort_direction,
                         raw_materials=raw_materials_json)

@bp.route('/delete_production_record/<int:id>', methods=['DELETE'])
@login_required
@require_capability('production_record.manage')
def delete_production_record(id):
    
    try:
        record = ProductionRecord.query.get_or_404(id)
        
        # 保存旧数据用于回滚
        old_data = {
            'employee_id': record.employee_id,
            'process_id': record.process_id,
            'quantity': record.quantity,
            'date': record.date.isoformat() if record.date else None,
            'notes': record.notes,
            'materials': []
        }
        
        # 恢复所有使用的原材料库存
        for material in record.materials:
            # 保存原材料数据用于回滚
            old_data['materials'].append({
                'material_id': material.raw_material_id,
                'quantity': material.quantity
            })
            
            # 恢复库存
            if material.raw_material:
                old_quantity = material.raw_material.quantity
                old_status = material.raw_material.status
                material.raw_material.quantity += material.quantity
                
                # 如果原材料状态是"已使用"且恢复库存后数量大于0，将状态改回"在库"
                if material.raw_material.status == 'used' and material.raw_material.quantity > 0:
                    material.raw_material.status = 'in_stock'
                    # 记录状态变更的审计日志
                    status_log = AuditLog(
                        user_id=current_user.id,
                        action='自动恢复原材料状态',
                        details=f'删除生产记录后，原材料 {material.raw_material.material_name} 库存恢复，状态自动更新为在库',
                        can_rollback=True,
                        rollback_type='edit',
                        target_model='RawMaterial',
                        target_id=material.raw_material.id,
                        old_data={'status': old_status, 'quantity': old_quantity},
                        new_data={'status': 'in_stock', 'quantity': material.raw_material.quantity}
                    )
                    db.session.add(status_log)
        
        # 如果使用旧方式存储了原材料，也需要恢复
        if record.raw_material and record.raw_material_quantity:
            # 保存原材料数据用于回滚
            old_data['raw_material_id'] = record.raw_material_id
            old_data['raw_material_quantity'] = record.raw_material_quantity
            
            # 恢复库存
            old_quantity = record.raw_material.quantity
            old_status = record.raw_material.status
            record.raw_material.quantity += record.raw_material_quantity
            
            # 如果原材料状态是"已使用"且恢复库存后数量大于0，将状态改回"在库"
            if record.raw_material.status == 'used' and record.raw_material.quantity > 0:
                record.raw_material.status = 'in_stock'
                # 记录状态变更的审计日志
                status_log = AuditLog(
                    user_id=current_user.id,
                    action='自动恢复原材料状态',
                    details=f'删除生产记录后，原材料 {record.raw_material.material_name} 库存恢复，状态自动更新为在库',
                    can_rollback=True,
                    rollback_type='edit',
                    target_model='RawMaterial',
                    target_id=record.raw_material.id,
                    old_data={'status': old_status, 'quantity': old_quantity},
                    new_data={'status': 'in_stock', 'quantity': record.raw_material.quantity}
                )
                db.session.add(status_log)
        
        # 记录审计日志
        log = AuditLog(
            user_id=current_user.id,
            action='删除生产记录',
            details=f'删除生产记录：员工 {record.employee.name}，工序 {record.process.process_name}，数量 {record.quantity}',
            can_rollback=True,
            rollback_type='delete',
            target_model='ProductionRecord',
            target_id=record.id,
            old_data=old_data
        )
        db.session.add(log)
        
        # 删除记录及其关联的原材料记录
        db.session.delete(record)  # 由于材料上的cascade设置，关联的材料记录会被自动删除
        db.session.commit()
        
        return jsonify({'success': True, 'message': '生产记录删除成功'})
    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(f'删除生产记录失败: {str(e)}')
        return jsonify({'success': False, 'message': '删除失败，请重试'}), 500
@bp.route('/bonus_penalties', methods=['GET', 'POST'])
@login_required
@require_capability('bonus.manage')
@handle_pagination_args
def manage_bonus_penalties():
    """管理奖惩记录"""
    
    form = BonusPenaltyForm()
    search_form = BonusPenaltySearchForm()
    
    # 获取所有员工
    employees = Employee.query.all()
    form.employee_id.choices = [(e.id, f"{e.employee_id} - {e.name} ({e.department})") for e in employees]
    
    # 获取所有当前生效的工序
    today = datetime.now().date()
    latest_versions = db.session.query(
        ProcessPrice.process_code,
        db.func.max(ProcessPrice.effective_date).label('max_date')
    ).filter(ProcessPrice.effective_date <= today)\
     .group_by(ProcessPrice.process_code)\
     .subquery()
    
    current_processes = ProcessPrice.query.join(
        latest_versions,
        db.and_(
            ProcessPrice.process_code == latest_versions.c.process_code,
            ProcessPrice.effective_date == latest_versions.c.max_date
        )
    ).order_by(ProcessPrice.process_code).all()
    
    form.process_id.choices = [(0, '无')] + [(p.id, f"{p.process_code} - {p.process_name} ({p.component or ''} {p.drawing_no or ''} {p.model_no or ''})".strip()) for p in current_processes]
    
    # 构建查询
    query = BonusPenalty.query.join(Employee)
    
    # 处理搜索条件
    if request.args.get('search'):
        search_term = f"%{request.args.get('search')}%"
        query = query.filter(db.or_(
            Employee.name.like(search_term),
            Employee.employee_id.like(search_term),
            BonusPenalty.reason.like(search_term)
        ))
    
    if request.args.get('type'):
        query = query.filter(BonusPenalty.type == request.args.get('type'))
    
    if request.args.get('start_date'):
        try:
            start_date = datetime.strptime(request.args.get('start_date'), '%Y-%m-%d')
            query = query.filter(BonusPenalty.date >= start_date)
        except (ValueError, TypeError):
            pass
    
    if request.args.get('end_date'):
        try:
            end_date = datetime.strptime(request.args.get('end_date'), '%Y-%m-%d')
            query = query.filter(BonusPenalty.date <= end_date)
        except (ValueError, TypeError):
            pass
    
    # 处理排序
    sort_column = request.args.get('sort', 'date')
    sort_direction = request.args.get('direction', 'desc')
    
    # 定义排序映射
    sort_mapping = {
        'date': BonusPenalty.date,
        'employee_name': Employee.name,
        'type': BonusPenalty.type,
        'amount': BonusPenalty.amount
    }
    
    if sort_column in sort_mapping:
        column = sort_mapping[sort_column]
        if sort_direction == 'desc':
            column = column.desc()
        query = query.order_by(column)
    else:
        query = query.order_by(BonusPenalty.date.desc())

    # 分页
    pagination = query.paginate(page=request.validated_page, per_page=request.validated_per_page)
    records = pagination.items

    # 从请求参数填充搜索表单
    search_form.search.data = request.args.get('search', '')
    search_form.type.data = request.args.get('type', '')
    if request.args.get('start_date'):
        try:
            search_form.start_date.data = datetime.strptime(request.args.get('start_date'), '%Y-%m-%d')
        except (ValueError, TypeError):
            pass
    if request.args.get('end_date'):
        try:
            search_form.end_date.data = datetime.strptime(request.args.get('end_date'), '%Y-%m-%d')
        except (ValueError, TypeError):
            pass

    return render_template('main/bonus_penalties.html',
                         form=form,
                         search_form=search_form,
                         records=records,
                         pagination=pagination,
                         current_sort=sort_column,
                         current_direction=sort_direction)

@bp.route('/bonus_penalty/<int:id>', methods=['DELETE'])
@login_required
@require_capability('bonus.manage')
def delete_bonus_penalty(id):
    
    try:
        record = BonusPenalty.query.get_or_404(id)
        
        # 记录可回滚的审计日志
        log = AuditLog(
            user_id=current_user.id,
            action='删除奖惩记录',
            details=f'删除{"奖金" if record.type == "bonus" else "罚款"}记录：员工 {record.employee.name}，金额 {record.amount}',
            can_rollback=True,
            rollback_type='delete',
            target_model='BonusPenalty',
            target_id=record.id,
            old_data={
                'employee_id': record.employee_id,
                'type': record.type,
                'amount': record.amount,
                'reason': record.reason,
                'date': record.date.isoformat() if record.date else None
            }
        )
        db.session.add(log)
        
        db.session.delete(record)
        db.session.commit()
        return jsonify({'success': True, 'message': '记录删除成功'})
    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(f'删除奖惩记录失败: {str(e)}')
        return jsonify({'success': False, 'message': '删除失败，请重试'}), 500

@bp.route('/bonus_penalties/<int:id>/edit', methods=['POST'])
@login_required
@require_capability('bonus.manage')
def edit_bonus_penalty(id):
    
    form = BonusPenaltyForm()
    if form.validate_on_submit():
        try:
            record = BonusPenalty.query.get_or_404(id)
            
            # 保存旧数据用于回滚
            old_data = {
                'employee_id': record.employee_id,
                'type': record.type,
                'amount': record.amount,
                'reason': record.reason,
                'date': record.date.isoformat() if record.date else None
            }
            
            # 更新数据
            record.employee_id = form.employee_id.data
            record.type = form.type.data
            record.amount = form.amount.data
            record.reason = form.reason.data
            record.date = form.date.data
            
            # 记录可回滚的审计日志
            log = AuditLog(
                user_id=current_user.id,
                action='修改奖金/罚款记录',
                details=f'修改奖金/罚款记录（ID：{record.id}）',
                can_rollback=True,
                rollback_type='edit',
                target_model='BonusPenalty',
                target_id=record.id,
                old_data=old_data,
                new_data={
                    'employee_id': record.employee_id,
                    'type': record.type,
                    'amount': record.amount,
                    'reason': record.reason,
                    'date': record.date.isoformat() if record.date else None
                }
            )
            db.session.add(log)
            
            db.session.commit()
            flash('记录修改成功', 'success')
            return redirect(url_for('main.manage_bonus_penalties'))
        except Exception as e:
            _reraise_http(e)
            db.session.rollback()
            flash('修改失败，请重试', 'danger')
            return redirect(url_for('main.manage_bonus_penalties'))
    return render_template('main/edit_bonus_penalty.html', form=form, record=record)
@bp.route('/bonus_penalties/add', methods=['POST'])
@login_required
@require_capability('bonus.manage')
def add_bonus_penalty():
    """添加奖金/罚款记录"""
    
    try:
        data = request.get_json()
        
        # 创建新的奖金/罚款记录
        bonus_penalty = BonusPenalty(
            global_sn=SerialNumber.get_next_number(),
            employee_id=data.get('employee_id'),
            amount=data.get('amount'),
            reason=data.get('reason'),
            date=datetime.strptime(data.get('date'), '%Y-%m-%d').date(),
            type=data.get('type'),
            process_id=data.get('process_id')
        )
        db.session.add(bonus_penalty)
        db.session.flush()  # 获取bonus_penalty.id
        
        # 记录可回滚的审计日志
        log = AuditLog(
            user_id=current_user.id,
            action='添加奖金/罚款记录',
            details=f'添加{"奖金" if bonus_penalty.type == "bonus" else "罚款"}记录：员工ID {bonus_penalty.employee_id}，金额 {bonus_penalty.amount}',
            can_rollback=True,
            rollback_type='add',
            target_model='BonusPenalty',
            target_id=bonus_penalty.id,
            new_data={
                'employee_id': bonus_penalty.employee_id,
                'type': bonus_penalty.type,
                'amount': bonus_penalty.amount,
                'reason': bonus_penalty.reason,
                'date': bonus_penalty.date.isoformat() if bonus_penalty.date else None,
                'process_id': bonus_penalty.process_id
            }
        )
        db.session.add(log)
        db.session.commit()
        flash('记录添加成功', 'success')
        return redirect(url_for('main.manage_bonus_penalties'))
    except Exception as e:
        db.session.rollback()
        flash('添加失败，请重试', 'danger')
        current_app.logger.error(f'添加奖金/罚款记录失败: {str(e)}')
        return redirect(url_for('main.manage_bonus_penalties'))

@bp.route('/salary_calculation', methods=['GET', 'POST'])
@login_required
@require_capability('salary.view')
def salary_calculation():
    
    form = SalaryCalculationForm()
    
    # 获取所有部门
    departments = [(d[0], d[0]) for d in db.session.query(Employee.department).distinct().all()]
    form.department.choices = [('', '全部')] + departments
    
    # 获取所有员工
    employees = Employee.query.order_by(Employee.name).all()
    form.employee_id.choices = [(0, '全部')] + [(e.id, f"{e.employee_id} - {e.name} ({e.department})") for e in employees]
    
    if form.validate_on_submit():
        start_date = form.start_date.data
        end_date = form.end_date.data
        department = form.department.data
        employee_id = form.employee_id.data
        
        # 构建查询
        query = Employee.query
        
        # 如果选择了特定员工，则只查询该员工
        if employee_id and employee_id != 0:
            query = query.filter_by(id=employee_id)
        # 否则，如果选择了部门，则按部门筛选
        elif department:
            query = query.filter_by(department=department)
        
        employees = query.all()
        
        # 计算每个员工的工资
        salary_data = []
        total_stats = {
            'base_salary': 0,
            'piecework': 0,
            'bonus': 0,
            'penalty': 0,
            'total_salary': 0
        }
        
        for employee in employees:
            # 获取指定日期范围内的生产记录
            production_records = ProductionRecord.query.filter(
                ProductionRecord.employee_id == employee.id,
                ProductionRecord.date.between(start_date, end_date)
            ).all()
            
            # 获取指定日期范围内的奖金/罚款记录
            bonus_penalty_records = BonusPenalty.query.filter(
                BonusPenalty.employee_id == employee.id,
                BonusPenalty.date.between(start_date, end_date)
            ).all()
            
            # 计算工资
            base_salary = employee.base_salary
            piecework = sum(record.quantity * record.process.price for record in production_records)
            piecework = piecework * employee.coefficient
            bonus = sum(bp.amount for bp in bonus_penalty_records if bp.type == 'bonus')
            penalty = sum(bp.amount for bp in bonus_penalty_records if bp.type == 'penalty')
            total_salary = base_salary + piecework + bonus - penalty
            
            # 更新总计
            total_stats['base_salary'] += base_salary
            total_stats['piecework'] += piecework
            total_stats['bonus'] += bonus
            total_stats['penalty'] += penalty
            total_stats['total_salary'] += total_salary
            
            salary_data.append({
                'employee': employee,
                'base_salary': base_salary,
                'piecework': piecework,
                'bonus': bonus,
                'penalty': penalty,
                'total_salary': total_salary,
                'production_records': production_records,
                'bonus_penalty_records': bonus_penalty_records
            })
        
        return render_template('main/salary_calculation.html', 
                             form=form, 
                             salary_data=salary_data,
                             total_stats=total_stats,
                             start_date=start_date,
                             end_date=end_date)
    
    return render_template('main/salary_calculation.html', form=form)

@bp.route('/audit_logs', methods=['GET', 'POST'])
@login_required
@require_capability('audit.view')
@handle_pagination_args
def view_audit_logs():
    
    form = AuditLogSearchForm()
    # 获取所有用户供选择
    form.user_id.choices = [(0, '全部')] + [(u.id, u.username) for u in User.query.all()]
    
    # 修改查询，明确指定join条件
    query = AuditLog.query.join(
        User,
        AuditLog.user_id == User.id
    ).order_by(desc(AuditLog.timestamp))
    
    if form.validate_on_submit():
        if form.start_date.data:
            query = query.filter(AuditLog.timestamp >= form.start_date.data)
        if form.end_date.data:
            # 将结束日期设置为当天的最后一秒
            end_date = datetime.combine(form.end_date.data, datetime.max.time())
            query = query.filter(AuditLog.timestamp <= end_date)
        if form.action.data:
            query = query.filter(AuditLog.action == form.action.data)
        if form.user_id.data and form.user_id.data != 0:
            query = query.filter(AuditLog.user_id == form.user_id.data)
    
    # 分页（统一走 @handle_pagination_args 的白名单口径）
    page = request.validated_page
    pagination = query.paginate(page=page, per_page=request.validated_per_page, error_out=False)
    logs = pagination.items
    
    return render_template('main/audit_logs.html', 
                         form=form, 
                         logs=logs, 
                         pagination=pagination)

@bp.route('/employees/template')
@login_required
@require_capability('employee.manage')
def download_employee_template():
    """下载员工导入模板"""
    
    temp_path = None
    try:
        wb = ExcelGenerator.create_employee_template()
        filename = 'employee_template.xlsx'
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        
        # 确保文件写入完成
        time.sleep(0.1)
        
        return send_file(
            buf,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        flash(f'下载模板失败：{str(e)}', 'danger')
        return redirect(url_for('main.manage_employees'))
    finally:
        # 确保在请求结束后删除临时文件
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass

@bp.route('/employees/import', methods=['POST'])
@login_required
@require_capability('employee.manage')
def import_employees():
    """导入员工数据"""
    
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': '没有上传文件'})
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'message': '没有选择文件'})
    
    if not file.filename.endswith('.xlsx'):
        return jsonify({'success': False, 'message': '请上传Excel文件(.xlsx)'})
    
    temp_path = None
    try:
        filename = secure_filename(file.filename)
        temp_path = os.path.join(current_app.config['TEMP_FOLDER'], filename)
        file.save(temp_path)
        
        # 解析Excel数据
        try:
            employee_data = ExcelGenerator.parse_employee_data(temp_path)
        except Exception as e:
            return jsonify({'success': False, 'message': f'Excel文件解析失败：{str(e)}。请检查文件格式是否正确。'})
        
        if not employee_data:
            return jsonify({'success': False, 'message': 'Excel文件中没有找到有效数据。请检查文件内容。'})
        
        success_count = 0
        error_messages = []
        warning_messages = []
        
        # 数据验证
        for i, data in enumerate(employee_data, 1):
            row_errors = []
            
            # 必填字段验证
            if not data.get('employee_id'):
                row_errors.append('工号不能为空')
            elif len(str(data['employee_id']).strip()) == 0:
                row_errors.append('工号不能为空字符串')
            elif len(str(data['employee_id'])) > 20:
                row_errors.append('工号长度不能超过20个字符')
            
            if not data.get('name'):
                row_errors.append('姓名不能为空')
            elif len(str(data['name']).strip()) == 0:
                row_errors.append('姓名不能为空字符串')
            elif len(str(data['name'])) > 50:
                row_errors.append('姓名长度不能超过50个字符')
            
            if not data.get('position'):
                row_errors.append('职位不能为空')
            elif len(str(data['position'])) > 50:
                row_errors.append('职位长度不能超过50个字符')
                
            if not data.get('department'):
                row_errors.append('部门不能为空')
            elif len(str(data['department'])) > 50:
                row_errors.append('部门长度不能超过50个字符')
            
            # 数值字段验证
            if data.get('base_salary') is None:
                row_errors.append('基本工资不能为空')
            else:
                try:
                    base_salary = float(data['base_salary'])
                    if base_salary < 0:
                        row_errors.append('基本工资不能为负数')
                    elif base_salary > 999999.99:
                        row_errors.append('基本工资不能超过999999.99')
                    data['base_salary'] = base_salary
                except (ValueError, TypeError):
                    row_errors.append('基本工资必须是有效数字')
            
            if data.get('coefficient') is None:
                row_errors.append('系数不能为空')
            else:
                try:
                    coefficient = float(data['coefficient'])
                    if coefficient < 0:
                        row_errors.append('系数不能为负数')
                    elif coefficient > 99.99:
                        row_errors.append('系数不能超过99.99')
                    data['coefficient'] = coefficient
                except (ValueError, TypeError):
                    row_errors.append('系数必须是有效数字')
            
            # 入职时间验证
            if not data.get('hire_date'):
                row_errors.append('入职时间不能为空')
            else:
                try:
                    from datetime import datetime, date
                    if isinstance(data['hire_date'], str):
                        data['hire_date'] = datetime.strptime(data['hire_date'], '%Y-%m-%d').date()
                    elif isinstance(data['hire_date'], datetime):
                        data['hire_date'] = data['hire_date'].date()
                    elif not isinstance(data['hire_date'], date):
                        row_errors.append('入职时间格式错误，应为YYYY-MM-DD格式')
                except (ValueError, AttributeError):
                    row_errors.append('入职时间格式错误，应为YYYY-MM-DD格式')
            
            # 离职时间验证（如果提供）
            if data.get('termination_date'):
                try:
                    from datetime import datetime, date
                    if isinstance(data['termination_date'], str):
                        data['termination_date'] = datetime.strptime(data['termination_date'], '%Y-%m-%d').date()
                    elif isinstance(data['termination_date'], datetime):
                        data['termination_date'] = data['termination_date'].date()
                    elif not isinstance(data['termination_date'], date):
                        row_errors.append('离职时间格式错误，应为YYYY-MM-DD格式')
                    
                    # 验证离职时间不能早于入职时间
                    if (data.get('hire_date') and data.get('termination_date') and 
                        isinstance(data['hire_date'], date) and isinstance(data['termination_date'], date)):
                        if data['termination_date'] < data['hire_date']:
                            row_errors.append('离职时间不能早于入职时间')
                except (ValueError, AttributeError):
                    row_errors.append('离职时间格式错误，应为YYYY-MM-DD格式')
            
            if row_errors:
                error_messages.append(f'第{i+1}行数据错误：{"; ".join(row_errors)}')
        
        # 如果有验证错误，直接返回
        if error_messages:
            return jsonify({
                'success': False, 
                'message': f'数据验证失败，共发现{len(error_messages)}个错误：\n' + '\n'.join(error_messages[:10]) + 
                          (f'\n... 还有{len(error_messages)-10}个错误未显示' if len(error_messages) > 10 else '')
            })
        
        # 检查重复的工号
        employee_ids = [data['employee_id'] for data in employee_data if data.get('employee_id')]
        duplicate_ids = [emp_id for emp_id in set(employee_ids) if employee_ids.count(emp_id) > 1]
        if duplicate_ids:
            return jsonify({
                'success': False, 
                'message': f'Excel文件中存在重复的工号：{", ".join(duplicate_ids)}'
            })
        
        # 检查数据库中已存在的工号
        existing_employee_ids = []
        existing_user_ids = []
        for data in employee_data:
            # 检查员工工号是否已存在
            if Employee.query.filter_by(employee_id=data['employee_id']).first():
                existing_employee_ids.append(data['employee_id'])
            
            # 检查用户名是否已存在
            if User.query.filter_by(username=data['employee_id']).first():
                existing_user_ids.append(data['employee_id'])
        
        if existing_employee_ids:
            return jsonify({
                'success': False, 
                'message': f'以下工号在数据库中已存在：{", ".join(existing_employee_ids)}'
            })
        
        if existing_user_ids:
            return jsonify({
                'success': False, 
                'message': f'以下工号对应的用户名已存在：{", ".join(existing_user_ids)}'
            })
        
        # 处理员工数据
        for i, data in enumerate(employee_data, 1):
            try:
                # 创建用户账号
                user = User(username=data['employee_id'], role='user')
                user.set_password(data['employee_id'])  # 初始密码与工号相同
                db.session.add(user)
                db.session.flush()  # 获取用户ID
                
                # 创建员工记录
                employee = Employee(
                    global_sn=SerialNumber.get_next_number(),
                    employee_id=data['employee_id'],
                    name=data['name'],
                    position=data['position'],
                    department=data['department'],
                    base_salary=data['base_salary'],
                    coefficient=data['coefficient'],
                    hire_date=data['hire_date'],
                    termination_date=data.get('termination_date'),
                    user=user
                )
                db.session.add(employee)
                success_count += 1
                
            except Exception as e:
                error_messages.append(f"第{i+1}行员工 {data.get('employee_id', '未知')} 处理失败: {str(e)}")
        
        # 最终提交
        try:
            if success_count > 0:
                db.session.commit()
                # 记录审计日志
                log = AuditLog(
                    user_id=current_user.id,
                    action='批量导入员工',
                    details=f'成功导入 {success_count} 条员工记录'
                )
                db.session.add(log)
                db.session.commit()
            else:
                db.session.rollback()
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'保存数据时发生错误：{str(e)}'})
        
        # 构建返回消息
        message_parts = []
        if success_count > 0:
            message_parts.append(f'成功导入 {success_count} 条记录')
        
        if warning_messages:
            message_parts.append(f'警告：{"; ".join(warning_messages)}')
        
        if error_messages:
            message_parts.append(f'失败：{len(error_messages)} 条记录导入失败')
            if len(error_messages) <= 5:
                message_parts.append('\n错误详情：\n' + '\n'.join(error_messages))
            else:
                message_parts.append(f'\n错误详情（前5条）：\n' + '\n'.join(error_messages[:5]) + 
                                   f'\n... 还有{len(error_messages)-5}个错误未显示')
        
        final_message = '\n'.join(message_parts)
        
        # 如果有成功导入的记录，则认为操作成功
        return jsonify({
            'success': success_count > 0,
            'message': final_message
        })
        
    except Exception as e:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        db.session.rollback()
        return jsonify({'success': False, 'message': f'导入失败：{str(e)}'})

def cleanup_temp_files():
    """清理超过5分钟的临时文件"""
    try:
        temp_folder = current_app.config['TEMP_FOLDER']
        current_time = time.time()
        
        # 遍历临时文件夹
        for filename in os.listdir(temp_folder):
            file_path = os.path.join(temp_folder, filename)
            # 检查文件是否存在且是否为文件（不是文件夹）
            if os.path.isfile(file_path):
                # 获取文件的最后修改时间
                file_time = os.path.getmtime(file_path)
                # 如果文件超过5分钟未被修改，则删除
                if current_time - file_time > 300:  # 300秒 = 5分钟
                    try:
                        os.remove(file_path)
                        current_app.logger.info(f"Cleaned up temp file: {filename}")
                    except Exception as e:
                        current_app.logger.error(f"Error cleaning up temp file {filename}: {str(e)}")
    except Exception as e:
        current_app.logger.error(f"Error during temp files cleanup: {str(e)}")

@bp.before_request
def before_request():
    """在每个请求之前执行清理操作"""
    # 每次请求都检查是否需要清理临时文件
    cleanup_temp_files()

@bp.route('/employees/export', methods=['GET', 'POST'])
@login_required
@require_capability('employee.view')
def export_employees():
    form = ExportEmployeeForm()
    if form.validate_on_submit():
        query = Employee.query
        if form.department.data:
            query = query.filter(Employee.department == form.department.data)
        if form.position.data:
            query = query.filter(Employee.position == form.position.data)

        employees = query.all()
        wb = ExcelGenerator.export_employees(employees)

        try:
            # 写入内存：避免 Windows 上 send_file 后临时文件被占用、删不掉而持续堆积
            buf = io.BytesIO()
            wb.save(buf)
            buf.seek(0)

            return send_file(
                buf,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name=f'employees_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
            )
        except Exception as e:
            current_app.logger.error(f'导出员工数据失败: {str(e)}')
            flash(f'导出失败：{str(e)}', 'danger')
            return redirect(url_for('main.manage_employees'))

    return render_template('main/export_form.html', title='导出员工数据', form=form)

@bp.route('/process_prices/template')
@login_required
@require_capability('process.manage')
def download_process_price_template():
    """下载工序价格导入模板"""
    
    temp_path = None
    try:
        wb = ExcelGenerator.create_process_price_template()
        filename = 'process_price_template.xlsx'
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        
        # 确保文件写入完成
        time.sleep(0.1)
        
        return send_file(
            buf,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        flash(f'下载模板失败：{str(e)}', 'danger')
        return redirect(url_for('main.process_prices'))
    finally:
        # 确保在请求结束后删除临时文件
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
@bp.route('/process_prices/import', methods=['POST'])
@login_required
@require_capability('process.manage')
def import_process_prices():
    """导入工序价格数据"""
    
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': '没有上传文件'})
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'message': '没有选择文件'})
    
    if not file.filename.endswith('.xlsx'):
        return jsonify({'success': False, 'message': '请上传Excel文件(.xlsx)'})
    
    temp_path = None
    try:
        filename = secure_filename(file.filename)
        temp_path = os.path.join(current_app.config['TEMP_FOLDER'], filename)
        file.save(temp_path)
        
        # 解析Excel数据
        try:
            process_data = ExcelGenerator.parse_process_price_data(temp_path)
        except Exception as e:
            return jsonify({'success': False, 'message': f'Excel文件解析失败：{str(e)}。请检查文件格式是否正确。'})
        
        if not process_data:
            return jsonify({'success': False, 'message': 'Excel文件中没有找到有效数据。请检查文件内容。'})
        
        success_count = 0
        error_messages = []
        warning_messages = []
        
        # 数据验证
        for i, data in enumerate(process_data, 1):
            row_errors = []
            
            # 必填字段验证
            if not data.get('process_code'):
                row_errors.append('工序编号不能为空')
            elif len(str(data['process_code'])) > 50:
                row_errors.append('工序编号长度不能超过50个字符')
            
            if not data.get('process_name'):
                row_errors.append('工序名称不能为空')
            elif len(str(data['process_name'])) > 100:
                row_errors.append('工序名称长度不能超过100个字符')
            
            if not data.get('effective_date'):
                row_errors.append('生效日期不能为空')
            else:
                # 验证日期格式
                try:
                    if isinstance(data['effective_date'], str):
                        from datetime import datetime
                        data['effective_date'] = datetime.strptime(data['effective_date'], '%Y-%m-%d').date()
                    elif hasattr(data['effective_date'], 'date'):
                        data['effective_date'] = data['effective_date'].date()
                except (ValueError, AttributeError):
                    row_errors.append('生效日期格式错误，应为YYYY-MM-DD格式')
            
            # 价格验证
            if data.get('price') is None:
                if data.get('price_type') != 'subtotal':
                    row_errors.append('单价不能为空')
            else:
                try:
                    price = float(data['price'])
                    if price < 0:
                        row_errors.append('单价不能为负数')
                    data['price'] = price
                except (ValueError, TypeError):
                    row_errors.append('单价必须是有效数字')
            
            # 价格类型验证
            price_type = data.get('price_type', 'normal').lower()
            if price_type not in ['normal', 'subtotal']:
                row_errors.append('价格类型必须是normal或subtotal')
            data['price_type'] = price_type
            
            # 小计工序特殊验证
            if price_type == 'subtotal':
                if not data.get('included_processes'):
                    row_errors.append('小计工序必须指定包含的工序编号')
                elif not isinstance(data['included_processes'], list) or len(data['included_processes']) == 0:
                    row_errors.append('小计工序的包含工序列表不能为空')
            
            # 字符串长度验证
            if data.get('component') and len(str(data['component'])) > 100:
                row_errors.append('部件名称长度不能超过100个字符')
            if data.get('drawing_no') and len(str(data['drawing_no'])) > 100:
                row_errors.append('图号长度不能超过100个字符')
            if data.get('model_no') and len(str(data['model_no'])) > 100:
                row_errors.append('型号长度不能超过100个字符')
            
            if row_errors:
                error_messages.append(f'第{i+1}行数据错误：{"; ".join(row_errors)}')
        
        # 如果有验证错误，直接返回
        if error_messages:
            return jsonify({
                'success': False, 
                'message': f'数据验证失败，共发现{len(error_messages)}个错误：\n' + '\n'.join(error_messages[:10]) + 
                          (f'\n... 还有{len(error_messages)-10}个错误未显示' if len(error_messages) > 10 else '')
            })
        
        # 检查重复的工序编号
        process_codes = [data['process_code'] for data in process_data]
        duplicate_codes = [code for code in set(process_codes) if process_codes.count(code) > 1]
        if duplicate_codes:
            return jsonify({
                'success': False, 
                'message': f'Excel文件中存在重复的工序编号：{", ".join(duplicate_codes)}'
            })
        
        # 检查数据库中已存在的工序编号
        existing_codes = []
        for data in process_data:
            existing = ProcessPrice.query.filter_by(
                process_code=data['process_code'], 
                is_current=True
            ).first()
            if existing:
                existing_codes.append(data['process_code'])
        
        if existing_codes:
            warning_messages.append(f'以下工序编号在数据库中已存在，将创建新版本：{", ".join(existing_codes)}')
        
        # 第一遍：处理普通工序
        normal_processes = {}  # 用于存储导入的普通工序，以便后续建立小计关联
        
        for i, data in enumerate(process_data, 1):
            if data['price_type'] != 'subtotal':
                try:
                    # 如果工序已存在，将现有版本设为非当前
                    existing_process = ProcessPrice.query.filter_by(
                        process_code=data['process_code'], 
                        is_current=True
                    ).first()
                    
                    if existing_process:
                        existing_process.is_current = False
                        next_version = existing_process.version + 1
                    else:
                        next_version = 1
                    
                    # 创建新工序价格记录
                    process = ProcessPrice(
                        global_sn=SerialNumber.get_next_number(),
                        process_code=data['process_code'],
                        process_name=data['process_name'],
                        component=data['component'],
                        drawing_no=data['drawing_no'],
                        model_no=data['model_no'],
                        price=data['price'],
                        effective_date=data['effective_date'],
                        notes=data['notes'],
                        version=next_version,
                        is_current=True,
                        price_type='normal'
                    )
                    db.session.add(process)
                    db.session.flush()  # 获取ID
                            
                    normal_processes[data['process_code']] = process.id
                    success_count += 1
                    
                except Exception as e:
                    error_messages.append(f"第{i+1}行普通工序 {data['process_code']} 处理失败: {str(e)}")
        
        # 提交普通工序，以便后续小计能找到
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'保存普通工序时发生错误：{str(e)}'})
        
        # 第二遍：处理小计工序
        for i, data in enumerate(process_data, 1):
            if data['price_type'] == 'subtotal':
                try:
                    # 查找包含的普通工序
                    included_process_ids = []
                    missing_processes = []
                    
                    # 首先查找本次导入的工序
                    for code in data['included_processes']:
                        if code in normal_processes:
                            included_process_ids.append(normal_processes[code])
                        else:
                            # 查找数据库中已有的工序
                            existing_process = ProcessPrice.query.filter_by(
                                process_code=code, 
                                price_type='normal', 
                                is_current=True
                            ).first()
                            if existing_process:
                                included_process_ids.append(existing_process.id)
                            else:
                                missing_processes.append(code)
                    
                    if missing_processes:
                        error_messages.append(f"第{i+1}行小计工序 {data['process_code']} 包含的工序未找到：{', '.join(missing_processes)}")
                        continue
                    
                    if not included_process_ids:
                        error_messages.append(f"第{i+1}行小计工序 {data['process_code']} 没有找到有效的包含工序")
                        continue
                    
                    # 计算小计总价
                    total_price = 0
                    for pid in included_process_ids:
                        process = ProcessPrice.query.get(pid)
                        if process:
                            total_price += process.price
                    
                    # 如果工序已存在，将现有版本设为非当前
                    existing_process = ProcessPrice.query.filter_by(
                        process_code=data['process_code'], 
                        is_current=True
                    ).first()
                    
                    if existing_process:
                        existing_process.is_current = False
                        next_version = existing_process.version + 1
                    else:
                        next_version = 1
                    
                    # 创建小计工序
                    subtotal = ProcessPrice(
                        global_sn=SerialNumber.get_next_number(),
                        process_code=data['process_code'],
                        process_name=data['process_name'],
                        component=data['component'],
                        drawing_no=data['drawing_no'],
                        model_no=data['model_no'],
                        price=total_price,
                        effective_date=data['effective_date'],
                        notes=data['notes'],
                        version=next_version,
                        is_current=True,
                        price_type='subtotal'
                    )
                    db.session.add(subtotal)
                    db.session.flush()  # 获取ID
                    
                    # 创建小计关联
                    for pid in included_process_ids:
                        group = ProcessPriceGroup(
                            subtotal_id=subtotal.id,
                            process_id=pid
                        )
                        db.session.add(group)
                    
                    success_count += 1
                    
                except Exception as e:
                    error_messages.append(f"第{i+1}行小计工序 {data['process_code']} 处理失败: {str(e)}")
        
        # 最终提交
        try:
            if success_count > 0:
                db.session.commit()
                # 记录审计日志
                log = AuditLog(
                    user_id=current_user.id,
                    action='批量导入工序价格',
                    details=f'成功导入 {success_count} 条工序价格记录'
                )
                db.session.add(log)
                db.session.commit()
            else:
                db.session.rollback()
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'保存数据时发生错误：{str(e)}'})
        
        # 构建返回消息
        message_parts = []
        if success_count > 0:
            message_parts.append(f'成功导入 {success_count} 条记录')
        
        if warning_messages:
            message_parts.append(f'警告：{"; ".join(warning_messages)}')
        
        if error_messages:
            message_parts.append(f'失败：{len(error_messages)} 条记录导入失败')
            if len(error_messages) <= 5:
                message_parts.append('\n错误详情：\n' + '\n'.join(error_messages))
            else:
                message_parts.append(f'\n错误详情（前5条）：\n' + '\n'.join(error_messages[:5]) + 
                                   f'\n... 还有{len(error_messages)-5}个错误未显示')
        
        final_message = '\n'.join(message_parts)
        
        # 如果有成功导入的记录，则认为操作成功
        return jsonify({
            'success': success_count > 0,
            'message': final_message,
            'details': {
                'total_processed': len(process_data),
                'success_count': success_count,
                'error_count': len(error_messages),
                'warning_count': len(warning_messages)
            }
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'导入过程中发生未预期的错误：{str(e)}'})
    finally:
        # 清理临时文件
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass

@bp.route('/process_prices/export', methods=['GET', 'POST'])
@login_required
@require_capability('process.view')
def export_process_prices():
    form = ExportProcessForm()
    if form.validate_on_submit():
        query = ProcessPrice.query
        if form.component.data:
            query = query.filter(ProcessPrice.component == form.component.data)
        if form.model_no.data:
            query = query.filter(ProcessPrice.model_no == form.model_no.data)
        if form.start_date.data:
            query = query.filter(ProcessPrice.effective_date >= form.start_date.data)
        if form.end_date.data:
            query = query.filter(ProcessPrice.effective_date <= form.end_date.data)
        
        processes = query.all()
        wb = ExcelGenerator.export_process_prices(processes)

        try:
            # 写入内存：避免 Windows 上 send_file 后临时文件被占用、删不掉而持续堆积
            buf = io.BytesIO()
            wb.save(buf)
            buf.seek(0)

            return send_file(
                buf,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name=f'processes_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
            )
        except Exception as e:
            current_app.logger.error(f'导出工序数据失败: {str(e)}')
            flash(f'导出失败：{str(e)}', 'danger')
            return redirect(url_for('main.process_prices'))

    return render_template('main/export_form.html', title='导出工序数据', form=form)

@bp.route('/production_records/template')
@login_required
@require_capability('production_record.manage')
def download_production_record_template():
    """下载生产记录导入模板"""
    
    temp_path = None
    try:
        wb = ExcelGenerator.create_production_record_template()
        filename = 'production_record_template.xlsx'
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        
        # 确保文件写入完成
        time.sleep(0.1)
        
        return send_file(
            buf,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        flash(f'下载模板失败：{str(e)}', 'danger')
        return redirect(url_for('main.manage_production_records'))
    finally:
        # 确保在请求结束后删除临时文件
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass

@bp.route('/production_records/import', methods=['POST'])
@login_required
@require_capability('production_record.manage')
def import_production_records():
    """导入生产记录数据"""
    
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': '没有上传文件'})
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'message': '没有选择文件'})
    
    if not file.filename.endswith('.xlsx'):
        return jsonify({'success': False, 'message': '请上传Excel文件(.xlsx)'})
    
    try:
        filename = secure_filename(file.filename)
        temp_path = os.path.join(current_app.config['TEMP_FOLDER'], filename)
        file.save(temp_path)
        
        record_data = ExcelGenerator.parse_production_record_data(temp_path)
        os.remove(temp_path)  # 删除临时文件
        
        success_count = 0
        error_messages = []
        
        for data in record_data:
            try:
                # 查找员工
                employee = Employee.query.filter_by(employee_id=data['employee_id']).first()
                if not employee:
                    error_messages.append(f"员工工号 {data['employee_id']} 不存在")
                    continue
                
                # 查找工序价格，使用改进的日期处理逻辑
                target_date = data['date']
                end_of_day = datetime.combine(target_date, datetime.max.time())
                
                process_price = ProcessPrice.query.filter(
                    ProcessPrice.process_code == data['process_code'],
                    ProcessPrice.effective_date <= end_of_day + timedelta(days=1)
                ).order_by(ProcessPrice.effective_date.desc()).first()
                
                if not process_price:
                    error_messages.append(f"未找到工序 {data['process_code']} 在 {data['date']} 的价格")
                    continue
                
                # 创建生产记录
                record = ProductionRecord(
                    global_sn=SerialNumber.get_next_number(),
                    employee_id=employee.id,
                    process_id=process_price.id,
                    quantity=data['quantity'],
                    date=data['date'],
                    notes=data['notes']
                )
                db.session.add(record)
                success_count += 1
                
            except Exception as e:
                error_messages.append(f"处理记录时出错: {str(e)}")
        
        if success_count > 0:
            db.session.commit()
            # 记录审计日志
            log = AuditLog(
                user_id=current_user.id,
                action='批量导入生产记录',
                details=f'成功导入 {success_count} 条生产记录'
            )
            db.session.add(log)
            db.session.commit()
        
        message = f'成功导入 {success_count} 条记录'
        if error_messages:
            message += f'，{len(error_messages)} 条记录导入失败：\n' + '\n'.join(error_messages)
        
        return jsonify({
            'success': True,
            'message': message
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'导入失败：{str(e)}'})

@bp.route('/production_records/export', methods=['GET', 'POST'])
@login_required
@require_capability('production_record.view')
def export_production_records():
    form = ExportProductionRecordForm()
    if form.validate_on_submit():
        query = ProductionRecord.query
        if form.employee_id.data:
            query = query.join(Employee).filter(Employee.employee_id == form.employee_id.data)
        if form.process_code.data:
            query = query.join(ProcessPrice).filter(ProcessPrice.process_code == form.process_code.data)
        if form.start_date.data:
            query = query.filter(ProductionRecord.date >= form.start_date.data)
        if form.end_date.data:
            query = query.filter(ProductionRecord.date <= form.end_date.data)
        
        records = query.all()
        wb = ExcelGenerator.export_production_records(records)
        
        temp_path = None
        try:
            # 创建临时文件
            buf = io.BytesIO()
            wb.save(buf)
            buf.seek(0)
            # 发送文件
            return send_file(
                buf,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name=f'production_records_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
            )
        except Exception as e:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            flash(f'导出失败：{str(e)}', 'danger')
            return redirect(url_for('main.manage_production_records'))
        finally:
            # 确保在请求结束后删除临时文件
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
    
    return render_template('main/export_form.html', form=form, title='导出生产记录')

@bp.route('/bonus_penalties/export', methods=['GET', 'POST'])
@login_required
@require_capability('bonus.manage')
def export_bonus_penalties():
    form = ExportBonusPenaltyForm()
    if form.validate_on_submit():
        query = BonusPenalty.query
        if form.employee_id.data:
            query = query.join(Employee).filter(Employee.employee_id == form.employee_id.data)
        if form.process_code.data:
            query = query.join(ProcessPrice).filter(ProcessPrice.process_code == form.process_code.data)
        if form.type.data:
            query = query.filter(BonusPenalty.type == form.type.data)
        if form.start_date.data:
            query = query.filter(BonusPenalty.date >= form.start_date.data)
        if form.end_date.data:
            query = query.filter(BonusPenalty.date <= form.end_date.data)
        
        records = query.all()
        wb = ExcelGenerator.export_bonus_penalties(records)
        
        temp_path = None
        try:
            # 创建临时文件
            buf = io.BytesIO()
            wb.save(buf)
            buf.seek(0)
            # 发送文件
            return send_file(
                buf,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name=f'bonus_penalties_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
            )
        except Exception as e:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            flash(f'导出失败：{str(e)}', 'danger')
            return redirect(url_for('main.manage_bonus_penalties'))
        finally:
            # 确保在请求结束后删除临时文件
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
    
    return render_template('main/export_form.html', form=form, title='导出奖惩记录')

@bp.route('/search', methods=['GET', 'POST'])
@login_required
@require_capability('search.use')
@handle_pagination_args
def global_search():
    """全局搜索页面"""
    form = GlobalSearchForm()
    search_results = None
    search_types = allowed_search_types()
    
    # 处理URL参数传递的搜索（快速搜索）
    url_query = request.args.get('query')
    if url_query and request.method == 'GET':
        form.query.data = url_query
        form.search_type.data = request.args.get('search_type', 'all')
        
        # 分页（统一走 @handle_pagination_args 的白名单口径）
        page = request.validated_page
        per_page = request.validated_per_page
        
        search_results = SearchService.global_search(
            query=url_query,
            search_type=form.search_type.data,
            page=page,
            per_page=per_page,
            allowed_types=search_types
        )
    elif form.validate_on_submit():
        query = form.query.data
        search_type = form.search_type.data
        # 分页（统一走 @handle_pagination_args 的白名单口径）
        page = request.validated_page
        per_page = request.validated_per_page
        
        search_results = SearchService.global_search(
            query=query,
            search_type=search_type,
            page=page,
            per_page=per_page,
            allowed_types=search_types
        )
    
    return render_template('main/search/global_search.html', 
                         form=form, 
                         search_results=search_results)

@bp.route('/search/advanced', methods=['GET', 'POST'])
@login_required
@require_capability('search.use')
@handle_pagination_args
def advanced_search():
    """高级搜索页面"""
    form = AdvancedSearchForm()
    search_results = None
    
    if form.validate_on_submit():
        # 构建搜索参数字典
        search_params = {}
        
        # 员工搜索参数
        if form.employee_name.data:
            search_params['employee_name'] = form.employee_name.data
        if form.employee_id.data:
            search_params['employee_id'] = form.employee_id.data
        if form.department.data:
            search_params['department'] = form.department.data
        if form.position.data:
            search_params['position'] = form.position.data
        if form.is_active.data:
            search_params['is_active'] = form.is_active.data
        
        # 工序价格搜索参数
        if form.process_code.data:
            search_params['process_code'] = form.process_code.data
        if form.process_name.data:
            search_params['process_name'] = form.process_name.data
        if form.component.data:
            search_params['component'] = form.component.data
        if form.drawing_no.data:
            search_params['drawing_no'] = form.drawing_no.data
        if form.model_no.data:
            search_params['model_no'] = form.model_no.data
        
        # 生产记录搜索参数
        if form.production_date_start.data:
            search_params['production_date_start'] = form.production_date_start.data
        if form.production_date_end.data:
            search_params['production_date_end'] = form.production_date_end.data
        
        # 产品搜索参数
        if form.product_code.data:
            search_params['product_code'] = form.product_code.data
        if form.product_name.data:
            search_params['product_name'] = form.product_name.data
        if form.drawing_number.data:
            search_params['drawing_number'] = form.drawing_number.data
        if form.model.data:
            search_params['model'] = form.model.data
        
        # 库存搜索参数
        if form.inventory_type.data:
            search_params['inventory_type'] = form.inventory_type.data
        if form.supplier.data:
            search_params['supplier'] = form.supplier.data
        if form.material_name.data:
            search_params['material_name'] = form.material_name.data
        if form.storage_date_start.data:
            search_params['storage_date_start'] = form.storage_date_start.data
        if form.storage_date_end.data:
            search_params['storage_date_end'] = form.storage_date_end.data
        
        # 客户搜索参数
        if form.customer_code.data:
            search_params['customer_code'] = form.customer_code.data
        if form.customer_name.data:
            search_params['customer_name'] = form.customer_name.data
        if form.contact_person.data:
            search_params['contact_person'] = form.contact_person.data
        if form.customer_type.data:
            search_params['customer_type'] = form.customer_type.data
        
        # 销售订单搜索参数
        if form.sales_order_number.data:
            search_params['sales_order_number'] = form.sales_order_number.data
        if form.order_source.data:
            search_params['order_source'] = form.order_source.data
        if form.year_month.data:
            search_params['year_month'] = form.year_month.data
        if form.order_status.data:
            search_params['order_status'] = form.order_status.data
        
        # 生产订单搜索参数
        if form.production_order_number.data:
            search_params['production_order_number'] = form.production_order_number.data
        if form.production_status.data:
            search_params['production_status'] = form.production_status.data
        if form.planned_start_date.data:
            search_params['planned_start_date'] = form.planned_start_date.data
        if form.planned_end_date.data:
            search_params['planned_end_date'] = form.planned_end_date.data
        
        # 分页（统一走 @handle_pagination_args 的白名单口径）
        page = request.validated_page
        per_page = request.validated_per_page
        
        search_results = SearchService.advanced_search(
            search_params=search_params,
            page=page,
            per_page=per_page,
            allowed_types=allowed_search_types()
        )
    
    return render_template('main/search/advanced_search.html', 
                         form=form, 
                         search_results=search_results)

@bp.route('/api/search/suggestions')
@login_required
@require_capability('search.use')
def search_suggestions():
    """搜索建议API"""
    query = request.args.get('q', '')
    limit = request.args.get('limit', 10, type=int)
    
    if not query or len(query) < 2:
        return jsonify({'suggestions': {}})
    
    suggestions = SearchService.get_search_suggestions(
        query, limit, allowed_types=allowed_search_types())
    return jsonify({'suggestions': suggestions})
@bp.route('/search/quick', methods=['POST'])
@login_required
@require_capability('search.use')
def quick_search():
    """快速搜索API"""
    data = request.get_json()
    query = data.get('query', '')
    search_type = data.get('search_type', 'all')
    
    if not query:
        return jsonify({'error': '请输入搜索关键词'}), 400
    
    # 只返回前5个结果用于快速预览：本端点是不分页的固定窗口建议接口，
    # 白名单即固定 per_page=5/page=1（页面列表一律走 @handle_pagination_args 的 20/50/100 口径）
    search_results = SearchService.global_search(
        query=query,
        search_type=search_type,
        page=1,
        per_page=5,
        allowed_types=allowed_search_types()
    )
    
    # 简化结果格式
    simplified_results = {}
    for category, results in search_results['results'].items():
        simplified_results[category] = {
            'total': results['total'],
            'items': []
        }
        
        for item in results['items']:
            if category == 'employees':
                simplified_results[category]['items'].append({
                    'id': item.id,
                    'name': item.name,
                    'employee_id': item.employee_id,
                    'department': item.department,
                    'url': url_for('main.manage_employees') + f'?search={item.employee_id}'
                })
            elif category == 'process_prices':
                simplified_results[category]['items'].append({
                    'id': item.id,
                    'process_name': item.process_name,
                    'process_code': item.process_code,
                    'price': item.price,
                    'url': url_for('main.process_prices') + f'?search={item.process_code}'
                })
            elif category == 'products':
                simplified_results[category]['items'].append({
                    'id': item.id,
                    'product_name': item.product_name,
                    'product_code': item.product_code,
                    'model': item.model,
                    'url': url_for('main.manage_products') + f'?search={item.product_code}'
                })
            elif category == 'customers':
                simplified_results[category]['items'].append({
                    'id': item.id,
                    'customer_name': item.customer_name,
                    'customer_code': item.customer_code,
                    'contact_person': item.contact_person,
                    'url': url_for('main.customer_detail', customer_id=item.id)
                })
            # 可以继续添加其他类别的简化格式
    
    return jsonify({
        'results': simplified_results,
        'total_count': search_results['total_count'],
        'query': query
    })

@bp.route('/tasks', methods=['GET', 'POST'])
@login_required
@require_capability('task.manage')
@handle_pagination_args
def manage_tasks():
    """管理任务分配"""
    
    form = TaskAssignmentForm()
    search_form = TaskSearchForm()
    
    # 获取所有员工
    employees = Employee.query.all()
    form.employee_id.choices = [(e.id, f"{e.employee_id} - {e.name} ({e.department})") for e in employees]
    
    # 获取所有当前生效的工序
    today = datetime.now().date()
    latest_versions = db.session.query(
        ProcessPrice.process_code,
        db.func.max(ProcessPrice.effective_date).label('max_date')
    ).filter(ProcessPrice.effective_date <= today + timedelta(days=1))\
     .group_by(ProcessPrice.process_code)\
     .subquery()
    
    current_processes = ProcessPrice.query.join(
        latest_versions,
        db.and_(
            ProcessPrice.process_code == latest_versions.c.process_code,
            ProcessPrice.effective_date == latest_versions.c.max_date
        )
    ).order_by(ProcessPrice.process_code).all()
    
    form.process_id.choices = [(0, '无')] + [(p.id, f"{p.process_code} - {p.process_name} ({p.component or ''} {p.drawing_no or ''} {p.model_no or ''})".strip()) for p in current_processes]
    
    # 构建查询
    query = TaskAssignment.query.join(Employee).join(ProcessPrice)
    
    # 处理搜索条件
    if request.args.get('search'):
        search_term = f"%{request.args.get('search')}%"
        query = query.filter(db.or_(
            Employee.name.like(search_term),
            Employee.employee_id.like(search_term),
            ProcessPrice.process_code.like(search_term),
            ProcessPrice.process_name.like(search_term),
            TaskAssignment.notes.like(search_term)
        ))
    
    # 状态筛选，默认为pending（未完成）
    status_filter = request.args.get('status', 'pending')
    if status_filter and status_filter != '':
        query = query.filter(TaskAssignment.status == status_filter)
    
    if request.args.get('start_date'):
        try:
            start_date = datetime.strptime(request.args.get('start_date'), '%Y-%m-%d')
            query = query.filter(TaskAssignment.target_date >= start_date)
        except (ValueError, TypeError):
            pass
    
    if request.args.get('end_date'):
        try:
            end_date = datetime.strptime(request.args.get('end_date'), '%Y-%m-%d')
            query = query.filter(TaskAssignment.target_date <= end_date)
        except (ValueError, TypeError):
            pass
    
    # 处理排序
    sort_column = request.args.get('sort', 'assigned_date')
    sort_direction = request.args.get('direction', 'desc')
    
    # 定义排序映射
    sort_mapping = {
        'assigned_date': TaskAssignment.assigned_date,
        'target_date': TaskAssignment.target_date,
        'employee_name': Employee.name,
        'process_name': ProcessPrice.process_name,
        'status': TaskAssignment.status,
        'completion_rate': TaskAssignment.completed_quantity / TaskAssignment.quantity
    }
    
    if sort_column in sort_mapping:
        column = sort_mapping[sort_column]
        if sort_direction == 'desc':
            column = column.desc()
        query = query.order_by(column)
    else:
        query = query.order_by(TaskAssignment.assigned_date.desc())
    
    # 分页
    pagination = query.paginate(page=request.validated_page, per_page=request.validated_per_page)
    tasks = pagination.items
    
    # 处理任务分配表单提交
    if request.method == 'POST' and form.validate_on_submit():
        try:
            # 获取对应的工序价格记录和员工记录
            process_price = ProcessPrice.query.get(form.process_id.data)
            employee = Employee.query.get(form.employee_id.data)
            
            if not process_price:
                flash('未找到对应的工序', 'danger')
                return redirect(url_for('main.manage_tasks'))
            
            if not employee:
                flash('未找到对应的员工', 'danger')
                return redirect(url_for('main.manage_tasks'))
            
            # 创建任务分配记录
            task = TaskAssignment(
                global_sn=SerialNumber.get_next_number(),
                employee_id=form.employee_id.data,
                process_id=process_price.id,
                quantity=form.quantity.data,
                target_date=form.target_date.data,
                notes=form.notes.data,
                status='pending',  # 设置初始状态为待处理
                assigned_date=datetime.now().date(),  # 设置分配日期
                # 规格型号信息
                spec_extended=form.spec_extended.data,
                spec_gasket=form.spec_gasket.data,
                spec_joint=form.spec_joint.data,
                spec_drilling=form.spec_drilling.data,
                spec_other=form.spec_other.data,
                spec_other_desc=form.spec_other_desc.data,
                direction=form.direction.data
            )
            db.session.add(task)
            db.session.flush()  # 获取task.id
            
            # 记录审计日志
            log = AuditLog(
                user_id=current_user.id,
                action='分配生产任务',
                details=f'将工序 {process_price.process_name} 分配给员工 {employee.name}，数量：{task.quantity}',
                can_rollback=True,
                rollback_type='add',
                target_model='TaskAssignment',
                target_id=task.id,
                new_data={
                    'employee_id': task.employee_id,
                    'process_id': task.process_id,
                    'quantity': task.quantity,
                    'target_date': task.target_date.isoformat() if task.target_date else None,
                    'notes': task.notes,
                    'status': task.status
                }
            )
            db.session.add(log)
            db.session.commit()
            
            flash('任务分配成功', 'success')
            return redirect(url_for('main.manage_tasks'))
        except Exception as e:
            db.session.rollback()
            flash(f'任务分配失败：{str(e)}', 'danger')
    
    # 从请求参数填充搜索表单
    search_form.search.data = request.args.get('search', '')
    search_form.status.data = request.args.get('status', 'pending')
    if request.args.get('start_date'):
        try:
            search_form.start_date.data = datetime.strptime(request.args.get('start_date'), '%Y-%m-%d')
        except (ValueError, TypeError):
            pass
    if request.args.get('end_date'):
        try:
            search_form.end_date.data = datetime.strptime(request.args.get('end_date'), '%Y-%m-%d')
        except (ValueError, TypeError):
            pass
    
    return render_template('main/tasks.html',
                         form=form,
                         search_form=search_form,
                         tasks=tasks,
                         pagination=pagination,
                         current_sort=sort_column,
                         current_direction=sort_direction)

@bp.route('/tasks/<int:id>/update_status', methods=['POST'])
@login_required
@require_capability('task.manage', 'my_tasks.use')
def update_task_status(id):
    """更新任务状态"""
    try:
        task = TaskAssignment.query.get_or_404(id)

        # 员工自助报工只能改自己名下的任务：这个端点会扣减原材料、生成生产记录
        # 并按任务上的 employee_id 计件，改他人任务等于替别人报工
        if not can('task.manage'):
            employee = Employee.query.filter_by(user_id=current_user.id).first()
            if not employee or task.employee_id != employee.id:
                return jsonify({'success': False, 'message': '只能更新分配给本人的任务'}), 403

        # 兼容JSON和表单数据
        if request.is_json:
            data = request.get_json()
            completed_quantity = int(data.get('completed_quantity', 0))
            materials_data = data.get('materials', [])
            equipment_id = data.get('equipment_id')
            workpiece_codes = data.get('workpiece_codes') or []
            if isinstance(workpiece_codes, str):
                workpiece_codes = [c.strip() for c in workpiece_codes.replace(',', ' ').split() if c.strip()]
        else:
            # 处理表单数据
            completed_quantity = int(request.form.get('completed_quantity', 0))
            materials_json = request.form.get('materials', '[]')
            equipment_id = request.form.get('equipment_id', type=int)
            workpiece_codes = request.form.getlist('workpiece_codes')
            if not workpiece_codes:
                raw_codes = request.form.get('workpiece_codes') or ''
                workpiece_codes = [c.strip() for c in raw_codes.replace(',', ' ').split() if c.strip()]
            try:
                import json
                materials_data = json.loads(materials_json)
            except (json.JSONDecodeError, TypeError):
                materials_data = []

        from app.services import mes_service
        from app.models import Equipment, TaskWorkpiece, Workpiece

        if not workpiece_codes:
            workpiece_codes = [
                tw.workpiece.code for tw in task.workpiece_links.all() if tw.workpiece
            ]
        if not equipment_id and task.equipment_id:
            equipment_id = task.equipment_id

        if equipment_id:
            eq = Equipment.query.get(int(equipment_id))
            ok, msg = mes_service.equipment_available(eq)
            if not ok:
                return jsonify({'success': False, 'message': msg}), 400
            task.equipment_id = eq.id

        for code in workpiece_codes:
            wp = Workpiece.query.filter_by(code=str(code).strip()).first()
            if not wp:
                continue
            allowed, msg = mes_service.qc_gate_allows(wp)
            if not allowed:
                return jsonify({'success': False, 'message': f'{wp.code}: {msg}'}), 400
            if not TaskWorkpiece.query.filter_by(task_id=task.id, workpiece_id=wp.id).first():
                db.session.add(TaskWorkpiece(task_id=task.id, workpiece_id=wp.id))
            wp.current_process_id = task.process_id
            wp.current_equipment_id = task.equipment_id
 
        # 验证完成数量
        if completed_quantity < 0:
            return jsonify({'success': False, 'message': '完成数量不能为负数'}), 400
        if completed_quantity > task.quantity:
            return jsonify({'success': False, 'message': '完成数量不能超过任务数量'}), 400
        
        # 验证原材料数据
        for material in materials_data:
            if not isinstance(material, dict) or 'raw_material_id' not in material or 'quantity' not in material:
                return jsonify({'success': False, 'message': '原材料数据格式错误'}), 400
                
            try:
                material_id = int(material['raw_material_id'])
                quantity = float(material['quantity'])
            except (ValueError, TypeError):
                return jsonify({'success': False, 'message': '原材料数据格式错误'}), 400
                
            raw_material = RawMaterial.query.get(material_id)
            if not raw_material:
                return jsonify({'success': False, 'message': f'原材料不存在'}), 400
            if raw_material.quantity < quantity:
                return jsonify({'success': False, 'message': f'原材料 {raw_material.material_name} 库存不足'}), 400
        
        # 更新任务状态
        task.completed_quantity = completed_quantity
        if completed_quantity >= task.quantity:
            # 重复报工按幂等拒绝：ProductionRecord 以 task.global_sn 作为与任务的关联键
            # （一个任务只应有一条生产记录，计件薪资也按它计算）。历史上第二次达量报工会撞
            # global_sn 唯一约束、让整单回滚并抛 500；这里在扣料/计件/建质检任务之前就挡住，
            # 既不重复计件也不重复扣料，同时给出可读提示并留日志，不静默丢数据。
            existing_record = ProductionRecord.query.filter_by(global_sn=task.global_sn).first()
            if existing_record is not None:
                db.session.rollback()
                current_app.logger.warning(
                    f'重复报工被拒：任务 {task.id} 已有生产记录 {existing_record.id}'
                    f'（global_sn={existing_record.global_sn}）'
                )
                return jsonify({
                    'success': False,
                    'message': f'该任务已报工完成（生产记录 {existing_record.global_sn}，'
                               f'{existing_record.date}），请勿重复提交',
                }), 400
            task.status = 'completed'
            task.completed_at = datetime.now()
            
            # 创建生产记录
            production_record = ProductionRecord(
                employee_id=task.employee_id,
                process_id=task.process_id,
                quantity=task.quantity,
                global_sn=task.global_sn,
                date=datetime.now().date()
            )
            db.session.add(production_record)
            db.session.flush()
            
            # 检查工序是否需要检验，如果需要则自动创建质检任务
            process = ProcessPrice.query.get(task.process_id)
            if process and process.needs_inspection:
                try:
                    # 查找默认的质检员
                    default_inspector = User.query.filter(
                        db.or_(
                            User.role == 'inspector',
                            User.role == 'admin'
                        )
                    ).first()
                    
                    if default_inspector:
                        # 创建质检任务
                        from app.models import InspectionTask, SerialNumber, InspectionTemplate
                        tmpl = InspectionTemplate.query.filter_by(type='production_record', is_active=True).first()
                        inspection_task = InspectionTask(
                            global_sn=SerialNumber.get_next_number(),
                            template_id=tmpl.id if tmpl else None,
                            target_type='production_record',
                            target_id=production_record.id,
                            inspector_id=default_inspector.id,
                            priority=1,  # 中等优先级
                            deadline=datetime.now() + timedelta(days=3),  # 3天内完成
                            notes=f'工序 {process.process_name} 完成后自动创建的质检任务',
                            created_by=current_user.id,
                            status='pending'
                        )
                        db.session.add(inspection_task)
                        
                        # 记录质检任务创建的审计日志
                        inspection_log = AuditLog(
            user_id=current_user.id,
                            action='自动创建质检任务',
                            details=f'工序 {process.process_name} 完成后自动创建质检任务：{inspection_task.global_sn}',
            can_rollback=True,
                            rollback_type='add',
                            target_model='InspectionTask',
                            target_id=inspection_task.id,
            new_data={
                                'target_type': 'production_record',
                                'target_id': production_record.id,
                                'inspector_id': default_inspector.id,
                                'priority': 1,
                                'auto_created': True
                            }
                        )
                        db.session.add(inspection_log)
                        
                        current_app.logger.info(f'自动创建质检任务：{inspection_task.global_sn}，对应生产记录：{production_record.global_sn}')
                        for tw in task.workpiece_links.all():
                            if tw.workpiece:
                                wp_task = mes_service.create_inspection_task(
                                    'workpiece', tw.workpiece.id,
                                    notes=f'工序 {process.process_name} 工件 {tw.workpiece.code}',
                                )
                                tw.status = 'done'
                                mes_service.log_event(
                                    tw.workpiece, 'reported',
                                    task_id=task.id, equipment_id=task.equipment_id,
                                    payload={'inspection_task_id': wp_task.id},
                                )
                    else:
                        current_app.logger.warning(f'未找到可用的质检员，无法为生产记录 {production_record.global_sn} 创建质检任务')
                        
                except Exception as e:
                    current_app.logger.error(f'自动创建质检任务失败: {str(e)}')
                    # 不影响主流程，继续执行
            
            # 添加原材料使用记录
            for material in materials_data:
                material_usage = ProductionRecordMaterial(
                    production_record_id=production_record.id,
                    raw_material_id=int(material['raw_material_id']),
                    quantity=float(material['quantity'])
                )
                db.session.add(material_usage)
                
                # 更新原材料库存
                raw_material = RawMaterial.query.get(int(material['raw_material_id']))
                old_quantity = raw_material.quantity
                raw_material.quantity -= float(material['quantity'])
                
                # 如果原材料数量耗尽（小于等于0），将状态修改为已使用
                if raw_material.quantity <= 0:
                    raw_material.status = 'used'
                    # 记录状态变更的审计日志
                    status_log = AuditLog(
                        user_id=current_user.id,
                        action='自动更新原材料状态',
                        details=f'原材料 {raw_material.material_name} 数量耗尽，状态自动更新为已使用',
                        can_rollback=True,
                        rollback_type='edit',
                        target_model='RawMaterial',
                        target_id=raw_material.id,
                        old_data={'status': 'in_stock', 'quantity': old_quantity},
                        new_data={'status': 'used', 'quantity': raw_material.quantity}
                    )
                    db.session.add(status_log)

            # 决策 2：报工扣料按「任务所属生产订单」归集已消耗数量，与上面的实扣同口径，
            # 避免计划账（MaterialAllocation.required/allocated）与实际账（RawMaterial.quantity）脱节。
            # 覆盖 production_batch_id 与 batch_item_id 两种挂接；没有对应分配行时只记 missing 并留痕，
            # 不臆造计划行；非法明细只记 invalid，不阻断本次报工。
            try:
                with db.session.begin_nested():
                    consumption = mes_service.record_task_material_consumption(task, materials_data)
                if consumption['written']:
                    current_app.logger.info(
                        f'报工扣料已回写生产订单 {consumption["production_order_id"]}：'
                        f'{len(consumption["written"])} 条分配行'
                    )
                if consumption['missing']:
                    current_app.logger.warning(
                        f'报工扣料未回写（该订单无对应分配行）：{consumption["missing"]}'
                    )
                if consumption['invalid']:
                    current_app.logger.warning(f'报工扣料明细被跳过：{consumption["invalid"]}')
            except Exception as e:
                current_app.logger.error(f'报工扣料回写 MaterialAllocation 失败: {str(e)}')
        else:
            # 如果任务还未完成，但已经开始，更新状态为进行中
            task.status = 'in_progress'
        
        # 记录审计日志（含替用明细）
        substitutions = []
        try:
            bom_ids = set()
            order_ref = None
            if task.production_batch_id:
                _b = ProductionBatch.query.get(task.production_batch_id)
                order_ref = _b.production_order if _b else None
            elif task.batch_item_id:
                _it = ProductionBatchItem.query.get(task.batch_item_id)
                order_ref = _it.batch.production_order if _it and _it.batch else None
            if order_ref and order_ref.product_id:
                for _bom in ProductBOM.query.filter_by(product_id=order_ref.product_id, material_type='raw').all():
                    bom_ids.add(_bom.material_id)
            for m in materials_data:
                try:
                    mid = int(m.get('raw_material_id'))
                    qty = float(m.get('quantity') or 0)
                    if mid not in bom_ids:
                        substitutions.append({'raw_material_id': mid, 'quantity': qty})
                except Exception:
                    continue
        except Exception as se:
            current_app.logger.warning(f'替用分析失败: {str(se)}')

        audit_log = AuditLog(
            user_id=current_user.id,
            action='更新任务完成与用料',
            details=f'任务 {task.id} 完成数量 {completed_quantity}，记录用料 {len(materials_data)} 条',
            can_rollback=True,
            rollback_type='edit',
            target_model='TaskAssignment',
            target_id=task.id,
            new_data={
                'completed_quantity': completed_quantity,
                'materials': materials_data,
                'substitutions': substitutions
            }
        )
        db.session.add(audit_log)
        
        # 触发“原材料替用”通知（如存在替用）
        try:
            if substitutions:
                from app.services.notification_service import notify_raw_substitution
                order_number = None
                if task.production_batch_id:
                    _b = ProductionBatch.query.get(task.production_batch_id)
                    if _b and _b.production_order:
                        order_number = _b.production_order.order_number
                elif task.batch_item_id:
                    _it = ProductionBatchItem.query.get(task.batch_item_id)
                    if _it and _it.batch and _it.batch.production_order:
                        order_number = _it.batch.production_order.order_number

                # 尝试补全物料名称，便于通知阅读
                enriched = []
                for item in substitutions:
                    try:
                        rm = RawMaterial.query.get(item.get('raw_material_id'))
                        enriched.append({
                            'raw_material_id': item.get('raw_material_id'),
                            'raw_material_name': rm.material_name if rm else str(item.get('raw_material_id')),
                            'quantity': item.get('quantity')
                        })
                    except Exception:
                        enriched.append(item)

                notify_raw_substitution(
                    task_id=task.id,
                    order_number=order_number or '未知订单',
                    substitutions=enriched,
                    operator_name=current_user.username if hasattr(current_user, 'username') else None
                )
        except Exception as _ne:
            current_app.logger.error(f'触发原材料替用通知失败: {str(_ne)}')
        
        # 如果任务关联了生产批次，同步更新批次状态
        if task.production_batch_id:
            try:
                # 获取同一批次的所有任务
                batch_tasks = TaskAssignment.query.filter_by(production_batch_id=task.production_batch_id).all()
                
                # 计算批次任务的完成情况
                total_tasks = len(batch_tasks)
                completed_tasks = len([t for t in batch_tasks if t.status == 'completed'])
                in_progress_tasks = len([t for t in batch_tasks if t.status in ['in_progress', 'completed']])
                
                # 获取生产批次
                batch = ProductionBatch.query.get(task.production_batch_id)
                if batch:
                    old_status = batch.status
                    
                    # 根据任务完成情况更新批次状态
                    if completed_tasks == total_tasks:
                        # 所有任务都完成了
                        batch.status = 'completed'
                        if not batch.end_date:
                            batch.end_date = datetime.now().date()
                    elif in_progress_tasks > 0:
                        # 有任务在进行中
                        batch.status = 'in_progress'
                        if not batch.start_date:
                            batch.start_date = datetime.now().date()
                    else:
                        # 所有任务都是待开始状态
                        batch.status = 'pending'
                    
                    # 如果状态发生变化，记录审计日志
                    if old_status != batch.status:
                        batch_log = AuditLog(
                            user_id=current_user.id,
                            action='自动更新生产批次状态',
                            details=f'由于任务状态变化，生产批次 {batch.batch_number} 状态从 {old_status} 更新为 {batch.status}',
                            target_model='ProductionBatch',
                            target_id=batch.id,
                            old_data={'status': old_status},
                            new_data={'status': batch.status}
                        )
                        db.session.add(batch_log)
                        
                        current_app.logger.info(f'生产批次 {batch.batch_number} 状态自动更新：{old_status} -> {batch.status}')
                
                # 更新生产状态层次结构
                update_production_status_hierarchy()
                
            except Exception as e:
                current_app.logger.error(f'同步更新生产批次状态失败: {str(e)}')
                # 不影响主流程，继续执行
        
        # 同步生产中心：若任务关联实例/批次则更新实例或批次下各实例的可视状态
        # 注意：ProductionBatchItem 由模块顶部统一 import；这里绝不能再用函数内 import，
        # 否则 Python 会把该名字视为整个函数的局部变量，函数前部的替用分析（L3557 附近）
        # 会抛 UnboundLocalError 并被 except 吞掉，导致实例任务的替用通知发不出。
        try:
            if task.batch_item_id:
                bi = ProductionBatchItem.query.get(task.batch_item_id)
                if bi:
                    if task.status == 'completed' and bi.status != 'completed':
                        bi.status = 'completed'
                    elif task.status in ['in_progress', 'pending'] and bi.status == 'pending':
                        bi.status = 'in_progress'
            elif task.production_batch_id:
                # 批次级任务：当有任务进行中或完成，推进该批次下所有 pending 实例为 in_progress（轻量同步）
                if task.status in ['in_progress', 'completed']:
                    ProductionBatchItem.query.filter_by(batch_id=task.production_batch_id, status='pending').update({'status': 'in_progress'})
        except Exception as sync_err:
            current_app.logger.warning(f'同步生产中心状态失败: {str(sync_err)}')

        # 决策 1：报工路径末道工序完成后按工件域 MES 口径把产出计入正品库（stock_kind='fg'）。
        # 两套入口并存：只补 /my_tasks 报工这条链，工件域（/production_center + 质检）路径不动。
        # 门禁、末道判定、幂等都由 mes_service 统一负责（本次报工自身随之创建的质检任务属于
        # 下游流程，其不合格由既有未通过库口径处置；入库前仍须过 qc_gate_allows_output）。
        if completed_quantity >= task.quantity:
            try:
                batch_for_output = (ProductionBatch.query.get(task.production_batch_id)
                                    if task.production_batch_id else None)
                item_for_output = (ProductionBatchItem.query.get(task.batch_item_id)
                                   if task.batch_item_id else None)
                order_for_output = (batch_for_output.production_order if batch_for_output else None) or (
                    item_for_output.batch.production_order
                    if item_for_output and item_for_output.batch else None)

                if order_for_output is None:
                    current_app.logger.debug(
                        f'任务 {task.id} 未挂生产批次/批次实例，报工产出不入正品库'
                    )
                elif not mes_service.is_last_process(order_for_output.product_id, task.process_id):
                    current_app.logger.info(
                        f'任务 {task.id} 工序 {task.process_id} 不是末道工序，产出不入正品库'
                    )
                else:
                    # 入库数量与同口径生成的 ProductionRecord.quantity 一致（本次报工数量）
                    with db.session.begin_nested():
                        finished_product, reason = mes_service.inbound_production_output(
                            task=task,
                            production_order=order_for_output,
                            process_id=task.process_id,
                            quantity=task.quantity,
                        )
                    if finished_product is None:
                        current_app.logger.warning(
                            f'任务 {task.id} 末道产出未入正品库（{order_for_output.order_number}）：{reason}'
                        )
                    elif reason:
                        # 已有同编号正品库行（服务幂等），本次没有新建，不写入库审计
                        current_app.logger.info(
                            f'任务 {task.id} 末道产出未重复入库：{finished_product.product_number}（{reason}）'
                        )
                    else:
                        current_app.logger.info(
                            f'任务 {task.id} 末道产出已入正品库：'
                            f'{finished_product.product_number} × {finished_product.quantity}'
                        )
                        db.session.add(AuditLog(
                            user_id=current_user.id,
                            action='报工末道入库',
                            details=f'任务 {task.id} 末道工序报工，产出 {finished_product.product_number} '
                                    f'入正品库，数量 {finished_product.quantity}',
                            can_rollback=True,
                            rollback_type='delete',
                            target_model='FinishedProduct',
                            target_id=finished_product.id,
                            new_data={
                                'product_number': finished_product.product_number,
                                'quantity': finished_product.quantity,
                                'stock_kind': 'fg',
                                'production_order_id': order_for_output.id,
                                'task_id': task.id,
                                'process_id': task.process_id,
                            }
                        ))
            except Exception as inbound_err:
                current_app.logger.error(f'报工末道入库失败: {str(inbound_err)}')

        db.session.commit()
        return jsonify({'success': True, 'message': '更新成功'})
    except Exception as e:
        _reraise_http(e)
        db.session.rollback()
        current_app.logger.error(f'更新任务状态失败: {str(e)}')
        return jsonify({'success': False, 'message': f'更新失败：{str(e)}'}), 500

@bp.route('/tasks/<int:id>', methods=['DELETE'])
@login_required
@require_capability('task.manage')
def delete_task(id):
    """删除任务"""
    
    try:
        task = TaskAssignment.query.get_or_404(id)
        
        # 保存旧数据用于回滚
        old_data = {
            'employee_id': task.employee_id,
            'process_id': task.process_id,
            'quantity': task.quantity,
            'target_date': task.target_date.isoformat() if task.target_date else None,
            'notes': task.notes,
            'status': task.status,
            'completed_quantity': task.completed_quantity
        }
        
        # 记录审计日志
        log = AuditLog(
            user_id=current_user.id,
            action='删除任务',
            details=f'删除任务：员工 {task.employee.name}，工序 {task.process.process_name}',
            can_rollback=True,
            rollback_type='delete',
            target_model='TaskAssignment',
            target_id=task.id,
            old_data=old_data
        )
        db.session.add(log)
        
        db.session.delete(task)
        db.session.commit()
        
        return jsonify({'success': True, 'message': '任务删除成功'})
    except Exception as e:
        _reraise_http(e)
        db.session.rollback()
        return jsonify({'success': False, 'message': f'删除失败：{str(e)}'}), 500

@bp.route('/my_tasks')
@login_required
def my_tasks():
    """查看我的任务"""
    # 获取当前用户的员工记录
    employee = Employee.query.filter_by(user_id=current_user.id).first()
    if not employee:
        flash('未找到您的员工信息', 'danger')
        return redirect(url_for('main.index'))
    
    # 获取该员工的所有任务
    tasks = TaskAssignment.query.filter_by(employee_id=employee.id)\
        .order_by(TaskAssignment.assigned_date.desc()).all()
    
    return render_template('main/my_tasks.html', tasks=tasks)

@bp.route('/bonus_penalties/template')
@login_required
@require_capability('bonus.manage')
def download_bonus_penalty_template():
    """下载奖金/罚款导入模板"""
    
    temp_path = None
    try:
        wb = ExcelGenerator.create_bonus_penalty_template()
        filename = 'bonus_penalty_template.xlsx'
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        
        # 确保文件写入完成
        time.sleep(0.1)
        
        return send_file(
            buf,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        flash(f'下载模板失败：{str(e)}', 'danger')
        return redirect(url_for('main.manage_bonus_penalties'))
    finally:
        # 确保在请求结束后删除临时文件
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass

@bp.route('/bonus_penalties/import', methods=['POST'])
@login_required
@require_capability('bonus.manage')
def import_bonus_penalties():
    """导入奖金/罚款数据"""
    
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': '没有上传文件'})
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'message': '没有选择文件'})
    
    if not file.filename.endswith('.xlsx'):
        return jsonify({'success': False, 'message': '请上传Excel文件(.xlsx)'})
    
    try:
        filename = secure_filename(file.filename)
        temp_path = os.path.join(current_app.config['TEMP_FOLDER'], filename)
        file.save(temp_path)
        
        record_data = ExcelGenerator.parse_bonus_penalty_data(temp_path)
        os.remove(temp_path)  # 删除临时文件
        
        success_count = 0
        error_messages = []
        
        for index, data in enumerate(record_data):
            try:
                # 查找员工
                employee = Employee.query.filter_by(employee_id=data['employee_id']).first()
                if not employee:
                    error_messages.append(f"员工工号 {data['employee_id']} 不存在")
                    continue
                
                # 日期兜底：文本日期单元格（str）会被 SQLite 方言拒绝，统一解析
                bonus_date, date_error = _coerce_excel_date(data.get('date'), '日期')
                if date_error:
                    error_messages.append(f'第 {index + 2} 行：{date_error}')
                    continue
                
                # 查找工序（如果有）
                process_id = None
                if data['process_code']:
                    process = ProcessPrice.query.filter_by(process_code=data['process_code']).first()
                    if process:
                        process_id = process.id
                
                # 创建奖惩记录
                record = BonusPenalty(
                    global_sn=SerialNumber.get_next_number(),
                    employee_id=employee.id,
                    type=data['type'],
                    amount=data['amount'],
                    date=bonus_date,
                    process_id=process_id,
                    reason=data['reason']
                )
                db.session.add(record)
                success_count += 1
                
            except Exception as e:
                error_messages.append(f"处理记录时出错: {str(e)}")
        
        if success_count > 0:
            db.session.commit()
        # 记录审计日志
        log = AuditLog(
            user_id=current_user.id,
                action='批量导入奖惩记录',
                details=f'成功导入 {success_count} 条奖惩记录'
        )
        db.session.add(log)
        db.session.commit()
        
        message = f'成功导入 {success_count} 条记录'
        if error_messages:
            message += f'，{len(error_messages)} 条记录导入失败：\n' + '\n'.join(error_messages)
        
        return jsonify({
            'success': True,
            'message': message
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'导入失败：{str(e)}'})

@bp.route('/tasks/template')
@login_required
@require_capability('task.manage')
def download_task_template():
    """下载任务导入模板"""
    
    temp_path = None
    try:
        wb = ExcelGenerator.create_task_template()
        filename = 'task_template.xlsx'
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        
        # 确保文件写入完成
        time.sleep(0.1)
        
        return send_file(
            buf,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        flash(f'下载模板失败：{str(e)}', 'danger')
        return redirect(url_for('main.manage_tasks'))
    finally:
        # 确保在请求结束后删除临时文件
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass

@bp.route('/tasks/import', methods=['POST'])
@login_required
@require_capability('task.manage')
def import_tasks():
    """导入任务数据"""
    
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': '没有上传文件'})
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'message': '没有选择文件'})
    
    if not file.filename.endswith('.xlsx'):
        return jsonify({'success': False, 'message': '请上传Excel文件(.xlsx)'})
    
    try:
        filename = secure_filename(file.filename)
        temp_path = os.path.join(current_app.config['TEMP_FOLDER'], filename)
        file.save(temp_path)
        
        task_data = ExcelGenerator.parse_task_data(temp_path)
        os.remove(temp_path)  # 删除临时文件
        
        success_count = 0
        error_messages = []
        
        for index, data in enumerate(task_data):
            try:
                # 查找员工
                employee = Employee.query.filter_by(employee_id=data['employee_id']).first()
                if not employee:
                    error_messages.append(f"员工工号 {data['employee_id']} 不存在")
                    continue
                
                # 查找工序
                process = ProcessPrice.query.filter_by(process_code=data['process_code']).first()
                if not process:
                    error_messages.append(f"工序编号 {data['process_code']} 不存在")
                    continue
                
                # 目标日期兜底：文本日期单元格（str）会被 SQLite 方言拒绝，统一解析
                target_date, date_error = _coerce_excel_date(data.get('target_date'), '目标完成日期')
                if date_error:
                    error_messages.append(f'第 {index + 2} 行：{date_error}')
                    continue
                
                # 创建任务记录
                task = TaskAssignment(
                    global_sn=SerialNumber.get_next_number(),
                    employee_id=employee.id,
                    process_id=process.id,
                    quantity=data['quantity'],
                    target_date=target_date,
                    notes=data['notes']
                )
                db.session.add(task)
                success_count += 1
                
            except Exception as e:
                error_messages.append(f"处理记录时出错: {str(e)}")
        
        if success_count > 0:
            db.session.commit()
            # 记录审计日志
            log = AuditLog(
                user_id=current_user.id,
                action='批量导入任务',
                details=f'成功导入 {success_count} 条任务记录'
            )
            db.session.add(log)
            db.session.commit()
        
        message = f'成功导入 {success_count} 条记录'
        if error_messages:
            message += f'，{len(error_messages)} 条记录导入失败：\n' + '\n'.join(error_messages)
        
        return jsonify({
            'success': True,
            'message': message
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'导入失败：{str(e)}'})
@bp.route('/export_tasks', methods=['GET', 'POST'])
@login_required
@require_capability('task.manage')
def export_tasks():

    # 新增：支持 GET 导出以兼容前端直接链接
    if request.method == 'GET':
        try:
            # 构建查询（与 manage_tasks 保持一致的筛选维度）
            query = TaskAssignment.query.join(Employee).join(ProcessPrice)

            # 处理搜索条件
            if request.args.get('search'):
                search_term = f"%{request.args.get('search')}%"
                query = query.filter(db.or_(
                    Employee.name.like(search_term),
                    Employee.employee_id.like(search_term),
                    ProcessPrice.process_code.like(search_term),
                    ProcessPrice.process_name.like(search_term),
                    TaskAssignment.notes.like(search_term)
                ))

            # 状态筛选（与页面默认一致）
            status_filter = request.args.get('status', '')
            if status_filter:
                query = query.filter(TaskAssignment.status == status_filter)

            # 时间范围（可选）
            if request.args.get('start_date'):
                try:
                    start_date = datetime.strptime(request.args.get('start_date'), '%Y-%m-%d')
                    query = query.filter(TaskAssignment.target_date >= start_date)
                except (ValueError, TypeError):
                    pass
            if request.args.get('end_date'):
                try:
                    end_date = datetime.strptime(request.args.get('end_date'), '%Y-%m-%d')
                    query = query.filter(TaskAssignment.target_date <= end_date)
                except (ValueError, TypeError):
                    pass

            tasks = query.all()

            # 生成并返回 Excel
            excel_file = ExcelGenerator.export_tasks(tasks)

            # 写入内存：避免 Windows 上 send_file 后临时文件被占用、删不掉而持续堆积
            buf = io.BytesIO()
            excel_file.save(buf)
            buf.seek(0)

            return send_file(
                buf,
                as_attachment=True,
                download_name='生产任务数据.xlsx',
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
        except Exception as e:
            current_app.logger.error(f'导出任务数据失败(GET): {str(e)}')
            flash('导出失败，请重试', 'danger')
            return redirect(url_for('main.manage_tasks'))

    form = ExportTaskForm()
    if form.validate_on_submit():
        try:
            # 构建查询（与 GET 分支同口径：员工工号 / 工序编号 / 状态 / 目标日期区间）
            query = TaskAssignment.query.join(Employee).join(ProcessPrice)
            
            # 处理搜索条件
            if form.employee_id.data:
                # 表单里填的是员工工号（人事编号），任务表存的是 employee.id
                employee = Employee.query.filter_by(employee_id=form.employee_id.data).first()
                if employee is None:
                    flash(f'员工工号 {form.employee_id.data} 不存在', 'warning')
                    return redirect(url_for('main.manage_tasks'))
                query = query.filter(TaskAssignment.employee_id == employee.id)
            
            if form.process_code.data:
                query = query.filter(ProcessPrice.process_code == form.process_code.data)
            
            if form.status.data:
                query = query.filter(TaskAssignment.status == form.status.data)
            
            if form.start_date.data:
                query = query.filter(TaskAssignment.target_date >= form.start_date.data)
            
            if form.end_date.data:
                query = query.filter(TaskAssignment.target_date <= form.end_date.data)
            
            # 获取数据
            tasks = query.all()
            
            # 生成Excel文件
            excel_file = ExcelGenerator.export_tasks(tasks)
            
            # 写入内存：避免 Windows 上 send_file 后临时文件被占用、删不掉而持续堆积
            buf = io.BytesIO()
            excel_file.save(buf)
            buf.seek(0)

            return send_file(
                buf,
                as_attachment=True,
                download_name='生产任务数据.xlsx',
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
        except Exception as e:
            current_app.logger.error(f'导出任务数据失败: {str(e)}')
            flash('导出失败，请重试', 'danger')
            return redirect(url_for('main.manage_tasks'))
    
    flash('表单验证失败', 'danger')
    return redirect(url_for('main.manage_tasks'))

def _resolve_audit_model(model_name):
    """按类名从 app.models 取模型。审计日志里存的是字符串，用 globals() 取不到未在本模块 import 的模型。"""
    import app.models as models_module

    model_class = getattr(models_module, model_name or '', None)
    if isinstance(model_class, type) and issubclass(model_class, db.Model):
        return model_class
    return None


@bp.route('/audit_logs/rollback/<int:log_id>', methods=['POST'])
@login_required
@require_capability('audit.rollback')
def rollback_audit_log(log_id):
    
    try:
        log = AuditLog.query.get_or_404(log_id)
        
        if not log.can_rollback:
            return jsonify({'success': False, 'message': '此记录不支持回滚'}), 400

        model_class = _resolve_audit_model(log.target_model)
        if model_class is None:
            return jsonify({'success': False, 'message': f'未知的目标模型：{log.target_model}'}), 400

        # 根据不同的回滚类型执行不同的操作
        if log.rollback_type == 'add':
            # 删除新增的记录
            target = model_class.query.get(log.target_id)
            if target:
                db.session.delete(target)
                
                # 记录回滚操作
                rollback_log = AuditLog(
                    user_id=current_user.id,
                    action=f'回滚{log.action}',
                    details=f'回滚操作：{log.details}',
                    can_rollback=False,
                    timestamp=datetime.now()  # 使用本地时间
                )
                db.session.add(rollback_log)
                db.session.commit()
                return jsonify({'success': True, 'message': '回滚成功'})
            else:
                return jsonify({'success': False, 'message': '目标记录不存在'}), 404
                
        elif log.rollback_type == 'edit':
            # 恢复编辑前的数据
            target = model_class.query.get(log.target_id)
            if target:
                for key, value in log.old_data.items():
                    if hasattr(target, key):
                        if key.endswith('_date') and value:
                            value = datetime.fromisoformat(value).date()
                        setattr(target, key, value)
                
                # 记录回滚操作
                rollback_log = AuditLog(
                    user_id=current_user.id,
                    action=f'回滚{log.action}',
                    details=f'回滚操作：{log.details}',
                    can_rollback=False,
                    timestamp=datetime.now()  # 使用本地时间
                )
                db.session.add(rollback_log)
                db.session.commit()
                return jsonify({'success': True, 'message': '回滚成功'})
            else:
                return jsonify({'success': False, 'message': '目标记录不存在'}), 404
                
        elif log.rollback_type == 'delete':
            # 恢复被删除的记录
            new_record = model_class()
            for key, value in log.old_data.items():
                if hasattr(new_record, key):
                    if key.endswith('_date') and value:
                        value = datetime.fromisoformat(value).date()
                    setattr(new_record, key, value)
            
            db.session.add(new_record)
            
            # 记录回滚操作
            rollback_log = AuditLog(
                user_id=current_user.id,
                action=f'回滚{log.action}',
                details=f'回滚操作：{log.details}',
                can_rollback=False,
                timestamp=datetime.now()  # 使用本地时间
            )
            db.session.add(rollback_log)
            db.session.commit()
            return jsonify({'success': True, 'message': '回滚成功'})
        
        else:
            return jsonify({'success': False, 'message': '不支持的回滚类型'}), 400
            
    except Exception as e:
        _reraise_http(e)
        db.session.rollback()
        current_app.logger.error(f'回滚失败: {str(e)}')
        return jsonify({'success': False, 'message': f'回滚失败：{str(e)}'}), 500

@bp.route('/bonus_penalties/<int:id>', methods=['GET'])
@login_required
@require_capability('bonus.manage')
def get_bonus_penalty(id):
    """获取单个奖惩记录"""
    record = BonusPenalty.query.get_or_404(id)
    return jsonify({
        'id': record.id,
        'date': record.date.strftime('%Y-%m-%d'),
        'employee_id': record.employee_id,
        'process_id': record.process_id,
        'amount': float(record.amount),
        'reason': record.reason,
        'type': record.type
    })

@bp.route('/bonus_penalties/<int:id>/update', methods=['POST'])
@login_required
@require_capability('bonus.manage')
def update_bonus_penalty(id):
    """更新奖惩记录"""
    
    try:
        record = BonusPenalty.query.get_or_404(id)
        data = request.get_json()
        
        # 保存旧数据用于回滚
        old_data = {
            'employee_id': record.employee_id,
            'type': record.type,
            'amount': record.amount,
            'reason': record.reason,
            'date': record.date.isoformat() if record.date else None,
            'process_id': record.process_id
        }
        
        # 更新数据
        record.employee_id = data.get('employee_id')
        record.type = data.get('type')
        record.amount = data.get('amount')
        record.reason = data.get('reason')
        record.date = datetime.strptime(data.get('date'), '%Y-%m-%d').date() if data.get('date') else None
        record.process_id = data.get('process_id') if data.get('process_id') != 0 else None
        
        # 记录可回滚的审计日志
        log = AuditLog(
            user_id=current_user.id,
            action='修改奖惩记录',
            details=f'修改{"奖金" if record.type == "bonus" else "罚款"}记录：员工ID {record.employee_id}，金额 {record.amount}',
            can_rollback=True,
            rollback_type='edit',
            target_model='BonusPenalty',
            target_id=record.id,
            old_data=old_data,
            new_data={
                'employee_id': record.employee_id,
                'type': record.type,
                'amount': record.amount,
                'reason': record.reason,
                'date': record.date.isoformat() if record.date else None,
                'process_id': record.process_id
            }
        )
        db.session.add(log)
        db.session.commit()
        
        return jsonify({'success': True, 'message': '记录更新成功'})
    except Exception as e:
        _reraise_http(e)
        db.session.rollback()
        current_app.logger.error(f'更新奖惩记录失败: {str(e)}')
        return jsonify({'success': False, 'message': f'更新失败：{str(e)}'}), 500

@bp.route('/tasks/<int:id>', methods=['GET'])
@login_required
@require_capability('task.manage')
def get_task(id):
    """获取单个任务"""
    try:
        task = TaskAssignment.query.get_or_404(id)
        return jsonify({
            'success': True,
            'data': {
                'id': task.id,
                'assigned_date': task.assigned_date.strftime('%Y-%m-%d'),
                'target_date': task.target_date.strftime('%Y-%m-%d'),
                'employee_id': task.employee_id,
                'process_id': task.process_id,
                'quantity': task.quantity,
                'status': task.status
            }
        })
    except Exception as e:
        _reraise_http(e)
        current_app.logger.error(f'获取任务失败: {str(e)}')
        return jsonify({'success': False, 'message': f'获取失败：{str(e)}'}), 500

@bp.route('/tasks/add', methods=['POST'])
@login_required
@require_capability('task.manage')
def add_task():
    """添加任务"""
    
    try:
        data = request.get_json()
        
        # 获取对应的工序价格记录和员工记录
        process_price = ProcessPrice.query.get(data.get('process_id'))
        employee = Employee.query.get(data.get('employee_id'))
        
        if not process_price:
            return jsonify({'success': False, 'message': '未找到对应的工序'}), 400
        
        if not employee:
            return jsonify({'success': False, 'message': '未找到对应的员工'}), 400
        
        # 创建任务分配记录
        task = TaskAssignment(
            global_sn=SerialNumber.get_next_number(),
            employee_id=data.get('employee_id'),
            process_id=data.get('process_id'),
            quantity=data.get('quantity'),
            target_date=datetime.strptime(data.get('target_date'), '%Y-%m-%d').date() if data.get('target_date') else None,
            notes=data.get('notes'),
            status='pending',  # 设置初始状态为待处理
            assigned_date=datetime.now().date(),  # 设置分配日期
            # 规格型号信息
            spec_extended=data.get('spec_extended'),
            spec_gasket=data.get('spec_gasket'),
            spec_joint=data.get('spec_joint'),
            spec_drilling=data.get('spec_drilling'),
            spec_other=data.get('spec_other'),
            spec_other_desc=data.get('spec_other_desc'),
            direction=data.get('direction')
        )
        db.session.add(task)
        db.session.flush()  # 获取task.id
        
        # 记录审计日志
        log = AuditLog(
            user_id=current_user.id,
            action='分配生产任务',
            details=f'将工序 {process_price.process_name} 分配给员工 {employee.name}，数量：{task.quantity}',
            can_rollback=True,
            rollback_type='add',
            target_model='TaskAssignment',
            target_id=task.id,
            new_data={
                'employee_id': task.employee_id,
                'process_id': task.process_id,
                'quantity': task.quantity,
                'target_date': task.target_date.isoformat() if task.target_date else None,
                'notes': task.notes,
                'status': task.status
            }
        )
        db.session.add(log)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': '任务分配成功',
            'task': {
                'id': task.id,
                'employee_name': employee.name,
                'process_name': process_price.process_name,
                'quantity': task.quantity,
                'target_date': task.target_date.strftime('%Y-%m-%d') if task.target_date else None,
                'status': task.status
            }
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'添加任务失败: {str(e)}')
        return jsonify({'success': False, 'message': f'添加失败：{str(e)}'}), 500

@bp.route('/tasks/assignment/<int:id>', methods=['GET'])
@login_required
@require_capability('task.manage')
def get_task_assignment(id):
    """获取任务分配详情"""
    try:
        task = TaskAssignment.query.get_or_404(id)
        return jsonify({
            'success': True,
            'data': {
                'id': task.id,
                'assigned_date': task.assigned_date.strftime('%Y-%m-%d'),
                'employee_id': task.employee_id,
                'process_id': task.process_id,
                'quantity': task.quantity,
                'target_date': task.target_date.strftime('%Y-%m-%d') if task.target_date else None,
                'notes': task.notes,
                'status': task.status,
                'completed_quantity': task.completed_quantity
            }
        })
    except Exception as e:
        _reraise_http(e)
        current_app.logger.error(f'获取任务分配详情失败: {str(e)}')
        return jsonify({'success': False, 'message': f'获取失败：{str(e)}'}), 500

@bp.route('/tasks/<int:id>/edit', methods=['POST'])
@login_required
@require_capability('task.manage')
def edit_task(id):
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': '无效的请求数据'}), 400
        
        task = TaskAssignment.query.get_or_404(id)
        employee = Employee.query.get(data.get('employee_id'))
        process = ProcessPrice.query.get(data.get('process_id'))
        
        if not employee or not process:
            return jsonify({'success': False, 'message': '员工或工序不存在'}), 400
            
        # 保存旧数据用于回滚
        old_data = {
            'employee_id': task.employee_id,
            'process_id': task.process_id,
            'quantity': task.quantity,
            'target_date': task.target_date.isoformat() if task.target_date else None,
            'notes': task.notes,
            'status': task.status,
            'completed_quantity': task.completed_quantity
        }
            
        # 更新任务信息
        task.target_date = datetime.strptime(data.get('target_date'), '%Y-%m-%d').date()
        task.employee_id = data.get('employee_id')
        task.process_id = data.get('process_id')
        task.quantity = data.get('quantity')
        
        # 更新状态
        new_status = data.get('status')
        if new_status in ['pending', 'completed', 'cancelled']:
            task.status = new_status
            # TaskAssignment 只有 completed_at（DateTime），没有 completed_date/cancelled_date；
            # 原来写的是不存在的属性，赋值被 SQLAlchemy 静默丢弃、完成时间从未落库
            if new_status == 'completed':
                task.completed_at = datetime.now()
        
        # 记录可回滚的审计日志
        log = AuditLog(
            user_id=current_user.id,
            action='修改生产任务',
            details=f'修改任务：员工 {employee.name}，工序 {process.process_name}，数量：{task.quantity}',
            can_rollback=True,
            rollback_type='edit',
            target_model='TaskAssignment',
            target_id=task.id,
            old_data=old_data,
            new_data={
                'employee_id': task.employee_id,
                'process_id': task.process_id,
                'quantity': task.quantity,
                'target_date': task.target_date.isoformat() if task.target_date else None,
                'notes': task.notes,
                'status': task.status,
                'completed_quantity': task.completed_quantity
            },
            timestamp=datetime.now()  # 使用本地时间
        )
        db.session.add(log)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': '任务修改成功',
            'task': {
                'id': task.id,
                'employee_name': employee.name,
                'process_name': process.process_name,
                'quantity': task.quantity,
                'target_date': task.target_date.strftime('%Y-%m-%d') if task.target_date else None,
                'status': task.status
            }
        })
    except Exception as e:
        _reraise_http(e)
        db.session.rollback()
        current_app.logger.error(f'更新任务失败: {str(e)}')
        return jsonify({'success': False, 'message': f'更新失败：{str(e)}'}), 500

@bp.route('/employee_salary_changes/<int:employee_id>')
@login_required
@require_capability('employee.salary_change')
@handle_pagination_args
def employee_salary_changes(employee_id):
    page = request.validated_page
    per_page = request.validated_per_page
    
    # 获取员工信息
    employee = Employee.query.get_or_404(employee_id)
    
    # 直接查询对象而不是字段
    salary_changes = SalaryChange.query.filter_by(employee_id=employee_id).all()
    coefficient_changes = CoefficientChange.query.filter_by(employee_id=employee_id).all()
    
    # 合并两种变更记录并添加类型标记
    records = []
    for change in salary_changes:
        records.append({
            'id': change.id,
            'global_sn': change.global_sn,
            'change_type': 'salary',
            'old_value': change.old_salary,
            'new_value': change.new_salary,
            'effective_date': change.effective_date,
            'reason': change.reason,
            'created_at': change.created_at,
            'creator': User.query.get(change.created_by) if change.created_by else None
        })
    
    for change in coefficient_changes:
        records.append({
            'id': change.id,
            'global_sn': change.global_sn,
            'change_type': 'coefficient',
            'old_value': change.old_coefficient,
            'new_value': change.new_coefficient,
            'effective_date': change.effective_date,
            'reason': change.reason,
            'created_at': change.created_at,
            'creator': User.query.get(change.created_by) if change.created_by else None
        })
    
    # 按创建时间倒序排序
    records.sort(key=lambda x: x['created_at'], reverse=True)
    
    # 手动分页
    total = len(records)
    start = (page - 1) * per_page
    end = min(start + per_page, total)
    paged_records = records[start:end]
    
    # 创建分页对象
    pagination = Pagination(page=page, per_page=per_page, total=total, items=paged_records)
    
    # 为添加表单创建员工JSON数据
    employee_json = {
        'id': employee.id,
        'employee_id': employee.employee_id,
        'name': employee.name,
        'base_salary': employee.base_salary,
        'coefficient': employee.coefficient
    }
    
    return render_template('main/employee_salary_changes.html',
                          employee=employee,
                          employee_json=employee_json,
                          records=paged_records,
                          pagination=pagination,
                          now=datetime.now())

@bp.route('/add_salary_change', methods=['POST'])
@login_required
@require_capability('employee.salary_change')
def add_salary_change():
    
    data = request.get_json()
    employee_id = data.get('employee_id')
    change_type = data.get('change_type')
    old_value = float(data.get('old_value'))
    new_value = float(data.get('new_value'))
    effective_date = datetime.strptime(data.get('effective_date'), '%Y-%m-%d')
    reason = data.get('reason')
    
    try:
        if change_type == 'salary':
            change = SalaryChange(
                global_sn=SerialNumber.get_next_number(),
                employee_id=employee_id,
                old_salary=old_value,
                new_salary=new_value,
                effective_date=effective_date,
                reason=reason,
                creator_id=current_user.id
            )
        else:
            change = CoefficientChange(
                global_sn=SerialNumber.get_next_number(),
                employee_id=employee_id,
                old_coefficient=old_value,
                new_coefficient=new_value,
                effective_date=effective_date,
                reason=reason,
                creator_id=current_user.id
            )
        
        db.session.add(change)
        db.session.commit()
        
        # 添加审计日志
        log = AuditLog(
            user_id=current_user.id,
            action=f"添加{'工资' if change_type == 'salary' else '工资系数'}变更记录",
            details=f"为员工ID {employee_id} 添加{'工资' if change_type == 'salary' else '工资系数'}变更记录，从 {old_value} 变更为 {new_value}，生效日期 {data.get('effective_date')}",
            can_rollback=True,
            rollback_type='add',
            target_model='SalaryChange' if change_type == 'salary' else 'CoefficientChange',
            target_id=change.id
        )
        db.session.add(log)
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"添加工资变更记录失败: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})
@bp.route('/delete_salary_change', methods=['POST'])
@login_required
@require_capability('employee.salary_change')
def delete_salary_change():
    
    change_id = request.form.get('id')
    
    try:
        # 尝试删除工资变更记录
        salary_change = SalaryChange.query.get(change_id)
        if salary_change and salary_change.effective_date >= datetime.now().date():
            # 添加审计日志
            log = AuditLog(
                user_id=current_user.id,
                action="删除工资变更记录",
                details=f"删除工资变更记录ID {change_id}，员工ID {salary_change.employee_id}，从 {salary_change.old_salary} 变更为 {salary_change.new_salary}，生效日期 {salary_change.effective_date}",
                can_rollback=True,
                rollback_type='delete',
                target_model='SalaryChange',
                target_id=salary_change.id,
                old_data={
                    'employee_id': salary_change.employee_id,
                    'old_salary': salary_change.old_salary,
                    'new_salary': salary_change.new_salary,
                    'effective_date': salary_change.effective_date.strftime('%Y-%m-%d'),
                    'reason': salary_change.reason,
                    'creator_id': salary_change.created_by
                }
            )
            db.session.add(log)
            
            db.session.delete(salary_change)
            db.session.commit()
            return jsonify({'success': True})
        
        # 尝试删除系数变更记录
        coefficient_change = CoefficientChange.query.get(change_id)
        if coefficient_change and coefficient_change.effective_date >= datetime.now().date():
            # 添加审计日志
            log = AuditLog(
                user_id=current_user.id,
                action="删除工资系数变更记录",
                details=f"删除工资系数变更记录ID {change_id}，员工ID {coefficient_change.employee_id}，从 {coefficient_change.old_coefficient} 变更为 {coefficient_change.new_coefficient}，生效日期 {coefficient_change.effective_date}",
                can_rollback=True,
                rollback_type='delete',
                target_model='CoefficientChange',
                target_id=coefficient_change.id,
                old_data={
                    'employee_id': coefficient_change.employee_id,
                    'old_coefficient': coefficient_change.old_coefficient,
                    'new_coefficient': coefficient_change.new_coefficient,
                    'effective_date': coefficient_change.effective_date.strftime('%Y-%m-%d'),
                    'reason': coefficient_change.reason,
                    'creator_id': coefficient_change.created_by
                }
            )
            db.session.add(log)
            
            db.session.delete(coefficient_change)
            db.session.commit()
            return jsonify({'success': True})
        
        return jsonify({'success': False, 'message': '记录不存在或已生效'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"删除工资变更记录失败: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})

@bp.route('/inventory')
@login_required
@require_capability('inventory.view')
@handle_pagination_args
def manage_inventory():
    # 分页口径统一走 @handle_pagination_args（per_page 白名单 20/50/100）
    page = request.validated_page
    per_page = request.validated_per_page
    inventory_type = request.args.get('type', 'finished')
    search = request.args.get('search', '')
    show_archived = request.args.get('show_archived', '0') == '1'
    
    if inventory_type == 'raw':
        query = RawMaterial.query
        if search:
            # material_name 是取 category.name 的 property，不能直接进 SQL
            query = query.join(
                RawMaterialCategory, RawMaterial.category_id == RawMaterialCategory.id
            ).filter(or_(
                RawMaterial.supplier.ilike(f'%{search}%'),
                RawMaterialCategory.name.ilike(f'%{search}%'),
                RawMaterial.melt_number.ilike(f'%{search}%'),
                RawMaterial.supplier_number.ilike(f'%{search}%'),
                RawMaterial.internal_number.ilike(f'%{search}%')
            ))
        if not show_archived:
            # 上面 join 之后 filter_by 会落到 RawMaterialCategory 上，必须写全限定
            query = query.filter(RawMaterial.is_archived.is_(False))
    else:
        query = FinishedProduct.query
        if search:
            query = query.filter(or_(
                FinishedProduct.product_number.ilike(f'%{search}%'),
                FinishedProduct.drawing_number.ilike(f'%{search}%'),
                FinishedProduct.model.ilike(f'%{search}%'),
                FinishedProduct.inspector.ilike(f'%{search}%')
            ))
        if not show_archived:
            query = query.filter_by(is_archived=False)
    
    pagination = query.order_by(desc('id')).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return render_template('main/inventory.html',
                         inventory=pagination.items,
                         pagination=pagination,
                         show_archived=show_archived)

@bp.route('/inventory/template')
@login_required
@require_capability('inventory.view')
def download_inventory_template():
    """下载库存导入模板"""
    inventory_type = request.args.get('type', 'finished')
    
    # 创建工作簿
    wb = Workbook()
    ws = wb.active
    ws.title = "库存导入模板"
    
    if inventory_type == 'finished':
        headers = ['产品编号*', '生产日期*', '图号*', '型号*', '检验员*', '状态*', '备注']
        example_data = [
            ['P2024001', '2024-03-20', 'DWG-001', 'MODEL-A', '张三', 'in_stock', '示例数据'],
            ['P2024002', '2024-03-20', 'DWG-002', 'MODEL-B', '李四', 'in_stock', '示例数据']
        ]
        filename = '成品库存导入模板.xlsx'
    else:
        headers = ['供应商*', '品名*', '原料冶炼炉号*', '供应商编号*', '入库时间*', '数量*', '是否带样品', '备注']
        example_data = [
            ['供应商A', '钢材', 'M001', 'S001', '2024-03-20', '100', '是', '示例数据'],
            ['供应商B', '铝材', 'M002', 'S002', '2024-03-20', '200', '否', '示例数据']
        ]
        filename = '原材料库存导入模板.xlsx'
    
    # 添加表头
    ws = ExcelGenerator.add_headers(wb, headers)
    
    # 添加示例数据
    for i, row in enumerate(example_data, 2):
        ExcelGenerator.add_row(ws, row, i)
    
    # 添加说明
    start_row = len(example_data) + 3
    ws.cell(row=start_row, column=1, value='说明：')
    ws.cell(row=start_row + 1, column=1, value='1. 标记*的字段为必填项')
    if inventory_type == 'finished':
        ws.cell(row=start_row + 2, column=1, value='2. 状态可选值：in_stock(在库), shipped(已发货), scrapped(报废), used(已使用)')
    else:
        ws.cell(row=start_row + 2, column=1, value='2. 是否带样品可选值：是, 否')
    ws.cell(row=start_row + 3, column=1, value='3. 日期格式：YYYY-MM-DD')
    
    # 调整列宽
    for col in ws.columns:
        max_length = 0
        for cell in col:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except OSError:
                pass
        ws.column_dimensions[col[0].column_letter].width = max_length + 2
    
    # 返回文件
    return ExcelGenerator.generate_response(wb, filename)

@bp.route('/inventory/finished/import', methods=['POST'])
@login_required
@require_capability('inventory.manage')
def import_finished_products():
    """导入成品库存"""
    
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': '没有上传文件'})
    
    file = request.files['file']
    if not file or not file.filename.endswith('.xlsx'):
        return jsonify({'success': False, 'message': '请上传Excel文件'})
    
    try:
        # 保存临时文件
        temp_path = os.path.join(tempfile.gettempdir(), secure_filename(file.filename))
        file.save(temp_path)
        
        # 读取Excel文件
        df = pd.read_excel(temp_path)
        
        # 验证必要的列是否存在
        required_columns = ['产品编号', '生产日期', '图号', '型号', '检验员', '状态']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            return jsonify({'success': False, 'message': f'缺少必要的列：{", ".join(missing_columns)}'})
        
        # 开始导入
        success_count = 0
        error_messages = []
        
        for index, row in df.iterrows():
            try:
                # 创建成品记录
                product = FinishedProduct(
                    global_sn=SerialNumber.get_next_number(),
                    serial_number=SerialNumber.get_next_number(),
                    product_number=str(row['产品编号']),
                    production_date=pd.to_datetime(row['生产日期']).date(),
                    drawing_number=str(row['图号']),
                    model=str(row['型号']),
                    inspector=str(row['检验员']),
                    status=str(row['状态']),
                    notes=str(row.get('备注', ''))
                )
                db.session.add(product)
                
                # 记录审计日志
                log = AuditLog(
                    user_id=current_user.id,
                    action='导入成品',
                    details=f'导入成品：{product.product_number}',
                    can_rollback=True,
                    rollback_type='add',
                    target_model='FinishedProduct',
                    target_id=product.id,
                    new_data={
                        'product_number': product.product_number,
                        'drawing_number': product.drawing_number,
                        'model': product.model,
                        'inspector': product.inspector,
                        'status': product.status
                    }
                )
                db.session.add(log)
                
                success_count += 1
            except Exception as e:
                error_messages.append(f'第{index+2}行导入失败：{str(e)}')
        
        db.session.commit()
        
        # 返回结果
        message = f'成功导入{success_count}条记录'
        if error_messages:
            message += f'，{len(error_messages)}条记录导入失败：\n' + '\n'.join(error_messages)
        
        return jsonify({'success': True, 'message': message})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'导入失败：{str(e)}'})
    finally:
        # 清理临时文件
        if os.path.exists(temp_path):
            os.remove(temp_path)

@bp.route('/inventory/raw/import', methods=['POST'])
@login_required
@require_capability('inventory.manage')
def import_raw_materials():
    """导入原材料库存"""
    
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': '没有上传文件'})
    
    file = request.files['file']
    if not file or not file.filename.endswith('.xlsx'):
        return jsonify({'success': False, 'message': '请上传Excel文件'})
    
    try:
        # 保存临时文件
        temp_path = os.path.join(tempfile.gettempdir(), secure_filename(file.filename))
        file.save(temp_path)
        
        # 读取Excel文件
        df = pd.read_excel(temp_path)
        
        # 验证必要的列是否存在
        required_columns = ['供应商', '品名', '原料冶炼炉号', '供应商编号', '入库时间', '数量']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            return jsonify({'success': False, 'message': f'缺少必要的列：{", ".join(missing_columns)}'})
        
        # 开始导入
        success_count = 0
        error_messages = []
        
        for index, row in df.iterrows():
            try:
                # 创建原材料记录
                # 品名在 RawMaterial 上是取 category.name 的 @property，不是列；
                # 必须落成真实品类（不存在则按需建），否则 category_id 缺失 + TypeError
                category = _resolve_raw_material_category(row['品名'], current_user.id)
                material = RawMaterial(
                    global_sn=SerialNumber.get_next_number(),
                    supplier=str(row['供应商']),
                    category_id=category.id,
                    melt_number=str(row['原料冶炼炉号']),
                    supplier_number=str(row['供应商编号']),
                    storage_date=pd.to_datetime(row['入库时间']).date(),
                    internal_number=SerialNumber.get_next_number(),
                    quantity=float(row['数量']),
                    has_sample=bool(row.get('是否带样品', False)),
                    notes=str(row.get('备注', ''))
                )
                db.session.add(material)
                
                # 记录审计日志
                log = AuditLog(
                    user_id=current_user.id,
                    action='导入原材料',
                    details=f'导入原材料：{material.material_name}',
                    can_rollback=True,
                    rollback_type='add',
                    target_model='RawMaterial',
                    target_id=material.id,
                    new_data={
                        'supplier': material.supplier,
                        'material_name': material.material_name,
                        'melt_number': material.melt_number,
                        'supplier_number': material.supplier_number,
                        'quantity': material.quantity
                    }
                )
                db.session.add(log)
                
                success_count += 1
            except Exception as e:
                error_messages.append(f'第{index+2}行导入失败：{str(e)}')
        
        db.session.commit()
        
        # 返回结果
        message = f'成功导入{success_count}条记录'
        if error_messages:
            message += f'，{len(error_messages)}条记录导入失败：\n' + '\n'.join(error_messages)
        
        return jsonify({'success': True, 'message': message})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'导入失败：{str(e)}'})
    finally:
        # 清理临时文件
        if os.path.exists(temp_path):
            os.remove(temp_path)

def validate_raw_material_data(df):
    """验证原材料数据的必填字段"""
    required_columns = ['name', 'specification', 'unit', 'unit_price', 'quantity']
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        return False, f"缺少必填列：{', '.join(missing_columns)}"
    return True, None

def validate_finished_product_data(df):
    """验证成品数据的必填字段"""
    required_columns = ['name', 'model', 'specification', 'unit', 'unit_price', 'quantity']
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        return False, f"缺少必填列：{', '.join(missing_columns)}"
    return True, None

def allowed_file(filename: str, allowed_extensions: set = {'xlsx', 'xls'}) -> bool:
    """检查文件扩展名是否允许上传"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

def validate_excel_file(file: FileStorage) -> Optional[str]:
    """验证上传的Excel文件"""
    if not file:
        return "未选择文件"
    if not allowed_file(file.filename):
        return "不支持的文件格式，请上传Excel文件(.xlsx或.xls)"
    return None

def save_temp_file(file: FileStorage) -> str:
    """保存上传的文件到临时目录"""
    temp_dir = tempfile.mkdtemp()
    temp_path = os.path.join(temp_dir, secure_filename(file.filename))
    file.save(temp_path)
    return temp_path


@bp.route('/inventory/finished/add', methods=['POST'])
@login_required
@require_capability('inventory.manage')
def add_finished_product():
    """添加单个成品"""
    
    try:
        # 检查Content-Type
        if not request.is_json:
            return jsonify({'success': False, 'message': '请求必须是JSON格式'})
            
        data = request.json
        if not data:
            return jsonify({'success': False, 'message': '请求数据为空'})
            
        # 打印日志，辅助调试
        current_app.logger.info(f"接收到添加成品请求: {data}")
        
        # 检查必填字段
        required_fields = ['drawing_number', 'model', 'production_date', 'inspector']
        missing_fields = [field for field in required_fields if field not in data or not data[field]]
        
        if missing_fields:
            return jsonify({'success': False, 'message': f'缺少必要的字段：{", ".join(missing_fields)}'})
        
        # 处理产品编号
        product_number = None
        if data.get('product_number_type') == 'manual':
            if not data.get('product_number'):
                return jsonify({'success': False, 'message': '手动输入模式下产品编号不能为空'})
            product_number = data['product_number']
        else:  # 使用编码规则
            if not data.get('code_rule_id'):
                return jsonify({'success': False, 'message': '请选择编码规则'})
            
            # 获取编码规则并生成编码
            rule = CodeRule.query.get(data['code_rule_id'])
            if not rule:
                return jsonify({'success': False, 'message': '编码规则不存在'})
            if not rule.is_active:
                return jsonify({'success': False, 'message': '编码规则已禁用'})
            
            product_number = rule.generate_code()
        
        # 创建成品记录
        product = FinishedProduct(
            global_sn=SerialNumber.get_next_number(),
            serial_number=SerialNumber.get_next_number(),
            product_number=product_number,
            production_date=datetime.strptime(data['production_date'], '%Y-%m-%d').date(),
            drawing_number=data['drawing_number'],
            model=data['model'],
            inspector=data['inspector'],
            status='in_stock',
            notes=data.get('notes', '')
        )
        
        # 添加到数据库
        db.session.add(product)
        
        # 记录审计日志
        log = AuditLog(
            user_id=current_user.id,
            action='添加成品',
            details=f'添加成品：{product.product_number}',
            can_rollback=True,
            rollback_type='add',
            target_model='FinishedProduct',
            target_id=product.id,
            new_data={
                'product_number': product.product_number,
                'drawing_number': product.drawing_number,
                'model': product.model,
                'inspector': product.inspector,
                'status': product.status
            }
        )
        db.session.add(log)
        
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': '成功添加成品',
            'id': product.id
        })
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'添加失败：{str(e)}'})

@bp.route('/inventory/raw/add', methods=['POST'])
@login_required
@require_capability('inventory.manage')
def add_raw_material():
    """添加单个原材料"""
    
    try:
        # 检查Content-Type
        if not request.is_json:
            return jsonify({'success': False, 'message': '请求必须是JSON格式'})
            
        data = request.json
        if not data:
            return jsonify({'success': False, 'message': '请求数据为空'})
            
        # 打印日志，辅助调试
        current_app.logger.info(f"接收到添加原材料请求: {data}")
        
        # 检查必填字段（移除了melt_number）
        required_fields = ['supplier', 'category_id', 'supplier_number', 'storage_date', 'quantity']
        missing_fields = [field for field in required_fields if field not in data or not data[field]]
        
        if missing_fields:
            return jsonify({'success': False, 'message': f'缺少必要的字段：{", ".join(missing_fields)}'})
        
        # 处理内部编号
        internal_number = None
        if data.get('internal_number_type') == 'manual':
            internal_number = data.get('internal_number', '')
        else:  # 使用编码规则
            if not data.get('code_rule_id'):
                return jsonify({'success': False, 'message': '请选择编码规则'})
            
            # 获取编码规则并生成编码
            rule = CodeRule.query.get(data['code_rule_id'])
            if not rule:
                return jsonify({'success': False, 'message': '编码规则不存在'})
            if not rule.is_active:
                return jsonify({'success': False, 'message': '编码规则已禁用'})
            
            internal_number = rule.generate_code()
        
        # 验证品类ID
        category_id = data.get('category_id')
        if not category_id:
            return jsonify({'success': False, 'message': '请选择原材料品类'})
        
        # 验证品类是否存在
        from app.models import RawMaterialCategory
        category = RawMaterialCategory.query.get(category_id)
        if not category or not category.is_active:
            return jsonify({'success': False, 'message': '选择的原材料品类无效'})
        
        # 创建原材料记录
        material = RawMaterial(
            global_sn=SerialNumber.get_next_number(),
            supplier=data['supplier'],
            category_id=category_id,
            melt_number=data.get('melt_number', ''),  # 修改为可选字段
            supplier_number=data['supplier_number'],
            storage_date=datetime.strptime(data['storage_date'], '%Y-%m-%d').date(),
            internal_number=internal_number or SerialNumber.get_next_number(),
            quantity=float(data['quantity']),
            has_sample=data.get('has_sample', False),
            notes=data.get('notes', '')
        )
        
        # 添加到数据库
        db.session.add(material)
        
        # 记录审计日志
        log = AuditLog(
            user_id=current_user.id,
            action='添加原材料',
            details=f'添加原材料：{material.material_name} ({material.category_code})',
            can_rollback=True,
            rollback_type='add',
            target_model='RawMaterial',
            target_id=material.id,
            new_data={
                'supplier': material.supplier,
                'category_id': material.category_id,
                'material_name': material.material_name,  # 通过品类获取
                'melt_number': material.melt_number,
                'supplier_number': material.supplier_number,
                'internal_number': material.internal_number,
                'quantity': material.quantity,
                'status': material.status
            }
        )
        db.session.add(log)
        
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': '成功添加原材料',
            'id': material.id
        })
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'添加失败：{str(e)}'})

# ==================== 系统配置 ====================

SYSTEM_CONFIG_CATEGORY_LABELS = {
    'purchase': '采购',
    'quality': '质量',
    'material': '物料',
    'general': '通用',
}


@bp.route('/system_configs', methods=['GET', 'POST'])
@login_required
@require_capability('system_config.manage')
def manage_system_configs():
    """系统配置管理：业务开关的统一入口"""
    from app.permissions import ROLES

    if request.method == 'POST':
        try:
            # 只动本次提交涵盖的配置项。原先遍历全表，bool 型一律按「表单里没有
            # 这个字段 = false」处理，于是只提交一个字段的 POST 会把其余开关全部
            # 静默关掉。cfg_present 由模板逐项声明；再并上表单里实际出现的
            # cfg__ 字段，兼容不带该声明的调用方。
            managed_keys = set(request.form.getlist('cfg_present'))
            managed_keys.update(
                name[len('cfg__'):] for name in request.form if name.startswith('cfg__')
            )

            configs = SystemConfig.query.all()
            changed = 0
            for config in configs:
                if config.key not in managed_keys:
                    continue
                field = f'cfg__{config.key}'
                if config.value_type == 'bool':
                    value = field in request.form
                elif config.value_type == 'json':
                    value = request.form.getlist(field)
                else:
                    if field not in request.form:
                        continue
                    value = request.form.get(field)

                if SystemConfig.set(config.key, value, current_user.id):
                    changed += 1

            db.session.commit()
            flash(f'已保存 {changed} 项配置' if changed else '配置未发生变化', 'success')
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'保存系统配置失败: {str(e)}')
            flash('保存失败，请重试', 'danger')
        return redirect(url_for('main.manage_system_configs'))

    configs = SystemConfig.query.order_by(SystemConfig.category, SystemConfig.key).all()
    grouped = {}
    for config in configs:
        grouped.setdefault(config.category or 'general', []).append(config)

    return render_template(
        'main/system_configs.html',
        grouped_configs=grouped,
        category_labels=SYSTEM_CONFIG_CATEGORY_LABELS,
        roles=ROLES
    )


@bp.route('/code_rules')
@login_required
@require_capability('code_rule.manage')
def manage_code_rules():
    """编码规则管理"""
    rules = CodeRule.query.order_by(CodeRule.created_at.desc()).all()
    return render_template('main/code_rules.html', rules=rules)
@bp.route('/code_rules/add', methods=['GET', 'POST'])
@login_required
@require_capability('code_rule.manage')
def add_code_rule():
    """添加编码规则"""
    
    if request.method == 'POST':
        try:
            data = request.get_json()
            
            # 创建新规则
            rule = CodeRule(
                name=data['name'],
                code_type=data['code_type'],
                prefix=data.get('prefix', ''),
                suffix=data.get('suffix', ''),
                sequence_length=int(data.get('sequence_length', 4)),
                reset_frequency=data.get('reset_frequency', 'never'),
                format_pattern=data['format_pattern'],
                created_by=current_user.id,
                notes=data.get('notes', '')
            )
            
            db.session.add(rule)
            
            # 添加审计日志
            log = AuditLog(
                user_id=current_user.id,
                action='添加编码规则',
                details=f'添加编码规则：{rule.name}',
                can_rollback=True,
                rollback_type='add',
                target_model='CodeRule',
                target_id=rule.id,
                new_data={
                    'name': rule.name,
                    'code_type': rule.code_type,
                    'format_pattern': rule.format_pattern
                }
            )
            db.session.add(log)
            
            db.session.commit()
            return jsonify({'success': True, 'message': '添加成功'})
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'添加失败：{str(e)}'})
    
    return render_template('main/code_rule_form.html', title='添加编码规则')

@bp.route('/code_rules/<int:rule_id>/edit', methods=['GET', 'POST'])
@login_required
@require_capability('code_rule.manage')
def edit_code_rule(rule_id):
    """编辑编码规则"""
    
    rule = CodeRule.query.get_or_404(rule_id)
    
    if request.method == 'POST':
        try:
            data = request.get_json()
            
            # 保存旧数据用于审计日志
            old_data = {
                'name': rule.name,
                'code_type': rule.code_type,
                'format_pattern': rule.format_pattern
            }
            
            # 更新规则
            rule.name = data['name']
            rule.code_type = data['code_type']
            rule.prefix = data.get('prefix', '')
            rule.suffix = data.get('suffix', '')
            rule.sequence_length = int(data.get('sequence_length', 4))
            rule.reset_frequency = data.get('reset_frequency', 'never')
            rule.format_pattern = data['format_pattern']
            rule.notes = data.get('notes', '')
            
            # 添加审计日志
            log = AuditLog(
                user_id=current_user.id,
                action='编辑编码规则',
                details=f'编辑编码规则：{rule.name}',
                can_rollback=True,
                rollback_type='edit',
                target_model='CodeRule',
                target_id=rule.id,
                old_data=old_data,
                new_data={
                    'name': rule.name,
                    'code_type': rule.code_type,
                    'format_pattern': rule.format_pattern
                }
            )
            db.session.add(log)
            
            db.session.commit()
            return jsonify({'success': True, 'message': '更新成功'})
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'更新失败：{str(e)}'})
    
    return render_template('main/code_rule_form.html', title='编辑编码规则', rule=rule)

@bp.route('/code_rules/<int:rule_id>/delete', methods=['POST'])
@login_required
@require_capability('code_rule.manage')
def delete_code_rule(rule_id):
    """删除编码规则"""
    
    rule = CodeRule.query.get_or_404(rule_id)
    
    try:
        # 保存旧数据用于审计日志
        old_data = {
            'name': rule.name,
            'code_type': rule.code_type,
            'format_pattern': rule.format_pattern
        }
        
        # 添加审计日志
        log = AuditLog(
            user_id=current_user.id,
            action='删除编码规则',
            details=f'删除编码规则：{rule.name}',
            can_rollback=True,
            rollback_type='delete',
            target_model='CodeRule',
            target_id=rule.id,
            old_data=old_data
        )
        db.session.add(log)
        
        db.session.delete(rule)
        db.session.commit()
        
        return jsonify({'success': True, 'message': '删除成功'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'删除失败：{str(e)}'})

@bp.route('/code_rules/<int:rule_id>/generate', methods=['POST'])
@login_required
@require_capability('code_rule.manage')
def generate_code(rule_id):
    """生成编码"""
        
    rule = CodeRule.query.get_or_404(rule_id)
    
    try:
        # 生成编码
        code = rule.generate_code()
        
        # 记录生成日志
        log = CodeGenerationLog(
            rule_id=rule.id,
            generated_code=code,
            created_by=current_user.id,
            target_type=request.json.get('target_type'),
            target_id=request.json.get('target_id')
        )
        db.session.add(log)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'code': code,
            'message': '编码生成成功'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'编码生成失败：{str(e)}'})

@bp.route('/code_rules/available/product', methods=['GET'])
@login_required
@require_capability('product.view')
def get_available_product_rules():
    """获取可用的产品编码规则"""
    try:
        rules = CodeRule.query.filter_by(code_type='product', is_active=True).all()
        current_app.logger.info(f"找到 {len(rules)} 个可用的产品编码规则")
        
        rules_data = [{
            'id': rule.id,
            'name': rule.name
        } for rule in rules]
        
        current_app.logger.debug(f"编码规则数据: {rules_data}")
        
        return jsonify({
            'success': True,
            'rules': rules_data
        })
    except Exception as e:
        current_app.logger.error(f"获取产品编码规则时出错: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'获取编码规则失败: {str(e)}'
        }), 500

@bp.route('/code_rules/available/material', methods=['GET'])
@login_required
@require_capability('inventory.view')
def get_available_material_rules():
    """获取可用的原材料编码规则"""
    try:
        rules = CodeRule.query.filter_by(code_type='material', is_active=True).all()
        current_app.logger.info(f"找到 {len(rules)} 个可用的原材料编码规则")
        
        rules_data = [{
            'id': rule.id,
            'name': rule.name
        } for rule in rules]
        
        current_app.logger.debug(f"编码规则数据: {rules_data}")
        
        return jsonify({
            'success': True,
            'rules': rules_data
        })
    except Exception as e:
        current_app.logger.error(f"获取原材料编码规则时出错: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'获取编码规则失败: {str(e)}'
        }), 500

@bp.route('/inventory/finished/<int:id>', methods=['GET'])
@login_required
@require_capability('inventory.view')
def get_finished_product(id):
    """获取成品详情"""
    
    try:
        product = FinishedProduct.query.get_or_404(id)
        return jsonify({
            'success': True,
            'data': {
                'id': product.id,
                'product_number': product.product_number,
                'drawing_number': product.drawing_number,
                'model': product.model,
                'production_date': product.production_date.strftime('%Y-%m-%d'),
                'inspector': product.inspector,
                'quantity': product.quantity,
                'status': product.status,
                'notes': product.notes or ''
            }
        })
    except Exception as e:
        _reraise_http(e)
        return jsonify({'success': False, 'message': f'获取成品详情失败：{str(e)}'})

@bp.route('/inventory/finished/<int:id>', methods=['PUT'])
@login_required
@require_capability('inventory.manage')
def update_finished_product(id):
    """更新成品信息"""
    
    try:
        product = FinishedProduct.query.get_or_404(id)
        data = request.json
        
        if not data:
            return jsonify({'success': False, 'message': '请求数据为空'})
        
        # 保存旧数据用于审计日志
        old_data = {
            'product_number': product.product_number,
            'drawing_number': product.drawing_number,
            'model': product.model,
            'production_date': product.production_date.strftime('%Y-%m-%d'),
            'inspector': product.inspector,
            'quantity': product.quantity,
            'status': product.status,
            'notes': product.notes
        }
        
        # 更新数据
        product.drawing_number = data['drawing_number']
        product.model = data['model']
        product.production_date = datetime.strptime(data['production_date'], '%Y-%m-%d').date()
        product.inspector = data['inspector']
        product.quantity = data['quantity']
        product.status = data['status']
        product.notes = data.get('notes', '')
        # FinishedProduct 没有 code_rule_id / updated_at 列（那是 Product 的列），
        # 原写法只是给实例挂了个不落库的临时属性，属于同一类「不存在的列」误用，已删除
        
        # 记录审计日志
        log = AuditLog(
            user_id=current_user.id,
            action='更新成品',
            details=f'更新成品：{product.product_number}',
            can_rollback=True,
            rollback_type='edit',
            target_model='FinishedProduct',
            target_id=product.id,
            old_data=old_data,
            new_data={
                'product_number': product.product_number,
                'drawing_number': product.drawing_number,
                'model': product.model,
                'production_date': product.production_date.strftime('%Y-%m-%d'),
                'inspector': product.inspector,
                'quantity': product.quantity,
                'status': product.status,
                'notes': product.notes
            }
        )
        db.session.add(log)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': '成功更新成品信息'
        })
        
    except Exception as e:
        _reraise_http(e)
        db.session.rollback()
        return jsonify({'success': False, 'message': f'更新失败：{str(e)}'})

@bp.route('/inventory/raw/<int:id>', methods=['GET'])
@login_required
@require_capability('inventory.view')
def get_raw_material(id):
    """获取原材料详情"""
    
    try:
        material = RawMaterial.query.get_or_404(id)
        return jsonify({
            'success': True,
            'data': {
                'id': material.id,
                'supplier': material.supplier,
                'category_id': material.category_id,
                'material_name': material.material_name,  # 通过品类获取
                'category_code': material.category_code,
                'melt_number': material.melt_number,
                'supplier_number': material.supplier_number,
                'internal_number': material.internal_number,
                'storage_date': material.storage_date.strftime('%Y-%m-%d'),
                'quantity': material.quantity,
                'status': material.status,
                'has_sample': material.has_sample,
                'notes': material.notes or ''
            }
        })
    except Exception as e:
        _reraise_http(e)
        return jsonify({'success': False, 'message': f'获取原材料详情失败：{str(e)}'})

@bp.route('/inventory/raw/<int:id>', methods=['PUT'])
@login_required
@require_capability('inventory.manage')
def update_raw_material(id):
    """更新原材料信息"""
    
    try:
        material = RawMaterial.query.get_or_404(id)
        data = request.json
        
        if not data:
            return jsonify({'success': False, 'message': '请求数据为空'})
        
        # 保存旧数据用于审计日志
        old_data = {
            'supplier': material.supplier,
            'category_id': material.category_id,
            'material_name': material.material_name,
            'melt_number': material.melt_number,
            'supplier_number': material.supplier_number,
            'internal_number': material.internal_number,
            'storage_date': material.storage_date.strftime('%Y-%m-%d'),
            'quantity': material.quantity,
            'status': material.status,
            'has_sample': material.has_sample,
            'notes': material.notes
        }
        
        # 验证品类ID
        category_id = data.get('category_id')
        if not category_id:
            return jsonify({'success': False, 'message': '请选择原材料品类'})
        
        # 验证品类是否存在
        from app.models import RawMaterialCategory
        category = RawMaterialCategory.query.get(category_id)
        if not category or not category.is_active:
            return jsonify({'success': False, 'message': '选择的原材料品类无效'})
        
        # 更新数据
        material.supplier = data['supplier']
        material.category_id = category_id
        material.melt_number = data.get('melt_number', '')  # 可选字段
        material.supplier_number = data['supplier_number']
        material.storage_date = datetime.strptime(data['storage_date'], '%Y-%m-%d').date()
        material.quantity = float(data['quantity'])
        material.status = data.get('status', 'in_stock')
        material.has_sample = data.get('has_sample', False)
        material.notes = data.get('notes', '')
        
        # 记录审计日志
        log = AuditLog(
            user_id=current_user.id,
            action='更新原材料',
            details=f'更新原材料：{material.material_name} ({material.category_code})',
            can_rollback=True,
            rollback_type='edit',
            target_model='RawMaterial',
            target_id=material.id,
            old_data=old_data,
            new_data={
                'supplier': material.supplier,
                'category_id': material.category_id,
                'material_name': material.material_name,  # 通过品类获取
                'melt_number': material.melt_number,
                'supplier_number': material.supplier_number,
                'internal_number': material.internal_number,
                'storage_date': material.storage_date.strftime('%Y-%m-%d'),
                'quantity': material.quantity,
                'status': material.status,
                'has_sample': material.has_sample,
                'notes': material.notes
            }
        )
        db.session.add(log)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': '成功更新原材料信息'
        })
        
    except Exception as e:
        _reraise_http(e)
        db.session.rollback()
        return jsonify({'success': False, 'message': f'更新失败：{str(e)}'})

@bp.route('/process_prices/<int:id>', methods=['GET'])
@login_required
@require_capability('process.view')
def get_process_price(id):
    """获取工序详情"""
    try:
        process = ProcessPrice.query.get_or_404(id)
        
        # 构建包含工序的数据
        included_processes = []
        if process.price_type == 'subtotal' and process.included_processes:
            for group in process.included_processes:
                included_processes.append({
                    'process': {
                        'process_code': group.process.process_code,
                        'process_name': group.process.process_name,
                        'component': group.process.component,
                        'price': float(group.process.price)
                    }
                })
        
        return jsonify({
            'success': True,
            'process': {
                'id': process.id,
                'process_code': process.process_code,
                'process_name': process.process_name,
                'component': process.component,
                'drawing_no': process.drawing_no,
                'model_no': process.model_no,
                'price': float(process.price),
                'effective_date': process.effective_date.strftime('%Y-%m-%d'),
                'price_type': process.price_type,
                'has_output': process.has_output,
                'output_type': process.output_type,
                'needs_inspection': process.needs_inspection,
                'code_rule_id': process.code_rule_id,
                'notes': process.notes,
                'included_processes': included_processes
            }
        })
    except Exception as e:
        _reraise_http(e)
        return jsonify({'success': False, 'message': f'获取工序详情失败：{str(e)}'}), 500



@bp.route('/inventory/raw/<int:id>', methods=['DELETE'])
@login_required
@require_capability('inventory.manage')
@csrf.exempt  # 对DELETE请求豁免CSRF保护
def delete_raw_material(id):
    """删除原材料"""
    
    try:
        material = RawMaterial.query.get_or_404(id)
        
        # 检查是否有关联的生产记录
        if len(material.production_records) > 0:
            return jsonify({
                'success': False, 
                'message': '该原材料已被使用，无法删除'
            }), 400
        
        # 保存旧数据用于审计日志
        old_data = {
            'supplier': material.supplier,
            'category_id': material.category_id,
            'material_name': material.material_name,  # 通过品类获取
            'melt_number': material.melt_number,
            'supplier_number': material.supplier_number,
            'internal_number': material.internal_number,
            'storage_date': material.storage_date.strftime('%Y-%m-%d'),
            'quantity': material.quantity,
            'status': material.status,
            'has_sample': material.has_sample,
            'notes': material.notes
        }
        
        # 记录审计日志
        log = AuditLog(
            user_id=current_user.id,
            action='删除原材料',
            details=f'删除原材料：{material.material_name} ({material.category_code})',
            can_rollback=True,
            rollback_type='delete',
            target_model='RawMaterial',
            target_id=material.id,
            old_data=old_data
        )
        db.session.add(log)
        
        # 删除原材料
        db.session.delete(material)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': '原材料删除成功'
        })
        
    except Exception as e:
        _reraise_http(e)
        db.session.rollback()
        current_app.logger.error(f'删除原材料失败: {str(e)}')
        return jsonify({
            'success': False,
            'message': f'删除失败：{str(e)}'
        }), 500

@bp.route('/inventory/finished/<int:id>', methods=['DELETE'])
@login_required
@require_capability('inventory.manage')
@csrf.exempt  # 对DELETE请求豁免CSRF保护
def delete_finished_product(id):
    """删除成品"""
    
    try:
        product = FinishedProduct.query.get_or_404(id)
        
        # 检查是否有关联的生产记录
        if len(product.production_records) > 0:
            return jsonify({
                'success': False, 
                'message': '该成品已关联生产记录，无法删除'
            }), 400
        
        # 保存旧数据用于审计日志
        old_data = {
            'product_number': product.product_number,
            'drawing_number': product.drawing_number,
            'model': product.model,
            'production_date': product.production_date.strftime('%Y-%m-%d'),
            'inspector': product.inspector,
            'quantity': product.quantity,
            'status': product.status,
            'notes': product.notes
        }
        
        # 记录审计日志
        log = AuditLog(
            user_id=current_user.id,
            action='删除成品',
            details=f'删除成品：{product.product_number}',
            can_rollback=True,
            rollback_type='delete',
            target_model='FinishedProduct',
            target_id=product.id,
            old_data=old_data
        )
        db.session.add(log)
        
        # 删除成品
        db.session.delete(product)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': '成品删除成功'
        })
        
    except Exception as e:
        _reraise_http(e)
        db.session.rollback()
        current_app.logger.error(f'删除成品失败: {str(e)}')
        return jsonify({
            'success': False,
            'message': f'删除失败：{str(e)}'
        }), 500

@bp.route('/tasks/<int:id>/get', methods=['GET'])
@login_required
def get_task_details(id):
    """获取任务详情"""
    try:
        task = TaskAssignment.query.get_or_404(id)
        
        # 检查权限：管理员可以查看所有任务，普通用户只能查看自己的任务
        if current_user.role not in ['admin', 'hr']:
            # 获取当前用户的员工记录
            employee = Employee.query.filter_by(user_id=current_user.id).first()
            if not employee or employee.id != task.employee_id:
                return jsonify({'success': False, 'message': '权限不足'}), 403
        
        # 附带返回该任务对应订单的BOM物料ID清单（用于前端校验但不强过滤）
        bom_material_ids = []
        try:
            from app.models import ProductionBatch, ProductionBatchItem, ProductionOrder, ProductBOM
            order = None
            if task.production_batch_id:
                batch = ProductionBatch.query.get(task.production_batch_id)
                order = batch.production_order if batch else None
            elif task.batch_item_id:
                item = ProductionBatchItem.query.get(task.batch_item_id)
                if item and item.batch:
                    order = item.batch.production_order
            if order and order.product_id:
                # 取该产品的BOM（仅 raw 类型）
                boms = ProductBOM.query.filter_by(product_id=order.product_id, material_type='raw').all()
                bom_material_ids = [b.material_id for b in boms]
        except Exception:
            pass

        return jsonify({
            'success': True,
            'data': {
                'id': task.id,
                'global_sn': task.global_sn,
                'employee_id': task.employee_id,
                'process_id': task.process_id,
                'quantity': task.quantity,
                'completed_quantity': task.completed_quantity,
                'status': task.status,
                'target_date': task.target_date.strftime('%Y-%m-%d') if task.target_date else None,
                'notes': task.notes,
                'bom_material_ids': bom_material_ids
            }
        })
    except Exception as e:
        _reraise_http(e)
        return jsonify({'success': False, 'message': f'获取任务详情失败：{str(e)}'}), 500

@bp.route('/api/inventory/raw-materials')
@login_required
@require_capability('material.lookup')
def get_available_raw_materials():
    """获取可用的原材料列表
    
    Query Parameters:
        only_available (bool): 是否只返回有库存的原材料
    """
    try:
        query = RawMaterial.query
        
        # 如果指定了only_available参数，只返回有库存的原材料
        if request.args.get('only_available', 'false').lower() == 'true':
            query = query.filter(RawMaterial.quantity > 0)
            
        raw_materials = query.all()
        materials_list = [{
                'id': material.id,
            'name': material.material_name,
            'material_name': material.material_name,  # 为了兼容性保留
            'specification': f"{material.internal_number} - {material.melt_number}",
            'quantity': material.quantity,
            'supplier': material.supplier,
            'melt_number': material.melt_number,
            'internal_number': material.internal_number
        } for material in raw_materials]
        
        return jsonify({
            'success': True,
            'data': materials_list
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'获取原材料列表失败: {str(e)}'
        }), 500

@bp.route('/api/inventory/finished-products')
@login_required
@require_capability('product.view')
def get_available_finished_products():
    """获取可用的成品列表
    
    Query Parameters:
        only_available (bool): 是否只返回有库存的成品
    """
    try:
        query = FinishedProduct.query
        
        # 如果指定了only_available参数，只返回有库存的成品
        if request.args.get('only_available', 'false').lower() == 'true':
            query = query.filter(FinishedProduct.status == 'in_stock')
            
        finished_products = query.all()
        # 成品表没有 specification/unit 列：规格按 raw-materials 同一风格用自身列拼，
        # 单位取关联产品（一次批量查，避免逐行懒加载打 N+1）
        product_ids = {p.product_id for p in finished_products if p.product_id}
        product_units = {}
        if product_ids:
            product_units = {
                pid: (unit or '件')
                for pid, unit in db.session.query(Product.id, Product.unit).filter(
                    Product.id.in_(product_ids)).all()
            }
        products_list = [{
            'id': product.id,
            'name': product.product_number,
            'product_number': product.product_number,  # 为了兼容性保留
            'drawing_number': product.drawing_number,
            'model': product.model,
            'serial_number': product.serial_number,
            # Select2 契约与 /api/inventory/raw-materials 对齐：id/name/specification/quantity
            'specification': f"{product.drawing_number or '-'} - {product.model or '-'}",
            'unit': product_units.get(product.product_id, '件'),
            'quantity': product.quantity,
            'status': product.status,
            'inspector': product.inspector,
            'production_date': product.production_date.strftime('%Y-%m-%d') if product.production_date else ''
        } for product in finished_products]
        
        return jsonify({
            'success': True,
            'data': products_list
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'获取成品列表失败: {str(e)}'
        }), 500

@bp.route('/api/inventory/consumables')
@login_required
@require_capability('inventory.manage')
def get_available_consumables():
    """获取可用的易耗品列表，结构与原材料接口一致。"""
    try:
        from app.models import Consumable
        query = Consumable.query.filter_by(is_archived=False)
        if request.args.get('only_available', 'false').lower() == 'true':
            query = query.filter(Consumable.quantity > 0, Consumable.status == 'in_stock')
        rows = query.all()
        data = [{
            'id': c.id,
            'name': c.consumable_name,
            'specification': c.specification or c.internal_number,
            'quantity': c.quantity,
            'unit': c.unit,
            'supplier': c.supplier,
            'internal_number': c.internal_number,
            'status': c.status,
        } for c in rows]
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'message': f'获取易耗品列表失败: {str(e)}'}), 500

@bp.route('/inventory/raw/<int:id>/archive', methods=['POST'])
@login_required
@require_capability('inventory.manage')
def toggle_raw_material_archive(id):
    """切换原材料存档状态"""
    
    try:
        material = RawMaterial.query.get_or_404(id)
        
        # 切换存档状态
        old_archived = material.is_archived
        material.is_archived = not material.is_archived
        action = '存档' if material.is_archived else '取消存档'
        
        # 记录审计日志
        log = AuditLog(
            user_id=current_user.id,
            action=f'{action}原材料',
            details=f'{action}原材料：{material.material_name}',
            can_rollback=True,
            rollback_type='edit',
            target_model='RawMaterial',
            target_id=material.id,
            old_data={'is_archived': old_archived},
            new_data={'is_archived': material.is_archived}
        )
        db.session.add(log)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'原材料{action}成功'
        })
        
    except Exception as e:
        _reraise_http(e)
        db.session.rollback()
        current_app.logger.error(f'原材料存档状态切换失败: {str(e)}')
        return jsonify({
            'success': False,
            'message': f'操作失败：{str(e)}'
        }), 500
@bp.route('/inventory/finished/<int:id>/archive', methods=['POST'])
@login_required
@require_capability('inventory.manage')
def toggle_finished_product_archive(id):
    """切换成品存档状态"""
    
    try:
        product = FinishedProduct.query.get_or_404(id)
        
        # 切换存档状态
        old_archived = product.is_archived
        product.is_archived = not product.is_archived
        action = '存档' if product.is_archived else '取消存档'
        
        # 记录审计日志
        log = AuditLog(
            user_id=current_user.id,
            action=f'{action}成品',
            details=f'{action}成品：{product.product_number}',
            can_rollback=True,
            rollback_type='edit',
            target_model='FinishedProduct',
            target_id=product.id,
            old_data={'is_archived': old_archived},
            new_data={'is_archived': product.is_archived}
        )
        db.session.add(log)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'成品{action}成功'
        })
        
    except Exception as e:
        _reraise_http(e)
        db.session.rollback()
        current_app.logger.error(f'成品存档状态切换失败: {str(e)}')
        return jsonify({
            'success': False,
            'message': f'操作失败：{str(e)}'
        }), 500

@bp.route('/inventory/auto-archive', methods=['POST'])
@login_required
@require_capability('inventory.manage')
def auto_archive_inventory():
    """自动存档库存"""
    try:
        data = request.get_json()
        days = data.get('days', 90)
        
        if not days or days < 1:
            return jsonify({'success': False, 'message': '天数必须大于0'})
        
        cutoff_date = datetime.now() - timedelta(days=days)
        
        # 存档成品：已发货、报废、已使用状态且超过指定天数
        # 未存档判定与发货路径同一口径（NULL 也视为「未存档」），否则历史 NULL 行永远不被自动归档
        finished_products = FinishedProduct.query.filter(
            FinishedProduct.status.in_(['shipped', 'scrapped', 'used']),
            FinishedProduct.created_at < cutoff_date,
            db.or_(FinishedProduct.is_archived.is_(False), FinishedProduct.is_archived.is_(None))
        ).all()
        
        # 存档原材料：数量为0且超过指定天数
        raw_materials = RawMaterial.query.filter(
            RawMaterial.quantity <= 0,
            RawMaterial.created_at < cutoff_date,
            db.or_(RawMaterial.is_archived.is_(False), RawMaterial.is_archived.is_(None))
        ).all()
        
        archived_count = 0
        
        # 存档成品
        for product in finished_products:
            product.is_archived = True
            archived_count += 1
        
        # 存档原材料
        for material in raw_materials:
            material.is_archived = True
            archived_count += 1
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'成功存档 {archived_count} 条记录'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'自动存档失败: {str(e)}'})


@bp.route('/inventory/inbound', methods=['GET', 'POST'])
@login_required
@require_capability('inventory.manage')
def inventory_inbound():
    """批量入库管理"""
    from app.main.forms import InventoryInboundForm
    from app.models import RawMaterial, FinishedProduct, SerialNumber, AuditLog
    
    form = InventoryInboundForm()
    
    if request.method == 'POST':
        try:
            # 获取所有表单数据
            form_data = request.form.to_dict()
            
            # 解析批量数据
            rows_data = {}
            for key, value in form_data.items():
                if '_' in key and key != 'csrf_token':
                    field_name, row_index = key.rsplit('_', 1)
                    if row_index.isdigit():
                        row_index = int(row_index)
                        if row_index not in rows_data:
                            rows_data[row_index] = {}
                        rows_data[row_index][field_name] = value
            
            success_count = 0
            error_messages = []
            
            # 处理每一行数据
            for row_index, row_data in rows_data.items():
                try:
                    inventory_type = row_data.get('inventory_type', '').strip()
                    if not inventory_type:
                        continue
                    
                    quantity = float(row_data.get('quantity', 0))
                    if quantity <= 0:
                        error_messages.append(f'第 {row_index + 1} 行：数量无效')
                        continue
                    
                    storage_date_str = row_data.get('storage_date', '')
                    if not storage_date_str:
                        error_messages.append(f'第 {row_index + 1} 行：入库日期不能为空')
                        continue
                    
                    try:
                        from datetime import datetime
                        storage_date = datetime.strptime(storage_date_str, '%Y-%m-%d').date()
                    except ValueError:
                        error_messages.append(f'第 {row_index + 1} 行：日期格式错误')
                        continue
                    
                    field1 = row_data.get('field1', '').strip()
                    field2 = row_data.get('field2', '').strip()
                    field3 = row_data.get('field3', '').strip()
                    field4 = row_data.get('field4', '').strip()
                    field5 = row_data.get('field5', '').strip()
                    notes = row_data.get('notes', '').strip()
                    has_sample = f'has_sample_{row_index}' in form_data
                    
                    if not field1 or not field2:
                        error_messages.append(f'第 {row_index + 1} 行：必填字段不能为空')
                        continue
                    
                    if inventory_type == 'raw':
                        # 原材料入库
                        if not field4:  # 供应商编号
                            error_messages.append(f'第 {row_index + 1} 行：供应商编号不能为空')
                            continue
                        
                        # 自动生成内部编号
                        internal_number = field5 if field5 else SerialNumber.get_next_number()
                        
                        # field2 是品名（品类名）：material_name 是 @property，写不进库，
                        # 必须落成真实外键 category_id
                        category = _resolve_raw_material_category(field2, current_user.id)
                        raw_material = RawMaterial(
                            supplier=field1,           # 供应商
                            category_id=category.id,   # 品名 -> 原材料品类
                            quantity=quantity,
                            storage_date=storage_date,
                            melt_number=field3 if field3 else '',        # 冶炼炉号
                            supplier_number=field4,    # 供应商编号
                            internal_number=internal_number,
                            has_sample=has_sample,
                            notes=notes,
                            status='in_stock'
                        )
                        
                        db.session.add(raw_material)
                        db.session.flush()  # 获取ID
                        
                        # 记录审计日志
                        audit_log = AuditLog(
                            user_id=current_user.id,
                            action='原材料入库',
                            details=f'入库原材料：{raw_material.material_name}，数量：{raw_material.quantity}',
                            can_rollback=True,
                            rollback_type='delete',
                            target_model='RawMaterial',
                            target_id=raw_material.id,
                            new_data={
                                'supplier': raw_material.supplier,
                                'material_name': raw_material.material_name,
                                'quantity': float(raw_material.quantity),
                                'storage_date': raw_material.storage_date.isoformat()
                            }
                        )
                        db.session.add(audit_log)
                        success_count += 1
                        
                    elif inventory_type == 'finished':
                        # 成品入库
                        if not field3 or not field4 or not field5:
                            error_messages.append(f'第 {row_index + 1} 行：成品信息不完整')
                            continue
                        
                        try:
                            production_date = datetime.strptime(field5, '%Y-%m-%d').date()
                        except ValueError:
                            error_messages.append(f'第 {row_index + 1} 行：生产日期格式错误')
                            continue
                        
                        # FinishedProduct 没有 storage_date 列：入库日期由 created_at 承担
                        # （与 search_service 对成品 storage_date 的过滤口径一致）
                        finished_product = FinishedProduct(
                            product_number=field1,     # 产品编号
                            drawing_number=field2,     # 图号
                            model=field3,              # 型号
                            quantity=int(quantity),
                            created_at=datetime.combine(storage_date, datetime.min.time()),
                            inspector=field4,          # 检验员
                            production_date=production_date,
                            notes=notes,
                            status='in_stock'
                        )
                        
                        db.session.add(finished_product)
                        db.session.flush()  # 获取ID
                        
                        # 记录审计日志
                        audit_log = AuditLog(
                            user_id=current_user.id,
                            action='成品入库',
                            details=f'入库成品：{finished_product.product_number}，数量：{finished_product.quantity}',
                            can_rollback=True,
                            rollback_type='delete',
                            target_model='FinishedProduct',
                            target_id=finished_product.id,
                            new_data={
                                'product_number': finished_product.product_number,
                                'drawing_number': finished_product.drawing_number,
                                'model': finished_product.model,
                                'quantity': finished_product.quantity,
                                'production_date': finished_product.production_date.isoformat()
                            }
                        )
                        db.session.add(audit_log)
                        success_count += 1
                
                except Exception as e:
                    error_messages.append(f'第 {row_index + 1} 行处理失败: {str(e)}')
            
            # 提交数据库事务
            if success_count > 0:
                db.session.commit()
                flash(f'批量入库成功！共处理 {success_count} 条记录', 'success')
            
            if error_messages:
                flash(f'部分记录处理失败：\n' + '\n'.join(error_messages), 'warning')
            
            if success_count == 0 and not error_messages:
                flash('没有有效的入库数据', 'warning')
            
            return redirect(url_for('main.inventory_inbound'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'批量入库失败: {str(e)}', 'danger')
    
    return render_template('main/inventory_inbound.html', form=form)


@bp.route('/inventory/raw-material/inbound', methods=['GET', 'POST'])
@login_required
@require_capability('inventory.manage')
def raw_material_inbound():
    """原材料批量入库管理"""
    from app.main.forms import RawMaterialInboundForm
    from app.models import RawMaterial, SerialNumber, AuditLog
    
    form = RawMaterialInboundForm()
    
    if request.method == 'POST':
        try:
            # 获取所有表单数据
            form_data = request.form.to_dict()
            
            # 解析批量数据
            rows_data = {}
            for key, value in form_data.items():
                if '_' in key and key != 'csrf_token':
                    field_name, row_index = key.rsplit('_', 1)
                    if row_index.isdigit():
                        row_index = int(row_index)
                        if row_index not in rows_data:
                            rows_data[row_index] = {}
                        rows_data[row_index][field_name] = value
            
            success_count = 0
            error_messages = []
            
            # 处理每一行数据
            for row_index, row_data in rows_data.items():
                try:
                    supplier = row_data.get('supplier', '').strip()
                    material_name = row_data.get('material_name', '').strip()
                    supplier_number = row_data.get('supplier_number', '').strip()
                    
                    if not supplier or not material_name or not supplier_number:
                        error_messages.append(f'第 {row_index + 1} 行：供应商、品名、供应商编号不能为空')
                        continue
                    
                    quantity = float(row_data.get('quantity', 0))
                    if quantity <= 0:
                        error_messages.append(f'第 {row_index + 1} 行：数量无效')
                        continue
                    
                    storage_date_str = row_data.get('storage_date', '')
                    if not storage_date_str:
                        error_messages.append(f'第 {row_index + 1} 行：入库日期不能为空')
                        continue
                    
                    try:
                        from datetime import datetime
                        storage_date = datetime.strptime(storage_date_str, '%Y-%m-%d').date()
                    except ValueError:
                        error_messages.append(f'第 {row_index + 1} 行：日期格式错误')
                        continue
                    
                    melt_number = row_data.get('melt_number', '').strip()
                    internal_number = row_data.get('internal_number', '').strip()
                    notes = row_data.get('notes', '').strip()
                    has_sample = f'has_sample_{row_index}' in form_data
                    
                    # 自动生成内部编号
                    if not internal_number:
                        internal_number = SerialNumber.get_next_number()
                    
                    # 获取品类ID
                    category_id = form_data.get(f'category_id_{row_index}')
                    if category_id and category_id.strip():
                        try:
                            category_id = int(category_id)
                        except ValueError:
                            category_id = None
                    else:
                        category_id = None
                    
                    # 验证品类ID
                    if not category_id:
                        error_messages.append(f'第{row_index+1}行：请选择原材料品类')
                        continue
                    
                    # 验证品类是否存在
                    from app.models import RawMaterialCategory
                    category = RawMaterialCategory.query.get(category_id)
                    if not category or not category.is_active:
                        error_messages.append(f'第{row_index+1}行：选择的原材料品类无效')
                        continue
                    
                    raw_material = RawMaterial(
                        supplier=supplier,
                        category_id=category_id,
                        quantity=quantity,
                        storage_date=storage_date,
                        melt_number=melt_number,
                        supplier_number=supplier_number,
                        internal_number=internal_number,
                        has_sample=has_sample,
                        notes=notes,
                        status='in_stock'
                    )
                    
                    db.session.add(raw_material)
                    db.session.flush()  # 获取ID
                    
                    # 记录审计日志
                    audit_log = AuditLog(
                        user_id=current_user.id,
                        action='原材料入库',
                        details=f'入库原材料：{raw_material.material_name} ({raw_material.category_code})，数量：{raw_material.quantity}',
                        can_rollback=True,
                        rollback_type='delete',
                        target_model='RawMaterial',
                        target_id=raw_material.id,
                        new_data={
                            'supplier': raw_material.supplier,
                            'category_id': raw_material.category_id,
                            'material_name': raw_material.material_name,  # 通过品类获取
                            'quantity': float(raw_material.quantity),
                            'storage_date': raw_material.storage_date.isoformat()
                        }
                    )
                    db.session.add(audit_log)
                    success_count += 1
                
                except Exception as e:
                    error_messages.append(f'第 {row_index + 1} 行处理失败: {str(e)}')
            
            # 提交数据库事务
            if success_count > 0:
                db.session.commit()
                flash(f'原材料批量入库成功！共处理 {success_count} 条记录', 'success')
            
            if error_messages:
                flash(f'部分记录处理失败：\n' + '\n'.join(error_messages), 'warning')
            
            if success_count == 0 and not error_messages:
                flash('没有有效的入库数据', 'warning')
            
            return redirect(url_for('main.raw_material_inbound'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'原材料批量入库失败: {str(e)}', 'danger')
    
    return render_template('main/raw_material_inbound.html', form=form)


@bp.route('/inventory/finished-product/inbound', methods=['GET', 'POST'])
@login_required
@require_capability('inventory.manage')
def finished_product_inbound():
    """成品批量入库管理"""
    from app.main.forms import FinishedProductInboundForm
    from app.models import FinishedProduct, AuditLog
    
    form = FinishedProductInboundForm()
    
    if request.method == 'POST':
        try:
            # 获取所有表单数据
            form_data = request.form.to_dict()
            
            # 解析批量数据
            rows_data = {}
            for key, value in form_data.items():
                if '_' in key and key != 'csrf_token':
                    field_name, row_index = key.rsplit('_', 1)
                    if row_index.isdigit():
                        row_index = int(row_index)
                        if row_index not in rows_data:
                            rows_data[row_index] = {}
                        rows_data[row_index][field_name] = value
            
            success_count = 0
            error_messages = []
            
            # 处理每一行数据
            for row_index, row_data in rows_data.items():
                try:
                    product_number = row_data.get('product_number', '').strip()
                    drawing_number = row_data.get('drawing_number', '').strip()
                    model = row_data.get('model', '').strip()
                    inspector = row_data.get('inspector', '').strip()
                    production_date_str = row_data.get('production_date', '')
                    
                    if not product_number or not drawing_number or not model or not inspector or not production_date_str:
                        error_messages.append(f'第 {row_index + 1} 行：产品编号、图号、型号、检验员、生产日期不能为空')
                        continue
                    
                    quantity = int(row_data.get('quantity', 0))
                    if quantity <= 0:
                        error_messages.append(f'第 {row_index + 1} 行：数量无效')
                        continue
                    
                    storage_date_str = row_data.get('storage_date', '')
                    if not storage_date_str:
                        error_messages.append(f'第 {row_index + 1} 行：入库日期不能为空')
                        continue
                    
                    try:
                        from datetime import datetime
                        storage_date = datetime.strptime(storage_date_str, '%Y-%m-%d').date()
                        production_date = datetime.strptime(production_date_str, '%Y-%m-%d').date()
                    except ValueError:
                        error_messages.append(f'第 {row_index + 1} 行：日期格式错误')
                        continue
                    
                    notes = row_data.get('notes', '').strip()
                    
                    # FinishedProduct 没有 storage_date 列：入库日期由 created_at 承担
                    # （与 search_service 对成品 storage_date 的过滤口径一致）
                    finished_product = FinishedProduct(
                        product_number=product_number,
                        drawing_number=drawing_number,
                        model=model,
                        quantity=quantity,
                        created_at=datetime.combine(storage_date, datetime.min.time()),
                        inspector=inspector,
                        production_date=production_date,
                        notes=notes,
                        status='in_stock'
                    )
                    
                    db.session.add(finished_product)
                    db.session.flush()  # 获取ID
                    
                    # 记录审计日志
                    audit_log = AuditLog(
                        user_id=current_user.id,
                        action='成品入库',
                        details=f'入库成品：{finished_product.product_number}，数量：{finished_product.quantity}',
                        can_rollback=True,
                        rollback_type='delete',
                        target_model='FinishedProduct',
                        target_id=finished_product.id,
                        new_data={
                            'product_number': finished_product.product_number,
                            'drawing_number': finished_product.drawing_number,
                            'model': finished_product.model,
                            'quantity': finished_product.quantity,
                            'production_date': finished_product.production_date.isoformat()
                        }
                    )
                    db.session.add(audit_log)
                    success_count += 1
                
                except Exception as e:
                    error_messages.append(f'第 {row_index + 1} 行处理失败: {str(e)}')
            
            # 提交数据库事务
            if success_count > 0:
                db.session.commit()
                flash(f'成品批量入库成功！共处理 {success_count} 条记录', 'success')
            
            if error_messages:
                flash(f'部分记录处理失败：\n' + '\n'.join(error_messages), 'warning')
            
            if success_count == 0 and not error_messages:
                flash('没有有效的入库数据', 'warning')
            
            return redirect(url_for('main.finished_product_inbound'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'成品批量入库失败: {str(e)}', 'danger')
    
    return render_template('main/finished_product_inbound.html', form=form)


@bp.route('/inventory/raw-material/categories')
@login_required
@require_capability('inventory.manage')
def raw_material_categories():
    """原材料品类管理"""
    from app.models import RawMaterialCategory
    from app.main.forms import RawMaterialCategoryForm
    
    categories = RawMaterialCategory.query.order_by(RawMaterialCategory.created_at.desc()).all()
    form = RawMaterialCategoryForm()
    
    return render_template('main/raw_material_categories.html', categories=categories, form=form)


@bp.route('/inventory/raw-material/categories/add', methods=['POST'])
@login_required
@require_capability('inventory.manage')
def add_raw_material_category():
    """添加原材料品类"""
    from app.models import RawMaterialCategory, AuditLog
    from app.main.forms import RawMaterialCategoryForm
    
    
    try:
        data = request.json if request.is_json else request.form.to_dict()
        
        # 验证必填字段
        if not data.get('name') or not data.get('code'):
            return jsonify({'success': False, 'message': '品类名称和编码不能为空'})
        
        # 检查名称和编码是否已存在
        existing_name = RawMaterialCategory.query.filter_by(name=data['name']).first()
        if existing_name:
            return jsonify({'success': False, 'message': '品类名称已存在'})
        
        existing_code = RawMaterialCategory.query.filter_by(code=data['code']).first()
        if existing_code:
            return jsonify({'success': False, 'message': '品类编码已存在'})
        
        # 创建新品类
        category = RawMaterialCategory(
            name=data['name'].strip(),
            code=data['code'].strip(),
            description=data.get('description', '').strip(),
            is_active=_parse_flag(data, 'is_active', True),
            requires_approval=_parse_flag(data, 'requires_approval', True),
            created_by=current_user.id
        )
        
        db.session.add(category)
        db.session.flush()  # 获取ID
        
        # 记录审计日志
        audit_log = AuditLog(
            user_id=current_user.id,
            action='添加原材料品类',
            details=f'添加原材料品类：{category.name} ({category.code})',
            can_rollback=True,
            rollback_type='delete',
            target_model='RawMaterialCategory',
            target_id=category.id,
            new_data=category.to_dict()
        )
        db.session.add(audit_log)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': '品类添加成功',
            'data': category.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'添加失败：{str(e)}'})


@bp.route('/inventory/raw-material/categories/<int:category_id>', methods=['GET'])
@login_required
@require_capability('inventory.manage')
def get_raw_material_category(category_id):
    """获取原材料品类详情"""
    from app.models import RawMaterialCategory
    
    try:
        category = RawMaterialCategory.query.get_or_404(category_id)
        return jsonify({
            'success': True,
            'data': category.to_dict()
        })
    except Exception as e:
        _reraise_http(e)
        return jsonify({'success': False, 'message': f'获取品类详情失败：{str(e)}'})


@bp.route('/inventory/raw-material/categories/<int:category_id>', methods=['PUT'])
@login_required
@require_capability('inventory.manage')
def update_raw_material_category(category_id):
    """更新原材料品类"""
    from app.models import RawMaterialCategory, AuditLog
    
    
    try:
        category = RawMaterialCategory.query.get_or_404(category_id)
        data = request.json
        
        if not data:
            return jsonify({'success': False, 'message': '请求数据为空'})
        
        # 保存旧数据
        old_data = category.to_dict()
        
        # 检查名称和编码是否已被其他品类使用
        if data.get('name') and data['name'] != category.name:
            existing_name = RawMaterialCategory.query.filter(
                RawMaterialCategory.name == data['name'],
                RawMaterialCategory.id != category_id
            ).first()
            if existing_name:
                return jsonify({'success': False, 'message': '品类名称已存在'})
        
        if data.get('code') and data['code'] != category.code:
            existing_code = RawMaterialCategory.query.filter(
                RawMaterialCategory.code == data['code'],
                RawMaterialCategory.id != category_id
            ).first()
            if existing_code:
                return jsonify({'success': False, 'message': '品类编码已存在'})
        
        # 更新数据
        category.name = data.get('name', category.name).strip()
        category.code = data.get('code', category.code).strip()
        category.description = data.get('description', category.description).strip()
        category.is_active = data.get('is_active', category.is_active)
        if 'requires_approval' in data:
            category.requires_approval = _parse_flag(data, 'requires_approval', True)
        category.updated_at = datetime.utcnow()
        
        # 记录审计日志
        audit_log = AuditLog(
            user_id=current_user.id,
            action='更新原材料品类',
            details=f'更新原材料品类：{category.name} ({category.code})',
            can_rollback=True,
            rollback_type='edit',
            target_model='RawMaterialCategory',
            target_id=category.id,
            old_data=old_data,
            new_data=category.to_dict()
        )
        db.session.add(audit_log)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': '品类更新成功',
            'data': category.to_dict()
        })
        
    except Exception as e:
        _reraise_http(e)
        db.session.rollback()
        return jsonify({'success': False, 'message': f'更新失败：{str(e)}'})


@bp.route('/inventory/raw-material/categories/<int:category_id>', methods=['DELETE'])
@login_required
@require_capability('inventory.manage')
def delete_raw_material_category(category_id):
    """删除原材料品类"""
    from app.models import RawMaterialCategory, AuditLog
    
    
    try:
        category = RawMaterialCategory.query.get_or_404(category_id)
        
        # 检查是否有原材料使用此品类
        if category.raw_materials.count() > 0:
            return jsonify({'success': False, 'message': f'无法删除，该品类下还有 {category.raw_materials.count()} 个原材料'})
        
        # 保存数据用于审计日志
        category_data = category.to_dict()
        
        # 记录审计日志
        audit_log = AuditLog(
            user_id=current_user.id,
            action='删除原材料品类',
            details=f'删除原材料品类：{category.name} ({category.code})',
            can_rollback=True,
            rollback_type='add',
            target_model='RawMaterialCategory',
            target_id=category.id,
            old_data=category_data
        )
        db.session.add(audit_log)
        
        # 删除品类
        db.session.delete(category)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': '品类删除成功'
        })
        
    except Exception as e:
        _reraise_http(e)
        db.session.rollback()
        return jsonify({'success': False, 'message': f'删除失败：{str(e)}'})


@bp.route('/api/raw-material-categories', methods=['GET'])
@login_required
@require_capability('inventory.view')
def get_raw_material_categories_api():
    """获取原材料品类列表API"""
    from app.models import RawMaterialCategory
    
    try:
        categories = RawMaterialCategory.query.filter_by(is_active=True).order_by(RawMaterialCategory.name).all()
        
        result = []
        for category in categories:
            result.append({
                'id': category.id,
                'name': category.name,
                'code': category.code,
                'description': category.description
            })
        
        return jsonify({
            'success': True,
            'data': result
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'获取品类列表失败：{str(e)}'})
# 产品管理路由
@bp.route('/products')
@login_required
@require_capability('product.view')
@handle_pagination_args
def manage_products():
    """产品管理页面"""
    search = request.args.get('search', '')
    status_filter = request.args.get('status', '')
    category_filter = request.args.get('category', '')
    
    query = Product.query
    
    # 搜索过滤
    if search:
        query = query.filter(
            db.or_(
                Product.product_code.contains(search),
                Product.product_name.contains(search),
                Product.drawing_number.contains(search),
                Product.model.contains(search)
            )
        )
    
    # 状态过滤
    if status_filter:
        query = query.filter(Product.status == status_filter)
    
    # 类别过滤
    if category_filter:
        query = query.filter(Product.category == category_filter)
    
    # 分页（统一走 @handle_pagination_args 的白名单口径，不再读 ITEMS_PER_PAGE）
    page = request.validated_page
    per_page = request.validated_per_page
    
    products = query.order_by(Product.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    # 获取所有类别用于过滤
    categories = db.session.query(Product.category).distinct().filter(Product.category.isnot(None)).all()
    categories = [cat[0] for cat in categories if cat[0]]
    
    return render_template('main/products.html', 
                         products=products.items,
                         pagination=products,
                         categories=categories)

@bp.route('/products/add', methods=['POST'])
@login_required
@require_capability('product.manage')
def add_product():
    """添加产品"""
    try:
        # 检查请求内容类型
        if not request.is_json:
            return jsonify({'success': False, 'message': '请求必须是JSON格式'}), 400
            
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': '请求数据为空'}), 400
        
        # 验证必填字段
        required_fields = ['product_code', 'product_name']
        for field in required_fields:
            if not data.get(field) or not str(data.get(field)).strip():
                return jsonify({'success': False, 'message': f'{field} 是必填字段'}), 400
        
        # 检查产品编码是否已存在
        existing = Product.query.filter_by(product_code=data['product_code'].strip()).first()
        if existing:
            return jsonify({'success': False, 'message': '产品编码已存在'}), 400
        
        # 创建产品
        product = Product(
            global_sn=SerialNumber.get_next_number(),  # 明确设置全局流水号
            product_code=data['product_code'].strip(),
            product_name=data['product_name'].strip(),
            drawing_number=data.get('drawing_number', '').strip(),
            model=data.get('model', '').strip(),
            specification=data.get('specification', '').strip(),
            unit=data.get('unit', '件').strip(),
            category=data.get('category', '').strip(),
            version=data.get('version', '1.0').strip(),
            notes=data.get('notes', '').strip(),
            code_rule_id=data.get('code_rule_id') if data.get('code_rule_id') else None,
            created_by=current_user.id,
            sellable_as_part=bool(data.get('sellable_as_part')),
        )
        
        # 添加到数据库
        db.session.add(product)
        
        # 记录审计日志
        log = AuditLog(
            user_id=current_user.id,
            action='添加产品',
            details=f'添加产品：{product.product_name}（编码：{product.product_code}）',
            can_rollback=True,
            rollback_type='add',
            target_model='Product',
            target_id=product.id,
            new_data={
                'product_code': product.product_code,
                'product_name': product.product_name,
                'drawing_number': product.drawing_number,
                'model': product.model,
                'specification': product.specification,
                'unit': product.unit,
                'category': product.category,
                'version': product.version,
                'notes': product.notes
            }
        )
        db.session.add(log)
        
        db.session.commit()
        
        return jsonify({'success': True, 'message': '产品添加成功', 'id': product.id})
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'添加产品失败: {str(e)}')
        return jsonify({'success': False, 'message': f'添加失败: {str(e)}'}), 500

@bp.route('/products/<int:id>', methods=['GET'])
@login_required
@require_capability('product.view')
def get_product(id):
    """获取产品详情"""
    try:
        product = Product.query.get_or_404(id)
        
        return jsonify({
            'success': True,
            'data': {
                'id': product.id,
                'product_code': product.product_code,
                'product_name': product.product_name,
                'drawing_number': product.drawing_number or '',
                'model': product.model or '',
                'specification': product.specification or '',
                'unit': product.unit,
                'category': product.category or '',
                'version': product.version,
                'status': product.status,
                'notes': product.notes or '',
                'code_rule_id': product.code_rule_id,
                'sellable_as_part': bool(product.sellable_as_part),
                'total_material_cost': product.total_material_cost,
                'total_process_cost': product.total_process_cost,
                'total_cost': product.total_cost
            }
        })
        
    except Exception as e:
        _reraise_http(e)
        return jsonify({'success': False, 'message': f'获取产品详情失败: {str(e)}'})

@bp.route('/products/<int:id>', methods=['PUT'])
@login_required
@require_capability('product.manage')
def update_product(id):
    """更新产品"""
    try:
        product = Product.query.get_or_404(id)
        data = request.get_json()
        
        # 验证必填字段
        required_fields = ['product_name']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'message': f'{field} 是必填字段'})
        
        # 更新产品信息
        product.product_name = data['product_name']
        product.drawing_number = data.get('drawing_number', '')
        product.model = data.get('model', '')
        product.specification = data.get('specification', '')
        product.unit = data.get('unit', '件')
        product.category = data.get('category', '')
        product.version = data.get('version', '1.0')
        product.status = data.get('status', 'active')
        product.notes = data.get('notes', '')
        product.code_rule_id = data.get('code_rule_id') if data.get('code_rule_id') else None
        product.sellable_as_part = bool(data.get('sellable_as_part'))
        product.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({'success': True, 'message': '产品更新成功'})
        
    except Exception as e:
        _reraise_http(e)
        db.session.rollback()
        return jsonify({'success': False, 'message': f'更新失败: {str(e)}'})

@bp.route('/products/<int:id>', methods=['DELETE'])
@login_required
@require_capability('product.manage')
@csrf.exempt
def delete_product(id):
    """删除产品"""
    try:
        product = Product.query.get_or_404(id)
        
        # 检查是否有关联的BOM或工序
        if product.bom_items.count() > 0 or product.process_items.count() > 0:
            return jsonify({'success': False, 'message': '该产品存在BOM或工序信息，无法删除'})

        # 检查是否被生产订单引用（避免将 product_id 置空导致外键/非空约束错误）
        linked_orders = ProductionOrder.query.filter_by(product_id=id).count()
        if linked_orders > 0:
            return jsonify({'success': False, 'message': '该产品已被生产订单引用，无法删除。请先处理关联的生产订单'}), 400
        
        db.session.delete(product)
        db.session.commit()
        
        return jsonify({'success': True, 'message': '产品删除成功'})
        
    except Exception as e:
        _reraise_http(e)
        db.session.rollback()
        return jsonify({'success': False, 'message': f'删除失败: {str(e)}'})

@bp.route('/products/<int:id>/bom')
@login_required
@require_capability('product.view')
def product_bom(id):
    """产品BOM管理页面"""
    product = Product.query.get_or_404(id)
    
    # 获取BOM列表
    bom_items = ProductBOM.query.filter_by(product_id=id).order_by(ProductBOM.sequence).all()
    
    # 获取可用的原材料和成品
    raw_materials = RawMaterial.query.filter_by(status='in_stock').all()
    finished_products = FinishedProduct.query.filter_by(status='in_stock').all()
    
    return render_template('main/product_bom.html',
                         product=product,
                         bom_items=bom_items,
                         raw_materials=raw_materials,
                         finished_products=finished_products)

@bp.route('/products/<int:product_id>/bom/add', methods=['POST'])
@login_required
@require_capability('product.manage')
def add_product_bom(product_id):
    """批量添加产品BOM项"""
    try:
        product = Product.query.get_or_404(product_id)
        data = request.get_json()
        
        # 支持单个添加（向后兼容）
        if 'material_type' in data:
            bom_items = [data]
        else:
            # 批量添加
            bom_items = data.get('bom_items', [])
        
        if not bom_items:
            return jsonify({'success': False, 'message': '没有BOM数据'})
        
        # 验证所有BOM数据
        errors = []
        material_keys = []  # 用于检查重复的物料
        
        for i, bom_data in enumerate(bom_items):
            row_num = i + 1
        
        # 验证必填字段
            if not bom_data.get('material_type'):
                errors.append(f'第{row_num}行：物料类型是必填字段')
                continue
                
            if not bom_data.get('material_id'):
                errors.append(f'第{row_num}行：物料是必填字段')
                continue
                
            if not bom_data.get('quantity'):
                errors.append(f'第{row_num}行：用量是必填字段')
                continue
        
        # 检查产品类型时避免循环引用
            if bom_data['material_type'] == 'product' and int(bom_data['material_id']) == product_id:
                errors.append(f'第{row_num}行：不能将产品自身添加到BOM中')
                continue
            
            # 生成物料唯一键
            material_key = (bom_data['material_type'], int(bom_data['material_id']))
            
            # 检查在提交数据中是否重复
            if material_key in material_keys:
                errors.append(f'第{row_num}行：物料在本次提交中重复')
            else:
                material_keys.append(material_key)
        
            # 检查是否与数据库中已存在的物料冲突
        existing = ProductBOM.query.filter_by(
            product_id=product_id,
                material_type=bom_data['material_type'],
                material_id=bom_data['material_id']
        ).first()
        
        if existing:
                errors.append(f'第{row_num}行：该物料已存在于BOM中')
        
        if errors:
            return jsonify({'success': False, 'message': '数据验证失败:\n' + '\n'.join(errors)})
        
        # 获取当前最大序号
        max_sequence = db.session.query(db.func.max(ProductBOM.sequence)).filter_by(product_id=product_id).scalar() or 0
        
        # 批量创建BOM项
        created_count = 0
        for bom_data in bom_items:
            bom_item = ProductBOM(
                product_id=product_id,
                material_type=bom_data['material_type'],
                material_id=int(bom_data['material_id']),
                quantity=float(bom_data['quantity']),
                unit=bom_data.get('unit', '件'),
                unit_cost=float(bom_data.get('unit_cost', 0)),
                waste_rate=float(bom_data.get('waste_rate', 0)),
                notes=bom_data.get('notes', ''),
                sequence=max_sequence + created_count + 1
            )
            
            db.session.add(bom_item)
            created_count += 1
        
        db.session.commit()
        
        # 记录审计日志
        audit_log = AuditLog(
            user_id=current_user.id,
            action='批量添加产品BOM',
            details=f'为产品{product.product_name}批量添加{created_count}个BOM项'
        )
        db.session.add(audit_log)
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': f'成功添加{created_count}个BOM项',
            'created_count': created_count
        })
        
    except Exception as e:
        _reraise_http(e)
        db.session.rollback()
        return jsonify({'success': False, 'message': f'添加失败: {str(e)}'})

@bp.route('/products/<int:product_id>/bom/<int:bom_item_id>', methods=['GET'])
@login_required
@require_capability('product.view')
def get_product_bom_item(product_id, bom_item_id):
    """获取BOM项详情"""
    try:
        bom_item = ProductBOM.query.filter_by(
            id=bom_item_id, 
            product_id=product_id
        ).first_or_404()
        
        return jsonify({
            'success': True,
            'data': {
                'id': bom_item.id,
                'material_type': bom_item.material_type,
                'material_id': bom_item.material_id,
                'quantity': bom_item.quantity,
                'unit': bom_item.unit,
                'unit_cost': bom_item.unit_cost,
                'waste_rate': bom_item.waste_rate,
                'notes': bom_item.notes or '',
                'material_name': bom_item.material_name
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'获取BOM项详情失败: {str(e)}'})

@bp.route('/products/<int:product_id>/bom/<int:bom_item_id>', methods=['PUT'])
@login_required
@require_capability('product.manage')
def update_product_bom_item(product_id, bom_item_id):
    """更新BOM项"""
    try:
        bom_item = ProductBOM.query.filter_by(
            id=bom_item_id, 
            product_id=product_id
        ).first_or_404()
        
        data = request.get_json()
        
        # 验证必填字段
        required_fields = ['quantity']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'message': f'{field} 是必填字段'})
        
        # 更新BOM项
        bom_item.quantity = float(data['quantity'])
        bom_item.unit = data.get('unit', '件')
        bom_item.unit_cost = float(data.get('unit_cost', 0))
        bom_item.waste_rate = float(data.get('waste_rate', 0))
        bom_item.notes = data.get('notes', '')
        
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'BOM项更新成功'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'更新失败: {str(e)}'})

@bp.route('/products/<int:product_id>/bom/<int:bom_item_id>', methods=['DELETE'])
@login_required
@require_capability('product.manage')
@csrf.exempt
def delete_product_bom_item(product_id, bom_item_id):
    """删除BOM项"""
    try:
        bom_item = ProductBOM.query.filter_by(
            id=bom_item_id, 
            product_id=product_id
        ).first_or_404()
        
        db.session.delete(bom_item)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'BOM项删除成功'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'删除失败: {str(e)}'})

@bp.route('/products/<int:product_id>/processes')
@login_required
@require_capability('product.view')
def product_processes(product_id):
    """产品工序管理页面"""
    product = Product.query.get_or_404(product_id)
    
    # 获取工序列表
    process_items = ProductProcess.query.filter_by(product_id=product_id).order_by(ProductProcess.sequence).all()
    
    # 获取可用的工序
    processes = ProcessPrice.query.filter_by(is_current=True).all()
    work_centers = WorkCenter.query.filter_by(is_active=True).order_by(WorkCenter.code).all()
    
    return render_template('main/product_processes.html',
                         product=product,
                         process_items=process_items,
                         processes=processes,
                         work_centers=work_centers)

@bp.route('/products/<int:product_id>/processes/add', methods=['POST'])
@login_required
@require_capability('product.manage')
def add_product_process(product_id):
    """批量添加产品工序"""
    try:
        product = Product.query.get_or_404(product_id)
        data = request.get_json()
        
        # 支持单个添加（向后兼容）
        if 'process_id' in data:
            processes = [data]
        else:
            # 批量添加
            processes = data.get('processes', [])
        
        if not processes:
            return jsonify({'success': False, 'message': '没有工序数据'})
        
        # 验证所有工序数据
        errors = []
        sequence_list = []
        
        for i, process_data in enumerate(processes):
            row_num = i + 1
        
        # 验证必填字段
            if not process_data.get('process_id'):
                errors.append(f'第{row_num}行：工序是必填字段')
                continue
                
            if not process_data.get('sequence'):
                errors.append(f'第{row_num}行：序号是必填字段')
                continue
            
            sequence = int(process_data['sequence'])
            
            # 检查序号重复（在提交的数据中）
            if sequence in sequence_list:
                errors.append(f'第{row_num}行：序号{sequence}重复')
            else:
                sequence_list.append(sequence)
        
            # 检查序号是否与数据库中已存在的冲突
        existing = ProductProcess.query.filter_by(
            product_id=product_id,
                sequence=sequence
        ).first()
        
        if existing:
                errors.append(f'第{row_num}行：序号{sequence}已存在')
        
        if errors:
            return jsonify({'success': False, 'message': '数据验证失败:\n' + '\n'.join(errors)})
        
        # 批量创建工序项
        created_count = 0
        for process_data in processes:
            process_item = ProductProcess(
                product_id=product_id,
                process_id=int(process_data['process_id']),
                sequence=int(process_data['sequence']),
                quantity=int(process_data.get('quantity', 1)),
                unit_price=float(process_data['unit_price']) if process_data.get('unit_price') else None,
                setup_time=float(process_data.get('setup_time', 0)),
                process_time=float(process_data.get('process_time', 0)),
                notes=process_data.get('notes', ''),
                is_required=process_data.get('is_required', True),
                process_stage=process_data.get('process_stage') or 'machine',
                work_center_id=int(process_data['work_center_id']) if process_data.get('work_center_id') else None,
            )
            
            db.session.add(process_item)
            created_count += 1
        
        db.session.commit()
        
        # 记录审计日志
        audit_log = AuditLog(
            user_id=current_user.id,
            action='批量添加产品工序',
            details=f'为产品{product.product_name}批量添加{created_count}个工序'
        )
        db.session.add(audit_log)
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': f'成功添加{created_count}个工序',
            'created_count': created_count
        })
        
    except Exception as e:
        _reraise_http(e)
        db.session.rollback()
        return jsonify({'success': False, 'message': f'添加失败: {str(e)}'})

@bp.route('/products/<int:product_id>/processes/<int:process_item_id>', methods=['DELETE'])
@login_required
@require_capability('product.manage')
@csrf.exempt
def delete_product_process(product_id, process_item_id):
    """删除产品工序"""
    try:
        process_item = ProductProcess.query.filter_by(
            id=process_item_id, 
            product_id=product_id
        ).first_or_404()
        
        db.session.delete(process_item)
        db.session.commit()
        
        return jsonify({'success': True, 'message': '工序删除成功'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'删除失败: {str(e)}'})

@bp.route('/products/<int:product_id>/processes/<int:process_item_id>', methods=['PUT'])
@login_required
@require_capability('product.manage')
def update_product_process(product_id, process_item_id):
    """更新产品工序"""
    try:
        process_item = ProductProcess.query.filter_by(
            id=process_item_id, 
            product_id=product_id
        ).first_or_404()
        
        data = request.get_json()
        
        # 验证必填字段
        required_fields = ['sequence']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'message': f'{field} 是必填字段'})
        
        # 检查序号是否与其他工序冲突
        existing = ProductProcess.query.filter_by(
            product_id=product_id,
            sequence=data['sequence']
        ).filter(ProductProcess.id != process_item_id).first()
        
        if existing:
            return jsonify({'success': False, 'message': '该序号已存在'})
        
        # 更新工序项
        process_item.sequence = int(data['sequence'])
        process_item.quantity = int(data.get('quantity', 1))
        process_item.unit_price = float(data['unit_price']) if data.get('unit_price') else None
        process_item.setup_time = float(data.get('setup_time', 0))
        process_item.process_time = float(data.get('process_time', 0))
        process_item.notes = data.get('notes', '')
        process_item.is_required = data.get('is_required', True)
        process_item.process_stage = data.get('process_stage') or process_item.process_stage or 'machine'
        process_item.work_center_id = int(data['work_center_id']) if data.get('work_center_id') else None
        
        db.session.commit()
        
        return jsonify({'success': True, 'message': '工序更新成功'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'更新失败: {str(e)}'})

@bp.route('/products/<int:product_id>/processes/<int:process_item_id>', methods=['GET'])
@login_required
@require_capability('product.view')
def get_product_process(product_id, process_item_id):
    """获取产品工序详情"""
    try:
        process_item = ProductProcess.query.filter_by(
            id=process_item_id, 
            product_id=product_id
        ).first_or_404()
        
        return jsonify({
            'success': True,
            'data': {
                'id': process_item.id,
                'process_id': process_item.process_id,
                'sequence': process_item.sequence,
                'quantity': process_item.quantity,
                'unit_price': process_item.unit_price,
                'setup_time': process_item.setup_time,
                'process_time': process_item.process_time,
                'notes': process_item.notes or '',
                'is_required': process_item.is_required,
                'process_stage': process_item.process_stage or 'machine',
                'work_center_id': process_item.work_center_id,
                'process_name': process_item.process.process_name,
                'process_code': process_item.process.process_code,
                'default_price': process_item.process.price
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'获取工序详情失败: {str(e)}'})

# ================== 产品Excel导入导出功能 ==================

@bp.route('/products/template')
@login_required
@require_capability('product.import')
def download_product_template():
    """下载产品导入模板"""
    
    temp_path = None
    try:
        wb = ExcelGenerator.create_product_template()
        filename = 'product_template.xlsx'
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        
        # 确保文件写入完成
        time.sleep(0.1)
        
        return send_file(
            buf,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        flash(f'下载模板失败：{str(e)}', 'danger')
        return redirect(url_for('main.manage_products'))
    finally:
        # 确保在请求结束后删除临时文件
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
@bp.route('/products/import', methods=['POST'])
@login_required
@require_capability('product.import')
def import_products():
    """批量导入产品（含BOM和工序）"""
    try:
        
        form = ProductImportForm()
        if not form.validate_on_submit():
            return jsonify({'success': False, 'message': '表单验证失败'})
        
        file = form.file.data
        if not file or not allowed_file(file.filename):
            return jsonify({'success': False, 'message': '请选择有效的Excel文件（.xlsx或.xls）'})
        
        # 保存上传文件
        temp_path = save_temp_file(file)
        
        try:
            # 解析产品数据（含BOM和工序）
            import_data = ExcelGenerator.parse_product_data(temp_path)
            
            # 检查解析错误
            if import_data['errors']:
                return jsonify({
                    'success': False, 
                    'message': f'Excel解析失败，发现 {len(import_data["errors"])} 个错误',
                    'error_details': import_data['errors'][:10]  # 只返回前10个错误
                })
            
            imported_count = 0
            updated_count = 0
            bom_count = 0
            process_count = 0
            error_details = []
            
            # 记录产品编码到ID的映射，用于处理BOM中的产品类型物料
            product_code_to_id = {}
            
            # 第一阶段：导入产品
            for i, product_data in enumerate(import_data['products'], 1):
                try:
                    # 检查产品编码是否已存在
                    existing_product = Product.query.filter_by(
                        product_code=product_data['product_code']
                    ).first()
                    
                    if existing_product:
                        # 更新现有产品
                        if form.update_existing.data:
                            existing_product.product_name = product_data['product_name']
                            existing_product.drawing_number = product_data.get('drawing_number', '')
                            existing_product.model = product_data.get('model', '')
                            existing_product.specification = product_data.get('specification', '')
                            existing_product.unit = product_data.get('unit', '件')
                            existing_product.category = product_data.get('category', '')
                            existing_product.version = product_data.get('version', '1.0')
                            existing_product.status = product_data.get('status', 'active')
                            existing_product.code_rule_id = product_data.get('code_rule_id')
                            existing_product.notes = product_data.get('notes', '')
                            existing_product.updated_at = datetime.utcnow()
                            
                            # 如果更新现有产品，先清除其BOM和工序
                            ProductBOM.query.filter_by(product_id=existing_product.id).delete()
                            ProductProcess.query.filter_by(product_id=existing_product.id).delete()
                            
                            product_code_to_id[existing_product.product_code] = existing_product.id
                            
                            # 记录审计日志
                            log = AuditLog(
                                user_id=current_user.id,
                                action='批量更新产品',
                                details=f'更新产品：{existing_product.product_name}（编码：{existing_product.product_code}）',
                                can_rollback=True,
                                rollback_type='update',
                                target_model='Product',
                                target_id=existing_product.id,
                                new_data=product_data
                            )
                            db.session.add(log)
                            updated_count += 1
                        else:
                            error_details.append(f'产品第{i}行：产品编码 {product_data["product_code"]} 已存在')
                            continue
                    else:
                        # 创建新产品
                        new_product = Product(
                            global_sn=SerialNumber.get_next_number(),
                            product_code=product_data['product_code'],
                            product_name=product_data['product_name'],
                            drawing_number=product_data.get('drawing_number', ''),
                            model=product_data.get('model', ''),
                            specification=product_data.get('specification', ''),
                            unit=product_data.get('unit', '件'),
                            category=product_data.get('category', ''),
                            version=product_data.get('version', '1.0'),
                            status=product_data.get('status', 'active'),
                            code_rule_id=product_data.get('code_rule_id'),
                            notes=product_data.get('notes', ''),
                            created_by=current_user.id
                        )
                        
                        db.session.add(new_product)
                        db.session.flush()  # 获取产品ID
                        
                        product_code_to_id[new_product.product_code] = new_product.id
                        
                        # 记录审计日志
                        log = AuditLog(
                            user_id=current_user.id,
                            action='批量添加产品',
                            details=f'添加产品：{new_product.product_name}（编码：{new_product.product_code}）',
                            can_rollback=True,
                            rollback_type='add',
                            target_model='Product',
                            new_data=product_data
                        )
                        db.session.add(log)
                        imported_count += 1
                        
                except Exception as row_error:
                    error_details.append(f'产品第{i}行处理失败：{str(row_error)}')
                    continue
            
            # 第二阶段：导入BOM
            for i, bom_data in enumerate(import_data['bom_items'], 1):
                try:
                    product_id = product_code_to_id.get(bom_data['product_code'])
                    if not product_id:
                        error_details.append(f'BOM第{i}行：找不到对应的产品 {bom_data["product_code"]}')
                        continue
                    
                    # 处理产品类型的物料ID
                    material_id = bom_data['material_id']
                    if bom_data['material_type'] == 'product':
                        # 查找产品ID
                        material_product = Product.query.filter_by(product_code=bom_data['material_code']).first()
                        if material_product:
                            material_id = material_product.id
                        else:
                            error_details.append(f'BOM第{i}行：找不到产品编码为 {bom_data["material_code"]} 的产品')
                            continue
                    
                    # 创建BOM项
                    bom_item = ProductBOM(
                        product_id=product_id,
                        material_type=bom_data['material_type'], 
                        material_id=material_id,
                        quantity=bom_data['quantity'],
                        unit=bom_data['unit'],
                        unit_cost=bom_data['unit_cost'],
                        waste_rate=bom_data['waste_rate'],
                        notes=bom_data['notes'],
                        sequence=bom_data['sequence']
                    )
                    db.session.add(bom_item)
                    bom_count += 1
                    
                except Exception as row_error:
                    error_details.append(f'BOM第{i}行处理失败：{str(row_error)}')
                    continue
            
            # 第三阶段：导入工序
            for i, process_data in enumerate(import_data['process_items'], 1):
                try:
                    product_id = product_code_to_id.get(process_data['product_code'])
                    if not product_id:
                        error_details.append(f'工序第{i}行：找不到对应的产品 {process_data["product_code"]}')
                        continue
                    
                    # 创建工序项
                    process_item = ProductProcess(
                        product_id=product_id,
                        process_id=process_data['process_id'],
                        sequence=process_data['sequence'],
                        quantity=process_data['quantity'],
                        unit_price=process_data['unit_price'],
                        setup_time=process_data['setup_time'],
                        process_time=process_data['process_time'],
                        is_required=process_data['is_required'],
                        notes=process_data['notes']
                    )
                    db.session.add(process_item)
                    process_count += 1
                    
                except Exception as row_error:
                    error_details.append(f'工序第{i}行处理失败：{str(row_error)}')
                    continue
            
            # 提交数据库变更
            db.session.commit()
            
            # 构建返回消息
            messages = []
            if imported_count > 0:
                messages.append(f'成功导入 {imported_count} 个产品')
            if updated_count > 0:
                messages.append(f'成功更新 {updated_count} 个产品')
            if bom_count > 0:
                messages.append(f'{bom_count} 个BOM项')
            if process_count > 0:
                messages.append(f'{process_count} 个工序项')
            if error_details:
                messages.append(f'失败 {len(error_details)} 条')
            
            result_data = {
                'success': True,
                'message': '；'.join(messages),
                'imported_count': imported_count,
                'updated_count': updated_count,
                'bom_count': bom_count,
                'process_count': process_count,
                'error_count': len(error_details),
                'error_details': error_details[:10]  # 只显示前10个错误
            }
            
            return jsonify(result_data)
            
        finally:
            # 清理临时文件
            cleanup_temp_files()
            
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'产品导入失败: {str(e)}')
        return jsonify({'success': False, 'message': f'导入失败: {str(e)}'})

@bp.route('/products/export', methods=['GET', 'POST'])
@login_required  
@require_capability('product.view')
def export_products():
    """导出产品数据"""
    try:
        
        form = ExportProductForm()
        
        if request.method == 'GET':
            # 渲染导出表单页面（如果需要）
            return render_template('main/export_form.html', form=form, export_type='products')
        
        if form.validate_on_submit():
            # 构建查询
            query = Product.query
            
            # 应用筛选条件
            if form.category.data:
                query = query.filter(Product.category == form.category.data)
            
            if form.status.data:
                query = query.filter(Product.status == form.status.data)
            
            if form.start_date.data:
                query = query.filter(Product.created_at >= form.start_date.data)
            
            if form.end_date.data:
                end_date = datetime.combine(form.end_date.data, datetime.max.time())
                query = query.filter(Product.created_at <= end_date)
            
            # 获取数据
            products = query.order_by(Product.created_at.desc()).all()
            
            if not products:
                return jsonify({'success': False, 'message': '没有找到符合条件的产品数据'})
            
            # 创建Excel生成器
            wb = ExcelGenerator.export_products(products)
            filename = f'产品信息导出_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
            # 写入内存：避免 Windows 上 send_file 后临时文件被占用、删不掉而持续堆积
            buf = io.BytesIO()
            wb.save(buf)
            buf.seek(0)
            
            # 记录审计日志
            log = AuditLog(
                user_id=current_user.id,
                action='导出产品数据',
                details=f'导出了 {len(products)} 条产品数据',
                can_rollback=False
            )
            db.session.add(log)
            db.session.commit()
            
            return send_file(
                buf,
                as_attachment=True,
                download_name=filename,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
        else:
            errors = []
            for field, field_errors in form.errors.items():
                errors.extend(field_errors)
            return jsonify({'success': False, 'message': '表单验证失败：' + '；'.join(errors)})
            
    except Exception as e:
        current_app.logger.error(f'产品导出失败: {str(e)}')
        return jsonify({'success': False, 'message': f'导出失败: {str(e)}'})

@bp.route('/api/products/search')
@login_required
@require_capability('product.lookup')
def search_products():
    """搜索产品"""
    try:
        search_term = request.args.get('search', '').strip()
        exclude_current = request.args.get('exclude_current', type=int)
        
        query = Product.query.filter(Product.status == 'active')
        
        if search_term:
            query = query.filter(
                db.or_(
                    Product.product_name.contains(search_term),
                    Product.product_code.contains(search_term)
                )
            )
        
        if exclude_current:
            query = query.filter(Product.id != exclude_current)
        
        products = query.limit(50).all()
        
        return jsonify({
            'success': True,
            'data': [{
                'id': product.id,
                'product_code': product.product_code,
                'product_name': product.product_name,
                'drawing_number': product.drawing_number or '',
                'model': product.model or '',
                'category': product.category or '',
                'total_cost': product.total_cost
            } for product in products]
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'搜索失败: {str(e)}'})

# 生产订单管理路由
@bp.route('/production_orders')
@login_required
@require_capability('production_order.view')
@handle_pagination_args
def manage_production_orders():
    """生产订单管理页面"""
    # 获取筛选参数
    status_filter = request.args.get('status', '')
    product_filter = request.args.get('product', '')
    
    # 构建查询
    query = ProductionOrder.query.join(Product)
    
    if status_filter:
        query = query.filter(ProductionOrder.status == status_filter)
    
    if product_filter:
        query = query.filter(
            db.or_(
                Product.product_name.contains(product_filter),
                Product.product_code.contains(product_filter)
            )
        )
    
    # 排序和分页
    query = query.order_by(ProductionOrder.created_at.desc())
    orders = query.paginate(
        page=request.validated_page,
        per_page=request.validated_per_page,
        error_out=False
    )
    
    # 获取产品列表用于筛选
    products = Product.query.filter(Product.status == 'active').all()
    
    return render_template('main/production_orders.html',
                         orders=orders,
                         products=products,
                         status_filter=status_filter,
                         product_filter=product_filter)

@bp.route('/production_orders/add', methods=['POST'])
@login_required
@require_capability('production_order.manage')
def add_production_order():
    """添加生产订单"""
    try:
        data = request.get_json()
        
        # 验证必填字段
        required_fields = ['product_id', 'planned_quantity', 'planned_start_date', 'planned_end_date']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'message': f'{field} 是必填字段'})
        
        # 验证产品存在
        product = Product.query.get(data['product_id'])
        if not product:
            return jsonify({'success': False, 'message': '产品不存在'})
        from app.services import mes_service
        if not mes_service.product_has_routing(product):
            return jsonify({'success': False, 'message': '产品未配置工艺路线，不能创建生产订单'}), 400
        
        # 创建生产订单
        order = ProductionOrder(
            product_id=data['product_id'],
            planned_quantity=int(data['planned_quantity']),
            planned_start_date=datetime.strptime(data['planned_start_date'], '%Y-%m-%d').date(),
            planned_end_date=datetime.strptime(data['planned_end_date'], '%Y-%m-%d').date(),
            priority=int(data.get('priority', 0)),
            notes=data.get('notes', ''),
            created_by=current_user.id
        )
        
        db.session.add(order)
        db.session.flush()  # 获取订单ID
        
        # 自动分配物料
        if order.allocate_materials():
            db.session.commit()
            return jsonify({'success': True, 'message': '生产订单创建成功，物料已自动分配'})
        else:
            db.session.commit()
            return jsonify({'success': True, 'message': '生产订单创建成功，但物料分配失败，请手动分配'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'创建失败: {str(e)}'})

@bp.route('/production_orders/<int:order_id>', methods=['GET'])
@login_required
@require_capability('production_order.view', 'sales_order.manage')
def production_order_detail(order_id):
    """生产订单详情页面。并上 sales_order.manage 是因为销售会从销售订单详情页链进来。"""
    order = ProductionOrder.query.get_or_404(order_id)
    
    # 获取物料分配
    material_allocations = MaterialAllocation.query.filter_by(production_order_id=order_id).all()
    
    # 获取生产批次
    batches = ProductionBatch.query.filter_by(production_order_id=order_id).order_by(ProductionBatch.created_at).all()
    
    return render_template('main/production_order_detail.html',
                         order=order,
                         material_allocations=material_allocations,
                         batches=batches)

@bp.route('/production_orders/<int:order_id>', methods=['DELETE'])
@login_required
@require_capability('production_order.manage')
@csrf.exempt
def delete_production_order(order_id):
    """删除生产订单"""
    try:
        order = ProductionOrder.query.get_or_404(order_id)
        
        
        # 检查订单状态，只能删除待开始或已取消的订单
        if order.status not in ['pending', 'cancelled']:
            return jsonify({'success': False, 'message': '只能删除待开始或已取消状态的订单'})
        
        # 检查是否有关联的生产批次
        batches = ProductionBatch.query.filter_by(production_order_id=order_id).all()
        if batches:
            return jsonify({'success': False, 'message': '该订单已有生产批次，无法删除'})
        
        # 记录审计日志
        log = AuditLog(
            user_id=current_user.id,
            action='删除生产订单',
            details=f'删除生产订单: {order.order_number} (产品: {order.product.product_name})',
            can_rollback=False,
            rollback_type='delete',
            target_model='ProductionOrder',
            target_id=order.id,
            old_data={
                'order_number': order.order_number,
                'product_id': order.product_id,
                'planned_quantity': order.planned_quantity,
                'status': order.status,
                'priority': order.priority,
                'planned_start_date': order.planned_start_date.isoformat() if order.planned_start_date else None,
                'planned_end_date': order.planned_end_date.isoformat() if order.planned_end_date else None,
                'notes': order.notes
            }
        )
        db.session.add(log)
        
        # 删除订单（级联删除会自动删除相关的物料分配）
        db.session.delete(order)
        db.session.commit()
        
        return jsonify({'success': True, 'message': f'生产订单 {order.order_number} 删除成功'})
        
    except Exception as e:
        _reraise_http(e)
        db.session.rollback()
        return jsonify({'success': False, 'message': f'删除失败: {str(e)}'})

@bp.route('/production_orders/<int:order_id>/edit', methods=['GET', 'POST'])
@login_required
@require_capability('production_order.manage')
def edit_production_order(order_id):
    """编辑生产订单"""
    order = ProductionOrder.query.get_or_404(order_id)
    
    
    form = ProductionOrderForm()
    
    # 设置产品选择项
    form.product_id.choices = [(p.id, f'{p.product_name} ({p.product_code})') 
                               for p in Product.query.filter_by(status='active').all()]
    
    if form.validate_on_submit():
        try:
            # 记录修改前的数据用于审计
            old_data = {
                'product_id': order.product_id,
                'planned_quantity': order.planned_quantity,
                'status': order.status,
                'priority': order.priority,
                'planned_start_date': order.planned_start_date.isoformat() if order.planned_start_date else None,
                'planned_end_date': order.planned_end_date.isoformat() if order.planned_end_date else None,
                'actual_start_date': order.actual_start_date.isoformat() if order.actual_start_date else None,
                'actual_end_date': order.actual_end_date.isoformat() if order.actual_end_date else None,
                'spec_extended': order.spec_extended,
                'spec_gasket': order.spec_gasket,
                'spec_joint': order.spec_joint,
                'spec_drilling': order.spec_drilling,
                'spec_other': order.spec_other,
                'spec_other_desc': order.spec_other_desc,
                'direction': order.direction,
                'notes': order.notes
            }
            
            # 更新生产订单信息
            order.product_id = form.product_id.data
            order.planned_quantity = form.planned_quantity.data
            order.status = form.status.data
            order.priority = form.priority.data
            order.planned_start_date = form.planned_start_date.data
            order.planned_end_date = form.planned_end_date.data
            order.actual_start_date = form.actual_start_date.data
            order.actual_end_date = form.actual_end_date.data
            order.spec_extended = form.spec_extended.data
            order.spec_gasket = form.spec_gasket.data
            order.spec_joint = form.spec_joint.data
            order.spec_drilling = form.spec_drilling.data
            order.spec_other = form.spec_other.data
            order.spec_other_desc = form.spec_other_desc.data
            order.direction = form.direction.data
            order.spec_splice_hole = form.spec_splice_hole.data
            order.spec_gasket_hole = form.spec_gasket_hole.data
            order.anti_corrosion = form.anti_corrosion.data
            order.rubber_gasket_material = form.rubber_gasket_material.data
            order.turnout_rail = form.turnout_rail.data
            order.using_unit = form.using_unit.data
            order.notes = form.notes.data
            
            # 记录审计日志
            new_data = {
                'product_id': order.product_id,
                'planned_quantity': order.planned_quantity,
                'status': order.status,
                'priority': order.priority,
                'planned_start_date': order.planned_start_date.isoformat() if order.planned_start_date else None,
                'planned_end_date': order.planned_end_date.isoformat() if order.planned_end_date else None,
                'actual_start_date': order.actual_start_date.isoformat() if order.actual_start_date else None,
                'actual_end_date': order.actual_end_date.isoformat() if order.actual_end_date else None,
                'spec_extended': order.spec_extended,
                'spec_gasket': order.spec_gasket,
                'spec_joint': order.spec_joint,
                'spec_drilling': order.spec_drilling,
                'spec_other': order.spec_other,
                'spec_other_desc': order.spec_other_desc,
                'direction': order.direction,
                'notes': order.notes
            }
            
            # 级联更新相关的生产批次（所有12个规格字段）
            batches = ProductionBatch.query.filter_by(production_order_id=order.id).all()
            for batch in batches:
                batch.spec_extended = order.spec_extended
                batch.spec_gasket = order.spec_gasket
                batch.spec_joint = order.spec_joint
                batch.spec_drilling = order.spec_drilling
                batch.spec_other = order.spec_other
                batch.spec_other_desc = order.spec_other_desc
                batch.direction = order.direction
                batch.spec_splice_hole = order.spec_splice_hole
                batch.spec_gasket_hole = order.spec_gasket_hole
                batch.anti_corrosion = order.anti_corrosion
                batch.rubber_gasket_material = order.rubber_gasket_material
                batch.turnout_rail = order.turnout_rail
                batch.using_unit = order.using_unit
            
            # 级联更新相关的生产任务（所有12个规格字段）
            tasks = TaskAssignment.query.filter_by(production_batch_id=ProductionBatch.id)\
                                       .join(ProductionBatch)\
                                       .filter(ProductionBatch.production_order_id == order.id)\
                                       .all()
            for task in tasks:
                task.spec_extended = order.spec_extended
                task.spec_gasket = order.spec_gasket
                task.spec_joint = order.spec_joint
                task.spec_drilling = order.spec_drilling
                task.spec_other = order.spec_other
                task.spec_other_desc = order.spec_other_desc
                task.direction = order.direction
                task.spec_splice_hole = order.spec_splice_hole
                task.spec_gasket_hole = order.spec_gasket_hole
                task.anti_corrosion = order.anti_corrosion
                task.rubber_gasket_material = order.rubber_gasket_material
                task.turnout_rail = order.turnout_rail
                task.using_unit = order.using_unit
            
            log = AuditLog(
                user_id=current_user.id,
                action='修改生产订单',
                details=f'修改生产订单: {order.order_number}，同时更新了 {len(batches)} 个生产批次和 {len(tasks)} 个任务',
                target_model='ProductionOrder',
                target_id=order.id,
                old_data=old_data,
                new_data=new_data
            )
            db.session.add(log)
            
            db.session.commit()
            flash(f'生产订单修改成功，同时更新了 {len(batches)} 个批次和 {len(tasks)} 个任务的规格型号信息', 'success')
            return redirect(url_for('main.production_order_detail', order_id=order_id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'修改失败: {str(e)}', 'error')
    
    elif request.method == 'GET':
        # 填充表单数据（所有12个规格字段）
        form.product_id.data = order.product_id
        form.planned_quantity.data = order.planned_quantity
        form.status.data = order.status
        form.priority.data = order.priority
        form.planned_start_date.data = order.planned_start_date
        form.planned_end_date.data = order.planned_end_date
        form.actual_start_date.data = order.actual_start_date
        form.actual_end_date.data = order.actual_end_date
        form.spec_extended.data = order.spec_extended
        form.spec_gasket.data = order.spec_gasket
        form.spec_joint.data = order.spec_joint
        form.spec_drilling.data = order.spec_drilling
        form.spec_other.data = order.spec_other
        form.spec_other_desc.data = order.spec_other_desc
        form.direction.data = order.direction
        form.spec_splice_hole.data = order.spec_splice_hole
        form.spec_gasket_hole.data = order.spec_gasket_hole
        form.anti_corrosion.data = order.anti_corrosion
        form.rubber_gasket_material.data = order.rubber_gasket_material
        form.turnout_rail.data = order.turnout_rail
        form.using_unit.data = order.using_unit
        form.notes.data = order.notes
    
    return render_template('main/edit_production_order.html', form=form, order=order)

@bp.route('/sales_order/<int:order_id>/create_production_order', methods=['POST'])
@login_required
@require_capability('production_order.manage')
def create_production_order_from_sales(order_id):
    """从销售订单创建生产订单"""
    try:
        
        sales_order = SalesOrder.query.get_or_404(order_id)
        data = request.get_json()
        
        # 验证必填字段
        required_fields = ['planned_start_date', 'planned_end_date']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'message': f'{field} 是必填字段'})
        
        # 获取用户选择的订单行ID（可选）
        selected_ids = data.get('selected_item_ids') or []
        # 获取销售订单的订单行，若前端有选择则按选择过滤
        base_query = SalesOrderItem.query.filter_by(sales_order_id=order_id)
        if selected_ids:
            order_items = base_query.filter(SalesOrderItem.id.in_(selected_ids)).all()
        else:
            order_items = base_query.all()
        
        if not order_items:
            return jsonify({'success': False, 'message': '请选择至少一条订单行或该销售订单没有可用的订单行'})
        
        created_orders = []
        skipped = []
        from app.services import mes_service
        
        # 为每个订单行创建生产订单（跳过已有待处理/进行中的生产订单）
        for item in order_items:
            # 检查是否已经有生产订单
            existing_order = ProductionOrder.query.filter(
                ProductionOrder.sales_order_item_id == item.id,
                ProductionOrder.status.in_(['pending', 'in_progress'])
            ).first()
            
            if existing_order:
                skipped.append(f'{item.product_name or item.id}: 已有进行中的生产订单')
                continue  # 跳过已有生产订单的订单行

            product = Product.query.get(item.product_id)
            if not mes_service.product_has_routing(product):
                skipped.append(f'{item.product_name or item.id}: 未配置工艺路线')
                continue
            
            # 创建生产订单
            production_order = ProductionOrder(
                product_id=item.product_id,
                planned_quantity=item.quantity,
                planned_start_date=datetime.strptime(data['planned_start_date'], '%Y-%m-%d').date(),
                planned_end_date=datetime.strptime(data['planned_end_date'], '%Y-%m-%d').date(),
                priority=int(data.get('priority', 0)),
                notes=data.get('notes', f'从销售订单 {sales_order.order_number} 创建'),
                created_by=current_user.id,
                sales_order_id=sales_order.id,
                sales_order_item_id=item.id,
                source_type='sales_item',
                # 继承所有规格型号信息（12个字段）
                spec_extended=item.spec_extended,
                spec_gasket=item.spec_gasket,
                spec_joint=item.spec_joint,
                spec_drilling=item.spec_drilling,
                spec_other=item.spec_other,
                spec_other_desc=item.spec_other_desc,
                direction=item.direction,
                spec_splice_hole=item.spec_splice_hole,
                spec_gasket_hole=item.spec_gasket_hole,
                anti_corrosion=item.anti_corrosion,
                rubber_gasket_material=item.rubber_gasket_material,
                turnout_rail=item.turnout_rail,
                using_unit=item.using_unit
            )
            
            db.session.add(production_order)
            db.session.flush()  # 获取订单ID
            
            # 自动分配物料
            production_order.allocate_materials()
            
            created_orders.append({
                'order_number': production_order.order_number,
                'product_name': item.product_name,
                'quantity': item.quantity
            })
        
        if not created_orders:
            msg = '没有可创建的生产订单'
            if skipped:
                msg += '（' + '；'.join(skipped) + '）'
            return jsonify({'success': False, 'message': msg}), 400
        
        # 更新销售订单状态为生产中
        if sales_order.status == 'confirmed':
            sales_order.status = 'in_production'
        
        # 记录审计日志
        log = AuditLog(
            user_id=current_user.id,
            action='从销售订单创建生产订单',
            details=f'从销售订单 {sales_order.order_number} 创建了 {len(created_orders)} 个生产订单',
            target_model='ProductionOrder',
            new_data={'created_orders': created_orders}
        )
        db.session.add(log)
        
        db.session.commit()
        
        success_msg = f'成功创建 {len(created_orders)} 个生产订单'
        if skipped:
            success_msg += '；部分行未创建：' + '；'.join(skipped)
        return jsonify({
            'success': True, 
            'message': success_msg,
            'created_orders': created_orders
        })
        
    except Exception as e:
        _reraise_http(e)
        db.session.rollback()
        return jsonify({'success': False, 'message': f'创建失败: {str(e)}'})
@bp.route('/sales_order_item/<int:item_id>/create_production_order', methods=['POST'])
@login_required
@require_capability('production_order.manage')
def create_production_order_from_item(item_id):
    """从销售订单行创建生产订单"""
    try:
        
        order_item = SalesOrderItem.query.get_or_404(item_id)
        data = request.get_json()
        
        # 验证必填字段
        required_fields = ['planned_start_date', 'planned_end_date']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'message': f'{field} 是必填字段'})
        
        # 计算该订单行已创建的生产订单总计划数量（不计已取消）
        from sqlalchemy import func
        total_planned = db.session.query(func.coalesce(func.sum(ProductionOrder.planned_quantity), 0)) \
            .filter(ProductionOrder.sales_order_item_id == item_id) \
            .filter(ProductionOrder.status != 'cancelled') \
            .scalar() or 0
        remaining_to_create = max(0, (order_item.quantity or 0) - int(total_planned))
        
        if remaining_to_create <= 0:
            return jsonify({'success': False, 'message': '该订单行已全部创建生产订单，无剩余数量可创建'})

        from app.services import mes_service
        product = Product.query.get(order_item.product_id)
        if not mes_service.product_has_routing(product):
            return jsonify({'success': False, 'message': '产品未配置工艺路线，不能创建生产订单'}), 400
        
        # 计划数量：未传则默认使用剩余数量；传入则校验不超过剩余数量
        requested_qty = data.get('planned_quantity')
        if requested_qty is None or str(requested_qty).strip() == '':
            planned_qty = int(remaining_to_create)
        else:
            try:
                planned_qty = int(requested_qty)
            except (ValueError, TypeError):
                return jsonify({'success': False, 'message': '计划数量无效'})
            if planned_qty <= 0:
                return jsonify({'success': False, 'message': '计划数量必须大于0'})
            if planned_qty > remaining_to_create:
                return jsonify({'success': False, 'message': f'计划数量不能超过剩余未创建数量({remaining_to_create})'})
        
        # 创建生产订单
        production_order = ProductionOrder(
            product_id=order_item.product_id,
            planned_quantity=planned_qty,
            planned_start_date=datetime.strptime(data['planned_start_date'], '%Y-%m-%d').date(),
            planned_end_date=datetime.strptime(data['planned_end_date'], '%Y-%m-%d').date(),
            priority=int(data.get('priority', 0)),
            notes=data.get('notes', f'从销售订单行创建 - {order_item.product_name}'),
            created_by=current_user.id,
            sales_order_id=order_item.sales_order_id,
            sales_order_item_id=item_id,
            source_type='sales_item',
            # 继承所有规格型号信息（12个字段）
            spec_extended=order_item.spec_extended,
            spec_gasket=order_item.spec_gasket,
            spec_joint=order_item.spec_joint,
            spec_drilling=order_item.spec_drilling,
            spec_other=order_item.spec_other,
            spec_other_desc=order_item.spec_other_desc,
            direction=order_item.direction,
            spec_splice_hole=order_item.spec_splice_hole,
            spec_gasket_hole=order_item.spec_gasket_hole,
            anti_corrosion=order_item.anti_corrosion,
            rubber_gasket_material=order_item.rubber_gasket_material,
            turnout_rail=order_item.turnout_rail,
            using_unit=order_item.using_unit
        )
        
        db.session.add(production_order)
        db.session.flush()  # 获取订单ID
        
        # 自动分配物料
        if production_order.allocate_materials():
            material_message = "，物料已自动分配"
        else:
            material_message = "，但物料分配失败，请手动分配"
        
        # 记录审计日志
        log = AuditLog(
            user_id=current_user.id,
            action='从销售订单行创建生产订单',
            details=f'从销售订单行创建生产订单: {production_order.order_number} (产品: {order_item.product_name})',
            target_model='ProductionOrder',
            target_id=production_order.id,
            new_data={
                'order_number': production_order.order_number,
                'product_id': production_order.product_id,
                'planned_quantity': production_order.planned_quantity,
                'sales_order_item_id': item_id
            }
        )
        db.session.add(log)
        
        db.session.commit()
        
        # 计算剩余数量（创建后）
        new_total_planned = total_planned + planned_qty
        new_remaining = max(0, (order_item.quantity or 0) - int(new_total_planned))
        
        return jsonify({
            'success': True, 
            'message': f'生产订单 {production_order.order_number} 创建成功{material_message}，剩余可创建数量：{new_remaining}',
            'order_number': production_order.order_number,
            'order_id': production_order.id,
            'remaining_to_create': new_remaining
        })
        
    except Exception as e:
        _reraise_http(e)
        db.session.rollback()
        return jsonify({'success': False, 'message': f'创建失败: {str(e)}'})

def check_and_handle_material_shortage(order, batch_quantity):
    """检查该订单在本次批次下的物料缺口，返回短缺清单。

    注意：RawMaterial/FinishedProduct 都没有 current_stock 列，库存量是 quantity；
    曾把不存在的属性当列访问，AttributeError 被外层 except 吞掉 → 永远返回空清单。
    另外「自动分配物料」与「自动创建子生产订单」两个分支都未实现，这里不产生任何
    写操作（created_orders 恒为空），调用方的用户提示必须与此保持一致。
    """
    created_orders = []

    try:
        material_allocations = MaterialAllocation.query.filter_by(production_order_id=order.id).all()
    except Exception as e:
        current_app.logger.error(f"检查物料短缺时查询物料分配失败: {str(e)}")
        return {
            'shortage_info': [],
            'created_orders': created_orders,
            'has_shortage': False
        }

    planned_quantity = order.planned_quantity or 0
    if planned_quantity <= 0:
        current_app.logger.error(
            f"检查物料短缺失败：生产订单 {order.order_number} 的计划数量为 "
            f"{order.planned_quantity}，无法折算批次用量"
        )
        return {
            'shortage_info': [],
            'created_orders': created_orders,
            'has_shortage': False
        }

    shortage_info = []
    for allocation in material_allocations:
        try:
            # 计算此批次需要的物料数量
            batch_required = (allocation.required_quantity / planned_quantity) * batch_quantity

            # 检查是否有足够的已分配物料
            available_quantity = (allocation.allocated_quantity or 0) - (allocation.consumed_quantity or 0)

            if available_quantity >= batch_required:
                continue

            shortage = batch_required - available_quantity

            # 库存量只能取真实列：RawMaterial.quantity / FinishedProduct.quantity；
            # product 是需要先生产的物料，不是库存，恒按 0 处理
            material = allocation.material_info
            if allocation.material_type in ('raw', 'finished'):
                current_stock = (material.quantity or 0) if material else 0
            else:
                current_stock = 0

            shortage_info.append({
                'material_name': allocation.material_name,
                'material_type': allocation.material_type,
                'required': batch_required,
                'available': available_quantity,
                'shortage': shortage,
                'current_stock': current_stock,
                'can_fulfill': current_stock >= shortage
            })
        except Exception as e:
            # 单条分配数据异常不应吞掉整份短缺清单；只有数据库错误才需要回滚会话
            if isinstance(e, SQLAlchemyError):
                db.session.rollback()
            current_app.logger.error(
                f"检查物料短缺时处理分配记录 {allocation.id} 失败: {str(e)}"
            )
            continue

    return {
        'shortage_info': shortage_info,
        'created_orders': created_orders,
        'has_shortage': len(shortage_info) > 0
    }

@bp.route('/production_orders/<int:order_id>/batches/add', methods=['POST'])
@login_required
@require_capability('production_order.manage')
def add_production_batch(order_id):
    """添加生产批次"""
    try:
        order = ProductionOrder.query.get_or_404(order_id)
        data = request.get_json()
        
        # 验证必填字段
        if not data.get('batch_quantity'):
            return jsonify({'success': False, 'message': '批次数量是必填字段'})
        
        batch_quantity = int(data['batch_quantity'])
        
        # 检查剩余可下达数量（计划 - 已下达批次总和，不含取消）
        remaining_schedulable = order.remaining_to_schedule if hasattr(order, 'remaining_to_schedule') else order.remaining_quantity
        if batch_quantity > remaining_schedulable:
            return jsonify({'success': False, 'message': f'批次数量不能超过剩余可下达数量({remaining_schedulable})'})
        
        # 检查物料需求并处理不足情况
        material_shortage_info = check_and_handle_material_shortage(order, batch_quantity)
        
        # 创建生产批次，继承生产订单的所有规格型号信息
        batch = ProductionBatch(
            production_order_id=order_id,
            batch_quantity=batch_quantity,
            notes=data.get('notes', ''),
            # 继承生产订单的所有规格型号信息（12个字段）
            spec_extended=order.spec_extended,
            spec_gasket=order.spec_gasket,
            spec_joint=order.spec_joint,
            spec_drilling=order.spec_drilling,
            spec_other=order.spec_other,
            spec_other_desc=order.spec_other_desc,
            direction=order.direction,
            spec_splice_hole=order.spec_splice_hole,
            spec_gasket_hole=order.spec_gasket_hole,
            anti_corrosion=order.anti_corrosion,
            rubber_gasket_material=order.rubber_gasket_material,
            turnout_rail=order.turnout_rail,
            using_unit=order.using_unit
        )
        
        db.session.add(batch)
        db.session.flush()  # 获取批次ID
        
        # 生成产品编码
        if batch.generate_product_codes():
            # 自动为生产批次创建生产任务
            tasks_created = create_tasks_for_production_batch(batch)
            
            # 创建批次时不更新订单的完成数量，只有当批次实际完成时才更新
            # 如果订单状态还是待开始，且有了第一个批次，可以考虑更新为进行中
            if order.status == 'pending':
                order.status = 'in_progress'
                order.actual_start_date = datetime.now().date()
            
            db.session.commit()
            
            # 构建返回消息
            message = '生产批次创建成功，产品编码已自动生成'
            if tasks_created:
                message += '，生产任务已自动创建'
            else:
                message += '，但生产任务创建失败（可能是产品未配置工序或无可用员工）'
                
            # 系统不会自动创建子生产订单（该分支未实现，created_orders 恒为空），
            # 有缺口时只如实提示，避免出现与实际行为不符的文案
            if material_shortage_info['has_shortage']:
                shortage_names = '、'.join(
                    str(info.get('material_name') or '未知物料')
                    for info in material_shortage_info['shortage_info']
                )
                message += f'。注意：以下物料存在缺口，请人工补充（未自动创建子生产订单）：{shortage_names}'
            
            return jsonify({
                'success': True, 
                'message': message,
                'created_orders': material_shortage_info['created_orders'],
                'tasks_created': tasks_created
            })
        else:
            db.session.rollback()
            return jsonify({'success': False, 'message': '生产批次创建失败，无法生成产品编码'})
        
    except Exception as e:
        _reraise_http(e)
        db.session.rollback()
        return jsonify({'success': False, 'message': f'创建失败: {str(e)}'})

def create_tasks_for_production_batch(batch):
    """为生产批次自动创建生产任务"""
    try:
        # 获取产品的工序列表
        product = batch.production_order.product
        process_items = product.process_items.order_by(ProductProcess.sequence).all()
        
        if not process_items:
            current_app.logger.warning(f'产品 {product.product_name} 没有配置工序，无法创建生产任务')
            return False
        
        # 为每个工序创建任务（按工序分配规则选择员工）
        created_tasks = []
        for process_item in process_items:
            # 1) 查找工序分配规则
            # 为避免未迁移导致的异常，这里捕获并在异常时走兜底在职员工分配
            employee = None
            rule = None
            try:
                rule = ProcessAssignmentRule.query.filter_by(process_id=process_item.process_id, is_active=True).first()
            except Exception as e:
                if 'no such table' not in str(e).lower():
                    current_app.logger.warning(f'查询工序分配规则异常: {str(e)}')
            if rule:
                members = rule.members.filter_by(is_active=True).order_by(ProcessAssignmentMember.sequence).all()
                if members:
                    if rule.strategy == 'fixed':
                        # 固定：永远取 sequence 最小的第一个
                        employee = members[0].employee
                    elif rule.strategy == 'weighted':
                        # 权重：按权重构造池并轮询选择（简单实现）
                        pool = []
                        for m in members:
                            pool.extend([m.employee] * max(1, m.weight or 1))
                        employee = pool[len(created_tasks) % len(pool)] if pool else None
                    else:
                        # round_robin（默认）：按 sequence 轮询
                        employee = members[len(created_tasks) % len(members)].employee
            # 2) 兜底：全局在职员工轮询
            if not employee:
                available_employees = Employee.query.filter_by(is_active=True).all()
                if not available_employees:
                    current_app.logger.warning('没有可用的员工，无法创建生产任务')
                    return False
                employee = available_employees[len(created_tasks) % len(available_employees)]
            
            # 计算目标完成日期（根据工序顺序递增）
            days_offset = process_item.sequence * 2  # 每个工序间隔2天
            target_date = batch.production_order.planned_end_date + timedelta(days=days_offset)
            
            # 创建任务，并继承生产批次的所有规格型号信息
            task = TaskAssignment(
                employee_id=employee.id,
                process_id=process_item.process_id,
                quantity=batch.batch_quantity,
                target_date=target_date,
                production_batch_id=batch.id,
                task_type='auto',
                notes=f'自动创建 - 生产批次: {batch.batch_number}, 工序序号: {process_item.sequence}',
                # 继承生产批次的所有规格型号信息（12个字段）
                spec_extended=batch.spec_extended,
                spec_gasket=batch.spec_gasket,
                spec_joint=batch.spec_joint,
                spec_drilling=batch.spec_drilling,
                spec_other=batch.spec_other,
                spec_other_desc=batch.spec_other_desc,
                direction=batch.direction,
                spec_splice_hole=batch.spec_splice_hole,
                spec_gasket_hole=batch.spec_gasket_hole,
                anti_corrosion=batch.anti_corrosion,
                rubber_gasket_material=batch.rubber_gasket_material,
                turnout_rail=batch.turnout_rail,
                using_unit=batch.using_unit
            )
            
            db.session.add(task)
            created_tasks.append(task)
            from app.services import mes_service
            from app.models import TaskWorkpiece
            eq = mes_service.pick_equipment_for_process(process_item.process_id, process_item.work_center_id)
            task.work_center_id = process_item.work_center_id
            if eq:
                task.equipment_id = eq.id
            db.session.flush()
            for bi in batch.batch_items.all():
                wp = mes_service.ensure_workpiece(
                    code=bi.product_code, batch_item_id=bi.id, product_id=product.id, status='raw',
                )
                db.session.add(TaskWorkpiece(task_id=task.id, workpiece_id=wp.id))
            
            # 记录审计日志
            log = AuditLog(
                user_id=current_user.id,
                action='自动创建生产任务',
                details=f'为生产批次 {batch.batch_number} 的工序 {process_item.process.process_name} 自动创建任务，分配给员工 {employee.name}',
                can_rollback=True,
                rollback_type='add',
                target_model='TaskAssignment',
                target_id=None,  # 将在flush后更新
                new_data={
                    'employee_id': employee.id,
                    'process_id': process_item.process_id,
                    'quantity': batch.batch_quantity,
                    'target_date': target_date.isoformat(),
                    'production_batch_id': batch.id,
                    'task_type': 'auto'
                }
            )
            db.session.add(log)
        
        # 提交以获取任务ID
        db.session.flush()
        
        # 更新审计日志中的target_id
        for i, task in enumerate(created_tasks):
            logs = AuditLog.query.filter_by(
                user_id=current_user.id,
                action='自动创建生产任务',
                target_model='TaskAssignment',
                target_id=None
            ).order_by(AuditLog.id.desc()).limit(len(created_tasks)).all()
            
            if i < len(logs):
                logs[i].target_id = task.id
        
        current_app.logger.info(f'为生产批次 {batch.batch_number} 成功创建了 {len(created_tasks)} 个生产任务')
        return True
        
    except Exception as e:
        current_app.logger.error(f'为生产批次 {batch.batch_number} 创建生产任务失败: {str(e)}')
        return False 

@bp.route('/production_batches/<int:batch_id>')
@login_required
@require_capability('production_order.view', 'task.manage')
def production_batch_detail(batch_id):
    """生产批次详情页面。并上 task.manage 是因为 hr 会从任务分配页的批次链接进来。"""
    batch = ProductionBatch.query.get_or_404(batch_id)
    
    # 获取批次项目
    batch_items = ProductionBatchItem.query.filter_by(batch_id=batch_id).order_by(ProductionBatchItem.item_sequence).all()
    
    # 获取关联的生产任务
    related_tasks = TaskAssignment.query.filter_by(production_batch_id=batch_id).join(Employee).join(ProcessPrice).all()
    
    return render_template('main/production_batch_detail.html',
                         batch=batch,
                         batch_items=batch_items,
                         related_tasks=related_tasks)

@bp.route('/production_batch_items/<int:item_id>/update', methods=['PUT'])
@login_required
@require_capability('production_order.manage')
def update_batch_item(item_id):
    """更新批次项目状态"""
    try:
        item = ProductionBatchItem.query.get_or_404(item_id)
        data = request.get_json()
        
        # 更新状态
        if 'status' in data:
            item.status = data['status']
            # 如果状态更新为完成，设置完成时间
            if data['status'] == 'completed':
                item.completed_at = datetime.now()
        
        if 'production_date' in data and data['production_date']:
            item.production_date = datetime.strptime(data['production_date'], '%Y-%m-%d').date()
        
        if 'inspector' in data:
            item.inspector = data['inspector']
        
        if 'quality_status' in data:
            item.quality_status = data['quality_status']
        
        if 'notes' in data:
            item.notes = data['notes']
        
        db.session.commit()
        
        # 更新生产状态层次结构
        update_production_status_hierarchy()
        
        return jsonify({'success': True, 'message': '批次项目更新成功'})
        
    except Exception as e:
        _reraise_http(e)
        db.session.rollback()
        return jsonify({'success': False, 'message': f'更新失败: {str(e)}'})

@bp.route('/production_batches/<int:batch_id>/status', methods=['PUT'])
@login_required
@require_capability('production_order.manage')
def update_batch_status(batch_id):
    """更新生产批次状态"""
    try:
        batch = ProductionBatch.query.get_or_404(batch_id)
        data = request.get_json()
        
        new_status = data.get('status')
        if not new_status:
            return jsonify({'success': False, 'message': '状态参数缺失'})
        
        # 更新批次状态
        batch.status = new_status
        
        # 根据状态更新时间戳和批次项目状态
        if new_status == 'in_progress':
            if not batch.start_date:
                batch.start_date = datetime.now().date()
            # 将所有待生产的批次项目状态更新为进行中
            ProductionBatchItem.query.filter_by(
                batch_id=batch_id, 
                status='pending'
            ).update({
                'status': 'in_progress'
            })
            # 若尚未生成生产任务，则在开始生产时自动创建
            try:
                if batch.tasks.count() == 0:
                    created = create_tasks_for_production_batch(batch)
                    if not created:
                        current_app.logger.warning(f'批次 {batch.batch_number} 开始生产时未能自动创建任务（可能无工序或无可用员工）')
            except Exception as e:
                current_app.logger.error(f'批次 {batch.batch_number} 自动创建任务失败: {str(e)}')
        elif new_status == 'completed':
            if not batch.end_date:
                batch.end_date = datetime.now().date()
            # 更新所有批次项目为完成状态
            ProductionBatchItem.query.filter_by(batch_id=batch_id).update({
                'status': 'completed',
                'completed_at': datetime.now()
            })
        
        db.session.commit()
        
        # 更新生产状态层次结构
        update_production_status_hierarchy()
        
        status_text = {
            'in_progress': '已开始生产',
            'completed': '批次已完成',
            'cancelled': '批次已取消'
        }
        
        return jsonify({'success': True, 'message': status_text.get(new_status, '状态更新成功')})
        
    except Exception as e:
        _reraise_http(e)
        db.session.rollback()
        return jsonify({'success': False, 'message': f'状态更新失败: {str(e)}'})

def update_production_status_hierarchy():
    """更新生产状态层次结构：批次项目 -> 批次 -> 订单"""
    try:
        # 第一步：更新所有批次状态
        batches = ProductionBatch.query.all()
        for batch in batches:
            # 获取批次的所有项目
            batch_items = ProductionBatchItem.query.filter_by(batch_id=batch.id).all()
            
            if not batch_items:
                continue
                
            # 统计各状态的项目数量
            completed_count = sum(1 for item in batch_items if item.status == 'completed')
            in_progress_count = sum(1 for item in batch_items if item.status == 'in_progress')
            total_count = len(batch_items)
            
            # 确定批次状态
            old_status = batch.status
            if completed_count == total_count:
                batch.status = 'completed'
                if not batch.end_date:
                    batch.end_date = datetime.now().date()
            elif in_progress_count > 0 or completed_count > 0:
                batch.status = 'in_progress'
                if not batch.start_date:
                    batch.start_date = datetime.now().date()
            else:
                batch.status = 'pending'
            
            # 记录状态变化
            if old_status != batch.status:
                current_app.logger.info(f'批次 {batch.batch_number} 状态自动更新：{old_status} -> {batch.status}')
        
        # 第二步：更新所有订单状态和完成数量
        orders = ProductionOrder.query.all()
        for order in orders:
            # 获取订单的所有批次
            order_batches = ProductionBatch.query.filter_by(production_order_id=order.id).all()
            
            if not order_batches:
                continue
            
            # 统计各状态的批次数量
            completed_batches = [batch for batch in order_batches if batch.status == 'completed']
            in_progress_batches = [batch for batch in order_batches if batch.status in ['in_progress', 'completed']]
            total_batches = len(order_batches)
            
            # 计算完成数量（基于已完成批次的数量）
            old_completed_quantity = order.completed_quantity
            order.completed_quantity = sum(batch.batch_quantity for batch in completed_batches)
            
            # 确定订单状态
            old_status = order.status
            if len(completed_batches) == total_batches:
                order.status = 'completed'
                if not order.actual_end_date:
                    order.actual_end_date = datetime.now().date()
            elif len(in_progress_batches) > 0:
                order.status = 'in_progress'
                if not order.actual_start_date:
                    order.actual_start_date = datetime.now().date()
            else:
                order.status = 'pending'
            
            # 记录状态变化
            if old_status != order.status or old_completed_quantity != order.completed_quantity:
                current_app.logger.info(f'订单 {order.order_number} 状态自动更新：{old_status} -> {order.status}，完成数量：{old_completed_quantity} -> {order.completed_quantity}')
        
        db.session.commit()
        current_app.logger.info('生产状态层次结构更新完成')
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'更新生产状态层次结构失败: {str(e)}')
        raise e

# ==================== 客户管理 ====================

@bp.route('/customers')
@login_required
@require_capability('customer.manage')
@handle_pagination_args
def manage_customers():
    """客户管理页面"""
    
    # 构建基础查询
    query = Customer.query
    
    # 处理搜索
    search = request.args.get('search', '').strip()
    if search:
        search_term = f"%{search}%"
        query = query.filter(db.or_(
            Customer.customer_code.like(search_term),
            Customer.customer_name.like(search_term),
            Customer.contact_person.like(search_term),
            Customer.contact_phone.like(search_term),
            Customer.industry.like(search_term)
        ))
    
    # 状态筛选
    status_filter = request.args.get('status', '')
    if status_filter:
        query = query.filter(Customer.status == status_filter)
    
    # 客户类型筛选
    type_filter = request.args.get('customer_type', '')
    if type_filter:
        query = query.filter(Customer.customer_type == type_filter)
    
    # 排序
    query = query.order_by(Customer.created_at.desc())
    
    # 分页
    page = request.validated_page
    pagination = query.paginate(page=page, per_page=request.validated_per_page)
    customers = pagination.items
    
    return render_template('main/customers.html',
                         customers=customers,
                         pagination=pagination,
                         search=search,
                         status_filter=status_filter,
                         type_filter=type_filter)

@bp.route('/customer/add', methods=['GET', 'POST'])
@login_required
@require_capability('customer.manage')
def add_customer():
    """新增客户"""
    
    form = CustomerForm()
    if form.validate_on_submit():
        try:
            # 检查客户编码是否已存在
            if Customer.query.filter_by(customer_code=form.customer_code.data).first():
                flash('客户编码已存在', 'danger')
                return render_template('main/customer_form.html', form=form, title='新增客户')
            
            customer = Customer(
                customer_code=form.customer_code.data,
                customer_name=form.customer_name.data,
                customer_type=form.customer_type.data,
                contact_person=form.contact_person.data,
                contact_phone=form.contact_phone.data,
                contact_email=form.contact_email.data,
                tax_number=form.tax_number.data,
                credit_limit=form.credit_limit.data or 0,
                payment_terms=form.payment_terms.data,
                industry=form.industry.data,
                company_size=form.company_size.data,
                website=form.website.data,
                status=form.status.data,
                notes=form.notes.data,
                created_by=current_user.id
            )
            
            db.session.add(customer)
            db.session.commit()
            
            # 记录审计日志
            log = AuditLog(
                user_id=current_user.id,
                action='新增客户',
                details=f'新增客户：{customer.customer_name}（编码：{customer.customer_code}）'
            )
            db.session.add(log)
            db.session.commit()
            
            flash('客户新增成功', 'success')
            return redirect(url_for('main.customer_detail', customer_id=customer.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'新增客户失败：{str(e)}', 'danger')
    
    return render_template('main/customer_form.html', form=form, title='新增客户')

@bp.route('/customer/<int:customer_id>')
@login_required
@require_capability('customer.manage')
def customer_detail(customer_id):
    """客户详情页面"""
    customer = Customer.query.get_or_404(customer_id)
    
    # 获取客户地址
    addresses = CustomerAddress.query.filter_by(customer_id=customer_id).order_by(
        CustomerAddress.is_primary.desc(),
        CustomerAddress.created_at.desc()
    ).all()
    
    return render_template('main/customer_detail.html',
                         customer=customer,
                         addresses=addresses)

@bp.route('/customer/<int:customer_id>/edit', methods=['GET', 'POST'])
@login_required
@require_capability('customer.manage')
def edit_customer(customer_id):
    """编辑客户"""
    
    customer = Customer.query.get_or_404(customer_id)
    form = CustomerForm(obj=customer)
    
    if form.validate_on_submit():
        try:
            # 检查客户编码是否与其他客户冲突
            existing_customer = Customer.query.filter(
                Customer.customer_code == form.customer_code.data,
                Customer.id != customer_id
            ).first()
            
            if existing_customer:
                flash('客户编码已存在', 'danger')
                return render_template('main/customer_form.html', form=form, title='编辑客户', customer=customer)
            
            # 保存旧数据用于审计
            old_data = {
                'customer_code': customer.customer_code,
                'customer_name': customer.customer_name,
                'customer_type': customer.customer_type,
                'contact_person': customer.contact_person,
                'contact_phone': customer.contact_phone,
                'status': customer.status
            }
            
            # 更新客户信息
            form.populate_obj(customer)
            customer.updated_at = datetime.utcnow()
            
            db.session.commit()
            
            # 记录审计日志
            log = AuditLog(
                user_id=current_user.id,
                action='编辑客户',
                details=f'编辑客户：{customer.customer_name}（编码：{customer.customer_code}）',
                old_data=old_data
            )
            db.session.add(log)
            db.session.commit()
            
            flash('客户信息更新成功', 'success')
            return redirect(url_for('main.customer_detail', customer_id=customer.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'更新客户失败：{str(e)}', 'danger')
    
    return render_template('main/customer_form.html', form=form, title='编辑客户', customer=customer)

@bp.route('/customer/<int:customer_id>/delete', methods=['DELETE'])
@login_required
@require_capability('customer.delete')
def delete_customer(customer_id):
    """删除客户"""
    
    try:
        customer = Customer.query.get_or_404(customer_id)
        
        # 检查是否有关联的订单或其他业务数据
        # TODO: 添加订单关联检查
        
        # 保存旧数据用于回滚
        old_data = {
            'customer_code': customer.customer_code,
            'customer_name': customer.customer_name,
            'customer_type': customer.customer_type,
            'contact_person': customer.contact_person,
            'contact_phone': customer.contact_phone,
            'status': customer.status
        }
        
        # 记录可回滚的审计日志
        log = AuditLog(
            user_id=current_user.id,
            action='删除客户',
            details=f'删除客户：{customer.customer_name}（编码：{customer.customer_code}）',
            can_rollback=True,
            rollback_type='delete',
            target_model='Customer',
            target_id=customer.id,
            old_data=old_data
        )
        db.session.add(log)
        
        db.session.delete(customer)
        db.session.commit()
        
        return jsonify({'success': True, 'message': '客户删除成功'})
        
    except Exception as e:
        _reraise_http(e)
        db.session.rollback()
        return jsonify({'success': False, 'message': f'删除失败：{str(e)}'})
@bp.route('/customer/<int:customer_id>/address/add', methods=['GET', 'POST'])
@login_required
@require_capability('customer.manage')
def add_customer_address(customer_id):
    """新增客户地址"""
    
    customer = Customer.query.get_or_404(customer_id)
    form = CustomerAddressForm()
    
    if form.validate_on_submit():
        try:
            # 如果设置为主要地址，先取消其他主要地址
            if form.is_primary.data:
                CustomerAddress.query.filter_by(
                    customer_id=customer_id,
                    is_primary=True
                ).update({'is_primary': False})
            
            address = CustomerAddress(
                customer_id=customer_id,
                address_type=form.address_type.data,
                contact_person=form.contact_person.data,
                contact_phone=form.contact_phone.data,
                province=form.province.data,
                city=form.city.data,
                district=form.district.data,
                detailed_address=form.detailed_address.data,
                postal_code=form.postal_code.data,
                is_primary=form.is_primary.data,
                is_active=form.is_active.data,
                notes=form.notes.data
            )
            
            db.session.add(address)
            db.session.commit()
            
            # 记录审计日志
            log = AuditLog(
                user_id=current_user.id,
                action='新增客户地址',
                details=f'为客户 {customer.customer_name} 新增地址：{address.full_address}'
            )
            db.session.add(log)
            db.session.commit()
            
            flash('地址新增成功', 'success')
            return redirect(url_for('main.customer_detail', customer_id=customer_id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'新增地址失败：{str(e)}', 'danger')
    
    return render_template('main/customer_address_form.html', 
                         form=form, 
                         customer=customer, 
                         title='新增地址')
@bp.route('/customer/<int:customer_id>/address/<int:address_id>/edit', methods=['GET', 'POST'])
@login_required
@require_capability('customer.manage')
def edit_customer_address(customer_id, address_id):
    """编辑客户地址"""
    
    customer = Customer.query.get_or_404(customer_id)
    address = CustomerAddress.query.filter_by(
        id=address_id, 
        customer_id=customer_id
    ).first_or_404()
    
    form = CustomerAddressForm(obj=address)
    
    if form.validate_on_submit():
        try:
            # 如果设置为主要地址，先取消其他主要地址
            if form.is_primary.data and not address.is_primary:
                CustomerAddress.query.filter(
                    CustomerAddress.customer_id == customer_id,
                    CustomerAddress.id != address_id,
                    CustomerAddress.is_primary == True
                ).update({'is_primary': False})
            
            # 保存旧数据用于审计
            old_data = {
                'contact_person': address.contact_person,
                'contact_phone': address.contact_phone,
                'full_address': address.full_address,
                'is_primary': address.is_primary,
                'is_active': address.is_active
            }
            
            # 更新地址信息
            form.populate_obj(address)
            
            db.session.commit()
            
            # 记录审计日志
            log = AuditLog(
                user_id=current_user.id,
                action='编辑客户地址',
                details=f'编辑客户 {customer.customer_name} 的地址：{address.full_address}',
                old_data=old_data
            )
            db.session.add(log)
            db.session.commit()
            
            flash('地址更新成功', 'success')
            return redirect(url_for('main.customer_detail', customer_id=customer_id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'更新地址失败：{str(e)}', 'danger')
    
    return render_template('main/customer_address_form.html', 
                         form=form, 
                         customer=customer, 
                         address=address,
                         title='编辑地址')

@bp.route('/customer/<int:customer_id>/address/<int:address_id>/delete', methods=['DELETE'])
@login_required
@require_capability('customer.manage')
def delete_customer_address(customer_id, address_id):
    """删除客户地址"""
    
    try:
        customer = Customer.query.get_or_404(customer_id)
        address = CustomerAddress.query.filter_by(
            id=address_id, 
            customer_id=customer_id
        ).first_or_404()
        
        # 保存旧数据用于回滚
        old_data = {
            'customer_id': address.customer_id,
            'address_type': address.address_type,
            'contact_person': address.contact_person,
            'contact_phone': address.contact_phone,
            'full_address': address.full_address,
            'is_primary': address.is_primary,
            'is_active': address.is_active
        }
        
        # 记录可回滚的审计日志
        log = AuditLog(
            user_id=current_user.id,
            action='删除客户地址',
            details=f'删除客户 {customer.customer_name} 的地址：{address.full_address}',
            can_rollback=True,
            rollback_type='delete',
            target_model='CustomerAddress',
            target_id=address.id,
            old_data=old_data
        )
        db.session.add(log)
        
        db.session.delete(address)
        db.session.commit()
        
        return jsonify({'success': True, 'message': '地址删除成功'})
        
    except Exception as e:
        _reraise_http(e)
        db.session.rollback()
        return jsonify({'success': False, 'message': f'删除失败：{str(e)}'})

@bp.route('/customer/<int:customer_id>/address/<int:address_id>/set_primary', methods=['POST'])
@login_required
@require_capability('customer.manage')
def set_primary_address(customer_id, address_id):
    """设置主要地址"""
    
    try:
        customer = Customer.query.get_or_404(customer_id)
        address = CustomerAddress.query.filter_by(
            id=address_id, 
            customer_id=customer_id
        ).first_or_404()
        
        # 取消其他主要地址
        CustomerAddress.query.filter(
            CustomerAddress.customer_id == customer_id,
            CustomerAddress.id != address_id
        ).update({'is_primary': False})
        
        # 设置当前地址为主要地址
        address.is_primary = True
        
        db.session.commit()
        
        # 记录审计日志
        log = AuditLog(
            user_id=current_user.id,
            action='设置主要地址',
            details=f'将客户 {customer.customer_name} 的地址设为主要地址：{address.full_address}'
        )
        db.session.add(log)
        db.session.commit()
        
        return jsonify({'success': True, 'message': '主要地址设置成功'})
        
    except Exception as e:
        _reraise_http(e)
        db.session.rollback()
        return jsonify({'success': False, 'message': f'设置失败：{str(e)}'})

# ==================== 客户管理 API ====================

@bp.route('/api/customers/search')
@login_required
@require_capability('customer.manage')
def api_search_customers():
    """客户搜索API"""
    try:
        search = request.args.get('search', '').strip()
        only_active = request.args.get('only_active', 'false').lower() == 'true'
        
        query = Customer.query
        
        if only_active:
            query = query.filter(Customer.status == 'active')
        
        if search:
            search_term = f"%{search}%"
            query = query.filter(db.or_(
                Customer.customer_code.like(search_term),
                Customer.customer_name.like(search_term),
                Customer.contact_person.like(search_term)
            ))
        
        customers = query.order_by(Customer.customer_name).limit(50).all()
        
        return jsonify({
            'success': True,
            'data': [{
                'id': customer.id,
                'customer_code': customer.customer_code,
                'customer_name': customer.customer_name,
                'contact_person': customer.contact_person,
                'contact_phone': customer.contact_phone,
                'status': customer.status
            } for customer in customers]
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'搜索失败：{str(e)}'})

# 客户地址列表 API 见下方 api_get_customer_addresses（同一 URL 曾重复注册两次，
# 此处的旧实现已删除，保留支持 only_active 参数的那一个）

# ==================== 销售订单管理 ====================

@bp.route('/sales_orders')
@login_required
@require_capability('sales_order.manage')
@handle_pagination_args
def manage_sales_orders():
    """销售订单管理页面"""
    
    # 构建基础查询
    query = SalesOrder.query
    
    # 处理搜索
    search = request.args.get('search', '').strip()
    if search:
        search_term = f"%{search}%"
        query = query.join(Customer).filter(db.or_(
            SalesOrder.order_number.like(search_term),
            SalesOrder.order_source.like(search_term),
            Customer.customer_name.like(search_term),
            Customer.customer_code.like(search_term)
        ))
    
    # 状态筛选
    status_filter = request.args.get('status', '')
    if status_filter:
        query = query.filter(SalesOrder.status == status_filter)
    
    # 年月筛选
    year_month_filter = request.args.get('year_month', '')
    if year_month_filter:
        query = query.filter(SalesOrder.year_month == year_month_filter)
    
    # 客户筛选
    customer_filter = request.args.get('customer_id', '')
    if customer_filter:
        query = query.filter(SalesOrder.customer_id == customer_filter)
    
    # 排序
    query = query.order_by(SalesOrder.created_at.desc())
    
    # 分页
    page = request.validated_page
    pagination = query.paginate(page=page, per_page=request.validated_per_page)
    orders = pagination.items
    
    # 获取筛选选项
    customers = Customer.query.filter_by(status='active').order_by(Customer.customer_name).all()
    year_months = db.session.query(SalesOrder.year_month).distinct().order_by(SalesOrder.year_month.desc()).all()
    year_months = [ym[0] for ym in year_months if ym[0]]
    
    return render_template('main/sales_orders.html',
                         orders=orders,
                         pagination=pagination,
                         search=search,
                         status_filter=status_filter,
                         year_month_filter=year_month_filter,
                         customer_filter=customer_filter,
                         customers=customers,
                         year_months=year_months)

@bp.route('/sales_order/add', methods=['GET', 'POST'])
@login_required
@require_capability('sales_order.manage')
def add_sales_order():
    """新增销售订单"""
    
    form = SalesOrderForm()
    
    # 设置客户选择项
    from app.models import Customer
    form.customer_id.choices = [(c.id, f'{c.customer_name} ({c.customer_code})') 
                               for c in Customer.query.filter_by(status='active').all()]
    if form.validate_on_submit():
        try:
            # 创建销售订单
            order = SalesOrder(
                order_source=form.order_source.data,
                customer_id=form.customer_id.data,
                year_month=form.year_month.data,
                notes=form.notes.data,
                created_by=current_user.id
            )
            
            db.session.add(order)
            db.session.commit()
            
            # 记录审计日志
            log = AuditLog(
                user_id=current_user.id,
                action='新增销售订单',
                details=f'新增销售订单：{order.order_number}（客户：{order.customer.customer_name}）'
            )
            db.session.add(log)
            db.session.commit()
            
            flash('销售订单新增成功', 'success')
            return redirect(url_for('main.sales_order_detail', order_id=order.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'新增失败：{str(e)}', 'danger')
    
    return render_template('main/sales_order_form.html', form=form, title='新增销售订单')

@bp.route('/sales_order/<int:order_id>')
@login_required
@require_capability('sales_order.manage')
def sales_order_detail(order_id):
    """销售订单详情页面"""
    order = SalesOrder.query.get_or_404(order_id)
    
    # 获取订单行
    order_items = SalesOrderItem.query.filter_by(sales_order_id=order_id).order_by(
        SalesOrderItem.created_at
    ).all()
    
    # 计算总数量
    order.calculate_total_quantity()
    db.session.commit()
    
    # 将订单行转换为可序列化的字典格式，供JavaScript使用
    order_items_json = []
    for item in order_items:
        # 获取该订单行关联的生产订单
        production_orders = ProductionOrder.query.filter_by(sales_order_item_id=item.id).all()
        
        # 计算剩余可创建数量
        from sqlalchemy import func
        total_planned = db.session.query(func.coalesce(func.sum(ProductionOrder.planned_quantity), 0)) \
            .filter(ProductionOrder.sales_order_item_id == item.id) \
            .filter(ProductionOrder.status != 'cancelled') \
            .scalar() or 0
        remaining_to_create = max(0, (item.quantity or 0) - int(total_planned))
        
        order_items_json.append({
            'id': item.id,
            'product_id': item.product_id,
            'product_name': item.product_name,
            'drawing_number': item.drawing_number,
            'quantity': item.quantity,
            'direction': item.direction,
            'spec_extended': item.spec_extended,
            'spec_gasket': item.spec_gasket,
            'spec_joint': item.spec_joint,
            'spec_drilling': item.spec_drilling,
            'spec_other': item.spec_other,
            'spec_other_desc': item.spec_other_desc,
            'unit': item.unit,
            'order_time': item.order_time.isoformat() if item.order_time else None,
            'station_notes': item.station_notes,
            'sequence': item.sequence,
            'remaining_to_create': remaining_to_create,
            'production_orders': [{
                'id': po.id,
                'order_number': po.order_number,
                'status': po.status,
                'planned_quantity': po.planned_quantity,
                'completed_quantity': po.completed_quantity,
                'planned_start_date': po.planned_start_date.isoformat() if po.planned_start_date else None,
                'planned_end_date': po.planned_end_date.isoformat() if po.planned_end_date else None
            } for po in production_orders]
        })
    
    return render_template('main/sales_order_detail.html',
                         order=order,
                         order_items=order_items,
                         order_items_json=order_items_json)

@bp.route('/sales_order/<int:order_id>/edit', methods=['GET', 'POST'])
@login_required
@require_capability('sales_order.manage')
def edit_sales_order(order_id):
    """编辑销售订单"""
    
    order = SalesOrder.query.get_or_404(order_id)
    form = SalesOrderForm(obj=order)
    
    # 设置客户选择项
    from app.models import Customer
    form.customer_id.choices = [(c.id, f'{c.customer_name} ({c.customer_code})') 
                               for c in Customer.query.filter_by(status='active').all()]
    
    if form.validate_on_submit():
        try:
            # 保存旧数据用于审计
            old_data = {
                'order_source': order.order_source,
                'customer_id': order.customer_id,
                'year_month': order.year_month,
                'status': order.status
            }
            
            # 更新订单信息
            form.populate_obj(order)
            order.updated_at = datetime.utcnow()
            
            db.session.commit()
            
            # 记录审计日志
            log = AuditLog(
                user_id=current_user.id,
                action='编辑销售订单',
                details=f'编辑销售订单：{order.order_number}',
                old_data=old_data
            )
            db.session.add(log)
            db.session.commit()
            
            flash('销售订单更新成功', 'success')
            return redirect(url_for('main.sales_order_detail', order_id=order_id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'更新失败：{str(e)}', 'danger')
    
    return render_template('main/sales_order_form.html', form=form, title='编辑销售订单', order=order)

@bp.route('/sales_order/<int:order_id>/delete', methods=['DELETE'])
@login_required
@require_capability('sales_order.delete')
def delete_sales_order(order_id):
    """删除销售订单"""
    
    try:
        order = SalesOrder.query.get_or_404(order_id)
        
        # 保存旧数据用于回滚
        old_data = {
            'order_number': order.order_number,
            'order_source': order.order_source,
            'customer_id': order.customer_id,
            'year_month': order.year_month,
            'status': order.status
        }
        
        # 记录可回滚的审计日志
        log = AuditLog(
            user_id=current_user.id,
            action='删除销售订单',
            details=f'删除销售订单：{order.order_number}（客户：{order.customer.customer_name}）',
            can_rollback=True,
            rollback_type='delete',
            target_model='SalesOrder',
            target_id=order.id,
            old_data=old_data
        )
        db.session.add(log)
        
        db.session.delete(order)
        db.session.commit()
        
        return jsonify({'success': True, 'message': '销售订单删除成功'})
        
    except Exception as e:
        _reraise_http(e)
        db.session.rollback()
        return jsonify({'success': False, 'message': f'删除失败：{str(e)}'})

@bp.route('/sales_order/<int:order_id>/item/add', methods=['GET', 'POST'])
@login_required
@require_capability('sales_order.manage')
def add_sales_order_item(order_id):
    """新增销售订单行"""
    
    order = SalesOrder.query.get_or_404(order_id)
    form = SalesOrderItemForm()
    
    # 设置SelectField的选项
    form.product_name.choices = [('', '请选择产品名称')]
    form.drawing_number.choices = [('', '请选择图号')]
    form.customer_address_id.choices = [(0, '请选择收货地址')]
    
    # 在验证前，动态添加用户提交的值到choices中，避免"Not a valid choice"错误
    if request.method == 'POST':
        if form.product_name.data and form.product_name.data not in [choice[0] for choice in form.product_name.choices]:
            form.product_name.choices.append((form.product_name.data, form.product_name.data))
        if form.drawing_number.data and form.drawing_number.data not in [choice[0] for choice in form.drawing_number.choices]:
            form.drawing_number.choices.append((form.drawing_number.data, form.drawing_number.data))
        if form.customer_address_id.data and form.customer_address_id.data != 0:
            # 获取地址信息用于显示
            from app.models import CustomerAddress
            address = CustomerAddress.query.get(form.customer_address_id.data)
            if address:
                address_text = f"{address.detailed_address} ({address.contact_person})"
                form.customer_address_id.choices.append((address.id, address_text))
    
    # 若存在 copy_from，进行回填（仅 GET 阶段）
    try:
        if request.method == 'GET':
            copy_from_id = request.args.get('copy_from', type=int)
            if copy_from_id:
                src = SalesOrderItem.query.get(copy_from_id)
                if src and src.sales_order_id == order_id:
                    # 仅设置表单初值，仍需用户点击保存
                    form.quantity.data = src.quantity
                    form.direction.data = src.direction
                    form.spec_extended.data = src.spec_extended
                    form.spec_gasket.data = src.spec_gasket
                    form.spec_joint.data = src.spec_joint
                    form.spec_drilling.data = src.spec_drilling
                    form.spec_other.data = src.spec_other
                    form.spec_other_desc.data = src.spec_other_desc
                    # 新增扩展字段
                    if hasattr(form, 'spec_splice_hole'): form.spec_splice_hole.data = src.spec_splice_hole
                    if hasattr(form, 'spec_gasket_hole'): form.spec_gasket_hole.data = src.spec_gasket_hole
                    if hasattr(form, 'anti_corrosion'): form.anti_corrosion.data = src.anti_corrosion
                    if hasattr(form, 'rubber_gasket_material'): form.rubber_gasket_material.data = src.rubber_gasket_material
                    if hasattr(form, 'turnout_rail'): form.turnout_rail.data = src.turnout_rail
                    if hasattr(form, 'using_unit'): form.using_unit.data = src.using_unit or (order.customer.customer_name if order and order.customer else None)
                    # 产品选择（名称/图号）回填展示（提交仍由前端联动设置 product_id）
                    form.product_name.choices.append((src.product.product_name, src.product.product_name))
                    form.product_name.data = src.product.product_name
                    form.drawing_number.choices.append((src.product.drawing_number, src.product.drawing_number))
                    form.drawing_number.data = src.product.drawing_number
                    form.product_id.data = src.product_id
    except Exception as _e:
        current_app.logger.error(f'复制订单行预填失败: {str(_e)}')

    if form.validate_on_submit():
        try:
            # 获取最大序号
            max_sequence = db.session.query(db.func.max(SalesOrderItem.sequence)).filter_by(sales_order_id=order_id).scalar() or 0
            
            # 验证product_id是否有效
            if not form.product_id.data:
                flash('请选择有效的产品', 'danger')
                return render_template('main/sales_order_item_form.html', form=form, title='新增订单行', order=order)
            
            order_item = SalesOrderItem(
                sales_order_id=order_id,
                product_id=form.product_id.data,
                quantity=form.quantity.data,
                direction=form.direction.data,
                spec_extended=form.spec_extended.data,
                spec_gasket=form.spec_gasket.data,
                spec_joint=form.spec_joint.data,
                spec_drilling=form.spec_drilling.data,
                spec_other=form.spec_other.data,
                spec_other_desc=form.spec_other_desc.data,
                spec_splice_hole=form.spec_splice_hole.data,
                spec_gasket_hole=form.spec_gasket_hole.data,
                anti_corrosion=form.anti_corrosion.data,
                rubber_gasket_material=form.rubber_gasket_material.data,
                turnout_rail=form.turnout_rail.data,
                using_unit=(form.using_unit.data or (order.customer.customer_name if order and order.customer else None)),
                customer_address_id=(form.customer_address_id.data if form.customer_address_id.data else None),
                order_time=form.order_time.data,
                station_notes=form.station_notes.data,
                sequence=max_sequence + 1
            )
            
            db.session.add(order_item)
            
            # 更新订单合计数量
            order.calculate_total_quantity()
            
            # 记录审计日志
            log = AuditLog(
                user_id=current_user.id,
                action='新增订单行',
                details=f'为订单 {order.order_number} 新增订单行：{order_item.product_name} x {order_item.quantity}'
            )
            db.session.add(log)
            db.session.commit()
            
            flash('订单行新增成功', 'success')
            return redirect(url_for('main.sales_order_detail', order_id=order_id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'新增失败：{str(e)}', 'danger')
    
    return render_template('main/sales_order_item_form.html', form=form, title='新增订单行', order=order)

@bp.route('/sales_order_item/<int:item_id>/edit', methods=['GET', 'POST'])
@login_required
@require_capability('sales_order.manage')
def edit_sales_order_item(item_id):
    """编辑销售订单行"""
    
    order_item = SalesOrderItem.query.get_or_404(item_id)
    order = order_item.sales_order
    form = SalesOrderItemForm(obj=order_item)
    
    # 设置SelectField的选项
    form.product_name.choices = [('', '请选择产品名称')]
    form.drawing_number.choices = [('', '请选择图号')]
    form.customer_address_id.choices = [(0, '请选择收货地址')]
    
    # 预填充产品名称和图号字段
    if request.method == 'GET':
        form.product_name.data = order_item.product_name
        form.drawing_number.data = order_item.drawing_number
        form.product_id.data = order_item.product_id
    
    # 在验证前，动态添加用户提交的值到choices中，避免"Not a valid choice"错误
    if request.method == 'POST':
        if form.product_name.data and form.product_name.data not in [choice[0] for choice in form.product_name.choices]:
            form.product_name.choices.append((form.product_name.data, form.product_name.data))
        if form.drawing_number.data and form.drawing_number.data not in [choice[0] for choice in form.drawing_number.choices]:
            form.drawing_number.choices.append((form.drawing_number.data, form.drawing_number.data))
        if form.customer_address_id.data and form.customer_address_id.data != 0:
            # 获取地址信息用于显示
            from app.models import CustomerAddress
            address = CustomerAddress.query.get(form.customer_address_id.data)
            if address:
                address_text = f"{address.detailed_address} ({address.contact_person})"
                form.customer_address_id.choices.append((address.id, address_text))
    
    if form.validate_on_submit():
        try:
            # 保存旧数据用于审计
            old_data = {
                'product_id': order_item.product_id,
                'quantity': order_item.quantity,
                'direction': order_item.direction
            }
            
            # 更新订单行信息（不使用populate_obj避免设置只读属性）
            order_item.product_id = form.product_id.data
            order_item.quantity = form.quantity.data
            order_item.direction = form.direction.data
            order_item.spec_extended = form.spec_extended.data
            order_item.spec_gasket = form.spec_gasket.data
            order_item.spec_joint = form.spec_joint.data
            order_item.spec_drilling = form.spec_drilling.data
            order_item.spec_other = form.spec_other.data
            order_item.spec_other_desc = form.spec_other_desc.data
            order_item.spec_splice_hole = form.spec_splice_hole.data
            order_item.spec_gasket_hole = form.spec_gasket_hole.data
            order_item.anti_corrosion = form.anti_corrosion.data
            order_item.rubber_gasket_material = form.rubber_gasket_material.data
            order_item.turnout_rail = form.turnout_rail.data
            # 使用单位默认客户名，可修改
            order_item.using_unit = form.using_unit.data or (order.customer.customer_name if order and order.customer else None)
            order_item.customer_address_id = form.customer_address_id.data if form.customer_address_id.data != 0 else None
            order_item.order_time = form.order_time.data
            order_item.station_notes = form.station_notes.data
            
            # 更新订单合计数量
            order.calculate_total_quantity()
            
            # 记录审计日志
            log = AuditLog(
                user_id=current_user.id,
                action='编辑订单行',
                details=f'编辑订单 {order.order_number} 的订单行：{order_item.product_name}',
                old_data=old_data
            )
            db.session.add(log)
            db.session.commit()
            
            flash('订单行更新成功', 'success')
            return redirect(url_for('main.sales_order_detail', order_id=order.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'更新失败：{str(e)}', 'danger')
    
    return render_template('main/sales_order_item_form.html', form=form, title='编辑订单行', 
                         order=order, order_item=order_item)

@bp.route('/sales_order_item/<int:item_id>/delete', methods=['DELETE'])
@login_required
@require_capability('sales_order.manage')
def delete_sales_order_item(item_id):
    """删除销售订单行"""
    
    try:
        order_item = SalesOrderItem.query.get_or_404(item_id)
        order = order_item.sales_order
        
        # 保存旧数据用于回滚
        old_data = {
            'sales_order_id': order_item.sales_order_id,
            'product_id': order_item.product_id,
            'quantity': order_item.quantity,
            'direction': order_item.direction
        }
        
        # 记录可回滚的审计日志
        log = AuditLog(
            user_id=current_user.id,
            action='删除订单行',
            details=f'删除订单 {order.order_number} 的订单行：{order_item.product_name} x {order_item.quantity}',
            can_rollback=True,
            rollback_type='delete',
            target_model='SalesOrderItem',
            target_id=order_item.id,
            old_data=old_data
        )
        db.session.add(log)
        
        db.session.delete(order_item)
        
        # 更新订单合计数量
        order.calculate_total_quantity()
        
        db.session.commit()
        
        return jsonify({'success': True, 'message': '订单行删除成功'})
        
    except Exception as e:
        _reraise_http(e)
        db.session.rollback()
        return jsonify({'success': False, 'message': f'删除失败：{str(e)}'})

@bp.route('/sales_order_item/<int:item_id>/delivery_batches/manage', methods=['GET'])
@login_required
@require_capability('sales_order.manage')
def manage_delivery_batches_page(item_id):
    """分批到货管理页面"""
    
    order_item = SalesOrderItem.query.get_or_404(item_id)
    batches = order_item.delivery_batches_list
    
    return render_template('main/delivery_batches.html', 
                         order_item=order_item, 
                         batches=batches)
@bp.route('/sales_order_item/<int:item_id>/delivery_batches', methods=['GET', 'POST'])
@login_required
@require_capability('sales_order.manage')
@csrf.exempt  # 对分批到货API豁免CSRF保护
def manage_delivery_batches(item_id):
    """管理分批到货"""
    
    order_item = SalesOrderItem.query.get_or_404(item_id)
    
    if request.method == 'POST':
        try:
            data = request.get_json()
            batches = data.get('batches', [])
            
            # 验证分批数量总和不超过订单行数量
            total_batch_quantity = sum(batch.get('quantity', 0) for batch in batches)
            if total_batch_quantity > order_item.quantity:
                return jsonify({'success': False, 'message': '分批数量总和不能超过订单数量'})
            
            # 保存分批信息
            order_item.set_delivery_batches(batches)
            db.session.commit()
            
            # 记录审计日志
            log = AuditLog(
                user_id=current_user.id,
                action='设置分批到货',
                details=f'为订单行 {order_item.product_name} 设置分批到货，共 {len(batches)} 批次'
            )
            db.session.add(log)
            db.session.commit()
            
            return jsonify({'success': True, 'message': '分批到货设置成功'})
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'设置失败：{str(e)}'})
    
    # GET请求返回当前分批信息
    return jsonify({
        'success': True,
        'data': {
            'order_item': {
                'id': order_item.id,
                'product_name': order_item.product_name,
                'quantity': order_item.quantity,
                'unit': order_item.unit
            },
            'batches': order_item.delivery_batches_list
        }
    })

# ==================== 销售订单管理 API ====================

@bp.route('/api/sales_orders/search')
@login_required
@require_capability('sales_order.manage')
def api_search_sales_orders():
    """销售订单搜索API"""
    try:
        search = request.args.get('search', '').strip()
        status_filter = request.args.get('status', '')
        
        query = SalesOrder.query.join(Customer)
        
        if status_filter:
            query = query.filter(SalesOrder.status == status_filter)
        
        if search:
            search_term = f"%{search}%"
            query = query.filter(db.or_(
                SalesOrder.order_number.like(search_term),
                Customer.customer_name.like(search_term),
                Customer.customer_code.like(search_term)
            ))
        
        sales_orders = query.order_by(SalesOrder.created_at.desc()).limit(50).all()
        
        return jsonify({
            'success': True,
            'data': [{
                'id': order.id,
                'order_number': order.order_number,
                'customer_name': order.customer.customer_name,
                'customer_code': order.customer.customer_code,
                'year_month': order.year_month,
                'total_quantity': order.total_quantity,
                'status': order.status,
                'order_date': order.order_date.strftime('%Y-%m-%d %H:%M')
            } for order in sales_orders]
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'搜索失败：{str(e)}'})


# ==================== 产品名称和图号选择 API ====================

@bp.route('/api/products/names')
@login_required
@require_capability('product.lookup')
def api_get_product_names():
    """获取产品名称列表（去重）"""
    try:
        only_active = request.args.get('only_active', 'true').lower() == 'true'
        
        # 获取去重的产品名称
        query = db.session.query(Product.product_name).distinct()
        if only_active:
            query = query.filter(Product.status == 'active')
        
        product_names = query.order_by(Product.product_name).all()
        
        return jsonify({
            'success': True,
            'data': [name[0] for name in product_names if name[0]]  # 过滤空值
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'获取产品名称失败：{str(e)}'})

@bp.route('/api/products/drawings-by-name')
@login_required
@require_capability('product.lookup')
def api_get_drawings_by_product_name():
    """根据产品名称获取图号列表"""
    try:
        product_name = request.args.get('product_name', '').strip()
        only_active = request.args.get('only_active', 'true').lower() == 'true'
        
        if not product_name:
            return jsonify({'success': False, 'message': '产品名称不能为空'})
        
        query = Product.query.filter(Product.product_name == product_name)
        if only_active:
            query = query.filter(Product.status == 'active')
        
        products = query.order_by(Product.drawing_number).all()
        
        return jsonify({
            'success': True,
            'data': [{
                'id': product.id,
                'product_code': product.product_code,
                'product_name': product.product_name,
                'drawing_number': product.drawing_number or '',
                'unit': product.unit,
                'status': product.status
            } for product in products]
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'获取图号列表失败：{str(e)}'})

# ==================== 客户地址选择 API ====================

@bp.route('/api/customers/<int:customer_id>/addresses')
@login_required
@require_capability('customer.manage')
def api_get_customer_addresses(customer_id):
    """获取指定客户的地址列表"""
    try:
        only_active = request.args.get('only_active', 'true').lower() == 'true'
        
        query = CustomerAddress.query.filter(CustomerAddress.customer_id == customer_id)
        if only_active:
            query = query.filter(CustomerAddress.is_active == True)
        
        addresses = query.order_by(CustomerAddress.is_primary.desc(), CustomerAddress.created_at.desc()).all()
        
        return jsonify({
            'success': True,
            'data': [{
                'id': addr.id,
                'contact_person': addr.contact_person,
                'contact_phone': addr.contact_phone,
                'full_address': addr.full_address,
                'address_type': addr.address_type,
                'is_primary': addr.is_primary,
                'is_active': addr.is_active
            } for addr in addresses]
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'获取客户地址失败：{str(e)}'})

@bp.route('/api/sales_orders/<int:order_id>/customer_addresses')
@login_required
@require_capability('sales_order.manage')
def api_get_sales_order_customer_addresses(order_id):
    """获取销售订单对应客户的地址列表"""
    try:
        order = SalesOrder.query.get_or_404(order_id)
        only_active = request.args.get('only_active', 'true').lower() == 'true'
        
        query = CustomerAddress.query.filter(CustomerAddress.customer_id == order.customer_id)
        if only_active:
            query = query.filter(CustomerAddress.is_active == True)
        
        addresses = query.order_by(CustomerAddress.is_primary.desc(), CustomerAddress.created_at.desc()).all()
        
        return jsonify({
            'success': True,
            'data': [{
                'id': addr.id,
                'contact_person': addr.contact_person,
                'contact_phone': addr.contact_phone,
                'full_address': addr.full_address,
                'address_type': addr.address_type,
                'is_primary': addr.is_primary,
                'is_active': addr.is_active
            } for addr in addresses]
        })
        
    except Exception as e:
        _reraise_http(e)
        return jsonify({'success': False, 'message': f'获取客户地址失败：{str(e)}'}) 


# ================== 通知系统路由 ==================

@bp.route('/notifications')
@login_required
def manage_notifications():
    """通知管理页面"""
    from app.services.notification_service import NotificationService
    
    # 获取用户通知
    notifications_data = NotificationService.get_user_notifications(
        user_id=current_user.id,
        status=request.args.get('status'),
        limit=int(request.args.get('limit', 50))
    )
    
    return render_template('main/notifications.html',
                         notifications=notifications_data['notifications'],
                         stats=notifications_data['stats'])


@bp.route('/notifications/<int:notification_id>/read', methods=['POST'])
@login_required
def mark_notification_read(notification_id):
    """标记通知为已读"""
    from app.services.notification_service import NotificationService
    
    success = NotificationService.mark_as_read(notification_id, current_user.id)
    
    return jsonify({
        'success': success,
        'message': '标记成功' if success else '标记失败'
    })


@bp.route('/notification_rules')
@login_required
@require_capability('notification_rule.manage')
def manage_notification_rules():
    """通知规则管理"""
    
    from app.models import NotificationRule
    rules = NotificationRule.query.order_by(NotificationRule.priority.desc()).all()
    
    return render_template('main/notification_rules.html', rules=rules)


@bp.route('/notification_rules/add', methods=['GET', 'POST'])  
@login_required
@require_capability('notification_rule.manage')
def add_notification_rule():
    """添加通知规则"""
    
    form = NotificationRuleForm()
    
    if form.validate_on_submit():
        try:
            import json
            from app.models import NotificationRule
            
            rule = NotificationRule(
                rule_name=form.rule_name.data,
                trigger_type=form.trigger_type.data,
                receiver_type=form.receiver_type.data,
                receiver_config=json.loads(form.receiver_config.data) if form.receiver_config.data else {},
                priority=form.priority.data,
                is_active=form.is_active.data,
                created_by=current_user.id
            )
            
            db.session.add(rule)
            db.session.commit()
            
            flash('通知规则创建成功', 'success')
            return redirect(url_for('main.manage_notification_rules'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'创建失败: {str(e)}', 'danger')
    
    return render_template('main/add_notification_rule.html', form=form)


@bp.route('/api/notifications/stats')
@login_required
def api_notification_stats():
    """获取用户通知统计"""
    from app.services.notification_service import NotificationService
    
    stats = NotificationService.get_user_notification_stats(current_user.id)
    return jsonify(stats)

@bp.route('/api/notifications/recent')
@login_required
def api_recent_notifications():
    """获取最近的通知列表"""
    try:
        from app.models import Notification, NotificationReceiver
        
        # 获取当前用户最近的通知（最多10条）
        notifications_query = db.session.query(Notification, NotificationReceiver)\
            .join(NotificationReceiver, Notification.id == NotificationReceiver.notification_id)\
            .filter(NotificationReceiver.user_id == current_user.id)\
            .order_by(Notification.created_at.desc())\
            .limit(10)
        
        notifications_data = []
        for notification, receiver in notifications_query:
            notifications_data.append({
                'id': notification.id,
                'title': notification.title,
                'content': notification.content,
                'priority': notification.priority,
                'is_read': receiver.is_read,
                'created_at': notification.created_at.isoformat(),
                'trigger_type': notification.trigger_type
            })
        
        return jsonify({
            'success': True,
            'notifications': notifications_data
        })
        
    except Exception as e:
        current_app.logger.error(f'获取最近通知失败: {str(e)}')
        return jsonify({'success': False, 'message': '获取通知失败'}), 500


# ==================== 图表数据API路由 ====================

@bp.route('/api/chart-data/salary')
@login_required
@require_capability('dashboard.chart.view')
def api_chart_data_salary():
    """获取最近12个自然月的计件工资总额"""
    try:
        # 逐月回退，避免用固定天数近似月份
        months = []
        year, month = date.today().year, date.today().month
        for _ in range(12):
            months.append((year, month))
            month -= 1
            if month == 0:
                year, month = year - 1, 12
        months.reverse()
        start_date = date(months[0][0], months[0][1], 1)

        rows = db.session.query(
            ProductionRecord.date,
            ProductionRecord.quantity,
            ProcessPrice.price
        ).join(
            ProcessPrice, ProductionRecord.process_id == ProcessPrice.id
        ).filter(ProductionRecord.date >= start_date).all()

        monthly_wage = {}
        for record_date, quantity, price in rows:
            key = (record_date.year, record_date.month)
            monthly_wage[key] = monthly_wage.get(key, 0) + (quantity or 0) * (price or 0)

        data = {
            'labels': [f'{y}年{m}月' for y, m in months],
            'datasets': [{
                'label': '月度计件工资',
                'data': [round(monthly_wage.get(key, 0), 2) for key in months],
                'borderColor': '#007bff',
                'backgroundColor': 'rgba(0, 123, 255, 0.1)'
            }]
        }

        return jsonify({'success': True, 'data': data})
    except Exception as e:
        current_app.logger.error(f'获取工资统计数据失败: {str(e)}')
        return jsonify({'success': False, 'message': f'获取工资统计数据失败: {str(e)}'})

@bp.route('/api/chart-data/production')
@login_required
@require_capability('dashboard.chart.view')
def api_chart_data_production():
    """获取生产统计图表数据"""
    try:
        # 获取最近30天的生产数据
        from datetime import datetime, timedelta
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=30)
        
        # 查询生产记录
        production_records = ProductionRecord.query.filter(
            ProductionRecord.date.between(start_date, end_date)
        ).all()
        
        # 按日期汇总生产数量
        daily_production = {}
        for record in production_records:
            date_str = record.date.strftime('%m-%d')
            if date_str not in daily_production:
                daily_production[date_str] = 0
            daily_production[date_str] += record.quantity
        
        # 生成最近30天的标签和数据
        labels = []
        data = []
        current_date = start_date
        while current_date <= end_date:
            date_str = current_date.strftime('%m-%d')
            labels.append(date_str)
            data.append(daily_production.get(date_str, 0))
            current_date += timedelta(days=1)
        
        chart_data = {
            'labels': labels,
            'datasets': [{
                'label': '日产量',
                'data': data,
                'borderColor': '#28a745',
                'backgroundColor': 'rgba(40, 167, 69, 0.1)'
            }]
        }
        
        return jsonify({'success': True, 'data': chart_data})
    except Exception as e:
        return jsonify({'success': False, 'message': f'获取生产统计数据失败: {str(e)}'})

@bp.route('/api/chart-data/department')
@login_required
@require_capability('dashboard.chart.view')
def api_chart_data_department():
    """获取部门统计图表数据"""
    try:
        # 按部门统计员工数量
        from sqlalchemy import func
        department_stats = db.session.query(
            Employee.department,
            func.count(Employee.id).label('count')
        ).filter(Employee.is_active.is_(True)).group_by(Employee.department).all()
        
        data = {
            'labels': [stat[0] or '未分配' for stat in department_stats],
            'datasets': [{
                'label': '员工数量',
                'data': [stat[1] for stat in department_stats],
                'backgroundColor': [
                    '#007bff', '#28a745', '#ffc107', '#dc3545', 
                    '#6c757d', '#17a2b8', '#6f42c1', '#e83e8c'
                ]
            }]
        }
        
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'message': f'获取部门统计数据失败: {str(e)}'})

@bp.route('/api/chart-data/task')
@login_required
@require_capability('dashboard.chart.view')
def api_chart_data_task():
    """获取任务统计图表数据"""
    try:
        # 按状态统计任务数量
        from sqlalchemy import func
        task_stats = db.session.query(
            TaskAssignment.status,
            func.count(TaskAssignment.id).label('count')
        ).group_by(TaskAssignment.status).all()
        
        status_labels = {
            'pending': '待处理',
            'in_progress': '进行中',
            'completed': '已完成',
            'cancelled': '已取消'
        }
        
        data = {
            'labels': [status_labels.get(stat[0], stat[0]) for stat in task_stats],
            'datasets': [{
                'label': '任务数量',
                'data': [stat[1] for stat in task_stats],
                'backgroundColor': ['#ffc107', '#007bff', '#28a745', '#dc3545']
            }]
        }
        
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'message': f'获取任务统计数据失败: {str(e)}'})


# ==================== 易耗品管理路由 ====================

@bp.route('/consumables')
@login_required
@require_capability('inventory.manage')
@handle_pagination_args
def manage_consumables():
    """易耗品管理"""
    from app.main.forms import ConsumableSearchForm
    from app.models import Consumable, ConsumableCategory
    from datetime import datetime, timedelta
    
    form = ConsumableSearchForm()
    
    # 构建查询
    query = Consumable.query
    
    # 搜索条件
    if form.search.data:
        search_term = f"%{form.search.data}%"
        query = query.join(ConsumableCategory).filter(
            db.or_(
                Consumable.supplier.like(search_term),
                ConsumableCategory.name.like(search_term),
                Consumable.specification.like(search_term),
                Consumable.internal_number.like(search_term),
                Consumable.supplier_number.like(search_term)
            )
        )
    
    # 品类筛选
    if form.category_id.data and form.category_id.data != 0:
        query = query.filter(Consumable.category_id == form.category_id.data)
    
    # 状态筛选
    if form.status.data:
        query = query.filter(Consumable.status == form.status.data)
    
    # 供应商筛选
    if form.supplier.data:
        query = query.filter(Consumable.supplier.like(f"%{form.supplier.data}%"))
    
    # 入库日期筛选
    if form.storage_date_start.data:
        query = query.filter(Consumable.storage_date >= form.storage_date_start.data)
    if form.storage_date_end.data:
        query = query.filter(Consumable.storage_date <= form.storage_date_end.data)
    
    # 特殊筛选条件
    if form.low_stock_only.data:
        query = query.filter(
            db.and_(
                Consumable.min_stock_level > 0,
                Consumable.quantity <= Consumable.min_stock_level
            )
        )
    
    if form.expired_only.data:
        today = datetime.now().date()
        query = query.filter(
            db.and_(
                Consumable.expiry_date.isnot(None),
                Consumable.expiry_date < today
            )
        )
    
    if form.expiring_soon.data:
        today = datetime.now().date()
        thirty_days_later = today + timedelta(days=30)
        query = query.filter(
            db.and_(
                Consumable.expiry_date.isnot(None),
                Consumable.expiry_date >= today,
                Consumable.expiry_date <= thirty_days_later
            )
        )
    
    # 排序
    query = query.order_by(Consumable.created_at.desc())
    
    # 分页
    # 分页（统一走 @handle_pagination_args 的白名单口径）
    page = request.validated_page
    per_page = request.validated_per_page
    consumables = query.paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    # 统计信息
    total_count = Consumable.query.count()
    in_stock_count = Consumable.query.filter_by(status='in_stock').count()
    low_stock_count = Consumable.query.filter(
        db.and_(
            Consumable.min_stock_level > 0,
            Consumable.quantity <= Consumable.min_stock_level,
            Consumable.status == 'in_stock'
        )
    ).count()
    
    today = datetime.now().date()
    expired_count = Consumable.query.filter(
        db.and_(
            Consumable.expiry_date.isnot(None),
            Consumable.expiry_date < today,
            Consumable.status == 'in_stock'
        )
    ).count()
    
    thirty_days_later = today + timedelta(days=30)
    expiring_soon_count = Consumable.query.filter(
        db.and_(
            Consumable.expiry_date.isnot(None),
            Consumable.expiry_date >= today,
            Consumable.expiry_date <= thirty_days_later,
            Consumable.status == 'in_stock'
        )
    ).count()
    
    stats = {
        'total': total_count,
        'in_stock': in_stock_count,
        'low_stock': low_stock_count,
        'expired': expired_count,
        'expiring_soon': expiring_soon_count
    }
    
    return render_template('main/consumables.html', 
                         consumables=consumables, 
                         form=form, 
                         stats=stats)

@bp.route('/consumables/inbound', methods=['GET', 'POST'])
@login_required
@require_capability('inventory.manage')
def consumable_inbound():
    """易耗品入库"""
    from app.main.forms import ConsumableInboundForm
    from app.models import Consumable, ConsumableCategory
    
    form = ConsumableInboundForm()
    
    if form.validate_on_submit():
        try:
            # 验证品类是否存在
            category = ConsumableCategory.query.get(form.category_id.data)
            if not category:
                flash('选择的品类不存在', 'danger')
                return render_template('main/consumable_inbound.html', form=form)
            
            # 创建易耗品记录
            consumable = Consumable(
                supplier=form.supplier.data,
                category_id=form.category_id.data,
                specification=form.specification.data,
                supplier_number=form.supplier_number.data,
                internal_number=form.internal_number.data or None,  # 留空则自动生成
                quantity=form.quantity.data,
                unit=form.unit.data,
                unit_price=form.unit_price.data or 0,
                expiry_date=form.expiry_date.data,
                storage_location=form.storage_location.data,
                min_stock_level=form.min_stock_level.data or 0,
                storage_date=form.storage_date.data,
                notes=form.notes.data
            )
            
            db.session.add(consumable)
            
            # 记录审计日志
            audit_log = AuditLog(
                user_id=current_user.id,
                action='添加易耗品',
                details=f'添加易耗品：{category.name} - {consumable.supplier} - {consumable.supplier_number}',
                can_rollback=True,
                rollback_type='add',
                target_model='Consumable',
                target_id=consumable.id,
                new_data={
                    'supplier': consumable.supplier,
                    'category_id': consumable.category_id,
                    'specification': consumable.specification,
                    'supplier_number': consumable.supplier_number,
                    'quantity': consumable.quantity,
                    'unit': consumable.unit,
                    'unit_price': consumable.unit_price
                }
            )
            db.session.add(audit_log)
            
            db.session.commit()
            flash(f'易耗品入库成功！内部编号：{consumable.internal_number}', 'success')
            return redirect(url_for('main.manage_consumables'))
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'易耗品入库失败: {str(e)}')
            flash(f'入库失败：{str(e)}', 'danger')
    
    return render_template('main/consumable_inbound.html', form=form)

@bp.route('/consumables/<int:id>', methods=['GET'])
@login_required
@require_capability('inventory.manage')
def get_consumable(id):
    """获取易耗品详情"""
    from app.models import Consumable

    consumable = Consumable.query.get_or_404(id)
    
    return jsonify({
        'id': consumable.id,
        'global_sn': consumable.global_sn,
        'supplier': consumable.supplier,
        'category_id': consumable.category_id,
        'category_name': consumable.consumable_name,
        'category_code': consumable.category_code,
        'specification': consumable.specification,
        'supplier_number': consumable.supplier_number,
        'internal_number': consumable.internal_number,
        'quantity': consumable.quantity,
        'unit': consumable.unit,
        'unit_price': consumable.unit_price,
        'total_price': consumable.total_price,
        'expiry_date': consumable.expiry_date.strftime('%Y-%m-%d') if consumable.expiry_date else None,
        'storage_location': consumable.storage_location,
        'min_stock_level': consumable.min_stock_level,
        'storage_date': consumable.storage_date.strftime('%Y-%m-%d %H:%M:%S'),
        'notes': consumable.notes,
        'status': consumable.status,
        'is_low_stock': consumable.is_low_stock,
        'is_expired': consumable.is_expired,
        'days_to_expiry': consumable.days_to_expiry,
        'created_at': consumable.created_at.strftime('%Y-%m-%d %H:%M:%S')
    })
@bp.route('/consumables/<int:id>', methods=['PUT'])
@login_required
@require_capability('inventory.manage')
def update_consumable(id):
    """更新易耗品"""
    from app.main.forms import ConsumableUpdateForm
    from app.models import Consumable, ConsumableCategory
    
    consumable = Consumable.query.get_or_404(id)
    
    # 保存旧数据用于审计日志
    old_data = {
        'supplier': consumable.supplier,
        'category_id': consumable.category_id,
        'specification': consumable.specification,
        'supplier_number': consumable.supplier_number,
        'quantity': consumable.quantity,
        'unit': consumable.unit,
        'unit_price': consumable.unit_price,
        'expiry_date': consumable.expiry_date.strftime('%Y-%m-%d') if consumable.expiry_date else None,
        'storage_location': consumable.storage_location,
        'min_stock_level': consumable.min_stock_level,
        'status': consumable.status,
        'notes': consumable.notes
    }
    
    try:
        data = request.get_json()
        
        # 验证品类是否存在
        if 'category_id' in data:
            category = ConsumableCategory.query.get(data['category_id'])
            if not category:
                return jsonify({'success': False, 'message': '选择的品类不存在'}), 400
        
        # 更新字段
        if 'supplier' in data:
            consumable.supplier = data['supplier']
        if 'category_id' in data:
            consumable.category_id = data['category_id']
        if 'specification' in data:
            consumable.specification = data['specification']
        if 'supplier_number' in data:
            consumable.supplier_number = data['supplier_number']
        if 'quantity' in data:
            consumable.quantity = float(data['quantity'])
        if 'unit' in data:
            consumable.unit = data['unit']
        if 'unit_price' in data:
            consumable.unit_price = float(data['unit_price'])
            # 重新计算总价
            consumable.total_price = consumable.unit_price * consumable.quantity
        if 'expiry_date' in data:
            if data['expiry_date']:
                consumable.expiry_date = datetime.strptime(data['expiry_date'], '%Y-%m-%d').date()
            else:
                consumable.expiry_date = None
        if 'storage_location' in data:
            consumable.storage_location = data['storage_location']
        if 'min_stock_level' in data:
            consumable.min_stock_level = float(data['min_stock_level']) if data['min_stock_level'] else 0
        if 'status' in data:
            consumable.status = data['status']
        if 'notes' in data:
            consumable.notes = data['notes']
        
        # 新数据
        new_data = {
            'supplier': consumable.supplier,
            'category_id': consumable.category_id,
            'specification': consumable.specification,
            'supplier_number': consumable.supplier_number,
            'quantity': consumable.quantity,
            'unit': consumable.unit,
            'unit_price': consumable.unit_price,
            'expiry_date': consumable.expiry_date.strftime('%Y-%m-%d') if consumable.expiry_date else None,
            'storage_location': consumable.storage_location,
            'min_stock_level': consumable.min_stock_level,
            'status': consumable.status,
            'notes': consumable.notes
        }
        
        # 记录审计日志
        audit_log = AuditLog(
            user_id=current_user.id,
            action='更新易耗品',
            details=f'更新易耗品：{consumable.consumable_name} - {consumable.internal_number}',
            can_rollback=True,
            rollback_type='edit',
            target_model='Consumable',
            target_id=consumable.id,
            old_data=old_data,
            new_data=new_data
        )
        db.session.add(audit_log)
        
        db.session.commit()
        return jsonify({'success': True, 'message': '更新成功'})
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'更新易耗品失败: {str(e)}')
        return jsonify({'success': False, 'message': f'更新失败：{str(e)}'}), 500
@bp.route('/consumables/<int:id>', methods=['DELETE'])
@login_required
@require_capability('consumable.delete')
@csrf.exempt
def delete_consumable(id):
    """删除易耗品"""
    
    try:
        consumable = Consumable.query.get_or_404(id)
        
        # 保存旧数据用于回滚
        old_data = {
            'supplier': consumable.supplier,
            'category_id': consumable.category_id,
            'specification': consumable.specification,
            'supplier_number': consumable.supplier_number,
            'internal_number': consumable.internal_number,
            'quantity': consumable.quantity,
            'unit': consumable.unit,
            'unit_price': consumable.unit_price,
            'total_price': consumable.total_price,
            'expiry_date': consumable.expiry_date.strftime('%Y-%m-%d') if consumable.expiry_date else None,
            'storage_location': consumable.storage_location,
            'min_stock_level': consumable.min_stock_level,
            'storage_date': consumable.storage_date.strftime('%Y-%m-%d %H:%M:%S'),
            'notes': consumable.notes,
            'status': consumable.status
        }
        
        # 记录审计日志
        audit_log = AuditLog(
            user_id=current_user.id,
            action='删除易耗品',
            details=f'删除易耗品：{consumable.consumable_name} - {consumable.internal_number}',
            can_rollback=True,
            rollback_type='delete',
            target_model='Consumable',
            target_id=consumable.id,
            old_data=old_data
        )
        db.session.add(audit_log)
        
        db.session.delete(consumable)
        db.session.commit()
        
        return jsonify({'success': True, 'message': '删除成功'})
        
    except Exception as e:
        _reraise_http(e)
        db.session.rollback()
        current_app.logger.error(f'删除易耗品失败: {str(e)}')
        return jsonify({'success': False, 'message': f'删除失败：{str(e)}'}), 500

@bp.route('/consumables/<int:id>/use', methods=['POST'])
@login_required
@require_capability('inventory.manage')
def use_consumable(id):
    """使用易耗品"""
    from app.main.forms import ConsumableUsageForm
    
    consumable = Consumable.query.get_or_404(id)
    
    if consumable.status != 'in_stock':
        return jsonify({'success': False, 'message': '该易耗品不在库存中，无法使用'}), 400
    
    try:
        data = request.get_json()
        usage_quantity = float(data.get('usage_quantity', 0))
        
        if usage_quantity <= 0:
            return jsonify({'success': False, 'message': '使用数量必须大于0'}), 400
        
        if usage_quantity > consumable.quantity:
            return jsonify({'success': False, 'message': '使用数量不能超过库存数量'}), 400
        
        # 保存旧数据
        old_quantity = consumable.quantity
        old_status = consumable.status
        
        # 更新库存
        consumable.quantity -= usage_quantity
        
        # 如果库存耗尽，更新状态
        if consumable.quantity <= 0:
            consumable.status = 'used'
        
        # 记录审计日志
        audit_log = AuditLog(
            user_id=current_user.id,
            action='使用易耗品',
            details=f'使用易耗品：{consumable.consumable_name} - {consumable.internal_number}，使用数量：{usage_quantity}，使用人：{data.get("used_by", "")}',
            can_rollback=True,
            rollback_type='edit',
            target_model='Consumable',
            target_id=consumable.id,
            old_data={
                'quantity': old_quantity,
                'status': old_status
            },
            new_data={
                'quantity': consumable.quantity,
                'status': consumable.status,
                'usage_info': {
                    'usage_quantity': usage_quantity,
                    'used_by': data.get('used_by', ''),
                    'usage_purpose': data.get('usage_purpose', ''),
                    'usage_date': data.get('usage_date', datetime.now().strftime('%Y-%m-%d')),
                    'notes': data.get('notes', '')
                }
            }
        )
        db.session.add(audit_log)
        
        db.session.commit()
        return jsonify({'success': True, 'message': '使用记录成功'})
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'使用易耗品失败: {str(e)}')
        return jsonify({'success': False, 'message': f'使用失败：{str(e)}'}), 500

@bp.route('/consumables/categories')
@login_required
@require_capability('inventory.manage')
def consumable_categories():
    """易耗品品类管理"""
    from app.models import ConsumableCategory
    
    categories = ConsumableCategory.query.order_by(ConsumableCategory.created_at.desc()).all()
    return render_template('main/consumable_categories.html', categories=categories)

@bp.route('/consumables/categories/add', methods=['POST'])
@login_required
@require_capability('inventory.manage')
def add_consumable_category():
    """添加易耗品品类"""
    from app.main.forms import ConsumableCategoryForm
    from app.models import ConsumableCategory
    
    form = ConsumableCategoryForm()
    
    if form.validate_on_submit():
        try:
            # 检查品类名称是否已存在
            existing_name = ConsumableCategory.query.filter_by(name=form.name.data).first()
            if existing_name:
                return jsonify({'success': False, 'message': '品类名称已存在'}), 400
            
            # 检查品类编码是否已存在
            existing_code = ConsumableCategory.query.filter_by(code=form.code.data).first()
            if existing_code:
                return jsonify({'success': False, 'message': '品类编码已存在'}), 400
            
            category = ConsumableCategory(
                name=form.name.data,
                code=form.code.data,
                description=form.description.data,
                is_active=form.is_active.data,
                requires_approval=form.requires_approval.data,
                created_by=current_user.id
            )
            
            db.session.add(category)
            
            # 记录审计日志
            audit_log = AuditLog(
                user_id=current_user.id,
                action='添加易耗品品类',
                details=f'添加易耗品品类：{category.name} ({category.code})',
                can_rollback=True,
                rollback_type='add',
                target_model='ConsumableCategory',
                target_id=category.id,
                new_data={
                    'name': category.name,
                    'code': category.code,
                    'description': category.description,
                    'is_active': category.is_active,
                    'requires_approval': category.requires_approval
                }
            )
            db.session.add(audit_log)
            
            db.session.commit()
            return jsonify({'success': True, 'message': '品类添加成功'})
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'添加易耗品品类失败: {str(e)}')
            return jsonify({'success': False, 'message': f'添加失败：{str(e)}'}), 500
    
    # 返回表单验证错误
    errors = []
    for field, field_errors in form.errors.items():
        for error in field_errors:
            errors.append(f'{form[field].label.text}: {error}')
    
    return jsonify({'success': False, 'message': '; '.join(errors)}), 400

@bp.route('/consumables/categories/<int:category_id>', methods=['GET'])
@login_required
@require_capability('inventory.manage')
def get_consumable_category(category_id):
    """获取易耗品品类详情"""
    from app.models import ConsumableCategory
    
    category = ConsumableCategory.query.get_or_404(category_id)
    return jsonify(category.to_dict())

@bp.route('/consumables/categories/<int:category_id>', methods=['PUT'])
@login_required
@require_capability('inventory.manage')
def update_consumable_category(category_id):
    """更新易耗品品类"""
    from app.models import ConsumableCategory
    
    category = ConsumableCategory.query.get_or_404(category_id)
    
    # 保存旧数据
    old_data = {
        'name': category.name,
        'code': category.code,
        'description': category.description,
        'is_active': category.is_active,
        'requires_approval': category.requires_approval
    }
    
    try:
        data = request.get_json() or {}
        
        # 检查名称唯一性
        if 'name' in data and data['name'] != category.name:
            existing_name = ConsumableCategory.query.filter_by(name=data['name']).first()
            if existing_name:
                return jsonify({'success': False, 'message': '品类名称已存在'}), 400
        
        # 检查编码唯一性
        if 'code' in data and data['code'] != category.code:
            existing_code = ConsumableCategory.query.filter_by(code=data['code']).first()
            if existing_code:
                return jsonify({'success': False, 'message': '品类编码已存在'}), 400
        
        # 更新字段
        if 'name' in data:
            category.name = data['name']
        if 'code' in data:
            category.code = data['code']
        if 'description' in data:
            category.description = data['description']
        if 'is_active' in data:
            category.is_active = data['is_active']
        if 'requires_approval' in data:
            category.requires_approval = _parse_flag(data, 'requires_approval', False)
        
        category.updated_at = datetime.utcnow()
        
        # 新数据
        new_data = {
            'name': category.name,
            'code': category.code,
            'description': category.description,
            'is_active': category.is_active,
            'requires_approval': category.requires_approval
        }
        
        # 记录审计日志
        audit_log = AuditLog(
            user_id=current_user.id,
            action='更新易耗品品类',
            details=f'更新易耗品品类：{category.name} ({category.code})',
            can_rollback=True,
            rollback_type='edit',
            target_model='ConsumableCategory',
            target_id=category.id,
            old_data=old_data,
            new_data=new_data
        )
        db.session.add(audit_log)
        
        db.session.commit()
        return jsonify({'success': True, 'message': '更新成功'})
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'更新易耗品品类失败: {str(e)}')
        return jsonify({'success': False, 'message': f'更新失败：{str(e)}'}), 500

@bp.route('/consumables/categories/<int:category_id>', methods=['DELETE'])
@login_required
@require_capability('consumable.delete')
def delete_consumable_category(category_id):
    """删除易耗品品类"""
    from app.models import ConsumableCategory, Consumable
    
    
    try:
        category = ConsumableCategory.query.get_or_404(category_id)
        
        # 检查是否有易耗品使用该品类
        consumable_count = Consumable.query.filter_by(category_id=category_id).count()
        if consumable_count > 0:
            return jsonify({'success': False, 'message': f'该品类下还有 {consumable_count} 个易耗品，无法删除'}), 400
        
        # 保存旧数据用于回滚
        old_data = {
            'name': category.name,
            'code': category.code,
            'description': category.description,
            'is_active': category.is_active,
            'created_at': category.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'created_by': category.created_by
        }
        
        # 记录审计日志
        audit_log = AuditLog(
            user_id=current_user.id,
            action='删除易耗品品类',
            details=f'删除易耗品品类：{category.name} ({category.code})',
            can_rollback=True,
            rollback_type='delete',
            target_model='ConsumableCategory',
            target_id=category.id,
            old_data=old_data
        )
        db.session.add(audit_log)
        
        db.session.delete(category)
        db.session.commit()
        
        return jsonify({'success': True, 'message': '删除成功'})
        
    except Exception as e:
        _reraise_http(e)
        db.session.rollback()
        current_app.logger.error(f'删除易耗品品类失败: {str(e)}')
        return jsonify({'success': False, 'message': f'删除失败：{str(e)}'}), 500

@bp.route('/api/consumable-categories', methods=['GET'])
@login_required
@require_capability('inventory.manage')
def get_consumable_categories_api():
    """获取易耗品品类列表API"""
    from app.models import ConsumableCategory
    
    try:
        categories = ConsumableCategory.query.filter_by(is_active=True).order_by(ConsumableCategory.name).all()
        
        result = []
        for category in categories:
            result.append({
                'id': category.id,
                'name': category.name,
                'code': category.code,
                'description': category.description
            })
        
        return jsonify({
            'success': True,
            'categories': result
        })
        
    except Exception as e:
        current_app.logger.error(f'获取易耗品品类列表失败: {str(e)}')
        return jsonify({'success': False, 'message': f'获取失败：{str(e)}'}), 500

# ==================== 物料领用管理 ====================

@bp.route('/material_requisitions')
@login_required
@require_capability('inventory.manage')
@handle_pagination_args
def manage_material_requisitions():
    """物料领用记录管理"""
    from app.main.forms import MaterialRequisitionSearchForm
    from app.models import MaterialRequisition, Employee
    
    form = MaterialRequisitionSearchForm()
    
    # 构建查询
    query = MaterialRequisition.query.join(Employee)
    
    # 处理搜索条件
    if request.method == 'POST' and form.validate_on_submit():
        if form.search.data:
            search_term = f"%{form.search.data}%"
            query = query.filter(
                db.or_(
                    MaterialRequisition.requisition_number.like(search_term),
                    Employee.name.like(search_term),
                    MaterialRequisition.department.like(search_term),
                    MaterialRequisition.purpose.like(search_term)
                )
            )
        
        if form.department.data:
            query = query.filter(MaterialRequisition.department.like(f"%{form.department.data}%"))
        
        if form.employee_id.data and form.employee_id.data != 0:
            query = query.filter(MaterialRequisition.employee_id == form.employee_id.data)
        
        if form.requisition_date_start.data:
            query = query.filter(MaterialRequisition.required_date >= form.requisition_date_start.data)
        
        if form.requisition_date_end.data:
            query = query.filter(MaterialRequisition.required_date <= form.requisition_date_end.data)
    
    # 排序和分页
    query = query.order_by(MaterialRequisition.requested_date.desc())
    
    # 分页（统一走 @handle_pagination_args 的白名单口径）
    page = request.validated_page
    per_page = request.validated_per_page
    
    requisitions = query.paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    # 统计数据
    total_count = MaterialRequisition.query.count()
    this_month_count = MaterialRequisition.query.filter(
        MaterialRequisition.required_date >= datetime.now().replace(day=1).date()
    ).count()
    this_week_count = MaterialRequisition.query.filter(
        MaterialRequisition.required_date >= (datetime.now() - timedelta(days=7)).date()
    ).count()
    today_count = MaterialRequisition.query.filter(
        MaterialRequisition.required_date == datetime.now().date()
    ).count()
    
    return render_template('main/material_requisitions.html',
                         requisitions=requisitions,
                         form=form,
                         total_count=total_count,
                         this_month_count=this_month_count,
                         this_week_count=this_week_count,
                         today_count=today_count)

@bp.route('/material_requisitions/add', methods=['GET', 'POST'])
@login_required
@require_capability('inventory.manage')
def add_material_requisition():
    """添加物料领用记录：选真实库存行，按品类决定是否审批。"""
    from app.main.forms import MaterialRequisitionRecordForm
    from app.models import MaterialRequisition, MaterialRequisitionItem, Employee
    from app.services import mes_service
    import json
    
    form = MaterialRequisitionRecordForm()
    
    if form.validate_on_submit():
        try:
            employee = Employee.query.get(form.employee_id.data)
            if not employee:
                flash('员工不存在', 'error')
                return render_template('main/material_requisition_form.html', form=form, title='创建物料领用记录')
            
            materials_data = json.loads(form.materials_data.data or '[]')
            if not materials_data:
                flash('请至少添加一项物料', 'error')
                return render_template('main/material_requisition_form.html', form=form, title='创建物料领用记录')

            need_approval = False
            parsed_lines = []
            for material_data in materials_data:
                mtype = material_data.get('material_type')
                mid = material_data.get('material_id')
                if not mtype or not mid:
                    flash('必须选择具体库存物料，不能手填品名', 'error')
                    return render_template('main/material_requisition_form.html', form=form, title='创建物料领用记录')
                mid = int(mid)
                qty = float(material_data.get('quantity') or 0)
                if qty <= 0:
                    flash('领用数量必须大于0', 'error')
                    return render_template('main/material_requisition_form.html', form=form, title='创建物料领用记录')
                if mes_service.get_stock_row(mtype, mid) is None:
                    flash('所选物料不存在', 'error')
                    return render_template('main/material_requisition_form.html', form=form, title='创建物料领用记录')
                if mes_service.line_requires_approval(mtype, mid):
                    need_approval = True
                parsed_lines.append({
                    'material_type': mtype,
                    'material_id': mid,
                    'quantity': qty,
                    'unit': material_data.get('unit') or '件',
                    'notes': material_data.get('notes') or '',
                })

            po_id = form.production_order_id.data or 0
            requisition = MaterialRequisition(
                employee_id=form.employee_id.data,
                department=employee.department or '',
                purpose=form.purpose.data,
                required_date=form.requisition_date.data,
                notes=form.notes.data,
                status='pending' if need_approval else 'approved',
                requested_date=datetime.now(),
                production_order_id=po_id if po_id else None,
            )
            db.session.add(requisition)
            db.session.flush()

            for line in parsed_lines:
                db.session.add(MaterialRequisitionItem(
                    requisition_id=requisition.id,
                    material_type=line['material_type'],
                    material_id=line['material_id'],
                    quantity=line['quantity'],
                    unit=line['unit'],
                    notes=line['notes'],
                    issued_quantity=0,
                ))

            db.session.add(AuditLog(
                user_id=current_user.id,
                action='创建物料领用记录',
                details=f'创建物料领用记录：{requisition.requisition_number} - {employee.name}',
                can_rollback=True,
                rollback_type='add',
                target_model='MaterialRequisition',
                target_id=requisition.id,
                new_data={
                    'requisition_number': requisition.requisition_number,
                    'employee_id': requisition.employee_id,
                    'status': requisition.status,
                    'purpose': requisition.purpose,
                }
            ))
            db.session.commit()
            flash('物料领用记录创建成功！' + ('待审批。' if need_approval else '免审，可直接发料。'), 'success')
            return redirect(url_for('main.material_requisition_detail', id=requisition.id))
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'创建物料领用记录失败: {str(e)}')
            flash(f'创建失败：{str(e)}', 'danger')
    
    return render_template('main/material_requisition_form.html', form=form, title='创建物料领用记录')

@bp.route('/material_requisitions/<int:id>')
@login_required
@require_capability('inventory.manage')
def material_requisition_detail(id):
    """物料领用详情"""
    from app.models import MaterialRequisition
    requisition = MaterialRequisition.query.get_or_404(id)
    return render_template('main/material_requisition_detail.html', requisition=requisition)


@bp.route('/api/material_requisitions/<int:id>/issued-items')
@login_required
@require_capability('inventory.manage')
def api_requisition_issued_items(id):
    from app.models import MaterialRequisition
    try:
        requisition = MaterialRequisition.query.get_or_404(id)
        if requisition.status != 'completed':
            return jsonify({'success': False, 'message': '只能关联已发料的领用单'}), 400
        data = []
        for item in requisition.items.all():
            data.append({
                'id': item.id,
                'material_type': item.material_type,
                'material_id': item.material_id,
                'material_name': item.material_name,
                'issued_quantity': item.issued_quantity or 0,
                'unit': item.unit,
            })
        return jsonify({'success': True, 'data': data, 'employee_id': requisition.employee_id,
                        'department': requisition.department})
    except Exception as e:
        _reraise_http(e)
        return jsonify({'success': False, 'message': str(e)}), 500


@bp.route('/material_requisitions/<int:id>/approve', methods=['POST'])
@login_required
@require_capability('inventory.manage')
def approve_material_requisition(id):
    from app.models import MaterialRequisition
    dest = url_for('main.material_requisition_detail', id=id)
    try:
        requisition = MaterialRequisition.query.get_or_404(id)
        if not requisition.can_approve:
            return _warehouse_reply(False, '当前状态不可审批', dest)
        requisition.status = 'approved'
        requisition.approved_by = current_user.id
        requisition.approved_at = datetime.utcnow()
        db.session.add(AuditLog(
            user_id=current_user.id, action='审批物料领用',
            details=f'通过领用单 {requisition.requisition_number}',
            target_model='MaterialRequisition', target_id=requisition.id,
        ))
        db.session.commit()
        return _warehouse_reply(True, '审批通过', dest)
    except Exception as e:
        _reraise_http(e)
        db.session.rollback()
        current_app.logger.error(f'审批领用单失败: {str(e)}')
        return _warehouse_reply(False, f'审批失败：{str(e)}', dest)


@bp.route('/material_requisitions/<int:id>/reject', methods=['POST'])
@login_required
@require_capability('inventory.manage')
def reject_material_requisition(id):
    from app.models import MaterialRequisition
    dest = url_for('main.material_requisition_detail', id=id)
    try:
        requisition = MaterialRequisition.query.get_or_404(id)
        if not requisition.can_approve:
            return _warehouse_reply(False, '当前状态不可拒绝', dest)
        requisition.status = 'rejected'
        requisition.approved_by = current_user.id
        requisition.approved_at = datetime.utcnow()
        db.session.add(AuditLog(
            user_id=current_user.id, action='拒绝物料领用',
            details=f'拒绝领用单 {requisition.requisition_number}',
            target_model='MaterialRequisition', target_id=requisition.id,
        ))
        db.session.commit()
        return _warehouse_reply(True, '已拒绝', dest)
    except Exception as e:
        _reraise_http(e)
        db.session.rollback()
        current_app.logger.error(f'拒绝领用单失败: {str(e)}')
        return _warehouse_reply(False, f'操作失败：{str(e)}', dest)


@bp.route('/material_requisitions/<int:id>/issue', methods=['POST'])
@login_required
@require_capability('inventory.manage')
def issue_material_requisition(id):
    from app.models import MaterialRequisition
    from app.services import mes_service
    dest = url_for('main.material_requisition_detail', id=id)
    try:
        requisition = MaterialRequisition.query.get_or_404(id)
        mes_service.issue_requisition(requisition, current_user.id)
        db.session.add(AuditLog(
            user_id=current_user.id, action='领用发料',
            details=f'发料 {requisition.requisition_number}',
            can_rollback=False, target_model='MaterialRequisition', target_id=requisition.id,
        ))
        db.session.commit()
        return _warehouse_reply(True, '发料成功，已扣减库存', dest)
    except ValueError as e:
        db.session.rollback()
        return _warehouse_reply(False, str(e), dest)
    except Exception as e:
        _reraise_http(e)
        db.session.rollback()
        current_app.logger.error(f'发料失败: {str(e)}')
        return _warehouse_reply(False, f'发料失败：{str(e)}', dest)


@bp.route('/material_requisitions/<int:id>/cancel', methods=['POST'])
@login_required
@require_capability('inventory.manage')
def cancel_material_requisition(id):
    from app.models import MaterialRequisition
    dest = url_for('main.material_requisition_detail', id=id)
    try:
        requisition = MaterialRequisition.query.get_or_404(id)
        if not requisition.can_cancel:
            return _warehouse_reply(False, '当前状态不可取消', dest)
        requisition.status = 'cancelled'
        db.session.add(AuditLog(
            user_id=current_user.id, action='取消物料领用',
            details=f'取消领用单 {requisition.requisition_number}',
            target_model='MaterialRequisition', target_id=requisition.id,
        ))
        db.session.commit()
        return _warehouse_reply(True, '已取消', dest)
    except Exception as e:
        _reraise_http(e)
        db.session.rollback()
        current_app.logger.error(f'取消领用单失败: {str(e)}')
        return _warehouse_reply(False, f'取消失败：{str(e)}', dest)



# ==================== 物料归还管理 ====================

@bp.route('/material_returns')
@login_required
@require_capability('inventory.manage')
@handle_pagination_args
def manage_material_returns():
    """物料归还管理"""
    from app.main.forms import MaterialReturnSearchForm
    from app.models import MaterialReturn, Employee
    
    form = MaterialReturnSearchForm()
    
    # 构建查询
    query = MaterialReturn.query.join(Employee)
    
    # 处理搜索条件
    if request.method == 'POST' and form.validate_on_submit():
        if form.search.data:
            search_term = f"%{form.search.data}%"
            query = query.filter(
                db.or_(
                    MaterialReturn.return_number.like(search_term),
                    Employee.name.like(search_term),
                    MaterialReturn.department.like(search_term),
                    MaterialReturn.return_reason.like(search_term)
                )
            )
        
        if form.status.data:
            query = query.filter(MaterialReturn.status == form.status.data)
        
        if form.department.data:
            query = query.filter(MaterialReturn.department.like(f"%{form.department.data}%"))
        
        if form.employee_id.data and form.employee_id.data != 0:
            query = query.filter(MaterialReturn.employee_id == form.employee_id.data)
        
        if form.returned_date_start.data:
            query = query.filter(MaterialReturn.returned_date >= form.returned_date_start.data)
        
        if form.returned_date_end.data:
            query = query.filter(MaterialReturn.returned_date <= form.returned_date_end.data)
    
    # 排序和分页
    query = query.order_by(MaterialReturn.returned_date.desc())
    
    # 分页（统一走 @handle_pagination_args 的白名单口径）
    page = request.validated_page
    per_page = request.validated_per_page
    
    returns = query.paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    # 统计数据
    total_count = MaterialReturn.query.count()
    pending_count = MaterialReturn.query.filter_by(status='pending').count()
    confirmed_count = MaterialReturn.query.filter_by(status='confirmed').count()
    
    return render_template('main/material_returns.html',
                         returns=returns,
                         form=form,
                         total_count=total_count,
                         pending_count=pending_count,
                         confirmed_count=confirmed_count)


@bp.route('/material_returns/add', methods=['GET', 'POST'])
@login_required
@require_capability('inventory.manage')
def add_material_return():
    """新建归还单，必须关联已发料领用单，数量不超过已发数量。"""
    from app.main.forms import MaterialReturnForm
    from app.models import MaterialReturn, MaterialReturnItem, Employee, MaterialRequisition
    import json

    form = MaterialReturnForm()
    if form.validate_on_submit():
        try:
            orig_id = form.original_requisition_id.data or 0
            if not orig_id:
                flash('请选择原领用单', 'error')
                return render_template('main/material_return_form.html', form=form, title='新建物料归还')
            orig = MaterialRequisition.query.get(orig_id)
            if not orig or orig.status != 'completed':
                flash('只能关联已发料完成的领用单', 'error')
                return render_template('main/material_return_form.html', form=form, title='新建物料归还')
            employee = Employee.query.get(form.employee_id.data)
            if not employee:
                flash('员工不存在', 'error')
                return render_template('main/material_return_form.html', form=form, title='新建物料归还')
            lines = json.loads(form.materials_data.data or '[]')
            if not lines:
                flash('请至少添加一项归还明细', 'error')
                return render_template('main/material_return_form.html', form=form, title='新建物料归还')

            issued_map = {}
            for it in orig.items.all():
                key = (it.material_type, it.material_id)
                issued_map[key] = issued_map.get(key, 0) + (it.issued_quantity or 0)
            already = {}
            for ret in orig.returns:
                if ret.status == 'rejected':
                    continue
                for it in ret.items.all():
                    key = (it.material_type, it.material_id)
                    already[key] = already.get(key, 0) + it.quantity

            parsed = []
            for line in lines:
                mtype = line.get('material_type')
                mid = int(line.get('material_id') or 0)
                qty = float(line.get('quantity') or 0)
                if not mtype or not mid or qty <= 0:
                    flash('归还明细不完整', 'error')
                    return render_template('main/material_return_form.html', form=form, title='新建物料归还')
                key = (mtype, mid)
                remain = issued_map.get(key, 0) - already.get(key, 0)
                if qty > remain + 1e-9:
                    flash(f'{line.get("material_name") or "物料"} 归还数量不能超过已发剩余 {remain}', 'error')
                    return render_template('main/material_return_form.html', form=form, title='新建物料归还')
                parsed.append({
                    'material_type': mtype, 'material_id': mid, 'quantity': qty,
                    'condition': line.get('condition') or 'good',
                    'unit': line.get('unit') or '件',
                    'notes': line.get('notes') or '',
                })
                already[key] = already.get(key, 0) + qty

            ret = MaterialReturn(
                employee_id=form.employee_id.data,
                department=form.department.data or employee.department or '',
                return_reason=form.return_reason.data,
                original_requisition_id=orig.id,
                status='pending',
                returned_date=form.returned_date.data or datetime.utcnow(),
                notes=form.notes.data,
            )
            db.session.add(ret)
            db.session.flush()
            for line in parsed:
                db.session.add(MaterialReturnItem(
                    return_id=ret.id, **line
                ))
            db.session.add(AuditLog(
                user_id=current_user.id, action='创建物料归还',
                details=f'创建归还单 {ret.return_number}',
                can_rollback=True, rollback_type='add',
                target_model='MaterialReturn', target_id=ret.id,
            ))
            db.session.commit()
            flash('归还单已提交，等待确认回库', 'success')
            return redirect(url_for('main.material_return_detail', id=ret.id))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'创建归还单失败: {str(e)}')
            flash(f'创建失败：{str(e)}', 'danger')
    return render_template('main/material_return_form.html', form=form, title='新建物料归还')


@bp.route('/material_returns/<int:id>')
@login_required
@require_capability('inventory.manage')
def material_return_detail(id):
    from app.models import MaterialReturn
    ret = MaterialReturn.query.get_or_404(id)
    return render_template('main/material_return_detail.html', ret=ret)


@bp.route('/material_returns/<int:id>/confirm', methods=['POST'])
@login_required
@require_capability('inventory.manage')
def confirm_material_return(id):
    from app.models import MaterialReturn
    from app.services import mes_service
    dest = url_for('main.material_return_detail', id=id)
    try:
        ret = MaterialReturn.query.get_or_404(id)
        mes_service.confirm_return(ret, current_user.id)
        notes = (request.get_json() or {}).get('notes') if request.is_json else request.form.get('notes')
        if notes:
            ret.notes = ((ret.notes or '') + '\n确认：' + notes).strip()
        db.session.add(AuditLog(
            user_id=current_user.id, action='确认物料归还',
            details=f'确认归还单 {ret.return_number}，完好项已回库',
            target_model='MaterialReturn', target_id=ret.id,
        ))
        db.session.commit()
        return _warehouse_reply(True, '已确认，完好物料已回库', dest)
    except ValueError as e:
        db.session.rollback()
        return _warehouse_reply(False, str(e), dest)
    except Exception as e:
        _reraise_http(e)
        db.session.rollback()
        current_app.logger.error(f'确认归还失败: {str(e)}')
        return _warehouse_reply(False, f'确认失败：{str(e)}', dest)


@bp.route('/material_returns/<int:id>/reject', methods=['POST'])
@login_required
@require_capability('inventory.manage')
def reject_material_return(id):
    from app.models import MaterialReturn
    dest = url_for('main.material_return_detail', id=id)
    try:
        ret = MaterialReturn.query.get_or_404(id)
        if not ret.can_confirm:
            return _warehouse_reply(False, '当前状态不可拒绝', dest)
        ret.status = 'rejected'
        ret.confirmed_by = current_user.id
        ret.confirmed_at = datetime.utcnow()
        db.session.add(AuditLog(
            user_id=current_user.id, action='拒绝物料归还',
            details=f'拒绝归还单 {ret.return_number}',
            target_model='MaterialReturn', target_id=ret.id,
        ))
        db.session.commit()
        return _warehouse_reply(True, '已拒绝归还', dest)
    except Exception as e:
        _reraise_http(e)
        db.session.rollback()
        current_app.logger.error(f'拒绝归还失败: {str(e)}')
        return _warehouse_reply(False, f'操作失败：{str(e)}', dest)


# ==================== 库存盘点管理 ====================

@bp.route('/inventory_counts')
@login_required
@require_capability('inventory.manage')
@handle_pagination_args
def manage_inventory_counts():
    """库存盘点管理"""
    from app.main.forms import InventoryCountSearchForm
    from app.models import InventoryCount
    
    form = InventoryCountSearchForm()
    
    # 构建查询
    query = InventoryCount.query
    
    # 处理搜索条件
    if request.method == 'POST' and form.validate_on_submit():
        if form.search.data:
            search_term = f"%{form.search.data}%"
            query = query.filter(
                db.or_(
                    InventoryCount.count_number.like(search_term),
                    InventoryCount.count_name.like(search_term)
                )
            )
        
        if form.status.data:
            query = query.filter(InventoryCount.status == form.status.data)
        
        if form.count_type.data:
            query = query.filter(InventoryCount.count_type == form.count_type.data)
        
        if form.count_scope.data:
            query = query.filter(InventoryCount.count_scope == form.count_scope.data)
        
        if form.planned_date_start.data:
            query = query.filter(InventoryCount.planned_date >= form.planned_date_start.data)
        
        if form.planned_date_end.data:
            query = query.filter(InventoryCount.planned_date <= form.planned_date_end.data)
    
    # 排序和分页
    query = query.order_by(InventoryCount.planned_date.desc())
    
    # 分页（统一走 @handle_pagination_args 的白名单口径）
    page = request.validated_page
    per_page = request.validated_per_page
    
    counts = query.paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    # 统计数据
    total_count = InventoryCount.query.count()
    in_progress_count = InventoryCount.query.filter_by(status='counting').count()
    completed_count = InventoryCount.query.filter_by(status='completed').count()
    planning_count = InventoryCount.query.filter_by(status='planning').count()
    
    return render_template('main/inventory_counts.html',
                         counts=counts,
                         form=form,
                         total_count=total_count,
                         in_progress_count=in_progress_count,
                         completed_count=completed_count,
                         planning_count=planning_count)


@bp.route('/inventory_counts/add', methods=['GET', 'POST'])
@login_required
@require_capability('inventory.manage')
def add_inventory_count():
    from app.main.forms import InventoryCountForm
    from app.models import InventoryCount
    from app.services import mes_service

    form = InventoryCountForm()
    if form.validate_on_submit():
        try:
            count = InventoryCount(
                count_name=form.count_name.data,
                count_type=form.count_type.data,
                count_scope=form.count_scope.data,
                warehouse_location=form.warehouse_location.data,
                planned_date=form.planned_date.data,
                count_team=form.count_team.data or [],
                notes=form.notes.data,
                status='planning',
                created_by=current_user.id,
            )
            db.session.add(count)
            db.session.flush()
            mes_service.snapshot_inventory_count(count)
            db.session.add(AuditLog(
                user_id=current_user.id, action='创建库存盘点',
                details=f'创建盘点 {count.count_number}，快照 {count.total_items} 行',
                can_rollback=True, rollback_type='add',
                target_model='InventoryCount', target_id=count.id,
            ))
            db.session.commit()
            flash('盘点单已创建并生成库存快照', 'success')
            return redirect(url_for('main.inventory_count_detail', id=count.id))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'创建盘点失败: {str(e)}')
            flash(f'创建失败：{str(e)}', 'danger')
    return render_template('main/inventory_count_form.html', form=form, title='新建库存盘点')


@bp.route('/inventory_counts/<int:id>')
@login_required
@require_capability('inventory.manage')
def inventory_count_detail(id):
    from app.models import InventoryCount
    count = InventoryCount.query.get_or_404(id)
    return render_template('main/inventory_count_detail.html', count=count)


@bp.route('/inventory_counts/<int:id>/start', methods=['POST'])
@login_required
@require_capability('inventory.manage')
def start_inventory_count(id):
    from app.models import InventoryCount
    dest = url_for('main.inventory_count_detail', id=id)
    try:
        count = InventoryCount.query.get_or_404(id)
        if not count.can_start:
            return _warehouse_reply(False, '当前状态不可开始盘点', dest)
        count.status = 'counting'
        count.start_date = datetime.utcnow()
        db.session.commit()
        return _warehouse_reply(True, '已开始盘点', dest)
    except Exception as e:
        _reraise_http(e)
        db.session.rollback()
        return _warehouse_reply(False, f'操作失败：{str(e)}', dest)


@bp.route('/inventory_counts/<int:id>/record', methods=['POST'])
@login_required
@require_capability('inventory.manage')
def record_inventory_count(id):
    from app.models import InventoryCount, InventoryCountItem
    dest = url_for('main.inventory_count_detail', id=id)
    try:
        count = InventoryCount.query.get_or_404(id)
        if count.status != 'counting':
            return _warehouse_reply(False, '仅盘点中的单据可以录入实盘', dest)
        payload = request.get_json(silent=True) or {}
        items_payload = payload.get('items')
        if items_payload is None:
            items_payload = []
            for item in count.items.all():
                raw = request.form.get(f'actual_{item.id}')
                if raw is None or str(raw).strip() == '':
                    continue
                items_payload.append({
                    'id': item.id,
                    'actual_quantity': raw,
                    'variance_reason': request.form.get(f'reason_{item.id}', ''),
                })
        for row in items_payload:
            item = InventoryCountItem.query.get(row.get('id'))
            if item is None or item.count_id != count.id:
                continue
            item.actual_quantity = float(row.get('actual_quantity'))
            item.variance_reason = row.get('variance_reason') or item.variance_reason
            item.counted_by = current_user.id
            item.counted_at = datetime.utcnow()
            item.calculate_variance()
        db.session.commit()
        return _warehouse_reply(True, '实盘数量已保存', dest)
    except Exception as e:
        _reraise_http(e)
        db.session.rollback()
        current_app.logger.error(f'录入盘点失败: {str(e)}')
        return _warehouse_reply(False, f'保存失败：{str(e)}', dest)


@bp.route('/inventory_counts/<int:id>/complete', methods=['POST'])
@login_required
@require_capability('inventory.manage')
def complete_inventory_count(id):
    from app.models import InventoryCount
    from app.services import mes_service
    dest = url_for('main.inventory_count_detail', id=id)
    try:
        count = InventoryCount.query.get_or_404(id)
        if not count.can_complete:
            return _warehouse_reply(False, '未盘完或当前状态不可完成', dest)
        mes_service.apply_inventory_count(count)
        db.session.add(AuditLog(
            user_id=current_user.id, action='完成库存盘点',
            details=f'完成盘点 {count.count_number} 并调账',
            can_rollback=False, target_model='InventoryCount', target_id=count.id,
        ))
        db.session.commit()
        return _warehouse_reply(True, '盘点完成，库存已按实盘调整', dest)
    except ValueError as e:
        db.session.rollback()
        return _warehouse_reply(False, str(e), dest)
    except Exception as e:
        _reraise_http(e)
        db.session.rollback()
        current_app.logger.error(f'完成盘点失败: {str(e)}')
        return _warehouse_reply(False, f'完成失败：{str(e)}', dest)


@bp.route('/inventory_counts/<int:id>/cancel', methods=['POST'])
@login_required
@require_capability('inventory.manage')
def cancel_inventory_count(id):
    from app.models import InventoryCount
    dest = url_for('main.inventory_count_detail', id=id)
    try:
        count = InventoryCount.query.get_or_404(id)
        if not count.can_cancel:
            return _warehouse_reply(False, '已调账或当前状态不可取消', dest)
        count.status = 'cancelled'
        db.session.add(AuditLog(
            user_id=current_user.id, action='取消库存盘点',
            details=f'取消盘点 {count.count_number}',
            target_model='InventoryCount', target_id=count.id,
        ))
        db.session.commit()
        return _warehouse_reply(True, '已取消盘点', dest)
    except Exception as e:
        _reraise_http(e)
        db.session.rollback()
        return _warehouse_reply(False, f'取消失败：{str(e)}', dest)

# ==================== API接口 ====================
@bp.route('/api/materials/search')
@login_required
@require_capability('inventory.manage')
def api_search_materials():
    """搜索物料API"""
    try:
        material_type = request.args.get('type', 'all')
        query = request.args.get('q', '')
        only_available = request.args.get('only_available', 'false').lower() == 'true'
        
        materials = []
        
        if material_type in ['all', 'raw']:
            from app.models import RawMaterial
            raw_query = RawMaterial.query.filter_by(is_archived=False)
            
            if only_available:
                raw_query = raw_query.filter(RawMaterial.quantity > 0, RawMaterial.status == 'in_stock')
            
            if query:
                raw_query = raw_query.filter(
                    db.or_(
                        RawMaterial.internal_number.like(f"%{query}%"),
                        RawMaterial.supplier.like(f"%{query}%"),
                        RawMaterial.supplier_number.like(f"%{query}%")
                    )
                )
            
            for material in raw_query.all():
                materials.append({
                    'id': material.id,
                    'type': 'raw',
                    'name': material.material_name,
                    'internal_number': material.internal_number,
                    'supplier': material.supplier,
                    'quantity': material.quantity,
                    'unit': '件',
                    'status': material.status
                })
        
        if material_type in ['all', 'consumable']:
            from app.models import Consumable
            consumable_query = Consumable.query.filter_by(is_archived=False)
            
            if only_available:
                consumable_query = consumable_query.filter(Consumable.quantity > 0, Consumable.status == 'in_stock')
            
            if query:
                consumable_query = consumable_query.filter(
                    db.or_(
                        Consumable.internal_number.like(f"%{query}%"),
                        Consumable.supplier.like(f"%{query}%"),
                        Consumable.supplier_number.like(f"%{query}%"),
                        Consumable.specification.like(f"%{query}%")
                    )
                )
            
            for material in consumable_query.all():
                materials.append({
                    'id': material.id,
                    'type': 'consumable',
                    'name': material.consumable_name,
                    'internal_number': material.internal_number,
                    'supplier': material.supplier,
                    'quantity': material.quantity,
                    'unit': material.unit,
                    'status': material.status
                })
        
        if material_type in ['all', 'finished']:
            from app.models import FinishedProduct
            finished_query = FinishedProduct.query.filter_by(is_archived=False)
            
            if only_available:
                finished_query = finished_query.filter(FinishedProduct.quantity > 0, FinishedProduct.status == 'in_stock')
            
            if query:
                finished_query = finished_query.filter(
                    db.or_(
                        FinishedProduct.product_number.like(f"%{query}%"),
                        FinishedProduct.drawing_number.like(f"%{query}%"),
                        FinishedProduct.model.like(f"%{query}%")
                    )
                )
            
            for material in finished_query.all():
                materials.append({
                    'id': material.id,
                    'type': 'finished',
                    'name': f"{material.product_number} - {material.model}",
                    'internal_number': material.product_number,
                    'supplier': '-',
                    'quantity': material.quantity,
                    'unit': '件',
                    'status': material.status
                })
        
        return jsonify({
            'success': True,
            'data': materials
        })
        
    except Exception as e:
        current_app.logger.error(f'搜索物料失败: {str(e)}')
        return jsonify({'success': False, 'message': f'搜索失败：{str(e)}'}), 500