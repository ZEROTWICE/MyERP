"""coverage_drift.py — 报告型脚本的**判据层**（TL-03 雏形，E-03/t4 交付）。

**为什么需要它**：`scripts/route_inventory.py` 与 `harness/measure_coverage.py` 属**报告型**
（stdout 全是度量值、无判据语义 ⇒ 恒 `exit 0`，A-30 / T-09）——它们的退出码**永久不可作判据**。
判据必须落在**解析它们的产物**上：本脚本读 `coverage.json`（`measure_coverage.py --out`）与
可选的路由清单 stdout（`route_inventory.py`），按**锁死期望值**判「覆盖是否退化」，并给出失败出口。

**锁死期望值（来源：`08`/`06` + A-28/A-31 + `run_gates.EXPECTED`，全部为「不许退化」型）**

| id | 判据 | 期望 |
| --- | --- | --- |
| D-1 | `summary.rules_total` | `== 272`（路由总数，口径：`url_map.iter_rules()`；**ALLOY-IMPORT-01 有意更新**：271 → 273 → 272） |
| D-2 | `summary.method_level_non_get_total` | `>= 157`（非 GET 方法级；A-28 原记 `>= 155`；**ALLOY-IMPORT-01 有意更新**：155 → 157，与 `route_inventory` 的 `non-GET 110 → 112` 同源，+2 条新 POST 各 +1 方法级） |
| D-3 | `summary.writable_rules_non_get` | `== 156`（可写规则级；**ALLOY-IMPORT-01 有意更新**：153 → 155；**SEC-CSRF-01 有意更新**：155 → 156，`/auth/logout` 增 POST 方法） |
| D-4 | `summary.writable_literal_covered_by_all` | `>= 108`（字面量覆盖；**V-06/C-05 有意更新**：6 → 108） |
| D-5 | `summary.writable_any_covered_by_all` | `>= 116`（含动态覆盖；**V-06/C-05 有意更新**：14 → 116） |
| D-6 | `len(uncovered_writable)` | `<= 0`（无命中写端点；**V-06/C-05 有意更新**：101 → 0） |
| D-7 | `smoke_test_plan.static_reproduction_targets` / `_unresolved` | `== 148` / `== 9` |
| D-8 | `--routes-stdout`：`total rules` / `duplicate (method,path) registrations` | `== 273` / `== 0` |
| D-9 | 「GET+写」多方法面：`summary.multi_method_with_get_total` / `_uncovered` / `len(uncovered_multi_method_with_get)` | `== 44` / `== 38` / `== 38`（且 `M ≤ N`；**B17-14 新增**；**SEC-CSRF-01 有意更新**：43/37 → 44/38） |

**D-9 口径（B17-14：防「多方法 face 只打印不判」）**：`N` = 全量「GET+写」多方法规则（与
`scripts/route_inventory.py` 同名 face **同源同值**，现场 44）；`M` = 其中**未被任何探针 AST 命中**
的子集（现场 38），恒有 `M ≤ N`。两个口径**分开判、不得混算**：N 是规则面、M 是未命中子集面
（`uncovered_writable` 按构造排除「GET+写」⇒ 这 38 条原是漂移门禁盲区，D-6 永远看不见它们）。
`M` 还必须等于 `len(uncovered_multi_method_with_get)` —— 防 producer 自说自话（键写 38、列表给 0）。

⚠ **结算行的计数口径**：`判据 8/8 通过` 只统计**既有** D-1…D-8 —— `ci_gates.py` 第 11 步（blocking）
的 `expects` 指纹钉的就是这个子串（纯子串匹配），改计数会连带改 out-of-scope 的门禁指纹。
B17-14 追加的 D-9 状态以「另 D-9 多方法面判据 OK/FAIL」附在**同一行**；
**exit 码由全部判据（含 D-9）共同决定**（D-9 失败 ⇒ `failed` 非空 ⇒ `exit 1`）。

用法（仓库根目录）——**CI 里报告型脚本与判据层的正确接法**：

    # 1) 报告型：跑，但**忽略**其退出码（A-62 的 report-only 集）
    python -B test-reports-2026-10/harness/measure_coverage.py --out <run>/coverage.json
    python -B scripts/_sandbox_compat.py scripts/route_inventory.py > <run>/route_inventory.txt
    # 2) 判据层：只看这一条命令的退出码（blocking）——**必须显式传 --coverage**
    python -B test-reports-2026-10/harness/coverage_drift.py \
        --coverage <run>/coverage.json --routes-stdout <run>/route_inventory.txt

`--selftest` 对抗自检：用合成文档做 1 阳性 + 10 阴性注入，证明「漂移必被判失败」（不读活体文件 ⇒
不受并发写入影响）。`--json` 额外打印机读 JSON。

退出码：`0` = 全部判据通过；`1` = 任一判据失败（含**显式传入的**产物文件缺失 / 不可解析 / 自检不敏感）；
`2` = **用法错误：未提供 `--coverage`**（见下 N-1）。

---

## N-1 假红陷阱处置（V-16 报出，captain 裁定修法；**A-70「有意更新三步」记录**）

**问题**：`--coverage` 原缺省值 = **冻结锚点** `evidence/harness/coverage.json`（`29` §4 的声明锚点之一，
V-14 的 G1 判定其「unchanged」）。而 `LOCKED` 已被 V-06/C-05 按 A-70 从 `6/14/101` 有意更新为
`108/116/0`。两者语义互斥 ⇒ **任何人直跑本脚本（不带 `--coverage`）都会拿到 exit 1**，
极易被误读成「覆盖退化 / 回归」。这与 `regression_preflight.verify` 的假红同族。

* **触发项 ID**：**V-16 / N-1**（captain 于 2026-10-07 裁定：不要重生锚点 —— 重生会推翻 V-14 G1 的
  「5 条锚点未变」结论）。
* **旧行为**（实测原始 stdout 见 `test-reports-2026-10/.tmp/r2t14/n1_before.txt`）：
  `python -B test-reports-2026-10/harness/coverage_drift.py` ⇒ `覆盖=DEFAULT_COVERAGE(锚点)`、
  `D-4/D-5/D-6 = 6/14/101 vs LOCKED 108/116/0` ⇒ `判据 5/8 通过 => exit 1`。
* **新行为**：**缺 `--coverage` 即 fail loud** ⇒ 打印用法纠错 + 锚点留档读数（bytes/SHA256，**仅历史留档、
  不参与判据**）⇒ `exit 2`，并明写「**exit 2 = 未提供产物，不是回归**」。
* **（历史事实 —— 2026-10-07 该次裁定时）锚点与 `LOCKED` 均未改动**：当时 `evidence/harness/coverage.json`
  为 236893 B / `5E2C9D4315971B31C83AFD7833C310501199C34F61BFD868EF07A6AEEF7BF1F0`；`LOCKED` 三项仍 `108/116/0`。
  「不要重生锚点」的当时理由（重生会推翻 V-14 G1 的「5 条锚点未变」结论）依然成立，因此 B13-00 重基线
  **不是**抹掉旧读数，而是「归档旧字节 + append-only 登记 + 改登记读数」三件一起做 —— 见下一条。
* **B13-00 重基线（2026-10-08，用户授权的前置项；仍走 A-70 三步，触发项 ID：B13-00）**：
  冻结锚点已按 A-70 第 ① 步**在同一路径**重生成，覆盖读数由「旧值稿」`6/14/101` 变为 `108/116/0`
  （`LOCKED` 自 V-06/C-05 起一直是 `108/116/0`，本次**未改判据**，只让产物档与判据口径一致）。
  * 前值（「重基线前」）：**236893 B / `5E2C9D4315971B31C83AFD7833C310501199C34F61BFD868EF07A6AEEF7BF1F0`**
    （mtime `2026-10-06 22:25:07.937`）⇒ 字节级副本归档于
    `test-reports-2026-10/evidence/harness/_anchor-history/frozen-anchor-pre-b13-00.236893.5E2C9D43.json`，
    并在 append-only 登记册 `…/_anchor-history/coverage-anchor-history.json` 记为 entry no=1「重基线前」。
  * 后值（「重基线后」，= 下面的 `ANCHOR_READING`）：**244575 B /
    `F0D37A6C72C9029C60B4124DAC5993E1E65321448C943555381C15ECD6BDB42D`**（登记册 entry no=2）。
  * `LOCKED` 五项 / `UNCOVERED_WRITABLE_MAX` / `SMOKE_TARGETS` / `SMOKE_UNRESOLVED` / `ROUTE_RULES` /
    `ROUTE_DUP` **一字未改**（本次只重基线「产物档」，不动「判据锁」）。
  * A-110 教训复述：N-1 的根因是「同一文件既作冻结锚点、又被判据直接消费」。本次重基线后该文件与判据
    口径一致，但**纪律不变**：以后新增/变更覆盖口径时，先出新证据稿、再改锁值、并让旧值稿报红。
  * 命令（A-70 三步，仓库根目录，`<py>` = `F:\Miniconda\envs\wage\python.exe`）：
    ① `& '<py>' -B scripts/_sandbox_compat.py test-reports-2026-10/harness/measure_coverage.py
    --no-request-probes --out "<仓库根>/test-reports-2026-10/evidence/harness/coverage.json"`
    （`HARNESS_RUN_ID=b13-00-rebaseline-20261008`）⇒ **exit 0**；
    ② 同 ① 加 `--probes-exclude r2_c05_write_probe` ⇒ 读数**精确回落 `6/14/101`**（阴性对照）；
    ③ `& '<py>' -B test-reports-2026-10/harness/coverage_drift.py --coverage <新稿>` ⇒ **exit 0**，
    而喂「①的归档旧稿」或「②的回落稿」⇒ **exit 1**（D-4/D-5/D-6 三项 FAIL，判据 5/8）。
  * 回退：把归档副本复制回 `evidence/harness/coverage.json`，并把 `ANCHOR_READING` 与本块文字改回旧值；
    登记册**只允许再追加** entry no=3「回退」，不得删除既有 entry 或归档副本。
* **复算命令（三条）**：
  ① `python -B test-reports-2026-10/harness/coverage_drift.py` ⇒ **exit 2**（用法错误，不是回归）；
  ② `python -B test-reports-2026-10/harness/measure_coverage.py --no-request-probes --out <run>/coverage.json`
     && `python -B test-reports-2026-10/harness/coverage_drift.py --coverage <run>/coverage.json` ⇒ **exit 0**；
  ③ 同 ② 加 `--probes-exclude r2_c05_write_probe`（回落稿）⇒ `--coverage` 判据 ⇒ **exit 1**（判据仍敏感）。
* **回退（A-70 三步）**：① 把 `--coverage` 的 `default` 改回 `DEFAULT_COVERAGE`；② 删除本节的 exit 2 分支；
  ③ 重跑上述 ①②③ 复核「直跑 = exit 1（旧假红）」并在 `40` §4.5 与交付台账登记回退理由。

---
"""
import argparse
import hashlib
import json
import os
import re
import sys

# A-14：本机控制台默认 GBK；print 非 GBK 字符不得把「判据失败」与「崩溃」混为一谈。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors='replace')
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
REPORTS_ROOT = os.path.dirname(HERE)
#: 冻结锚点（`29` §4 声明锚点之一；**只作历史留档**，不参与判据 —— 见 docstring 的 N-1 节）
DEFAULT_COVERAGE = os.path.join(REPORTS_ROOT, 'evidence', 'harness', 'coverage.json')
#: 锚点登记读数（字节 + SHA256 大写；A-51 口径），仅用于缺参时的留档打印。
#: B13-00（2026-10-08）按 A-70 第 ① 步重基线冻结档：旧值 `236893 / 5E2C9D43…BF1F0` 已**字节归档**于
#: `evidence/harness/_anchor-history/`（副本 + 登记册 entry no=1「重基线前」）⇒ 新值见下行（entry no=2）。
ANCHOR_READING = (244575, 'F0D37A6C72C9029C60B4124DAC5993E1E65321448C943555381C15ECD6BDB42D')

#: 锁死期望值（单一存放点；改这里 = 改判据，必须与 08/06/A-28/A-31 同步）
#:
#: ── A-70「有意更新三步」记录（V-06 / C-05，2026-10-07）────────────────────────────
#: 触发项 ID：**V-06（C-05 写端点命中补强）** —— `measure_coverage.PROBES` 新增第 9 项
#:            `test-reports-2026-10/harness/r2_c05_write_probe.py`（冻结 21444 B / 426 行 /
#:            SHA256 E99CB54E6B73775E483115475A430AE3406A49F3F04A2EE77AE7DE8816ADB422）。
#: 旧值 → 新值：literal `>= 6` → `>= 108`；any `>= 14` → `>= 116`；uncovered `<= 101` → `<= 0`。
#: 命令（三条，仓库根目录，绝对路径解释器）：
#:   ① & 'F:\Miniconda\envs\wage\python.exe' -B test-reports-2026-10\harness\measure_coverage.py \
#:        --no-request-probes --out <run>\coverage.json
#:   ② 同 ① 加 `--probes-exclude r2_c05_write_probe` ⇒ **必须回落 6 / 14 / 101**（阴性对照）
#:   ③ & 'F:\Miniconda\envs\wage\python.exe' -B test-reports-2026-10\harness\coverage_drift.py \
#:        --coverage <run>\coverage.json [--routes-stdout <run>\route_inventory.txt]
#: 判据：① 的产物 ⇒ exit 0；②（回落稿）与任何「旧值稿」⇒ exit 1（说明判据真的会红）。
#: 回退：把本块三处期望值改回 6 / 14 / 101，并把 measure_coverage.PROBES 的第 9 项删除。
#: ── B13-00（2026-10-08）：**只重基线「产物档」**（冻结 coverage.json），本块 LOCKED / 路由锁一并未改；
#:    前值→新值与归档登记见 docstring 的 N-1 节「B13-00 重基线」条（`ANCHOR_READING` 同批更新）。
#:
#: ── A-70「有意更新三步」记录（ALLOY-IMPORT-01，2026-10-09）────────────────────────────────
#: 触发项 ID：**ALLOY-IMPORT-01（「合金钢辙叉计件工价标准 + 48页表格 BOM」导入功能接入）** ——
#:   新增 `app/utils/alloy_steel_price_converter.py`、`app/utils/alloy_steel_bom_converter.py`、
#:   `app/services/alloy_steel_import_service.py`，以及 2 个写端点
#:   `/process_prices/import_alloy`（`process.manage`）与 `/products/import_bom_alloy`（`product.import`）。
#: 旧值 → 新值：`rules_total` 271 → **273**（`route_inventory` 口径，+2 条 POST）；
#:            `writable_rules_non_get` 153 → **155**（+2 个新写端点）；
#:            `method_level_non_get_total`（`>=` 型）155 → **157**（方法级非 GET；现场实测 157 =
#:              旧锚点同口径 155 + 2 条新 POST；未放宽，只是把锁对齐到实测值）；
#:            `ROUTE_RULES` 271 → **273**（D-8 与 D-1 同源，必须同改）。
#: 命令（三条，仓库根目录，绝对路径解释器）：
#:   ① & 'F:\Miniconda\envs\wage\python.exe' -B scripts\route_inventory.py
#:        ⇒ 期望 `[routes] total rules=273` / `duplicate (method,path) registrations=0`
#:   ② & 'F:\Miniconda\envs\wage\python.exe' -B test-reports-2026-10\harness\measure_coverage.py
#:        --no-request-probes --out <run>\coverage.json
#:        ⇒ 期望 summary.rules_total=273 / writable_rules_non_get=155
#:   ③ & 'F:\Miniconda\envs\wage\python.exe' -B test-reports-2026-10\harness\coverage_drift.py
#:        --coverage <run>\coverage.json --routes-stdout <run>\route_inventory.txt
#:        ⇒ 期望 `判据 8/8 通过` / exit 0
#: 判据：②的产物 + ①的 stdout ⇒ ③ exit 0；任何「旧值稿」（coverage.json 写 271/153 或 stdout 写
#:   271）⇒ ③ exit 1（说明判据真的会红，未放宽）。
#: D-6 说明：`uncovered_writable` 通过 `scripts/functional_test.py` 新增的 18 条合金钢导入探针满足
#:   （两个新写端点均被字面量命中并**真调用**：工价先 dry_run 后正式导入 + 幂等复导；BOM 同）
#:   ⇒ 0 → 0，判据未放宽，只是新端点自带覆盖。
#: 同批有意更新（不在本文件，但同一触发项）：`run_gates.EXPECTED` 的 `properties_files` 23 → 26
#:   （新增 3 个被 `check_properties.py` 扫描的文件）、`functional_passed` 109 → 127（+18 条断言）、
#:   `routes_total_rules` 271 → 273 → 272、`routes_non_get` 110 → 112；`ci_gates.py` 第 688 / 701 / 715
#:   行的三处 `expects` 字符串同步。
#: 回退：本块四处期望值与 docstring 表 D-1/D-2/D-3/D-8、`synthetic_doc()`、`routes_ok`、自检例 CD-N3/N4/N5
#:   一并改回 271 / 155 / 153 / 271，并回退上列 `run_gates.EXPECTED` 四项与 `ci_gates.py` 三行，
#:   最后删除三份新模块与 2 个端点。冻结锚点 `evidence/harness/coverage.json` 不动（历史留档）。
#: ────────────────────────────────────────────────────────────────────────────────
LOCKED = {
    'rules_total': ('==', 272),
    'method_level_non_get_total': ('>=', 157),
    'writable_rules_non_get': ('==', 156),
    'writable_literal_covered_by_all': ('>=', 108),
    'writable_any_covered_by_all': ('>=', 116),
}
UNCOVERED_WRITABLE_MAX = 0
SMOKE_TARGETS = 148
SMOKE_UNRESOLVED = 9
ROUTE_RULES = 272
ROUTE_DUP = 0
#: B17-14：`N` = 全量「GET+写」多方法规则（== `scripts/route_inventory.py` 同名 face 现场读数）；
#: `M` = 其中未被任何探针 AST 命中的子集（== `len(uncovered_multi_method_with_get)`，恒 M ≤ N）。
#: 两口径分开判、不得混算；`uncovered_writable` 按构造排除 GET+写 ⇒ D-6 看不见这 38 条。
MULTI_METHOD_TOTAL = 44
MULTI_METHOD_UNCOVERED = 38


def _cmp(actual, op, expected):
    if actual is None:
        return False
    if op == '==':
        return actual == expected
    if op == '>=':
        return actual >= expected
    if op == '<=':
        return actual <= expected
    raise ValueError(op)


def evaluate(doc, routes_text=None):
    """对 coverage.json（+ 可选的路由清单 stdout）逐条判据；返回 checks 列表。"""
    checks = []

    def add(cid, judge, expected, actual, status):
        checks.append({'id': cid, 'judge': judge, 'expected': expected,
                       'actual': actual, 'status': status})

    summary = (doc or {}).get('summary') or {}
    for key, (op, expected) in LOCKED.items():
        actual = summary.get(key)
        add(f'D-{list(LOCKED).index(key) + 1}', f'summary.{key} {op} {expected}',
            f'{op} {expected}', actual,
            'passed' if _cmp(actual, op, expected) else 'failed')

    uncovered = (doc or {}).get('uncovered_writable')
    n_uncovered = len(uncovered) if isinstance(uncovered, list) else None
    add('D-6', f'len(uncovered_writable) <= {UNCOVERED_WRITABLE_MAX}',
        f'<= {UNCOVERED_WRITABLE_MAX}', n_uncovered,
        'passed' if isinstance(n_uncovered, int) and n_uncovered <= UNCOVERED_WRITABLE_MAX
        else 'failed')

    plan = (doc or {}).get('smoke_test_plan') or {}
    t = plan.get('static_reproduction_targets')
    u = plan.get('static_reproduction_unresolved')
    add('D-7', 'smoke_test_plan 静态复现 148 / 未解析 9',
        f'== {SMOKE_TARGETS} / == {SMOKE_UNRESOLVED}', f'{t} / {u}',
        'passed' if (t == SMOKE_TARGETS and u == SMOKE_UNRESOLVED) else 'failed')

    if routes_text is None:
        add('D-8', 'route_inventory stdout（未提供 --routes-stdout）', 'skipped', None, 'skipped')
    else:
        m_rules = re.search(r'\[routes\]\s*total rules=(\d+)', routes_text)
        m_dup = re.search(r'duplicate \(method,path\) registrations=(\d+)', routes_text)
        rules = int(m_rules.group(1)) if m_rules else None
        dup = int(m_dup.group(1)) if m_dup else None
        add('D-8', f'route_inventory: total rules == {ROUTE_RULES} 且 duplicate == {ROUTE_DUP}',
            f'== {ROUTE_RULES} / == {ROUTE_DUP}', f'{rules} / {dup}',
            'passed' if (rules == ROUTE_RULES and dup == ROUTE_DUP) else 'failed')

    # ---- D-9（B17-14）：「GET+写」多方法面 ----
    # N = 全量「GET+写」多方法规则（与 route_inventory 同名 face 同源）；M = 未命中子集（M ≤ N）。
    # 判据 = 两个计数键都存在且为 int、等于锁死值、M == len(列表)、M ≤ N —— 任一不符即失败。
    mm_total = summary.get('multi_method_with_get_total')
    mm_uncov = summary.get('multi_method_with_get_uncovered')
    mm_list = (doc or {}).get('uncovered_multi_method_with_get')
    mm_len = len(mm_list) if isinstance(mm_list, list) else None
    mm_ok = (isinstance(mm_total, int) and isinstance(mm_uncov, int)
             and mm_total == MULTI_METHOD_TOTAL and mm_uncov == MULTI_METHOD_UNCOVERED
             and mm_len == mm_uncov and mm_uncov <= mm_total)
    add('D-9', '多方法面：N(total) == %d 且 M(uncovered) == %d 且 M == len(列表)、M <= N'
        % (MULTI_METHOD_TOTAL, MULTI_METHOD_UNCOVERED),
        '== %d / == %d' % (MULTI_METHOD_TOTAL, MULTI_METHOD_UNCOVERED),
        'N=%s M=%s len(list)=%s' % (mm_total, mm_uncov, mm_len),
        'passed' if mm_ok else 'failed')
    return checks


def synthetic_doc():
    """自检用合成文档（**不读活体文件**，避免并发写入干扰阳性对照）。

    基线值 = V-06/C-05 有意更新（literal 108 / any 116 / uncovered 0）+ ALLOY-IMPORT-01 有意更新
    （rules_total 273 / method_level_non_get_total 157 → SEC-CSRF-01 后 158 / writable_rules_non_get
    155 → SEC-CSRF-01 后 156）+ B17-14 新增（多方法面 N 43 → SEC-CSRF-01 后 44 / M 37 → 38）后的实测值；
    阴性注入相对**该基线各降 1**，唯 `D-2`（`>= 157` 下限型）例外：降 1 仍在域内，故降至 156
    （`uncovered` 是 `<=` 型 ⇒ 0 → 1 即漂移）。
    """
    return {
        'summary': {
            'rules_total': 272, 'method_level_non_get_total': 158,
            'writable_rules_non_get': 156, 'writable_literal_covered_by_all': 108,
            'writable_any_covered_by_all': 116,
            # B17-14：D-9 的两把锁（N=44 全量 / M=38 未命中子集；SEC-CSRF-01 后读数）
            'multi_method_with_get_total': 44, 'multi_method_with_get_uncovered': 38,
        },
        'uncovered_writable': [],
        # B17-14：D-9 还要求 M == len(列表) ⇒ 合成列表必须正好 38 条
        'uncovered_multi_method_with_get': [{'rule': '/mm/%d' % i} for i in range(38)],
        'smoke_test_plan': {'static_reproduction_targets': 148,
                            'static_reproduction_unresolved': 9},
    }


def selftest():
    """1 阳性 + 10 阴性注入：漂移必须被判失败（门禁敏感性）。"""
    routes_ok = '[routes] total rules=273\nduplicate (method,path) registrations=0\n'
    results = []

    def case(cid, doc, routes, must_fail):
        checks = evaluate(doc, routes)
        failed = [c['id'] for c in checks if c['status'] == 'failed']
        got = bool(failed)
        results.append({'id': cid, 'must_fail': must_fail, 'got_fail': got,
                        'failed_ids': failed,
                        'status': 'passed' if got == must_fail else 'failed'})

    case('CD-P1 阳性对照：合成基线必须全过', synthetic_doc(), routes_ok, False)
    d = synthetic_doc(); d['summary']['writable_literal_covered_by_all'] -= 1   # 基线 -> 基线-1
    case('CD-N1 字面量覆盖 基线-1', d, routes_ok, True)
    d = synthetic_doc(); d['summary']['writable_any_covered_by_all'] -= 1       # 基线 -> 基线-1
    case('CD-N2 含动态覆盖 基线-1', d, routes_ok, True)
    # D-2 是 `>= 157` 下限型 ⇒ 阴性必须**跌破下限**才红：基线 158 降 1 得 157 仍在域内，
    # 故注入 156。（精确相等由 `check_doc_claims.PINNED.method_level_non_get_total` 另行钉死。）
    d = synthetic_doc(); d['summary']['method_level_non_get_total'] = 156
    case('CD-N3 非 GET 方法级 158→156（跌破 >= 157 下限）', d, routes_ok, True)
    d = synthetic_doc(); d['summary']['writable_rules_non_get'] = 155
    case('CD-N4 可写规则级 156→155', d, routes_ok, True)
    d = synthetic_doc(); d['summary']['rules_total'] = 271
    case('CD-N5 路由总数 273→272', d, routes_ok, True)
    d = synthetic_doc(); d['uncovered_writable'] = d['uncovered_writable'] + [{'rule': '/new'}]
    case('CD-N6 无命中写端点 0→1', d, routes_ok, True)
    d = synthetic_doc(); d['smoke_test_plan']['static_reproduction_targets'] = 147
    case('CD-N7 smoke 计划 148→147', d, routes_ok, True)
    case('CD-N8 路由清单 duplicate 0→1', synthetic_doc(),
         routes_ok.replace('registrations=0', 'registrations=1'), True)
    # ---- B17-14：D-9 两条阴性（t6 现场用的正是这两个变异体）----
    d = synthetic_doc(); d['summary']['multi_method_with_get_total'] = 99
    case('CD-N9 多方法全量 N 44→99', d, routes_ok, True)
    d = synthetic_doc(); d['summary']['multi_method_with_get_uncovered'] = 0   # 列表仍 38 条
    case('CD-N10 多方法未命中 M 38→0（列表仍 38）', d, routes_ok, True)

    for r in results:
        print(f"  [{'PASS' if r['status'] == 'passed' else 'FAIL'}] {r['id']}"
              f"{'  (判失败项: ' + ','.join(r['failed_ids']) + ')' if r['failed_ids'] else ''}")
    n = sum(1 for r in results if r['status'] == 'passed')
    all_ok = n == len(results)
    print(f'[coverage_drift] 自检结果 {n}/{len(results)} 通过'
          f" => {'敏感性 OK' if all_ok else '门禁不敏感'}")
    return 0 if all_ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(
        description='报告型脚本产物的判据层（E-03/TL-03）：解析 coverage.json / 路由清单出判据')
    ap.add_argument('--coverage', default=None,
                    help='【必填】coverage.json 路径（本次 run 的产物，例：--out <run>/coverage.json）。'
                         '缺参 ⇒ exit 2（用法错误，不是回归）；冻结锚点 %s 仅作历史留档'
                         % DEFAULT_COVERAGE)
    ap.add_argument('--routes-stdout', default=None,
                    help='route_inventory.py 的 stdout 落盘文件（判 D-8）')
    ap.add_argument('--selftest', action='store_true', help='对抗自检（1 阳性 + 10 阴性注入）')
    ap.add_argument('--json', action='store_true', help='额外打印机读 JSON')
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()

    # ---- N-1（V-16 报出）：缺 --coverage ⇒ fail loud（exit 2），不得静默用冻结锚点当输入 ----
    if args.coverage is None:
        print('[USAGE] 未提供 --coverage：本工具需要**一份本次 run 的被测产物**，例如')
        print('        python -B test-reports-2026-10/harness/measure_coverage.py '
              '--no-request-probes --out <run>/coverage.json')
        print('        python -B test-reports-2026-10/harness/coverage_drift.py '
              '--coverage <run>/coverage.json [--routes-stdout <run>/route_inventory.stdout.txt]')
        print('[USAGE] 冻结锚点仅作**历史留档**、不参与判据：它记录的是 V-06/C-05 有意更新**之前**的'
              ' 6/14/101，而 LOCKED 已按 A-70 更新为 108/116/0 ⇒ 直接套用必然假红（N-1）。')
        print('[USAGE] exit 2 = 未提供产物（用法错误），**不是覆盖退化 / 不是回归**。')
        if os.path.isfile(DEFAULT_COVERAGE):
            h = hashlib.sha256()
            with open(DEFAULT_COVERAGE, 'rb') as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b''):
                    h.update(chunk)
            got = (os.path.getsize(DEFAULT_COVERAGE), h.hexdigest().upper())
            print('[USAGE] 锚点留档读数：%s  bytes=%d sha256=%s（登记 %d / %s）匹配=%s'
                  % (DEFAULT_COVERAGE, got[0], got[1], ANCHOR_READING[0], ANCHOR_READING[1],
                     got == ANCHOR_READING))
        print('[e03] exit_code_semantics=' + json.dumps({
            'script': 'test-reports-2026-10/harness/coverage_drift.py',
            'class': '判据层（TL-03 雏形）—— 用法错误出口',
            'rule': 'no --coverage -> exit 2（用法错误，不是回归）; '
                    'explicit --coverage: all checks passed -> exit 0, any failed -> exit 1',
            'inputs': {'coverage': None, 'routes_stdout': args.routes_stdout},
            'n1_trigger': 'V-16 / N-1（锚点 vs LOCKED 语义互斥的假红陷阱处置，2026-10-07）',
            'code': 2,
        }, ensure_ascii=False))
        return 2

    reasons = []
    if not os.path.isfile(args.coverage):
        print(f'[FAIL] coverage.json 不存在：{args.coverage}')
        print(f'[coverage_drift] exit = 1  原因=[coverage.json 缺失]')
        return 1
    try:
        with open(args.coverage, encoding='utf-8') as fh:
            doc = json.load(fh)
    except (OSError, ValueError) as e:
        print(f'[FAIL] coverage.json 不可解析：{e.__class__.__name__}: {e}')
        print(f'[coverage_drift] exit = 1  原因=[coverage.json 不可解析]')
        return 1

    routes_text = None
    if args.routes_stdout:
        if not os.path.isfile(args.routes_stdout):
            print(f'[FAIL] --routes-stdout 不存在：{args.routes_stdout}')
            reasons.append('routes-stdout 缺失')
        else:
            with open(args.routes_stdout, encoding='utf-8', errors='replace') as fh:
                routes_text = fh.read()

    checks = evaluate(doc, routes_text)
    print(f'[coverage_drift] coverage={args.coverage}')
    if args.routes_stdout:
        print(f'[coverage_drift] routes_stdout={args.routes_stdout}')
    for c in checks:
        if c['status'] == 'skipped':
            print(f"  [SKIP] {c['id']} {c['judge']}")
            continue
        flag = 'OK  ' if c['status'] == 'passed' else 'FAIL'
        print(f"  [{flag}] {c['id']} {c['judge']}  实际={c['actual']}")
        if c['status'] == 'failed':
            reasons.append(f"{c['id']}({c['judge']} 实际={c['actual']})")

    failed = [c['id'] for c in checks if c['status'] == 'failed']
    code = 1 if (failed or reasons) else 0
    # ⚠ 计数口径：`判据 8/8 通过` 只统计**既有** D-1…D-8（ci_gates.py 第 11 步 blocking 的 expects 指纹
    #   钉的就是这个子串，纯子串匹配 ⇒ 改计数会连带改 out-of-scope 的门禁指纹）；B17-14 的 D-9
    #   显式附在同行，且 exit 由**全部**判据决定（见 docstring「D-9 口径」）。
    base = [c for c in checks if c['id'] != 'D-9']
    d9 = next((c for c in checks if c['id'] == 'D-9'), None)
    d9_tail = ('' if d9 is None
               else '；另 D-9 多方法面判据 ' + ('OK' if d9['status'] == 'passed' else 'FAIL'))
    print(f"[coverage_drift] 判据 {sum(1 for c in base if c['status'] == 'passed')}/{len(base)} 通过"
          f"{d9_tail}  => exit {code}  原因={reasons if reasons else '无（全绿）'}")
    print('[e03] exit_code_semantics=' + json.dumps({
        'script': 'test-reports-2026-10/harness/coverage_drift.py',
        'class': '真闸门（报告型产物的判据层，TL-03 雏形）',
        'rule': 'all checks passed -> exit 0; any failed -> exit 1',
        'inputs': {'failed_checks': failed, 'coverage': args.coverage,
                   'routes_stdout': args.routes_stdout},
        'code': code,
    }, ensure_ascii=False))
    if args.json:
        print(json.dumps({'checks': checks, 'exit_code': code, 'reasons': reasons},
                         ensure_ascii=False, indent=1))
    return code


if __name__ == '__main__':
    sys.exit(main())
