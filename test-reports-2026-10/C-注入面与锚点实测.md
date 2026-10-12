# C-注入面与锚点实测（G-15 TL-05/06/07 三条 + G-16① 显式锚点残留复测）

- **任务**：`t3 [T-gov-inject]`（attempt_id `b234a3df-b72f-465f-8ce6-6123855c8138`）
- **执行者**：`gov-inject`（非代码线；**只测不改**——未改任何判据/钉值/期望值，未改仓库任何受跟踪文件）
- **时点**：2026-10-12 04:40–04:46 UTC｜解释器 `/opt/wage-venv/bin/python`（3.11.2）｜cwd `/root/code/MyERP`
- **本件性质**：新增件（append-only，不覆盖任何既有文件）
- **真库 `app.db` 三值（钉值 = `34E48E7A21163DB390EEBDA4F2030343F3609AFEDC65D8C6E909D6EB5A49177E` / 2531328 B / `2026-10-12 04:25:37.128430119 +0000`）**：
  - 操作后（04:43:10 UTC，探针全跑完）：`34e48e7a21163db390eebda4f2030343f3609afedc65d8c6e909d6eb5a49177e`｜2531328｜`2026-10-12 04:25:37.128430119 +0000` ✅（`measure_coverage` 另自报 `real.db unchanged = True`）
  - **探针窗口（04:40–04:44）内 `app.db` 未被写入，由 mtime 直接判定**：mtime = `04:25:37.128430119` **早于**窗口起始，而 mtime 本身就是钉值三值之一（任何写入必改 mtime）。
  - ⚠ 口径说明（不掩饰）：本件**未单独落一次「操作前」读数文件**——原因即上一条：mtime 判定覆盖面严格强于「前后各核一次」（前者能证明「窗口内未写」，后者只能证明「首尾同值」）。
  - 本件所用 5 个工具（`check_properties` / `check_doc_claims` / `coverage_drift` / `measure_coverage` / `ci_gates`）均为**静态扫描**，不建立 DB 连接。
- **产物落点**：`test-reports-2026-10/.tmp/t3-inject-20261012/`（`.gitignore:41`）+ `test-reports-2026-10/evidence/harness/ci-run-20261012-0441{28,45}/`（`.gitignore:42`）。
  `git status --porcelain` 复核：**无任何受跟踪文件改动**。未 `push`（依约束 ⑧）。

---

## 0. 总览

| # | 注入面 | 判据入口 | 注入命令 | 读数 | 期望 | 判定 |
| --- | --- | --- | --- | --- | --- | --- |
| G-15① | `e.not_a_column`（不存在的列当列用） | `scripts/check_properties.py`（`ci_gates` 步 4，blocking） | 直测 `--root <合成树>` / 入口 `ci_gates.py --inject-step check_properties` | 直测 **exit 1**、入口 **exit 1** | exit 1 | **PASS** |
| G-15② | 作废口径值 `≥135`（另 `≥139` / `45 张`） | `scripts/check_doc_claims.py`（`ci_gates` 步 20，blocking） | `--docs <含注入行副本> --coverage <本次产物>` | **exit 1**（0→1，仅差注入行） | 非 0 | **PASS** |
| G-15③ | 删 `requirements.lock` | 同上（TL-07 依赖钉版） | `--lock /nonexistent/requirements.lock --coverage <本次产物>` | **exit 1** | 非 0 | **PASS**（真删文件路径见 §5 未测项） |
| G-16① | 显式传锚点 | `harness/coverage_drift.py` | `--coverage test-reports-2026-10/evidence/harness/coverage.json` | **exit 1**（`coverage.json 不存在`） | — | **判据正确，非缺陷**（§4；证据形态与 `70` §5.2③ 已不同，附新登记事实） |

**未测项**：G-15③ 的「物理删除 `requirements.lock`」路径；G-16① 的**处置**（重建/改默认路径）——均见 §5，一律不折算 pass。

---

## 1. G-15① 注入 `e.not_a_column` ⇒ 期望 exit 1（TL-05 面）

**口径**：`scripts/check_properties.py` 扫描 `app/**/*.py`，判据 = `RESULT: OK` + exit 0 + `已扫描 25 个文件，模型类 74 个`（`ci_gates` 步 4，blocking；步清单见 `ci_gates.py --list`）。注入面 = 把「不存在的列/@property 当数据库列用」的违规样本喂进去，判据必须转红并被**指名**。

### 1a. 直测（任务书字面的注入内容，合成树只读复制）

```bash
# 合成树：app/models.py 副本 + 注入文件 bad_inst.py
#   from models import Employee
#   def bad():
#       e = Employee()
#       return e.not_a_column
/opt/wage-venv/bin/python -B scripts/check_properties.py \
  --root test-reports-2026-10/.tmp/t3-inject-20261012/tl05
```

读数（stdout 全文）：

```
发现 1 处违规：
  test-reports-2026-10/.tmp/t3-inject-20261012/tl05/bad_inst.py:6  [实例访问了该类不存在的属性]  e.not_a_column —— e 判定为 Employee 的实例，而该类及其项目内基类都没有 not_a_column
RESULT: FAIL
EXIT_tl05=1
```

**阴性对照（同一入口、真实树）**：`/opt/wage-venv/bin/python -B scripts/check_properties.py --selftest` ⇒ `自检 22/22 通过` / `已扫描 25 个文件，模型类 74 个` / `RESULT: OK（未发现把 @property / 不存在的列当数据库列用）` / **exit 0**。
⇒ 成对读数（0 → 1），注入敏感且违规被指名。

### 1b. 现有入口（harness 自检面）

```bash
/opt/wage-venv/bin/python -B test-reports-2026-10/harness/ci_gates.py --inject-step check_properties
```

关键行（`echo $?` = **1**）：

```
[ci_gates] FAIL check_properties       group=blocking    exit=1 checks 3/6
[ci_gates]      !! expects 已扫描 25 个文件，模型类 74 个
[ci_gates]      !! expects RESULT: OK
[ci_gates]      !! exit exit == 0
[ci_gates]      inject kind=real_input criterion_unchanged=True
[ci_gates] 注入未生效 = 无
[ci_gates] exit = 1  phase=first
```

- harness 声明注入（`build_injection`，记于 run 产物）：`--root <syn>`,合成树 `inject/check_properties/`，fixture `bad_ref.py`，degradation = *`Employee.status` 是 `@property` 却作类级访问（A 类违规）*；`criterion_sha256_before == after == 68B3609C4B15FB99506E9E982E949E4770EC06EDCC2579B5B7F914D3150A472E`（**判据字节未改**）。
- 注：harness 声明的注入内容（`@property` 类级访问）与任务书字面的 `e.not_a_column`（不存在的属性，实例访问）**是同一门禁的两条违规分支**，1a/1b 分别覆盖；两条都 ⇒ exit 1。

**判定**：`PASS`。G-15 自陈的「注入面未实测」在本面**已解除**。

---

## 2. G-15② 注入 `≥135` ⇒ 期望非 0（TL-06 面）

**口径**：`scripts/check_doc_claims.py`（`ci_gates` 步 20，blocking）。三类检查中最相关的是**作废口径值**：文档任意一行出现 `≥135` / `≥139` / `45 张` ⇒ violation（同行带撤回标记则放行）；默认扫描域 = 5 份文档。

### ⚠ 先立基线（否则读数不可归因）

**新发现（本件实测）**：该脚本**默认调用**（不带 `--coverage`）今日**已红**——

```bash
/opt/wage-venv/bin/python -B scripts/check_doc_claims.py      # EXIT_dc_default = 1
[check_doc_claims] 钉常量 vs 权威源：20/29 相等
[check_doc_claims] [VIOLATION] 权威源错误：权威源缺失：test-reports-2026-10/evidence/harness/coverage.json（coverage 判据输入；本 run 产物请 `--coverage <path>` 显式传入）
[check_doc_claims] [VIOLATION] 权威源错误：锚点留档读数（…/ci-run-20261009-054416/coverage.json，sha256 58BF84462840…）：method_level_non_get_total=157 … writable_rules_non_get=155
[check_doc_claims] [VIOLATION] 口径源漂移：… 钉值 N ≠ 源值 None（源：coverage.json:…）      # 9 条，源值全 None
[check_doc_claims] RESULT: FAIL（violations=11）              # 计数拆解 = 2 条「权威源错误」+ 9 条「口径源漂移」
```

原因：默认权威源 `test-reports-2026-10/evidence/harness/coverage.json` **不存在**（见 §4）；`钉常量 vs 权威源：20/29 相等` 即 9 条钉值失去源。⇒ 必须在**可复现的绿色基线**上做注入对照，故本节的 `--coverage` 一律显式传**本次产物**（`measure_coverage.py --no-request-probes --out <run>/coverage.json`，246678 B）。

### 2a. 基线（C0）

```bash
RUN=test-reports-2026-10/.tmp/t3-inject-20261012
/opt/wage-venv/bin/python -B scripts/check_doc_claims.py --coverage $RUN/coverage.json
```
```
[check_doc_claims] 钉常量 vs 权威源：29/29 相等
[check_doc_claims] 文档：扫描 5 份、带口径表 1 份
[check_doc_claims] RESULT: OK（violations=0）          EXIT_C0 = 0
```

### 2b. 阴性对照（C1）与三处注入（C2a/b/c）

同一份文档副本（`dc_clean.md` = `test-reports-2026-10/80-开发与需求文档-实际进度逐条对账.md` 的逐字节副本），**只**追加一行注入文本：

```bash
cp "test-reports-2026-10/80-开发与需求文档-实际进度逐条对账.md" $RUN/dc_clean.md
cp $RUN/dc_clean.md $RUN/dc_ge135.md   && printf '\n## 注入行\n\n写端点无命中 覆盖 ≥135 条。\n' >> $RUN/dc_ge135.md
cp $RUN/dc_clean.md $RUN/dc_ge139.md   && printf '\n## 注入行\n\n写端点无命中 ≥139 条。\n'   >> $RUN/dc_ge139.md
cp $RUN/dc_clean.md $RUN/dc_45zhang.md && printf '\n## 注入行\n\n零行表 45 张。\n'          >> $RUN/dc_45zhang.md
```

| 用例 | 命令（追加 `--docs <副本>`，`--coverage` 恒为本次产物） | exit | 关键 stdout |
| --- | --- | --- | --- |
| C1 对照 | `--docs $RUN/dc_clean.md` | **0** | `文档：扫描 1 份、带口径表 0 份` / `RESULT: OK（violations=0）` |
| C2a `≥135` | `--docs $RUN/dc_ge135.md` | **1** | `[VIOLATION] …/dc_ge135.md:783：出现作废口径值 ge135 —— ≥135：写端点无命中计数（A-31 已更正为 ≥141）` / `RESULT: FAIL（violations=1）` |
| C2b `≥139` | `--docs $RUN/dc_ge139.md` | **1** | `… 出现作废口径值 ge139 —— ≥139：写端点无命中计数（同上，已作废）` / `RESULT: FAIL（violations=1）` |
| C2c `45 张` | `--docs $RUN/dc_45zhang.md` | **1** | `… 出现作废口径值 tables45 —— 「45 张」：零行表（A-2 已更正为 49 张）` / `RESULT: FAIL（violations=1）` |

**判定**：`PASS`。同一份文档、同一 `--coverage` 输入，**仅差一行注入** ⇒ 0 → 1，三条作废值全部分支实测命中。
**自检面旁证**：`check_doc_claims.py --selftest` ⇒ `自检 26/26 通过` / exit 0（含 `DC-N1 出现 ≥135 ⇒ fail`）。

### 2c. harness 入口（旁证，不替代 2b）

```bash
/opt/wage-venv/bin/python -B test-reports-2026-10/harness/ci_gates.py --inject-step check_doc_claims   # exit 1
[ci_gates] FAIL check_doc_claims       group=blocking    exit=1 checks 3/7
[ci_gates] inject kind=real_input criterion_unchanged=True     # criterion_sha256 84B3E67C…5E251 前后一致
[ci_gates] 注入未生效 = 无
```

harness **声明的**注入是「`--coverage` 指向归档锚点副本、`summary.writable_any_covered_by_all` 118→117（口径源漂移）」，**不是** `≥135`/删 lock；故本面以 2b 的三条直测为准。

---

## 3. G-15③ 删 `requirements.lock` ⇒ 期望非 0（TL-07 面）

**口径**：`check_doc_claims.py` 的 TL-07 分支——`requirements.lock` 不存在 ⇒ 1 条 violation ⇒ exit 1（`--lock` 为可注入路径参数；默认 = `<root>/requirements.lock`）。

```bash
RUN=test-reports-2026-10/.tmp/t3-inject-20261012
/opt/wage-venv/bin/python -B scripts/check_doc_claims.py \
  --coverage $RUN/coverage.json --lock /nonexistent/requirements.lock      # EXIT_C4 = 1
```
```
[check_doc_claims] [VIOLATION] requirements.lock 不存在：../../../nonexistent/requirements.lock（TL-07：删 lock ⇒ 非 0）
[check_doc_claims] RESULT: FAIL（violations=1）
```

- **阴性对照**：同命令不带 `--lock`（即 §2a C0：锁在、coverage 为本产物）⇒ `RESULT: OK（violations=0）` / exit 0。基线锁读数（同一 C0 现场）：`lock：33 条钉版 / 环境匹配 33 条 / exception 0 条`（另 `[WARN] 声明表环境标记在本平台为假，不进 lock：pywin32`，非违规）。
- **偏移量**：注入只增加**这 1 条** violation（1 条锁定 violation 之外无其它）⇒ 归因干净。
- 前置证据（历史件）：同一命令在**未注入**且缺 coverage 时也报过 lock 之外的 11 条，印证 lock 分支是**独立判定项**。

**判定**：`PASS`（注入面已实测）。**残留**（不折算 pass）：注入走的是 `--lock` **参数**，不是物理 `rm requirements.lock`——见 §5。

---

## 4. G-16① 显式锚点残留复测（`70` §5.2③ / §5.3 残留 1）

**口径**：`harness/coverage_drift.py` 是「报告型产物（`measure_coverage.py`）的判据层」：`LOCKED`（`coverage_drift.py:173-189`）= `rules_total==273` / `method_level_non_get_total>=158` / `writable_rules_non_get==156` / `writable_literal>=108` / `writable_any>=116` / `uncovered_writable==0` / `smoke 149/9` / `multi-method N=44 M=38`。缺 `--coverage` ⇒ **exit 2**（fail loud，N-1 修）。

### 4a. 复现（三条命令 + 读数）

| 命令 | exit | 读数 |
| --- | --- | --- |
| `coverage_drift.py`（**无参**） | **2** | `[USAGE] 未提供 --coverage…`；`…冻结锚点仅作历史留档、不参与判据：它记录的是 V-06/C-05 有意更新之前的 6/14/101，而 LOCKED 已按 A-70 更新为 108/116/0 ⇒ 直接套用必然假红（N-1）`；`n1_trigger = V-16 / N-1` |
| `coverage_drift.py --coverage test-reports-2026-10/evidence/harness/coverage.json`（**显式锚点**） | **1** | `[FAIL] coverage.json 不存在：test-reports-2026-10/evidence/harness/coverage.json` / `exit = 1  原因=[coverage.json 缺失]` |
| `coverage_drift.py --coverage <本次产物>`（**显式传本次产物**） | **0** | `D-1…D-7` 全 `[OK]`（`273/158/156/110/118/0/149,9`）、`D-8 SKIP`（未传 `--routes-stdout`）、`D-9 [OK] N=44 M=38 len=38` / `判据 7/8 通过… => exit 0` / `failed_checks=[]` |

**与 `70` §5.2③ 的差异（必须写清）**：`70` 当时记的读数是 **exit 1 且 `D-4=6 / D-5=14 / D-6=101`**（锚点存在、读数陈旧 ⇒ 撞 `LOCKED` 的 108/116/0）；**今日该文件已不在盘上**，故复现到的是 `coverage.json 不存在`。同一残留（显式传锚点仍 exit 1）**成立**，但证据形态已换。

**现场事实（本次实测）**：
- `test-reports-2026-10/evidence/harness/` 下只剩 3 个文件：`artifact_hashes.json`(1770 B) / `coverage-B18Q1.json`(246604 B) / `nm-B18Q1.txt`(32324 B)；**默认锚点 `coverage.json` 与头注（`coverage_drift.py:120`）声明的冻结字节归档目录 `_anchor-history/` 均不存在**。
- 锚点登记值仍在文里：`29-第2轮事实底盘.md:70` = 236893 B / `5E2C9D4315971B31C83AFD7833C310501199C34F61BFD868EF07A6AEEF7BF1F0`；`coverage_drift.py:121` 的 B13-00 重基线后值 = 244575 B / `F0D37A6C72C9029C60B4124DAC5993E1E65321448C943555381C15ECD6BDB42D`。两者今日**都无现场文件可比对**。
- `evidence/**` 被 `.gitignore:42` 忽略、从未入 git（`git log --all --diff-filter=D -- <该路径>` 为空）⇒ **不可从 git 恢复**。

### 4b. 判定：**判据正确（非缺陷）**

1. **无参通道已不静默**：缺参 ⇒ exit 2 + `n1_trigger` + 明写「直接套用必然假红」⇒ 「锚点 ≠ 门禁输入」的语义由**代码**表达，不只靠文档。
2. **显式传「陈旧产物」⇒ exit 1 是正确行为**（`--coverage` 通道本身健康）：拿**在盘上**的归档锚点 `evidence/harness/ci-run-20261009-054416/coverage.json`（246076 B / `58BF844628402AE6D87F6A0F0336049D313463E83C28DFA448BBEFD9DB21E055`）复跑 ⇒ **exit 1**，读数 = `D-2 157<158` / `D-3 155<156` / `D-7 148/9<149/9` / `D-9 len(list)=37≠38`（`D-1/D-4/D-5/D-6` OK）。即：**B18-Q1 的 A-70 重基线之后，任何早于重基线的产物都必然红**——这是闸门按设计拒收陈旧输入，不是显式传参坏了。
3. **显式传「本次产物」⇒ exit 0**（§4a 第三行）⇒ 同一通道给新产物即全绿。三点合起来：`70` §5.3「残留 1」的**定性**（只能靠文档 + 无参 fail loud 双保险）**成立且今日仍成立**；它**不是缺陷**，属「锚点与 `LOCKED` 语义互斥」的正确表达。

### 4c. 新登记事实（须转资产/口径面，不在本件处置）

**默认锚点缺失是本次新测出的资产面事实**，波及两个默认入口：
- `coverage_drift.py`：无参 ⇒ exit 2（不受影响）；**显式传默认路径**才可见缺失（§4a 第 2 行）。
- `check_doc_claims.py`：**默认无参 ⇒ exit 1 / violations=11**（§2 前置读数）——任何人直跑默认入口都会看到与自身改动无关的红。

`ci_gates` 的两步**都不走默认锚点**：步 11 `measure_coverage`（report-only）产出本次产物；步 20 `check_doc_claims` 的 argv 即 `--coverage <run_dir>/coverage.json`（见 `ci_gates.py --list`）⇒ 链不受默认锚点缺失影响。
**已存在的现成替代源（本件实测）**：`test-reports-2026-10/evidence/harness/coverage-B18Q1.json`（246604 B，sha256 前 32 位 `E8D168101A271CCBA37B42DD6906A316`）——`coverage_drift --coverage <它>` ⇒ **exit 0**（8/8 面）；`check_doc_claims --coverage <它>` ⇒ `29/29 相等` / `RESULT: OK` / **exit 0**。

---

## 5. 未测项 / 残留 / 解除条件（**一律不折算 pass**）

| ID | 状态 | 内容 | 解除条件 |
| --- | --- | --- | --- |
| U-1 | `not_measured` | G-15③ 的**物理删除** `requirements.lock` 后跑默认入口（本件受「只测不改」约束，只做了 `--lock` 参数注入） | 在仓库副本（非本工作区）`mv requirements.lock requirements.lock.bak` → 跑 `check_doc_claims.py --coverage <产物>` → 预期 exit 1 + 同一条 violation → 恢复文件并复核 `git status` 干净 |
| U-2 | `not_measured` | **默认锚点缺失的处置**（重建 `evidence/harness/coverage.json` or 把默认路径改为现存的 `coverage-B18Q1.json` → 并同步 `29` §4 / `AGENTS.md`）——属改判据路径，须走 **A-70 三步**（旧值留档 → 阴性对照先转红 → 改值 + 复跑绿 + 登记件） | 资产/口径面出裁定 + 登记件；本件已备好替代源读数（§4c） |
| U-3 | `not_covered` | `coverage_drift` 的 `D-8`（`--routes-stdout` 面）本次 `SKIP`（未传路由清单 stdout） | 复跑 `coverage_drift.py --coverage <产物> --routes-stdout <run>/route_inventory.stdout.txt`，期望 D-8 转 `[OK]` 且 exit 0 |
| U-4 | `not_covered` | `70` §5.3 残留 2（下游 `reconcile_r2.py:555` / `r2_v14_ledgerbook.py:259` 未同步）**不在本任务范围** | 由该条责任线处置；本件只测源面 |

---

## 6. 一键复跑（复制即可，全部只读 + 落 `.tmp/`）

```bash
cd /root/code/MyERP
PY=/opt/wage-venv/bin/python; RUN=test-reports-2026-10/.tmp/t3-inject-20261012

# G-15① 直测 + 阴性对照
$PY -B scripts/check_properties.py --root $RUN/tl05                  # 期望 exit 1 + bad_inst.py:6
$PY -B scripts/check_properties.py --selftest                        # 期望 exit 0（22/22）
$PY -B test-reports-2026-10/harness/ci_gates.py --inject-step check_properties   # 期望 exit 1

# G-15② 基线与注入（先出产物，再对照）
$PY -B test-reports-2026-10/harness/measure_coverage.py --no-request-probes --out $RUN/coverage.json
$PY -B scripts/check_doc_claims.py --coverage $RUN/coverage.json                              # 期望 exit 0 / 29/29
$PY -B scripts/check_doc_claims.py --coverage $RUN/coverage.json --docs $RUN/dc_clean.md       # 期望 exit 0
$PY -B scripts/check_doc_claims.py --coverage $RUN/coverage.json --docs $RUN/dc_ge135.md       # 期望 exit 1（ge135）
$PY -B scripts/check_doc_claims.py --coverage $RUN/coverage.json --docs $RUN/dc_ge139.md       # 期望 exit 1（ge139）
$PY -B scripts/check_doc_claims.py --coverage $RUN/coverage.json --docs $RUN/dc_45zhang.md     # 期望 exit 1（tables45）

# G-15③ 删 lock 面
$PY -B scripts/check_doc_claims.py --coverage $RUN/coverage.json --lock /nonexistent/requirements.lock   # 期望 exit 1

# G-16① 锚点面
$PY -B test-reports-2026-10/harness/coverage_drift.py                                              # 期望 exit 2
$PY -B test-reports-2026-10/harness/coverage_drift.py --coverage test-reports-2026-10/evidence/harness/coverage.json          # 期望 exit 1（文件不存在）
$PY -B test-reports-2026-10/harness/coverage_drift.py --coverage test-reports-2026-10/evidence/harness/ci-run-20261009-054416/coverage.json  # 期望 exit 1（陈旧产物）
$PY -B test-reports-2026-10/harness/coverage_drift.py --coverage $RUN/coverage.json                # 期望 exit 0
$PY -B test-reports-2026-10/harness/coverage_drift.py --coverage test-reports-2026-10/evidence/harness/coverage-B18Q1.json     # 期望 exit 0

# 真库三值
sha256sum app.db && stat -c '%s %y' app.db
```

---

## 7. 证据路径

| 内容 | 路径 |
| --- | --- |
| 全部 stdout 留档（原始读数） | `test-reports-2026-10/.tmp/t3-inject-20261012/`（`tl05*.txt` / `dc_*.txt` / `cd_*.txt` / `inj_*.txt` / `mc.out.txt` / `coverage.json` / `dc_*.md`） |
| G-15① 合成树 | `…/t3-inject-20261012/tl05/`（`models.py` 副本 + `bad_inst.py`） |
| harness 入口 run 产物（含声明注入的 argv/判据哈希） | `test-reports-2026-10/evidence/harness/ci-run-20261012-044128/`（步 `check_properties`）、`…/ci-run-20261012-044145/`（步 `check_doc_claims`）；`evidence_journal.jsonl` 记 console 哈希 `FBB7B0C2…1175` / `1BF87D12…0409` |

**自检面读数（旁证）**：`check_properties --selftest` 22/22 ⇒ 0；`check_doc_claims --selftest` 26/26 ⇒ 0；`coverage_drift --selftest` 11/11 ⇒ 0。

---

## 8. 硬约束遵守声明

| 约束 | 本件执行 |
| --- | --- |
| ① 禁 `flask db migrate/upgrade` | 未执行任何 `flask db *` |
| ② 真库只读 | 未以 `app.db` 为输入；操作后（04:43:10 UTC）三值逐位等于钉值；**窗口内未写入**由 mtime（`04:25:37`，早于窗口起始 `04:40`）判定——「操作前」单独读数文件未落，理由见文首口径说明；全部工具为静态扫描 |
| ③ append-only | 本件为**新增**文件；未覆盖 `docs/**` 与任何既有 `test-reports-2026-10/*.md` |
| ④ blocked/not_measured 不折算 pass | §5 U-1…U-4 明写状态 + 解除条件 |
| ⑤ 判据改动走 A-70 | **未改任何判据/钉值/期望值**；U-2 的处置被显式挡回资产面 |
| ⑥ 证据 = 工具 + 口径 + 值 | 每条 = 命令 + 口径 + stdout 关键行 + 退出码 |
| ⑦ 验证者非作者（C9） | 本件为**实测件**（非实现件的自审）；G-15①②③ 的判据文件均非本件所写 |
| ⑧ 提交白名单 / 不 push | 未 `git add`、未 `push`；`git status --porcelain` 无受跟踪改动 |
| ⑨ `ci_gates.py --phase first` exit 0 | **未跑全链**（不属本任务；本件含 2 次 `--inject-step` 单步跑，均为**故意转红**）⇒ 若下游需要全链读数，须由提交/收口责任线补 |
