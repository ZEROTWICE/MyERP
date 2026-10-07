# -*- coding: utf-8 -*-
"""只读事实采集探针：路由/模型/权限/schema。绝不写真实 app.db。

用法：F:\\Miniconda\\envs\\wage\\python.exe -B docs/test-reports/_probe/collect_facts.py
"""
import ast
import collections
import json
import os
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

out = {}

# ---------- 1. 路由 ----------
from _test_bootstrap import make_app  # noqa: E402

app, copy_path = make_app()
rules = list(app.url_map.iter_rules())
by_rule = collections.defaultdict(list)
for r in rules:
    for m in sorted(r.methods - {'HEAD', 'OPTIONS'}):
        by_rule[(m, str(r))].append(r.endpoint)
dup = {k: v for k, v in by_rule.items() if len(v) > 1}

mod_of = {}
for r in rules:
    fn = app.view_functions.get(r.endpoint)
    mod = getattr(fn, '__module__', 'unknown') if fn else 'MISSING'
    mod_of.setdefault(mod, []).append(str(r))

out['routes'] = {
    'total_rules': len(rules),
    'duplicates': {f'{k[0]} {k[1]}': v for k, v in dup.items()},
    'by_module': {k: len(v) for k, v in sorted(mod_of.items(), key=lambda x: -len(x[1]))},
    'get_noarg': len([r for r in rules if 'GET' in r.methods and not r.arguments and r.endpoint != 'static']),
    'get_witharg': len([r for r in rules if 'GET' in r.methods and r.arguments and r.endpoint != 'static']),
    'non_get': len([r for r in rules if 'GET' not in r.methods]),
}
out['db_copy'] = copy_path

# ---------- 2. 模型 / 表 ----------
import sqlite3  # noqa: E402

from app import db  # noqa: E402
from app import models as M  # noqa: E402

model_classes = []
for name in dir(M):
    obj = getattr(M, name)
    if isinstance(obj, type) and issubclass(obj, db.Model) and obj is not db.Model:
        model_classes.append(name)
out['models'] = {
    'count': len(model_classes),
    'with_tablename': sorted(m.__tablename__ for m in [getattr(M, n) for n in model_classes] if hasattr(m, '__tablename__')),
}

with app.app_context():
    insp = db.inspect(db.engine)
    tables = sorted(insp.get_table_names())
out['tables'] = {'count': len(tables), 'names': tables}

# _ENSURED_COLUMNS
src = (ROOT / 'app' / '__init__.py').read_text(encoding='utf-8')
tree = ast.parse(src)
ens = None
for node in tree.body:
    if isinstance(node, ast.Assign) and any(getattr(t, 'id', None) == '_ENSURED_COLUMNS' for t in node.targets):
        ens = ast.literal_eval(node.value)
out['ensured_columns'] = {
    'tables': len(ens),
    'columns': sum(len(v) for v in ens.values()),
    'per_table': {k: len(v) for k, v in ens.items()},
}

# ---------- 3. 不在迁移里的表 ----------
mig_dir = ROOT / 'migrations' / 'versions'
created = set()
for p in sorted(mig_dir.glob('*.py')):
    txt = p.read_text(encoding='utf-8', errors='replace')
    for m in re.finditer(r"create_table\(\s*['\"]([^'\"]+)['\"]", txt):
        created.add(m.group(1))
out['migration'] = {
    'revision_files': len(list(mig_dir.glob('*.py'))),
    'tables_in_migrations': len(created),
    'tables_not_in_migrations': sorted(set(tables) - created),
    'tables_not_in_migrations_count': len(set(tables) - created),
}
uncond = []
for p in sorted(mig_dir.glob('*.py')):
    txt = p.read_text(encoding='utf-8', errors='replace')
    tree2 = ast.parse(txt)
    n = 0
    for node in ast.walk(tree2):
        if isinstance(node, ast.Call):
            f = node.func
            fname = getattr(f, 'attr', None)
            if fname == 'create_table':
                # 判断是否被 if 守卫：粗略用所在行列文本判断缩进
                n += 1
    if n:
        uncond.append((p.name, n))
out['migration']['create_table_calls_per_file'] = uncond

# ---------- 4. 权限 ----------
import importlib  # noqa: E402

perm = importlib.import_module('app.permissions')
out['permissions'] = {
    'roles': len(perm.ROLES),
    'capabilities': len(perm.CAPABILITIES),
    'search_type_capabilities': len(perm.SEARCH_TYPE_CAPABILITIES),
    'capability_names': sorted(perm.CAPABILITIES),
}

# 路由侧使用的能力
used = set()
for p in (ROOT / 'app').rglob('*.py'):
    if '__pycache__' in str(p):
        continue
    txt = p.read_text(encoding='utf-8', errors='replace')
    for m in re.finditer(r"require_capability\(\s*['\"]([^'\"]+)['\"]", txt):
        used.add(m.group(1))
out['permissions']['used_on_routes'] = len(used)
out['permissions']['used_minus_declared'] = sorted(used - set(perm.CAPABILITIES))
out['permissions']['declared_minus_used'] = sorted(set(perm.CAPABILITIES) - used)

# ---------- 5. 内联 current_user.role ----------
inline_py = []
for p in (ROOT / 'app').rglob('*.py'):
    if '__pycache__' in str(p):
        continue
    for i, line in enumerate(p.read_text(encoding='utf-8', errors='replace').splitlines(), 1):
        if 'current_user.role' in line:
            inline_py.append(f'{p.relative_to(ROOT).as_posix()}:{i}')
inline_tpl = []
for p in (ROOT / 'app' / 'templates').rglob('*.html'):
    for i, line in enumerate(p.read_text(encoding='utf-8', errors='replace').splitlines(), 1):
        if 'current_user.role' in line:
            inline_tpl.append(f'{p.relative_to(ROOT).as_posix()}:{i}')
out['inline_role'] = {'python': inline_py, 'templates': inline_tpl}

# ---------- 6. 路由上无权限校验的视图（粗筛） ----------
decorated = {}
for p in (ROOT / 'app').rglob('*.py'):
    if '__pycache__' in str(p):
        continue
    txt = p.read_text(encoding='utf-8', errors='replace')
    tree3 = ast.parse(txt)
    for node in ast.walk(tree3):
        if isinstance(node, ast.FunctionDef):
            decs = []
            for d in node.decorator_list:
                if isinstance(d, ast.Call):
                    decs.append(getattr(d.func, 'attr', getattr(d.func, 'id', '')))
                else:
                    decs.append(getattr(d, 'attr', getattr(d, 'id', '')))
            decorated.setdefault(node.name, set()).update(decs)
no_check = []
for r in rules:
    fn = app.view_functions.get(r.endpoint)
    if not fn or r.endpoint == 'static':
        continue
    name = fn.__name__
    decs = decorated.get(name, set())
    if not ({'login_required', 'require_capability'} & decs):
        no_check.append((r.endpoint, name, sorted(decs)))
out['routes_no_login_or_capability'] = [{'endpoint': e, 'func': n, 'decorators': d} for e, n, d in no_check]

print(json.dumps(out, ensure_ascii=False, indent=1))
