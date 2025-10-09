"""
通知服务模块
提供通知的创建、发送、管理等功能
"""

from datetime import datetime
from typing import List, Dict, Any, Optional, Union
from sqlalchemy import and_, or_
from flask import current_app
from flask_login import current_user

from app import db
from app.models import (
    NotificationRule, Notification, NotificationReceiver, 
    NotificationTemplate, User, Employee
)


class NotificationService:
    """通知服务类"""
    
    # 预定义的触发类型
    TRIGGER_TYPES = {
        'PROCESS_CHANGE': 'process_change',           # 工艺变更
        'SPEC_CHANGE': 'spec_change',                 # 规格变更
        'INVENTORY_WARNING': 'inventory_warning',     # 库存预警
        'PRODUCTION_ORDER_STATUS': 'production_order_status',  # 生产订单状态变更
        'TASK_ASSIGNMENT': 'task_assignment',         # 任务分配
        'TASK_OVERDUE': 'task_overdue',              # 任务逾期
        'QUALITY_ISSUE': 'quality_issue',            # 质量问题
        'SYSTEM_MAINTENANCE': 'system_maintenance',  # 系统维护
        'USER_LOGIN': 'user_login',                  # 用户登录
        'DATA_BACKUP': 'data_backup',                # 数据备份
        'RAW_SUBSTITUTION': 'raw_substitution',      # 原材料替用
    }
    
    # 预定义的接收者类型
    RECEIVER_TYPES = {
        'USER': 'user',           # 指定用户
        'ROLE': 'role',           # 指定角色
        'DEPARTMENT': 'department' # 指定部门
    }
    
    # 预定义的通知方式
    NOTIFICATION_METHODS = {
        'SYSTEM': 'system',       # 系统内通知
        'EMAIL': 'email',         # 邮件通知
        'SMS': 'sms'              # 短信通知
    }

    @staticmethod
    def create_notification(
        trigger_type: str,
        title: str,
        content: str,
        notification_type: str = 'info',
        priority: str = 'normal',
        related_model: str = None,
        related_id: int = None,
        trigger_data: Dict = None,
        receivers: List[Union[int, str]] = None,
        template_code: str = None,
        template_variables: Dict = None
    ) -> Notification:
        """
        创建通知
        
        Args:
            trigger_type: 触发类型
            title: 通知标题
            content: 通知内容
            notification_type: 通知类型 (info, warning, error, success)
            priority: 优先级 (low, normal, high, urgent)
            related_model: 关联模型名称
            related_id: 关联对象ID
            trigger_data: 触发数据
            receivers: 接收者列表 (用户ID列表或特殊标识符)
            template_code: 模板编码
            template_variables: 模板变量
        
        Returns:
            Notification: 创建的通知对象
        """
        try:
            # 如果使用模板，渲染标题和内容
            if template_code and template_variables:
                template = NotificationTemplate.query.filter_by(
                    template_code=template_code, 
                    is_active=True
                ).first()
                if template:
                    title, content = template.render(template_variables)
                    notification_type = template.notification_type
            
            # 创建通知记录
            notification = Notification(
                trigger_type=trigger_type,
                trigger_data=trigger_data or {},
                title=title,
                content=content,
                notification_type=notification_type,
                priority=priority,
                related_model=related_model,
                related_id=related_id
            )
            
            db.session.add(notification)
            db.session.flush()  # 获取通知ID
            
            # 处理接收者
            if receivers:
                NotificationService._create_receivers(notification, receivers)
            else:
                # 根据规则自动确定接收者
                NotificationService._create_receivers_by_rules(notification, trigger_type, trigger_data)
            
            # 标记为已发送
            notification.status = 'sent'
            notification.sent_at = datetime.utcnow()
            
            db.session.commit()
            
            current_app.logger.info(f'通知创建成功: {notification.title} (ID: {notification.id})')
            return notification
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'创建通知失败: {str(e)}')
            raise e

    @staticmethod
    def _create_receivers(notification: Notification, receivers: List[Union[int, str]]):
        """根据接收者列表创建通知接收者记录"""
        for receiver in receivers:
            if isinstance(receiver, int):
                # 直接指定用户ID
                user = User.query.get(receiver)
                if user:
                    NotificationService._add_receiver(notification, user)
            elif isinstance(receiver, str):
                # 特殊标识符
                if receiver == 'all_admins':
                    # 所有管理员
                    admins = User.query.filter_by(role='admin').all()
                    for admin in admins:
                        NotificationService._add_receiver(notification, admin)
                elif receiver == 'all_managers':
                    # 所有经理
                    managers = User.query.filter_by(role='manager').all()
                    for manager in managers:
                        NotificationService._add_receiver(notification, manager)
                elif receiver.startswith('role:'):
                    # 角色：role:admin
                    role = receiver.split(':', 1)[1]
                    users = User.query.filter_by(role=role).all()
                    for user in users:
                        NotificationService._add_receiver(notification, user)
                elif receiver.startswith('department:'):
                    # 部门：department:生产部
                    department = receiver.split(':', 1)[1]
                    employees = Employee.query.filter_by(department=department, is_active=True).all()
                    for emp in employees:
                        if emp.user:
                            NotificationService._add_receiver(notification, emp.user)

    @staticmethod
    def _create_receivers_by_rules(notification: Notification, trigger_type: str, trigger_data: Dict):
        """根据通知规则自动确定接收者"""
        rules = NotificationRule.query.filter_by(
            trigger_type=trigger_type,
            is_active=True
        ).order_by(NotificationRule.priority.desc()).all()
        
        receiver_set = set()  # 避免重复接收者
        
        for rule in rules:
            if NotificationService._check_rule_conditions(rule, trigger_data):
                # 规则匹配，添加接收者
                rule_receivers = NotificationService._get_rule_receivers(rule)
                receiver_set.update(rule_receivers)
                
                # 关联规则（取第一个匹配的规则）
                if not notification.rule_id:
                    notification.rule_id = rule.id
        
        # 创建接收者记录
        for user_id in receiver_set:
            user = User.query.get(user_id)
            if user:
                NotificationService._add_receiver(notification, user)

    @staticmethod
    def _check_rule_conditions(rule: NotificationRule, trigger_data: Dict) -> bool:
        """检查规则条件是否匹配"""
        if not rule.trigger_conditions:
            return True  # 无条件限制，匹配所有
        
        conditions = rule.trigger_conditions
        
        try:
            # 检查优先级条件
            if 'priority' in conditions:
                required_priority = conditions['priority']
                if trigger_data.get('priority') != required_priority:
                    return False
            
            # 检查部门条件
            if 'departments' in conditions:
                required_departments = conditions['departments']
                trigger_department = trigger_data.get('department')
                if trigger_department not in required_departments:
                    return False
            
            # 检查用户条件
            if 'users' in conditions:
                required_users = conditions['users']
                trigger_user = trigger_data.get('user_id')
                if trigger_user not in required_users:
                    return False
            
            # 检查模型条件
            if 'models' in conditions:
                required_models = conditions['models']
                trigger_model = trigger_data.get('model')
                if trigger_model not in required_models:
                    return False
            
            return True
            
        except Exception as e:
            current_app.logger.error(f'检查规则条件失败: {str(e)}')
            return False

    @staticmethod
    def _get_rule_receivers(rule: NotificationRule) -> List[int]:
        """获取规则的接收者用户ID列表"""
        receivers = []
        config = rule.receiver_config or {}
        
        if rule.receiver_type == 'user':
            # 指定用户
            user_ids = config.get('user_ids', [])
            receivers.extend(user_ids)
            
        elif rule.receiver_type == 'role':
            # 指定角色
            roles = config.get('roles', [])
            for role in roles:
                users = User.query.filter_by(role=role).all()
                receivers.extend([u.id for u in users])
                
        elif rule.receiver_type == 'department':
            # 指定部门
            departments = config.get('departments', [])
            for dept in departments:
                employees = Employee.query.filter_by(department=dept, is_active=True).all()
                for emp in employees:
                    if emp.user:
                        receivers.append(emp.user.id)
        
        return list(set(receivers))  # 去重

    @staticmethod
    def _add_receiver(notification: Notification, user: User):
        """添加通知接收者"""
        # 检查是否已存在
        existing = NotificationReceiver.query.filter_by(
            notification_id=notification.id,
            user_id=user.id
        ).first()
        
        if not existing:
            receiver = NotificationReceiver(
                notification_id=notification.id,
                user_id=user.id,
                delivery_method='system',
                delivery_status='delivered',
                delivery_at=datetime.utcnow()
            )
            db.session.add(receiver)

    @staticmethod
    def get_user_notifications(
        user_id: int, 
        status: str = None, 
        notification_type: str = None,
        limit: int = 50,
        offset: int = 0
    ) -> Dict:
        """
        获取用户通知列表
        
        Args:
            user_id: 用户ID
            status: 状态过滤 (unread, read, archived)
            notification_type: 通知类型过滤 (info, warning, error, success)
            limit: 限制数量
            offset: 偏移量
        
        Returns:
            Dict: 包含通知列表和统计信息
        """
        query = db.session.query(Notification, NotificationReceiver).join(
            NotificationReceiver, Notification.id == NotificationReceiver.notification_id
        ).filter(NotificationReceiver.user_id == user_id)
        
        # 状态过滤
        if status:
            query = query.filter(NotificationReceiver.status == status)
        
        # 通知类型过滤
        if notification_type:
            query = query.filter(Notification.notification_type == notification_type)
        
        # 排序
        query = query.order_by(Notification.created_at.desc())
        
        # 分页
        total = query.count()
        notifications = query.offset(offset).limit(limit).all()
        
        # 统计信息
        stats = NotificationService.get_user_notification_stats(user_id)
        
        return {
            'notifications': [
                {
                    'id': notif.id,
                    'title': notif.title,
                    'content': notif.content,
                    'notification_type': notif.notification_type,
                    'priority': notif.priority,
                    'status': receiver.status,
                    'created_at': notif.created_at,
                    'read_at': receiver.read_at,
                    'related_model': notif.related_model,
                    'related_id': notif.related_id
                }
                for notif, receiver in notifications
            ],
            'total': total,
            'stats': stats
        }

    @staticmethod
    def get_user_notification_stats(user_id: int) -> Dict:
        """获取用户通知统计"""
        base_query = NotificationReceiver.query.filter_by(user_id=user_id)
        
        unread_count = base_query.filter_by(status='unread').count()
        read_count = base_query.filter_by(status='read').count()
        archived_count = base_query.filter_by(status='archived').count()
        total_count = base_query.count()
        
        # 按类型统计
        type_stats = db.session.query(
            Notification.notification_type,
            db.func.count(NotificationReceiver.id).label('count')
        ).join(NotificationReceiver).filter(
            NotificationReceiver.user_id == user_id,
            NotificationReceiver.status == 'unread'
        ).group_by(Notification.notification_type).all()
        
        return {
            'unread': unread_count,
            'read': read_count,
            'archived': archived_count,
            'total': total_count,
            'by_type': {stat.notification_type: stat.count for stat in type_stats}
        }

    @staticmethod
    def mark_as_read(notification_id: int, user_id: int) -> bool:
        """标记通知为已读"""
        try:
            receiver = NotificationReceiver.query.filter_by(
                notification_id=notification_id,
                user_id=user_id
            ).first()
            
            if receiver:
                receiver.mark_as_read()
                return True
            return False
            
        except Exception as e:
            current_app.logger.error(f'标记通知已读失败: {str(e)}')
            return False

    @staticmethod
    def archive_notification(notification_id: int, user_id: int) -> bool:
        """归档通知"""
        try:
            receiver = NotificationReceiver.query.filter_by(
                notification_id=notification_id,
                user_id=user_id
            ).first()
            
            if receiver:
                receiver.archive()
                return True
            return False
            
        except Exception as e:
            current_app.logger.error(f'归档通知失败: {str(e)}')
            return False

    @staticmethod
    def delete_notification(notification_id: int, user_id: int) -> bool:
        """删除用户的通知接收记录"""
        try:
            receiver = NotificationReceiver.query.filter_by(
                notification_id=notification_id,
                user_id=user_id
            ).first()
            
            if receiver:
                db.session.delete(receiver)
                db.session.commit()
                return True
            return False
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'删除通知失败: {str(e)}')
            return False


# 便捷的触发器函数
def notify_process_change(process_name: str, old_data: Dict, new_data: Dict, user_id: int = None):
    """工艺变更通知"""
    user_id = user_id or (current_user.id if current_user.is_authenticated else None)
    
    NotificationService.create_notification(
        trigger_type=NotificationService.TRIGGER_TYPES['PROCESS_CHANGE'],
        title=f'工艺变更通知 - {process_name}',
        content=f'工艺 {process_name} 已发生变更，请及时关注。',
        notification_type='warning',
        priority='high',
        related_model='ProcessPrice',
        trigger_data={
            'process_name': process_name,
            'old_data': old_data,
            'new_data': new_data,
            'user_id': user_id
        },
        template_code='process_change',
        template_variables={
            'process_name': process_name,
            'user_name': current_user.username if current_user.is_authenticated else '系统',
            'old_data': old_data,
            'new_data': new_data
        }
    )


def notify_spec_change(order_number: str, batch_count: int, task_count: int, user_id: int = None):
    """规格变更通知"""
    user_id = user_id or (current_user.id if current_user.is_authenticated else None)
    
    NotificationService.create_notification(
        trigger_type=NotificationService.TRIGGER_TYPES['SPEC_CHANGE'],
        title=f'规格变更通知 - {order_number}',
        content=f'生产订单 {order_number} 的规格信息已更新，影响 {batch_count} 个批次和 {task_count} 个任务。',
        notification_type='info',
        priority='normal',
        related_model='ProductionOrder',
        trigger_data={
            'order_number': order_number,
            'batch_count': batch_count,
            'task_count': task_count,
            'user_id': user_id
        },
        template_code='spec_change',
        template_variables={
            'order_number': order_number,
            'batch_count': batch_count,
            'task_count': task_count,
            'user_name': current_user.username if current_user.is_authenticated else '系统'
        }
    )


def notify_inventory_warning(material_name: str, current_stock: float, min_stock: float):
    """库存预警通知"""
    NotificationService.create_notification(
        trigger_type=NotificationService.TRIGGER_TYPES['INVENTORY_WARNING'],
        title=f'库存预警 - {material_name}',
        content=f'物料 {material_name} 库存不足，当前库存：{current_stock}，最低库存：{min_stock}。',
        notification_type='warning',
        priority='high',
        trigger_data={
            'material_name': material_name,
            'current_stock': current_stock,
            'min_stock': min_stock
        },
        template_code='inventory_warning',
        template_variables={
            'material_name': material_name,
            'current_stock': current_stock,
            'min_stock': min_stock
        }
    )


def notify_task_assignment(employee_name: str, task_count: int, batch_number: str = None):
    """任务分配通知"""
    NotificationService.create_notification(
        trigger_type=NotificationService.TRIGGER_TYPES['TASK_ASSIGNMENT'],
        title=f'任务分配通知 - {employee_name}',
        content=f'已为 {employee_name} 分配 {task_count} 个新任务' + (f'（批次：{batch_number}）' if batch_number else '') + '。',
        notification_type='info',
        priority='normal',
        trigger_data={
            'employee_name': employee_name,
            'task_count': task_count,
            'batch_number': batch_number
        },
        template_code='task_assignment',
        template_variables={
            'employee_name': employee_name,
            'task_count': task_count,
            'batch_number': batch_number or '无'
        }
    ) 


def notify_raw_substitution(task_id: int, order_number: str, substitutions: List[Dict], operator_name: str = None):
    """原材料替用通知
    substitutions: [{'raw_material_id': int, 'raw_material_name': str, 'quantity': float}]
    """
    operator_name = operator_name or (current_user.username if current_user.is_authenticated else '系统')

    # 生成简要内容
    try:
        items_text = '；'.join([
            f"{item.get('raw_material_name', '未知物料')}×{item.get('quantity', 0)}"
            for item in substitutions
        ]) or '无'
    except Exception:
        items_text = '无'

    NotificationService.create_notification(
        trigger_type=NotificationService.TRIGGER_TYPES['RAW_SUBSTITUTION'],
        title=f'原材料替用 - 任务{task_id}',
        content=f'生产订单 {order_number} 的任务 {task_id} 发生原材料替用：{items_text}。',
        notification_type='warning',
        priority='normal',
        related_model='TaskAssignment',
        related_id=task_id,
        trigger_data={
            'task_id': task_id,
            'order_number': order_number,
            'substitutions': substitutions,
            'operator_name': operator_name,
            'model': 'TaskAssignment'
        },
        template_code='raw_substitution',
        template_variables={
            'task_id': task_id,
            'order_number': order_number,
            'operator_name': operator_name,
            'items': substitutions
        }
    )