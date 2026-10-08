# -*- coding: utf-8 -*-
"""t7 文档漂移对账：数字实测探针（只读，不写库、不改既有文件）。
口径全部写明；输出可直接抄进 recon-docs.md。
"""
import os
import re
import sys
import ast

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

out = []


def p(s=""):
    out.append(s)


def sec(t):
    p("")
    p("=" * 70)
    p(t)
    p("=" * 70)


# ---------- 1. 迁移 create_table / 表集合 ----------
sec("1. migrations/versions 的 create_table 与表集合（口径：正则 create_table('name')）")
verdir = os.path.join("migrations", "versions")
files = sorted(f for f in os.listdir(verdir) if f.endswith(".py"))
p("migrations/versions/*.py 文件数 = %d" % len(files))

ct_files = []
mig_names = {}
guarded = []
for f in files:
    s = open(os.path.join(verdir, f), encoding="utf-8").read()
    ns = re.findall(r"create_table\(\s*['\"]([A-Za-z_0-9]+)['\"]", s)
    if not ns:
        continue
    ct_files.append((f, len(ns)))
    mig_names[f] = ns
    # 守卫启发式：同一文件内是否存在任何表存在性判断
    g = bool(re.search(r"has_table|get_table_names|insp\.|inspector\.|if_exists|checkfirst", s))
    guarded.append((f, g))

p("含 create_table( 调用的文件数 = %d" % len(ct_files))
for f, n in ct_files:
    p("   %-55s ct=%d" % (f, n))
p("create_table 调用总数 = %d" % sum(n for _, n in ct_files))

allmig = set()
for ns in mig_names.values():
    allmig.update(ns)
p("迁移里出现的唯一表名 = %d" % len(allmig))

p("---- 逐文件是否有表存在性守卫（启发式） ----")
for f, g in guarded:
    p("   %-55s guarded=%s" % (f, g))

# ---------- 2. metadata / 真库表集合 ----------
sec("2. metadata 表集合 vs 迁移表集合（差集口径）")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
import app.models  # noqa
from app import db  # noqa

meta = set(db.metadata.tables.keys())
p("db.metadata.tables 数 = %d" % len(meta))
p("metadata 有、迁移无（差集） = %d" % len(meta - allmig))
for t in sorted(meta - allmig):
    p("   - %s" % t)
p("迁移有、metadata 无 = %d" % len(allmig - meta))
for t in sorted(allmig - meta):
    p("   + %s" % t)

# 真库表集合（只读）
import sqlite3
con = sqlite3.connect("file:app.db?mode=ro", uri=True)
rows = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
con.close()
p("app.db（只读打开）表数 = %d" % len(rows))
biz = [r for r in rows if r != "alembic_version"]
p("剔除 alembic_version 后 = %d" % len(biz))
p("真库表 ∉ 迁移 create_table = %d" % len(set(biz) - allmig))
for t in sorted(set(biz) - allmig):
    p("   - %s" % t)

# ---------- 3. _ENSURED_COLUMNS ----------
sec("3. _ENSURED_COLUMNS（AST 字面量口径）")
s = open("app/__init__.py", encoding="utf-8").read()
t = ast.parse(s)
for n in t.body:
    if isinstance(n, ast.Assign):
        for x in n.targets:
            if isinstance(x, ast.Name) and isinstance(n.value, ast.Dict):
                tot = 0
                det = []
                for k, v in zip(n.value.keys, n.value.values):
                    c = len(v.elts) if isinstance(v, (ast.List, ast.Tuple)) else 0
                    tot += c
                    det.append("%s=%d" % (k.value, c))
                p("%s line=%d tables=%d cols=%d" % (x.id, n.lineno, len(n.value.keys), tot))
                p("   " + " ".join(det))

# ---------- 4. 模型类 / 表 ----------
sec("4. models.py 模型类数（check_properties 口径见门禁输出）")
ms = open("app/models.py", encoding="utf-8").read()
mt = ast.parse(ms)
cls = [n.name for n in ast.walk(mt) if isinstance(n, ast.ClassDef)]
p("app/models.py ClassDef 数 = %d" % len(cls))
p("app/models.py 行数 = %d" % len(ms.splitlines()))

# ---------- 5. 导入端点落盘 ----------
sec("5. 落盘导入端点（口径：请求内有 file.save( 的视图函数）")
for fn in sorted(os.listdir("app/main")):
    if not fn.endswith(".py"):
        continue
    src = open(os.path.join("app/main", fn), encoding="utf-8").read()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        p("%-25s SYNTAX ERROR" % fn)
        continue
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            body = ast.dump(node)
            if "save" in body and ("TEMP_FOLDER" in body or "save_temp_file" in body or "mkdtemp" in body):
                hits.append((node.name, node.lineno))
    if hits:
        p("%-25s %d 个: %s" % (fn, len(hits), hits))

# 文本口径：file.save(
sec("5b. 文本口径 file.save( / pd.read_excel( / save_temp_file(")
for fn in sorted(os.listdir("app/main")):
    if not fn.endswith(".py"):
        continue
    lines = open(os.path.join("app/main", fn), encoding="utf-8").read().splitlines()
    ls = [i + 1 for i, l in enumerate(lines) if "file.save(" in l]
    xl = [i + 1 for i, l in enumerate(lines) if "pd.read_excel(" in l]
    st = [i + 1 for i, l in enumerate(lines) if "save_temp_file(" in l]
    if ls or xl or st:
        p("%-25s file.save=%s pd.read_excel=%s save_temp_file=%s" % (fn, ls, xl, st))

# ---------- 6. 导出 BytesIO ----------
sec("6. io.BytesIO（文本口径 'BytesIO()'）")
tot = 0
for dp, dn, fns in os.walk("app"):
    if "__pycache__" in dp:
        continue
    for fn in sorted(fns):
        if not fn.endswith(".py"):
            continue
        path = os.path.join(dp, fn)
        lines = open(path, encoding="utf-8").read().splitlines()
        ls = [i + 1 for i, l in enumerate(lines) if "BytesIO()" in l]
        if ls:
            p("%-45s %d %s" % (path, len(ls), ls))
            tot += len(ls)
p("BytesIO() 合计 = %d" % tot)

# ---------- 7. 内置 role / 模板 ----------
sec("7. 内联 current_user.role（AST 口径）")
tot = 0
for dp, dn, fns in os.walk("app"):
    if "__pycache__" in dp:
        continue
    for fn in sorted(fns):
        if not fn.endswith(".py"):
            continue
        path = os.path.join(dp, fn)
        src = open(path, encoding="utf-8").read()
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        ls = sorted(
            x.lineno
            for x in ast.walk(tree)
            if isinstance(x, ast.Attribute)
            and x.attr == "role"
            and isinstance(x.value, ast.Name)
            and x.value.id == "current_user"
        )
        if ls:
            p("%-45s %d %s" % (path, len(ls), ls))
            tot += len(ls)
p("Python 合计 = %d" % tot)

tot = 0
for dp, dn, fns in os.walk("app/templates"):
    for fn in sorted(fns):
        path = os.path.join(dp, fn)
        lines = open(path, encoding="utf-8").read().splitlines()
        ls = [i + 1 for i, l in enumerate(lines) if "current_user.role" in l]
        if ls:
            p("%-45s %d %s" % (path, len(ls), ls))
            tot += len(ls)
p("模板合计 = %d" % tot)

# ---------- 8. bp.route ----------
sec("8. @bp.route 装饰器（AST 口径）")
tot = 0
for dp, dn, fns in os.walk("app"):
    if "__pycache__" in dp:
        continue
    for fn in sorted(fns):
        if not fn.endswith(".py"):
            continue
        path = os.path.join(dp, fn)
        src = open(path, encoding="utf-8").read()
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        n = 0
        for x in ast.walk(tree):
            if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for d in x.decorator_list:
                    dd = d.func if isinstance(d, ast.Call) else d
                    if (
                        isinstance(dd, ast.Attribute)
                        and dd.attr == "route"
                        and isinstance(dd.value, ast.Name)
                        and dd.value.id == "bp"
                    ):
                        n += 1
        if n:
            p("%-45s %d" % (path, n))
            tot += n
p("TOTAL = %d" % tot)

# ---------- 9. 模板数 ----------
sec("9. 模板 / 迁移文件数")
n = sum(
    len([f for f in fns if f.lower().endswith(".html")])
    for dp, dn, fns in os.walk("app/templates")
)
p("app/templates 下 .html 文件数 = %d" % n)
p("app/templates 下全部文件数 = %d" % sum(len(fns) for dp, dn, fns in os.walk("app/templates")))

# ---------- 10. routes.py 行数 ----------
sec("10. app/main/routes.py 行数（字节口径）")
b = open("app/main/routes.py", "rb").read()
tx = b.decode("utf-8")
p("bytes=%d splitlines=%d LF=%d CRLF=%d endswith_LF=%s BOM=%s" % (
    len(b), len(tx.splitlines()), tx.count("\n"), b.count(b"\r\n"), tx.endswith("\n"), b[:3] == b"\xef\xbb\xbf"))

# ---------- 11. 大文件/死文件 ----------
sec("11. app/main 下文件清单与大小")
for f in sorted(os.listdir("app/main")):
    fp = os.path.join("app/main", f)
    if os.path.isfile(fp):
        p("   %-25s %d bytes" % (f, os.path.getsize(fp)))

open(os.path.join("test-reports-2026-10", "reconcile-2026-10-08", "probe_docs_numbers.output.txt"),
     "w", encoding="utf-8").write("\n".join(out))
print("\n".join(out))
