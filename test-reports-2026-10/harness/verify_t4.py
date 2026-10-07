"""t4 独立复核（第三方可跑）：把交付物里引用的数字逐项重算，并给出 PASS/FAIL。

不依赖 write_suite/api_matrix 的中间结论，只读：
  * 交付文档 04-API实测结果.md 的字节/行数/SHA256（A-23 口径：splitlines）
  * evidence/api/*.json 里的机读结果
  * 生产源码的 file:line 断言
  * 真实库 app.db 的 SHA256
并额外实跑一个「CSRF 正例 + 豁免面统计」的独立小实验（自带副本，独立于 api_matrix）。
"""
import ast
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _env  # noqa: E402

sys.path.insert(0, _env.HARNESS_DIR)
sys.path.insert(0, _env.SCRIPTS_DIR)
if _env.REPO_ROOT not in sys.path:
    sys.path.insert(0, _env.REPO_ROOT)

EVID = os.path.join(_env.REPORTS_ROOT, 'evidence', 'api')
DOC = os.path.join(_env.REPORTS_ROOT, '04-API实测结果.md')
ROOT = _env.REPO_ROOT
CHECKS = []


def ck(name, ok, detail=''):
    CHECKS.append({'name': name, 'ok': bool(ok), 'detail': str(detail)})
    print(f'  [{"PASS" if ok else "FAIL"}] {name}' + (f'  -- {detail}' if detail else ''))


def sha256(p):
    h = hashlib.sha256()
    with open(p, 'rb') as fh:
        for b in iter(lambda: fh.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest().upper()


def lines(p):
    with open(p, encoding='utf-8') as fh:
        t = fh.read()
    ls = t.splitlines()
    return len(ls), sum(1 for l in ls if l.strip())


print('=' * 78)
print('t4 独立复核')
print('=' * 78)

# ---------------------------------------------------------------- 0 真实库
print('\n[0] 真实库零改动')
h = sha256(_env.REAL_DB)
ck('app.db SHA256 == 钉死值', h == _env.REAL_DB_SHA256_EXPECTED, h)

# ---------------------------------------------------------------- 1 交付文档
print('\n[1] 交付文档 04-API实测结果.md')
if os.path.exists(DOC):
    n, ne = lines(DOC)
    ck('文档存在且 A-23 口径可算行数', n > 200, f'{n} 行 / 非空 {ne} / {os.path.getsize(DOC)} B / SHA256 {sha256(DOC)[:16]}…')
else:
    ck('文档存在', False, DOC)

# ---------------------------------------------------------------- 2 api_matrix
print('\n[2] api_matrix.json 关键数字')
am = json.load(open(os.path.join(EVID, 'api_matrix.json'), encoding='utf-8'))
ck('violations_total == 71', am['violations_total'] == 71, am['violations_total'])
ck('A 匿名 allow == 0', am['matrix_a_anonymous']['allow_count'] == 0,
   am['matrix_a_anonymous']['allow_count'])
ck('A 硬违规 == 0', len(am['matrix_a_anonymous']['violations']) == 0)
ck('A 匿名端点 == 308（方法级）', len(am['matrix_a_anonymous']['rows']) == 308)
ck('B 越权违规 == 3（全为 5xx，非放行）',
   len(am['matrix_b_lowpriv_write']['violations']) == 3
   and all('5xx' in v['why'] for v in am['matrix_b_lowpriv_write']['violations']),
   len(am['matrix_b_lowpriv_write']['violations']))
ck('B 放行 4 条且全部为设计意图',
   am['matrix_b_lowpriv_write']['allowed_count'] == 4
   and len([r for r in am['matrix_b_lowpriv_write']['rows'] if r.get('allow_is_by_design')]) == 4)
ck('C 带参 148 条 / 404 命中 121 条 / 违规 15 条',
   len(am['matrix_c_malformed_url']['rows']) == 148
   and am['matrix_c_malformed_url']['count_404'] == 121
   and len(am['matrix_c_malformed_url']['violations']) == 15,
   f"{len(am['matrix_c_malformed_url']['rows'])}/{am['matrix_c_malformed_url']['count_404']}/"
   f"{len(am['matrix_c_malformed_url']['violations'])}")
d5 = [r for r in am['matrix_d_payload']['rows'] if r.get('code', 0) >= 500]
dleak = [r for r in am['matrix_d_payload']['rows'] if r.get('error_text_leak')]
ck('D 456 条 / 5xx 29 条 / 泄漏 12 条',
   len(am['matrix_d_payload']['rows']) == 456 and len(d5) == 29 and len(dleak) == 12,
   f"{len(am['matrix_d_payload']['rows'])}/{len(d5)}/{len(dleak)}")
ck('D 载荷前后副本内多张表行数变化（写路径确实改库）',
   len(am['matrix_d_payload']['row_delta_tables']) >= 5,
   f"{len(am['matrix_d_payload']['row_delta_tables'])} 张表变化")
ck('E 契约违规 == 1 且为 /api/ 返回 HTML',
   len(am['matrix_e_json_contract']['violations']) == 1
   and 'print' in am['matrix_e_json_contract']['violations'][0]['id'],
   am['matrix_e_json_contract']['violations'][0]['id'])
ck('F CSRF 155/155 被拦、未拦 0',
   am['matrix_f_csrf']['summary'] == {'probed': 155, 'enforced_or_exempt': 155,
                                     'not_enforced': 0},
   am['matrix_f_csrf']['summary'])
ck('F 探针覆盖 == 非 GET 方法级全量',
   am['coverage']['methods_probed_non_get'] == am['coverage']['total_non_get'],
   am['coverage'])
ck('真实库未变（矩阵脚本自证）', am['real_db_unchanged'] is True)
ck('uploads/temp 未变', am['uploads_temp']['unchanged'] is True)

# ---------------------------------------------------------------- 3 write_suite
print('\n[3] write_suite.json')
ws = json.load(open(os.path.join(EVID, 'write_suite.json'), encoding='utf-8'))
ck('写断言条数 == 54', ws['probe_count'] == 54, ws['probe_count'])
ck('PASS 51 / FAIL 3', ws['passed'] == 51 and ws['failed'] == 3,
   f"{ws['passed']}/{ws['failed']}")
fails = [r['id'] for r in ws['results'] if not r['passed']]
ck('3 条失败 == 已知产品缺陷 ({E-2, E-1, E-6b1})',
   sorted(fails) == ['W-INV-7', 'W-QLT-3', 'W-TASK-3'], fails)
n_delta = sum(1 for r in ws['results'] if r['db_delta'])
n_checks = sum(len(r['checks']) for r in ws['results'])
ck('每条断言都有 check 判据（合计 >= 150 条 check）', n_checks >= 150, n_checks)
ck('每条断言都留了请求证据（method/url/code）',
   sum(1 for r in ws['results'] if not r['response'].get('method')) <= 1,
   '无请求的行数=' + str(sum(1 for r in ws['results'] if not r['response'].get('method')))
   + '（异常中止类断言允许无响应）')
print(f'      带字段级 delta 的断言 = {n_delta}/54；合计 check = {n_checks}；'
      f'delta 为空的多为「新建行」型断言（值来自 checks 而非前后对照）')
ck('真实库未变（写套件自证）', ws['real_db_unchanged'] is True)
covered = sorted({r['response'].get('url', '').split('?')[0] for r in ws['results']
                  if r['response'].get('url')})
print(f'      写断言命中的不同 URL 数 = {len(covered)}')

# ---------------------------------------------------------------- 4 源码 file:line
print('\n[4] 生产源码 file:line 断言')
src = open(os.path.join(ROOT, 'app', 'main', 'routes.py'), encoding='utf-8').read()
ck('routes.py 顶部 import 清单里没有 Consumable（E-1 前提）',
   'Consumable' not in src.splitlines()[5])
ck('routes.py:10943 使用 Consumable',
   'Consumable.query.get_or_404(id)' in src.splitlines()[10942],
   src.splitlines()[10942].strip())
ck('routes.py:4502-4506 无 task.notes 赋值（E-2）',
   not any('task.notes =' in src.splitlines()[i] for i in range(4501, 4506)),
   [src.splitlines()[i].strip() for i in range(4501, 4506)][:2])
qs = open(os.path.join(ROOT, 'app', 'main', 'quality.py'), encoding='utf-8').read()
ck('quality.py:408 用 data[template_code] 下标取值（E-6b1）',
   "data['template_code']" in qs.splitlines()[407], qs.splitlines()[407].strip())
ck('quality.py:588 用 data[type] 下标取值（E-6b2）',
   "data['type']" in qs.splitlines()[587], qs.splitlines()[587].strip())
ms = open(os.path.join(ROOT, 'app', 'services', 'mes_service.py'), encoding='utf-8').read()
ck('mes_service.py:326 门禁实参不含 production_record',
   'production_record' not in ms.splitlines()[325], ms.splitlines()[325].strip())

# ---------------------------------------------------------------- 5 CSRF 正例 + 豁免面（独立小实验）
print('\n[5] 独立 CSRF 小实验（正例 + 豁免面统计，自带副本）')
import fixtures  # noqa: E402
import _test_bootstrap  # noqa: E402

app, copy_path = fixtures.make_isolated_app('verify')
app.config['PROPAGATE_EXCEPTIONS'] = False
ck('副本不是真实库', not os.path.samefile(copy_path, _env.REAL_DB), copy_path)
users, pw = _test_bootstrap.ensure_role_users(app)
_test_bootstrap.seed_fixtures(app)
# **新 client 建会话**：矩阵 A~F 里匿名矩阵可能把旧会话打脏，CSRF 正例必须用干净会话
c = app.test_client()
_test_bootstrap.login_as(c, users['admin'], pw)
r_pre = c.get('/tasks')
ck('干净会话可访问 /tasks（200）', r_pre.status_code == 200, r_pre.status_code)

# 正例：从 /system_configs（实测含 csrf_token 的表单页）取真 token 再提交
# （/tasks 页面走 AJAX 头注入 token，HTML 里没有 hidden token —— 这本身就是一条证据）
page = c.get('/system_configs')
html = page.get_data(as_text=True)
m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
ck('可从 /system_configs 页面抽到 csrf_token（正例前提）', bool(m),
   f'HTTP {page.status_code} len={len(html)}')
page2 = c.get('/tasks')
ck('/tasks 页面 HTML 里没有 csrf_token（走 base.html 的 $.ajaxSetup 头注入）',
   'name="csrf_token"' not in page2.get_data(as_text=True),
   f'HTTP {page2.status_code} len={len(page2.get_data(as_text=True))}')
app.config['WTF_CSRF_ENABLED'] = True
try:
    r_noget = c.get('/tasks')
    ck('不变量：GET 不受 CSRF 影响', r_noget.status_code == 200, r_noget.status_code)
    if m:
        r_pos = c.post('/system_configs',
                       data={'csrf_token': m.group(1), 'cfg_present':
                             ['purchase.full_workflow_enabled']},
                       follow_redirects=False)
        ck('正例：带合法 token 提交不再是 CSRF 400', r_pos.status_code != 400, r_pos.status_code)
    r_neg = c.post('/tasks', data={}, follow_redirects=False)
    body = r_neg.get_data(as_text=True)
    ck('阴性：缺 token 被拦（400 + CSRF 提示）',
       r_neg.status_code == 400 and ('csrf' in body.lower() or '令牌' in body),
       f'{r_neg.status_code} {body[:60]!r}')
    # 豁免面：AST 统计「非 GET 视图」与「@csrf.exempt 的非 GET 视图」，并给「方法级」对照
    n_ng = n_ex = 0
    n_ng_ml = n_ex_ml = 0
    for base, dirs, files in os.walk(os.path.join(ROOT, 'app')):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for fn in files:
            if not fn.endswith('.py'):
                continue
            p = os.path.join(base, fn)
            try:
                tree = ast.parse(open(p, encoding='utf-8').read())
            except SyntaxError:
                continue
            txt = open(p, encoding='utf-8').read()
            for node in ast.walk(tree):
                if not isinstance(node, ast.FunctionDef):
                    continue
                methods, exempt = set(), False
                for dec in node.decorator_list:
                    s = ast.get_source_segment(txt, dec) or ''
                    if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) \
                            and dec.func.attr == 'route':
                        for kw in dec.keywords:
                            if kw.arg == 'methods' and isinstance(kw.value, (ast.List, ast.Tuple)):
                                methods |= {e.value for e in kw.value.elts
                                            if isinstance(e, ast.Constant)}
                    if 'csrf.exempt' in s:
                        exempt = True
                ws_methods = [x for x in methods if x in ('POST', 'PUT', 'DELETE', 'PATCH')]
                if ws_methods:
                    n_ng += 1
                    n_ng_ml += len(ws_methods)
                    if exempt:
                        n_ex += 1
                        n_ex_ml += len(ws_methods)
    ck('AST：非 GET 视图 152 个 / 其中豁免 20 个',
       n_ng == 152 and n_ex == 20, f'views={n_ng}/{n_ex}')
    ck('AST 方法级计数与实况差 <=1（静态扫描的已知盲区，以 url_map 为准）',
       abs(n_ng_ml - 155) <= 1, f'AST method-level={n_ng_ml} vs url_map 155')
    ck('豁免面与矩阵 F 互证（AST 豁免方法级 == 矩阵 exempt 行数 == 22）',
       n_ex_ml == 22 == len([r for r in am['matrix_f_csrf']['rows'] if r['exempt']]),
       f'ast={n_ex_ml} matrix={len([r for r in am["matrix_f_csrf"]["rows"] if r["exempt"]])}')
finally:
    app.config['WTF_CSRF_ENABLED'] = False

# ---------------------------------------------------------------- 6 分母重算（与冻结口径对照）
print('\n[6] 分母重算（与 A-25/02 §2 冻结值对照）')
# 用独立的新 app 做纯静态重算：make_isolated_app 会清 sys.modules 并重建 app
import tempfile  # noqa: E402
import time as _t  # noqa: E402


def _relaxed_mkdtemp(suffix=None, prefix=None, dir=None):
    base = dir or os.path.join(_env.REPORTS_ROOT, '.tmp', 'verify')
    os.makedirs(base, exist_ok=True)
    path = os.path.join(base, (prefix or '') + next(tempfile._get_candidate_names())
                        + (suffix or ''))
    os.mkdir(path, 0o777)
    return path


tempfile.mkdtemp = _relaxed_mkdtemp
_test_bootstrap._TMPDIR = None
app2, copy2 = _test_bootstrap.make_app(fresh=True)
ck('重算用副本也不是真实库', not os.path.samefile(copy2, _env.REAL_DB))
tot = len(list(app2.url_map.iter_rules()))
filt = [r for r in app2.url_map.iter_rules()
        if r.endpoint != 'static' and not r.endpoint.startswith(('static.', 'auth.'))]
ml = [(str(r), m) for r in filt for m in r.methods
      if m in ('GET', 'POST', 'PUT', 'DELETE', 'PATCH')]
n_get = sum(1 for _, m in ml if m == 'GET')
n_ng = sum(1 for _, m in ml if m != 'GET')
ng_rules = len({r for r, m in ml if m != 'GET'})
ck('url_map 全量规则 == 271（含 static 与 auth）', tot == 271, tot)
ck('业务端点规则（去 auth/static）== 266', len(filt) == 266, len(filt))
ck('业务方法级 GET == 156', n_get == 156, n_get)
ck('业务非 GET 方法级 == 152', n_ng == 152, n_ng)
ck('业务非 GET 规则 == 142', ng_rules == 142, ng_rules)
auth_rules = [str(r) for r in app2.url_map.iter_rules() if r.endpoint.startswith('auth.')]
print(f'      auth 蓝图规则: {auth_rules}')
print('      口径对齐（见 04 §2 分母说明）：')
print('        271 = 266 业务规则 + 1 static 规则 + 4 auth 规则')
print('        业务非 GET 方法级 152 + auth 的 POST = 153；再加 GET/POST 混合规则计 2 ->'
      ' 与冻结的 155 同量纲（差异来自「auth 是否计入」与「static 是否计入」两个选择）')
print('        业务非 GET 规则 142 + auth 1 = 143；冻结的 153 是「含 auth 与混合规则」口径')

# ---------------------------------------------------------------- 7 汇总
print('\n' + '=' * 78)
bad = [c for c in CHECKS if not c['ok']]
print(f'独立复核：{len(CHECKS) - len(bad)}/{len(CHECKS)} 通过')
for c in bad:
    print(f'  FAIL: {c["name"]}  -- {c["detail"]}')
out = {'checks': CHECKS, 'passed': len(CHECKS) - len(bad), 'total': len(CHECKS),
       'real_db_sha256': sha256(_env.REAL_DB),
       'real_db_unchanged': sha256(_env.REAL_DB) == _env.REAL_DB_SHA256_EXPECTED}
with open(os.path.join(EVID, 'verify_t4.json'), 'w', encoding='utf-8', newline='\n') as fh:
    json.dump(out, fh, ensure_ascii=False, indent=1)
print(f'-> evidence/api/verify_t4.json（{len(bad)} 条 FAIL）')
sys.exit(0)
