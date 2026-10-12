# E-收口轮非作者验证（t20，verify-c）

- **任务**：t20 —「收口轮非作者验证（含 t7 F1–F4 与失败成因闭合）：O1/O6/O9/O10 + t18/t19 交付件」
- **验证者**：`verify-c`（**非作者**，C9）；attempt `cc98b1dc-0781-4254-a077-e9c698e6db6d`
- **口径**：本件全部读数由验证者**自己重跑**（工具 + 口径 + 值）；不采信作者/captain 自述；判据不符即 finding，**不折算 pass**
- **开工基线（真库只读）**：`sha256sum app.db` = `34E48E7A21163DB390EEBDA4F2030343F3609AFEDC65D8C6E909D6EB5A49177E` / `stat -c '%s %y'` = `2531328` B / `2026-10-12 04:25:37.128430119 +0000`；**收工复核逐字一致**（三值同，见 §1.9）
- **HEAD**：开工 `b8e9ca0` → **会话中由 captain 提交 `e5956f1`**（`批次18-收口轮：O6/O9/O10 闭合 + O1 终态裁定 + t18/t19 交付件`，12 files / +1217 −16，**不含 `app/main/routes.py`**）；收工 HEAD = `e5956f1`。⇒ 该提交不影响本件读数：判据 1.1 的「`routes.py` 相对 HEAD 无改动」在 `b8e9ca0` 与 `e5956f1` 两时点均成立
- **解释器**：`/opt/wage-venv/bin/python`（3.11.2）；全程未跑 `flask db *`；PG 仅只读事务

---

## §1 十条判据：命令 / 口径 / 值

### 1.1（O9）`/products/import` 表单层修复
- **命令**：`/opt/wage-venv/bin/python -B test-reports-2026-10/harness/check_products_import_form.py`
- **口径**：脚本 A–E 五场景（单文件/多文件/`update_existing` 开/关/无文件）逐场景断言，判 `RESULT: OK` + exit 0
- **值**：`11/11 PASS` · `RESULT: OK` · **exit 0**（逐场景读数见脚本 stdout，11 条 [PASS] 无 [FAIL]/[SKIP]）
- **静态旁证**（我自查，非脚本）：`app/main/forms.py:216 class ProductImportForm`、`:221 file = FileField(...)`（**不再是 `MultipleFileField`**）、`:223 update_existing = BooleanField(...)`
- **`app/main/routes.py` 相对 HEAD 无本批改动**：`git diff --numstat HEAD -- app/main/routes.py` = 空；`git diff --ignore-cr-at-eol --numstat HEAD -- app/main/routes.py` = 空（两口径同为空 ⇒ 非行尾漂移；HEAD 取 `b8e9ca0` 与 `e5956f1` 两时点均空）
- **修复已入库**（`git diff HEAD~1 HEAD -- app/main/forms.py` = `7 2`）：`-from wtforms import … MultipleFileField …` → `+… FileField …`；`-file = MultipleFileField('Excel文件', …)` → `+file = FileField('Excel文件', …)`；`+update_existing = BooleanField('更新已存在产品')`。我另查：`app/**` 内 `MultipleFileField` **实际使用 0 处**（唯一命中 = `forms.py:220` 注释）、`forms.py` 通过 `ast.parse`、消费点 `app/main/routes.py:8374 if form.update_existing.data`
- **结论**：✅ **相符**

### 1.2（O6）`check_doc_claims.py` **裸跑**（不带 `--coverage`）
- **命令**：`/opt/wage-venv/bin/python -B scripts/check_doc_claims.py`
- **口径**：默认覆盖源 = 脚本内自动挑选的**最新** `evidence/harness/ci-run-*/coverage.json`（本轮自动选中 `ci-run-20261012-080259`），判 `29/29 相等` + `violations=0` + exit 0
- **值**：`钉常量 vs 权威源：29/29 相等` · `文档：扫描 5 份、带口径表 1 份` · `lock：33 条钉版 / 环境匹配 33 条 / exception 0 条` · `RESULT: OK（violations=0）` · **exit 0**
- **对照（历史）**：t7 时点裸跑 = `20/29 相等` / `violations=11` / exit 1（默认覆盖源 `evidence/harness/coverage.json` 缺失 ⇒ 9 键源值 None）⇒ 本轮闭合
- **结论**：✅ **相符**

### 1.3（敏感性）自造阴性对照：隔离副本中把权威源改坏
- **口径**：在**隔离副本**（`test-reports-2026-10/.tmp/r2t20/coverage_mut.json`，不动任何既有产物）把 `summary.method_level_GET` 由 `161` 改 `162`，再用**同一条命令形状**指定该产物
- **值**：`钉常量 vs 权威源：28/29 相等` · `[VIOLATION] 口径源漂移：method_level_GET 钉值 161 ≠ 源值 162` · `RESULT: FAIL（violations=1）` · **exit 1**
- **对照 2**：显式传不存在路径 ⇒ `USAGE_ERROR`（用法错误）· **exit 2**
- **结论**：✅ 放宽后**仍敏感**（0 → 1，单向变化）⇒ 裸跑绿不是「判据被放宽」的假绿

### 1.4（O6 附带）`--selftest`
- **命令**：`/opt/wage-venv/bin/python -B scripts/check_doc_claims.py --selftest`
- **值**：`[check_doc_claims] 自检 26/26 通过` · **exit 0**（夹具目录 `test-reports-2026-10/.tmp/r2t13-selftest`，26 条全 [PASS] 无 SKIP）
- **结论**：✅ **相符**

### 1.5（O10）PG 只读复算
- **命令**：`/opt/wage-venv/bin/python -B -`（`psycopg2` 直连 `postgresql+psycopg2://erpuser:***@192.168.50.243:25432/erpdb`，`conn.set_session(readonly=True, autocommit=False)`；**无任何 UPDATE/INSERT/DELETE**）
- **口径**：① `"user"` 表 `must_change_password IS NOT TRUE` 计数；② `audit_log` 中 `details LIKE 'B18 弱口令处置%'` 计数；③ `"user"` 表 `password_hash` 全量聚合 sha256
- **值**：① `must_change_password IS NOT TRUE` = **0**（总账号数 64）；② `details like 'B18 弱口令处置%'` = **64**；③ `password_hash` 聚合 = `7e19e04f6b879cbf11479fa771367a0af4d32d32630e0340624de9c6f8b8fbfa`；`show transaction_read_only` = `on`
- **结论**：✅ **相符**（三个值逐字一致）

### 1.6（O1）`evidence_hash.py` 默认校验
- **命令**：`/opt/wage-venv/bin/python -B test-reports-2026-10/harness/evidence_hash.py`
- **口径**：默认（只读）校验；期望「违规**恰为 2 条 `modified`** 且指向 b17-verify 两探针 + `coverage_gap` = 0 + 判定 `VIOLATION`」
- **值（我本轮读数，run `ci-run-20261012-081020` 的 `evidence_hash.gate.json` 同值）**：`基线文件数=2896 当前文件数=2907 改写=2 删除=0 流水损坏=0 新增(允许)=11 覆盖缺项=0 幽灵条目=0 篡改基线=0` · `violations` 恰 2 条且 `kind` 均为 `modified`：
  - `harness/b17-verify/probe_permission_matrix.txt`：`9627 B / 1664B44BF5FB227B…` → `11234 B / F81525C2B3CF4A5E…`
  - `harness/b17-verify/probe_smoke_test.txt`：`3186 B / 59A7E5F065716E43…` → `3186 B / DA0C377DA223D63B…`
  - 判定 `VIOLATION` / **exit 1**
- **先在性（我的独立证据）**：`probe_permission_matrix.txt` mtime `2026-10-12 04:45:29.081386626`；两文件内容改写均发生在 C 批实现轮之前；本轮 ci_gates 运行未触碰两文件（见 §2.3 的 journal 证据）
- **未见 `baseline_tampered` / `phantom_entry` / `journal_broken`**（均 0）
- **结论**：✅ **相符**（期望的三项全部命中）

### 1.7（O1 机制）「`--freeze` 清不掉 `modified`」+ 反洗白
- **代码口径（我读源码）**：
  - `test-reports-2026-10/harness/evidence_hash.py` `freeze()` docstring/实现：**只为「尚未登记（未被任何快照覆盖）」的目录写新快照，绝不改写/删除既有快照**；已登记目录走 `if target is None: reported['skipped_existing'].append(...)` 分支直接跳过（第 313-320 行）
  - `load_baseline()`（`:361-395`）**先读根 canonical 的递归 `tree` 并 `setdefault`（先见者胜）** ⇒ 后冻结的快照无法覆盖既有条目
  - 反洗白判据（`:471-498`）：索引快照自身被改写 ⇒ `[VIOLATION/baseline_tampered]`，其 `required_fix` 逐字「索引快照只追加；被删/被改必须从备份恢复，**不得靠重新冻结洗白**」
- **最小沙箱阳性对照（我自己搭，`/tmp/eh-mini/`，真树零写盘）**：
  1. 建 `evidence/{top.txt, sub/data.txt}` ⇒ `--freeze` ⇒ 校验 `判定 = OK（退出码 0）`、`改写=0`
  2. 改写 `sub/data.txt` ⇒ 再 `--freeze` ⇒ 校验仍 `改写=1`、`[VIOLATION/modified] sub/data.txt: 基线哈希被改写：2D27FBDF… → DAD4E221…`、`判定 = VIOLATION（退出码 1）`（**freeze 清不掉**）
  3. 反洗白：追加改写 `sub/artifact_hashes.json` ⇒ `[VIOLATION/baseline_tampered] sub/artifact_hashes.json: 基线索引快照被改写：CEA194CC… → C4156E90…（反洗白判据）`
- **钉住机制实测**：`index_inventory` 中记录根 `artifact_hashes.json` sha256（前缀 `DC6AFDAB69522E0F`）的快照数 = **166**（现时点；`2026-10-12 08:08:02` 一次冻结把索引快照扩到 155 份，此前为 **11** 份 ⇒ §5 F-1）
- **结论**：✅ **相符**（机制由源码 + 沙箱对照 + 现读数三路支持）

### 1.8 `ci_gates.py --phase first`
- **命令**：`/opt/wage-venv/bin/python -B test-reports-2026-10/harness/ci_gates.py --phase first`
- **值**：`steps=20` · `blocking 失败 = 无` · `report_only_failed=['evidence_hash']` · `root_json_untouched=true` · `injection_ineffective=[]` · **exit=2**（`exit_code_semantics`：`2 = 仅 report-only 失败`）；挂账 `A-63-STEP2-BUILD-GATE = blocked（不计入通过数）`；产物 `test-reports-2026-10/evidence/harness/ci-run-20261012-081020/`
- **20 步**：blocking 16 步全 `passed`（check_templates / check_migration_heads / check_table_parity / check_properties / check_db_bootstrap / run_gates / functional_test / permission_matrix / coverage_drift / check_notification_triggers / check_model_refs / check_http_contract / chain_count_consistency / negative_matrix / check_is_archived_policy / check_doc_claims），report-only 4 步中 `evidence_hash failed`、其余 3 步 `passed`
- **结论**：✅ **相符**（按本任务书口径：steps=20 且 blocking 失败=无；report-only 红已按 §1.6 逐条归因）

### 1.9（O8）B17-14 钉值 44/38 与变异体对照
- **命令**：`/opt/wage-venv/bin/python -B test-reports-2026-10/harness/b17_governance_contract.py --only B17-14`
- **值**：`[PASS] B17-14 多方法面进判据层 + docstring | 现场 exit=0：规则 273 / GET+写 N=44 / 未命中 M=38；判据层引用面键 {'test-reports-2026-10/harness/coverage_drift.py': 10, …}；变异体（M=0,N=99,明细清空）⇒ drift exit=1 FAIL=['D-9']（未变异 exit=0 FAIL=[]）；docstring 含 273=True、残留 271 行=[]` · **汇总 1 条：PASS 1 / FAIL 0 / BLOCKED 0** · **exit 0** · 工具自报真库 sha256 前后一致
- **静态对账（我自查）**：`test-reports-2026-10/harness/b17_governance_contract.py:730-731` 钉 `multi_method_with_get_total == 44` / `multi_method_with_get_uncovered == 38`；`test-reports-2026-10/harness/coverage_drift.py:20` D-9 判据 `== 44` / `== 38` / `len(list) == 38`
- **结论**：✅ **相符**

### 1.10 交付件指纹复算（行数 / 字节 / sha256）
| 文件 | 声明 | 我实测 | 结论 |
|---|---|---|---|
| `test-reports-2026-10/E-资产与口径收口.md` | 326 行 / 28799 B / `ba225388…f913f6aa892` | 326 / 28799 / `ba225388c8655d1d8808eec2c8d8332106f104b45227d57f5c674f913f6aa892` | ✅ 逐字一致 |
| `docs/订正-内联角色模板计数-2026-10-12.md` | 88 行 / 6974 B / `f28c55ae…5bcee97` | 88 / 6974 / `f28c55ae…5bcee97` | ✅ |
| `test-reports-2026-10/E-治理与污染收口.md` | 298 行 / 34818 B / `e7897ecd…48d726d9f` | 298 / 34818 / `e7897ecd9d797e4a72234b14fff7054d4475bb0b3721a15b0cbb05848d726d9f` | ✅ |
| `docs/订正-阶段C移交件状态列-2026-10-12.md` | 28 行 / 3582 B / `bee943911…27e744d1` | 28 / 3582 / `bee943911aa3acf6e3b4a776103388fa5b0c314de5390ccd2c143b6527e744d1` | ✅ |

### 1.11 §E-01/E-02/E-03 存在性与 append-only + 关键值抽查
- **存在性**：`test-reports-2026-10/B18-登记.md:997` `## §B18-E-01 资产与口径面收口（t18，2026-10-12 UTC）`；`:1073` `## §B18-E-02 治理与污染面收口（t19，2026-10-12 UTC，append-only）`；`:1139` `## §B18-E-03 captain 侧在册项收口…（2026-10-12 UTC，append-only）` ✅
- **append-only**：`git diff --numstat HEAD -- test-reports-2026-10/B18-登记.md` = `208 0`；`git diff --ignore-cr-at-eol --numstat HEAD -- …` = `208 0` ⇒ **删除行 0**（两口径同值 ⇒ 非行尾噪声）✅
- **抽查 §E-03 ④ 四条关键值**（`:1170-1171`）：
  1. 「违规恰 2 条 modified」⇒ **✅ 复现**（§1.6）
  2. 「`coverage_gap` = 0」⇒ **✅ 复现（读数点口径）**：我本轮 `ci-run-20261012-081020/evidence_hash.gate.json` = `coverage_gap: 0`；⚠ **现时点**（我后置复跑）为 `覆盖缺项=1`，成因 = 另一 actor 的守卫改名产物 `probe_permission_matrix.b17-verify.txt`（`08:12:07`）落在最近一次冻结（`08:08:02`）之后 ⇒ A-50 形态（记 §5 F-2，**保护方向不变，非虚假陈述**）
  3. 「11 份快照 `index_inventory` 钉住」⇒ **机制 ✅ / 计数 ✗**：现读数 **166**；`11` 在 `08:08:02` 冻结前为真（我用 mtime 时间轴独立复算：`≤08:00` 时 = 11，`08:08:02` 一次写入 155 份 ⇒ 之后 = 166）⇒ 记 §5 F-1
  4. 「反洗白条款原文逐字」⇒ **✅ 逐字复现**（`索引快照只追加；被删/被改必须从备份恢复，不得靠重新冻结洗白`，`evidence_hash.py` `baseline_tampered` 分支）
- **结论**：存在性/append-only ✅；4 条值 **2 条逐字复现 + 1 条读数点复现（现时点漂移）+ 1 条机制成立但计数漂移**

### 1.12 真库三值（开工/收工）
- **开工**：`34E48E7A21163DB390EEBDA4F2030343F3609AFEDC65D8C6E909D6EB5A49177E` / `2531328` / `2026-10-12 04:25:37.128430119 +0000`
- **收工**：同上**逐字一致**（HEAD 仍 `b8e9ca0`）
- **结论**：✅ 真库**只读**（全程零写入；所有运行时实验未使用真库，PG 走只读事务）

---

## §2 阴性对照与机制证据（自造，非作者脚本）

1. **§1.3 权威源篡改对照**：`method_level_GET 161 → 162` ⇒ `28/29` + `[VIOLATION]` + exit 1（绿基线 exit 0 的同命令形状）⇒ **转红**
2. **§1.3 对照 2**：显式传不存在路径 ⇒ `USAGE_ERROR` + exit 2
3. **§1.9 变异体对照**（工具内建，我复核读数）：`M=0 / N=99 / 明细清空` ⇒ `coverage_drift` exit=1 `FAIL=['D-9']`（未变异 exit=0）⇒ 判据非空转
4. **§1.7 最小沙箱对照**：`modified` 不因 `--freeze` 消除；改写索引快照 ⇒ `baseline_tampered`
5. **§1.7 现网活证据（最强的一条，非沙箱）**：`test-reports-2026-10/evidence/harness/b17-verify/evidence_journal.jsonl` 末两行
   - `2026-10-12 08:11:54` `requested=probe_smoke_test.txt` `written=probe_smoke_test.txt` **`renamed_by_guard=false` `` `reused_identical=true` `` `sha256=DA0C377D…`（内容与已存在件**逐字相同** ⇒ 原路径复用；mtime 更新、**字节未变**）
   - `2026-10-12 08:12:07` `requested=probe_permission_matrix.txt` `written=`**`probe_permission_matrix.b17-verify.txt`** **`renamed_by_guard=true`** `sha256=F05DA5CA…`（内容不同 ⇒ **改名保留，原文件一字未动**：原件仍 `11234 B / F81525C2…`、mtime `04:45:29`）
   ⇒ §E-03 `:1171`「成因已断根：同类改写此后只会改名保留」**由现场 journal 直接证实**

---

## §3 t7 的 F1–F4：逐条结论

| # | 事项 | 我的结论 | 依据 |
|---|---|---|---|
| **F1** | P9 非退化归属分支 `not_measured`（真库 `production_record` 0 行） | **未闭合**（保持 `not_measured`，不折算 pass） | `test-reports-2026-10/B18-登记.md:914`（§B18-C-10）；解除条件 = 副本库自造 batch 夹具 |
| **F2** | P5 空行夹层行号漂移（第 3 行全空 ⇒ 文案报「第 3 行」而 Excel 物理行号 4） | **未闭合**（部分关闭，low；本轮不改代码） | `B18-登记.md:915`；解除条件 = 显式口径 + A-70 |
| **F3** | t5 任务书 AR2 载体措辞（`/employees/import` vs 实际 `/process_prices/import`） | **已闭合**（任务书缺陷，以登记条为订正；两载体均通过） | `B18-登记.md:916` |
| **F4** | t2 订正件 prose 字节 60690 B vs 现场 61233 B | **已闭合**（字节读数陈旧；`git hash-object` = `1175a92f…` 与声明一致 ⇒ **内容未漂移**） | `B18-登记.md:917` |

**t7 唯一失败项（AC③ 字面 exit 0）的失败成因闭合链**：
1. `B18-登记.md:905-927`（§B18-C-10）记录 t7 实质完成、唯一失败项 = 契约 AC③ 字面不可达；captain **amend** 口径为「steps=20 且 blocking 失败=无」，report-only 红逐条归因登记；
2. `B18-登记.md:973-978`（§B18-C-12）记录 **t17 轮 2** 以修订口径复验 ⇒ 判据满足；
3. t7 的 13 项关闭 + 12 条自造阴性对照 + O1–O9 留档（`B18-登记.md:911-921`）不因该失败项被推翻，O1 转入 §E-03 终态。
- **我的补充证据**：t20 本轮 `ci_gates`（`ci-run-20261012-081020`）与 t17 的 `ci-run-20261012-065809` 同形态 ⇒ 修订口径下的「步骤数 20 / blocking 失败=无」**跨两次独立 run 稳定复现**。

---

## §4 O1 / O6 / O9 / O10 终态

| 编号 | 事项 | 终态 | 依据（本轮实测） |
|---|---|---|---|
| **O1** | `evidence_hash` 两探针先在性违规 | **未闭合 — `blocked`**（不折算 pass） | §1.6 复现（2 条 modified、判定 VIOLATION）；`B18-登记.md:1170-1171` 解除条件二选一：(a) 授权放宽反洗白判据（A-70 三步 + 归档件 + 非作者复核）(b) 从备份恢复两文件原始字节（当前环境已证不存在） |
| **O6** | `check_doc_claims.py` 裸跑假红 11 条 | **已闭合** | §1.2 裸跑 `29/29` + exit 0；§1.3/§1.4 敏感性与自检 |
| **O9** | `/products/import` 表单层 `MultipleFileField` | **已闭合** | §1.1 `11/11` + `RESULT: OK` + exit 0；`forms.py:221 FileField` / `:223 update_existing`；`routes.py` 无改动 |
| **O10** | PG 弱口令处置 | **已闭合** | §1.5 `0 / 64 / 7e19e04f…`（只读事务，`transaction_read_only=on`） |

---

## §5 本轮 findings（登记，不折算 pass）

| # | 级别 | 问题 | 依据 / 读数 | 建议修复 |
|---|---|---|---|---|
| **F-1** | low | §E-03 ④「**11 份**既有快照钉住根 canonical」为**时点计数**，现时点 = **166** | `B18-登记.md:1170`；我的独立时间轴：`≤2026-10-12 08:00` = 11 份，`08:08:02` 一次冻结写入 155 份索引快照 ⇒ 之后 166 份（全部记录同一 sha 前缀 `DC6AFDAB69522E0F`） | 计数类断言加**时点**与复算命令（如 `index_inventory` 计数命令），或改写为「≥11 份」；**方向为保护更强，不改变结论**（有 1 份即已触发反洗白） |
| **F-2** | low | §E-03 ④「`coverage_gap` = 0」为**时点读数**；现时点 = **1** | 我本轮 `ci-run-20261012-081020/evidence_hash.gate.json` = `coverage_gap: 0`（✅ 复现）；后置复跑 = `覆盖缺项=1`，唯一命中 = `harness/b17-verify/probe_permission_matrix.b17-verify.txt`（`08:12:07` 由**守卫改名**新建，落在 `08:08:02` 冻结之后 ⇒ A-50 形态） | 同上：加时点；或**明确「守卫改名产物需在下一次冻结后纳入」**的运维口径（否则每次改名都会短暂产生 1 条 coverage_gap） |

- 两条均为**登记值口径（时点）**问题，**不涉及判据/钉值改动**，不触发 A-70；不影响 §1 其它读数与 §4 终态。
- **未测项（`not_measured`，不折算 pass）**：`A-63-STEP2-BUILD-GATE`（本容器无 `docker`/Jenkins/GH 执行面）⇒ 与 §B18-E-02① 一致，解除条件 = 具备 CI 执行面后观测 1 轮构建；F1 的 P9 非退化分支同上。
- 我**未发现**任何判据/钉值在本轮被放宽（`check_doc_claims.py` 相对 HEAD 仍为 PINNED 重基线那一处；`ci_gates.py` 无改动）。

---

## §6 证据索引（本轮新建/只读引用）

- 命令产物（新目录，工具自建）：`test-reports-2026-10/evidence/harness/ci-run-20261012-081020/`（`ci_gates_first.console.txt` 46045 B、`coverage.json` 246692 B、`evidence_hash.gate.json` 223225 B、`gates.json` 15376 B …）
- 隔离副本与日志（仅本地临时件，未入 git）：`test-reports-2026-10/.tmp/r2t20/coverage_mut.json`（对照用篡改产物）、`.tmp/r2t13-selftest/`（`--selftest` 夹具）、`/tmp/t20_ci.log`、`/tmp/t20_ev_final.log`、`/tmp/eh-mini/**`（沙箱）
- 只读引用：`B18-登记.md:905-927 / :973-978 / :997 / :1073 / :1139 / :1170-1171`；`harness/evidence_hash.py`（`freeze`/`load_baseline`/反洗白分支）；`harness/_env.py:341-374 save_evidence`；`harness/b17-verify/evidence_journal.jsonl`（末两行）

---

## §7 声明

- 本件为**新建件**（`git status --porcelain` 显示为 `??`，未入暂存）；未覆盖/改写任何既有文件；`docs/**` 既有文件一字未改（captain 的 2 件 `订正-*` 为新建件，且已随 `e5956f1` 入库 ⇒ `git status --porcelain -- docs/` 现为空；我未创建/未 add 它们）
- **未** `git add` / `commit` / `push`（`push` 由人工决定）。会话中 captain 自行提交 `e5956f1`（含 `app/main/forms.py`、`scripts/check_doc_claims.py`、`B18-登记.md`、E-01/E-02 交付件等 12 件），非我操作；我工作区写入仅限本件与工具新建产物
- 未跑 `flask db migrate/upgrade`；未写真实库；PG 仅只读事务
- `evidence/**` 属本地留档（`.gitignore:42`），本轮只新增工具产物，未追改既有文件
- 判据/钉值/期望值**未改动**；发现的 2 条口径问题已登记（§5），交 captain 处置
- 指纹复算口径：全件 `wc -l` / `wc -c` / `sha256sum`；本件自指指纹见下（`head -n -1` 三级复算**三命令一致**）

- 复算命令：`wc -l` / `wc -c` / `sha256sum`（均对 `head -n -1` 的产物）

**本件指纹（自指行不可自证 ⇒ 以 `head -n -1` 三级为准；复算三命令逐字一致）**：`head -n -1 test-reports-2026-10/E-收口轮非作者验证.md` = `179 行 / 21233 B / sha256 `2f8bd8d265d84b05b43a079a34c82b39e6befb75c382fb8fa46e70aaed18c3b5``；全件行数 = 上述行数 + 1（本行为唯一自指行）
