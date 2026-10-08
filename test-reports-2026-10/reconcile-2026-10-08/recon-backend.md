# 后端对账（批次4/5/6/7 逐条 + 阶段C P1–P12 现场复核）

- **任务**：t11（替代被取消的 t3）｜**执行者**：后端架构师｜**时点**：2026-10-08
- **工作目录**：`D:\workspace\wage_management_system - bak`｜**解释器**：`F:\Miniconda\envs\wage\python.exe`
- **唯一事实来源**：当前工作区**源码**（下称「实测」）。文档行号一律只作「计划给的原行号」引用，不作事实。
- **输出纪律**：本报告为**新建文件**；仓库内**未修改任何既有文件**（`app/`、`app/templates/`、`scripts/` 保持只读）。
  新增产物仅 3 个，全在 `test-reports-2026-10/reconcile-2026-10-08/` 下：本文件、`probe_backend_field.py`、
  `probe_backend_field.output.json`（后两者为本次现场复核的可复跑探针与其机读读数）。
- **真实库不变量**：`app.db` = `2531328 B` / `F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065` /
  mtime `2026-09-18 12:50:55` —— **复核开工与收尾两次 Hash 一致**，数据库写入全部发生在 `make_app()` 复制出的临时副本上。

---

## 0. 结论摘要

| 批次 | 条目 | 已实现 | 部分实现 | 未实现 | 计划内不做 |
| --- | --- | --- | --- | --- | --- |
| 批次4 质检闭合 | B4-01…B4-08 | 3（B4-01/B4-02/B4-03） | 2（B4-04/B4-05） | 2（B4-07/B4-08） | 1（B4-06） |
| 批次5 返工计件与料账 | B5-01…B5-06 | 5（B5-01/02/04/05/06） | 0 | 1（B5-03） | 0 |
| 批次6 不合格处置可读可办 | B6-01…B6-07 | 0 | 0 | 6（B6-01…B6-06）；1 可选（B6-07） | — |
| 批次7 通知与审计回滚 | B7-01…B7-07（+验证脚本） | 1（B7-06，仅「未新增」） | 0 | 6（B7-01…B7-05、B7-07）+ 计划门禁脚本 `scripts/check_notification_triggers.py` **不存在** | — |

**阶段C 产品问题（P1–P12）计数**：**仍存在 11 条**（P1–P10 + P12）；**已消失 1 条**（P11 的 `.tmp_v15_*` 原载体已被清理，但出现同族新残留 `_probe_tmp/`，见 §5-P11）。
其中 **P8 属文档口径问题、P12 属测试资产口径问题**，二者**不是产品代码缺陷**；若按 `70-` §10.3 的「产品面 10 条」（P1–P10）口径，则 **10 条全部仍需处置**。逐条见 §5。

**三条最需要下游注意的结论**

1. **批次4/5 的主体已在 W2/W3 修复中落地并有对抗验收载体**（`harness/w2w3_probe.py` 判据 46/46，见 §0.3），
   不是「只接线」。本报告用独立探针对其做了**行为级复核**，结论一致。
2. **批次6 与批次7 基本是「零开工」**：模板 33 行原样、通知 4 个触发器**仍零调用点**、
   审计回滚仍无级联/无守恒、计划里的门禁脚本 `check_notification_triggers.py` 与 `check_is_archived_policy.py` **在仓库中不存在**。
3. **B4-02 的「拒绝路径」在报工链上只有一个入口**：报工路径调用门禁时**不传** `production_record`，
   而报工建记录**不写 notes** ⇒ 门禁内部 `record_ids` 恒空 ⇒「有在办质检任务 / 未闭环不合格单」两条拒绝路径
   **在报工路径上不可达**，真正生效的只有 `quality_status`/`status` 分支（即 B4-03 的回写）。
   这**正向印证**计划抬头「必须先做 B4-03」的顺序约束；也意味着 **B4-02 的验收必须显式覆盖「fail 回写后拒绝」**，
   不能靠「创建了质检任务所以会被拦」的直觉断言（实测反例见 §0.2 的 J 组）。

### 0.1 行号漂移总述（计划行号 → 实测行号）

| 文件 | 漂移量 | 说明 |
| --- | --- | --- |
| `app/services/mes_service.py` | **+15 ～ +290**（最大） | 计划给的 `:169-172`（门禁）→ 实测 `:196-207`；`:421-422`（早退）→ 该早退对 `production_record` **已不存在**（分派 `:757-761` 在其前，工件路径早退在 `:763-764`）；`:704-719`/`:722-734`（处置）→ 实测 `:1069-1119`/`:1121-1143`；`:708`（quantity=1 硬编码）→ 实测已改为按来源记录取数（`:1026` 仅兜底 1） |
| `app/main/routes.py` | **+7 ～ +32** | `:1815`（计件求和）→ 实测 `:1822`（且已改为调用共享函数）；`:3594`（唯一通知调用点）→ 实测 `:3601`；`:3679-3737`（嵌套事务）→ 实测 `:3711-3717`；`:8898-8899`（人工 PUT `quality_status`）→ 实测 `:8926-8927`；`:4183`（回滚端点）→ 实测 `:4192`；`:4240-4261`（delete 分支）→ 实测 `:4252-4273`。**反例：P1 对照的 flush 三处 `:564`/`:1734`/`:4420` 未漂移** |
| `app/main/stock.py` | **+6** | 计划 `:113-118`（`:117` 全量取前 200）→ 实测 `:119-124`（`:123`） |
| `app/models.py` | **+3 ～ +9** | 开关种子 `:2603` → 实测 `:2606`；`Employee.total_salary` `:148-155` → 实测 `:148-158`（`:154` 改为调 `piecework_amount`） |
| `app/services/notification_service.py` | **0** | `:52`/`:430`/`:457`/`:484`/`:506` **全部未漂移**（计划行号今天仍准确） |
| `app/templates/main/stock/nonconformities.html` | **0** | `:12`/`:13`/`:14`/`:17-23` **全部未漂移** |
| `app/main/quality.py`（P1/P7 载体） | **0** | `:625`/`:628-635`（P1）、`:837-839`（P7）**未漂移** |
| `app/main/routes.py`（P2/P3/P4/P5/P10 载体） | **0** | `:2061-2066`/`:2171-2176`/`:2733`/`:2717-2720`/`:4000-4006`/`:4016`/`:4022`/`:4028`/`:4945`/`:5036` **全部未漂移** |
| `docs/test-reports/2026-10/04-*.md` | **0** | A4 = `:75`、B2 = `:88` **未漂移** |

> **结论**：漂移集中在 `mes_service.py`（功能大幅增补）与 `routes.py` 后段；**模板、notification_service、
> quality.py 的 P1/P7 载体、routes.py 的导入/回滚段、`04` 文档均未漂移**。凡未漂移者可直接复用计划行号。

### 0.2 行为级实测读数（探针 `probe_backend_field.py`，副本库 + 真实服务函数/真实端点）

| 组 | 覆盖 | 实测读数（机读件 `probe_backend_field.output.json`） |
| --- | --- | --- |
| **A** | P1 真库旁证（副本只读） | `audit_log` = **73 行**，`target_id IS NULL` = **40**，其中 `can_rollback=1` = **10**（与 `70-` §4-P1 的「73/40/10」**逐位相同**） |
| **B** | B4-01/B4-03 | 造「实例 + 任务(global_sn) + 生产记录(同 global_sn) + 质检任务(in_progress) + 质检记录(fail)」→ `apply_production_record_result` 返回 `(rec, item, 'fail')`；`nonconformity_records` **+1** 且 `target_type='production_record'`/`target_id=rec.id`（**工件路径不是唯一出口**）；`batch_item.quality_status: NULL → 'fail'` |
| **C** | B4-02 门禁 | fail 后 `qc_gate_allows_output` = **拒**，原因「实例 … 质检不合格，不得入正品库」；处置 `rework` 至 `done` 后 = **放行**（`quality_status='pass'`）⇒ **验收 2b 阳性对照成立**；报废后 `status='scrapped'` ⇒ 仍 **拒**（终态优先） |
| **D** | B5-05 返工件数 | 显式 `rework_quantity=7` ⇒ 任务 `quantity=7`；缺省 ⇒ `quantity=5`（= 来源生产记录 `quantity`），notes 追加「件数取来源生产记录#1（quantity=5）」⇒ **非静默写死 1** |
| **E** | B5-04 报废扣料 | 消耗行 `3.0`（料2）/`4.0`（料3），报废 2 件 ⇒ 实测 `−6.0 / −8.0`，**对照料4 不变（Δ=0）** ⇒ 逐行各扣各自物料、按实际消耗、不扣错料 |
| **F** | P9 scrap 台账 | 报工路径报废前后 `finished_product(stock_kind='scrap')` 行数 **0 → 0**（Δ=0），但实例已置 `scrapped` |
| **G** | B5-01/B5-02 工资差分 | 用**真实链路**（fail → NC → 处置 rework → 返工任务 → 该任务报工出的记录，`global_sn` 与任务同值）：R1∨R2 识别到返工记录 `id=3`；**开关 `false` ⇒ 计件 `60.0`，`true` ⇒ `160.0`，`Δ=100.0`**（= 5 件 × 价 20.0）；`drop` 侧 `100.0 → 0.0` ⇒ **开关真的决定工资数字** |
| **H** | P3 / P4 | `/employees/import` 3 好 + 2 坏 ⇒ `success=false`、响应「数据验证失败，共发现2个错误」、`employee` 增量 **0**（整单拒绝）；上传文件**残留** `t3_xxxxgood_bad.xlsx`（`residue_exists=true`）。`/tasks/import` 传非 xlsx 内容 ⇒ 返回「导入失败…」但**文件残留** `t3_xxxxbroken.xlsx`（两处都缺 `finally`） |
| **I** | P1 根因 + 审计回滚 | `POST /inventory/finished/add` ⇒ 200，新增审计行 `id=74 / action=添加成品 / target_model=FinishedProduct / target_id=null / can_rollback=true`（**NULL 现场复现**）；对它发起回滚 ⇒ **HTTP 404「目标记录不存在」**（`can_rollback=true` 却指不到对象）。对 `old_data IS NULL` 的 edit 行（`id=70`）回滚 ⇒ **HTTP 500「回滚失败…」**（不是计划要求的「400 + 原因」）；对 old_data 完整的 delete 行（`id=2`）⇒ 200（**叶节点可回滚，缺的是级联/守恒**） |
| **J** | B4-02 结构 | 质检任务 `status='pending'` 时：**报工路径形态**（`batch_item=` 不传 `production_record`）⇒ **放行**（`record_ids` 经 notes 软关联 = **空**）；**质检域形态**（传 `production_record`）⇒ **拒绝**「产出存在未完成的质检任务」；`quality_status='fail'` 后 ⇒ **拒绝**「质检不合格」 |

> 上传类端点已把 `app.config['TEMP_FOLDER']` 改指到副本临时目录 ⇒ **仓库 `uploads/temp` 复核前后均为 0 个文件**（未污染）。

### 0.3 批次4/5 的既有验收载体（非本次产物，作为交叉证据）

| 载体 | 读数 | 出处 |
| --- | --- | --- |
| `harness/w2w3_probe.py --scenario all` | 判据 **46 / passed 46 / failed 0** | `evidence/harness/w2w3-t7-final/w2w3-criteria.json`（本次只读复核：`checks=46`，非 passed = 0） |
| W2/W3 口径裁定 | DEC-1/DEC-2（四值语义、门禁顺序、返工识别 R1/R2、扣料取值链） | `test-reports-2026-10/07b-DEC-1-DEC-2-业务口径决策单.md` §1.2–§2.5 |
| 判定表 + AC 载体 | AC-15（处置后恢复放行）/AC-16（pass 阴性）等在 `w2w3_probe.py:429/496/507/513` 有具名格 | `test-reports-2026-10/33-剩余项业务验收判据.md` §F-11 |

---

## 1. 批次4 —— 无工件报工的质检结论落地（计划 §1 批次4）

> 计划抬头的批内顺序 **B4-01 → B4-03 → B4-02** 与 t6 F2 的「先回写后门禁」约束：**实测已满足**（回写与门禁均已落地，且 §0.2-J 证明门禁在报工路径上只能靠回写生效）。

| 编号 | 计划要求（含计划给的原 file:line） | 当前源码实测行号与行内容 | 状态 | 证据 | 剩余工作 | 置信度 |
| --- | --- | --- | --- | --- | --- | --- |
| **B4-01** | `apply_inspection_result` 对 `production_record` 目标**不再早退**：`fail` → 建 `NonconformityRecord`（按 `target_type` 区分）；`pass` → 不建。计划行号：`mes_service.py:421-422`（早退）、NC 创建仅 `:454`/`:557` | `mes_service.py:736 def apply_inspection_result(record)`；`:753-761` 分派：`elif task.target_type == 'production_record': apply_production_record_result(record, task); return`（**在 `:763 if workpiece is None:` 早退之前**）；`:763-764` 早退**仅对工件路径**；NC 创建实测 `:624-636`（`NonconformityRecord(record_id=record.id, type='rework', …, target_type='production_record', target_id=production_record.id)`）与 `:796-808`（工件路径）。**偏移**：`:421-422` 早退对 production_record 已不存在；`:454/:557` → `:624/:796`（+170/+239） | **已实现** | 现场取行（上列）+ 行为级 B 组：`nc_rows_delta=1`、`target_type='production_record'`、`target_id=rec.id` | 无（结构上已闭合）。**建议**：把「fail 必须建 NC」加入常驻门禁（当前只有 W2/W3 探针载体，未进门禁链） | 高 |
| **B4-03** | 质检结论**自动回写** `ProductionBatchItem.quality_status`。计划行号：唯一写入点 `routes.py:8898-8899`（人工 PUT） | 自动写点实测 `mes_service.py:553 def recompute_production_quality_status`，写入在 `:596-597 if (batch_item.quality_status or '').strip().lower() != value: batch_item.quality_status = value`；调用点 `:640`（fail/结论落地）与 `:667`（处置闭环复位）；日志 `:641-642`「质检结论落地：生产记录 … → 实例 … quality_status=」、`:668-669`（复位）。人工通道仍存（实测 `routes.py:8926-8927 if 'quality_status' in data: item.quality_status = data['quality_status']`）。**偏移**：`routes.py:8898-8899` → 实测 `:8926-8927`（+28） | **已实现** | 现场取行 + 行为级 B/C 组：`quality_status: NULL → 'fail'`；处置 `done` 后 → `'pass'` | 人工 PUT（`:8926-8927`）仍与自动写点并存 ⇒ 需在文档明确「人工通道只作纠正」（`07b` DEC-1 §1.5-4 已写，代码未加提示） | 高 |
| **B4-02** | `fail` 后**门禁生效**：该生产订单/实例的后续产出**被拒入正品库**并给出可读原因。计划行号：门禁 `mes_service.py:169-172` | 门禁 `mes_service.py:157 def qc_gate_allows_output(...)`；batch_item 分支实测 `:196-207`（`:199-200 quality_status in ('fail','failed','rejected') ⇒ 拒，原因「实例 … 质检不合格，不得入正品库」`）；`:201-202` `status=='scrapped'` ⇒ 拒；`:203-207` `pending/pending_inspection` **且** `has_open_documents` ⇒ 拒；`:209-212` 有在办质检任务/未闭环 NC ⇒ 拒；报工路径调用实测 `routes.py:3711-3717`（`with db.session.begin_nested(): finished_product, reason = mes_service.inbound_production_output(task=task, production_order=order_for_output, process_id=task.process_id, quantity=task.quantity)`）→ 内部 `mes_service.py:351 allowed, reason = qc_gate_allows_output(batch_item=item, workpieces=workpieces)`；拒后 `:352-354` warning + `return None, reason`，路由 `:3718-3721` 记 warning。**偏移**：`:169-172` → 实测 `:196-207`（+27） | **已实现（拒绝路径可达，但只有一条在报工链上可达）** | 现场取行 + 行为级 C/F/J 组：fail ⇒ 拒（可读原因）；处置 done ⇒ 放行；报废 ⇒ 仍拒；**J 组实测：报工形态（不传 `production_record`）下 `record_ids=[]` ⇒ 「有在办质检任务」不命中（放行），传 `production_record` 才命中** | ① **验收必须按「fail 回写后再报工」构造**（不能靠「已建质检任务」）；② 若业务上希望「报工产出存在未完成质检任务也拦」，需给报工路径补传 `production_record`（**本轮未做，属口径变更，须先拍板**）；③ 验收 2b（处置后恢复放行）已有载体（`w2w3_probe` 格 N4/P4） | 高 |
| **B4-04** | `/quality/nonconformities` 能查到报工路径的不合格，且能看出对应哪张生产记录。计划行号：`stock.py:113-118`（`:117` 全量取前 200） | 列表路由实测 `app/main/stock.py:119-124`：`:122 def manage_nonconformities():`、`:123 items = NonconformityRecord.query.order_by(NonconformityRecord.id.desc()).limit(200).all()`（**无任何筛选**，故 `target_type='production_record'` 的行**能查到**）；模板实测 `app/templates/main/stock/nonconformities.html:14`「`{% if nc.workpiece_id %}` 链接 `workpiece_detail`，`{% else %}-{% endif %}`」⇒ production_record 路径（`workpiece_id IS NULL`）**只显示 `-`**，**看不出对应哪张生产记录**。**偏移**：`:113-118`/`:117` → 实测 `:119-124`/`:123`（+6） | **部分实现** | 现场取行（路由行 + 模板 `:14`）+ 行为级 B 组（该 NC 的 `workpiece_id=null`） | 列表页需按 `target_type` 渲染目标列（production_record ⇒ 显示 `ProductionRecord.global_sn` 并给链接）；当前模板只认工件（与 B6-02 是同一处改动） | 高 |
| **B4-05** | 处置动作对报工路径可用（**返工 → 新建任务**；**报废 → 入报废库台账**）。计划行号：`mes_service.dispose_nonconformity`（返工 `:704-719`、报废 `:722-734`） | 入口实测 `mes_service.py:1029-1030 def dispose_nonconformity(nc, action, *, notes='', scrap_cost=0, rework_process_id=None, employee_id=None, target_date=None, rework_quantity=None, scrap_quantity=None)`；返工分支实测 `:1069-1119`（`:1071-1084` 工序/员工的取值链「工件最近任务 → 来源记录 → 当前用户员工 → `Employee.query.first()`」、`:1085-1086` 件数、`:1088` `task_notes = f'返工 不合格单#{nc.id}'`、`:1091-1101` 建 `TaskAssignment` 并 flush、`:1105 nc.rework_task_id = task.id`、`:1117 nc.status='done'`）；报废分支实测 `:1121-1143`（`:1125-1131 if wp:` → `inbound_workpiece(wp, stock_kind='scrap', …, quantity=pieces)`、`:1133-1134` 扣料、`:1138 item.status='scrapped'`）；端点实测 `stock.py:95-104`（`dispose_nonconformity_api` → commit）。**偏移**：`:704-719`/`:722-734` → 实测 `:1069-1119`/`:1121-1143`（+365/+399） | **部分实现**：返工 ✅；**报废入库台账仅对「有工件」路径成立**，报工路径（`workpiece_id IS NULL`）**不产生报废台账行** | 现场取行 + 行为级 D/E/F 组：返工建任务且件数正确；报废扣料正确，但 `scrap_rows_delta=0` | 报工路径报废需补 `scrap` 台账（与 **P9** 同一条）；另：返工的工序/员工缺省仍会**静默落到 `Employee.query.first()`**（`:1081-1084`），与 B6-03「必须能选工序与员工、未选给可读提示」配套修 | 高 |
| **B4-07** | **事务/原子性**：`fail` 处置（建 NC + 回写 `quality_status` + 库存动作）必须**同事务**或**显式声明分步补偿**，禁止「NC 已建但门禁未生效」的中间态。计划行号：`routes.py:3679-3737` 的 `db.session.begin_nested()` 模式可复用 | 质检提交链实测 `quality.py:896 @bp.route('/api/quality/records/<int:record_id>/submit')` → `:961-964` 任务置 completed → `:967-976` 建审计行 → **`:978 db.session.commit()`** → `:980-981 from app.services import mes_service; mes_service.apply_inspection_result(record)`（**NC 创建 + `quality_status` 回写发生在此调用内**）→ `:990 db.session.commit()`；异常出口 `:997-1002`（`_reraise_http(e)` → `rollback()` → 500）。报工链则**有**嵌套事务：`routes.py:3711 with db.session.begin_nested():` 包住 `inbound_production_output`。**偏移**：`:3679-3737` → 实测 `:3711-3717`（+32） | **未实现（存在两段提交缝）** | 现场取行（`:978` commit、`:981` 调用、`:990` 第二 commit） | 把「质检结论落地」纳入**同一事务**（把 `:981` 移到 `:978` 之前，或对 `:978` 只 `flush()`），否则「质检记录已提交、NC/门禁未落地」的中间态与「500 但结论已入库」都可复现；同时应按计划**显式声明**该边界（文档 + 代码注释） | 中高（缝的存在是**确定**的；能否被外部触发取决于第二个 commit 的失败注入，本轮**未做故障注入**） |
| **B4-08** | **两条生产链的产出计数一致性对拍**：报工路径（`quantity=task.quantity` 一行批量）与工件路径（单件 1 行）入库后**件数合计必须相等**（**对拍脚本**，纳入本批验收）。计划行号：`routes.py:3700-3704` vs `mes_service.py:210-243` | 报工路径实测 `routes.py:3712-3717`（`quantity=task.quantity`）；工件路径实测 `mes_service.py:225 def inbound_workpiece(workpiece, stock_kind='fg', inspector_name='系统', product=None, quantity=1)`（默认 1 件）；**对拍脚本：不存在** —— 全仓检索 `scripts/`（15 个 .py）与 `harness/`（60 个 .py）**无任何**件数守恒/双链对拍脚本；计划 §3.3 T-F 的「件数守恒」仅由 `w2w3_probe` 的**单链**格（N3/N4/A1/A2）覆盖，**未做「两条链合计相等」**。**偏移**：`:3700-3704` → 实测 `:3712-3717`；`mes_service.py:210-243` → 实测 `:225-270` | **未实现** | 现场取行 + 全仓文件清单（`scripts/`、`harness/` 逐一列举，无该脚本） | 新增对拍脚本（建议纳入门禁链，判据形状：「同一订单/实例两条链的 `fg` **件数合计**相等」，按 `docs/业务流程现状与缺口.md` §6.1 **禁止用行数判定**） | 高（「脚本不存在」是确定事实） |
| **B4-06** | **本轮不做**「产出行按次拆分」前置项（除非 Q-1 选 B） | 无「按次拆分」实现；现存形态即 Q1 建议的默认 A（**阻断 + 登记**）：门禁拒绝 + NC 登记（`mes_service.py:196-212`、`:624-636`）。**偏移**：n/a（计划本就标注「不做」） | **计划内不做（符合）** | 现场取行（同 B4-01/B4-02）+ 全仓无拆分逻辑 | 无；建议在后续规划中把「Q-1 选 A」**显式登记为已决**（避免下一轮误判为遗漏） | 中高 |

---

## 2. 批次5 —— 假开关接线与工资/料账正确性（计划 §1 批次5 + F1/F3 取数规则）

> **口径迭代提示（重要）**：计划正文写的是 F1 修法「`join(TaskAssignment, global_sn==global_sn)` + `TaskAssignment.notes.like('返工 不合格单#%')`」与 F3「主取数 `record.materials`」。
> 实测实现采用的是**更晚的 DEC-1/DEC-2 裁定**：返工识别 = **R1 `NonconformityRecord.rework_task_id` → R2 `global_sn`**（`07b` §2.2，**明确否决 notes 前缀单判与 `task_type` 单判**）。
> 二者**目标一致、判据更强**；下表按「计划要求 → 实测」逐条给出差异，**不把口径升级记成未实现**。

| 编号 | 计划要求（含原 file:line） | 当前源码实测行号与行内容 | 状态 | 证据 | 剩余工作 | 置信度 |
| --- | --- | --- | --- | --- | --- | --- |
| **B5-01** | 接线 `quality.rework_counts_piecework`：默认 `false` 不计件、`true` 计件。计划行号：**零读取点**（`models.py:2603` 唯一命中；求和 `routes.py:1815`） | 读取点实测 `mes_service.py:1761-1766 def rework_counts_piecework()`（`:1763 value = SystemConfig.get('quality.rework_counts_piecework', False)`，字符串兜底 `'1/true/yes/on'`）；开关种子实测 `models.py:2606-2612`（`value='false'`，文案「返工工时重复计件」）；**四个工资计算点全部改为调用共享函数**：S1 `routes.py:1822 piecework = piecework_amount(production_records)`、S2 `models.py:154 piecework = piecework_amount(list(self.production_records))`（`Employee.total_salary`）、S3 `routes.py:400 daily_piecework = piecework_amount(daily_production)`、S4 `routes.py:409 monthly_piecework = piecework_amount(monthly_production)`；**模板无开关判断**（全仓模板 grep `rework_counts_piecework` = 0）。**偏移**：`routes.py:1815` → 实测 `:1822`（+7）；`models.py:2603` → 实测 `:2606`（+3） | **已实现** | 现场取行（4/4 计算点）+ 行为级 G 组：`false ⇒ 60.0`、`true ⇒ 160.0`、`Δ=100.0`（**行为级差分成立**，非「有读取点」） | 无（代码侧）。**建议**：把 T-B 的「双向差分 + 阴性对照」做成常驻门禁脚本（计划 §3.3 T-B 要求的脚本目前不存在） | 高 |
| **B5-02** | 返工记录识别链路（F1 修正后形态）；**不新增列** | 实测 `mes_service.py:1758 REWORK_NOTE_PREFIX = '返工 不合格单#'`；`:1769-1775 def rework_task_ids()`（**R1**：`NonconformityRecord.rework_task_id` 非空集合）；`:1778-1785 def rework_task_global_sns()`（**R1 → R2**：取这些任务的 `global_sn`）；`:1788-1794 def rework_production_record_ids(records)`（`{r.id for r in records if r.global_sn in sns}`）；判定处 `:1812-1824 def piecework_breakdown(records)`，关键行 `:1815 excluded = set() if rework_counts_piecework() else rework_production_record_ids(records)`；`:1797-1801 def is_rework_task(task)`；`:1804-1809 def rework_hint(task)`（R3，仅提示）。返工任务 `global_sn` 由模型 `__init__` 自动生成（`models.py:374-377`），报工建记录带 `global_sn=task.global_sn`（`routes.py:3399-3405`，计划记 `:3392-3398`，+7）⇒ **R1→R2 链路真实闭合**。**未新增列**（`check_properties` 期望值未变，23 文件 / 74 模型类） | **已实现**（判据升级为 R1∧R2） | 现场取行（R1/R2/R3 三层）+ 行为级 G 组：`R1R2_identified_rework_record_ids=[3]`，且该记录正是「返工任务报工产生」的记录；开关两态工资不同 | ① **R3（notes 前缀）不参与判定**：若将来出现「NC 未写 `rework_task_id`」（例如工序/员工推不出而不建返工任务，`mes_service.py:1112-1116`）的返工记录，工资侧**不会**剔除 ⇒ 需要 A/B 断言覆盖该支路；② 计划的 `notes.like(...)` join 与实测不同，**规划文本需回填实测口径** | 高 |
| **B5-03** | 工资明细**可区分**返工产量（哪些是返工、哪些正常） | 实测**无任何消费方**：`piecework_breakdown`（`:1812`）除 `piecework_amount`（`:1833`）外**零调用**；`routes.py` 只取 `piecework_amount` 的标量（`:400/:409/:1822`）；模板 `salary_calculation.html:59-72/88-120` 仅渲染 `total_stats.piecework` / `data.piecework` 汇总列，`salary_details.html`/`user_dashboard.html` 亦无返工分列（全仓模板 grep `返工\|rework` 命中仅 `nonconformities.html:20` 按钮与 `admin_dashboard.html:601` 图表标签） | **未实现** | 现场取行（`piecework_breakdown` 的调用图 = 1）+ 模板 grep 证据 | 后端侧已有可直接复用的 `piecework_breakdown(records) → (counted, dropped, excluded)`（AC2.3 只需传 `dropped`/`excluded` 到明细接口 + 模板加一列）；**建议与 B6 一起做，成本极低** | 高 |
| **B5-04** | 报废扣料**按实际消耗**（替代 `mat.quantity - 1`）；按 F3 五条取数规则。计划行号：`mes_service.py:729-732` 的 `mat.quantity = max(0, mat.quantity - 1)` 硬编码 | **硬编码已不存在**（全仓 grep `quantity - 1`/`mat.quantity` 仅命中 `:1202-1205` 的 BOM 装配扣料）。实测取值链 `mes_service.py:673-700 def scrap_material_plan`：① `:683-690` 逐行 `ProductionRecordMaterial` 按 `raw_material_id` 合并求和；② `:691-692` 兜底 `raw_material_quantity + raw_material_id`；③ `:693-699` 两者皆无 ⇒ **空清单 + warning（不扣任何料）**；扣减 `:703-733 def deduct_scrap_materials(plan, pieces=1, nc=None)`：`:721-722 before/requested = 单件量 × 件数`、`:724-729` 夹紧 0 并记 warning（含物料号/原量/请求量/夹紧后量）、`:730 material.quantity = after`；调用点 `:1133-1134` | **已实现** | 现场取行 + 行为级 E 组：`3.0×2 → −6.0`、`4.0×2 → −8.0`、**对照料 Δ=0**（覆盖 4a 实际消耗 N≠1、4c 不扣错料；4b 夹紧与 4d 不扣料由 `w2w3_probe` 的 AC-29-b/-d 覆盖，46/46 内含） | 无（代码侧）。**建议**：`w2w3_probe` 的 AC-29-b/-d 目前**未回写进断言账本**（见 `27-` §C-11「有载体未登记」）⇒ 归阶段C 台账动作 | 高 |
| **B5-05** | 返工任务**件数不再固定 1**（或明确「由处置时填写」）。计划行号：`mes_service.py:708`（`quantity=1`） | 实测 `:1007-1026 def rework_quantity_for(nc, workpiece, explicit=None, production_record=None)`：`:1012-1019` 显式入参（≤0/非整数 ⇒ `ValueError` → 端点 400）；`:1022-1025` 来源生产记录 `quantity`（**返回留痕说明**）；`:1026 return 1, '件数取默认值1（未找到来源生产记录）'`（**兜底留痕，非静默**）；入参透传 `stock.py:93/101`（`rework_quantity`）；调用 `mes_service.py:1085-1090`（notes 追加说明）。**偏移**：`:708` → 实测 `:1026`（+318） | **已实现** | 现场取行 + 行为级 D 组：显式 7 ⇒ `quantity=7`；缺省 ⇒ `quantity=5` 且 notes 含「件数取来源生产记录#1（quantity=5）」 | 无。**建议**：`rework_quantity` 目前是**端点可选入参**，UI 未提供输入框（模板 33 行无该字段）⇒ 与 B6-03 一并补 | 高 |
| **B5-06** | 报废成本口径**登记**（`nc.scrap_cost` 单字段、无台账；本批只登记不做台账）。计划行号：`mes_service.py:723` | 实测 `:1123 nc.scrap_cost = scrap_cost or 0`（生产路径）与 `:976 nc.scrap_cost = scrap_cost or 0`（来料检路径）；模型 `models.py:944 scrap_cost = db.Column(db.Float, default=0)`；**全仓无报废成本台账/汇总表**（grep `scrap_cost` 命中 11 处，全为入参/单字段写入/日志 payload）；启动自愈列登记 `app/__init__.py:77 ('scrap_cost', 'FLOAT')`。**偏移**：`:723` → 实测 `:1123`（+400） | **已实现（按计划仅登记）** | 现场取行（grep 全量 11 处）+ 行为级 E 组：`nc_scrap_cost=12.5` | 无（本批口径即「只登记」）；若后续要做成本台账，属**新增口径**，需先拍板 | 高 |

**F1 / F3 取数规则的实测对应**（计划 §1 批次5 的 `F1`/`F3` 两段）

| 规则 | 计划文字 | 实测 | 判定 |
| --- | --- | --- | --- |
| F1 返工识别 | `join(TaskAssignment, global_sn==)` + `notes.like('返工 不合格单#%')` | R1 `rework_task_id` → R2 `global_sn`（`mes_service.py:1769-1794`）；notes 前缀**降级为提示**（`:1804-1809`） | **更强实现，目标达成**；规划文本需回填 |
| F1 行为级差分 | false/true 两次运行工资数字**不同** | 实测 `60.0 → 160.0`（Δ=100） | **通过** |
| F3 主取数 | `record.materials` 逐行按 `raw_material_id` 扣 `row.quantity` | `:683-690` 逐行 + 同料合并 | **通过** |
| F3 兜底 | 空则用 `raw_material_quantity` | `:691-692` | **通过** |
| F3 取不到不扣 | 不得默认减 1，记 warning + 留痕 | `:693-699` warning「报废处置未扣减：未找到产出的消耗明细…」 | **通过** |
| F3 不为负 / 不扣错料 | `max(0,…)` + 逐料 | `:724-730` 夹紧 + warning；逐行各自物料 | **通过**（E 组实测） |

---

## 3. 批次6 —— 不合格处置的「能看懂、能办完」（计划 §1 批次6）

> **本批后端侧几乎为零开工**：`app/templates/main/stock/nonconformities.html` 仍是 **33 行**最小页面；`stock.py` 列表路由**无筛选参数**；`quality.py` 的详情接口**不含 `nonconformity` 键**。以下行号**全部未漂移**（与计划一致）。

| 编号 | 计划要求（含原 file:line） | 当前源码实测行号与行内容 | 状态 | 证据 | 剩余工作 | 置信度 |
| --- | --- | --- | --- | --- | --- | --- |
| **B6-01** | 「类型/状态」显示**中文**。计划：`nonconformities.html:12`/`:13` | 实测 `:12 <td>{{ nc.type }}</td>`、`:13 <td>{{ nc.status }}</td>`（**仍直接渲染英文枚举**）；模型中已有可复用的人读口径 `NonconformityRecord.target_label`（`models.py:954-961`）与 `mes_service.INCOMING_NC_LABELS`（`:816`），但**未接入模板** | **未实现** | 现场取行（`:12`/`:13`，行号与计划一致） | 加枚举→中文映射（后端字典或 Jinja 过滤器）；AC4.1 要求 DOM 可见文案不再出现 `open`/`pending_approval`/`rework`/`scrap`/`accept` | 高 |
| **B6-02** | 来料检不合格行可**跳转到到货单/采购单**（不再全 `-`）。计划：`nonconformities.html:14` | 实测 `:14 <td>{% if nc.workpiece_id %}<a href="{{ url_for('main.workpiece_detail', id=nc.workpiece_id) }}">{{ nc.workpiece_id }}</a>{% else %}-{% endif %}</td>`（**只认工件**）；来料检 NC 的 `workpiece_id` 为 NULL（模型注释 `models.py:926`、`nonconformity_target` `:819-835`）⇒ 显示 `-` | **未实现** | 现场取行（`:14`）+ 模型 `target_type/target_id` 语义（`:946-948`） | 按 `target_type` 分支渲染：`goods_receipt` → `goods_receipt`/采购单链接；`production_record` → 生产记录链接（与 B4-04 同一处） | 高 |
| **B6-03** | 返工必须能**选工序与员工**；未选给可读提示。计划：`nonconformities.html:18-23` 不带参数 → 落到 `mes_service.py:697-703` | 实测 `:18-23` 表单只含 `csrf_token` 与三个 `name="action"` 按钮（**无 `rework_process_id`/`employee_id`/`rework_quantity`/`scrap_quantity` 任何输入**）；服务端缺省链实测 `mes_service.py:1073-1084`（工序：工件最近任务 → 来源记录；员工：来源记录 → **`Employee.query.filter_by(user_id=current_user.id).first() or Employee.query.first()`**）⇒ **仍会静默指派第一个员工** | **未实现** | 现场取行（模板 `:18-23` + 服务 `:1073-1084`） | 表单补两个必填下拉（工序/员工，可复用 `get_processes`/`get_inspectors` JSON API）+ 未选返回 400 可读提示；`stock.py:89-102` 已支持透传，**只缺前端与必填校验** | 高 |
| **B6-04** | 不适用动作**不提供按钮**或明确说明（而非 400 报错）。计划：`nonconformities.html:17`；来料检点返工走 `mes_service.py:604-605` 抛错 | 实测 `:17 {% if nc.status in ('open', 'pending_approval') %}` ⇒ **对所有未闭环单都显示三按钮**（含来料检）；服务端实测 `mes_service.py:1041-1043`（`target_type=='goods_receipt'` → `dispose_incoming_nonconformity`）→ `:946-947 if action not in INCOMING_NC_ACTIONS: raise ValueError('来料检不合格仅支持退货/让步接收/报废处置')` → 端点 `stock.py:110-112` ⇒ **HTTP 400**。**偏移**：计划 `:604-605` → 实测 `:946-947`（+342） | **未实现** | 现场取行（模板 `:17` + 服务 `:946-947` + 端点 400 通道） | 模板按 `target_type` **条件渲染动作集**（来料检只给退货/让步接收/报废）；后端已有明确错误文案可继续兜底 | 高 |
| **B6-05** | 让步审批人可按「待审批」**筛选**。计划：`stock.py:117` 全量前 200、无筛选；审批是「同按钮点第二次」 | 实测 `stock.py:123`（`limit(200)`、**无 `request.args` 读取**、模板无筛选表单）；审批机制实测 `mes_service.py:1055-1067`（`accept`：角色不在 `quality.concession_approver_roles` ⇒ `nc.status='pending_approval'`，否则 `approved` + `approver_id` + `approved_at`）与来料检 `:959-970`（同形）⇒ **「同按钮点第二次」仍是唯一审批入口**。**偏移**：`:117` → 实测 `:123`（+6） | **未实现** | 现场取行（路由 `:123` + 服务 `:1055-1067`） | 列表路由加 `status` 筛选参数 + 模板筛选控件（计划限定「不改二次点击机制本身」） | 高 |
| **B6-06** | 质检记录详情弹窗显示处置信息（消除死分支）。计划：`app/main/quality.py` 中 `nonconformity` **零命中**（仅 `:7` import）→ 模板 `quality/records.html:406-429` 恒隐藏 | **实测仍是零命中**：`quality.py` 全文件 grep `nonconform` = **1 处，且仅为 `:7` 的 import**；详情接口实测 `:1271-1329 def get_inspection_record_detail`，其 `record_data`（`:1313-1324`）字段为 `id/record_code/type/inspection_target/inspector_name/inspection_time/result/notes/items/base_items` —— **无 `nonconformity` 键**；模板实测 `records.html:404-430`（`:406 if (record.nonconformity) { … } else { nonconformityContainer.style.display = 'none'; }`）⇒ **恒走 else 分支** | **未实现** | 现场取行（`quality.py:7` 唯一命中 + `:1313-1324` 键清单 + 模板 `:404-430`） | 详情接口补处置信息（可从 `NonconformityRecord.query.filter_by(record_id=record.id)` 取：处置类型/处置人/时间/状态/备注），并按模板已有字段名（`handling_method/handler_name/handling_time/handling_notes`）对齐；AC7.1 | 高 |
| **B6-07** | 让步审批通知（**可选**，与批次7 通知接线合并做最省）。计划：通知触发器仅 1 个有调用点 | 实测：`dispose_nonconformity` 的 `accept` 分支（`:1055-1067`）与 `dispose_incoming_nonconformity`（`:959-970`）**均无任何通知调用**；`notify_*` 全仓调用点仍只有 1 个（`routes.py:3601 notify_raw_substitution`，见 §4） | **未实现（计划标注为可选）** | 现场取行（两处 accept 分支）+ `notify_*` 调用点清单 | 若做：在 `nc.status='pending_approval'` 落点调 `create_notification(trigger_type='quality_issue'|'task_assignment', related_model='NonconformityRecord', related_id=nc.id)`；建议与 B7-01…B7-03 同一批，且**先**解决 B7-07 幂等 | 高 |

---

## 4. 批次7 —— 可追踪性：通知触发器接线 + 审计回滚级联（计划 §1 批次7）

| 编号 | 计划要求（含原 file:line） | 当前源码实测行号与行内容 | 状态 | 证据 | 剩余工作 | 置信度 |
| --- | --- | --- | --- | --- | --- | --- |
| **B7-01** | 派工后发通知（`notify_task_assignment`）。计划：定义 `notification_service.py:506`；**唯一**调用点 `routes.py:3594`（`notify_raw_substitution`） | 定义实测 `notification_service.py:506 def notify_task_assignment(employee_name, task_count, batch_number=None)`（**行号未漂移**）；**调用点 0**（`notify_task_assignment` 全仓仅 1 命中 = 定义处）；唯一在用的通知函数实测 `routes.py:3601 notify_raw_substitution(`（在 `update_task_status` 的替用分支内；计划记 `:3594`，+7） | **未实现** | 现场取行（定义 + 调用点 = 1/1 命中在定义处） | 在派工写入路径（`routes.py:4384 add_task` / `:3111 manage_tasks` / 生产中心派工）接入；**并满足 B7-06/07**（不得新增隐式 commit、需幂等） | 高 |
| **B7-02** | 库存预警通知（`notify_inventory_warning`）。计划：`notification_service.py:484`（零调用点） | 定义实测 `:484 def notify_inventory_warning(material_name, current_stock, min_stock)`；**零调用点**（全仓 1 命中 = 定义处）；库存写入点（如 `routes.py:3490 raw_material.quantity -= …`）附近**无**安全库存比较 | **未实现** | 现场取行 + 全仓 `notify_*` 调用点清单（唯一 = `routes.py:3601`） | 在库存递减/入库路径加「低于 `min_stock`」判定并调通知；需先明确 `min_stock` 数据源（当前无该列/无配置项 ⇒ 需拍板，可能涉及新增配置） | 高 |
| **B7-03** | 工序变更 / 规格变更通知。计划：`notification_service.py:430` / `:457`（零调用点） | 定义实测 `:430 def notify_process_change(...)`、`:457 def notify_spec_change(...)`；**两者零调用点** | **未实现** | 现场取行（同上） | 在工序/规格变更落点接入（`routes.py` 的 `ProductProcess`/`ProductBOM`/订单规格更新段）；建议与 B7-01 同批 | 高 |
| **B7-04** | 审计回滚**级联**：`delete` 分支恢复父行时按关系恢复子行。计划：`routes.py:4183`；`delete` 分支 `:4240-4261` 只 `db.session.add(new_record)`，无级联 | 端点实测 `routes.py:4192-4195`（`@bp.route('/audit_logs/rollback/<int:log_id>', methods=['POST'])` / `@require_capability('audit.rollback')` / `def rollback_audit_log(log_id)`）；`delete` 分支实测 `:4252-4273`：`:4254 new_record = model_class()` → `:4255-4259` 逐字段 `setattr` → **`:4261 db.session.add(new_record)`** → `:4264-4271` 回滚审计行 → `:4272 commit`（**无任何子行恢复**）；反射入口实测 `:4182-4189 def _resolve_audit_model(model_name)`（计划记 `:4170`，+12）。**偏移**：`:4183` → `:4192`（+9）；`:4240-4261` → `:4252-4273`（+12） | **未实现** | 现场取行（`:4252-4273` 全段）+ 行为级 I-4（叶节点 `ProcessPrice` 回滚 **200 成功** ⇒ 缺的正是「带子行的父行」这一情形） | 级联恢复（按 `models.py` 关系/`ondelete` 反向恢复子行）或**显式拒绝**（带子行时 400 + 原因，避免 `IntegrityError`）；AC4：带子行父记录回滚后**子行数前后一致** | 高 |
| **B7-05** | 回滚**守恒**：回滚已扣料生产记录后库存与 `MaterialAllocation.consumed_quantity` 回到扣料前；否则 **400 + 原因**。**前置判定（t6 §3④）**：先判定 `AuditLog.old_data` 是否真含「扣料量/子行」 | **前置判定结果：`old_data` 不含扣料/子行信息** —— 只读查真库 `audit_log`：`old_data IS NULL` = **61/73**；`old_data` 文本含 `materials`/`raw_material`/`consumed` 的行 = **0**；`rollback_type='edit'` 且 `old_data IS NULL` = **2 行**（`id=42` 保存工序分配规则/`ProcessAssignmentRule`、`id=70` 更新任务完成与用料/`TaskAssignment`）；`target_model='ProductionRecord'` 的 edit 行 = **0**。⇒ 按 t6 建议**本项应降级为「明确 400 + 原因」**；而实测端点**两者都没做**：`:4228-4251` 的 `edit` 分支 `:4232 for key, value in log.old_data.items():` 在 `old_data IS NULL` 时抛 `AttributeError` → `:4278-4282` 兜底 ⇒ **HTTP 500「回滚失败，请稍后重试或联系管理员」**（行为级 I-3 实测）；`delete` 分支同样 `:4255 for key, value in log.old_data.items():`（同一缺陷面）。**偏移**：计划 `:4170` 反射入口 → 实测 `:4182` | **未实现**（且**前置判定已给结论：守恒在既有数据上不可实现**） | 现场取行 + 只读真库取数（61/0/2/0 四个读数）+ 行为级 I-3（`id=70` 回滚 ⇒ **500** 而非 400） | ① 按 t6 结论把本项**登记为「明确 400 + 原因」**（不得承诺守恒）；② 修 `old_data is None` 分支（`if not log.old_data: return 400 + 原因`）；③ 若要真守恒，需先改**写入面**让 `old_data` 含扣料明细（属口径/迁移变更，须单独排期） | 高 |
| **B7-06** | 新增接线**不得各写一次隐式 `commit`**。计划：既有 `notify_raw_substitution` 内部自提交（`routes.py:3594` 调用点） | 实测 `notification_service.py:107-121`（`db.session.add(notification)` → `:108 flush()` → `:115 _create_receivers_by_rules(...)` → `:121 db.session.commit()`）⇒ **`create_notification` 内部自带 commit**；异常 `:126-129 rollback + raise`；唯一调用点 `routes.py:3601`（包在 `:3575-3608 try/except` 内，吞异常仅记日志）。因**未新增任何接线**，故「净增 = 0」**形式上成立**，但**约束本身仍待执行**（B7-01…B7-03 一接线就会立刻违反） | **形式已实现（未接线 ⇒ 未新增）**；**约束未落地** | 现场取行（`:107-121`）+ 调用点计数（1） | 接线时必须先给 `create_notification` 加 `commit=False`（或调用方 `begin_nested`）**再**接线，否则每接一个触发器就多一次隐式提交 | 高 |
| **B7-07** | 通知接线的**幂等/重复通知判据**：同一业务事件重复触发不得产生重复通知（按 `trigger_type + related_model + related_id` 去重，或按批次+接收人唯一） | `create_notification` 实测 `:52-129`：`Notification` 构造 `:96-105` → `add/flush` `:107-108` → 接收者 `:111-115` → **无任何查重查询**；模型侧有可用字段实测 `models.py:1908 trigger_type` / `:1919 related_model` / `:1920 related_id`（`:1922-1927` 只有普通索引，**无唯一约束**）⇒ 去重判据**既无实现也无唯一约束** | **未实现** | 现场取行（`:52-129` 无查重 + `models.py:1908/1919/1920/1922-1927`） | 在 `create_notification` 内按 `trigger_type+related_model+related_id`（或批次+接收人）去重；若加唯一约束属 schema 变更 ⇒ 必须**手写迁移 + `_ENSURED_COLUMNS` 登记**（AGENTS.md 禁令） | 高 |
| **计划门禁脚本** | 批次7「验证命令」：`scripts/check_notification_triggers.py`（§3.3 T-A，AST 抓 `def notify_*` → 要求每个触发器 ≥1 调用点，`--expect N`，未接线 = exit 1） | **仓库中不存在**：`scripts/` 下 15 个 .py（`check_db_bootstrap/check_doc_claims/check_migration_heads/check_model_refs/check_properties/check_templates/functional_test/migrate_sqlite_to_postgres/permission_matrix/route_inventory/smoke_test/windows_service/_probe_seed/_sandbox_compat/_test_bootstrap`）**无该文件**；全仓仅 4 处**文档引用**（`docs/开发与测试规划-2026-10-06.md:374/496/640/657`、`docs/test-reports/2026-10/04-…:297`、`…/03-…:261`）。同批 §3.3 T-C 的 `scripts/check_is_archived_policy.py` **亦不存在** | **未实现（门禁缺口）** | 文件清单逐一列举 + 全仓 grep（命中全为文档） | 新增该脚本并纳入门禁链（`ci_gates`），否则「触发器是否接线」永远无自动判据 | 高 |

---

## 5. 阶段C 产品问题 P1–P12 现场复核（`70-` §4 + §10.3）

| # | 今天是否仍存在 | 实测 file:line 与行内容 | 判定 | 备注 |
| --- | --- | --- | --- | --- |
| **P1** | **仍存在（行为级复现）** | `routes.py:5149 db.session.add(product)` → `:5152 log = AuditLog(` … `:5159 target_id=product.id`（**其间无 `flush()`**）；`quality.py:625 db.session.add(task)` → `:628 log = AuditLog(` … `:635 target_id=task.id`（**同形，无 flush**）。对照三处**有** flush：`routes.py:564`（`db.session.flush()`）、`:1734`（`db.session.flush()  # 获取bonus_penalty.id`）、`:4420`（`db.session.flush()  # 获取task.id`）——**计划给的这三个行号今日逐位准确（0 漂移）**，结构性差异确实**只在 flush 时机** | **确认存在**；且**下游后果实测**：新建成品 ⇒ 审计行 `target_id=null / can_rollback=true`；对它回滚 ⇒ **404「目标记录不存在」** | 真库旁证（本次只读复核）：`audit_log` 73 行 / NULL 40 行 / `can_rollback=1 且 NULL` **10 行**（与 `70-` 值逐位相同）；具名例 `id=73 创建质检任务 / InspectionTask / target_id NULL / can_rollback=1` **今日可复现**；10 行明细：`id=7,8,12,15,24,29,40,44,68,73` |
| **P2** | **仍存在** | `routes.py:4945 error_messages.append('第{index+2}行导入失败，请稍后重试或联系管理员')`、`routes.py:5036`（**同字面量，缺 f 前缀**）；对照 `:4028 error_messages.append(f'第 {index + 2} 行：{date_error}')`（**有 f**） | **确认存在**（`literal_brace_bug` 判据仍红） | 行号**未漂移**；修法 = 两处加 `f`（2 字符） |
| **P3** | **仍存在（行为级复现）** | `routes.py:2061-2066`：`:2061 if error_messages:` → `:2062 return jsonify({'success': False, 'message': f'数据验证失败，共发现{len(error_messages)}个错误：…'})`（**早于任何 commit**）；其后 `:2102-2140` 才是行级容错+最终 commit | **确认存在**（违反 AGENTS.md「导入必须行级容错」） | 行为级 H 组：3 好 + 2 坏 ⇒ `success=false`、`employee` 增量 **0**、响应「数据验证失败，共发现2个错误」；行号**未漂移** |
| **P4** | **仍存在（行为级复现，两个场景都红）** | 场景 S4：`routes.py:4000 try:` → `:4003 file.save(temp_path)` → `:4005 task_data = ExcelGenerator.parse_task_data(temp_path)` → **`:4006 os.remove(temp_path)`（在 try 内）**；异常出口 `:4066-4067 except Exception as e: return jsonify(...)`（**无 `finally`、无删除**）。场景 S5：`routes.py:2171-2176`：`:2171 except Exception as e:` → `:2172-2176 if temp_path and os.path.exists(temp_path): try: os.remove(temp_path) except OSError: pass` ⇒ **清理只在 except 分支**，而早退 `:2062` 与成功返回 `:2166` 都不经 `except`；`@bp.before_request` 钩子阈值实测 `:2194 if current_time - file_time > 300:`（**救不了当次文件**） | **确认存在** | 行为级 H 组两场景 `residue_exists=true`：残留 `t3_xxxxgood_bad.xlsx`（早退路径）与 `t3_xxxxbroken.xlsx`（解析失败路径）；**注意**：本次实测把 `TEMP_FOLDER` 改指副本临时目录，**未污染仓库 `uploads/temp`** |
| **P5** | **仍存在** | `routes.py:4016 error_messages.append(f"员工工号 {data['employee_id']} 不存在")`（**无「第 N 行」**）、`:4022 error_messages.append(f"工序编号 {data['process_code']} 不存在")`（**无**）；对照 `:4028 f'第 {index + 2} 行：{date_error}'`（**有**）与 `:2058 f'第{i+1}行数据错误：{…}'`（**有**） | **确认存在**（`row_number_all_ok=false`） | 四行行号**全部未漂移** |
| **P6** | **仍存在** | 载体端点实测 `routes.py:3285-3288`（`@bp.route('/tasks/<int:id>/update_status')` → `def update_task_status(id)`），函数体内**7 处**「记日志后继续」的内层 try/except：`:3474-3476`（自动创建质检任务）、`:3527-3528`（报工扣料回写）、`:3555-3556`（替用分析）、`:3607-3608`（替用通知）、`:3659-3661`（批次状态同步）、`:3684-3685`（生产中心状态同步）、`:3750-3751`（末道入库）；外层出口 `:3755-3759 except Exception as e: _reraise_http(e); db.session.rollback(); …` | **确认存在**（≥4 处 ⇒ 可形成「部分应用」事务；响应码不反映原子性） | 计划只给「由 `r2_c02_probe.py` 的 damage 向量实测（探针 artifact 内具名）」，本次给出**逐处行号**：共 7 处，含 `except: logger.warning` 两处（`:3555`/`:3684`） |
| **P7** | **仍存在** | 实现侧：`quality.py:837-839`：`:838 if template.type != task.target_type:` → `:839 return jsonify({'success': False, 'message': '质检模板类型与任务类型不匹配'}), 400`；界面侧：`templates/main/quality/templates.html:103-107` 模板类型下拉仅 `production_record` / `product` / `material`（**无 `goods_receipt`**）；质检任务取模板实测 `templates/main/quality/tasks.html:964 get_templates）？type= + encodeURIComponent(taskType)`（`taskType` = `goods_receipt` ⇒ 查不到模板）；文档侧：`docs/test-reports/2026-10/04-…md:75`（A4）要求「启用的 **`type='material'`** 质检模板」 | **确认存在**（文档口径 ↔ 实现口径 ↔ 界面可选项**三方冲突**） | 按 `70-` §10.3⑦：**二选一**（改文档为 `goods_receipt`，或实现接受 `material`）**并**给界面补 `goods_receipt` 选项 |
| **P8** | **仍存在（文档口径问题，非代码缺陷）** | `docs/test-reports/2026-10/04-…md:88`（B2 行）字面：「`production_batches` +1、`production_batch_items` +n（产品编码生成）、`task_assignment` +「**工序数×n**」」；`70-` §4-P8 登记 V-12 实测 `V12-B2.3：task_delta=3 / process_count=3 / batch_item_delta=2`（字面期望 6） | **确认存在**（口径过时；实现为「每工序一张」） | `docs/` 树不可覆写 ⇒ 只能**新建订正件**（`70-` §10.4 已列） |
| **P9** | **仍存在（行为级复现）** | `mes_service.py:1121-1131`：`:1125 if wp:` → `:1127 inbound_workpiece(wp, stock_kind='scrap', …)`；`:1138 item.status = 'scrapped'`（状态已置，但**台账行只在 `wp` 非空时写**）；报工路径 NC 的 `workpiece_id` 为 NULL（`mes_service.py:632 workpiece_id=None`） | **确认存在** | 行为级 F 组：报废处置前后 `finished_product(stock_kind='scrap')` 行数 **Δ=0**（`70-` 的 `scrap_rows_delta=0` 复现）；同时 `bi.status='scrapped'` ⇒ 门禁仍拒（终态口径正确，缺的只是台账行） |
| **P10** | **仍存在**（两子项均确认） | ① `routes.py:2733 notes=data['notes']`（`ProductionRecord(...)` 实参）↔ `app/utils/excel_generator.py:336-341`：`:336 data.append({` / `:337 'date'` / `:338 'employee_id'` / `:339 'process_code'` / `:340 'quantity'`（**无 `notes` 键**）⇒ 每行 `KeyError: 'notes'` → `:2738-2739 except Exception as e: error_messages.append(f"处理记录时出错: {str(e)}")` ⇒ **0 条入库**。② 取价三处：`routes.py:2717-2720 ProcessPrice.query.filter(ProcessPrice.process_code == …, ProcessPrice.effective_date <= …).order_by(ProcessPrice.effective_date.desc()).first()` ↔ `routes.py:3902 process = ProcessPrice.query.filter_by(process_code=data['process_code']).first()` ↔ `routes.py:4020 process = ProcessPrice.query.filter_by(process_code=data['process_code']).first()`（**后两处不看 `effective_date`**） | **确认存在**（① `notes` KeyError；② 三处取价口径不一致） | 全部行号**未漂移**（与 `70-` §4-P10 载体一致）；修法：解析器补 `notes` 键 + 统一取价口径（建议抽 `pick_process_price(code, date)` 单点） |
| **P11** | **已消失**（原载体不存在）；但**同族新残留存在** | ① 仓库根 `.tmp_v15_*`：`Get-ChildItem -Force -File \| Where-Object { $_.Name -like '.tmp_v15*' }` = **0 个**（原 6 个 `.{out,err}` 已清理）。② **今日新观察**：仓库根存在 `_probe_tmp/gate-baseline.txt`（**24704 B**），`git status --porcelain` 显示为 `?? _probe_tmp/`（未跟踪）；另有 `scripts/_probe_seed.py` 同在 `scripts/` 内（非门禁表列名） | **P11 原条已消除**；`_probe_tmp/` 属**同族新残留**（建议归 `40` §2 运行时目录纪律） | 本次未删除（只读纪律 + 可能是其他成员在途产物）⇒ **只登记，交由 captain 处置** |
| **P12** | **仍存在**（两处下游资产仍指向无参调用） | ① `test-reports-2026-10/harness/reconcile_r2.py:555`：`chk_subprocess([PY, '-B', 'test-reports-2026-10/harness/coverage_drift.py'], '漂移判据 exit 0')]`，而 `chk_subprocess` 实测 `:262 def chk_subprocess(argv, label=None, expect_exit=0, …)`、`:274 ok = None if code is None else (code == expect_exit)` ⇒ **无参 + 断言 exit 0**。② `test-reports-2026-10/harness/r2_v14_ledgerbook.py:257-262`：`'command': (… '%s -B test-reports-2026-10/harness/coverage_drift.py；' …)`、`:262 'exit_code': 0` | **确认存在**（两处都会因 N-1 的修而变红/变陈旧） | **本次实跑复核**：`coverage_drift.py` **无参 ⇒ exit 2**（stdout 明写「[USAGE] exit 2 = 未提供产物（用法错误），不是覆盖退化 / 不是回归」）；`--coverage .tmp\r2-exec-b5-v14\coverage.json` ⇒ 按 `70-` §5.2 为 exit 0（本次未复跑该命令，属**转述**，标注为未复核）；⇒ 修法 = 两处重指 `--coverage <run 产物>` |

**P 条计数**：**仍存在 = 11 条**（P1、P2、P3、P4、P5、P6、P7、P8、P9、P10、P12 —— 其中 P8 为文档口径、P12 为测试资产口径，二者**非产品代码缺陷**）；
**已消失 = 1 条**（P11 原载体 `.tmp_v15_*`；同族新残留 `_probe_tmp/` 已登记）。若按 `70-` §10.3 的「10 条产品面」口径（P1–P10）：**10 条全部仍需处置**。

---

## 6. 剩余工作清单（供后续「开发与测试规划」直接消费）

### 6.1 未实现 / 部分实现（按建议批次聚合）

| 优先级 | 条目 | 落点（实测行号） | 备注 |
| --- | --- | --- | --- |
| **P0（阻断闭环）** | **B4-07 事务缝** | `quality.py:978`（commit）→ `:981`（落地）→ `:990`（commit） | 「结论已提交、NC/门禁未落地」可复现；建议改为同事务（`:981` 前移或 `:978` 只 flush） |
| **P0** | **B4-08 双链对拍脚本** | 新增脚本（`scripts/` 或 `harness/`）+ 门禁登记 | 判据：两条链 `fg` **件数合计**相等（禁行数） |
| **P1** | **批次6 全部（B6-01…B6-06）** | `templates/main/stock/nonconformities.html`（33 行，`:12/:13/:14/:17-23`）、`stock.py:119-124`、`quality.py:1271-1329` | 后端侧改动小（筛选参数、详情键、动作集校验）；前端改动集中在一个模板 |
| **P1** | **批次7 B7-01…B7-04 + B7-07 + 门禁脚本** | `notification_service.py:52/430/457/484/506`、`routes.py:4252-4273`、新增 `scripts/check_notification_triggers.py` | **先**给 `create_notification` 加 `commit=False`（B7-06）**再**接线 |
| **P1** | **B7-05 降级登记** | `routes.py:4232`/`:4255`（`log.old_data.items()`） | 按 t6 §3④：`old_data` 不含扣料/子行 ⇒ **登记为「明确 400 + 原因」**，不得承诺守恒；同时修 `old_data is None` |
| **P2** | **B4-04 / B4-05(报废台账) / P9** | `nonconformities.html:14`、`mes_service.py:1121-1143` | 三处同源：production_record 路径「看得见 + 报得出 + 有台账」 |
| **P2** | **B5-03 工资明细区分返工** | `mes_service.py:1812`（复用 `piecework_breakdown`）+ `salary_calculation.html:88-120` | 后端已就绪，成本极低 |
| **P2** | **P1 / P2 / P3 / P4 / P5 / P10** | `routes.py:5152`、`quality.py:628`（+2 处 flush）；`routes.py:4945/5036`（加 `f`）；`routes.py:2061-2066`；`routes.py:4000-4006`/`:2171-2176`；`routes.py:4016/4022`；`app/utils/excel_generator.py:336-341` + `routes.py:2717-2720/3902/4020` | 均为**小改动**；建议打包成一个「阶段C 产品面」批次 |
| **P3** | **P7 / P8（口径二选一 + 文档订正）** | `quality.py:838`、`templates/main/quality/templates.html:103-107`、`docs/test-reports/2026-10/04-…md:75/88` | `docs/` 不可覆写 ⇒ 新建订正件 |
| **P3** | **P12（测试资产重指）** | `harness/reconcile_r2.py:555`、`harness/r2_v14_ledgerbook.py:257-262` | 加 `--coverage <run 产物>` |
| **P3** | **P11 同族新残留 `_probe_tmp/`** | 仓库根 | 只登记，未处置（可能是他人在途产物） |
| **登记** | B4-02 的口径边界；B5-02 的 R3 不参与判定；B4-06 = 计划内不做 | 见 §1/§2 各行「剩余工作」 | 防下一轮误判为遗漏 |

### 6.2 必须补的**测试**（计划 §3.3 的盲区脚本，实测缺失）

| 计划代号 | 计划脚本 | 实测是否存在 | 判据 |
| --- | --- | --- | --- |
| T-A | `scripts/check_notification_triggers.py` | **不存在** | 每个 `notify_*` ≥1 个非定义处调用点；未接线 exit 1 |
| T-B | （双差分 + 阴性对照） | **无独立脚本**（`harness/w2w3_probe.py` 内含同类格，46/46） | `false/true` 工资数字不同；非返工两态相同；带开关白名单 |
| T-C | `scripts/check_is_archived_policy.py` | **不存在** | `is_archived` 谓词统一 + 可见性反转 |
| T-F | 件数守恒对拍 | **不存在**（仅单链格） | 两条生产链件数合计相等；`pass` 场景 0 变化 |

---

## 7. 与计划文本的冲突/需回填项（不改变实测结论，只标出规划文本需更正处）

1. **批次5 的 F1 修法与实测口径不同**：计划写 `notes.like('返工 不合格单#%')`，实测为 **R1 `rework_task_id` → R2 `global_sn`**（`07b` DEC-2 §2.2 明确否决 notes 前缀单判与 `task_type` 单判）。规划文本应按实测回填。
2. **批次4 抬头顺序**（B4-01→B4-03→B4-02）：代码侧**三条都已落地**，顺序约束**已满足**；但 §0.2-J 证明「门禁在报工路径上只能靠 `quality_status`」⇒ 该顺序约束在**验收**上仍是硬约束（不得先验门禁后验回写）。
3. **B4-02 的「有在办单据」拒绝路径在报工链不可达**（结构性）：报工路径不传 `production_record`（`routes.py:3712-3717`），而报工记录不写 notes（`routes.py:3399-3405`）⇒ `batch_item_production_records`（`mes_service.py:148-154`）恒空。若业务要求「报工产出有未完成质检任务也拦」，须先拍板补传 `production_record`（**属口径变更**）。
4. **B7-05 按 t6 §3④ 应降级**：实测 `old_data` 不含扣料/子行信息（真库 `materials/raw_material/consumed` 命中 **0**）⇒ 计划里「回滚守恒」在既有数据上**不可实现**，应改为「明确 400 + 原因」并登记边界。
5. **批次7 验证命令不存在**：`scripts/check_notification_triggers.py` 与 `scripts/check_is_archived_policy.py` 均为**计划文本独有**，仓库无实现。
6. **`04-业务验收标准与端到端判据.md` 的 A4 口径**（`:75` 写 `type='material'`）与实现（`quality.py:838` 要求 `template.type == 'goods_receipt'`）冲突 —— 与 P7 同源。

---

## 8. 自检与边界（**我没有做什么**）

1. **只读**：未修改任何既有文件（`app/`、`app/templates/`、`scripts/`、`docs/` 全只读）；新增仅 §0 声明的 3 个文件。
2. **真实库零写入**：`app.db` SHA256 与 mtime 复核前后一致（`F5DA2306…0E0F065` / `2026-09-18 12:50:55`）；所有 DB 写入发生在 `make_app()` 的临时副本（探针输出记录 `copy_path`）。
3. **未跑 `flask db migrate/stamp`**，未跑任何请求型门禁脚本（`smoke_test`/`permission_matrix`/`functional_test`/`w2w3_probe` 均**未复跑**，只读其历史产物）。
4. **上传残留未被制造到仓库**：实测期间 `uploads/temp` 文件数 **0**（`TEMP_FOLDER` 已改指副本目录）。
5. **未复核项（明确标注为转述，不作证据）**：
   - `coverage_drift.py --coverage .tmp\r2-exec-b5-v14\coverage.json ⇒ exit 0`（`70-` §5.2 ②，本次未复跑）；
   - `w2w3_probe.py` 各格（N3/N4/A1/A2/AC-29-b/-d）的**逐格读数**——本次只读其 `w2w3-criteria.json` 的汇总（46/46）与文档引用；
   - **B4-07 的故障注入**（未人为触发第二个 commit 失败）⇒ B4-07 判「存在两段提交缝」是**取行级确定**，「中间态可否被外部触发」标注为**中高置信**；
   - `P6` 的**注入复现**（未重跑 `r2_c02_probe.py` 的 damage 向量）⇒ 结论来自**取行 + 历史探针自述**。
6. **未做判断的**：`_probe_tmp/`、`scripts/_probe_seed.py` 的归属与去留（只登记，交 captain）。

---

## 9. 证据索引（可复跑）

```powershell
$env:PYTHONIOENCODING='utf-8'
$py = 'F:\Miniconda\envs\wage\python.exe'
# ① 本报告的行为级读数（副本库 + 真实端点；不写真实库、不污染仓库 uploads/temp）
& $py -B test-reports-2026-10/reconcile-2026-10-08/probe_backend_field.py      # 机读件：probe_backend_field.output.json
# ② 真实库不变量（期望 2531328 / F5DA2306…0E0F065 / 2026-09-18 12:50:55）
(Get-FileHash app.db -Algorithm SHA256).Hash ; (Get-Item app.db).Length ; (Get-Item app.db).LastWriteTime
# ③ P12 的行为（期望 exit 2）
& $py -B test-reports-2026-10/harness/coverage_drift.py    # 无参 ⇒ exit 2
# ④ P11（期望 0 个）
Get-ChildItem -Force -File | Where-Object { $_.Name -like '.tmp_v15*' }
# ⑤ P1 的真库旁证（只读 URI）
$code = @'
import sqlite3; con = sqlite3.connect('file:app.db?mode=ro', uri=True); c = con.cursor()
c.execute('select count(*) from audit_log'); print('total', c.fetchone()[0])
c.execute('select count(*) from audit_log where target_id is null'); print('null', c.fetchone()[0])
c.execute('select count(*) from audit_log where can_rollback=1 and target_id is null'); print('null+can_rollback', c.fetchone()[0])
c.execute("select count(*) from audit_log where old_data like '%materials%' or old_data like '%raw_material%' or old_data like '%consumed%'"); print('old_data-with-consumption', c.fetchone()[0])
'@
$code | & $py -B -
```

**本报告引用的其它证据文件（既有，只读）**

| 文件 | 用途 |
| --- | --- |
| `docs/开发与测试规划-2026-10-06.md` §1 批次4/5/6/7、§3.3 T-A/T-B/T-C/T-F | 计划要求与判据原文本 |
| `test-reports-2026-10/70-第2轮收口与阶段C移交.md` §4 / §10.3 | P1–P12 载体与阶段C判据 |
| `test-reports-2026-10/60-第2轮改进报告（定稿）.md` §4.2/§4.3/§6-N-2 | C-01 审计面、C-08 三缺口、N-2 |
| `test-reports-2026-10/07b-DEC-1-DEC-2-业务口径决策单.md` §1.2–§1.7 / §2.2–§2.5 | 实测实现所依据的四值语义、门禁顺序、R1/R2、扣料取值链 |
| `test-reports-2026-10/33-剩余项业务验收判据.md` §F-11 | AC-15/AC-16 的既有载体 |
| `test-reports-2026-10/evidence/harness/w2w3-t7-final/w2w3-criteria.json` | W2/W3 判据 46/46（本次只读复核） |
| `docs/test-reports/2026-10/04-业务验收标准与端到端判据.md:75/88/297` | P7/P8 的文档侧载体 |
| `test-reports-2026-10/reconcile-2026-10-08/probe_backend_field.py` / `.output.json` | 本次现场复核探针与机读读数（新增） |
