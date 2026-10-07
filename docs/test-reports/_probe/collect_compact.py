# -*- coding: utf-8 -*-
"""紧凑事实采集：仅打印待核对的清单项。"""
import ast
import collections
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

from _test_bootstrap import make_app  # noqa: E402

app, _ = make_app()
rules = list(app.url_map.iter_rules())

decorated = {}
for p in (ROOT / 'app').rglob('*.py'):
    if '__pycache__' in str(p):
        continue
    try:
        tree = ast.parse(p.read_text(encoding='utf-8', errors='replace'))
    except SyntaxError as e:
        print(f'PARSE-FAIL {p.name}: {e}')
        continue
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            decs = []
            for d in node.decorator_list:
                tgt = d.func if isinstance(d, ast.Call) else d
                decs.append(getattr(tgt, 'attr', getattr(tgt, 'id', '?')))
            decorated.setdefault(node.name, set()).update(decs)

print('=== 路由无 login_required/require_capability（粗筛，需人工判定）===')
for r in sorted(rules, key=lambda x: str(x)):
    fn = app.view_functions.get(r.endpoint)
    if not fn or r.endpoint == 'static' or r.endpoint.startswith('bootstrap.'):
        continue
    name = fn.__name__
    decs = decorated.get(name)
    if decs is None:
        print(f'  ?  {r.endpoint:55s} {name:40s} (未在 app/ 内找到同名函数定义)')
        continue
    if not ({'login_required', 'require_capability'} & decs):
        print(f'  NO {r.endpoint:55s} {name:40s} decorators={sorted(decs)}')

print()
print('=== 使用 require_capability 的路由端点数 ===')
n_cap = 0
for r in rules:
    fn = app.view_functions.get(r.endpoint)
    if not fn:
        continue
    if 'require_capability' in decorated.get(fn.__name__, set()):
        n_cap += 1
print(f'  {n_cap} / {len(rules)}')
