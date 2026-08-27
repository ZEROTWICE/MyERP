"""权限矩阵检查。

对每个 GET 路由，比较各角色的实际可访问性与 permissions.py 的登记：
- ALL_ROLES_PASS：所有登录角色都能访问（含 user），提示可能缺校验
- ANON_PASS：未登录也能拿到内容，属于严重问题
并列出路由源码上实际挂的校验方式（require_capability / 手写 role 判断 / 无）。
"""
import json
import re
import sys
import pathlib

from _test_bootstrap import make_app, ensure_role_users, login_as, seed_fixtures, ROLES

ROOT = pathlib.Path(__file__).resolve().parent.parent
ROUTE_FILES = ('app/main/routes.py', 'app/main/quality.py', 'app/main/production_center.py')


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


def run():
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

    with open('../_permission_matrix.json', 'w', encoding='utf-8') as f:
        json.dump(matrix, f, ensure_ascii=False, indent=1)
    print('\n完整矩阵已写入 _permission_matrix.json')
    return 0


if __name__ == '__main__':
    sys.exit(run())
