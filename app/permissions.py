"""权限能力映射：导航可见性与路由校验的唯一事实来源。

历史上导航写在 base.html、校验散落在各视图函数里，两边各写各的导致菜单与
实际可访问范围错位。新增受限功能时只在这里登记一次，模板用 can()、路由用
@require_capability，两侧自然保持一致。

映射初始值逐条抄自 routes.py / quality.py 中已有的 current_user.role 判断；
少数原本没有任何校验的列表页按同模块写操作的角色范围收敛，属于收紧而非放宽。
"""
from functools import wraps

from flask import flash, jsonify, redirect, request, url_for
from flask_login import current_user

# 系统内全部角色及其中文名，供配置页与权限说明使用
ROLES = (
    ('admin', '系统管理员'),
    ('manager', '经理'),
    ('hr', '人事'),
    ('accountant', '会计'),
    ('inspector', '检验员'),
    ('sales', '销售'),
    ('user', '普通员工'),
)

# capability -> 允许的角色
CAPABILITIES = {
    # 员工与人事
    'employee.view': ('admin', 'hr'),
    'employee.manage': ('admin', 'hr'),
    'employee.delete': ('admin',),
    'employee.salary_change': ('admin', 'hr'),
    'bonus.manage': ('admin', 'hr'),
    'salary.view': ('admin', 'accountant'),

    # 工序
    'process.view': ('admin', 'hr', 'manager'),
    'process.manage': ('admin', 'hr'),
    'process.delete': ('admin',),
    'process_assignment.manage': ('admin', 'manager'),

    # 生产
    'production_record.view': ('admin', 'hr', 'manager'),
    'production_record.manage': ('admin', 'hr'),
    'task.manage': ('admin', 'hr'),
    'production_order.view': ('admin', 'manager'),
    'production_order.manage': ('admin', 'manager'),
    'production_center.use': ('admin', 'manager'),

    # 库存
    'inventory.view': ('admin', 'manager'),
    'inventory.manage': ('admin', 'manager'),
    'consumable.delete': ('admin',),

    # 产品
    'product.view': ('admin', 'manager'),
    'product.manage': ('admin', 'manager'),
    'product.import': ('admin',),

    # 客户与销售
    'customer.manage': ('admin', 'manager', 'sales'),
    'customer.delete': ('admin', 'manager'),
    'sales_order.manage': ('admin', 'manager', 'sales'),
    'sales_order.delete': ('admin', 'manager'),

    # 质量
    'quality.view': ('admin', 'manager', 'inspector'),
    'quality.inspect': ('admin', 'manager', 'inspector'),
    'quality.template.manage': ('admin', 'manager'),
    'quality.task.manage': ('admin', 'manager'),
    'quality.export': ('admin', 'manager'),

    # 系统
    'code_rule.manage': ('admin',),
    'audit.view': ('admin',),
    'audit.rollback': ('admin',),
    'notification_rule.manage': ('admin', 'manager'),
    'system_config.manage': ('admin',),

    # 员工自助（手机端）
    'my_tasks.use': ('user',),
}


def roles_for(capability):
    """返回某个能力允许的角色元组；未登记的能力返回空元组（默认拒绝）。"""
    return CAPABILITIES.get(capability, ())


def can(capability, user=None):
    """当前用户（或指定用户）是否具备某个能力。"""
    user = user or current_user
    if not getattr(user, 'is_authenticated', False):
        return False
    return getattr(user, 'role', None) in roles_for(capability)


def can_any(*capabilities):
    """具备其中任意一个能力即为真，用于父级菜单的显隐。"""
    return any(can(c) for c in capabilities)


def _wants_json():
    """JSON API 与页面路由的失败响应形式不同。"""
    if request.path.startswith('/api/'):
        return True
    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return True
    return request.accept_mimetypes.best == 'application/json'


def require_capability(*capabilities):
    """路由级权限校验，具备任意一个能力即放行。"""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated:
                if _wants_json():
                    return jsonify({'success': False, 'message': '请先登录'}), 401
                return redirect(url_for('auth.login', next=request.url))

            if not can_any(*capabilities):
                if _wants_json():
                    return jsonify({'success': False, 'message': '权限不足'}), 403
                flash('权限不足', 'danger')
                return redirect(url_for('main.index'))

            return f(*args, **kwargs)
        return decorated
    return decorator


def init_app(app):
    """注册模板全局函数，使 base.html 可直接使用 can() / can_any()。"""
    app.jinja_env.globals['can'] = can
    app.jinja_env.globals['can_any'] = can_any
