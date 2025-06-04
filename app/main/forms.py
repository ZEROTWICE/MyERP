from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, IntegerField, SelectField, TextAreaField, DateField, SubmitField, BooleanField, PasswordField, DecimalField, SelectMultipleField, HiddenField, MultipleFileField, DateTimeField
from wtforms.validators import DataRequired, NumberRange, Optional, Length, ValidationError, Email, URL
from datetime import datetime

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

class CustomerForm(FlaskForm):
    """客户表单"""
    customer_code = StringField('客户编码', validators=[DataRequired(), Length(1, 50)])
    customer_name = StringField('客户名称', validators=[DataRequired(), Length(1, 100)])
    customer_type = SelectField('客户类型', choices=[
        ('enterprise', '企业客户'),
        ('individual', '个人客户')
    ], default='enterprise')
    contact_person = StringField('联系人', validators=[Length(0, 50)])
    contact_phone = StringField('联系电话', validators=[Length(0, 20)])
    contact_email = StringField('联系邮箱', validators=[Optional(), Email(), Length(0, 100)])
    tax_number = StringField('税号', validators=[Length(0, 50)])
    credit_limit = FloatField('信用额度', validators=[Optional(), NumberRange(min=0)], default=0)
    payment_terms = StringField('付款条件', validators=[Length(0, 50)])
    industry = StringField('所属行业', validators=[Length(0, 50)])
    company_size = SelectField('公司规模', choices=[
        ('', '请选择'),
        ('small', '小型企业'),
        ('medium', '中型企业'),
        ('large', '大型企业')
    ])
    website = StringField('公司网站', validators=[Optional(), URL(), Length(0, 200)])
    status = SelectField('状态', choices=[
        ('active', '活跃'),
        ('inactive', '非活跃'),
        ('blacklist', '黑名单')
    ], default='active')
    notes = TextAreaField('备注')
    submit = SubmitField('保存')

class CustomerAddressForm(FlaskForm):
    """客户地址表单"""
    address_type = SelectField('地址类型', choices=[
        ('shipping', '收货地址'),
        ('billing', '账单地址'),
        ('office', '办公地址')
    ], default='shipping')
    contact_person = StringField('联系人', validators=[DataRequired(), Length(1, 50)])
    contact_phone = StringField('联系电话', validators=[DataRequired(), Length(1, 20)])
    province = StringField('省份', validators=[DataRequired(), Length(1, 50)])
    city = StringField('城市', validators=[DataRequired(), Length(1, 50)])
    district = StringField('区县', validators=[Length(0, 50)])
    detailed_address = StringField('详细地址', validators=[DataRequired(), Length(1, 200)])
    postal_code = StringField('邮政编码', validators=[Length(0, 10)])
    is_primary = BooleanField('设为主要地址')
    is_active = BooleanField('启用地址', default=True)
    notes = TextAreaField('备注')
    submit = SubmitField('保存')

class SalesOrderForm(FlaskForm):
    """销售订单表单"""
    order_source = StringField('订单来源', validators=[DataRequired(), Length(1, 50)])
    customer_id = SelectField('客户', coerce=int, validators=[DataRequired()])
    year_month = StringField('年月', validators=[DataRequired(), Length(7, 7)], 
                           render_kw={'placeholder': 'YYYY-MM', 'pattern': r'\d{4}-\d{2}'})
    order_date = DateTimeField('下单时间', default=datetime.utcnow, format='%Y-%m-%d %H:%M')
    status = SelectField('状态', choices=[
        ('pending', '待处理'),
        ('confirmed', '已确认'),
        ('in_production', '生产中'),
        ('completed', '已完成'),
        ('cancelled', '已取消')
    ], default='pending')
    notes = TextAreaField('备注')
    submit = SubmitField('保存')

class SalesOrderItemForm(FlaskForm):
    """销售订单行表单"""
    product_name = SelectField('产品名称', validators=[DataRequired()])
    drawing_number = SelectField('图号', validators=[DataRequired()])
    product_id = HiddenField()  # 隐藏字段，存储最终选择的产品ID
    quantity = IntegerField('数量', validators=[DataRequired(), NumberRange(min=1)])
    direction = StringField('开向', validators=[Length(0, 50)])
    
    # 规格型号（多选）
    spec_extended = StringField('加长', validators=[Length(0, 100)])
    spec_gasket = StringField('垫板', validators=[Length(0, 100)])
    spec_joint = StringField('接头', validators=[Length(0, 100)])
    spec_drilling = StringField('钻孔', validators=[Length(0, 100)])
    spec_other = StringField('其他', validators=[Length(0, 100)])
    spec_other_desc = StringField('其他规格描述', validators=[Length(0, 200)])
    
    customer_address_id = SelectField('收货地址', coerce=int, validators=[Optional()])
    order_time = DateTimeField('下单时间', default=datetime.utcnow, format='%Y-%m-%d %H:%M')
    station_notes = TextAreaField('到站备注')
    station_notes = TextAreaField('到站备注')
    station_notes = TextAreaField('到站备注')