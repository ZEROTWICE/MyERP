# C-独立验证（round 2）—— 阶段C 收口态复验（非作者）

- 验证者：`verify-c`（**非作者**；round 1 见 `test-reports-2026-10/C-独立验证.md`）
- 任务：`t17`（verification round 2）；attempt `823584ee-a91b-48a4-bc22-02dad349c659`
- 时点：2026-10-12 06:58–07:05 UTC；`HEAD = 9f28baa`
- 判据（本轮，按 captain 修订后契约）：`ci_gates.py --phase first` ⇒ **`steps=20` 且 `blocking 失败=无`**；report-only 红**逐条**给「工具 + 口径 + 值」并登记 `blocked`（**不要求** `exit=0`）
- 本轮工作范围：**只新建本件**；`app/**`、`scripts/**`、`test-reports-2026-10/harness/**`、`docs/**`、`evidence/**` 一律不改（发现问题只登记）
- 结论：**blocking 口径 PASS**；`exit=2`（唯一红 = 先在性 report-only `evidence_hash`，本轮未变）⇒ 计入 §4.3-O1 仍留档；**禁写「在册缺陷清零」**

---

## 1. 命令 / 口径 / 值

### 1.1 `ci_gates.py --phase first`（本轮重跑）

- **命令**：`/opt/wage-venv/bin/python -B test-reports-2026-10/harness/ci_gates.py --phase first`
- **口径**：`steps=20`（blocking 16 + report-only 4）；`blocking_failed` 为空 ⇒ 判据满足；`exit` 语义由脚本自述（见下）；report-only 红单列归因，不折算 pass。
- **值**（工具 + 口径 + 值三段式）：
  - run 产物目录 `test-reports-2026-10/evidence/harness/ci-run-20261012-065809/`：`ci_gates_first.console.txt` 46922 B（06:59:20）、`coverage.json` 246692 B（06:59:07）、`evidence_hash.gate.json` 297549 B（06:59:09）、`gates.json` 15376 B（06:58:34）、`negative_matrix.json` 32338 B（06:59:20）、`chain_count_consistency.json` 7980 B、`evidence_whitelist.registered.json` 1207 B、`http_contract.json` 1965 B、`route_inventory.stdout.txt` 13903 B、`evidence_journal.jsonl` 373 B
  - `[ci_gates] run_id=run-20261012-065809 phase=first interpreter=/opt/wage-venv/bin/python steps=20`
  - `exit_code_semantics = {"code": 2, "rule": "0 = 全部 blocking 通过; 1 = 有 blocking 失败（或仓库根 JSON 被写 / 注入未生效）; 2 = 仅 report-only 失败", "inputs": {"blocking_failed": [], "report_only_failed": ["evidence_hash"], "root_json_untouched": true, "injection_ineffective": []}}`
  - ⇒ **`blocking 失败 = 无`（判据 PASS）**；`exit = 2`（仅 report-only）；`root_json_untouched = true`；`注入未生效 = 无`

**20 步逐条（id / group / 结果）**：

| # | step | group | 结果 |
| --- | --- | --- | --- |
| 1 | `check_templates` | blocking | passed |
| 2 | `check_migration_heads` | blocking | passed |
| 3 | `check_table_parity` | blocking | passed |
| 4 | `check_properties` | blocking | passed |
| 5 | `check_db_bootstrap` | blocking | passed |
| 6 | `run_gates` | blocking | passed（内部读数见 §2.3） |
| 7 | `functional_test` | blocking | passed |
| 8 | `permission_matrix` | blocking | passed |
| 9 | `smoke_test` | report-only | passed |
| 10 | `route_inventory` | report-only | passed |
| 11 | `measure_coverage` | report-only | passed |
| 12 | `coverage_drift` | blocking | passed |
| 13 | `check_notification_triggers` | blocking | passed |
| 14 | `check_model_refs` | blocking | passed |
| 15 | `check_http_contract` | blocking | passed |
| 16 | `evidence_hash` | report-only | **failed**（§2.1） |
| 17 | `chain_count_consistency` | blocking | passed |
| 18 | `negative_matrix` | blocking | passed |
| 19 | `check_is_archived_policy` | blocking | passed |
| 20 | `check_doc_claims` | blocking | passed |

- 计数核对：blocking 16 + report-only 4 = **20**（与 `steps=20` 一致）；blocking 中 failed 数 = **0**。
- `coverage_drift` 步（blocking）本轮 D-1…D-9 逐条：[OK] `rules_total == 273`（实际 273）、`method_level_non_get_total >= 158`（158）、`writable_rules_non_get == 156`（156）、`writable_literal_covered_by_all >= 108`（110）、`writable_any_covered_by_all >= 116`（118）、`len(uncovered_writable) <= 0`（0）、`smoke_test_plan` 静态复现 149 / 未解析 9、`route_inventory` total 273 且 duplicate 0、D-9 多方法面 `N=44 / M=38 / len(list)=38` ⇒ `判据 8/8 通过；另 D-9 多方法面判据 OK => exit 0`。
- 挂账（不折算 pass）：`A-63-STEP2-BUILD-GATE` = `blocked（不计入通过数）`；解除条件（原文照录）=「A-63 第二步：解注释 `Jenkinsfile:112/122` + GH 去 `continue-on-error` + `build-and-push` 加 `needs: gate`，再观测 1 轮全绿」；owner = captain；本环境无 `docker` ⇒ 不可测。

### 1.2 `check_doc_claims.py --selftest`

- **命令**：`/opt/wage-venv/bin/python -B scripts/check_doc_claims.py --selftest`
- **口径**：自检夹具全绿 = `26/26`，`exit 0`。
- **值**：`[check_doc_claims] 自检 26/26 通过`，`exit 0`（夹具目录 `test-reports-2026-10/.tmp/r2t13-selftest`）。逐条含 `DC-P1`、`DC-N1…N9`（含 `DC-N9[real_db_sha256]`/`[real_db_bytes]`/`[ci_gates_steps]` 等 9 个口径键阴性对照）、`DC-L1…L5`（lock 面）——**全部 `[PASS]`，无 SKIP**。

### 1.3 `check_doc_claims.py --coverage <本轮 run 产物>`

- **命令**：`/opt/wage-venv/bin/python -B scripts/check_doc_claims.py --coverage test-reports-2026-10/evidence/harness/ci-run-20261012-065809/coverage.json`
- **口径**：文档口径值 vs 权威源（本轮 coverage 产物）逐键相等；lock 面 `33 条钉版 / 环境匹配 33 条 / exception 0 条`；`RESULT: OK（violations=0）` ⇒ `exit 0`。
- **值**：`钉常量 vs 权威源：29/29 相等`；`文档：扫描 5 份、带口径表 1 份`；`lock：33 条钉版 / 环境匹配 33 条 / exception 0 条`；`[WARN] 声明表环境标记在本平台为假，不进 lock：pywin32`；`RESULT: OK（violations=0）`；**exit 0**。
- 对照（不折算 pass，`not_counted_as_passed`）：**裸跑**（不带 `--coverage`，默认源 `test-reports-2026-10/evidence/harness/coverage.json` 已不在盘）本轮复测 = `钉常量 vs 权威源：20/29 相等`、violations = **11**、`RESULT: FAIL（violations=11）`、**exit 1**；样例：`[VIOLATION] 口径源漂移：writable_any_covered_by_all 钉值 118 ≠ 源值 None（源：coverage.json:summary.writable_any_covered_by_all）`。⇒ 与真违规**同码**，属工具面待解除项（§4.3-O6）；**本件不以裸跑读数判红/绿**。

### 1.4 真库只读（前 / 后）

- **命令**：`sha256sum app.db` + `stat -c '%s %y' app.db`
- **口径**：三值逐字恒等 = sha256 `34E48E7A21163DB390EEBDA4F2030343F3609AFEDC65D8C6E909D6EB5A49177E` / 2531328 B / mtime `2026-10-12 04:25:37.128430119 +0000`。
- **值**：
  - 开工（06:58 前）：`34e48e7a21163db390eebda4f2030343f3609afedc65d8c6e909d6eb5a49177e` / `2531328` / `2026-10-12 04:25:37.128430119 +0000` ✅
  - 收工（07:01 后，`ci_gates` + `check_doc_claims` 全部复跑之后）：同上，**逐字一致** ✅
  - 交叉读数（工具自报）：`[run_gates] real.db unchanged = True (34E48E7A21163DB3…)`
  - 未跑任何 `flask db *`；`HEAD` 全程 `9f28baa`（未变）

---

## 2. report-only 红逐条归因（工具 + 口径 + 值；登记 `blocked`）

### 2.1 `evidence_hash`（**唯一** report-only 红）

- **工具**：`ci_gates.py --phase first` 第 16 步；产物 `ci-run-20261012-065809/evidence_hash.gate.json`（297549 B，06:59:09）
- **口径**：`evidence/**` 与 `artifact_hashes.json` 基线逐文件对账；`modified != 0` ⇒ 红（report-only）
- **值**（本轮）：`baseline_files=1433 / current_files=2837 / modified=2 / deleted=0 / added=1404 / index_missing=148 / coverage_gap=2 / journal_broken=0 / phantom_entry=0 / baseline_tampered=0`
- 两条 `modified` 的**三值对照**（现场实测）：

| 文件 | 基线 字节 / sha256 | 现场 字节 / sha256 | 现场 mtime（UTC） | `append_only` |
| --- | --- | --- | --- | --- |
| `harness/b17-verify/probe_permission_matrix.txt` | 9627 / `1664B44BF5FB227BC4ED118CAD75EFB812AE3B8636768FD5CF8437D8389C49D5` | 11234 / `f81525c2b3cf4a5ed41f24ce5fee08ab0eedc5fda4436ab168e066384d5afb16` | `2026-10-12 04:45:29.081386626` | False |
| `harness/b17-verify/probe_smoke_test.txt` | 3186 / `59A7E5F065716E43B5049763C8471C207F1CF55632A914ADCF72FBCEDBAD7E95` | 3186 / `da0c377da223d63b998a3f1674b24c4b612d94d3420b4332bd23de314a954b68` | `2026-10-12 04:45:16.035562426` | False |

- **归因 = 先在性（非本批回归）**，三条独立证据：
  1. 两文件 mtime = `04:45:29` / `04:45:16`，**早于** C 批全部实现轮（t4 实验件 mtime `05:23:27`；本轮门禁 `06:32` / `06:46` / `06:58`）。
  2. 本轮窗口内该目录**零新增写入**：`find test-reports-2026-10/evidence/harness/b17-verify -newermt '2026-10-12 06:00' | wc -l` = `0`；目录内最新三件仍是 `04:45:29` / `04:45:16` / `04:43:56`。
  3. 机制（原文照录，非转述）：`test-reports-2026-10/harness/b17_governance_contract.py:48  e['HARNESS_RUN_ID'] = 'b17-verify'` 把该治理件钉在固定 run 目录；修前 `measure_coverage.py:254-255` 用裸 `open(ev,'w')` **原地覆盖**同目录 probe 证据 ⇒ 复跑即产生 `modified`。t8 修法（本批暂存改动 `+13/−9`，注释原文）：「t8：改走 `_env.save_evidence()`（E-01 只追加）——裸 `open(ev, 'w')` 会**原地覆盖**同 run 目录下的既有 probe 证据（2026-10-12 04:45 在 `b17-verify/` 实测发生过一次，导致 `evidence_hash` 报 2 条 modified）；守卫版同 run 复跑改名保留、原文件一字不动。」
- **状态**：`blocked`（**不折算 pass**）。
- **解除条件**（与登记件 `test-reports-2026-10/B18-登记.md:891` §B18-C-08「在册未解除 ①」一致）：A-70 `--freeze` 重基线 `artifact_hashes.json`，**或**让该治理件落到新的 `run_id` 目录后复跑 `ci_gates --phase first`；用户 A/B 未裁（默认 B）。本轮实测基线文件未变：`test-reports-2026-10/evidence/harness/artifact_hashes.json` = 1770 B / mtime `2026-10-11 00:28:08.859651549`（顶层索引；逐目录索引如 `harness/b17-verify/artifact_hashes.json` 承载 54 条实体）。
- **附带 `not_measured`**：t8 守卫「防再发」**本轮未实测** —— `ci_gates.py` 不调用 `b17_governance_contract.py`（`grep -n "b17_governance\|b17-verify" ci_gates.py` = **0 命中**；本轮 console 内 `b17_governance` 命中 **0**，`b17-verify` 仅出现在 `evidence_hash` 的 modified 清单里）。**解除条件**：单列复跑该治理件（钉 `HARNESS_RUN_ID=b17-verify` 或新 run_id）观测「改名保留、原文件一字不动」。

### 2.2 其余 report-only 步

`smoke_test` / `route_inventory` / `measure_coverage` 三步本轮均 **passed**（§1.1 步骤表）；即 report-only 红只有 `evidence_hash` 一条，与 `report_only_failed` 数组一致。

### 2.3 观察（不折算 pass）：`run_gates` 内部 `exit=1` 而 `ci_gates` 判 `passed`

- **值**：`[run_gates] run_id=run-20261012-065809  5/6 项 pass`；`probe_unexpected = 1`（= `route_inventory_native_probe exit=0 mode=native checks=0/0`）；`real.db unchanged = True (34E48E7A21163DB3…)`；`[run_gates] exit = 1  原因=['probe_unexpected=1']`。
- **口径（原文照录）**：`"note": "A-62：环境依赖探针留在 report-only；其 native_exit 与 expected 同时打印"`；`AGENTS.md` 亦明令 `run_gates.py` 的 `route_inventory_native_probe` 属环境依赖探针、**退出码不得写入任何 blocking 判据** ⇒ `ci_gates` 第 6 步判 `passed` 与 A-62 一致，**不构成 blocking 失败**，也不得据此判红。此条**登记为观察**（口径依据在册），**不折算 pass**。

---

## 3. 交付件指纹与暂存白名单（AC②）

### 3.1 C 批交付件指纹（本轮**全部重算**）

- **口径**：`wc -l` / `wc -c` 为全件；`head -n -1` 为「末行自指指纹行不计」的可复算口径（sha256 取前 16 位十六进制）。
- **值**（`test-reports-2026-10/` 下现场实测）：

| 交付件 | 全件行 | 全件字节 | `head -n -1` 行 | `head -n -1` 字节 | `head -n -1` sha256 |
| --- | --- | --- | --- | --- | --- |
| `C-P1P6P9P10-实现与读数.md` | 294 | 28215 | 293 | 27897 | `1a92548c10036f68` |
| `C-P2P3P4P5-实现与读数.md` | 203 | 17299 | 202 | 16893 | `ceb4dd61d7732bd6` |
| `C-工具面覆盖口径.md` | 264 | 29166 | 263 | 28566 | `7d7e8dbe6ff3222c` |
| `C-独立验证.md`（round 1） | 268 | 35326 | 267 | 35141 | `d980989634e86f7c` |
| `C-落点与在册项盘点.md` | 313 | 45051 | 312 | 44537 | `405a73ba65ee66b1` |
| `C-资产与口径订正.md` | 471 | 61233 | 470 | 61054 | `27db1f78b1a289d2` |
| `C-注入面与锚点实测.md` | 276 | 22411 | 275 | 22194 | `8b0d46b20d61c1ee` |
| `C-P1P6P9P10-复核.md` | 252 | 19682 | 251 | 19381 | `cc924d921ee6e413` |
| `C-P2P3P4P5-非作者复核.md` | 99 | 14799 | 98 | 14288 | `4483d8c595210180` |
| `C-写盘守卫-实现与读数.md` | 278 | 16497 | 277 | 16493 | `37a5eab9c91c01ae` |
| `C-写盘守卫-非作者复核.md` | 222 | 18340 | 221 | 18049 | `74f4eb246cb2bbef` |
| `C-工具面覆盖口径-非作者复核.md` | 226 | 24006 | 225 | 23723 | `774384b605be4ede` |
| `C-工具面覆盖口径-非作者复核-round2.md` | 219 | 27469 | 218 | 26786 | `2f4877c4ede00b5b` |
| `C-落点与在册项盘点-勘误附录.md` | 150 | 15376 | 149 | 14849 | `96bec726ceba3dc6` |

- 对账结论：① `C-P1P6P9P10-实现与读数.md`、`C-P2P3P4P5-实现与读数.md`、`C-工具面覆盖口径.md`、`C-工具面覆盖口径-非作者复核.md`、`C-独立验证.md`、`C-落点与在册项盘点.md` 的**自指值与本轮重算逐字一致**（前五者与 round 1 读数一致）；② `C-资产与口径订正.md` 的 `git hash-object` = `1175a92fc612e01007d649a1d3a255d27fea3afc`，与 t2 声明 blob 一致（其 prose 里的 `60690 B` 比现场 `61233 B` 少 543 B ⇒ 陈旧数，round 1 已记 F4，**只读件不追改**）；③ 与 round 1（06:20–06:46 窗口）相比，**全部 14 件未被覆盖**（行数/字节与 round 1 表逐条一致，唯本件为新增）。
- **append-only 复核**：`git status --porcelain -- docs/` = **空**；`docs/**` 本轮与本批均未被改写。

### 3.2 暂存白名单（本时点快照 `2026-10-12 07:01:09 UTC`）

- **口径**：逐条 `git diff --cached --name-status`；禁入项 = `app.db.evidence-*` / `instance/` / `.vscode/` / `.tmp*` / `node_modules`；行尾按 C7 用 `git diff --cached --ignore-cr-at-eol --numstat` 复核。
- **值**：暂存 **21 条** = 7 `M` + 14 `A`：
  - `M app/main/routes.py`（51/32）、`M scripts/check_doc_claims.py`（3/2）、`M scripts/permission_matrix.py`（28/18）、`M test-reports-2026-10/52-V13-TL050607-工具链收尾.md`（1/1）、`M test-reports-2026-10/B18-登记.md`（93/0）、`M test-reports-2026-10/harness/measure_coverage.py`（13/9）、`M test-reports-2026-10/subagent-routing.md`（3/2）
  - 新增 14 件 = `C-P1P6P9P10-复核.md`(252/0)、`C-P1P6P9P10-实现与读数.md`(294/0)、`C-P2P3P4P5-实现与读数.md`(203/0)、`C-P2P3P4P5-非作者复核.md`(99/0)、`C-写盘守卫-实现与读数.md`(278/0)、`C-写盘守卫-非作者复核.md`(222/0)、`C-工具面覆盖口径-非作者复核-round2.md`(219/0)、`C-工具面覆盖口径-非作者复核.md`(226/0)、`C-工具面覆盖口径.md`(264/0)、`C-注入面与锚点实测.md`(276/0)、`C-独立验证.md`(268/0)、`C-落点与在册项盘点-勘误附录.md`(150/0)、`C-落点与在册项盘点.md`(313/0)、`C-资产与口径订正.md`(471/0)
  - 禁入项逐项计数：`app.db.evidence-` = 0、`instance/` = 0、`.vscode/` = 0、`.tmp` = 0、`node_modules` = 0 ✅
  - C7 行尾：`git diff --cached --numstat` 与 `--ignore-cr-at-eol` 版本 `diff` = **空** ⇒ 无 CRLF 漂移 ✅
- **观察（时间戳口径）**：本轮窗口内暂存集合由 06:5x 的 6 条扩至 07:01 的 21 条（另一线在做提交准备）⇒ 本判定仅对**上述时点快照**有效；提交前请以 `git diff --cached --name-status` 再核一次，且继续用逐条白名单（禁 `git add -A` / `git add .`）。
- **未跟踪残留（不被暂存 ⇒ 无污染风险，但提交前勿误加）**：`.tmp/`、`.tmp-t6runs/`、`.tmp-t9runs/`、`instance/`、`.vscode/settings.json`、`app.db.evidence-ALLOY-IMPORT-02-20261009_004539`。

---

## 4. 三张清单（round 2 收口态）

### 4.1 本批**关闭**（复验通过；逐条给关键实测值）

| 项 | 载体 | 关键实测值（round 1 自写脚本复跑；round 2 复核未漂移） |
| --- | --- | --- |
| P1 | `app/main/routes.py:4471 _assert_add_audit_target` + 11 调用点 + `app/main/quality.py:601/:675` | AST 扫描 `SITES=74 NULL_RISK=0 GUARDED=12`；实跑 `target_id=2 can_rollback=True`；守卫直调 ⇒ `AssertionError`；真库 `can_rollback=1 & target_id IS NULL = 0` |
| P2 | `app/main/routes.py:5505`、`:5598` | `JoinedStr=2 / 裸字面量=0`；渲染 `第5行导入失败，请稍后重试或联系管理员` |
| P3(a) | `/employees/import`（**权威载体**，`70-…md:161` P3 定义） | 3 好 + 2 坏 ⇒ `Δ=3`、`第4行/第6行数据错误`、TEMP `[]` |
| P3(b) | `/process_prices/import`（t5 实际改动点） | 同上形态 ⇒ `Δ=3`、`第5行/第6行数据错误` |
| P4 | `import_products` `app/main/routes.py:8324`（`finally` + `rmtree`）、`save_temp_file:5645` | helper 失败路径 + 端点异常路径两条均 `TEMP entries=[]` |
| P5（主流） | `app/main/routes.py` 11 处 `第 {index + 2} 行：` | `ΔPR=3`、`第 4 行：员工工号 … 不存在`（= Excel 行号） |
| P6 | `update_task_status`（7 个内层块 + 外层兜底） | 健康 `PR 0->1`；投毒 ⇒ `http=500`、`PR 0->0`、`raw 100.0->100.0`（全 Δ=0） |
| P9（退化分支） | `app/main/stock.py:74` → `mes_service.py:1297` | `http=200`、台账行 `报废单1 qty=2 workpiece_id=None`；退化路径 `报废单2` |
| P10① | `app/utils/excel_generator.py:358` | 4 列 ⇒ `notes=None`；5 列 ⇒ `'备A'`；端到端 `成功导入 1 条记录` |
| P10② | `app/main/routes.py:157-197`（调用点 `:2963/:4179/:4300`） | 业务日 `2026-06-15 ⇒ version=2/price=20.0`；`None ⇒ None` |
| G-12 | `test-reports-2026-10/harness/analysis_ledger.py` / `improve_plan.py` / `final_recount.py` | 整数词边界扫描 `101/141` 命中 **0**；`coverage_verdict()` 现场重算；`final_recount` 已绑 `coverage_pins()` |
| G-15（TL-05/06/07 **注入面**） | `scripts/check_properties.py` / `check_doc_claims.py` | 合成坏树 `rc=1`；注入作废值 `≥135` ⇒ `rc=1` 报 `ge135`；删 lock ⇒ `rc=1`；三态阴性对照全红（⚠ G-15 的**「三载体」层**仍未测 ⇒ 见 O4，不并入本行） |
| G-16②=P12 | `harness/reconcile_r2.py:593` + `:324/:327` | 调用点已带 `--coverage run_coverage_artifact()`；四态 `0/2/1` 语义齐 |
| G-17 | `test-reports-2026-10/40-*.md` | `git status --porcelain` 与 `git diff --numstat` 均空 |
| G-20 | `test-reports-2026-10/harness/api_matrix.py:733 def csrf_matrix` | 唯一实现（`scripts/api_matrix.py` 不存在）；A-69 单一分母注释在册 |
| G-19 | `scripts/permission_matrix.py`（`deny_roles_for:383`） | 写端点 **21**（9/8/4）、逐端点 ≥1 allow + ≥1 deny、工具 `exit=0` |
| G-21（成文口径） | `test-reports-2026-10/C-工具面覆盖口径.md` | `N=44 / M=38`（`N−M=6`）；38 条 rule 在件内逐条出现（未出现 = `[]`） |

### 4.2 **部分关闭 / finding**（不折算 pass，逐条带解除条件）

- **F1（medium）`not_measured`：P9 非退化归属分支** —— 未独立复现「有 `production_record` + batch + 订单」时台账行 `product_number` 取真实产品号（真库 `production_record` 0 行，须自造夹具）。**解除条件**：副本库自造夹具走 `/api/quality/nonconformities/<id>/dispose`，断言 `product_number` = 批次产品号（非 `报废单N`）且件数一致；跑绿后回填本行。
- **F2（low）P5 行号口径边界** —— 输入含**中间全空行**时 `parse_*` 跳过空行 ⇒ 文案行号（解析后序号 + 2）< Excel 物理行号（`Δ=3` 主流场景不受影响）。**既有语义，非本批引入**。**解除条件**：改为「解析后序号 + 丢弃行数 + 2」显式口径（或 pandas 行索引映射）并补空行夹层用例；改判据须走 A-70 三步。
- **F3（low）任务书载体措辞勘误** —— t5 的 AR2 写 `/employees/import`，代码落在 `/process_prices/import`；两载体均实测通过 ⇒ 记勘误，不折算 pass。**解除条件**：captain 在登记件留档勘误（`B18-登记.md:901` 已就近记录同族处置纪律）。
- **F4（note）`C-资产与口径订正.md` prose 陈旧数** —— 声明 60690 B，现场 61233 B；`git hash-object` 与声明 blob 一致 ⇒ 内容未漂移。**解除条件**：无需动作，后续引用以现场字节数为准。
- **F5（low，本轮新增）`run_gates` 内部 `exit=1` 与步判 `passed` 的表述风险** —— 见 §2.3。**解除条件**：无需改码（A-62 口径已定）；引用时须同时给 `probe_unexpected=1` 与 A-62 依据，**不得**把 `run_gates exit=1` 写成「blocking 失败」，也**不得**写成「6/6 全绿」。
- **F6（low，本轮新增）P11 / G-22：读数已清零但无处置登记件 ⇒ `not_counted_as_passed`** —— 工作区 `.tmp_v15_*` 0 个、`git ls-files | grep tmp_v15` 0 条（本轮复核，见 O3），但「不复现」**不等于**「已处置」，故**不列入 §4.1 关闭表**。**解除条件**：captain 出登记件记录「已消除/不复现」+ 复现命令后，方可移入关闭表。

### 4.3 **仍留档**（`blocked` / `not_measured` / `not_covered` / `not_counted_as_passed`，逐条带解除条件）

- **O1 `blocked`（report-only，先在性）`evidence_hash`** —— 见 §2.1；本轮值 `modified=2`（`b17-verify/probe_permission_matrix.txt`、`probe_smoke_test.txt`，mtime `04:45:29`/`04:45:16`）。**解除条件**：A-70 `--freeze` 重基线 或 治理件落到新 `run_id` 目录后复跑取 `exit=0`（用户 A/B 未裁，默认 B）。
- **O2 `not_counted_as_passed` `A-63-STEP2-BUILD-GATE`** —— `ci_gates` 自报 `blocked（不计入通过数）`；容器内无 `docker` ⇒ 不可测。**解除条件**：解注释 `Jenkinsfile:112/122` + GH 去 `continue-on-error` + `build-and-push` 加 `needs: gate`，在有 Docker 的 CI 主机复跑一轮并回填。
- **O3 `not_counted_as_passed` P11 / G-22（处置登记件缺位）** —— 工作区与 git 索引均 0 条（本轮复核：`git ls-files | grep tmp_v15` = 0），但**无处置登记件** ⇒ 不得折算 pass。**解除条件**：captain 出登记件记录「已消除/不复现」+ 复现命令。
- **O4 `not_covered` G-13 / G-15 三载体 / G-18** —— t1/t3 判定（G-13 保持 `not_covered`；G-15 三载体 MISSING；G-18 仍增长）；本轮未复跑（不在 round 2 必做面）。**解除条件**：单列任务补测后回填。
- **O5 `not_measured` coverage 冻结锚点** —— `evidence/harness/coverage.json` 已不在盘、`coverage_drift.py:120` 声明的 `_anchor-history/` 不存在、`evidence/**` 被 `.gitignore:42` 忽略且从未入 git ⇒ **不可恢复**；判据本身正确（无参 `rc=2` fail loud、陈旧产物 `rc=1`、本次产物 `rc=0` 8/8 面）。**解除条件**：A-70 重基线并新建冻结锚点（用户/captain 层裁定）。
- **O6 `not_counted_as_passed` 工具缺陷：`check_doc_claims.py` 裸跑假红 11 条** —— 本轮复测 `20/29 相等` + `violations=11` + `exit=1`，与真违规**同码**（§1.3）。**解除条件**：默认源缺失走「fail loud + 专用退出码/文案」，或把默认源语义改为显式 `--coverage` 必填；改判据须走 A-70 三步。
- **O7 `not_measured` G-21 uncovered 38 条** —— 口径已逐类成文（38/38：已纳入 1 / 显式不纳入 13 / 留档待决 24），但**未纳入不构成覆盖**。**解除条件**：captain 裁定分批纳入计划后逐批跑绿回填。
- **O8 `blocked` B17-11 契约钉值 vs 现场** —— `b17_governance_contract.py:723-724` 钉旧值 `multi_method_with_get=43 / uncovered=37`，现场 `44/38`；该契约**不在** `ci_gates` 链内（不构成红）。**解除条件**：重新入链前先走 A-70 重基线，否则保持只读报告口径。
- **O9 `not_counted_as_passed` 既有在案：`/products/import` 表单层** —— `forms.py:216 MultipleFileField` + `update_existing` 缺位（`B17-登记.md:187`；`B18-登记.md:891` 在册未解除 ②）；本轮复跑 P4 时**同样必须**用表单垫片才能触达端点主体（印证仍在）。**解除条件**：单列任务修复该表单字段后，复跑 P4 段与 `after_observations.py` E 场景。
- **O10 `not_counted_as_passed` 63 个「口令==用户名」自证账号未全量打标** —— 设计为首次登录自动打标，**用户裁决未回**（`B18-登记.md:891` 在册未解除 ③）。**解除条件**：用户裁决 或 观测首次登录打标后回填读数。
- **O11 `blocked` `/auth/logout` 仍为 GET** —— B18-Q2 残余风险（`B18-登记.md:891` 在册未解除 ④）；未在本轮改动。**解除条件**：单列任务改为 POST（含模板/JS 同步 + `check_templates` 复跑）后回填。
- **禁写「在册缺陷清零」**：本批关闭 17 项 / 部分关闭 6 项与上列留档 **11 项并存**；任何「清零 / 全绿 / 门禁 exit 0」表述均与本件读数不符（实测 `exit=2`，`blocking 失败=无`）。

---

## 5. 未测项与复现边界（一律不折算 pass）

1. P9 非退化归属分支（F1）；2. `evidence_hash` 转绿（O1）与 t8 守卫「防再发」实测（§2.1 附带 `not_measured`）；3. A-63-STEP2 build gate（O2，环境无 docker）；4. G-13/G-15 三载体/G-18（O4）；5. coverage 冻结锚点重建（O5）；6. G-21 38 条纳入实施（O7）；7. 63 自证账号打标（O10）；8. `/auth/logout`（O11）；9. `/products/import` 表单修复（O9）。
- 本件**未**独立复跑 round 1 的 12 条自造阴性对照（判据：t7 任务书要求「每条已修缺陷 ≥1 条自造阴性对照」，round 1 §4 已给出 11–12 条转红读数并存入 `test-reports-2026-10/evidence/c/t7/`，`evidence/**` 被 `.gitignore:42` 忽略、属本地留档）；本轮**新增**的判据侧对照 = §1.3 裸跑（真红/假红同码）与 §4.3-O6 复测 ⇒ 均按上述状态登记。

---

## 6. 证据索引

- **本轮新跑产物（工具自带落点，不是我写的）**：`test-reports-2026-10/evidence/harness/ci-run-20261012-065809/`（§1.1 十个文件）。
- **round 1 自写脚本（沿用，本轮未改）**：`test-reports-2026-10/evidence/c/t7/` 下 `p1_invariant_scan.py`、`t7_a_p1_p6_p9.py`、`t7_b_p2_p3_p4_p5.py`、`t7_c_g19_g21.py`、`t7_d_inject_assets.sh`、`t7_e_gates.sh`、`t7_f_p10.py`、`t7_g_p3_authoritative.py` + `negctl/` 夹具 + 各自 `.log`。
- **在册登记件（引用口径的依据）**：`test-reports-2026-10/B18-登记.md:860` §B18-C-07（A-70 重基线 `routes_py_lines` 12806 → 12825）、`:886` §B18-C-08（C 批观察项裁定；在册未解除 ①–④ 在 `:891`）、`:893` §B18-C-09（t12 复核裁定）。
- `evidence/**` 被 `.gitignore:42` 忽略 ⇒ 本地留档，不追改、不入 git。

## 7. 声明

- 本件由**非作者**（`verify-c`）编写；**作者自述未作为通过依据**，round 2 的门禁读数、指纹、`check_doc_claims` 两命令与真库三值**均本轮重跑**；引用 round 1 读数的位置已显式标注轮次。
- 未改任何判据 / 钉值 / 期望值；未改 `app/**`、`scripts/**`、`test-reports-2026-10/harness/**`、`docs/**`、`evidence/**`；发现的口径问题一律登记（F1–F5、O1–O11）。
- 未 `git add` / `commit` / `push`；真库只读，三值开工/收工逐字恒等；未跑任何 `flask db *`。
- 本轮结论：**blocking 口径 PASS（`steps=20` / `blocking 失败=无`）**；`exit=2`（唯一红 = 先在性 report-only `evidence_hash`）；**本批关闭 17 项 / 部分关闭 6 项 / 仍留档 11 项**；**禁写「在册缺陷清零」**。
- 本件自指指纹（末行不计）：`head -n -1` = 220 行 / 28061 字节 / sha256 `65f84e30e7a99fb5`（全件 = 221 行 / 28208 字节）。
