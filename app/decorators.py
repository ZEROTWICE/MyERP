from functools import wraps
from flask import flash, redirect, url_for
from flask_login import current_user

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('您需要管理员权限才能访问此页面', 'warning')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function 