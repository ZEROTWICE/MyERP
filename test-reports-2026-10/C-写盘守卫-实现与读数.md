# C-写盘守卫-实现与读数（t8：measure_coverage probe 证据写盘改走 save_evidence）

- 任务：AgentTeams `taskc-product-face` · t8（后端工程师 · 代码溢出线 impl-p2）
- 日期：2026-10-12（UTC）
- 前置事实（事故背景）：2026-10-12 04:45，`measure_coverage.py` 旧形态的裸写
  （`open(ev, 'w')`）在同 run 复跑时**原地覆盖**了 `evidence/harness/b17-verify/probe_smoke_test.txt`
  与 `probe_permission_matrix.txt`（evidence_hash 报 2 条 modified，原件字节不可恢复）。
  本任务治本点 = **写盘入口**，不改判据、不改基线。

## 1. 改动点（文件:函数:行号，本次实测）

唯一代码改动（`git diff --ignore-cr-at-eol --numstat` = `13	9	test-reports-2026-10/harness/measure_coverage.py`）：

| 位置 | 改动 |
| --- | --- |
| `test-reports-2026-10/harness/measure_coverage.py:45` | import 增补 `save_evidence`：`from _env import EVIDENCE_DIR, REPO_ROOT, ensure_dir, real_db_status, save_evidence`（`EVIDENCE_DIR` 仍被 `:421` `--out` 默认值引用，保留） |
| `test-reports-2026-10/harness/measure_coverage.py:220`（`run_request_probes`）内 `:253–261` 旧裸写块 | **删除** `ev = os.path.join(EVIDENCE_DIR, f'probe_…}.txt')` + `with open(ev,'w',…)` 形态 |
| `test-reports-2026-10/harness/measure_coverage.py:257–264` | 改为 `ev = save_evidence(f'probe_{name.replace(".py", "")}.txt', <同格式头部 + stdout + stderr>)`；`record['evidence_file'] = os.path.relpath(ev, REPO_ROOT).replace('\\','/')` 取守卫**返回的实际路径**（发生改名时即改名后路径），relpath 口径不变 |

- `_env.py` **未改**（只调用其既有 `save_evidence`/`guard_write`，硬约束）。
- `evidence/**`、`app/**`、`scripts/**`、`docs/**`、`requirements.lock` 均未动。

## 2. 验证命令与读数

### 2.1 门禁步（合同 Verify ①）

```
/opt/wage-venv/bin/python -B test-reports-2026-10/harness/ci_gates.py --only measure_coverage
```

读数（2026-10-12 05:41:05 UTC run）：

```
[ci_gates] OK   measure_coverage       group=report-only exit=0 checks 1/1
[ci_gates] steps=1 blocking 失败 = 无
[ci_gates] report-only 失败 = 无
[ci_gates] exit = 0  phase=first
```

判据满足：exit=0、报告型失败=无。原始输出已按守卫落盘
`test-reports-2026-10/evidence/harness/ci-run-20261012-054105/ci_gates_first.console.txt`。

### 2.2 守卫自检脚本（合同 Verify ②；脚本全文见附录 A）

```
/opt/wage-venv/bin/python -B test-reports-2026-10/.tmp/t8-guard/check_guard.py
```

读数（exit=0，判据全过）：

```
[t8-guard] 场景 A：不同内容二次写同名 probe（阴性对照）
  OK   ① 首写落在请求路径本身：probe_smoke_test.txt
  OK   ① 原文件 sha256 前后恒等（未被覆盖）：b262f32f590e9bdd972423b6dac5b6e2cbdb2874e9bc30806a36e764f17ebcb7
  OK   ② 新内容落到改名件 <name>.<RUN_ID>.txt：probe_smoke_test.t8-guard.txt
  OK   ② 改名件内容 = 第二版（新内容确已落盘）
[t8-guard] 场景 B：同内容重复写（幂等）
  OK   ③ 幂等：返回路径 == 首写路径（无修订版文件）：probe_smoke_test.txt
  OK   ③ 幂等：目录中不存在 `<name>.n` 修订版文件（found=无）
[t8-guard] journal 逐行（evidence_journal.jsonl，共 3 行）：
    {"ts": "2026-10-12 05:40:23", "run_id": "t8-guard", … "written": "probe_smoke_test.txt",  "renamed_by_guard": false, "reused_identical": false, "bytes": 55, "sha256": "B262F32F…EBCB7"}
    {"ts": "2026-10-12 05:40:23", "run_id": "t8-guard", … "written": "probe_smoke_test.t8-guard.txt", "renamed_by_guard": true,  "reused_identical": false, "bytes": 88, "sha256": "72D9C76A…9907"}
    {"ts": "2026-10-12 05:40:23", "run_id": "t8-guard", … "written": "probe_smoke_test.txt",  "renamed_by_guard": false, "reused_identical": true,  "bytes": 55, "sha256": "B262F32F…EBCB7"}
  OK   ③ journal 共 3 行（首写 / 异内容改名 / 同内容复用）
  OK   ③ journal 第 2 行记录改名事实（renamed_by_guard=true, written=probe_smoke_test.t8-guard.txt）
  OK   ③ journal 第 3 行记 reused_identical=true（written=probe_smoke_test.txt）
  OK   ④ relpath(REPO_ROOT) 口径不变：test-reports-2026-10/.tmp/t8-guard/run/t8-guard/probe_smoke_test.t8-guard.txt
```

对照验收第 2 条（阴性对照）：① 原文件 sha256 前后恒等 ✅；② 新内容落
`probe_smoke_test.t8-guard.txt`（`<name>.<RUN_ID>.txt`）✅；③ journal 追加行且
`renamed_by_guard=true` ✅。
对照验收第 3 条（幂等）：不产生修订版文件（返回路径 == 首写路径）✅；
journal 第 3 行 `reused_identical=true` ✅。

### 2.3 端到端实测（真实探针全跑，改造后首次）

```
HARNESS_RUN_ID=t8-probe-demo /opt/wage-venv/bin/python -B test-reports-2026-10/harness/measure_coverage.py --out test-reports-2026-10/.tmp/t8-guard/coverage.probe.json
```

读数：exit=0；`real.db unchanged = True`。两条探针证据均按守卫落**新 run 目录**：

```
test-reports-2026-10/evidence/harness/t8-probe-demo/probe_smoke_test.txt         （3192 B，journal: renamed_by_guard=false, reused_identical=false）
test-reports-2026-10/evidence/harness/t8-probe-demo/probe_permission_matrix.txt  （11240 B，journal 同上格式）
```

`coverage.probe.json` 的 `request_probe_runs.*.evidence_file` 取到的正是守卫
返回的实际路径（`…/t8-probe-demo/probe_smoke_test.txt`），与 journal `written` 字段一致。

### 2.4 零口径漂移（验收第 4 条）

改码前（基线，`HARNESS_RUN_ID=t8-before … --no-request-probes --out .tmp/t8-guard/coverage.before.json`）
与改码后（`HARNESS_RUN_ID=t8-after … --no-request-probes --out .tmp/t8-guard/coverage.after.json`）
两次 JSON `summary` 对拍：

```
summary keys before=24 after=24
diffs: NONE — 判据字段逐字一致
```

判据字段读数（前后一致）：`rules_total=273, rules_static=1, rules_get_no_arg=104,
rules_get_with_arg=56, rules_non_get=112, rules_get_only=116, method_level_total=319,
method_level_GET=161, method_level_POST=126, method_level_DELETE=20, method_level_PUT=12,
method_level_non_get_total=158, method_level_non_get_via_multi_method_rules=158,
writable_rules_non_get=156, writable_literal_covered_by_functional=8,
writable_literal_covered_by_all=110, writable_any_covered_by_functional=16,
writable_any_covered_by_all=118, function_writes_literal_covered_method_level=8,
function_writes_method_level_total=158, readable_rules_get_only=116,
readable_any_covered_by_all=17, multi_method_with_get_total=44,
multi_method_with_get_uncovered=38`。

`evidence_file` 指向差异说明：本次全跑写入的是**新 run 目录**（`t8-probe-demo/`），
属新目录新增证据（append-only，合法），`evidence_file` 因此指向新目录内路径——这是
RUN_ID 不同的自然结果，不是口径漂移；`os.path.relpath(ev, REPO_ROOT)` 的计算口径
未变（2.2 的 ④ 已旁证）。

## 3. evidence_hash 现状（验收第 5 条，blocked 处置）

实测（`/opt/wage-venv/bin/python -B test-reports-2026-10/harness/ci_gates.py --only evidence_hash`）：

- verdict = **VIOLATION（exit 1）**，`modified=2`：
  - `harness/b17-verify/probe_permission_matrix.txt`：基线 sha256 `1664B44BF5FB227B…` → 当前 `F81525C2B3CF4A5E…`（9627 B → 11234 B）
  - `harness/b17-verify/probe_smoke_test.txt`：基线 sha256 `59A7E5F065716E43…` → 当前 `DA0C377DA223D63B…`（3186 B → 3186 B）
- 该 2 条 modified 即 t8 开工前 04:45 已发生的历史覆盖（文件 mtime 04:45:16 / 04:45:29，早于本任务开工），**不是本次改动引入**；本次任务**未删除/重建/改写 `evidence/**` 下任何既有文件**。

处置（按任务书 = blocked，不折算 pass）：

- **状态：blocked** —— `evidence_hash` 步因上述 2 条 `modified` 维持红，且原件字节
  经全盘 `find / -name 'probe_*.txt'` + sha256 扫描确认不可恢复（开工前已实测）。
- **解除条件**（二选一，均须另立任务、走 A-70 三步，不由本任务顺手处置）：
  1. 人工核定后以「基线重冻结」方式吸收：跑 `harness/evidence_hash.py --freeze` 重建
     `evidence/artifact_hashes.json` 基线（只追加/重建索引），把 b17-verify 目录的
     当前字节定为新基线；须按 A-70 三步（旧值留档 → 阴性对照先转红 → 改值复跑绿 +
     登记件）执行并新建登记件。
  2. 恢复 `b17-verify/probe_*.txt` 原件字节至基线 sha256（`1664B44B…` / `59A7E5F0…`），
     若任何离线备份（磁带/异地镜像）存在；目前容器内无可用副本。

## 4. 真实库三值核对（验收第 7 条）

- 开工（2026-10-12 ~04:30 UTC）：sha256 `34e48e7a21163db390eebda4f2030343f3609afedc65d8c6e909d6eb5a49177e` / 2531328 B / mtime `2026-10-12 04:25:37.128430119 +0000` —— 与钉值恒等 ✅
- 收工（2026-10-12 05:44 UTC，`sha256sum app.db` + `stat`）：`34e48e7a21163db390eebda4f2030343f3609afedc65d8c6e909d6eb5a49177e` / 2531328 B / `2026-10-12 04:25:37.128430119 +0000` —— **恒等** ✅（全程未写过真实库；`measure_coverage` 自身每跑都带 `real.db unchanged = True` 校验）

## 5. 交付与入库清单

- 本件（新建，append-only，未覆盖任何既有文件）：`test-reports-2026-10/C-写盘守卫-实现与读数.md`
- 代码改动：`test-reports-2026-10/harness/measure_coverage.py`（`git add` 白名单逐条）
- 自检脚本：`test-reports-2026-10/.tmp/t8-guard/check_guard.py`（`.tmp/` 属 `.gitignore:41` 忽略的本地留档；按任务书「脚本与读数一并入库」要求，脚本全文收录于附录 A，读数收录于 §2.2）
- 未动：`docs/**`、`test-reports-2026-10/evidence/**`（只新增 `t8-probe-demo/`、`ci-run-20261012-054105/`、`ci-run-20261012-054122/` 三个**新** run 目录，均为守卫/journal 正常产物，未触碰既有文件）、`app/**`、`scripts/**`

## 附录 A：check_guard.py 全文（2026-10-12 实测通过版）

```python
# -*- coding: utf-8 -*-
"""t8 守卫自检：`measure_coverage.py` 的 probe 原始输出写盘已改走 `_env.save_evidence()`。

判据（验收第 2/3 条，全部**实测**、任何一条不满足即 exit 1）：

* **阴性对照（不同内容二次写同名 probe）**，在同一 run 目录下：
  ① 原文件 sha256 前后恒等（未被覆盖）；
  ② 新内容落到 `<name>.<RUN_ID>.txt`；
  ③ 同目录 `evidence_journal.jsonl` 追加一行且记录改名事实（`renamed_by_guard=true`）。
* **幂等（同内容重复写）**：
  不产生修订版文件（返回路径 == 请求路径），journal 记 `reused_identical=true`。

与 `_env.py __main__` 自检同法：把 `EVIDENCE_ROOT` 指到本脚本的隔离 run 目录（不碰
`evidence/`、不碰 `b17-verify/` 等任何既有证据目录）。写法上完全复刻
`measure_coverage.run_request_probes` 的真实调用形态（`save_evidence(f'probe_{...}.txt', text)`
+ `record['evidence_file'] = os.path.relpath(ev, REPO_ROOT)`）。

用法（仓库根目录）：

    /opt/wage-venv/bin/python -B test-reports-2026-10/.tmp/t8-guard/check_guard.py
"""
import hashlib
import json
import os
import sys

HARNESS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), 'harness')
# ^ __file__ = test-reports-2026-10/.tmp/t8-guard/check_guard.py → 上溯 3 级 = test-reports-2026-10/
REPO_ROOT = os.path.dirname(HARNESS)      # = 仓库根 /root/code/MyERP
sys.path.insert(0, HARNESS)
sys.path.insert(0, os.path.join(REPO_ROOT, 'scripts'))

RUN_ID = 't8-guard'
# 隔离 run 目录：本脚本专属 scratch（.tmp/ 不入库），每次自检前清空重来 ⇒ journal 恰为本次 3 行
ISOLATED = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'run')
import shutil
if os.path.isdir(ISOLATED):
    shutil.rmtree(ISOLATED)
os.makedirs(ISOLATED, exist_ok=True)

import _env  # noqa: E402  （import 前先改 EVIDENCE_ROOT，等同 _env.py 自检法）

_env.EVIDENCE_ROOT = ISOLATED            # 只追加纪律：绝不写入真 evidence/harness/
_env.RUN_ID = RUN_ID

from _env import REPO_ROOT as RR, EVIDENCE_JOURNAL_NAME, save_evidence  # noqa: E402

failures = []


def check(cond, msg):
    print(('  OK   ' if cond else '  FAIL ') + msg)
    if not cond:
        failures.append(msg)


def sha256_of(path):
    with open(path, 'rb') as fh:
        return hashlib.sha256(fh.read()).hexdigest()


print('[t8-guard] 隔离 run 目录 = %s（EVIDENCE_ROOT 已重定向，不碰 evidence/）' % ISOLATED)

# ── 场景 A（阴性对照）：同一 run 目录，先写 probe_x.txt，再用**不同内容**写同名 ──────────
print('[t8-guard] 场景 A：不同内容二次写同名 probe（阴性对照）')
name = 'smoke_test.py'                                   # 与真实探针同名的文件名形态
fname = f'probe_{name.replace(".py", "")}.txt'           # = probe_smoke_test.txt
text1 = ('# command: probe A v1\n--- stdout ---\nA 第一版内容\n')
text2 = ('# command: probe A v2 不同内容\n--- stdout ---\nB 第二版内容（不应覆盖 A）\n')

ev1 = save_evidence(fname, text1)                        # measure_coverage 的真实调用形态
requested = ev1                                          # save_evidence 的实际请求路径
sha1_before = sha256_of(ev1)
check(os.path.basename(ev1) == fname, '① 首写落在请求路径本身：%s' % os.path.basename(ev1))

ev2 = save_evidence(fname, text2)                        # 不同内容二次写
sha1_after = sha256_of(ev1)

check(sha1_before == sha1_after, '① 原文件 sha256 前后恒等（未被覆盖）：%s' % sha1_before)
check(os.path.basename(ev2) == f'probe_smoke_test.{RUN_ID}.txt',
      '② 新内容落到改名件 <name>.<RUN_ID>.txt：%s' % os.path.basename(ev2))
check(sha256_of(ev2) == hashlib.sha256(text2.encode('utf-8')).hexdigest(),
      '② 改名件内容 = 第二版（新内容确已落盘）')

# ── 场景 B（幂等）：同内容重复写 ─────────────────────────────────────────────────────
print('[t8-guard] 场景 B：同内容重复写（幂等）')
ev3 = save_evidence(fname, text1)                        # 与首写逐字相同
check(ev3 == requested, '③ 幂等：返回路径 == 首写路径（无修订版文件）：%s' % os.path.basename(ev3))
rev = [p for p in os.listdir(ISOLATED)
       if p.startswith(fname) and p != fname
       and RUN_ID not in p]
check(not rev, '③ 幂等：目录中不存在 `<name>.n` 修订版文件（found=%s）' % (rev or '无'))

# ── journal 逐行审计 ────────────────────────────────────────────────────────────────
journal = os.path.join(os.path.dirname(ev1), EVIDENCE_JOURNAL_NAME)
rows = [json.loads(l) for l in open(journal, encoding='utf-8') if l.strip()]
print('[t8-guard] journal 逐行（%s，共 %d 行）：' % (EVIDENCE_JOURNAL_NAME, len(rows)))
for r in rows:
    print('    %s' % json.dumps(r, ensure_ascii=False))
check(len(rows) == 3, '③ journal 共 3 行（首写 / 异内容改名 / 同内容复用）')
if len(rows) == 3:
    check(rows[1]['renamed_by_guard'] is True and rows[1]['requested'].endswith(fname)
          and rows[1]['written'] != fname,
          '③ journal 第 2 行记录改名事实（renamed_by_guard=true, written=%s）'
          % rows[1]['written'])
    check(rows[2]['reused_identical'] is True and rows[2]['written'] == fname,
          '③ journal 第 3 行记 reused_identical=true（written=%s）' % rows[2]['written'])

# ── 场景 C（零口径漂移的守卫侧旁证）：relpath 口径与 measure_coverage 一致 ────────────
rec_file = os.path.relpath(ev2, RR).replace('\\', '/')
check(rec_file.startswith('test-reports-2026-10/.tmp/t8-guard/'),
      '④ relpath(REPO_ROOT) 口径不变：%s' % rec_file)

print()
if failures:
    print('[t8-guard] FAIL（%d 条判据未过）：' % len(failures))
    for m in failures:
        print('  - %s' % m)
    sys.exit(1)
print('[t8-guard] 判据全过：阴性对照（不覆盖 + 改名保留 + journal 记录）与幂等'
      '（复用 + reused_identical=true）均实测通过')
sys.exit(0)
```
