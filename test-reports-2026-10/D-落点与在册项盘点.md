# D 组落点与在册项盘点（只读侦察）

- 任务：`t1 [recon] — D 组落点侦察与在册缺陷盘点（只读，不改代码）`
- attempt_id：`fe666b56-cacd-442b-904a-4a8f8be3b1d3`
- 执行者：`recon-d`（非实现者、非验证者）
- 侦察时点：`2026-10-11 14:0x–14:2x UTC`（本件为 append-only 交付件）
- 工作区：`/root/code/MyERP`，解释器 `/opt/wage-venv/bin/python -B`
- 纪律：全程只读。**未跑 `flask db *`；未改任何代码/schema；未写 `app.db`**（开工前/收工后三值各核一次，见 §4.3）。
- 本件结论口径：一条 D 组项记 `HIT` 当且仅当 ① 载体文件在盘上存在（给路径 + 字节 + mtime/sha256）② 判据的现读值由本次实跑或本次原文直读给出。任一不成立 ⇒ 记 **`not_counted_as_passed`** 并写解除条件（硬约束④）。

---

## §1 D 组本体定位（`08-测试总方案.md:460` 所述 V-13…V-16）

### 1.0 引用源原文

`test-reports-2026-10/08-测试总方案.md:460`（该文件末次提交 `590b688`，未被本战役改动）：

```
| **V 验证目标** | V-01…V-28 | A 组 V-01…V-04（质检落地与门禁，全 P0）；B 组 V-05…V-08（返工/报废/计件）；C 组 V-09…V-11（权限矩阵）；E 组 V-12/V-17（**门禁脚本自身可信度**）；D 组 V-13…V-16（迁移/schema）；F 组 V-20…V-22/V-27（业务主链）；G 组 V-19/V-23/V-24（数据卫生与只读纪律）；H 组 V-25/V-26（文档一致性） |
```

⇒ 该行只给**分组归属**，不给判据与载体。权威判据/载体行在 `test-reports-2026-10/35-第2轮测试总方案（定稿）.md:432-436`（本次逐行实读）：

| 项 | 分工 | 载体（35- 原文） | 判据（35- 原文摘要） |
| --- | --- | --- | --- |
| V-13 | B4/B5 工具评估 | `scripts/check_properties.py`（独占）、新建 `scripts/check_doc_claims.py`、`requirements.lock` | TL-05：注入 `e.not_a_column` ⇒ exit 1，且既有期望值（23 文件/74 模型类）不得漂移；TL-06：错误数字 ⇒ 非 0、正确 ⇒ 0；TL-07：按 lock 安装后 6 项静态门禁 + `run_gates` 可跑 |
| V-14 | B5 分析师 | `evidence/regression-r2/**` | 7 锚点中无意更新者哈希不变；有意更新者留「旧值 + 新值 + 触发 ID + 命令」；`functional_test` 109/0；`uat` 40 链 pass 数不下降；`app.db` 不变 |
| V-15 | B4 自动化 | `harness/w1_p01_probe.py`、`harness/w2w3_uatdiff.py`（改钉显式提交号） | 「修复前树」不再依赖移动 `HEAD`（改钉 `2c6dbfd` 类显式提交）；负向对照恢复可复现；只改这两处，不改判据口径 |
| V-16 | B5 流程优化 | `test-reports-2026-10/6x-第2轮改进报告（定稿）.md` | 每个数字带三要素；已补/仍缺/新发现/工程化建议（含 A-63 第二步晋升条件与判据）；与第一轮 `07` 前后对照 |

> 口径说明：`08-…:460` 与 `35-…:432-436` 的归属**互不矛盾但不等价**——`35-` 把 V-13/V-15 归 B4（自动化/工具）、V-14/V-16 归 B5（分析师/流程），`08-` 把 V-13…V-16 整体挂 D 组。D 组收口应以 `35-` 的判据为准、以 `08-` 的组归属为准。

### 1.1 V-13 —— 判据面 `HIT`，证据面 `not_counted_as_passed`

**载体在盘（本次 `ls -la` 实测）**

| 路径 | 字节 | mtime |
| --- | --- | --- |
| `scripts/check_properties.py` | 28715 | `2026-10-09 22:26` |
| `scripts/check_doc_claims.py` | 45998 | `2026-10-11 13:21` |
| `requirements.lock` | 1642 | `2026-10-10 08:50` |
| `test-reports-2026-10/52-V13-TL050607-工具链收尾.md`（交付件） | 38619 | `2026-10-11 13:21:25.207630943 +0000` |

`52-…md` sha256 = `fd04fb5524ef5ac332742d551aadc603485be28cebf8c93a19803fb1febd3760`；末次提交 `1a3850f`（`git log --oneline -1 -- test-reports-2026-10/52-V13-TL050607-工具链收尾.md`）⇒ 交付件已入库，不在「未提交面」。

**现读结论（判据面）**——`52-…md` §0 验收表（本次原文直读）：TL-05 ✅ pass、TL-06 ✅ pass、TL-07 ✅ pass、A10 ✅ pass（`--selftest` 22/22 TL-05、16/16 TL-06/07）。**本次门禁链独立复现**（见 §4.2）：`ci_gates.py --phase first` ⇒ `check_properties group=blocking exit=0 checks 4/4`、`check_doc_claims group=blocking exit=0 checks 5/5`、整体 `exit 0 / steps=20`。

**证据面失效（本次实测，deviation 级）**：`52-…:84-85` 声明「证据落点（E-01）＝ `evidence/harness/r2-v13-tl050607/`（14 件…）与 `evidence/harness/ci-v13-gate/`」，`:306` 引 `evidence/harness/ci-v13-gate/ci_gates.json`、`:308` 引锚点 `evidence/harness/coverage.json`（声明 236893 B）。**本次 `ls -d` 逐条实测：`evidence/harness/r2-v13-tl050607` = MISSING、`evidence/harness/ci-v13-gate` = MISSING、`evidence/harness/ci-v13-verify` = MISSING、`evidence/harness/coverage.json` = MISSING。** 全仓 `find . -name "*r2-v13*"`（排除 `.git`）返回空；`find . -name "tl0[567]*"` 只命中 `.tmp/r2t14/` 与 `.tmp/r2t1-reconcile*/tl05probe`（scratch）。

存活件：`test-reports-2026-10/.tmp/r2t14/v13_evidence_index.json`（4918 字符，本次实读）逐件记录 14 件的 `name / title / exit_code / sha256`，例如 `tl05.inject.txt` exit_code **1** / sha256 `EB21B507CD55B12730DBA15972C8033A6EB47DAFD5C371826B14300539EE0906`、`tl06.default.txt` exit_code **1**、`n1.before.txt` exit_code **1**、`n1.after.txt` exit_code **2**、`n1.selftest.txt` exit_code **0**。注入夹具在盘：`.tmp/r2t14/inject/tl05_class`、`.tmp/r2t14/inject/tl05_instance`、`.tmp/r2t14/inject/tl05_instance_clean`。

> 触发原因（旁证，非本次直接测量）：`70-第2轮收口与阶段C移交.md:442` 记 `evidence/` = **13,209 文件 / 320,687,725 B**；本次 `find test-reports-2026-10/evidence -type f | wc -l` = **1951**、`du -sb` = **38,266,532 B`。⇒ 该 evidence 树在其后被大幅裁剪，早期 run 目录成批消失（`evidence/` 整树被 `.gitignore:42 /test-reports-2026-10/evidence/` 忽略，删除不留 git 痕迹）。

裁定：V-13 **判据面 `HIT`**（工具在册、已进 `ci_gates` blocking 链、本次全绿）；**证据面 `not_counted_as_passed`**（14 件载体 + `ci-v13-gate` 机读件在盘缺失）。解除条件：任选其一并落新 run 目录——① 重跑 TL-05/06/07 三条（`check_properties --selftest` / `--root app` / 注入 `e.not_a_column`；`check_doc_claims --selftest` / `--list-constants` / 默认域；`requirements.lock` 干净 venv 安装 + 6 门禁 + `run_gates`）② 依 `v13_evidence_index.json` 的 14 条 sha256 重建 `evidence/harness/r2-v13-tl050607/`（若原始字节已不可得则只能走 ①）。

### 1.2 V-14 —— `not_counted_as_passed`（载体目录整体缺失）

- 载体声明：`evidence/regression-r2/**`（`35-…:433`；另见 `31-第2轮实测队建队计划.md:91` inScope）。
- **本次实测：`test-reports-2026-10/evidence/regression-r2` 不存在**；`find . -maxdepth 5 -name "*regression-r2*"` 无匹配；`find test-reports-2026-10 -maxdepth 2 -type d -name "regression*"` 无匹配。
- 工具在册：`test-reports-2026-10/harness/regression_preflight.py`（6621 B，`2026-10-10 18:12`）、`harness/r2_v14_ledgerbook.py`（`OUT_DIR_REL = 'test-reports-2026-10/evidence/regression-r2'`，见 `.tmp/captain-a123-w2w3/trees/{before,after}/…/r2_v14_ledgerbook.py:35`）、`harness/t6_ledger_check.py`（12256 B，`2026-10-09 03:49`）。
- 唯一存活台账：`test-reports-2026-10/.tmp/r2-exec-b5-v14/ledger/r2-exec-b5-v14-ledger.json`（**30844 B**，mtime `2026-10-07 14:48`；同目录 `anchor_drift.json` 4505 B）。本次实读其头：`ledger_version 2.0` / `task_id t15` / `attempt_id b27da258-bd82-4fc7-b2bf-597c0f91554e` / `operator 测试结果分析师` / `2026-10-07T22:43:51+08:00 → 22:48:28` / `env.workdir "D:\workspace\wage_management_system - bak"` / `env.git_head 6e45ee7de58253465b62d6d74064da43ceda69bb` / `env.app_tree c8f7d4abca1567b6219dbd77f22c82722f877ad6` / `env.python "F:\Miniconda\envs\wage\python.exe (3.9.21)"` / `env.temp_run_root test-reports-2026-10/.tmp/r2-exec-b5-v14`。
  ⚠ **该台账的 `db_invariant.pinned_sha256` = `F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065`**（before/after 同值、`verdict 通过`）。**与当前钉值 `B4FB980C…` 不可比**——真库在 `ALLOY-IMPORT-02` 重基线后才变为现钉值（见 `ALLOY-IMPORT-02-真库锚点重基线登记.md`）。台账自洽但对今日不构成锚点证据。
- 裁定：**`not_counted_as_passed`**。解除条件：重跑 `regression_preflight.py preflight/verify` + 锚点比对，把台账落到 inScope 目录 `evidence/regression-r2/r2-exec-b5-v14-ledger.json`（或新 RUN_ID），并以 `t6_ledger_check.py <台账>` 复核（`60-第2轮改进报告（定稿）.md:558` 的复核命令）；同时把 `db_invariant` 的钉值改为当前 `B4FB980C…`（否则锚点比对口径错位）。

### 1.3 V-15 —— 判据面 `HIT`（改钉已落盘且提交号真实性已核）

载体在盘：`test-reports-2026-10/harness/w1_p01_probe.py`（**42707 B**，`2026-10-08 21:06`）、`harness/w2w3_uatdiff.py`（**57500 B**，`2026-10-08 21:06`）。

现读原文（本次 `grep -n` 实测）：

| 位置 | 原文 |
| --- | --- |
| `w1_p01_probe.py:91` | `PRE_FIX_REV = '2c6dbfd66a43aebf6733500b5579436f7e8d8da0'` |
| `w1_p01_probe.py:94` | `FIX_COMMIT_REV = 'fd5102360b3777d8ec2a0fb2610b2abbc2119df6'` |
| `w1_p01_probe.py:14` | `## ⚠ 「修复前树」必须钉**显式提交号**（A-79 / 同源 A-70）` |
| `w1_p01_probe.py:23-25` | 常量=修复前最后一个提交；`2c6dbfd == fd51023^`；可被环境变量 `WMS_PREFIX_REV` 覆盖，**默认值永远是显式提交号** |
| `w2w3_uatdiff.py:179` / `:181` | 同值 `PRE_FIX_REV` / `FIX_COMMIT_REV` |
| `w2w3_uatdiff.py:374` | 解析优先级 `--pre-fix-rev` > `WMS_PREFIX_REV` > 常量 |
| `w2w3_uatdiff.py:390` | 从**钉死的显式提交**取文件字节（A-70：绝不 `HEAD:`） |
| `w2w3_uatdiff.py:123` | 负向对照 `RE-2`：`--pre-fix-rev HEAD` ⇒ 回退失效、`R_now=[]` ⇒ **如实转红** |

提交号真实性（本次只读核对）：`git cat-file -t 2c6dbfd66a43aebf6733500b5579436f7e8d8da0` = `commit`；`git rev-parse fd5102360b3777d8ec2a0fb2610b2abbc2119df6^` = `2c6dbfd66a43aebf6733500b5579436f7e8d8da0`；`git log --oneline -1 2c6dbfd` = `feat(tl-01): 新增 check_model_refs 门禁，防 P-01 类 NameError 复发` ⇒ 钉值**非悬空常量**，`fd51023^ == 2c6dbfd` 成立。

裁定：**判据面 `HIT`**（「改钉显式提交号」已落盘、只改这两处、常量有效）。**运行面 `not_measured`**（本任务只读侦察，未做「两脚本双跑 + 与 `functional_test` 一致性」；该项属 V-15 的验证者范围，不折算 pass）。

### 1.4 V-16 —— 载体 `HIT`（内容可信度未抽检）

- 载体在盘且入库：`test-reports-2026-10/60-第2轮改进报告（定稿）.md`（**67735 B**，`2026-10-07 16:26`；末次提交 `ec64676`，msg = `docs(r2): A-121 处置遗留#3(60- 作废值加撤回标记 => check_doc_claims exit 0) + 追加快照边界指针行 + 遗留#1基于原则拒绝重跑preflight(以精确归因结案)`）。
- 复核工具在册：`harness/t6_ledger_check.py`（12256 B，`2026-10-09 03:49`）。
- 旁证：F-V13-6（`52-…:337` 记录 `60-…md:274` 的作废口径值 `≥135` 曾使 `check_doc_claims` 默认域 exit 1）**已由 `ec64676` 处置**；本次 `ci_gates` 实测 `check_doc_claims group=blocking exit=0 checks 5/5` ⇒ 该活违规已闭。
- 裁定：**载体 `HIT`**；「每个数字带三要素」与「A-63 第二步晋升条件」的逐条内容未抽检 ⇒ 该项记 `not_measured`，解除条件 = 数字可复算抽查（`t6_ledger_check.py` + 抽 3 条数字回算）。

### 1.5 G-15（TL-05/06/07，V-13）当前状态裁决 —— `70-` 文件内部自相矛盾，**以收口结论为准 = 已收口**

`test-reports-2026-10/70-第2轮收口与阶段C移交.md`（657 行）**同一文件内同时记录「未收口」与「已收口」**，逐条给原文与行号：

**（甲）未收口面（§9 台账原样，未被刷新）**

- `70-…:469`（§9.2 G-15 行）原文：`| **G-15** | **TL-05/06/07 终态未收口** | `in_progress` | t14 `in_progress`；盘上产物 mtime 22:32–22:50；**注入面（`e.not_a_column` ⇒ exit 1 / `≥135` ⇒ 非 0 / 删 lock ⇒ 非 0）未实测** | V-13 续跑 / 阶段C |`
- `70-…:451`（§9.1 G-2 行）`in_progress`（「本体未收口」）。
- `70-…:534`（§10.7 §10.7 未收口任务接续）列 V-13 续跑，判据 =「三条注入各有一次实测 + `--selftest` exit 0」。
- `70-…:647`（§13 结论）「目标②**部分完成**：回归复验 6/6 `HIT`；TL-05/06/07 在途」。

**（乙）已收口面（`70-…:418-442`，captain 追加的 §8.5「收口后刷新」，行号在后）**

`70-…:420` 原文含：「**V-13 / V-15 均已 `completed`**，且 captain 随后把全部终态成果**分 4 批提交**（含 `t19`/`t20`/`t21` 三个后续修复）」；刷新读数（HEAD=`ec64676`）：生产面 0 / 提交面（`7e0a995..HEAD`）**66** / 工作区未提交面 **2** / 并集 **68 文件 / 2,786,534 B**；rollback 种类 `git-checkout-from-BASE 12 / delete-untracked 2 / delete-committed-new 54`（`git-checkout-worktree` 归零）；只读推演 **68/68 全绿 `anomaly=0`**；剩余工作区仅 2 个 `??`：`docs/交接提示词-批次3开工-2026-10-06.md`、`docs/开发与测试规划-2026-10-06.md`。

**（丙）本次独立判据（外部实证，不依赖 `70-` 自述）**

1. `52-V13-…md` §0 三条验收 ✅ + A10 ✅，且该件已由 `1a3850f` 入库（`git log` 实证）。
2. 本次实跑 `ci_gates.py --phase first`（`2026-10-11 14:24:04 UTC`）⇒ **`exit 0` / `steps=20` / blocking 失败=无 / report-only 失败=无 / 注入未生效=无**，两条 TL 门禁步 `check_properties exit=0 checks 4/4`、`check_doc_claims exit=0 checks 5/5`。
3. G-15 行自述「注入面未实测」所指的注入夹具（`.tmp/r2t14/inject/tl05_instance` 等）在盘，但**其输出件载体已缺失**（§1.1）。

**裁决**：G-15 的**判据面已收口**（V-13 三条 TL + A10 有验收台账且已入库；门禁链在 2026-10-11 独立复现全绿）⇒ **G-15 不应再记 `in_progress`**；但 `70-…` §9.1/§9.2/§13 **未随 §8.5 刷新**（文件内矛盾）且 §1.1 的 14 件证据载体缺失 ⇒ 建议：① 由本轮收口在 `70-` 追加（不删原文）一条「G-15 → `completed`，判据 = `52-` §0 + `1a3850f` + 2026-10-11 `ci_gates` 复现，证据面缺口见 N-D1」；② **不得**用 `70-` §8.5 的自述替代证据（其自身钉的 `app.db` 已过期，见 §1.6）。

### 1.6 `70-` 文件内两处已过期钉值（引用时须带时点）

| 位置 | `70-` 所钉 | 现读 | 差异 |
| --- | --- | --- | --- |
| `70-…:439` | `app.db` = `F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065` / 2531328 B / mtime `2026-09-18 12:50:55` | `b4fb980c5d1b25b3c3a0eadc12ecf01c75b36ebd213b109e5dd190c617eeaabe` / 2531328 B / `2026-10-09 03:39:39.418764055 +0000` | **真库已重基线**（ALLOY-IMPORT-02），字节数相同、哈希与 mtime 不同 |
| `70-…:442` | `evidence/` = 13,209 文件 / 320,687,725 B；`.tmp/` = 27,883 文件 / 2,912,971,276 B | `evidence/` = **1951 文件 / 38,266,532 B** | evidence 树被大幅裁剪（§1.1 载体消失的直接原因） |

同类过期钉值亦见 `52-…md` §0 纪律段（钉 `F5DA2306…`）与 `.tmp/r2-exec-b5-v14/ledger/r2-exec-b5-v14-ledger.json` 的 `db_invariant.pinned_sha256`（同上）。**本轮 D 组任何引用都必须改用 `B4FB980C…`。**

### 1.7 `70-` §13.6/§13.7 与 D 组的关系（在册项，非新增缺陷）

- `70-…:652`（§13.6）：**P1（审计 `target_id` 落库 NULL）+ P10（取价口径两处不一致）** 列为数据可信度级，阶段C 优先于覆盖扩张。⇒ P10 正是本任务 §3 / 团队线③ 的 N-5 同族；P1 对应 `B18-登记.md` N-1（B13-02 未执行写入）。
- `70-…:653`（§13.7）：构建层仍 `blocked`（P-3 = 0 轮真实 CI，A-63 第二步，`not_counted_as_passed=true`）。本次 `ci_gates` 输出亦自带 `gaps: A-63-STEP2-BUILD-GATE = blocked（不计入通过数）` ⇒ **仍为 blocked，未折算 pass**。

---

## §2 枚举中文化落点清单

### 2.1 五个点名点：现读原文 + 行号 + 覆盖率（worktree @ `1a3850fd`)

| # | 落点 | 现读原文（逐字） | 该点的可达取值集合 | 中文覆盖 |
| --- | --- | --- | --- | --- |
| 1 | `app/templates/main/purchase/order_detail.html:29` | `<li>{{ r.receipt_no }} {{ r.status }}` | GoodsReceipt 6 值（2.2 a1） | **0/6 裸英文** |
| 2 | `app/templates/main/purchase/requisitions.html:21` | `<td>{{ r.status }}</td>` | PurchaseRequisition 5 值（2.2 a2） | **0/5 裸英文** |
| 3 | `app/templates/main/search/global_search.html:357` | `{% else %}{{ order.status }}{% endif %}`（SalesOrder 块 else 兜底） | SalesOrder 5 值（2.2 a3） | **5/5 已中文**（`:352-357` 五分支全覆盖；仅越界值走 else） |
| 4 | `app/templates/main/search/global_search.html:405` | `{% else %}{{ order.status }}{% endif %}`（ProductionOrder 块 else 兜底） | ProductionOrder 4 值（2.2 a4） | **4/4 已中文**（`:400-405` 四分支全覆盖；仅越界值走 else） |
| 5 | `app/templates/main/quality/tasks.html:378-385` | `:378 function getStatusName(status) {` / `:379 const statuses = {` / `:380 'pending': '待处理',` / `:381 'in_progress': '进行中',` / `:382 'completed': '已完成',` / `:383 'failed': '不合格'` / `:384 };` / `:385 return statuses[status] \|\| status;` | InspectionTask 4 声明值（2.2 a5） | **3/4**（缺 `cancelled`；多出未声明的 `failed`） |

`grep -c cancelled app/templates/main/quality/tasks.html` = **0**（退出码 1，本次实测）。

**同族兄弟点（任务未点名、但属同一「英文枚举直出」缺陷族，供一处决策时一并裁）**

| 位置 | 现读原文 | 说明 |
| --- | --- | --- |
| `app/templates/main/purchase/order_detail.html:5` | `<h2>采购单 {{ po.po_no }} <span class="badge bg-secondary">{{ po.status }}</span></h2>` | PurchaseOrder.status 裸英文 |
| `app/templates/main/purchase/orders.html:42` | `<td>{{ po.status }}</td>` | PurchaseOrder.status 裸英文（**另一模板文件**） |
| `app/templates/main/quality/tasks.html:33-39` | `:34 全部状态` / `:35 <option value="pending">待处理</option>` / `:36 in_progress 进行中` / `:37 completed 已完成` / `:38 failed 不合格` | 与 `getStatusName` **同一 4 键缺陷**，同文件第二落点（筛选下拉） |
| `app/templates/main/quality/tasks.html:28-32` | 类型下拉只列 4 类（production_record/product/material/goods_receipt） | 对照 `task_detail.html:9-11` 有 6 类（多 workpiece/heat_lot） |

`grep -rn "{{ *[a-z_]*\.status *}}" app/templates/main/purchase app/templates/main/search` 的**全部 6 命中**即上表 1/2 + 兄弟 1/2 与 global_search 的 `:357`/`:405`（无遗漏）。

### 2.2 四处各自的可达取值集合（含后端赋值点 `file:line`）

**a1. GoodsReceipt.status = 6 值** —— 模型默认 `'pending_inspection'`（`app/models.py:3161`）；写入点：`app/main/purchase.py:367`（pending_inspection）、`:369`（accepted）、`app/main/quality.py:1034`（accepted）、`app/services/mes_service.py:988`（putaway）、`:1003`（accepted）、`:1021`（rejected）、`:1131`（accepted）、`:1136`（returned）、`:1141`（scrapped）。
⇒ 模板 `order_detail.html:29` 的渲染点仅硬编码覆盖 `accepted`（`:31`）与 `rejected`（`:36`）；`pending_inspection / returned / scrapped / putaway` 四值**必然裸英文漏出**。

**a2. PurchaseRequisition.status = 5 值** —— 模型默认 **`'draft'`**（`app/models.py:3088`：`status = db.Column(db.String(20), default='draft', index=True)`）；写入点：`app/main/purchase.py:150`（`status='pending'`）、`:177`（`'approved' if request.form.get('decision') != 'reject' else 'rejected'`）、`:254`（converted）、`:332`（converted）。
⚠ **同名不混用**：`app/main/routes.py:12227` 的 `requisition.status = 'cancelled'` 属 **MaterialRequisition**（同函数 `:12223` `from app.models import MaterialRequisition`，端点 `cancel_material_requisition`），**不是** PurchaseRequisition。
⇒ `requisitions.html:21` 仅覆盖 pending（`:24`）与 approved/converted（`:31`）；**`draft`、`rejected` 会裸英文漏出**。

**a3. SalesOrder.status = 5 值** —— 声明注释 `app/models.py:1783`：`# 状态: pending(待处理), confirmed(已确认), in_production(生产中), completed(已完成), cancelled(已取消)`；表单 `app/main/forms.py:277-283` 同 5 值同中文；写入点：`app/main/routes.py:8849`（`order.status = form.status.data`，表单驱动可取 5 值任一）、`app/main/shipping.py:204-205`（confirmed→in_production）、`:203`（→completed）、`app/main/routes.py:9089`（→in_production）；只读守卫 `app/main/shipping.py:67`（`if order.status == 'cancelled':`）。
⇒ `global_search.html:352-357` **5/5 已中文**，无缺口。

**a4. ProductionOrder.status = 4 值** —— 声明注释 `app/models.py:1300`（`# pending, in_progress, completed, cancelled`）；表单 `app/main/forms.py:324-327`（pending 待开始 / in_progress 进行中 / completed 已完成 / cancelled 已取消）；写入点：`app/main/routes.py:8849`（表单驱动）、`:9708`（completed）、`:9712`（in_progress）、`:9716`（pending）；守卫 `:8769`（`if order.status not in ['pending', 'cancelled']:`）、`:9136`、`:10328`（`ProductionOrder.status != 'cancelled'`）。
⇒ `global_search.html:400-405` **4/4 已中文**，无缺口。

**a5. InspectionTask.status = 4 声明值（含 `cancelled`），但唯一缺口是「无写入者」** —— 声明 `app/models.py:958`：`status = db.Column(db.String(20), nullable=False, default='pending', comment='任务状态(pending/in_progress/completed/cancelled)', index=True)`；写入点：默认 `pending`（同上）、`app/services/mes_service.py:138`（创建 `status='pending'`）、`app/main/quality.py:1793`（创建 `status='pending'`）、`app/main/routes.py:3675`（创建 InspectionTask）、`app/main/quality.py:881`（`task.status = 'in_progress'`）、`app/main/quality.py:1003`（`task.status = 'completed'`，`:1004` `completed_at=datetime.now()`）。
本次实测：**全仓无任何代码把 `InspectionTask.status` 写成 `'cancelled'`**；`grep -c failed app/main/quality.py` = **0**，且 `failed` 不在模型声明里。
另：`app/main/quality.py:1139-1200` `update_task` **不处理 status 字段**（只依次处理 template_id/inspector_id/target_id/target_type/priority/deadline/notes，**无 `if 'status' in data`**）；删除守卫 `app/main/quality.py:1083`（`if task.status in ['in_progress', 'completed']:`）。
⇒ 结论（load-bearing，供一处决策）：`getStatusName` 的缺口是**双向错配**——缺的 `cancelled` 是**声明值但无写入者**（防御性映射），多出的 `failed` 是**非声明值且无写入者**（无来源的死键）。`cancelled` 的现成中文名已在两处存在：`app/main/quality.py:851` `'cancelled': '已取消'`、`app/templates/main/quality/task_detail.html:13` 同名键。

**真库现存量分布（`sqlite3 file:app.db?mode=ro`，只读）**：`goods_receipts` 0 行（无分布）；`purchase_requisitions` 0 行；`sales_orders` 4 行 = pending 4；`production_orders` 11 行 = pending 7 / in_progress 3 / completed 1；`inspection_tasks` 1 行 = pending 1。
⇒ 真库**无法**为 a1/a2/a5 的漏出提供现网样本；判据只能用合成夹具或对模板分支做静态穷举（同 §3 的退化性教训）。

### 2.3 (b) 仓库内已有的中文映射表（可复用范本，逐张给键集与坐标）

| # | 位置 | 变量名 | 键集 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | `app/main/quality.py:1581-1588` | `_TASK_TYPE_NAMES` | 6 键 `product/production_record/material/goods_receipt/workpiece/heat_lot` | 消费点 `app/main/quality.py:1603`（导出行 `'检验类型'`）；`:1589` `_VALID_TASK_TYPES`（仅 4 键） |
| 2 | `app/main/quality.py:846-852` | 内联 `status_names` | 4 键 `pending/in_progress/completed/cancelled` | guard 在 `:846`、表体 `:847-852`、`'cancelled': '已取消'` 在 **`:851`**、消费点 `:853`；**与 `models.py:958` 声明枚举逐字一致，是 InspectionTask 的现成范本** |
| 3 | `app/templates/main/quality/task_detail.html:9-11` | `{% set TASK_TYPE_LABELS %}` | 6 键（同 #1） | Jinja 侧范本 |
| 4 | `app/templates/main/quality/task_detail.html:12-13` | `{% set TASK_STATUS_LABELS %}` | **5 键 = pending 待处理 / in_progress 进行中 / completed 已完成 / failed 不合格 / cancelled 已取消** | 含 `cancelled`；`:57` 用 `.get(task.status, task.status)` ⇒ cancelled 已落中文（走 `:48-56` if/elif 的 else） |
| 5 | `app/templates/main/quality/task_detail.html:14` | `{% set RESULT_LABELS %}` | `pass` 合格 / `fail` 不合格 | — |
| 6 | `app/services/mes_service.py:924` | `INCOMING_NC_LABELS` | `return/accept/scrap` | **处置动作**中文，非到货单状态 |
| 7 | `app/main/routes.py:5873-5878` | `SYSTEM_CONFIG_CATEGORY_LABELS` | `purchase/quality/material/general` | 配置分类，与状态无关 |
| 8 | `app/main/routes.py:11200-11205` | `status_labels` | 4 键 `pending/in_progress/completed/cancelled` | TaskAssignment 图表（`:11204` cancelled） |
| 9 | `app/main/routes.py:9640-9644` | `status_text` | `in_progress/completed/cancelled` | ProductionBatch 响应文案 |
| 10 | `app/main/forms.py:148-154` | `TaskSearchForm.status` choices | `('',全部)`/pending 未完成/in_progress 进行中/completed 已完成/cancelled 已取消 | 编号最全的现成名表源之一 |
| 11 | `app/main/forms.py:197-199` | `ExportTaskForm` | pending 待处理/in_progress 进行中/completed 已完成/cancelled 已取消 | — |
| 12 | `app/main/forms.py:277-283` | `SalesOrderForm.status` | 5 键（同 a3） | a3 的可复用范本 |
| 13 | `app/main/forms.py:324-327` | `ProductionOrderForm.status` | 4 键（同 a4） | a4 的可复用范本 |
| 14 | `app/main/forms.py:482-489` / `:491-497` | 搜索表单 order_status / production_status | 同 #12 / #13，另含 `('',全部)` | — |
| 15 | `app/main/forms.py:858-864` | `InventoryCountSearchForm` | planning 计划中/counting 盘点中/completed 已完成/cancelled 已取消 | — |
| 16 | `app/templates/main/production_batch_detail.html:487` / `:523` | 批次动作文案 | `'completed': '完成批次'` / `'completed': '完成'` | 动作文案，非状态表 |
| — | `app/utils/alloy_steel_price_converter.py:36`、`alloy_steel_bom_converter.py:63` | `ROMAN_MAP` | — | 无关 |

**既存决策先例（load-bearing，一处决策必须交代）**：`app/templates/main/quality/task_detail.html:218-220` 原文
`{# B18-C-02/t9：来料检的检验对象是到货单（B14-07 方案 A）。到货单号与打印页 get_inspection_target_name（app/main/quality.py）同一数据源；不渲染 receipt.status（英文枚举，purchase 模板亦无现成中文映射，不新造表）。 #}`
⇒ 该先例的裁决是「**英文枚举不渲染、且不新造表**」。本轮若给 `order_detail.html:29` / `requisitions.html:21` 补中文，属**推翻该先例**（或需说明为何此处不同），一处决策必须显式裁决这一冲突；且 §2.4 证明「purchase 模板亦无现成中文映射」这句**现在仍成立**（只有整句原因，没有短标签表）。

### 2.4 (c) `app/main/purchase.py:33-36` 是否已有到货单状态中文口径可复用 —— **答：无可用短标签表**

逐行实测：

| 行 | 原文 |
| --- | --- |
| `:33` | 注释（到货单可入库的状态口径） |
| `:34` | `_PUTAWAY_ALLOWED_STATUSES = ('accepted',)` |
| `:35` | `_PUTAWAY_BLOCK_REASONS = {` |
| `:36-39` | 四键 `'pending_inspection'` / `'rejected'` / `'returned'` / `'scrapped'`，**值是整句话**（如 `:38` `'returned': '到货单已退货，不能入库',`、`:39` `'scrapped': '到货单已报废，不能入库',`） |
| `:40` | `}` |

结论：该表是「**不可入库原因**」整句口径，覆盖 6 值中的 4 值（缺 `accepted`/`putaway`），**不是**可直接复用为 badge 短标签的到货单状态中文表。`app/main/quality.py:846-852` 的 4 键 `status_names` 也不适用于 GoodsReceipt（键集不同）。

---

## §3 N-5 取价复算的可执行口径

### 3.1 真实表名与列（实测）

- **真表名 = `process_price`（单数）**；**不存在 `process_prices`**（本次对真库直接查表的实测结论）。伴生表 `process_price_group`。
- 模型：`class ProcessPrice(db.Model)`，`app/models.py:67-88`，含 `__table_args__ = (db.UniqueConstraint('global_sn', name='uq_process_price_global_sn'),)`；伴生 `class ProcessPriceGroup` 起于 `app/models.py:102`。
- `PRAGMA table_info(process_price)`（本次实测列清单，17 列）：`id` INTEGER PK · `global_sn` VARCHAR(8) NOT NULL · `process_code` VARCHAR(50) NOT NULL · `process_name` VARCHAR(100) NOT NULL · `component` VARCHAR(100) · `drawing_no` VARCHAR(100) · `model_no` VARCHAR(100) · `price` FLOAT NOT NULL · `version` INTEGER NOT NULL · `effective_date` DATETIME · `is_current` BOOLEAN · `notes` TEXT · `price_type` VARCHAR(20) NOT NULL · `has_output` BOOLEAN · `output_type` VARCHAR(20) · `code_rule_id` INTEGER · `needs_inspection` BOOLEAN。

### 3.2 真库读数（`sqlite3 file:app.db?mode=ro`，本次实测；开工前后 `app.db` 三值一致）

| 量 | 值 |
| --- | --- |
| `count(*)` | **3486** |
| `count(distinct process_code)` | **3486** |
| 多版本码数（`count(*) > 1` 的 code） | **0** |
| `effective_date` NULL 或空串 | **0** |
| `min(effective_date)` / `max(effective_date)` | `2025-07-01 00:00:00.000000` / `2025-07-01 00:00:00.000000`（全表同日） |
| `is_current` distinct | **{1}**（3486 行全 1） |
| `version` distinct | **{1}** |
| `price_type` 分布 | `normal` 2918 / `subtotal` 568 |
| `effective_date > 2026-10-12 23:59:59.999999` 行数 | **0** |
| `effective_date > 2026-10-13 23:59:59.999999` 行数 | **0** |
| `effective_date like '0000%'` | 0（未来价样本查询返回空集） |

### 3.3 两个口径的原文

**新口径（唯一定义）**：`app/main/routes.py:157` `def pick_process_price(process_code, business_date):`；docstring `:158-179`；分支 `:180-192`（None ⇒ None；datetime ⇒ `.date()`；date ⇒ 原样；str ⇒ `_coerce_excel_date(value, '业务日期')`（def `app/main/routes.py:135`），err/None ⇒ None；其他类型 ⇒ None）；核心 `:193-197`：

```
:193    end_of_day = datetime.combine(day, datetime.max.time())
:194    return ProcessPrice.query.filter(
:195        ProcessPrice.process_code == process_code,
:196        ProcessPrice.effective_date <= end_of_day + timedelta(days=1)
:197    ).order_by(ProcessPrice.effective_date.desc()).first()
```

docstring 自述与旧口径的两点差异：① 排除 `effective_date` 晚于业务日 +1 天的行（不把未生效未来价当现价）；② 多版本时按 `effective_date` 降序取最新；无生效版本返回 None。`+ timedelta(days=1)` 是仓库既有约定（docstring 引 `routes.py:765/800/1169/3126`、`quality.py:706`），用于吸收「`effective_date` 被写成 datetime 且落在业务日之后」的边界。

**旧口径（被 `1a3850f` 删除，`git show 1a3850f -- app/utils/excel_generator.py` 实证）**：

```
-                    process = ProcessPrice.query.filter_by(process_code=process_code, is_current=True).first()
+                    from app.main.routes import pick_process_price
+                    process = pick_process_price(process_code, datetime.now().date())
```

即旧口径 = `ProcessPrice.query.filter_by(process_code=process_code, is_current=True).first()`（**`is_current` 优先、无日期维度、无 order_by**）。新调用点注释（同 diff）：`# 查找工序：取价单点统一（B18-C §1.3 裁决）——复用 routes.pick_process_price 的唯一口径（effective_date<=业务日+1d，降序取最新），不再另留 is_current`。

**四个调用点**（`grep -rn 'pick_process_price' app/`）：`app/main/routes.py:2960`（生产记录导入，业务日 `business_date`；`:2959` 注释 `# 查找工序价格（B12-01 取价单点：唯一口径见模块级 pick_process_price）`）、`:4174`（`bonus_date`）、`:4294`（`target_date`）、`app/utils/excel_generator.py:902`（`datetime.now().date()`，函数内延迟导入于 `:901`）。

### 3.4 一次算出「旧口径 ↔ 新口径逐码同 id」的口径（不实现，只给口径与预期读数）

**逐码比对 SQL（单条即可，两口径各一 CTE 后 outer join）**：

```sql
WITH codes AS (SELECT DISTINCT process_code FROM process_price),
old_c AS (
  SELECT c.process_code,
         (SELECT p.id FROM process_price p
           WHERE p.process_code = c.process_code AND p.is_current = 1
           ORDER BY p.id LIMIT 1) AS old_id          -- 复刻 filter_by(...).first()：无 ORDER BY ⇒ 行序取首行
  FROM codes c),
new_c AS (
  SELECT c.process_code,
         (SELECT p.id FROM process_price p
           WHERE p.process_code = c.process_code
             AND p.effective_date <= datetime(:business_date, '+1 day', '+23 hours', '+59 minutes', '+59 seconds')
           ORDER BY p.effective_date DESC LIMIT 1) AS new_id
  FROM codes c)
SELECT count(*) AS compared,
       sum(CASE WHEN old_c.old_id IS new_c.new_id THEN 1 ELSE 0 END) AS same,
       sum(CASE WHEN old_c.old_id IS NOT new_c.new_id THEN 1 ELSE 0 END) AS mismatch
FROM old_c JOIN new_c USING (process_code);
```

- 业务日取 `:business_date = '2026-10-11'`（或 `2025-07-02`，两者对当前库等价，见下）。
- **预期读数（本次真库读数推得，不是实测）**：`compared = 3486`、`same = 3486`、`mismatch = 0`。
- **判别力声明（硬约束⑥/④）**：因 `min=max(effective_date)`、多版本码 = 0、`is_current` 全 1，**该 SQL 在真库上恒等地返回 `mismatch = 0`——它证明「真库当前状态下两口径不分歧」，但不构成对「多版本取最新」「未来价不取值」两条差异的判别证据**（每条 code 只有 1 行 ⇒ 两口径按构造命中同一行）。写进结论时必须标为 `not_counted_as_passed` + 解除条件（下条）。
- **真正有判别力的口径 = 合成夹具（`B18-登记.md:480-496` P10② 先例，本次实读）**：同码同业务日三口径一致 ⇒ id 3488；同码双版本（v1 已生效 / v2 生效日之后）⇒ 新口径取**最新有效** = 3489；仅未来价 ⇒ 新口径 **None** vs 旧口径 3490；**阴性对照** = 同一 SQL 改 `order_by(effective_date.asc())` ⇒ 得 3488 ≠ 3489 ⇒ **必须转红**（不转红即说明夹具无判别力）。解除条件 = 夹具跑通且阴性对照转红，并把 `compared/same/mismatch` 与夹具四场景读数一并落台账。

---

## §4 开工基线

### 4.1 版本与工作区

- `git rev-parse HEAD` = **`1a3850fd767a39c8b89717e98ae2ac83e2587e62`**（msg：`fix(batch18-c): 阶段C 产品面收口（导入容错/报工事务、取价单点、审计回滚、质检中文化）`），分支 `main`。
- `git status --porcelain`（本次实测，6 行逐字）：

```
 M "test-reports-2026-10/B18-登记.md"
?? .tmp/
?? .vscode/settings.json
?? app.db.evidence-ALLOY-IMPORT-02-20261009_004539
?? instance/
?? test-reports-2026-10/subagent-routing.md
```

⇒ ① `B18-登记.md` 处于**已修改未提交**态，本件引用其行号属 **worktree 态**（非 HEAD 态）；② `.tmp/`、`.vscode/`、`instance/`、`app.db.evidence-ALLOY-IMPORT-02-20261009_004539` 四者**不被 `.gitignore` 覆盖**（硬约束⑧），提交必须逐条白名单；③ `test-reports-2026-10/subagent-routing.md` 亦为未跟踪新增。

### 4.2 门禁链

- `test-reports-2026-10/harness/ci_gates.py` sha256 = **`28f885798bc7fc2d29095863ceb8bd17423ccd88530102e6d08152c8fe577242`**（本次运行前实测）。
- 命令：`/opt/wage-venv/bin/python -B test-reports-2026-10/harness/ci_gates.py --phase first`（`2026-10-11 14:24:04 UTC` 起跑；运行锁获取 pid=13306）。
- **读数**：`steps=20`（blocking 16 / report-only 4）、**blocking 失败 = 无**、**report-only 失败 = 无**、**注入未生效 = 无**、`仓库根两 JSON 未被触碰 = True（A-11）`、`gaps: A-63-STEP2-BUILD-GATE = blocked（不计入通过数）`、**`exit = 0`**。
- 逐步（本次 stdout 逐字摘要）：blocking = `check_templates 5/5` / `check_migration_heads 4/4` / `check_table_parity 2/2` / `check_properties 4/4` / `check_db_bootstrap 4/4` / `run_gates 4/4`（`exit=1`，`env-probe route_inventory_native_probe: native_exit=0 expected=1 verdict=unexpected`，A-62 环境依赖探针、**不计判据**）/ `functional_test 2/2` / `permission_matrix 3/3` / `coverage_drift 2/2` / `check_notification_triggers 5/5` / `check_model_refs 5/5` / `check_http_contract 4/4` / `chain_count_consistency 8/8` / `negative_matrix 5/5` / `check_is_archived_policy 3/3` / `check_doc_claims 5/5`；report-only = `smoke_test 3/3` / `route_inventory 3/3` / `measure_coverage 1/1` / `evidence_hash 4/4`。
- 原始输出落盘：`test-reports-2026-10/evidence/harness/ci-run-20261011-142404/ci_gates_first.console.txt`。
- 对照：`AGENTS.md` 记「post-push 四冻结项 = `exit 0` / `steps=20` / blocking 失败=无 / report-only 失败=无」，本次**逐项一致**（差异仅在 `run_gates` 的 env-probe 打点为 `unexpected`，属 A-62 已登记的环境依赖项，不入判据）。

### 4.3 `app.db` 三值（开工前 / 收工后各一次，完全一致）

| 时点 | sha256 | 字节 | mtime |
| --- | --- | --- | --- |
| 开工前 | `b4fb980c5d1b25b3c3a0eadc12ecf01c75b36ebd213b109e5dd190c617eeaabe` | 2531328 | `2026-10-09 03:39:39.418764055 +0000` |
| 收工后 | `b4fb980c5d1b25b3c3a0eadc12ecf01c75b36ebd213b109e5dd190c617eeaabe` | 2531328 | `2026-10-09 03:39:39.418764055 +0000` |

与团队硬约束②的钉值逐字一致（仅大小写书写差异）。⇒ 本次侦察**零写入**。

---

## §5 结论与移交建议

### 5.1 §1 汇总（D 组四项现读状态）

| 项 | 载体现读 | 判据面 | 总裁定 |
| --- | --- | --- | --- |
| **V-13** | `scripts/check_properties.py`（28715 B）/ `scripts/check_doc_claims.py`（45998 B）/ `requirements.lock`（1642 B）/ `52-…md`（38619 B，`1a3850f` 入库）**均在**；`52-` 声明的 14 件证据载体 + `ci-v13-gate` + `coverage.json` **均缺失** | 三条 TL + A10 ✅（`52-` §0）；本次 `ci_gates` 两条门禁步 blocking 全绿 ⇒ **`HIT`** | **证据面 `not_counted_as_passed`**（N-D1） |
| **V-14** | `evidence/regression-r2/**` **不存在**；存活台账仅在 `.tmp/r2-exec-b5-v14/ledger/`（30844 B，2026-10-07，钉旧锚点 `F5DA2306…`） | 本次未重跑 `regression_preflight.py` ⇒ `not_measured` | **`not_counted_as_passed`**（N-D2） |
| **V-15** | `harness/w1_p01_probe.py`（42707 B）/ `harness/w2w3_uatdiff.py`（57500 B）均在，显式钉 `2c6dbfd6…`（w1 `:91` / w2w3 `:179`）且提交号真实性已核 | 改钉判据 **`HIT`**；「双跑 + 与 `functional_test` 一致性」`not_measured` | **判据面 `HIT` / 运行面 `not_measured`** |
| **V-16** | `60-第2轮改进报告（定稿）.md`（67735 B，末次 `ec64676`）在盘入库；`harness/t6_ledger_check.py`（12256 B）在册 | 载体 `HIT`；「数字三要素」逐条 `not_measured` | **载体 `HIT` / 内容抽检 `not_measured`** |

**G-15 裁决**：判据面已收口（`52-` §0 + `1a3850f` 入库 + 2026-10-11 `ci_gates` 独立复现全绿），`70-…:469` 的 `in_progress` 已被同文件 `§8.5`（`:418-442`）的 `completed` 取代但**未回写 §9**⇒ 文件内自相矛盾；建议本轮在 `70-` **追加**（不删原文）一条 G-15 → `completed` + 判据引用 + 证据缺口指针，并同步 §10.7/§13。

### 5.2 本轮新增在册项（`not_counted_as_passed`，各带解除条件）

- **N-D1｜V-13 证据载体缺失**：`evidence/harness/r2-v13-tl050607/`（14 件）、`evidence/harness/ci-v13-gate/ci_gates.json`、锚点 `evidence/harness/coverage.json` 三者现均不存在（`evidence/` 由 13,209 文件裁至 1,951 文件）。解除条件：重跑 TL-05/06/07 三件（或按 `.tmp/r2t14/v13_evidence_index.json` 的 14 条 sha256 重建）并落**新** run 目录；重建不可能时只能重跑。
- **N-D2｜V-14 台账不在 inScope 目录**：载体目录 `evidence/regression-r2/` 不存在，唯一台账落在 `.tmp/r2-exec-b5-v14/ledger/`，且其 `db_invariant.pinned_sha256` 仍是 `F5DA2306…`（ALLOY-IMPORT-02 之前的旧锚点）。解除条件：重跑 `regression_preflight.py preflight/verify` + 换新锚点 + 台账落 `evidence/regression-r2/<RUN_ID>-ledger.json` + `t6_ledger_check.py` 复核。
- **N-D3｜N-5 真库比对退化（本任务 §3 结论）**：真库 `compared=3486 / mismatch=0` 为**恒真读数**（每码 1 行、`is_current` 全 1、`version` 全 1、`effective_date` 全同且非未来）⇒ **不得**当作「两口径等价」的判别证据。解除条件：按 §3.4 合成夹具跑出四场景（同 id / 双版本取最新 / 未来价 None / `asc()` 阴性对照转红）。
- **N-D4｜`70-` 文件内矛盾与过期钉值**：`70-…:439`（真库）与 `:442`（evidence 计数）均为过期值；§9 台账与 §8.5 刷新结论互斥。解除条件：本轮追加刷新条目（不删原文）+ 后续任何引用强制带时点。

### 5.3 对三条实现线的直接输入

- **线①（枚举中文化）**：真实落点是 **2 处裸英文模板**（`order_detail.html:29`、`requisitions.html:21`）+ **1 处映射缺键**（`tasks.html:378-385` 缺 `cancelled`）**+ 1 处同文件同族缺陷**（`tasks.html:33-39` 筛选下拉）+ **2 处兄弟裸英文**（`order_detail.html:5`、`orders.html:42`）；而 `global_search.html:357`/`:405` **无缺口**（5/5、4/4 已中文），不应计入修复面。一处决策必须裁决：与 `task_detail.html:218-220` 的既存先例「英文枚举不渲染、不新造表」是否冲突、以及是否复用 `app/main/quality.py:846-852`（4 键范本）/`task_detail.html:12-13`（5 键范本）而非新造第 N 张表（§2.3 已列 16 条现成映射，其中状态类 10 条）。
- **线③（N-5）**：口径与真表名以本件 §3 为准（`process_price` 单数）；真库读数**充分但判别力为零**，判据必须落在合成夹具 + 阴性对照上。
