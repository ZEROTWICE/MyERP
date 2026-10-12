# C-写盘守卫-非作者复核（t9）

**任务**：t9 [verification round 1] 非作者独立复核 t8 对 `test-reports-2026-10/harness/measure_coverage.py` 写盘路径的守卫改造（`_env.save_evidence()`）。
**执行者**：`gov-inject`（**非** t8 实现者 `impl-p2`）；attempt_id `a533bd59-1be4-43ed-9a91-51e49bb4b931`。
**性质**：只测不改 —— 本件为**新建件**（append-only），未改 `measure_coverage.py` / `_env.py` / `docs/**` / 既有 `evidence/**`。
**时点**：2026-10-12 05:40–06:0x UTC。
**结论**：**6/6 条验收全部通过**；另有 2 项**超范围观测**写于 §8，按纪律**不折算 pass**。

---

## §0 被测件与判定口径

| 物件 | 值 |
| --- | --- |
| 被测文件 | `test-reports-2026-10/harness/measure_coverage.py` |
| 工作区 sha256 / mtime | `ff0a9840c51f44cc92953444ac5da48d47ac618555b92e7c4232697cae762d5b` / `2026-10-12 05:36:11.600748481 +0000`（复核前后恒等 ⇒ 未被本任务改动） |
| 守卫实现件 | `test-reports-2026-10/harness/_env.py` sha256 `b84fa68acd4a5436f4279fc00a6e9987ea914b27ae179a9b22ae75d9e8d17431` / mtime `2026-10-12 04:29:49.820043307 +0000`（复核前后恒等） |
| 改动（`git diff HEAD`，已 staged） | `+from _env import … save_evidence`（`:45`）；探针落盘由裸写改为 `ev = save_evidence('probe_<name>.txt', …)`（`:257`）；`record['evidence_file'] = os.path.relpath(ev, REPO_ROOT).replace('\\','/')`（`:265`，**由返回值派生**） |
| 改动前（HEAD） | `with open(ev, 'w', encoding='utf-8', newline='\n') as fh:`（HEAD `:255`）= 同 run 目录二次写**原地覆盖** |

**判定口径**：本轮是「阴性对照 + 幂等 + 静态取证 + 回归」四类，判据均为**本次实测读数**，不引用实现者结论。

---

## §1 复核方法（独立性）

| 复核件 | sha256 | 与实现者件的差异（独立性所在） |
| --- | --- | --- |
| `.tmp/t9-verify/repro_guard.py`（本任务自建） | `54a84e956a3a4a6aaea38fbee1968e26d3a97c0d13b88058b16aea6d391d1c90` | 调**被测模块的真实调用点** `measure_coverage.run_request_probes()`（即 diff 改动的那段），只把「跑子进程」这一**输入**换成夹具（`_env.run_child`），**不给被测代码打补丁** |
| `.tmp/t9-verify/mc_head.py`（由版本库取出） | `6de24b5d149f78585a511f82672f0437024484a3b107ee135c484fe0f2c1455c` | `git show HEAD:…/measure_coverage.py`，**改动前**代码，用于阴性对照的「判据有效性」验证 |
| `.tmp/t9-verify/head_negative_control.py` | `0de855fae0e0075ba9fa6184d14ab75eb2fc453da7dac17b0fbb4ec16eb6a2e5` | 同一复现流程跑 HEAD 版 ⇒ 必须**转红** |
| `.tmp/t9-verify/cmp_judged.py` | `bd1d4a83c15ece1a0e8ae91177fd260d17de5b89bafc6baf042f62258eae3d2f` | 判据字段三方对照（基线取自 **t3 于 04:41 用 HEAD 版**产出的 coverage.json，独立于 t8） |
| `.tmp/t9-verify/realrun_crosscheck.py` | `570caba1fb72daeac16c873c6ae8ab2a389a384d36b2b11af520336bf029fce2` | 核对实现者**真实 run**（`t8-probe-demo`）的 journal / record / 落盘件三方一致 |
| 实现者对照脚本（**仅作交叉印证，不作为通过依据**） | `.tmp/t8-guard/check_guard.py` = `e406e72e9404d7afc001e61b1158f8199cc54aae65da4dc119bf210d455cbec3` | 直接调 `_env.save_evidence()`，不覆盖 `run_request_probes()` 调用点 |

**隔离口径**：本任务全部写入重定向到 `test-reports-2026-10/.tmp/t9-verify/run/`（`_env.EVIDENCE_ROOT` / `EVIDENCE_DIR` / `RUN_ID` 显式改写后 import 被测模块），**未往 `evidence/**` 写任何探针件**（复核：`ls evidence/harness/run-*/probe_*.txt` 仅见 2026-10-09 的历史件 + 实现者 `t8-probe-demo`）。

---

## §2 验收① 非作者身份 —— **PASS**

| 项 | 读数 |
| --- | --- |
| 命令 | `git status --porcelain -- test-reports-2026-10/harness/ scripts/`；`stat -c '%n %y' test-reports-2026-10/harness/measure_coverage.py` |
| 读数 | 被测件 mtime `05:36:11`（**早于**本任务开工 05:4x）、sha256 复核前后恒等；本任务新增/改动仅限 `.tmp/t9-verify/**` 与新建本件 |
| 判定 | PASS：本件由 `gov-inject` 执行，t8 实现者为 `impl-p2`（t8 留档 `.tmp/t8-guard/check_guard.py` 05:38 由实现者产出）；发现问题只报不改 |

---

## §3 验收② 阴性对照复测（不同内容二次写不覆盖） —— **PASS**

### 3.1 守卫版（真实调用点）—— **不覆盖**

**命令**
```
/opt/wage-venv/bin/python -B test-reports-2026-10/.tmp/t9-verify/repro_guard.py    # exit 0
```
**关键 stdout（完整留档 `.tmp/t9-verify/repro_guard.out.txt`）**
```
[t9-verify] 隔离证据根 = …/.tmp/t9-verify/run（EVIDENCE_ROOT 已重定向）
[t9-verify] 被测入口 = measure_coverage.run_request_probes（真实调用点）
  OK   ① 首写落请求路径：probe_smoke_test.txt
  OK   ② 原文件 sha256 前后恒等（未被覆盖）：5b46c54ccbfa7e51de3120bb7f7dbb4514e6eb9db10a953a9d1b6bfd66d6acda
  OK   ② 另一 probe 原文件同样恒等：1b9f6d139e022d51c4c16f868459ec06cd9bd1dd69b3f5fb1c362a756a7778ce
  OK   ② 新内容落改名件：probe_smoke_test.t9-verify.txt
  OK   ② 另一 probe 同样改名：probe_permission_matrix.t9-verify.txt
  OK   ② 改名件内容 = 第二轮新内容（含 GEN 1 内容）
  OK   ③ 幂等轮后原文件仍恒等（未被覆盖）
  OK   ③ 目录恰为 4 件（无 `.n` 修订版）
  OK   ⑤ journal sha256 对上实际落盘件 probe_smoke_test.t9-verify.txt     fd8693c4aceb52b8…
```
**口径**：两轮 `run_request_probes(True)`，夹具内容按调用次数变化（GEN 0 → GEN 1）；判定「原文件未覆盖 + 新内容进改名件 `probe_<name>.<RUN_ID>.txt` + journal 追加行」。
**判定**：PASS。

### 3.2 改动前（HEAD 版）同一流程 —— **转红（阴性对照成立）**

**命令**
```
/opt/wage-venv/bin/python -B test-reports-2026-10/.tmp/t9-verify/head_negative_control.py   # exit 0（"转红"本身是期望结果）
```
**关键 stdout**
```
  OK   ④（对照）首写落在请求路径：probe_smoke_test.txt
  OK   ①（转红）HEAD 版二次写不同内容 ⇒ 原文件被**原地覆盖**：sha 5b46c54ccbfa7e51… → fd8693c4aceb52b8…
  OK   ②（转红）HEAD 版**无**改名件（probe_smoke_test.head-neg.txt 不存在）
  OK   ③（转红）HEAD 版**无** evidence_journal.jsonl
       目录实际内容：['probe_permission_matrix.txt', 'probe_smoke_test.txt']
```
**口径**：同一夹具、同一两轮流程，仅把被测模块换成 `git show HEAD:` 的版本；隔离根 `.tmp/t9-verify/head-neg/`。
**判定**：PASS —— ① 改动前确有此缺陷（原文件被覆盖，`5b46c54c…` 丢失）；② 本任务复现判据**有检出能力**，不是空转；③ 两版逐字节交叉印证：HEAD 覆盖后的 `fd8693c4…` **正是**守卫版放进改名件 `probe_smoke_test.t9-verify.txt` 的内容（同输入、不同保留策略）。

### 3.3 实现者对照脚本（交叉印证） —— **读数一致**

**命令**：`/opt/wage-venv/bin/python -B test-reports-2026-10/.tmp/t8-guard/check_guard.py` ⇒ **exit 0**（留档 `.tmp/t9-verify/check_guard.out.txt`）
**读数**：场景 A（异内容）原文件 sha `b262f32f…` 前后恒等、改名件 `probe_smoke_test.t8-guard.txt`；场景 B（同内容）返回首写路径、无 `.n` 修订版；journal 3 行（首写 / 改名 / 复用）——与 §3.1、§4 语义一致。

---

## §4 验收③ 幂等复测（同内容重复写不产生修订版） —— **PASS**

| 口径 | 读数（`.tmp/t9-verify/repro_guard.out.txt`） |
| --- | --- |
| 第三轮夹具重置为 GEN 0（与首写**逐字相同**） | `OK ③ 幂等轮后原文件仍恒等（未被覆盖）` |
| `record['evidence_file']` | `OK ④ 幂等轮 record['evidence_file'] 回到请求路径：…/probe_smoke_test.txt` |
| 目录件数 | `OK ③ 目录恰为 4 件（无 .n 修订版）：['probe_permission_matrix.t9-verify.txt','probe_permission_matrix.txt','probe_smoke_test.t9-verify.txt','probe_smoke_test.txt']` |
| journal 第 3 行 | `{"written":"probe_smoke_test.txt","renamed_by_guard":false,"reused_identical":true,"sha256":"5B46C54C…6ACDA"}` |
| journal sha256 ↔ 实际落盘件 | `OK ⑤ journal sha256 对上实际落盘件 probe_smoke_test.txt 5b46c54ccbfa7e51…`（3 行全对） |
**判定**：PASS —— 幂等轮**复用请求路径**、`reused_identical=true`、无 `<name>.n` 修订版、无多写件。

---

## §5 验收④ 静态核对 —— **PASS**

| 判据 | 命令 | 读数 |
| --- | --- | --- |
| 无写 probe 的裸 `open(...,'w')` | `grep -n "open(" test-reports-2026-10/harness/measure_coverage.py` | `178: src = open(full, encoding='utf-8').read()`（只读）；`254:` 注释；`518: with open(args.out, 'w', …)`（**显式 `--out` 报告产物，非探针件**） |
| 改动前确实有裸写（对照） | `git show HEAD:test-reports-2026-10/harness/measure_coverage.py \| grep -n "open(ev"` | `255: with open(ev, 'w', encoding='utf-8', newline='\n') as fh:`（工作区已无此行） |
| probe 落盘走守卫 | `grep -n "save_evidence\|evidence_file" test-reports-2026-10/harness/measure_coverage.py` | `45: from _env import … save_evidence`；`257: ev = save_evidence(f'probe_{name.replace(".py","")}.txt',`；`265: record['evidence_file'] = os.path.relpath(ev, REPO_ROOT).replace('\\','/')` |
| `evidence_file` 由 `save_evidence()` 返回值派生 | 同上 + 实测 | `:257` 赋值、`:265` 由**同一变量** `ev` 派生；实测两轮方向正确：改名轮 `evidence_file` 指向 `probe_smoke_test.t9-verify.txt`，幂等轮回到 `probe_smoke_test.txt`（§3.1/§4） |
**判定**：PASS。

---

## §6 验收⑤ 回归核对（`ci_gates` + 判据字段对照） —— **PASS**

### 6.1 门禁入口

**命令**：`/opt/wage-venv/bin/python -B test-reports-2026-10/harness/ci_gates.py --only measure_coverage`
**读数**：
```
[ci_gates] OK   measure_coverage       group=report-only exit=0 checks 1/1
[ci_gates] steps=1 blocking 失败 = 无
[ci_gates] report-only 失败 = 无
[ci_gates] exit = 0  phase=first
[ci_gates] 原始输出已落盘（写入守卫 + 台账）-> …/evidence/harness/ci-run-20261012-055023/ci_gates_first.console.txt
```
⇒ **exit 0**，报告型失败列表 = **无**（该步 `report-only`，判据取自 `expect_exit=0`）。

### 6.2 `coverage.json` 判据字段与改动前对照

**命令**：`/opt/wage-venv/bin/python -B test-reports-2026-10/.tmp/t9-verify/cmp_judged.py <本次 run>/coverage.json` ⇒ **exit 0**
**口径**：字段组 = `summary` + `conventions` + `comparison` + `routes`/`probes`/`uncovered_*` 长度，逐字段相等即通过。**A（改动前基线，独立）= t3 于 04:41 用 HEAD 版产出的 `.tmp/t3-inject-20261012/coverage.json` sha256 `291571bd…`；B（现状）= 本次 `ci-run-20261012-055023/coverage.json` sha256 `ed5aafce…`；C = 实现者留档 `coverage.before/after.json`**
```
  OK   ① A vs B：判据字段逐字段相等（9 个字段组）
  OK   ① A vs C-before：判据字段逐字段相等
  OK   ① B vs C-after：判据字段逐字段相等
```
**判据值（来源 B）**：`rules_total=273`、`rules_non_get=112`、`rules_get_only=116`、`method_level_total=319`、`method_level_non_get_total=158`、`method_level_non_get_via_multi_method_rules=158`、`writable_rules_non_get=156`、`routes=273`、`uncovered_get_only=100`、`uncovered_writable=0`、`uncovered_multi_method_with_get=38`、`comparison.matches_A/B=False`（`reference_08_says=155` 为**改动前既有**口径差，三份产物一致 ⇒ **非本次回归**）。
**判定**：PASS —— 改动未触碰任何判据值。

### 6.3 实跑侧三方一致（真实 run，非隔离）

**命令**：`/opt/wage-venv/bin/python -B test-reports-2026-10/.tmp/t9-verify/realrun_crosscheck.py` ⇒ **exit 0**（留档 `.tmp/t9-verify/realrun_crosscheck.out.txt`）
**读数**：`t8-probe-demo`（impl-p2 实跑）journal 2 行 —— 实测 `CCF4C561…`/3192 B、`C8A6D439…`/11240 B 与 journal 记录**逐字节相等**；`record['evidence_file']`（`test-reports-2026-10/evidence/harness/t8-probe-demo/probe_{smoke_test,permission_matrix}.txt`）均为**仓库根相对**路径且文件存在；record 与 journal 的落盘件集合一致。
**判定**：PASS（`record['evidence_file']` 指向**实际写入**路径，此点在实跑与隔离两侧均成立）。

---

## §7 验收⑥ append-only + 真库三值 —— **PASS**

| 项 | 命令 | 读数 |
| --- | --- | --- |
| 本件为新建件 | `ls test-reports-2026-10/C-写盘守卫-非作者复核.md`（复核前） | `No such file`（无覆盖） |
| `docs/**` / 既有 `evidence/**` 未动 | `git status --porcelain -- docs test-reports-2026-10/evidence` | 空 |
| 真库三值（开工 + 中途 + 收工） | `sha256sum app.db; stat -c '%s %y' app.db` | `34e48e7a21163db390eebda4f2030343f3609afedc65d8c6e909d6eb5a49177e` / `2531328` / `2026-10-12 04:25:37.128430119 +0000` —— **三值三次恒定**（与钉值一致；本复核脚本均不建 DB 连接） |
**判定**：PASS。

---

## §8 观测与未覆盖项（**不折算 pass**，附解除条件）

| id | 状态 | 观测（工具 + 口径 + 值） | 解除条件 |
| --- | --- | --- | --- |
| O-1 | `not_covered`（**超本次改造范围**） | `measure_coverage.py:421` `--out` 默认 = `os.path.join(EVIDENCE_DIR, 'coverage.json')`，`:518` 仍是**裸 `open(args.out,'w')`** ⇒ 若两次运行共用同一 `RUN_ID`，`coverage.json` 会被原地覆盖（与 t8 修掉的是**同一类**缺陷，只是对象是报告产物而非探针件）。本次 `ci_gates` 步传 `--no-request-probes` 且 run 目录按时间戳新建，实测 `evidence/harness/run-20261012-055023/` 为空、`ci-run-20261012-055023/` 新建 ⇒ **当前不触发** | 若后续引入固定 `HARNESS_RUN_ID` 复用 run 目录，或 `coverage.json` 进入 `evidence_hash` 白名单，则须同法改走 `save_evidence()` 或强制传 `--out`（届时按 A-70 三步处置） |
| O-2 | `not_measured`（**门禁步覆盖面**） | `ci_gates.py:913-917` 的 `measure_coverage` 步 argv = `… measure_coverage.py --no-request-probes` ⇒ **CI 门禁从不执行探针写盘路径**，该路径只有人工/专项 run（如 `t8-probe-demo`、本任务隔离 run）才会走到。这正是 2026-10-12 04:45 `b17-verify/` 覆盖事故能逃过门禁的原因 | 若要求门禁常态执法该路径，需新增一步（如 `--run-probes` 的专项步）并把「探针件不覆盖」纳入其判据；本任务无此授权，**未做** |
| O-3 | 说明（非缺陷） | 本任务复现脚本首轮曾报 4 条 FAIL，经定位**全部为本脚本自身缺陷**（`REPO_ROOT` 少一层目录、改名件内容期望值口径错、目录列举前缀过滤错），修好后转绿；实现者代码未改一行。留档：`repro_guard.out.txt`（终版）+ 本件 §3.1 | 无需解除（已闭环）；记录目的在于说明判据确实在比较，而非恒真 |

---

## §9 工件清单（sha256）

| 工件 | sha256 |
| --- | --- |
| 被测 `harness/measure_coverage.py`（工作区） | `ff0a9840c51f44cc92953444ac5da48d47ac618555b92e7c4232697cae762d5b` |
| `harness/_env.py`（工作区） | `b84fa68acd4a5436f4279fc00a6e9987ea914b27ae179a9b22ae75d9e8d17431` |
| `.tmp/t9-verify/repro_guard.py` | `54a84e956a3a4a6aaea38fbee1968e26d3a97c0d13b88058b16aea6d391d1c90` |
| `.tmp/t9-verify/head_negative_control.py` | `0de855fae0e0075ba9fa6184d14ab75eb2fc453da7dac17b0fbb4ec16eb6a2e5` |
| `.tmp/t9-verify/mc_head.py`（HEAD 版） | `6de24b5d149f78585a511f82672f0437024484a3b107ee135c484fe0f2c1455c` |
| `.tmp/t9-verify/cmp_judged.py` | `bd1d4a83c15ece1a0e8ae91177fd260d17de5b89bafc6baf042f62258eae3d2f` |
| `.tmp/t9-verify/realrun_crosscheck.py` | `570caba1fb72daeac16c873c6ae8ab2a389a384d36b2b11af520336bf029fce2` |
| A 基线（改动前）`.tmp/t3-inject-20261012/coverage.json` | `291571bd4a23abc60cd57ca89de65905737ded4774394307860478be19deb4a6` |
| B 现状 `evidence/harness/ci-run-20261012-055023/coverage.json` | `ed5aafce5e0a0c02b1e5750a32413ed37b4b4ad86eff991600ad1ce346061d49` |
| C`.tmp/t8-guard/coverage.before.json` / `.after.json` | `f8ec7d64dd7ffa877bea5f9aba0a9d2932d83f603b82e9ab6dd7a88122a49e44` / `c20c998100a7ed6c789f5a21e7d6fe521757795fe603119eb459a4b3c537ac2e` |
| C`.tmp/t8-guard/coverage.probe.json`（实跑） | `7edb9d761f199996a0708996a51e9b0a0f17f3abe300fc0be7779862111382ec` |
| 输出留档（4 份 `.out.txt`） | `.tmp/t9-verify/{repro_guard,check_guard,head_negative_control,realrun_crosscheck,cmp_judged}.out.txt` |

> 说明：`.tmp/**` 与 `evidence/**` 均被 `.gitignore` 覆盖（本地留档，不随提交），本件为唯一提交面。

---

## §10 复跑命令（逐条可复现）

```bash
cd /root/code/MyERP
# ② 守卫版：不覆盖 + 改名 + journal           （期望 exit 0，判据全过）
/opt/wage-venv/bin/python -B test-reports-2026-10/.tmp/t9-verify/repro_guard.py
# ② 阴性对照：HEAD 版同一流程 ⇒ 转红          （期望 exit 0 = 缺陷复现成功）
/opt/wage-venv/bin/python -B test-reports-2026-10/.tmp/t9-verify/head_negative_control.py
# ② 实现者对照脚本（交叉印证）                （期望 exit 0）
/opt/wage-venv/bin/python -B test-reports-2026-10/.tmp/t8-guard/check_guard.py
# ⑤ 门禁入口                                  （期望 exit 0，report-only 失败=无）
/opt/wage-venv/bin/python -B test-reports-2026-10/harness/ci_gates.py --only measure_coverage
# ⑤ 判据字段对照                              （期望 exit 0）
/opt/wage-venv/bin/python -B test-reports-2026-10/.tmp/t9-verify/cmp_judged.py \
    test-reports-2026-10/evidence/harness/ci-run-20261012-055023/coverage.json
# ⑤ 实跑侧三方一致                            （期望 exit 0）
/opt/wage-venv/bin/python -B test-reports-2026-10/.tmp/t9-verify/realrun_crosscheck.py
# 真库三值（每次操作前后）
sha256sum app.db && stat -c '%s %y' app.db
```

**逐条判定汇总**：① 非作者身份 PASS｜② 阴性对照 PASS｜③ 幂等 PASS｜④ 静态核对 PASS｜⑤ 回归核对 PASS｜⑥ append-only + 真库三值 PASS ⇒ **6/6 PASS**；O-1/O-2 保持 `not_covered`/`not_measured`（§8 解除条件），**不计入通过数**。
