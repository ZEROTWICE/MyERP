# 任务D 集成复核（t6，reviewer-d；**非实现者 / 非作者**）

- 复核人：`reviewer-d`（route `volcengine-code/deepseek-v4-1-flash-260910`，effort=max）；task `t6` / attempt `1` / `attempt_id=33c79011-c36a-4430-93e3-e34141c3be47`
- 时间窗：2026-10-11 15:12–15:2x UTC；工作目录 `/root/code/MyERP`；`HEAD = 1a3850fd767a39c8b89717e98ae2ac83e2587e62`
- **边界**：未改任何实现代码 / 模板 / `scripts/` / `harness/`；未跑 `flask db *`；真库 `app.db` 全程 **只读**（`sqlite3 file:…?mode=ro`）；未改写任何 task 终态；`push` 由人工决定。
- **时点性声明**：本件所有 sha256 / 行数 / mtime 均带时点；凡"每次运行会重写"的件（§10 活产物表）引用时必须重取。
- 本文证据 = **工具 + 口径 + 值**；凡 `blocked` / `not_measured` / `not_covered` / `not_counted_as_passed` 一律**不折算 pass**（§6）。

## §0 结论速览

| # | 必核项 | 判定 | 关键读数 |
| --- | --- | --- | --- |
| 1 | 门禁末态（自跑） | ✅ 成立 | `steps=20` / blocking 失败 **无** / report-only 失败 **无** / 注入未生效 **无** / 根两 JSON 未被触碰 **True** / `exit=0`；`--selftest` 26/26 |
| 2 | 真库不变量 + 仓库卫生 | ✅ 成立 | `app.db` 三值逐位一致（开工/3 次 uat run 前后/收工）；`git status` 仅 6 `M` + 6 `??`（全部可归属，见 §2） |
| 3 | 在册项守门 | ✅ 成立 | **0 项被折算 pass**；本轮真正消除**只有 N-2、N-5**（归属见 §6.1），其余 24 项保留原状态 token + 解除条件（§6.2） |
| 3b | t9 退出码正式验收（`t11-R1` 解除条件） | ✅ 通过 | 红 `exit=1` / 同扰动旧退出码行 `exit=0` / 绿 `exit=0`（§3，A/B 唯一差异 = 退出码行） |
| 3c | 重基线未回退（t9 落盘后） | ✅ 成立 | `APPEND.1` PASS、`84/84/0/0`、digest 仍 `D82423A9…46F2C`（§4） |
| 4 | 提交清单 | ✅ 给出 | 白名单 9 项（6 `M` + 3 `??`）；`evidence/` 整树被 `.gitignore:42` 忽略 ⇒ **不入库**；禁 `git add -A` / `git add .`（§7） |
| 5 | 残余风险 | ✅ 给出 | R-1 移动靶 / 真库锚点重设前置 / `G-1…G-22` 未处置面（§8） |

**finding**：**零阻塞 finding**。另有 3 条**观察**（§12）：均为既存口径事实、非本批引入、**不折算 pass**、附处置。

---

## §1 必核 1：门禁末态（**本件自跑，不引用他人 console**）

命令（逐字）：

```
/opt/wage-venv/bin/python -B test-reports-2026-10/harness/ci_gates.py --phase first   # exit=0
/opt/wage-venv/bin/python -B scripts/check_doc_claims.py --selftest                    # exit=0
```

run 产物：`test-reports-2026-10/evidence/harness/ci-run-20261011-151232/`（10 文件）

| 件 | 值 |
| --- | --- |
| `ci_gates_first.console.txt` | 46737 B，mtime `2026-10-11 15:13:42`，sha256 `188edbe0d1c34455c50e69663337c42a6a9d137116c5bad907cf10d8477f3043` |
| `gates.json` | 15376 B，sha256 `62dd99f89775d9dd0d62c1a551b00934d72cb28395301af54a847eb265a41efe` |

**读数（console 内嵌 JSON 实读）**：
`run_id=run-20261011-151232`、`phase=first`、`interpreter=/opt/wage-venv/bin/python`、**`step_count=20`**、
`blocking_failed=[]`、`report_only_failed=[]`、`injection_ineffective=[]`、`injection=null`、
`root_json_untouched.ok=true`（before/after 逐位相同：`_smoke_results.json` = `D301835F077D2EDFFCB5DA4469C87A23C594D1E9EC75010594C3A812466A9762`、`_permission_matrix.json` = `999A01209A8A56BBE7CF1FB5842FE4991762A91683DF97621650B11068B67C19`；`frozen_reference` 同值）、`exit=0`、gaps = `A-63-STEP2-BUILD-GATE = blocked（不计入通过数）`。

**20 步逐条**（`id / group / exit_code / status`）：

| 步 | 组 | exit | status |
| --- | --- | --- | --- |
| check_templates | blocking | 0 | passed |
| check_migration_heads | blocking | 0 | passed |
| check_table_parity | blocking | 0 | passed |
| check_properties | blocking | 0 | passed |
| check_db_bootstrap | blocking | 0 | passed |
| run_gates | blocking | **1** | **passed**（判据 = 4 条 needle，`expected_exit=None`，见 §12 观察①） |
| functional_test | blocking | 0 | passed |
| permission_matrix | blocking | 0 | passed |
| smoke_test | report-only | 0 | passed |
| route_inventory | report-only | 0 | passed |
| measure_coverage | report-only | 0 | passed |
| coverage_drift | blocking | 0 | passed |
| check_notification_triggers | blocking | 0 | passed |
| check_model_refs | blocking | 0 | passed |
| check_http_contract | blocking | 0 | passed |
| evidence_hash | report-only | 0 | passed |
| chain_count_consistency | blocking | 0 | passed |
| negative_matrix | blocking | 0 | passed |
| check_is_archived_policy | blocking | 0 | passed |
| check_doc_claims | blocking | 0 | passed |

- `check_doc_claims` 步 needle **实读命中**：`钉常量 vs 权威源：29/29 相等`、`文档：扫描 5 份、带口径表 1 份`、`RESULT: OK（violations=0）`、`[VIOLATION]` 缺席、`exit == 0`。
- `--selftest` ⇒ `[check_doc_claims] 自检 26/26 通过`，`exit=0`（含 DC-N9 九键逐键必红、DC-L1…L5 lock 面）。
- **与 AGENTS.md 既存读数对照**：`report-only 失败` 在本批不同时点构成不同（B18-08 时 = `['evidence_hash']` + `exit=2`；**本次 = 无 + `exit=0`**）⇒ 记为**时点差异**，不据此改任何钉值。

## §2 必核 2：真库不变量与仓库卫生

**真库 `app.db` 三值**（每次操作前后各核，本件全程 5 次：开工 / uat 三次 run 的 before+after / 收工）：

| 项 | 值 |
| --- | --- |
| sha256 | `b4fb980c5d1b25b3c3a0eadc12ecf01c75b36ebd213b109e5dd190c617eeaabe` |
| 字节 | `2531328` |
| mtime | `2026-10-09 03:39:39.418764055 +0000` |

⇒ 三值**逐位一致**，未跑 `flask db *`；本次对真库只有一次 `sqlite3 …?mode=ro` 只读查询（§6 N-1/N-6）。

**`git status --porcelain`**（收工现读，12 项，全部可归属）：

| 状态 | 路径 | 归属 |
| --- | --- | --- |
| `M` | `app/templates/main/purchase/order_detail.html` | t2（R-2 枚举中文化） |
| `M` | `app/templates/main/purchase/orders.html` | t2（R-2） |
| `M` | `app/templates/main/purchase/requisitions.html` | t2（R-2） |
| `M` | `app/templates/main/quality/tasks.html` | t2（R-3 补 `cancelled`） |
| `M` | `test-reports-2026-10/B18-登记.md` | captain 台账（append-only） |
| `M` | `test-reports-2026-10/harness/uat_chains.py` | t3（N-2）+ t8（重基线）+ t9（退出码） |
| `??` | `test-reports-2026-10/D-落点与在册项盘点.md` | t1 交付件 |
| `??` | `test-reports-2026-10/subagent-routing.md` | 路由规则仓库内副本（非 D 组产物，入库与否见 §7） |
| `??` | `test-reports-2026-10/D-集成复核.md` | **本件（t6 交付件）** |
| `??` | `test-reports-2026-10/.tmp-t9runs/` | t9 红副本暂存（**新增 scratch，禁入库**） |
| `??` | `test-reports-2026-10/.tmp-t6runs/` | 本件红副本暂存（**新增 scratch，禁入库**） |
| `??` | `.tmp/` · `.vscode/settings.json` · `app.db.evidence-ALLOY-IMPORT-02-20261009_004539` · `instance/` | §B18-C-06 B 预登记既有遗留（禁入库） |

`git diff --stat` 现读：6 files changed, 358 insertions(+), 25 deletions(-)（`B18-登记.md` +274、`uat_chains.py` 85、4 模板 24）。
`git check-ignore -v` 逐路径复核：`test-reports-2026-10/evidence/**` 命中 `.gitignore:42`；`test-reports-2026-10/.tmp/` 命中 `.gitignore:41`；上表 6 个 `??` 非忽略路径 **rc=1（无输出）** ⇒ 必须逐条 `git add`。

## §3 追加必核 ①：t9 退出码的**正式验收**（解除 `t11-R1`）

**口径**：作者（t9）自报读数不计分；本件**自行构造**并留痕（仍严格非作者：t9 的验证对象是 `harness/uat_chains.py` 的退出码语义，本件独立重造同一 A/B 对并自跑）。

构造（`test-reports-2026-10/.tmp-t6runs/`，**干净同层目录 + `PYTHONPATH=test-reports-2026-10/harness`**，避开 `.tmp/_env.py` 影射陷阱，见 §9）：

| 副本 | 构造 | sha256 | 大小 |
| --- | --- | --- | --- |
| A `t6-red-new-uat_chains.py` | 现盘文件 + `BASELINE40_DIGEST` 末位 `C→D`（`…DD46F2D`） | `8d514df1dc5ba0486b5a18556495340724553cff8378a175673a3fac51d772d8` | 198211 B |
| B `t6-red-old-uat_chains.py` | 同 A 扰动 + 退出码行换回旧形态 `return 0 if summary['blocked'] == 0 else 1` | `755a20d90cd07280017eff68c5887a374c0956eacd6660c71acc59e9b1019a51` | 198185 B |

**A/B 唯一差异（机械证明）**：`diff A B` 输出 = `3257c3257` 单行（`< return 1 if (summary['failed'] > 0 or summary['blocked'] > 0) else 0` / `> return 0 if summary['blocked'] == 0 else 1`），无第二处差异。
（两副本 sha 与 t9 在册件 `test-reports-2026-10/.tmp-t9runs/t9-{red,negctl}-uat_chains.py` **逐位相同** ⇒ 确定性构造、同一扰动；本次读数仍以**本件自跑**为准。）

**三联读数**：

| run | 被测文件 | 判据状态 | 退出码 | console（sha256 / 大小 / 时点） | run 产物 |
| --- | --- | --- | --- | --- | --- |
| 红态 `t6-red-new-151419` | A（新退出码行） | `[FAIL] APPEND.1`（`digest_match=False`）`total=84 passed=83 failed=1 blocked=0 execution_errors=False` | **exit 1** | `dd33a67a11f498b1d806ba5459171622eae5c7110c69f50fabf96ce57a911b87` / 67999 B / 15:14 | `evidence/harness/uat/t6-red-new-151419/` |
| 阴性对照 `t6-red-old-151424` | B（同扰动 + 旧退出码行） | **逐字节相同**（`APPEND.1` FAIL、`84/83/1/0`） | **exit 0** | `5c36d1f2d3fe9efdbb18a4cac52522009445585c0af29a3e6e9279b40e90170e` / 67999 B / 15:14 | `evidence/harness/uat/t6-red-old-151424/` |
| 绿态 `t6-green-151429` | **现盘文件原样（in place）** | `[PASS] APPEND.1` + `[PASS] FLIP.SUM`（`failed_rows=0`）`total=84 passed=84 failed=0 blocked=0` | **exit 0** | `ef47fd0aff599301010736501bf1d4a567f6cb6f827c63cae3f8882d5bf3f5bb` / 66920 B / 15:14 | `evidence/harness/uat/t6-green-151429/` |

⇒ **判定：`t11-R1` 解除条件达成** —— 红态 `failed>0` ⇒ `1`；同扰动下唯一差异（退出码行）换回旧形态 ⇒ `0`（**缺陷复现**，证明新判据非恒真）；绿态 ⇒ `0`。

**子分支覆盖口径**（不折算）：
- `failed>0` 分支：**已实测**（上表两行）。
- `blocked>0` 分支：**未构造运行面样本** ⇒ 记 **`not_measured`**；作为补充，用 AST 从**现盘文件**抽取第 `:3257` 行表达式（`ast.get_source_segment`，表达式 sha256 `97353070abe472721bbbc2146adce0caff713bd510dea2122acfb2a378737254`）后逐组合求值：`failed=0/blocked=0 ⇒ 0`、`failed=1/blocked=0 ⇒ 1`、`failed=0/blocked=1 ⇒ 1`（**静态语义读数，不是运行读数**）。
- 解除条件：构造一个 `blocked>0` 的真实 run（链级异常路径），复跑本表红态口径一次。

## §4 追加必核 ②：重基线未回退（t9 落盘后）

来源 = §3 绿态 run（现盘文件原样）console 实读：

| 判据 | 读数 |
| --- | --- |
| `APPEND.1` | **PASS**，`baseline_count=40`、`ids_match_order=True`、**`digest_match=True`**、`expected.digest = got.digest = got.frozen_digest = D82423A90EF13F77DAA06C5BD4F85EC83C9002F31FA78BAF5D7482968DD46F2C`、`total_checks=82`、`new_checks=42` |
| `FLIP.SUM` | **PASS**，`new_checks=43`、`flip_rows=43`、`expected_flip_rows=43`、`red_rows=43`、`all_red=True`、`blocked_rows=0`、**`failed_rows=0`**、`chain_a_pass=21` |
| 汇总 | `total=84 passed=84 failed=0 blocked=0 execution_errors=False` |
| 现盘 `BASELINE40_DIGEST` | `harness/uat_chains.py:1194` = `D82423A90EF13F77DAA06C5BD4F85EC83C9002F31FA78BAF5D7482968DD46F2C`（**未回退**） |
| 现盘文件 | sha256 `5721adecb25cc8f963e1bf45efa06443f7451c9ac31692e72a899b36ab04ae8e` / 198211 B（与 t9 交付值逐位一致 ⇒ t9 之后无人再改） |

⇒ 结论：**A-70 重基线在 t9 落盘后未回退**。（`new_checks` 在两条判据里分别记 42 / 43，见 §12 观察②。）

## §5 追加必核 ③：`git diff` 面复核（按 §B18-D-07 **D-4**，不沿用"只有两类"的错表述）

命令与值：

```
git diff -U0 -- test-reports-2026-10/harness/uat_chains.py | grep -c '^@@'     # = 15
```

| 类 | hunk 数 | 坐标（新文件行） |
| --- | --- | --- |
| t8（A-70 重基线） | 2 | `:1180-1183`（溯源注释）、`:1194`（digest 值） |
| t3（N-2 CA4a 订正） | **11** | `:1512`、`:1533`、`:1537`、`:1543`、`:1546`、`:1549`、`:1623`、`:1827`、`:1836`、`:1947`、`:1953` |
| t9（退出码 + argv 校验） | 2 | `:3254`（退出码）、`:3293`（argv 处理） |
| **合计** | **15** | **零不可归属 hunk（零越域）** |

**留档 ≠ HEAD 版**（D-1 订正，本件独立复核）：

| 件 | sha256 |
| --- | --- |
| `test-reports-2026-10/.tmp/t8-pre-uat_chains.py`（留档） | `96b933b5113e8f9535cd0a654a4839b2d8b8953b1a5caf17b78d2494337f0d10` |
| `git show HEAD:test-reports-2026-10/harness/uat_chains.py` | `1413f57731868bb687237a581e491ed32cdddaa93767b0a29042669a004aa5f6` |

⇒ 正确表述：「留档**不是** HEAD 版（HEAD 版**不含** t3/N-2，留档**已含**）；`diff 留档 → 现文件` = **4 hunk**（t8×2 + t9×2），**无第 5 处差异** ⇒ 留档是 **t8 的真前像**」。本件实测：`diff -U0 留档 现文件 | grep -c '^@@'` = 4。

## §6 必核 3：在册项守门（本任务核心纪律）

**总口径**：`blocked` / `not_measured` / `not_covered` / `not_counted_as_passed` **一律不得折算 pass**；本轮**真正消除的只有 N-2 与 N-5**，且必须写明**由谁的哪条读数消除**。

### §6.1 本轮消除项（仅 2 项，逐条归属）

| # | 项 | 消除依据（作者读数 + 非作者读数 + 本件终态读数） |
| --- | --- | --- |
| **N-2** | `B14-07` V-12 探针 `CA4a` 与方案A 冲突（harness 未改） | ①**实现**：t3 按 §B18-D-01 裁决②订正期望（A-70 三步，§B18-D-04:629-636）——`n2-before` `CA4a` **FAIL**（期望 `False` vs 实测 `True`）→ `n2-negctl` 期望临时改回 `False` ⇒ **必红**（passed 83→82）→ `n2-after` `CA4a` **PASS**、`total=84 passed=83 failed=1 blocked=0`（**该 run 的 `failed=1` = 既存 `APPEND.1` 恒红，属 t8 口径漂移、非本项**）。②**非作者验证**：t5（verify-d3）`evidence/d/t5-验证登记.md`（sha256 `c2cffcf056214441fff1…`，`verdict=pass`）§3 = `CA4a` 改前 FAIL / 改后 PASS（复跑对象 = t3 交付件快照 `96b933b5…`）。③**本件终态复跑**（§3 绿态 run，被测 = 现盘终态 `5721adec…`）：`[PASS] CA4a`，`got.ui_goods_receipt_option=True`、`ui_options=['production_record','product','material','goods_receipt']`，全链 `84 PASS / 0 FAIL` ⇒ **终态未回退**。 |
| **N-5** | 全库逐码**新旧取价口径等价**未独立复算 | ①**独立复算（非作者）**：t4（verify-d2），§B18-D-02:585 —— C2 合成夹具 **15/15**（4 类新旧差异：多版本取最新有效 / 仅未来价 / `is_current=0` / 容差上界）、C3 阴性对照 **3/3 全转红**、C2X 第三工具面（纯 sqlite、无 ORM）**11/11**；JSON sha `BAE56F9A…5030` / `809F7A85…C5` / `1FEB8803…8872`。②**口径收紧**（§B18-D-01 裁决③）：真库 `compared=3486 same=3486 mismatch=0` **判别力为零**（多版本码 0 / 未来价 0 / `is_current={1:3486}`）⇒ **不作解除证据**。③工具面：t7 修 v2 退出码（`1437027E…5DE69`）、t10（verify-d2）非作者复核 `1C3AF423…BE41`。 |

> **本件对 N-2 的守门补充**：`B18-登记.md` 中 N-2 只出现在 `:500`（清单复述）、`:543`（裁决②修法）、`:625`（t3 交付裁决）三处，**原先没有一条显式「N-2 解除」语句** —— 本件按上表归属补记，并在 §B18-D-09 追加（append-only）。

### §6.2 未消除项（**24 条，全部保留原状态 token + 解除条件**）

**a) 复核件 §7 N-1…N-8**（`evidence/b18c/integration-review.md`，sha256 `50865091ad144d507321b0e400c63e25cc07b6037401b70c5e5b82c7808e5df7`、20325 B、mtime `2026-10-11 13:30:07`，本件未改）

| # | 现读（本件独立抽核） | 状态 token | 解除条件 |
| --- | --- | --- | --- |
| N-1 | `sqlite3 mode=ro`：`audit_log` total **73** / `can_rollback=1` **34** / 命中（`can_rollback=1 ∧ target_id IS NULL`）**10** 行 `id=[7,8,12,15,24,29,40,44,68,73]`，`rollback_type` 全 `add`、`rolled_back` 全 `0` ⇒ **写入确未执行** | `not_counted_as_passed` | 用户放行 + 接受真库锚点重设（§B18-C-06 D） |
| N-2 | 见 §6.1（**本轮消除**） | ~~`not_counted_as_passed`~~ → **已消除** | 达成（t3 + t5 + 本件终态） |
| N-3 | `Jenkinsfile:111-112`、`:121-122` 的 `error()` **仍是注释**；`:124` 仍 `echo UNSTABLE`；`.github/workflows/docker-deploy.yml:36 continue-on-error: true`、`:106` **无** `needs: gate` ⇒ 未解除 | `blocked` | 真实 CI 全绿 ≥1 轮 + 三动作（Jenkinsfile 解注释 / GH 去 `continue-on-error` + 加 `needs: gate` / echo 清单补三脚本） |
| N-4 | `B17-02 ≡ C-07`（`81-…md:823`「同一件事，不得重复计数」+ `90-…md:205/:264`） | `blocked(生产面冻结)` / `not_counted_as_passed=true` | 生产面冻结解除 + 显式授权通道；判据 `--guard-source present ⇒ create_all_calls 1→0` + `--strict-current-guard` |
| N-5 | 见 §6.1（**本轮消除**） | ~~`not_counted_as_passed`~~ → **已消除** | 达成（t4 + t7/t10 工具面） |
| N-6 | `scripts/_remediate_b13_02_audit_log.py --apply` 仅**副本**验证过 | `not_counted_as_passed` | 与 N-1 同一次放行（真库执行后回填读数） |
| N-7 | `G-19`（C-06 写端点 deny 未断言）/`G-21`（37 条「GET+写」多方法规则未命中）：`81-…md:785/:787` 逐条 **`not_covered`** | `not_covered` | 同一工具内加方法参数化 face（**不得新起并行工具**） |
| N-8 | `P11` **部分关闭** / `P12` 已重指（按 §B18-C-06 冻结后复核四条留档） | `P11` 部分关闭 / `P12` 已重指（**不折算 pass**） | 按 §B18-C-06 C 四条一并留档 |

**b) 复核件 §5 残余风险 R-1…R-10**（本件抽核 3 条 + 引用其余）

| # | 本件抽核 | 状态 |
| --- | --- | --- |
| R-1 | `scripts/check_doc_claims.py:158` 钉 `('routes_py_lines', (12806, …))`；`wc -l app/main/routes.py` = **12806** ⇒ 现值相等、未漂，但锚定**工作树**行数 ⇒ 任何未提交改动会再打漂 | **在册**（移动靶；改一次走 A-70 三步，**不得**改工作树迁就钉值） |
| R-2 | 三处英文枚举模板项：本批 t2 已修（4 处裸渲染中文化，`git diff` 实证：`order_detail.html:5/:29`、`requisitions.html:21`、`orders.html:42`）+ t5 非作者验证（改前 19/19 红 → 改后 19/19 绿、NC-1/NC-2 转红） | **本批关闭（实现+验证齐）**；`search/global_search.html:357/:405` 经 §B18-D-01 裁决① 判为**显式中文分支链、无缺口** |
| R-3 | `quality/tasks.html getStatusName` 缺 `cancelled`：本批 t2 已补（diff 实证 `+ 'cancelled': '已取消'`），`failed` 键保留备查；筛选下拉按 §B18-D-04 **有意不动** | **本批关闭（实现+验证齐）**；下拉缺项已按裁决**不在册** |
| R-4…R-10 | 未在本件重判，引用复核件 §5 原状态（R-4 P11/P12、R-5 `G-1…G-22`、R-6 B13-02、R-7 未跟踪遗留、R-8 V-12 harness、R-9 构建层、R-10 取价全库等价） | R-8/R-10 对应 N-2/N-5 **已消除**（§6.1）；R-4/R-5/R-6/R-7/R-9 **在册** |

**c) 本批新增在册 N-D1…N-D6**（§B18-D-01:550-556 / §B18-D-02:601-605）

| # | 项 | 状态 token | 解除条件 |
| --- | --- | --- | --- |
| N-D1 | `V-13` 证据载体缺失（`evidence/harness/r2-v13-tl050607/`、`ci-v13-gate/ci_gates.json`、`coverage.json` 三者 MISSING） | `not_counted_as_passed` | 重跑 TL-05/06/07 出件，或按 `.tmp/r2t14/v13_evidence_index.json` 重建载体 |
| N-D2 | `V-14` 载体目录缺失（`evidence/regression-r2/` 不存在；唯一台账钉旧锚 `F5DA2306…`） | `not_counted_as_passed` | 以现锚 `B4FB980C…` 重跑并落正式载体 |
| N-D3 | N-5 真库比对判别力为零 | `not_counted_as_passed` | 合成夹具四场景 + 阴性对照转红（**已达成** ⇒ 见 §6.1；本条作口径留痕，不重复计分） |
| N-D4 | `70-第2轮收口与阶段C移交.md:439/:442` 两处读数过期（真库钉值 / evidence 计数 13209） | `not_counted_as_passed` | 引用一律改用 `B4FB980C…` + 时点；后续**追加**订正（不删原文） |
| N-D5 | 真库取价面**不可测**（多版本码 / `is_current=0` / 未来价样本数均 0） | `not_counted_as_passed` | 真库首现此类样本后按 C1 复跑 |
| N-D6 | 新口径 **4 个调用点运行面**未测（`app/main/routes.py:2960`/`:4174`/`:4294`、`app/utils/excel_generator.py:902`） | `not_measured` | 调用点级回归 |

**d) t10 / t11 余项**

| # | 项 | 状态 token | 解除条件 |
| --- | --- | --- | --- |
| t10-R1 | 旧件「断言失败仍 exit 0」的**动态**复现未行使（v2 已动态证明） | `not_counted_as_passed` | 若需动态证据：在副本上复现旧件红 run 的 rc（**不得改动冻结件**） |
| t10-R2 | 作者 RUN 产物**未逐字节重放**（防覆盖 `ABORT` 是设计行为；36/36 字段比对为等价替代） | `not_counted_as_passed` | 以新 RUN_ID 全量重跑并与旧 JSON 做字段级 diff |
| **t11-R1** | t9 退出码语义的逐条正式验收 | ~~在册~~ → **本件 §3 正式计分 ⇒ 解除** | **达成**（红 1 / 同扰动旧行 0 / 绿 0） |
| t11-R2 | `.tmp/_env.py`（旧锚副本）影射陷阱 | `not_counted_as_passed`（captain 已裁**不删除、定为纪律**，§B18-D-08） | 清理/改名该文件（须走 A-70 面），或**所有复跑一律显式 `PYTHONPATH`**（本件已遵从，§9） |

### §6.3 守门结论

- 逐条核对 `B18-登记.md`（现 783 行）+ 复核件 §5/§7：**没有任何一条 `blocked` / `not_measured` / `not_covered` / `not_counted_as_passed` 被写成 pass**；全文亦无「已清零 / 全部解除」类表述（`grep -n "已清零\|全部解除\|清零"` = 0 命中）。
- 状态 token 计数（本件认定）：**已消除 2**（N-2、N-5）+ **t11-R1 解除 1**；**保留在册 24 条**（N-1/N-3/N-4/N-6/N-7/N-8 = 6；R-1/R-4/R-5/R-6/R-7/R-9 = 6；N-D1…N-D6 = 6（N-D3 作口径留痕）；t10-R1/R2 + t11-R2 = 3；另 R-2/R-3/R-8/R-10 已随 N-2/N-5 消除而关闭）。
- **未折算项**：`blocked>0` 分支运行面（§3）、`evidence_hash` 时点差异（§1）、`new_checks` 42/43（§4）均**不折算 pass**。

## §7 必核 4：本轮提交清单（逐条 `git add` 白名单）

**A. 建议入库（9 项 = 6 `M` + 3 `??`）** —— 逐条执行，**禁用** `git add -A` / `git add .`：

```
git add app/templates/main/purchase/order_detail.html
git add app/templates/main/purchase/orders.html
git add app/templates/main/purchase/requisitions.html
git add app/templates/main/quality/tasks.html
git add test-reports-2026-10/harness/uat_chains.py
git add test-reports-2026-10/B18-登记.md
git add test-reports-2026-10/D-落点与在册项盘点.md
git add test-reports-2026-10/D-集成复核.md
git add test-reports-2026-10/subagent-routing.md      # ← 非 D 组产物，见下注
```

> 注（`subagent-routing.md`）：该件是 `/root/.dsh/profiles/web/cordis.patch.yml` 路由规则的**仓库内同步副本**（其自身标题即声明"改动 profile 后请把本件一并更新"），**非本任务产物**。**建议入库**，但**最终归 captain/用户裁定**；若不入库，则应移出工作树（否则长期以 `??` 形态污染 `git status` 复核读数）。

**B. 禁止入库（6 路径 = §B18-C-06 B 既有 4 项 + 本批新增 2 项 scratch）**：

| 路径 | 实测 | 处置 |
| --- | --- | --- |
| `app.db.evidence-ALLOY-IMPORT-02-20261009_004539` | `git check-ignore` 无输出（rc=1） | **不 add**（用户裁决是否清理） |
| `instance/`（`instance/app.db` 0 B） | rc=1 | **不 add** |
| `.vscode/settings.json` | rc=1 | **不 add** |
| `.tmp/` | rc=1 | **不 add**（A-70 留档与探针中转） |
| **`test-reports-2026-10/.tmp-t9runs/`**（本批新增） | rc=1（**不忽略**） | **不 add**（t9 红副本留存供复跑；scratch，非交付） |
| **`test-reports-2026-10/.tmp-t6runs/`**（本批新增） | rc=1（**不忽略**） | **不 add**（本件红副本留存供复跑） |

> 本批**不新增** `.gitignore` 规则（会打漂 `gitignore_lines`=56 ⇒ 需再走一轮 A-70）；上列 6 项用**选择性 `git add`** 处理。

**C. `evidence/` 是否入库 —— 判定：不入库**。`git check-ignore -v test-reports-2026-10/evidence/d/` 命中 **`.gitignore:42` = `/test-reports-2026-10/evidence/`**；`git ls-files test-reports-2026-10/evidence/` 为空（与 §B18-C-07:507 一致）⇒ 本轮全部判据件（`evidence/d/**`、`evidence/uat/**`、`evidence/harness/**`）**只存在于工作树**，提交清单**不含**任何 `evidence/` 路径。

**D. 提交后冻结复核四条（顺序不可换）**：① `ci_gates.py --phase first` ⇒ `steps=20 / 无失败 / exit 0` ② `check_doc_claims.py --selftest` ⇒ `26/26` ③ `sha256sum app.db` 三值 ④ `git status --porcelain` 复核（应只剩上表 B 的 6 项）。

## §8 必核 5：残余风险（至少覆盖三条）

1. **R-1 `routes_py_lines` 移动靶**：钉值 `12806` 锚定**工作树**行数；本轮 D 组未改 `app/main/routes.py` ⇒ 现值相等（§6.2b）。任何后续未提交改动会**立刻**把 `check_doc_claims` 打红 ⇒ 必须走 **A-70 三步**重基线，**不得**改工作树迁就钉值。
2. **真库锚点重设的前置**：N-1/N-6 的真库 10 行写入（`id=[7,8,12,15,24,29,40,44,68,73]`）**一旦执行**，`app.db` sha256/bytes 变化 ⇒ 连带 `scripts/check_doc_claims.py` 的 `real_db_sha256`/`real_db_bytes` 两个钉值 + 多份文档（`70-:439`、AGENTS.md 等）⇒ 又是**一轮 A-70**；执行前必须由用户裁决（§B18-C-06 D、§B18-C-08 处置段）。
3. **`G-1…G-22` 未处置面**：与本阶段直接相关的开放项 —— `G-8` = `A-63-STEP2-BUILD-GATE` **`blocked`**（本件 §1 gates gaps 行实读）；`G-4` = `B17-02 ≡ C-07` **`blocked(生产面冻结)`**；`G-19` / `G-21` = **`not_covered`**（同一工具内加方法参数化 face，不得新起并行工具）。
4. **不利因素面（供下批）**：`evidence/` 被 `.gitignore:42` 整树忽略 ⇒ 所有判据件**只在工作树**，工作树损坏即判据证据丢失；`evidence/` 计数已从 13209 裁到 1974（N-D1/N-D2 根源）。
5. **可复现性**：`.tmp/_env.py` 旧锚影射（§9）+ 活产物重写（§10）是**两位独立见证人**踩过的同型陷阱 ⇒ 一律按 §9/§10 口径复跑与引用。

## §9 追加必核 ④：复跑前提（可复现性陷阱）

- **事实**：`harness/uat_chains.py:56` = `sys.path.insert(0, HERE)`（`HERE` = 脚本所在目录）。若把该脚本 `cp` 到 `test-reports-2026-10/.tmp/` 下运行，会优先 import **同目录** `_env.py` —— 那是 B15 重锚**前**的旧副本（`:48` 钉旧锚 `F5DA2306…`），而与正本 `harness/_env.py:94`（钉 `B4FB980C…`）不同源 ⇒ 脚本**死在真库钉值闸**（打印期望/实测两值），其 `exit 1` **不是判据读数**。
- **依据**：§B18-D-08（captain 裁决：**不删除、定为纪律**）；两位独立见证人（impl-harness 首轮两次副本 run、verify-d1 一次）。
- **本件遵守方式（可复核）**：红/阴副本落 `test-reports-2026-10/.tmp-t6runs/`（**干净同层目录**，非 `.tmp/`），并显式 `PYTHONPATH=test-reports-2026-10/harness`；绿态直接用**现盘文件原样 in place**（`HERE` = `harness/` ⇒ 解析正本）。三联 run 结果为 `1 / 0 / 0`，**无一条来自钉值闸异常路径**（红态有 `[FAIL] APPEND.1` 判据行 + `failed=1` 摘要 + run 产物 JSON，可反查）。
- **纪律（并入收口清单）**：`harness/` 下脚本的一切复跑 ⇒ 干净同层目录或空目录 + 显式 `PYTHONPATH=harness`。

## §10 追加必核 ⑥：`evidence/d/` 活产物清单（引用必须带**时点 + sha256**）

**口径**：活产物 = 会被后续运行**重写/追加**的件；不可变件 = 只在生成时写一次（引用仍建议带 sha256）。

### A. 活产物（**会被后续运行改动**）

| 件（`test-reports-2026-10/…`） | 谁在改 | 现读 sha256 | 大小 / 时点 |
| --- | --- | --- | --- |
| `evidence/uat/uat_chains.json` | **每次 uat run 重写**（硬编码 live 路径，`--out` 无效，§B18-D-05） | `1017e02d5bc634eb3e29db2f8714fd14ba579d8d6a6bc6e4b6683eedc821c18b` | 128127 B / `2026-10-11 15:14`（= 本件绿态 run） |
| `evidence/uat/uat_chains.out.txt` | 同上 | `9e6910f714dc7c6b8c208e1f75f1696b24aa2ff2132542da2b356d6544bc6788` | 41848 B / 15:14 |
| `evidence/d/t7-N5-工具修复-登记.md` | `t4_n5_recompute_v2.py`（`REPORT` 常量 = 该件）+ `t4_n5_recompute.py` **每次运行 append** | `d1f2ecde5d1ce06579d2…`（全值见 §11 索引） | 16499 B / `14:53`（v2 自 14:53 后未跑过） |
| `evidence/d/t4-N5-登记.md` | `t4_n5_recompute.py`（v1）append | `2c7f31808df82df24d87…` | 13726 B / `14:31` |
| `evidence/d/t5-enum-*.json`（7 件）、`t10-verify-*.json`（4 件）、`t11-canonical-blob-*.json`（8 件） | 各自探针脚本**固定文件名重写** | 见 §11 索引 | 均 ≤ 13 KB，14:31–15:10 |
| `evidence/harness/ci-run-*/`、`evidence/harness/uat/<RUN_ID>/` | **每次 run 新建目录**（不覆盖旧目录） | 目录级：本件 3 个 `t6-*` + `ci-run-20261011-151232` | 15:12–15:14 |
| `test-reports-2026-10/.tmp/`、`.tmp-t6runs/`、`.tmp-t9runs/` | 复跑中转（**不入库**） | 见 §7 B | — |

**示范形态（沿用 t11 做法）**：引用活产物时给「快照件 + 快照前后 sha」——如 `t11-live-uat_chains-{BEFORE,AFTER}.json`（`40a9a551…` → `3571afa3…`）+ 对应 `.out.txt`。本件对应的快照 = §3 三份 `t6-*.console.txt` 与三个 `evidence/harness/uat/t6-*/` run 目录。

### B. 不可变（生成后未再改；本件引用值）

`t5-验证登记.md` `c2cffcf056214441fff1…`（8408 B/15:05）· `t11-t8-重基线复核.md` `4afb94da4a3eaee8891e…`（19093 B/15:11）· `t10-N5-退出码复核登记.md` `1c3af423ce95f3b01f8a…`（11067 B/15:03）· `t9-退出码-登记.md` `99c8fc5d0688bfdb0b8a…`（7228 B/15:11）· `t8-A70-重基线-登记.md` `b55cf14c689e57c30605…`（3522 B/15:02）· `t7-N5-工具修复-登记.md`（**同时是活产物，见 A**）· `t4_n5_recompute_v2.py` `1437027eb56e4989541c…`（27914 B/14:50）· `t4_n5_recompute.py` `c5837d471aedd7fdae4a…`（24224 B/14:30）· `t4_n5_crosscheck.py` `312baf978ee588da060f…`（4994 B/14:30）· `t5-enum-probe.py` `d51a2f3c25f528eb7811…`（12599 B/15:05）· `t2-enum-zh-20261011.py` `013f19416b7d8de079e5…`（15619 B/14:46）· `t3-N2-CA4a-订正登记.md` `1397a23edef50c8d81ad…`（11701 B/14:42）。

## §11 证据索引与边界声明

**本件新增产物**（工作树，`evidence/` ⇒ 不入库）：

| 件 | sha256 | 大小 / 时点 |
| --- | --- | --- |
| `evidence/d/t6-green.console.txt` | `ef47fd0aff599301010736501bf1d4a567f6cb6f827c63cae3f8882d5bf3f5bb` | 66920 B / 15:14 |
| `evidence/d/t6-red-new.console.txt` | `dd33a67a11f498b1d806ba5459171622eae5c7110c69f50fabf96ce57a911b87` | 67999 B / 15:14 |
| `evidence/d/t6-red-old.console.txt` | `5c36d1f2d3fe9efdbb18a4cac52522009445585c0af29a3e6e9279b40e90170e` | 67999 B / 15:14 |
| `evidence/harness/uat/t6-{red-new-151419,red-old-151424,green-151429}/` | 各含 7 件（`*-chains.json`/`-flips.json`/`-ledger.json`/`-ledger.md`/`-append-only.json`/`-v12-observations.json`/`evidence_journal.jsonl`） | 15:14 |
| `evidence/harness/ci-run-20261011-151232/` | `gates.json` `62dd99f89775d9dd0d62…`、`ci_gates_first.console.txt` `188edbe0d1c34455c50e…` | 15:12–15:13 |
| `.tmp-t6runs/t6-red-{new,old}-uat_chains.py` | `8d514df1…772d8` / `755a20d9…19a51` | 198211 / 198185 B |

**边界**：本件复核者**未改**任何实现代码、模板、`scripts/`、`harness/`；未跑 `flask db *`；真库只读（唯一一次 `mode=ro` 查询）并三值逐位复核；未改写任何 task 终态；**零阻塞 finding**；`push` 由人工决定。

**复现命令**（逐条可执行）：

```
/opt/wage-venv/bin/python -B test-reports-2026-10/harness/ci_gates.py --phase first
/opt/wage-venv/bin/python -B scripts/check_doc_claims.py --selftest
sha256sum app.db && stat -c '%s %y' app.db && git status --porcelain
git diff -U0 -- test-reports-2026-10/harness/uat_chains.py | grep -c '^@@'            # 15
diff -U0 test-reports-2026-10/.tmp/t8-pre-uat_chains.py test-reports-2026-10/harness/uat_chains.py | grep -c '^@@'   # 4
cd /root/code/MyERP && PYTHONPATH=test-reports-2026-10/harness UAT_RUN_ID=... \
  /opt/wage-venv/bin/python -B test-reports-2026-10/harness/uat_chains.py            # 绿 ⇒ exit 0
```
