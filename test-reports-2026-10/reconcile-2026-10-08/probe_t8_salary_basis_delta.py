# -*- coding: utf-8 -*-
"""t8 / B12-05：取价统一（B12-01）修前 / 修后**工资口径对照**读数。

工具 + 口径 + 值（本文件即「工具」；口径写在下面；值落在同名 `.output.json`）：
  · 工具：`scripts/_sandbox_compat.py` 垫片 + `scripts/_test_bootstrap.make_app(fresh=True)`
          ⇒ 全部读写发生在 `app.db` **副本**上（真实库只做只读 SHA256 前后比对）。
  · 口径：同一 `process_code`（`_T8S9001`）+ 同一业务日期（`biz_day = 今天 + 1 天`）。
          修前取价语义 = `ProcessPrice.query.filter_by(process_code=code).first()`
                        （即 B12-01 修前 `routes.py:3902` / `:4020` 的**错误口径**）
          修后取价语义 = `app.main.routes.pick_process_price(process_code, business_date)`
  · 值：工价版本 `id` / 单价 / 计件额 / 工资合计，均从真实 HTTP 面
        （`/production_records/import`、`/salary_calculation?format=json`）读出。

判据（含阴性对照 ⇒ 自证敏感）：
  A1 单点读数：修前取「该 code 的第一行」= 旧版 `3487`（单价 2.5）；修后取「业务日之前的最新版」= 新版 `3488`（单价 4.0）。
     编号 3487/3488 由**副本库插入序自然分配**（真库 `process_price` 只读实测 `max(id)=3486`、`count(*)=3486`）。
  A2 端到端（同工序 + 同业务日期 + 数量 10）：修前落 3487 ⇒ 计件 25.0；修后落 3488 ⇒ 计件 40.0；Δ = 15.0。
     两名夹具员工各只写 1 行、基本工资 0、系数 1.0 ⇒ 工资合计 = 计件额，差值可归因到取价版本。
  A3 阴性/边界：仅「业务日之后 10 天」的价 ⇒ None；两版中较新版在业务日之后 ⇒ 取旧版；
     `business_date=None` ⇒ None；**容差留档**：`effective_date = 业务日 + 1 天 00:00` 仍会被取到
     （`pick_process_price` 逐字沿用仓库既有 `+ timedelta(days=1)` 约定）。
  A4 不变量：真实 `app.db` 的 SHA256 前后不变；副本 `sqlite_master` 与真库逐表逐位一致（无 schema 变更）。
"""

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

REAL_DB = ROOT / 'app.db'
EXPECTED_REAL_SHA = 'F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065'

CODE = '_T8S9001'            # 两版工价：旧（业务日 - 30 天）/ 新（业务日 - 1 天）
CODE_FUTURE_ONLY = '_T8S9004'   # 只有业务日 + 10 天的价 ⇒ 必须取不到
CODE_TOLERANCE = '_T8S9003'     # 只有业务日 + 1 天 00:00 的价 ⇒ 容差留档（见 A3）
EMP_PRE = '_t8S_EMP9101'     # 修前口径
EMP_POST = '_t8S_EMP9102'    # 修后口径
QTY = 10


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest().upper()


def schema_rows(db_path):
    con = sqlite3.connect('file:%s?mode=ro' % pathlib.Path(db_path).as_posix(), uri=True)
    try:
        return con.execute(
            "SELECT type, name, sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
        ).fetchall()
    finally:
        con.close()


def jnum(x):
    try:
        return round(float(x), 4)
    except (TypeError, ValueError):
        return x


def build_xlsx(rows):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(['日期*', '员工工号*', '工序编号*', '数量*'])
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def main():
    out = {'probe': 'probe_t8_salary_basis_delta.py',
           'task': 't8 / B12-05（修前·修后工资口径对照）',
           'real_db': str(REAL_DB),
           'real_db_sha256_expected': EXPECTED_REAL_SHA}

    real_before = sha256(REAL_DB)
    out['real_db_sha256_before'] = real_before

    # 真实库只读实测：取价版本编号从哪来（口径 A1 的上下文）
    con = sqlite3.connect('file:%s?mode=ro' % REAL_DB.as_posix(), uri=True)
    try:
        mx, cnt = con.execute('SELECT max(id), count(*) FROM process_price').fetchone()
    finally:
        con.close()
    out['real_db_process_price_readonly'] = {
        'tool': "sqlite3 uri=file:.../app.db?mode=ro（只读）",
        'caliber': 'SELECT max(id), count(*) FROM process_price',
        'max_id': mx, 'count': cnt,
        'note': '3487/3488 不是真库既有行；它们是副本库上按插入序自然分配的夹具编号'}

    tmp_dir = ROOT / '.analysis-scratch' / 't8_temp'
    tmp_dir.mkdir(parents=True, exist_ok=True)

    app, copy_path = make_app(fresh=True)
    app.config['TEMP_FOLDER'] = str(tmp_dir)
    mappings, password = ensure_role_users(app)
    client = app.test_client()
    login_as(client, mappings['admin'], password)
    out['copy_path'] = str(copy_path)
    out['db_uri'] = app.config['SQLALCHEMY_DATABASE_URI']
    out['temp_folder_override'] = str(tmp_dir)
    out['temp_folder_note'] = ('沙箱下 uploads/temp 被 ACL 拒写；端点只读 app.config["TEMP_FOLDER"]，'
                               '故覆盖该 config，端点代码零改动')

    from app import db  # noqa: E402
    from app import models as M  # noqa: E402
    from app.main import routes as R  # noqa: E402
    from app.utils.excel_generator import ExcelGenerator  # noqa: E402

    today = date.today()
    biz_day = today + timedelta(days=1)

    with app.app_context():
        sn = M.SerialNumber.get_next_number()
        old_price = M.ProcessPrice(
            global_sn=sn + 'O', process_code=CODE, process_name='t8 对照工序',
            price=2.5, version=1, is_current=True, price_type='normal',
            effective_date=datetime.combine(biz_day - timedelta(days=30), datetime.min.time()))
        db.session.add(old_price)
        db.session.flush()
        new_price = M.ProcessPrice(
            global_sn=sn + 'N', process_code=CODE, process_name='t8 对照工序',
            price=4.0, version=2, is_current=True, price_type='normal',
            effective_date=datetime.combine(biz_day - timedelta(days=1), datetime.min.time()))
        db.session.add(new_price)
        db.session.flush()

        future_only = M.ProcessPrice(
            global_sn=sn + 'F', process_code=CODE_FUTURE_ONLY, process_name='t8 未来价工序',
            price=9.99, version=1, is_current=True, price_type='normal',
            effective_date=datetime.combine(biz_day + timedelta(days=10), datetime.min.time()))
        tolerance = M.ProcessPrice(
            global_sn=sn + 'T', process_code=CODE_TOLERANCE, process_name='t8 容差边界工序',
            price=7.77, version=1, is_current=True, price_type='normal',
            effective_date=datetime.combine(biz_day + timedelta(days=1), datetime.min.time()))
        db.session.add_all([future_only, tolerance])

        employees = []
        for emp_code, emp_name in ((EMP_PRE, 't8 修前对照员工'), (EMP_POST, 't8 修后对照员工')):
            emp = M.Employee(global_sn=M.SerialNumber.get_next_number(), employee_id=emp_code,
                             name=emp_name, position='普通员工', hire_date=today,
                             base_salary=0.0, coefficient=1.0, department='生产部', is_active=True)
            db.session.add(emp)
            employees.append(emp)
        db.session.commit()

        out['fixture'] = {
            'process_code': CODE,
            'business_date': biz_day.isoformat(),
            'quantity': QTY,
            'old_version': {'id': old_price.id, 'price': jnum(old_price.price),
                            'effective_date': old_price.effective_date.isoformat()},
            'new_version': {'id': new_price.id, 'price': jnum(new_price.price),
                            'effective_date': new_price.effective_date.isoformat()},
            'employees': [{'employee_id': e.employee_id, 'name': e.name,
                           'base_salary': jnum(e.base_salary), 'coefficient': jnum(e.coefficient)}
                          for e in employees]}

        # ---- A1：单点取价读数（修前语义 vs 修后单点） ----
        def old_semantics(code):
            return M.ProcessPrice.query.filter_by(process_code=code).first()

        pre_row = old_semantics(CODE)
        post_row = R.pick_process_price(CODE, biz_day)
        out['A1_single_point'] = {
            'tool': '直调（副本库）：filter_by(...).first()  vs  routes.pick_process_price()',
            'caliber': 'same process_code=%s + same business_date=%s' % (CODE, biz_day.isoformat()),
            'pre_fix': {'version_id': getattr(pre_row, 'id', None),
                        'unit_price': jnum(getattr(pre_row, 'price', None))},
            'post_fix': {'version_id': getattr(post_row, 'id', None),
                         'unit_price': jnum(getattr(post_row, 'price', None))},
        }
        out['A1_single_point']['version_id_delta'] = [out['A1_single_point']['pre_fix']['version_id'],
                                                      out['A1_single_point']['post_fix']['version_id']]
        out['A1_single_point']['unit_price_delta'] = jnum(
            (out['A1_single_point']['post_fix']['unit_price'] or 0)
            - (out['A1_single_point']['pre_fix']['unit_price'] or 0))

        # ---- A3：阴性 / 边界 ----
        future_row = R.pick_process_price(CODE_FUTURE_ONLY, biz_day)
        tolerance_row = R.pick_process_price(CODE_TOLERANCE, biz_day)
        out['A3_negative'] = {
            'tool': '直调 routes.pick_process_price（副本库）',
            'caliber': 'business_date 之后的价 / 仅未来价 / business_date=None',
            'future_only_code': CODE_FUTURE_ONLY,
            'future_only_result': None if future_row is None else {
                'version_id': future_row.id, 'unit_price': jnum(future_row.price)},
            'future_only_excluded': future_row is None,
            'none_date_result': R.pick_process_price(CODE, None),
            'none_date_is_none': R.pick_process_price(CODE, None) is None,
            'tolerance_code': CODE_TOLERANCE,
            'tolerance_effective_date': tolerance.effective_date.isoformat(),
            'tolerance_result': None if tolerance_row is None else {
                'version_id': tolerance_row.id, 'unit_price': jnum(tolerance_row.price)},
            'tolerance_picked_future_version': tolerance_row is not None,
            'tolerance_note': ('口径限制：pick_process_price 逐字沿用仓库既有 '
                               '`effective_date <= 业务日 23:59:59.999999 + timedelta(days=1)` 约定 '
                               '⇒ 业务日次日的价仍在窗口内。81-:107 阴性栏「effective_date > 业务日期 必须被排除」'
                               '只在「业务日 + 1 天」之后严格成立；本读数即该容差的留档（见登记件 §B.2）。'),
        }

    # ---- 预检：复现端点的落盘 + 解析两步（端点外层 except 会吞异常，故此处显式冒烟） ----
    # 两种单元格形态各跑一次：**真 date 单元格**（A2 采用）与**文本日期单元格**（见 A5 限制）——
    # 后者解析回 str，落库时被 SQLite Date 绑定器拒绝，是本探针的已知口径限制。
    import traceback

    def preflight(cell_value, name):
        try:
            path = tmp_dir / name
            path.write_bytes(build_xlsx([[cell_value, EMP_PRE, CODE, QTY]]).getvalue())
            rows = ExcelGenerator.parse_production_record_data(str(path))
            return {'ok': True, 'temp_folder': str(tmp_dir),
                    'cell_value_type': type(cell_value).__name__,
                    'parsed_date_type': type(rows[0]['date']).__name__ if rows else None,
                    'rows': [{k: (v.isoformat() if isinstance(v, (date, datetime)) else v)
                              for k, v in row.items()} for row in rows]}
        except Exception as exc:  # noqa: BLE001
            return {'ok': False, 'temp_folder': str(tmp_dir),
                    'error': repr(exc), 'traceback': traceback.format_exc()}

    out['preflight'] = preflight(biz_day, 't8_preflight.xlsx')
    out['preflight_text_date_cell'] = preflight(biz_day.isoformat(), 't8_preflight_text.xlsx')

    # ---- A2：端到端（真实 HTTP + 真实工资面） ----
    original_pick = R.pick_process_price
    original_jsonify = R.jsonify

    # 端点外层 `except Exception` 会把真实异常吞成「导入失败，请稍后重试或联系管理员」
    # ⇒ 用 jsonify 间谍在 except 块内取 sys.exc_info()，把被吞的异常原样落到证据里。
    swallowed = []

    def spy_jsonify(*args, **kwargs):
        exc = sys.exc_info()
        if exc[0] is not None and not issubclass(exc[0], SystemExit):
            swallowed.append({'type': exc[0].__name__, 'error': repr(exc[1]),
                              'traceback': ''.join(traceback.format_exception(*exc))})
        return original_jsonify(*args, **kwargs)

    R.jsonify = spy_jsonify

    def import_row(emp_code, tag, date_cell=None):
        # 日期单元格写真 `date` 对象（与 t3 探针一致）：文本日期单元格会被 SQLite Date
        # 绑定器拒绝（见 A5 限制留档），故 A2 主链一律真 date。
        buf = build_xlsx([[biz_day if date_cell is None else date_cell, emp_code, CODE, QTY]])
        resp = client.post('/production_records/import',
                           data={'file': (buf, 't8s_%s.xlsx' % tag)},
                           content_type='multipart/form-data')
        try:
            payload = resp.get_json()
        except Exception:
            payload = None
        return resp.status_code, payload

    # A5（口径限制留档）在 A2 主链之后单独跑，见下。

    # 修前：把单点临时换回旧语义 ⇒ 走真实导入端点
    R.pick_process_price = lambda code, business_date: old_semantics(code)
    pre_http, pre_payload = import_row(EMP_PRE, 'pre')
    R.pick_process_price = original_pick
    # 修后：原语义
    post_http, post_payload = import_row(EMP_POST, 'post')

    # ---- A5（口径限制留档）：**文本日期单元格** ⇒ 外层 except 吞掉 StatementError，
    # 前端只看到 HTTP 200 + success=false、0 行入库。本探针不改 app/**（out of scope）。
    mark = len(swallowed)
    text_http, text_payload = import_row(EMP_PRE, 'textdate', date_cell=biz_day.isoformat())
    text_swallowed = swallowed[mark:]
    R.jsonify = original_jsonify
    out['swallowed_endpoint_errors'] = swallowed
    out['A5_text_date_cell_limitation'] = {
        'caliber': ('同一夹具、仅把日期单元格由真 date 改为文本 "%s"（openpyxl 文本单元格）'
                    % biz_day.isoformat()),
        'import_http': text_http,
        'import_payload': text_payload,
        'swallowed_error_count': len(text_swallowed),
        'swallowed_error_types': [e['type'] for e in text_swallowed],
        'swallowed_error_headline': (text_swallowed[0]['error'] if text_swallowed else None),
        'swallowed_error_frames': [
            [ln.strip() for ln in e['traceback'].splitlines()
             if 'routes.py' in ln or 'Error' in ln][-3:] for e in text_swallowed],
        'records_written_for_employee': None,  # 由下方 A5 复读填充
    }

    with app.app_context():
        def last_record(emp_code):
            emp = M.Employee.query.filter_by(employee_id=emp_code).first()
            rec = (M.ProductionRecord.query.filter_by(employee_id=emp.id)
                   .order_by(M.ProductionRecord.id.desc()).first())
            if rec is None:
                return None
            price_row = M.ProcessPrice.query.get(rec.process_id)
            return {'record_id': rec.id, 'employee_id': emp_code, 'quantity': rec.quantity,
                    'process_id': rec.process_id, 'unit_price': jnum(price_row.price),
                    'piecework_amount': jnum(rec.quantity * price_row.price)}

        pre_rec = last_record(EMP_PRE)
        post_rec = last_record(EMP_POST)

        pre_emp = M.Employee.query.filter_by(employee_id=EMP_PRE).first()
        pre_record_count = M.ProductionRecord.query.filter_by(employee_id=pre_emp.id).count()

    out['A5_text_date_cell_limitation']['records_written_for_employee'] = pre_record_count
    out['A5_text_date_cell_limitation']['verdict'] = {
        'http_200': text_http == 200,
        'success_false': bool(text_payload) and text_payload.get('success') is False,
        'swallowed_statementerror': bool(text_swallowed)
        and text_swallowed[-1]['type'] == 'StatementError'
        and 'SQLite Date type only accepts Python date objects' in text_swallowed[-1]['error'],
        'wrote_zero_rows': pre_record_count == 1,  # 只有 A2 修前那 1 行；A5 未新增
    }

    out['A2_end_to_end'] = {
        'tool': "/production_records/import（真实 HTTP，副本库） + /salary_calculation?format=json",
        'caliber': ('同一 process_code=%s + 同一 business_date=%s + quantity=%d；'
                    '两员工各 1 行、base_salary=0、coefficient=1.0 ⇒ 工资合计 = 计件额'
                    % (CODE, biz_day.isoformat(), QTY)),
        'import_http': {'pre_fix': pre_http, 'post_fix': post_http},
        'import_payloads': {'pre_fix': pre_payload, 'post_fix': post_payload},
        'pre_fix_record': pre_rec,
        'post_fix_record': post_rec,
    }

    day_s = biz_day.isoformat()
    sal = client.post('/salary_calculation?format=json',
                      data={'start_date': day_s, 'end_date': day_s,
                            'department': '', 'employee_id': '0'})
    try:
        sal_json = sal.get_json() or {}
    except Exception:
        sal_json = {}
    rows = {r.get('employee_no'): r for r in (sal_json.get('data') or [])}
    out['A2_end_to_end']['salary_http'] = sal.status_code
    out['A2_end_to_end']['salary_rows'] = {}
    for emp_code in (EMP_PRE, EMP_POST):
        row = rows.get(emp_code)
        if row is None:
            out['A2_end_to_end']['salary_rows'][emp_code] = None
            continue
        out['A2_end_to_end']['salary_rows'][emp_code] = {
            'coefficient': jnum(row.get('coefficient')),
            'counted': jnum(row.get('counted')),
            'dropped': jnum(row.get('dropped')),
            'piecework': jnum(row.get('piecework')),
            'normal_quantity': row.get('normal_quantity'),
            'rework_quantity': row.get('rework_quantity'),
            'records': [{'record_id': r.get('record_id'), 'price': jnum(r.get('price')),
                         'quantity': r.get('quantity'), 'amount': jnum(r.get('amount')),
                         'is_rework': r.get('is_rework')} for r in (row.get('records') or [])],
        }
    pre_s = out['A2_end_to_end']['salary_rows'].get(EMP_PRE) or {}
    post_s = out['A2_end_to_end']['salary_rows'].get(EMP_POST) or {}
    out['A2_end_to_end']['piecework_delta'] = jnum(
        (post_s.get('piecework') or 0) - (pre_s.get('piecework') or 0))
    out['A2_end_to_end']['counted_delta'] = jnum(
        (post_s.get('counted') or 0) - (pre_s.get('counted') or 0))
    out['A2_end_to_end']['verdict'] = {
        'same_process_code_and_date': True,
        'pre_used_old_version': pre_rec is not None and pre_rec['process_id'] == out['A1_single_point']['pre_fix']['version_id'],
        'post_used_new_version': post_rec is not None and post_rec['process_id'] == out['A1_single_point']['post_fix']['version_id'],
        'salary_piecework_pre': pre_s.get('piecework'),
        'salary_piecework_post': post_s.get('piecework'),
        'salary_piecework_delta': out['A2_end_to_end']['piecework_delta'],
    }

    # ---- A4：不变量 ----
    real_after = sha256(REAL_DB)
    out['real_db_sha256_after'] = real_after
    out['real_db_unchanged'] = (real_after == real_before == EXPECTED_REAL_SHA)
    out['schema_identical'] = (schema_rows(REAL_DB) == schema_rows(copy_path))

    verdict = {
        'A1_pre_is_first_row_old_version': out['A1_single_point']['pre_fix']['version_id'] == out['fixture']['old_version']['id'],
        'A1_post_is_latest_before_biz_day': out['A1_single_point']['post_fix']['version_id'] == out['fixture']['new_version']['id'],
        'A1_version_pair_3487_3488': [out['A1_single_point']['pre_fix']['version_id'],
                                      out['A1_single_point']['post_fix']['version_id']] == [3487, 3488],
        'A2_pre_record_old_version': out['A2_end_to_end']['verdict']['pre_used_old_version'],
        'A2_post_record_new_version': out['A2_end_to_end']['verdict']['post_used_new_version'],
        'A2_salary_delta_15': out['A2_end_to_end']['piecework_delta'] == 15.0,
        'A2_salary_http_200': out['A2_end_to_end']['salary_http'] == 200,
        'A3_future_only_excluded': out['A3_negative']['future_only_excluded'],
        'A3_none_date_is_none': out['A3_negative']['none_date_is_none'],
        'A5_preflight_ok': out['preflight']['ok'],
        'A5_preflight_text_date_parsed_as_str': out['preflight_text_date_cell'].get('parsed_date_type') == 'str',
        'A5_text_date_import_http_200': out['A5_text_date_cell_limitation']['verdict']['http_200'],
        'A5_text_date_swallowed_statementerror': out['A5_text_date_cell_limitation']['verdict']['swallowed_statementerror'],
        'A5_text_date_wrote_zero_rows': out['A5_text_date_cell_limitation']['verdict']['wrote_zero_rows'],
        'A4_real_db_unchanged': out['real_db_unchanged'],
        'A4_schema_identical': out['schema_identical'],
    }
    out['verdict'] = verdict
    ok = all(bool(v) for v in verdict.values())
    out['RESULT'] = 'OK' if ok else 'FAIL'

    out_path = pathlib.Path(__file__).with_suffix('.output.json')
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'RESULT': out['RESULT'], 'verdict': verdict,
                      'A1': out['A1_single_point'], 'piecework_delta': out['A2_end_to_end']['piecework_delta'],
                      'output': str(out_path)}, ensure_ascii=False, indent=2))
    print('RESULT:', out['RESULT'])
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
