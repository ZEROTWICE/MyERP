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
    
    # 规格型号字段
    spec_extended = StringField('加长', validators=[Length(0, 100)])
    spec_gasket = StringField('垫板', validators=[Length(0, 100)])
    spec_joint = StringField('接头', validators=[Length(0, 100)])
    spec_drilling = StringField('钻孔', validators=[Length(0, 100)])
    spec_other = StringField('其他', validators=[Length(0, 100)])
    spec_other_desc = StringField('其他规格描述', validators=[Length(0, 200)])
    direction = StringField('开向', validators=[Length(0, 50)])
    
    submit = SubmitField('分配任务')

class TaskSearchForm(FlaskForm):
    """任务搜索表单"""
    search = StringField('搜索')
    status = SelectField('状态', choices=[
        ('', '全部'),
        ('pending', '未完成'),
        ('in_progress', '进行中'),
        ('completed', '已完成'),
        ('cancelled', '已取消')
    ], default='pending')
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

class ExportProductForm(FlaskForm):
    """产品数据导出表单"""
    category = StringField('产品类别', validators=[Optional()])
    status = SelectField('状态', choices=[
        ('', '全部'),
        ('active', '启用'),
        ('inactive', '停用'),
        ('obsolete', '淘汰')
    ], validators=[Optional()])
    start_date = DateField('创建日期从', validators=[Optional()])
    end_date = DateField('创建日期至', validators=[Optional()])
    submit = SubmitField('导出')

class ProductImportForm(FlaskForm):
    """产品导入表单"""
    file = MultipleFileField('Excel文件', validators=[DataRequired('请选择文件')])
    submit = SubmitField('导入')

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
    submit = SubmitField('保存')

class ProductionOrderForm(FlaskForm):
    """生产订单表单"""
    product_id = SelectField('产品', coerce=int, validators=[DataRequired()])
    planned_quantity = IntegerField('计划数量', validators=[DataRequired(), NumberRange(min=1)])
    planned_start_date = DateField('计划开始日期', validators=[DataRequired()])
    planned_end_date = DateField('计划完成日期', validators=[DataRequired()])
    actual_start_date = DateField('实际开始日期')
    actual_end_date = DateField('实际完成日期')
    status = SelectField('状态', 
                        choices=[('pending', '待开始'), ('in_progress', '进行中'), 
                                ('completed', '已完成'), ('cancelled', '已取消')],
                        default='pending')
    priority = SelectField('优先级',
                          choices=[('low', '低优先级'), ('normal', '普通'), ('high', '高优先级')],
                          default='normal')
    
    # 规格型号（多选）
    spec_extended = StringField('加长', validators=[Length(0, 100)])
    spec_gasket = StringField('垫板', validators=[Length(0, 100)])
    spec_joint = StringField('接头', validators=[Length(0, 100)])
    spec_drilling = StringField('钻孔', validators=[Length(0, 100)])
    spec_other = StringField('其他', validators=[Length(0, 100)])
    spec_other_desc = StringField('其他规格描述', validators=[Length(0, 200)])
    direction = StringField('开向', validators=[Length(0, 50)])
    
    notes = TextAreaField('备注', validators=[Length(0, 500)])
    
    def validate_planned_end_date(self, field):
        if field.data and self.planned_start_date.data:
            if field.data <= self.planned_start_date.data:
                raise ValidationError('计划完成日期必须晚于计划开始日期')
    
    def validate_actual_end_date(self, field):
        if field.data and self.actual_start_date.data:
            if field.data <= self.actual_start_date.data:
                raise ValidationError('实际完成日期必须晚于实际开始日期')

class NotificationRuleForm(FlaskForm):
    """通知规则表单"""
    rule_name = StringField('规则名称', validators=[DataRequired(), Length(1, 100)])
    trigger_type = SelectField('触发类型', validators=[DataRequired()], 
                              choices=[
                                  ('process_change', '工艺变更'),
                                  ('spec_change', '规格变更'),
                                  ('inventory_warning', '库存预警'),
                                  ('production_order_status', '生产订单状态变更'),
                                  ('task_assignment', '任务分配'),
                                  ('task_overdue', '任务逾期'),
                                  ('quality_issue', '质量问题'),
                                  ('system_maintenance', '系统维护'),
                              ])
    receiver_type = SelectField('接收者类型', validators=[DataRequired()],
                               choices=[
                                   ('user', '指定用户'),
                                   ('role', '指定角色'),
                                   ('department', '指定部门')
                               ])
    priority = IntegerField('优先级', validators=[DataRequired()], default=0)
    is_active = BooleanField('启用', default=True)
    
    # 接收者配置 - 通过JavaScript动态填充
    receiver_config = HiddenField('接收者配置')
    
    submit = SubmitField('保存')

class NotificationTemplateForm(FlaskForm):
    """通知模板表单"""
    template_code = StringField('模板编码', validators=[DataRequired(), Length(1, 50)])
    template_name = StringField('模板名称', validators=[DataRequired(), Length(1, 100)])
    trigger_type = SelectField('适用触发类型', validators=[DataRequired()],
                              choices=[
                                  ('process_change', '工艺变更'),
                                  ('spec_change', '规格变更'),
                                  ('inventory_warning', '库存预警'),
                                  ('production_order_status', '生产订单状态变更'),
                                  ('task_assignment', '任务分配'),
                                  ('task_overdue', '任务逾期'),
                                  ('quality_issue', '质量问题'),
                                  ('system_maintenance', '系统维护'),
                              ])
    title_template = StringField('标题模板', validators=[DataRequired(), Length(1, 200)])
    content_template = TextAreaField('内容模板', validators=[DataRequired()])
    notification_type = SelectField('通知类型', validators=[DataRequired()],
                                   choices=[
                                       ('info', '信息'),
                                       ('warning', '警告'),
                                       ('error', '错误'),
                                       ('success', '成功')
                                   ], default='info')
    variables = TextAreaField('可用变量（JSON格式）')
    is_active = BooleanField('启用', default=True)
    
    submit = SubmitField('保存')

class GlobalSearchForm(FlaskForm):
    """全局搜索表单"""
    query = StringField('搜索关键词', validators=[DataRequired(message='请输入搜索关键词')])
    search_type = SelectField('搜索范围', choices=[
        ('all', '全部数据'),
        ('employees', '员工信息'),
        ('process_prices', '工序价格'),
        ('production_records', '生产记录'),
        ('products', '产品管理'),
        ('inventory', '库存管理'),
        ('customers', '客户管理'),
        ('sales_orders', '销售订单'),
        ('production_orders', '生产订单')
    ], default='all')
    
class AdvancedSearchForm(FlaskForm):
    """高级搜索表单"""
    
    # 员工搜索
    employee_name = StringField('员工姓名')
    employee_id = StringField('工号')
    department = StringField('部门')
    position = StringField('职位')
    is_active = SelectField('在职状态', choices=[('', '全部'), ('1', '在职'), ('0', '离职')])
    
    # 工序价格搜索
    process_code = StringField('工序编号')
    process_name = StringField('工序名称')
    component = StringField('部件')
    drawing_no = StringField('图号')
    model_no = StringField('型号')
    
    # 生产记录搜索
    production_date_start = DateField('生产日期开始')
    production_date_end = DateField('生产日期结束')
    
    # 产品搜索
    product_code = StringField('产品编码')
    product_name = StringField('产品名称')
    drawing_number = StringField('图号')
    model = StringField('型号')
    
    # 库存搜索
    inventory_type = SelectField('库存类型', choices=[('', '全部'), ('raw', '原材料'), ('finished', '成品')])
    supplier = StringField('供应商')
    material_name = StringField('品名')
    storage_date_start = DateField('入库日期开始')
    storage_date_end = DateField('入库日期结束')
    
    # 客户搜索
    customer_code = StringField('客户编码')
    customer_name = StringField('客户名称')
    contact_person = StringField('联系人')
    customer_type = SelectField('客户类型', choices=[('', '全部'), ('enterprise', '企业'), ('individual', '个人')])
    
    # 销售订单搜索
    sales_order_number = StringField('订单编号')
    order_source = StringField('订单来源')
    year_month = StringField('年月 (YYYY-MM)')
    order_status = SelectField('订单状态', choices=[
        ('', '全部'),
        ('pending', '待处理'),
        ('confirmed', '已确认'),
        ('in_production', '生产中'),
        ('completed', '已完成'),
        ('cancelled', '已取消')
    ])
    
    # 生产订单搜索
    production_order_number = StringField('生产订单编号')
    production_status = SelectField('生产状态', choices=[
        ('', '全部'),
        ('pending', '待开始'),
        ('in_progress', '进行中'),
        ('completed', '已完成'),
        ('cancelled', '已取消')
    ])
    planned_start_date = DateField('计划开始日期')
    planned_end_date = DateField('计划结束日期')
    
    submit = SubmitField('搜索')

class RawMaterialCategoryForm(FlaskForm):
    """原材料品类管理表单"""
    name = StringField('品类名称', validators=[DataRequired('请输入品类名称'), Length(max=100)])
    code = StringField('品类编码', validators=[DataRequired('请输入品类编码'), Length(max=20)])
    description = TextAreaField('品类描述', validators=[Optional(), Length(max=500)])
    is_active = BooleanField('是否启用', default=True)
    submit = SubmitField('保存')

class RawMaterialInboundForm(FlaskForm):
    """原材料入库表单"""
    supplier = StringField('供应商', validators=[DataRequired('请输入供应商'), Length(max=100)])
    category_id = SelectField('品类', coerce=int, validators=[DataRequired('请选择品类')])
    melt_number = StringField('原料冶炼炉号', validators=[Optional(), Length(max=100)])
    supplier_number = StringField('供应商编号', validators=[DataRequired('请输入供应商编号'), Length(max=100)])
    internal_number = StringField('内部编号', validators=[Optional(), Length(max=100)], description="留空则自动生成")
    has_sample = BooleanField('是否带样品', default=False)
    quantity = FloatField('数量', validators=[DataRequired('请输入数量'), NumberRange(min=0.01, message='数量必须大于0')])
    storage_date = DateField('入库时间', validators=[DataRequired('请选择入库时间')], default=datetime.today)
    notes = TextAreaField('备注', validators=[Optional(), Length(max=500)])
    submit = SubmitField('确认入库')
    
    def __init__(self, *args, **kwargs):
        super(RawMaterialInboundForm, self).__init__(*args, **kwargs)
        from app.models import RawMaterialCategory
        self.category_id.choices = [(c.id, c.name) for c in RawMaterialCategory.query.filter_by(is_active=True).all()]

class FinishedProductInboundForm(FlaskForm):
    """成品入库表单"""
    product_number = StringField('产品编号', validators=[DataRequired('请输入产品编号'), Length(max=50)])
    drawing_number = StringField('图号', validators=[DataRequired('请输入图号'), Length(max=100)])
    model = StringField('型号', validators=[DataRequired('请输入型号'), Length(max=100)])
    inspector = StringField('检验员', validators=[DataRequired('请输入检验员'), Length(max=50)])
    production_date = DateField('生产日期', validators=[DataRequired('请选择生产日期')])
    quantity = IntegerField('数量', validators=[DataRequired('请输入数量'), NumberRange(min=1, message='数量必须大于0')])
    storage_date = DateField('入库时间', validators=[DataRequired('请选择入库时间')], default=datetime.today)
    notes = TextAreaField('备注', validators=[Optional(), Length(max=500)])
    submit = SubmitField('确认入库')

class InventoryInboundForm(FlaskForm):
    """入库管理表单"""
    inventory_type = SelectField('库存类型', choices=[
        ('raw', '原材料'),
        ('finished', '成品')
    ], validators=[DataRequired('请选择库存类型')])
    
    # 原材料字段
    supplier = StringField('供应商', validators=[Optional(), Length(max=100)])
    material_name = StringField('品名', validators=[Optional(), Length(max=100)])
    melt_number = StringField('原料冶炼炉号', validators=[Optional(), Length(max=100)])
    supplier_number = StringField('供应商编号', validators=[Optional(), Length(max=100)])
    internal_number = StringField('内部编号', validators=[Optional(), Length(max=100)])
    has_sample = BooleanField('是否带样品', default=False)
    
    # 成品字段
    product_number = StringField('产品编号', validators=[Optional(), Length(max=50)])
    drawing_number = StringField('图号', validators=[Optional(), Length(max=100)])
    model = StringField('型号', validators=[Optional(), Length(max=100)])
    inspector = StringField('检验员', validators=[Optional(), Length(max=50)])
    production_date = DateField('生产日期', validators=[Optional()])
    
    # 通用字段
    quantity = FloatField('数量', validators=[DataRequired('请输入数量'), NumberRange(min=0.01, message='数量必须大于0')])
    storage_date = DateField('入库时间', validators=[DataRequired('请选择入库时间')], default=datetime.today)
    notes = TextAreaField('备注', validators=[Optional(), Length(max=500)])
    
    submit = SubmitField('确认入库')
    
    def validate(self, extra_validators=None):
        """自定义验证"""
        if not super().validate(extra_validators):
            return False
        
        if self.inventory_type.data == 'raw':
            # 原材料必需字段验证
            if not self.supplier.data:
                self.supplier.errors.append('供应商不能为空')
                return False
            if not self.material_name.data:
                self.material_name.errors.append('品名不能为空')
                return False
            if not self.supplier_number.data:
                self.supplier_number.errors.append('供应商编号不能为空')
                return False
        elif self.inventory_type.data == 'finished':
            # 成品必需字段验证
            if not self.product_number.data:
                self.product_number.errors.append('产品编号不能为空')
                return False
            if not self.drawing_number.data:
                self.drawing_number.errors.append('图号不能为空')
                return False
            if not self.model.data:
                self.model.errors.append('型号不能为空')
                return False
            if not self.inspector.data:
                self.inspector.errors.append('检验员不能为空')
                return False
            if not self.production_date.data:
                self.production_date.errors.append('生产日期不能为空')
                return False
        
        return True

class ConsumableCategoryForm(FlaskForm):
    """易耗品品类管理表单"""
    name = StringField('品类名称', validators=[DataRequired('请输入品类名称'), Length(max=100)])
    code = StringField('品类编码', validators=[DataRequired('请输入品类编码'), Length(max=20)])
    description = TextAreaField('品类描述', validators=[Optional(), Length(max=500)])
    is_active = BooleanField('是否启用', default=True)
    submit = SubmitField('保存')

class ConsumableInboundForm(FlaskForm):
    """易耗品入库表单"""
    supplier = StringField('供应商', validators=[DataRequired('请输入供应商'), Length(max=100)])
    category_id = SelectField('品类', coerce=int, validators=[DataRequired('请选择品类')])
    specification = StringField('规格型号', validators=[Optional(), Length(max=200)])
    supplier_number = StringField('供应商编号', validators=[DataRequired('请输入供应商编号'), Length(max=100)])
    internal_number = StringField('内部编号', validators=[Optional(), Length(max=100)], description="留空则自动生成")
    quantity = FloatField('数量', validators=[DataRequired('请输入数量'), NumberRange(min=0.01, message='数量必须大于0')])
    unit = StringField('单位', validators=[DataRequired('请输入单位'), Length(max=20)], default='个')
    unit_price = FloatField('单价', validators=[Optional(), NumberRange(min=0, message='单价不能为负数')], default=0)
    expiry_date = DateField('过期日期', validators=[Optional()])
    storage_location = StringField('存放位置', validators=[Optional(), Length(max=100)])
    min_stock_level = FloatField('最低库存预警', validators=[Optional(), NumberRange(min=0, message='预警值不能为负数')], default=0)
    storage_date = DateField('入库时间', validators=[DataRequired('请选择入库时间')], default=datetime.today)
    notes = TextAreaField('备注', validators=[Optional(), Length(max=500)])
    submit = SubmitField('确认入库')
    
    def __init__(self, *args, **kwargs):
        super(ConsumableInboundForm, self).__init__(*args, **kwargs)
        from app.models import ConsumableCategory
        self.category_id.choices = [(c.id, c.name) for c in ConsumableCategory.query.filter_by(is_active=True).all()]

class ConsumableSearchForm(FlaskForm):
    """易耗品搜索表单"""
    search = StringField('搜索', render_kw={"placeholder": "输入供应商、品类名称、规格型号或内部编号进行搜索"})
    category_id = SelectField('品类', coerce=int, validators=[Optional()])
    status = SelectField('状态', choices=[
        ('', '全部'),
        ('in_stock', '在库'),
        ('used', '已使用'),
        ('scrapped', '报废'),
        ('expired', '过期')
    ], default='')
    supplier = StringField('供应商')
    storage_date_start = DateField('入库日期开始')
    storage_date_end = DateField('入库日期结束')
    low_stock_only = BooleanField('仅显示低库存')
    expired_only = BooleanField('仅显示已过期')
    expiring_soon = BooleanField('仅显示即将过期(30天内)')
    submit = SubmitField('搜索')
    
    def __init__(self, *args, **kwargs):
        super(ConsumableSearchForm, self).__init__(*args, **kwargs)
        from app.models import ConsumableCategory
        categories = [(0, '全部品类')] + [(c.id, c.name) for c in ConsumableCategory.query.filter_by(is_active=True).all()]
        self.category_id.choices = categories

class ConsumableUsageForm(FlaskForm):
    """易耗品使用表单"""
    consumable_id = HiddenField('易耗品ID', validators=[DataRequired()])
    usage_quantity = FloatField('使用数量', validators=[DataRequired('请输入使用数量'), NumberRange(min=0.01, message='使用数量必须大于0')])
    usage_date = DateField('使用日期', validators=[DataRequired('请选择使用日期')], default=datetime.today)
    used_by = StringField('使用人', validators=[DataRequired('请输入使用人'), Length(max=50)])
    usage_purpose = StringField('使用用途', validators=[Optional(), Length(max=200)])
    notes = TextAreaField('备注', validators=[Optional(), Length(max=500)])
    submit = SubmitField('确认使用')

class ConsumableUpdateForm(FlaskForm):
    """易耗品更新表单"""
    supplier = StringField('供应商', validators=[DataRequired('请输入供应商'), Length(max=100)])
    category_id = SelectField('品类', coerce=int, validators=[DataRequired('请选择品类')])
    specification = StringField('规格型号', validators=[Optional(), Length(max=200)])
    supplier_number = StringField('供应商编号', validators=[DataRequired('请输入供应商编号'), Length(max=100)])
    quantity = FloatField('数量', validators=[DataRequired('请输入数量'), NumberRange(min=0, message='数量不能为负数')])
    unit = StringField('单位', validators=[DataRequired('请输入单位'), Length(max=20)])
    unit_price = FloatField('单价', validators=[Optional(), NumberRange(min=0, message='单价不能为负数')])
    expiry_date = DateField('过期日期', validators=[Optional()])
    storage_location = StringField('存放位置', validators=[Optional(), Length(max=100)])
    min_stock_level = FloatField('最低库存预警', validators=[Optional(), NumberRange(min=0, message='预警值不能为负数')])
    status = SelectField('状态', choices=[
        ('in_stock', '在库'),
        ('used', '已使用'),
        ('scrapped', '报废'),
        ('expired', '过期')
    ], validators=[DataRequired('请选择状态')])
    notes = TextAreaField('备注', validators=[Optional(), Length(max=500)])
    submit = SubmitField('更新')
    
    def __init__(self, *args, **kwargs):
        super(ConsumableUpdateForm, self).__init__(*args, **kwargs)
        from app.models import ConsumableCategory
        self.category_id.choices = [(c.id, c.name) for c in ConsumableCategory.query.filter_by(is_active=True).all()]

# 物料领用相关表单
class MaterialRequisitionRecordForm(FlaskForm):
    """物料领用记录表单"""
    employee_id = SelectField('领用人', coerce=int, validators=[DataRequired('请选择领用人')])
    purpose = StringField('领用用途', validators=[DataRequired('请输入领用用途'), Length(max=200)])
    requisition_date = DateField('领用日期', validators=[DataRequired('请选择领用日期')])
    notes = TextAreaField('备注', validators=[Optional(), Length(max=500)])
    
    # 物料明细字段（动态添加）
    materials_data = HiddenField('物料数据')
    
    submit = SubmitField('保存记录')
    
    def __init__(self, *args, **kwargs):
        super(MaterialRequisitionRecordForm, self).__init__(*args, **kwargs)
        from app.models import Employee
        
        # 加载员工选项
        employees = Employee.query.filter_by(is_active=True).all()
        self.employee_id.choices = [(e.id, f"{e.name} ({e.employee_id})") for e in employees]

class MaterialRequisitionItemForm(FlaskForm):
    """物料领用明细表单（用于表格行添加）"""
    material_type = SelectField('物料类型', choices=[
        ('raw', '原材料'),
        ('consumable', '易耗品'),
        ('finished', '成品')
    ], validators=[DataRequired('请选择物料类型')])
    material_name = StringField('物料名称', validators=[DataRequired('请输入物料名称'), Length(max=100)])
    quantity = FloatField('领用数量', validators=[DataRequired('请输入领用数量'), NumberRange(min=0.01, message='数量必须大于0')])
    unit = StringField('单位', validators=[DataRequired('请输入单位'), Length(max=20)], default='件')
    notes = TextAreaField('备注', validators=[Optional(), Length(max=500)])
    submit = SubmitField('添加到表格')

class MaterialRequisitionSearchForm(FlaskForm):
    """物料领用记录搜索表单"""
    search = StringField('搜索', render_kw={"placeholder": "输入领用单号、员工姓名、部门或用途进行搜索"})
    department = StringField('部门')
    employee_id = SelectField('领用人', coerce=int, validators=[Optional()])
    requisition_date_start = DateField('领用日期开始')
    requisition_date_end = DateField('领用日期结束')
    submit = SubmitField('搜索')
    
    def __init__(self, *args, **kwargs):
        super(MaterialRequisitionSearchForm, self).__init__(*args, **kwargs)
        from app.models import Employee
        employees = [(0, '全部员工')] + [(e.id, f"{e.name} ({e.employee_id})") for e in Employee.query.filter_by(is_active=True).all()]
        self.employee_id.choices = employees

# 物料归还相关表单
class MaterialReturnForm(FlaskForm):
    """物料归还表单"""
    employee_id = SelectField('归还人', coerce=int, validators=[DataRequired('请选择归还人')])
    department = StringField('归还部门', validators=[DataRequired('请输入归还部门'), Length(max=50)])
    return_reason = StringField('归还原因', validators=[DataRequired('请输入归还原因'), Length(max=200)])
    original_requisition_id = SelectField('原领用单', coerce=int, validators=[Optional()])
    returned_date = DateTimeField('归还时间', validators=[DataRequired('请选择归还时间')], default=datetime.utcnow)
    notes = TextAreaField('备注', validators=[Optional(), Length(max=500)])
    submit = SubmitField('提交归还')
    
    def __init__(self, *args, **kwargs):
        super(MaterialReturnForm, self).__init__(*args, **kwargs)
        from app.models import Employee, MaterialRequisition
        
        # 加载员工选项
        employees = Employee.query.filter_by(is_active=True).all()
        self.employee_id.choices = [(e.id, f"{e.name} ({e.employee_id})") for e in employees]
        
        # 加载已完成的领用单
        requisitions = MaterialRequisition.query.filter_by(status='completed').order_by(MaterialRequisition.requested_date.desc()).limit(50).all()
        self.original_requisition_id.choices = [(0, '无关联领用单')] + [(r.id, f"{r.requisition_number} - {r.employee.name}") for r in requisitions]

class MaterialReturnItemForm(FlaskForm):
    """物料归还明细表单"""
    material_type = SelectField('物料类型', choices=[
        ('raw', '原材料'),
        ('consumable', '易耗品'),
        ('finished', '成品')
    ], validators=[DataRequired('请选择物料类型')])
    material_id = SelectField('物料', coerce=int, validators=[DataRequired('请选择物料')])
    quantity = FloatField('归还数量', validators=[DataRequired('请输入归还数量'), NumberRange(min=0.01, message='数量必须大于0')])
    condition = SelectField('物料状态', choices=[
        ('good', '完好'),
        ('damaged', '损坏'),
        ('expired', '过期')
    ], default='good', validators=[DataRequired('请选择物料状态')])
    unit = StringField('单位', validators=[DataRequired('请输入单位'), Length(max=20)], default='件')
    notes = TextAreaField('备注', validators=[Optional(), Length(max=500)])
    submit = SubmitField('添加')

class MaterialReturnSearchForm(FlaskForm):
    """物料归还搜索表单"""
    search = StringField('搜索', render_kw={"placeholder": "输入归还单号、员工姓名、部门或原因进行搜索"})
    status = SelectField('状态', choices=[
        ('', '全部'),
        ('pending', '待确认'),
        ('confirmed', '已确认'),
        ('rejected', '已拒绝')
    ], default='')
    department = StringField('部门')
    employee_id = SelectField('归还人', coerce=int, validators=[Optional()])
    returned_date_start = DateField('归还日期开始')
    returned_date_end = DateField('归还日期结束')
    submit = SubmitField('搜索')
    
    def __init__(self, *args, **kwargs):
        super(MaterialReturnSearchForm, self).__init__(*args, **kwargs)
        from app.models import Employee
        employees = [(0, '全部员工')] + [(e.id, f"{e.name} ({e.employee_id})") for e in Employee.query.filter_by(is_active=True).all()]
        self.employee_id.choices = employees

class MaterialReturnConfirmForm(FlaskForm):
    """物料归还确认表单"""
    action = SelectField('确认操作', choices=[
        ('confirm', '确认归还'),
        ('reject', '拒绝归还')
    ], validators=[DataRequired('请选择确认操作')])
    notes = TextAreaField('确认意见', validators=[Optional(), Length(max=500)])
    submit = SubmitField('提交确认')

# 库存盘点相关表单
class InventoryCountForm(FlaskForm):
    """库存盘点表单"""
    count_name = StringField('盘点名称', validators=[DataRequired('请输入盘点名称'), Length(max=100)])
    count_type = SelectField('盘点类型', choices=[
        ('full', '全盘'),
        ('partial', '抽盘'),
        ('cycle', '循环盘点')
    ], default='full', validators=[DataRequired('请选择盘点类型')])
    count_scope = SelectField('盘点范围', choices=[
        ('all', '全部'),
        ('raw', '原材料'),
        ('consumable', '易耗品'),
        ('finished', '成品')
    ], default='all', validators=[DataRequired('请选择盘点范围')])
    warehouse_location = StringField('仓库位置', validators=[Optional(), Length(max=100)])
    planned_date = DateField('计划盘点日期', validators=[DataRequired('请选择计划盘点日期')])
    count_team = SelectMultipleField('盘点小组', coerce=int, validators=[DataRequired('请选择盘点小组成员')])
    notes = TextAreaField('备注', validators=[Optional(), Length(max=500)])
    submit = SubmitField('创建盘点')
    
    def __init__(self, *args, **kwargs):
        super(InventoryCountForm, self).__init__(*args, **kwargs)
        from app.models import User
        users = User.query.filter_by(role='admin').all() + User.query.filter_by(role='manager').all()
        self.count_team.choices = [(u.id, u.username) for u in users]

class InventoryCountSearchForm(FlaskForm):
    """库存盘点搜索表单"""
    search = StringField('搜索', render_kw={"placeholder": "输入盘点单号或盘点名称进行搜索"})
    status = SelectField('状态', choices=[
        ('', '全部'),
        ('draft', '草稿'),
        ('in_progress', '进行中'),
        ('completed', '已完成'),
        ('approved', '已审批'),
        ('cancelled', '已取消')
    ], default='')
    count_type = SelectField('盘点类型', choices=[
        ('', '全部'),
        ('full', '全盘'),
        ('partial', '抽盘'),
        ('cycle', '循环盘点')
    ], default='')
    count_scope = SelectField('盘点范围', choices=[
        ('', '全部'),
        ('all', '全部物料'),
        ('raw', '原材料'),
        ('consumable', '易耗品'),
        ('finished', '成品')
    ], default='')
    employee_id = SelectField('盘点人', coerce=int, validators=[Optional()])
    planned_date_start = DateField('计划日期开始')
    planned_date_end = DateField('计划日期结束')
    submit = SubmitField('搜索')
    
    def __init__(self, *args, **kwargs):
        super(InventoryCountSearchForm, self).__init__(*args, **kwargs)
        from app.models import Employee
        employees = [(0, '全部员工')] + [(e.id, f"{e.name} ({e.employee_id})") for e in Employee.query.filter_by(is_active=True).all()]
        self.employee_id.choices = employees

class InventoryCountItemForm(FlaskForm):
    """库存盘点明细表单"""
    actual_quantity = FloatField('实际数量', validators=[DataRequired('请输入实际数量'), NumberRange(min=0, message='数量不能为负数')])
    variance_reason = StringField('差异原因', validators=[Optional(), Length(max=200)])
    notes = TextAreaField('备注', validators=[Optional(), Length(max=500)])
    submit = SubmitField('保存盘点结果')

class InventoryCountBatchForm(FlaskForm):
    """批量盘点表单"""
    count_data = TextAreaField('盘点数据', validators=[DataRequired('请输入盘点数据')], 
                              render_kw={"placeholder": "格式：物料编号,实际数量,差异原因\n每行一条记录"})
    submit = SubmitField('批量提交')

class InventoryAdjustmentForm(FlaskForm):
    """库存调整表单"""
    adjustment_reason = StringField('调整原因', validators=[DataRequired('请输入调整原因'), Length(max=200)])
    notes = TextAreaField('调整说明', validators=[Optional(), Length(max=500)])
    submit = SubmitField('应用调整')

# 物料管理统计表单
class MaterialStatisticsForm(FlaskForm):
    """物料管理统计表单"""
    report_type = SelectField('报表类型', choices=[
        ('requisition_summary', '领用汇总'),
        ('return_summary', '归还汇总'),
        ('inventory_turnover', '库存周转'),
        ('material_usage', '物料使用分析'),
        ('department_usage', '部门使用统计')
    ], validators=[DataRequired('请选择报表类型')])
    date_range = SelectField('时间范围', choices=[
        ('today', '今天'),
        ('week', '本周'),
        ('month', '本月'),
        ('quarter', '本季度'),
        ('year', '本年'),
        ('custom', '自定义')
    ], default='month', validators=[DataRequired('请选择时间范围')])
    start_date = DateField('开始日期', validators=[Optional()])
    end_date = DateField('结束日期', validators=[Optional()])
    department = StringField('部门', validators=[Optional(), Length(max=50)])
    material_type = SelectField('物料类型', choices=[
        ('', '全部'),
        ('raw', '原材料'),
        ('consumable', '易耗品'),
        ('finished', '成品')
    ], default='')
    submit = SubmitField('生成报表')
    
    def validate(self, extra_validators=None):
        """自定义验证"""
        if not super().validate(extra_validators):
            return False
        
        if self.date_range.data == 'custom':
            if not self.start_date.data:
                self.start_date.errors.append('自定义时间范围时开始日期不能为空')
                return False
            if not self.end_date.data:
                self.end_date.errors.append('自定义时间范围时结束日期不能为空')
                return False
            if self.start_date.data > self.end_date.data:
                self.end_date.errors.append('结束日期不能早于开始日期')
                return False
        
        return True