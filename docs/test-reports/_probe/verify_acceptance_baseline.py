"""只读探针：为「业务级验收标准」文档取证（t4 acceptance）。

只做三件事，全部只读：
  1) 打印环境与真实库 SHA256（用于验收文档的「基线库零改动」判据）；
  2) 在 app.db 的临时副本上，逐轮 `seed_fixtures()` 打印关键业务表的行数
     ——得到「端到端验收必须自建夹具」的精确清单（哪些表 seed 之后就非 0）；
  3) 打印 5 个配置开关的读取点计数（区分「真接线 / 假开关 / 功能未启用」）。

不写任何生产代码、不写真实 app.db、不发请求。
用法（仓库根目录）：
    & 'F:\\Miniconda\\envs\\wage\\python.exe' -B docs/test-reports/_probe/verify_acceptance_baseline.py
"""
import hashlib
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT))

REAL_DB = ROOT / 'app.db'

# 验收链路上「行列数 = 0 就必须自建夹具」的关键业务表
CRITICAL_TABLES = [
    # 销售 / 生产计划
    'sales_orders', 'sales_order_items', 'production_orders', 'production_batches',
    'production_batch_items', 'task_assignment', 'production_record',
    'production_record_materials', 'material_allocations',
    # 质量
    'inspection_templates', 'inspection_tasks', 'inspection_records',
    'nonconformity_records',
    # 库存 / 仓库单据
    'raw_material', 'finished_product', 'consumables', 'material_requisitions',
    'material_requisition_items', 'material_returns', 'inventory_counts',
    # 采购 / 来料检（基线全空）
    'suppliers', 'purchase_requisitions', 'purchase_orders', 'purchase_order_items',
    'goods_receipts', 'goods_receipt_items', 'purchase_settlements',
    # 发货（基线全空）
    'shipments', 'shipment_items', 'shipment_receipts',
    # 设备 / 炉次 / 工件（基线全空）
    'equipment', 'work_centers', 'heat_lots', 'heat_lot_slots', 'workpieces',
    'workpiece_events', 'task_workpieces',
    # 配置 / 审计
    'system_configs', 'audit_log',
]


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest().upper()


def print_env():
    print('== 1. 环境与真实库基线 ==')
    print(f'  ROOT = {ROOT}')
    print(f'  real app.db exists = {REAL_DB.is_file()}')
    if REAL_DB.is_file():
        print(f'  real app.db SHA256 = {sha256_of(REAL_DB)}')
        print(f'  期望值             = F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065')


def count_tables(app):
    from app import db
    from sqlalchemy import text
    out = {}
    with app.app_context():
        for name in CRITICAL_TABLES:
            try:
                out[name] = db.session.execute(
                    text(f'SELECT COUNT(*) FROM "{name}"')).scalar()
            except Exception as e:  # 表不存在时照实打印
                out[name] = f'ERR:{e.__class__.__name__}'
    return out


def print_fixture_matrix():
    print('\n== 2. 夹具矩阵：seed_fixtures() 前后逐表行数（副本库，只读统计）==')
    os_environ_backup = None
    try:
        import _test_bootstrap as tb
        app, copy_path = tb.make_app()
        print(f'  副本路径 = {copy_path}')
        before = count_tables(app)
        made = tb.seed_fixtures(app)
        after = count_tables(app)
        print(f'  seed_fixtures 新建/复用对象 = {sorted(made.keys())}')
        print(f'  {"表名":<32} {"baseline":>10} {"after_seed":>11}  判定')
        for name in CRITICAL_TABLES:
            b, a = before[name], after[name]
            if b == 0 and a == 0:
                verdict = '★ 缺失：端到端必须自建夹具'
            elif b == 0 and isinstance(a, int) and a > 0:
                verdict = 'seed_fixtures 已覆盖'
            elif b > 0:
                verdict = 'baseline 已有数据（仍须造场景数据）'
            else:
                verdict = '?'
            print(f'  {name:<32} {str(b):>10} {str(a):>11}  {verdict}')
    finally:
        if os_environ_backup is not None:
            import os
            os.environ.update(os_environ_backup)


def print_config_readers():
    print('\n== 3. 配置开关读取点（区分 真接线 / 假开关 / 功能未启用）==')
    files = [p for p in (ROOT / 'app').rglob('*.py')]
    for key in ('purchase.full_workflow_enabled', 'purchase.settlement_enabled',
                'purchase.incoming_inspection_required',
                'quality.concession_approver_roles', 'quality.rework_counts_piecework'):
        hits = []
        for p in files:
            txt = p.read_text(encoding='utf-8', errors='replace')
            for m in re.finditer(re.escape(key), txt):
                line = txt[:m.start()].count('\n') + 1
                hits.append(f'{p.relative_to(ROOT).as_posix()}:{line}')
        print(f'  {key:<40} 命中 {len(hits):>2} 处 -> {hits if hits else "零读取点（假开关）"}')


def main():
    print_env()
    print_fixture_matrix()
    print_config_readers()
    print('\n== 4. 复核 ==')
    if REAL_DB.is_file():
        print(f'  真实库 SHA256（收尾）= {sha256_of(REAL_DB)}')
    print('  （本探针全程只读：不写生产代码、不写真实库、不发 HTTP 请求）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
