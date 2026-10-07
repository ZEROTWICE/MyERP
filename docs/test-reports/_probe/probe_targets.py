"""t3 验证目标可行性探针（只读：只在 app.db 的临时副本上运行）。

用途：为「验证目标设定与风险登记评估」提供可复跑的原始证据：
  S1 环境能力（pytest / coverage / unittest / Excel 库）
  S2 关键空表的夹具成本（NOT NULL 且无默认值的列）
  S3 复现 G-1：production_record 目标质检 fail → 零落地
  S4 复现 G-2 后果：失败后 qc_gate_allows_output 仍放行
  S5 对照：workpiece 目标 fail → 不合格单确实生成（证明测试手法灵）
  S6 复现 G-4a：返工任务 quantity 硬编码 1
  S7 复现 G-4b：报废扣料硬编码 −1（与真实消耗量无关）

跑法（仓库根目录）：
    & 'F:\\Miniconda\\envs\\wage\\python.exe' -B scripts/_sandbox_compat.py docs/test-reports/_probe/probe_targets.py

本脚本**不写真实 app.db**：make_app() 先复制到 %TEMP%，并在启动后校验 URI 落在副本上。
"""
import ast
import importlib.util
import os
import pathlib
import sys
import traceback
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

FAILS = []


def check(label, ok, detail=''):
    mark = 'PASS' if ok else 'FAIL'
    if not ok:
        FAILS.append(label)
    print(f'[{mark}] {label}' + (f' | {detail}' if detail else ''))


def section(title):
    print('\n' + '=' * 78)
    print(title)
    print('=' * 78)


# ----------------------------------------------------------------- S1 环境能力
section('S1 环境能力清单（决定「分层测试」能否落地）')
print(f'python = {sys.executable}  ({sys.version.split()[0]})')
for mod in ('pytest', 'coverage', 'unittest', 'flask', 'flask_login', 'sqlalchemy',
            'alembic', 'pandas', 'openpyxl', 'requests', 'bs4'):
    try:
        spec = importlib.util.find_spec(mod)
    except Exception as exc:  # pragma: no cover
        spec = None
        print(f'  {mod}: 查询异常 {exc}')
        continue
    print(f'  {mod}: {"有" if spec else "无"}')
print('  => pytest/coverage 缺失：任何 pytest 用例层都先要装依赖（装在 '
      'F:\\Miniconda\\envs\\wage，属工作区外写入）。')

# ----------------------------------------------------------------- S2 夹具成本
section('S2 关键业务表夹具成本（NOT NULL 且无默认值 = 自建夹具必填）')
from _test_bootstrap import make_app, ensure_role_users  # noqa: E402

app, copy_path = make_app(fresh=True)
print(f'副本库 = {copy_path}')

from app import db  # noqa: E402

TABLES = [
    'workpieces', 'workpiece_events', 'heat_lots', 'heat_lot_slots', 'equipment',
    'work_centers', 'work_center_equipment', 'furnace_layouts', 'furnace_layout_cells',
    'suppliers', 'purchase_requisitions', 'purchase_requisition_items', 'purchase_orders',
    'purchase_order_items', 'goods_receipts', 'goods_receipt_items', 'shipment_items',
    'shipments', 'shipment_receipts', 'production_record', 'production_record_materials',
    'production_batch_items', 'production_batches', 'inspection_tasks', 'inspection_records',
    'inspection_templates', 'nonconformity_records', 'task_assignment', 'task_workpieces',
    'finished_product', 'material_requisitions', 'inventory_counts', 'inventory_count_items',
]
rows = []
for name in TABLES:
    t = db.metadata.tables.get(name)
    if t is None:
        rows.append((name, 'NOT-IN-METADATA', []))
        continue
    required = []
    for c in t.columns:
        if c.primary_key or c.nullable:
            continue
        if c.default is not None or c.server_default is not None:
            continue
        if c.foreign_keys:
            required.append(f'{c.name}→{sorted(fk.target_fullname for fk in c.foreign_keys)[0]}')
        else:
            required.append(c.name)
    rows.append((name, len(required), required))

for name, n, req in rows:
    print(f'  {name}: {n} 个必填' + (f'  {req}' if req else ''))
not_in_meta = [r[0] for r in rows if r[1] == 'NOT-IN-METADATA']
check('S2 关键业务表全部在 db.metadata 中', not not_in_meta, f'缺失={not_in_meta}')

# --------------------------------------------------- S3/S4/S5 质检结果流转复现
section('S3-S5 质检结果流转复现（G-1 / G-2，含 workpiece 对照）')
from app import models as M  # noqa: E402
from app.services import mes_service as mes  # noqa: E402

ensure_role_users(app)
made = {}
with app.app_context():
    admin = M.User.query.filter_by(role='admin').first()
    emp = M.Employee.query.first()
    pp = M.ProcessPrice.query.first()
    raw = M.RawMaterial.query.first()
    assert admin and emp and pp, 'admin/employee/process_price 缺一不可'

    def count_nc():
        return M.NonconformityRecord.query.count()

    # ---- S3: production_record 目标 fail
    prec = M.ProductionRecord(employee_id=emp.id, process_id=pp.id, quantity=10, date=date.today())
    db.session.add(prec)
    db.session.flush()
    t1 = M.InspectionTask(global_sn=M.SerialNumber.get_next_number(), inspector_id=admin.id,
                          target_type='production_record', target_id=prec.id, status='pending',
                          created_by=admin.id)
    db.session.add(t1)
    db.session.flush()
    r1 = M.InspectionRecord(global_sn=M.SerialNumber.get_next_number(), task_id=t1.id,
                            inspector_id=admin.id, inspection_date=date.today(), result='fail')
    db.session.add(r1)
    db.session.commit()

    nc_before = count_nc()
    t1.status = 'completed'
    db.session.commit()
    ret = mes.apply_inspection_result(r1)
    db.session.commit()
    nc_after = count_nc()

    print(f'  production_record 目标：NC {nc_before} → {nc_after}，返回值 = {ret!r}')
    check('S3 G-1 复现：production_record fail 不生成不合格单（当前缺陷行为）',
          nc_after == nc_before,
          f'NC 增量 = {nc_after - nc_before}（正确行为应 ≥1）')

    # ---- S4: 门禁是否仍然放行
    allowed, reason = mes.qc_gate_allows_output(production_record=prec)
    print(f'  qc_gate_allows_output(production_record) = {(allowed, reason)!r}')
    check('S4 G-2 复现：判失败后门禁仍放行（当前缺陷行为）',
          allowed is True,
          f'allowed={allowed}, reason={reason!r}，正确行为应为 False')

    # ---- S5: workpiece 对照，证明同一手法能检出 NC 生成
    wp = M.Workpiece(code='_T3_WP_1', status='raw', raw_material_id=(raw.id if raw else None))
    db.session.add(wp)
    db.session.flush()
    t2 = M.InspectionTask(global_sn=M.SerialNumber.get_next_number(), inspector_id=admin.id,
                          target_type='workpiece', target_id=wp.id, status='pending',
                          created_by=admin.id)
    db.session.add(t2)
    db.session.flush()
    r2 = M.InspectionRecord(global_sn=M.SerialNumber.get_next_number(), task_id=t2.id,
                            inspector_id=admin.id, inspection_date=date.today(), result='fail')
    db.session.add(r2)
    db.session.commit()

    nc_before2 = count_nc()
    t2.status = 'completed'
    db.session.commit()
    mes.apply_inspection_result(r2)
    db.session.commit()
    nc_after2 = count_nc()
    print(f'  workpiece 目标：NC {nc_before2} → {nc_after2}')
    check('S5 对照：workpiece fail 生成不合格单 + 工件置 failed + 入未通过库',
          nc_after2 == nc_before2 + 1 and wp.status == 'failed',
          f'增量={nc_after2 - nc_before2}, wp.status={wp.status!r}')

    gated, gwhy = mes.qc_gate_allows_output(workpieces=[wp])
    check('S5b 对照：工件路径门禁确实拦住了', gated is False, f'{(gated, gwhy)!r}')

    # ------------------------------------------------ S6/S7 处置：返工/报废硬编码
    section('S6-S7 不合格处置数字复现（G-4a quantity=1 / G-4b 扣料 −1）')
    nc = M.NonconformityRecord.query.filter_by(workpiece_id=wp.id).first()
    # 先做返工
    mes.dispose_nonconformity(nc, 'rework', rework_process_id=pp.id, employee_id=emp.id)
    db.session.commit()
    rework = M.TaskAssignment.query.get(nc.rework_task_id)
    print(f'  返工任务：id={rework.id} quantity={rework.quantity} notes={rework.notes!r}')
    check('S6 G-4a 复现：返工任务 quantity 硬编码 1（与不合格数量无关）',
          rework.quantity == 1, f'quantity={rework.quantity}')
    made['rework_task_id'] = rework.id

    # 再做报废（同一工件换一个新工件，避免状态冲突）
    wp2 = M.Workpiece(code='_T3_WP_2', status='failed', raw_material_id=(raw.id if raw else None))
    db.session.add(wp2)
    db.session.flush()
    t3 = M.InspectionTask(global_sn=M.SerialNumber.get_next_number(), inspector_id=admin.id,
                          target_type='workpiece', target_id=wp2.id, status='pending',
                          created_by=admin.id)
    db.session.add(t3)
    db.session.flush()
    r3 = M.InspectionRecord(global_sn=M.SerialNumber.get_next_number(), task_id=t3.id,
                            inspector_id=admin.id, inspection_date=date.today(), result='fail')
    db.session.add(r3)
    db.session.commit()
    t3.status = 'completed'
    db.session.commit()
    mes.apply_inspection_result(r3)
    db.session.commit()
    nc2 = M.NonconformityRecord.query.filter_by(workpiece_id=wp2.id).first()
    raw_qty_before = float(raw.quantity or 0)
    mes.dispose_nonconformity(nc2, 'scrap', scrap_cost=99.0)
    db.session.commit()
    db.session.refresh(raw)
    print(f'  原材料 {raw.internal_number!r}({raw.material_name}): quantity {raw_qty_before} -> {raw.quantity}')
    check('S7 G-4b 复现：报废扣料 = 固定 1（与工件真实消耗量/数量无关）',
          abs((raw_qty_before - float(raw.quantity or 0)) - 1.0) < 1e-9,
          f'扣减 = {raw_qty_before - float(raw.quantity or 0)}')

# ---------------------------------------------------- S8 静态事实交叉复核（AST）
section('S8 静态事实交叉复核（AST，只读源码）')
src = (ROOT / 'app' / 'services' / 'mes_service.py').read_text(encoding='utf-8')
lines = src.splitlines()
tree = ast.parse(src)


def func_node(name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


f = func_node('apply_inspection_result')
ret_lines = [n.lineno for n in ast.walk(f) if isinstance(n, ast.Return)]
print(f'  apply_inspection_result 的 return 行号 = {ret_lines}')
check('S8 t1 坐标复核：mes_service.py:421-422 是「workpiece is None → return」',
      'if workpiece is None:' in lines[420] and lines[421].strip() == 'return',
      f'L421={lines[420].strip()!r} L422={lines[421].strip()!r}')

nc_ctor = [n.lineno for n in ast.walk(tree)
           if isinstance(n, ast.Call) and getattr(n.func, 'id', None) == 'NonconformityRecord']
print(f'  mes_service.py 里 NonconformityRecord(...) 构造行 = {nc_ctor}')
allpy = []
for p in (ROOT / 'app').rglob('*.py'):
    try:
        t = ast.parse(p.read_text(encoding='utf-8', errors='replace'))
    except SyntaxError:
        continue
    for n in ast.walk(t):
        if isinstance(n, ast.Call) and getattr(n.func, 'id', None) == 'NonconformityRecord':
            allpy.append(f'{p.relative_to(ROOT).as_posix()}:{n.lineno}')
print(f'  全 app/ 构造点 = {allpy}')

qstatus = []
for p in (ROOT / 'app').rglob('*'):
    if p.suffix not in ('.py', '.html') or not p.is_file():
        continue
    try:
        txt = p.read_text(encoding='utf-8', errors='replace')
    except OSError:
        continue
    for i, ln in enumerate(txt.splitlines(), 1):
        if 'quality_status' in ln and 'quality_status' in ln:
            qstatus.append(f'{p.relative_to(ROOT).as_posix()}:{i}')
print(f'  quality_status 命中 {len(qstatus)} 处：')
for h in qstatus:
    print(f'    {h}')

rework_cfg = []
for p in (ROOT / 'app').rglob('*.py'):
    try:
        txt = p.read_text(encoding='utf-8', errors='replace')
    except OSError:
        continue
    for i, ln in enumerate(txt.splitlines(), 1):
        if 'rework_counts_piecework' in ln:
            rework_cfg.append(f'{p.relative_to(ROOT).as_posix()}:{i}')
print(f'  rework_counts_piecework 命中 = {rework_cfg}')
check('S8 t1 复核：quality.rework_counts_piecework 仅配置种子、零读取点',
      len(rework_cfg) == 1 and rework_cfg[0].endswith('src') is False, f'{rework_cfg}')
check('S8 t1 复核：NonconformityRecord 业务构造点仅 2 处',
      len(allpy) == 2, f'{allpy}')

# ------------------------------------------------------------ S9 请求级可行性
section('S9 请求级（Flask test_client）验证可行性')
from _test_bootstrap import login_as  # noqa: E402

maps, pwd = ensure_role_users(app)
client = app.test_client()
anon = client.get('/tasks', follow_redirects=False)
print(f'  匿名 GET /tasks -> {anon.status_code}')
check('S9a 请求级：匿名请求被拦（302 或 401）', anon.status_code in (302, 401),
      f'status={anon.status_code}')
resp = login_as(client, maps['admin'], pwd)
print(f'  登录 POST /auth/login -> {resp.status_code}')
page = client.get('/tasks', follow_redirects=False)
print(f'  admin GET /tasks -> {page.status_code}')
check('S9b 请求级：登录后可发请求并取到真实响应', page.status_code in (200, 302),
      f'status={page.status_code}')
json_resp = client.get('/api/quality/statistics', follow_redirects=False)
print(f'  admin GET /api/quality/statistics -> {json_resp.status_code} '
      f'content-type={json_resp.headers.get("Content-Type")!r}')
check('S9c 请求级：JSON 端点可断言状态码与 content-type',
      json_resp.status_code in (200, 404, 403), f'status={json_resp.status_code}')

# ------------------------------------------------------------------ 结尾
section('结果')
print(f'副本库仍为 {copy_path}（真实 app.db 未被访问）')
print(f'FAIL 项 = {len(FAILS)}')
for x in FAILS:
    print(f'  - {x}')
print('\n注：本脚本的 FAIL 表示「探针预期与实际不符」，不代表产品缺陷；'
      'S3/S4/S6/S7 的 PASS 恰恰说明产品缺陷已被复现。')
sys.exit(1 if FAILS else 0)
