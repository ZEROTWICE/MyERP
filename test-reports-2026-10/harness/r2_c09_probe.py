#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""r2_c09_probe.py —— C-09「工价版本取值 + 三策略派工可区分」探针（V-11 / t12）。

任务契约（`35-第2轮测试总方案（定稿）.md` §4 C-09 行 / `33` §3.1 `D-09.1…4` 五元组）：

* **inScope**：本文件（`test-reports-2026-10/harness/r2_c09_probe.py`）。**不得改 `app/**`**，
  也**不得改 `harness/fixtures.py`**（V-04 已完成并冻结于 64496 B）。
* **四条判据（五元组：业务语义 → 载体 `file:line` → 期望值 → 变红条件 → 证伪条件）**：

| 判据 | 内容 | 载体 |
| --- | --- | --- |
| `D-09.1` | 工价取值口径 = `effective_date <= 当日` 中 `effective_date` **最新**的一版（**不是** `version` 最大、**不是** `is_current=True`） | `routes.py:2717-2720` |
| `D-09.2` | 报工记录价格是「**报工时点取价并冻结**」还是「按 `process_id` **现值**」⇒ **必须实测后二选一写死**，并给「新增版本前 A / 新增版本后 A′」两个数 | 计件式 `mes_service.py:1819`；取价 `routes.py:2717`（另 `:3902`/`:4020` 同口径） |
| `D-09.3` | 列表页只出**最新有效版**（`max(effective_date)` 且 `<= today+1`） | `routes.py:762-776` |
| `D-09.4` | `fixed` / `weighted` / `round_robin` 三策略在同一夹具下产出**两两可区分**的员工序列 | `models.py:2511`；分派 `routes.py:8780`（fixed）/`:8783-8788`（weighted）/`:8789-8791`（round_robin） |

* **⚠ 关键（必须带 `weight ≥ 2` 成员）**：`models.py:2537` 的 `weight` 默认 **1**
  ⇒ 全员 `weight=1` 时 `weighted` 池 = `[A,B,C]`，**与 `round_robin` 数学同解**
  ⇒ 该判据恒真无信息量。本探针的**主夹具**用 `A=2, B=1, C=1`；
  另做**权重对照实验**（全员 1）并**如实登记「本夹具下二者不可区分」——不得记 PASS**。
* **同策略两次稳定**：`weighted` 场景连开两个批次，两次序列必须相同。
* **工价两版夹具（P-3）**：V1(`D-30`,10) / V2(`D-10`,20) / **V3(`D+10`,99) 未来生效**。
* **verify**：探针 `--selftest` + 权重对照实验 + 双跑一致 + 真库前后指纹。

## 实测结果（本文件实跑；**14/16 通过**，失败 2 条**全是产品面缺口**，exit=1）

| 判据 | 结果 | 实测读数 |
| --- | --- | --- |
| `D-09.1.a` 口径本体（具名载体语句） | **PASS**（content_implementation） | `filter(process_code==code, effective_date <= end_of_day+1d).order_by(effective_date.desc()).first()` ⇒ 取到 **V2(id=3488, 20.0)**；对照 `order_by(version.desc())` 会取到 V3(99) ⇒ 证明口径是「最新生效」而非「最大版本号」 |
| `D-09.1.b` 具名载体**可达性** | **GAP(product)** | `POST /production_records/import` 实测 `成功导入 0 条记录，1 条记录导入失败：处理记录时出错: 'notes'` ⇒ **任何行都进不去**：`ExcelGenerator.parse_production_record_data`（`excel_generator.py:326-343`）返回的 dict 只有 `date/employee_id/process_code/quantity`，而 `routes.py:2733` 读 `data['notes']` ⇒ `KeyError: 'notes'` 被逐行 `except` 吞掉 |
| `D-09.1.c` 三处取价点**口径一致性** | **GAP(product)** | 同类取价共三处：`routes.py:2717-2720` 用「生效日最新」，而 `routes.py:3902`（奖惩导入）/`:4020`（任务导入）用 `filter_by(process_code=…).first()`（**无生效日过滤、无排序**）⇒ 用可达的 `/tasks/import` 实测取到 **V1(id=3487, 10.0)**（最早那版），与 `:2717` 的 V2 **不一致** |
| `D-09.1.d` 未来版排除（证伪条件） | **PASS** | V3(`D+10`, 99, `version=3`, `is_current=True`) 在**两条路径**下都未被取到 ⇒ 判据非恒真亦非恒假（错的是「选哪一版」，不是「未来版混进来」） |
| `D-09.2` 报工价格口径（**必须写死**） | **PASS** | 实测登记 = **`frozen_at_report_time`（报工时点取价并冻结）**：`A = 60.0`（= 3 × 20），新增一版「今日生效 99」后 **`A′ = 60.0` 不变**（若按现值应为 297.0）⇒ **新增版本不改写存量计件工资**。机制：`ProductionRecord.process_id` 是指向 **process_price 版本行**的外键（`routes.py:1206` / 计件 `mes_service.py:1819` 读 `record.process.price`） |
| `D-09.3` 列表只出最新有效版 | **PASS** | `/process_prices?search=<code>` 在 V1/V2 两版下恰 **1 行**、单价 `20.00`、生效日 `2026-09-27`（V2）；`10.00` 不出现 |
| `D-09.3` 未来生效回落（证伪条件） | **PASS** | V2 改为未来生效 ⇒ 列表回落到 **V1**（`10.00` / `2026-09-07`），`20.00` 不出现 |
| `D-09.4` `fixed` | **PASS** | 序列 = `A,A,A,A,A,A` |
| `D-09.4` `round_robin` | **PASS** | 序列 = `A,B,C,A,B,C` |
| `D-09.4` `weighted`（**weight≥2**） | **PASS** | 夹具 A=2,B=1,C=1 ⇒ 池 `[A,A,B,C]` ⇒ 序列 = `A,A,B,C,A,A`（第 5、6 位与 `round_robin` **不同**） |
| `D-09.4` 两两可区分 | **PASS** | 三条序列互不相同（distinct=3） |
| `D-09.4` 同策略两次稳定 | **PASS** | `weighted` 连开 2 个批次，两次序列**逐位相同** |
| `D-09.4` ⚠ 权重对照（全员 1） | **PASS（含义=如实登记「不可区分」）** | 全员 `weight=1` ⇒ `weighted` 序列 = `A,B,C,A,B,C` = `round_robin` ⇒ **数学同解、本夹具下不可区分**；本格通过的含义是「探针正确登记了不可区分」，**不是**「二者可区分」（`33` §3.2-①） |
| `C-09.db` / `C-09.probe-self-check` | **PASS** | 真库全程 `F5DA2306…0E0F065`；7 场景全部产出可解析读数 |

**两条产品面缺口的坐标（可直接进改进报告）**：
1. `app/utils/excel_generator.py:326-343` 与 `app/main/routes.py:2733` —— 解析器产出无 `notes`
   键、端点却读 `data['notes']` ⇒ `/production_records/import` **100% 行失败**（且被行级
   `except` 静默成「处理记录时出错」，响应仍是 `success: true`）。
2. `app/main/routes.py:3902` / `:4020` —— 同功能取价用 `filter_by(process_code=…).first()`
   （无生效日过滤、无排序）⇒ 与 `:2717-2720` 的「最新生效」口径**不一致**，实测取到最早版。

## 探针自纠（双跑暴露的夹具坑）

`employee_id` 为 `String(20)`，而夹具前缀由 `RUN_ID` 生成：单跑 `r2-exec-b4-c09` 时前缀 17 字符
可容纳 `label+index`，双跑 `r2-exec-b4-c09-runA` 时前缀正好 20 字符 ⇒ `('%s%s%d')[:20]`
把 `label+index` **截掉**，三名员工拿到**同一个** `employee_id` ⇒ UNIQUE 冲突、4 个策略场景
整体 fatal、`C-09.db`/`C-09.probe-self-check` 连带变红。已把 tag 固定截到 14 字符并加**夹具自检**
（撞号即 `AssertionError`）。教训：**双跑用更长的 RUN_ID 是发现夹具唯一性缺陷的必要动作**。

## 用法（仓库根目录；解释器绝对路径，`28` §5-1 / `40` R-4）

```powershell
$py = 'F:\Miniconda\envs\wage\python.exe'
$env:HARNESS_RUN_ID = 'r2-exec-b4-c09'
& $py -B test-reports-2026-10\harness\r2_c09_probe.py                 # 判据层
& $py -B test-reports-2026-10\harness\r2_c09_probe.py --selftest      # 判据会报红
& $py -B test-reports-2026-10\harness\r2_c09_probe.py --json-out a.json
& $py -B test-reports-2026-10\harness\r2_c09_probe.py --compare a.json b.json
```

退出码：`0` = 判据层全过；`1` = 任一判据失败。红点用 `gap_owner` 标明归属
（`product` = 被测方缺口 / `probe` = 探针自身问题）。
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

RESULT_MARKER = '##R2C09-RESULT##'
REPO_ROOT = _env.REPO_ROOT
DEFAULT_REAL_DB = _env.REAL_DB
ALLOW_ENV = 'WMS_ALLOW_REAL_DB'

#: 三策略的具名序列（由夹具决定；见各场景的 desc）
STRATEGIES = ('fixed', 'weighted', 'round_robin')

SCENARIOS = [
    {
        'id': 'P1-price-version', 'kind': 'price-version', 'group': 'D-09.1+D-09.2',
        'desc': 'D-09.1（取价口径）+ D-09.2（价格冻结口径）**同批**实测：V1(D-30,10) / '
                'V2(D-10,20) / V3(D+10,99 未来生效) ⇒ 报工记录必须取 V2；再新增 V4(今日生效,99) '
                '看同一记录的计件额是否被改写',
        'endpoint': '/production_records/import', 'file_line': 'routes.py:2717-2720',
        'quantity': 3,
    },
    {
        'id': 'P2-price-list', 'kind': 'price-list', 'group': 'D-09.3',
        'desc': 'D-09.3：两版（V1 过去 / V2 过去）⇒ 列表只出 1 行且为 V2',
        'versions': [('V1', -30, 10.0), ('V2', -10, 20.0)],
        'expect_rows': 1, 'expect_price': '20.00', 'expect_version': 'V2',
        'file_line': 'routes.py:762-776',
    },
    {
        'id': 'P3-price-list-future', 'kind': 'price-list', 'group': 'D-09.3-control',
        'desc': 'D-09.3 阴性对照：V2 改为**未来生效** ⇒ 列表必须回落到 V1（证明取的是「有效」'
                '而非「最大版本号」）',
        'versions': [('V1', -30, 10.0), ('V2', +10, 20.0)],
        'expect_rows': 1, 'expect_price': '10.00', 'expect_version': 'V1',
        'file_line': 'routes.py:762-776',
    },
    {
        'id': 'S-fixed', 'kind': 'strategy', 'group': 'D-09.4',
        'strategy': 'fixed', 'weights': {'A': 2, 'B': 1, 'C': 1}, 'batches': 1,
        'expect_sequence': ['A', 'A', 'A', 'A', 'A', 'A'],
        'desc': 'fixed：永远取 sequence 最小者 ⇒ A×6（`routes.py:8780-8782`）',
    },
    {
        'id': 'S-round-robin', 'kind': 'strategy', 'group': 'D-09.4',
        'strategy': 'round_robin', 'weights': {'A': 2, 'B': 1, 'C': 1}, 'batches': 1,
        'expect_sequence': ['A', 'B', 'C', 'A', 'B', 'C'],
        'desc': 'round_robin：按 sequence 轮询 ⇒ A,B,C,A,B,C（`routes.py:8789-8791`）；'
                '成员权重**不影响**该路径（对照用）',
    },
    {
        'id': 'S-weighted', 'kind': 'strategy', 'group': 'D-09.4',
        'strategy': 'weighted', 'weights': {'A': 2, 'B': 1, 'C': 1}, 'batches': 2,
        'expect_sequence': ['A', 'A', 'B', 'C', 'A', 'A'],
        'desc': 'weighted：池 `[A,A,B,C]` 轮转 ⇒ A,A,B,C,A,A（`routes.py:8783-8788`）；'
                '连开 2 个批次验证「**同策略两次稳定**」',
    },
    {
        'id': 'S-weighted-all-weight-1', 'kind': 'strategy', 'group': 'D-09.4-control',
        'strategy': 'weighted', 'weights': {'A': 1, 'B': 1, 'C': 1}, 'batches': 1,
        'expect_sequence': None,
        'desc': '⚠ 权重对照实验（全员 weight=1，`models.py:2537` 默认值）：'
                'weighted 池退化为 `[A,B,C]` ⇒ **与 round_robin 数学同解** ⇒ '
                '本夹具下该格**只能登记「不可区分」，不得记 PASS**',
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
"""r2_c09_child.py —— C-09 子场景（由 `r2_c09_probe.py` 生成到 `.tmp/<RUN_ID>/c09/child/`）。

参数经环境变量传入：`C09_SPEC`（JSON）/ `C09_RUN_ID` / `C09_HARNESS_DIR` /
`C09_SCRIPTS_DIR` / `C09_REPO_ROOT`。输出一行 `##R2C09-RESULT##<json>`。
"""
import io
import json
import os
import re
import sys
import traceback
from datetime import date, datetime, timedelta

HARNESS_DIR = os.environ.get('C09_HARNESS_DIR') or ''
SCRIPTS_DIR = os.environ.get('C09_SCRIPTS_DIR') or ''
REPO_ROOT = os.environ.get('C09_REPO_ROOT') or ''
for _p in (HARNESS_DIR, SCRIPTS_DIR, REPO_ROOT):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)

import _env        # noqa: E402
import fixtures    # noqa: E402

SPEC = json.loads(os.environ.get('C09_SPEC') or '{}')
RUN_ID = os.environ.get('C09_RUN_ID') or _env.RUN_ID
RESULT = {'scenario': SPEC.get('id'), 'kind': SPEC.get('kind'), 'run_id': RUN_ID,
          'errors': [], 'trace': []}
TRACE = []


def trace(msg):
    TRACE.append(str(msg))


def _json_safe(obj, depth=0):
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, dict):
        return {str(k): _json_safe(v, depth + 1) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_json_safe(v, depth + 1) for v in obj]
    if depth > 6:
        return '<%s>' % type(obj).__name__
    return '%s: %s' % (type(obj).__name__, str(obj)[:200])


def _mkdirs_xlsx(headers, rows):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(list(headers))
    for r in rows:
        ws.append(list(r))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _login(app, admin_id):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(admin_id)
        sess['_fresh'] = True
    return client


def _rows_for_code(html, code):
    """从列表页 HTML 里抽该 process_code 的行：返回 [{cells:[...]}]（只用 `<td>` 文本）。"""
    out = []
    for m in re.finditer(r'<tr\b[^>]*>(.*?)</tr>', html, re.S):
        block = m.group(1)
        cells = [re.sub(r'<[^>]+>', '', c).strip()
                 for c in re.findall(r'<td\b[^>]*>(.*?)</td>', block, re.S)]
        if cells and cells[0] == code:
            out.append({'cells': cells})
    return out


def main():
    from datetime import date, datetime, timedelta

    app, copy_path = fixtures.make_isolated_app('c09-' + str(SPEC.get('id')))
    RESULT['copy_path'] = copy_path
    RESULT['copy_path_verdict'] = fixtures.copy_path_verdict()
    RESULT['real_db_sha256_before'] = _env.sha256_file(_env.REAL_DB)
    trace('isolated app ready: %s' % copy_path)

    from app import db
    from app import models as M

    fixtures.seed_all(app)
    with app.app_context():
        admin = M.User.query.filter_by(username='admin').first() or M.User.query.first()
        emp = M.Employee.query.first()
        if admin is None or emp is None:
            raise AssertionError('夹具失败：缺 user/employee')
        ctx = {'admin_id': admin.id, 'employee': emp, 'today': date.today(),
               'code': ('_c09C%s' % RUN_ID)[:50]}
    client = _login(app, ctx['admin_id'])
    RESULT['fixture_ctx'] = {'admin_id': ctx['admin_id'], 'employee_id': emp.employee_id,
                             'process_code': ctx['code'], 'today': ctx['today'].isoformat()}

    kind = SPEC.get('kind')
    if kind == 'price-version':
        return run_price_version(app, client, ctx, M, db, date, datetime, timedelta)
    if kind == 'price-list':
        return run_price_list(app, client, ctx, M, db, date, timedelta)
    if kind == 'strategy':
        return run_strategy(app, client, ctx, M, db, date, timedelta)
    raise AssertionError('未知 kind: %s' % kind)


def _finish(RESULT, TRACE):
    RESULT['real_db_sha256_after'] = _env.sha256_file(_env.REAL_DB)
    RESULT['real_db_unchanged'] = (RESULT['real_db_sha256_before']
                                   == RESULT['real_db_sha256_after'])
    RESULT['real_db_pinned'] = _env.REAL_DB_SHA256_EXPECTED
    try:
        _env.assert_real_db_untouched('c09 child ' + str(RESULT.get('scenario')))
        RESULT['real_db_assert_ok'] = True
    except Exception as e:                                    # noqa: BLE001
        RESULT['real_db_assert_ok'] = False
        RESULT['errors'].append('真实库指纹断言失败：%s' % e)
    RESULT['trace'] = TRACE
    print('##R2C09-RESULT##' + json.dumps(_json_safe(RESULT), ensure_ascii=False))
    return 0


def _mk_versions(app, M, db, code, versions, today, timedelta):
    """造多版工价：`versions = [(label, day_offset, price)]` ⇒ 返回 {label: row}。"""
    made = {}
    with app.app_context():
        for i, (label, offset, price) in enumerate(versions):
            row = M.ProcessPrice(
                process_code=code, process_name='_c09 探针工序', price=float(price),
                version=i + 1, effective_date=datetime.combine(
                    today + timedelta(days=offset), datetime.min.time()),
                is_current=True, price_type='normal', has_output=False,
                needs_inspection=False)
            db.session.add(row)
            db.session.flush()
            made[label] = row.id
        db.session.commit()
    return made


def run_price_version(app, client, ctx, M, db, date, datetime, timedelta):
    """D-09.1（取价口径）+ D-09.2（价格冻结口径）**同批**实测。

    实测发现（见 docstring「实测结果」）：判据具名的载体 `/production_records/import`
    （`routes.py:2681`，取价在 `:2717-2720`）**对任何行都失败** ——
    `ExcelGenerator.parse_production_record_data`（`excel_generator.py:326-343`）返回的字典
    **没有 `notes` 键**，而 `routes.py:2733` 读 `data['notes']` ⇒ `KeyError: 'notes'` 被逐行
    `except` 吞成「处理记录时出错」⇒ 好行也永不入库。故本场景同时做三件事：
    ① 记录该载体**不可达**（产品面缺口）；② 用**逐字同式**的语句在副本上复算该取价口径；
    ③ 用**可达**的同功能取价点（`/tasks/import`，`routes.py:4020`）实测其真实取值。
    """
    code = ctx['code']
    versions = [('V1', -30, 10.0), ('V2', -10, 20.0), ('V3', +10, 99.0)]
    ids = _mk_versions(app, M, db, code, versions, ctx['today'], timedelta)
    RESULT['versions'] = {'ids': ids, 'spec': versions,
                          'note': 'V3 为**未来生效**（version=3 且 is_current=True）'
                                  '——D-09.1 的证伪条件',
                          'process_code': code}
    trace('versions: %s' % ids)
    qty = int(SPEC.get('quantity') or 3)
    eid = ctx['employee'].employee_id

    # ---- ① 判据具名载体：POST /production_records/import（取价 :2717-2720）
    blob = _mkdirs_xlsx(['生产日期', '员工工号', '工序编号', '数量'],
                        [[ctx['today'], eid, code, qty]])
    resp = client.post('/production_records/import',
                       data={'file': (io.BytesIO(blob), 'c09_%s.xlsx' % RUN_ID)},
                       content_type='multipart/form-data')
    RESULT['carrier_a'] = {'endpoint': '/production_records/import',
                           'file_line': 'routes.py:2681（取价 :2717-2720）',
                           'http_status': resp.status_code,
                           'body': resp.get_data(as_text=True)[:400],
                           'records_created': None}
    with app.app_context():
        db.session.remove()
        RESULT['carrier_a']['records_created'] = int(
            M.ProductionRecord.query.filter(
                M.ProductionRecord.process_id.in_([ids['V1'], ids['V2'], ids['V3']])
            ).count())
    trace('carrierA: status=%s created=%s' % (resp.status_code,
                                              RESULT['carrier_a']['records_created']))

    # ---- ② 逐字同式的取价语句复算（content_implementation；口径对照）
    with app.app_context():
        db.session.remove()
        end_of_day = datetime.combine(ctx['today'], datetime.max.time())
        stmt_sites = {}
        stmt_sites['routes.py:2717-2720（具名载体）'] = {
            'expr': 'filter(process_code==code, effective_date <= end_of_day+1d)'
                    '.order_by(effective_date.desc()).first()',
            'picked_id': None}
        row = (M.ProcessPrice.query.filter(
            M.ProcessPrice.process_code == code,
            M.ProcessPrice.effective_date <= end_of_day + timedelta(days=1)
        ).order_by(M.ProcessPrice.effective_date.desc()).first())
        stmt_sites['routes.py:2717-2720（具名载体）']['picked_id'] = (row.id if row else None)
        stmt_sites['routes.py:2717-2720（具名载体）']['picked_price'] = (row.price if row else None)

        by_version = (M.ProcessPrice.query.filter_by(process_code=code)
                      .order_by(M.ProcessPrice.version.desc()).first())
        by_first = (M.ProcessPrice.query.filter_by(process_code=code).first())
        stmt_sites['routes.py:3902/:4020（另两处，filter_by(...).first()）'] = {
            'expr': 'filter_by(process_code=code).first()（**无 effective_date 过滤、无 order_by**）',
            'picked_id': (by_first.id if by_first else None),
            'picked_price': (by_first.price if by_first else None),
            'picked_effective_date': (str(by_first.effective_date) if by_first else None)}
        stmt_sites['（对照）version 最大者'] = {
            'expr': 'filter_by(process_code=code).order_by(version.desc()).first()',
            'picked_id': (by_version.id if by_version else None),
            'picked_price': (by_version.price if by_version else None)}
        RESULT['statement_eval'] = {'sites': stmt_sites, 'version_ids': ids}
    trace('statement_eval: %s' % {k: v.get('picked_id') for k, v in
                                  (RESULT.get('statement_eval') or {}).get('sites', {}).items()})

    # ---- ③ 可达载体：POST /tasks/import（取价 :4020）⇒ 看它实际落哪一版
    task_blob = _mkdirs_xlsx(['员工工号', '工序编号', '数量', '目标完成日期', '备注'],
                             [[eid, code, qty, ctx['today'], '_c09 取价观测']])
    before_tasks = None
    with app.app_context():
        db.session.remove()
        before_tasks = int(M.TaskAssignment.query.count())
    resp3 = client.post('/tasks/import',
                        data={'file': (io.BytesIO(task_blob), 'c09t_%s.xlsx' % RUN_ID)},
                        content_type='multipart/form-data')
    with app.app_context():
        db.session.remove()
        after_tasks = int(M.TaskAssignment.query.count())
        task = (M.TaskAssignment.query.order_by(M.TaskAssignment.id.desc()).first())
        RESULT['carrier_b'] = {
            'endpoint': '/tasks/import', 'file_line': 'routes.py:4020',
            'http_status': resp3.status_code,
            'body': resp3.get_data(as_text=True)[:300],
            'tasks_before': before_tasks, 'tasks_after': after_tasks,
            'picked_process_id': (task.process_id if task else None),
            'picked_price': (task.process.price if task and task.process else None),
            'picked_effective_date': (str(task.process.effective_date)
                                      if task and task.process else None),
        }
    trace('carrierB: status=%s picked_process_id=%s (V2=%s V1=%s V3=%s)'
          % (resp3.status_code, RESULT['carrier_b']['picked_process_id'],
             ids.get('V2'), ids.get('V1'), ids.get('V3')))

    # ---- ④ D-09.2：报工记录的价格口径（表单路径，显式 process_id=V2）
    r_before = None
    with app.app_context():
        db.session.remove()
        r_before = int(M.ProductionRecord.query.count())
    resp4 = client.post('/production_records',
                        data={'employee_id': str(ctx['employee'].id),
                              'process_id': str(ids['V2']),
                              'quantity': str(qty),
                              'date': ctx['today'].isoformat(),
                              'notes': '_c09 冻结口径观测',
                              'inspector': ''},
                        follow_redirects=False)
    RESULT['carrier_c'] = {'endpoint': 'POST /production_records（表单）',
                           'file_line': 'routes.py:1149/1205-1210',
                           'http_status': resp4.status_code,
                           'records_before': r_before}
    with app.app_context():
        db.session.remove()
        rec = (M.ProductionRecord.query.order_by(M.ProductionRecord.id.desc()).first())
        RESULT['carrier_c']['records_after'] = int(M.ProductionRecord.query.count())
        RESULT['record'] = (None if rec is None else
                            {'id': rec.id, 'process_id': rec.process_id,
                             'quantity': rec.quantity, 'date': str(rec.date),
                             'process_code': rec.process.process_code,
                             'price': rec.process.price,
                             'effective_date': str(rec.process.effective_date)})
        if rec is not None:
            from app.services import mes_service
            RESULT['piecework_before'] = mes_service.piecework_amount([rec])
        else:
            RESULT['piecework_before'] = None
        RESULT['expected_piecework'] = float(qty) * 20.0
    trace('carrierC: status=%s records=%s->%s piecework=%s'
          % (resp4.status_code, r_before, RESULT['carrier_c']['records_after'],
             RESULT.get('piecework_before')))

    # 新增一版「今日生效、价 99」⇒ 同一记录的计件额是否被改写
    with app.app_context():
        newv = M.ProcessPrice(process_code=code, process_name='_c09 探针工序（新增版）',
                              price=99.0, version=4,
                              effective_date=datetime.combine(ctx['today'], datetime.min.time()),
                              is_current=True, price_type='normal', has_output=False,
                              needs_inspection=False)
        db.session.add(newv)
        db.session.commit()
        RESULT['added_version_id'] = newv.id
    with app.app_context():
        db.session.remove()
        rid = (RESULT.get('record') or {}).get('id')
        rec2 = db.session.get(M.ProductionRecord, rid) if rid else None
        if rec2 is not None:
            from app.services import mes_service
            RESULT['piecework_after'] = mes_service.piecework_amount([rec2])
            RESULT['record_after'] = {'process_id': rec2.process_id,
                                      'price': rec2.process.price,
                                      'effective_date': str(rec2.process.effective_date)}
        else:
            RESULT['piecework_after'] = None
    before = RESULT.get('piecework_before')
    after = RESULT.get('piecework_after')
    if before is None or after is None:
        verdict_scope = 'undecidable'
    elif abs(after - before) < 1e-9:
        verdict_scope = 'frozen_at_report_time'
    else:
        verdict_scope = 'follows_current_version'
    RESULT['price_scope'] = {
        'verdict': verdict_scope,
        'piecework_before': before, 'piecework_after': after,
        'expected_if_frozen': before, 'expected_if_current': float(qty) * 99.0,
        'mechanism': 'ProductionRecord.process_id 是指向 **process_price 版本行**的外键'
                     '（routes.py:1206 落 `form.process_id.data`；计件读 `record.process.price`'
                     ' `mes_service.py:1819`）⇒ 版本行一旦选定即冻结',
        'one_line': ('报工时点取价并**冻结**（新增版本不改写存量计件工资）'
                     if verdict_scope == 'frozen_at_report_time'
                     else ('按当前版本取值（历史工资会被新版本改写）'
                           if verdict_scope == 'follows_current_version' else '不可判定')),
    }
    trace('price_scope: %s before=%s after=%s' % (verdict_scope, before, after))
    return _finish(RESULT, TRACE)


def run_price_list(app, client, ctx, M, db, date, timedelta):
    code = ctx['code']
    versions = [(label, off, price) for label, off, price in (SPEC.get('versions') or [])]
    ids = _mk_versions(app, M, db, code, versions, ctx['today'], timedelta)
    RESULT['versions'] = {'ids': ids, 'spec': versions, 'process_code': code}
    resp = client.get('/process_prices', query_string={'search': code, 'per_page': '100'})
    RESULT['http_status'] = resp.status_code
    html = resp.get_data(as_text=True)
    RESULT['html_bytes'] = len(html)
    rows = _rows_for_code(html, code)
    RESULT['rows'] = rows
    RESULT['row_count'] = len(rows)
    RESULT['row_cells_flat'] = [c for r in rows for c in r['cells']]
    trace('list: status=%s rows=%d cells=%s'
          % (resp.status_code, len(rows), RESULT['row_cells_flat'][:8]))
    #: 表头顺序（模板 L127/L132/L133）：code, name, ..., price, effective_date
    RESULT['prices_seen'] = sorted({c for c in RESULT['row_cells_flat']
                                    if re.fullmatch(r'\d+\.\d{2}', c)})
    RESULT['dates_seen'] = sorted({c for c in RESULT['row_cells_flat']
                                   if re.fullmatch(r'\d{4}-\d{2}-\d{2}', c)})
    return _finish(RESULT, TRACE)


def run_strategy(app, client, ctx, M, db, date, timedelta):
    """D-09.4：造 6 个同 process_id 的 ProductProcess ⇒ 一次批次派工产生 6 条任务。"""
    strategy = SPEC.get('strategy')
    weights = SPEC.get('weights') or {'A': 1, 'B': 1, 'C': 1}
    n_batches = int(SPEC.get('batches') or 1)
    #: ⚠ 坑（V-11 双跑实测）：`employee_id` 是 `String(20)`，而 RUN_ID 会变长
    #: （单跑 `r2-exec-b4-c09` = 17 字符，双跑 `r2-exec-b4-c09-runA` 的 tag 正好 20 字符）
    #: ⇒ 若 tag 取满 20 字符，`('%s%s%d')[:20]` 会把 label/index **截掉**，三名员工拿到同一个
    #: employee_id ⇒ UNIQUE 冲突、场景整体 fatal。故 tag 固定留出 4 字符给 label+index。
    tag = ('_c09%s' % RUN_ID)[:14]
    with app.app_context():
        # 1) 工序（派工规则挂在它上面）
        proc = M.ProcessPrice(process_code=('%s_%s' % (tag, strategy))[:50],
                              process_name='_c09 派工工序', price=1.0, version=1,
                              effective_date=datetime.combine(ctx['today'], datetime.min.time()),
                              is_current=True, price_type='normal', has_output=False,
                              needs_inspection=False)
        db.session.add(proc)
        db.session.flush()
        # 2) 三名员工 A/B/C（employee_id 必须两两不同——见上面的坑）
        emps = {}
        emp_ids = {}
        for i, label in enumerate(('A', 'B', 'C')):
            eid = ('%s%s%d' % (tag, label, i))[:20]
            if eid in emp_ids.values():
                raise AssertionError('夹具自检失败：employee_id 撞号 %r' % eid)
            emp_ids[label] = eid
            e = M.Employee(global_sn=M.SerialNumber.get_next_number(),
                           employee_id=eid,
                           name='_c09 员工%s' % label, position='普通员工',
                           department='_c09 部门', base_salary=1000.0, coefficient=1.0,
                           hire_date=ctx['today'], is_active=True)
            db.session.add(e)
            db.session.flush()
            emps[label] = e.id
        RESULT['fixture_employee_ids'] = emp_ids
        # 3) 派工规则 + 成员（sequence 1/2/3，权重按场景）
        rule = M.ProcessAssignmentRule(process_id=proc.id, strategy=strategy, is_active=True)
        db.session.add(rule)
        db.session.flush()
        for seq, label in enumerate(('A', 'B', 'C'), start=1):
            db.session.add(M.ProcessAssignmentMember(
                rule_id=rule.id, employee_id=emps[label], sequence=seq,
                weight=int(weights.get(label, 1)), is_active=True))
        # 4) 编码规则（批次生成需要 product.code_rule + 可用 pattern）
        rule_code = M.CodeRule(name=('_c09CR%s' % RUN_ID)[:100], code_type='product',
                               prefix='_C09', sequence_length=4,
                               format_pattern='{prefix}{sequence}', is_active=True,
                               created_by=ctx['admin_id'])
        db.session.add(rule_code)
        db.session.flush()
        # 5) 产品 + 6 个同 process_id 的工序（sequence 1..6）
        prod = M.Product(product_code=('%sP' % tag)[:50], product_name='_c09 派工产品',
                         status='active', created_by=ctx['admin_id'],
                         code_rule_id=rule_code.id)
        db.session.add(prod)
        db.session.flush()
        for s in range(1, 7):
            db.session.add(M.ProductProcess(product_id=prod.id, process_id=proc.id,
                                            sequence=s, quantity=1, is_required=True))
        # 6) 生产订单（planned 足够开两次批次）
        order = M.ProductionOrder(product_id=prod.id, planned_quantity=6 * n_batches,
                                  planned_start_date=ctx['today'],
                                  planned_end_date=ctx['today'] + timedelta(days=30),
                                  created_by=ctx['admin_id'])
        db.session.add(order)
        db.session.commit()
        fx = {'process_id': proc.id, 'employees': emps, 'product_id': prod.id,
              'order_id': order.id, 'code_rule_id': rule_code.id,
              'members': [{'label': lb, 'employee_id': emps[lb], 'sequence': s,
                           'weight': int(weights.get(lb, 1))}
                          for s, lb in enumerate(('A', 'B', 'C'), start=1)]}
    RESULT['fixture'] = fx
    RESULT['strategy'] = strategy
    RESULT['weights'] = weights
    trace('fixture: rule strategy=%s weights=%s order=%s' % (strategy, weights, fx['order_id']))

    id2label = {v: k for k, v in fx['employees'].items()}
    sequences = []
    for b in range(n_batches):
        before = 0
        with app.app_context():
            before = M.ProductionBatch.query.count()
        resp = None
        raised = None
        try:
            resp = client.post('/production_orders/%d/batches/add' % fx['order_id'],
                               json={'batch_quantity': 6})
            RESULT.setdefault('http_statuses', []).append(resp.status_code)
            RESULT.setdefault('http_bodies', []).append(
                resp.get_data(as_text=True)[:300])
        except BaseException as e:                            # noqa: BLE001
            raised = {'type': e.__class__.__name__, 'message': str(e)[:300]}
            RESULT.setdefault('http_raised', []).append(raised)
        with app.app_context():
            db.session.remove()
            batches = (M.ProductionBatch.query.order_by(M.ProductionBatch.id.desc())
                       .limit(1).all())
            batch = batches[0] if batches else None
            tasks = []
            if batch is not None and batch.id is not None and (before is not None):
                cfg = M.ProductionBatch.query.count()
                tasks = (M.TaskAssignment.query
                         .filter(M.TaskAssignment.production_batch_id == batch.id)
                         .order_by(M.TaskAssignment.id).all())
        seq = [id2label.get(t.employee_id, '?') for t in tasks]
        sequences.append({'batch_index': b, 'batch_id': (batch.id if batch else None),
                          'n_tasks': len(tasks), 'sequence': seq,
                          'http_status': (resp.status_code if resp else None)})
        trace('batch#%d: status=%s tasks=%d seq=%s'
              % (b, (resp.status_code if resp else None), len(tasks), seq))
    RESULT['sequences'] = sequences
    RESULT['sequence'] = sequences[0]['sequence'] if sequences else []
    RESULT['stable_across_batches'] = (
        len(sequences) > 1 and all(s['sequence'] == sequences[0]['sequence']
                                   for s in sequences))
    #: round_robin 的对照序列（同权重、同成员）——用于「两两可区分」的判定
    rr = (['A', 'B', 'C', 'A', 'B', 'C'] if len(sequences) and len(sequences[0]['sequence']) == 6
          else [])
    RESULT['round_robin_reference'] = rr
    RESULT['equals_round_robin'] = bool(RESULT['sequence']) and RESULT['sequence'] == rr
    return _finish(RESULT, TRACE)


if __name__ == '__main__':
    try:
        _rc = main()
    except Exception:                       # noqa: BLE001 —— SystemExit 不在此列（正常出口）
        print('##R2C09-RESULT##' + json.dumps(
            {'scenario': SPEC.get('id'), 'fatal': traceback.format_exc()[-1500:]},
            ensure_ascii=False))
        _rc = 3
    sys.exit(_rc)
'''


def child_script_path(run_id, scenario_id):
    safe = re.sub(r'[^0-9A-Za-z_.-]', '_', str(scenario_id))
    return os.path.join(_env.tmp_dir('c09', 'child'),
                        'c09_%s_%s.py' % (str(run_id).replace(os.sep, '_'), safe))


def _parse_payload(stdout, stderr):
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
    run_id = run_id or _env.RUN_ID
    path = child_script_path(run_id, spec['id'])
    write_text(path, CHILD_TEMPLATE)
    out = _env.run_child([path], cwd=REPO_ROOT, timeout=timeout,
                         extra_env={ALLOW_ENV: '',
                                    'C09_HARNESS_DIR': HERE,
                                    'C09_SCRIPTS_DIR': _env.SCRIPTS_DIR,
                                    'C09_REPO_ROOT': REPO_ROOT,
                                    'C09_RUN_ID': run_id,
                                    'C09_SPEC': json.dumps(spec, ensure_ascii=False)},
                         label='c09-%s' % spec['id'])
    out['payload'] = _parse_payload(out['stdout'], out['stderr'])
    out['script'] = path
    return out


# --------------------------------------------------------------------- 判据（纯函数）
def eval_checks(results):
    A = []

    def add(aid, title, expected, actual, verdict, evidence='',
            evidence_kind='behavior_verified', note='', gap_owner='probe'):
        A.append({'id': aid, 'title': title, 'expected': expected, 'actual': actual,
                  'verdict': verdict, 'evidence': evidence, 'evidence_kind': evidence_kind,
                  'note': note, 'gap_owner': gap_owner})
        return A[-1]

    by_id = {r.get('scenario'): r for r in results}

    def one(sid):
        return by_id.get(sid) or {}

    # ---------------------------------------------------------------- D-09.1
    p1 = one('P1-price-version')
    ver = (p1.get('versions') or {})
    ids = (ver.get('ids') or {})
    ca = p1.get('carrier_a') or {}
    cb = p1.get('carrier_b') or {}
    se = ((p1.get('statement_eval') or {}).get('sites') or {})
    named = se.get('routes.py:2717-2720（具名载体）') or {}
    other = se.get('routes.py:3902/:4020（另两处，filter_by(...).first()）') or {}

    # D-09.1-a：具名载体 (:2717-2720) 的**语句**口径是否正确（逐字同式复算）
    stmt_ok = named.get('picked_id') == ids.get('V2')
    add('D-09.1.a(statement=latest-effective)',
        'D-09.1（口径本体）：判据具名载体的取价语句 —— `filter(process_code==code, '
        'effective_date <= end_of_day+1d).order_by(effective_date.desc()).first()` —— '
        '在逐字同式复算下**取到 V2**（最新生效），而**不是** `version` 最大者/`is_current`'
        '——夹具 V1(D-30,10) / V2(D-10,20) / V3(D+10,99 未来生效)',
        {'picked_id': '= V2.id', 'picked_price': 20.0},
        {'picked_id': named.get('picked_id'), 'picked_price': named.get('picked_price'),
         'V2_id': ids.get('V2'), 'V1_id': ids.get('V1'), 'V3_id': ids.get('V3'),
         'version_max_picker': se.get('（对照）version 最大者')},
        'passed' if stmt_ok else 'failed',
        evidence=rel(p1.get('out_file') or ''),
        evidence_kind='content_implementation',
        note='⚠ 证据级别说明：这是**逐字同式的语句复算**（content_implementation），不是'
             '「端点跑出来的读数」——因为该端点本身不可达（见下一格）',
        gap_owner='probe' if stmt_ok else 'product')

    # D-09.1-b：具名载体**不可达**（端点 100% 行失败）
    ca_body = ca.get('body') or ''
    ca_broken = (ca.get('records_created') == 0)
    add('D-09.1.b(named-carrier-reachable)',
        'D-09.1（可达性，**实测发现的产品面缺口**）：具名载体 `/production_records/import`'
        '（取价 `routes.py:2717-2720`）**对任何行都失败** ⇒ 取价结果**不可能**被观测到'
        '（好行永不入库 = 行级容错的「好行必须入库」亦不成立）',
        {'http_status': 200, 'records_created': '>= 1'},
        {'http_status': ca.get('http_status'), 'records_created': ca.get('records_created'),
         'response_body': ca_body,
         'carrier': 'routes.py:2681（端点）/ :2717-2720（取价）/ :2733（`notes=data["notes"]`）',
         'root_cause': 'ExcelGenerator.parse_production_record_data'
                       '（excel_generator.py:326-343）产出的 dict 键只有 '
                       'date/employee_id/process_code/quantity，**无 `notes`**，'
                       '而 :2733 读 `data["notes"]` ⇒ KeyError 被逐行 except 吞成'
                       '「处理记录时出错」'},
        'passed' if not ca_broken else 'failed',
        evidence=rel(p1.get('out_file') or ''),
        note='变红条件（本格）：0 条入库 + 响应体含 `处理记录时出错: \'notes\'`。'
             '这一格红 = 判据具名载体不可达（product），而非探针问题',
        gap_owner='product' if ca_broken else 'probe')

    # D-09.1-c：同功能另两处取价点口径不一致（可达载体实测取到 V1）
    picked_b = cb.get('picked_process_id')
    inconsistent = (picked_b is not None and picked_b != ids.get('V2'))
    add('D-09.1.c(scope-consistency-across-sites)',
        'D-09.1（一致性，**实测发现的产品面缺口**）：同类取价在仓库里共三处，'
        '`routes.py:2717-2720` 用「`effective_date` 最新」；而 `routes.py:3902`（奖惩导入）'
        '与 `:4020`（任务导入）用 `filter_by(process_code=…).first()` —— **无生效日过滤、'
        '无排序** ⇒ 取到的是「随机/最早」那一版。用**可达**的 `/tasks/import` 实测其真实取值',
        {'picked_process_id': '= V2.id（与 :2717 口径一致）'},
        {'carrier_b_endpoint': cb.get('endpoint'), 'http_status': cb.get('http_status'),
         'picked_process_id': picked_b, 'picked_price': cb.get('picked_price'),
         'picked_effective_date': cb.get('picked_effective_date'),
         'expected_V2': ids.get('V2'), 'V1': ids.get('V1'), 'V3': ids.get('V3'),
         'statement_eval_for_this_site': other,
         'body': cb.get('body')},
        'passed' if not inconsistent else 'failed',
        evidence=rel(p1.get('out_file') or ''),
        note='变红条件：同一 process_code 多版本时两处取价点取到**不同**版本 ⇒ '
             '「工价版本取值」口径不唯一（GAP-21 的实测形态）',
        gap_owner='product' if inconsistent else 'probe')

    # D-09.1-d：未来版永不参与（证伪条件，两条路径都要排除 V3）
    v3_id = ids.get('V3')
    excl_ok = (named.get('picked_id') != v3_id and picked_b != v3_id)
    add('D-09.1.d(future-version-excluded)',
        'D-09.1 证伪条件（**防恒真**）：**未来生效**版 V3（price=99，version=3 且 '
        '`is_current=True`）在任何路径下都**不得**被取到（若取到 99 ⇒ 口径写错，'
        '把「最新」当成了「最大版本号」）',
        {'statement_picked != V3': True, 'reachable_carrier_picked != V3': True},
        {'statement_picked': named.get('picked_id'), 'carrier_b_picked': picked_b,
         'V3_id': v3_id, 'V3_price': 99.0,
         'version_max_picker_picked': se.get('（对照）version 最大者')},
        'passed' if excl_ok else 'failed',
        evidence=rel(p1.get('out_file') or ''),
        note='本格绿 + 上面「口径不一致」红 ⇒ 判据既非恒真也非恒假：'
             '错的是「选哪一版」，不是「未来版混进来了」')

    # ---------------------------------------------------------------- D-09.2
    scope = p1.get('price_scope') or {}
    scope_known = scope.get('verdict') in ('frozen_at_report_time', 'follows_current_version')
    nums_ok = (scope.get('piecework_before') is not None
               and scope.get('piecework_after') is not None)
    rec = p1.get('record') or {}
    add('D-09.2(price-scope-measured)',
        'D-09.2（**口径必须实测写死**）：报工记录的价格是「报工时点取价并冻结」还是'
        '「按现值」—— 同批给出两个数：新增一版今日生效(99) **前**同一记录的计件额 A、'
        '**后**的 A′，并把实测口径显式登记为二者之一',
        {'verdict ∈ {frozen_at_report_time, follows_current_version}': True,
         'A': '= quantity × 20', 'A′': '= A（冻结）或 quantity × 99'},
        {'verdict': scope.get('verdict'), 'one_line': scope.get('one_line'),
         'mechanism': scope.get('mechanism'),
         'A_piecework_before': scope.get('piecework_before'),
         'A_prime_piecework_after': scope.get('piecework_after'),
         'expected_if_frozen': scope.get('expected_if_frozen'),
         'expected_if_current': scope.get('expected_if_current'),
         'record': rec, 'record_after': p1.get('record_after'),
         'added_version_id': p1.get('added_version_id'),
         'carrier_c': p1.get('carrier_c')},
        'passed' if (scope_known and nums_ok and rec.get('process_id') == ids.get('V2'))
        else 'failed',
        evidence=rel(p1.get('out_file') or ''),
        note='载体：`routes.py:1206`（表单落 `process_id`）+ `mes_service.py:1819`'
             '（计件读 `record.process.price`）；⚠ 判据具名的报工**导入**路径因 `notes` '
             'KeyError 不可达（见 D-09.1.b），故本格用**可达**的表单路径测同一口径',
        gap_owner='probe' if (scope_known and nums_ok) else 'product')

    frozen = scope.get('verdict') == 'frozen_at_report_time'
    a_ok = (abs((scope.get('piecework_after') or -1)
                - (scope.get('piecework_before') or -2)) < 1e-9) if frozen else True
    add('D-09.2(freeze-holds)',
        'D-09.2 判定：口径为「冻结」⇒ A′ **必须等于** A（存量计件工资不被新版本改写）；'
        '口径为「按现值」⇒ A′ 必须等于 `quantity × 99`。**两种都算通过** —— '
        '本判据要求的是「实测后二选一登记」，不是「必须冻结」',
        {'frozen ⇒ A′ == A': True, '或 follows_current ⇒ A′ == quantity×99': True},
        {'verdict': scope.get('verdict'), 'A': scope.get('piecework_before'),
         'A_prime': scope.get('piecework_after'),
         'expected_frozen': scope.get('expected_if_frozen'),
         'expected_current': scope.get('expected_if_current'),
         'structural_reason': '`ProductionRecord.process_id` 是 process_price **版本行**外键'
                              '（非 process_code）⇒ 新版本行不可能改写已落库记录的价格',
         'frozen_consistent': a_ok},
        'passed' if (scope_known and a_ok) else 'failed',
        evidence=rel(p1.get('out_file') or ''),
        note='本格只判「登记口径与实测数字一致」，不预设业务结论',
        gap_owner='probe' if (scope_known and a_ok) else 'product')

    # ---------------------------------------------------------------- D-09.3
    p2 = one('P2-price-list')
    cells2 = p2.get('row_cells_flat') or []
    row_ok = (p2.get('row_count') == 1)
    price_ok = ('20.00' in cells2)
    old_price_absent = ('10.00' not in cells2)
    add('D-09.3(list-latest-effective)',
        'D-09.3：列表页同一 `process_code` **只出一版**（最新有效版）——'
        '两版（V1 过去 10 / V2 过去 20）下 `/process_prices?search=<code>` 必须恰 **1 行**，'
        '且单价显示 20.00、生效日为 V2',
        {'row_count': 1, 'price': '20.00', 'price_10_absent': True},
        {'row_count': p2.get('row_count'), 'cells': cells2[:12],
         'prices_seen': p2.get('prices_seen'), 'dates_seen': p2.get('dates_seen'),
         'http_status': p2.get('http_status')},
        'passed' if (row_ok and price_ok and old_price_absent) else 'failed',
        evidence=rel(p2.get('out_file') or ''),
        note='载体 `routes.py:762-776`（`max(effective_date)` 子查询 + `<= today+1`）',
        gap_owner='probe' if (row_ok and price_ok) else 'product')

    p3 = one('P3-price-list-future')
    cells3 = p3.get('row_cells_flat') or []
    fallback_ok = (p3.get('row_count') == 1 and '10.00' in cells3 and '20.00' not in cells3)
    add('D-09.3(future-falls-back)',
        'D-09.3 阴性对照：把 V2 的 `effective_date` 改为**未来** ⇒ 列表必须**回落到 V1**'
        '（证明取的是「有效」而非「最大版本号」）',
        {'row_count': 1, 'price': '10.00', 'price_20_absent': True},
        {'row_count': p3.get('row_count'), 'cells': cells3[:12],
         'prices_seen': p3.get('prices_seen'), 'dates_seen': p3.get('dates_seen')},
        'passed' if fallback_ok else 'failed',
        evidence=rel(p3.get('out_file') or ''),
        note='这一条是 D-09.3 的**证伪条件**：未来版不得出现在「当前有效」列表里',
        gap_owner='probe' if fallback_ok else 'product')

    # ---------------------------------------------------------------- D-09.4
    sf = one('S-fixed')
    sr = one('S-round-robin')
    sw = one('S-weighted')
    ctl = one('S-weighted-all-weight-1')
    seq_f = sf.get('sequence') or []
    seq_r = sr.get('sequence') or []
    seq_w = sw.get('sequence') or []
    seq_c = ctl.get('sequence') or []
    exp_f = next(s for s in SCENARIOS if s['id'] == 'S-fixed')['expect_sequence']
    exp_r = next(s for s in SCENARIOS if s['id'] == 'S-round-robin')['expect_sequence']
    exp_w = next(s for s in SCENARIOS if s['id'] == 'S-weighted')['expect_sequence']

    add('D-09.4(fixed)',
        'D-09.4 策略 `fixed`（**weight≥2 夹具**：A=2,B=1,C=1）⇒ 6 条任务的员工序列必须为 A×6'
        '（`routes.py:8780-8782` 取 `members[0]`）',
        {'sequence': exp_f},
        {'sequence': seq_f, 'n_tasks': (sf.get('sequences') or [{}])[0].get('n_tasks'),
         'http_statuses': sf.get('http_statuses')},
        'passed' if seq_f == exp_f else 'failed',
        evidence=rel(sf.get('out_file') or ''), gap_owner='probe' if seq_f == exp_f else 'product')

    add('D-09.4(round_robin)',
        'D-09.4 策略 `round_robin` ⇒ 序列必须为 A,B,C,A,B,C（`routes.py:8789-8791` 按 sequence 轮询）',
        {'sequence': exp_r},
        {'sequence': seq_r, 'http_statuses': sr.get('http_statuses')},
        'passed' if seq_r == exp_r else 'failed',
        evidence=rel(sr.get('out_file') or ''), gap_owner='probe' if seq_r == exp_r else 'product')

    add('D-09.4(weighted-with-weight2)',
        'D-09.4 策略 `weighted` **带 weight ≥ 2 成员** ⇒ 池 `[A,A,B,C]` 轮转 ⇒ '
        'A,A,B,C,A,A（第 5、6 位与 round_robin **不同**）',
        {'sequence': exp_w},
        {'sequence': seq_w, 'weights': sw.get('weights'),
         'stable_across_batches': sw.get('stable_across_batches'),
         'sequences': sw.get('sequences'), 'http_statuses': sw.get('http_statuses')},
        'passed' if seq_w == exp_w else 'failed',
        evidence=rel(sw.get('out_file') or ''),
        note='这一格是 GAP-42 的主体：**必须**有 weight≥2 才有信息量（见下一格对照）',
        gap_owner='probe' if seq_w == exp_w else 'product')

    pairwise = (len(seq_f) == 6 and len(seq_r) == 6 and len(seq_w) == 6
                and len({tuple(seq_f), tuple(seq_r), tuple(seq_w)}) == 3)
    add('D-09.4(pairwise-distinguishable)',
        'D-09.4 判据主体：三策略在同一夹具下**两两可区分**（`fixed` / `round_robin` / `weighted` '
        '三条序列互不相同）',
        {'three_distinct_sequences': True},
        {'fixed': seq_f, 'round_robin': seq_r, 'weighted': seq_w,
         'distinct_count': len({tuple(seq_f), tuple(seq_r), tuple(seq_w)})},
        'passed' if pairwise else 'failed',
        evidence='；'.join(rel((one(s).get('out_file') or ''))
                           for s in ('S-fixed', 'S-round-robin', 'S-weighted')),
        note='变红条件：三条序列完全相同（串味）或任一路径抛异常',
        gap_owner='probe' if pairwise else 'product')

    add('D-09.4(same-strategy-stable)',
        'D-09.4 稳定性：**同策略连开两个批次**，两次的员工序列必须相同'
        '（`weighted` 场景 `batches=2`）',
        {'stable_across_batches': True},
        {'sequences': sw.get('sequences'), 'stable_across_batches':
         sw.get('stable_across_batches')},
        'passed' if sw.get('stable_across_batches') else 'failed',
        evidence=rel(sw.get('out_file') or ''),
        note='两批之间的索引都会从 0 重新开始 ⇒ 序列应逐位相同',
        gap_owner='probe' if sw.get('stable_across_batches') else 'product')

    ctl_ok = (seq_c == exp_r)
    add('D-09.4(weight-control-indistinguishable)',
        '⚠ D-09.4 **权重对照实验**（`models.py:2537` 默认 `weight=1`）：全员 `weight=1` 时 '
        '`weighted` 池 = `[A,B,C]` ⇒ 与 `round_robin` **数学同解** ⇒ '
        '本夹具下这两者**不可区分**。本格判据 = 「如实登记为不可区分」'
        '（**不得**把 `weighted==round_robin` 记成 PASS 的「可区分」）',
        {'all_weight_1 ⇒ weighted == round_robin': True, '登记为不可区分': True},
        {'sequence': seq_c, 'round_robin_reference': exp_r,
         'equals_round_robin': ctl.get('equals_round_robin'),
         'registered': 'indistinguishable(本夹具下)',
         'weights': ctl.get('weights')},
        'passed' if (ctl_ok and ctl.get('equals_round_robin') is True) else 'failed',
        evidence=rel(ctl.get('out_file') or ''),
        note='这是 `33` §3.2-① 的阳性对照：把权重全改 1 后**如实登记「不可区分」，不得记 PASS**'
             '（本格通过的含义是「探针正确登记了不可区分」，不是「可区分」）',
        evidence_kind='behavior_verified', gap_owner='probe')

    # ---------------------------------------------------------------- 不变量与自证
    allr = [r for r in results if r.get('scenario')]
    db_ok = bool(allr) and all(r.get('real_db_unchanged') and r.get('real_db_assert_ok')
                              for r in allr)
    add('C-09.db',
        '不变量：全部场景全程真实库 app.db SHA256 不变（= 钉死值）',
        {'sha256': _env.REAL_DB_SHA256_EXPECTED, 'unchanged': True},
        {'per_scenario': {r.get('scenario'): {'unchanged': r.get('real_db_unchanged'),
                                              'assert_ok': r.get('real_db_assert_ok')}
                          for r in allr}},
        'passed' if db_ok else 'failed',
        evidence='每个子进程的 real_db_sha256_before/after',
        note='一切库操作走带 RUN_ID 的副本')

    add('C-09.probe-self-check',
        '探针自证：%d 个场景全部在独立子进程里产出可解析读数（无 fatal）' % len(SCENARIOS),
        {'scenarios': len(SCENARIOS), 'fatal': 0},
        {'scenarios': len(allr),
         'fatal_scenarios': [r.get('scenario') for r in allr if r.get('fatal')]},
        'passed' if (len(allr) == len(SCENARIOS)
                     and not [r for r in allr if r.get('fatal')]) else 'failed',
        evidence='各子场景 stdout/stderr')

    failed = [r['id'] for r in A if r['verdict'] != 'passed']
    criteria = [r for r in A if r['id'] not in ('C-09.db', 'C-09.probe-self-check')]
    return A, failed, criteria


# --------------------------------------------------------------------- 父进程编排
def full_run(args):
    started = time.strftime('%Y-%m-%d %H:%M:%S')
    real_before = _env.assert_real_db_untouched('r2_c09 开工')
    print('=' * 88)
    print('[c09] C-09 工价版本取值 + 三策略派工可区分探针')
    print('[c09] run_id=%s  time=%s' % (_env.RUN_ID, started))
    print('[c09] 真实库 %s  sha256=%s' % (rel(args.real_db), real_before))
    print('[c09] 关键前置：`models.py:2537` weight 默认 1 ⇒ 主夹具用 A=2,B=1,C=1；'
          '另做全员 1 的对照（登记「不可区分」）')
    print('=' * 88)

    results = []
    for spec in SCENARIOS:
        out = run_scenario(spec, timeout=args.timeout)
        p = out['payload'] or {}
        p['scenario'] = p.get('scenario') or spec['id']
        p['out_file'] = out['out_file']
        p['child_exit_code'] = out['exit_code']
        results.append(p)
        if spec['kind'] == 'strategy':
            print('  [CASE] %-26s strategy=%-12s weights=%-18s seq=%s %s'
                  % (spec['id'], spec.get('strategy'), p.get('weights'),
                     p.get('sequence'), ('stable=%s' % p.get('stable_across_batches'))
                     if spec.get('batches', 1) > 1 else ''))
        elif spec['kind'] == 'price-list':
            print('  [CASE] %-26s rows=%s prices=%s dates=%s'
                  % (spec['id'], p.get('row_count'), p.get('prices_seen'),
                     p.get('dates_seen')))
        else:
            ca = p.get('carrier_a') or {}
            cb = p.get('carrier_b') or {}
            sc = p.get('price_scope') or {}
            print('  [CASE] %-26s carrierA(records=%s body=%s) carrierB(pid=%s) '
                  'A=%s->A\'=%s scope=%s'
                  % (spec['id'], ca.get('records_created'),
                     (ca.get('body') or '').replace('\n', ' ')[:58],
                     cb.get('picked_process_id'), sc.get('piecework_before'),
                     sc.get('piecework_after'), sc.get('verdict')))
        if p.get('fatal'):
            print('         FATAL: %s' % str(p.get('fatal'))[-300:])

    real_after = _env.assert_real_db_untouched('r2_c09 收尾')
    assertions, failed, criteria = eval_checks(results)

    print('')
    print('-' * 88)
    print('[c09] 判据层')
    for r in assertions:
        print('  %-42s %-8s %-20s %s%s' % (r['id'], r['verdict'].upper(), r['evidence_kind'],
                                           r['title'][:42],
                                           '' if r['verdict'] == 'passed'
                                           else '  [GAP:%s]' % r['gap_owner']))
    print('')
    for r in assertions:
        if r['verdict'] != 'passed':
            print('  [%s] %s' % ('PRODUCT-GAP' if r['gap_owner'] == 'product' else 'FAIL',
                                 r['id']))
            print('         expected=%s' % json.dumps(r['expected'], ensure_ascii=False)[:300])
            print('         actual  =%s' % json.dumps(r['actual'], ensure_ascii=False)[:600])
            if r['note']:
                print('         note    =%s' % r['note'][:260])
    n_pass = len([r for r in assertions if r['verdict'] == 'passed'])
    product_gaps = [r for r in assertions if r['verdict'] != 'passed' and r['gap_owner'] == 'product']
    scope = (one := {r.get('scenario'): r for r in results}).get('P1-price-version', {}) \
        .get('price_scope') or {}
    print('')
    print('[c09] 判据层：%d/%d 通过；失败=%s' % (n_pass, len(assertions), failed or '无'))
    print('[c09] 产品面缺口：%s' % ([r['id'] for r in product_gaps] or '无'))
    print('[c09] D-09.2 口径实测登记 = %s（A=%s → A′=%s）'
          % (scope.get('verdict'), scope.get('piecework_before'), scope.get('piecework_after')))
    print('[c09] D-09.4 三策略序列：fixed=%s round_robin=%s weighted=%s'
          % (( {r.get('scenario'): r for r in results}.get('S-fixed') or {}).get('sequence'),
             ({r.get('scenario'): r for r in results}.get('S-round-robin') or {}).get('sequence'),
             ({r.get('scenario'): r for r in results}.get('S-weighted') or {}).get('sequence')))
    print('[c09] 权重对照（全员 1）：weighted=%s == round_robin=%s ⇒ %s'
          % (({r.get('scenario'): r for r in results}.get('S-weighted-all-weight-1') or {})
             .get('sequence'),
             ({r.get('scenario'): r for r in results}.get('S-round-robin') or {}).get('sequence'),
             '不可区分（已如实登记）'))
    print('[c09] 真实库 app.db：before=%s after=%s 不变=%s'
          % (real_before[:16] + '...', real_after[:16] + '...', real_before == real_after))
    verdict = 1 if failed else 0
    print('[c09] exit=%d' % verdict)
    print('=' * 88)

    payload = {
        'run_id': _env.RUN_ID, 'started': started,
        'probe': 'test-reports-2026-10/harness/r2_c09_probe.py',
        'task': 'V-11 / t12 (C-09)',
        'criteria_ids': ['D-09.1', 'D-09.2', 'D-09.3', 'D-09.4'],
        'preconditions': {
            'P-3 工价两版夹具': 'V1(D-30,10) / V2(D-10,20) / V3(D+10,99 未来生效)',
            'P-4 派工权重夹具': '主夹具 A=2,B=1,C=1（weight≥2）；对照夹具全员 1',
            'models.py:2537 weight 默认': 1,
            'routes.py:8783-8788 weighted 池': 'pool.extend([employee] * max(1, weight or 1))',
        },
        'real_db': {'path': rel(args.real_db), 'sha256_before': real_before,
                    'sha256_after': real_after, 'unchanged': real_before == real_after,
                    'pinned': _env.REAL_DB_SHA256_EXPECTED},
        'scenarios': results,
        'assertions': assertions,
        'criteria_failed': failed, 'criteria_passed': n_pass, 'criteria_total': len(assertions),
        'price_scope_measured': scope,
        'strategy_sequences': {s['id']: (r.get('sequence'))
                               for s in SCENARIOS if s['kind'] == 'strategy'
                               for r in [next((x for x in results
                                               if x.get('scenario') == s['id']), {})]},
        'weight_control': {
            'all_weight_1_sequence': (next((x for x in results
                                            if x.get('scenario') == 'S-weighted-all-weight-1'),
                                           {}) or {}).get('sequence'),
            'round_robin_sequence': (next((x for x in results
                                           if x.get('scenario') == 'S-round-robin'),
                                          {}) or {}).get('sequence'),
            'registered_as': 'indistinguishable（本夹具下 weighted 与 round_robin 数学同解，'
                             '不得记为 PASS 的「可区分」）',
        },
        'product_gaps': [{'id': r['id'], 'expected': r['expected'], 'actual': r['actual'],
                          'note': r['note']} for r in product_gaps],
        'blocked_faces': [
            {'id': 'C-09(price-scope-other-sites)', 'status': 'not_covered',
             'reason': '另有两条同口径取价点 `routes.py:3902`（任务）/`:4020`（导入）本轮未驱动，'
                       '仅登记；口径由 :2717 实测代表'},
            {'id': 'C-09(strategy-other-carriers)', 'status': 'not_covered',
             'reason': '`ProcessAssignmentRule` 的策略分派只在 `create_tasks_for_production_batch` '
                       '（routes.py:8780-8791）实现；管理端 `/api/process_assignment*` 仅存取配置'},
        ],
        'uncovered_faces': [
            {'face': '`routes.py:3902` / `:4020` 的按 process_code 取价点',
             'why': '与 :2717 同口径但入口不同（任务新增 / 任务导入），本轮未驱动'},
            {'face': '`is_current` 字段与 `version` 字段在取价中的实际作用',
             'why': '本轮只证明「按 effective_date 最新」；is_current/version 不参与取价的结论'
                    '由「V3(version=3, is_current=True, 未来生效) 未被取到」间接支撑'},
            {'face': '工价小计（price_type=subtotal）与 `+1 天` 容差的边界',
             'why': '`effective_date <= end_of_day + 1 天` 的容差语义未单独构造边界用例'},
        ],
        'exit_code': verdict,
        'evidence_kind': 'behavior_verified',
        'search_domain': {
            'app/**.py 内容搜索 effective_date': '取价/列表两处（routes.py:2717-2720 / :762-776）',
            'app/**.py 内容搜索 ProcessAssignmentRule': '定义 models.py:2504；分派唯一实现 '
                                                       'routes.py:8773-8791；管理端 :140-290 仅存取',
            '计件唯一口径': 'mes_service.piecework_amount（= record.quantity * record.process.price）',
        },
        'exclude_basenames': ['r2_c09_probe.py（判定脚本自身）', 'captain_r2_*.py',
                              'reconcile_r2.py', 'improve_plan.py', 'analysis_ledger.py',
                              'evidence/** 度量产物'],
        'del_what_goes_red': '把取价改成按 version 最大 ⇒ D-09.1 必红（取到 V3=99）；'
                             '把列表的 max(effective_date) 子查询去掉 ⇒ D-09.3 必红（2 行）；'
                             '把 weighted 的池改成不带权重 ⇒ D-09.4(weighted) 必红（= round_robin）；'
                             '把全员权重改成 1 ⇒ D-09.4 主格失去信息量，须走对照格登记「不可区分」',
        'four_injection_pitfalls_aligned': [
            '1) _env.run_child 是 python -B <argv>：argv 必带脚本路径（生成脚本写 .tmp 再跑）',
            '2) 不碰 create_app() 启动链（本探针只发 HTTP + 读库）',
            '3) 每个场景一份独立副本（fixtures.make_isolated_app(tag=场景名)）',
            '4) 授权开关逐场景传参并显式清空（extra_env={WMS_ALLOW_REAL_DB: ""}）',
        ],
    }
    if args.json_out:
        write_text(args.json_out, json.dumps(payload, ensure_ascii=False, indent=1))
    saved = _env.save_evidence('r2_c09_probe.json',
                               json.dumps(payload, ensure_ascii=False, indent=1))
    print('[c09] 机读结果已落盘 %s' % rel(saved))
    if args.json_out:
        print('[c09] --json-out 副本 %s' % rel(args.json_out))
    return verdict


# --------------------------------------------------------------------- 工具自检
def synth_strategy(sid, strategy, weights, seq, batches=1, fatal=None):
    spec = next(s for s in SCENARIOS if s['id'] == sid)
    out = {'scenario': sid, 'kind': 'strategy', 'strategy': strategy, 'weights': weights,
           'sequence': seq, 'sequences': [{'batch_index': i, 'sequence': seq, 'n_tasks': len(seq),
                                           'http_status': 200} for i in range(batches)],
           'stable_across_batches': batches > 1,
           'equals_round_robin': seq == ['A', 'B', 'C', 'A', 'B', 'C'],
           'http_statuses': [200] * batches, 'real_db_unchanged': True,
           'real_db_assert_ok': True, 'out_file': '(synthetic)'}
    if fatal:
        out['fatal'] = fatal
    return out


def synth_price_version(statement_pick='V2', carrier_a_created=1, carrier_b_pick='V2',
                        price=20.0, piece=60.0, piece_after=60.0,
                        scope='frozen_at_report_time'):
    """合成 P1 读数：默认 = 实测到的**真实形态**（具名载体不可达 + 另两处取到 V1）。"""
    ids = {'V1': 101, 'V2': 102, 'V3': 103}
    price_of = {'V1': 10.0, 'V2': 20.0, 'V3': 99.0}

    def pick(label):
        return {'picked_id': ids.get(label), 'picked_price': price_of.get(label)}

    return {'scenario': 'P1-price-version', 'kind': 'price-version',
            'versions': {'ids': ids,
                         'spec': [['V1', -30, 10.0], ['V2', -10, 20.0], ['V3', 10, 99.0]]},
            'carrier_a': {'endpoint': '/production_records/import',
                          'file_line': 'routes.py:2681（取价 :2717-2720）',
                          'http_status': 200,
                          'body': ('成功导入 0 条记录，1 条记录导入失败：\\n'
                                   '处理记录时出错: \'notes\'' if not carrier_a_created
                                   else '成功导入 1 条记录'),
                          'records_created': carrier_a_created},
            'statement_eval': {'sites': {
                'routes.py:2717-2720（具名载体）': pick(statement_pick),
                'routes.py:3902/:4020（另两处，filter_by(...).first()）': pick('V1'),
                '（对照）version 最大者': pick('V3')}},
            'carrier_b': {'endpoint': '/tasks/import', 'file_line': 'routes.py:4020',
                          'http_status': 200, 'body': '成功导入 1 条记录',
                          'tasks_before': 10, 'tasks_after': 11,
                          'picked_process_id': ids.get(carrier_b_pick),
                          'picked_price': price_of.get(carrier_b_pick),
                          'picked_effective_date': '2026-09-27'},
            'record': {'id': 1, 'process_id': ids['V2'], 'quantity': 3, 'price': price},
            'carrier_c': {'http_status': 302, 'records_before': 0, 'records_after': 1},
            'piecework_before': piece, 'piecework_after': piece_after,
            'expected_piecework': 60.0,
            'price_scope': {'verdict': scope, 'piecework_before': piece,
                            'piecework_after': piece_after, 'expected_if_frozen': 60.0,
                            'expected_if_current': 297.0, 'one_line': '(synthetic)',
                            'mechanism': '(synthetic)'},
            'added_version_id': 104, 'real_db_unchanged': True, 'real_db_assert_ok': True,
            'out_file': '(synthetic)'}


def synth_price_list(sid, rows=1, cells=None, price='20.00'):
    return {'scenario': sid, 'kind': 'price-list', 'http_status': 200, 'row_count': rows,
            'rows': [{'cells': cells or []}], 'row_cells_flat': cells or [],
            'prices_seen': [price], 'dates_seen': ['2026-09-27'],
            'real_db_unchanged': True, 'real_db_assert_ok': True, 'out_file': '(synthetic)'}


def synth_results():
    """合成读数：缺陷形态基线（具名载体不可达 + 另两处取价取到 V1 + 列表两行 + 三策略同解）。"""
    return [
        synth_price_version(carrier_a_created=0, carrier_b_pick='V1'),   # 实测到的真实形态
        synth_price_list('P2-price-list', rows=2, cells=['_c09C', '10.00', '20.00'],
                         price='10.00'),
        synth_price_list('P3-price-list-future', rows=1, cells=['_c09C', '10.00'], price='10.00'),
        synth_strategy('S-fixed', 'fixed', {'A': 2, 'B': 1, 'C': 1}, ['A', 'B', 'C', 'A', 'B', 'C']),
        synth_strategy('S-round-robin', 'round_robin', {'A': 2, 'B': 1, 'C': 1},
                       ['A', 'B', 'C', 'A', 'B', 'C']),
        synth_strategy('S-weighted', 'weighted', {'A': 2, 'B': 1, 'C': 1},
                       ['A', 'B', 'C', 'A', 'B', 'C'], batches=2),
        synth_strategy('S-weighted-all-weight-1', 'weighted', {'A': 1, 'B': 1, 'C': 1},
                       ['A', 'B', 'C', 'A', 'B', 'C']),
    ]


def selftest(args):
    """自检：合成读数 ⇒ 判据函数的预期判定（含「必须报红」的阳性样本）。"""
    checks = []
    real_before = _env.assert_real_db_untouched('r2_c09 selftest')
    print('=' * 88)
    print('[selftest] 判据函数对拍（合成读数 ⇒ 预期判定）')
    print('=' * 88)

    def run_case(tag, results, expect_failed, expect_exit):
        assertions, failed, _crit = eval_checks(results)
        ok_fail = set(failed) == set(expect_failed)
        ok_exit = (0 if not failed else 1) == expect_exit
        good = ok_fail and ok_exit
        checks.append({'tag': tag, 'failed': failed, 'expect_failed': sorted(expect_failed),
                       'exit': expect_exit, 'ok': good})
        print('  [%s] %-22s failed=%-58s 期望=%-58s exit=%s(期望 %s)'
              % ('PASS' if good else 'FAIL', tag, json.dumps(failed)[:58],
                 json.dumps(sorted(expect_failed))[:58], 0 if not failed else 1, expect_exit))
        if not good:
            print('         verdicts=%s'
                  % json.dumps({r['id']: r['verdict'] for r in assertions}, ensure_ascii=False))
        return good

    #: 缺陷形态基线：具名载体不可达（D-09.1.b 红）+ 另两处取价取到 V1（D-09.1.c 红）
    #: + 列表 2 行（D-09.3 红）+ 三策略同解（fixed/weighted/pairwise 红；
    #: round_robin 本身是正确参考值故绿）
    gap_ids = {'D-09.1.b(named-carrier-reachable)', 'D-09.1.c(scope-consistency-across-sites)',
               'D-09.3(list-latest-effective)', 'D-09.4(fixed)',
               'D-09.4(weighted-with-weight2)', 'D-09.4(pairwise-distinguishable)'}
    ok_all = True
    ok_all &= run_case('baseline', synth_results(), gap_ids, 1)

    green = [
        synth_price_version(),            # 具名载体可达 + 另两处也取 V2
        synth_price_list('P2-price-list', rows=1, cells=['_c09C', '20.00']),
        synth_price_list('P3-price-list-future', rows=1, cells=['_c09C', '10.00'], price='10.00'),
        synth_strategy('S-fixed', 'fixed', {'A': 2, 'B': 1, 'C': 1}, ['A'] * 6),
        synth_strategy('S-round-robin', 'round_robin', {'A': 2, 'B': 1, 'C': 1},
                       ['A', 'B', 'C', 'A', 'B', 'C']),
        synth_strategy('S-weighted', 'weighted', {'A': 2, 'B': 1, 'C': 1},
                       ['A', 'A', 'B', 'C', 'A', 'A'], batches=2),
        synth_strategy('S-weighted-all-weight-1', 'weighted', {'A': 1, 'B': 1, 'C': 1},
                       ['A', 'B', 'C', 'A', 'B', 'C']),
    ]
    ok_all &= run_case('all-green', green, set(), 0)

    # 阳性样本①：语句口径按 version 最大 ⇒ 取到未来版 V3 ⇒ D-09.1.a / D-09.1.d 必红
    r = list(green)
    r[0] = synth_price_version(statement_pick='V3', carrier_b_pick='V3')
    ok_all &= run_case('version-max-instead-of-effective', r,
                       {'D-09.1.a(statement=latest-effective)',
                        'D-09.1.c(scope-consistency-across-sites)',
                        'D-09.1.d(future-version-excluded)'}, 1)

    # 阳性样本②：D-09.2 口径数字对不上（声称冻结但 A′≠A）⇒ 必红
    r = list(green)
    r[0] = synth_price_version(piece=60.0, piece_after=297.0,
                               scope='frozen_at_report_time')
    ok_all &= run_case('scope-number-mismatch', r, {'D-09.2(freeze-holds)'}, 1)

    # 阳性样本③：列表出 2 行 ⇒ D-09.3 必红
    r = list(green)
    r[1] = synth_price_list('P2-price-list', rows=2, cells=['_c09C', '10.00', '20.00'])
    ok_all &= run_case('list-two-rows', r, {'D-09.3(list-latest-effective)'}, 1)

    # 阳性样本③：weighted 不带权重（== round_robin）⇒ 主格与两两可区分必红
    r = list(green)
    r[5] = synth_strategy('S-weighted', 'weighted', {'A': 1, 'B': 1, 'C': 1},
                          ['A', 'B', 'C', 'A', 'B', 'C'], batches=2)
    ok_all &= run_case('weighted-no-weight', r,
                       {'D-09.4(weighted-with-weight2)', 'D-09.4(pairwise-distinguishable)'}, 1)

    # 阳性样本④：同策略两次不稳定 ⇒ 稳定性格必红
    r = list(green)
    w = dict(r[5])
    w['sequences'] = [{'batch_index': 0, 'sequence': ['A', 'A', 'B', 'C', 'A', 'A']},
                      {'batch_index': 1, 'sequence': ['A', 'B', 'C', 'A', 'B', 'C']}]
    w['stable_across_batches'] = False
    r[5] = w
    ok_all &= run_case('strategy-unstable', r, {'D-09.4(same-strategy-stable)'}, 1)

    real_ok = _env.sha256_file(_env.REAL_DB) == real_before == _env.REAL_DB_SHA256_EXPECTED
    ok_all &= real_ok
    print('  [%s] 真实库 app.db SHA256 = %s（钉死值）'
          % ('PASS' if real_ok else 'FAIL', real_before))
    payload = {'mode': 'selftest', 'run_id': _env.RUN_ID, 'checks': checks,
               'real_db_sha256': real_before, 'real_db_ok': real_ok,
               'verdict': 'passed' if ok_all else 'failed'}
    saved = _env.save_evidence('r2_c09_probe_selftest.json',
                               json.dumps(payload, ensure_ascii=False, indent=1))
    print('[selftest] 结论：%s（1 组缺陷基线 + 1 组全绿 + 4 组必红对拍）'
          % ('OK' if ok_all else 'FAIL'))
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
        return {k: {'sequence': v.get('sequence'),
                    'row_count': v.get('row_count'),
                    'prices': v.get('prices_seen'),
                    'record_process_id': (v.get('record') or {}).get('process_id'),
                    'price': (v.get('record') or {}).get('price'),
                    'piecework_before': v.get('piecework_before'),
                    'piecework_after': v.get('piecework_after'),
                    'scope': (v.get('price_scope') or {}).get('verdict'),
                    'http_status': v.get('http_status') or v.get('http_statuses')}
                for k, v in sc.items()}

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
    saved = _env.save_evidence('r2_c09_probe_compare.json',
                               json.dumps(out, ensure_ascii=False, indent=1))
    print('[compare] A=%s B=%s' % (out['run_id_a'], out['run_id_b']))
    print('[compare] only_in_a=%s only_in_b=%s verdict_diff=%s'
          % (out['only_in_a'], out['only_in_b'], out['verdict_diff']))
    print('[compare] reading_diff=%s' % json.dumps(out['reading_diff'], ensure_ascii=False)[:300])
    print('[compare] 双跑一致 = %s' % out['identical'])
    print('[compare] 证据已落盘 %s' % rel(saved))
    return 0 if out['identical'] else 1


def main():
    ap = argparse.ArgumentParser(description='C-09 工价版本与三策略派工探针（V-11 / t12）')
    ap.add_argument('--selftest', action='store_true', help='用合成读数对拍判据函数')
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
