"""权限矩阵检查。

对每个 GET 路由，比较各角色的实际可访问性与 permissions.py 的登记：
- ALL_ROLES_PASS：所有登录角色都能访问（含 user），提示可能缺校验
- ANON_PASS：未登录也能拿到内容，属于严重问题
并列出路由源码上实际挂的校验方式（require_capability / 手写 role 判断 / 无）。

**退出码语义（E-03 分类：原「伪门禁型」→ 已补失败出口）**

本脚本 stdout **携带判据语义**（`匿名可访问（应为 0）`），因此退出码必须与之同源（A-30）：
`anon_open == 0` ⇒ **exit 0**；`anon_open` 非空 ⇒ **exit 1**（并打印 `[FAIL] 匿名可访问视图 N 个（应为 0）`）。

**落盘与退出码解耦（E-03：原「写盘污染型」）**：矩阵 JSON 默认写
`test-reports-2026-10/.tmp/<RUN_ID>/_permission_matrix.json`（**不再写仓库根**，历史缺陷 T-07/A-11：
写仓库根 JSON 被拒时「断言全绿也 exit 1」= 狼来了）。`--out PATH` 可指定落点，`--no-dump` 完全跳过；
**写盘失败只打印 `[WARN]`，绝不改变退出码**。退出码纯由判据决定。

用法（仓库根目录）：

    python -B scripts/permission_matrix.py                # 默认落 .tmp/<RUN_ID>/
    python -B scripts/permission_matrix.py --no-dump      # 不落盘（CI 推荐）
    python -B scripts/permission_matrix.py --out /tmp/x.json

**C-06 四模块权限断言面（V-07 新增，复用本脚本口径、不新起并行工具）**

`35` §4 的 `C-06` 行把靶心收窄为「**权限断言面**」（可达性命中面已在库）：`equipment` /
`purchase_orders` / `shipments` / `stock` 四个模块**各 ≥1 allow + ≥1 deny**；注入「移除
`@require_capability`」⇒ 对应 deny 断言**必须转红**；这四个模块的 **5xx = 0**。
本脚本用**同一个 `classify()` 口径**（'权限不足' 文案 / 401 / 403 ⇒ DENY）与**同一批 actor client**
跑 `MODULE_FACE`，因此不存在「同端点两个分母」。能力→允许角色取自 `app.permissions.roles_for`
（与产品同一事实来源）。

* `--out-modules PATH`：额外落盘四模块面矩阵（默认不写；`--no-dump` 不影响它）。
* `--inject-module NAME`：**副本进程内**把该模块面端点的 `@require_capability` 剥掉
  （保留 `@login_required`）⇒ 对应 deny 断言必须转红（`strip_capability()`；**不改生产代码**）。
* 退出码：`anon_open == 0` **且** 四模块面全绿 ⇒ `exit 0`；任一不满足 ⇒ `exit 1`。
"""
import argparse
import json
import os
import re
import sys
import time
import pathlib

from _test_bootstrap import make_app, ensure_role_users, login_as, seed_fixtures, ROLES

ROOT = pathlib.Path(__file__).resolve().parent.parent
REPORTS = ROOT / 'test-reports-2026-10'
DUMP_NAME = '_permission_matrix.json'
ROUTE_FILES = ('app/main/routes.py', 'app/main/quality.py', 'app/main/production_center.py')

#: ---- C-06（V-07）：四模块权限断言面（口径 = 本脚本 classify，不新起工具）----
#: `urls` 是该模块**页面面**的具名入口（含被通用 GET 扫因为带参而跳过的 `/stock/<kind>`）；
#: `capability` 取自路由源码上的 `@require_capability`；允许角色由 `app.permissions.roles_for` 派生。
MODULE_FACE = (
    {'module': 'equipment', 'capability': 'equipment.manage',
     'urls': ('/equipment', '/work_centers', '/heat_lots', '/workpieces'),
     'inject_endpoint': 'main.manage_equipment',
     'deny_sample': ('hr', 'accountant', 'inspector', 'sales', 'user')},
    {'module': 'purchase_orders', 'capability': 'purchase.manage',
     'urls': ('/purchase_orders', '/suppliers', '/purchase_requisitions'),
     'inject_endpoint': 'main.manage_purchase_orders',
     'deny_sample': ('hr', 'accountant', 'inspector', 'sales', 'user')},
    {'module': 'shipments', 'capability': 'shipment.manage',
     'urls': ('/shipments',),
     'inject_endpoint': 'main.manage_shipments',
     'deny_sample': ('hr', 'accountant', 'inspector', 'user')},
    {'module': 'stock', 'capability': 'inventory.view',
     'urls': ('/stock/fg', '/stock/raw'),
     'inject_endpoint': 'main.stock_by_kind',
     'deny_sample': ('hr', 'accountant', 'inspector', 'sales', 'user')},
)
MODULES_DUMP_NAME = '_permission_matrix_modules.json'


def run_id():
    """落盘标识：优先 HARNESS_RUN_ID，否则时间戳。"""
    return os.environ.get('HARNESS_RUN_ID') or time.strftime('run-%Y%m%d-%H%M%S')


def default_out():
    """.tmp/<RUN_ID>/ 下的落点（绝对路径，与 cwd 无关 —— 不再是 cwd 相对的 `../`）。"""
    return str(REPORTS / '.tmp' / run_id() / DUMP_NAME)


def modules_out(path):
    """`--out-modules` 的落点解析（**绝对路径、cwd 无关**，且绝不落到任何根目录）。

    * 绝对路径 ⇒ 原样；
    * 带目录的相对路径 ⇒ 相对 `REPORTS`（`test-reports-2026-10/`）解析；
    * **裸文件名** ⇒ 落到 `REPORTS/.tmp/<RUN_ID>/`（与 `default_out()` 同目录）。

    ⚠ 两个踩过的坑（t8 实测）：① 经 `scripts/_sandbox_compat.py` 运行时 cwd 是 `scripts/`，
    直接把相对路径交给 `open()` 会落到 `scripts/test-reports-2026-10/.tmp/...`；
    ② 裸文件名若按 `REPORTS` 直接解析会落到报告根目录。⇒ 统一解析成绝对路径。
    """
    if not path:
        return None
    p = pathlib.Path(path)
    if p.is_absolute():
        return str(p)
    if p.parent == pathlib.Path('.'):
        return str(REPORTS / '.tmp' / run_id() / p.name)
    return str(REPORTS / p)


def a14_reconfigure():
    """A-14：本机控制台是 GBK；只放宽 errors，避免编码问题被误读成「崩溃 exit 1」。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors='replace')
        except Exception:
            pass


def dump_matrix(matrix, out_path):
    """落盘（**与退出码解耦**）：失败返回 (False, 警告串)，调用方不得据此改退出码。"""
    try:
        directory = os.path.dirname(os.path.abspath(out_path))
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(out_path, 'w', encoding='utf-8', newline='\n') as f:
            json.dump(matrix, f, ensure_ascii=False, indent=1)
        return True, f'完整矩阵已写入 {out_path}'
    except OSError as e:
        return False, (f'[WARN] 落盘失败（不影响退出码）: {e.__class__.__name__}: {e}')


def guard_of_view():
    """扫源码，得出每个视图函数用了哪种权限校验。"""
    guards = {}
    for rel in ROUTE_FILES:
        text = (ROOT / rel).read_text(encoding='utf-8')
        lines = text.splitlines()
        for i, line in enumerate(lines):
            m = re.match(r'^def (\w+)\(', line)
            if not m:
                continue
            func = m.group(1)
            # 往上收集装饰器
            decos = []
            j = i - 1
            while j >= 0 and (lines[j].startswith('@') or lines[j].strip() == ''):
                if lines[j].startswith('@'):
                    decos.append(lines[j].strip())
                j -= 1
            # 往下看函数体前 25 行有没有手写 role 判断
            body = '\n'.join(lines[i:i + 25])
            kinds = []
            for d in decos:
                if 'require_capability' in d:
                    kinds.append('capability' + d[d.index('('):] if '(' in d else 'capability')
                elif 'require_roles' in d or 'admin_required' in d:
                    kinds.append(d)
            if re.search(r'current_user\.role\s+(not\s+)?in|_require_roles\(|current_user\.role\s*[!=]=', body):
                kinds.append('inline_role_check')
            if not any('login_required' in d for d in decos):
                kinds.append('NO_LOGIN_REQUIRED')
            guards[func] = kinds or ['NONE']
    return guards


def content_ok(resp_code, final_code):
    return final_code == 200 and resp_code == 200


def classify(client, url):
    """**单一判定口径**（C-06 复用，不另起第二套）：`'权限不足'` 文案 / 401 / 403 ⇒ `DENY`；
    登录页特征 ⇒ `LOGIN`；200 且非以上 ⇒ `OK`；其余 ⇒ `HTTP<code>`；抛异常 ⇒ `EXC:<类型>`。"""
    try:
        r = client.get(url, follow_redirects=True)
    except Exception as e:
        return f'EXC:{e.__class__.__name__}'
    try:
        body = r.get_data(as_text=True)
    except UnicodeDecodeError:
        body = ''  # 二进制下载（导出文件）
    denied = ('权限不足' in body) or r.status_code in (401, 403)
    login_page = 'name="username"' in body and '登录' in body
    if r.status_code == 200 and not denied and not login_page:
        return 'OK'
    if denied:
        return 'DENY'
    if login_page:
        return 'LOGIN'
    return f'HTTP{r.status_code}'


def strip_capability(app, endpoint):
    """**副本进程内**移除某端点的 `@require_capability`（C-06 注入回放；不改生产代码）。

    装饰器链：`@login_required`（最外）→ `@require_capability` → 视图函数 ⇒ 取最内层视图函数后
    用 `login_required` 重包：**能力面被移除、登录面保留**（匿名判定因此不受污染，注入是靶向的）。
    返回注入记录（`None` = 端点不存在）。"""
    from flask_login import login_required
    view = app.view_functions.get(endpoint)
    if view is None:
        return None
    inner, layers = view, 0
    while hasattr(inner, '__wrapped__') and layers < 8:
        inner = inner.__wrapped__
        layers += 1
    app.view_functions[endpoint] = login_required(inner)
    return {'endpoint': endpoint, 'stripped_layers': layers,
            'inner': getattr(inner, '__name__', '?')}


def run_module_face(clients, roles_for):
    """四模块 allow + deny 断言（**复用 `classify()` 的同一口径与同一批 client**）。

    判据分两层（缺一不可）：
    * **逐入口（可被注入证伪的那一层）**：每个 face URL 上 ① `capability` 允许的角色**至少一个**
      `OK`（allow 面）② `deny_sample` 中**至少一个**未授权角色 `DENY`（deny 面）③ 无 5xx。
      ⇒ 「移除某端点的 `@require_capability`」必然让**该入口**的 deny 面塌掉 ⇒ 对应断言转红。
      （模块级只看「≥1」会**掩盖**同模块其它入口仍在拒绝，注入因此不红 —— 实测踩过，见 t8 证据。）
    * **模块级**：`35` §4 C-06 的口径 = 该模块 ≥1 allow + ≥1 deny + 5xx=0。
    返回 `(逐 URL 矩阵, 逐模块结论)`。"""
    rows, summary = {}, []
    for spec in MODULE_FACE:
        cap_roles = tuple(roles_for(spec['capability']))
        table = {url: {actor: classify(c, url) for actor, c in clients.items()}
                 for url in spec['urls']}
        rows[spec['module']] = table
        per_url = []
        for url in spec['urls']:
            row = table[url]
            allow = [r for r in cap_roles if row[r] == 'OK']
            deny = [r for r in spec['deny_sample'] if row[r] == 'DENY']
            five = sorted({v for v in row.values() if v.startswith('HTTP5')})
            problems = []
            if not allow:
                problems.append('allow 面为 0（%s 无任何允许角色可访问）' % url)
            if not deny:
                problems.append('deny 面为 0（%s 未拒绝任何样本角色）' % url)
            if five:
                problems.append('%s 出现 5xx: %s' % (url, ','.join(five)))
            per_url.append({'url': url, 'allow': allow, 'deny': deny, 'fivexx': five,
                            'problems': problems, 'ok': not problems})
        allow_any = [r for r in cap_roles if any(table[u][r] == 'OK' for u in spec['urls'])]
        deny_any = [r for r in spec['deny_sample']
                    if any(table[u][r] == 'DENY' for u in spec['urls'])]
        five_all = sorted({v for u in spec['urls'] for v in table[u].values()
                           if v.startswith('HTTP5')})
        problems = ['%s: %s' % (e['url'], '; '.join(e['problems']))
                    for e in per_url if not e['ok']]
        if len(allow_any) != len(cap_roles):
            problems.append('模块级 allow 角色缺失: %s'
                            % ','.join(r for r in cap_roles if r not in allow_any))
        if not deny_any:
            problems.append('模块级 deny ≥1 不成立（样本角色全未命中）')
        if five_all:
            problems.append('模块级 5xx 非空: %s' % ','.join(five_all))
        summary.append({'module': spec['module'], 'capability': spec['capability'],
                        'cap_roles': list(cap_roles), 'allow_ok': allow_any,
                        'deny_sample': list(spec['deny_sample']), 'deny_ok': deny_any,
                        'fivexx': five_all, 'urls': list(spec['urls']), 'per_url': per_url,
                        'inject_endpoint': spec['inject_endpoint'],
                        'problems': problems, 'ok': not problems})
    return rows, summary


def run(out_path=None, dump=True, out_modules=None, inject_module=None):
    a14_reconfigure()
    app, _ = make_app()
    users, password = ensure_role_users(app)
    seed_fixtures(app)
    guards = guard_of_view()
    from app.permissions import roles_for   # C-06：能力→角色取**产品同一事实来源**

    from smoke_test import first_ids, resolve_url, SKIP
    ids = first_ids(app)

    targets = []
    for rule in app.url_map.iter_rules():
        if rule.endpoint == 'static' or 'GET' not in rule.methods or str(rule) in SKIP:
            continue
        if rule.endpoint.startswith('auth.') or rule.endpoint == 'bootstrap.static':
            continue
        if rule.arguments:
            url, _why = resolve_url(rule, ids)
            if url is None:
                continue
        else:
            url = str(rule)
        targets.append((str(rule), url, rule.endpoint))

    matrix = {}
    clients = {}
    for role in ROLES:
        c = app.test_client()
        login_as(c, users[role], password)
        clients[role] = c
    clients['anonymous'] = app.test_client()

    for rule_str, url, endpoint in sorted(targets):
        row = {}
        for actor, c in clients.items():
            row[actor] = classify(c, url)
        matrix[f'{rule_str} [{endpoint}]'] = row

    print('=== 匿名可访问（应为 0，登录页/静态资源除外）===')
    anon_open = [k for k, v in matrix.items() if v['anonymous'] == 'OK']
    for k in anon_open:
        func = k.split('[')[-1].rstrip(']').split('.')[-1]
        print(f'  {k}  guards={guards.get(func)}')
    if not anon_open:
        print('  无')

    print('\n=== 所有登录角色（含 user/accountant/sales）均可访问 ===')
    for k, v in matrix.items():
        if v['anonymous'] == 'OK':
            continue
        if all(v[r] == 'OK' for r in ROLES):
            func = k.split('[')[-1].rstrip(']').split('.')[-1]
            print(f'  {k}  guards={guards.get(func)}')

    print('\n=== 源码上完全没有权限校验的视图（仅 login_required 或更少）===')
    endpoints_tested = {k.split('[')[-1].rstrip(']').split('.')[-1] for k in matrix}
    for func in sorted(endpoints_tested):
        g = guards.get(func, ['UNKNOWN'])
        if g == ['NONE'] or 'NO_LOGIN_REQUIRED' in g:
            print(f'  {func}: {g}')

    # ---- C-06（V-07）：四模块权限断言面（allow + deny + 5xx=0）----
    injection = None
    if inject_module:
        spec = next((s for s in MODULE_FACE if s['module'] == inject_module), None)
        if spec is None:
            print(f'\n[FAIL] --inject-module 未知模块: {inject_module}'
                  f'（可选 {[s["module"] for s in MODULE_FACE]}）')
            return 2
        injection = strip_capability(app, spec['inject_endpoint'])
        print(f'\n[INJECT] 副本进程内移除 @require_capability：module={inject_module} '
              f'endpoint={spec["inject_endpoint"]} stripped_layers='
              f'{None if injection is None else injection["stripped_layers"]} '
              f'inner={None if injection is None else injection["inner"]}'
              f'（login_required 保留 ⇒ 匿名判定不受污染）')
    face_rows, face = run_module_face(clients, roles_for)
    face_failures = [m['module'] for m in face if not m['ok']]
    print('\n=== C-06 四模块权限断言面（复用本脚本口径：逐入口 allow+deny，模块级 ≥1≥1，5xx=0）===')
    for m in face:
        print(f"  [{'OK  ' if m['ok'] else 'FAIL'}] {m['module']:<16}"
              f"cap={m['capability']:<20} allow≥1={','.join(m['allow_ok']) or '-'}"
              f"  deny≥1={','.join(m['deny_ok']) or '-'}  入口={len(m['urls'])}"
              f"  5xx={m['fivexx'] or '无'}")
        for e in m['per_url']:
            print(f"        [{'OK  ' if e['ok'] else 'FAIL'}] {e['url']:<32}"
                  f"allow={','.join(e['allow']) or '-'}  deny={','.join(e['deny']) or '-'}"
                  f"  5xx={e['fivexx'] or '无'}")
        for p in m['problems']:
            print(f'        - {p}')
    if injection is not None:
        target = next((m for m in face if m['module'] == inject_module), {})
        print(f'[INJECT] 期望 = 该模块 deny 断言转红 ⇒ 实际 deny_ok='
              f'{target.get("deny_ok")}  module_ok={target.get("ok")}')
        print(f'[INJECT] 靶向性 = 其它三模块仍全绿: '
              f'{[m["module"] for m in face if m["module"] != inject_module and m["ok"]]}')

    # ---- E-03：落盘与退出码解耦（写盘失败绝不改变判据）----
    if dump:
        _ok, note = dump_matrix(matrix, out_path or default_out())
        print('\n' + note)
    else:
        print('\n[--no-dump] 已跳过落盘（退出码只反映判据）')
    if out_modules:
        face_doc = {'run_id': run_id(), 'capability_source': 'app.permissions.roles_for',
                    'criterion': 'C-06：各模块 ≥1 allow + ≥1 deny + 5xx=0（复用本脚本 classify 口径）',
                    'injected': injection, 'summary': face, 'rows': face_rows}
        m_ok, m_note = dump_matrix(face_doc, out_modules)
        print(m_note if m_ok else m_note)      # 与主落盘同口径：失败只 [WARN]，不改退出码

    # ---- E-03：失败出口（原为无条件 return 0 的伪门禁；判据语义与退出码同源）----
    # C-06（V-07）：四模块权限面失败同样计入退出码 ⇒ ci_gates 的 permission_matrix 步骤
    # **永久**执法 C-06（allow + deny + 5xx=0），而不只是在实测里跑一次。
    code = 1 if (anon_open or face_failures) else 0
    if anon_open:
        print(f'[FAIL] 匿名可访问视图 {len(anon_open)} 个（应为 0）')
    else:
        print('[OK] 匿名可访问 = 0')
    if face_failures:
        print(f'[FAIL] C-06 四模块权限面失败：{",".join(face_failures)}')
    else:
        print('[OK] C-06 四模块权限面 = 全绿（4 模块 allow + deny + 5xx=0）')
    print('[e03] exit_code_semantics=' + json.dumps({
        'script': 'scripts/permission_matrix.py',
        'class': '有判据语义（原伪门禁，E-03 已补失败出口；V-07 增补 C-06 四模块面）',
        'rule': 'anon_open == 0 且 C-06 四模块面全绿 -> exit 0; 任一不满足 -> exit 1',
        'inputs': {'anon_open': len(anon_open), 'routes_tested': len(matrix),
                   'c06_modules_failed': face_failures, 'c06_injected': inject_module},
        'dump': ('skipped' if not dump else str(out_path or default_out())),
        'modules_dump': str(out_modules) if out_modules else 'skipped',
        'code': code,
    }, ensure_ascii=False))
    return code


def main(argv=None):
    ap = argparse.ArgumentParser(
        description='权限矩阵检查（E-03：判据驱动退出码；落盘与退出码解耦；'
                    'V-07：C-06 四模块 allow/deny 断言面）')
    ap.add_argument('--out', default=None,
                    help=f'矩阵 JSON 落点（默认 {REPORTS}/.tmp/<RUN_ID>/{DUMP_NAME}）')
    ap.add_argument('--no-dump', action='store_true', help='完全不落盘（退出码只反映判据）')
    ap.add_argument('--out-modules', default=None,
                    help='额外落盘 C-06 四模块面矩阵（默认不写；裸文件名 ⇒ '
                         f'test-reports-2026-10/.tmp/<RUN_ID>/{MODULES_DUMP_NAME}，'
                         '带目录的相对路径 ⇒ 相对 test-reports-2026-10/ 解析）')
    ap.add_argument('--inject-module', default=None,
                    help='注入回放：副本进程内移除该模块面端点的 @require_capability '
                         '⇒ 对应 deny 断言必须转红（不改生产代码）')
    args = ap.parse_args(argv)
    return run(out_path=args.out, dump=not args.no_dump,
               out_modules=modules_out(args.out_modules), inject_module=args.inject_module)


if __name__ == '__main__':
    sys.exit(main())
