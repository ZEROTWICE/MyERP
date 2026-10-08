# 业务口径与产品问题对账（Q-1…Q-4 落地 + P1–P12 分级与验收判据）

- **任务**：`t6 [W5]`（attempt 5，`a61c46d9-ada8-4f60-bd8b-18b26bfcc0ea`）｜**执行者**：产品经理2
- **时点**：2026-10-08｜**工作目录**：`D:\workspace\wage_management_system - bak`
- **解释器**：`F:\Miniconda\envs\wage\python.exe`（3.9.21）
- **唯一事实来源**：当前工作区**源码**。文档行号一律只作「计划给的原行号」引用，**不作事实**。
- **只读纪律**：仓库内**未修改任何既有文件**（`app/`、`app/templates/`、`scripts/`、`docs/`、`AGENTS.md` 全只读）。
  新增产物仅 4 个（全在 `test-reports-2026-10/reconcile-2026-10-08/`）：本文件、
  `probe_product_piecework.py`、`probe_product_doc_anchors.py`、`probe_product_import_endpoints.py`、
  `probe_product_appendixB.py`（各带同名 `.output.json` 机读件）。
- **真实库不变量**：`app.db` = `2531328 B` / `F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065` /
  mtime `2026-09-18 12:50:55` —— **开工与收尾两次 Hash + mtime 逐位一致**；全部写入发生在
  `scripts/_test_bootstrap.make_app(fresh=True)` 复制的临时副本上（副本路径见各探针 output 的 `copy_path`）。

---

## 0. 一页结论

| # | 结论 | 依据（工具 + 口径 + 值） |
| --- | --- | --- |
| **C-1** | **Q-1（已入库产出判不合格 ⇒ 阻断+登记，不自动回退）：已落地，但**「阻断」在报工路径上**只靠 `quality_status='fail'` 一根柱子**；「有在办单据也拦」这根柱子**在报工路径结构性不可达** | 探针 `probe_backend_field.py`：fail 后 `nc_rows_delta=1`、`quality_status` **NULL→fail**、门禁 `allowed=false`；结构侧 `mes_service.py:351` 调门禁时**不传** `production_record` |
| **C-2** | **Q-2（返工默认不计件）：已落地且**行为级双向可证**；但**识别口径已由 `07b` DEC-2 §2.2 改判**——**不是** Q-2 原文的「notes 前缀」，而是 R1 `rework_task_id` → R2 `global_sn` | 探针 `probe_product_piecework.py`：开关 false→true，`S1 60→160`、`S2 2060→2160`、`S3 60→160`、`S4 60→160`；非返工记录两态均 `60.0`（阴性对照通过）；`mes_service.py:1761-1834` 为唯一读取点 |
| **C-3** | **Q-3（`/production_center` 实例完工是否入正品库）：本批不含，现状符合**——该路径**完全不写** `FinishedProduct` | `app/main/production_center.py` 全文 `grep -i inbound/finished_product/stock_kind` = **0 命中**；`api_execute_operation`（`:309-…`）只建 `ProductionRecord` + `notes` 软关联 |
| **C-4** | **Q-4（对已完成任务部分报工 ⇒ 保留现状 + 页面提示更正路径）：**`保留现状` 已成立，`页面提示` **未落地**（0 命中）** | `app/templates/**` 全量搜 `部分报工/重新报工/删生产记录/更正/未完成质检` = **0 命中**（工具=Python 逐行读，口径=子串命中，值=0） |
| **C-5** | **P1–P12：仍存在 11 条**（P1–P10 + P12），**P11 原载体已消失**（同族新残留 `_probe_tmp/` 已登记，属测试资产不是产品缺陷） | 独立复现见 §3；与 `recon-backend.md` §5 逐条一致（**本次已独立重跑 P1/P9 载体与行为**，非转述） |
| **C-6** | **本次唯一新发现的「口径级」结构性缺口**：`inbound_production_output`（`mes_service.py:351`）调 `qc_gate_allows_output(batch_item=item, workpieces=workpieces)` **漏传 `production_record`** ⇒ 报工路径上 `record_ids` 恒空 ⇒ 门禁**序 3/序 4** 永不生效 ⇒ `07b` DEC-1 §1.4 序 3 的「确有在办单据才拒」**在报工路径上无法判定**（当前表现为**放行**，即 fail-open） | 代码：`mes_service.py:176-180`（`record_ids` 来源）+ `:351`（唯一调用点不传 `production_record`）+ `:3712-3717`（调用方也不传）；行为：`probe_backend_field.py` J 组 `gate_without_production_record_report_path = {allowed: true, reason: null}` vs `gate_with_production_record_qc_domain = {allowed: false, reason: '产出存在未完成的质检任务…'}` |
| **C-7** | **业务视角优先级与技术视角有 3 处显式冲突**（P9 该上 P0、P2/P5 该并入而非单列、门禁时序该先钉口径再改代码） | 见 §4 |

---

## 1. Q-1…Q-4 落地核查

> 口径说明：**「已落地」= 有可运行代码路径且**行为级**可复现；「部分」= 主干成立但有结构性缺口；
> 「未落地」= 0 命中。**不把「有配置项」当「开关生效」**，故下表全部给出**行为读数**或**结构读数**。

### 1.1 Q-1｜产出已入正品库后才判不合格 ⇒ 阻断后续 + 登记不合格，不自动回退

**原文口径**（`docs/交接提示词-批次3开工-2026-10-06.md:47`）：
> **Q-1** 产出已入正品库后才被判不合格 → **A：阻断后续 + 登记不合格，不自动回退**（B 自动回退需先做「产出行按次拆分」）。

| 子判据 | 源码落点（实测行号） | 状态 | 证据 |
| --- | --- | --- | --- |
| ① 登记不合格（建 `NonconformityRecord`，`target_type='production_record'`） | `mes_service.py:621-639`（`apply_production_record_result`，`db.session.add(NonconformityRecord(...))` 在 `:624`） | **已落地** | 行为：`nc_rows_delta=1`，`nc_created={id:1, target_type:'production_record', target_id:1, workpiece_id:null, status:'open', type:'rework'}` |
| ② 写 `quality_status='fail'`（复算写点唯一） | `mes_service.py:640` → `:553-598`（`recompute_production_quality_status`）；`db.session.flush()` 在 `:636` | **已落地** | 行为：`written_quality_status='fail'`，库字段读出 `quality_status='fail'` |
| ③ **阻断后续**（再次报工不入正品库） | `mes_service.py:351` 门禁 + `:199-200`（`fail` 分支） | **部分落地** | 行为：`gate_after_fail={allowed:false, reason:'实例 … 质检不合格，不得入正品库'}` ✅；**但阻断只由 `quality_status` 承担**（见 ④） |
| ④ 「存在未闭环不合格单 / 在办质检任务」也拦（`07b` DEC-1 §1.4 序 4） | `mes_service.py:184-194`（`record_ids` 组装）→ `:209-212`（拒绝） | **报工路径不可达** | 结构：唯一调用点 `:351` 写 `qc_gate_allows_output(batch_item=item, workpieces=workpieces)`，**`production_record` 缺省 `None`**；而 `batch_item_production_records`（`:148-154`）按 `notes.contains('"batch_item_id": N')` 反查，**报工端点创建的 `ProductionRecord` 不写 notes**（`routes.py:3399-3405` 只传 `employee_id/process_id/quantity/global_sn/date`）⇒ `record_ids=[]` ⇒ `pending_task`/`open_nc` 恒 `None` |
| ⑤ **不自动回退**（不把已入库产出转走） | 全仓无「按次拆分」实现；处置分支只改字段与状态（`mes_service.py:1055-1143`） | **已落地（= 未做自动回退）** | `grep 'create_task_split|按次拆分|auto_reverse'` **0 命中**；与 `docs/开发与测试规划-2026-10-06.md:784` N-11「不做产出行按次拆分」一致 |
| ⑥ 处置闭环后**自动复位**（`07b` DEC-1 §1.5-4，是 ③ 不变成死锁的必要条件） | `mes_service.py:646-670`（`reset_quality_status_after_disposal`），在 `accept`(`:1066`)/`rework`(`:1118`)/`scrap`(`:1142`) 三支调用 | **已落地** | 行为：`gate_after_rework_done={allowed:true, quality_status:'pass'}`；`scrap` 走终态 `:1138 item.status='scrapped'` ⇒ 仍拒（`:201-202`）✅ |

**⚠ 部分落地的最小修法（本节核心建议）**

- **问题**：`07b` DEC-1 §1.4 序 3 要求「`pending` 只在**确有在办单据**时才拒」，前提是门禁**看得见**在办单据。
  报工路径上它看不见（`record_ids` 恒空）⇒ 该分支**静默失效**，等价于「放行」。
  这是 **fail-open**：批次数一多，`pending` 就会被当作 `NULL` 处理。
- **最小落地方案**（改 1 个函数、2 行）：
  - `app/services/mes_service.py:351` 改为
    `allowed, reason = qc_gate_allows_output(batch_item=item, workpieces=workpieces, production_record=production_record)`；
  - `inbound_production_output` 的入参处（签名在 `:325` 附近）补可选参数 `production_record=None`，
    由调用方 `routes.py:3712-3717` 传「本次报工刚建的 `production_record`」（该对象在 `:3399` 已存在且已 `flush`）。
  - 若不愿改签名：在 `:351` 之前用 `ProductionRecord.query.filter_by(global_sn=task.global_sn).first()` 就地取，
    但**必须**保留 `production_record=None` 时「只按 `quality_status` 判」的既有语义并记 `logger.warning`（不得静默）。
- **验收怎么测（可判定，含双侧对照）**：

  | # | 场景 | 阳性对照（必须拒） | 阴性对照（必须放行） |
  | --- | --- | --- | --- |
  | A-1 | 实例 `quality_status='fail'` | 再次报工 ⇒ `finished_product(stock_kind='fg')` **Δ=0** 且 `reason` 非空 | 同实例处置 `rework` 到 `done` 后报工 ⇒ **Δ>0** 且 `quality_status='pass'` |
  | A-2 | 实例 `quality_status=NULL` 但**挂有在办** `InspectionTask(target_type='production_record')` | 报工 ⇒ **Δ=0**，`reason` 含「未完成的质检任务」 | 把该质检任务置 `completed` 后报工 ⇒ **Δ>0** |
  | A-3 | 实例 `quality_status=NULL`、无任务、无 NC（回归基线） | — | 报工 ⇒ **Δ=+N**（当前基线 `+4`，不得回归） |

  > A-2 是**当前必红**的格子（fail-open 的直接证据）。修复前**不得**把「Q-1 已落地」写成无条件成立。

- **口径建议**：Q-1 的 A 方案应**显式写明**「阻断 = `quality_status` 拒 + 在办单据拒，二者都必须生效」，
  否则实现方会只做前者（现状），而验收方按后者验，形成「文档说过了、代码没做、测试没盖」的三不管地带。

---

### 1.2 Q-2｜返工工时默认不计件（false），用既有 notes 前缀识别，不新增列

**原文口径**（`docs/交接提示词-批次3开工-2026-10-06.md:48`）：
> **Q-2** 返工工时是否重复计件 → **默认 `false` 不计件**，用既有 `notes` 前缀识别，**不新增列**。

| 子判据 | 源码落点（实测行号） | 状态 | 证据 |
| --- | --- | --- | --- |
| ① 默认值 `false`（配置种子） | `models.py:2605-2611`（`'key': 'quality.rework_counts_piecework'`, `'value': 'false'`） | **已落地** | 直读源码 |
| ② **唯一读取点**（防「假开关」） | `mes_service.py:1761-1766`（`rework_counts_piecework()`）→ 唯一调用方 `:1815`（`piecework_breakdown`） | **已落地** | `grep rework_counts_piecework` 全仓 Python 赋值/读取点 = **1 处读取**（其余为文档/探针）；代码注释 `:1746-1749` 明文自称唯一读取点 |
| ③ **不新增列** | `grep 'is_rework'` 全仓 Python = **0 命中** | **已落地** | 判定完全走既有字段（`NonconformityRecord.rework_task_id` / `global_sn`） |
| ④ **默认不计件**（false 时剔除返工记录） | `mes_service.py:1812-1824`（`piecework_breakdown`：`excluded = set() if rework_counts_piecework() else rework_production_record_ids(records)`） | **已落地（行为级）** | 探针 `probe_product_piecework.py`：`false` ⇒ 计入 `60.0`（仅非返工 3 件×20）；`true` ⇒ `160.0`（+5 件×20）；**Δ=100.0** |
| ⑤ **S1/S2/S3/S4 同口径**（`07b` DEC-2 §2.5；防「主表变了、员工总工资没变」） | S1 `routes.py:1822`；S2 `models.py:148-158`（`:154`）；S3 `routes.py:400`；S4 `routes.py:409` | **已落地（行为级，本次新证）** | 探针读数（副本库）：`S1 60.0→160.0`、`S2 2060.0→2160.0`、`S3 60.0→160.0`、`S4 60.0→160.0`，四条**全部 Δ≠0** |
| ⑥ **阴性对照：非返工记录两态不变** | `mes_service.py:1818-1823` | **已落地** | 探针：非返工贡献 `off=60.0 / on=60.0` ⇒ `nonrework_unchanged=true` |
| ⑦ **识别口径 = 反查优先（R1→R2），禁用 `task_type` 单判** | `mes_service.py:1769-1809`（`rework_task_ids` / `rework_task_global_sns` / `rework_production_record_ids` / `is_rework_task` / `rework_hint`） | **已落地，但与 Q-2 原文口径不同** | 探针夹具给足 `task_type='auto'` + notes 前缀 + `rework_task_id`，识别结果 `R1R2_identified=[2]`（返工记录）、`R3_hint_only=true`（仅提示） |

**⚠ Q-2 原文口径已被 `07b` 取代（必须登记，否则下一轮会按原文核验而判错）**

| 项 | Q-2 原文 | `07b` DEC-2 §2.2 裁定（今日实现） | 处置建议 |
| --- | --- | --- | --- |
| 识别方式 | 「用既有 `notes` 前缀识别」 | **R1 `NonconformityRecord.rework_task_id == task.id`（主）→ R2 `global_sn` 相等（次）**；notes 前缀降为 **R3 人工可读提示，不参与判定** | **以 `07b` 为准**；`docs/交接提示词…§五` Q-2 行需加「识别口径已由 `07b` DEC-2 §2.2 更正」 |
| 为什么必须改 | — | 报工端点创建的 `ProductionRecord` **不写 notes**（`routes.py:3392-3398`，实测位置 `:3399-3405`）⇒ notes 前缀**无数据源**，等于空判据（`07b` §2.2 表第 2 行「明确否决」） | 同上 |
| 危害 | — | 若照原文实现，返工记录**永远不会被识别** ⇒ 开关形同虚设 ⇒ 返工工时**照旧重复计件**（工资多付） | 高（资金） |

> 结构化风险评估见 `recon-backend.md` §7-1；本报告从**业务口径**角度确认：**`07b` 的口径是对的，
> Q-2 原文的识别方式是不可实现的**。二者不是「两种可选方案」，而是「一个能跑、一个跑不了」。

---

### 1.3 Q-3｜`/production_center` 实例完工是否入正品库 —— 本批不含

**原文口径**（`docs/交接提示词-批次3开工-2026-10-06.md:49`）：
> **Q-3** `/production_center` 实例完工是否入正品库 → **本批不含**，一致性放批次10–11。

| 子判据 | 源码落点（实测行号） | 状态 |
| --- | --- | --- |
| ① 该路径**不写** `FinishedProduct` | `production_center.py` 全文：`grep -i 'inbound\|finished_product\|stock_kind'` = **0 命中** | **已落地（= 未做入库）** |
| ② 该路径只建 `ProductionRecord` + `notes` 软关联 | `production_center.py:335-342`（`ProductionRecord(... notes=record_notes)`），`record_notes = json.dumps({'batch_item_id': item.id})` 在 `:333` | **符合现状** |
| ③ 该路径**不触发**质检/门禁 | `grep 'qualit\|inspection\|qc_gate' production_center.py` = **0 命中** | **符合现状**（即该路径产出**完全绕过质检闭环**） |

**业务风险与口径建议**

- **风险（中）**：走 `/production_center` 完工的批次，**既不入正品库、也不过质检门禁** ⇒ 若一线把生产中心当主入口，
  则「质检门禁」这一整条闭环对该路径**完全不存在**。`recon-backend.md` §1 也指出报工链的门禁才刚落地。
- **建议选项**：
  - **（推荐）维持「本批不含」**，但必须**在界面显式标注**：「此入口完工不生成正品库记录，正式入库请走任务报工」；
    并在 `docs/业务流程现状与缺口.md` 的口径表登记「生产中心 = 执行记录域，非库存域」。
  - 若要补入库：**必须先解决给谁建质检结论**（该路径无任务、无 `TaskAssignment`，`07b` §1.7 的 `global_sn` 定位链**取不到**），
    成本量级 = **中高**（需新增定位约定或新增列 ⇒ 触碰 AGENTS.md「禁止 `flask db migrate`」纪律）。
- **验收判据（可判定）**：
  - 现状基线（阳性）：`POST /api/production_center/items/<id>/execute_operation` 后
    `finished_product` 表**总行数 Δ=0**，且 `inspection_tasks` 表 **Δ=0**；
  - 若未来拍板要入库，则改为：同一请求后 `finished_product(stock_kind='fg')` **Δ=+1**，
    且该行可被 `/api/quality/...` 的质检结论追溯到（`target_type='production_record'` 命中）。

---

### 1.4 Q-4｜对已完成任务部分报工 —— 保留现状 + 页面提示更正路径

**原文口径**（`docs/交接提示词-批次3开工-2026-10-06.md:50`；规划 `:799`）：
> **Q-4** 「对已完成任务部分报工」→ **保留现状** + 页面提示更正路径。

| 子判据 | 源码落点（实测行号） | 状态 | 证据 |
| --- | --- | --- | --- |
| ① **保留现状**（不禁止） | `routes.py:3285-3288`（端点）→ `:3377-3395`（达量分支：`if completed_quantity >= task.quantity:` → `task.status='completed'`）→ `:3529-3531`（`else: task.status='in_progress'`） | **已落地** | 结构：未达量提交**不报错**，且会把已 `completed` 的任务**改回 `in_progress`**（`:3531`）——这就是「部分报工」的真实现状 |
| ② 重复达量报工被幂等拒绝（既有保护） | `routes.py:3383-3394`（`existing_record` → 400「请勿重复提交」） | **已落地** | 直读源码；`global_sn` 为报工链唯一关联键（`:3379-3382` 注释明文） |
| ③ **页面提示更正路径** | `app/templates/**` 全量搜 `部分报工/重新报工/删生产记录/更正/未完成质检` | **未落地** | 工具=Python 逐行读全模板，口径=子串命中，**值=0 命中** |

**最小落地方案**

- **落点**：报工弹窗所在模板（`app/templates/main/my_tasks.html` 或 `tasks.html` 的报工表单区块）加**静态提示**，
  或在报工响应里带可读提示。**不建议**为它改后端状态机（那会把 Q-4 从「保留现状」变成「禁止」）。
- **建议文案**（业务口径，需与 `07b` 的复位提示风格一致）：
  > 「任务已完成但需补报时：请先删除该任务的生产记录，再重新报工。直接再次提交会把任务状态退回「进行中」，不会重复计件。」
- **验收判据（可判定）**：
  - **阳性对照**：对 `status='completed'` 的任务提交 `completed_quantity < quantity` ⇒
    响应 `success=true` 且 `task.status` **由 `completed` 变为 `in_progress`**（现状行为，不得被静默改掉）；
  - **阴性对照**：对同一任务重复提交**达量**数量 ⇒ **HTTP 400** 且响应含「请勿重复提交」，
    且 `production_records` **Δ=0**、`raw_material.quantity` **Δ=0**（不重复扣料、不重复计件）；
  - **文案面**：模板渲染后 DOM 含上述提示句（可用字符串断言）。

---

## 2. 附录 B 其余 11 组待拍板项

> 15 组中 Q-1…Q-4 = G-I / G-C(关联) / G-N(范围) / G-O（规划 `:790-799` 的「阻塞开发 4 条」）。
> 其余 11 组逐条如下：**当前实现是什么 → 业务风险 → 建议选项 → 不拍板默认路径是否仍成立**。
> 另附 §7.1「明确不做」清单的今日复核（**14/15 仍成立**，1 条与实测冲突）。

| 组 | 当前实现（实测 file:line / 命令读数） | 业务风险 | 建议选项 | 不拍板默认路径是否仍成立 |
| --- | --- | --- | --- | --- |
| **G-A** 采购完整流程与对账是否启用 | 开关**双 false** 且**有读取点**：定义 `models.py:2582/2590`；读取 `purchase.py:20`（`_full_workflow`）、`:24`（`_settlement_on`）；实际执法 `purchase.py:490`（`if not _settlement_on(): flash('对账付款未启用')` + redirect） | **中**：关闭期间「请购→对账付款」无页面入口，一线若按完整流程作业会卡住；`settle` 端点存在但被开关挡住（**不是**缺功能） | **维持关闭**（与默认一致）；若要试点，只开 `full_workflow_enabled`，`settlement_enabled` 涉及资金留到最后一档 | **成立**（`functional_test.py:26-56` 已覆盖开关读写与恢复） |
| **G-B** `delivery_batches` 是否升级为驱动发货 | 现状 = **视图/存档**：模型列 `models.py:1716`（JSON）+ 读写属性 `:1784-1797`；CRUD 路由 `routes.py:10058-10118`（页面 + JSON 读写）；**发货模块 0 引用**（`grep delivery_batches` 在 `shipping.py` **0 命中**） | **中**：分批计划与实际发货**两张皮** ⇒ 超发/漏发无系统约束（与 C-04「整单发货超发」同族） | **只做对照视图**（默认）；若要驱动发货，须先定义「计划变更审批」（当前无） | **成立**；但建议**加一句页面口径说明**（否则一线会以为已联动） |
| **G-C** 计件工资是否与质检结果挂钩 | **未挂钩**：`piecework_breakdown`（`mes_service.py:1812-1824`）只按「是否返工」过滤，**不看任何质检字段** | **中高（资金）**：不合格产出仍照常计件 ⇒ 返工/报废工时与合格工时同价 | **暂不挂钩**（默认），但**登记为「质量成本」需求**并给出目标：不合格产出计件 = 合格件数 × 单价（与 `07b` 的四值语义对齐） | **成立**；**注意**：与 Q-2 是**两个不同问题**（Q-2 解决「返工是否重复计件」，G-C 解决「不合格是否计件」），不得混为一谈 |
| **G-D** 编码规则/流水号日志查询页 | 现状 = **有模型、有写入、无查询页**：`CodeGenerationLog`（`models.py:732`）、写入点 `models.py:1031` + `routes.py:5518`；`grep CodeGenerationLog.query` = **0 命中**（无任何读取/列表页） | **低**：流水号可追溯但要人肉查库；合规审查时不便 | **需要**（默认）：只读列表 + 按 `rule_id/时间/用户` 筛选 | **成立**（不排期即维持「有日志无页面」） |
| **G-E** 删除客户的关联订单处理 | 现状 = **允许裸删**：`routes.py:9258-9296`（`delete_customer`），`:9267-9268` 明写 `# 检查是否有关联的订单或其他业务数据` / `# TODO: 添加订单关联检查`，随后**直接** `db.session.delete(customer)`（`:9293`） | **高（数据完整性）**：客户有销售订单时删除 ⇒ 孤儿订单（`models.py:1666` 反向关系可变 `None`）；且审计 `rollback_type='delete'` 只回写 `Customer` 主字段（`:9271-9278`），**不回写子表** ⇒ 回滚不可能完整 | **按默认实施**：禁止删除有订单客户（**400 + 提示**），只允许「停用」（`status` 置非 active）。**注意**：该 TODO 与 `07b` §3-3「不新增列 > 新增列」不冲突（无需新列） | **成立**；**但必须补一句**：当前是**允许删除**，若暂不实现则默认路径**不是**「按默认实施」而是「保持允许删除」——**默认路径描述本身需要修**（见 §5 订正清单 D-3） |
| **G-F** 「条 vs 件」文案 | 现状不变（与 §7.1 N-1 一致） | **低** | **不改** | **成立** |
| **G-G** 分批发货口径说明 / 报表按行口径 | 现状 = 报表按行（未改）；页面**无**口径说明句 | **中低**：一线把「按行」误读为「按单」⇒ 与 G-B 叠加放大 | **只加说明句**（默认） | **成立**（可与 G-B 的说明句一并写） |
| **G-H** `is_archived` 是否继续统一（含 `Consumable`） | 现状 = **部分统一**：已统一（NULL 也视为未存档）`quality.py:744`、`routes.py:6247/6254/6261`、`mes_service.py:1562-1563`；**仍排除 NULL**：`routes.py:4797`（`RawMaterial.is_archived.is_(False)`）、`:4808`、**`:6125`（`Consumable.query.filter_by(is_archived=False)`）**、`:12065`、`:12093`、`:12122`；**有意例外（白名单）**：`mes_service.py:1441/1447/1453`（盘点快照，`filter_by(is_archived=False, status='in_stock')`） | **中（库存可信度）**：NULL 行在部分页面消失 ⇒ 「在库却查不到」，一线会重复采购 | **按默认实施**（批次8，统一为 NULL=未存档，盘点快照白名单保留） | **成立**；**行号需订正**：规划写的 `routes.py:6109` 实测是 `:6125`（见 §5 订正清单 D-4） |
| **G-J** 报工物料账「未挂批次不回写」是否可接受 | 现状 = 不臆造：`routes.py:3521-3524`（`consumption['missing']` ⇒ 只 `logger.warning('报工扣料未回写（该订单无对应分配行）')`）、`:3514`（`db.session.begin_nested()` savepoint） | **中**：计划账与实扣账对不上，且**日志级提示对一线不可见** | **可接受 + 页面可见提示**（默认） | **成立**；提示面**未落地**（同 Q-4 的 0 命中） |
| **G-K** 三套生产执行入口职责边界是否落文档 | 现状 = 三入口**都在且行为不同**：任务报工 `routes.py:3285`（过门禁 + 扣料 + 入正品库）、`/production_center`（`production_center.py:309`，**不入库不过门禁**）、工件域 MES（`mes_service.py:121` `qc_gate_allows`） | **中高**：同一批产出从不同入口走，**库存与质检结论不一致**；一线不知道「哪个入口才算数」 | **落文档**（默认）：员工端 / 生产中心 / 工件域 MES 各自定位 + **并入界面提示** | **成立**；建议**升优先级**（与 C-7 的冲突项一致） |
| **G-L** 内联 `current_user.role` 是否强制清零 | 现状 = **Python 15 处 + 模板 2 处**（实测见 §6）；`AGENTS.md` 明令「不要新写 `role in [...]`」 | **低（可维护性）**：新增代码若继续内联，能力表会被绕过 | **不强制**（默认）：保留「角色 + 对象归属」豁免（如「只能改本人任务」这类带对象归属的判断） | **成立**；§7.1 N-14 同结论。**⚠ 口径歧义**：`grep current_user.role` 会**多算 1 处**（`permissions.py:7` 是**注释行**），报数时必须说明「15 = 代码 14 + ？」，见 §6 |
| **G-M** 质检模板是否随初始化数据下发 | 现状 = **未随初始化下发**：`InspectionTemplate(` 构造点仅 `quality.py:262`（手工创建路由）；seed 函数 `models.py:2722 seed_defaults` / `app/__init__.py:142 _seed_system_configs` / `db_bootstrap.py:85 bootstrap_if_empty` **均不建** `InspectionTemplate`；`_test_bootstrap.py:133` 只在**测试副本**里造 | **高（闭环必备）**：无启用模板 ⇒ `mes_service.py:87 pick_template` 返回 `None` ⇒ 质检任务无模板 ⇒ 「看得懂」缺失（批次6 的 B6 系） | **是**（默认）：seed 至少一套 `type='production_record'`；**并注意 P7**（`goods_receipt` 类型界面无选项，来料检建不出可用模板） | **成立**；**但**「登记为数据初始化待办」等于**长期不修** ⇒ 建议提为 P1（见 §4） |
| **G-N** C-1 / C-2 / C-3 如何处置 | C-1 迁移碎片对拍（B10-01a/01b）：**未做**（实测：真实库 75 表 / 迁移 `create_table` 49 表 / 差集 **32**，去掉 `alembic_version` = **31**，见 §6）；C-2 PG 主从：`docker`/`pg_dump`/`psql` 不在 PATH（本机不可做）；C-3 断网多主：不做 | **低**（C-1 口径卫生）/ **不可做**（C-2） | C-1 可作批次10 可选排期；C-2 本机不做；C-3 不立项（默认） | **成立** |
| **G-O** 「对已完成任务部分报工」是否禁止 | 见 §1.4（**保留现状已成立，提示未落地**） | 见 §1.4 | **保留现状 + 页面提示**（默认） | **部分成立**（提示面未落地） |

### 2.1 §7.1「明确不做」清单复核（15 条）

| # | 结论 | 依据 |
| --- | --- | --- |
| N-1（不改「条/件」代码） | ✅ 仍成立 | 未见相关改动 |
| N-2（盘点快照 `is_archived=False` 例外保留） | ✅ 仍成立且**已固化** | `mes_service.py:1441/1447/1453` |
| N-3（不删 `/production_center`） | ✅ 仍成立 | 路由在 `production_center.py:26` |
| N-4（不并库存表） | ✅ 仍成立 | `stock_kind` 分库逻辑在 `mes_service.py:232-237`（`status_map`） |
| N-5（不做断网多主 C-3） | ✅ 仍成立 | 无相关代码 |
| N-6（本机不做 PG 演练） | ✅ 仍成立 | 环境事实 |
| N-7（禁止 `flask db migrate`） | ✅ 仍成立 | AGENTS.md 明令；未见违背 |
| N-8（导出不回退落盘） | ✅ 仍成立 | `BytesIO` 构造点实测 **15 处**（见 §6） |
| N-9（不做 `is_archived` 机械全文替换） | ✅ 仍成立 | 逐处语义不同（见 G-H） |
| N-10（`smoke_test` 不当验收替代品） | ✅ 仍成立 | 本轮未跑请求型脚本 |
| N-11（不做产出行按次拆分） | ✅ 仍成立 = Q-1 选 A 的直接后果 | 无实现 |
| N-12（不做报废成本台账） | ✅ 仍成立，**但与 P9 冲突** | P9 要求补 `scrap` 台账行（见 §3-P9、§4 冲突项） |
| N-13（不给全部模型补 `cascade`） | ✅ 仍成立 | 见 `recon-backend.md` §4 |
| N-14（不强制清零内联 role） | ✅ 仍成立 | 实测 Python 15 + 模板 2 |
| N-15（不改 `permission_matrix` 判定口径） | ✅ 仍成立 | 未见改动 |

> **14/15 成立**；**N-12 与 P9 直接冲突**：N-12 说「不做报废成本台账」，P9 说「报工路径报废应产生
> `scrap` 台账行」。二者的差别是**「成本台账」vs「库存台账行」**——建议把 N-12 措辞收窄为
> 「不做**成本**台账（金额），但**库存**台账行必须写（P9）」，否则 P9 会被 N-12 挡回去。

---

## 3. P1–P12 产品问题分级与验收判据

> 分级口径：**业务影响**（数据可信度 / 资金 / 库存 / 合规 / 可用性）×**暴露概率**×**修复成本量级** ⇒ P0/P1/P2。
> **每条判据必须含阴性或阳性对照**（硬纪律）。「变红条件」沿用 `70-` §4 的定义并加业务侧判据。

### 3.1 P1｜审计行 `target_id` 落库 `NULL` 而 `can_rollback=True` ⇒ 回滚指不到对象

| 维度 | 评估 |
| --- | --- |
| **业务影响** | **数据可信度（高）**：审计表存在「可回滚」标记但目标不可寻址 ⇒ **回滚功能对这批记录是假的（点了 404）**。**合规（中高）**：审计可追溯性是企业内控要件，审计员会问「你说能回滚，怎么回滚？」 |
| **暴露概率** | **已发生**：真库 `audit_log` **73 行**，`target_id IS NULL` **40 行**，其中 `can_rollback=1 且 NULL` **10 行**（工具=副本库只读查询，口径=`AuditLog.query.filter(...)`，值=`73/40/10`）。即**现有数据里已有 10 个「假回滚」按钮** |
| **修复成本** | **极低**（量级=2 行）：`routes.py:5152` 与 `quality.py:628` 前各加 `db.session.flush()`；三处对照组（`routes.py:564/1734/4420`）本就是正确写法 |
| **建议优先级** | **P0**（理由：成本 2 行 + 已有 10 条受污染数据 + 属合规面；`70-` §10.3 把它列在产品面 ① 位） |
| **口径建议** | ① 修 `flush()` 时机（结构性）；② **存量 10 行必须处置**：要么把 `can_rollback` 置 `False`（诚实标记），要么补 `target_id`（不推荐，需推断）；③ 审计行写入前**加不变量断言**：`rollback_type='add'` ⇒ `target_id IS NOT NULL`。 |
| **验收判据** | **阳性**：`POST /products/add` 成功 ⇒ 新增审计行 `target_id` **非空**，且对其调 `POST /audit_logs/rollback/<id>` ⇒ **HTTP 200** 且目标行被删。**阴性对照（必红→转绿）**：修复前同流程 ⇒ `target_id` 为 `NULL`、回滚 **404「目标记录不存在」**（本次实测复现：`I_P1_behavior.target_id=null` / `I_P1_rollback_consequence.status_code=404`）。**存量**：修复后 `count(target_id IS NULL AND can_rollback=1)` 必须 `= 0`（当前 `10`） |

### 3.2 P2｜缺 f-string 前缀 ⇒ 落库为字面量 `第{index+2}行导入失败…`

| 维度 | 评估 |
| --- | --- |
| **业务影响** | **可用性（中低）**：错误提示对用户**完全无用**（把源码表达式写给用户看）。**数据可信度（低）**（不影响数据本身） |
| **暴露概率** | **中低**：只在「导入行失败」时出现。但导入是批量作业，出错概率不低 |
| **修复成本** | **极低**（2 字符）：`routes.py:4945`、`:5036` 各加 `f` |
| **建议优先级** | **P1**（成本 2 字符、用户可见面广；建议与 P5 合并为一张「导入错误提示」工单） |
| **验收判据** | **阳性**：构造 1 条坏行导入 ⇒ 响应错误文本含**具体行号数字**（如 `第 5 行`），且**不含**字面量 `{index+2}`。**阴性对照**：修复前响应文本**逐字**为 `第{index+2}行导入失败，请稍后重试或联系管理员`（本次实测取行确认 `:4945/:5036` 无 `f` 前缀） |

### 3.3 P3｜`/employees/import` 整单拒绝（违反 AGENTS.md「导入必须行级容错」）

| 维度 | 评估 |
| --- | --- |
| **业务影响** | **可用性（高）**：3 好 + 2 坏 ⇒ **一条都不进**。一线拿到「某几行有错」后必须**手改 Excel 重传全量**，且不知道哪些已成功 |
| **暴露概率** | **高**：HR 批量导入员工是常规操作，Excel 表头/格式漂移常见 |
| **修复成本** | **低**（1 个函数的控制流）：`routes.py:2061-2066` 早退改为「好行 commit + 逐行错误」，与同文件 `:2102-2140` 的既有行级容错形态对齐 |
| **建议优先级** | **P1** |
| **验收判据** | **阳性**：3 好 + 2 坏 ⇒ `success=true`（或含 `success_count=3`）且 `employee` 表 **Δ=+3**，响应逐行列出 2 条「第 N 行」错误。**阴性对照（必红→转绿）**：修复前同夹具 ⇒ `success=false`、`employee` **Δ=0**、响应「数据验证失败，共发现2个错误」（本次实测复现：`H_P3_P4_employees_import.employee_delta=0`） |

### 3.4 P4｜上传残留（解析失败与早退两条路径）

| 维度 | 评估 |
| --- | --- |
| **业务影响** | **可用性（中）**：`uploads/temp` 堆积；AGENTS.md 明确该目录是「纯运行时临时目录」，**残留属未清账**。长期会吃磁盘 |
| **暴露概率** | **中高**：只要有一次解析失败或早退就留 1 个文件；`@bp.before_request` 钩子阈值 `>300s`（`routes.py:2194`）**当次不清** |
| **修复成本** | **低**（两处 `finally`）：`routes.py:4000-4006`（`os.remove` 在 `try` 内）与 `:2171-2176`（清理只在 `except` 分支，早退 `:2062` 与成功 `:2166` 都不经 `except`） |
| **建议优先级** | **P1** |
| **验收判据** | **阳性（阳性对照）**：S4 解析失败 / S5 早退两场景跑完后，`TEMP_FOLDER` 内**无**本次文件（`residue_exists=false`）。**阴性对照（必红→转绿）**：修复前同场景 ⇒ `residue_exists=true`（本次实测复现：`t3_*_good_bad.xlsx` / `t3_*_broken.xlsx` 两份残留，且 `TEMP_FOLDER` 已改指副本目录、**未污染仓库 `uploads/temp`**） |

### 3.5 P5｜行号覆盖不一致（同类错误三类坏行里两类不带「第 N 行」）

| 维度 | 评估 |
| --- | --- |
| **业务影响** | **可用性（中低）**：与 P2 同族，「哪一行错了」说不清 ⇒ 一线只能全表肉眼找 |
| **暴露概率** | **中高**（同 P2） |
| **修复成本** | **极低**（2 处加「第 N 行」前缀）：`routes.py:4016`、`:4022` |
| **建议优先级** | **P1**（与 P2 同工单） |
| **验收判据** | **阳性**：三类坏行（员工不存在 / 工序不存在 / 日期格式错）**全部**含「第 N 行」，即 `row_number_all_ok=true`。**阴性对照**：修复前 `row_number_all_ok=false`（`routes.py:4028/2058` 有行号 vs `:4016/4022` 无行号，本次取行确认） |

### 3.6 P6｜`update_status` 内 ≥4 处内层 `try/except` 可吞失败 ⇒ 可能「部分应用」

| 维度 | 评估 |
| --- | --- |
| **业务影响** | **数据可信度（高）**：一次报工可能「扣了料但没计件」「入了库但没扣料」⇒ **账实不符**，且响应码不反映原子性 |
| **暴露概率** | **低–中**：需内层抛错才触发；但报工是高频写操作，累积暴露面大 |
| **修复成本** | **中**（7 处内层 try，含 2 处 `logger.warning`）：`routes.py:3474-3476/3527-3528/3555-3556/3607-3608/3659-3661/3684-3685/3750-3751` |
| **建议优先级** | **P1**（不是 P0：需外部条件触发；但一旦触发是**静默**的，所以不能低于 P1） |
| **验收判据** | **阳性（注入）**：让第 3 个内层失败（如让 `record_task_material_consumption` 抛错）⇒ 报工响应**必须** `success=false`，且**全部**目标表 Δ=0（真正的原子性）。**阴性对照**：成功路径下各表 Δ 与既有基线一致（不得因改 savepoint 而丢写入）。**注意**：`recon-backend.md` §8-5 明确「注入复现**未重跑**」⇒ 本条判「可形成部分应用」为**取行级确定 + 中高置信**，判据需下一轮真注入 |

### 3.7 P7｜质检模板类型口径三方冲突 + 界面无 `goods_receipt` 选项

| 维度 | 评估 |
| --- | --- |
| **业务影响** | **可用性（高）+ 数据可信度（中）**：**来料检建不出可用模板** ⇒ 采购到货无法完成质检 ⇒ 入库被卡（`purchase.py:39`「到货单已报废/未入库」一族提示） |
| **暴露概率** | **高**：只要走「采购到货 → 来料检」，就会撞上 |
| **修复成本** | **低–中**：`quality.py:838` 口径二选一（改文档为 `goods_receipt`，或实现接受 `material`）**并**给 `templates/main/quality/templates.html:103-107` 补 `goods_receipt` 选项 |
| **建议优先级** | **P1**（属「能办完」的闭环缺口；`70-` §10.3⑦ 归在产品面） |
| **口径建议** | **推荐「实现接受 `goods_receipt` + 界面补选项」**：语义上「来料检的受检对象就是到货单」，`material` 是「物料」不是「到货批次」，用 `material` 会在「一批到货多物料」时歧义。**同时**修改 `04` 文档的 A4 口径（`docs/` 不可覆写 ⇒ 新建订正件）。 |
| **验收判据** | **阳性**：为 `goods_receipt` 任务绑模板 ⇒ HTTP **200**（修复前实测 **400**「质检模板类型与任务类型不匹配」）；且界面下拉 `ui_goods_receipt_option=true`（修复前实测 `false`）。**阴性对照**：`production_record` 任务的既有绑定流程 ⇒ 仍 200（不得回归） |

### 3.8 P8｜`04` §2.2 B2 工序数口径过时（文档问题，非代码缺陷）

| 维度 | 评估 |
| --- | --- |
| **业务影响** | **数据可信度（低）**（文档口径）；但会**误导验收方按错期望值判红** ⇒ 间接影响排期判断 |
| **暴露概率** | **必现**（照字面验收就必红） |
| **修复成本** | **极低**（改一句）；但 `docs/` 不可覆写 ⇒ **新建订正件** |
| **建议优先级** | **P2**（文档面，不阻塞代码） |
| **验收判据** | **阳性**：订正件里 B2 行写「每工序一张」，且 n=2 场景实测 `task_delta=3 / process_count=3 / batch_item_delta=2`（`70-` §4-P8 的 V-12 `V12-B2.3` 读数）。**阴性对照**：按字面「工序数×n」期望 6 ⇒ 该格**必红**（这就是要订正的原因） |

### 3.9 P9｜报工路径（无工件）报废不产生 `scrap` 台账行

| 维度 | 评估 |
| --- | --- |
| **业务影响** | **库存（高）+ 资金（中）**：报废**不落库存台账** ⇒ 账面没有「报废了多少件」，报废损失**无法统计**、无法与报废成本对账。`bi.status='scrapped'` 只解决「不再放行」，不解决「报废了几件」 |
| **暴露概率** | **高**：报工路径（无工件）是主路径（`recon-backend.md` §1：主判据就是报工链） |
| **修复成本** | **低–中**：`mes_service.py:1121-1143` 的 `scrap` 分支 `:1125 if wp:` 是唯一写台账的入口；无工件时需按 `item`（批次实例）+ 件数直接建 `FinishedProduct(stock_kind='scrap')` 行 |
| **建议优先级** | **P0（业务视角）**——**与技术排序冲突**，见 §4。理由：库存台账缺失属**账实不符**，且修法只在 1 个函数内 |
| **口径建议（明确）** | ① **台账行必须写**，载体沿用既有 `finished_product` 表（`stock_kind='scrap'`），**不新建表**（遵守 `07b` §3-3「不新增列 > 新增列」）；② 数量 = `pieces`（`scrap_quantity`，默认 1），与 `:1129 inbound_workpiece(..., quantity=pieces)` 同口径；③ **「不做报废成本台账」（N-12）应措辞收窄**为「不做**金额**台账」——P9 要的是**库存台账行**，二者不矛盾；④ 关联键：把 `nc.id` / `production_record.id` 写进该行 `notes`，便于追溯。 |
| **验收判据** | **阳性**：报工路径（`workpiece_id IS NULL`）的 NC 走 `scrap` 处置 ⇒ `finished_product(stock_kind='scrap')` **Δ=1**（`scrap_rows_delta=1`），且该行 `notes` 可定位回 `nc.id`。**阴性对照（必红→转绿）**：修复前同场景 ⇒ `Δ=0`（本次实测复现：`F_P9.scrap_ledger_rows_before=0 / after=0 / delta=0`，同时 `bi_status_after_scrap='scrapped'`、门禁 `allowed=false` —— **证明「状态对了、台账没写」**）。**回归对照**：有工件路径（`wp` 非空）的报废台账 Δ **不得**从 1 变 0 |

### 3.10 P10｜`notes` KeyError 掩盖 + 取价口径三处不一致

| 维度 | 评估 |
| --- | --- |
| **业务影响** | ① **可用性（高）**：`/production_records/import` **0 条入库**（功能完全不可用）；② **资金（高）**：同一 `process_code` 两处取到**不同版本**的单价 ⇒ **计件工资算错**（实测 `3487` vs `3488`） |
| **暴露概率** | ① **必现**（每次导入都 0 条）；② **条件必现**（只要存在多条同 `process_code` 的价格版本） |
| **修复成本** | **低**：① `excel_generator.py:336-341` 的 dict 补 `notes` 键（或 `routes.py:2733` 改成 `data.get('notes')`）；② 抽单点 `pick_process_price(code, date)` 替换 `routes.py:2717-2720`、`:3902`、`:4020` |
| **建议优先级** | **P0（业务视角）**——**与技术排序冲突**，见 §4。理由：① 功能完全不可用（导入 0 条）；② 取价不一致直接改工资数字 |
| **口径建议（明确）** | 取价**唯一口径** = 「`process_code` 匹配 且 `effective_date <= 业务日期` 的**最新版本**」（即 `routes.py:2717-2720` 的写法）。
`routes.py:3902`（奖惩导入）与 `:4020`（任务导入）的 `filter_by(process_code).first()` **无序取第一条** ⇒ 必须改为调用同一单点函数。**注意**：奖惩记录的业务日期字段是 `target_date`/`date`，调用时须显式传日期，不得用「今天」兜底。 |
| **验收判据** | **阳性**：同一 `process_code` 造两版价格（旧 `3487` / 新 `3488`），
① 导入生产记录 ⇒ `records_created >= 1`（修复前 `0`，响应含 `处理记录时出错: 'notes'`）；
② 同一条 `process_code` 在两处取价 ⇒ **取到同一版本**（都取「业务日期之前的最新版」）。**阴性对照**：
导入**合法**行时 `records_created` 与既有基线一致（不得因补 `notes` 键而改变别的字段）；且**不存在**
「取价函数把未来生效价当当前价」的格子（`effective_date > 业务日期` 的行必须被排除）。 |

### 3.11 P11｜仓库根污染（原 `.tmp_v15_*` 已清；同族新残留 `_probe_tmp/`）

| 维度 | 评估 |
| --- | --- |
| **业务影响** | **无（产品面）**：属**仓库卫生/测试资产**，不影响任何业务数据。但它会污染 `git status`，让「生产面零改动」的判定变难 |
| **暴露概率** | 已发生（`recon-backend.md` §5-P11：原 6 个 `.tmp_v15_*.{out,err}` = **0 个**；新残留 `_probe_tmp/gate-baseline.txt` 24704 B + `scripts/_probe_seed.py`） |
| **修复成本** | **极低**（删除 / 改写到 `.tmp/<RUN_ID>/`） |
| **建议优先级** | **P2**（纪律面，不阻塞交付） |
| **验收判据** | **阳性**：`git status --porcelain` 中**不含** `.tmp_v15_*` / `_probe_tmp/`。**阴性对照**：本次实测 `_probe_tmp/` 显示为 `?? _probe_tmp/`（未经 captain 许可**不自行删除**，只登记） |

### 3.12 P12｜N-1 修好后两个下游资产变红/变陈旧

| 维度 | 评估 |
| --- | --- |
| **业务影响** | **无（产品面）**：属**测试资产口径**。但**会**把「假红」洗成「假绿」（`reconcile_r2.py:555` 断言无参调用 `exit 0`，修后实际 `exit 2`）⇒ 削弱回归网络可信度 |
| **暴露概率** | **必现**（只要跑 `reconcile_r2.py`） |
| **修复成本** | **极低**（两处重指 `--coverage <run 产物>`）：`harness/reconcile_r2.py:555`、`harness/r2_v14_ledgerbook.py:257-262` |
| **建议优先级** | **P1**（测试资产可信度是「后续每批验收」的地基；`ci_gates` 已把 `coverage_drift` 列为 **blocking**，下游却还按无参调用记） |
| **验收判据** | **阳性**：`coverage_drift.py` 显式传 `--coverage <本次 run 产物>` ⇒ `exit 0`（8/8）。**阴性对照**：**无参**调用 ⇒ `exit 2`（用法错误，**不是**回归）——本次实测复现 `exit 2`（`recon-backend.md` §5-P12 同结论）；两个下游脚本改写后，其记录的 `command` 与实际一致且断言与 `exit_code` 一致 |

---

## 4. 后续开发优先级建议（业务视角）与冲突显式声明

### 4.1 业务视角排序

| 业务序 | 条目 | 业务理由 | 建议层级 |
| --- | --- | --- | --- |
| **B-1** | **P10 取价口径统一 + `notes` 键** | ① 导入功能**完全不可用**（0 条入库）；② 取价不一致**直接算错工资**（资金） | **P0** |
| **B-2** | **P9 报工路径报废补 `scrap` 台账行** | 库存台账缺失 ⇒ **账实不符**；报废损失不可统计 | **P0** |
| **B-3** | **P1 审计 `target_id` 两处 `flush()` + 存量 10 行处置** | 成本 2 行 + 已有 10 条污染数据 + 合规面 | **P0** |
| **B-4** | **`inbound_production_output` 补传 `production_record`**（§1.1 C-6） | 让 Q-1 的「阻断」真正成立（当前 fail-open） | **P0** |
| **B-5** | **G-E 客户删除关联校验** | **数据完整性**（孤儿订单）+ 回滚不可能完整；成本低（1 函数） | **P1** |
| **B-6** | **G-M 质检模板 seed + P7 `goods_receipt` 口径** | 「能办完」的闭环；来料检当前建不出可用模板 | **P1** |
| **B-7** | **P2/P3/P5/P4 打包成「导入体验」一张工单** | 同族（都是导入错误提示/容错/清账），一次改完一处验收 | **P1** |
| **B-8** | **P6 报工原子性（内层 try → savepoint/上抛）** | 静默部分应用是**最难排查**的一类账实不符 | **P1** |
| **B-9** | **Q-4 页面提示句 + G-J 未回写提示句** | 纯文案、0 风险、直接降一线误操作 | **P1**（成本 P2，收益 P1） |
| **B-10** | **G-H `is_archived` 统一（NULL=未存档）** | 「在库却查不到」引发重复采购 | **P2** |
| **B-11** | **P12 测试资产两处重指** | 保护回归网络的可信度 | **P2**（技术面可 P1） |
| **B-12** | **G-K 三入口职责边界落文档 + 界面提示** | 一线不知道「哪个入口才算数」 | **P2** |
| **B-13** | **G-D 编码规则日志页 / G-B+G-G 口径说明句 / P8 文档订正 / P11 卫生** | 体验与治理 | **P2** |

### 4.2 ⚠ 与技术排序的显式冲突（3 处）

| # | 冲突 | 技术排序（`70-` §10.3 / `recon-backend.md` §6.1） | 业务排序 | 业务方立场与理由 |
| --- | --- | --- | --- | --- |
| **X-1** | **P9 的层级** | 技术侧列 **P2**（`recon-backend.md` §6.1「P2 / B4-04 / B4-05(报废台账) / P9 三处同源」） | 业务侧 **P0** | **业务优先**：台账行缺失 = **账实不符**，且 N-12 目前把 P9 挡在门外。**修法风险极低**（1 个函数内的 `if wp:` 分支扩展）。建议：至少与批次6 同批，**不得**推到 P2 之后 |
| **X-2** | **P2/P5 的层级** | 技术侧把 P1/P2/P3/P4/P5/P10 打包成「阶段C 产品面」一批（**P2**） | 业务侧 **P1** | **业务优先（部分）**：P4（上传残留，违反 AGENTS.md 明文纪律）与 P6（静默部分应用）可以留 P2 之后；但 **P2/P3/P5 是用户可见的错误提示与整单拒绝**，属「一线天天碰」，建议**并入最早的一批**，不要等「阶段C 收尾」。**P3 尤其**：整单拒绝会让 HR 白干一遍 |
| **X-3** | **门禁时序（G-K / C-6）** | 技术侧：先实现（`recon-backend.md` §7-3 指出「报工链上拒绝路径不可达」并建议**先拍板**是否补传 `production_record`） | 业务侧：**先钉口径**（本报告 §1.1 已给出建议：补传 `production_record`，同时保留 `quality_status` 兜底） | **一致但需显式**：双方都不反对补传；**分歧在「谁拍板」**。业务侧要求：**在改 `mes_service.py:351` 之前**先确认「报工未出质检结论 ⇒ 必须拦」这条业务规则（否则改了仍无法验收）。这条属**业务口径**，不是技术实现细节 |
| **X-4** | **N-12 与 P9 的措辞冲突** | N-12「不做报废成本台账」写在「明确不做」清单（写了即**不再重复报**） | 业务侧要求 P9 | **必须先把 N-12 措辞收窄**为「不做**金额**台账」，否则按 §7.1 的规则，P9 报上来会被以「N-12 已明确不做」驳回。**这是流程性冲突，不是技术分歧** |

### 4.3 建议的最小交付切分（业务可验收为主）

- **切分 1（P0，1 个工作包，全部为小改动）**：B-1（P10）+ B-2（P9）+ B-3（P1 + 存量处置）+ B-4（补传 `production_record`）。
  验收 = 本报告 §1.1 / §3.1 / §3.9 / §3.10 的「阳性 + 阴性对照」四组全绿。
- **切分 2（P1，导入体验 + 闭环）**：B-5 / B-6 / B-7 / B-8 / B-9。
  验收 = §3.3/§3.4/§3.5/§3.6/§3.7 + §1.4 的判据。
- **切分 3（P2，治理与卫生）**：B-10 / B-11 / B-12 / B-13。
  验收 = §3.8/§3.11/§3.12 + G-H/G-K 的口径说明。
- **共同前置**：**先把 N-12 措辞收窄**（否则切分 1 的 B-2 无合法依据）。

---

## 5. 附：本次发现的两处「文档 vs 实测」需要登记（供总表消费）

| # | 项 | 实测 | 关联 |
| --- | --- | --- | --- |
| D-1 | **Q-2 原文识别口径** | `07b` DEC-2 §2.2 已改判为 R1/R2；notes 前缀降为提示 | `docs/交接提示词…§五` Q-2 行需加订正说明 |
| D-2 | **G-E 默认路径措辞** | 实测**允许裸删**（`routes.py:9267-9268` 的 TODO 仍在） | 附录 B G-E「不拍板时 = 按默认实施」与实际不符 ⇒ 应写「保持现状（允许删除）直至拍板」 |
| D-3 | **N-12 措辞** | 「不做报废成本台账」会挡住 P9 的库存台账行 | 需收窄为「不做金额台账」 |
| D-4 | **G-H 行号** | 规划写 `routes.py:6109`，实测 `Consumable.query.filter_by(is_archived=False)` 在 **`:6125`** | 应由技术文档工程师统一订正（本报告只登记） |

---

## 6. 附：本次实测的关键数字（工具 + 口径 + 值）

| 项 | 工具 + 口径 | 值 |
| --- | --- | --- |
| `audit_log` 总行 / `target_id IS NULL` / `NULL 且 can_rollback=1` | 副本库只读 `AuditLog.query`（探针 `probe_backend_field.py` A 组） | `73 / 40 / 10` |
| fail 后 NC 增量 / `quality_status` / 门禁 | `apply_production_record_result` 行为（同探针 B 组） | `+1 / NULL→fail / allowed=false` |
| 处置 `rework` 后门禁 | 同探针 C 组 | `allowed=true, quality_status=pass` |
| 报废台账行 Δ（报工路径） | 同探针 F 组 | **`0`**（`before=0 after=0`），`bi.status='scrapped'` |
| 计件开关 false/true 差分（S1） | `piecework_amount` 行为（同探针 G 组） | `60.0 → 160.0`（Δ=100.0） |
| 计件开关 false/true 差分（S2/S3/S4，本次新证） | 探针 `probe_product_piecework.py`：`Employee.total_salary` / `piecework_amount`×系数 | `S2 2060→2160`、`S3 60→160`、`S4 60→160`；非返工两态均 `60.0` |
| 返工件数取值链 | 同探针 D 组 | 显式 `7`；缺省取来源 `quantity=5`；兜底 `1` 且 notes 留痕 |
| 报废扣料（逐行） | 同探针 E 组 | 料 2 `-6.0`（3.0×2）、料 3 `-8.0`（4.0×2）、料 4 `0.0` |
| `/employees/import` 3 好+2 坏 | 同探针 H 组 | `success=false`、`employee Δ=0`、响应含「数据验证失败，共发现2个错误」 |
| 上传残留（两场景） | 同探针 H 组 | `residue_exists=true`（`t3_*_good_bad.xlsx` / `t3_*_broken.xlsx`） |
| P1 回滚后果 | 同探针 I 组 | 新增审计 `target_id=null`、`can_rollback=true` ⇒ 回滚 **404** |
| P12 无参 `coverage_drift` | `recon-backend.md` §5-P12（本次未复跑，标转述） | `exit 2` |
| **落盘导入端点** | 探针 `probe_product_import_endpoints.py`（AST：`file.save(` / `save_temp_file(` / `read_excel(file)`） | **`routes.py` 8 个**（`/employees/import`、`/process_prices/import`、`/production_records/import`、`/bonus_penalties/import`、`/tasks/import`、`/inventory/finished/import`、`/inventory/raw/import`、`/products/import`）；**`quality.py` `/api/quality/tasks/import` 不落盘**（`pd.read_excel(file)` 内存流，`:1634`） |
| 内联 `current_user.role` | 文本行 grep：`current_user.role` | **Python 16 行 / 模板 2 行**；其中 **`permissions.py:7` 是注释行** ⇒ **代码实为 15 处**（与 `AGENTS.md` 口径一致）；模板 `task_detail.html:13`、`tasks.html:340` |

---

## 7. 自检与边界（我没有做什么）

1. **只读**：未修改任何既有文件（含 `docs/`、`AGENTS.md`）。新增仅 `reconcile-2026-10-08/` 下的 5 个文件（1 报告 + 4 探针 + 各自 `.output.json`）。
2. **真实库零写入**：`app.db` 开工与收尾两次 Hash + 大小 + mtime **逐位一致**（`F5DA2306…0E0F065` / `2531328` / `2026-09-18 12:50:55`）；写入全在 `make_app(fresh=True)` 的临时副本。
3. **未跑请求型门禁脚本**（`smoke_test` / `permission_matrix` / `functional_test` / `w2w3_probe` 均**未复跑**）。
4. **未污染仓库 `uploads/temp`**：探针把 `TEMP_FOLDER` 改指副本临时目录。
5. **未复核项（明确标注为转述，不作证据）**：
   - `coverage_drift.py --coverage <run 产物> ⇒ exit 0`（`70-` §5.2②，本次未复跑）；
   - P6 的**注入复现**（本次只做取行确认，未注入）；
   - P7/P8 的 **V-12 探针读数**（本次只做代码/页面侧取行确认）。
6. **未做判断的**：`_probe_tmp/`、`scripts/_probe_seed.py` 的归属与去留（只登记）。
7. **不把「有配置项」当「开关生效」**：本报告凡称「已落地」处，均给出**行为读数**或**调用点结构证据**；
   G-A 的两个采购开关虽为 false，但**有真实读取点与执法点**（`purchase.py:20/24/490`），故归「已接线」而非「假开关」。
