"""t4 缺陷最小复现：① /tasks/<id>/edit 的 notes 不落库 ② /consumables/<id>/use 恒 500。

独立于 write_suite：自己建副本、自己建前置、只做最小请求，输出可单条复核的证据。
"""
import json
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _env  # noqa: E402

sys.path.insert(0, _env.HARNESS_DIR)
sys.path.insert(0, _env.SCRIPTS_DIR)
if _env.REPO_ROOT not in sys.path:
    sys.path.insert(0, _env.REPO_ROOT)

import fixtures  # noqa: E402
import _test_bootstrap  # noqa: E402

TAG = 't4repro'
out = {'real_db_sha256_before': _env.sha256_file(_env.REAL_DB), 'cases': {}}

app, copy_path = fixtures.make_isolated_app('repro')
app.config['PROPAGATE_EXCEPTIONS'] = False   # 与写矩阵一致：异常按 500 响应取证，不让测试客户端抛出
from app import db  # noqa: E402
from app import models as M  # noqa: E402
from datetime import date  # noqa: E402

users, pw = _test_bootstrap.ensure_role_users(app)
_test_bootstrap.seed_fixtures(app)
client = app.test_client()
_test_bootstrap.login_as(client, users['admin'], pw)
print('copy:', copy_path)
print('iso samefile(real)=', os.path.samefile(copy_path, _env.REAL_DB))

# ---------------------------------------------------------------- ① edit 的 notes
with app.app_context():
    emp = M.Employee.query.first()
    proc = M.ProcessPrice.query.first()
    t = M.TaskAssignment(global_sn=M.SerialNumber.get_next_number(), employee_id=emp.id,
                         process_id=proc.id, quantity=5, status='pending',
                         assigned_date=date.today(), target_date=date(2026, 12, 31),
                         notes='OLD_NOTES')
    db.session.add(t)
    db.session.commit()
    tid, emp_id, proc_id = t.id, emp.id, proc.id
print(f'\n[①] 建任务 id={tid} notes=OLD_NOTES')
r = client.post(f'/tasks/{tid}/edit', json={'employee_id': emp_id, 'process_id': proc_id,
                                            'quantity': 8, 'target_date': '2026-11-30',
                                            'status': 'completed', 'notes': 'NEW_NOTES'})
print('[①] POST /tasks/%d/edit -> HTTP %s' % (tid, r.status_code))
print('[①] 响应:', r.get_data(as_text=True)[:300])
with app.app_context():
    db.session.expire_all()
    row = M.TaskAssignment.query.get(tid)
    print(f'[①] 库内 quantity={row.quantity} status={row.status} '
          f'target_date={row.target_date} notes={row.notes!r}')
    # 原始 SQL 再确认一次（绕开 ORM 缓存）
    raw = db.session.execute(db.text(
        'SELECT quantity, status, notes FROM task_assignment WHERE id=:i'), {'i': tid}).fetchone()
    print(f'[①] 原始 SQL: quantity={raw[0]} status={raw[1]} notes={raw[2]!r}')
    audit = M.AuditLog.query.filter_by(target_model='TaskAssignment', target_id=tid)\
        .order_by(M.AuditLog.id.desc()).first()
    audit_new = json.loads(json.dumps(audit.new_data)) if audit else None
    audit_old = json.loads(json.dumps(audit.old_data)) if audit else None
    print(f'[①] 审计 new_data.notes={audit_new.get("notes")!r} '
          f'old_data.notes={audit_old.get("notes")!r}')
    db_notes_after_edit = row.notes
    db_qty_after_edit = row.quantity
    # 直接按源码口径赋值一次，验证 ORM 本身可写
    row.notes = 'DIRECT_SET'
    db.session.commit()
    db.session.expire_all()
    print('[①] 直接 row.notes=DIRECT_SET 后再读:', M.TaskAssignment.query.get(tid).notes)
out['cases']['edit_notes'] = {
    'task_id': tid, 'http': r.status_code,
    'db_notes_after_edit': db_notes_after_edit, 'db_quantity_after_edit': db_qty_after_edit,
    'audit_new_data': audit_new, 'audit_old_data': audit_old,
    'source_evidence': 'app/main/routes.py:4502-4506 只赋值 target_date/employee_id/'
                       'process_id/quantity；**没有任何 task.notes 赋值**，'
                       '而 :4497/:4532 把 task.notes 当作已更新值写入审计',
}

# ---------------------------------------------------------------- ② consumable/use
with app.app_context():
    cc = M.ConsumableCategory.query.first()
    if cc is None:
        cc = M.ConsumableCategory(name='_t4repro 品类', code='t4reproCC', is_active=True)
        db.session.add(cc)
        db.session.flush()
    c1 = M.Consumable(supplier='_t4repro', category_id=cc.id, supplier_number='t4reproCS1',
                      internal_number='t4reproCI1', quantity=10, unit='个', unit_price=1.0,
                      status='in_stock')
    db.session.add(c1)
    db.session.commit()
    cid, q0 = c1.id, c1.quantity
print(f'\n[②] 建易耗品 id={cid} quantity={q0}')
r2 = client.post(f'/consumables/{cid}/use', json={'usage_quantity': 3, 'used_by': '_t4'})
print('[②] POST /consumables/%d/use -> HTTP %s' % (cid, r2.status_code))
print('[②] 响应:', r2.get_data(as_text=True)[:300])
with app.app_context():
    db.session.expire_all()
    c2 = M.Consumable.query.get(cid)
    print(f'[②] 库内 quantity={c2.quantity} status={c2.status}（期望 7 / in_stock）')
out['cases']['consumable_use'] = {'consumable_id': cid, 'http': r2.status_code,
                                 'quantity_before': q0,
                                 'quantity_after': c2.quantity,
                                 'body': r2.get_data(as_text=True)[:200],
                                 'status_after': c2.status}

# ---------------------------------------------------------------- 直接调用视图函数（绕开 HTTP）
print('\n[②b] 直接调用视图函数，拿真实异常类型')
try:
    with app.test_request_context(f'/consumables/{cid}/use', method='POST',
                                 json={'usage_quantity': 1}):
        from app.main.routes import use_consumable
        use_consumable(cid)
        print('[②b] 未抛异常？')
except Exception as e:
    print(f'[②b] 抛出 {e.__class__.__name__}: {e}')
    out['cases']['consumable_use_direct'] = {'exc': e.__class__.__name__, 'msg': str(e)}

# ---------------------------------------------------------------- ③ A-3 门禁调用点（对照）
print('\n[③] 门禁调用点 mes_service.py:326 的实参（AST 取证）')
import ast  # noqa: E402
p = os.path.join(_env.REPO_ROOT, 'app', 'services', 'mes_service.py')
src = open(p, encoding='utf-8').read()
lines = src.splitlines()
for i in range(300, 335):
    if 'qc_gate_allows_output' in lines[i]:
        print(f'   mes_service.py:{i+1}: {lines[i].strip()}')
        print(f'   mes_service.py:{i+2}: {lines[i+1].strip()}')
        print(f'   mes_service.py:{i+3}: {lines[i+2].strip()}')
out['real_db_sha256_after'] = _env.sha256_file(_env.REAL_DB)
out['real_db_unchanged'] = out['real_db_sha256_after'] == _env.REAL_DB_SHA256_EXPECTED
print(f'\n[真实库] 开工={out["real_db_sha256_before"]}')
print(f'[真实库] 收尾={out["real_db_sha256_after"]} 未变={out["real_db_unchanged"]}')

EVID = os.path.join(_env.REPORTS_ROOT, 'evidence', 'api')
os.makedirs(EVID, exist_ok=True)
with open(os.path.join(EVID, 'defect_repro.json'), 'w', encoding='utf-8', newline='\n') as fh:
    json.dump(out, fh, ensure_ascii=False, indent=1)
print('-> evidence/api/defect_repro.json')
