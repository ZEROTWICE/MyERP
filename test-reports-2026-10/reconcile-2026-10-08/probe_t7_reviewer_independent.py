"""B12-03 非作者独立评审探针（t7 reviewer = verifier，t2 作者 = mes-dev）。

目标：不采信 t2 的 output.json，在 app.db 副本上自行复跑
  ① 报工路径（production_record 来源 / workpiece_id IS NULL）报废的 scrap 库存台账「按件数」
     阴阳对照：阴 = 把 mes_service.inbound_production_scrap 临时替换为 no-op（等价 t2 之前的代码
     —— 报废分支没有 else 支），阳 = 保持当前实现；两态都走真实端点
     POST /api/quality/nonconformities/<id>/dispose。
  ② 有工件路径（workpiece_id 非空）回归：台账「件数」不得由 1 变 0；wp.status='scrap'；
     WorkpieceEvent('scrap') payload 仍为 {nc_id, scrap_cost, pieces}。
  ③ 静态核验：冻结口径行逐字未变 / app/ 改动为纯新增 / app/__init__.py 零 diff。
  ④ 真库 app.db SHA256 前后不变。

环境纪律：只用 app.db 副本（scripts/_test_bootstrap.make_app()，内置副本 URI 闸）；
  必须经 `python -B scripts/_sandbox_compat.py <本脚本>` 运行（脚本内 mkdtemp 直跑会被沙箱拒写）。
"""
import hashlib
import json
import os
import pathlib
import subprocess
import sys
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

REAL_DB = ROOT / 'app.db'
REAL_SHA_BEFORE = hashlib.sha256(REAL_DB.read_bytes()).hexdigest().upper()
EXPECT_SHA = 'F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065'

OUT = {}
VERDICTS = []


def v(name, ok, detail):
    VERDICTS.append({'id': name, 'ok': bool(ok), 'detail': detail})
    print(('[OK] ' if ok else '[NG] ') + name + ' | ' + str(detail)[:400])


def real_sha():
    return hashlib.sha256(REAL_DB.read_bytes()).hexdigest().upper()


def static_checks():
    src = (ROOT / 'app/services/mes_service.py').read_text(encoding='utf-8')
    lines = src.splitlines()
    want = 'allowed, reason = qc_gate_allows_output(batch_item=item, workpieces=workpieces)'
    gate = [(i + 1, l) for i, l in enumerate(lines) if 'qc_gate_allows_output(batch_item=item' in l]
    OUT['frozen_gate'] = {'hits': [n for n, _ in gate],
                          'text': gate[0][1].strip() if gate else None}
    v('S1_frozen_gate_line_verbatim_once',
      len(gate) == 1 and gate[0][1].strip() == want, OUT['frozen_gate'])

    d = [(i + 1, l) for i, l in enumerate(lines) if l.startswith('def inbound_production_scrap(')]
    c = [(i + 1, l) for i, l in enumerate(lines)
         if 'inbound_production_scrap(' in l and not l.startswith('def ')]
    OUT['def_line'] = d[0][0] if d else None
    OUT['call_lines'] = [n for n, _ in c]
    v('S2_def_once_and_single_call_site', len(d) == 1 and len(c) == 1,
      {'def': d[0] if d else None, 'calls': [(n, t.strip()) for n, t in c]})

    body = '\n'.join(lines[(d[0][0] - 1):(d[0][0] + 70)]) if d else ''
    OUT['body'] = {k: (k in body) for k in ("stock_kind='scrap'", "status='scrapped'",
                                            'quantity=', 'nc_id', '#{nc_id}',
                                            'workpiece_id=None')}
    v('S3_new_func_writes_scrap_row_with_nc_backref',
      all(OUT['body'].values()), OUT['body'])

    ns = subprocess.run(['git', 'diff', '--numstat', '--', 'app/'], cwd=str(ROOT),
                        capture_output=True, text=True, encoding='utf-8', errors='replace')
    rows = [l.split('\t') for l in ns.stdout.splitlines() if l.strip()]
    OUT['app_numstat'] = rows
    deletions = {r[2].strip(): int(r[1]) for r in rows}
    OUT['deletions'] = {k: deletions[k] for k in sorted(deletions)}
    own = [k for k in deletions if k.endswith('app/services/mes_service.py')]
    OUT['b12_03_file_deletions'] = {k: deletions[k] for k in own}
    v('S4_reviewed_file_deletions_zero_pure_insertion',
      own != [] and all(deletions[k] == 0 for k in own),
      {'b12_03_file': OUT['b12_03_file_deletions'],
       'all_touched_files': OUT['deletions'],
       'note': 'B12-03 唯一受改动文件 app/services/mes_service.py 删除行 = 0（纯新增）；'
               '同批其余文件的删除行（routes.py 20 / salary_calculation.html 2 / '
               'excel_generator.py 1）分别属 B12-01/04 取价改写、B12-04 明细页与 B12-02 '
               'notes 修复，不属本次评审对象、只登记不判'})

    ns2 = subprocess.run(['git', 'diff', '--numstat', '--', 'app/__init__.py'], cwd=str(ROOT),
                         capture_output=True, text=True, encoding='utf-8', errors='replace')
    OUT['app_init_numstat'] = ns2.stdout.strip()
    v('S5_app_init_zero_diff', ns2.stdout.strip() == '', {'numstat': ns2.stdout.strip()})


def build_scaffold(app, M, db):
    tag = '_t7v'
    with app.app_context():
        emp = M.Employee.query.filter_by(employee_id=tag + '_EMP1').first()
        if emp is None:
            emp = M.Employee(global_sn=M.SerialNumber.get_next_number(),
                             employee_id=tag + '_EMP1', name='_t7v 评审员工',
                             position='操作工', hire_date=date(2024, 1, 1))
            db.session.add(emp)
            db.session.commit()
        prod = M.Product.query.filter_by(product_code=tag + '_P1').first()
        if prod is None:
            prod = M.Product(global_sn=M.SerialNumber.get_next_number(),
                             product_code=tag + '_P1', product_name='_t7v 产品')
            db.session.add(prod)
            db.session.commit()
        order = M.ProductionOrder(global_sn=M.SerialNumber.get_next_number(),
                                  product_id=prod.id, planned_quantity=100,
                                  planned_start_date=date(2026, 10, 1),
                                  planned_end_date=date(2026, 12, 31))
        db.session.add(order)
        db.session.commit()
        batch = M.ProductionBatch(global_sn=M.SerialNumber.get_next_number(),
                                  production_order_id=order.id, batch_quantity=10)
        db.session.add(batch)
        db.session.commit()
        pp = M.ProcessPrice.query.first()
        return {'tag': tag, 'emp_id': emp.id, 'product_id': prod.id,
                'batch_id': batch.id, 'process_id': pp.id,
                'process_code': pp.process_code}


def make_nc(app, M, db, ctx, item_seq, qty=3):
    """造一张报工路径（workpiece_id 为空）的 open NC：实例 + 任务 + 报工 + 质检 fail + NC。"""
    with app.app_context():
        item = M.ProductionBatchItem(global_sn=M.SerialNumber.get_next_number(),
                                     batch_id=ctx['batch_id'], item_sequence=item_seq,
                                     product_code=f"_t7v_ITEM_{item_seq}", status='in_progress')
        db.session.add(item)
        db.session.commit()
        task = M.TaskAssignment(employee_id=ctx['emp_id'], process_id=ctx['process_id'],
                                target_date=date.today(), quantity=qty, status='pending',
                                task_type='auto', batch_item_id=item.id,
                                production_batch_id=ctx['batch_id'])
        db.session.add(task)
        db.session.commit()
        pr = M.ProductionRecord(employee_id=ctx['emp_id'], process_id=ctx['process_id'],
                                quantity=qty, date=date.today(),
                                notes=json.dumps({'batch_item_id': item.id}))
        db.session.add(pr)
        db.session.commit()
        it = M.InspectionTask(global_sn=M.SerialNumber.get_next_number(),
                              inspector_id=ctx['emp_id'], created_by=ctx['emp_id'],
                              target_type='production_record', target_id=pr.id,
                              status='completed')
        db.session.add(it)
        db.session.commit()
        ir = M.InspectionRecord(global_sn=M.SerialNumber.get_next_number(), task_id=it.id,
                                inspector_id=ctx['emp_id'],
                                inspection_date=date.today(), result='fail')
        db.session.add(ir)
        db.session.commit()
        nc = M.NonconformityRecord(record_id=ir.id, type='scrap', handler_id=ctx['emp_id'],
                                   handling_date=date.today(), handling_result='scrap',
                                   target_type='production_record', target_id=pr.id,
                                   status='open')
        db.session.add(nc)
        db.session.commit()
        return {'nc_id': nc.id, 'workpiece_id': nc.workpiece_id, 'item_id': item.id,
                'record_id': pr.id, 'task_id': task.id}


def scrap_sum(app, M, db):
    with app.app_context():
        pieces = float(db.session.query(db.func.coalesce(db.func.sum(M.FinishedProduct.quantity), 0))
                       .filter(M.FinishedProduct.stock_kind == 'scrap').scalar() or 0.0)
        rows = int(M.FinishedProduct.query.filter_by(stock_kind='scrap').count())
        return pieces, rows


def main():
    static_checks()

    from _test_bootstrap import make_app, ensure_role_users, login_as
    app, copy_path = make_app()
    from app import db
    from app import models as M
    from app.services import mes_service

    uri = app.config['SQLALCHEMY_DATABASE_URI']
    OUT['isolation'] = {'uri': uri, 'copy_path': copy_path,
                        'uri_on_copy': os.path.normcase(copy_path) in os.path.normcase(uri.replace('/', os.sep)),
                        'mes_service_file': mes_service.__file__}
    v('E0_running_on_db_copy', OUT['isolation']['uri_on_copy'], OUT['isolation'])

    ctx = build_scaffold(app, M, db)
    OUT['scaffold'] = ctx
    users, pw = ensure_role_users(app)
    client = app.test_client()
    r = login_as(client, f"_t_{'admin'}", pw)
    OUT['login_status'] = r.status_code
    v('E1_login_ok', r.status_code in (200, 302), {'status': r.status_code})

    real_func = mes_service.inbound_production_scrap

    # ---------------- 阴态：inbound_production_scrap -> no-op（等价修前）
    nc_b = make_nc(app, M, db, ctx, item_seq=911, qty=3)
    OUT['nc_before'] = nc_b
    p0, r0 = scrap_sum(app, M, db)
    mes_service.inbound_production_scrap = lambda **kw: None
    try:
        rb = client.post(f"/api/quality/nonconformities/{nc_b['nc_id']}/dispose",
                         json={'action': 'scrap', 'scrap_cost': 0, 'scrap_quantity': 3})
    finally:
        mes_service.inbound_production_scrap = real_func
    p1, r1 = scrap_sum(app, M, db)
    OUT['pre_fix'] = {'workpiece_id': nc_b['workpiece_id'], 'http': rb.status_code,
                      'body': rb.get_json(silent=True), 'pieces_delta': round(p1 - p0, 6),
                      'rows_delta': r1 - r0}
    v('D1_pre_fix_pieces_delta_zero', nc_b['workpiece_id'] is None
      and abs(p1 - p0) < 1e-9 and (r1 - r0) == 0, OUT['pre_fix'])

    # ---------------- 阳态：当前实现
    nc_a = make_nc(app, M, db, ctx, item_seq=912, qty=3)
    OUT['nc_after'] = nc_a
    p2, r2 = scrap_sum(app, M, db)
    ra = client.post(f"/api/quality/nonconformities/{nc_a['nc_id']}/dispose",
                     json={'action': 'scrap', 'scrap_cost': 0, 'scrap_quantity': 3})
    p3, r3 = scrap_sum(app, M, db)
    with app.app_context():
        row = (M.FinishedProduct.query.filter_by(stock_kind='scrap')
               .order_by(M.FinishedProduct.id.desc()).first())
        nc_row = M.NonconformityRecord.query.get(nc_a['nc_id'])
        item_now = M.ProductionBatchItem.query.get(nc_a['item_id'])
        OUT['post_fix'] = {
            'http': ra.status_code, 'body': ra.get_json(silent=True),
            'pieces_delta': round(p3 - p2, 6), 'rows_delta': r3 - r2,
            'qty_per_piece': round((p3 - p2) / 3.0, 6),
            'new_row': {'id': row.id, 'quantity': row.quantity, 'stock_kind': row.stock_kind,
                        'status': row.status, 'workpiece_id': row.workpiece_id,
                        'product_number': row.product_number, 'product_id': row.product_id,
                        'notes': row.notes},
            'nc_status': nc_row.status, 'item_status': item_now.status,
            'item_quality_status': item_now.quality_status,
        }
    pf = OUT['post_fix']
    v('D2_post_fix_pieces_delta_3_by_pieces',
      abs(pf['pieces_delta'] - 3.0) < 1e-9 and abs(pf['qty_per_piece'] - 1.0) < 1e-9,
      {'pieces_delta': pf['pieces_delta'], 'rows_delta': pf['rows_delta'],
       'qty_per_piece': pf['qty_per_piece']})
    v('D3_scrap_row_semantics',
      pf['new_row']['stock_kind'] == 'scrap' and pf['new_row']['status'] == 'scrapped'
      and int(pf['new_row']['quantity'] or 0) == 3 and pf['new_row']['workpiece_id'] is None
      and pf['new_row']['product_id'] is not None, pf['new_row'])
    v('D4_notes_backrefers_nc',
      str(pf['new_row']['notes'] or '').find(f"#{nc_a['nc_id']}") >= 0,
      {'notes': pf['new_row']['notes'], 'nc_id': nc_a['nc_id']})
    v('D5_nc_done_and_item_scrapped',
      pf['nc_status'] == 'done' and pf['item_status'] == 'scrapped' and pf['http'] == 200,
      {'nc_status': pf['nc_status'], 'item_status': pf['item_status'], 'http': pf['http']})

    # ---------------- 有工件路径回归（阴性对照：不得由 1 变 0）
    with app.app_context():
        wp = M.Workpiece(code='_t7v_WP1', status='in_stock', batch_item_id=nc_a['item_id'])
        db.session.add(wp)
        db.session.commit()
        wp_id = wp.id
        it2 = M.InspectionTask(global_sn=M.SerialNumber.get_next_number(),
                               inspector_id=ctx['emp_id'], created_by=ctx['emp_id'],
                               target_type='workpiece', target_id=wp_id, status='completed')
        db.session.add(it2)
        db.session.commit()
        ir2 = M.InspectionRecord(global_sn=M.SerialNumber.get_next_number(), task_id=it2.id,
                                 inspector_id=ctx['emp_id'],
                                 inspection_date=date.today(), result='fail')
        db.session.add(ir2)
        db.session.commit()
        ncw = M.NonconformityRecord(record_id=ir2.id, type='scrap', handler_id=ctx['emp_id'],
                                    handling_date=date.today(), handling_result='scrap',
                                    workpiece_id=wp_id, status='open')
        db.session.add(ncw)
        db.session.commit()
        ncw_id = ncw.id
    pw0, rw0 = scrap_sum(app, M, db)
    rw = client.post(f"/api/quality/nonconformities/{ncw_id}/dispose",
                     json={'action': 'scrap', 'scrap_cost': 5, 'scrap_quantity': 1})
    pw1, rw1 = scrap_sum(app, M, db)
    with app.app_context():
        wp_now = M.Workpiece.query.get(wp_id)
        ev = (M.WorkpieceEvent.query.filter_by(workpiece_id=wp_id, event_type='scrap')
              .order_by(M.WorkpieceEvent.id.desc()).first())
        OUT['workpiece_path'] = {
            'http': rw.status_code, 'body': rw.get_json(silent=True),
            'pieces_delta': round(pw1 - pw0, 6), 'rows_delta': rw1 - rw0,
            'wp_status': wp_now.status, 'event_id': ev.id if ev else None,
            'event_payload': ev.payload if ev else None}
    wpp = OUT['workpiece_path']
    v('C1_workpiece_pieces_delta_1_not_zero',
      abs(wpp['pieces_delta'] - 1.0) < 1e-9, wpp)
    v('C2_workpiece_pieces_monotone_nonzero', pw1 > 0 and p3 > 0,
      {'after_workpiece_path': pw1, 'after_report_path': p3})
    v('C3_wp_status_scrap_and_event_payload_shape',
      wpp['wp_status'] == 'scrap' and isinstance(wpp['event_payload'], dict)
      and set(wpp['event_payload'].keys()) == {'nc_id', 'scrap_cost', 'pieces'}
      and wpp['event_payload']['nc_id'] == ncw_id
      and abs(float(wpp['event_payload']['pieces']) - 1.0) < 1e-9,
      {'wp_status': wpp['wp_status'], 'payload': wpp['event_payload']})

    # ---------------- 真库不变量
    OUT['real_db_sha'] = {'before': REAL_SHA_BEFORE, 'after': real_sha(), 'expect': EXPECT_SHA}
    v('F1_real_db_unchanged', REAL_SHA_BEFORE == real_sha() == EXPECT_SHA, OUT['real_db_sha'])

    failed = [x['id'] for x in VERDICTS if not x['ok']]
    OUT['verdicts'] = VERDICTS
    OUT['failed_verdicts'] = failed
    OUT['verdict_counts'] = {'total': len(VERDICTS), 'failed': len(failed)}
    pathlib.Path(__file__).with_suffix('.output.json').write_text(
        json.dumps(OUT, ensure_ascii=False, indent=2), encoding='utf-8')
    print('verdicts=%d failed=%s' % (len(VERDICTS), failed))
    print('RESULT: ' + ('OK' if not failed else 'FAILED'))
    return 0 if not failed else 1


if __name__ == '__main__':
    sys.exit(main())
