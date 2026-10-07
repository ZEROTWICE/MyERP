"""w2w3_probe.py — W2/W3（P-02…P-07）修复的对抗验证探针。

## 判据来源（权威）
- `07b-DEC-1-DEC-2-业务口径决策单.md`：14 格判定表 + 机读 `acceptance_matrix`；
- `16-W2W3修复验收判据.md`（含 §11 补记）：AC-13-a / AC-18-a / AC-25-a / AC-26-a / AC-27-C /
  AC-04-d/e/e2 / AC-29-ac/b/d/d2 / AC-30-a/b/c/NEG + RC-1…RC-22 反向约束。

## 探针结构（全部在**副本库**上、经**真实端点**或真实服务函数）
| 段 | 覆盖 |
| --- | --- |
| `cells` | 判定表：N1 / N3 / N4 / P1 / P3 / P4 / A1 / A2 / F1 / F2 / F3(+scrap 支路) + 不变量 |
| `ac13_18` | AC-13-a（5 条断言，含幂等）/ AC-18-a（4 条，含「写的那行恰好是 BI」）/ AC-16 / AC-18-NEG |
| `amounts` | AC-25-a / AC-26-a / AC-27-C / AC-04-d（S1==S2 + S3/S4 同口径）/ AC-04-e（唯一读取点 +
  缺省 False）/ AC-04-e2（模板零命中）+ S1 真端点两态 |
| `scrap` | AC-29-ac（逐行各扣各自物料 + 对照料不变）/ -b（夹紧 0 + warning 四要素）/ -d（取不到不扣
  + 未扣减说明）/ -d2（报废入库数量 == 报废件数） |
| `rework` | AC-30-a（默认件数 = 来源记录件数）/ -b（显式覆盖 + 非法值 4xx）/ -c（兜底留痕）/ -NEG |
| `static` | 六项静态门禁 + 真实库指纹 + RC-15（无新增列）/ RC-19（模板零命中） |

## 只读约束
- 真实库 `app.db` **只做 SHA256**；一切写入发生在 `shutil.copy2` 出的带时间戳副本上
  （`samefile=False`，证据里记）。
- 证据落盘一律 `_env.save_evidence`（分 run 目录 + 写入守卫 + 台账），**绝不原地覆盖**。
- 控制台行 ASCII 安全（A-14/A-60）；行数用 `splitlines()`（A-23）。

## 用法（仓库根目录；A-40：复跑换 `HARNESS_RUN_ID`）
    $env:HARNESS_RUN_ID='w2w3-t7-final'
    python -B test-reports-2026-10/harness/w2w3_probe.py --scenario all
"""
import argparse
import ast
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
REPORTS_ROOT = os.path.dirname(HERE)
REPO_ROOT = os.path.dirname(REPORTS_ROOT)
SCRIPTS_DIR = os.path.join(REPO_ROOT, 'scripts')
sys.path.insert(0, HERE)

from _env import (  # noqa: E402
    REAL_DB, REAL_DB_SHA256_EXPECTED, RUN_ID, ensure_dir, run_child, save_evidence,
    sha256_file, tmp_dir,
)

CHECKS = []
NOTES = []
RAW = {}


def note(text):
    NOTES.append(text)
    print('[note] %s' % text, flush=True)


def check(cid, desc, expected, actual, ok, evidence=''):
    CHECKS.append({'id': cid, 'desc': desc, 'expected': expected, 'actual': actual,
                   'status': 'passed' if ok else 'failed', 'evidence': evidence})
    print('[%s] %-8s %s | expected=%s actual=%s %s'
          % ('PASS' if ok else 'FAIL', cid, desc, json.dumps(expected, ensure_ascii=True),
             json.dumps(actual, ensure_ascii=True), evidence), flush=True)
    return ok


class _Capture(logging.Handler):
    def __init__(self):
        logging.Handler.__init__(self, level=logging.INFO)
        self.rows = []

    def emit(self, record):
        try:
            self.rows.append((record.levelname, record.getMessage()))
        except Exception:  # pragma: no cover
            pass


def captured(app, fn):
    """执行 fn 并捕获 `app.logger` 的日志行（AC-29-b/-d 要求「用捕获日志而不是响应体」。"""
    handler = _Capture()
    app.logger.addHandler(handler)
    try:
        result = fn()
    finally:
        app.logger.removeHandler(handler)
    return result, handler.rows


# ------------------------------------------------------------------ 环境与夹具
def build_app():
    db_dir = ensure_dir(os.path.join(tmp_dir('db')))
    copy_path = os.path.join(db_dir, 'app_w2w3_%s.db' % RUN_ID)
    shutil.copy2(REAL_DB, copy_path)
    same_file = os.path.samefile(copy_path, REAL_DB)
    os.environ['DATABASE_URL'] = 'sqlite:///' + copy_path.replace('\\', '/')
    if REPO_ROOT not in sys.path:
        sys.path.insert(0, REPO_ROOT)
    import _test_bootstrap
    from app import create_app
    application = create_app()
    application.config['WTF_CSRF_ENABLED'] = False
    application.config['TESTING'] = True
    application.config['PROPAGATE_EXCEPTIONS'] = False
    uri = application.config['SQLALCHEMY_DATABASE_URI']
    if os.path.normcase(copy_path) not in os.path.normcase(uri.replace('/', os.sep)):
        raise RuntimeError('副本库隔离失败：%s' % uri)
    users, password = _test_bootstrap.ensure_role_users(application)
    client = application.test_client()
    login = _test_bootstrap.login_as(client, users['admin'], password)
    return {'app': application, 'client': client, 'copy_path': copy_path,
            'copy_samefile_as_real': same_file, 'copy_sha256': sha256_file(copy_path),
            'login_status': login.status_code, 'users': users, 'password': password,
            'db_uri': uri}


def build_fixtures(env):
    """最小夹具：两个产品（有检 / 无检）、订单/批次/实例、员工、原料、模板。"""
    app = env['app']
    from app import db
    from app import models as M
    tag = RUN_ID.replace('-', '')[-6:].upper()
    ctx = {'tag': tag}
    with app.app_context():
        admin = M.User.query.filter_by(role='admin').first()
        proc_insp = M.ProcessPrice(process_code='_w2w3_cut_%s' % tag,
                                   process_name='_w2w3 有检工序 %s' % tag,
                                   price=20.0, version=1, needs_inspection=True)
        proc_plain = M.ProcessPrice(process_code='_w2w3_plain_%s' % tag,
                                    process_name='_w2w3 无检工序 %s' % tag,
                                    price=20.0, version=1, needs_inspection=False)
        db.session.add_all([proc_insp, proc_plain])
        db.session.flush()
        made = {}
        for key, proc, needs in (('A', proc_insp, True), ('B', proc_plain, False)):
            product = M.Product(product_code='_W2W3%s%s' % (key, tag),
                                product_name='_w2w3 产品 %s' % key,
                                drawing_number='_W2W3-D', model='_W2W3-M',
                                unit='件', status='active',
                                created_by=admin.id if admin else None)
            db.session.add(product)
            db.session.flush()
            db.session.add(M.ProductProcess(product_id=product.id, process_id=proc.id,
                                            sequence=1, process_stage='machine'))
            order = M.ProductionOrder(product_id=product.id,
                                      order_number='_W2W3O%s%s' % (key, tag),
                                      planned_quantity=100, planned_start_date=date.today(),
                                      planned_end_date=date.today() + timedelta(days=30),
                                      created_by=admin.id if admin else None)
            db.session.add(order)
            db.session.flush()
            batch = M.ProductionBatch(production_order_id=order.id,
                                      batch_number='_W2W3B%s%s' % (key, tag),
                                      batch_quantity=100)
            db.session.add(batch)
            db.session.flush()
            item = M.ProductionBatchItem(batch_id=batch.id, item_sequence=1,
                                         product_code='_W2W3I%s%s' % (key, tag),
                                         status='in_progress', quality_status=None)
            db.session.add(item)
            db.session.flush()
            made[key] = {'product_id': product.id, 'process_id': proc.id, 'order_id': order.id,
                         'batch_id': batch.id, 'item_id': item.id, 'needs_inspection': needs,
                         'product_code': item.product_code}
        employee = M.Employee(employee_id='_w2w3emp%s' % tag, name='_w2w3 员工',
                             position='普通员工', base_salary=0.0, coefficient=1.5,
                             department='_w2w3', hire_date=date(2026, 1, 1))
        db.session.add(employee)
        category = M.RawMaterialCategory.query.first()
        materials = []
        for idx in (1, 2, 3):
            rm = M.RawMaterial(supplier='_w2w3 供应商',
                               category_id=category.id if category else None,
                               melt_number='_w2w3MELT%d%s' % (idx, tag),
                               supplier_number='_w2w3SUP%d%s' % (idx, tag),
                               internal_number='_w2w3RAW%d%s' % (idx, tag),
                               quantity=100.0, status='in_stock', is_archived=False)
            db.session.add(rm)
            materials.append(rm)
        template = M.InspectionTemplate(template_code='_W2W3T%s' % tag, name='_w2w3 模板',
                                        type='production_record', is_active=True,
                                        created_by=admin.id if admin else None)
        db.session.add(template)
        db.session.commit()
        ctx.update({
            'A': made['A'], 'B': made['B'],
            'emp_id': employee.id, 'emp_code': employee.employee_id,
            'coefficient': employee.coefficient,
            'material_ids': [m.id for m in materials],
            'template_id': template.id,
            'admin_id': admin.id if admin else 1,
        })
    return ctx


def new_item_task(env, ctx, key, seq, qty, quality_status=None, suffix=None, item_status=None):
    """新建「实例 + 待报工任务」，返回 (item_id, task_id)。

    `quality_status` / `item_status` 是**构造性前置**（把某一格的起始态摆出来）；
    业务路径上 `fail`/`scrapped` 只能由质检结论/报废处置写入，探针在证据里如实标注。
    """
    app = env['app']
    from app import db
    from app import models as M
    code = '_W2W3I%s%s%s' % (key, ctx['tag'], suffix or ('S%d' % seq))
    with app.app_context():
        item = M.ProductionBatchItem(batch_id=ctx[key]['batch_id'], item_sequence=seq,
                                     product_code=code, status=item_status or 'in_progress',
                                     quality_status=quality_status)
        db.session.add(item)
        db.session.flush()
        task = M.TaskAssignment(employee_id=ctx['emp_id'], process_id=ctx[key]['process_id'],
                                target_date=date.today(), quantity=qty, status='pending',
                                task_type='manual', batch_item_id=item.id,
                                production_batch_id=ctx[key]['batch_id'],
                                notes='_w2w3 探针任务')
        db.session.add(task)
        db.session.commit()
        return item.id, task.id


def report(env, task_id, qty, materials=None):
    body = {'completed_quantity': qty}
    if materials:
        body['materials'] = materials
    resp = env['client'].post('/tasks/%d/update_status' % task_id, json=body)
    return resp.status_code, (resp.get_json(silent=True) or {})


def submit_inspection(env, ctx, ta_task_id, result):
    """对「报工任务 ta_task_id」产出的质检任务走真实端点：start-inspection → submit。

    注意：start-inspection 的入参是 **InspectionTask.id**（不是 TaskAssignment.id）——
    本函数按 `global_sn` 定位产出、再取其 `target_type='production_record'` 的质检任务。
    返回 (submit_status, record_id, body)。
    """
    from app import db
    from app import models as M
    client = env['client']
    with env['app'].app_context():
        task = M.TaskAssignment.query.get(ta_task_id)
        production_record = M.ProductionRecord.query.filter_by(
            global_sn=task.global_sn).first() if task else None
        inspection_task = None
        if production_record is not None:
            inspection_task = (M.InspectionTask.query
                               .filter_by(target_type='production_record',
                                          target_id=production_record.id)
                               .order_by(M.InspectionTask.id.desc()).first())
        inspection_task_id = inspection_task.id if inspection_task else None
    if inspection_task_id is None:
        return None, None, {'error': 'no inspection task for report task %s' % ta_task_id}
    start = client.post('/api/quality/tasks/%d/start-inspection' % inspection_task_id,
                        json={'template_id': ctx['template_id'], 'notes': '_w2w3 开始质检'})
    with env['app'].app_context():
        record = M.InspectionRecord.query.filter_by(task_id=inspection_task_id).first()
        record_id = record.id if record else None
    if record_id is None:
        return start.status_code, None, {'start': start.get_json(silent=True),
                                         'inspection_task_id': inspection_task_id}
    submit = client.post('/api/quality/records/%d/submit' % record_id,
                         json={'result': result, 'notes': '_w2w3 质检结论'})
    return submit.status_code, record_id, (submit.get_json(silent=True) or {})


def dispose(env, nc_id, **payload):
    resp = env['client'].post('/api/quality/nonconformities/%d/dispose' % nc_id, json=payload)
    return resp.status_code, (resp.get_json(silent=True) or {})


# ------------------------------------------------------------ 库字段/增量读取
def _scalar(app, sql):
    from app import db
    with app.app_context():
        return float(db.session.execute(db.text(sql)).scalar() or 0)


def fg_pieces(env):
    return _scalar(env['app'],
                   "SELECT COALESCE(SUM(quantity),0) FROM finished_product "
                   "WHERE stock_kind='fg' AND status='in_stock'")


def scrap_pieces(env, code=None):
    if code:
        return _scalar(env['app'],
                       "SELECT COALESCE(SUM(quantity),0) FROM finished_product "
                       "WHERE stock_kind='scrap' AND product_number='%s'" % code)
    return _scalar(env['app'], "SELECT COALESCE(SUM(quantity),0) FROM finished_product "
                              "WHERE stock_kind='scrap'")


def nc_count(env):
    return _scalar(env['app'], 'SELECT COUNT(*) FROM nonconformity_records')


def qs(env, item_id):
    from app import models as M
    with env['app'].app_context():
        item = M.ProductionBatchItem.query.get(item_id)
        return None if item is None else item.quality_status


def item_status(env, item_id):
    from app import models as M
    with env['app'].app_context():
        item = M.ProductionBatchItem.query.get(item_id)
        return None if item is None else item.status


def gate_message(env, item_id, production_record=None):
    from app import models as M
    from app.services import mes_service
    with env['app'].app_context():
        item = M.ProductionBatchItem.query.get(item_id)
        return list(mes_service.qc_gate_allows_output(batch_item=item, workpieces=[],
                                                      production_record=production_record))


def raw_qty(env, material_id):
    from app import models as M
    with env['app'].app_context():
        material = M.RawMaterial.query.get(material_id)
        return None if material is None else float(material.quantity or 0.0)


def nc_row(env, nc_id):
    from app import models as M
    with env['app'].app_context():
        nc = M.NonconformityRecord.query.get(nc_id)
        if nc is None:
            return None
        return {'id': nc.id, 'status': nc.status, 'type': nc.type, 'target_type': nc.target_type,
                'target_id': nc.target_id, 'record_id': nc.record_id,
                'rework_task_id': nc.rework_task_id, 'scrap_cost': nc.scrap_cost}


def latest_nc_for_item(env, item_id):
    from app import models as M
    with env['app'].app_context():
        rows = (M.NonconformityRecord.query
                .join(M.InspectionRecord, M.NonconformityRecord.record_id == M.InspectionRecord.id)
                .join(M.InspectionTask, M.InspectionRecord.task_id == M.InspectionTask.id)
                .filter(M.InspectionTask.target_type == 'production_record')
                .order_by(M.NonconformityRecord.id.desc()).all())
        for nc in rows:
            task = nc.record.task if nc.record else None
            if task is None:
                continue
            pr = M.ProductionRecord.query.get(task.target_id)
            if pr is None:
                continue
            from app.services import mes_service
            if getattr(mes_service.batch_item_for_production_record(pr), 'id', None) == item_id:
                return nc.id
    return None


# ------------------------------------------------------------------ 段一：判定表
def section_cells(env, ctx):
    out = {}
    # N1：全新实例（无检工序）正常报工 —— 必须入库，字段维持 NULL（RC-1 / AC-18-NEG）
    item_n1, task_n1 = new_item_task(env, ctx, 'B', 11, 4, suffix='N1')
    before = fg_pieces(env)
    code, body = report(env, task_n1, 4)
    after = fg_pieces(env)
    out['N1'] = {'http': code, 'fg_delta': round(after - before, 6), 'qs': qs(env, item_n1)}
    check('N1', '全新实例正常报工 ⇒ 入库且字段维持 NULL',
          {'fg_delta': 4.0, 'qs': None},
          {'fg_delta': out['N1']['fg_delta'], 'qs': out['N1']['qs']},
          abs(out['N1']['fg_delta'] - 4.0) < 1e-9 and out['N1']['qs'] is None,
          'AC-18-NEG / RC-1 / RC-4（无质检任务 ⇒ 不得被顺手改写）')

    # N3：报工 → submit fail ⇒ 字段 NULL→fail + NC +1；再次报工 ⇒ 拒收
    item_n3, task_n3 = new_item_task(env, ctx, 'A', 12, 10, suffix='N3')
    report(env, task_n3, 10)
    nc0 = nc_count(env)
    sub_code, record_id, sub_body = submit_inspection(env, ctx, task_n3, 'fail')
    nc1 = nc_count(env)
    nc_id = latest_nc_for_item(env, item_n3)
    # 同一产出的「后续报工」不可达（该任务的报工幂等拒绝）⇒ 用同一字段值的等价形态（构造性，如实标注）
    field_after_fail = qs(env, item_n3)
    before = fg_pieces(env)
    item_n3b, task_n3b = new_item_task(env, ctx, 'A', 13, 3, quality_status=field_after_fail,
                                       suffix='N3b')
    code2, _ = report(env, task_n3b, 3)
    after = fg_pieces(env)
    gate = gate_message(env, item_n3)
    out['N3'] = {'submit_http': sub_code, 'record_id': record_id, 'nc_delta': nc1 - nc0,
                 'nc_id': nc_id, 'nc': nc_row(env, nc_id) if nc_id else None,
                 'qs': field_after_fail, 'retry_fg_delta': round(after - before, 6),
                 'retry_http': code2, 'retry_item_quality_status': field_after_fail,
                 'retry_note': '等价形态：同一 quality_status 的新实例（构造性前置）',
                 'gate': gate}
    nc_rec = out['N3']['nc'] or {}
    check('N3-a', '报工 fail ⇒ 不合格登记增量恰为 1 且指回该产出',
          {'nc_delta': 1, 'target_type': 'production_record',
           'status_in': ['open', 'pending_approval']},
          {'nc_delta': out['N3']['nc_delta'], 'target_type': nc_rec.get('target_type'),
           'status': nc_rec.get('status')},
          out['N3']['nc_delta'] == 1 and nc_rec.get('target_type') == 'production_record'
          and nc_rec.get('status') in ('open', 'pending_approval'),
          'AC-13-a 断言 1/2/4')
    check('N3-b', '实例 quality_status 由 NULL 变 fail（直接字段断言）',
          {'qs': 'fail'}, {'qs': out['N3']['qs']}, out['N3']['qs'] == 'fail',
          'AC-18-a 断言 1（07b §1.7 直接字段断言）')
    check('N3-c', 'failing 产出再次报工 ⇒ 拒收（fg 增量 0）且原因可读',
          {'fg_delta': 0.0, 'reason_nonempty': True},
          {'fg_delta': out['N3']['retry_fg_delta'], 'gate': gate},
          abs(out['N3']['retry_fg_delta']) < 1e-9 and bool(gate[1] if len(gate) > 1 else None),
          'RC-12（结论落地必须产生业务后果）')

    # N4：N3 之后处置 rework 至 done ⇒ 字段写 pass + 恢复放行
    if nc_id:
        d_code, d_body = dispose(env, nc_id, action='rework',
                                 rework_process_id=ctx['A']['process_id'],
                                 employee_id=ctx['emp_id'], notes='_w2w3 返工')
        out['N4'] = {'dispose_http': d_code, 'nc': nc_row(env, nc_id), 'qs': qs(env, item_n3)}
        item_n4, task_n4 = new_item_task(env, ctx, 'A', 14, 5, suffix='N4')
        before = fg_pieces(env)
        report(env, task_n4, 5)
        after = fg_pieces(env)
        out['N4']['fg_delta'] = round(after - before, 6)
        check('N4', '处置 rework 至 done 后：字段 pass + 该实例恢复放行',
              {'qs': 'pass', 'fg_delta': 5.0},
              {'qs': out['N4']['qs'], 'fg_delta': out['N4']['fg_delta']},
              out['N4']['qs'] == 'pass' and abs(out['N4']['fg_delta'] - 5.0) < 1e-9,
              'AC-15 / RC-3 / DEC-1 §1.5-4 自动复位')

    # F3（scrap 支路）：fail → 处置 scrap ⇒ 字段 pass 但实例 scrapped ⇒ 仍拒收（RC-5/RC-11）
    item_f3, task_f3 = new_item_task(env, ctx, 'A', 15, 6, suffix='F3')
    report(env, task_f3, 6)
    submit_inspection(env, ctx, task_f3, 'fail')
    nc_store = latest_nc_for_item(env, item_f3)
    if nc_store:
        d_code, _ = dispose(env, nc_store, action='scrap', scrap_cost=12.0, notes='_w2w3 报废')
        before = fg_pieces(env)
        # 报废终态后的「再次报工」用同一实例状态的等价形态（构造性前置，如实标注）
        item_f3b, task_f3b = new_item_task(env, ctx, 'A', 16, 2, quality_status='pass',
                                           suffix='F3b', item_status='scrapped')
        report(env, task_f3b, 2)
        after = fg_pieces(env)
        out['F3_scrap'] = {'dispose_http': d_code, 'qs': qs(env, item_f3),
                           'item_status': item_status(env, item_f3),
                           'fg_delta': round(after - before, 6),
                           'retry_note': '等价形态：quality_status=pass + status=scrapped 的新实例',
                           'gate': gate_message(env, item_f3)}
        check('F3', 'scrap 处置 ⇒ quality_status=pass 但 status=scrapped ⇒ 仍拒收',
              {'qs': 'pass', 'item_status': 'scrapped', 'fg_delta': 0.0},
              {'qs': out['F3_scrap']['qs'], 'item_status': out['F3_scrap']['item_status'],
               'fg_delta': out['F3_scrap']['fg_delta']},
              out['F3_scrap']['qs'] == 'pass' and out['F3_scrap']['item_status'] == 'scrapped'
              and abs(out['F3_scrap']['fg_delta']) < 1e-9,
              'DEC-1 §1.3 / §3.3-5 / RC-5 / RC-11')

    # P1：人为 pending 且无任何在办单据 ⇒ 必须放行（死锁回归，与 P0-2.4 成对）
    item_p1, task_p1 = new_item_task(env, ctx, 'A', 17, 7, quality_status='pending', suffix='P1')
    before = fg_pieces(env)
    report(env, task_p1, 7)
    after = fg_pieces(env)
    out['P1'] = {'fg_delta': round(after - before, 6), 'qs': qs(env, item_p1),
                 'gate': gate_message(env, item_p1)}
    check('P1', 'pending 且无在办单据 ⇒ 放行（死锁回归）',
          {'fg_delta': 7.0, 'qs_in': ['pending', 'pass']},
          {'fg_delta': out['P1']['fg_delta'], 'qs': out['P1']['qs']},
          abs(out['P1']['fg_delta'] - 7.0) < 1e-9 and out['P1']['qs'] in ('pending', 'pass'),
          'DEC-1 §1.6 P1 / P0-2.5 成对常驻（本格为预期翻转）')

    # P3：pending 实例的产出判 fail ⇒ 字段 fail + NC +1；P4：处置 done ⇒ pass + 放行
    item_p3, task_p3 = new_item_task(env, ctx, 'A', 18, 8, quality_status='pending', suffix='P3')
    report(env, task_p3, 8)
    nc0 = nc_count(env)
    submit_inspection(env, ctx, task_p3, 'fail')
    nc1 = nc_count(env)
    nc_p3 = latest_nc_for_item(env, item_p3)
    out['P3'] = {'nc_delta': nc1 - nc0, 'qs': qs(env, item_p3), 'nc_id': nc_p3,
                 'gate': gate_message(env, item_p3)}
    check('P3', 'pending 实例判 fail ⇒ 字段 fail + NC +1 + 拒收',
          {'qs': 'fail', 'nc_delta': 1, 'blocked': False},
          {'qs': out['P3']['qs'], 'nc_delta': out['P3']['nc_delta'],
           'gate_allowed': out['P3']['gate'][0]},
          out['P3']['qs'] == 'fail' and out['P3']['nc_delta'] == 1
          and out['P3']['gate'][0] is False, 'DEC-1 §1.6 P3')
    if nc_p3:
        dispose(env, nc_p3, action='accept', notes='_w2w3 让步接收', scrap_cost=0)
        item_p4, task_p4 = new_item_task(env, ctx, 'A', 19, 9, suffix='P4')
        before = fg_pieces(env)
        report(env, task_p4, 9)
        after = fg_pieces(env)
        out['P4'] = {'qs': qs(env, item_p3), 'fg_delta': round(after - before, 6)}
        check('P4', 'P3 处置 accept(approved) ⇒ 字段 pass + 放行',
              {'qs': 'pass', 'fg_delta': 9.0}, out['P4'],
              out['P4']['qs'] == 'pass' and abs(out['P4']['fg_delta'] - 9.0) < 1e-9,
              'DEC-1 §1.6 P4 / AC-15')

    # A1：pass 实例正常报工 ⇒ 入库 + 维持 pass（不得回归）
    item_a1, task_a1 = new_item_task(env, ctx, 'A', 20, 4, quality_status='pass', suffix='A1')
    before = fg_pieces(env)
    report(env, task_a1, 4)
    after = fg_pieces(env)
    out['A1'] = {'fg_delta': round(after - before, 6), 'qs': qs(env, item_a1)}
    check('A1', 'pass 实例正常报工 ⇒ 入库 + 维持 pass（不得回归）',
          {'fg_delta': 4.0, 'qs': 'pass'}, out['A1'],
          abs(out['A1']['fg_delta'] - 4.0) < 1e-9 and out['A1']['qs'] == 'pass',
          'DEC-1 §3.2 A1 / AC-16 阴性对照')

    # A2：pass 实例出现新 fail 结论 ⇒ 字段 fail + NC +1（守门格：改判后仍必须拦）
    item_a2, task_a2 = new_item_task(env, ctx, 'A', 21, 5, quality_status='pass', suffix='A2')
    report(env, task_a2, 5)
    nc0 = nc_count(env)
    submit_inspection(env, ctx, task_a2, 'fail')
    nc1 = nc_count(env)
    out['A2'] = {'nc_delta': nc1 - nc0, 'qs': qs(env, item_a2), 'gate': gate_message(env, item_a2)}
    check('A2', 'pass 实例出现 fail 结论 ⇒ 字段 fail + NC +1 + 拒收（守门格）',
          {'qs': 'fail', 'nc_delta': 1, 'gate_allowed': False},
          {'qs': out['A2']['qs'], 'nc_delta': out['A2']['nc_delta'],
           'gate_allowed': out['A2']['gate'][0]},
          out['A2']['qs'] == 'fail' and out['A2']['nc_delta'] == 1
          and out['A2']['gate'][0] is False, 'DEC-1 §3.2 A2（pending 改判后必须仍拦得住）')

    # F1/F2：fail 未处置 ⇒ 拒收；再来一个 fail 结论 ⇒ 字段维持 fail + NC +1
    item_f1, task_f1 = new_item_task(env, ctx, 'A', 22, 3, quality_status='fail', suffix='F1')
    gate_f1 = gate_message(env, item_f1)
    before = fg_pieces(env)
    report(env, task_f1, 3)
    after = fg_pieces(env)
    out['F1'] = {'fg_delta': round(after - before, 6), 'gate': gate_f1, 'qs': qs(env, item_f1)}
    check('F1', 'fail 未处置 ⇒ 拒收 + 原因指向不合格 + 字段维持 fail',
          {'fg_delta': 0.0, 'gate_allowed': False, 'qs': 'fail'},
          {'fg_delta': out['F1']['fg_delta'], 'gate_allowed': gate_f1[0], 'qs': out['F1']['qs']},
          abs(out['F1']['fg_delta']) < 1e-9 and gate_f1[0] is False
          and out['F1']['qs'] == 'fail', 'DEC-1 §3.2 F1 / RC-8')
    item_f2, task_f2 = new_item_task(env, ctx, 'A', 23, 2, quality_status='fail', suffix='F2')
    report(env, task_f2, 2)
    nc0 = nc_count(env)
    submit_inspection(env, ctx, task_f2, 'fail')
    nc1 = nc_count(env)
    out['F2'] = {'nc_delta': nc1 - nc0, 'qs': qs(env, item_f2)}
    check('F2', 'fail 未处置时再来一个 fail 结论 ⇒ 字段维持 fail + NC +1',
          {'qs': 'fail', 'nc_delta': 1}, out['F2'],
          out['F2']['qs'] == 'fail' and out['F2']['nc_delta'] == 1, 'DEC-1 §3.2 F2')
    RAW['cells'] = out
    return out


# ------------------------------------------------------------------ 段二：AC-13 / AC-18
def section_ac13_18(env, ctx):
    out = {}
    from app import db
    from app import models as M
    from app.services import mes_service
    item_id, task_id = new_item_task(env, ctx, 'A', 31, 10, suffix='AC13')
    report(env, task_id, 10)
    with env['app'].app_context():
        task = M.TaskAssignment.query.get(task_id)
        pr = M.ProductionRecord.query.filter_by(global_sn=task.global_sn).first()
        pr_id = pr.id if pr else None
        task_status_after_submit = None
    nc0 = nc_count(env)
    with env['app'].app_context():
        others_before = {i.id: i.quality_status for i in M.ProductionBatchItem.query.filter(
            M.ProductionBatchItem.id != item_id).all()}
    sub_code, record_id, _ = submit_inspection(env, ctx, task_id, 'fail')
    nc1 = nc_count(env)
    with env['app'].app_context():
        record = M.InspectionRecord.query.get(record_id)
        nc = M.NonconformityRecord.query.filter_by(record_id=record_id).first()
        qtask = (M.InspectionTask.query
                 .filter_by(target_type='production_record', target_id=pr_id)
                 .order_by(M.InspectionTask.id.desc()).first()) if pr_id else None
        item = M.ProductionBatchItem.query.get(item_id)
        located = mes_service.batch_item_for_production_record(pr) if pr else None
        other_items = {i.id: i.quality_status for i in
                       M.ProductionBatchItem.query.filter(
                           M.ProductionBatchItem.id != item_id).all()}
        others_changed = sorted([k for k, v in other_items.items()
                                 if others_before.get(k) != v])
        out['ac13'] = {'submit_http': sub_code, 'record_result': record.result if record else None,
                       'task_status': qtask.status if qtask else None,
                       'nc_id': nc.id if nc else None,
                       'nc_target_type': nc.target_type if nc else None,
                       'nc_target_id': nc.target_id if nc else None,
                       'nc_status': nc.status if nc else None, 'pr_id': pr_id,
                       'located_item': getattr(located, 'id', None),
                       'qs': item.quality_status, 'other_quality_status': other_items,
                       'others_changed': others_changed,
                       'nc_delta': nc1 - nc0}
    out['ac13']['nc_delta_idempotent'] = None
    with env['app'].app_context():
        record = M.InspectionRecord.query.get(record_id)
        before2 = nc_count(env)
        mes_service.apply_inspection_result(record)   # 幂等：同一条质检记录不得重复建单
        db.session.commit()
        after2 = nc_count(env)
        out['ac13']['nc_delta_idempotent'] = after2 - before2
    a = out['ac13']
    check('AC13-1', 'fail ⇒ NC 增量恰为 1（且重复回放不重复建单）',
          {'nc_delta': 1, 'replay_delta': 0},
          {'nc_delta': a['nc_delta'], 'replay_delta': a['nc_delta_idempotent']},
          a['nc_delta'] == 1 and a['nc_delta_idempotent'] == 0, 'AC-13-a 断言 1')
    check('AC13-2', 'NC 指回该产出（target_type/target_id）且状态未闭环',
          {'target_type': 'production_record', 'target_id': 'pr_id', 'status': 'open'},
          {'target_type': a['nc_target_type'], 'target_id': a['nc_target_id'],
           'pr_id': a['pr_id'], 'status': a['nc_status']},
          a['nc_target_type'] == 'production_record' and a['nc_target_id'] == a['pr_id']
          and a['nc_status'] in ('open', 'pending_approval'), 'AC-13-a 断言 2/3/4')
    check('AC13-3', '质检任务本身仍正常闭环（completed）',
          {'task_status': 'completed'}, {'task_status': a['task_status']},
          a['task_status'] == 'completed', 'AC-13-a 断言 5（不回归项）')
    check('AC18-1', 'quality_status 由 NULL 变 fail（直接字段断言）',
          {'qs': 'fail'}, {'qs': a['qs']}, a['qs'] == 'fail', 'AC-18-a 断言 1')
    check('AC18-2', '写入命中的恰好是该产出对应的实例（gloval_sn 链定位）',
          {'located_item': 'item_id', 'qs_of_item': 'fail'},
          {'located_item': a['located_item'], 'item_id': item_id, 'qs_of_item': a['qs']},
          a['located_item'] == item_id and a['qs'] == 'fail', 'AC-18-a 断言 2 / RC-14')
    changed_others = [k for k, v in (a['other_quality_status'] or {}).items() if v is not None]
    check('AC18-3', '未命中其它实例：其余实例 quality_status 未被顺手改写',
          {'others_changed': []}, {'others_changed': a.get('others_changed')},
          not a.get('others_changed'), 'AC-18-a 断言 2（不得写到别的实例）')

    # pass 提交 ⇒ 字段写 pass（不得只实现 fail 分支）
    item_p, task_p = new_item_task(env, ctx, 'B', 32, 4, suffix='AC18P')
    report(env, task_p, 4)
    with env['app'].app_context():
        task = M.TaskAssignment.query.get(task_p)
        pr_p = M.ProductionRecord.query.filter_by(global_sn=task.global_sn).first()
    from app import models as _M
    with env['app'].app_context():
        inspection_task = _M.InspectionTask(target_type='production_record', target_id=pr_p.id,
                                            global_sn=_M.SerialNumber.get_next_number(),
                                            inspector_id=ctx['admin_id'], status='in_progress',
                                            created_by=ctx['admin_id'], template_id=ctx['template_id'])
        db.session.add(inspection_task)
        db.session.flush()
        record = _M.InspectionRecord(global_sn=_M.SerialNumber.get_next_number(),
                                     task_id=inspection_task.id, template_id=ctx['template_id'],
                                     inspector_id=ctx['admin_id'], inspection_date=date.today(),
                                     result='pass')
        db.session.add(record)
        db.session.commit()
        record_id_p = record.id
    sub_code_p, _, _ = submit_inspection(env, ctx, task_p, 'pass')
    out['ac18_pass'] = {'submit_http': sub_code_p, 'qs': qs(env, item_p)}
    check('AC18-4', 'pass 提交 ⇒ 字段写 pass（不得只实现 fail 分支）',
          {'qs': 'pass'}, {'qs': out['ac18_pass']['qs']},
          out['ac18_pass']['qs'] == 'pass', 'AC-18-a 断言 3')
    RAW['ac13_18'] = out
    return out


# ------------------------------------------------------------------ 段三：计件口径
def section_amounts(env, ctx):
    out = {}
    from app import db
    from app import models as M
    from app.services import mes_service as piecework
    tag = ctx['tag']
    day = date(2026, 10, 9)
    with env['app'].app_context():
        # 计件口径需要「同一员工、同一区间」对齐 ⇒ 专用员工（其全部生产记录都在本区间内），
        # 否则 S2（Employee.total_salary 无区间概念）与 S1（区间窗口）不可比。
        employee = M.Employee(employee_id='_w2w3piece%s' % tag, name='_w2w3 计件员工',
                             position='普通员工', base_salary=0.0, coefficient=1.5,
                             department='_w2w3p', hire_date=date(2026, 1, 1))
        db.session.add(employee)
        db.session.flush()
        emp_id = employee.id
        proc = M.ProcessPrice(process_code='_w2w3_piece_%s' % tag,
                              process_name='_w2w3 计件工序 %s' % tag, price=20.0, version=1,
                              needs_inspection=False)
        db.session.add(proc)
        db.session.flush()
        rework_task = M.TaskAssignment(employee_id=employee.id, process_id=proc.id,
                                       target_date=day, quantity=10, status='pending',
                                       task_type='auto', notes='返工 不合格单#_w2w3')
        db.session.add(rework_task)
        db.session.flush()
        r_rework = M.ProductionRecord(employee_id=employee.id, process_id=proc.id, quantity=10,
                                      date=day, global_sn=rework_task.global_sn,
                                      notes='_w2w3 返工记录')
        r_normal = M.ProductionRecord(employee_id=employee.id, process_id=proc.id, quantity=2,
                                      date=day, notes='_w2w3 正常记录')
        db.session.add_all([r_rework, r_normal])
        db.session.flush()
        item_for_nc = M.ProductionBatchItem.query.first()
        wp = M.Workpiece(code='_w2w3WP_%s' % tag, status='machining',
                         product_id=ctx['A']['product_id'])
        db.session.add(wp)
        db.session.flush()
        insp_task = M.InspectionTask(global_sn=M.SerialNumber.get_next_number(),
                                     target_type='workpiece', target_id=wp.id,
                                     inspector_id=ctx['admin_id'], status='in_progress',
                                     created_by=ctx['admin_id'])
        db.session.add(insp_task)
        db.session.flush()
        insp_record = M.InspectionRecord(global_sn=M.SerialNumber.get_next_number(),
                                        task_id=insp_task.id,
                                        inspector_id=ctx['admin_id'],
                                        inspection_date=day, result='fail')
        db.session.add(insp_record)
        db.session.flush()
        nc = M.NonconformityRecord(record_id=insp_record.id, type='rework',
                                  handler_id=ctx['admin_id'], handling_date=day,
                                  handling_result='_w2w3 返工', status='done',
                                  workpiece_id=wp.id, target_type='workpiece', target_id=wp.id,
                                  rework_task_id=rework_task.id, scrap_cost=0)
        db.session.add(nc)
        db.session.commit()
        out['fixture'] = {'rework_record_id': r_rework.id, 'normal_record_id': r_normal.id,
                          'rework_task_id': rework_task.id, 'nc_id': nc.id,
                          'price': proc.price, 'coefficient': employee.coefficient,
                          'item_id_for_nc': item_for_nc.id if item_for_nc else None}

    def _switch(value):
        """写开关（只动副本库）；读侧唯一入口是 piecework.rework_counts_piecework。"""
        with env['app'].app_context():
            row = M.SystemConfig.query.filter_by(key='quality.rework_counts_piecework').first()
            if row is None:
                M.SystemConfig.seed_defaults()
                db.session.commit()
                row = M.SystemConfig.query.filter_by(key='quality.rework_counts_piecework').first()
            if row is None:
                raise RuntimeError('副本库缺 quality.rework_counts_piecework 种子行')
            row.value = 'true' if value else 'false'
            db.session.commit()
            M.SystemConfig.invalidate_cache('quality.rework_counts_piecework')

    def _amounts():
        with env['app'].app_context():
            records = M.ProductionRecord.query.filter(M.ProductionRecord.employee_id == emp_id,
                                                      M.ProductionRecord.date == day).all()
            employee = M.Employee.query.get(emp_id)
            counted, dropped, excluded = piecework.piecework_breakdown(records)
            normal_only = [r for r in records if r.id == out['fixture']['normal_record_id']]
            total_salary = employee.total_salary
            base = employee.base_salary or 0.0
            adjustments = sum(bp.amount if bp.type == 'bonus' else -bp.amount
                              for bp in employee.bonuses_penalties)
            return {'counted': round(counted, 6), 'dropped': round(dropped, 6),
                    'excluded': sorted(excluded), 'normal_only': round(
                        piecework.piecework_amount(normal_only), 6),
                    'total_salary': round(total_salary, 6),
                    's2_piecework': round((total_salary - base - adjustments)
                                          / (employee.coefficient or 1.0), 6)}

    _switch(False)
    off = _amounts()
    http_off = env['client'].post('/salary_calculation',
                                 data={'start_date': day.isoformat(), 'end_date': day.isoformat(),
                                       'department': '_w2w3p', 'employee_id': str(emp_id)})
    html_off = http_off.data.decode('utf-8', 'replace')
    _switch(True)
    on = _amounts()
    http_on = env['client'].post('/salary_calculation',
                                data={'start_date': day.isoformat(), 'end_date': day.isoformat(),
                                      'department': '_w2w3p', 'employee_id': str(emp_id)})
    html_on = http_on.data.decode('utf-8', 'replace')
    _switch(False)   # 复位：默认口径（RC-18 的反面：不得依赖当前值）
    out['emp_id_piece'] = emp_id
    out.update({'off': off, 'on': on, 'http_off': http_off.status_code,
                'http_on': http_on.status_code,
                'html_off_has_60': '>60.00<' in html_off, 'html_off_has_360': '>360.00<' in html_off,
                'html_on_has_60': '>60.00<' in html_on, 'html_on_has_360': '>360.00<' in html_on})
    delta = round(on['counted'] - off['counted'], 6)
    rework_contribution = round(out['fixture']['price'] * 10, 6)
    check('AC26-a', '开关 false→true 的计件差值 ≠ 0（形状断言）',
          {'delta': '!=0', 'equals_rework_contribution': rework_contribution},
          {'delta': delta}, abs(delta) > 1e-9, 'AC-26-a / RC-17')
    check('AC25-a', 'false 时返工记录**不计件**（剔除额 == 返工贡献）',
          {'dropped': rework_contribution, 'counted': 2 * 20.0, 'excluded': '1 条'},
          {'dropped': off['dropped'], 'counted': off['counted'],
           'excluded_count': len(off['excluded'])},
          abs(off['dropped'] - rework_contribution) < 1e-9
          and abs(off['counted'] - 40.0) < 1e-9 and len(off['excluded']) == 1, 'AC-25-a')
    check('AC27-C', '非返工记录两态**完全相同**（不得回归）',
          {'off': 40.0, 'on': 40.0},
          {'off': off['normal_only'], 'on': on['normal_only']},
          abs(off['normal_only'] - on['normal_only']) < 1e-9, 'AC-27-C')
    check('AC04-d', 'S1 == S2（Employee.total_salary 同口径）',
          {'s1': off['counted'], 's2': off['s2_piecework'],
           's1_on': on['counted'], 's2_on': on['s2_piecework']},
          {'s1': off['counted'], 's2': off['s2_piecework'],
           's1_on': on['counted'], 's2_on': on['s2_piecework']},
          abs(off['counted'] - off['s2_piecework']) < 1e-6
          and abs(on['counted'] - on['s2_piecework']) < 1e-6, 'AC-04-d（S1/S2）')
    check('AC04-d-http', 'S1 真端点两态数字不同（页面计件单元格）',
          {'off_page': '>60.00<', 'on_page': '>360.00<'},
          {'off_has_60': out['html_off_has_60'], 'off_has_360': out['html_off_has_360'],
           'on_has_60': out['html_on_has_60'], 'on_has_360': out['html_on_has_360'],
           'http': [out['http_off'], out['http_on']]},
          out['html_off_has_60'] and not out['html_off_has_360']
          and out['html_on_has_360'], 'AC-26-a（S1 端点实测）')

    # AC-04-e：唯一读取点 + 缺省 False；AC-04-e2：模板零命中；S3/S4 同口径（AST）
    read_sites = []
    for dirpath, dirnames, filenames in os.walk(os.path.join(REPO_ROOT, 'app')):
        dirnames[:] = [d for d in dirnames if d != '__pycache__']
        for name in sorted(filenames):
            if not name.endswith('.py'):
                continue
            path = os.path.join(dirpath, name)
            source = open(path, encoding='utf-8', errors='replace').read()
            if 'rework_counts_piecework' not in source and 'REWORK_SWITCH_KEY' not in source:
                continue
            try:
                tree = ast.parse(source)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                fn = node.func
                fname = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, 'id', None)
                if fname != 'get' or not node.args:
                    continue
                arg = node.args[0]
                key = arg.value if isinstance(arg, ast.Constant) else None
                if key != 'quality.rework_counts_piecework':
                    continue
                default = node.args[1] if len(node.args) > 1 else None
                default_is_false = isinstance(default, ast.Constant) and default.value is False
                read_sites.append({'file': os.path.relpath(path, REPO_ROOT).replace('\\', '/'),
                                   'line': node.lineno, 'default_is_false': default_is_false})
    template_hits = []
    for dirpath, dirnames, filenames in os.walk(os.path.join(REPO_ROOT, 'app', 'templates')):
        for name in filenames:
            path = os.path.join(dirpath, name)
            try:
                text = open(path, encoding='utf-8', errors='replace').read()
            except OSError:
                continue
            if 'rework_counts_piecework' in text:
                template_hits.append(os.path.relpath(path, REPO_ROOT).replace('\\', '/'))
    out['read_sites'] = read_sites
    out['template_hits'] = template_hits
    check('AC04-e', '开关在全仓**只有一个**读取点且缺省值为 False（不得缺省即计入）',
          {'sites': 1, 'default_is_false': True},
          {'sites': len(read_sites), 'sites_detail': read_sites},
          len(read_sites) == 1 and all(s['default_is_false'] for s in read_sites),
          'AC-04-e / RC-18')
    check('AC04-e2', '三个工资模板中零命中（模板不得分支）',
          {'hits': 0}, {'hits': template_hits}, not template_hits, 'AC-04-e2 / RC-19')
    routes_src = open(os.path.join(REPO_ROOT, 'app', 'main', 'routes.py'),
                      encoding='utf-8', errors='replace').read()
    call_count = len(re.findall(r'piecework_amount\(', routes_src))
    check('AC04-d-s34', 'S1/S3/S4 三处均已改为调用共享口径函数',
          {'calls_in_routes': 3}, {'calls_in_routes': call_count},
          call_count == 3, 'AC-04-d（S3/S4 同口径，防「主表变了、员工总工资没变」）')
    RAW['amounts'] = out
    return out


# ------------------------------------------------------------------ 段四：报废扣料
def set_raw(env, material_id, value):
    from app import db
    from app import models as M
    with env['app'].app_context():
        material = M.RawMaterial.query.get(material_id)
        material.quantity = float(value)
        db.session.commit()


def make_workpiece_nc(env, ctx, item_id, suffix, raw_material_id=None):
    """工件路径不合格单（阳性对照路径，与 uat P0-4.0 同法）：返回 (nc_id, workpiece_id)。"""
    from app import db
    from app import models as M
    from app.services import mes_service
    with env['app'].app_context():
        workpiece = M.Workpiece(code='_w2w3WP%s%s' % (ctx['tag'], suffix), status='machining',
                                product_id=ctx['A']['product_id'],
                                raw_material_id=raw_material_id, batch_item_id=item_id)
        db.session.add(workpiece)
        db.session.flush()
        task = M.InspectionTask(global_sn=M.SerialNumber.get_next_number(),
                                target_type='workpiece', target_id=workpiece.id,
                                inspector_id=ctx['admin_id'], status='in_progress',
                                created_by=ctx['admin_id'])
        db.session.add(task)
        db.session.flush()
        record = M.InspectionRecord(global_sn=M.SerialNumber.get_next_number(), task_id=task.id,
                                    inspector_id=ctx['admin_id'], inspection_date=date.today(),
                                    result='fail')
        db.session.add(record)
        db.session.commit()
        mes_service.apply_inspection_result(record)
        db.session.commit()
        nc = (M.NonconformityRecord.query.filter_by(workpiece_id=workpiece.id)
              .order_by(M.NonconformityRecord.id.desc()).first())
        return (nc.id if nc else None), workpiece.id


def section_scrap(env, ctx):
    out = {}
    rm1, rm2, rm3 = ctx['material_ids']

    # AC-29-ac：逐行各扣各自物料（默认件数 1）；对照料 rm3 不变
    item_id, task_id = new_item_task(env, ctx, 'A', 41, 4, suffix='SC1')
    set_raw(env, rm1, 100.0)
    set_raw(env, rm2, 100.0)
    set_raw(env, rm3, 100.0)
    report(env, task_id, 4, materials=[{'raw_material_id': rm1, 'quantity': 2.0},
                                       {'raw_material_id': rm2, 'quantity': 3.0}])
    nc_id, wp_id = make_workpiece_nc(env, ctx, item_id, 'SC1', raw_material_id=rm1)
    a1, a2, a3 = raw_qty(env, rm1), raw_qty(env, rm2), raw_qty(env, rm3)
    if nc_id:
        code, body = dispose(env, nc_id, action='scrap', scrap_cost=9.0, notes='_w2w3 报废')
        b1, b2, b3 = raw_qty(env, rm1), raw_qty(env, rm2), raw_qty(env, rm3)
        out['ac29_ac'] = {'dispose_http': code, 'body': body, 'before': [a1, a2, a3],
                          'after': [b1, b2, b3], 'nc': nc_row(env, nc_id),
                          'item_status': item_status(env, item_id)}
        check('AC29-ac', '报废扣料逐行各扣各自物料（N_i × 件数）且对照料不变',
              {'rm1': a1 - 2.0, 'rm2': a2 - 3.0, 'rm3': a3},
              {'rm1': b1, 'rm2': b2, 'rm3': b3},
              abs(b1 - (a1 - 2.0)) < 1e-9 and abs(b2 - (a2 - 3.0)) < 1e-9 and abs(b3 - a3) < 1e-9,
              'AC-29 / AC-29-c（不得只扣 wp.raw_material_id 那一条）')

    # AC-29-b：库存 < 扣量 ⇒ 夹紧到 0 + warning（四要素：物料/原量/请求量/夹紧后）
    item_b, task_b = new_item_task(env, ctx, 'A', 42, 4, suffix='SC2')
    set_raw(env, rm1, 100.0)
    set_raw(env, rm2, 100.0)
    report(env, task_b, 4, materials=[{'raw_material_id': rm1, 'quantity': 2.0},
                                      {'raw_material_id': rm2, 'quantity': 3.0}])
    nc_b, _wp_b = make_workpiece_nc(env, ctx, item_b, 'SC2', raw_material_id=rm1)
    set_raw(env, rm1, 1.0)
    if nc_b:
        _result, logs = captured(env['app'], lambda: dispose(env, nc_b, action='scrap',
                                                             scrap_cost=1.0, notes='_w2w3 夹紧'))
        clamp_logs = [m for lvl, m in logs if lvl in ('WARNING', 'ERROR') and '夹紧' in m]
        out['ac29_b'] = {'rm1_after': raw_qty(env, rm1), 'warnings': clamp_logs}
        has_four = bool(clamp_logs) and all(
            part in clamp_logs[0] for part in ('物料 %s' % rm1, '原量 1.0', '请求扣减 2.0',
                                               '夹紧后 0.0'))
        check('AC29-b', '扣量超过库存 ⇒ 夹紧到 0 且 warning 含四要素',
              {'rm1': 0.0, 'warning_4_elements': True},
              {'rm1': out['ac29_b']['rm1_after'], 'warnings': clamp_logs[:1]},
              abs(out['ac29_b']['rm1_after']) < 1e-9 and has_four, 'AC-29-b（不得为负）')

    # AC-29-d：取不到消耗数据 ⇒ 不扣任何料 + 「未扣减」说明
    item_d, task_d = new_item_task(env, ctx, 'A', 43, 2, suffix='SC3')
    set_raw(env, rm1, 50.0)
    report(env, task_d, 2)          # 不传 materials ⇒ 该产出无消耗明细
    nc_d, _wp_d = make_workpiece_nc(env, ctx, item_d, 'SC3', raw_material_id=rm1)
    before_d = raw_qty(env, rm1)
    if nc_d:
        _result, logs = captured(env['app'], lambda: dispose(env, nc_d, action='scrap',
                                                             scrap_cost=1.0, notes='_w2w3 无消耗'))
        noded = [m for lvl, m in logs if lvl in ('WARNING', 'ERROR') and '未扣减' in m]
        out['ac29_d'] = {'rm1_after': raw_qty(env, rm1), 'warnings': noded}
        check('AC29-d', '无消耗数据 ⇒ 料账不变且存在「未扣减」说明（不得默认减 1）',
              {'rm1': before_d, 'has_undeducted_note': True},
              {'rm1': out['ac29_d']['rm1_after'], 'notes': noded[:1]},
              abs(out['ac29_d']['rm1_after'] - before_d) < 1e-9 and bool(noded),
              'AC-29-d / RC-20')

    # AC-29-d2：显式报废件数 3 ⇒ 扣量 = N_i × 3 且报废入库数量 == 3
    item_e, task_e = new_item_task(env, ctx, 'A', 44, 4, suffix='SC4')
    set_raw(env, rm1, 100.0)
    set_raw(env, rm2, 100.0)
    report(env, task_e, 4, materials=[{'raw_material_id': rm1, 'quantity': 2.0},
                                      {'raw_material_id': rm2, 'quantity': 3.0}])
    nc_e, wp_e = make_workpiece_nc(env, ctx, item_e, 'SC4', raw_material_id=rm1)
    from app import models as M
    with env['app'].app_context():
        workpiece = M.Workpiece.query.get(wp_e)
        wp_code = workpiece.code if workpiece else None
    e1, e2 = raw_qty(env, rm1), raw_qty(env, rm2)
    if nc_e:
        dispose(env, nc_e, action='scrap', scrap_cost=3.0, scrap_quantity=3, notes='_w2w3 3件')
        f1, f2 = raw_qty(env, rm1), raw_qty(env, rm2)
        scrap_row = scrap_pieces(env, wp_code)
        out['ac29_d2'] = {'rm1': [e1, f1], 'rm2': [e2, f2], 'scrap_inbound': scrap_row,
                          'wp_code': wp_code}
        check('AC29-d2', '显式报废件数 3 ⇒ 扣量 = N_i × 3，报废入库数量 == 3',
              {'rm1': e1 - 6.0, 'rm2': e2 - 9.0, 'scrap_inbound': 3.0},
              {'rm1': f1, 'rm2': f2, 'scrap_inbound': scrap_row},
              abs(f1 - (e1 - 6.0)) < 1e-9 and abs(f2 - (e2 - 9.0)) < 1e-9
              and abs(scrap_row - 3.0) < 1e-9, 'AC-29-d2（mes_service.py 报废入库数量同步）')

    # 非法件数 ⇒ 4xx（走既有 ValueError→400 通道）
    item_x, task_x = new_item_task(env, ctx, 'A', 45, 2, suffix='SC5')
    report(env, task_x, 2)
    nc_x, _wp_x = make_workpiece_nc(env, ctx, item_x, 'SC5', raw_material_id=rm1)
    if nc_x:
        code_neg, _ = dispose(env, nc_x, action='scrap', scrap_quantity=0, notes='_w2w3 非法件数')
        out['ac29_neg'] = {'http': code_neg}
        check('AC29-neg', '非法报废件数（0）⇒ 4xx 且不被静默接受',
              {'http_in': [400, 422]}, {'http': code_neg},
              code_neg in (400, 422), 'AC-30-b 的同类非法值通道')
    RAW['scrap'] = out
    return out


# ------------------------------------------------------------------ 段五：返工件数
def section_rework(env, ctx):
    out = {}
    # AC-30-a：默认链（显式不传 rework_quantity）⇒ quantity == 来源生产记录件数 Q
    item_a, task_a = new_item_task(env, ctx, 'A', 51, 10, suffix='RW1')
    report(env, task_a, 10)
    submit_inspection(env, ctx, task_a, 'fail')
    nc_a = latest_nc_for_item(env, item_a)
    if nc_a:
        code, _ = dispose(env, nc_a, action='rework', rework_process_id=ctx['A']['process_id'],
                          employee_id=ctx['emp_id'], notes='_w2w3 返工默认链')
        row = nc_row(env, nc_a)
        from app import models as M
        with env['app'].app_context():
            task = M.TaskAssignment.query.get(row['rework_task_id']) if row and row['rework_task_id'] else None
            info = None if task is None else {'id': task.id, 'quantity': task.quantity,
                                              'notes': task.notes,
                                              'process_id': task.process_id,
                                              'employee_id': task.employee_id}
        out['ac30_a'] = {'dispose_http': code, 'task': info, 'nc': row}
        check('AC30-a', '返工默认链 ⇒ 新任务件数 == 来源生产记录件数（Q=10）',
              {'quantity': 10, 'process_id': ctx['A']['process_id'], 'employee_id': ctx['emp_id']},
              info or {}, bool(info) and info['quantity'] == 10
              and info['process_id'] == ctx['A']['process_id']
              and info['employee_id'] == ctx['emp_id'], 'AC-30-a / P0-4.2')

    # AC-30-b：显式 rework_quantity 覆盖 + 非法值 4xx
    item_b, task_b = new_item_task(env, ctx, 'A', 52, 10, suffix='RW2')
    report(env, task_b, 10)
    submit_inspection(env, ctx, task_b, 'fail')
    nc_b = latest_nc_for_item(env, item_b)
    if nc_b:
        dispose(env, nc_b, action='rework', rework_process_id=ctx['A']['process_id'],
                employee_id=ctx['emp_id'], rework_quantity=7, notes='_w2w3 显式件数')
        row = nc_row(env, nc_b)
        from app import models as M
        with env['app'].app_context():
            task = M.TaskAssignment.query.get(row['rework_task_id'])
            explicit_qty = task.quantity if task else None
        out['ac30_b'] = {'quantity': explicit_qty}
        check('AC30-b', '显式 rework_quantity=7 覆盖来源件数（10）',
              {'quantity': 7}, {'quantity': explicit_qty}, explicit_qty == 7, 'AC-30-b')
    item_c, task_c = new_item_task(env, ctx, 'A', 53, 10, suffix='RW3')
    report(env, task_c, 10)
    submit_inspection(env, ctx, task_c, 'fail')
    nc_c = latest_nc_for_item(env, item_c)
    if nc_c:
        code_neg, _ = dispose(env, nc_c, action='rework', rework_process_id=ctx['A']['process_id'],
                              employee_id=ctx['emp_id'], rework_quantity=0, notes='_w2w3 非法')
        out['ac30_b_neg'] = {'http': code_neg}
        check('AC30-b-neg', '非法 rework_quantity（0）⇒ 4xx 且不静默落回 1/Q',
              {'http_in': [400, 422]}, {'http': code_neg}, code_neg in (400, 422), 'AC-30-b')

    # AC-30-c：取不到来源生产记录 ⇒ 兜底 1 + **留痕**
    from app import db
    from app import models as M
    from app.services import mes_service
    with env['app'].app_context():
        workpiece = M.Workpiece(code='_w2w3WP%sRW4' % ctx['tag'], status='machining',
                                product_id=ctx['A']['product_id'])
        db.session.add(workpiece)
        db.session.flush()
        task = M.InspectionTask(global_sn=M.SerialNumber.get_next_number(),
                                target_type='workpiece', target_id=workpiece.id,
                                inspector_id=ctx['admin_id'], status='in_progress',
                                created_by=ctx['admin_id'])
        db.session.add(task)
        db.session.flush()
        record = M.InspectionRecord(global_sn=M.SerialNumber.get_next_number(), task_id=task.id,
                                    inspector_id=ctx['admin_id'], inspection_date=date.today(),
                                    result='fail')
        db.session.add(record)
        db.session.commit()
        mes_service.apply_inspection_result(record)
        db.session.commit()
        nc = (M.NonconformityRecord.query.filter_by(workpiece_id=workpiece.id)
              .order_by(M.NonconformityRecord.id.desc()).first())
        nc_c_id = nc.id if nc else None
    if nc_c_id:
        dispose(env, nc_c_id, action='rework', rework_process_id=ctx['A']['process_id'],
                employee_id=ctx['emp_id'], notes='_w2w3 兜底')
        row = nc_row(env, nc_c_id)
        with env['app'].app_context():
            new_task = M.TaskAssignment.query.get(row['rework_task_id']) if row['rework_task_id'] else None
            info = None if new_task is None else {'quantity': new_task.quantity, 'notes': new_task.notes}
        out['ac30_c'] = info or {}
        check('AC30-c', '取不到来源生产记录 ⇒ 件数 1 且 notes 留痕（禁止静默写死 1）',
              {'quantity': 1, 'note_has': '件数取默认值1（未找到来源生产记录）'},
              info or {}, bool(info) and info['quantity'] == 1
              and '件数取默认值1（未找到来源生产记录）' in (info.get('notes') or ''),
              'AC-30-c / 07b §2.3 禁令')

    # AC-30-NEG / RC-16：批次自动派工（task_type='auto' 且 notes 非返工前缀）不得被当返工
    from app.services import mes_service as piecework
    day = date(2026, 10, 10)
    with env['app'].app_context():
        proc = M.ProcessPrice(process_code='_w2w3_auto_%s' % ctx['tag'],
                              process_name='_w2w3 自动派工工序 %s' % ctx['tag'],
                              price=5.0, version=1, needs_inspection=False)
        db.session.add(proc)
        db.session.flush()
        auto_task = M.TaskAssignment(employee_id=ctx['emp_id'], process_id=proc.id,
                                     target_date=day, quantity=8, status='pending',
                                     task_type='auto', notes='批次自动派工（非返工）')
        db.session.add(auto_task)
        db.session.flush()
        record = M.ProductionRecord(employee_id=ctx['emp_id'], process_id=proc.id, quantity=8,
                                    date=day, global_sn=auto_task.global_sn,
                                    notes='_w2w3 自动派工产出')
        db.session.add(record)
        db.session.commit()
        row = M.SystemConfig.query.filter_by(key='quality.rework_counts_piecework').first()
        row.value = 'false'
        db.session.commit()
        M.SystemConfig.invalidate_cache('quality.rework_counts_piecework')
        amount = piecework.piecework_amount([record])
        is_rework = piecework.is_rework_task(auto_task)
        out['ac30_neg'] = {'amount': round(amount, 6), 'is_rework': is_rework}
        check('AC30-NEG', '批次自动派工产出不计为返工（计件不被剔除）',
              {'amount': 8 * 5.0, 'is_rework': False},
              out['ac30_neg'], abs(amount - 40.0) < 1e-9 and is_rework is False,
              'AC-30-NEG / RC-16（否决 task_type==auto 单判）')
    RAW['rework'] = out
    return out


# ------------------------------------------------------------------ 段六：静态门禁与反向约束
def section_static(env):
    out = {'gates': []}
    shim = os.path.join('scripts', '_sandbox_compat.py')
    gates = (
        ('check_templates', [os.path.join('scripts', 'check_templates.py')],
         ['parsed 87 files', '44 declared', 'landing] 5', 'RESULT: OK']),
        ('check_migration_heads', [os.path.join('scripts', 'check_migration_heads.py')],
         ["HEADS=['p1nonctarget']", 'head_count=1', 'revisions=35']),
        ('check_properties', [os.path.join('scripts', 'check_properties.py')],
         ['已扫描 23 个文件，模型类 74 个', 'RESULT: OK']),
        ('check_model_refs', [os.path.join('scripts', 'check_model_refs.py'), '--root', 'app'],
         ['violations 0', 'RESULT: OK']),
        ('route_inventory', [shim, os.path.join('scripts', 'route_inventory.py')],
         ['total rules=271', 'duplicate (method,path) registrations=0']),
        ('check_db_bootstrap', [shim, os.path.join('scripts', 'check_db_bootstrap.py')],
         ['6712', 'RESULT' if False else 'OK:']),
    )
    for name, argv, expects in gates:
        res = run_child([os.path.join(REPO_ROOT, argv[0])] + list(argv[1:]), cwd=REPO_ROOT,
                        timeout=1800, label='w2w3-' + name)
        body = res['stdout'] + res['stderr']
        missing = [e for e in expects if e not in body]
        out['gates'].append({'gate': name, 'exit_code': res['exit_code'], 'missing': missing,
                             'real_db_unchanged': res['real_db_unchanged']})
        check('SG-%s' % name, '静态门禁 %s exit 0 且期望行命中' % name,
              {'exit': 0, 'missing': []},
              {'exit': res['exit_code'], 'missing': missing},
              res['exit_code'] == 0 and not missing, ' '.join(argv))

    # RC-15：不得新增列/迁移来「解决」返工识别（只认**列声明**，不把文档里的词当成列）
    column_hits = []
    column_pattern = re.compile(r'^\s*is_rework\s*=\s*db\.Column', re.M)
    for dirpath, dirnames, filenames in os.walk(os.path.join(REPO_ROOT, 'app')):
        dirnames[:] = [d for d in dirnames if d != '__pycache__']
        for name in filenames:
            if not name.endswith('.py'):
                continue
            path = os.path.join(dirpath, name)
            text = open(path, encoding='utf-8', errors='replace').read()
            if column_pattern.search(text):
                column_hits.append(os.path.relpath(path, REPO_ROOT).replace('\\', '/'))
    status_file = os.path.join(tmp_dir(), 'git-status-migrations.txt')
    with open(status_file, 'wb') as fh:
        subprocess.run(['git', 'status', '--porcelain', '--', 'migrations'],
                       cwd=REPO_ROOT, stdout=fh, stderr=subprocess.DEVNULL)
    migration_rows = [ln for ln in open(status_file, encoding='utf-8', errors='replace')
                      .read().splitlines() if ln.strip()]
    out['is_rework_column_hits'] = column_hits
    out['migration_changes'] = migration_rows
    check('RC-15', '无新增列（is_rework 列声明零命中）且 migrations/ 无改动',
          {'column_hits': [], 'migration_changes': []},
          {'column_hits': column_hits, 'migration_changes': migration_rows},
          not column_hits and not migration_rows, 'RC-15（07b §2.2 否决新增列；禁止 migrate）')

    real_after = sha256_file(REAL_DB)
    check('ISO-db', '真实库 app.db 全程未被改动',
          {'sha256': REAL_DB_SHA256_EXPECTED},
          {'before': out.get('real_db_before'), 'after': real_after},
          real_after == REAL_DB_SHA256_EXPECTED, 'AC-22 / RC-22')
    out['real_db_after'] = real_after
    RAW['static'] = out
    return out


# ------------------------------------------------------------------ 主流程
def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError, OSError):
        pass
    parser = argparse.ArgumentParser(description='W2/W3 (P-02..P-07) verification probe')
    parser.add_argument('--scenario', default='all',
                        choices=('all', 'cells', 'ac13_18', 'amounts', 'scrap', 'rework', 'static'))
    args = parser.parse_args(argv)

    started = time.strftime('%Y-%m-%d %H:%M:%S')
    real_before = sha256_file(REAL_DB)
    print('=' * 78)
    print('[w2w3_probe] RUN_ID=%s scenario=%s started=%s' % (RUN_ID, args.scenario, started))
    print('[w2w3_probe] real db sha256 before = %s' % real_before)
    print('=' * 78)

    env = build_app()
    note('副本库 %s（samefile(real)=%s）' % (env['copy_path'], env['copy_samefile_as_real']))
    note('登录 HTTP %s（_t_admin）' % env['login_status'])
    ctx = build_fixtures(env)
    note('夹具：产品 A(有检) 实例 %s / 产品 B(无检) 实例 %s / 员工 %s / 原料 %s'
         % (ctx['A']['item_id'], ctx['B']['item_id'], ctx['emp_id'], ctx['material_ids']))
    RAW['copy'] = {'path': env['copy_path'], 'sha256': env['copy_sha256'],
                   'samefile_as_real': env['copy_samefile_as_real'],
                   'db_uri': env['db_uri'], 'login_status': env['login_status']}
    RAW['fixtures'] = {k: v for k, v in ctx.items() if k not in ('password',)}

    if args.scenario in ('all', 'cells'):
        section_cells(env, ctx)
    if args.scenario in ('all', 'ac13_18'):
        section_ac13_18(env, ctx)
    if args.scenario in ('all', 'amounts'):
        section_amounts(env, ctx)
    if args.scenario in ('all', 'scrap'):
        section_scrap(env, ctx)
    if args.scenario in ('all', 'rework'):
        section_rework(env, ctx)
    if args.scenario in ('all', 'static'):
        out = section_static(env)
        out['real_db_before'] = real_before

    real_after = sha256_file(REAL_DB)
    summary = {
        'run_id': RUN_ID, 'started': started, 'finished': time.strftime('%Y-%m-%d %H:%M:%S'),
        'interpreter': sys.executable, 'scenario': args.scenario,
        'total': len(CHECKS),
        'passed': len([c for c in CHECKS if c['status'] == 'passed']),
        'failed': len([c for c in CHECKS if c['status'] != 'passed']),
        'real_db_sha256_before': real_before, 'real_db_sha256_after': real_after,
        'real_db_unchanged': real_before == real_after == REAL_DB_SHA256_EXPECTED,
    }
    result = {'summary': summary, 'checks': CHECKS, 'notes': NOTES, 'raw': RAW}
    transcript_lines = []
    for row in CHECKS:
        transcript_lines.append('[%s] %-12s %s' % (row['status'].upper(), row['id'], row['desc']))
        transcript_lines.append('        expected=%s actual=%s %s'
                                % (json.dumps(row['expected'], ensure_ascii=True),
                                   json.dumps(row['actual'], ensure_ascii=True), row['evidence']))
    transcript = '\n'.join(transcript_lines) + '\n'
    saved = [save_evidence('w2w3-criteria.json',
                           json.dumps(result, ensure_ascii=False, indent=1, default=str)),
             save_evidence('w2w3-transcript.txt', transcript)]
    print('')
    print('[summary] %s' % json.dumps(summary, ensure_ascii=True, sort_keys=True))
    for path in saved:
        print('[evidence] -> %s' % os.path.relpath(path, REPO_ROOT).replace('\\', '/'))
    verdict = 'PASS' if summary['failed'] == 0 else 'FAIL'
    print('[verdict] %s' % verdict)
    return 0 if verdict == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
