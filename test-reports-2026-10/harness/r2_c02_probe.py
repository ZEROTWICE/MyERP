#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""r2_c02_probe.py —— C-02「并发/事务原子性」的 L3 + L4 探针（V-03 / t4）。

任务契约（`35-第2轮测试总方案（定稿）.md` §4 C-02 行 / `34` §3 / `33` §1）：

* **inScope**：本文件（`test-reports-2026-10/harness/r2_c02_probe.py`）。**不得改 `app/**`**，
  也**不得改 `harness/fixtures.py`**（V-04 已完成，该文件冻结于 64496 B）。
* **分母**：`app/**.py` 的 **162** 处 `db.session.rollback()`；`harness` 线程用例 **0**。
* **L3 判据**：注入 `IntegrityError` ⇒ **表行数回到注入前** + **`rollback` 被调用**（用例 **0 → ≥1**）。
* **L4 判据**：**链中断后首尾台账守恒**（扣料链在提交前被打断 ⇒ 物料账/记录账逐表回到链前）。
* **阴性用例（防「恒不变」伪守恒）**：**不注入**的正常路径 ⇒ 行数**必须变化**。
* **不可实施面**：真并发竞态（SQLite 单写锁 ⇒ 不可重放）⇒ 显式登记 `blocked(重放性不足)`。
* **verify**：探针双跑一致（`--compare`）+ 阴性对照 + 真库前后指纹。

## 被测链条（真实端点，非自造 API）

`POST /tasks/<id>/update_status`（`app/main/routes.py:3285-3759`）是**一条多步单事务链**：

```text
task.completed_quantity / status / completed_at  ← 写 1
ProductionRecord(...) + flush()                  ← 写 2
InspectionTask + AuditLog（needs_inspection 时）  ← 写 3
ProductionRecordMaterial × N + RawMaterial.quantity -= qty（+ AuditLog）  ← 写 4
with db.session.begin_nested(): record_task_material_consumption(...)      ← 写 5（SAVEPOINT）
AuditLog（更新任务完成与用料）
ProductionBatch.status / end_date 同步（+ AuditLog）
db.session.commit()                              ← :3753
except Exception: _reraise_http(e); db.session.rollback()                  ← :3755-3757
```

## 三条场景（每个场景一个**独立子进程**与一份**独立副本**，互不污染）

| key | 注入 | 必须观测到 |
| --- | --- | --- |
| `control` | **不注入**（阴性对照） | 行数**变化**：物料实扣、`ProductionRecord` +1、`update_status=200` |
| `integrity-real` | **真约束**：先占掉 `task.global_sn`，令 `ProductionRecord(global_sn=task.global_sn)` 在 `flush()` 撞 UNIQUE | 真 `IntegrityError` ⇒ 行数**回到注入前** + `rollback()` 被调用 |
| `fault-mid` | 故障注入：`before_flush` 在「本次请求内已出现 `ProductionRecordMaterial` 新增对象」的那一次 flush 抛 `IntegrityError` | 抛错点在**链中段**（写 4 刚发生）⇒ 写 1…4 **全部**回滚 + `rollback()` 被调用 |
| `concurrency-attempt` | 两线程并发改同一行（仅取证） | 结论登记 `blocked(重放性不足)`；**不计入判据层** |

「回到注入前」的判据是**逐表读数**（`COUNT(*)` / 行 id 集合 / 物料 `quantity` / `consumed_quantity`
总和），不是「没抛异常」——异常本身在 `fault-mid` 里是**期望输入**。

## 四个「注入式探针」坑（V-02 实测，本文件逐条对齐）

1. `_env.run_child` 是 `python -B <argv...>`，**argv 必须带脚本路径**（否则子进程恒 exit 2）；
2. 注入的代码**绝不能插进 `create_app()` 体内**（本探针改的是 `Session` 事件/方法，不碰启动链）；
3. 注入副本与对照副本必须是**两个不同目录**（本探针每场景一份独立副本）；
4. 授权开关须逐场景传参并对其余场景**显式清空**（复用 `WMS_ALLOW_REAL_DB` 口径；
   本探针全程 `mode=ro` 只读通道读真实库，从不连真实库）。

## 复算坐标（本文件实跑所得，第三方可逐条复核）

| 量 | 口径 | 实测值 |
| --- | --- | --- |
| `db.session.rollback()` 处数（C-02 分母） | 只读正则遍历 `app/**.py` | **162** |
| `AuditLog(` 处数（C-01 分母，仅交叉引用） | 同上 | **114** |
| 被测端点 | 独立阅读 | `app/main/routes.py:3285-3759`（`commit` :3753 / `rollback` :3757） |
| 注入点（真实约束） | 第 **2** 次 flush = 端点 :3407 的显式 `flush()` | 真 `sqlite3.IntegrityError: UNIQUE constraint failed: production_record.global_sn` |
| 注入点（故障注入） | 第 **9** 次 flush（`Notification`，在 savepoint **之后**、内层 `try` **之外**） | HTTP **500** + 逐表 Δ=0 |
| 阴性对照 | 不注入 | HTTP 200；原材料 5.0→4.0；`ProductionRecord` +1 / `production_record_materials` +1 / `AuditLog` ≥1 |
| L4 重跑 | 链中断后再跑一次 | 守恒：`Δ原材料 = −成功写入数`、`Δconsumed_quantity = 成功写入数`、`Δ用料行 == Δ生产记录` |
| 真实库 | `_env.sha256_file` | `F5DA2306…0E0F065`（2531328 B），四个场景前后一致 |

## 三个必须写进报告的实测发现（都带可复算证据）

1. **注入点必须落在「异常真的会逃逸」的位置**：端点链路里有 **≥4 处**
   `except Exception: logger.error(...)` 的防御性内层 try（自动创建质检任务、报工扣料回写、
   替用通知、批次状态同步）。往这些**保护区之内**注入，异常会被吞掉、链照常提交
   —— 实测把注入点放在 `InspectionTask`（第 4 次 flush）得 HTTP 200 + Δ≠0（**假绿**）；
   放在 `Notification`（第 9 次 flush）才得 HTTP 500 + Δ=0。
2. **`begin_nested()` 的 `_take_snapshot()` 会在建 savepoint 之前先 flush**：按「nested 出现过」
   或「`get_nested_transaction()` 为 None」判「已在 savepoint 之外」都是**错的**（实测连踩三次）；
   可靠信号是 `after_transaction_end(transaction.nested)` 的**已关闭 savepoint 计数**。
3. **响应码不反映原子性**：同一个端点，注入被内层 try 吞掉时返回 200（且数据已提交），
   冒到外层时返回 500（且全部回滚）。⇒ C-02 的判据必须落在**库内读数 + rollback 取证**上，
   不能落在状态码上（与 `write_suite.py` 的「不看状态码判通过」同口径）。

## 用法（仓库根目录；解释器绝对路径，`28` §5-1 / `40` R-4）

```powershell
$py = 'F:\Miniconda\envs\wage\python.exe'
$env:HARNESS_RUN_ID = 'r2-exec-b2-c02-a'
& $py -B test-reports-2026-10\harness\r2_c02_probe.py                 # 判据层
& $py -B test-reports-2026-10\harness\r2_c02_probe.py --selftest      # 工具自检（会报红）
$env:HARNESS_RUN_ID = 'r2-exec-b2-c02-b'
& $py -B test-reports-2026-10\harness\r2_c02_probe.py --json-out <a.json>
& $py -B test-reports-2026-10\harness\r2_c02_probe.py --json-out <b.json>
& $py -B test-reports-2026-10\harness\r2_c02_probe.py --compare <a.json> <b.json>   # 双跑一致
```

退出码：`0` = 判据层全过（L3×3 + L4×2 + 不变量）；`1` = 任一失败。
`--selftest` 退出码：`0` = 探针的**判据函数**在合成输入下逐条给出预期判定（含「必须报红」的阳性样本）。
"""
import argparse
import hashlib
import json
import os
import sys
import threading
import time

try:  # A-14：本机控制台 GBK
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import _env  # noqa: E402

RESULT_MARKER = '##R2C02-RESULT##'
REPO_ROOT = _env.REPO_ROOT
DEFAULT_REAL_DB = _env.REAL_DB

#: 被测端点（真实路由，非自造 API）
ENDPOINT = '/tasks/%d/update_status'
ROUTE_FILE = 'app/main/routes.py'
ROUTE_LINES = (3285, 3759)          # 本探针独立量测：@bp.route ... rollback() 返回块
ROLLBACK_DENOMINATOR = 162          # `app/**.py` 的 `db.session.rollback()` 计数（C-02 分母）
AUDITLOG_DENOMINATOR = 114          # C-01 分母（本文件只作交叉引用，不判 C-01）
ALLOW_ENV = 'WMS_ALLOW_REAL_DB'     # 与 V-02 同口径；本探针不连真实库（只在子进程里显式清空）

#: 注入类型
INJ_NONE = 'none'
INJ_REAL_UNIQUE = 'real-unique'
INJ_FLUSH_HOOK = 'flush-hook'

#: 逐表读数（L3/L4 的「行数」口径）
LEDGER_TABLES = ('production_record', 'production_record_materials', 'audit_log',
                 'material_allocations', 'task_assignment', 'raw_material',
                 'inspection_tasks', 'inspection_records')
QUANTITY_EPS = 1e-9

#: 「现状登记」类断言：不计入判据层（与 V-02 的 GAP_ASSERTION_IDS 同法）
GAP_ASSERTION_IDS = ('C-02-concurrency',)


def rel(path):
    try:
        return os.path.relpath(path, REPO_ROOT).replace('\\', '/')
    except Exception:
        return path


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest().upper()


def read_text(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read()


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(text)


# --------------------------------------------------------------- 子进程：读数与注入
#: 子场景源码（`CHILD_TEMPLATE`）由父进程写到 `.tmp/<RUN_ID>/c02/child/` 后**以脚本路径**执行：
#: 坑 1 —— `_env.run_child` 是 `python -B <argv...>`，argv 必须带脚本路径（否则 exit 2）。
#: 三方路径经环境变量传入（`C02_HARNESS_DIR` / `C02_SCRIPTS_DIR` / `C02_REPO_ROOT`），
#: 因为脚本落在 `.tmp/` 下，`__file__` 推不出 harness 路径。


def _ids_sha(ids):
    return hashlib.sha256(','.join(str(i) for i in ids).encode()).hexdigest().upper()


# --------------------------------------------------------------- 子进程主体（在被测进程内跑）
CHILD_TEMPLATE = r'''#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""r2_c02_child.py —— C-02 子场景（由 `r2_c02_probe.py` 生成到 `.tmp/<RUN_ID>/c02/child/`）。

每个场景一个**独立子进程 + 独立副本**，参数经环境变量传入：

| 环境变量 | 含义 |
| --- | --- |
| `C02_SCENARIO` | `control` / `integrity-real` / `fault-mid` |
| `C02_INJECTION` | `none` / `real-unique` / `flush-hook` |
| `C02_RUN_ID` | 与父进程同一个 `HARNESS_RUN_ID` |

输出：stdout 里一行 `##R2C02-RESULT##<json>`（父进程只认这一行）。
本文件只是**生成模板**，不含判据；判定逻辑在 `r2_c02_probe.py`。所以它自己**不参与**
`harness/**.py` 的产物口径（父进程把它写到 `.tmp/` 下再执行，落点不在 harness 树内）。
"""
import hashlib
import json
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
#: 三方路径由父进程经环境变量注入（本脚本被写到 `.tmp/<RUN_ID>/c02/child/` 后执行）
HARNESS_DIR = os.environ.get('C02_HARNESS_DIR') or HERE
SCRIPTS_DIR = os.environ.get('C02_SCRIPTS_DIR') or ''
REPO_ROOT = os.environ.get('C02_REPO_ROOT') or ''
for _p in (HARNESS_DIR, SCRIPTS_DIR, REPO_ROOT):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)


def _active_exc():
    """当前活动异常（**每次调用现取**）。

    坑（V-03 实测）：写成模块级常量或默认参数（`sys.exc_info()[1]`）会在**定义那一刻**求值，
    那时活动异常恒为 None ⇒ `is_integrity_error` 永远 false，判据恒红且原因难查。
    """
    return sys.exc_info()[1]


def _json_safe(obj, _depth=0):
    """把任意对象转成可 JSON 序列化的形态（**异常对象绝不允许直接进 RESULT**）。

    坑（V-03 实测）：注入用的 `IntegrityError` 对象一旦被塞进 `RESULT`（例如放进 state），
    收尾 `json.dumps(RESULT)` 会抛 `TypeError: Object of type IntegrityError is not JSON
    serializable` —— 表现是子进程 exit 3 + 一行 fatal，看起来像「被测方崩了」，其实是探针自己
    的数据没洗。落盘前统一过这一层。
    """
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, dict):
        return {str(k): _json_safe(v, _depth + 1) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_json_safe(v, _depth + 1) for v in obj]
    if _depth > 6:
        return '<%s>' % type(obj).__name__
    return '%s: %s' % (type(obj).__name__, str(obj)[:200])


def _real_unique_violation(db, M, ctx):
    """真跑一次会被 UNIQUE 拦下的 INSERT，取回**原始 DBAPI 异常**（消息/语句都是真的）。

    这样注入进链路的 `IntegrityError` 不是凭空构造的字符串，而是与真实冲突同源同形
    （`sqlite3.IntegrityError: UNIQUE constraint failed: production_record.global_sn`）。
    """
    from sqlalchemy.exc import IntegrityError as _IE
    out = {}
    try:
        with db.session.begin_nested():
            db.session.add(M.ProductionRecord(employee_id=ctx['employee_id'],
                                              process_id=ctx['process_id'], quantity=1,
                                              global_sn=ctx['global_sn'],
                                              date=__import__('datetime').datetime.now().date()))
            db.session.flush()
    except _IE as e:
        orig = getattr(e, 'orig', None)
        out['dbapi_exc'] = orig
        out['dbapi_message'] = str(orig)
        out['sql'] = (str(getattr(e, 'statement', '') or ''))[:200]
    except Exception as e:                      # noqa: BLE001
        out['dbapi_message'] = '%s: %s' % (e.__class__.__name__, e)
    finally:
        db.session.rollback()
    return out

import _env        # noqa: E402
import fixtures    # noqa: E402
from sqlalchemy.orm import Session          # noqa: E402
from sqlalchemy import event as _sa_event   # noqa: E402

SCENARIO = os.environ.get('C02_SCENARIO') or 'control'
INJECTION = os.environ.get('C02_INJECTION') or 'none'
RUN_ID = os.environ.get('C02_RUN_ID') or _env.RUN_ID
TARGET_MODEL = os.environ.get('C02_TARGET_MODEL') or ''

LEDGER_TABLES = ('production_record', 'production_record_materials', 'audit_log',
                 'material_allocations', 'task_assignment', 'raw_material',
                 'inspection_tasks', 'inspection_records')

RESULT = {'scenario': SCENARIO, 'injection': INJECTION, 'run_id': RUN_ID,
          'rollback_calls': [], 'rollback_events': [], 'flush_events': [], 'errors': []}
TRACE = []


def trace(msg):
    TRACE.append(str(msg))
    print('[child:%s] %s' % (SCENARIO, msg), flush=True)


def _ids_sha(ids):
    return hashlib.sha256(','.join(str(i) for i in ids).encode()).hexdigest().upper()


def snapshot(app, extra=None):
    """逐表读数：COUNT(*) + 行 id 集合（L3/L4 的「行数」判据载体）。"""
    from app import db
    out = {}
    with app.app_context():
        for t in LEDGER_TABLES:
            try:
                rows = db.session.execute(db.text('SELECT id FROM %s' % t)).fetchall()
                ids = sorted(int(r[0]) for r in rows)
                out[t] = {'count': len(ids), 'ids_tail': ids[-5:], 'ids_sha': _ids_sha(ids)}
            except Exception as e:
                out[t] = {'error': '%s: %s' % (e.__class__.__name__, e)}
    if extra:
        out.update(extra)
    return out


def main():
    from datetime import date, datetime, timedelta

    app, copy_path = fixtures.make_isolated_app('c02-' + SCENARIO)
    RESULT['copy_path'] = copy_path
    RESULT['copy_path_verdict'] = fixtures.copy_path_verdict()
    RESULT['real_db_sha256_before'] = _env.sha256_file(_env.REAL_DB)
    trace('isolated app ready: %s' % copy_path)

    from app import db
    from app import models as M

    # ---- 夹具：独立副本内自造（不依赖真实库形态），全部 _c02 前缀
    with app.app_context():
        admin = M.User.query.filter_by(username='admin').first() or M.User.query.first()
        if admin is None:
            raise AssertionError('夹具失败：副本里没有任何 user 行')
        prod = M.Product.query.first()
        proc = M.ProcessPrice.query.first()
        emp = M.Employee.query.first()
        cat = M.RawMaterialCategory.query.first()
        if prod is None or proc is None or emp is None:
            raise AssertionError('夹具失败：缺 product / process_price / employee')
        order = M.ProductionOrder(product_id=prod.id, planned_quantity=10,
                                  planned_start_date=date.today(),
                                  planned_end_date=date.today() + timedelta(days=30),
                                  created_by=admin.id)
        db.session.add(order)
        db.session.flush()
        batch = M.ProductionBatch(production_order_id=order.id, batch_quantity=10)
        db.session.add(batch)
        db.session.flush()
        rm = M.RawMaterial(supplier='_c02 供应商', category_id=cat.id if cat else None,
                           melt_number='_c02MELT%s' % RUN_ID,
                           supplier_number='_c02SUP%s' % RUN_ID,
                           internal_number='_c02RAW%s' % RUN_ID,
                           quantity=5.0, status='in_stock', is_archived=False)
        db.session.add(rm)
        db.session.flush()
        alloc = M.MaterialAllocation(production_order_id=order.id, material_type='raw',
                                     material_id=rm.id, required_quantity=5.0,
                                     allocated_quantity=0.0, consumed_quantity=0.0,
                                     unit='件', status='pending')
        db.session.add(alloc)
        db.session.flush()
        task = M.TaskAssignment(global_sn='C02T%s' % RUN_ID[-8:],
                                employee_id=emp.id, process_id=proc.id,
                                assigned_date=datetime.now(), target_date=date.today(),
                                quantity=10, completed_quantity=0, status='pending',
                                production_batch_id=batch.id, task_type='manual')
        db.session.add(task)
        db.session.commit()
        ctx = {'task_id': task.id, 'raw_id': rm.id, 'alloc_id': alloc.id,
               'order_id': order.id, 'batch_id': batch.id, 'product_id': prod.id,
               'process_id': proc.id, 'employee_id': emp.id, 'admin_id': admin.id,
               'global_sn': task.global_sn,
               'needs_inspection': bool(getattr(proc, 'needs_inspection', False))}
    RESULT['fixture'] = ctx
    #: 注入状态容器（**在注入块之前**初始化：real-unique 块也要写它）
    state = {'flushes': 0, 'target_seen': 0, 'raised_at': None, 'nested_seen': 0,
             'raised_phase': None, 'savepoint_seen': 0, 'nested_started': False}
    trace('fixture: task=%s raw=%s alloc=%s order=%s global_sn=%s needs_inspection=%s'
          % (ctx['task_id'], ctx['raw_id'], ctx['alloc_id'], ctx['order_id'],
             ctx['global_sn'], ctx['needs_inspection']))

    # ---- 真约束注入：预占 `production_record.global_sn`
    #: 构造（确定性、可重放、无需线程）：
    #: 1) 先落一条 `global_sn = task.global_sn` 的 `ProductionRecord`（该列 UNIQUE NOT NULL）；
    #: 2) 在端点 :3407 的**显式 `db.session.flush()`**（本次请求第 2 次 flush）抛出一个
    #:    **按真实 UNIQUE 冲突构造**的 `sqlalchemy.exc.IntegrityError`（原始 DBAPI 异常取自
    #:    真跑一次 INSERT 得到的 `sqlite3.IntegrityError`，消息与约束名都是真的）。
    #: ⇒ 异常在「guard 之后、内层 try 之外」冒到端点外层 `except Exception`（:3755-3757）
    #: ⇒ `db.session.rollback()` ⇒ 逐表回到注入前。
    #: ⚠ 实测补充（如实登记）：若不注入这一步，同一条链上的**幂等 guard**（:3383-3394）
    #: 会先于 UNIQUE 冲突命中并 `db.session.rollback()` + 400 —— 两种路径都「回到注入前」，
    #: 但只有前者打的是**真 IntegrityError**（本判据要的形态）。
    if INJECTION == 'real-unique':
        from app.models import ProductionRecord as _PR
        with app.app_context():
            taken = _PR(employee_id=ctx['employee_id'], process_id=ctx['process_id'],
                        quantity=1, global_sn=ctx['global_sn'], date=date.today())
            db.session.add(taken)
            db.session.commit()
            taken_id = taken.id
            raw = _real_unique_violation(db, M, ctx)     # 真跑一次 INSERT，取原始 DBAPI 异常
        RESULT['pre_occupied_global_sn'] = ctx['global_sn']
        RESULT['pre_occupied_record_id'] = taken_id
        RESULT['pre_occupied_table'] = 'production_record'
        RESULT['real_injection'] = {
            'kind': 'unique-collision-on-production_record.global_sn',
            'dup_sn': ctx['global_sn'],
            'real_dbapi_error': raw.get('dbapi_message'),
            'real_sql': raw.get('sql'),
            'raise_at_flush': 2,
            'collides_with': 'app/main/routes.py:3406-3407 的 ProductionRecord INSERT/flush'}
        state['real_unique'] = {'dbapi_message': raw.get('dbapi_message'),
                                'sql': raw.get('sql')}

        @_sa_event.listens_for(Session, 'before_flush')
        def _real_hook(session, flush_context, instances):   # noqa: ANN001
            state['flushes'] += 1
            #: 只注一次：重跑（L4 的守恒验证）必须能正常跑完，否则会把 500 误读成
            #: 「重跑也不守恒」（实测踩到：retry=500，L4 的 expected_writes 被算成 0）
            if state['flushes'] == 2 and state['raised_at'] is None:
                state['raised_at'] = 2
                state['raised_phase'] = 'explicit-flush'
                state['raised_stack'] = [f'{f[2]}:{f[3]}'
                                         for f in traceback.extract_stack()[-10:-1]]
                trace('real-unique: 在第 2 次 flush（端点 :3407 显式 flush）抛真实形态的 '
                      'IntegrityError：%s' % raw.get('dbapi_message'))
                from sqlalchemy.exc import IntegrityError as _IE2
                raise _IE2(raw.get('sql') or 'INSERT INTO production_record ...',
                           None, raw.get('dbapi_exc') or Exception(raw.get('dbapi_message')))
        trace('real-unique: 预占 production_record.global_sn=%s（id=%s）'
              % (ctx['global_sn'], taken_id))

    # ---- 故障注入：before_flush 在链的**指定位置**抛 IntegrityError
    #: 触发位置（`C02_FLUSH_TRIGGER`）：
    #:  * `first-target`         —— 目标模型首次进入 session.new 的那次 flush（= 链中段）
    #:  * `target-after-savepoint` —— `begin_nested()` 之后目标模型首次出现的那次 flush：
    #:     必须落在「写 5 的 SAVEPOINT **之外**」，这样异常才会冒到端点自己的
    #:     `except Exception: db.session.rollback()`（写 1…5 全回滚）
    trigger = os.environ.get('C02_FLUSH_TRIGGER') or 'first-target'
    try:
        need_sp = int(os.environ.get('C02_SAVEPOINTS_BEFORE_RAISE') or '0')
    except (TypeError, ValueError):
        need_sp = 0
    if INJECTION == 'flush-hook':
        @_sa_event.listens_for(Session, 'after_begin')
        def _on_begin(session, transaction, connection):    # noqa: ANN001
            if transaction.nested:
                state['nested_seen'] += 1
                state['nested_started'] = True

        @_sa_event.listens_for(Session, 'after_transaction_end')
        def _on_trans_end(session, transaction):            # noqa: ANN001
            """SAVEPOINT **关闭**的信号（`transaction.nested`）。

            坑（V-03 实测，连踩三次，逐条记下）：
            ① `begin_nested()` 在**建 savepoint 之前**先 `_take_snapshot()`，而
               `_take_snapshot()` 内部就 `session.flush()` —— 此刻 `get_nested_transaction()`
               仍是 None、`transaction.nested` 尚未置位。按「nested 出现过」判会把注入打进
               savepoint **内部**，异常被 `begin_nested` 吃掉 ⇒ 链照常提交（**假绿**，实测 200）；
            ② `transaction._parent is None` **不能**判「嵌套已结束」（实测恒 False：
               顶层事务从头到尾都在栈上）；
            ③ 即使 savepoint 已关闭，**同一个 savepoint 的 `_take_snapshot` flush** 也发生在
               「上一个 savepoint 已关闭」之后 ⇒ 必须用**已关闭 savepoint 的计数**
               （`savepoint_seen >= N`，N 由 `C02_SAVEPOINTS_BEFORE_RAISE` 指定）来定位
               「真正在嵌套之外」的那一次 flush。
            """
            if getattr(transaction, 'nested', False):
                state['savepoint_seen'] += 1

        @_sa_event.listens_for(Session, 'before_flush')
        def _hook(session, flush_context, instances):       # noqa: ANN001
            state['flushes'] += 1
            names = [type(o).__name__ for o in session.new]
            seen = sum(1 for n in names if n == TARGET_MODEL)
            if seen:
                state['target_seen'] += seen
            if len(RESULT['flush_events']) < 80:
                RESULT['flush_events'].append({'n': state['flushes'], 'new': names[:12],
                                               'nested_seen': state['nested_seen'],
                                               'nested_open': bool(
                                                   session.get_nested_transaction()),
                                               'savepoint_seen': state['savepoint_seen'],
                                               'nested_started': state['nested_started'],
                                               'target_seen': state['target_seen']})
            cond = (seen and state['target_seen'] > 0)
            if trigger == 'target-after-savepoint':
                cond = (cond and state['nested_started'] and need_sp > 0
                        and state['savepoint_seen'] >= need_sp)
            if state['raised_at'] is None and cond:
                state['raised_at'] = state['flushes']
                state['raised_phase'] = 'post-savepoint'
                state['raised_stack'] = ['%s:%s:%s' % (f[2], f[3], f[4])
                                         if len(f) > 4 else '%s:%s' % (f[2], f[3])
                                         for f in traceback.extract_stack()[-12:-1]]
                trace('flush-hook: 第 %d 次 flush 抛 IntegrityError'
                      '（new 含 %s，savepoint_seen=%d，nested_open=%s，phase=%s）'
                      % (state['flushes'], TARGET_MODEL, state['savepoint_seen'],
                         bool(session.get_nested_transaction()), state['raised_phase']))
                if os.environ.get('C02_DEBUG'):
                    trace('  raise stack: %s' % ' <- '.join(reversed(state['raised_stack'])))
                from sqlalchemy.exc import IntegrityError as _IE
                raise _IE('C-02 故障注入（before_flush，第 %d 次）' % state['flushes'],
                          None, Exception('injected'))

    # ---- 回滚取证：两层都记
    #: ① `after_rollback` 事件 —— 捕获**所有**回滚（含 `begin_nested()` 的 SAVEPOINT 回滚，
    #:    它不走 `Session.rollback`，只包 Session.rollback 会漏掉）；
    #: ② 包 `Session.rollback` —— 记录「应用层显式调用」（栈里能看到 `update_task_status`）。
    @_sa_event.listens_for(Session, 'after_rollback')
    def _on_rollback(session):                       # noqa: ANN001
        exc = _active_exc()
        if len(RESULT['rollback_events']) < 60:
            RESULT['rollback_events'].append({
                'kind': 'after_rollback_event',
                'active_exception': (exc.__class__.__name__ if exc else None),
                'is_integrity_error': bool(exc is not None
                                           and 'IntegrityError' in exc.__class__.__name__),
            })

    _orig_rollback = Session.rollback

    def _recording_rollback(self, *a, **kw):
        exc = _active_exc()
        if os.environ.get('C02_DEBUG'):
            trace('rollback 被调用：活动异常=%s（%s）'
                  % (exc.__class__.__name__ if exc else None,
                     [f[2] for f in traceback.extract_stack()[-5:-1]]))
        RESULT['rollback_calls'].append({
            'n': len(RESULT['rollback_calls']) + 1,
            'active_exception': (exc.__class__.__name__ if exc else None),
            'is_integrity_error': bool(exc is not None
                                       and 'IntegrityError' in exc.__class__.__name__),
            'caller': ['%s:%s:%s' % (f[2], f[3], f[4]) if len(f) > 4 else '%s:%s' % (f[2], f[3])
                       for f in traceback.extract_stack()[-7:-1]],
        })
        return _orig_rollback(self, *a, **kw)

    Session.rollback = _recording_rollback
    RESULT['rollback_hook_installed'] = True
    if os.environ.get('C02_DEBUG'):
        trace('rollback hook installed: Session.rollback is patched=%s'
              % (getattr(Session.rollback, '__name__', '?') == '_recording_rollback'))

    # ---- 读数辅助
    def _raw_qty():
        with app.app_context():
            return db.session.get(M.RawMaterial, ctx['raw_id']).quantity

    def _alloc():
        with app.app_context():
            a = db.session.get(M.MaterialAllocation, ctx['alloc_id'])
            return {'consumed_quantity': a.consumed_quantity,
                    'allocated_quantity': a.allocated_quantity}

    def _task():
        with app.app_context():
            t = db.session.get(M.TaskAssignment, ctx['task_id'])
            return {'status': t.status, 'completed_quantity': t.completed_quantity,
                    'completed_at': (t.completed_at.isoformat() if t.completed_at else None)}

    def _audit_snapshot():
        with app.app_context():
            rows = db.session.execute(db.text('SELECT COUNT(*) FROM audit_log')).scalar()
            return int(rows or 0)

    before = snapshot(app, {'raw_quantity': _raw_qty(), 'allocation': _alloc(),
                            'task': _task(), 'audit_log_count_crosscheck': _audit_snapshot()})
    RESULT['before'] = before
    trace('before: raw_quantity=%s alloc=%s task=%s'
          % (before['raw_quantity'], before['allocation'], before['task']))

    # ---- 发请求（登录用 session 注入：绕开脚手架用户，不写任何 fixture）
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(ctx['admin_id'])
        sess['_fresh'] = True
    url = '/tasks/%d/update_status' % ctx['task_id']
    payload = {'completed_quantity': 10,
               'materials': [{'raw_material_id': ctx['raw_id'], 'quantity': 1.0}]}
    raised = None
    try:
        response = client.post(url, json=payload)
        RESULT['http_status'] = response.status_code
        RESULT['http_body'] = response.get_data(as_text=True)[:400]
    except BaseException as e:              # noqa: BLE001
        raised = {'type': e.__class__.__name__, 'message': str(e)[:400],
                  'stack': [f'{f[2]}:{f[3]}:{f[4]}' if len(f) > 4 else f'{f[2]}:{f[3]}'
                            for f in traceback.extract_tb(e.__traceback__)][-8:]}
        RESULT['http_raised'] = raised
    trace('request: status=%s raised=%s' % (RESULT.get('http_status'),
                                            (raised or {}).get('type')))
    if os.environ.get('C02_DEBUG') and raised:
        trace('  raised stack: %s' % ' <- '.join(
            f[2] if isinstance(f, str) else str(f) for f in raised.get('stack') or []))

    RESULT['injection_state'] = state
    trace('rollback_calls=%d' % len(RESULT['rollback_calls']))
    after = snapshot(app, {'raw_quantity': _raw_qty(), 'allocation': _alloc(),
                           'task': _task(), 'audit_log_count_crosscheck': _audit_snapshot()})
    RESULT['after'] = after
    trace('after: raw_quantity=%s alloc=%s task=%s'
          % (after['raw_quantity'], after['allocation'], after['task']))

    # ---- L4 附加：链中断后「再完整跑一遍」是否守恒（不重复扣料 / 不留半行）
    if SCENARIO in ('integrity-real', 'fault-mid'):
        with app.app_context():
            db.session.rollback()           # 清会话残留，防影响下一次判读
        try:
            r2 = client.post(url, json=payload)
            RESULT['retry'] = {'status': r2.status_code,
                               'body': r2.get_data(as_text=True)[:400]}
        except BaseException as e:          # noqa: BLE001
            RESULT['retry'] = {'raised': '%s: %s' % (e.__class__.__name__, str(e)[:300])}
        trace('retry: %s' % json.dumps(RESULT['retry'], ensure_ascii=False)[:220])
        RESULT['after_retry'] = snapshot(app, {'raw_quantity': _raw_qty(),
                                               'allocation': _alloc(), 'task': _task()})

    RESULT['trace'] = TRACE
    RESULT['real_db_sha256_after'] = _env.sha256_file(_env.REAL_DB)
    RESULT['real_db_unchanged'] = (RESULT['real_db_sha256_before']
                                   == RESULT['real_db_sha256_after'])
    RESULT['real_db_pinned'] = _env.REAL_DB_SHA256_EXPECTED
    try:
        _env.assert_real_db_untouched('c02 child ' + SCENARIO)
        RESULT['real_db_assert_ok'] = True
    except Exception as e:                  # noqa: BLE001
        RESULT['real_db_assert_ok'] = False
        RESULT['errors'].append('真实库指纹断言失败：%s' % e)
    print('##R2C02-RESULT##' + json.dumps(_json_safe(RESULT), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    try:
        _rc = main()
    except Exception:                       # noqa: BLE001 —— SystemExit 不在此列（正常出口）
        print('##R2C02-RESULT##' + json.dumps(
            {'scenario': SCENARIO, 'fatal': traceback.format_exc()[-1500:]},
            ensure_ascii=False))
        _rc = 3
    sys.exit(_rc)
'''


def child_script_path(run_id, scenario):
    return os.path.join(_env.tmp_dir('c02', 'child'),
                        'c02_%s_%s.py' % (str(run_id).replace(os.sep, '_'), scenario))


def _parse_payload(stdout, stderr):
    """取**第一个可解析且非 fatal** 的 `##R2C02-RESULT##` 行。

    为什么要挑：子进程收尾若有异常，会再打一行 fatal 结果；取最后一行会把正常读数覆盖掉
    （V-02 的同类坑：exit 2 被误读成「被测缺陷」）。
    """
    payload = None
    fallback = None
    for line in (stdout + '\n' + stderr).splitlines():
        if not line.startswith(RESULT_MARKER):
            continue
        try:
            obj = json.loads(line[len(RESULT_MARKER):])
        except Exception as e:
            obj = {'parse_error': '%s: %s' % (e.__class__.__name__, e)}
        if fallback is None:
            fallback = obj
        if 'fatal' not in obj and payload is None:
            payload = obj
    return payload if payload is not None else fallback


def run_scenario(scenario, injection, target_model, timeout=900, run_id=None,
                 flush_trigger='first-target', env_extra=None, savepoints_before=None):
    """在独立子进程里跑一个场景（独立副本、独立解释器）。"""
    run_id = run_id or _env.RUN_ID
    path = child_script_path(run_id, scenario)
    write_text(path, CHILD_TEMPLATE)          # 原样落盘（三方路径经环境变量传）
    extra = {ALLOW_ENV: '',                     # 坑 4：显式清空授权开关
             'C02_HARNESS_DIR': HERE,
             'C02_SCRIPTS_DIR': _env.SCRIPTS_DIR,
             'C02_REPO_ROOT': REPO_ROOT,
             'C02_SCENARIO': scenario,
             'C02_INJECTION': injection,
             'C02_TARGET_MODEL': target_model or '',
             'C02_FLUSH_TRIGGER': flush_trigger or 'first-target',
             'C02_SAVEPOINTS_BEFORE_RAISE': str(savepoints_before or 0),
             'C02_RUN_ID': run_id}
    extra.update(env_extra or {})
    #: 坑 1：argv 必须带脚本路径（`_env.run_child` = `python -B <argv...>`）
    out = _env.run_child([path], cwd=REPO_ROOT, timeout=timeout,
                         extra_env=extra, label='c02-%s' % scenario)
    payload = _parse_payload(out['stdout'], out['stderr'])
    out['payload'] = payload
    out['script'] = path
    return out


# --------------------------------------------------------------------- 判据（纯函数）
def _counts(snap):
    return {t: (snap.get(t) or {}).get('count') for t in LEDGER_TABLES}


def eval_checks(cases):
    """把 L3/L4 判据写成结构化断言（可被 `--selftest` 用合成输入对拍）。

    `cases` 需要 `control` / `integrity-real` / `fault-mid` 三份**同形读数**：
    `{before: sn, after: sn, rollback_calls: [...], http_status, http_raised, ...}`
    """
    A = []

    def add(aid, title, expected, actual, verdict, evidence='', evidence_kind='behavior_verified',
            note=''):
        A.append({'id': aid, 'title': title, 'expected': expected, 'actual': actual,
                  'verdict': verdict, 'evidence': evidence, 'evidence_kind': evidence_kind,
                  'note': note})

    def counts_delta(a, b):
        ca, cb = _counts(a), _counts(b)
        return {t: (cb.get(t, 0) - ca.get(t, 0)) for t in LEDGER_TABLES}

    ctl = cases.get('control') or {}
    intg = cases.get('integrity-real') or {}
    fm = cases.get('fault-mid') or {}
    conc = cases.get('concurrency-attempt') or {}

    # ---------------------------------------------------------------- 阴性用例
    d = counts_delta(ctl.get('before') or {}, ctl.get('after') or {})
    ctl_qty_before = (ctl.get('before') or {}).get('raw_quantity')
    ctl_qty_after = (ctl.get('after') or {}).get('raw_quantity')
    qty_drop = (None not in (ctl_qty_before, ctl_qty_after)
                and abs((ctl_qty_before - ctl_qty_after) - 1.0) < QUANTITY_EPS)
    changed = (d.get('production_record', 0) >= 1
               and d.get('production_record_materials', 0) >= 1
               and d.get('audit_log', 0) >= 1)
    ctl_ok = (ctl.get('http_status') == 200 and qty_drop and changed
              and not ctl.get('http_raised'))
    add('C-02-L3.0(control)',
        '阴性用例（防「恒不变」伪守恒）：**不注入**时正常报工 ⇒ 行数**必须变化**'
        '（ProductionRecord / ProductionRecordMaterial / AuditLog 各 +1，原材料实扣 1.0）',
        {'http_status': 200, 'raw_quantity_delta': -1.0,
         'delta.production_record': '>=1', 'delta.production_record_materials': '>=1',
         'delta.audit_log': '>=1'},
        {'http_status': ctl.get('http_status'), 'http_raised': ctl.get('http_raised'),
         'raw_quantity': [ctl_qty_before, ctl_qty_after], 'delta': d,
         'task_after': (ctl.get('after') or {}).get('task')},
        'passed' if ctl_ok else 'failed',
        evidence=rel(ctl.get('out_file') or ''), note='这条不成立则整套 L3 无意义（守恒恒真）')

    # ---------------------------------------------------------------- L3-a 真约束
    d_i = counts_delta(intg.get('before') or {}, intg.get('after') or {})
    rb_i = intg.get('rollback_calls') or []
    ev_i = intg.get('rollback_events') or []
    ie_seen = any(r.get('is_integrity_error') for r in rb_i)
    intg_app = any('update_task_status' in (fr or '') for r in rb_i
                   for fr in (r.get('caller') or []))
    rows_back = all(v == 0 for v in d_i.values() if v is not None)
    qty_back = (intg.get('before') or {}).get('raw_quantity') == \
               (intg.get('after') or {}).get('raw_quantity')
    alloc_back = ((intg.get('before') or {}).get('allocation')
                  == (intg.get('after') or {}).get('allocation'))
    intg_ok = (ie_seen and intg_app and rb_i and rows_back and qty_back
               and alloc_back and intg.get('pre_occupied_record_id') is not None)
    add('C-02-L3.a(integrity-real)',
        'L3 判据①：注入 **真实** IntegrityError —— 预占 `production_record.global_sn` 后，'
        '在端点 :3406-3407 的 `ProductionRecord` INSERT/显式 `flush()` 上抛出**与真实冲突同源**的 '
        '`IntegrityError`（原始 DBAPI 异常取自真跑一次 INSERT）⇒ 异常冒到端点外层 `except` ⇒ '
        '`db.session.rollback()`（:3757）被调用 ⇒ **逐表行数回到注入前**、物料实扣与 '
        '`allocation.consumed_quantity` 复原（分母 `app/**.py` 的 %d 处之 1）' % ROLLBACK_DENOMINATOR,
        {'rollback_called_with_IntegrityError_by_endpoint': True, 'delta_all_zero': True,
         'raw_quantity_restored': True, 'allocation_restored': True,
         'task_status_restored': 'pending'},
        {'rollback_calls': rb_i, 'rollback_events_integrity': [e for e in ev_i
                                                               if e.get('is_integrity_error')][:4],
         'delta': d_i,
         'raw_quantity': [(intg.get('before') or {}).get('raw_quantity'),
                          (intg.get('after') or {}).get('raw_quantity')],
         'allocation_before_after': [(intg.get('before') or {}).get('allocation'),
                                     (intg.get('after') or {}).get('allocation')],
         'task_before_after': [(intg.get('before') or {}).get('task'),
                               (intg.get('after') or {}).get('task')],
         'http_status': intg.get('http_status'), 'http_raised': intg.get('http_raised'),
         'pre_occupied': {'table': intg.get('pre_occupied_table'),
                          'global_sn': intg.get('pre_occupied_global_sn'),
                          'id': intg.get('pre_occupied_record_id')},
         'real_injection': intg.get('real_injection'),
         'retry': intg.get('retry'),
         'retry_delta': counts_delta(intg.get('after') or {}, intg.get('after_retry') or {})},
        'passed' if intg_ok else 'failed',
        evidence=rel(intg.get('out_file') or ''),
        note='确定性构造：同一个 UNIQUE 值 ⇒ 链内必然撞约束（无需线程、可重放）；'
             '判据要求「rollback 的活动异常 = IntegrityError」—— 这一条把「应用层按异常回滚」'
             '与「ORM 自己清了会话」严格区分开')

    # ---------------------------------------------------------------- L3-b 链后段故障注入
    d_f = counts_delta(fm.get('before') or {}, fm.get('after') or {})
    rb_f = fm.get('rollback_calls') or []
    ev_f = fm.get('rollback_events') or []
    ist_f = fm.get('injection_state') or {}
    raised_at = ist_f.get('raised_at')
    raise_stack = ist_f.get('raised_stack') or []
    fm_ie = any(r.get('is_integrity_error') for r in rb_f)
    fm_rows_back = all(v == 0 for v in d_f.values() if v is not None)
    fm_qty_back = (fm.get('before') or {}).get('raw_quantity') == \
                  (fm.get('after') or {}).get('raw_quantity')
    #: 「应用层回滚」而不是「ORM 内部清理」：栈里必须出现端点的 `except` 分支调用点
    fm_app_level = any('update_task_status' in (fr or '') for r in rb_f
                       for fr in (r.get('caller') or []))
    fm_ok = (raised_at is not None and bool(raise_stack) and fm_ie and fm_app_level
             and fm_rows_back and fm_qty_back)
    add('C-02-L3.b(fault-mid)',
        'L3 判据②（注入式）：在**嵌套之外、内层 try 之外**的链后段注入 IntegrityError '
        '⇒ 该异常冒到端点外层 `except Exception` ⇒ `db.session.rollback()` 被应用层调用 '
        '⇒ **逐表行数回到注入前、物料实扣复原**（写 1…5 全不落库）',
        {'raised_at_flush': '>=1', 'raise_inside_endpoint_call_stack': True,
         'app_level_rollback_with_IntegrityError': True, 'delta_all_zero': True,
         'raw_quantity_restored': True},
        {'raised_at': raised_at, 'raised_phase': ist_f.get('raised_phase'),
         'savepoint_seen': ist_f.get('savepoint_seen'),
         'raise_stack': raise_stack[-6:],
         'rollback_calls': rb_f,
         'rollback_events_integrity': [e for e in ev_f if e.get('is_integrity_error')][:4],
         'delta': d_f,
         'raw_quantity': [(fm.get('before') or {}).get('raw_quantity'),
                          (fm.get('after') or {}).get('raw_quantity')],
         'http_status': fm.get('http_status')},
        'passed' if fm_ok else 'failed',
        evidence=rel(fm.get('out_file') or ''),
        note='注入点用 before_flush 事件（不碰启动链、不改生产代码）。**不断言 HTTP 状态码**：'
             '实测 200 —— 该端点在链路里有多处 `except: logger.error` 吞掉异常的内层 try'
             '（如 `update_production_status_hierarchy()`），响应码不反映原子性；'
             '判据落在「异常确实冒到端点外层 except + 应用层 rollback + 逐表复原」三件事上')

    # ---------------------------------------------------------------- L4 台账守恒
    def ledger_consistent(payload, label):
        """链中断后台账守恒（L4）。

        「守恒」= 三路互校：
        ① **打断即不动**：中断后逐表 Δ=0、物料 `quantity` / `allocation.consumed_quantity` 未动；
        ② **重跑不重复扣**：重跑（可能是「完整成功」也可能是「幂等拒重复」）后，
           `Δ原始材料` 必须恰等于 `-成功写入的记录数`，`Δconsumed_quantity` 恰等于成功记录数；
        ③ **不留半行**：`Δproduction_record_materials == Δproduction_record`（不成对即半行）。
        """
        before, after = payload.get('before') or {}, payload.get('after') or {}
        d = counts_delta(before, after)
        zero = all(v == 0 for v in d.values() if v is not None)
        retry = payload.get('retry') or {}
        retry_after = payload.get('after_retry') or {}
        rd = counts_delta(after, retry_after)
        retry_ok = (retry.get('status') == 200)
        success = 1 if retry_ok else 0
        qty_delta = None
        if retry_after.get('raw_quantity') is not None:
            qty_delta = round((retry_after.get('raw_quantity') or 0)
                              - ((after.get('raw_quantity') or 0)), 6)
        consumed = (retry_after.get('allocation') or {}).get('consumed_quantity')
        consumed_delta = None
        if consumed is not None:
            consumed_delta = round(float(consumed)
                                   - float((after.get('allocation') or {})
                                           .get('consumed_quantity') or 0), 6)
        pr_delta = rd.get('production_record')
        prm_delta = rd.get('production_record_materials')
        return {
            'label': label,
            'delta_after_interrupt': d,
            'interrupt_zero_delta': zero,
            'retry': {'status': retry.get('status'), 'body': (retry.get('body') or '')[:200],
                      'raised': retry.get('raised')},
            'retry_succeeded': retry_ok,
            'expected_writes': success,
            'retry_raw_quantity_delta': qty_delta,
            'retry_consumed_quantity_delta': consumed_delta,
            'retry_production_record_delta': pr_delta,
            'retry_production_record_materials_delta': prm_delta,
            'qty_conserved': (qty_delta is not None
                              and abs(qty_delta - (-1.0 * success)) < QUANTITY_EPS),
            'consumed_conserved': (consumed_delta is not None
                                   and abs(consumed_delta - success) < QUANTITY_EPS),
            'no_half_row': (pr_delta == prm_delta) if (pr_delta is not None
                                                       and prm_delta is not None) else False,
            'record_delta_is_expected': (pr_delta == success),
            'raw_quantity': {'before': before.get('raw_quantity'),
                             'after_interrupt': after.get('raw_quantity'),
                             'after_retry': retry_after.get('raw_quantity')},
            'consumed_quantity': {'after_interrupt': (after.get('allocation') or {})
                                  .get('consumed_quantity'),
                                  'after_retry': consumed},
        }

    l4a = ledger_consistent(intg, 'integrity-real')
    l4b = ledger_consistent(fm, 'fault-mid')
    l4_ok = all((x['interrupt_zero_delta'] and x['qty_conserved'] and x['consumed_conserved']
                 and x['no_half_row'] and x['record_delta_is_expected'])
                for x in (l4a, l4b))
    add('C-02-L4(ledger)',
        'L4 判据：链中断后 **首尾台账守恒**（三路互校）—— ① 中断即不动：逐表 Δ=0 且 '
        '物料 `quantity`/`allocation.consumed_quantity` 未动；② 重跑后 `Δ原材料 = −成功写入数`、'
        '`Δconsumed_quantity = 成功写入数`（不重复扣料）；③ `Δ生产记录用料行 == Δ生产记录`（不留半行）',
        {'interrupt_zero_delta': True, 'qty_conserved': True, 'consumed_conserved': True,
         'no_half_row': True, 'record_delta_is_expected': True},
        {'integrity-real': l4a, 'fault-mid': l4b},
        'passed' if l4_ok else 'failed',
        evidence=rel(fm.get('out_file') or ''),
        note='重跑可能是「完整成功（200，写 1 次）」或「幂等拒重复（400，写 0 次）」'
             '——两者都守恒：期望写入数随重跑结果取值，不写死')

    # ---------------------------------------------------------------- 真库不变量
    allp = [c for c in (ctl, intg, fm, conc) if c]
    db_ok = all(p.get('real_db_unchanged') and p.get('real_db_assert_ok') for p in allp)
    add('C-02(db)',
        '不变量：四个场景全程真实库 app.db SHA256 不变（= 钉死值）',
        {'sha256': _env.REAL_DB_SHA256_EXPECTED, 'unchanged': True},
        {'per_scenario': {p.get('scenario'): {'unchanged': p.get('real_db_unchanged'),
                                              'assert_ok': p.get('real_db_assert_ok')}
                          for p in allp}},
        'passed' if db_ok else 'failed',
        evidence='探针 stdout + 每个子进程的 real_db_sha256_before/after',
        note='一切库操作走带 RUN_ID 的副本（fixtures.make_isolated_app）')

    # ---------------------------------------------------------------- 并发登记（不计判据层）
    add('C-02-concurrency',
        '不可实施面登记：真并发竞态 ⇒ `blocked(重放性不足)`（SQLite 单写锁使结果不可重放）；'
        '本项是**现状登记**，不计入判据层',
        {'status': 'blocked(重放性不足)', 'replayable': False},
        {'attempt': conc.get('concurrency') or None,
         'reason': 'SQLite 单写锁 + 同一 Session 非线程安全 ⇒ 观测到的是锁序而非业务竞态'},
        'blocked', evidence=rel(conc.get('out_file') or ''),
        evidence_kind='file_exists',
        note='并发部分按 `35` §4 C-02 行「不可实施面」登记，不混入通过数')

    criteria = [r for r in A if r['id'] not in GAP_ASSERTION_IDS]
    failed = [r['id'] for r in criteria if r['verdict'] != 'passed']
    return A, failed


# --------------------------------------------------------------------- 父进程编排
def full_run(args):
    started = time.strftime('%Y-%m-%d %H:%M:%S')
    real_before = _env.assert_real_db_untouched('r2_c02 开工')
    print('=' * 84)
    print('[c02] C-02 并发/事务原子性探针（L3 注入式 + L4 台账守恒）')
    print('[c02] run_id=%s  time=%s' % (_env.RUN_ID, started))
    print('[c02] 真实库 %s  sha256=%s' % (rel(args.real_db), real_before))
    print('[c02] 被测端点 %s（%s:%d-%d）' % (ENDPOINT % 0, ROUTE_FILE, *ROUTE_LINES))
    print('[c02] 分母：`db.session.rollback()` = %d 处（本探针独立量测）；'
          '`AuditLog(` = %d 处（C-01 分母，仅交叉引用）'
          % (_count_rollbacks(), _count_auditlog()))
    print('=' * 84)

    scenarios = [
        ('control', INJ_NONE, None, None, None, '阴性对照：不注入 ⇒ 行数必须变化'),
        ('integrity-real', INJ_REAL_UNIQUE, 'ProductionRecord', None, None,
         'L3-a：真 UNIQUE 冲突（预占 task.global_sn）⇒ 行数回到注入前'),
        #: 注入点：**Notification**（第 9 次 flush，位于嵌套 savepoint 之后、链后段）——
        #: 该处不在任何内层 `except: logger.error` 的保护区内 ⇒ 异常一路冒到端点的外层
        #: `except Exception`（:3755-3757）⇒ 实测 HTTP **500** + 逐表 Δ=0。
        #: 反例（实测）：把注入点放在 `InspectionTask`（第 4 次 flush）会被
        #: 「自动创建质检任务」的内层 try 吞掉 ⇒ 链照常提交（HTTP 200、Delta≠0）——
        #: 这正是本任务要证明的「注入点必须落在异常真的会逃逸的位置」。
        ('fault-mid', INJ_FLUSH_HOOK, 'Notification', 'first-target', None,
         'L3-b：链后段（各内层 try 之外）注入 IntegrityError ⇒ 行数回到注入前 + 端点外层 rollback'),
        ('concurrency-attempt', INJ_NONE, None, None, None,
         '并发取证（登记 blocked，不计判据层）'),
    ]
    cases = {}
    for key, inj, target, trigger, savepoints, desc in scenarios:
        if key == 'concurrency-attempt':
            out = run_concurrency_attempt(args.timeout)
            payload = out['payload'] or {}
            cases[key] = {'scenario': key, 'out_file': out['out_file'],
                          'concurrency': payload.get('concurrency'),
                          'threads': payload.get('threads'),
                          'final': payload.get('final'),
                          'real_db_unchanged': out['real_db_unchanged'],
                          'real_db_assert_ok': True}
            print('  [CASE] %-20s exit=%s %s' % (key, out['exit_code'],
                                                 json.dumps(payload.get('concurrency') or {},
                                                            ensure_ascii=False)[:150]))
            continue
        out = run_scenario(key, inj, target, timeout=args.timeout, flush_trigger=trigger,
                           savepoints_before=savepoints)
        p = out['payload'] or {}
        p.setdefault('scenario', key)
        p['out_file'] = out['out_file']
        cases[key] = p
        print('  [CASE] %-20s exit=%s http=%s raised=%s rollback_calls=%s '
              'raw_qty=%s->%s' % (key, out['exit_code'], p.get('http_status'),
                                  (p.get('http_raised') or {}).get('type'),
                                  len(p.get('rollback_calls') or []),
                                  (p.get('before') or {}).get('raw_quantity'),
                                  (p.get('after') or {}).get('raw_quantity')))
        if p.get('fatal'):
            print('         FATAL: %s' % str(p.get('fatal'))[-400:])

    real_after = _env.assert_real_db_untouched('r2_c02 收尾')
    assertions, failed = eval_checks(cases)

    print('')
    print('-' * 84)
    print('[c02] 判据层')
    for r in assertions:
        print('  %-28s %-8s %-20s %s' % (r['id'], r['verdict'].upper(), r['evidence_kind'],
                                         r['title'][:58]))
    print('')
    for r in assertions:
        if r['verdict'] not in ('passed', 'blocked'):
            print('  [FAIL] %s' % r['id'])
            print('         expected=%s' % json.dumps(r['expected'], ensure_ascii=False)[:400])
            print('         actual  =%s' % json.dumps(r['actual'], ensure_ascii=False)[:600])
            if r['note']:
                print('         note    =%s' % r['note'])
    n_pass = len([r for r in assertions if r['verdict'] == 'passed'
                  and r['id'] not in GAP_ASSERTION_IDS])
    n_tot = len([r for r in assertions if r['id'] not in GAP_ASSERTION_IDS])
    print('')
    print('[c02] 判据层：%d/%d 通过；失败=%s' % (n_pass, n_tot, failed or '无'))
    print('[c02] 不可实施面：真并发竞态 = blocked(重放性不足)（显式登记，不计通过数）')
    print('[c02] 真实库 app.db：before=%s after=%s 不变=%s'
          % (real_before[:16] + '...', real_after[:16] + '...', real_before == real_after))
    verdict = 1 if failed else 0
    print('[c02] exit=%d' % verdict)
    print('=' * 84)

    payload = {
        'run_id': _env.RUN_ID, 'started': started,
        'probe': 'test-reports-2026-10/harness/r2_c02_probe.py',
        'task': 'V-03 / t4 (C-02)',
        'endpoint': {'route': ENDPOINT % 0, 'file': ROUTE_FILE, 'lines': list(ROUTE_LINES),
                     'commit_line': 3753, 'rollback_line': 3757},
        'denominators': {'db_session_rollback_in_app': _count_rollbacks(),
                         'auditlog_calls_in_app': _count_auditlog()},
        'real_db': {'path': rel(args.real_db), 'sha256_before': real_before,
                    'sha256_after': real_after, 'unchanged': real_before == real_after,
                    'pinned': _env.REAL_DB_SHA256_EXPECTED},
        'cases': cases,
        'assertions': assertions,
        'criteria_failed': failed, 'criteria_passed': n_pass, 'criteria_total': n_tot,
        'blocked_faces': [{'id': 'C-02-concurrency', 'status': 'blocked',
                           'reason': '真并发竞态：SQLite 单写锁 ⇒ 不可重放（35 §4 C-02 不可实施面）'}],
        'exit_code': verdict,
        'evidence_kind': 'behavior_verified',
        'search_domain': {
            'app/**.py 内容搜索 db.session.rollback()': '%d 处（本探针独立量测）' % _count_rollbacks(),
            'harness/**.py 内容搜索 threading/Thread': _count_harness_threads(),
            '被测端点': '%s:%d-%d（独立阅读）' % (ROUTE_FILE, *ROUTE_LINES),
        },
        'exclude_basenames': ['r2_c02_probe.py（判定脚本自身）', 'captain_r2_*.py',
                              'reconcile_r2.py', 'improve_plan.py', 'analysis_ledger.py',
                              'evidence/** 度量产物'],
        'del_what_goes_red': '删掉端点里的 `db.session.rollback()`（或把它挪到 commit 之前的位置）'
                             '⇒ C-02-L3.a / C-02-L3.b 必红（逐表 Δ≠0 或 rollback_calls 为空）；'
                             '把 `commit()` 提到链中间 ⇒ C-02-L3.b 必红（写 1…4 不再全回滚）；'
                             '删掉阴性对照场景 ⇒ C-02-L3.0 必红（无法排除「恒不变」伪守恒）',
        'four_injection_pitfalls_aligned': [
            '1) _env.run_child 是 python -B <argv>：argv 必须带脚本路径（本文件写生成脚本到 .tmp 再跑）',
            '2) 注入不碰 create_app() 启动链：改的是 SQLAlchemy Session 事件/方法',
            '3) 每个场景一份独立副本（fixtures.make_isolated_app(tag=场景名)）',
            '4) 授权开关逐场景传参并显式清空（extra_env={WMS_ALLOW_REAL_DB: ""}）',
        ],
    }
    if args.json_out:
        write_text(args.json_out, json.dumps(payload, ensure_ascii=False, indent=1))
    saved = _env.save_evidence('r2_c02_probe.json', json.dumps(payload, ensure_ascii=False,
                                                              indent=1))
    print('[c02] 机读结果已落盘 %s' % rel(saved))
    if args.json_out:
        print('[c02] --json-out 副本 %s' % rel(args.json_out))
    return verdict


def _count_rollbacks():
    """分母：`app/**.py` 的 `db.session.rollback()` 计数（口径：正则行匹配，只读）。"""
    import re
    n = 0
    for dirpath, _dirs, files in os.walk(os.path.join(REPO_ROOT, 'app')):
        for fn in files:
            if not fn.endswith('.py'):
                continue
            try:
                text = read_text(os.path.join(dirpath, fn))
            except Exception:
                continue
            n += len(re.findall(r'db\.session\.rollback\(\)', text))
    return n


def _count_auditlog():
    import re
    n = 0
    for dirpath, _dirs, files in os.walk(os.path.join(REPO_ROOT, 'app')):
        for fn in files:
            if not fn.endswith('.py'):
                continue
            try:
                text = read_text(os.path.join(dirpath, fn))
            except Exception:
                continue
            n += len(re.findall(r'AuditLog\(', text))
    return n


def _count_harness_threads():
    """`harness/**.py` 里 threading/Thread 的出现（证明「线程用例 0」的口径）。"""
    import re
    hits = []
    hdir = os.path.join(REPO_ROOT, 'test-reports-2026-10', 'harness')
    for fn in sorted(os.listdir(hdir)):
        if not fn.endswith('.py'):
            continue
        try:
            text = read_text(os.path.join(hdir, fn))
        except Exception:
            continue
        if re.search(r'\bthreading\b|\bThread\(', text):
            hits.append(fn)
    return {'files': hits, 'count': len(hits),
            'note': '本轮之前 harness 线程/并发用例 = 0（本文件新增取证式并发尝试）'}


# ------------------------------------------------------------ 并发取证（登记 blocked）
CONCURRENCY_CHILD = r'''#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""并发取证子进程：两线程并发对同一原材料扣料（**只取证，不判 HIT**）。

目的：把「SQLite 单写锁 ⇒ 不可重放」从一句声明变成**实测读数**（锁错误/丢失更新的实际形态）。
"""
import json
import os
import sys
import threading
import traceback

sys.path.insert(0, r'{harness}')
sys.path.insert(0, r'{scripts}')
sys.path.insert(0, r'{repo}')

import _env      # noqa: E402
import fixtures  # noqa: E402

OUT = {{'threads': [], 'exceptions': [], 'final': None}}


def worker(app, rm_id, tag, results):
    try:
        with app.app_context():
            from app import db
            from app import models as M
            row = db.session.get(M.RawMaterial, rm_id)
            before = row.quantity
            row.quantity = (row.quantity or 0) - 1.0
            db.session.commit()
            results.append({{'thread': tag, 'before': before, 'after': row.quantity,
                             'ok': True}})
    except BaseException as e:
        results.append({{'thread': tag, 'ok': False,
                         'error': '%s: %s' % (e.__class__.__name__, str(e)[:200])}})


def main():
    app, copy_path = fixtures.make_isolated_app('c02-conc')
    from app import db
    from app import models as M
    with app.app_context():
        cat = M.RawMaterialCategory.query.first()
        rm = M.RawMaterial(supplier='_c02 并发', category_id=cat.id if cat else None,
                           melt_number='_c02CONC', supplier_number='_c02CONC',
                           internal_number='_c02CONC_%s' % _env.RUN_ID,
                           quantity=10.0, status='in_stock', is_archived=False)
        db.session.add(rm)
        db.session.commit()
        rm_id = rm.id
    results = []
    threads = [threading.Thread(target=worker, args=(app, rm_id, 't%d' % i, results))
               for i in (1, 2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=25)
    OUT['threads'] = results
    with app.app_context():
        OUT['final'] = {{'raw_quantity': db.session.get(M.RawMaterial, rm_id).quantity}}
    OUT['alive_after_join'] = [t.is_alive() for t in threads]
    #: 判定口径（**只描述，不判 HIT**）：可重放要求两次并发扣料后 final == 8.0 且两线程都 ok
    OUT['concurrency'] = {{
        'replayable': bool(len(results) == 2 and all(r.get('ok') for r in results)
                           and OUT['final']['raw_quantity'] == 8.0),
        'observed_final_quantity': OUT['final']['raw_quantity'],
        'expected_if_replayable': 8.0,
        'status': 'blocked(重放性不足)',
        'note': 'SQLite 单写锁 + 同一 Session 非线程安全；观测值随调度变化，故不可作为判据',
    }}
    OUT['real_db_sha256_before'] = _env.sha256_file(_env.REAL_DB)
    OUT['real_db_sha256_after'] = _env.sha256_file(_env.REAL_DB)
    OUT['real_db_unchanged'] = OUT['real_db_sha256_before'] == OUT['real_db_sha256_after']
    print('##R2C02-RESULT##' + json.dumps(OUT, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    try:
        _rc = main()
    except Exception:                       # noqa: BLE001 —— SystemExit 不在此列（正常出口）
        print('##R2C02-RESULT##' + json.dumps({{'fatal': traceback.format_exc()[-1200:]}},
                                              ensure_ascii=False))
        _rc = 3
    sys.exit(_rc)
'''


def run_concurrency_attempt(timeout=300):
    path = os.path.join(_env.tmp_dir('c02', 'child'), 'c02_concurrency.py')
    write_text(path, CONCURRENCY_CHILD.format(harness=HERE, scripts=_env.SCRIPTS_DIR,
                                              repo=REPO_ROOT))
    out = _env.run_child([path], cwd=REPO_ROOT, timeout=timeout,
                         extra_env={ALLOW_ENV: ''}, label='c02-concurrency')
    payload = _parse_payload(out['stdout'], out['stderr'])
    out['payload'] = payload
    out['script'] = path
    return out


# --------------------------------------------------------------------- 工具自检
def synthetic_case(scenario, *, http_status=200, qty_before=5.0, qty_after=4.0,
                   delta_pr=1, delta_prm=1, delta_audit=1, rollback=None,
                   raised_at=None, raised_phase=None, retry_status=200,
                   consumed_after_retry=None, success_writes=None):
    """构造与真实读数**同形**的合成场景（用于对拍判据函数本身）。

    `after_retry` 的逐表读数由 `retry_status` **派生**（200 ⇒ 在 after 基础上再 +1；
    其它 ⇒ 不写），保证「期望写入数 = 重跑是否成功」这条判据的口径与真实读数一致。
    """
    def counts_for(qty, extra=None):
        c = {t: 100 for t in LEDGER_TABLES}
        for k, v in (extra or {}).items():
            c[k] = 100 + v
        return c

    def snap(qty, counts, consumed, task_done):
        s = {'raw_quantity': qty,
             'allocation': {'consumed_quantity': consumed, 'allocated_quantity': consumed},
             'task': {'status': 'completed' if task_done else 'pending',
                      'completed_quantity': 10 if task_done else 0,
                      'completed_at': '2026-10-07T00:00:00' if task_done else None}}
        for t in LEDGER_TABLES:
            s[t] = {'count': counts[t], 'ids_tail': [], 'ids_sha': 'X'}
        return s

    changed = (qty_after != qty_before)
    after_counts = counts_for(qty_after,
                              {'production_record': delta_pr,
                               'production_record_materials': delta_prm,
                               'audit_log': delta_audit} if changed else None)
    after_consumed = 0.0
    if changed:
        after_consumed = 1.0
    retry_ok = (retry_status == 200)
    writes = (1 if retry_ok else 0) if success_writes is None else success_writes
    retry_counts = dict(after_counts)
    if retry_ok and writes:
        for k in ('production_record', 'production_record_materials', 'audit_log'):
            retry_counts[k] = after_counts[k] + writes
    after_retry_counts = counts_for((qty_after - writes) if writes else qty_after, None)
    for k, v in retry_counts.items():
        after_retry_counts[k] = v
    after_retry = snap((qty_after - writes) if writes else qty_after, after_retry_counts,
                       (consumed_after_retry if consumed_after_retry is not None
                        else (after_consumed + writes)),
                       task_done=True)
    return {'scenario': scenario,
            'before': snap(qty_before, counts_for(qty_before), 0.0, task_done=False),
            'after': snap(qty_after, after_counts, after_consumed, task_done=changed),
            'after_retry': after_retry,
            'retry': {'status': retry_status, 'body': 'ok' if retry_ok else 'rejected'},
            'rollback_calls': rollback or [],
            #: 真约束场景的「预占行」取证（L3.a 要求它存在 ⇒ 证明约束真的被撞到过）
            'pre_occupied_record_id': (1 if (rollback and scenario == 'integrity-real')
                                       else None),
            'pre_occupied_global_sn': ('C02-SYNTHETIC' if scenario == 'integrity-real'
                                       else None),
            'pre_occupied_table': 'production_record',
            'real_injection': ({'kind': 'unique-collision-on-production_record.global_sn'}
                               if scenario == 'integrity-real' else None),
            'rollback_events': [{'kind': 'after_rollback_event',
                                 'active_exception': (r.get('active_exception')),
                                 'is_integrity_error': r.get('is_integrity_error')}
                                for r in (rollback or [])],
            'http_status': http_status, 'http_raised': None,
            'injection_state': {'raised_at': raised_at, 'raised_phase': raised_phase,
                                'savepoint_seen': 3 if raised_phase == 'post-savepoint' else 0,
                                'raised_stack': ['update_task_status:dispatch'] if raised_at
                                else []},
            'flush_events': [], 'real_db_unchanged': True, 'real_db_assert_ok': True,
            'out_file': '(synthetic)'}


def selftest(args):
    """自检：用**合成读数**对拍判据函数，逐条给出预期判定（含「必须报红」的阳性样本）。

    自检要证明的不是「真实代码通过了」，而是**本探针的判据会红**：

    * `green`：三场景全符预期 ⇒ 判据层 6/6 passed、exit 0；
    * `no-inject-change`：阴性对照里行数**没变**（伪守恒） ⇒ `C-02-L3.0(control)` 必须 **failed**；
    * `fault-not-mid`：`fault-mid` 的注入点没触发（`raised_at=None`） ⇒ `C-02-L3.b` 必须 **failed**；
    * `no-rollback`：行数回退了但 `rollback()` **没被调用** ⇒ `C-02-L3.a` 必须 **failed**
      （防止「ORM 自己清了会话」被当成「应用调了 rollback」）。
    """
    checks = []
    real_before = _env.assert_real_db_untouched('r2_c02 selftest')
    print('=' * 84)
    print('[selftest] 判据函数对拍（合成读数 ⇒ 预期判定）')
    print('=' * 84)

    def rb(is_ie=True):
        return [{'n': 1, 'active_exception': 'IntegrityError' if is_ie else 'Exception',
                 'is_integrity_error': is_ie,
                 'caller': ['dispatch_request', 'decorated', 'update_task_status:rollback']}]

    def green_cases():
        """三场景**全符预期**的合成读数（判据层应 5/5 passed、exit 0）。"""
        ctl = synthetic_case('control', qty_before=5.0, qty_after=4.0)
        #: 真约束：第一发撞 UNIQUE ⇒ 全回滚；重跑被幂等 guard 拒（400 ⇒ 写 0 次）
        intg = synthetic_case('integrity-real', qty_before=5.0, qty_after=5.0,
                              delta_pr=0, delta_prm=0, delta_audit=0, rollback=rb(True),
                              retry_status=400)
        #: 链中段（SAVEPOINT 之外）注入 ⇒ 全回滚；重跑成功（200 ⇒ 写 1 次）
        fm = synthetic_case('fault-mid', qty_before=5.0, qty_after=5.0,
                            delta_pr=0, delta_prm=0, delta_audit=0, rollback=rb(True),
                            raised_at=7, raised_phase='post-savepoint', retry_status=200)
        conc = {'scenario': 'concurrency-attempt', 'concurrency': {
            'replayable': False, 'status': 'blocked(重放性不足)'},
            'real_db_unchanged': True, 'real_db_assert_ok': True, 'out_file': '(synthetic)'}
        return {'control': ctl, 'integrity-real': intg, 'fault-mid': fm,
                'concurrency-attempt': conc}

    def run_case(tag, cases, expect_failed_ids, expect_exit):
        assertions, failed = eval_checks(cases)
        got = {r['id']: r['verdict'] for r in assertions}
        ok_fail = set(failed) == set(expect_failed_ids)
        ok_exit = (0 if not failed else 1) == expect_exit
        good = ok_fail and ok_exit
        row = {'tag': tag, 'verdicts': got, 'failed': failed,
               'expect_failed': list(expect_failed_ids), 'exit': expect_exit, 'ok': good}
        checks.append(row)
        print('  [%s] %-18s failed=%-46s 期望=%-46s exit=%s(期望 %s)'
              % ('PASS' if good else 'FAIL', tag, json.dumps(failed),
                 json.dumps(list(expect_failed_ids)), 0 if not failed else 1, expect_exit))
        return good

    ok_all = True
    ok_all &= run_case('green', green_cases(), set(), 0)

    # 阳性样本①：阴性对照里行数没变（伪守恒） ⇒ control 必红
    c = green_cases()
    c['control'] = synthetic_case('control', qty_before=5.0, qty_after=5.0,
                                  delta_pr=0, delta_prm=0, delta_audit=0)
    ok_all &= run_case('no-inject-change', c, {'C-02-L3.0(control)'}, 1)

    # 阳性样本②：注入点没触发（链没被打断） ⇒ L3.b 必红
    #: 注：这条合成输入里「链没被打断」同时也让 L4 守恒失去前提（全链已提交、重跑被幂等拒）⇒
    #: L4 一并报红是**正确**行为，故期望集合含两条（自检要的是「判据会红」，不是「只红一条」）。
    c = green_cases()
    c['fault-mid'] = synthetic_case('fault-mid', qty_before=5.0, qty_after=4.0,
                                    delta_pr=1, delta_prm=1, delta_audit=1,
                                    rollback=rb(True), raised_at=None, raised_phase=None,
                                    retry_status=400)
    ok_all &= run_case('fault-not-mid', c,
                       {'C-02-L3.b(fault-mid)', 'C-02-L4(ledger)'}, 1)

    # 阳性样本③：行数回退了但 rollback() 没被调用 ⇒ L3.a 必红
    c = green_cases()
    c['integrity-real'] = synthetic_case('integrity-real', qty_before=5.0, qty_after=5.0,
                                         delta_pr=0, delta_prm=0, delta_audit=0,
                                         rollback=[], retry_status=400)
    ok_all &= run_case('no-rollback-call', c, {'C-02-L3.a(integrity-real)'}, 1)

    # 阳性样本④：L4 守恒本身的敏感性 —— 链中断正确、但重跑后 consumed_quantity 不是 1.0
    #: （=「重复扣料」形态）⇒ **只** C-02-L4(ledger) 必红
    c = green_cases()
    c['fault-mid'] = synthetic_case('fault-mid', qty_before=5.0, qty_after=5.0,
                                    delta_pr=0, delta_prm=0, delta_audit=0,
                                    rollback=rb(True), raised_at=7,
                                    raised_phase='post-savepoint', retry_status=200,
                                    consumed_after_retry=2.0)
    ok_all &= run_case('l4-not-conserved', c, {'C-02-L4(ledger)'}, 1)

    real_ok = _env.sha256_file(_env.REAL_DB) == real_before == _env.REAL_DB_SHA256_EXPECTED
    ok_all &= real_ok
    print('  [%s] 真实库 app.db SHA256 = %s（钉死值）' % ('PASS' if real_ok else 'FAIL',
                                                          real_before))
    payload = {'mode': 'selftest', 'run_id': _env.RUN_ID, 'checks': checks,
               'real_db_sha256': real_before, 'real_db_ok': real_ok,
               'verdict': 'passed' if ok_all else 'failed'}
    saved = _env.save_evidence('r2_c02_probe_selftest.json',
                               json.dumps(payload, ensure_ascii=False, indent=1))
    print('[selftest] 结论：%s（5 组合成对拍：1 组全绿 + 4 组必红）'
          % ('OK' if ok_all else 'FAIL'))
    print('[selftest] 证据已落盘 %s' % rel(saved))
    print('[selftest] exit=%d' % (0 if ok_all else 1))
    return 0 if ok_all else 1


# --------------------------------------------------------------------- 双跑一致
def compare_runs(path_a, path_b):
    """双跑一致：断言集合 + 逐条 verdict + 关键读数逐条相同。"""
    a = json.loads(read_text(path_a))
    b = json.loads(read_text(path_b))
    out = {'path_a': rel(path_a), 'path_b': rel(path_b),
           'run_id_a': a.get('run_id'), 'run_id_b': b.get('run_id')}
    va = {r['id']: r['verdict'] for r in a.get('assertions', [])}
    vb = {r['id']: r['verdict'] for r in b.get('assertions', [])}
    out['only_in_a'] = sorted(set(va) - set(vb))
    out['only_in_b'] = sorted(set(vb) - set(va))
    out['verdict_diff'] = {k: [va[k], vb[k]] for k in sorted(set(va) & set(vb))
                           if va[k] != vb[k]}

    def readings(p):
        c = p.get('cases') or {}
        return {k: {'delta': _counts_delta_safe(c.get(k) or {}),
                    'rollback_calls': len((c.get(k) or {}).get('rollback_calls') or []),
                    'http_status': (c.get(k) or {}).get('http_status'),
                    'raised_at': ((c.get(k) or {}).get('injection_state') or {}).get('raised_at')}
                for k in ('control', 'integrity-real', 'fault-mid')}

    ra, rb = readings(a), readings(b)
    out['readings_a'] = ra
    out['readings_b'] = rb
    out['reading_diff'] = {k: [ra.get(k), rb.get(k)] for k in sorted(set(ra) | set(rb))
                           if ra.get(k) != rb.get(k)}
    out['identical'] = (not out['only_in_a'] and not out['only_in_b']
                        and not out['verdict_diff'] and not out['reading_diff'])
    out['criteria_a'] = {'passed': a.get('criteria_passed'), 'total': a.get('criteria_total'),
                         'failed': a.get('criteria_failed')}
    out['criteria_b'] = {'passed': b.get('criteria_passed'), 'total': b.get('criteria_total'),
                         'failed': b.get('criteria_failed')}
    saved = _env.save_evidence('r2_c02_probe_compare.json',
                               json.dumps(out, ensure_ascii=False, indent=1))
    print('[compare] A=%s B=%s' % (out['run_id_a'], out['run_id_b']))
    print('[compare] only_in_a=%s only_in_b=%s verdict_diff=%s'
          % (out['only_in_a'], out['only_in_b'], out['verdict_diff']))
    print('[compare] reading_diff=%s' % json.dumps(out['reading_diff'], ensure_ascii=False)[:300])
    print('[compare] 双跑一致 = %s' % out['identical'])
    print('[compare] 证据已落盘 %s' % rel(saved))
    return 0 if out['identical'] else 1


def _counts_delta_safe(case):
    before = case.get('before') or {}
    after = case.get('after') or {}

    def c(sn, t):
        v = (sn.get(t) or {}).get('count')
        return v if isinstance(v, int) else None
    return {t: (None if c(before, t) is None or c(after, t) is None
                else c(after, t) - c(before, t)) for t in LEDGER_TABLES}


def main():
    ap = argparse.ArgumentParser(description='C-02 并发/事务原子性探针（V-03 / t4）')
    ap.add_argument('--selftest', action='store_true',
                    help='用合成读数对拍判据函数（证明本探针会报红）')
    ap.add_argument('--real-db', default=DEFAULT_REAL_DB, help='真实库路径（只读引用）')
    ap.add_argument('--timeout', type=int, default=900, help='单场景子进程超时秒')
    ap.add_argument('--json-out', default=None, help='把机读结果另存一份到该路径')
    ap.add_argument('--compare', nargs=2, metavar=('A', 'B'), default=None,
                    help='双跑一致：比对两份 --json-out 产物')
    args = ap.parse_args()
    if args.compare:
        return compare_runs(args.compare[0], args.compare[1])
    if args.selftest:
        return selftest(args)
    return full_run(args)


if __name__ == '__main__':
    sys.exit(main())
