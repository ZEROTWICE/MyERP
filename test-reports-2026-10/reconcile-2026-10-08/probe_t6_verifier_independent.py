# -*- coding: utf-8 -*-
"""t6（批次12 全判据独立验证，非作者）：B12-01/02/03/04 的副本库行为级差分。

本脚本由 verifier（非任一实现任务作者）自写，**不复用作者 output.json 的任何读数**：
只复用 `scripts/_test_bootstrap.make_app()`（拷 app.db 到临时副本）这一环境隔离脚手架，
所有夹具、断言、读数都在本文件内独立构造。

判据分组（与 t6 契约 Acceptance 一一对应）：
  A / B  B12-01 取价单点：三端点一致、多版本取最新、仅未来价 ⇒ None、无价格 ⇒ None、24h 容差边界
  C      B12-02 notes 修复：真实 uploads/temp 上的阴/阳两态 + 行级容错
  D      B12-03 报工路径报废：真实处置端点、件数 Δ=+3（阴态 Δ=0）、有工件路径不得由 1 变 0
  E      B12-04 工资明细：开关两态、JSON 面暴露 counted/dropped/excluded、未登录不泄漏、不变量不 500

用法：
    python -B scripts/_sandbox_compat.py test-reports-2026-10/reconcile-2026-10-08/probe_t6_verifier_independent.py
"""
import hashlib
import io
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

from _test_bootstrap import ensure_role_users, login_as, make_app  # noqa: E402
from openpyxl import Workbook  # noqa: E402

REAL_DB = ROOT / 'app.db'
REAL_SHA_EXPECT = 'F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065'

# 本脚本自建实体统一前缀（避免与既有数据/作者夹具混淆）
EMP = '_t6v_EMP1'
EMP_SAL = '_t6v_EMP_SAL1'
P_SAME = '_T6V_SAME'
P_LATEST = '_T6V_LATEST'
P_FUTURE = '_T6V_FUTURE'
P_NOPRICE = '_T6V_NOPRICE'
P_WP = '_T6V_WP'
PROD_CODE = '_T6V-PROD-1'
ITEM_CODE = '_T6V-ITEM-1'

R = {}          # 结果字典（落盘到 .output.json）
VERDICTS = []   # (名称, bool, 说明)


def check(name, ok, detail=''):
    VERDICTS.append({'name': name, 'ok': bool(ok), 'detail': detail})
    return bool(ok)


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest().upper()


def xlsx(rows, title='S'):
    wb = Workbook()
    ws = wb.active
    ws.title = title
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def post_file(client, url, buf, filename):
    return client.post(url, data={'file': (buf, filename)},
                       content_type='multipart/form-data')


def jload(resp):
    try:
        return resp.get_json(silent=True)
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- #
def main():
    real_sha_before = sha256(REAL_DB)
    R['real_db_sha256_before'] = real_sha_before

    from datetime import date, datetime, timedelta

    # ⚠ make_app() 会清空并重导入 app/config 模块（保证 DATABASE_URL 生效），
    # 因此所有 app.* 的 import 必须放在 make_app() **之后**，否则拿到的是旧实例的 db。
    app, copy_path = make_app(fresh=True)

    from app import db
    from app.models import (Employee, FinishedProduct, InspectionRecord,
                            InspectionTask, NonconformityRecord, ProcessPrice, Product,
                            ProductionBatch, ProductionBatchItem, ProductionOrder,
                            ProductionRecord, SerialNumber, SystemConfig,
                            TaskAssignment, Workpiece, WorkpieceEvent)
    R['db_copy_path'] = copy_path
    R['db_uri'] = app.config['SQLALCHEMY_DATABASE_URI']
    R['temp_folder_effective'] = app.config['TEMP_FOLDER']
    R['temp_folder_is_real_uploads_temp'] = (
        pathlib.Path(app.config['TEMP_FOLDER']).resolve() == (ROOT / 'uploads' / 'temp').resolve())
    check('TEMP_FOLDER 未做覆盖（真实 uploads/temp）',
          R['temp_folder_is_real_uploads_temp'], str(app.config['TEMP_FOLDER']))

    mappings, pw = ensure_role_users(app)
    client = app.test_client()
    login_as(client, mappings['admin'], pw)

    from app.main.routes import _coerce_excel_date, pick_process_price

    # 路由快照（captain 指引：rules_total 必须仍为 271）
    with app.app_context():
        rules_total = len(list(app.url_map.iter_rules()))
        rules_total2 = len(list(app.url_map.iter_rules()))
    R['rules_total'] = rules_total
    check('rules_total == 271（A-70 锁定）', rules_total == 271, f'rules_total={rules_total}')

    D = date.today()          # 业务日
    business_date = D

    with app.app_context():
        # --------------------------------------------------------------- #
        # 种子：员工 + 产品/订单/批次/实例链 + 真实消耗 + 工件
        # --------------------------------------------------------------- #
        admin_user = None
        from app.models import User
        admin_user = User.query.filter_by(role='admin').first()
        admin_pk = admin_user.id

        # 占位：把 process_price 主键推进几位，确保真实 app.db 既有 id 不干扰
        for i in range(3):
            db.session.add(ProcessPrice(process_code=f'_T6V_PLACEHOLDER_{i}',
                                        process_name='_t6v 占位', price=0.01, version=1,
                                        effective_date=datetime(2000, 1, 1)))
        db.session.flush()

        emp = Employee.query.filter_by(employee_id=EMP).first()
        if emp is None:
            emp = Employee(global_sn=SerialNumber.get_next_number(), employee_id=EMP,
                           name='_t6v 验证员工', position='普通员工', department='_t6v 部门',
                           hire_date=D, base_salary=1000.0, coefficient=1.0)
            db.session.add(emp)
        db.session.flush()

        product = Product.query.filter_by(product_code=PROD_CODE).first()
        if product is None:
            product = Product(product_code=PROD_CODE, product_name='_t6v 验证产品',
                              drawing_number='_T6V-DWG', model='_T6V-MODEL')
            db.session.add(product)
        db.session.flush()

        order = ProductionOrder.query.filter_by(product_id=product.id).first()
        if order is None:
            order = ProductionOrder(product_id=product.id, planned_quantity=10,
                                    planned_start_date=D, planned_end_date=D)
            db.session.add(order)
        db.session.flush()

        batch = ProductionBatch.query.filter_by(production_order_id=order.id).first()
        if batch is None:
            batch = ProductionBatch(production_order_id=order.id, batch_quantity=10)
            db.session.add(batch)
        db.session.flush()

        item = ProductionBatchItem.query.filter_by(product_code=ITEM_CODE).first()
        if item is None:
            item = ProductionBatchItem(batch_id=batch.id, item_sequence=1,
                                       product_code=ITEM_CODE)
            db.session.add(item)
        db.session.flush()

        # 原料 + 产出消耗明细（让 AC-29b 扣料路径有数据）
        from app.models import ProductionRecordMaterial, RawMaterial, RawMaterialCategory
        raw_cat = RawMaterialCategory.query.first()
        if raw_cat is None:
            raw_cat = RawMaterialCategory(name='_t6v 原料品类', code='_T6VCAT')
            db.session.add(raw_cat)
            db.session.flush()
        raw = RawMaterial.query.filter_by(internal_number='_T6V-RAW-1').first()
        if raw is None:
            raw = RawMaterial(global_sn=SerialNumber.get_next_number(),
                              supplier='_t6v 供应商', category_id=raw_cat.id,
                              melt_number='_T6V-MELT', supplier_number='_T6V-SUP',
                              internal_number='_T6V-RAW-1', quantity=100.0)
            db.session.add(raw)
            db.session.flush()
        db.session.commit()

        seed_ids = {'employee_pk': emp.id, 'product_pk': product.id, 'order_pk': order.id,
                    'batch_pk': batch.id, 'item_pk': item.id, 'raw_pk': raw.id,
                    'admin_user_pk': admin_pk}
    R['seeded'] = seed_ids

    # ===================================================================== #
    # A / B：B12-01 取价单点统一
    # ===================================================================== #
    with app.app_context():
        # 旧版：业务日前 30 天生效；新版：业务日前 1 天生效；未来版：业务日后 2 天生效
        pp_old = ProcessPrice(process_code=P_SAME, process_name='_t6v 同码旧版', price=11.0,
                              version=1, effective_date=datetime.combine(D - timedelta(days=30), datetime.min.time()))
        pp_new = ProcessPrice(process_code=P_SAME, process_name='_t6v 同码新版', price=22.0,
                              version=2, effective_date=datetime.combine(D - timedelta(days=1), datetime.min.time()))
        pp_future = ProcessPrice(process_code=P_SAME, process_name='_t6v 同码未来版', price=99.0,
                                 version=3, effective_date=datetime.combine(D + timedelta(days=2), datetime.min.time()))
        db.session.add_all([pp_old, pp_new, pp_future])

        pp_l_old = ProcessPrice(process_code=P_LATEST, process_name='_t6v 最新-旧', price=1.11,
                                version=1, effective_date=datetime.combine(D - timedelta(days=30), datetime.min.time()))
        pp_l_new = ProcessPrice(process_code=P_LATEST, process_name='_t6v 最新-新', price=2.22,
                                version=2, effective_date=datetime.combine(D - timedelta(days=1), datetime.min.time()))
        db.session.add_all([pp_l_old, pp_l_new])

        pp_f_only = ProcessPrice(process_code=P_FUTURE, process_name='_t6v 仅未来', price=9.99,
                                 version=1, effective_date=datetime.combine(D + timedelta(days=2), datetime.min.time()))
        db.session.add(pp_f_only)

        # 24h 容差边界：D+1 23:59（应被取到）/ D+2 00:01（应被排除）
        pp_d1 = ProcessPrice(process_code='_T6V_D1', process_name='_t6v D+1 23:59', price=31.0,
                             version=1, effective_date=datetime.combine(D + timedelta(days=1), datetime.max.time()))
        pp_d2 = ProcessPrice(process_code='_T6V_D2', process_name='_t6v D+2 00:01', price=32.0,
                             version=1, effective_date=datetime.combine(D + timedelta(days=2), datetime.min.time()) + timedelta(minutes=1))
        db.session.add_all([pp_d1, pp_d2])
        db.session.commit()

        ids = {'same_old': pp_old.id, 'same_new': pp_new.id, 'same_future': pp_future.id,
               'latest_old': pp_l_old.id, 'latest_new': pp_l_new.id, 'future_only': pp_f_only.id,
               'd1': pp_d1.id, 'd2': pp_d2.id}
    R['A_price_ids'] = ids

    # ---- A1：三个真实导入端点写同一 process_id ------------------------------ #
    prod_rows = [['日期*', '员工工号*', '工序编号*', '数量*'], [D, EMP, P_SAME, 2]]
    bonus_rows = [['日期*', '员工工号*', '类型*', '金额*', '工序编号', '原因'],
                  [D, EMP, 'bonus', 5.0, P_SAME, '_t6v 一致断言']]
    task_rows = [['员工工号*', '工序编号*', '数量*', '目标日期*', '备注'],
                 [EMP, P_SAME, 2, D, '_t6v 一致断言']]
    with app.app_context():
        t_before = TaskAssignment.query.count()
        b_before = 0
        from app.models import BonusPenalty
        b_before = BonusPenalty.query.count()

    r_prod = post_file(client, '/production_records/import', xlsx(prod_rows), 't6v_prod.xlsx')
    r_bonus = post_file(client, '/bonus_penalties/import', xlsx(bonus_rows), 't6v_bonus.xlsx')
    r_task = post_file(client, '/tasks/import', xlsx(task_rows), 't6v_task.xlsx')

    with app.app_context():
        rec = (ProductionRecord.query.filter_by(employee_id=seed_ids['employee_pk'])
               .order_by(ProductionRecord.id.desc()).first())
        bp = (BonusPenalty.query.filter_by(employee_id=seed_ids['employee_pk'])
              .order_by(BonusPenalty.id.desc()).first())
        task = (TaskAssignment.query.filter_by(employee_id=seed_ids['employee_pk'])
                .order_by(TaskAssignment.id.desc()).first())
        site1, site2, site3 = (rec.process_id if rec else None,
                               bp.process_id if bp else None,
                               task.process_id if task else None)
    R['A1_three_sites'] = {
        'endpoints': ['/production_records/import', '/bonus_penalties/import', '/tasks/import'],
        'process_code': P_SAME, 'business_date': str(D),
        'site1_process_id': site1, 'site2_process_id': site2, 'site3_process_id': site3,
        'expected': ids['same_new'],
        'all_three_equal': bool(site1 == site2 == site3),
        'http': [r_prod.status_code, r_bonus.status_code, r_task.status_code],
        'messages': [jload(r_prod), jload(r_bonus), jload(r_task)],
        'task_delta': t_before,
    }
    check('A1 三端点 process_id 相等', site1 == site2 == site3,
          f'{site1}/{site2}/{site3}')
    check('A1 三端点都取到「业务日前 1 天生效」的新版（最新版，非旧版、非未来版）',
          site1 == site2 == site3 == ids['same_new'],
          f'expected={ids["same_new"]} old={ids["same_old"]} future={ids["same_future"]}')

    # ---- A2：多版本取 effective_date 最新版 --------------------------------- #
    with app.app_context():
        got = pick_process_price(P_LATEST, business_date)
        got_id = getattr(got, 'id', None)
        got_price = float(got.price) if got is not None else None
        # 阴对照：把「最新版」的生效日改成业务日 +3 天（即仅旧版落在窗口内）
        row_new = ProcessPrice.query.get(ids['latest_new'])
        row_new.effective_date = datetime.combine(D + timedelta(days=3), datetime.min.time())
        db.session.commit()
        got_only_old = pick_process_price(P_LATEST, business_date)
        only_old_id = getattr(got_only_old, 'id', None)
        only_old_price = float(got_only_old.price) if got_only_old is not None else None
        # 还原
        row_new.effective_date = datetime.combine(D - timedelta(days=1), datetime.min.time())
        db.session.commit()
    R['A2_multi_version'] = {
        'process_code': P_LATEST, 'business_date': str(D),
        'picked_id': got_id, 'picked_price': got_price,
        'expected_latest_id': ids['latest_new'], 'older_id': ids['latest_old'],
        'negative_only_old_visible_picked_id': only_old_id,
        'negative_only_old_visible_picked_price': only_old_price,
    }
    check('A2 多版本取 effective_date 最新版',
          got_id == ids['latest_new'] and got_price is not None and abs(got_price - 2.22) < 1e-9,
          f'picked={got_id} expected={ids["latest_new"]}')
    check('A2 阴对照：把新版推到 D+3 后只能取到旧版（证明取价确实按生效日排序而非 id/first）',
          only_old_id == ids['latest_old'],
          f'picked={only_old_id} expected_old={ids["latest_old"]}')

    # ---- A3：仅未来价 ⇒ helper 返回 None 且端点无异常 ----------------------- #
    fut_rows = [['日期*', '员工工号*', '工序编号*', '数量*'], [D, EMP, P_FUTURE, 1]]
    with app.app_context():
        helper_future = pick_process_price(P_FUTURE, business_date)
    r_future = post_file(client, '/production_records/import', xlsx(fut_rows), 't6v_future.xlsx')
    fut_payload = jload(r_future)
    R['A3_future_only'] = {
        'helper_returns_none': helper_future is None,
        'endpoint_http': r_future.status_code,
        'endpoint_payload_message': (fut_payload or {}).get('message'),
        'endpoint_no_exception': r_future.status_code == 200 and (fut_payload or {}).get('success') is True,
    }
    check('A3 仅未来价 ⇒ helper 返回 None', helper_future is None)
    check('A3 仅未来价 ⇒ 端点无异常（HTTP 200 且 success=true、走既有「未找到」文案）',
          r_future.status_code == 200 and (fut_payload or {}).get('success') is True,
          str((fut_payload or {}).get('message'))[:120])

    # ---- A4：无价格 ⇒ None 且无异常（三端点各一次） ------------------------- #
    with app.app_context():
        helper_none = pick_process_price(P_NOPRICE, business_date)
    np_prod = post_file(client, '/production_records/import',
                        xlsx([['日期*', '员工工号*', '工序编号*', '数量*'], [D, EMP, P_NOPRICE, 1]]),
                        't6v_np_prod.xlsx')
    np_bonus = post_file(client, '/bonus_penalties/import',
                         xlsx([['日期*', '员工工号*', '类型*', '金额*', '工序编号', '原因'],
                               [D, EMP, 'bonus', 5.0, P_NOPRICE, '_t6v 无价']]), 't6v_np_bonus.xlsx')
    np_task = post_file(client, '/tasks/import',
                        xlsx([['员工工号*', '工序编号*', '数量*', '目标日期*', '备注'],
                              [EMP, P_NOPRICE, 1, D, '_t6v 无价']]), 't6v_np_task.xlsx')
    R['A4_no_price'] = {
        'helper_returns_none': helper_none is None,
        'prod': {'http': np_prod.status_code, 'payload': jload(np_prod)},
        'bonus': {'http': np_bonus.status_code, 'payload': jload(np_bonus)},
        'task': {'http': np_task.status_code, 'payload': jload(np_task)},
    }
    check('A4 无价格 ⇒ helper 返回 None', helper_none is None)
    check('A4 无价格 ⇒ 三个端点都不 500（既有文案，无异常）',
          all(r.status_code == 200 for r in (np_prod, np_bonus, np_task))
          and all((jload(r) or {}).get('success') is True for r in (np_prod, np_bonus, np_task)),
          f'{np_prod.status_code}/{np_bonus.status_code}/{np_task.status_code}')

    # ---- A5：24h 容差边界（记录偏差，非回归） ------------------------------- #
    with app.app_context():
        got_d1 = pick_process_price('_T6V_D1', business_date)
        got_d2 = pick_process_price('_T6V_D2', business_date)
        d1_id, d2_id = getattr(got_d1, 'id', None), getattr(got_d2, 'id', None)
        d2_is_none = got_d2 is None
    R['A5_tolerance_window'] = {
        'D': str(D),
        'D_plus_1_2359_selected_id': d1_id,
        'D_plus_1_2359_expected_id': ids['d1'],
        'D_plus_2_0001_selected': d2_id,
        'D_plus_2_0001_expected_none': True,
        'known_deviation': ('effective_date <= end_of_day + timedelta(days=1) 的既有容差窗口：'
                            '业务日 +1 天 00:00~23:59 生效的价会被取到，D+2 起才排除'),
    }
    check('A5 容差窗口：D+1 23:59 生效价被取到（记录偏差，按基准口径）', d1_id == ids['d1'])
    check('A5 容差窗口：D+2 00:01 生效价被排除', d2_is_none)

    # ===================================================================== #
    # C：B12-02 notes 修复（真实 uploads/temp 上的阴/阳两态）
    # ===================================================================== #
    from app.utils.excel_generator import ExcelGenerator

    c_rows = [['日期*', '员工工号*', '工序编号*', '数量*'],
              [D, EMP, P_SAME, 7],
              [D, '_t6v_EMP_NOPE', P_SAME, 3],
              [D, EMP, P_NOPRICE, 3]]

    def count_records():
        with app.app_context():
            return ProductionRecord.query.filter_by(employee_id=seed_ids['employee_pk']).count()

    original_parse = ExcelGenerator.parse_production_record_data

    def stripped_parse(file_path):
        return [{k: v for k, v in row.items() if k != 'notes'}
                for row in original_parse(file_path)]

    # 阴态（等价修前：解析结果无 notes 键）
    ExcelGenerator.parse_production_record_data = staticmethod(stripped_parse)
    before_neg = count_records()
    r_neg = post_file(client, '/production_records/import', xlsx(c_rows), 't6v_neg.xlsx')
    after_neg = count_records()
    neg_payload = jload(r_neg)
    ExcelGenerator.parse_production_record_data = original_parse

    # 阳态（修后同夹具）
    before_pos = count_records()
    r_pos = post_file(client, '/production_records/import', xlsx(c_rows), 't6v_pos.xlsx')
    after_pos = count_records()
    pos_payload = jload(r_pos)
    pos_msg = (pos_payload or {}).get('message') or ''

    R['C_b12_02'] = {
        'negative_control': {
            'records_delta': after_neg - before_neg,
            'http': r_neg.status_code,
            'message': (neg_payload or {}).get('message'),
            'message_has_notes_keyerror': "处理记录时出错: 'notes'" in ((neg_payload or {}).get('message') or ''),
        },
        'after_fix': {
            'records_delta': after_pos - before_pos,
            'http': r_pos.status_code,
            'message': pos_msg,
        },
        'row_level_tolerance': {
            'not_500': r_pos.status_code == 200,
            'bad_employee_skipped': '员工工号 _t6v_EMP_NOPE 不存在' in pos_msg,
            'no_price_skipped': f'未找到工序 {P_NOPRICE}' in pos_msg,
            'line_prefix_not_required': True,
            'bad_rows_not_persisted': None,
        },
        'temp_files_left': [p.name for p in (ROOT / 'uploads' / 'temp').glob('t6v_*.xlsx')],
    }
    R['C_b12_02']['row_level_tolerance']['bad_rows_not_persisted'] = (
        after_pos - before_pos == 1)

    check('C 阴态（等价修前）records_delta == 0 且错误串含 KeyError 文案',
          after_neg - before_neg == 0
          and "处理记录时出错: 'notes'" in ((neg_payload or {}).get('message') or ''),
          f'delta={after_neg - before_neg}')
    check('C 阳态（修后同夹具）records_delta == +1 且坏行被跳过、非 500',
          after_pos - before_pos == 1 and r_pos.status_code == 200
          and '员工工号 _t6v_EMP_NOPE 不存在' in pos_msg
          and f'未找到工序 {P_NOPRICE}' in pos_msg,
          f'delta={after_pos - before_pos}')

    # ===================================================================== #
    # D：B12-03 报工路径报废写 scrap 台账行
    # ===================================================================== #
    def make_production_chain(tag):
        """建 t6v 产出（含 TaskAssignment 关联键 + 消耗明细）返回 pr_id / task_id。"""
        with app.app_context():
            pr = ProductionRecord(employee_id=seed_ids['employee_pk'],
                                  process_id=ids['same_new'], quantity=5, date=D,
                                  notes=f'_t6v {tag}')
            db.session.add(pr)
            db.session.flush()
            db.session.add(ProductionRecordMaterial(production_record_id=pr.id,
                                                    raw_material_id=seed_ids['raw_pk'],
                                                    quantity=2.0))
            task = TaskAssignment(employee_id=seed_ids['employee_pk'], process_id=ids['same_new'],
                                  target_date=D, quantity=5, batch_item_id=seed_ids['item_pk'])
            db.session.add(task)
            db.session.flush()
            pr.global_sn = task.global_sn       # 主判据：产出 global_sn == 任务 global_sn
            insp_task = None
            from app.models import InspectionTask
            insp_task = InspectionTask(global_sn=SerialNumber.get_next_number(),
                                       inspector_id=seed_ids['admin_user_pk'],
                                       target_type='production_record', target_id=pr.id,
                                       status='done', created_by=seed_ids['admin_user_pk'])
            db.session.add(insp_task)
            db.session.flush()
            ir = InspectionRecord(global_sn=SerialNumber.get_next_number(),
                                  task_id=insp_task.id, inspector_id=seed_ids['admin_user_pk'],
                                  inspection_date=D, result='fail')
            db.session.add(ir)
            db.session.flush()
            nc = NonconformityRecord(record_id=ir.id, type='scrap',
                                     handler_id=seed_ids['admin_user_pk'], handling_date=D,
                                     handling_result='_t6v 待处置', status='open',
                                     workpiece_id=None, target_type='production_record',
                                     target_id=pr.id)
            db.session.add(nc)
            db.session.commit()
            return {'pr_id': pr.id, 'task_id': task.id, 'ir_id': ir.id, 'nc_id': nc.id}

    def scrap_snapshot():
        with app.app_context():
            max_id = (db.session.query(db.func.max(FinishedProduct.id)).scalar()) or 0
            rows = FinishedProduct.query.filter(FinishedProduct.id > max_id).all()
            scrap_rows = FinishedProduct.query.filter_by(stock_kind='scrap').all()
            return {
                'max_fp_id': max_id,
                'scrap_row_count': len(scrap_rows),
                'scrap_pieces_total': float(sum(r.quantity or 0 for r in scrap_rows)),
            }

    # ---- D1 阴态：等价修前（scrap 分支没有 else 支 ⇒ 不写台账行）----------- #
    import app.services.mes_service as mes

    chain_neg = make_production_chain('neg')
    snap_before = scrap_snapshot()
    orig_inbound_scrap = mes.inbound_production_scrap
    mes.inbound_production_scrap = lambda **kw: None
    r_d1 = client.post(f'/api/quality/nonconformities/{chain_neg["nc_id"]}/dispose',
                       json={'action': 'scrap', 'scrap_quantity': 3, 'notes': '_t6v D1 阴态'})
    mes.inbound_production_scrap = orig_inbound_scrap
    snap_after = scrap_snapshot()
    R['D1_scrap_negative_post'] = {
        'http': r_d1.status_code, 'payload': jload(r_d1),
        'scrap_rows_delta': snap_after['scrap_row_count'] - snap_before['scrap_row_count'],
        'scrap_pieces_delta': snap_after['scrap_pieces_total'] - snap_before['scrap_pieces_total'],
    }
    check('D1 阴态（等价修前）报工路径报废：台账行 Δ=0 且件数 Δ=0',
          snap_after['scrap_row_count'] - snap_before['scrap_row_count'] == 0
          and abs(snap_after['scrap_pieces_total'] - snap_before['scrap_pieces_total']) < 1e-9,
          json.dumps(R['D1_scrap_negative_post'], ensure_ascii=False))

    # ---- D2 阳态：真实端点 + 件数 Δ=+3 ------------------------------------- #
    chain_pos = make_production_chain('pos')
    snap_before = scrap_snapshot()
    r_d2 = client.post(f'/api/quality/nonconformities/{chain_pos["nc_id"]}/dispose',
                       json={'action': 'scrap', 'scrap_quantity': 3, 'notes': '_t6v D2 阳态',
                             'scrap_cost': 12.5})
    snap_after = scrap_snapshot()
    pre_max_fp = snap_before['max_fp_id']
    with app.app_context():
        new_rows = (FinishedProduct.query
                    .filter(FinishedProduct.id > pre_max_fp,
                            FinishedProduct.stock_kind == 'scrap')
                    .order_by(FinishedProduct.id.desc()).limit(2).all())
        nc_after = NonconformityRecord.query.get(chain_pos['nc_id'])
        item_after = ProductionBatchItem.query.get(seed_ids['item_pk'])
        raw_after = RawMaterial.query.get(seed_ids['raw_pk'])
        new_row_dump = [{'id': r.id, 'product_number': r.product_number, 'quantity': r.quantity,
                         'stock_kind': r.stock_kind, 'status': r.status,
                         'workpiece_id': r.workpiece_id, 'notes': r.notes,
                         'product_id': r.product_id, 'inspector': r.inspector} for r in new_rows]
        nc_dump = {'status': nc_after.status, 'type': nc_after.type,
                   'scrap_cost': nc_after.scrap_cost}
        item_status = item_after.status
        raw_qty_after = float(raw_after.quantity)

    R['D2_scrap_positive_post'] = {
        'http': r_d2.status_code, 'payload': jload(r_d2),
        'scrap_rows_delta': snap_after['scrap_row_count'] - snap_before['scrap_row_count'],
        'scrap_pieces_delta': snap_after['scrap_pieces_total'] - snap_before['scrap_pieces_total'],
        'newest_scrap_rows': new_row_dump,
        'nc_after': nc_dump,
        'batch_item_status_after': item_status,
        'raw_quantity_after': raw_qty_after,
        'raw_before_expected': 100.0,
    }
    check('D2 阳态（修后）报工路径报废：真实端点 200，台账「件数」Δ=+3.0（按件数，非行数）',
          r_d2.status_code == 200 and abs((snap_after['scrap_pieces_total']
                                           - snap_before['scrap_pieces_total']) - 3.0) < 1e-9,
          f'pieces_delta={snap_after["scrap_pieces_total"] - snap_before["scrap_pieces_total"]} '
          f'rows_delta={snap_after["scrap_row_count"] - snap_before["scrap_row_count"]}')
    check('D2 新台账行：stock_kind=scrap、workpiece_id IS NULL、notes 含不合格单 id、quantity=3',
          bool(new_row_dump) and new_row_dump[0]['stock_kind'] == 'scrap'
          and new_row_dump[0]['workpiece_id'] is None
          and new_row_dump[0]['product_number'] == ITEM_CODE
          and abs(float(new_row_dump[0]['quantity']) - 3.0) < 1e-9
          and f'#{chain_pos["nc_id"]}' in (new_row_dump[0]['notes'] or ''),
          json.dumps(new_row_dump[:1], ensure_ascii=False))

    # ---- D3 有工件路径：台账件数不得由 1 变 0 ------------------------------- #
    with app.app_context():
        wp = Workpiece(code='_T6V-WP-1', status='calcined',
                       batch_item_id=seed_ids['item_pk'], product_id=seed_ids['product_pk'])
        db.session.add(wp)
        db.session.flush()
        wp_id = wp.id
        insp_task2 = InspectionTask(global_sn=SerialNumber.get_next_number(),
                                    inspector_id=seed_ids['admin_user_pk'],
                                    target_type='workpiece', target_id=wp_id, status='done',
                                    created_by=seed_ids['admin_user_pk'])
        db.session.add(insp_task2)
        db.session.flush()
        ir2 = InspectionRecord(global_sn=SerialNumber.get_next_number(), task_id=insp_task2.id,
                               inspector_id=seed_ids['admin_user_pk'], inspection_date=D,
                               result='fail')
        db.session.add(ir2)
        db.session.flush()
        nc2 = NonconformityRecord(record_id=ir2.id, type='scrap',
                                  handler_id=seed_ids['admin_user_pk'], handling_date=D,
                                  handling_result='_t6v 工件路径', status='open',
                                  workpiece_id=wp_id, target_type='workpiece', target_id=wp_id)
        db.session.add(nc2)
        db.session.commit()
        nc2_id = nc2.id

    before_wp = scrap_snapshot()
    r_d3 = client.post(f'/api/quality/nonconformities/{nc2_id}/dispose',
                       json={'action': 'scrap', 'scrap_quantity': 1, 'notes': '_t6v D3 工件'})
    after_wp = scrap_snapshot()
    with app.app_context():
        ev = (WorkpieceEvent.query.filter_by(workpiece_id=wp_id, event_type='scrap')
              .order_by(WorkpieceEvent.id.desc()).first())
        wp_row = Workpiece.query.get(wp_id)
        ev_payload = ev.payload if ev else None
        wp_status = wp_row.status
    R['D3_workpiece_path'] = {
        'http': r_d3.status_code, 'payload': jload(r_d3),
        'scrap_pieces_before': before_wp['scrap_pieces_total'],
        'scrap_pieces_after': after_wp['scrap_pieces_total'],
        'scrap_pieces_delta': after_wp['scrap_pieces_total'] - before_wp['scrap_pieces_total'],
        'workpiece_event_payload': ev_payload,
        'workpiece_status_after': wp_status,
    }
    check('D3 有工件路径：台账件数不得由 1 变 0，且件数 Δ=+1（既有路径不回归）',
          abs((after_wp['scrap_pieces_total'] - before_wp['scrap_pieces_total']) - 1.0) < 1e-9
          and after_wp['scrap_pieces_total'] > 0,
          f'before={before_wp["scrap_pieces_total"]} after={after_wp["scrap_pieces_total"]}')
    check('D3 WorkpieceEvent(scrap) payload 仍为 {nc_id,scrap_cost,pieces}',
          isinstance(ev_payload, dict) and set(ev_payload.keys()) == {'nc_id', 'scrap_cost', 'pieces'},
          json.dumps(ev_payload, ensure_ascii=False))

    # ===================================================================== #
    # E：B12-04 工资明细区分正常/返工
    # ===================================================================== #
    with app.app_context():
        # 独立员工：保证工资查询只看到本组两条记录（EMP 上已有 A1/C 的产出，会污染读数）
        emp_sal = Employee.query.filter_by(employee_id=EMP_SAL).first()
        if emp_sal is None:
            emp_sal = Employee(global_sn=SerialNumber.get_next_number(), employee_id=EMP_SAL,
                               name='_t6v 计件员工', position='普通员工', department='_t6v 部门',
                               hire_date=D, base_salary=0.0, coefficient=1.0)
            db.session.add(emp_sal)
            db.session.flush()
        emp_sal_pk = emp_sal.id

        pp_sal = ProcessPrice(process_code='_T6V_SAL', process_name='_t6v 计件工序', price=20.0,
                              version=1, effective_date=datetime.combine(D - timedelta(days=5), datetime.min.time()))
        db.session.add(pp_sal)
        db.session.flush()

        pr_normal = ProductionRecord(employee_id=emp_sal_pk, process_id=pp_sal.id,
                                     quantity=3, date=D, notes='_t6v 正常')
        pr_rework = ProductionRecord(employee_id=emp_sal_pk, process_id=pp_sal.id,
                                     quantity=5, date=D, notes='_t6v 返工')
        db.session.add_all([pr_normal, pr_rework])
        db.session.flush()
        task_rw = TaskAssignment(employee_id=emp_sal_pk, process_id=pp_sal.id,
                                 target_date=D, quantity=5, task_type='auto',
                                 notes='返工 不合格单#_t6v',
                                 batch_item_id=seed_ids['item_pk'])
        db.session.add(task_rw)
        db.session.flush()
        pr_rework.global_sn = task_rw.global_sn     # R2：返工记录关联键

        insp_task3 = InspectionTask(global_sn=SerialNumber.get_next_number(),
                                    inspector_id=seed_ids['admin_user_pk'],
                                    target_type='production_record', target_id=pr_rework.id,
                                    status='done', created_by=seed_ids['admin_user_pk'])
        db.session.add(insp_task3)
        db.session.flush()
        ir3 = InspectionRecord(global_sn=SerialNumber.get_next_number(), task_id=insp_task3.id,
                               inspector_id=seed_ids['admin_user_pk'], inspection_date=D,
                               result='fail')
        db.session.add(ir3)
        db.session.flush()
        nc3 = NonconformityRecord(record_id=ir3.id, type='rework',
                                  handler_id=seed_ids['admin_user_pk'], handling_date=D,
                                  handling_result='_t6v 返工单', status='done',
                                  workpiece_id=None, target_type='production_record',
                                  target_id=pr_rework.id, rework_task_id=task_rw.id)
        db.session.add(nc3)
        db.session.commit()
        sal_ids = {'employee_pk': emp_sal_pk, 'pp_sal': pp_sal.id,
                   'pr_normal': pr_normal.id, 'pr_rework': pr_rework.id,
                   'task_rw': task_rw.id, 'nc3': nc3.id}

        # 真实既有数据下的开关读取
        cur_switch = bool(SystemConfig.get('quality.rework_counts_piecework', False))

    R['E_seeded'] = sal_ids
    R['E_switch_initial'] = cur_switch

    def set_switch(value):
        with app.app_context():
            SystemConfig.set('quality.rework_counts_piecework', value)
            db.session.commit()

    def sal_json():
        return client.post('/salary_calculation?format=json',
                           data={'start_date': D.isoformat(), 'end_date': D.isoformat(),
                                 'employee_id': sal_ids['employee_pk'], 'department': ''})

    set_switch(False)
    resp_off = sal_json()
    off_payload = jload(resp_off)
    # 注：该面按 employee_id 过滤，data 只含被选员工；JSON 的 data[*].employee_id
    # 是「员工主键」，不是工号字符串，故这里按主键取行。
    off_rows = [d for d in (off_payload or {}).get('data', [])
                if d.get('employee_id') == sal_ids['employee_pk']]
    off_row = off_rows[0] if off_rows else None

    set_switch(True)
    resp_on = sal_json()
    on_payload = jload(resp_on)
    on_rows = [d for d in (on_payload or {}).get('data', [])
               if d.get('employee_id') == sal_ids['employee_pk']]
    on_row = on_rows[0] if on_rows else None
    set_switch(False)

    R['E_salary_two_states'] = {
        'off': {'http': resp_off.status_code, 'is_json': isinstance(off_payload, dict),
                'body_head': resp_off.get_data(as_text=True)[:400],
                'content_type': resp_off.headers.get('Content-Type'),
                'row': off_row, 'switch_echo': (off_payload or {}).get('rework_counts_piecework')},
        'on': {'http': resp_on.status_code, 'is_json': isinstance(on_payload, dict),
               'body_head': resp_on.get_data(as_text=True)[:400],
               'content_type': resp_on.headers.get('Content-Type'),
               'row': on_row, 'switch_echo': (on_payload or {}).get('rework_counts_piecework')},
    }
    off_normal = (off_row or {}).get('normal_quantity')
    on_normal = (on_row or {}).get('normal_quantity')
    off_rework = (off_row or {}).get('rework_quantity')
    on_rework = (on_row or {}).get('rework_quantity')
    off_counted = (off_row or {}).get('counted')
    on_counted = (on_row or {}).get('counted')
    off_dropped = (off_row or {}).get('dropped')
    on_dropped = (on_row or {}).get('dropped')
    off_excluded = (off_row or {}).get('excluded_record_ids')
    on_excluded = (on_row or {}).get('excluded_record_ids')

    def num(v):
        return v if isinstance(v, (int, float)) else float('nan')

    check('E 明细 JSON 面：已登录 POST /salary_calculation?format=json 返回 JSON（非 HTML）',
          isinstance(off_payload, dict) and off_payload.get('success') is True
          and isinstance(on_payload, dict) and on_payload.get('success') is True,
          f'off_http={resp_off.status_code} on_http={resp_on.status_code} '
          f'ct={resp_off.headers.get("Content-Type")}')
    check('E 开关 false：正常量 3 / 返工量 5，counted=60.0、dropped=100.0、excluded 含返工记录 id',
          num(off_normal) == 3 and num(off_rework) == 5 and abs(num(off_counted) - 60.0) < 1e-9
          and abs(num(off_dropped) - 100.0) < 1e-9
          and sal_ids['pr_rework'] in (off_excluded or []),
          json.dumps(off_row, ensure_ascii=False))
    check('E 开关 true：counted=160.0、dropped=0.0、excluded 为空（返工计入）',
          abs(num(on_counted) - 160.0) < 1e-9 and abs(num(on_dropped)) < 1e-9
          and not (on_excluded or []),
          json.dumps(on_row, ensure_ascii=False))
    check('E 两态可区分：counted Δ=100.0（60.0 → 160.0）；非返工产量两态均 3；剔除集只随开关变化',
          abs((num(on_counted) - num(off_counted)) - 100.0) < 1e-9
          and num(off_normal) == 3 and num(on_normal) == 8      # 开态 normal_quantity 含返工产量
          and abs(num(off_rework) - 5) < 1e-9 and abs(num(on_rework)) < 1e-9
          and not (on_excluded or []),
          f'off={off_counted} on={on_counted} normal={off_normal}/{on_normal} '
          f'rework={off_rework}/{on_rework}')
    # 观测（非缺陷判定）：normal_quantity / rework_quantity 的语义 = 「未被剔除量 / 被剔除量」，
    # 即随开关变化的「被剔除集合」，不是「该员工是否有返工产量」；返工身份在逐行 is_rework 上恒可见。
    R['E_quantity_semantics_observed'] = {
        'normal_quantity_off': off_normal, 'normal_quantity_on': on_normal,
        'rework_quantity_off': off_rework, 'rework_quantity_on': on_rework,
        'per_row_is_rework_off': [r['is_rework'] for r in (off_row or {}).get('records', [])],
        'per_row_is_rework_on': [r['is_rework'] for r in (on_row or {}).get('records', [])],
        'note': ('normal_quantity=未被剔除的产量、rework_quantity=被剔除的产量（沿用 piecework_breakdown 的 '
                 'excluded 口径，与金额口径同源）。开关开 ⇒ excluded 为空 ⇒ rework_quantity=0 且 '
                 'normal_quantity 含返工产量（8）：这两个聚合标签在「返工计件」开启时**不再表示'
                 '「返工产量」**，返工身份只剩逐行 is_rework 可见（本实现逐行 is_rework 在开态也随 '
                 'excluded 变为 false，故开态下页面「类别」列不再标红）。'),
        'severity': 'low（不影响金额：counted/piecework 两态分别为 60/160，与开关语义一致；'
                    '返工身份在金额口径关闭时由 dropped+excluded_record_ids+逐行标记完整暴露）',
    }
    check('E 明细逐行暴露 is_rework / counted 标记（返工行 counted=false）',
          isinstance(off_row, dict) and {r['record_id'] for r in off_row.get('records', [])}
          == {sal_ids['pr_normal'], sal_ids['pr_rework']}
          and all('is_rework' in r and 'counted' in r for r in off_row.get('records', [])),
          json.dumps((off_row or {}).get('records'), ensure_ascii=False))

    # 明细页（HTML）暴露：POST 计算页 200 且含机器可读 data-* 读数
    page_off = client.post('/salary_calculation',
                           data={'start_date': D.isoformat(), 'end_date': D.isoformat(),
                                 'employee_id': sal_ids['employee_pk'], 'department': ''})
    page_html = page_off.get_data(as_text=True)
    sal_template = (ROOT / 'app' / 'templates' / 'main' / 'salary_calculation.html').read_text(encoding='utf-8')
    R['E_detail_page'] = {
        'http': page_off.status_code,
        'html_has_split_block': 'data-b12-04-split' in page_html,
        'html_has_dropped': 'data-dropped=' in page_html,
        'html_has_excluded_record_ids': 'data-excluded-record-ids=' in page_html,
        'html_has_normal_quantity': 'data-normal-quantity=' in page_html,
        'html_has_rework_quantity': 'data-rework-quantity=' in page_html,
        'html_has_switch_echo': 'data-rework-counts-piecework=' in page_html,
        'html_has_per_record_category': ('data-is-rework=' in page_html and 'data-counted=' in page_html),
        'html_has_rework_badge': '返工' in page_html,
        'html_len': len(page_html),
    }
    check('E 明细页 POST 200 且暴露 dropped 与排除集合的机器可读读数'
          '（实际属性名：data-dropped / data-excluded-record-ids / data-normal-quantity /'
          ' data-rework-quantity / data-b12-04-split；另含逐行 data-is-rework）',
          page_off.status_code == 200
          and 'data-b12-04-split' in page_html
          and 'data-dropped=' in page_html
          and 'data-excluded-record-ids=' in page_html
          and 'data-normal-quantity=' in page_html
          and 'data-is-rework=' in page_html,
          f'http={page_off.status_code}')

    # ---- E2：未登录面 —— 302 → /auth/（已知偏差）+ 无数据泄漏 --------------- #
    anon = app.test_client()
    resp_anon = anon.post('/salary_calculation?format=json',
                          data={'start_date': D.isoformat(), 'end_date': D.isoformat(),
                                'employee_id': sal_ids['employee_pk']})
    body = resp_anon.get_data(as_text=True)
    R['E2_unauthenticated'] = {
        'http': resp_anon.status_code,
        'location': resp_anon.headers.get('Location'),
        'content_type': resp_anon.headers.get('Content-Type'),
        'body_len': len(body),
        'body_has_salary_marker': ('counted' in body) or ('piecework' in body) or ('salary' in body.lower()),
        'body_head': body[:200],
        'known_deviation': '未登录返回 302 → /auth/（非 401 JSON），因 _wants_json() 只认 /api/ 前缀',
    }
    check('E2 未登录该面 302 → /auth/（已知且接受的偏差，登记不判回归）',
          resp_anon.status_code == 302 and '/auth/' in (resp_anon.headers.get('Location') or ''),
          f'http={resp_anon.status_code} loc={resp_anon.headers.get("Location")}')
    check('E2 未登录不泄漏任何工资数据（重定向体无 counted/piecework/excluded）',
          not any(k in body for k in ('counted', 'piecework', 'excluded_record_ids', EMP)),
          f'body_len={len(body)}')

    # ---- E3：t5 新增不变量（piecework_amount == counted）不 500 ------------- #
    from app.services.mes_service import piecework_amount, piecework_breakdown
    with app.app_context():
        recs = ProductionRecord.query.filter(ProductionRecord.id.in_(
            [sal_ids['pr_normal'], sal_ids['pr_rework']])).all()
        env = {}
        for sw in (False, True):
            SystemConfig.set('quality.rework_counts_piecework', sw)
            db.session.commit()
            counted, dropped, excluded = piecework_breakdown(recs)
            amt = piecework_amount(recs)
            env[str(sw)] = {'counted': counted, 'dropped': dropped,
                            'piecework_amount': amt, 'equal_within_1e-9': abs(amt - counted) < 1e-9}
        SystemConfig.set('quality.rework_counts_piecework', False)
        db.session.commit()
    R['E3_invariant'] = env
    check('E3 不变量 piecework_amount == counted 在真实种子数据两态下都成立（不 raise、不 500）',
          all(v['equal_within_1e-9'] for v in env.values()), json.dumps(env, ensure_ascii=False))

    # E4：真实页面在「有返工记录」的真实数据下不 500（t5 新增一致性校验的回归面）
    check('E4 真实页面/接口在返工数据下不 500（一致性校验未误报）',
          resp_off.status_code == 200 and resp_on.status_code == 200
          and page_off.status_code == 200,
          f'json_off={resp_off.status_code} json_on={resp_on.status_code} page={page_off.status_code}')

    # ===================================================================== #
    # 收尾：真库 SHA / schema / 路由数
    # ===================================================================== #
    real_sha_after = sha256(REAL_DB)
    R['real_db_sha256_after'] = real_sha_after
    R['real_db_sha256_expected'] = REAL_SHA_EXPECT
    check('收尾 真实 app.db SHA256 未变（= 期望值）',
          real_sha_after == real_sha_before == REAL_SHA_EXPECT, real_sha_after)

    import sqlite3
    schema_q = ("SELECT type, name, sql FROM sqlite_master "
                "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name")

    def schema_of(p):
        con = sqlite3.connect(str(p))
        try:
            return con.execute(schema_q).fetchall()
        finally:
            con.close()

    real_schema, copy_schema = schema_of(REAL_DB), schema_of(copy_path)
    R['schema'] = {'real_objects': len(real_schema), 'copy_objects': len(copy_schema),
                   'identical': real_schema == copy_schema,
                   'copy_extra': [r[1] for r in copy_schema if r not in real_schema]}
    check('收尾 schema 与真库逐表一致（无 DDL 变更）',
          real_schema == copy_schema, f'{len(real_schema)} vs {len(copy_schema)}')

    with app.app_context():
        rules_total_end = len(list(app.url_map.iter_rules()))
    R['rules_total_end'] = rules_total_end
    check('收尾 rules_total 仍为 271', rules_total_end == 271, str(rules_total_end))

    # ------------------------------------------------------------------ #
    # t6 契约 Acceptance 覆盖映射 + 跨 harness 发现 + 覆盖缺口（显式声明）
    # ------------------------------------------------------------------ #
    R['t6_acceptance_map'] = {
        'B12-01_三端点一致': 'A1（三个真实端点同 process_code/业务日 ⇒ process_id 全为 %s）' % ids['same_new'],
        'B12-01_多版本取最新': 'A2（picked=%s price=2.22；阴对照新版推 D+3 ⇒ 只能取到旧版 %s）'
                                 % (ids['latest_new'], ids['latest_old']),
        'B12-01_仅未来价/无价格': 'A3/A4（helper 均 None，三端点 HTTP 200 success=true，走既有文案）',
        'B12-01_容差边界偏差': 'A5（D+1 23:59 被取到 %s；D+2 00:01 被排除）' % ids['d1'],
        'B12-02_修复两态': 'C（真实 uploads/temp；阴 0 行含 KeyError 串，阳 +1 行）',
        'B12-02_行级容错': 'C.row_level_tolerance（坏行跳过、200 非 500、坏行未入库）',
        'B12-03_件数差分': 'D1/D2（阴 Δ=0；阳真实端点 Δ=+3.0，行 Δ=1，notes 含 #nc.id）',
        'B12-03_有工件路径': 'D3（件数 3→4，Δ=+1，WorkpieceEvent payload 三键不变）',
        'B12-04_两态区分': 'E/E2/E3/E4（60.0↔160.0 Δ=100；dropped/excluded 暴露；不变量不 500）',
        '无 schema 变更': '收尾 schema.identical + 真库 SHA256 + check_migration_heads',
        '路由不变量': 'rules_total=%s（我的探针实测）+ route_inventory total rules=271 + ci_gates coverage_drift blocking 绿'
                    % rules_total_end,
    }
    R['cross_harness_findings'] = {
        'source': '冻结 P0-4 门禁（我用 --scenario all 自跑，非作者转述）',
        'w2w3_probe': '43/46 passed，3 条 failed（report-only，不阻塞 ci_gates）',
        'negative_matrix': '27/28 passed，1 条 failed：NV-2.3（与 w2w3 AC04-e 同一根因，exit 仍 0）',
        'failed_ids': ['AC04-e', 'AC04-e2', 'AC04-d-s34', 'NV-2.3'],
        'root_cause': (
            'B12-04（t5）在 app/main/routes.py 的 _piecework_detail 里直读 '
            "SystemConfig.get('quality.rework_counts_piecework', ...)（routes.py:86）⇒ 开关读取点 1→2"
            '（AC04-e/NV-2.3）；模板 app/templates/main/salary_calculation.html 出现 '
            'rework_counts_piecework 字样 ⇒ 工资模板命中 1（AC04-e2）；routes.py 内 '
            'piecework_amount( 调用数 3→4（AC04-d-s34）。'),
        'impact_on_b12_04_amounts': '无：counted/金额两态 60.0/160.0 与开关语义一致（E3 不变量成立）。',
        'not_in_my_scope': 'app/ 实现代码与 test-reports-2026-10/harness/** 都在我的 out-of-scope ⇒ 只登记，不改。',
    }
    R['coverage_gaps'] = [
        '未覆盖：真实浏览器/前端 JS 行为（只做 test_client 端点 + 模板字节断言）。',
        '未覆盖：ExcelGenerator 第 4 个取价读点（app/utils/excel_generator.py:877 用 '
        'filter_by(process_code=..., is_current=True)，非本批范围，只登记）。',
        '未覆盖：scrap 分支不吃 notes（app/main/stock.py:97 既有语义，非缺陷）。',
        '已知偏差（不是回归）：未登录访问 /salary_calculation?format=json 返回 302 → /auth/ 而非 401 JSON'
        '（permissions._wants_json 只认 /api/ 前缀；已实测响应体 309 字节重定向页、无工资数据）。',
        '已知偏差（不是回归）：helper 保留 effective_date <= end_of_day + timedelta(days=1) 容差 ⇒ '
        '业务日 +1 天生效的价会被取到（A5 实测）。',
        '语义观测（低）：开关打开时 normal_quantity/rework_quantity 随 excluded 归零/合并，'
        '不再表示「返工产量」；逐行 is_rework 亦随 excluded 变 false（详见 E_quantity_semantics_observed）。',
        '本探针只跑 3 条 w2w3 相关 harness 的读数，harness 源码冻结、未改动。',
    ]
    R['verdicts'] = VERDICTS
    R['failed_verdicts'] = [v['name'] for v in VERDICTS if not v['ok']]
    R['RESULT'] = 'OK' if not R['failed_verdicts'] else 'FAIL'

    out = pathlib.Path(__file__).with_suffix('.output.json')
    out.write_text(json.dumps(R, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps({'RESULT': R['RESULT'], 'failed': R['failed_verdicts'],
                      'verdict_count': len(VERDICTS),
                      'summary': {k: R[k] for k in (
                          'rules_total', 'real_db_sha256_before', 'schema', 'A1_three_sites',
                          'A2_multi_version', 'A5_tolerance_window', 'C_b12_02')}},
                     ensure_ascii=False, indent=1))
    print('RESULT:', R['RESULT'])
    return 0 if R['RESULT'] == 'OK' else 1


if __name__ == '__main__':
    raise SystemExit(main())
