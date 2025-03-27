from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from flask_bootstrap import Bootstrap5
import os
import click
from config import Config

db = SQLAlchemy()
login = LoginManager()
migrate = Migrate()
csrf = CSRFProtect()
bootstrap = Bootstrap5()

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

    with app.app_context():
        # 首先导入并创建所有模型
        from app import models

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