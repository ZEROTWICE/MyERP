# DEC-1 / DEC-2 业务口径决策单（代码修复的硬前置）

> 本文件是 **W2（质检闭环）与 W3（金额料账）代码修复的签前口径**。任何涉及
> `quality_status` / 质检门禁 / 返工识别 / 报废扣料的代码改动，必须逐条对齐本单；
> 与本单冲突的实现视为**未授权实现**。
>
> **裁定状态**：`DECIDED`（已定稿）· **v1.0** · 2026-10-08
> **来源任务**：`t2 [decisions]`（attempt 1，`2d1189ee-7ef9-42e8-86bc-2b061de09098`）
> **依据文档**：`07-测试与工程改进报告.md` §3.1/§4.1/§6、`08-最终测试报告.md` §5.2/§5.3、
> `05-端到端验收实测.md` §UAT-D1…D6、`06-测试结果分析与缺陷分级.md` §5.2（M-1…M-4）、
> `test-reports-2026-10/evidence/improve/fix_plan.json`（DEC-1/DEC-2 条目）
> **全部源码引用均为只读复核**（本单不改任何生产代码）

## 0. 签署与生效

| 角色 | 谁签 | 签的是 | 状态 |
| --- | --- | --- | --- |
| 业务 | 产品经理 | §1.2 / §1.3 / §2.3 / §2.4 的业务含义（放行、复位、返工口径、扣料量） | ☐ 待签（`t7` 开工前必须签） |
| 开发 | 后端架构师 | §1.4 / §1.5 / **§1.7（口径更正）** / §2.2 / §2.5 的可实现性与写点唯一性 | ☐ 待签 |
| 测试 | 测试结果分析师 + 测试自动化工程师 | §1.6 / §2.6 判定表与判据形状（必须可机读、可逐格复现） | ☐ 待签 |

**生效条件**：三方均签 ⇒ `t7`（P-03/P-07/P-02）与 P-04/P-05/P-06 才可开工。
**变更规则**：本单任何实质修改一律**新开文件**（`09b-…`），不原地改（沿用 `00b` 的冻结纪律）。

**未签署时的默认口径**：以本单 v1.0 为准执行；若三方未签而代码先动，则 `t7` 视为**顺序违规**，
回归验收直接判 `needs_revision`（依据 `07` §4.1「顺序错就是引入新缺陷」）。

---

## 1. DEC-1 —— `quality_status` 取值语义与复位口径

### 1.1 问题（签前必须承认的事实）

| 事实 | 证据（只读复核） |
| --- | --- |
| 字段存在且注释已声明三值 | `app/models.py:1466` `quality_status = db.Column(db.String(20))  # pass, fail, pending` |
| 全仓**唯一写入点**是人工 PUT | `app/main/routes.py:8898-8899`（`'quality_status' in data` → 赋值）；grep 全仓仅此一处赋值 |
| 门禁**已经**把 `pending`/`fail` 当拒绝条件 | `app/services/mes_service.py:169-173` |
| 自动链路对 `production_record` **零落地** | `mes_service.py:403-422`：只有 `workpiece`/`heat_lot`/`goods_receipt` 三条分派，其余落到 `:421 if workpiece is None: return` |
| 因此 `pending` 一旦被写入即**永久锁死** | 实测：`NULL` 实例报工 `finished_product` **+4**（放行）；`pending` 实例 **+0**（静默拒绝），无自动复位路径（`05` §UAT-D3 / `07` §4.1） |
| 真实库尚未受害，但一次 PUT 即触发 | `production_batch_items` 23 行 `quality_status` 全 `NULL`（`07` §4.1 表） |

> **危险方向已明确**：只补 `fail` 落地、不补 `pass` 与复位 ⇒ 修好 AC-13/AC-18 却引入 AC-15 的阻塞，
> 属**回归**，不是新缺陷（`07` §4.1 红线）。

### 1.2 裁定 A：取值语义（**唯一口径**，四值）

| 取值 | 唯一含义（准入判据） | 写它的人 | 不写它的人 |
| --- | --- | --- | --- |
| `NULL` | **未开始 / 未判定**：该产出**尚无任何质检结论**，也**无在办质检任务** | 保持默认；复位时**不回写 NULL**（回写成 `pass`） | — |
| `pending` | **质检进行中**：存在**在办**（`status ∈ {pending, in_progress}`）的质检任务，或存在**未闭环**（`status ∈ {open, pending_approval}`）的不合格记录 | `apply_inspection_result` 在该产出被挂上在办单据时 | 任何「仅因为怕漏检」而预写 `pending` 的实现 **一律禁止** |
| `pass` | **合格**：该产出关联的质检任务**全部 completed 且结果均为 pass**，且**无**未闭环不合格记录 | `apply_inspection_result`（全绿时）与 `dispose_nonconformity`（处置 done 后复算） | — |
| `fail` | **不合格**：存在结果 `fail` 的质检结论，且对应不合格记录**未闭环** | `apply_inspection_result`（结果 fail 时） | 处置 done 后**必须**由复位路径改写，不得停留在 `fail` |

**写死两条禁令**（`fix_plan.json` P-07 fix_action 第 3 条）：
1. **禁止**出现「写了 `pending` 却没有任何在办质检任务 / 未闭环不合格记录」的中间态——那正是死锁形态。
2. **禁止**在 `apply_inspection_result` 之外新增自动写点；人工 PUT `routes.py:8899` 只作**纠正通道**，
   不得成为任何链路的必经步骤。

### 1.3 裁定 B：与 `status` / `scrapped` 的职责边界（不得互相替代）

| 字段 | 管什么 | 明文规则 |
| --- | --- | --- |
| `ProductionBatchItem.quality_status` | **质检结论**（能不能入正品库的依据） | 本单 §1.2 四值；`fail`/`pending` 是门禁的拒绝输入 |
| `ProductionBatchItem.status` | **产出流程状态**（`pending/in_progress/completed/scrapped`） | `scrapped` 是**终态**：报废处置后写 `scrapped`，**即使** `quality_status` 复位为 `pass`，门禁仍必须拒绝（`mes_service.py:174-175` 已实现，保留） |
| `Workpiece.status` | **单件流转状态**（`raw/…/fg/failed/scrap/…`） | 由处置逻辑写；`scrapped` 复位**不得**把 `wp.status` 从 `scrap` 改回 `machining` |

### 1.4 裁定 C：门禁判据（P-07 的实现口径）

`qc_gate_allows_output` 的**拒绝顺序**固定为（`mes_service.py:167-207` 改造后）：

| 序 | 判据 | 结果 | 与现状差异 |
| --- | --- | --- | --- |
| 1 | `quality_status ∈ {fail, failed, rejected}` | 拒，原因「质检不合格，不得入正品库」 | 保留（`:170-171`） |
| 2 | `status == 'scrapped'` | 拒，原因「已报废」 | 保留（`:174-175`） |
| 3 | `quality_status ∈ {pending, pending_inspection}` **且**存在在办质检任务（按 `record_ids`）**或**未闭环不合格记录 | 拒，原因须**可读且可执行**（告知复位路径） | **改判点**：现状 `:172-173` **无条件**拒 `pending` |
| 4 | `record_ids` 存在在办质检任务 / 未闭环不合格记录（与 `quality_status` 无关） | 拒 | 保留（`:184-197`，AC-14 的**真实**拒绝路径） |
| 5 | 工件维度未处置不合格 / 未完成质检（`workpiece_blocked` + `qc_gate_allows`） | 拒 | 保留（`:199-207`） |
| 6 | 以上皆不命中 | **放行** | — |

**关键裁定**：`pending` **不再**是「一律拒绝」的绝对条件，而是「**确实有在办单据**才拒绝」。
依据：`06` §5.5 的 Y-1 更正——AC-14 的判据必须写成「拒绝路径存在但**依赖 NC / 质检任务行**」，
不能写成「门禁读 `quality_status` 所以必然拦」。

**拒绝文案要求**：命中序 3 时必须给出**下一步可执行的复位动作**（例：
`实例 X 质检未出结果，不得入正品库；请在质检任务完成后重新报工（或由质检处置入口完成处置）`），
不得只写「不得入正品库」。

### 1.5 裁定 D：写点归属与落地路径（P-03 / P-02 的实现口径）

**自动写点唯一**：`mes_service.apply_inspection_result(record)`（`mes_service.py:403`）。

新增 `target_type == 'production_record'` 分支（在 `:421` 早返回**之前**分派），实现顺序：

1. **定位产出（⚠ 口径更正，见 §1.7）**：`record.task.target_id` = `ProductionRecord.id`，取 `pr = ProductionRecord.query.get(target_id)`；
   再由 `pr.global_sn` → `TaskAssignment.global_sn`（**报工链唯一关联键**，`routes.py:3372-3377` 明文）
   → `TaskAssignment.batch_item_id` → `ProductionBatchItem`（定位函数 `task_batch_item(task)`，`mes_service.py:246-250`）。
   **不得**使用 `batch_item_production_records` 的反查（那是 `production_center` 执行记录专用约定）。
   **不新增列、不改关联约定**；定位不到 batch_item 时**不得**抛错：记 `logger.warning` 并跳过回写
   （链 A 的既有语义是「无工件也可判」）。
2. **fail 落地（P-02 + P-03 同批）**：
   - 建 `NonconformityRecord(record_id=record.id, type='rework', status='open',
     target_type='production_record', target_id=production_record.id, workpiece_id=None)`；
   - 该 batch_item 写 `quality_status='fail'`。
3. **pass 回写（P-03）**：`record.result == 'pass'` 时**不得**建 NC；
   仅当「该产出关联的质检任务**全部** completed 且结果**全部** pass，且**无**未闭环不合格记录」时写 `pass`。
4. **复位（P-07 的自动动作）**：`dispose_nonconformity` 处置动作为 `rework` / `scrap` / `accept`
   且 `nc.status ∈ {done, approved}` 时，对该产出**复算**一次：仍存在 fail / 未闭环 ⇒ 保持；否则写 `pass`。
   **复位必须是链路自动动作**，不得要求人工 PUT。
5. **状态机不变量**（可静态断言）：任何时刻不得出现
   `quality_status='pending'` 且「无在办质检任务 ∧ 无未闭环不合格记录」。

### 1.6 判定表（**逐格实测**，缺格即不算通过）

表内「入库」指该批次实例产出再报工时 `finished_product`（`stock_kind='fg'`）**可用件数增量 > 0**；
「拒收」指增量 = 0 且返回**可读原因**。**必须同时查库字段**（`06` §5.5：只看页面会得到「`-` 不变」，AC-18 无法判定）。

| `quality_status` 状态 | 格 | 前置（同一实例） | 期望：入库/拒收 | 期望：字段终值 | 对应判据 |
| --- | --- | --- | --- | --- | --- |
| `NULL` | N1 | 全新实例、无质检任务、无 NC | **入库**（基线实测 +4，不得回归） | `NULL`（不因放行而改写） | P0-2.4 / AC-15 阳性对照 |
| `NULL` | N2 | 报工后被挂上在办质检任务 | 拒收 + 可读原因 | `pending`（**允许**，因为确有在办任务） | 新增 `GP-N2` |
| `NULL` | N3 | 报工后质检判 `fail` | 拒收 | `fail` + NC **+1**（`target_type='production_record'`） | AC-13 / P0-1.7 / AC-18 / P0-1.6/P0-1.8 |
| `NULL` | N4 | N3 之后处置 `rework` 或 `scrap` 或 `accept` 至 `done`/`approved` | **入库**（恢复放行） | `pass`（`scrap` 时 `status='scrapped'` ⇒ 仍拒收，见 §1.3） | **AC-15**（本轮不可判定 → 必须转 passed） |
| `pending` | P1 | 被人为写成 `pending`，**无**在办任务、**无** NC | **入库**（当前 fg **+0** ❌ → 修复后必须 > 0） | 允许 `pending` 保持或复算为 `pass`（二者取一，**但必须放行**） | **P0-2.5 死锁回归**（与 P0-2.4 成对常驻） |
| `pending` | P2 | 确有在办质检任务 | 拒收 + 可执行原因 | `pending` | `GP-P2` |
| `pending` | P3 | 质检判 `fail` | 拒收（原因指向不合格） | `fail` + NC +1 | AC-13 同格 |
| `pending` | P4 | P3 后处置 `done` | **入库** | `pass`（或 `status='scrapped'` 时拒收） | **AC-15** |
| `pass` | A1 | 正常报工 | **入库** | `pass` | AC-16 阴性对照 |
| `pass` | A2 | 关联任务全部 pass、无 NC | 入库 | `pass`（**不建 NC**：`nonconformity_records` 增量 = 0） | **AC-16** |
| `pass` | A3 | 已入库后又出现新的在办质检任务 | 拒收 | `pending`（在办） | `GP-A3` |
| `fail` | F1 | 未处置 | **拒收**（当前门禁确实拒绝 ✅） | `fail` | AC-14 |
| `fail` | F2 | 处置 `done` | **入库** | `pass` | AC-15 |
| `fail` | F3 | 处置 `scrap`（`status='scrapped'`） | **拒收**（报废终态） | `quality_status='pass'` 但 `status='scrapped'` | §1.3 |

**红线复述**：P0-2.4（放行）与 P0-2.5（死锁）两条判据**必须成对常驻**，缺一不算通过。
**固化为常驻用例**：上表 14 格 → `negative_matrix` 的 `GP` 族（`GP-N1…F3`），每格至少包含
① 库字段断言 ② `finished_product` 增量断言 ③ 拒收格必须断言「原因非空且含复位提示」。

### 1.7 ⚠ 口径更正：产出 → 批次实例的定位链路（**本单新增裁定，直接改变 P-03 的实现**）

**更正对象**：`fix_plan.json` P-03 `fix_action` 第 2 条写的
「经 `batch_item_production_records` 反查 batch_item」——**在报工路径上取不到数据**，照此实现会
「静默定位失败 ⇒ 跳过回写 ⇒ P-03 看起来修了但字段仍是 NULL」。

**只读复核证据**：

| 事实 | 证据 |
| --- | --- |
| 报工端点创建的 `ProductionRecord`**没有** notes | `routes.py:3392-3398` 的构造只传 `employee_id/process_id/quantity/global_sn/date`，**未传 notes** |
| 报工端点另建了一条**唯一关联键** | `global_sn=task.global_sn`（`routes.py:3396`），并在 `:3372-3377` 注释明文「ProductionRecord 以 task.global_sn 作为与任务的关联键」 |
| `batch_item_id` 的权威落点在任务上 | `ProductionRecord` **无** `batch_item_id` 列（`models.py:181-208`）；`TaskAssignment` **有** `batch_item_id`（`models.py:288`） |
| 反查函数的搜索键只在**另一条**路径写入 | `mes_service.py:148-154` 按 `notes.contains('"batch_item_id": N')`；该 notes 仅由 `app/main/production_center.py:318-329` 的 `execute_operation` 写入（`:72-74`/`:230-231` 亦为同约定） |

**裁定（唯一口径）**：

```
record → pr = ProductionRecord.query.get(record.task.target_id)          # 定位产出
       → task = TaskAssignment.query.filter_by(global_sn=pr.global_sn)   # 第一优先：global_sn
       → item = task_batch_item(task)                                    # task.batch_item_id → 实例
   若 global_sn 未命中（production_center 执行记录路径）：
       → item = 按 ProductionRecord.notes 反查实例                        # 仅作回退
   两条都未命中 ⇒ logger.warning + 跳过回写（不抛错、不猜归属）
```

| 产出来源路径 | 定位键 | 说明 |
| --- | --- | --- |
| 报工 `POST /tasks/<id>/update_status`（链 A / B 主路径，AC-13/18 的载体） | `ProductionRecord.global_sn == TaskAssignment.global_sn` → `TaskAssignment.batch_item_id` | **主判据**；`ProductionRecord` 与任务一对一（`routes.py:3376` 幂等拒绝保证） |
| `POST /api/production_center/items/<id>/execute_operation` | `notes` 内的 `{"batch_item_id": N}` | **回退判据**；此路径无工件、可能无任务 |

**两条路径的作用域**：§1.5 的写点（`apply_inspection_result`）只对**有 `InspectionTask`** 的产出触发，
而质检任务只在报工端点按 `ProcessPrice.needs_inspection` 自动创建（`routes.py:3402-3430`）
⇒ 主路径就是报工链；回退分支属**防御性兼容**，不得作为主判据。

**下游影响（必须传播）**：

1. `t7` 的 P-03 实现按上表改写定位逻辑；实现后**必须**证明「`fail` 后 `quality_status` 真的由 `NULL` 变 `fail`」
   （断言**字段真的被写过**，而不是靠「没有异常」判定通过）。
2. `fix_plan.json` 的 P-03 `fix_action` 第 2 条应视为**已被本单更正**；引用时以本单为准。
3. 该更正**不扩大**修复面（仍只改 `mes_service.py` 一处），但**改变了**必须存在的回归断言：
   新增「报工路径 fail 后字段 = fail」的**直接字段断言**（原计划只有 NC 增量断言，字段断言才是 AC-18 的核心）。

---

## 2. DEC-2 —— 返工识别口径与扣料 N 来源

### 2.1 问题（签前必须承认的事实）

| 事实 | 证据（只读复核） |
| --- | --- |
| 开关存在但**全仓零读取点** | 定义 `app/models.py:2603-2609`（`quality.rework_counts_piecework`，默认 `false`，文案「返工工时重复计件」）；读取点 grep = **0** |
| 计件公式不区分返工 | `app/main/routes.py:1815` `piecework = sum(record.quantity * record.process.price for record in production_records)` |
| 返工任务件数**恒 1** | `app/services/mes_service.py:704-712`，`quantity=1` 在 `:708`；实测 `task_rows_delta=1`、`rework_quantity=1`（`05` §UAT-D5） |
| 报废扣料**恒 −1** | `mes_service.py:729-732` `mat.quantity = max(0, mat.quantity - 1)`；实测料账 `5.0→4.0`（`05` §UAT-D6） |
| 报废入库数量也写死 1 | `mes_service.py:210-243`，`quantity=1` 在 `:225` |
| 已有权威消耗字段 | `ProductionRecord.raw_material_quantity`（`models.py:193`）、`ProductionRecordMaterial.quantity`（`models.py:217`）、`MaterialAllocation.consumed_quantity`（`models.py:1496`） |
| 工件是**单件身份**（无 quantity 列） | `models.py:2839-2862`；`Workpiece.batch_item` 为 `uselist=False`（一实例一工件）⇒ 件数口径下 `quantity=1` 成立，但**料账扣减单位必须与原料计量单位一致** |

### 2.2 裁定 A：返工识别（**选定：反查优先，禁用 `task_type` 单判**）

**唯一判据链**（按序命中即认定返工，`ProductionRecord` → 是否计入计件）：

| 序 | 判据 | 说明 |
| --- | --- | --- |
| R1 | 存在 `NonconformityRecord` 使 `rework_task_id == task.id` | **主判据**。`nc.rework_task_id` 在返工处置时写入（`mes_service.py:716`）⇒ 权威、无歧义、**不需要新列** |
| R2 | 该任务 `global_sn` 与生产记录 `global_sn` 相等 | 与报工链既有唯一关联键一致（`routes.py:3372-3377` 注释明文「ProductionRecord 以 task.global_sn 作为与任务的关联键」） |
| R3 | 辅助判据（仅用于人工可读与兜底）：`task.task_type == 'auto'` **且** `task.notes` 以 `返工 不合格单#` 开头 | `mes_service.py:710-711` |

**明确否决**（`fix_plan.json` DEC-2 备选方案的处理）：

| 备选 | 裁定 | 理由 |
| --- | --- | --- |
| `task_type == 'auto'` 单判 | **否决** | `routes.py:8783` 的**批次自动派工**同样 `task_type='auto'` ⇒ 会误伤正常批量派工，把正常工时当返工扣掉 |
| `ProductionRecord.notes` 标记 | **否决** | 报工链创建生产记录时**不写 notes**（`routes.py:3392-3398` 未传 notes）⇒ 无数据源，等于空判据 |
| 新增 `ProductionRecord.is_rework` 列 | **本轮不采用**（可作为阶段 B 的显式化增强） | 需迁移 + `_ENSURED_COLUMNS` 登记 + 回填，成本高于 R1+R2；R1 已能唯一判定 |

**计件口径（P-04 实现）**：`fix_plan.json` 的原始要求是「选定后写进**同一处**并只写一次」。
只读复核确认计件金额有 **4 个计算点**（S1…S4，见 §2.5）⇒ 裁定为
「**同一处**」= **一个共享口径函数**，S1…S4 全部改为调用它（只读一处、只判一次）：

```
开关 = SystemConfig.get('quality.rework_counts_piecework', False)   # 共享函数内唯一读取点
若 开关 为 True  ⇒ 计件包含返工记录（现状语义，回退安全）
若 开关 为 False ⇒ 从求和中剔除判据 R1∨R2 命中的生产记录
```

**阴性断言（防「同解退化」）**：非返工记录**必须不变**（AC-27）；
`SystemConfig.get` 的默认值必须是 `False`（与 `models.py:2604` 的 `value='false'` 一致），
不得用「参数缺省即计入」的实现把开关做成新的假开关。

### 2.3 裁定 B：返工任务件数（P-05 实现口径）

**件数来源优先级**（`dispose_nonconformity` 的 `rework` 分支）：

| 序 | 来源 | 规则 |
| --- | --- | --- |
| 1 | 处置入参 `rework_quantity`（**新增可选 kwarg**，`stock.py:91-97` 从 `data.get('rework_quantity')` 透传） | 显式填写优先；须为正整数，非法 ⇒ `ValueError`（现有 400 通道） |
| 2 | 来源生产记录 `ProductionRecord.quantity`（经 `nc.record` → 其 `task.global_sn` 或该工件最近一条报工记录定位） | **默认**。判据：报工 10 件判 fail ⇒ 返工任务 `quantity=10` |
| 3 | 兜底 | `1`（工件单件语义），**并**在 `task.notes` 追加 `件数取默认值1（未找到来源生产记录）` |

**禁令**：不得**静默**写死 1。取不到来源时必须在 notes/日志留下可解释痕迹
（`fix_plan.json` P-05：当前无法区分「恰好 1 件」与「写死 1 件」）。

**返工作业链**：`rework_task_id` 仍指向新建任务；`TaskWorkpiece` 链接保留
（`mes_service.py:714-717`）。

### 2.4 裁定 C：报废扣料 N 的来源（P-06 实现口径，四条子判据逐条对齐）

**N = 该报废产出**实际投入**的原材料量，按物料逐行扣减**，取值链：

| 序 | 来源 | 口径 |
| --- | --- | --- |
| 1 | 来源生产记录的 `ProductionRecordMaterial` **逐行**（`production_record_id` 匹配） | 每行按 `raw_material_id` **各自扣自己的 `quantity × 本次报废件数`**（AC-29c 不扣错料） |
| 2 | 生产记录 `ProductionRecord.raw_material_quantity` + `raw_material_id`（仅一条消耗） | 视为单行消耗 |
| 3 | 工件 `Workpiece.raw_material_id` | 仅当序 1/2**完全取不到**时使用，且扣减量按「**不扣料**」处理（见 AC-29d），只记 warning |

**硬性约束**：

| 约束 | 规则 | 对应 |
| --- | --- | --- |
| 不为负 | `max(0, 现存 - N)`，夹紧发生时记 `logger.warning`（含物料号、原量、请求量、夹紧后量） | **AC-29b** |
| 不扣错料 | 多条消耗行分别扣各自物料；**不得**只按 `wp.raw_material_id` 取一条（现状缺陷） | **AC-29c** |
| 取不到不扣 | 无 `materials` 行且无 `raw_material_quantity` ⇒ **不扣任何料**，返回/日志含「未扣减」说明，**不得默认减 1** | **AC-29d** |
| 单位一致 | 扣减量单位 = `RawMaterial` 计量单位；多料场景逐料判定，不做跨物料合计 | §2.1 表末行 |
| 件数口径 | 报废扣料量 = 单件消耗 N × 本次报废件数；**默认件数 = 1**（工件单件身份），显式 `scrap_quantity` 覆盖 | P-06 fix_action 第 4 条 |
| 同步 | `inbound_workpiece` 的报废入库数量 `:225` 的写死 `1` 改为与报废件数同一口径（默认 1，显式时同值） | P-06 fix_action 第 4 条 |

**防回退判据**：`NV-4.3`（三种扣量得三个不同余额）必须常驻——若实现回退成「恒减 1」，
该用例必须**红**（`07` §3.1 第 8 行）。

### 2.5 裁定 D：料账与计件的耦合边界（避免多处各写一遍）

**只读复核发现**：计件金额目前有 **4 个独立计算点**，口径必须收敛，否则「开关」只在一处生效 = 新的假开关：

| 计算点 | 位置 | 作用面 |
| --- | --- | --- |
| S1 | `app/main/routes.py:1815` | `/salary_calculation` 主表（P0 判据所在，**必改**） |
| S2 | `app/models.py:148-155` `Employee.total_salary`（`:151`） | 员工列表/详情等处的「总工资」属性（**同族，必须同口径**） |
| S3 | `app/main/routes.py:393` | 员工详情页「当日工资」 |
| S4 | `app/main/routes.py:402` | 员工详情页「当月工资」 |

**裁定**：

| 关注点 | 唯一归属 | 明文 |
| --- | --- | --- |
| 返工记录「是否计入计件」 | **单一共享函数**（建议置于 `app/services/` 下的工资口径助手，或 `mes_service` 内只读函数，如 `piecework_amount(records, employee=None)` / `rework_production_record_ids()`） | 该函数是 `quality.rework_counts_piecework` 的**唯一读取点**；S1/S2/S3/S4 一律调用它，**不得各自再写一份过滤** |
| 返工记录「识别为返工」 | 同一处（`is_rework_task` / `rework_task_ids`） | 禁止在模板/路由各写一份口径 |
| 返工任务「件数」 | `mes_service.dispose_nonconformity` 的 `rework` 分支 | 只此一处写 `TaskAssignment.quantity` |
| 报废「扣料量」 | `mes_service.dispose_nonconformity` 的 `scrap` 分支 | 只此一处写 `RawMaterial.quantity` |
| 模板侧展示 | **不改模板**（`salary_calculation.html:154-155` / `salary_details.html:32-35` / `user_dashboard.html:262-263` 逐行渲染） | 行级展示值遵循其数据源；若数据源来自 S1/S2 则自动一致。**模板里不得出现 `rework_counts_piecework` 判断** |

**P-04 的验收点仍锚定 S1**（`total_stats['piecework']` 两态差值 ≠ 0）；
**S2/S3/S4 的一致性是同批的附加断言**（防止「主表变了、员工总工资没变」的新一类不一致）。

### 2.6 判据形状（**不写死夹具数字**）

复用 `07` 的纪律：验收写**判据形状**，不写死 `75.0/300.0/5.0/4.0` 这些夹具值。

| 判据 | 形状（可机读） |
| --- | --- |
| P-04 | 同一夹具下 `开关=false` 与 `开关=true` 的 `total_stats['piecework']` **差值 ≠ 0**；且非返工记录的贡献在两态下**相等** |
| P-05 | `报工 quantity = Q (Q > 1)` 判 fail 后处置 rework ⇒ `TaskAssignment.quantity == Q` |
| P-06-ac | 料账 = `初始 − Σ(逐消耗行 N_i × 件数)`；且**另一未消耗原料的数量两态相等** |
| P-06-b | 库存 < N ⇒ 终值 `== 0` 且存在夹紧 warning |
| P-06-d | 无消耗数据 ⇒ 料账终值 `== 初始`，且存在「未扣减」说明 |

---

## 3. 冲突判定顺序（实现时遇矛盾按此裁决）

1. **本单 > AC 文本 > `07` 报告行 > 代码注释**（AC 文本中 AC-14 的解释已被 `06` §5.5 的 Y-1 更正，
   以更正后的口径为准：AC-14 的拒绝路径**依赖 NC / 质检任务行**）。
2. **门禁安全 > 放行顺畅**：当「放行一个可能不合格的产出」与「锁死一个可能合格的产出」冲突时，
   取**不锁死**（因为死锁无复位路径，是不可逆损失；漏放行可被后续质检结论纠正）。这是 §1.4 序 3 改判的理由。
3. **不新增列 > 新增列**：能用既有字段（`rework_task_id` / `global_sn` / `raw_material_quantity`）判定的，
   一律不新增列（遵守 AGENTS.md「禁止 `flask db migrate`」「新增列须手写迁移 + `_ENSURED_COLUMNS` 登记」）。
4. **单点唯一 > 多点分散**：同一口径只允许一个写入点/读取点（§2.5）。

---

## 4. 下游改动清单（`t7` / P-04/P-05/P-06 的落地坐标）

| 编号 | 文件:行 | 改动（按本单口径） | 依赖 |
| --- | --- | --- | --- |
| P-03 | `app/services/mes_service.py:403-422` | 在 `:421` 早返回前新增 `production_record` 分支：定位产出 → 写 `quality_status`（含 pass 回写） | DEC-1 §1.5 |
| P-02 | `app/services/mes_service.py:409-422` | 同分支建 `NonconformityRecord(target_type='production_record', target_id=production_record.id, record_id=record.id, status='open')` | DEC-1 §1.5 |
| P-07 | `app/services/mes_service.py:167-207` | 序 3 改判：`pending` 只在「确有在办质检任务/未闭环 NC」时拒绝；拒绝文案含复位动作 | DEC-1 §1.4 |
| P-07b | `app/services/mes_service.py:652-736` | `dispose_nonconformity` 在 `rework/scrap/accept` 完成时对该产出**复算**并写 `pass`（自动复位） | DEC-1 §1.5 |
| P-04 | `app/main/routes.py:1815`（S1，P0-3.1 判据锚点）+ 同口径收敛到 `app/models.py:151`（S2）、`app/main/routes.py:393`（S3）、`app/main/routes.py:402`（S4） | 建**单一**共享口径函数：读 `SystemConfig.get('quality.rework_counts_piecework', False)` + 按 §2.2 判据剔除返工记录；S1…S4 全部改调它 | DEC-2 §2.2/§2.5 |
| P-05 | `app/services/mes_service.py:704-712` | `quantity` 按 §2.3 优先级取值（新增可选 `rework_quantity`），禁止静默 1 | DEC-2 §2.3 |
| P-06 | `app/services/mes_service.py:722-734` + `:210-243` | 按 §2.4 逐料扣 `N × 件数`，`max(0,…)` + warning，取不到不扣；报废入库数量同步 | DEC-2 §2.4 |
| 透传 | `app/main/stock.py:87-97` | `rework_quantity` / `scrap_quantity` 从表单或 JSON 透传（可选，缺省即默认口径） | DEC-2 §2.3/§2.4 |

**回归面（不得遗漏）**：P0-2.4（放行）与 P0-2.5（死锁）成对；AC-16 阴性对照；AC-27 非返工不变；
AC-29b/c/d 三条；`NV-2.1` 与 `NV-4.3` 常驻；`uat_chains.json`（33318 B，SHA256 `360A8570BC0080A2…D23A`，40 条）
逐条 diff：6 条红转绿，34 条绿**不得**变红。真实库 `app.db` SHA256 前后均为
`F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065`。

---

## 5. 机读摘要（供 `t7` 与测试组直接消费）

```json
{
  "decision": "DEC-1/DEC-2",
  "version": "1.0",
  "status": "DECIDED",
  "date": "2026-10-08",
  "source_task": "t2",
  "source_attempt_id": "2d1189ee-7ef9-42e8-86bc-2b061de09098",
  "dec1": {
    "field": "production_batch_items.quality_status",
    "values": {
      "NULL": "未开始/未判定（无结论、无在办质检任务）",
      "pending": "质检进行中（存在在办质检任务或未闭环不合格记录）",
      "pass": "合格（关联质检任务全部 completed 且全 pass，且无未闭环不合格记录）",
      "fail": "不合格（存在 fail 结论且对应不合格记录未闭环）"
    },
    "forbidden_states": ["quality_status=pending 且无在办质检任务且无未闭环不合格记录"],
    "gate_reject_order": [
      "quality_status in (fail, failed, rejected)",
      "status == scrapped",
      "quality_status in (pending, pending_inspection) AND (有在办质检任务 OR 有未闭环不合格记录)",
      "record_ids 有在办质检任务或未闭环不合格记录",
      "工件维度未处置不合格或未完成质检"
    ],
    "gate_pass": "以上皆不命中则放行",
    "auto_write_point": "mes_service.apply_inspection_result",
    "linkage_rule": {
      "primary": "ProductionRecord.global_sn == TaskAssignment.global_sn -> TaskAssignment.batch_item_id -> ProductionBatchItem",
      "fallback": "ProductionRecord.notes.contains('\"batch_item_id\": N')（仅 production_center execute_operation 路径写入）",
      "forbidden": "把 batch_item_production_records 反查当作报工路径主判据（报工创建的 ProductionRecord 不写 notes）",
      "on_miss": "logger.warning + 跳过回写，不抛错不猜归属"
    },
    "correction_note": "本单 §1.7 更正 fix_plan.json P-03 fix_action 第 2 条的定位链路",
    "reset_trigger": "dispose_nonconformity 处置 rework/scrap/accept 且 nc.status in (done, approved) -> 复算写 pass",
    "manual_write_point": "app/main/routes.py:8899（纠正通道，不得成为链路必经）",
    "scrapped_override": "status=scrapped 为终态，即使 quality_status=pass 仍拒绝",
    "matrix_cells": 14,
    "matrix_names": ["N1","N2","N3","N4","P1","P2","P3","P4","A1","A2","A3","F1","F2","F3"],
    "paired_assertions": ["P0-2.4", "P0-2.5"],
    "accepted_values_for_reset": "pass（不回写 NULL）"
  },
  "dec2": {
    "rework_identification": {
      "primary": "NonconformityRecord.rework_task_id == TaskAssignment.id",
      "secondary": "TaskAssignment.global_sn == ProductionRecord.global_sn",
      "assist": "task_type=='auto' AND notes 前缀 '返工 不合格单#'",
      "rejected_alternatives": [
        "task_type=='auto' 单判（与 routes.py:8783 批次自动派工冲突）",
        "ProductionRecord.notes 标记（报工链不写 notes，无数据源）",
        "新增 ProductionRecord.is_rework（本轮不采用，留阶段B）"
      ],
      "consumer": "单一共享口径函数（S1/S2/S3/S4 唯一读取者）",
      "compute_points": {
        "S1": "app/main/routes.py:1815（P0-3.1 判据锚点，必改）",
        "S2": "app/models.py:151 Employee.total_salary（同口径）",
        "S3": "app/main/routes.py:393 当日工资（同口径）",
        "S4": "app/main/routes.py:402 当月工资（同口径）"
      },
      "templates_must_not_branch": [
        "app/templates/main/salary_calculation.html",
        "app/templates/main/salary_details.html",
        "app/templates/main/user_dashboard.html"
      ],
      "config_key": "quality.rework_counts_piecework",
      "config_default": false
    },
    "rework_quantity_source": {
      "order": ["处置入参 rework_quantity", "来源 ProductionRecord.quantity", "1（须在 notes/日志留痕）"],
      "forbidden": "静默写死 1"
    },
    "scrap_material_n_source": {
      "order": [
        "ProductionRecordMaterial 逐行（各扣各自 raw_material_id）",
        "ProductionRecord.raw_material_quantity + raw_material_id",
        "Workpiece.raw_material_id（仅提示，按 AC-29d 不扣料）"
      ],
      "clamp_non_negative": true,
      "warn_on_clamp": true,
      "no_deduction_when_unknown": true,
      "forbidden_default": "默认减 1",
      "quantity_basis": "单件消耗 N × 报废件数（默认 1，显式 scrap_quantity 覆盖）",
      "sync_points": ["mes_service.py:732 扣料", "mes_service.py:225 报废入库数量"]
    }
  },
  "acceptance_matrix": [
    {"id": "N1", "start": "NULL", "precondition": "全新实例，无质检任务，无NC", "expect_output": "allow", "expect_quality_status": "NULL"},
    {"id": "N2", "start": "NULL", "precondition": "报工后在办质检任务", "expect_output": "deny", "expect_quality_status": "pending"},
    {"id": "N3", "start": "NULL", "precondition": "报工后质检 fail", "expect_output": "deny", "expect_quality_status": "fail", "expect_nc_delta": 1, "expect_nc_target_type": "production_record"},
    {"id": "N4", "start": "NULL", "precondition": "N3后处置 done/approved", "expect_output": "allow", "expect_quality_status": "pass"},
    {"id": "P1", "start": "pending", "precondition": "被写成pending但无在办任务且无NC", "expect_output": "allow", "expect_quality_status": "pending|pass", "role": "deadlock_regression"},
    {"id": "P2", "start": "pending", "precondition": "确有在办质检任务", "expect_output": "deny", "expect_quality_status": "pending"},
    {"id": "P3", "start": "pending", "precondition": "质检判fail", "expect_output": "deny", "expect_quality_status": "fail", "expect_nc_delta": 1},
    {"id": "P4", "start": "pending", "precondition": "P3后处置done", "expect_output": "allow", "expect_quality_status": "pass"},
    {"id": "A1", "start": "pass", "precondition": "正常报工", "expect_output": "allow", "expect_quality_status": "pass"},
    {"id": "A2", "start": "pass", "precondition": "关联任务全pass且无NC", "expect_output": "allow", "expect_quality_status": "pass", "expect_nc_delta": 0},
    {"id": "A3", "start": "pass", "precondition": "出现新的在办质检任务", "expect_output": "deny", "expect_quality_status": "pending"},
    {"id": "F1", "start": "fail", "precondition": "未处置", "expect_output": "deny", "expect_quality_status": "fail"},
    {"id": "F2", "start": "fail", "precondition": "处置done", "expect_output": "allow", "expect_quality_status": "pass"},
    {"id": "F3", "start": "fail", "precondition": "处置scrap", "expect_output": "deny", "expect_quality_status": "pass", "expect_item_status": "scrapped"}
  ],
  "required_assertions_per_cell": [
    "查 production_batch_items.quality_status 字段终值",
    "查 finished_product(stock_kind=fg) 可用件数增量",
    "拒收格必须断言原因非空且含可执行复位提示"
  ],
  "acceptance_judgement_shapes": {
    "P-04": "开关 false/true 两态 piecework 差值 != 0，且非返工记录贡献两态相等",
    "P-05": "报工 Q>1 件判 fail 后处置 rework => 返工任务 quantity == Q",
    "P-06-ac": "料账 = 初始 - Σ(N_i * 件数)；未消耗原料两态相等",
    "P-06-b": "库存 < N => 终值 == 0 且存在夹紧 warning",
    "P-06-d": "无消耗数据 => 料账终值 == 初始 且存在未扣减说明",
    "AC-16": "pass 场景 nonconformity_records 增量 == 0 且 quality_status != 'fail'",
    "AC-18": "报工 fail 后 production_batch_items.quality_status 由 NULL 变 fail（直接字段断言，不得只断 NC 增量）",
    "AC-27": "非返工记录计件贡献不变"
  },
  "change_coordinates": {
    "P-03": "app/services/mes_service.py:403-422",
    "P-02": "app/services/mes_service.py:409-422",
    "P-07": "app/services/mes_service.py:167-207",
    "P-07b": "app/services/mes_service.py:652-736",
    "P-04": "app/main/routes.py:1815 + app/models.py:151 + app/main/routes.py:393 + app/main/routes.py:402（共享函数收敛）",
    "P-05": "app/services/mes_service.py:704-712",
    "P-06": "app/services/mes_service.py:722-734 + app/services/mes_service.py:210-243",
    "passthrough": "app/main/stock.py:87-97"
  },
  "db_guard": {
    "production_db": "app.db",
    "sha256_expected": "F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065",
    "rule": "零改动；一切验证用副本"
  }
}
```

---

## 6. 本单未做的事（边界声明，防止越权）

- **未改任何生产代码**：仅只读复核 `app/models.py`、`app/services/mes_service.py`、
  `app/main/routes.py`、`app/main/quality.py`、`app/main/stock.py` 与 `test-reports-2026-10/**`。
- **未新增列/未写迁移**：DEC-2 选 R1 反查即为此（见 §3 冲突裁决第 3 条）。
- **未跑会产 evidence 的脚本**（A-40 纪律）：本单全部结论来自静态只读复核与既有报告引用。
- **未定 AC-29e 台账化**：报废库台账属新功能，沿用 `06` §5.5 的「本期只登记」处置。
- **未定 `heat_lot` / `goods_receipt` 路径的复位细则**：本单只覆盖 `production_record` 与 `workpiece` 两条
  涉及报工产出的路径；来料检已由 `dispose_incoming_nonconformity`（`mes_service.py:600-640`）独立闭环，不在本次修复面。
