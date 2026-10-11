from flask import Flask, flash, jsonify, redirect, request, url_for
from werkzeug.exceptions import HTTPException
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from flask_bootstrap import Bootstrap5
import os
import click
from config import Config
from sqlalchemy import inspect, text

db = SQLAlchemy()
login = LoginManager()
migrate = Migrate()
csrf = CSRFProtect()
bootstrap = Bootstrap5()

# 启动时需要保证存在的列：表名 -> [(列名, SQLite 列类型)]
# 迁移链存在多个 head 且历史表多由 db.create_all() 建出，这里做幂等兜底。
_ENSURED_COLUMNS = {
    'sales_order_items': [
        ('spec_splice_hole', 'VARCHAR(100)'),
        ('spec_gasket_hole', 'VARCHAR(100)'),
        ('anti_corrosion', 'VARCHAR(100)'),
        ('rubber_gasket_material', 'VARCHAR(100)'),
        ('turnout_rail', 'VARCHAR(100)'),
        ('using_unit', 'VARCHAR(100)'),
    ],
    'task_assignment': [
        ('completed_at', 'DATETIME'),
        ('equipment_id', 'INTEGER'),
        ('work_center_id', 'INTEGER'),
        ('spec_splice_hole', 'VARCHAR(100)'),
        ('spec_gasket_hole', 'VARCHAR(100)'),
        ('anti_corrosion', 'VARCHAR(100)'),
        ('rubber_gasket_material', 'VARCHAR(100)'),
        ('turnout_rail', 'VARCHAR(100)'),
        ('using_unit', 'VARCHAR(100)'),
    ],
    # 这三个规格列组只由 eb1234567890 补过一次，且该修订在早于它的老库上
    # 是无条件 add_column；这里登记后，版本停留在 c81522b131f7 及更早、
    # schema 却由 create_all() 建出的库也能在启动时自愈。
    'production_orders': [
        ('spec_splice_hole', 'VARCHAR(100)'),
        ('spec_gasket_hole', 'VARCHAR(100)'),
        ('anti_corrosion', 'VARCHAR(100)'),
        ('rubber_gasket_material', 'VARCHAR(100)'),
        ('turnout_rail', 'VARCHAR(100)'),
        ('using_unit', 'VARCHAR(100)'),
    ],
    'production_batches': [
        ('spec_splice_hole', 'VARCHAR(100)'),
        ('spec_gasket_hole', 'VARCHAR(100)'),
        ('anti_corrosion', 'VARCHAR(100)'),
        ('rubber_gasket_material', 'VARCHAR(100)'),
        ('turnout_rail', 'VARCHAR(100)'),
        ('using_unit', 'VARCHAR(100)'),
    ],
    'user': [
        # Q1（CWE-521）：弱口令账户的强制改密标记；老库由启动自愈补列，默认 0。
        ('must_change_password', 'BOOLEAN DEFAULT 0'),
    ],
    'products': [
        ('sellable_as_part', 'BOOLEAN'),
    ],
    'product_processes': [
        ('process_stage', 'VARCHAR(20)'),
        ('work_center_id', 'INTEGER'),
    ],
    'finished_product': [
        ('stock_kind', 'VARCHAR(20)'),
        ('workpiece_id', 'INTEGER'),
        ('product_id', 'INTEGER'),
    ],
    'nonconformity_records': [
        ('status', 'VARCHAR(20)'),
        ('approver_id', 'INTEGER'),
        ('approved_at', 'DATETIME'),
        ('rework_task_id', 'INTEGER'),
        ('scrap_cost', 'FLOAT'),
        ('workpiece_id', 'INTEGER'),
        # P1-3：处置对象口径（workpiece=生产质检 / goods_receipt=来料检）
        ('target_type', 'VARCHAR(20)'),
        ('target_id', 'INTEGER'),
    ],
    'raw_material_categories': [
        ('requires_approval', 'BOOLEAN'),
    ],
    'consumable_categories': [
        ('requires_approval', 'BOOLEAN'),
    ],
}


def _sql_type(coltype, dialect):
    """把 SQLite 口径的列类型翻成目标方言的合法 DDL 片段。

    PostgreSQL 是强类型：`ADD COLUMN x BOOLEAN DEFAULT 0` 会抛
    `DatatypeMismatch`（boolean 与 integer 不同型），必须写 FALSE/TRUE，
    而 SQLite 只认 0/1（2026-10-11 一次性 PG 测试库实测）。
    """
    if dialect != 'postgresql':
        return coltype
    return {
        'DATETIME': 'TIMESTAMP',
        'BOOLEAN': 'BOOLEAN',
        'BOOLEAN DEFAULT 0': 'BOOLEAN DEFAULT FALSE',
        'BOOLEAN DEFAULT 1': 'BOOLEAN DEFAULT TRUE',
        'FLOAT': 'DOUBLE PRECISION',
        'INTEGER': 'INTEGER',
    }.get(coltype, coltype)


def _build_alter_add_column(engine, table, name, coltype, dialect):
    """构造补列 DDL（B18）。独立成函数有两个原因：

    1. SQL 标识符必须按方言加引号 —— ``user`` 是 PostgreSQL 保留字，裸写成
       ``ALTER TABLE user ...`` 会抛 ``SyntaxError``，而调用方的 except 只记日志、
       不阻断启动，于是老库在生产上永远补不上这一列，SQLite 上又永远测不出来。
    2. 它让「有没有漏引号」可以被离线检查（``scripts/check_table_parity.py`` 只扫
       本函数体，注释里的示例串因此不会被误判）。
    """
    preparer = engine.dialect.identifier_preparer
    # quote() 自身带引号（PG 下 user -> "user"），模板里不要再手写引号，
    # 否则会拼出 ""user"" 这种零长度定界标识符。
    return 'ALTER TABLE {tbl} ADD COLUMN {col} {typ}'.format(
        tbl=preparer.quote(table),
        col=preparer.quote(name),
        typ=_sql_type(coltype, dialect),
    )


def _ensure_schema(app):
    """补齐缺失的表与列，保证老库可直接启动。"""
    try:
        engine = db.engine
        db.create_all()

        inspector = inspect(engine)
        existing_tables = set(inspector.get_table_names())
        dialect = engine.dialect.name
        for table, columns in _ENSURED_COLUMNS.items():
            if table not in existing_tables:
                continue
            present = {c['name'] for c in inspector.get_columns(table)}
            missing = [(name, coltype) for name, coltype in columns if name not in present]
            if not missing:
                continue
            with engine.begin() as conn:
                for name, coltype in missing:
                    conn.execute(text(
                        _build_alter_add_column(engine, table, name, coltype, dialect)
                    ))
                    app.logger.info(f'已为 {table} 添加缺失列：{name}')

        # 早期建库时 password_hash 是 VARCHAR(128)，装不下 scrypt 哈希。
        # 只有 Postgres 会因此拒写，SQLite 不校验长度也不支持改列类型。
        if dialect == 'postgresql' and 'user' in existing_tables:
            column = next((c for c in inspector.get_columns('user')
                           if c['name'] == 'password_hash'), None)
            width = getattr(column['type'], 'length', None) if column else None
            if width is not None and width < 255:
                with engine.begin() as conn:
                    conn.execute(text(
                        'ALTER TABLE "user" ALTER COLUMN password_hash TYPE VARCHAR(255)'
                    ))
                app.logger.info('已将 user.password_hash 放宽到 VARCHAR(255)')
    except Exception as e:
        app.logger.error(f'检查/补齐数据库结构失败: {e}')


def _seed_system_configs(app):
    """补齐缺失的系统配置项与默认质检模板（已存在的不覆盖）。

    B14-08：空库上 `inspection_templates` 原本零行，`mes_service.pick_template()`
    对生产质检与来料检都返回 `None`，质检流程整条不可用。这里复用既有的
    「只补缺不覆盖」初始化路径，把两类默认模板一并下发（幂等，重复启动不再插入，
    也不改写用户改过的模板/项目）。顺序上本函数在 `db.create_all()` 与
    `bootstrap_if_empty()` 之后执行，故登记 `created_by` 时账号已存在。
    """
    try:
        from app.models import SystemConfig
        created = SystemConfig.seed_defaults()
        if created:
            app.logger.info(f'已补齐 {created} 个系统配置项')
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'初始化系统配置项失败: {e}')

    try:
        from app.models import InspectionTemplate
        seeded = InspectionTemplate.seed_defaults()
        if seeded['templates']:
            app.logger.info(
                f"已补齐默认质检模板 {len(seeded['templates'])} 套"
                f"（{'/'.join(seeded['templates'])}，共 {seeded['items']} 个检验项目）"
            )
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'初始化默认质检模板失败: {e}')


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # 确保上传文件夹存在
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # 创建临时文件夹用于存储导出的文件
    temp_folder = os.path.join(app.config['UPLOAD_FOLDER'], 'temp')
    os.makedirs(temp_folder, exist_ok=True)
    app.config['TEMP_FOLDER'] = temp_folder

    db.init_app(app)
    login.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    bootstrap.init_app(app)
    login.login_view = 'auth.login'
    login.login_message = '请先登录'
    login.login_message_category = 'info'

    from app import permissions

    @login.unauthorized_handler
    def _unauthorized():
        """session 过期时 AJAX 请求要拿到 401 JSON，不能是登录页 HTML。

        默认行为是 302 到登录页，前端 `response.json()` 解析这段 HTML 会抛错，
        表现为一个和登录无关的脚本报错。这里统一拦在 Flask-Login 层，
        比逐个端点改装饰器顺序可靠——`@login_required` 是外层装饰器，
        排在它下面的 `@require_capability` 对未登录请求根本没有执行机会。
        """
        if permissions._wants_json():
            return jsonify({'success': False, 'message': '请先登录'}), 401
        flash(login.login_message, login.login_message_category)
        return redirect(url_for('auth.login', next=request.url))

    #: 框架级 HTTP 异常的**可读中文原因**（W4/P-09/P-12：4xx 必须带可读原因且不得泄漏实现细节）
    _HTTP_REASONS = {
        400: '请求参数有误',
        401: '请先登录',
        403: '权限不足',
        404: '资源不存在',
        405: '该路径不支持此 HTTP 方法',
        409: '资源状态冲突',
        413: '请求体过大',
        415: '请求的媒体类型不受支持，请改用 application/json',
        422: '请求参数无法处理',
        429: '请求过于频繁',
    }

    @app.errorhandler(HTTPException)
    def _http_error(e):
        """JSON 面（/api/、XHR、DELETE/PUT/PATCH）返回 JSON；页面面保持原响应。

        `get_or_404` / `first_or_404` / `get_json()` 抛出的异常在端点内被
        `_reraise_http` 重抛后走到这里（W4/P-09/P-12）——**不改变**端点自己
        `jsonify(...), 400` 返回的业务提示（那些不经过 errorhandler，RC-15）。
        """
        if permissions._wants_json():
            message = _HTTP_REASONS.get(e.code, e.description or e.name)
            return jsonify({'success': False, 'message': message}), e.code
        return e.get_response()

    permissions.init_app(app)

    @app.before_request
    def _force_password_change():
        """Q1/CWE-521：标记了的账户登录后只能停在改密页。

        挂在应用级而非逐个端点，是因为 `@login_required` 在 265 条规则里的
        装饰器顺序各不相同，逐个加会漏（同 `unauthorized_handler` 的理由）。
        改密页自身放行，否则无限重定向。
        """
        if not current_user.is_authenticated or not current_user.must_change_password:
            return None
        if request.endpoint in ('auth.change_password', 'auth.logout', 'static'):
            return None
        if permissions._wants_json():
            return jsonify({'success': False, 'message': '请先修改密码'}), 403
        return redirect(url_for('auth.change_password', next=request.full_path))

    with app.app_context():
        # 首先导入并创建所有模型
        from app import models

        _ensure_schema(app)
        # 空库首次启动时从 SQLite 种子库导入；库里已有账号则是空操作
        from app.db_bootstrap import bootstrap_if_empty
        bootstrap_if_empty(app)
        _seed_system_configs(app)

        # 然后注册蓝图
        from app.auth import bp as auth_bp
        app.register_blueprint(auth_bp, url_prefix='/auth')

        from app.main import bp as main_bp
        app.register_blueprint(main_bp)

    # 添加命令行工具
    @app.cli.command("init-db")
    @click.option('--username', default='admin', help='管理员用户名')
    @click.option('--password', required=True, prompt=True, hide_input=True,
                confirmation_prompt=True, help='管理员密码')
    def init_db(username, password):
        """Initialize database and create admin user"""
        with app.app_context():
            from app.models import User
            db.create_all()
            
            if not User.query.filter_by(username=username).first():
                admin = User(username=username, role='admin')
                admin.set_password(password)
                db.session.add(admin)
                db.session.commit()
                click.echo(f'管理员账户 {username} 创建成功')
            else:
                click.echo(f'管理员账户 {username} 已存在')

    return app 