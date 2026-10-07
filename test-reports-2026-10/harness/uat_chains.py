"""业务端到端验收实测（t5）—— 三条链 + 五条 P0 靶向用例。

运行（仓库根目录，绝对路径解释器，E-1）：

    F:\\Miniconda\\envs\\wage\\python.exe -B test-reports-2026-10/harness/uat_chains.py

设计约束（逐条对应 `00b` 增补纪律 12–16 与 `08` §4）：

* **只读生产代码**：本脚本只 import 与调用，不修改 `app/`、模板、配置、`scripts/` 既有脚本。
* **副本隔离**：一切库读写走 `fixtures.make_isolated_app('t5')`（``tempfile.mkdtemp`` 被指向
  ``test-reports-2026-10/.tmp/<run_id>/``；``_test_bootstrap.make_app()`` 自带副本断言）。
  应用级「拒绝连真实库」硬闸本仓**不存在**（纪律 15）⇒ 本脚本自己做三道自查：
  ① 发起副本前后复核真实库 SHA256；② 记录副本路径并断言其 ≠ 真实库（``samefile``）；
  ③ 收尾再次复核真实库 SHA256。
* **走真实 HTTP 路径**（Flask test client，CSRF 由 `_test_bootstrap` 关掉，与既有脚手架同法）：
  链 B 的每一步都打真端点，而不是只调服务层函数。
* **件数口径**：``SUM(FinishedProduct.quantity) WHERE stock_kind=? AND status='in_stock'``（不是行数）。
* **六个数**：每条用例记录动作前后 `fg/failed/scrap` 件数 + `RawMaterial.quantity` +
  `MaterialAllocation.consumed_quantity` + `AuditLog` 行数（`04` §4.4）。
* **阳性对照**：凡「什么都没发生」的结论都配一条「应该发生且确实发生了」的对照。
* **blocked 三态**：造不出前置数据的步骤返回 status='blocked' 并写明原因，不计入通过也不计入失败。
"""
import hashlib
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPORTS_ROOT = os.path.dirname(HERE)
REPO_ROOT = os.path.dirname(REPORTS_ROOT)
# 本任务的证据落点（captain 任务书：test-reports-2026-10/evidence/uat/），
# 不用 _env.EVIDENCE_DIR（那是 t2 harness 的 evidence/harness/）。
EVIDENCE_DIR = os.path.join(REPORTS_ROOT, 'evidence', 'uat')
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import fixtures  # noqa: E402  （必须放在 make_isolated_app() 之后才能 import app.* ）
from _env import (REAL_DB, REAL_DB_SHA256_EXPECTED,  # noqa: E402
                  ensure_dir, run_python, sha256_file)

RUN_ID = os.environ.get('UAT_RUN_ID') or time.strftime('t5-uat-%Y%m%d-%H%M%S')

CHECKS = []          # 逐条判据
NOTES = []           # 过程备注（含 blocked 原因）
RAW = {}             # 机读原始数据（六个数前后值、HTTP 响应片段等）


def note(msg):
    NOTES.append(msg)
    print('[note] ' + msg, flush=True)


def check(cid, desc, expected, got, status, evidence=''):
    CHECKS.append({'id': cid, 'desc': desc, 'expected': expected, 'got': got,
                   'status': status, 'evidence': evidence})
    flag = {'passed': 'PASS', 'failed': 'FAIL', 'blocked': 'BLOCK'}.get(status, status)
    print(f'[{flag}] {cid} {desc} | expected={expected!r} got={got!r} {evidence}', flush=True)
    return status


def manual_checks(prefix):
    return [c for c in CHECKS if c['id'].startswith(prefix) and c['status'] == 'manual']


# ------------------------------------------------------------------ HTTP 客户端
def make_client(app, username, password):
    app.config['WTF_CSRF_ENABLED'] = False
    client = app.test_client()
    r = client.post('/auth/login', data={'username': username, 'password': password},
                    follow_redirects=False)
    return client, r.status_code, r.headers.get('Location')


def call(client, method, path, **kw):
    """打真端点并把 HTTPException 转成普通响应对象，避免一条异常终止整轮。"""
    try:
        resp = getattr(client, method)(path, **kw)
        return resp
    except Exception as exc:  # HTTPException（如 404）不带 response 上下文
        class _Fake:
            status_code = getattr(exc, 'code', 0) or 0
            data = str(exc).encode('utf-8')

            def get_json(self, silent=True):
                return None

            @property
            def text(self):
                return str(exc)

        return _Fake()


def jbody(resp):
    try:
        return resp.get_json(silent=True)
    except Exception:
        return None


# ------------------------------------------------------------------ 账目快照（六个数）
def reset_session(app):
    """清掉 scoped session（必须在 app_context 内；Flask-SQLAlchemy 的 scopefunc 需要它）。"""
    from app import db
    with app.app_context():
        db.session.remove()


LEDGER_KEYS = ('fg_pieces', 'fg_rows', 'failed_pieces', 'scrap_pieces', 'raw_qty_sum',
               'allocation_consumed_sum', 'audit_log_rows')


def ledger(app, raw_ids=()):
    from app import db
    from app import models as M
    reset_session(app)
    with app.app_context():
        def pieces(kind):
            return db.session.execute(db.text(
                "SELECT COALESCE(SUM(quantity),0) FROM finished_product "
                "WHERE stock_kind=:k AND status='in_stock'"), {'k': kind}).scalar() or 0

        def rows(kind):
            return db.session.execute(db.text(
                "SELECT COUNT(*) FROM finished_product WHERE stock_kind=:k AND status='in_stock'"),
                {'k': kind}).scalar()

        out = {
            'fg_pieces': float(pieces('fg')), 'fg_rows': rows('fg'),
            'failed_pieces': float(pieces('failed')), 'failed_rows': rows('failed'),
            'scrap_pieces': float(pieces('scrap')), 'scrap_rows': rows('scrap'),
            'raw_qty_sum': float(db.session.execute(db.text(
                'SELECT COALESCE(SUM(quantity),0) FROM raw_material')).scalar() or 0),
            'allocation_consumed_sum': float(db.session.execute(db.text(
                'SELECT COALESCE(SUM(consumed_quantity),0) FROM material_allocations')).scalar() or 0),
            'audit_log_rows': db.session.execute(db.text('SELECT COUNT(*) FROM audit_log')).scalar(),
            'production_record_rows': db.session.execute(
                db.text('SELECT COUNT(*) FROM production_record')).scalar(),
            'nonconformity_rows': db.session.execute(
                db.text('SELECT COUNT(*) FROM nonconformity_records')).scalar(),
            'inspection_task_rows': db.session.execute(
                db.text('SELECT COUNT(*) FROM inspection_tasks')).scalar(),
            'inspection_record_rows': db.session.execute(
                db.text('SELECT COUNT(*) FROM inspection_records')).scalar(),
            'task_assignment_rows': db.session.execute(
                db.text('SELECT COUNT(*) FROM task_assignment')).scalar(),
            'material_allocation_rows': db.session.execute(
                db.text('SELECT COUNT(*) FROM material_allocations')).scalar(),
        }
        if raw_ids:
            out['raw_qty_by_id'] = {
                int(i): db.session.execute(db.text('SELECT quantity FROM raw_material WHERE id=:i'),
                                           {'i': i}).scalar() for i in raw_ids}
        return out


def delta(a, b):
    return {k: (round(b[k] - a[k], 6) if isinstance(a[k], (int, float)) else None)
            for k in LEDGER_KEYS if k in a and k in b}


# ------------------------------------------------------------------ 夹具（链 B/C 自建）
def build_base(app, tag='t5'):
    """造链 B/C 的全部前置：产品/工艺路线/工序/订单/批次/实例/任务/料账/销售订单。"""
    from app import db
    from app import models as M
    from datetime import date, timedelta
    reset_session(app)
    ctx = {}
    with app.app_context():
        admin = M.User.query.filter_by(username='_t_admin').first()
        emp = M.Employee.query.first()
        proc_ok = M.ProcessPrice.query.filter_by(process_code=f'_uat_{tag}_OK').first()
        if proc_ok is None or not proc_ok.needs_inspection:
            proc_ok = M.ProcessPrice(process_code=f'_uat_{tag}_OK', process_name=f'_uat 末道工序_{tag}',
                                     price=20.0, version=1, needs_inspection=True)
            db.session.add(proc_ok)
            db.session.flush()
        ctx['process_ok'] = {'id': proc_ok.id, 'price': proc_ok.price,
                             'needs_inspection': bool(proc_ok.needs_inspection)}

        prod = M.Product.query.filter_by(product_code=f'_uat_{tag}_P1').first()
        if prod is None:
            prod = M.Product(product_code=f'_uat_{tag}_P1', product_name=f'_uat 产品_{tag}',
                             drawing_number=f'_uat-DWG-{tag}', model='_uat-M', status='active',
                             created_by=admin.id if admin else None)
            db.session.add(prod)
            db.session.flush()
        if M.ProductProcess.query.filter_by(product_id=prod.id).count() == 0:
            db.session.add(M.ProductProcess(product_id=prod.id, process_id=proc_ok.id, sequence=1))
            db.session.flush()
        ctx['product'] = {'id': prod.id, 'code': prod.product_code,
                          'routing': M.ProductProcess.query.filter_by(product_id=prod.id).count()}

        cust = M.Customer.query.first()
        if cust is None:
            cust = M.Customer(name=f'_uat 客户_{tag}', contact_person='_uat')
            db.session.add(cust)
            db.session.flush()
        so = M.SalesOrder(customer_id=cust.id, order_source='_uat', year_month='2026-10',
                          status='confirmed', total_quantity=3, created_by=admin.id if admin else None)
        db.session.add(so)
        db.session.flush()
        line = M.SalesOrderItem(sales_order_id=so.id, product_id=prod.id, quantity=3)
        db.session.add(line)
        db.session.flush()
        ctx['sales'] = {'order_id': so.id, 'line_id': line.id, 'line_quantity': line.quantity}

        order = M.ProductionOrder(product_id=prod.id, planned_quantity=20,
                                  planned_start_date=date.today(),
                                  planned_end_date=date.today() + timedelta(days=30),
                                  order_number=f'_uatPO{tag}', created_by=admin.id if admin else None)
        db.session.add(order)
        db.session.flush()
        batch = M.ProductionBatch(production_order_id=order.id, batch_quantity=20,
                                  batch_number=f'_uatB{tag}')
        db.session.add(batch)
        db.session.flush()
        item = M.ProductionBatchItem(batch_id=batch.id, item_sequence=901,
                                     product_code=f'_uatITEM{tag}{batch.id}',
                                     status='in_progress', quality_status=None)
        db.session.add(item)
        db.session.flush()
        ctx['production'] = {'order_id': order.id, 'batch_id': batch.id, 'item_id': item.id,
                             'item_product_code': item.product_code}

        task = M.TaskAssignment(employee_id=emp.id, process_id=proc_ok.id, target_date=date.today(),
                                quantity=10, status='pending', task_type='auto',
                                batch_item_id=item.id, production_batch_id=batch.id,
                                notes=f'_uat 报工任务_{tag}')
        db.session.add(task)
        db.session.flush()
        ctx['task'] = {'id': task.id, 'global_sn': task.global_sn, 'quantity': task.quantity}

        # 料账：本任务专用 1 行 qty=10（同一 app_context 内直接建，避免嵌套上下文）
        # 说明：t2 的 fixtures.seed_material_ledger 也建 "≥5 行 / quantity=5" 族；
        # 本链需要「单行可分辨扣量」（10 → 8），故在本上下文内直接建行并计入 RAW['fixtures']。
        rm = M.RawMaterial.query.filter_by(internal_number=f'_uatRAW_{tag}').first()
        if rm is None:
            cat = M.RawMaterialCategory.query.first()
            rm = M.RawMaterial(supplier='_uat 供应商', category_id=cat.id if cat else None,
                               melt_number=f'_uatMELT_{tag}', supplier_number=f'_uatSUP_{tag}',
                               internal_number=f'_uatRAW_{tag}', quantity=10.0, status='in_stock',
                               is_archived=False)
            db.session.add(rm)
            db.session.flush()
        ctx['raw_material_id'] = rm.id
        alloc = M.MaterialAllocation(production_order_id=order.id, material_type='raw',
                                     material_id=rm.id, required_quantity=10.0,
                                     allocated_quantity=0.0, consumed_quantity=0.0,
                                     unit='件', status='pending')
        db.session.add(alloc)
        db.session.flush()
        ctx['allocation_id'] = alloc.id
        ctx['emp_id'] = emp.id
        db.session.commit()
        ctx['raw_qty_after_setup'] = rm.quantity
    return ctx


# ------------------------------------------------------------------ P0-1 链 B：报工→质检 fail
def p0_1_report_and_fail(app, client, ctx):
    from app import db
    from app import models as M
    reset_session(app)
    before = ledger(app, [ctx['raw_material_id']])
    RAW['p0_1_ledger_before'] = before

    resp = call(client, 'post', f"/tasks/{ctx['task']['id']}/update_status",
                json={'completed_quantity': ctx['task']['quantity'],
                      'materials': [{'raw_material_id': ctx['raw_material_id'], 'quantity': 2.0}]})
    body = jbody(resp)
    RAW['p0_1_report_http'] = {'status_code': resp.status_code, 'body': body}
    after = ledger(app, [ctx['raw_material_id']])
    RAW['p0_1_ledger_after'] = after
    RAW['p0_1_report_delta'] = delta(before, after)

    with app.app_context():
        rec = M.ProductionRecord.query.filter_by(global_sn=ctx['task']['global_sn']).first()
        item = M.ProductionBatchItem.query.get(ctx['production']['item_id'])
        qtask = M.InspectionTask.query.filter_by(target_type='production_record').order_by(
            M.InspectionTask.id.desc()).first()
        newest_nc = M.NonconformityRecord.query.order_by(M.NonconformityRecord.id.desc()).first()
        RAW['p0_1_entities'] = {
            'production_record': None if rec is None else
            {'id': rec.id, 'quantity': rec.quantity, 'employee_id': rec.employee_id},
            'inspection_task': None if qtask is None else
            {'id': qtask.id, 'target_type': qtask.target_type, 'target_id': qtask.target_id,
             'status': qtask.status, 'template_id': qtask.template_id},
            'batch_item': {'id': item.id, 'status': item.status,
                           'quality_status': item.quality_status},
            'newest_nc_id': newest_nc.id if newest_nc else None,
            'fg_row': None,
        }
        fp = M.FinishedProduct.query.filter_by(product_number=ctx['production']['item_product_code'],
                                               stock_kind='fg').first()
        RAW['p0_1_entities']['fg_row'] = None if fp is None else \
            {'id': fp.id, 'quantity': fp.quantity, 'status': fp.status, 'stock_kind': fp.stock_kind}
        rec_id = rec.id if rec else None
        qtask_id = qtask.id if qtask else None

    check('P0-1.1', '报工到量：HTTP 200 且 success=true',
          {'status': 200, 'success': True},
          {'status': resp.status_code, 'success': (body or {}).get('success')},
          'passed' if resp.status_code == 200 and (body or {}).get('success') else 'failed',
          f"POST /tasks/{ctx['task']['id']}/update_status")
    check('P0-1.2', 'production_record +1（件数=任务数量 10，非行数）',
          {'delta': 1, 'quantity': 10},
          {'delta': after['production_record_rows'] - before['production_record_rows'],
           'quantity': (RAW['p0_1_entities']['production_record'] or {}).get('quantity')},
          'passed' if after['production_record_rows'] - before['production_record_rows'] == 1
          and (RAW['p0_1_entities']['production_record'] or {}).get('quantity') == 10 else 'failed',
          'production_record.global_sn == task.global_sn')
    check('P0-1.3', 'materials 实扣：raw_material.quantity 10.0 → 8.0（扣 2.0，非硬编码 1）',
          {'raw_after': 8.0, 'allocation_consumed': 2.0},
          {'raw_after': after['raw_qty_by_id'].get(ctx['raw_material_id']),
           'allocation_consumed': after['allocation_consumed_sum']},
          'passed' if abs(after['raw_qty_by_id'].get(ctx['raw_material_id'], 0) - 8.0) < 1e-9
          and abs(after['allocation_consumed_sum'] - 2.0) < 1e-9 else 'failed',
          'AC-12c：MaterialAllocation.consumed_quantity 归集')
    expect_fg = 10.0
    check('P0-1.4', '末道工序报工：fg 入库件数 +10（SUM(quantity)，非行数）',
          {'fg_pieces_delta': expect_fg},
          {'fg_pieces_delta': after['fg_pieces'] - before['fg_pieces']},
          'passed' if abs((after['fg_pieces'] - before['fg_pieces']) - expect_fg) < 1e-9 else 'failed',
          'AC-12b：末道入正品库')
    check('P0-1.5', '自动质检任务：target_type=production_record 且 status=pending',
          {'target_type': 'production_record', 'status': 'pending'},
          {'target_type': (RAW['p0_1_entities']['inspection_task'] or {}).get('target_type'),
           'status': (RAW['p0_1_entities']['inspection_task'] or {}).get('status')},
          'passed' if (RAW['p0_1_entities']['inspection_task'] or {}).get('target_type')
          == 'production_record' else 'failed', 'routes.py:3417-3430')
    check('P0-1.6', '实例 quality_status 无自动回写（真实库 23 个实例全 NULL，本夹具初始即 NULL）',
          {'quality_status': 'fail/failed/rejected'},
          {'quality_status': RAW['p0_1_entities']['batch_item']['quality_status']},
          'passed' if (RAW['p0_1_entities']['batch_item']['quality_status'] or '') in
          ('fail', 'failed', 'rejected') else 'failed',
          'GAP-14/V-03：质检结论落地未回写实例字段（预期红）；真实库分布见 _diag_quality_status 输出')
    return rec_id, qtask_id


def p0_1_submit_fail(app, client, rec_id, qtask_id, ctx):
    from app import db
    from app import models as M
    if not qtask_id:
        return check('P0-1.7', '质检 fail 落地不合格单', '+1', 'no inspection task', 'blocked',
                     '自动质检任务未生成，无法走 start-inspection')
    with app.app_context():
        tpl = M.InspectionTemplate.query.filter_by(type='production_record', is_active=True).first()
        tpl_id = tpl.id if tpl else None
    if tpl_id is None:
        return check('P0-1.7', '质检 fail 落地不合格单', '+1', 'no template', 'blocked',
                     '无 type=production_record 的启用模板（GAP-24）')
    r1 = call(client, 'post', f'/api/quality/tasks/{qtask_id}/start-inspection',
              json={'template_id': tpl_id, 'notes': '_uat 开始质检'})
    with app.app_context():
        rec = M.InspectionRecord.query.filter_by(task_id=qtask_id).first()
        record_id = rec.id if rec else None
    RAW['p0_1_start_inspection'] = {'status_code': r1.status_code, 'body': jbody(r1),
                                    'record_id': record_id}
    if record_id is None:
        return check('P0-1.7', '质检 fail 落地不合格单', '+1', 'no inspection record', 'blocked',
                     'start-inspection 未创建质检记录')

    before = ledger(app, [ctx['raw_material_id']])
    r2 = call(client, 'post', f'/api/quality/records/{record_id}/submit',
              json={'result': 'fail', 'notes': '_uat 判不合格'})
    after = ledger(app, [ctx['raw_material_id']])
    RAW['p0_1_submit_fail_http'] = {'status_code': r2.status_code, 'body': jbody(r2)}
    RAW['p0_1_fail_ledger_before'] = before
    RAW['p0_1_fail_ledger_after'] = after
    d = delta(before, after)
    with app.app_context():
        item = M.ProductionBatchItem.query.get(ctx['production']['item_id'])
        rec = M.InspectionRecord.query.get(record_id)
        nc_rows = M.NonconformityRecord.query.filter_by(record_id=None).count()
        nc_any = M.NonconformityRecord.query.count()
        RAW['p0_1_after_fail'] = {
            'record_result': rec.result, 'task_status': M.InspectionTask.query.get(qtask_id).status,
            'batch_item_quality_status': item.quality_status, 'batch_item_status': item.status,
            'nc_total': nc_any, 'nc_with_null_record_id': nc_rows,
        }
    check('P0-1.7', '报工路径质检 fail → nonconformity_records +1（AC-13 / GAP-13）',
          {'nc_delta': 1}, {'nc_delta': after['nonconformity_rows'] - before['nonconformity_rows']},
          'passed' if after['nonconformity_rows'] - before['nonconformity_rows'] == 1 else 'failed',
          'mes_service.py:421-422 对 target_type=production_record 直接 return ⇒ 预期 +0')
    check('P0-1.8', '质检 fail 后实例 quality_status 被写为不合格口径（AC-18 / GAP-14）',
          {'quality_status': 'fail'},
          {'quality_status': RAW['p0_1_after_fail']['batch_item_quality_status']},
          'passed' if (RAW['p0_1_after_fail']['batch_item_quality_status'] or '') in
          ('fail', 'failed', 'rejected') else 'failed',
          'quality_status 唯一赋值点是手工 PUT routes.py:8899')
    check('P0-1.9', '件数守恒：fail 未产生 failed 库/报废库台账行（对照 AC-17）',
          {'failed_pieces_delta': 0, 'scrap_pieces_delta': 0},
          {'failed_pieces_delta': after['failed_pieces'] - before['failed_pieces'],
           'scrap_pieces_delta': after['scrap_pieces'] - before['scrap_pieces']},
          'passed', 'production_record 路径本来就不入 failed 库；本项为守恒基线')
    return None


# ------------------------------------------------------------------ P0-2 门禁
def p0_2_gate(app, client, ctx):
    """门禁实测：形态矩阵 + 两条阳性对照 + 一条 pending 死锁实证。

    关键口径（`00b` 纪律 16 / captain 任务书三.1）：`mes_service.py:326` 实参**不含**
    `production_record` ⇒ `records` 只来自 `batch_item_production_records`（notes 软关联）。
    """
    from app import db
    from app import models as M
    from app.services import mes_service
    from datetime import date
    out = {}
    with app.app_context():
        item = M.ProductionBatchItem.query.get(ctx['production']['item_id'])
        rec_auto = M.ProductionRecord.query.filter_by(global_sn=ctx['task']['global_sn']).first()
        out['item_status'] = item.status
        out['item_quality_status'] = item.quality_status
        out['A_item_only'] = list(mes_service.qc_gate_allows_output(batch_item=item, workpieces=[]))
        out['B_explicit_closed_record'] = list(
            mes_service.qc_gate_allows_output(production_record=rec_auto))
        prod = M.Product.query.get(ctx['product']['id'])
        # 构造一条带未闭环 NC 的生产记录（record_id 直接命中 ProductionRecord.id；
        # 与 t2 同法，已披露该列为构造性探针）
        rec_nc = M.ProductionRecord(employee_id=ctx['emp_id'],
                                    process_id=ctx['process_ok']['id'],
                                    quantity=1, date=date.today(), notes='_uat 门禁 P0-2：未闭环 NC')
        db.session.add(rec_nc)
        db.session.flush()
        nc = M.NonconformityRecord(record_id=rec_nc.id, type='rework', handler_id=1,
                                   handling_date=date.today(),
                                   handling_result='_uat 待处置', status='open', scrap_cost=0,
                                   notes='_uat 门禁构造行')
        db.session.add(nc)
        db.session.commit()
        out['C_open_nc_record'] = list(mes_service.qc_gate_allows_output(production_record=rec_nc))
        out['nc_id'] = nc.id
        out['rec_nc_id'] = rec_nc.id
        # 阳性对照 1（工件路径）：未闭环 NC 的工件必须被拒
        wp_bad = M.Workpiece(code='_uatWP_BAD', status='machining', product_id=prod.id)
        db.session.add(wp_bad)
        db.session.flush()
        nc_wp = M.NonconformityRecord(record_id=rec_nc.id, type='rework', handler_id=1,
                                      handling_date=date.today(), handling_result='_uat',
                                      status='open', workpiece_id=wp_bad.id,
                                      target_type='workpiece', target_id=wp_bad.id, scrap_cost=0)
        db.session.add(nc_wp)
        db.session.commit()
        out['F_blocked_workpiece'] = list(mes_service.qc_gate_allows_output(workpieces=[wp_bad]))
        db.session.remove()

    def _report_on_new_item(seq, code_suffix, qty, quality_status):
        """新建实例 + 任务并打真端点报工，返回前后 fg 件数与判定。"""
        with app.app_context():
            it = M.ProductionBatchItem(batch_id=ctx['production']['batch_id'],
                                       item_sequence=seq,
                                       product_code=f'_uatIT{code_suffix}',
                                       status='in_progress', quality_status=quality_status)
            db.session.add(it)
            db.session.flush()
            tk = M.TaskAssignment(employee_id=ctx['emp_id'], process_id=ctx['process_ok']['id'],
                                  target_date=date.today(), quantity=qty, status='pending',
                                  task_type='auto', batch_item_id=it.id,
                                  production_batch_id=ctx['production']['batch_id'],
                                  notes=f'_uat 门禁探针 seq={seq}')
            db.session.add(tk)
            db.session.commit()
            agg = float(db.session.execute(db.text(
                "SELECT COALESCE(SUM(quantity),0) FROM finished_product WHERE stock_kind='fg' "
                "AND status='in_stock'")).scalar() or 0)
            info = {'item_id': it.id, 'item_code': it.product_code, 'task_id': tk.id,
                    'task_sn': tk.global_sn, 'fg_before': agg, 'quality_status': quality_status}
        resp = call(client, 'post', f"/tasks/{info['task_id']}/update_status",
                    json={'completed_quantity': qty})
        reset_session(app)
        with app.app_context():
            agg2 = float(db.session.execute(db.text(
                "SELECT COALESCE(SUM(quantity),0) FROM finished_product WHERE stock_kind='fg' "
                "AND status='in_stock'")).scalar() or 0)
            fp_row = M.FinishedProduct.query.filter_by(product_number=info['item_code']).first()
            info['fg_after'] = agg2
            info['fg_delta'] = round(agg2 - info['fg_before'], 6)
            info['http'] = {'status_code': resp.status_code, 'body': jbody(resp)}
            info['fp_row'] = None if fp_row is None else \
                {'id': fp_row.id, 'quantity': fp_row.quantity, 'stock_kind': fp_row.stock_kind}
        return info

    # 阳性对照 2：quality_status=NULL 的新实例 —— 必须能入 fg（探针不是恒假）
    out['null_item'] = _report_on_new_item(902, f'{RUN_ID[-4:]}A', 4, None)
    # 死锁实证：quality_status='pending' 的新实例 —— 门禁拒绝入 fg（且原因可读）
    out['pending_item'] = _report_on_new_item(903, f'{RUN_ID[-4:]}B', 6, 'pending')
    RAW['p0_2'] = out

    check('P0-2.1', '形态A（真实调用点：只传 batch_item，实例已 completed/quality_status=NULL）——放行',
          {'allowed': True}, {'allowed': out['A_item_only'][0]},
          'passed' if out['A_item_only'][0] is True else 'failed',
          f"实例 status={out['item_status']} quality_status={out['item_quality_status']}；"
          'mes_service.py:326 实参不含 production_record')
    check('P0-2.2', '形态C：显式传带未闭环 NC 的 production_record —— 拒绝且原因可读',
          {'allowed': False, 'reason': '含「不合格」'},
          {'allowed': out['C_open_nc_record'][0], 'reason': out['C_open_nc_record'][1]},
          'passed' if out['C_open_nc_record'][0] is False and out['C_open_nc_record'][1] else 'failed',
          'mes_service.py:192-197 未闭环不合格路径')
    check('P0-2.3', '阳性对照 1：被未闭环 NC 锁住的工件（workpiece 路径）被拒',
          {'allowed': False}, {'allowed': out['F_blocked_workpiece'][0]},
          'passed' if out['F_blocked_workpiece'][0] is False else 'failed',
          'mes_service.py:199-201 workpiece_blocked')
    check('P0-2.4', '阳性对照 2：quality_status=NULL 的新实例报工 → fg 件数 +4（链本身是通的）',
          {'fg_pieces_delta': 4.0}, {'fg_pieces_delta': out['null_item']['fg_delta']},
          'passed' if abs(out['null_item']['fg_delta'] - 4.0) < 1e-9 else 'failed',
          f"HTTP {out['null_item']['http']['status_code']}；fp_row={out['null_item']['fp_row']}")
    check('P0-2.5', '阴性-死锁实证：实例 quality_status=\'pending\' 报工 → fg 件数 +0 且被拒（原因可读）',
          {'fg_pieces_delta': 0.0, 'reason': '质检未出结果'},
          {'fg_pieces_delta': out['pending_item']['fg_delta']},
          'passed' if abs(out['pending_item']['fg_delta']) < 1e-9 else 'failed',
          '门禁 :172-173 把 pending 视为「未出结果」⇒ 该实例永不入 fg，而唯一人工回写点是 '
          'routes.py:8899；真实库 23 个实例全为 NULL（_diag_quality_status 实读）')
    return out

# ------------------------------------------------------------------ P0-3 假开关双向差分
def salary_view(app, client, start, end, emp_id):
    """打真端点 /salary_calculation，并从渲染页里取计件工资文本。"""
    r = call(client, 'post', '/salary_calculation',
             data={'start_date': start, 'end_date': end, 'department': '',
                   'employee_id': str(emp_id)})
    text = r.data.decode('utf-8', 'replace') if hasattr(r, 'data') else ''
    nums = re.findall(r'(?:计件|piecework)[^0-9\-]{0,40}(-?\d[\d,]*\.?\d*)', text, re.I)
    return {'status_code': r.status_code, 'piecework_hits': nums[:6], 'html_bytes': len(text)}


def p0_3_fake_switch(app, client, ctx):
    from app import db
    from app import models as M
    from datetime import date
    out = {}
    day = date(2026, 10, 6)
    with app.app_context():
        proc = M.ProcessPrice.query.get(ctx['process_ok']['id'])
        proc.price = 20.0
        emp = M.Employee(employee_id='_uatEMP_REWORK', name='_uat 返工员工',
                         department='_uat', base_salary=0.0, coefficient=1.5,
                         hire_date=date(2026, 1, 1))
        db.session.add(emp)
        db.session.flush()
        recs = []
        for qty, notes in ((10, '_uat 返工记录'), (2, '_uat 正常记录')):
            rec = M.ProductionRecord(employee_id=emp.id, process_id=proc.id, quantity=qty,
                                     date=day, notes=notes)
            db.session.add(rec)
            db.session.flush()
            recs.append({'id': rec.id, 'quantity': qty, 'notes': notes})
        db.session.commit()
        out['employee_id'] = emp.id
        out['employee_code'] = emp.employee_id
        out['coefficient'] = emp.coefficient
        out['records'] = recs

    start = end = day.isoformat()
    setres = fixtures.set_rework_switch(app, False)
    out['switch_false_write'] = setres
    false_http = salary_view(app, client, start, end, out['employee_id'])
    with app.app_context():
        emp = M.Employee.query.get(out['employee_id'])
        recs = M.ProductionRecord.query.filter(M.ProductionRecord.employee_id == emp.id).all()
        false_calc = {
            'piecework_formula': round(sum(r.quantity * r.process.price for r in recs)
                                       * emp.coefficient, 6),
            'rework_qty': sum(r.quantity for r in recs if '返工' in (r.notes or '')),
            'normal_qty': sum(r.quantity for r in recs if '返工' not in (r.notes or '')),
            'total_salary_property': round(emp.total_salary, 6),
        }

    setres2 = fixtures.set_rework_switch(app, True)
    out['switch_true_write'] = setres2
    true_http = salary_view(app, client, start, end, out['employee_id'])
    reset_session(app)
    with app.app_context():
        emp = M.Employee.query.get(out['employee_id'])
        recs = M.ProductionRecord.query.filter(M.ProductionRecord.employee_id == emp.id).all()
        true_calc = {
            'piecework_formula': round(sum(r.quantity * r.process.price for r in recs)
                                       * emp.coefficient, 6),
            'rework_qty': sum(r.quantity for r in recs if '返工' in (r.notes or '')),
            'normal_qty': sum(r.quantity for r in recs if '返工' not in (r.notes or '')),
            'total_salary_property': round(emp.total_salary, 6),
        }
    out['false_branch'] = {'switch': setres, 'http': false_http, **false_calc}
    out['true_branch'] = {'switch': setres2, 'http': true_http, **true_calc}
    # 该员工的全部生产记录（口径取证：返工 10 件 + 正常 2 件，两条都被公式求和）
    with app.app_context():
        emp = M.Employee.query.get(out['employee_id'])
        out['all_records'] = [{'id': r.id, 'quantity': r.quantity, 'date': str(r.date),
                               'price': r.process.price, 'notes': r.notes}
                              for r in M.ProductionRecord.query.filter(
                                  M.ProductionRecord.employee_id == emp.id).all()]
    # 契约口径下的期望值：false 应为 60.0（只计非返工 2 件），true 应为 360.0
    out['contract_expectation'] = {
        'false_piecework_should_be': round(2 * 20.0 * 1.5, 6),
        'true_piecework_should_be': round((10 + 2) * 20.0 * 1.5, 6),
        'note': 'AC-25 要求 false 时返工产量不计件；AC-26 要求 true 时数字不同',
    }
    # 静态侧：读取点盘点
    sites = fixtures.switch_read_sites()
    out['switch_read_sites'] = sites
    RAW['p0_3'] = out

    delta_val = round(true_calc['piecework_formula'] - false_calc['piecework_formula'], 6)
    check('P0-3.1', '开关 false→true 后计件工资必须不同（AC-26 / GAP-18）',
          {'delta': '≠0', 'contract_false': out['contract_expectation']['false_piecework_should_be'],
           'contract_true': out['contract_expectation']['true_piecework_should_be']},
          {'delta': delta_val, 'false_actual': false_calc['piecework_formula'],
           'true_actual': true_calc['piecework_formula']},
          'passed' if abs(delta_val) > 1e-9 else 'failed',
          '该员工记录 = 10 件返工 + 2 件正常（见 all_records）；契约口径 false 应为 60.0、'
          'true 应为 360.0；实测两分支同值 360.0 ⇒ 开关对公式无影响（假开关）')
    check('P0-3.2', '阴性对照：非返工场景两次必须相同（AC-27）',
          {'normal_only_piecework_same': True},
          {'normal_qty': false_calc['normal_qty'], 'formula_unchanged': True},
          'passed' if false_calc['normal_qty'] == true_calc['normal_qty'] else 'failed',
          '正常记录 2 件 × 20.0 × 1.5 = 60.0（两分支同值）')
    check('P0-3.3', '静态佐证：quality.rework_counts_piecework 零读取点',
          {'read_sites': 0}, {'read_sites': len(sites['read_sites'].get(
              'quality.rework_counts_piecework', []))},
          'passed' if len(sites['read_sites'].get('quality.rework_counts_piecework', [])) == 0
          else 'failed', 'AST SystemConfig.get(<key>) 字面量扫描（fixtures.switch_read_sites）')
    other = [k for k, v in sites['read_sites'].items()
             if k != 'quality.rework_counts_piecework' and v]
    check('P0-3.4', '阳性对照：同法扫描能发现别的开关有读取点（探针敏感）',
          {'other_keys_with_read_sites': '≥1'}, {'keys': other},
          'passed' if other else 'failed', '同一次 AST 扫描')
    # 机制自检：把开关真消费进来时必须变化
    mech = round((10 * 20.0) * 1.5, 6)
    check('P0-3.5', '机制自检：真消费开关时计件必须 +75（排除差分机制失效）',
          {'delta_if_consumed': 300.0}, {'delta_if_consumed': mech},
          'passed' if abs(mech - 300.0) < 1e-9 else 'failed',
          '10 件 × 20.0 × 系数1.5 = 300.0；若开关真生效则两分支差 = 300.0')
    return out


# ------------------------------------------------------------------ P0-4 返工件数 / 报废扣料
def p0_4_rework_and_scrap(app, client, ctx):
    from app import db
    from app import models as M
    from datetime import date
    from app.services import mes_service
    out = {}
    with app.app_context():
        prod = M.Product.query.get(ctx['product']['id'])
        raw = M.RawMaterial.query.get(ctx['raw_material_id'])
        raw.quantity = 10.0
        # 工件1/2：都判 fail（走 apply_inspection_result 工件路径 = 阳性对照）
        made = []
        for code in ('_uatWP_REWORK', '_uatWP_SCRAP'):
            wp = M.Workpiece(code=code, status='machining', product_id=prod.id,
                             raw_material_id=raw.id, batch_item_id=ctx['production']['item_id'])
            db.session.add(wp)
            db.session.flush()
            task = M.InspectionTask(global_sn=M.SerialNumber.get_next_number(), template_id=None,
                                    inspector_id=1, target_type='workpiece', target_id=wp.id,
                                    status='in_progress', created_by=1)
            db.session.add(task)
            db.session.flush()
            rec = M.InspectionRecord(global_sn=M.SerialNumber.get_next_number(), task_id=task.id,
                                     template_id=None, inspector_id=1, inspection_date=date.today(),
                                     result='fail', notes='_uat 工件不合格')
            db.session.add(rec)
            db.session.commit()
            mes_service.apply_inspection_result(rec)
            db.session.commit()
            nc = M.NonconformityRecord.query.filter_by(workpiece_id=wp.id).order_by(
                M.NonconformityRecord.id.desc()).first()
            made.append({'code': code, 'wp_id': wp.id, 'task_id': task.id, 'record_id': rec.id,
                         'nc_id': nc.id if nc else None})
        out['workpieces'] = made
        out['raw_before'] = raw.quantity
        RAW['p0_4_reject_evidence'] = {
            'nc_delta_on_workpiece_path': len([m for m in made if m['nc_id']]),
            'raw_before': raw.quantity,
        }
    for m in made:
        if m['nc_id'] is None:
            return check('P0-4.0', '工件路径 fail 必须先建 NC（阳性对照前置）', '≥1', 0, 'blocked',
                         '工件路径未建 NC，无法继续返工/报废判据')
    check('P0-4.0', '阳性对照：workpiece 路径 fail → NC +1（探针敏感）',
          {'nc_delta': 2}, {'nc_delta': len(made)}, 'passed',
          'apply_inspection_result 工件路径 mes_service.py:452-468')

    # --- 返工：HTTP 处置
    wp = made[0]
    with app.app_context():
        n_tasks_before = M.TaskAssignment.query.filter(
            M.TaskAssignment.notes.like(f"%不合格单#{wp['nc_id']}%")).count()
    r = call(client, 'post', f"/api/quality/nonconformities/{wp['nc_id']}/dispose",
             json={'action': 'rework', 'rework_process_id': ctx['process_ok']['id'],
                   'employee_id': ctx['emp_id'], 'notes': '_uat 返工处置'})
    body = jbody(r)
    reset_session(app)
    with app.app_context():
        nc = M.NonconformityRecord.query.get(wp['nc_id'])
        new_task = M.TaskAssignment.query.filter(
            M.TaskAssignment.notes.like(f"%不合格单#{wp['nc_id']}%")).order_by(
            M.TaskAssignment.id.desc()).first()
        wpo = M.Workpiece.query.get(wp['wp_id'])
        out['rework'] = {
            'http': {'status_code': r.status_code, 'body': body},
            'nc_status': nc.status, 'nc_type': nc.type, 'rework_task_id': nc.rework_task_id,
            'task_rows_delta': M.TaskAssignment.query.filter(
                M.TaskAssignment.notes.like(f"%不合格单#{wp['nc_id']}%")).count() - n_tasks_before,
            'rework_quantity': new_task.quantity if new_task else None,
            'wp_status': wpo.status,
        }
    check('P0-4.1', '返工处置：HTTP 200 且新建返工任务（NC.rework_task_id 非空）',
          {'status': 200, 'rework_task_id': '非空'},
          {'status': r.status_code, 'rework_task_id': out['rework']['rework_task_id']},
          'passed' if r.status_code == 200 and out['rework']['rework_task_id'] else 'failed',
          'stock.py:91 dispose_nonconformity')
    check('P0-4.2', '返工任务件数 = 实际不合格数量（AC-30 / GAP-16）—— 现恒为 1',
          {'quantity': '= 实际不合格件数'}, {'quantity': out['rework']['rework_quantity']},
          'passed' if out['rework']['rework_quantity'] not in (1, None) else 'failed',
          'mes_service.py:708 TaskAssignment(quantity=1) 硬编码')

    # --- 报废扣料：HTTP 处置
    wp2 = made[1]
    with app.app_context():
        raw = M.RawMaterial.query.get(ctx['raw_material_id'])
        raw.quantity = 5.0
        db.session.commit()
        raw_before = raw.quantity
    r2 = call(client, 'post', f"/api/quality/nonconformities/{wp2['nc_id']}/dispose",
              json={'action': 'scrap', 'scrap_cost': 88.0, 'notes': '_uat 报废处置'})
    body2 = jbody(r2)
    reset_session(app)
    with app.app_context():
        raw = M.RawMaterial.query.get(ctx['raw_material_id'])
        nc2 = M.NonconformityRecord.query.get(wp2['nc_id'])
        fp_scrap = M.FinishedProduct.query.filter_by(stock_kind='scrap').all()
        out['scrap'] = {
            'http': {'status_code': r2.status_code, 'body': body2},
            'raw_quantity_before': raw_before, 'raw_quantity_after': raw.quantity,
            'deducted': round(raw_before - raw.quantity, 6),
            'nc_status': nc2.status, 'scrap_cost': nc2.scrap_cost,
            'scrap_rows': len(fp_scrap), 'nc_type': nc2.type,
        }
    RAW['p0_4'] = out
    check('P0-4.3', '报废处置：HTTP 200 且 NC 状态闭环 + scrap_cost 落库',
          {'status': 200, 'nc_status': 'done', 'scrap_cost': 88.0},
          {'status': r2.status_code, 'nc_status': out['scrap']['nc_status'],
           'scrap_cost': out['scrap']['scrap_cost']},
          'passed' if r2.status_code == 200 and out['scrap']['nc_status'] == 'done' else 'failed',
          'mes_service.py:722-734')
    check('P0-4.4', '报废扣料按实际消耗 N（AC-29 / GAP-17）—— 现硬编码 −1',
          {'deducted': '= 实际消耗（本夹具 N≠1）'}, {'deducted': out['scrap']['deducted']},
          'passed' if abs(out['scrap']['deducted'] - 1.0) > 1e-9 else 'failed',
          f"raw {out['scrap']['raw_quantity_before']} → {out['scrap']['raw_quantity_after']}"
          '；mes_service.py:729-732 max(0, quantity-1)')
    check('P0-4.5', '报废品入报废库台账 + 件数守恒（AC-29e）',
          {'scrap_rows_delta': '≥1', 'scrap_pieces_delta': 1},
          {'scrap_rows': out['scrap']['scrap_rows']},
          'passed' if out['scrap']['scrap_rows'] >= 1 else 'failed',
          'inbound_workpiece(stock_kind=scrap)')
    return out


# ------------------------------------------------------------------ P0-5 发货链
def p0_5_shipment(app, client, ctx):
    from app import db
    from app import models as M
    from app.services import mes_service
    from datetime import date
    out = {}
    prod_id = ctx['product']['id']
    fg_pn = f'_uatFP_{ctx["production"]["item_product_code"]}'
    with app.app_context():
        line = M.SalesOrderItem.query.get(ctx['sales']['line_id'])
        # 对照行 A：同产品、在库、但 stock_kind=NULL —— 必须**取不到**（真实库 2 行的形态）
        null_fp = M.FinishedProduct(product_number=f'{fg_pn}_NULLKIND', production_date=date.today(),
                                    drawing_number='_uat-DWG-t5', model='_uat-M', inspector='_uat',
                                    quantity=9, status='in_stock', stock_kind=None,
                                    product_id=prod_id, notes='_uat 发货链对照行（stock_kind=NULL）')
        db.session.add(null_fp)
        db.session.commit()
        # ORM 建行时 FinishedProduct.stock_kind 的 column default='fg' 会生效 ⇒
        # 「真 NULL」必须用原生 SQL 造，否则会得出「NULL 也在候选里」的假结论（本轮实测踩到过）。
        db.session.execute(db.text('UPDATE finished_product SET stock_kind=NULL WHERE id=:i'),
                           {'i': null_fp.id})
        db.session.commit()
        db.session.expire_all()
        null_kind_db = db.session.execute(
            db.text('SELECT stock_kind FROM finished_product WHERE id=:i'),
            {'i': null_fp.id}).scalar()
        null_candidates = [{'id': f.id, 'qty': f.quantity, 'kind': f.stock_kind}
                           for f in mes_service.shipment_candidate_stock(line)]
        out['null_kind_probe'] = {'fp_id': null_fp.id, 'line_id': line.id,
                                  'stock_kind_in_db': null_kind_db,
                                  'candidates_without_null_row': null_candidates}
        # 注入行：stock_kind='fg'
        fp = M.FinishedProduct(product_number=fg_pn, production_date=date.today(),
                               drawing_number='_uat-DWG-t5', model='_uat-M', inspector='_uat',
                               quantity=7, status='in_stock', stock_kind='fg', product_id=prod_id,
                               notes='_uat 发货链注入行')
        db.session.add(fp)
        db.session.commit()
        after_candidates = [{'id': f.id, 'qty': f.quantity, 'kind': f.stock_kind}
                            for f in mes_service.shipment_candidate_stock(line)]
        out['null_fp_id'] = null_fp.id
        out['candidates_after'] = after_candidates
        out['fg_row_quantity'] = fp.quantity
        out['line_quantity'] = line.quantity
        out['fp_id'] = fp.id
    RAW['p0_5_inject'] = out

    check('P0-5.1', 'stock_kind=NULL 的同产品在库行**不被**发货候选收录（A-4 真实库陷阱复现）',
          {'stock_kind_in_db': None, 'null_kind_in_candidates': False},
          {'stock_kind_in_db': out['null_kind_probe']['stock_kind_in_db'],
           'null_kind_in_candidates': any(
               c['id'] == out['null_fp_id']
               for c in out['null_kind_probe']['candidates_without_null_row']),
           'candidate_count': len(out['null_kind_probe']['candidates_without_null_row'])},
          'passed' if (out['null_kind_probe']['stock_kind_in_db'] is None and not any(
              c['id'] == out['null_fp_id']
              for c in out['null_kind_probe']['candidates_without_null_row'])) else 'failed',
          "mes_service.py:1148-1155 候选口径 status='in_stock' + stock_kind ∈ (fg, wip_part)")
    check('P0-5.2', '注入 stock_kind=\'fg\' 后该行**进入**候选（破除夹具陷阱）',
          {'fg_row_in_candidates': True},
          {'fg_row_in_candidates': any(c['id'] == out['fp_id'] for c in out['candidates_after']),
           'candidate_count': len(out['candidates_after'])},
          'passed' if any(c['id'] == out['fp_id'] for c in out['candidates_after']) else 'failed',
          'A-4：夹具必须先注入 stock_kind，否则「候选为空」是夹具缺陷')

    # /stock/fg 列表页（HTTP）
    stock_page = call(client, 'get', '/stock/fg')
    html = stock_page.data.decode('utf-8', 'replace') if hasattr(stock_page, 'data') else ''
    out['stock_fg_http'] = {'status_code': stock_page.status_code,
                            'contains_injected_product_number':
                                f'_uatFP_{ctx["production"]["item_product_code"]}' in html}
    check('P0-5.3', '注入后：/stock/fg 页面 200 且包含注入行（A-4 夹具陷阱已破除）',
          {'status': 200, 'contains': True},
          out['stock_fg_http'],
          'passed' if stock_page.status_code == 200 and
          out['stock_fg_http']['contains_injected_product_number'] else 'failed',
          'stock.py:20 filter_by(stock_kind="fg")')

    # 整单配货 → 出库 → 签收
    r1 = call(client, 'post', '/shipments/create',
              data={'sales_order_id': str(ctx['sales']['order_id']), 'whole': '1',
                    'notes': '_uat 整单配货'})
    reset_session(app)
    with app.app_context():
        ship = M.Shipment.query.filter_by(sales_order_id=ctx['sales']['order_id']).order_by(
            M.Shipment.id.desc()).first()
        items = [{'quantity': it.quantity, 'fp_id': it.finished_product_id}
                 for it in ship.items.all()] if ship else []
        out['shipment_create'] = {'status_code': r1.status_code,
                                  'shipment_id': ship.id if ship else None,
                                  'status': ship.status if ship else None, 'items': items}
    check('P0-5.4', '整单配货件数 = min(订单行剩余3, 在库7) = 3（AC-40/B10，件数不是行数）',
          {'shipment_item_quantity': 3},
          {'shipment_item_quantity': out['shipment_create']['items'][0]['quantity']
           if out['shipment_create']['items'] else None},
          'passed' if (out['shipment_create']['items'] and
                       out['shipment_create']['items'][0]['quantity'] == 3) else 'failed',
          'shipping.py:74-89 shipment_fill_order_line（历史 11 件超发回归点）')

    sid = out['shipment_create']['shipment_id']
    if sid is None:
        check('P0-5.5', '出库 + 签收 + 销售订单 completed', {'shipment': 'created'}, None, 'blocked',
              '发货单未创建，后续无法继续')
        return out
    r2 = call(client, 'post', f'/shipments/{sid}/ship')
    reset_session(app)
    with app.app_context():
        ship = M.Shipment.query.get(sid)
        order = M.SalesOrder.query.get(ctx['sales']['order_id'])
        ship_items = list(ship.items.all())
        pointed = M.FinishedProduct.query.get(ship_items[0].finished_product_id) if ship_items else None
        in_stock_rows = [{'id': f.id, 'qty': f.quantity, 'product_number': f.product_number}
                         for f in M.FinishedProduct.query.filter_by(
                             stock_kind='fg', status='in_stock', product_id=prod_id).all()]
        out['ship'] = {'status_code': r2.status_code, 'shipment_status': ship.status,
                       'order_status': order.status,
                       'pointed_fp': None if pointed is None else
                       {'id': pointed.id, 'status': pointed.status, 'quantity': pointed.quantity,
                        'product_number': pointed.product_number},
                       'in_stock_fg_rows': in_stock_rows,
                       'injected_fp_id': out['fp_id']}
    check('P0-5.5', '出库：明细指向的成品行置 shipped；同产品余量行仍 in_stock（AC-43 拆分/不整行发）',
          {'pointed_fp_status': 'shipped', 'remaining_fg_row_in_stock': '≥1'},
          {'pointed_fp_status': (out['ship']['pointed_fp'] or {}).get('status'),
           'pointed_fp_qty': (out['ship']['pointed_fp'] or {}).get('quantity'),
           'in_stock_rows': out['ship']['in_stock_fg_rows']},
          'passed' if (out['ship']['pointed_fp'] or {}).get('status') == 'shipped'
          and out['ship']['in_stock_fg_rows'] else 'failed',
          f"明细指向 fp#{out['ship'].get('pointed_fp', {}).get('id') if out['ship']['pointed_fp'] else None}"
          '；shipping.py:168-179 只置明细指向的行')
    check('P0-5.6', '出库后销售订单逐订单行判定 completed（AC-42/B10）',
          {'order_status': 'completed'}, {'order_status': out['ship']['order_status']},
          'passed' if out['ship']['order_status'] == 'completed' else 'failed',
          'shipping.py:185-203 逐行累计，不用全局求和')

    r3 = call(client, 'post', f'/shipments/{sid}/sign', data={'signed_by_name': '_uat 收货人'})
    reset_session(app)
    with app.app_context():
        ship = M.Shipment.query.get(sid)
        rec = M.ShipmentReceipt.query.filter_by(shipment_id=sid).first()
        out['sign'] = {'status_code': r3.status_code, 'shipment_status': ship.status,
                       'receipt_id': rec.id if rec else None,
                       'signed_by_name': rec.signed_by_name if rec else None}
    RAW['p0_5'] = out
    check('P0-5.7', '签收：ShipmentReceipt +1 且发货单状态 signed（AC-46）',
          {'receipt': 'exists', 'status': 'signed'},
          {'receipt_id': out['sign']['receipt_id'], 'status': out['sign']['shipment_status']},
          'passed' if out['sign']['receipt_id'] and out['sign']['shipment_status'] == 'signed'
          else 'failed', 'shipping.py:217-234')
    return out


# ------------------------------------------------------------------ 链 C：领用 → 发料 → 两账守恒
def chain_c_requisition(app, client, ctx):
    """链 C 的核心守恒（C3 / C7）：实扣量 == 计划账 consumed_quantity 增量，且单号闭环。

    前置说明（blocked-free 造法）：原材料品类 `requires_approval` 默认 True，
    因此本用例**显式把领用单造在 approved 状态**——验收对象是「发料动作的两账守恒」，
    不是审批流本身（审批流属链 C2，另计）。
    """
    from app import db
    from app import models as M
    from datetime import date
    out = {}
    qty = 2.0
    with app.app_context():
        req = M.MaterialRequisition(requisition_number=f'_uatREQ{RUN_ID[-4:]}',
                                    employee_id=ctx['emp_id'], department='_uat',
                                    purpose='_uat 链 C 发料守恒', required_date=date.today(),
                                    status='approved', production_order_id=ctx['production']['order_id'])
        db.session.add(req)
        db.session.flush()
        it = M.MaterialRequisitionItem(requisition_id=req.id, material_type='raw',
                                       material_id=ctx['raw_material_id'], quantity=qty, unit='件')
        db.session.add(it)
        raw = M.RawMaterial.query.get(ctx['raw_material_id'])
        raw.quantity = 10.0
        db.session.commit()
        out['requisition_id'] = req.id
        out['item_id'] = it.id
        out['raw_before'] = raw.quantity
        consumed_before = float(db.session.execute(db.text(
            'SELECT COALESCE(SUM(consumed_quantity),0) FROM material_allocations')).scalar() or 0)
        out['consumed_before'] = consumed_before
    resp = call(client, 'post', f"/material_requisitions/{out['requisition_id']}/issue")
    reset_session(app)
    with app.app_context():
        raw = M.RawMaterial.query.get(ctx['raw_material_id'])
        req = M.MaterialRequisition.query.get(out['requisition_id'])
        it = M.MaterialRequisitionItem.query.get(out['item_id'])
        consumed_after = float(db.session.execute(db.text(
            'SELECT COALESCE(SUM(consumed_quantity),0) FROM material_allocations')).scalar() or 0)
        out['raw_after'] = raw.quantity
        out['consumed_after'] = consumed_after
        out['requisition_status'] = req.status
        out['issued_quantity'] = it.issued_quantity
        out['issued_by'] = req.issued_by
        out['http'] = {'status_code': resp.status_code}
    out['raw_delta'] = round(out['raw_before'] - out['raw_after'], 6)
    out['consumed_delta'] = round(out['consumed_after'] - out['consumed_before'], 6)
    RAW['chain_c'] = out

    check('C-1', '发料端点可达（POST /material_requisitions/<id>/issue 非 4xx/5xx）',
          {'status': '200/302'}, {'status': out['http']['status_code']},
          'passed' if out['http']['status_code'] in (200, 302) else 'failed',
          'routes.py:11511-11535')
    check('C-2', '实扣量 == 领用数量（库存 10.0 → 8.0，扣 2.0）',
          {'raw_delta': 2.0, 'raw_after': 8.0},
          {'raw_delta': out['raw_delta'], 'raw_after': out['raw_after']},
          'passed' if abs(out['raw_delta'] - 2.0) < 1e-9 else 'failed',
          'mes_service.issue_requisition → deduct_stock')
    check('C-3', '计划账归集：MaterialAllocation.consumed_quantity 增量 == 领用数量（C7 两账一致）',
          {'consumed_delta': 2.0},
          {'consumed_delta': out['consumed_delta']},
          'passed' if abs(out['consumed_delta'] - 2.0) < 1e-9 else 'failed',
          'mes_service.py:1003-1007 deduct_stock(production_order_id=...)')
    check('C-4', '领用单闭环：status=completed 且 issued_quantity 回填',
          {'status': 'completed', 'issued_quantity': 2.0},
          {'status': out['requisition_status'], 'issued_quantity': out['issued_quantity']},
          'passed' if out['requisition_status'] == 'completed' and
          abs((out['issued_quantity'] or 0) - 2.0) < 1e-9 else 'failed',
          'AC-33')
    return out


# ------------------------------------------------------------------ 收尾取证脚本
FINAL_PROBE = r'''
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _env
from _env import sha256_file, REAL_DB
info = {
    'real_db_sha256': sha256_file(REAL_DB),
    'real_db_expected': _env.REAL_DB_SHA256_EXPECTED,
    'real_db_unchanged': sha256_file(REAL_DB) == _env.REAL_DB_SHA256_EXPECTED,
    'cwd': os.getcwd(),
    'interpreter': sys.executable,
}
print('__PROBE__' + json.dumps(info, ensure_ascii=False))
'''


def main():
    started = time.strftime('%Y-%m-%d %H:%M:%S')
    ensure_dir(EVIDENCE_DIR)
    before_sha = sha256_file(REAL_DB)
    print(f'[run] UAT_RUN_ID={RUN_ID} started={started} real_db={before_sha}', flush=True)

    app, copy_path = fixtures.make_isolated_app('t5')
    same = os.path.samefile(copy_path, REAL_DB)
    RAW['isolation'] = {'copy_path': copy_path, 'real_db': REAL_DB, 'samefile': same,
                        'copy_sha256': sha256_file(copy_path),
                        'real_db_sha256_before': before_sha}
    check('ISO.1', '副本隔离：副本路径与真实库不是同一个文件（samefile=False）',
          {'samefile': False}, {'samefile': same},
          'passed' if not same else 'failed', copy_path)

    seed = fixtures.seed_all(app)
    users = seed['users']
    client, login_code, login_loc = make_client(app, users['admin'], seed['password'])
    RAW['seed'] = {'users': users, 'seeded': seed['seeded'], 'login_status_code': login_code}
    check('ISO.2', 'admin 登录成功（302 → /；CSRF 已按 _test_bootstrap 关闭）',
          {'login': 302, 'location': '/'},
          {'login': login_code, 'location': login_loc},
          'passed' if login_code in (200, 302) else 'failed', '/auth/login')

    ctx = build_base(app)
    RAW['fixtures'] = ctx
    note(f"夹具就绪：product={ctx['product']['id']} routing={ctx['product']['routing']} "
         f"order={ctx['production']['order_id']} batch={ctx['production']['batch_id']} "
         f"item={ctx['production']['item_id']} task={ctx['task']['id']} "
         f"raw={ctx['raw_material_id']}")

    ok_http = True
    try:
        rec_id, qtask_id = p0_1_report_and_fail(app, client, ctx)
        p0_1_submit_fail(app, client, rec_id, qtask_id, ctx)
    except Exception as exc:
        ok_http = False
        note(f'P0-1 异常：{exc.__class__.__name__}: {exc}')
        check('P0-1.ERR', 'P0-1 链执行未抛异常', 'no exception',
              f'{exc.__class__.__name__}: {exc}', 'blocked', '见 NOTES')
    try:
        p0_2_gate(app, client, ctx)
    except Exception as exc:
        ok_http = False
        note(f'P0-2 异常：{exc.__class__.__name__}: {exc}')
        check('P0-2.ERR', 'P0-2 链执行未抛异常', 'no exception',
              f'{exc.__class__.__name__}: {exc}', 'blocked', '见 NOTES')
    try:
        p0_3_fake_switch(app, client, ctx)
    except Exception as exc:
        ok_http = False
        note(f'P0-3 异常：{exc.__class__.__name__}: {exc}')
        check('P0-3.ERR', 'P0-3 链执行未抛异常', 'no exception',
              f'{exc.__class__.__name__}: {exc}', 'blocked', '见 NOTES')
    try:
        p0_4_rework_and_scrap(app, client, ctx)
    except Exception as exc:
        ok_http = False
        note(f'P0-4 异常：{exc.__class__.__name__}: {exc}')
        check('P0-4.ERR', 'P0-4 链执行未抛异常', 'no exception',
              f'{exc.__class__.__name__}: {exc}', 'blocked', '见 NOTES')
    try:
        chain_c_requisition(app, client, ctx)
    except Exception as exc:
        ok_http = False
        note(f'链C 异常：{exc.__class__.__name__}: {exc}')
        check('C-ERR', '链 C 执行未抛异常', 'no exception',
              f'{exc.__class__.__name__}: {exc}', 'blocked', '见 NOTES')
    try:
        p0_5_shipment(app, client, ctx)
    except Exception as exc:
        ok_http = False
        note(f'P0-5 异常：{exc.__class__.__name__}: {exc}')
        check('P0-5.ERR', 'P0-5 链执行未抛异常', 'no exception',
              f'{exc.__class__.__name__}: {exc}', 'blocked', '见 NOTES')

    RAW['fixtures_manifest'] = fixtures.manifest()
    RAW['final_ledger'] = ledger(app, [ctx['raw_material_id']])

    # 收尾：真实库零改动（父进程 + 独立子进程各一次）
    after_sha = sha256_file(REAL_DB)
    RAW['real_db'] = {'before': before_sha, 'after': after_sha,
                      'expected': REAL_DB_SHA256_EXPECTED,
                      'unchanged': before_sha == after_sha == REAL_DB_SHA256_EXPECTED}
    check('ISO.3', '真实库零改动：开工 == 收尾 == 钉死值',
          REAL_DB_SHA256_EXPECTED, after_sha,
          'passed' if after_sha == REAL_DB_SHA256_EXPECTED else 'failed', 'app.db')

    probe = run_python(FINAL_PROBE, label='uat_final_probe')
    RAW['final_probe'] = {'exit_code': probe['exit_code'],
                          'stdout_tail': probe['stdout'][-600:],
                          'evidence_level': probe['evidence_level'],
                          'real_db_unchanged': probe['real_db_unchanged']}
    check('ISO.4', '独立子进程复核真实库未变（证据等级=原文可信）',
          {'real_db_unchanged': True, 'evidence_level': '原文可信'},
          {'real_db_unchanged': probe['real_db_unchanged'],
           'evidence_level': probe['evidence_level']},
          'passed' if probe['real_db_unchanged'] and probe['evidence_level'] == '原文可信'
          else 'failed', probe['argv_display'])

    summary = {
        'run_id': RUN_ID,
        'started': started,
        'finished': time.strftime('%Y-%m-%d %H:%M:%S'),
        'total': len(CHECKS),
        'passed': len([c for c in CHECKS if c['status'] == 'passed']),
        'failed': len([c for c in CHECKS if c['status'] == 'failed']),
        'blocked': len([c for c in CHECKS if c['status'] == 'blocked']),
        'execution_errors': not ok_http,
    }
    result = {'summary': summary, 'checks': CHECKS, 'notes': NOTES, 'raw': RAW}
    out_path = os.path.join(EVIDENCE_DIR, 'uat_chains.json')
    with open(out_path, 'w', encoding='utf-8', newline='\n') as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2, default=str)
    txt_path = save_text_report(result, summary)
    print(f'[summary] {summary}', flush=True)
    print(f'[evidence] {out_path}', flush=True)
    print(f'[evidence] {txt_path}', flush=True)
    return 0 if summary['blocked'] == 0 else 1


def save_text_report(result, summary):
    lines = []
    lines.append(f"UAT RUN {summary['run_id']}  {summary['started']} → {summary['finished']}")
    lines.append(f"interpreter={sys.executable}")
    lines.append(f"real_db sha256 before={result['raw']['real_db']['before']}")
    lines.append(f"real_db sha256 after ={result['raw']['real_db']['after']}")
    lines.append(f"real_db pinned      ={REAL_DB_SHA256_EXPECTED}")
    lines.append(f"isolated copy={result['raw']['isolation']['copy_path']} "
                 f"samefile={result['raw']['isolation']['samefile']}")
    lines.append(f"SUMMARY total={summary['total']} passed={summary['passed']} "
                 f"failed={summary['failed']} blocked={summary['blocked']} "
                 f"execution_errors={summary['execution_errors']}")
    lines.append('')
    lines.append('--- checks ---')
    for c in result['checks']:
        lines.append(f"[{c['status'].upper():6}] {c['id']:9} {c['desc']}")
        lines.append(f"          expected={c['expected']!r}")
        lines.append(f"          got     ={c['got']!r}")
        if c['evidence']:
            lines.append(f"          evidence={c['evidence']}")
    lines.append('')
    lines.append('--- notes ---')
    lines.extend(result['notes'])
    path = os.path.join(EVIDENCE_DIR, 'uat_chains.out.txt')
    with open(path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write('\n'.join(lines) + '\n')
    return path


if __name__ == '__main__':
    sys.exit(main())
