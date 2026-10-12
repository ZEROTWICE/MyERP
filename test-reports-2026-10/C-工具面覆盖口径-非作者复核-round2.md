# C · 工具面覆盖口径 —— 非作者复核 round 2（t15 复核件）

- **任务**：`t15`（kind=`review` round 2，attempt `05f8c3ca-f0b6-47fe-ad85-3a6ade471573`）非作者复核 **`t14`**（repair-round-2，attempt 3，作者 `impl-p1`）。
- **复核基准**：`test-reports-2026-10/C-工具面覆盖口径.md`（t6 交付件 · t14 工作区版）＋ 本队 t13 复核件 `test-reports-2026-10/C-工具面覆盖口径-非作者复核.md`。
- **C9 满足**：被复核件作者 = `impl-p1`（t6/t14），复核者 = `gov-assets`，**非同一作者**；本件不批准自身任何实现。
- **现场**：HEAD `9f28baa`（2026-10-12 04:34:29 +0000）；解释器 `/opt/wage-venv/bin/python`（3.11.2）；复核时点 2026-10-12 06:25–06:48 UTC。
- **真库只读**（硬约束②）：开工（06:25）与收工（06:48）各核一次，三值恒等 —— sha256 `34e48e7a21163db390eebda4f2030343f3609afedc65d8c6e909d6eb5a49177e` / `2531328 B` / mtime `2026-10-12 04:25:37.128430119 +0000`。全部请求型实验经副本库（工具自带 `make_app()`）。
- **被复核件指纹（复核者复算）**：`wc -l -c` = **264 行 / 29166 B**；sha256 = `3d22fd6b425bef5c5c673a20ebccf50cb639824a5437870ccab1da7f81d8defa`；可复算口径 `head -n -1` = **263 行 / 28566 B** / sha256 **`7d7e8dbe6ff3222ce4414f4881d58f6c0b361d4a06c250402b9e0551de950a13`** —— 与 t14 自述**逐位相符**。行尾 C7：`grep -c $'\r'` = **0**。
- **边界**：本件**只读复核 + 新建本件**。未改被复核件、未改 `scripts/**`、未改 `harness/**`、未动 `app/**`、未动 `docs/**`、未追改 `evidence/**`、未 `git add`/commit/push（工作区另有他成员暂存件，不碰）。

## §0 速览

**verdict = `pass`**（无 findings）。四条 acceptance 全部满足；t13 的两条 findings（F-01 / F-02）经**独立复算**判定 **resolved**；门禁 blocking 面全绿；**未发现任何为了让某步转绿而放宽的判据**。

| # | acceptance（任务书原文摘要） | 判定 |
| --- | --- | --- |
| 1 | G-19 是否**在既有工具内**做方法参数化 face（不得新起并行工具/新脚本另开判据），给 `文件:函数:行号` + `--help` 取证 | **passed** |
| 2 | G-19 判据实测：写端点 deny **阳性** + **阴性对照**，两条都要命令 + 值 | **passed** |
| 3 | G-21 口径实测：多方法规则计数与来源 + 与 `route_inventory.py` / `run_gates.py EXPECTED['routes_total_rules']` 钉值对照 + A-70 三步核查 | **passed** |
| 4 | 回归核对：`ci_gates --phase first` 的 `blocking 失败=无`（run 目录 + 读数）+ `permission_matrix` 步 checks 数与改动前对照 + 不得放宽任何 blocking 判据 | **passed** |

## §1 逐条 acceptance 判定（工具 + 口径 + 值）

### 1.1 验收项 1 —— G-19 载体在既有工具内、方法参数化【passed】

**证据 1（唯一性）**：`git ls-files | grep -i permission_matrix` ⇒ **仅 `scripts/permission_matrix.py`**（全仓唯一、受跟踪）。`git ls-files` 无第二个 permission_matrix 载体 ⇒ 未新起并行工具。任务书所写 `test-reports-2026-10/harness/permission_matrix.py` **不存在**（沿 t13 观察项 O-1，见 §4）。

**证据 2（方法轴，工作区帧逐行实读）**：

| 行号 | 内容 | 口径意义 |
| --- | --- | --- |
| `scripts/permission_matrix.py:448` | `def write_endpoints(app, guards, capability):` | 写端点面入口 |
| `:449` | docstring「**派生**该能力面的写端点（**不手抄路径表**）」 | 口径声明 |
| `:453` | `for rule in app.url_map.iter_rules():` | 从 `url_map` **派生** |
| `:456` | `methods = sorted(rule.methods - {'GET', 'HEAD', 'OPTIONS'})` | **方法轴参数化**（非 GET 即写面） |
| `:457-458` | `if not methods: continue` | 纯 GET 规则不入写面 |
| `:459-461` | 能力面匹配 ⇒ `out.append((str(rule), rule.endpoint, methods[0]))` | 带出 method |
| `:496` | `row = {actor: classify(c, url, method=method, data=data) …}` | **方法透传至判定函数** |
| `:518-519` | `if len(found) != spec['write_expect']:` ⇒ `'写端点数漂移: 现场 %d != 台账 %d'` | 模块级台账**上下漂移都红** |
| `:713` | `code = 1 if (anon_open or face_failures or write_failures or ir_failed) else 0` | 写面失败**计入退出码** |

**证据 3（`--help`，verify 命令直跑）**：usage 列出 `[--inject-write-module INJECT_WRITE_MODULE]`，说明逐字「注入回放（B17-13）：副本进程内移除该模块**首个写端点**的 `@require_capability` ⇒ 写面 deny 断言必须转红（不改生产代码）」⇒ 参数面在册、用法可复算。

**证据 4（角色集合规）**：`deny_roles_for()` 无手写角色名单 —— `:383 def deny_roles_for(capability):`、`:387 from app.permissions import ROLES as APP_ROLES, roles_for`、`:388 allow = set(roles_for(capability))`、`:389 return tuple(r for r, _label in APP_ROLES if r not in allow)`；页面面 `:406`、写端点面 `:490` 共用；`MODULE_FACE` 4 处 `deny_sample` 手写元组已删。

**判定**：需求「同一工具内参数化」满足；无并行工具、无新脚本另开判据。**passed**。

### 1.2 验收项 2 —— 阳性 + 阴性对照【passed】

**阳性（副本库，本轮复核者直跑）**：`/opt/wage-venv/bin/python -B scripts/permission_matrix.py --no-dump` ⇒ **exit 0**，四行：

```
[OK] 匿名可访问 = 0
[OK] C-06 四模块权限面 = 全绿（4 模块 allow + deny + 5xx=0）
[OK] C-06 四模块写端点面 = 全绿（21 写端点：逐端点 ≥1 allow + ≥1 deny，5xx/EXC=0）
[OK] 内联 role ≤ 白名单 = 全绿（扫描 16 条 == 白名单 16 条，按 (file, 文本) 出现次数逐一相等、双向无漏斗；行号漂移 9 处仅 WARN）
```

`e03 inputs`：`anon_open=0 / routes_tested=146 / c06_modules_failed=[] / c06_write_modules_failed=[] / code=0`。台账对拍 `equipment 9/9`、`purchase_orders 8/8`、`shipments 4/4`、`stock 0/0`（无写端点声明）= **21 写端点全绿**，逐端点 `allow≥1=admin,manager`（shipments 含 sales）、`deny≥1` = 派生 deny 集。

**阴性对照（本轮复核者独立复跑，同 t13 口径三轮）**：
`--no-dump --inject-write-module equipment` ⇒ **exit 1**，读数：
`[INJECT] … module=equipment endpoint=main.equipment_downtime stripped_layers=2`、
`[FAIL] POST /equipment/<int:id>/downtime   allow=admin,manager  deny=-  5xx/EXC=无`、
`[INJECT] 期望 = 该模块写面 deny 断言转红 ⇒ 实际 deny_ok=['hr','accountant','inspector','sales','user']  module_ok=False`、
`[INJECT] 靶向性 = 其它三模块写面仍全绿: ['purchase_orders', 'shipments', 'stock']`、
`[FAIL] C-06 四模块**写端点**面失败：equipment`。
撤注入复跑 ⇒ `RECOVERY_EXIT=0`，写面回 21 端点全绿（`§4` 第 1/2 条）。

**判定**：阳性（allow 侧）与阴性（deny 侧转红 + 靶向性 + 可恢复）两条均有命令与值 ⇒ 判据**非恒真**。**passed**。

### 1.3 验收项 3 —— G-21 计数口径与钉值对照【passed】

**计数与来源（本轮复核者直跑）**：
`/opt/wage-venv/bin/python -B scripts/route_inventory.py` ⇒
`[routes] total rules=273` / `[routes] duplicate (method,path) registrations=0` / `[routes] GET no-arg=104 GET with-arg=56 non-GET=112` / **`[multi] GET+写 多方法规则=44（判据由 harness/coverage_drift.py 消费本段计数与逐条列表；measure_coverage 的同名 face 是其中「未被任何探针命中」的子集）`**。

本轮 run 产物 `test-reports-2026-10/evidence/harness/ci-run-20261012-062509/coverage.json` 顶层实读：`multi_method_with_get_total = 44`、`multi_method_with_get_uncovered = 38`、`len(uncovered_multi_method_with_get) = 38`、`rules_total = 273`。

**判据层对照（关键：44/38 是钉值本身，不是自创口径）**：
`/opt/wage-venv/bin/python -B test-reports-2026-10/harness/coverage_drift.py --coverage test-reports-2026-10/evidence/harness/ci-run-20261012-062509/coverage.json` ⇒ **exit 0**，逐条：

```
[OK] D-1 summary.rules_total == 273                                 实际=273
[OK] D-2 summary.method_level_non_get_total >= 158                  实际=158
[OK] D-3 summary.writable_rules_non_get == 156                      实际=156
[OK] D-4 summary.writable_literal_covered_by_all >= 108             实际=110
[OK] D-5 summary.writable_any_covered_by_all >= 116                 实际=118
[OK] D-6 len(uncovered_writable) <= 0                               实际=0
[OK] D-7 smoke_test_plan 静态复现 149 / 未解析 9                    实际=149 / 9
[OK] D-9 多方法面：N(total) == 44 且 M(uncovered) == 38 且 M == len(列表)、M <= N   实际=N=44 M=38 len(list)=38
[coverage_drift] 判据 7/8 通过；另 D-9 多方法面判据 OK  => exit 0  原因=无（全绿）
```

⇒ 44/38 与 `coverage_drift.py:20` 的 **D-9 单元格**逐字相同。

**与 `run_gates.py EXPECTED` 钉值对照（verify 命令）**：`grep -n "routes_total_rules" test-reports-2026-10/harness/run_gates.py` ⇒ `:50 'routes_total_rules': 273,`、`:128 'routes_total_rules': r'total rules=(\d+)',` ⇒ 与现场 `total rules=273` 一致。**量纲警示复核成立**：`273`（全部规则数）≠ `44`（GET+写多方法规则）≠ `38`（其中未被探针命中）≠ `check_doc_claims.py:123` 的 `non_get_uncovered_method_level=40`（方法级非 GET 未命中），**四者不得互替**。

**A-70 三步核查**：t14 本轮**未改任何判据/钉值/期望值** —— `git diff --numstat` 对 `test-reports-2026-10/harness/coverage_drift.py`、`test-reports-2026-10/harness/run_gates.py`、`test-reports-2026-10/harness/ci_gates.py` 三处**全空**；D-9 单元格自带演进链留档（SEC-CSRF-01 `43/37→44/38`；`e057e81` 删 `/auth/register` `44/38→43/37`；B18-Q1 增 `/auth/change-password` `43/37→44/38`）⇒ 不存在「未走 A-70 就改钉值」的情形，故本项不适用 A-70 第①②③步（无改值对象）。

**任务书「37 条」为陈旧值**：`37` = `70-第2轮收口与阶段C移交.md` 时点（RL-01 帧）读数，已被 `44/38` 取代；被复核件 §2.1 以现场读数分类并对账锚点链、**未追改历史件** ⇒ 处理正确。

**被复核件 §2.2 数字复核（复核者复算，与 t14 无关地独立跑其内嵌脚本）**：§4 第 6 条脚本去缩进后 `python -B` ⇒ **exit 0，输出 28 行**，与 §2.2 逐条相符 —— ②读 4 条全 `adds=0 commits=0`（`view_audit_logs :2033-2069` / `manage_bonus_penalties :1649-1755` / `salary_calculation :1896-2032` / `advanced_search :3155-3263`）；③写 24 条全 `gate=True`（`/assembly` 除外按 §2.2③ 单列，其 `gate=True` 亦真）；`commits` 分布 = **17 条 `commits=1` + 7 条 `commits=2`** ⇒ 与 §2.2③「22 表单条中 15 条 commits=1、7 条 commits=2」（+`/tasks` 与 `/assembly` 两条各 `commits=1`）**逐数相符**。§4 第 8 条脚本复跑：`manage_tasks def块 3350-3537: adds=2 commits=1`、换 `FUNC=consumable_inbound` ⇒ `11374-11444: adds=2 commits=1`，与 §2.2③ 两行逐字一致。

**判定**：计数、来源、钉值对照、A-70 核查四项齐全。**passed**。

### 1.4 验收项 4 —— 回归核对【passed】

**本轮复核者直跑**（run 目录 `test-reports-2026-10/evidence/harness/ci-run-20261012-062509/`，console `ci_gates_first.console.txt`）：

```
[ci_gates] steps=20 blocking 失败 = 无
[ci_gates] report-only 失败 = ['evidence_hash']
[ci_gates] 注入未生效 = 无
[ci_gates] 仓库根两 JSON 未被触碰 = True（A-11）
[ci_gates] gaps: A-63-STEP2-BUILD-GATE = blocked（不计入通过数）
[ci_gates] exit = 2  phase=first
exit_code_semantics: {"code": 2, "rule": "0 = 全部 blocking 通过; 1 = 有 blocking 失败（或仓库根 JSON 被写 / 注入未生效）; 2 = 仅 report-only 失败",
                      "inputs": {"blocking_failed": [], "report_only_failed": ["evidence_hash"], "root_json_untouched": true, "injection_ineffective": []}}
```

按本轮判据「**blocking 失败 = 无**」⇒ **绿**。`exit=2` 的唯一来源是**先在性** report-only `evidence_hash`。

**`permission_matrix` 步 checks 数与改动前对照（不得放宽判据）**：

| 帧 | run | 时点 | permission_matrix | 备注 |
| --- | --- | --- | --- | --- |
| 改动前基线（t10 轮） | `ci-run-20261012-053155` | 05:31:55 | `group=blocking exit=0 checks 3/3` | 早于 t6 的 05:44 改动 |
| t6 自测 | `ci-run-20261012-054655` | 05:47 | `exit=0 checks 3/3` | — |
| t14 自测 | `ci-run-20261012-062243` | 06:22 | `exit=0 checks 3/3` | — |
| **本件复核（独立）** | **`ci-run-20261012-062509`** | **06:25** | **`group=blocking exit=0 checks 3/3`** | 与基线**逐字相同** |

同轮 `check_doc_claims group=blocking exit=0 checks 5/5`（本轮另以 `--coverage <本 run>/coverage.json` 直跑该脚本：`29/29 相等` / `文档：扫描 5 份、带口径表 1 份` / `lock：33 条钉版 / 环境匹配 33 条 / exception 0 条` / `RESULT: OK（violations=0）` / **exit 0**）。

**判据放宽核查（逐处实证，非「未发现问题」）**：
- `test-reports-2026-10/harness/ci_gates.py`：`git diff --numstat` **空** ⇒ needle / 步骤表 / 期望值未动。
- `test-reports-2026-10/harness/run_gates.py`：**空** ⇒ `EXPECTED['routes_total_rules']=273` 等钉值未动。
- `test-reports-2026-10/harness/coverage_drift.py`：**空** ⇒ D-1…D-9 判据未动。
- `scripts/permission_matrix.py`：`28 18`（**= t6 的 deny 派生化，与 t13 复核时逐字同值**；见 §3 归属核验）⇒ 写面判据仍「逐端点 ≥1 allow + ≥1 deny + 无 5xx/EXC」+ 模块级 `write_expect` 台账，**未放宽**。
- `scripts/check_doc_claims.py`：`3 2`（**上级 A-70 重基线**，见 §2.2）——非 t14 改动，且走完 A-70 三步。
- `app/**`、`docs/**`、`evidence/**`：本件未动；被复核件作者 t14 亦未动（其自述 + 本件核验一致）。

**`evidence_hash`（report-only）明细**：`evidence_hash.gate.json` ⇒ `verdict=violation`、`counts` = `baseline_files 1433 / current_files 2702 / modified 2 / deleted 0 / added 1269`，两条违规 = `harness/b17-verify/probe_permission_matrix.txt` 与 `harness/b17-verify/probe_smoke_test.txt` —— 与 t2/t4/t6/t13 各轮**同一对先在性违规**（根因 = `measure_coverage.py:254` 裸 `open(ev,'w')` 原地覆写基线成员；修复已在另一线 `_env.save_evidence()`）。**不折算 pass**，状态 `blocked`，解除条件 = 按新 `run_id` 落盘或 A-70 重基线 `artifact_hashes.json`（`--freeze` 只追加）。

**判定**：`blocking 失败=无` 满足、checks 数与改动前一致、逐处放宽核查均有 `git diff` 实证。**passed**。

## §2 t13 findings 关闭判定（round 1 → round 2）

### 2.1 F-01（medium）`consumable_inbound` 写侧数字不可复现 → **resolved**

- **原 finding**：`C-工具面覆盖口径.md:108` 记「`consumable_inbound` adds=16/commits=12」，实测不可复现（块内 `add(`=2、`commit(`=1，全文无 adds=16 的函数）。
- **复核者独立复算（工作区帧，本件直跑）**：§4 第 8 条脚本换 `FUNC=consumable_inbound` ⇒ **`consumable_inbound def块 11374-11444: adds=2 commits=1`**，exit 0；§4 第 6 条全量脚本同一端点同值。逐行佐证：`db.session.add(` 在 `:11406`、`:11429`；`db.session.commit(` 在 `:11431`。
- **交付件现状**（`:134`）：已改为「`consumable_inbound` `:11374-11444` adds=2/commits=1（**t14 订正**：旧记「consumable_inbound adds=16/commits=12」为误值，现场实测 2/1，复算命令同 §4 第 6 条）」⇒ **值已订正、误值留档、复算命令在册**（符合硬约束⑥证据三要素）。
- **判定**：**resolved**。

### 2.2 F-02（low）§1.1 表行号实为 HEAD（改动前）帧 → **resolved（且扩至更严）**

- **复核者逐条实证（两帧各自 `grep -n` 实测，非算术推算）**：

| 锚点 | HEAD 帧 | 工作区帧 | 交付件 §1.1 声明 | 核验 |
| --- | --- | --- | --- | --- |
| `def write_endpoints` | `:440` | `:448` | `:448`（帧对照 `:440`，Δ+8） | ✅ |
| `def run_write_face` | `:469` | `:477` | `:477`（`:469`，Δ+8） | ✅ |
| `写端点数漂移` 消息 | `:509` | `:519` | `:518-519`（`:509`，Δ+10） | ✅ |
| `def print_write_face` | `:527` | `:537` | `:537`（`:527`，Δ+10） | ✅ |
| 注入前 `write_found =` | `:587` | `:597` | `:597`（`:587`，Δ+10） | ✅ |
| `write_failures = [` / `print_write_face(write_face` | `:670` / `:671` | `:680` / `:681` | `:680-681`（`:670`/`:671`，Δ+10） | ✅ |
| `write_summary` | `:691` | `:701` | `:701`（`:691`，Δ+10） | ✅ |
| 退出码 `code = 1 if (anon_open or face_failures …)` | `:703` | `:713` | `:713`（`:703`，Δ+10） | ✅ |
| `if write_failures:` / `[FAIL] … 写端点…` | `:712` / `:713` | `:722` / `:723` | `:722-723`（`:712`/`:713`，Δ+10） | ✅ |
| `--inject-write-module`（argparse） | `:759` | `:769` | `:769`（`:759`，Δ+10） | ✅ |
| `inject_write_module=args.…` | `:765` | `:775` | `:775`（`:765`，Δ+10） | ✅ |

- **提交基线声明核验**：交付件 `:12` 称「该文件的提交基线为 `64d48c9`，`git diff --stat 64d48c9 9f28baa -- scripts/permission_matrix.py` 输出为空」⇒ 复核者实跑：**输出为空**，✅；`git log --oneline -3 -- scripts/permission_matrix.py` ⇒ `64d48c9` / `3262aa4` / `5d1dcb4`，与声明一致。
- **额外收益（超出原 finding 要求）**：t14 另订正了两处同类帧错 —— §2.2② `advanced_search` `:3150-3258`（HEAD 帧）→ **`:3155-3263`**（工作区帧，实测相符 ✅）；§2.2③ `assembly` `:36-71`（只到函数体末行）→ **`:36-76`**（`def` 至下一顶层 `def`，实测相符 ✅）。§2.2③ 的 `/tasks` 由 `2/2` 订正为 **`adds=2/commits=1`**（原作者将注释行 `:3496` 误计；复核者实跑 §4 第 8 条脚本得同值 ✅）。
- **判定**：**resolved**，且帧口径由「单点行号」升级为「双帧对照表 + 复算命令」= 更严。

### 2.3 承 t13 的 A-70 链条核验（`routes_py_lines` 12806 → 12825）

- **① 旧值留档**：`scripts/check_doc_claims.py` 的 `git diff` = **`3 2`**，diff 体逐字含 `'routes_py_lines': (12806, …)` 作为被替换行（旧值在同处注释与 `B18-登记.md` §B18-C-07 留档，不删）。
- **③ 改值 + 复跑绿 + 登记**：`test-reports-2026-10/B18-登记.md:860` `## §B18-C-07 A-70 重基线：routes_py_lines 12806 → 12825（2026-10-12，C 批 t5 的直接后果）`，其 §A 明载旧值落点两处（`check_doc_claims.py:158` 与 `52-V13-TL050607-工具链收尾.md:50`）、漂移触发源（C 批 t5 净 +19 行、`git diff --cached --ignore-cr-at-eol --numstat -- app/main/routes.py` = `51 32`）、源值独立复算（`splitlines()` = `12825`，bytes `557036`）。复核者实跑：`wc -l app/main/routes.py` = **12825**、HEAD 帧 `git show 9f28baa:app/main/routes.py | wc -l` = **12806** ✅。
- **② 阴性对照（先转红，给出实测读数）**：t14 轮 06:07 的 run `ci-run-20261012-060742` 实测 `check_doc_claims` 步 **`checks 1/5`、exit=1**，唯一 violation = `[VIOLATION] 口径源漂移：routes_py_lines 钉值 12806 ≠ 源值 12825（源：app/main/routes.py splitlines() 行数）` ⇒ **转红读数在册**（被复核件 §3.3 全文引用，且 §1.5 保留该早期读数、不追改）。复核者另独立复现「裸跑 vs 带参」的差异：`scripts/check_doc_claims.py --coverage <本 run>/coverage.json` ⇒ `29/29 相等 / RESULT: OK（violations=0）` exit 0，即带参形态绿。
- **判定**：该重基线**走完 A-70 三步**，且**不在 t14 的 in-scope**（`scripts/check_doc_claims.py` 明列 Out of scope）；被复核件只记录读数、未参与改值 ⇒ 无越界。

## §3 `scripts/permission_matrix.py` 改动归属核验（防「借改判据转绿」）

- 工作区 `git diff --numstat -- scripts/permission_matrix.py` = **`28 18`**；完整 diff 逐 hunk 审阅后确认**全部**为 G-19 deny 派生化：`MODULE_FACE` 4 处 `deny_sample` 删除（hunk `@@ -70,24 +70,21 @@`）、新增 `deny_roles_for()`（`@@ -383,12 +380,22 @@`）、页面面 `deny = [r for r in deny_roles …]`（`@@ -403,7 +411,7 @@`）、模块级 `deny_any`（`@@ -415,7 +423,7 @@`）、落盘键 `'deny_sample': list(deny_roles)`（`@@ -430,7 +438,7 @@`）、写面 5 处同构替换（`@@ -470,14 +478,16 @@` … `@@ -518,7 +528,7 @@`）。**无任何一处触碰判据强度、期望值、白名单集合或退出码逻辑**。
- 该 diff 与 t13 复核时读数**逐字同值（`28 18`）** ⇒ t14 本轮**未再改该工具**，与 t14 自述一致。
- `§3.1` 声明「`scripts/check_doc_claims.py` PINNED 与 `harness/ci_gates.py` needle **未触碰**（改动仅 `scripts/permission_matrix.py` + 本件）」—— 复核：`harness/ci_gates.py` diff **空** ✅；`scripts/check_doc_claims.py` 的 `3 2` 为**上级** A-70 重基线（§2.3），非本任务改动，且被复核件 §1.5/§3.3 已如实标注为「上级已走 A-70 三步」✅。

## §4 观察项（非 findings：均不改任何值/判据/计数，故不构成 needs_revision）

- **O-1（承 t13，仍未闭合）**：本队 `t13` / `t15` 两轮任务书的 acceptance 均把工具路径写作 `test-reports-2026-10/harness/permission_matrix.py` —— 该路径**不存在**（`git ls-files` 无、`ls` 无）。真实唯一载体 = `scripts/permission_matrix.py`（779 行 / 45805 B / sha256 `73c329f8647883c33de13676baac6c5c78790931e6ca51f19c2f3ed8e794e4f7`）。建议在台账/任务书模板中订正，否则后续复核会按错路径空跑（本轮已按真实路径复核，未空跑）。
- **O-2（承 t13，仍未闭合）**：`test-reports-2026-10/harness/b17_governance_contract.py:723-724` 仍断言 `multi_method_with_get_total == 43` / `_uncovered == 37`（B17 期值），已被 `coverage_drift.py:20` D-9 的 `44/38` 取代。该契约**不在门禁链**（t2 已证 `ci_gates.py`/`run_gates.py`/`scripts/` 对其零引用），故无活影响；与 t2 登记的 B17-11 同族，建议并案处置。
- **O-3（本轮新发现，仅一处来源说明措辞）**：被复核件 `:42` 注记「t14 复跑……唯一差别是第 4 行末段**随 t16（另一线）改动扩写**」。复核实证：该末段（`，按 (file, 文本) 出现次数逐一相等、双向无漏斗；行号漂移 9 处仅 WARN`）**在 HEAD `9f28baa` 中即已存在**（`git show HEAD:scripts/permission_matrix.py | grep -c '双向无漏斗'` = **2**），且可追至提交 **`64d48c9`（2026-10-10 13:49:43，早于本批开工 2026-10-12 04:25：43）** —— 即**不在本批内发生**；该文件在工作区的**唯一** diff（`28 18`）不含此行（§3）⇒ 该「差别」的真实成因应是 t6 §1.2 原文**引述截断**，而非任何并发改动。建议改写为「该末段在 HEAD 提交基线 `64d48c9` 即已存在；t6 §1.2 原引用为节引」。**未按 finding 计**：该句只涉来源说明，不改任何读数/判据/计数，且被引用正文（`:50`）已按现场全文照录、正确。
- **O-4（沿 t6/t13 口径）**：任务书 acceptance 中的「**37 条**」为 `70-` 文档时点陈旧值；被复核件 §2.1 已按现场 `44/38` 分类并对账锚点链、未追改历史件 ⇒ 不需纠正文，但后续任务书宜直接写「与现场 `route_inventory` 读数对齐」。

## §5 复跑命令（本件全部读数可复算）

1. `/opt/wage-venv/bin/python -B scripts/permission_matrix.py --no-dump`（阳性：写面 21 端点全绿，**exit 0**）
2. 同上 + `--inject-write-module equipment`（阴性：`[FAIL] … deny=-`、靶向性其余三模块仍绿，**exit 1**）；再不带注入复跑 ⇒ **exit 0**
3. `/opt/wage-venv/bin/python -B scripts/permission_matrix.py --help`（`--inject-write-module` 在册）
4. `/opt/wage-venv/bin/python -B scripts/route_inventory.py | grep -E '^\[routes\]|^\[multi\]'`（`total rules=273` / `[multi]=44`）
5. `grep -n "routes_total_rules" test-reports-2026-10/harness/run_gates.py`（`:50` = `273`）
6. `/opt/wage-venv/bin/python -B test-reports-2026-10/harness/coverage_drift.py --coverage test-reports-2026-10/evidence/harness/ci-run-20261012-062509/coverage.json`（D-9 `N=44 M=38 len(list)=38`，**exit 0**）
7. `/opt/wage-venv/bin/python -B test-reports-2026-10/harness/ci_gates.py --phase first`（**blocking 失败=无**；`permission_matrix exit=0 checks 3/3`、`check_doc_claims exit=0 checks 5/5`；exit=2 仅因 report-only `evidence_hash`）
8. `/opt/wage-venv/bin/python -B scripts/check_doc_claims.py --coverage test-reports-2026-10/evidence/harness/ci-run-20261012-062509/coverage.json`（`29/29 相等` / `RESULT: OK（violations=0）` / **exit 0**）
9. 被复核件 §4 第 6 / 第 8 条内嵌脚本（先 `sed 's/^   //'` 去列表缩进，去首行命令与末行 `PYEOF`）⇒ **exit 0**；第 6 条输出 **28 行**与 §2.2 逐条一致，第 8 条打印 `manage_tasks def块 3350-3537: adds=2 commits=1`
10. 帧对照（两帧均 `grep -n` 实测）：工作区 `grep -n 'def write_endpoints\|def run_write_face\|def print_write_face\|写端点数漂移\|write_found =\|write_failures = \[\|write_summary\|anon_open or face_failures\|--inject-write-module\|inject_write_module=args\|def deny_roles_for' scripts/permission_matrix.py`；HEAD 帧把路径换成 `<(git show 9f28baa:scripts/permission_matrix.py)`
11. `sha256sum app.db && stat -c '%s %y' app.db`（真库三值；开工/收工恒等）
12. `git diff --numstat -- scripts/permission_matrix.py scripts/check_doc_claims.py test-reports-2026-10/harness/ci_gates.py test-reports-2026-10/harness/run_gates.py test-reports-2026-10/harness/coverage_drift.py`（`28 18` / `3 2` / 空 / 空 / 空）
13. 被复核件指纹：`wc -l -c test-reports-2026-10/C-工具面覆盖口径.md` ⇒ `264 29166`；`head -n -1 … | wc -l && … | wc -c && … | sha256sum` ⇒ `263` / `28566` / `7d7e8dbe6ff3222ce4414f4881d58f6c0b361d4a06c250402b9e0551de950a13`；`grep -c $'\r' …` ⇒ `0`

## §6 本件指纹

- 本件为 **新建件**（append-only：未覆盖/未改写任何既有文件）。
- 复核结论：**verdict = pass**，0 findings；t13 的 F-01 / F-02 均 **resolved**；4 条 acceptance 全 **passed**。
- **不折算 pass 的登记项（沿被复核件 §3.2 / §3.3，本件不改其状态）**：`evidence_hash`（report-only）= **blocked**（先在性、非本任务引入），解除条件 = 新 `run_id` 目录落盘 或 A-70 重基线 `artifact_hashes.json`（`--freeze` 只追加）；G-21 的 24 条留档待决 = **不折算 pass**，解除条件见被复核件 §2.3 的分批三步。
- 本件共 **219 行**（末行即本行）。**自指不可行**：任何对末行的改写都会同时改变全量 `wc -c`/`sha256`，故此处的全量值会自相矛盾 —— 一律以 **`head -n -1` 口径**为准（末行不参与），该口径在本次两次末行改正中**恒为**：**218 行 / 26786 B**、SHA256 = **`2F4877C4EDE00B5B7B8275147D6853ACBFD89A5B349992F189651F15624FE281`**。复算：`head -n -1 test-reports-2026-10/C-工具面覆盖口径-非作者复核-round2.md | wc -l && … | wc -c && … | sha256sum`。行尾 C7：`grep -c $'\r'` = **0**；`git diff --no-index --numstat [--ignore-cr-at-eol] /dev/null <本件>` 两种口径**同为 `219 0`**。
