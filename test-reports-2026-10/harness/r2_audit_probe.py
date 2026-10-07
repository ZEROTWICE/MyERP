#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""r2_audit_probe.py —— C-01「J 域通知与审计」的审计写入**增量断言**探针（V-05 / t6）。

任务契约（`35-第2轮测试总方案（定稿）.md` §4 C-01 行 / `33` §1）：

* **inScope**：本文件（`test-reports-2026-10/harness/r2_audit_probe.py`）。**不得改 `app/**`**，
  也**不得改 `harness/fixtures.py`**（V-04 已完成并冻结于 64496 B）。
* **分母（两种口径，本文件独立量测）**：`app/**.py` 的 `AuditLog(` **114** 处（与 `34`/`35` 同口径）；
  其中 `class AuditLog(db.Model):` 是**子串误计** ⇒ 真实例化 **113** 处。
* **通过判据（形态 ⑤/⑥）**：取 **N≥3** 个写端点 —— **Δ`AuditLog` 行数 = 断言动作数**，
  且 `target_model`/`target_id` **正确**（`target_id` 必须等于该动作真正建出的那一行的 id）⇒ **0 → >0**。
* **阴性用例（必做）**：**业务写失败 ⇒ `AuditLog` 不得新增**（5 类失败路径，含 1 类「审计与被审计
  动作同事务」的提交期真 `IntegrityError`）。
* **不能证明什么（必须登记）**：通知是否送达（属 L5 人工）；是否覆盖全部 113 处（**必须登记抽样率**）。
* **verify**：`--selftest`（判据会报红）+ **前后两个数** + 双跑一致（`--compare`）+ 真库前后指纹。

## 被测端点（**真实端点**，非自造 API；每条都给出 `AuditLog(` 调用点坐标）

| # | 端点 | 动作（`action`） | `target_model` | `target_id` 来源 | 调用点 |
| --- | --- | --- | --- | --- | --- |
| E1 | `POST /bonus_penalties/add` | 添加奖金/罚款记录 | `BonusPenalty` | `bonus_penalty.id`（:**1734 已 flush**） | `routes.py:1737` |
| E2 | `POST /tasks/add` | 分配生产任务 | `TaskAssignment` | `task.id`（:**4420 已 flush**） | `routes.py:4423` |
| E3 | `POST /employee/add` | 添加员工 | `Employee` | `employee.id`（:**564 已 flush**） | `routes.py:568` |
| E4 | `POST /inventory/finished/add` | 添加成品 | `FinishedProduct` | `product.id`（**无 flush**） | `routes.py:5152` |
| E5 | `POST /api/quality/tasks` | 创建质检任务 | `InspectionTask` | `task.id`（**无 flush**） | `quality.py:628` |

**E1/E2/E3 构成 N=3 的判据集**；**E4/E5 是同一形态的第二类样本** —— 源码显示
`db.session.add(x)` 之后**没有 `flush()`** 就取 `x.id` ⇒ 预期 `target_id` 落库为 **NULL**。
本探针把这两条**实测**出来并作为**发现**登记（见 `GAP_ASSERTION_IDS`），不混入判据层通过数。

## 失败路径（业务写失败 ⇒ 审计不得新增）

| # | 失败形态 | 触发方式 |
| --- | --- | --- |
| F1 | 入参解析失败（`date` 缺失 ⇒ `strptime(None)` 抛错） | `POST /bonus_penalties/add` 不带 `date` |
| F2 | 业务前置校验拒绝（工序不存在 ⇒ 400） | `POST /tasks/add` 用不存在的 `process_id` |
| F3 | 真 `IntegrityError`（`TaskAssignment.quantity` NOT NULL） | `POST /tasks/add` 带 `quantity=null` |
| F4 | 唯一性预检拒绝（工号已存在 ⇒ 渲染表单，不写库） | `POST /employee/add` 用工号副本已有的工号 |
| F5 | **提交期**真 `IntegrityError`（审计行**已进 session** 才失败） | E1 路径上注入 `before_flush`（`AuditLog` 一进 `session.new` 即失败）⇒ 审计与被审计动作**同事务**双回滚 |

## 复算坐标（本文件实跑所得；第三方可逐条复核）

| 量 | 口径 | 实测值 |
| --- | --- | --- |
| `AuditLog(` 裸子串 | 只读遍历 `app/**.py` | **114**（含 `class AuditLog(` 1 处 ⇒ 真实例化 **113**） |
| 含审计写入的真实端点 | 调用点 → 所在 `def` → 最近 `@bp.route` | **90** 个 |
| 带 `target_model`+`target_id` 的调用点 | 同上（块内正则） | **91**（无 `target_id` 者 **23**） |
| 覆盖的调用点 / 端点 | 本探针驱动的 5 条 | **5/113 = 4.42%** / **5/90 = 5.56%** |
| 核心端点 Δ`AuditLog` | 请求前/后 `COUNT(*)` | E1/E2/E3 各 **+1**（`0 → >0`），`target_id` = **2 / 19 / 64** |
| 失败路径 Δ`AuditLog` | 同上 | F1…F5 全 **0**（新增行数 0） |
| 真实库 `audit_log` | `mode=ro` 只读 | 73 行，`target_id IS NULL` **40** 行、其中 `can_rollback=True` **10** 行 |

## ⟪发现⟫ 审计行 `target_id` 落库为 NULL（产品面缺陷，**不计入判据层**）

| 场景 | 端点 | 调用点 | `db.session.add(x)` | 取 `x.id` | 实测 |
| --- | --- | --- | --- | --- | --- |
| E4 | `POST /inventory/finished/add` | `routes.py:5152` | `:5149`（**无 flush**） | `:5159` | `target_model=FinishedProduct` 正确、**`target_id=NULL`**、`can_rollback=True` |
| E5 | `POST /api/quality/tasks` | `quality.py:628` | `:625`（**无 flush**） | `:635` | `target_model=InspectionTask` 正确、**`target_id=NULL`**、`can_rollback=True` |

* **对照组**：同一判据下 E1/E2/E3（调用点前**有** flush：`routes.py:1734` / `:4420` / `:564`）
  的 `target_id` 全部正确 ⇒ 唯一结构性差异就是 **flush 时机**。
* **真库旁证（决定性，且不由本探针产生）**：真实库 `audit_log` **id=73** 即
  `action='创建质检任务'`、`target_model='InspectionTask'`、`target_id=NULL`、`can_rollback=1`
  —— 正是 E5 那条调用点（`quality.py:628`）的产物。全库另有 `自动创建生产任务`(TaskAssignment) 4、
  `创建销售订单…`(ProductionOrder) 3、`添加产品`(Product) 2、`添加编码规则`(CodeRule) 2、
  `添加原材料`(RawMaterial) 1 等同样形态。
* **影响**：`can_rollback=True` 的审计轨迹指不到目标行 ⇒ `/audit_logs/rollback/<id>` 类回滚
  无法定位对象；审计的「可回滚」承诺与实际数据不一致。
* 机制断言的口径：**观察**是 `behavior_verified`（HTTP + 库内读数 + 真库实例）；**因果解释**
  （缺 `flush()`）为源码级推断，坐标已给全（上表两行），可独立复核。

## 用法（仓库根目录；解释器绝对路径，`28` §5-1 / `40` R-4）

```powershell
$py = 'F:\Miniconda\envs\wage\python.exe'
$env:HARNESS_RUN_ID = 'r2-exec-b3-c01'
& $py -B test-reports-2026-10\harness\r2_audit_probe.py                 # 判据层
& $py -B test-reports-2026-10\harness\r2_audit_probe.py --selftest      # 判据会报红（含 4 条阳性样本）
& $py -B test-reports-2026-10\harness\r2_audit_probe.py --json-out a.json
& $py -B test-reports-2026-10\harness\r2_audit_probe.py --compare a.json b.json   # 双跑一致
```

退出码：`0` = 判据层全过（前后两数 + N≥3 端点 + 5 类失败路径 + 抽样登记 + 真库不变量）；
`1` = 任一失败。`--selftest`：`0` = 判据函数在合成输入下逐条给出预期判定（含必红样本）。
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time

try:  # A-14：本机控制台 GBK
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import _env  # noqa: E402

RESULT_MARKER = '##R2C01-RESULT##'
REPO_ROOT = _env.REPO_ROOT
DEFAULT_REAL_DB = _env.REAL_DB
ALLOW_ENV = 'WMS_ALLOW_REAL_DB'      # 与 V-02 同口径；本探针不连真实库（逐场景显式清空）

AUDIT_TABLE = 'audit_log'
#: 判据层要求的最少端点数（`35` §4 C-01「取 N≥3 个写端点」）
MIN_ENDPOINTS = 3
#: 「发现」类断言：**不计入判据层通过数与退出码**（与 V-02 的 GAP_ASSERTION_IDS 同法）
GAP_ASSERTION_IDS = ('C-01-finding(target_id-null)',)

#: 场景表（parent 侧声明；payload 里的 `@x.y` 占位符由子进程按副本现状解析）
SCENARIOS = [
    {
        'id': 'E1-bonus-add', 'group': 'core',
        'endpoint': '/bonus_penalties/add', 'method': 'POST', 'payload_kind': 'json',
        'payload': {'employee_id': '@employee.id', 'amount': 100.0, 'reason': '_c01 探针',
                    'date': '@today', 'type': 'bonus', 'process_id': '@process.id'},
        'setup': 'none', 'target_table': 'bonus_penalty',
        'action': '添加奖金/罚款记录', 'target_model': 'BonusPenalty', 'rollback_type': 'add',
        'audit_call_site': 'app/main/routes.py:1737',
        'desc': 'E1 奖金/罚款新增（target_id 于 :1734 flush 后取 ⇒ 应正确）',
    },
    {
        'id': 'E2-task-add', 'group': 'core',
        'endpoint': '/tasks/add', 'method': 'POST', 'payload_kind': 'json',
        'payload': {'process_id': '@process.id', 'employee_id': '@employee.id', 'quantity': 5,
                    'target_date': '@today', 'notes': '_c01 探针'},
        'setup': 'none', 'target_table': 'task_assignment',
        'action': '分配生产任务', 'target_model': 'TaskAssignment', 'rollback_type': 'add',
        'audit_call_site': 'app/main/routes.py:4423',
        'desc': 'E2 任务分配新增（target_id 于 :4420 flush 后取 ⇒ 应正确）',
    },
    {
        'id': 'E3-employee-add', 'group': 'core',
        'endpoint': '/employee/add', 'method': 'POST', 'payload_kind': 'form',
        'payload': {'employee_id': '@emp_code', 'name': '_c01 探针员工', 'position': '普通员工',
                    'base_salary': '3000', 'coefficient': '1.0', 'department': '_c01 部门',
                    'hire_date': '@today'},
        'setup': 'none', 'target_table': 'employee',
        'action': '添加员工', 'target_model': 'Employee', 'rollback_type': 'add',
        'audit_call_site': 'app/main/routes.py:568',
        'desc': 'E3 员工新增（target_id 于 :564 flush 后取 ⇒ 应正确）',
    },
    {
        'id': 'E4-finished-add', 'group': 'finding-candidate',
        'endpoint': '/inventory/finished/add', 'method': 'POST', 'payload_kind': 'json',
        'payload': {'product_number_type': 'manual', 'product_number': '@fp_code',
                    'drawing_number': '_c01-DWG', 'model': '_c01-MODEL',
                    'production_date': '@today', 'inspector': '_c01 检验员', 'notes': '_c01 探针'},
        'setup': 'none', 'target_table': 'finished_product',
        'action': '添加成品', 'target_model': 'FinishedProduct', 'rollback_type': 'add',
        'audit_call_site': 'app/main/routes.py:5152',
        'desc': 'E4 成品新增（:5149 add 后**无 flush** 就取 product.id ⇒ 预期 target_id=NULL）',
    },
    {
        'id': 'E5-quality-task-add', 'group': 'finding-candidate',
        'endpoint': '/api/quality/tasks', 'method': 'POST', 'payload_kind': 'json',
        #: `type='product'` + `@product.id`：真实库副本里 `production_record` 可能为空，
        #: 而 `inspection_target_id` 只要有值即可（该端点不校验目标存在性）；
        #: 审计写法（`quality.py:628`）与 type 无关 ⇒ 不影响本判据
        'payload': {'type': 'product', 'inspection_target_id': '@product.id',
                    'inspector_id': '@admin.id', 'priority': 1, 'notes': '_c01 探针'},
        'setup': 'none', 'target_table': 'inspection_tasks',
        'action': '创建质检任务', 'target_model': 'InspectionTask', 'rollback_type': 'add',
        'audit_call_site': 'app/main/quality.py:628',
        'desc': 'E5 质检任务新增（:625 add 后**无 flush** 就取 task.id ⇒ 预期 target_id=NULL）',
    },
    {
        'id': 'F1-bonus-bad-date', 'group': 'failure',
        'endpoint': '/bonus_penalties/add', 'method': 'POST', 'payload_kind': 'json',
        'payload': {'employee_id': '@employee.id', 'amount': 10.0, 'reason': '_c01 失败路径',
                    'type': 'bonus'},          # 故意不带 date ⇒ strptime(None) 抛错
        'setup': 'none', 'target_table': 'bonus_penalty', 'expect_audit_rows': 0,
        'desc': 'F1 入参解析失败（缺 date）⇒ 审计不得新增',
    },
    {
        'id': 'F2-task-no-process', 'group': 'failure',
        'endpoint': '/tasks/add', 'method': 'POST', 'payload_kind': 'json',
        'payload': {'process_id': 99999999, 'employee_id': '@employee.id', 'quantity': 1,
                    'target_date': '@today'},
        'setup': 'none', 'target_table': 'task_assignment', 'expect_audit_rows': 0,
        'desc': 'F2 业务前置校验拒绝（工序不存在 ⇒ 400）⇒ 审计不得新增',
    },
    {
        'id': 'F3-task-null-quantity', 'group': 'failure',
        'endpoint': '/tasks/add', 'method': 'POST', 'payload_kind': 'json',
        'payload': {'process_id': '@process.id', 'employee_id': '@employee.id',
                    'quantity': '@none', 'target_date': '@today'},
        'setup': 'none', 'target_table': 'task_assignment', 'expect_audit_rows': 0,
        'desc': 'F3 真 IntegrityError（quantity NOT NULL）⇒ 审计不得新增',
    },
    {
        'id': 'F4-employee-dup-code', 'group': 'failure',
        'endpoint': '/employee/add', 'method': 'POST', 'payload_kind': 'form',
        'payload': {'employee_id': '@dup_code', 'name': '_c01 重复工号', 'position': '普通员工',
                    'base_salary': '3000', 'coefficient': '1.0', 'department': '_c01',
                    'hire_date': '@today'},
        'setup': 'duplicate_employee', 'target_table': 'employee', 'expect_audit_rows': 0,
        'desc': 'F4 唯一性预检拒绝（工号已存在）⇒ 审计不得新增',
    },
    {
        'id': 'F5-bonus-audit-same-txn', 'group': 'failure',
        'endpoint': '/bonus_penalties/add', 'method': 'POST', 'payload_kind': 'json',
        'payload': {'employee_id': '@employee.id', 'amount': 50.0, 'reason': '_c01 同事务',
                    'date': '@today', 'type': 'penalty', 'process_id': '@process.id'},
        'setup': 'inject_flush_after_audit', 'target_table': 'bonus_penalty',
        'expect_audit_rows': 0, 'expect_target_delta': 0,
        'desc': 'F5 提交期真 IntegrityError（审计行已进 session）⇒ 审计与被审计动作同事务双回滚',
    },
]


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


# --------------------------------------------------------------- 子场景（生成后执行）
CHILD_TEMPLATE = r'''#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""r2_audit_child.py —— C-01 子场景（由 `r2_audit_probe.py` 生成到 `.tmp/<RUN_ID>/c01/child/`）。

参数经环境变量传入（坑：脚本落在 `.tmp/` 下，`__file__` 推不出 harness 路径）：

| 环境变量 | 含义 |
| --- | --- |
| `C01_SPEC` | 场景声明（JSON：endpoint/method/payload_kind/payload/setup/target_table/action/...） |
| `C01_RUN_ID` | 与父进程同一个 `HARNESS_RUN_ID` |
| `C01_HARNESS_DIR` / `C01_SCRIPTS_DIR` / `C01_REPO_ROOT` | 三方路径 |

输出：stdout 一行 `##R2C01-RESULT##<json>`（父进程只认这一行；结果先过 `_json_safe`）。
"""
import json
import os
import sys
import traceback

HARNESS_DIR = os.environ.get('C01_HARNESS_DIR') or ''
SCRIPTS_DIR = os.environ.get('C01_SCRIPTS_DIR') or ''
REPO_ROOT = os.environ.get('C01_REPO_ROOT') or ''
for _p in (HARNESS_DIR, SCRIPTS_DIR, REPO_ROOT):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)

import _env        # noqa: E402
import fixtures    # noqa: E402

SPEC = json.loads(os.environ.get('C01_SPEC') or '{}')
RUN_ID = os.environ.get('C01_RUN_ID') or _env.RUN_ID
RESULT = {'scenario': SPEC.get('id'), 'group': SPEC.get('group'), 'run_id': RUN_ID,
          'errors': [], 'trace': []}


def trace(msg):
    RESULT['trace'].append(str(msg))


def _json_safe(obj, depth=0):
    """落盘前统一洗成可序列化形态（异常对象绝不允许直接进 RESULT）。"""
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, dict):
        return {str(k): _json_safe(v, depth + 1) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_json_safe(v, depth + 1) for v in obj]
    if depth > 6:
        return '<%s>' % type(obj).__name__
    return '%s: %s' % (type(obj).__name__, str(obj)[:200])


def _table_meta(db, table):
    """逐表读数：行数 + 最大 id（增量判据的分母）。"""
    try:
        cnt = db.session.execute(db.text('SELECT COUNT(*) FROM "%s"' % table)).scalar()
        mx = db.session.execute(db.text('SELECT MAX(id) FROM "%s"' % table)).scalar()
        return {'count': int(cnt or 0), 'max_id': (int(mx) if mx is not None else None)}
    except Exception as e:
        return {'error': '%s: %s' % (e.__class__.__name__, e)}


def _audit_rows_after(db, baseline_max_id):
    """本次请求新增的审计行（口径：id > 基线 max_id，按 id 升序）。"""
    base = '' if baseline_max_id is None else ' WHERE id > %d' % int(baseline_max_id)
    rows = db.session.execute(db.text(
        'SELECT id, user_id, action, target_model, target_id, can_rollback, rollback_type, '
        'details FROM audit_log%s ORDER BY id' % base)).fetchall()
    out = []
    for r in rows:
        out.append({'id': r[0], 'user_id': r[1], 'action': r[2], 'target_model': r[3],
                    'target_id': r[4], 'can_rollback': (None if r[5] is None else bool(r[5])),
                    'rollback_type': r[6], 'details': (r[7] or '')[:120]})
    return out


def _resolve(value, ctx):
    """解析 `@obj.attr` / `@today` / `@run` / `@none` 占位符（payload 里全是模板）。"""
    if not isinstance(value, str) or not value.startswith('@'):
        return value
    key = value[1:]
    if key == 'today':
        return ctx['today']
    if key == 'run':
        return ctx['run']
    if key == 'none':
        return None
    if '.' in key:
        obj, attr = key.split('.', 1)
        return getattr(ctx[obj], attr, None) if key.split('.', 1)[0] in ctx else None
    return ctx.get(key)


def main():
    from datetime import date

    app, copy_path = fixtures.make_isolated_app('c01-' + str(SPEC.get('id')))
    RESULT['copy_path'] = copy_path
    RESULT['copy_path_verdict'] = fixtures.copy_path_verdict()
    RESULT['real_db_sha256_before'] = _env.sha256_file(_env.REAL_DB)
    trace('isolated app ready: %s' % copy_path)

    from app import db
    from app import models as M

    # ---- 夹具：脚手架 + 基础对象（V-04 的夹具面直接复用，不改它）
    seeded = fixtures.seed_all(app)
    RESULT['fixture_seeded'] = {'users': len((seeded or {}).get('users') or {}),
                                'seeded_tables': len((seeded or {}).get('seeded') or {})}
    with app.app_context():
        admin = M.User.query.filter_by(username='admin').first() or M.User.query.first()
        if admin is None:
            raise AssertionError('夹具失败：副本里没有任何 user 行')
        ctx = {
            'admin': admin,
            'employee': M.Employee.query.first(),
            'process': M.ProcessPrice.query.first(),
            'product': M.Product.query.first(),
            'production_record': M.ProductionRecord.query.first(),
            'customer': M.Customer.query.first(),
            'today': date.today().isoformat(),
            'run': RUN_ID,
            'emp_code': ('_c01E%s' % RUN_ID)[:50],
            'dup_code': ('_c01D%s' % RUN_ID)[:50],
            'fp_code': ('_c01FP%s' % RUN_ID)[:50],
        }
        for need in ('employee', 'process'):
            if ctx[need] is None:
                raise AssertionError('夹具失败：缺 %s（seed_all 未建出）' % need)
        if ctx['production_record'] is None:
            ctx['production_record'] = M.ProductionRecord.query.first()
    RESULT['fixture_ctx'] = {k: (getattr(v, 'id', v) if k not in ('today', 'run') else v)
                             for k, v in ctx.items()}
    trace('ctx: employee=%s process=%s production_record=%s admin=%s'
          % (getattr(ctx['employee'], 'id', None), getattr(ctx['process'], 'id', None),
             getattr(ctx['production_record'], 'id', None), getattr(ctx['admin'], 'id', None)))

    # ---- 场景专属 setup
    setup = SPEC.get('setup') or 'none'
    if setup == 'duplicate_employee':
        with app.app_context():
            dup = M.Employee(global_sn=M.SerialNumber.get_next_number(),
                             employee_id=ctx['dup_code'], name='_c01 已存在工号',
                             position='普通员工', department='_c01',
                             hire_date=date.today(), is_active=True)
            db.session.add(dup)
            db.session.commit()
            RESULT['setup_dup_employee_id'] = dup.id
        trace('setup: 预占工号 %s' % ctx['dup_code'])
    elif setup == 'inject_flush_after_audit':
        from sqlalchemy.orm import Session
        from sqlalchemy import event as _sa_event

        @_sa_event.listens_for(Session, 'before_flush')
        def _hook(session, flush_context, instances):        # noqa: ANN001
            names = [type(o).__name__ for o in session.new]
            if 'AuditLog' in names:
                RESULT['injection_fired'] = True
                RESULT['injection_new'] = names[:10]
                trace('注入：AuditLog 已进 session.new（%s）⇒ 抛 IntegrityError' % names[:6])
                from sqlalchemy.exc import IntegrityError as _IE
                raise _IE('C-01 故障注入：审计行已进 session 后失败',
                          None, Exception('injected'))
        trace('setup: 已装 before_flush 钩子（AuditLog 进 session ⇒ 失败）')

    # ---- 基线读数（**注入之后**、请求之前；注入钩子不影响读数）
    with app.app_context():
        base_audit = _table_meta(db, 'audit_log')
        base_target = _table_meta(db, SPEC.get('target_table') or 'audit_log')
    RESULT['before'] = {'audit_log': base_audit, 'target': base_target,
                        'target_table': SPEC.get('target_table')}
    trace('before: audit=%s target(%s)=%s'
          % (base_audit, SPEC.get('target_table'), base_target))

    # ---- 发请求（登录用 session 注入：不写任何 fixture）
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(ctx['admin'].id)
        sess['_fresh'] = True
    payload = {k: _resolve(v, ctx) for k, v in (SPEC.get('payload') or {}).items()}
    RESULT['payload_sent'] = _json_safe(payload)
    raised = None
    try:
        if SPEC.get('payload_kind') == 'form':
            data = {k: ('' if v is None else str(v)) for k, v in payload.items()}
            resp = client.open(SPEC['endpoint'], method=SPEC.get('method') or 'POST', data=data)
        else:
            resp = client.open(SPEC['endpoint'], method=SPEC.get('method') or 'POST', json=payload)
        RESULT['http_status'] = resp.status_code
        RESULT['http_location'] = resp.headers.get('Location', '')
        RESULT['http_body'] = resp.get_data(as_text=True)[:400]
    except BaseException as e:                                # noqa: BLE001
        raised = {'type': e.__class__.__name__, 'message': str(e)[:400]}
        RESULT['http_raised'] = raised
    trace('request: %s %s -> status=%s raised=%s'
          % (SPEC.get('method'), SPEC.get('endpoint'), RESULT.get('http_status'),
             (raised or {}).get('type')))

    # ---- 术后读数 + 新增审计行
    with app.app_context():
        after_audit = _table_meta(db, 'audit_log')
        after_target = _table_meta(db, SPEC.get('target_table') or 'audit_log')
        new_rows = _audit_rows_after(db, base_audit.get('max_id'))
    RESULT['after'] = {'audit_log': after_audit, 'target': after_target}
    RESULT['new_audit_rows'] = new_rows
    RESULT['delta'] = {
        'audit_log': ((after_audit.get('count') or 0) - (base_audit.get('count') or 0)
                      if 'error' not in after_audit and 'error' not in base_audit else None),
        'target': ((after_target.get('count') or 0) - (base_target.get('count') or 0)
                   if 'error' not in after_target and 'error' not in base_target else None),
    }
    #: 「该动作真正建出的那一行的 id」= 目标表请求后的 max_id（增量恰为 1 时它就是新建行）
    RESULT['created_target_max_id'] = after_target.get('max_id')
    RESULT['created_target_delta'] = RESULT['delta']['target']
    trace('after: audit=%s target=%s delta=%s new_audit_rows=%d'
          % (after_audit, after_target, RESULT['delta'], len(new_rows)))

    RESULT['real_db_sha256_after'] = _env.sha256_file(_env.REAL_DB)
    RESULT['real_db_unchanged'] = (RESULT['real_db_sha256_before']
                                   == RESULT['real_db_sha256_after'])
    RESULT['real_db_pinned'] = _env.REAL_DB_SHA256_EXPECTED
    try:
        _env.assert_real_db_untouched('c01 child ' + str(SPEC.get('id')))
        RESULT['real_db_assert_ok'] = True
    except Exception as e:                                    # noqa: BLE001
        RESULT['real_db_assert_ok'] = False
        RESULT['errors'].append('真实库指纹断言失败：%s' % e)
    print('##R2C01-RESULT##' + json.dumps(_json_safe(RESULT), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    try:
        _rc = main()
    except Exception:                       # noqa: BLE001 —— SystemExit 不在此列（正常出口）
        print('##R2C01-RESULT##' + json.dumps(
            {'scenario': SPEC.get('id'), 'fatal': traceback.format_exc()[-1500:]},
            ensure_ascii=False))
        _rc = 3
    sys.exit(_rc)
'''


def child_script_path(run_id, scenario_id):
    safe = re.sub(r'[^0-9A-Za-z_.-]', '_', str(scenario_id))
    return os.path.join(_env.tmp_dir('c01', 'child'),
                        'c01_%s_%s.py' % (str(run_id).replace(os.sep, '_'), safe))


def _parse_payload(stdout, stderr):
    """取**第一个可解析且非 fatal** 的 `##R2C01-RESULT##` 行（防收尾 fatal 覆盖正常读数）。"""
    payload, fallback = None, None
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


def run_scenario(spec, timeout=900, run_id=None):
    """在独立子进程里跑一个场景（独立副本、独立解释器；argv 必带脚本路径）。"""
    run_id = run_id or _env.RUN_ID
    path = child_script_path(run_id, spec['id'])
    write_text(path, CHILD_TEMPLATE)
    out = _env.run_child([path], cwd=REPO_ROOT, timeout=timeout,
                         extra_env={ALLOW_ENV: '',        # 显式清空授权开关
                                    'C01_HARNESS_DIR': HERE,
                                    'C01_SCRIPTS_DIR': _env.SCRIPTS_DIR,
                                    'C01_REPO_ROOT': REPO_ROOT,
                                    'C01_RUN_ID': run_id,
                                    'C01_SPEC': json.dumps(spec, ensure_ascii=False)},
                         label='c01-%s' % spec['id'])
    out['payload'] = _parse_payload(out['stdout'], out['stderr'])
    out['script'] = path
    return out


# ------------------------------------------------------- 抽样率与覆盖面（只读源码）
def scan_audit_call_sites():
    """只读清点 `app/**.py` 的 `AuditLog(`：两种口径 + 所在函数 + 最近路由 + 是否带 target_*。"""
    sites = []
    for dirpath, _dirs, files in os.walk(os.path.join(REPO_ROOT, 'app')):
        for fn in sorted(files):
            if not fn.endswith('.py'):
                continue
            path = os.path.join(dirpath, fn)
            relpath = rel(path)
            lines = read_text(path).splitlines()
            func = None
            route = None
            for i, line in enumerate(lines, start=1):
                m = re.match(r'\s*def (\w+)\(', line)
                if m:
                    func = m.group(1)
                r = re.search(r"@bp\.route\(\s*['\"]([^'\"]+)['\"]", line)
                if r:
                    route = r.group(1)
                if 'AuditLog(' in line:
                    block = '\n'.join(lines[i - 1:i + 16])
                    sites.append({
                        'file': relpath, 'line': i, 'func': func, 'route': route,
                        'is_class_decl': bool(re.match(r'\s*class\s+AuditLog\(', line)),
                        'has_target_model': bool(re.search(r'target_model\s*=', block)),
                        'has_target_id': bool(re.search(r'target_id\s*=', block)),
                        'has_can_rollback': bool(re.search(r'can_rollback\s*=', block)),
                        'has_rollback_type': bool(re.search(r'rollback_type\s*=', block)),
                    })
    return sites


def build_coverage(covered_sites):
    sites = scan_audit_call_sites()
    inst = [s for s in sites if not s['is_class_decl']]
    endpoints = {}
    for s in sites:
        if s['route']:
            endpoints.setdefault((s['file'], s['route']), []).append(s['line'])
    covered_keys = set()
    covered_lines = set()
    for c in covered_sites:
        covered_lines.add('%s:%s' % (c['file'], c['line']))
        for s in sites:
            if s['file'] == c['file'] and s['line'] == c['line'] and s['route']:
                covered_keys.add((s['file'], s['route']))
    by_file = {}
    for s in sites:
        by_file.setdefault(s['file'], {'raw': 0, 'inst': 0, 'with_target': 0})
        by_file[s['file']]['raw'] += 1
        if not s['is_class_decl']:
            by_file[s['file']]['inst'] += 1
        if s['has_target_model'] and s['has_target_id']:
            by_file[s['file']]['with_target'] += 1
    return {
        'auditlog_calls_raw': len(sites),
        'auditlog_instantiations': len(inst),
        'class_decl_false_positive': [{'file': s['file'], 'line': s['line']}
                                      for s in sites if s['is_class_decl']],
        'sites_with_target_model_and_id': len(
            [s for s in sites if s['has_target_model'] and s['has_target_id']]),
        'sites_without_target_id': len([s for s in sites if not s['has_target_id']]),
        'endpoints_with_audit': len(endpoints),
        'endpoint_list': sorted(''.join([f.split('/')[-1] + ' ' + r]) for f, r in endpoints),
        'by_file': by_file,
        'covered_call_sites': sorted(covered_lines),
        'covered_call_site_count': len([c for c in covered_lines
                                        if any(c == '%s:%s' % (s['file'], s['line'])
                                               for s in sites)]),
        'covered_endpoints': sorted(''.join([f.split('/')[-1] + ' ' + r])
                                    for f, r in covered_keys),
        'covered_endpoint_count': len(covered_keys),
        'sampling_rate_by_call_site': round(
            len(covered_lines) / float(len(inst) or 1), 4),
        'sampling_rate_by_endpoint': round(
            len(covered_keys) / float(len(endpoints) or 1), 4),
        'uncovered_faces': [
            {'face': 'quality.py 质检域（%d 处，本探针覆盖 1 处）'
                     % by_file.get('app/main/quality.py', {}).get('inst', 0),
             'why': '需质检单据夹具与 inspector 角色链路'},
            {'face': 'production_center.py 生产中心（%d 处）'
                     % by_file.get('app/main/production_center.py', {}).get('inst', 0),
             'why': '实例生成/技术分解/工序执行三端点需批次实例夹具'},
            {'face': 'models.py `SystemConfig.set`（%d 处，服务层）'
                     % by_file.get('app/models.py', {}).get('inst', 0),
             'why': '配置写入走服务层，不经 HTTP 写端点'},
            {'face': 'purchase.py `_log_purchase` / mes_service.py（各 1 处，服务层）',
             'why': '被业务链内部调用，动作数取决于链内分支'},
            {'face': '导入型端点（import_finished_products / import_raw_materials 等）',
             'why': '「动作数」是行数而非 1，需成对判据（好行数=审计行数）'},
            {'face': '无 target_model/target_id 的 %d 处'
                     % len([s for s in sites if not s['has_target_id']]),
             'why': '这些调用点无法满足「target_id 正确」这一半判据（口径缺口，需单独登记）'},
        ],
    }


# --------------------------------------------------------------------- 判据（纯函数）
def eval_checks(results, coverage):
    """把判据写成结构化断言（可被 `--selftest` 用合成输入对拍）。"""
    A = []

    def add(aid, title, expected, actual, verdict, evidence='',
            evidence_kind='behavior_verified', note='', finding=False):
        A.append({'id': aid, 'title': title, 'expected': expected, 'actual': actual,
                  'verdict': verdict, 'evidence': evidence, 'evidence_kind': evidence_kind,
                  'note': note, 'finding': finding})
        return A[-1]

    by_id = {r.get('scenario'): r for r in results}
    core = [s for s in SCENARIOS if s['group'] == 'core']
    fail = [s for s in SCENARIOS if s['group'] == 'failure']
    cand = [s for s in SCENARIOS if s['group'] == 'finding-candidate']

    # ---------------------------------------------------------------- 前后两个数
    deltas = {s['id']: (by_id.get(s['id']) or {}).get('delta', {}).get('audit_log')
              for s in SCENARIOS}
    rows_new = {s['id']: len((by_id.get(s['id']) or {}).get('new_audit_rows') or [])
                for s in SCENARIOS}
    before_counts = {s['id']: ((by_id.get(s['id']) or {}).get('before') or {})
                     .get('audit_log', {}).get('count') for s in SCENARIOS}
    after_counts = {s['id']: ((by_id.get(s['id']) or {}).get('after') or {})
                    .get('audit_log', {}).get('count') for s in SCENARIOS}
    two_numbers_ok = all(
        deltas.get(s['id']) is not None and before_counts.get(s['id']) is not None
        and after_counts.get(s['id']) is not None for s in SCENARIOS)
    add('C-01.0(before-after)',
        '「前后两个数」：每个场景都给出 `audit_log` 的 before/after 行数与 Δ'
        '（成功路径 Δ>0、失败路径 Δ=0）⇒ 0 → >0 可复算',
        {'per_scenario': 'before / after / delta 三者齐备', 'covered_delta_sum': '>0'},
        {'before_counts': before_counts, 'after_counts': after_counts, 'delta': deltas,
         'new_rows_by_scenario': rows_new,
         'success_path_delta_sum': sum(v for k, v in (deltas or {}).items()
                                       if v is not None
                                       and k in [s['id'] for s in core + cand])},
        'passed' if two_numbers_ok else 'failed',
        evidence='探针 stdout + 各子场景 JSON before/after',
        note='口径：`SELECT COUNT(*) FROM audit_log`，前=请求前、后=请求后，同一子进程内')

    # ---------------------------------------------------------------- N≥3 端点（判据主体）
    def endpoint_ok(spec):
        r = by_id.get(spec['id']) or {}
        if r.get('fatal') or not r.get('before'):
            return False, {'reason': 'child_fatal_or_no_readings', 'fatal': r.get('fatal')}
        delta = (r.get('delta') or {}).get('audit_log')
        rows = r.get('new_audit_rows') or []
        target_delta = (r.get('delta') or {}).get('target')
        created_id = r.get('created_target_max_id')
        admin_id = ((r.get('fixture_ctx') or {}).get('admin'))
        checks = {
            'delta_eq_expected_rows': delta == 1 and len(rows) == 1,
            'action_match': bool(rows) and rows[0].get('action') == spec.get('action'),
            'target_model_match': bool(rows) and rows[0].get('target_model') == spec.get(
                'target_model'),
            'target_id_points_at_created_row': bool(rows) and created_id is not None
            and rows[0].get('target_id') == created_id,
            'target_row_created': target_delta == 1,
            'can_rollback_true': bool(rows) and rows[0].get('can_rollback') is True,
            'rollback_type_match': bool(rows) and rows[0].get('rollback_type') == spec.get(
                'rollback_type'),
            'user_id_is_actor': bool(rows) and admin_id is not None
            and rows[0].get('user_id') == admin_id,
        }
        detail = dict(checks)
        detail.update({'delta': delta, 'target_delta': target_delta,
                       'created_target_max_id': created_id,
                       'audit_row': (rows[0] if rows else None)})
        return all(checks.values()), detail

    ok_ids = []
    for spec in core:
        good, detail = endpoint_ok(spec)
        if good:
            ok_ids.append(spec['id'])
        add('C-01.1(%s)' % spec['id'],
            '%s：Δ`AuditLog` 行数 = 动作数（1）且 `action`/`target_model`/`target_id`/'
            '`can_rollback`/`rollback_type`/`user_id` 六项全符 —— `target_id` 必须等于该动作'
            '真正建出的那一行的 id' % spec['id'],
            {'delta': 1, 'action': spec.get('action'), 'target_model': spec.get('target_model'),
             'target_id': '= 新建行 id', 'can_rollback': True,
             'rollback_type': spec.get('rollback_type'), 'user_id': '= 操作者 id'},
            detail, 'passed' if good else 'failed',
            evidence=rel((by_id.get(spec['id']) or {}).get('out_file') or ''),
            note='调用点 %s' % spec.get('audit_call_site'))

    add('C-01.1(count>=%d)' % MIN_ENDPOINTS,
        '判据规模：**≥%d 个写端点**同时满足「Δ = 动作数 + target_model/target_id 正确」'
        '（C-01 的「0 → ≥1」形态；本探针给出 0 → %d）' % (MIN_ENDPOINTS, len(core)),
        {'endpoints_ok': '>=%d' % MIN_ENDPOINTS},
        {'endpoints_ok': len(ok_ids), 'endpoints_checked': [s['id'] for s in core],
         'ok': ok_ids},
        'passed' if len(ok_ids) >= MIN_ENDPOINTS else 'failed',
        evidence='见各 C-01.1(*) 的 evidence',
        note='判据只认「六项全符」的端点数，不接受「写了审计行」这种弱形态')

    # ---------------------------------------------------------------- 失败路径
    fail_detail = {}
    for spec in fail:
        r = by_id.get(spec['id']) or {}
        rows = r.get('new_audit_rows') or []
        delta = (r.get('delta') or {}).get('audit_log')
        target_delta = (r.get('delta') or {}).get('target')
        expect_target = spec.get('expect_target_delta')
        item = {'delta_audit': delta, 'new_rows': len(rows),
                'http_status': r.get('http_status'), 'http_raised': r.get('http_raised'),
                'target_delta': target_delta,
                'injection_fired': r.get('injection_fired'),
                'pass': (delta == 0 and len(rows) == 0
                         and (expect_target is None or target_delta == expect_target))}
        fail_detail[spec['id']] = item
    fail_ok = all(v['pass'] for v in fail_detail.values()) and len(fail_detail) == len(fail)
    add('C-01.2(failure-paths)',
        '阴性用例（必做）：**业务写失败 ⇒ `AuditLog` 不得新增**（Δ=0 且新增行数 0）——'
        '覆盖 5 类失败形态：入参解析失败 / 业务前置校验拒绝 / 真 NOT NULL 冲突 / '
        '唯一性预检拒绝 / **提交期**真 IntegrityError（审计与被审计动作同事务）',
        {'per_failure': 'Δaudit=0 且 new_rows=0', 'F5_target_delta': 0},
        fail_detail, 'passed' if fail_ok else 'failed',
        evidence='；'.join(rel((by_id.get(s['id']) or {}).get('out_file') or '') for s in fail),
        note='F5 额外要求 Δ目标表 = 0 ⇒ 证明审计行与被审计动作**同一事务**，动作失败审计不落库')

    # ---------------------------------------------------------------- 抽样率与覆盖面
    declared_sites = len([s for s in SCENARIOS if s.get('audit_call_site')])
    cov_ok = (coverage.get('auditlog_calls_raw') == 114
              and coverage.get('auditlog_instantiations') == 113
              and coverage.get('covered_call_site_count') == declared_sites
              and coverage.get('covered_endpoint_count') >= MIN_ENDPOINTS
              and coverage.get('endpoints_with_audit', 0) >= MIN_ENDPOINTS
              and bool(coverage.get('endpoints_with_audit'))
              and len(coverage.get('uncovered_faces') or []) >= 4)
    add('C-01.3(sampling)',
        '抽样率与未覆盖面登记：分母 = `app/**.py` 的 `AuditLog(` **114** 处'
        '（裸子串口径，含 `class AuditLog(` 1 处误计）⇒ **真实例化 113** 处；'
        '本探针覆盖 %d 个调用点 / %d 个含审计写入的真实端点（共 %d 个）；未覆盖面逐条登记'
        % (declared_sites, coverage.get('covered_endpoint_count', 0),
           coverage.get('endpoints_with_audit', 0)),
        {'auditlog_calls_raw': 114, 'auditlog_instantiations': 113,
         'covered_call_site_count': declared_sites, 'uncovered_faces': '>=4 条'},
        coverage, 'passed' if cov_ok else 'failed',
        evidence='只读遍历 app/**.py（调用点 → 所在 def → 最近 @bp.route）',
        evidence_kind='content_implementation',
        note='两个数必须同时给：114（与 34/35 同口径）与 113（排除类声明后的真实例化）')

    # ---------------------------------------------------------------- 真实库不变量
    allr = [r for r in results if r.get('scenario')]
    db_ok = bool(allr) and all(r.get('real_db_unchanged') and r.get('real_db_assert_ok')
                              for r in allr)
    add('C-01.4(db)',
        '不变量：全部场景全程真实库 app.db SHA256 不变（= 钉死值）',
        {'sha256': _env.REAL_DB_SHA256_EXPECTED, 'unchanged': True},
        {'per_scenario': {r.get('scenario'): {'unchanged': r.get('real_db_unchanged'),
                                              'assert_ok': r.get('real_db_assert_ok')}
                          for r in allr}},
        'passed' if db_ok else 'failed',
        evidence='每个子进程的 real_db_sha256_before/after + 父进程开工/收尾复核',
        note='一切库操作走带 RUN_ID 的副本（fixtures.make_isolated_app）')

    # ---------------------------------------------------------------- 发现（不计判据层）
    findings = {}
    for spec in cand:
        good, detail = endpoint_ok(spec)
        r = by_id.get(spec['id']) or {}
        rows = r.get('new_audit_rows') or []
        findings[spec['id']] = {
            'endpoint': spec.get('endpoint'), 'call_site': spec.get('audit_call_site'),
            'six_checks_all_ok': good,
            'delta': (r.get('delta') or {}).get('audit_log'),
            'created_target_max_id': r.get('created_target_max_id'),
            'audit_row': (rows[0] if rows else None),
            'detail': detail,
            'http_status': r.get('http_status'),
            'desc': spec.get('desc'),
        }
    nulls = [k for k, v in findings.items()
             if (v.get('audit_row') or {}).get('target_id') is None
             and (v.get('audit_row') or {}).get('target_model')]
    find_ok = bool(findings) and not nulls      # 「无缺陷」才算 passed；有缺陷 ⇒ failed（但属发现）
    add('C-01-finding(target_id-null)',
        '发现（产品面，非探针缺陷）：`db.session.add(x)` 后**未 `flush()`** 就取 `x.id` 的调用点'
        '（E4 `routes.py:5149→5159`、E5 `quality.py:625→635`）⇒ 审计行 `target_model` 正确但 '
        '`target_id` 落库为 **NULL**，而 `can_rollback=True` ⇒ 「可回滚」的审计轨迹指不到目标行',
        {'target_id': '= 新建行 id（非 NULL）'},
        {'findings': findings, 'null_target_id_scenarios': nulls,
         'real_db_corroboration': coverage.get('real_db_audit_corroboration')},
        'passed' if find_ok else 'failed',
        evidence='；'.join(rel((by_id.get(s.get('id')) or {}).get('out_file') or '')
                           for s in cand),
        evidence_kind='behavior_verified', finding=True,
        note='本项**不计入判据层通过数与退出码**（GAP_ASSERTION_IDS）：它是被测方的缺陷登记，'
             '不是规格判据；真库旁证见 C-01.3(sampling) 与 JSON `finding_corroboration`')

    criteria = [r for r in A if r['id'] not in GAP_ASSERTION_IDS]
    failed = [r['id'] for r in criteria if r['verdict'] != 'passed']
    return A, failed


def build_findings_summary(assertions, coverage, corroboration):
    """给下游（V-16 改进报告）用的机读发现摘要：缺陷面 + 触发场景 + 真库旁证 + 机制坐标。"""
    find = next((r for r in assertions if r.get('finding')), None) or {}
    rows = ((find.get('actual') or {}).get('findings') or {})
    nulls = {k: {'endpoint': v.get('endpoint'), 'call_site': v.get('call_site'),
                 'audit_row': v.get('audit_row'),
                 'created_target_max_id': v.get('created_target_max_id')}
             for k, v in rows.items()
             if (v.get('audit_row') or {}).get('target_id') is None
             and (v.get('audit_row') or {}).get('target_model')}
    return {
        'id': 'C-01-finding(target_id-null)',
        'verdict': find.get('verdict'),
        'gates_exit_code': False,
        'one_line': '审计行写入时 `target_id` 落库为 NULL：`db.session.add(x)` 之后**未 `flush()`** '
                    '就取 `x.id`（此时 `x.id` 仍是 None），而 `can_rollback=True` ⇒ '
                    '「可回滚」的审计轨迹指不到目标行，回滚动作无法定位对象。',
        'target_id_null_scenarios': nulls,
        'mechanism': [
            {'call_site': 'app/main/routes.py:5152',
             'add_line': 'app/main/routes.py:5149（db.session.add(product)，无 flush()）',
             'target_id_line': 'app/main/routes.py:5159（target_id=product.id）'},
            {'call_site': 'app/main/quality.py:628',
             'add_line': 'app/main/quality.py:625（db.session.add(task)，无 flush()）',
             'target_id_line': 'app/main/quality.py:635（target_id=task.id）'},
        ],
        'contrast_control': '同一判据下 E1/E2/E3（调用点前**有** flush：routes.py:1734 / :4420 / '
                            ':564）的 target_id 全部正确（2 / 19 / 64）⇒ 唯一结构性差异就是 '
                            'flush 时机，构成机制级对照',
        'real_db_corroboration': corroboration,
        'coverage_note': '本发现来自 5/113 调用点抽样；真库 73 行审计里 40 行 target_id 为 NULL'
                         '（其中 10 行 can_rollback=True）⇒ 该形态在真库中已是多数',
    }


def corroborate_real_db():
    """只读旁证：真实库 `audit_log` 里 `target_id IS NULL` 的规模（**只读连接**，不复制）。"""
    import sqlite3
    out = {'tool': 'sqlite3 只读 URI（mode=ro）', 'table': AUDIT_TABLE}
    try:
        con = sqlite3.connect('file:%s?mode=ro' % _env.REAL_DB.replace('\\', '/'), uri=True)
        try:
            total = con.execute('select count(*) from audit_log').fetchone()[0]
            nulls = con.execute('select count(*) from audit_log where target_id is null'
                                ).fetchone()[0]
            rollback_null = con.execute(
                'select count(*) from audit_log where target_id is null and can_rollback = 1'
            ).fetchone()[0]
            models = con.execute(
                'select target_model, count(*) from audit_log where target_id is null '
                'and target_model is not null group by target_model order by 2 desc'
            ).fetchall()
        finally:
            con.close()
        out.update({'audit_rows_total': int(total), 'target_id_null': int(nulls),
                    'can_rollback_true_but_target_id_null': int(rollback_null),
                    'null_target_id_by_model': {m: int(c) for m, c in models},
                    'ok': True})
    except Exception as e:                                      # noqa: BLE001
        out.update({'ok': False, 'error': '%s: %s' % (e.__class__.__name__, e)})
    return out


# --------------------------------------------------------------------- 父进程编排
def full_run(args):
    started = time.strftime('%Y-%m-%d %H:%M:%S')
    real_before = _env.assert_real_db_untouched('r2_c01 开工')
    corroboration = corroborate_real_db()
    print('=' * 86)
    print('[c01] C-01 审计写入增量断言探针（J 域通知与审计）')
    print('[c01] run_id=%s  time=%s' % (_env.RUN_ID, started))
    print('[c01] 真实库 %s  sha256=%s' % (rel(args.real_db), real_before))
    print('[c01] 分母口径：`AuditLog(` 裸子串 = 114（含 class 声明 1 处）⇒ 真实例化 113')
    if corroboration.get('ok'):
        print('[c01] 真库旁证（只读）：audit_log %d 行，target_id IS NULL %d 行，'
              '其中 can_rollback=True %d 行'
              % (corroboration['audit_rows_total'], corroboration['target_id_null'],
                 corroboration['can_rollback_true_but_target_id_null']))
    print('=' * 86)

    results = []
    for spec in SCENARIOS:
        out = run_scenario(spec, timeout=args.timeout)
        p = out['payload'] or {}
        p['scenario'] = p.get('scenario') or spec['id']
        p['out_file'] = out['out_file']
        p['child_exit_code'] = out['exit_code']
        results.append(p)
        rows = p.get('new_audit_rows') or []
        print('  [CASE] %-24s %-4s http=%-4s Δaudit=%-4s new_rows=%d target_Δ=%s %s'
              % (spec['id'], spec['group'][:4], p.get('http_status'),
                 (p.get('delta') or {}).get('audit_log'), len(rows),
                 (p.get('delta') or {}).get('target'),
                 ('target_id=%s' % rows[0].get('target_id')) if rows else ''))
        if p.get('fatal'):
            print('         FATAL: %s' % str(p.get('fatal'))[-300:])

    real_after = _env.assert_real_db_untouched('r2_c01 收尾')
    covered = [{'file': s['audit_call_site'].split(':')[0],
                'line': int(s['audit_call_site'].split(':')[1])}
               for s in SCENARIOS if s.get('audit_call_site')]
    coverage = build_coverage(covered)
    coverage['real_db_audit_corroboration'] = corroboration
    assertions, failed = eval_checks(results, coverage)

    print('')
    print('-' * 86)
    print('[c01] 判据层')
    for r in assertions:
        flag = '  [FINDING]' if r.get('finding') else ''
        print('  %-34s %-8s %-22s %s%s' % (r['id'], r['verdict'].upper(),
                                           r['evidence_kind'], r['title'][:52], flag))
    print('')
    for r in assertions:
        if r['verdict'] not in ('passed', 'blocked'):
            print('  [%s] %s' % ('FINDING-FAIL' if r.get('finding') else 'FAIL', r['id']))
            print('         expected=%s' % json.dumps(r['expected'], ensure_ascii=False)[:400])
            print('         actual  =%s' % json.dumps(r['actual'], ensure_ascii=False)[:700])
            if r['note']:
                print('         note    =%s' % r['note'][:300])
    n_pass = len([r for r in assertions if r['verdict'] == 'passed'
                  and r['id'] not in GAP_ASSERTION_IDS])
    n_tot = len([r for r in assertions if r['id'] not in GAP_ASSERTION_IDS])
    print('')
    print('[c01] 判据层：%d/%d 通过；失败=%s' % (n_pass, n_tot, failed or '无'))
    print('[c01] 抽样率：调用点 %d/%d = %.2f%%；端点 %d/%d = %.2f%%（未覆盖面 %d 条已登记）'
          % (coverage['covered_call_site_count'], coverage['auditlog_instantiations'],
             100.0 * coverage['sampling_rate_by_call_site'],
             coverage['covered_endpoint_count'], coverage['endpoints_with_audit'],
             100.0 * coverage['sampling_rate_by_endpoint'],
             len(coverage.get('uncovered_faces') or [])))
    for r in assertions:
        if r.get('finding'):
            nulls = [k for k, v in (r['actual'].get('findings') or {}).items()
                     if (v.get('audit_row') or {}).get('target_id') is None
                     and (v.get('audit_row') or {}).get('target_model')]
            print('[c01] 发现（不计判据层）：%s → target_id IS NULL 的场景 = %s'
                  % (r['id'], nulls or '无'))
    print('[c01] 真实库 app.db：before=%s after=%s 不变=%s'
          % (real_before[:16] + '...', real_after[:16] + '...', real_before == real_after))
    verdict = 1 if failed else 0
    print('[c01] exit=%d' % verdict)
    print('=' * 86)

    payload = {
        'run_id': _env.RUN_ID, 'started': started,
        'probe': 'test-reports-2026-10/harness/r2_audit_probe.py',
        'task': 'V-05 / t6 (C-01)',
        'denominators': {'auditlog_calls_raw': coverage['auditlog_calls_raw'],
                         'auditlog_instantiations': coverage['auditlog_instantiations'],
                         'endpoints_with_audit': coverage['endpoints_with_audit']},
        'real_db': {'path': rel(args.real_db), 'sha256_before': real_before,
                    'sha256_after': real_after, 'unchanged': real_before == real_after,
                    'pinned': _env.REAL_DB_SHA256_EXPECTED},
        'coverage': coverage,
        'finding_corroboration': corroboration,
        'scenarios': results,
        'assertions': assertions,
        'criteria_failed': failed, 'criteria_passed': n_pass, 'criteria_total': n_tot,
        'findings': [r['actual'] for r in assertions if r.get('finding')],
        'findings_summary': build_findings_summary(assertions, coverage, corroboration),
        'blocked_faces': [{'id': 'C-01-L5(notify-delivery)', 'status': 'blocked',
                           'reason': '通知是否送达属 L5 人工/外部通道，本轮不判（35 §4 C-01 边界）'},
                          {'id': 'C-01-coverage(113-5)', 'status': 'partial',
                           'reason': '113 处例化仅抽样 5 处；未覆盖面逐条登记在 coverage.uncovered_faces'}],
        'exit_code': verdict,
        'evidence_kind': 'behavior_verified',
        'search_domain': {
            'app/**.py 内容搜索 AuditLog(': '%d 处（裸子串）/ %d 处（真实例化）'
                                          % (coverage['auditlog_calls_raw'],
                                             coverage['auditlog_instantiations']),
            '被测 5 个端点的调用点': [s['audit_call_site'] for s in SCENARIOS
                                      if s.get('audit_call_site')],
            '真实库 audit_log': 'sqlite3 mode=ro 只读读 73 行（不复制、不写）',
        },
        'exclude_basenames': ['r2_audit_probe.py（判定脚本自身）', 'captain_r2_*.py',
                              'reconcile_r2.py', 'improve_plan.py', 'analysis_ledger.py',
                              'evidence/** 度量产物'],
        'del_what_goes_red': '删掉任一被测端点的 `db.session.add(log)` ⇒ 对应 C-01.1(*) 必红'
                             '（Δ=0）；把 `target_id=<x>.id` 改成写死值/None ⇒ 对应 C-01.1(*) 必红'
                             '（target_id 指不到新建行）；把失败路径的 rollback 去掉 ⇒ '
                             'C-01.2(failure-paths) 必红（审计行落库）；删抽样率登记 ⇒ '
                             'C-01.3(sampling) 必红',
        'four_injection_pitfalls_aligned': [
            '1) _env.run_child 是 python -B <argv>：argv 必带脚本路径（本文件写生成脚本到 .tmp 再跑）',
            '2) 注入不碰 create_app() 启动链：F5 只装 SQLAlchemy Session 的 before_flush 钩子',
            '3) 每个场景一份独立副本（fixtures.make_isolated_app(tag=场景名)）',
            '4) 授权开关逐场景传参并显式清空（extra_env={WMS_ALLOW_REAL_DB: ""}）',
        ],
    }
    if args.json_out:
        write_text(args.json_out, json.dumps(payload, ensure_ascii=False, indent=1))
    saved = _env.save_evidence('r2_audit_probe.json',
                               json.dumps(payload, ensure_ascii=False, indent=1))
    print('[c01] 机读结果已落盘 %s' % rel(saved))
    if args.json_out:
        print('[c01] --json-out 副本 %s' % rel(args.json_out))
    return verdict


# --------------------------------------------------------------------- 工具自检
def synthetic_scenario(spec_id, *, delta_audit=1, new_rows=1, action=None, target_model=None,
                       target_id='=created', created_id=101, can_rollback=True,
                       rollback_type='add', user_id=1, target_delta=1, fatal=None):
    spec = next(s for s in SCENARIOS if s['id'] == spec_id)
    rows = []
    if new_rows:
        rows.append({'id': 900 + new_rows, 'user_id': user_id,
                     'action': action if action is not None else spec.get('action'),
                     'target_model': (target_model if target_model is not None
                                      else spec.get('target_model')),
                     'target_id': (created_id if target_id == '=created' else target_id),
                     'can_rollback': can_rollback,
                     'rollback_type': (rollback_type if rollback_type is not None
                                       else spec.get('rollback_type')),
                     'details': '(synthetic)'})
    before = {'audit_log': {'count': 73, 'max_id': 873},
              'target': {'count': 5, 'max_id': 5}, 'target_table': spec.get('target_table')}
    after = {'audit_log': {'count': 73 + (delta_audit or 0), 'max_id': 873 + (delta_audit or 0)},
             'target': {'count': 5 + (target_delta or 0), 'max_id': 5 + (target_delta or 0)}}
    out = {'scenario': spec_id, 'group': spec.get('group'), 'before': before, 'after': after,
           'delta': {'audit_log': delta_audit, 'target': target_delta},
           'new_audit_rows': rows, 'created_target_max_id': created_id,
           'created_target_delta': target_delta, 'http_status': 200,
           'fixture_ctx': {'admin': 1}, 'out_file': '(synthetic)',
           'real_db_unchanged': True, 'real_db_assert_ok': True}
    if fatal:
        out['fatal'] = fatal
    return out


def synth_coverage():
    declared = len([s for s in SCENARIOS if s.get('audit_call_site')])
    return {'auditlog_calls_raw': 114, 'auditlog_instantiations': 113,
            'endpoints_with_audit': 90, 'covered_call_site_count': declared,
            'covered_endpoint_count': 5, 'sampling_rate_by_call_site': 0.0442,
            'sampling_rate_by_endpoint': 0.0556,
            'sites_without_target_id': 23, 'uncovered_faces': [{'face': 'x', 'why': 'y'}] * 6}


def green_results():
    out = []
    for spec in SCENARIOS:
        if spec['group'] == 'core':
            out.append(synthetic_scenario(spec['id']))
        elif spec['group'] == 'finding-candidate':
            #: 真实形态：审计行写了、target_id 为 None ⇒ 发现项红、判据层不受影响
            out.append(synthetic_scenario(spec['id'], target_id=None))
        else:
            out.append(synthetic_scenario(spec['id'], delta_audit=0, new_rows=0,
                                          target_delta=0))
    return out


def selftest(args):
    """自检：用**合成读数**对拍判据函数，逐条给出预期判定（含「必须报红」的阳性样本）。

    证明的不是「真实代码通过了」，而是**本探针的判据会红**：
    ① `green`：三组读数全符预期 ⇒ 判据层全过、exit 0（发现项虽红但不计入）；
    ② `audit-missing`：把一个成功端点的 Δaudit 改成 0 ⇒ 该 `C-01.1(*)` 必红 + 计数判据必红；
    ③ `target-id-wrong`：`target_id` 写成别的 id ⇒ 该 `C-01.1(*)` 必红（计数判据一并红，属正确联动）；
    ④ `failure-wrote-audit`：失败路径写了 1 行审计 ⇒ `C-01.2(failure-paths)` 必红；
    ⑤ `sampling-missing`：抽样分母/覆盖数缺失 ⇒ `C-01.3(sampling)` 必红。
    """
    checks = []
    real_before = _env.assert_real_db_untouched('r2_c01 selftest')
    print('=' * 86)
    print('[selftest] 判据函数对拍（合成读数 ⇒ 预期判定）')
    print('=' * 86)

    def run_case(tag, results, coverage, expect_failed, expect_exit):
        assertions, failed = eval_checks(results, coverage)
        got = {r['id']: r['verdict'] for r in assertions}
        ok_fail = set(failed) == set(expect_failed)
        ok_exit = (0 if not failed else 1) == expect_exit
        good = ok_fail and ok_exit
        checks.append({'tag': tag, 'failed': failed, 'expect_failed': list(expect_failed),
                       'exit': expect_exit, 'ok': good,
                       'verdicts': got})
        print('  [%s] %-22s failed=%-58s 期望=%-58s exit=%s(期望 %s)'
              % ('PASS' if good else 'FAIL', tag, json.dumps(failed),
                 json.dumps(sorted(expect_failed)), 0 if not failed else 1, expect_exit))
        if not good:
            print('         verdicts=%s' % json.dumps(got, ensure_ascii=False))
        return good

    ok_all = True
    ok_all &= run_case('green', green_results(), synth_coverage(), set(), 0)

    # 阳性样本①：成功端点没写审计 ⇒ 该端点判据 + 计数判据必红
    r = green_results()
    for x in r:
        if x['scenario'] == 'E2-task-add':
            x.update(synthetic_scenario('E2-task-add', delta_audit=0, new_rows=0,
                                        target_delta=1))
    ok_all &= run_case('audit-missing', r, synth_coverage(),
                       {'C-01.1(E2-task-add)', 'C-01.1(count>=3)'}, 1)

    # 阳性样本②：target_id 指不到新建行 ⇒ 该端点判据必红
    #: 注：该端点掉出 OK 集合后，N≥3 的计数判据**同时**失去前提 ⇒ 一并报红是**正确**行为
    #: （自检要的是「判据会红」，不是「只红一条」）。
    r = green_results()
    for x in r:
        if x['scenario'] == 'E3-employee-add':
            x.update(synthetic_scenario('E3-employee-add', target_id=999999))
    ok_all &= run_case('target-id-wrong', r, synth_coverage(),
                       {'C-01.1(E3-employee-add)', 'C-01.1(count>=3)'}, 1)

    # 阳性样本③：失败路径写了审计行 ⇒ C-01.2 必红
    r = green_results()
    for x in r:
        if x['scenario'] == 'F1-bonus-bad-date':
            x.update(synthetic_scenario('F1-bonus-bad-date', delta_audit=1, new_rows=1,
                                        target_delta=0))
    ok_all &= run_case('failure-wrote-audit', r, synth_coverage(),
                       {'C-01.2(failure-paths)'}, 1)

    # 阳性样本④：抽样率登记缺失 ⇒ C-01.3 必红
    cov = synth_coverage()
    cov['auditlog_instantiations'] = 999
    cov['covered_call_site_count'] = 0
    cov['uncovered_faces'] = []
    ok_all &= run_case('sampling-missing', green_results(), cov, {'C-01.3(sampling)'}, 1)

    real_ok = _env.sha256_file(_env.REAL_DB) == real_before == _env.REAL_DB_SHA256_EXPECTED
    ok_all &= real_ok
    print('  [%s] 真实库 app.db SHA256 = %s（钉死值）'
          % ('PASS' if real_ok else 'FAIL', real_before))
    payload = {'mode': 'selftest', 'run_id': _env.RUN_ID, 'checks': checks,
               'real_db_sha256': real_before, 'real_db_ok': real_ok,
               'verdict': 'passed' if ok_all else 'failed'}
    saved = _env.save_evidence('r2_audit_probe_selftest.json',
                               json.dumps(payload, ensure_ascii=False, indent=1))
    print('[selftest] 结论：%s（1 组全绿 + 4 组必红对拍）' % ('OK' if ok_all else 'FAIL'))
    print('[selftest] 证据已落盘 %s' % rel(saved))
    print('[selftest] exit=%d' % (0 if ok_all else 1))
    return 0 if ok_all else 1


# --------------------------------------------------------------------- 双跑一致
def compare_runs(path_a, path_b):
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
        sc = {s.get('scenario'): s for s in (p.get('scenarios') or [])}
        return {k: {'delta_audit': (v.get('delta') or {}).get('audit_log'),
                    'new_rows': len(v.get('new_audit_rows') or []),
                    'target_id': ((v.get('new_audit_rows') or [{}])[0].get('target_id')
                                  if v.get('new_audit_rows') else None),
                    'http_status': v.get('http_status'),
                    'action': ((v.get('new_audit_rows') or [{}])[0].get('action')
                               if v.get('new_audit_rows') else None)}
                for k, v in sc.items()}

    ra, rb = readings(a), readings(b)
    out['readings_a'] = ra
    out['readings_b'] = rb
    out['reading_diff'] = {k: [ra.get(k), rb.get(k)] for k in sorted(set(ra) | set(rb))
                           if ra.get(k) != rb.get(k)}
    out['coverage_a'] = {'covered_call_site_count':
                         (a.get('coverage') or {}).get('covered_call_site_count'),
                         'auditlog_instantiations':
                         (a.get('coverage') or {}).get('auditlog_instantiations')}
    out['coverage_b'] = {'covered_call_site_count':
                         (b.get('coverage') or {}).get('covered_call_site_count'),
                         'auditlog_instantiations':
                         (b.get('coverage') or {}).get('auditlog_instantiations')}
    out['identical'] = (not out['only_in_a'] and not out['only_in_b']
                        and not out['verdict_diff'] and not out['reading_diff']
                        and out['coverage_a'] == out['coverage_b'])
    out['criteria_a'] = {'passed': a.get('criteria_passed'), 'total': a.get('criteria_total'),
                         'failed': a.get('criteria_failed')}
    out['criteria_b'] = {'passed': b.get('criteria_passed'), 'total': b.get('criteria_total'),
                         'failed': b.get('criteria_failed')}
    saved = _env.save_evidence('r2_audit_probe_compare.json',
                               json.dumps(out, ensure_ascii=False, indent=1))
    print('[compare] A=%s B=%s' % (out['run_id_a'], out['run_id_b']))
    print('[compare] only_in_a=%s only_in_b=%s verdict_diff=%s'
          % (out['only_in_a'], out['only_in_b'], out['verdict_diff']))
    print('[compare] reading_diff=%s' % json.dumps(out['reading_diff'], ensure_ascii=False)[:300])
    print('[compare] coverage 一致 = %s' % (out['coverage_a'] == out['coverage_b']))
    print('[compare] 双跑一致 = %s' % out['identical'])
    print('[compare] 证据已落盘 %s' % rel(saved))
    return 0 if out['identical'] else 1


def main():
    ap = argparse.ArgumentParser(description='C-01 审计写入增量断言探针（V-05 / t6）')
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
