# -*- coding: utf-8 -*-
"""t9 新增取证（`16` §11 / `17` §12.2 / §12.3 三项在本轮才具备取证窗口的判据）。

三个段落全部在**副本库**上跑（`DATABASE_URL` 指向 `<repo>/.tmp/<RUN_ID>/db/*.db`，
真实 `app.db` 只读），证据走 `_env.save_evidence`（分 run 目录 + 写入守卫 + 台账）。

## 段 D：CSRF 判据失效的**三方判别**（回应 api_matrix 的 `not_enforced` 0 -> 24）
`api_matrix.csrf_matrix` 的判据是 `code==400 and ('csrf' in body or '令牌' in body or 'Token'
 in body)`。W4/P-12 把 `errorhandler(HTTPException)` 统一后，JSON 面的 CSRF 400 正文变成
`{"message":"请求参数有误"}`（`app/__init__.py:191-216` 的 `_HTTP_REASONS[400]`）⇒ 判据探测不到标记。
本段用同一端点做三方对照，**证明拦截仍在、只是标记被换掉**：
  (a) 无 token + CSRF 开 => 期望「框架级 400」（`请求参数有误`，视图未执行）
  (b) 带合法 token + CSRF 开 => 视图必须执行（`缺少批次 id`）
  (c) 无 token + CSRF 关 => 视图必须执行（`缺少批次 id`）
判据 D-1：a 的正文 == 框架级文案且 != b/c 的视图级文案；D-2：b、c 的正文 == 视图级文案。

## 段 E：`16` §11 补记的**交叉守护断言**（返工件数 / 报废件数不得互相串台）
  E-1 显式 `rework_quantity=3` 且不传 `scrap_quantity`，action=scrap
      => 料账扣量必须是 `N×1`（不是 `N×3`），报废入库 == 1
  E-2 显式 `scrap_quantity=2` 且不传 `rework_quantity`，action=rework
      => 返工任务件数必须是来源产出件数（4），不是 2；且不得发生报废扣料

## 段 F：`17` §12.3 质检员归属校验（P-12 修好 415 后才具备取证窗口）
  F-1 非归属 inspector（U_B）`start-inspection` => 403 + 原因含「自己」+ 0 个 5xx
  F-2 归属人（U_A）同一请求 => **不得 403**（阳性对照，防「一律 403」假修复）
  F-3 非归属 inspector（U_B）`records/<id>/submit` => 403 + 原因含「自己」
  F-4 归属人（U_A）提交同一记录 => **不得 403**
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPORTS_ROOT = os.path.dirname(HERE)
REPO_ROOT = os.path.dirname(REPORTS_ROOT)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO_ROOT, 'scripts'))

from _env import (  # noqa: E402
    REAL_DB, REAL_DB_SHA256_EXPECTED, RUN_ID, save_evidence, sha256_file,
)
import w2w3_probe as W  # noqa: E402  （复用其副本库夹具与真实端点助手）

CHECKS = []
RAW = {}


def ck(cid, desc, expected, actual, ok, evidence=''):
    CHECKS.append({'id': cid, 'desc': desc, 'expected': expected, 'actual': actual,
                   'status': 'passed' if ok else 'failed', 'evidence': evidence})
    print('[%s] %-6s %s | expected=%s actual=%s %s'
          % ('PASS' if ok else 'FAIL', cid, desc, json.dumps(expected, ensure_ascii=True),
             json.dumps(actual, ensure_ascii=True, default=str), evidence), flush=True)


# ------------------------------------------------------------------ 段 D：CSRF
TARGET_URL = '/api/production/generate-codes'
FRAMEWORK_400_TEXT = '请求参数有误'      # app/__init__.py:193 `_HTTP_REASONS[400]`
VIEW_400_TEXT = '缺少批次 id'            # production_center.py:414 视图级文案


def _post_text(client, headers=None):
    resp = client.post(TARGET_URL, json={}, headers=headers or {})
    return resp.status_code, (resp.get_data(as_text=True) or '')


def _msg(body):
    """从 JSON 正文里取 message（响应正文是 \\uXXXX 转义，直接子串匹配会漏）。"""
    try:
        return (json.loads(body) or {}).get('message')
    except Exception:
        return None


def section_csrf(env):
    import re as _re
    app = env['app']
    client = env['client']
    out = {}
    orig = bool(app.config.get('WTF_CSRF_ENABLED'))

    def _mint_token():
        """用**同一个 client 会话**渲染 base.html 的 `<meta name="csrf-token">`（base.html:7）。"""
        page = client.get('/')
        html = page.get_data(as_text=True) or ''
        m = _re.search(r'name="csrf-token"\s+content="([^"]+)"', html)
        return (m.group(1) if m else None), page.status_code, len(html)

    token, page_code, page_bytes = _mint_token()
    app.config['WTF_CSRF_ENABLED'] = True
    try:
        code_a, body_a = _post_text(client)
        code_b, body_b = _post_text(client, headers={'X-CSRFToken': token or ''})
        app.config['WTF_CSRF_ENABLED'] = False
        code_c, body_c = _post_text(client)
    finally:
        app.config['WTF_CSRF_ENABLED'] = orig
    out.update({'token_from_page': bool(token), 'token_page': {'code': page_code,
                                                              'bytes': page_bytes},
                'a_no_token_csrf_on': {'code': code_a, 'body': body_a[:200],
                                       'message': _msg(body_a)},
                'b_valid_token_csrf_on': {'code': code_b, 'body': body_b[:200],
                                          'message': _msg(body_b)},
                'c_no_token_csrf_off': {'code': code_c, 'body': body_c[:200],
                                        'message': _msg(body_c)},
                'csrf_flag_restored': bool(app.config.get('WTF_CSRF_ENABLED')) == orig})
    RAW['csrf'] = out
    # (a) 无 token + CSRF 开 ⇒ 框架级 400（视图未执行）;(c) 关 CSRF ⇒ 视图级 400 文案
    a_ok = code_a == 400 and _msg(body_a) == FRAMEWORK_400_TEXT and VIEW_400_TEXT not in body_a
    c_ok = VIEW_400_TEXT == _msg(body_c)
    b_ok = (_msg(body_b) == VIEW_400_TEXT) if token else None
    ck('D-1', '无 token + CSRF 开 => 框架级 400（视图未执行）；关 CSRF => 视图级 400（视图执行）'
              ' ⇒ CSRF 拦截仍在，只是标记被统一 400 文案替换',
       {'a_message': FRAMEWORK_400_TEXT, 'c_message': VIEW_400_TEXT},
       {'a_code': code_a, 'a_message': _msg(body_a), 'c_code': code_c,
        'c_message': _msg(body_c)},
       a_ok and c_ok, '同一端点的 CSRF 开/关对照（production_center.py:400）')
    ck('D-2', '带合法 token（同一会话的 meta csrf-token）=> 视图必须执行（三方判别闭环）',
       {'b_message': VIEW_400_TEXT}, {'token_found': bool(token), 'b_code': code_b,
                                      'b_message': _msg(body_b)},
       bool(token) and b_ok, 'base.html:7 的 meta csrf-token + X-CSRFToken 头（base.html:576 同法）')
    ck('D-3', 'api_matrix 的 csrf_blocked 判据在本仓库**已失效**（标记被替换）',
       {'csrf_marker_in_a_body': False},
       {'csrf_marker_in_a_body': ('csrf' in body_a.lower() or '令牌' in body_a
                                  or 'Token' in body_a)},
       not ('csrf' in body_a.lower() or '令牌' in body_a or 'Token' in body_a),
       'api_matrix.py:808-809 的判据形状 => 24 条误报为 not_enforced（安全属性未变）')
    return out


# ------------------------------------------------------------------ 段 E：交叉守护
def section_crossguard(env, ctx):
    from app import db
    from app import models as M
    out = {}
    rm1, rm2 = ctx['material_ids'][0], ctx['material_ids'][1]

    # E-1：显式 rework_quantity 不得影响 scrap 分支的扣量（扣 N×1）
    item1, task1 = W.new_item_task(env, ctx, 'A', 61, 4, suffix='XG1')
    W.set_raw(env, rm1, 100.0)
    W.set_raw(env, rm2, 100.0)
    W.report(env, task1, 4, materials=[{'raw_material_id': rm1, 'quantity': 2.0},
                                       {'raw_material_id': rm2, 'quantity': 3.0}])
    nc1, wp1 = W.make_workpiece_nc(env, ctx, item1, 'XG1', raw_material_id=rm1)
    a1, a2 = W.raw_qty(env, rm1), W.raw_qty(env, rm2)
    if nc1:
        code1, _body1 = W.dispose(env, nc1, action='scrap', scrap_cost=1.0,
                                  rework_quantity=3, notes='_t9 交叉守护 E1')
        b1, b2 = W.raw_qty(env, rm1), W.raw_qty(env, rm2)
        with env['app'].app_context():
            wp = M.Workpiece.query.get(wp1)
            scrap_qty = W.scrap_pieces(env, wp.code if wp else None)
        out['e1'] = {'http': code1, 'before': [a1, a2], 'after': [b1, b2],
                     'scrap_inbound': scrap_qty}
        ck('E-1', '显式 rework_quantity=3 + action=scrap（不传 scrap_quantity）'
                  ' => 扣量 N×1（不是 N×3）',
           {'rm1': a1 - 2.0, 'rm2': a2 - 3.0, 'scrap_inbound': 1.0},
           {'rm1': b1, 'rm2': b2, 'scrap_inbound': scrap_qty},
           abs(b1 - (a1 - 2.0)) < 1e-9 and abs(b2 - (a2 - 3.0)) < 1e-9
           and abs((scrap_qty or 0) - 1.0) < 1e-9,
           '16 §11 补记：两个入参不得合并（否则「返工按报废件数扣料」静默错账）')

    # E-2：显式 scrap_quantity 不得影响 rework 分支的件数（件数取来源产出 Q）
    item2, task2 = W.new_item_task(env, ctx, 'A', 62, 4, suffix='XG2')
    W.set_raw(env, rm1, 100.0)
    W.report(env, task2, 4)
    W.submit_inspection(env, ctx, task2, 'fail')
    nc2 = W.latest_nc_for_item(env, item2)
    if nc2:
        before_rm1 = W.raw_qty(env, rm1)
        code2, _body2 = W.dispose(env, nc2, action='rework',
                                  rework_process_id=ctx['A']['process_id'],
                                  employee_id=ctx['emp_id'], scrap_quantity=2,
                                  notes='_t9 交叉守护 E2')
        row2 = W.nc_row(env, nc2)
        with env['app'].app_context():
            new_task = (M.TaskAssignment.query.get(row2['rework_task_id'])
                        if row2 and row2.get('rework_task_id') else None)
            info = None if new_task is None else {'id': new_task.id,
                                                  'quantity': new_task.quantity}
        after_rm1 = W.raw_qty(env, rm1)
        out['e2'] = {'http': code2, 'rework_task': info,
                     'raw_material_unchanged': abs(after_rm1 - before_rm1) < 1e-9}
        ck('E-2', '显式 scrap_quantity=2 + action=rework（不传 rework_quantity）'
                  ' => 返工件数 = 来源产出件数 4（不是 2），且不发生报废扣料',
           {'quantity': 4, 'scrap_deduction': 0.0},
           {'quantity': (info or {}).get('quantity'),
            'raw_delta': round(after_rm1 - before_rm1, 6)},
           bool(info) and info['quantity'] == 4 and abs(after_rm1 - before_rm1) < 1e-9,
           '16 §11 补记（交叉守护） / DEC-2 §2.3')
    return out


# ------------------------------------------------------------------ 段 F：归属校验
def section_ownership(env, ctx):
    from app import db
    from app import models as M
    from datetime import date
    out = {}
    users, password = env['users'], env['password']
    admin_id = ctx['admin_id']
    app, client = env['app'], env['client']

    with app.app_context():
        ua = M.User.query.filter_by(username=users['inspector']).first()
        ub = M.User.query.filter_by(username='_t9_inspector_B').first()
        if ub is None:
            ub = M.User(username='_t9_inspector_B', role='inspector')
            ub.set_password(password)
            db.session.add(ub)
            db.session.commit()
        ub_id = ub.id
        wp = M.Workpiece(code='_t9WPOWN%s' % ctx['tag'], status='machining',
                         product_id=ctx['A']['product_id'])
        db.session.add(wp)
        db.session.flush()
        task = M.InspectionTask(global_sn=M.SerialNumber.get_next_number(),
                                target_type='workpiece', target_id=wp.id,
                                inspector_id=ua.id, status='pending',
                                created_by=admin_id)
        db.session.add(task)
        db.session.flush()
        tpl = M.InspectionTemplate(template_code='_T9OWN%s' % ctx['tag'],
                                   name='_t9 归属校验模板', type='workpiece',
                                   is_active=True, created_by=admin_id)
        db.session.add(tpl)
        db.session.commit()
        task_id, tpl_id, ua_id = task.id, tpl.id, ua.id
        rec = M.InspectionRecord(global_sn=M.SerialNumber.get_next_number(), task_id=task_id,
                                 inspector_id=ua_id, inspection_date=date.today(),
                                 result='pending')
        db.session.add(rec)
        db.session.commit()
        rec_id = rec.id
    out['fixture'] = {'task_id': task_id, 'template_id': tpl_id, 'owner_inspector_id': ua_id,
                      'other_inspector_id': ub_id, 'record_id': rec_id}

    from _test_bootstrap import login_as

    def _as(username, method, url, payload):
        client.get('/auth/logout')
        st = login_as(client, username, password)
        resp = getattr(client, method)(url, json=payload)
        raw = (resp.get_data(as_text=True) or '')
        try:
            message = (json.loads(raw) or {}).get('message')
        except Exception:
            message = None
        return {'login': st.status_code, 'code': resp.status_code, 'body': raw[:220],
                'message': message}

    b_start = _as('_t9_inspector_B', 'post',
                  '/api/quality/tasks/%d/start-inspection' % task_id, {'template_id': tpl_id})
    a_start = _as(users['inspector'], 'post',
                  '/api/quality/tasks/%d/start-inspection' % task_id, {'template_id': tpl_id})
    b_submit = _as('_t9_inspector_B', 'post',
                   '/api/quality/records/%d/submit' % rec_id, {'result': 'pass'})
    a_submit = _as(users['inspector'], 'post',
                   '/api/quality/records/%d/submit' % rec_id, {'result': 'pass'})
    out.update({'b_start': b_start, 'a_start': a_start, 'b_submit': b_submit,
                'a_submit': a_submit})
    RAW['ownership'] = out

    ck('F-1', '非归属 inspector 提交 start-inspection => 403 + 原因可读 + 0 个 5xx',
       {'code': 403, 'message': '只能执行分配给自己的质检任务'},
       {'code': b_start['code'], 'message': b_start['message']},
       b_start['code'] == 403 and b_start['message'] == '只能执行分配给自己的质检任务',
       '17 §12.3')
    ck('F-2', '归属人（阳性对照）同一请求 => **不得 403**（防「一律 403」假修复）',
       {'code_not': 403, 'code_in': [200, 400, 404, 415]},
       {'code': a_start['code'], 'message': a_start['message']},
       a_start['code'] != 403, '17 §12.3 阳性对照 / RC-4 / RC-8')
    ck('F-3', '非归属 inspector 提交 records/<id>/submit => 403 + 原因可读',
       {'code': 403, 'message': '只能提交分配给自己的质检记录'},
       {'code': b_submit['code'], 'message': b_submit['message']},
       b_submit['code'] == 403 and b_submit['message'] == '只能提交分配给自己的质检记录',
       '17 §12.3')
    ck('F-4', '归属人提交同一质检记录 => **不得 403**',
       {'code_not': 403}, {'code': a_submit['code'], 'message': a_submit['message']},
       a_submit['code'] != 403, '17 §12.3 阳性对照')
    for cid, row in (('F-1', b_start), ('F-3', b_submit)):
        ck(cid + '-noleak', '%s 的正文不得泄漏实现细节' % cid,
           {'no_sql_or_traceback': True}, {'body': row['body']},
           not any(m in row['body'] for m in ('sqlite3.', '[SQL:', 'Traceback',
                                              'IntegrityError', '[parameters:')),
           '与 P-11 同口径')
    return out


# ------------------------------------------------------------------ main
def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError, OSError):
        pass
    ap = argparse.ArgumentParser(description='t9 new-findings probe')
    ap.add_argument('--scenario', default='all', choices=('all', 'csrf', 'xguard', 'ownership'))
    args = ap.parse_args(argv)

    started = time.strftime('%Y-%m-%d %H:%M:%S')
    before = sha256_file(REAL_DB)
    print('=' * 90)
    print('[t9-new] RUN_ID=%s scenario=%s started=%s' % (RUN_ID, args.scenario, started))
    print('[t9-new] real db sha256 before = %s' % before)
    print('=' * 90)

    env = W.build_app()
    print('[t9-new] copy=%s samefile(real)=%s login=%s'
          % (env['copy_path'], env['copy_samefile_as_real'], env['login_status']), flush=True)
    ctx = W.build_fixtures(env)

    if args.scenario in ('all', 'csrf'):
        print('\n### 段 D：CSRF 三方判别')
        section_csrf(env)
    if args.scenario in ('all', 'xguard'):
        print('\n### 段 E：交叉守护（16 §11）')
        section_crossguard(env, ctx)
    if args.scenario in ('all', 'ownership'):
        print('\n### 段 F：质检员归属校验（17 §12.3）')
        section_ownership(env, ctx)

    after = sha256_file(REAL_DB)
    failed = [c for c in CHECKS if c['status'] != 'passed']
    summary = {'run_id': RUN_ID, 'started': started,
               'finished': time.strftime('%Y-%m-%d %H:%M:%S'), 'scenario': args.scenario,
               'total': len(CHECKS), 'passed': len(CHECKS) - len(failed),
               'failed': len(failed), 'failed_ids': [c['id'] for c in failed],
               'real_db_sha256_before': before, 'real_db_sha256_after': after,
               'real_db_unchanged': before == after == REAL_DB_SHA256_EXPECTED,
               'copy_path': env['copy_path']}
    result = {'summary': summary, 'checks': CHECKS, 'raw': RAW}
    text = ('=' * 90 + '\n[t9-new] summary=%s\n'
            % json.dumps(summary, ensure_ascii=True, sort_keys=True)
            + ''.join('[%s] %-6s %s | expected=%s actual=%s\n'
                      % (c['status'].upper(), c['id'], c['desc'],
                         json.dumps(c['expected'], ensure_ascii=True),
                         json.dumps(c['actual'], ensure_ascii=True, default=str))
                      for c in CHECKS)
            + '\n--- raw ---\n' + json.dumps(RAW, ensure_ascii=False, indent=1, default=str) + '\n')
    p1 = save_evidence('t9-newfindings.json',
                       json.dumps(result, ensure_ascii=False, indent=1, default=str))
    p2 = save_evidence('t9-newfindings.console.txt', text)
    print('\n[summary] %s' % json.dumps(summary, ensure_ascii=True, sort_keys=True))
    print('[evidence] -> %s' % os.path.relpath(p1, REPO_ROOT).replace('\\', '/'))
    print('[evidence] -> %s' % os.path.relpath(p2, REPO_ROOT).replace('\\', '/'))
    verdict = 'PASS' if not failed and summary['real_db_unchanged'] else 'FAIL'
    print('[verdict] %s' % verdict)
    return 0 if verdict == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
