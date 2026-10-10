"""副本库夹具工厂（供 t4 / t5 / 本任务阴性矩阵复用）。

关键设计（与 `08` §6 第 1 步 / A-4 / A-10 / GAP-02 / GAP-39 对齐）：

1. **每个 run 一份自己的带时间戳副本**：``app_nv_<RUN_ID>.db``，落在 ``test-reports-2026-10/.tmp/<run_id>/``（本沙箱禁止 0o700 目录写入，且不可删 ⇒ 一律 ``os.makedirs``，绝不裸 ``tempfile.mkdtemp()``）。
2. **两道隔离闸**：
   * ``scripts/_test_bootstrap.make_app()`` 自带「URI 必须落在副本上」断言（:41）；
   * 本模块的 ``assert_isolated()`` 再独立复核一次（URI 不得指向真实库），并把真实库当作**故意负例**验收。
3. **夹具族按域分函数、可重复调用（幂等）**：采购 / 发货（**注入 ``stock_kind='fg'``**）/
   料账（**≥5 行、``quantity ≥ 5``**，A-10）/ 质检门禁（A-3）/ 工资差分。
4. **零副作用**：新增行一律打 ``_hv`` 前缀，``manifest()`` 记录逐表新增主键，便于第三人复核；
   真实库 ``app.db`` 的 SHA256 在每次建副本前后自动复核（``_env.run_child`` 亦复核）。
"""
from datetime import date, datetime, timedelta
import os

from _env import (REAL_DB, assert_real_db_untouched, db_copy, tmp_dir,
                  sha256_file, RUN_ID, REAL_DB_SHA256_EXPECTED, TMP_ROOT,
                  save_evidence, real_db_status, evidence_dir, _append_journal)

_APP = None
_COPY_PATH = None
_MANIFEST = {}


# ------------------------------------------------------------------ 隔离与启动
def _patch_mkdtemp():
    """把 ``tempfile.mkdtemp`` 指向本 run 的隔离目录（同 `_sandbox_compat` 的放宽，但不依赖它）。"""
    import tempfile
    base = tmp_dir('mkdtemp')

    def _relaxed(suffix=None, prefix=None, dir=None):
        name = (prefix or '') + _run_tag() + '_' + next(tempfile._get_candidate_names()) + (suffix or '')
        path = str(base / name) if hasattr(base, '__fspath__') else __import__('os').path.join(base, name)
        __import__('os').mkdir(path, 0o777)
        return path

    tempfile.mkdtemp = _relaxed
    return base


# ----------------------------------------------------- B14-R3：引导前字节副本指纹
#: 最近一次 ``make_isolated_app`` 截获的「真实库 -> 副本」字节复制指纹（**引导前**时点）。
PRE_BOOTSTRAP_COPY = {}
#: 全部截获记录（同一进程多次调用按序累积；供复核「哪一次复制被记了」）。
_COPY_WATCH_HISTORY = []


def _watch_real_db_copy():
    """包住 ``shutil.copy2``：只截获「源 == 真实库」的那次复制，在**复制刚完成**时取副本指纹。

    为什么必须钉在这一时刻（B14-R3）：``_test_bootstrap.make_app(fresh=True)`` 的序列是
    ``shutil.copy2(REAL_DB, copy)`` → ``create_app()``；后者经
    ``app/__init__.py:247 _seed_system_configs()`` → ``InspectionTemplate.seed_defaults()``（B14-08）
    向副本下发默认质检模板 ⇒ **引导后**的副本指纹必然偏离真实库钉死值。
    「副本逐字节等于真实库」这一前提**只在引导前成立** —— 判据必须钉在这一时点。
    """
    import shutil
    orig = shutil.copy2
    if getattr(orig, '_b14r3_watched', False):
        return orig

    def watched(src, dst, *args, **kwargs):
        result = orig(src, dst, *args, **kwargs)
        try:
            is_real_src = os.path.samefile(src, REAL_DB)
        except OSError:
            is_real_src = False
        if is_real_src and os.path.exists(dst):
            _COPY_WATCH_HISTORY.append({
                'src': str(src), 'dst': str(dst), 'sha256': sha256_file(dst),
                'bytes': os.path.getsize(dst),
                'captured_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'phase': 'pre_app_factory（字节复制完成、create_app 之前）',
            })
        return result

    watched._b14r3_watched = True
    shutil.copy2 = watched
    return watched


def _record_pre_bootstrap_copy(copy_path, since=0):
    """从本次调用截获的记录里选出 ``PRE_BOOTSTRAP_COPY``（优先与返回副本同文件的那条）。"""
    picked = None
    for row in _COPY_WATCH_HISTORY[since:]:
        try:
            if os.path.samefile(row['dst'], copy_path):
                picked = row
        except OSError:
            picked = row
    if picked is None and len(_COPY_WATCH_HISTORY) > since:
        picked = _COPY_WATCH_HISTORY[-1]
    PRE_BOOTSTRAP_COPY.clear()
    if picked:
        PRE_BOOTSTRAP_COPY.update(picked)
    return PRE_BOOTSTRAP_COPY


def pre_bootstrap_copy():
    """引导前的字节副本指纹（B14-R3）。未截获时给带 ``error`` 的占位 —— **绝不伪造读数**。"""
    if not PRE_BOOTSTRAP_COPY:
        return {'error': '未截获「真实库 -> 副本」的 shutil.copy2（未走 make_isolated_app？）'}
    return dict(PRE_BOOTSTRAP_COPY)


def _attach_pre_bootstrap_evidence():
    """把引导前指纹并入 ``LAST_ISOLATION_EVIDENCE``（隔离自证的第二时点，供产物复核）。"""
    ev = globals().get('LAST_ISOLATION_EVIDENCE')
    if isinstance(ev, dict):
        ev['pre_bootstrap_copy'] = pre_bootstrap_copy()
    return ev


def make_isolated_app(tag='nv'):
    """返回 ``(app, copy_path)``，app 的 ``DATABASE_URL`` 一定指向本 run 的副本。

    B14-R3：本函数同时记下**引导前**的字节副本指纹（``pre_bootstrap_copy()``）——
    ``_test_bootstrap.make_app(fresh=True)`` 先 ``shutil.copy2`` 再 ``create_app()``，
    而后者会下发默认质检模板（B14-08）⇒ 引导后的副本**不再**逐字节等于真实库。
    """
    global _APP, _COPY_PATH
    assert_real_db_untouched('before make_isolated_app')
    _patch_mkdtemp()
    _watch_real_db_copy()
    seen = len(_COPY_WATCH_HISTORY)
    import _test_bootstrap
    app, path = _test_bootstrap.make_app(fresh=True)
    _APP, _COPY_PATH = app, path
    _record_pre_bootstrap_copy(path, since=seen)
    assert_isolated(app); _open_ledger(app, tag)   # C-10：台账基线（逐表 COUNT/MAX(id)）+ 带 RUN_ID 的同 inode 副本别名
    _attach_pre_bootstrap_evidence()
    return app, path


def seed_all(app, password='test_pw_123'):
    """复刻既有脚手架的前置：``ensure_role_users`` + ``seed_fixtures``（幂等，可反复调用）。

    这一步是 ``smoke_test`` / ``permission_matrix`` / ``functional_test`` 的共同前置，少了它带参 GET 会有 10 条因「模型无数据」被跳过（实测：138 条 vs 148 条）。
    """
    import _test_bootstrap
    users, pw = _test_bootstrap.ensure_role_users(app, password=password)
    seeded = _test_bootstrap.seed_fixtures(app)
    _note_seeded(app, users, seeded)      # C-10/F-4：脚手架直接建的行也进台账（此前零记账）
    return {'users': users, 'password': pw, 'seeded': seeded}


def assert_isolated(app):
    """独立隔离闸：应用的库 URI 必须指向副本，绝不指向真实库 ``app.db``。

    判据（路径级）：URI 的目标文件与真实库 ``os.path.samefile`` 成立 ⇒ 拒。
    补充记录（非拒绝条件）：目标文件指纹等于真实库钉死哈希 —— 合法副本本来就该**逐字节相同**
    （``_test_bootstrap`` 就是 ``shutil.copy2``），因此**指纹不能当拒绝条件**；
    指纹只用于「换目录后仍指向同一文件」的取证（见 ``_env.assert_isolated_fingerprint``）。
    """
    from _env import (REAL_DB_SHA256_EXPECTED, assert_isolated_fingerprint,
                      sha256_file)
    uri = (app.config.get('SQLALCHEMY_DATABASE_URI') or '')
    if not uri:
        raise AssertionError('隔离失败：SQLALCHEMY_DATABASE_URI 为空')
    if 'mode=ro' in uri:
        return uri  # 显式只读 URI 是授权通道
    db_path = (uri.split('sqlite:///', 1)[-1]).replace('/', os.sep)
    if os.path.exists(db_path) and os.path.exists(REAL_DB):
        try:
            if os.path.samefile(db_path, REAL_DB):
                raise AssertionError(f'隔离失败：URI 指向的文件就是真实库 -> {uri}')
        except OSError:
            pass
    _APP_ISOLATION_EVIDENCE = assert_isolated_fingerprint(uri, db_path)
    globals()['LAST_ISOLATION_EVIDENCE'] = _APP_ISOLATION_EVIDENCE
    return uri


def app():
    return _APP


def copy_path():
    return _COPY_PATH


# ------------------------------------------------------------------ 记录与查询
def _note(table, **row):
    _MANIFEST.setdefault(table, []).append(row)


def manifest():
    return _build_manifest()      # C-10/E-10.3：内存 dict -> **落盘产物**（evidence/harness/<RUN_ID>/fixtures_manifest.json）


def counts(app, tables=None):
    """读副本里的行数（口径：``SELECT COUNT(*)``）。"""
    from app import db
    tables = tables or ['production_record', 'production_batch_items', 'inspection_tasks',
                        'inspection_records', 'nonconformity_records', 'raw_material',
                        'material_allocations', 'finished_product', 'audit_log', 'workpieces',
                        'task_assignment']
    out = {}
    with app.app_context():
        for t in tables:
            out[t] = db.session.execute(db.text(f'SELECT COUNT(*) FROM {t}')).scalar()
    return out


# ------------------------------------------------------------------ 基础对象
def _base_objects(app):
    """取真实库里已有的基础对象（产品/工序/客户/原材料/管理员），找不到就造一个最小行。"""
    from app import db
    from app import models as M
    ctx = {}
    with app.app_context():
        ctx['admin'] = M.User.query.filter_by(username='admin').first() or M.User.query.first()
        ctx['product'] = M.Product.query.first()
        if ctx['product'] is None:
            ctx['product'] = M.Product(product_code='_hv_P1', product_name='_hv 测试产品',
                                       status='active', created_by=ctx['admin'].id if ctx['admin'] else 1)
            db.session.add(ctx['product'])
            db.session.flush()
            _note('products', id=ctx['product'].id)
        ctx['process'] = M.ProcessPrice.query.first()
        if ctx['process'] is None:
            ctx['process'] = M.ProcessPrice(process_code='_hv_C1', process_name='_hv 测试工序',
                                            price=10.0, version=1)
            db.session.add(ctx['process'])
            db.session.flush()
            _note('process_price', id=ctx['process'].id)
        ctx['employee'] = M.Employee.query.first()
        if ctx['employee'] is None:
            ctx['employee'] = M.Employee(employee_id='_hv_E1', name='_hv 测试员工',
                                         hire_date=date(2026, 1, 1))
            db.session.add(ctx['employee'])
            db.session.flush()
            _note('employee', id=ctx['employee'].id)
        ctx['raw_category'] = M.RawMaterialCategory.query.first()
        if ctx['raw_category'] is None:
            ctx['raw_category'] = M.RawMaterialCategory(name='_hv 品类', code='_hv_CAT1')
            db.session.add(ctx['raw_category'])
            db.session.flush()
            _note('raw_material_categories', id=ctx['raw_category'].id)
        ctx['customer'] = M.Customer.query.first()
        db.session.commit()
    return ctx


# ------------------------------------------------------------------ 料账夹具（A-10）
def seed_material_ledger(app, rows=5, qty=5.0):
    """料账夹具：**≥5 行 / ``quantity ≥ 5``**（A-10 强制前置）。

    真实库 ``raw_material`` 仅 1 行 ``quantity=1.0``，扣料 1.0→0.0 与「硬编码减 1」同解
    ⇒ 本夹具把每行放到 ``quantity=qty``（默认 5.0），并要求调用方按行扣不同数量。
    """
    from app import db
    from app import models as M
    made, _tag = [], _call_tag('raw_material')   # C-10/E-10.2：每次调用一个唯一后缀（含 RUN_ID + 序号）
    with app.app_context():
        cat = M.RawMaterialCategory.query.first()
        for i in range(rows):
            rm = M.RawMaterial(
                supplier=f'_hv 供应商{i + 1}', category_id=cat.id, melt_number=f'_hvMELT{i + 1}',
                supplier_number=f'_hvSUP{i + 1}', internal_number=f'_hvRAW{i + 1}' + _tag,
                quantity=qty, status='in_stock', is_archived=False,
            )
            db.session.add(rm)
            db.session.flush()
            made.append({'id': rm.id, 'internal_number': rm.internal_number, 'quantity': rm.quantity})
            _note('raw_material', id=rm.id, quantity=qty)
        db.session.commit()
    return made


def material_ledger_state(app, ids):
    """料账可查值：``RawMaterial.quantity`` 之和 + ``MaterialAllocation.consumed_quantity`` 之和。"""
    from app import db
    from app import models as M
    with app.app_context():
        rows = M.RawMaterial.query.filter(M.RawMaterial.id.in_(ids)).all()
        total = sum((r.quantity or 0) for r in rows)
        allocs = M.MaterialAllocation.query.all()
        consumed = sum((a.consumed_quantity or 0) for a in allocs)
        return {
            'raw_rows': len(rows),
            'raw_quantity_sum': round(total, 4),
            'raw_quantity_by_id': {r.id: r.quantity for r in rows},
            'allocation_rows': len(allocs),
            'consumed_quantity_sum': round(consumed, 4),
        }


def seed_allocation_rows(app, order_id, items):
    """造 ``MaterialAllocation`` 行（``write_consumed_allocation`` **不会凭空建行**，:839 注释）。"""
    from app import db
    from app import models as M
    made = []
    with app.app_context():
        for it in items:
            alloc = M.MaterialAllocation(
                production_order_id=order_id, material_type='raw', material_id=it['id'],
                required_quantity=it.get('required', 10.0), allocated_quantity=0.0,
                consumed_quantity=0.0, unit='件', status='pending',
            )
            db.session.add(alloc)
            db.session.flush()
            made.append({'id': alloc.id, 'material_id': it['id'],
                         'required_quantity': alloc.required_quantity})
            _note('material_allocations', id=alloc.id, material_id=it['id'])
        db.session.commit()
    return made


# ------------------------------------------------------------------ 发货夹具（A-4）
def seed_shipment(app, quantity=10, kind='fg'):
    """发货链前置：**必须显式注入 ``stock_kind='fg'``**（A-4）。

    真实库 ``finished_product`` 2 行 ``stock_kind`` 全为 NULL ⇒ ``/stock/fg``
    （``stock.py:20`` 的 ``filter_by(stock_kind=kind)``）与 ``shipment_candidate_stock``
    （``mes_service.py:1150`` 的 ``in_(SHIPPABLE_STOCK_KINDS)``）都取不到；「候选为空」
    是**夹具缺陷，不是产品缺陷**。
    """
    from app import db
    from app import models as M
    with app.app_context():
        p = M.Product.query.first()
        fp = M.FinishedProduct(
            product_number=f'_hvFP_{kind.upper()}', production_date=date.today(),
            drawing_number='_hv-DWG', model='_hv-MODEL', inspector='_hv',
            quantity=quantity, status='in_stock', stock_kind=kind,
            product_id=p.id if p else None, notes='_hv 发货链夹具（stock_kind 显式注入）',
        )
        db.session.add(fp)
        db.session.commit()
        _note('finished_product', id=fp.id, stock_kind=kind, quantity=quantity)
        return {'id': fp.id, 'product_number': fp.product_number,
                'stock_kind': fp.stock_kind, 'quantity': fp.quantity}


def shipment_candidates(app):
    """按产品口径复核发货候选：``finished_product WHERE stock_kind='fg' AND status='in_stock'``。"""
    from app import db
    from app import models as M
    from app.services.mes_service import SHIPPABLE_STOCK_KINDS
    with app.app_context():
        rows = (M.FinishedProduct.query
                .filter(M.FinishedProduct.stock_kind.in_(SHIPPABLE_STOCK_KINDS))
                .filter(M.FinishedProduct.status == 'in_stock').all())
        return {'shippable_kinds': list(SHIPPABLE_STOCK_KINDS),
                'candidates': [{'id': r.id, 'product_number': r.product_number,
                                'stock_kind': r.stock_kind, 'quantity': r.quantity} for r in rows]}


# ------------------------------------------------------------------ 质检门禁夹具（A-3）
def seed_qc_gate(app):
    """造门禁探针数据（全部在副本内新增，打 ``_hv`` 前缀）。

    三条独立的数据形态，用于把门禁的**互不相同的拒绝路径**区分开：

    * ``P1``：批次实例 ``quality_status='fail'`` —— ``mes_service.py:170-175`` 路径（按 ``product_code`` 报原因）；
    * ``P1b``：批次实例 ``quality_status='pending'`` —— ``mes_service.py:172-173`` 路径；
    * ``P6``：供 `apply_inspection_result` 使用的「质检前 pending」实例 + 生产记录 + 未闭环质检任务
      （用于验证 GAP-14「自动回写」是否发生）。
    * ``P2``：生产记录 + ``status='completed'`` 的质检任务 + 无不合格记录 —— **应放行**（阴性对照：
      证明「有质检任务」本身不触发拒绝，只有未完成 ``pending`` 的才触发）；
    * ``P3``：生产记录 + ``status='pending'`` 的质检任务 —— ``:184-191`` 路径；
    * ``P4``：生产记录 + 已闭环任务 + ``status='open'`` 的不合格记录 —— ``:192-197`` 路径；
    * ``WP_BLOCKED`` / ``WP_CLEAN``：工件阳性对照与被锁工件（``workpiece_blocked``）。
    """
    from app import db
    from app import models as M
    ctx = {}
    with app.app_context():
        admin = M.User.query.filter_by(username='admin').first() or M.User.query.first()
        emp = M.Employee.query.first()
        proc = M.ProcessPrice.query.first()
        prod = M.Product.query.first()
        today = date.today()

        def _mk_task(target_type, target_id, status='pending'):
            t = M.InspectionTask(
                global_sn=M.SerialNumber.get_next_number(),
                template_id=None, inspector_id=admin.id, target_type=target_type,
                target_id=target_id, status=status, created_by=admin.id,
            )
            db.session.add(t)
            db.session.flush()
            _note('inspection_tasks', id=t.id, target_type=target_type, target_id=target_id,
                  status=status)
            return t

        def _mk_record(tag, notes):
            rec = M.ProductionRecord(employee_id=emp.id, process_id=proc.id, quantity=1,
                                     date=today, notes=notes)
            db.session.add(rec)
            db.session.flush()
            _note('production_record', id=rec.id)
            return rec

        # --- P1) 批次实例：quality_status='fail'（报工路径的真实形态）
        batch = M.ProductionBatch.query.first()
        if batch is None:
            order = M.ProductionOrder(
                product_id=prod.id, planned_quantity=10, planned_start_date=today,
                planned_end_date=today + timedelta(days=30), created_by=admin.id)
            db.session.add(order)
            db.session.flush()
            batch = M.ProductionBatch(production_order_id=order.id, batch_quantity=10)
            db.session.add(batch)
            db.session.flush()
            _note('production_orders', id=order.id)
            _note('production_batches', id=batch.id)
        batch_item = M.ProductionBatchItem(
            batch_id=batch.id, item_sequence=9001, product_code='_hvBI_FAIL',
            status='in_progress', quality_status='fail')
        db.session.add(batch_item)
        db.session.flush()
        _note('production_batch_items', id=batch_item.id, quality_status='fail')
        ctx['batch_item'] = {'id': batch_item.id, 'product_code': batch_item.product_code,
                             'quality_status': batch_item.quality_status}

        # --- P1b) 批次实例：quality_status='pending'
        bi_pending = M.ProductionBatchItem(
            batch_id=batch.id, item_sequence=9002, product_code='_hvBI_PENDING',
            status='in_progress', quality_status='pending')
        db.session.add(bi_pending)
        db.session.flush()
        _note('production_batch_items', id=bi_pending.id, quality_status='pending')
        ctx['batch_item_pending'] = {'id': bi_pending.id,
                                     'product_code': bi_pending.product_code}

        # --- P6) 质检闭环探针：实例 pending + 生产记录 + 未闭环质检任务
        bi_auto = M.ProductionBatchItem(
            batch_id=batch.id, item_sequence=9003, product_code='_hvBI_AUTO',
            status='in_progress', quality_status='pending')
        db.session.add(bi_auto)
        db.session.flush()
        _note('production_batch_items', id=bi_auto.id, quality_status='pending', role='auto')
        rec_auto = M.ProductionRecord(
            employee_id=emp.id, process_id=proc.id, quantity=1, date=today,
            notes=f'_hv 自动回写探针 {{"batch_item_id": {bi_auto.id}}}')
        db.session.add(rec_auto)
        db.session.flush()
        _note('production_record', id=rec_auto.id, batch_item_id=bi_auto.id)
        task_auto = _mk_task('production_record', rec_auto.id, status='in_progress')
        ctx['p6_auto_writeback'] = {'batch_item_id': bi_auto.id,
                                    'record_id': rec_auto.id, 'task_id': task_auto.id,
                                    'quality_status_before': bi_auto.quality_status,
                                    'nc_before': M.NonconformityRecord.query.filter_by(
                                        record_id=None).count()}

        # --- P2) 生产记录 + 已闭环质检任务（应放行）
        rec_closed = _mk_record('closed', '_hv 门禁 P2：已闭环，应放行')
        task_closed = _mk_task('production_record', rec_closed.id, status='completed')
        ctx['p2_closed'] = {'record_id': rec_closed.id, 'task_id': task_closed.id,
                            'expect_reject': False}

        # --- P3) 生产记录 + 未完成质检任务（应拒，:184-191）
        rec_pending = _mk_record('pending', '_hv 门禁 P3：未完成质检任务，应拒')
        task_pending = _mk_task('production_record', rec_pending.id, status='pending')
        ctx['p3_pending_task'] = {'record_id': rec_pending.id, 'task_id': task_pending.id,
                                  'expect_reject': True}

        # --- P4/P5) 同一条生产记录上的「未闭环」与「已闭环」不合格（构造行：
        #     `NonconformityRecord.record_id` 直接命中该生产记录 id）。
        #     P4 的质检任务先造 pending（:184-191 会先行拒绝），`qc_gate_states` 随后把它
        #     改成 completed 并 rollback，以隔离出 :192-197。
        rec_nc = _mk_record('nc', '_hv 门禁 P4/P5：同一条记录上的开/闭不合格')
        task_nc = _mk_task('production_record', rec_nc.id, status='pending')
        nc_open = M.NonconformityRecord(
            record_id=rec_nc.id, type='rework', handler_id=admin.id, handling_date=today,
            handling_result='_hv 待处置（构造行：record_id 命中该生产记录 id）', status='open',
            scrap_cost=0)
        nc_done = M.NonconformityRecord(
            record_id=rec_nc.id, type='accept', handler_id=admin.id, handling_date=today,
            handling_result='_hv 让步接收（已闭环，阴性对照）', status='approved', scrap_cost=0)
        db.session.add_all([nc_open, nc_done])
        db.session.flush()
        _note('nonconformity_records', id=nc_open.id, status='open',
              bound='record_id_hits_production_record', note='构造性探针')
        _note('nonconformity_records', id=nc_done.id, status='approved',
              bound='record_id_hits_production_record', note='构造性探针（阴性对照）')
        ctx['p4_open_nc'] = {'record_id': rec_nc.id, 'task_id': task_nc.id,
                             'nc_id': nc_open.id, 'expect_reject': True}
        ctx['p5_closed_nc'] = {'record_id': rec_nc.id, 'task_id': task_nc.id,
                               'nc_id': nc_done.id, 'expect_reject': False,
                               'note': '与 P4 同一条记录；:192-197 只匹配 open/pending_approval'}
        # 为了分离「未闭环」与「已闭环」两条判定，P5 另用一条**只有 approved NC** 的记录
        rec_ok2 = _mk_record('nc_closed_only', '_hv 门禁 P5b：只有已闭环不合格，应放行')
        task_ok2 = _mk_task('production_record', rec_ok2.id, status='completed')
        nc_ok2 = M.NonconformityRecord(
            record_id=rec_ok2.id, type='accept', handler_id=admin.id, handling_date=today,
            handling_result='_hv 让步接收', status='approved', scrap_cost=0)
        db.session.add(nc_ok2)
        db.session.flush()
        _note('nonconformity_records', id=nc_ok2.id, status='approved',
              bound='record_id_hits_production_record')
        ctx['p5b_closed_only'] = {'record_id': rec_ok2.id, 'task_id': task_ok2.id,
                                  'nc_id': nc_ok2.id, 'expect_reject': False}

        # --- 工件两条：一条被未闭环不合格锁住，一条完全干净
        wp_blocked = M.Workpiece(code='_hvWP_BLOCKED', status='machining', product_id=prod.id)
        wp_clean = M.Workpiece(code='_hvWP_CLEAN', status='machining', product_id=prod.id)
        db.session.add_all([wp_blocked, wp_clean])
        db.session.flush()
        ir_wp = M.InspectionRecord(
            global_sn=M.SerialNumber.get_next_number(),
            task_id=task_closed.id, template_id=None, inspector_id=admin.id,
            inspection_date=today, result='fail', notes='_hv 工件不合格记录')
        db.session.add(ir_wp)
        db.session.flush()
        _note('inspection_records', id=ir_wp.id, result='fail', bound='workpiece')
        nc_wp = M.NonconformityRecord(
            record_id=ir_wp.id, type='rework', handler_id=admin.id, handling_date=today,
            handling_result='_hv 待处置', status='open', workpiece_id=wp_blocked.id,
            target_type='workpiece', target_id=wp_blocked.id, scrap_cost=0)
        db.session.add(nc_wp)
        db.session.flush()
        _note('nonconformity_records', id=nc_wp.id, status='open', bound='workpiece')
        _note('workpieces', id=wp_blocked.id, status='machining', open_nc=nc_wp.id)
        _note('workpieces', id=wp_clean.id, status='machining')
        ctx['wp_blocked'] = {'id': wp_blocked.id, 'code': wp_blocked.code,
                             'open_nc_id': nc_wp.id, 'expect_reject': True}
        ctx['wp_clean'] = {'id': wp_clean.id, 'code': wp_clean.code, 'expect_reject': False}
        db.session.commit()
    return ctx


def qc_gate_states(app, ctx):
    """跑多种调用形态，返回**可 diff** 的判定（除最后一次 flush 外只读）。

    形态设计的目的（A-3 的「缺少触发拒绝的数据」）：

    * 形态 A：``batch_item=实例(quality_status='fail')`` + ``workpieces=[]`` ——
      与 ``mes_service.py:326`` 的真实调用点等价（**不传** ``production_record``）；
    * 形态 A2：``quality_status='pending'`` 的实例 —— ``:172-173``；
    * 形态 C：``record_ids`` 命中 ``status='pending'`` 的质检任务 —— ``:184-191``；
    * 形态 D：同一 record 的 task 改为 ``completed`` 后 —— ``:192-197``（未闭环不合格）；
    * 形态 E/F：干净工件 / 被锁工件（工件侧阳性对照）；
    * 形态 H：把**同一** ``production_record`` 实参喂给两个 ``quality_status`` 不同的实例 ——
      证明门禁会随实参变化（非写死结论）。
    """
    from app import db
    from app import models as M
    from app.services import mes_service
    with app.app_context():
        bi = M.ProductionBatchItem.query.get(ctx['batch_item']['id'])
        bi_pending = M.ProductionBatchItem.query.get(ctx['batch_item_pending']['id'])
        rec2 = M.ProductionRecord.query.get(ctx['p2_closed']['record_id'])
        rec3 = M.ProductionRecord.query.get(ctx['p3_pending_task']['record_id'])
        rec4 = M.ProductionRecord.query.get(ctx['p4_open_nc']['record_id'])
        rec5 = M.ProductionRecord.query.get(ctx['p5b_closed_only']['record_id'])
        wp_b = M.Workpiece.query.get(ctx['wp_blocked']['id'])
        wp_c = M.Workpiece.query.get(ctx['wp_clean']['id'])
        gate = mes_service.qc_gate_allows_output
        states = {
            'A_batch_item_only__no_production_record': gate(batch_item=bi, workpieces=[]),
            'A2_batch_item_pending': gate(batch_item=bi_pending, workpieces=[]),
            'B_explicit_closed_record': gate(batch_item=bi, workpieces=[], production_record=rec2),
            'C_explicit_pending_task_record': gate(production_record=rec3),
            'D2_explicit_closed_nc_record': gate(production_record=rec5),
            'E_clean_workpiece': gate(workpieces=[wp_c]),
            'F_blocked_workpiece': gate(workpieces=[wp_b]),
            'G_nothing_at_all': gate(),
            'H_same_record_two_instances': [
                list(gate(batch_item=bi, workpieces=[], production_record=rec2)),
                list(gate(batch_item=bi_pending, workpieces=[], production_record=rec2)),
            ],
        }
        # 分离 :192-197：把 P4 的质检任务从 pending 改成 completed（唯一的一次写操作）
        task_nc = M.InspectionTask.query.get(ctx['p4_open_nc']['task_id'])
        task_nc.status = 'completed'
        db.session.flush()
        states['D_after_task_completed__open_nc_path'] = gate(production_record=rec4)
        states['C_before_task_completed__pending_path'] = gate(production_record=rec4)
        db.session.rollback()
        extra = {
            'workpiece_blocked_flag_blocked': mes_service.workpiece_blocked(wp_b),
            'workpiece_blocked_flag_clean': mes_service.workpiece_blocked(wp_c),
            'batch_item_derived_records': [
                r.id for r in mes_service.batch_item_production_records(bi)],
            'p4_note': 'C_* 与 D_* 用的是**同一个** rec4 实参；差别只在质检任务状态，'
                       '因此两条拒绝路径（:184-191 与 :192-197）被逐个打亮。',
        }
    return {'states': states, 'extra': extra}


# ------------------------------------------------------------------ 工资差分夹具
def seed_salary(app, rework_qty=5, normal_qty=3, price=10.0):
    """造「返工记录 / 正常记录」两名员工，供假开关双向差分使用。

    * ``_hvEMP_REWORK``：1 条 ``notes`` 含「返工」的生产记录（``rework_qty`` 件）；
    * ``_hvEMP_NORMAL``：1 条普通生产记录（``normal_qty`` 件）。
    真实库 ``production_record`` **0 行**（t1 只读重算）⇒ 必须自建。
    """
    from app import db
    from app import models as M
    today = date(2026, 10, 6)
    with app.app_context():
        proc = M.ProcessPrice.query.first()
        proc.price = price
        rows = {}
        for tag, qty, notes in (('REWORK', rework_qty, '_hv 返工记录（返工工时）'),
                                ('NORMAL', normal_qty, '_hv 正常记录')):
            emp = M.Employee(employee_id=f'_hvEMP_{tag}', name=f'_hv 员工{tag}',
                             department='_hv', base_salary=100.0, coefficient=1.5,
                             hire_date=date(2026, 1, 1))
            db.session.add(emp)
            db.session.flush()
            rec = M.ProductionRecord(employee_id=emp.id, process_id=proc.id, quantity=qty,
                                     date=today, notes=notes)
            db.session.add(rec)
            db.session.flush()
            rows[tag] = {'employee_id': emp.id, 'employee_code': emp.employee_id,
                         'record_id': rec.id, 'quantity': qty, 'notes': notes}
            _note('employee', id=emp.id)
            _note('production_record', id=rec.id)
        db.session.commit()
        rows['process'] = {'id': proc.id, 'price': proc.price}
        rows['date'] = today.isoformat()
    return rows


def salary_piecework(app, seed_info, start=None, end=None, employee_codes=None):
    """按 ``routes.py:1815`` 的原式重算计件工资（不改任何代码）。

    ``piecework = sum(record.quantity * record.process.price) * employee.coefficient``
    """
    from app import models as M
    start = start or date.fromisoformat(seed_info['date'])
    end = end or start
    codes = employee_codes or ['_hvEMP_REWORK', '_hvEMP_NORMAL']
    out = {}
    with app.app_context():
        for code in codes:
            emp = M.Employee.query.filter_by(employee_id=code).first()
            if emp is None:
                out[code] = None
                continue
            records = M.ProductionRecord.query.filter(
                M.ProductionRecord.employee_id == emp.id,
                M.ProductionRecord.date.between(start, end)).all()
            piecework = sum(r.quantity * r.process.price for r in records) * emp.coefficient
            out[code] = {
                'employee_id': emp.id,
                'records': len(records),
                'quantities': [r.quantity for r in records],
                'piecework': round(piecework, 4),
                'base_salary': emp.base_salary,
                'coefficient': emp.coefficient,
                'total_formula': round(emp.base_salary + piecework, 4),
            }
    return out


def batch_item_derived_records(app, batch_item_id):
    """按 ``batch_item_production_records`` 的同一口径（notes 含 JSON）取记录 id。"""
    from app.services import mes_service
    from app import models as M
    with app.app_context():
        bi = M.ProductionBatchItem.query.get(batch_item_id)
        rows = mes_service.batch_item_production_records(bi)
        return [{'id': r.id, 'notes': r.notes} for r in rows]


def set_rework_switch(app, value):
    """写 ``quality.rework_counts_piecework`` 开关（副本内），返回写入后的读回值。"""
    from app import db
    from app import models as M
    with app.app_context():
        changed = M.SystemConfig.set('quality.rework_counts_piecework', bool(value), user_id=None)
        db.session.commit()
        M.SystemConfig.invalidate_cache()
        raw = M.SystemConfig.query.filter_by(key='quality.rework_counts_piecework').first()
        readback = M.SystemConfig.get('quality.rework_counts_piecework')
        return {'changed': changed, 'raw': raw.value if raw else None, 'readback': readback}


def switch_read_sites():
    """配置开关的**读取点**盘点（AST ``SystemConfig.get('key')`` 字面量，排除定义处）。

    返回 ``{'defaults': [...], 'read_sites': {key: [file:line, ...]}}``。
    本函数只看 AST 调用点，不看注释与字符串，避免把「定义」误当「消费」。
    """
    import ast
    import os
    from app import models as M
    defaults = [d['key'] for d in M.SystemConfig.DEFAULTS]
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    read_sites = {k: [] for k in defaults}
    for dirpath, dirnames, filenames in os.walk(os.path.join(root, 'app')):
        dirnames[:] = [d for d in dirnames if d != '__pycache__']
        for fn in sorted(filenames):
            if not fn.endswith('.py'):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root).replace('\\', '/')
            tree = ast.parse(open(full, encoding='utf-8').read())
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if not (isinstance(func, ast.Attribute) and func.attr == 'get'
                        and isinstance(func.value, ast.Name) and func.value.id == 'SystemConfig'):
                    continue
                if not node.args:
                    continue
                arg = node.args[0]
                if isinstance(arg, ast.Constant) and arg.value in read_sites:
                    read_sites[arg.value].append(f'{rel}:{node.lineno}')
    return {'defaults': defaults, 'read_sites': read_sites,
            'unread_defaults': [k for k, v in read_sites.items() if not v]}


# ============================================================================
# C-10 / V-04：台账产物化 + 幂等 + 隔离自证（本节是本任务**唯一新增面**）
# ----------------------------------------------------------------------------
# 判据映射（`33-剩余项业务验收判据.md` §3.1；`35` §4 C-10 行）：
#   E-10.1 跨 run 幂等        -> `--selftest` 双跑 + `--compare`（断言集合与判定逐条相同）
#   E-10.2 同库重跑不撞 UNIQUE -> `seed_material_ledger` 连调两次；编号 = `_hvRAW<i>` + RUN_ID + 调用序号
#   E-10.3 台账产物化 + 逐表对拍 -> `write_manifest()` 落 `evidence/harness/<RUN_ID>/fixtures_manifest.json`
#   E-10.4 副本隔离自证        -> `copy_path_verdict()`：文件名含 RUN_ID + 在 run 临时目录 + 非真实库
# 三条**阳性对照**（回答「删掉它什么会变红」，对应 28 §3 A-73 与 35 §2.3 形态⑦）：
#   ① 直接写入重复 `internal_number` => 必须抛 IntegrityError（证明 UNIQUE 约束真的在，旧固定编号必红）
#   ② 两次调用之间插一行**不记账**的外部写入 => 逐表对拍必须报红（35 §4 C-10 的阴性用例）
#   ③ 把真实库路径喂给隔离判据 => 必须报红（E-10.4 的阳性对照）
# 运行（绝对路径解释器，A-7；证据落 `evidence/harness/<HARNESS_RUN_ID>/`）：
#   $env:HARNESS_RUN_ID='r2-exec-b3-v04'
#   & 'F:\Miniconda\envs\wage\python.exe' -B test-reports-2026-10\harness\fixtures.py --selftest --report <path.json>
#   & 'F:\Miniconda\envs\wage\python.exe' -B test-reports-2026-10\harness\fixtures.py --compare <a.json> <b.json>
# ============================================================================
MANIFEST_SCHEMA = 'fixtures-manifest/1'

#: 表 -> 夹具族（E-10.3 要求「至少覆盖 4 类夹具表」，此处用于机检而非人工声明）
TABLE_CLASSES = {
    'raw_material': '料账', 'material_allocations': '料账',
    'finished_product': '发货', 'shipments': '发货', 'shipment_items': '发货',
    'suppliers': '采购', 'purchase_orders': '采购', 'purchase_order_items': '采购',
    'inspection_tasks': '质检门禁', 'inspection_records': '质检门禁',
    'nonconformity_records': '质检门禁', 'workpieces': '质检门禁',
    'employee': '工资差分', 'production_record': '工资差分',
    'products': '基础对象', 'process_price': '基础对象', 'raw_material_categories': '基础对象',
    'production_orders': '基础对象', 'production_batches': '基础对象',
    'production_batch_items': '基础对象',
    'user': '脚手架', 'consumables': '脚手架', 'consumable_categories': '脚手架',
    'customers': '脚手架', 'customer_addresses': '脚手架', 'bonus_penalties': '脚手架',
    'material_requisitions': '脚手架', 'product_bom': '脚手架', 'inspection_templates': '脚手架',
}
E10_3_REQUIRED_CLASSES = ('料账', '发货', '采购', '质检门禁')

_BASELINE = None          # 副本库「零夹具写入之前」的逐表快照（`_open_ledger` 内采集）
_COPY_ALIAS = None        # 带 RUN_ID 的副本别名（与 URI 指向的副本同 inode）
_COPY_ALIAS_NOTE = ''
_CALL_SEQ = {}            # 同一 run 内各夹具族的调用序号（E-10.2 的唯一后缀来源）
_LAST_WRITE = {'sha256': None, 'path': None}


def _run_tag():
    """``RUN_ID`` 的安全形态（目录名 / 键名 / 唯一后缀共用；非法字符一律转 ``_``）。"""
    tag = ''.join(c if (c.isalnum() or c in '-_.') else '_' for c in str(RUN_ID or 'noid'))
    return tag[:48] or 'noid'


def _call_tag(family):
    """同一 run 内第 N 次调用某夹具族的唯一后缀（E-10.2：两次的编号**必须互不相同**）。"""
    n = int(_CALL_SEQ.get(family, 0)) + 1
    _CALL_SEQ[family] = n
    return '_%s_c%d' % (_run_tag(), n)


def _now():
    import time
    return time.strftime('%Y-%m-%d %H:%M:%S')


def _q(name):
    """SQLite 标识符引用（``user`` 一类名字也不出错）。"""
    return '"%s"' % str(name).replace('"', '""')


def _open_ledger(app, tag):
    """台账开工：① 采基线（**任何夹具写入之前**）② 建带 RUN_ID 的同 inode 副本别名。"""
    _capture_baseline(app)
    _link_run_copy(path=copy_path(), tag=tag)
    return {'baseline_tables': len((_BASELINE or {}).get('tables') or {}),
            'copy_alias': _COPY_ALIAS, 'copy_alias_note': _COPY_ALIAS_NOTE}


def _capture_baseline(app):
    """台账基线：逐表 ``COUNT(*)`` / ``MAX(id)``（E-10.3 逐表对拍的分母，缺它则对拍不成立）。"""
    global _BASELINE
    from app import db
    snap = {}
    with app.app_context():
        for name, tbl in sorted(db.metadata.tables.items()):
            has_id = 'id' in [c.name for c in tbl.columns]
            try:
                cnt = db.session.execute(db.text('SELECT COUNT(*) FROM %s' % _q(name))).scalar()
                mx = (db.session.execute(db.text('SELECT MAX(id) FROM %s' % _q(name))).scalar()
                      if has_id else None)
                snap[name] = {'count': int(cnt or 0), 'max_id': mx, 'id_col': 'id' if has_id else None}
            except Exception as exc:      # 单表失败不掩盖其余表（并如实登记）
                snap[name] = {'count': None, 'max_id': None, 'id_col': None,
                              'error': '%s: %s' % (exc.__class__.__name__, exc)}
    _BASELINE = {'captured_at': _now(), 'run_id': RUN_ID, 'table_count': len(snap), 'tables': snap,
                 'real_db_sha256_at_baseline': sha256_file(REAL_DB),
                 'real_db_pinned': REAL_DB_SHA256_EXPECTED}
    return _BASELINE


def _link_run_copy(path, tag='nv'):
    """给本次 run 的副本建一个**同 inode** 的别名，使台账的 ``copy_path`` 文件名含 ``RUN_ID``（E-10.4）。

    ``scripts/_test_bootstrap.make_app()`` 固定把副本命名成 ``<tmpdir>/app.db``（该文件不在本任务
    inScope）⇒ 不重写上游，改用 ``os.link``：两个名字**同一个 inode**，``os.path.samefile`` 为真，
    因此「文件名含 RUN_ID」与「它就是本次副本」同时成立，且不是复制品（不会读到两个分叉的库）。
    文件系统/沙箱不支持硬链接时**如实降级**（``_COPY_ALIAS=None`` + 原因），绝不伪造。
    """
    global _COPY_ALIAS, _COPY_ALIAS_NOTE
    base = tmp_dir('db')
    dest = os.path.join(base, 'app_%s_%s.db' % (tag, _run_tag()))
    try:
        if not os.path.abspath(dest).startswith(os.path.abspath(base) + os.sep):
            raise OSError('拒绝在 run 临时目录之外落盘：%s' % dest)
        if os.path.exists(dest):        # 目标只可能是本 run 目录内的同名残留
            os.remove(dest)
        os.link(path, dest)
        same = os.path.samefile(path, dest)
        _COPY_ALIAS = dest if same else None
        _COPY_ALIAS_NOTE = ('hardlink 别名与 URI 副本同 inode（samefile=True）'
                            if same else 'os.link 返回但 samefile=False ⇒ 弃用（如实降级）')
    except OSError as exc:
        _COPY_ALIAS, _COPY_ALIAS_NOTE = None, '%s: %s' % (exc.__class__.__name__, exc)
    return _COPY_ALIAS


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_new_row(table, rid):
    """该行是否在基线之后新增（无基线信息时**视为新增**：宁可多记，不可漏记）。"""
    base = ((_BASELINE or {}).get('tables') or {}).get(table) or {}
    if base.get('max_id') is None:
        return True
    got = _as_int(rid)
    return True if got is None else got > _as_int(base['max_id'])


def _note_seeded(app, users, seeded):
    """把 ``_test_bootstrap`` **直接建的行**补进台账（F-4：这些行原本零记账）。"""
    from app import db
    from app import models as M
    made = 0
    with app.app_context():
        for model_name, rid in sorted((seeded or {}).items()):
            table = getattr(getattr(M, model_name, None), '__tablename__', None)
            if table and rid is not None and _is_new_row(table, rid):
                _note(table, id=rid, source='seed_fixtures')
                made += 1
        for role, username in sorted((users or {}).items()):
            row = M.User.query.filter_by(username=username).first()
            if row is not None and _is_new_row('user', row.id):
                _note('user', id=row.id, source='ensure_role_users', role=role)
                made += 1
    return made


def _dedup_rows():
    """台账行按 (表, id) 去重（``_note`` 可能被同一行叫两次）；返回逐表重复计数供复核。"""
    out, dups = {}, {}
    for table, rows in _MANIFEST.items():
        seen, keep, dup = set(), [], 0
        for row in rows:
            rid = row.get('id')
            if rid is not None and rid in seen:
                dup += 1
                continue
            if rid is not None:
                seen.add(rid)
            keep.append(row)
        out[table] = keep
        if dup:
            dups[table] = dup
    return out, dups


def reconcile(app=None):
    """逐表对拍：``manifest.rows`` 与副本库**实际新增行**是否一致（E-10.3 的核心判据）。

    某表 OK 需三条同时成立：``Δcount == len(rows)``、台账里每个 id 都在库内、
    基线之后新增的 id **全部**被记账（``unrecorded_ids`` 为空）。缺基线 ⇒ ``ok=None``（**不得**判 OK）。
    """
    app = app or _APP
    rows, dups = _dedup_rows()
    out = {'ok': None, 'tables': {}, 'problems': [], 'duplicate_notes': dups,
           'recorded_tables': len(rows), 'rows_total': sum(len(v) for v in rows.values()),
           'basis': 'manifest.rows vs 副本库 Δcount / Δid（基线 = make_isolated_app 时的副本快照）',
           'unrecorded_note': '基线之后由**应用/业务链**写入的行也会落进 unrecorded_ids：夹具台账只记账'
                              '夹具族建的行 ⇒ 「逐表一致」在 --selftest 的受控场景里断言，'
                              '其它 run 的产物只报读数、不判 HIT'}
    if app is None or not (_BASELINE or {}).get('tables'):
        out['problems'].append('无 app 或无基线（未走 make_isolated_app）⇒ 对拍不成立，不得判 OK')
        return out
    from app import db
    base_tables = (_BASELINE or {}).get('tables') or {}
    with app.app_context():
        known = set(db.metadata.tables)
        for table in sorted(rows):
            rec = {'recorded': len(rows[table]), 'ids': [r.get('id') for r in rows[table]]}
            base = base_tables.get(table) or {}
            if table not in known:
                rec['verdict'] = 'RED'
                rec['reason'] = '台账表名 %r 不在 db.metadata ⇒ 记账 label 与库内表名不一致' % table
                out['problems'].append('%s: %s' % (table, rec['reason']))
                out['tables'][table] = rec
                continue
            if base.get('count') is None:
                rec['verdict'] = 'RED'
                rec['reason'] = '基线缺该表（%s）⇒ 无法对拍' % (base.get('error') or '未采集')
                out['problems'].append('%s: %s' % (table, rec['reason']))
                out['tables'][table] = rec
                continue
            cnt = int(db.session.execute(db.text('SELECT COUNT(*) FROM %s' % _q(table))).scalar() or 0)
            rec['actual_count'] = cnt
            rec['baseline_count'] = int(base['count'])
            rec['delta'] = cnt - int(base['count'])
            rec['ids_missing'], rec['unrecorded_ids'] = [], []
            if 'id' in [c.name for c in db.metadata.tables[table].columns]:
                present = {r[0] for r in db.session.execute(
                    db.text('SELECT id FROM %s' % _q(table))).fetchall()}
                rec['ids_missing'] = sorted(i for i in rec['ids'] if i not in present)
                mx = _as_int(base.get('max_id'))
                if mx is not None:
                    rec['unrecorded_ids'] = sorted(
                        int(i) for i in present if _as_int(i) is not None and _as_int(i) > mx
                        and i not in set(rec['ids']))
            ok = (rec['delta'] == rec['recorded'] and not rec['ids_missing']
                  and not rec['unrecorded_ids'])
            rec['verdict'] = 'OK' if ok else 'RED'
            if not ok:
                out['problems'].append('%s: Δ=%s 记账=%s 库内缺失=%s 未记账=%s'
                                       % (table, rec['delta'], rec['recorded'],
                                          rec['ids_missing'], rec['unrecorded_ids']))
            out['tables'][table] = rec
    out['ok'] = not out['problems']
    return out


def copy_path_verdict(path=None, real_db=None):
    """E-10.4 判据（**纯函数**，可对任意路径做阴阳性对照）。

    OK 需四条同时成立：文件名含 ``RUN_ID``、路径落在本 run 临时目录、文件真实存在、
    ``os.path.samefile`` 判定它**不是**真实库 ``app.db``。
    """
    if path is None:
        path = _COPY_ALIAS or _COPY_PATH
    real = real_db or REAL_DB
    reasons = []
    if not path:
        return {'ok': False, 'path': None, 'run_id': RUN_ID, 'reasons': ['copy_path 为空']}
    ap = os.path.abspath(path)
    if str(RUN_ID) not in os.path.basename(ap):
        reasons.append('文件名不含 RUN_ID（%s）' % RUN_ID)
    if not ap.startswith(os.path.abspath(TMP_ROOT) + os.sep):
        reasons.append('路径不落在本 run 临时目录（%s）' % TMP_ROOT)
    if not os.path.exists(ap):
        reasons.append('文件不存在：%s' % ap)
    if os.path.exists(real):
        try:
            if os.path.samefile(ap, real):
                reasons.append('该文件就是真实库 app.db（samefile=True）⇒ 拒')
        except OSError as exc:
            reasons.append('samefile 探测失败：%s' % exc.__class__.__name__)
    return {'ok': not reasons, 'path': ap, 'basename': os.path.basename(ap), 'run_id': RUN_ID,
            'reasons': reasons, 'is_real_db': any('真实库' in r for r in reasons)}


def isolation_evidence(path=None):
    """台账的隔离自证块（E-10.4）：copy_path 判据 + 真实库指纹（钉死值对拍）。"""
    real = real_db_status()
    target = (_COPY_ALIAS or _COPY_PATH) if path is None else path
    uri_sha = (sha256_file(_COPY_PATH) if (_COPY_PATH and os.path.exists(_COPY_PATH)) else None)
    return {'run_id': RUN_ID, 'copy_path': target, 'copy_path_uri': _COPY_PATH,
            'copy_path_alias_note': _COPY_ALIAS_NOTE, 'copy_path_uri_sha256': uri_sha,
            'verdict': copy_path_verdict(target), 'real_db': real,
            'real_db_pinned': REAL_DB_SHA256_EXPECTED,
            'real_db_unchanged': real['sha256'] == REAL_DB_SHA256_EXPECTED}


#: 同一 RUN_ID 内跨进程**必然漂移**的字段（实测两跑 diff）：时间戳与随机 ``mkdtemp`` 副本路径。
#: 幂等复用判据 = 剥离这些键后的「稳定投影」相等（B18-08 ① / N-14 同族治本）。
_STABLE_VOLATILE_KEYS = ('generated_at', 'captured_at', 'copy_path_uri',
                         'copy_path_uri_sha256', 'artifact')


def _stable_view(value, volatile=_STABLE_VOLATILE_KEYS):
    """递归剥离漂移键后的稳定投影（**只用于复用判据**，不改落盘内容，不伪造时间戳）。"""
    if isinstance(value, dict):
        return {k: _stable_view(v, volatile) for k, v in value.items() if k not in volatile}
    if isinstance(value, list):
        return [_stable_view(v, volatile) for v in value]
    return value


def _stable_digest(payload):
    import hashlib as _hashlib
    import json as _json
    return _hashlib.sha256(_json.dumps(_stable_view(payload), ensure_ascii=False,
                                       sort_keys=True).encode('utf-8')).hexdigest().upper()


def _reuse_stable_artifact(filename, payload):
    """同 run 幂等复用（B18-08 ①）：本 run 的 evidence 目录里已有「稳定投影」相同的产物
    ⇒ 复用现有路径、**不写新文件**（从而不产生 ``<name>.<run_id>.n`` 修订版）。

    命中：记 journal（``reused_identical=true`` + 现有文件指纹）并返回 ``(path, text)``；
    未命中 / 无既有文件：返回 ``None``，调用方走 ``save_evidence`` 正常写入（异内容仍改名，
    append-only 语义不变）。漂移字段仅限时间戳与随机副本路径（见 ``_STABLE_VOLATILE_KEYS``）。
    """
    import glob as _glob
    import json as _json
    directory = evidence_dir()
    stem = filename.rsplit('.', 1)[0]
    mine = _stable_view(payload)
    for cand in sorted(_glob.glob(os.path.join(directory, stem + '*.json'))):
        try:
            with open(cand, encoding='utf-8') as fh:
                existing_text = fh.read()
            if _stable_view(_json.loads(existing_text)) == mine:
                try:                       # 审计留痕：复用也是一次写入决策，记现有文件指纹
                    _append_journal(directory, os.path.join(directory, filename), cand,
                                    False, existing_text, reused_identical=True)
                except OSError:
                    pass
                return cand, existing_text
        except (OSError, ValueError):       # 读不了 / 解析不了的候选直接跳过，不阻塞正常写入
            continue
    return None


def _build_manifest(app=None, write=True, filename='fixtures_manifest.json', extra=None):
    """组装台账（逐表对拍 + 隔离自证），并可选**落盘为产物**（E-10.3）。

    落盘走 ``_env.save_evidence``：目标已存在则改名保留（``<name>.<run_id>.json``）+ 追加
    ``evidence_journal.jsonl`` 一行；**内容哈希与上次写入相同时不重复落盘**（记 ``skipped_identical``）。
    同 run 复跑：时间戳/随机副本路径导致全文哈希必变 ⇒ 先按 ``_stable_view`` 找**稳定投影相同**
    的既有产物复用（不新增修订版，B18-08 ①）；没有才落新文件。
    """
    import hashlib as _hashlib
    import json as _json
    rows, dups = _dedup_rows()
    classes = {}
    for table in sorted(rows):
        classes.setdefault(TABLE_CLASSES.get(table, '其他'), []).append(table)
    payload = {
        'schema': MANIFEST_SCHEMA,
        'run_id': RUN_ID,
        'run_tag': _run_tag(),
        'generated_at': _now(),
        'copy_path': _COPY_ALIAS or _COPY_PATH,
        'copy_path_uri': _COPY_PATH,
        'copy_path_alias_note': _COPY_ALIAS_NOTE,
        'rows': rows,
        'row_counts': {t: len(v) for t, v in sorted(rows.items())},
        'row_total': sum(len(v) for v in rows.values()),
        'duplicate_notes': dups,
        'table_classes': classes,
        'classes_covered': sorted(classes),
        'e10_3_required_classes': list(E10_3_REQUIRED_CLASSES),
        'e10_3_classes_ok': all(c in classes for c in E10_3_REQUIRED_CLASSES),
        'call_seq': dict(_CALL_SEQ),
        'reconcile': reconcile(app=app),
        'isolation': isolation_evidence(),
        'baseline': {'captured_at': (_BASELINE or {}).get('captured_at'),
                     'run_id': (_BASELINE or {}).get('run_id'),
                     'table_count': (_BASELINE or {}).get('table_count'),
                     'real_db_sha256_at_baseline': (_BASELINE or {}).get('real_db_sha256_at_baseline')},
        'artifact': None,
    }
    if extra:
        payload['extra'] = extra
    if write:
        text = _json.dumps(payload, ensure_ascii=False, indent=1)
        digest = _hashlib.sha256(text.encode('utf-8')).hexdigest().upper()
        sdigest = _stable_digest(payload)
        if _LAST_WRITE.get('sha256') == digest:
            payload['artifact'] = {'written': _LAST_WRITE.get('path'), 'skipped_identical': True,
                                   'sha256': digest, 'sha256_stable': sdigest,
                                   'bytes': len(text.encode('utf-8'))}
        else:
            reuse = _reuse_stable_artifact(filename, payload)
            if reuse:                       # 同 run 复跑：稳定投影相同 ⇒ 复用，不新增修订版
                reused_path, existing_text = reuse
                payload['artifact'] = {
                    'written': reused_path, 'skipped_identical': True,
                    'skipped_reason': 'stable_projection_match（同 run 复跑，仅时间戳/随机副本路径漂移）',
                    'sha256': _hashlib.sha256(existing_text.encode('utf-8')).hexdigest().upper(),
                    'sha256_stable': sdigest,
                    'bytes': len(existing_text.encode('utf-8'))}
                _LAST_WRITE.update({'sha256': digest, 'path': reused_path})
            else:
                try:
                    art = save_evidence(filename, text, journal=True)
                    _LAST_WRITE.update({'sha256': digest, 'path': art})
                    payload['artifact'] = {'written': art, 'skipped_identical': False,
                                           'sha256': digest, 'sha256_stable': sdigest,
                                           'bytes': len(text.encode('utf-8'))}
                except Exception as exc:      # 落盘失败必须留痕（不得静默当成功）
                    payload['artifact'] = {'written': None,
                                           'error': '%s: %s' % (exc.__class__.__name__, exc)}
    return payload


def write_manifest(app=None, filename='fixtures_manifest.json', extra=None):
    """E-10.3：把台账**落盘为产物**并返回台账（含 ``artifact`` 路径 / 字节 / 哈希）。"""
    return _build_manifest(app=app, write=True, filename=filename, extra=extra)


def seed_purchase_order(app, items=2, quantity=10.0, unit_price=3.5):
    """采购夹具族（``suppliers`` / ``purchase_orders`` / ``purchase_order_items``）。

    文件头声明的五个夹具域里**采购此前是空白**（E-10.3 明确点名该域）⇒ 本任务补齐。
    全部行 ``_hv`` 前缀、``_note`` 记账、``_call_tag`` 保证同库重跑不撞唯一约束（``code`` / ``po_no``）。
    """
    from app import db
    from app import models as M
    tag = _call_tag('purchase')
    with app.app_context():
        sup = M.Supplier(code='_hvSUP%s' % tag, name='_hv 采购供应商%s' % tag, is_active=True)
        db.session.add(sup)
        db.session.flush()
        _note('suppliers', id=sup.id, code=sup.code)
        po = M.PurchaseOrder(supplier_id=sup.id, status='draft', order_date=date.today(),
                             notes='_hv 采购夹具%s' % tag)
        db.session.add(po)
        db.session.flush()
        _note('purchase_orders', id=po.id, po_no=po.po_no, supplier_id=sup.id)
        item_ids = []
        for i in range(items):
            it = M.PurchaseOrderItem(po_id=po.id, material_type='raw', name='_hv 物料%d' % (i + 1),
                                     spec='_hv-SPEC', quantity=quantity, received_qty=0,
                                     unit_price=unit_price, unit='件')
            db.session.add(it)
            db.session.flush()
            _note('purchase_order_items', id=it.id, po_id=po.id)
            item_ids.append(it.id)
        db.session.commit()
        return {'supplier_id': sup.id, 'supplier_code': sup.code, 'po_id': po.id,
                'po_no': po.po_no, 'item_ids': item_ids}


# ------------------------------------------------------------------ 自检与对拍
def selftest(report_path=None):
    """V-04 自证（可复跑，CH-2 副本通道）：E-10.1…4 + 三条阳性对照。exit 0 = 全过。"""
    import json as _json
    checks = []

    def chk(cid, ok, detail=''):
        checks.append({'id': cid, 'verdict': 'PASS' if ok else 'FAIL', 'detail': detail})
        print('[%s] %-52s %s' % ('PASS' if ok else 'FAIL', cid, detail))
        return bool(ok)

    def mk_raw(internal_number, note_prefix):
        """在副本里直接造一行原料（不经夹具函数 ⇒ 天然是「外部写入」形态）。"""
        from app import db
        from app import models as M
        with app.app_context():
            cat = M.RawMaterialCategory.query.first()
            row = M.RawMaterial(supplier='%s 供应商' % note_prefix, category_id=cat.id if cat else None,
                                melt_number='%s_MELT' % note_prefix,
                                supplier_number='%s_SUP' % note_prefix,
                                internal_number=internal_number, quantity=1.0,
                                status='in_stock', is_archived=False)
            db.session.add(row)
            db.session.commit()
            return row.id

    def del_raw(row_id):
        from app import db
        from app import models as M
        with app.app_context():
            row = db.session.get(M.RawMaterial, row_id)
            if row is not None:
                db.session.delete(row)
                db.session.commit()
            return row_id

    before = sha256_file(REAL_DB)
    print('[ctx] RUN_ID=%s python=%s' % (RUN_ID, __import__('sys').version.split()[0]))
    app, path = make_isolated_app('v04')
    print('[ctx] copy_uri=%s' % path)
    print('[ctx] copy_alias=%s（%s）' % (_COPY_ALIAS, _COPY_ALIAS_NOTE))
    print('[ctx] baseline_tables=%s' % len((_BASELINE or {}).get('tables') or {}))

    _base_objects(app)                       # 基础对象（缺失时自建并记账）
    seed_all(app)                            # 脚手架直建的行也进台账（F-4 缺口）
    first = seed_material_ledger(app, rows=5, qty=5.0)
    second, err = [], ''
    try:
        second = seed_material_ledger(app, rows=5, qty=5.0)
    except Exception as exc:
        err = '%s: %s' % (exc.__class__.__name__, exc)
    n1 = [r['internal_number'] for r in first]
    n2 = [r['internal_number'] for r in second]
    chk('E-10.2.a_same_run_two_calls_no_unique', err == '' and len(second) == len(first),
        '第二次调用行数=%d err=%s' % (len(second), err or 'none'))
    chk('E-10.2.b_internal_numbers_disjoint_and_run_scoped',
        bool(n1 and n2) and not (set(n1) & set(n2)) and all(_run_tag() in x for x in n1 + n2),
        'n1[0]=%s n2[0]=%s' % (n1[:1], n2[:1]))

    # 阳性对照①：UNIQUE 约束是真的（旧固定编号 `_hvRAW{i+1}` 第二次调用就必然走这条路径）
    dup_raised = ''
    from app import db as _db
    from app import models as _M
    with app.app_context():
        cat = _M.RawMaterialCategory.query.first()
        dup = _M.RawMaterial(supplier='_hv 负例', category_id=cat.id if cat else None,
                             melt_number='_hvMELT_DUP', supplier_number='_hvSUP_DUP',
                             internal_number=n1[0], quantity=1.0, status='in_stock',
                             is_archived=False)
        _db.session.add(dup)
        try:
            _db.session.commit()
        except Exception as exc:
            dup_raised = exc.__class__.__name__
            _db.session.rollback()
    chk('E-10.2.c_unique_constraint_real_positive_control', 'IntegrityError' in dup_raised,
        '重复编号提交结果=%r（对照：修前固定编号第二次即此路径）' % dup_raised)

    # 其余夹具域（覆盖 E-10.3 的「四类」：料账 / 发货 / 采购 / 质检门禁；另加工资差分）
    fp = seed_shipment(app, quantity=7, kind='fg')
    cands = shipment_candidates(app)
    po = seed_purchase_order(app, items=2)
    seed_qc_gate(app)
    seed_salary(app)
    rec = reconcile(app)
    chk('E-10.3.c_reconcile_green_on_controlled_run', rec.get('ok') is True,
        '表数=%d 问题=%s' % (len(rec.get('tables') or {}), rec.get('problems')))

    # 阳性对照②（35 §4 C-10 的阴性用例）：两次调用之间插一行**不记账**的外部写入 ⇒ 对拍必须发现差异
    ext_id = mk_raw('_hvRAW_EXTERNAL_%s' % _run_tag(), '_hv 外部写入')
    red = reconcile(app)
    t_red = (red.get('tables') or {}).get('raw_material') or {}
    chk('E-10.3.d_external_write_detected_by_reconcile',
        red.get('ok') is False and ext_id in (t_red.get('unrecorded_ids') or []),
        'raw_material verdict=%s Δ=%s 未记账=%s' % (t_red.get('verdict'), t_red.get('delta'),
                                                t_red.get('unrecorded_ids')))
    del_raw(ext_id)
    rec2 = reconcile(app)
    chk('E-10.3.e_reconcile_recovers_after_removal', rec2.get('ok') is True,
        '问题=%s' % rec2.get('problems'))

    payload = write_manifest(app=app, extra={'selftest': True})
    art = payload.get('artifact') or {}
    apath = art.get('written')
    chk('E-10.3.a_artifact_written',
        bool(apath) and os.path.exists(apath) and os.path.getsize(apath) > 0,
        'path=%s bytes=%s sha16=%s' % (apath, art.get('bytes'),
                                       (art.get('sha256_stable') or art.get('sha256') or '')[:16]))
    loaded = {}
    try:
        loaded = _json.loads(open(apath, encoding='utf-8').read())
    except Exception as exc:
        loaded = {'_load_error': '%s: %s' % (exc.__class__.__name__, exc)}
    chk('E-10.3.b_artifact_shape_and_four_classes',
        all(k in loaded for k in ('run_id', 'copy_path', 'rows', 'reconcile', 'isolation'))
        and len(loaded.get('rows') or {}) >= 4 and loaded.get('e10_3_classes_ok') is True,
        '表数=%d 类别=%s' % (len(loaded.get('rows') or {}), loaded.get('classes_covered')))
    chk('E-10.3.f_artifact_reconcile_green', (loaded.get('reconcile') or {}).get('ok') is True,
        'artifact 内 problems=%s' % ((loaded.get('reconcile') or {}).get('problems')))
    legacy = manifest()                       # 既有 API（uat_chains.py:1240 的调用点）现在也落盘
    chk('E-10.3.g_legacy_manifest_api_writes_artifact',
        bool((legacy.get('artifact') or {}).get('written')),
        'artifact=%s' % ((legacy.get('artifact') or {}).get('written')))

    iso = payload.get('isolation') or {}
    v = iso.get('verdict') or {}
    chk('E-10.4.a_copy_path_run_scoped_and_not_real_db',
        v.get('ok') is True and str(RUN_ID) in (v.get('basename') or ''),
        'basename=%s reasons=%s note=%s' % (v.get('basename'), v.get('reasons'), _COPY_ALIAS_NOTE))
    rej = copy_path_verdict(REAL_DB)
    chk('E-10.4.b_real_db_positive_control_red', rej.get('ok') is False,
        '喂真实库路径的判定=%s reasons=%s' % (rej.get('ok'), rej.get('reasons')))
    after = sha256_file(REAL_DB)
    chk('E-10.4.c_real_db_sha256_unchanged', before == after == REAL_DB_SHA256_EXPECTED,
        '%s -> %s（钉死 %s）' % (before[:16], after[:16], REAL_DB_SHA256_EXPECTED[:16]))
    ids = [c['id'] for c in checks]
    chk('E-10.1.a_assertion_ids_unique_and_deterministic',
        len(ids) == len(set(ids)) and len(ids) >= 12, '断言数=%d' % len(ids))

    passed = sum(1 for c in checks if c['verdict'] == 'PASS')
    result = 'OK' if passed == len(checks) else 'FAILED'
    report = {'schema': 'fixtures-selftest/1', 'run_id': RUN_ID, 'run_tag': _run_tag(),
              'result': result, 'assertions': checks, 'passed': passed,
              'failed': len(checks) - passed, 'copy_path': _COPY_ALIAS or _COPY_PATH,
              'copy_path_uri': _COPY_PATH, 'copy_alias_note': _COPY_ALIAS_NOTE,
              'real_db_sha256_before': before, 'real_db_sha256_after': after,
              'artifact': apath, 'manifest_artifact': apath,
              'fixture_probe': {'finished_product_id': fp.get('id'), 'candidates': len(cands.get('candidates') or []),
                                'po_no': po.get('po_no'), 'po_items': len(po.get('item_ids') or [])}}
    if report_path:
        os.makedirs(os.path.dirname(os.path.abspath(report_path)), exist_ok=True)
    # 自检报告也走 E-01 的落盘 API（guard_write + 审计流水）；存档件里**不含** evidence_artifact 字段
    # （S-2 自引用约束：写入即改变自身），带该字段的副本另落 .tmp 供本次对拍使用。
    # 同 run 复跑：与 fixtures_manifest 同一套稳定投影复用（漂移仅 copy_path_uri）⇒ 不新增修订版。
    archived = None
    try:
        reuse = _reuse_stable_artifact('fixtures_selftest_report.json', report)
        if reuse:
            archived = reuse[0]
        else:
            archived = save_evidence('fixtures_selftest_report.json',
                                     _json.dumps(report, ensure_ascii=False, indent=1), journal=True)
    except Exception as exc:
        report['evidence_artifact_error'] = '%s: %s' % (exc.__class__.__name__, exc)
    report['evidence_artifact'] = archived
    if report_path:
        with open(report_path, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(_json.dumps(report, ensure_ascii=False, indent=1))
    print('[ctx] artifact=%s' % apath)
    print('[ctx] selftest_report_artifact=%s' % archived)
    print('assertions=%d passed=%d failed=%d' % (len(checks), passed, len(checks) - passed))
    print('RESULT: %s' % result)
    return 0 if result == 'OK' else 1


def compare_runs(path_a, path_b):
    """E-10.1（跨 run 幂等，软口径）：两次 ``--selftest`` 的**断言集合与判定逐条相同**且均 OK。"""
    import json as _json
    with open(path_a, encoding='utf-8') as fh:
        a = _json.load(fh)
    with open(path_b, encoding='utf-8') as fh:
        b = _json.load(fh)
    ma = {c['id']: c['verdict'] for c in (a.get('assertions') or [])}
    mb = {c['id']: c['verdict'] for c in (b.get('assertions') or [])}
    only_a, only_b = sorted(set(ma) - set(mb)), sorted(set(mb) - set(ma))
    diff = sorted(k for k in set(ma) & set(mb) if ma[k] != mb[k])
    ok = (not only_a and not only_b and not diff
          and a.get('result') == 'OK' and b.get('result') == 'OK')
    payload = {'schema': 'fixtures-selftest-crossrun/1', 'compared_at': _now(),
               'run_a': {'run_id': a.get('run_id'), 'result': a.get('result'), 'assertions': len(ma)},
               'run_b': {'run_id': b.get('run_id'), 'result': b.get('result'), 'assertions': len(mb)},
               'report_a': os.path.abspath(path_a), 'report_b': os.path.abspath(path_b),
               'only_in_a': only_a, 'only_in_b': only_b, 'verdict_diff': diff,
               'identical_assertion_set': not only_a and not only_b,
               'identical_verdicts': not diff, 'ok': ok,
               'note': '两次 RUN_ID 不同 ⇒ detail 内的编号必然不同；E-10.1 的口径只对拍 id 与 verdict'}
    try:
        payload['artifact'] = save_evidence('fixtures_manifest_crossrun_compare.json',
                                            _json.dumps(payload, ensure_ascii=False, indent=1))
    except Exception as exc:
        payload['artifact'] = None
        payload['artifact_error'] = '%s: %s' % (exc.__class__.__name__, exc)
    print('run_a=%s run_b=%s' % (payload['run_a'], payload['run_b']))
    print('only_in_a=%s only_in_b=%s verdict_diff=%s identical=%s'
          % (only_a, only_b, diff, ok))
    print('[ctx] compare_artifact=%s' % payload.get('artifact'))
    print('RESULT: %s' % ('OK' if ok else 'FAILED'))
    return 0 if ok else 1


def main(argv=None):
    import sys as _sys
    args = list(_sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ('-h', '--help'):
        print('用法: fixtures.py --selftest [--report <path.json>] | --compare <a.json> <b.json>')
        return 0
    if args[0] == '--selftest':
        report = args[args.index('--report') + 1] if '--report' in args else None
        return selftest(report_path=report)
    if args[0] == '--compare':
        return compare_runs(args[1], args[2])
    print('未知参数: %s' % args)
    return 2


if __name__ == '__main__':
    import sys as _sys
    _sys.exit(main())

