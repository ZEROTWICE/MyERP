from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
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
    ],
}


def _ensure_schema(app):
    """补齐缺失的表与列，保证老库可直接启动。"""
    try:
        engine = db.engine

        from app.models import SystemConfig
        SystemConfig.__table__.create(bind=engine, checkfirst=True)

        if engine.dialect.name != 'sqlite':
            return

        inspector = inspect(engine)
        existing_tables = set(inspector.get_table_names())
        for table, columns in _ENSURED_COLUMNS.items():
            if table not in existing_tables:
                continue
            present = {c['name'] for c in inspector.get_columns(table)}
            missing = [(name, coltype) for name, coltype in columns if name not in present]
            if not missing:
                continue
            with engine.begin() as conn:
                for name, coltype in missing:
                    conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {coltype}'))
                    app.logger.info(f'已为 {table} 添加缺失列：{name}')
    except Exception as e:
        app.logger.error(f'检查/补齐数据库结构失败: {e}')


def _seed_system_configs(app):
    """补齐缺失的系统配置项（已存在的不覆盖）。"""
    try:
        from app.models import SystemConfig
        created = SystemConfig.seed_defaults()
        if created:
            app.logger.info(f'已补齐 {created} 个系统配置项')
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'初始化系统配置项失败: {e}')


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
    permissions.init_app(app)

    with app.app_context():
        # 首先导入并创建所有模型
        from app import models

        _ensure_schema(app)
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