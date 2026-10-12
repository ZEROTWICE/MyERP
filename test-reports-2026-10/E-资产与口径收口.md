# E-资产与口径收口（t18）

- **任务**：`t18` — 阶段C 在册项收口（一）：资产与口径面 O5 / O8 / B18-08④⑤ / `delivery_batches` / docs 订正件
- **执行者**：`gov-assets`（资产/口径同步工程师，非代码线）；**attempt** `643eee06-6846-411a-9e2d-d5656ccf65da`
- **时点**：2026-10-12（UTC）
- **权威清单**：`test-reports-2026-10/B18-登记.md` §B18-C-10 / §B18-C-12；`test-reports-2026-10/C-独立验证.md`、`C-独立验证-round2.md` §4.3「仍留档 11 项 O1–O11」
- **证据形态**：每条 = **工具 + 口径 + 值**；`blocked` / `not_measured` / `not_covered` / `not_counted_as_passed` 一律不折算 pass，均写状态 + 解除条件
- **真库不变量**：`app.db` = `34e48e7a21163db390eebda4f2030343f3609afedc65d8c6e909d6eb5a49177e` / **2531328 B** / mtime `2026-10-12 04:25:37.128430119 +0000` —— **开工、中途、收工三次复核恒等**（本件所有实验均在副本或隔离树进行）

---

## 0. 总览（5 项 × 终态）

| 项 | 内容 | 终态 | 一句话结论 |
| --- | --- | --- | --- |
| ① **O8** | `b17_governance_contract.py` 钉值 43/37 vs 判据层 D-9 的 44/38 | **✅ 完成** | 按 **A-70 三步**重基线：改前实测 **FAIL（PASS 0 / FAIL 1）**，改值后复跑 **PASS（exit 0）**；该文件**不在门禁链内**，`ci_gates` 读数不受影响（实测 blocking 失败=无） |
| ② **O5** | coverage 冻结锚点 `evidence/harness/coverage.json` 不可恢复 | **按设计接受 + 一项 blocked** | 三查证据齐（不在盘 / `_anchor-history/` 不存在 / git 历史 0 条）⇒ **确不可恢复**；其「锚点」角色已由**不可变 run 产物快照** `ci-run-20261009-054416/coverage.json` 承接（246076 B / `58bf8446…`）；**「新建冻结锚点」登记 `blocked`**（须 captain/用户层裁定，且与 V-14 的 G1 冲突） |
| ③ **B18-08 ④** | `regression_preflight` 白名单内容 | **机制 ✅ 实测可执法；内容 按设计接受** | 通配白名单**实测被拒**（`harness/*.json` ⇒ `[verify] 白名单第 2 行含通配符…` **exit 2** = 阴性对照转红）；精确路径**被接受**；docstring 明载「**不给默认白名单**」且全仓无白名单文件 ⇒ 无「默认内容」可对拍 |
| ③ **B18-08 ⑤** | 锚点 `superseded_by` | **按设计接受** | 被指锚点 `evidence/harness/coverage.json` **已不在盘**（= O5）⇒ 载体不存在，无法追写；该字段的现行唯一权威定义在 `40-第2轮实测Runbook与台账规范.md:294` |
| ④ **`delivery_batches`** | 视图口径与判据落点 | **✅ 完成（按设计接受）** | 权威判据 = `docs/开发与测试规划-2026-10-06.md:478` B10-07「`shipping.py` + `mes_service.py` 无输出」；**实测四文件零命中**；口径 = 计划面 JSON，**不驱动**库存/发货动作 |
| ⑤ **docs 6 处「模板 2 处」** | 历史件计数过期 | **✅ 完成** | 新建 `docs/订正-内联角色模板计数-2026-10-12.md`（**不覆盖**原文件，原文件 sha256 恒等）；现况 = **模板 1 处 + Python 15 处 = 16 条** |

> **⚠ 不得写作「在册项清零」**：本件 5 项中 2 项为「按设计接受」、1 项含 `blocked`、另登记 3 条残留（见 §6）。任何「清零 / 全绿」表述均与本件读数不符。

---

## 1. ① O8：`b17_governance_contract.py` 钉值冲突 ⇒ A-70 三步重基线

### 1.1 现场与其冲突（工具 + 口径 + 值）

- **被订正对象**：`test-reports-2026-10/harness/b17_governance_contract.py`（B17-14 判据）。
- **工具 / 口径**：读该判据 `ok` 合取式中的两个钉值与现场 `coverage.json` 对拍；现场源 = `harness/measure_coverage.py` 产出的 `summary.multi_method_with_get_total` / `_uncovered`。
- **值**：
  - 钉值（改前，`:723-724`）：`s['multi_method_with_get_total'] == 43` / `s['multi_method_with_get_uncovered'] == 37`
  - 现场：**`N=44 / M=38`**（同一契约自印：`现场 exit=0：规则 273 / GET+写 N=44 / 未命中 M=38`）
  - 判据层同键（权威）：`test-reports-2026-10/harness/coverage_drift.py:20` 的 **D-9** = `== 44` / `== 38` / `== 38`（且 `M ≤ N`），并自带 A-70 演进链（`SEC-CSRF-01` 43/37→44/38；`e057e81` 44/38→43/37；`B18-Q1` 43/37→44/38）
- **冲突定性**：`coverage_drift.py` 的 D-9 已随 **B18-Q1**（新增 `GET+POST /auth/change-password`）升至 `44/38`，而本契约仍钉 `43/37` ⇒ **该合取项恒 False ⇒ 恒 FAIL**。与 O8 原文逐字一致（`C-独立验证-round2.md:193`）。

> **标签勘误（登记）**：O8 原文标题写「**B17-11** 契约钉值」，但其实质指向的行号 `:723-724` 属 **B17-14** 判据。本件按**实质**（43/37 钉值）处置，并另行登记 B17-11 为相邻残留（§6 第 2 行）。

### 1.2 A-70 第 ① 步：旧值留档

| 项 | 值 |
| --- | --- |
| 旧钉值 | `multi_method_with_get_total == 43`、`multi_method_with_get_uncovered == 37` |
| 旧落点 | `test-reports-2026-10/harness/b17_governance_contract.py:723-724`（`ok = (` 合取式的第 1、2 行） |
| 旧叙述 | 同文件 `:732` 逐字 `（N==43 / M==37 / M==len(list) / M<=N，` |
| 旧值来源 | B17-14 登记时点判据层 D-9 恰为 `43/37`（`e057e81` 删除 `GET+POST /auth/register` 之后的读数） |
| 留档落点 | **① 文件内注释**（改后 `:723-729`，8 行，含触发 ID 与三处复算指引）；**② 本件 §1.2**；**③ `test-reports-2026-10/B18-登记.md` §B18-E-01** |

### 1.3 A-70 第 ② 步：阴性对照先转红（实测读数）

为**不触碰仓库内既有证据与非本任务文件**，在**隔离副本树**中执行（`/tmp/t18-iso`，由仓库 `tar` 复制，66 MB；`app.db` 为副本，真库路径不在其内）：

```
rm -rf /tmp/t18-iso && mkdir -p /tmp/t18-iso
cd /root/code/MyERP && tar -c --exclude='./.git' --exclude='./.tmp' --exclude='./instance' \
  --exclude='./test-reports-2026-10/.tmp' --exclude='./test-reports-2026-10/evidence' . | tar -x -C /tmp/t18-iso
mkdir -p /tmp/t18-iso/test-reports-2026-10/evidence/harness
cd /tmp/t18-iso && /opt/wage-venv/bin/python -B test-reports-2026-10/harness/b17_governance_contract.py --only B17-14
```

**实测（改前，24.4 s）**：

```
[FAIL] B17-14   多方法面进判据层 + docstring | 现场 exit=0：规则 273 / GET+写 N=44 / 未命中 M=38；
       判据层引用面键 {'…/coverage_drift.py': 10, '…/ci_gates.py': 0, '…/negative_matrix.py': 0, 'scripts/check_doc_claims.py': 0}；
       变异体（M=0,N=99,明细清空）⇒ drift exit=1 FAIL=['D-9']（未变异 exit=0 FAIL=[]）；docstring 含 273=True、残留 271 行=[]
==== 汇总 1 条：PASS 0 / FAIL 1 / BLOCKED 0（blocked 不计入通过）====
EXIT=1
```

⇒ **合取式唯一为假项 = `== 43` / `== 37`**：其余各合取项（`c0 == 0` / `face_line` / `any(refs.values())` / `fails1` / `doc_live` / `not stale`）均为真，且变异体敏感度仍在线（`M=0,N=99` ⇒ D-9 转红）。**阴性对照成立。**

### 1.4 A-70 第 ③ 步：改值 + 复跑绿

**改动面（唯一受跟踪文件）**：`test-reports-2026-10/harness/b17_governance_contract.py`

1. `:723-724` 钉值 `43`/`37` → **`44`/`38`**；
2. 同处上方新增 **8 行 A-70 注释**（旧值留档 + 触发 ID + 三处复算指引 + 回退指引）；
3. `:732`（改后 `:739`）叙述 `N==43 / M==37` → **`N==44 / M==38`**。

**实测（改后，隔离树复跑）**：

```
[PASS] B17-14   多方法面进判据层 + docstring | … 规则 273 / GET+写 N=44 / 未命中 M=38 … docstring 含 273=True、残留 271 行=[]
==== 汇总 1 条：PASS 1 / FAIL 0 / BLOCKED 0（blocked 不计入通过）====
EXIT=0
```

⇒ **红 → 绿可归因到本次改值**（同一隔离树、同一命令，唯一变量 = 该文件）。

**改动面指纹**：

| 命令 | 值 |
| --- | --- |
| `git diff --numstat -- test-reports-2026-10/harness/b17_governance_contract.py` | `10	3` |
| `git diff --ignore-cr-at-eol --numstat -- …`（C7 复核） | `10	3`（**与不忽略行尾读数逐字一致**） |
| `git show HEAD:…b17_governance_contract.py \| grep -c $'\r'` | **0** |
| 改后 `ok = (` 行号 | **`:730`**（旧 `:723`，Δ+7 = 插入的注释块行数） |
| 改后叙述行号 | **`:739`**（旧 `:732`，Δ+7） |

### 1.5 「口径表 / PINNED 同步」核查（工具 + 口径 + 值）

| 面 | 工具 | 值 | 是否需改 |
| --- | --- | --- | --- |
| 判据层口径表 | `grep -n 'multi_method_with_get_total' test-reports-2026-10/harness/coverage_drift.py` | `:20` = `== 44 / == 38 / == 38`（**本就 44/38**） | **否**（无需同步） |
| `check_doc_claims.py` PINNED | `grep -n "'42'\|'43'\|'37'\|'38'\|'44'\|multi_method" scripts/check_doc_claims.py` | **零命中** ⇒ PINNED 不含该键 | **否**（无该键可同步） |
| 其余钉值面 | `grep -rn 'multi_method_with_get_total' --include='*.py' .`（排除 `.tmp`） | 仅 4 文件：`coverage_drift.py` / `measure_coverage.py` / `b17_governance_contract.py`（本次已改） / `negative_matrix.py`（**0 引用**） | **否** |
| 负控基线 | `coverage_drift.py:280` | `synthetic_doc()` 内 `'multi_method_with_get_total': 44, 'multi_method_with_get_uncovered': 38` | **否**（本就 44/38） |

⇒ **结论：本次重基线只需改 `b17_governance_contract.py` 一处**，判据层口径表与 PINNED 均**已与现场一致**，不存在第二处待同步落点。

### 1.6 该文件是否在门禁链内 / 是否影响 `ci_gates` 读数

- **不在门禁链内**（工具 + 口径 + 值）：`grep -rn 'b17_governance_contract' test-reports-2026-10/harness/ci_gates.py test-reports-2026-10/harness/run_gates.py scripts/ Jenkinsfile .github/workflows/` ⇒ **零命中（rc=1）**；`grep -c 'b17\|governance' test-reports-2026-10/harness/ci_gates.py` ⇒ **0**。
- **`ci_gates` 读数未受影响（实跑）**：

```
/opt/wage-venv/bin/python -B test-reports-2026-10/harness/ci_gates.py --phase first
run 目录：test-reports-2026-10/evidence/harness/ci-run-20261012-080259/
steps=20   blocking 失败 = 无   report-only 失败 = ['evidence_hash']   注入未生效 = 无
仓库根两 JSON 未被触碰 = True（A-11）   gaps: A-63-STEP2-BUILD-GATE = blocked（不计入通过数）
exit = 2   （语义：2 = 仅 report-only 失败）
check_doc_claims 步 = OK  group=blocking  exit=0  checks 5/5
```

  ⇒ **blocking 面全绿**；`exit=2` 的唯一来源是**先在性** report-only `evidence_hash`（`modified=2`，两条与 t2/t4/t6/t13 各轮**同一对**文件；`baseline_files 1433 / modified 2 / deleted 0`），与本轮改动无关，按纪律**不折算 pass**（§6）。
- **该契约自身仍不在链内**：本次只做**重基线**（消除其恒红），**是否将其重新入链是 captain 层决策，本件不擅自改 `ci_gates` 步骤数**（§6 第 4 行）。

---

## 2. ② O5：coverage 冻结锚点不可恢复 ⇒ 终态

### 2.1 三查（工具 + 口径 + 值）

| 查 | 命令 | 值 |
| --- | --- | --- |
| 锚点是否在盘 | `ls -l test-reports-2026-10/evidence/harness/coverage.json` | **No such file or directory** |
| 声明的历史目录 | `ls -d test-reports-2026-10/evidence/harness/_anchor-history`（`coverage_drift.py:120` 声明） | **No such file or directory** |
| git 历史是否可回溯 | `git log --all --oneline -- 'test-reports-2026-10/evidence/harness/coverage.json' \| wc -l` | **0 条** |
| 忽略规则 | `grep -n 'evidence' .gitignore` | **`:42:/test-reports-2026-10/evidence/`** ⇒ 整目录被忽略、从未入 git |

⇒ **字节确不可恢复**（与 O5 原文逐字一致）。

### 2.2 判据本身是否正确（fail loud 已验证）

```
/opt/wage-venv/bin/python -B test-reports-2026-10/harness/coverage_drift.py
→ [USAGE] 未提供 --coverage：本工具需要**一份本次 run 的被测产物**，例如
  [USAGE] 冻结锚点仅作**历史留档**、不参与判据：它记录的是 V-06/C-05 有意更新**之前**的 6/14/101，
          而 LOCKED 已按 A-70 更新为 108/116/0 ⇒ 直接套用必然假红（N-1）。
  [USAGE] exit 2 = 未提供产物（用法错误），**不是覆盖退化 / 不是回归**。
  [e03] exit_code_semantics={"script": "…/coverage_drift.py", "class": "判据层（TL-03 雏形）—— 用法错误出口",
        "rule": "no --coverage -> exit 2（用法错误，不是回归）; explicit --coverage: all checks passed -> exit 0, any failed -> exit 1",
        "n1_trigger": "V-16 / N-1（锚点 vs LOCKED 语义互斥的假红陷阱处置，2026-10-07）", "code": 2}
EXIT=2
```

⇒ 锚点缺失**不再产生假红**（N-1 已按 captain 首选「fail loud」处置，登记 A-115/A-116）。

### 2.3 终态判定

| 子项 | 终态 | 依据 |
| --- | --- | --- |
| 锚点字节**不可恢复** | **按设计接受** | §2.1 三查；且 V-14 的 G1 曾判该锚点 `unchanged`，重生会**推翻 G1**；captain 在 A-113 已裁定「**禁止重生锚点**」 |
| 锚点的「冻结基线」**角色已承接** | **按设计接受** | **不可变 run 产物快照** `test-reports-2026-10/evidence/harness/ci-run-20261009-054416/coverage.json` = **246076 B / mtime `Oct 9 05:45` / sha256 `58bf844628402ae6d87f6a0f0336049d313463e83c28dfa448bbefd9db21e055`**（只读归档 `-r-xr-xr-x`）；`ci_gates.py` 以 `COVERAGE_ARCHIVE_ANCHOR` 指向它、`check_doc_claims.py:73-80` 的 `COVERAGE_ANCHOR_READINGS` 以它作留档读数源 ⇒ 符合 captain 通用纪律「**锚点与产物分离**」 |
| **新建**冻结锚点 | **`blocked`** | 解除条件：**captain/用户层裁定**「新建冻结锚点 + 明确其与 `LOCKED`（`108/116/0`）的语义关系」（历史上 N-1 就是这对互斥）；**非本任务可单方决定**（涉判据面与 V-14 G1） |

> **旁注（任务书所述「`b17-verify/probe_*.txt` 字节已丢」）**：该对文件属 **O1** 面（`evidence_hash` 的 `modified=2`）。本次实测：两文件**当前** sha256 = `f81525c2…5afb16`（11234 B）/ `da0c377d…954b68`（3186 B），与基线 `1664B44B…`/`59A7E5F0…` **不同** ⇒ 旧字节同样不可复原；但**写入者已定位并已修**（`harness/measure_coverage.py:254` 的裸 `open(ev,'w')` → `_env.save_evidence()`；根因注释自述「2026-10-12 04:45 在 b17-verify/ 实测发生过一次，导致 evidence_hash 报 2 条 modified」）⇒ **同一病根已收口，此处不再重复登记**。

---

## 3. ③ B18-08 ④⑤

### 3.1 ④ `regression_preflight` 白名单内容

**载体**：`test-reports-2026-10/harness/regression_preflight.py`（162 行）。

**机制（工具 + 口径 + 值，全部实跑）**：

| 场景 | 命令 | 实测值 |
| --- | --- | --- |
| 阳性：精确相对路径白名单 | `… regression_preflight.py verify --whitelist /tmp/t18-wl-exact.txt`（内容 `harness/coverage.json`） | **被接受**（无通配报错），仅报 `NO MANIFEST：请先跑 preflight` ⇒ **exit 2** |
| **阴性：通配白名单（必须被拒）** | `… verify --whitelist /tmp/t18-wl-wildcard.txt`（内容 `harness/*.json`） | **`[verify] 白名单第 2 行含通配符（本工具只接受精确路径）：harness/*.json`** ⇒ **exit 2** ✅ **判据实测转红** |
| 用法面 | `… --help` | 打印 22 行 docstring ⇒ **exit 2** |
| 归档目录 | `ls -d test-reports-2026-10/evidence/_phaseB-prefreeze/` | **No such file or directory** |

**口径（docstring `:11-15` 逐字）**：「白名单只接受**精确相对路径**（相对 `evidence/`，一行一条，`#` 注释）——**通配一律拒绝**」；「**不给默认白名单**：不传参 = 与旧行为完全一致」。

**终态**：

| 子项 | 终态 | 依据 |
| --- | --- | --- |
| 白名单**机制** | **✅ 实测可执法** | 阴性（通配）**exit 2**、阳性（精确）**被接受** —— 判据不恒真 |
| 白名单**默认内容** | **按设计接受** | docstring 明载「不给默认白名单」；`grep`/`find` 全仓**无白名单文件**（唯一 `t8-evidence-whitelist.json` 属 `evidence_hash`，且在 `test-reports-2026-10/retired/` 有退休存档 `B18-t8-evidence-whitelist-退休存档-20261011.json`）⇒ **无「逐条内容」可对拍** |
| 两阶段全跑（`preflight` → `verify`） | **`not_measured`** | 解除条件：在**允许写 `evidence/**`** 的一轮里跑 `preflight` + `verify --whitelist <精确路径文件>`。本轮硬约束「禁改 `evidence/**`」，且 captain 已在 A-121 明确**拒绝**「为拿绿灯而重跑 `preflight` 归档」（会把 2.3 GB 再归档进被 `evidence_hash` 索引的 `evidence/`，放大 A-89 病根）⇒ **本任务不跑，不折算 pass** |

### 3.2 ⑤ 锚点 `superseded_by`

- **被指锚点** = `test-reports-2026-10/evidence/harness/coverage.json` ⇒ **已不在盘**（§2.1 三查）⇒ **载体不存在，无法追写 `superseded_by`**。
- **该字段的现行唯一权威定义**：`test-reports-2026-10/40-第2轮实测Runbook与台账规范.md:294`（台账字段 `superseded_by`，与 `:254` 的「唯一裁决规则」配套）；模板 `test-reports-2026-10/40-第2轮实测台账模板.json:132` = `"superseded_by": null`。全仓对**该锚点**无任何 `superseded_by` 改动进入本批提交。
- **终态**：**按设计接受**。理由：该字段的原始目的是「防止第三方把已作废的冻结锚点读成现行值」；在 N-1 已按 fail loud 处置后，**锚点不再被任何判据读取**（§2.2 实测 `exit 2` + `[USAGE]` 明写「冻结锚点仅作历史留档、不参与判据」）⇒ **目的已由更强的机制达成**，且锚点载体本身已不存在 ⇒ 追写不可执行亦无必要。

---

## 4. ④ `delivery_batches` 视图口径：权威读数与判据落点

**判据落点（权威计划原文）**：

| 出处 | 逐字 |
| --- | --- |
| `docs/开发与测试规划-2026-10-06.md:478`（B10-07） | 「`delivery_batches` 与发货**无关联**（计划与现实无论对照）｜G-02｜`Select-String delivery_batches app/main/shipping.py app/services/mes_service.py` → **无输出**｜✅ 若采纳 T3 Q6-A（**只做对照视图**）」 |
| `docs/开发与测试规划-2026-10-06.md:822`（G-B） | 「`delivery_batches` 是否升级为驱动发货｜…｜**只做对照视图**｜**保持现状（登记「无关联」）**」 |
| `docs/test-reports/2026-10/03-需求追溯矩阵.md:93`（REQ-C-04） | 「`delivery_batches` 只是计划 JSON，**不驱动任何库存动作**（口径登记）｜**N 本阶段不测**（G-B 建议保持现状）」 |

**实测（工具 + 口径 + 值）**：

| 面 | 命令（口径） | 值 |
| --- | --- | --- |
| **执行面（B10-07 判据本体）** | `grep -c 'delivery_batches' <file>` | `app/main/shipping.py` **0** / `app/main/stock.py` **0** / `app/services/mes_service.py` **0** / `app/utils/excel_generator.py` **0** |
| **计划面列** | `grep -n 'delivery_batches' app/models.py` | `:1845 delivery_batches = db.Column(db.Text)`（归属类 = `app/models.py:1813 class SalesOrderItem`） |
| **计划面属性** | 同上 | `:1913 delivery_batches_list` / `:1923 set_delivery_batches` / `:1929 delivery_status` / `:1966 delivery_progress` |
| **计划面端点（唯一读写通路）** | `grep -n 'delivery_batches' app/main/routes.py` | `:10724` 路由 `/sales_order_item/<int:item_id>/delivery_batches/manage`（GET）/ `:10727 manage_delivery_batches_page` / `:10731` 读 / `:10736` 路由 `…/delivery_batches`（GET,**POST**）/ `:10740 manage_delivery_batches` / `:10756` 写 `order_item.set_delivery_batches(batches)` / `:10784` 读 `'batches': order_item.delivery_batches_list` |

**终态：✅ 完成（按设计接受）** —— B10-07 判据**实测满足**（执行面四文件零命中）；口径 = **计划面 JSON，只做对照视图，不驱动库存/发货动作**；本阶段**不测**（REQ-C-04 明载）。**未新增任何判据**，故不适用 A-70。

> **备查瑕疵（既有，非本轮引入，不改）**：`app/models.py:1929 delivery_status` 的 `:1939 overdue_count = 0`、`:1949 if delivery_date < today:` 与 `:1951 elif delivery_date < today:` **条件同构** ⇒ `:1952 overdue_count += 1` **不可达**，`:1960 elif overdue_count > 0:` 分支**永不生效**。已读数登记，未改动（超出本轮范围；如需修须单独立项）。

---

## 5. ⑤ docs 订正件（`docs/**` 只新建、不覆盖）

- **订正件（新建）**：`docs/订正-内联角色模板计数-2026-10-12.md`
- **被订正文件**：`docs/开发与测试规划-2026-10-06.md` —— **未改动一字**，开工/收工 sha256 恒等 `78da5698065406bb2f7869c9321f264557ad8e99adf07a5c5a358d5e9a6934e6`（= 记录值 `78DA5698…6934E6`）
- **6 处落点**：`:92` / `:129` / `:390` / `:436` / `:787` / `:901`（含字面串 `模板 2 处` 的是 `:129` 与 `:787`）
- **订正结论**：「模板 **2 处**」→ **模板 1 处**（`app/templates/main/quality/tasks.html` 那处已由 **B16-08** 等价改写为 `can('quality.inspect')`，现 `:343`）；`app/templates/main/quality/task_detail.html` 那处仍在（现场 `:22`，属 B16-08 契约豁免）；**Python 15 处不变，总数 16 条**

**依据（工具 + 口径 + 值）**：

| 工具 | 口径 | 值 |
| --- | --- | --- |
| `grep -c 'current_user\.role' app/templates/main/quality/tasks.html` | 子串计数（按行） | **0** |
| `grep -c … task_detail.html` | 同上 | **1** |
| `sed -n '110,131p' scripts/permission_matrix.py` | `INLINE_ROLE_WHITELIST` 逐条枚举（权威台账） | **16 条 = 15 Python + 1 模板**；`:100` 注释逐字「台账 = 15 Python + 1 模板」；`:130` 模板条 = `('app/templates/main/quality/task_detail.html', 13, "…")`（行号 `13` 为登记时点，判据按 `(file, 文本)` 出现次数、**不按行号**） |
| 实跑 `scripts/_sandbox_compat.py scripts/permission_matrix.py --no-dump` | B17-04 **双向**断言 | **`[OK] 内联 role ≤ 白名单 = 全绿（扫描 16 条 == 白名单 16 条，按 (file, 文本) 出现次数逐一相等、双向无漏斗；行号漂移 9 处仅 WARN）`** ⇒ exit **0**（若模板仍 2 处，台账缺 1 条 ⇒ 双向断言必红） |
| 改写机制 | `app/templates/main/quality/tasks.html:342-343` | `:342` 逐字注释 `{# B16-08 等价改写：原内联角色集合 ('admin','manager','inspector') 与 can('quality.inspect') 逐元素相等（app/permissions.py:76）。 #}`；`:343 {% if can('quality.inspect') %}` |

**终态：✅ 完成**。**未改任何判据**（判据面 `INLINE_ROLE_WHITELIST` 与 B17-04 双向断言一字未动）⇒ 不适用 A-70。

> **纪律说明**：本项**不覆盖** `docs/开发与测试规划-2026-10-06.md`（该文件写于批次8/9 时点，「模板 2 处」是**当时正确**的读数）—— 按交付纪律 ③，订正一律**新建件**，原文件保留历史读数。

---

## 6. 非 pass 登记表（一律不折算 pass）

| # | 项 | 状态 | 解除条件 |
| --- | --- | --- | --- |
| 1 | **新建** coverage 冻结锚点（O5 第 3 子项） | `blocked` | captain/用户层裁定「新建冻结锚点 + 明确其与 `LOCKED`（108/116/0）的语义关系」；须先解决 N-1 同族互斥，并说明与 **V-14 的 G1**（曾判该锚点 `unchanged`）的冲突处置 |
| 2 | **B17-11** 判据残留（O8 相邻项，非本件范围） | `blocked` | 该判据断言「`271` 在 `git show HEAD:` 的常量里」（= 提交前一次性工具口径），而 **B17 已入库 ⇒ HEAD 即现场 273 ⇒ 结构性不可满足**（t2 已在真树实测 FAIL：`'271' in hprobe` = False）。解除条件：单独立项按 A-70 改为「改前帧取钉住提交」或退役该判据；**不得**为让它绿而改 `git show HEAD:` 的取树口径。⚠ 本次在隔离树复跑 `--only B17-11` 得 FAIL，但其行内 `HEAD 该常量=` 显示为 stderr 文本（**非 git 树伪影**）⇒ 该次读数**不作为证据**，以 t2 真树读数为准 |
| 3 | B18-08 ④ 两阶段全跑（`preflight`→`verify`） | `not_measured` | 允许写 `evidence/**` 的一轮里跑；captain 已在 A-121 拒绝为拿绿灯而重跑归档 |
| 4 | 把 `b17_governance_contract.py` **重新入链** `ci_gates` | `not_done` | captain 层决策（改 `ci_gates` 步骤数 = 改门禁口径，须走 A-70 并同步三处步骤数引用）；本轮**只做重基线**，未改链 |
| 5 | `evidence_hash`（report-only，先在性） | `blocked` | A-70 `--freeze` 重基线 `evidence/artifact_hashes.json`，或治理件落到新 `run_id` 目录后复跑取 `exit=0`。本轮实测 `modified=2`（`b17-verify/probe_permission_matrix.txt`、`probe_smoke_test.txt`），**与 t2/t4/t6/t13 各轮同一对**，非本轮引入；写入者已定位并已修（`measure_coverage.py:254` → `_env.save_evidence()`） |
| 6 | `A-63-STEP2-BUILD-GATE` | `not_counted_as_passed` | `ci_gates` 自报 `blocked（不计入通过数）`；容器内无 `docker` ⇒ 不可测（同 O2） |

---

## 7. 复现命令（一次性）

```bash
cd /root/code/MyERP
PY=/opt/wage-venv/bin/python

# —— 真库三值（开工 / 收工各一次，应恒等）——
sha256sum app.db && stat -c '%s %y' app.db

# —— ① O8：A-70 三步（隔离树；勿在仓库树跑，避免写 evidence/**）——
rm -rf /tmp/t18-iso && mkdir -p /tmp/t18-iso
tar -c --exclude='./.git' --exclude='./.tmp' --exclude='./instance' \
    --exclude='./test-reports-2026-10/.tmp' --exclude='./test-reports-2026-10/evidence' . | tar -x -C /tmp/t18-iso
mkdir -p /tmp/t18-iso/test-reports-2026-10/evidence/harness
cd /tmp/t18-iso && $PY -B test-reports-2026-10/harness/b17_governance_contract.py --only B17-14   # 改前 FAIL / 改后 PASS
cd /root/code/MyERP && git diff --numstat -- test-reports-2026-10/harness/b17_governance_contract.py

# —— ① 门禁链归属与读数 ——
grep -rn 'b17_governance_contract' test-reports-2026-10/harness/ci_gates.py \
     test-reports-2026-10/harness/run_gates.py scripts/ Jenkinsfile .github/workflows/   # 零命中
$PY -B test-reports-2026-10/harness/ci_gates.py --phase first

# —— ② O5 三查 ——
ls -l test-reports-2026-10/evidence/harness/coverage.json      # 不存在
ls -d test-reports-2026-10/evidence/harness/_anchor-history    # 不存在
git log --all --oneline -- 'test-reports-2026-10/evidence/harness/coverage.json' | wc -l   # 0
$PY -B test-reports-2026-10/harness/coverage_drift.py          # exit 2 + [USAGE]
sha256sum test-reports-2026-10/evidence/harness/ci-run-20261009-054416/coverage.json

# —— ③ B18-08 ④ 白名单机制（成对对照）——
printf 'harness/*.json\n' > /tmp/t18-wl-wildcard.txt
printf 'harness/coverage.json\n' > /tmp/t18-wl-exact.txt
$PY -B test-reports-2026-10/harness/regression_preflight.py verify --whitelist /tmp/t18-wl-wildcard.txt  # exit 2 通配被拒
$PY -B test-reports-2026-10/harness/regression_preflight.py verify --whitelist /tmp/t18-wl-exact.txt     # exit 2 仅缺 manifest

# —— ④ delivery_batches ——
for f in app/main/shipping.py app/main/stock.py app/services/mes_service.py app/utils/excel_generator.py; do
  printf '%-34s %s\n' "$f" "$(grep -c delivery_batches $f)"; done      # 全 0
grep -n 'delivery_batches' app/models.py app/main/routes.py

# —— ⑤ docs 订正件依据 ——
grep -c 'current_user\.role' app/templates/main/quality/tasks.html app/templates/main/quality/task_detail.html  # 0 / 1
sed -n '110,131p' scripts/permission_matrix.py
$PY -B scripts/_sandbox_compat.py scripts/permission_matrix.py --no-dump | grep '内联 role'   # 扫描 16 == 白名单 16
git status --porcelain -- docs/ && sha256sum docs/开发与测试规划-2026-10-06.md                # 原文件未改
```

---

## 8. 收尾声明

1. **改动面（受跟踪文件，3 个）**：
   - `test-reports-2026-10/harness/b17_governance_contract.py`（`10 3`，A-70 重基线）
   - `docs/订正-内联角色模板计数-2026-10-12.md`（**新建**）
   - `test-reports-2026-10/E-资产与口径收口.md`（**新建**，本件）
   - 另 **append-only**：`test-reports-2026-10/B18-登记.md` 追加 `§B18-E-01`（**不改写既有段落**）
2. **未做**：未 `git add` / 未 commit / 未 push（提交由 captain 白名单复核）；未改 `app/**`；未覆盖 `docs/**` 既有文件；未改 `evidence/**` 既有文件；未执行 `flask db *`；未改任何判据口径（除 ① 的 A-70 重基线外无判据改动）。
3. **真库**：`app.db` 三值开工/中途/收工**三次恒等**；本件所有实验在隔离副本树或只读路径进行。
4. **门禁**：`ci_gates.py --phase first` = **steps=20 / blocking 失败 = 无 / report-only = ['evidence_hash'] / exit = 2**（`exit≠0` 唯一来源为先在性 report-only，已在 §6 第 5 行登记 `blocked`，**不折算 pass**）。
