"""功能专项测试：系统配置、Excel 导出/模板、JSON API 契约、任务写操作、启动自愈幂等。"""
import json
import os
import shutil
import sys
import tempfile

from _test_bootstrap import make_app, ensure_role_users, login_as, seed_fixtures, ROOT

PASS, FAIL = [], []


def check(name, ok, detail=''):
    (PASS if ok else FAIL).append((name, detail))
    print(f'  {"PASS" if ok else "FAIL"}  {name}' + (f'  -- {detail}' if detail else ''))


# ---------------------------------------------------------------- 系统配置
def test_system_config(app, client_admin, client_user):
    print('\n== SystemConfig ==')
    from app import db
    from app.models import SystemConfig, AuditLog

    with app.app_context():
        SystemConfig.invalidate_cache()
        check('bool 解析', SystemConfig.get('purchase.full_workflow_enabled') is False,
              repr(SystemConfig.get('purchase.full_workflow_enabled')))
        roles = SystemConfig.get('quality.concession_approver_roles')
        check('json 解析', roles == ['admin', 'manager'], repr(roles))
        check('未知 key 返回默认值', SystemConfig.get('__no_such_key__', 'D') == 'D')

        check('seed_defaults 幂等', SystemConfig.seed_defaults() == 0)

        before = AuditLog.query.count()
        changed = SystemConfig.set('purchase.full_workflow_enabled', True, user_id=1)
        db.session.commit()
        check('set 返回值变化标记', changed is True, repr(changed))
        SystemConfig.invalidate_cache()
        check('set 后读到新值', SystemConfig.get('purchase.full_workflow_enabled') is True)
        check('set 写审计日志', AuditLog.query.count() == before + 1,
              f'{before} -> {AuditLog.query.count()}')

        again = SystemConfig.set('purchase.full_workflow_enabled', True, user_id=1)
        db.session.commit()
        check('同值再写不算变化', again is False)

        # 缓存失效：不手动 invalidate 时能否读到新值
        SystemConfig.get('purchase.settlement_enabled')  # 预热缓存
        SystemConfig.set('purchase.settlement_enabled', True, user_id=1)
        db.session.commit()
        v = SystemConfig.get('purchase.settlement_enabled')
        check('set 自动失效缓存', v is True, f'读到 {v!r}（False 说明 set 没有清缓存）')

        # 还原
        SystemConfig.set('purchase.full_workflow_enabled', False, user_id=1)
        SystemConfig.set('purchase.settlement_enabled', False, user_id=1)
        db.session.commit()
        SystemConfig.invalidate_cache()

    r = client_admin.get('/system_configs')
    check('配置页 admin 可访问', r.status_code == 200, str(r.status_code))
    r = client_user.get('/system_configs', follow_redirects=True)
    check('配置页 user 被拒', '权限不足' in r.get_data(as_text=True))

    # 只提交一个 bool 字段，检查其余 bool 是否被连带重置
    r = client_admin.post('/system_configs',
                          data={'cfg__purchase.full_workflow_enabled': 'on'},
                          follow_redirects=True)
    with app.app_context():
        SystemConfig.invalidate_cache()
        insp = SystemConfig.get('purchase.incoming_inspection_required')
        check('部分提交不误改其他开关', insp is True,
              f'incoming_inspection_required 变成 {insp!r}（默认 true，被复选框缺省逻辑重置）')

    # 反向：整页提交时，声明了 key 但没勾选的开关必须真的被关掉
    r = client_admin.post('/system_configs',
                          data={'cfg_present': ['purchase.incoming_inspection_required',
                                                'purchase.full_workflow_enabled'],
                                'cfg__purchase.full_workflow_enabled': 'on'},
                          follow_redirects=True)
    with app.app_context():
        SystemConfig.invalidate_cache()
        insp = SystemConfig.get('purchase.incoming_inspection_required')
        full = SystemConfig.get('purchase.full_workflow_enabled')
        check('整页提交可关闭开关', insp is False, f'incoming_inspection_required={insp!r}')
        check('整页提交可开启开关', full is True, f'full_workflow_enabled={full!r}')

        SystemConfig.set('purchase.full_workflow_enabled', False, user_id=1)
        SystemConfig.set('purchase.incoming_inspection_required', True, user_id=1)
        from app import db as _db
        _db.session.commit()
        SystemConfig.invalidate_cache()


# ------------------------------------------------------- Excel 模板与导出
# (url, 期望)  file=直接下载xlsx  form=返回导出表单页
DOWNLOADS = [
    ('/employees/template', 'file'), ('/process_prices/template', 'file'),
    ('/production_records/template', 'file'), ('/bonus_penalties/template', 'file'),
    ('/tasks/template', 'file'), ('/products/template', 'file'), ('/inventory/template', 'file'),
    # 列表页上的「导出」按钮是 <a href> 直连，GET 直接给文件
    ('/export_tasks', 'file'),
    # 这几个 GET 先给导出条件表单页，填完再 POST 下载
    ('/employees/export', 'form'), ('/process_prices/export', 'form'),
    ('/production_records/export', 'form'), ('/bonus_penalties/export', 'form'),
]


def test_downloads(client_admin):
    print('\n== Excel 模板 / 导出（GET） ==')
    for url, expect in DOWNLOADS:
        r = client_admin.get(url, follow_redirects=False)
        ct = r.headers.get('Content-Type', '')
        size = len(r.get_data())
        got = 'file' if 'spreadsheet' in ct else ('form' if r.status_code == 200 else 'redirect')
        detail = f'HTTP {r.status_code} {ct[:45]} {size}B'
        if r.status_code == 302:
            with client_admin.session_transaction() as s:
                fl = s.get('_flashes')
                if fl:
                    detail += f' flash={fl[-1][1][:80]}'
                s.pop('_flashes', None)
        check(f'{url} 期望{expect}', got == expect, detail)


# 表单页填完提交后必须真的吐出 xlsx（历史上这条路径因 try 缩进错位一直静默失败）
POST_EXPORTS = [
    ('/employees/export', {'department': '', 'position': ''}),
    ('/process_prices/export', {'component': '', 'model_no': ''}),
]


def test_post_exports(client_admin):
    print('\n== 导出表单 POST ==')
    for url, payload in POST_EXPORTS:
        r = client_admin.post(url, data=payload, follow_redirects=False)
        ct = r.headers.get('Content-Type', '')
        detail = f'HTTP {r.status_code} {ct[:45]} {len(r.get_data())}B'
        if r.status_code == 302:
            with client_admin.session_transaction() as s:
                fl = s.get('_flashes')
                if fl:
                    detail += f' flash={fl[-1][1][:80]}'
                s.pop('_flashes', None)
        check(f'POST {url} 下载 xlsx', 'spreadsheet' in ct, detail)


# ------------------------------------------------------------ JSON 契约
JSON_APIS = [
    '/api/inventory/raw-materials', '/api/inventory/finished-products',
    '/api/inventory/consumables',
    '/api/consumable-categories', '/api/raw-material-categories',
    '/api/customers/search?q=a', '/api/materials/search?q=a',
    '/api/products/search?q=a', '/api/sales_orders/search?q=a',
    '/api/notifications/recent', '/api/notifications/stats',
    '/api/quality/tasks', '/api/quality/templates', '/api/quality/records',
    '/api/quality/inspectors', '/api/quality/processes', '/api/quality/finished-products',
    '/api/quality/production-records', '/api/process_assignment',
    '/api/chart-data/production', '/api/chart-data/salary',
    '/api/chart-data/task', '/api/chart-data/department',
    '/api/products/names', '/api/search/suggestions?q=a',
]


def test_json_apis(client_admin):
    print('\n== JSON API 契约 ==')
    for url in JSON_APIS:
        r = client_admin.get(url)
        ct = r.headers.get('Content-Type', '')
        if 'application/json' not in ct:
            check(f'{url} 返回 JSON', False, f'HTTP {r.status_code}, Content-Type={ct}')
            continue
        try:
            body = r.get_json()
        except Exception as e:
            check(f'{url} 返回 JSON', False, str(e))
            continue
        ok = isinstance(body, (dict, list))
        shape = 'list' if isinstance(body, list) else ','.join(sorted(body.keys()))[:70]
        check(f'{url} 返回 JSON', ok and r.status_code == 200, f'HTTP {r.status_code} keys={shape}')


def test_json_unauth(app):
    print('\n== 未登录访问 JSON API 的返回形式 ==')
    c = app.test_client()
    for url in ['/api/inventory/raw-materials', '/api/quality/tasks', '/api/notifications/stats']:
        r = c.get(url, follow_redirects=False)
        ct = r.headers.get('Content-Type', '')
        check(f'{url} 未登录返回', r.status_code in (401, 403) or 'json' in ct,
              f'HTTP {r.status_code} Content-Type={ct} -> {r.headers.get("Location", "")}')


def test_missing_resource_404(client_admin):
    """get_or_404 被 except Exception 吞掉时会变成 500 或带错误文案的 200。"""
    print('\n== 不存在的资源应返回 404 ==')
    for url in (
        '/tasks/999999/get',
        '/process_prices/999999',
        '/inventory/raw/999999',
        '/products/999999',
        '/api/sales_orders/999999/customer_addresses',
    ):
        r = client_admin.get(url)
        check(f'{url} 不存在时 404', r.status_code == 404, f'HTTP {r.status_code}')


# ------------------------------------------------------------ 任务写操作
def test_task_write(app, client_admin, client_user):
    print('\n== 任务写操作 ==')
    from app.models import Employee, ProcessPrice, TaskAssignment

    with app.app_context():
        emp = Employee.query.first()
        pp = ProcessPrice.query.first()
        emp_id, pp_id = emp.id, pp.id

    payload = {'employee_id': emp_id, 'process_id': pp_id, 'quantity': 3,
               'target_date': '2026-12-31', 'notes': '_功能测试'}

    r = client_user.post('/tasks/add', json=payload)
    check('user 新增任务被拒 403', r.status_code == 403, str(r.status_code))

    r = client_admin.post('/tasks/add', json=payload)
    body = r.get_json() if 'json' in r.headers.get('Content-Type', '') else None
    check('admin 新增任务成功', r.status_code == 200 and body and body.get('success'),
          f'HTTP {r.status_code} {body}')

    with app.app_context():
        task = TaskAssignment.query.filter_by(notes='_功能测试').first()
        tid = task.id if task else None
    if not tid:
        check('取回新建任务', False, '库里查不到')
        return

    # 报工归属：任务挂在 emp_id 名下，_t_user 未关联该员工
    r = client_user.post(f'/tasks/{tid}/update_status',
                         json={'completed_quantity': 1, 'materials': []})
    check('user 改他人任务被拒 403', r.status_code == 403, f'HTTP {r.status_code} {r.get_json()}')

    from app import db
    from app.models import User
    with app.app_context():
        emp_row = Employee.query.get(emp_id)
        prev_user_id = emp_row.user_id
        emp_row.user_id = User.query.filter_by(username='_t_user').first().id
        db.session.commit()

    r = client_user.post(f'/tasks/{tid}/update_status',
                         json={'completed_quantity': 1, 'materials': []})
    b = r.get_json()
    check('user 改本人任务放行', r.status_code == 200 and b and b.get('success'),
          f'HTTP {r.status_code} {b}')

    with app.app_context():
        emp_row = Employee.query.get(emp_id)
        emp_row.user_id = prev_user_id
        db.session.commit()

    r = client_admin.post(f'/tasks/{tid}/update_status',
                          json={'completed_quantity': 1, 'materials': []})
    b = r.get_json()
    check('更新任务状态', r.status_code == 200 and b and b.get('success'), f'HTTP {r.status_code} {b}')

    r = client_admin.post(f'/tasks/{tid}/update_status',
                          json={'completed_quantity': 999, 'materials': []})
    check('超量提交被拒 400', r.status_code == 400, f'HTTP {r.status_code} {r.get_json()}')

    r = client_admin.post(f'/tasks/{tid}/update_status',
                          json={'completed_quantity': -1, 'materials': []})
    check('负数被拒 400', r.status_code == 400, f'HTTP {r.status_code}')

    # 完成后 completed_at 是否回填（批次1 新增字段）
    r = client_admin.post(f'/tasks/{tid}/update_status',
                          json={'completed_quantity': 3, 'materials': []})
    with app.app_context():
        t = TaskAssignment.query.get(tid)
        check('完工后 status=completed', t.status == 'completed', repr(t.status))
        check('完工后 completed_at 回填', t.completed_at is not None, repr(t.completed_at))

    r = client_user.delete(f'/tasks/{tid}')
    check('user 删除任务被拒 403', r.status_code == 403, str(r.status_code))
    r = client_admin.delete(f'/tasks/{tid}')
    check('admin 删除任务成功', r.status_code == 200 and r.get_json().get('success'),
          str(r.status_code))


# ------------------------------------------------------ 仓库闭合 / 无工序禁下单
def test_no_process_blocks_order(app, client_admin):
    print('\n== 无工艺路线禁止下生产单 ==')
    from app import db
    from app.models import Product, User

    with app.app_context():
        admin = User.query.filter_by(username='_t_admin').first()
        p = Product.query.filter_by(product_code='_NOROUTE_WH').first()
        if not p:
            p = Product(product_code='_NOROUTE_WH', product_name='无工艺测试品',
                        created_by=admin.id if admin else 1, status='active')
            db.session.add(p)
            db.session.commit()
        pid = p.id
        n_proc = p.process_items.count()

    check('测试产品无工序', n_proc == 0, f'process_items={n_proc}')
    r = client_admin.post('/production_orders/add', json={
        'product_id': pid,
        'planned_quantity': 1,
        'planned_start_date': '2026-09-01',
        'planned_end_date': '2026-09-30',
    })
    body = r.get_json() if r.is_json else None
    check('无工序下单失败', r.status_code == 400 and body and body.get('success') is False,
          f'HTTP {r.status_code} {body}')
    if body:
        check('失败原因含工艺路线', '工艺路线' in (body.get('message') or ''), body.get('message'))


def test_requisition_issue_deducts(app, client_admin):
    print('\n== 领用选真实库存并行发料扣账 ==')
    from app import db
    from app.models import Consumable, Employee, MaterialRequisition

    with app.app_context():
        emp = Employee.query.filter_by(is_active=True).first()
        mat = Consumable.query.filter(Consumable.quantity > 0, Consumable.status == 'in_stock').first()
        if mat is None:
            mat = Consumable.query.filter_by(is_archived=False).first()
            if mat:
                mat.quantity = 10
                mat.status = 'in_stock'
                db.session.commit()
        if not emp or not mat:
            check('有员工和易耗品样本', False, f'emp={emp} mat={mat}')
            return
        emp_id, mat_id, before = emp.id, mat.id, mat.quantity

    r = client_admin.post('/material_requisitions/add', data={
        'employee_id': emp_id,
        'purpose': '_功能测试领用',
        'requisition_date': '2026-08-26',
        'production_order_id': 0,
        'materials_data': json.dumps([{
            'material_type': 'consumable',
            'material_id': mat_id,
            'quantity': 2,
            'unit': '个',
            'notes': '_ft',
        }]),
        'submit': '保存记录',
    }, follow_redirects=False)
    check('创建领用单 302', r.status_code in (302, 200), f'HTTP {r.status_code} {r.get_data(as_text=True)[:180]}')

    with app.app_context():
        req = MaterialRequisition.query.filter_by(purpose='_功能测试领用').order_by(
            MaterialRequisition.id.desc()).first()
        if not req:
            check('取回新建领用单', False, '库里查不到')
            return
        rid, status = req.id, req.status
        item = req.items.first()
        mid_ok = item and item.material_id == mat_id

    check('领用明细写入真实 material_id', mid_ok, f'item.material_id={getattr(item, "material_id", None)}')
    check('免审批易耗品直接 approved', status == 'approved', f'status={status}')

    r = client_admin.post(f'/material_requisitions/{rid}/issue', json={})
    body = r.get_json() if r.is_json else None
    check('发料成功', r.status_code == 200 and body and body.get('success'), f'HTTP {r.status_code} {body}')

    with app.app_context():
        after = Consumable.query.get(mat_id).quantity
        req = MaterialRequisition.query.get(rid)
        check('发料后库存减少 2', after == before - 2, f'{before} -> {after}')
        check('领用单 completed', req.status == 'completed', repr(req.status))


def test_inventory_count_adjusts(app, client_admin):
    print('\n== 盘点完成调账 ==')
    from datetime import date
    from app import db
    from app.models import Consumable, InventoryCount, User

    with app.app_context():
        admin = User.query.filter_by(username='_t_admin').first()
        mat = Consumable.query.filter_by(is_archived=False, status='in_stock').first()
        if mat is None:
            check('有在库易耗品可盘', False)
            return
        mat_id, before = mat.id, mat.quantity or 0
        uid = admin.id

    r = client_admin.post('/inventory_counts/add', data={
        'count_name': '_功能测试盘点',
        'count_type': 'full',
        'count_scope': 'consumable',
        'planned_date': date.today().isoformat(),
        'count_team': uid,
        'submit': '创建盘点',
    }, follow_redirects=False)
    check('创建盘点 302', r.status_code in (302, 200), f'HTTP {r.status_code} {r.get_data(as_text=True)[:180]}')

    with app.app_context():
        count = InventoryCount.query.filter_by(count_name='_功能测试盘点').order_by(
            InventoryCount.id.desc()).first()
        if not count:
            check('取回盘点单', False)
            return
        cid = count.id
        n_items = count.total_items
        snapshot = []
        target = None
        for it in count.items.all():
            snapshot.append({'id': it.id, 'material_id': it.material_id,
                             'system_quantity': it.system_quantity or 0})
            if it.material_type == 'consumable' and it.material_id == mat_id:
                target = it
        if target is None and snapshot:
            target = count.items.first()
            mat_id = target.material_id
            before = target.system_quantity or 0
        item_id = target.id if target else None

    check('盘点快照有行', n_items > 0 and item_id, f'items={n_items} item_id={item_id}')
    if not item_id:
        return

    r = client_admin.post(f'/inventory_counts/{cid}/start', json={})
    check('开始盘点', r.status_code == 200 and (r.get_json() or {}).get('success'),
          f'HTTP {r.status_code} {r.get_json()}')

    actual = (before or 0) + 3
    payload_items = []
    for row in snapshot:
        payload_items.append({
            'id': row['id'],
            'actual_quantity': actual if row['id'] == item_id else row['system_quantity'],
            'variance_reason': '_ft' if row['id'] == item_id else '',
        })
    r = client_admin.post(f'/inventory_counts/{cid}/record', json={'items': payload_items})
    check('录入实盘', r.status_code == 200 and (r.get_json() or {}).get('success'),
          f'HTTP {r.status_code} {r.get_json()}')

    r = client_admin.post(f'/inventory_counts/{cid}/complete', json={})
    check('完成调账', r.status_code == 200 and (r.get_json() or {}).get('success'),
          f'HTTP {r.status_code} {r.get_json()}')

    with app.app_context():
        after = Consumable.query.get(mat_id).quantity
        count = InventoryCount.query.get(cid)
        item = count.items.filter_by(id=item_id).first()
        check('库存已写成实盘数', after == actual, f'{before} -> {after} (期望 {actual})')
        check('adjustment_applied', bool(item.adjustment_applied), repr(item.adjustment_applied))
        check('盘点 completed', count.status == 'completed', repr(count.status))


# ------------------------------------------------------ 启动自愈幂等
CHILD_SCRIPT = r'''
import os, sys, json, sqlite3
sys.path.insert(0, sys.argv[1])
dst = sys.argv[2]
os.environ['DATABASE_URL'] = 'sqlite:///' + dst.replace('\\', '/')

# 模拟老库：先把批次1 新增的表与列删掉，再看启动能不能自愈
con = sqlite3.connect(dst)
con.execute('DROP TABLE IF EXISTS system_configs')
cols = [r[1] for r in con.execute('PRAGMA table_info(task_assignment)')]
if 'completed_at' in cols:
    keep = [c for c in cols if c != 'completed_at']
    con.execute('CREATE TABLE _ta_bak AS SELECT %s FROM task_assignment' % ','.join(keep))
con.commit(); con.close()

from app import create_app
from app.models import SystemConfig

out = {'runs': []}
for i in (1, 2):
    try:
        a = create_app()
        with a.app_context():
            out['runs'].append({'n_configs': SystemConfig.query.count()})
    except Exception as e:
        out['runs'].append({'error': f'{e.__class__.__name__}: {e}'})

con = sqlite3.connect(dst)
out['tables'] = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
out['ta_cols'] = [r[1] for r in con.execute('PRAGMA table_info(task_assignment)')]
out['soi_cols'] = [r[1] for r in con.execute('PRAGMA table_info(sales_order_items)')]
con.close()
print('__RESULT__' + json.dumps(out))
'''


def test_ensure_schema_idempotent():
    print('\n== _ensure_schema / seed 幂等（子进程内连续两次 create_app） ==')
    import subprocess

    tmp = tempfile.mkdtemp(prefix='wms_schema_')
    dst = os.path.join(tmp, 'app.db')
    shutil.copy2(ROOT / 'app.db', dst)
    script = os.path.join(tmp, 'child.py')
    with open(script, 'w', encoding='utf-8') as f:
        f.write(CHILD_SCRIPT)

    proc = subprocess.run([sys.executable, '-B', script, str(ROOT), dst],
                          capture_output=True, text=True, encoding='utf-8', errors='replace')
    marker = [l for l in (proc.stdout or '').splitlines() if l.startswith('__RESULT__')]
    if not marker:
        check('子进程启动测试', False, (proc.stderr or proc.stdout)[-300:])
        return
    out = json.loads(marker[0][len('__RESULT__'):])

    errs = [r for r in out['runs'] if 'error' in r]
    check('连续两次启动无异常', not errs, str(errs))
    check('两次启动配置项数一致', len({r.get('n_configs') for r in out['runs']}) == 1, str(out['runs']))
    check('system_configs 表被自动创建', 'system_configs' in out['tables'])
    check('task_assignment.completed_at 自动补齐', 'completed_at' in out['ta_cols'])
    check('sales_order_items 扩展列齐全',
          {'spec_splice_hole', 'using_unit', 'anti_corrosion'} <= set(out['soi_cols']))


# ---------------------------------------------------------------- 全局搜索
# 角色 -> 快速搜索应返回的实体类型（与 permissions.SEARCH_TYPE_CAPABILITIES 对应）
SEARCH_VISIBILITY = {
    'admin': {'employees', 'process_prices', 'production_records', 'products',
              'inventory', 'customers', 'sales_orders', 'production_orders'},
    'hr': {'employees', 'process_prices', 'production_records'},
    'manager': {'process_prices', 'production_records', 'products', 'inventory',
                'customers', 'sales_orders', 'production_orders'},
    'sales': {'customers', 'sales_orders'},
    'accountant': set(),
    'inspector': set(),
    'user': set(),
}


def test_search(app, users, pw, client_admin):
    print('\n== 全局搜索 ==')
    from app.models import Employee

    with app.app_context():
        emp = Employee.query.first()
        emp_name, emp_no = emp.name, emp.employee_id

    # search_type=all 会走到库存分支，那里曾对 property 字段用 .like() 直接 500
    r = client_admin.get(f'/search?query={emp_name}&search_type=all')
    check('admin 全局搜索 200', r.status_code == 200, f'HTTP {r.status_code}')
    check('admin 搜到员工', emp_no in r.get_data(as_text=True), f'页面里找不到 {emp_no}')

    for role, expected in SEARCH_VISIBILITY.items():
        c = app.test_client()
        login_as(c, users[role], pw)
        r = c.post('/search/quick', json={'query': 'a', 'search_type': 'all'})
        if r.status_code == 403:
            got = set()
        elif r.status_code == 200:
            got = set((r.get_json() or {}).get('results', {}).keys())
        else:
            got = {f'HTTP{r.status_code}'}
        check(f'{role} 搜索实体范围', got == expected,
              f'期望 {sorted(expected)}，实到 {sorted(got)}')

    # RawMaterial.material_name 是取 category.name 的 property。三个入口都曾直接把它
    # 拼进 SQL：库存页当场 500，生产记录页被 except 吞掉、按原材料搜从来搜不到。
    from app.models import RawMaterial, RawMaterialCategory
    with app.app_context():
        cat = RawMaterialCategory.query.join(
            RawMaterial, RawMaterial.category_id == RawMaterialCategory.id
        ).first()
        cat_name = cat.name
        sample_no = RawMaterial.query.filter_by(category_id=cat.id).first().internal_number

    r = client_admin.get(f'/inventory?type=raw&search={cat_name}')
    check('库存页按品类名搜原材料 200', r.status_code == 200, f'HTTP {r.status_code}')
    check('库存页搜到该品类下的原材料', sample_no in r.get_data(as_text=True),
          f'页面里找不到 {sample_no}')

    r = client_admin.get(f'/production_records?search={cat_name}')
    check('生产记录页按品类名搜 200', r.status_code == 200, f'HTTP {r.status_code}')

    r = client_admin.get(f'/search?query={cat_name}&search_type=inventory')
    check('全局搜索按品类名搜库存 200', r.status_code == 200, f'HTTP {r.status_code}')
    check('全局搜索命中该品类', cat_name in r.get_data(as_text=True), '结果里没有品类名')

    # 建议接口同样按能力过滤，否则姓名直接从这里漏出去
    c = app.test_client()
    login_as(c, users['user'], pw)
    r = c.get(f'/api/search/suggestions?q={emp_name[:2]}')
    sug = (r.get_json() or {}).get('suggestions', {}) if r.status_code == 200 else {}
    check('user 拿不到员工姓名建议', not sug.get('employee_names'),
          f'HTTP {r.status_code} {sug}')


def run():
    app, _ = make_app()
    users, pw = ensure_role_users(app)
    seed_fixtures(app)

    ca = app.test_client()
    login_as(ca, users['admin'], pw)
    cu = app.test_client()
    login_as(cu, users['user'], pw)

    test_system_config(app, ca, cu)
    test_downloads(ca)
    test_post_exports(ca)
    test_json_apis(ca)
    test_json_unauth(app)
    test_missing_resource_404(ca)
    test_search(app, users, pw, ca)
    test_task_write(app, ca, cu)
    test_no_process_blocks_order(app, ca)
    test_requisition_issue_deducts(app, ca)
    test_inventory_count_adjusts(app, ca)
    test_ensure_schema_idempotent()

    print(f'\n================ 结果：{len(PASS)} 通过 / {len(FAIL)} 失败 ================')
    for name, detail in FAIL:
        print(f'  FAIL  {name}  {detail}')
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(run())
