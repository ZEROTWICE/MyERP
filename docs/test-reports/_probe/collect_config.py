# -*- coding: utf-8 -*-
"""只读探针 B：SystemConfig 种子、表/行数、请求型脚本 --no-dump 支持情况。"""
import ast
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

from _test_bootstrap import make_app  # noqa: E402

app, copy_path = make_app()

from app import db  # noqa: E402
from app.models import SystemConfig  # noqa: E402

with app.app_context():
    rows = SystemConfig.query.order_by(SystemConfig.key).all()
print(f'SystemConfig rows = {len(rows)}')
for r in rows:
    print(f'  {r.key:45s} type={r.value_type:5s} value={str(r.value)[:60]!r}')

with app.app_context():
    insp = db.inspect(db.engine)
    tables = insp.get_table_names()
    big = []
    for t in tables:
        try:
            n = db.session.execute(db.text(f'SELECT COUNT(*) FROM "{t}"')).scalar()
        except Exception as e:  # noqa: BLE001
            n = f'ERR {e}'
        big.append((t, n))
print('\n=== 表行数（副本上只读 SELECT COUNT(*)）===')
for t, n in sorted(big, key=lambda x: -(x[1] if isinstance(x[1], int) else -1)):
    print(f'  {t:35s} {n}')

print('\n=== 请求型脚本 --no-dump / 写盘点检查 ===')
for name in ('smoke_test.py', 'permission_matrix.py', 'functional_test.py'):
    p = ROOT / 'scripts' / name
    txt = p.read_text(encoding='utf-8', errors='replace')
    has_flag = '--no-dump' in txt
    writes = [i for i, l in enumerate(txt.splitlines(), 1)
              if re.search(r"open\(.*['\"]w['\"]", l) or 'json.dump' in l]
    print(f'  {name}: --no-dump={has_flag} 可疑写盘点={writes}')
    for i in writes:
        print(f'      {i}: ' + txt.splitlines()[i - 1].strip()[:130])

print('\n=== tests/ 目录 ===')
tp = ROOT / 'tests'
print(f'  exists={tp.exists()}')
if tp.exists():
    items = sorted(x.name for x in tp.iterdir())
    print(f'  entries={items}')
