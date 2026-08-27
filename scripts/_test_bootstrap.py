"""测试脚手架：在 app.db 的临时副本上启动应用，绝不碰真实库。

用法：
    from _test_bootstrap import make_app, login_as, ROLES
"""
import os
import pathlib
import shutil
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ROLES = ('admin', 'manager', 'hr', 'accountant', 'inspector', 'sales', 'user')

_TMPDIR = None


def make_app(fresh=False):
    """复制 app.db 到临时目录后创建应用。fresh=True 时每次调用都用新副本。"""
    global _TMPDIR
    if fresh or _TMPDIR is None:
        _TMPDIR = tempfile.mkdtemp(prefix='wms_test_')
        shutil.copy2(ROOT / 'app.db', os.path.join(_TMPDIR, 'app.db'))
    copy_path = os.path.join(_TMPDIR, 'app.db')
    os.environ['DATABASE_URL'] = 'sqlite:///' + copy_path.replace('\\', '/')

    # config.Config 在类体里读 DATABASE_URL，若它已被导入过，上面的环境变量就来不及生效，
    # 应用会连到真实库。清掉再导入，保证 URI 一定指向副本。
    for name in [m for m in list(sys.modules) if m == 'config' or m == 'app' or m.startswith('app.')]:
        del sys.modules[name]

    from app import create_app
    app = create_app()
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['TESTING'] = True

    # 最后一道闸：URI 没落在副本上就直接失败，绝不允许测试写真实库
    uri = app.config['SQLALCHEMY_DATABASE_URI']
    if os.path.normcase(copy_path) not in os.path.normcase(uri.replace('/', os.sep)):
        raise RuntimeError(
            f'测试库隔离失败：SQLALCHEMY_DATABASE_URI={uri!r}，期望指向 {copy_path!r}。'
            '请确认 make_app() 在任何 app/config 导入之前调用。'
        )
    return app, copy_path


def ensure_role_users(app, password='test_pw_123'):
    """为每个角色准备一个测试用户，返回 {role: username}。"""
    from app import db
    from app.models import User

    mapping = {}
    with app.app_context():
        for role in ROLES:
            username = f'_t_{role}'
            u = User.query.filter_by(username=username).first()
            if not u:
                u = User(username=username, role=role)
                db.session.add(u)
            u.role = role
            u.set_password(password)
            mapping[role] = username
        db.session.commit()
    return mapping, password


def seed_fixtures(app):
    """为空表补最小样本数据，让详情页路由能被覆盖到。返回 {模型名: id}。"""
    from datetime import date, datetime

    from app import db
    from app import models as M

    made = {}
    with app.app_context():
        admin = M.User.query.filter_by(role='admin').first()
        emp = M.Employee.query.first()
        cust = M.Customer.query.first()
        prod = M.Product.query.first()
        raw = M.RawMaterial.query.first()
        pp = M.ProcessPrice.query.first()
        prec = M.ProductionRecord.query.first()

        def get_or_make(model, factory):
            row = model.query.first()
            if row is None:
                row = factory()
                if row is None:
                    return None
                db.session.add(row)
                db.session.flush()
            return row

        cat = get_or_make(M.ConsumableCategory,
                          lambda: M.ConsumableCategory(name='_测试品类', code='_TC01', is_active=True))
        if cat:
            made['ConsumableCategory'] = cat.id
            c = get_or_make(M.Consumable, lambda: M.Consumable(
                supplier='_测试供应商', category_id=cat.id, supplier_number='_SUP01',
                specification='_规格', quantity=10, unit='个', unit_price=1.5))
            if c:
                made['Consumable'] = c.id

        if cust:
            addr = get_or_make(M.CustomerAddress, lambda: M.CustomerAddress(
                customer_id=cust.id, contact_person='_测试联系人', contact_phone='13800000000',
                province='江苏省', city='南京市', detailed_address='_测试路1号', is_primary=True))
            if addr:
                made['CustomerAddress'] = addr.id

        if emp:
            bp_row = get_or_make(M.BonusPenalty, lambda: M.BonusPenalty(
                employee_id=emp.id, amount=100.0, reason='_测试奖励', type='bonus',
                process_id=pp.id if pp else None))
            if bp_row:
                made['BonusPenalty'] = bp_row.id
            req = get_or_make(M.MaterialRequisition, lambda: M.MaterialRequisition(
                employee_id=emp.id, department='_测试部门', purpose='_测试用途',
                required_date=date.today(), status='pending'))
            if req:
                made['MaterialRequisition'] = req.id

        if prod and raw:
            bom = get_or_make(M.ProductBOM, lambda: M.ProductBOM(
                product_id=prod.id, material_type='raw', material_id=raw.id,
                quantity=2.0, unit='件', unit_cost=5.0))
            if bom:
                made['ProductBOM'] = bom.id

        if admin:
            tpl = get_or_make(M.InspectionTemplate, lambda: M.InspectionTemplate(
                template_code='_TPL01', name='_测试模板', type='production_record',
                is_active=True, created_by=admin.id))
            if tpl:
                made['InspectionTemplate'] = tpl.id
                target_type, target_id = ('production_record', prec.id) if prec else ('product', 1)
                task = get_or_make(M.InspectionTask, lambda: M.InspectionTask(
                    global_sn=M.SerialNumber.get_next_number(), template_id=tpl.id,
                    inspector_id=admin.id, target_type=target_type, target_id=target_id,
                    status='pending', created_by=admin.id))
                if task:
                    made['InspectionTask'] = task.id
                    rec = get_or_make(M.InspectionRecord, lambda: M.InspectionRecord(
                        global_sn=M.SerialNumber.get_next_number(), task_id=task.id,
                        template_id=tpl.id, inspector_id=admin.id,
                        inspection_date=datetime.now().date(), result='pass'))
                    if rec:
                        made['InspectionRecord'] = rec.id

        db.session.commit()
    return made


def login_as(client, username, password='test_pw_123'):
    return client.post('/auth/login',
                       data={'username': username, 'password': password},
                       follow_redirects=False)
