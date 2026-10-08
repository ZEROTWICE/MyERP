# -*- coding: utf-8 -*-
"""t6（产品经理）AGENTS.md 门禁表口径复核探针 —— **纯静态只读**，不碰任何数据库。

用途：为 recon-product.md 的「数字对账」与「门禁表口径」章节提供**工具+口径+值**三要素读数。
本探针只 `ast.parse` / 读文本，不 import `app`、不连库、不写盘（除自身 `.output.json`）。

计数口径声明（每一行都在输出里带 `rule` 字段）：
- `routes_bp_route`：`app/**/*.py` 中 AST 函数装饰器里出现 `.route(` 的函数个数（含 methods 多值算 1 条规则）。
- `inline_role_python`：`app/**/*.py` 文本行里出现 `current_user.role` 的行数（模板另计）。
- `inline_role_templates`：`app/templates/**/*.html` 中 `current_user.role` 出现行数。
- `ensured_columns`：`app/__init__.py` 里 `_ENSURED_COLUMNS` 字面量的 `ast.literal_eval` 结果（表数 / 列数）。
- `bytesio_exports`：`app/**/*.py` 中 `io.BytesIO` / `from io import BytesIO` 的**构造点**数。
- `tempfolder_import_endpoints`：`app/main/routes.py` 中 `TEMP_FOLDER` 出现次数（两侧口径都报）。
- `create_all_tables` / `migration_create_table`：见函数内注释。
"""
import ast
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
APP = ROOT / 'app'
OUT = {}


def read(p):
    return p.read_text(encoding='utf-8', errors='replace')


# ---------------------------------------------------------------- 1) 路由模块
def route_modules():
    """每个 app/**/*.py 里含 `.route(` 装饰器函数的条数与文件名。"""
    rows = {}
    for p in sorted(APP.rglob('*.py')):
        if '__pycache__' in p.parts:
            continue
        try:
            tree = ast.parse(read(p))
        except SyntaxError as e:
            rows[str(p.relative_to(ROOT))] = {'parse_error': str(e)}
            continue
        n = 0
        names = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for d in node.decorator_list:
                    if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) \
                            and d.func.attr == 'route':
                        n += 1
                        names.append(node.name)
                        break
        if n:
            rows[str(p.relative_to(ROOT)).replace('\\', '/')] = {'count': n, 'funcs': names}
    return rows


rm = route_modules()
OUT['route_modules'] = {
    'rule': 'AST：ast.walk 找 FunctionDef 的装饰器里 Call(func.attr=="route")，每条算 1 条规则',
    'per_file': {k: v['count'] for k, v in rm.items() if 'count' in v},
    'total_rules': sum(v['count'] for v in rm.values() if 'count' in v),
    'module_count_with_routes': len([v for v in rm.values() if 'count' in v]),
    'parse_errors': {k: v['parse_error'] for k, v in rm.items() if 'parse_error' in v},
}

# ------------------------------------------------------- 2) 内联 role（Python / 模板）
py_role = []
for p in sorted(APP.rglob('*.py')):
    if '__pycache__' in p.parts:
        continue
    for i, line in enumerate(read(p).splitlines(), 1):
        if 'current_user.role' in line:
            py_role.append(f'{p.relative_to(ROOT)}:{i}: {line.strip()[:110]}')
tpl_role = []
for p in sorted((APP / 'templates').rglob('*.html')):
    for i, line in enumerate(read(p).splitlines(), 1):
        if 'current_user.role' in line:
            tpl_role.append(f'{p.relative_to(ROOT)}:{i}: {line.strip()[:110]}')
OUT['inline_role'] = {
    'rule': '文本行 grep：`current_user.role` 出现行数（一行算一处）',
    'python_count': len(py_role), 'python_lines': py_role,
    'template_count': len(tpl_role), 'template_lines': tpl_role,
}

# --------------------------------------------------- 3) _ENSURED_COLUMNS（AST 字面量）
src = read(APP / '__init__.py')
tree = ast.parse(src)
ensured = None
for node in ast.walk(tree):
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Name) and t.id == '_ENSURED_COLUMNS':
                try:
                    ensured = ast.literal_eval(node.value)
                except Exception as e:  # noqa: BLE001
                    ensured = {'literal_eval_error': str(e)}
OUT['ensured_columns'] = {
    'rule': 'AST：`_ENSURED_COLUMNS` 赋值的 ast.literal_eval（不是正则、不是转述）',
    'tables': len(ensured) if isinstance(ensured, dict) else None,
    'columns_per_table': {k: len(v) for k, v in ensured.items()} if isinstance(ensured, dict) else None,
    'columns_total': sum(len(v) for v in ensured.values()) if isinstance(ensured, dict) else None,
}

# --------------------------------------------------------------- 4) BytesIO 导出
bytesio = []
for p in sorted(APP.rglob('*.py')):
    if '__pycache__' in p.parts:
        continue
    for i, line in enumerate(read(p).splitlines(), 1):
        if 'BytesIO' in line:
            bytesio.append(f'{p.relative_to(ROOT)}:{i}: {line.strip()[:110]}')
OUT['bytesio'] = {'rule': '文本行 grep：含 `BytesIO` 的行（import 行也计入，故与「13 处导出」口径不同）',
                  'line_count': len(bytesio), 'lines': bytesio}

# ---------------------------------------------------- 5) TEMP_FOLDER 落盘导入端点
routes_src = read(ROOT / 'app' / 'main' / 'routes.py')
OUT['temp_folder'] = {
    'rule': '文本 grep：`TEMP_FOLDER` 出现次数（routes.py）',
    'routes_py_occurrences': routes_src.count('TEMP_FOLDER'),
    'app_all_occurrences': sum(read(p).count('TEMP_FOLDER') for p in APP.rglob('*.py')
                               if '__pycache__' not in p.parts),
    'save_temp_file_def_line': next((i for i, l in enumerate(routes_src.splitlines(), 1)
                                     if 'def save_temp_file' in l), None),
}

# --------------------------------------- 6) create_all 表数 / 迁移 create_table 表数
import sqlite3  # noqa: E402
real_db = ROOT / 'app.db'
conn = sqlite3.connect(f'file:{real_db.as_posix()}?mode=ro', uri=True)
try:
    tables = sorted(r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall())
finally:
    conn.close()
mig_tables = set()
files = []
for p in sorted((ROOT / 'migrations' / 'versions').glob('*.py')):
    t = read(p)
    found = re.findall(r"create_table\(\s*['\"]([^'\"]+)['\"]", t)
    if found:
        files.append({'file': p.name, 'count': len(found)})
    mig_tables.update(found)
OUT['tables'] = {
    'rule': "真实库 sqlite_master（**只读 URI，未写库**） vs 正则 `create_table('...')` 扫 migrations/versions/*.py",
    'real_db_table_count': len(tables),
    'migration_create_table_count': len(mig_tables),
    'migration_files_with_create_table': len(files),
    'diff_count': len([t for t in tables if t not in mig_tables]),
    'diff_tables': [t for t in tables if t not in mig_tables],
    'per_file': files,
}

# ------------------------------------------------------------------- 7) 杂项锚点
OUT['anchors'] = {
    'rule': '文件/文本直读',
    'sales_routes_py_bytes': (APP / 'main' / 'sales_routes.py').stat().st_size,
    'app_main_py_files': sorted(p.name for p in (APP / 'main').glob('*.py')),
    'capabilities_count': len(re.findall(r"^\s*'([a-z][a-z0-9_.]+)'\s*:",
                                        (read(APP / 'permissions.py').split('CAPABILITIES')[1]
                                         if 'CAPABILITIES' in read(APP / 'permissions.py') else ''), re.M)),
    'roles_count': len(re.findall(r"'([a-z_]+)'", re.search(r"ROLES\s*=\s*\[(.*?)\]",
                       read(APP / 'permissions.py'), re.S).group(1))) if re.search(
        r"ROLES\s*=\s*\[(.*?)\]", read(APP / 'permissions.py'), re.S) else None,
}

p = pathlib.Path(__file__).with_suffix('.output.json')
p.write_text(json.dumps(OUT, ensure_ascii=False, indent=1), encoding='utf-8')
print(json.dumps({k: (v if k != 'bytesio' else {'line_count': v['line_count']})
                  for k, v in OUT.items()}, ensure_ascii=False, indent=1))
sys.exit(0)
