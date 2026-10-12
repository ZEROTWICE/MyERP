# C-独立验证（verify-c，非作者，t7）

- 验证者：`verify-c`（**非作者**：t4/t5/t6 的实现者分别为 impl-p1/impl-p2/impl-p1；本件与全部夹具、脚本均由验证者自写）
- 被验对象：t4（P1/P6/P9/P10）、t5（P2/P3/P4/P5）、t6（G-19/G-21）的实现件 + t2（资产/口径订正）、t3（注入面与锚点实测）的交付件
- 尝试号：`cf77add3-0b2b-4363-9266-c4c6026623eb`
- HEAD：`9f28baa`
- 交付件本体：**本文件之前版本均不存在**（新建件；`docs/**` 一字未动，`git status --porcelain -- docs/` 空）
- 本次新增且仅新增：`test-reports-2026-10/C-独立验证.md`、`test-reports-2026-10/evidence/c/t7/**`（后者被 `.gitignore:42` 忽略，属本地留档）

## 0. 结论摘要

**总体**：被验 7 条缺陷（P1/P2/P3/P4/P5/P6/P9/P10 计 8 条）+ 2 条工具面口径（G-19/G-21）**逐条独立复跑通过**；t2/t3 的资产与口径面结论**逐条现场复算一致**（G-12/G-16/G-17/G-20/G-22 + TL-05/06/07）。**没有任何一条作者的判据被放宽**。

**但不得写成「本批全绿」或「在册缺陷清零」**，因为：

| 事项 | 状态 | 说明 |
| --- | --- | --- |
| `ci_gates.py --phase first` 的**字面 exit 0** | **未达成** | 实测 `exit=2`：`blocking 失败=无`、唯一红 = **先在性** report-only `evidence_hash`（2 条 modified 的 mtime = 本批首轮 04:45 之前已在盘，非本批回归）。AC③ 据此**记 failed**，不折算 pass。解除条件见 §5.3-O1 |
| P9 非退化归属分支（`production_record → batch → product` 命名） | **not_measured** | 真库 `production_record` 0 行，我未独立构造 batch 夹具；仅复跑作者脚本得 +1 行。解除条件见 §5.2-F1 |
| P5 行号口径在「空行夹层」输入下 | **部分关闭/finding** | 我自造边界探针实测：解析器跳过空行 ⇒ 文案报 `第 3 行` 而 Excel 物理行号是 `第 4 行`。低危、口径边界，未折算 pass。见 §5.2-F2 |
| t5 验收书写的载体 `/employees/import` vs 实际改动载体 `/process_prices/import` | **勘误登记** | 两者我都独立实测通过（§2.6 双载体）；任务书措辞与现场不符，登记不折算 |
| G-21 uncovered 38 条 / coverage 冻结锚点缺失 / A-63-STEP2 挂账 | **仍留档** | 逐条带解除条件，见 §5.3 |

**自造阴性对照**：11 条（每条已修缺陷 ≥1 条），**全部「对照正确 ⇒ 断言转红」**，读数见 §4。

## 1. 验前基线（开工态）

### 1.1 真库三值（开工 / 收工逐字一致）

| 时刻 | sha256 | bytes | mtime |
| --- | --- | --- | --- |
| 开工 | `34e48e7a21163db390eebda4f2030343f3609afedc65d8c6e909d6eb5a49177e` | 2531328 | `2026-10-12 04:25:37.128430119 +0000` |
| 收工 | `34e48e7a21163db390eebda4f2030343f3609afedc65d8c6e909d6eb5a49177e` | 2531328 | `2026-10-12 04:25:37.128430119 +0000` |

- 命令：`sha256sum app.db; stat -c '%s %y' app.db`（口径 = 只读；全部写实验走 `scripts/_test_bootstrap.make_app()` 副本库）
- 真库只读旁证（我自跑只读查询两次）：`audit_log` 74 行；`can_rollback=1 AND target_id IS NULL` = **0**；`rollback_type='add' AND target_id IS NULL` = 10（**这 10 行 `can_rollback=0`，不构成 P1 违反**）。开工收工两次读数逐字相同。
- 未执行任何 `flask db *`；未写真实库；未跑请求型脚本以外的写库操作（请求全部落在副本）。

### 1.2 门禁三命令（本轮实测）

| 命令 | 读数 | exit |
| --- | --- | --- |
| `/opt/wage-venv/bin/python -B test-reports-2026-10/harness/ci_gates.py --phase first` | `steps=20 / blocking 失败=无 / report-only 失败=['evidence_hash'] / 注入未生效=无 / root_json_untouched=true / gaps: A-63-STEP2-BUILD-GATE = blocked（不计入通过数）`；run 产物 `test-reports-2026-10/evidence/harness/ci-run-20261012-064637/`（首轮 `ci-run-20261012-063220/` 同读数） | **2** |
| `/opt/wage-venv/bin/python -B scripts/check_doc_claims.py --selftest` | `自检 26/26 通过` | 0 |
| `/opt/wage-venv/bin/python -B scripts/check_doc_claims.py --coverage $(ls -dt test-reports-2026-10/evidence/harness/ci-run-*/coverage.json | head -1)` | `lock：33 条钉版 / 环境匹配 33 条 / exception 0 条` + `RESULT: OK（violations=0）` | 0 |

`evidence_hash` 失败明细（`ci-run-20261012-063220/evidence_hash.gate.json`）：`baseline_files 1433 / current_files 2748 / modified 2 / deleted 0 / added 1315 / index_missing 139 / coverage_gap 2 / journal_broken 0 / phantom_entry 0 / baseline_tampered 0`；两条 modified = `harness/b17-verify/probe_permission_matrix.txt`（9627→11234 B）与 `harness/b17-verify/probe_smoke_test.txt`（3186 B，sha `59A7E5F0…`→`DA0C377D…`），mtime = `2026-10-12 04:45:29` / `04:45:16`（**均早于本批 C 组全部实现轮**）⇒ 我先前的**先在性**判定成立，非本批引入。

### 1.3 命令口径常量（本轮 `--list-constants` 实读，29/29 `OK`）

`rules_total (273, 273)`｜`routes_py_lines (12825, 12825)`｜`models_py_lines (3246, 3246)`｜`ci_gates_steps (20, 20)`｜`method_level_GET (161, 161)`｜`method_level_non_get_total (158, 158)`｜`writable_rules_non_get (156, 156)`｜`writable_any_covered_by_all (118, 118)`｜`non_get_uncovered_method_level (40, 40)`｜`uncovered_writable_rules (0, 0)`｜`templates_files (87, 87)`｜`capabilities_declared (44, 44)`｜`properties_files (25, 25)`｜`model_classes (74, 74)`｜`migration_revisions (35, 35)`｜`roles_count (7, 7)`｜`ensured_columns_tables (11, 11)`｜`ensured_columns_total (44, 44)`｜`smoke_targets (149, 149)`｜`smoke_unresolved (9, 9)`｜`real_db_sha256 (34E48E7A…177E, 同值)`｜`real_db_bytes (2531328, 2531328)`
（写法 = `(钉值, 源值)`；命令：`scripts/check_doc_claims.py --list-constants --coverage <最新 run 产物>`）

### 1.4 作者自述的**不作为证据**原则

作者的实现件读数只用于「对表」，不作为通过依据；本件 §2/§3 每条的「值」全部来自**我自己重跑的命令**。作者脚本**未被采信**为证据（复跑作者脚本仅用于两条标注「复现性」的项，且已注明）。

## 2. 逐件独立复核（命令 / 口径 / 值）

### 2.1 P1 审计不变量（`rollback_type='add'`/`can_rollback` 行必须有 `target_id`）+ 守卫 fail-loud

- **命令**：`/opt/wage-venv/bin/python -B test-reports-2026-10/evidence/c/t7/t7_a_p1_p6_p9.py`（我自写，日志 `…/t7_a.log`）
- **口径**：副本库 + `login_as('_t_admin')` → `POST /products/add`；随后读 `audit_log` 最新行断言 `target_model='Product' AND target_id=<新行 id> AND can_rollback=1`；另直调守卫 `_assert_add_audit_target(log,'T7-守卫对照',None)`
- **值**：`login=302 http=200 body={'id': 2, 'message': '产品添加成功', 'success': True}`；`product.id=2 audit.id=75 target_model=Product target_id=2 can_rollback=True rollback_type=add`；守卫对照 ⇒ `AssertionError: 审计不变量被破坏：rollback_type=add 的审计行没有 target_id（回滚端点按 target_id 找不到目标，会返回 404「目标记录不存在」）。成因：新建业务行后未先 db.session.flush() 取主键就给 AuditLog(target_id=<新行>.id) 赋值（B13-01；正确写法见 add_employee 的 flush）。`（logger 同落 B13-01 ERROR）⇒ **关闭**
- **独立复算路径**（不与作者同源）：我自写 AST 扫描器 `test-reports-2026-10/evidence/c/t7/p1_invariant_scan.py`，对 `app/main/routes.py`、`app/main/quality.py`、`app/main/production_center.py` 每个 `AuditLog(...)` 站点解析 `rollback_type='add'`/`can_rollback=True` 与 `target_id=<expr>`，回看 +30 行内是否有 flush/savepoint/commit 边界 ⇒ `SITES=74 NULL_RISK=0 GUARDED=12`
- **阴性对照**：`negctl/prefix_form.py`（我自造修前形态：`db.session.add(product)` 后无 flush 直接 `target_id=product.id`）⇒ `SITES=1 NULL_RISK=1` / `RED(OK)`

### 2.2 P6 报工局部事务原子性（内层失败必须整体回滚 + 上抛 500）

- **命令**：同 `t7_a_p1_p6_p9.py`（P6 段）
- **口径**：副本库夹具 task=(1,1,'00019248','pending') + 自造 `raw_material` id=2 qty=100；健康路径与投毒路径各一次；投毒 = `MS2.record_task_material_consumption = raiser`（RuntimeError）
- **值**：健康 `http=200 body={'message': '更新成功', 'success': True}`、`PR 0->1 status pending->completed`（**仪器灵敏度证明：非恒零**）；投毒 `http=500 body={'message': '更新失败，请稍后重试或联系管理员', 'success': False}`、`PR 0->0 status pending->pending raw 100.0->100.0 注入=1`，logger 两行 `报工扣料回写 MaterialAllocation 失败：T7-P6 注入：扣料回写失败` + `更新任务状态失败：T7-P6 注入：扣料回写失败` ⇒ **关闭**
- **自造微形态阴性对照**（同一副本内重放两种微观形态，用自造 `Product` 行）：无 savepoint + 吞异常 ⇒ **残留 1 行**；savepoint + 上抛 + 外层 rollback ⇒ **0 行** ⇒ `[T7-P6-NC] PASS`

### 2.3 P9 报工路径报废自动入账（`inbound_production_scrap` 全调用点接入）

- **命令**：同 `t7_a_p1_p6_p9.py`（P9 段）；端点 `POST /api/quality/nonconformities/<id>/dispose`（`app/main/stock.py:74`）
- **口径**：副本库自造不合格单 → 处置 `action='scrap'`，量 `finished_product` 增量（基线 = 事前 `max(id)`）与 `product_number/workpiece_id/notes`
- **值**：`nc_id=1 http=200 body={'message': '处置已记录', 'status': 'done', 'success': True, 'target_id': '', 'target_type': 'production_record'}`；台账行 `id=3 product_number='报废单1' qty=2 workpiece_id=None notes='报工路径报废自动入账：不合格单 #1，实例 -，件数 2'`；logger `报工路径报废：不合格单 1 定位不到批次实例/订单 ⇒ 台账行产品号退化为 报废单1（件数仍按 2 入账，不猜归属）` + `报废处置未扣减：未找到产出的消耗明细（不合格单 1，生产记录 None）；按 AC-29d 不扣任何料`；**退化路径**（target 全空）仍入账 1 行 `报废单2` ⇒ **关闭（退化分支）**
- **阴性对照**：把 `mes_service.inbound_production_scrap` 打成 `lambda **kw: None`（= 修前形态）⇒ 反转期望「报废后台账行数 ≥1」实测 `rows=0` ⇒ **RED(如预期)**

### 2.4 P10 notes 兜底 + 取价单点

- **命令**：`/opt/wage-venv/bin/python -B test-reports-2026-10/evidence/c/t7/t7_f_p10.py`（我自写，日志 `…/t7_f.log`，**10/10 PASS / exit 0**）
- **口径**：① `ExcelGenerator.parse_production_record_data`（`app/utils/excel_generator.py:340-361`，兜底行 `:358`）4 列 / 5 列两形态 + `POST /production_records/import` 端到端；② `pick_process_price`（`app/main/routes.py:157-197`）三版本夹具 × 业务日
- **值**：4 列 ⇒ `notes` 键存在且 `None`；5 列 ⇒ `'备A'`；端到端 `http=200 body={'message': '成功导入 1 条记录'}`、新增 1 行、`notes=NULL`。`pick_process_price`：业务日 `2026-06-15` ⇒ `version=2/price=20.0`（排未来版 + 取最新版）；文本日期 `'2026-06-15'` 同口径；`business_date=None` ⇒ `None` ⇒ **关闭**
- **阴性对照**：① 修前形态「无条件 `row[4]`」在同一 4 列行 ⇒ `IndexError: tuple index out of range` ⇒ **RED**；② 旧取价形态 `filter_by(process_code=…).first()` ⇒ `version=3/price=30.0`（取到未来生效版）⇒ **RED**
- **边界（文档化既有语义，非缺陷）**：`routes.py:167-169` 的「+1 天容差」⇒ 业务日 `2025-12-31` 仍取 `2026-01-01` 版（version=1），`2025-12-30` 才 `None`

### 2.5 P2 f-string 前缀（`第{index+2}行…`）

- **命令**：`…/t7_b_p2_p3_p4_p5.py`（我自写，日志 `…/t7_b.log`）
- **口径**：AST 复算（遍历 `ast.JoinedStr` 取常量片段含「第…行」，判定 `ast.FormattedValue` + `ast.BinOp(Name('index') + Constant)`），再取渲染值；**不采信 `grep` 计数**
- **值**：`app/main/routes.py` ⇒ `JoinedStr=2 裸字面量=0 行号偏移量=[2, 2]`；`index=3` 渲染 = `'第5行导入失败，请稍后重试或联系管理员'` ⇒ **关闭**
- **阴性对照（自造两形态）**：NC1 去掉 f 前缀 ⇒ `JoinedStr=0 / 裸字面量=1`；NC2 f-string 但 `index+1` ⇒ 偏移 `[1]`、渲染 `'第4行…'`（断言「第5行」不成立）⇒ 两条均 **RED(如预期)**
- 现场残留复核：`第{index`/`第 {index` 字面量 14 处**全在 f-string 内**；AST 复算 62 条 f-string 行号文案、**0** 条缺 f 前缀的裸字面量

### 2.6 P3 行级容错（**双载体**：权威载体 + 本批实际改动载体）

**（a）权威载体 `/employees/import`**（`test-reports-2026-10/70-第2轮收口与阶段C移交.md:509` ③ 原文点名）

- **命令**：`/opt/wage-venv/bin/python -B test-reports-2026-10/evidence/c/t7/t7_g_p3_authoritative.py`（我自写，日志 `…/t7_g.log`，**6/6 PASS / exit 0**）
- **口径**：按原文构造 **3 好 + 2 坏**（坏 = 负工资、22 字符工号）xlsx，走真实端点，量 `Employee` 行数 Δ 与文案
- **值**：`http=200 success=True Δ员工=3`；`message='成功导入 3 条记录\n失败：2 条记录导入失败\n\n错误详情：\n第4行数据错误：基本工资不能为负数\n第6行数据错误：工号长度不能超过20个字符'`；入库的恰是好行 `['E7G001','E7G002','E7G004']`；POST 后 `TEMP_FOLDER` 残留 `[]` ⇒ **关闭**
- **阴性对照**：反转期望「整单拒绝 ⇒ Δ==0」（= 修前形态）实测 `Δ=3` ⇒ **RED(如预期)**
- 归属说明：该载体在 HEAD `9f28baa` 已是行级容错（`app/main/routes.py` 内 `prepared_rows`/逐行 `try` + `第{i+1}行数据错误`），**不是 t5 本批改动**；本项由我实测确认缺陷不存在。

**（b）本批实际改动载体 `/process_prices/import`**（t5 的 AR2 落点）

- **命令**：同 `t7_b_p2_p3_p4_p5.py`（P3 段）
- **口径**：3 好 + 2 坏（坏 = 生效日期空、单价负）xlsx，真实端点
- **值**：`http=200 success=True Δ=3`；`message='成功导入 3 条记录\n失败：2 条记录导入失败\n\n错误详情：\n第5行数据错误：生效日期不能为空\n第6行数据错误：单价不能为负数'`（Excel 物理行号）⇒ **关闭**
- **阴性对照**：反转期望「坏行也必须入库 ⇒ Δ=5」实测 `Δ=3` ⇒ **RED(如预期)**
- **勘误登记**：t5 任务书 AR2 写的是 `/employees/import`，而 t5 的代码改动落在 `/process_prices/import`。**两者都已实测通过**，但任务书措辞与现场不符 ⇒ 登记（caption 层），不折算 pass。

### 2.7 P4 上传件清理（解析失败 / 校验早退 / 成功 / 异常四条出口）

- **命令**：同 `t7_b_p2_p3_p4_p5.py`（P4 段）
- **口径**：`TEMP_FOLDER=/root/code/MyERP/uploads/temp`；① helper `save_temp_file` 注入 `BoomFile.save` 抛 RuntimeError；② 端点（表单垫片 + 非法 xlsx）
- **值**：初始 `entries=[]`；helper 失败 ⇒ 无残留；端点 ⇒ `http=200 body={'message': '导入失败，请稍后重试或联系管理员', 'success': False}`、`entries=[]` ⇒ **关闭**
- **阴性对照**：把 `shutil.rmtree` 改为 no-op（= 修前形态，只靠 mtime>300s 钩子）⇒ 残留 `tmp9tzkhkkg` ⇒ **RED(如预期)**（随后我 `rm -rf` 清除，`ls uploads/temp | wc -l` = 0）

### 2.8 P5 行号口径（坏行行号 == Excel 实际行号）

- **命令**：同 `t7_b_p2_p3_p4_p5.py`（P5 段）+ 边界探针（同脚本 `P5-edge`）
- **口径**：4 行 xlsx（第 4 行坏工号），量 `production_record` Δ 与文案行号
- **值**：`ΔPR=3`、message 含 `第 4 行：员工工号 T7-NO-SUCH-EMP 不存在` ⇒ **与 Excel 物理行号一致** ⇒ 主流路径 **关闭**
- **边界探针（我自造，输入 Excel 第 3 行全空）**：解析器跳过空行 ⇒ 坏行实际 Excel 行号 = 4，但文案报 **`第 3 行`** ⇒ 口径漂移 ⇒ **finding（low，见 §5.2-F2）**，不折算 pass
- 现场残留复核：`app/main/routes.py` 内 `第 {index + 2} 行：` 共 **11 处**（2949/2959/2967/2990/4166/4172/4198/4289/4295/4302/4318），残留 `index + 1` 形态 **0 处**；`git show 1a3850f -- app/main/routes.py` 证本批只给 2 处**原先完全没有行号**的文案补了行号，另 11 条来自 B15 `d809e68`

### 2.9 G-19 写端点 deny face（同一工具内，角色集派生化）

- **命令**：`/opt/wage-venv/bin/python -B test-reports-2026-10/evidence/c/t7/t7_c_g19_g21.py`（我自写，日志 `…/t7_c.log`）+ 工具 `scripts/permission_matrix.py`
- **口径**：① 我自写独立派生：AST 扫 4 模块文件的 `@require_capability` 与 `url_map` 写方法对账；② 逐 role 实测 POST（`follow_redirects=True` 才能看到 `require_capability` 的 `flash('权限不足')`）
- **值**：写端点 = `equipment.manage:9 / purchase.manage:8 / shipment.manage:4` 合计 **21**（与工具 stdout「C-06 四模块写端点面 = 全绿（21 写端点…）」逐数一致，工具 `exit=0`）；逐端点 allow 集：equipment 9 条 `allow=admin,manager`；purchase 8 条 `allow=admin,manager`；shipment 4 条 `allow=admin,manager,sales`；**无「零 allow」或「全 allow」端点** ⇒ **关闭**
- **阴性对照**：放宽期望「`user` 可 POST `/work_centers/save`」⇒ 实测不成立（被 403/权限不足拦）⇒ **RED(如预期)**
- 派生化复核：`scripts/permission_matrix.py:383 def deny_roles_for(capability)`、`:486` 注释「deny 角色 = `deny_roles_for()` 派生（G-19：与能力面同源，不手写名单）」；`grep -nE "roles? *= *\[" scripts/permission_matrix.py` **0 命中**；该文件本批 diff = `+28/-18`

### 2.10 G-21 多方法规则覆盖口径

- **命令**：同 `t7_c_g19_g21.py` + `/opt/wage-venv/bin/python -B scripts/route_inventory.py`（报告型）
- **口径**：`route_inventory` 给多方法（GET+写）规则总量 N；最新 run 产物 `coverage.json:uncovered_multi_method_with_get` 给未命中 M；再用正则从交付件 `test-reports-2026-10/C-工具面覆盖口径.md` 提取反引号内 `/…` token 逐条对账
- **值**：`N=44`、`M=38`、`N−M=6`；38 条 rule **全部**在交付件中逐条出现（未出现 = `[]`）⇒ **关闭（口径成文）**
- **阴性对照**：放宽期望「uncovered=0」实测 38 ⇒ **RED(如预期)**
- 备注：`coverage.json` 顶层 = `harness/run_id/interpreter/isolation/conventions/summary/method_matrix/probes`；多方法未命中键为 `uncovered_multi_method_with_get`（**无** `multi_method_with_get_total` 字段；44 来自 `route_inventory.py` stdout）

## 3. 资产 / 口径面与注入面独立复算（t2 / t3 交付件）

脚本：`test-reports-2026-10/evidence/c/t7/t7_d_inject_assets.sh`（我自写，日志 `…/t7_d.log`，**16 PASS / 0 FAIL / exit 0**）

| 项 | 命令 | 口径 | 值 | 结论 |
| --- | --- | --- | --- | --- |
| G-12 | `t7_d_inject_assets.sh`（G-12 段） | 整数词边界 `grep -cE "(^\|[^0-9])(101\|141)([^0-9]$\|$)"` + `coverage_verdict()` 整函数重算 | `analysis_ledger 101/141 命中=0`；`coverage_verdict 内 108/116 命中=0`；`improve_plan 101/141 命中=0`；`final_recount` 已绑 `coverage_pins()`（`:314/:315/:386/:449`） | 已同步（无改值对象） |
| G-16②=P12 | 同上 | 静态调用点 + 四态 | `reconcile_r2.py:324 COVERAGE_DRIFT=…`、`:593 chk_subprocess([PY,'-B',COVERAGE_DRIFT,'--coverage',run_coverage_artifact()]`；`--selftest` 11/11 `rc=0`、缺参 `rc=2`、死路径 `rc=1`、本次产物 `rc=0`（8/8 面） | 已修且语义正确 |
| G-16① | `coverage_drift.py --coverage test-reports-2026-10/evidence/harness/coverage.json` | 显式传**归档锚点** | `[FAIL] coverage.json 不存在` / `rc=1`；无参 `rc=2`（fail loud）；陈旧产物 `rc=1`；本次产物 `rc=0` | **判据正确，非缺陷**；证据形态 = 锚点缺失（见 §5.3-O5） |
| G-17 | `git status --porcelain -- 'test-reports-2026-10/40-*'` + `git diff --numstat` | 工作区干净 | 两者均**空** | 已提交 |
| G-20 | `grep -c 'def csrf_matrix' test-reports-2026-10/harness/api_matrix.py`；`ls scripts/api_matrix.py` | 唯一实现 + 单一分母 | `1`；`scripts/api_matrix.py: No such file or directory`；A-69 注释命中 2（`:733 def csrf_matrix`、`:753-757` AC-69 单一分母） | 单一分母，24 条文案分母已废 |
| G-22 | `ls .tmp_v15_*` + `git ls-files \| grep tmp_v15` | 现场与索引 | 工作区 **0** 个；索引 **0** 条 | 已消除 |
| TL-05 | `check_properties.py --root <合成树>` | 实例访问不存在属性 | 合成树 `rc=1` 报 `negctl/tl05/app/bad_inst_verify.py:11 [实例访问了该类不存在的属性] e.not_a_column`；真树 `--selftest` ⇒ `已扫描 25 个文件，模型类 74 个 / RESULT: OK` `rc=0` | 注入转红 + 恢复绿 ✅ |
| TL-06 | `check_doc_claims.py --docs <干净件> --skip-lock --coverage <产物>` | 同一命令两态 | C0 `rc=0` `RESULT: OK（violations=0）` → C1（同文件注入 `≥135` 一行）`rc=1`、`[VIOLATION] …/negctl/dc_ge135_verify.md:1：出现作废口径值 ge135 —— ≥135：写端点无命中计数（A-31 已更正为 ≥141）` | 转红 ✅ |
| TL-07 | `check_doc_claims.py --lock /nonexistent/…` | 删 lock | `rc=1` 报 lock 不存在；不删 ⇒ `lock：33 条钉版 / 环境匹配 33 条 / exception 0 条` `rc=0` | 转红 + 恢复绿 ✅ |
| A-70 §C-07 | `negctl/check_doc_claims_pin12806.py`（旧钉值副本，伪造 `__file__` 保 `REPO_ROOT`） | 旧值对照 | `钉常量 vs 权威源：28/29 相等` / `[VIOLATION] … route_py_lines 钉值 12806 ≠ 源值 12825` + 终判 `RESULT: FAIL（violations=2）` `exit=1`；现场（12825）`29/29 RESULT: OK` | A-70 三步齐全且**我独立复现 ② 步转红** ✅ |
| t2 §1.7 headline：`check_doc_claims.py` 裸跑 | `/opt/wage-venv/bin/python -B scripts/check_doc_claims.py`（无参） | 默认覆盖源 | `钉常量 vs 权威源：20/29 相等`、**11 条 VIOLATION**、`RESULT: FAIL（violations=11）`、`exit=1`；根因 = 默认源 `evidence/harness/coverage.json`（常量 `scripts/check_doc_claims.py:67`）**不在盘** ⇒ 9 键源值 `None` | **假红确认**（工具缺陷，见 §5.3-O6） |

## 4. 自造阴性对照汇总（11 条，全部转红）

| # | 被验项 | 对照构造（我自写） | 转红读数 |
| --- | --- | --- | --- |
| NC1 | P1 | `negctl/prefix_form.py`：add 后无 flush 直接取 `.id` | `NULL_RISK=1`（现场 74 站点为 0）；守卫直调 ⇒ `AssertionError` |
| NC2 | P1 | 反向断言：`can_rollback=1 AND target_id IS NULL` 应为 0 而非「存在」 | 真库 0 ⇒ 反向断言不成立（如预期） |
| NC3 | P6 | 无 savepoint + 吞异常 vs 有 savepoint + 上抛 | 残留 **1 行** vs **0 行** |
| NC4 | P9 | `inbound_production_scrap` 打成 `lambda **kw: None`（修前） | 反转期望「台账行 ≥1」实测 `rows=0` |
| NC5 | P10① | 修前形态「无条件 `row[4]`」喂 4 列行 | `IndexError: tuple index out of range` |
| NC6 | P10② | 旧取价形态 `filter_by(...).first()` | `version=3/price=30.0`（取到未来版，期望 2/20.0） |
| NC7 | P2 | ① 去 f 前缀 ② `index+1` | `JoinedStr=0/裸字面量=1`；渲染 `第4行…` ≠ `第5行` |
| NC8 | P3(a)(b) | 反转期望「整批拒绝 ⇒ Δ=0」/「坏行也必须入库 ⇒ Δ=5」 | 实测 Δ=3 / Δ=3（两处均不成立） |
| NC9 | P4 | `shutil.rmtree` 改 no-op（修前） | `uploads/temp` 残留 `tmp9tzkhkkg` |
| NC10 | G-19 | 放宽期望「`user` 可 POST `/work_centers/save`」 | 不成立（被拦） |
| NC11 | G-21 | 放宽期望「uncovered_multi_method=0」 | 实测 38 |
| NC12 | TL-05/06/07 | 合成坏树 / 注入作废值 / 删 lock | `rc=1`、`[VIOLATION] …ge135`、lock 不存在（三态全红） |

**不能构造的对照（说明原因）**：P9 的**非退化归属分支**（`production_record → batch → product` 命名）——真库 `production_record` **0 行**、无 `workpiece_id IS NULL` 的不合格单，我未在验证窗口内独立搭出 batch 夹具 ⇒ 记 `not_measured`（解除条件见 §5.2-F1），不接受作者脚本读数作证据。

## 5. 三张清单

### 5.1 本批**关闭**（逐条给实测值）

| 项 | 载体 | 关键实测值 | 对照 |
| --- | --- | --- | --- |
| P1 | `app/main/routes.py:4471 _assert_add_audit_target` + 11 调用点 + `app/main/quality.py:601/:675` | `target_id=2 can_rollback=True`；扫描 `SITES=74 NULL_RISK=0 GUARDED=12` | NC1/NC2 |
| P2 | `app/main/routes.py:5505`、`:5598`（f-string） | `JoinedStr=2 裸字面量=0`；渲染 `第5行导入失败…` | NC7 |
| P3(a) | `/employees/import`（权威载体） | 3 好 + 2 坏 ⇒ `Δ=3`、`第4行/第6行数据错误`、TEMP `[]` | NC8 |
| P3(b) | `/process_prices/import`（t5 实际改动） | 3 好 + 2 坏 ⇒ `Δ=3`、`第5行/第6行数据错误` | NC8 |
| P4 | `import_products` `app/main/routes.py:8324` + `save_temp_file:5645` | helper/端点两路径 `TEMP entries=[]` | NC9 |
| P5（主流） | `app/main/routes.py:2949…4318` 11 处 | `ΔPR=3`、`第 4 行：员工工号 … 不存在`（= Excel 行号） | NC8 同族 |
| P6 | `update_task_status` 7 内层块 + 外层兜底 | 健康 `PR 0->1`；投毒 `http=500`、`PR 0->0`、`raw 100.0->100.0` | NC3 |
| P9（退化分支） | `app/main/stock.py:74` → `mes_service.py:1297` | `http=200`、台账 `报废单1 qty=2 workpiece_id=None`；退化 `报废单2` | NC4 |
| P10① | `app/utils/excel_generator.py:358` | 4 列 ⇒ `notes=None`；5 列 ⇒ `'备A'`；端到端 `成功导入 1 条记录` | NC5 |
| P10② | `app/main/routes.py:157-197`（调用点 `:2963/:4179/:4300`） | `2026-06-15 ⇒ version=2/price=20.0`；`None ⇒ None` | NC6 |
| G-12 / G-16② / G-17 / G-20 / G-22 | 见 §3 | 见 §3 | — |
| G-19 | `scripts/permission_matrix.py`（`deny_roles_for:383`） | 21 写端点、允许集 9/8/4、工具 `exit=0` | NC10 |
| G-21（成文口径） | `test-reports-2026-10/C-工具面覆盖口径.md` | `N=44 M=38`、38 条逐条在册 | NC11 |
| TL-05/06/07 + A-70 §C-07 | 见 §3 | 15 条读数全绿 | NC12 |

### 5.2 **部分关闭 / finding**（必须带解除条件，不折算 pass）

- **F1（medium）P9 非退化归属分支 `not_measured`**：未独立复现「有 `production_record` + batch + 订单」时台账行的 `product_number` 取真实产品号。**解除条件**：在副本库自造 batch/production_record 夹具，走 `/api/quality/nonconformities/<id>/dispose`，断言 `product_number` = 批次对应产品号（非 `报废单N`）且件数一致；独立跑绿后回填本行。
- **F2（low）P5 行号口径边界**：输入含**中间全空行**时，`parse_*` 跳过空行 ⇒ 文案行号（解析后序号 + 2）< Excel 物理行号。既有语义（非本批引入）。**解除条件**：改为「解析后序号 + 丢弃行数 + 2」的显式口径（或改用 pandas 行索引映射），并补一条空行夹层用例；改判据须走 A-70 三步。
- **F3（low）t5 任务书载体措辞勘误**：AR2 写 `/employees/import`，代码落在 `/process_prices/import`；两者我都已实测通过 ⇒ 记勘误，**不折算 pass**。**解除条件**：captain 在登记件留档勘误（不改判据）。
- **F4（note）`C-资产与口径订正.md` prose 陈旧数**：t2 声明 60690 B，现场 61233 B，但 `git hash-object` = `1175a92fc612e01007d649a1d3a255d27fea3afc` 与 t2 声明的 blob **一致** ⇒ 内容未漂移，仅 prose 数字陈旧（只读件不追改）。**解除条件**：无需动作；后续引用以现场字节数为准。

### 5.3 **仍留档**（`blocked` / `not_measured` / `not_covered` / `not_counted_as_passed`，逐条带解除条件）

- **O1 `blocked`（report-only，先在性）`evidence_hash`**：2 条 modified = `harness/b17-verify/probe_permission_matrix.txt`、`harness/b17-verify/probe_smoke_test.txt`，mtime `2026-10-12 04:45:29`/`04:45:16`（**早于本批全部实现轮**）；结构病灶 = `b17_governance_contract.py` 硬钉 `HARNESS_RUN_ID='b17-verify'` + `harness/_env.py:36-40` 目录解析 + `measure_coverage.py:254-255` 原地覆盖（t8 已改走 `_env.save_evidence()` def `:341`）。⇒ **门禁字面 exit 0 未达成（exit=2）**，AC③ 记 failed。**解除条件**：A-70 `--freeze` 重基线 `test-reports-2026-10/evidence/artifact_hashes.json`，或让该治理件落到新的 run_id 目录后复跑 `ci_gates --phase first` 取 `exit=0`。
- **O2 `not_counted_as_passed` `A-63-STEP2-BUILD-GATE`**：`ci_gates` 自报 `blocked（不计入通过数）`；Docker 为唯一部署路径、容器内无 docker ⇒ 本环境不可测。**解除条件**：在有 Docker 的 CI 主机执行 build gate 并回填读数。
- **O3 `not_measured` P11/G-22 与 `.tmp_v15_*`**：工作区与 git 索引均 0 条（我已实测），但**无处置登记件** ⇒ 按守门口径不得折算 pass。**解除条件**：captain 出登记件记录「已消除/不复现」+ 复现命令。
- **O4 `not_covered` G-13 / G-15 三载体 / G-18**：t1/t3 现场判定（G-13 保持 `not_covered`；G-15 三载体 MISSING；G-18 仍在增长）。我未在本轮独立复跑这三项（不在 t7 必做面）。**解除条件**：单列任务补测后回填。
- **O5 `not_measured` coverage 冻结锚点**：`test-reports-2026-10/evidence/harness/coverage.json` 已不在盘、`coverage_drift.py:120` 声明的 `_anchor-history/` 不存在、`evidence/**` 被 `.gitignore:42` 忽略且从未入 git（`git log --all --diff-filter=D` 空）⇒ **不可恢复**。判据本身正确（无参 `rc=2` fail loud、显式传陈旧产物 `rc=1`、本次产物 `rc=0`）。**解除条件**：A-70 重基线并新建冻结锚点（用户/ captain 层裁定）。
- **O6 `not_counted_as_passed` 工具缺陷：`check_doc_claims.py` 裸跑假红 11 条**：默认覆盖源缺失 ⇒ 9 键源值 `None` ⇒ 报「钉值 X ≠ 源值 None」且 `exit=1`，与真违规**同码**。**解除条件**：让默认源缺失走「fail loud with 专用码/文案」或把默认源改为 `/dev/null` 语义；改判据须走 A-70 三步。t2 已把此发现写进订正件，我独立复现确认。
- **O7 `not_measured` G-21 uncovered 38 条**：口径已逐类成文（38/38 在册：已纳入 1 / 显式不纳入 13 / 留档待决 24），但**未纳入不构成覆盖**。**解除条件**：captain 裁定分批纳入计划后逐批跑绿回填。
- **O8 `blocked` B17-11 契约钉值 vs 现场**：`b17_governance_contract.py:723-724` 钉旧值 `multi_method_with_get=43 / uncovered=37`，现场 `44/38`。该脚本**不在** `ci_gates` 链内（不构成红），但写报告引用时按 A-70 三步处理。**解除条件**：A-70 重基线或保持只读报告口径。
- **O9 `not_counted_as_passed` 既有在案缺陷**：`/products/import` 表单层 `MultipleFileField`（`app/forms.py` ↔ `app/templates/products.html:896-898`，`test-reports-2026-10/B17-登记.md:187`）——我复跑 P4 时**同样必须**用表单垫片才能触达端点主体（印证该在案项仍存在）。**解除条件**：单列任务修复该表单字段后，复跑 `t7_b` P4 段与 `after_observations.py` 的 E 场景。
- **禁写「在册缺陷清零」**：本批关闭项与上列留档项**并存**；任何「清零/全绿」表述均与本件读数不符。

## 6. 门禁与真库读数（AC③ 评估）

- AC③ 字面要求：`ci_gates --phase first` **exit 0**；`check_doc_claims --selftest` = 26/26；真库三值恒等。
- 实测：`selftest 26/26` ✅；真库三值前/后逐字一致 ✅；`ci_gates` = `exit 2`（`blocking 失败=无`，唯一红 = 先在性 report-only `evidence_hash`）❌ 字面未达。
- ⇒ **AC③ 记 failed（字面口径）**；该未达**不是本批回归**（mtime 证据 + 两条 modified 均在 `harness/b17-verify/`，与 P/G 面实现 0 交集），解除条件 = O1。**不得**把「blocking 全绿」写成「门禁 exit 0」。

## 7. 交付件指纹对账（作者声明 vs 现场）

| 交付件 | 现场 `wc -l/-c` | 作者声明 | 对账 |
| --- | --- | --- | --- |
| `C-落点与在册项盘点.md` | 313 / 45051 | 313 行 / 45051 B | ✅ 一致 |
| `C-资产与口径订正.md` | 471 / 61233 | 471 行 / 60690 B，blob `1175a92f…` | blob ✅ 一致（prose 字节数陈旧，见 F4） |
| `C-注入面与锚点实测.md` | 276 / 22411 | 276 行 | ✅ 一致 |
| `C-P1P6P9P10-实现与读数.md` | 294 / 28215 | 自指 `head -n -1` = 293 / 27897 / `1a92548c…` | ✅ MATCH |
| `C-P2P3P4P5-实现与读数.md` | 203 / 17299 | 自指 202 / 16893 / `ceb4dd61…` | ✅ MATCH |
| `C-工具面覆盖口径.md` | 264 / 29166 | §5 自指 263 / 28566 / `7D7E8DBE…` | ✅ MATCH |
| 其它在盘复核件 | `C-P1P6P9P10-复核.md` 252；`C-P2P3P4P5-非作者复核.md` 99/14799；`C-写盘守卫-非作者复核.md` 222/18340；`C-工具面覆盖口径-非作者复核.md` 226（自指 MATCH 225/23723/`774384b6…`）；`…-round2.md` 219；`C-落点与在册项盘点-勘误附录.md` 150；`C-写盘守卫-实现与读数.md` 278/16497 | — | 均在盘，未被我覆盖（append-only） |

## 8. 未测项与复现边界

1. P9 非退化归属分支（F1）；2. P5 空行夹层（F2，已实测漂移，属 finding 不是未测）；3. G-13/G-15/G-18（O4）；4. A-63-STEP2 build gate（O2，环境无 docker）；5. G-21 38 条的纳入实施（O7）；6. coverage 冻结锚点重建（O5）；7. `evidence_hash` 转绿（O1）。
以上**一律不折算 pass**。

## 9. 证据索引（全部在 `test-reports-2026-10/evidence/c/t7/`）

| 文件 | 用途 | 指纹（行/字节/前缀） |
| --- | --- | --- |
| `p1_invariant_scan.py` | P1 AST 独立扫描器 | 158 / 5627 / `48245f3aeedcd347` |
| `t7_a_p1_p6_p9.py` + `t7_a.log` | P1/P6/P9 + 3 对照 | 380 / 15688 / `e0e75ddcc4e73bc1`；11 PASS |
| `t7_b_p2_p3_p4_p5.py` + `t7_b.log` | P2/P3/P4/P5 + 6 对照 | 293 / 13876 / `fe89d4ee804b6171`；`failed=['P5-edge']`（即 F2，其余 11 PASS） |
| `t7_c_g19_g21.py` + `t7_c.log` | G-19/G-21 + 2 对照 | 156 / 7619 / `dfbebd920cc20521`；6 PASS |
| `t7_d_inject_assets.sh` + `t7_d.log` | 注入面 + 资产口径面 | 93 / 6913 / `0f78ba47420bda90`；16 PASS |
| `t7_g_p3_authoritative.py` + `t7_g.log` | P3 权威载体 `/employees/import` | 6 PASS / exit 0 |
| `t7_f_p10.py` + `t7_f.log` | P10 补测 | 152 / 7348 / `5ddd75689ad7e84b`；10/10 PASS |
| `negctl/prefix_form.py`、`negctl/tl05/app/bad_inst_verify.py`、`negctl/dc_clean_verify.md`、`negctl/dc_ge135_verify.md`、`negctl/check_doc_claims_pin12806.py` | 阴性对照夹具 | 见 §4 |

`evidence/**` 被 `.gitignore:42` 忽略 ⇒ 本地留档，不追改、不入 git。

## 10. 声明

- 本件由**非作者**（verify-c）编写；作者脚本输出未作为通过依据（唯一例外 = §5.2-F1 明确标注的「复现性」读数，且已记 `not_measured`）。
- 未改任何判据、钉值、期望值；未改 `app/**`、`scripts/**`、`test-reports-2026-10/harness/**`、`docs/**`；发现的口径问题一律登记（F1–F4、O1–O9）。
- 未 `git add` / `commit` / `push`；真库只读三值前/后恒等；未跑任何 `flask db *`。
- **本批关闭 13 项 / 部分关闭 4 项 / 仍留档 9 项**；`ci_gates` 字面 exit 0 **未达成**（唯一红 = 先在性 report-only）；**禁写「在册缺陷清零」**。
