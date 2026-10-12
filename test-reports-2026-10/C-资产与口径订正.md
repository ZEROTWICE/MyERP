# C-资产与口径订正（G-12 / G-16②=P12 / G-17 / G-20 / G-22=P11 + B18-06 三项）

- **任务**：`t2 [T-gov-assets]`（attempt_id `bbfb9c0f-4629-42a3-af89-c52169b92ced`）
- **执行者**：`gov-assets`（资产/口径同步工程师，非代码线）
- **时点**：2026-10-12 04:25–04:57 UTC（实测窗口）｜解释器 `/opt/wage-venv/bin/python`（3.11.2，唯一解释器）｜cwd `/root/code/MyERP`
- **本件性质**：**新增件**（append-only）。未覆盖、未改动任何既有文件；未改任何判据 / 钉值 / 期望值（⇒ **无需 A-70 三步**，理由见 §7）；未改业务代码 `app/**`；未 `push`（约束 ⑧）。
- **证据形态**：每条 = **工具 + 口径 + 值**。「未发现问题」不作为证据；未跑项一律登记为 `not_measured` / `blocked` 并给出**解除条件**（约束 ④⑥）。
- **真库 `app.db` 三值**（钉值 = `34E48E7A21163DB390EEBDA4F2030343F3609AFEDC65D8C6E909D6EB5A49177E` / 2531328 B / `2026-10-12 04:25:37.128430119 +0000`）：
  - 操作前（04:25:37 后首次核）：`34e48e7a21163db390eebda4f2030343f3609afedc65d8c6e909d6eb5a49177e`｜2531328｜`2026-10-12 04:25:37.128430119 +0000` ✅
  - 操作后（04:47，全部实测与门禁跑完后）：`34e48e7a21163db390eebda4f2030343f3609afedc65d8c6e909d6eb5a49177e`｜2531328｜`2026-10-12 04:25:37.128430119 +0000` ✅
  - 旁证（第三方工具自报）：`evidence_hash.gate.json` 的 `real_db_matches_pinned = true`；`b17_governance_contract.py` 收尾自印「真实 app.db 只读：sha256 前后一致 `34e48e7a…9177e`」。
- **本件所用工具均为静态扫描 / 只读**：`coverage_drift.py`、`check_doc_claims.py`、`b17_governance_contract.py`、`ci_gates.py`。不建立写连接。（`ci_gates` 的请求型步骤按既有垫片走 `scripts/_test_bootstrap.make_app()` 库副本。）

---

## 0. 总览

| # | 条目 | 任务书所述状态 | **现场实测结论** | 判据/钉值是否改动 |
| --- | --- | --- | --- | --- |
| G-12 | 覆盖分母抬升未同步（4 落点） | 待同步 | **4 落点现场全部已同步 / 载体不存在**（§1.1–1.4，含反向证据）；另发现 **3 处残留**（§1.5 归档锚点 = 第二套分母〔4 键〕；§1.6 B17 契约永久转红；**§1.7 `check_doc_claims.py` 裸跑假红 11 条 + 注入夹具空转**） | **未改** |
| G-16②/P12 | `reconcile_r2.py:555` 无参假绿 + ledgerbook 陈旧读数 | 待重指 | **两处均已重指为带参形态**（B17-11，`5d1dcb4` 入库）；四态实跑证实 `0/1/2` 语义成立 | **未改** |
| G-17 | `40-` §4.5 工作区版未提交 | 待提交 | **已提交**，`git status --porcelain` 全量**无 `M` 行** | **未改** |
| G-20 | 同一 CSRF 面两个分母 | 只留一个 | **24 条文案判据已废并改写**，只剩 `133/133` 状态码 + 哨兵口径 | **未改** |
| G-22/P11 | 仓库根 6 个 `.tmp_v15_*.{out,err}` | 处置或登记 | **已消除（6 → 0）**，从未入库（`git ls-files` 零命中） | **未改** |
| B18-06① | `delivery_batches` 对照视图口径说明 | 需给口径 | **口径已给**（§6.1）：计划面通路完整、执行面零命中 ⇒ 对照视图不存在；状态 `not_measured` | **未改** |
| B18-06② | 客户删除关联校验（G-E） | 按用户裁定改措辞 | **措辞已按实测现场给出**（§6.2）；**未实现 400**。⚠ **裁定前提「现状=允许裸删」被实测证伪**——现状 = 删除失败 + 静默 200 (`success:false`)，须复议 | **未改** |
| B18-06③ | `CodeGenerationLog` / `api_execute_operation` / `G-K` 三入口 | 需给口径或默认路径 | **三条口径已给**（§6.3）：日志表默认「只写不读」；工序端点不碰正品库；三入口边界 = 是否走报工链末道入库 | **未改** |
| **⚠ 新发现**<br>（任务书未列） | `scripts/check_doc_claims.py` **裸跑假红 11 条** + 注入夹具空转 + 文档三处口径并存 | — | **§1.7**（本件最重要的工具缺陷）：默认覆盖源已死 ⇒ 裸跑 `RESULT: FAIL（violations=11）`/`exit 1`，与真违规**同码**；`AGENTS.md:99` 恰把它列入「优先裸跑」清单 | **未改**（只登记；改须走 A-70） |

**门禁复核（约束 ⑨）**：`ci_gates.py --phase first` ⇒ **steps=20 / blocking 失败 = 无** ✅，`report-only 失败 = ['evidence_hash']`，**exit = 2**。⚠ **exit 0 当前不可达**，机制见 §7.2，登记见 §8。⚠ **链内 `check_doc_claims` 的 OK 只在带 `--coverage` 时成立**，不可外推到裸跑（§1.7 / §7.2）。

---

## 1. G-12 覆盖分母抬升未同步（N-13）

**口径**：覆盖度期望值的唯一权威源 = `scripts/check_doc_claims.py` 的 `PINNED`（`:98`）+ `COVERAGE_LOCKED`（`108/116/0`，rules=271），由 `ci_gates.py` 第 19/20 步（blocking）逐条执法。任何下游产物**不得自持字面分母**——自持即会随 A-70 重基线而漂移，形成「同一覆盖面两套分母」。

任务书列举的 4 个落点，逐处现场读数：

### 1.1 `harness/analysis_ledger.py`（claim）— **无陈旧常量，已达标**

- **工具**：`grep -n '101\|141' test-reports-2026-10/harness/analysis_ledger.py`
- **值**：**零命中**。（唯一含 `10156` 的是 `:95 'harness/_env.py': (10156, 242, '2ADBE8FEA5C4BF17')` —— 这是 `_env.py` 的**字节数**，与覆盖分母无关。）
- **claim 机制现场**：`CLAIMED_FINGERPRINTS = {`（`:94`，11 项，校验对象为 `harness/_env.py`/`fixtures.py`/`run_gates.py`/`measure_coverage.py`/`negative_matrix.py`/`uat_chains.py`/`uat_evidence.py`/`_diag_quality_status.py` 与 3 份 `md` 件 —— **不含 `coverage.json`**），校验器 `def verify_claimed_fingerprints(arts)`（`:109`），逐条比对 `claimed_bytes/actual_bytes/claimed_sha16/actual_sha16/claimed_lines/actual_lines`。
- **反向证据（证明不自持分母）**：覆盖段 `def coverage_verdict(am, cov)`（`:597`，止于下一个 `def main()` = `:659`）**整函数现场重算**：`method_level_non_get_recount=len(non_get)`、`literal_covered_recount=len(lit)`、`covered_any_recount=len(anyc)`、`non_get_without_any_hit=len(non_get)-len(anyc)`、`rules_non_get`、`uncovered_writable`、`smoke_plan`。**工具 / 值**：`sed -n '597,660p' … | grep -n '108\|116\|155\|156\|157\|158\|149\|273'` ⇒ **零命中**（exit 1）✅
- **判定**：**已同步**（该文件本就不自持覆盖分母）。`70-` §9.1 所称「`analysis_ledger` 的 claim 指纹」现场无对应陈旧常量。

### 1.2 `harness/improve_plan.py`（行号）— **载体不存在**

- **工具**：`grep -n '101\|141' test-reports-2026-10/harness/improve_plan.py`
- **值**：**零命中**，不存在该载体。
- **现场实读**：常量区 `:31-49`（`HARNESS_DIR` `:31` / `REPORTS_ROOT` `:32` / `REPO_ROOT` `:33` / `EVIDENCE_ROOT` `:36` / `EVID_DIR` `:37` / `REAL_DB` `:39` / `RUN_ID` `:49`）；`HASH_TARGETS = [`（`:52-58`，注释逐字「声明式指针：`evidence/improve/` 下要参与哈希基线的制品（`artifact_hashes.json` 自身除外）」，5 项）；`:753` 遍历 `('harness/gates.json','harness/negative_matrix.json','harness/coverage.json',…)`；派生块 `:779-790` 显式读 `evidence/harness/coverage.json.summary`（注释逐字：「**显式读 coverage.json.summary**，不用泛化 key 搜索，避免误取布尔标记」），`:790` 记 `source`。
- **无 CLI 参数**：`grep -n 'add_argument\|argparse' test-reports-2026-10/harness/improve_plan.py` ⇒ **零命中** ⇒ 该脚本**无法**用 `--coverage` 指向本 run 产物（故它只能读固定路径，缺文件时优雅降级）。
- **判定**：**该载体非现场项**。`improve_plan.py` 是**报告型**（stdout 全度量、无判据语义，退出码不进闸门链），对缺失文件由 `def load_evidence(name)`（`:562`）记 `exists: False`。

### 1.3 `harness/final_recount.py`（101/141）— **已改绑权威源（B18-08）**

- **工具**：`grep -n '101\|141'` + 直接读 `:383-400` / `:449-468`
- **值**：仅剩 **2 处说明性注释**（非钉值）：`:385`「B18-08：同上，期望值一律绑定权威源（改前 141/101/155/6/14 留档见 82- 登记件）」、`:452`「改前：本文件自持 `155/6/14/8/141/153/101/161` —— 那是 **V-06 之前**的读数」。
- **实现现场**：`def coverage_pins()`（`:449`）docstring 逐字「覆盖度期望值**从唯一权威源绑定**（B18-08 / G-12）…改后：一律从 `scripts/check_doc_claims.py:PINNED` 绑定…本文件不再有可漂移的字面量。改前值留档：`test-reports-2026-10/82-数字对账表机检登记.md`」；`:469-472` 以 `importlib.util` 加载 `scripts/check_doc_claims.py`；t7 派生循环（`:387-391`）逐键取 `_p["…"]` 作期望值（`non_get_without_any_hit` / `uncovered_writable` / `method_level_non_get_recount` / `literal_covered_recount` / `covered_any_recount`）。
- **判定**：**已同步**。改前值有留档件（`82-数字对账表机检登记.md`），符合 A-70 第①步的留档要求（该步由 B18-08 完成，非本件所为）。

### 1.4 文档 `6/14/101` — **均为历史留档或有意阴性对照，无现行判据**

- **口径**：`6/14/101` 是 **V-06/C-05 有意重基线之前**的锚点读数；现行 `LOCKED` = `108/116/0`。留档原文（`harness/coverage_drift.py` 缺参时打印，实测）逐字：「冻结锚点仅作**历史留档**、不参与判据：它记录的是 V-06/C-05 有意更新**之前**的 6/14/101，而 LOCKED 已按 A-70 更新为 108/116/0 ⇒ 直接套用必然假红（N-1）」。`40-第2轮实测Runbook与台账规范.md` 同类表述：「本轮之前的台账/报告若仍写 `6/14/101`，即为**陈旧口径**」。
- **判定**：**无现行判据依赖 `6/14/101`**；命中该串的既有文档分两类——(a) 历史读数留档（`60-`/`70-`/`90-` 等 appd-only 历史件，按约束 ③ 不追改）；(b) **有意阴性对照的期望值**（如 `35-` 记 C-05 的三步回退对照，其「转红」读数**就是**要打印 `6/14/101`，删掉反而破坏阴性对照）。⇒ **不改**。

### 1.5 ⚠ 残留 1（新发现）：归档锚点 = 同一覆盖面的**第二套分母**

- **工具 / 命令**：`/opt/wage-venv/bin/python -B test-reports-2026-10/harness/coverage_drift.py --coverage test-reports-2026-10/evidence/harness/ci-run-20261009-054416/coverage.json`
- **口径**：`coverage_drift.py` 对「本次 run 产物」判 9 条（D-1…D-9）；`D-2`/`D-3`/`D-7` 的期望值来自现行 `LOCKED`（`method_level_non_get_total >= 158`、`writable_rules_non_get == 156`、smoke 静态复现 `149`/未解析 `9`）。
- **值（实测，exit 1，判据 4/8）**：

  | 判据 | 期望（现行 LOCKED） | 该归档锚点实际 | 结果 |
  | --- | --- | --- | --- |
  | D-1 `rules_total == 273` | 273 | 273 | OK |
  | D-2 `method_level_non_get_total >= 158` | ≥158 | **157** | **FAIL** |
  | D-3 `writable_rules_non_get == 156` | 156 | **155** | **FAIL** |
  | D-4 `writable_literal_covered_by_all >= 108` | ≥108 | 110 | OK |
  | D-5 `writable_any_covered_by_all >= 116` | ≥116 | 118 | OK |
  | D-6 `len(uncovered_writable) <= 0` | ≤0 | 0 | OK |
  | D-7 smoke 静态复现 149 / 未解析 9 | 149 / 9 | **148 / 9** | **FAIL** |
  | D-8 route_inventory stdout | — | 未提供 `--routes-stdout` | SKIP |
  | D-9 多方法面 N==44 且 M==38 | 44 / 38 | **N=None M=None len(list)=37** | **FAIL** |

- **该归档锚点指纹**：`test-reports-2026-10/evidence/harness/ci-run-20261009-054416/coverage.json`，246076 B，`-r-xr-xr-x`，mtime `2026-10-09 05:45`，`sha256 = 58bf844628402ae6d87f6a0f0336049d313463e83c28dfa448bbefd9db21e055`。
- **判定**：**`asset_defect`，属 G-12 同族（覆盖分母抬升未同步）的在世实例**。B18-Q1 把 `method_level_non_get 157→158`、`writable 155→156`、`smoke 148→149` 抬升后，**该冻结归档未同步**，且它同时被 `scripts/check_doc_claims.py:73 COVERAGE_ANCHOR_READINGS` 作为「留档读数」引用（该常量现行值 = `157/155/148`，与 `PINNED` 的 `158/156/149` 并存）。
- ⚠ **本表只看到 3 键，完整落后面是 4 键**：`coverage_drift` 的 9 条判据**不含派生键** `non_get_uncovered_method_level`（= `method_level_non_get_total − writable_any_covered_by_all` = `158−118` vs `157−118`），该键由 `check_doc_claims.py` 的 `PINNED` 自持钉值 40 ⇒ **`--coverage <该归档>` 在 `check_doc_claims` 下报 4 条违规**（实测 25/29、violations=4、exit 1）。**两工具口径互补，缺一不可** —— 详见 **§1.7**。
- **未折算 pass**：`coverage_drift --coverage <该归档>` = **exit 1**，**不得**当作 `blocked`/`not_counted_as_passed` 之外的状态，也**不得**因「只是个归档」而记通过。
- **解除条件**（须由 owner 裁决，涉及 A-70 与跨批资产）：**三条须一并处置**（§1.7 补齐了第 2、3 条）——
  ① 该归档保持不动，但在 `check_doc_claims.py` 的 `COVERAGE_ANCHOR_READINGS` 处**显式标注它是 B18-Q1 之前的读数**（现状注释只声明来源与 sha，未声明「已落后于 PINNED **四**键（含派生键）」）；
  ② `check_doc_claims.py` 的**裸跑假红**须同时消灭（否则任何裸跑者都看到 11 条违规，见 §1.7）；
  ③ `ci_gates` 的 `_inj_check_doc_claims` 注入夹具基线须与 `PINNED` 一致（否则阴性对照空转，见 §1.7）；
  或 ④ 若要把归档当活输入，则须走 A-70 三步重基线（**本件不擅自改**）。

### 1.6 ⚠ 残留 2（新发现）：`b17_governance_contract.py` 的 B17-11 条目在 HEAD **永久转红**

- **工具 / 命令**：`/opt/wage-venv/bin/python -B test-reports-2026-10/harness/b17_governance_contract.py --only B17-11`
- **口径**：该条目判据 = `all(hits.values()) and '273' in probe.splitlines()[113] and '271' in hprobe`；其中 `hprobe = git show HEAD:test-reports-2026-10/harness/r2_c07_probe.py | grep -n "ROUTE_RULES_BASELINE = "`。其**设计语义**是「HEAD = 改前 271，现场 = 273」。
- **值（实测，PASS 0 / FAIL 1 / BLOCKED 0，exit 1）**：
  - `hits = {'reconcile_r2.py': True, 'r2_v14_ledgerbook.py': True}`（命中行数 5 / 2）✅
  - 现场 `ROUTE_RULES_BASELINE = 273`（`r2_c07_probe.py:114`）✅
  - **`git show HEAD:test-reports-2026-10/harness/r2_c07_probe.py | grep -n "ROUTE_RULES_BASELINE = "` ⇒ `114:ROUTE_RULES_BASELINE = 273        # \`scripts/route_inventory.py\` 口径：total rules=273`** ⇒ `'271' in hprobe` = **False** ❌
- **机制**：该契约是**提交前（pre-commit）一次性证据工具**——它断言「改前在 HEAD、改后在现场」。B17 的改动随 commit `5d1dcb4`（`feat(b17): 批次17 工程治理与门禁收口（B17-01…B17-19；B17-02 登记 blocked）`）入库后，HEAD 亦为 273，该断言**不可满足**，条目永久转红。同族写法遍布该文件（`git show HEAD:` 出现在 `:78`/`:109`/`:136`/`:214`/`:582`/`:595`/`:603`/`:608`/`:616` 等），故这是**整件口径**问题，不是 B17-11 修得不对。
- **不影响 ⑨ 的证据**：`grep -rn 'b17_governance_contract' test-reports-2026-10/harness/ci_gates.py test-reports-2026-10/harness/run_gates.py scripts/` ⇒ **零命中** ⇒ 该文件**未进门禁链**。
- **判定**：**`blocked`（口径未定，非回归）**。`--only B17-11` 的 FAIL **不得**读成「P12 未修」——P12 的修复本体已由 §2 的带参形态与 `B17-登记.md §B17-11` 双重覆盖。
- **解除条件**：由 owner 二选一——① 为该契约补「提交后态」口径（判据改为「现场 273 **且** 改前 271 已留档于 `B17-登记.md` §B17-11」，不再要求 HEAD 仍为 271）；② 在契约头部显式声明「本件只在 B17 提交前运行，提交后 `git show HEAD:` 面对照组整体失效，复跑须以登记件留档值为准」。**本件不擅自改判据**（约束 ⑤）。

### 1.7 ⚠ 残留 3（新发现，**本件最重要的工具缺陷**）：`check_doc_claims.py` 裸跑 = **假红 11 条**（`exit 1`）

- **工具 / 命令（三态对照，同一脚本）**：

  ```bash
  P=/opt/wage-venv/bin/python
  A=test-reports-2026-10/evidence/harness/ci-run-20261009-054416/coverage.json   # 归档锚点
  C=test-reports-2026-10/evidence/harness/ci-run-20261012-044515/coverage.json   # 本次 run 产物
  $P -B scripts/check_doc_claims.py                    # ① 裸跑
  $P -B scripts/check_doc_claims.py --coverage "$A"    # ② 归档锚点
  $P -B scripts/check_doc_claims.py --coverage "$C"    # ③ 本次 run 产物
  ```

- **值（实测三态）**：

  | 调用 | `钉常量 vs 权威源` | violations | RESULT | exit |
  | --- | --- | --- | --- | --- |
  | **① 裸跑**（默认路径） | **20/29** | **11** | `FAIL` | **1** |
  | ② `--coverage <归档锚点>` | 25/29 | **4** | `FAIL` | **1** |
  | ③ `--coverage <本次 run 产物>` | **29/29** | 0 | `OK` | **0** ✅ |

- **① 的 11 条构成（逐条实测，`grep VIOLATION`）**：
  - `#1` `权威源错误：权威源缺失：test-reports-2026-10/evidence/harness/coverage.json（coverage 判据输入；本 run 产物请 --coverage <path> 显式传入）`
  - `#2` `权威源错误：锚点留档读数（…ci-run-20261009-054416/coverage.json，sha256 58BF84462840…）：method_level_GET=161、…、writable_rules_non_get=155`
  - `#3–#11` **9 条** `口径源漂移：<键> 钉值 X ≠ 源值 None`（`method_level_GET` / `method_level_non_get_total` / `non_get_uncovered_method_level` / `smoke_targets` / `smoke_unresolved` / `uncovered_writable_rules` / `writable_any_covered_by_all` / `writable_literal_covered_by_all` / `writable_rules_non_get`）
- **机制**：`COVERAGE_JSON = os.path.join(REPORTS_ROOT, 'evidence', 'harness', 'coverage.json')`（`scripts/check_doc_claims.py:67`）—— 该文件**已不存在**（`ls` ⇒ `No such file or directory`）。源值取不到 ⇒ 9 条 coverage 键的「源值」为 `None` ⇒ 逐条报「钉值 X ≠ 源值 `None`」。
- ⚠ **危险度高于 P12 的原始形态**：同族的 `coverage_drift.py` 缺参 ⇒ **`exit 2` + `[USAGE]` 明示「用法错误，不是回归」**；`check_doc_claims.py` 缺参 ⇒ **`exit 1`**（与「真判据失败」**同码**）+ **`RESULT: FAIL（violations=11）`**。虽然 `#1` 里确有一句「请 `--coverage <path>` 显式传入」的提示，但**在退出码与 RESULT 这两个机读通道上，假红与真违规不可区分**。`70-` §10.8-1 的判据原文要求「该检查项恢复绿且**不再是「无参假绿」**」—— 该要求**在 `coverage_drift` 上已达成，在 `check_doc_claims` 上仍未达成**（此处为**无参假红**，与「假绿」互为镜像，同属 N-1 家族）。
- ⚠ **文档三处记载并存，裸跑那条会踩坑（同类原则的又一实例）**：
  - `AGENTS.md:99` 把 `check_doc_claims` 列入「**只做静态检查时优先跑**不发请求的脚本」清单，**未注明必须带 `--coverage`**；
  - `81-后续开发与测试规划.md:467` 的片段是**裸跑**：`& $py -B scripts/check_doc_claims.py ; & $py -B scripts/check_doc_claims.py --selftest`；
  - 只有 `docs/验收记录-批次18-2026-10-11.md:115` 记了**带参**形态：`scripts/check_doc_claims.py --coverage <run>/coverage.json` ⇒ `钉常量 vs 权威源：20/20 相等` / `RESULT: OK（violations=0）`。
- **② 的 4 条（= 归档锚点落后 `PINNED`）**：`method_level_non_get_total 158≠157`、`writable_rules_non_get 156≠155`、`smoke_targets 149≠148`、**派生键 `non_get_uncovered_method_level 40≠39`**（源式 `method_level_non_get_total − writable_any_covered_by_all` = `158−118` vs `157−118`）。⇒ **§1.5 的「第二套分母」实为 4 键**（第 4 键是**派生键**，不出现在 `coverage_drift` 的 D-1…D-9 里，故 §1.5 的表看不到它）。
- ⚠ **连带发现（B18-Q1b 的注入夹具是「空转注入」）**：`ci_gates.py:680 COVERAGE_ARCHIVE_ANCHOR` → `:710 def _inj_check_doc_claims(ctx)` 的注入**以该已漂移的归档锚点为基线**（`:716 src = COVERAGE_ARCHIVE_ANCHOR`），只把 `writable_any_covered_by_all` **下调 1**（`:726 summary[key] = before - 1`）并断言「至少报 2 条 violation」。但**基线本身就已 4 键不符**（见上）⇒ 注入后转红**不是因为那 −1**，而是**基线本来就红**。而 `ci_gates` 的 `injection_ineffective` 只判「**是否转红**」，不判「**是否因注入而转红**」⇒ 该步的阴性对照**在因果意义上不成立**（表面 PASS，实为空转）。这是「**挂点与产物混放**」纪律在**注入夹具层**的又一次复发（A-89 / N-1 同族）。
- **③ 转绿的原因（正面控制）**：`ci_gates.py:1054` 的 `'extra_argv': [{'tail': ['--coverage', '{json}'], 'json_name': 'coverage.json'}]` ⇒ 门禁链内该步**总是**被追加 `--coverage <本 run 产物>` ⇒ 链内绿是**真绿**。故此行与 §7.2 的「`check_doc_claims` OK」**不矛盾**：**链内绿、链外（裸跑）红**。
- **判定**：**`asset_defect`**（G-12 同族 + G-16②「无参出口」同族 + 注入夹具空转），**不得折算 pass**。
- **解除条件**（涉及既有判据与其阴性对照 ⇒ **必须走 A-70 三步**；本件只提供步骤①的现场读数，**不擅自改**）：
  1. 让 `read_sources()` 在 `coverage_path is None` 且默认锚点缺失时**发 `exit 2` + `[USAGE]`**（与 `coverage_drift` 对齐，消灭假红）；**或**把 `COVERAGE_JSON` 重指到一份**在世**的不可变快照（须同步 ③ 的 `extra_argv` 语义）。
  2. `COVERAGE_ANCHOR_READINGS`（`:73-80`）显式标注「**B18-Q1b 之前的读数**，落后 `PINNED` 共 4 键（含派生键 `non_get_uncovered_method_level`）」，或随锚点重选而更新。
  3. 注入夹具的**基线**改从与 `PINNED` 一致的快照取；或把判据从「转红」改为「**因该 −1 而新增 violation**」（否则无法区分真注入与空转）。
  4. 同步 `AGENTS.md:99` 与 `81-:467` 的调用形态（补 `--coverage`），使三处记载归一。

---

## 2. G-16② / P12 — 两处下游 `--coverage` 重指：**已修（B17-11）**

**口径**：`coverage_drift.py` 必须显式传 `--coverage <本次 run 产物>`；**缺参 = exit 2（用法错误），不是回归**。已同步 `40-第2轮实测Runbook与台账规范.md` §4.5。

### 2.1 `harness/reconcile_r2.py` — **已是带参形态**

- **工具**：`grep -n 'coverage_drift\|run_coverage_artifact' test-reports-2026-10/harness/reconcile_r2.py`
- **值（现场）**：`COVERAGE_DRIFT = 'test-reports-2026-10/harness/coverage_drift.py'`（`:324`）；`def run_coverage_artifact():`（`:327`）docstring 逐字「B17-11 / A-114：`coverage_drift.py` 必须显式 `--coverage <run 产物>`。缺参 = **exit 2（用法错误，不是回归）**…取值顺序：`HARNESS_COVERAGE` 环境变量 → `evidence/harness/*/coverage.json` 中 mtime 最新者 → 不可变归档快照 `ci-run-20261009-054416/coverage.json`（A-114：不读 live 路径）」；调用点 `:593` = `chk_subprocess([PY, '-B', COVERAGE_DRIFT, '--coverage', run_coverage_artifact()], …)`。`grep -n run_coverage_artifact` **仅命中 `:327` 与 `:593`** ⇒ **无第二处无参调用**。
- **行号订正**：任务书与 `70-` §4.1/§9.2/§10.8-1 记的 **`:555`** 是**旧版本行号**；现场 `:555` 是 C-10 夹具注释行（`# （uq_raw_material_internal_number）⇒ 只有它需要 RUN_ID 后缀；`），与本题无关。现场行号 = **`:324` / `:327` / `:593`**。

### 2.2 `harness/r2_v14_ledgerbook.py` — **command 已带参，notes 已记 B17-11**

- **工具**：`grep -n 'coverage_drift\|coverage %s' test-reports-2026-10/harness/r2_v14_ledgerbook.py`
- **值（现场）**：`REG-business` 条目 `:252` title「业务套件复跑读数（write_suite / negative_matrix / coverage_drift / permission_matrix）」；`:258-260` command 含 **`' --coverage %s/coverage.json；'`**（`:260`）；`:263` `'exit_code': 0`（**该 run 的历史读数，非无参命令的读数**）；`:267` observed 记 `coverage_drift 8/8（rules=271 / method_level_non_get=155 / writable=153 / literal=108 / any=116 / uncovered=0 / smoke_plan=148/9 / duplicate=0）`；`:292` `'class': 'improved'`；**`:296-298` notes 逐字**：「B17-11（2026-10-09）：coverage_drift 调用点补显式 `--coverage <run 产物>`（缺参 = exit 2 用法错误，不是回归 —— A-114）。`observed`/`criterion_digest` 仍为该 run 的历史读数，本次不重写。」
- **行号订正**：任务书记的 `:259-262` 与现场一致（command 块 `:258-262`）✅；但**「无参命令 + `exit_code: 0`」的描述与现场不符**——现场 command 已是带参形态，`:263` 的 `exit_code: 0` 属该历史 run 读数并由 `:296-298` 明确声明不重写。

### 2.3 交叉复核（本次实跑，四态）

| 调用形态 | 命令 | 实测 exit | 读数 |
| --- | --- | --- | --- |
| 自检 | `coverage_drift.py --selftest` | **0** | `自检结果 11/11 通过 => 敏感性 OK`（CD-N1…CD-N10 全 PASS） |
| **缺参（阴性对照）** | `coverage_drift.py` | **2** | `[USAGE] 未提供 --coverage…` + `[USAGE] exit 2 = 未提供产物（用法错误），不是覆盖退化 / 不是回归` |
| 显式传**死路径** | `--coverage test-reports-2026-10/evidence/harness/coverage.json` | **1** | `[FAIL] coverage.json 不存在：…`；`exit = 1 原因=[coverage.json 缺失]` |
| 显式传**归档锚点** | `--coverage evidence/harness/ci-run-20261009-054416/coverage.json` | **1** | 判据 4/8（见 §1.5） |

⇒ **`0` / `1` / `2` 三态语义现场成立**：`2` 与 `1` 可区分（用法错误 vs 真判据失败），「无参假绿」已消除。

---

## 3. G-17 — `40-第2轮实测Runbook与台账规范.md` §4.5 字段清单：**已提交**

- **工具 / 命令**：`git status --porcelain -- 'test-reports-2026-10/40-*'` 与 `git status --porcelain`（全量）
- **值**：**两条均无输出**（全量 `git status --porcelain` 仅 7 行，全部为 `??` 未跟踪，**无任何 `M` 行**）⇒ `40-` 的工作区版**已入库**，`81-` §6.2 为 G-17 设的判据「`git status` 不再显示 `M 40-…`」**已达**。
- **附带留档（口径纠偏）**：`70-` §9.2/§6.3 记的工作区态读数（`40-` = 56294 B / `1D3AECE5…`，`+22/-1`）属**当时未提交态**的读数；`40-` §4.5 工作区版相对 HEAD 的追加内容为 `method_level_non_get=155 · writable_literal=108 · writable_any=116 · uncovered_writable=0` + N-1 说明 + 回退三步。**追改 HEAD 版不在本件范围**（约束 ③ 既有文件不覆盖）。
- **判定**：**已同步**。

---

## 4. G-20 — 同一 CSRF 面两个分母：**已只留一个**

- **口径**：按 `35-` §4「同类原则只留一个」，且**保留可复跑的那个**。被废者 = **按响应文案匹配的 24 条判据**；保留者 = **状态码 + 哨兵标记口径**：唯一分母 = 非豁免 **133** = 155 站点 − 22 豁免；判据 = 拦截率 `133/133`。
- **工具 / 命令**：`grep -n 'def csrf_matrix' test-reports-2026-10/harness/api_matrix.py` + 读 `:732-760`
- **值（现场）**：`def csrf_matrix(app, facts):` 在 **`:733`**；`:753-757` 现场注释逐字：「**A-69 / B18-08**：CSRF 判据**不再断文案**（统一 errorhandler 已换掉 CSRFError 文案，旧文案判据漏判了 24 条真被拦下的请求）。稳定标记：`CSRFProtect` 的 `csrf_protect`…」⇒ **24 条文案判据已废且已删除/改写**。
- **行号订正**：任务书与 `70-` §9.2/§10.8-5 记的 `scripts/api_matrix.py:808-809` —— ① **路径不存在**（`scripts/api_matrix.py` 现场无此文件，实际路径 = `test-reports-2026-10/harness/api_matrix.py`，869 行 / 45196 B）；② 行号 `808-809` 为旧版本行号，现场对应位置 = **`api_matrix.py:733`（函数定义）/ `:753-757`（A-69 注释）**。
- **判定**：**已同步（同一 CSRF 面只剩 `133/133` 一个分母）**。

---

## 5. G-22 / P11 — 仓库根 6 个 `.tmp_v15_*.{out,err}`：**已消除（6 → 0）**

- **工具 / 命令**：
  - `ls -la .tmp_v15_*`（仓库根）
  - `git status --porcelain`（全量，逐行核）
  - `git ls-files | grep tmp_v15`
  - `grep -n 'tmp_v15\|\.tmp_p01\|\.tmp/' .gitignore`
- **值（实测）**：
  - `ls -la .tmp_v15_*` ⇒ **`No such file or directory`**（6 个文件一个都不在）
  - `git status --porcelain` ⇒ **无任何 `.tmp_v15_*` 行**（仅 `.tmp/`、`.vscode/settings.json`、`app.db.evidence-ALLOY-IMPORT-02-20261009_004539`、`instance/`、`test-reports-2026-10/.tmp-t6runs/`、`test-reports-2026-10/.tmp-t9runs/` 6 条 `??`）
  - `git ls-files | grep tmp_v15` ⇒ **零命中**（从未入库）
  - `.gitignore` 相关行仅 `16:.tmp_p01/`、`17:tmp_p01/`、`41:/test-reports-2026-10/.tmp/` —— **无 `.tmp_v15_*` 规则**（因为它们已不存在，无需规则）
- **判定**：**已消除**，与 `81-` §6.2 的 G-22 归属（批次17 `B17-12` 登记，状态「已消除（原 6 个 → 0）」）一致。⇒ 无需删除动作、无需新 `.gitignore` 规则。
- **P11 部分关闭的现场复核**：`81-` §6.3 记「原载体已清 + `_probe_tmp/gate-baseline.txt` 系 captain 自跑残留、已删除；`scripts/_probe_seed.py`（mtime 2026-08-27）先于本轮、不并入 P11」⇒ 与本次 `git status` 读数一致。**不折算 pass**：P11 状态仍为**部分关闭**。

---

## 6. B18-06 三项治理（**本件只落文档措辞/口径，未实现任何行为变更**）

> **依据**：`81-后续开发与测试规划.md:519`（任务行）、`:535`（验收）、`:861`（**用户裁定第 7 条**）。`B18-05-批次收口台账.md` §2 只做了**现状核查**（自述「只核查现状，未改业务代码」），其中 `delivery_batches` 视图口径记 `not_measured` ⇒ 本件补齐口径说明。

### 6.1 ① `delivery_batches` 对照视图口径说明

- **工具 / 命令**：`grep -rn 'delivery_batches' --include=*.py --include=*.html app/ scripts/`（排除 `__pycache__`）+ 读 `app/models.py:1813/1845/1913/1923/1929/1966`
- **值（实测）**：
  - 归属：类 `app/models.py:1813 class SalesOrderItem(db.Model)`；列 `:1845 delivery_batches = db.Column(db.Text)  # JSON格式: [{"batch_no": 1, "delivery_date": "2025-01-15", "quantity": 10, "notes": ""}]`（**订正：不是 `ProductionOrder`**）
  - **计划面读写通路（实测完整）**：`app/main/routes.py:10705` `@bp.route('/sales_order_item/<int:item_id>/delivery_batches/manage', methods=['GET'])` → `:10708 def manage_delivery_batches_page` → `:10712 batches = order_item.delivery_batches_list` → `:10714 render_template('main/delivery_batches.html',…)`；`app/main/routes.py:10717` `@bp.route('/sales_order_item/<int:item_id>/delivery_batches', methods=['GET','POST'])` → `:10721 def manage_delivery_batches` → **写** `:10737 order_item.set_delivery_batches(batches)`、**读** `:10765 'batches': order_item.delivery_batches_list`（JSON 出口）
  - 模型内：属性 `:1913 delivery_batches_list`（`json.loads`，异常回落 `[]`）、`:1923 set_delivery_batches`（`json.dumps(..., ensure_ascii=False)`）；只读派生 `:1929 def delivery_status` / `:1966 def delivery_progress`（均只按 `delivery_date` 与 `date.today()` 比较**推算**）
  - 模板消费：`app/templates/main/sales_order_detail.html:165`（`{% set batches = item.delivery_batches_list %}`）、`:186`/`:191`（编辑链接）、`:421`/`:478`/`:680`（`fetch` 调 `/delivery_batches`）；`app/templates/main/delivery_batches.html:289`（`apiFetch`）
  - **执行面零命中（实测）**：`grep -c delivery_batches` ⇒ `app/main/shipping.py` = **0**、`app/main/stock.py` = **0**、`app/utils/excel_generator.py` = **0**。（`scripts/check_table_parity.py:80` 只是把表名 `sales_order_delivery_batches` 列在跳过表里，与本题的**列** `delivery_batches` 不是同一物。）
- **口径说明（默认路径）**：`delivery_batches` 是**销售订单行**（`SalesOrderItem`）上的**计划面 JSON 快照**（计划交货批次），**有**完整的录入/编辑/展示通路。但它与**执行面**（发货单 / 库存动作 / 导出）**零连接**：无外键、无自动比对、不驱动任何库存或发货实体，模型内只派生两个只读汇总量。⇒ B10-07 / `G-B` / `REQ-C-04` 所要求的「**对照视图**（计划批次 ↔ 实际发货）」**当前不存在，也不自动成立**：需**新增**只读对照页 + 差异判定口径，**本件不实现**（任务硬约束：不改业务代码 `app/**`）。
- **状态**：`not_measured`（对照视图未实现，无法测量计划-执行差异）——**不得折算 pass**。
- **解除条件**：若业务要该视图，需单独立项（新页面 + 差异判定口径 + 空值/旧数据兼容），并给出「计划批次数 / 实际发货行数 / 差异行数」三个实测值。
- **备查（既有实现瑕疵，不属本件范围）**：`delivery_status`（`:1929`）内 `:1948` 注释自称「这里假设到货日期就是交付日期」，且 `:1949` `if delivery_date < today:` 与 `:1951` `elif delivery_date < today:` **条件同构** ⇒ `:1952` 的 `overdue_count += 1` **不可达**（`:1960 elif overdue_count > 0:` 分支永不生效）。仅登记，不改。

### 6.2 ② 客户删除关联校验（G-E）——按**用户裁定第 7 条**落措辞

> ⚠ **本小节推翻了裁定所依据的前提。** 用户裁定第 7 条（`81-:861` 逐字）称「现状是**允许裸删**（`app/main/routes.py:9293`）」，**该前提与现场实测不符**（见下）。本件**未改任何业务代码、未实现 400**（遵裁定「保持现状」），但**必须**把「现场到底是什么」如实登记，否则措辞会把错误前提固化。

#### 代码现场（工具：`grep -n 'def delete_customer' -A 40 app/main/routes.py`）

- `app/main/routes.py:9905` `@bp.route('/customer/<int:customer_id>/delete', methods=['DELETE'])`；`:9906` `@login_required`；`:9907` `@require_capability('customer.delete')`；`:9908` `def delete_customer(customer_id):`（**行号订正**：`81-:861`/`81-:519`/`B18-05` §2 记的 `:9293` 与 `:9258-9296`、TODO 在 `:9267-9268` 均为**旧版本行号**；现场 = `:9905-:9908`，TODO 在 **`:9915`**）
- `:9912` `customer = Customer.query.get_or_404(customer_id)`
- **`:9914-9915` 逐字**：`# 检查是否有关联的订单或其他业务数据` / `# TODO: 添加订单关联检查` ⇒ **关联校验为零**（只有注释）
- `:9917-9938` 组装 `old_data` 并写 `AuditLog(action='删除客户', can_rollback=True, rollback_type='delete', target_model='Customer')`
- `:9940-9941` `db.session.delete(customer)` + `db.session.commit()`
- `:9943` 成功出口 = `jsonify({'success': True, 'message': '客户删除成功'})`
- `:9945-9948` 失败出口 = `except Exception as e: _reraise_http(e); db.session.rollback(); return jsonify({'success': False, 'message': '删除失败，请稍后重试或联系管理员'})` —— ⚠ **未记日志**（无 `current_app.logger`）；`_reraise_http`（`routes.py:99-103`）只对 `HTTPException` 重抛，其余异常一律落到这条**泛化 200**
- 模型：`app/models.py:1771 class SalesOrder`，`:1779 customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)`（**无 `ondelete`**）；`app/models.py:1730 class CustomerAddress`，`:1736 customer_id = ... db.ForeignKey('customers.id', ondelete='CASCADE')`

#### 行为实测（成对对照；工具 = `.tmp/t2-ge-probe/probe_ge2.py`，走 `scripts/_test_bootstrap.make_app()` 库副本，约束 ②）

- **库内 FK 强制**：`PRAGMA foreign_keys = 0`（**未强制**；`app/`、`config.py`、`scripts/_test_bootstrap.py` 内无 FK pragma 监听器，仅业务层 `routes.py:4627` 用 `col.foreign_keys` 做元数据遍历）
- **ORM 层根因**：`db.session.delete(customer)` + `commit()` ⇒ **`IntegrityError: NOT NULL constraint failed: sales_orders.customer_id`**，`[SQL: UPDATE sales_orders SET customer_id=?, updated_at=? WHERE sales_orders.id = ?]`，`[parameters: (None, '2026-10-12 04:49:49.222403', 5)]` ⇒ **SQLAlchemy 在父行删除时对子 FK 执行「置空」（默认 save-update/nullify 行为），撞上子列 `nullable=False` ⇒ 整体回滚**
- **HTTP 成对读数**：

  | 对照 | 客户 | HTTP | body | 删除后客户仍在？ | 名下订单数 |
  | --- | --- | --- | --- | --- | --- |
  | **阴性对照** | 无订单 | **200** | `{"message":"客户删除成功","success":true}` | **False（删除成功）** | — |
  | **阳性** | 有 1 张订单 | **200** | `{"message":"删除失败，请稍后重试或联系管理员","success":false}` | **True（已回滚）** | **1** |

- 真库旁证：探针前后 `app.db` sha256 均 `34e48e7a21163db390eebda4f2030343f3609afedc65d8c6e909d6eb5a49177e`，`unchanged = True`。

#### 结论：现状 = **数据层已兜住 + 出口被静默吞成 200**

- **现状 ≠「允许裸删」**：有订单客户的删除**不会成功**（订单不会悬挂引用，`customer_id` 未被置空——因整笔事务回滚）。
- **现状 ≠「400 + 提示」**：客户端拿到的是 **HTTP 200 + `success:false` + 泛化文案**，且**服务端无日志** ⇒ 运维不可观测、用户不可理解。
- ⇒ **「禁止删除有订单客户」这一目标在数据层已事实上达成**；真正缺的是**出口语义（应 400 + 明确原因）与可观测性（应记日志）**。

#### 文档措辞（按**实测现场**落定的权威表述）

> 「客户删除（G-E）**现场行为**：无订单客户可正常删除（HTTP 200 / `success:true`）；**有订单客户的删除会失败并整体回滚**（HTTP 200 / `success:false` / 文案「删除失败，请稍后重试或联系管理员」），订单**不会**变成悬挂引用。该拦截由数据层兜住（SQLAlchemy 父行删除时对 `sales_orders.customer_id` 置空撞 `nullable=False` ⇒ `IntegrityError`），**不是**显式关联校验——`app/main/routes.py:9914-9915` 至今只有 `# TODO: 添加订单关联检查`。**不实施 400 拦截**（遵用户裁定第 7 条「保持现状」，2026-10-12 复核）。⚠ 裁定原前提「现状是允许裸删」已被实测证伪；若业务要「允许删除有订单客户」，须单独立项（明确订单归属/级联口径）；若只要「可理解的拒绝」，则须把出口改为 400 + 明确提示并补日志——两者都是**业务代码变更**，不在本件范围。」

- **前提不符登记（须 captain/用户复议）**：`81-:861` 的裁定建立在「现状 = 允许裸删」之上，而现场为「删除失败 + 静默 200」。**裁定方向（保持现状、不实现 400）本件照办**，但**措辞不得写成「允许删除」**——否则文档将与现场再次不符。
- **约束遵守**：`docs/**` 既有文件**不覆盖**（约束 ③）；本措辞以**本新增件**为权威载体，供后续新建订正件转引。未改 `app/**`（任务硬约束）。

### 6.3 ③ `CodeGenerationLog` / `api_execute_operation` / `G-K` 三入口职责边界

#### 6.3.a `CodeGenerationLog`（编码规则日志页）——**默认路径 = 保留模型 + 不建页面**

- **工具 / 命令**：`grep -rn 'CodeGenerationLog' --include=*.py --include=*.html .`（排除 `.tmp/`）
- **值（实测）**：
  - 定义：`app/models.py:735` `class CodeGenerationLog(db.Model):`（旧记 `models.py:732` ⇒ 已漂至 `735`）
  - **写点 2**：`app/main/routes.py:6105`（编码规则生成后写入）、`app/models.py:1160`
  - **读点 0**：`app/**` 与模板中**无任何查询/渲染该表**的代码（⇒ 无 `编码规则日志` 页面）
- **口径说明（默认路径）**：`CodeGenerationLog` 属**纯留痕**用途——写多读零，**无页面、无报表、无导出**。默认路径 = **保持现状（只写不读）**，不新增页面；其价值是事故时可直查库定位编码发号历史。
- **状态**：`not_measured`（无 UI 可测）。**解除条件**：若要可查，需单独立项（列表页 + 分页/筛选 + 权限能力登记，参考 §6.3.c 的三入口边界口径）。

#### 6.3.b `production_center.py:309 api_execute_operation`（工序执行记录）——职责边界

- **工具 / 命令**：`grep -n '@bp.route' app/main/production_center.py` + 读 `:309-397`
- **值（实测）**：
  - `app/main/production_center.py:309` `@bp.route('/api/production_center/items/<int:item_id>/execute_operation', methods=['POST'])`；`:313` `def api_execute_operation(item_id: int):` docstring「记录工序执行（操作者与物料消耗），并更新相关任务进度」
  - 其写入面（`:330-397` 实测）：`:335` `ProductionRecord(`、`:354` `ProductionRecordMaterial(`（`:343` `db.session.add(prod_record)`、`:344` `flush()`）、`:361-` 同步任务进度、`:378` `AuditLog(`（`:384` `target_model='ProductionRecord'`）、`:390` `db.session.commit()`、`:391` 返回 `{'success': True, 'message': '记录成功', 'data': {'record_id': prod_record.id}}`、`:395` `db.session.rollback()` + **`:396` `current_app.logger.error(f'记录工序执行失败：{str(e)}')`** + `:397` 返回 500。
  - **`:330-400` 内零 `stock` / `Stock` 命中** ⇒ 该端点**不触碰正品库**。
  - **对照点**（与 §6.2 的 `delete_customer` 比）：本端点 `:396` **有** `logger.error`，而 `delete_customer:9945-9948` **无**任何日志 ⇒ 「静默 200」是该端点**独有**的出口缺陷，不是全仓通例。
- **口径说明**：`api_execute_operation` = **工件域（`/production_center`）的工序执行记录写入口**，职责 = 「记生产记录 + 物料消耗 + 审计日志 + 推进任务进度」；**不含**正品库入库。此边界与 `routes.py:3966` 的权威声明一致（见 6.3.c）。

#### 6.3.c `G-K` 三入口职责边界（`03-需求追溯矩阵.md` GAP-45 / REQ-E-02）

- **口径来源**：**权威声明已在代码中**——`app/main/routes.py:3965-3968` 逐字：
  > `# 决策 1：报工路径末道工序完成后按工件域 MES 口径把产出计入正品库（stock_kind='fg'）。`
  > `# 两套入口并存：只补 /my_tasks 报工这条链，工件域（/production_center + 质检）路径不动。`
  > `# 门禁、末道判定、幂等都由 mes_service 统一负责（本次报工自身随之创建的质检任务属于`
  > `# 下游流程，其不合格由既有未通过库口径处置；入库前仍须过 qc_gate_allows_output）。`
- **三入口现场读数（工具：`grep -n '@bp.route' app/main/production_center.py` + `grep -n "my_tasks" app/main/routes.py`）**：

  | # | 入口 | 位置 | 权限 | 职责（现场） |
  | --- | --- | --- | --- | --- |
  | 1 | `/my_tasks`（员工自助报工链） | `app/main/routes.py:4086`（`def my_tasks()` `:4088`，docstring「查看我的任务」；`:4097` 按 `TaskAssignment.employee_id` 取本人任务） | `@login_required`（`:4087`；**无** `@require_capability`）；能力 `my_tasks.use` 登记在 `app/permissions.py:96` `'my_tasks.use': ('user',)`，使用点 `routes.py:447`/`:449`（工作台角色推导）/`:3532`（`@require_capability('task.manage','my_tasks.use')`） | 员工查看本人任务 → 报工；**末道工序完成后按 MES 口径把产出计入正品库（`stock_kind='fg'`）**，入库前过 `qc_gate_allows_output` |
  | 2 | `/production_center`（工件域管理端） | `app/main/production_center.py:23`（页面）/ `:63`（实例详情）/ `:95`（`api_create_instances`） | 见各端点装饰器（`production_center` 能力族） | 管理员按生产订单创建成品实例、查看实例；**走工件域路径，不做 `/my_tasks` 的报工入库** |
  | 3 | `/api/production_center/execute_operation/<item_id>` | `app/main/production_center.py:309`（`def` `:313`） | 见端点装饰器 | 记工序执行 + 物料消耗 + 审计 + 推进任务进度（**不碰正品库**，§6.3.b） |
- **职责边界口径（落定表述）**：
  > 「**两套入口并存，边界 = 是否走「报工链末道入库」**：`/my_tasks`（员工报工链）在末道工序完成时按工件域 MES 口径把产出计入正品库（`stock_kind='fg'`，`app/main/routes.py:3965-3968`）；`/production_center` + 质检（工件域）路径**不动**，其 `execute_operation`（`production_center.py:309`）只写 `ProductionRecord` / `ProductionRecordMaterial` / `AuditLog` 并推进任务进度，**不写库存**。门禁、末道判定、幂等统一由 `app/services/mes_service.py` 负责；入库前必须过 `qc_gate_allows_output`。」
- **状态**：口径**已给出**；`03-需求追溯矩阵.md` GAP-45 / REQ-E-02 所称「职责边界无断言（仅各自 200）」的**断言缺口仍在** ⇒ 该项 `not_covered`（本件只给口径，未加断言）。**解除条件**：若要断言化，须在 `harness` 现有工具内加「同一产出经两入口后 `stock_kind='fg'` 行数不变」的成对判据（**不得新起并行工具**）。

---

## 7. 门禁复核与 A-70 适用性判定

### 7.1 A-70 三步**不适用**于本件的理由

本件**未改动任何判据 / 钉值 / 期望值**：所有实测差异均被判定为「已由 B17-11 / B17-12 / B18-08 修复」或「口径问题待 owner 裁决」。故约束 ⑤ 的 A-70 三步（① 旧值留档 → ② 阴性对照先转红 → ③ 改值 + 复跑绿 + 登记件）**无改值对象**。三处残留（§1.5 / §1.6 / §1.7）**若**要改值，必须先由 owner 立项并补 A-70 第①②步——本件只提供①的现场读数。

### 7.2 `ci_gates.py --phase first` 实测（约束 ⑨）

- **命令**：`/opt/wage-venv/bin/python -B test-reports-2026-10/harness/ci_gates.py --phase first`
- **值**：

  | 项 | 读数 |
  | --- | --- |
  | **steps** | **20** |
  | **blocking 失败** | **无** ✅ |
  | report-only 失败 | `['evidence_hash']` |
  | 注入未生效 | 无 |
  | 仓库根两 JSON 未被触碰（A-11） | `True` |
  | gaps | `A-63-STEP2-BUILD-GATE = blocked`（不计入通过数） |
  | **exit** | **2**（语义 `2 = 仅 report-only 失败`） |

- 逐步（20 步全 OK，除 `evidence_hash`）：`check_table_parity` 2/2、`check_properties` 4/4、`check_db_bootstrap` 4/4、`run_gates` 4/4（其 `env-probe route_inventory_native_probe: native_exit=0 expected=1 verdict=unexpected` 属 A-62 环境依赖探针**预期**不匹配）、`functional_test` 2/2、`permission_matrix` 3/3、`smoke_test` 3/3、`route_inventory` 3/3、`measure_coverage` 1/1、`coverage_drift` 2/2、`check_notification_triggers` 5/5、`check_model_refs` 5/5、`check_http_contract` 4/4、**`evidence_hash` FAIL exit=1 checks 3/4**、`chain_count_consistency` 8/8、`negative_matrix` 5/5、`check_is_archived_policy` 3/3、**`check_doc_claims` OK exit=0 checks 5/5**。
- ⚠ **「`check_doc_claims` OK」只在链内成立，不可外推**：该步的绿来自 `ci_gates.py:1054` 的 `'extra_argv': [{'tail': ['--coverage', '{json}'], 'json_name': 'coverage.json'}]` —— 门禁链**总是**把本 run 的 `coverage.json` 显式传给该脚本；**裸跑（不带 `--coverage`）则 exit 1 / violations=11**（§1.7 实测 20/29）。⇒ 本行**不代表**该脚本可直接裸跑。
- **产物落点**：`test-reports-2026-10/evidence/harness/ci-run-20261012-044515/`（`.gitignore:42` 忽略，本地留档不追改）——含 `ci_gates_first.console.txt`（46920 B）、`coverage.json`（246692 B）、`evidence_hash.gate.json`（219259 B）、`gates.json`、`negative_matrix.json`、`route_inventory.stdout.txt`、`chain_count_consistency.json`、`http_contract.json`、`evidence_whitelist.registered.json`、`evidence_journal.jsonl`。
- **三次独立复跑，读数逐行一致（可重复性）**：`ci-run-20261012-044515`、`ci-run-20261012-045456`、`ci-run-20261012-045618` ⇒ 三次均 `steps=20` / `blocking 失败 = 无` / `report-only 失败 = ['evidence_hash']` / `注入未生效 = 无` / `仓库根两 JSON 未被触碰 = True（A-11）` / `exit = 2`。⇒ 上表读数**非单次抖动**；第 3 次复跑所测内容的工作区 blob = `21bed9ef7949d5f9d7ef070e8ab700d63508c9b9`（与暂存 blob 同一 commit 前一致）。
- ⚠ **约束 ⑨ 的「exit 0」当前不可达**：`blocking 失败 = 无` 已满足，但 `evidence_hash` 这一 **report-only** 项把 exit 压到 `2`。这与 `AGENTS.md` 登记的既有基线读数（`20 步 / blocking 失败=无 / report-only=['evidence_hash'] / exit=2`）**完全一致** ⇒ **非本次引入的回归**，但该约束的「exit 0」字面**必须**按 report-only 语义解读，或先清除 §7.3 的两条违规。

### 7.3 `evidence_hash` report-only 失败的现场机制（**G-12 同族：挂点与产物混放**）

- **工具 / 文件**：`test-reports-2026-10/evidence/harness/ci-run-20261012-044515/evidence_hash.gate.json`
- **值（实测）**：
  - `verdict = "violation"`；`violations_total = 2`；`counts = {"baseline_files": 1433, "current_files": 2239, "modified": 2, "deleted": 0, "journal_broken": 0, "added": 806, "index_missing": 91, "coverage_gap": 2, "phantom_entry": 0, "baseline_tampered": 0, "dirs_conform": 166, "dirs_total": 259}`
  - 两条违规均为 `kind: "modified"`：
    ① `harness/b17-verify/probe_permission_matrix.txt`：基线 `1664B44BF5FB227B…` / 9627 B → 现 `F81525C2B3CF4A5E…` / **11234 B**
    ② `harness/b17-verify/probe_smoke_test.txt`：基线 `59A7E5F065716E43…` / 3186 B → 现 `DA0C377DA223D63B…` / 3186 B（**同字节数、异 sha**）
  - whitelist：`test-reports-2026-10/harness/t8-evidence-whitelist.json`，`registered: 0`，`unregistered_count: 2`，`unregistered_first10 = ["modified|harness/b17-verify/probe_permission_matrix.txt", "modified|harness/b17-verify/probe_smoke_test.txt"]`；断言 `no unregistered violation` **失败**。
  - 两文件 mtime = `2026-10-12 04:45:29.081386626` / `04:45:16.035562426` UTC ⇒ **落在本次 `ci_gates` 运行窗口内，由本次探针步骤原地重写**。
  - 旁证：`real_db_matches_pinned = true`（真库未被触碰，与 §0 三值一致）。
- **机制判定**：这两条路径**既是冻结基线成员、又是会被探针原地写出的活产物** ⇒ 任何跑过该探针的 run 都会触发 `modified`。属 `AGENTS.md` 已登记的「挂点与产物分离」纪律（A-89 同族）**未覆盖到的漏点**：`evidence/harness/b17-verify/probe_*.txt` 被 `artifact_hashes.json` 基线纳入，却由探针每次覆写。
- **状态**：`blocked`（report-only，不阻断 blocking 判据）。**不得折算 pass**。
- **解除条件**（二选一，须 owner 裁决）：① 把 `harness/b17-verify/probe_*.txt` 改为**按 run_id 落新目录**（新产物不覆盖基线成员），并重建基线；② 或按 A-89 纪律把这两条从基线索引中摘除（判据改从不可变快照读取）。

---

## 8. 未测项 / 非 pass 状态登记（约束 ④）

| # | 项 | 状态 | 解除条件 |
| --- | --- | --- | --- |
| 1 | §1.5 归档锚点 = 第二套分母（**4 键**：`157/155/148` + 派生键 `non_get_uncovered_method_level 39` vs `PINNED 158/156/149/40`） | `asset_defect`（**不折算 pass**） | owner 裁决：只在 `COVERAGE_ANCHOR_READINGS` 显式标注「B18-Q1 之前读数（落后 4 键）」，或走 A-70 重基线 |
| 2 | §1.6 `b17_governance_contract.py` B17-11 条目永久转红 | `blocked`（口径未定，**非回归**；该文件未进门禁链） | owner 二选一：补「提交后态」判据，或头部声明「仅提交前有效」 |
| 3 | §6.1 `delivery_batches` 对照视图 | `not_measured` | 立项做只读对照页，并给出计划批次数 / 实际发货行数 / 差异行数三个实测值 |
| 4 | §6.3.a `CodeGenerationLog` 日志页 | `not_measured` | 立项做列表页 + 权限能力登记 |
| 5 | §6.3.c G-K 职责边界的**断言**缺口（GAP-45 / REQ-E-02） | `not_covered` | 在现有 `harness` 工具内加「两入口产出后 `stock_kind='fg'` 行数不变」成对判据（不得新起并行工具） |
| 6 | §7.2 `ci_gates --phase first` 的 **exit 0** | `not_achieved`（`blocking 失败=无` 已满足；exit=2 仅因 report-only） | 处置 §7.3 的两条 `modified` ⇒ 复跑取 exit 0 |
| 7 | §7.3 `evidence_hash` report-only | `blocked` | 同上（探针产物改按 run_id 落盘，或摘出基线索引） |
| 8 | P11（`70-` §4.1 原始载体） | **部分关闭**（与 `81-` §6.2 一致） | 原载体已清；其余子项按 `81-` 归属继续 |
| 9 | §1.7 `check_doc_claims.py` **裸跑假红 11 条**（`RESULT: FAIL（violations=11）` / exit 1，与真违规同码） | `asset_defect`（**不折算 pass**；链内绿不代表可裸跑） | 改 `read_sources()` 为 `exit 2 + [USAGE]`，或把默认路径重指在世快照 ⇒ **走 A-70** |
| 10 | §1.7 注入夹具 `_inj_check_doc_claims` **空转**（基线已 4 键漂移，转红非因注入） | `blocked`（**阴性对照不成立**，`injection_ineffective` 判据不覆盖） | 夹具基线改取与 `PINNED` 一致的快照；或判据改为「因该 −1 而**新增** violation」 |
| 11 | §1.7 文档口径三处并存（`AGENTS.md:99` 裸跑清单 / `81-:467` 裸跑片段 / `docs/验收记录-批次18-2026-10-11.md:115` 带参） | `asset_defect`（同 G-20「同类原则只留一个」） | 三处归一为带 `--coverage` 形态（`AGENTS.md` 属 inScope 可改；`81-`/`docs/` 须新建订正件转引） |

---

## 9. 复现命令清单（逐条可复跑）

```bash
cd /root/code/MyERP
P=/opt/wage-venv/bin/python
A=test-reports-2026-10/evidence/harness/ci-run-20261009-054416/coverage.json

# G-12 §1.1-1.3：下游产物无陈旧字面分母
grep -n '101\|141' test-reports-2026-10/harness/analysis_ledger.py   # 零命中
grep -n '101\|141' test-reports-2026-10/harness/improve_plan.py      # 零命中
sed -n '449,470p'   test-reports-2026-10/harness/final_recount.py     # coverage_pins() 绑定 PINNED

# G-12 §1.5：归档锚点 = 第二套分母（exit 1，判据 4/8）
sha256sum "$A"                                                        # 58bf8446…21e055
$P -B test-reports-2026-10/harness/coverage_drift.py --coverage "$A"

# G-12 §1.6：B17 契约 B17-11 条目转红（exit 1）
$P -B test-reports-2026-10/harness/b17_governance_contract.py --only B17-11
git show HEAD:test-reports-2026-10/harness/r2_c07_probe.py | grep -n "ROUTE_RULES_BASELINE = "
grep -rn 'b17_governance_contract' test-reports-2026-10/harness/ci_gates.py \
     test-reports-2026-10/harness/run_gates.py scripts/              # 零命中 = 未进门禁链

# G-12 §1.7：check_doc_claims 三态（裸跑假红 11 条 / 归档锚点 4 条 / 本 run 产物 0 条）
C=test-reports-2026-10/evidence/harness/ci-run-20261012-044515/coverage.json
$P -B scripts/check_doc_claims.py                    # 20/29，violations=11，RESULT: FAIL，exit 1
$P -B scripts/check_doc_claims.py --coverage "$A"    # 25/29，violations=4， RESULT: FAIL，exit 1
$P -B scripts/check_doc_claims.py --coverage "$C"    # 29/29，violations=0， RESULT: OK，  exit 0
ls -la test-reports-2026-10/evidence/harness/coverage.json   # No such file or directory ⇒ :67 默认路径已死
sed -n '67p;73,80p' scripts/check_doc_claims.py              # COVERAGE_JSON / COVERAGE_ANCHOR_READINGS
sed -n '1052,1069p' test-reports-2026-10/harness/ci_gates.py # extra_argv 追加 --coverage（链内绿的来因）
sed -n '710,730p'   test-reports-2026-10/harness/ci_gates.py # _inj_check_doc_claims 基线 = 同一归档锚点
grep -n 'check_doc_claims' AGENTS.md                                 # :99 裸跑清单（未注明须带参）
grep -n 'check_doc_claims' test-reports-2026-10/81-*.md              # :467 裸跑片段
grep -n 'check_doc_claims' docs/验收记录-批次18-2026-10-11.md         # :115 带 --coverage（正确形态）

# G-16② §2：三态语义 + 两处已是带参形态
$P -B test-reports-2026-10/harness/coverage_drift.py --selftest      # exit 0，11/11
$P -B test-reports-2026-10/harness/coverage_drift.py                 # exit 2（用法错误）
$P -B test-reports-2026-10/harness/coverage_drift.py \
     --coverage test-reports-2026-10/evidence/harness/coverage.json  # exit 1（产物缺失）
grep -n 'run_coverage_artifact' test-reports-2026-10/harness/reconcile_r2.py   # :327 / :593
grep -n 'coverage %s/coverage.json' test-reports-2026-10/harness/r2_v14_ledgerbook.py  # :260

# G-17 §3：已提交
git status --porcelain -- 'test-reports-2026-10/40-*'                # 空

# G-20 §4：已只留一个分母
grep -n 'def csrf_matrix' test-reports-2026-10/harness/api_matrix.py  # :733
sed -n '753,757p' test-reports-2026-10/harness/api_matrix.py          # A-69：不再断文案

# G-22 §5：已消除
ls -la .tmp_v15_* 2>&1                                                # No such file or directory
git status --porcelain | grep tmp_v15                                 # 空
git ls-files | grep tmp_v15                                           # 空

# B18-06 §6.1：delivery_batches 归属 + 消费面
grep -n 'delivery_batches = db.Column' app/models.py                  # :1845（类 SalesOrderItem = :1813）
grep -rn 'delivery_batches' --include=*.py --include=*.html app/ scripts/ | grep -v __pycache__
for f in app/main/shipping.py app/main/stock.py app/utils/excel_generator.py; do
  printf '%s = %s\n' "$f" "$(grep -c delivery_batches $f)"; done         # 全 0（执行面零连接）

# B18-06 §6.2：G-E 现场（成对对照，走库副本；真库 sha256 前后一致）
$P -B test-reports-2026-10/.tmp/t2-ge-probe/probe_ge2.py               # NEG 200/success:true；POS 200/success:false
grep -n 'def delete_customer' -A 43 app/main/routes.py                 # :9908；:9914-9915 TODO；:9940-9941 裸删；:9945-9948 静默 200（无 logger）
grep -n 'class SalesOrder' -A 12 app/models.py | grep customer_id      # :1779 nullable=False，无 ondelete

# B18-06 §6.3：日志表 / 工序端点 / G-K 边界
grep -n 'class CodeGenerationLog' app/models.py                       # :735
grep -rn 'CodeGenerationLog' --include=*.py --include=*.html app/     # 写点 routes.py:6105 + models.py:1160；读点 0
grep -n '@bp.route' app/main/production_center.py                      # :309 = /api/production_center/items/<id>/execute_operation
grep -n 'def api_execute_operation' -A 4 app/main/production_center.py # :313
sed -n '3965,3968p' app/main/routes.py                                 # G-K 权威边界声明（stock_kind='fg'）
grep -n "my_tasks" app/permissions.py                                  # :96 'my_tasks.use': ('user',)

# 门禁（约束 ⑨）
$P -B test-reports-2026-10/harness/ci_gates.py --phase first           # steps=20 / blocking=无 / exit=2

# 真库三值（前后各一次）
sha256sum app.db && stat -c '%s %y' app.db
```

---

## 10. 收尾声明

- **未覆盖任何既有文件**；本件为 `test-reports-2026-10/` 下**新增件**（约束 ③）。`docs/**` 未动一字节（含 `docs/test-reports/2026-10/03-需求追溯矩阵.md` 的 GAP-45 转引）。
- **未改任何判据 / 钉值 / 期望值** ⇒ 无需 A-70 三步（理由见 §7.1）；三处残留（§1.5 / §1.6 / §1.7）**只登记不擅改**。
- **未改业务代码 `app/**`**；未实现任何行为变更（含 G-E 的 400 拦截，遵用户裁定第 7 条「保持现状」）。
- ⚠ **本件最重要的一条（工具缺陷）**：§1.7 —— `scripts/check_doc_claims.py` **裸跑 = 假红 11 条**（`RESULT: FAIL（violations=11）` / `exit 1`，与真违规**同码**），因为其默认覆盖源 `test-reports-2026-10/evidence/harness/coverage.json`（`:67`）**已不存在**；且 `AGENTS.md:99` 恰好把该脚本列入「优先裸跑」的静态脚本清单。同族 `coverage_drift.py` 缺参已修成 `exit 2 + [USAGE]`（P12），**本脚本尚未对齐**。连带发现 `ci_gates` 的 `_inj_check_doc_claims` 注入夹具**空转**（基线自身已 4 键漂移 ⇒ 转红非因注入）。⇒ **链内绿 ≠ 可裸跑**。
- ⚠ **次重要**：§6.2 用**成对对照实测**证伪了用户裁定第 7 条所依据的前提（「现状是允许裸删」）。现场真相 = 「有订单客户的删除**会失败并整体回滚**，但出口是 **HTTP 200 + `success:false` + 泛化文案、且无日志**」。裁定方向本件照办（未实现 400、未改业务代码），但**措辞已按实测现场落定**，并已在 §6.2 与 §8 显式登记**须 captain/用户复议**。
- **提交范围**：仅白名单内本件 1 个新增件 `test-reports-2026-10/C-资产与口径订正.md`（逐条 `git add`，禁 `git add -A`/`.`，约束 ⑧）；**未 `push`**（由人工决定）。探针 `test-reports-2026-10/.tmp/t2-ge-probe/probe_ge2.py` 落在 `.gitignore:41` 覆盖的 `.tmp/` 下，为本地留档、**不入提交**。
- **真库 `app.db` 三值前后一致** ✅（§0），且由 `evidence_hash` 的 `real_db_matches_pinned = true` 与 `b17_governance_contract.py` 的收尾自检双重旁证。
