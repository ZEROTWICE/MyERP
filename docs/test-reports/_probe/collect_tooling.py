"""只读探针：量化 5 个静态门禁 + 3 个请求型脚本的覆盖范围与盲区（t6 证据）。

只读、不改生产代码、不写仓库根产物、不连真实库写操作（数据库仅经 make_app()
的临时副本，且本脚本不修改任何数据）。用法：

    # 只做静态统计（不需要数据库，任何环境都能跑）
    F:\\Miniconda\\envs\\wage\\python.exe -B docs/test-reports/_probe/collect_tooling.py

    # 追加动态统计（需要 sandbox 垫片，见 scripts/_sandbox_compat.py）
    F:\\Miniconda\\envs\\wage\\python.exe -B scripts/_sandbox_compat.py docs/test-reports/_probe/collect_tooling.py --dynamic

输出 5 组事实：
  A 路由模块 / 装饰器：每个模块的 view 数与 @require_capability/@login_required 数
  B 门禁盲区：check_templates.ROUTE_FILES、permission_matrix.ROUTE_FILES 漏掉哪些模块
  C smoke_test 的参数化覆盖：哪些路由参数没有 ID 来源映射（必被跳过）
  D 请求型脚本是否被 CI 覆盖（Jenkinsfile / .github / deploy.bat / tests/）
  E 动态（--dynamic）：test_client 下的状态码分布，验证「静态门禁 vs 请求脚本」的互补性
"""
import ast
import collections
import json
import os
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))

ROUTE_MODULES = sorted((ROOT / 'app' / 'main').glob('*.py'))

# check_templates.py / permission_matrix.py 里硬编码的清单（读源码，避免抄错）
def _listed_files(script, varname='ROUTE_FILES'):
    src = (ROOT / 'scripts' / script).read_text(encoding='utf-8')
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == varname:
                    return tuple(e.value for e in node.value.elts)
    return ()


def _view_decorators():
    """{模块: {'views': n, 'capability': n, 'login_required': n, 'inline_role': n}}"""
    out = {}
    for path in ROUTE_MODULES:
        text = path.read_text(encoding='utf-8')
        lines = text.splitlines()
        stat = collections.Counter()
        for i, line in enumerate(lines):
            if not re.match(r'^def \w+\(', line):
                continue
            stat['views'] += 1
            decos = []
            j = i - 1
            while j >= 0 and (lines[j].lstrip().startswith('@') or not lines[j].strip()):
                if lines[j].lstrip().startswith('@'):
                    decos.append(lines[j])
                j -= 1
            blob = '\n'.join(decos)
            if 'require_capability' in blob:
                stat['capability'] += 1
            if 'login_required' in blob:
                stat['login_required'] += 1
            body = '\n'.join(lines[i:i + 25])
            if re.search(r'current_user\.role\s+(not\s+)?in|current_user\.role\s*[!=]=', body):
                stat['inline_role'] += 1
        out[path.name] = dict(stat)
    return out


def static_report():
    print('== A. 路由模块 / 装饰器统计（正则收集装饰器） ==')
    decos = _view_decorators()
    for name in sorted(decos):
        d = decos[name]
        print('  %-22s views=%-4d capability=%-4d login_required=%-4d inline_role=%d'
              % (name, d.get('views', 0), d.get('capability', 0),
                 d.get('login_required', 0), d.get('inline_role', 0)))

    print('\n== B. 门禁扫描清单的盲区 ==')
    all_modules = {p.name for p in ROUTE_MODULES}
    for script in ('check_templates.py', 'permission_matrix.py'):
        listed = _listed_files(script)
        base = {os.path.basename(x) for x in listed}
        missing = sorted(m for m in all_modules - base if decos.get(m, {}).get('views'))
        print('  %s 声明扫描 %d 个模块；有视图但未扫描：%s' % (script, len(listed), missing or '无'))
        for m in missing:
            d = decos.get(m, {})
            print('      -> %s views=%d capability=%d' % (m, d.get('views', 0), d.get('capability', 0)))
        if missing:
            tot = sum(decos[m]['views'] for m in missing)
            print('      -> 合计 %d 个视图 的「守卫类型」无法被 permission_matrix.guard_of_view() 识别' % tot)

    print('\n== C. smoke_test / permission_matrix 的参数化覆盖 ==')
    sys.path.insert(0, str(ROOT / 'scripts'))
    src = (ROOT / 'scripts' / 'smoke_test.py').read_text(encoding='utf-8')
    tree = ast.parse(src)
    known = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in ('ID_SOURCES',):
                    for k in node.value.keys:
                        known.add(k.value)
    # 路由参数集合（静态：从 @bp.route 字符串里解析）
    params = collections.Counter()
    for path in ROUTE_MODULES:
        for m in re.finditer(r"@(?:bp|\w+)\.route\(\s*'([^']+)'", path.read_text(encoding='utf-8')):
            for a in re.findall(r'<(?:\w+:)?(\w+)>', m.group(1)):
                params[a] += 1
    unmapped = sorted(p for p in params if p not in known and p != 'filename')
    print('  路由参数名共 %d 种，ID_SOURCES 覆盖 %d 种；无映射（必然被跳过）：%s'
          % (len(params), len(known), unmapped or '无'))
    print('  smoke_test SKIP 常量：%s'
          % (re.search(r"SKIP = \{([^}]*)\}", src).group(1).strip(),))

    print('\n== D. 请求型脚本的 CI 覆盖 ==')
    jenkins = (ROOT / 'Jenkinsfile').read_text(encoding='utf-8')
    for needle in ('check_templates', 'check_properties', 'check_migration_heads',
                   'route_inventory', 'check_db_bootstrap', 'smoke_test',
                   'permission_matrix', 'functional_test', 'pytest', 'py_compile'):
        print('  Jenkinsfile 含 %-22s : %s' % (needle, needle in jenkins))
    yml = (ROOT / '.github' / 'workflows' / 'docker-deploy.yml').read_text(encoding='utf-8')
    print('  docker-deploy.yml 有测试步骤 : %s' % any(
        n in yml for n in ('check_templates', 'smoke_test', 'pytest', 'functional_test', 'route_inventory')))
    tests_dir = ROOT / 'tests'
    n_tests = len(list(tests_dir.rglob('*.py'))) if tests_dir.exists() else 0
    print('  tests/ 下的 .py 文件数 : %d%s' % (n_tests, '' if tests_dir.exists() else '（tests/ 不存在）'))
    print('  pytest.ini/pyproject/tox.ini/setup.cfg/conftest.py 存在 : %s'
          % [p for p in ('pytest.ini', 'pyproject.toml', 'tox.ini', 'setup.cfg', 'conftest.py')
             if (ROOT / p).exists()])


def dynamic_report():
    print('\n== E. 动态：GATES 语义分档（GET 请求状态码） ==')
    import _test_bootstrap as tb
    from app.permissions import CAPABILITIES, ROLES
    app, db_path = tb.make_app(fresh=True)
    users, pw = tb.ensure_role_users(app)
    tb.seed_fixtures(app)
    print('  临时库副本 = %s' % db_path)
    print('  capability=%d role=%d' % (len(CAPABILITIES), len(ROLES)))

    # E0 url_map 的真实分布（门禁 route_inventory 的口径）
    rules = list(app.url_map.iter_rules())
    per_endpoint = collections.Counter(r.endpoint for r in rules)
    print('  url_map 规则数 = %d（含 static），endpoint 数 = %d' % (len(rules), len(per_endpoint)))

    # E1 「语义混淆」：把 POST 用 GET 打，看是否 405（405 说明方法隔离有效）
    probe = ['/tasks/add', '/system_configs', '/tasks/import', '/export_tasks']
    c = app.test_client()
    tb.login_as(c, users['admin'], pw)
    for url in probe:
        r = c.get(url, follow_redirects=False)
        print('  GET(应为 POST/表单) %-22s -> %s' % (url, r.status_code))

    # E2 导出类端点返回的 Content-Type，验证「是不是 xlsx」这类契约是否被测
    for url in ['/employees/template', '/tasks/template']:
        r = c.get(url, follow_redirects=False)
        print('  %-22s -> %s %s %dB' % (url, r.status_code,
                                        r.headers.get('Content-Type', '')[:48], len(r.get_data())))

    # E3 静态闭包：路由里 url_for 的目标是否可解析（模板渲染时才炸的类错误）
    import jinja2
    tpl_dir = ROOT / 'app' / 'templates'
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(tpl_dir)))
    bad = []
    for p in sorted(tpl_dir.rglob('*.html')):
        try:
            env.parse(p.read_text(encoding='utf-8'), filename=p.name)
        except jinja2.TemplateSyntaxError as e:
            bad.append('%s:%s %s' % (p.name, e.lineno, e.message))
    print('  Jinja2 语法检查：%d 个模板，%d 个失败' % (len(list(tpl_dir.rglob('*.html'))), len(bad)))
    for b in bad:
        print('     %s' % b)

    # E4 smoke_test 实际能打到的 GET 带参路由（复用被测脚本自己的判定逻辑）
    import smoke_test
    ids = smoke_test.first_ids(app)
    resolvable, skipped = [], []
    for rule in rules:
        if rule.endpoint == 'static' or 'GET' not in rule.methods or str(rule) in smoke_test.SKIP:
            continue
        if not rule.arguments:
            continue
        url, why = smoke_test.resolve_url(rule, ids)
        (resolvable if url else skipped).append((str(rule), why))
    print('  smoke_test：GET 带参路由 %d 条，可解析 %d 条，跳过 %d 条'
          % (len(resolvable) + len(skipped), len(resolvable), len(skipped)))
    for r, why in sorted(skipped):
        print('     SKIP %-52s %s' % (r, why))

    # E5 functional_test 的实际覆盖集合（从源码里抽出所有字面 URL，不靠估计）
    ft_src = (ROOT / 'scripts' / 'functional_test.py').read_text(encoding='utf-8')
    ft_urls = set()
    for m in re.finditer(r"'((?:/)[^'\s]*)'", ft_src):
        u = m.group(1)
        if '<' in u or '%' in u or ' ' in u or '\\' in u:
            continue
        ft_urls.add(u.split('?')[0])
    # 带参数 URL 是用 f-string 拼的，单独挑出来
    ft_fstrings = set(re.findall(r"f'(/[^']*)'", ft_src))
    methods = collections.Counter()
    non_get_paths = set()
    for r in rules:
        if r.endpoint == 'static':
            continue
        ms = sorted(r.methods - {'HEAD', 'OPTIONS'})
        for m in ms:
            methods[m] += 1
        if 'GET' not in ms:
            non_get_paths.add(str(r))
    print('  url_map 方法分布：%s' % dict(sorted(methods.items())))
    print('  非 GET 路径（去重）：%d 条；其中被 functional_test 覆盖的：%d 条'
          % (len(non_get_paths), len(non_get_paths & ft_urls)))
    print('     -> 未被 functional_test 覆盖的非 GET 路径：%d 条'
          % len(non_get_paths - ft_urls))
    print('  functional_test 字面 URL 集合共 %d 个（含 f-string %d 个）'
          % (len(ft_urls) + len(ft_fstrings), len(ft_fstrings)))

    # E7 这 5 条被覆盖的非 GET 路径是哪 5 条（可审计）
    covered_non_get = sorted(non_get_paths & ft_urls)
    for u in covered_non_get:
        eps = sorted({r.endpoint for r in rules if str(r) == u})
        print('     覆盖 %-40s -> %s' % (u, eps))

    # E8 permission_matrix / route_inventory 的返回值语义（静态读源码）
    for name, pat in (('route_inventory.py', r'return (\d)'),
                      ('permission_matrix.py', r'return (\d)'),
                      ('smoke_test.py', r'return (1 if [^\n]*)')):
        src = (ROOT / 'scripts' / name).read_text(encoding='utf-8')
        print('  %-22s 的返回语句：%s' % (name, re.findall(pat, src)))


def main():
    static_report()
    if '--dynamic' in sys.argv:
        dynamic_report()
    else:
        print('\n（加 --dynamic 并由 scripts/_sandbox_compat.py 驱动可追加动态统计）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
