# ALLOY-IMPORT-02 真库锚点重基线登记 —— 「合金钢辙叉计件工价标准 + 48页表格 BOM」正式写入真实库（A-70「有意更新三步」）

> **本件性质（append-only 登记件）**：只允许**追加**新条目，不得改写既有段落、不得删除既有读数。
> 所有读数均为**现场复跑自证**，格式 =「工具 + 口径 + 值 + 时点」。
> 仓库根 = `D:\workspace\wage_management_system - bak`；解释器 = `F:\Miniconda\envs\wage\python.exe`；
> 现场时点 = **2026-10-09 00:44–00:5x**（备份戳 `004428` / `004433` / `004503` / `004525`）。

---

## 0. 一句话结论

用户裁定「**A 清旧后导入** + **写入真实 `app.db`（先备份）**」后，本任务把合金钢辙叉的两份数据源
正式导入真实库：工价 **3534** 条（2907 普通 / 627 小计，含 3507 条小计关系）、BOM **48** 个父件 /
**1033** 个子件 / **1728** 条明细；同时清掉早先经 10 列模板导入的 **3486** 条旧编号工价与 **2906** 条旧
小计关系，并把 **22** 行引用改指到新编号（残留外键引用 **0**）。
真实库锚点由 `2531328 B / F5DA2306…0E0F065` → **`3035136 B / 4EB632A4…FA43`**，按 A-70 三步把
**4 处活体判据**同步并附**旧值必红的阴性对照**。**未**跑 `evidence_hash.py --freeze`、**未**重生冻结锚点、
**未**新增路由、**未**改 `app/**` 业务代码（本轮只改判据/期望串与登记件）。

---

## 1. 触发项 ID 与授权来源

* 触发项 ID：**ALLOY-IMPORT-02**（ALLOY-IMPORT-01 = 同一功能的「基线接入」，见
  `test-reports-2026-10/B14-00-基线推进登记-合金钢.md` 与 `harness/coverage_drift.py` 的 A-70 记录块）。
* 授权：用户明确裁定 —— ① 旧工价处理 =「**A 清旧后导入**」（备份 → 22 行引用按自然键改指 → 删旧
  3486 工价 + 2906 小计关系 → 导入新 3534 工价 + BOM）；② 写入目标 =「**写入真实 `app.db`（先做
  `app.db.bak` 备份）**」。
* 纪律边界：① 不得用 `process_code LIKE 'YHGH%'` 当删除判据（新旧编号同前缀）⇒ 全程用**备份时刻的
  id 快照**；② 改指无法唯一映射时**中止且不删任何行**；③ 冻结历史件（`harness/final_recount.py`、
  `harness/reconcile_r2.py`、`reconcile-2026-10-08/*`、带日期 markdown 报告）一律不动。

---

## 2. 执行载体与操作步骤（真实库）

| # | 步骤 | 载体 / 事实 |
| --- | --- | --- |
| S-0 | 备份真实库 → `app.db.bak-20261009_004525`（2531328 B / `F5DA2306…0E0F065`） | `.tmp/run_real_import.py` 步骤 0 |
| S-1 | 工价导入（`import_price_result(dry_run=False)`）：3534 条、错误 0 | stdout `步骤1 工价导入 = {"total_rows": 3534, "normal_created": 2907, "subtotal_created": 627, "groups_created": 3507, "success": true}` |
| S-2 | 旧工价快照 3486 条的引用改指（9 个 FK 列中排除 `process_price_group`，其随旧行一并删除）：**22 行**（`process_assignment_rules` 1 + `product_processes` 3 + `task_assignment` 18） | stdout `可唯一映射的旧 id = 8 / 8`、`步骤2 改指行数 = 22` |
| S-3 | 删旧：`ProcessPriceGroup` 2906 条 + `ProcessPrice` 3486 条 | stdout `步骤3 删除 小计关系 2906 条 / 工价 3486 条` |
| S-4 | BOM 导入（`convert_bom_files` + `import_bom_result(replace_existing=True)`）：48 文件 / 3074 行 | stdout `步骤4 BOM 导入 = {"file_count": 48, "total_rows": 3074, "parents_created": 48, "children_created": 1032, "bom_rows_created": 1728, "success": true}` |
| S-5 | 复核 + 审计：指向 `process_price.id` 的 9 个 FK 列对旧 id 引用 **归零**；新增 `AuditLog(action='清理旧合金钢辙叉工价并重指向（ALLOY-IMPORT-01）', can_rollback=False)` | stdout `步骤5 残留引用 = {}` |
| S-6 | 结束指纹：`结尾 sha256=4EB632A48F1C7E8A13BCE8F6263D587A1958D01CC84E37A0D4359E1506DDFA43 bytes=3035136` | 同上 |

* 产物：`.tmp/real_import.out.txt`（3618 B）、`.tmp/real_import.err.txt`（1306 B，仅 openpyxl
  `DrawingML support is incomplete…` UserWarning）、`.tmp/real_import_report.json`（2294 B）。
* 两次失败尝试（均**未删任何行**、已回滚，留档）：`app.db.bak-20261009_004428`、`004433`、
  `004503` —— 失败原因分别是 ① `.tmp/` 在 `sys.path` 首位导致 `No module named 'app'`；
  ② 引用推导误含 `process_price_group` 两列 ⇒ `可唯一映射 790/3474`；③ 映射索引同时含旧行与新行
  ⇒ `可唯一映射 0/8`。修法：排除 `process_price_group`、映射只允许落在「新行」（`r.id not in old_id_set`）。

---

## 3. 真实库锚点：旧值 → 新值（本触发项的核心）

| 项 | 旧值（导入前锚点） | 新值（导入后锚点） | 时点 / 证据 |
| --- | --- | --- | --- |
| 字节数 | 2531328 | **3035136** | `Get-Item app.db` ⇒ mtime `2026-10-09 00:45:39` |
| SHA256 | `F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065` | **`4EB632A48F1C7E8A13BCE8F6263D587A1958D01CC84E37A0D4359E1506DDFA43`** | `Get-FileHash app.db -Algorithm SHA256` |
| 降级登记 | 旧值改记为「**导入前锚点**」 | — | 回滚源 `app.db.bak-20261009_004525`（字节级等于旧锚点） |

### 3.1 表计数（before → after）

| 表 | 步骤 0（before） | 步骤 1 后 | 步骤 3 后 | 终态（after） |
| --- | --- | --- | --- | --- |
| `ProcessPrice` | 3486 | 7020 | 3534 | **3534** |
| `ProcessPriceGroup` | 2906 | 6413 | 3507 | **3507** |
| `Product` | 1 | 1 | 1 | **1081** |
| `ProductBOM` | 0 | 0 | 0 | **1728** |
| `ProductProcess` | 3 | 3 | 3 | **3** |
| `AuditLog` | 73 | 74 | 74 | **76** |

* 口径核对：`Product 1081 = 原 1 + 48 父件 + 1032 子件`；`AuditLog 76 = 73 + 工价导入 1 + BOM 导入 1 +
  清理/改指 1`。三项互为交叉验证，不是单一读数的孤证。

---

## 4. A-70 同批有意更新（4 处活体判据）

| # | 文件:行 | 旧值 → 新值 | 说明 |
| --- | --- | --- | --- |
| L-1 | `test-reports-2026-10/harness/_env.py:48` `REAL_DB_SHA256_EXPECTED` | `F5DA2306…0E0F065` → `4EB632A4…FA43` | 单一声明源；`assert_real_db_untouched()`、`evidence_hash` 的 `real_db_matches_pinned`、`measure_coverage`、`fixtures`、`t9_regression` 等全部经此常量取用 |
| L-2 | `test-reports-2026-10/harness/t6_ledger_check.py:35` `PINNED_DB_SHA` | 同上 | 与 `_env` **交叉断言**（该文件 `:182-184`）⇒ 必须同改 |
| L-3 | `test-reports-2026-10/harness/ci_gates.py:692`（`check_db_bootstrap` 期望串） | `直接拷贝 6712 行，跳过 0 张表` → `直接拷贝 10172 行，跳过 0 张表` | `scripts/check_db_bootstrap.py:71` 把**真实 `app.db` 当种子库**拷贝 ⇒ 行数随真库变化；`种子库账号数 = 64` 不变 |
| L-4 | `test-reports-2026-10/harness/run_gates.py:57` `EXPECTED['bootstrap_copied_rows']` | `6712` → `10172` | 期望值单一存放点（`bootstrap_accounts 64` / `bootstrap_skipped_tables 0` 不变） |

* 行数推导（交叉验证）：`6712 − 3486 − 2906 + 3534 + 3507 + 1080 + 1728 + 3 = 10172` ✓
  （减旧工价、减旧小计关系、加新工价、加新小计关系、加净增产品 `1081−1`、加 BOM 明细、加审计 3 条）。
* **不改**的历史件（同值但属冻结留档）：`harness/final_recount.py:41/327`、`harness/reconcile_r2.py:94`、
  `harness/analysis_ledger.py:41`、`harness/improve_plan.py:40`、`reconcile-2026-10-08/*.py`（5 个探针）、
  以及 `docs/**`、`test-reports-2026-10/**`、`docs/test-reports/**` 下约 200 处带日期的 markdown/JSON 证据。
* 未跑：`evidence_hash.py --freeze`（严禁）；冻结锚点 `evidence/harness/coverage.json` **未重生**
  （其口径为路由覆盖，不含真库哈希，本次无须动）。

---

## 5. 命令（三条，仓库根目录，绝对路径解释器）

```
① & 'F:\Miniconda\envs\wage\python.exe' -B scripts\check_db_bootstrap.py
     ⇒ 期望 `种子库账号数（经自举导入到空库）= 64` + `直接拷贝 10172 行，跳过 0 张表` + exit 0
② & 'F:\Miniconda\envs\wage\python.exe' -B test-reports-2026-10\harness\ci_gates.py --phase first
     ⇒ 期望 exit 0 / steps=15 / 无 blocking 与 report-only 失败
③ & 'F:\Miniconda\envs\wage\python.exe' -B test-reports-2026-10\harness\ci_gates.py --phase first --only evidence_hash
     ⇒ 期望 exit 0（`real_db_matches_pinned == true`）
```

---

## 6. 阴性对照（旧值必须报红）

| # | 对照 | 实测 |
| --- | --- | --- |
| N-1 | 把 `_env.REAL_DB_SHA256_EXPECTED` 写回旧值 `F5DA2306…` 后调用 `assert_real_db_untouched()` | **抛 `RuntimeError: 真实库 app.db 已偏离钉死哈希（negative-control）`**：期望 `F5DA2306…`／实测 `4EB632A4…` |
| N-2 | `check_db_bootstrap` 的旧期望串 `直接拷贝 6712 行` | 新库现场输出为 `10172` ⇒ 旧串**不再出现**，旧期望必红 |

---

## 7. 回退

1. `Copy-Item 'app.db.bak-20261009_004525' 'app.db' -Force`（恢复为 `2531328 B / F5DA2306…0E0F065`）；
2. 把 L-1 改回 `F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065`、L-2 同改；
3. 把 L-3 的 `10172` 改回 `6712`、L-4 同改；
4. 复跑 `ci_gates.py --phase first` 取回退后的 exit 0。

---

## 8. 与并发任务 B14-00 的关系（须由其所有人裁定）

* `test-reports-2026-10/B14-00-基线推进登记-合金钢.md`（任务 t8，本任务读取时 mtime 为
  2026-10-09 00:43:10）其 **§8 把「真实库 `app.db` 起点 == 终点」列为本任务的零改动不变量**
  （`2531328` / `F5DA2306…0E0F065` / mtime `2026-09-18 12:50:55`）。该不变量**已被本次经用户授权的
  真实库写入取代**（ALLOY-IMPORT-02）：B14-00 在**其现场时点内**的读数仍然真实有效，但其「不变」表述
  自 `2026-10-09 00:45:39` 起不再成立。
* B14-00 §6 的 `evidence_hash` 读数（`real_db_matches_pinned == true`）在本登记件的 L-1 落地后
  **仍然成立**（钉值已同步为新锚点），但其比对基准换代了：旧稿比 `F5DA2306…`，现稿比 `4EB632A4…`。
* 本件**没有**改写 B14-00 的任何既有段落（append-only 纪律），也未改其 `LOCKED` 相关口径
  （路由/覆盖锁仍为 ALLOY-IMPORT-01 的 273 / 155 / 157）。

---

## 9. 待追加条目

* CI 复跑读数（`--phase first` 与 `--only evidence_hash`）将在本件末尾以新小节追加。

---

## 10. CI 复跑读数（追加，2026-10-09 00:49–00:50）

* `& '<py>' -B test-reports-2026-10\harness\ci_gates.py --phase first`
  ⇒ **exit 0** / `steps=15` / `blocking 失败 = 无` / `report-only 失败 = 无` / `注入未生效 = 无` /
  `仓库根两 JSON 未被触碰 = True（A-11）` / `gaps: A-63-STEP2-BUILD-GATE = blocked（不计入通过数）`；
  原始输出落盘 `test-reports-2026-10/evidence/harness/ci-run-20261009-004944/ci_gates_first.console.txt`。
* 逐步 checks：`check_templates 5/5`、`check_migration_heads 4/4`、`check_properties 3/3`、
  `check_db_bootstrap 4/4`（现读 `直接拷贝 10172 行，跳过 0 张表`）、`run_gates 4/4`
  （其自身 exit=1：`env-probe route_inventory_native_probe native_exit=0 expected=1 verdict=unexpected`，
  A-62 判定为环境依赖预期，`expect_exit=None` 且 `summary.fail==0`）、`functional_test 2/2`、
  `permission_matrix 3/3`、`smoke_test 3/3`（report-only）、`route_inventory 3/3`、
  `measure_coverage 1/1`、`coverage_drift 2/2`、`check_notification_triggers 5/5`、
  `check_model_refs 5/5`、`check_http_contract 4/4`、`evidence_hash 4/4`（自身 exit=1，report-only）。
* `& '<py>' -B test-reports-2026-10\harness\ci_gates.py --phase first --only evidence_hash`
  ⇒ **exit 0**（`real_db_matches_pinned == true`）；落盘 `evidence/harness/ci-run-20261009-005045/`。
* 链后真实库仍为 **`3035136 B / 4EB632A4…FA43`**（mtime `2026-10-09 00:45:39`）⇒ 整链对真实库只读。
* 首轮（改判据后、夹具修复前）为 **exit 1**，唯一 blocking 失败 = `functional_test`（checks 0/2），
  原因与修复见 §12。

---

## 11. 验收探针读数（追加，真实库**字节级副本**上只读验收）

`.tmp/verify_real_import.py`（经 `python -B scripts/_sandbox_compat.py` 运行）⇒ **21 通过 / 0 失败**（exit 0）：

* `ProcessPrice total=3534 normal=2907 subtotal=627 is_current=3534 groups=3507`；`process_code` 唯一 3534、
  最长 25 字符、**无成员小计 0 条**。
* `Product total=1081 辙叉总成=48 BOM子件=1032 | ProductBOM=1728(全 product) ProductProcess=3`；
  3 条产品工序全部指向**新**工价行（`process_id > 3486`）。
* **48 个父件全部有 BOM 明细**；抽检 `YHHCCZ577-I-03` 33 行（例：`高强度大六角头螺栓 M27x290 (GB1228)`）、
  `YHHCXJX21-03` 32 行（例：`高强度平垫圈 27 (GB1230)`）。
* 子件规格落 `specification`：例 `材料：合金钢；单重：208.0kg；总重：208.0kg`。
* 小计抽检：`YHGHCZ2209-I-4698DF` 小计 `240.00` == 9 名成员单价合计 `240.00`。
* 页面可达（真实渲染）：`GET /process_prices` 200、`?show_all=y` 200、`GET /products` 200、
  `?search=辙叉` 200。
* 探针末尾复核真实库 SHA256 **未变**（`4EB632A4…FA43`）⇒ 验收全程只读。

---

## 12. 首轮 CI 红与夹具隔离修复（追加，连带发现）

* 首轮 `functional_test` exit=1 / 2 失败：`BOM 正式导入 1 父件 + 2 子件 + 2 明细 -- parents=0 children=0
  rows=2 err=[]`、`BOM 写库 3 产品 + 2 明细且父件可查 -- (1082, 1728) -> (1082, 1697)`。
* 根因（真库已有全量合金钢数据后暴露）：探针夹具用了**真实数据键** —— 文件名
  `（1）YHHC CZ577-I-03.xlsx` + 标题 `总图号：YHHC CZ577-I-03`（父件图号 `YHHCCZ577-I-03`）与子件代码
  `GB1228` ⇒ 命中既有行，`parents_created` 由 1 变 0、`children_created` 由 2 变 0；更严重的是
  `replace_existing=1` 把真实父件 `YHHCCZ577-I-03` 的明细在**副本内**删掉（`ProductBOM 1728 → 1697`）。
* 修复（`scripts/functional_test.py`）：夹具改为**全合成键** —— 工价 工作表/型号/图号 = `01-ZZTEST-01` /
  `ZZTEST-01`；BOM 文件名 `（99）ZZTESTBOM-01.xlsx` + 标题 `总图号：ZZTESTBOM-01` + 子件代码
  `ZZTEST-B1`/`ZZTEST-B2`（名称 `ZZTEST 螺栓M27x120` / `ZZTEST 橡胶垫板`）；探针内父件查询改为
  `product_name='ZZTESTBOM-01'`。
* 修复后：`结果：127 通过 / 0 失败`（exit 0），链内 `functional_test 2/2`（见 §10）。
* 影响面：修复前该夹具在**任何**已含合金钢数据的库上都会误伤真实父件明细（副本内），故此为必要加固，
  不只是让期望值满足。

---

## 13. 本触发项落地文件哈希（追加，SHA256）

| 文件 | 字节 | SHA256 |
| --- | --- | --- |
| `test-reports-2026-10/harness/_env.py` | 16889 | `5DA5FEA499E07A90232D83BD6087CEE2A567F7587D9A981F78E5FFA15168463E` |
| `test-reports-2026-10/harness/t6_ledger_check.py` | 11815 | `58F107DA3190107EB6EDFE12750D54D9798E533B3956D993EBD2929285E01E26` |
| `test-reports-2026-10/harness/ci_gates.py` | 73526 | `E71CC9C7AD5F62867D6776455AEBF495BDF45BCFB343F012031EF1CF0AA2CB91` |
| `test-reports-2026-10/harness/run_gates.py` | 24546 | `FF724816C55A6154B003F2C9F0B882B0F5840B8EA973F4A63974F829608A4C45` |
| `scripts/functional_test.py` | 37567 | `E0FABA1C28B43108E953FD5A8424F752D24C9BEAA45C69B6DF9CF71D8C935C69` |

> 对照：本触发项**改动前**的 `ci_gates.py`（ALLOY-IMPORT-01 落地态）=
> `9BA710184CEEE4AA23F0D5085E52BE1C06595A389BBCBA257AE92916ACCA311B`（73288 B）、
> `run_gates.py` = `066E1E96C1B4A2840CEBD8EE43BC44980B75A9F2A25311B195155EB8FF42B311`（24476 B）。

---

## 14. 覆盖声明（追加，2026-10-09 01:0x）—— **§3 的真库锚点新值与 §4 的 4 处判据同步均已被取代**

> **本节为 append-only 覆盖声明**：§0–§13 的既有读数**逐字节保留、未做任何改写**，但其中「导入后新锚点生效」这一
> 结论自 `2026-10-09 00:5x` 起**不再成立**。所有读数均为现场复跑自证，格式 =「工具 + 口径 + 值 + 时点」。

### 14.1 取代结论（一句话）

* 用户裁定「**真库 + 判据锚点一起回退、合金钢功能代码保留**」后：
  * §3 的「新锚点 = `3035136 B / 4EB632A4…DFA43`」**已被取代**；
  * §4 的 4 处活体判据同步（L-1 `harness/_env.py` / L-2 `harness/t6_ledger_check.py` / L-3 `harness/ci_gates.py`
    的 `check_db_bootstrap` 期望串 / L-4 `harness/run_gates.py` 的 `EXPECTED['bootstrap_copied_rows']`）
    **已随之逐处回退**；
  * **现行期望值回到 `2531328 B / F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065` /
    mtime `2026-09-18 12:50:55`**；
  * 回退的逐处明细、阴性对照与复现命令见 `test-reports-2026-10/B14-R1-锚点回退登记.md`（B14-R1 = 任务 t10，
    即本覆盖声明的执行载体）；真库还原由 captain 以**字节级回滚源**完成（§7 步骤 1）。

### 14.2 「仍然生效」与「已被取代」（必须分开读）

| 项 | 状态 | 现场依据（工具 + 口径 + 值） |
| --- | --- | --- |
| ALLOY-IMPORT-01 的**路由基线推进**：路由 271→**273**、`writable_rules_non_get` 153→**>=157**、`check_properties` 扫描文件 23→**26**（模型类 74） | **仍然生效** | `harness/coverage_drift.py:161-167` LOCKED（`rules_total == 273` / `method_level_non_get_total >= 157` / `writable_rules_non_get == 155`）；`harness/ci_gates.py:688` 期望 `['已扫描 26 个文件，模型类 74 个', 'RESULT: OK']`；放行绿灯 run 内 `coverage_drift` 步 checks 2/2、`check_properties` 步 checks 3/3 全 passed（= 上述锁在该 run 的 `coverage.json` 上成立） |
| 合金钢**功能代码与工具链**（`app/**` 4 个新模块、`app/main/routes.py` 2 条 POST、`scripts/functional_test.py` 合成键加固等） | **仍然生效** | 绿 run 内 `functional_test` 步 needles `['结果：127 通过 / 0 失败', 'exit == 0']` 全 passed、checks 2/2 |
| §3 的**真库锚点新值**（`3035136 / 4EB632A4…DFA43`） | **已被取代** | 见 §14.3 第 1/2/3 行（现行真库三值 ≠ 导入态三值） |
| §4 的 **L-1 … L-4** 4 处判据同步 | **已被取代** | 见 §14.3 第 4–7 行（现行行值 = 干净口径） |
| ALLOY-IMPORT-02 **导入真实库的数据**（工价 3534、小计关系 3507、48 父件 / 1032 子件、BOM 明细 1728、22 行改指、审计 3 条） | **已不在真实库**（仅存于留证副本） | 真库现为 `2531328 B / F5DA2306…0F065`（§14.3 第 1 行）；导入态整体另存为 `app.db.evidence-ALLOY-IMPORT-02-20261009_004539` = `3035136 B / 4EB632A4…DFA43`（§14.3 第 2 行） |

### 14.3 现场读数（工具 + 口径 + 值 + 时点 = 2026-10-09 01:0x，本次复核）

| # | 项 | 工具 + 口径 | 值 | 时点 |
| --- | --- | --- | --- | --- |
| 1 | 现场**真实库**三值 | `F:\Miniconda\envs\wage\python.exe -B` 只读脚本：`os.stat` 取字节数/mtime + `hashlib.sha256(open(p,'rb').read())`（口径 = 三元组） | `app.db` = `2531328` / `F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065` / `2026-09-18 12:50:55` | 本次复核 |
| 2 | 导入态**留证副本**三值 | 同上（副本 `app.db.evidence-ALLOY-IMPORT-02-20261009_004539`） | `3035136` / `4EB632A48F1C7E8A13BCE8F6263D587A1958D01CC84E37A0D4359E1506DDFA43` / `2026-10-09 00:45:39` | 本次复核 |
| 3 | 4 份**回滚源备份**三值 | 同上（`app.db.bak-20261009_004428` / `_004433` / `_004503` / `_004525`） | 四份逐字节相同 = `2531328` / `F5DA2306…0F065` / `2026-09-18 12:50:55`（字节级等于 §7 步骤 1 的还原源） | 本次复核 |
| 4 | L-1 现行行 | `read`（utf-8）逐行取证 | `test-reports-2026-10/harness/_env.py:67` = `REAL_DB_SHA256_EXPECTED = 'F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065'`；其上 `:48-66` 为「历史留痕 + B14-R1 回退」注释，导入期值 `4EB632A4…` / `3035136` **仅存注释** | 本次复核 |
| 5 | L-2 现行行 | 同上 | `test-reports-2026-10/harness/t6_ledger_check.py:37` = `PINNED_DB_SHA = 'F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065'`（`:35-36` 注释记该值曾同步为 `4EB632A4…FA43`，属历史） | 本次复核 |
| 6 | L-3 现行串 | 同上 | `test-reports-2026-10/harness/ci_gates.py:696` = `'expects': ['种子库账号数（经自举导入到空库）= 64', '直接拷贝 6712 行，跳过 0 张表', 'OK: 空库自举、幂等、无种子库跳过、整表无遗漏 均通过']`（`:689-692` 注释记回退依据 = run `ci-run-20261009-005619` 的 `ci_check_db_bootstrap.out:4`） | 本次复核 |
| 7 | L-4 现行值 | 同上 | `test-reports-2026-10/harness/run_gates.py:57` = `'bootstrap_copied_rows': 6712,`（行内注释记导入期值 10172） | 本次复核 |
| 8 | **放行绿灯 run**（本波自证） | 机读 `test-reports-2026-10/evidence/harness/ci-run-20261009-005727/ci_gates_first.console.txt`（口径 = 首行 `steps=` + JSON 的 `blocking_failed` / `report_only_failed` / `injection_ineffective` / `root_json_untouched.ok`） | `run_id=run-20261009-005727 phase=first steps=15`；`blocking_failed=[]`、`report_only_failed=[]`、`injection_ineffective=[]`、`root_json_untouched.ok=true`；`check_db_bootstrap` needles 现读 `直接拷贝 6712 行，跳过 0 张表`（checks 4/4）；`run_gates` stdout `real.db unchanged = True (F5DA2306BC31CBAB…)` ⇒ 按 `exit_code_semantics`（0 = 全部 blocking 通过）**exit 0** | run 落盘 mtime `2026-10-09 00:58:19` |
| 9 | **复核绿灯 run** | 同口径，`evidence/harness/ci-run-20261009-005944/ci_gates_first.console.txt` | 同上：`steps=15`、两失败表空、`6712`、`real.db unchanged = True`；15 步 checks 全 passed（`run_gates` 与 `evidence_hash` 自身 exit=1 属 A-62/A-63 既有预期，checks 4/4） | run 落盘 mtime `2026-10-09 01:00:37` |
| 10 | **独立复现绿灯 run**（t4 侧，非本波执行者） | 同口径，`evidence/harness/ci-run-20261009-010225/ci_gates_first.console.txt` | 同上：`steps=15`、`blocking_failed=[]`、`report_only_failed=[]`、`直接拷贝 6712 行`、`real.db unchanged = True (F5DA2306BC31CBAB…)` | run 落盘 mtime `2026-10-09 01:03:17` |
| 11 | 阴性对照（**方向已反转**） | 把 `_env.REAL_DB_SHA256_EXPECTED` 写成**导入后**锚点 `4EB632A4…` ⇒ `assert_real_db_untouched()` 现场抛 `RuntimeError: 真实库 app.db 已偏离钉死哈希` | 见 `harness/_env.py:61-62` 注释与 `B14-R1-锚点回退登记.md` §阴性对照（NC 系列）实测 | `2026-10-09 00:5x–01:0x` |

* **口径说明（不作夸大）**：`ci_gates_first.console.txt` 只落盘「首行 `run_id/steps` + JSON 摘要」，**不含进程退出码**；
  因此上表第 8–10 行的 `exit 0` 是**按 ci_gates 自述规则**（`exit_code_semantics`：`0 = 全部 blocking 通过`）由
  机读三表为空 + `root_json_untouched.ok=true` 推得，未引用任何未落盘读数。
* 本节**未运行** `ci_gates.py`（本波门禁执行者 = quality-dev 的 t2）；第 8–10 行是对**既有落盘产物**的只读取证。

### 14.4 与 §6 / §7 / §8 / §13 的关系（不改写，仅声明）

* §6 的两条阴性对照为**历史对照**，方向随本次取代而反转：当前**写回** `4EB632A4…` 才报红（依据同 §14.3 第 11 行）。
* §7 的 4 步回退**已按序执行完毕**：步骤 1（真库还原为干净锚点）由 captain 以字节级回滚源执行；步骤 2–4
  （L-1/L-2 改回、L-3/L-4 改回 `6712`、复跑取回 exit 0）由 B14-R1 执行，逐处明细见 `B14-R1-锚点回退登记.md` §4。
* §8 关于 B14-00「真实库起点 == 终点」不变量的表述，因真库还原而**重新成立**
  （现行 = `2531328` / `F5DA2306…0F065` / `2026-09-18 12:50:55`）；本件不改写 §8 原文。
* §13 的文件哈希表为**历史值**：`_env.py`（16889 B / `5DA5FEA4…463E`）、`t6_ledger_check.py`（11815 B /
  `58F107DA…1E26`）、`ci_gates.py`（73526 B / `E71CC9C7…CB91`）、`run_gates.py`（24546 B / `FF724816…4C45`）
  均已因本次回退而变化；**现行值**见 `B14-R1-锚点回退登记.md` §8。

### 14.5 收尾声明

**本件为 append-only 覆盖声明：§0–§13 的原读数一律是历史事实，不得据此重装判据锚点。**
任何把真库锚点 / 拷行情数 / `functional_test` 期望串改回 §3 / §4 导入期值的操作，都等于复活已被取代的基线；
如需再次变更真库或锚点，必须另立 A-70 触发项（备份 → 全量同步同源判据 → 旧值必红的阴性对照 → 登记件）。
