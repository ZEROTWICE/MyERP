"""模板与权限一致性静态检查（无需启动应用）。

1) 用 Jinja2 解析所有模板，捕获语法错误
2) 交叉核对模板中 can()/can_any() 与路由上 @require_capability 用到的
   capability 是否都已在 app/permissions.py 的 CAPABILITIES 中登记
3) 校验 routes.py 中 ROLE_LANDING_ENDPOINTS 指向的端点确实存在

导航可见性与路由校验共用同一张能力表，本脚本用于防止两侧再次漂移。
"""
import ast
import pathlib
import re
import sys

from jinja2 import Environment, FileSystemLoader
from jinja2.exceptions import TemplateSyntaxError

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEMPLATE_DIR = ROOT / 'app' / 'templates'


def check_syntax():
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    failures = []
    total = 0
    for path in sorted(TEMPLATE_DIR.rglob('*.html')):
        total += 1
        rel = path.relative_to(TEMPLATE_DIR).as_posix()
        try:
            env.parse(path.read_text(encoding='utf-8'), filename=rel)
        except TemplateSyntaxError as e:
            failures.append(f'{rel}:{e.lineno}: {e.message}')
    return total, failures


def declared_capabilities():
    source = (ROOT / 'app' / 'permissions.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == 'CAPABILITIES':
                    return {k.value for k in node.value.keys}
    return set()


def used_capabilities():
    pattern = re.compile(r"can(?:_any)?\(([^)]*)\)")
    literal = re.compile(r"'([^']+)'")
    used = {}
    for path in sorted(TEMPLATE_DIR.rglob('*.html')):
        rel = path.relative_to(TEMPLATE_DIR).as_posix()
        for lineno, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            for call in pattern.findall(line):
                for cap in literal.findall(call):
                    used.setdefault(cap, []).append(f'{rel}:{lineno}')
    return used


ROUTE_FILES = ('app/main/routes.py', 'app/main/quality.py', 'app/main/production_center.py')


def route_capabilities():
    """收集路由文件中 @require_capability(...) 使用的 capability"""
    pattern = re.compile(r"require_capability\(([^)]*)\)")
    literal = re.compile(r"'([^']+)'")
    used = {}
    for rel in ROUTE_FILES:
        path = ROOT / rel
        if not path.exists():
            continue
        for lineno, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            for call in pattern.findall(line):
                for cap in literal.findall(call):
                    used.setdefault(cap, []).append(f'{rel}:{lineno}')
    return used


def landing_endpoint_problems():
    """ROLE_LANDING_ENDPOINTS 指向的 main.xxx 必须存在同名视图函数"""
    source = (ROOT / 'app' / 'main' / 'routes.py').read_text(encoding='utf-8')
    tree = ast.parse(source)

    endpoints = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == 'ROLE_LANDING_ENDPOINTS':
                    for k, v in zip(node.value.keys, node.value.values):
                        endpoints[k.value] = v.value

    defined = set()
    for rel in ROUTE_FILES:
        path = ROOT / rel
        if not path.exists():
            continue
        for match in re.finditer(r'^def (\w+)\(', path.read_text(encoding='utf-8'), re.M):
            defined.add(match.group(1))

    problems = []
    for role, endpoint in endpoints.items():
        func = endpoint.split('.', 1)[-1]
        if func not in defined:
            problems.append(f'{role} -> {endpoint} (未找到视图函数 {func})')
    return len(endpoints), problems


def main():
    total, failures = check_syntax()
    print(f'[templates] parsed {total} files')
    for f in failures:
        print(f'  SYNTAX ERROR  {f}')

    declared = declared_capabilities()
    tpl_used = used_capabilities()
    route_used = route_capabilities()
    print(f'[permissions] {len(declared)} declared / {len(tpl_used)} used in templates / '
          f'{len(route_used)} used on routes')

    unknown = {}
    for cap, locs in list(tpl_used.items()) + list(route_used.items()):
        if cap not in declared:
            unknown.setdefault(cap, []).extend(locs)
    for cap, locs in sorted(unknown.items()):
        print(f'  UNKNOWN CAPABILITY  {cap}  <- {", ".join(locs)}')

    n_endpoints, endpoint_problems = landing_endpoint_problems()
    print(f'[landing] {n_endpoints} role landing endpoints')
    for p in endpoint_problems:
        print(f'  BROKEN ENDPOINT  {p}')

    if failures or unknown or endpoint_problems:
        print('RESULT: FAIL')
        return 1
    print('RESULT: OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
