# -*- coding: utf-8 -*-
"""B15-07 双链件数守恒对拍（报工链 vs 工件链）—— 供 ``ci_gates.py`` 第 16 步调用。

目的（批次15 B15-07 / I5）
=========================
同一生产实例上把**两条产出链**各跑一次，对拍它们落到正品台账上的**件数合计**：

* 报工链读数 ``A``：``SUM(production_record.quantity)``（本次报工记录，行数 1）；
* 工件链读数 ``B``：``SUM(finished_product.quantity)``（本次对拍的 N 件工件对应的 fg 行，行数 N）。

两条链的件数都是「件」，但**行数不同构**（A 侧 1 行 N 件，B 侧 N 行 1 件）——因此本判据
**必须读件数合计，禁止读行数**：读行数会得到 1 != N 的假红。

判据语义（判据 ID 取自 ``test-reports-2026-10/B15-00-契约冻结.md`` §1/§5，供 ci_gates 判定）
==========================================================================================
``C-B15-07.a``   两侧件数守恒且等于报工件数：``A == B == 报工件数``，口径 = 件数合计。
``C-B15-07.a2``  「行数不同而件数相同」的构造成立：``A_rows(1) != B_rows(N)`` 而件数相同
                 ⇒ 证明本判据与行数解耦（敏感性/反假红构造）。
``C-B15-07.a3``  报工链的**入库产出**件数（``finished_product`` 中 ``workpiece_id IS NULL``
                 且 ``product_number`` = 实例产品编码的行）也等于报工件数（两条链都真跑到了入库）。
``C-B15-07.b``   两侧基数均 > 0（``COUNT(*)`` 恒打印）：防「空集恒等 0 == 0」被当绿。
``C-B15-07.d``   阴性对照：工件链全 ``pass`` ⇒ ``nonconformity_records`` Δ=0（不得凭空造 NC）。
``C-B15-07.e``   件数增量只来自本次动作：全库 fg 件数合计增量 ``== A + C``（= 2N）。

退出码（脚本自带失败出口）
==========================
``0`` = 判据全过；``1`` = 判据不满足（件数不守恒 / 空集 / 夹具未产出 / 注入偏差）；
``2`` = 用法与参数错误（缺 ``--out``、坏 ``--perturb``、``--pieces < 2`` 等）。

``--perturb <json>``（注入判据输入，供 ci_gates ``--inject-step`` 使用）
----------------------------------------------------------------------
JSON：``{"side": "report"|"workpiece", "delta": ±N, "reason": "..."}``。
**两种写法都接**：内联 JSON（`--perturb '{"side":"report","delta":1}'`，ci_gates 注入用）
或 JSON 文件路径（便于留档复现）；非 ``{`` 开头即按路径解释。
语义 = **判据输入声明**：把人造偏差加在声明侧的件数读数上（**不改台账、不写库**），用来证明
「判据不满足 ⇒ exit 1 且指名侧别与差值」。声明侧 = 唯一一个读数偏离报工件数的一侧。

夹具装配顺序（现场实测约束，非任意选择）
========================================
``qc_gate_allows_output``（``app/services/mes_service.py``）的序 5 会遍历
``batch_item_workpieces(item)``：只要实例名下**存在未完成的工件质检任务**，报工链的末道入库即被
拒绝（实测原因逐字：``_ccWP01: 存在未完成的质检任务``）。因此本脚本的装配顺序固定为
「报工链先跑 → 再给工件建质检任务 → 工件链后跑」；脚本内 ``interference_probe`` 段落会把这条
干涉关系**实测留痕**（独立实例，断言「报工记录已落库、产出未入正品库」），供复核顺序依据。

``--b15-06-injection``（默认关，B15-06 提交缝证据，不参与 ci_gates 判据）
=======================================================================
同一次运行里追加 B15-06（``quality.py`` 提交缝单事务）的注入证据：
``R1`` 修复后注入（``apply_inspection_result`` 抛错 ⇒ 四读数同时回到动作前）、
``R2`` 修复后阴性对照（``result=fail`` ⇒ NC +1 ∧ ``quality_status`` ``None→fail``）、
``R3`` 预镜像（合成树装 ``git show HEAD:app/main/quality.py``，子进程复跑同一注入
⇒ 「质检记录已提交、NC/门禁未落地」）。默认关，避免污染 ci_gates 第 16 步的判据输出。

运行（副本库，绝不碰真实 ``app.db``）
====================================
``/opt/wage-venv/bin/python -B test-reports-2026-10/harness/chain_count_consistency.py
--out test-reports-2026-10/.tmp/run-b15/chain.json``
"""

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import time
import traceback

try:  # 历史教训（uat_chains.py：39-47）：CP936 下 UnicodeEncodeError 会让判据静默消失
    sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace')
    sys.stderr.reconfigure(encoding='utf-8', errors='backslashreplace')
except Exception:  # pragma: no cover
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
REPORTS_ROOT = os.path.dirname(HERE)
REPO_ROOT = os.path.dirname(REPORTS_ROOT)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import fixtures  # noqa: E402  （必须在任何 app.* 导入之前）
from _env import (  # noqa: E402
    REAL_DB_SHA256_EXPECTED, RUN_ID, SCRIPTS_DIR, TMP_ROOT, ensure_dir,
    run_child, save_evidence, sha256_file)

TAG = 'cc'
DEFAULT_PIECES = 3           # ≥2：才可能构造「行数 1 vs 行数 N 而件数相同」
MIN_PIECES = 2

EXIT_OK = 0
EXIT_CRITERION_FAILED = 1
EXIT_USAGE = 2

CONSOLE_MARK = '[cc] '

CHECKS = []
NOTES = []
RAW = {}


# ------------------------------------------------------------------ 输出
def note(msg):
    NOTES.append(msg)
    print(CONSOLE_MARK + msg, flush=True)


def check(cid, desc, expected, got, ok, evidence=''):
    status = 'passed' if ok else 'failed'
    CHECKS.append({'id': cid, 'desc': desc, 'expected': expected, 'got': got,
                   'status': status, 'evidence': evidence})
    print('[%s] %s %s | expected=%s got=%s %s' % ('OK' if ok else 'FAIL', cid, desc,
                                                  expected, got, evidence), flush=True)
    return ok


class UsageError(Exception):
    """用法/参数错误 ⇒ 退出码 2。"""


# ------------------------------------------------------------------ HTTP 小工具（与 uat_chains.py 同法）
def make_client(app, username, password):
    app.config['WTF_CSRF_ENABLED'] = False
    client = app.test_client()
    r = client.post('/auth/login', data={'username': username, 'password': password},
                    follow_redirects=False)
    return client, r.status_code, r.headers.get('Location')


def call(client, method, path, **kw):
    """打真端点并把 HTTPException 转成普通响应对象，避免一条异常终止整轮。"""
    try:
        return getattr(client, method)(path, **kw)
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


def reset_session(app):
    """清掉 scoped session（必须在 app_context 内；Flask-SQLAlchemy 的 scopefunc 需要它）。"""
    from app import db
    with app.app_context():
        db.session.remove()


class LogCapture(logging.Handler):
    """抓 WARNING/INFO 文本（用于留痕门禁拒绝原因；纯观测，不参与判据）。"""

    def __init__(self):
        logging.Handler.__init__(self, level=logging.INFO)
        self.messages = []

    def emit(self, record):
        try:
            self.messages.append(record.getMessage())
        except Exception:
            pass


def capture_log(reason):
    handler = LogCapture()
    targets = [logging.getLogger(), logging.getLogger('mes_service'),
               logging.getLogger('routes'), logging.getLogger('app')]
    attached = []
    for lg in targets:
        try:
            lg.addHandler(handler)
            attached.append(lg)
        except Exception:
            pass
    return handler, attached


def release_log(handler, attached, needle):
    for lg in attached:
        try:
            lg.removeHandler(handler)
        except Exception:
            pass
    return [m for m in handler.messages if needle in m]


# ------------------------------------------------------------------ 夹具
def build_fixture(app, tag=TAG, pieces=DEFAULT_PIECES):
    """造「同一订单/同一实例」的两条链前置：产品/路线/订单/批次/实例/两个任务/N 件工件。

    关键：``TaskWorkpiece`` 挂在 ``task_wp`` 上，而 ``task_wp.batch_item_id == item.id``
    ⇒ ``mes_service.batch_item_workpieces(item)`` 能看到这 N 件工件（报工链门禁序 5 的作用面）。
    """
    from app import db
    from app import models as M
    from datetime import date, timedelta
    reset_session(app)
    ctx = {'tag': tag, 'pieces': pieces}
    with app.app_context():
        admin = M.User.query.filter_by(username='_t_admin').first()
        emp = M.Employee.query.first()
        if admin is None or emp is None:
            raise RuntimeError('seed_all 未产出 _t_admin / Employee，夹具无法装配')
        proc = M.ProcessPrice(process_code='_%s_OK' % tag, process_name='_%s 末道工序' % tag,
                              price=20.0, version=1, needs_inspection=True)
        db.session.add(proc)
        db.session.flush()
        prod = M.Product(product_code='_%s_P' % tag, product_name='_%s 产品' % tag,
                         drawing_number='_%s-DWG' % tag, model='_%s-M' % tag,
                         status='active', created_by=admin.id)
        db.session.add(prod)
        db.session.flush()
        db.session.add(M.ProductProcess(product_id=prod.id, process_id=proc.id, sequence=1))
        db.session.flush()
        order = M.ProductionOrder(product_id=prod.id, planned_quantity=pieces,
                                  planned_start_date=date.today(),
                                  planned_end_date=date.today() + timedelta(days=7),
                                  order_number='_%sPO' % tag, created_by=admin.id)
        db.session.add(order)
        db.session.flush()
        batch = M.ProductionBatch(production_order_id=order.id, batch_quantity=pieces,
                                  batch_number='_%sB' % tag)
        db.session.add(batch)
        db.session.flush()
        item = M.ProductionBatchItem(batch_id=batch.id, item_sequence=1,
                                     product_code='_%sITEM' % tag, status='in_progress',
                                     quality_status=None)
        db.session.add(item)
        db.session.flush()
        task_report = M.TaskAssignment(employee_id=emp.id, process_id=proc.id,
                                       target_date=date.today(), quantity=pieces,
                                       status='pending', task_type='auto',
                                       batch_item_id=item.id, production_batch_id=batch.id,
                                       notes='_%s 报工链任务' % tag)
        db.session.add(task_report)
        db.session.flush()
        task_wp = M.TaskAssignment(employee_id=emp.id, process_id=proc.id,
                                   target_date=date.today(), quantity=pieces,
                                   status='pending', task_type='auto',
                                   batch_item_id=item.id, production_batch_id=batch.id,
                                   notes='_%s 工件链任务' % tag)
        db.session.add(task_wp)
        db.session.flush()
        workpieces = []
        for i in range(1, pieces + 1):
            wp = M.Workpiece(code='_%sWP%02d' % (tag, i), status='assembled',
                             product_id=prod.id, current_process_id=proc.id)
            db.session.add(wp)
            db.session.flush()
            db.session.add(M.TaskWorkpiece(task_id=task_wp.id, workpiece_id=wp.id))
            db.session.flush()
            workpieces.append({'workpiece_id': wp.id, 'code': wp.code})
        db.session.commit()
        ctx.update({'admin_id': admin.id, 'emp_id': emp.id, 'process_id': proc.id,
                    'product_id': prod.id, 'order_id': order.id, 'batch_id': batch.id,
                    'item_id': item.id, 'item_product_code': item.product_code,
                    'task_report_id': task_report.id,
                    'task_report_global_sn': task_report.global_sn,
                    'task_wp_id': task_wp.id, 'workpieces': workpieces})
    return ctx


def attach_qc_tasks(app, ctx, tag=None):
    """给工件链的 N 件工件建「在办质检任务 + 待判记录」（这一步必须在报工链跑完之后）。"""
    from app import db
    from app import models as M
    from datetime import date
    tag = tag or ctx['tag']
    reset_session(app)
    with app.app_context():
        rows = []
        for i, wp in enumerate(ctx['workpieces'], start=1):
            itask = M.InspectionTask(global_sn=M.SerialNumber.get_next_number(),
                                     target_type='workpiece', target_id=wp['workpiece_id'],
                                     inspector_id=ctx['admin_id'], status='in_progress',
                                     created_by=ctx['admin_id'],
                                     notes='_%s 工件质检任务 %d' % (tag, i))
            db.session.add(itask)
            db.session.flush()
            irec = M.InspectionRecord(global_sn=M.SerialNumber.get_next_number(),
                                      task_id=itask.id, inspector_id=ctx['admin_id'],
                                      inspection_date=date.today(), result='pending',
                                      notes='_%s 工件质检记录 %d' % (tag, i))
            db.session.add(irec)
            db.session.flush()
            rows.append({'workpiece_id': wp['workpiece_id'], 'code': wp['code'],
                         'inspection_task_id': itask.id, 'record_id': irec.id})
        db.session.commit()
    ctx['qc'] = rows
    return rows


# ------------------------------------------------------------------ 量测（件数口径）
SQL_SIDE = ("SELECT COALESCE(SUM(quantity),0) AS pieces, COUNT(*) AS rows "
            "FROM finished_product WHERE stock_kind='fg' AND status='in_stock' ")


def snapshot(app, ctx):
    """读两侧件数合计 + 基数 + 全库 fg 件数 + 过程读数。"""
    from app import db
    reset_session(app)
    with app.app_context():
        report = db.session.execute(db.text(
            'SELECT COALESCE(SUM(quantity),0) AS pieces, COUNT(*) AS rows '
            'FROM production_record WHERE global_sn=:sn'),
            {'sn': ctx['task_report_global_sn']}).first()
        ids = ','.join(str(int(w['workpiece_id'])) for w in ctx['workpieces'])
        wp = db.session.execute(db.text(
            SQL_SIDE + 'AND workpiece_id IN (%s)' % ids)).first()
        out_rows = db.session.execute(db.text(
            SQL_SIDE + 'AND workpiece_id IS NULL AND product_number=:c'),
            {'c': ctx['item_product_code']}).first()
        total = db.session.execute(db.text(SQL_SIDE)).first()
        counters = {}
        for t in ('production_record', 'nonconformity_records', 'inspection_tasks',
                  'inspection_records', 'audit_log', 'workpieces', 'finished_product'):
            counters[t] = db.session.execute(db.text('SELECT COUNT(*) FROM %s' % t)).scalar()
        return {
            'A_report_record_pieces': float(report[0]), 'A_report_record_rows': int(report[1]),
            'B_workpiece_pieces': float(wp[0]), 'B_workpiece_rows': int(wp[1]),
            'C_report_output_pieces': float(out_rows[0]), 'C_report_output_rows': int(out_rows[1]),
            'fg_total_pieces': float(total[0]), 'fg_total_rows': int(total[1]),
            'counters': counters,
        }


def target_pieces(reading):
    """报工件数（判据的公共基准）：本次报工记录上的件数合计。"""
    return reading['A_report_record_pieces']


def judge(reading, perturb=None):
    """纯函数：给定读数（+可选判据输入偏差声明）⇒ 判据结果与偏差归因。"""
    adj = {'report': 0.0, 'workpiece': 0.0}
    if perturb:
        adj[perturb['side']] += float(perturb['delta'])
    a = reading['A_report_record_pieces'] + adj['report']
    b = reading['B_workpiece_pieces'] + adj['workpiece']
    c = reading['C_report_output_pieces']
    target = target_pieces(reading)
    verdict = {
        'A_pieces': a, 'B_pieces': b, 'C_pieces': c, 'target_pieces': target,
        'A_rows': reading['A_report_record_rows'],
        'B_rows': reading['B_workpiece_rows'],
        'C_rows': reading['C_report_output_rows'],
        'a_conserved': (a == b == target),
        'a2_rows_differ': (reading['A_report_record_rows'] != reading['B_workpiece_rows']),
        'a3_output_matches': (c == target),
        'b_nonempty': (a > 0 and b > 0),
        'deviation_side': None, 'deviation_diff': None, 'deviation_reading': '',
    }
    dev = [s for s, v in (('report', a), ('workpiece', b)) if v != target]
    if len(dev) == 1:
        side = dev[0]
        verdict['deviation_side'] = side
        verdict['deviation_diff'] = round((a if side == 'report' else b) - target, 6)
        verdict['deviation_reading'] = (f'{side} 侧件数 {a if side == "report" else b:g} '
                                        f'≠ 报工件数 {target:g}（差值 {verdict["deviation_diff"]:+g}）')
    elif len(dev) == 2:
        verdict['deviation_side'] = 'both'
        verdict['deviation_diff'] = round(a - target, 6)
        verdict['deviation_reading'] = (f'两侧件数 report={a:g} / workpiece={b:g} 均 ≠ '
                                        f'报工件数 {target:g}')
    return verdict


# ------------------------------------------------------------------ 两条链
def run_report_chain(client, ctx, pieces):
    resp = call(client, 'post', '/tasks/%d/update_status' % ctx['task_report_id'],
                json={'completed_quantity': pieces})
    return {'http': resp.status_code, 'body': jbody(resp)}


def run_workpiece_chain(client, ctx, result='pass'):
    out = []
    for row in ctx.get('qc', []):
        resp = call(client, 'post', '/api/quality/records/%d/submit' % row['record_id'],
                    json={'result': result})
        out.append({'record_id': row['record_id'], 'workpiece_id': row['workpiece_id'],
                    'http': resp.status_code, 'body': jbody(resp)})
    return out


# ------------------------------------------------------------------ 干涉观测（非判据，B15-07 夹具顺序的实测依据）
def interference_probe(app, client, ctx, tag=TAG):
    """独立实例上实测「同实例已挂待检工件 ⇒ 报工链被工件门禁前置拒绝」。非判据、不影响退出码。"""
    from app import db
    from app import models as M
    from datetime import date, timedelta
    reset_session(app)
    probe = {'tag': tag, 'status': 'skipped'}
    try:
        with app.app_context():
            admin = M.User.query.filter_by(username='_t_admin').first()
            emp = M.Employee.query.first()
            item = M.ProductionBatchItem(batch_id=ctx['batch_id'], item_sequence=77,
                                         product_code='_%sPROBEITEM' % tag,
                                         status='in_progress', quality_status=None)
            db.session.add(item)
            db.session.flush()
            task = M.TaskAssignment(employee_id=emp.id, process_id=ctx['process_id'],
                                    target_date=date.today(), quantity=ctx['pieces'],
                                    status='pending', task_type='auto',
                                    batch_item_id=item.id, production_batch_id=ctx['batch_id'],
                                    notes='_%s 干涉探针报工任务' % tag)
            db.session.add(task)
            db.session.flush()
            wp = M.Workpiece(code='_%sPROBEWP' % tag, status='assembled',
                             product_id=ctx['product_id'], current_process_id=ctx['process_id'])
            db.session.add(wp)
            db.session.flush()
            db.session.add(M.TaskWorkpiece(task_id=task.id, workpiece_id=wp.id))
            db.session.flush()
            itask = M.InspectionTask(global_sn=M.SerialNumber.get_next_number(),
                                     target_type='workpiece', target_id=wp.id,
                                     inspector_id=admin.id, status='in_progress',
                                     created_by=admin.id, notes='_%s 干涉探针质检任务' % tag)
            db.session.add(itask)
            db.session.flush()
            db.session.commit()
            probe.update({'item_id': item.id, 'task_id': task.id, 'task_global_sn': task.global_sn,
                          'workpiece_id': wp.id, 'workpiece_code': wp.code,
                          'pending_qc_task_id': itask.id,
                          'item_product_code': item.product_code})
        handler, attached = capture_log('门禁')
        try:
            resp = call(client, 'post', '/tasks/%d/update_status' % probe['task_id'],
                        json={'completed_quantity': ctx['pieces']})
        finally:
            reasons = release_log(handler, attached, '门禁')
        reset_session(app)
        with app.app_context():
            row = db.session.execute(db.text(
                'SELECT COALESCE(SUM(quantity),0), COUNT(*) FROM production_record '
                'WHERE global_sn=:sn'), {'sn': probe['task_global_sn']}).first()
            probe['report_record_pieces'] = float(row[0])
            probe['report_record_rows'] = int(row[1])
            probe['fg_probe_pieces'] = float(db.session.execute(db.text(
                SQL_SIDE + 'AND product_number=:c'),
                {'c': probe['item_product_code']}).scalar() or 0)
        probe['http'] = resp.status_code
        probe['body'] = jbody(resp)
        probe['gate_refusal_messages'] = reasons
        body = probe['body'] if isinstance(probe['body'], dict) else {}
        body_message = body.get('message')
        probe['body_message'] = body_message if isinstance(body_message, str) else None
        # HTTP 侧读数优先：当前树 routes.py 在写台账**之前**就按工件门禁拒绝（:3617-3620 把任务已挂的
        # TaskWorkpiece 工件码补齐后逐个过 mes_service.qc_gate_allows(wp)，:3635-3637 返回 400），
        # 故拒绝原因原文在 body 里，日志捕获只作旁证。
        if probe['body_message'] and '存在未完成的质检任务' in probe['body_message']:
            probe['refusal_source'] = 'http_body'
            probe['refusal_reason'] = probe['body_message']
        elif reasons:
            probe['refusal_source'] = 'log'
            probe['refusal_reason'] = reasons[0]
        else:
            probe['refusal_source'] = None
            probe['refusal_reason'] = None
        probe['ledger_writes'] = bool(probe['report_record_rows'] > 0
                                      or probe['fg_probe_pieces'] > 0)
        probe['partial_landing'] = bool(probe['report_record_rows'] > 0
                                        and probe['fg_probe_pieces'] == 0)
        if probe['refusal_reason'] and probe['http'] >= 400 and not probe['ledger_writes']:
            probe['status'] = 'refused_precheck_no_ledger_write'
            probe['refusal_stage'] = 'workpiece_precheck(routes.py:3635 qc_gate_allows)'
        elif probe['refusal_reason'] and probe['http'] >= 400:
            probe['status'] = 'refused_with_partial_landing'
            probe['refusal_stage'] = 'unknown(after_ledger_write)'
        elif probe['fg_probe_pieces'] > 0:
            probe['status'] = 'inbound_ok'
            probe['refusal_stage'] = None
        else:
            probe['status'] = 'unclassified'
            probe['refusal_stage'] = None
            probe['unclassified_reason'] = ('HTTP=%s 且既无拒绝原因也无入库产出，无法归因'
                                            % probe['http'])
        probe['observed'] = True
    except Exception as exc:  # 观测段永不阻断判据
        probe['status'] = 'error'
        probe['error'] = '%s: %s' % (exc.__class__.__name__, exc)
        probe['traceback_tail'] = traceback.format_exc().splitlines()[-3:]
    RAW['interference_probe'] = probe
    if probe.get('observed'):
        note('干涉观测（非判据）：报工记录行数=%d 件数=%g，产出 fg 件数=%g，HTTP=%s；'
             '拒绝原因（来源 %s）= %s；台账写入=%s；归因=%s'
             % (probe['report_record_rows'], probe['report_record_pieces'],
                probe['fg_probe_pieces'], probe['http'], probe['refusal_source'] or '无',
                probe['refusal_reason'] or '（无）', probe['ledger_writes'], probe['status']))
    else:
        note('干涉观测（非判据）未完成：%s' % probe.get('error', probe['status']))
    return probe


# ------------------------------------------------------------------ B15-06 提交缝（opt-in）
B15_06_NC_FIELDS = {'type': 'rework', 'status': 'open', 'handling_result': '待处置',
                    'target_type': 'production_record'}


def build_b15_06_fixture(app, tag, pieces):
    """B15-06 用迷你夹具：任务/报工记录/质检任务/待判记录（同一实例）。"""
    from app import db
    from app import models as M
    from datetime import date, timedelta
    reset_session(app)
    with app.app_context():
        admin = M.User.query.filter_by(username='_t_admin').first()
        emp = M.Employee.query.first()
        proc = M.ProcessPrice(process_code='_%s_OK' % tag, process_name='_%s 末道工序 %s' % (TAG, tag),
                              price=20.0, version=1, needs_inspection=True)
        db.session.add(proc)
        db.session.flush()
        prod = M.Product(product_code='_%s_P' % tag, product_name='_%s 产品 %s' % (TAG, tag),
                         drawing_number='_%s-DWG' % tag, model='_%s-M' % tag,
                         status='active', created_by=admin.id)
        db.session.add(prod)
        db.session.flush()
        db.session.add(M.ProductProcess(product_id=prod.id, process_id=proc.id, sequence=1))
        db.session.flush()
        order = M.ProductionOrder(product_id=prod.id, planned_quantity=pieces,
                                  planned_start_date=date.today(),
                                  planned_end_date=date.today() + timedelta(days=7),
                                  order_number='_%sPO' % tag, created_by=admin.id)
        db.session.add(order)
        db.session.flush()
        batch = M.ProductionBatch(production_order_id=order.id, batch_quantity=pieces,
                                  batch_number='_%sB' % tag)
        db.session.add(batch)
        db.session.flush()
        item = M.ProductionBatchItem(batch_id=batch.id, item_sequence=6,
                                     product_code='_%sITEM' % tag, status='in_progress',
                                     quality_status=None)
        db.session.add(item)
        db.session.flush()
        task = M.TaskAssignment(employee_id=emp.id, process_id=proc.id, target_date=date.today(),
                                quantity=pieces, status='pending', task_type='auto',
                                batch_item_id=item.id, production_batch_id=batch.id,
                                notes='_%s 提交缝任务' % tag)
        db.session.add(task)
        db.session.flush()
        pr = M.ProductionRecord(employee_id=emp.id, process_id=proc.id, date=date.today(),
                                quantity=pieces, global_sn=task.global_sn)
        db.session.add(pr)
        db.session.flush()
        itask = M.InspectionTask(global_sn=M.SerialNumber.get_next_number(),
                                 target_type='production_record', target_id=pr.id,
                                 inspector_id=admin.id, status='in_progress',
                                 created_by=admin.id, notes='_%s 提交缝质检任务' % tag)
        db.session.add(itask)
        db.session.flush()
        irec = M.InspectionRecord(global_sn=M.SerialNumber.get_next_number(), task_id=itask.id,
                                  inspector_id=admin.id, inspection_date=date.today(),
                                  result='pending', notes='_%s 提交缝记录' % tag)
        db.session.add(irec)
        db.session.flush()
        db.session.commit()
        return {'tag': tag, 'pieces': pieces, 'item_id': item.id, 'task_id': task.id,
                'task_global_sn': task.global_sn, 'production_record_id': pr.id,
                'inspection_task_id': itask.id, 'record_id': irec.id,
                'product_code': item.product_code}


def build_b15_06_control(app, ctx, tag):
    """在同一 production_record 上再建一条在办质检任务 + 待判记录（阴性对照用）。"""
    from app import db
    from app import models as M
    from datetime import date
    with app.app_context():
        itask = M.InspectionTask(global_sn=M.SerialNumber.get_next_number(),
                                 target_type='production_record',
                                 target_id=ctx['production_record_id'],
                                 inspector_id=M.User.query.filter_by(
                                     username='_t_admin').first().id,
                                 status='in_progress',
                                 created_by=M.User.query.filter_by(username='_t_admin').first().id,
                                 notes='_%s 对照质检任务' % tag)
        db.session.add(itask)
        db.session.flush()
        irec = M.InspectionRecord(global_sn=M.SerialNumber.get_next_number(), task_id=itask.id,
                                  inspector_id=itask.inspector_id,
                                  inspection_date=date.today(), result='pending',
                                  notes='_%s 对照记录' % tag)
        db.session.add(irec)
        db.session.flush()
        db.session.commit()
        return {'inspection_task_id': itask.id, 'record_id': irec.id}


def seam_snapshot(app, ctx, extra_record_id=None):
    """提交缝四读数：记录 result / 任务 status / audit_log 行数 / NC 行数 / 实例 quality_status。"""
    from app import db
    from app import models as M
    reset_session(app)
    with app.app_context():
        rec = db.session.get(M.InspectionRecord, extra_record_id or ctx['record_id'])
        itask = db.session.get(M.InspectionTask, ctx['inspection_task_id'])
        item = db.session.get(M.ProductionBatchItem, ctx['item_id'])
        newest_nc = M.NonconformityRecord.query.order_by(M.NonconformityRecord.id.desc()).first()
        row = newest_nc
        return {
            'record_result': None if rec is None else rec.result,
            'inspection_task_status': None if itask is None else itask.status,
            'item_quality_status': None if item is None else item.quality_status,
            'audit_rows': db.session.execute(db.text('SELECT COUNT(*) FROM audit_log')).scalar(),
            'nc_rows': db.session.execute(
                db.text('SELECT COUNT(*) FROM nonconformity_records')).scalar(),
            'newest_nc_id': None if row is None else row.id,
            'nc_row': None if row is None else {
                'id': row.id, 'record_id': row.record_id, 'type': row.type,
                'status': row.status, 'handling_result': row.handling_result,
                'target_type': row.target_type},
        }


def raise_injector(*_args, **_kwargs):
    raise RuntimeError('B15-06 注入：第二段 mes_service.apply_inspection_result(record) 抛错')


def run_b15_06_probe(app, tag='cc06', pieces=2, with_control=True, label='post_fix'):
    """在同一 app 上跑提交缝注入（R1）+ 可选阴性对照（R2）。父/子进程共用同一段探针代码。"""
    client, login_status, login_loc = make_client(app, '_t_admin', 'test_pw_123')
    ctx = build_b15_06_fixture(app, tag, pieces)
    out = {'label': label, 'tag': tag, 'login': {'status': login_status, 'location': login_loc},
           'fixture': ctx}
    from app.services import mes_service
    before = seam_snapshot(app, ctx)
    original = mes_service.apply_inspection_result
    mes_service.apply_inspection_result = raise_injector
    try:
        resp = call(client, 'post', '/api/quality/records/%d/submit' % ctx['record_id'],
                    json={'result': 'fail'})
    finally:
        mes_service.apply_inspection_result = original
    after = seam_snapshot(app, ctx)
    out['injection'] = {
        'injector': 'app.services.mes_service.apply_inspection_result → RuntimeError',
        'http': resp.status_code, 'body': jbody(resp), 'before': before, 'after': after,
        'delta': {
            'record_result': [before['record_result'], after['record_result'],
                              before['record_result'] != after['record_result']],
            'inspection_task_status': [before['inspection_task_status'],
                                       after['inspection_task_status'],
                                       before['inspection_task_status'] != after['inspection_task_status']],
            'item_quality_status': [before['item_quality_status'], after['item_quality_status'],
                                    before['item_quality_status'] != after['item_quality_status']],
            'audit_delta': after['audit_rows'] - before['audit_rows'],
            'nc_delta': after['nc_rows'] - before['nc_rows'],
        },
    }
    if with_control:
        ctl = build_b15_06_control(app, ctx, tag)
        ctx2 = dict(ctx)
        ctx2['record_id'] = ctl['record_id']
        ctx2['inspection_task_id'] = ctl['inspection_task_id']
        before2 = seam_snapshot(app, ctx2)
        resp2 = call(client, 'post', '/api/quality/records/%d/submit' % ctl['record_id'],
                     json={'result': 'fail'})
        after2 = seam_snapshot(app, ctx2)
        nc = seam_snapshot(app, ctx2)['nc_row']
        out['control'] = {
            'http': resp2.status_code, 'body': jbody(resp2), 'before': before2, 'after': after2,
            'delta': {'record_result': [before2['record_result'], after2['record_result']],
                      'item_quality_status': [before2['item_quality_status'],
                                              after2['item_quality_status']],
                      'audit_delta': after2['audit_rows'] - before2['audit_rows'],
                      'nc_delta': after2['nc_rows'] - before2['nc_rows']},
            'newest_nc_row': nc,
            'nc_fields_ok': bool(nc) and all(nc.get(k) == v for k, v in B15_06_NC_FIELDS.items()),
        }
    return out


def evaluate_b15_06(probe, expect):
    """把 B15-06 探针读数折算成判据行。

    ``expect='post_fix'``：注入后四读数同时回到动作前；
    ``expect='control'`` ：不注入 ⇒ result=fail ∧ NC +1 ∧ quality_status None→fail ∧ NC 四字段；
    ``expect='prefix'``  ：预镜像 ⇒ 「质检记录已提交、NC/门禁未落地」。
    """
    ok_all = True
    if expect == 'post_fix':
        d = probe['injection']['delta']
        ok = (d['record_result'][1] == probe['injection']['before']['record_result']
              and not d['record_result'][2] and d['audit_delta'] == 0 and d['nc_delta'] == 0
              and not d['item_quality_status'][2] and not d['inspection_task_status'][2]
              and probe['injection']['http'] >= 400)
        ok_all &= check('C-B15-06.a',
                        '注入第二段失败 ⇒ 四读数同时回到动作前（result/任务/audit/NC/quality_status）',
                        'result=%r auditΔ=0 ncΔ=0 quality_status=[%r→%r] HTTP>=400' % (
                            probe['injection']['before']['record_result'],
                            probe['injection']['before']['item_quality_status'],
                            probe['injection']['after']['item_quality_status']),
                        'result=%r auditΔ=%s ncΔ=%s quality_status=[%r→%r] HTTP=%s' % (
                            d['record_result'][1], d['audit_delta'], d['nc_delta'],
                            d['item_quality_status'][0], d['item_quality_status'][1],
                            probe['injection']['http']),
                        ok, evidence='injector=%s' % probe['injection']['injector'])
    elif expect == 'control':
        c = probe['control']
        nc_ok = c['nc_fields_ok']
        ok = (c['http'] == 200 and c['delta']['record_result'][1] == 'fail'
              and c['delta']['nc_delta'] == 1 and c['delta']['item_quality_status'][1] == 'fail'
              and nc_ok)
        ok_all &= check('C-B15-06.b',
                        '阴性对照：result=fail ⇒ NC +1 ∧ quality_status None→fail ∧ NC 四字段一致',
                        'HTTP=200 result=fail ncΔ=+1 quality_status None→fail '
                        'NC{type=rework,status=open,handling_result=待处置,target_type=production_record}',
                        'HTTP=%s result=%s ncΔ=%s quality_status=[%r→%r] nc_fields_ok=%s' % (
                            c['http'], c['delta']['record_result'][1], c['delta']['nc_delta'],
                            c['delta']['item_quality_status'][0], c['delta']['item_quality_status'][1],
                            nc_ok),
                        ok, evidence='newest_nc=%s' % json.dumps(c['newest_nc_row'], ensure_ascii=False))
    elif expect == 'prefix':
        d = probe['injection']['delta']
        ok = (d['record_result'][1] == 'fail' and d['nc_delta'] == 0
              and not d['item_quality_status'][2] and d['audit_delta'] >= 1)
        ok_all &= check('C-B15-06.prefix',
                        '修复前形态（预镜像）可复现：质检记录已提交、NC/门禁未落地',
                        "result='fail' 已落库 ∧ NCΔ=0 ∧ quality_status 不变 ∧ auditΔ>=1",
                        'result=%r NCΔ=%s quality_status=[%r→%r] auditΔ=%s' % (
                            d['record_result'][1], d['nc_delta'], d['item_quality_status'][0],
                            d['item_quality_status'][1], d['audit_delta']),
                        ok, evidence='预镜像树：git show HEAD:app/main/quality.py 覆盖合成树 app/main/quality.py')
    return ok_all


# ------------------------------------------------------------------ 预镜像（修复前形态）
PREFIX_RUNNER = '''# -*- coding: utf-8 -*-
"""自动生成的 B15-06 预镜像探针 runner（合成树 = 工作树 app/ + HEAD 版 app/main/quality.py）。"""
import json
import os
import sys

HARNESS, SCRIPTS, SYN, REPO, OUT = sys.argv[1:6]
sys.path.insert(0, HARNESS)
sys.path.insert(0, SCRIPTS)
import fixtures                       # noqa: E402
fixtures._patch_mkdtemp()
import _test_bootstrap                # noqa: E402  （import 时把 REPO 插到 sys.path[0]）
sys.path.insert(0, SYN)               # ← 合成树必须排在 REPO 之前，import app 才会命中预镜像
app, copy_path = _test_bootstrap.make_app(fresh=True)
fixtures.assert_isolated(app)
fixtures.seed_all(app)
import chain_count_consistency as cc  # noqa: E402
result = cc.run_b15_06_probe(app, tag='cc06pfx', pieces=2, with_control=False, label='prefix')
result['copy_path'] = copy_path
result['py_file_loaded'] = os.path.join(SYN, 'app', 'main', 'quality.py')
with open(OUT, 'w', encoding='utf-8') as fh:
    json.dump(result, fh, ensure_ascii=False, indent=2, sort_keys=True)
print('[prefix] dumped ' + OUT)
'''


def build_prefix_tree(work_dir, worktree_quality):
    """合成树 = 工作树 app/ 的副本，仅把 app/main/quality.py 换成 HEAD 版。"""
    syn_root = os.path.join(work_dir, 'syn')
    if os.path.exists(syn_root):
        shutil.rmtree(syn_root)
    os.makedirs(syn_root)
    shutil.copytree(os.path.join(REPO_ROOT, 'app'), os.path.join(syn_root, 'app'))
    head = subprocess.run(['git', 'show', 'HEAD:app/main/quality.py'], cwd=REPO_ROOT,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    info = {'returncode': head.returncode}
    if head.returncode != 0:
        info['stderr'] = head.stderr.decode('utf-8', 'replace')
        return None, info
    target = os.path.join(syn_root, 'app', 'main', 'quality.py')
    with open(target, 'wb') as fh:
        fh.write(head.stdout)
    work_bytes = open(worktree_quality, 'rb').read()
    syn_bytes = open(target, 'rb').read()
    info.update({'syn_quality_py': target, 'syn_sha256': sha256_file(target),
                 'worktree_sha256': sha256_file(worktree_quality),
                 'bytes': len(syn_bytes)})
    # 归因闸：合成树与工作树的 quality.py 差异必须**只有** B15-06 那一处（commit → flush + 说明注释）
    diff = subprocess.run(['git', 'diff', '--no-index', '--unified=0', target, worktree_quality],
                          cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    text = diff.stdout.decode('utf-8', 'replace')
    info['diff_lines'] = [ln for ln in text.splitlines()
                          if ln[:1] in '+-' and not ln.startswith(('+++', '---'))]
    removed = [ln[1:].strip() for ln in info['diff_lines'] if ln.startswith('-')]
    added = [ln[1:].strip() for ln in info['diff_lines'] if ln.startswith('+')]
    info['removed_lines'] = removed
    info['added_lines'] = added
    info['diff_sha256_note'] = 'diff(syn, worktree) 只应含 B15-06 的 commit→flush 改动'
    info['guard_rule'] = ("removed == ['db.session.commit()'] 且 added 全部为注释或 "
                          "'db.session.flush()' ⇒ 工作树相对 HEAD 只改了 B15-06 那一处提交缝")
    ok_removed = (removed == ['db.session.commit()'])
    ok_added = bool(added) and all(t.startswith('#') or t == 'db.session.flush()' for t in added)
    info['worktree_unchanged_elsewhere'] = bool(ok_removed and ok_added
                                               and len(info['diff_lines']) <= 24)
    return syn_root, info


def run_prefix_probe(work_dir):
    """子进程跑预镜像探针，返回 (result_dict, meta)。"""
    worktree_quality = os.path.join(REPO_ROOT, 'app', 'main', 'quality.py')
    syn_root, info = build_prefix_tree(work_dir, worktree_quality)
    meta = {'prefix_tree': info, 'runner': None, 'child': None}
    if syn_root is None:
        meta['status'] = 'blocked'
        meta['blocked_reason'] = 'git show HEAD:app/main/quality.py 失败'
        return None, meta
    if not info['worktree_unchanged_elsewhere']:
        meta['status'] = 'blocked'
        meta['blocked_reason'] = ('合成树与工作树的 quality.py 差异不止 B15-06 一处 ⇒ 归因不成立：%s'
                                  % json.dumps(info['diff_lines'], ensure_ascii=False))
        return None, meta
    runner = os.path.join(work_dir, 'run_prefix_probe.py')
    with open(runner, 'w', encoding='utf-8') as fh:
        fh.write(PREFIX_RUNNER)
    out_path = os.path.join(work_dir, 'prefix_probe.json')
    args = [runner, HERE, SCRIPTS_DIR, syn_root, REPO_ROOT, out_path]
    child = run_child(args, cwd=REPO_ROOT, timeout=900, label='b15_06_prefix')
    meta['runner'] = runner
    meta['child'] = {'argv_display': child['argv_display'], 'exit_code': child['exit_code'],
                     'stdout_tail': child['stdout'][-2000:], 'stderr_tail': child['stderr'][-2000:],
                     'duration_s': child['duration_s'],
                     'real_db_sha256_before': child['real_db_sha256_before'],
                     'real_db_sha256_after': child['real_db_sha256_after'],
                     'evidence_level': child['evidence_level']}
    if not os.path.isfile(out_path):
        meta['status'] = 'blocked'
        meta['blocked_reason'] = '子进程未产出 %s（exit=%s）' % (out_path, child['exit_code'])
        return None, meta
    with open(out_path, encoding='utf-8') as fh:
        result = json.load(fh)
    meta['status'] = 'done'
    meta['result_path'] = out_path
    return result, meta


# ------------------------------------------------------------------ 参数
def parse_args(argv):
    ap = argparse.ArgumentParser(add_help=True, description='B15-07 双链件数守恒对拍')
    ap.add_argument('--out', required=True, help='判据产物 JSON 落点（必填）')
    ap.add_argument('--pieces', type=int, default=DEFAULT_PIECES,
                    help='本次对拍的工件件数（默认 %d，必须 >= %d）' % (DEFAULT_PIECES, MIN_PIECES))
    ap.add_argument('--perturb', default=None,
                    help='判据输入偏差声明：内联 JSON 或 JSON 文件路径（注入用）')
    ap.add_argument('--b15-06-injection', action='store_true',
                    help='追加 B15-06 提交缝注入 / 阴性对照 / 预镜像证据（默认关）')
    ap.add_argument('--no-dump', action='store_true', help='兼容 ci_gates 请求型脚本约定（本脚本无 dump）')
    return ap.parse_args(argv)


def load_perturb(spec):
    """`--perturb` 既接内联 JSON（`{` 开头，供 ci_gates 注入形态 ⑦ 免落夹具）也接 JSON 文件路径。"""
    if spec is None:
        return None
    text = spec.strip()
    source = 'inline'
    if not text.startswith('{'):
        source = 'file'
        if not os.path.isfile(text):
            raise UsageError('--perturb 既不是内联 JSON（应以 { 开头）也不是存在的文件：%s' % spec)
        try:
            with open(text, encoding='utf-8') as fh:
                text = fh.read()
        except Exception as exc:
            raise UsageError('--perturb 文件读不出：%s（%s）' % (spec, exc))
    try:
        doc = json.loads(text)
    except Exception as exc:
        raise UsageError('--perturb 不是合法 JSON：%s（%s）' % (spec, exc))
    if not isinstance(doc, dict):
        raise UsageError('--perturb 顶层必须是对象：%s' % spec)
    side = str(doc.get('side') or '').lower()
    if side not in ('report', 'workpiece'):
        raise UsageError("--perturb 的 side 必须是 'report' 或 'workpiece'，实得 %r" % doc.get('side'))
    try:
        delta = int(doc.get('delta'))
    except (TypeError, ValueError):
        raise UsageError('--perturb 的 delta 必须是整数，实得 %r' % doc.get('delta'))
    if delta == 0:
        raise UsageError('--perturb 的 delta 不得为 0（无偏差即无注入）')
    return {'source': source, 'spec': spec, 'side': side, 'delta': delta,
            'reason': doc.get('reason') or '（未声明原因）',
            'mode': 'judge_input_delta（只改判据输入，不改台账）'}


# ------------------------------------------------------------------ 主流程
def dump_out(path, payload):
    ensure_dir(os.path.dirname(os.path.abspath(path)) or '.')
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True)
    return path


def run(argv):
    args = parse_args(argv)
    if args.pieces < MIN_PIECES:
        raise UsageError('--pieces 必须 >= %d（才能构造「行数不同而件数相同」），实得 %d'
                         % (MIN_PIECES, args.pieces))
    perturb = load_perturb(args.perturb)
    print(CONSOLE_MARK + '口径 = SUM(finished_product.quantity) 件数合计（禁止用行数）', flush=True)
    note('批次15 B15-07 双链件数守恒对拍 run_id=%s pieces=%d' % (RUN_ID, args.pieces))
    if perturb:
        note('注入：判据输入偏差 side=%s delta=%+d（%s）'
             % (perturb['side'], perturb['delta'], perturb['mode']))

    started = time.strftime('%Y-%m-%d %H:%M:%S')
    app, copy_path = fixtures.make_isolated_app(TAG)
    seeded = fixtures.seed_all(app)
    client, login_status, login_loc = make_client(app, '_t_admin', 'test_pw_123')
    note('隔离副本=%s；登录 _t_admin HTTP=%s' % (copy_path, login_status))
    ctx = build_fixture(app, TAG, args.pieces)
    note('夹具：实例 item#%d 产品编码=%s 报工件数=%d 工件数=%d 工件链任务#%d'
         % (ctx['item_id'], ctx['item_product_code'], args.pieces, len(ctx['workpieces']),
            ctx['task_wp_id']))

    probe = interference_probe(app, client, ctx, TAG)

    before = snapshot(app, ctx)
    RAW['before'] = before
    chain_a = run_report_chain(client, ctx, args.pieces)
    RAW['chain_report'] = chain_a
    note('报工链 POST /tasks/%d/update_status HTTP=%s body=%s'
         % (ctx['task_report_id'], chain_a['http'], json.dumps(chain_a['body'], ensure_ascii=False)))
    attach_qc_tasks(app, ctx, TAG)
    chain_b = run_workpiece_chain(client, ctx, 'pass')
    RAW['chain_workpiece'] = chain_b
    note('工件链 submit x%d HTTP=%s' % (len(chain_b), [r['http'] for r in chain_b]))
    after = snapshot(app, ctx)
    RAW['after'] = after

    verdict = judge(after, perturb)
    RAW['judgement'] = verdict
    fg_delta = round(after['fg_total_pieces'] - before['fg_total_pieces'], 6)
    nc_delta = after['counters']['nonconformity_records'] - before['counters']['nonconformity_records']
    a_ok = verdict['a_conserved']
    if perturb:
        a_ok = a_ok and verdict['deviation_side'] is not None
    else:
        a_ok = a_ok and verdict['deviation_side'] is None
    check('C-B15-07.a', '两侧件数守恒（件数合计口径，非行数）',
          'A=report_record SUM(quantity) == B=workpiece fg SUM(quantity) == 报工件数',
          'A=%g B=%g 报工件数=%g' % (verdict['A_pieces'], verdict['B_pieces'],
                                     verdict['target_pieces']),
          a_ok, evidence=(verdict['deviation_reading'] or '两侧与报工件数三者一致（无偏差）'))
    check('C-B15-07.a2', '行数与件数不同构（A 1 行 N 件 vs B N 行 1 件）',
          'A_rows(%d) != B_rows(%d) 而件数相同 ⇒ 判据与行数解耦'
          % (verdict['A_rows'], verdict['B_rows']),
          'A_rows=%d A=%g；B_rows=%d B=%g' % (verdict['A_rows'], verdict['A_pieces'],
                                              verdict['B_rows'], verdict['B_pieces']),
          bool(verdict['a2_rows_differ'] and verdict['A_pieces'] == verdict['B_pieces']),
          evidence='若改读行数 ⇒ %d != %d 假红' % (verdict['A_rows'], verdict['B_rows']))
    check('C-B15-07.a3', '报工链入库产出件数 = 报工件数',
          'C=finished_product(workpiece_id IS NULL ∧ product_number=实例编码) SUM(quantity) == 报工件数',
          'C=%g 报工件数=%g' % (verdict['C_pieces'], verdict['target_pieces']),
          bool(verdict['a3_output_matches']),
          evidence='报工链产出行数=%d' % verdict['C_rows'])
    check('C-B15-07.b', '两侧基数均 > 0（防空集恒等 0 == 0）',
          'A_rows>0 且 B_rows>0', 'A_rows=%d B_rows=%d' % (verdict['A_rows'], verdict['B_rows']),
          bool(verdict['b_nonempty']))
    check('C-B15-07.d', '阴性对照：工件链全 pass ⇒ 无不合格单',
          'nonconformity_records Δ=0', 'ncΔ=%s' % nc_delta, nc_delta == 0)
    check('C-B15-07.e', '件数增量只来自本次动作（报工链产出 + 工件链产出）',
          'fg 件数增量 == A + C = %g' % (verdict['A_pieces'] + verdict['C_pieces']),
          'fgΔ=%g（before=%g after=%g）' % (fg_delta, before['fg_total_pieces'],
                                           after['fg_total_pieces']),
          abs(fg_delta - (verdict['A_pieces'] + verdict['C_pieces'])) < 1e-6)

    b15_06 = {'enabled': bool(args.b15_06_injection)}
    if args.b15_06_injection:
        work_dir = ensure_dir(os.path.join(TMP_ROOT, 'b15-06-prefix'))
        live = run_b15_06_probe(app, tag='cc06live', pieces=2, with_control=True, label='post_fix')
        b15_06['post_fix'] = live
        evaluate_b15_06(live, 'post_fix')
        evaluate_b15_06(live, 'control')
        prefix_result, prefix_meta = run_prefix_probe(work_dir)
        b15_06['prefix'] = {'meta': prefix_meta}
        if prefix_result:
            b15_06['prefix']['probe'] = prefix_result
            evaluate_b15_06(prefix_result, 'prefix')
        else:
            print('[BLOCK] C-B15-06.prefix 预镜像未完成：%s' % prefix_meta.get('blocked_reason'),
                  flush=True)
            CHECKS.append({'id': 'C-B15-06.prefix', 'desc': '修复前形态（预镜像）复现登记',
                           'expected': '预镜像可跑并复现「已提交、未落地」',
                           'got': prefix_meta.get('blocked_reason'), 'status': 'blocked',
                           'evidence': '不伪造读数；阻断原因见 got'})
        b15_06['work_dir'] = work_dir

    failed = [c for c in CHECKS if c['status'] == 'failed']
    payload = {
        'schema': 'chain-count-consistency/1',
        'task': 'B15-07（批次15 I5）：报工链 vs 工件链 fg 件数守恒对拍',
        'judgement_semantics': {
            'A_report_record': "SUM(production_record.quantity)（本次报工记录；行数 1）",
            'B_workpiece': "SUM(finished_product.quantity)（本次 N 件工件对应 fg 行；行数 N）",
            'C_report_output': ("SUM(finished_product.quantity) workpiece_id IS NULL ∧ "
                                "product_number=实例产品编码（报工链入库产出）"),
            'rule': 'A == B == 报工件数，且 C == 报工件数；基数（COUNT(*)）恒打印；禁止用行数',
        },
        'exit_codes': {'0': '判据全过', '1': '判据不满足（件数不守恒/空集/注入偏差）',
                       '2': '用法与参数错误'},
        'ci_gates_expects': [CONSOLE_MARK + '口径 = SUM(finished_product.quantity) 件数合计（禁止用行数）',
                             '[OK] C-B15-07.a 两侧件数守恒',
                             '[OK] C-B15-07.a2 行数与件数不同构',
                             CONSOLE_MARK + 'RESULT: OK'],
        'run': {'run_id': RUN_ID, 'started_at': started,
                'generated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                'interpreter': sys.executable, 'script': os.path.abspath(__file__),
                'script_sha256': sha256_file(os.path.abspath(__file__)),
                'repo_root': REPO_ROOT, 'copy_path': copy_path,
                'pieces': args.pieces, 'seeded_users': sorted(seeded['users']),
                'real_db_sha256_pinned': REAL_DB_SHA256_EXPECTED,
                'real_db_sha256_actual': sha256_file(os.path.join(REPO_ROOT, 'app.db'))},
        'perturb': perturb,
        'fixture': {k: v for k, v in ctx.items() if k not in ('qc',)},
        'before': before, 'after': after,
        'chains': {'report': chain_a, 'workpiece': chain_b},
        'judgement': verdict, 'fg_delta': fg_delta, 'nc_delta': nc_delta,
        'interference_probe': probe,
        'b15_06': b15_06,
        'checks': CHECKS, 'notes': NOTES,
        'exit_code': EXIT_CRITERION_FAILED if failed else EXIT_OK,
    }
    out_path = dump_out(args.out, payload)
    note('判据产物=%s' % out_path)
    try:
        ev = save_evidence('chain_count_consistency.json',
                           json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
                           run_id=RUN_ID)
        note('证据落盘=%s' % ev)
    except Exception as exc:
        note('证据落盘失败（不影响判据）：%s: %s' % (exc.__class__.__name__, exc))
    print(CONSOLE_MARK + '判据：%d 条通过 / %d 条失败 / %d 条阻断'
          % (len([c for c in CHECKS if c['status'] == 'passed']), len(failed),
             len([c for c in CHECKS if c['status'] == 'blocked'])), flush=True)
    if failed:
        for c in failed:
            print(CONSOLE_MARK + 'RED %s %s | expected=%s got=%s %s'
                  % (c['id'], c['desc'], c['expected'], c['got'], c['evidence']), flush=True)
    print(CONSOLE_MARK + 'RESULT: %s' % ('FAIL' if failed else 'OK'), flush=True)
    return EXIT_CRITERION_FAILED if failed else EXIT_OK


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    out_arg = None
    if '--out' in argv:
        idx = argv.index('--out')
        if idx + 1 < len(argv):
            out_arg = argv[idx + 1]
    try:
        return run(argv)
    except UsageError as exc:
        print(CONSOLE_MARK + 'RESULT: USAGE_ERROR %s' % exc, flush=True)
        if out_arg:
            dump_out(out_arg, {'schema': 'chain-count-consistency/1', 'exit_code': EXIT_USAGE,
                               'usage_error': str(exc), 'argv': argv,
                               'generated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                               'checks': []})
        return EXIT_USAGE
    except Exception as exc:
        print(CONSOLE_MARK + 'RESULT: ERROR %s: %s' % (exc.__class__.__name__, exc), flush=True)
        traceback.print_exc()
        if out_arg:
            dump_out(out_arg, {'schema': 'chain-count-consistency/1', 'exit_code': EXIT_CRITERION_FAILED,
                               'error': '%s: %s' % (exc.__class__.__name__, exc),
                               'traceback': traceback.format_exc().splitlines()[-12:],
                               'argv': argv, 'checks': CHECKS, 'notes': NOTES,
                               'generated_at': time.strftime('%Y-%m-%d %H:%M:%S')})
        return EXIT_CRITERION_FAILED


if __name__ == '__main__':
    sys.exit(main())
