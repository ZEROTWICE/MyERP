# -*- coding: utf-8 -*-
"""只读探针 D：真实 app.db 的只读快照信息（复制后以 ro 模式打开）。"""
import os
import shutil
import sqlite3
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
src = os.path.join(ROOT, 'app.db')
d = tempfile.mkdtemp(prefix='ro_')
p = os.path.join(d, 'app.db')
shutil.copy2(src, p)
c = sqlite3.connect('file:' + p.replace('\\', '/') + '?mode=ro', uri=True)
print('alembic_version =', c.execute('select version_num from alembic_version').fetchall())
names = [r[0] for r in c.execute("select name from sqlite_master where type='table'")]
print('table count (含 alembic_version) =', len(names))
total = 0
for t in names:
    total += c.execute('select count(*) from "%s"' % t).fetchone()[0]
print('total rows (全部表) =', total)
print('user count =', c.execute('select count(*) from "user"').fetchone()[0])
print('employee count =', c.execute('select count(*) from employee').fetchone()[0])
print('views =', [r[0] for r in c.execute("select name from sqlite_master where type='view'")])
print('indexes =', len([r[0] for r in c.execute("select name from sqlite_master where type='index'")]))
c.close()
print('ro copy dir =', d)
