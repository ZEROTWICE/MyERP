# -*- coding: utf-8 -*-
"""更正确认探针：(a) route_inventory 原生 vs shim 的真实 exit code；
(b) 行数为 0 的表实体数与名单；非空表数复核。"""
import os
import pathlib
import re
import sqlite3
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[3]
PY = sys.executable
print('interpreter =', PY)
print('cwd =', os.getcwd())

compat = ROOT / 'scripts' / '_sandbox_compat.py'
target = ROOT / 'scripts' / 'route_inventory.py'

print('\n=== (a1) 原生：python -B scripts/route_inventory.py ===')
p = subprocess.run([PY, '-B', str(target)], cwd=str(ROOT),
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
print('exit =', p.returncode)
err = (p.stderr or b'').decode('utf-8', 'replace')
tail = [l for l in err.strip().splitlines() if l.strip()][-4:]
for l in tail:
    print('  ERR:', l)
out = (p.stdout or b'').decode('utf-8', 'replace')
print('  stdout 首行:', (out.splitlines() or ['<empty>'])[0][:100])

print('\n=== (a2) shim：python -B scripts/_sandbox_compat.py scripts/route_inventory.py ===')
p2 = subprocess.run([PY, '-B', str(compat), str(target)], cwd=str(ROOT),
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
print('exit =', p2.returncode)
o2 = (p2.stdout or b'').decode('utf-8', 'replace').splitlines()
for l in o2[:3]:
    print('  OUT:', l)

print('\n=== (b) 行数为 0 的表（只读副本实算）===')
d = tempfile.mkdtemp(prefix='zerocheck_')
dst = os.path.join(d, 'app.db')
import shutil  # noqa: E402

shutil.copy2(ROOT / 'app.db', dst)
c = sqlite3.connect('file:' + dst.replace('\\', '/') + '?mode=ro', uri=True)
names = [r[0] for r in c.execute(
    "select name from sqlite_master where type='table' and name not like 'sqlite_%'")]
zero, nonzero = [], []
for t in names:
    n = c.execute('select count(*) from "%s"' % t).fetchone()[0]
    (zero if n == 0 else nonzero).append((t, n))
c.close()
print('名字含 alembic_version 的业务表总数 =', len(names))
print('行数为 0 的表实体数 =', len(zero))
print('行数 > 0 的表实体数 =', len(nonzero))
print('零行表名单（' + str(len(zero)) + ' 项）：')
for t, _ in zero:
    print(f'  {t}')
