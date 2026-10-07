"""只读探针：真实库 batch item 的 quality_status 分布 + 第二条发货明细取证（t5 过程材料）。"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import sqlite3  # noqa: E402

DB = os.path.join(ROOT, 'app.db')
con = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
cur = con.cursor()
print('--- production_batch_items.quality_status 分布 ---')
for row in cur.execute("SELECT COALESCE(quality_status,'<NULL>'), status, COUNT(*) "
                       "FROM production_batch_items GROUP BY 1,2 ORDER BY 3 DESC"):
    print(row)
print('--- 现库 finished_product（发货候选口径） ---')
for row in cur.execute("SELECT id, product_number, quantity, status, stock_kind, is_archived, "
                       "product_id, drawing_number FROM finished_product"):
    print(row)
con.close()
