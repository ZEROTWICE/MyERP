# -*- coding: utf-8 -*-
"""t6（产品经理）盘点「落盘导入端点」与「内存流导入端点」 —— 纯静态只读。

口径：AST 找 `@bp.route(...)` 装饰的函数（端点），再在其函数体内按行号定位
`file.save(` / `save_temp_file(` / `read_excel(` 的调用，据此判定该端点是否**落盘**。
输出端点名 + 路由 + 触发行 + 落盘目标变量名。
"""
import ast
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
TARGETS = ('app/main/routes.py', 'app/main/quality.py', 'app/main/stock.py',
           'app/main/purchase.py', 'app/main/equipment.py',
           'app/main/production_center.py', 'app/main/shipping.py')


def read(p):
    return (ROOT / p).read_text(encoding='utf-8', errors='replace')


out = {}
for rel in TARGETS:
    src = read(rel)
    lines = src.splitlines()
    tree = ast.parse(src)
    eps = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        route = None
        for d in node.decorator_list:
            if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) \
                    and d.func.attr == 'route' and d.args:
                try:
                    route = ast.literal_eval(d.args[0])
                except Exception:  # noqa: BLE001
                    route = '<?>'
        if route is None:
            continue
        end = node.end_lineno or node.lineno
        body = '\n'.join(lines[node.lineno - 1:end])
        disk, memory = [], []
        for i in range(node.lineno, end + 1):
            ln = lines[i - 1]
            if re.search(r'\bfile\.save\(', ln) or 'save_temp_file(' in ln:
                disk.append({'line': i, 'text': ln.strip()[:120]})
            if re.search(r'read_excel\(\s*file\s*\)', ln) or re.search(r'read_excel\(\s*\w*file\w*\s*\)', ln):
                memory.append({'line': i, 'text': ln.strip()[:120]})
            elif 'read_excel(' in ln and 'temp_path' not in ln:
                memory.append({'line': i, 'text': ln.strip()[:120]})
        if disk or memory:
            eps.append({'endpoint': node.name, 'route': route,
                        'def_line': node.lineno,
                        'disk_writes': disk, 'memory_reads': memory})
    out[rel] = eps

print(json.dumps(out, ensure_ascii=False, indent=1))
pathlib.Path(__file__).with_suffix('.output.json').write_text(
    json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
