# 独立复核（非作者）· `80-` 对账总表 与 `81-` 后续规划的事实一致性、可复算性与可执行性

| 项 | 值 |
| --- | --- |
| 交付物 | `test-reports-2026-10/reconcile-2026-10-08/recon-verification.md`（**新建**；本任务是「被取消的 t10」的重启件 `t14`） |
| 复核身份 | **独立复核员2（非作者）**｜attempt `031ad69d-2dee-4ad5-9c19-bab548ebfd03`｜立场：**对抗式**（默认「作者可能写宽了」，不能现场复现的判定一律不接受） |
| 时点 | 2026-10-08（本机本地时间；复核区间约 01:26 → 01:40） |
| 工作目录 / 解释器 | `D:\workspace\wage_management_system - bak`｜`F:\Miniconda\envs\wage\python.exe`（3.9.21，`PYTHONIOENCODING=utf-8`） |
| 被复核对象（只读） | `test-reports-2026-10/80-开发与需求文档-实际进度逐条对账.md`（t12）｜`test-reports-2026-10/81-后续开发与测试规划.md`（t13）｜`reconcile-2026-10-08/` 8 份领域稿（含 `recon-arbitration.md`） |
| 被核对象版本（**重要**） | `81-` = **103,855 B / 832 行**（mtime 2026-10-08 01:30:35，复核全程未变）；`80-` = **复核期间被追加过**：开始时 126,981 B / 544 行，01:33:05 变为 **131,911 B / 577 行**（由**任务 `t15`** 追加 §0.5 取代声明，纯插入 33 行，正文其余部分未改）。**本报告的 80- 行号一律按 131,911 B/577 行的当前版本**给出，并已在 §0.4 记录该变更 |
| 只读声明 | **未修改任何既有文件**（`app/`、`app/templates/`、`scripts/`、`migrations/`、`docs/`、`AGENTS.md`、`80-`、`81-`、`reconcile-2026-10-08/` 既有 8 份稿全部只读）；本次唯一新增 = 本文件。`git status --porcelain --untracked-files=no` = **0 行** |
| 真实库不变量（开工/收尾两次同值） | `app.db` = **2531328 B** / SHA256 = `F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065` / mtime **2026-09-18 12:50:55** |
| git HEAD | `534ce70b204c767feee551e8fd04e538374b1de8` |

---

## 0. 复核口径

### 0.1 本次复核只接受“可现场复现”的证据

1. **不引用文档转述**：`80-`/`81-` 中凡来自 `recon-*.md` 的行为读数（`nc_rows_delta=+1`、`Δ=100.0`、`scrap_rows_delta=0` 等），本次**一律不作为我判断的依据**；我改为独立取行（`file:line`）+ 独立实跑（静态门禁/只读库查询）来确定**载体是否在位**，并显式区分「载体一致」与「行为已被我复跑」。
2. **抽查类型**：`文件存在 ≠ 已实现`；「计划要求改的文档改了没有」；「blocked 是否被折算成 pass」；「inScope 路径是否存在」；「验收是否可判定」。
3. **行号口径**：`80-`/`81-` 引用的是**当前工作区源码**行号；我逐条按当前源码复算，凡与文档不符即登记。

### 0.2 本次实跑命令（真实 exit code，不经管道；详见 §7）

`check_templates` / `check_migration_heads` / `check_properties` / `check_model_refs` / `route_inventory` / `check_db_bootstrap` / `ci_gates --list` / `coverage_drift`（无参）/ `check_doc_claims --selftest` / `check_doc_claims --list-constants` / `check_properties --selftest`

### 0.3 只读的库查询

用 `sqlite3` 以 `file:app.db?mode=ro`（`uri=True`）只读连接真库，**未执行任何写语句**；复核前后 `app.db` 三值逐位一致（见 §8）。

### 0.4 复核期间被核对象的变更（必须披露；影响一条早期疑点的存废）

本次复核开始后，`80-` 于 **01:33:05** 由任务 `t15` 追加了 §0.5「取代声明」（`80-:63-90`）。该声明：
- 明确把 `80-` §1.1 的 5 值分布 `12/7/54/6/3` **原值保留**、并给出**取代后唯一有效口径 `11/5/57/6/3`**（含逐条改判 `B8-07`→部分、`B7-06`/`B8-05`/`B8-12`→未实现，及计数自洽校验 `11+5+57+6+3=82`）；
- 我独立复核该自洽校验：`12−1=11`、`7−3+1=5`、`54+4=57`、`11+5+57+6+3=82` ✓，且与 `81-` §1.1 逐值一致 ✓，与 `recon-arbitration.md:97-107`（A-7/A-8）一致 ✓。
⇒ 我在复核早期登记的「`80-` 未回填、同一事实两套起点数字」这一疑点在**当前版本已消除**，故**不作为 finding**，仅在此留痕。

---

## 1. 一页结论

### 1.1 总体 verdict：**needs_revision**（不接受为 pass；但不构成 reject）

| 维度 | 结论 |
| --- | --- |
| `80-` 事实底盘 | **高度可靠**。抽查 **49 条**判定（覆盖批次3/4/5/6/7/8/9/10/11 + 阶段C §10.1/§10.2/§10.3/§10.7/§10.8）中 **46 条一致、3 条需订正**（#12 `B4-08` 措辞过宽 → **F-4 低**；#36 `B10-11` 的 grep 断言 → **F-5 低**；#49 `AGENTS.md` 「硬错」定性 → **F-1 高**）；无「file_exists 当已实现」硬性违规、无「blocked 折算 pass」违规 |
| `81-` 事实承继 | 起点口径（11/5/57）与仲裁件 `A-6…A-13` 逐条可核、与 `80-` §0.5 **已对齐**；`blocked`（A-63 第二步 / C-07）**原样登记、未折算**；7 批 65 条新编号与来源映射自洽（5+9+8+8+8+19+8=65 ✓） |
| `81-` 可执行性 | **4 处缺陷**：① inScope 路径 `app/templates/main/advanced_search.html` **不存在**（真实在 `main/search/`）；② 批次16 inScope **漏** `production_center*.html`，而 B16-02 要求改其中 3 处 fetch 站点 ⇒ inScope 不闭合；③ 批次13 B13-02 的验收（真库存量 10→0）与 §5.2 DoD 第 3/4 条（真实库零改动）**互相冲突**；④ 批次18 inScope 的 harness 白名单**不含** B18-08 实际要改的 `api_matrix.py`/`final_recount.py`/`ci_gates.py` 👉 **这 4 处会让执行者在批内无法满足 DoD** |
| 最高价值单条 finding | **F-1（高）**：`80-:412` 把 `AGENTS.md:87` 的「`3=入口缺失`」定为**硬错**并称「全仓『入口缺失』0 命中」——实测 **`Jenkinsfile:104 exit /b 3` + `:110 if (ciRc == 3)`** 表明 exit 3 是 CI 封装层的真实出口，该表述**不是硬错**；而 `81-:428/:444` 的 B18-02 却要求 `AGENTS.md`「退出码语义只留 0/1/2」⇒ **会删掉一条正确表述** |

### 1.2 抽查总览（**49 条**，逐条见 §2）

| 批次/节 | 抽查条数 | 一致 | 需订正 |
| --- | --- | --- | --- |
| 批次3（#1–#5） | 5 | 5 | 0 |
| 批次4（#6–#12） | 7 | 6 | 1（#12 → F-4） |
| 批次5（#13–#17） | 5 | 5 | 0 |
| 批次6（#18–#21） | 4 | 4 | 0 |
| 批次7（#22–#27） | 6 | 6 | 0 |
| 批次8（#28–#31） | 4 | 4 | 0 |
| 批次9（#32–#34、#38） | 4 | 4 | 0 |
| 批次10（#35–#36） | 2 | 1 | 1（#36 → F-5） |
| 批次11（#37） | 1 | 1 | 0 |
| 阶段C（#39–#49） | 11 | 10 | 1（#49 → F-1） |
| **合计** | **49** | **46** | **3** |

---

## 2. `80-` 判定条目抽查（**49 条**，逐条给实测 `file:line`/命令读数）

> 格式：**编号｜文档写的状态｜我的独立复算证据（本次实测）｜是否一致**。
> `[跑]` = 本次真实执行；`[读]` = 本次读源码取行；`[库]` = 本次只读连真库。

### 批次3 —— 测试资产与工程纪律

| # | 条目 | 文档状态 | 独立复算证据 | 一致? |
| --- | --- | --- | --- | --- |
| 1 | **B3-01** 请求型脚本 `--no-dump`/退出码与落盘解耦 | 已实现 | `[读]` `scripts/smoke_test.py:90 def default_out()`、`:115 '[WARN] 落盘失败（不影响退出码）'`、`:246` no-dump 提示、`:266 --no-dump`；`scripts/permission_matrix.py:127` 同款 `[WARN]`、`:376 code = 1 if (anon_open or face_failures) else 0`。**未复跑请求型脚本（纪律）** ⇒ 判「源码级一致」 | ✅ 一致（源码级） |
| 2 | **B3-02** `git rm` 1 字节死文件 | 未实现 | `[读]` `(Get-Item app/main/sales_routes.py).Length` = **1**；`git ls-files app/main` = **10 个文件且含 `sales_routes.py`**；AST `@bp.route` = **0** | ✅ 一致 |
| 3 | **B3-03** `flask db *` 前置校验缺失 | 未实现 | `[读]` `Test-Path scripts/check_db_url_guard.py` = **False**；`app/__init__.py:103 _ensure_schema`、`:107 db.create_all()`、`:224` 调用点，`:156-224` 无任何 URI 闸 | ✅ 一致 |
| 4 | **B3-05** 内联 role 白名单断言缺失（有探测无断言） | 未实现 | `[读]` `scripts/permission_matrix.py:156-157` 仅 `kinds.append('inline_role_check')`；`:376` 退出码只由 `anon_open`/`face_failures` 决定。**白名单独立复算 = Python 15 处**（`routes.py:337/340/350/654/5983` + `quality.py:46/82/104/120/529/822/911/1217/1277/1347`；另 `permissions.py:7` 为 docstring ⇒ 文本命中 16 行）+ **模板 2 处**（`tasks.html:340`、`task_detail.html:13`） | ✅ 一致（15+2 逐行相符） |
| 5 | **B3-06** 31 表 / 无条件 `create_table` 对拍脚本缺失 | 未实现 | `[读]` `scripts/` 15 个 `.py` + `harness/` 无对拍脚本；**独立复算**：迁移文件 **35**；含 `create_table` **14**（AST）；有存在性守卫 **3**（`b1a01_*.py`、`da_add_process_assignment_tables.py`、`p0p2messtables_*.py`，口径 = `sa.inspect()/has_table/get_table_names`）⇒ **无守卫 11** ✅；`c02604883c72` = **24 处** ✅；字面表名（除 `p0p2messtables`）= **49** ✅ | ✅ 一致 |

> 备注（自查纠错）：我第一遍用「文件文本是否含 `has_table` 字符串」粗测得「无守卫 13」，与 `80-` 的 11 不符；改用 AST + `sa.inspect()/has_table/get_table_names` 口径后为 **11**（13 的差来自把 `c02604883c72` 的 `inspector` **列名**误判为守卫）⇒ **`80-` 该值是准确的**。

### 批次4 —— 质检闭合

| # | 条目 | 文档状态 | 独立复算证据 | 一致? |
| --- | --- | --- | --- | --- |
| 6 | **B4-01** `production_record` 路径不再早退、fail 建 NC | 已实现 | `[读]` `mes_service.py:736 def apply_inspection_result`；`:753-756` goods_receipt 分支 return；**`:757-761` production_record 分支 return（位于 `:763 if workpiece is None` 之前）**；NC 构造 `:624-636`（`:632 workpiece_id=None`、`:633 target_type='production_record'`、`:634 target_id=production_record.id`、`:636 db.session.flush()`） | ✅ 一致（结构级在位；行为 Δ 未复跑） |
| 7 | **B4-02** fail 后门禁生效 | 已实现 | `[读]` `mes_service.py:157 def qc_gate_allows_output(..., production_record=None)`；`:196-207`（`:199-200` fail/failed/rejected 拒；`:201-202` scrapped 拒；`:203-207` pending 且在办拒）；`:209-210` 有未完成质检任务拒；`:211-212` 有未闭环 NC 拒；报工链调用 `:351` | ✅ 一致 |
| 8 | **B4-03** 自动回写 `quality_status` | 已实现 | `[读]` `mes_service.py:553 def recompute_production_quality_status`；`:596-597` 写字段；`:640`/`:667` 两个调用点；人工通道 `routes.py:8926-8927` | ✅ 一致（指针级） |
| 9 | **B4-04** 列表能查到报工路径 NC、但看不出目标 | 部分实现 | `[读]` `stock.py:123 NonconformityRecord.query…limit(200).all()`、`:124 render_template`；`nonconformities.html:14` 只认 `nc.workpiece_id` | ✅ 一致 |
| 10 | **B4-05** 处置可用；报废台账仅工件路径 | 部分实现 | `[读]` `mes_service.py:1069-1090`（返工：`:1073-1084` 工序/员工缺省链、`:1085-1086 rework_quantity_for`、`:1088 task_notes`）、`:1105 nc.rework_task_id`、`:1117 nc.status='done'`；报废 `:1121-1143`，**`:1125 if wp:` 是唯一台账入口** | ✅ 一致 |
| 11 | **B4-07** 结论落地存在两段提交缝 | 未实现 | `[读]` `quality.py:978 db.session.commit()` → `:981 mes_service.apply_inspection_result(record)` → `:990 db.session.commit()`；异常出口 `:997-1002`（`_reraise_http` + `rollback` + 500） | ✅ 一致 |
| 12 | **B4-08** 双链件数对拍脚本 | 未实现 | `[读]` `scripts/`+`harness/` 无 `chain_count_consistency` 类脚本；报工 `routes.py:3712-3717 quantity=task.quantity`；工件 `mes_service.py:225 inbound_workpiece(..., quantity=1)`。**但「harness 内无任何件数守恒脚本」这一绝对表述不成立**：`harness/uat_chains.py:403` 有 `check('P0-1.9','件数守恒：fail 未产生 failed 库/报废库台账行（对照 AC-17）')`，`:913` 亦有「件数守恒」判据 ⇒ **方向一致、措辞需收窄（F-4）** | ⚠ 一致（措辞过宽） |

### 批次5 —— 假开关接线与工资/料账

| # | 条目 | 文档状态 | 独立复算证据 | 一致? |
| --- | --- | --- | --- | --- |
| 13 | **B5-01** 返工计件开关行为级生效 | 已实现 | `[读]` `mes_service.py:1761-1766 def rework_counts_piecework()`（`:1763 SystemConfig.get('quality.rework_counts_piecework', False)`、`:1765 '1/true/yes/on'` 兜底）；使用点 `:1815`；**4 个计算点独立复算**：`routes.py:1822 piecework_amount(...)`、`models.py:154 piecework_amount(...)`、`routes.py:400`、`routes.py:409` | ✅ 一致（指针级；`Δ=100.0` 行为读数属 t6 探针，本次未复跑） |
| 14 | **B5-03** 工资明细不可区分返工 | 未实现 | `[读]` 全仓 `piecework_breakdown` = **2 命中**：`:1812 def` + `:1833`（`piecework_amount` 内部）⇒ **零消费方**；`routes.py` 三处只取标量 | ✅ 一致 |
| 15 | **B5-04** 报废扣料按实际消耗（无 `quantity - 1`） | 已实现 | `[读]` `mes_service.py:673-700 def scrap_material_plan`（`:683-690` 明细合并、`:691-692` 兜底、`:693-699` 空清单 + warning）；`:703-733 def deduct_scrap_materials`（`:722 requested=per_piece*pieces`、`:724-729` 夹紧 + warning）；全仓 `quantity - 1` 已 0 命中 | ✅ 一致 |
| 16 | **B5-05** 返工件数不再固定 1 | 已实现 | `[读]` `mes_service.py:1007-1026 def rework_quantity_for`（`:1012-1019` 显式入参 ≤0/非整数 ⇒ `ValueError`；`:1022-1025` 来源记录；`:1026` 兜底留痕文案） | ✅ 一致 |
| 17 | **B5-06** `scrap_cost` 仅登记 | 已实现 | `[读]` `mes_service.py:1123 nc.scrap_cost = scrap_cost or 0`；`models.py:944 scrap_cost = db.Column(db.Float, default=0)`；`app/__init__.py:77 ('scrap_cost','FLOAT')`；无成本台账表 | ✅ 一致 |

### 批次6 —— 不合格处置可用性

| # | 条目 | 文档状态 | 独立复算证据 | 一致? |
| --- | --- | --- | --- | --- |
| 18 | **B6-01** 类型/状态未中文 | 未实现 | `[读]` `nonconformities.html` **33 行**：`:12 {{ nc.type }}`、`:13 {{ nc.status }}`、**`:15 {{ nc.handling_result }}`**（英文枚举直渲） | ✅ 一致 |
| 19 | **B6-02** 无到货单/采购单跳转 | 未实现 | `[读]` `:14` 仅 `{% if nc.workpiece_id %}`，else 显示 `-` | ✅ 一致 |
| 20 | **B6-03** 返工不能选工序/员工、静默指派 | 未实现 | `[读]` `:17-23` 表单仅 `csrf_token` + 3 个 `name="action"` 按钮（无 `rework_process_id`/`employee_id`/`rework_quantity`/`scrap_quantity`）；服务端静默链 `mes_service.py:1081-1084 Employee.query.filter_by(user_id=…).first() or Employee.query.first()` | ✅ 一致 |
| 21 | **B6-04** 不适用动作仍给按钮 | 未实现 | `[读]` `:17 {% if nc.status in ('open','pending_approval') %}` 全量三按钮；`mes_service.py:946-947 raise ValueError('来料检不合格仅支持退货/让步接收/报废处置')` → `stock.py:110-112` 400 | ✅ 一致 |

### 批次7 —— 通知与审计回滚

| # | 条目 | 文档状态 | 独立复算证据 | 一致? |
| --- | --- | --- | --- | --- |
| 22 | **B7-01/02/03** 三触发器零调用点 | 未实现 | `[读]` 定义 5 个：`notification_service.py:430 notify_process_change`、`:457 notify_spec_change`、`:484 notify_inventory_warning`、`:506 notify_task_assignment`、`:528 notify_raw_substitution`；**全仓非定义调用点 = 1**（`routes.py:3601 notify_raw_substitution(`）⇒ 四条零调用 | ✅ 一致（逐字相符） |
| 23 | **B7-04** 回滚 delete 分支无级联 | 未实现 | `[读]` 端点 `routes.py:4192-4195`（`@bp.route('/audit_logs/rollback/<int:log_id>')` + `@require_capability('audit.rollback')`）、delete 分支 `:4252-4273`（`:4261 db.session.add(new_record)`，无子行恢复） | ✅ 一致 |
| 24 | **B7-05** `old_data` NULL ⇒ 500；守恒不可实现 | 未实现 | `[读]` `routes.py:4232` 与 `:4255` 均 `for key, value in log.old_data.items():`（无 None 判断）；兜底 `:4278-4282` ⇒ 500。`[库]` `audit_log` 73 行 / `old_data IS NULL` **61** / `rollback_type='edit' 且 NULL` 分支存在 | ✅ 一致 |
| 25 | **B7-06** 隐式 commit 未落地 | 部分实现（A-8 改判**未实现**） | `[读]` `notification_service.py:107 add` → `:108 flush()` → `:121 db.session.commit()`（函数内部自带提交）；`:126-129` rollback + raise | ✅ 一致（A-8 改判正确：净增 0 不是完成证据） |
| 26 | **B7-07** 无去重 | 未实现 | `[读]` `notification_service.py` 全文 `filter_by(trigger_type` = **0**、无查重查询；`models.py:1922-1927` 仅 4 条普通索引/唯一约束（`uq_notification_global_sn` + 3 索引），**无 `trigger_type+related_model+related_id` 唯一约束** | ✅ 一致 |
| 27 | **附：计划门禁两脚本不存在** | 未实现 | `[跑/读]` `scripts/` 仅 15 个 `.py`（`_probe_seed`/`_sandbox_compat`/`_test_bootstrap`/`check_db_bootstrap`/`check_doc_claims`/`check_migration_heads`/`check_model_refs`/`check_properties`/`check_templates`/`functional_test`/`migrate_sqlite_to_postgres`/`permission_matrix`/`route_inventory`/`smoke_test`/`windows_service`）；`check_notification_triggers.py`、`check_is_archived_policy.py` 均 **False** | ✅ 一致 |

### 批次8 —— 口径收口与残余

| # | 条目 | 文档状态 | 独立复算证据 | 一致? |
| --- | --- | --- | --- | --- |
| 28 | **B8-01/02/03** 六处 `is_archived` 未统一 | 未实现 | `[读]` 未统一：`routes.py:4797 is_(False)`、`:4808 filter_by(is_archived=False)`、`:6125`、`:12065`、`:12093`、`:12122`；已统一：`:6247 db.or_(FinishedProduct.is_archived.is_(False), …is_(None))`、`:6254`（RawMaterial 同款）、`quality.py:744`、`mes_service.py:1562` | ✅ 一致（六处 + 四处逐行相符） |
| 29 | **B8-05/06** 内联 role 15+2、无豁免注释 | 部分实现（A-7 改判**未实现**） | 见 #4（15+2 逐行复算）；`tasks.html:340`、`task_detail.html:13` 上下文 8 行内无豁免注释 | ✅ 一致 |
| 30 | **B8-07** 分页白名单 | 已实现（静态面）（A-7 改判**部分实现**） | `[读]` `routes.py:293 def handle_pagination_args(f)`、`:304 if per_page not in [20, 50, 100]:`、`:305 per_page = 20` | ✅ 一致（A-7 改判合理：无「锁死」断言载体） |
| 31 | **B8-10/11/12** 死清理块 / 目录泄漏 / 内存流导入 | 未实现 / 部分实现 | `[读]` `routes.py:7647 def download_product_template`、`:7650 temp_path = None`、`:7654-7656 io.BytesIO()`、**`:7668-7674` 与 `:7675-7681` 两处 `if temp_path and os.path.exists(...)`（temp_path 全程 None ⇒ 死代码）**；`:5083 def save_temp_file`、`:5085 tempfile.mkdtemp()`、`cleanup_temp_files` `:2180`（无 `rmdir/rmtree`）、`@bp.before_request` `:2203`、唯一调用点 `:7698`；`quality.py:1615 def import_inspection_tasks`、`:1634 df = pd.read_excel(file)` | ✅ 一致 |

### 批次9 —— 文档纠偏（只判「计划要求改的文档改了没有」）

| # | 条目 | 文档状态 | 独立复算证据 | 一致? |
| --- | --- | --- | --- | --- |
| 32 | **B9-01/02** 旧数字仍在位 | 未实现 | `[读]` `docs/继续开发准备报告.md:14`「261 个 main 视图 = 150 装饰器 + 102 inline role + 9 仅 login_required」；`:20`「31 模板 77 处硬编码 role」；`:24`「194 路由」；`:21`/`:57`「2 个 head」；`:50`「`quality/tasks.html:337`」**逐字仍在位** | ✅ 一致 |
| 33 | **B9-12/B11-01** `_ENSURED_COLUMNS` 10 表 43 列未落文档 | 未实现 | `[读]` AST `app/__init__.py:21` ⇒ **tables=10 / cols=43**（逐表 6/9/6/6/1/2/3/8/1/1）；三份主文档「10 表 43 列」命中 **0**；`148d8a5` 命中 2/2/3，`f60a54d` 命中 **0** | ✅ 一致 |
| 34 | **B9-15/B9-16** 质检「完整」未降级、`AGENTS.md` 「8 个模块」0 命中 | 未实现 | `[读]` `docs/业务流程现状与缺口.md:51` 仍「完整」，全文「部分实现」= **0**；`AGENTS.md` 「8 个含」= **0**；`app/main` 实测 **7 模块/265 条**（与 A-6 同值） | ✅ 一致 |

### 批次10 / 批次11

| # | 条目 | 文档状态 | 独立复算证据 | 一致? |
| --- | --- | --- | --- | --- |
| 35 | **B10-01a/01b/01-边界/02/03/04/08/11** | 见各行 | `[读]` 具名约束逐行命中 `models.py:84/110/111/145/242/314/394/424/466/467`；`[库]` `alembic_version = f179636cecf0`（**未** stamp 到 `p1nonctarget`）、`sqlite_master` 表 **75**；迁移碎片 `011e395c1aa4:21/38/146/164`、`a3f28e475446:71/107` 逐行命中；`scripts/deploy.bat:178-179`、`Jenkinsfile:295-296` 逐行命中；`permissions.py:96 'my_tasks.use'` + 使用点 `routes.py:3287 @require_capability('task.manage','my_tasks.use')`、`:356 can_any('my_tasks.use',…)`；`routes.py:9258-9268`（`:9267-9268` TODO）→ `:9293 db.session.delete(customer)`；`production_center.py` `inbound`/`finished_product`/`stock_kind`/`qc_gate`/`inspection` 各 **0** | ✅ 一致（**唯 B10-11 的「qualit 0 命中」不成立，见 #36/F-5**） |
| 36 | **B10-11**「`qualit` 0 命中」 | 未实现（须先拍板） | `[读]` `app/main/production_center.py:294 'quality_status': item.quality_status` ⇒ **`qualit` 文本命中 1 行**（我的第一遍 `findall` 计 2 次为同一行的键+值）⇒ **该 grep 断言不准**，但「不扣料/不入库/无门禁」的结论仍成立 | ⚠ 方向一致、断言需订正（F-5） |
| 37 | **B11-04/05** 仓库卫生部分实现、验收记录 0 | 部分实现 / 未实现 | `[跑]` `git ls-files uploads`=**0**、`git ls-files '*.pyc'`=**0**、`git rev-list --left-right --count github/main...HEAD`=**0 0**、`git status --short` **有 4 条未跟踪**；`Get-ChildItem docs -Filter '验收记录*'` = **0** | ✅ 一致 |
| 38 | **B9-13** `routes.py` 行数口径 | 部分实现 | `[读]` `routes.py` = **511,969 B / `splitlines()`=12155 / `\n`=12155 / CRLF=0 / 无 BOM**；文档仍写 `12126` | ✅ 一致 |

### 阶段C（`70-` §10.x）

| # | 条目 | 文档状态 | 独立复算证据 | 一致? |
| --- | --- | --- | --- | --- |
| 39 | **§10.1** 构建层晋升 | 未做（blocked，不得折算 pass） | `[读]` `Jenkinsfile` 生效 `error(` = **0**（`:111/:112/:121/:122` 全为 `//` 注释；`:124` 是 `echo`）；`.github/workflows/docker-deploy.yml:19 continue-on-error: true`、`:57 build-and-push`（`:58` 注释明示未加 `needs: gate`）；`ci_gates.py:117-132` `state='blocked'` + `not_counted_as_passed: True` | ✅ 一致 |
| 40 | **§10.2** C-07 硬闸 | 未实现（blocked） | `[读]` `app/__init__.py:156-224` 无闸（见 #3）；`harness/r2_c07_probe.py` 存在 | ✅ 一致 |
| 41 | **§10.3 P1** 审计 `target_id` NULL 且可回滚 | 未实现 | `[读]` `routes.py:5149 db.session.add(product)` → `:5152 log = AuditLog(` → `:5159 target_id=product.id`（**其间无 flush**）；`quality.py:625 add(task)` → `:628 AuditLog(` → `:635 target_id=task.id`（同形）；对照三处**有** flush：`routes.py:564`、`:1734`、`:4420`。`[库]` `count(target_id IS NULL AND can_rollback=1)` = **10**，id 清单 `[7,8,12,15,24,29,40,44,68,73]` **逐字与文档相同** | ✅ 一致（含真库读数逐字相符） |
| 42 | **§10.3 P2** 缺 f 前缀 | 未实现 | `[跑]` `Select-String` ⇒ `routes.py:4945`、`:5036` 同字面量 `'第{index+2}行导入失败，请稍后重试或联系管理员'`（**无 f**）；对照 `:3896`/`:4028` 有 f | ✅ 一致 |
| 43 | **§10.3 P9** 报工路径报废无 `scrap` 台账行 | 未实现 | `[读]` `mes_service.py:1121-1143`（`:1125 if wp:` → `:1127 inbound_workpiece(stock_kind='scrap')`；`:1138 item.status='scrapped'`；`:632 workpiece_id=None`） | ✅ 一致 |
| 44 | **§10.3 P10** `notes` KeyError + 取价三处不一致 | 未实现 | `[读]` `excel_generator.py:336-341` 字典键 = `date`/`employee_id`/`process_code`/`quantity`（**无 notes**）；`routes.py:2733 notes=data['notes']` → `:2739 error_messages.append(f"处理记录时出错: {str(e)}")`；取价 `:2717-2720`（带 `effective_date` + `order_by desc first`）vs `:3902`/`:4020 filter_by(process_code).first()` | ✅ 一致 |
| 45 | **§10.7 / N-3** TL-05/06/07 三件已落盘且自检通过 | 可改「验收 + 进链」 | `[跑]` `check_properties --selftest` **22/22 / exit 0**；`check_doc_claims --selftest` **16/16 / exit 0**；`check_doc_claims --list-constants` **20 条 OK / exit 0**；`requirements.lock` 存在 | ✅ 一致 |
| 46 | **§10.8 / P12** 两处下游资产按无参调用 | 未实现 | `[读]` `reconcile_r2.py:555 chk_subprocess([PY,'-B','…/coverage_drift.py'], '漂移判据 exit 0')`（无 `--coverage`）；`r2_v14_ledgerbook.py:257-262` `command` 拼串无 `--coverage` 且 `'exit_code': 0`；`[跑]` `coverage_drift.py` 无参 ⇒ **[USAGE] … exit 2 = 未提供产物（用法错误，不是回归）**，**exit code = 2** | ✅ 一致 |
| 47 | **P11** 原载体已清 + 同族残留 | 部分关闭（A-10） | `[跑/读]` `Test-Path _probe_tmp` = **False**；`git status` 无该目录；`scripts/_probe_seed.py` 仍在（mtime 2026-08-27，先于本轮） | ✅ 一致（A-10 与当前工作区状态相符） |
| 48 | **`AGENTS.md` 门禁表期望值** | 逐字相符、不需改 | `[跑]` `check_templates` = `87 templates / 44 declared / 40 used in templates / 44 used on routes / landing 5` → `RESULT: OK`；`check_migration_heads` = `HEADS=['p1nonctarget'] / head_count=1 / revisions=35`；`check_properties` = `已扫描 23 个文件，模型类 74 个`；`check_model_refs` = `scanned 23 files, name_query_refs 602, violations 0`；`route_inventory` = `total rules=271 / duplicate=0`；`ci_gates --list` = `steps=14`（blocking 10 + report-only 4），SHA256 = `2EDB60DAE31C5D649E3A3177D5502AD2EB3438E85D5898DC7EC48C83EED75D09` | ✅ 一致（六项 + 14 步 + SHA256 全部逐字相符） |
| 49 | **`AGENTS.md:87` 硬错定性** | 硬错-1（「全仓『入口缺失』0 命中」） | `[读]` 源码侧：`ci_gates.py:1138 code = 1 if (...) else (2 if report_fail else 0)`、全文无 `return 3`/`sys.exit(3)` ✅ **但**：`Jenkinsfile:104 exit /b 3`（入口缺失守卫）+ `:110 if (ciRc == 3)` + `:102/:111/:112/:114`、`.github/workflows/docker-deploy.yml:35`、`ci_gates.py:122` 自陈 `ciRc==3` ⇒ **exit 3 真实存在（属 CI 封装层），「全仓 0 命中」不成立** | ❌ **不一致（F-1，高）** |

### 2.10 本次抽查**未能独立复跑**的项（不计入一致，见 §6）

行为级读数（`nc_rows_delta`、`Δ=100.0`、`scrap_rows_delta=0`、`residue_exists=true`、`employee Δ=0`、门禁两侧 allowed 差分）**本次未复跑**（需在副本库上跑请求型/行为型探针，与「不得写真实 app.db」纪律冲突，且 `80-` 已自陈为引用）；`smoke_test` / `permission_matrix` / `functional_test` / `w2w3_probe` **本次未跑**。

---

## 3. `81-` 规划的独立核查

### 3.1 每个批次的 inScope 路径存在性（逐条给存在性）

| 批次 | inScope 声明的路径 | 实测存在性 |
| --- | --- | --- |
| **批次12** | `app/main/routes.py` ✓ / `app/utils/excel_generator.py` ✓ / `app/services/mes_service.py` ✓ / `app/main/quality.py` ✓ / `app/templates/main/salary*.html` | **4/4 存在**；通配 `salary*.html` 命中 **1 个**：`app/templates/main/salary_calculation.html` ✓（B12-04 落点即它） |
| **批次13** | `app/main/routes.py` ✓ / `app/main/quality.py` ✓ / `app/services/notification_service.py` ✓ / `app/main/production_center.py` ✓ / `app/models.py` ✓ / **新增** `scripts/check_notification_triggers.py`（当前 False，属"新增"✓）/ `test-reports-2026-10/harness/ci_gates.py` ✓ | **6/6 既有路径存在**（1 个为计划新增，与文本一致） |
| **批次14** | `app/templates/main/stock/nonconformities.html` ✓ / `app/templates/main/quality/records.html` ✓ / `…/quality/templates.html` ✓ / `…/quality/tasks.html` ✓ / `app/main/stock.py` ✓ / `app/main/quality.py` ✓ / `app/services/mes_service.py` ✓ / `app/models.py` ✓ | **8/8 存在** |
| **批次15** | `app/main/routes.py` ✓ / `app/main/quality.py` ✓ / `app/templates/main/my_tasks.html` ✓ / `…/tasks.html` ✓ / `…/production_batch_detail.html` ✓ / **新增** `harness/chain_count_consistency.py`（False ✓）/ `harness/ci_gates.py` ✓ | **6/6 存在** |
| **批次16** | `app/templates/main/{tasks,my_tasks,production_batch_detail,consumables,consumable_categories,delivery_batches,process_assignment_bulk,products,inventory}.html` 均 ✓（9/9）/ `app/templates/main/advanced_search.html` ❌ **不存在** / `app/templates/main/quality/*.html` ✓ / `app/static/js/**` ✓ / `app/__init__.py` ✓ / `config.py` 需自行确认 `app/__init__.py` 已用 `Config` | **14/15 存在，1 条路径错误（F-3）**；**另：inScope 未列 `production_center.html`/`production_center_item.html`，但 B16-02 要求改其中 3 处 fetch（F-6）** |
| **批次17** | `scripts/**` ✓（含 `permission_matrix.py`、`deploy.bat`）/ `test-reports-2026-10/harness/**` ✓（`ci_gates.py`/`run_gates.py`/`reconcile_r2.py`/`r2_v14_ledgerbook.py` 均在）/ `app/main/routes.py` ✓ / `app/__init__.py` ✓ / `migrations/versions/**` ✓ / `Jenkinsfile` ✓ / `deploy.config.yml` ✓ / **删除** `app/main/sales_routes.py`（存在 ✓，待删） | **8/8 存在** |
| **批次18** | `docs/**` ✓ / `AGENTS.md` ✓ / `test-reports-2026-10/**`（仅新增订正件与验收记录）/ `scripts/check_doc_claims.py` ✓ / `harness/{evidence_hash,regression_preflight,reconcile_r2,r2_v14_ledgerbook}.py` 均 ✓ | **路径存在**；**但与 B18-08 的需求不闭合（F-10）**：B18-08 还要改 `harness/fixtures.py`、`harness/api_matrix.py`、`harness/final_recount.py`、`harness/ci_gates.py`（运行锁）——**四者均不在 inScope 白名单内**（四文件实测均存在） |

### 3.2 验收标准是否**可判定**（能否构造阴/阳对照）

- **65 条新编号逐批核对**：B12-01…B12-05（5）、B13-01…B13-09（9）、B14-01…B14-08（8）、B15-01…B15-08（8）、B16-01…B16-08（8）、B17-01…B17-19（19）、B18-01…B18-08（8）= **65**，与附录 B 的 `5+9+8+8+8+19+8=65` ✓ 自洽。
- **对照栏齐备性**：65 行**均有「阳性对照 + 阴性对照」两列且基本非空**；**唯 1 行缺阳性对照**：**B12-05**（`81-:110` 阳性栏写「——（文档类…）」）⇒ 与 §5.2 DoD-1「缺任一对照 = 未完成」形式冲突（**F-9，低**；该项本身可用文本断言判定，只是栏位空）。
- **可判定性不足/需点名的 6 处**（不含上面那条）：
  1. **B13-02**（`81-:159`）：判据「存量 `count(target_id IS NULL AND can_rollback=1)` 由 10 → 0」**只能在真实 `app.db` 上判定**，与 §5.2-3/-4（真库三值逐位不变、所有写只在副本）**冲突** ⇒ **F-2（中）**。
  2. **B14-01/B14-03/B14-04**（`81:206/208/209`）：判据以 **DOM 可见文案**为口径 ⇒ 静态不可判，`81-` 已把它放 §4.4 手工面 M-1 ✓（**可见性判据仍需浏览器，标法正确**）。
  3. **B16-01**（`81-:307`）：二选一；若选「前端客户端过滤」则判据降级为 `无法核实（需浏览器）` ✓ 文本已显式标注，**可接受**。
  4. **B16-07**（`81-:313`）：若选「只登记不本地化」⇒ 该格判 **blocked（需离线环境）**、不得写成通过 ✓ 文本已标，**可接受**。
  5. **B17-09 轨二**（`81-:377`）：文本已标「本环境不可验 ⇒ 必须标『需非沙箱环境』，不得写成已通过」✓
  6. **B18-01**（`81-:443`）：判据是「逐条表达式可在源码复现」，阳性对照栏给的是 `check_doc_claims 20/20 + violations=0`（**是命令读数而非对照**）⇒ 属「可判定但对照形式偏弱」，建议给一条「故意写错一个数字 ⇒ check_doc_claims 非 0」的注入对照（B18-03 已有该注入 ✓，故实为可用）。
- **结论**：65 条中 **64 条判定性成立**（其中 8 条属 DOM/离线/非沙箱类，已由 §4.4 手工面 `M-1…M-5` 承接且标注齐备）＋**1 条对照栏不完整（B12-05 → F-9）** = 65；另有 **1 条虽可判但与同文件 DoD 冲突（B13-02 → F-2）**。

### 3.3 blocked / 未覆盖项**没有被计入已完成**（逐项核）

| 检查点 | 实测 | 结论 |
| --- | --- | --- |
| `81-` §1.1 是否把 `A-63` 第二步 / `C-07` 计入完成 | `81-:25` 单列「blocked（不得折算 pass）」并写明 `P-3 = 真实 CI 全绿 ≥1 轮 = 0 轮` 与 `blocked(生产面冻结)`；`81-:680-685` 再列 blocked 表 | ✅ **未折算** |
| `81-` §6.1/§6.2 的 `G-1…G-22` 是否被吞进完成数 | G-4（C-07）标 `保持 blocked`；G-7（轨二）标 `blocked(需非沙箱)`；G-8（A-63）标 `保持 blocked`；G-5/G-6/G-9/G-11 等标 `blocked/not_covered` 且写「不计入通过数」 | ✅ **未折算** |
| `ci_gates` 侧证据链是否存在 | `[读]` `ci_gates.py:117-132`（`state='blocked'`、`not_counted_as_passed: True`、`condition_to_unblock`） | ✅ **可核** |
| 六条**作废口径**是否出现在 `81-` 正文 | `81-:667-676` 为唯一出现处（黑名单表，标注「作废 → 必须改用」）；正文我 grep 复核：`110 处/28 文件` 0 命中、`8 个模块` 0 命中（`81-:672` 仅在黑名单）、`BytesIO 15` 0 命中（仅黑名单）、`0/12` 仅黑名单、`B7-06 已实现` 仅黑名单 | ✅ **符合自身声明** |
| 但 `81-` §2 批次17 把 **B17-02 ≡ C-07** 当作普通验收项排入（`81-:343/:370`），批次 DoD 又要求「本批验收全绿」 | `81-:370` 的 B17-02 验收行**未标 blocked 前置**（只在 §6.1 G-4 写了「解除 = 生产面冻结解除 + 显式授权」） | ⚠ **登记缺陷（F-10 同类，中低）**：应显式写「前置未解除 ⇒ 本项只登记不实施，不阻塞本批其余条目」 |

### 3.4 声称的验证命令 —— 真实实跑（exit code 逐条给出）

| 命令（`81-` 附录 A / 各批） | 实跑读数 | exit |
| --- | --- | --- |
| `scripts/check_templates.py` | `87 templates / 44 declared / 40 used in templates / 44 used on routes / landing 5` → `RESULT: OK` | **0** |
| `scripts/check_migration_heads.py` | `HEADS=['p1nonctarget']` / `head_count=1 revisions=35` | **0** |
| `scripts/check_properties.py` | `已扫描 23 个文件，模型类 74 个` → `RESULT: OK` | **0** |
| `scripts/check_model_refs.py` | `scanned 23 files, name_query_refs 602, violations 0` → `RESULT: OK` | **0** |
| `scripts/route_inventory.py` | `total rules=271` / `duplicate=0`（报告型，`in_gate_chain=false`） | **0** |
| `scripts/check_db_bootstrap.py` | `种子库账号数=64 / 首次启动导入 64 个账号，再次启动后 64 个 / 直接拷贝 6712 行，跳过 0 张表` → `OK: …均通过`（**在临时空库上跑，app.db 未变**） | **0** |
| `harness/ci_gates.py --list` | `phase=first steps=14`；blocking 10 + report-only 4 | **0** |
| `harness/coverage_drift.py`（无参） | `[USAGE] 未提供 --coverage…` + `exit 2 = 未提供产物（用法错误），不是回归` | **2**（符合文本） |
| `scripts/check_doc_claims.py --selftest` | `自检 16/16 通过` | **0** |
| `scripts/check_doc_claims.py --list-constants` | **20 条钉常量全部 OK** | **0** |
| `scripts/check_properties.py --selftest` | `自检 22/22 通过` | **0** |
| `Select-String routes.py '第\{index\+2\}行导入失败'` | 命中 `:4945`、`:5036`（无 f） | 0（命中即符合 80- P2） |
| `Select-String nonconformities.html 'nc.type|nc.status'` | 命中 `:12`、`:13` | 0（命中即符合 80- B6-01） |

**未实跑（纪律/环境）**：`smoke_test.py`、`permission_matrix.py`、`functional_test.py`、`w2w3_probe.py --scenario all`、`negative_matrix.py`、`uat_chains.py`、`w4_http_contract.py`、`probe_backend_field.py`（请求型/行为型，需副本库与服务，且 `80-` 已自陈未复跑）。`w2w3_probe.py` 确有 `--scenario`（`:1197`）、`negative_matrix.py` 确有 `--out`（`:915`）⇒ **命令形态真实可跑**（存在性已核，未执行为纪律选择）。

---

## 4. 三类反模式专章

### 4.1 「`file_exists` 当已实现」

**未发现硬性违规。** 我搜过：
- `80-` §0.1 的判定档位表（`:19-30`）明文禁止「文件存在」判已实现；
- `80-` §7 S-1（`:500`）自陈 12 条「已实现」中 8 条行为级 + 4 条源码/读数级；
- 我逐条核这 12 条：`B3-01`（源码读数级，本次取行证实）、`B4-01/02/03`、`B5-01/02/04/05/06`（载体 `file:line` 全部在位）、`B10-01a`、`B10-01-边界`（**源码面在位**）。
- **唯一接近边界的两条**并**已被 `81-` 的起点表处理**：`B8-07` 由 A-7 改判「部分实现」（理由正是「缺验收载体」）；`B10-01a`/`B10-01-边界` 在 `80-:301` 与 `:304` 行内已注「⚠ 对既有库无效」/「与计划的关系需澄清（是已完成还是立项时已存在被误列为待做）」，**属已披露**。
- **建议（非 finding 级）**：`81-` §1.1 把 `B10-01a`/`B10-01-边界` 计入「可复用、不重做」，易被读成「本轮战果」；建议加一句「立项前已在位」。

### 4.2 「文档说已修当证据」

**发现 1 处实质冲突 + 1 处轻度残留。**
- ✅ **成立的两处**：`80-` D14/D20 称「`AGENTS.md` 已修正（`:92-94` / `:92-99`）」——我读 `AGENTS.md:92-101`，确有「落盘改到 `.tmp/<RUN_ID>/`、`--out`/`--no-dump`、写盘失败只 `[WARN]`」「`coverage_drift` 缺参 = exit 2」等订正文本 ⇒ **属实**。
- ❌ **不成立的一处（F-1，高）**：`80-:412`（硬错-1）与 `80-:147`（§1.1 口径 B 表）判定 `AGENTS.md:87` 的「`3=入口缺失`」为**硬错**，理由是「`ci_gates.py:1138` 只有 0/1/2」+「全仓『入口缺失』**0 命中**」。实测：`ci_gates.py` 确实不产生 3（✅ 该半句对），但 **`Jenkinsfile:104 exit /b 3`、`:110 if (ciRc == 3)`、`:102/:111/:112/:114`、`.github/workflows/docker-deploy.yml:35`、以及 `ci_gates.py:122` 自己的 `ciRc==3`** 都表明 **exit 3 是 CI 封装层的既成语义**。⇒「硬错」定性**过强**，「全仓 0 命中」**为假**；下游 `81-:428/:444`（B18-02）据此要求「退出码语义只留 0/1/2」⇒ **会删掉一条正确表述**。
- ⚠ **轻度残留（F-7，低）**：`80-` §5.2-A7（`:419`）与 §6.3 N-A4（`:489`）仍把 `BytesIO 15 处`标「待裁定」，§6.3 抬头（`:482`）与 §0.2 条 3（`:35`）、§8.2 条 4（`:526`）仍写「待 captain 追加裁定」；而 A-9/A-13 已裁定「15 处作废」，`81-` §6.3（`:667-676`）又把该值列入**禁止出现在 `80-` 正文**的黑名单。§0.5 只覆盖了 A-7/A-8 的计数，未覆盖此处。
  （我搜过：`80-` 全文 `BytesIO`/「待裁定」相关行 = `:35`（§0.2 条 3）、`:419`(A7)、`:445`(§5.3 BytesIO 行)、`:482`(§6.3 抬头)、`:489`(N-A4)、`:526`(§8.2 条 4)；`81-` 全文 `15 处` 仅在黑名单表出现。）

### 4.3 「把 blocked 折算 pass」

**未发现。** 我搜过：`80-` §3 两个 blocked 前置表（表体 `:347-350`，A-63 行 `:349`）、`80-` §1.2 F-5、`81-` §1.1（`:25`）、`81-` §6.3 blocked 表（`:680-685`）、`81-` §6.1 G-4/G-8、`81-` B18-07 验收（`:449`）；并核源码侧 `ci_gates.py:117-132` 的 `state='blocked'` / `not_counted_as_passed=True`。
- 两件交付物均**原样登记、未折算**；`81-` §5.2 DoD-5 还要求「未在沙箱执行的项显式标注，不得写成通过」✓。
- **唯一边界问题**：`81-` 把 `B17-02`（≡ C-07，blocked）作为批次17 的普通验收项（`81-:343/:370`），DoD 又要求本批全绿 ⇒ **会让批次17 无法收口**（见 §3.3 末行 / F-10）。

---

## 5. 结构化 findings（可被第三方按 `file:line` 复现）

| id | severity | problem | requiredFix | file | line |
| --- | --- | --- | --- | --- | --- |
| **F-1** | **high** | 把 `AGENTS.md:87` 的「`3=入口缺失`」定为**硬错**，并以「全仓『入口缺失』**0 命中**」为佐证；实测 `Jenkinsfile:104` 有 `exit /b 3`、`:110` 有 `if (ciRc == 3)`（`:102/:111/:112/:114`、`.github/workflows/docker-deploy.yml:35`、`ci_gates.py:122` 的 `ciRc==3` 同族）⇒ exit 3 是 CI 封装层真实语义，该定性过强、佐证为假；下游 B18-02 因此要求「退出码只留 0/1/2」**会删除正确表述** | ①`80-` 撤回「硬错-1」定级，改为「口径不完备」：写成「`ci_gates.py` 自身退出码只 0/1/2；**3 由 CI 封装的入口缺失守卫产生**（`Jenkinsfile:104 exit /b 3` → `:110 if (ciRc == 3)`）」；②`81-` B18-02 的 requiredFix 由「只留 0/1/2」改为「补注 3 的来源（`Jenkinsfile:104/:110`），不得删除该语义」；③`80-` §1.1 口径 B 表的「1 处硬错」同步订正为「1 处口径需补注」 | `test-reports-2026-10/80-开发与需求文档-实际进度逐条对账.md`；`test-reports-2026-10/81-后续开发与测试规划.md` | 80-:412（硬错-1，另 80-:147 §1.1 口径 B 表、80-:416）；81-:428（B18-02）、81-:444（B18-02 验收） |
| **F-2** | **medium** | `B13-02` 的验收（真库存量 `count(target_id IS NULL AND can_rollback=1)` **10 → 0**）要求**写真实 `app.db`**，与同文件 §5.2 DoD 第 3 条（真库三值逐位不变）与第 4 条（所有 DB 写入只在副本）**直接冲突** ⇒ 按 DoD 执行则该项永不可判通过，批次13 无法收口；拍板项 5 的结论也无法落地 | ①在 §5.2 DoD 为「真库数据修复」类条目加**显式例外条款**（备份 → 单次数据修复 → 记录新 SHA256/大小/mtime + SQL 全文 + 执行人/时点），或 ②把 `B13-02` 拆为「代码面（副本可判）」+「数据修复（真库，独立运行手册、不进批次 DoD）」 | `test-reports-2026-10/81-后续开发与测试规划.md` | 81-:142（B13-02 条目）、81-:159（B13-02 验收）、81-:605（DoD-3）、81-:612（DoD-4） |
| **F-3** | **medium** | 批次16 inScope 与 B16-06 落点写的 `app/templates/main/advanced_search.html` **不存在**；真实文件是 `app/templates/main/search/advanced_search.html`（`glob app/templates/**/advanced_search.html` 唯一命中）⇒ 执行者按 inScope 找不到落点 | 把两处路径改为 `app/templates/main/search/advanced_search.html`；并复核 `80-` B8-08/B8-09（`:268`/`:269`）同样只写文件名的引用 | `test-reports-2026-10/81-后续开发与测试规划.md` | 81-:300（inScope）、81-:296（B16-06 落点）、81-:312（B16-06 验收） |
| **F-4** | **low** | 「`harness/` 内**无任何**件数守恒/双链对拍脚本」为**过宽**断言：`harness/uat_chains.py:403` 有名为「件数守恒」的判据（`P0-1.9`，对照 AC-17），`:913` 亦有「件数守恒」（AC-29e）；真正缺的是「报工链 vs 工件链 **件数合计相等**」的对拍 | 表述收窄为「**无**『两条生产链 `fg` 件数合计相等』的对拍脚本；既有 `uat_chains.py:403/:913` 为单链/守恒基线，不构成该对拍」 | `80-…diff.md`；`81-…md` | 80-:215（B4-08 证据）；81-:247（B15-07 落点）、81-:263（B15-07 验收） |
| **F-5** | **low** | B10-11 的 grep 断言「`qualit` **0 命中**」不成立：`app/main/production_center.py:294` 有 `'quality_status': item.quality_status`（1 行，读出用途） | 改为「`inbound`/`finished_product`/`stock_kind`/`qc_gate`/`inspection` 均 **0 命中**；`quality_status` 仅 `:294` **读出**、无门禁判定与写入」 | `test-reports-2026-10/80-…diff.md` | 80-:314（B10-11 证据格） |
| **F-6** | **medium** | 批次16 inScope **不闭合**：B16-02 要求把 15 处原生 `fetch` 全改 `apiFetch(`，其中 **3 处**在 `production_center.html:92` 与 `production_center_item.html:171/204`，但两个文件**不在 inScope**（inScope 只列了 9 个模板 + `quality/*.html` + `app/static/js/**` + `routes.py` + `__init__.py`/`config.py`）⇒ 按 inScope 无法满足 B16-02 的「站点数 = 0」判据 | inScope 补 `app/templates/main/production_center.html`、`app/templates/main/production_center_item.html`（或把 B16-02 的 15 处清单缩到 inScope 内并按实际站点数改判据） | `test-reports-2026-10/81-后续开发与测试规划.md` | 81-:300（inScope）、81-:292（B16-02 落点）、81-:308（B16-02 验收） |
| **F-7** | **low** | `80-` 正文仍以「待裁定」呈现 4 条**已被 A-6…A-13 裁定完毕**的口径（`BytesIO 15`、`app/main 8 个模块`、批次8 `0/12`、`B7-06 已实现`），而 `81-` §6.3 把其中数条列为「**禁止出现在 `80-`/`81-` 正文**」的黑名单；`80-` 新增的 §0.5 只覆盖 A-7/A-8 的起点计数 | 在 `80-` §0.5 追加一行「本节同时取代 §5.2-A7/§5.3/§6.3 中『待裁定』的 4 条口径（`A-6`/`A-9`/`A-11`/`A-12`/`A-13`）」；或把 §6.3 抬头改为「已由 A-6…A-13 裁毕」 | `test-reports-2026-10/80-…diff.md` | 80-:63-90（§0.5）、80-:419（A7 行）、80-:445（§5.3 BytesIO 行）、80-:489（N-A4）、80-:482（§6.3 抬头）、80-:526（§8.2 条 4） |
| **F-8** | **low** | 批次16 的「必跑」验证命令依赖 `.analysis-scratch/t4_*.py`（5 个），而 `.analysis-scratch/` 在 `.gitignore:8` 被忽略（`git ls-files .analysis-scratch` = 0）⇒ 干净检出/CI 上这些命令**不可跑**；批次16 DoD 却引用它们 | 二选一：①把 5 个分析器移入 `test-reports-2026-10/harness/`（并登记）；②在 `81-` 标注「本机 scratch 依赖，不作 DoD 判据」，并改用可入库的等价断言 | `test-reports-2026-10/81-后续开发与测试规划.md`；`.gitignore` | 81-:320-323（`t4_tpl_scan/csrf_split/js_calls/cap_gap`）；`.gitignore:8` |
| **F-9** | **low** | `B12-05` 的**阳性对照栏为空**（写「——（文档类…）」），与 §5.2 DoD-1「缺任一对照 = 未完成」形式冲突；该项本身可用文本断言判定 | 补一条可判定对照：阳性 = 口径块出现「不做金额台账 + **库存**台账行必须写」；阴性 = 不出现「不做报废台账」旧措辞（阴性已有，只需把阳性写成文本断言而非「——」） | `test-reports-2026-10/81-后续开发与测试规划.md` | 81-:110（B12-05 验收行）、81-:97（B12-05 条目） |
| **F-10** | **medium** | 两处 inScope/前置不闭合：①批次18 inScope（`81-:436`）把 `test-reports-2026-10/**` 限为「仅新增订正件与验收记录」+ 4 个 harness 文件，但 B18-08（`81-:434`）还要改 `harness/fixtures.py`、`harness/api_matrix.py`、`harness/final_recount.py`、`harness/ci_gates.py`（运行锁）——四者均**不在** inScope 白名单；②批次17 把 `B17-02`（≡ §10.2 C-07，`blocked(生产面冻结)`）当普通验收项（`81-:343/:370`），而批次 DoD 要求「本批验收全绿」⇒ 无法收口 | ①批次18 inScope 的 harness 名单补齐上述 4 文件；②`B17-02` 验收行加显式前置：「前置未解除 ⇒ 本项**只登记不实施**、`not_counted_as_passed`，不阻塞本批其余条目」（与 §6.3 blocked 表口径一致） | `test-reports-2026-10/81-后续开发与测试规划.md` | 81-:343（B17-02 条目）、81-:370（B17-02 验收）、81-:434（B18-08）、81-:436（批次18 inScope） |

**severity 汇总**：high 1（F-1）｜medium 4（F-2/F-3/F-6/F-10）｜low 5（F-4/F-5/F-7/F-8/F-9）。

---

## 6. 本次复核未覆盖 / 不可核实（不得当作已通过）

1. **行为级读数未复跑**：`nc_rows_delta=+1`、`quality_status NULL→fail`、`gate allowed` 两态、`Δ=100.0`（`false⇒60.0/true⇒160.0`）、`scrap_rows_delta=0`、`residue_exists=true`、`employee Δ=0`、`old_data IS NULL ⇒ 500`、`target_id=null ⇒ 回滚 404` —— 均在**副本库 + 请求型探针**上才能复现；本次按「不得写真实 `app.db`」纪律**未跑**。我改以**载体取行 + 真库只读计数**独立佐证（见 §2/§3）。
2. **请求型/端到端脚本未跑**：`smoke_test`、`permission_matrix`、`functional_test`、`w2w3_probe`、`negative_matrix`、`uat_chains`、`write_suite`、`api_matrix`、`measure_coverage`、`w4_http_contract`、`coverage_drift --coverage …`（后者需 run 产物）。
3. **浏览器/离线/多进程/PG/CI 环境面**：DOM 文案、Select2 实际过滤、移动端断点、`BOOTSTRAP_SERVE_LOCAL` 离线加载（`flask_bootstrap` 是**已安装的第三方包**，不在仓库内：`Test-Path flask_bootstrap` = **False** ⇒ `recon-arbitration.md:19-20` 与 `81-:297` 引用的 `flask_bootstrap/__init__.py:76/108/114-119/173` **属 site-packages 行号**，随环境版本漂移、不可由本仓库复现——属本次**新增的一条口径风险提示**，未列为 finding）——一律**未判**。
4. **`80-`/`81-` 引用的 `docs/**` 只做了 4 份主文档的定点取行**（`继续开发准备报告.md`、`开发进度与交接.md`、`业务流程现状与缺口.md`、`交付说明-P0P1.md`），未逐字通读全部 24 条 D 漂移。
5. **`81-` §6.1/§6.2 的 `G-1…G-22` 状态**仅核了 `G-4/G-7/G-8/G-19/G-21/G-22` 与其载体（`70-` §9 原文未逐条读）。
6. **`80-` 的 24 条 D 漂移**抽核了 **D1–D13、D16–D19、D21–D23**（文档侧逐字取行 + 源码/工具读数），**未逐条核** D14/D15/D20/D24 的文档侧措辞与量纲表述（D14/D20 只核了 `AGENTS.md:92-101` 的订正文本确实存在）。其中 **D8 的反证独立复现成功**：`git ls-tree -l 'f60a54d^'` ⇒ 三后缀文件确被跟踪（455184 B / 98687 B / 0 B），`git show --name-status f60a54d` ⇒ **7 个 `D`**，`git show 'f60a54d^:.gitignore'` ⇒ **无** `*.bak/*.new/*.backup`（仅 `/app.db.bak-*`）；4 名字型 1989144 B + 三后缀 553871 B = **2543015 B** 逐字节符 ✓。
7. **`80-` 复核期间发生文件变更**（`t15` 追加 §0.5，见 §0.4）：本报告的行号与判定以 **131,911 B/577 行** 版本为准；若该文件再次被追加，请以 §0.4 的声明为锚点重定位。

---

## 7. 复跑附录（仓库根目录；全部只读，命令 → 实测读数）

```powershell
$env:PYTHONIOENCODING='utf-8'
$py = 'F:\Miniconda\envs\wage\python.exe'
Set-Location 'D:\workspace\wage_management_system - bak'

# ⓪ 不变量（开工/收尾各一次）
(Get-Item app.db).Length                     # 2531328
(Get-FileHash app.db -Algorithm SHA256).Hash # F5DA2306…0E0F065
(Get-Item app.db).LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss')   # 2026-09-18 12:50:55
git rev-parse HEAD                           # 534ce70b204c767feee551e8fd04e538374b1de8
git status --porcelain --untracked-files=no  # 期望 0 行（实测 0）

# ① 五项静态门禁（+ 报告型）—— 本次实测全 exit 0
& $py -B scripts/check_templates.py          # 87/44/40/44/landing 5 → RESULT: OK （exit 0）
& $py -B scripts/check_migration_heads.py    # HEADS=['p1nonctarget'] 1 / 35 （exit 0）
& $py -B scripts/check_properties.py         # 已扫描 23 个文件，模型类 74 个 （exit 0）
& $py -B scripts/check_model_refs.py         # scanned 23 files, name_query_refs 602, violations 0 （exit 0）
& $py -B scripts/route_inventory.py          # total rules=271 / duplicate=0 （exit 0）
& $py -B scripts/check_db_bootstrap.py       # 64 账号 / 6712 行 / 跳过 0 张表 （exit 0；临时空库）
& $py -B test-reports-2026-10/harness/ci_gates.py --list   # steps=14（blocking 10 + report-only 4）（exit 0）
& $py -B test-reports-2026-10/harness/coverage_drift.py     # 无参 ⇒ exit 2（用法错误，不是回归）
& $py -B scripts/check_doc_claims.py --selftest             # 16/16（exit 0）
& $py -B scripts/check_doc_claims.py --list-constants       # 20 条钉常量 OK（exit 0）
& $py -B scripts/check_properties.py --selftest             # 22/22（exit 0）

# ② 契约点名的两条核对
Select-String -Path app/main/routes.py -Pattern '第\{index\+2\}行导入失败'   # 命中 :4945 / :5036（无 f）
Select-String -Path app/templates/main/stock/nonconformities.html -Pattern 'nc.type|nc.status'  # 命中 :12 / :13

# ③ 结构与口径（本次实测）
#   app/main 含 @bp.route：7 个模块 / 265 条（routes 192/quality 27/equipment 15/purchase 13/production_center 7/shipping 6/stock 5）
#   全仓 @bp.route = 269（+app/auth 4）；routes.py = 511969 B / splitlines 12155；sales_routes.py = 1 B（仍被跟踪）
#   app/templates/**/*.html = 87；nonconformities.html = 33 行；scripts/*.py = 15 个
#   迁移：35 文件 / 含 create_table 14（AST）/ 守卫 3 ⇒ 无守卫 11 / c02604883c72 24 处 / 字面表名 49
#   _ENSURED_COLUMNS = 10 表 43 列（6/9/6/6/1/2/3/8/1/1）
#   内联 current_user.role：Python 15（+permissions.py:7 docstring）+ 模板 2（tasks.html:340 / task_detail.html:13）
#   通知：def notify_* = 5；非定义调用点 = 1（routes.py:3601）
#   harness/uat_chains.py:403/:913 = 既有「件数守恒」判据；无「双链件数合计」对拍脚本
#   .analysis-scratch/t4_*.py 存在但被 .gitignore:8 忽略（git ls-files = 0）
#   flask_bootstrap 不在仓库内（Test-Path False）⇒ CDN 结论的证据在 site-packages

# ④ 只读真库（绝不写）
python -B -c "import sqlite3;c=sqlite3.connect('file:app.db?mode=ro',uri=True).cursor();print(c.execute('select count(*) from audit_log').fetchone(),c.execute('select count(*) from audit_log where target_id is null and can_rollback=1').fetchone(),c.execute('select version_num from alembic_version').fetchall(),c.execute(\"select count(*) from sqlite_master where type='table'\").fetchone())"
#    ⇒ (73,) (10,) [('f179636cecf0',)] (75,)

# ⑤ 收尾不变量（必须与 ⓪ 逐字相同）
(Get-FileHash app.db -Algorithm SHA256).Hash
```

---

## 8. 只读自证（收尾）

| 项 | 开工 | 收尾 | 结论 |
| --- | --- | --- | --- |
| `app.db` 大小 | 2531328 | **2531328** | 逐位一致 |
| `app.db` SHA256 | `F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065` | **同值** | 逐位一致 |
| `app.db` mtime | 2026-09-18 12:50:55 | **同值** | 逐位一致 |
| `git status --porcelain --untracked-files=no` | 0 行 | **0 行** | 未改任何既有受跟踪文件 |
| 未跟踪项 | 4 条（2 份 docs + `80-` + `81-` + `reconcile-2026-10-08/`） | 同上（+ 本文件） | 与 t13/t15 声明一致 |
| 本次新增 | —— | **仅** `test-reports-2026-10/reconcile-2026-10-08/recon-verification.md` | 只新建、未覆盖任何文件 |
| `flask db migrate/stamp` | —— | **未执行**（全复核无任何 `flask` 命令） | 符合硬纪律 |
| 真实库写入 | —— | **0 次**（唯一 DB 访问 = `mode=ro` 只读查询；`check_db_bootstrap` 在 `tempfile` 空库上跑） | 符合硬纪律 |

---

*本报告的每一条判定都给出本次实测的 `file:line` 或命令读数；凡属引用 `80-`/`81-` 的行为读数，一律在 §2.10/§6 声明「本次未复跑」，不计入一致数。总体 verdict = **needs_revision**（10 条结构化 findings：high 1 / medium 4 / low 5），其中 **F-1 为高优先级**（会导致删除 `AGENTS.md` 的一条正确表述）。*
