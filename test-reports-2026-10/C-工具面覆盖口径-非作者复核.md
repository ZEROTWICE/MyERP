# C · t6 非作者复核（G-19 写端点 deny face / G-21 多方法规则覆盖口径）

- 任务：t13（kind=review, round 1）；复核对象 = t6（attempt 3 `0963f005-626d-4579-a6f1-a90205245701`，作者 `impl-p1`）。
- 复核者：`gov-assets`（attempt 1 `0ba08b14-2697-45bf-b42d-44e316dc1fc0`）——**非作者**（C9）。
- 现场：HEAD `9f28baa`；解释器 `/opt/wage-venv/bin/python`（3.11.2）；时点 2026-10-12 05:35–06:05 UTC。
- 真库只读复核（开工 05:35 / 收工 06:03 各一次，恒等）：sha256 `34e48e7a21163db390eebda4f2030343f3609afedc65d8c6e909d6eb5a49177e` / `2531328 B` / mtime `2026-10-12 04:25:37.128430119 +0000`。
- 只读性：本复核**未改任何受跟踪文件**、未 `git add`/commit/push、未跑 `flask db *`、未追改 `evidence/**`。全部请求型实验经 `scripts/_sandbox_compat.py` + 工具的副本库自举（不改真库）。
- 复核方法：不复述 t6 自述，全部读数由本复核**独立重跑**取得；t6 交付件（`test-reports-2026-10/C-工具面覆盖口径.md`）按只读引用。

## §0 结论

**verdict = `needs_revision`**（2 条 findings：F-01 值不可复现 / F-02 行号帧错标）。

核心机制**全部独立复现通过**：写面确在既有工具内、方法轴真实存在、allow/deny 两侧实测成立、注入阴性对照定向转红且可恢复、21 端点台账与 `write_expect` 对拍一致、G-21 的 N/M 与该**判据层钉值**（`coverage_drift.py` D-9）现场一致且绿、门禁 blocking 全绿且 `permission_matrix` 步 checks 数与改动前逐字相同、PINNED/needle 未触碰。
⇒ 两条 findings 均为**交付件内被要求登记的「值/位置」不准确**，**不影响** G-19/G-21 的机制与结论；修正面限于文档。

### t6 验收项逐条判定

| # | 验收项（t6 任务书原文摘要） | 判定 | 证据 |
| --- | --- | --- | --- |
| 1 | G-19 写端点 face 在**同一工具**内实现 + `--help`/参数面 + 逐入口 allow+deny + 角色集取自 `app.permissions.roles_for`（不得手写角色名列表） | **passed** | §1/§2/§4：同一文件 `scripts/permission_matrix.py`（全仓唯一）；`--help` 见 `--inject-write-module`；21 端点 allow+deny 实测；`deny_roles_for()` 派生；diff 删除 4 处手写元组 |
| 2 | G-19 阴性对照：改坏期望 ⇒ 断言转红 + 恢复绿 | **passed** | §3：我独立三轮（绿 0 → 注入红 1 → 恢复绿 0），注入**定向**（仅写面红、页面面仍绿） |
| 3 | `ci_gates.py --phase first` exit 0 | **failed（如实，非 t6 缺陷）** | §6：`steps=20 / blocking 失败=无` 但 `exit=2`；唯一来源 = **report-only** `evidence_hash` 先在性红（非 t6 引入、t6 已归因 + 解除条件、**不折算 pass**，见 §9） |
| 4 | G-21 逐类「纳入 / 显式不纳入 + 理由 / 留档待决」成文，不得只给结论数字 | **passed（含 F-01）** | §5：1+13+24=38 逐类成文；本复核抽样与批量复算大体相符；**唯 1 处值错（F-01）** |
| 5 | 纪律：未改 `check_doc_claims.py` PINNED 与 `ci_gates.py` needle | **passed** | §7：四处 diff 全 clean |

## §1 G-19 —— face 确在**既有工具内**，且为真方法轴

**工具唯一性（口径：仓库索引）**：
- `git ls-files | grep -i permission_matrix` ⇒ 仅 `scripts/permission_matrix.py`（**779 行 / 45805 B**，sha256 `73c329f8647883c33de13676baac6c5c78790931e6ca51f19c2f3ed8e794e4f7`）⇒ 未新起并行工具。

**载体（口径：现场 `grep -n`，行号为本复核实测）**：

| 组件 | 现场行号 | 取证件 |
| --- | --- | --- |
| 写端点**派生** | `scripts/permission_matrix.py:448` `def write_endpoints(app, guards, capability)` | `:449` docstring「**派生**该能力面的写端点（不手抄路径表）：`url_map` 里有写方法 + 该视图函数挂了该能力」 |
| 方法轴（本 item 核心） | `:456` | `methods = sorted(rule.methods - {'GET', 'HEAD', 'OPTIONS'})`；`:457-458` `if not methods: continue`（只取写方法） |
| 派生来源 | `:453` | `for rule in app.url_map.iter_rules():` ⇒ **非手抄路径表** |
| 方法透传到执行口径 | `:496` | `classify(c, url, method=method, data=data)` ⇒ 与页面面**同一 `classify()` 口径** |
| 写面判据 | `:477` `def run_write_face(...)` | `:490 deny_roles = deny_roles_for(spec['capability'])`；`:501 deny = [r for r in deny_roles if row[r] == 'DENY']` |
| 注入执行 | `:666` `if inject_write_module:` | 副本进程内摘 `@require_capability`（不改生产代码） |
| 退出码计入 | `:713` | `code = 1 if (anon_open or face_failures or write_failures or ir_failed) else 0` ⇒ 写面失败**真的**影响退出码 |

**`--help` 读数**（验收项 1 点名要求；命令见 §8.3，exit=0）：

```
usage: permission_matrix.py [-h] [--out OUT] [--no-dump]
                            [--out-modules OUT_MODULES]
                            [--inject-module INJECT_MODULE]
                            [--inject-write-module INJECT_WRITE_MODULE]
  --inject-write-module INJECT_WRITE_MODULE
                        注入回放（B17-13）：副本进程内移除该模块**首个写端点**的
                        @require_capability ⇒ 写面 deny 断言必须转红（不改生产代码）
```

**载体沿革（如实登记，非缺陷）**：`--inject-write-module` 与其说明均自述 **(B17-13)** ⇒ 写面**已在 HEAD 落地**，t6 §1.1 对此如实自述（「face 现状（HEAD 已落地 B17-13，本轮实测）」）。故验收项 1 的「**新增**的写端点 face / 新增参数」在本轮属**已存在物**：t6 未新增 face/参数，其本轮实际贡献 = 角色集合规化（§4）+ 独立读数；验收项 1 按**实质**（face 在既有工具内、方法轴、角色派生）判 passed。

## §2 G-19 阳性读数（我独立重跑）

命令见 §8.1，**exit=0**：

```
[OK] 匿名可访问 = 0
[OK] C-06 四模块权限面 = 全绿（4 模块 allow + deny + 5xx=0）
[OK] C-06 四模块写端点面 = 全绿（21 写端点：逐端点 ≥1 allow + ≥1 deny，5xx/EXC=0）
[OK] 内联 role ≤ 白名单 = 全绿（扫描 16 条 == 白名单 16 条，按 (file, 文本) 出现次数逐一相等、双向无漏斗；行号漂移 9 处仅 WARN）
[e03] inputs: {"routes_tested": 146, "c06_modules_failed": [], "c06_write_modules_failed": [], "code": 0}
```

**逐端点两侧抽样（口径：stdout 的 allow/deny 列）**：

| 端点 | allow（能力允许角色） | deny（派生 deny 集） | 5xx/EXC |
| --- | --- | --- | --- |
| `POST /shipments/create` | `admin,manager,sales` | `hr,accountant,inspector,user` | 无 |
| `POST /shipments/<int:id>/ship` | `admin,manager,sales` | `hr,accountant,inspector,user` | 无 |
| `POST /shipments/<int:id>/sign` | `admin,manager,sales` | `hr,accountant,inspector,user` | 无 |
| `stock`（`inventory.view`） | `-` | `-` | 无（台账 `write_expect=0` ⇒ 只声明「无写端点」，非静默跳过） |

**台账对拍（口径：stdout 逐模块行，本复核实测）**：

```
  [OK  ] equipment       cap=equipment.manage     写端点=9/9  allow≥1=admin,manager  deny≥1=hr,accountant,inspector,sales,user  5xx/EXC=无
  [OK  ] purchase_orders cap=purchase.manage      写端点=8/8  allow≥1=admin,manager  deny≥1=hr,accountant,inspector,sales,user  5xx/EXC=无
  [OK  ] shipments       cap=shipment.manage      写端点=4/4  allow≥1=admin,manager,sales  deny≥1=hr,accountant,inspector,user  5xx/EXC=无
  [OK  ] stock           cap=inventory.view       写端点=0/0  allow≥1=-  deny≥1=-  5xx/EXC=无
```

⇒ equipment **9/9**、purchase_orders **8/8**、shipments **4/4**、stock **0/0** = 合计 **21 写端点**，与 §2 汇总行一致；`:518` 的模块级判据另含「写端点数 == `write_expect`（**上下漂移都红**）」⇒ 防 face 静默缩小（stock 的 `0/0` 即该台账的显式声明，非静默跳过）。

## §3 G-19 阴性对照（我独立三轮，A-70 第②③步口径）

| 轮 | 命令 | 关键读数 | 退出码 |
| --- | --- | --- | --- |
| A 阳性 | §8.1 | `[OK] C-06 四模块写端点面 = 全绿（21 写端点…）` | **0** |
| B 注入 | §8.2 | `[FAIL] C-06 四模块**写端点**面失败：equipment`；`c06_write_modules_failed=["equipment"]`；`c06_write_injected="equipment"`；`[INJECT] 靶向性 = 其它三模块写面仍全绿: ['purchase_orders','shipments','stock']` | **1** |
| C 恢复 | §8.1 | 同 A，写面回到 21 端点全绿 | **0** |

**定向性（本对照的关键）**：B 轮里**页面面判据仍绿**（同轮输出 `[OK] C-06 四模块权限面 = 全绿`），只有写面转红 ⇒ 写面**独立可证伪**、未被页面面掩盖，注释所称「逐端点层才行、模块级只看 ≥1 会掩盖」的机制成立。
**A-70 适用性**：本轮**无判据/钉值/期望值改动**（判据仍是「≥1 allow + ≥1 deny」；PINNED/needle 未动）⇒ 无「改值」对象，A-70 第①步无留档需求；第②③步（阴性对照转红 + 恢复绿）**照做并实测**如上。

## §4 角色集合规：`deny_roles_for()` 派生（不再手写）

- 实现（现场 `scripts/permission_matrix.py:383-389`）：`:387 from app.permissions import ROLES as APP_ROLES, roles_for`；`:388 allow = set(roles_for(capability))`；`:389 return tuple(r for r, _label in APP_ROLES if r not in allow)` ⇒ `deny = 全角色表 − roles_for(cap)`，页面面（`:406`）与写面（`:490`）**共用**。
- 改动面（口径：`git diff --numstat`）⇒ `28 18`，与 t6 自述 **+28/−18 逐字相符**；diff 内容 = 删除 `MODULE_FACE` 4 处手写 `deny_sample` 元组 + 新增 `deny_roles_for()` + 6 处引用改派生值（落盘 JSON 键名保留，形状兼容）。
- **等价性**（口径：`app.permissions.ROLES` 与 `roles_for` 的真实取值，非 t6 自述）：`ROLES` 共 7 个（`admin/manager/hr/accountant/inspector/sales/user`）——
  - `equipment.manage` / `purchase.manage`（allow=`admin,manager`）⇒ deny={hr,accountant,inspector,sales,user}（5）
  - `shipment.manage`（allow=`admin,manager,sales`）⇒ deny={hr,accountant,inspector,user}（4）
  - `inventory.view` ⇒ 同 equipment
  与 diff 中**被删除的原手写元组逐条相等** ⇒ **合规性重构**（输出逐字不变），非判据放宽。§2 实测 deny 列 = 上述派生集，佐证等价。

## §5 G-21 多方法规则覆盖口径

### 5.1 N/M 现场读数与**判据层**钉值（本复核最重要的一节）

| 量 | 值 | 工具 + 口径 |
| --- | --- | --- |
| N（GET+写 多方法规则总数） | **44** | `scripts/route_inventory.py` ⇒ `[routes] total rules=273` / `[multi] GET+写 多方法规则=44`；本复核另以 `grep -c '^  MULTI '` 独立计数 = **44** ✅ |
| M（其中未被任何探针命中） | **38** | `coverage.json` 顶层 `uncovered_multi_method_with_get`，`len` = **38**（`summary.multi_method_with_get_uncovered=38`） |
| 判据层（**这是钉值**） | `N==44 / M==38 / len==38 / M<=N` | `test-reports-2026-10/harness/coverage_drift.py:20` **D-9** |

**D-9 实跑裁定**（§8.4，`--coverage` 传本 run 产物）⇒ **`[OK] D-9 … 实际=N=44 M=38 len(list)=38`**，脚本结论 `判据 7/8 通过；另 D-9 多方法面判据 OK => exit 0`（`exit=0`）。
⇒ **结论：t6 引用的 44/38 不是自创口径，而是判据层钉值本身的现场一致读数**（且该判据当前为绿）。

**演进链与 A-70**（口径：D-9 单元格自载注释）：`SEC-CSRF-01`（43/37→**44/38**）→ `e057e81` 删 GET+POST 的 `/auth/register`（44/38→43/37）→ `B18-Q1` 增 `/auth/change-password`（43/37→**44/38**）。每次变更均有「有意更新」留档；本复核确认 **t6 本轮未改动该判据**（`coverage_drift.py` diff clean，§7）⇒ 不存在「未走 A-70 就改钉值」的情形。

**与任务书「37 条」的差异（登记，不追改历史件）**：37 = `70-` 文档时点（RL-01 帧）的 M 值；按上述演进链，现场 M=38、N=44。任务书该数字**陈旧**，t6 按现场读数分类并显式说明锚点对账，处理正确。
**与 `run_gates.py` 钉值的关系**：`test-reports-2026-10/harness/run_gates.py:50` `'routes_total_rules': 273` —— 与 G-21 的 N/M **不同量纲、不冲突**（273 = 全部规则数，44 = 其中多方法规则数）。
**量纲警示（沿 t6，我复核成立）**：38（多方法规则面未命中）**≠** `scripts/check_doc_claims.py:123` 的 `non_get_uncovered_method_level = 40`（方法级非 GET 未命中）⇒ 二者**不得互替**。

### 5.2 逐类处置口径（验收项 4：不得只给结论数字）

t6 §2.2 给出 **1 + 13 + 24 = 38** 三类，逐类带规则清单与理由；另有「探针已命中 6 条」对账（44−38=6）。本复核抽样复算：

| 抽样 | t6 声称 | 我实测（口径：def 块机械扫描，见 §8.5） | 判定 |
| --- | --- | --- | --- |
| ② `view_audit_logs` | `routes.py:2033-2069`，adds=0/commits=0 | `:2033-2069`，**0/0** | ✅ 逐字相符 |
| ② `manage_bonus_penalties` | `:1649-1755`，0/0 | `:1649-1755`，**0/0** | ✅ |
| ② `salary_calculation` | `:1896-2032`，0/0 | `:1896-2032`，**0/0** | ✅ |
| ② `advanced_search` | `:3150-3258`，0/0 | `:3150-3258`，**0/0** | ✅ |
| ③ `add_employee` | adds=3/commits=1 | **3/1** | ✅ 逐字相符 |
| ③ `/tasks`（`manage_tasks`） | `routes.py:3345-3532`，adds=2/commits=2 | `:3345-3532`，**2/2** | ✅ 逐字相符 |
| ③ `consumable_inbound` | adds=16/commits=12 | **2/1** | ❌ **F-01** |
| ③ 更新型 `assemble_product` | `stock.py:36-71`，0 add/1 commit = UPDATE 型 | `stock.py:36-76`，**0/1** | ✅ 相符（含 UPDATE 型定性） |

**类别结论的独立批量复算**：对 t6 §2.2③ 所列 24 条逐条扫描 ⇒ **23 条**满足 `adds≥1 ∧ commits≥1`；唯一例外是 `assemble_product`（0 add / 1 commit），而 t6 **已主动登记为 UPDATE 型** ⇒ 「24 条均为真写侧」的**分类结论成立**，F-01 仅是其中一条示例数字错。
**② 类的判据语义（复核成立）**：`coverage.json` 的 `uncovered_multi_method_with_get` 定义为 `'GET' in methods and methods != ['GET']`（`measure_coverage.py:495-496`）⇒ 它是**探针字面量口径**下的「未命中」，与**执法面**（`permission_matrix` 写面）不是同一物：`/equipment/<int:id>/layout` 即「探针未命中但已被 C-06 写面执法」的实例（t6 §2.2① 的定性正确）。

## §6 回归核对（验收项 3 的可控部分）

- 命令 §8.6；run 目录 `test-reports-2026-10/evidence/harness/ci-run-20261012-055431/`；产品 `ci_gates_first.console.txt`。
- 汇总（逐字）：`steps=20` / **`blocking 失败 = 无`** / `report-only 失败 = ['evidence_hash']` / `注入未生效 = 无` / `仓库根两 JSON 未被触碰 = True（A-11）` / `exit = 2`；`exit_code_semantics` 明载 `2 = 仅 report-only 失败`。
- **`permission_matrix` 步与改动前对照**：本轮 `permission_matrix group=blocking exit=0 checks 3/3`；改动前基线（t10 轮 run `ci-run-20261012-053155`，05:31:55，**早于** t6 的 05:44 改动）同为 `exit=0 checks 3/3` ⇒ **checks 数逐字相同**，未放宽判据、未减少断言；t6 自测的 `ci-run-20261012-054655` 亦为 `3/3`（三帧一致）。
- **未把「本步转绿」建立在放宽 blocking 判据上**：另见 §7（PINNED/needle/`coverage_drift.py` 均未改）。
- `evidence_hash` 明细（我读 `ci-run-20261012-055431/evidence_hash.gate.json`）：`verdict=violation`、`counts.modified=2 / deleted=0`，两条 = `harness/b17-verify/probe_permission_matrix.txt`、`harness/b17-verify/probe_smoke_test.txt` ⇒ 与 t4/t6 轮**同一对先在性违规**，**t6 未引入新违规**。（其余增长项 `current_files`、`added`、`index_missing` 由各线不断新增 run 目录所致，非 t6。）

## §7 纪律核对（验收项 5，我独立查）

| 受查文件 | 口径 | 结果 |
| --- | --- | --- |
| `scripts/check_doc_claims.py`（PINNED） | `git diff --numstat` | **clean** ✅ |
| `test-reports-2026-10/harness/ci_gates.py`（needle/步骤定义） | 同上 | **clean** ✅ |
| `test-reports-2026-10/harness/run_gates.py`（`EXPECTED` 钉值） | 同上 | **clean** ✅ |
| `test-reports-2026-10/harness/coverage_drift.py`（D-9 判据） | 同上 | **clean** ✅ |
| `docs/**` | `git status --porcelain` 无 docs 行 | 未动 ✅ |

t6 改动面（`git status --porcelain`）：` M scripts/permission_matrix.py`（`28 18`）+ 交付件 `C-工具面覆盖口径.md`（`??` 未暂存）⇒ 与 t6 自述「无 `git add`/commit/push」一致。
**非 t6 的同工作区改动**（登记以免误归因）：`M  test-reports-2026-10/harness/measure_coverage.py`（**已暂存**，属 t8 写盘守卫线：把 `:254` 裸 `open(ev,'w')` 改为 `_env.save_evidence()`，其注释自述 2026-10-12 04:45 `b17-verify/` 事件）+ ` M test-reports-2026-10/subagent-routing.md` + `A` 两份 `C-*.md`（他成员）。经核该改动**未触碰** `multi_method_with_get` 计数口径 ⇒ **不影响** §5 读数。

## §8 发现（findings）

### F-01（medium）—— `consumable_inbound` 的 add/commit 值不可复现

- 位置：`test-reports-2026-10/C-工具面覆盖口径.md:108`（§2.2③ 表单写 22 条行），原文「如 `add_employee` adds=3/commits=1、**`consumable_inbound` adds=16/commits=12**」。
- 实测（§8.5 同口径）：`consumable_inbound` def 块 `app/main/routes.py:11355-11425`，`db.session.add(` = **2**（`:11387`、`:11410`），`db.session.commit(` = **1**（`:11412`）。
- 排他：该块内**全部** `db.session.` 出现仅 **5** 处（2 add + 1 flush + 1 commit + 1 rollback），71 行 ⇒ 不存在任何计数口径能得到 16/12；且全仓 `app/main/*.py` **无任何** `adds=16` 的函数（我做了全文件 def 块扫描）⇒ 该数字**无出处**（非「抄错别的行」）。
- 影响面：**结论不受影响**——§2.2③ 的「24 条均为真写侧」经我独立批量复算成立（23/24 显式满足 `adds≥1 ∧ commits≥1`，例外 `assemble_product` 已由 t6 正确登记为 UPDATE 型）。但本件性质是**口径登记件**，其「值」列属硬约束⑥「证据 = 工具 + 口径 + 值」的组成，值不可复现即为缺陷。
- requiredFix：把该括号内数字改为实测 **`adds=2/commits=1`**，并在 §4 复跑命令里补一条可复算的扫描命令（口径需写明「def 块 = 该 def 至下一顶层 def」）。

### F-02（low）—— §1.1 表头「本轮实测行号」与实际帧不符

- 位置：`test-reports-2026-10/C-工具面覆盖口径.md:14-20`（§1.1 载体表）。
- 实测：8 行锚点中 **6 行**与现场（改动后工作区）不符，其中多数恰为 **HEAD 版（改动前）行号**：

| 表中声称 | HEAD 版实际 | 现场（改动后）实际 | 判定 |
| --- | --- | --- | --- |
| `:440` `def write_endpoints` | `:440` | **`:448`** | 标 HEAD 帧却称「本轮实测」 |
| `:587` 注入前派生清单 | `:587` | **`:597`** | 同上 |
| `:669-671` 执行+失败收集 | `:670` | **`:680-681`** | 同上 |
| `:691` 落盘 `write_summary` | `:691` | **`:701`** | 同上 |
| `:716` 汇总行 | `:712` | **`:722-723`** | 两端均不符 |
| `:535` `def print_write_face` | `:527` | **`:537`** | **两端均不符** |
| `:477` `def run_write_face` | `:469` | `:477` | ✅ 现场帧 |
| `:383` `def deny_roles_for` | — | `:383` | ✅ |

- 成因（推定，非借口）：t6 先量测后改码，其 +28/−18 落点位于这些锚点**之上**，改后未重锚。
- 影响面：定位需按**函数名**搜才准确；按行号读会落到无关代码（评审核对成本上升，且与本案「读数/现场一致」的战役主旨相悖）。
- requiredFix：§1.1 表全部**按改动后现场行号**重锚（上表右列），或明确加一列「帧（HEAD / 改动后）」；同步核对 §1.1 末行「退出码计入」所引位置。

### 观察项（非 findings，登记供 captain 处置）

- **O-1（复核任务书自身缺陷）**：t13 的 acceptance 把工具路径写作 `test-reports-2026-10/harness/permission_matrix.py`，**该路径不存在**；全仓唯一真实路径 = `scripts/permission_matrix.py`（`git ls-files` 佐证，且 t6 任务书 inScope 写的正是后者）。本复核已按真实路径完成取证，建议订正台账以免后续复核再次空跑。
- **O-2（同族陈旧判据，t6 范围外）**：`test-reports-2026-10/harness/b17_governance_contract.py:723-724` 仍断言 `multi_method_with_get_total == 43` 且 `_uncovered == 37`（B17 期值），现已被 D-9 的 **44/38** 取代 ⇒ 该契约若复跑必红。该契约**不在门禁链**（t2 已证 `grep -rn b17_governance_contract ci_gates.py run_gates.py scripts/` 零命中），属「提交前一次性」工具，故**无活影响**；与 t2 登记的 B17-11 同族，建议并案处置。

## §9 非 pass / blocked 登记（硬约束④：不得折算 pass）

| # | 项 | 状态 | 解除条件 |
| --- | --- | --- | --- |
| 1 | t6 验收项 3「`ci_gates.py --phase first` exit 0」 | **not_achieved**（实测 `exit=2`） | 唯一来源 = report-only `evidence_hash`（先在性、非 t6 引入）：按新 run_id 落盘，或 A-70 重基线 `test-reports-2026-10/evidence/artifact_hashes.json`（`--freeze` 只追加）后复跑。**blocking 面已全绿**，该项不得因 blocking 绿而折算 pass |
| 2 | F-01 / F-02 | **needs_revision**（本复核 verdict 来源） | 按各自 requiredFix 修正交付件后，由**非作者**复核确认；本条为文档修正，**不需**重跑机制类判据 |
| 3 | G-21 ③ 的 24 条「留档待决」 | **留档待决**（不折算 pass） | 按能力域分批纳入 `write_expect` 台账：每批 = 旧值留档 → `--inject-write-module` 阴性对照转红 → 复跑绿 + 登记（t6 §2.3 已给分批序） |

## §10 复现命令

1. **阳性（写面 + 页面面全绿）**：`cd /root/code/MyERP && /opt/wage-venv/bin/python -B scripts/_sandbox_compat.py scripts/permission_matrix.py --no-dump`（判据：`[OK] C-06 四模块写端点面 = 全绿（21 写端点…）`，exit 0）
2. **阴性对照（定向转红）**：同上命令追加 `--inject-write-module equipment`（判据：`[FAIL] C-06 四模块**写端点**面失败：equipment` + `靶向性`，exit 1）
3. **`--help`（参数面）**：`/opt/wage-venv/bin/python -B scripts/_sandbox_compat.py scripts/permission_matrix.py --help`（判据：`--inject-write-module` 在读，exit 0）
4. **D-9 判据裁定**：`/opt/wage-venv/bin/python -B test-reports-2026-10/harness/coverage_drift.py --coverage test-reports-2026-10/evidence/harness/ci-run-20261012-054655/coverage.json`（判据：`[OK] D-9 … N=44 M=38 len(list)=38`，exit 0）
5. **N 独立计数与写侧扫描**：`/opt/wage-venv/bin/python -B scripts/route_inventory.py | grep -c '^  MULTI '`（判据：44）；写侧扫描用「def 至下一顶层 def」块口径统计 `db.session.add(` / `db.session.commit(`（F-01 复算：`consumable_inbound` ⇒ 2/1）
6. **门禁**：`/opt/wage-venv/bin/python -B test-reports-2026-10/harness/ci_gates.py --phase first`（判据：`steps=20` / `blocking 失败 = 无` / `permission_matrix … checks 3/3`）
7. **纪律**：`git diff --numstat -- scripts/check_doc_claims.py test-reports-2026-10/harness/ci_gates.py test-reports-2026-10/harness/run_gates.py test-reports-2026-10/harness/coverage_drift.py`（判据：四条均无输出）
8. **真库三值**：`sha256sum app.db && stat -c '%s %y' app.db`

## §11 本件指纹

- §0–§9 为 2026-10-12 05:35–06:05 UTC 现场读数；append-only。
- 本件共 226 行（末行即本行）；`head -n -1` 口径 = 225 行 / 23723 B、SHA256 = `774384b605be4ede0f765983fd5efc5f595637c657b366a485a046c9420b3407`。复算：`head -n -1 test-reports-2026-10/C-工具面覆盖口径-非作者复核.md | wc -l -c`、`… | sha256sum`。
