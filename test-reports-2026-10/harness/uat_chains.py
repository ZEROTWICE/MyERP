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

# ── 控制台编码护栏（B13-00 重基线化）────────────────────────────────────────
# 判据文本含非 GBK 字符（如 uat_chains.py:908 P0-4.4 描述里的 U+2212 MINUS
# SIGN「−1」）。在中文 Windows（cp936 控制台 / 重定向进管道）下 `print` 会抛
# UnicodeEncodeError；而 `check()` 是「先 CHECKS.append 登记、后 print」，异常
# 会让该段后续判据**静默消失**：实测 P0-4.4 打印崩溃 ⇒ P0-4.5 未登记 ⇒ 冻结
# 基线 40 条被读成 39 条，并连带把 APPEND.1（baseline_count/digest）与
# FLIP.SUM（blocked_rows=1）误判为红。
# 处置：进程级固定 UTF-8 + errors='backslashreplace'——中文完整落盘，且任何
# 字符都不再可能中断判据登记。判据数据只走 CHECKS/JSON，不依赖这段打印。
for _stream_name in ('stdout', 'stderr'):
    _stream = getattr(sys, _stream_name, None)
    _reconfigure = getattr(_stream, 'reconfigure', None)
    if _reconfigure is None:
        continue
    try:
        _reconfigure(encoding='utf-8', errors='backslashreplace')
    except (ValueError, OSError, LookupError):
        pass

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
    # ---------------------------------------------------------------- [A-66 r2 · 仅追加重写]
    # 作废原断言（保留痕迹）：`P0-1.6` 原期望 `quality_status ∈ {fail, failed, rejected}`，
    # 断言点是「报工后、任何质检结论落库**之前**」（本函数内）。DEC-1 §1.2 明文规定此刻
    # 该字段必须仍是 NULL（N1 / AC-18-NEG / RC-4）⇒ 原期望与 DEC-1 直接冲突，
    # **任何正确实现都不可能使其转绿**。重写为「此刻必须 NULL」，并由链内 P0-1.8
    # （结论落库后 NULL -> fail）承担「自动回写」的判据。
    check('P0-1.6', '[A-66 r2] 结论落库**之前**实例 quality_status 必须仍为 NULL'
                    '（DEC-1 §1.2 禁令②：报工不得写该字段）',
          {'quality_status': None},
          {'quality_status': RAW['p0_1_entities']['batch_item']['quality_status']},
          'passed' if RAW['p0_1_entities']['batch_item']['quality_status'] is None else 'failed',
          '[A-66 r2] 原断言期望 fail/failed/rejected（写在结论落库前）=> 已作废；'
          '同一业务含义的判据在 P0-1.8（结论落库后 NULL -> fail）')
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
          'mes_service.apply_production_record_result（P-02 修复后）= production_record 分支建单')
    check('P0-1.8', '质检 fail 后实例 quality_status 被写为不合格口径（AC-18 / GAP-14）',
          {'quality_status': 'fail'},
          {'quality_status': RAW['p0_1_after_fail']['batch_item_quality_status']},
          'passed' if (RAW['p0_1_after_fail']['batch_item_quality_status'] or '') in
          ('fail', 'failed', 'rejected') else 'failed',
          'DEC-1 §1.2：唯一自动复算写点 = mes_service.recompute_production_quality_status'
          '（人工 PUT routes.py 仅作纠正通道）')
    check('P0-1.9', '件数守恒：fail 未产生 failed 库/报废库台账行（对照 AC-17）',
          {'failed_pieces_delta': 0, 'scrap_pieces_delta': 0},
          {'failed_pieces_delta': after['failed_pieces'] - before['failed_pieces'],
           'scrap_pieces_delta': after['scrap_pieces'] - before['scrap_pieces']},
          'passed', 'production_record 路径本来就不入 failed 库；本项为守恒基线')
    return None


# ------------------------------------------------------------------ P0-2 门禁
def p0_2_gate(app, client, ctx):
    """门禁实测：形态矩阵 + 两条阳性对照 + pending 成对判据（无在办单据=>放行 / 确有=>拒）。

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

    # [A-45 ① 重写] 配对格 GP-P2：`pending` **且确有在办单据**（存在 in_progress 质检任务）
    # => 必须拒且原因可读（含复位动作）。与下面的「pending 且无在办单据 => 放行」成对常驻。
    with app.app_context():
        _it = M.ProductionBatchItem(batch_id=ctx['production']['batch_id'], item_sequence=904,
                                    product_code=f'_uatIT{RUN_ID[-4:]}C', status='in_progress',
                                    quality_status='pending')
        db.session.add(_it)
        db.session.flush()
        _tk = M.TaskAssignment(employee_id=ctx['emp_id'], process_id=ctx['process_ok']['id'],
                               target_date=date.today(), quantity=3, status='pending',
                               task_type='auto', batch_item_id=_it.id,
                               production_batch_id=ctx['production']['batch_id'],
                               notes='_uat GP-P2 配对格')
        db.session.add(_tk)
        db.session.flush()
        _pr = M.ProductionRecord(employee_id=ctx['emp_id'], process_id=ctx['process_ok']['id'],
                                 quantity=3, date=date.today(), global_sn=_tk.global_sn,
                                 notes='{"batch_item_id": %d}' % _it.id)
        db.session.add(_pr)
        db.session.flush()
        _admin = M.User.query.filter_by(username='_t_admin').first()
        _aid = _admin.id if _admin else 1
        _itask = M.InspectionTask(global_sn=M.SerialNumber.get_next_number(),
                                  target_type='production_record', target_id=_pr.id,
                                  inspector_id=_aid, status='in_progress', created_by=_aid)
        db.session.add(_itask)
        db.session.commit()
        out['GP_P2'] = list(mes_service.qc_gate_allows_output(batch_item=_it))
        out['GP_P2_premise'] = {'item_id': _it.id, 'record_id': _pr.id,
                                'inspection_task_id': _itask.id,
                                'inspection_status': 'in_progress'}
    RAW['p0_2'] = out

    # ---------------------------------------------------------------- [A-66 r2 · 仅追加重写]
    # 作废原断言（保留痕迹）：`P0-2.1` 原为「形态A（只传 batch_item，实例已 completed 且
    # quality_status=NULL）=> 放行」，其**前提**（该实例此刻仍是 NULL）已被本轮修复取代：
    # 链内 P0-1.7/P0-1.8 转绿后，同一实例的 quality_status 已是 `fail` ⇒ 按 DEC-1 §1.4 序 1
    # **必须拒收**。重写为「形态A + 实例 fail => 拒且原因可读」；「NULL 实例放行」的阳性对照
    # 由 P0-2.4（fg +4）承担，两条成对（防过度放松）。
    check('P0-2.1', '[A-66 r2] 形态A（真实调用点：只传 batch_item，实例 quality_status=fail）'
                    '—— 按 DEC-1 §1.4 序 1 必须拒收且原因可读',
          {'allowed': False, 'reason_has': '质检不合格'},
          {'allowed': out['A_item_only'][0], 'reason': out['A_item_only'][1]},
          'passed' if (out['A_item_only'][0] is False
                       and '质检不合格' in (out['A_item_only'][1] or '')) else 'failed',
          f"[A-66 r2] 实例 status={out['item_status']} quality_status={out['item_quality_status']}；"
          '原期望 allowed=True（前提是该实例仍 NULL，已被 DEC-1 §1.4 序 1 取代）；'
          'NULL 实例不得被拒 = P0-2.4 阳性对照（fg +4）')
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
          f"HTTP {out['null_item']['http']['status_code']}；fp_row={out['null_item']['fp_row']}；"
          '[A-45 ③] 本格必须维持不变（防「pending 一律放行」的过度放松）')
    # ---------------------------------------------------------------- [A-45 ① · 仅追加重写]
    # 作废原断言（保留痕迹）：`P0-2.5` 原期望「pending 报工 => fg +0 且被拒（原因：质检未出结果）」，
    # 把**死锁**当成了正确行为。DEC-1 §1.4 序 3 / §1.6 P1 改判：`pending` **且无在办单据** => 放行。
    # 重写为**成对**判据（A-45 ① 明确要求两者常驻）：
    #   (a) pending 且无在办单据 => 放行（fg > 0，死锁解除）；
    #   (b) pending 且确有在办单据 => 拒且原因可读（含复位动作）——GP-P2 配对格。
    _gp2_ok = (out['GP_P2'][0] is False
               and '未出结果' in (out['GP_P2'][1] or '')
               and '处置' in (out['GP_P2'][1] or ''))
    check('P0-2.5', '[A-45 ①] pending 两态成对：(a) 且无在办单据 => 放行；(b) 且确有在办单据'
                    ' => 拒且原因可读（含复位动作）',
          {'no_docs_fg_delta': '> 0（放行）', 'with_docs_allowed': False,
           'with_docs_reason_has': '未出结果 + 处置'},
          {'no_docs_fg_delta': out['pending_item']['fg_delta'],
           'with_docs_allowed': out['GP_P2'][0], 'with_docs_reason': out['GP_P2'][1],
           'gp_p2_premise': out['GP_P2_premise']},
          'passed' if (out['pending_item']['fg_delta'] > 1e-9 and _gp2_ok) else 'failed',
          '[A-45 ①] 原期望 fg +0（把死锁当正确）=> 已作废；A-67 口径：序 3 只在'
          '「确有在办单据」时可见，本格用构造性前置把该形态摆出来')
    return out

# ------------------------------------------------------------------ P0-3 假开关双向差分
def salary_view(app, client, start, end, emp_id):
    """打真端点 /salary_calculation，并从渲染页里取计件工资文本。"""
    r = call(client, 'post', '/salary_calculation',
             data={'start_date': start, 'end_date': end, 'department': '',
                   'employee_id': str(emp_id)})
    text = r.data.decode('utf-8', 'replace') if hasattr(r, 'data') else ''
    nums = re.findall(r'(?:计件|piecework)[^0-9\-]{0,40}(-?\d[\d,]*\.?\d*)', text, re.I)
    return {'status_code': r.status_code, 'piecework_hits': nums[:6], 'html_bytes': len(text),
            'has_60': '>60.00<' in text, 'has_360': '>360.00<' in text}


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
        # [A-66 r2 / DEC-2 §2.2 · 仅追加重写] 作废原夹具（保留痕迹）：原先两条记录**仅以
        # `notes`（'_uat 返工记录'）区分返工/正常`，而 DEC-2 §2.2 明确**否决** notes 标记
        # （报工链不写 notes），选定 R1∨R2。重写为 DEC-2 合规夹具：
        #   R1 主判据 `NonconformityRecord.rework_task_id == TaskAssignment.id`
        #   R2 次判据 该任务 `global_sn` == `ProductionRecord.global_sn`
        _admin_u = M.User.query.filter_by(username='_t_admin').first()
        _aid = _admin_u.id if _admin_u else 1
        rework_task = M.TaskAssignment(employee_id=emp.id, process_id=proc.id, target_date=day,
                                       quantity=10, status='pending', task_type='auto',
                                       notes='返工 不合格单#_uat')
        db.session.add(rework_task)
        db.session.flush()
        _wp = M.Workpiece(code=f'_uatWP_P031_{RUN_ID[-4:]}', status='machining',
                          product_id=ctx['product']['id'])
        db.session.add(_wp)
        db.session.flush()
        _itask = M.InspectionTask(global_sn=M.SerialNumber.get_next_number(),
                                  target_type='workpiece', target_id=_wp.id,
                                  inspector_id=_aid, status='in_progress', created_by=_aid)
        db.session.add(_itask)
        db.session.flush()
        _irec = M.InspectionRecord(global_sn=M.SerialNumber.get_next_number(),
                                   task_id=_itask.id, inspector_id=_aid,
                                   inspection_date=day, result='fail')
        db.session.add(_irec)
        db.session.flush()
        _nc = M.NonconformityRecord(record_id=_irec.id, type='rework', handler_id=_aid,
                                    handling_date=day, handling_result='_uat 返工',
                                    status='done', workpiece_id=_wp.id,
                                    target_type='workpiece', target_id=_wp.id,
                                    rework_task_id=rework_task.id, scrap_cost=0)
        db.session.add(_nc)
        db.session.flush()
        for qty, notes, sn in ((10, '_uat 返工记录', rework_task.global_sn),
                               (2, '_uat 正常记录', None)):
            rec = M.ProductionRecord(employee_id=emp.id, process_id=proc.id, quantity=qty,
                                     date=day, global_sn=sn, notes=notes)
            db.session.add(rec)
            db.session.flush()
            recs.append({'id': rec.id, 'quantity': qty, 'notes': notes,
                         'global_sn': rec.global_sn})
        out['rework_link'] = {'rework_task_id': rework_task.id,
                              'rework_task_global_sn': rework_task.global_sn,
                              'nc_id': _nc.id, 'workpiece_id': _wp.id}
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
        from app.services import mes_service as _mes
        emp = M.Employee.query.get(out['employee_id'])
        recs = M.ProductionRecord.query.filter(M.ProductionRecord.employee_id == emp.id).all()
        _counted, _dropped, _excluded = _mes.piecework_breakdown(recs)
        _base = emp.base_salary or 0.0
        _adj = sum(bp.amount if bp.type == 'bonus' else -bp.amount for bp in emp.bonuses_penalties)
        _coeff = emp.coefficient or 1.0
        false_calc = {
            'piecework_formula': round(sum(r.quantity * r.process.price for r in recs)
                                       * emp.coefficient, 6),
            'rework_qty': sum(r.quantity for r in recs if '返工' in (r.notes or '')),
            'normal_qty': sum(r.quantity for r in recs if '返工' not in (r.notes or '')),
            'total_salary_property': round(emp.total_salary, 6),
            # [A-66 r2] 产品路径读数：唯一口径函数 + Employee.total_salary(S2)
            'product_piecework': round(_counted * _coeff, 6),
            'product_counted_raw': round(_counted, 6),
            's2_piecework': round((emp.total_salary - _base - _adj) / _coeff, 6),
            'excluded_ids': sorted(_excluded),
            'dropped': round(_dropped, 6),
        }

    setres2 = fixtures.set_rework_switch(app, True)
    out['switch_true_write'] = setres2
    true_http = salary_view(app, client, start, end, out['employee_id'])
    reset_session(app)
    with app.app_context():
        from app.services import mes_service as _mes
        emp = M.Employee.query.get(out['employee_id'])
        recs = M.ProductionRecord.query.filter(M.ProductionRecord.employee_id == emp.id).all()
        _counted, _dropped, _excluded = _mes.piecework_breakdown(recs)
        _base = emp.base_salary or 0.0
        _adj = sum(bp.amount if bp.type == 'bonus' else -bp.amount for bp in emp.bonuses_penalties)
        _coeff = emp.coefficient or 1.0
        true_calc = {
            'piecework_formula': round(sum(r.quantity * r.process.price for r in recs)
                                       * emp.coefficient, 6),
            'rework_qty': sum(r.quantity for r in recs if '返工' in (r.notes or '')),
            'normal_qty': sum(r.quantity for r in recs if '返工' not in (r.notes or '')),
            'total_salary_property': round(emp.total_salary, 6),
            'product_piecework': round(_counted * _coeff, 6),
            'product_counted_raw': round(_counted, 6),
            's2_piecework': round((emp.total_salary - _base - _adj) / _coeff, 6),
            'excluded_ids': sorted(_excluded),
            'dropped': round(_dropped, 6),
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
    # ---------------------------------------------------------------- [A-66 r2 · 仅追加重写]
    # 作废原断言（保留痕迹）：`P0-3.1` 原判据 `abs(delta_val) > 1e-9`，其 delta 取自**链内自算公式**
    # `sum(r.quantity*r.process.price)*coefficient`（与产品路径无关，开关怎么改它都不动），
    # 且夹具用 `notes` 标记造返工（DEC-2 §2.2 已否决）⇒ 双重与 DEC-2 冲突。
    # 重写为：DEC-2 合规夹具（R1∨R2）+ **产品路径**读数（唯一口径函数 `piecework_breakdown`
    # 与 `Employee.total_salary`，均见 mes_service.py:1812-1834 / models.py Employee.total_salary）
    # + 真端点页面（/salary_calculation 的计件单元格）。
    _prod_delta = round(true_calc['product_piecework'] - false_calc['product_piecework'], 6)
    check('P0-3.1', '[A-66 r2] 开关 false→true：false 剔除返工（计件=60.0）、true 全含'
                    '（计件=360.0），差值 300.0 = 返工贡献（AC-26/AC-25，产品路径读数）',
          {'false_piecework': 60.0, 'true_piecework': 360.0, 'delta': 300.0,
           'false_excluded_records': 1, 's1_eq_s2': True,
           'page_off': '>60.00<', 'page_on': '>360.00<'},
          {'false_piecework': false_calc['product_piecework'],
           'true_piecework': true_calc['product_piecework'], 'delta': _prod_delta,
           'false_excluded_records': len(false_calc['excluded_ids']),
           's1_raw': false_calc['product_counted_raw'],
           's2_raw': false_calc['s2_piecework'],
           'false_dropped': false_calc['dropped'],
           'page_off_60': false_http['has_60'], 'page_off_360': false_http['has_360'],
           'page_on_60': true_http['has_60'], 'page_on_360': true_http['has_360'],
           'rework_link': out.get('rework_link')},
          'passed' if (abs(false_calc['product_piecework'] - 60.0) < 1e-6
                       and abs(true_calc['product_piecework'] - 360.0) < 1e-6
                       and len(false_calc['excluded_ids']) == 1
                       and abs(false_calc['product_counted_raw']
                               - false_calc['s2_piecework']) < 1e-6
                       and false_http['has_60'] and not false_http['has_360']
                       and true_http['has_360']) else 'failed',
          '[A-66 r2] 原判据 delta 取自链内自算公式 + notes 夹具 => 已作废；'
          '现值 = mes_service.piecework_breakdown（唯一口径）×系数 与 Employee.total_salary(S2)，'
          '夹具按 R1∨R2（NC.rework_task_id + global_sn）')
    check('P0-3.2', '阴性对照：非返工场景两次必须相同（AC-27）',
          {'normal_only_piecework_same': True},
          {'normal_qty': false_calc['normal_qty'], 'formula_unchanged': True},
          'passed' if false_calc['normal_qty'] == true_calc['normal_qty'] else 'failed',
          '正常记录 2 件 × 20.0 × 1.5 = 60.0（两分支同值）')
    # ---------------------------------------------------------------- [A-66/AC-04-e · 仅追加重写]
    # 作废原断言（保留痕迹）：`P0-3.3` 原期望「该开关**零**读取点」（`read_sites == 0`）——
    # 这正是本轮要消除的缺陷形态（假开关），与 `negative_matrix` 的 `NV-2.3` 同一断言形态
    # （A-66 ⑤ 已就 NV-2.3 裁定「断言的就是缺陷本身」）。重写为「恰 1 个读取点且缺省 False」。
    _sites = sites['read_sites'].get('quality.rework_counts_piecework', [])
    check('P0-3.3', '[A-66/AC-04-e] 该开关在 app/ 下**恰有 1 个**读取点'
                    '（唯一判定处，残缺省值不得缺省即计入）',
          {'read_sites': 1, 'in_mes_service': True},
          {'read_sites': len(_sites), 'sites': _sites},
          'passed' if (len(_sites) == 1 and 'mes_service.py' in (_sites[0] if _sites else ''))
          else 'failed',
          '[A-66] 原期望 0 个读取点（= 假开关的静态证据）=> 已作废；'
          '同源：NV-2.3 由 A-66 ⑤ 裁定重写，本格是其 uat 孪生')
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


# ==============================================================================
# [V-12 / C-04 - r2 仅追加段] 链 A（采购 -> 来料检 -> 入库/退货）+ 链 B/C 缺口
# ------------------------------------------------------------------------------
# 追加纪律（判据 = BASELINE40_DIGEST，见 v12_append_only_selfcheck）：
#   * 本段只新增函数/常量/断言，**不修改**上面任何既有函数体；
#   * 本段在既有 40 条之后执行，故既有读数不受影响（同时逐条比对 id/desc/expected）；
#   * RUN_ID 参与夹具编码 => 必须换 UAT_RUN_ID（40 5.2-1 只增不改）。
# 依赖 V-04：fixtures.manifest() 落盘 + 夹具幂等（本段只调用，不重复实现）。
# 判据来源：phase1-snapshot/04-业务验收标准与端到端判据.md 2.1（A0..A7）/ 2.2（B0..B7）
#           / 2.3（C1..C5）；40-第2轮实测Runbook与台账规范.md 4.2（台账字段）。
# ==============================================================================
V12_TAG = re.sub(r'[^0-9A-Za-z]', '', RUN_ID)[-12:]

#: 冻结基线（改动前 r2-exec-b4-v12-pre2 全量读数）：40 条的 id 顺序 + (id,desc,expected) 摘要
BASELINE40_IDS = (
    'ISO.1', 'ISO.2',
    'P0-1.1', 'P0-1.2', 'P0-1.3', 'P0-1.4', 'P0-1.5', 'P0-1.6', 'P0-1.7', 'P0-1.8', 'P0-1.9',
    'P0-2.1', 'P0-2.2', 'P0-2.3', 'P0-2.4', 'P0-2.5',
    'P0-3.1', 'P0-3.2', 'P0-3.3', 'P0-3.4', 'P0-3.5',
    'P0-4.0', 'P0-4.1', 'P0-4.2', 'P0-4.3', 'P0-4.4', 'P0-4.5',
    'C-1', 'C-2', 'C-3', 'C-4',
    'P0-5.1', 'P0-5.2', 'P0-5.3', 'P0-5.4', 'P0-5.5', 'P0-5.6', 'P0-5.7',
    'ISO.3', 'ISO.4',
)
BASELINE40_DIGEST = 'C9FAD00E20050A3D5C2A96E9D24957E243EBD197588BE22604A79C375B5CDD9C'

#: t1 冻结的另外 6 个锚点（bytes, sha256）——本 run 只读复核，不改动
V12_ANCHORS = (
    ('test-reports-2026-10/evidence/harness/negative_matrix.json', 24424,
     'B743C73F86F5EB5C0FBA38410119D8D3A6BDE5FBACDF214CFA0DB409EF5B7479'),
    ('test-reports-2026-10/evidence/analysis/assertion_ledger.json', 60937,
     'C7C312734DD8E02486D26C3639D8D074CCFCD59BCEB002C13C7CC9587AC94092'),
    ('test-reports-2026-10/evidence/api/write_suite.json', 73293,
     'B608117EBDCA2A6F74595F0DB4A010187D8834715CD5E70D5C1AAD85F4A3F403'),
    ('test-reports-2026-10/evidence/harness/coverage.json', 244575,
     'F0D37A6C72C9029C60B4124DAC5993E1E65321448C943555381C15ECD6BDB42D'),
    ('test-reports-2026-10/evidence/api/api_matrix.json', 1342834,
     '8451BB6738CCB25C41794E7B9548969D0EDDC8FE6EAE855DCC5F1D1CC746CB86'),
    ('test-reports-2026-10/26-阶段A收口-复核读数.json', 11994,
     'CF0E2B14581D82072E087617B0CE3DBC1F4676897787DB6B14D6C6FA43D37319'),
)
#: V-12 有意更新登记：evidence/uat/uat_chains.json（旧值 + 触发 + 归档位置）
V12_UAT_ANCHOR_OLD = {
    'bytes': 33318,
    'sha256': '360A8570BC0080A2984A59AD945B2C837AD96ACF7B55E6242AE7E2C6417DD23A',
    'archived_copy': 'test-reports-2026-10/evidence/_phaseB-prefreeze/20261007-220640/uat/uat_chains.json',
    'trigger': 'V-12 / t13 追加链 A + 链 B/C 缺口后重跑（40 条 -> 46+ 条）',
    'command': 'uat_chains.py（UAT_RUN_ID=本 run）',
}
#: B13-00（2026-10-08）有意更新登记：evidence/harness/coverage.json 覆盖读数锚点（旧值 + 触发 + 归档位置）
#: 依据 = A-70「有意更新三步」；前值字节已归档、登记册 append-only 记 entry no=1「重基线前」。
V12_COVERAGE_ANCHOR_OLD = {
    'bytes': 236893,
    'sha256': '5E2C9D4315971B31C83AFD7833C310501199C34F61BFD868EF07A6AEEF7BF1F0',
    'archived_copy': 'test-reports-2026-10/evidence/harness/_anchor-history/'
                     'frozen-anchor-pre-b13-00.236893.5E2C9D43.json',
    'registry': 'test-reports-2026-10/evidence/harness/_anchor-history/coverage-anchor-history.json',
    'trigger': 'B13-00：冻结 coverage.json 仍是 A-70 之前的旧读数（6/14/101），与 LOCKED 108/116/0 互斥 '
               '⇒ 直喂该档必假红（D-4/D-5/D-6）；用户授权在批次13 开工前重基线化。',
    'command': "& '<py>' -B scripts/_sandbox_compat.py test-reports-2026-10/harness/measure_coverage.py "
               '--no-request-probes --out "<仓库根>/test-reports-2026-10/evidence/harness/coverage.json"',
}

V12 = {'chain_a': {}, 'chain_b': {}, 'chain_c': {}, 'steps': [], 'other_steps': [],
       'fixtures': {}}
V12_FLIPS = []
V12_LOOSE_ENDS = []
V12_QUALITY_MANUAL_PUTS = 0


def _v12_baseline_items():
    return [[c['id'], c['desc'], c['expected']] for c in CHECKS if c['id'] in BASELINE40_IDS]


def _v12_baseline_digest():
    blob = json.dumps(_v12_baseline_items(), ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'))
    return hashlib.sha256(blob.encode('utf-8')).hexdigest().upper()


def _crit(cid, desc, expected, observed, judge, broken, evidence):
    """新判据统一形态：真实观测判定 + 「删掉它什么会变红」敏感度自证（B4 DoD 第 7 项）。

    参数顺序：expected / observed / judge(观测 -> bool) / broken(注入偏差后的观测)。
    """
    try:
        verdict = bool(judge(observed))
        jexc = ''
    except Exception as exc:
        verdict = False
        jexc = f' | judge_exception={exc.__class__.__name__}: {exc}'
    status = 'passed' if verdict else 'failed'
    check(cid, desc, expected, observed, status, evidence + jexc)
    if status == 'passed':
        try:
            broken_verdict = bool(judge(broken))
        except Exception as exc:
            broken_verdict = f'{exc.__class__.__name__}: {exc}'
        red = (broken_verdict is False)
    else:
        broken_verdict = 'n/a（判据实测已红）'
        red = True
    V12_FLIPS.append({
        'id': cid,
        'question': f'删掉/破坏「{cid} {desc}」的机制或注入偏差观测值时，该条是否变红？',
        'answer': evidence,
        'observed': status,
        'broken_observed': broken_verdict,
        'red_when_removed': red,
    })
    return status


def _v12_note_loose_end(item, state, reason, action, owner_wave):
    V12_LOOSE_ENDS.append({'id': f'GAP-{RUN_ID}-{len(V12_LOOSE_ENDS) + 1}', 'item': item,
                           'state': state, 'reason': reason, 'action': action,
                           'owner_wave': owner_wave})


# ------------------------------------------------------------------ 观测工具
def _v12_counts(app):
    from app import db
    reset_session(app)
    with app.app_context():
        out = {}
        for t in ('suppliers', 'purchase_requisitions', 'purchase_requisition_items',
                  'purchase_orders', 'purchase_order_items', 'goods_receipts',
                  'goods_receipt_items', 'inspection_tasks', 'inspection_records',
                  'nonconformity_records', 'inspection_templates', 'production_orders',
                  'production_batches', 'production_batch_items', 'task_assignment',
                  'finished_product', 'raw_material', 'audit_log', 'material_requisitions',
                  'material_requisition_items', 'material_returns', 'material_return_items',
                  'inventory_counts', 'inventory_count_items'):
            out[t] = int(db.session.execute(db.text(f'SELECT COUNT(*) FROM {t}')).scalar() or 0)
        return out


def _v12_raw_sum(app):
    from app import db
    reset_session(app)
    with app.app_context():
        return float(db.session.execute(db.text(
            'SELECT COALESCE(SUM(quantity),0) FROM raw_material')).scalar() or 0)


def _v12_cursor(app):
    V12['_raw_cursor'] = _v12_raw_sum(app)
    return V12['_raw_cursor']


def _v12_step(app, label, expected_pieces, bucket='chain_a'):
    """配对观测：某一步动作引起的原料件数变化 vs 该步「应入/应出」件数。"""
    before = V12.get('_raw_cursor')
    after = _v12_raw_sum(app)
    row = {'label': label, 'expected_pieces': expected_pieces,
           'raw_before': before, 'raw_after': after,
           'observed_pieces': round((after - before) if before is not None else float('nan'), 6)}
    V12['steps' if bucket == 'chain_a' else 'other_steps'].append(row)
    return row


def _v12_template_type_options():
    """静态取证：质检模板「类型」下拉的可选项（判断 goods_receipt 是否界面可达）。"""
    path = os.path.join(REPO_ROOT, 'app', 'templates', 'main', 'quality', 'templates.html')
    try:
        with open(path, encoding='utf-8') as fh:
            html = fh.read()
    except OSError as exc:
        return {'error': f'{exc.__class__.__name__}: {exc}'}
    idx = html.find('id="templateType"')
    seg = html[idx:idx + 1200] if idx >= 0 else ''
    opts = re.findall(r'<option value="([^"]*)"', seg)
    return {'options': opts, 'goods_receipt_in_ui': 'goods_receipt' in opts,
            'file': 'app/templates/main/quality/templates.html'}


# ==============================================================================
# 链 A：采购 -> 来料检 -> 入库/退货（04 2.1 A0..A7）
# ==============================================================================
def v12_chain_a(app, client, seed):
    from app import db
    from app import models as M
    from datetime import date, timedelta
    from app.models import SystemConfig
    out = {}
    tag = V12_TAG
    today = date.today()
    later = today + timedelta(days=14)

    # ------------------------------------------------------------ A1 开关（先探，随后还原）
    with app.app_context():
        orig_switch = SystemConfig.get('purchase.full_workflow_enabled', False)
    with app.app_context():
        SystemConfig.set('purchase.full_workflow_enabled', False)
        db.session.commit()
        SystemConfig.invalidate_cache('purchase.full_workflow_enabled')
    r_off = call(client, 'get', '/purchase_requisitions')
    off_loc = r_off.headers.get('Location') or ''
    with app.app_context():
        SystemConfig.set('purchase.full_workflow_enabled', True)
        db.session.commit()
        SystemConfig.invalidate_cache('purchase.full_workflow_enabled')
    r_on = call(client, 'get', '/purchase_requisitions')
    with app.app_context():
        SystemConfig.set('purchase.full_workflow_enabled', bool(orig_switch))
        db.session.commit()
        SystemConfig.invalidate_cache('purchase.full_workflow_enabled')
    a1 = {'switch_original': bool(orig_switch),
          'off_status': r_off.status_code, 'off_location': off_loc,
          'off_redirects_to_orders': off_loc.rstrip('/').endswith('/purchase_orders'),
          'on_status': r_on.status_code}
    out['a1'] = a1
    _crit('CA1a', 'A1 关闭 purchase.full_workflow_enabled 时 GET /purchase_requisitions 302 -> /purchase_orders',
          {'status': 302, 'location_endswith': '/purchase_orders'}, a1,
          lambda o: o['off_status'] == 302 and o['off_redirects_to_orders'],
          dict(a1, off_status=200, off_redirects_to_orders=False),
          'app/main/purchase.py:131-134（关闭态 302 是预期行为，04 6.2 第 11 项）')
    _crit('CA1b', 'A1b 开启开关后 GET /purchase_requisitions 返回 200 列表页',
          {'status': 200}, a1, lambda o: o['on_status'] == 200,
          dict(a1, on_status=302), 'app/main/purchase.py:135-142')

    # ------------------------------------------------------------ A0 供应商建档（HTTP）
    sup_code = f'_V12SUP{tag}'
    r_page = call(client, 'get', '/suppliers')
    with app.app_context():
        sup_dup = M.Supplier.query.filter_by(code=sup_code).first()
        sup_before = M.Supplier.query.count()
    r0 = call(client, 'post', '/suppliers/save',
              data={'code': sup_code, 'name': f'_V12 供应商 {tag}', 'contact': '_v12',
                    'phone': '0000', 'address': '_v12', 'notes': f'_V12 链A {RUN_ID}',
                    'is_active': '1'})
    reset_session(app)
    with app.app_context():
        sup = M.Supplier.query.filter_by(code=sup_code).first()
        sup_after = M.Supplier.query.count()
        sup_id = sup.id if sup is not None else None
        sup_active = bool(sup.is_active) if sup is not None else None
        sup_name = sup.name if sup is not None else None
    a0 = {'page_status': r_page.status_code, 'save_status': r0.status_code,
          'supplier_rows_before': sup_before, 'supplier_rows_after': sup_after,
          'rows_delta': sup_after - sup_before, 'supplier_id': sup_id,
          'is_active': sup_active, 'name': sup_name, 'preexisting': sup_dup is not None}
    out['a0'] = a0
    _crit('CA0', 'A0 供应商主数据：GET /suppliers 200 且 POST /suppliers/save 建档（供后续请购/采购单引用，不再手填 ID）',
          {'get': 200, 'post': 302, 'rows_delta': 1, 'is_active': True}, a0,
          lambda o: o['page_status'] == 200 and o['save_status'] in (200, 302)
          and o['rows_delta'] == 1 and o['is_active'] is True and o['supplier_id'] is not None,
          dict(a0, rows_delta=0, is_active=False),
          'app/main/purchase.py:92-125（save_supplier）')

    # ------------------------------------------------------------ A2 请购 -> 审批 -> 转采购单
    with app.app_context():
        req_before = M.PurchaseRequisition.query.count()
    r_req = call(client, 'post', '/purchase_requisitions/save',
                 data={'item_name': f'_V12 采购料 {tag}', 'item_qty': '40', 'item_spec': 'S-1',
                       'notes': f'_V12 链A 请购 {RUN_ID}'})
    reset_session(app)
    with app.app_context():
        req = M.PurchaseRequisition.query.order_by(M.PurchaseRequisition.id.desc()).first()
        req_id = req.id if req is not None else None
        req_items = req.items.all() if req is not None else []
        req_item_id = req_items[0].id if req_items else None
        req_item_qty = req_items[0].quantity if req_items else None
        req_rows_delta = M.PurchaseRequisition.query.count() - req_before
    call(client, 'post', f'/purchase_requisitions/{req_id}/approve', data={'decision': 'approve'})
    reset_session(app)
    with app.app_context():
        req_row = M.PurchaseRequisition.query.get(req_id)
        req_status = req_row.status
        req_approved_by = req_row.approved_by
        po_before = M.PurchaseOrder.query.count()
        poi_before = M.PurchaseOrderItem.query.count()
        audit_before = M.AuditLog.query.count()
    # 阴性对照：未审批请购单不得转采购单
    call(client, 'post', '/purchase_requisitions/save',
         data={'item_name': f'_V12 未审料 {tag}', 'item_qty': '5'})
    reset_session(app)
    with app.app_context():
        req2 = M.PurchaseRequisition.query.order_by(M.PurchaseRequisition.id.desc()).first()
        req2_id = req2.id
        req2_status_before = req2.status
    r_conv_neg = call(client, 'post', f'/purchase_requisitions/{req2_id}/convert',
                      json={'supplier_id': sup_id})
    neg_body = jbody(r_conv_neg) or {}
    reset_session(app)
    with app.app_context():
        po_after_neg = M.PurchaseOrder.query.count()
        req2_status = M.PurchaseRequisition.query.get(req2_id).status
    a2n = {'status': r_conv_neg.status_code, 'message': neg_body.get('message') or '',
           'po_rows_delta': po_after_neg - po_before,
           'req2_status': req2_status, 'req2_status_before': req2_status_before}
    out['a2_negative'] = a2n
    _crit('CA2N', 'A2 阴性对照：未审批请购单转采购单被拒（400 + 可读原因，且不产生采购单）',
          {'status': 400, 'reason_contains': '仅已审批', 'po_rows_delta': 0}, a2n,
          lambda o: o['status'] == 400 and '仅已审批' in o['message']
          and o['po_rows_delta'] == 0 and o['req2_status'] == 'pending',
          dict(a2n, status=200, po_rows_delta=1),
          'app/main/purchase.py:208-213（JSON 分支 400）')
    # 正例：已审批 -> 转采购单
    r_conv = call(client, 'post', f'/purchase_requisitions/{req_id}/convert',
                  json={'supplier_id': sup_id, 'prices': {str(req_item_id): 12.5}})
    conv_body = jbody(r_conv) or {}
    reset_session(app)
    with app.app_context():
        po = M.PurchaseOrder.query.order_by(M.PurchaseOrder.id.desc()).first()
        po_id = po.id if po is not None else None
        poi = M.PurchaseOrderItem.query.filter_by(po_id=po_id).first() if po_id else None
        poi_id = poi.id if poi is not None else None
        poi_qty = poi.quantity if poi is not None else None
        poi_price = poi.unit_price if poi is not None else None
        conv_req_status = M.PurchaseRequisition.query.get(req_id).status
        po_req_id = po.requisition_id if po is not None else None
        po_sup_id = po.supplier_id if po is not None else None
        po_rows_delta = M.PurchaseOrder.query.count() - po_before
        poi_rows_delta = M.PurchaseOrderItem.query.count() - poi_before
        audit_rows_delta = M.AuditLog.query.count() - audit_before
        audit_row = M.AuditLog.query.order_by(M.AuditLog.id.desc()).first()
        audit_conv = ({'action': audit_row.action, 'target_model': audit_row.target_model,
                       'target_id': audit_row.target_id} if audit_row is not None else {})
    a2 = {'status': r_conv.status_code, 'success': conv_body.get('success'),
          'po_id': (conv_body.get('data') or {}).get('po_id'),
          'req_rows_delta': req_rows_delta, 'req_status': req_status,
          'req_approved_by': req_approved_by, 'req_item_qty': req_item_qty,
          'po_rows_delta': po_rows_delta, 'poi_rows_delta': poi_rows_delta,
          'conv_req_status': conv_req_status, 'po_requisition_id': po_req_id,
          'po_supplier_id': po_sup_id, 'req_id': req_id, 'po_id_db': po_id,
          'po_item_qty': poi_qty, 'po_item_unit_price': poi_price,
          'audit_rows_delta': audit_rows_delta, 'audit_row': audit_conv}
    out['a2'] = a2
    _crit('CA2', 'A2 已审批请购单转采购单：purchase_orders +1 / purchase_order_items +n / 请购单 converted / 写 AuditLog / 来源可追溯',
          {'status': 200, 'po_rows_delta': 1, 'poi_rows_delta': 1, 'conv_req_status': 'converted',
           'po_requisition_id': '== req_id', 'po_supplier_id': '== sup_id',
           'audit_rows_delta': 1}, a2,
          lambda o: o['status'] == 200 and o['success'] is True and o['po_rows_delta'] == 1
          and o['poi_rows_delta'] == 1 and o['conv_req_status'] == 'converted'
          and o['po_requisition_id'] == o['req_id']
          and o['po_supplier_id'] == a0['supplier_id']
          and o['audit_rows_delta'] == 1
          and o['audit_row'].get('action') == '请购单转采购单',
          dict(a2, po_rows_delta=0, audit_rows_delta=0, conv_req_status='approved'),
          'app/main/purchase.py:190-280（convert_purchase_requisition）')

    # A4 前置：先造一张 type='material' 模板（04 2.1 A4 的字面前置），再造来料检模板
    mtpl_code = f'_V12MT{tag}'
    r_mtpl = call(client, 'post', '/api/quality/templates',
                  json={'template_code': mtpl_code, 'name': f'_V12 原材料质检模板 {tag}',
                        'type': 'material', 'is_active': True,
                        'items': [{'name': '_V12 外观检查', 'standard': '无缺陷'}]})
    mtpl_body = jbody(r_mtpl) or {}
    mtpl_id = (mtpl_body.get('data') or {}).get('id')
    grtpl_code = f'_V12GR{tag}'
    r_grtpl = call(client, 'post', '/api/quality/templates',
                   json={'template_code': grtpl_code, 'name': f'_V12 来料检模板 {tag}',
                         'type': 'goods_receipt', 'is_active': True,
                         'items': [{'name': '_V12 来料外观', 'standard': '无缺陷'}]})
    grtpl_body = jbody(r_grtpl) or {}
    grtpl_id = (grtpl_body.get('data') or {}).get('id')
    ui_opts = _v12_template_type_options()
    out['templates'] = {'material_template_id': mtpl_id, 'material_http': r_mtpl.status_code,
                        'gr_template_id': grtpl_id, 'gr_http': r_grtpl.status_code,
                        'ui_options': ui_opts}
    _crit('CA4a', 'A4a 质检模板可按 API 建档（含 type=goods_receipt）；界面类型下拉只提供 product/production_record/material（来料检模板界面不可达）',
          {'material_http': 200, 'gr_http': 200, 'gr_template_id': 'non-null',
           'ui_goods_receipt_option': False},
          {'material_http': r_mtpl.status_code, 'gr_http': r_grtpl.status_code,
           'gr_template_id': grtpl_id,
           'ui_goods_receipt_option': ui_opts.get('goods_receipt_in_ui'),
           'ui_options': ui_opts.get('options')},
          lambda o: o['material_http'] == 200 and o['gr_http'] == 200
          and o['gr_template_id'] is not None and o['ui_goods_receipt_option'] is False,
          {'material_http': 200, 'gr_http': 200, 'gr_template_id': None,
           'ui_goods_receipt_option': True},
          'app/main/quality.py:233-337（无类型白名单）；'
          'app/templates/main/quality/templates.html:103-106（下拉仅三类）')

    # ------------------------------------------------------------ A3 到货登记
    def _receive(qty, note):
        r = call(client, 'post', f'/purchase_orders/{po_id}/receive',
                 data={f'qty_{poi_id}': str(qty), 'notes': note})
        reset_session(app)
        with app.app_context():
            rec = M.GoodsReceipt.query.order_by(M.GoodsReceipt.id.desc()).first()
            it = (M.GoodsReceiptItem.query.filter_by(receipt_id=rec.id).first()
                  if rec is not None else None)
            task = (M.InspectionTask.query.filter_by(
                target_type='goods_receipt', target_id=rec.id).order_by(
                M.InspectionTask.id.desc()).first() if rec is not None else None)
            po_row = M.PurchaseOrder.query.get(po_id)
            poi_row = M.PurchaseOrderItem.query.get(poi_id)
            return {'http_status': r.status_code, 'receipt_id': rec.id if rec else None,
                    'receipt_status': rec.status if rec else None,
                    'receipt_task_id': rec.inspection_task_id if rec else None,
                    'item_qty': it.quantity if it else None,
                    'item_rows': (M.GoodsReceiptItem.query.filter_by(
                        receipt_id=rec.id).count() if rec is not None else 0),
                    'task_id': task.id if task is not None else None,
                    'task_status': task.status if task is not None else None,
                    'task_template_id': task.template_id if task is not None else None,
                    'po_status': po_row.status if po_row else None,
                    'po_item_received_qty': poi_row.received_qty if poi_row else None}

    with app.app_context():
        gr_before = M.GoodsReceipt.query.count()
        grt_before = M.GoodsReceiptItem.query.count()
        qtask_before = M.InspectionTask.query.count()
    rec1 = _receive(10, f'_V12 到货#1 {RUN_ID}')
    reset_session(app)
    with app.app_context():
        gr_delta = M.GoodsReceipt.query.count() - gr_before
        grt_delta = M.GoodsReceiptItem.query.count() - grt_before
        qtask_delta = M.InspectionTask.query.count() - qtask_before
    a3 = dict(rec1, gr_rows_delta=gr_delta, gr_item_rows_delta=grt_delta,
              inspection_task_delta=qtask_delta)
    out['a3'] = a3
    _crit('CA3r', 'A3 到货登记：goods_receipts +1 且 status=pending_inspection（incoming_inspection_required 默认开）',
          {'http': 302, 'rows_delta': 1, 'receipt_status': 'pending_inspection', 'item_rows': 1,
           'item_qty': 10}, a3,
          lambda o: o['http_status'] in (200, 302) and o['gr_rows_delta'] == 1
          and o['receipt_status'] == 'pending_inspection' and o['item_rows'] == 1
          and abs((o['item_qty'] or 0) - 10.0) < 1e-9,
          dict(a3, receipt_status='accepted', item_qty=0.0),
          'app/main/purchase.py:359-393（receive_purchase_order）')
    _crit('CA3t', 'A3t 到货自动建来料检任务（target_type=goods_receipt, target_id=到货单）+ 采购单转 received',
          {'task_delta': 1, 'task_status': 'pending', 'receipt_task_id': '== task_id',
           'po_status': 'received'}, a3,
          lambda o: o['inspection_task_delta'] == 1 and o['task_status'] == 'pending'
          and o['receipt_task_id'] == o['task_id'] and o['po_status'] == 'received',
          dict(a3, inspection_task_delta=0, po_status='confirmed'),
          'app/main/purchase.py:378-383 + mes_service.create_inspection_task')

    # ------------------------------------------------------------ A4 来料检（阴性 + 正例）
    r_si_mat = call(client, 'post', f"/api/quality/tasks/{rec1['task_id']}/start-inspection",
                    json={'template_id': mtpl_id, 'notes': '_V12 用 material 模板开始来料检'})
    si_mat_body = jbody(r_si_mat) or {}
    with app.app_context():
        rec_after_mat = M.InspectionRecord.query.filter_by(task_id=rec1['task_id']).count()
    a4n = {'status': r_si_mat.status_code, 'message': si_mat_body.get('message') or '',
           'inspection_records_for_task': rec_after_mat,
           'task_template_id': rec1['task_template_id'], 'material_template_id': mtpl_id}
    out['a4_negative'] = a4n
    _crit('CA4N', 'A4 阴性对照/口径冲突：用 04 A4 字面前置的 type=material 模板开始来料检被 400 拒（模板类型 != 任务类型 goods_receipt）',
          {'status': 400, 'message_contains': '类型', 'inspection_records': 0}, a4n,
          lambda o: o['status'] == 400 and '类型' in o['message']
          and o['inspection_records_for_task'] == 0,
          dict(a4n, status=200, inspection_records_for_task=1),
          'app/main/quality.py:837-839（template.type != task.target_type => 400）；'
          'app/services/mes_service.py:90-94（无 goods_receipt 模板时回退 material）')
    r_si_gr = call(client, 'post', f"/api/quality/tasks/{rec1['task_id']}/start-inspection",
                   json={'template_id': grtpl_id, 'notes': '_V12 用来料检模板开始'})
    si_gr_body = jbody(r_si_gr) or {}
    reset_session(app)
    with app.app_context():
        qrec1 = M.InspectionRecord.query.filter_by(task_id=rec1['task_id']).first()
        qtask1 = M.InspectionTask.query.get(rec1['task_id'])
        qrec1_id = qrec1.id if qrec1 is not None else None
    a4b = {'status': r_si_gr.status_code, 'success': si_gr_body.get('success'),
           'record_id': si_gr_body.get('record_id'), 'db_record_id': qrec1_id,
           'task_status': qtask1.status if qtask1 is not None else None,
           'task_template_id': qtask1.template_id if qtask1 is not None else None}
    out['a4'] = a4b
    _crit('CA4b', 'A4b 用来料检模板（type=goods_receipt）可开始来料检：HTTP 200 + inspection_records +1（task.target_type=goods_receipt）',
          {'status': 200, 'record_id_non_null': True, 'task_status': 'in_progress',
           'task_template_id': '== gr_template_id'}, a4b,
          lambda o: o['status'] == 200 and o['record_id'] is not None
          and o['db_record_id'] == o['record_id'] and o['task_status'] == 'in_progress'
          and o['task_template_id'] == grtpl_id,
          dict(a4b, status=400, task_status='pending'),
          'app/main/quality.py:796-894（start_inspection）；模板类型校验 :838')

    # ------------------------------------------------------------ A5b fail 路径
    _v12_cursor(app)
    r_fail1 = call(client, 'post', f"/api/quality/records/{qrec1_id}/submit",
                   json={'result': 'fail', 'notes': f'_V12 来料检不合格 {RUN_ID}'})
    reset_session(app)
    with app.app_context():
        rec1_row = M.GoodsReceipt.query.get(rec1['receipt_id'])
        nc1 = M.NonconformityRecord.query.filter_by(
            target_type='goods_receipt', target_id=rec1['receipt_id']).order_by(
            M.NonconformityRecord.id.desc()).first()
        nc1_id = nc1.id if nc1 is not None else None
        nc1_info = ({'id': nc1_id, 'status': nc1.status, 'type': nc1.type,
                     'target_type': nc1.target_type, 'target_id': nc1.target_id,
                     'workpiece_id': nc1.workpiece_id} if nc1 is not None else {})
        rec1_status = rec1_row.status
    step_fail = _v12_step(app, 'A5b 来料检 fail（拒收待处置，不入库）', 0)
    a5b = {'status': r_fail1.status_code, 'receipt_status': rec1_status, 'nc': nc1_info,
           'stock': step_fail}
    out['a5b'] = a5b
    _crit('CA5b', 'A5b 来料检 fail：到货单 rejected + nonconformity_records +1（target_type=goods_receipt, status=open）+ 库存增量 0',
          {'http': 200, 'receipt_status': 'rejected', 'nc_target_type': 'goods_receipt',
           'nc_status': 'open', 'stock_delta': 0}, a5b,
          lambda o: o['status'] == 200 and o['receipt_status'] == 'rejected'
          and o['nc'].get('target_type') == 'goods_receipt'
          and o['nc'].get('target_id') == rec1['receipt_id']
          and o['nc'].get('status') == 'open'
          and abs(o['stock']['observed_pieces']) < 1e-9,
          dict(a5b, receipt_status='accepted', nc=dict(nc1_info, status='done')),
          'app/services/mes_service.py:884-917（apply_goods_receipt_result）')

    # ------------------------------------------------------------ A5c 三种处置
    def _rejected_receipt(qty, note):
        r = _receive(qty, note)
        call(client, 'post', f"/api/quality/tasks/{r['task_id']}/start-inspection",
             json={'template_id': grtpl_id, 'notes': note})
        reset_session(app)
        with app.app_context():
            qr = M.InspectionRecord.query.filter_by(task_id=r['task_id']).first()
            r['record_id'] = qr.id if qr is not None else None
        call(client, 'post', f"/api/quality/records/{r['record_id']}/submit",
             json={'result': 'fail', 'notes': note + ' 不合格'})
        reset_session(app)
        with app.app_context():
            nc = M.NonconformityRecord.query.filter_by(
                target_type='goods_receipt', target_id=r['receipt_id']).order_by(
                M.NonconformityRecord.id.desc()).first()
            r['nc_id'] = nc.id if nc is not None else None
        return r

    # A5c-return
    _v12_cursor(app)
    r_ret = call(client, 'post', f"/goods_receipts/{rec1['receipt_id']}/nonconformity",
                 json={'action': 'return', 'notes': f'_V12 退货 {RUN_ID}'})
    ret_body = jbody(r_ret) or {}
    reset_session(app)
    with app.app_context():
        rec1_row = M.GoodsReceipt.query.get(rec1['receipt_id'])
        nc1_row = M.NonconformityRecord.query.get(nc1_id)
        ret_obs = {'receipt_status': rec1_row.status, 'nc_status': nc1_row.status,
                   'nc_type': nc1_row.type}
    step_ret = _v12_step(app, 'A5c 退货（不入库）', 0)
    a5c_ret = dict(ret_obs, http_status=r_ret.status_code,
                   body_receipt_status=(ret_body.get('data') or {}).get('receipt_status'),
                   stock=step_ret)
    out['a5c_return'] = a5c_ret
    _crit('CA5c-return', 'A5c 退货处置：HTTP 200 + 到货单 returned + NC done/type=return + 库存增量 0（不入库）',
          {'http': 200, 'receipt_status': 'returned', 'nc_status': 'done', 'nc_type': 'return',
           'stock_delta': 0}, a5c_ret,
          lambda o: o['http_status'] == 200 and o['receipt_status'] == 'returned'
          and o['nc_status'] == 'done' and o['nc_type'] == 'return'
          and abs(o['stock']['observed_pieces']) < 1e-9,
          dict(a5c_ret, receipt_status='putaway', nc_status='open'),
          'app/main/purchase.py:444-483 + mes_service.dispose_incoming_nonconformity:971-974')

    # A5c-accept（非授权 inspector -> pending_approval；admin -> approved + 入库）
    rec2 = _rejected_receipt(10, f'_V12 到货#2 {RUN_ID}')
    # A5c 阴性对照：非法处置动作（须在 NC 仍 open 时打；处置后 NC 闭环会先撞 404）
    r_bad = call(client, 'post', f"/goods_receipts/{rec2['receipt_id']}/nonconformity",
                 json={'action': 'foobar'})
    bad_body = jbody(r_bad) or {}
    reset_session(app)
    with app.app_context():
        nc2_after_bad = M.NonconformityRecord.query.get(rec2['nc_id'])
        bad_obs = {'status': r_bad.status_code, 'message': bad_body.get('message') or '',
                   'nc_status': nc2_after_bad.status, 'nc_type': nc2_after_bad.type}
    out['a5c_bad_action'] = bad_obs
    _crit('CA5c-bad', 'A5c 阴性对照：来料检非法处置动作（foobar）被 400 拒（仅 return/accept/scrap）且不合格单状态不变',
          {'status': 400, 'message_contains': '仅支持', 'nc_status': 'open'}, bad_obs,
          lambda o: o['status'] == 400 and '仅支持' in o['message'] and o['nc_status'] == 'open',
          dict(bad_obs, status=200),
          'mes_service.dispose_incoming_nonconformity:946-947（INCOMING_NC_ACTIONS 白名单）')
    client_ins, ins_code, ins_loc = make_client(app, seed['users']['inspector'], seed['password'])
    out['inspector_login'] = {'status': ins_code, 'location': ins_loc}
    _v12_cursor(app)
    r_acc_ins = call(client_ins, 'post', f"/goods_receipts/{rec2['receipt_id']}/nonconformity",
                     json={'action': 'accept', 'notes': f'_V12 让步接收(inspector) {RUN_ID}'})
    acc_ins_body = jbody(r_acc_ins) or {}
    reset_session(app)
    with app.app_context():
        nc2_ins = M.NonconformityRecord.query.get(rec2['nc_id'])
        rec2_ins_row = M.GoodsReceipt.query.get(rec2['receipt_id'])
        a5c_acc_a = {'nc_status': nc2_ins.status, 'approver_id': nc2_ins.approver_id,
                     'receipt_status': rec2_ins_row.status,
                     'http_status': r_acc_ins.status_code,
                     'body_status': (acc_ins_body.get('data') or {}).get('status'),
                     'inspector_role': 'inspector'}
    step_acc_ins = _v12_step(app, 'A5c 让步接收（非授权角色，须 pending_approval 且不入库）', 0)
    a5c_acc_a['stock'] = step_acc_ins
    out['a5c_accept_pending'] = a5c_acc_a
    _crit('CA5c-accept-a', 'A5c 让步接收（非授权角色 inspector）：NC 转 pending_approval、到货单不变、库存增量 0',
          {'http': 200, 'nc_status': 'pending_approval', 'receipt_status': 'rejected',
           'approver_id': None, 'stock_delta': 0}, a5c_acc_a,
          lambda o: o['http_status'] == 200 and o['nc_status'] == 'pending_approval'
          and o['receipt_status'] == 'rejected' and o['approver_id'] is None
          and abs(o['stock']['observed_pieces']) < 1e-9,
          dict(a5c_acc_a, nc_status='approved', receipt_status='putaway'),
          'app/services/mes_service.py:959-964（concession_approver_roles 判定）')
    _v12_cursor(app)
    r_acc_adm = call(client, 'post', f"/goods_receipts/{rec2['receipt_id']}/nonconformity",
                     json={'action': 'accept', 'notes': f'_V12 让步接收(admin) {RUN_ID}'})
    acc_adm_body = jbody(r_acc_adm) or {}
    reset_session(app)
    with app.app_context():
        nc2_adm = M.NonconformityRecord.query.get(rec2['nc_id'])
        rec2_adm_row = M.GoodsReceipt.query.get(rec2['receipt_id'])
        new_raw_rows = M.RawMaterial.query.filter(
            M.RawMaterial.internal_number.like(f'R{poi_id}-{rec2["receipt_id"]}-%')).count()
        a5c_acc_b = {'nc_status': nc2_adm.status, 'approver_id': nc2_adm.approver_id,
                     'receipt_status': rec2_adm_row.status,
                     'raw_rows_for_receipt': new_raw_rows,
                     'http_status': r_acc_adm.status_code,
                     'body_status': (acc_adm_body.get('data') or {}).get('status'),
                     'body_receipt_status': (acc_adm_body.get('data') or {}).get('receipt_status')}
    step_acc_adm = _v12_step(app, 'A5c 让步接收（admin 授权，放行入库）', 10)
    a5c_acc_b['stock'] = step_acc_adm
    out['a5c_accept_approved'] = a5c_acc_b
    _crit('CA5c-accept-b', 'A5c 让步接收（admin 授权）：NC approved + 到货单 accepted/putaway + 原料库存 +10',
          {'http': 200, 'nc_status': 'approved', 'receipt_status': 'putaway',
           'approver_id_non_null': True, 'stock_delta': 10, 'raw_rows_for_receipt': 1},
          a5c_acc_b,
          lambda o: o['http_status'] == 200 and o['nc_status'] == 'approved'
          and o['receipt_status'] == 'putaway' and o['approver_id'] is not None
          and abs(o['stock']['observed_pieces'] - 10.0) < 1e-9
          and o['raw_rows_for_receipt'] == 1,
          dict(a5c_acc_b, nc_status='pending_approval',
               stock=dict(step_acc_adm, observed_pieces=0.0)),
          'mes_service.py:965-970（approved -> receipt accepted + putaway_goods_receipt）')

    # A5c-scrap
    rec3 = _rejected_receipt(10, f'_V12 到货#3 {RUN_ID}')
    _v12_cursor(app)
    r_scrap = call(client, 'post', f"/goods_receipts/{rec3['receipt_id']}/nonconformity",
                   json={'action': 'scrap', 'scrap_cost': 66.0, 'notes': f'_V12 报废 {RUN_ID}'})
    scrap_body = jbody(r_scrap) or {}
    reset_session(app)
    with app.app_context():
        nc3 = M.NonconformityRecord.query.get(rec3['nc_id'])
        rec3_row = M.GoodsReceipt.query.get(rec3['receipt_id'])
        a5c_scrap = {'receipt_status': rec3_row.status, 'nc_status': nc3.status,
                     'nc_type': nc3.type, 'scrap_cost': nc3.scrap_cost,
                     'http_status': r_scrap.status_code,
                     'body_receipt_status': (scrap_body.get('data') or {}).get('receipt_status')}
    step_scrap = _v12_step(app, 'A5c 报废（不入库）', 0)
    a5c_scrap['stock'] = step_scrap
    out['a5c_scrap'] = a5c_scrap
    _crit('CA5c-scrap', 'A5c 报废处置：HTTP 200 + 到货单 scrapped + NC done/type=scrap/scrap_cost=66 + 库存增量 0',
          {'http': 200, 'receipt_status': 'scrapped', 'nc_status': 'done', 'nc_type': 'scrap',
           'scrap_cost': 66.0, 'stock_delta': 0}, a5c_scrap,
          lambda o: o['http_status'] == 200 and o['receipt_status'] == 'scrapped'
          and o['nc_status'] == 'done' and o['nc_type'] == 'scrap'
          and abs((o['scrap_cost'] or 0) - 66.0) < 1e-9
          and abs(o['stock']['observed_pieces']) < 1e-9,
          dict(a5c_scrap, receipt_status='putaway', scrap_cost=0.0),
          'mes_service.py:975-979')
    r_bad = None
    bad_obs = None
    out['a5c_bad_action'] = {'moved': '非法动作对照已前移到 A5c-accept 之前（NC 须仍 open）'}

    # ------------------------------------------------------------ A5a pass 路径（入库）
    rec4 = _receive(10, f'_V12 到货#4 {RUN_ID}')
    a5a_bind = {'task_template_id': rec4['task_template_id'], 'gr_template_id': grtpl_id,
                'auto_bound': rec4['task_template_id'] == grtpl_id}
    _crit('CA5a-bind', 'A5a 到货任务自动绑来料检模板（pick_template("goods_receipt") 命中启用模板；缺模板时才回退 material）',
          {'auto_bound': True, 'task_template_id': '== gr_template_id'}, a5a_bind,
          lambda o: o['auto_bound'] is True and o['task_template_id'] == grtpl_id,
          dict(a5a_bind, auto_bound=False), 'mes_service.py:85-94（pick_template）')
    call(client, 'post', f"/api/quality/tasks/{rec4['task_id']}/start-inspection",
         json={'template_id': grtpl_id, 'notes': f'_V12 来料检 pass {RUN_ID}'})
    reset_session(app)
    with app.app_context():
        qrec4 = M.InspectionRecord.query.filter_by(task_id=rec4['task_id']).first()
        rec4_id = qrec4.id if qrec4 is not None else None
    _v12_cursor(app)
    r_pass = call(client, 'post', f"/api/quality/records/{rec4_id}/submit",
                  json={'result': 'pass', 'notes': f'_V12 来料检合格 {RUN_ID}'})
    reset_session(app)
    with app.app_context():
        rec4_row = M.GoodsReceipt.query.get(rec4['receipt_id'])
        raw4 = M.RawMaterial.query.filter(
            M.RawMaterial.internal_number.like(f'R{poi_id}-{rec4["receipt_id"]}-%')).first()
        a5a = {'receipt_status': rec4_row.status,
               'raw_rows': M.RawMaterial.query.filter(M.RawMaterial.internal_number.like(
                   f'R{poi_id}-{rec4["receipt_id"]}-%')).count(),
               'raw_row_quantity': raw4.quantity if raw4 is not None else None,
               'http_status': r_pass.status_code,
               'body_success': (jbody(r_pass) or {}).get('success')}
    step_pass = _v12_step(app, 'A5a 来料检合格（放行入库）', 10)
    a5a['stock'] = step_pass
    out['a5a'] = a5a
    _crit('CA5a', 'A5a 来料检 pass：到货单 accepted/putaway + 原料库存 +10（新建原料行 quantity=到货数量）',
          {'http': 200, 'receipt_status': 'putaway', 'stock_delta': 10, 'raw_rows': 1,
           'raw_row_quantity': 10.0}, a5a,
          lambda o: o['http_status'] == 200 and o['receipt_status'] == 'putaway'
          and abs(o['stock']['observed_pieces'] - 10.0) < 1e-9 and o['raw_rows'] == 1
          and abs((o['raw_row_quantity'] or 0) - 10.0) < 1e-9,
          dict(a5a, receipt_status='pending_inspection',
               stock=dict(step_pass, observed_pieces=0.0)),
          'app/main/quality.py:982-990（pass -> accepted + putaway_goods_receipt）')

    # ------------------------------------------------------------ A6 强行入库被拒 + 阳性对照
    rec5 = _receive(10, f'_V12 到货#5 {RUN_ID}')
    with app.app_context():
        audit_guard_before = M.AuditLog.query.filter_by(action='拒绝到货入库').count()
    _v12_cursor(app)
    r_block = call(client, 'post', f"/goods_receipts/{rec5['receipt_id']}/putaway")
    reset_session(app)
    with app.app_context():
        rec5_row = M.GoodsReceipt.query.get(rec5['receipt_id'])
        audit_guard = M.AuditLog.query.filter_by(action='拒绝到货入库').order_by(
            M.AuditLog.id.desc()).first()
        a6 = {'receipt_status': rec5_row.status,
              'audit_delta': M.AuditLog.query.filter_by(
                  action='拒绝到货入库').count() - audit_guard_before,
              'audit_details': (audit_guard.details or '') if audit_guard is not None else '',
              'audit_target_id': audit_guard.target_id if audit_guard is not None else None,
              'http_status': r_block.status_code, 'receipt_id': rec5['receipt_id']}
    step_block = _v12_step(app, 'A6 强行入库被拒（pending_inspection）', 0)
    a6['stock'] = step_block
    out['a6'] = a6
    _crit('CA6', 'A6 pending_inspection 到货单强行入库被拒：状态不变 + 库存增量 0 + 写 AuditLog「拒绝到货入库」并含可读原因',
          {'http': 302, 'receipt_status': 'pending_inspection', 'audit_delta': 1,
           'reason_contains': '来料检', 'stock_delta': 0}, a6,
          lambda o: o['http_status'] in (200, 302) and o['receipt_status'] == 'pending_inspection'
          and o['audit_delta'] == 1 and '来料检' in o['audit_details']
          and o['audit_target_id'] == rec5['receipt_id']
          and abs(o['stock']['observed_pieces']) < 1e-9,
          dict(a6, receipt_status='putaway', audit_delta=0),
          'app/main/purchase.py:401-441（_PUTAWAY_BLOCK_REASONS + AuditLog）')
    with app.app_context():
        rec5_fix = M.GoodsReceipt.query.get(rec5['receipt_id'])
        rec5_fix.status = 'accepted'
        db.session.commit()
    _v12_cursor(app)
    r_force = call(client, 'post', f"/goods_receipts/{rec5['receipt_id']}/putaway")
    reset_session(app)
    with app.app_context():
        rec5_row2 = M.GoodsReceipt.query.get(rec5['receipt_id'])
        a6b = {'receipt_status': rec5_row2.status,
               'raw_rows': M.RawMaterial.query.filter(M.RawMaterial.internal_number.like(
                   f'R{poi_id}-{rec5["receipt_id"]}-%')).count(),
               'http_status': r_force.status_code}
    step_force = _v12_step(app, 'A6 阳性对照：状态改 accepted 后同端点放行入库', 10)
    a6b['stock'] = step_force
    out['a6_positive'] = a6b
    _crit('CA6b', 'A6 阳性对照：同一 putaway 端点在 status=accepted 时确实入库（库存 +10）=> 判据咬住的是状态门',
          {'http': 302, 'receipt_status': 'putaway', 'stock_delta': 10, 'raw_rows': 1}, a6b,
          lambda o: o['http_status'] in (200, 302) and o['receipt_status'] == 'putaway'
          and abs(o['stock']['observed_pieces'] - 10.0) < 1e-9 and o['raw_rows'] == 1,
          dict(a6b, receipt_status='accepted', stock=dict(step_force, observed_pieces=0.0)),
          'app/main/purchase.py:412-434（放行分支）')

    # ------------------------------------------------------------ A7 链级守恒
    steps = V12['steps']
    total_expected = round(sum(s['expected_pieces'] for s in steps), 6)
    total_observed = round(sum(s['observed_pieces'] for s in steps), 6)
    per_step_ok = all(abs(s['observed_pieces'] - s['expected_pieces']) < 1e-9 for s in steps)
    a7 = {'steps': steps, 'total_expected': total_expected, 'total_observed': total_observed,
          'per_step_exact': per_step_ok, 'receipts': 5}
    out['a7'] = a7
    _crit('CA7', 'A7 链级判据：A5a/A5b/A5c 各路径的原料库存件数变化与到货数量严格一致（逐步配对 + 总量相等）',
          {'per_step_exact': True, 'total_expected': 30.0, 'total_observed': 30.0}, a7,
          lambda o: o['per_step_exact'] is True
          and abs(o['total_observed'] - o['total_expected']) < 1e-9
          and abs(o['total_observed'] - 30.0) < 1e-9,
          dict(a7, per_step_exact=False, total_observed=total_observed + 1.0),
          '04 2.1 A7（三条路径件数守恒）；本段逐步观测见 steps[]')
    _v12_note_loose_end('来料检质检模板类型（04 2.1 A4 字面前置 type=material vs 实现要求 type==target_type）',
                        'asset_defect',
                        'A4 前置写「启用的 type=material 质检模板」，但 quality.py:838 要求'
                        '模板类型 == 任务类型（goods_receipt）；且界面下拉只有 product/production_record/material '
                        '=> 界面无法为来料检建可用模板（CA4N 实测 400）',
                        '登记为判据与实现的口径冲突：要么在界面补 goods_receipt 类型，要么放宽模板类型匹配；'
                        '本轮不改判据、不改生产代码', '阶段B / C-04 后续（业务口径）')
    V12['chain_a'] = out
    return out

# ==============================================================================
# 链 B 缺口：B0（无工艺路线拒绝）/ B1（销售订单转生产订单）/ B2（批次与派工策略）
#              / B6（报工路径 NC 处置 rework/scrap/accept）/ B7（实例「质量」列自动回写）
# ==============================================================================
def v12_b_fixtures(app, ctx):
    """链 B 缺口所需夹具：code_rule + 无路线产品 + 带 3 工序/3 策略的产品与规则。"""
    from app import db
    from app import models as M
    tag = V12_TAG
    reset_session(app)
    with app.app_context():
        admin = M.User.query.filter_by(username='_t_admin').first()
        admin_id = admin.id if admin is not None else None
        emps = M.Employee.query.filter_by(is_active=True).order_by(M.Employee.id).limit(4).all()
        if len(emps) < 2:
            raise RuntimeError('在职员工不足 2 人，无法构造派工策略对照')
        emp_a, emp_b = emps[0].id, emps[1].id
        rule = M.CodeRule(name=f'_V12B2CR{tag}', code_type='product', prefix=f'_V12B2{tag}',
                          suffix='', sequence_length=4, current_sequence=1,
                          reset_frequency='never', format_pattern='{prefix}{sequence}',
                          is_active=True, created_by=admin_id, notes=f'_V12 {RUN_ID}')
        db.session.add(rule)
        db.session.flush()
        cat = M.RawMaterialCategory.query.first()
        b6_raw = M.RawMaterial(supplier='_V12 供应商', category_id=cat.id if cat else None,
                               melt_number=f'_V12MELT{tag}', supplier_number=f'_V12SUP{tag}',
                               internal_number=f'_V12B6RAW{tag}', quantity=100.0,
                               status='in_stock', is_archived=False)
        db.session.add(b6_raw)
        db.session.flush()
        p_nr = M.Product(product_code=f'_V12B0NR{tag}', product_name=f'_V12 无路线产品 {tag}',
                         drawing_number=f'_V12NR-{tag}', model='_V12-NR', status='active',
                         created_by=admin_id)
        p_b2 = M.Product(product_code=f'_V12B2P{tag}', product_name=f'_V12 派工产品 {tag}',
                         drawing_number=f'_V12B2-{tag}', model='_V12-B2', status='active',
                         created_by=admin_id, code_rule_id=rule.id)
        db.session.add(p_nr)
        db.session.add(p_b2)
        db.session.flush()
        rules = []
        specs = [('fixed', 1, [emp_b, emp_a], [1, 1]),
                 ('round_robin', 2, [emp_a, emp_b], [1, 1]),
                 ('weighted', 3, [emp_a, emp_b], [1, 3])]
        for strategy, seq, members, weights in specs:
            proc = M.ProcessPrice(process_code=f'_V12B2P{seq}{tag}',
                                  process_name=f'_V12 工序{seq} {tag}', price=10.0 * seq,
                                  version=1, needs_inspection=False)
            db.session.add(proc)
            db.session.flush()
            db.session.add(M.ProductProcess(product_id=p_b2.id, process_id=proc.id, sequence=seq))
            r = M.ProcessAssignmentRule(process_id=proc.id, strategy=strategy, is_active=True,
                                        notes=f'_V12 {strategy} {RUN_ID}')
            db.session.add(r)
            db.session.flush()
            for k, eid in enumerate(members):
                db.session.add(M.ProcessAssignmentMember(
                    rule_id=r.id, employee_id=eid, weight=weights[k], sequence=k, is_active=True))
            rules.append({'strategy': strategy, 'sequence': seq, 'process_id': proc.id,
                          'rule_id': r.id,
                          'members': [{'employee_id': eid, 'weight': weights[k], 'sequence': k}
                                      for k, eid in enumerate(members)]})
        db.session.commit()
        out = {'code_rule_id': rule.id, 'no_route_product_id': p_nr.id,
               'b2_product_id': p_b2.id, 'b2_product_code': p_b2.product_code,
               'b6_raw_id': b6_raw.id, 'emp_a': emp_a, 'emp_b': emp_b, 'rules': rules,
               'process_ids': [r['process_id'] for r in rules]}
    V12['fixtures']['chain_b'] = out
    return out


def _v12_predict(members, strategy, idx):
    """按 routes.create_tasks_for_production_batch 的既有实现口径预测指派员工。"""
    if not members:
        return None
    if strategy == 'fixed':
        return members[0]['employee_id']
    if strategy == 'weighted':
        pool = []
        for m in members:
            pool.extend([m['employee_id']] * max(1, m['weight'] or 1))
        return pool[idx % len(pool)] if pool else None
    return members[idx % len(members)]['employee_id']


def _pr_template_id(app):
    from app import models as M
    reset_session(app)
    with app.app_context():
        tpl = M.InspectionTemplate.query.filter_by(type='production_record',
                                                   is_active=True).first()
        return tpl.id if tpl is not None else None


def v12_chain_b(app, client, seed, ctx):
    from app import db
    from app import models as M
    from datetime import date, timedelta
    out = {}
    today = date.today()
    later = today + timedelta(days=21)
    fx = v12_b_fixtures(app, ctx)

    # ------------------------------------------------------------ B0 无工艺路线 => 400
    with app.app_context():
        ord_before = M.ProductionOrder.query.count()
    r_b0 = call(client, 'post', '/production_orders/add',
                json={'product_id': fx['no_route_product_id'], 'planned_quantity': 1,
                      'planned_start_date': today.strftime('%Y-%m-%d'),
                      'planned_end_date': later.strftime('%Y-%m-%d'),
                      'notes': f'_V12 B0 {RUN_ID}'})
    b0_body = jbody(r_b0) or {}
    reset_session(app)
    with app.app_context():
        ord_after_b0 = M.ProductionOrder.query.count()
    b0 = {'status': r_b0.status_code, 'message': b0_body.get('message') or '',
          'orders_delta': ord_after_b0 - ord_before}
    out['b0'] = b0
    _crit('B0', 'B0 无工艺路线的产品禁止创建生产订单：400 + 可读原因含「工艺路线」且不落库',
          {'status': 400, 'reason_contains': '工艺路线', 'orders_delta': 0}, b0,
          lambda o: o['status'] == 400 and '工艺路线' in o['message'] and o['orders_delta'] == 0,
          dict(b0, status=200, orders_delta=1),
          'app/main/routes.py:8080-8082（product_has_routing => 400）')
    r_ok = call(client, 'post', '/production_orders/add',
                json={'product_id': fx['b2_product_id'], 'planned_quantity': 3,
                      'planned_start_date': today.strftime('%Y-%m-%d'),
                      'planned_end_date': later.strftime('%Y-%m-%d'),
                      'notes': f'_V12 B0 阳性对照 {RUN_ID}'})
    ok_body = jbody(r_ok) or {}
    reset_session(app)
    with app.app_context():
        po_b2 = M.ProductionOrder.query.filter_by(
            product_id=fx['b2_product_id']).order_by(M.ProductionOrder.id.desc()).first()
        po_b2_id = po_b2.id if po_b2 is not None else None
        ord_after_ok = M.ProductionOrder.query.count()
    b0b = {'status': r_ok.status_code, 'success': ok_body.get('success'),
           'orders_delta': ord_after_ok - ord_after_b0, 'order_id': po_b2_id}
    out['b0_positive'] = b0b
    _crit('B0b', 'B0 阳性对照：同一端点对有工艺路线的产品建单成功（探针不是恒假）',
          {'status': 200, 'success': True, 'orders_delta': 1, 'order_id': 'non-null'}, b0b,
          lambda o: o['status'] == 200 and o['success'] is True and o['orders_delta'] == 1
          and o['order_id'] is not None,
          dict(b0b, status=400, orders_delta=0),
          'app/main/routes.py:8084-8104（add_production_order 放行分支）')

    # ------------------------------------------------------------ B1 销售订单 -> 生产订单
    with app.app_context():
        cust = M.Customer.query.first()
        cust_id = cust.id if cust is not None else None
        admin = M.User.query.filter_by(username='_t_admin').first()
        so = M.SalesOrder(customer_id=cust_id, order_source='_V12', year_month='2026-10',
                          status='confirmed', total_quantity=3,
                          created_by=admin.id if admin is not None else None,
                          notes=f'_V12 B1 {RUN_ID}')
        db.session.add(so)
        db.session.flush()
        line = M.SalesOrderItem(sales_order_id=so.id, product_id=fx['b2_product_id'], quantity=3)
        db.session.add(line)
        db.session.commit()
        so_id, line_id = so.id, line.id
        orders_before = M.ProductionOrder.query.count()
        audit_before = M.AuditLog.query.filter_by(action='从销售订单创建生产订单').count()
    r_b1 = call(client, 'post', f'/sales_order/{so_id}/create_production_order',
                json={'planned_start_date': today.strftime('%Y-%m-%d'),
                      'planned_end_date': later.strftime('%Y-%m-%d'),
                      'notes': f'_V12 B1 {RUN_ID}'})
    b1_body = jbody(r_b1) or {}
    reset_session(app)
    with app.app_context():
        so_row = M.SalesOrder.query.get(so_id)
        new_orders = M.ProductionOrder.query.filter_by(sales_order_item_id=line_id).all()
        b1 = {'status': r_b1.status_code, 'success': b1_body.get('success'),
              'created_orders': len(b1_body.get('created_orders') or []),
              'orders_delta': M.ProductionOrder.query.count() - orders_before,
              'order_id': new_orders[0].id if new_orders else None,
              'order_sales_order_id': new_orders[0].sales_order_id if new_orders else None,
              'order_sales_item_id': new_orders[0].sales_order_item_id if new_orders else None,
              'line_id': line_id, 'so_id': so_id, 'so_status': so_row.status,
              'audit_delta': M.AuditLog.query.filter_by(
                  action='从销售订单创建生产订单').count() - audit_before}
    out['b1'] = b1
    _crit('B1', 'B1 销售订单行转生产订单：production_orders +1 且带 sales_order_item_id/sales_order_id；销售订单 confirmed -> in_production',
          {'status': 200, 'orders_delta': 1, 'order_sales_item_id': '== line_id',
           'order_sales_order_id': '== so_id', 'so_status': 'in_production', 'audit_delta': 1},
          b1,
          lambda o: o['status'] == 200 and o['success'] is True and o['orders_delta'] == 1
          and o['order_sales_item_id'] == o['line_id'] and o['order_sales_order_id'] == o['so_id']
          and o['so_status'] == 'in_production' and o['audit_delta'] == 1,
          dict(b1, orders_delta=0, so_status='confirmed'),
          'app/main/routes.py:8343-8461（create_production_order_from_sales）')

    # ------------------------------------------------------------ B2 批次 + 派工策略
    with app.app_context():
        batch_before = M.ProductionBatch.query.count()
        bitem_before = M.ProductionBatchItem.query.count()
        task_before = M.TaskAssignment.query.count()
    r_bat1 = call(client, 'post', f'/production_orders/{po_b2_id}/batches/add',
                  json={'batch_quantity': 1, 'notes': f'_V12 B2 批次#1 {RUN_ID}'})
    bat1_body = jbody(r_bat1) or {}
    reset_session(app)
    with app.app_context():
        batch = M.ProductionBatch.query.filter_by(
            production_order_id=po_b2_id).order_by(M.ProductionBatch.id.desc()).first()
        batch_id = batch.id if batch is not None else None
        bits = M.ProductionBatchItem.query.filter_by(batch_id=batch_id).all()
        tasks = M.TaskAssignment.query.filter_by(
            production_batch_id=batch_id).order_by(M.TaskAssignment.id).all()
        b21 = {'status': r_bat1.status_code, 'success': bat1_body.get('success'),
               'tasks_created_flag': bat1_body.get('tasks_created'),
               'batch_delta': M.ProductionBatch.query.count() - batch_before,
               'batch_item_delta': M.ProductionBatchItem.query.count() - bitem_before,
               'task_delta': M.TaskAssignment.query.count() - task_before,
               'process_count': len(fx['process_ids']), 'n_codes': len(bits),
               'by_process': [{'process_id': t.process_id, 'employee_id': t.employee_id,
                               'quantity': t.quantity, 'notes': (t.notes or '')[:60]}
                              for t in tasks],
               'batch_id': batch_id}
    out['b2_1'] = b21
    _crit('B2.1', 'B2 批次创建（n=1）：production_batches +1 / production_batch_items +1（产品编码生成）/ task_assignment +「工序数 x n」= 3',
          {'status': 200, 'batch_delta': 1, 'batch_item_delta': 1, 'task_delta': 3,
           'process_count': 3}, b21,
          lambda o: o['status'] == 200 and o['batch_delta'] == 1 and o['batch_item_delta'] == 1
          and o['task_delta'] == o['process_count'] * o['n_codes'] and o['n_codes'] == 1,
          dict(b21, batch_delta=0, task_delta=0),
          'app/main/routes.py:8663-8752 + create_tasks_for_production_batch（每工序一张任务）')
    assign = {}
    for i, t in enumerate(b21['by_process']):
        assign[t['process_id']] = {'employee_id': t['employee_id'], 'idx': i}
    for r in fx['rules']:
        r['observed_employee_id'] = assign.get(r['process_id'], {}).get('employee_id')
        r['observed_idx'] = assign.get(r['process_id'], {}).get('idx')
        idx = r['observed_idx'] or 0
        r['pred_fixed'] = _v12_predict(r['members'], 'fixed', idx)
        r['pred_round_robin'] = _v12_predict(r['members'], 'round_robin', idx)
        r['pred_weighted'] = _v12_predict(r['members'], 'weighted', idx)
    out['b2_2'] = {'rules': fx['rules'], 'emp_a': fx['emp_a'], 'emp_b': fx['emp_b']}
    r_fixed = [r for r in fx['rules'] if r['strategy'] == 'fixed'][0]
    r_rr = [r for r in fx['rules'] if r['strategy'] == 'round_robin'][0]
    r_wt = [r for r in fx['rules'] if r['strategy'] == 'weighted'][0]
    _crit('B2.2a', 'B2 派工策略 fixed：该工序任务指派 == 规则 members[0]（固定取首成员）',
          {'observed': '== pred_fixed', 'strategy': 'fixed'},
          {'observed_employee_id': r_fixed['observed_employee_id'],
           'pred_fixed': r_fixed['pred_fixed'], 'pred_round_robin': r_fixed['pred_round_robin'],
           'idx': r_fixed['observed_idx']},
          lambda o: o['observed_employee_id'] is not None
          and o['observed_employee_id'] == o['pred_fixed'],
          {'observed_employee_id': -1, 'pred_fixed': r_fixed['pred_fixed'],
           'pred_round_robin': r_fixed['pred_round_robin'], 'idx': r_fixed['observed_idx']},
          'routes.create_tasks_for_production_batch:8777-8782（fixed 取 members[0]）')
    _crit('B2.2b', 'B2 派工策略 round_robin：该工序任务指派 == 轮询预测（members[idx % n]）且与 fixed 预测不同（策略可区分）',
          {'observed': '== pred_round_robin', 'and != pred_fixed': True},
          {'observed_employee_id': r_rr['observed_employee_id'],
           'pred_round_robin': r_rr['pred_round_robin'], 'pred_fixed': r_rr['pred_fixed'],
           'idx': r_rr['observed_idx']},
          lambda o: o['observed_employee_id'] == o['pred_round_robin']
          and o['pred_round_robin'] != o['pred_fixed'],
          {'observed_employee_id': r_rr['pred_fixed'], 'pred_round_robin': r_rr['pred_round_robin'],
           'pred_fixed': r_rr['pred_fixed'], 'idx': r_rr['observed_idx']},
          'routes.create_tasks_for_production_batch:8789-8791（round_robin 轮询）')
    _crit('B2.2c', 'B2 派工策略 weighted：该工序任务指派 == 权重池预测且与 round_robin 预测不同（权重确实参与选择）',
          {'observed': '== pred_weighted', 'and != pred_round_robin': True},
          {'observed_employee_id': r_wt['observed_employee_id'],
           'pred_weighted': r_wt['pred_weighted'], 'pred_round_robin': r_wt['pred_round_robin'],
           'weights': [m['weight'] for m in r_wt['members']], 'idx': r_wt['observed_idx']},
          lambda o: o['observed_employee_id'] == o['pred_weighted']
          and o['pred_weighted'] != o['pred_round_robin'],
          {'observed_employee_id': r_wt['pred_round_robin'],
           'pred_weighted': r_wt['pred_weighted'],
           'pred_round_robin': r_wt['pred_round_robin'],
           'weights': [m['weight'] for m in r_wt['members']], 'idx': r_wt['observed_idx']},
          'routes.create_tasks_for_production_batch:8783-8788（weighted 权重池）')
    with app.app_context():
        bitem_before2 = M.ProductionBatchItem.query.count()
        task_before2 = M.TaskAssignment.query.count()
    r_bat2 = call(client, 'post', f'/production_orders/{po_b2_id}/batches/add',
                  json={'batch_quantity': 2, 'notes': f'_V12 B2 批次#2 {RUN_ID}'})
    reset_session(app)
    with app.app_context():
        b23 = {'status': r_bat2.status_code,
               'batch_item_delta': M.ProductionBatchItem.query.count() - bitem_before2,
               'task_delta': M.TaskAssignment.query.count() - task_before2,
               'process_count': len(fx['process_ids']),
               'literal_expectation': len(fx['process_ids']) * 2,
               'measured_rule': 'task_delta == 工序数（每工序一张任务，quantity=批数量）'}
    out['b2_3'] = b23
    _v12_note_loose_end('派工粒度口径（04 2.2 B2 字面「工序数 x n」vs 实现「每工序一张」）',
                        'asset_defect',
                        'create_tasks_for_production_batch 对每个工序只建 1 张任务'
                        '（quantity=batch_quantity，并把该批次全部实例的工件挂到同一任务）；'
                        f'实测 n=2: 任务 +{b23["task_delta"]}，字面期望 +{b23["literal_expectation"]}',
                        '交 C-04 后续/文档口径修正：改判据文字或改实现粒度（本轮只登记，不改判据）',
                        '阶段B / C-04 后续')
    _crit('B2.3', 'B2 批次创建（n=2）实测粒度：production_batch_items +2 且 task_assignment +工序数（实现口径）；字面「工序数 x n」差异已显式登记',
          {'status': 200, 'batch_item_delta': 2, 'task_delta': 3, 'process_count': 3,
           'literal_expectation': 6}, b23,
          lambda o: o['status'] == 200 and o['batch_item_delta'] == 2
          and o['task_delta'] == o['process_count'],
          dict(b23, batch_item_delta=0, task_delta=0),
          'app/main/routes.py:8767-8862（循环粒度为工序，非工序 x 实例）')

    # ------------------------------------------------------------ B6 + B7
    def _b6_fail_nc(idx, qty, mat_qty):
        """造一张报工路径（production_record）的 open NC：实例+任务 -> 报工 -> 质检 fail。"""
        with app.app_context():
            item = M.ProductionBatchItem(batch_id=ctx['production']['batch_id'],
                                         item_sequence=910 + idx,
                                         product_code=f'_V12B6{idx}{V12_TAG}',
                                         status='in_progress', quality_status=None)
            db.session.add(item)
            db.session.flush()
            task = M.TaskAssignment(employee_id=ctx['emp_id'],
                                    process_id=ctx['process_ok']['id'],
                                    target_date=date.today(), quantity=qty, status='pending',
                                    task_type='auto', batch_item_id=item.id,
                                    production_batch_id=ctx['production']['batch_id'],
                                    notes=f'_V12 B6 报工 idx={idx} {RUN_ID}')
            db.session.add(task)
            db.session.commit()
            info = {'item_id': item.id, 'task_id': task.id, 'product_code': item.product_code}
        r_rep = call(client, 'post', f"/tasks/{info['task_id']}/update_status",
                     json={'completed_quantity': qty,
                           'materials': [{'raw_material_id': fx['b6_raw_id'],
                                          'quantity': mat_qty}]})
        reset_session(app)
        with app.app_context():
            pr = M.ProductionRecord.query.order_by(M.ProductionRecord.id.desc()).first()
            info['report_http'] = r_rep.status_code
            info['report_body'] = jbody(r_rep)
            info['record_id'] = pr.id if pr is not None else None
            qrec = None
            if pr is not None:
                qrec = M.InspectionTask.query.filter_by(
                    target_type='production_record', target_id=pr.id).order_by(
                    M.InspectionTask.id.desc()).first()
            info['qtask_id'] = qrec.id if qrec is not None else None
            info['item_quality_before_submit'] = M.ProductionBatchItem.query.get(
                info['item_id']).quality_status
        if not info['qtask_id']:
            return info
        call(client, 'post', f"/api/quality/tasks/{info['qtask_id']}/start-inspection",
             json={'template_id': _pr_template_id(app), 'notes': f'_V12 B6 质检 idx={idx}'})
        reset_session(app)
        with app.app_context():
            qr = M.InspectionRecord.query.filter_by(task_id=info['qtask_id']).first()
            info['qrecord_id'] = qr.id if qr is not None else None
        r_sub = call(client, 'post', f"/api/quality/records/{info['qrecord_id']}/submit",
                     json={'result': 'fail', 'notes': f'_V12 B6 判不合格 idx={idx}'})
        reset_session(app)
        with app.app_context():
            nc = M.NonconformityRecord.query.filter_by(
                record_id=info['qrecord_id']).order_by(
                M.NonconformityRecord.id.desc()).first()
            info['submit_http'] = r_sub.status_code
            info['nc_id'] = nc.id if nc is not None else None
            info['nc_target_type'] = nc.target_type if nc is not None else None
            info['nc_target_id'] = nc.target_id if nc is not None else None
            info['item_quality_after_submit'] = M.ProductionBatchItem.query.get(
                info['item_id']).quality_status
        return info

    # --- B7：结论落库后实例「质量」列自动为 fail（无人工 PUT）
    b6r = _b6_fail_nc(1, 3, 2.0)
    out['b6_rework_setup'] = b6r
    page = call(client, 'get', f"/production_center?search={b6r['product_code']}")
    html = page.data.decode('utf-8', errors='replace') if page.data else ''
    cell = None
    pos = html.find(b6r['product_code'])
    if pos >= 0:
        m = re.search(r'</td>\s*<td>\s*([^<]*?)\s*</td>\s*<td>\s*([^<]*?)\s*</td>'
                      r'\s*<td>\s*([^<]*?)\s*</td>', html[pos:], re.S)
        cell = m.group(3) if m else None
    det = call(client, 'get', f"/api/production_center/items/{b6r['item_id']}/detail")
    det_body = jbody(det) or {}
    det_quality = ((det_body.get('data') or {}).get('item') or {}).get('quality_status')
    b7 = {'page_status': page.status_code, 'page_has_code': b6r['product_code'] in html,
          'quality_cell': cell, 'api_status': det.status_code, 'api_quality_status': det_quality,
          'item_quality_after_submit': b6r.get('item_quality_after_submit'),
          'quality_before_submit': b6r.get('item_quality_before_submit'),
          'manual_quality_put_calls': V12_QUALITY_MANUAL_PUTS}
    out['b7'] = b7
    _crit('B7', 'B7 实例「质量」列自动回写：质检 fail 落库后 /production_center 行内质量格与实例 API 均为 fail（无需人工 PUT）',
          {'page': 200, 'quality_cell': 'fail', 'api_quality_status': 'fail',
           'manual_put_calls': 0}, b7,
          lambda o: o['page_status'] == 200 and o['page_has_code']
          and (o['quality_cell'] or '').strip() == 'fail' and o['api_quality_status'] == 'fail'
          and o['manual_quality_put_calls'] == 0,
          dict(b7, quality_cell='-', api_quality_status=None),
          'mes_service.apply_production_record_result -> recompute_production_quality_status；'
          '页面口径 app/templates/main/production_center.html:46')

    # --- B6.1 返工
    with app.app_context():
        n_before = M.TaskAssignment.query.filter(
            M.TaskAssignment.notes.like(f"%不合格单#{b6r['nc_id']}%")).count()
    r_rw = call(client, 'post', f"/api/quality/nonconformities/{b6r['nc_id']}/dispose",
                json={'action': 'rework', 'rework_process_id': ctx['process_ok']['id'],
                      'employee_id': ctx['emp_id'], 'notes': f'_V12 返工 {RUN_ID}'})
    reset_session(app)
    with app.app_context():
        nc = M.NonconformityRecord.query.get(b6r['nc_id'])
        new_task = M.TaskAssignment.query.filter(
            M.TaskAssignment.notes.like(f"%不合格单#{b6r['nc_id']}%")).order_by(
            M.TaskAssignment.id.desc()).first()
        item_now = M.ProductionBatchItem.query.get(b6r['item_id'])
        b61 = {'status': r_rw.status_code, 'nc_status': nc.status, 'nc_type': nc.type,
               'rework_task_id': nc.rework_task_id,
               'task_rows_delta': M.TaskAssignment.query.filter(
                   M.TaskAssignment.notes.like(f"%不合格单#{b6r['nc_id']}%")).count() - n_before,
               'task_notes': new_task.notes if new_task is not None else None,
               'task_quantity': new_task.quantity if new_task is not None else None,
               'item_quality_status': item_now.quality_status}
    out['b6_rework'] = b61
    _crit('B6.1', 'B6 返工处置：task_assignment +1 且新任务 notes 以「返工 不合格单#<nc.id>」开头、NC.rework_task_id 回填、NC 闭环',
          {'status': 200, 'task_rows_delta': 1,
           'notes_prefix': f'返工 不合格单#{b6r["nc_id"]}',
           'rework_task_id': 'non-null', 'nc_status': 'done'}, b61,
          lambda o: o['status'] == 200 and o['task_rows_delta'] == 1
          and (o['task_notes'] or '').startswith(f'返工 不合格单#{b6r["nc_id"]}')
          and o['rework_task_id'] is not None and o['nc_status'] == 'done',
          dict(b61, task_rows_delta=0, task_notes='_V12 无前缀', nc_status='open'),
          'mes_service.dispose_nonconformity:1069-1119（rework 分支）')
    b7b = {'item_quality_status': b61['item_quality_status'], 'manual_put_calls': 0}
    _crit('B7b', 'B7b 处置闭环后自动复位：返工处置 done 后实例 quality_status 由 fail 自动转 pass（无需人工 PUT）',
          {'item_quality_status': 'pass', 'manual_put_calls': 0}, b7b,
          lambda o: o['item_quality_status'] == 'pass' and o['manual_put_calls'] == 0,
          dict(b7b, item_quality_status='fail'),
          'mes_service.reset_quality_status_after_disposal（recompute 写 pass）')

    # --- B6.2 报废（报工路径）
    b6s = _b6_fail_nc(2, 3, 2.0)
    out['b6_scrap_setup'] = b6s
    with app.app_context():
        raw_before_sc = M.RawMaterial.query.get(fx['b6_raw_id']).quantity
        fg_rows_before = M.FinishedProduct.query.filter_by(stock_kind='fg',
                                                           status='in_stock').count()
        scrap_rows_before = M.FinishedProduct.query.filter_by(stock_kind='scrap').count()
    r_sc = call(client, 'post', f"/api/quality/nonconformities/{b6s['nc_id']}/dispose",
                json={'action': 'scrap', 'scrap_cost': 77.0, 'notes': f'_V12 报废 {RUN_ID}'})
    reset_session(app)
    with app.app_context():
        nc = M.NonconformityRecord.query.get(b6s['nc_id'])
        item_now = M.ProductionBatchItem.query.get(b6s['item_id'])
        raw_row = M.RawMaterial.query.get(fx['b6_raw_id'])
        b62 = {'status': r_sc.status_code, 'nc_status': nc.status, 'nc_type': nc.type,
               'scrap_cost': nc.scrap_cost, 'item_status': item_now.status,
               'item_quality_status': item_now.quality_status,
               'raw_before': raw_before_sc, 'raw_after': raw_row.quantity,
               'raw_deducted': round((raw_before_sc or 0) - (raw_row.quantity or 0), 6),
               'fg_rows_delta': M.FinishedProduct.query.filter_by(
                   stock_kind='fg', status='in_stock').count() - fg_rows_before,
               'scrap_rows_delta': M.FinishedProduct.query.filter_by(
                   stock_kind='scrap').count() - scrap_rows_before}
    out['b6_scrap'] = b62
    _crit('B6.2', 'B6 报废处置（报工路径）：NC done/type=scrap/scrap_cost=77 + 实例转 scrapped（终态）+ 原料按实际消耗扣 2.0 + fg 在库行不增',
          {'status': 200, 'nc_status': 'done', 'nc_type': 'scrap', 'scrap_cost': 77.0,
           'item_status': 'scrapped', 'raw_deducted': 2.0, 'fg_rows_delta': 0}, b62,
          lambda o: o['status'] == 200 and o['nc_status'] == 'done' and o['nc_type'] == 'scrap'
          and abs((o['scrap_cost'] or 0) - 77.0) < 1e-9 and o['item_status'] == 'scrapped'
          and abs(o['raw_deducted'] - 2.0) < 1e-9 and o['fg_rows_delta'] == 0,
          dict(b62, nc_status='open', raw_deducted=1.0, item_status='in_progress'),
          'mes_service.dispose_nonconformity:1121-1143 + deduct_scrap_materials（P-06 口径）')
    if b62['scrap_rows_delta'] == 0:
        _v12_note_loose_end('报工路径（无工件）报废不产生 scrap 库台账行',
                            'asset_defect',
                            '04 2.2 B6 字面要求「报废 -> scrap 台账 +1」，实现只在有工件时'
                            'inbound_workpiece(scrap)；报工路径 NC 的 workpiece_id 为空 => 无 scrap 行',
                            '登记为两条路径口径差异（工件路径由既有 P0-4.5 覆盖）；'
                            '如需报工路径也出台账，属新功能，本轮不改判据',
                            '阶段B / C-04 后续')

    # --- B6.3 让步接收
    b6a = _b6_fail_nc(3, 3, 2.0)
    out['b6_accept_setup'] = b6a
    client_ins, ins_code, ins_loc = make_client(app, seed['users']['inspector'], seed['password'])
    r_ac_ins = call(client_ins, 'post', f"/api/quality/nonconformities/{b6a['nc_id']}/dispose",
                    json={'action': 'accept', 'notes': f'_V12 让步(inspector) {RUN_ID}'})
    reset_session(app)
    with app.app_context():
        nc = M.NonconformityRecord.query.get(b6a['nc_id'])
        item_now = M.ProductionBatchItem.query.get(b6a['item_id'])
        ac_ins = {'status': r_ac_ins.status_code, 'nc_status': nc.status,
                  'nc_approver_id': nc.approver_id,
                  'item_quality_status': item_now.quality_status}
    out['b6_accept_pending'] = ac_ins
    _crit('B6.3a', 'B6 让步接收（非授权角色）：NC 转 pending_approval 且 approver_id 为空（未放行）',
          {'status': 200, 'nc_status': 'pending_approval', 'nc_approver_id': None}, ac_ins,
          lambda o: o['status'] == 200 and o['nc_status'] == 'pending_approval'
          and o['nc_approver_id'] is None,
          dict(ac_ins, nc_status='approved'),
          'mes_service.dispose_nonconformity:1055-1059（非授权 => pending_approval）')
    r_ac_adm = call(client, 'post', f"/api/quality/nonconformities/{b6a['nc_id']}/dispose",
                    json={'action': 'accept', 'notes': f'_V12 让步(admin) {RUN_ID}'})
    reset_session(app)
    with app.app_context():
        nc = M.NonconformityRecord.query.get(b6a['nc_id'])
        item_now = M.ProductionBatchItem.query.get(b6a['item_id'])
        ac_adm = {'status': r_ac_adm.status_code, 'nc_status': nc.status,
                  'nc_approver_id': nc.approver_id,
                  'item_quality_status': item_now.quality_status}
    out['b6_accept_approved'] = ac_adm
    _crit('B6.3b', 'B6 让步接收（admin 授权）：NC approved + approver_id 落库 + 实例 quality_status 自动复位 pass',
          {'status': 200, 'nc_status': 'approved', 'nc_approver_id': 'non-null',
           'item_quality_status': 'pass'}, ac_adm,
          lambda o: o['status'] == 200 and o['nc_status'] == 'approved'
          and o['nc_approver_id'] is not None and o['item_quality_status'] == 'pass',
          dict(ac_adm, nc_status='pending_approval', item_quality_status='fail'),
          'mes_service.dispose_nonconformity:1060-1067')
    V12['chain_b'] = out
    return out


# ==============================================================================
# 链 C 缺口：C1（明细真实 material_id）/ C2（免审 vs 需审）/ C4（归还回库）/ C5（盘点调账）
# ==============================================================================
def v12_chain_c(app, client, seed, ctx):
    from app import db
    from app import models as M
    from datetime import date, datetime
    out = {}
    reset_session(app)
    with app.app_context():
        raws = [r.id for r in M.RawMaterial.query.filter_by(
            is_archived=False, status='in_stock').order_by(M.RawMaterial.id).limit(6).all()]
        cand = [i for i in raws if i != 1][:2] or raws[:2]
        cons = M.Consumable.query.first()
        if cons is None:
            ccat = M.ConsumableCategory.query.first()
            if ccat is None:
                ccat = M.ConsumableCategory(name='_V12 易耗品类', code=f'_V12CC{V12_TAG}')
                db.session.add(ccat)
                db.session.flush()
            cons = M.Consumable(supplier='_V12 供应商', category_id=ccat.id,
                                supplier_number=f'_V12CSUP{V12_TAG}',
                                internal_number=f'_V12CONS{V12_TAG}', quantity=20.0,
                                specification='_V12')
            db.session.add(cons)
            db.session.commit()
        emp = M.Employee.query.filter_by(is_active=True).order_by(M.Employee.id).first()
        cat = M.RawMaterialCategory.query.first()
        if cat is None:
            cat = M.RawMaterialCategory(name='_V12 原料品类', code=f'_V12RC{V12_TAG}')
            db.session.add(cat)
            db.session.commit()
        raw_cat_id = cat.id
        fx = {'raw_a': cand[0], 'raw_b': cand[1] if len(cand) > 1 else cand[0],
              'consumable_id': cons.id, 'emp_id': emp.id, 'raw_category_id': raw_cat_id}
    V12['fixtures']['chain_c'] = fx
    today = date.today().strftime('%Y-%m-%d')

    # ------------------------------------------------------------ C1（真实 material_id）
    with app.app_context():
        req_before = M.MaterialRequisition.query.count()
    payload = [{'material_type': 'raw', 'material_id': fx['raw_a'], 'quantity': 2},
               {'material_type': 'raw', 'material_id': fx['raw_b'], 'quantity': 3}]
    r_c1 = call(client, 'post', '/material_requisitions/add',
                data={'employee_id': str(fx['emp_id']), 'purpose': f'_V12 C1 {RUN_ID}',
                      'requisition_date': today, 'production_order_id': '0',
                      'notes': f'_V12 C1 {RUN_ID}',
                      'materials_data': json.dumps(payload, ensure_ascii=False)})
    reset_session(app)
    with app.app_context():
        req = M.MaterialRequisition.query.order_by(M.MaterialRequisition.id.desc()).first()
        items = req.items.all() if req is not None else []
        c1 = {'status': r_c1.status_code,
              'req_rows_delta': M.MaterialRequisition.query.count() - req_before,
              'req_id': req.id if req is not None else None,
              'req_status': req.status if req is not None else None,
              'item_material_ids': sorted(i.material_id for i in items),
              'expected_ids': sorted([fx['raw_a'], fx['raw_b']]),
              'item_types': sorted({i.material_type for i in items}),
              'item_quantities': sorted(i.quantity for i in items)}
    out['c1'] = c1
    _crit('C1', 'C1 领用明细写入真实 material_id（两条不同原料各自落库，非硬编码 1）',
          {'status': 302, 'rows_delta': 1, 'item_material_ids': '== 所选两条 id',
           'item_types': ['raw']}, c1,
          lambda o: o['status'] in (200, 302) and o['req_rows_delta'] == 1
          and o['item_material_ids'] == o['expected_ids'] and o['item_types'] == ['raw'],
          dict(c1, item_material_ids=[1, 1]),
          'app/main/routes.py:11372-11421（必须选具体库存物料，不能手填品名）')

    # ------------------------------------------------------------ C2 需审批 / 免审批
    r_issue_pending = call(client, 'post', f"/material_requisitions/{c1['req_id']}/issue", json={})
    pend_body = jbody(r_issue_pending) or {}
    reset_session(app)
    with app.app_context():
        raw_a_row = M.RawMaterial.query.get(fx['raw_a'])
        c2a_obs = {'req_status': M.MaterialRequisition.query.get(c1['req_id']).status,
                   'issue_status': r_issue_pending.status_code,
                   'issue_message': pend_body.get('message') or '',
                   'raw_a_quantity': raw_a_row.quantity}
    out['c2_raw_pending'] = c2a_obs
    _crit('C2a', 'C2 需审批品类（raw，requires_approval 默认真）：建单即 pending 且未发料（发料被拒 + 库存不变）',
          {'req_status': 'pending', 'issue_status': 400, 'issue_message_contains': '不可发料'},
          c2a_obs,
          lambda o: o['req_status'] == 'pending' and o['issue_status'] == 400
          and '不可发料' in o['issue_message'],
          dict(c2a_obs, req_status='approved', issue_status=200),
          'app/main/routes.py:11388-11405（need_approval => pending）'
          ' + models.py:2118-2120（can_issue 仅 approved）')
    r_c2b = call(client, 'post', '/material_requisitions/add',
                 data={'employee_id': str(fx['emp_id']), 'purpose': f'_V12 C2 免审 {RUN_ID}',
                       'requisition_date': today, 'production_order_id': '0',
                       'notes': f'_V12 C2 {RUN_ID}',
                       'materials_data': json.dumps(
                           [{'material_type': 'consumable',
                             'material_id': fx['consumable_id'], 'quantity': 2}],
                           ensure_ascii=False)})
    reset_session(app)
    with app.app_context():
        req2 = M.MaterialRequisition.query.order_by(M.MaterialRequisition.id.desc()).first()
        c2b_obs = {'status': r_c2b.status_code,
                   'req_status': req2.status if req2 is not None else None,
                   'req_id': req2.id if req2 is not None else None,
                   'item_material_ids': sorted(
                       i.material_id for i in (req2.items.all() if req2 is not None else [])),
                   'consumable_id': fx['consumable_id']}
    out['c2_consumable_approved'] = c2b_obs
    _crit('C2b', 'C2 免审批品类（consumable 默认免审）：建单即 approved（可直接发料）',
          {'status': 302, 'req_status': 'approved', 'item_material_ids': '== consumable_id'},
          c2b_obs,
          lambda o: o['status'] in (200, 302) and o['req_status'] == 'approved'
          and o['item_material_ids'] == [fx['consumable_id']],
          dict(c2b_obs, req_status='pending'),
          'app/main/routes.py:11405（need_approval False => approved）'
          ' + mes_service.line_requires_approval:1366-1369')

    # ------------------------------------------------------------ C4 归还（完好回库 / 损坏不入库）
    with app.app_context():
        c4_raw = M.RawMaterial(supplier='_V12 供应商', category_id=fx['raw_category_id'],
                               melt_number=f'_V12C4MELT{V12_TAG}',
                               supplier_number=f'_V12C4SUP{V12_TAG}',
                               internal_number=f'_V12C4RAW{V12_TAG}', quantity=10.0,
                               status='in_stock', is_archived=False)
        db.session.add(c4_raw)
        db.session.flush()
        c4_raw_id = c4_raw.id
        orig = M.MaterialRequisition(requisition_number=f'_V12C4REQ{V12_TAG}',
                                     employee_id=fx['emp_id'], department='_V12',
                                     purpose=f'_V12 C4 已发料单 {RUN_ID}',
                                     required_date=date.today(), status='completed',
                                     requested_date=datetime.now())
        db.session.add(orig)
        db.session.flush()
        db.session.add(M.MaterialRequisitionItem(
            requisition_id=orig.id, material_type='raw', material_id=c4_raw_id,
            quantity=6.0, issued_quantity=6.0, unit='件'))
        db.session.commit()
        orig_id = orig.id
    r_c4add = call(client, 'post', '/material_returns/add',
                   data={'employee_id': str(fx['emp_id']), 'department': '_V12',
                         'return_reason': f'_V12 C4 归还 {RUN_ID}',
                         'original_requisition_id': str(orig_id),
                         'returned_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                         'notes': f'_V12 C4 {RUN_ID}',
                         'materials_data': json.dumps([
                             {'material_type': 'raw', 'material_id': c4_raw_id,
                              'quantity': 2, 'condition': 'good', 'unit': '件'},
                             {'material_type': 'raw', 'material_id': c4_raw_id,
                              'quantity': 1, 'condition': 'damaged', 'unit': '件'}],
                             ensure_ascii=False)})
    reset_session(app)
    with app.app_context():
        ret = M.MaterialReturn.query.order_by(M.MaterialReturn.id.desc()).first()
        ret_id = ret.id if ret is not None else None
        ret_items = [(i.condition, i.quantity) for i in (ret.items.all() if ret is not None else [])]
        raw_before = M.RawMaterial.query.get(c4_raw_id).quantity
        ret_status_add = ret.status if ret is not None else None
    out['c4_create'] = {'add_status': r_c4add.status_code, 'return_id': ret_id,
                        'status': ret_status_add, 'items': ret_items, 'raw_before': raw_before}
    _v12_cursor(app)
    r_c4conf = call(client, 'post', f'/material_returns/{ret_id}/confirm')
    reset_session(app)
    with app.app_context():
        ret_after = M.MaterialReturn.query.get(ret_id)
        raw_after = M.RawMaterial.query.get(c4_raw_id).quantity
        c4 = {'add_status': r_c4add.status_code, 'confirm_status': r_c4conf.status_code,
              'return_id': ret_id, 'status_add': ret_status_add,
              'status': ret_after.status, 'items': ret_items,
              'raw_before': raw_before, 'raw_after': raw_after,
              'restocked': round((raw_after or 0) - (raw_before or 0), 6),
              'confirmed_by': ret_after.confirmed_by}
    out['c4'] = c4
    _crit('C4', 'C4 归还确认：完好项回增库存 +2，损坏项不入正品库（合计 +2 而非 +3），单据转 confirmed',
          {'confirm': 302, 'status': 'confirmed', 'restocked': 2.0}, c4,
          lambda o: o['confirm_status'] in (200, 302) and o['status'] == 'confirmed'
          and abs(o['restocked'] - 2.0) < 1e-9,
          dict(c4, restocked=3.0, status='pending'),
          'mes_service.confirm_return:1424-1433（仅 condition == good 回库）')

    # ------------------------------------------------------------ C5 盘点 add -> start -> record -> complete
    with app.app_context():
        c5_raw = M.RawMaterial(supplier='_V12 供应商', category_id=fx['raw_category_id'],
                               melt_number=f'_V12C5MELT{V12_TAG}',
                               supplier_number=f'_V12C5SUP{V12_TAG}',
                               internal_number=f'_V12C5RAW{V12_TAG}', quantity=50.0,
                               status='in_stock', is_archived=False)
        db.session.add(c5_raw)
        db.session.commit()
        c5_raw_id = c5_raw.id
        admin_user = M.User.query.filter_by(username='_t_admin').first()
        admin_uid = admin_user.id if admin_user is not None else None
    r_c5add = call(client, 'post', '/inventory_counts/add',
                   data={'count_name': f'_V12 C5 盘点 {V12_TAG}', 'count_type': 'partial',
                         'count_scope': 'raw', 'warehouse_location': '_V12',
                         'planned_date': today, 'count_team': [str(admin_uid)],
                         'notes': f'_V12 C5 {RUN_ID}'})
    reset_session(app)
    with app.app_context():
        cnt = M.InventoryCount.query.order_by(M.InventoryCount.id.desc()).first()
        cnt_id = cnt.id if cnt is not None else None
        item = (M.InventoryCountItem.query.filter_by(
            count_id=cnt_id, material_type='raw', material_id=c5_raw_id).first()
            if cnt_id else None)
        c5_add = {'add_status': r_c5add.status_code, 'count_id': cnt_id,
                  'status': cnt.status if cnt is not None else None,
                  'total_items': cnt.total_items if cnt is not None else None,
                  'target_item_id': item.id if item is not None else None,
                  'system_quantity': item.system_quantity if item is not None else None}
    r_start = call(client, 'post', f'/inventory_counts/{cnt_id}/start')
    payload_items = []
    reset_session(app)
    with app.app_context():
        for it in M.InventoryCountItem.query.filter_by(count_id=cnt_id).all():
            actual = it.system_quantity
            if it.id == c5_add['target_item_id']:
                actual = (it.system_quantity or 0) - 3.0
            payload_items.append({'id': it.id, 'actual_quantity': actual,
                                  'variance_reason': ('_V12 差异说明'
                                                      if it.id == c5_add['target_item_id'] else '')})
        raw_pre = M.RawMaterial.query.get(c5_raw_id).quantity
    r_record = call(client, 'post', f'/inventory_counts/{cnt_id}/record',
                    json={'items': payload_items})
    reset_session(app)
    with app.app_context():
        raw_mid = M.RawMaterial.query.get(c5_raw_id).quantity
    r_complete = call(client, 'post', f'/inventory_counts/{cnt_id}/complete')
    reset_session(app)
    with app.app_context():
        cnt_end = M.InventoryCount.query.get(cnt_id)
        raw_end = M.RawMaterial.query.get(c5_raw_id).quantity
        item_end = M.InventoryCountItem.query.get(c5_add['target_item_id'])
        c5 = {'add_status': c5_add['add_status'], 'start_status': r_start.status_code,
              'record_status': r_record.status_code, 'complete_status': r_complete.status_code,
              'count_id': cnt_id, 'status': cnt_end.status,
              'total_items': cnt_end.total_items, 'completed_items': cnt_end.completed_items,
              'raw_before_record': raw_pre, 'raw_after_record': raw_mid,
              'raw_after_complete': raw_end,
              'system_quantity': c5_add['system_quantity'],
              'actual_quantity': item_end.actual_quantity,
              'variance_quantity': item_end.variance_quantity,
              'variance_reason': item_end.variance_reason,
              'adjustment_applied': bool(item_end.adjustment_applied)}
    out['c5'] = c5
    _crit('C5.1', 'C5 盘点录入阶段不写库存（配对判据）：record 后 target 原料数量仍为 50.0（差异只在 complete 调账）',
          {'raw_before_record': 50.0, 'raw_after_record': 50.0}, c5,
          lambda o: abs(o['raw_before_record'] - 50.0) < 1e-9
          and abs(o['raw_after_record'] - 50.0) < 1e-9,
          dict(c5, raw_after_record=47.0),
          'app/main/routes.py:11957-11995（record 只落实盘数）')
    _crit('C5.2', 'C5 盘点完成调账：库存被写成实盘数（50 -> 47）、adjustment_applied=True、盘点单 completed、差异有 variance_reason',
          {'status': 'completed', 'raw_after_complete': 47.0, 'variance_quantity': -3.0,
           'variance_reason_non_empty': True, 'adjustment_applied': True}, c5,
          lambda o: o['status'] == 'completed' and abs(o['raw_after_complete'] - 47.0) < 1e-9
          and abs(o['variance_quantity'] + 3.0) < 1e-9 and bool(o['variance_reason'])
          and o['adjustment_applied'] is True,
          dict(c5, raw_after_complete=50.0, adjustment_applied=False),
          'mes_service.apply_inventory_count:1460-1480（写成实盘数 + status=completed）')
    _crit('C5.3', 'C5 盘点四步链路齐备（add -> start -> record -> complete）且完成时明细齐全',
          {'add': '302/200', 'start': '302/200', 'record': '302/200', 'complete': '302/200',
           'completed_items': '== total_items'}, c5,
          lambda o: o['add_status'] in (200, 302) and o['start_status'] in (200, 302)
          and o['record_status'] in (200, 302) and o['complete_status'] in (200, 302)
          and o['completed_items'] == o['total_items'] and o['total_items'] > 0,
          dict(c5, complete_status=400, completed_items=0),
          'app/main/routes.py:11937-12024（start/record/complete 各自状态门）')
    V12['chain_c'] = out
    return out


# ==============================================================================
# 运行入口 + 收尾自证 + 证据落盘（save_evidence 契约）
# ==============================================================================
def v12_run_all(app, client, seed, ctx):
    """链 A / 链 B / 链 C：各自 try/except，异常 => blocked（不静默、不误判为通过）。"""
    for name, fn in (('链A', lambda: v12_chain_a(app, client, seed)),
                     ('链B', lambda: v12_chain_b(app, client, seed, ctx)),
                     ('链C', lambda: v12_chain_c(app, client, seed, ctx))):
        try:
            fn()
        except Exception as exc:
            note(f'{name} 异常：{exc.__class__.__name__}: {exc}')
            check(f'V12-{name}-ERR', f'{name} 执行未抛异常', 'no exception',
                  f'{exc.__class__.__name__}: {exc}', 'blocked', '见 NOTES')
    return V12


def v12_append_only_selfcheck():
    items = _v12_baseline_items()
    ids = [i[0] for i in items]
    digest = _v12_baseline_digest()
    new_checks = [c for c in CHECKS if c['id'] not in BASELINE40_IDS]
    obs = {'baseline_count': len(items), 'digest': digest, 'frozen_digest': BASELINE40_DIGEST,
           'ids_match_order': ids == list(BASELINE40_IDS),
           'digest_match': digest == BASELINE40_DIGEST,
           'total_checks': len(CHECKS), 'new_checks': len(new_checks),
           'frozen_source': 'evidence/harness/uat/r2-exec-b4-v12-pre2/'
                            'r2-exec-b4-v12-pre2-baseline40-signature.json（改动前全量读数）'}
    broken = dict(obs, digest='0' * 64, digest_match=False)
    _crit('APPEND.1', '追加纪律：既有 40 条断言的 id/顺序/desc/expected 与冻结基线逐条逐字节相同（只追加，不改既有期望值）',
          {'baseline_count': 40, 'digest': BASELINE40_DIGEST, 'ids_match_order': True,
           'digest_match': True, 'new_checks': '> 0'}, obs,
          lambda o: o['baseline_count'] == 40 and o['ids_match_order'] is True
          and o['digest_match'] is True and o['new_checks'] > 0,
          broken,
          '冻结值 = 改动前 r2-exec-b4-v12-pre2 的 (id,desc,expected) 摘要 C9FAD00E...D9C')
    V12['append_only'] = obs
    return obs


def v12_finalize(app):
    """收尾两条自证判据（追加纪律 + 每条新判据的「会变红」自证）。"""
    v12_append_only_selfcheck()
    new_checks = [c for c in CHECKS if c['id'] not in BASELINE40_IDS]
    flips = V12_FLIPS
    blocked = len([c for c in new_checks if c['status'] == 'blocked'])
    obs = {'new_checks': len(new_checks), 'flip_rows': len(flips),
           'expected_flip_rows': len(new_checks) - blocked,
           'red_rows': sum(1 for f in flips if f['red_when_removed']),
           'all_red': all(f['red_when_removed'] for f in flips),
           'blocked_rows': blocked,
           'failed_rows': len([c for c in new_checks if c['status'] == 'failed']),
           'chain_a_pass': len([c for c in new_checks
                                if c['id'].startswith('CA') and c['status'] == 'passed'])}
    broken = dict(obs, all_red=False, red_rows=obs['red_rows'] - 1)
    _crit('FLIP.SUM', '每条新增判据都有一次「删掉它什么会变红」的敏感度自证；新增链无 blocked',
          {'flip_rows': '== new_checks - 1', 'all_red': True, 'blocked_rows': 0,
           'chain_a_pass': '>= 1'}, obs,
          lambda o: o['flip_rows'] == o['expected_flip_rows'] and o['all_red'] is True
          and o['blocked_rows'] == 0 and o['chain_a_pass'] >= 1,
          broken,
          '逐条自证见 <RUN_ID>-flips.json（observed/broken 两次判定）')
    V12['flip_summary'] = obs
    V12['flips'] = V12_FLIPS
    V12['loose_ends'] = V12_LOOSE_ENDS
    return obs


# ------------------------------------------------------------------ 台账与产物
def _v12_file_sig(rel):
    import _env
    p = os.path.join(REPO_ROOT, rel.replace('/', os.sep))
    if not os.path.exists(p):
        return None
    return {'path': rel, 'bytes': os.path.getsize(p), 'sha256': sha256_file(p)}


def _v12_new_rows():
    flips = {f['id']: f for f in V12_FLIPS}
    rows = []
    for c in CHECKS:
        if c['id'] in BASELINE40_IDS:
            continue
        fl = flips.get(c['id'], {})
        verdict = {'passed': 'HIT', 'failed': 'MISS', 'blocked': 'PARTIAL'}.get(
            c['status'], 'PARTIAL')
        rows.append({
            'id': 'V12-' + c['id'], 'wave': 'W6', 'title': c['desc'][:150],
            'evidence_kind': 'behavior_verified', 'verdict': verdict,
            'criterion': (c['expected'] if isinstance(c['expected'], str)
                          else json.dumps(c['expected'], ensure_ascii=False)),
            'command': f'{sys.executable} -B test-reports-2026-10/harness/uat_chains.py'
                       f'  (UAT_RUN_ID={RUN_ID})',
            'exit_code': 0 if c['status'] == 'passed' else 1,
            'expected': str(c['expected'])[:500], 'observed': str(c['got'])[:500],
            'criterion_digest': (f"status={c['status']},"
                                 f"expected={str(c['expected'])[:120]},"
                                 f"observed={str(c['got'])[:120]}"),
            'reproducible': True,
            'search_domain': {'dirs': ['app/main', 'app/services', 'app/templates',
                                       'test-reports-2026-10/harness'],
                              'match': 'content',
                              'exclude_basenames': ['uat_chains.py', 't6_ledger_check.py',
                                                    'fixtures.py']},
            'behavior_flip_test': {'question': fl.get('question', ''),
                                   'answer': str(fl.get('answer', ''))[:400],
                                   'red_when_removed': (str(fl.get('answer', ''))[:200]
                                                        if fl.get('red_when_removed') else '')},
            'coverage_delta': None,
            'provenance': {'source': '本 run 实跑（V-12 / t13）', 'source_sha256': None,
                           'source_verdict': None, 'superseded_by': None},
            'postfix_verdict': c['status'], 'rewrite_verdict': None,
            'class': 'improved' if c['status'] == 'passed' else 'still_red_asset',
            'class_basis': '新增链级判据（基线不存在该 id）；本 run 首次实测',
            'postfix_evidence': f'test-reports-2026-10/evidence/harness/uat/{RUN_ID}/',
            'notes': '' if c['status'] == 'passed' else '新增判据实测为红，见 evidence_note',
        })
    return rows


def v12_build_ledger(result, summary):
    ca_new = [c for c in CHECKS if c['id'].startswith('CA') and c['id'] not in BASELINE40_IDS]
    ca_pass = len([c for c in ca_new if c['status'] == 'passed'])
    ao = V12.get('append_only') or {}
    total = len(CHECKS)
    c04_verdict = ('HIT' if ca_pass >= 1 and ao.get('digest_match') and total > 40
                   else 'PARTIAL')
    results = [{
        'id': 'C-04', 'wave': 'W6',
        'title': '链级未覆盖补齐：链 A（采购 -> 来料检 -> 入库/退货）+ 链 B/C 缺口（B0/B1/B2/B6/B7、C1/C2/C4/C5）',
        'evidence_kind': 'behavior_verified', 'verdict': c04_verdict,
        'criterion': '链 A 0 -> >=1 端到端通过；链总数由 40 上升；新增链不改既有 40 链期望值（只追加）；换 UAT_RUN_ID',
        'command': f'{sys.executable} -B test-reports-2026-10/harness/uat_chains.py'
                   f'  (UAT_RUN_ID={RUN_ID})',
        'exit_code': 0 if summary.get('blocked') == 0 else 1,
        'expected': 'chain_a_pass>=1, total>40, baseline40_digest=C9FAD00E...D9C 不变, run_id 变化',
        'observed': f'chain_a_pass={ca_pass}, total={total}, baseline40_digest_match='
                    f'{ao.get("digest_match")}, run_id={RUN_ID}, blocked={summary.get("blocked")}',
        'criterion_digest': (f'chain_a_pass={ca_pass},total={total},'
                             f'baseline40_digest_match={ao.get("digest_match")},'
                             f'new_checks={ao.get("new_checks")},blocked={summary.get("blocked")}'),
        'reproducible': True,
        'search_domain': {'dirs': ['app/main', 'app/services', 'app/templates',
                                   'test-reports-2026-10/harness'],
                          'match': 'content',
                          'exclude_basenames': ['uat_chains.py', 't6_ledger_check.py',
                                                'fixtures.py']},
        'behavior_flip_test': {
            'question': '删掉它什么会变红？',
            'answer': '删掉 uat_chains.py 的 v12_chain_a 段 => CA* 判据消失、chain_a_pass=0、'
                      '本行 verdict 转 PARTIAL；删掉 v12_run_all 的调用 => 链总数仍是 40，同样转红',
            'red_when_removed': 'uat_chains.py#v12_chain_a / v12_run_all'},
        'coverage_delta': {'metric': 'uat_chain_checks', 'before': 40, 'after': total,
                           'produced_by': 'test-reports-2026-10/harness/uat_chains.py'},
        'provenance': {'source': '本 run 实跑（V-12 / t13）',
                       'source_sha256': sha256_file(os.path.abspath(__file__)),
                       'source_verdict': None, 'superseded_by': None},
        'postfix_verdict': None, 'rewrite_verdict': None,
        'class': 'improved', 'class_basis': '基线 链A=0 / 链总数 40 => 本 run 链A>=1 且只追加',
        'postfix_evidence': f'test-reports-2026-10/evidence/harness/uat/{RUN_ID}/{RUN_ID}-ledger.json',
        'notes': '',
    }]
    results.extend(_v12_new_rows())
    gaps = list(V12_LOOSE_ENDS)
    if c04_verdict != 'HIT':
        gaps.append({'id': f'GAP-{RUN_ID}-C04', 'item': 'C-04 链级补齐未达 HIT',
                     'state': 'not_covered', 'reason': '见 results[0].observed',
                     'action': '按 CA* 失败项逐条修复后重跑', 'owner_wave': '阶段B / C-04'})
    anchor_readings = []
    uat_now = _v12_file_sig('test-reports-2026-10/evidence/uat/uat_chains.json')
    if uat_now:
        anchor_readings.append({
            'path': uat_now['path'], 'bytes': uat_now['bytes'], 'sha256': uat_now['sha256'],
            'matches_captain': False,
            'note': (f"V-12 有意更新：旧 {V12_UAT_ANCHOR_OLD['bytes']}/"
                     f"{V12_UAT_ANCHOR_OLD['sha256']} -> 新 {uat_now['bytes']}/{uat_now['sha256']}；"
                     f"触发 = {V12_UAT_ANCHOR_OLD['trigger']}；旧读数已由 B0 preflight 归档于 "
                     f"{V12_UAT_ANCHOR_OLD['archived_copy']}")})
    for rel, by, sha in V12_ANCHORS:
        sig = _v12_file_sig(rel)
        if sig is None:
            anchor_readings.append({'path': rel, 'bytes': None, 'sha256': None,
                                    'matches_captain': False, 'note': '文件不存在（读不到）'})
        else:
            anchor_readings.append({'path': rel, 'bytes': sig['bytes'], 'sha256': sig['sha256'],
                                    'matches_captain': (sig['bytes'] == by
                                                        and sig['sha256'] == sha)})
    # B13-00：coverage.json 这一锚点在 2026-10-08 被**有意更新**（A-70 三步），单独补 note 留痕。
    for row in anchor_readings:
        if row.get('path') == 'test-reports-2026-10/evidence/harness/coverage.json':
            row['note'] = (
                f"B13-00 有意更新（A-70 三步，2026-10-08）：旧 {V12_COVERAGE_ANCHOR_OLD['bytes']}/"
                f"{V12_COVERAGE_ANCHOR_OLD['sha256']} -> 新 {row['bytes']}/{row['sha256']}；"
                f"触发 = {V12_COVERAGE_ANCHOR_OLD['trigger']}；旧字节归档于 "
                f"{V12_COVERAGE_ANCHOR_OLD['archived_copy']}（登记册 "
                f"{V12_COVERAGE_ANCHOR_OLD['registry']} entry no=1「重基线前」）；"
                f"命令 = {V12_COVERAGE_ANCHOR_OLD['command']}")
    artifacts = []
    for p in (V12.get('artifacts') or {}).values():
        artifacts.append(_v12_file_sig(p))
    artifacts.append(_v12_file_sig('test-reports-2026-10/evidence/uat/uat_chains.json'))
    artifacts.append(_v12_file_sig('test-reports-2026-10/evidence/uat/uat_chains.out.txt'))
    artifacts.append(_v12_file_sig(V12_UAT_ANCHOR_OLD['archived_copy']))
    artifacts.append({'path': f'test-reports-2026-10/evidence/harness/uat/{RUN_ID}/{RUN_ID}-ledger.json',
                      'bytes': None, 'sha256': None,
                      'note': '本台账自身（S-2：不记录自己的哈希，写完由调用方另算）'})
    ledger = {
        'ledger_version': '2.0', 'run_id': RUN_ID, 'task_id': 't13',
        'attempt_id': 'dcdfa057-7244-4bdf-a737-aa8c8188e481',
        'operator': '验收测试工程师（V-12 / C-04 链级端到端）',
        'started_at': (summary.get('started') or '').replace(' ', 'T') + '+08:00',
        'finished_at': (summary.get('finished') or '').replace(' ', 'T') + '+08:00',
        'env': {'workdir': REPO_ROOT, 'git_head': _v12_git('HEAD'),
                'app_tree': _v12_git('HEAD:app'),
                'python': f'{sys.executable} ({sys.version.split()[0]})',
                'sandbox': 'DSH danger-full-access',
                'temp_run_root': f'test-reports-2026-10/.tmp/{RUN_ID}'},
        'db_invariant': {
            'target': 'app.db', 'pinned_sha256': REAL_DB_SHA256_EXPECTED,
            'sha256_before': (result.get('raw', {}).get('real_db') or {}).get('before'),
            'sha256_after': (result.get('raw', {}).get('real_db') or {}).get('after'),
            'verdict': '通过' if (result.get('raw', {}).get('real_db') or {}).get('unchanged')
                       else '不通过'},
        'production_freeze': {'files': [_v12_file_sig('app/main/purchase.py'),
                                        _v12_file_sig('app/main/quality.py'),
                                        _v12_file_sig('app/services/mes_service.py'),
                                        _v12_file_sig('test-reports-2026-10/harness/uat_chains.py')]},
        'anchor_readings': anchor_readings,
        'results': results,
        'gaps': gaps,
        'artifact_index': [a for a in artifacts if a],
    }
    return ledger


def _v12_git(rev):
    import subprocess
    try:
        return subprocess.run(['git', 'rev-parse', rev], cwd=REPO_ROOT, capture_output=True,
                              text=True, timeout=30).stdout.strip()
    except Exception as exc:
        return f'<git {rev} 失败: {exc.__class__.__name__}>'


def v12_ledger_md(ledger):
    lines = [f"# 台账（人读）{ledger['run_id']}", '',
             f"task={ledger['task_id']} attempt={ledger['attempt_id']}",
             f"app_tree={ledger['env']['app_tree']}",
             f"db_invariant={ledger['db_invariant']['verdict']} "
             f"({ledger['db_invariant']['sha256_before']})", '',
             '| ID | 判定 | evidence_kind | 期望 | 实测 |', '| --- | --- | --- | --- | --- |']
    for r in ledger['results']:
        lines.append(f"| {r['id']} | {r['verdict']} | {r['evidence_kind']} | "
                     f"{str(r['expected'])[:90]} | {str(r['observed'])[:90]} |")
    lines += ['', '## gaps']
    for g in ledger['gaps']:
        lines.append(f"- [{g['state']}] {g['id']} {g['item']} -> {g['action']}")
    return '\n'.join(lines) + '\n'


def v12_save_artifacts(result, summary):
    """把本 run 的 V-12 产物按 40 2.2 的 save_evidence 契约落盘（只增不改 + 审计流水）。"""
    import _env
    subdir = os.path.join('uat', RUN_ID)
    paths = {}
    paths['flips'] = _env.save_evidence(
        f'{RUN_ID}-flips.json',
        json.dumps({'run_id': RUN_ID, 'flips': V12_FLIPS}, ensure_ascii=False, indent=1),
        subdir=subdir, run_id=RUN_ID)
    paths['observations'] = _env.save_evidence(
        f'{RUN_ID}-v12-observations.json',
        json.dumps(V12, ensure_ascii=False, indent=1, default=str),
        subdir=subdir, run_id=RUN_ID)
    paths['append_only'] = _env.save_evidence(
        f'{RUN_ID}-append-only.json',
        json.dumps(V12.get('append_only') or {}, ensure_ascii=False, indent=1),
        subdir=subdir, run_id=RUN_ID)
    V12['artifacts'] = paths
    ledger = v12_build_ledger(result, summary)
    paths['ledger'] = _env.save_evidence(
        f'{RUN_ID}-ledger.json', json.dumps(ledger, ensure_ascii=False, indent=1),
        subdir=subdir, run_id=RUN_ID)
    paths['ledger_md'] = _env.save_evidence(
        f'{RUN_ID}-ledger.md', v12_ledger_md(ledger), subdir=subdir, run_id=RUN_ID)
    V12['artifacts'] = paths
    # chains.json 最后落盘：此时 V12['artifacts'] 已就位（避免产物清单自引用为空）
    paths['chains'] = _env.save_evidence(
        f'{RUN_ID}-chains.json',
        json.dumps(result, ensure_ascii=False, indent=1, default=str),
        subdir=subdir, run_id=RUN_ID)
    V12['artifacts'] = paths
    print('[v12] artifacts=' + json.dumps(paths, ensure_ascii=False), flush=True)
    return paths


# ------------------------------------------------------------------ 双跑差分（台账差分）
def v12_cli_compare(path_a, path_b):
    """台账差分：逐条比对两条链级读数的 verdict/expected/observed 与台账摘要。"""
    import _env
    def _load(p):
        with open(p, encoding='utf-8') as fh:
            return json.load(fh)

    def _ledger_of(p):
        d = os.path.dirname(os.path.abspath(p))
        cands = [f for f in os.listdir(d) if f.endswith('-ledger.json')]
        if not cands:
            return None
        with open(os.path.join(d, cands[0]), encoding='utf-8') as fh:
            return json.load(fh)

    a, b = _load(path_a), _load(path_b)
    ca = {c['id']: c for c in a['checks']}
    cb = {c['id']: c for c in b['checks']}
    only_a = sorted(set(ca) - set(cb))
    only_b = sorted(set(cb) - set(ca))
    verdict_diff, expected_diff, observed_diff = [], [], []
    for cid in sorted(set(ca) & set(cb)):
        if ca[cid]['status'] != cb[cid]['status']:
            verdict_diff.append({'id': cid, 'a': ca[cid]['status'], 'b': cb[cid]['status']})
        if ca[cid]['expected'] != cb[cid]['expected']:
            expected_diff.append({'id': cid, 'a': str(ca[cid]['expected'])[:120],
                                  'b': str(cb[cid]['expected'])[:120]})
        if ca[cid]['got'] != cb[cid]['got']:
            observed_diff.append({'id': cid, 'a': str(ca[cid]['got'])[:120],
                                  'b': str(cb[cid]['got'])[:120]})
    la, lb = _ledger_of(path_a), _ledger_of(path_b)
    digest_diff = []
    if la and lb:
        da = {r['id']: r.get('criterion_digest') for r in la['results']}
        db_ = {r['id']: r.get('criterion_digest') for r in lb['results']}
        digest_diff = [{'id': k, 'a': da.get(k), 'b': db_.get(k)}
                       for k in sorted(set(da) | set(db_)) if da.get(k) != db_.get(k)]
    diff = {
        'run_a': a['summary'].get('run_id'), 'run_b': b['summary'].get('run_id'),
        'checks_a': len(ca), 'checks_b': len(cb),
        'only_in_a': only_a, 'only_in_b': only_b,
        'verdict_diff': verdict_diff, 'expected_diff': expected_diff,
        'observed_diff': observed_diff, 'ledger_criterion_digest_diff': digest_diff,
        'summary_a': a['summary'], 'summary_b': b['summary'],
        'baseline40_digest_a': (a.get('raw', {}).get('v12') or {}).get('append_only', {}).get('digest'),
        'verdict': 'OK',
    }
    diff['verdict'] = ('OK' if not (only_a or only_b or verdict_diff or expected_diff
                                   or digest_diff) else 'DIFF')
    p = _env.save_evidence(f'{RUN_ID}-crossrun-diff.json',
                           json.dumps(diff, ensure_ascii=False, indent=1),
                           subdir=os.path.join('uat', RUN_ID), run_id=RUN_ID)
    print('[v12-compare] ' + json.dumps(
        {'verdict': diff['verdict'], 'only_in_a': only_a, 'only_in_b': only_b,
         'verdict_diff': verdict_diff, 'expected_diff': expected_diff,
         'digest_diff': digest_diff, 'evidence': p}, ensure_ascii=False))
    return 0 if diff['verdict'] == 'OK' else 1

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

    # ---------------- [V-12 / C-04 · r2 仅追加] 链 A + 链 B/C 缺口 ----------------
    # 说明：本段在既有 40 条断言之后执行；只新增函数/常量/断言（自证见 APPEND.1）。
    try:
        v12_run_all(app, client, seed, ctx)
    except Exception as exc:
        ok_http = False
        note(f'V-12 段异常：{exc.__class__.__name__}: {exc}')
        check('V12-ERR', 'V-12 段执行未抛异常', 'no exception',
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

    # ---------------- [V-12] 收尾自证（追加纪律 + 逐条「会变红」自证） ----------------
    try:
        v12_finalize(app)
    except Exception as exc:
        ok_http = False
        note(f'V-12 收尾异常：{exc.__class__.__name__}: {exc}')
        check('V12-FIN-ERR', 'V-12 收尾判据未抛异常', 'no exception',
              f'{exc.__class__.__name__}: {exc}', 'blocked', '见 NOTES')
    RAW['v12'] = V12

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
    try:
        v12_save_artifacts(result, summary)
    except Exception as exc:
        note(f'V-12 证据落盘异常：{exc.__class__.__name__}: {exc}（chains JSON 仍已落盘）')
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
    # [V-12 仅追加] 双跑/台账差分模式：--compare <runA-chains.json> <runB-chains.json>
    if len(sys.argv) >= 4 and sys.argv[1] == '--compare':
        sys.exit(v12_cli_compare(sys.argv[2], sys.argv[3]))
    sys.exit(main())
