# C · G-19/G-21 工具面覆盖口径（t6 交付件）

- 任务：t6 实现 G-19（C-06 写端点 deny face）/ G-21（多方法规则覆盖口径）；attempt 3 `0963f005-626d-4579-a6f1-a90205245701`。
- 现场：HEAD `9f28baa`；解释器 `/opt/wage-venv/bin/python`（3.11.2）。
- 真库只读复核：开工（05:36）与收工（05:49）三值恒等 `34e48e7a21163db390eebda4f2030343f3609afedc65d8c6e909d6eb5a49177e` / `2531328 B` / `2026-10-12 04:25:37.128430119 +0000`；全部请求型实验经 `scripts/_test_bootstrap.make_app()` 副本库。
- 本件改动面：`scripts/permission_matrix.py`（deny 角色派生化，见 §1.3）+ 本件。`scripts/check_doc_claims.py` PINNED 与 `harness/ci_gates.py` needle **未触碰**（git diff 佐证）。

## §1 G-19 —— C-06 四模块写端点 deny face（同一工具内）

### 1.1 face 现状（HEAD 已落地 B17-13，本轮实测）

同一工具 `scripts/permission_matrix.py` 内的写端点面（**无并行工具**）。**帧口径（t14 重锚）**：下行号均为**工作区帧** = 现场 HEAD `9f28baa` + 该文件本轮未提交改动（t6 派生化；该文件的**提交基线**为 `64d48c9`，`git diff --stat 64d48c9 9f28baa -- scripts/permission_matrix.py` 输出为空 ⇒ 两提交间该文件无改动）。工作区帧指纹 = `sha256 73c329f8647883c33de13676baac6c5c78790931e6ca51f19c2f3ed8e794e4f7` / 45805 B；行号**逐条 `grep -n` 实测，不作算术推算**（t6 的插入/替换在工作区帧 `:383`、`:406`、`:485`、`:490` 等点混布，各行位偏移不齐：实测 Δ=+8 或 +10）。HEAD 帧（`git show 9f28baa:scripts/permission_matrix.py`）逐条对照见本表末注。

| 组件 | 载体（工作区帧实测行号） | 说明 |
| --- | --- | --- |
| 写端点派生 | `scripts/permission_matrix.py:448` `def write_endpoints(app, guards, capability)` | 从 `url_map` **派生**（写方法 + 视图挂该能力），不手抄路径表 |
| 写面执行 | `:477` `def run_write_face(found_by_module, clients, roles_for, ids)`；台账漂移判红 `:518-519`（`:518` `if len(found) != spec['write_expect']:` ⇒ `:519` 消息 `写端点数漂移: 现场 %d != 台账 %d`） | 逐端点 ≥1 allow + ≥1 deny + 5xx/EXC=0；模块级写端点数 == `write_expect` 台账（**上下漂移都红**） |
| 写面打印 | `:537` `def print_write_face(...)` | 含注入面回显 |
| CLI 参数 | `--inject-write-module`（argparse `:769`；`--help` 读数见 §1.2） | 副本进程内摘除该模块首个写端点的 `@require_capability` ⇒ deny 断言必须转红 |
| 主流程接线 | `:597`（注入前派生清单 `write_found`）/ `:680-681`（失败收集+打印）/ `:701`（落盘 `write_summary`）/ `:722-723`（汇总行） | 退出码计入：`:713` `code = 1 if (anon_open or face_failures or write_failures or ir_failed) else 0` |

> **帧对照（HEAD `9f28baa` 帧 ↔ 工作区帧，两帧均 `grep -n` 实测）**：
>
> | 锚点 | HEAD 帧 | 工作区帧 | Δ |
> | --- | --- | --- | --- |
> | `def write_endpoints` | `:440` | `:448` | +8 |
> | `def run_write_face` | `:469` | `:477` | +8 |
> | 消息 `写端点数漂移` | `:509` | `:519` | +10 |
> | `def print_write_face` | `:527` | `:537` | +10 |
> | 注入前派生 `write_found =` | `:587` | `:597` | +10 |
> | 失败收集 `write_failures = [` / 打印调用 `print_write_face(write_face` | `:670` / `:671` | `:680` / `:681` | +10 |
> | 落盘 `write_summary` | `:691` | `:701` | +10 |
> | 退出码 `code = 1 if (anon_open or face_failures …)` | `:703` | `:713` | +10 |
> | 汇总 `if write_failures:` / `print([FAIL] C-06 … 写端点…)` | `:712` / `:713` | `:722` / `:723` | +10 |
> | argparse `--inject-write-module` | `:759` | `:769` | +10 |
> | `inject_write_module=args.inject_write_module` | `:765` | `:775` | +10 |
>
> 上表 Δ 的成因：t6 新增 `deny_roles_for()` 及其调用（HEAD 帧无此符号）——工作区帧 `def` `:383`、页面面引用 `:406`、写面引用 `:490`；`Δ` 在同一文件内**非均匀**，故表中每个数字都以两帧实测为准。复算（工作区）：`grep -n 'def write_endpoints\|def run_write_face\|def print_write_face\|写端点数漂移\|write_found =\|write_failures = \[\|write_summary\|anon_open or face_failures\|^    if write_failures:\|--inject-write-module\|inject_write_module=args' scripts/permission_matrix.py`；HEAD 帧：把同一命令的路径换成 `<(git show 9f28baa:scripts/permission_matrix.py)`。

### 1.2 本轮实测读数（2026-10-12 05:36–05:47，副本库）

> t14 复跑（2026-10-12 06:1x，`--no-dump`）：下述四行 `[OK]` 与 `exit 0（routes_tested=146, c06_write_modules_failed=[]）` **逐字同值**；唯一差别是第 4 行末段随 t16（另一线）改动扩写为「…，按 (file, 文本) 出现次数逐一相等、双向无漏斗；行号漂移 9 处仅 WARN」，本件已按现场全文引用。

**基线（修后）**：`/opt/wage-venv/bin/python -B scripts/permission_matrix.py --no-dump` ⇒

```
[OK] 匿名可访问 = 0
[OK] C-06 四模块权限面 = 全绿（4 模块 allow + deny + 5xx=0）
[OK] C-06 四模块写端点面 = 全绿（21 写端点：逐端点 ≥1 allow + ≥1 deny，5xx/EXC=0）
[OK] 内联 role ≤ 白名单 = 全绿（扫描 16 条 == 白名单 16 条，按 (file, 文本) 出现次数逐一相等、双向无漏斗；行号漂移 9 处仅 WARN）
exit 0（routes_tested=146, c06_write_modules_failed=[]）
```

写端点台账对拍：equipment 9/9、purchase_orders 8/8、shipments 4/4、stock 0/0（无写端点声明）= **21 写端点全绿**，逐端点 allow=admin,manager（shipments 含 sales）、deny=派生 deny 集（见 §1.3）、5xx/EXC=无。21 条逐端点明细见运行 stdout（复跑命令 §4.1）。

**`--help` 读数**（节选，完整见 §4.1 命令）：

```
usage: permission_matrix.py [-h] [--out OUT] [--no-dump]
                            [--out-modules OUT_MODULES]
                            [--inject-module INJECT_MODULE]
                            [--inject-write-module INJECT_WRITE_MODULE]
  --inject-write-module INJECT_WRITE_MODULE
                        注入回放（B17-13）：副本进程内移除该模块**首个写端点**的
                        @require_capability ⇒ 写面 deny 断言必须转红（不改生产代码）
```

### 1.3 本轮代码改动：deny 角色集派生化（G-19 合同字面合规）

**修前**：deny 样本角色是 `MODULE_FACE[*]['deny_sample']` 手写元组（4 处，如 `('hr','accountant','inspector','sales','user')`）——与任务书「deny 断言的角色集走 `app.permissions.roles_for`（**不得手写角色名列表**）」不符（allow 面已走 `roles_for`，deny 面未走）。

**修后**（`git diff scripts/permission_matrix.py` = +28/−18 行）：

- 新增 `deny_roles_for(capability)`（`scripts/permission_matrix.py:383`）：`deny = app.permissions.ROLES 全角色表 − roles_for(capability)`，页面面（`:406`）与写端点面（`:490`）共用；
- 删除 `MODULE_FACE` 4 处手写 `deny_sample` 元组；两个 run 函数内 6 处引用全部改为派生值；落盘 JSON 键 `deny_sample` 保留（值=派生集，形状兼容）。

**等价性证明（口径=工具+值）**：派生前硬编码样本 vs 派生后集合逐模块比对——equipment.manage（allow=admin,manager）⇒ deny={hr,accountant,inspector,sales,user}；purchase.manage 同；shipment.manage（allow=admin,manager,sales）⇒ deny={hr,accountant,inspector,user}；inventory.view ⇒ 同 equipment。**四模块派生集与原手写样本逐一相等** ⇒ stdout deny 列名逐字不变（修后基线输出可证）。此为**合规性重构**，非判据口径改动：判据仍是「≥1 deny」，钉值/needle 未动，故不适用 A-70 改值三步（无值改动）；阴性对照照做（§1.4）。

### 1.4 阴性对照（A-70 第②③步口径；修前修后各一轮）

**修前（05:37，改动前代码）**：`--inject-write-module equipment` ⇒

```
[INJECT] 副本进程内移除**写端点**的 @require_capability：module=equipment endpoint=main.equipment_downtime
  [FAIL] POST /equipment/<int:id>/downtime   allow=admin,manager  deny=-  5xx/EXC=无
[INJECT] 期望 = 该模块写面 deny 断言转红 ⇒ 实际 deny_ok=['hr','accountant','inspector','sales','user']  module_ok=False
[INJECT] 靶向性 = 其它三模块写面仍全绿: ['purchase_orders', 'shipments', 'stock']
[FAIL] C-06 四模块**写端点**面失败：equipment
exit_code_semantics inputs: c06_write_modules_failed=["equipment"], code=1
```

**修后（05:44，派生化代码）**：同一命令 ⇒ 同样 `[FAIL] POST /equipment/<int:id>/downtime … deny=-`、`c06_write_modules_failed=["equipment"]`、**进程真退出码 = 1**；靶向性同（其余三模块仍绿）。

**t14 复跑（2026-10-12 06:1x，工作区帧）**：`--inject-write-module equipment` ⇒ **exit 1**，读数逐字同修后轮：`[INJECT] … module=equipment endpoint=main.equipment_downtime stripped_layers=2`、`[FAIL] POST /equipment/<int:id>/downtime … deny=-`、`[INJECT] 靶向性 = 其它三模块写面仍全绿: ['purchase_orders', 'shipments', 'stock']`、`e03 inputs.c06_write_modules_failed=["equipment"] code=1`；且 `find test-reports-2026-10/evidence -newer <marker> -type f` 为空 ⇒ 该注入跑**未写任何 evidence 文件**（t8/t9 写盘守卫之后入口）；真库三值前后恒等。

**恢复绿（第③步）**：撤注入（不携带 `--inject-write-module`）复跑 ⇒ 修前 05:39 与修后 05:45 两轮 `RECOVERY_EXIT=0`，写面回到 21 端点全绿。注入为副本进程内操作，无生产代码恢复动作。

### 1.5 门禁（permission_matrix 是 blocking 步）

`ci_gates.py --phase first`（run `ci-run-20261012-054655`，05:47）：`steps=20 / blocking 失败=无 / permission_matrix group=blocking exit=0 checks 3/3 / report-only 失败=['evidence_hash'] / exit=2`。exit≠0 的唯一来源是 **report-only `evidence_hash` 先在性红**（另线 04:45 run 改写两条 b17-verify 基线；归因与解除条件 §3.2），非本任务引入；blocking 面全绿。

**t14 复跑（2026-10-12 06:07，run `ci-run-20261012-060742`）**：`steps=20 / blocking 失败=['check_doc_claims'] / report-only 失败=['evidence_hash'] / 注入未生效=无 / 仓库根两 JSON 未被触碰=True / permission_matrix group=blocking exit=0 checks 3/3 / exit=1`。与 05:47 轮的差 = 新增一条 blocking 红 `check_doc_claims`（`checks 1/5`），唯一 violation = `[VIOLATION] 口径源漂移：routes_py_lines 钉值 12806 ≠ 源值 12825（源：app/main/routes.py splitlines() 行数）` —— 成因是**他线未提交的 `app/main/routes.py` 改动**（mtime 06:01，晚于 05:47 轮）使行数漂移，与本件改动（本件不入 `check_doc_claims` 的权威源）无关。修它须改 `scripts/check_doc_claims.py` 钉值 ⇒ **本任务 Out of scope**，按 §3.3 记 blocked，**不折算 pass**。

**t14 attempt-3 复跑（2026-10-12 06:22，run `ci-run-20261012-062243`）**：上级已走 **A-70 三步**重基线 `routes_py_lines` 12806→12825（`scripts/check_doc_claims.py` 改动 3/2 行、旧值留档于同处注释 + `B18-登记.md` §B18-C-07，+26 行；`52-V13-TL050607-工具链收尾.md` 1/1）⇒ `steps=20 / blocking 失败=无 / check_doc_claims group=blocking exit=0 checks 5/5 / permission_matrix group=blocking exit=0 checks 3/3 / report-only 失败=['evidence_hash'] / 注入未生效=无 / 仓库根两 JSON 未被触碰=True / exit=2`。按本轮判据「**blocking 失败=无**」= **绿**；`exit=2` 的唯一来源是入册 **report-only** `evidence_hash`（§3.2，blocked），**不构成 verify 失败**。§3.3 记的 blocked 由此转 **resolved**。

## §2 G-21 —— 「GET+写」多方法规则覆盖口径

### 2.1 现场读数与锚点对账

- 现场权威读数（2026-10-12 05:41）：`route_inventory.py` ⇒ `[multi] GET+写 多方法规则=44`；`measure_coverage`（ci-run-20261012-053210/054655 coverage.json）⇒ `multi_method_with_get_total=44 / multi_method_with_get_uncovered=38`。
- 锚点对账：任务书「37 条」= 70-文档时点（RL-01 帧）；`52-V13-TL050607-工具链收尾.md` caliber 注释与 `harness/coverage_drift.py:20`（D-9）留档的演进链 = SEC-CSRF-01（43/37→44/38）→ e057e81 删 `/auth/register`（→43/37）→ **B18-Q1 增 `/auth/change-password`（43/37→44/38）**。本任务按现场读数 **N=44 / M=38** 分类（37 已陈旧，不追改历史件）。
- 量纲警示（沿 t1）：38（多方法规则面）≠ 钉值 `non_get_uncovered_method_level=40`（方法级非 GET 未命中，`52-:30` / `check_doc_claims.py:123`），**不得互替**。

### 2.2 38 条未命中规则逐类处置口径（1+13+24=38）

**① 已纳入判据（执法面已存在、本轮实测绿）—— 1 条**

| 规则 | 端点 | 处置 | 证据 |
| --- | --- | --- | --- |
| `/equipment/<int:id>/layout` | `main.furnace_layout` | **已纳入**：POST 侧即 C-06 写面 equipment 9/9 之一 | 本轮基线 `[OK] POST /equipment/<int:id>/layout allow=admin,manager deny=hr,accountant,inspector,sales,user`；「未命中」只是 `measure_coverage` 的**探针字面量口径差**（探针面 vs 执法面），非执法缺失 |

**② 显式不纳入 + 理由 —— 13 条**

| 子类 | 规则（条数） | 理由 |
| --- | --- | --- |
| auth 平面 | `/auth/`、`/auth/change-password`、`/auth/logout`（3） | `permission_matrix` 页面/写面**设计性排除** `auth.*`（`run()` 内 `endpoint.startswith('auth.')` 早退）；change-password 有 B18-Q1 弱口令专项、logout POST 有 SEC-CSRF-01 专项（`52-` caliber 注释明载非 GET 面 +1 即由此）。能力面判据语义不适用于登录前/会话平面 |
| GET+POST 双支持导出 | `/employees/export`、`/process_prices/export`、`/production_records/export`、`/bonus_penalties/export`、`/export_tasks`、`/products/export`（6） | POST 侧 = 旧表单导出别名（**读语义**，无落库）；AGENTS.md 明文「新增 GET 下载不能破坏既有 POST 表单导出」。把读别名塞进写执法判据 = 把读误当写 |
| 查询/筛选型 POST | `/audit_logs`、`/bonus_penalties`、`/salary_calculation`、`/search/advanced`（4） | POST = 筛选/计算预览，**无落库**：def 块扫描（工作区帧，`app/main/routes.py` sha256 `e80e7a7269257ebd42b6619c17a4498c55866a58d53261bcbb9938afa020166d`）`view_audit_logs`（`:2033-2069`）/`manage_bonus_penalties`（`:1649-1755`）/`salary_calculation`（`:1896-2032`）/`advanced_search`（`:3155-3263`，**t14 重锚**：旧记 `:3150-3258` 为 HEAD 帧，工作区因他线未提交改动净 +5）均 `db.session.add=0 / db.session.commit=0`（§4 第 6 条复算命令） |

**③ 留档待决（真实写侧、无执法判据、探针未命中）—— 24 条**

| 子类 | 规则 | 写侧证据（工具+口径） |
| --- | --- | --- |
| 表单写 22 条 | `/employee/add`、`/employees/<int:id>/edit`、`/add_process_price`、`/process_prices/<int:id>/edit`、`/code_rules/add`、`/code_rules/<int:rule_id>/edit`、`/inventory/inbound`、`/inventory/raw-material/inbound`、`/inventory/finished-product/inbound`、`/production_orders/<int:order_id>/edit`、`/customer/add`、`/customer/<int:customer_id>/edit`、`/customer/<int:customer_id>/address/add`、`/customer/<int:customer_id>/address/<int:address_id>/edit`、`/sales_order/add`、`/sales_order/<int:order_id>/edit`、`/sales_order/<int:order_id>/item/add`、`/sales_order_item/<int:item_id>/edit`、`/sales_order_item/<int:item_id>/delivery_batches`、`/notification_rules/add`、`/consumables/inbound`、`/material_returns/add` | def 块机械扫描（§4 第 6 条逐端点一行；口径同 §4 第 8 条）：**22/22** 均 `form.validate_on_submit`/`request.method` 门 + `db.session.add ≥1` + `db.session.commit ≥1`（其中 15 条 commits=1、7 条 commits=2）；例 `add_employee` `:620-697` adds=3/commits=1、`consumable_inbound` `:11374-11444` adds=2/commits=1（**t14 订正**：旧记「consumable_inbound adds=16/commits=12」为误值，现场实测 2/1，复算命令同 §4 第 6 条） |
| 报工写 1 条 | `/tasks` | def 块实读（工作区帧，`app/main/routes.py` sha256 `e80e7a72…`）`:3350-3537`（`def manage_tasks():` 至下一顶层 `def`，口径见 §4 第 8 条）：POST `form.validate_on_submit()` → `db.session.add(task)`（`:3472`）+ `add(log)`（`:3493`）→ `db.session.commit()`（`:3505`）⇒ **adds=2/commits=1**。t14 订正：原记「commits=2」系把注释行 `:3496`（`# 随下方既有的 db.session.commit()…`）误计；本口径只计**非注释行**，复算命令 §4 第 8 条 |
| 更新型写 1 条 | `/assembly/<int:product_id>` | 实读 `app/main/stock.py:36-76`（工作区帧，sha256 `53fa18433bd44c33ba87fb1d3fd398504ba145cf7653535331ffda66db123165`；t14 重锚，旧记 `:36-71` 只到函数体末行，未含至下一顶层 `def`）：`def assemble_product` 内 POST 变更 `wp.status='assembled'` + `mes_service.log_event(...)` + `db.session.commit()`（`:62`）⇒ **0 add / 1 commit = UPDATE 型** |

**探针已命中（不在 38 之列，列此对账）—— 6 条**：`/auth/login`、`/search`、`/system_configs`、`/production_records`、`/material_requisitions/add`、`/inventory_counts/add`（44−38=6，`uncovered_multi_method_with_get` 反集）。

### 2.3 ③ 的处置建议（不凑数：24 条**不**一次性塞进判据）

按能力域分批纳入 `MODULE_FACE` 写面台账（`write_expect` +1 需 A-70 登记 + 阴性对照）：

1. **账务/库存优先**（`/inventory/*` ×3、`/consumables/inbound`、`/material_returns/add`、`/tasks` 报工面）——资金/存量面，风险最高；
2. **单据面**（sales_order 族 5 条、`/production_orders/<id>/edit`、delivery_batches）；
3. **主数据面**（employee ×2、customer ×4、process_price ×2、code_rules ×2、notification_rules、assembly）。

解除条件（留档待决 → 纳入）：每批 = ① 台账登记 `write_expect` 新值（旧值留档）→ ② `--inject-write-module <该模块>` 阴性对照转红 → ③ 复跑绿 + `52-`/登记件更新。全批完成前 G-21 保持本件口径，**不折算 pass**。

## §3 纪律与归因

### 3.1 未改口径

- `scripts/check_doc_claims.py` PINNED 与 `test-reports-2026-10/harness/ci_gates.py` needle：**未触碰**（`git status` / diff 佐证，改动仅 `scripts/permission_matrix.py` + 本件）。
- `docs/**` 未动；`test-reports-2026-10/evidence/**` 未追改；未 `git add`/commit/push（工作区另有他成员暂存件，不碰）。

### 3.2 evidence_hash（report-only）归因与解除条件

run `ci-run-20261012-054655` 的 `evidence_hash.gate.json`：violations=modified×2，与 t4 轮归因**同对**（mtime 04:45:16/04:45:29 = 另线 run-20261012-044515 帧产物，先于本任务开工 05:36）：

| 文件 | 基线 sha256 | 现场 sha256 | 尺寸 |
| --- | --- | --- | --- |
| `harness/b17-verify/probe_permission_matrix.txt` | `1664B44BF5FB227BC4ED118CAD75EFB812AE3B8636768FD5CF8437D8389C49D5` | `F81525C2B3CF4A5ED41F24CE5FEE08AB0EEDC5FDA4436AB168E066384D5AFB16` | 9627→11234 B |
| `harness/b17-verify/probe_smoke_test.txt` | `59A7E5F065716E43B5049763C8471C207F1CF55632A914ADCF72FBCEDBAD7E95` | `DA0C377DA223D63B998A3F1674B24C4B612D94D3420B4332BD23DE314A954B68` | 3186→3186 B |

解除条件：按 `required_fix` 用新 run_id 目录落盘，或 A-70 重基线 `artifact_hashes.json`（`--freeze` 只追加）后复跑。**状态 = blocked（先在性、非本任务引入），不得折算 pass。**

### 3.3 check_doc_claims（blocking）t14 复跑归因与解除条件

run `ci-run-20261012-060742`（06:07）`check_doc_claims` 步 `checks 1/5`、`exit=1`，stdout_tail 全文：

```
[check_doc_claims] 钉常量 vs 权威源：28/29 相等
[check_doc_claims] 文档：扫描 5 份、带口径表 1 份
[check_doc_claims] lock：33 条钉版 / 环境匹配 33 条 / exception 0 条
[check_doc_claims] [WARN] 声明表环境标记在本平台为假，不进 lock：pywin32
[check_doc_claims] [VIOLATION] 口径源漂移：routes_py_lines 钉值 12806 ≠ 源值 12825（源：app/main/routes.py splitlines() 行数）
[check_doc_claims] RESULT: FAIL（violations=1）
```

- **工具 + 口径 + 值**：工具 `ci_gates.py --phase first`（第 20 步，argv 明写 `--coverage <run_dir>/coverage.json`）；口径 = 钉常量 vs 权威源（`routes_py_lines` 源 = `app/main/routes.py` 的 `splitlines()` 行数）；值 = 钉值 12806 / 源值 12825 / violations=1。独立复核（同一工具直跑）：`/opt/wage-venv/bin/python -B scripts/check_doc_claims.py` ⇒ exit 1、violations=12（其中 11 条是**缺 `--coverage` 的参数性红**：源值 None；第 12 条即上述 routes_py_lines，与 ci_gates 内读数一致）。
- **先在性判定**：05:47 轮（t6）该步 `29/29 相等`；routes.py 的改动 mtime = **06:01**，晚于 05:47 ⇒ 该红由**他线未提交改动**引入，先于本件会话（t14 开工 06:0x）且不因本件任何改动产生（本件为 `test-reports-2026-10/**` 下未跟踪新件，不入 `check_doc_claims` 的任何权威源/文档扫描面）。
- **状态 = blocked（不折算 pass）**；解除条件 = 由 `app/main/routes.py` 改动的属主：① 若该改动将入库 ⇒ 走 **A-70 三步**重基线 `check_doc_claims.py` 的 `routes_py_lines` 钉值（旧值 12806 留档 → 阴性对照先转红 → 改值 + 复跑绿 + `52-`/登记件）；② 若该改动回退 ⇒ 源值回到 12806，本步自愈。两条路径均**不在 t14 的 in-scope**（`scripts/check_doc_claims.py` 明列 Out of scope）。
- **解除记录（2026-10-12 06:22，走路径①）**：上级完成 A-70 三步——旧值 12806 留档（`scripts/check_doc_claims.py` 同处注释+新登记 `B18-登记.md` §B18-C-07，`git diff` = 3/2 行）、改值 12825、复跑绿（run `ci-run-20261012-062243`：`check_doc_claims group=blocking exit=0 checks 5/5`、`steps=20 / blocking 失败=无`）⇒ 本项 **blocked → resolved**。本件只记录该三步读数、未参与改值（`scripts/check_doc_claims.py` 全程 Out of scope）。
- **本件自身的 blocking 面**（同轮）：`permission_matrix group=blocking exit=0 checks 3/3`、其余 blocking 步全绿（见 §1.5）⇒ 与本件相关的判据面无红。

## §4 复跑命令

1. `cd /root/code/MyERP && /opt/wage-venv/bin/python -B scripts/permission_matrix.py --no-dump`（基线：写面 21 端点全绿，exit 0）
2. 同上 + `--inject-write-module equipment`（阴性对照：`[FAIL] POST /equipment/<int:id>/downtime … deny=-`，exit 1）
3. `/opt/wage-venv/bin/python -B scripts/permission_matrix.py --help`（`--inject-write-module` 参数在读）
4. `/opt/wage-venv/bin/python -B scripts/route_inventory.py | grep -A50 '\[multi\]'`（N=44 逐条列表）
5. `/opt/wage-venv/bin/python -B scripts/permission_matrix.py --no-dump 2>&1 | grep 'deny≥1'`（派生 deny 集逐模块读数）
6. **§2.2②③ 全量复算（t14 补：口径同第 8 条）**——路径 → 视图函数（解析 `@bp.route` 装饰器，`app/main/*.py`）→ def 块逐条打印 `范围 / adds / commits / gate`，一次复算 §2.2② 读语义 4 条 + §2.2③ 写侧 24 条。

   粘贴说明（t14 实测）：代码块在本文列表内带 **3 空格缩进**，原样粘贴会 `IndentationError: unexpected indent`；先整体左移 3 空格（`sed 's/^   //'`）并去掉首行 `/opt/wage-venv/bin/python - <<'PYEOF'`、末行 `PYEOF`，即得脚本本体。实测（t14，2026-10-12）：去缩进后 `/opt/wage-venv/bin/python -B <body>` ⇒ **exit 0**，输出 28 行与 §2.2 数字逐条一致（读语义 4 条 `adds=0 commits=0`；`/tasks`、`/assembly/<int:product_id>` 见 §2.2③）。

   ```bash
   /opt/wage-venv/bin/python - <<'PYEOF'
   import re, glob
   READ = ['/audit_logs','/bonus_penalties','/salary_calculation','/search/advanced']
   WRITE = ['/employee/add','/employees/<int:id>/edit','/add_process_price','/process_prices/<int:id>/edit',
            '/code_rules/add','/code_rules/<int:rule_id>/edit','/inventory/inbound','/inventory/raw-material/inbound',
            '/inventory/finished-product/inbound','/production_orders/<int:order_id>/edit','/customer/add',
            '/customer/<int:customer_id>/edit','/customer/<int:customer_id>/address/add',
            '/customer/<int:customer_id>/address/<int:address_id>/edit','/sales_order/add',
            '/sales_order/<int:order_id>/edit','/sales_order/<int:order_id>/item/add',
            '/sales_order_item/<int:item_id>/edit','/sales_order_item/<int:item_id>/delivery_batches',
            '/notification_rules/add','/consumables/inbound','/material_returns/add','/tasks',
            '/assembly/<int:product_id>']
   views = {}
   for f in sorted(glob.glob('app/main/*.py')):
       src = open(f, encoding='utf-8').read().splitlines()
       pend = []
       for i, l in enumerate(src, 1):
           m = re.match(r"@bp\.route\(\s*'([^']+)'", l)
           if m:
               pend.append(m.group(1)); continue
           d = re.match(r'def (\w+)\(', l)
           if d and pend:
               for p in pend: views.setdefault(p, []).append((f, i))
               pend = []
           elif l.strip() and not l.startswith(('@', 'def ')) and not l[0].isspace():
               pend = []
   for grp, rules in (('②读', READ), ('③写', WRITE)):
       for p in rules:
           for f, lo in views.get(p, []):
               src = open(f, encoding='utf-8').read().splitlines()
               hi = next((j for j, l in enumerate(src[lo:], lo + 1) if re.match(r'^def ', l)), len(src)+1)
               blk = [l for l in src[lo-1:hi-1] if not l.lstrip().startswith('#')]
               adds = sum(1 for l in blk if 'db.session.add(' in l)
               commits = sum(1 for l in blk if 'db.session.commit(' in l)
               gate = any('form.validate_on_submit' in l or 'request.method' in l for l in blk)
               print(f'{grp} {p:58s} {f}:{lo}-{hi-1} adds={adds} commits={commits} gate={gate}')
   PYEOF
   ```

   期望（2026-10-12 工作区帧实测）：② 读语义 4 条 `adds=0 commits=0`；③ 写侧 22 表单条 `gate=True` 且 `adds>=1 / commits>=1`，`/tasks` `adds=2 commits=1`，`/assembly/<int:product_id>` `adds=0 commits=1`（`app/main/stock.py:36-76`）。
7. `sha256sum app.db && stat -c '%s %y' app.db`（真库三值复核）
8. **写侧 def 块扫描（t14 补，§2.2③ 各行数字的复算命令）**——口径：**def 块 = 该 `def` 行至下一顶层 `def` 行（不含）**；只计**非注释行**（`lstrip()` 后不以 `#` 开头）。

   粘贴说明同第 6 条（先 `sed 's/^   //'` 去 3 空格列表缩进，去掉首行命令与末行 `PYEOF`）。实测（t14，2026-10-12）：去缩进后 `python -B <body>` ⇒ **exit 0**，打印 `manage_tasks def块 3350-3537: adds=2 commits=1`，与 §2.2③ `/tasks` 行逐字一致。换其它端点复算：改 `FUNC`（如 `consumable_inbound` ⇒ 期望 `:11374-11444: adds=2 commits=1`）。

   ```bash
   /opt/wage-venv/bin/python - <<'PYEOF'
   import re
   PATH, FUNC = 'app/main/routes.py', 'manage_tasks'   # 换 FUNC 复算其它端点
   src = open(PATH, encoding='utf-8').read().splitlines()
   lo = next(i for i, l in enumerate(src, 1) if l.startswith(f'def {FUNC}('))
   hi = next(i for i, l in enumerate(src[lo:], lo + 1)
             if re.match(r'^def ', l))
   blk = src[lo - 1:hi - 1]
   adds = sum(1 for l in blk if 'db.session.add(' in l and not l.lstrip().startswith('#'))
   commits = sum(1 for l in blk if 'db.session.commit(' in l and not l.lstrip().startswith('#'))
   print(f'{FUNC} def块 {lo}-{hi-1}: adds={adds} commits={commits}')
   # manage_tasks => 3350-3537: adds=2 commits=1
   PYEOF
   ```

9. **门禁全链（t14 复跑，2026-10-12 06:22）**：`/opt/wage-venv/bin/python -B test-reports-2026-10/harness/ci_gates.py --phase first`（约 67 s）⇒ `steps=20 / blocking 失败=无 / report-only 失败=['evidence_hash'] / 注入未生效=无 / exit=2`（判据 = blocking 失败=无 ⇒ 绿），console 落盘 `test-reports-2026-10/evidence/harness/ci-run-20261012-062243/ci_gates_first.console.txt`；report-only `evidence_hash` 归因与解除条件见 §3.2，blocking `check_doc_claims` 的 blocked→resolved 见 §3.3。早期读数（06:07 run `ci-run-20261012-060742` 的 exit=1）保留于 §1.5 供对账，不追改。

## §5 本件指纹

- 本件共 **264 行**（末行即本行）；`head -n -1` 口径 = **263 行 / 28566 B**、SHA256 = **`7D7E8DBE6FF3222CE4414F4881D58F6C0B361D4A06C250402B9E0551DE950A13`**。复算：`head -n -1 test-reports-2026-10/C-工具面覆盖口径.md | wc -c -l`、`… | sha256sum`。§1–§4 为 2026-10-12 05:36–05:49 现场读数；t14（2026-10-12）重锚 §1.1 工作区帧、订正 §2.2③ 数字、补 §4 第 6/8/9 条与 §3.3、§1.2/§1.4/§1.5 增补 t14 复跑读数（06:07 红 → 06:22 绿，blocking 失败=无），t6 时点旧指纹 153/14307/37bae076…e69 由 t13 复核留档。
