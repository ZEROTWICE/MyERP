from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db, login
from sqlalchemy.exc import SQLAlchemyError

@login.user_loader
def load_user(id):
    return User.query.get(int(id))

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True)
    password_hash = db.Column(db.String(128))
    role = db.Column(db.String(20), default='user')  # admin/hr/accountant

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class SerialNumber(db.Model):
    """全局流水号管理表"""
    __tablename__ = 'serial_numbers'
    
    id = db.Column(db.Integer, primary_key=True)
    current_number = db.Column(db.Integer, nullable=False, default=1)
    last_updated = db.Column(db.DateTime, nullable=False, default=datetime.now)

    @classmethod
    def get_next_number(cls):
        """获取下一个流水号"""
        while True:
            try:
                with db.session.begin_nested():
                    serial = cls.query.with_for_update().first()
                    if not serial:
                        serial = cls(current_number=1)
                        db.session.add(serial)
                    else:
                        serial.current_number += 1
                        serial.last_updated = datetime.now()
                    db.session.flush()
                    return f"{serial.current_number:08d}"
            except SQLAlchemyError:
                db.session.rollback()
                continue

class ProcessPrice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    global_sn = db.Column(db.String(8), unique=True, nullable=False)  # 全局流水号
    process_code = db.Column(db.String(50), nullable=False, index=True)  # 工序编号
    process_name = db.Column(db.String(100), nullable=False)
    component = db.Column(db.String(100))  # 部件
    drawing_no = db.Column(db.String(100))  # 图号
    model_no = db.Column(db.String(100))  # 型号
    price = db.Column(db.Float, nullable=False)
    version = db.Column(db.Integer, nullable=False)
    effective_date = db.Column(db.DateTime, default=datetime.utcnow)
    is_current = db.Column(db.Boolean, default=True)
    notes = db.Column(db.Text)  # 备注
    price_type = db.Column(db.String(20), nullable=False, default='normal')  # normal: 普通工价, subtotal: 小计
    has_output = db.Column(db.Boolean, default=True)  # 是否有产出
    output_type = db.Column(db.String(20))  # finished: 成品, raw: 原材料
    code_rule_id = db.Column(db.Integer, db.ForeignKey('code_rule.id', ondelete='SET NULL', name='fk_process_code_rule_id'))  # 编码规则ID
    needs_inspection = db.Column(db.Boolean, default=True)  # 是否需要检验
    
    __table_args__ = (
        db.UniqueConstraint('global_sn', name='uq_process_price_global_sn'),
    )

    @property
    def is_subtotal(self):
        return self.price_type == 'subtotal'

    def __init__(self, **kwargs):
        super(ProcessPrice, self).__init__(**kwargs)
        if not self.global_sn:
            self.global_sn = SerialNumber.get_next_number()

    # 关联关系
    code_rule = db.relationship('CodeRule', backref=db.backref('processes', lazy=True))

class ProcessPriceGroup(db.Model):
    """工序价格小计关系表"""
    __tablename__ = 'process_price_group'
    
    id = db.Column(db.Integer, primary_key=True)
    global_sn = db.Column(db.String(8), unique=True, nullable=False)  # 全局流水号
    subtotal_id = db.Column(db.Integer, db.ForeignKey('process_price.id', ondelete='CASCADE'), nullable=False)
    process_id = db.Column(db.Integer, db.ForeignKey('process_price.id', ondelete='CASCADE'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('global_sn', name='uq_process_price_group_global_sn'),
        db.UniqueConstraint('subtotal_id', 'process_id', name='uq_subtotal_process'),
    )
    
    # 关系
    subtotal = db.relationship('ProcessPrice', foreign_keys=[subtotal_id], 
                             backref=db.backref('included_processes', lazy='dynamic'))
    process = db.relationship('ProcessPrice', foreign_keys=[process_id],
                            backref=db.backref('belongs_to_subtotals', lazy='dynamic'))
    
    def __init__(self, **kwargs):
        super(ProcessPriceGroup, self).__init__(**kwargs)
        if not self.global_sn:
            self.global_sn = SerialNumber.get_next_number()

class Employee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    global_sn = db.Column(db.String(8), unique=True, nullable=False)  # 全局流水号
    employee_id = db.Column(db.String(50), unique=True, nullable=False, index=True)  # 工号
    name = db.Column(db.String(100), nullable=False)
    position = db.Column(db.String(50), nullable=False, default='普通员工')
    base_salary = db.Column(db.Float, default=0)
    coefficient = db.Column(db.Float, default=1.0)
    department = db.Column(db.String(50))
    hire_date = db.Column(db.Date, nullable=False)  # 入职时间
    termination_date = db.Column(db.Date, nullable=True)  # 离职时间
    is_active = db.Column(db.Boolean, default=True)  # 是否在职
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', name='fk_employee_user_id'))
    user = db.relationship('User', backref=db.backref('employee', uselist=False))
    
    __table_args__ = (
        db.UniqueConstraint('global_sn', name='uq_employee_global_sn'),
    )

    @property
    def total_salary(self):
        # 计件工资计算
        piecework = sum(record.quantity * record.process.price for record in self.production_records)
        # 奖金/罚款计算
        adjustments = sum(bp.amount if bp.type == 'bonus' else -bp.amount for bp in self.bonuses_penalties)
        # 总工资 = 基本工资 + 计件工资 * 系数 + 调整金额
        return self.base_salary + piecework * self.coefficient + adjustments

    @property
    def status(self):
        """获取员工状态"""
        if not self.is_active:
            return '离职'
        return '在职'

    def update_active_status(self):
        """根据入职时间和离职时间更新活跃状态"""
        today = datetime.now().date()
        if self.termination_date and self.termination_date <= today:
            self.is_active = False
        else:
            self.is_active = True

    def __init__(self, **kwargs):
        super(Employee, self).__init__(**kwargs)
        if not self.global_sn:
            self.global_sn = SerialNumber.get_next_number()

    # 关系
    bonuses_penalties = db.relationship('BonusPenalty', backref='employee', lazy='dynamic')
    production_records = db.relationship('ProductionRecord', backref=db.backref('employee'), lazy='dynamic')

class ProductionRecord(db.Model):
    """生产记录"""
    id = db.Column(db.Integer, primary_key=True)
    global_sn = db.Column(db.String(8), unique=True, nullable=False)  # 全局流水号
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    process_id = db.Column(db.Integer, db.ForeignKey('process_price.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)  # 生产数量
    date = db.Column(db.Date, nullable=False)  # 生产日期
    notes = db.Column(db.Text)  # 备注
    
    # 新增字段
    raw_material_id = db.Column(db.Integer, db.ForeignKey('raw_material.id'))  # 使用的原材料ID
    raw_material_quantity = db.Column(db.Float)  # 使用的原材料数量
    finished_product_id = db.Column(db.Integer, db.ForeignKey('finished_product.id'))  # 生成的成品ID
    
    # 关系
    process = db.relationship('ProcessPrice', backref='production_records')
    raw_material = db.relationship('RawMaterial', backref='production_records')
    finished_product = db.relationship('FinishedProduct', backref='production_records')
    
    def __repr__(self):
        return f'<ProductionRecord {self.id}: {self.employee.name} - {self.process.process_name}>'

    def __init__(self, **kwargs):
        super(ProductionRecord, self).__init__(**kwargs)
        if not self.global_sn:
            self.global_sn = SerialNumber.get_next_number()

class BonusPenalty(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    global_sn = db.Column(db.String(8), unique=True, nullable=False)  # 全局流水号
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'))
    amount = db.Column(db.Float)
    reason = db.Column(db.Text)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    type = db.Column(db.String(10))  # bonus/penalty
    process_id = db.Column(db.Integer, db.ForeignKey('process_price.id', name='fk_bp_process_id'))
    process = db.relationship('ProcessPrice', backref='bonus_penalties')
    
    __table_args__ = (
        db.UniqueConstraint('global_sn', name='uq_bonus_penalty_global_sn'),
    )

    def __init__(self, **kwargs):
        super(BonusPenalty, self).__init__(**kwargs)
        if not self.global_sn:
            self.global_sn = SerialNumber.get_next_number()

class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    action = db.Column(db.String(100))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    details = db.Column(db.Text)
    # 回滚相关字段
    can_rollback = db.Column(db.Boolean, default=False)  # 是否可以回滚
    rollback_type = db.Column(db.String(50))  # 回滚类型：add, edit, delete
    target_model = db.Column(db.String(50))  # 目标模型：Employee, ProcessPrice, ProductionRecord, BonusPenalty
    target_id = db.Column(db.Integer)  # 目标记录ID
    old_data = db.Column(db.JSON)  # 修改前的数据（用于回滚）
    new_data = db.Column(db.JSON)  # 修改后的数据
    rolled_back = db.Column(db.Boolean, default=False)  # 是否已经回滚
    rolled_back_by = db.Column(db.Integer, db.ForeignKey('user.id'))  # 由谁回滚
    rolled_back_at = db.Column(db.DateTime)  # 回滚时间

    # 明确指定relationship的外键关系
    user = db.relationship('User', 
                         foreign_keys=[user_id],
                         backref=db.backref('audit_logs', lazy='dynamic'))
    rollback_user = db.relationship('User',
                                  foreign_keys=[rolled_back_by],
                                  backref=db.backref('rolled_back_logs', lazy='dynamic'))

class TaskAssignment(db.Model):
    """生产任务分配"""
    id = db.Column(db.Integer, primary_key=True)
    global_sn = db.Column(db.String(8), unique=True, nullable=False)  # 全局流水号
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    process_id = db.Column(db.Integer, db.ForeignKey('process_price.id'), nullable=False)
    assigned_date = db.Column(db.DateTime, default=datetime.utcnow)  # 分配时间
    target_date = db.Column(db.Date, nullable=False)  # 目标完成日期
    quantity = db.Column(db.Integer, nullable=False)  # 分配数量
    completed_quantity = db.Column(db.Integer, default=0)  # 已完成数量
    status = db.Column(db.String(20), default='pending')  # pending, in_progress, completed, cancelled
    notes = db.Column(db.Text)  # 备注
    
    __table_args__ = (
        db.UniqueConstraint('global_sn', name='uq_task_assignment_global_sn'),
    )

    # 关系
    employee = db.relationship('Employee', backref='task_assignments')
    process = db.relationship('ProcessPrice', backref='task_assignments')
    
    def __repr__(self):
        return f'<TaskAssignment {self.id}: {self.employee.name} - {self.process.process_name}>'
    
    @property
    def completion_rate(self):
        """完成率"""
        if self.quantity == 0:
            return 0
        return (self.completed_quantity / self.quantity) * 100
    
    @property
    def is_overdue(self):
        """是否逾期"""
        return self.target_date < datetime.now().date() and self.status != 'completed'

    def __init__(self, **kwargs):
        super(TaskAssignment, self).__init__(**kwargs)
        if not self.global_sn:
            self.global_sn = SerialNumber.get_next_number()

class EmployeeSalaryHistory(db.Model):
    """员工工资变更历史"""
    __tablename__ = 'employee_salary_history'
    
    id = db.Column(db.Integer, primary_key=True)
    global_sn = db.Column(db.String(8), unique=True, nullable=False)  # 全局流水号
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id', ondelete='CASCADE', name='fk_salary_history_employee_id'), nullable=False)
    old_salary = db.Column(db.Float, nullable=False)
    new_salary = db.Column(db.Float, nullable=False)
    effective_date = db.Column(db.Date, nullable=False)
    reason = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL', name='fk_salary_history_creator_id'), nullable=True)
    
    __table_args__ = (
        db.UniqueConstraint('global_sn', name='uq_salary_history_global_sn'),
    )
    
    employee = db.relationship('Employee', backref=db.backref('salary_history', lazy=True))
    creator = db.relationship('User', backref=db.backref('salary_history_created', lazy=True))
    
    def __init__(self, **kwargs):
        if 'creator_id' in kwargs:
            kwargs['created_by'] = kwargs.pop('creator_id')
        super(EmployeeSalaryHistory, self).__init__(**kwargs)
        
        # 如果没有设置流水号，自动生成一个
        if not self.global_sn:
            self.global_sn = SerialNumber.get_next_number()

class EmployeeCoefficientHistory(db.Model):
    """员工工资系数变更历史"""
    __tablename__ = 'employee_coefficient_history'
    
    id = db.Column(db.Integer, primary_key=True)
    global_sn = db.Column(db.String(8), unique=True, nullable=False)  # 全局流水号
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id', ondelete='CASCADE', name='fk_coefficient_history_employee_id'), nullable=False)
    old_coefficient = db.Column(db.Float, nullable=False)
    new_coefficient = db.Column(db.Float, nullable=False)
    effective_date = db.Column(db.Date, nullable=False)
    reason = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL', name='fk_coefficient_history_creator_id'), nullable=True)
    
    __table_args__ = (
        db.UniqueConstraint('global_sn', name='uq_coefficient_history_global_sn'),
    )
    
    employee = db.relationship('Employee', backref=db.backref('coefficient_history', lazy=True))
    creator = db.relationship('User', backref=db.backref('coefficient_history_created', lazy=True))
    
    def __init__(self, **kwargs):
        if 'creator_id' in kwargs:
            kwargs['created_by'] = kwargs.pop('creator_id')
        super(EmployeeCoefficientHistory, self).__init__(**kwargs)
        
        # 如果没有设置流水号，自动生成一个
        if not self.global_sn:
            self.global_sn = SerialNumber.get_next_number()

# 为与路由函数保持一致，创建别名
SalaryChange = EmployeeSalaryHistory
CoefficientChange = EmployeeCoefficientHistory

class FinishedProduct(db.Model):
    """成品库存管理"""
    id = db.Column(db.Integer, primary_key=True)
    global_sn = db.Column(db.String(8), unique=True, nullable=False)  # 全局流水号
    serial_number = db.Column(db.String(8), unique=True, nullable=False)
    product_number = db.Column(db.String(50), nullable=False, index=True)  # 产品编号
    production_date = db.Column(db.Date, nullable=False)  # 生产日期
    drawing_number = db.Column(db.String(100), nullable=False)  # 图号
    model = db.Column(db.String(100), nullable=False)  # 型号
    inspector = db.Column(db.String(50), nullable=False)  # 检验员
    quantity = db.Column(db.Integer, nullable=False, default=1)  # 数量
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='in_stock')  # in_stock: 在库, shipped: 已发货, scrapped: 报废, used: 已使用
    notes = db.Column(db.Text)  # 备注
    
    __table_args__ = (
        db.UniqueConstraint('serial_number', name='uq_finished_product_serial_number'),
        db.UniqueConstraint('global_sn', name='uq_finished_product_global_sn'),
    )
    
    def __init__(self, **kwargs):
        super(FinishedProduct, self).__init__(**kwargs)
        if not self.serial_number:
            self.serial_number = SerialNumber.get_next_number()
        if not self.global_sn:
            self.global_sn = SerialNumber.get_next_number()

class RawMaterial(db.Model):
    """原材料管理"""
    id = db.Column(db.Integer, primary_key=True)
    global_sn = db.Column(db.String(8), unique=True, nullable=False)  # 全局流水号
    supplier = db.Column(db.String(100), nullable=False)  # 供应商
    material_name = db.Column(db.String(100), nullable=False)  # 品名
    melt_number = db.Column(db.String(100), nullable=False)  # 原料冶炼炉号
    supplier_number = db.Column(db.String(100), nullable=False)  # 供应商编号
    has_sample = db.Column(db.Boolean, default=False)  # 是否带样品
    storage_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)  # 入库时间
    internal_number = db.Column(db.String(100), nullable=False)  # 内部编号
    quantity = db.Column(db.Float, nullable=False)  # 数量
    notes = db.Column(db.Text)  # 备注
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('global_sn', name='uq_raw_material_global_sn'),
        db.UniqueConstraint('internal_number', name='uq_raw_material_internal_number'),
    )
    
    def __init__(self, **kwargs):
        super(RawMaterial, self).__init__(**kwargs)
        if not self.global_sn:
            self.global_sn = SerialNumber.get_next_number()
        if not self.internal_number or self.internal_number == '':
            self.internal_number = SerialNumber.get_next_number()

class CodeRule(db.Model):
    """编码规则管理"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)  # 规则名称
    code_type = db.Column(db.String(50), nullable=False)  # 编码类型：product(产品编码), material(物料编码), etc.
    prefix = db.Column(db.String(20))  # 前缀
    suffix = db.Column(db.String(20))  # 后缀
    sequence_length = db.Column(db.Integer, nullable=False, default=4)  # 序号长度
    current_sequence = db.Column(db.Integer, default=1)  # 当前序号
    reset_frequency = db.Column(db.String(20), default='never')  # 重置频率：never, daily, monthly, yearly
    last_reset_date = db.Column(db.DateTime)  # 上次重置时间
    format_pattern = db.Column(db.String(200))  # 格式模式，例如：{prefix}{year}{month}{sequence}
    is_active = db.Column(db.Boolean, default=True)  # 是否启用
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    notes = db.Column(db.Text)  # 备注

    def generate_code(self):
        """生成编码"""
        # 检查是否需要重置序号
        self._check_reset()
        
        # 获取当前日期时间
        now = datetime.now()
        
        # 准备替换字典
        replace_dict = {
            'prefix': self.prefix or '',
            'suffix': self.suffix or '',
            'year': str(now.year),
            'year2': str(now.year)[-2:],
            'month': f"{now.month:02d}",
            'day': f"{now.day:02d}",
            'sequence': str(self.current_sequence).zfill(self.sequence_length)
        }
        
        # 使用格式模式生成编码
        code = self.format_pattern
        for key, value in replace_dict.items():
            code = code.replace('{' + key + '}', value)
        
        # 更新序号
        self.current_sequence += 1
        db.session.commit()
        
        return code

    def _check_reset(self):
        """检查是否需要重置序号"""
        if not self.last_reset_date:
            self.last_reset_date = datetime.now()
            return

        now = datetime.now()
        last_reset = self.last_reset_date

        if self.reset_frequency == 'daily':
            if now.date() > last_reset.date():
                self._reset_sequence()
        elif self.reset_frequency == 'monthly':
            if now.year > last_reset.year or now.month > last_reset.month:
                self._reset_sequence()
        elif self.reset_frequency == 'yearly':
            if now.year > last_reset.year:
                self._reset_sequence()

    def _reset_sequence(self):
        """重置序号"""
        self.current_sequence = 1
        self.last_reset_date = datetime.now()

class CodeGenerationLog(db.Model):
    """编码生成日志"""
    id = db.Column(db.Integer, primary_key=True)
    rule_id = db.Column(db.Integer, db.ForeignKey('code_rule.id'), nullable=False)
    generated_code = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    target_type = db.Column(db.String(50))  # 使用目标类型
    target_id = db.Column(db.Integer)  # 使用目标ID

    rule = db.relationship('CodeRule', backref='generation_logs')
    creator = db.relationship('User', backref='code_generation_logs')