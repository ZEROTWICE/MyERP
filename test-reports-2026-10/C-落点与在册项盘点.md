# C 组 · 落点与在册项盘点（P1–P12 / G-12…G-22 / B18-06）

| 项 | 值 |
| --- | --- |
| 盘点者 | `recon-c`（阶段C C 组**只读**盘点者，非实现者） |
| 任务 | `t1`（attempt `1d4ffd9e-26ee-4dab-85ac-e010df1a0f73`） |
| 时点 / HEAD | 2026-10-12（UTC）/ `9f28baa2f4c402b0baa2cddd1bdc95139747936e` |
| 工作区 / 解释器 | `/root/code/MyERP` / `/opt/wage-venv/bin/python`（3.11.2） |
| 方法 | 只读：`grep -n` / `read` / `sqlite3 file:app.db?mode=ro` / `ast` 静态扫描 |
| 未做的 | **未跑请求型脚本**（`smoke_test` / `permission_matrix` / `functional_test` / harness 探针）；未改任何受跟踪文件；唯一新增 = 本件 |
| 真库三值（开工，逐字） | sha256 `34E48E7A21163DB390EEBDA4F2030343F3609AFEDC65D8C6E909D6EB5A49177E` / `2531328` B / mtime `2026-10-12 04:25:37.128430119 +0000` |
| 真库三值（收工，逐字） | 与开工**三项恒等**（零漂移）：`34E48E7A21163DB390EEBDA4F2030343F3609AFEDC65D8C6E909D6EB5A49177E` / `2531328` B / `2026-10-12 04:25:37.128430119 +0000` |

**状态口径**：`已修` / `部分修` / `未修` / `已消除` / `not_measured` / `not_covered`。其中
`blocked`、`not_measured`、`not_covered`、`not_counted_as_passed` **一律不折算 pass**，逐条附解除条件（§4）。
「未发现问题」不算证据；本条只登记**工具 + 口径 + 值**三者齐备的读数。

**判定边界**：本件只做**读码/读库级**重锚。凡判据本身是探针（`r2_c08_probe`、V-12/V-13/V-15、
`uat_chains`、`permission_matrix` 写面、`write_suite`）的条目，若本容器本轮不具备复跑条件，
一律写 `not_measured` + 解除条件，**不得**据读码写成「通过」。

---

## 0. 一页结论

| 条目 | 状态 | 现落点（HEAD 9f28baa 现场） | 建议归属 |
| --- | --- | --- | --- |
| P1 审计 `target_id=NULL` 而 `can_rollback=1` | **已修**（读码 + 真库读数） | 不变量 `routes.py:4465-4478`（def）/ 11 调用点 / `quality.py:601`(def)+`:675` | 留档（可复跑判据见 §1） |
| P2 缺 f-string 前缀（字面量花括号） | **已修** | `routes.py:5499` / `:5592` 均带 `f` 前缀；全仓缺前缀实例 **0** | 留档 |
| P3 `/employees/import` 整单拒绝 | **已修** | `routes.py:2302` `if success_count > 0:` / `:2319-2320` `'success': success_count > 0` | 留档 |
| P4 上传残留（无 `finally`） | **部分修（9/10）** | 10 个导入端点 9 个带 `finally`+`remove`；`import_products`（`routes.py:8313`）**无** `finally`/`remove` | **本批**（1 处）或登记为依赖钩子 |
| P5 行号覆盖不一致 | **部分修（2/2 原载体已修，残余 5 处）** | 原载体 `:4283`/`:4296` 已带「第 N 行」；残余 `:2231`（多行 append）/`:2956`/`:2963`/`:2985`/`:4192` | **本批**（4 条文案 + 1 处目视） |
| P6 内层 `except` 吞失败 ⇒ 事务部分应用 | **已修（关键块）** | 5 处 `db.session.begin_nested()`（`:3662`/`:3768`/`:3922`/`:3945`/`:3989`）+ 关键 handler `raise`（`:3786`/`:3818`/`:3934`/`:4034`）；残 3 处仅 `warning`（非账务） | 留档 + 显式登记设计选择 |
| P7 `04` §2.1 A4 与实现冲突 / 界面无 `goods_receipt` | **已修** | `quality.py:878` 400 守卫；`goods_receipt` 已入 4 个模板（`records.html:31/:261` 等）；N-2 终态复跑 green | 留档 |
| P8 `04` §2.2 B2 工序数口径过时 | **已收口** | `B18-04-订正件…md:530-543`：「**每工序一张**（与 n 无关）」+ 实测 n=2 ⇒ +3 | 留档 |
| P9 报工路径（无工件）报废不产生 scrap 台账行 | **未修**（读码证伪） | `production_center.py:313-400` 全段无 `scrap`/库存写入 | **本批**（若做）或留档 |
| P10 `notes` KeyError + 取价三口径 | **已修** | `excel_generator.py:357-358` 补 `'notes'` 键；`routes.py:157` `pick_process_price` 单点 + 3 调用点 + `excel_generator.py:897-902` 复用 | 留档 |
| P11 仓库根污染 6 个 `.tmp_v15_*` | **已消除**（不可复现） | `ls .tmp_v15_*` ⇒ `No such file or directory`；`ls -a \| grep -i tmp` ⇒ 仅 `.tmp/` | 留档（写状态，禁折算 pass） |
| P12 N-1 修好后两下游资产陈旧 | **已修 2/2** | `reconcile_r2.py:324/:328-330/:593-594` 显式 `--coverage`；`r2_v14_ledgerbook.py:257-262` command 含 `--coverage %s/coverage.json` | 留档 |
| G-12 覆盖分母抬升未同步（N-13） | **部分收口** | `final_recount` 已改（`B18-05:103`）；残余 `40-…md:364`/`:396` 仍写 `method_level_non_get=155`（现钉 **158**，差 **+3**） | **本批**（引用口径）或留档 |
| G-13 V-03/V-05/V-06/V-07 未复跑 | **not_covered（保持）** | 本轮无复跑记录 | 留档（解除条件见 §4） |
| G-14 N-14 修订版产物无 `superseded_by` | **部分处置 / not_measured** | `evidence/` 带 `superseded_by` 的文件 **22** 个（本件实测）；51 条逐产物清单未逐条核对 | 留档 |
| G-15 TL-05/06/07 终态 | **判据面收口，载体缺失（N-D1）** | `evidence/harness/{r2-v13-tl050607,ci-v13-gate}` 与 `evidence/harness/coverage.json` **三者均 MISSING** | 留档（`not_counted_as_passed`） |
| G-16 N-1 残留 2 项 | **①根因已在档、实测不可做；②已修** | ①`coverage_drift.py:52-79` 记 A-70 第①步同路径重基线（`6/14/101` ⇒ `108/116/0`，后值 244575 B），但锚点文件本体缺失；②同 P12 已修 | 留档 |
| G-17 `40` §4.5 字段清单过时/未提交 | **部分修** | 工作区版**已入 HEAD**（`git status` 无 `M`）；但 `:364`/`:396` 数值仍 `155`（现钉 158） | **本批**（与 G-12 同一条引用口径项） |
| G-18 改动面收口时点仍在增长 | **仍在增长（in_progress）** | tracked 647 / `evidence` 文件 **2419**（B18-D-01 记 1974 ⇒ **+445**；两次测量 2396→2419）/ `.tmp` 文件 293 / porcelain **9** | 留档（收口时点须钉） |
| G-19 C-06 写端点 deny 未断言 | **已修** | `scripts/permission_matrix.py:440 write_endpoints` / `:469 run_write_face` / `:527 print_write_face` / `:669-671` 调用 / `:716` 汇总 | 留档（实跑面 not_measured） |
| G-20 同一 CSRF 面两个分母 | **已修为单一分母** | `api_matrix.py:753-756` 明写「**不再断文案**（旧文案判据漏判 24 条）」；`:796-848` 单分母 `probed/enforced_or_exempt/not_enforced` + 可观测性守卫 | 留档 |
| G-21 37 条「GET+写」多方法规则未命中 | **not_measured** | `52-…md:13-14` 现场值「多方法面 44/38→**43/37**」；钉值 `non_get_uncovered_method_level=40`（量纲不同，不得互替） | 留档（需 `api_matrix` 覆盖行实读） |
| G-22 仓库根污染 6 个 `.tmp_v15_*` | **已消除** | 同 P11 | 留档 |
| B18-06 ① `delivery_batches` 对照视图口径 | **not_measured** | `B18-05:85/:260/:437` 三处均记「本会话未复核」 | **本批**（最省：读码写口径说明） |
| B18-06 ② 客户删除关联校验（G-E） | **未实施** | `routes.py:9905` route / `:9908` def / `:9915` `# TODO: 添加订单关联检查` / `:9940` `db.session.delete(customer)` **无守卫** | **本批**（二选一，见 §3） |
| B18-06 ③ 编码规则日志页（G-D） | **未实施** | `models.py:735 class CodeGenerationLog`；写点 `routes.py:6105` + `models.py:1160`；**读点 0**；模板 0 命中；真库 `code_generation_log` **25 行** | **本批**（若做页）或留档 |
| B18-06 ④ `G-K` 三入口职责边界 | **未落文档** | `production_center.py:23`（GET）/`:63`（GET item）/`:95`（POST create_instances）/`:309-313`（`api_execute_operation`） | **本批**（落文档） |

**去陈旧（本盘点实测推翻的旧读数）**

1. **真库 `audit_log` 旁证口径已变**（B13-02 真库整治后）：旧「73 行 / 40 NULL / 其中 10 行 `can_rollback=True`」⇒ 现 `SELECT COUNT(*), SUM(target_id IS NULL), SUM(can_rollback=1 AND target_id IS NULL) FROM audit_log` = **`(74, 41, 0)`**；`can_rollback=1` 共 **24** 行；`rollback_type` 分布 = `NULL 40 / add 25 / delete 4 / edit 5`。**「10 行假可回滚」已归零**。
2. **本件取代的落点**（后续批次已漂移，旧行号勿再引用）：`delete_customer` 区段 `9859/9863/9869/9895` ⇒ **`9905/9908/9915/9940`**（+46/+46/+46/+45）；`CodeGenerationLog` 写点 `routes.py:6066` ⇒ **`:6105`**；P7 守卫 `quality.py:838` ⇒ **`:878`**；P2 载体 `:4945/:5036` ⇒ **`:5499/:5592`**；`api_execute_operation` `production_center.py:309-313` **未漂移**；`models.py:735`、`models.py:1160` **未漂移**。
3. **已落地资产**（任务书点名的两项均在场）：`scripts/_remediate_b13_02_audit_log.py`、`scripts/check_db_url_guard.py`。
4. **已关闭的在册项**（后续批次）：N-2（`B18-登记.md:830`：A-70 三步 + 非作者验证 + 终态复跑 `[PASS] CA4a`、`ui_goods_receipt_option=True`、`ui_options=['product','production_record','material','goods_receipt']`）、N-5（`B18-登记.md` §B18-D-02：合成夹具四场景 + 阴性对照 3/3 转红，解除）、R-2/R-3（`B18-登记.md:839`：随消除关闭；`:858` 明确「**在册 24 条并未清零**」，只 N-2/N-5/R-2/R-3 清零）。
5. **`40-` §4.5 字段清单在 HEAD 现状**（`git status` 无 `M` ⇒ 已提交），但 `:364` 指标行仍 `method_level_non_get=155`、`:396` 仍 `155`，而现钉值 `method_level_non_get_total=158`（`check_doc_claims --list-constants` + `52-…md:29` 同值）。

---

## 1. 产品面 P1–P12（现状 / 判据 / 变红条件 / 归属）

### P1 — 审计行 `target_id` 落 NULL 而 `can_rollback=True`

- **现状（已修，读码）**：不变量函数 `app/main/routes.py:4465 def _assert_add_audit_target(log, action, new_row_id):`，实现体 `:4472-4478`（`if new_row_id is None or log.target_id is None:` ⇒ `logger.error` + `raise AssertionError(detail)`；docstring `:4466-4470` 明写「必须在新行业务行 `flush()` 之后、`commit()` 之前调用」）。调用点 **11 处**：`:3707`（自动创建质检任务）、`:5494`（导入成品）、`:5587`（导入原材料）、`:5750`（添加成品）、`:5856`（添加原材料）、`:5986`（添加编码规则）、`:7727`（添加产品）、`:8428`（批量添加产品）、`:9511`（自动创建生产任务）、`:11409`（添加易耗品）、`:11742`（添加易耗品品类）。质量面：`app/main/quality.py:601 def _assert_add_audit_target` + `:675` 调用（创建质检任务）。
- **数据集侧**：见 §0 去陈旧 1 —— 真库「假可回滚」行已归零。
- **判据**（可复跑，只读）：
  - `grep -c "_assert_add_audit_target" app/main/routes.py app/main/quality.py` ⇒ 期望 `routes.py:12`（1 def + 11 调用）、`quality.py:2`（1 def + 1 调用）。
  - 只读 SQL：`SELECT SUM(can_rollback=1 AND target_id IS NULL) FROM audit_log` ⇒ 期望 `0`。
- **变红条件**：任一 `rollback_type='add'` 审计行的 `target_id IS NULL`；或新增 `add` 类审计写点未接不变量（`AssertionError` 未触发即意味着漏接）。
- **归属**：留档（可用 `r2_audit_probe` 的 E4/E5 做请求面复跑，本轮未跑 ⇒ 该面 `not_measured`）。

### P2 — 缺 f-string 前缀 ⇒ 落库字面量 `第{index+2}行…`

- **现状（已修）**：`app/main/routes.py:5499` 与 `:5592` 均为 `error_messages.append(f'第{index+2}行导入失败，请稍后重试或联系管理员')`（**f 前缀在位**）。
- **判据**（实测命令 + 实测值）：`grep -rn "第{" app --include='*.py' | grep -vE "f['\"]" | grep -v "\.format(" | wc -l` ⇒ **实测 `0`**。其余含 `第{0}页 行{1}` 的命中全部是 `.format()` 合法用法（`app/services/alloy_steel_import_service.py:232/605/610/626`、`app/utils/alloy_steel_bom_converter.py:575`、`app/utils/alloy_steel_price_converter.py:474/519/525/583/594/599/632/653`）。
- **权威探针（未跑）**：`test-reports-2026-10/harness/r2_c08_probe.py:359` `'literal_brace_bug': bool(re.search(r'第\s*\{[^}]*\}\s*行', msg or ''))` ⇒ 复跑期望 `literal_brace_bug=false`（请求面 ⇒ §4 `not_measured`）。
- **变红条件**：上述 grep 计数 > 0，或探针 `literal_brace_bug=true`。
- **归属**：留档。

### P3 — `/employees/import` 整单拒绝违反行级容错

- **现状（已修）**：`routes.py:2093` route / `:2096 def import_employees():`；逐行收集 `error_messages`（`:2221`/`:2231`/`:2244`/`:2249`/`:2280`），成功行提交（`ast` 实测 `commit` 在 `:2285`、`:2293`），`except` 出口 `:2298`；部分成功语义 `:2302 if success_count > 0:` + `:2319-2320 'success': success_count > 0`；**无「发现错误即整体 return」早退分支**。
- **判据**：`grep -n "'success': success_count > 0" app/main/routes.py` ⇒ 期望命中 `:2320`；AST 口径：`import_employees` 内 `commit` 调用存在且被 `if success_count > 0` 包围。
- **变红条件**：出现 `if error_messages: return jsonify(...)` 早于任何 `commit`；或探针实测 `delta_target=0`（3 好 + 2 坏用例）。
- **归属**：留档（请求面复跑 `not_measured`）。

### P4 — 上传残留（`os.remove` 在 `try` 内、无 `finally`）

- **现状（部分修 9/10）**：AST 扫描 `app/main/routes.py` 的 10 个导入端点 ——

  | 端点（def 行） | `finally` | `remove/rmtree` | `commit` |
  | --- | --- | --- | --- |
  | `import_employees:2096` | ✅ | `:2332` | `:2285`/`:2293` |
  | `import_process_prices:2436` | ✅ | `:2749` | `:2607`/`:2697`/`:2705` |
  | `import_alloy_process_prices:2756` | ✅ | `:2799` | — |
  | `import_production_records:2917` | ✅ | `:3024` | `:2979`/`:2998` |
  | `import_bonus_penalties:4131` | ✅ | `:4221` | `:4195`/`:4203` |
  | `import_tasks:4254` | ✅ | `:4341` | `:4315`/`:4323` |
  | `import_products:8313` | ❌ | ❌ | `:8502` |

  `import_products` 走 `:8326 temp_path = save_temp_file(file)`（`tempfile.mkdtemp(dir=TEMP_FOLDER)`），`try:` 开在 `:8328`，**无 `finally`、无 `remove`/`rmtree`** ⇒ 只能等 `@bp.before_request` 的 `cleanup_temp_files()`（mtime > 5 分钟）回收（AGENTS.md 已把「钩子回收」写成既有约定）。
- **判据**：复跑上表 AST 扫描 ⇒ 期望 **10/10** `finally=True`；现状 **9/10**。另：`grep -n "finally:" app/main/routes.py` 在 2096–4341 区间应各端点 ≥1。
- **变红条件**：新增导入端点既无 `finally` 又无显式 `remove`；或 `residue_exists=true`（S4/S5 探针，请求面 ⇒ 本条请求面 `not_measured`）。
- **归属**：**本批**（1 处，或走「显式登记为依赖钩子」路线并同步改 `70-` §10.3 P4 措辞）。

### P5 — 行号覆盖不一致

- **现状（原 2 处载体已修，残余 5 处）**：原载体之「员工工号…不存在」现 `routes.py:4283`、「工序编号…不存在」现 `:4296`，**均带 `第 {index + 2} 行：` 前缀**（同族 `:4289`/`:4312`、`import_bonus_penalties:4161/:4167`、成品/原材料/产品/入库类 `:6950…:7343` 全部带行号）。**残余无行号**：`:2956`（`f"{date_error}（原值：…）"` —— 同族 `:4167`/`:4289` 却带前缀）、`:2963`（`未找到工序 X 在 Y 的价格`）、`:2985` 与 `:4192`（`处理记录时出错: …`）；另 `:2231` 是**换行拼接**的 `append(`，需目视其首行文案。
- **判据**：`grep -n "error_messages.append" app/main/routes.py | grep -v "第"` ⇒ 现状集合 = `{2231, 2956, 2963, 2985, 4192}`。
- **变红条件**：新增/存量用户可见错误文案缺「第 N 行」定位；或该集合扩大。
- **归属**：**本批**（4 条文案，纯字符串前缀，风险最低）。

### P6 — 内层 `except Exception` 吞失败 ⇒ 事务可能部分应用

- **现状（关键块已修）**：`app/main/routes.py:3533 def update_task_status(id):` 内 —— 业务写块已改为 savepoint + 上抛：
  - `:3662 sp_inspection = db.session.begin_nested()`（配 `:3726 except` → `:3781-3786` 注释「`db.session.rollback()` + 500 `success=false`，避免『实扣已发生、计划账未回写』」+ **`raise`**）
  - `:3768 with db.session.begin_nested():` → `:3811-3818`（「避免『替用明细缺失但报工照常提交』」+ **`raise`**）
  - `:3922 with db.session.begin_nested():` → `:3925-3934`（**`raise`**）
  - `:3945 with db.session.begin_nested():` → 出口 `:4028-4034`（**`raise`**）
  - `:3989 with db.session.begin_nested():` → 同上
  - 外层兜底 `:4038-4040 except Exception as e: _reraise_http(e); db.session.rollback()`
  - **残余仅 `warning` 的 3 处（非账务写）**：`:3869-3870`（`触发原材料替用通知失败`，通知副作用；其内层 `:3853-3860` 同族）、`:3962-3963`（`同步生产中心状态失败`，**派生状态轻量同步**，`ProductionBatchItem.status` 推进）、`app/main/production_center.py:351-352`（`except Exception: continue` —— 逐行容错，跳过坏物料行，符合 AGENTS.md 行级容错）。
- **判据（静态口径）**：`update_task_status` 内 `begin_nested()` 计数期望 **5**（现状 5）；每个 `begin_nested` 所在块的 handler 必含 `raise`（现状 5/5 出口均 `raise`）。
- **变红条件**：出现**库存/工价/账务/审计**写入位于无 savepoint 的 `try` 内且 handler 无 `raise`（即 V-12 的 damage 向量实测出现部分应用）。
- **归属**：留档 + 把上述 3 处「只 warning」显式登记为**设计选择**（否则下一轮盘点会重复把它读成缺口）。请求面（damage 向量）⇒ §4 `not_measured`。

### P7 — `04` §2.1 A4 与实现冲突 / 界面下拉无 `goods_receipt`

- **现状（已修）**：守卫 `app/main/quality.py:878 return jsonify({'success': False, 'message': '质检模板类型与任务类型不匹配'}), 400`（原读点 `:838`，漂移 +40）。UI 面 `goods_receipt` 已落地：`app/templates/main/quality/inspection.html:9`、`records.html:31`/`:261`、`print_record.html:53`、`task_detail.html:10`（`'goods_receipt': '来料质检'`）。
- **旁证**：`B18-登记.md:830`（N-2 终态复跑）`ui_goods_receipt_option=True`、`ui_options=['product','production_record','material','goods_receipt']`、`[PASS] CA4a`；判据订正件 = `test-reports-2026-10/B18-C-02-验收判据文档订正-A4模板类型.md`（B14-07 方案 A）。
- **判据**：`grep -n "质检模板类型与任务类型不匹配" app/main/quality.py` ⇒ `:878`；`grep -rl goods_receipt app/templates/main/quality/` ⇒ 4 文件。
- **变红条件**：守卫行消失或 UI 选项回退（`ui_goods_receipt_option=False`）。
- **归属**：留档。

### P8 — `04` §2.2 B2 工序数口径过时（「工序数 × n」）

- **现状（已收口，`docs/` 原文未覆写）**：`test-reports-2026-10/B18-04-订正件-04状态列-REQ状态列-Q4服务名.md`（表行 `:543`、判据值 `:552`、上游登记 `:555`）给出改前/改后行：改后 = 「`task_assignment` +『**工序数**』（**每工序一张**，与 n 无关）」；实测口径 `:551-552`：`n = 2`、`process_count = 3` ⇒ `expected={'status':200,'batch_item_delta':2,'task_delta':3,'process_count':3,'literal_expectation':6}`（`uat-after.out:69` 逐字）。
- **判据**：`grep -n "每工序一张" test-reports-2026-10/B18-04-*.md` ⇒ 命中 `:543`；`grep -c "工序数×n" docs/test-reports/2026-10/04-*.md` ⇒ 仍 >0 属**预期**（历史件不覆写，订正件为唯一现行口径）。
- **变红条件**：订正件丢失，或有人回改 `04` 措辞为「工序数 × n」而未走 A-70。
- **归属**：留档。

### P9 — 报工路径（无工件）报废不产生 scrap 库台账行

- **现状（未修，读码证伪）**：`app/main/production_center.py:309` route / `:313 def api_execute_operation(item_id: int):`，全函数（`:313-397`）**无 `scrap` 关键字、无库存台账写入**；`:3949` 只在 `routes.update_task_status` 里做「`bi.status == 'scrapped'` 终态 ⇒ 本次报工不同步实例状态」的**拒绝型**判断（`:3952-3953` 文案「实例…已报废（终态），本次报工不同步实例状态」）。`app/services/mes_service.py` 侧确有 `scrap` 域口径（`:20` 条目、`:262` docstring「末道通过后入库。`stock_kind`: `fg`/`wip_part`/`failed`/`scrap`」、`:272` 映射 `'scrap': 'scrapped'`、`:300-301 workpiece.status = 'scrap'`）——但**报工路径未接**。
- **判据**：`grep -c "scrap" app/main/production_center.py` ⇒ 期望（修后）>0，现状 **0**；请求面判据 = V12-B6.2 `scrap_rows_delta`（历史实测 **0**）。
- **变红条件**：报工报废后 `scrap_rows_delta=0`（现状即红）。
- **归属**：**本批**（若纳入，需按 `mes_service` 既有 `stock_kind='scrap'` 口径接一次，并配阴性对照）；否则留档并写明「报工报废不进 scrap 台账」的当前口径。

### P10 — `notes` KeyError 掩盖 + 取价口径不一致

- **现状（已修）**：① `app/utils/excel_generator.py:357-358` 显式补键并写注释「保持与路由 `notes=data['notes']` 的键约定一致（缺键会 KeyError 致整批导入失败）」⇒ `'notes': str(row[4].value).strip() if len(row) >= 5 and row[4].value else None`；消费点 `app/main/routes.py:2591`/`:2673`/`:2973`/`:4306`。② 取价单点 `app/main/routes.py:157 def pick_process_price(process_code, business_date):`，docstring `:158-179` 明写「等价语义 = 原 `routes.py:2717-2720`」、「与 `filter_by(process_code=…).first()` 的旧写法相比多做两件事：排除未来价 + 多版本取最新」、无版本返回 `None` 且**调用方不得改抛异常**；调用点 `:2960`、`:4174`、`:4294`；`app/utils/excel_generator.py:897-902` 延迟导入复用（注释「不再另留 `is_current` 第三口径」，产品导入无业务日期 ⇒ 业务日 = 导入当日）。
- **判据**：`grep -n "def pick_process_price" app/main/routes.py` ⇒ `:157`；`grep -rn "pick_process_price" app/ | wc -l` ⇒ 期望 6（1 def + 3 路由调用 + `excel_generator.py` 1 import + 1 调用）；`grep -n "'notes':" app/utils/excel_generator.py` ⇒ 命中 `:358`。
- **变红条件**：`parse_production_record_data` 输出缺 `notes` 键；或出现第四处取价写法（`is_current`/裸 `filter_by(...).first()`）。
- **归属**：留档。

### P11 — 仓库根污染 6 个 `.tmp_v15_*.{out,err}`

- **现状（已消除，不可复现）**：`ls -la .tmp_v15_*` ⇒ `No such file or directory`；`ls -a | grep -i tmp` ⇒ 仅 `.tmp/`（未跟踪目录）。`git status --porcelain` 全 7 行中无 `.tmp_v15_*`（这 6 个文件当时即 `??` 未跟踪，删除后不留 git 痕迹）。`grep -rn "tmp_v15" test-reports-2026-10/*.md` 仅命中 `70-` 自身的原始记录（`:126`/`:174`/`:323-326`），**无处置登记件**。
- **判据**：`ls .tmp_v15_* 2>&1` ⇒ 期望 `No such file or directory`；`git status --porcelain | grep -c "\.tmp_v15_"` ⇒ 期望 `0`。
- **变红条件**：根目录再现 `.tmp_v15_*`（或任何未被 `.gitignore` 覆盖的根级 `.tmp_*` 产物）。
- **归属**：留档 —— 状态须写成「**已消除（不可复现）**、无处置登记」并**不得折算 pass**（原缺陷的复现条件已不可构造）。

### P12 — N-1 修好后两下游资产变红/陈旧

- **现状（已修 2/2）**：
  - `test-reports-2026-10/harness/reconcile_r2.py`：`:324 COVERAGE_DRIFT = 'test-reports-2026-10/harness/coverage_drift.py'`；`:328-330` 注释「B17-11 / A-114：必须显式 `--coverage <run 产物>`；缺参 = exit 2（用法错误，不是回归）」；判据实现 `:593-594 chk_subprocess([PY, '-B', COVERAGE_DRIFT, '--coverage', run_coverage_artifact()], '漂移判据 exit 0（B17-11：显式 --coverage <run 产物>；缺参 = exit 2 用法错误）')`。
  - `test-reports-2026-10/harness/r2_v14_ledgerbook.py:257-262`：`'command'` 现为 `…coverage_drift.py --coverage %s/coverage.json；…`（`RUN_DIR_REL` 注入），`:263 'exit_code': 0`。
- **判据**：`grep -n "\-\-coverage" test-reports-2026-10/harness/reconcile_r2.py test-reports-2026-10/harness/r2_v14_ledgerbook.py` ⇒ 期望命中 `reconcile_r2.py:593-594`、`r2_v14_ledgerbook.py:260`。
- **变红条件**：任一处回退为无参调用 `coverage_drift.py`（今 ⇒ exit 2，会被误读成回归）。
- **归属**：留档。

---

## 2. 资产/口径面 G-12…G-22（现状 / 判据 / 变红条件 / 归属）

| 条目 | 现状（HEAD 现场） | 判据（命令 + 期望） | 变红条件 | 归属 |
| --- | --- | --- | --- | --- |
| **G-12** | `final_recount.py` 已按权威源绑定（`B18-05:103`：`:384` 注释「期望值一律绑定权威源（改前 `141/101/155/6/14` 留档见 `82-` 登记件）」、`:451-452` 明写旧自持值与 `coverage_drift.LOCKED(108/116/0)` 互斥，文件 `62+/6−`）。**残余**：`test-reports-2026-10/40-第2轮实测Runbook与台账规范.md:364` 指标行仍 `method_level_non_get=155`、`:396` 表仍 `155`；现钉值 = **158**（实测 `/opt/wage-venv/bin/python -B scripts/check_doc_claims.py --list-constants` 第 10 行 `method_level_non_get_total 钉值=158`；`52-V13-…md:28` 同为 `158`）⇒ **差 +3**。该表 `:364` 另有 `rules=271`、`smoke_plan=148` 两项，其对应钉值（`rules_total`/`smoke_targets`）本轮**未逐项取值比对** ⇒ 该两字段标 `not_measured`（解除条件：取 `check_doc_claims --list-constants` 同名键后比对）。`scripts/check_doc_claims.py` 内**无**对 `40-` 这些数值的钉常量（`grep -n "40-" scripts/check_doc_claims.py` ⇒ 0 命中）⇒ 该表**不在机检覆盖内**。`harness/analysis_ledger.py`、`harness/improve_plan.py` 两件均在仓内（`improve_plan.py:141` docstring「行号以实测为准并回写」），其内部行号/claim 的逐条现况本轮未核。 | `grep -n "method_level_non_get" test-reports-2026-10/40-*.md` ⇒ 期望 `364/396` 为 `158`（现状 `155`）；`/opt/wage-venv/bin/python -B scripts/check_doc_claims.py --list-constants` ⇒ 期望「口径键登记表（29 条）」（现状 29 条；`81-:516` 记 B18-03 时为 20 条 ⇒ 已扩容） | 文档数值 ≠ 钉值且无订正标注；或 `check_doc_claims` 出现 `DRIFT` 于**非 `coverage.json` 依赖键** | **本批**（`40-` 两处，引用口径）或留档 |
| **G-13** | V-03/V-05/V-06/V-07 探针本轮**未复跑**（`70-` §9.1 G-13 的 `not_covered` 理由 = A-40 须 preflight、A-98 并发风险）。`B18-05` 中 V-03/V-05/V-06/V-07 的唯一命中（`:103`）讲的是 `final_recount` 的 `101/141` 同步，**不是**探针复跑记录。 | 无可复跑判据（不得伪造）；解除条件见 §4 | —— | 留档（`not_covered` 保持） |
| **G-14** | N-14「同 run 51 个修订版探针产物无 `superseded_by`」：现 `grep -rl superseded_by test-reports-2026-10/evidence \| wc -l` = **22** 个文件带该字段 ⇒ 处置面远小于 N-14 的 51 条；**51 条逐产物清单未逐条核对**（⇒ 不得据此判已收口）。 | 上述 `grep` 计数（现状 **22**）；逐条面需 V-16 §6-N-1 的 51 条清单对表 | 修订版产物仍可被下游读成现行值（无 `superseded_by` 且文件名同形） | 留档（`not_measured` 部分） |
| **G-15** | 判据面按 `B18-登记.md` §B18-D-01 裁决④「已收口（可改判 `completed`）」，但**证据载体缺失（N-D1）**：`test-reports-2026-10/evidence/harness/r2-v13-tl050607`、`…/ci-v13-gate`、`test-reports-2026-10/evidence/harness/coverage.json` **三者实测均 `No such file or directory`**。工具侧口径表在场：`52-V13-TL050607-工具链收尾.md:26-45` 与现钉值逐项同值（`rules_total=273` …）。 | `ls -d <上述三路径>` ⇒ 期望三者存在（现状三者缺失）；口径表逐项与 `check_doc_claims --list-constants` 同值（现状同值） | 判据被引用而载体不存在（即现状） | 留档：`not_counted_as_passed`（判据面可 `completed`，**证据载体面不得折算 pass**） |
| **G-16** | ①「显式传锚点仍 exit 1」：根因已在档 `test-reports-2026-10/harness/coverage_drift.py:52-79` —— `:52` 问题陈述（原缺省值 = 冻结锚点 `evidence/harness/coverage.json`）、`:62` 新行为「缺 `--coverage` 即 fail loud」、`:69` 「冻结锚点已按 **A-70 第 ① 步**在同一路径重生成，覆盖读数由『旧值稿』`6/14/101` 变为 `108/116/0`」、`:75` 后值 `244575 B`。**但锚点文件本体在本容器缺失**（同 N-D1）⇒ 显式传锚点实测**不可做**。②下游两资产 = **P12 已修 2/2**。 | ①`/opt/wage-venv/bin/python -B test-reports-2026-10/harness/coverage_drift.py --coverage <锚点>` ⇒ 期望 `exit 0`（**未跑**：文件缺失）；`… --selftest` ⇒ 期望 `9/9` `exit 0`（未跑）②同 P12 判据 | 显式传锚点仍 `exit 1`（锚点读数 ≠ `LOCKED`）；或下游回退无参调用 | 留档（① 改判为「根因已消、待实测」，② 可关闭） |
| **G-17** | `40-` §4.5 字段清单：工作区版**已入 HEAD**（`git status --short` 无 `M test-reports-2026-10/40-*`；历史提交 `2c98292 docs(40): §4.5 N-1 漂移字段同步`）⇒ 「工作区版未提交」一条**已消**。残余 = `:364`/`:396` 数值 `155`（同 G-12）。 | 同 G-12 判据 + `git status --porcelain -- test-reports-2026-10/40-*` ⇒ 期望空 | 数值与钉值不一致且无订正标注 | **本批**（与 G-12 合并为一条引用口径项） |
| **G-18** | 改动面**仍在增长**：`git ls-files \| wc -l` = **647**；`find test-reports-2026-10/evidence -type f \| wc -l` = **2419**（`B18-登记.md` §B18-D-01 记 **1974** ⇒ **+445**；**本件两次测量间 2396→2419**，并行线仍在写）；`find .tmp -type f \| wc -l` = **293**；`git status --porcelain \| wc -l` = **9**（`?? .tmp/`、`?? .vscode/settings.json`、`?? app.db.evidence-ALLOY-IMPORT-02-20261009_004539`、`?? instance/`、`?? test-reports-2026-10/.tmp-t6runs/`、`?? test-reports-2026-10/.tmp-t9runs/`、`?? test-reports-2026-10/C-落点与在册项盘点.md`（本件）、`?? test-reports-2026-10/C-注入面与锚点实测.md`、`?? test-reports-2026-10/C-资产与口径订正.md`（后两件为**并行 C 线**的在制品））。 | 上列 4 条计数命令（现状如上） | 收口件引用的计数与现场不一致（即当前状态） | 留档：收口时必须**同时**记「计数 + 时点 + HEAD」 |
| **G-19** | C-06 写端点 deny 面**已实现于同一工具**（符合 AGENTS.md「须在同一工具内加方法参数化 face，不得新起并行工具」）：`scripts/permission_matrix.py:440 def write_endpoints(app, guards, capability):`、`:469 def run_write_face(found_by_module, clients, roles_for, ids):`、`:527 def print_write_face(...)`（含 `:544-548` 注入面回显）、`:669-671` 主流程调用 + `write_failures`、`:691` 落盘 `write_summary`、`:716` 汇总行。 | `grep -n "def write_endpoints\|def run_write_face\|write_summary" scripts/permission_matrix.py` ⇒ 期望非空（现状 `:440`/`:469`/`:691`） | 写面回到「只扫 GET」而未登记 | 留档（**实跑面** = §4 `not_measured`） |
| **G-20** | 两个分母已收敛为**一个**：`test-reports-2026-10/harness/api_matrix.py:753-756` 注释「B18-08 / A-69：CSRF 判据**不再断文案**（统一 `errorhandler` 已换掉 `CSRFError` 文案，旧文案判据漏判了 **24 条**真被拦下的请求）。稳定标记：`CSRFProtect` 的 `csrf_protect` … `preprocess_request` 遇非 None 返回值/异常即短路」；判据实现 `:796-848`（`n_w`/`n_ok`/`n_bad` 单一分母 + `:837 summary={'probed','enforced_or_exempt','not_enforced'}` + `:838-848` 可观测性守卫「哨兵一次都没跑过 ⇒ CSRF 判据不可观测」）。原 `:808-809` 处现为 URL 模板兜底（`re.sub(r'<int:\w+>', …)`），**已无 24 条文案判据**。 | `grep -n "不再断文案" test-reports-2026-10/harness/api_matrix.py` ⇒ 命中 `:753`；单分母：`grep -c "n_bad += 1" …` ⇒ 单点 | 文案型判据回归或出现第二分母 | 留档 |
| **G-21** | 「37 条『GET+写』多方法规则未命中」：`52-…md:13-14` 现场一句「`rules_total` 273→272 与多方法面 **44/38→43/37** 属同一触发项、已在上一轮重基线中按现场写入」。与钉值 `non_get_uncovered_method_level = 40`（`52-:30`）**量纲不同**（37 = 多方法规则面；40 = 方法级非 GET 未命中），**不得互替**。`api_matrix.py` 覆盖行口径 = `methods_probed_non_get / methods_not_probed_non_get / total_non_get`（`:662-669`）。 | `api_matrix.py` 的 `[覆盖] 非 GET 方法级被探针实际命中 x/y（未命中 z）` 行（**未跑**，请求型） | 覆盖行读数与 `52-` 现场值不一致 | 留档（`not_measured`，解除条件见 §4） |
| **G-22** | 同 P11：`.tmp_v15_*` **已消除**，无处置登记件。 | 同 P11 判据 | 同 P11 | 留档（不得折算 pass） |

---

## 3. B18-06 治理条（`81-后续开发与测试规划.md:519` / 验收 `:535`）

**计划原文口径**（`:519`）：治理可做项 + 待拍板登记 = `delivery_batches` 对照视图口径说明、客户删除关联校验（G-E 默认路径）、编码规则日志页、`G-K` 三入口职责边界落文档；落点写 `routes.py:9258-9296 delete_customer`（`:9267-9268` TODO）、`models.py:732 CodeGenerationLog`、`production_center.py:309`。
**验收口径**（`:535`）：三条治理项各给口径说明或默认路径；G-E 按「禁止删除有订单客户」实现（或显式保持现状并改措辞）；阳性对照 = 删除有订单客户 ⇒ 400 + 提示（若实施）；阴性对照 = **现状 ⇒ 允许裸删（`routes.py:9293`）**；若暂不实现 ⇒ 默认路径措辞**必须**改为「保持现状（允许删除）」。

| 子项 | 现状（HEAD 现场） | 判据 | 变红条件 | 归属 |
| --- | --- | --- | --- | --- |
| ① `delivery_batches` 对照视图口径说明 | **未做**：`B18-05-批次收口台账.md:85` 表行「`delivery_batches` 对照视图口径 / — / **本会话未复核该项** / 标 `not_measured`，不得折算 pass」；`:260` 同义；`:437`「B18-06 四项治理 = 只核查现状，未改业务代码…其中 `delivery_batches` 视图口径 `not_measured`」。视图本体在场：`routes.py:10705`/`:10708 manage_delivery_batches_page`、`:10717`/`:10721 manage_delivery_batches`（`:10737 order_item.set_delivery_batches(batches)`、`:10765 'batches': order_item.delivery_batches_list`）、模板 `app/templates/main/delivery_batches.html`（「分批到货管理」页）。 | 期望 = 一份**口径说明**（源字段、与 `sales_order_item` 的对照关系、`set_delivery_batches` 的写入语义）+ 可复跑读取命令；现无 | 无口径说明而把该项当已收口 | **本批**（读码即可产出，最省） |
| ② 客户删除关联校验（G-E） | **未实施（现状 = 允许裸删）**：`routes.py:9905` route（`DELETE /customer/<int:customer_id>/delete`）/ `:9907 @require_capability('customer.delete')` / `:9908 def delete_customer(customer_id):` / `:9914-9915 # 检查是否有关联的订单或其他业务数据` + `# TODO: 添加订单关联检查`（**注释占位，无代码**）/ `:9928-9938 AuditLog(can_rollback=True, rollback_type='delete', target_model='Customer', target_id=customer.id)` / `:9940 db.session.delete(customer)`（**无条件**）/ `:9941 commit` / `:9945-9948 except → _reraise_http(e); rollback; 500`。真库侧：`customers` **1** 行；相关表在场 `sales_orders`/`sales_order_items`/`production_orders`/`customer_addresses`。 | 阳性对照（若实施）= `DELETE` 有订单客户 ⇒ **400 + 提示**；阴性对照（现状）= **允许裸删**（`:9940` 前无任何 `SalesOrder.query`/`ProductionOrder.query` 守卫）。复跑需请求面 ⇒ §4。 | 实施后仍允许删除有订单客户；或未实施却把措辞写成「已校验」 | **本批**（二选一：①实施守卫 + 阳性/阴性对照；②保持现状 ⇒ 把 `70-`/`81-` 默认路径措辞改为「**保持现状（允许删除）**」并留档） |
| ③ 编码规则日志页（G-D） | **未实施**：模型 `app/models.py:735 class CodeGenerationLog(db.Model):`（**未漂移**）；写点 2 处 = `app/main/routes.py:6105 log = CodeGenerationLog(`、`app/models.py:1160 log = CodeGenerationLog(`；**读点 0**（全仓 `grep -rn CodeGenerationLog app/` 仅 4 命中 = 1 处 import + 2 处写 + 1 处模型定义）；模板面 `grep -rl "编码生成日志\|CodeGeneration\|编码规则日志" app/templates/` ⇒ **0 命中**。真库 `code_generation_log` 已有 **25** 行数据（写侧在跑，读侧无出口）。 | `grep -rn "CodeGenerationLog" app/ --include='*.py' \| wc -l` ⇒ 期望含**读点**（现状 4 = 定义 + import + 2 写）；`grep -rl CodeGenerationLog app/templates/` ⇒ 期望非空（现状空） | 写点继续增长而读点长期为 0（现状）；或页面存在却无权限登记 | **本批**（若做页；否则留档并写明「写而不可读」的当前口径） |
| ④ `G-K` 三入口职责边界落文档 | **未落文档**：`app/main/production_center.py:23 @bp.route('/production_center', methods=['GET'])`、`:63 @bp.route('/production_center/items/<int:item_id>', methods=['GET'])`、`:95 @bp.route('/api/production_center/create_instances', methods=['POST'])`、`api_execute_operation` = `:309` route / `:310-312` 装饰器（`@login_required`、`@require_capability('production_center.use')`、`@csrf.exempt`）/ `:313 def`（**与 `81-:519` 记的 `:309` 一致，无漂移**）。其余相关入口：`:179 tech_decomposition`（POST）、`:229 detail`（GET）、`:400 /api/production/generate-codes`（POST）。 | 期望 = 一份职责边界文档（三入口：页面 / 实例详情 / 建实例 API，各自可写域与前置校验）+ `file:line`；现无 | 边界仅存于代码、无文档载体（现状） | **本批**（落文档，`docs/**` 不可覆写 ⇒ 新建件） |

---

## 4. 本轮**未做**的面（`not_measured` / `not_covered`）与解除条件

| 未做的面 | 状态 | 为什么未做 | 解除条件（可判定） |
| --- | --- | --- | --- |
| 请求型复跑（`r2_c08_probe` P2、`r2_audit_probe` P1 E4/E5、V-12 damage 向量 / P6、V12-B6.2 P9、`uat_chains` P8 复核） | `not_measured` | 任务书硬约束：**不跑请求型脚本**（`smoke_test`/`permission_matrix`/`functional_test`） | 在 `scripts/_test_bootstrap.make_app()` + 副本 `DATABASE_URL` 下逐探针复跑，留存 run 目录与退出码 |
| G-13 V-03/V-05/V-06/V-07 复跑 | `not_covered` | A-40 要求 `regression_preflight` 前置、A-98 并发风险 | 先跑 `harness/regression_preflight.py`，再逐探针复跑并留档读数 |
| `permission_matrix` 写面（C-06 deny）实跑 / `api_matrix` 覆盖行（G-21） | `not_measured` | 二者均为请求型工具 | `python -B scripts/_sandbox_compat.py scripts/permission_matrix.py --no-dump`（写面纳入）与 `api_matrix.py` 覆盖行实读，二者 `exit 0` |
| G-15 证据载体（N-D1） | `not_counted_as_passed` | 三个载体文件在本容器不存在 | 取回/重建 `evidence/harness/{r2-v13-tl050607,ci-v13-gate,coverage.json}` 并复跑 V-13 两件 + `ci_gates --phase first` |
| G-16 显式传锚点 `exit 0` | `not_measured` | 锚点文件缺失（同上） | 同上一行的载体取回后，`coverage_drift.py --coverage <锚点>` ⇒ `exit 0` |
| G-14 51 条逐产物核对 | `not_measured` | 需 V-16 §6-N-1 的 51 条清单逐条对表（本件未逐条） | 按清单逐条核 `superseded_by`，缺者补 |
| B18-06 ② 阳性/阴性对照实跑 | `not_measured` | 请求面 | 见 §3 ② 的对照定义 |
| 本件未覆盖的 PG 面（`postgresql+psycopg2://…` 实例） | `not_measured` | 本轮只读 SQLite 真库；PG 面属 B18-Q1b/Q2 记录（`app→web` 服务名等） | 按 `B18-登记.md` §B18-Q1b 口径在 PG 临时库复跑 |

---

## 5. 建议归属汇总

**本批可做（读码/文案级，风险最低）**
1. P5 残余 4 条文案补「第 N 行」（`:2956`/`:2963`/`:2985`/`:4192`）+ 目视 `:2231` —— 纯字符串前缀。
2. P4 `import_products:8313` 补 `finally`（或按 B18-05 先例显式登记「依赖 `cleanup_temp_files()` 钩子」并同步改 `70-` §10.3 P4 措辞）。
3. B18-06 ① `delivery_batches` 对照视图口径说明（读码即可）。
4. B18-06 ④ `G-K` 三入口职责边界落文档（新建件，`docs/**` 不覆写）。
5. G-12 + G-17 合并的引用口径项：`40-…md:364`/`:396` 的 `155` ⇒ `158`（或加「时点：B18-Q1 前」标注）。
6. B18-06 ② 二选一（实施守卫 + 双对照，或把默认路径措辞改为「保持现状（允许删除）」）。
7. P6 残余 3 处「只 warning」显式登记为设计选择（防下一轮重复读成缺口）。

**必须留档（不得折算 pass）**
- P9（未修，读码证伪）、P11/G-22（已消除但不可复现、无处置登记）、G-13（`not_covered`）、G-14（51 条未逐条）、G-15（载体 N-D1 缺失）、G-16①（待实测）、G-18（计数仍在增长）、G-21（`not_measured`）、§4 全部请求型面。

**建议：需要拍板的**
- B18-06 ③ 编码规则日志页：真库已有 25 行写侧数据而**读点为 0** ⇒ 「做页」与「保持写而不可读」二选一，后者须写进口径。
- B18-06 ② 与上同族的「默认路径」措辞裁定（`81-:535` 已给二选一，尚无裁定记录）。

---

## 6. 复现命令清单（全部只读；本件所有读数均由下列命令取得）

```bash
cd /root/code/MyERP
# 真库三值（开工/收工各一次；本件两次恒等）
sha256sum app.db && stat -c '%s %y' app.db

# P1 不变量覆盖
grep -c "_assert_add_audit_target" app/main/routes.py app/main/quality.py
/opt/wage-venv/bin/python - <<'PY'
import sqlite3; c=sqlite3.connect("file:app.db?mode=ro",uri=True).cursor()
print(c.execute("SELECT COUNT(*),SUM(target_id IS NULL),SUM(can_rollback=1 AND target_id IS NULL) FROM audit_log").fetchone())
print(c.execute("SELECT rollback_type,COUNT(*) FROM audit_log GROUP BY 1").fetchall())
PY

# P2 缺 f 前缀实例（期望 0）
grep -rn "第{" app --include='*.py' | grep -vE "f['\"]" | grep -v "\.format(" | wc -l

# P4 十端点 finally 审计（AST 口径）
/opt/wage-venv/bin/python -B - <<'PY'
import ast
eps={'import_employees','import_process_prices','import_alloy_process_prices','import_bom_alloy','import_production_records','import_bonus_penalties','import_tasks','import_finished_inventory','import_raw_inventory','import_products'}
t=ast.parse(open('app/main/routes.py',encoding='utf-8').read())
for n in ast.walk(t):
    if isinstance(n,ast.FunctionDef) and n.name in eps:
        print(n.name, n.lineno, bool([x for x in n.body if isinstance(x,ast.Try) and x.finalbody]))
PY

# P5 无行号错误文案集合
grep -n "error_messages.append" app/main/routes.py | grep -v "第"

# P12 / G-16② 显式 --coverage
grep -n "\-\-coverage" test-reports-2026-10/harness/reconcile_r2.py test-reports-2026-10/harness/r2_v14_ledgerbook.py

# G-12 / G-17 引用口径
grep -n "method_level_non_get" test-reports-2026-10/40-第2轮实测Runbook与台账规范.md
/opt/wage-venv/bin/python -B scripts/check_doc_claims.py --list-constants

# G-15 / G-16① 载体存在性
ls -d test-reports-2026-10/evidence/harness/r2-v13-tl050607 test-reports-2026-10/evidence/harness/ci-v13-gate test-reports-2026-10/evidence/harness/coverage.json

# G-18 改动面计数
git ls-files | wc -l; find test-reports-2026-10/evidence -type f | wc -l; find .tmp -type f | wc -l; git status --porcelain | wc -l

# G-19 / G-20 工具面
grep -n "def write_endpoints\|def run_write_face\|write_summary" scripts/permission_matrix.py
grep -n "不再断文案" test-reports-2026-10/harness/api_matrix.py

# B18-06 落点
grep -n "delete_customer\|TODO: 添加订单关联检查\|db.session.delete(customer)" app/main/routes.py
grep -rn "CodeGenerationLog" app/ --include='*.py' --include='*.html'
grep -n "@bp.route" app/main/production_center.py

# P11 / G-22
ls .tmp_v15_* 2>&1; git status --porcelain | grep -c "\.tmp_v15_"
```

---

## 7. 本件指纹

| 项 | 值 |
| --- | --- |
| 路径 | `test-reports-2026-10/C-落点与在册项盘点.md` |
| 类型 | **唯一新增文件**；未覆写 `docs/**` 与 `test-reports-2026-10/**` 任何既有件 |
| 行数 / 字节 / SHA256 | 见本件**末行**（指纹不可自指 ⇒ 末行给出「`head -n -1`／本行之前全部内容」口径的行数/字节/SHA256 与复算命令） |
- **指纹（末行；自指不可行 ⇒ `head -n -1` 口径 = 本行之前的全部内容）**：本件共 **313 行**（末行即本行）；`head -n -1` 输出 **312 行**、字节 = **44537**、SHA256 = **`405A73BA65EE66B1FA12302BF33329E5926CAB6E461374B8162F9BBAD1494C32`**。复算：`head -n -1 test-reports-2026-10/C-落点与在册项盘点.md | sha256sum`（期望 `405a73ba65ee66b1fa12302bf33329e5926cab6e461374b8162f9bbad1494c32`）、`… | wc -c`（期望 44537）、`wc -l < …`（期望 313）。
