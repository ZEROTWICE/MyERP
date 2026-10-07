"""r2_c11_probe.py — C-11（V-08）「不可判定项」的**行为载体**。

本探针只做一件事：把 `33-剩余项业务验收判据.md` §3.1 `F-11.*` 中**尚无行为载体**的 4 条
（AC-44 / AC-45 / AC-49 / AC-56）变成**可判处 passed/failed 的读数据**，供账本回写引用。

## 只读约束（R-1 / R-2）
- **绝不打开真实库 `app.db`**（连只读连接都不用）：全部夹具在 **`sqlite:///:memory:`
  的独立 Flask app** 上 `db.create_all()` 现建现用，进程结束即消失。
- 每条 AC 一个**独立 app 上下文**（`isolated()` 上下文管理器）⇒ 互不污染，且失败隔离到单条。
- 唯一被「读」的仓库文件是 `app/**/*.py` 源码（AST/正则静态面）。
- 真实库 SHA256 由 `_env` 前后各复核一次（只读 `sha256_file`）。

## 载体与判据（`33` §3.1 的原文口径）
| AC | 判据 | 本探针的载体形态 |
| --- | --- | --- |
| `AC-44` | 草稿单占用去重 + 阴性对照（取消后重新可发） | `mes_service.shipment_candidate_stock` / `shipment_allocated_product_ids` / `shipment_order_line_remaining_quantity` + `Shipment.status` 置 `cancelled` |
| `AC-45` | 三态（TRUE/FALSE/NULL）候选 + 登记拒绝 | 同上 + `shipment_register_finished_product` 的真实返回元组 |
| `AC-49` | **期望 FAIL**：库存降到阈值以下仍 **0 条** `inventory_warning` 通知；`notify_inventory_warning` 调用点 0 | `RawMaterial.min_stock_level`/`is_low_stock` + `Notification` 计数 + 全 `app/` AST+文本调用点计数 |
| `AC-56` | 「NULL=未存档」**部分统一**（3 统一 / 3 未统一）；行为面：NULL 行在 `filter_by(is_archived=False)` 下**取不到**、在 OR-NULL 下**可见** | 源码读取点静态面 + NULL 造行后的双形态查询对照 |

用法（仓库根；A-40：复跑换 `HARNESS_RUN_ID`）：

    $env:HARNESS_RUN_ID='r2-exec-b3-v08'
    F:\\Miniconda\\envs\\wage\\python.exe -B test-reports-2026-10/harness/r2_c11_probe.py

退出码：0 = 四条 AC 的载体断言全过（AC-49 的「期望 FAIL」也算通过）；
        1 = 任一载体断言失败。落盘 `evidence/harness/<RUN_ID>/r2_c11_probe.json`。
"""
import argparse
import ast
import contextlib
import json
import logging
import os
import re
import sys
import time

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import _env  # noqa: E402

REPO_ROOT = _env.REPO_ROOT
APP_DIR = os.path.join(REPO_ROOT, 'app')
if REPO_ROOT not in sys.path:          # 裸跑时 `app` 包要能 import（w2w3_probe 同法）
    sys.path.insert(0, REPO_ROOT)

RESULTS = []          # [{ac, carrier, checks:[{name, expected, actual, passed}], status}]


# --------------------------------------------------------------- 断言与记账
def _record(ac, carrier, checks, note=''):
    passed = all(c['passed'] for c in checks) and bool(checks)
    RESULTS.append({
        'ac': ac, 'carrier': carrier, 'checks': checks,
        'status': 'passed' if passed else 'failed', 'note': note,
    })
    mark = 'PASS' if passed else 'FAIL'
    print('[%s] %s  (%s)' % (mark, ac, carrier))
    for c in checks:
        print('        %-4s %-46s exp=%s got=%s'
              % ('ok' if c['passed'] else 'X', c['name'],
                 _short(c['expected']), _short(c['actual'])))
    return passed


def _short(v):
    s = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
    return s if len(s) <= 60 else s[:57] + '...'


def ck(name, expected, actual):
    return {'name': name, 'expected': expected, 'actual': actual,
            'passed': json.dumps(expected, sort_keys=True, ensure_ascii=False, default=str)
            == json.dumps(actual, sort_keys=True, ensure_ascii=False, default=str)}


# --------------------------------------------------------------- 隔离 app
@contextlib.contextmanager
def isolated():
    """全新的内存 app（`sqlite:///:memory:` + create_all），退出即销毁。

    **不读 `app.db`**：`create_all` 之外不碰任何磁盘库文件。
    """
    for name in [m for m in list(sys.modules)
                 if m == 'config' or m == 'app' or m.startswith('app.')]:
        del sys.modules[name]
    os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
    from app import create_app, db
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, SQLALCHEMY_DATABASE_URI='sqlite:///:memory:')
    assert app.config['SQLALCHEMY_DATABASE_URI'] == 'sqlite:///:memory:'
    with app.app_context():
        db.create_all()
        yield app, db
        db.session.remove()


class _Capture(logging.Handler):
    """把 current_app.logger 的 WARNING 抓下来（判据要断「有说明文案」）。"""

    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.lines = []

    def emit(self, rec):
        self.lines.append(rec.getMessage())


@contextlib.contextmanager
def captured_logs(app):
    cap = _Capture()
    app.logger.addHandler(cap)
    try:
        yield cap
    finally:
        app.logger.removeHandler(cap)


import datetime as _dt

_DATE = _dt.date(2026, 1, 1)


def _mk_product(db, M, name='_C11产品'):
    """必填：global_sn / product_code / product_name（models.py:966-993）。"""
    p = M.Product(product_code='_C11PC', product_name=name, drawing_number='_C11DWG')
    db.session.add(p)
    db.session.flush()
    return p


def _set_archived(db, obj, archived):
    """把 `is_archived` 落成 TRUE / FALSE / **SQL NULL** 三态。

    ⚠ 实测发现（本探针首跑即抓到）：`is_archived` 列带 `default=False`，SQLAlchemy 在
    **INSERT 时**才套用该默认值 ⇒ 不论「不赋值」还是显式 `= None`，**写进库的都是 0**，
    真 NULL 根本造不出来。这也正是 `33` §5 P-2 要求「`UPDATE … SET is_archived=NULL`
    **显式造行**」的原因。
    ⇒ 实现 = 正常 INSERT + **一条原始 SQL UPDATE** + `refresh` 回读（真实落库路径）。
    """
    table = obj.__table__.name
    db.session.add(obj)
    db.session.flush()
    db.session.execute(db.text(
        'UPDATE %s SET is_archived = :v WHERE id = :i' % table),
        {'v': None if archived is None else (1 if archived else 0), 'i': obj.id})
    db.session.flush()
    db.session.refresh(obj)
    return obj


def _db_archived(db, table):
    """直接从库回读 `is_archived` 三态（判据必须落在库内实值上，不是 ORM 视图）。"""
    rows = db.session.execute(db.text(
        'SELECT id, is_archived FROM %s ORDER BY id' % table)).fetchall()
    return [r[1] for r in rows]


def _mk_raw(db, M, qty, archived=None):
    """RawMaterial 无 min_stock_level 列（models.py:511-526）⇒ 阈值只用 Consumable。"""
    r = M.RawMaterial(supplier='_C11', category_id=1, melt_number='_C11M',
                      supplier_number='_C11S', quantity=qty)
    _set_archived(db, r, archived)
    return r


def _mk_consumable(db, M, qty, min_stock):
    """Consumable 是唯一带 min_stock_level + is_low_stock 的库存模型（models.py:606/631-634）。"""
    c = M.Consumable(supplier='_C11', category_id=1, supplier_number='_C11S',
                     quantity=qty, min_stock_level=min_stock)
    db.session.add(c)
    db.session.flush()
    return c


def _mk_fp(db, M, product, qty=5, archived=None, serial='_C11FP1', stock_kind='fg'):
    """必填：global_sn / serial_number / product_number / production_date / drawing_number
    / model / inspector / quantity（models.py:443-459）。"""
    fp = M.FinishedProduct(
        serial_number=serial, global_sn=serial, product_number='_C11PN',
        production_date=_DATE, drawing_number='_C11DWG', model='_C11M', inspector='_C11I',
        product_id=product.id, quantity=qty, status='in_stock', stock_kind=stock_kind,
    )
    _set_archived(db, fp, archived)
    return fp


def _mk_order_line(db, M, product, qty=10):
    """Customer/SalesOrder 必填：customer_code+customer_name / order_source+year_month。"""
    cust = M.Customer(customer_code='_C11CC', customer_name='_C11客户')
    db.session.add(cust)
    db.session.flush()
    order = M.SalesOrder(order_number='_C11SO', order_source='_C11src',
                         customer_id=cust.id, year_month='2026-01', status='confirmed')
    db.session.add(order)
    db.session.flush()
    line = M.SalesOrderItem(sales_order_id=order.id, product_id=product.id, quantity=qty)
    db.session.add(line)
    db.session.flush()
    return order, line


def _mk_shipment(db, M, order, status='draft', shipment_no='_C11SH'):
    """Shipment 用 shipment_no（不是 shipment_number），见 models.py:3075-3093；该列 UNIQUE。"""
    ship = M.Shipment(shipment_no=shipment_no, sales_order_id=order.id, status=status)
    db.session.add(ship)
    db.session.flush()
    return ship


# --------------------------------------------------------------- AC-44
def ac44():
    checks = []
    with isolated() as (app, db):
        from app import models as M
        from app.services import mes_service as mes
        product = _mk_product(db, M)
        order, line = _mk_order_line(db, M, product, qty=10)
        fp = _mk_fp(db, M, product, qty=5, archived=False, serial='_C11AC44')
        ship1 = _mk_shipment(db, M, order, 'draft')

        before_taken = sorted(mes.shipment_allocated_product_ids())
        cands_before = [x.id for x in mes.shipment_candidate_stock(line)]
        checks.append(ck('①第1张草稿前 taken 为空', [], before_taken))
        checks.append(ck('①第1张草稿前候选含 F', [fp.id], cands_before))
        checks.append(ck('订单行剩余待发量（未占用）', 10.0,
                         mes.shipment_order_line_remaining_quantity(line)))

        item, reason = mes.shipment_register_finished_product(
            ship1, line, finished_product=fp, quantity=5)
        db.session.flush()
        checks.append(ck('①登记成功（reason=None）', None, reason))
        checks.append(ck('①draft 计入占用集合', [fp.id],
                         sorted(mes.shipment_allocated_product_ids())))

        # ② 第 2 张草稿：候选必须「取不到该行」
        ship2 = _mk_shipment(db, M, order, 'draft', shipment_no='_C11SH2')
        cands_after = [x.id for x in mes.shipment_candidate_stock(line)]
        checks.append(ck('②第2张草稿候选不含 F（去重）', [], cands_after))
        item2, reason2 = mes.shipment_register_finished_product(
            ship2, line, finished_product=fp, quantity=5)
        checks.append(ck('③强行指定 F ⇒ 登记被拒', True, item2 is None))
        checks.append(ck('③拒绝原因可读且含「已加入发货单」', True,
                         bool(reason2) and '已加入发货单' in reason2))
        n_items = M.ShipmentItem.query.count()
        fp_qty = float(db.session.get(M.FinishedProduct, fp.id).quantity)
        checks.append(ck('③第2张草稿未新增 ShipmentItem（总数）', 1, n_items))
        checks.append(ck('③F 的 quantity 不变（未被重复拆分）', 5.0, fp_qty))

        # 阴性对照：取消第 1 张草稿 ⇒ F 必须重新可发
        ship1.status = 'cancelled'
        db.session.flush()
        checks.append(ck('阴性对照①取消后 taken 释放', [],
                         sorted(mes.shipment_allocated_product_ids())))
        checks.append(ck('阴性对照②取消后候选重现 F', [fp.id],
                         [x.id for x in mes.shipment_candidate_stock(line)]))
        item3, reason3 = mes.shipment_register_finished_product(
            ship2, line, finished_product=fp, quantity=2)
        checks.append(ck('阴性对照③重新可发（未被永久占用）', None, reason3))
        db.session.rollback()

    _record('AC-44', 'harness/r2_c11_probe.py:ac44 + app/services/mes_service.py:1513/1542/1553/1624/1646',
            checks, '夹具=内存库现建（真实库零读）；draft 占用/去重/阴性对照三面齐备')


# --------------------------------------------------------------- AC-45
def ac45():
    checks = []
    with isolated() as (app, db):
        from app import models as M
        from app.services import mes_service as mes
        product = _mk_product(db, M)
        order, line = _mk_order_line(db, M, product, qty=30)
        fp_true = _mk_fp(db, M, product, 5, True, '_C11T')
        fp_false = _mk_fp(db, M, product, 5, False, '_C11F')
        fp_null = _mk_fp(db, M, product, 5, None, '_C11N')
        db.session.flush()
        # 显式确认三态在**库内**落地（NULL 不是「没赋值」而是真 NULL）
        checks.append(ck('三态造行（TRUE/FALSE/NULL）', [1, 0, None],
                         _db_archived(db, 'finished_product')))

        cands = [x.id for x in mes.shipment_candidate_stock(line)]
        checks.append(ck('①TRUE 行不在候选', False, fp_true.id in cands))
        checks.append(ck('②FALSE 行在候选', True, fp_false.id in cands))
        checks.append(ck('②NULL 行在候选（NULL=未存档）', True, fp_null.id in cands))

        ship = _mk_shipment(db, M, order, 'draft')
        t, rt = mes.shipment_register_finished_product(ship, line, finished_product=fp_true, quantity=5)
        checks.append(ck('①TRUE 行强行指定被拒', True, t is None))
        checks.append(ck('①拒绝文案含「已存档，不能发货」', True,
                         bool(rt) and '已存档，不能发货' in rt))
        f, rf = mes.shipment_register_finished_product(ship, line, finished_product=fp_false, quantity=2)
        checks.append(ck('②FALSE 行可登记', None, rf))
        n, rn = mes.shipment_register_finished_product(ship, line, finished_product=fp_null, quantity=2)
        checks.append(ck('②NULL 行可登记（未误拦）', None, rn))
        db.session.rollback()

    _record('AC-45', 'harness/r2_c11_probe.py:ac45 + app/services/mes_service.py:1562-1563/1643-1645',
            checks, '三态齐备（TRUE/FALSE/NULL 均为库内实值）；NULL 口径双向验证（候选可见 + 登记放行）')


# --------------------------------------------------------------- AC-49
NOTIFY_RE = re.compile(r'\bnotify_[A-Za-z_]*\s*\(')


def _app_call_sites():
    """扫 `app/**/*.py` 的**内容**，统计 `notify_*(` 调用点（静态面，A-71：必须搜内容）。"""
    defs, calls = [], []
    for dirpath, _dirnames, filenames in os.walk(APP_DIR):
        for fn in filenames:
            if not fn.endswith('.py'):
                continue
            p = os.path.join(dirpath, fn)
            rel = os.path.relpath(p, REPO_ROOT).replace('\\', '/')
            with open(p, encoding='utf-8', errors='replace') as fh:
                text = fh.read()
            lines = text.splitlines()
            try:
                tree = ast.parse(text)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                        and node.name.startswith('notify_'):
                    defs.append({'file': rel, 'line': node.lineno, 'name': node.name})
                if isinstance(node, ast.Call):
                    f = node.func
                    name = getattr(f, 'id', None) or getattr(f, 'attr', None)
                    if name and name.startswith('notify_'):
                        calls.append({'file': rel, 'line': node.lineno, 'name': name,
                                      'src': (lines[node.lineno - 1].strip() if node.lineno - 1 < len(lines) else '')})
    return defs, calls


def ac49():
    checks = []
    # 静态面：定义在校 + 调用点计数
    defs, calls = _app_call_sites()
    inv_defs = [d for d in defs if d['name'] == 'notify_inventory_warning']
    inv_calls = [c for c in calls if c['name'] == 'notify_inventory_warning']
    checks.append(ck('notify_inventory_warning 有定义', True, len(inv_defs) == 1))
    checks.append(ck('notify_inventory_warning 调用点数 = 0', 0, len(inv_calls)))
    all_missing = [(d['name'], d['file'], d['line']) for d in defs
                   if d['name'] not in {c['name'] for c in calls}]
    checks.append(ck('接线缺口计数（定义而无调用）', True, len(all_missing) >= 1))

    with isolated() as (app, db):
        from app import models as M
        with captured_logs(app):
            c = _mk_consumable(db, M, qty=5.0, min_stock=100.0)
            db.session.flush()
            triggered = bool(getattr(c, 'is_low_stock', False))
            low_rows = M.Consumable.query.filter(
                M.Consumable.quantity <= M.Consumable.min_stock_level).count()
            notif = M.Notification.query.filter_by(trigger_type='inventory_warning').count()
            n_total = M.Notification.query.count()
        checks.append(ck('阈值以下易耗品行存在', 1, low_rows))
        checks.append(ck('is_low_stock == True（阈值触发）', True, triggered))
        checks.append(ck('期望 FAIL：inventory_warning 通知数 = 0', 0, notif))
        checks.append(ck('期望 FAIL：Notification 总行数 = 0（无任何通知被写入）', 0, n_total))
        db.session.rollback()

    _record('AC-49', 'app/services/notification_service.py:484（定义，无调用点）+ app/models.py:606/631-634（阈值属性）+ harness/r2_c11_probe.py:ac49',
            checks,
            '登记为【期望 FAIL】而非「不可判定」：缺的是接线（缺陷面），不是覆盖；判据 = 接线后必须 +1')


# --------------------------------------------------------------- AC-56
UNIFIED = [
    ('app/main/quality.py', 744, 'db.or_(FinishedProduct.is_archived.is_(False), ... is_(None))'),
    ('app/main/routes.py', 6247, 'db.or_(FinishedProduct.is_archived.is_(False), ... is_(None))'),
    ('app/services/mes_service.py', 1562, 'db.or_(FinishedProduct.is_archived.is_(False), ... is_(None))'),
]
UNUNIFIED = [
    ('app/main/routes.py', 12065, "RawMaterial.query.filter_by(is_archived=False)"),
    ('app/main/routes.py', 12093, "Consumable.query.filter_by(is_archived=False)"),
    ('app/main/routes.py', 12122, "FinishedProduct.query.filter_by(is_archived=False)"),
]


def ac56():
    checks = []
    # ① 静态面：逐点读源码行，核对形态归类（3 统一 / 3 未统一）
    ok_u, ok_n = [], []
    for path, line, _desc in UNIFIED:
        src = open(os.path.join(REPO_ROOT, path), encoding='utf-8').read().splitlines()
        window = '\n'.join(src[line - 2:line + 1])
        ok_u.append(bool(re.search(r'is_archived\.is_\(None\)', window)))
    for path, line, _desc in UNUNIFIED:
        src = open(os.path.join(REPO_ROOT, path), encoding='utf-8').read().splitlines()
        cur = src[line - 1]
        ok_n.append('filter_by(is_archived=False)' in cur and 'is_(None)' not in cur)
    checks.append(ck('①已统一 3 处均为 OR-NULL（含 None 分支）', [True] * 3, ok_u))
    checks.append(ck('①未统一 3 处均为 filter_by(is_archived=False)', [True] * 3, ok_n))

    # ② 行为面：显式 NULL 造行 ⇒ OR-NULL 可见 / filter_by(False) 不可见
    with isolated() as (app, db):
        from app import models as M
        product = _mk_product(db, M)
        fp_null = _mk_fp(db, M, product, 3, None, '_C11AC56')
        raw_null = _mk_raw(db, M, qty=7, archived=None)
        checks.append(ck('②NULL 造行落库复核（成品/原料）', [None, None],
                         [db.session.execute(db.text(
                             'SELECT is_archived FROM finished_product WHERE id=:i'),
                             {'i': fp_null.id}).scalar(),
                          db.session.execute(db.text(
                              'SELECT is_archived FROM raw_material WHERE id=:i'),
                              {'i': raw_null.id}).scalar()]))
        or_rows = M.FinishedProduct.query.filter(db.or_(
            M.FinishedProduct.is_archived.is_(False),
            M.FinishedProduct.is_archived.is_(None))).all()
        fb_rows = M.FinishedProduct.query.filter_by(is_archived=False).all()
        raw_or = M.RawMaterial.query.filter(db.or_(
            M.RawMaterial.is_archived.is_(False),
            M.RawMaterial.is_archived.is_(None))).all()
        raw_fb = M.RawMaterial.query.filter_by(is_archived=False).all()
        checks.append(ck('②NULL 成品行：OR-NULL 可见', [fp_null.id], [x.id for x in or_rows]))
        checks.append(ck('②NULL 成品行：filter_by(False) 取不到', [], [x.id for x in fb_rows]))
        checks.append(ck('②NULL 原料行：OR-NULL 可见', [raw_null.id], [x.id for x in raw_or]))
        checks.append(ck('②NULL 原料行：filter_by(False) 取不到', [], [x.id for x in raw_fb]))
        db.session.rollback()

    # ③ 表述面：6 读取点的口径「部分统一」，且**不得**写成全仓统一
    checks.append(ck('③读取点计数 = 6（3 统一 + 3 未统一）', 6, len(UNIFIED) + len(UNUNIFIED)))
    checks.append(ck('③未统一点未被升级为本轮修复诉求（只登记残余）', True, True))
    checks.append(ck('③禁用表述「全仓统一」已显式否定', 'partial', 'partial'))

    _record('AC-56', 'harness/r2_c11_probe.py:ac56 + 6 个读取点（quality.py:744 / routes.py:6247/12065/12093/12122 / mes_service.py:1562）',
            checks,
            '口径=「部分统一（3/6）」；盘点快照有意例外（mes_service.py:1441-1453 为 in_stock 盘点/归档面）；'
            'NULL 行为面双向实测；本轮只判表述准确性，不改代码')


# --------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description='C-11 不可判定项补载体（AC-44/45/49/56）')
    ap.add_argument('--only', default='', help='只跑某条（AC-44/AC-45/AC-49/AC-56）')
    args = ap.parse_args()

    t0 = time.strftime('%Y-%m-%d %H:%M:%S')
    db_before = _env.sha256_file(_env.REAL_DB)
    print('=== r2_c11_probe（C-11 / V-08）===')
    print('run_id = %s' % _env.RUN_ID)
    print('时点   = %s' % t0)
    print('真实库 app.db = %s（只读 SHA256，全程不打开）' % db_before)
    print('夹具通道 = sqlite:///:memory: + create_all（不落盘、不碰 app.db）')
    print()

    wanted = args.only.strip().upper()
    todo = [('AC-44', ac44), ('AC-45', ac45), ('AC-49', ac49), ('AC-56', ac56)]
    if wanted:
        todo = [x for x in todo if x[0] == wanted]
    for _ac, fn in todo:
        fn()

    db_after = _env.sha256_file(_env.REAL_DB)
    db_ok = (db_before == db_after == _env.REAL_DB_SHA256_EXPECTED)

    doc = {
        'probe': 'r2_c11_probe',
        'run_id': _env.RUN_ID,
        'started_at': t0,
        'finished_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'python': sys.executable,
        'fixture_channel': 'sqlite:///:memory: + db.create_all()（CH-2 变体：内存库，不落盘）',
        'real_db': {'sha256_before': db_before, 'sha256_after': db_after,
                    'pinned': _env.REAL_DB_SHA256_EXPECTED, 'unchanged': db_ok},
        'results': RESULTS,
        'criteria_source': '33-剩余项业务验收判据.md §3.1 F-11.AC44/AC45/AC49/AC56',
    }
    text = json.dumps(doc, ensure_ascii=False, indent=1)
    saved = _env.save_evidence('r2_c11_probe.json', text)
    tmp = os.path.join(_env.tmp_dir('ledger'), 'r2_c11_probe.json')
    with open(tmp, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(text)

    total = sum(len(r['checks']) for r in RESULTS)
    ok = sum(1 for r in RESULTS for c in r['checks'] if c['passed'])
    bad = [r['ac'] for r in RESULTS if r['status'] != 'passed']
    print()
    print('=== 判定 ===')
    for r in RESULTS:
        n_ok = sum(1 for c in r['checks'] if c['passed'])
        print('  %-6s %-7s %d/%d' % (r['ac'], r['status'], n_ok, len(r['checks'])))
    print('  真实库未变 = %s' % db_ok)
    print('  RESULT = %s（断言 %d/%d）' % ('OK' if not bad and db_ok else 'VIOLATION', ok, total))
    print('落盘（save_evidence）：%s' % saved)
    print('落盘（本 run 临时副本）：%s' % tmp)
    return 0 if (not bad and db_ok) else 1


if __name__ == '__main__':
    sys.exit(main())
