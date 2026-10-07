"""t3 夹具缺口实测探针（只读：只在 app.db 的临时副本上运行）。

用途：为「t3 夹具风险登记与可行性裁定」提供可复跑的原始数据：
  A1 finished_product 行数与 stock_kind 分布（stock.py:20 按 stock_kind 过滤）
  A2 is_archived 的 NULL / True 分布（决定 T-C 数据级差分能否直接在真实库形态上跑）
  A3 raw_material 行数与 quantity（决定报废扣料用例的可观测幅度）
  A4 副本库 0 行表总数与清单（= 真实库形态）
  B1 seed_fixtures() 实际覆盖的对象数
  B2 seed 之后仍为 0 行的"关键主链表"清单（24 张）

跑法（仓库根目录）：
    & 'F:\\Miniconda\\envs\\wage\\python.exe' -B scripts/_sandbox_compat.py docs/test-reports/_probe/probe_fixture_gaps.py
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

FAILS = []


def check(label, ok, detail=''):
    print(f'[{"PASS" if ok else "FAIL"}] {label}' + (f' | {detail}' if detail else ''))
    if not ok:
        FAILS.append(label)


def section(t):
    print('\n' + '=' * 78)
    print(t)
    print('=' * 78)


from _test_bootstrap import make_app, seed_fixtures  # noqa: E402

app, copy_path = make_app(fresh=True)
print(f'副本库 = {copy_path}')

from app import db  # noqa: E402
from app import models as M  # noqa: E402
from sqlalchemy import text  # noqa: E402

# 关键主链表（采购/发货/设备/炉次/工件/质检/料账/正品库）
CHAIN_TABLES = [
    'production_record', 'production_record_materials', 'material_allocations',
    'nonconformity_records', 'inspection_records', 'inspection_tasks',
    'inspection_templates', 'inspection_items', 'inspection_base_items',
    'purchase_requisitions', 'purchase_requisition_items', 'purchase_orders',
    'purchase_order_items', 'purchase_settlements', 'goods_receipts', 'goods_receipt_items',
    'shipments', 'shipment_items', 'shipment_receipts',
    'suppliers', 'equipment', 'heat_lots', 'heat_lot_slots', 'workpieces',
    'work_centers', 'work_center_equipment', 'workpiece_events', 'finished_product',
    'inventory_counts', 'inventory_count_items', 'task_workpieces', 'material_requisitions',
]


def table_names():
    return [r[0] for r in db.session.execute(text(
        "select name from sqlite_master where type='table' order by name"))]


def zero_tables():
    out = []
    for name in table_names():
        n = db.session.execute(text(f'select count(*) from "{name}"')).scalar()
        if not n:
            out.append(name)
    return out


section('A 真实库形态基线（副本 = 逐字节复制 app.db）')
with app.app_context():
    fp = M.FinishedProduct.query.all()
    dist = {}
    for r in fp:
        key = 'NULL' if r.stock_kind is None else r.stock_kind
        dist[key] = dist.get(key, 0) + 1
    print(f'  A1 finished_product 行数 = {len(fp)}，stock_kind 分布 = {dist}')
    shippable = M.FinishedProduct.query.filter(
        M.FinishedProduct.stock_kind.in_(('fg', 'wip_part'))).count()
    print(f'     stock_kind in (fg, wip_part) 行数 = {shippable}'
          f'   （app/main/stock.py:20 按 stock_kind 过滤）')
    check('A1 finished_product 有行但无一行是 fg/wip_part 口径', len(fp) > 0 and shippable == 0,
          f'行数={len(fp)}, 可发货口径行数={shippable}')

    arch = {}
    for name in ('FinishedProduct', 'RawMaterial', 'Product', 'Consumable', 'Employee'):
        m = getattr(M, name, None)
        col = getattr(m, 'is_archived', None) if m is not None else None
        if col is None:
            continue
        total = m.query.count()
        n_null = m.query.filter(col.is_(None)).count()
        n_true = m.query.filter(col.is_(True)).count()
        arch[name] = (total, n_null, n_true)
    print(f'  A2 is_archived (行数, NULL, True) = {arch}')
    check('A2 is_archived 无 NULL 行（T-C 数据级差分必须自建 NULL 行）',
          all(v[1] == 0 for v in arch.values()) and arch, f'{arch}')

    rm = M.RawMaterial.query.all()
    print(f'  A3 raw_material 行数 = {len(rm)}，quantity = {[r.quantity for r in rm]}')
    check('A3 raw_material 仅 1 行且 quantity=1.0（扣料幅度退化：1→0）',
          len(rm) == 1 and float(rm[0].quantity or 0) == 1.0,
          f'{[(r.internal_number, r.quantity) for r in rm]}')

    all_zero = zero_tables()
    print(f'  A4 副本库 0 行表 = {len(all_zero)} 张 / 共 {len(table_names())} 张')
    chain_zero = [t for t in CHAIN_TABLES if t in all_zero]
    chain_nonzero = [t for t in CHAIN_TABLES if t not in all_zero]
    print(f'     关键主链表 {len(CHAIN_TABLES)} 张：0 行 {len(chain_zero)} 张，非空 {chain_nonzero}')

section('B seed_fixtures() 的覆盖边界')
with app.app_context():
    zero_before = set(zero_tables())

made = seed_fixtures(app)
with app.app_context():
    zero_after = set(zero_tables())

print(f'  B1 seed_fixtures() 返回对象数 = {len(made)} -> {sorted(made)}')
print(f'  B2 0 行表：seed 前 {len(zero_before)} 张 -> seed 后 {len(zero_after)} 张'
      f'（被填 {len(zero_before - zero_after)} 张）')
still_zero_chain = [t for t in CHAIN_TABLES if t in zero_after]
print(f'     关键主链表中 seed 后仍 0 行 = {len(still_zero_chain)} 张')
print(f'     {still_zero_chain}')
check('B1 seed_fixtures 覆盖对象数 <= 10（远小于主链表规模）', len(made) <= 10, f'{len(made)}')
check('B2 关键主链表 seed 后仍有 >= 20 张 0 行（端到端必须自建夹具）',
      len(still_zero_chain) >= 20, f'{len(still_zero_chain)} 张')

section('结果')
print(f'副本库 = {copy_path}（真实 app.db 未被访问）')
print(f'FAIL 项 = {len(FAILS)}')
for x in FAILS:
    print(f'  - {x}')
print('注：FAIL 表示"探针预期与实际不符"；A1/A2/A3/B2 的 PASS 恰恰说明夹具缺口成立。')
sys.exit(1 if FAILS else 0)
