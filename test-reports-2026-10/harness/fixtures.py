"""副本库夹具工厂（供 t4 / t5 / 本任务阴性矩阵复用）。

关键设计（与 `08` §6 第 1 步 / A-4 / A-10 / GAP-02 / GAP-39 对齐）：

1. **每个 run 一份自己的带时间戳副本**：``app_nv_<RUN_ID>.db``，落在 ``test-reports-2026-10/.tmp/<run_id>/``
   （本沙箱禁止 0o700 目录写入，且不可删 ⇒ 一律 ``os.makedirs``，绝不裸 ``tempfile.mkdtemp()``）。
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
                  sha256_file)

_APP = None
_COPY_PATH = None
_MANIFEST = {}


# ------------------------------------------------------------------ 隔离与启动
def _patch_mkdtemp():
    """把 ``tempfile.mkdtemp`` 指向本 run 的隔离目录（同 `_sandbox_compat` 的放宽，但不依赖它）。"""
    import tempfile
    base = tmp_dir('mkdtemp')

    def _relaxed(suffix=None, prefix=None, dir=None):
        name = (prefix or '') + next(tempfile._get_candidate_names()) + (suffix or '')
        path = str(base / name) if hasattr(base, '__fspath__') else __import__('os').path.join(base, name)
        __import__('os').mkdir(path, 0o777)
        return path

    tempfile.mkdtemp = _relaxed
    return base


def make_isolated_app(tag='nv'):
    """返回 ``(app, copy_path)``，app 的 ``DATABASE_URL`` 一定指向本 run 的副本。"""
    global _APP, _COPY_PATH
    assert_real_db_untouched('before make_isolated_app')
    _patch_mkdtemp()
    import _test_bootstrap
    app, path = _test_bootstrap.make_app(fresh=True)
    _APP, _COPY_PATH = app, path
    assert_isolated(app)
    return app, path


def seed_all(app, password='test_pw_123'):
    """复刻既有脚手架的前置：``ensure_role_users`` + ``seed_fixtures``（幂等，可反复调用）。

    这一步是 ``smoke_test`` / ``permission_matrix`` / ``functional_test`` 的共同前置，
    少了它带参 GET 会有 10 条因「模型无数据」被跳过（实测：138 条 vs 148 条）。
    """
    import _test_bootstrap
    users, pw = _test_bootstrap.ensure_role_users(app, password=password)
    seeded = _test_bootstrap.seed_fixtures(app)
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
    return {'run_id': __import__('_env').RUN_ID, 'copy_path': _COPY_PATH, 'rows': _MANIFEST}


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
    made = []
    with app.app_context():
        cat = M.RawMaterialCategory.query.first()
        for i in range(rows):
            rm = M.RawMaterial(
                supplier=f'_hv 供应商{i + 1}', category_id=cat.id, melt_number=f'_hvMELT{i + 1}',
                supplier_number=f'_hvSUP{i + 1}', internal_number=f'_hvRAW{i + 1}',
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

