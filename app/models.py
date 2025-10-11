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
    def get_next_number(cls, prefix=None):
        """获取下一个流水号
        Args:
            prefix: 可选的前缀，如果提供则会添加到流水号前面
        Returns:
            str: 格式化的流水号
        """
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
                    number = f"{serial.current_number:08d}"
                    return f"{prefix}{number}" if prefix else number
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
    materials = db.relationship('ProductionRecordMaterial', back_populates='production_record', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<ProductionRecord {self.id}: {self.employee.name} - {self.process.process_name}>'

    def __init__(self, **kwargs):
        super(ProductionRecord, self).__init__(**kwargs)
        if not self.global_sn:
            self.global_sn = SerialNumber.get_next_number()

class ProductionRecordMaterial(db.Model):
    """生产记录与原材料的关联表"""
    __tablename__ = 'production_record_materials'
    
    id = db.Column(db.Integer, primary_key=True)
    production_record_id = db.Column(db.Integer, db.ForeignKey('production_record.id', ondelete='CASCADE'), nullable=False)
    raw_material_id = db.Column(db.Integer, db.ForeignKey('raw_material.id', ondelete='SET NULL'))
    quantity = db.Column(db.Float, nullable=False)  # this field stores the quantity of raw material used
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # 关系
    production_record = db.relationship('ProductionRecord', back_populates='materials')
    raw_material = db.relationship('RawMaterial', backref='production_materials')
    
    def __repr__(self):
        return f'<ProductionRecordMaterial: Record {self.production_record_id}, Material {self.raw_material_id}, Quantity {self.quantity}>'

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
    
    # 新增字段：关联生产批次
    production_batch_id = db.Column(db.Integer, db.ForeignKey('production_batches.id', ondelete='SET NULL'), nullable=True)
    batch_item_id = db.Column(db.Integer, db.ForeignKey('production_batch_items.id', ondelete='SET NULL'), nullable=True)
    task_type = db.Column(db.String(20), default='manual')  # manual: 手动创建, auto: 自动创建
    
    # 从生产订单继承的规格型号信息
    spec_extended = db.Column(db.String(100))  # 加长（具体值）
    spec_gasket = db.Column(db.String(100))  # 垫板（具体值）
    spec_joint = db.Column(db.String(100))  # 接头（具体值）
    spec_drilling = db.Column(db.String(100))  # 钻孔（具体值）
    spec_other = db.Column(db.String(100))  # 其他（具体值）
    spec_other_desc = db.Column(db.String(200))  # 其他规格描述
    direction = db.Column(db.String(50))  # 开向
    
    # 新增规格型号字段（与销售订单行保持一致）
    spec_splice_hole = db.Column(db.String(100))  # 接续线孔
    spec_gasket_hole = db.Column(db.String(100))  # 垫板孔型
    anti_corrosion = db.Column(db.String(100))  # 辙叉防腐
    rubber_gasket_material = db.Column(db.String(100))  # 橡胶垫板材质
    turnout_rail = db.Column(db.String(100))  # 道岔配轨
    using_unit = db.Column(db.String(100))  # 使用单位
    
    __table_args__ = (
        db.UniqueConstraint('global_sn', name='uq_task_assignment_global_sn'),
    )

    # 关系
    employee = db.relationship('Employee', backref='task_assignments')
    process = db.relationship('ProcessPrice', backref='task_assignments')
    production_batch = db.relationship('ProductionBatch', backref=db.backref('tasks', lazy='dynamic'))
    batch_item = db.relationship('ProductionBatchItem', backref=db.backref('tasks', lazy='dynamic'))
    
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
    
    @property
    def specifications(self):
        """获取规格型号列表"""
        specs = []
        if self.spec_extended:
            specs.append(f'加长型式({self.spec_extended})')
        if self.spec_gasket:
            specs.append(f'垫板({self.spec_gasket})')
        if self.spec_joint:
            specs.append(f'接头型式({self.spec_joint})')
        if self.spec_drilling:
            specs.append(f'跳线孔({self.spec_drilling})')
        if self.spec_splice_hole:
            specs.append(f'接续线孔({self.spec_splice_hole})')
        if self.spec_gasket_hole:
            specs.append(f'垫板孔型({self.spec_gasket_hole})')
        if self.anti_corrosion:
            specs.append(f'辙叉防腐({self.anti_corrosion})')
        if self.rubber_gasket_material:
            specs.append(f'橡胶垫板材质({self.rubber_gasket_material})')
        if self.turnout_rail:
            specs.append(f'道岔配轨({self.turnout_rail})')
        if self.using_unit:
            specs.append(f'使用单位({self.using_unit})')
        if self.spec_other:
            specs.append(f'其他({self.spec_other})')
        return specs
    
    @property
    def specifications_text(self):
        """获取规格型号文本"""
        specs = self.specifications
        return ', '.join(specs) if specs else '无'

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
    is_archived = db.Column(db.Boolean, default=False)  # 是否已存档
    
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

class RawMaterialCategory(db.Model):
    """原材料品类管理"""
    __tablename__ = 'raw_material_categories'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)  # 品类名称
    code = db.Column(db.String(20), nullable=False, unique=True)  # 品类编码
    description = db.Column(db.Text)  # 品类描述
    is_active = db.Column(db.Boolean, default=True)  # 是否启用
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))  # 创建人
    
    # 关系
    raw_materials = db.relationship('RawMaterial', backref='category', lazy='dynamic')
    creator = db.relationship('User', backref='created_categories')
    
    def __repr__(self):
        return f'<RawMaterialCategory {self.name}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'code': self.code,
            'description': self.description,
            'is_active': self.is_active,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'material_count': self.raw_materials.count()
        }

class RawMaterial(db.Model):
    """原材料管理"""
    id = db.Column(db.Integer, primary_key=True)
    global_sn = db.Column(db.String(8), unique=True, nullable=False)  # 全局流水号
    supplier = db.Column(db.String(100), nullable=False)  # 供应商
    category_id = db.Column(db.Integer, db.ForeignKey('raw_material_categories.id'), nullable=False)  # 品类ID
    melt_number = db.Column(db.String(100), nullable=False)  # 原料冶炼炉号
    supplier_number = db.Column(db.String(100), nullable=False)  # 供应商编号
    has_sample = db.Column(db.Boolean, default=False)  # 是否带样品
    storage_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)  # 入库时间
    internal_number = db.Column(db.String(100), nullable=False)  # 内部编号
    quantity = db.Column(db.Float, nullable=False)  # 数量
    notes = db.Column(db.Text)  # 备注
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), nullable=False, default='in_stock', index=True)  # 状态: in_stock: 在库, used: 已使用, scrapped: 报废
    is_archived = db.Column(db.Boolean, default=False)  # 是否已存档
    
    __table_args__ = (
        db.UniqueConstraint('global_sn', name='uq_raw_material_global_sn'),
        db.UniqueConstraint('internal_number', name='uq_raw_material_internal_number'),
    )
    
    @property
    def material_name(self):
        """获取品名（通过品类）"""
        if self.category:
            return self.category.name
        return "未设置品类"
    
    @property
    def category_code(self):
        """获取品类编码"""
        if self.category:
            return self.category.code
        return ""
    
    def __init__(self, **kwargs):
        super(RawMaterial, self).__init__(**kwargs)
        if not self.global_sn:
            self.global_sn = SerialNumber.get_next_number()
        if not self.internal_number or self.internal_number == '':
            self.internal_number = SerialNumber.get_next_number()

class ConsumableCategory(db.Model):
    """易耗品品类管理"""
    __tablename__ = 'consumable_categories'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)  # 品类名称
    code = db.Column(db.String(20), nullable=False, unique=True)  # 品类编码
    description = db.Column(db.Text)  # 品类描述
    is_active = db.Column(db.Boolean, default=True)  # 是否启用
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))  # 创建人
    
    # 关系
    consumables = db.relationship('Consumable', backref='category', lazy='dynamic')
    creator = db.relationship('User', backref='created_consumable_categories')
    
    def __repr__(self):
        return f'<ConsumableCategory {self.name}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'code': self.code,
            'description': self.description,
            'is_active': self.is_active,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'consumable_count': self.consumables.count()
        }

class Consumable(db.Model):
    """易耗品管理"""
    __tablename__ = 'consumables'
    
    id = db.Column(db.Integer, primary_key=True)
    global_sn = db.Column(db.String(8), unique=True, nullable=False)  # 全局流水号
    supplier = db.Column(db.String(100), nullable=False)  # 供应商
    category_id = db.Column(db.Integer, db.ForeignKey('consumable_categories.id'), nullable=False)  # 品类ID
    specification = db.Column(db.String(200))  # 规格型号
    supplier_number = db.Column(db.String(100), nullable=False)  # 供应商编号
    storage_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)  # 入库时间
    internal_number = db.Column(db.String(100), nullable=False)  # 内部编号
    quantity = db.Column(db.Float, nullable=False)  # 数量
    unit = db.Column(db.String(20), default='个')  # 单位
    unit_price = db.Column(db.Float, default=0)  # 单价
    total_price = db.Column(db.Float, default=0)  # 总价
    expiry_date = db.Column(db.Date)  # 过期日期
    storage_location = db.Column(db.String(100))  # 存放位置
    min_stock_level = db.Column(db.Float, default=0)  # 最低库存预警
    notes = db.Column(db.Text)  # 备注
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), nullable=False, default='in_stock', index=True)  # 状态: in_stock: 在库, used: 已使用, scrapped: 报废, expired: 过期
    is_archived = db.Column(db.Boolean, default=False)  # 是否已存档
    
    __table_args__ = (
        db.UniqueConstraint('global_sn', name='uq_consumable_global_sn'),
        db.UniqueConstraint('internal_number', name='uq_consumable_internal_number'),
    )
    
    @property
    def consumable_name(self):
        """获取易耗品名称（通过品类）"""
        if self.category:
            return self.category.name
        return "未设置品类"
    
    @property
    def category_code(self):
        """获取品类编码"""
        if self.category:
            return self.category.code
        return ""
    
    @property
    def is_low_stock(self):
        """是否低库存"""
        return self.quantity <= self.min_stock_level if self.min_stock_level > 0 else False
    
    @property
    def is_expired(self):
        """是否已过期"""
        if self.expiry_date:
            return datetime.now().date() > self.expiry_date
        return False
    
    @property
    def days_to_expiry(self):
        """距离过期天数"""
        if self.expiry_date:
            delta = self.expiry_date - datetime.now().date()
            return delta.days
        return None
    
    def __init__(self, **kwargs):
        super(Consumable, self).__init__(**kwargs)
        if not self.global_sn:
            self.global_sn = SerialNumber.get_next_number()
        if not self.internal_number or self.internal_number == '':
            self.internal_number = SerialNumber.get_next_number()
        # 自动计算总价
        if self.unit_price and self.quantity:
            self.total_price = self.unit_price * self.quantity

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

class InspectionTemplate(db.Model):
    """质检模板"""
    __tablename__ = 'inspection_templates'

    id = db.Column(db.Integer, primary_key=True)
    template_code = db.Column(db.String(50), unique=True, nullable=False, comment='模板编码', index=True)
    name = db.Column(db.String(100), nullable=False, comment='模板名称')
    type = db.Column(db.String(20), nullable=False, comment='模板类型(product/production_record/material)', index=True)
    description = db.Column(db.Text, comment='模板描述')
    is_active = db.Column(db.Boolean, default=True, comment='是否启用', index=True)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now, index=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    # 关联关系
    creator = db.relationship('User', backref=db.backref('created_templates', lazy='dynamic'))
    base_items = db.relationship('InspectionBaseItem', backref='template', lazy='dynamic')
    items = db.relationship('InspectionItem', backref='template', lazy='dynamic')

    def __repr__(self):
        return f'<InspectionTemplate {self.template_code}>'

class InspectionBaseItem(db.Model):
    """质检基本信息项目"""
    __tablename__ = 'inspection_base_items'

    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey('inspection_templates.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False, comment='信息项目名称')
    description = db.Column(db.Text, comment='项目描述')
    notes = db.Column(db.Text, comment='项目备注')
    input_type = db.Column(db.String(20), nullable=False, comment='输入类型(text/number/date/select)')
    default_value = db.Column(db.String(200), comment='默认值')
    options = db.Column(db.JSON, comment='选择项(JSON格式)')
    is_required = db.Column(db.Boolean, default=True, comment='是否必填')
    validation_rules = db.Column(db.JSON, comment='验证规则(JSON格式)')
    order_num = db.Column(db.Integer, default=0, comment='排序号')

    # 关联关系
    linked_items = db.relationship('InspectionItem', backref='linked_base_item', lazy='dynamic')
    base_records = db.relationship('InspectionBaseItemRecord', backref='base_item', lazy='dynamic')

    def __repr__(self):
        return f'<InspectionBaseItem {self.name}>'

class InspectionItem(db.Model):
    """质检项目"""
    __tablename__ = 'inspection_items'

    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey('inspection_templates.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False, comment='检验项目名称')
    description = db.Column(db.Text, comment='项目描述')
    notes = db.Column(db.Text, comment='项目备注')
    inspection_method = db.Column(db.Text, comment='检验方法')
    standard = db.Column(db.Text, comment='检验标准')
    standard_value = db.Column(db.Float, comment='标准值')
    linked_base_item_id = db.Column(db.Integer, db.ForeignKey('inspection_base_items.id'), comment='关联的基本信息项目ID')
    use_linked_value = db.Column(db.Boolean, default=False, comment='是否使用关联值作为标准值')
    value_extraction_rule = db.Column(db.JSON, comment='值提取规则(JSON格式)')
    deviation_type = db.Column(db.String(20), comment='偏差类型(value/percentage)')
    upper_deviation_value = db.Column(db.Float, comment='上偏差值')
    lower_deviation_value = db.Column(db.Float, comment='下偏差值')
    upper_deviation_percentage = db.Column(db.Float, comment='上偏差百分比')
    lower_deviation_percentage = db.Column(db.Float, comment='下偏差百分比')
    unit = db.Column(db.String(20), comment='单位')
    order_num = db.Column(db.Integer, default=0, comment='排序号')

    # 关联关系
    item_records = db.relationship('InspectionItemRecord', backref='item', lazy='dynamic')

    def __repr__(self):
        return f'<InspectionItem {self.name}>'

class InspectionTask(db.Model):
    """质检任务"""
    __tablename__ = 'inspection_tasks'

    id = db.Column(db.Integer, primary_key=True)
    global_sn = db.Column(db.String(50), unique=True, nullable=False, comment='全局流水号', index=True)
    template_id = db.Column(db.Integer, db.ForeignKey('inspection_templates.id'), nullable=True, index=True)
    inspector_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    target_type = db.Column(db.String(20), nullable=False, comment='检验对象类型(product/production_record/material)', index=True)
    target_id = db.Column(db.Integer, nullable=False, comment='检验对象ID', index=True)
    status = db.Column(db.String(20), nullable=False, default='pending', comment='任务状态(pending/in_progress/completed/cancelled)', index=True)
    priority = db.Column(db.Integer, default=0, comment='优先级', index=True)
    deadline = db.Column(db.DateTime, comment='截止时间', index=True)
    notes = db.Column(db.Text, comment='备注说明')
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now, index=True)
    completed_at = db.Column(db.DateTime, comment='完成时间', index=True)

    # 关联关系
    template = db.relationship('InspectionTemplate', backref=db.backref('tasks', lazy='dynamic'))
    inspector = db.relationship('User', foreign_keys=[inspector_id], backref=db.backref('inspection_tasks', lazy='dynamic'))
    creator = db.relationship('User', foreign_keys=[created_by], backref=db.backref('created_tasks', lazy='dynamic'))
    record = db.relationship('InspectionRecord', backref='task', uselist=False)

    @property
    def target_record(self):
        """获取生产记录对象"""
        if self.target_type == 'production_record':
            return ProductionRecord.query.get(self.target_id)
        return None
    
    @property
    def target_product(self):
        """获取成品对象"""
        if self.target_type == 'product':
            return FinishedProduct.query.get(self.target_id)
        return None
    
    @property
    def target_material(self):
        """获取原材料对象"""
        if self.target_type == 'material':
            return RawMaterial.query.get(self.target_id)
        return None

    def __repr__(self):
        return f'<InspectionTask {self.global_sn}>'

class InspectionRecord(db.Model):
    """质检记录"""
    __tablename__ = 'inspection_records'

    id = db.Column(db.Integer, primary_key=True)
    global_sn = db.Column(db.String(50), unique=True, nullable=False, comment='全局流水号', index=True)
    task_id = db.Column(db.Integer, db.ForeignKey('inspection_tasks.id'), nullable=False, unique=True)
    template_id = db.Column(db.Integer, db.ForeignKey('inspection_templates.id'), nullable=True, index=True)
    inspector_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    inspection_date = db.Column(db.Date, nullable=False, comment='检验日期', index=True)
    result = db.Column(db.String(20), nullable=False, comment='总体检验结果(pass/fail)', index=True)
    notes = db.Column(db.Text, comment='备注说明')
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now, index=True)

    # 关联关系
    template = db.relationship('InspectionTemplate', backref=db.backref('records', lazy='dynamic'))
    inspector = db.relationship('User', backref=db.backref('inspection_records', lazy='dynamic'))
    base_item_records = db.relationship('InspectionBaseItemRecord', backref='record', lazy='dynamic')
    item_records = db.relationship('InspectionItemRecord', backref='record', lazy='dynamic')
    nonconformity_records = db.relationship('NonconformityRecord', backref='record', lazy='dynamic')

    def __repr__(self):
        return f'<InspectionRecord {self.global_sn}>'

class InspectionBaseItemRecord(db.Model):
    """质检基本信息记录"""
    __tablename__ = 'inspection_base_item_records'

    id = db.Column(db.Integer, primary_key=True)
    record_id = db.Column(db.Integer, db.ForeignKey('inspection_records.id'), nullable=False)
    base_item_id = db.Column(db.Integer, db.ForeignKey('inspection_base_items.id'), nullable=False)
    value = db.Column(db.String(500), nullable=False, comment='记录的值')
    notes = db.Column(db.Text, comment='备注说明')

    def __repr__(self):
        return f'<InspectionBaseItemRecord {self.id}>'

class InspectionItemRecord(db.Model):
    """质检项目记录"""
    __tablename__ = 'inspection_item_records'

    id = db.Column(db.Integer, primary_key=True)
    record_id = db.Column(db.Integer, db.ForeignKey('inspection_records.id'), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey('inspection_items.id'), nullable=False)
    measured_value = db.Column(db.Float, nullable=False, comment='实测值')
    is_qualified = db.Column(db.Boolean, nullable=False, comment='是否合格')
    notes = db.Column(db.Text, comment='备注说明')
    evidence = db.Column(db.String(500), comment='证据(如照片路径)')

    def __repr__(self):
        return f'<InspectionItemRecord {self.id}>'

class NonconformityRecord(db.Model):
    """不合格品处理记录"""
    __tablename__ = 'nonconformity_records'

    id = db.Column(db.Integer, primary_key=True)
    record_id = db.Column(db.Integer, db.ForeignKey('inspection_records.id'), nullable=False)
    type = db.Column(db.String(20), nullable=False, comment='处理类型(rework/scrap/accept)')
    handler_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    handling_date = db.Column(db.Date, nullable=False, comment='处理日期')
    handling_result = db.Column(db.Text, nullable=False, comment='处理结果')
    notes = db.Column(db.Text, comment='处理说明')

    # 关联关系
    handler = db.relationship('User', backref=db.backref('handled_nonconformities', lazy='dynamic'))

    def __repr__(self):
        return f'<NonconformityRecord {self.id}: {self.type}>'

class Product(db.Model):
    """产品管理"""
    __tablename__ = 'products'
    
    id = db.Column(db.Integer, primary_key=True)
    global_sn = db.Column(db.String(8), unique=True, nullable=False)  # 全局流水号
    product_code = db.Column(db.String(50), unique=True, nullable=False, index=True)  # 产品编码
    product_name = db.Column(db.String(100), nullable=False)  # 产品名称
    drawing_number = db.Column(db.String(100))  # 图号
    model = db.Column(db.String(100))  # 型号
    specification = db.Column(db.Text)  # 规格说明
    unit = db.Column(db.String(20), default='件')  # 单位
    category = db.Column(db.String(50))  # 产品类别
    version = db.Column(db.String(20), default='1.0')  # 版本号
    status = db.Column(db.String(20), default='active')  # 状态: active, inactive, obsolete
    notes = db.Column(db.Text)  # 备注
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 新增编码规则关联
    code_rule_id = db.Column(db.Integer, db.ForeignKey('code_rule.id', ondelete='SET NULL'), nullable=True)  # 产品编码规则
    
    __table_args__ = (
        db.UniqueConstraint('global_sn', name='uq_product_global_sn'),
        db.UniqueConstraint('product_code', name='uq_product_code'),
    )
    
    # 关系
    creator = db.relationship('User', backref=db.backref('created_products', lazy='dynamic'))
    bom_items = db.relationship('ProductBOM', backref='product', lazy='dynamic', cascade='all, delete-orphan')
    process_items = db.relationship('ProductProcess', backref='product', lazy='dynamic', cascade='all, delete-orphan')
    code_rule = db.relationship('CodeRule', backref=db.backref('products', lazy='dynamic'))
    production_orders = db.relationship('ProductionOrder', backref='product', lazy='dynamic')
    
    def __init__(self, **kwargs):
        super(Product, self).__init__(**kwargs)
        if not self.global_sn:
            self.global_sn = SerialNumber.get_next_number()
    
    @property
    def total_material_cost(self):
        """计算总原材料成本（包括原材料、成品和产品）"""
        return sum(bom.total_cost for bom in self.bom_items)
    
    @property
    def total_process_cost(self):
        """计算总工序成本"""
        return sum(process.total_cost for process in self.process_items)
    
    @property
    def total_cost(self):
        """计算总成本"""
        return self.total_material_cost + self.total_process_cost
    
    def generate_product_code(self, batch_size=1):
        """根据关联的编码规则生成产品编码"""
        if not self.code_rule or not self.code_rule.is_active:
            return None
        
        codes = []
        for i in range(batch_size):
            code = self.code_rule.generate_code()
            # 记录编码生成日志
            log = CodeGenerationLog(
                rule_id=self.code_rule.id,
                generated_code=code,
                target_type='product',
                target_id=self.id
            )
            db.session.add(log)
            codes.append(code)
        
        return codes if batch_size > 1 else codes[0]
    
    def __repr__(self):
        return f'<Product {self.product_code}: {self.product_name}>'

class ProductBOM(db.Model):
    """产品物料清单"""
    __tablename__ = 'product_bom'
    
    id = db.Column(db.Integer, primary_key=True)
    global_sn = db.Column(db.String(8), unique=True, nullable=False)  # 全局流水号
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'), nullable=False)
    material_type = db.Column(db.String(20), nullable=False)  # raw: 原材料, finished: 成品
    material_id = db.Column(db.Integer, nullable=False)  # 原材料或成品ID
    quantity = db.Column(db.Float, nullable=False)  # 用量
    unit = db.Column(db.String(20), default='件')  # 单位
    unit_cost = db.Column(db.Float, default=0)  # 单价
    waste_rate = db.Column(db.Float, default=0)  # 损耗率(%)
    notes = db.Column(db.Text)  # 备注
    sequence = db.Column(db.Integer, default=0)  # 排序序号
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('global_sn', name='uq_product_bom_global_sn'),
        db.Index('ix_product_bom_material', 'material_type', 'material_id'),
    )
    
    def __init__(self, **kwargs):
        super(ProductBOM, self).__init__(**kwargs)
        if not self.global_sn:
            self.global_sn = SerialNumber.get_next_number()
    
    @property
    def actual_quantity(self):
        """实际用量（含损耗）"""
        return self.quantity * (1 + self.waste_rate / 100)
    
    @property
    def total_cost(self):
        """总成本"""
        return self.actual_quantity * self.unit_cost
    
    @property
    def material_info(self):
        """获取物料信息"""
        if self.material_type == 'raw':
            return RawMaterial.query.get(self.material_id)
        elif self.material_type == 'finished':
            return FinishedProduct.query.get(self.material_id)
        elif self.material_type == 'product':
            return Product.query.get(self.material_id)
        return None
    
    @property
    def material_name(self):
        """获取物料名称"""
        material = self.material_info
        if material:
            if self.material_type == 'raw':
                return material.material_name
            elif self.material_type == 'finished':
                return material.product_number
            elif self.material_type == 'product':
                return f"{material.product_name} ({material.product_code})"
        return '未知物料'
    
    def __repr__(self):
        return f'<ProductBOM {self.id}: {self.product.product_code} -> {self.material_name}>'

class ProductProcess(db.Model):
    """产品工序"""
    __tablename__ = 'product_processes'
    
    id = db.Column(db.Integer, primary_key=True)
    global_sn = db.Column(db.String(8), unique=True, nullable=False)  # 全局流水号
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'), nullable=False)
    process_id = db.Column(db.Integer, db.ForeignKey('process_price.id'), nullable=False)
    sequence = db.Column(db.Integer, nullable=False)  # 工序顺序
    quantity = db.Column(db.Integer, default=1)  # 加工数量
    unit_price = db.Column(db.Float)  # 单价（可覆盖工序价格表中的价格）
    setup_time = db.Column(db.Float, default=0)  # 准备时间（分钟）
    process_time = db.Column(db.Float, default=0)  # 加工时间（分钟）
    notes = db.Column(db.Text)  # 备注
    is_required = db.Column(db.Boolean, default=True)  # 是否必需工序
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('global_sn', name='uq_product_process_global_sn'),
        db.UniqueConstraint('product_id', 'sequence', name='uq_product_process_sequence'),
    )
    
    # 关系
    process = db.relationship('ProcessPrice', backref=db.backref('product_processes', lazy='dynamic'))
    
    def __init__(self, **kwargs):
        super(ProductProcess, self).__init__(**kwargs)
        if not self.global_sn:
            self.global_sn = SerialNumber.get_next_number()
    
    @property
    def effective_price(self):
        """有效价格"""
        return self.unit_price if self.unit_price is not None else self.process.price
    
    @property
    def total_cost(self):
        """总成本"""
        return self.quantity * self.effective_price
    
    @property
    def total_time(self):
        """总时间（分钟）"""
        return self.setup_time + self.process_time
    
    def __repr__(self):
        return f'<ProductProcess {self.id}: {self.product.product_code} -> {self.process.process_name}>'

class ProductionOrder(db.Model):
    """生产订单"""
    __tablename__ = 'production_orders'
    
    id = db.Column(db.Integer, primary_key=True)
    global_sn = db.Column(db.String(8), unique=True, nullable=False)  # 全局流水号
    order_number = db.Column(db.String(50), unique=True, nullable=False, index=True)  # 订单编号
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'), nullable=False)
    planned_quantity = db.Column(db.Integer, nullable=False)  # 计划生产数量
    completed_quantity = db.Column(db.Integer, default=0)  # 已完成数量
    status = db.Column(db.String(20), default='pending')  # pending, in_progress, completed, cancelled
    priority = db.Column(db.Integer, default=0)  # 优先级
    planned_start_date = db.Column(db.Date, nullable=False)  # 计划开始日期
    planned_end_date = db.Column(db.Date, nullable=False)  # 计划完成日期
    actual_start_date = db.Column(db.Date)  # 实际开始日期
    actual_end_date = db.Column(db.Date)  # 实际完成日期
    notes = db.Column(db.Text)  # 备注
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    # 销售订单关联字段
    sales_order_id = db.Column(db.Integer, db.ForeignKey('sales_orders.id', ondelete='SET NULL'), nullable=True)  # 关联的销售订单ID
    sales_order_item_id = db.Column(db.Integer, db.ForeignKey('sales_order_items.id', ondelete='SET NULL'), nullable=True)  # 关联的销售订单行ID
    source_type = db.Column(db.String(20), default='manual')  # manual: 手动创建, sales_order: 从销售订单创建, sales_item: 从销售订单行创建
    
    # 从销售订单继承的规格型号信息
    spec_extended = db.Column(db.String(100))  # 加长（具体值）
    spec_gasket = db.Column(db.String(100))  # 垫板（具体值）
    spec_joint = db.Column(db.String(100))  # 接头（具体值）
    spec_drilling = db.Column(db.String(100))  # 钻孔（具体值）
    spec_other = db.Column(db.String(100))  # 其他（具体值）
    spec_other_desc = db.Column(db.String(200))  # 其他规格描述
    direction = db.Column(db.String(50))  # 开向
    
    # 新增规格型号字段（与销售订单行保持一致）
    spec_splice_hole = db.Column(db.String(100))  # 接续线孔
    spec_gasket_hole = db.Column(db.String(100))  # 垫板孔型
    anti_corrosion = db.Column(db.String(100))  # 辙叉防腐
    rubber_gasket_material = db.Column(db.String(100))  # 橡胶垫板材质
    turnout_rail = db.Column(db.String(100))  # 道岔配轨
    using_unit = db.Column(db.String(100))  # 使用单位
    
    __table_args__ = (
        db.UniqueConstraint('global_sn', name='uq_production_order_global_sn'),
        db.UniqueConstraint('order_number', name='uq_production_order_number'),
    )
    
    # 关系
    creator = db.relationship('User', backref=db.backref('created_production_orders', lazy='dynamic'))
    batches = db.relationship('ProductionBatch', backref='production_order', lazy='dynamic', cascade='all, delete-orphan')
    material_allocations = db.relationship('MaterialAllocation', backref='production_order', lazy='dynamic', cascade='all, delete-orphan')
    sales_order = db.relationship('SalesOrder', backref=db.backref('production_orders', lazy='dynamic'))
    sales_order_item = db.relationship('SalesOrderItem', backref=db.backref('production_orders', lazy='dynamic'))
    
    def __init__(self, **kwargs):
        super(ProductionOrder, self).__init__(**kwargs)
        if not self.global_sn:
            self.global_sn = SerialNumber.get_next_number()
        if not self.order_number:
            self.order_number = f"PO{SerialNumber.get_next_number()}"
    
    @property
    def completion_rate(self):
        """完成率"""
        if self.planned_quantity == 0:
            return 0
        return (self.completed_quantity / self.planned_quantity) * 100
    
    @property
    def remaining_quantity(self):
        """剩余数量"""
        return max(0, self.planned_quantity - self.completed_quantity)

    @property
    def scheduled_quantity(self):
        """已下达批次数量（不含已取消批次）"""
        try:
            from sqlalchemy import func
            total = db.session.query(func.coalesce(func.sum(ProductionBatch.batch_quantity), 0)) \
                .filter(ProductionBatch.production_order_id == self.id) \
                .filter(ProductionBatch.status != 'cancelled') \
                .scalar()
            return int(total or 0)
        except Exception:
            return 0

    @property
    def remaining_to_schedule(self):
        """剩余待下达数量（计划 - 已下达批次，不含取消）"""
        return max(0, (self.planned_quantity or 0) - (self.scheduled_quantity or 0))
    
    @property
    def specifications(self):
        """获取规格型号列表"""
        specs = []
        if self.spec_extended:
            specs.append(f'加长型式({self.spec_extended})')
        if self.spec_gasket:
            specs.append(f'垫板({self.spec_gasket})')
        if self.spec_joint:
            specs.append(f'接头型式({self.spec_joint})')
        if self.spec_drilling:
            specs.append(f'跳线孔({self.spec_drilling})')
        if self.spec_splice_hole:
            specs.append(f'接续线孔({self.spec_splice_hole})')
        if self.spec_gasket_hole:
            specs.append(f'垫板孔型({self.spec_gasket_hole})')
        if self.anti_corrosion:
            specs.append(f'辙叉防腐({self.anti_corrosion})')
        if self.rubber_gasket_material:
            specs.append(f'橡胶垫板材质({self.rubber_gasket_material})')
        if self.turnout_rail:
            specs.append(f'道岔配轨({self.turnout_rail})')
        if self.using_unit:
            specs.append(f'使用单位({self.using_unit})')
        if self.spec_other:
            specs.append(f'其他({self.spec_other})')
        return specs
    
    @property
    def specifications_text(self):
        """获取规格型号文本"""
        specs = self.specifications
        return ', '.join(specs) if specs else '无'
    
    def allocate_materials(self):
        """根据产品BOM分配原材料"""
        try:
            # 清除现有分配
            MaterialAllocation.query.filter_by(production_order_id=self.id).delete()
            
            # 根据BOM分配材料
            for bom_item in self.product.bom_items:
                required_quantity = bom_item.actual_quantity * self.planned_quantity
                
                allocation = MaterialAllocation(
                    production_order_id=self.id,
                    material_type=bom_item.material_type,
                    material_id=bom_item.material_id,
                    required_quantity=required_quantity,
                    unit=bom_item.unit,
                    notes=f"根据BOM自动分配 - {bom_item.material_name}"
                )
                db.session.add(allocation)
            
            db.session.commit()
            return True
        except Exception as e:
            db.session.rollback()
            return False
    
    def __repr__(self):
        return f'<ProductionOrder {self.order_number}: {self.product.product_name}>'

class ProductionBatch(db.Model):
    """生产批次"""
    __tablename__ = 'production_batches'
    
    id = db.Column(db.Integer, primary_key=True)
    global_sn = db.Column(db.String(8), unique=True, nullable=False)  # 全局流水号
    batch_number = db.Column(db.String(50), unique=True, nullable=False, index=True)  # 批次号
    production_order_id = db.Column(db.Integer, db.ForeignKey('production_orders.id', ondelete='CASCADE'), nullable=False)
    batch_quantity = db.Column(db.Integer, nullable=False)  # 批次数量
    status = db.Column(db.String(20), default='pending')  # pending, in_progress, completed, cancelled
    start_date = db.Column(db.Date)  # 开始日期
    end_date = db.Column(db.Date)  # 完成日期
    notes = db.Column(db.Text)  # 备注
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # 从生产订单继承的规格型号信息
    spec_extended = db.Column(db.String(100))  # 加长（具体值）
    spec_gasket = db.Column(db.String(100))  # 垫板（具体值）
    spec_joint = db.Column(db.String(100))  # 接头（具体值）
    spec_drilling = db.Column(db.String(100))  # 钻孔（具体值）
    spec_other = db.Column(db.String(100))  # 其他（具体值）
    spec_other_desc = db.Column(db.String(200))  # 其他规格描述
    direction = db.Column(db.String(50))  # 开向
    
    # 新增规格型号字段（与销售订单行保持一致）
    spec_splice_hole = db.Column(db.String(100))  # 接续线孔
    spec_gasket_hole = db.Column(db.String(100))  # 垫板孔型
    anti_corrosion = db.Column(db.String(100))  # 辙叉防腐
    rubber_gasket_material = db.Column(db.String(100))  # 橡胶垫板材质
    turnout_rail = db.Column(db.String(100))  # 道岔配轨
    using_unit = db.Column(db.String(100))  # 使用单位
    
    __table_args__ = (
        db.UniqueConstraint('global_sn', name='uq_production_batch_global_sn'),
        db.UniqueConstraint('batch_number', name='uq_production_batch_number'),
    )
    
    # 关系
    batch_items = db.relationship('ProductionBatchItem', backref='batch', lazy='dynamic', cascade='all, delete-orphan')
    
    def __init__(self, **kwargs):
        super(ProductionBatch, self).__init__(**kwargs)
        if not self.global_sn:
            self.global_sn = SerialNumber.get_next_number()
        if not self.batch_number:
            # 生成批次号：订单号 + 批次序号（健壮：基于已存在最大序号递增，避免并发/取消造成重复）
            order = ProductionOrder.query.get(kwargs.get('production_order_id'))
            if order:
                try:
                    # 取该订单已存在批次号中的最大序号
                    existing_numbers = []
                    for (bn,) in db.session.query(ProductionBatch.batch_number)\
                            .filter(ProductionBatch.production_order_id == order.id).all():
                        if bn and '-B' in bn:
                            try:
                                existing_numbers.append(int(bn.split('-B')[-1]))
                            except Exception:
                                # 非预期格式时忽略该条
                                pass
                    next_index = (max(existing_numbers) if existing_numbers else 0) + 1
                    candidate = f"{order.order_number}-B{next_index:03d}"
                    # 兜底：若偶发并发导致冲突，则继续递增直到唯一
                    while db.session.query(ProductionBatch.id)\
                            .filter(ProductionBatch.batch_number == candidate).first():
                        next_index += 1
                        candidate = f"{order.order_number}-B{next_index:03d}"
                    self.batch_number = candidate
                except Exception:
                    # 回退到简单计数法（极端情况下可能重复，但已尽力规避）
                    batch_count = ProductionBatch.query.filter_by(production_order_id=order.id).count()
                    self.batch_number = f"{order.order_number}-B{batch_count + 1:03d}"
    
    def generate_product_codes(self):
        """为批次中的产品生成编码"""
        try:
            product = self.production_order.product
            if not product.code_rule:
                return False
            
            # 生成产品编码
            codes = product.generate_product_code(self.batch_quantity)
            if not codes:
                return False
            
            # 如果只有一个编码，转换为列表
            if not isinstance(codes, list):
                codes = [codes]
            
            # 创建批次项目
            for i, code in enumerate(codes):
                batch_item = ProductionBatchItem(
                    batch_id=self.id,
                    item_sequence=i + 1,
                    product_code=code,
                    status='pending'
                )
                db.session.add(batch_item)
            
            db.session.commit()
            return True
        except Exception as e:
            db.session.rollback()
            return False
    
    @property
    def specifications(self):
        """获取规格型号列表"""
        specs = []
        if self.spec_extended:
            specs.append(f'加长型式({self.spec_extended})')
        if self.spec_gasket:
            specs.append(f'垫板({self.spec_gasket})')
        if self.spec_joint:
            specs.append(f'接头型式({self.spec_joint})')
        if self.spec_drilling:
            specs.append(f'跳线孔({self.spec_drilling})')
        if self.spec_splice_hole:
            specs.append(f'接续线孔({self.spec_splice_hole})')
        if self.spec_gasket_hole:
            specs.append(f'垫板孔型({self.spec_gasket_hole})')
        if self.anti_corrosion:
            specs.append(f'辙叉防腐({self.anti_corrosion})')
        if self.rubber_gasket_material:
            specs.append(f'橡胶垫板材质({self.rubber_gasket_material})')
        if self.turnout_rail:
            specs.append(f'道岔配轨({self.turnout_rail})')
        if self.using_unit:
            specs.append(f'使用单位({self.using_unit})')
        if self.spec_other:
            specs.append(f'其他({self.spec_other})')
        return specs
    
    @property
    def specifications_text(self):
        """获取规格型号文本"""
        specs = self.specifications
        return ', '.join(specs) if specs else '无'
    
    def __repr__(self):
        return f'<ProductionBatch {self.batch_number}: {self.batch_quantity}件>'

class ProductionBatchItem(db.Model):
    """生产批次项目"""
    __tablename__ = 'production_batch_items'
    
    id = db.Column(db.Integer, primary_key=True)
    global_sn = db.Column(db.String(8), unique=True, nullable=False)  # 全局流水号
    batch_id = db.Column(db.Integer, db.ForeignKey('production_batches.id', ondelete='CASCADE'), nullable=False)
    item_sequence = db.Column(db.Integer, nullable=False)  # 项目序号
    product_code = db.Column(db.String(100), unique=True, nullable=False, index=True)  # 产品编码
    status = db.Column(db.String(20), default='pending')  # pending, in_progress, completed, scrapped
    production_date = db.Column(db.Date)  # 生产日期
    inspector = db.Column(db.String(50))  # 检验员
    quality_status = db.Column(db.String(20))  # pass, fail, pending
    notes = db.Column(db.Text)  # 备注
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)  # 完成时间
    
    __table_args__ = (
        db.UniqueConstraint('global_sn', name='uq_production_batch_item_global_sn'),
        db.UniqueConstraint('product_code', name='uq_production_batch_item_code'),
        db.UniqueConstraint('batch_id', 'item_sequence', name='uq_batch_item_sequence'),
    )
    
    def __init__(self, **kwargs):
        super(ProductionBatchItem, self).__init__(**kwargs)
        if not self.global_sn:
            self.global_sn = SerialNumber.get_next_number()
    
    def __repr__(self):
        return f'<ProductionBatchItem {self.product_code}>'

class MaterialAllocation(db.Model):
    """物料分配"""
    __tablename__ = 'material_allocations'
    
    id = db.Column(db.Integer, primary_key=True)
    global_sn = db.Column(db.String(8), unique=True, nullable=False)  # 全局流水号
    production_order_id = db.Column(db.Integer, db.ForeignKey('production_orders.id', ondelete='CASCADE'), nullable=False)
    material_type = db.Column(db.String(20), nullable=False)  # raw, finished, product
    material_id = db.Column(db.Integer, nullable=False)  # 物料ID
    required_quantity = db.Column(db.Float, nullable=False)  # 需求数量
    allocated_quantity = db.Column(db.Float, default=0)  # 已分配数量
    consumed_quantity = db.Column(db.Float, default=0)  # 已消耗数量
    unit = db.Column(db.String(20), default='件')  # 单位
    status = db.Column(db.String(20), default='pending')  # pending, allocated, consumed
    notes = db.Column(db.Text)  # 备注
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('global_sn', name='uq_material_allocation_global_sn'),
        db.Index('ix_material_allocation_material', 'material_type', 'material_id'),
    )
    
    def __init__(self, **kwargs):
        super(MaterialAllocation, self).__init__(**kwargs)
        if not self.global_sn:
            self.global_sn = SerialNumber.get_next_number()
    
    @property
    def material_info(self):
        """获取物料信息"""
        if self.material_type == 'raw':
            return RawMaterial.query.get(self.material_id)
        elif self.material_type == 'finished':
            return FinishedProduct.query.get(self.material_id)
        elif self.material_type == 'product':
            return Product.query.get(self.material_id)
        return None
    
    @property
    def material_name(self):
        """获取物料名称"""
        material = self.material_info
        if material:
            if self.material_type == 'raw':
                return material.material_name
            elif self.material_type == 'finished':
                return material.product_number
            elif self.material_type == 'product':
                return f"{material.product_name} ({material.product_code})"
        return '未知物料'
    
    @property
    def shortage_quantity(self):
        """短缺数量"""
        return max(0, self.required_quantity - self.allocated_quantity)
    
    def __repr__(self):
        return f'<MaterialAllocation {self.material_name}: {self.required_quantity}{self.unit}>'

class Customer(db.Model):
    """客户管理"""
    __tablename__ = 'customers'
    
    id = db.Column(db.Integer, primary_key=True)
    global_sn = db.Column(db.String(8), unique=True, nullable=False)  # 全局流水号
    customer_code = db.Column(db.String(50), unique=True, nullable=False, index=True)  # 客户编码
    customer_name = db.Column(db.String(100), nullable=False)  # 客户名称
    customer_type = db.Column(db.String(20), default='enterprise')  # 客户类型: enterprise(企业), individual(个人)
    contact_person = db.Column(db.String(50))  # 联系人
    contact_phone = db.Column(db.String(20))  # 联系电话
    contact_email = db.Column(db.String(100))  # 联系邮箱
    tax_number = db.Column(db.String(50))  # 税号
    credit_limit = db.Column(db.Float, default=0)  # 信用额度
    payment_terms = db.Column(db.String(50))  # 付款条件
    industry = db.Column(db.String(50))  # 所属行业
    company_size = db.Column(db.String(20))  # 公司规模: small, medium, large
    website = db.Column(db.String(200))  # 公司网站
    status = db.Column(db.String(20), default='active')  # 状态: active(活跃), inactive(非活跃), blacklist(黑名单)
    notes = db.Column(db.Text)  # 备注
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('global_sn', name='uq_customer_global_sn'),
        db.UniqueConstraint('customer_code', name='uq_customer_code'),
    )
    
    # 关系
    creator = db.relationship('User', backref=db.backref('created_customers', lazy='dynamic'))
    addresses = db.relationship('CustomerAddress', backref='customer', lazy='dynamic', cascade='all, delete-orphan')
    
    def __init__(self, **kwargs):
        super(Customer, self).__init__(**kwargs)
        if not self.global_sn:
            self.global_sn = SerialNumber.get_next_number()
        if not self.customer_code:
            # 自动生成客户编码
            self.customer_code = f"C{SerialNumber.get_next_number()}"
    
    @property
    def primary_address(self):
        """获取主要地址"""
        return self.addresses.filter_by(is_primary=True).first()
    
    @property
    def address_count(self):
        """地址数量"""
        return self.addresses.count()
    
    def __repr__(self):
        return f'<Customer {self.customer_code}: {self.customer_name}>'

class CustomerAddress(db.Model):
    """客户地址"""
    __tablename__ = 'customer_addresses'
    
    id = db.Column(db.Integer, primary_key=True)
    global_sn = db.Column(db.String(8), unique=True, nullable=False)  # 全局流水号
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id', ondelete='CASCADE'), nullable=False)
    address_type = db.Column(db.String(20), default='shipping')  # 地址类型: shipping(收货), billing(账单), office(办公)
    contact_person = db.Column(db.String(50), nullable=False)  # 联系人
    contact_phone = db.Column(db.String(20), nullable=False)  # 联系电话
    province = db.Column(db.String(50), nullable=False)  # 省份
    city = db.Column(db.String(50), nullable=False)  # 城市
    district = db.Column(db.String(50))  # 区县
    detailed_address = db.Column(db.String(200), nullable=False)  # 详细地址
    postal_code = db.Column(db.String(10))  # 邮政编码
    is_primary = db.Column(db.Boolean, default=False)  # 是否为主要地址
    is_active = db.Column(db.Boolean, default=True)  # 是否启用
    notes = db.Column(db.Text)  # 备注
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('global_sn', name='uq_customer_address_global_sn'),
    )
    
    def __init__(self, **kwargs):
        super(CustomerAddress, self).__init__(**kwargs)
        if not self.global_sn:
            self.global_sn = SerialNumber.get_next_number()
    
    @property
    def full_address(self):
        """完整地址"""
        parts = [self.province, self.city]
        if self.district:
            parts.append(self.district)
        parts.append(self.detailed_address)
        return ''.join(parts)
    
    def __repr__(self):
        return f'<CustomerAddress {self.id}: {self.contact_person} - {self.full_address}>'

class SalesOrder(db.Model):
    """销售订单"""
    __tablename__ = 'sales_orders'
    
    id = db.Column(db.Integer, primary_key=True)
    global_sn = db.Column(db.String(8), unique=True, nullable=False)  # 全局流水号
    order_number = db.Column(db.String(50), unique=True, nullable=False, index=True)  # 订单编号
    order_source = db.Column(db.String(50), nullable=False)  # 订单来源
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)  # 客户ID
    year_month = db.Column(db.String(7), nullable=False)  # 年月 (YYYY-MM)
    total_quantity = db.Column(db.Integer, default=0)  # 合计数量（自动计算）
    order_date = db.Column(db.DateTime, default=datetime.utcnow)  # 下单时间
    status = db.Column(db.String(20), default='pending')  # 状态: pending(待处理), confirmed(已确认), in_production(生产中), completed(已完成), cancelled(已取消)
    notes = db.Column(db.Text)  # 备注
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('global_sn', name='uq_sales_order_global_sn'),
        db.UniqueConstraint('order_number', name='uq_sales_order_number'),
    )
    
    # 关系
    customer = db.relationship('Customer', backref=db.backref('sales_orders', lazy='dynamic'))
    creator = db.relationship('User', backref=db.backref('created_sales_orders', lazy='dynamic'))
    order_items = db.relationship('SalesOrderItem', backref='sales_order', lazy='dynamic', cascade='all, delete-orphan')
    
    def __init__(self, **kwargs):
        super(SalesOrder, self).__init__(**kwargs)
        if not self.global_sn:
            self.global_sn = SerialNumber.get_next_number()
        if not self.order_number:
            self.order_number = f"SO{SerialNumber.get_next_number()}"
    
    def calculate_total_quantity(self):
        """计算合计数量"""
        self.total_quantity = sum(item.quantity for item in self.order_items)
    
    def __repr__(self):
        return f'<SalesOrder {self.order_number}: {self.customer.customer_name if self.customer else "Unknown"}>'

class SalesOrderItem(db.Model):
    """销售订单行"""
    __tablename__ = 'sales_order_items'
    
    id = db.Column(db.Integer, primary_key=True)
    global_sn = db.Column(db.String(8), unique=True, nullable=False)  # 全局流水号
    sales_order_id = db.Column(db.Integer, db.ForeignKey('sales_orders.id', ondelete='CASCADE'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)  # 产品ID（关联产品管理）
    quantity = db.Column(db.Integer, nullable=False)  # 数量
    direction = db.Column(db.String(50))  # 开向
    
    # 规格型号（可同时选择多个）
    spec_extended = db.Column(db.String(100))  # 加长（具体值）
    spec_gasket = db.Column(db.String(100))  # 垫板（具体值）
    spec_joint = db.Column(db.String(100))  # 接头（具体值）
    spec_drilling = db.Column(db.String(100))  # 钻孔（具体值）
    spec_other = db.Column(db.String(100))  # 其他（具体值）
    spec_other_desc = db.Column(db.String(200))  # 其他规格描述

    # 新增：孔型/配置信息等
    spec_splice_hole = db.Column(db.String(100))  # 接续线孔
    spec_gasket_hole = db.Column(db.String(100))  # 垫板孔型
    anti_corrosion = db.Column(db.String(100))  # 辙叉防腐
    rubber_gasket_material = db.Column(db.String(100))  # 橡胶垫板材质
    turnout_rail = db.Column(db.String(100))  # 道岔配轨
    using_unit = db.Column(db.String(100))  # 使用单位（默认客户名，可修改）
    
    customer_address_id = db.Column(db.Integer, db.ForeignKey('customer_addresses.id'), nullable=True)  # 客户地址ID
    order_time = db.Column(db.DateTime, default=datetime.utcnow)  # 下单时间
    station_notes = db.Column(db.Text)  # 到站备注
    
    # 分批到货信息（JSON格式存储）
    delivery_batches = db.Column(db.Text)  # JSON格式: [{"batch_no": 1, "delivery_date": "2025-01-15", "quantity": 10, "notes": ""}]
    
    sequence = db.Column(db.Integer, default=0)  # 排序序号
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('global_sn', name='uq_sales_order_item_global_sn'),
    )
    
    # 关系
    product = db.relationship('Product', backref=db.backref('sales_order_items', lazy='dynamic'))
    customer_address = db.relationship('CustomerAddress', backref=db.backref('sales_order_items', lazy='dynamic'))
    
    def __init__(self, **kwargs):
        super(SalesOrderItem, self).__init__(**kwargs)
        if not self.global_sn:
            self.global_sn = SerialNumber.get_next_number()
    
    @property
    def product_name(self):
        """获取产品名称"""
        return self.product.product_name if self.product else '未知产品'
    
    @property
    def drawing_number(self):
        """获取图号"""
        return self.product.drawing_number if self.product else ''
    
    @property
    def unit(self):
        """获取单位"""
        return self.product.unit if self.product else '件'
    
    @property
    def specifications(self):
        """获取规格型号列表"""
        specs = []
        if self.spec_extended:
            specs.append(f'加长型式({self.spec_extended})')
        if self.spec_gasket:
            specs.append(f'垫板({self.spec_gasket})')
        if self.spec_joint:
            specs.append(f'接头型式({self.spec_joint})')
        if self.spec_drilling:
            specs.append(f'跳线孔({self.spec_drilling})')
        if self.spec_splice_hole:
            specs.append(f'接续线孔({self.spec_splice_hole})')
        if self.spec_gasket_hole:
            specs.append(f'垫板孔型({self.spec_gasket_hole})')
        if self.anti_corrosion:
            specs.append(f'辙叉防腐({self.anti_corrosion})')
        if self.rubber_gasket_material:
            specs.append(f'橡胶垫板材质({self.rubber_gasket_material})')
        if self.turnout_rail:
            specs.append(f'道岔配轨({self.turnout_rail})')
        if self.using_unit:
            specs.append(f'使用单位({self.using_unit})')
        if self.spec_other:
            specs.append(f'其他({self.spec_other})')
        return specs
    
    @property
    def specifications_text(self):
        """获取规格型号文本"""
        specs = self.specifications
        return ', '.join(specs) if specs else '无'
    
    @property
    def delivery_batches_list(self):
        """获取分批到货列表"""
        if self.delivery_batches:
            try:
                import json
                return json.loads(self.delivery_batches)
            except:
                return []
        return []
    
    def set_delivery_batches(self, batches):
        """设置分批到货信息"""
        import json
        self.delivery_batches = json.dumps(batches, ensure_ascii=False)
    
    @property
    def delivery_status(self):
        """获取分批到货状态"""
        batches = self.delivery_batches_list
        if not batches:
            return 'not_set'  # 未设置
        
        from datetime import datetime, date
        today = date.today()
        
        total_delivered = 0
        overdue_count = 0
        
        for batch in batches:
            delivery_date = batch.get('delivery_date')
            if delivery_date:
                try:
                    if isinstance(delivery_date, str):
                        delivery_date = datetime.strptime(delivery_date, '%Y-%m-%d').date()
                    
                    # 检查是否逾期（这里假设到货日期就是交付日期）
                    if delivery_date < today:
                        total_delivered += batch.get('quantity', 0)
                    elif delivery_date < today:
                        overdue_count += 1
                except:
                    pass
        
        if total_delivered >= self.quantity:
            return 'completed'  # 已完成
        elif total_delivered > 0:
            return 'partial'    # 部分完成
        elif overdue_count > 0:
            return 'overdue'    # 有逾期
        else:
            return 'pending'    # 待交付
    
    @property
    def delivery_progress(self):
        """获取分批到货进度"""
        batches = self.delivery_batches_list
        if not batches:
            return 0
        
        from datetime import datetime, date
        today = date.today()
        
        delivered_quantity = 0
        for batch in batches:
            delivery_date = batch.get('delivery_date')
            if delivery_date:
                try:
                    if isinstance(delivery_date, str):
                        delivery_date = datetime.strptime(delivery_date, '%Y-%m-%d').date()
                    
                    # 如果到货日期已过，认为已交付
                    if delivery_date <= today:
                        delivered_quantity += batch.get('quantity', 0)
                except:
                    pass
        
        return min(100, int((delivered_quantity / self.quantity) * 100)) if self.quantity > 0 else 0
    
    def __repr__(self):
        return f'<SalesOrderItem {self.id}: {self.product_name} x {self.quantity}>'


class NotificationRule(db.Model):
    """通知规则"""
    __tablename__ = 'notification_rules'
    
    id = db.Column(db.Integer, primary_key=True)
    global_sn = db.Column(db.String(8), unique=True, nullable=False)  # 全局流水号
    rule_name = db.Column(db.String(100), nullable=False)  # 规则名称
    trigger_type = db.Column(db.String(50), nullable=False)  # 触发类型
    trigger_conditions = db.Column(db.JSON)  # 触发条件（JSON格式）
    receiver_type = db.Column(db.String(20), nullable=False)  # 接收者类型：user, role, department
    receiver_config = db.Column(db.JSON)  # 接收者配置（JSON格式）
    notification_methods = db.Column(db.JSON)  # 通知方式：[system, email, sms]
    template_config = db.Column(db.JSON)  # 模板配置
    is_active = db.Column(db.Boolean, default=True)  # 是否启用
    priority = db.Column(db.Integer, default=0)  # 优先级
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('global_sn', name='uq_notification_rule_global_sn'),
    )
    
    # 关系
    creator = db.relationship('User', backref=db.backref('created_notification_rules', lazy='dynamic'))
    
    def __init__(self, **kwargs):
        super(NotificationRule, self).__init__(**kwargs)
        if not self.global_sn:
            self.global_sn = SerialNumber.get_next_number()
    
    def __repr__(self):
        return f'<NotificationRule {self.rule_name}>'


class Notification(db.Model):
    """通知记录"""
    __tablename__ = 'notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    global_sn = db.Column(db.String(8), unique=True, nullable=False)  # 全局流水号
    rule_id = db.Column(db.Integer, db.ForeignKey('notification_rules.id'), nullable=True)  # 关联规则
    trigger_type = db.Column(db.String(50), nullable=False)  # 触发类型
    trigger_data = db.Column(db.JSON)  # 触发数据（JSON格式）
    title = db.Column(db.String(200), nullable=False)  # 通知标题
    content = db.Column(db.Text, nullable=False)  # 通知内容
    notification_type = db.Column(db.String(20), default='info')  # 通知类型：info, warning, error, success
    priority = db.Column(db.String(20), default='normal')  # 优先级：low, normal, high, urgent
    status = db.Column(db.String(20), default='pending')  # 状态：pending, sent, failed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    sent_at = db.Column(db.DateTime)  # 发送时间
    
    # 关联相关业务对象
    related_model = db.Column(db.String(50))  # 关联模型名称
    related_id = db.Column(db.Integer)  # 关联对象ID
    
    __table_args__ = (
        db.UniqueConstraint('global_sn', name='uq_notification_global_sn'),
        db.Index('ix_notification_status', 'status'),
        db.Index('ix_notification_type', 'trigger_type'),
        db.Index('ix_notification_created', 'created_at'),
    )
    
    # 关系
    rule = db.relationship('NotificationRule', backref=db.backref('notifications', lazy='dynamic'))
    receivers = db.relationship('NotificationReceiver', back_populates='notification', cascade='all, delete-orphan')
    
    def __init__(self, **kwargs):
        super(Notification, self).__init__(**kwargs)
        if not self.global_sn:
            self.global_sn = SerialNumber.get_next_number()
    
    @property
    def unread_count(self):
        """未读数量"""
        return NotificationReceiver.query.filter_by(
            notification_id=self.id, 
            status='unread'
        ).count()
    
    @property
    def total_receivers(self):
        """接收者总数"""
        return NotificationReceiver.query.filter_by(notification_id=self.id).count()
    
    def __repr__(self):
        return f'<Notification {self.title}>'


class NotificationReceiver(db.Model):
    """通知接收者"""
    __tablename__ = 'notification_receivers'
    
    id = db.Column(db.Integer, primary_key=True)
    notification_id = db.Column(db.Integer, db.ForeignKey('notifications.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    status = db.Column(db.String(20), default='unread')  # 状态：unread, read, archived
    read_at = db.Column(db.DateTime)  # 阅读时间
    archived_at = db.Column(db.DateTime)  # 归档时间
    delivery_method = db.Column(db.String(20), default='system')  # 投递方式：system, email, sms
    delivery_status = db.Column(db.String(20), default='pending')  # 投递状态：pending, delivered, failed
    delivery_at = db.Column(db.DateTime)  # 投递时间
    failure_reason = db.Column(db.Text)  # 失败原因
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('notification_id', 'user_id', name='uq_notification_receiver'),
        db.Index('ix_receiver_user_status', 'user_id', 'status'),
        db.Index('ix_receiver_status', 'status'),
    )
    
    # 关系
    notification = db.relationship('Notification', back_populates='receivers')
    user = db.relationship('User', backref=db.backref('received_notifications', lazy='dynamic'))
    
    def mark_as_read(self):
        """标记为已读"""
        if self.status == 'unread':
            self.status = 'read'
            self.read_at = datetime.utcnow()
            db.session.commit()
    
    def archive(self):
        """归档"""
        self.status = 'archived'
        self.archived_at = datetime.utcnow()
        db.session.commit()
    
    def __repr__(self):
        return f'<NotificationReceiver {self.notification.title} -> {self.user.username}>'


class NotificationTemplate(db.Model):
    """通知模板"""
    __tablename__ = 'notification_templates'
    
    id = db.Column(db.Integer, primary_key=True)
    global_sn = db.Column(db.String(8), unique=True, nullable=False)  # 全局流水号
    template_code = db.Column(db.String(50), unique=True, nullable=False)  # 模板编码
    template_name = db.Column(db.String(100), nullable=False)  # 模板名称
    trigger_type = db.Column(db.String(50), nullable=False)  # 适用的触发类型
    title_template = db.Column(db.String(200), nullable=False)  # 标题模板
    content_template = db.Column(db.Text, nullable=False)  # 内容模板
    variables = db.Column(db.JSON)  # 可用变量说明
    notification_type = db.Column(db.String(20), default='info')  # 默认通知类型
    is_active = db.Column(db.Boolean, default=True)  # 是否启用
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('global_sn', name='uq_notification_template_global_sn'),
        db.UniqueConstraint('template_code', name='uq_notification_template_code'),
    )
    
    # 关系
    creator = db.relationship('User', backref=db.backref('created_notification_templates', lazy='dynamic'))
    
    def __init__(self, **kwargs):
        super(NotificationTemplate, self).__init__(**kwargs)
        if not self.global_sn:
            self.global_sn = SerialNumber.get_next_number()
    
    def render(self, variables):
        """渲染模板"""
        title = self.title_template
        content = self.content_template
        
        for key, value in variables.items():
            title = title.replace(f'{{{key}}}', str(value))
            content = content.replace(f'{{{key}}}', str(value))
        
            return title, content
    
    def __repr__(self):
        return f'<NotificationTemplate {self.template_name}>'

class MaterialRequisition(db.Model):
    """物料领用记录"""
    __tablename__ = 'material_requisitions'
    
    id = db.Column(db.Integer, primary_key=True)
    global_sn = db.Column(db.String(8), unique=True, nullable=False)  # 全局流水号
    requisition_number = db.Column(db.String(50), unique=True, nullable=False, index=True)  # 领用单号
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)  # 领用人
    department = db.Column(db.String(50), nullable=False)  # 领用部门
    purpose = db.Column(db.String(200), nullable=False)  # 领用用途
    project_code = db.Column(db.String(50))  # 项目编号
    production_order_id = db.Column(db.Integer, db.ForeignKey('production_orders.id'))  # 关联生产订单
    status = db.Column(db.String(20), default='pending')  # pending: 待审批, approved: 已审批, rejected: 已拒绝, completed: 已完成, cancelled: 已取消
    priority = db.Column(db.String(20), default='normal')  # low, normal, high, urgent
    requested_date = db.Column(db.DateTime, default=datetime.utcnow)  # 申请时间
    required_date = db.Column(db.Date, nullable=False)  # 需要日期
    approved_by = db.Column(db.Integer, db.ForeignKey('user.id'))  # 审批人
    approved_at = db.Column(db.DateTime)  # 审批时间
    issued_by = db.Column(db.Integer, db.ForeignKey('user.id'))  # 发料人
    issued_at = db.Column(db.DateTime)  # 发料时间
    notes = db.Column(db.Text)  # 备注
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('global_sn', name='uq_material_requisition_global_sn'),
        db.UniqueConstraint('requisition_number', name='uq_material_requisition_number'),
        db.Index('ix_material_requisition_status', 'status'),
        db.Index('ix_material_requisition_date', 'requested_date'),
    )
    
    # 关系
    employee = db.relationship('Employee', backref=db.backref('material_requisitions', lazy='dynamic'))
    production_order = db.relationship('ProductionOrder', backref=db.backref('material_requisitions', lazy='dynamic'))
    approver = db.relationship('User', foreign_keys=[approved_by], backref=db.backref('approved_requisitions', lazy='dynamic'))
    issuer = db.relationship('User', foreign_keys=[issued_by], backref=db.backref('issued_requisitions', lazy='dynamic'))
    items = db.relationship('MaterialRequisitionItem', backref='requisition', lazy='dynamic', cascade='all, delete-orphan')
    
    def __init__(self, **kwargs):
        super(MaterialRequisition, self).__init__(**kwargs)
        if not self.global_sn:
            self.global_sn = SerialNumber.get_next_number()
        if not self.requisition_number:
            # 生成领用单号：REQ + 年月日 + 4位序号
            today = datetime.now()
            prefix = f"REQ{today.strftime('%Y%m%d')}"
            # 查找当天最大序号
            last_req = MaterialRequisition.query.filter(
                MaterialRequisition.requisition_number.like(f"{prefix}%")
            ).order_by(MaterialRequisition.requisition_number.desc()).first()
            
            if last_req:
                last_seq = int(last_req.requisition_number[-4:])
                new_seq = last_seq + 1
            else:
                new_seq = 1
            
            self.requisition_number = f"{prefix}{new_seq:04d}"
    
    @property
    def total_items(self):
        """总项目数"""
        return self.items.count()
    
    @property
    def total_quantity(self):
        """总数量"""
        return sum(item.quantity for item in self.items)
    
    @property
    def can_approve(self):
        """是否可以审批"""
        return self.status == 'pending'
    
    @property
    def can_issue(self):
        """是否可以发料"""
        return self.status == 'approved'
    
    @property
    def can_cancel(self):
        """是否可以取消"""
        return self.status in ['pending', 'approved']
    
    def __repr__(self):
        return f'<MaterialRequisition {self.requisition_number}>'

class MaterialRequisitionItem(db.Model):
    """物料领用明细"""
    __tablename__ = 'material_requisition_items'
    
    id = db.Column(db.Integer, primary_key=True)
    global_sn = db.Column(db.String(8), unique=True, nullable=False)  # 全局流水号
    requisition_id = db.Column(db.Integer, db.ForeignKey('material_requisitions.id', ondelete='CASCADE'), nullable=False)
    material_type = db.Column(db.String(20), nullable=False)  # raw: 原材料, consumable: 易耗品, finished: 成品
    material_id = db.Column(db.Integer, nullable=False)  # 物料ID
    quantity = db.Column(db.Float, nullable=False)  # 申请数量
    issued_quantity = db.Column(db.Float, default=0)  # 已发数量
    unit = db.Column(db.String(20), default='件')  # 单位
    notes = db.Column(db.Text)  # 备注
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('global_sn', name='uq_material_requisition_item_global_sn'),
        db.Index('ix_material_requisition_item_material', 'material_type', 'material_id'),
    )
    
    def __init__(self, **kwargs):
        super(MaterialRequisitionItem, self).__init__(**kwargs)
        if not self.global_sn:
            self.global_sn = SerialNumber.get_next_number()
    
    @property
    def material_info(self):
        """获取物料信息"""
        if self.material_type == 'raw':
            return RawMaterial.query.get(self.material_id)
        elif self.material_type == 'consumable':
            return Consumable.query.get(self.material_id)
        elif self.material_type == 'finished':
            return FinishedProduct.query.get(self.material_id)
        return None
    
    @property
    def material_name(self):
        """获取物料名称"""
        material = self.material_info
        if material:
            if self.material_type == 'raw':
                return material.material_name
            elif self.material_type == 'consumable':
                return material.consumable_name
            elif self.material_type == 'finished':
                return f"{material.product_number} - {material.model}"
        return "未知物料"
    
    @property
    def remaining_quantity(self):
        """剩余待发数量"""
        return self.quantity - self.issued_quantity
    
    @property
    def is_fully_issued(self):
        """是否已完全发料"""
        return self.issued_quantity >= self.quantity
    
    def __repr__(self):
        return f'<MaterialRequisitionItem {self.material_name}: {self.quantity}>'

class MaterialReturn(db.Model):
    """物料归还记录"""
    __tablename__ = 'material_returns'
    
    id = db.Column(db.Integer, primary_key=True)
    global_sn = db.Column(db.String(8), unique=True, nullable=False)  # 全局流水号
    return_number = db.Column(db.String(50), unique=True, nullable=False, index=True)  # 归还单号
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)  # 归还人
    department = db.Column(db.String(50), nullable=False)  # 归还部门
    return_reason = db.Column(db.String(200), nullable=False)  # 归还原因
    original_requisition_id = db.Column(db.Integer, db.ForeignKey('material_requisitions.id'))  # 原领用单
    status = db.Column(db.String(20), default='pending')  # pending: 待确认, confirmed: 已确认, rejected: 已拒绝
    returned_date = db.Column(db.DateTime, default=datetime.utcnow)  # 归还时间
    confirmed_by = db.Column(db.Integer, db.ForeignKey('user.id'))  # 确认人
    confirmed_at = db.Column(db.DateTime)  # 确认时间
    notes = db.Column(db.Text)  # 备注
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('global_sn', name='uq_material_return_global_sn'),
        db.UniqueConstraint('return_number', name='uq_material_return_number'),
        db.Index('ix_material_return_status', 'status'),
        db.Index('ix_material_return_date', 'returned_date'),
    )
    
    # 关系
    employee = db.relationship('Employee', backref=db.backref('material_returns', lazy='dynamic'))
    original_requisition = db.relationship('MaterialRequisition', backref=db.backref('returns', lazy='dynamic'))
    confirmer = db.relationship('User', foreign_keys=[confirmed_by], backref=db.backref('confirmed_returns', lazy='dynamic'))
    items = db.relationship('MaterialReturnItem', backref='return_record', lazy='dynamic', cascade='all, delete-orphan')
    
    def __init__(self, **kwargs):
        super(MaterialReturn, self).__init__(**kwargs)
        if not self.global_sn:
            self.global_sn = SerialNumber.get_next_number()
        if not self.return_number:
            # 生成归还单号：RET + 年月日 + 4位序号
            today = datetime.now()
            prefix = f"RET{today.strftime('%Y%m%d')}"
            # 查找当天最大序号
            last_ret = MaterialReturn.query.filter(
                MaterialReturn.return_number.like(f"{prefix}%")
            ).order_by(MaterialReturn.return_number.desc()).first()
            
            if last_ret:
                last_seq = int(last_ret.return_number[-4:])
                new_seq = last_seq + 1
            else:
                new_seq = 1
            
            self.return_number = f"{prefix}{new_seq:04d}"
    
    @property
    def total_items(self):
        """总项目数"""
        return self.items.count()
    
    @property
    def total_quantity(self):
        """总数量"""
        return sum(item.quantity for item in self.items)
    
    @property
    def can_confirm(self):
        """是否可以确认"""
        return self.status == 'pending'
    
    def __repr__(self):
        return f'<MaterialReturn {self.return_number}>'

class MaterialReturnItem(db.Model):
    """物料归还明细"""
    __tablename__ = 'material_return_items'
    
    id = db.Column(db.Integer, primary_key=True)
    global_sn = db.Column(db.String(8), unique=True, nullable=False)  # 全局流水号
    return_id = db.Column(db.Integer, db.ForeignKey('material_returns.id', ondelete='CASCADE'), nullable=False)
    material_type = db.Column(db.String(20), nullable=False)  # raw: 原材料, consumable: 易耗品, finished: 成品
    material_id = db.Column(db.Integer, nullable=False)  # 物料ID
    quantity = db.Column(db.Float, nullable=False)  # 归还数量
    condition = db.Column(db.String(20), default='good')  # good: 完好, damaged: 损坏, expired: 过期
    unit = db.Column(db.String(20), default='件')  # 单位
    notes = db.Column(db.Text)  # 备注
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('global_sn', name='uq_material_return_item_global_sn'),
        db.Index('ix_material_return_item_material', 'material_type', 'material_id'),
    )
    
    def __init__(self, **kwargs):
        super(MaterialReturnItem, self).__init__(**kwargs)
        if not self.global_sn:
            self.global_sn = SerialNumber.get_next_number()
    
    @property
    def material_info(self):
        """获取物料信息"""
        if self.material_type == 'raw':
            return RawMaterial.query.get(self.material_id)
        elif self.material_type == 'consumable':
            return Consumable.query.get(self.material_id)
        elif self.material_type == 'finished':
            return FinishedProduct.query.get(self.material_id)
        return None
    
    @property
    def material_name(self):
        """获取物料名称"""
        material = self.material_info
        if material:
            if self.material_type == 'raw':
                return material.material_name
            elif self.material_type == 'consumable':
                return material.consumable_name
            elif self.material_type == 'finished':
                return f"{material.product_number} - {material.model}"
        return "未知物料"
    
    def __repr__(self):
        return f'<MaterialReturnItem {self.material_name}: {self.quantity}>'

class InventoryCount(db.Model):
    """库存盘点记录"""
    __tablename__ = 'inventory_counts'
    
    id = db.Column(db.Integer, primary_key=True)
    global_sn = db.Column(db.String(8), unique=True, nullable=False)  # 全局流水号
    count_number = db.Column(db.String(50), unique=True, nullable=False, index=True)  # 盘点单号
    count_name = db.Column(db.String(100), nullable=False)  # 盘点名称
    count_type = db.Column(db.String(20), default='full')  # full: 全盘, partial: 抽盘, cycle: 循环盘点
    count_scope = db.Column(db.String(50))  # 盘点范围：all, raw, consumable, finished
    warehouse_location = db.Column(db.String(100))  # 仓库位置
    status = db.Column(db.String(20), default='planning')  # planning: 计划中, counting: 盘点中, completed: 已完成, cancelled: 已取消
    planned_date = db.Column(db.Date, nullable=False)  # 计划盘点日期
    start_date = db.Column(db.DateTime)  # 开始盘点时间
    end_date = db.Column(db.DateTime)  # 结束盘点时间
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # 创建人
    count_team = db.Column(db.JSON)  # 盘点小组成员（JSON格式存储用户ID列表）
    notes = db.Column(db.Text)  # 备注
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('global_sn', name='uq_inventory_count_global_sn'),
        db.UniqueConstraint('count_number', name='uq_inventory_count_number'),
        db.Index('ix_inventory_count_status', 'status'),
        db.Index('ix_inventory_count_date', 'planned_date'),
    )
    
    # 关系
    creator = db.relationship('User', backref=db.backref('created_inventory_counts', lazy='dynamic'))
    items = db.relationship('InventoryCountItem', backref='count_record', lazy='dynamic', cascade='all, delete-orphan')
    
    def __init__(self, **kwargs):
        super(InventoryCount, self).__init__(**kwargs)
        if not self.global_sn:
            self.global_sn = SerialNumber.get_next_number()
        if not self.count_number:
            # 生成盘点单号：CNT + 年月日 + 4位序号
            today = datetime.now()
            prefix = f"CNT{today.strftime('%Y%m%d')}"
            # 查找当天最大序号
            last_cnt = InventoryCount.query.filter(
                InventoryCount.count_number.like(f"{prefix}%")
            ).order_by(InventoryCount.count_number.desc()).first()
            
            if last_cnt:
                last_seq = int(last_cnt.count_number[-4:])
                new_seq = last_seq + 1
            else:
                new_seq = 1
            
            self.count_number = f"{prefix}{new_seq:04d}"
    
    @property
    def total_items(self):
        """总盘点项目数"""
        return self.items.count()
    
    @property
    def completed_items(self):
        """已完成盘点项目数"""
        return self.items.filter(InventoryCountItem.actual_quantity.isnot(None)).count()
    
    @property
    def progress_percentage(self):
        """盘点进度百分比"""
        total = self.total_items
        if total == 0:
            return 0
        return round((self.completed_items / total) * 100, 2)
    
    @property
    def variance_items(self):
        """有差异的项目数"""
        return self.items.filter(
            InventoryCountItem.actual_quantity.isnot(None),
            InventoryCountItem.system_quantity != InventoryCountItem.actual_quantity
        ).count()
    
    @property
    def can_start(self):
        """是否可以开始盘点"""
        return self.status == 'planning'
    
    @property
    def can_complete(self):
        """是否可以完成盘点"""
        return self.status == 'counting' and self.completed_items == self.total_items
    
    @property
    def count_team_members(self):
        """获取盘点小组成员"""
        if self.count_team:
            user_ids = self.count_team
            return User.query.filter(User.id.in_(user_ids)).all()
        return []
    
    def __repr__(self):
        return f'<InventoryCount {self.count_number}>'

class InventoryCountItem(db.Model):
    """库存盘点明细"""
    __tablename__ = 'inventory_count_items'
    
    id = db.Column(db.Integer, primary_key=True)
    global_sn = db.Column(db.String(8), unique=True, nullable=False)  # 全局流水号
    count_id = db.Column(db.Integer, db.ForeignKey('inventory_counts.id', ondelete='CASCADE'), nullable=False)
    material_type = db.Column(db.String(20), nullable=False)  # raw: 原材料, consumable: 易耗品, finished: 成品
    material_id = db.Column(db.Integer, nullable=False)  # 物料ID
    system_quantity = db.Column(db.Float, nullable=False)  # 系统数量
    actual_quantity = db.Column(db.Float)  # 实际数量（盘点结果）
    variance_quantity = db.Column(db.Float)  # 差异数量（实际-系统）
    variance_reason = db.Column(db.String(200))  # 差异原因
    counted_by = db.Column(db.Integer, db.ForeignKey('user.id'))  # 盘点人
    counted_at = db.Column(db.DateTime)  # 盘点时间
    verified_by = db.Column(db.Integer, db.ForeignKey('user.id'))  # 复核人
    verified_at = db.Column(db.DateTime)  # 复核时间
    adjustment_applied = db.Column(db.Boolean, default=False)  # 是否已应用调整
    notes = db.Column(db.Text)  # 备注
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('global_sn', name='uq_inventory_count_item_global_sn'),
        db.Index('ix_inventory_count_item_material', 'material_type', 'material_id'),
        db.Index('ix_inventory_count_item_variance', 'variance_quantity'),
    )
    
    # 关系
    counter = db.relationship('User', foreign_keys=[counted_by], backref=db.backref('counted_items', lazy='dynamic'))
    verifier = db.relationship('User', foreign_keys=[verified_by], backref=db.backref('verified_items', lazy='dynamic'))
    
    def __init__(self, **kwargs):
        super(InventoryCountItem, self).__init__(**kwargs)
        if not self.global_sn:
            self.global_sn = SerialNumber.get_next_number()
    
    @property
    def material_info(self):
        """获取物料信息"""
        if self.material_type == 'raw':
            return RawMaterial.query.get(self.material_id)
        elif self.material_type == 'consumable':
            return Consumable.query.get(self.material_id)
        elif self.material_type == 'finished':
            return FinishedProduct.query.get(self.material_id)
        return None
    
    @property
    def material_name(self):
        """获取物料名称"""
        material = self.material_info
        if material:
            if self.material_type == 'raw':
                return material.material_name
            elif self.material_type == 'consumable':
                return material.consumable_name
            elif self.material_type == 'finished':
                return f"{material.product_number} - {material.model}"
        return "未知物料"
    
    @property
    def has_variance(self):
        """是否有差异"""
        if self.actual_quantity is None:
            return False
        return abs(self.variance_quantity or 0) > 0.001  # 考虑浮点数精度
    
    @property
    def variance_percentage(self):
        """差异百分比"""
        if self.system_quantity == 0:
            return 0 if self.actual_quantity == 0 else 100
        return round((self.variance_quantity / self.system_quantity) * 100, 2) if self.variance_quantity else 0
    
    def calculate_variance(self):
        """计算差异"""
        if self.actual_quantity is not None:
            self.variance_quantity = self.actual_quantity - self.system_quantity
    
    def __repr__(self):
        return f'<InventoryCountItem {self.material_name}: {self.system_quantity} -> {self.actual_quantity}>'

class ProcessAssignmentRule(db.Model):
    """工序分配规则：定义某个工序的分配策略与成员"""
    __tablename__ = 'process_assignment_rules'

    id = db.Column(db.Integer, primary_key=True)
    global_sn = db.Column(db.String(8), unique=True, nullable=False)
    process_id = db.Column(db.Integer, db.ForeignKey('process_price.id', ondelete='CASCADE'), nullable=False, index=True)
    strategy = db.Column(db.String(20), nullable=False, default='round_robin')  # round_robin / weighted / fixed
    is_active = db.Column(db.Boolean, default=True)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('global_sn', name='uq_process_assign_rule_global_sn'),
        db.UniqueConstraint('process_id', name='uq_process_assign_rule_process'),
    )

    process = db.relationship('ProcessPrice', backref=db.backref('assignment_rule', uselist=False))

    def __init__(self, **kwargs):
        super(ProcessAssignmentRule, self).__init__(**kwargs)
        if not self.global_sn:
            self.global_sn = SerialNumber.get_next_number()

class ProcessAssignmentMember(db.Model):
    """工序分配成员：某个工序下的默认员工与权重/顺序"""
    __tablename__ = 'process_assignment_members'

    id = db.Column(db.Integer, primary_key=True)
    global_sn = db.Column(db.String(8), unique=True, nullable=False)
    rule_id = db.Column(db.Integer, db.ForeignKey('process_assignment_rules.id', ondelete='CASCADE'), nullable=False, index=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id', ondelete='CASCADE'), nullable=False, index=True)
    weight = db.Column(db.Integer, default=1)  # 权重（weighted策略使用）
    sequence = db.Column(db.Integer, default=0)  # 顺序（round_robin/fixed 使用）
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('global_sn', name='uq_process_assign_member_global_sn'),
        db.UniqueConstraint('rule_id', 'employee_id', name='uq_process_assign_member_unique'),
    )

    rule = db.relationship('ProcessAssignmentRule', backref=db.backref('members', lazy='dynamic', cascade='all, delete-orphan'))
    employee = db.relationship('Employee', backref=db.backref('process_assignments', lazy='dynamic'))

    def __init__(self, **kwargs):
        super(ProcessAssignmentMember, self).__init__(**kwargs)
        if not self.global_sn:
            self.global_sn = SerialNumber.get_next_number()