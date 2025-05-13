from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, IntegerField, SelectField, TextAreaField, DateField, SubmitField, BooleanField, PasswordField, DecimalField, SelectMultipleField, HiddenField, MultipleFileField
from wtforms.validators import DataRequired, NumberRange, Optional, Length, ValidationError, Email

class EmployeeForm(FlaskForm):
    employee_id = StringField('工号', validators=[DataRequired()])
    name = StringField('姓名', validators=[DataRequired()])
    position = StringField('职位', validators=[DataRequired()])
    base_salary = FloatField('基本工资', validators=[DataRequired(), NumberRange(min=0)])
    coefficient = FloatField('系数', validators=[DataRequired(), NumberRange(min=0)])
    department = StringField('部门', validators=[DataRequired()])
    hire_date = DateField('入职时间', validators=[DataRequired()])
    termination_date = DateField('离职时间', validators=[Optional()])
    is_admin = BooleanField('设为管理员')
    password = PasswordField('密码', validators=[Optional()])
    submit = SubmitField('提交')

    def validate_termination_date(self, field):
        if field.data and self.hire_date.data and field.data < self.hire_date.data:
            raise ValidationError('离职时间不能早于入职时间')

class ProcessPriceForm(FlaskForm):
    """工序价格表单"""
    process_code = StringField('工序编号', validators=[DataRequired('请输入工序编号'), Length(max=50)])
    process_name = StringField('工序名称', validators=[DataRequired('请输入工序名称'), Length(max=100)])
    component = StringField('部件', validators=[Optional(), Length(max=100)])
    drawing_no = StringField('图号', validators=[Optional(), Length(max=100)])
    model_no = StringField('型号', validators=[Optional(), Length(max=100)])
    price = FloatField('单价(元/件)', validators=[DataRequired('请输入单价')])
    effective_date = DateField('生效日期', validators=[DataRequired('请选择生效日期')])
    notes = TextAreaField('备注')
    price_type = SelectField('价格类型', choices=[('normal', '普通工价'), ('subtotal', '小计')], default='normal', validators=[DataRequired('请选择价格类型')])
    included_processes = SelectMultipleField('包含工序', coerce=int, validators=[Optional()])
    has_output = BooleanField('有产出', default=False)
    output_type = SelectField('产出类型', choices=[('', '请选择'), ('finished', '成品'), ('raw', '原材料')], validators=[Optional()])
    code_rule_id = SelectField('编码规则', coerce=int, validators=[Optional()])
    needs_inspection = BooleanField('需要检验', default=True)
    submit = SubmitField('提交')

    def validate_output_type(form, field):
        """验证产出类型"""
        if form.has_output.data and not field.data:
            raise ValidationError('如果有产出，请选择产出类型')
    
    def validate_code_rule_id(form, field):
        """验证编码规则"""
        # 只有当有产出并且选择了产出类型时才验证
        if form.has_output.data and form.output_type.data:
            # 允许值为0（表示"请选择"）
            if field.data == 0:
                return
            
            # 所有值都被视为有效，因为后端已经加载了所有可能的选项
            # 如果值无效，在routes.py中会处理（设为None）
            pass

    def validate_included_processes(self, field):
        if self.price_type.data == 'subtotal' and not field.data:
            raise ValidationError('小计必须包含至少一个工序')

    def validate_price(self, field):
        if self.price_type.data == 'normal' and not field.data:
            raise ValidationError('普通工价必须填写单价')
        elif self.price_type.data == 'normal' and field.data <= 0:
            raise ValidationError('单价必须大于0')

class ProcessPriceSearchForm(FlaskForm):
    search = StringField('搜索', render_kw={"placeholder": "输入工序编号、部件、图号或型号进行搜索"})
    show_all = BooleanField('显示所有工序')
    submit = SubmitField('搜索')

class ProductionRecordSearchForm(FlaskForm):
    search = StringField('搜索', render_kw={"placeholder": "输入员工姓名、工序编号、部件、图号或型号进行搜索"})
    submit = SubmitField('搜索')

class ProductionRecordForm(FlaskForm):
    """生产记录表单"""
    employee_id = SelectField('员工', coerce=int, validators=[DataRequired()])
    process_id = SelectField('工序', coerce=int, validators=[DataRequired()])
    quantity = IntegerField('数量', validators=[DataRequired(), NumberRange(min=1)])
    date = DateField('生产日期', validators=[DataRequired()])
    inspector = StringField('检验员', validators=[Optional(), Length(max=50)])
    notes = TextAreaField('备注')
    submit = SubmitField('提交')

class BonusPenaltySearchForm(FlaskForm):
    """奖惩记录搜索表单"""
    search = StringField('搜索关键词')
    type = SelectField('类型', choices=[('', '全部'), ('bonus', '奖金'), ('penalty', '罚款')])
    start_date = DateField('开始日期', validators=[Optional()])
    end_date = DateField('结束日期', validators=[Optional()])
    submit = SubmitField('搜索')

class BonusPenaltyForm(FlaskForm):
    """奖惩记录表单"""
    employee_id = SelectField('员工', coerce=int, validators=[DataRequired('请选择员工')])
    type = SelectField('类型', choices=[('bonus', '奖金'), ('penalty', '罚款')], validators=[DataRequired('请选择类型')])
    amount = DecimalField('金额', validators=[DataRequired('请输入金额'), NumberRange(min=0, message='金额必须大于0')])
    date = DateField('日期', validators=[DataRequired('请选择日期')])
    process_id = SelectField('相关工序', coerce=str, validators=[Optional()])
    reason = StringField('原因', validators=[DataRequired('请输入原因')])

class SalaryCalculationForm(FlaskForm):
    start_date = DateField('开始日期', validators=[DataRequired()])
    end_date = DateField('结束日期', validators=[DataRequired()])
    department = SelectField('部门', choices=[], validators=[Optional()])
    employee_id = SelectField('员工', choices=[], validators=[Optional()], coerce=int)
    submit = SubmitField('计算工资')

class AuditLogSearchForm(FlaskForm):
    start_date = DateField('开始日期', validators=[Optional()])
    end_date = DateField('结束日期', validators=[Optional()])
    action = SelectField('操作类型', choices=[
        ('', '全部'),
        ('添加员工', '添加员工'),
        ('更新员工', '更新员工'),
        ('删除员工', '删除员工'),
        ('添加工序价格', '添加工序价格'),
        ('添加生产记录', '添加生产记录'),
        ('添加奖金/罚款记录', '添加奖金/罚款记录')
    ], validators=[Optional()])
    user_id = SelectField('操作用户', coerce=int, validators=[Optional()])
    submit = SubmitField('查询')

class TaskAssignmentForm(FlaskForm):
    """任务分配表单"""
    employee_id = SelectField('员工', coerce=int, validators=[DataRequired()])
    process_id = SelectField('工序', coerce=int, validators=[DataRequired()])
    quantity = IntegerField('数量', validators=[DataRequired(), NumberRange(min=1)])
    target_date = DateField('目标完成日期', validators=[DataRequired()])
    notes = TextAreaField('备注')
    submit = SubmitField('分配任务')

class TaskSearchForm(FlaskForm):
    """任务搜索表单"""
    search = StringField('搜索')
    status = SelectField('状态', choices=[
        ('', '全部'),
        ('pending', '待开始'),
        ('in_progress', '进行中'),
        ('completed', '已完成'),
        ('cancelled', '已取消')
    ], default='')
    start_date = DateField('开始日期')
    end_date = DateField('结束日期')
    submit = SubmitField('搜索')

class ExportEmployeeForm(FlaskForm):
    """员工数据导出表单"""
    department = StringField('部门', validators=[Optional()])
    position = StringField('职位', validators=[Optional()])
    submit = SubmitField('导出')

class ExportProcessForm(FlaskForm):
    """工序数据导出表单"""
    component = StringField('部件', validators=[Optional()])
    model_no = StringField('型号', validators=[Optional()])
    start_date = DateField('生效日期从', validators=[Optional()])
    end_date = DateField('生效日期至', validators=[Optional()])
    submit = SubmitField('导出')

class ExportProductionRecordForm(FlaskForm):
    """生产记录导出表单"""
    employee_id = StringField('员工工号', validators=[Optional()])
    process_code = StringField('工序编号', validators=[Optional()])
    start_date = DateField('日期从', validators=[Optional()])
    end_date = DateField('日期至', validators=[Optional()])
    submit = SubmitField('导出')

class ExportBonusPenaltyForm(FlaskForm):
    """奖惩记录导出表单"""
    employee_id = StringField('员工工号', validators=[Optional()])
    type = SelectField('类型', 
                      choices=[('', '全部'), ('bonus', '奖金'), ('penalty', '罚款')],
                      validators=[Optional()])
    start_date = DateField('日期从', validators=[Optional()])
    end_date = DateField('日期至', validators=[Optional()])
    submit = SubmitField('导出')

class ExportTaskForm(FlaskForm):
    """任务导出表单"""
    employee_id = StringField('员工工号', validators=[Optional()])
    process_code = StringField('工序编号', validators=[Optional()])
    status = SelectField('状态',
                        choices=[('', '全部'), ('pending', '待处理'), ('in_progress', '进行中'),
                                ('completed', '已完成'), ('cancelled', '已取消')],
                        validators=[Optional()])
    start_date = DateField('分配日期从', validators=[Optional()])
    end_date = DateField('分配日期至', validators=[Optional()])
    submit = SubmitField('导出')