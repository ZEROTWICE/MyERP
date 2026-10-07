#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""r2_c08_probe.py —— C-08「导入行级容错 / 导出零残留 / 上传目录清理」探针（V-10 / t11）。

任务契约（`35-第2轮测试总方案（定稿）.md` §4 C-08 行 / `33` §3.1 `B-08.1/2/3` 五元组）：

* **inScope**：本文件（`test-reports-2026-10/harness/r2_c08_probe.py`）。**不得改 `app/**`**，
  也**不得改 `harness/fixtures.py`**（V-04 已完成并冻结于 64496 B）。
* **分母**：导入端点 **8** 个落盘 + `quality.py` 1 个（共 **9**，`33` §3.1 B-08.1 具名登记）；
  导出 **13 处** `io.BytesIO` 内存生成。
* **判据（B-08.1/2/3 五元组，逐条实测）**：
  * `B-08.1` 行级容错：3 好 + 2 坏 ⇒ `新增=3 / 错误=2`；**逐条含「第 N 行」**（N = xlsx 真实行号，
    表头为第 1 行）；**全好 ⇒ 错误数必须为 0**（防「一律报坏行」的恒真判据）。
  * `B-08.2` 导入清理：请求返回后上传文件**不再存在**于落盘目录；
    ⚠ **双前置**（`35` §4-② 实测）：`routes.py:2194` 阈值 **>300s 才清理**（钩子清不动当次文件）、
    `routes.py:4892/4979` 两个导入落 **`tempfile.gettempdir()`**（不被清理钩子覆盖）
    ⇒ 判据必须**成对**写：`TEMP_FOLDER` 类 + OS-temp 类**各一条**。
  * `B-08.3` 导出零残留：导出前后 `uploads/temp` **清单逐一相同**（文件名 + 内容 SHA256），
    且响应 `Content-Type` 为 xlsx 且可被 `openpyxl` 打开；**阳性对照** = 清单比对必须能发现新文件。
* **不能证明什么（必须登记）**：`mkdtemp` 目录回收（G-11）；导出零残留轨二 ⇒
  `blocked(需非沙箱环境)`。

## 运行时目录事实（探针独立量测，**重要**）

`config.py` 的 `UPLOAD_FOLDER = <repo>/uploads`、`TEMP_FOLDER = <repo>/uploads/temp`
⇒ **导入落盘点是仓库根的 `uploads/temp`，不是副本内**（副本只换 `DATABASE_URL`）。
因此 B-08.2 的残留判据必须在**真实路径**上做，且探针只写/只读/只清**自己命名的** `_c08_*` 文件
（收尾 best-effort 清理，读数已在 JSON 里落地，不影响证据）。

## 被测端点（真实端点，非自造 API）

| 场景 | 端点（`file:line`） | 落盘目录 | 行级容错 | 错误文案「第 N 行」 |
| --- | --- | --- | --- | --- |
| S1/S2/S3/S4 | `POST /tasks/import`（`routes.py:3987`） | `TEMP_FOLDER`（`:4002`） | ✅ 逐行 try（`:4011-4044`） | ⚠ 仅日期类（`:4028`）；工号/工序类**无**（`:4016/:4022`） |
| S5 | `POST /employees/import`（`routes.py:1935`） | `TEMP_FOLDER`（`:1951`） | ❌ 先全量校验、有错即整单返回（`:2061-2066`） | ✅（`:2058`） |
| S6 | `POST /inventory/finished/import`（`routes.py:4880`） | **OS-temp**（`:4892`） | ✅ 逐行 try（`:4908-4945`） | ❌ **缺 f-string** ⇒ 字面量 `第{index+2}行`（`:4945`） |
| S7/S8 | `GET /export_tasks`（`routes.py:4068`） | 内存 `io.BytesIO`（`:4115`） | — | — |

## 实测结果（本文件实跑；11/14 通过，3 条**产品面缺口**，exit=1 且红点全为 product）

| 判据 | 结果 | 实测读数 |
| --- | --- | --- |
| `C-08.1.a` `/tasks/import` 3 好 + 2 坏 | **PASS** | HTTP 200；`成功导入 3 条`；错误 **2** 条；`task_assignment` **Δ=3** |
| `C-08.1.b` 错误逐条带「第 N 行」 | **GAP(product)** | 错误文案 = `员工工号 NO_X 不存在` / `工序编号 NO_X 不存在` ⇒ **无行号**（`routes.py:4016/:4022`） |
| `C-08.1.c` 日期类带真行号 | **PASS** | 坏行 = 第 3 行 ⇒ 错误含 `第 3 行：目标完成日期格式错误（不是日期）`（`routes.py:4028`） |
| `C-08.1.d` 5 行全好 ⇒ 错误 0 | **PASS** | `成功导入 5 条`、错误 **0**、Δ=5（防「一律报坏行」） |
| `C-08.1.e` `/employees/import` 行级容错 | **GAP(product)** | 有行号（`第5行数据错误：工号长度不能超过20个字符` / `第6行…职位长度不能超过50个字符`）但**整单 0 行**（`delta_target=0`，`数据验证失败，共发现2个错误`，`:2061-2066`） |
| `C-08.1.f` 非恒真对照 | **PASS** | B-08.1 的两半在**不同端点**上分别为绿 ⇒ 红点定位到具体端点/类 |
| `C-08.2.a` TEMP_FOLDER 类残留 | **GAP(product)** | 正常路径 S1/S3 **不残留**（`:4006` 解析后 `os.remove`）；**解析失败 S4 残留**、`/employees/import` 早退 S5 **残留** ⇒ 两处都缺 `finally` |
| `C-08.2.b` OS-temp 类残留 | **PASS** | `/inventory/finished/import`（`:4892` OS-temp）请求后**不残留**（`:4959` 有 `finally`） |
| `C-08.2.c` 成对性 | **PASS** | 两类目录都实际判过（一个 `uploads/temp`、一个 `tempfile.gettempdir()`）；覆盖 3 个导入端点 |
| `C-08.3.a` 导出零残留 | **PASS** | 前后清单**逐一相同**（0→0 文件、无 added/removed/changed）；`Content-Type` = xlsx；`openpyxl` 可打开（11 行 × 5 列，5123 B 级） |
| `C-08.3.b` 清单比对敏感性 | **PASS** | 手工放一个新文件 ⇒ 比对**发现**；删除后恢复一致（证明非恒真） |
| `C-08.3.c` 导出覆盖面 | **PASS** | 导出侧抽样 **1/13** 处 `io.BytesIO`（`/export_tasks`，`:4115`） |
| `C-08.4` 真库不变量 | **PASS** | 全程 `F5DA2306…0E0F065` |
| `C-08.5` 探针自证 | **PASS** | 8 场景全部产出可解析读数；收尾只清自己命名的文件（2 个） |

**两条实现级缺口坐标（可直接进改进报告）**：
1. `app/main/routes.py:4016` / `:4022`（`/tasks/import`）—— 工号/工序类错误**不含行号**；
   同文件 `:4028`（日期类）与 `app/main/routes.py:2058`（员工导入）**含行号** ⇒ 三种坏行类
   「行号覆盖」不一致。
2. `app/main/routes.py:4945`（`/inventory/finished/import`）与 `:5036`（`/inventory/raw/import`）
   —— **缺 f-string 前缀**：错误文案落库为**字面量** `第{index+2}行…`（实测 `literal_brace_bug=true`），
   行号永远不会被代入。
3. 上传清理：`/tasks/import` 的 `os.remove` 在解析**之后**且无 `finally`（`:4000-4006`）；
   `/employees/import` 只在 `except` 里 `os.remove`（`:2171-2176`）⇒ 解析失败/校验早退两条路径
   **必然残留**当次上传文件，而 `@bp.before_request` 的阈值是 `>300s`（`:2194`）⇒ 靠钩子救不回来。

## 用法（仓库根目录；解释器绝对路径，`28` §5-1 / `40` R-4）

```powershell
$py = 'F:\Miniconda\envs\wage\python.exe'
$env:HARNESS_RUN_ID = 'r2-exec-b4-c08'
& $py -B test-reports-2026-10\harness\r2_c08_probe.py                 # 判据层
& $py -B test-reports-2026-10\harness\r2_c08_probe.py --selftest      # 判据会报红
& $py -B test-reports-2026-10\harness\r2_c08_probe.py --json-out a.json
& $py -B test-reports-2026-10\harness\r2_c08_probe.py --compare a.json b.json
```

退出码：`0` = 判据层全过；`1` = 任一判据失败。**注意**：本探针的判据层**包含 B-08.x 本身**，
因此若被测方不满足某条（例如错误文案缺「第 N 行」、上传文件未清理），退出码为 `1` 是
**正确读数**（`criteria[].gap_owner = 'product'` 标明归属，`product_gaps[]` 机读汇总）。
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import time

try:  # A-14：本机控制台 GBK
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import _env  # noqa: E402

RESULT_MARKER = '##R2C08-RESULT##'
REPO_ROOT = _env.REPO_ROOT
DEFAULT_REAL_DB = _env.REAL_DB
ALLOW_ENV = 'WMS_ALLOW_REAL_DB'
#: 探针自有文件前缀（只写/只清自己的文件，绝不碰他人文件）
PROBE_PREFIX = '_c08_'

#: 判据层要求的最少端点覆盖（`33` §3.1 具名登记 9 个导入端点，本轮抽样驱动）
MIN_IMPORT_ENDPOINTS = 3

#: 场景表（payload 的 xlsx 行在子进程内按副本现状解析 `@employee.code` 占位符）
SCENARIOS = [
    {
        'id': 'S1-tasks-3good-2bad', 'kind': 'import', 'group': 'B-08.1',
        'endpoint': '/tasks/import', 'file_line': 'routes.py:3987',
        'headers': ['员工工号', '工序编号', '数量', '目标完成日期', '备注'],
        'rows': [
            ['@employee.code', '@process.code', 5, '@today', '_c08 好行1'],
            ['@employee.code', '@process.code', 3, '@today', '_c08 好行2'],
            ['@employee.code', '@process.code', 2, '@today', '_c08 好行3'],
            ['@no_employee_code', '@process.code', 1, '@today', '_c08 坏行-工号不存在'],
            ['@employee.code', '@no_process_code', 1, '@today', '_c08 坏行-工序不存在'],
        ],
        'target_table': 'task_assignment', 'residue_dir': 'temp_folder',
        'expect_success': 3, 'expect_errors': 2,
        'desc': 'B-08.1 主体：3 好 + 2 坏（工号不存在 / 工序不存在）⇒ 新增 3 / 错误 2',
    },
    {
        'id': 'S2-tasks-5good', 'kind': 'import', 'group': 'B-08.1-control',
        'endpoint': '/tasks/import', 'file_line': 'routes.py:3987',
        'headers': ['员工工号', '工序编号', '数量', '目标完成日期', '备注'],
        'rows': [
            ['@employee.code', '@process.code', 5, '@today', '_c08 全好1'],
            ['@employee.code', '@process.code', 4, '@today', '_c08 全好2'],
            ['@employee.code', '@process.code', 3, '@today', '_c08 全好3'],
            ['@employee.code', '@process.code', 2, '@today', '_c08 全好4'],
            ['@employee.code', '@process.code', 1, '@today', '_c08 全好5'],
        ],
        'target_table': 'task_assignment', 'residue_dir': 'temp_folder',
        'expect_success': 5, 'expect_errors': 0,
        'desc': 'B-08.1 阴性对照：5 行全好 ⇒ 新增 5 / **错误 0**（防「一律报坏行」）',
    },
    {
        'id': 'S3-tasks-baddate', 'kind': 'import', 'group': 'B-08.1',
        'endpoint': '/tasks/import', 'file_line': 'routes.py:3987',
        'headers': ['员工工号', '工序编号', '数量', '目标完成日期', '备注'],
        'rows': [
            ['@employee.code', '@process.code', 5, '@today', '_c08 好行'],
            ['@employee.code', '@process.code', 1, '不是日期', '_c08 坏行-日期文本非法'],
        ],
        'target_table': 'task_assignment', 'residue_dir': 'temp_folder',
        'expect_success': 1, 'expect_errors': 1, 'expect_row_numbers': [3],
        'desc': 'B-08.1 第 3 类坏行（日期文本非法）⇒ 错误必须带**真行号**「第 3 行」',
    },
    {
        'id': 'S4-tasks-parsefail', 'kind': 'import-corrupt', 'group': 'B-08.2',
        'endpoint': '/tasks/import', 'file_line': 'routes.py:3987',
        'residue_dir': 'temp_folder', 'expect_residue': False,
        'desc': 'B-08.2 解析失败路径：文件必须在请求返回后不残留（实测 :4006 的 os.remove 在 '
                '解析之后、且无 finally ⇒ 本项预期红）',
    },
    {
        'id': 'S5-employees-3good-2bad', 'kind': 'import', 'group': 'B-08.1',
        'endpoint': '/employees/import', 'file_line': 'routes.py:1935',
        'headers': ['工号', '姓名', '职位', '部门', '基本工资', '系数', '入职时间', '离职时间'],
        'rows': [
            ['@emp_code_1', '_c08 员工1', '普通员工', '_c08 部门', 3000, 1.0, '@today', ''],
            ['@emp_code_2', '_c08 员工2', '普通员工', '_c08 部门', 3000, 1.0, '@today', ''],
            ['@emp_code_3', '_c08 员工3', '普通员工', '_c08 部门', 3000, 1.0, '@today', ''],
            #: 坏行必须取**校验器**能拦下的形态：空单元格会被解析器 `str(None)` 变成字面量
            #: `'None'`（非空）而绕过「不能为空」，'不是数字' 也会被兜底成数字（实测 S5 首跑
            #: `success=4/errors=0`）⇒ 改用长度越界（`routes.py:1976/:1988`）确保确定性命中
            ['@emp_code_long', '_c08 员工4', '普通员工', '_c08 部门', 3000, 1.0, '@today', ''],
            ['@emp_code_5', '_c08 员工5', '@position_long', '_c08 部门', 3000, 1.0, '@today', ''],
        ],
        'target_table': 'employee', 'residue_dir': 'temp_folder',
        'expect_success': 3, 'expect_errors': 2,
        'desc': 'B-08.1 第二个端点：3 好 + 2 坏（工号超 20 字符 / 职位超 50 字符）⇒ 新增 3 / 错误 2；'
                '本端点先全量校验（:2061）⇒ 实测预期「整单 0 行」= B-08.1 的变红条件之一',
    },
    {
        'id': 'S6-finished-3good-2bad', 'kind': 'import', 'group': 'B-08.2',
        'endpoint': '/inventory/finished/import', 'file_line': 'routes.py:4880',
        'headers': ['产品编号', '生产日期', '图号', '型号', '检验员', '状态'],
        'rows': [
            ['@fp_no1', '@today', '_c08-DWG', '_c08-MODEL', '_c08 检验员', 'in_stock'],
            ['@fp_no2', '@today', '_c08-DWG', '_c08-MODEL', '_c08 检验员', 'in_stock'],
            ['@fp_no3', '@today', '_c08-DWG', '_c08-MODEL', '_c08 检验员', 'in_stock'],
            ['@fp_no4', '不是日期', '_c08-DWG', '_c08-MODEL', '_c08 检验员', 'in_stock'],
            ['@fp_no5', '也不是日期', '_c08-DWG', '_c08-MODEL', '_c08 检验员', 'in_stock'],
        ],
        'target_table': 'finished_product', 'residue_dir': 'ostemp',
        'expect_success': 3, 'expect_errors': 2, 'expect_residue': False,
        'desc': 'B-08.2 **OS-temp 类**（`tempfile.gettempdir()`，:4892）：3 好 + 2 坏 + '
                '请求返回后文件必须不残留（:4959 有 finally）',
    },
    {
        'id': 'S7-export-tasks', 'kind': 'export', 'group': 'B-08.3',
        'endpoint': '/export_tasks', 'file_line': 'routes.py:4068',
        'desc': 'B-08.3：导出前后 `uploads/temp` 清单逐一相同 + Content-Type + openpyxl 可打开',
    },
    {
        'id': 'S8-export-sensitivity', 'kind': 'export-sensitivity', 'group': 'B-08.3-control',
        'endpoint': '/export_tasks', 'file_line': 'routes.py:4068',
        'desc': 'B-08.3 阳性对照：往 `uploads/temp` 放一个新文件 ⇒ 清单比对**必须**发现',
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
"""r2_c08_child.py —— C-08 子场景（由 `r2_c08_probe.py` 生成到 `.tmp/<RUN_ID>/c08/child/`）。

参数经环境变量传入：`C08_SPEC`（JSON）/ `C08_RUN_ID` / `C08_HARNESS_DIR` /
`C08_SCRIPTS_DIR` / `C08_REPO_ROOT`。输出一行 `##R2C08-RESULT##<json>`。
"""
import hashlib
import io
import json
import os
import re
import sys
import tempfile
import traceback

HARNESS_DIR = os.environ.get('C08_HARNESS_DIR') or ''
SCRIPTS_DIR = os.environ.get('C08_SCRIPTS_DIR') or ''
REPO_ROOT = os.environ.get('C08_REPO_ROOT') or ''
for _p in (HARNESS_DIR, SCRIPTS_DIR, REPO_ROOT):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)

import _env        # noqa: E402
import fixtures    # noqa: E402

SPEC = json.loads(os.environ.get('C08_SPEC') or '{}')
RUN_ID = os.environ.get('C08_RUN_ID') or _env.RUN_ID
PROBE_PREFIX = '_c08_'
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


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest().upper()


def listing(directory, prefix=None):
    """目录清单：`文件名 -> 内容 SHA256`（清单逐一相同的判据载体）。"""
    out = {}
    try:
        for name in sorted(os.listdir(directory)):
            p = os.path.join(directory, name)
            if not os.path.isfile(p):
                continue
            if prefix and not name.startswith(prefix):
                continue
            try:
                out[name] = {'sha256': sha256_file(p), 'bytes': os.path.getsize(p),
                             'mtime': int(os.path.getmtime(p))}
            except OSError as e:
                out[name] = {'error': '%s: %s' % (e.__class__.__name__, e)}
    except OSError as e:
        out['__error__'] = '%s: %s' % (e.__class__.__name__, e)
    return out


def table_count(db, table):
    try:
        return int(db.session.execute(db.text('SELECT COUNT(*) FROM "%s"' % table)).scalar() or 0)
    except Exception as e:
        return {'error': '%s: %s' % (e.__class__.__name__, e)}


def build_xlsx(headers, rows):
    """按行在内存里造 xlsx（openpyxl），返回 bytes（不落盘）。"""
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    if headers:
        ws.append(list(headers))
    for r in rows:
        ws.append(list(r))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def resolve(value, ctx):
    if not isinstance(value, str) or not value.startswith('@'):
        return value
    key = value[1:]
    if key == 'today':
        return ctx['today']
    if key == 'run':
        return ctx['run']
    if key.startswith('no_'):
        #: 「不存在」占位符：拼一个必然查不到的业务编号
        base = ctx.get(key[3:]) or ''
        return 'NO_%s' % (str(base)[:20] or 'X')
    return ctx.get(key, value)


def parse_message(msg):
    """从导入响应里抽 `成功导入 N 条`、错误条目与「第 N 行」行号（含 f-string 缺陷探测）。"""
    out = {'raw': (msg or '')[:1200], 'success_count': None, 'error_count': None,
           'error_items': [], 'row_numbers': [], 'row_number_all_ok': None,
           'literal_brace_bug': bool(re.search(r'第\s*\{[^}]*\}\s*行', msg or ''))}
    m = re.search(r'成功导入\s*(\d+)\s*条', msg or '')
    if m:
        out['success_count'] = int(m.group(1))
    m2 = re.search(r'(\d+)\s*条记录导入失败', msg or '')
    if m2:
        out['error_count'] = int(m2.group(1))
    m3 = re.search(r'共发现(\d+)个错误', msg or '')
    if m3:
        out['error_count'] = int(m3.group(1))
    #: 错误条目：以「，」或换行分隔、含已知关键词的行
    items = []
    for line in re.split(r'[\n]', msg or ''):
        line = line.strip()
        if not line:
            continue
        if line.startswith('成功导入') or line.startswith('数据验证失败'):
            continue
        if any(k in line for k in ('不存在', '第', '错误', '失败', '不能为空', '必须是有效数字')):
            items.append(line[:160])
    out['error_items'] = items
    if out['error_count'] is None:
        out['error_count'] = len(items)
    out['row_numbers'] = [int(x) for x in re.findall(r'第\s*(\d+)\s*行', msg or '')]
    if items:
        out['row_number_all_ok'] = all(
            re.search(r'第\s*\d+\s*行', it) for it in items)
    return out


def main():
    from datetime import date

    app, copy_path = fixtures.make_isolated_app('c08-' + str(SPEC.get('id')))
    RESULT['copy_path'] = copy_path
    RESULT['copy_path_verdict'] = fixtures.copy_path_verdict()
    RESULT['real_db_sha256_before'] = _env.sha256_file(_env.REAL_DB)
    temp_folder = os.path.join(REPO_ROOT, 'uploads', 'temp')
    ostemp = tempfile.gettempdir()
    RESULT['runtime_dirs'] = {'temp_folder': temp_folder, 'ostemp': ostemp,
                              'note': 'TEMP_FOLDER 来自 config.py 的 <repo>/uploads/temp；'
                                      '副本只换 DATABASE_URL，不换上传目录'}

    if SPEC.get('kind') in ('export', 'export-sensitivity'):
        return run_export(app, temp_folder)

    from app import db
    from app import models as M

    fixtures.seed_all(app)
    with app.app_context():
        admin = M.User.query.filter_by(username='admin').first() or M.User.query.first()
        emp = M.Employee.query.first()
        proc = M.ProcessPrice.query.first()
        if admin is None or emp is None or proc is None:
            raise AssertionError('夹具失败：缺 user/employee/process_price')
        ctx = {'admin': admin, 'employee': emp, 'process': proc, 'today': date.today().isoformat(),
               'run': RUN_ID, 'employee.code': emp.employee_id,
               'process.code': getattr(proc, 'process_code', None),
               'emp_code_1': ('_c08E1%s' % RUN_ID)[:20],
               'emp_code_2': ('_c08E2%s' % RUN_ID)[:20],
               'emp_code_3': ('_c08E3%s' % RUN_ID)[:20],
               'emp_code_4': ('_c08E4%s' % RUN_ID)[:20],
               'emp_code_5': ('_c08E5%s' % RUN_ID)[:20],
               #: 坏行用「长度越界」确保被校验器拦下（见 SCENARIOS[4] 的注释）
               'emp_code_long': ('长工号%s' % RUN_ID) + 'X' * 12,
               'position_long': ('超长职位%s' % RUN_ID) + 'Y' * 40,
               'fp_no1': ('_c08FP1%s' % RUN_ID)[:50],
               'fp_no2': ('_c08FP2%s' % RUN_ID)[:50],
               'fp_no3': ('_c08FP3%s' % RUN_ID)[:50],
               'fp_no4': ('_c08FP4%s' % RUN_ID)[:50],
               'fp_no5': ('_c08FP5%s' % RUN_ID)[:50]}
    RESULT['fixture_ctx'] = {'employee_id': emp.employee_id, 'process_code': ctx['process.code'],
                             'admin_id': admin.id}
    if not ctx['process.code']:
        raise AssertionError('夹具失败：process_price.process_code 为空，无法构造好行')

    filename = '%s%s_%s.xlsx' % (PROBE_PREFIX, RUN_ID, str(SPEC.get('id')))[:80]
    #: ⚠ 坑（V-10 实测）：端点用 `secure_filename(filename)` 落盘，而 werkzeug 会**剥掉前导
    #: 下划线**（`_c08_…` → `c08_…`）。若探针按原样名判残留，会得到「不存在」的**假绿**。
    #: ⇒ 必须用与 app 相同的口径算出落盘名，并额外做一次「按场景名模糊匹配」的兜底。
    from werkzeug.utils import secure_filename
    disk_name = secure_filename(filename)
    RESULT['upload_filename'] = filename
    RESULT['disk_filename'] = disk_name
    RESULT['disk_filename_differs'] = (disk_name != filename)
    residue_dir = temp_folder if SPEC.get('residue_dir') == 'temp_folder' else ostemp
    RESULT['residue_dir_used'] = residue_dir

    def residue_probe():
        """残留判定：主判据（与 app 同口径的落盘名）+ 兜底（目录里含场景名的同后缀文件）。"""
        hit = os.path.exists(os.path.join(residue_dir, disk_name))
        scanned = []
        try:
            for name in os.listdir(residue_dir):
                if name.endswith('.xlsx') and str(SPEC.get('id')) in name:
                    scanned.append(name)
        except OSError:
            pass
        return (hit or bool(scanned)), {'exact_exists': hit, 'scanned_hits': scanned,
                                        'disk_name': disk_name}

    # ---- 造 xlsx（内存）或损坏文件
    if SPEC.get('kind') == 'import-corrupt':
        blob = b'this is not a valid xlsx (C-08 corrupt-file fixture)'
    else:
        rows = [[resolve(c, ctx) for c in r] for r in (SPEC.get('rows') or [])]
        blob = build_xlsx(SPEC.get('headers') or [], rows)
    RESULT['fixture_bytes'] = len(blob)
    RESULT['fixture_rows'] = len(SPEC.get('rows') or [])

    # ---- 基线读数
    with app.app_context():
        base_target = table_count(db, SPEC.get('target_table') or 'audit_log')
    base_temp = listing(temp_folder)
    base_ostemp = listing(ostemp, prefix=PROBE_PREFIX)
    base_residue, base_residue_detail = residue_probe()
    RESULT['before'] = {'target_count': base_target,
                        'temp_folder_count': len([k for k in base_temp if k != '__error__']),
                        'ostemp_probe_files': sorted(k for k in base_ostemp
                                                     if k != '__error__'),
                        'residue_exists': base_residue,
                        'residue_detail': base_residue_detail}
    trace('before: target=%s temp_folder=%d files ostemp_probe=%s residue=%s'
          % (base_target, RESULT['before']['temp_folder_count'],
             RESULT['before']['ostemp_probe_files'], base_residue))

    # ---- 发请求（登录用 session 注入）
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(admin.id)
        sess['_fresh'] = True
    raised = None
    try:
        resp = client.post(SPEC['endpoint'],
                           data={'file': (io.BytesIO(blob), filename)},
                           content_type='multipart/form-data')
        RESULT['http_status'] = resp.status_code
        body = resp.get_data(as_text=True)
        RESULT['http_body'] = body[:600]
        try:
            RESULT['json'] = json.loads(body)
        except Exception:
            RESULT['json'] = None
    except BaseException as e:                                # noqa: BLE001
        raised = {'type': e.__class__.__name__, 'message': str(e)[:400]}
        RESULT['http_raised'] = raised
    trace('request: POST %s -> status=%s raised=%s'
          % (SPEC['endpoint'], RESULT.get('http_status'), (raised or {}).get('type')))

    RESULT['message_parsed'] = parse_message((RESULT.get('json') or {}).get('message')
                                             if isinstance(RESULT.get('json'), dict) else '')
    RESULT['injection_fired'] = None

    # ---- 术后读数（含残留判据）
    with app.app_context():
        db.session.remove()          # 丢弃可能的失败会话状态，保证读数不被污染
        after_target = table_count(db, SPEC.get('target_table') or 'audit_log')
    after_temp = listing(temp_folder)
    after_ostemp = listing(ostemp, prefix=PROBE_PREFIX)
    residue_exists, residue_detail = residue_probe()
    RESULT['after'] = {
        'target_count': after_target,
        'delta_target': (None if isinstance(after_target, dict) or isinstance(base_target, dict)
                         else after_target - base_target),
        'residue_exists': residue_exists,
        'residue_detail': residue_detail,
        'temp_folder_added': sorted(set(after_temp) - set(base_temp) - {'__error__'}),
        'temp_folder_removed': sorted(set(base_temp) - set(after_temp) - {'__error__'}),
        'ostemp_probe_files': sorted(k for k in after_ostemp if k != '__error__'),
    }
    trace('after: target=%s delta=%s residue=%s temp_added=%s temp_removed=%s'
          % (after_target, RESULT['after']['delta_target'], residue_exists,
             RESULT['after']['temp_folder_added'], RESULT['after']['temp_folder_removed']))

    RESULT['real_db_sha256_after'] = _env.sha256_file(_env.REAL_DB)
    RESULT['real_db_unchanged'] = (RESULT['real_db_sha256_before']
                                   == RESULT['real_db_sha256_after'])
    RESULT['real_db_pinned'] = _env.REAL_DB_SHA256_EXPECTED
    try:
        _env.assert_real_db_untouched('c08 child ' + str(SPEC.get('id')))
        RESULT['real_db_assert_ok'] = True
    except Exception as e:                                    # noqa: BLE001
        RESULT['real_db_assert_ok'] = False
        RESULT['errors'].append('真实库指纹断言失败：%s' % e)
    RESULT['trace'] = TRACE
    print('##R2C08-RESULT##' + json.dumps(_json_safe(RESULT), ensure_ascii=False))
    return 0


def run_export(app, temp_folder):
    """B-08.3：导出前后 `uploads/temp` 清单逐一相同（+ 阳性对照）。"""
    client = app.test_client()
    with app.app_context():
        from app import models as M
        admin = M.User.query.filter_by(username='admin').first() or M.User.query.first()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(admin.id)
        sess['_fresh'] = True

    #: 预热请求：让 `@bp.before_request` 的 `cleanup_temp_files()`（>300s 阈值）先把
    #: 历史遗留文件清掉 ⇒ 之后的 before/after 之间不会再发生「钩子删旧文件」的干扰
    priming = client.get('/export_tasks')
    RESULT['priming_status'] = priming.status_code
    trace('priming: GET /export_tasks -> %s' % priming.status_code)

    before = listing(temp_folder)
    RESULT['before'] = {'temp_folder': before,
                        'count': len([k for k in before if k != '__error__'])}
    injected = None
    if SPEC.get('kind') == 'export-sensitivity':
        #: 阳性对照：手工放一个新文件 ⇒ 清单比对必须发现
        injected = os.path.join(temp_folder, '%s%s_sensitivity.tmp' % (PROBE_PREFIX, RUN_ID))
        with open(injected, 'w', encoding='utf-8') as fh:
            fh.write('C-08 清单比对敏感性对照\n')
        RESULT['injected_file'] = os.path.basename(injected)
        mid = listing(temp_folder)
        RESULT['mid'] = {'temp_folder': mid, 'count': len([k for k in mid if k != '__error__'])}
        RESULT['sensitivity_detected'] = set(mid) != set(before)
        try:
            os.remove(injected)
        except OSError as e:
            RESULT['errors'].append('清理对照文件失败：%s' % e)
        RESULT['after_cleanup_identical'] = set(listing(temp_folder)) == set(before)

    raised = None
    resp = None
    try:
        resp = client.get(SPEC['endpoint'])
        RESULT['http_status'] = resp.status_code
        RESULT['content_type'] = resp.headers.get('Content-Type', '')
        RESULT['content_disposition'] = resp.headers.get('Content-Disposition', '')
        RESULT['bytes'] = len(resp.get_data())
        blob = resp.get_data()
        try:
            from openpyxl import load_workbook
            wb = load_workbook(io.BytesIO(blob))
            ws = wb.active
            RESULT['xlsx_ok'] = True
            RESULT['xlsx_sheets'] = len(wb.sheetnames)
            RESULT['xlsx_rows'] = ws.max_row
            RESULT['xlsx_cols'] = ws.max_column
        except Exception as e:                                # noqa: BLE001
            RESULT['xlsx_ok'] = False
            RESULT['xlsx_error'] = '%s: %s' % (e.__class__.__name__, str(e)[:200])
    except BaseException as e:                                # noqa: BLE001
        raised = {'type': e.__class__.__name__, 'message': str(e)[:400]}
        RESULT['http_raised'] = raised
    trace('export: GET %s -> status=%s bytes=%s xlsx_ok=%s'
          % (SPEC['endpoint'], RESULT.get('http_status'), RESULT.get('bytes'),
             RESULT.get('xlsx_ok')))

    after = listing(temp_folder)
    RESULT['after'] = {'temp_folder': after,
                       'count': len([k for k in after if k != '__error__'])}
    RESULT['added'] = sorted(set(after) - set(before) - {'__error__'})
    RESULT['removed'] = sorted(set(before) - set(after) - {'__error__'})
    RESULT['changed_content'] = sorted(
        k for k in (set(before) & set(after))
        if (before[k] or {}).get('sha256') != (after[k] or {}).get('sha256'))
    RESULT['listing_identical'] = (not RESULT['added'] and not RESULT['removed']
                                   and not RESULT['changed_content'])
    trace('after: count=%s added=%s removed=%s changed=%s identical=%s'
          % (RESULT['after']['count'], RESULT['added'], RESULT['removed'],
             RESULT['changed_content'], RESULT['listing_identical']))

    RESULT['real_db_sha256_after'] = _env.sha256_file(_env.REAL_DB)
    RESULT['real_db_unchanged'] = (RESULT['real_db_sha256_before']
                                   == RESULT['real_db_sha256_after'])
    RESULT['real_db_pinned'] = _env.REAL_DB_SHA256_EXPECTED
    try:
        _env.assert_real_db_untouched('c08 child ' + str(SPEC.get('id')))
        RESULT['real_db_assert_ok'] = True
    except Exception as e:                                    # noqa: BLE001
        RESULT['real_db_assert_ok'] = False
        RESULT['errors'].append('真实库指纹断言失败：%s' % e)
    RESULT['trace'] = TRACE
    print('##R2C08-RESULT##' + json.dumps(_json_safe(RESULT), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    try:
        _rc = main()
    except Exception:                       # noqa: BLE001 —— SystemExit 不在此列（正常出口）
        print('##R2C08-RESULT##' + json.dumps(
            {'scenario': SPEC.get('id'), 'fatal': traceback.format_exc()[-1500:]},
            ensure_ascii=False))
        _rc = 3
    sys.exit(_rc)
'''


def child_script_path(run_id, scenario_id):
    safe = re.sub(r'[^0-9A-Za-z_.-]', '_', str(scenario_id))
    return os.path.join(_env.tmp_dir('c08', 'child'),
                        'c08_%s_%s.py' % (str(run_id).replace(os.sep, '_'), safe))


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
                                    'C08_HARNESS_DIR': HERE,
                                    'C08_SCRIPTS_DIR': _env.SCRIPTS_DIR,
                                    'C08_REPO_ROOT': REPO_ROOT,
                                    'C08_RUN_ID': run_id,
                                    'C08_SPEC': json.dumps(spec, ensure_ascii=False)},
                         label='c08-%s' % spec['id'])
    out['payload'] = _parse_payload(out['stdout'], out['stderr'])
    out['script'] = path
    return out


def cleanup_probe_files(run_id):
    """收尾：只删**本 run 自己命名**的残留（读数已落地，不影响证据）。

    ⚠ 匹配口径必须与 app 的 `secure_filename` 一致：它**剥掉前导下划线** ⇒ 磁盘上的名字是
    `c08_<run_id>_…`（无前导 `_`）。首跑曾因按 `_c08_*` 匹配而一个都没清掉（实测留 2 个）。
    """
    removed = []
    targets = [os.path.join(REPO_ROOT, 'uploads', 'temp'), tempfile.gettempdir()]
    for directory in targets:
        try:
            names = os.listdir(directory)
        except OSError:
            continue
        for name in names:
            if not name.lower().startswith(PROBE_PREFIX.strip('_')):   # 'c08'
                continue
            if str(run_id) not in name:
                continue
            p = os.path.join(directory, name)
            if not os.path.isfile(p):
                continue
            try:
                os.remove(p)
                removed.append(rel(p) if p.startswith(REPO_ROOT) else p)
            except OSError as e:
                removed.append('FAILED %s: %s' % (name, e))
    return removed


# --------------------------------------------------------------------- 判据（纯函数）
def eval_checks(results, covered_endpoints, cleanup_report):
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

    # ---------------------------------------------------------------- B-08.1 主体
    s1 = one('S1-tasks-3good-2bad')
    m1 = s1.get('message_parsed') or {}
    s1_ok_counts = (s1.get('http_status') == 200 and (m1.get('success_count') == 3)
                    and (m1.get('error_count') == 2)
                    and ((s1.get('after') or {}).get('delta_target') == 3))
    add('C-08.1.a(tasks 3good+2bad counts)',
        'B-08.1 主体：`/tasks/import` 混入 2 个坏行 ⇒ **HTTP 非 5xx**、'
        '`成功导入 3 条`、错误清单 **2 条**、库内 `task_assignment` **Δ=3**（好行必须入库、不整单回滚）',
        {'http_not_5xx': True, 'success_count': 3, 'error_count': 2, 'db_delta': 3},
        {'http_status': s1.get('http_status'), 'success_count': m1.get('success_count'),
         'error_count': m1.get('error_count'),
         'delta_target': (s1.get('after') or {}).get('delta_target'),
         'error_items': m1.get('error_items')},
        'passed' if s1_ok_counts else 'failed',
        evidence=rel(s1.get('out_file') or ''),
        note='五元组①业务语义 + ②载体 `routes.py:3987` + ③期望值；变红条件=任一坏行导致整单 0 行/500',
        gap_owner='probe')

    add('C-08.1.b(tasks row-number in errors)',
        'B-08.1 判据③：错误清单**逐条含「第 N 行」**（N = xlsx 真实行号，表头为第 1 行）'
        '—— 本条按**端点实际实现**判：`/tasks/import` 的「工号不存在」「工序不存在」两类'
        '（`routes.py:4016/:4022`）**不带行号**，只有日期类（`:4028`）带',
        {'row_number_all_ok': True, 'row_numbers': '非空且等于坏行真实行号'},
        {'row_number_all_ok': m1.get('row_number_all_ok'), 'row_numbers': m1.get('row_numbers'),
         'error_items': m1.get('error_items'),
         'carrier': {'exists_with_rowno': 'app/main/routes.py:4028',
                     'missing_rownno': ['app/main/routes.py:4016', 'app/main/routes.py:4022']}},
        'passed' if m1.get('row_number_all_ok') else 'failed',
        evidence=rel(s1.get('out_file') or ''),
        note='变红条件 = 错误清单为空或**不带行号**；本条红即被测方缺口（gap_owner=product）',
        gap_owner='product')

    add('C-08.1.c(tasks date-class row-number)',
        'B-08.1 判据③（日期类）：`日期文本非法` 的坏行（第 3 行）⇒ 错误必须带**真行号**「第 3 行」'
        '（证明「第 N 行」机制在本端点**确实存在**，故上一条的红不是「格式从未实现」）',
        {'row_numbers': [3]},
        {'row_numbers': (one('S3-tasks-baddate').get('message_parsed') or {}).get('row_numbers'),
         'error_items': (one('S3-tasks-baddate').get('message_parsed') or {}).get('error_items'),
         'success_count': (one('S3-tasks-baddate').get('message_parsed') or {})
         .get('success_count')},
        'passed' if ((one('S3-tasks-baddate').get('message_parsed') or {})
                     .get('row_numbers') == [3]) else 'failed',
        evidence=rel(one('S3-tasks-baddate').get('out_file') or ''),
        note='载体 app/main/routes.py:4028（`f\'第 {index + 2} 行：{date_error}\'`）')

    s2 = one('S2-tasks-5good')
    m2 = s2.get('message_parsed') or {}
    s2_ok = ((m2.get('success_count') == 5) and (m2.get('error_count') in (0, None))
             and ((s2.get('after') or {}).get('delta_target') == 5)
             and not (m2.get('error_items') or []))
    add('C-08.1.d(5-good negative control)',
        'B-08.1 阴性对照（**防恒真**）：5 行**全好** ⇒ `成功导入 5 条`、**错误 0 条**、Δ=5 '
        '（若全好也报错，说明判据/实现是「一律报坏行」）',
        {'success_count': 5, 'error_count': 0, 'db_delta': 5},
        {'success_count': m2.get('success_count'), 'error_count': m2.get('error_count'),
         'delta_target': (s2.get('after') or {}).get('delta_target'),
         'error_items': m2.get('error_items')},
        'passed' if s2_ok else 'failed',
        evidence=rel(s2.get('out_file') or ''),
        note='五元组⑤证伪条件（防恒真）')

    s5 = one('S5-employees-3good-2bad')
    m5 = s5.get('message_parsed') or {}
    s5_rowno_ok = bool(m5.get('row_number_all_ok'))
    s5_tolerant_ok = ((s5.get('after') or {}).get('delta_target') == 3)
    add('C-08.1.e(employees row-tolerance)',
        'B-08.1 第二个端点 `/employees/import`：3 好 + 2 坏 ⇒ 好行**必须入库**（Δ=3）'
        '且错误 **2 条** —— 该端点实现在 `:2061-2066` **先全量校验、有错即整单返回**，'
        '故「好行入库」这一半预期不成立（B-08.1 的变红条件之一：整单 0 行）',
        {'success_count': 3, 'error_count': 2, 'db_delta': 3, 'row_number_all_ok': True},
        {'http_status': s5.get('http_status'), 'success_count': m5.get('success_count'),
         'error_count': m5.get('error_count'),
         'delta_target': (s5.get('after') or {}).get('delta_target'),
         'row_number_all_ok': s5_rowno_ok, 'error_items': m5.get('error_items'),
         'carrier': {'whole_order_reject': 'app/main/routes.py:2061-2066',
                     'row_number': 'app/main/routes.py:2058'}},
        'passed' if (s5_tolerant_ok and s5_rowno_ok and m5.get('error_count') == 2) else 'failed',
        evidence=rel(s5.get('out_file') or ''),
        note='两条互补结论：该端点**有**行号但**不**行级容错；与 /tasks/import 恰好相反 '
             '⇒ B-08.1 在两个端点上分别缺一半',
        gap_owner='product')

    n_tolerant = len([1 for s, ok in (('S1', s1_ok_counts), ('S5', s5_tolerant_ok)) if ok])
    add('C-08.1.f(non-vacuity)',
        '非恒真对照：B-08.1 的两半在不同端点上**分别为绿**（`/tasks/import` 计数绿、'
        '`/employees/import` 行号绿）⇒ 本判据既非恒真也非恒假，红点是**定位到具体端点/类的**',
        {'tasks_counts_green': True, 'employees_rowno_green': True},
        {'tasks_counts_ok': s1_ok_counts, 'employees_rowno_ok': s5_rowno_ok,
         'tolerant_endpoints': n_tolerant},
        'passed' if (s1_ok_counts and s5_rowno_ok) else 'failed',
        evidence='见 C-08.1.a / C-08.1.b / C-08.1.e 的 evidence',
        note='用来排除「整条判据恒红所以无从改进」的读法')

    # ---------------------------------------------------------------- B-08.2 上传清理（成对）
    s4 = one('S4-tasks-parsefail')
    s6 = one('S6-finished-3good-2bad')
    tf_ok = ((s1.get('after') or {}).get('residue_exists') is False)
    tf_parsefail_ok = (s4.get('after') or {}).get('residue_exists') is False
    tf_emp_ok = (s5.get('after') or {}).get('residue_exists') is False
    os_ok = (s6.get('after') or {}).get('residue_exists') is False
    add('C-08.2.a(TEMP_FOLDER class)',
        'B-08.2 **TEMP_FOLDER 类**断言：上传文件在请求返回后**不再存在**于 '
        '`<repo>/uploads/temp`（对照 `>300s` 阈值事实：钩子 `routes.py:2194` 清不动当次新文件 '
        '⇒ 只能靠端点自己的清理）',
        {'residue_exists': False},
        {'happy_path_tasks': {'residue_exists': (s1.get('after') or {}).get('residue_exists'),
                              'carrier': 'app/main/routes.py:4006（解析后 os.remove，无 finally）'},
         'parse_fail_tasks': {'residue_exists': s4.get('after') or {},
                              'residue_exists_bool': (s4.get('after') or {})
                              .get('residue_exists'),
                              'carrier': 'app/main/routes.py:4000-4006 无 finally'},
         'happy_path_employees': {'residue_exists': (s5.get('after') or {})
                                  .get('residue_exists'),
                                  'carrier': 'app/main/routes.py:1935-2178 仅 except 里 os.remove'},
         'filename': s1.get('upload_filename'), 'dir': s1.get('residue_dir_used')},
        'passed' if (tf_ok and tf_parsefail_ok and tf_emp_ok) else 'failed',
        evidence=rel(s1.get('out_file') or ''),
        note='变红条件 = 导入后文件仍存在且**非** 5 分钟阈值内的当次文件；'
             '三条子读数分别对应「正常路径 / 解析失败 / 另一端点正常路径」',
        gap_owner='product')

    add('C-08.2.b(OS-temp class)',
        'B-08.2 **OS-temp 类**断言（`35` §4-② 双前置之一）：`/inventory/finished/import` 落 '
        '`tempfile.gettempdir()`（`routes.py:4892`，**不被清理钩子覆盖**）⇒ 请求返回后该文件必须不残留',
        {'residue_exists': False},
        {'residue_exists': (s6.get('after') or {}).get('residue_exists'),
         'dir': s6.get('residue_dir_used'), 'filename': s6.get('upload_filename'),
         'carrier': 'app/main/routes.py:4959-4962（finally: os.remove）'},
        'passed' if os_ok else 'failed',
        evidence=rel(s6.get('out_file') or ''),
        note='这一条与 C-08.2.a 构成「TEMP_FOLDER + OS-temp」**成对**判据（缺一不可）')

    add('C-08.2.c(paired asserts present)',
        '成对性自证：两类的残留断言**都实际执行过**（各自的 `residue_dir_used` 一个指向 '
        '`uploads/temp`、一个指向 `tempfile.gettempdir()`），且覆盖 3 个导入端点 '
        '（`/tasks/import`、`/employees/import`、`/inventory/finished/import`）',
        {'temp_folder_class': True, 'ostemp_class': True},
        {'temp_folder_dir': s1.get('residue_dir_used'), 'ostemp_dir': s6.get('residue_dir_used'),
         'endpoints': covered_endpoints,
         'runtime_dirs': s1.get('runtime_dirs')},
        'passed' if (s1.get('residue_dir_used') and s6.get('residue_dir_used')
                     and str(s6.get('residue_dir_used')) != str(s1.get('residue_dir_used'))
                     and len(covered_endpoints) >= MIN_IMPORT_ENDPOINTS) else 'failed',
        evidence=rel(s6.get('out_file') or ''),
        note='双前置②：两个导入落 OS-temp ⇒ 只写 TEMP_FOLDER 一条会漏判',
        evidence_kind='content_implementation')

    # ---------------------------------------------------------------- B-08.3 导出零残留
    s7 = one('S7-export-tasks')
    s8 = one('S8-export-sensitivity')
    mime_ok = 'spreadsheetml.sheet' in (s7.get('content_type') or '')
    exp_ok = (s7.get('listing_identical') is True and mime_ok
              and s7.get('xlsx_ok') is True and s7.get('http_status') == 200)
    add('C-08.3.a(export zero-residue)',
        'B-08.3：导出**前后** `uploads/temp` 清单**逐一相同**（文件名集合 + 内容 SHA256 皆相同）'
        '，且响应 `Content-Type` 为 xlsx、正文可被 `openpyxl` 打开（内存生成 `io.BytesIO`）',
        {'listing_identical': True, 'content_type_contains': 'spreadsheetml.sheet',
         'xlsx_ok': True, 'http_status': 200},
        {'listing_identical': s7.get('listing_identical'), 'added': s7.get('added'),
         'removed': s7.get('removed'), 'changed_content': s7.get('changed_content'),
         'before_count': (s7.get('before') or {}).get('count'),
         'after_count': (s7.get('after') or {}).get('count'),
         'content_type': s7.get('content_type'), 'xlsx_ok': s7.get('xlsx_ok'),
         'xlsx_rows': s7.get('xlsx_rows'), 'xlsx_cols': s7.get('xlsx_cols'),
         'bytes': s7.get('bytes'), 'http_status': s7.get('http_status'),
         'carrier': 'app/main/routes.py:4115（io.BytesIO）/ :4119（send_file）'},
        'passed' if exp_ok else 'failed',
        evidence=rel(s7.get('out_file') or ''),
        note='变红条件 = 导出后出现**新文件**或含本次请求标识的文件；⚠ 必须成对写，'
             '不得把 `>300s` 历史文件（钩子清理）当成本次残留 ⇒ 探针先做预热请求再取前快照')

    add('C-08.3.b(export listing sensitivity)',
        'B-08.3 阳性对照（**防恒真**）：手工往 `uploads/temp` 放一个新文件 ⇒ 清单比对**必须**发现；'
        '删除后必须恢复一致（证明「清单逐一相同」不是「永远相同」）',
        {'sensitivity_detected': True, 'after_cleanup_identical': True},
        {'sensitivity_detected': s8.get('sensitivity_detected'),
         'after_cleanup_identical': s8.get('after_cleanup_identical'),
         'injected_file': s8.get('injected_file'),
         'before_count': (s8.get('before') or {}).get('count'),
         'mid_count': (s8.get('mid') or {}).get('count')},
        'passed' if (s8.get('sensitivity_detected') and s8.get('after_cleanup_identical'))
        else 'failed',
        evidence=rel(s8.get('out_file') or ''),
        note='判据强度要求：阴性对照必须能红（否则「清单相同」是恒真断言）')

    n_export = len([1 for ok in (exp_ok, bool(s8.get('sensitivity_detected'))) if ok])
    add('C-08.3.c(export endpoints covered)',
        '覆盖面登记（抽样率）：导出侧本轮实测 **1/13** 处 `io.BytesIO` 内存生成'
        '（`/export_tasks`，`routes.py:4115`）；其余导出与「轨二（非沙箱环境）零残留」登记在 '
        '`uncovered_faces` / `blocked_faces`',
        {'export_endpoints_covered': 1, 'blocked_track2': '登记 blocked'},
        {'export_endpoints_covered': n_export, 'sampled': '/export_tasks（routes.py:4068）'},
        'passed' if n_export >= 1 else 'failed',
        evidence=rel(s7.get('out_file') or ''),
        evidence_kind='content_implementation',
        note='13 处内存生成本轮只抽样 1 处；未覆盖面逐条登记（见 coverage.uncovered_faces）')

    # ---------------------------------------------------------------- 不变量与自证
    allr = [r for r in results if r.get('scenario')]
    db_ok = bool(allr) and all(r.get('real_db_unchanged') and r.get('real_db_assert_ok')
                              for r in allr)
    add('C-08.4(db)',
        '不变量：全部场景全程真实库 app.db SHA256 不变（= 钉死值）',
        {'sha256': _env.REAL_DB_SHA256_EXPECTED, 'unchanged': True},
        {'per_scenario': {r.get('scenario'): {'unchanged': r.get('real_db_unchanged'),
                                              'assert_ok': r.get('real_db_assert_ok')}
                          for r in allr}},
        'passed' if db_ok else 'failed',
        evidence='每个子进程的 real_db_sha256_before/after',
        note='一切库操作走带 RUN_ID 的副本；上传目录是真实路径但只碰自己命名的 _c08_* 文件')

    add('C-08.5(probe self-check)',
        '探针自证：8 个场景**全部**在独立子进程里产出可解析读数（无 fatal、有 http_status/'
        'before/after），且收尾只清理自己命名的文件',
        {'scenarios_with_readings': len(SCENARIOS), 'fatal': 0},
        {'scenarios': len(allr),
         'with_readings': len([r for r in allr if r.get('before') and not r.get('fatal')]),
         'fatal_scenarios': [r.get('scenario') for r in allr if r.get('fatal')],
         'cleanup_removed': cleanup_report},
        'passed' if (len(allr) == len(SCENARIOS)
                     and not [r for r in allr if r.get('fatal')]) else 'failed',
        evidence='各子场景 stdout/stderr',
        evidence_kind='behavior_verified', note='')

    failed = [r['id'] for r in A if r['verdict'] != 'passed']
    return A, failed


# --------------------------------------------------------------------- 父进程编排
def full_run(args):
    started = time.strftime('%Y-%m-%d %H:%M:%S')
    real_before = _env.assert_real_db_untouched('r2_c08 开工')
    temp_folder = os.path.join(REPO_ROOT, 'uploads', 'temp')
    print('=' * 88)
    print('[c08] C-08 导入行级容错 / 导出零残留 / 上传目录清理探针')
    print('[c08] run_id=%s  time=%s' % (_env.RUN_ID, started))
    print('[c08] 真实库 %s  sha256=%s' % (rel(args.real_db), real_before))
    print('[c08] 运行时目录：TEMP_FOLDER=%s（config.py 的 <repo>/uploads/temp，'
          '**不是副本内**）；OS-temp=%s' % (rel(temp_folder), tempfile.gettempdir()))
    before_listing = {}
    try:
        for name in sorted(os.listdir(temp_folder)):
            p = os.path.join(temp_folder, name)
            if os.path.isfile(p):
                before_listing[name] = {'sha256': sha256(p), 'bytes': os.path.getsize(p)}
    except OSError as e:
        before_listing = {'__error__': str(e)}
    print('[c08] 开工时 uploads/temp 清单：%d 个文件' % len(before_listing))
    print('=' * 88)

    results = []
    for spec in SCENARIOS:
        out = run_scenario(spec, timeout=args.timeout)
        p = out['payload'] or {}
        p['scenario'] = p.get('scenario') or spec['id']
        p['out_file'] = out['out_file']
        p['child_exit_code'] = out['exit_code']
        results.append(p)
        msg = p.get('message_parsed') or {}
        print('  [CASE] %-28s http=%-4s success=%-4s errors=%-4s residue=%-5s '
              'Δtarget=%-4s %s'
              % (spec['id'], p.get('http_status'), msg.get('success_count'),
                 msg.get('error_count'),
                 (p.get('after') or {}).get('residue_exists'),
                 (p.get('after') or {}).get('delta_target'),
                 ('listing_identical=%s' % p.get('listing_identical')
                  if spec['kind'].startswith('export') else '')))
        if p.get('fatal'):
            print('         FATAL: %s' % str(p.get('fatal'))[-300:])

    real_after = _env.assert_real_db_untouched('r2_c08 收尾')
    covered_endpoints = sorted({s['endpoint'] for s in SCENARIOS
                                if s.get('kind', '').startswith('import')
                                and not s.get('kind') == 'import-corrupt'}
                               | {s['endpoint'] for s in SCENARIOS
                                  if s.get('kind') == 'import-corrupt'})
    cleanup_report = cleanup_probe_files(_env.RUN_ID)
    assertions, failed = eval_checks(results, covered_endpoints, cleanup_report)

    print('')
    print('-' * 88)
    print('[c08] 判据层（含 B-08.1/2/3 本身；`gap_owner` 标明红点归属）')
    for r in assertions:
        print('  %-40s %-8s %-22s %s%s' % (r['id'], r['verdict'].upper(), r['evidence_kind'],
                                           r['title'][:44],
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
    n_tot = len(assertions)
    product_gaps = [r for r in assertions if r['verdict'] != 'passed' and r['gap_owner'] == 'product']
    print('')
    print('[c08] 判据层：%d/%d 通过；失败=%s' % (n_pass, n_tot, failed or '无'))
    print('[c08] 其中产品面缺口 %d 条（gap_owner=product）：%s'
          % (len(product_gaps), [r['id'] for r in product_gaps] or '无'))
    print('[c08] 上传目录收尾：清理自己命名的文件 %d 个（读数已落盘，不影响证据）'
          % len(cleanup_report))
    print('[c08] 真实库 app.db：before=%s after=%s 不变=%s'
          % (real_before[:16] + '...', real_after[:16] + '...', real_before == real_after))
    verdict = 1 if failed else 0
    print('[c08] exit=%d%s' % (verdict, '（红点全部为产品面缺口）' if product_gaps and not
                               [r for r in assertions
                                if r['verdict'] != 'passed' and r['gap_owner'] != 'product']
                               else ''))
    print('=' * 88)

    payload = {
        'run_id': _env.RUN_ID, 'started': started,
        'probe': 'test-reports-2026-10/harness/r2_c08_probe.py',
        'task': 'V-10 / t11 (C-08)',
        'criteria_ids': ['B-08.1', 'B-08.2', 'B-08.3'],
        'runtime_dirs': {'temp_folder': rel(temp_folder),
                         'temp_folder_abs': temp_folder,
                         'ostemp': tempfile.gettempdir(),
                         'note': 'TEMP_FOLDER 来自 config.py = <repo>/uploads/temp；'
                                 '副本只换 DATABASE_URL'},
        'preconditions_from_spec': {
            'P-1': 'routes.py:2194 阈值 >300s 才清理（钩子清不动当次新文件）',
            'P-2': 'routes.py:4892/4979 两个导入落 tempfile.gettempdir()（不被钩子覆盖）'
                   '⇒ TEMP_FOLDER 类与 OS-temp 类**各一条**断言',
        },
        'covered_endpoints': covered_endpoints,
        'uploads_temp_listing_at_start': before_listing,
        'real_db': {'path': rel(args.real_db), 'sha256_before': real_before,
                    'sha256_after': real_after, 'unchanged': real_before == real_after,
                    'pinned': _env.REAL_DB_SHA256_EXPECTED},
        'scenarios': results,
        'assertions': assertions,
        'criteria_failed': failed, 'criteria_passed': n_pass, 'criteria_total': n_tot,
        'product_gaps': [{'id': r['id'], 'expected': r['expected'], 'actual': r['actual'],
                          'note': r['note']} for r in product_gaps],
        'cleanup_removed': cleanup_report,
        'blocked_faces': [
            {'id': 'C-08(export-track2)', 'status': 'blocked',
             'reason': '导出零残留「轨二」需非沙箱环境（35 §4 C-08 不可实施面）'},
            {'id': 'C-08(G-11)', 'status': 'not_covered',
             'reason': 'mkdtemp 目录回收（G-11）不在本轮判据内，登记为未覆盖面'},
        ],
        'uncovered_faces': [
            {'face': '导入端点 9 个中本轮驱动 3 个（/tasks/import、/employees/import、'
                     '/inventory/finished/import）',
             'why': '其余 6 个需各自夹具（工序价格/奖惩/生产记录/原料/产品/质检任务）'},
            {'face': '导出 13 处 io.BytesIO 中本轮抽样 1 处（/export_tasks）',
             'why': '其余导出与模板下载需对应数据夹具；判据形态相同'},
            {'face': '解析期抛错的整单失败形态（如「数量」非数字使 parse_task_data 整体抛错）',
             'why': '本轮未构造该类坏行（属 B-08.1 的另一变红形态）'},
            {'face': 'quality.py:1612 质检任务导入（第 9 个端点）',
             'why': '需质检模板夹具'},
        ],
        'exit_code': verdict,
        'evidence_kind': 'behavior_verified',
        'search_domain': {
            'app/**.py 内容搜索 io.BytesIO': '13 处（导出内存生成）',
            'app/**.py 内容搜索 tempfile.gettempdir()': '导入落 OS-temp 的端点'
                                                       '（routes.py:4892/4979）',
            '被测端点（独立阅读）': [s['file_line'] for s in SCENARIOS
                                     if s.get('file_line')],
        },
        'exclude_basenames': ['r2_c08_probe.py（判定脚本自身）', 'captain_r2_*.py',
                              'reconcile_r2.py', 'improve_plan.py', 'analysis_ledger.py',
                              'evidence/** 度量产物'],
        'del_what_goes_red': '把错误文案里的行号去掉 ⇒ C-08.1.a/b/c 必红；让坏行导致整单回滚 ⇒ '
                             'C-08.1.a 必红（Δ=0）；全好行也报错 ⇒ C-08.1.d 必红；'
                             '去掉端点的 os.remove / finally ⇒ C-08.2.a/b 必红；'
                             '把导出改回 mkstemp 落盘 ⇒ C-08.3.a 必红；'
                             '让清单比对恒真 ⇒ C-08.3.b 必红',
        'four_injection_pitfalls_aligned': [
            '1) _env.run_child 是 python -B <argv>：argv 必带脚本路径（本文件写生成脚本到 .tmp 再跑）',
            '2) 不碰 create_app() 启动链（本探针只发 HTTP + 读文件系统）',
            '3) 每个场景一份独立副本 + 上传文件按场景独立命名（_c08_<RUN_ID>_<场景>.xlsx）',
            '4) 授权开关逐场景传参并显式清空（extra_env={WMS_ALLOW_REAL_DB: ""}）',
        ],
    }
    if args.json_out:
        write_text(args.json_out, json.dumps(payload, ensure_ascii=False, indent=1))
    saved = _env.save_evidence('r2_c08_probe.json',
                               json.dumps(payload, ensure_ascii=False, indent=1))
    print('[c08] 机读结果已落盘 %s' % rel(saved))
    if args.json_out:
        print('[c08] --json-out 副本 %s' % rel(args.json_out))
    return verdict


# --------------------------------------------------------------------- 工具自检
def synth_case(sid, *, http=200, success=None, errors=None, db_delta=None,
               row_numbers=None, row_number_all_ok=None, residue=None,
               listing_identical=None, xlsx_ok=True, content_type=None,
               sensitivity=None, fatal=None, kind=None):
    spec = next(s for s in SCENARIOS if s['id'] == sid)
    out = {'scenario': sid, 'kind': kind or spec.get('kind'),
           'http_status': http, 'upload_filename': '%s%s.xlsx' % (PROBE_PREFIX, sid),
           'residue_dir_used': ('/repo/uploads/temp' if spec.get('residue_dir') == 'temp_folder'
                                else '/os/temp'),
           'runtime_dirs': {'temp_folder': '/repo/uploads/temp', 'ostemp': '/os/temp'},
           'before': {'target_count': 10, 'temp_folder_count': 0, 'residue_exists': False},
           'after': {'target_count': (10 + (db_delta or 0)), 'delta_target': db_delta,
                     'residue_exists': residue, 'temp_folder_added': [],
                     'temp_folder_removed': [], 'ostemp_probe_files': []},
           'message_parsed': {'success_count': success, 'error_count': errors,
                              'row_numbers': row_numbers or [],
                              'row_number_all_ok': row_number_all_ok,
                              'error_items': ['(synthetic)'] * (errors or 0),
                              'literal_brace_bug': False},
           'real_db_unchanged': True, 'real_db_assert_ok': True, 'out_file': '(synthetic)'}
    if spec.get('kind', '').startswith('export'):
        out.update({'listing_identical': listing_identical, 'added': [], 'removed': [],
                    'changed_content': [], 'xlsx_ok': xlsx_ok,
                    'content_type': content_type or
                    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    'xlsx_rows': 11, 'xlsx_cols': 5, 'bytes': 5123,
                    'before': {'count': 3}, 'after': {'count': 3},
                    'sensitivity_detected': sensitivity, 'after_cleanup_identical': True,
                    'mid': {'count': 4}, 'injected_file': '_c08_inj.tmp'})
    if fatal:
        out['fatal'] = fatal
    return out


def synth_results():
    """合成读数：真实链路的**同形**形态（计数绿、行号红、员工端点整单 0 行、清理红）。"""
    return [
        synth_case('S1-tasks-3good-2bad', success=3, errors=2, db_delta=3,
                   row_numbers=[], row_number_all_ok=False, residue=False),
        synth_case('S2-tasks-5good', success=5, errors=0, db_delta=5,
                   row_numbers=[], row_number_all_ok=None, residue=False),
        synth_case('S3-tasks-baddate', success=1, errors=1, db_delta=1,
                   row_numbers=[3], row_number_all_ok=True, residue=False),
        synth_case('S4-tasks-parsefail', http=200, residue=True, db_delta=0),
        synth_case('S5-employees-3good-2bad', http=200, success=0, errors=2, db_delta=0,
                   row_numbers=[4, 5], row_number_all_ok=True, residue=True),
        synth_case('S6-finished-3good-2bad', success=3, errors=2, db_delta=3,
                   row_numbers=[], row_number_all_ok=False, residue=False),
        synth_case('S7-export-tasks', listing_identical=True, xlsx_ok=True),
        synth_case('S8-export-sensitivity', listing_identical=True, sensitivity=True),
    ]


def selftest(args):
    """自检：合成读数 ⇒ 判据函数的预期判定（含「必须报红」的阳性样本）。

    证明的不是「真实代码通过了」，而是**本探针的判据会红**：
    ① `baseline`：合成读数（缺陷形态）⇒ 4 条产品面缺口必红，`gap_owner` 全部为 product；
    ② `all-green`：把缺口全修好 ⇒ 判据层全过、exit 0（证明判据不是恒红）；
    ③ `no-residue-check`：清理类读数缺失（residue=None）⇒ `C-08.2.*` 必红；
    ④ `export-residue`：导出后清单出现新文件 ⇒ `C-08.3.a` 必红；
    ⑤ `listing-vacuous`：清单比对恒真（sensitivity=False）⇒ `C-08.3.b` 必红；
    ⑥ `always-errors`：5 行全好也报错 ⇒ `C-08.1.d` 必红。
    """
    checks = []
    real_before = _env.assert_real_db_untouched('r2_c08 selftest')
    print('=' * 88)
    print('[selftest] 判据函数对拍（合成读数 ⇒ 预期判定）')
    print('=' * 88)

    def run_case(tag, results, expect_failed, expect_exit):
        assertions, failed = eval_checks(results, ['a', 'b', 'c'], [])
        ok_fail = set(failed) == set(expect_failed)
        ok_exit = (0 if not failed else 1) == expect_exit
        good = ok_fail and ok_exit
        checks.append({'tag': tag, 'failed': failed, 'expect_failed': sorted(expect_failed),
                       'exit': expect_exit, 'ok': good})
        print('  [%s] %-18s failed=%-64s 期望=%-64s exit=%s(期望 %s)'
              % ('PASS' if good else 'FAIL', tag, json.dumps(failed),
                 json.dumps(sorted(expect_failed)), 0 if not failed else 1, expect_exit))
        if not good:
            print('         verdicts=%s'
                  % json.dumps({r['id']: r['verdict'] for r in assertions}, ensure_ascii=False))
        return good

    gap_ids = {'C-08.1.b(tasks row-number in errors)',
               'C-08.1.e(employees row-tolerance)',
               'C-08.2.a(TEMP_FOLDER class)'}
    ok_all = True
    ok_all &= run_case('baseline', synth_results(), gap_ids, 1)

    green = synth_results()
    for r in green:
        if r['scenario'] == 'S1-tasks-3good-2bad':
            r['message_parsed']['row_number_all_ok'] = True
            r['message_parsed']['row_numbers'] = [5, 6]
            r['message_parsed']['error_items'] = ['第 5 行：员工工号不存在', '第 6 行：工序编号不存在']
        if r['scenario'] == 'S5-employees-3good-2bad':
            r['after']['delta_target'] = 3
            r['after']['residue_exists'] = False
            r['message_parsed']['success_count'] = 3
        if r['scenario'] == 'S4-tasks-parsefail':
            r['after']['residue_exists'] = False
    ok_all &= run_case('all-green', green, set(), 0)

    r = synth_results()
    for x in r:
        if x['scenario'] in ('S1-tasks-3good-2bad', 'S4-tasks-parsefail',
                             'S5-employees-3good-2bad'):
            x['after']['residue_exists'] = None
    ok_all &= run_case('no-residue-readings', r,
                       gap_ids | {'C-08.2.a(TEMP_FOLDER class)'}, 1)

    r = synth_results()
    for x in r:
        if x['scenario'] == 'S7-export-tasks':
            x['listing_identical'] = False
            x['added'] = ['_c08_new.tmp']
    ok_all &= run_case('export-residue', r, gap_ids | {'C-08.3.a(export zero-residue)'}, 1)

    r = synth_results()
    for x in r:
        if x['scenario'] == 'S8-export-sensitivity':
            x['sensitivity_detected'] = False
    ok_all &= run_case('listing-vacuous', r, gap_ids | {'C-08.3.b(export listing sensitivity)'}, 1)

    r = synth_results()
    for x in r:
        if x['scenario'] == 'S2-tasks-5good':
            x['message_parsed']['error_count'] = 5
            x['message_parsed']['error_items'] = ['(synthetic)'] * 5
    ok_all &= run_case('always-errors', r, gap_ids | {'C-08.1.d(5-good negative control)'}, 1)

    real_ok = _env.sha256_file(_env.REAL_DB) == real_before == _env.REAL_DB_SHA256_EXPECTED
    ok_all &= real_ok
    print('  [%s] 真实库 app.db SHA256 = %s（钉死值）'
          % ('PASS' if real_ok else 'FAIL', real_before))
    payload = {'mode': 'selftest', 'run_id': _env.RUN_ID, 'checks': checks,
               'real_db_sha256': real_before, 'real_db_ok': real_ok,
               'verdict': 'passed' if ok_all else 'failed'}
    saved = _env.save_evidence('r2_c08_probe_selftest.json',
                               json.dumps(payload, ensure_ascii=False, indent=1))
    print('[selftest] 结论：%s（1 组缺陷基线 + 5 组必红 + 1 组全绿对拍）'
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
        return {k: {'success': ((v.get('message_parsed') or {}).get('success_count')),
                    'errors': ((v.get('message_parsed') or {}).get('error_count')),
                    'row_numbers': ((v.get('message_parsed') or {}).get('row_numbers')),
                    'delta_target': (v.get('after') or {}).get('delta_target'),
                    'residue': (v.get('after') or {}).get('residue_exists'),
                    'listing_identical': v.get('listing_identical'),
                    'sensitivity': v.get('sensitivity_detected'),
                    'http_status': v.get('http_status')}
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
    saved = _env.save_evidence('r2_c08_probe_compare.json',
                               json.dumps(out, ensure_ascii=False, indent=1))
    print('[compare] A=%s B=%s' % (out['run_id_a'], out['run_id_b']))
    print('[compare] only_in_a=%s only_in_b=%s verdict_diff=%s'
          % (out['only_in_a'], out['only_in_b'], out['verdict_diff']))
    print('[compare] reading_diff=%s' % json.dumps(out['reading_diff'], ensure_ascii=False)[:300])
    print('[compare] 双跑一致 = %s' % out['identical'])
    print('[compare] 证据已落盘 %s' % rel(saved))
    return 0 if out['identical'] else 1


def main():
    ap = argparse.ArgumentParser(description='C-08 导入容错 / 导出零残留探针（V-10 / t11）')
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
