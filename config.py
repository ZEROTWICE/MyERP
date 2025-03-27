import os
from datetime import timedelta
basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'app.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=60)
    
    # 修改上传文件夹路径
    UPLOAD_FOLDER = os.path.join(basedir, 'uploads')
    
    @staticmethod
    def init_app(app):
        # 确保上传文件夹存在
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True) 