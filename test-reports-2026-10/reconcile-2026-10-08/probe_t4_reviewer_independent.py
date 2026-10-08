# -*- coding: utf-8 -*-
"""t4（B12-01 取价单点统一）非作者独立评审探针 —— 只读评审，不改实现。

作者 = backend-dev（t3）；本脚本由 reviewer 独立编写，不依赖 t3 探针的任何返回值：
夹具自建（`_t4r_` 前缀）、静态核对用本脚本自己的 AST、修前证据用 `git show HEAD:app/main/routes.py`
落盘后的 AST + `git diff HEAD` 的删除行两条独立来源核对。

判据（与 t4 任务 Acceptance 一一对应）：
  B1 代码级：三个原取价点（:2717-2720 段 / :3902 / :4020）所在视图函数内
     ① 出现 pick_process_price(...) 调用；② 直接 `ProcessPrice.query` 命中 0 处；
     ③ 全文件 `ProcessPrice.query` 的 AST 命中只剩 helper 自己；④ 代码层（非注释）
     `filter_by(process_code` 命中 0 处
  B2 独立可复跑：三端点同值（自建夹具，业务日落在两版之间 ⇒ 都取新版高 id）
  B3 阴性：严格未来价（业务日 +2 天 / +30 天）必须排除；无价返 None 不抛异常；
     并给出 `+1 天` 容差的边界读数（计划 81- :107 阴性对照的严格措辞是否成立）
  B4 修前差异留档可复现：用 `git show HEAD` 的修前源码证明 :3902/:4020 原为
     `filter_by(process_code).first()`（无日期约束、无版本排序），并把差异沿真实工资链
     **修前语义** tasks 导入 → TaskAssignment.process_id → 报工 → ProductionRecord.process_id
     → mes_service.piecework_amount 与**修后**同链对照，给出单价/计件读数
  B5 无 schema 变更：副本与真库 sqlite_master 逐表一致；真库 app.db SHA256 前后不变

用法（仓库根目录）：
    python -B scripts/_sandbox_compat.py test-reports-2026-10/reconcile-2026-10-08/probe_t4_reviewer_independent.py
"""
import ast
import hashlib
import io
import json
import pathlib
import sqlite3
import sys
from datetime import date, datetime, timedelta

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

from _test_bootstrap import ensure_role_users, login_as, make_app  # noqa: E402

ROUTES_PY = ROOT / 'app' / 'main' / 'routes.py'
REAL_DB = ROOT / 'app.db'
SCRATCH = ROOT / '.analysis-scratch'
PREFIX_PY = SCRATCH / 't4_prefix_routes.py'
DIFF_TXT = SCRATCH / 't4_routes.diff'
OUT_JSON = pathlib.Path(__file__).resolve().with_suffix('.output.json')
REAL_SHA_EXPECT = 'F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065'

CALL_SITES = ('import_production_records', 'import_bonus_penalties', 'import_tasks')

EMP_TEST = '_t4r_EMP9001'
CODE_MAIN = '_T4R9001'   # 旧版(D-30,1.5) / 新版(D-1,3.5) / 远未来(D+30,99.0)
CODE_TOL = '_T4R9010'    # 容差边界：D+1 00:00 / D+1 23:59:59.999999 / D+2 00:00
CODE_FAR = '_T4R9011'    # 只有 D+30 的严格未来价
CODE_NONE = '_T4R9012'   # 完全没有工价
CODE_D1 = '_T4R9013'     # 只有 D+1 00:00 的一条（严格未来，落在 +1 天容差内）

FAILURES = []


def check(name, ok, detail=None):
    FAILURES.append({'check': name, 'detail': detail}) if not ok else None
    return ok


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest().upper()


def pp_query_lines(tree):
    """全文件 AST：`ProcessPrice.query` 命中（line → 所属函数名）。"""
    hits = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for sub in ast.walk(node):
                if (isinstance(sub, ast.Attribute) and sub.attr == 'query'
                        and isinstance(sub.value, ast.Name) and sub.value.id == 'ProcessPrice'):
                    hits.setdefault(sub.lineno, node.name)
    return hits


def analyse(path):
    """对给定 routes.py 副本做静态核对，返回结构化读数。"""
    src = pathlib.Path(path).read_text(encoding='utf-8')
    tree = ast.parse(src)
    lines = src.splitlines()
    sites = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in CALL_SITES:
            calls, direct = [], []
            for sub in ast.walk(node):
                if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
                        and sub.func.id == 'pick_process_price'):
                    calls.append(sub.lineno)
                if (isinstance(sub, ast.Attribute) and sub.attr == 'query'
                        and isinstance(sub.value, ast.Name) and sub.value.id == 'ProcessPrice'):
                    direct.append(sub.lineno)
            seg = '\n'.join(lines[node.lineno - 1:node.end_lineno])
            code_only = '\n'.join(l for l in seg.splitlines() if not l.strip().startswith('#'))
            sites[node.name] = {
                'lineno': node.lineno,
                'end_lineno': node.end_lineno,
                'pick_process_price_call_lines': sorted(set(calls)),
                'direct_ProcessPrice_query_lines': sorted(set(direct)),
                'inline_effective_date_filter_in_code': 'ProcessPrice.effective_date' in code_only,
                'code_text_filter_by_process_code_hits': code_only.count('filter_by(process_code'),
                'comment_text_filter_by_process_code_hits': (
                    seg.count('filter_by(process_code') - code_only.count('filter_by(process_code')),
            }
    return {
        'path': str(path),
        'sha256': sha256(path),
        'line_count': len(lines),
        'sites': sites,
        'module_ProcessPrice_query_hits': {str(k): v for k, v in sorted(pp_query_lines(tree).items())},
        'helper_def_lineno': next((n.lineno for n in ast.walk(tree)
                                   if isinstance(n, ast.FunctionDef)
                                   and n.name == 'pick_process_price'), None),
    }


def diff_removed_pricing_lines():
    """`git diff HEAD` 里被删除的、含 ProcessPrice 的行（修前源码的机械证据）。"""
    txt = DIFF_TXT.read_text(encoding='utf-8', errors='replace')
    return [ln.strip() for ln in txt.splitlines()
            if ln.startswith('-') and not ln.startswith('---') and 'ProcessPrice' in ln]


def xlsx(headers, rows):
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
    from app import db
    from app.models import Employee, ProcessPrice, SerialNumber

    today = date.today()
    biz = today + timedelta(days=1)
    with app.app_context():
        emp = Employee.query.filter_by(employee_id=EMP_TEST).first()
        if emp is None:
            emp = Employee(global_sn=SerialNumber.get_next_number(), employee_id=EMP_TEST,
                           name='_t4r_评审员工', position='普通员工', hire_date=today)
            db.session.add(emp)
            db.session.flush()

        def add(code, price, eff, name):
            row = ProcessPrice(global_sn=SerialNumber.get_next_number(), process_code=code,
                               process_name=name, price=price, version=1,
                               effective_date=eff, is_current=True, price_type='normal')
            db.session.add(row)
            db.session.flush()
            return row.id

        existing = ProcessPrice.query.filter(
            ProcessPrice.process_code.in_([CODE_MAIN, CODE_TOL, CODE_FAR, CODE_NONE, CODE_D1])).count()
        if not existing:
            ids = {
                'old': add(CODE_MAIN, 1.5, datetime.combine(today - timedelta(days=30), datetime.min.time()), '_t4r_旧版'),
                'new': add(CODE_MAIN, 3.5, datetime.combine(today - timedelta(days=1), datetime.min.time()), '_t4r_新版'),
                'far30': add(CODE_MAIN, 99.0, datetime.combine(today + timedelta(days=30), datetime.min.time()), '_t4r_远未来'),
                'tol_d1_0000': add(CODE_TOL, 7.77, datetime.combine(biz + timedelta(days=1), datetime.min.time()), '_t4r_业务日+1天0点'),
                'tol_d1_2359': add(CODE_TOL, 7.78, datetime.combine(biz + timedelta(days=1), datetime.max.time()), '_t4r_业务日+1天末'),
                'tol_d2_0000': add(CODE_TOL, 8.88, datetime.combine(biz + timedelta(days=2), datetime.min.time()), '_t4r_业务日+2天'),
                'far_only': add(CODE_FAR, 9.99, datetime.combine(biz + timedelta(days=30), datetime.min.time()), '_t4r_仅远未来'),
                'd_plus_1_only': add(CODE_D1, 6.66, datetime.combine(biz + timedelta(days=1), datetime.min.time()), '_t4r_仅业务日+1天'),
            }
        else:
            rows = ProcessPrice.query.filter_by(process_code=CODE_MAIN).order_by(ProcessPrice.id).all()
            tol = ProcessPrice.query.filter_by(process_code=CODE_TOL).order_by(ProcessPrice.id).all()
            far = ProcessPrice.query.filter_by(process_code=CODE_FAR).order_by(ProcessPrice.id).all()
            d1 = ProcessPrice.query.filter_by(process_code=CODE_D1).order_by(ProcessPrice.id).all()
            ids = {'old': rows[0].id, 'new': rows[1].id, 'far30': rows[2].id,
                   'tol_d1_0000': tol[0].id, 'tol_d1_2359': tol[1].id, 'tol_d2_0000': tol[2].id,
                   'far_only': far[0].id, 'd_plus_1_only': d1[0].id}
        db.session.commit()
        return {'employee_pk': emp.id, 'biz_day': biz.isoformat(),
                'today': today.isoformat(), 'price_ids': ids}


def old_semantics(process_code):
    """修前 :3902/:4020 口径逐字复现：无 effective_date 约束、无 order_by desc。"""
    from app.models import ProcessPrice
    return ProcessPrice.query.filter_by(process_code=process_code).first()


def call_helper(app, code, business_date):
    import app.main.routes as routes_mod
    try:
        with app.app_context():
            row = routes_mod.pick_process_price(code, business_date)
            return (None, None, None) if row is None else (row.id, float(row.price), None)
    except Exception as exc:  # noqa: BLE001
        return None, None, f'{type(exc).__name__}: {exc}'


def db_objects(path):
    con = sqlite3.connect('file:%s?mode=ro' % pathlib.Path(path).as_posix(), uri=True)
    try:
        return con.execute("SELECT type, name, sql FROM sqlite_master "
                           "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name").fetchall()
    finally:
        con.close()


def main():
    res = {}
    real_before = sha256(REAL_DB)
    res['real_db_sha256_before'] = real_before
    res['real_db_sha256_expected'] = REAL_SHA_EXPECT
    check('real_db_sha256_before_unchanged', real_before == REAL_SHA_EXPECT, real_before)

    # ---------- B1 静态核对（当前工作副本）----------
    res['B1_current'] = analyse(ROUTES_PY)
    res['B1_prefix_HEAD'] = analyse(PREFIX_PY)
    res['B1_diff_removed_ProcessPrice_lines'] = diff_removed_pricing_lines()

    res['routes_py_sha256_at_probe_start'] = res['B1_current']['sha256']
    for fn, reading in res['B1_current']['sites'].items():
        check('B1_%s_uses_helper' % fn, bool(reading['pick_process_price_call_lines']), reading)
        check('B1_%s_no_direct_ProcessPrice_query' % fn,
              not reading['direct_ProcessPrice_query_lines'], reading)
        check('B1_%s_no_code_level_filter_by_process_code' % fn,
              reading['code_text_filter_by_process_code_hits'] == 0, reading)
    helper_line = res['B1_current']['helper_def_lineno']
    others = {ln: f for ln, f in res['B1_current']['module_ProcessPrice_query_hits'].items()
              if f != 'pick_process_price'}
    res['B1_module_hits_outside_helper'] = others
    check('B1_helper_defined', helper_line is not None, helper_line)

    pre = res['B1_prefix_HEAD']['sites']
    res['B1_prefix_summary'] = {
        fn: {
            'uses_helper': bool(r['pick_process_price_call_lines']),
            'code_text_filter_by_process_code_hits': r['code_text_filter_by_process_code_hits'],
            'has_inline_effective_date_filter': r['inline_effective_date_filter_in_code'],
        } for fn, r in pre.items()}
    check('B1_prefix_bonus_penalties_was_filter_by_process_code',
          pre['import_bonus_penalties']['code_text_filter_by_process_code_hits'] >= 1)
    check('B1_prefix_tasks_was_filter_by_process_code',
          pre['import_tasks']['code_text_filter_by_process_code_hits'] >= 1)
    check('B1_prefix_production_records_used_effective_date_baseline',
          pre['import_production_records']['inline_effective_date_filter_in_code'] is True)

    # ---------- 应用（app.db 副本）----------
    app, copy_path = make_app(fresh=True)
    res['db_copy_path'] = copy_path
    res['db_uri'] = app.config['SQLALCHEMY_DATABASE_URI']
    scratch = SCRATCH / 't4_temp'
    scratch.mkdir(parents=True, exist_ok=True)
    app.config['TEMP_FOLDER'] = str(scratch)

    mappings, pw = ensure_role_users(app)
    fixture = seed(app)
    res['fixture'] = fixture
    ids = fixture['price_ids']
    D = date.fromisoformat(fixture['biz_day'])
    D_12h = datetime.combine(D, datetime.min.time()).replace(hour=12)

    import app.main.routes as routes_mod
    from app.models import BonusPenalty, ProcessPrice, ProductionRecord, TaskAssignment
    from app.services import mes_service
    from app import db

    client = app.test_client()
    login_as(client, mappings['admin'], pw)

    def count(model):
        with app.app_context():
            return model.query.count()

    # ---------- B2 三端点同值（真实 HTTP）----------
    b2 = {}
    before = count(ProductionRecord)
    r = client.post('/production_records/import',
                    data={'file': (xlsx(['日期*', '员工工号*', '工序编号*', '数量*'],
                                        [[D, EMP_TEST, CODE_MAIN, 7]]), 't4_pr.xlsx')},
                    content_type='multipart/form-data')
    b2['site1_production_records_import'] = {
        'http_status': r.status_code, 'body': r.get_json(silent=True),
        'records_delta': count(ProductionRecord) - before, 'expected_process_id': ids['new']}
    with app.app_context():
        row = ProductionRecord.query.filter_by(process_id=ids['new']).order_by(ProductionRecord.id.desc()).first()
        b2['site1_production_records_import']['process_id_written'] = row.process_id if row else None

    before = count(BonusPenalty)
    r = client.post('/bonus_penalties/import',
                    data={'file': (xlsx(['日期', '员工工号', '类型', '金额', '工序编号', '原因'],
                                        [[D, EMP_TEST, 'bonus', 50.0, CODE_MAIN, '_t4r_阳性']]), 't4_bp.xlsx')},
                    content_type='multipart/form-data')
    b2['site2_bonus_penalties_import'] = {
        'http_status': r.status_code, 'body': r.get_json(silent=True),
        'records_delta': count(BonusPenalty) - before, 'expected_process_id': ids['new']}
    with app.app_context():
        row = BonusPenalty.query.filter_by(process_id=ids['new']).order_by(BonusPenalty.id.desc()).first()
        b2['site2_bonus_penalties_import']['process_id_written'] = row.process_id if row else None

    before = count(TaskAssignment)
    r = client.post('/tasks/import',
                    data={'file': (xlsx(['员工工号', '工序编号', '数量', '目标完成日期', '备注'],
                                        [[EMP_TEST, CODE_MAIN, 5, D, '_t4r_阳性']]), 't4_ta.xlsx')},
                    content_type='multipart/form-data')
    b2['site3_tasks_import'] = {
        'http_status': r.status_code, 'body': r.get_json(silent=True),
        'records_delta': count(TaskAssignment) - before, 'expected_process_id': ids['new']}
    with app.app_context():
        row = (TaskAssignment.query.filter_by(notes='_t4r_阳性')
               .order_by(TaskAssignment.id.desc()).first())
        b2['site3_tasks_import']['process_id_written'] = row.process_id if row else None

    got = [b2['site1_production_records_import']['process_id_written'],
           b2['site2_bonus_penalties_import']['process_id_written'],
           b2['site3_tasks_import']['process_id_written']]
    b2['all_three_equal'] = all(g == ids['new'] for g in got)
    res['B2_three_sites'] = b2
    check('B2_all_three_equal_new_version', b2['all_three_equal'], got)

    # ---------- B3 阴性 / 容差边界 ----------
    b3 = {}
    b3['main_code_ignores_far30'] = {}
    nid, nprice, nerr = call_helper(app, CODE_MAIN, D)
    b3['main_code_ignores_far30'] = {'returned_id': nid, 'expected': ids['new'],
                                     'far_row_id': ids['far30'], 'returned_price': nprice, 'error': nerr}
    check('B3_main_picks_new_not_far30', nid == ids['new'], b3['main_code_ignores_far30'])

    tid, tprice, terr = call_helper(app, CODE_TOL, D)
    b3['tolerance_boundary'] = {
        'business_day': str(D),
        'd_plus_1_0000_id': ids['tol_d1_0000'],
        'd_plus_1_2359_id': ids['tol_d1_2359'],
        'd_plus_2_0000_id': ids['tol_d2_0000'],
        'returned_id': tid, 'returned_price': tprice, 'error': terr,
        'returned_is_latest_in_window_d_plus_1_2359': tid == ids['tol_d1_2359'],
        'd_plus_2_excluded': tid != ids['tol_d2_0000'],
        'strict_negative_control_81_line107_holds': tid is None,
    }
    check('B3_d_plus_2_excluded', tid != ids['tol_d2_0000'], b3['tolerance_boundary'])

    fid, _, ferr = call_helper(app, CODE_FAR, D)
    b3['far_only_code'] = {'returned_id': fid, 'excluded': fid is None, 'error': ferr,
                           'row_id': ids['far_only']}
    check('B3_far_only_returns_none', fid is None, b3['far_only_code'])

    # 严格未来但落在 `+ timedelta(days=1)` 容差内的单条：helper 会取到它
    # （仅记录读数，不作失败判据 —— 容差是修前基准 :2717-2720 的既有口径，见评审 output）
    o1id, o1price, o1err = call_helper(app, CODE_D1, D)
    b3['strict_future_within_1day_tolerance'] = {
        'business_day': str(D), 'row_effective_date': str(D + timedelta(days=1)),
        'row_id': ids['d_plus_1_only'], 'returned_id': o1id, 'returned_price': o1price,
        'error': o1err,
        'strict_future_row_is_picked_by_helper': o1id == ids['d_plus_1_only'],
        'plan_81_line107_strict_wording_holds': o1id is None,
    }

    zid, _, zerr = call_helper(app, CODE_NONE, D)
    b3['no_price_code'] = {'returned_id': zid, 'none_without_exception': zid is None and zerr is None,
                           'error': zerr}
    check('B3_no_price_none_no_exception', zid is None and zerr is None, b3['no_price_code'])

    sid, _, serr = call_helper(app, CODE_MAIN, D.isoformat())
    b3['string_business_date'] = {'returned_id': sid, 'error': serr, 'same_as_date_object': sid == ids['new']}
    check('B3_string_date_same_result', sid == ids['new'], b3['string_business_date'])

    did, _, derr = call_helper(app, CODE_MAIN, D_12h)
    b3['datetime_midday_business_date'] = {'returned_id': did, 'error': derr}
    check('B3_datetime_midday_same_result', did == ids['new'], b3['datetime_midday_business_date'])

    nid2, _, nerr2 = call_helper(app, CODE_MAIN, None)
    gid, _, gerr = call_helper(app, CODE_MAIN, '不是日期')
    b3['none_and_garbage'] = {'none_business_date_returned': nid2, 'none_error': nerr2,
                              'garbage_returned': gid, 'garbage_error': gerr}
    check('B3_none_business_date_returns_none', nid2 is None and nerr2 is None, b3['none_and_garbage'])
    check('B3_garbage_business_date_no_exception', gerr is None, b3['none_and_garbage'])
    res['B3_negative_and_boundary'] = b3

    # 端点侧阴性：严格未来价不得入库
    b3['http_negative'] = {}
    before = count(ProductionRecord)
    r = client.post('/production_records/import',
                    data={'file': (xlsx(['日期*', '员工工号*', '工序编号*', '数量*'],
                                        [[D, EMP_TEST, CODE_FAR, 3]]), 't4_pr_neg.xlsx')},
                    content_type='multipart/form-data')
    b3['http_negative']['production_records_import'] = {
        'http_status': r.status_code, 'records_delta': count(ProductionRecord) - before,
        'body': r.get_json(silent=True)}
    check('B3_http_production_records_rejects_future_only',
          b3['http_negative']['production_records_import']['records_delta'] == 0,
          b3['http_negative']['production_records_import'])

    before = count(TaskAssignment)
    r = client.post('/tasks/import',
                    data={'file': (xlsx(['员工工号', '工序编号', '数量', '目标完成日期', '备注'],
                                        [[EMP_TEST, CODE_FAR, 4, D, '_t4r_阴性']]), 't4_ta_neg.xlsx')},
                    content_type='multipart/form-data')
    b3['http_negative']['tasks_import'] = {
        'http_status': r.status_code, 'records_delta': count(TaskAssignment) - before,
        'body': r.get_json(silent=True)}
    check('B3_http_tasks_rejects_future_only',
          b3['http_negative']['tasks_import']['records_delta'] == 0,
          b3['http_negative']['tasks_import'])

    before = count(BonusPenalty)
    r = client.post('/bonus_penalties/import',
                    data={'file': (xlsx(['日期', '员工工号', '类型', '金额', '工序编号', '原因'],
                                        [[D, EMP_TEST, 'bonus', 10.0, CODE_FAR, '_t4r_阴性']]), 't4_bp_neg.xlsx')},
                    content_type='multipart/form-data')
    with app.app_context():
        neg_bp = (BonusPenalty.query.filter_by(reason='_t4r_阴性')
                  .order_by(BonusPenalty.id.desc()).first())
    b3['http_negative']['bonus_penalties_import'] = {
        'http_status': r.status_code, 'records_delta': count(BonusPenalty) - before,
        'process_id_written': neg_bp.process_id if neg_bp else 'NO_ROW',
        'body': r.get_json(silent=True)}
    check('B3_http_bonus_writes_null_process_for_future_only',
          b3['http_negative']['bonus_penalties_import']['process_id_written'] is None,
          b3['http_negative']['bonus_penalties_import'])
    res['B3_negative_and_boundary'] = b3

    # ---------- B4 修前差异沿真实工资链复现 ----------
    def run_chain(label, patch_old):
        original = routes_mod.pick_process_price
        if patch_old:
            routes_mod.pick_process_price = lambda code, d: old_semantics(code)
        try:
            r_imp = client.post('/tasks/import',
                                data={'file': (xlsx(['员工工号', '工序编号', '数量', '目标完成日期', '备注'],
                                                    [[EMP_TEST, CODE_MAIN, 10, D, label]]), 't4_chain.xlsx')},
                                content_type='multipart/form-data')
        finally:
            routes_mod.pick_process_price = original
        with app.app_context():
            ta = (TaskAssignment.query.filter_by(notes=label)
                  .order_by(TaskAssignment.id.desc()).first())
            step1 = {'task_assignment_id': ta.id if ta else None,
                     'process_id': ta.process_id if ta else None,
                     'quantity': ta.quantity if ta else None}
        r_rep = client.post('/tasks/%s/update_status' % step1['task_assignment_id'],
                            json={'completed_quantity': 10})
        with app.app_context():
            rec = ProductionRecord.query.filter_by(global_sn=ta.global_sn).first() if ta else None
            step2 = {'production_record_id': rec.id if rec else None,
                     'process_id': rec.process_id if rec else None,
                     'quantity': rec.quantity if rec else None,
                     'date': str(rec.date) if rec else None}
            if rec and rec.process_id:
                pp = ProcessPrice.query.get(rec.process_id)
                step2['unit_price'] = float(pp.price) if pp else None
                step2['piecework_amount'] = float(mes_service.piecework_amount([rec]))
            else:
                step2['unit_price'] = None
                step2['piecework_amount'] = None
        return {'import_http': r_imp.status_code, 'import_body': r_imp.get_json(silent=True),
                'import_reading': step1, 'report_http': r_rep.status_code,
                'report_body': r_rep.get_json(silent=True), 'wage_reading': step2}

    chain_pre = run_chain('_t4r_修前链', patch_old=True)
    chain_post = run_chain('_t4r_修后链', patch_old=False)
    res['B4_wage_chain'] = {
        'fixture': {'code': CODE_MAIN, 'business_day': str(D), 'quantity': 10,
                    'old_price_id': ids['old'], 'new_price_id': ids['new'],
                    'old_price': 1.5, 'new_price': 3.5},
        'prefix_code_evidence': {
            'routes_py_at_HEAD_sha256': res['B1_prefix_HEAD']['sha256'],
            'import_bonus_penalties_pre_fix_hits': pre['import_bonus_penalties'],
            'import_tasks_pre_fix_hits': pre['import_tasks'],
            'import_production_records_pre_fix_hits': pre['import_production_records'],
            'diff_removed_ProcessPrice_lines': res['B1_diff_removed_ProcessPrice_lines'],
        },
        'pre_fix_semantics_on_real_wage_chain': chain_pre,
        'post_fix_on_real_wage_chain': chain_post,
    }
    check('B4_pre_fix_chain_locks_old_price',
          chain_pre['import_reading']['process_id'] == ids['old']
          and chain_pre['wage_reading']['process_id'] == ids['old'],
          chain_pre)
    check('B4_post_fix_chain_locks_new_price',
          chain_post['import_reading']['process_id'] == ids['new']
          and chain_post['wage_reading']['process_id'] == ids['new'],
          chain_post)
    pre_amount = chain_pre['wage_reading']['piecework_amount']
    post_amount = chain_post['wage_reading']['piecework_amount']
    res['B4_wage_chain']['piecework_delta'] = (
        None if pre_amount is None or post_amount is None else float(post_amount - pre_amount))
    check('B4_wage_delta_is_price_diff_times_qty',
          res['B4_wage_chain']['piecework_delta'] == 20.0,
          res['B4_wage_chain']['piecework_delta'])

    # ---------- B5 schema / 真库 ----------
    real_after = sha256(REAL_DB)
    res['real_db_sha256_after'] = real_after
    res['B5_real_db_unchanged'] = (real_after == real_before)
    check('B5_real_db_sha256_unchanged', real_after == real_before)
    real_objs = db_objects(REAL_DB)
    copy_objs = db_objects(copy_path)
    res['B5_schema'] = {'real_object_count': len(real_objs), 'copy_object_count': len(copy_objs),
                        'identical': real_objs == copy_objs}
    check('B5_schema_identical', real_objs == copy_objs)

    res['routes_py_sha256_at_probe_end'] = sha256(ROUTES_PY)
    res['routes_py_modified_during_probe'] = (
        res['routes_py_sha256_at_probe_end'] != res['routes_py_sha256_at_probe_start'])
    res['checks'] = {'failure_count': len(FAILURES), 'failures': FAILURES}

    OUT_JSON.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in res.items()
                      if k.startswith(('real_db', 'B5', 'routes_py'))}, ensure_ascii=False, indent=2))
    print('\nB1 三处调用点：')
    print(json.dumps(res['B1_current']['sites'], ensure_ascii=False, indent=2))
    print('\nB1 全文件 ProcessPrice.query 命中（line→函数）：',
          res['B1_current']['module_ProcessPrice_query_hits'])
    print('B2 all_three_equal =', b2['all_three_equal'], got)
    print('B3 tolerance =', json.dumps(b3['tolerance_boundary'], ensure_ascii=False))
    print('B3 strict-future-within-tolerance =',
          json.dumps(b3['strict_future_within_1day_tolerance'], ensure_ascii=False))
    print('B4 单价/计件：修前 process_id=%s 单价=%s 计件=%s | 修后 process_id=%s 单价=%s 计件=%s | delta=%s'
          % (chain_pre['wage_reading']['process_id'], chain_pre['wage_reading']['unit_price'],
             chain_pre['wage_reading']['piecework_amount'], chain_post['wage_reading']['process_id'],
             chain_post['wage_reading']['unit_price'], chain_post['wage_reading']['piecework_amount'],
             res['B4_wage_chain']['piecework_delta']))
    print('output ->', OUT_JSON)
    print('FAILED_CHECKS =', len(FAILURES))
    if FAILURES:
        print('RESULT: FAIL')
        return 1
    print('RESULT: OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
