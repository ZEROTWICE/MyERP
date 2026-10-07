"""r2_csrf_probe.py — C-03 CSRF 拦截面判据（V-09 / B4；新增文件，运行于 CH-2 副本）。

**为什么重写判据**（A-69）：W4 的统一 `errorhandler(HTTPException)`（`app/__init__.py:205`）接手了
CSRF 失败的响应构造，于是「断 `CSRFError` 的**自然语言文案**」的 24 条旧判据**失效**，但**拦截行为
仍在**。⇒ 判据必须改断「**状态码 + 机读标记**」，一律**不得**断自然语言文案。

**本探针的机读标记（三条，全部与文案无关）**
  M1 `status == 400`              —— CSRF 失败的 HTTP 状态（`CSRFError` 是 `BadRequest`）；
  M2 `view_invoked is False`      —— **拦截信号**：派发层计数包装器（`functools.wraps` 保号）证明
                                     请求**没有**走到视图函数（业务 400 必然走视图 ⇒ 与 CSRF 400 可区分）；
  M3 `claims_success is False`    —— 响应体（若为 JSON）**不**声明成功（结构化字段，不读 `message`）。

**口径（与 `06` §4.2 的冻结基线同源）**：`url_map` 重算 **非 GET 方法级站点 155 条**
= `WTF_CSRF_METHODS`（POST/PUT/PATCH/DELETE）∩ `rule.methods`；其中**豁免 22 条**
（`csrf.exempt` 注册表 `app.extensions['csrf']._exempt_views`，**与运行时同一事实来源**，非 AST 文本匹配）
⇒ **非豁免面 133 条**，判据 = **拦截率 133/133**、豁免面**未拦 0**。

**三个相位（同一进程、同一副本）**
  * **A 判据相位**：`WTF_CSRF_ENABLED=True` + **无 token** 空体 ⇒ 非豁免面必须 133/133 被拦；
  * **C 全量控制**：`WTF_CSRF_ENABLED=False` ⇒ 133 条**必须**走到视图（证明 M2 不是「恒 False」的假绿）；
  * **B token 对照**：`WTF_CSRF_ENABLED=True` + **有效 token**（取 `base.html:7` 的
    `<meta name="csrf-token">`，即前端 `X-CSRFToken` 的同一通道）⇒ 抽样 12 条必须走到视图
    （证明 A 的 400 由「缺 token」引起，而非别的 before_request 早退）。

**注入回放（`--inject-endpoint`）**：把该端点的 `dest` 加进 `csrf._exempt_views`（= 运行期放宽
`@csrf.exempt` 的**同一机制**，**不改生产代码**）⇒ 重跑 A 相位：**该条必须转红**，且**只有该条**翻转。
注入模式的退出码语义：`0` = 注入生效且靶向唯一（即「该条真的会红」被证明）；`1` = 未生效/影响面失控。

**双跑对拍（`--compare A B`）**：两份报告 JSON 的 `checks` 判定与逐站点 verdict **必须逐条相同**。

运行（仓库根目录，绝对路径解释器；证据一律走 `_env.save_evidence` 落 `evidence/harness/<RUN_ID>/`）：
    $env:HARNESS_RUN_ID='r2-exec-b4-v09'
    & 'F:\\Miniconda\\envs\\wage\\python.exe' -B test-reports-2026-10\\harness\\r2_csrf_probe.py
    & 'F:\\Miniconda\\envs\\wage\\python.exe' -B test-reports-2026-10\\harness\\r2_csrf_probe.py --inject-endpoint main.add_process_price
    & 'F:\\Miniconda\\envs\\wage\\python.exe' -B test-reports-2026-10\\harness\\r2_csrf_probe.py --compare <a.json> <b.json>
"""
import argparse
import functools
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

for _stream in (sys.stdout, sys.stderr):   # A-14：GBK 控制台不得把「判据失败」与「崩溃」混为一谈
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from _env import EVIDENCE_DIR, REPO_ROOT, ensure_dir, real_db_status, save_evidence   # noqa: E402
import fixtures   # noqa: E402

RUN_ID = os.environ.get('HARNESS_RUN_ID') or 'adhoc-c03'
CSRF_METHODS = ('POST', 'PUT', 'PATCH', 'DELETE')       # 与 WTF_CSRF_METHODS 默认同源
TOKEN_META_RE = re.compile(r'<meta\s+name="csrf-token"\s+content="([^"]+)"')
CONV = {'int': '1', 'float': '1.0', 'path': 'x', 'uuid': '00000000-0000-0000-0000-000000000000'}
#: 判据只读这些字段（**白名单**：不含任何自然语言文案字段）
JUDGED_FIELDS = ('status', 'view_invoked', 'claims_success', 'is_json', 'content_type', 'exempt')


def url_for_rule(rule):
    """把 `<int:id>` 一类占位符换成**能匹配该规则**的常量（不依赖库内数据 ⇒ 155 条全覆盖）。"""
    url = str(rule)
    for m in re.finditer(r'<(?:(\w+):)?(\w+)>', url):
        url = url.replace(m.group(0), CONV.get(m.group(1) or 'string', 'x'), 1)
    return url


def collect_sites(app):
    """非 GET 方法级站点 + 豁免判定（豁免取自 flask_wtf 注册表 = 运行时同一事实来源）。"""
    csrf = app.extensions['csrf']
    exempt_views = set(getattr(csrf, '_exempt_views', set()))
    exempt_bps = set(getattr(csrf, '_exempt_blueprints', set()))
    sites = []
    for rule in app.url_map.iter_rules():
        if rule.endpoint == 'static':
            continue
        for method in sorted(set(rule.methods or set()) - {'HEAD', 'OPTIONS'}):
            if method == 'GET' or method not in CSRF_METHODS:
                continue
            view = app.view_functions.get(rule.endpoint)
            dest = '%s.%s' % (view.__module__, view.__name__) if view else None
            bp = app.blueprints.get(rule.endpoint.rsplit('.', 1)[0])
            sites.append({
                'method': method, 'rule': str(rule), 'endpoint': rule.endpoint,
                'url': url_for_rule(rule), 'dest': dest,
                'exempt': bool((dest in exempt_views) or (bp in exempt_bps)),
            })
    sites.sort(key=lambda s: (s['rule'], s['method'], s['endpoint']))
    return sites


def wrap_views(app):
    """派发层计数包装（M2 拦截信号）。`functools.wraps` **必须**：否则 `view.__module__/__name__`
    改变 ⇒ flask_wtf 的 `dest in _exempt_views` 判定被破坏（豁免面会凭空消失）。"""
    hits = {}
    for endpoint, orig in list(app.view_functions.items()):
        def make(orig, endpoint):
            @functools.wraps(orig)
            def wrapper(*args, **kwargs):
                hits[endpoint] = hits.get(endpoint, 0) + 1
                return orig(*args, **kwargs)
            return wrapper
        app.view_functions[endpoint] = make(orig, endpoint)
    return hits


def send(client, site, hits, headers=None):
    """发一次空体请求（**不带 token**，除非显式给 headers），返回机读记录。"""
    hits.pop(site['endpoint'], None)
    try:
        resp = client.open(site['url'], method=site['method'], data='', headers=headers or {},
                           follow_redirects=False)
        status = resp.status_code
        ctype = (resp.headers.get('Content-Type') or '').split(';')[0].strip().lower()
        payload = resp.get_json(silent=True)
        is_json = isinstance(payload, (dict, list))
        claims_success = bool(payload.get('success')) if isinstance(payload, dict) else False
    except Exception as exc:                      # 单条请求不得让整轮崩
        status, ctype, is_json, claims_success = 'EXC:' + exc.__class__.__name__, '', False, None
    view_invoked = hits.get(site['endpoint'], 0) > 0
    rec = {'status': status, 'content_type': ctype, 'is_json': is_json,
           'claims_success': claims_success, 'view_invoked': view_invoked}
    # M1 + M2 + M3（全部机读；**不含**任何自然语言文案）
    rec['intercepted'] = bool(status == 400 and not view_invoked and not claims_success)
    return rec


def sweep(client, sites, hits, headers=None):
    return {('%s %s' % (s['method'], s['rule'])): send(client, s, hits, headers=headers)
            for s in sites}


def fetch_client_token(client):
    """取前端同一通道的 CSRF token：`base.html:7` 的 `<meta name="csrf-token">`（机读属性提取）。"""
    html = client.get('/').get_data(as_text=True)
    m = TOKEN_META_RE.search(html)
    return m.group(1) if m else None


def build_checks(sites, phase_a, phase_c, phase_b, real_before, real_after, token):
    non_exempt = [s for s in sites if not s['exempt']]
    exempt = [s for s in sites if s['exempt']]
    key = lambda s: '%s %s' % (s['method'], s['rule'])
    a_int = [key(s) for s in non_exempt if phase_a[key(s)]['intercepted']]
    a_exempt_hit = [key(s) for s in exempt if phase_a[key(s)]['intercepted']]
    a_5xx = [k for k, v in phase_a.items() if isinstance(v['status'], int) and v['status'] >= 500]
    c_reached = [key(s) for s in non_exempt if phase_c[key(s)]['view_invoked']]
    b_reached = [k for k, v in phase_b.items() if v['view_invoked']]
    # C8 是真机检（不是恒真）：判据记录只允许出现白名单字段 + intercepted；
    # 一旦有人往判定里塞 `message`/文案一类字段，本检查立刻转红。
    allowed = set(JUDGED_FIELDS) | {'intercepted'}
    extra = sorted({f for rec in phase_a.values() for f in rec if f not in allowed})
    checks = [
        {'id': 'C1_sites_total_155', 'expect': 155, 'actual': len(sites),
         'ok': len(sites) == 155},
        {'id': 'C2_exempt_22_of_133', 'expect': '22 豁免 / 133 非豁免',
         'actual': '%d / %d' % (len(exempt), len(non_exempt)),
         'ok': len(exempt) == 22 and len(non_exempt) == 133},
        {'id': 'C3_intercept_133_of_133', 'expect': 133, 'actual': len(a_int),
         'ok': len(a_int) == 133},
        {'id': 'C4_exempt_not_intercepted_0', 'expect': 0, 'actual': len(a_exempt_hit),
         'ok': not a_exempt_hit},
        {'id': 'C5_phase_a_5xx_zero', 'expect': 0, 'actual': len(a_5xx), 'ok': not a_5xx},
        {'id': 'C6_csrf_off_control_reaches_133', 'expect': 133, 'actual': len(c_reached),
         'ok': len(c_reached) == 133},
        {'id': 'C7_token_control_reaches_sample', 'expect': len(phase_b),
         'actual': len(b_reached), 'ok': bool(phase_b) and len(b_reached) == len(phase_b)},
        {'id': 'C8_judged_fields_text_free', 'expect': '判定字段 ⊆ %s' % sorted(allowed),
         'actual': '越界字段=%s' % (extra or '无'), 'ok': not extra},
        {'id': 'C9_real_db_unchanged',
         'expect': real_before['sha256'], 'actual': real_after['sha256'],
         'ok': real_before['sha256'] == real_after['sha256']},
        {'id': 'C10_token_channel_available', 'expect': 'meta csrf-token 非空',
         'actual': bool(token), 'ok': bool(token)},
    ]
    return checks, {'intercepted': a_int, 'exempt_intercepted': a_exempt_hit,
                    'phase_a_5xx': a_5xx, 'phase_c_not_reached': [key(s) for s in non_exempt
                                                                  if not phase_c[key(s)]['view_invoked']],
                    'phase_b_not_reached': [k for k, v in phase_b.items() if not v['view_invoked']]}


def run(inject_endpoint=None, sample_step=11):
    before = real_db_status()
    app, copy_path = fixtures.make_isolated_app('c03')
    fixtures.seed_all(app)

    client = app.test_client()
    app.config['WTF_CSRF_ENABLED'] = False          # 先登录（登录本身也受 CSRF 保护）
    client.post('/auth/login', data={'username': '_t_admin', 'password': 'test_pw_123'})
    token = fetch_client_token(client)

    sites = collect_sites(app)
    hits = wrap_views(app)
    non_exempt = [s for s in sites if not s['exempt']]

    # ---- 相位 A（判据）：CSRF 开 + 无 token + 空体 ----
    app.config['WTF_CSRF_ENABLED'] = True
    phase_a = sweep(client, sites, hits)
    # ---- 相位 C（全量控制）：CSRF 关 ⇒ 非豁免面必须走到视图 ----
    app.config['WTF_CSRF_ENABLED'] = False
    phase_c = sweep(client, non_exempt, hits)
    # ---- 相位 B（token 对照，抽样；放最后：会真的执行写端点）----
    app.config['WTF_CSRF_ENABLED'] = True
    sample = non_exempt[::sample_step][:12]
    phase_b = sweep(client, sample, hits, headers={'X-CSRFToken': token} if token else None)

    injection = None
    phase_a2 = None
    if inject_endpoint:
        view = app.view_functions.get(inject_endpoint)
        if view is None:
            print('[csrf] [FAIL] --inject-endpoint 不存在: %s' % inject_endpoint)
            return 2
        dest = '%s.%s' % (view.__module__, view.__name__)
        app.extensions['csrf']._exempt_views.add(dest)     # = 运行期放宽 @csrf.exempt 的同一机制
        injection = {'endpoint': inject_endpoint, 'dest': dest}
        phase_a2 = sweep(client, sites, hits)              # 重跑**全量** A 相位

    after = real_db_status()
    checks, detail = build_checks(sites, phase_a, phase_c, phase_b, before, after, token)

    if phase_a2 is not None:
        key = lambda s: '%s %s' % (s['method'], s['rule'])
        flipped = [key(s) for s in sites
                   if phase_a[key(s)]['intercepted'] and not phase_a2[key(s)]['intercepted']]
        still = [key(s) for s in non_exempt if phase_a2[key(s)]['intercepted']]
        injected_keys = [key(s) for s in sites if s['endpoint'] == inject_endpoint]
        targeted = sorted(flipped) == sorted(injected_keys)
        checks.append({'id': 'C11_injection_targeted_red', 'expect': injected_keys,
                       'actual': {'flipped': flipped, 'still_intercepted': len(still)},
                       'ok': targeted and len(still) == 133 - len(injected_keys)})
        injection.update({'flipped': flipped, 'still_intercepted': len(still),
                          'targeted': targeted})

    payload = {
        'harness': 'r2_csrf_probe.py',
        'run_id': RUN_ID,
        'mode': 'inject' if injection else 'face',
        'interpreter': sys.executable,
        'isolation': {'db_copy': copy_path, 'uri': app.config['SQLALCHEMY_DATABASE_URI']},
        'method': ('口径 = url_map 重算的非 GET 方法级站点 ∩ WTF_CSRF_METHODS；'
                   '豁免取自 flask_wtf 注册表 app.extensions["csrf"]._exempt_views；'
                   'M1 status==400 / M2 view_invoked==False（派发层计数包装）/ '
                   'M3 claims_success==False（结构化字段，不读 message）'),
        'judged_fields': list(JUDGED_FIELDS),
        'forbidden_judged_inputs': ['response text', 'message 字段内容', '自然语言文案'],
        'site_count': {'total': len(sites), 'exempt': len(sites) - len(non_exempt),
                       'non_exempt': len(non_exempt)},
        'checks': checks,
        'detail': detail,
        'injection': injection,
        'phase_b_sample': [('%s %s' % (s['method'], s['rule'])) for s in sample],
        'real_db': {'before': before, 'after': after,
                    'unchanged': before['sha256'] == after['sha256']},
        'sites': sites,
        'phase_a': phase_a,
        'phase_a_after_injection': phase_a2,
        'phase_c': phase_c,
        'phase_b': phase_b,
    }
    ensure_dir(EVIDENCE_DIR)
    print('[csrf] RUN_ID=%s copy=%s' % (RUN_ID, copy_path))
    print('[csrf] 站点 total=%d exempt=%d non_exempt=%d' % (len(sites),
                                                            len(sites) - len(non_exempt),
                                                            len(non_exempt)))
    for c in checks:
        print('  [%-4s] %-34s expect=%s actual=%s'
              % ('OK' if c['ok'] else 'FAIL', c['id'], c['expect'], c['actual']))
    if injection:
        key = lambda s: '%s %s' % (s['method'], s['rule'])
        after_int = [key(s) for s in non_exempt if phase_a2[key(s)]['intercepted']]
        print('[csrf] [INJECT] %s dest=%s ⇒ 翻转=%s 仍拦截=%s 靶向=%s'
              % (injection['endpoint'], injection['dest'], injection['flipped'],
                 injection['still_intercepted'], injection['targeted']))
        print('[csrf] [INJECT-RED] 注入后非豁免面拦截率 = %d/133（注入前 133/133）'
              '⇒ 该条已由「拦截」变为「放行」：C3 若按注入后重算必然失败（非恒真）'
              % len(after_int))
    failed = [c['id'] for c in checks if not c['ok']]
    result = 'OK' if not failed else 'FAILED'
    art = save_evidence('r2_csrf_probe.json' if not injection else
                        'r2_csrf_probe_inject_%s.json' % injection['endpoint'].replace('.', '_'),
                        json.dumps(payload, ensure_ascii=False, indent=1), journal=True)
    print('[csrf] 判据 %d/%d 通过  失败=%s' % (len(checks) - len(failed), len(checks), failed or '无'))
    print('[csrf] artifact -> %s' % art)
    print('[csrf] RESULT: %s' % result)
    return 0 if not failed else 1


def compare_runs(path_a, path_b):
    """C-03 双跑对拍：两份报告的 checks 判定与逐站点 verdict 必须逐条相同。"""
    with open(path_a, encoding='utf-8') as fh:
        a = json.load(fh)
    with open(path_b, encoding='utf-8') as fh:
        b = json.load(fh)
    ca = {c['id']: c['ok'] for c in a.get('checks') or []}
    cb = {c['id']: c['ok'] for c in b.get('checks') or []}
    site_a = {k: (v['status'], v['view_invoked'], v['intercepted'])
              for k, v in (a.get('phase_a') or {}).items()}
    site_b = {k: (v['status'], v['view_invoked'], v['intercepted'])
              for k, v in (b.get('phase_a') or {}).items()}
    only_a, only_b = sorted(set(ca) - set(cb)), sorted(set(cb) - set(ca))
    diff = sorted(k for k in set(ca) & set(cb) if ca[k] != cb[k])
    site_only_a = sorted(set(site_a) - set(site_b))
    site_only_b = sorted(set(site_b) - set(site_a))
    site_diff = sorted(k for k in set(site_a) & set(site_b) if site_a[k] != site_b[k])
    ok = (a.get('run_id') != b.get('run_id') and not only_a and not only_b and not diff
          and not site_only_a and not site_only_b and not site_diff)
    payload = {'schema': 'r2-csrf-crossrun/1', 'harness': 'r2_csrf_probe.py --compare',
               'run_id': RUN_ID,
               'run_a': {'run_id': a.get('run_id'), 'checks': len(ca), 'sites': len(site_a),
                         'result': 'OK' if all(ca.values()) else 'FAILED'},
               'run_b': {'run_id': b.get('run_id'), 'checks': len(cb), 'sites': len(site_b),
                         'result': 'OK' if all(cb.values()) else 'FAILED'},
               'checks_only_in_a': only_a, 'checks_only_in_b': only_b, 'checks_verdict_diff': diff,
               'sites_only_in_a': site_only_a, 'sites_only_in_b': site_only_b,
               'site_verdict_diff': site_diff, 'identical': ok,
               'note': '对拍只比判定（checks.ok 与逐站点 status/view_invoked/intercepted），'
                       '不比时间戳/路径一类运行期字段'}
    text = json.dumps(payload, ensure_ascii=False, indent=1)
    try:
        payload['artifact'] = save_evidence('r2_csrf_crossrun_compare.json', text, journal=True)
    except Exception as exc:
        payload['artifact_error'] = '%s: %s' % (exc.__class__.__name__, exc)
    print('[csrf] run_a=%s run_b=%s' % (payload['run_a'], payload['run_b']))
    print('[csrf] checks_only_in_a=%s checks_only_in_b=%s checks_diff=%s'
          % (only_a, only_b, diff))
    print('[csrf] sites_only_in_a=%s sites_only_in_b=%s site_diff=%s'
          % (site_only_a, site_only_b, site_diff))
    print('[csrf] identical=%s artifact=%s' % (ok, payload.get('artifact')))
    print('[csrf] RESULT: %s' % ('OK' if ok else 'FAILED'))
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description='C-03 CSRF 拦截面判据（V-09；断状态码 + 机读标记，不断文案）')
    ap.add_argument('--inject-endpoint', default=None,
                    help='注入回放：把该端点的 dest 加入 csrf._exempt_views（= 运行期放宽 '
                         '@csrf.exempt）⇒ 该条必须转红且仅该条翻转')
    ap.add_argument('--sample-step', type=int, default=11, help='相位 B token 对照的抽样步长')
    ap.add_argument('--compare', nargs=2, metavar=('A', 'B'), default=None,
                    help='双跑对拍：两份 r2_csrf_probe.json')
    args = ap.parse_args(argv)
    if args.compare:
        return compare_runs(args.compare[0], args.compare[1])
    return run(inject_endpoint=args.inject_endpoint, sample_step=args.sample_step)


if __name__ == '__main__':
    sys.exit(main())
