import sqlite3
import sys

c = sqlite3.connect(sys.argv[1] if len(sys.argv) > 1 else 'app.db')
rows = list(c.execute('SELECT username, role, length(password_hash), password_hash FROM "user"'))
for name, role, n, h in rows:
    print(f'user={name!r} role={role} hash_len={n} method={(h or "").split("$")[0]}')
tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
print('table_count =', len(tables))
print('max_hash_len =', max([r[2] or 0 for r in rows] or [0]))
