# -*- coding: utf-8 -*-
"""t3（后端架构师）现场复核探针 —— 只读仓库源码 + 只写 app.db **副本**。

用途：把「文档说已实现 / 未实现」的后端条目做**行为级**验证，而不是只数读取点。

纪律（与本任务硬纪律一致）：
1. 所有数据写 `scripts/_test_bootstrap.make_app()` 生成的 **app.db 副本**；真实 app.db 只读不写；
2. 上传类端点把 `app.config['TEMP_FOLDER']` 改指到副本临时目录 ⇒ **不在仓库 `uploads/` 留下残留**；
3. 不修改任何既有文件；本文件本身是本任务的新增产物。

覆盖：
  A. 真库旁证（副本读）：`audit_log` 的 `target_id IS NULL` 统计（P1）
  B. B4-01/B4-03：报工路径 fail ⇒ 建 NC + 自动回写 `quality_status`（行为）
  C. B4-02：门禁拒绝 + 处置 done 后恢复（阳性对照 2b）
  D. B5-05：返工件数 = 显式入参 / 来源生产记录 quantity（行为）
  E. B5-04：报废扣料按逐行实际消耗 N×件数（行为）
  F. P9：报工路径报废**不产生** scrap 台账行（行为）
  G. B5-01/B5-02：`quality.rework_counts_piecework` false/true **工资数字差分**（行为）
  H. P3/P4：`/employees/import` 整单拒绝 + 上传残留（行为，TEMP_FOLDER 已改指副本）
"""
import json
import os
import pathlib
import sys
import tempfile
from datetime import date, datetime, timedelta

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

from _test_bootstrap import ensure_role_users, login_as, make_app  # noqa: E402

app, copy_path = make_app(fresh=True)
TMP = pathlib.Path(tempfile.mkdtemp(prefix='t3_probe_'))
# 上传落点（= 被改造的 TEMP_FOLDER）与「本地待上传文件」分开放，避免把本地文件误判成残留
UP = TMP / 'uploads_temp'
SRC = TMP / 'incoming'
UP.mkdir(parents=True, exist_ok=True)
SRC.mkdir(parents=True, exist_ok=True)
app.config['TEMP_FOLDER'] = str(UP)
app.config['UPLOAD_FOLDER'] = str(UP)

from app import db  # noqa: E402
from app import models as M  # noqa: E402
from app.services import mes_service  # noqa: E402

OUT = {'copy_path': copy_path, 'tmp_dir': str(TMP), 'uploads_temp_dir': str(UP),
       'real_db_sha256_expected':
       'F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065'}

TODAY = date(2026, 10, 8)
TAG = '_t3_' + datetime.now().strftime('%H%M%S')


def jnum(x):
    try:
        return round(float(x), 4)
    except (TypeError, ValueError):
        return x


# --------------------------------------------------------------------------- A
with app.app_context():
    OUT['A_P1_audit_log_readonly'] = {
        'total': M.AuditLog.query.count(),
        'target_id_is_null': M.AuditLog.query.filter(M.AuditLog.target_id.is_(None)).count(),
        'null_and_can_rollback_true': M.AuditLog.query.filter(
            M.AuditLog.target_id.is_(None), M.AuditLog.can_rollback.is_(True)).count(),
    }


# --------------------------------------------------------------- 夹具构造
def build_report_chain(seq):
    """报工链：实例 + 任务(global_sn) + 生产记录(同 global_sn) + 质检任务/记录(fail)。"""
    admin = M.User.query.filter_by(role='admin').first() or M.User.query.first()
    emp = M.Employee.query.first()
    prod = M.Product.query.first()
    proc = M.ProcessPrice.query.first()
    order = M.ProductionOrder(
        order_number=f'{TAG}ORD{seq}', product_id=prod.id, planned_quantity=10,
        planned_start_date=TODAY, planned_end_date=TODAY + timedelta(days=30),
        created_by=admin.id)
    db.session.add(order)
    db.session.flush()
    batch = M.ProductionBatch(production_order_id=order.id, batch_quantity=10,
                              batch_number=f'{TAG}BAT{seq}')
    db.session.add(batch)
    db.session.flush()
    bi = M.ProductionBatchItem(batch_id=batch.id, item_sequence=9900 + seq,
                               product_code=f'{TAG}BI{seq}', status='in_progress')
    db.session.add(bi)
    db.session.flush()
    task = M.TaskAssignment(employee_id=emp.id, process_id=proc.id, target_date=TODAY,
                            quantity=5, status='completed', batch_item_id=bi.id,
                            task_type='auto')
    db.session.add(task)
    db.session.flush()
    rec = M.ProductionRecord(employee_id=emp.id, process_id=proc.id, quantity=5, date=TODAY,
                             global_sn=task.global_sn, notes=None)
    db.session.add(rec)
    db.session.flush()
    itask = M.InspectionTask(
        global_sn=M.SerialNumber.get_next_number(), template_id=None, inspector_id=admin.id,
        target_type='production_record', target_id=rec.id, status='completed',
        created_by=admin.id)
    db.session.add(itask)
    db.session.flush()
    irec = M.InspectionRecord(
        global_sn=M.SerialNumber.get_next_number(), task_id=itask.id, template_id=None,
        inspector_id=admin.id, inspection_date=TODAY, result='fail', notes=f'{TAG} 探针 fail')
    db.session.add(irec)
    db.session.flush()
    return {'admin': admin.id, 'emp': emp.id, 'proc': proc.id, 'prod': prod.id,
            'order': order.id, 'batch': batch.id, 'bi': bi.id, 'task': task.id,
            'rec': rec.id, 'itask': itask.id, 'irec': irec.id,
            'task_global_sn': task.global_sn}


with app.app_context():
    c1 = build_report_chain(1)
    c2 = build_report_chain(2)          # 供工资差分用的独立链
    # 干净实例（门禁阴性对照）
    prod = M.Product.query.first()
    bi_clean = M.ProductionBatchItem(batch_id=c1['batch'], item_sequence=9998,
                                     product_code=f'{TAG}BICLEAN', status='in_progress')
    db.session.add(bi_clean)
    db.session.flush()
    c1['bi_clean'] = bi_clean.id
    # 报废扣料用原材料（3 条：两条被同一记录消耗，一条对照）
    cat = M.RawMaterialCategory.query.first()
    if cat is None:
        cat = M.RawMaterialCategory(name=f'{TAG}品类', code=f'{TAG}C')
        db.session.add(cat)
        db.session.flush()
    rms = []
    for i in range(3):
        rm = M.RawMaterial(supplier=f'{TAG}供应商', category_id=cat.id,
                           melt_number=f'{TAG}M{i}', supplier_number=f'{TAG}S{i}',
                           internal_number=f'{TAG}IN{i}', quantity=100.0, status='in_stock')
        db.session.add(rm)
        db.session.flush()
        rms.append(rm.id)
    c1['rms'] = rms
    # 该生产记录的两条消耗行（不同物料）：3.0 / 4.0（单件消耗）
    db.session.add_all([
        M.ProductionRecordMaterial(production_record_id=c1['rec'], raw_material_id=rms[0], quantity=3.0),
        M.ProductionRecordMaterial(production_record_id=c1['rec'], raw_material_id=rms[1], quantity=4.0),
    ])
    db.session.commit()
    OUT['fixtures'] = {'c1': c1, 'c2': c2}


# --------------------------------------------------------------------------- B/C
with app.app_context():
    def gate(bi_id, rec_id=None):
        bi = M.ProductionBatchItem.query.get(bi_id)
        rec = M.ProductionRecord.query.get(rec_id) if rec_id else None
        allowed, reason = mes_service.qc_gate_allows_output(batch_item=bi, production_record=rec)
        return {'allowed': allowed, 'reason': reason,
                'quality_status': bi.quality_status, 'status': bi.status}

    before = {
        'nc_rows': M.NonconformityRecord.query.count(),
        'quality_status': M.ProductionBatchItem.query.get(c1['bi']).quality_status,
        'gate': gate(c1['bi'], c1['rec']),
        'gate_clean_control': gate(c1['bi_clean']),
    }
    # 模拟「质检员提交 fail」：quality.py 在调用前先把任务置 completed（:961-964）
    itask = M.InspectionTask.query.get(c1['itask'])
    itask.status = 'completed'
    irec = M.InspectionRecord.query.get(c1['irec'])
    task = M.InspectionTask.query.get(c1['itask'])
    db.session.commit()

    ret = mes_service.apply_production_record_result(irec, task)
    db.session.commit()

    nc = M.NonconformityRecord.query.filter_by(record_id=irec.id).first()
    after = {
        'return': {'production_record': ret[0].id if ret[0] else None,
                   'batch_item': ret[1].id if ret[1] else None,
                   'written_quality_status': ret[2]},
        'nc_created': None if nc is None else {
            'id': nc.id, 'target_type': nc.target_type, 'target_id': nc.target_id,
            'workpiece_id': nc.workpiece_id, 'status': nc.status, 'type': nc.type},
        'nc_rows_delta': M.NonconformityRecord.query.count() - before['nc_rows'],
        'quality_status': M.ProductionBatchItem.query.get(c1['bi']).quality_status,
        'gate_after_fail': gate(c1['bi'], c1['rec']),
        'gate_clean_control': gate(c1['bi_clean']),
    }
    OUT['B_B4_01_03'] = {'before': before, 'after': after}
    OUT['C_B4_02'] = {'gate_after_fail': after['gate_after_fail']}


# ------------------------------------------------------------------- G（工资差分）
with app.app_context():
    def set_switch(value):
        cfg = M.SystemConfig.query.filter_by(key='quality.rework_counts_piecework').first()
        if cfg is None:
            cfg = M.SystemConfig(key='quality.rework_counts_piecework', value='false',
                                 value_type='bool', category='quality', label='返工工时重复计件')
            db.session.add(cfg)
        cfg.value = 'true' if value else 'false'
        db.session.commit()
        M.SystemConfig.invalidate_cache()
        return M.SystemConfig.get('quality.rework_counts_piecework')

    # 用真实链路造返工：c2 的 fail → NC → 处置 rework（显式件数 5）→ 返工任务 → 该任务报工出的记录
    itask2 = M.InspectionTask.query.get(c2['itask'])
    itask2.status = 'completed'
    db.session.commit()
    mes_service.apply_production_record_result(M.InspectionRecord.query.get(c2['irec']), itask2)
    db.session.commit()
    nc2 = M.NonconformityRecord.query.filter_by(record_id=c2['irec']).first()
    src = M.ProductionRecord.query.get(c2['rec'])
    nc2.status = 'open'
    db.session.commit()
    mes_service.dispose_nonconformity(nc2, 'rework', rework_quantity=5,
                                      rework_process_id=src.process_id,
                                      employee_id=src.employee_id)
    db.session.commit()
    rework_task = M.TaskAssignment.query.get(nc2.rework_task_id)
    # 返工任务的「报工」：生产记录 global_sn == 任务 global_sn（routes.py:3399-3405 口径）
    rework_rec = M.ProductionRecord(employee_id=rework_task.employee_id,
                                    process_id=rework_task.process_id,
                                    quantity=rework_task.quantity, date=TODAY,
                                    global_sn=rework_task.global_sn, notes=None)
    # 正常记录（阴性对照：非返工）
    emp_n = M.Employee.query.first()
    proc_n = M.ProcessPrice.query.first()
    normal_task = M.TaskAssignment(employee_id=emp_n.id, process_id=proc_n.id,
                                   target_date=TODAY, quantity=3, status='completed')
    db.session.add(normal_task)
    db.session.flush()
    normal_rec = M.ProductionRecord(employee_id=emp_n.id, process_id=proc_n.id, quantity=3,
                                    date=TODAY, global_sn=normal_task.global_sn, notes=None)
    db.session.add_all([rework_rec, normal_rec])
    db.session.commit()

    records = [normal_rec, rework_rec]
    switch_off = set_switch(False)
    amount_off = mes_service.piecework_amount(records)
    brk_off = mes_service.piecework_breakdown(records)
    switch_on = set_switch(True)
    amount_on = mes_service.piecework_amount(records)
    brk_on = mes_service.piecework_breakdown(records)
    redis = mes_service.rework_production_record_ids(records)
    OUT['G_B5_01_02'] = {
        'nc_id': nc2.id,
        'rework_task': {'id': rework_task.id, 'quantity': rework_task.quantity,
                        'global_sn': rework_task.global_sn, 'notes': rework_task.notes},
        'nc_rework_task_id': nc2.rework_task_id,
        'rework_rec': {'id': rework_rec.id, 'global_sn': rework_rec.global_sn,
                       'quantity': rework_rec.quantity},
        'normal_rec': {'id': normal_rec.id, 'global_sn': normal_rec.global_sn,
                       'quantity': normal_rec.quantity},
        'R1R2_identified_rework_record_ids': sorted(redis),
        'price': proc_n.price,
        'switch_off_readback': switch_off, 'amount_off': jnum(amount_off),
        'switch_on_readback': switch_on, 'amount_on': jnum(amount_on),
        'delta': jnum(amount_on - amount_off),
        'breakdown_off': {'counted': jnum(brk_off[0]), 'dropped': jnum(brk_off[1])},
        'breakdown_on': {'counted': jnum(brk_on[0]), 'dropped': jnum(brk_on[1])},
    }
    set_switch(False)


# ------------------------------------------------------------------- D/E/F
with app.app_context():
    rms = c1['rms']
    nc = M.NonconformityRecord.query.filter_by(record_id=c1['irec']).first()
    nc.status = 'open'
    db.session.commit()
    src = M.ProductionRecord.query.get(c1['rec'])

    # D-1：显式件数
    mes_service.dispose_nonconformity(nc, 'rework', rework_quantity=7,
                                      rework_process_id=src.process_id,
                                      employee_id=src.employee_id)
    db.session.commit()
    t_explicit = M.TaskAssignment.query.get(nc.rework_task_id)
    d1 = {'quantity': t_explicit.quantity, 'notes': t_explicit.notes}
    # D-2：缺省 ⇒ 取来源生产记录 quantity(=5)
    nc.status = 'open'
    nc.rework_task_id = None
    db.session.commit()
    mes_service.dispose_nonconformity(nc, 'rework', rework_process_id=src.process_id,
                                      employee_id=src.employee_id)
    db.session.commit()
    t_default = M.TaskAssignment.query.get(nc.rework_task_id)
    d2 = {'quantity': t_default.quantity, 'notes': t_default.notes}
    OUT['D_B5_05'] = {'explicit_7': d1, 'default_from_record': d2,
                      'source_record_quantity': src.quantity}

    # C-2b：处置 done 后门禁恢复（阳性对照）
    bi = M.ProductionBatchItem.query.get(c1['bi'])
    allowed_after_rework, reason_after_rework = mes_service.qc_gate_allows_output(batch_item=bi)
    OUT['C_B4_02']['gate_after_rework_done'] = {
        'allowed': allowed_after_rework, 'reason': reason_after_rework,
        'quality_status': bi.quality_status, 'status': bi.status}

    # E/F：报废处置（显式 2 件 ⇒ 逐行 3×2 / 4×2）
    before_qty = {rm: jnum(M.RawMaterial.query.get(rm).quantity) for rm in rms}
    scrap_before = M.FinishedProduct.query.filter_by(stock_kind='scrap').count()
    nc.status = 'open'
    db.session.commit()
    mes_service.dispose_nonconformity(nc, 'scrap', scrap_quantity=2, scrap_cost=12.5)
    db.session.commit()
    after_qty = {rm: jnum(M.RawMaterial.query.get(rm).quantity) for rm in rms}
    scrap_after = M.FinishedProduct.query.filter_by(stock_kind='scrap').count()
    bi = M.ProductionBatchItem.query.get(c1['bi'])
    allowed_after_scrap, reason_after_scrap = mes_service.qc_gate_allows_output(batch_item=bi)
    OUT['E_B5_04'] = {
        'consumption_rows': [{'raw_material_id': rms[0], 'per_piece': 3.0},
                             {'raw_material_id': rms[1], 'per_piece': 4.0}],
        'scrap_quantity': 2, 'expect_delta': {rms[0]: -6.0, rms[1]: -8.0, rms[2]: 0.0},
        'before': before_qty, 'after': after_qty,
        'delta': {k: jnum(after_qty[k] - before_qty[k]) for k in after_qty},
        'nc_scrap_cost': nc.scrap_cost, 'nc_status': nc.status,
    }
    OUT['F_P9'] = {'scrap_ledger_rows_before': scrap_before,
                   'scrap_ledger_rows_after': scrap_after,
                   'scrap_rows_delta': scrap_after - scrap_before,
                   'bi_status_after_scrap': bi.status,
                   'gate_after_scrap': {'allowed': allowed_after_scrap,
                                        'reason': reason_after_scrap}}


# --------------------------------------------------------------------------- H
with app.app_context():
    ensure_role_users(app)
    client = app.test_client()
    login_as(client, '_t_admin')

    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(['工号', '姓名', '职位', '部门', '基本工资', '系数', '入职时间', '离职时间'])
    ws.append([f'{TAG}imp1', '好员工一', '操作工', '生产部', 3000, 1.0, '2026-01-01', None])
    ws.append([f'{TAG}imp2', '好员工二', '操作工', '生产部', 3000, 1.0, '2026-01-01', None])
    ws.append([f'{TAG}imp3', '好员工三', '操作工', '生产部', 3000, 1.0, '2026-01-01', None])
    ws.append([f'{TAG}imp4', '坏' * 60, '操作工', '生产部', 3000, 1.0, '2026-01-01', None])
    ws.append([f'{TAG}imp5', '坏员工五', '岗' * 60, '生产部', 3000, 1.0, '2026-01-01', None])
    good_bad = SRC / f'{TAG}good_bad.xlsx'
    wb.save(good_bad)

    before_emp = M.Employee.query.count()
    with open(good_bad, 'rb') as fh:
        resp = client.post('/employees/import',
                           data={'file': (fh, f'{TAG}good_bad.xlsx')},
                           content_type='multipart/form-data')
    body = resp.get_json(silent=True) or {}
    OUT['H_P3_P4_employees_import'] = {
        'status_code': resp.status_code,
        'success_field': body.get('success'),
        'message_head': (body.get('message') or '')[:120],
        'employee_delta': M.Employee.query.count() - before_emp,
        'residue_in_temp_folder': [p.name for p in UP.glob('*good_bad*')],
        'residue_exists': any(UP.glob('*good_bad*')),
    }

    # S4：解析失败路径（/tasks/import），非 xlsx 内容 + .xlsx 后缀
    bad = SRC / f'{TAG}broken.xlsx'
    bad.write_bytes(b'not an xlsx at all')
    before_task = M.TaskAssignment.query.count()
    with open(bad, 'rb') as fh:
        resp2 = client.post('/tasks/import',
                            data={'file': (fh, f'{TAG}broken.xlsx')},
                            content_type='multipart/form-data')
    OUT['H_P4_tasks_import'] = {
        'status_code': resp2.status_code,
        'body': resp2.get_json(silent=True),
        'task_delta': M.TaskAssignment.query.count() - before_task,
        'residue_exists': any(UP.glob('*broken*')),
        'residue_files': [p.name for p in UP.glob('*broken*')],
    }

# --------------------------------------------------------------------------- I
with app.app_context():
    client = app.test_client()
    login_as(client, '_t_admin')

    # I-1：P1 根因的**行为级**复现 —— 新建成品（routes.py:5149 add → :5152-5167 AuditLog 取 .id）
    before_ids = {r.id for r in M.AuditLog.query.all()}
    resp = client.post('/inventory/finished/add', json={
        'product_number_type': 'manual', 'product_number': f'{TAG}FP',
        'drawing_number': f'{TAG}DWG', 'model': f'{TAG}M',
        'production_date': '2026-10-08', 'inspector': f'{TAG}inspector'})
    new_logs = [r for r in M.AuditLog.query.all() if r.id not in before_ids]
    new_log = new_logs[-1] if new_logs else None
    i1 = {'status_code': resp.status_code, 'body': resp.get_json(silent=True),
          'audit_rows_added': len(new_logs)}
    if new_log is not None:
        i1.update({'log_id': new_log.id, 'action': new_log.action,
                   'target_model': new_log.target_model, 'target_id': new_log.target_id,
                   'can_rollback': new_log.can_rollback, 'rollback_type': new_log.rollback_type})
    OUT['I_P1_behavior'] = i1

    # I-2：P1 的下游后果 —— 对 target_id=NULL 的审计行发起回滚
    if new_log is not None:
        r2 = client.post(f'/audit_logs/rollback/{new_log.id}')
        OUT['I_P1_rollback_consequence'] = {
            'log_id': new_log.id, 'status_code': r2.status_code,
            'body': r2.get_json(silent=True)}

    # I-3：old_data=NULL 的 edit 行回滚（B7-05 的边界：应 400+原因，实测？）
    r3 = client.post('/audit_logs/rollback/70')
    OUT['I_B7_05_edit_null_old_data'] = {
        'log_id': 70, 'status_code': r3.status_code, 'body': r3.get_json(silent=True)}

    # I-4：delete 行回滚（old_data 完整，无子行）——对照：这条能成功
    r4 = client.post('/audit_logs/rollback/2')
    OUT['I_B7_04_delete_rollback'] = {
        'log_id': 2, 'status_code': r4.status_code, 'body': r4.get_json(silent=True)}

# --------------------------------------------------------------------------- J
# B4-02 结构复核：报工路径（routes.py:3711-3717）**不传** production_record ⇒ 门禁内部的
# record_ids 只能来自 notes 软关联；报工链不写 notes ⇒「有在办质检任务 / 未闭环 NC」两条路径
# 在报工路径上不命中，真正生效的是 quality_status / status 分支（即 B4-03 的回写）。
with app.app_context():
    c3 = build_report_chain(3)
    it = M.InspectionTask.query.get(c3['itask'])
    it.status = 'pending'                       # 报工刚创建质检任务时的真实形态
    db.session.commit()
    bi3 = M.ProductionBatchItem.query.get(c3['bi'])
    rec3 = M.ProductionRecord.query.get(c3['rec'])
    form_report_path = mes_service.qc_gate_allows_output(batch_item=bi3)          # = routes.py:3712 的形态
    form_with_record = mes_service.qc_gate_allows_output(batch_item=bi3, production_record=rec3)
    bi3.quality_status = 'fail'                 # = B4-03 回写之后的形态
    db.session.commit()
    after_writeback = mes_service.qc_gate_allows_output(batch_item=bi3)
    OUT['J_B4_02_structure'] = {
        'task_status': 'pending',
        'record_ids_via_notes_softlink':
            [r.id for r in mes_service.batch_item_production_records(bi3)],
        'gate_without_production_record_report_path': {
            'allowed': form_report_path[0], 'reason': form_report_path[1]},
        'gate_with_production_record_qc_domain': {
            'allowed': form_with_record[0], 'reason': form_with_record[1]},
        'gate_after_quality_status_fail': {
            'allowed': after_writeback[0], 'reason': after_writeback[1]},
    }

text = json.dumps(OUT, ensure_ascii=False, indent=2, default=str)
(pathlib.Path(__file__).with_suffix('.output.json')).write_text(text, encoding='utf-8')
print(text)

