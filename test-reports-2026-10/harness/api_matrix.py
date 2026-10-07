"""t4 执行器：副本库上的 HTTP 契约 × 权限 × 写端点安全矩阵。

只读生产代码；一切请求打在 ``app.db`` 的**副本**上（``fixtures.make_isolated_app``），
脚手架自身不清洗被测应用（不关 CSRF、不改 config），因此测的是**真实配置**行为。

统一口径（``README`` 见 ``04-API实测结果.md`` §1）：

* **分母 A（方法级）**：``url_map`` 中每个 rule 的每个谓词算一个端点（GET/POST/PUT/DELETE），
  与 ``02`` §2 的 155（非 GET 方法级）同口径。
* **分母 B（规则级）**：每个 rule 算一个（非 GET 规则 153）。
* **cjk 哨兵**：``__t4_probe__``（字符串）、``999999999``（整数）。哨兵值都**不会**命中真实行。
* **判「已放行」**：见 ``_verdict_of_response``，避免把「200 + 权限不足」误判成放行。
* **只读证明**：真实库 SHA256 每阶段前后复核（钉死 ``F5DA2306…``）；副本库做逐表行数指纹。

产出（全部落在 ``evidence/api/``）：
``api_matrix.json``（机读全量：端点清单 + 3 个矩阵 + 契约审计 + 载荷轨迹 + 停止原因）、
``api_matrix.out.txt``（人读日志 + 断言汇总）。
"""
import ast
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 控制台/重定向在 cp936 下遇到 GBK 不可表示的符号（如 =>）会 UnicodeEncodeError 崩掉
# —— 取证脚本不能因为打印符号而死，这里统一按 UTF-8 输出（A-14 同款处置）。
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

import _env  # noqa: E402
import fixtures  # noqa: E402
from _env import REAL_DB, assert_real_db_untouched, sha256_file  # noqa: E402

EVID = os.path.join(_env.REPORTS_ROOT, 'evidence', 'api')
ROOT = _env.REPO_ROOT
SCAN_DIRS = (os.path.join(ROOT, 'app'), os.path.join(ROOT, 'scripts'))
SKIP_ENDPOINT_PREFIX = ('auth.', 'static')
SKIP_PATH = {'/auth/logout', '/auth/register', '/auth/login'}
API_PREFIX = '/api/'
SENTINEL_STR = '__t4_probe__'
SENTINEL_INT = 999999999
EXC_PAT = re.compile(r'[A-Za-z_][A-Za-z0-9_]*Error|[A-Za-z_][A-Za-z0-9_]*Exception'
                     r'|Traceback \(most recent call last\)|sqlite3\.|NOT NULL constraint'
                     r'|\[SQL:|UNIQUE constraint|IntegrityError')
DENY_HINT = ('权限不足', '请先登录', '失败', '错误', '不存在', '无效', '不能为空')
PROBE_KEYS_IN_SOURCE = ('form', 'args', 'json', 'values', 'get_json', 'files')
ARRAY_HINT = ('不能为空', '无效', '失败', '错误', '必须', '未提供', '格式')

_LOG = []


def log(msg=''):
    line = str(msg)
    _LOG.append(line)
    print(line, flush=True)


# ============================================================ 1. 源码静态侧
def view_facts():
    """扫 app/**.py + scripts/**.py，产出 {func: {file, line, guards, csrf_exempt, keys}}。

    只做静态事实采集，不改动任何文件；用于补 url_map 给不出的权限/CSRF 信息。
    """
    facts = {}
    for base in SCAN_DIRS:
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in ('__pycache__', '.git')]
            for fn in sorted(filenames):
                if not fn.endswith('.py'):
                    continue
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, ROOT).replace('\\', '/')
                try:
                    text = open(full, encoding='utf-8').read()
                    tree = ast.parse(text)
                except Exception:
                    continue
                lines = text.splitlines()
                for node in ast.walk(tree):
                    if not isinstance(node, ast.FunctionDef):
                        continue
                    guards, exempt = [], False
                    for dec in node.decorator_list:
                        src = ast.get_source_segment(text, dec) or ''
                        if 'require_capability' in src:
                            caps = [a.value for a in getattr(dec, 'args', [])
                                    if isinstance(a, ast.Constant)]
                            guards.append('capability:' + ','.join(caps))
                        elif 'require_roles' in src or 'admin_required' in src:
                            guards.append('role_deco')
                        elif 'login_required' in src:
                            guards.append('login_required')
                        if 'csrf.exempt' in src:
                            exempt = True
                    body = '\n'.join(lines[node.lineno - 1:node.lineno + 39])
                    if re.search(r'current_user\.role\s+(not\s+)?in|current_user\.role\s*[!=]=',
                                 body):
                        guards.append('inline_role_check')
                    keys = set()
                    for sub in ast.walk(node):
                        if not isinstance(sub, ast.Subscript):
                            continue
                        v = sub.value
                        if not (isinstance(v, ast.Attribute) and isinstance(v.value, ast.Name)
                                and v.value.id == 'request'):
                            continue
                        attr = v.attr
                        if attr not in PROBE_KEYS_IN_SOURCE:
                            continue
                        sl = sub.slice
                        if isinstance(sl, ast.Index):  # py3.8 兼容
                            sl = sl.value
                        if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
                            keys.add(sl.value)
                    for kw in ('json', 'form', 'values', 'args'):
                        if f'request.{kw}.get(' in body:
                            for m in re.finditer(rf"request\.{kw}\.get\(\s*'([^']+)'", body):
                                keys.add(m.group(1))
                            for m in re.finditer(rf'request\.{kw}\.get\(\s*"([^"]+)"', body):
                                keys.add(m.group(1))
                    facts.setdefault(node.name, {
                        'file': rel, 'line': node.lineno, 'guards': guards,
                        'csrf_exempt': exempt, 'keys': sorted(keys)})
    return facts


# ============================================================ 2. 端点清单
def view_function(endpoint):
    return endpoint.rsplit('.', 1)[-1]


def build_inventory(app, facts):
    """把 url_map 转成端点清单（方法级 + 规则级），并解析出可请求的 URL。"""
    import smoke_test  # scripts/ 已在 _env 的 sys.path 上

    ids = smoke_test.first_ids(app)
    rules, method_level, unresolved = [], [], []
    for rule in app.url_map.iter_rules():
        if rule.endpoint == 'static' or rule.endpoint.startswith(SKIP_ENDPOINT_PREFIX) \
                or rule.endpoint.startswith('static.'):
            continue
        methods = sorted(m for m in rule.methods if m in ('GET', 'POST', 'PUT', 'DELETE', 'PATCH'))
        func = view_function(rule.endpoint)
        fact = facts.get(func, {})
        entry = {
            'rule': str(rule), 'endpoint': rule.endpoint, 'methods': methods,
            'has_args': bool(rule.arguments), 'args': sorted(rule.arguments),
            'file': fact.get('file'), 'line': fact.get('line'),
            'guards': fact.get('guards', []), 'csrf_exempt': fact.get('csrf_exempt', False),
            'form_keys': fact.get('keys', []),
            'path': str(rule),
        }
        real_url, why = None, None
        if rule.arguments:
            real_url, why = smoke_test.resolve_url(rule, ids)
            if real_url is None:
                real_url = str(rule)
                for arg in rule.arguments:
                    real_url = real_url.replace(f'<int:{arg}>', str(SENTINEL_INT))
                    real_url = real_url.replace(f'<string:{arg}>', SENTINEL_STR)
                    real_url = real_url.replace(f'<{arg}>', SENTINEL_STR)
                entry['args_unresolved'] = why
        else:
            real_url = str(rule)
        entry['url_real'] = real_url
        sentinel_url = re.sub(r'<int:(\w+)>', str(SENTINEL_INT), str(rule))
        sentinel_url = re.sub(r'<string:(\w+)>', SENTINEL_STR, sentinel_url)
        sentinel_url = re.sub(r'<(?:path|any)?:?(\w+)>', SENTINEL_STR, sentinel_url)
        entry['url_sentinel'] = sentinel_url
        entry['skipped_reason'] = None
        if str(rule) in SKIP_PATH:
            entry['skipped_reason'] = 'SKIP_PATH（登出/注册：改状态且与业务契约无关）'
            unresolved.append((str(rule), entry['skipped_reason']))
            rules.append(entry)
            continue
        rules.append(entry)
        if not methods:
            continue
        for m in methods:
            method_level.append({'rule': str(rule), 'endpoint': rule.endpoint, 'method': m,
                                 'url_real': real_url, 'url_sentinel': sentinel_url,
                                 'kind': 'read' if m == 'GET' else 'write',
                                 'guards': entry['guards'], 'csrf_exempt': entry['csrf_exempt'],
                                 'file': entry['file'], 'line': entry['line'],
                                 'form_keys': entry['form_keys']})
    return rules, method_level, unresolved


# ============================================================ 3. 磁盘/库指纹
def db_fingerprint(app, tables):
    from app import db
    out = {}
    with app.app_context():
        for t in tables:
            try:
                out[t] = db.session.execute(db.text(f'SELECT COUNT(*) FROM {t}')).scalar()
            except Exception as e:
                out[t] = f'ERR:{e.__class__.__name__}'
    return out


def all_tables(app):
    from app import db
    with app.app_context():
        rows = db.session.execute(db.text(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")).fetchall()
    return [r[0] for r in rows]


def uploads_temp_state():
    d = os.path.join(ROOT, 'uploads', 'temp')
    if not os.path.isdir(d):
        return {'exists': False, 'files': [], 'count': 0}
    files = []
    for fn in sorted(os.listdir(d)):
        p = os.path.join(d, fn)
        if os.path.isfile(p):
            files.append({'name': fn, 'bytes': os.path.getsize(p)})
    return {'exists': True, 'files': files, 'count': len(files)}


# ============================================================ 4. 响应判定
def verdict_of_response(r):
    """把响应判成 ``allow`` / ``deny`` / ``anon_redirect`` / ``error`` / ``empty``。

    关键：**2xx 不等于放行**（表单型端点用 flash+302 表达拒绝），必须双判据：
    状态码 + 正文（``success:false`` / 拒绝词 / 空正文）。
    """
    code = r.status_code
    ctype = (r.headers.get('Content-Type') or '').split(';')[0].strip().lower()
    try:
        body = r.get_data(as_text=True)
    except Exception:
        body = ''
    loc = r.headers.get('Location', '')
    info = {'code': code, 'ctype': ctype, 'location': loc, 'body_len': len(body),
            'body_head': body[:200].replace('\n', ' ')}
    if code in (401, 403):
        return 'deny', info
    if code == 400:
        return 'deny', info
    if code == 404:
        return 'notfound', info
    if code in (301, 302, 303, 307, 308):
        # 登录页有两种等价形态：/auth/login 与 /auth/（auth 蓝图把 login 同时挂在
        # `/login` 和 `/` 上，`login_view='auth.login'` 实际产出的是 `/auth/?next=...`）
        if loc.rstrip('/').endswith('/auth') or '/auth/login' in loc or loc.startswith('/auth/'):
            return 'anon_redirect', info
        return 'redirect', info
    if code >= 500:
        return 'error', info
    low = body.lower()
    try:
        parsed = json.loads(body)
        if isinstance(parsed, dict):
            if parsed.get('success') is False:
                return 'deny', info
            if 'error' in parsed or ('message' in parsed and '成功' not in str(parsed.get('message'))):
                return 'deny', info
    except Exception:
        parsed = None
    if any(h in body for h in DENY_HINT):
        return 'deny', info
    if code == 200 and len(body.strip()) == 0:
        return 'empty', info
    if code in (200, 201, 204):
        return 'allow', info
    return 'other', info


def wants_json_url(url):
    return url.startswith(API_PREFIX)


def probe_kind_ok(kind, is_api, code):
    """契约期望（AC-03/04/10 + JSON API 约定）。返回 (ok, expected_note)。"""
    if is_api:
        return code in (200, 201, 204, 400, 401, 403, 404, 405, 409, 415, 422), \
            'JSON API：2xx 或 4xx(≠5xx/3xx)'
    return code in (200, 201, 204, 302, 303, 400, 401, 403, 404, 405, 409, 415, 422), \
        'HTML/表单：2xx 或 3xx(登录/首页) 或 4xx'


# ============================================================ 5. 主流程
def main():
    started = time.time()
    result = {
        'task': 't4', 'runner': 'test-reports-2026-10/harness/api_matrix.py',
        'run_id': _env.RUN_ID, 'started_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'real_db_path': os.path.relpath(REAL_DB, ROOT).replace('\\', '/'),
        'real_db_sha256_pinned': _env.REAL_DB_SHA256_EXPECTED,
    }
    log('=' * 78)
    log('t4 API / 写端点安全实测矩阵')
    log(f'run_id={_env.RUN_ID}  真实库={result["real_db_path"]}')
    sha0 = sha256_file(REAL_DB)
    log(f'[真实库] 开工 SHA256 = {sha0}  (钉死命中={sha0 == _env.REAL_DB_SHA256_EXPECTED})')
    result['real_db_sha256_before'] = sha0
    assert_real_db_untouched('t4 开工')
    up0 = uploads_temp_state()

    import _test_bootstrap
    app, copy_path = fixtures.make_isolated_app('t4')
    seeded = fixtures.seed_all(app)
    from _test_bootstrap import login_as
    users, password = seeded['users'], seeded['password']
    uri = app.config.get('SQLALCHEMY_DATABASE_URI')
    log(f'[副本] {copy_path}')
    log(f'[副本] URI={uri}')
    log(f'[副本] samefile(真实库)={os.path.samefile(copy_path, REAL_DB)}')
    log(f'[副本] SHA256={sha256_file(copy_path)}')
    log(f'[身份] users={users}')
    log(f'[配置] WTF_CSRF_ENABLED={app.config.get("WTF_CSRF_ENABLED")} '
        f'TESTING={app.config.get("TESTING")} DEBUG={app.config.get("DEBUG")}')
    result['copy'] = {'path': copy_path, 'uri': uri, 'sha256': sha256_file(copy_path),
                      'samefile_real': os.path.samefile(copy_path, REAL_DB),
                      'seed': seeded['seeded'], 'users': users,
                      'config': {'WTF_CSRF_ENABLED': app.config.get('WTF_CSRF_ENABLED'),
                                 'TESTING': app.config.get('TESTING'),
                                 'PROPAGATE_EXCEPTIONS': app.config.get('PROPAGATE_EXCEPTIONS')}}

    facts = view_facts()
    log(f'[静态] 扫到视图函数 {len(facts)} 个（app/ + scripts/ 全树 AST）')
    rules, method_level, unresolved = build_inventory(app, facts)
    n_get = sum(1 for e in method_level if e['method'] == 'GET')
    n_write = sum(1 for e in method_level if e['kind'] == 'write')
    n_write_rules = len({e['rule'] for e in method_level if e['kind'] == 'write'})
    log(f'[分母] 规则 {len(rules)}（非 GET {n_write_rules}） / 方法级 {len(method_level)}'
        f'（GET {n_get} / 非 GET {n_write}）')
    log(f'[分母] 无法解析真实 id 的规则 {len(unresolved)} 条（退化为哨兵 URL）')
    result['denominators'] = {'rules_total': len(rules), 'non_get_rules': n_write_rules,
                              'method_level_total': len(method_level), 'method_level_get': n_get,
                              'method_level_non_get': n_write,
                              'unresolved_arg_rules': len(unresolved)}
    result['inventory'] = rules
    result['method_level'] = method_level
    result['unresolved'] = [{'rule': r, 'why': w} for r, w in unresolved]

    tables = all_tables(app)
    fp_before = db_fingerprint(app, tables)
    result['tables'] = tables

    # ---------------------------------------------------------------- 矩阵 A：匿名
    log('')
    log('=' * 78)
    log('矩阵 A：匿名（未登录）访问全部端点 —— AC-03')
    anon = app.test_client()
    rows_a, fails_a = [], []
    for e in method_level:
        url = e['url_real']
        is_api = wants_json_url(url)
        try:
            r = anon.open(url, method=e['method'], follow_redirects=False)
        except Exception as ex:
            rows_a.append({'rule': e['rule'], 'method': e['method'], 'exc': ex.__class__.__name__,
                           'url': url})
            fails_a.append({'id': f'A-{e["method"]}-{e["rule"]}', 'why': 'EXC ' + ex.__class__.__name__})
            continue
        v, info = verdict_of_response(r)
        row = {'rule': e['rule'], 'endpoint': e['endpoint'], 'method': e['method'], 'url': url,
               'is_api': is_api, 'verdict': v, 'code': info['code'], 'ctype': info['ctype'],
               'location': info['location'], 'body_head': info['body_head'],
               'guards': e['guards']}
        rows_a.append(row)
        # 硬违规（不可接受）：匿名被放行 / 空 200 / 5xx / 重定向到非登录页
        if v in ('allow', 'empty', 'error'):
            fails_a.append({'id': f'A-{e["method"]}-{e["rule"]}',
                            'why': f'匿名被放行或异常（verdict={v} code={info["code"]}）', 'row': row})
        elif v == 'redirect':
            fails_a.append({'id': f'A-{e["method"]}-{e["rule"]}',
                            'why': f'匿名重定向到非登录页：{info["location"]}', 'row': row})
    # 软观测：/api/ JSON 端点匿名时给的不是 401 JSON（可能 403/302），单列不判违规
    api_soft = [r for r in rows_a if r['is_api'] and r['verdict'] != 'deny'
                and r['verdict'] != 'notfound']
    n_allow_anon = sum(1 for r in rows_a if r['verdict'] == 'allow')
    log(f'  端点 {len(rows_a)}：allow={n_allow_anon} / '
        f'deny={sum(1 for r in rows_a if r["verdict"]=="deny")} / '
        f'anon_redirect={sum(1 for r in rows_a if r["verdict"]=="anon_redirect")} / '
        f'notfound={sum(1 for r in rows_a if r["verdict"]=="notfound")} / '
        f'error={sum(1 for r in rows_a if r["verdict"]=="error")} / '
        f'other={sum(1 for r in rows_a if r["verdict"]=="other")}')
    log(f'  => 硬违规 {len(fails_a)} 条 / 软观测（/api 非 401 JSON）{len(api_soft)} 条')
    for row in [r for r in rows_a if r['verdict'] == 'allow'][:8]:
        log(f'     匿名被放行: {row["method"]:6s} {row["rule"]}  -> {row["code"]} '
            f'{row["ctype"]} guards={row["guards"]}')
    for row in api_soft[:8]:
        log(f'     /api 非 401: {row["method"]:6s} {row["rule"]}  -> {row["code"]} {row["ctype"]}')
    result['matrix_a_anonymous'] = {'rows': rows_a, 'violations': fails_a,
                                    'allow_count': n_allow_anon,
                                    'api_non_401_observations': len(api_soft)}

    # ---------------------------------------------------------------- 矩阵 B：低权写
    log('')
    log('=' * 78)
    log('矩阵 B：低权/中权身份对写端点的越权控制 —— AC-04')
    low_roles = [r for r in ('user', 'sales', 'accountant', 'inspector', 'hr') if r in users]
    CAP_ROLES.clear()
    CAP_ROLES.update(cap_roles())
    log(f'  能力表载入 {len(CAP_ROLES)} 项（capability -> roles）；'
        f'「低权被放行」仅在角色不在登记表内时判违规')
    clients = {}
    for role in low_roles:
        c = app.test_client()
        login_as(c, users[role], password)
        clients[role] = c
    writes = [e for e in method_level if e['kind'] == 'write']
    log(f'  低权身份 {low_roles} × 写端点 {len(writes)} 条（空表单体，避免触发真实写入路径）')
    rows_b, fails_b = [], []
    for e in writes:
        for role, c in clients.items():
            try:
                r = c.open(e['url_real'], method=e['method'], follow_redirects=False)
            except Exception as ex:
                rows_b.append({'rule': e['rule'], 'method': e['method'], 'role': role,
                               'exc': ex.__class__.__name__})
                continue
            v, info = verdict_of_response(r)
            rows_b.append({'rule': e['rule'], 'endpoint': e['endpoint'], 'method': e['method'],
                           'role': role, 'url': e['url_real'], 'verdict': v, 'code': info['code'],
                           'ctype': info['ctype'], 'location': info['location'],
                           'body_head': info['body_head'], 'guards': e['guards'],
                           'csrf_exempt': e['csrf_exempt']})
            if v == 'error':
                fails_b.append({'id': f'B-{e["method"]}-{e["rule"]}-{role}',
                                'why': f'低权写请求触发 5xx（code={info["code"]}）',
                                'severity': 'high', 'row': rows_b[-1]})
            elif v == 'allow':
                # 「低权被放行」只有在**该角色确实不具备所需能力**时才算违规：
                # 例如 hr 含 task.manage、sales 含 customer.manage/sales_order.manage，
                # 它们能写是设计意图（permissions.py CAPABILITIES），不是越权。
                role_caps = caps_of(facts, e['endpoint'])
                if role_caps and any(role in CAP_ROLES.get(cap, ()) for cap in role_caps):
                    rows_b[-1]['allow_is_by_design'] = True
                else:
                    fails_b.append({'id': f'B-{e["method"]}-{e["rule"]}-{role}',
                                    'why': f'低权角色 {role} 的写请求被放行，且该角色不在'
                                           f'所需能力登记表内（guards={e["guards"]}）',
                                    'severity': 'high', 'row': rows_b[-1]})
    def _cnt(key):
        return sum(1 for r in rows_b if r.get('verdict') == key)
    log(f'  请求 {len(rows_b)} 条：allow={_cnt("allow")} / deny={_cnt("deny")} / '
        f'redirect={_cnt("redirect") + _cnt("anon_redirect")} / notfound={_cnt("notfound")} / '
        f'error={_cnt("error")} / exc={sum(1 for r in rows_b if "exc" in r)}')
    n_allow_b = _cnt('allow')
    log(f'  => 低权写请求被放行 {n_allow_b} 条 / 5xx {len(fails_b)} 条')
    result['matrix_b_lowpriv_write'] = {'rows': rows_b, 'violations': fails_b,
                                        'allowed_count': n_allow_b, 'roles': low_roles}

    # ---------------------------------------------------------------- 矩阵 C：畸形 URL
    log('')
    log('=' * 78)
    log('矩阵 C：带参端点的畸形/不存在资源（404/400 而非 500/200）—— AC-10')
    admin = app.test_client()
    login_as(admin, users['admin'], password)
    rows_c, fails_c = [], []
    arg_rules = [e for e in method_level if e['rule'] in {x['rule'] for x in rules if x['has_args']}]
    for e in arg_rules:
        url = e['url_sentinel']
        is_api = wants_json_url(url)
        try:
            r = admin.open(url, method=e['method'], follow_redirects=False)
        except Exception as ex:
            rows_c.append({'rule': e['rule'], 'method': e['method'], 'url': url,
                           'exc': ex.__class__.__name__})
            fails_c.append({'id': f'C-{e["method"]}-{e["rule"]}', 'kind': '异常',
                            'severity': 'high',
                            'why': 'EXC ' + ex.__class__.__name__})
            continue
        v, info = verdict_of_response(r)
        ok, note = probe_kind_ok(v, is_api, info['code'])
        row = {'rule': e['rule'], 'endpoint': e['endpoint'], 'method': e['method'], 'url': url,
               'is_api': is_api, 'verdict': v, 'code': info['code'], 'ctype': info['ctype'],
               'body_head': info['body_head'], 'contract_ok': ok, 'contract_note': note}
        rows_c.append(row)
        if not ok:
            fails_c.append({'id': f'C-{e["method"]}-{e["rule"]}',
                            'severity': 'high' if is_api else 'medium',
                            'kind': ('JSON 契约' if is_api else 'HTML 契约'),
                            'why': f'畸形/不存在资源 code={info["code"]}（{note}）',
                            'row': row})
    log(f'  带参端点请求 {len(rows_c)} 条：contract_ok={sum(1 for r in rows_c if r.get("contract_ok"))}'
        f' / 违规 {len(fails_c)}（JSON {sum(1 for v in fails_c if v.get("kind") == "JSON 契约")} / '
        f'HTML {sum(1 for v in fails_c if v.get("kind") == "HTML 契约")} / '
        f'异常 {sum(1 for v in fails_c if v.get("kind") == "异常")}）')
    # 404 覆盖统计：带参端点里有多少条对「不存在的 id」给出了 404
    n_404 = sum(1 for r in rows_c if r.get('code') == 404)
    log(f'  其中 404（正确语义）{n_404} 条；500 {sum(1 for r in rows_c if r.get("code") == 500)} 条')
    result['matrix_c_malformed_url'] = {'rows': rows_c, 'violations': fails_c,
                                        'count_404': n_404}

    # ---------------------------------------------------------------- 矩阵 D：载荷安全
    log('')
    log('=' * 78)
    log('矩阵 D：写端点载荷形态（空体 / 类型混淆 / 不存在的 id）—— 禁 5xx')
    shapes = {
        'D1_empty': {'data': {}},
        'D2_type_confusion': {'json': None},   # 现填
        'D3_nonexistent_ids': {'json': None},
    }
    rows_d, fails_d = [], []
    fp_d_before = db_fingerprint(app, tables)
    for e in writes:
        keys = [k for k in (e.get('form_keys') or [])
                if k not in ('csrf_token', 'submit', 'action')]
        # D1 空表单体；D2 每个已发现键给错类型；D3 每个键给「不存在的 id / 哨兵串」
        d1_body = {}
        d2_body = {k: 'x' for k in keys}
        d3_body = {}
        for k in keys:
            d3_body[k] = SENTINEL_INT if k.endswith(('_id', '_ids', 'id', 'quantity',
                                                     'amount', 'price', 'qty', 'page')) \
                else SENTINEL_STR
        bodies = {'D1_empty': ('data', d1_body), 'D2_type_confusion': ('json', d2_body),
                  'D3_nonexistent_ids': ('json', d3_body)}
        for shape, (kw_key, body) in bodies.items():
            kw = {kw_key: body}
            try:
                r = admin.open(e['url_real'], method=e['method'], follow_redirects=False, **kw)
            except Exception as ex:
                rows_d.append({'rule': e['rule'], 'method': e['method'], 'shape': shape,
                               'url': e['url_real'], 'keys': keys, 'exc': ex.__class__.__name__})
                fails_d.append({'id': f'D-{shape}-{e["method"]}-{e["rule"]}',
                                'why': 'EXC ' + ex.__class__.__name__, 'severity': 'high'})
                continue
            v, info = verdict_of_response(r)
            leak = bool(EXC_PAT.search(info['body_head']))
            row = {'rule': e['rule'], 'endpoint': e['endpoint'], 'method': e['method'],
                   'shape': shape, 'url': e['url_real'], 'body_keys': keys, 'verdict': v,
                   'code': info['code'], 'ctype': info['ctype'], 'body_head': info['body_head'],
                   'error_text_leak': leak,
                   'html_on_api': is_api_html_leak(e['url_real'], info)}
            rows_d.append(row)
            if info['code'] >= 500:
                fails_d.append({'id': f'D-{shape}-{e["method"]}-{e["rule"]}',
                                'why': f'写端点畸形载荷返回 {info["code"]}', 'severity': 'high',
                                'row': row})
            if leak:
                fails_d.append({'id': f'D-leak-{shape}-{e["method"]}-{e["rule"]}',
                                'why': '响应正文疑似泄漏异常类名/Traceback（信息泄漏）',
                                'severity': 'medium', 'row': row})
            if row['html_on_api']:
                fails_d.append({'id': f'D-html-{shape}-{e["method"]}-{e["rule"]}',
                                'why': f'/api/ 端点返回非 JSON（{info["ctype"]}）',
                                'severity': 'medium', 'row': row})
    fp_d_after = db_fingerprint(app, tables)
    delta = {t: (fp_d_before.get(t), fp_d_after.get(t)) for t in tables
             if fp_d_before.get(t) != fp_d_after.get(t)}
    n_allow_d = sum(1 for r in rows_d if r.get('verdict') == 'allow')
    n_5xx_d = sum(1 for r in rows_d if r.get('code', 0) >= 500)
    log(f'  请求 {len(rows_d)} 条（{len(writes)} 写端点 × 3 形态）：allow={n_allow_d} / '
        f'5xx={n_5xx_d} / '
        f'异常文本泄漏={sum(1 for r in rows_d if r.get("error_text_leak"))} / '
        f'违规 {len(fails_d)} 条')
    log(f'  载荷前后逐表行数变化：{len(delta)} 张表 ({list(delta)[:6]}'
        f'{"…" if len(delta) > 6 else ""})')
    result['matrix_d_payload'] = {'rows': rows_d, 'violations': fails_d,
                                 'row_delta_tables': {k: {'before': v[0], 'after': v[1]}
                                                      for k, v in delta.items()},
                                 'allowed_count': n_allow_d}

    # ---------------------------------------------------------------- 矩阵 E：契约审计
    log('')
    log('=' * 78)
    log('矩阵 E：HTTP 契约面（JSON API 不得返回 HTML / 错误体形状）')
    json_rows, json_fails, json_observations = [], [], []
    api_urls = sorted({e['url_real'] for e in method_level if wants_json_url(e['url_real'])})
    for url in api_urls:
        try:
            r = admin.get(url, follow_redirects=False)
        except Exception as ex:
            json_rows.append({'url': url, 'exc': ex.__class__.__name__})
            continue
        try:
            body = r.get_data(as_text=True)
        except Exception:
            body = ''
        ctype = (r.headers.get('Content-Type') or '')
        parsed_ok, parsed = False, None
        if 'json' in ctype.lower():
            try:
                parsed = json.loads(body)
                parsed_ok = True
            except Exception:
                parsed_ok = False
        row = {'url': url, 'code': r.status_code, 'ctype': ctype.split(';')[0],
               'json_parsable': parsed_ok,
               'body_head': body[:180].replace('\n', ' '),
               'html_detected': '<!DOCTYPE' in body[:400] or '<html' in body[:400].lower()}
        json_rows.append(row)
        # 口径：/api/ 前缀下**本应是 JSON** 的端点，若 200 返回 HTML ⇒ 契约破坏（AGENTS.md
        # 「禁止 JSON API 返回 HTML」）。而 xlsx 导出（.xlsx mimetype）与「打印页」
        # （text/html 的渲染视图）本就是非 JSON 载体 ⇒ 单列 observation，不判违规。
        is_binary = ('spreadsheet' in row['ctype'] or 'octet-stream' in row['ctype']
                     or 'pdf' in row['ctype'])
        if r.status_code == 200 and not parsed_ok and not is_binary:
            if row['html_detected']:
                json_fails.append({'id': f'E-html-{url}', 'severity': 'medium',
                                   'why': '/api/ 前缀端点返回 HTML（契约：JSON API 不得返回 HTML）',
                                   'row': row})
            else:
                json_fails.append({'id': f'E-json-{url}', 'severity': 'low',
                                   'why': f'/api/ 200 但非 JSON/非二进制（{row["ctype"]}）',
                                   'row': row})
        elif is_binary:
            json_observations.append({'id': f'E-bin-{url}',
                                      'why': f'/api/ 前缀下的二进制下载端点（{row["ctype"]}）'
                                             f'—— 非 JSON 属设计，登记为观测',
                                      'row': row})
    log(f'  /api/ 端点 {len(json_rows)} 条：可解析 JSON {sum(1 for r in json_rows if r.get("json_parsable"))}'
        f' / 契约违规 {len(json_fails)} / 非 JSON 设计观测 {len(json_observations)}'
        f'（二进制下载 {sum(1 for o in json_observations if "spreadsheet" in o["row"]["ctype"])} 条）')
    result['matrix_e_json_contract'] = {'rows': json_rows, 'violations': json_fails,
                                        'observations': json_observations}

    # ---------------------------------------------------------------- 矩阵 F：CSRF
    log('')
    log('=' * 78)
    log('矩阵 F：CSRF 防护实测（**同一 app 内临时打开 WTF_CSRF_ENABLED**）')
    csrf_result = csrf_matrix(app, facts)
    result['matrix_f_csrf'] = csrf_result

    # ---------------------------------------------------------------- 收尾指纹
    fp_after = db_fingerprint(app, tables)
    # 阶段 D 已有 delta，这里记录全程
    full_delta = {t: {'before': fp_before.get(t), 'after': fp_after.get(t)}
                  for t in tables if fp_before.get(t) != fp_after.get(t)}
    up1 = uploads_temp_state()
    sha1 = sha256_file(REAL_DB)
    result['real_db_sha256_after'] = sha1
    result['real_db_unchanged'] = sha1 == _env.REAL_DB_SHA256_EXPECTED
    result['copy_row_delta_full'] = full_delta
    result['uploads_temp'] = {'before': up0, 'after': up1,
                              'unchanged': up0 == up1}
    log('')
    log('=' * 78)
    log(f'[收尾] 真实库 SHA256 = {sha1}  未变={result["real_db_unchanged"]}')
    log(f'[收尾] 副本逐表行数变化 {len(full_delta)} 张表')
    log(f'[收尾] uploads/temp 未变={result["uploads_temp"]["unchanged"]} '
        f'(before={up0["count"]} files / after={up1["count"]} files)')
    assert_real_db_untouched('t4 收尾')

    # ---------------------------------------------------------------- 覆盖分母
    executed = {}
    for e in method_level:
        executed.setdefault(e['rule'], {'GET': False, 'POST': False, 'PUT': False,
                                        'DELETE': False, 'PATCH': False})
    for row in rows_a:
        if 'rule' in row and 'method' in row:
            executed.setdefault(row['rule'], {})[row['method']] = True
    for row in rows_c:
        executed.setdefault(row['rule'], {})[row['method']] = True
    for row in rows_d:
        executed.setdefault(row['rule'], {})[row['method']] = True
    for row in rows_b:
        executed.setdefault(row['rule'], {})[row['method']] = True
    n_w_exec = sum(1 for e in method_level if e['kind'] == 'write'
                   and executed.get(e['rule'], {}).get(e['method']))
    n_w_not = sum(1 for e in method_level if e['kind'] == 'write'
                  and not executed.get(e['rule'], {}).get(e['method']))
    result['coverage'] = {'methods_probed_non_get': n_w_exec,
                          'methods_not_probed_non_get': n_w_not,
                          'total_non_get': n_write}
    log(f'[覆盖] 非 GET 方法级被探针实际命中 {n_w_exec}/{n_write}（未命中 {n_w_not}）')
    for e in method_level:
        if e['kind'] == 'write' and not executed.get(e['rule'], {}).get(e['method']):
            log(f'        未命中: {e["method"]:6s} {e["rule"]}  [{e["endpoint"]}]')

    # ---------------------------------------------------------------- 汇总
    all_viol = ([{'matrix': 'A', **v} for v in fails_a]
                + [{'matrix': 'B', **v} for v in fails_b]
                + [{'matrix': 'C', **v} for v in fails_c]
                + [{'matrix': 'D', **v} for v in fails_d]
                + [{'matrix': 'E', **v} for v in json_fails]
                + [{'matrix': 'F', **v} for v in csrf_result.get('violations', [])])
    result['violations_total'] = len(all_viol)
    result['violations'] = all_viol
    result['duration_s'] = round(time.time() - started, 1)
    log('')
    log('=' * 78)
    log(f'断言总违规 {len(all_viol)} 条（A={len(fails_a)} B={len(fails_b)} C={len(fails_c)} '
        f'D={len(fails_d)} E={len(json_fails)} F={len(csrf_result.get("violations", []))}）')
    for v in all_viol[:40]:
        log(f'  [{v["matrix"]}] {v.get("id")}  {v.get("why")}')
    if len(all_viol) > 40:
        log(f'  … 其余 {len(all_viol) - 40} 条见 api_matrix.json')
    log(f'总耗时 {result["duration_s"]}s')

    os.makedirs(EVID, exist_ok=True)
    with open(os.path.join(EVID, 'api_matrix.json'), 'w', encoding='utf-8', newline='\n') as fh:
        json.dump(result, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(EVID, 'api_matrix.out.txt'), 'w', encoding='utf-8', newline='\n') as fh:
        fh.write('\n'.join(_LOG) + '\n')
    log(f'[落盘] {EVID}/api_matrix.json + api_matrix.out.txt')
    return 0


def caps_of(facts, endpoint):
    """视图声明的能力（``require_capability(...)`` 的实参），供权限判据使用。"""
    f = facts.get(view_function(endpoint), {})
    out = []
    for g in f.get('guards', []):
        if g.startswith('capability:'):
            out += [c for c in g.split(':', 1)[1].split(',') if c]
    return out


def cap_roles():
    """``permissions.CAPABILITIES`` 的能力→角色表（运行时读，不复制常量）。"""
    try:
        from app.permissions import CAPABILITIES
        return {k: tuple(v) for k, v in CAPABILITIES.items()}
    except Exception:
        return {}


CAP_ROLES = {}


def is_api_html_leak(url, info):
    if not wants_json_url(url):
        return False
    body = info.get('body_head', '')
    return ('<html' in body.lower() or '<!doctype' in body.lower()) and info['code'] >= 400


# ============================================================ CSRF 矩阵
def csrf_matrix(app, facts):
    """**在同一个 app 上临时打开 CSRF**：验证「缺 token 的非 GET 请求被拒」。

    为什么不再另建 app：flask_sqlalchemy 3.x 的全局 ``db`` 只能 ``init_app`` 到一个 app，
    同一进程里交替用两个 app 的 ``app_context()`` 会抛
    ``RuntimeError: The current Flask app is not registered with this 'SQLAlchemy' instance``
    （实测踩到）。而 ``WTF_CSRF_ENABLED`` 是**请求时读**的配置项
    （``flask_wtf/csrf.py: CSRFProtect.protect`` 每次请求读 ``app.config``），
    因此在同一 app 上临时改配置即可，无需第二个 app。

    正例（判定装置有效性）：带合法 token 提交表单 → 不再是 CSRF 400；
    不变量：GET 不受 CSRF 影响（CSRFProtect 只作用于非安全方法）。
    """
    from _test_bootstrap import login_as
    orig = bool(app.config.get('WTF_CSRF_ENABLED'))
    c = app.test_client()
    with app.app_context():
        admin = _model_admin()
    login_as(c, admin.username, 'test_pw_123')

    out = {'enabled_original': orig, 'enabled_during_probe': True,
           'rows': [], 'violations': [], 'positive_control': {}, 'get_control': {},
           'note': '同一 app 内临时打开 WTF_CSRF_ENABLED（请求时读取），测完还原'}
    app.config['WTF_CSRF_ENABLED'] = True
    try:
        r = c.get('/tasks')
        out['get_control'] = {'url': '/tasks', 'code': r.status_code}
        log(f'  [F] 不变量：GET /tasks = {r.status_code}（CSRF 只作用于非安全方法）')

        page = c.get('/tasks/add')
        m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page.get_data(as_text=True))
        out['positive_control']['token_found'] = bool(m)
        if m:
            token = m.group(1)
            r2 = c.post('/tasks/add', data={'csrf_token': token, 'name': '_t4_csrf_probe'},
                        follow_redirects=False)
            out['positive_control']['post_with_token'] = {
                'url': '/tasks/add', 'code': r2.status_code,
                'location': r2.headers.get('Location', '')}
            ok = r2.status_code != 400
            out['positive_control']['verdict'] = (
                'CSRF 判定装置有效（带合法 token 不再是 400）' if ok
                else '带 token 仍 400 => 判定装置可疑')
            log(f'  [F] 正例：POST /tasks/add + 合法 token → {r2.status_code}'
                f'（{out["positive_control"]["verdict"]}）')
        else:
            out['positive_control']['verdict'] = '未取到 csrf_token（页面无表单或未渲染）'

        import smoke_test
        ids = smoke_test.first_ids(app)
        n_w = n_ok = n_bad = 0
        for rule in app.url_map.iter_rules():
            if rule.endpoint == 'static' or rule.endpoint in SKIP_ENDPOINT_PREFIX:
                continue
            methods = sorted(m for m in rule.methods if m in ('POST', 'PUT', 'DELETE', 'PATCH'))
            if not methods:
                continue
            func = view_function(rule.endpoint)
            exempt = facts.get(func, {}).get('csrf_exempt', False)
            url = str(rule)
            if rule.arguments:
                url, _ = smoke_test.resolve_url(rule, ids)
                if url is None:
                    url = re.sub(r'<int:\w+>', str(SENTINEL_INT), str(rule))
                    url = re.sub(r'<string:\w+>', SENTINEL_STR, url)
                    url = re.sub(r'<(?:path|any)?:?\w+>', SENTINEL_STR, url)
            for meth in methods:
                n_w += 1
                try:
                    r = c.open(url, method=meth, data={}, follow_redirects=False)
                except Exception as ex:
                    out['rows'].append({'rule': str(rule), 'method': meth, 'url': url,
                                        'exempt': exempt, 'exc': ex.__class__.__name__})
                    continue
                body = r.get_data(as_text=True)
                csrf_blocked = r.status_code == 400 and ('csrf' in body.lower()
                                                         or '令牌' in body or 'Token' in body)
                row = {'rule': str(rule), 'endpoint': rule.endpoint, 'method': meth, 'url': url,
                       'exempt': exempt, 'code': r.status_code, 'csrf_blocked': csrf_blocked,
                       'body_head': body[:160].replace('\n', ' ')}
                out['rows'].append(row)
                if exempt or csrf_blocked:
                    n_ok += 1
                    continue
                n_bad += 1
                out['violations'].append({
                    'id': f'F-{meth}-{rule}', 'rule': str(rule), 'method': meth,
                    'code': r.status_code,
                    'why': f'非 GET 端点未声明 @csrf.exempt 却未在缺 token 时被 CSRF 拦'
                           f'（code={r.status_code}）', 'severity': 'high'})
        out['summary'] = {'probed': n_w, 'enforced_or_exempt': n_ok, 'not_enforced': n_bad}
        log(f'  [F] 非 GET 探针 {n_w} 条：期望被拒/豁免命中 {n_ok} 条，未拦 {n_bad} 条')
    finally:
        app.config['WTF_CSRF_ENABLED'] = orig
    return out


def _model_admin():
    from app import models as M
    return M.User.query.filter_by(username='_t_admin').first() or M.User.query.first()



if __name__ == '__main__':
    sys.exit(main())
