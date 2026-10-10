from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, current_user, login_required
from app import db
from .forms import LoginForm, ChangePasswordForm
from . import bp

def _safe_next(target):
    """只接受站内相对路径，防 open redirect。"""
    return target if target and target.startswith('/') and not target.startswith('//') else None

def _login_and_redirect(user, remember, next_target=None):
    """登录后落点：被强制改密（Q1）或显式带 next 时改道，否则回首页。"""
    login_user(user, remember=remember)
    if getattr(user, 'must_change_password', False) or next_target:
        return redirect(url_for('auth.change_password', next=next_target or request.full_path))
    return redirect(url_for('main.index'))

@bp.route('/login', methods=['GET', 'POST'])
@bp.route('/', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    form = LoginForm()
    next_target = _safe_next(request.args.get('next'))
    if form.validate_on_submit():
        from app.models import User
        user = User.query.filter_by(username=form.username.data).first()
        if user is None or not user.check_password(form.password.data):
            flash('无效的用户名或密码', 'danger')
            return redirect(url_for('auth.login'))
        # Q1：用户名==密码的老账户（历史遗留）登录即打上强制改密标记。
        if user.username == form.password.data and not user.must_change_password:
            user.must_change_password = True
            db.session.commit()
            flash('检测到初始密码与用户名相同，请先修改密码', 'warning')
        return _login_and_redirect(user, form.remember_me.data, next_target)
    return render_template('auth/login.html', title='登录', form=form)

@bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Q1 自助改密：不校验原密码（本页只在已登录会话内可达，且强制改密场景下
    原密码就是刚提交的登录口令）；改完清标记并回原落点。"""
    form = ChangePasswordForm()
    if form.validate_on_submit():
        if current_user.check_password(form.new_password.data):
            flash('新密码不能与原密码相同', 'warning')
            return redirect(url_for('auth.change_password', next=request.args.get('next')))
        current_user.set_password(form.new_password.data)
        current_user.must_change_password = False
        db.session.commit()
        flash('密码已修改', 'success')
        return redirect(_safe_next(request.args.get('next')) or url_for('main.index'))
    return render_template('auth/change_password.html', title='修改密码', form=form)

@bp.route('/logout', methods=['GET', 'POST'])
def logout():
    logout_user()
    return redirect(url_for('main.index'))

