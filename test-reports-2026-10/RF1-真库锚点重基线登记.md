# RF-1 真库锚点重基线登记（A-70）

- 登记件版本：v1（2026-10-09，批次15 开工前项 I1）
- 性质：**append-only**。本件一经落盘即不得回改既有段落；后续如有订正，一律在文末追加「附录 N」并注明订正对象与本轮触发项。
- 授权范围：本件登记的操作**是本批次唯一被授权写真实库 `app.db` 的动作**（任务 t2 / 触发项 RF-1，用户拍板「真库重基线」）。除本次外的任何写真实库动作仍需单独授权。
- 关联件：`test-reports-2026-10/B15-00-契约冻结.md` §3（RF-1 现场复核与判据）、`test-reports-2026-10/ALLOY-IMPORT-02-真库锚点重基线登记.md`（A-70 先例）、`test-reports-2026-10/B14-R1-锚点回退登记.md`、`test-reports-2026-10/B14-R3-NV1.5复标登记.md`。

---

## §0 一句话结论

真实库 `app.db` 已完成**一次正常首启播种**（`app/__init__.py` 启动路径 → `_seed_system_configs` → `InspectionTemplate.seed_defaults()`），净增 **9 行**（`inspection_templates` +2 / `inspection_items` +7，其余 73 表 Δ=0）；**文件字节数不变（2531328 B）**，SHA256 由 `F5DA2306…0E0F065` → `B4FB980C…EEAABE`；A-70 三步（①播种 ②阴性对照先红 ③重基线）全部实测留档；仓库内以真库读数作判据的代码位置共 **10 处**已按同一触发项前移（6 处 SHA256 钉值 + 1 处判据描述串 + 1 处 NV-1.5 口径 + 2 处行数口径），另有 **3 处**按队长裁决「移交 / 只登记不修」。终局：`negative_matrix` **28/28 全绿 exit 0**；`run_gates` 的 `gates.json` **`summary.fail == 0`** 且 `real_db` 段 `before == after == 新钉死值`、`unchanged == true`；`ci_gates --phase first` 仍 exit 1，残留**唯一** blocking 红点为 `ci_gates.py:695` 的 `6712` 期望串（**已移交 dev-tx 的 t5 承载**，非本任务可改），report-only 红点 `evidence_hash` 为**既有报告型红、与 RF-1 无关**（本轮判据已移除）。

---

## §1 触发项 ID 与授权来源

| 项 | 值 |
| --- | --- |
| 触发项 ID | **RF-1**（批次15 开工前项 I1「真库锚点重基线」） |
| 团队任务 | `t2`（kind=implementation，attempt 1，`attempt_id = 43964b4c-c23b-45d0-8377-cf0d5023ae1e`），成员 `ops-baseline` |
| 上游依赖 | `t1` 契约冻结 → `test-reports-2026-10/B15-00-契约冻结.md` §3（现场复核：`app/__init__.py:142/161-166/239-247` 无条件播种且真库 templates/items 均 0 行 ⇒ **活缺陷**） |
| 授权来源 | **用户拍板**：任务书 Objective 逐字「用户已拍板 RF-1 = 『真库重基线』…**这是本批次唯一被授权写真实库的任务**」 |
| 队长裁决 | ①`harness/run_gates.py` 前移获**批准**（契约 `inScope` 已 amend 加入该文件）；②`harness/ci_gates.py` 期望串**移交 dev-tx(t5)**，本任务不得改；③`harness/w1_p01_regress.py` / `harness/w2w3_probe.py` **只登记不修**（契约 `outOfScope` 已 amend 加入）；④acceptance ⑥ 的 `evidence_hash` 子项**已移除** |
| 仍生效的红线 | 禁 `flask db migrate`；**除 I1 外永不写真实 app.db**；`app/services/mes_service.py` 中 `qc_gate_allows_output(...)` 调用逐字不动；tracked 文件只增不删；smoke_test 不作验收 |

---

## §2 执行载体与操作步骤（A-70 第 1 步：播种）

### §2.1 改前留档（要求 ①）

播种前先做带时点副本 + 记录改前读数：

```bash
cd /root/code/MyERP
cp -p app.db app.db.bak-rf1-$(date +%Y%m%d_%H%M%S)     # 实际生成 app.db.bak-rf1-20261009_033829
chmod u+w app.db.bak-rf1-20261009_033829                # 便于后续对拍（不改内容）
sha256sum app.db ; stat -c '%s %y' app.db
```

**改前读数（实测，与验收书逐字一致）**

| 项 | 值 |
| --- | --- |
| 字节 | **2531328** |
| SHA256 | **F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065** |
| mtime_ns | **1789707055016880300**（= 2026-09-18 04:50:55.016880300 +0000） |
| 只读备份 | `app.db.bak-rf1-20261009_033829`（2531328 B，`cp -p` 保留 mtime = Sep 18 04:50） |

留档位置：仓库根 `app.db.bak-rf1-20261009_033829`（`.gitignore:21-22` 的 `/app.db.bak-*` 覆盖，不进 tracked 面）。

### §2.2 执行器与命令

执行器：`test-reports-2026-10/.tmp/run-b15/rf1_seed.py`（**未跟踪**，`.gitignore:40-44` 覆盖 `.tmp/`）。
动作序列：只读指纹 → 逐表行数 → `from app import create_app; create_app()` → 复取指纹 + 75 表逐表 diff → 打印 `__RF1__{json}`。

**关键安全设计**：脚本**不设 `DATABASE_URL`**，落 `config.py:8-9/17` 的默认 URI；并在脚本内 `assert` URI 含 `MyERP/app.db`（实测 `db_uri = "sqlite:////root/code/MyERP/app.db"`），杜绝「改写副本却以为改了真库」或反向误伤。

```bash
cd /root/code/MyERP
/opt/wage-venv/bin/python -B test-reports-2026-10/.tmp/run-b15/rf1_seed.py \
  > test-reports-2026-10/.tmp/run-b15/rf1_seed_run1.out 2> .../rf1_seed_run1.err   # 第一次首启
/opt/wage-venv/bin/python -B test-reports-2026-10/.tmp/run-b15/rf1_seed.py \
  > test-reports-2026-10/.tmp/run-b15/rf1_seed_run2.out 2> .../rf1_seed_run2.err   # 幂等复跑
```

两次 `stderr` 均 **0 字节**，`exit 0`。

### §2.3 播种链路（现场行号）

`app/__init__.py:239` `with app.app_context():` → `:243 _ensure_schema(app)` → `:246 bootstrap_if_empty(app)` → `:247 _seed_system_configs(app)` → `:153 SystemConfig.seed_defaults()` → `:162 InspectionTemplate.seed_defaults()`（定义在 `:142-170`）。
`bootstrap_if_empty` 因 `seed.db` / `SEED_SQLITE_PATH` **不存在**直接 return；`user` 表已有 64 行再加一道早退 ⇒ 自举不写库。`InspectionTemplate.seed_defaults()`（`app/models.py:804`）按 **type** 判存在性（非 template_code），只补缺不覆盖。

---

## §3 旧值 → 新值（要求 ③）

### §3.1 文件级指纹

| 项 | 旧值（播种前） | 新值（播种后） | Δ |
| --- | --- | --- | --- |
| 字节 | 2531328 | **2531328** | **0（不变）** |
| SHA256 | F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065 | **B4FB980C5D1B25B3C3A0EADC12ECF01C75B36EBD213B109E5DD190C617EEAABE** | 变化 |
| mtime_ns | 1789707055016880300（2026-09-18 04:50:55.016880300 +0000） | 1791517179418764055（2026-10-09 03:39:39.418764055 +0000） | 变化 |

> 字节数不变而 SHA256 变化的原因：SQLite 在原有 page 空洞/空闲页内落入了新行，文件尺寸未增长。**故凡以「字节数」为判据的位置本轮不需前移**（见 §5.3）。

### §3.2 逐表 Δ（工具 + 口径 + 值）

- **工具**：`test-reports-2026-10/.tmp/run-b15/rf1_seed.py`（播种前后各全表 `select count(*)`），另以只读复算脚本二次核对（`sqlite3 ... mode=ro`）。
- **口径**：75 张表（`select name from sqlite_master where type='table'`，与 `analysis_ledger.py:301` 一致：`rows_business = rows_total − rows_in(alembic_version)`）。
- **值**：`tables_total = 75`；实测 `alembic_version` 1 行 ⇒ `rows_total 6713 → 6722`、`rows_business 6712 → 6721`、`zero_row_tables 49 → 47`（两表由 0 行转非 0）。

| 表 | 播种前 | 播种后 | Δ | 判定依据 |
| --- | --- | --- | --- | --- |
| `inspection_templates` | 0 | **2** | **+2** | 新增行标识见 §3.3 |
| `inspection_items` | 0 | **7** | **+7** | 新增行标识见 §3.3 |
| `system_configs` | 5 | 5 | **0** | `SystemConfig.DEFAULTS`（`app/models.py:2706-2745`）恰 5 项；真库 5 行的 key/值/type/category 与 DEFAULTS **逐 key 相同** ⇒ `seed_defaults()` 只补缺不覆盖，零净增 |
| 其余 72 表 | — | — | **0** | 逐表 `count(*)` 前后相同（含 `audit_log`、`user` 未变） |

> **口径差声明（必须留档）**：任务书写的是 `inspection_template_items`，**本仓库不存在该表**。实际表名为 **`inspection_items`**（`app/models.py:918`）与 **`inspection_templates`**（`app/models.py:747`）。本件按实际表名登记，避免后续按任务书字面 grep 得出「0 命中」的假结论。

### §3.3 新增行标识（逐行）

`inspection_templates`（2 行）

| id | template_code | name | type | is_active | created_by |
| --- | --- | --- | --- | --- | --- |
| 1 | `SYS-QC-PROD-REC` | 生产质检（系统默认） | `production_record` | 1 | 1 |
| 2 | `SYS-QC-GOODS-REC` | 来料检（系统默认） | `goods_receipt` | 1 | 1 |

`created_by = _seed_creator_id()`（优先 `role=admin` 的最小 id，实测 =1）。

`inspection_items`（7 行）

| id | template_id | name | sort_order |
| --- | --- | --- | --- |
| 1 | 1 | 外观 | 1 |
| 2 | 1 | 尺寸 | 2 |
| 3 | 1 | 材质·规格符合性 | 3 |
| 4 | 2 | 外观 | 1 |
| 5 | 2 | 尺寸 | 2 |
| 6 | 2 | 材质·规格符合性 | 3 |
| 7 | 2 | 到货数量 | 4 |

### §3.4 幂等（要求 ④）

同一路径再跑一次首启（`rf1_seed_run2`）：

| 读数点 | 字节 | SHA256 | mtime_ns |
| --- | --- | --- | --- |
| run1 `before`（= 旧值） | 2531328 | F5DA2306…0E0F065 | 1789707055016880300 |
| run1 `after` | 2531328 | **B4FB980C…EEAABE** | 1791517179418764055 |
| run2 `before` | 2531328 | **B4FB980C…EEAABE** | 1791517179418764055 |
| run2 `after` | 2531328 | **B4FB980C…EEAABE** | 1791517179418764055 |

run2 的 `changed_tables = {}`（75 表**全 Δ=0**），且 **mtime 也未变** ⇒ 第二次首启对真库**零写入**，`seed_defaults()` 的「按 type 判存在」幂等性成立。

---

## §4 同批一并前移的处（A-70 四要素：文件:行 / 旧值→新值 / 说明）

前移判据：**该处是否以真实库读数作判据**（而非仅留档）。全部 10 处同属触发项 RF-1，故必须同批更新，否则 `t6_ledger_check.py:184` 的交叉断言或门禁必红。

### §4.1 SHA256 钉值（单一声明源 + 4 个「读现场真库」重算器 + 1 个交叉断言）

| # | 文件:行 | 旧值 → 新值 | 说明 |
| --- | --- | --- | --- |
| 1 | `test-reports-2026-10/harness/_env.py:94` | `REAL_DB_SHA256_EXPECTED` `F5DA2306…` → `B4FB980C…` | **唯一权威声明源**；`_env.assert_real_db_untouched()` 是唯一硬闸（`fixtures.py:123` 首行调用 ⇒ 钉值不更新则 NV-1.2…NV-5.1 全 blocked） |
| 2 | `test-reports-2026-10/harness/t6_ledger_check.py:40` | `PINNED_DB_SHA` `F5DA2306…` → `B4FB980C…` | `:184` 断言 `PINNED_DB_SHA == _env.REAL_DB_SHA256_EXPECTED`（**交叉断言**，二者必须同改）；实测 `--selftest` ⇒ `判定 = OK（9/9）` |
| 3 | `test-reports-2026-10/harness/improve_plan.py:42` | `REAL_DB_*` → 新值 | `:594/:801` `matches_pinned` **现读真库** ⇒ 活判据 |
| 4 | `test-reports-2026-10/harness/analysis_ledger.py:43` | 同上 | `:281` `'unchanged': sha == REAL_DB_PINNED`，`sha = sha256_file(REAL_DB)` **现读** ⇒ 活判据 |
| 5 | `test-reports-2026-10/harness/final_recount.py:43` | 同上 | `:456` 现场读 `sha256_of(REAL_DB)`、`:491 db_same = (db_after == db_before == REAL_DB_PINNED)`、`:334` 与 evidence JSON 对拍 ⇒ 活判据（文件头部逐字声明「不打开真实库」，但仍读指纹） |
| 6 | `test-reports-2026-10/harness/reconcile_r2.py:96` | 同上 | `:814 'equals_frozen': sha == REAL_DB_SHA`、`:1014` **现读** ⇒ 活判据 |

### §4.2 判据串与口径复标

| # | 文件:行 | 旧值 → 新值 | 说明 |
| --- | --- | --- | --- |
| 7 | `test-reports-2026-10/harness/negative_matrix.py`（NV-1.1） | 描述串硬编码 `'…等于 F5DA2306…0E0F065'` → 由常量派生 `'sha256(app.db) 三次一致且等于 %s…%s' % (REAL_DB_SHA256_EXPECTED[:8], REAL_DB_SHA256_EXPECTED[-5:])` | 消除同类陈旧期望（判据本体 `sha == before_hash == REAL_DB_SHA256_EXPECTED` 未动，仅描述串改为派生） |
| 8 | `test-reports-2026-10/harness/negative_matrix.py`（NV-1.5 **口径复标**） | 判据由 B14-R3 的 `… and post_deviates and all(v > 0 for v in deltas.values())` → `pre_sha == REAL_DB_SHA256_EXPECTED and copy_is_real_file is False and not unattributed and deviation_explained`（`deviation_explained = post_deviates == bool(deltas)`）；criterion 名追加「/ RF-1 复标」；新增记录键 `seeding_delta_total` / `post_bootstrap_deviates` | **复标理由**：真库播种后已自带 2 模板/7 条目 ⇒ 引导副本 `seed_defaults()` 按 type 命中既有行、**零净增** ⇒ 引导后副本指纹 == 钉死值、`seeding_deltas` 为空，B14-R3 的「必然偏离」前提失效（旧判据会对**正确状态**报红）。新判据是唯一等价式：**引导前**副本指纹仍须等于钉死值，**引导后**的偏离与 `seeding_deltas` 必须**同时为空或同时非空**。note 内保留逐字「**不得据此放宽隔离保证**：`copy_is_real_file`（samefile）仍是硬判据，NV-1.2/1.3/1.4 未动」。 |

> 本条（#8）属 A-70「同批有意更新」，与本件 §8 的阴性对照配套：旧口径在播种后**必然红**，实测见 §8.2。

### §4.3 行数口径（真库 business 行数 6712 → 6721）

| # | 文件:行 | 旧值 → 新值 | 说明 |
| --- | --- | --- | --- |
| 9 | `test-reports-2026-10/harness/run_gates.py:57` | `EXPECTED['bootstrap_copied_rows'] 6712` → **6721** | `gates.json` 是本文件唯一产物，不改则 `summary.fail != 0`（acceptance ⑥ 直接依赖）。前值系 B14-R1 回退 ALLOY-IMPORT-02 导入期值 10172 的结果。**队长裁决①批准**（`inScope` 已 amend 加入本文件） |
| 10 | `test-reports-2026-10/harness/final_recount.py:329` | `("rows_total", 6713), ("rows_business", 6712), ("zero_row_tables", 49)` → `("rows_total", 6722), ("rows_business", 6721), ("zero_row_tables", 47)` | 与 `:43` 同批前移的一致性期望。**该块仅在 `evidence/analysis/real_db_recount.json` 存在时生效，而该件当前不存在 ⇒ 本轮未参与门禁**（属预防性前移，避免将来生成该件时对正确状态报假红） |

### §4.4 `_env.py` 注释块的同步声明

`test-reports-2026-10/harness/_env.py` 的 RF-1 段随 #1/#3~#6/#9/#10 一并增补：列出四处「读现场真库」重算器的**新行号**（`improve_plan.py:42` / `analysis_ledger.py:43` / `final_recount.py:43` / `reconcile_r2.py:96`）、「行数口径同批前移」段、以及「**已移交他任务（本处只作声明，不得在本任务内改）**」段。
`_env.py:48-66` 原有的 A-70/B14-R1 历史注释块**逐字保留未删**，其中 `:63-65`「冻结历史件……一律不动」原句仍在。

---

## §5 穷举与逐条归类（要求 ⑤）

### §5.1 用于穷举的 grep 命令（tracked 面）

```bash
cd /root/code/MyERP
# (A) SHA256 字面量维度（多模式，含派生变量名与时间字面）
git ls-files -z | xargs -0 grep -lI -e "F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065" \
  -e "REAL_DB_SHA256_EXPECTED" -e "2531328" -e "1789707055" \
  -e "2026-09-18 04:50:55" -e "2026-09-18 12:50:55" -e "2026-09-18T04:50:55"     # → 155 files
# (B) 全值维度（HEAD 基线 / 工作区改后对照）
git grep -lI "F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065" HEAD   # → 132 files（.py 19）
git ls-files -z | xargs -0 grep -lI "F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065"  # → 124 files（.py 13）
git ls-files -z | xargs -0 grep -lI "B4FB980C5D1B25B3C3A0EADC12ECF01C75B36EBD213B109E5DD190C617EEAABE"  # → 恰 6 files
# (C) 行数口径维度（本轮新发现的遗漏面）
git ls-files -z '*.py' | xargs -0 grep -nI -e "6712" -e "6713" -e "6721"                          # → 6 处（见 §5.2）
# (D) 字节 / mtime 维度
git ls-files -z '*.py' | xargs -0 grep -nI -e "2531328" -e "1789707055016880300" -e "2026-09-18 0"
git ls-files -z '*.py' | xargs -0 grep -nI -e "inspection_templates" -e "inspection_items"        # → harness 内 0 处计数判据
```

命中清单留档（均未跟踪，目录已被 `.gitignore:40-44` 覆盖）：
`test-reports-2026-10/.tmp/run-b15/rf1_tracked_hits.txt`（泛模式 155 件）、`rf1_hits_oldsha_after.txt`（改后仍含旧全值的 124 件）、`rf1_hits_newsha_after.txt`（含新全值的 6 件）。

**关键结构事实**：非 `docs/` 且非 `test-reports-2026-10/` 前缀的 tracked 命中**只有 `scripts/_remediate_b13_02_audit_log.py` 一个**；`test-reports-2026-10/.tmp/`、`test-reports-2026-10/evidence/`、仓库根 `.tmp/`、`.analysis-scratch/`、`.agent-teams/` 均被 gitignore ⇒ 不进重基线面。

### §5.2 逐条归类（判据 / 仅留档 / 历史件）与处置

**〔判据〕已改 10 处** —— 见 §4.1(#1–#6)、§4.2(#7–#8)、§4.3(#9–#10)。判据性证据（逐个现场读值，非名字推断）：

| 文件:行 | 类别 | 判据性证据（现场读到的表达式） |
| --- | --- | --- |
| `_env.py:94` | 判据 | `assert_real_db_untouched()`(:205-211) 偏离即 `RuntimeError`，`:167 real_db_is_target` 只判 samefile |
| `t6_ledger_check.py:40` | 判据 | `:184 assert PINNED_DB_SHA == _env.REAL_DB_SHA256_EXPECTED`（交叉断言） |
| `improve_plan.py:42` | 判据 | `:594/:801 matches_pinned`（现读真库） |
| `analysis_ledger.py:43` | 判据 | `:281 'unchanged': sha == REAL_DB_PINNED`（`sha` 现读） |
| `final_recount.py:43` | 判据 | `:491 db_same = (db_after == db_before == REAL_DB_PINNED)` |
| `reconcile_r2.py:96` | 判据 | `:814 'equals_frozen': sha == REAL_DB_SHA`（现读） |
| `negative_matrix.py` NV-1.1 | 判据 | `:152-158 record(...)` + `:996-998 NV-0`；`:1004-1005 real_db_ok`；`:1011-1012` 非 passed 即 infra_error |
| `negative_matrix.py` NV-1.5 | 判据 | `:197-224 record(...)`（口径复标见 §4.2 #8） |
| `run_gates.py:57` | 判据 | `EXPECTED['bootstrap_copied_rows']` → `gates.json` → ci_gates `summary.fail` |
| `final_recount.py:329` | 判据（惰性） | `if rd:`（`real_db_recount.json` 不存在 ⇒ 本轮不生效） |

**〔仅留档〕有意不改 2 处**

| # | 文件:行 | 内容 | 不改理由（现场依据） |
| --- | --- | --- | --- |
| 11 | `test-reports-2026-10/harness/r2_v14_ledgerbook.py:351-357` | 历史条目字面量（criterion / expected / observed / criterion_digest 四字段） | 该处是**自洽历史条目**（verdict='HIT'，四字段互证），不含任何「现读真库 vs 钉值」比较；改动会破坏自洽与 append-only 语义 |
| 12 | `scripts/_remediate_b13_02_audit_log.py:66-71` | `PRE_ANCHOR` + `:67` 字节 `2531328` + `:69-70` 旧 mtime | 行前注释逐字「§5.3 前置 ③ 的『整治前』锚点（**原值，append-only 留档，不得被覆盖**）」；全文仅 `:229/:340` 两处 `out()` **打印**、无比较 ⇒ 非判据。且**字节数未变**（2531328→2531328）⇒ 即使按数值也无需前移 |

**〔历史件〕有意不改**（带日期批次档，A-70 历史惯例 + 队长裁决③）

| # | 位置 | 内容 | 不改理由 |
| --- | --- | --- | --- |
| 13 | `test-reports-2026-10/reconcile-2026-10-08/*.py`（10 个：`check_t8_registration` / `probe_backend_field` / `probe_t1_notes_keyerror` / `probe_t3_pick_process_price` / `probe_t3_salary_delta` / `probe_t4_reviewer_independent` / `probe_t5_salary_rework_split` / `probe_t6_verifier_independent` / `probe_t7_reviewer_independent` / `probe_t8_salary_basis_delta`） | 硬编码旧全值 | 带日期批次目录，`_env.py:63-65` 逐字列为「冻结历史件，一律不动」 |
| 14 | `docs/test-reports/_probe/verify_acceptance_baseline.py:63` | `print(f'  期望值 = …')` | 纯打印、**无断言**；同属 `_probe` 历史件 |
| 15 | `test-reports-2026-10/harness/w1_p01_regress.py:60` | `['种子库账号数（经自举导入到空库）= 64', '直接拷贝 6712 行，跳过 0 张表']` | **RF-1 后已陈旧**（`6712` 应为 `6721`）；**本批有意不改** —— 未接入 ci_gates/run_gates 链（`25-W2W3修复说明.md:299` 逐字「不参与 CI 链条」），**队长裁决③：只登记不修**；契约 `outOfScope` 已 amend 加入 |
| 16 | `test-reports-2026-10/harness/w2w3_probe.py:1140` | `['6712', 'RESULT' if False else 'OK:']` | 同上（**RF-1 后已陈旧、本批有意不改**）；将来若修须走 A-70 |
| 17 | `test-reports-2026-10/harness/ci_gates.py:692`(注释)/`:696` | `'直接拷贝 6712 行，跳过 0 张表'` | **RF-1 后已陈旧、已移交 dev-tx(t5) 承载**（队长裁决②：本任务不得修改 `ci_gates.py`）；见 §9 |
| 18 | 全部带日期 `.md` / `.json` / `.txt` 历史档（改后仍含旧全值的 124 件中除上表外的部分） | 旧值与旧读数 | 历史记录，append-only，不得回改 |

### §5.3 明确「不需前移」的面（附证据）

| 维度 | 命令 | 结果 | 结论 |
| --- | --- | --- | --- |
| 字节数 | 见 §5.1(D) | `.py` 内 `2531328` 仅 `scripts/_remediate_b13_02_audit_log.py:67`（留档件）及注释 | **字节未变 ⇒ 无需前移** |
| mtime 字面 | 见 §5.1(D) | 旧 mtime 字面仅 `scripts/_remediate_b13_02_audit_log.py:69-70` | 同上（非判据） |
| 模板/条目计数 | 见 §5.1(D) | harness 内**无任何**以 `inspection_templates` / `inspection_items` 计数为判据的位置（命中全在 `app/models.py`、`migrations/**`、`docs/test-reports/_probe/*`） | 无需前移 |
| 门禁编排 | `grep -rn "analysis_ledger\|final_recount\|reconcile_r2\|t6_ledger_check\|r2_v14_ledgerbook\|improve_plan" test-reports-2026-10/harness/ci_gates.py test-reports-2026-10/harness/run_gates.py` | **0 命中** | 上列重算器均不被 `ci_gates`/`run_gates` 直接调度（改动属「防假红」而非「改门禁」） |

---

## §6 阴性对照（A-70 第 2 步：改写钉值**之前**必须先红）

### §6.1 工具与命令

```bash
cd /root/code/MyERP
/opt/wage-venv/bin/python -B test-reports-2026-10/harness/negative_matrix.py \
  --out /root/code/MyERP/test-reports-2026-10/.tmp/run-b15/negative_matrix_i1.json
```

**时点**：播种已完成、**钉值尚未改写**（`_env.REAL_DB_SHA256_EXPECTED` 仍为旧值 `F5DA2306…`）。
**证据**：stdout 全文 `test-reports-2026-10/.tmp/run-b15/nm_prerebase.stdout`；JSON 副本 `test-reports-2026-10/.tmp/run-b15/negative_matrix_i1_PREREBASE.json`。

### §6.2 原始 stdout 行（逐字）与退出码

```
[negative_matrix] 真实库开工 SHA256 = B4FB980C5D1B25B3C3A0EADC12ECF01C75B36EBD213B109E5DD190C617EEAABE
  [FAILED ] NV-1.1  真实库 SHA256 跑前 == 跑后 == 钉死值
            expected={'before': 'B4FB980C…EEAABE', 'pinned': 'F5DA2306…0E0F065'}
            actual  ={'now': 'B4FB980C…EEAABE'}
  [FAILED ] NV-0  收尾：真实库 SHA256 仍等于钉死值
            expected={'sha256': 'F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065'}
            actual  ={'sha256': 'B4FB980C5D1B25B3C3A0EADC12ECF01C75B36EBD213B109E5DD190C617EEAABE', 'mtime_ns': 1791517179418764055}
[negative_matrix] 合计 7 条：passed=0 failed=2 blocked=5
[negative_matrix] 真实库异常？ 否（SHA256 未变）
[negative_matrix] 基础设施级问题：['真实库 SHA256 发生漂移（严重）', '5 条用例 blocked（探针未跑出结论）', '隔离用例 NV-1.1 未通过（隔离能力本身不可信）', '隔离用例 NV-1.2 未通过（隔离能力本身不可信）']
```

**退出码 = 1**（`NM_PREREBASE_EXIT=1`）。

**归因**：`_env.assert_real_db_untouched()` 在 `fixtures.py:123` 首行抛 `RuntimeError: 真实库 app.db 已偏离钉死哈希`，导致 5 条依赖 `make_isolated_app()` 的探针连 `__GUARD__` 标记都拿不到 ⇒ 记为 `PROBE_NOT_RUN`（blocked）。**这正是「钉值必须前移」的实测证明**：不先红就直接写新值，等于跳过了 A-70 第 2 步。

> 同时注意 `真实库异常？ 否（SHA256 未变）` 一行：该行比的是**跑前/跑后**（同为本轮新值），未与钉值比对，故不红 —— 与 NV-1.1/NV-0 的失败**不矛盾**。

### §6.3 行数口径的阴性对照

`run_gates` 在**期望未改**（`6712`）时实测红点（`ci-run-20261009-034254`）：

```
[ci_gates]      !! gates_json summary.fail == 0
[ci_gates]      !! gates_json 4 项进链门禁全 pass
[ci_gates]      !! gates_json 进链门禁逐项 checks 全过
```

其中 `check_db_bootstrap` 步的失败 needle 逐字 `!! expects 直接拷贝 6712 行，跳过 0 张表`。改 `run_gates.py:57` → `6721` 后 `run_gates` 步**不再失败**（见 §7.2）。

---

## §7 重基线后转绿（要求 ⑥）

### §7.1 verify 命令 1：negative_matrix

```bash
/opt/wage-venv/bin/python -B test-reports-2026-10/harness/negative_matrix.py \
  --out /root/code/MyERP/test-reports-2026-10/.tmp/run-b15/negative_matrix_i1.json
# → exit 0
```

```
[negative_matrix] 合计 28 条：passed=28 failed=0 blocked=0
[negative_matrix] 真实库异常？ 否（SHA256 未变）
[negative_matrix] 基础设施级问题：无
```

stdout 全文 `test-reports-2026-10/.tmp/run-b15/nm_final.stdout`。关键条目：`[PASSED ] NV-1.1 真实库 SHA256 跑前 == 跑后 == 钉死值`、`[PASSED ] NV-1.5 口径校准：引导前副本指纹 == 真实库钉死值；引导后偏离须由实测写入解释（B14-R3 复标 / RF-1 复标）`、`[PASSED ] NV-0 收尾：真实库 SHA256 仍等于钉死值`。
NV-1.5 实测：`pre_bootstrap.sha256 == post_bootstrap_sha256 == B4FB980C…EEAABE`、`post_bootstrap_bytes 2531328`、`samefile_with_real false`、`seeding_deltas {}`、`seeding_delta_total 0`、`unattributed_deltas []`、`post_bootstrap_deviates false`、`deviation_explained true`、`byte_copy_rejected_by_fingerprint_guard true`、`real_db_templates == copy_templates == [id1 SYS-QC-PROD-REC/production_record, id2 SYS-QC-GOODS-REC/goods_receipt]`。
JSON `real_db` 段：`{"before":{"sha256":"B4FB980C…","bytes":2531328,"mtime_ns":1791517179418764055},"after":<同值>,"unchanged":true,"pinned":"B4FB980C…"}`。

### §7.2 verify 命令 2：ci_gates --phase first

```bash
/opt/wage-venv/bin/python -B test-reports-2026-10/harness/ci_gates.py --phase first
# → exit 1
```

```
[ci_gates] steps=15 blocking 失败 = ['check_db_bootstrap']
[ci_gates] report-only 失败 = ['evidence_hash']
[ci_gates] 注入未生效 = 无
[ci_gates] 仓库根两 JSON 未被触碰 = True（A-11）
[ci_gates] gaps: A-63-STEP2-BUILD-GATE = blocked（不计入通过数）
[ci_gates] exit = 1  phase=first
```

stdout 全文 `test-reports-2026-10/.tmp/run-b15/ci_gates_first_final.stdout`；证据目录 `test-reports-2026-10/evidence/harness/ci-run-20261009-034734/`（`gates.json` / `evidence_hash.gate.json` / `ci_gates_first.console.txt`）。

**达成的两条（acceptance ⑥ 前两句）**

- `gates.json`：`summary = {"total": 6, "pass": 5, "fail": 0, "probe_only": 1, "probe_unexpected": 1, "in_gate_chain": ["check_templates","check_migration_heads","check_properties","check_db_bootstrap"], "report_only": ["route_inventory"], "evidence_only": ["route_inventory_native_probe"]}` ⇒ **`summary.fail == 0`** ✔
  （独立复跑 `run_gates.py --out .tmp/run-b15/gates_rf1_run.json` 同口径：`summary.fail=0`、`real_db.before == after == B4FB980C…`、`unchanged=true`；其自身 exit=1 系 A-62「环境依赖探针，不得重基线化」的 `route_inventory_native_probe` 所致，与本触发项无关。）
- `gates.json` 的 `real_db` 段：`unchanged = True`、`before.sha256 = after.sha256 = B4FB980C5D1B25B3C3A0EADC12ECF01C75B36EBD213B109E5DD190C617EEAABE` ⇒ **before == after == 新钉死值且 unchanged=true** ✔

**残留的唯一 blocking 红点（显式标注，不得折算为 pass）**

```
[ci_gates]      !! expects 直接拷贝 6712 行，跳过 0 张表
```

来源 = `test-reports-2026-10/harness/ci_gates.py:695` 的 `check_db_bootstrap` 步期望串（`6712` 应为 `6721`）。
**状态：已移交 dev-tx(t5) 承载**（队长裁决②：`ci_gates.py` 是 dev-tx 的唯一在写文件，两任务同写会丢更新；该条已作为 t5 契约第 8 条 acceptance）。本任务**零改动** `ci_gates.py`。依据与现场直跑读数：`scripts/check_db_bootstrap.py` 独立执行 exit 0、逐字打印 `直接拷贝 6721 行，跳过 0 张表` / `种子库账号数（经自举导入到空库）= 64` / `OK: 空库自举、幂等、无种子库跳过、整表无遗漏 均通过` ⇒ 期望串是本轮唯一陈旧项，**非真库异常**。

**report-only 红点（既有、与 RF-1 无关、本轮判据已移除）**

```
[ci_gates]      !! whitelist whitelist has no stale exact entry
[ci_gates]      !! whitelist wildcard rule(s) match >=1 violation
[ci_gates]      !! pinned real_db_matches_pinned == true
```

根因（结构性、非本轮引入）：`ci_gates.py:296` 读 `evidence_hash.gate.json` 的 `real_db_matches_pinned`，而 `evidence_hash.py` 在 `verdict=no_baseline`（根索引 `artifact_hashes.json` 不存在）时**早退**，该键只在 `evidence_hash.py:577-578` 的 `verify()` 正常路径与 `:849-850` 的 `--selftest` 分支写入 ⇒ `bool(None) = False` 恒失败。
现场反证：`_env.REAL_DB_SHA256_EXPECTED` 与 `_env.sha256_file(_env.REAL_DB)` **同为** `B4FB980C…EEAABE`。
历史对照：`ci-run-20261008-220300`、`ci-run-20261008-220943`、`ci-dsh-envcheck-033706`（**均在 RF-1 之前**）三次运行的 `real_db_matches_pinned: false` 与该 needle `status: failed` **逐字存在**。
处置：登记为「既有报告型红」；`ci_gates.py` 与 `evidence_hash.py` 均被 `outOfScope` 逐字点名，本任务**零改动**。

### §7.3 RF-1 前 / 后逐步骤对照（证明红点归属）

| 运行 | 时点 | blocking 失败 | report-only 失败 |
| --- | --- | --- | --- |
| `ci-dsh-envcheck-033706` | **RF-1 前** | **（无）** | `evidence_hash` |
| `ci-run-20261009-034254` | RF-1 后、`run_gates.py` 未改 | `check_db_bootstrap`、`run_gates` | `evidence_hash` |
| `ci-run-20261009-034734` | RF-1 后、`run_gates.py` 已改 | **`check_db_bootstrap`（仅此一处，已移交）** | `evidence_hash`（既有） |

⇒ RF-1 引入的红点**只有行数口径一条链**；`evidence_hash` 三条 needle 与 RF-1 无关。

---

## §8 归档与回退方法（要求 ⑦）

### §8.1 归档

| 件 | 路径 | 说明 |
| --- | --- | --- |
| **旧库副本** | `/root/code/MyERP/app.db.bak-rf1-20261009_033829` | 2531328 B，`cp -p` 保留 mtime = Sep 18 04:50；SHA256 = 旧值 `F5DA2306…0E0F065` |
| 播种原始读数 | `test-reports-2026-10/.tmp/run-b15/rf1_seed_run{1,2}.{out,err}` | 含 `__RF1__{json}` 全文（`db_uri`、before/after 三值、`tables_total 75`、`changed_tables`、逐行明细） |
| 阴性对照原文 | `test-reports-2026-10/.tmp/run-b15/nm_prerebase.stdout`、`negative_matrix_i1_PREREBASE.json` | 第 2 步证据 |
| 重基线后读数 | `test-reports-2026-10/.tmp/run-b15/nm_final.stdout`、`negative_matrix_i1.json`、`ci_gates_first_final.stdout`、`gates_rf1_run.json` | 第 3 步证据 |
| 穷举清单 | `test-reports-2026-10/.tmp/run-b15/rf1_tracked_hits.txt`、`rf1_hits_oldsha_after.txt`、`rf1_hits_newsha_after.txt` | §5 证据 |
| 门禁证据目录 | `test-reports-2026-10/evidence/harness/ci-run-20261009-034734/`、`ci-run-20261009-034254/`、`ci-dsh-envcheck-033706/` | 含 `gates.json` / console |

> 副本与 `.tmp/`、`evidence/harness/` 均为 gitignore 覆盖（`.gitignore:21-22`、`:40-44`），不进 tracked 面。

### §8.2 回退方法（**必须把钉死值与 app.db 一并还原**）

单向回退到播种前状态，三步缺一不可：

```bash
cd /root/code/MyERP
# ① 还原真库（先备份当前态以防再次需要）
cp -p app.db app.db.bak-rf1-rollback-$(date +%Y%m%d_%H%M%S)
cp -p app.db.bak-rf1-20261009_033829 app.db
# ② 钉值还原：8 处 SHA256/口径常量（§4.1 #1–#6、§4.2 #7、§4.3 #10）
#    B4FB980C5D1B25B3C3A0EADC12ECF01C75B36EBD213B109E5DD190C617EEAABE
#    → F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065
#    行数口径同步回退 run_gates.py:57 6721→6712、final_recount.py:329 6722/6721/47→6713/6712/49
# ③ 校验：sha256(app.db) == 旧值；再跑 verify 命令 1/2 应回到「RF-1 前」的红/绿形态
```

**注意**：`nm_*` / `rf1_*` / `ci-run-*` 证据不准删除（append-only）；回退只动 `app.db` 与钉值常量。
**另注**：回退 `negative_matrix.py` 的 NV-1.5 口径时应**保留** RF-1 复标（新判据是旧判据的超集：`post_deviates` 由硬条件降为「与 `deltas` 同真同假」），否则会在**正确状态**上产生假红。

---

## §9 未决事项与移交声明

| # | 事项 | 状态 | 承载方 |
| --- | --- | --- | --- |
| 1 | `test-reports-2026-10/harness/ci_gates.py:692(注释)/:696` 的 `直接拷贝 6712 行，跳过 0 张表` | **RF-1 后已陈旧、本批不改**；移交依据 = 队长裁决②（该文件是 dev-tx 的唯一在写文件，避免丢更新；已作为 t5 契约第 8 条 acceptance） | **dev-tx（t5）** |
| 2 | `test-reports-2026-10/harness/w1_p01_regress.py:60`、`test-reports-2026-10/harness/w2w3_probe.py:1140` 的同类陈旧期望（`6712`） | **RF-1 后已陈旧、本批有意不改**；队长裁决③「只登记不修」（未接入 ci_gates/run_gates 链，`25-W2W3修复说明.md:299` 逐字「不参与 CI 链条」） | 未分配；将来若修须走 A-70 |
| 3 | `evidence_hash` 的 `real_db_matches_pinned == true` needle | **既有报告型红、与 RF-1 无关、本轮判据已移除**（队长裁决④：从 acceptance ⑥ 移除）；根因见 §7.2 | `ci_gates.py` / `evidence_hash.py`（均 `outOfScope`，本轮零改动） |
| 4 | `route_inventory_native_probe` 的 `native_exit=0 expected=1 verdict=unexpected` | **A-62 明令「环境依赖探针，不得重基线化」**；现场 `git diff --ignore-cr-eol --numstat` 显示队友并发改动 `app/main/routes.py`(53/50) 等 | 与本任务无关 |

---

## §10 验收对照（七条）

| # | 验收项 | 结果 | 证据 |
| --- | --- | --- | --- |
| ① | 改前留档（副本 + 改前读数） | **passed** | §2.1（2531328 / F5DA2306…0E0F065 / mtime 2026-09-18 04:50:55.016880300 +0000；副本 `app.db.bak-rf1-20261009_033829`） |
| ② | 阴性对照**先红** | **passed** | §6.2（exit 1；`[FAILED ] NV-1.1` / `[FAILED ] NV-0` / `合计 7 条：passed=0 failed=2 blocked=5`）+ §6.3（行数口径红点） |
| ③ | 播种可归因（逐表 Δ + 新增行标识 + 工具/口径/值 + 播种后 bytes/SHA256） | **passed** | §3.1–§3.3（+2/+7；`system_configs` Δ=0 依据；新值 B4FB980C…EEAABE / 2531328 B） |
| ④ | 幂等 | **passed** | §3.4（run1.after == run2.before == run2.after 三值全同，run2 Δ 全 0） |
| ⑤ | 重基线完整（穷举命令 + 完整清单 + 逐条归类 + 处置理由） | **passed** | §5.1–§5.3（判据 10 改 / 留档 2 不改 / 历史件 6 类不改，逐条给依据） |
| ⑥ | 重基线后转绿 | **passed（按队长 amend 后口径）** | §7.1（28/28 exit 0）+ §7.2（`gates.json summary.fail==0`；`real_db` before==after==新值、`unchanged=true`）。残留唯一 blocking 红点 = `ci_gates.py:695`，**已显式标注为「已移交 t5 承载」，未折算为 pass**；`evidence_hash` 子项已从判据移除 |
| ⑦ | 登记件 append-only（触发项 ID、旧→新、A-70 三步命令与原始读数、副本归档路径、回退方法） | **passed** | 本件 §1 / §3 / §2+§6+§7 / §8.1 / §8.2 |

---

## 附录 A：本件引用的命令一览（可复跑）

```bash
cd /root/code/MyERP
# A-70 第 1 步（播种，已在 2026-10-09 03:39 执行）
/opt/wage-venv/bin/python -B test-reports-2026-10/.tmp/run-b15/rf1_seed.py
# A-70 第 2 步（阴性对照先红，改钉值前）
/opt/wage-venv/bin/python -B test-reports-2026-10/harness/negative_matrix.py --out test-reports-2026-10/.tmp/run-b15/negative_matrix_i1.json
# A-70 第 3 步（重基线后验证）
/opt/wage-venv/bin/python -B test-reports-2026-10/harness/negative_matrix.py --out /root/code/MyERP/test-reports-2026-10/.tmp/run-b15/negative_matrix_i1.json
/opt/wage-venv/bin/python -B test-reports-2026-10/harness/ci_gates.py --phase first
/opt/wage-venv/bin/python -B test-reports-2026-10/harness/run_gates.py --out test-reports-2026-10/.tmp/run-b15/gates_rf1_run.json
/opt/wage-venv/bin/python -B test-reports-2026-10/harness/t6_ledger_check.py --selftest
/opt/wage-venv/bin/python -B scripts/check_db_bootstrap.py
```

（本件到此结束。后续订正一律追加「附录 B / C …」，不得回改以上段落。）

---

## 附录 B（追加 · 2026-10-09 03:50）：§7.2 唯一 blocking 红点已由 t5 落地清除，门禁终局形态

**追加事由**：§7.2 记录的残留唯一 blocking 红点（`ci_gates.py:692/:696` 的 `直接拷贝 6712 行，跳过 0 张表`）标注为「已移交 dev-tx(t5) 承载」。其后 dev-tx 已把该 needle 前移（同批 RFC 注释，前值来源与本件 §4.3 #9 同源），本次复跑确认该红点**已消失**。本节为**追加记录，不回改 §7.2 原文**。

**命令与读数（逐字）**

```bash
cd /root/code/MyERP
/opt/wage-venv/bin/python -B test-reports-2026-10/harness/ci_gates.py --phase first
# → exit 2
```

```
[ci_gates] steps=16 blocking 失败 = 无
[ci_gates] report-only 失败 = ['evidence_hash']
[ci_gates] 注入未生效 = 无
[ci_gates] 仓库根两 JSON 未被触碰 = True（A-11）
[ci_gates] gaps: A-63-STEP2-BUILD-GATE = blocked（不计入通过数）
[ci_gates] exit = 2  phase=first
[ci_gates] exit_code_semantics={...,"inputs": {"blocking_failed": [], "report_only_failed": ["evidence_hash"], "root_json_untouched": true, "injection_ineffective": []}}
```

- 步数由 15 → **16**（dev-tx 本批新增 `chain_count_consistency` 步）；**`blocking 失败 = 无`**。
- `exit = 2` 的语义（逐字取自输出）：`2 = 仅 report-only 失败` ⇒ **不存在任何 blocking 红点**。
- stdout 全文 `test-reports-2026-10/.tmp/run-b15/ci_gates_first_final2.stdout`；证据目录 `test-reports-2026-10/evidence/harness/ci-run-20261009-034959/`。

**`gates.json`（`ci-run-20261009-034959`）**

```
summary = {"total": 6, "pass": 5, "fail": 0, "probe_only": 1, "probe_unexpected": 1,
           "in_gate_chain": ["check_templates","check_migration_heads","check_properties","check_db_bootstrap"],
           "report_only": ["route_inventory"], "evidence_only": ["route_inventory_native_probe"]}
real_db.unchanged = True
real_db.before = {"path":"app.db","sha256":"B4FB980C5D1B25B3C3A0EADC12ECF01C75B36EBD213B109E5DD190C617EEAABE","bytes":2531328,"mtime_ns":1791517179418764055}
real_db.after  = <与 before 逐字段相同>
```

⇒ `summary.fail == 0` ✔；`real_db` **before == after == 新钉死值** 且 `unchanged == true` ✔。

**残留 report-only 与真库收尾复核**

- 仍存 3 条 report-only needle（逐字：`!! whitelist whitelist has no stale exact entry`、`!! whitelist wildcard rule(s) match >=1 violation`、`!! pinned real_db_matches_pinned == true`），即 §7.2 已归因的**既有报告型红、与 RF-1 无关**（`ci_gates.py` / `evidence_hash.py` 均 `outOfScope`，本任务零改动）。
- 真库收尾复核（只读）：`bytes = 2531328`、`sha256 = B4FB980C5D1B25B3C3A0EADC12ECF01C75B36EBD213B109E5DD190C617EEAABE`、`mtime_ns = 1791517179418764055` ⇒ 与 §3.1 新值、§3.4 幂等读数**三处一致**，播种后无任何后续写入。

**对 §10 验收表的影响**：验收 ⑥ 的状态不变（`passed`，按队长 amend 后口径），但证据由「残留 1 处 blocking 红点（已移交）」升级为「**blocking 红点清零**（`blocking 失败 = 无`，exit 2 = 仅 report-only 失败）」。§4.4 中「已移交他任务」段的声明仍然有效（本任务始终零改动 `ci_gates.py`）。

---

## 评审订正（追加 · 2026-10-09 · t13 集成落定 · append-only）

> **触发**：`t13`（Kind=integration，attempt 1，`attempt_id=063ed9a7-7538-467b-b97a-073d17914cef`）任务书第 7 条验收 —— 落定 R1 评审（`t8`，attempt 2 复核）对本登记件的 **O-1 / O-3** 两项事实订正。
> **性质**：本节为**纯追加**；上方 §0–§10 与附录 A/B **一字未改**（历史段保留原样，便于追溯当时的笔误）。两项均为**文档层笔误 / 归因订正**，**不改变任何判据、钉值、读数与结论**。

### 订正 1（O-1）：§3.3 所列列名 `sort_order` 应为 **`order_num`**；条目名应为「材质/规格符合性」

一手复现（`t13` 本轮实跑，全程只读真库、`mode=ro`）：

```bash
cd /root/code/MyERP
/opt/wage-venv/bin/python - <<'PY'
import sqlite3
c=sqlite3.connect('file:app.db?mode=ro',uri=True)
print(c.execute("PRAGMA table_info(inspection_items)").fetchall())
print(c.execute("SELECT * FROM inspection_items ORDER BY id").fetchall())
PY
git grep -nI sort_order | wc -l
```

实际读数：

- `PRAGMA table_info(inspection_items)` 共 18 列，**末列为 `order_num`**：`(17,'order_num','INTEGER',0,None,0)`；全表**不存在** `sort_order`（`any('sort_order' in col_name) = False`）。
- `inspection_items` 7 行实测：`(1,1,'外观',…,1)`、`(2,1,'尺寸',…,2)`、`(3,1,'材质/规格符合性',…,3)`、`(4,2,'外观',…,1)`、`(5,2,'尺寸',…,2)`、`(6,2,'材质/规格符合性',…,3)`、`(7,2,'到货数量',…,4)`。
  ⇒ **条目名真库值为「材质/规格符合性」（斜杠，U+002F）**；登记件 §3.3 写的「材质·规格符合性」（间隔号，U+00B7）为**文档笔误**。
- `git grep -nI sort_order` ⇒ **0 命中**（全树 tracked 面）。
- 旁证（R1 评审件附录 A.2）：`app/models.py:763/765/767/777/779` 均为 `'order_num': n`。

**订正口径**：§3.3 表中「列名 `sort_order`」应读作 **`order_num`**；该小节条目名应读作 **`材质/规格符合性`**。**判据与结论不变** —— §3.3 的用途是逐行标识新增行，列名仅作定位说明，`order_num` 与 `sort_order` 所指位置相同；**无需**修改任何代码、钉值或真库。

### 订正 2（O-3）：「124 vs 126 文件数差」的归因 = `grep -I` 二进制启发式差集，**与 t3 的 append 无关**

一手复现（`t13` 本轮实跑）：

```bash
cd /root/code/MyERP
V=F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065
git -c core.quotepath=false grep -lI "$V" | wc -l          # 法 A（git grep -I）
git ls-files -z | xargs -0 grep -lI "$V" | wc -l           # 法 B（GNU grep -I）
comm -23 <(git -c core.quotepath=false grep -lI "$V" | sort) \
         <(git ls-files -z | xargs -0 grep -lI "$V" | sort) # A − B
```

实际读数：

- 法 A（`git grep -lI`） = **126** 个文件（其中 `.py` 13 个）。
- 法 B（`git ls-files -z | xargs -0 grep -lI`） = **124** 个文件（其中 `.py` 13 个）。
- A − B 差集**恰为 2 件**：
  - `test-reports-2026-10/00b-裁定与纪律增补.md`（237109 B；**1 个 NUL，首个 @ 偏移 52369**）
  - `test-reports-2026-10/24-P01修复说明.原始输出.txt`（62270 B；**614 个 NUL，首个 @ 偏移 59765**）
- `test-reports-2026-10/81-后续开发与测试规划.md` 与 `test-reports-2026-10/90-新DSH交接-批次12-14收口与恢复点.md`（即 t3 的 append 落点）在**两种清单中都在** ⇒ **124 / 126 的差与 t3 的 append 无关**。

**归因**：GNU grep 的 `-I` 判「含 NUL 即二进制」并**整体跳过**该文件；`git grep -I` 仅按文件头启发式判定，仍将这两件当文本命中 ⇒ 差值纯属**工具启发式**，不代表任何文件「新增 / 丢失」，也不影响 §5.2 的归类（两件均属 §5.2 #18 类「带日期历史档」，处置不变：**只登记不修**）。

**订正口径**：日后引用「旧全值命中文件数」时，须**同时标明计数法与口径**（`git grep -lI` = 126 / `ls-files + grep -lI` = 124），不得单说「124 或 126」；**不得**再将该差值归因于 t3 的 append。§5 的穷举结论**不变**（受 tracking 的 18 项改动与钉值面已由 §4 / §5.2 覆盖）。

### 本节回退方法

删除本节（`## 评审订正` 起至文末）即可回到本登记件在 `t13` 之前的原状；**无需**任何代码 / 钉值 / 真库动作（本节零代码改动、零真库写入）。两处笔误若日后要修，只能在**新追加段**内声明，**不得回改 §3.3 原行**（append-only 纪律）。

**本节追加后本件指纹（现算，2026-10-09 · t13）**：正文追加（即本节 62 行）落盘后、加本尾注前实测 —— **565 行 / 44241 B / `sha256 = c9653898865e15b92afeeda26e4da15736bed77234be81b91da138600fd6f62a`**；追加前为 503 行 / 39638 B / `sha256 = d559fc517df4649c752d2aa8c8a2b0a701af7ce4a1c0317db996ac7f2fcbefa0`（已以 `head -c 39638 | sha256sum` 复核：**历史段字节级未改**）。本尾注自身只增行，不回改任何既有段落。
