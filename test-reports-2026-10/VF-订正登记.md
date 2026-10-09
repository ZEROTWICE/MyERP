# VF 订正登记（批次15 开工前项 I2）

> **性质**：**append-only 登记件**。本件**只追加**，不删既有行、不重写历史；被订正件（`81-` / `90-` / `B15-00-契约冻结.md` / `B14-T7-汇总评审报告.md`）的**原值一律保留**，本件与 `81- 附录 E` / `90- §13` 只提供**取代后的唯一有效读法**。
> **触发项**：批次15 开工前项 **I2** —— VF-2 / VF-3 / VF-5 / VF-6 / VF-7 / VF-8 / VF-9 一次性订正 + **RF-5** 登记（队长追加）。
> **任务 / attempt**：`t3` / `6220d696-b767-49d1-9e5b-e5ac8f28f43a`。
> **授权来源**：`90-新DSH交接-批次12-14收口与恢复点.md` §8 挂账表（`:315` 行「VF-2 / VF-5 / VF-6 / VF-7」）与 §10（`:357` 行「开工前应先处理：§8 的 RF-1 与 RF-2；并把 VF-2/VF-3/VF-5/VF-6/VF-7 一次性订正」）；`test-reports-2026-10/B15-00-契约冻结.md` §3.3–§3.8（判据 `C-VF-2.a` / `C-VF-3.a` / `C-VF-5.a/.b` / `C-VF-6.a/.b` / `C-VF-7.a` / `C-VF-8.a/.b`）；**VF-9** 与 **RF-5** 为队长本轮裁定新增（`w2w3_probe` 内嵌陈旧期望 / 报工 `update_status` 第 4/5 内层块原子性缺口）。
> **解释器**：`/opt/wage-venv/bin/python`；工作目录 `/root/code/MyERP`（本容器唯一钉版环境）。
> **红线遵守**：未写真实 `app.db`（本轮真库只读复核，见 §10.3）；未跑 `flask db migrate`；tracked 文件**只增不删**；`app/services/mes_service.py` 中 `qc_gate_allows_output(...)` 调用逐字未动（§10.4）。

---

## §0 一句话结论

七条 VF 一次性订正完成：**代码面只动 2 处**（`app/models.py:953` 注释按方案 A 对齐 = VF-3；`app/services/mes_service.py` 的 `pick_template` 类型守卫 = RF-2，附属于 VF-7 的行号口径订正）；**文档面在 `81- 附录 E` 与 `90- §13` 追加取代读法**（不删原行）；**VF-9 与 RF-5 只登记不修**（VF-9 两文件未接入门禁链；RF-5 真修需改 services 提交契约、属批次15 outOfScope）；**验证层判据（`coverage_drift.py` 的 `LOCKED` / `ANCHOR_READING`、`ci_gates.py`、`evidence_hash.py`）一字未改**。

---

## §1 逐条状态总表

| 项 | 主题 | 处置 | 落点 | 判据 ID |
| --- | --- | --- | --- | --- |
| **VF-2** | 契约文本 `rules_total 271` 陈旧（现场 = 273） | **订正**（文档面） | `81- 附录 E` + `90- §13` | `C-VF-2.a` |
| **VF-3** | `app/models.py:953` 注释未随方案 A 更新 | **订正**（代码面，仅注释） | `app/models.py:953` | `C-VF-3.a` |
| **VF-5** | 验证层判据自指风险 / 锚点与现行口径不一致 | **订正**（登记 + 自证未放宽） | 本件 §4 | `C-VF-5.a/.b` |
| **VF-6** | `run_gates` 裸 exit 1 不得作红/绿信号 | **订正**（口径 + 并列留档） | 本件 §5 + `90- §13` | `C-VF-6.a/.b` |
| **VF-7** | 契约措辞 `mes_service.py:94` 兜底链（实际 `:89-93` + `:96-111`） | **订正**（文档面） | 本件 §6 + `81- 附录 E` | `C-VF-7.a` |
| **VF-8** | `coverage.json` 冻结锚点期望句过期（244575 B / `F0D37A6C…`） | **订正**（期望句改判据型） | `90- §13` | `C-VF-8.a/.b` |
| **VF-9** | `w2w3_probe` 内嵌陈旧期望（23 文件 / 271 路由 / 6712 行） | **只登记不修** | 本件 §8 | — |
| **RF-5** | 报工 `update_status` 第 4/5 内层块：被调方自带 `rollback`/`commit` | **只登记不修**（下游挂账） | 本件 §9 | — |

---

## §2 VF-2：契约文本 `rules_total 271` 陈旧（现场与锁定值 = **273**）

**改前**（陈旧文本落点，逐行）

| 文件:行 | 逐字原值（保留不删） |
| --- | --- |
| `test-reports-2026-10/81-后续开发与测试规划.md:57` | 「凡引用『路由 **271**/269/265、能力 44、模板 87…』等，一律**连口径**引用 §6.3」 |
| `test-reports-2026-10/81-后续开发与测试规划.md:462` | `& $py -B scripts/route_inventory.py                 # 报告型：271/0（退出码不进链）` |
| `test-reports-2026-10/81-后续开发与测试规划.md:650` | L1 静态表期望值列含 `271/0`（`route_inventory` 项） |
| `test-reports-2026-10/81-后续开发与测试规划.md:923` | `& $py -B scripts/route_inventory.py            # total rules=271 / duplicate=0（报告型；退出码不进链）` |
| `test-reports-2026-10/90-新DSH交接-批次12-14收口与恢复点.md:315` | §8 挂账行：「VF-2 / VF-5 / VF-6 / VF-7 … 契约 271 vs 273 … 批次15 开批时一次订正」 |
| `test-reports-2026-10/90-新DSH交接-批次12-14收口与恢复点.md:359` | 「附录 A 已知陈旧 6 处 …：`route_inventory` total rules 271→**273**」 |

**改后**（取代读法）

- `rules_total` 的**唯一有效值 = 273**（等值口径，**不是下界**）；`duplicate (method,path) registrations = 0`。
- 273 = 271 + **2 条合金钢 POST**（`/process_prices/import_alloy` = `main.import_alloy_process_prices`、`/products/import_bom_alloy` = `main.import_alloy_bom`，用户裁定保留 + 正式重基线，见 `90- §7.2` `:299`）。
- `81-`/`90-` 前文所有 `271` 一律按本行读作 273；**不得**把 `LOCKED['rules_total']` 放宽为 `>=271`（口径是等值）。

**证据**（本轮一手，2026-10-09）

| # | 工具 + 命令 | 原始读数 |
| --- | --- | --- |
| ① | `/opt/wage-venv/bin/python -B scripts/_sandbox_compat.py scripts/route_inventory.py` | `[routes] total rules=273` / `[routes] duplicate (method,path) registrations=0`（`RI_EXIT=0`；stdout 留档 `test-reports-2026-10/.tmp/run-b15/vf_route_inventory.out:1-2`） |
| ② | `sed -n '161,171p' test-reports-2026-10/harness/coverage_drift.py` | `LOCKED = {` / `'rules_total': ('==', 273),` / `'method_level_non_get_total': ('>=', 157),` / `'writable_rules_non_get': ('==', 155),` / `'writable_literal_covered_by_all': ('>=', 108),` / `'writable_any_covered_by_all': ('>=', 116),` / `}` / `UNCOVERED_WRITABLE_MAX = 0` / `SMOKE_TARGETS = 148` / `SMOKE_UNRESOLVED = 9` / `ROUTE_RULES = 273` |
| ③ | `grep -n "rules_total" test-reports-2026-10/evidence/harness/ci-run-20261009-035515/coverage.json`（该轮 `ci_gates --phase first` 产物） | `"rules_total": 273` |

**未改清单（本批 `harness/**` 为 t3 outOfScope，逐条登记，将来若改须走 A-70 三步）**

| 文件:行 | 内容 | 处置 |
| --- | --- | --- |
| `test-reports-2026-10/harness/coverage_drift.py:12/134/138/148-149/155/158` | A-70 历史记录块内 `271→273` 的**过程留档** | 不改（`:104` 注释逐字「冻结锚点（`29` §4 声明锚点之一；**只作历史留档**，不参与判据）」） |
| `test-reports-2026-10/harness/measure_coverage.py:6/450` | 自述「规则总数 271」 | 不改（outOfScope；报告型脚本，退出码不进链） |
| `test-reports-2026-10/harness/final_recount.py:274` | `("routes_total_rules", "271")` | 不改（outOfScope；历史对拍口径） |
| `test-reports-2026-10/harness/r2_c07_probe.py:77/114/947`、`harness/r2_v14_ledgerbook.py:266/271`、`harness/verify_t4.py:270/278` | 历史批次探针/账本内 `271` | 不改（历史件） |
| `test-reports-2026-10/harness/w1_p01_regress.py:13/58`、`harness/w2w3_probe.py:1138` | 陈旧期望 `total rules=271` | 不改（**VF-9**：只登记不修，见 §8） |

**回退**：本项只追加文档段（`81- 附录 E`、`90- §13`），原行未删 ⇒ 回退 = 删除这两个追加段；代码面无改动。

---

## §3 VF-3：`app/models.py:953` 注释未随方案 A 更新（三类 → 四类，含 `goods_receipt`）

**改前**（逐字，`app/models.py:953`）

```python
    target_type = db.Column(db.String(20), nullable=False, comment='检验对象类型(product/production_record/material)', index=True)
```

**改后**（逐字，`app/models.py:953`）

```python
    target_type = db.Column(db.String(20), nullable=False, comment='检验对象类型(product/production_record/material/goods_receipt；自动创建为 workpiece/heat_lot)', index=True)
```

**证据**

| # | 工具 + 命令 | 原始读数 |
| --- | --- | --- |
| ① | `sed -n '953p' app/models.py` | 上式改后行逐字可查；`grep -n "检验对象类型" app/models.py` ⇒ `:953` 唯一命中 |
| ② | `git diff --ignore-cr-at-eol --numstat -- app/models.py` | `1	1	app/models.py` ⇒ **+1/−1 级别，只动该注释行**；该列其余部分（`db.String(20)` / `nullable=False` / `index=True` / 列名 `target_type`）逐字未变 |
| ③ | `grep -n "_VALID_TASK_TYPES" app/main/quality.py` | `:630`（`create_task` 入口校验）、`:1570 _VALID_TASK_TYPES = ('product', 'production_record', 'material', 'goods_receipt')`、`:1718`（导入校验） |
| ④ | `awk 'NR>=840 && NR<=890 && /target_type ==|^def /{...}' app/services/mes_service.py` | `:844 def apply_inspection_result(record):` / `:854 if task.target_type == 'workpiece':` / `:856 elif task.target_type == 'heat_lot':` / `:861 elif task.target_type == 'goods_receipt':` / `:865 elif task.target_type == 'production_record':` |

**集合口径现场实测（四个集合，供裁定；本件不做隐藏放宽）**

| 集合 | 值 | 大小 | 现场出处 |
| --- | --- | --- | --- |
| A. 注释**原列** | product / production_record / material | **3** | `app/models.py:953` 改前行 |
| B. 注释**现列** | product / production_record / material / goods_receipt（+ 补注「自动创建为 workpiece/heat_lot」） | **4** | `app/models.py:953` 改后行 |
| C. `apply_inspection_result` **实际分派集** | workpiece / heat_lot / goods_receipt / production_record | **4** | `app/services/mes_service.py:854/856/861/865` |
| D. `InspectionTask.target_type` **可达写入域** | product / production_record / material / goods_receipt（`_VALID_TASK_TYPES`）∪ {workpiece, heat_lot}（自动创建） | **6** | `app/main/quality.py:1570/630/1718` + `app/main/routes.py:3720` + `app/main/equipment.py:320` / `app/main/stock.py:60` / `app/main/purchase.py:379` |

**口径差声明（须由复核/队长裁定，本件不得自行放宽）**：`B15-00-契约冻结.md:366` 的 `C-VF-3.a` 写「与 `apply_inspection_result` 实际分派值集合**相等**（**5 类**）」，但现场**不存在**任何大小为 5 的集合（A=3 / B=4 / C=4 / D=6）。t3 验收 ④ 逐字为「按已拍板方案 A 对齐（**三类 → 四类，含 `goods_receipt`**）」，故实现取 **B（= A + `goods_receipt`）**，并把自动创建值 `workpiece`/`heat_lot` 以同句补注形式保留信息量。`C-VF-3.a` 的「5 类」与代码不符，**建议订正为「4 类」或显式声明取 D 口径**（该订正不在 t3 授权范围内，本件只登记）。

**回退**：`git checkout -- app/models.py`（或把 `:953` 注释还原为上表「改前」逐字行）；该行是纯注释，回退无行为影响。

---

## §4 VF-5：验证层判据自指风险 + 冻结锚点与现行口径不一致（**本批未放宽任何判据**）

**改前（风险面）**：`B14-T7-汇总评审报告.md:141` 指出「本批内改了验证层文件」⇒ 判据自指风险；`90- §6.1-②`/§6.3/§6.4 把 `evidence/harness/coverage.json` 钉为 `244575 B / F0D37A6C…`（该件现已不存在，见 VF-8）。

**改后（本批口径）**

- 验证层判据**一字未改**：`harness/coverage_drift.py` 的 `:161-166 LOCKED`、`:167 UNCOVERED_WRITABLE_MAX = 0`、`:109 ANCHOR_READING = (244575, 'F0D37A6C…B42D')`、`harness/ci_gates.py`、`harness/evidence_hash.py` 全部保持原样。
- 本批**唯一**动过的验证层判据在 t2（RF-1 真库重基线）：`harness/_env.py:94 REAL_DB_SHA256_EXPECTED`、`t6_ledger_check.py:40 PINNED_DB_SHA`、`improve_plan.py:42` / `analysis_ledger.py:43` / `final_recount.py:43` / `reconcile_r2.py:96` 的同值副本、`run_gates.py:57` 的 `bootstrap_copied_rows`、`negative_matrix.py` 的 NV-1.1 描述串与 NV-1.5 复标 —— 已按 **A-70 三步**登记在 `test-reports-2026-10/RF1-真库锚点重基线登记.md`（本件只作交叉引用，不重复登记）。
- `B13-05` 打法的敏感度自证保留：把下界下调 1 的合成产物仍须被 `coverage_drift` 判红（`ci_gates.py` 第 11 步的 `inject` 行即此打法）。

**证据**

| # | 工具 + 命令 | 原始读数 |
| --- | --- | --- |
| ① | `git diff --ignore-cr-at-eol --numstat -- test-reports-2026-10/harness/coverage_drift.py` | **空输出**（`0` 行）⇒ 本批未改该文件 |
| ② | 阳性对照：`/opt/wage-venv/bin/python -B test-reports-2026-10/harness/coverage_drift.py --coverage <本轮 246076 B 产物>` | `D-1 OK 273` / `D-2 OK 157` / `D-3 OK 155` / `D-4 OK 110（>=108）` / `D-5 OK 118（>=116）` / `D-6 OK 0（<=0）` / `D-7 OK 148 / 9` / `D-8 SKIP` ⇒ **判据 8/8 通过 ⇒ exit 0** |
| ③ | 阴性对照：`measure_coverage.py --no-request-probes --probes-exclude r2_c05_write_probe --out …/cov_fallback_t3.json` 后跑 `coverage_drift.py --coverage <该件>` | `[coverage] 阴性对照：剔除探针 ['r2_c05_write_probe'] ⇒ PROBES 9 -> 8`；`D-4 FAIL 实际=8` / `D-5 FAIL 实际=16` / `D-6 FAIL 实际=101` ⇒ **判据 5/8 ⇒ exit 1** ⇒ 判据**敏感、非恒真** |
| ④ | `sed -n '109p;161,171p' test-reports-2026-10/harness/coverage_drift.py` | `ANCHOR_READING = (244575, 'F0D37A6C72C9029C60B4124DAC5993E1E65321448C943555381C15ECD6BDB42D')`；`LOCKED` 六项与 §2 表② 逐字一致 |

**回退**：代码面无可回退（未改）；文档面 = 删除 `90- §13` 的 VF-5 段。

---

## §5 VF-6：`run_gates` 裸 exit 1 是环境依赖探针所致，**不得**作红/绿信号

**改前（易误读面）**：`run_gates.py` 裸跑 `exit 1`（`probe_unexpected=1`）易被读成「门禁红」；`90- §5.3` 已声明其为沙箱假红。

**改后（唯一健康口径）**

- 健康判定**只看** `ci_gates.py --phase first` 的汇总：`blocking 失败 == []`（`gates.json.summary` 层）。`run_gates.py` 的裸 exit code **不得**作为判据。
- `probe_unexpected=1` 与 `route_inventory_native_probe.verdict="unexpected"` **并列留档**（两个读数必须同轮同源）。
- A-62 明令：`route_inventory_native_probe` 属**环境依赖探针，不得重基线化**（`ci_gates.py:19`）。

**证据（本轮 `ci_gates --phase first`，证据目录 `test-reports-2026-10/evidence/harness/ci-run-20261009-035515/`）**

| # | 读数 | 值 |
| --- | --- | --- |
| ① | `ci_gates` 汇总行（逐字） | `steps=16`、`blocking 失败 = 无`、`report-only 失败 = ['evidence_hash']`、`exit = 2`（语义逐字「2 = 仅 report-only 失败」）；`注入未生效 = 无`；`仓库根两 JSON 未被触碰 = True（A-11）` |
| ② | `gates.json.summary` | `{"total": 6, "pass": 5, "fail": 0, "probe_only": 1, "probe_unexpected": 1, "exit_code_informative": 4, "in_gate_chain": ["check_templates","check_migration_heads","check_properties","check_db_bootstrap"], "report_only": ["route_inventory"], "evidence_only": ["route_inventory_native_probe"], "sensitivity_ok": null}` |
| ③ | `route_inventory_native_probe` | `{"exit_code": 0, "expected_exit_code": 1, "verdict": "unexpected"}` ⇒ **与 ② 的 `probe_unexpected=1` 并列留档** |
| ④ | `gates.json.real_db` | `before == after == {"sha256": "B4FB980C5D1B25B3C3A0EADC12ECF01C75B36EBD213B109E5DD190C617EEAABE", "bytes": 2531328, "mtime_ns": 1791517179418764055}`；`unchanged: true` |

**报告型红点说明（与 VF-6 同族的既有报告型红，非本批引入）**：`report-only 失败 = ['evidence_hash']`，三条 needle 逐字 `whitelist whitelist has no stale exact entry` / `whitelist wildcard rule(s) match >=1 violation` / `pinned real_db_matches_pinned == true`。根因：`evidence_hash.py` 在 `verdict=no_baseline`（根索引 `artifact_hashes.json` 不存在）时**早退**，其 `evidence_hash.gate.json` 不含 `real_db_sha256` / `real_db_matches_pinned` 两键 ⇒ `ci_gates.py:296 pinned = bool(rep.get('real_db_matches_pinned'))` 恒 `False`。**RF-1 之前**的 `ci-run-20261008-220300` / `ci-run-20261008-220943` / `ci-dsh-envcheck-033706` 三次运行里该 needle 已逐字为 `status: failed` ⇒ **既有报告型红、与 RF-1/RF-2 均无关**；t2 已把该子项从 acceptance ⑥ 移除（队长裁定），本件只作登记。

**回退**：无代码改动（口径订正）；文档面 = 删除 `90- §13` 的 VF-6 段。

---

## §6 VF-7：契约措辞陈旧（`mes_service.py:94` 兜底链 → 实际 `:89-93` 链字典 + `:96-111` 通用循环）

**改前**（陈旧契约串）

- `B14-T7-汇总评审报告.md:143`（源）：「`app/services/mes_service.py:**94**` 兜底链加 `pick_template('goods_receipt')`」。
- `90-:315`：「契约行号漂移（如契约称 `app/services/mes_service.py:94`，实现是 **`:90`** 链字典 + 通用循环）」—— `:90` 亦不准确。

**改后**（取代读法）

- 实现 = **`:89-93` 链字典 `_TEMPLATE_TYPE_CHAIN`** + **`:96-111` `pick_template` 通用循环**（`pick_template` 定义行 `:96`）。
- 行为结果与 B14-07 方案 A 一致；**字面量 `pick_template('goods_receipt')` 全树 0 命中**（该调用从未以字面量形式存在）。
- 行号随 RF-2 守卫落地位移：`def create_inspection_task` 由 `:114` → **`:128`**；`_TEMPLATE_TYPE_CHAIN` 仍在 `:89`。

**证据**

| # | 工具 + 命令 | 原始读数 |
| --- | --- | --- |
| ① | `grep -rn "pick_template('goods_receipt')" app/ scripts/` | **0 命中** |
| ② | `grep -n "_TEMPLATE_TYPE_CHAIN" app/services/mes_service.py` | `:89`（定义，字典体 `:89-93`）/ `:112`（RF-2 docstring 引用）/ `:115`（过滤循环） |
| ③ | `grep -n "^def pick_template\|^def create_inspection_task" app/services/mes_service.py` | `:96` / `:128` |
| ④ | `git show HEAD:app/services/mes_service.py \| grep -n "^def pick_template\|^def create_inspection_task\|_TEMPLATE_TYPE_CHAIN"` | HEAD 侧 `:96` / `:114`；链字典 `:89` ⇒ 位移仅由 RF-2 docstring 增行造成，链内容逐字未变 |

**回退**：本项为文本订正（`81- 附录 E` / 本件），代码面回退见 §3 与 RF-2（把 `pick_template` 还原为 `if template is not None: return template` 即回到旧行为，但**会重新引入「错型模板 + 下游 400 死锁」**，不得作为常态回退）。

---

## §7 VF-8：`coverage.json` 冻结锚点期望句过期 → 改为**判据型**期望

**改前**（陈旧期望句落点，逐行保留）

| 文件:行 | 逐字原值 |
| --- | --- |
| `90-:256`（§6.4 交接期事件登记订正表） | 「期望值**不变**：重建后必须 = **244575 B / `F0D37A6C72C9029C60B4124DAC5993E1E65321448C943555381C15ECD6BDB42D`**；复现不出即为口径漂移，按 A-70 处置」 |
| `90-:370`（§11.4 第 4 步） | 「重建的 `evidence/harness/coverage.json` 必须 = 244575 B / `F0D37A6C…B42D`」 |
| `90-:65`（§1-⑤）/`:212`（§6.1-②）/`:237`（§6.3）/`:282`（§7.2 B13-00） | 同值期望句 / 锚点表行 |
| `harness/coverage_drift.py:109` | `ANCHOR_READING = (244575, 'F0D37A6C…B42D')`（**保留为历史留档**，不接判据） |

**改后**（取代读法，=`C-VF-8.a`）

> 重建后必须 **`coverage_drift` 判据 8/8 通过（exit 0）**；**字节数 / SHA256 以当轮产物为准并留档**（不写绝对值、不作判据）。

**差异归因**（三类字段，逐字）

1. **路由集变化（实质）**：`summary.rules_total` **273 vs 271**（+2 = `/process_prices/import_alloy`、`/products/import_bom_alloy`，见 §2）；连带 `routes` 数组 273 条、`method_matrix` 317 条。
2. **运行期字段（逐字节不可复现的直接原因）**：`run_id='run-20261009-035515'`（对照 `run-20261008-220943`）；`interpreter='/opt/wage-venv/bin/python'`（历史档为 `F:\Miniconda\envs\wage\python.exe`）；`isolation.db_copy='…/mkdtemp/wms_test_run-20261009-035515_v79ap5fn/app.db'`（内嵌 mkdtemp 随机后缀 `v79ap5fn`，对照 `grq2acuk`）。
3. **计数漂移（在 LOCKED 内）**：`writable_literal_covered_by_all` 110（下界 108）、`writable_any_covered_by_all` 118（下界 116）、`method_level_non_get_total` 157。

**「逐字节复现结构性不可能」的实证**：两轮产物**同尺寸 246076 B，SHA 不同** —— `ci-run-20261008-220943/coverage.json` = 246076 B / `d2f3e24dee50c5422044d9a9db902d673fea00323b19cfba79df312da1f7fbfa`；`ci-run-20261009-035515/coverage.json` = 246076 B / `c8a73c47eb8dc5491416001dcf84f0befa7a1deeb6afbf323266b5730653b3da`。⇒ 以固定字节数/SHA 为期望在结构上不可满足。

**证据**

| # | 工具 + 命令 | 原始读数 |
| --- | --- | --- |
| ① | `coverage_drift.py --coverage <本轮 246076 B 产物>` | **8/8 ⇒ exit 0**（`D-1 OK 273` … `D-6 OK 0`，`D-8 SKIP`） |
| ② | 阴性对照（同上 §4 表③） | 回落 `8/16/101` ⇒ **5/8 ⇒ exit 1**（`D-4`/`D-5`/`D-6` 报红） |
| ③ | 本轮产物 `summary` | `rules_total 273` / `method_level_non_get_total 157` / `writable_rules_non_get 155` / `writable_literal_covered_by_all 110` / `writable_any_covered_by_all 118` |
| ④ | `sed -n '104p' harness/coverage_drift.py` | 「冻结锚点（`29` §4 声明锚点之一；**只作历史留档**，不参与判据 —— 见 docstring 的 N-1 节）」⇒ `ANCHOR_READING` 不参与判据的代码证据 |

**明写禁令（`C-VF-8.a` 末句）**：**不得**为对齐 `244575 B` 去改 `coverage_drift.py` 的判据（`LOCKED` / `ANCHOR_READING` / `:315-323`）；若有人把 `ANCHOR_READING` 接进判据，现行 8/8 产物必然转红。产物档变更（`evidence/harness/coverage.json` 重生）须走 **A-70 三步**（`90- §6.2`）。

**回退**：文档面 = 删除 `90- §13` 的 VF-8 段（原期望句未删，仍在 `:256`/`:370` 原位）。

---

## §8 VF-9：`w2w3_probe` / `w1_p01_regress` 内嵌陈旧期望（**本批只登记不修**）

**现场实测（陈旧期望逐条）**

| 文件:行 | 逐字陈旧期望 | 现行值 |
| --- | --- | --- |
| `test-reports-2026-10/harness/w2w3_probe.py:1134` | `'已扫描 23 个文件，模型类 74 个'` | **26 个文件** / 74 模型类 |
| `test-reports-2026-10/harness/w2w3_probe.py:1138` | `['total rules=271', 'duplicate (method,path) registrations=0']` | **273** / 0 |
| `test-reports-2026-10/harness/w2w3_probe.py:1140` | `['6712', 'RESULT' if False else 'OK:']` | **6721**（RF-1 播种 +9 行后） |
| `test-reports-2026-10/harness/w1_p01_regress.py:13` | 注释 R6 写 `total rules=271` | 273 |
| `test-reports-2026-10/harness/w1_p01_regress.py:58` | `expects` 串同上 | 273 |

**处置（本批有意不改，理由）**

1. 两文件**均未接入门禁链**：`grep -rn "w2w3_probe\|w1_p01_regress" test-reports-2026-10/harness/ci_gates.py test-reports-2026-10/harness/run_gates.py` ⇒ **0 命中**（`ci_gates.py:47` 仅 docstring 提及 `w2w3_probe`）；`25-W2W3修复说明.md:299` 逐字「不参与 CI 链条」。
2. **`harness/**` 是 t3 的 outOfScope**（契约逐字），故只登记不修。
3. 将来若修**必须走 A-70 三步**（逐字 diff + 阴性对照证明旧值为红 + append-only 登记），且须与 `w2w3_probe` 的「≥43 + 逐条归因」口径（`B15-00-契约冻结.md:432`）一致：`43 passed / 3 failed / 46 total`，3 条红点 = **2 条内嵌陈旧期望（本条）+ 1 条 CRLF 假红（`RC-15`）**。

**证据**：上表行号由 `grep -n` 现场取得；门禁链无命中的 grep 见上「处置 1」；`B15-00-契约冻结.md:429`（23→26 文件）/`:430`（271→273）已作为 `81-` 订正项登记。

**回退**：无代码改动；文档面 = 删除本件 §8 与 `90- §13` 的 VF-9 段。

---

## §9 RF-5：报工 `update_status` 第 4/5 内层块的原子性缺口（**只登记不修**）

**触发**：t6 实测发现；队长在本任务追加为第 6 条 acceptance。**族别**：与 B15-05 同族（内层块失败被静默吞掉），但缺口成因是**被调方自带事务边界** ⇒ 调用方**无法**用 savepoint 隔离。

**现场重定位（任务书给的行号与现行文件不符，本件按现场代码重定位并逐条留证）**

| 项 | 任务书引用 | 现场实测（2026-10-09） |
| --- | --- | --- |
| 路由 | 「报工 `update_status`」 | `app/main/routes.py:3575` `@bp.route('/tasks/<int:id>/update_status', methods=['POST'])` + `:3578 def update_task_status(id):`（**函数名是 `update_task_status`**；`grep -rn "def update_status" app/` ⇒ **0 命中**） |
| 第 4 个内层块 | （未给行号） | `routes.py:3882 try:` / `:3884 from app.services.notification_service import notify_raw_substitution` / `:3908 notify_raw_substitution(...)` / `:3914 except Exception as _ne:` / `:3915 current_app.logger.error(...)`（**不 raise**） |
| 第 5 个内层块 | （未给行号） | `routes.py:3919 try:` / `:3964 update_production_status_hierarchy()` / `:3966 except Exception as e:` / `:3967 logger.error('同步更新生产批次状态失败…')` / `:3969 # 不影响主流程，继续执行`（**不 raise**） |
| 序号的来源 | 「第 4/5 个内层块」 | = `B15-05` 清单七处吞异常内层块的第 4、5 项。冻结时（`git show HEAD:app/main/routes.py`）该七处位于 `:3707`（质检员/自动建质检任务）/ `:3810`（报工扣料回写 MaterialAllocation，含 `with db.session.begin_nested()`）/ `:3832`（替用分析）/ **`:3872`（原材料替用通知）** / **`:3909`（同步更新批次状态）** / `:3964`（同步生产中心实例可视状态）/ `:3989`（报工末道入库）⇒ 第 4 = 通知块、第 5 = 批次同步块，**与现场一致** |
| 被调方 ① | `app/services/notification_service.py:166-169` | 逐字 `        except Exception as e:` / `            db.session.rollback()` / `            current_app.logger.error(f'创建通知失败: {str(e)}')` / `            raise e` —— 属 `NotificationService.create_notification`（`notification_service.py:53`）的错误路径；`notify_raw_substitution`（`:671`）docstring `:684` 自称「事务边界：本 helper 不自提交，提交责任在调用方的事务边界内（B13-05）」，**但错误路径的 `db.session.rollback()` 是会话级回滚**，会连同调用方在同一事务内的全部未提交写入一起丢弃 |
| 被调方 ② | `app/main/routes.py:9642-9722 的 :9711/:9715` | 现场落在 `def update_production_status_hierarchy():`（**普通函数非路由**，def `:9657`、`try:` `:9659`）的「第二步：更新所有订单状态和完成数量」（`:9691`，遍历 `ProductionOrder.query.all()` `:9692`），`:9711 if len(completed_batches) == total_batches:` / `:9715 elif len(in_progress_batches) > 0:` 为**订单状态判定**；该函数自带 `db.session.commit()` `:9726`（成功路径）与 `db.session.rollback()` `:9730` + `raise e` `:9732`（错误路径）⇒ 任务书引用的**目标函数正确**，但终态行号须按上式更正（`:9722` 之后仍有 `commit` `:9726` / `rollback` `:9730`） |

**缺口机制（两条，均为「事务边界穿透 + 静默吞掉 + 响应仍 `success=true`」）**

1. **第 4 块（原材料替用通知）**：调用方（`update_task_status`）与 `create_notification` 共用同一 scoped session；被调方错误路径执行 `db.session.rollback()`（`notification_service.py:167`）⇒ **调用方本事务内的全部待提交写入（任务状态、`AuditLog`、扣料回写等）被一并丢弃**；随后 `raise e` 被调用方 `:3914` 捕获、仅记 error 日志**不 raise**；函数继续走到 `:4060 db.session.commit()` 并返回 `:4061 jsonify({'success': True, 'message': '更新成功'})` ⇒ **报工被静默丢弃但响应对前端报成功**。
2. **第 5 块（批次/订单状态层次同步）**：被调方在**成功**路径 `:9726` 自行 `commit()` ⇒ 把调用方尚未完成的业务单元**提前提交**（原子性边界被外力切断：此后 `:3974`/`:3999` 等后续步骤若失败，外层 `:4062 except` → `:4064 rollback()` **无法回滚已提交部分** ⇒ **部分应用**）；在**失败**路径 `:9730 rollback()` + `:9732 raise e` ⇒ 同 ①，调用方 `:3966` 吞掉异常后继续提交一个空事务并返回 `success: true` ⇒ **静默全丢**。
3. **savepoint 不可隔离**：`Session.rollback()` 回滚的是**最外层事务**（含所有 savepoint）；`Session.commit()` 提交的也是整个事务 ⇒ 即便调用方用 `db.session.begin_nested()` 包住（`routes.py` 现行仅在 `:3707`/`:3813`/`:4018` 三处使用 savepoint，**第 4/5 块均未用**），被调方的会话级 `rollback`/`commit` 仍会穿透。⇒ 真修须**改动 services 的提交契约**（`notification_service` + `update_production_status_hierarchy`），**属批次15 outOfScope**。

**处置**：**本批有意不修**，列为下游挂账（建议：**批次16 或与 `RF-5` 同族的「事务边界收口」专项一并处理**；处理前须先补一条「报工遇通知失败/批次同步失败 ⇒ 响应必须 `success=false` 且无部分应用」的故障注入判据，与 B15 的故障注入验收同族）。本条**不改变** B15-05 已落地的七处口径（B15-05 处理的是「吞异常」，本条处理的是「被调方自带事务边界」）。

**证据**：上表全部行号与逐字文本由 `sed -n` / `awk` / `git show HEAD:` 现场取得；`grep -rn "def update_status" app/` ⇒ 0 命中；`grep -n "update_production_status_hierarchy\|notification_service" app/main/routes.py`（限 `3575-4066`）⇒ `:3884` / `:3908` / `:3964` 三处。

**回退**：无代码改动（只登记）；文档面 = 删除本件 §9 与 `90- §13` 的 RF-5 段。

---

## §10 收尾核对

### §10.1 本任务改动面（tracked 文件）

| 文件 | 改动 | numstat（`--ignore-cr-at-eol`） |
| --- | --- | --- |
| `app/services/mes_service.py` | RF-2 类型守卫 + docstring（`:96-127`） | `16	2` |
| `app/models.py` | `:953` 注释（VF-3） | `1	1` |
| `test-reports-2026-10/81-后续开发与测试规划.md` | **追加** 附录 E | 只增 |
| `test-reports-2026-10/90-新DSH交接-批次12-14收口与恢复点.md` | **追加** §13 | 只增 |
| `test-reports-2026-10/VF-订正登记.md` | 新建（本件） | 新文件 |

### §10.2 明确未改动项

`test-reports-2026-10/harness/**`（含 `coverage_drift.py` / `ci_gates.py` / `evidence_hash.py` / `w2w3_probe.py` / `w1_p01_regress.py` / `run_gates.py`）、`scripts/**`、`app/main/**`、`app/db/**`、`alembic/**`、`app.db` —— **零改动**（逐条对应 outOfScope 与红线条目）。

### §10.3 真实库只读复核（红线）

`app.db` = **2531328 B / `B4FB980C5D1B25B3C3A0EADC12ECF01C75B36EBD213B109E5DD190C617EEAABE` / mtime 2026-10-09 03:39:39.418764055 +0000** ⇒ 与 RF-1 播种后钉值逐位相同，**本任务未写入真库**（RF-2 探针使用 `make_app(fresh=True)` 的 `/tmp/wms_test_f1rtfhce/app.db` 隔离副本）。

### §10.4 红线核对

| 红线 | 读数 |
| --- | --- |
| 禁 `flask db migrate` | 未执行 |
| 除 I1 外永不写真实 `app.db` | 本任务零写入（§10.3） |
| `qc_gate_allows_output(...)` 调用逐字不动 | `grep -n qc_gate_allows_output app/services/mes_service.py` ⇒ `:193`(def) / `:416`(docstring) / **`:459`(唯一调用，逐字 `    allowed, reason = qc_gate_allows_output(batch_item=item, workpieces=workpieces)`)**；HEAD 侧为 `:179` / `:402` / **`:445`**（同文本，纯行号位移）；`git diff -U0 -- app/services/mes_service.py \| grep -c qc_gate_allows_output` ⇒ **0** |
| tracked 文件只增不删 | `git status --porcelain` 内本任务涉及文件无 `D` 项；`81-`/`90-` 为纯追加 |
| `smoke_test` 不作验收 | 未引用 |

### §10.5 门禁读数（本任务两次 verify）

| 命令 | 退出码 | 读数 |
| --- | --- | --- |
| `/opt/wage-venv/bin/python -B scripts/functional_test.py` | **0** | 尾行逐字 `================ 结果：127 通过 / 0 失败 ================` |
| `/opt/wage-venv/bin/python -B test-reports-2026-10/harness/ci_gates.py --phase first` | **2**（= 仅 report-only 失败） | `steps=16`、`blocking 失败 = 无`、`report-only 失败 = ['evidence_hash']`；`gates.json.summary.fail == 0`；`real_db.unchanged == true` |

---

## §11 回退方法（逐条）

| 项 | 回退动作 | 影响 |
| --- | --- | --- |
| VF-2 / VF-7 / VF-8 | 删除 `81- 附录 E`、`90- §13` 的对应追加段（原行未删、仍在原位） | 文档回到「陈旧但可追溯」状态 |
| VF-3 | `app/models.py:953` 注释还原为 `comment='检验对象类型(product/production_record/material)'` | 纯注释，无行为影响 |
| RF-2（伴随 VF-7） | `pick_template` 循环还原 `if template is None: continue` / `if template.type != target_type: continue` 两行为原 `if template is not None: return template` | **会重新引入错型绑定 + `quality.py:863-865` 的 400 死锁**，仅作最后手段 |
| VF-5 / VF-6 / VF-9 / RF-5 | 无代码可回退（未改）；只需删除本件与 `90- §13` 的对应段 | 无 |

---

## §12 收尾复跑（本件与 `81- 附录 E` / `90- §13` 追加完成后，2026-10-09 · append-only 补录）

| 命令 | 退出码 | 原始读数 |
| --- | --- | --- |
| `/opt/wage-venv/bin/python -B scripts/functional_test.py` | **0** | 尾行逐字 `================ 结果：127 通过 / 0 失败 ================`（stdout `test-reports-2026-10/.tmp/run-b15/ft_final.out`，stderr 0 B） |
| `/opt/wage-venv/bin/python -B test-reports-2026-10/harness/ci_gates.py --phase first` | **2**（语义逐字「2 = 仅 report-only 失败」） | `steps=16`、`blocking 失败 = 无`、`report-only 失败 = ['evidence_hash']`、`注入未生效 = 无`、`仓库根两 JSON 未被触碰 = True（A-11）`；证据目录 `test-reports-2026-10/evidence/harness/ci-run-20261009-040046/` |

该轮 `gates.json` 终值（与 §5/§10.5 结论一致，仅 run 号不同）：

- `summary = {"total": 6, "pass": 5, "fail": 0, "probe_only": 1, "probe_unexpected": 1, "exit_code_informative": 4, "in_gate_chain": ["check_templates","check_migration_heads","check_properties","check_db_bootstrap"], "report_only": ["route_inventory"], "evidence_only": ["route_inventory_native_probe"], "sensitivity_ok": null}` ⇒ **`summary.fail == 0`**。
- `real_db = {"before": {"path":"app.db","sha256":"B4FB980C5D1B25B3C3A0EADC12ECF01C75B36EBD213B109E5DD190C617EEAABE","bytes":2531328,"mtime_ns":1791517179418764055}, "after": <同值>, "unchanged": true}`。
- 逐步骤组别：`run_gates`(blocking, exit=1, checks 4/4 **OK**) / `functional_test`(blocking, 2/2) / `permission_matrix`(blocking, 3/3) / `coverage_drift`(blocking, exit=0, 2/2) / `check_notification_triggers`(5/5) / `check_model_refs`(5/5) / `check_http_contract`(4/4) / `chain_count_consistency`(8/8) 全 OK；`evidence_hash`(report-only) `1/4` FAIL（三条 needle 见 §5）。

**红线终态复核**：`app.db` = **2531328 B** / **`b4fb980c5d1b25b3c3a0eadc12ecf01c75b36ebd213b109e5dd190c617eeaabe`**（只读 `sha256sum`）⇒ 与 RF-1 播种后钉值逐位相同，本任务**零写入真库**。

**append-only 自证**：`git diff --ignore-cr-at-eol --numstat -- test-reports-2026-10/81-后续开发与测试规划.md test-reports-2026-10/90-新DSH交接-批次12-14收口与恢复点.md` ⇒ `63	0` 与 `60	0`（**纯追加、0 删除**）；`app/models.py` = `1	1`（仅 VF-3 注释行）；`app/services/mes_service.py` = `16	2`（RF-2 守卫 + docstring）。

---

## §13 attempt 2 复核补录（append-only，2026-10-09 · t3 / attempt_id=`2202a521-2d1a-48f8-8da3-b72879177bb9`）

> **说明**：本件页首 `:5` 记录的是 **attempt 1**（`6220d696-…`）；本节为 **attempt 2** 的独立复核补录，**不改**前文任何行。§2–§12 的实现结论经本轮复跑依然成立。

### §13.1 RF-2 类型守卫的阴/阳双向实测（本轮一手，临时库副本）

探针：`test-reports-2026-10/.tmp/run-b15/rf2_pick_template_probe.py`（sha256 `23bcc9f6034878579574bea449be0ef11affec7b9cba62ca79b27621b1791259`）；
原始读数：`test-reports-2026-10/.tmp/run-b15/rf2_pick_template_probe.out`（单行 `B15RF2 {…}`）。
做法：`make_app(fresh=True)` 隔离副本（`/tmp/wms_test_eqyu_ynv/app.db`，**未碰真实库**），同一进程内**同时加载** HEAD 版 `app/services/mes_service.py`（`git show HEAD:` 落盘后 import，模块 1986 行）与工作树版，逐一对比同名函数返回。

| 场景 | 目标类型 | 工作树（修复后） | HEAD（修复前） | 判定 |
| --- | --- | --- | --- | --- |
| **N1（阴性对照）** | `goods_receipt` | `id=2 / SYS-QC-GOODS-REC / type=goods_receipt / 来料检（系统默认）` | **逐字相同** | `identical=true` ⇒ 类型匹配路径行为未变 |
| **N2（阴性对照）** | `production_record` | `id=1 / SYS-QC-PROD-REC / type=production_record / 生产质检（系统默认）` | **逐字相同** | `identical=true` |
| **P1（阳性对照）** | `goods_receipt`（链首同型模板 `id=2` 被置 `is_active=False`） | `None` | `id=1 / SYS-QC-PROD-REC / type=production_record`（**错型**） | `fixed_binds_mismatched=false` vs `head_binds_mismatched=true` ⇒ 守卫拦下错型绑定 |
| **P2（阳性对照）** | `workpiece`（库内无同型模板） | `None` | `id=1 / type=production_record`（**错型**） | 同上 |

⇒ 修复后 `pick_template` **只可能**返回 `type == target_type` 的模板或 `None`；核心阴性读数（验收②逐字要求）＝ `goods_receipt` 仍命中 `来料检（系统默认）`（`id=2`，与修复前逐字一致）。
下游死锁点现场复核：`app/main/quality.py:861-863`（`# 检查模板类型是否匹配` / `if template.type != task.target_type:` / `return jsonify({…'质检模板类型与任务类型不匹配'}), 400`）⇒ P1/P2 在修复前正是该 400 的成因。

### §13.2 红线 R-3（`qc_gate_allows_output(...)` 调用逐字未变）

```text
$ git diff -U0 --ignore-cr-at-eol -- app/services/mes_service.py | grep -c qc_gate_allows_output
0                        # diff 中零命中 ⇒ 该调用不在改动面内
$ grep -n "qc_gate_allows_output(batch_item=item, workpieces=workpieces)" app/services/mes_service.py
459:    allowed, reason = qc_gate_allows_output(batch_item=item, workpieces=workpieces)
$ git show HEAD:app/services/mes_service.py | grep -n "qc_gate_allows_output(batch_item=item, workpieces=workpieces)"
445:    allowed, reason = qc_gate_allows_output(batch_item=item, workpieces=workpieces)
```
两行**逐字相同**（`:445` → `:459` 纯行号位移，由 RF-2 docstring 增行造成）。

### §13.3 本轮 verify 读数（attempt 2 独立复跑）

| 命令 | 退出码 | 原始读数 |
| --- | --- | --- |
| `/opt/wage-venv/bin/python -B scripts/functional_test.py` | **0** | 尾行逐字 `================ 结果：127 通过 / 0 失败 ================`（stdout `test-reports-2026-10/.tmp/run-b15/ft_t3_attempt2.out`） |
| `/opt/wage-venv/bin/python -B test-reports-2026-10/harness/ci_gates.py --phase first` | **2**（语义逐字「2 = 仅 report-only 失败」） | `steps=16`、`blocking 失败 = 无`、`report-only 失败 = ['evidence_hash']`、`注入未生效 = 无`、`仓库根两 JSON 未被触碰 = True（A-11）`；证据目录 `test-reports-2026-10/evidence/harness/ci-run-20261009-040317/`（stdout `…/.tmp/run-b15/ci_gates_t3_attempt2.out`） |

逐步骤：`check_templates 5/5`、`check_migration_heads 4/4`、`check_properties 3/3`、`check_db_bootstrap 4/4`、`run_gates 4/4`（`exit=1` 属 A-62 环境探针，`summary.fail==0`）、`functional_test 2/2`、`permission_matrix 3/3`、`smoke_test 3/3`（report-only）、`route_inventory 3/3`（report-only）、`measure_coverage 1/1`（report-only）、`coverage_drift exit=0 2/2`、`check_notification_triggers 5/5`、`check_model_refs 5/5`、`check_http_contract 4/4`、`chain_count_consistency 8/8` 全 OK；`evidence_hash`（report-only）`1/4` FAIL 三条 needle 与 §5/§13.5 登记的**既有报告型红**逐字相同（`no_baseline` 早退所致，非本任务引入）。

### §13.4 append-only 与红线终态（本轮复核）

- `git status --porcelain | awk '$1 ~ /D/'` ⇒ **0 行** ⇒ tracked 文件无删除；`git diff --ignore-cr-at-eol --numstat`（本任务 inScope 五件）⇒ `app/models.py 1 1` / `app/services/mes_service.py 16 2` / `81- 63 0` / `90- 60 0` / `VF-订正登记.md`（新文件）⇒ 文档面**纯追加**（两文件 `grep -c "^-[^-]"` 均 **0**）。
- `sha256sum app.db` ⇒ `b4fb980c5d1b25b3c3a0eadc12ecf01c75b36ebd213b109e5dd190c617eeaabe` / **2531328 B** / mtime 2026-10-09 03:39:39.418764055 +0000 ⇒ 与 §10.3 钉值逐位相同，**本任务零写入真库**（探针副本路径 `/tmp/wms_test_eqyu_ynv/app.db`，`real_db_unchanged=true`）。
- `harness/**`、`scripts/**`、`app/main/**`、`alembic/**`：本任务**零改动**（本轮未触碰；`coverage_drift.py` 的 `LOCKED` / `ANCHOR_READING` 一字未动）。

### §13.5 回退（本节）

删除本节 §13 全文即可；§2–§12 的回退方法见 §11，代码面回退见 §11 的 RF-2 行（会重新引入错型绑定 + `quality.py:861-863` 400 死锁，仅作最后手段）。

## 14 批次15 I2（RF-2 + VF 订正）attempt 3 独立复核补录（append-only）

- 记录人：dev-core（团队成员）；任务 t3 / attempt 3；attempt_id `295d44c8-0d15-49e8-95a5-791808cb65e7`（attempt 1 = ops-baseline `6220d696-b767-49d1-9e5b-e5ac8f28f43a`，attempt 2 = analyst `2202a521-2d1a-48f8-8da3-b72879177bb9`，两者均以 `MALFORMED_RESPONSE` 崩溃且未提交结构化 payload ⇒ 本节只复核其留在工作树/本文档的成果，不改写 §0–§13）。
- 本节性质：**纯复核**。attempt 3 **未改动 inScope 五件的任何一行**（工作树内容与 §13 记录逐字节一致），只新增本节与归档本轮证据副本。

### §14.1 R-3 冻结红线（逐字证明）

| 命令 | 实测读数 |
| --- | --- |
| `git diff -U0 --ignore-cr-at-eol -- app/services/mes_service.py \| grep -c qc_gate_allows_output` | **0** |
| 工作树 `app/services/mes_service.py:459` | `    allowed, reason = qc_gate_allows_output(batch_item=item, workpieces=workpieces)` |
| HEAD `app/services/mes_service.py:445` | `    allowed, reason = qc_gate_allows_output(batch_item=item, workpieces=workpieces)` |
| `diff <(git show HEAD:... \| sed -n '445p') <(sed -n '459p' ...)` | 无输出 ⇒ `IDENTICAL(逐字)`（仅行号位移 445→459） |
| diff 全部 hunk 头 | 仅两条，均在 `pick_template`：`@@ -105,0 +106,8 @@ def pick_template(target_type):`、`@@ -109,2 +117,8 @@ def pick_template(target_type):` |

### §14.2 RF-2 类型守卫 阴/阳双向实测（独立探针，非复用 attempt 2 结论）

- 探针脚本 `test-reports-2026-10/.tmp/run-b15/t3_rf2_probe.py`，原始 stdout `…/t3_rf2_probe.out`（逐字 `T3RF2 {json}` 一行）。方法：副本库 `_test_bootstrap.make_app(fresh=True)`（副本路径 `/tmp/wms_test_58nm1gt0/app.db`，**非真库**）内同进程加载 `git show HEAD:app/services/mes_service.py`（`head_module_lines=1986`）为第二模块，函数级对拍工作树 vs HEAD。exit 0。
- 链字典同源：`chain_identical=true`（三键 `goods_receipt`/`workpiece`/`heat_lot` 两侧逐字相同，均为四元素链）。
- **阴性对照（类型匹配既有场景行为逐字不变）**：`N1 goods_receipt` 两侧同为 `id=2 / SYS-QC-GOODS-REC / 来料检（系统默认）`，`identical=true`；`N2 production_record` 两侧同为 `id=1 / SYS-QC-PROD-REC / 生产质检（系统默认）`，`identical=true`。
- **阳性对照（不得再绑定类型不匹配模板）**：`P1`（`goods_receipt` 模板 `is_active=False` ⇒ 链回落 `production_record`）HEAD 返回 `id=1 / type=production_record`（`head_binds_mismatched=true`），工作树返回 `null`（`worktree_binds_mismatched=false`）；`P2 workpiece`、`P3 heat_lot` 同型同读数（两侧 HEAD 均错型绑定、工作树均 `null`）。
- 不变量：6 个 `target_type`（`goods_receipt`/`workpiece`/`heat_lot`/`production_record`/`material`/`product`）工作树全部 `ok=true`（只返回同型模板或 `None`）。
- E2E 成因链：`create_inspection_task('workpiece', 1)` ⇒ 工作树 `template_id=null`，HEAD `template_id=1` 且 `head_bound_template_type='production_record'` ⇒ 即 `app/main/quality.py:863-865` 的 400 死锁成因（HEAD 行为，工作树已消除）。

### §14.3 VF-3 与改动面

- `app/models.py:953` 工作树逐字：`target_type = db.Column(db.String(20), nullable=False, comment='检验对象类型(product/production_record/material/goods_receipt；自动创建为 workpiece/heat_lot)', index=True)` ⇒ 方案 A（三类→四类含 `goods_receipt`）在位，纯注释。
- `git diff --ignore-cr-at-eol --numstat`（inScope 五件）：`app/models.py 1 1`、`app/services/mes_service.py 16 2`、`81-…md 63 0`、`90-…md 60 0`、`VF-订正登记.md`（新文件，395 行 / 41026 B 起，本节追加后行数增加）⇒ 文档面纯追加。

### §14.4 门禁读数（attempt 3 本轮实跑）

| 命令 | 退出码 | 读数 |
| --- | --- | --- |
| `/opt/wage-venv/bin/python -B scripts/functional_test.py` | **0** | 尾行逐字 `================ 结果：127 通过 / 0 失败 ================`（stdout 归档 `…/.tmp/run-b15/ft_t3_attempt3.out`） |
| `/opt/wage-venv/bin/python -B test-reports-2026-10/harness/ci_gates.py --phase first` | **2**（语义逐字「2 = 仅 report-only 失败」） | `steps=16`、`blocking 失败 = 无`、`report-only 失败 = ['evidence_hash']`、`注入未生效 = 无`、`仓库根两 JSON 未被触碰 = True（A-11）`、`gates.json summary.fail = 0`；证据目录 `test-reports-2026-10/evidence/harness/ci-run-20261009-040610/`（stdout 归档 `…/.tmp/run-b15/ci_gates_t3_attempt3.out`），逐步骤含 `chain_count_consistency 8/8`、`run_gates 4/4`（`exit=1` 属 A-62 环境探针）。 |

- `evidence_hash` 的 report-only 红为**既有报告型红、非本任务引入**：其判定 `NO_BASELINE（无防篡改基线，退出码 1）`、`[VIOLATION/no_baseline] 根索引 artifact_hashes.json 不存在`，在 t5 基线档 `test-reports-2026-10/evidence/harness/ci-run-20261009-035439/` 中同为 `"id": "evidence_hash" … "exit_code": 1, "status": "failed"`（三条 needle 与 §5/§13.5 登记逐字相同）；且 `harness/**` 属本任务 outOfScope，本轮零改动。

### §14.5 红线与真库终态（attempt 3 复读）

- 真库 `app.db`：`sha256 = b4fb980c5d1b25b3c3a0eadc12ecf01c75b36ebd213b109e5dd190c617eeaabe`、`2531328 B`、mtime `2026-10-09 03:39:39.418764055 +0000` ⇒ 与 §10.3/§13.4 钉值逐位相同，**零写入**（本轮所有 DB 读写只发生在 `/tmp/wms_test_58nm1gt0/` 副本）。
- `git status --porcelain | awk '$1 ~ /D/'` ⇒ **0 行**（tracked 文件只增不删）；
- `app/main/**`、`app/services/**` 除 inScope 的 `mes_service.py` 外、`harness/**`、`scripts/**`、`alembic/**`、`app.db`：本轮零改动；`coverage_drift.py` 的 `LOCKED`/`ANCHOR_READING` 一字未动（§7 VF-8 明写不得为对齐 244575 B 改判据）。

### §14.6 回退（本节）

删除本节 §14 全文即可（纯追加、无代码面耦合）；代码面与 §0–§13 的回退方法见 §11。

## 15 VF-10：`scripts/check_doc_claims.py` 内嵌陈旧期望（append-only 登记 · 只登记不修）

- 记录人：captain（队长）；来源：t7 非作者独立验证报告 §9 发现 3（`test-reports-2026-10/B15-验证报告.md`）。
- 现场（工具 + 口径 + 值）：`grep -n 'rules_total' scripts/check_doc_claims.py` ⇒ `:24` 与 `:74` 仍钉旧口径（`rules_total = 271` 一族）；直跑该脚本 ⇒ **`violations = 15`**。
- 判定：**只登记不修**。理由三条：① 该脚本**未接入任何门禁链**（`test-reports-2026-10/harness/ci_gates.py --phase first` 现行 16 步中含此步 = 无），故不产生假红、不影响健康结论；② 本批 inScope 未含 `scripts/**`；③ 与 **VF-2 / VF-9 同族**（同一批 `271 → 273` 路由漂移的余波：VF-2 = `coverage_drift.py` 契约行文，VF-9 = `w2w3_probe.py:1134/:1138`）。
- 未处置项（留档备查）：`scripts/check_doc_claims.py:24`、`scripts/check_doc_claims.py:74`。
- 将来若修：须走 **A-70 三步**（改前值留档 → 阴性对照必须先报红 → 改后值 + 登记件）；该脚本未进门禁链，故「阴性对照报红」需人工构造（直接跑脚本读 `violations`）。
- 回退：删除本节 §15 全文即可（纯追加、无代码面耦合）。

**（§15 结束：本件 §0–§14 未改动。）**
