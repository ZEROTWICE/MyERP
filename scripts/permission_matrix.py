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


def run_id():
    """落盘标识：优先 HARNESS_RUN_ID，否则时间戳。"""
    return os.environ.get('HARNESS_RUN_ID') or time.strftime('run-%Y%m%d-%H%M%S')


def default_out():
    """.tmp/<RUN_ID>/ 下的落点（绝对路径，与 cwd 无关 —— 不再是 cwd 相对的 `../`）。"""
    return str(REPORTS / '.tmp' / run_id() / DUMP_NAME)


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


def run(out_path=None, dump=True):
    a14_reconfigure()
    app, _ = make_app()
    users, password = ensure_role_users(app)
    seed_fixtures(app)
    guards = guard_of_view()

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
            try:
                r = c.get(url, follow_redirects=True)
            except Exception as e:
                row[actor] = f'EXC:{e.__class__.__name__}'
                continue
            try:
                body = r.get_data(as_text=True)
            except UnicodeDecodeError:
                body = ''  # 二进制下载（导出文件）
            denied = ('权限不足' in body) or r.status_code in (401, 403)
            login_page = 'name="username"' in body and '登录' in body
            row[actor] = 'OK' if (r.status_code == 200 and not denied and not login_page) \
                else ('DENY' if denied else ('LOGIN' if login_page else f'HTTP{r.status_code}'))
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

    # ---- E-03：落盘与退出码解耦（写盘失败绝不改变判据）----
    if dump:
        _ok, note = dump_matrix(matrix, out_path or default_out())
        print('\n' + note)
    else:
        print('\n[--no-dump] 已跳过落盘（退出码只反映判据）')

    # ---- E-03：失败出口（原为无条件 return 0 的伪门禁；判据语义与退出码同源）----
    code = 1 if anon_open else 0
    if anon_open:
        print(f'[FAIL] 匿名可访问视图 {len(anon_open)} 个（应为 0）')
    else:
        print('[OK] 匿名可访问 = 0')
    print('[e03] exit_code_semantics=' + json.dumps({
        'script': 'scripts/permission_matrix.py',
        'class': '有判据语义（原伪门禁，E-03 已补失败出口）',
        'rule': 'anon_open == 0 -> exit 0; anon_open != 0 -> exit 1',
        'inputs': {'anon_open': len(anon_open), 'routes_tested': len(matrix)},
        'dump': ('skipped' if not dump else (out_path or default_out())),
        'code': code,
    }, ensure_ascii=False))
    return code


def main(argv=None):
    ap = argparse.ArgumentParser(
        description='权限矩阵检查（E-03：判据驱动退出码；落盘与退出码解耦）')
    ap.add_argument('--out', default=None,
                    help=f'矩阵 JSON 落点（默认 {REPORTS}/.tmp/<RUN_ID>/{DUMP_NAME}）')
    ap.add_argument('--no-dump', action='store_true', help='完全不落盘（退出码只反映判据）')
    args = ap.parse_args(argv)
    return run(out_path=args.out, dump=not args.no_dump)


if __name__ == '__main__':
    sys.exit(main())
