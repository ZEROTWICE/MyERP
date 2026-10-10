import os
from datetime import timedelta
basedir = os.path.abspath(os.path.dirname(__file__))


def _normalize_database_url(url):
    """Heroku 风格 postgres:// 以及空值处理。"""
    if not url:
        return 'sqlite:///' + os.path.join(basedir, 'app.db')
    if url.startswith('postgres://'):
        url = 'postgresql://' + url[len('postgres://'):]
    return url


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev'
    SQLALCHEMY_DATABASE_URI = _normalize_database_url(os.environ.get('DATABASE_URL'))
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=60)
    # CWE-614: HTTPS 部署后设 SESSION_COOKIE_SECURE=true 阻止会话 cookie 经明文 HTTP 传输
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', '').lower() in ('1', 'true', 'yes')
    # 两地部署时给流水号加站点前缀，避免切主后撞号。空串表示单站点兼容旧 8 位号。
    SITE_CODE = (os.environ.get('SITE_CODE') or '').strip().upper()[:2]
    # Bootstrap 核心 css/js 本地供给（flask_bootstrap 蓝图静态目录，前缀 /bootstrap/static/）。
    # 必须在 bootstrap.init_app() 之前经 from_object 写入才生效（见 app/__init__.py）。
    BOOTSTRAP_SERVE_LOCAL = True
    
    # 修改上传文件夹路径
    UPLOAD_FOLDER = os.path.join(basedir, 'uploads')
    
    @staticmethod
    def init_app(app):
        # 确保上传文件夹存在
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True) 