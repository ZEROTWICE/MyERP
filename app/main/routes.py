from flask import render_template, redirect, url_for, flash, request, jsonify, current_app, send_file
from sqlalchemy.exc import SQLAlchemyError
from flask_login import login_required, current_user
from app import db
from app.models import Employee, ProcessPrice, ProductionRecord, BonusPenalty, AuditLog, ProcessPrice, User, TaskAssignment, SerialNumber, SalaryChange, CoefficientChange, EmployeeSalaryHistory, EmployeeCoefficientHistory, ProcessPriceGroup, FinishedProduct, RawMaterial, CodeRule, CodeGenerationLog, ProductionRecordMaterial
from datetime import datetime, timedelta
from . import bp
from app.main.forms import (
    EmployeeForm, ProcessPriceForm, ProductionRecordForm, BonusPenaltyForm,
    SalaryCalculationForm, AuditLogSearchForm, ProcessPriceSearchForm,
    ProductionRecordSearchForm, TaskAssignmentForm, TaskSearchForm,
    BonusPenaltySearchForm, ExportEmployeeForm, ExportProcessForm,
    ExportProductionRecordForm, ExportBonusPenaltyForm, ExportTaskForm
)
from sqlalchemy import desc, or_
from app.utils.excel_generator import ExcelGenerator
import os
import time
from werkzeug.utils import secure_filename
from werkzeug.datastructures import FileStorage
from typing import Optional
from flask import after_this_request
from functools import wraps
import tempfile
from flask_paginate import Pagination
import pandas as pd
from app.decorators import admin_required
import numpy as np
from werkzeug.datastructures import FileStorage
from typing import List, Dict, Any, Optional, Union
import shutil
from openpyxl import Workbook
import json

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

@bp.route('/')
@login_required
def index():
    if current_user.role == 'user':
        return redirect(url_for('main.user_dashboard'))
    elif current_user.role == 'admin':
        return render_template('main/admin_dashboard.html')
    else:
        flash('权限不足', 'danger')
        return redirect(url_for('main.user_dashboard'))

@bp.route('/user_dashboard')
@login_required
def user_dashboard():
    if current_user.role != 'user':
        return redirect(url_for('main.index'))
    
    # 获取当前用户的员工信息
    employee = Employee.query.filter_by(user_id=current_user.id).first()
    if not employee:
        flash('未找到员工信息', 'error')
        return redirect(url_for('main.index'))
    
    # 获取最近的任务（最多5个）
    recent_tasks = TaskAssignment.query.filter_by(employee_id=employee.id)\
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
    
    return render_template('main/user_dashboard.html',
                         employee=employee,
                         recent_tasks=recent_tasks,
                         recent_records=recent_records,
                         recent_bonuses=recent_bonuses)

@bp.route('/employees')
@login_required
@handle_pagination_args
def manage_employees():
    if current_user.role not in ['admin', 'hr']:
        flash('权限不足', 'danger')
        return redirect(url_for('main.index'))
    
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
def delete_employee(id):
    if not current_user.role == 'admin':
        return jsonify({'success': False, 'message': '权限不足'}), 403
    
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
def add_employee():
    if current_user.role not in ['admin', 'hr']:
        flash('权限不足', 'danger')
        return redirect(url_for('main.index'))
    
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
def edit_employee(id):
    if current_user.role not in ['admin', 'hr']:
        flash('权限不足', 'danger')
        return redirect(url_for('main.index'))
    
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
                    serial_number=SerialNumber.get_next_number(),
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
                    serial_number=SerialNumber.get_next_number(),
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
def add_process_price():
    """添加工序价格"""
    if current_user.role not in ['admin', 'hr']:
        flash('权限不足', 'danger')
        return redirect(url_for('main.index'))
    
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
    
    # 设置编码规则选项（初始为空）
    form.code_rule_id.choices = [(0, '请选择')]
    
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
                code_rule_id=form.code_rule_id.data if form.has_output.data else None,
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
def edit_process_price(id):
    if current_user.role not in ['admin', 'hr']:
        flash('权限不足', 'danger')
        return redirect(url_for('main.index'))
    
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
    
    # 根据当前产出类型设置编码规则选项
    if process_price.output_type == 'finished':
        form.code_rule_id.choices = [(0, '请选择')] + [(r.id, r.name) for r in finished_rules]
    elif process_price.output_type == 'raw':
        form.code_rule_id.choices = [(0, '请选择')] + [(r.id, r.name) for r in raw_rules]
    else:
        form.code_rule_id.choices = [(0, '请选择')]
    
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
            process_price.code_rule_id = form.code_rule_id.data if form.has_output.data else None
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
    
    # GET请求时，填充表单数据
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
        form.output_type.data = process_price.output_type
        form.code_rule_id.data = process_price.code_rule_id
        form.needs_inspection.data = process_price.needs_inspection
        
        # 如果是小计，填充已包含的工序
        if process_price.price_type == 'subtotal':
            included_process_ids = [group.process_id for group in ProcessPriceGroup.query.filter_by(subtotal_id=id).all()]
            form.included_processes.data = included_process_ids
    
    return render_template('main/process_price_form.html', 
                         form=form, 
                         title='编辑工序价格', 
                         employee=process_price,
                         finished_rules_json=finished_rules_json,
                         raw_rules_json=raw_rules_json)

@bp.route('/process_price/<int:id>', methods=['DELETE'])
@login_required
def delete_process_price(id):
    if not current_user.role == 'admin':
        return jsonify({'success': False, 'message': '权限不足'}), 403
    
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
@handle_pagination_args
def manage_production_records():
    """管理生产记录"""
    form = ProductionRecordForm()
    search_form = ProductionRecordSearchForm()
    
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

    # 获取可用的原材料
    raw_materials = RawMaterial.query.filter(RawMaterial.quantity > 0).all()
    form.raw_material_id.choices = [(0, '请选择原材料')] + [(m.id, f"{m.material_name} (库存: {m.quantity})") for m in raw_materials]

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
                raw_material_id=form.raw_material_id.data if form.raw_material_id.data != 0 else None,
                raw_material_quantity=form.raw_material_quantity.data,
                notes=form.notes.data
            )
            
            if form.inspector.data:
                # 如果提供了检验员信息，创建成品记录
                finished_product = FinishedProduct(
                    product_number=SerialNumber.get_next_number('FP'),
                    inspector=form.inspector.data
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
                            raw_material.quantity -= float(quantity)
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
    
    if search_form.search.data:
        search_term = f"%{search_form.search.data}%"
        query = query.filter(db.or_(
            Employee.name.like(search_term),
            Employee.employee_id.like(search_term),
            ProcessPrice.process_code.like(search_term),
            ProcessPrice.process_name.like(search_term),
            ProcessPrice.component.like(search_term),
            ProcessPrice.drawing_no.like(search_term),
            ProcessPrice.model_no.like(search_term)
        ))

    # 处理排序
    sort_column = request.args.get('sort', 'date')
    sort_direction = request.args.get('direction', 'desc')
    
    # 定义排序映射
    sort_mapping = {
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
                         current_direction=sort_direction)

@bp.route('/delete_production_record/<int:id>', methods=['DELETE'])
@login_required
def delete_production_record(id):
    if not current_user.role in ['admin', 'hr']:
        return jsonify({'success': False, 'message': '权限不足'}), 403
    
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
                material.raw_material.quantity += material.quantity
        
        # 如果使用旧方式存储了原材料，也需要恢复
        if record.raw_material and record.raw_material_quantity:
            # 保存原材料数据用于回滚
            old_data['raw_material_id'] = record.raw_material_id
            old_data['raw_material_quantity'] = record.raw_material_quantity
            
            # 恢复库存
            record.raw_material.quantity += record.raw_material_quantity
        
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
@handle_pagination_args
def manage_bonus_penalties():
    """管理奖惩记录"""
    if current_user.role not in ['admin', 'hr']:
        flash('权限不足', 'danger')
        return redirect(url_for('main.index'))
    
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
def delete_bonus_penalty(id):
    if not current_user.role in ['admin', 'hr']:
        return jsonify({'success': False, 'message': '权限不足'}), 403
    
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
def edit_bonus_penalty(id):
    if current_user.role not in ['admin', 'hr']:
        flash('权限不足', 'danger')
        return redirect(url_for('main.index'))
    
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
            db.session.rollback()
            flash('修改失败，请重试', 'danger')
            return redirect(url_for('main.manage_bonus_penalties'))
    return render_template('main/edit_bonus_penalty.html', form=form, record=record)

@bp.route('/bonus_penalties/add', methods=['POST'])
@login_required
def add_bonus_penalty():
    """添加奖金/罚款记录"""
    if current_user.role not in ['admin', 'hr']:
        return jsonify({'success': False, 'message': '权限不足'}), 403
    
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
def salary_calculation():
    if current_user.role not in ['admin', 'accountant']:
        flash('权限不足')
        return redirect(url_for('main.index'))
    
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
def view_audit_logs():
    if current_user.role != 'admin':
        flash('权限不足', 'danger')
        return redirect(url_for('main.index'))
    
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
    
    # 分页
    page = request.args.get('page', 1, type=int)
    pagination = query.paginate(page=page, per_page=20, error_out=False)
    logs = pagination.items
    
    return render_template('main/audit_logs.html', 
                         form=form, 
                         logs=logs, 
                         pagination=pagination)

@bp.route('/employees/template')
@login_required
def download_employee_template():
    """下载员工导入模板"""
    if current_user.role not in ['admin', 'hr']:
        flash('权限不足', 'danger')
        return redirect(url_for('main.index'))
    
    temp_path = None
    try:
        wb = ExcelGenerator.create_employee_template()
        filename = 'employee_template.xlsx'
        temp_path = os.path.join(current_app.config['TEMP_FOLDER'], filename)
        
        # 保存并关闭工作簿
        wb.save(temp_path)
        wb.close()
        
        # 确保文件写入完成
        time.sleep(0.1)
        
        return send_file(
            temp_path,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass
        flash(f'下载模板失败：{str(e)}', 'danger')
        return redirect(url_for('main.manage_employees'))
    finally:
        # 确保在请求结束后删除临时文件
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass

@bp.route('/employees/import', methods=['POST'])
@login_required
def import_employees():
    """导入员工数据"""
    if current_user.role not in ['admin', 'hr']:
        return jsonify({'success': False, 'message': '权限不足'})
    
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
        
        employee_data = ExcelGenerator.parse_employee_data(temp_path)
        os.remove(temp_path)  # 删除临时文件
        
        success_count = 0
        error_messages = []
        
        for data in employee_data:
            try:
                # 检查工号是否已存在
                if Employee.query.filter_by(employee_id=data['employee_id']).first():
                    error_messages.append(f"工号 {data['employee_id']} 已存在")
                    continue
                
                # 检查用户名是否已存在
                if User.query.filter_by(username=data['employee_id']).first():
                    error_messages.append(f"用户名 {data['employee_id']} 已存在")
                    continue
                
                # 创建用户账号
                user = User(username=data['employee_id'], role='user')
                user.set_password(data['employee_id'])  # 初始密码与工号相同
                db.session.add(user)
                
                # 创建员工记录
                employee = Employee(
                    global_sn=SerialNumber.get_next_number(),
                    employee_id=data['employee_id'],
                    name=data['name'],
                    position=data['position'],
                    department=data['department'],
                    base_salary=data['base_salary'],
                    coefficient=data['coefficient'],
                    user=user
                )
                db.session.add(employee)
                success_count += 1
                
            except Exception as e:
                error_messages.append(f"处理 {data['employee_id']} 时出错: {str(e)}")
        
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
        
        message = f'成功导入 {success_count} 条记录'
        if error_messages:
            message += f'，{len(error_messages)} 条记录导入失败：\n' + '\n'.join(error_messages)
        
        return jsonify({
            'success': True,
            'message': message
        })
        
    except Exception as e:
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
def export_employees():
    form = ExportEmployeeForm()
    if form.validate_on_submit():
        query = Employee.query
        if form.department.data:
            query = query.filter(Employee.department == form.department.data)
        if form.position.data:
            query = query.filter(Employee.position == form.position.data)
        if form.status.data:
            query = query.filter(Employee.status == form.status.data)
        
        employees = query.all()
        wb = ExcelGenerator.export_employees(employees)
        
        temp_path = None
    try:
        # 创建临时文件
        fd, temp_path = tempfile.mkstemp(suffix='.xlsx')
        # 关闭文件描述符
        os.close(fd)
        # 保存Excel文件
        wb.save(temp_path)
        # 发送文件
        return send_file(
            temp_path,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'employees_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        )
    except Exception as e:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass
        flash(f'导出失败：{str(e)}', 'danger')
        return redirect(url_for('main.manage_employees'))
    finally:
        # 确保在请求结束后删除临时文件
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass

    return render_template('main/export_form.html', title='导出员工数据', form=form)

@bp.route('/process_prices/template')
@login_required
def download_process_price_template():
    """下载工序价格导入模板"""
    if current_user.role not in ['admin', 'hr']:
        flash('权限不足', 'danger')
        return redirect(url_for('main.index'))
    
    temp_path = None
    try:
        wb = ExcelGenerator.create_process_price_template()
        filename = 'process_price_template.xlsx'
        temp_path = os.path.join(current_app.config['TEMP_FOLDER'], filename)
        
        # 保存并关闭工作簿
        wb.save(temp_path)
        wb.close()
        
        # 确保文件写入完成
        time.sleep(0.1)
        
        return send_file(
            temp_path,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass
        flash(f'下载模板失败：{str(e)}', 'danger')
        return redirect(url_for('main.process_prices'))
    finally:
        # 确保在请求结束后删除临时文件
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass

@bp.route('/process_prices/import', methods=['POST'])
@login_required
def import_process_prices():
    """导入工序价格数据"""
    if current_user.role not in ['admin', 'hr']:
        return jsonify({'success': False, 'message': '权限不足'})
    
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
        
        process_data = ExcelGenerator.parse_process_price_data(temp_path)
        os.remove(temp_path)  # 删除临时文件
        
        success_count = 0
        error_messages = []
        
        # 第一遍：处理普通工序
        normal_processes = {}  # 用于存储导入的普通工序，以便后续建立小计关联
        
        for data in process_data:
            if data['price_type'] != 'subtotal':
                try:
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
                            version=1,  # 新工序的初始版本为1
                            is_current=True,  # 新工序默认为当前生效
                            price_type='normal'
                    )
                    db.session.add(process)
                    db.session.flush()  # 获取ID
                            
                    normal_processes[data['process_code']] = process.id
                    success_count += 1
                    
                except Exception as e:
                    error_messages.append(f"处理普通工序 {data['process_code']} 时出错: {str(e)}")
        
        # 提交普通工序，以便后续小计能找到
        db.session.commit()
        
        # 第二遍：处理小计工序
        for data in process_data:
            if data['price_type'] == 'subtotal':
                try:
                    # 查找包含的普通工序
                    included_process_ids = []
                    
                    # 首先查找本次导入的工序
                    for code in data['included_processes']:
                        if code in normal_processes:
                            included_process_ids.append(normal_processes[code])
                        else:
                            # 查找数据库中已有的工序
                            existing_process = ProcessPrice.query.filter_by(process_code=code, price_type='normal', is_current=True).first()
                            if existing_process:
                                included_process_ids.append(existing_process.id)
                    
                    if not included_process_ids:
                        error_messages.append(f"小计工序 {data['process_code']} 没有找到有效的包含工序")
                        continue
                    
                    # 计算小计总价
                    total_price = 0
                    for pid in included_process_ids:
                        process = ProcessPrice.query.get(pid)
                        if process:
                            total_price += process.price
                    
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
                        version=1,  # 新工序的初始版本为1
                        is_current=True,  # 新工序默认为当前生效
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
                    error_messages.append(f"处理小计工序 {data['process_code']} 时出错: {str(e)}")
        
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
        
        message = f'成功导入 {success_count} 条记录'
        if error_messages:
            message += f'，{len(error_messages)} 条记录导入失败：\n' + '\n'.join(error_messages)
        
        return jsonify({
            'success': True,
            'message': message
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'导入失败：{str(e)}'})

@bp.route('/process_prices/export', methods=['GET', 'POST'])
@login_required
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
        
        temp_path = None
    try:
            # 创建临时文件
        fd, temp_path = tempfile.mkstemp(suffix='.xlsx')
            # 关闭文件描述符
        os.close(fd)
            # 保存Excel文件
        wb.save(temp_path)
            # 发送文件
        return send_file(
            temp_path,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
                download_name=f'processes_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        )
    except Exception as e:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass
        flash(f'导出失败：{str(e)}', 'danger')
        return redirect(url_for('main.process_prices'))
    finally:
            # 确保在请求结束后删除临时文件
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass
    
    return render_template('main/export_form.html', title='导出工序数据', form=form)

@bp.route('/production_records/template')
@login_required
def download_production_record_template():
    """下载生产记录导入模板"""
    if current_user.role not in ['admin', 'hr']:
        flash('权限不足', 'danger')
        return redirect(url_for('main.index'))
    
    temp_path = None
    try:
        wb = ExcelGenerator.create_production_record_template()
        filename = 'production_record_template.xlsx'
        temp_path = os.path.join(current_app.config['TEMP_FOLDER'], filename)
        
        # 保存并关闭工作簿
        wb.save(temp_path)
        wb.close()
        
        # 确保文件写入完成
        time.sleep(0.1)
        
        return send_file(
            temp_path,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass
        flash(f'下载模板失败：{str(e)}', 'danger')
        return redirect(url_for('main.manage_production_records'))
    finally:
        # 确保在请求结束后删除临时文件
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass

@bp.route('/production_records/import', methods=['POST'])
@login_required
def import_production_records():
    """导入生产记录数据"""
    if current_user.role not in ['admin', 'hr']:
        return jsonify({'success': False, 'message': '权限不足'})
    
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
            fd, temp_path = tempfile.mkstemp(suffix='.xlsx')
            # 关闭文件描述符
            os.close(fd)
            # 保存Excel文件
            wb.save(temp_path)
            # 发送文件
            return send_file(
                temp_path,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name=f'production_records_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
            )
        except Exception as e:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass
            flash(f'导出失败：{str(e)}', 'danger')
            return redirect(url_for('main.manage_production_records'))
        finally:
            # 确保在请求结束后删除临时文件
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass
    
    return render_template('main/export_form.html', form=form, title='导出生产记录')

@bp.route('/bonus_penalties/export', methods=['GET', 'POST'])
@login_required
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
            fd, temp_path = tempfile.mkstemp(suffix='.xlsx')
            # 关闭文件描述符
            os.close(fd)
            # 保存Excel文件
            wb.save(temp_path)
            # 发送文件
            return send_file(
                temp_path,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name=f'bonus_penalties_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
            )
        except Exception as e:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass
            flash(f'导出失败：{str(e)}', 'danger')
            return redirect(url_for('main.manage_bonus_penalties'))
        finally:
            # 确保在请求结束后删除临时文件
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass
    
    return render_template('main/export_form.html', form=form, title='导出奖惩记录')

@bp.route('/tasks', methods=['GET', 'POST'])
@login_required
@handle_pagination_args
def manage_tasks():
    """管理任务分配"""
    if current_user.role not in ['admin', 'hr']:
        flash('权限不足', 'danger')
        return redirect(url_for('main.index'))
    
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
    
    if request.args.get('status'):
        query = query.filter(TaskAssignment.status == request.args.get('status'))
    
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
                assigned_date=datetime.now().date()  # 设置分配日期
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
    search_form.status.data = request.args.get('status', '')
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
def update_task_status(id):
    """更新任务状态"""
    try:
        task = TaskAssignment.query.get_or_404(id)
        
        # 检查权限：管理员可以更新所有任务，普通用户只能更新自己的任务
        if current_user.role not in ['admin', 'hr']:
            # 获取当前用户的员工记录
            employee = Employee.query.filter_by(user_id=current_user.id).first()
            if not employee or employee.id != task.employee_id:
                return jsonify({'success': False, 'message': '权限不足'}), 403
        
        # 保存旧数据用于回滚
        old_data = {
            'status': task.status,
            'completed_quantity': task.completed_quantity
        }
        
        # 更新状态（如果提供了）
        new_status = request.form.get('status')
        if new_status is not None:
            if new_status not in ['pending', 'in_progress', 'completed', 'cancelled']:
                return jsonify({'success': False, 'message': '无效的状态值'}), 400
            task.status = new_status
        
        # 更新完成数量（如果提供了）
        completed_quantity = request.form.get('completed_quantity', type=int)
        if completed_quantity is not None:
            if completed_quantity < 0:
                return jsonify({'success': False, 'message': '完成数量不能为负数'}), 400
            if completed_quantity > task.quantity:
                return jsonify({'success': False, 'message': '完成数量不能超过总数量'}), 400
            task.completed_quantity = completed_quantity
            
            # 根据完成数量自动更新状态
            if completed_quantity == 0:
                task.status = 'pending'
            elif completed_quantity == task.quantity:
                task.status = 'completed'
            elif completed_quantity < task.quantity:
                task.status = 'in_progress'
        
        # 记录审计日志
        log = AuditLog(
            user_id=current_user.id,
            action='更新任务状态',
            details=f'更新任务（ID：{task.id}）完成数量为 {task.completed_quantity}，状态为 {task.status}',
            can_rollback=True,
            rollback_type='edit',
            target_model='TaskAssignment',
            target_id=task.id,
            old_data=old_data,
            new_data={
                'status': task.status,
                'completed_quantity': task.completed_quantity
            }
        )
        db.session.add(log)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': '任务状态更新成功',
            'completion_rate': task.completion_rate
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'更新失败：{str(e)}'}), 500

@bp.route('/tasks/<int:id>', methods=['DELETE'])
@login_required
def delete_task(id):
    """删除任务"""
    if current_user.role not in ['admin', 'hr']:
        return jsonify({'success': False, 'message': '权限不足'}), 403
    
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
def download_bonus_penalty_template():
    """下载奖金/罚款导入模板"""
    if current_user.role not in ['admin', 'hr']:
        flash('权限不足', 'danger')
        return redirect(url_for('main.manage_bonus_penalties'))
    
    temp_path = None
    try:
        wb = ExcelGenerator.create_bonus_penalty_template()
        filename = 'bonus_penalty_template.xlsx'
        temp_path = os.path.join(current_app.config['TEMP_FOLDER'], filename)
        
        # 保存并关闭工作簿
        wb.save(temp_path)
        wb.close()
        
        # 确保文件写入完成
        time.sleep(0.1)
        
        return send_file(
            temp_path,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass
        flash(f'下载模板失败：{str(e)}', 'danger')
        return redirect(url_for('main.manage_bonus_penalties'))
    finally:
        # 确保在请求结束后删除临时文件
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass

@bp.route('/bonus_penalties/import', methods=['POST'])
@login_required
def import_bonus_penalties():
    """导入奖金/罚款数据"""
    if current_user.role not in ['admin', 'hr']:
        return jsonify({'success': False, 'message': '权限不足'})
    
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
        
        for data in record_data:
            try:
                # 查找员工
                employee = Employee.query.filter_by(employee_id=data['employee_id']).first()
                if not employee:
                    error_messages.append(f"员工工号 {data['employee_id']} 不存在")
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
                    date=data['date'],
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
def download_task_template():
    """下载任务导入模板"""
    if current_user.role not in ['admin', 'hr']:
        flash('权限不足', 'danger')
        return redirect(url_for('main.manage_tasks'))
    
    temp_path = None
    try:
        wb = ExcelGenerator.create_task_template()
        filename = 'task_template.xlsx'
        temp_path = os.path.join(current_app.config['TEMP_FOLDER'], filename)
        
        # 保存并关闭工作簿
        wb.save(temp_path)
        wb.close()
        
        # 确保文件写入完成
        time.sleep(0.1)
        
        return send_file(
            temp_path,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass
        flash(f'下载模板失败：{str(e)}', 'danger')
        return redirect(url_for('main.manage_tasks'))
    finally:
        # 确保在请求结束后删除临时文件
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass

@bp.route('/tasks/import', methods=['POST'])
@login_required
def import_tasks():
    """导入任务数据"""
    if current_user.role not in ['admin', 'hr']:
        return jsonify({'success': False, 'message': '权限不足'})
    
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
        
        for data in task_data:
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
                
                # 创建任务记录
                task = TaskAssignment(
                    global_sn=SerialNumber.get_next_number(),
                    employee_id=employee.id,
                    process_id=process.id,
                    quantity=data['quantity'],
                    target_date=data['target_date'],
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

@bp.route('/export_tasks', methods=['POST'])
@login_required
def export_tasks():
    if current_user.role not in ['admin', 'hr']:
        flash('权限不足', 'danger')
        return redirect(url_for('main.index'))
    
    form = ExportTaskForm()
    if form.validate_on_submit():
        try:
            # 构建查询
            query = TaskAssignment.query.join(Employee)
            
            # 处理搜索条件
            if form.employee_id.data:
                query = query.filter(TaskAssignment.employee_id == form.employee_id.data)
            
            if form.process_id.data:
                query = query.filter(TaskAssignment.process_id == form.process_id.data)
            
            if form.status.data:
                query = query.filter(TaskAssignment.status == form.status.data)
            
            if form.start_date.data:
                query = query.filter(TaskAssignment.target_date >= form.start_date.data)
            
            if form.end_date.data:
                query = query.filter(TaskAssignment.target_date <= form.end_date.data)
            
            # 获取数据
            tasks = query.all()
            
            # 生成Excel文件
            excel_generator = ExcelGenerator()
            excel_file = excel_generator.generate_tasks_excel(tasks)
            
            # 创建临时文件
            temp_dir = tempfile.mkdtemp()
            temp_file = os.path.join(temp_dir, '生产任务数据.xlsx')
            excel_file.save(temp_file)
            
            @after_this_request
            def remove_file(response):
                try:
                    os.remove(temp_file)
                    os.rmdir(temp_dir)
                except Exception as e:
                    current_app.logger.error(f'删除临时文件失败: {str(e)}')
                return response
            
            return send_file(
                temp_file,
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

@bp.route('/audit_logs/rollback/<int:log_id>', methods=['POST'])
@login_required
def rollback_audit_log(log_id):
    if not current_user.role == 'admin':
        return jsonify({'success': False, 'message': '权限不足'}), 403
    
    try:
        log = AuditLog.query.get_or_404(log_id)
        
        if not log.can_rollback:
            return jsonify({'success': False, 'message': '此记录不支持回滚'}), 400
        
        # 根据不同的回滚类型执行不同的操作
        if log.rollback_type == 'add':
            # 删除新增的记录
            model_class = globals()[log.target_model]
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
            model_class = globals()[log.target_model]
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
            model_class = globals()[log.target_model]
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
        db.session.rollback()
        current_app.logger.error(f'回滚失败: {str(e)}')
        return jsonify({'success': False, 'message': f'回滚失败：{str(e)}'}), 500

@bp.route('/add_production_record', methods=['GET', 'POST'])
@login_required
def add_production_record():
    if not current_user.role in ['admin', 'hr']:
        flash('权限不足', 'danger')
        return redirect(url_for('main.index'))
    
    form = ProductionRecordForm()
    if form.validate_on_submit():
        try:
            target_date = form.date.data
            start_of_day = datetime.combine(target_date, datetime.min.time())
            end_of_day = datetime.combine(target_date, datetime.max.time())
            
            # 获取当前生效的工序价格
            process_price = ProcessPrice.query.filter(
                ProcessPrice.process_code == form.process_code.data,
                ProcessPrice.effective_date <= end_of_day + timedelta(days=1)
            ).order_by(ProcessPrice.effective_date.desc()).first()
            
            if not process_price:
                flash('未找到有效的工序价格', 'danger')
                return redirect(url_for('main.manage_production_records'))
            
            record = ProductionRecord(
            global_sn=SerialNumber.get_next_number(),
            employee_id=form.employee_id.data,
            process_code=form.process_code.data,
            quantity=form.quantity.data,
            date=form.date.data,
            notes=form.notes.data
            )
            db.session.add(record)
            db.session.flush()
            
            log = AuditLog(
                user_id=current_user.id,
                action='添加生产记录',
                details=f'添加生产记录：员工 {record.employee.name}，工序 {process_price.process_name}，数量 {record.quantity}',
                can_rollback=True,
                rollback_type='add',
                target_model='ProductionRecord',
                target_id=record.id,
                new_data={
                    'employee_id': record.employee_id,
                    'process_code': record.process_code,
                    'quantity': record.quantity,
                    'date': record.date.isoformat() if record.date else None,
                    'notes': record.notes
                }
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
    
    return render_template('main/production_record_form.html', form=form, title='添加生产记录')

@bp.route('/bonus_penalties/<int:id>', methods=['GET'])
@login_required
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
def update_bonus_penalty(id):
    """更新奖惩记录"""
    if current_user.role not in ['admin', 'hr']:
        return jsonify({'success': False, 'message': '权限不足'}), 403
    
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
        db.session.rollback()
        current_app.logger.error(f'更新奖惩记录失败: {str(e)}')
        return jsonify({'success': False, 'message': f'更新失败：{str(e)}'}), 500

@bp.route('/tasks/<int:id>', methods=['GET'])
@login_required
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
        current_app.logger.error(f'获取任务失败: {str(e)}')
        return jsonify({'success': False, 'message': f'获取失败：{str(e)}'}), 500

@bp.route('/tasks/add', methods=['POST'])
@login_required
def add_task():
    """添加任务"""
    if current_user.role not in ['admin', 'hr']:
        return jsonify({'success': False, 'message': '权限不足'}), 403
    
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
            assigned_date=datetime.now().date()  # 设置分配日期
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
        current_app.logger.error(f'获取任务分配详情失败: {str(e)}')
        return jsonify({'success': False, 'message': f'获取失败：{str(e)}'}), 500

@bp.route('/tasks/<int:id>/edit', methods=['POST'])
@login_required
def edit_task(id):
    if not current_user.role in ['admin', 'hr']:
        return jsonify({'success': False, 'message': '权限不足'}), 403
    
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
            if new_status == 'completed':
                task.completed_date = datetime.now().date()
            elif new_status == 'cancelled':
                task.cancelled_date = datetime.now().date()
        
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
        db.session.rollback()
        current_app.logger.error(f'更新任务失败: {str(e)}')
        return jsonify({'success': False, 'message': f'更新失败：{str(e)}'}), 500

@bp.route('/employee_salary_changes/<int:employee_id>')
@login_required
def employee_salary_changes(employee_id):
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
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
def add_salary_change():
    if current_user.role not in ['admin', 'hr']:
        return jsonify({'success': False, 'message': '权限不足'})
    
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
def delete_salary_change():
    if current_user.role not in ['admin', 'hr']:
        return jsonify({'success': False, 'message': '权限不足'})
    
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
@handle_pagination_args
def manage_inventory():
    page = request.args.get('page', 1, type=int)
    per_page = 20
    inventory_type = request.args.get('type', 'finished')
    search = request.args.get('search', '')
    
    if inventory_type == 'raw':
        query = RawMaterial.query
        if search:
            query = query.filter(or_(
                RawMaterial.supplier.ilike(f'%{search}%'),
                RawMaterial.material_name.ilike(f'%{search}%'),
                RawMaterial.melt_number.ilike(f'%{search}%'),
                RawMaterial.supplier_number.ilike(f'%{search}%'),
                RawMaterial.internal_number.ilike(f'%{search}%')
            ))
    else:
        query = FinishedProduct.query
        if search:
            query = query.filter(or_(
                FinishedProduct.product_number.ilike(f'%{search}%'),
                FinishedProduct.drawing_number.ilike(f'%{search}%'),
                FinishedProduct.model.ilike(f'%{search}%'),
                FinishedProduct.inspector.ilike(f'%{search}%')
            ))
    
    pagination = query.order_by(desc('id')).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    # 获取可用的产品编码规则
    code_rules = CodeRule.query.filter_by(code_type='product', is_active=True).all()
    
    return render_template('main/inventory.html',
                         inventory=pagination.items,
                         pagination=pagination,
                         code_rules=code_rules)

@bp.route('/inventory/template')
@login_required
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
            except:
                pass
        ws.column_dimensions[col[0].column_letter].width = max_length + 2
    
    # 返回文件
    return ExcelGenerator.generate_response(wb, filename)

@bp.route('/inventory/finished/import', methods=['POST'])
@login_required
def import_finished_products():
    """导入成品库存"""
    if current_user.role not in ['admin', 'manager']:
        return jsonify({'success': False, 'message': '权限不足'})
    
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
def import_raw_materials():
    """导入原材料库存"""
    if current_user.role not in ['admin', 'manager']:
        return jsonify({'success': False, 'message': '权限不足'})
    
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
                material = RawMaterial(
                    global_sn=SerialNumber.get_next_number(),
                    supplier=str(row['供应商']),
                    material_name=str(row['品名']),
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

@bp.route('/inventory/export')
@login_required
def export_inventory():
    """导出库存数据"""
    inventory_type = request.args.get('type', 'finished')
    
    try:
        # 创建Excel生成器
        excel_generator = ExcelGenerator()
        
        if inventory_type == 'finished':
            # 导出成品库存
            headers = ['全局流水号', '产品编号', '生产日期', '图号', '型号', '检验员', '状态', '备注']
            excel_generator.add_headers(headers)
            
            # 查询数据
            products = FinishedProduct.query.order_by(FinishedProduct.created_at.desc()).all()
            
            # 添加数据行
            for product in products:
                row = [
                    product.global_sn,
                    product.product_number,
                    product.production_date.strftime('%Y-%m-%d'),
                    product.drawing_number,
                    product.model,
                    product.inspector,
                    product.status,
                    product.notes or ''
                ]
                excel_generator.add_row(row)
            
            filename = f'成品库存_{datetime.now().strftime("%Y%m%d")}.xlsx'
        else:
            # 导出原材料库存
            headers = ['全局流水号', '供应商', '品名', '原料冶炼炉号', '供应商编号', '内部编号', 
                      '入库时间', '数量', '是否带样品', '备注']
            excel_generator.add_headers(headers)
            
            # 查询数据
            materials = RawMaterial.query.order_by(RawMaterial.created_at.desc()).all()
            
            # 添加数据行
            for material in materials:
                row = [
                    material.global_sn,
                    material.supplier,
                    material.material_name,
                    material.melt_number,
                    material.supplier_number,
                    material.internal_number,
                    material.storage_date.strftime('%Y-%m-%d'),
                    f'{material.quantity:.2f}',
                    '是' if material.has_sample else '否',
                    material.notes or ''
                ]
                excel_generator.add_row(row)
            
            filename = f'原材料库存_{datetime.now().strftime("%Y%m%d")}.xlsx'
        
        # 生成并返回文件
        return excel_generator.generate_response(filename)
        
    except Exception as e:
        flash(f'导出失败：{str(e)}', 'danger')
        return redirect(url_for('main.manage_inventory', type=inventory_type))

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

@bp.route('/upload/raw-materials', methods=['POST'])
@login_required
@admin_required
def upload_raw_materials():
    """处理原材料数据文件上传"""
    try:
        file = request.files.get('file')
        error = validate_excel_file(file)
        if error:
            return jsonify({'success': False, 'message': error})

        temp_path = save_temp_file(file)
        
        try:
            df = pd.read_excel(temp_path)
            required_columns = ['material_code', 'material_name', 'unit', 'unit_price']
            
            # 验证必需列是否存在
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                return jsonify({
                    'success': False,
                    'message': f'文件缺少必需的列：{", ".join(missing_columns)}'
                })
            
            # 开始数据导入事务
            with db.session.begin_nested():
                for _, row in df.iterrows():
                    raw_material = RawMaterial(
                        material_code=str(row['material_code']),
                        material_name=str(row['material_name']),
                        unit=str(row['unit']),
                        unit_price=float(row['unit_price'])
                    )
                    db.session.add(raw_material)
            
            db.session.commit()
            return jsonify({'success': True, 'message': '原材料数据导入成功'})
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'数据处理错误：{str(e)}'})
        
        finally:
            # 清理临时文件
            if os.path.exists(temp_path):
                os.remove(temp_path)
            os.rmdir(os.path.dirname(temp_path))
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'上传处理错误：{str(e)}'})

@bp.route('/upload/finished-products', methods=['POST'])
@login_required
@admin_required
def upload_finished_products():
    """处理成品数据文件上传"""
    try:
        file = request.files.get('file')
        error = validate_excel_file(file)
        if error:
            return jsonify({'success': False, 'message': error})

        temp_path = save_temp_file(file)
        
        try:
            df = pd.read_excel(temp_path)
            required_columns = ['product_code', 'product_name', 'specification', 'unit', 'unit_price']
            
            # 验证必需列是否存在
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                return jsonify({
                    'success': False,
                    'message': f'文件缺少必需的列：{", ".join(missing_columns)}'
                })
            
            # 开始数据导入事务
            with db.session.begin_nested():
                for _, row in df.iterrows():
                    finished_product = FinishedProduct(
                        product_code=str(row['product_code']),
                        product_name=str(row['product_name']),
                        specification=str(row['specification']),
                        unit=str(row['unit']),
                        unit_price=float(row['unit_price'])
                    )
                    db.session.add(finished_product)
            
            db.session.commit()
            return jsonify({'success': True, 'message': '成品数据导入成功'})
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'数据处理错误：{str(e)}'})
        
        finally:
            # 清理临时文件
            if os.path.exists(temp_path):
                os.remove(temp_path)
            os.rmdir(os.path.dirname(temp_path))
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'上传处理错误：{str(e)}'})

@bp.route('/inventory/finished/add', methods=['POST'])
@login_required
def add_finished_product():
    """添加单个成品"""
    if current_user.role not in ['admin', 'manager']:
        return jsonify({'success': False, 'message': '权限不足'})
    
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
def add_raw_material():
    """添加单个原材料"""
    if current_user.role not in ['admin', 'manager']:
        return jsonify({'success': False, 'message': '权限不足'})
    
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
        required_fields = ['supplier', 'material_name', 'supplier_number', 'storage_date', 'quantity']
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
        
        # 创建原材料记录
        material = RawMaterial(
            global_sn=SerialNumber.get_next_number(),
            supplier=data['supplier'],
            material_name=data['material_name'],
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
            details=f'添加原材料：{material.material_name}',
            can_rollback=True,
            rollback_type='add',
            target_model='RawMaterial',
            target_id=material.id,
            new_data={
                'supplier': material.supplier,
                'material_name': material.material_name,
                'melt_number': material.melt_number,
                'supplier_number': material.supplier_number,
                'internal_number': material.internal_number,
                'quantity': material.quantity
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

@bp.route('/code_rules')
@login_required
def manage_code_rules():
    """编码规则管理"""
    if current_user.role != 'admin':
        flash('权限不足')
        return redirect(url_for('main.index'))
    
    rules = CodeRule.query.order_by(CodeRule.created_at.desc()).all()
    return render_template('main/code_rules.html', rules=rules)

@bp.route('/code_rules/add', methods=['GET', 'POST'])
@login_required
def add_code_rule():
    """添加编码规则"""
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': '权限不足'})
    
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
def edit_code_rule(rule_id):
    """编辑编码规则"""
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': '权限不足'})
    
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
def delete_code_rule(rule_id):
    """删除编码规则"""
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': '权限不足'})
    
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
def generate_code(rule_id):
    """生成编码"""
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': '权限不足'})
        
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
def get_finished_product(id):
    """获取成品详情"""
    if current_user.role not in ['admin', 'manager']:
        return jsonify({'success': False, 'message': '权限不足'})
    
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
        return jsonify({'success': False, 'message': f'获取成品详情失败：{str(e)}'})

@bp.route('/inventory/finished/<int:id>', methods=['PUT'])
@login_required
def update_finished_product(id):
    """更新成品信息"""
    if current_user.role not in ['admin', 'manager']:
        return jsonify({'success': False, 'message': '权限不足'})
    
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
        db.session.rollback()
        return jsonify({'success': False, 'message': f'更新失败：{str(e)}'})

@bp.route('/inventory/raw/<int:id>', methods=['GET'])
@login_required
def get_raw_material(id):
    """获取原材料详情"""
    if current_user.role not in ['admin', 'manager']:
        return jsonify({'success': False, 'message': '权限不足'})
    
    try:
        material = RawMaterial.query.get_or_404(id)
        return jsonify({
            'success': True,
            'data': {
                'id': material.id,
                'supplier': material.supplier,
                'material_name': material.material_name,
                'melt_number': material.melt_number,
                'supplier_number': material.supplier_number,
                'internal_number': material.internal_number,
                'storage_date': material.storage_date.strftime('%Y-%m-%d'),
                'quantity': material.quantity,
                'has_sample': material.has_sample,
                'notes': material.notes or ''
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'获取原材料详情失败：{str(e)}'})

@bp.route('/inventory/raw/<int:id>', methods=['PUT'])
@login_required
def update_raw_material(id):
    """更新原材料信息"""
    if current_user.role not in ['admin', 'manager']:
        return jsonify({'success': False, 'message': '权限不足'})
    
    try:
        material = RawMaterial.query.get_or_404(id)
        data = request.json
        
        if not data:
            return jsonify({'success': False, 'message': '请求数据为空'})
        
        # 保存旧数据用于审计日志
        old_data = {
            'supplier': material.supplier,
            'material_name': material.material_name,
            'melt_number': material.melt_number,
            'supplier_number': material.supplier_number,
            'internal_number': material.internal_number,
            'storage_date': material.storage_date.strftime('%Y-%m-%d'),
            'quantity': material.quantity,
            'has_sample': material.has_sample,
            'notes': material.notes
        }
        
        # 更新数据
        material.supplier = data['supplier']
        material.material_name = data['material_name']
        material.melt_number = data.get('melt_number', '')  # 可选字段
        material.supplier_number = data['supplier_number']
        material.storage_date = datetime.strptime(data['storage_date'], '%Y-%m-%d').date()
        material.quantity = float(data['quantity'])
        material.has_sample = data.get('has_sample', False)
        material.notes = data.get('notes', '')
        
        # 记录审计日志
        log = AuditLog(
            user_id=current_user.id,
            action='更新原材料',
            details=f'更新原材料：{material.material_name}',
            can_rollback=True,
            rollback_type='edit',
            target_model='RawMaterial',
            target_id=material.id,
            old_data=old_data,
            new_data={
                'supplier': material.supplier,
                'material_name': material.material_name,
                'melt_number': material.melt_number,
                'supplier_number': material.supplier_number,
                'internal_number': material.internal_number,
                'storage_date': material.storage_date.strftime('%Y-%m-%d'),
                'quantity': material.quantity,
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
        db.session.rollback()
        return jsonify({'success': False, 'message': f'更新失败：{str(e)}'})

@bp.route('/process_prices/<int:id>', methods=['GET'])
@login_required
def get_process_price(id):
    """获取工序详情"""
    try:
        process = ProcessPrice.query.get_or_404(id)
        return jsonify({
            'success': True,
            'data': {
                'id': process.id,
                'process_code': process.process_code,
                'process_name': process.process_name,
                'has_output': process.has_output,
                'output_type': process.output_type,
                'needs_raw_material': process.needs_raw_material,
                'code_rule_id': process.code_rule_id
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'获取工序详情失败：{str(e)}'}), 500

@bp.route('/raw_materials/available', methods=['GET'])
@login_required
def get_available_raw_materials():
    """获取可用的原材料列表"""
    try:
        materials = RawMaterial.query.filter(RawMaterial.quantity > 0).all()
        return jsonify({
            'success': True,
            'data': [{
                'id': material.id,
                'material_name': material.material_name,
                'quantity': material.quantity
            } for material in materials]
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'获取原材料列表失败：{str(e)}'}), 500