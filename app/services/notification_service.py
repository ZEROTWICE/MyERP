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
        'CONCESSION_APPROVAL': 'concession_approval',  # 让步审批（B13-08 补键）
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
        template_variables: Dict = None,
        _dedup_enabled: bool = True
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

        幂等（B13-07）：插入前按 (trigger_type, related_model, related_id) 做一次
        **查询级**存在性检查，同一业务事件重复触发（双击 / 重放 / 多路径触发）不会
        产生第二条通知行，此时返回既有通知行（不再新建 receiver，避免与
        uq_notification_receiver 冲突）。语义边界：

        * 去重键 = `trigger_type + related_model + related_id` 三者同时相等。
        * `related_id is None` 时**不去重**（直接新建）：无关联对象的通知无法在
          「同一事件的重复触发」与「两个不同事件」之间区分，去重会误合并真实事件；
          此处显式定义为「一律不去重」，而非意外行为。
        * 三键之外的信息（title/content/notification_type/receivers）**不**改变
          去重结果：同一事件重放时携带的载体数据差异不影响「同一事件」的判定。
        * 去重只做存在性查询，**不新增唯一约束 / 索引 / 列**（零 schema 变更）。

        事务边界（B13-05）：本方法只 add/flush，**不再自带 commit**。
        flush 仅用于取得 notification.id 以建立 receiver 关联，不是提交；
        提交责任在调用方（谁开事务谁提交），避免「每接一个触发器多一次隐式提交」。
        异常路径保留 rollback（沿用既有行为）：调用方须自持事务边界，
        失败时由其决定回滚或消化本次通知写入。
        """
        try:
            # 幂等检查（B13-07）：同一业务事件重复触发不重复建行。
            # 负例对照用的开关 _dedup_enabled=False 仅供证据探针使用（默认 True）。
            existing = NotificationService._find_existing_notification(
                trigger_type=trigger_type,
                related_model=related_model,
                related_id=related_id,
                dedup_enabled=_dedup_enabled,
            )
            if existing is not None:
                # 重放：返回既有行，不新建 Notification / NotificationReceiver。
                # 与首次创建保持同一终态（首次创建末尾即 status='sent'）。
                if existing.status != 'sent':
                    existing.status = 'sent'
                    existing.sent_at = existing.sent_at or datetime.utcnow()
                current_app.logger.info(
                    f'通知幂等命中，跳过重复创建: trigger_type={trigger_type} '
                    f'related_model={related_model} related_id={related_id} '
                    f'(既有 ID: {existing.id})'
                )
                return existing

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
            
            current_app.logger.info(f'通知创建成功: {notification.title} (ID: {notification.id})')
            return notification
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'创建通知失败: {str(e)}')
            raise e

    @staticmethod
    def _find_existing_notification(
        trigger_type: str,
        related_model: str = None,
        related_id: int = None,
        dedup_enabled: bool = True
    ) -> Optional[Notification]:
        """B13-07 幂等去重：按 (trigger_type, related_model, related_id) 查既有通知行。

        返回命中到的既有通知（已存在或本会话内已 add 未提交的），未命中返回 None。

        为什么两段查：
        1. 先查本会话 `db.session.new`——同一事务内连续两次触发时，第一次 add 的行
           还未落库，用 `no_autoflush` 的查询看不到它，会误建第二条。
        2. 再查库（`related_id is not None` 才查，见 create_notification 的语义边界）。
           用 `no_autoflush` 避免这次只读查询顺带 flush 调用方的其它待写对象
           （读操作不应有写副作用），也避免命中已被 `delete()` 标记删除的行。

        不改 schema：只用既有列做等值查询；`related_id` 为空时显式不去重。
        """
        if not dedup_enabled or related_id is None:
            return None

        # 1) 本会话内已 add 但尚未提交的通知（同事务重复触发）
        for obj in db.session.new:
            if not isinstance(obj, Notification):
                continue
            if (
                obj.trigger_type == trigger_type
                and obj.related_model == related_model
                and obj.related_id == related_id
            ):
                return obj

        # 2) 库内既有通知（跨请求 / 跨事务重复触发）
        with db.session.no_autoflush:
            return Notification.query.filter(
                Notification.trigger_type == trigger_type,
                Notification.related_model == related_model,
                Notification.related_id == related_id,
            ).order_by(Notification.id.asc()).first()

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
        """删除用户的通知接收记录

        事务边界：本方法沿用既有形态，仍自行提交/回滚（与 `mark_as_read`/
        `archive_notification` 的「调用方提交」形态不一致，但属 B13-05 的
        「除既有 1 处」存留项——B13-05 只移除 `create_notification` 的隐式提交，
        不扩大改动面）。当前全仓零调用点。
        """
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
def notify_process_change(process_name: str, old_data: Dict, new_data: Dict, user_id: int = None,
                          related_id: int = None, receivers: List[Union[int, str]] = None):
    """工艺变更通知

    B13-06 接线：调用方传 `related_id`（被变更的 `ProcessPrice.id`），本通知才具备
    B13-07 的查询级幂等键（`trigger_type='process_change'` + `related_model='ProcessPrice'`
    + `related_id`）；不传则按 B13-07 语义「一律不去重」（related_id 为空时不去重）。
    `receivers` 同样由调用方显式给出：规则表（NotificationRule）当前 0 行，
    只靠 `_create_receivers_by_rules` 会静默地一个接收人都不建。
    """
    user_id = user_id or (current_user.id if current_user.is_authenticated else None)
    
    # 事务边界：本 helper 不自提交，提交责任在调用方的事务边界内（B13-05）。
    notification = NotificationService.create_notification(
        trigger_type=NotificationService.TRIGGER_TYPES['PROCESS_CHANGE'],
        title=f'工艺变更通知 - {process_name}',
        content=f'工艺 {process_name} 已发生变更，请及时关注。',
        notification_type='warning',
        priority='high',
        related_model='ProcessPrice',
        related_id=related_id,
        receivers=receivers,
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
    return notification


def notify_spec_change(order_number: str, batch_count: int, task_count: int, user_id: int = None,
                       related_id: int = None, receivers: List[Union[int, str]] = None):
    """规格变更通知

    B13-06 接线：调用方传 `related_id`（被变更的 `ProductionOrder.id`），本通知才具备
    B13-07 的查询级幂等键（`trigger_type='spec_change'` + `related_model='ProductionOrder'`
    + `related_id`）；不传则按 B13-07 语义「一律不去重」（重复事件会重复建行）。
    `receivers` 同样由调用方显式给出：规则表（NotificationRule）当前 0 行，
    只靠 `_create_receivers_by_rules` 会静默地一个接收人都不建。
    """
    user_id = user_id or (current_user.id if current_user.is_authenticated else None)
    
    # 事务边界：本 helper 不自提交，提交责任在调用方的事务边界内（B13-05）。
    notification = NotificationService.create_notification(
        trigger_type=NotificationService.TRIGGER_TYPES['SPEC_CHANGE'],
        title=f'规格变更通知 - {order_number}',
        content=f'生产订单 {order_number} 的规格信息已更新，影响 {batch_count} 个批次和 {task_count} 个任务。',
        notification_type='info',
        priority='normal',
        related_model='ProductionOrder',
        related_id=related_id,
        receivers=receivers,
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
    return notification


# ---------------------------------------------------------------------------
# B13-06 / 拍板项 6：`notify_inventory_warning` **只登记、不接线**的仓库内可见登记。
#   * 缺失数据源：触发库存预警所需的「安全库存阈值」统一配置项尚无业务取值，
#     故本触发器在本批次按 81- §7.2 拍板项 6 的默认路径**继续保持零调用点（只登记）**。
#   * 待加配置项：`SystemConfig(key='inventory.min_stock_level')`（零 schema 变更——
#     `SystemConfig` 是既有 key/value 表）；其默认登记表 `SystemConfig.DEFAULTS` 位于
#     `app/models.py`，**不在 B13-06 的 inScope 内** ⇒ 本任务只登记、不改该文件。
#   * 未给值 ⇒ 不接线；给值后由后续条目把本函数接到库存校验落点。
#   * 门禁锚点：B13-09 的 allowlist 通道按 `test-reports-2026-10/81-后续开发与测试规划.md`
#     内「notify_inventory_warning … 只登记」同一行共现定位；本行同时含
#     notify_inventory_warning 与其豁免语义，便于仓库内检索该登记。
# ---------------------------------------------------------------------------
def notify_inventory_warning(material_name: str, current_stock: float, min_stock: float):
    """库存预警通知

    B13-06：**保持零调用点（只登记）**——安全库存阈值配置项 `inventory.min_stock_level`
    尚无业务取值，见上方登记块与 81- §7.2 拍板项 6。
    """
    # 事务边界：本 helper 不自提交，提交责任在调用方的事务边界内（B13-05）。
    notification = NotificationService.create_notification(
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
    return notification


def notify_task_assignment(employee_name: str, task_count: int, batch_number: str = None,
                           related_id: int = None, receivers: List[Union[int, str]] = None):
    """任务分配（派工）通知

    B13-06 接线：调用方传 `related_id`（新建 `TaskAssignment.id`）与 `receivers`
    （被派工员工的 user id 列表），本通知才同时具备「`/notifications` 可见」与
    B13-07 的查询级幂等键（`trigger_type='task_assignment'` +
    `related_model='TaskAssignment'` + `related_id`）。
    不传 `related_id` 则按 B13-07 语义「一律不去重」（重复派工事件会重复建行）。
    """
    # 事务边界：本 helper 不自提交，提交责任在调用方的事务边界内（B13-05）。
    notification = NotificationService.create_notification(
        trigger_type=NotificationService.TRIGGER_TYPES['TASK_ASSIGNMENT'],
        title=f'任务分配通知 - {employee_name}',
        content=f'已为 {employee_name} 分配 {task_count} 个新任务' + (f'（批次：{batch_number}）' if batch_number else '') + '。',
        notification_type='info',
        priority='normal',
        related_model='TaskAssignment',
        related_id=related_id,
        receivers=receivers,
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
    return notification


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

    # 事务边界：本 helper 不自提交，提交责任在调用方的事务边界内（B13-05）。
    notification = NotificationService.create_notification(
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
    return notification