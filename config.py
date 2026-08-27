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
    # 两地部署时给流水号加站点前缀，避免切主后撞号。空串表示单站点兼容旧 8 位号。
    SITE_CODE = (os.environ.get('SITE_CODE') or '').strip().upper()[:2]
    
    # 修改上传文件夹路径
    UPLOAD_FOLDER = os.path.join(basedir, 'uploads')
    
    @staticmethod
    def init_app(app):
        # 确保上传文件夹存在
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True) 