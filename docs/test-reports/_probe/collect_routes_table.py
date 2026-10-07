# -*- coding: utf-8 -*-
"""只读探针：导出路由明细表（method / path / endpoint / 模块 / capability 装饰器）。

用途：为 t5「需求→测试用例双向追溯矩阵」（`docs/test-reports/2026-10/03-需求追溯矩阵.md`）
提供**可引用的真实端点坐标**——矩阵里出现的每个路径都来自本脚本的实测输出，不是从文档抄的。

只读保证：
  * 不连真实库：经 `scripts/_test_bootstrap.make_app()` 只建**副本**应用；
  * **不写任何文件**（包括本目录）：全部结果只打印到 stdout。
    —— 这一点是刻意的：workspace-write 沙箱禁止写盘（写盘失败会把退出码污染成 1，
    参考 `01-基线事实清单.md` §6.6 对「请求型脚本 exit code 不可信」的记录）。
    因此本脚本在沙箱内外**行为一致、returncode 恒为 0**（只要应用能建起来）。

用法：
  F:\\Miniconda\\envs\\wage\\python.exe -B scripts/_sandbox_compat.py docs/test-reports/_probe/collect_routes_table.py

已知输出特征（可与 01-基线事实清单 §2.2 对拍）：
  routes.py 192 / quality.py 27 / equipment.py 15 / purchase.py 13 /
  production_center.py 7 / shipping.py 6 / stock.py 5 / auth 4 / bootstrap 1
  ⇒ 含 static 共 271 条，与本脚本的「270 条（不含 static）」互为对照。
"""
import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

from _test_bootstrap import make_app  # noqa: E402

app, copy_path = make_app()

# ---- 从源码 AST 取「函数名 -> (文件, 行号, 装饰器能力列表)」----
func_meta = {}
for p in sorted((ROOT / 'app').rglob('*.py')):
    if '__pycache__' in str(p):
        continue
    rel = p.relative_to(ROOT).as_posix()
    try:
        tree = ast.parse(p.read_text(encoding='utf-8', errors='replace'))
    except SyntaxError:
        continue
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        caps = []
        for d in node.decorator_list:
            if isinstance(d, ast.Call):
                name = getattr(d.func, 'attr', None) or getattr(d.func, 'id', None)
                if name == 'require_capability':
                    caps += [a.value for a in d.args if isinstance(a, ast.Constant)]
        func_meta.setdefault(node.name, (rel, node.lineno, caps))

rows = []
for r in sorted(app.url_map.iter_rules(), key=lambda x: (str(x), sorted(x.methods))):
    if r.endpoint == 'static':
        continue
    fn = app.view_functions.get(r.endpoint)
    fname = fn.__name__ if fn else '?'
    fmod = getattr(fn, '__module__', '?') if fn else '?'
    rel, line, caps = func_meta.get(fname, ('?', 0, []))
    methods = ','.join(sorted(r.methods - {'HEAD', 'OPTIONS'}))
    rows.append((fmod, methods, str(r), r.endpoint, rel, line, ','.join(caps)))

print('# %d routes (excluding static)' % len(rows))
for m in sorted({x[0] for x in rows}):
    sel = [x for x in rows if x[0] == m]
    print('\n## %s  (%d)' % (m, len(sel)))
    for _fmod, methods, path, endpoint, rel, line, caps in sel:
        print('%-14s %-58s %-46s %s:%s  [%s]' % (methods, path, endpoint, rel, line, caps))

print('\ncopy: %s' % copy_path)
