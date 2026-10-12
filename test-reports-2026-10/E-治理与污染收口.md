# E-治理与污染收口（t19 收口（二）：O2 / O3+G-22 / O7·G-21 台账 / G-13·G-15·G-18）

- **任务**：t19「阶段C 在册项收口（二）：治理与污染面」；`attempt_id = 3eee6e70-9108-4598-8ea7-e97c15c74665`
- **作者**：gov-inject（非实现者线条；本件**只测不改**，除本件与 `B18-登记.md` 的 append 外未改任何文件）
- **范围**：① O2 `A-63-STEP2-BUILD-GATE`；② O3 + G-22 仓库根污染 6 项；③ O7 / G-21 多方法规则**分批纳入台账**（本轮不要求实现）；④ G-13 / G-15 三载体 / G-18 的 `not_covered` 现场核实
- **解读器**：`/opt/wage-venv/bin/python`（3.11.2）；工作目录 `/root/code/MyERP`
- **真库三值**：开工（本件动笔前）与收工（写件后）各一次，见 §5-U-6 与 §8；期间恒等
  `sha256 = 34e48e7a21163db390eebda4f2030343f3609afedc65d8c6e909d6eb5a49177e` / `2531328 B` / `mtime = 2026-10-12 04:25:37.128430119 +0000`
- **硬约束**：未跑 `flask db *`；未写 `app.db`；未覆盖 `docs/**`（本件为 `test-reports-2026-10/` 下**新建**件）；未 `git add` / 未 commit / 未 push；未改判据钉值；删除类动作一律**先打印已解析绝对路径并确认在仓库内**（本轮**未执行任何删除**，理由见 §2）。

> 口径：本件每条 = **命令 + 口径 + 读数 + 判定 + 未测项解除条件**。「未发现问题」「看起来正常」一律不写；未跑的不折 pass，一律标 `not_measured` / `not_covered` 并给解除条件。

---

## §0 终态总览

| # | 项 | 终态 | 一句话读数 |
| --- | --- | --- | --- |
| ① | O2 `A-63-STEP2-BUILD-GATE` | **blocked（按设计接受，不计入通过数）** | 机读登记在 `ci_gates.py:119-132`，断言在 `--selfcheck`（`:1264-1267`），`gaps[]` 落盘（`:1280`/`:1636`）；`--selfcheck` = exit 0 / `step_count=20 failed=无`；解除 = A-63 第二步三件 |
| ② | O3 + G-22 根污染 6 项 | **6×「保留 + 登记」**（**不删、不新增 ignore 规则**） | 6 项 `git ls-files` = 0（全未跟踪）、`git check-ignore -v` **rc=1（均未被忽略）**；`git status --porcelain` 恰 6 条 `??`；删除因在途 scratch 受阻（U-2） |
| ③ | O7 / G-21 多方法规则 | **未纳入（本轮按任务不要求实现）+ 分批纳入台账已成文** | 现场 44 条 / 未命中 38 条 / **待决 24 条**；6 批（按 capability）逐批给 `write_expect`、A-70 三步、阴性对照命令与 4 条靶向性判据 |
| ④ | G-13 / G-15 / G-18 | **G-15 = 闭合**；**G-13 = 保持 `not_covered`**；**G-18 = 按设计接受（快照）+ 机制化兜底**（工具本容器不可跑 ⇒ 重跑判 `not_measured`） | G-15 三载体全在 blocking 链内且三条注入面均已实测转红；G-19（附带）现场已由 B17-13 闭合，`70` 的该行为陈旧 |

---

## §1 ① O2 `A-63-STEP2-BUILD-GATE`

### 1.1 在册位置（命令 + 读数）

```
grep -n 'A-63-STEP2-BUILD-GATE|BUILD_LAYER_BLOCKED|build-layer blocking registered' test-reports-2026-10/harness/ci_gates.py
```

| 位置 | 读数（原文摘要） |
| --- | --- |
| `test-reports-2026-10/harness/ci_gates.py:114-115` | `SMOKE_PROMOTION_NOTE = 'smoke_test 自 <待晋升日期> 起升为 blocking（A-63 第二步：观测 1 轮构建后）'` |
| 同上 `:119-132` | `BUILD_LAYER_BLOCKED = {'id': 'A-63-STEP2-BUILD-GATE', 'state': 'blocked', 'object': '构建层阻塞（Jenkinsfile / GitHub Actions 的门禁晋升）', 'owner': 'captain（A-85④ / A-63 明令 captain 独占）', 'not_counted_as_passed': True, ...}` |
| 台账 | `test-reports-2026-10/B18-05-批次收口台账.md:89`（blocked 登记）；`docs/验收记录-批次18-2026-10-11.md:185` |
| 自陈口径 | `ci_gates.py:31`：「该缺口在机读产物里**显式登记为 `blocked`**（随 `gaps[]` 落盘，**不计入通过数**）」 |

### 1.2 是否在门禁执行链内（命令 + 读数）

```
/opt/wage-venv/bin/python -B test-reports-2026-10/harness/ci_gates.py --selfcheck
```

- **读数**：exit `0`；`step_count=20 failed=无`；断言行 `build-layer blocking registered as blocked (A-63 step 2 pending)`（JSON `check` 字段，落 `test-reports-2026-10/evidence/harness/ci-run-20261012-080129/ci_gates.selfcheck.json:110`），断言体 = `BUILD_LAYER_BLOCKED.get('state') == 'blocked' and BUILD_LAYER_BLOCKED.get('not_counted_as_passed') is True`，附注 `id=… owner=…`（`ci_gates.py:1264-1267`）。
- **落盘/打印点**：`'gaps': [BUILD_LAYER_BLOCKED]` 在 `:1280`（selfcheck 出口）与 `:1636`（正式 run 出口）；人类可读行 `:1644-1645` 打印 `<id> = <state>`。今日 06:22 run 的 console 里该 `gaps` 块在 `test-reports-2026-10/evidence/harness/ci-run-20261012-062243/ci_gates_first.console.txt:813-822`。
- **口径**：**「在链」= 断言 + 随 `gaps[]` 落盘 + 每 run 打印一行**（不是 20 步里的一步）；即登记不可能被静默删掉——删了 `--selfcheck` 立刻红。

### 1.3 解除条件复核（命令 + 读数）

```
sed -n '108,126p' Jenkinsfile
grep -n 'continue-on-error|build-and-push|needs:' .github/workflows/docker-deploy.yml
```

| 登记所述 | 实测 | 判定 |
| --- | --- | --- |
| `Jenkinsfile:112 与 :122 的 error() 仍是注释` | `:111-112` = `// error('[E-04] 门禁入口缺失…')`；`:121-122` = `// error("[E-04] blocking 门禁失败…")`，两者下方均为 `currentBuild.result = 'UNSTABLE'` | **复核一致** ✓ |
| `.github/workflows/docker-deploy.yml:19 continue-on-error: true 未删` | 该行实在 **`:36`**（`:32-33` 有第一/第二阶段注释） | **行号已漂移**（F-1） |
| `:58 的 build-and-push 未加 needs: gate` | `build-and-push:` 实在 **`:105`**（`:106` 注释「第二阶段：在此加 `needs: gate`」）；全文无 `needs: gate` | **行号已漂移**（F-1） |

- **F-1（low，附带发现）**：`BUILD_LAYER_BLOCKED['blocked_reason']` 与 `['evidence']` 里的 GH 行号（`:19` / `:58`）相对现场已漂移；**语义仍为真**（`continue-on-error: true` 确实存在、`build-and-push` 确实无 `needs`）。建议 A-63 第二步实施时顺手同步这两处行号（改 `ci_gates.py` ⇒ 其 SHA 被多处文档引用，须同步文档读数）。

### 1.4 判定（终态）

- **终态 = `blocked`（按设计接受）**：① 登记完整且机读（id/state/object/blocked_reason/evidence/condition_to_unblock/owner/`not_counted_as_passed=True`）；② 断言在 `--selfcheck` 内、`gaps[]` 随每个 run 落盘 ⇒ 不会被静默清除；③ **不计入任何通过数**。
- **解除条件（三步，全属 captain）**：a) `Jenkinsfile:112`/`:122` 两处 `error()` 解注释（`ciRc==3` / `ciRc==1` 由 `UNSTABLE` 转红）；b) `.github/workflows/docker-deploy.yml` 删 `:36` 的 `continue-on-error: true` 且 `build-and-push`（`:105`）加 `needs: gate`；c) 观测 1 轮构建全绿后，把 `BUILD_LAYER_BLOCKED['state']` 改 `closed` 并同步 `SMOKE_PROMOTION_NOTE`（`smoke_test` 升 blocking 的日期）。
- **未测**：本容器无 Jenkins 执行面、亦不跑 GH Actions ⇒ 「观测 1 轮构建」不可执行（**U-1**：解除条件 = 由 captain 在有构建执行面处执行 a/b/c；本件只提供 `a/b` 的行号复核）。

---

## §2 ② O3 + G-22：仓库根污染 6 项

### 2.1 机械读取（命令 + 口径 + 读数）

```
git status --porcelain
git check-ignore -v <path>          # 口径：rc=0 命中某条 ignore 规则；rc=1 = 未被忽略
git ls-files -- <path>              # 口径：跟踪件数（0 = 未跟踪）
find <path> -type f -printf '%s…'   # 件数 / 字节 / 最新 mtime
```

| # | 项 | 跟踪 | ignore | 件数 / 字节 | 最新 mtime | 直接引用 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `.tmp/` | `ls-files`=0 | **rc=1 未忽略** | 301 files / **7,536,828 B** | `2026-10-12 05:23:22`（`.tmp/p1p6p9p10/exp_p1p6p9p10.py`） | 跟踪文档 0 处 |
| 2 | `.vscode/settings.json` | 0 | **rc=1** | 1 file / 135 B | — | — |
| 3 | `app.db.evidence-ALLOY-IMPORT-02-20261009_004539` | 0 | **rc=1** | 3,035,136 B / sha256 `4eb632a48f1c7e8a13bce8f6263d587a1958d01cc84e37a0d4359e1506ddfa43` | — | `B14-R1-锚点回退登记.md` |
| 4 | `instance/` | 0 | **rc=1** | 1 file（`instance/app.db` = **0 B** 空库） | — | — |
| 5 | `test-reports-2026-10/.tmp-t6runs/` | 0 | **rc=1** | 2 files / 396,396 B | — | `B18-登记.md:807`/`:855` |
| 6 | `test-reports-2026-10/.tmp-t9runs/` | 0 | **rc=1** | 2 files / 396,396 B | — | `B18-登记.md:741`/`:855` |

- `git status --porcelain` 实测恰 6 条 `??`（即上表 6 项），与 `B18-登记.md:848` 的「**禁入库 6 项**」名单**逐项一致**——该节已把这 6 项登记为「禁入库」并明写「本批**不新增** `.gitignore` 规则（避免打漂 `gitignore_lines`=56 触发又一轮 A-70）」。
- 对照：`test-reports-2026-10/.tmp/` 与 `test-reports-2026-10/evidence/**` **已被忽略**（`.gitignore:41` / `:42`），不在本项内。

### 2.2 逐项终态与理由

| # | 终态 | 理由（含为什么不删 / 不忽略） |
| --- | --- | --- |
| 1 `.tmp/` | **保留 + 登记**（删除判 `not_measured`，见 U-2） | 该目录**不是纯陈旧 scratch**：`p1p6p9p10/` 内是 P1/P6/P9/P10 线的 `routes_before_1a3850f.py` / `quality_before_a09b6c8.py` / `routes_before_a09b6c8.py` / `p10_no_notes.xlsx` 等**改动前快照与实验脚本**（最新写入 05:23:22，属阶段C 产品面在途材料）⇒ 删除会毁掉他线复跑材质，**本任务无授权也不该删** |
| 2 `.vscode/settings.json` | **保留 + 登记** | 本地 IDE 态（135 B）；`launch.json` 已在版本控制内属另一回事，本文件从未入库 |
| 3 `app.db.evidence-ALLOY-IMPORT-02-…` | **保留 + 登记** | **有意留证**（B14 时代对合金钢导入的真库留档；与 `/app.db`、`/app.db.bak-*` 同性质）⇒ 不能忽略后当它不存在，登记更诚实 |
| 4 `instance/` | **保留 + 登记** | 运行时侧产物；`instance/app.db` = 0 B 空库，**不是**真库、不构成 schema 事实来源（真库 = 仓库根 `app.db`，已被 `.gitignore:21` 覆盖） |
| 5 `.tmp-t6runs/` | **保留 + 登记** | `B18-登记.md:807` 的 t6 非作者 A/B 对照件落点；`:855` 明令「`harness/` 脚本一律在**干净同层目录**复跑、禁用 `test-reports-2026-10/.tmp/` 原地跑（`_env.py` 影射 ⇒ 假红）」⇒ 该目录是**纪律载体**，删了会让该纪律无落点 |
| 6 `.tmp-t9runs/` | **保留 + 登记** | `B18-登记.md:741` 明写「两份副本保留供非作者复跑」 |

### 2.3 决策记录：本轮**不**新增 `.gitignore` 规则（附可执行的 A-70 模板）

**结论**：6 项一律「保留 + 登记」，**不新增** `.gitignore` 规则。三条理由（都是实测/在册事实，非偏好）：

1. **既有约定**：`B18-登记.md:848` 已就**同一批 6 项**写明「本批不新增 `.gitignore` 规则」；`test-reports-2026-10/D-集成复核.md:266` 同口径（「会打漂 `gitignore_lines`=56 ⇒ 需再走一轮 A-70」）。
2. **`gitignore_lines` 是 PINNED 键**（`scripts/check_doc_claims.py` 的 `'gitignore_lines': (56, '.gitignore splitlines() 行数', …)`），且它有**两个载体**：`PINNED` 与 `test-reports-2026-10/52-V13-TL050607-工具链收尾.md:52`（`gitignore_lines = 56`，口径表逐键对拍）。加 5 条规则 ⇒ 56→61 ⇒ 必须走 A-70 三步（先例见 `B18-登记.md:302-306`：53→56 那一轮的「留档 → 注入 57 转红 → 改值 + 登记」）。
3. **并发安全**：`scripts/check_doc_claims.py` 本时段**正被并行任务改写**（实测 mtime `2026-10-12 08:02:06/08:02:10`、`git diff --numstat` = 41/9、期间一度 `IndentationError: unexpected indent (line 325)`、稳定后 sha256 `949388ad49606f82807ec7b06567eeec3355d825d22c305329508ca775e76de5`）⇒ 在同一文件上再压一次 PINNED 改动有踩踏风险，本轮不碰。

**A-70 现成模板（留给下轮「污染面二」整批执行，须一次加完 5 条）**

| 步 | 动作 | 期望读数 |
| --- | --- | --- |
| ① 旧值留档 | 记 `gitignore_lines` 旧值 = **56**（本件与 `52-V13` 口径表同值） | `.gitignore` = 56 行（`wc -l`） |
| ② 阴性对照**先转红** | 只改 `.gitignore`（加 `/.tmp/`、`/.vscode/settings.json`、`/app.db.evidence-*`、`/instance/`、`/test-reports-2026-10/.tmp-*/` 共 5 条 ⇒ 61 行），先**不改** PINNED，跑 `/opt/wage-venv/bin/python -B scripts/check_doc_claims.py --coverage test-reports-2026-10/evidence/harness/<run>/coverage.json` | 必红：`[VIOLATION] 口径源漂移：gitignore_lines 钉值 56 ≠ 源值 61`，exit 1（blocking 步亦红） |
| ③ 改值 + 复跑绿 + 登记 | `PINNED['gitignore_lines']` 56→**61** + `52-V13-TL050607-工具链收尾.md:52` 同改 61 | `check_doc_claims.py` ：`钉常量 vs 权威源：29/29 相等` / `RESULT: OK（violations=0）`；`--selftest` 26/26；`ci_gates.py --phase first` exit 0（20 步 / blocking 失败=无）；登记进 `B18-登记.md` |

> ⚠ 执行前提：`/.tmp/` 规则须等 P1–P12 线确认 `.tmp/p1p6p9p10/` 已无复跑需求（否则规则会**隐藏**在途材料）；`.tmp-t6runs/`/`.tmp-t9runs/` 被忽略 ≠ 被删，兼容 §2.2 的保留判定。

- **U-2（not_measured）**：本轮**未执行**任何删除（含 `.tmp/`）——解除条件：P1–P12 线书面确认 `.tmp/p1p6p9p10/` 可弃 **且** 该批产物已提交/归档后，再按「打印解析后绝对路径 → 校验前缀在 `/root/code/MyERP/` → 删除」三步执行；执行前须重取 §2.1 的件数/字节读数（本件读数是 2026-10-12 08:1x 时点快照，该目录 mtime 仍在增长）。

---

## §3 ③ O7 / G-21：多方法（GET+写）规则分批纳入台账

### 3.1 现场读数（命令 + 口径 + 值）

```
/opt/wage-venv/bin/python -B scripts/route_inventory.py            # [multi] 名单来源
/opt/wage-venv/bin/python -B -c "import json;c=json.load(open('test-reports-2026-10/evidence/harness/ci-run-20261012-062243/coverage.json'));print(c['summary']['multi_method_with_get_total'], c['summary']['multi_method_with_get_uncovered'])"
```

| 量 | 值 | 口径来源 |
| --- | --- | --- |
| 多方法（含 GET）规则 | **44** | `coverage.json:summary.multi_method_with_get_total`，与 `route_inventory.py` `[multi]`=44 一致 |
| 其中未命中 | **38** | `coverage.json:uncovered_multi_method_with_get`（形如 `{'rule': '/x', 'endpoint': 'main.x', 'methods': ['GET','POST']}`） |
| 已纳入写面台账 | **1** | `/equipment/<int:id>/layout`（`MODULE_FACE[*]['write_expect']=9` 的 equipment 面内） |
| 显式不纳入 | **13** | auth 3（`/auth/`、`/auth/change-password`、`/auth/logout`）+ 导出 6（`/employees/export`、`/process_prices/export`、`/production_records/export`、`/bonus_penalties/export`、`/export_tasks`、`/products/export`，GET/POST 双支持非写面）+ 查询 POST 4（`/audit_logs`、`/bonus_penalties`、`/salary_calculation`、`/search/advanced`） |
| **待决（本台账对象）** | **24** | = 38 − 1 − 13；⚠ 时点提示：`70-…md` §9.2 G-21 记的「37 条」是**重基线前**口径，同日 `§B18-E-01 ①` 已按 A-70 把 `b17_governance_contract.py` 的 `N==43 / M==37` 抬到 **`N==44 / M==38`** ⇒ 现行一律取 **44 / 38 / 24** |

### 3.2 台账字段与执法机制（现成，不新起工具）

- **`write_expect` 台账**：`scripts/permission_matrix.py:77-89` `MODULE_FACE` 每模块一条，含 `module` / `capability` / `urls`（页面面具名入口）/ `inject_endpoint`（页面面注入靶点）/ **`write_expect`（写端点数台账）**。写端点由 `write_endpoints()`（`:448-465`）从 `url_map` **派生**（不手抄）：`methods - {GET,HEAD,OPTIONS}` 非空 **且** 该视图挂了该 capability。
- **判据**（`permission_matrix.py:713` 计入退出码）：匿名=0 **且** 页面面全绿 **且** 写面全绿 **且** 内联 role 双向 via 白名单；写面 = 逐写端点 ≥1 allow + ≥1 deny、5xx/EXC=0、**写端点数 == `write_expect`（上下漂移都红）**（`:518-519`）。
- **阴性对照（唯一允许的工具面）**：`--inject-write-module <module>`（`:769-771`）= 副本进程内剥掉该模块**首个派生写端点**的 `@require_capability` ⇒ 写面 deny 必须转红；不得新起并行工具。
- **扫描集**：`guard_of_view()` 默认扫 `ROUTE_FILES`；四模块写视图在 `WRITE_ROUTE_FILES`（`:91-94`）⇒ 待决 24 条多在 `app/main/routes.py`，实测**已在扫描集内**（本件分析脚本用 `guard_of_view(tuple(ROUTE_FILES)+tuple(WRITE_ROUTE_FILES))` 一次拿到 24/24 的 capability，无需扩扫描集）。
- **复跑纪律**（`B18-登记.md:855`）：`harness/` 脚本一律在**干净同层目录**、显式 `PYTHONPATH=harness` 复跑；**禁用** `test-reports-2026-10/.tmp/` 原地跑（`_env.py` 影射会给出假读数）。

### 3.3 分批纳入台账（6 批 = 24 条，按 capability 切边界）

| 批 | capability | 条数 | `write_expect` 初值 | 阴性对照靶点（`--inject-write-module`） | 快照规则（`/opt/…/python -B` 后接） |
| --- | --- | --- | --- | --- | --- |
| B-1 | `inventory.manage` | 5 | 5 | 该面首个派生写端点（`/inventory/inbound` 族） | `/inventory/inbound`、`/inventory/raw-material/inbound`、`/inventory/finished-product/inbound`、`/consumables/inbound`、`/material_returns/add` |
| B-2 | `sales_order.manage` | 5 | 5 | 首个派生写端点 | `/sales_order/add`、`/sales_order/<int:order_id>/edit`、`/sales_order/<int:order_id>/item/add`、`/sales_order_item/<int:item_id>/edit`、`/sales_order_item/<int:item_id>/delivery_batches` |
| B-3 | `customer.manage` | 4 | 4 | 同上 | `/customer/add`、`/customer/<int:customer_id>/edit`、`/customer/<int:customer_id>/address/add`、`/customer/<int:customer_id>/address/<int:address_id>/edit` |
| B-4 | `process.manage` + `code_rule.manage` + `notification_rule.manage` | 2+2+1 | 2 / 2 / 1 | 每 capability 各一次（可合并一次 run 逐模块注） | `/add_process_price`、`/process_prices/<int:id>/edit`、`/code_rules/add`、`/code_rules/<int:rule_id>/edit`、`/notification_rules/add` |
| B-5 | `production_order.manage` | 2 | 2 | 首个派生写端点 | `/production_orders/<int:order_id>/edit`、`/assembly/<int:product_id>` |
| B-6 | `employee.manage` + `task.manage` | 2+1 | 2 / 1 | 各一次 | `/employee/add`、`/employees/<int:id>/edit`、`/tasks` |

**每批的 A-70 三步（不可省）**：① 旧值留档 = 现 `write_expect` 表（上表初值 + 每模块 `found_writes` 现值）；② **阴性对照先转红** = `--inject-write-module <module>` ⇒ 期望 `[FAIL] C-06 四模块**写端点**面失败：<module>`、`c06_write_modules_failed=["<module>"]`、exit 1，**其余模块仍绿**（防误伤）；③ 改 `write_expect` 为实测值 + 复跑绿（`permission_matrix.py --no-dump` exit 0 且 `写端点数 == 台账`）+ 登记 `B18-登记.md`。

**靶向性判据（4 条，缺一不算有效阴性对照）**：① 未注入时 `写端点数 == write_expect`（数不符即红，上下漂移都红）；② 注入后**仅**该模块红；③ 全绿时该面每写端点 allow ≥1 且 deny ≥1、5xx/EXC=0；④ `--no-dump` 下**不写任何 evidence 文件**（退出码与落盘解耦，t14 实测）。

> ⚠ **设计约束（实测得来）**：`MODULE_FACE` **双用**（页面面 C-06 + 写面 `write_expect`）。新增「写面专属」条目若 `urls=()`，会让页面面判据出现「0 url 模块」而**假红**。因此每批二选一：a) 该 capability 若已有页面面模块（如 `inventory.manage` 的 stock 面）则**并入既有条目**只抬 `write_expect`；b) 新增条目时**补齐** `urls`/`inject_endpoint` 来自页面面入口。机械护栏 = A-70 第 ③ 步的 `permission_matrix.py --no-dump` 必须 exit 0（假红会在此被抓住）。

### 3.4 待决 24 条逐条（纳入建议 + 机械读数）

口径：`def 块 = 该 def 行至下一顶层 def/装饰器行（不含）`，只计非注释行；`adds` = `db.session.add(` 次数、`commits` = `db.session.commit()` 次数；`gate=True` = 块内有 `validate_on_submit` / `request.method` / `method == 'POST'`。

| 规则 | 端点 | capability | def 行 | adds/commits | gate | 纳入建议 |
| --- | --- | --- | --- | --- | --- | --- |
| `/tasks` | `main.manage_tasks` | `task.manage` | 3350 | 2/1 | ✓ | 纳入（B-6） |
| `/employee/add` | `main.add_employee` | `employee.manage` | 620 | 3/1 | ✓ | 纳入（B-6） |
| `/employees/<int:id>/edit` | `main.edit_employee` | `employee.manage` | 698 | 3/1 | ✓ | 纳入（B-6） |
| `/add_process_price` | `main.add_process_price` | `process.manage` | 910 | 3/1 | ✓ | 纳入（B-4） |
| `/process_prices/<int:id>/edit` | `main.edit_process_price` | `process.manage` | 1037 | 2/1 | ✓ | 纳入（B-4） |
| `/code_rules/add` | `main.add_code_rule` | `code_rule.manage` | 5959 | 2/1 | ✓ | 纳入（B-4） |
| `/code_rules/<int:rule_id>/edit` | `main.edit_code_rule` | `code_rule.manage` | 6012 | 1/1 | ✓ | 纳入（B-4） |
| `/notification_rules/add` | `main.add_notification_rule` | `notification_rule.manage` | 11004 | 1/1 | ✓ | 纳入（B-4） |
| `/inventory/inbound` | `main.inventory_inbound` | `inventory.manage` | 6926 | 4/1 | ✓ | 纳入（B-1） |
| `/inventory/raw-material/inbound` | `main.raw_material_inbound` | `inventory.manage` | 7110 | 2/1 | ✓ | 纳入（B-1） |
| `/inventory/finished-product/inbound` | `main.finished_product_inbound` | `inventory.manage` | 7257 | 2/1 | ✓ | 纳入（B-1） |
| `/consumables/inbound` | `main.consumable_inbound` | `inventory.manage` | 11374 | 2/1 | ✓ | 纳入（B-1） |
| `/material_returns/add` | `main.add_material_return` | `inventory.manage` | 12333 | 3/1 | ✓ | 纳入（B-1） |
| `/production_orders/<int:order_id>/edit` | `main.edit_production_order` | `production_order.manage` | 8832 | 1/1 | ✓ | 纳入（B-5） |
| `/assembly/<int:product_id>` | `main.assemble_product` | `production_order.manage` | `stock.py:36` | **0/1** | ✓ | 纳入（B-5）但**单列**：此条**无 `db.session.add`**（更新型），须在台账里注明「更新型写端点」以免日后被误判为漏抄 |
| `/customer/add` | `main.add_customer` | `customer.manage` | 9801 | 2/2 | ✓ | 纳入（B-3） |
| `/customer/<int:customer_id>/edit` | `main.edit_customer` | `customer.manage` | 9871 | 1/2 | ✓ | 纳入（B-3） |
| `/customer/<int:customer_id>/address/add` | `main.add_customer_address` | `customer.manage` | 9971 | 2/2 | ✓ | 纳入（B-3） |
| `/customer/<int:customer_id>/address/<int:address_id>/edit` | `main.edit_customer_address` | `customer.manage` | 10027 | 1/2 | ✓ | 纳入（B-3） |
| `/sales_order/add` | `main.add_sales_order` | `sales_order.manage` | 10280 | 2/2 | ✓ | 纳入（B-2） |
| `/sales_order/<int:order_id>/edit` | `main.edit_sales_order` | `sales_order.manage` | 10388 | 1/2 | ✓ | 纳入（B-2） |
| `/sales_order/<int:order_id>/item/add` | `main.add_sales_order_item` | `sales_order.manage` | 10478 | 2/1 | ✓ | 纳入（B-2） |
| `/sales_order_item/<int:item_id>/edit` | `main.edit_sales_order_item` | `sales_order.manage` | 10594 | 1/1 | ✓ | 纳入（B-2） |
| `/sales_order_item/<int:item_id>/delivery_batches` | `main.manage_delivery_batches` | `sales_order.manage` | 10740 | 1/2 | ✓ | 纳入（B-2） |

- **纳入建议 = 24/24 纳入**（无一条被建议排除）：全部满足「有写方法 + 挂 `@require_capability` + 有 POST/表单门 + allow/deny 可断言」；`adds=0` 的更新型 1 条（`assemble_product`）不构成排除理由（写面判据是 deny/allow 与计数，不要求 `add`）。
- **行号口径**：上表 `def 行` 为**工作区帧**（`app/main/routes.py` 现盘 12825 行；`app/main/stock.py` 帧 sha256 `53fa1843…`）——t14 已确立「帧 = HEAD + 未提交改动」的记账方式，本表沿用。
- **U-3（not_covered，不折算 pass）**：24 条**本轮全部未纳入**（任务明写不要求实现）⇒ 写面 deny 对它们仍是空白；解除条件 = 逐批执行 §3.3 的 A-70 三步并登记（批间可并行，但**同一 capability 面一次只改一版**）。

---

## §4 ④ G-13 / G-15 三载体 / G-18（附 G-19）

### 4.1 G-13「本轮未复跑 V-03/V-05/V-06/V-07 探针」

- **命令/口径**：`sed -n '455,462p' test-reports-2026-10/70-第2轮收口与阶段C移交.md`（在册行）+ `ci_gates.py` 步表（本件 §4.2 的表）。
- **读数**：`70-…md:462` = `not_covered`，「保持（V-17 **亦未复跑**；理由 = A-40 复跑须 `preflight` + `A-98` 并发风险；`ci_gates` 已覆盖 `permission_matrix(blocking)` 与 `coverage_drift(blocking)` 两条执法面）」。
- **判定**：**保持 `not_covered`（不折算 pass）**。判据落点 = ① `permission_matrix`（blocking，`scripts/permission_matrix.py`，判据「匿名=0 且 C-06 页/写面全绿且内联 role 双向」`exit_code_semantics` 就写在 `:740-750`）；② `coverage_drift`（blocking，8 面 `LOCKED` 下界）；③ `functional_test` / `smoke_test`（后者 report-only + `SMOKE_PROMOTION_NOTE` 记 A-63 第二步）。
- **解除条件**：四条探针按 A-40 口径复跑（须 preflight + 遵守 A-98 并发纪律），或由 captain 明写「探针价值已由 ①② 替代」并改状态（改状态须同步 `70` 与登记件）。

### 4.2 G-15「TL-05/06/07 终态未收口（注入面未实测）」

- **命令/口径**：`ci_gates.py --selfcheck`（步表 + 组别）＋ `test-reports-2026-10/C-注入面与锚点实测.md`（t3 的三条注入面实测读数）＋ `--inject-step` 注入形态 ⑦（`ci_gates.py:793-799` / `:59`）。
- **读数（三载体是否在 blocking 链内）**：

| 载体 | 门禁步 | 组 | 注入形态 | 实测读数 |
| --- | --- | --- | --- | --- |
| TL-05 类级+实例面 属性门禁（`scripts/check_properties.py`） | 步 4 `check_properties` | **blocking** | `real_input`：`--root <合成坏树>` | 默认跑：`已扫描 25 个文件，模型类 74 个` → `RESULT: OK`；注入后 **exit 1** 且指名 `tl05/bad_inst.py:6 [实例访问了该类不存在的属性] e.not_a_column`（t3 §1） |
| TL-06 口径守卫（`scripts/check_doc_claims.py`） | 步 20 `check_doc_claims` | **blocking** | `real_input`：`--coverage` 指向归档锚点副本（口径源 −1） | 默认（`--coverage <本 run>`）：`钉常量 vs 权威源：29/29 相等` → `RESULT: OK（violations=0）`；注入后 **exit 1**（t3 §2） |
| TL-07 依赖钉版（同脚本 `--lock`） | 步 20 同一步（`check_lock()` 在 `:509`，`--lock` CLI `:749`） | **blocking** | `--lock /nonexistent/requirements.lock` | **exit 1**，`requirements.lock 不存在：…（TL-07：删 lock ⇒ 非 0）`（t3 §3） |

- **判定**：**G-15 可判「闭合」**——① 三载体**都在** `ci_gates --phase first` 的 blocking 链内（步 4 / 步 20，`--selfcheck` 报 `step_count=20 failed=无`）；② 三条注入面**均已实测转红**并留档（`C-注入面与锚点实测.md`，2026-10-12 04:4x UTC，同日同解释器）；③ 注入面「判据未被改动」由 `ci_gates --inject-step` 的 `criterion_unchanged=True` 机械保证。
- **残留（不算 pass）**：`70-…md:469` 的 G-15 行仍是 `in_progress` + 「注入面未实测」措辞 ⇒ **陈旧**；建议下轮改状态时同步（改 `70` 须 append-only 注记）。

### 4.3 附带：G-19（`not_covered` → 现场已闭合）

- **在册**：`70-…md:471` = `not_covered`「`permission_matrix` 按设计只扫 GET ⇒ 四模块**写端点面**未断言（补打须在同工具内加方法参数化 face，**不得新起并行工具**）」。
- **现场读数（2026-10-12）**：`permission_matrix.py --no-dump` = **exit 0**，`[OK] C-06 四模块写端点面 = 全绿（21 写端点：逐端点 ≥1 allow + ≥1 deny，5xx/EXC=0）`、`c06_write_modules_failed=[]`；阴性对照 `--inject-write-module equipment` = **exit 1**（`[FAIL] POST /equipment/<int:id>/downtime … deny=-`、`c06_write_modules_failed=["equipment"]`）⇒ **B17-13 已按当时口径在同一工具内补打完成**。
- **判定**：「写端点 deny 未断言」对**四模块 21 端点**已闭合；**仍未覆盖**的是 §3 的 24 条（不同 capability 面）⇒ 两件事不得混为一谈（G-19 可建议改 `closed`，G-21/O7 仍 `not_covered`）。

### 4.4 G-18「改动面在收口时点仍在增长」

- **命令/口径**：`70-…md:472`（在册）+ `70-…md` §8.5 captain append（同一日实测序列 `工作区面 25 → 27 → 35 → 36`、`evidence/** 10737→10763 件`、`.tmp/** 5775→17208 件`、定稿读数 `68 文件 / 2,786,534 B`，工具 `.tmp/r2-exec-b5-v17/_v17_inventory.py`）。
- **读数（本容器实测）**：`/opt/wage-venv/bin/python -B test-reports-2026-10/.tmp/r2-exec-b5-v17/_v17_inventory.py` ⇒ **rc=1**，
  `FileNotFoundError: [Errno 2] No such file or directory: 'D:\\workspace\\wage_management_system - bak/app.db'`（脚本 `:61`，Windows 绝对路径硬编码）⇒ **该工具在本环境不可运行**；`git status --porcelain` 本时点 = 6 条 `??` + 3 条 `M`（`app/main/forms.py`、`scripts/check_doc_claims.py`、`test-reports-2026-10/harness/b17_governance_contract.py`）⇒ 现场确有并行改动面。
- **判定**：**按设计接受「清单 = 时点快照」（非终态）**，并把「终态化」交给**机制**而不是再抄一遍数字：① `check_doc_claims` 的 `real_db_sha256` / `real_db_bytes` 钉值（改动一落盘即对拍）；② `ci_gates_steps`=20 钉值；③ `evidence_hash`（report-only，入册 blocked）。**不建议**把「改动面文件数」设为 PINNED（它每次提交必漂，会把 A-70 变成日常动作）。
- **U-4（not_measured）**：G-18 的**重跑读数本轮缺**（工具不可运行）⇒ 解除条件 = 把 `_v17_inventory.py:61` 的 Windows 绝对路径改为 POSIX/仓库相对（或改用现成口径重写），在**定稿时点**重跑并把「§8 清单 + 时点戳 + 该跑 run_id」一次性写死。

---

## §5 未测项与解除条件汇总

| ID | 项 | 状态 | 解除条件 |
| --- | --- | --- | --- |
| U-1 | A-63 第二步「观测 1 轮构建全绿」 | `not_measured`（本容器无构建执行面） | captain 在有 Jenkins/GH 执行面处执行 §1.4 a/b，观测 1 轮后改 `state` |
| U-2 | 根 `.tmp/` 的删除动作 | `not_measured`（在途 scratch：`p1p6p9p10/` 最新 05:23） | P1–P12 线书面确认可弃 + 该批产物归档 → 三步入库外删除（打印绝对路径 → 校验在仓内 → 删） |
| U-3 | 24 条多方法规则的写面断言 | `not_covered`（任务不要求本轮实现；已给分批台账） | 逐批执行 §3.3 A-70 三步 + 登记 |
| U-4 | G-18 重跑读数 | `not_measured`（`_v17_inventory.py` 在 Windows 路径上死） | 工具改 POSIX 路径后于定稿时点重跑，写死清单 + 时点戳 |
| U-5 | `BUILD_LAYER_BLOCKED` 内 GH 行号（`:19`/`:58`） | `asset_defect`（低） | A-63 第二步顺手同步为 `:36`/`:105-106`（并同步引用该文件 SHA 的文档） |
| U-6 | 真库三值 | **已核（开工 + 收工，恒等）** | — |

---

## §6 一键复跑（本件全部判据）

```bash
cd /root/code/MyERP
# ① O2：登记 + 断言 + 在链
grep -n 'BUILD_LAYER_BLOCKED\|A-63-STEP2\|gaps.: \[BUILD' test-reports-2026-10/harness/ci_gates.py
/opt/wage-venv/bin/python -B test-reports-2026-10/harness/ci_gates.py --selfcheck   # 期望 exit 0 / step_count=20 / failed=无
sed -n '108,126p' Jenkinsfile
grep -n 'continue-on-error\|build-and-push\|needs:' .github/workflows/docker-deploy.yml
# ② 污染面：6 项 × 机械读数
git status --porcelain
for p in .tmp .vscode/settings.json app.db.evidence-ALLOY-IMPORT-02-20261009_004539 instance test-reports-2026-10/.tmp-t6runs test-reports-2026-10/.tmp-t9runs; do git check-ignore -v "$p" || echo "NOT ignored: $p"; git ls-files -- "$p" | wc -l; done
# ③ O7/G-21：现场 44/38/24
/opt/wage-venv/bin/python -B scripts/route_inventory.py | tail -5
/opt/wage-venv/bin/python -B test-reports-2026-10/.tmp/t19-closeout/analyze_pending24.py   # 24 条 + capability 分组
# ④ G-13/G-15/G-18/G-19
/opt/wage-venv/bin/python -B scripts/permission_matrix.py --no-dump                      # 期望 exit 0（写面 21 全绿）
/opt/wage-venv/bin/python -B scripts/permission_matrix.py --no-dump --inject-write-module equipment   # 期望 exit 1（仅 equipment 红）
/opt/wage-venv/bin/python -B scripts/check_doc_claims.py --selftest                      # 期望 26/26
/opt/wage-venv/bin/python -B test-reports-2026-10/.tmp/r2-exec-b5-v17/_v17_inventory.py  # 期望 rc=1（Windows 路径，U-4）
# 真库三值（前后各一次）
sha256sum app.db && stat -c '%s %y' app.db
```

## §7 证据路径（本地留档；`evidence/**` 与 `.tmp/**` 均被 ignore，不入库）

- 本件读数落盘：`test-reports-2026-10/.tmp/t19-closeout/`（`dc_before.out`、`dc_selftest_before.out`、`route_inventory.txt`、`pending24.json`、`analyze_pending24.py`）
- 门禁 run 产物：`test-reports-2026-10/evidence/harness/ci-run-20261012-080129/`（`--selfcheck` JSON，含 §1.2 断言行）；`…/ci-run-20261012-062243/`（20 步 run console，含 `gaps` 块与 `check_doc_claims 5/5`）
- t3 注入面读数：`test-reports-2026-10/C-注入面与锚点实测.md`（TL-05/06/07 三条注入面 + G-16①）
- 在册行：`70-第2轮收口与阶段C移交.md:462/469/471/472`；`B18-05-批次收口台账.md:89`；`B18-登记.md:741/803/807/848/855`；`docs/验收记录-批次18-2026-10-11.md:185`

## §8 硬约束与边界声明

- **真库（开工与收工各一次，两次恒等）**：开工 `2026-10-12 07:5x UTC` / 收工 `2026-10-12 08:07 UTC`（本件与 `§B18-E-02` 落盘之后）—— `sha256sum app.db` = `34e48e7a21163db390eebda4f2030343f3609afedc65d8c6e909d6eb5a49177e`、`stat -c '%s %y'` = `2531328 2026-10-12 04:25:37.128430119 +0000`（两次逐字符相同）。**未**跑 `flask db migrate/upgrade`，**未**写 `app.db`。
- **append-only**：本件为**新建**件；对既有件的唯一动作 = 向 `test-reports-2026-10/B18-登记.md` **追加** `§B18-E-02`（不改既有行）。
- **判据**：**未改**任何判据/钉值/期望值 ⇒ 无需 A-70（§2.3 给出的是**留给下轮**的执行模板，本轮未执行）。
- **未跟踪**：本件与 `§B18-E-02` 追加均为工作区改动，**未 `git add` / 未 commit / 未 push**（提交由 captain 按白名单逐条执行）。
- **本任务创建的 evidence 侧新目录**：`test-reports-2026-10/evidence/harness/ci-run-20261012-080129/`（由标准入口 `ci_gates.py --selfcheck` 生成，属工具标准输出，非人工改写）。
