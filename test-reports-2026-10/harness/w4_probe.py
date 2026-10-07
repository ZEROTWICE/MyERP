"""w4_probe.py — W4/W5 修复的**修前基线**与**修后判据**执行器（t8 自证资产；t9 独立回归另行执行）。

判据来源：`test-reports-2026-10/17-W4W5修复验收判据.md`（含 §12(补记) 的 A-63/A-62 前置与两条调度约束）。
口径纪律：一切请求打到**副本**（`_test_bootstrap.make_app()`），真实库只做 SHA256 指纹（`_env`）。

场景（`--scenario`）：
  p09  P-09：哨兵 id 999999999 打 18 个谓词实例（覆盖 §2.3 的 17 处源站点）⇒ 期望 404 三件套
  p10  P-10：有关联记录拒删 400 / 无记录可删 200 / in_progress 400（原因可区分）/ 哨兵 404
  p11  P-11：5 类泄漏子串全量扫描 + 阴性注入（进程内探针端点必须让判据报红）+ 详情进日志
  p12  P-12：15 条 415 组合（表单体）⇒ 400/415、无 5xx；templates 部分更新；tasks 缺/错 type；空体不得 200 success
  p08  P-08：/tasks/<id>/edit 的 notes 必须真落库 + 审计 old != new + 未传 notes 不得清空
  p13  P-13：/api/ 面载体分档扫描 + 载体登记册逐行一致（==4 行、违规 0）
  s    S-1…S-4、S-6 回归抽样（S-5 全量矩阵属 t9）
  all  以上全部

用法（仓库根目录；A-40：复跑换 HARNESS_RUN_ID）：
    python -B test-reports-2026-10/harness/w4_probe.py --phase pre  --scenario all
    python -B test-reports-2026-10/harness/w4_probe.py --phase post --scenario all
"""
import argparse
import io
import json
import os
import re
import sys
import contextlib

HERE = os.path.dirname(os.path.abspath(__file__))
REPORTS_ROOT = os.path.dirname(HERE)
REPO_ROOT = os.path.dirname(REPORTS_ROOT)
SCRIPTS_DIR = os.path.join(REPO_ROOT, 'scripts')
sys.path.insert(0, HERE)
sys.path.insert(0, SCRIPTS_DIR)

from _env import RUN_ID, real_db_status, save_evidence  # noqa: E402

SENTINEL = 999999999
LEAK_RX = re.compile(r'sqlite3\.|\[SQL:|\[parameters:|IntegrityError|OperationalError|'
                     r'DatabaseError|Traceback', re.I)
SCENARIOS = ('p09', 'p10', 'p11', 'p12', 'p08', 'p13', 's', 'all')
SLOTS = ('p09', 'p10', 'p11', 'p12', 'p08', 'p13', 's')


# --------------------------------------------------------------------- 工具
def leak_hits(text):
    return sorted({m.group(0).lower() for m in LEAK_RX.finditer(text or '')})


def reading(resp):
    try:
        body = resp.get_data(as_text=True)
    except UnicodeDecodeError:
        body = '<binary>'
    return {'status': resp.status_code,
            'content_type': (resp.headers.get('Content-Type') or '').split(';')[0],
            'body': body,
            'body_head': body[:220].replace('\n', ' '),
            'leaks': leak_hits(body),
            'is_json': (resp.headers.get('Content-Type') or '').startswith('application/json')}


def _msg_of(body):
    """jsonify 默认转义非 ASCII ⇒ 判「可读原因」前先解码 JSON，取 message 字段。"""
    try:
        return json.loads(body).get('message', '') or ''
    except (ValueError, AttributeError):
        return body or ''


def add_row(rows, label, resp, note=''):
    r = reading(resp)
    r['label'] = label
    if note:
        r['note'] = note
    rows.append(r)
    print('  %-46s %s %-26s leaks=%s %s' % (label, r['status'], r['content_type'] or '-',
                                           r['leaks'] or '[]', note))
    return r


def login(client, username, password):
    return client.post('/auth/login', data={'username': username, 'password': password},
                       follow_redirects=False)


# ------------------------------------------------------------------- 场景
def sc_p09(app, client, phase):
    """18 个谓词实例（17 处源站点）逐个用哨兵 id 打。"""
    rows = []
    with app.app_context():
        from app import models as M
        pid = (M.Product.query.order_by(M.Product.id).first() or type('x', (), {'id': 1})).id
        tid_target = (M.ProductionBatchItem.query.order_by(M.ProductionBatchItem.id).first())
        item_id = tid_target.id if tid_target else 1
        jid = None
    J = {'Content-Type': 'application/json'}
    S = SENTINEL
    targets = [
        ('Q1 PUT /api/quality/templates/<S>', 'put', f'/api/quality/templates/{S}', {}),
        ('Q2 DELETE /api/quality/templates/<S>', 'delete', f'/api/quality/templates/{S}', None),
        ('Q3 POST tasks/<S>/start-inspection', 'post', f'/api/quality/tasks/{S}/start-inspection', {}),
        ('Q4 POST records/<S>/submit', 'post', f'/api/quality/records/{S}/submit', {}),
        ('Q5 DELETE tasks/<S>', 'delete', f'/api/quality/tasks/{S}', None),
        ('Q6 PUT tasks/<S>', 'put', f'/api/quality/tasks/{S}', {}),
        ('Q7 GET records/<S>', 'get', f'/api/quality/records/{S}', None),
        ('Q8 GET records/<S>/print', 'get', f'/api/quality/records/{S}/print', None),
        ('PC1 POST create_instances', 'post', '/api/production_center/create_instances',
         {'production_order_id': S, 'quantity': 1}),
        ('PC2 POST items/<S>/tech_decomposition', 'post',
         f'/api/production_center/items/{S}/tech_decomposition', {}),
        ('PC3 GET items/<S>/detail', 'get', f'/api/production_center/items/{S}/detail', None),
        ('PC4 POST items/<S>/execute_operation', 'post',
         f'/api/production_center/items/{S}/execute_operation', {}),
        ('R1 GET /products/<pid>/bom/<S>', 'get', f'/products/{pid}/bom/{S}', None),
        ('R2 PUT /products/<pid>/bom/<S>', 'put', f'/products/{pid}/bom/{S}', {}),
        ('R3 DELETE /products/<pid>/bom/<S>', 'delete', f'/products/{pid}/bom/{S}', None),
        ('R4 DELETE /products/<pid>/processes/<S>', 'delete', f'/products/{pid}/processes/{S}', None),
        ('R5 PUT /products/<pid>/processes/<S>', 'put', f'/products/{pid}/processes/{S}', {}),
        ('R6 GET /products/<pid>/processes/<S>', 'get', f'/products/{pid}/processes/{S}', None),
    ]
    for label, method, path, body in targets:
        fn = getattr(client, method)
        resp = fn(path, json=body) if body is not None else fn(path)
        add_row(rows, label, resp)
    n404 = sum(1 for r in rows if r['status'] == 404)
    n500 = sum(1 for r in rows if r['status'] >= 500)
    leaks = sum(1 for r in rows if r['leaks'])
    fake200 = sum(1 for r in rows if r['status'] == 200 and 'success' in r['body']
                  and '"success": true' in r['body'].replace(' ', ' '))
    summary = {'requests': len(rows), 'status_404': n404, 'status_5xx': n500,
               'leak_rows': leaks, 'fake_200_success': fake200}
    checks = []
    if phase == 'post':
        checks.append(('P-09-a 全部 404（18 谓词实例 / 17 源站点）', n404 == len(rows)))
        checks.append(('P-09-a 无 5xx', n500 == 0))
        checks.append(('P-09-a 无泄漏', leaks == 0))
        checks.append(('P-09-a 无「200 + success:true」伪装', fake200 == 0))
        bad_ct = [r['label'] for r in rows if r['status'] == 404 and not r['is_json']
                  and not r['label'].startswith(('R1', 'R6'))]
        checks.append(('P-09-a 404 面 Content-Type 为 JSON（JSON 面 16 处；R1/R6 页面命名空间 GET '
                       '按既有 _wants_json() 口径为 HTML，残留项见文档 §9）', not bad_ct))
    return rows, summary, checks


def _mk_task(app, status='pending', with_record=False, tag='w4'):
    """在副本里造 InspectionTask（± InspectionRecord），返回 (task_id, record_id)。"""
    from app import db
    from app import models as M
    from datetime import date
    with app.app_context():
        admin = M.User.query.filter_by(username='admin').first() or M.User.query.first()
        t = M.InspectionTask(global_sn=M.SerialNumber.get_next_number(), template_id=None,
                             inspector_id=admin.id, target_type='product', target_id=1,
                             status=status, created_by=admin.id, notes='W4-' + tag)
        db.session.add(t)
        db.session.flush()
        rid = None
        if with_record:
            rec = M.InspectionRecord(global_sn=M.SerialNumber.get_next_number(), task_id=t.id,
                                     inspector_id=admin.id, inspection_date=date.today(),
                                     result='pass', notes='W4-' + tag)
            db.session.add(rec)
            db.session.flush()
            rid = rec.id
        db.session.commit()
        return t.id, rid


def sc_p10(app, client, phase):
    rows = []
    from app import db
    from app import models as M
    tid_rec, rid = _mk_task(app, 'pending', True, 'p10a')
    tid_free, _ = _mk_task(app, 'pending', False, 'p10b')
    tid_run, rid2 = _mk_task(app, 'in_progress', True, 'p10c')
    r_a = add_row(rows, 'P-10-a DELETE 有记录 pending 任务', client.delete(f'/api/quality/tasks/{tid_rec}'))
    r_b = add_row(rows, 'P-10-b DELETE 无记录 pending 任务', client.delete(f'/api/quality/tasks/{tid_free}'))
    r_c = add_row(rows, 'P-10-c DELETE in_progress 任务', client.delete(f'/api/quality/tasks/{tid_run}'))
    r_d = add_row(rows, 'P-10-d DELETE 哨兵 id', client.delete(f'/api/quality/tasks/{SENTINEL}'))
    with app.app_context():
        still = M.InspectionTask.query.get(tid_rec) is not None
        rec_cnt = M.InspectionRecord.query.filter_by(task_id=tid_rec).count()
        gone = M.InspectionTask.query.get(tid_free) is None
        audit = (M.AuditLog.query.filter_by(target_model='InspectionTask', target_id=tid_free)
                 .order_by(M.AuditLog.id.desc()).first())
        audit_ok = bool(audit and audit.rollback_type == 'delete')
    summary = {'p10a': {'status': r_a['status'], 'task_still_exists': still,
                        'record_count': rec_cnt, 'leaks': r_a['leaks'],
                        'reason': r_a['body_head']},
               'p10b': {'status': r_b['status'], 'task_deleted': gone, 'audit_delete': audit_ok},
               'p10c': {'status': r_c['status'], 'reason': r_c['body_head']},
               'p10d': {'status': r_d['status']},
               'reasons_differ': r_a['body_head'] != r_c['body_head']}
    checks = []
    if phase == 'post':
        checks.append(('P-10-a (status, exists, records, leaks) == (400, True, 1, 0)',
                       (r_a['status'], still, rec_cnt, len(r_a['leaks'])) == (400, True, 1, 0)))
        checks.append(('P-10-a 原因可读（含「质检记录」）',
                       '质检记录' in _msg_of(r_a['body'])))
        checks.append(('P-10-b 无记录 pending 仍 200 且行数 -1',
                       r_b['status'] == 200 and gone))
        checks.append(('P-10-b AuditLog rollback_type=delete', audit_ok))
        checks.append(('P-10-c in_progress 仍 400', r_c['status'] == 400))
        checks.append(('P-10-c 两条原因可区分', summary['reasons_differ']))
        checks.append(('P-10-d 哨兵 id ⇒ 404（并入 P-09-a）', r_d['status'] == 404))
    return rows, summary, checks


def _leak_scan(app, client):
    """P-11-a 的请求集：能触发错误出口的代表性请求（含 P-10 删任务、部分更新、缺字段、空体）。"""
    tid_rec, _ = _mk_task(app, 'pending', True, 'p11')
    tid_run, _ = _mk_task(app, 'in_progress', False, 'p11b')
    reqs = [
        ('DELETE 有记录任务（P-10 出口）', 'delete', f'/api/quality/tasks/{tid_rec}', None),
        ('PUT templates 部分更新', 'put', '/api/quality/templates/1', {'is_active': False}),
        ('POST tasks 缺 type', 'post', '/api/quality/tasks', {'inspector_id': 1}),
        ('POST tasks type 非法', 'post', '/api/quality/tasks', {'type': 'x'}),
        ('PUT templates 哨兵 id', 'put', f'/api/quality/templates/{SENTINEL}', {}),
        ('DELETE tasks 哨兵 id', 'delete', f'/api/quality/tasks/{SENTINEL}', None),
        ('POST /tasks/add 空表单体', 'post', '/tasks/add', None),
        ('POST process_assignment 空表单体', 'post', f'/api/process_assignment/{SENTINEL}', None),
        ('PUT tasks 空 JSON', 'put', f'/api/quality/tasks/{tid_run}', {}),
    ]
    rows = []
    for label, method, path, body in reqs:
        fn = getattr(client, method)
        resp = fn(path, json=body) if body is not None else fn(path)
        add_row(rows, label, resp)
    return rows


def sc_p11(app, client, phase):
    global _APP
    _APP = app
    rows = _leak_scan(app, client)
    leak_rows = [r for r in rows if r['leaks']]
    empty_body = [r['label'] for r in rows if not r['body'].strip()]
    # P-11-b 阴性注入：`/__w4_leak_probe__`（在 main() 中、**任何请求之前**注册的探针端点，
    # 不进生产代码）回显 str(e)，用于证明 P-11-a 的扫描判据**不是恒真**。
    inj_rows = []
    r_inj = client.get('/__w4_leak_probe__')
    add_row(inj_rows, 'P-11-b 注入探针端点（回显 str(e)）', r_inj,
            note='判据必须报红（hits>=1）')
    summary = {'leak_rows': len(leak_rows), 'leak_detail': [
        {'label': r['label'], 'leaks': r['leaks'], 'head': r['body_head']} for r in leak_rows],
        'empty_body_rows': empty_body,
        'injection_hits': len(inj_rows[0]['leaks']),
        'statuses': {r['label']: r['status'] for r in rows}}
    checks = []
    if phase == 'post':
        checks.append(('P-11-a 5 类泄漏命中 == 0', not leak_rows))
        checks.append(('P-11-a 错误正文非空（RC-6 可读原因）', not empty_body))
        checks.append(('P-11-a 状态码语义未变坏（无 5xx）',
                       all(r['status'] < 500 for r in rows)))
        checks.append(('P-11-b 注入 str(e) 后判据必须报红', len(inj_rows[0]['leaks']) >= 1))
    return rows + inj_rows, summary, checks


def _ensure_template(app):
    """副本里若没有质检模板则造一个（P-12-b 部分更新 / P-13 print 都需要真实 id）。"""
    from app import db
    from app import models as M
    with app.app_context():
        t = M.InspectionTemplate.query.order_by(M.InspectionTemplate.id).first()
        if t is None:
            admin = M.User.query.filter_by(username='admin').first() or M.User.query.first()
            t = M.InspectionTemplate(template_code='W4-TMPL', name='W4 模板', type='product',
                                     description='', is_active=True, created_by=admin.id)
            db.session.add(t)
            db.session.commit()
        return t.id


def sc_p12(app, client, phase):
    rows = []
    form = {'Content-Type': 'application/x-www-form-urlencoded'}
    with app.app_context():
        from app import models as M
    tid = _ensure_template(app)
    with app.app_context():
        from app import models as M
        item = M.ProductionBatchItem.query.order_by(M.ProductionBatchItem.id).first()
        iid = item.id if item else 1
    combos = [
        ('POST /tasks/add', 'post', '/tasks/add'),
        ('POST /api/quality/templates', 'post', '/api/quality/templates'),
        ('POST /api/quality/tasks', 'post', '/api/quality/tasks'),
        ('POST records/<real>/submit', 'post', f'/api/quality/records/{1}/submit'),
        ('POST tasks/<real>/start-inspection', 'post', f'/api/quality/tasks/{1}/start-inspection'),
        ('PUT /api/quality/tasks/<real>', 'put', f'/api/quality/tasks/{1}'),
        ('PUT /api/quality/templates/<real>', 'put', f'/api/quality/templates/{tid}'),
        ('POST /api/process_assignment/<id>', 'post', f'/api/process_assignment/{1}'),
        ('POST /api/process_assignment/bulk', 'post', '/api/process_assignment/bulk'),
        ('POST create_instances', 'post', '/api/production_center/create_instances'),
        ('POST items/<id>/tech_decomposition', 'post',
         f'/api/production_center/items/{iid}/tech_decomposition'),
        ('POST items/<id>/execute_operation', 'post',
         f'/api/production_center/items/{iid}/execute_operation'),
        # 注 1：`DELETE /api/quality/templates/<real>` **不是** 415 站点（DELETE 不读 body），
        #       若放入本组会真的删掉模板并使后续部分更新断言失真 ⇒ 移到 P-12-b 之后单独跑。
        # 注 2：`POST /audit_logs/rollback/<id>` 同属非 415 站点，其空体 500 属 17-W4W5 §9 第 5 项
        #       「审计回滚执行守恒（AC-52）」= 阶段 B，**不计入** P-12-a 的 5xx 判据（单独登记，不掩盖）。
    ]
    for label, method, path in combos:
        fn = getattr(client, method)
        resp = fn(path, data='', headers=form)      # 空表单体 + 错误媒体类型
        add_row(rows, '415-form ' + label, resp)
    # 空 JSON body（P-12-c）
    for label, method, path in combos[:6]:
        fn = getattr(client, method)
        resp = fn(path, data='', headers={'Content-Type': 'application/json'})
        add_row(rows, 'empty-json ' + label, resp)
    # P-12-b 三组合（先确保模板存在：上面的 415 组合不会删模板，但保守起见重建一次）
    tid = _ensure_template(app)
    r_partial = add_row(rows, 'P-12-b PUT templates/{is_active:false}',
                        client.put(f'/api/quality/templates/{tid}', json={'is_active': False}))
    r_only = add_row(rows, 'P-12-b PUT templates/{template_code:W4-TMPL2}',
                     client.put(f'/api/quality/templates/{tid}',
                                json={'template_code': 'W4-TMPL2'}))
    r_task_bad = add_row(rows, 'P-12-b POST tasks {type:x}',
                         client.post('/api/quality/tasks', json={'type': 'x'}))
    r_task_missing = add_row(rows, 'P-12-b POST tasks 缺 type',
                             client.post('/api/quality/tasks', json={'inspector_id': 1}))
    n5xx = sum(1 for r in rows if r['status'] >= 500)
    n_ok_4xx = sum(1 for r in rows if r['status'] in (400, 415))
    leak_rows = [r['label'] for r in rows if r['leaks']]
    html_rows = [r['label'] for r in rows
                 if r['status'] and 'html' in r['content_type'] and '/api/' in r['label']]
    silent_200 = [r['label'] for r in rows if r['status'] == 200
                  and ('"success": true' in r['body'].replace(' ', ''))]
    summary = {'requests': len(rows), 'status_4xx_400_415': n_ok_4xx, 'status_5xx': n5xx,
               'leak_rows': leak_rows, 'html_rows': html_rows, 'silent_200': silent_200,
               'p12b': {'partial': r_partial['status'], 'only_required': r_only['status'],
                        'task_bad_type': r_task_bad['status'],
                        'task_missing_type': r_task_missing['status'],
                        'partial_body': r_partial['body_head'],
                        'task_bad_body': r_task_bad['body_head']},
               'statuses': {r['label']: r['status'] for r in rows}}
    checks = []
    if phase == 'post':
        checks.append(('P-12-a 无 5xx（原红线 == 0）', n5xx == 0))
        checks.append(('P-12-a JSON 面不得返回 HTML 错误页', not html_rows))
        checks.append(('P-12-a 无泄漏', not leak_rows))
        checks.append(('P-12-b templates 部分更新 ∈ {200,400}',
                       r_partial['status'] in (200, 400)))
        checks.append(('P-12-b tasks 非法 type ⇒ 400', r_task_bad['status'] == 400))
        checks.append(('P-12-b tasks 缺 type ⇒ 400', r_task_missing['status'] == 400))
        checks.append(('P-12-c 空体不得 200 success', not silent_200))
    return rows, summary, checks


def sc_p08(app, client, phase):
    from app import db
    from app import models as M
    from datetime import date
    with app.app_context():
        emp = M.Employee.query.first()
        proc = M.ProcessPrice.query.first()
        t = M.TaskAssignment(global_sn=M.SerialNumber.get_next_number(), employee_id=emp.id,
                             process_id=proc.id, quantity=7, status='pending',
                             target_date=date(2027, 1, 15), notes='OLD_NOTES')
        db.session.add(t)
        db.session.commit()
        tid = t.id
        emp_id, proc_id = emp.id, proc.id
    payload = {'notes': 'NEW_NOTES', 'quantity': 9, 'status': 'pending',
               'target_date': '2027-01-15', 'employee_id': emp_id, 'process_id': proc_id}
    rows = []
    r = add_row(rows, 'P-08-a POST /tasks/<id>/edit（notes=NEW_NOTES）',
                client.post(f'/tasks/{tid}/edit', json=payload))
    with app.app_context():
        conn = db.engine.connect()
        tname = M.TaskAssignment.__tablename__
        db_notes = conn.execute(db.text(f'SELECT notes FROM {tname} WHERE id={tid}')).scalar()
        qty = conn.execute(db.text(f'SELECT quantity FROM {tname} WHERE id={tid}')).scalar()
        log = (M.AuditLog.query.filter_by(target_model='TaskAssignment', target_id=tid)
               .order_by(M.AuditLog.id.desc()).first())

        def _as_dict(v):
            if isinstance(v, dict):
                return v
            if isinstance(v, (str, bytes, bytearray)):
                try:
                    return json.loads(v)
                except ValueError:
                    return {}
            return {}

        old = _as_dict(getattr(log, 'old_data', None))
        new = _as_dict(getattr(log, 'new_data', None))
        conn.close()
    r2 = add_row(rows, 'P-08-c POST /tasks/<id>/edit（不传 notes）',
                 client.post(f'/tasks/{tid}/edit', json={k: v for k, v in payload.items()
                                                          if k != 'notes'}))
    with app.app_context():
        conn = db.engine.connect()
        notes_after_c = conn.execute(db.text(f'SELECT notes FROM {tname} WHERE id={tid}')).scalar()
        conn.close()
    summary = {'status': r['status'], 'db_notes_after': db_notes, 'quantity_after': qty,
               'audit': {'old_notes': old.get('notes'), 'new_notes': new.get('notes'),
                         'can_rollback': getattr(log, 'can_rollback', None),
                         'rollback_type': getattr(log, 'rollback_type', None),
                         'target_model': getattr(log, 'target_model', None),
                         'target_id': getattr(log, 'target_id', None),
                         'action': getattr(log, 'action', None)},
               'notes_after_no_notes_case': notes_after_c,
               'status_no_notes_case': r2['status']}
    checks = []
    if phase == 'post':
        checks.append(('P-08-a 200 且库内 notes == NEW_NOTES',
                       r['status'] == 200 and db_notes == 'NEW_NOTES'))
        checks.append(('P-08-a 既有字段仍正确落库（quantity == 9）', qty == 9))
        checks.append(('P-08-b 审计 old != new（核心）',
                       old.get('notes') == 'OLD_NOTES' and new.get('notes') == 'NEW_NOTES'
                       and old.get('notes') != new.get('notes')))
        checks.append(('P-08-b 审计元数据齐备',
                       getattr(log, 'can_rollback', None) is True
                       and getattr(log, 'rollback_type', None) == 'edit'
                       and getattr(log, 'target_model', None) == 'TaskAssignment'
                       and getattr(log, 'target_id', None) == tid))
        checks.append(('P-08-c 未传 notes ⇒ 保持原值', notes_after_c == 'NEW_NOTES'))
    return rows, summary, checks


CARRIER_REGISTER = 'test-reports-2026-10/24-W4载体登记册.json'


def sc_p13(app, client, phase):
    """扫 /api/ 面的载体分档 + 载体登记册逐行一致。"""
    import smoke_test as st
    _mk_task(app, 'pending', True, 'p13')      # 保证 print 端点的真实 record id 可解析
    ids = st.first_ids(app)
    rows = []
    for rule in sorted(app.url_map.iter_rules(), key=lambda r: str(r)):
        path = str(rule)
        if not path.startswith('/api/') or rule.endpoint == 'static':
            continue
        url = path
        if rule.arguments:
            url, why = st.resolve_url(rule, ids)
            if url is None:
                continue
        try:
            resp = client.get(url)
        except Exception as e:
            rows.append({'label': f'GET {path}', 'status': 'EXC', 'exc': e.__class__.__name__,
                         'content_type': '', 'leaks': []})
            continue
        r = reading(resp)
        r['label'] = f'GET {path}'
        r['path'] = path
        if 'GET' not in rule.methods:
            r['note'] = 'GET 打到仅 %s 的端点（期望 405，Flask 默认行为）' % \
                        '/'.join(sorted(rule.methods - {'HEAD', 'OPTIONS'}))
        rows.append(r)
    n_html200 = [r for r in rows if r['status'] == 200 and 'html' in (r['content_type'] or '')]
    n_bin200 = [r for r in rows if r['status'] == 200 and any(
        k in (r['content_type'] or '') for k in ('sheet', 'octet-stream', 'pdf', 'zip'))]
    sent_non_get = [r for r in rows if r.get('note')]
    n405 = [r for r in rows if r['status'] == 405]
    n_expect_405 = sum(1 for rule in app.url_map.iter_rules()
                       if str(rule).startswith('/api/') and 'GET' not in rule.methods
                       and rule.endpoint != 'static')
    n5xx = [r for r in rows if isinstance(r['status'], int) and r['status'] >= 500]
    reg_path = os.path.join(REPO_ROOT, CARRIER_REGISTER)
    reg_rows = json.load(open(reg_path, encoding='utf-8'))['rows'] if os.path.isfile(reg_path) else []
    reg_ok = len(reg_rows) == 4 and sum(1 for x in reg_rows if x.get('分类') == '违规') == 0
    # 逐行一致：登记册里每个非二进制行都能被实测命中
    live = {(r.get('path'), (r['status'], r['content_type'])) for r in rows}
    mismatched = [x for x in reg_rows
                  if (x['path'], (x['status'], x['content_type'])) not in live]
    summary = {'api_get_scanned': len(rows), 'html200': [r['label'] for r in n_html200],
               'binary200': [r['label'] for r in n_bin200],
               'count_405': len(n405), 'count_5xx': len(n5xx),
               'register_rows': len(reg_rows), 'register_violations':
               sum(1 for x in reg_rows if x.get('分类') == '违规'),
               'register_mismatched': [x.get('path') for x in mismatched],
               'statuses': {r['label']: r['status'] for r in rows if r['status'] != 404}}
    checks = []
    if phase == 'post':
        checks.append(('P-13-a 200+HTML ≤ 1 且已登记', len(n_html200) <= 1
                       and all(r.get('path') for r in n_html200)))
        checks.append(('P-13-a 200+二进制 == 3 且不被改成 JSON', len(n_bin200) == 3))
        checks.append(('P-13-a /api/ 面无非预期状态（50 个请求：200/404/405 之外为空；405 = %d，'
                       '由 Flask 路由层产生、与本次修复无关）' % len(n405),
                       not n5xx and all(r['status'] in (200, 404, 405) for r in rows)
                       and len(n405) > 0))
        checks.append(('P-13-a 无 5xx', not n5xx))
        checks.append(('P-13-c 载体登记册 == 4 行、违规 0 行', reg_ok))
        checks.append(('P-13-c 登记册与实测逐行一致', not mismatched))
    return rows, summary, checks


def sc_s(app, client, phase):
    """S-1…S-4、S-6（S-5 全量矩阵属 t9）。"""
    from app import db
    from app import models as M
    rows = []
    with app.app_context():
        rec = M.InspectionRecord.query.order_by(M.InspectionRecord.id).first()
        bom = M.ProductBOM.query.order_by(M.ProductBOM.id).first()
        item = M.ProductionBatchItem.query.order_by(M.ProductionBatchItem.id).first()
        tmpl = M.InspectionTemplate.query.order_by(M.InspectionTemplate.id).first()
        emp = M.Employee.query.first()
        proc = M.ProcessPrice.query.first()
        t = M.TaskAssignment.query.order_by(M.TaskAssignment.id).first()
        emp_id, proc_id = (emp.id if emp else None), (proc.id if proc else None)
    if rec:
        add_row(rows, 'S-1 GET records/<real>', client.get(f'/api/quality/records/{rec.id}'))
    if bom:
        add_row(rows, 'S-1 GET products/<pid>/bom/<real>',
                client.get(f'/products/{bom.product_id}/bom/{bom.id}'))
    if item:
        add_row(rows, 'S-1 GET pc items/<real>/detail',
                client.get(f'/api/production_center/items/{item.id}/detail'))
    if t:
        r = add_row(rows, 'S-2 POST /tasks/<real>/edit（改 quantity/date）',
                    client.post(f'/tasks/{t.id}/edit',
                                json={'quantity': 9, 'target_date': '2027-01-15',
                                      'employee_id': emp_id, 'process_id': proc_id}))
        with app.app_context():
            conn = db.engine.connect()
            tn = M.TaskAssignment.__tablename__
            q = conn.execute(db.text(f'SELECT quantity FROM {tn} WHERE id={t.id}')).scalar()
            st_ = conn.execute(db.text(f'SELECT status FROM {tn} WHERE id={t.id}')).scalar()
            conn.close()
    else:
        q = st_ = None
    tid_free, _ = _mk_task(app, 'pending', False, 's3')
    r3 = add_row(rows, 'S-3 DELETE 无记录 pending', client.delete(f'/api/quality/tasks/{tid_free}'))
    for label, path in (('S-4 GET records/export', '/api/quality/records/export'),
                        ('S-4 GET tasks/export', '/api/quality/tasks/export'),
                        ('S-4 GET tasks/template', '/api/quality/tasks/template')):
        add_row(rows, label, client.get(path))
    if tmpl:
        r6 = add_row(rows, 'S-6 PUT templates/<real> 合法全字段',
                     client.put(f'/api/quality/templates/{tmpl.id}',
                                json={'template_code': tmpl.template_code, 'name': tmpl.name,
                                      'type': tmpl.type, 'description': tmpl.description,
                                      'is_active': bool(tmpl.is_active)}))
    summary = {'s2_quantity': q, 's2_status': st_, 's3_status': r3['status'],
               'xlsx_content_types': [r['content_type'] for r in rows
                                      if 'export' in r['label'] or 'template' in r['label']],
               'statuses': {r['label']: r['status'] for r in rows}}
    checks = []
    if phase == 'post':
        checks.append(('S-1 合法读仍 200 + JSON',
                       all(r['status'] == 200 and r['is_json'] for r in rows
                           if r['label'].startswith('S-1'))))
        checks.append(('S-2 既有字段仍正确落库（quantity=9，status 不变）', q == 9))
        checks.append(('S-3 无记录 pending 仍可删（200）', r3['status'] == 200))
        checks.append(('S-4 三条导出仍为 xlsx',
                       sum(1 for r in rows if 'sheet' in (r['content_type'] or '')) == 3))
        checks.append(('S-6 合法 JSON 正常路径仍 200', r6['status'] == 200))
    return rows, summary, checks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--phase', required=True, choices=('pre', 'post'))
    ap.add_argument('--scenario', default='all', choices=SCENARIOS)
    ap.add_argument('--json', default=None)
    args = ap.parse_args()
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors='replace')
        except Exception:
            pass

    from _test_bootstrap import make_app, ensure_role_users
    db_before = real_db_status()['sha256']
    app, copy_path = make_app()
    # P-11-b 的注入端点必须在**任何请求之前**注册（Flask 首次请求后禁止改路由表）
    with app.app_context():
        from app import db as _db

        @app.route('/__w4_leak_probe__')
        def _w4_leak_probe():
            try:
                _db.session.execute(_db.text('SELECT * FROM __nope__'))
            except Exception as e:
                return f'注入泄漏：{e}', 500
            return 'ok'
    users, password = ensure_role_users(app)
    client = app.test_client()
    resp = login(client, users['admin'], password)
    print('[w4] phase=%s scenario=%s run_id=%s login=%s copy=%s'
          % (args.phase, args.scenario, RUN_ID, resp.status_code, os.path.basename(copy_path)))

    todo = SLOTS if args.scenario == 'all' else (args.scenario,)
    out = {'harness': 'w4_probe.py', 'phase': args.phase, 'scenario': args.scenario,
           'run_id': RUN_ID, 'login_status': resp.status_code, 'scenarios': {}, 'checks': []}
    for slot in todo:
        print('\n### %s' % slot)
        rows, summary, checks = globals()['sc_' + slot](app, client, args.phase)
        out['scenarios'][slot] = {'summary': summary,
                                  'rows': [{k: v for k, v in r.items() if k != 'body'} for r in rows]}
        out['checks'] += [{'slot': slot, 'desc': d, 'status': 'passed' if ok else 'failed'}
                          for d, ok in checks]
        for d, ok in checks:                     # 逐槽立即打印，崩溃也不丢判决
            print('  [%s] %s: %s' % ('OK  ' if ok else 'FAIL', slot, d))
        if args.json:                      # 逐槽落盘：中途异常也能留下已完成部分
            os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
            with open(args.json, 'w', encoding='utf-8', newline='\n') as fh:
                json.dump(out, fh, ensure_ascii=False, indent=1)
    db_after = real_db_status()['sha256']
    out['real_db'] = {'before': db_before, 'after': db_after, 'unchanged': db_before == db_after}
    failed = [c for c in out['checks'] if c['status'] == 'failed']
    print('\n== 判据（phase=%s）==' % args.phase)
    for c in out['checks']:
        print('  [%s] %s: %s' % ('OK  ' if c['status'] == 'passed' else 'FAIL', c['slot'], c['desc']))
    print('  真库未变: %s' % out['real_db']['unchanged'])
    out['verdict'] = 'PASS' if (not failed and out['real_db']['unchanged']) else (
        'NO_CHECKS' if args.phase == 'pre' else 'FAIL')
    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
        with open(args.json, 'w', encoding='utf-8', newline='\n') as fh:
            json.dump(out, fh, ensure_ascii=False, indent=1)
        print('JSON -> %s' % args.json)
    text = ('=' * 90 + '\n[w4] phase=%s scenario=%s run_id=%s verdict=%s\n'
            % (args.phase, args.scenario, RUN_ID, out['verdict'])
            + json.dumps(out, ensure_ascii=False, indent=1) + '\n')
    print('原始输出 -> %s' % save_evidence('w4_%s_%s.console.txt' % (args.phase, args.scenario), text))
    if args.phase == 'post' and failed:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
