# -*- coding: utf-8 -*-
"""t7 补充探针：迁移 create_table 的守卫分类（只读）。"""
import ast
import os
import re

VD = "migrations/versions"
out = []


def p(s=""):
    out.append(s)


p("口径 A：正则 create_table(\\s*['\"]name['\"]) —— 字面表名")
p("口径 B：AST 调用 op.create_table / create_table 节点")
p("口径 C：守卫 = 该 create_table 调用位于某个引用 has_table/get_table_names 的 if 之内")
p("")
rows = []
for f in sorted(os.listdir(VD)):
    if not f.endswith(".py"):
        continue
    path = os.path.join(VD, f)
    src = open(path, encoding="utf-8").read()
    lit = re.findall(r"create_table\(\s*['\"]([A-Za-z_0-9]+)['\"]", src)
    tree = ast.parse(src)
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
    ct_nodes = []
    for n in calls:
        fn = n.func
        if isinstance(fn, ast.Attribute) and fn.attr == "create_table":
            ct_nodes.append(n)
        elif isinstance(fn, ast.Name) and fn.id == "create_table":
            ct_nodes.append(n)
    # 每个 create_table 调用是否被 has_table 判断包裹：取该文件 upgrade() 内所有 If 的 test 源码
    guards = []
    for n in ast.walk(tree):
        if isinstance(n, ast.If):
            t = ast.unparse(n.test) if hasattr(ast, "unparse") else ""
            if "has_table" in t or "get_table_names" in t:
                guards.append((n.lineno, t.replace("\n", " ")[:80]))
    rows.append((f, len(lit), len(ct_nodes), len(guards), sorted(set(lit))))

p("%-58s litASTguard" % "file")
tot_lit = tot_ct = 0
for f, a, b, g, names in rows:
    if b == 0:
        continue
    tot_lit += a
    tot_ct += b
    p("%-58s %3d %5d %5d" % (f, a, b, g))
p("")
p("含 create_table 调用的文件数（AST）= %d" % len([r for r in rows if r[2] > 0]))
p("含字面表名 create_table 的文件数（正则）= %d" % len([r for r in rows if r[1] > 0]))
p("create_table 调用总数（AST）= %d" % tot_ct)
p("字面表名调用总数（正则）= %d" % tot_lit)
p("")
p("逐文件守卫 if 列表（引用 has_table / get_table_names 的 If）：")
for f, a, b, g, names in rows:
    if b == 0:
        continue
    p("  %-58s guard_ifs=%d" % (f, g))

p("")
p("=== p0p2messtables 的 upgrade() 体 ===")
src = open(os.path.join(VD, "p0p2messtables_add_create_all_tables.py"), encoding="utf-8").read()
tree = ast.parse(src)
for n in tree.body:
    if isinstance(n, ast.FunctionDef) and n.name in ("upgrade", "downgrade"):
        p("--- %s() ---" % n.name)
        seg = src.splitlines()[n.lineno - 1:n.end_lineno]
        for i, l in enumerate(seg, n.lineno):
            p("%4d %s" % (i, l))

open(os.path.join("test-reports-2026-10", "reconcile-2026-10-08", "probe_migration_guard.output.txt"),
     "w", encoding="utf-8").write("\n".join(out))
print("\n".join(out))
