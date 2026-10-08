# -*- coding: utf-8 -*-
"""t3（B12-01）验证：取价单点统一 —— 三处取价解析到同一 ProcessPrice 版本。

全程只用 app.db 副本（scripts/_test_bootstrap.make_app()），真实 app.db 只读；
`_t3_` 前缀标记本脚本自建的测试实体，避免与既有数据混淆。

判据（与任务 Acceptance 一一对应）：
  A1 同一 process_code 在导入链（原 :2717 段）与报工/工资链（原 :3902、:4020 段）
     取到同一 ProcessPrice.id（现场断言相等）
  A2 阳性对照：两版工价（旧=低 id，新=高 id），业务日期落在两版之间 ⇒ 三处都取
     「业务日期之前的最新版」= 高 id 那条
  A3 阴性对照：effective_date > 业务日期（+1 天容差）的行必须被排除；
     无生效版本时返回 None（语义与修前基准 :2717-2720 一致），不抛未捕获异常
  A4 修前留档：同一夹具用修前口径 :3902/:4020（filter_by(process_code).first()）
     取到的是低 id 旧版（与 :2717 段的高 id 不一致）—— 81- 后续开发与测试规划.md:131
     风险①「工资数字会变」的证据
  A5 三处调用点不再各自内联构造 ProcessPrice 查询，统一走 pick_process_price；
     无 schema 变更；真库 app.db SHA256 不变

用法：python -B scripts/_sandbox_compat.py test-reports-2026-10/reconcile-2026-10-08/probe_t3_pick_process_price.py
"""
import ast
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

REAL_DB = ROOT / 'app.db'
REAL_SHA_EXPECT = 'F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065'

ROUTES_PY = ROOT / 'app' / 'main' / 'routes.py'

EMP_TEST = '_t3_EMP9001'
CODE_MAIN = '_T3P9001'      # 两版工价：旧（低 id）/ 新（高 id）+ 一条未来价
CODE_FUTURE = '_T3P9002'    # 只有未来价
CODE_NONE = '_T3P9003'      # 完全没有工价
# 修前留档里契约提到的现场读数（真库最大 id 为 3486，3487/3488 是「紧接着的两条」）
LEGACY_IDS = (3487, 3488)

# 三个调用点所在的视图函数（原行号 :2717-2720 / :3902 / :4020）
CALL_SITES = {
    'import_production_records': '生产记录导入链（原 :2717-2720，基准正确口径）',
    'import_bonus_penalties': '奖惩导入链（原 :3902，修前错误口径）',
    'import_tasks': '任务导入链（原 :4020，修前错误口径）',
}


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest().upper()


def xlsx(headers, rows):
    """内存构造一个 .xlsx，返回可供 test_client 上传的 BytesIO。"""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def seed(app):
    """在副本库里造夹具：两版工价 + 未来价 + 员工。返回 id 读数。"""
    from datetime import date, datetime, timedelta

    from app import db
    from app.models import Employee, SerialNumber

    with app.app_context():
        import app.models as M

        today = date.today()
        biz_day = today + timedelta(days=1)          # 业务日期
        past_eff = datetime.combine(today - timedelta(days=30), datetime.min.time())
        biz_eff = datetime.combine(today - timedelta(days=1), datetime.min.time())  # 业务日期之前
        future_eff = datetime.combine(today + timedelta(days=30), datetime.min.time())

        emp = Employee.query.filter_by(employee_id=EMP_TEST).first()
        if emp is None:
            emp = Employee(global_sn=SerialNumber.get_next_number(), employee_id=EMP_TEST,
                           name='_t3_测试员工', position='普通员工', hire_date=today)
            db.session.add(emp)
            db.session.flush()

        def add_price(code, price, eff, name):
            pp = M.ProcessPrice(global_sn=SerialNumber.get_next_number(), process_code=code,
                                process_name=name, price=price, version=1,
                                effective_date=eff, is_current=True, price_type='normal')
            db.session.add(pp)
            db.session.flush()
            return pp.id

        # 真库现在最大 id=3486 —— 先占两条，使新造的「旧/新」两版坐到 3487/3488，
        # 复现 81- 计划里的现场读数编号。已有夹具（重复运行时）则复用，不再占位。
        existing = {p.id for p in M.ProcessPrice.query.filter(
            M.ProcessPrice.process_code.in_([CODE_MAIN, CODE_FUTURE])).all()}
        if not existing:
            seat_a = add_price('_T3P_SEAT_A', 1.0, past_eff, '_t3_占位A')
            seat_b = add_price('_T3P_SEAT_B', 1.0, past_eff, '_t3_占位B')
            old_id = add_price(CODE_MAIN, 1.11, past_eff, '_t3_旧版工序')
            new_id = add_price(CODE_MAIN, 2.22, biz_eff, '_t3_新版工序')
            fut_id = add_price(CODE_MAIN, 9.99, future_eff, '_t3_未来版工序')
            fut_only_id = add_price(CODE_FUTURE, 3.33, future_eff, '_t3_仅未来价工序')
        else:
            main_rows = M.ProcessPrice.query.filter_by(
                process_code=CODE_MAIN).order_by(M.ProcessPrice.id).all()
            fut_rows = M.ProcessPrice.query.filter_by(
                process_code=CODE_FUTURE).order_by(M.ProcessPrice.id).all()
            seat_a, seat_b = -1, -1
            old_id = main_rows[0].id
            new_id = main_rows[1].id
            fut_id = main_rows[2].id
            fut_only_id = fut_rows[0].id
        db.session.commit()
        return {
            'employee_pk': emp.id,
            'seed_biz_day': biz_day.isoformat(),
            'past_effective_date': past_eff.isoformat(),
            'biz_effective_date': biz_eff.isoformat(),
            'future_effective_date': future_eff.isoformat(),
            'seat_ids': [seat_a, seat_b],
            'old_price_id': old_id,
            'new_price_id': new_id,
            'future_price_id': fut_id,
            'future_only_price_id': fut_only_id,
            'legacy_ids_referenced_by_contract': list(LEGACY_IDS),
            'legacy_ids_matched': (seat_a, seat_b) == LEGACY_IDS,
        }


def old_semantics(process_code):
    """修前 :3902/:4020 的口径（逐字复现）：无 effective_date 约束、无 order_by desc。"""
    from app.models import ProcessPrice

    return ProcessPrice.query.filter_by(process_code=process_code).first()


def call_helper(app, code, business_date):
    """直接调用单点函数（无 HTTP，需应用上下文），返回 (id, price, error)。"""
    import app.main.routes as routes_mod

    try:
        with app.app_context():
            pp = routes_mod.pick_process_price(code, business_date)
            if pp is None:
                return None, None, None
            return pp.id, float(pp.price), None
    except Exception as e:  # noqa: BLE001
        return None, None, f'{type(e).__name__}: {e}'


def site_source_map():
    """AST 定位三个调用点所在视图函数的源码片段 + 该函数内对 ProcessPrice 的直接引用。"""
    src = ROUTES_PY.read_text(encoding='utf-8')
    tree = ast.parse(src)
    lines = src.splitlines()
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in CALL_SITES:
            seg = '\n'.join(lines[node.lineno - 1:node.end_lineno])
            direct_pp = []
            for sub in ast.walk(node):
                # ProcessPrice.query / ProcessPrice.query.filter(...)
                if isinstance(sub, ast.Attribute) and sub.attr == 'query':
                    if isinstance(sub.value, ast.Name) and sub.value.id == 'ProcessPrice':
                        direct_pp.append(sub.lineno)
            out[node.name] = {
                'lineno': node.lineno,
                'end_lineno': node.end_lineno,
                'uses_pick_process_price': 'pick_process_price(' in seg,
                'direct_ProcessPrice_query_lines': sorted(set(direct_pp)),
                'snippet_has_effective_date_filter': 'ProcessPrice.effective_date' in seg,
            }
    return out


def main():
    result = {}
    real_sha_before = sha256(REAL_DB)
    result['real_db_sha256_before'] = real_sha_before
    result['real_db_sha256_expected'] = REAL_SHA_EXPECT

    app, copy_path = make_app(fresh=True)
    result['db_copy_path'] = copy_path
    result['db_uri'] = app.config['SQLALCHEMY_DATABASE_URI']

    # 沙箱下 uploads/temp 被 ACL 拒写（仅环境层限制，与本任务代码无关）。
    # 端点只读 app.config['TEMP_FOLDER']，因此把它指到工作区内可写目录 —— 端点代码零改动。
    scratch = ROOT / '.analysis-scratch' / 't3_temp'
    scratch.mkdir(parents=True, exist_ok=True)
    app.config['TEMP_FOLDER'] = str(scratch)

    mappings, pw = ensure_role_users(app)
    f = seed(app)
    result['fixture'] = f

    import app.main.routes as routes_mod
    from app import db
    from app.models import BonusPenalty, ProcessPrice, ProductionRecord, TaskAssignment

    biz_day = None
    from datetime import date as _date
    biz_day = _date.fromisoformat(f['seed_biz_day'])

    # ---- A1：三处取价（经真实 HTTP 端点）解析到同一 ProcessPrice.id ----
    client = app.test_client()
    login_as(client, mappings['admin'], pw)

    # 站点 1：生产记录导入（原 :2717-2720）
    with app.app_context():
        before_pr = ProductionRecord.query.count()
    fx1 = xlsx(['日期*', '员工工号*', '工序编号*', '数量*'],
               [[biz_day, EMP_TEST, CODE_MAIN, 7]])
    r1 = client.post('/production_records/import',
                     data={'file': (fx1, 't3_pr.xlsx')}, content_type='multipart/form-data')
    j1 = r1.get_json(silent=True) or {}
    with app.app_context():
        pr = (ProductionRecord.query.filter_by(process_id=f['new_price_id'])
              .order_by(ProductionRecord.id.desc()).first())
        pr_old = (ProductionRecord.query.filter_by(process_id=f['old_price_id'])
                  .order_by(ProductionRecord.id.desc()).first())
        result['site1_production_records_import'] = {
            'http_status': r1.status_code,
            'records_delta': ProductionRecord.query.count() - before_pr,
            'message': j1.get('message'),
            'process_id_written': pr.process_id if pr else None,
            'rows_on_old_price': ProductionRecord.query.filter_by(
                process_id=f['old_price_id']).count(),
            'rows_on_new_price': ProductionRecord.query.filter_by(
                process_id=f['new_price_id']).count(),
            'chose_new_price_id': bool(pr) and not pr_old,
        }

    # 站点 2：奖惩导入（原 :3902）
    with app.app_context():
        before_bp = BonusPenalty.query.count()
    fx2 = xlsx(['日期', '员工工号', '类型', '金额', '工序编号', '原因'],
               [[biz_day, EMP_TEST, 'bonus', 50.0, CODE_MAIN, '_t3_取价核对']])
    r2 = client.post('/bonus_penalties/import',
                     data={'file': (fx2, 't3_bp.xlsx')}, content_type='multipart/form-data')
    j2 = r2.get_json(silent=True) or {}
    with app.app_context():
        bp = (BonusPenalty.query.filter_by(process_id=f['new_price_id'])
              .order_by(BonusPenalty.id.desc()).first())
        bp_old = (BonusPenalty.query.filter_by(process_id=f['old_price_id'])
                  .order_by(BonusPenalty.id.desc()).first())
        result['site2_bonus_penalties_import'] = {
            'http_status': r2.status_code,
            'records_delta': BonusPenalty.query.count() - before_bp,
            'message': j2.get('message'),
            'process_id_written': bp.process_id if bp else None,
            'chose_new_price_id': bool(bp) and not bp_old,
        }

    # 站点 3：任务导入（原 :4020）
    with app.app_context():
        before_ta = TaskAssignment.query.count()
    fx3 = xlsx(['员工工号', '工序编号', '数量', '目标完成日期', '备注'],
               [[EMP_TEST, CODE_MAIN, 5, biz_day, '_t3_取价核对']])
    r3 = client.post('/tasks/import',
                     data={'file': (fx3, 't3_ta.xlsx')}, content_type='multipart/form-data')
    j3 = r3.get_json(silent=True) or {}
    with app.app_context():
        ta = (TaskAssignment.query.filter_by(process_id=f['new_price_id'])
              .order_by(TaskAssignment.id.desc()).first())
        ta_old = (TaskAssignment.query.filter_by(process_id=f['old_price_id'])
                  .order_by(TaskAssignment.id.desc()).first())
        result['site3_tasks_import'] = {
            'http_status': r3.status_code,
            'records_delta': TaskAssignment.query.count() - before_ta,
            'message': j3.get('message'),
            'process_id_written': ta.process_id if ta else None,
            'chose_new_price_id': bool(ta) and not ta_old,
        }

    got = {
        'site1': (result['site1_production_records_import']['process_id_written']
                  if result['site1_production_records_import']['chose_new_price_id'] else 'MISMATCH'),
        'site2': (result['site2_bonus_penalties_import']['process_id_written']
                  if result['site2_bonus_penalties_import']['chose_new_price_id'] else 'MISMATCH'),
        'site3': (result['site3_tasks_import']['process_id_written']
                  if result['site3_tasks_import']['chose_new_price_id'] else 'MISMATCH'),
    }
    result['A1_site_readings'] = {
        'expected_process_price_id': f['new_price_id'],
        'site1_process_id': got['site1'],
        'site2_process_id': got['site2'],
        'site3_process_id': got['site3'],
        'all_three_equal': got['site1'] == got['site2'] == got['site3'] == f['new_price_id'],
    }

    # ---- A2：helper 直调（两版 + 未来价） ----
    nid, nprice, nerr = call_helper(app, CODE_MAIN, biz_day)
    result['A2_helper_positive'] = {
        'business_date': str(biz_day),
        'returned_id': nid,
        'expected_new_id': f['new_price_id'],
        'expected_old_id': f['old_price_id'],
        'returned_price': nprice,
        'error': nerr,
        'picked_latest_effective_before_business_date': nid == f['new_price_id'],
    }

    # ---- A3：阴性对照 + 无生效版本 ----
    fut_id, fut_price, fut_err = call_helper(app, CODE_FUTURE, biz_day)
    none_id, _, none_err = call_helper(app, CODE_NONE, biz_day)
    result['A3_negative_future_price'] = {
        'code_with_only_future_price': CODE_FUTURE,
        'future_price_id_in_db': f['future_only_price_id'],
        'returned_id': fut_id,
        'excluded_future_price': fut_id is None,
        'error': fut_err,
    }
    result['A3_no_effective_version'] = {
        'code_without_price': CODE_NONE,
        'returned_id': none_id,
        'returned_none_no_exception': none_id is None and none_err is None,
        'error': none_err,
    }
    # 未来价不得占据 CODE_MAIN 的最新版位（helper 已排除 9.99 那条）
    result['A3_future_row_not_picked_for_main_code'] = {
        'main_code_picked_id': nid,
        'future_row_id': f['future_price_id'],
        'future_row_excluded': nid != f['future_price_id'],
    }

    # ---- A4：修前留档（同一夹具，旧口径读数） ----
    with app.app_context():
        legacy_old = old_semantics(CODE_MAIN)
        legacy_old_id = legacy_old.id if legacy_old else None
        legacy_old_price = float(legacy_old.price) if legacy_old else None
    original_helper = routes_mod.pick_process_price
    # 修前 :3902/:4020 的口径经真实端点重放（把单点临时换成旧语义，重放站点 3）
    routes_mod.pick_process_price = lambda code, d: old_semantics(code)
    fx4 = xlsx(['员工工号', '工序编号', '数量', '目标完成日期', '备注'],
               [[EMP_TEST, CODE_MAIN, 3, biz_day, '_t3_修前口径重放']])
    r4 = client.post('/tasks/import',
                     data={'file': (fx4, 't3_ta_prefix.xlsx')}, content_type='multipart/form-data')
    with app.app_context():
        prefix_row = (TaskAssignment.query.order_by(TaskAssignment.id.desc()).first())
        prefix_pid = prefix_row.process_id if prefix_row else None
    routes_mod.pick_process_price = original_helper
    result['A4_pre_fix_reading'] = {
        'same_fixture': True,
        'fixture_code': CODE_MAIN,
        'fixture_business_date': str(biz_day),
        'old_semantics_helper_returned_id': legacy_old_id,
        'old_semantics_helper_returned_price': legacy_old_price,
        'old_semantics_endpoint_process_id': prefix_pid,
        'old_semantics_endpoint_http_status': r4.status_code,
        'baseline_2717_reading_id': nid,          # 基准（修前就已正确的那处）= 新版高 id
        'inconsistent_before_fix': legacy_old_id is not None and legacy_old_id != nid,
        'pre_fix_three_site_reading': {
            'site1_original_2717_baseline': nid,
            'site2_original_3902_baseline': legacy_old_id,
            'site3_original_4020_baseline': prefix_pid,
            'sites_disagree_before_fix': len({nid, legacy_old_id, prefix_pid}) > 1,
        },
        'legacy_ids_referenced_by_contract': list(LEGACY_IDS),
        'legacy_ids_matched_this_run': bool(f.get('legacy_ids_matched')),
        'note': ('契约提到的现场读数 3487/3488 是「真库 max id=3486 之后紧接着的两条」；'
                 '本探针在副本库上让这两条坐到 %s（旧/低 id）/ %s（新/高 id），'
                 '复现同一现象：修前 :3902/:4020 取旧版 %s，:2717 段取新版 %s'
                 ' —— 同一业务数据取价版本不一致（81- 计划 :131 风险①）。'
                 % (legacy_old_id, nid, legacy_old_id, nid)),
    }

    # ---- A5：三处调用点统一 + 无 schema 变更 ----
    result['A5_call_sites'] = site_source_map()
    result['A5_helper_source_check'] = {
        'helper_exists': hasattr(routes_mod, 'pick_process_price'),
        'helper_defined_in_routes_py': 'def pick_process_price(' in ROUTES_PY.read_text(
            encoding='utf-8'),
    }
    with app.app_context():
        result['A5_price_rows_on_test_code'] = {
            'CODE_MAIN_total': ProcessPrice.query.filter_by(process_code=CODE_MAIN).count(),
            'CODE_MAIN_ids': [p.id for p in ProcessPrice.query.filter_by(
                process_code=CODE_MAIN).order_by(ProcessPrice.id).all()],
        }

    real_sha_after = sha256(REAL_DB)
    result['real_db_sha256_after'] = real_sha_after
    result['A5_real_db_unchanged'] = (real_sha_after == real_sha_before)

    import sqlite3
    schema_q = ("SELECT type, name, sql FROM sqlite_master "
                "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name")

    def schema_of(db_file):
        con = sqlite3.connect(db_file)
        try:
            return con.execute(schema_q).fetchall()
        finally:
            con.close()

    real_schema = schema_of(str(REAL_DB))
    copy_schema = schema_of(copy_path)
    result['A5_schema'] = {
        'real_objects': len(real_schema),
        'copy_objects': len(copy_schema),
        'schema_identical': real_schema == copy_schema,
    }

    out_path = pathlib.Path(__file__).with_suffix('.output.json')
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf-8')
    # 控制台按 GBK 输出中文会 mojibake/抛错；判据以 .output.json（UTF-8）为准。
    print(json.dumps(result, ensure_ascii=True, indent=1))

    sites = result['A5_call_sites']
    sites_unified = all(
        v['uses_pick_process_price'] and not v['direct_ProcessPrice_query_lines']
        for v in sites.values()
    ) and len(sites) == len(CALL_SITES)

    ok = (
        result['A1_site_readings']['all_three_equal']
        and result['A2_helper_positive']['picked_latest_effective_before_business_date']
        and result['A3_negative_future_price']['excluded_future_price']
        and result['A3_no_effective_version']['returned_none_no_exception']
        and result['A3_future_row_not_picked_for_main_code']['future_row_excluded']
        and result['A4_pre_fix_reading']['inconsistent_before_fix']
        and result['A4_pre_fix_reading']['pre_fix_three_site_reading']['sites_disagree_before_fix']
        and result['A4_pre_fix_reading']['old_semantics_endpoint_process_id']
            == result['A4_pre_fix_reading']['old_semantics_helper_returned_id']
        and result['A4_pre_fix_reading']['old_semantics_endpoint_http_status'] == 200
        and sites_unified
        and result['A5_real_db_unchanged']
        and result['A5_schema']['schema_identical']
        and real_sha_after == REAL_SHA_EXPECT
    )
    print('RESULT:', 'OK' if ok else 'FAIL')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
