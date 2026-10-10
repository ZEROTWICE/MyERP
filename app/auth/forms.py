from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, EqualTo, Length, ValidationError

class LoginForm(FlaskForm):
    username = StringField('用户名', validators=[DataRequired()])
    password = PasswordField('密码', validators=[DataRequired()])
    remember_me = BooleanField('记住我')
    submit = SubmitField('登录')

class ChangePasswordForm(FlaskForm):
    """Q1：自助改密（首次登录强制改密与日常改密共用同一张表单）。"""
    new_password = PasswordField('新密码', validators=[
        DataRequired(), Length(min=8, message='新密码至少 8 位')])
    confirm = PasswordField('确认新密码', validators=[
        DataRequired(), EqualTo('new_password', message='两次输入的新密码不一致')])
    submit = SubmitField('确认修改')

    def validate_new_password(self, field):
        from flask_login import current_user
        pwd = field.data or ''
        if pwd == getattr(current_user, 'username', None):
            raise ValidationError('新密码不能与用户名相同')
        if len(set(pwd)) == 1 or pwd.lower() in ('admin123', 'password', '12345678', '00000000'):
            raise ValidationError('新密码过于简单，请换一个')

