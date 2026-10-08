# -*- coding: utf-8 -*-
"""t3 补充证据：取价统一后「同一条业务数据」的取价版本 vs 修前版本对照读数。

81-后续开发与测试规划.md:131 风险① 要求「先出『修前 3487 / 修后 3488 同一条数据』的
对照读数，再上线」。本脚本在 app.db 副本上造同一条生产记录导入夹具（同一 process_code、
同一业务日期），分别用：
  修前 :3902/:4020 口径 = ProcessPrice.query.filter_by(process_code=...).first()
  统一口径 pick_process_price(process_code, business_date)
解析，并给出各自会写进 ProductionRecord.process_id / 计件单价的读数。

只用副本库；真实 app.db 只读。
用法：python -B scripts/_sandbox_compat.py test-reports-2026-10/reconcile-2026-10-08/probe_t3_salary_delta.py
"""
import hashlib
import io
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

from _test_bootstrap import ensure_role_users, login_as, make_app  # noqa: E402

REAL_DB = ROOT / 'app.db'
REAL_SHA_EXPECT = 'F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065'
EMP_TEST = '_t3S_EMP9001'
CODE = '_T3S9001'


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest().upper()


def main():
    from datetime import date, datetime, timedelta

    result = {'real_db_sha256_before': sha256(REAL_DB),
              'real_db_sha256_expected': REAL_SHA_EXPECT}

    app, copy_path = make_app(fresh=True)
    result['db_copy_path'] = copy_path
    result['db_uri'] = app.config['SQLALCHEMY_DATABASE_URI']
    scratch = ROOT / '.analysis-scratch' / 't3_temp'
    scratch.mkdir(parents=True, exist_ok=True)
    app.config['TEMP_FOLDER'] = str(scratch)

    mappings, pw = ensure_role_users(app)

    from app import db
    from app.models import Employee, ProcessPrice, ProductionRecord, SerialNumber

    today = date.today()
    biz_day = today + timedelta(days=1)
    with app.app_context():
        emp = Employee.query.filter_by(employee_id=EMP_TEST).first()
        if emp is None:
            emp = Employee(global_sn=SerialNumber.get_next_number(), employee_id=EMP_TEST,
                           name='_t3s_对照员工', position='普通员工', hire_date=today)
            db.session.add(emp)
            db.session.flush()
        eff_old = datetime.combine(today - timedelta(days=30), datetime.min.time())
        eff_new = datetime.combine(today - timedelta(days=1), datetime.min.time())
        if not ProcessPrice.query.filter_by(process_code=CODE).first():
            for price, eff, nm in ((2.5, eff_old, '_t3s_旧版工价'),
                                   (4.0, eff_new, '_t3s_新版工价')):
                db.session.add(ProcessPrice(
                    global_sn=SerialNumber.get_next_number(), process_code=CODE,
                    process_name=nm, price=price, version=1, effective_date=eff,
                    is_current=True, price_type='normal'))
            db.session.commit()
        rows = ProcessPrice.query.filter_by(process_code=CODE).order_by(
            ProcessPrice.id).all()
        old_id, old_price = rows[0].id, float(rows[0].price)
        new_id, new_price = rows[1].id, float(rows[1].price)

    import app.main.routes as routes_mod

    def old_semantics(code):
        return ProcessPrice.query.filter_by(process_code=code).first()

    # 直接读数（同一夹具 + 同一业务日期）
    with app.app_context():
        before = old_semantics(CODE)
        after = routes_mod.pick_process_price(CODE, biz_day)
        result['same_fixture_reading'] = {
            'process_code': CODE,
            'business_date': biz_day.isoformat(),
            'pre_fix_semantics': {'source': 'ProcessPrice.query.filter_by(process_code).first()',
                                  'process_price_id': before.id,
                                  'unit_price': float(before.price)},
            'after_fix_semantics': {'source': 'pick_process_price(process_code, business_date)',
                                    'process_price_id': after.id,
                                    'unit_price': float(after.price)},
            'price_changed': float(before.price) != float(after.price),
            'delta_per_unit': float(after.price) - float(before.price),
        }

    # 端到端：同一条导入夹具，修前(临时换旧语义) vs 修后 各写一次，读落库行
    client = app.test_client()
    login_as(client, mappings['admin'], pw)

    def post_import(tag):
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.append(['日期*', '员工工号*', '工序编号*', '数量*'])
        ws.append([biz_day, EMP_TEST, CODE, 10])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return client.post('/production_records/import',
                           data={'file': (buf, f't3s_{tag}.xlsx')},
                           content_type='multipart/form-data')

    original = routes_mod.pick_process_price
    routes_mod.pick_process_price = lambda code, d: old_semantics(code)
    r_pre = post_import('pre')
    with app.app_context():
        row_pre = ProductionRecord.query.order_by(ProductionRecord.id.desc()).first()
        pre = {'record_id': row_pre.id, 'process_id': row_pre.process_id,
               'quantity': row_pre.quantity} if row_pre else None
    routes_mod.pick_process_price = original
    r_post = post_import('post')
    with app.app_context():
        row_post = ProductionRecord.query.order_by(ProductionRecord.id.desc()).first()
        post = {'record_id': row_post.id, 'process_id': row_post.process_id,
                'quantity': row_post.quantity} if row_post else None
        pp_pre = ProcessPrice.query.get(pre['process_id']) if pre else None
        pp_post = ProcessPrice.query.get(post['process_id']) if post else None

    result['end_to_end_same_row'] = {
        'quantity': 10,
        'pre_fix_import': dict(pre or {}, http_status=r_pre.status_code,
                               unit_price=float(pp_pre.price) if pp_pre else None,
                               piecework_amount=(float(pp_pre.price) * 10) if pp_pre else None),
        'after_fix_import': dict(post or {}, http_status=r_post.status_code,
                                 unit_price=float(pp_post.price) if pp_post else None,
                                 piecework_amount=(float(pp_post.price) * 10) if pp_post else None),
        'expected_old_id': old_id, 'expected_new_id': new_id,
        'pre_fix_wrote_old_version': bool(pre and pre['process_id'] == old_id),
        'after_fix_wrote_new_version': bool(post and post['process_id'] == new_id),
        'piecework_amount_delta': ((float(pp_post.price) - float(pp_pre.price)) * 10)
        if (pp_pre and pp_post) else None,
        'unit_price_delta': (float(pp_post.price) - float(pp_pre.price))
        if (pp_pre and pp_post) else None,
    }

    result['real_db_sha256_after'] = sha256(REAL_DB)
    result['real_db_unchanged'] = result['real_db_sha256_after'] == result['real_db_sha256_before']

    import sqlite3
    schema_q = ("SELECT type, name, sql FROM sqlite_master "
                "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name")

    def schema_of(db_file):
        con = sqlite3.connect(db_file)
        try:
            return con.execute(schema_q).fetchall()
        finally:
            con.close()

    result['schema_identical'] = schema_of(str(REAL_DB)) == schema_of(copy_path)

    out_path = pathlib.Path(__file__).with_suffix('.output.json')
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=True, indent=1))

    ok = (result['same_fixture_reading']['price_changed']
          and result['same_fixture_reading']['pre_fix_semantics']['process_price_id'] == old_id
          and result['same_fixture_reading']['after_fix_semantics']['process_price_id'] == new_id
          and result['end_to_end_same_row']['pre_fix_wrote_old_version']
          and result['end_to_end_same_row']['after_fix_wrote_new_version']
          and result['real_db_unchanged']
          and result['schema_identical']
          and result['real_db_sha256_after'] == REAL_SHA_EXPECT)
    print('RESULT:', 'OK' if ok else 'FAIL')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
