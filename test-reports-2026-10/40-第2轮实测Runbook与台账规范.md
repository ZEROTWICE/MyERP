# 40 第2轮实测 Runbook 与台账规范（MyERP 第2轮 · t6）

| 项目 | 值 |
| --- | --- |
| 产出任务 | `t6` 第2轮实测 runbook 与台账规范（attempt `ae626d3d-d4c4-4fb0-a9fe-011f3b5c0870`） |
| 产出人 | 测试流程优化工程师 |
| 产出时间 | 2026-10-07（本机） |
| 工作目录 | `D:\workspace\wage_management_system - bak` |
| Python | `F:\Miniconda\envs\wage\python.exe` = 3.9.21（`flask 3.1.2` / `sqlalchemy 2.0.44`） |
| 生产面冻结 | `git rev-parse HEAD:app` = `c8f7d4abca1567b6219dbd77f22c82722f877ad6`（**与 t1 冻结值恒等**） |
| 真实库 `app.db` | `2531328 B` / SHA256 `F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065`（本文实跑前后各复核一次，未变） |
| 上游输入（权威顺序） | [`29-第2轮事实底盘.md`](29-第2轮事实底盘.md) → [`28-第2轮执行纪律.md`](28-第2轮执行纪律.md) → [`30-第2轮测试方案.md`](30-第2轮测试方案.md) → [`27-38条对账与阶段A终态冻结.md`](27-38条对账与阶段A终态冻结.md) |
| 阶段一前身 | [`phase1-snapshot/07-实测Runbook与台账规范.md`](phase1-snapshot/07-实测Runbook与台账规范.md)（**本文是它的第2轮接续，不是重写**） |
| 只读声明 | **未修改任何生产代码 / 模板 / 配置 / `scripts/` 既有脚本**；新增仅 `harness/t6_runbook_selftest.py` 与本文档族；真实库只读 |

> **本文的定位**：`29` 回答「第2轮要打哪些靶」；`28` 回答「判定口径怎么算数」；**本文回答「怎么跑、跑出的东西落哪里、落成什么形状才能被第三方复算」**。
> 本文所有命令都是 **PowerShell 7（pwsh）** 可直接粘贴执行的形态；凡本文自己实跑过的，标 `【已实测】` 并给证据；凡未实测的，标 `【未实测】` 并写明原因。**两者不得混排。**

---

## 0. 与第1轮的差异（先读这 8 条，否则会照抄过时的东西）

| # | 第1轮（`phase1-snapshot/07`） | 第2轮（本文） | 依据 |
| --- | --- | --- | --- |
| **D-1** | 证据等级三档（实测 / 源码级 / 未实测），后补 `E-3 归因` | **改用 `evidence_kind` 四值分级**：`file_exists` / `content_mention` / `content_implementation` / `behavior_verified`；**只有后两者够 `HIT`** | `28` §1 |
| **D-2** | 判定四值：`通过` / `部分` / `失败` / `不可判定` | **改用第2轮四档**：`HIT` / `PARTIAL` / `NOT_DONE` / `MISS`（新增 `NOT_DONE`，**不再与 `MISS` 混用**） | `28` §1；`29` §2–§3 |
| **D-3** | 搜索域只写「搜了什么」 | **搜索域必须声明「搜目录 / 搜文件名还是内容 / 排除了什么」，且强制输出 `EXCLUDE_BASENAMES`**（含判定脚本**自身**） | `28` §2.A-74 自指性假阳性 |
| **D-4** | 覆盖类只报「覆盖数」 | **覆盖类必须给「前后两个数 + 产生它的文件」**，并回答「删掉它什么会变红」 | `28` §3.A-73 |
| **D-5** | `_evidence/` 手工归档（`docs/` 子树，且已确认**拒绝 shell 落盘**） | **归档走 `_env.save_evidence()` API**（`guard_write` 改名保留 + `evidence_journal.jsonl` 审计）；**且 `evidence/` 已被 gitignore** | 本文 §2.3【已实测】 |
| **D-6** | `RUN_ID` 由人工命名（`2026-10-06-t7`） | **`RUN_ID` 由环境变量 `HARNESS_RUN_ID` 驱动**，未设时取时间戳；**每个实测任务一个 `RUN_ID`，全程复用** | `_env.py:36` |
| **D-7** | `--no-dump` 尚不存在（P-1 为待办） | **已落地**：`smoke_test` / `permission_matrix` 支持 `--no-dump`，且 `ci_gates` 的请求型步骤**强制**带它 | `ci_gates.py:84/89`；`29` §5 |
| **D-8** | 静态门禁 5 项 | **静态门禁 6 项**（新增 `check_model_refs`，TL-01），且 `ci_gates` 共 **11 步** | `29` §5；本文 §3.2 表 |

> ⛔ **不要照抄第1轮的这三个做法**：① 用「`evidence_level = E-1`」表示判定可信度（本轮改 `evidence_kind`）；② 用 `Tee-Object $ev/xxx.txt` 往 `_evidence/` 落盘（沙箱拒绝，静默失败）；③ 把 `evidence/**.json` 里的**度量产物**当作「新增覆盖」的证明（`28` §2.1 明令排除）。

---

## 1. 六条铁律（违反其中任何一条，该批结论作废）

| # | 铁律 | 可判定判据 | 本项目已发生过的真实事故 |
| --- | --- | --- | --- |
| **R-1** | **真实库零改动** | 每批**开工前**与**全部命令跑完后**各跑一次 `_env.assert_real_db_untouched()`（或 `Get-FileHash app.db`），两次都必须 = `F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065` | 真实库 SHA256 曾因 `create_app()` 启动自愈写到当前库而从 `BD18DA81…` 变为 `F5DA2306…`（`phase1-snapshot/07` R-1） |
| **R-2** | **一切数据级验证只走三类授权通道**：① `_test_bootstrap.make_app()` 副本 ② `file:app.db?mode=ro` 只读连接 ③ `_env.tmp_dir()` 隔离目录 | 命令里出现 `sqlite:///` 或任何写操作时，**必须能指出**它落在副本/临时目录上 | 同 R-1 |
| **R-3** | **禁止 `flask db migrate`**；`flask db *` 前先把 `DATABASE_URL` 指向目标库 | 命令历史里不得出现 `flask db migrate`；`flask db *` 命令块第一行必须是显式 `$env:DATABASE_URL=...` | 自动生成迁移会把 31 张不在迁移历史里的表纳入，产生与线上库冲突的脚本 |
| **R-4** | **解释器一律写绝对路径** `F:\Miniconda\envs\wage\python.exe`；**禁止裸 `python`** | 台账 `env.python` 填绝对路径；`commandsRun` 出现裸 `python` ⇒ 该行**判无效**（降级为 `未实测`） | PATH 上的 `python` 是 `C:\Users\Richard Zhang\.conda\pkgs\python-3.9.21-h8205438_1\python.exe`（**同版本号**，`python -V` 自检发现不了，但 `import flask` 报 `ModuleNotFoundError`）【已实测，见 §7.1】 |
| **R-5** | **读退出码禁止走 PowerShell 管道**（管道会覆盖 `$LASTEXITCODE`）；编码：子进程强制 UTF-8，控制台行 ASCII 安全（`⇒`→`=>`） | 命令块形如 `& $py ... > f 2> f; $rc = $LASTEXITCODE`，**不接管道** | `28` §5-2/§5-3；A-1/X-13、A-14/A-60 |
| **R-6** | **未验证不得计为通过**：`blocked` / `unexecuted` / `not_covered` 必须**显式登记**并写明交哪一波次 | 台账 `results[].evidence_kind` 为 `file_exists`/`content_mention` 的条目**不得**出现在 `HIT` 计数里 | `28` §7 |

> **R-4 的正确自检**（替代「`python -V` 就算通过」）：
> ```powershell
> & $py -c "import flask, sqlalchemy; print(flask.__version__, sqlalchemy.__version__)"   # 期望 3.1.2 2.0.44，exit 0
> ```

---

## 2. 证据通道（第2轮的唯一合法落盘路径）

### 2.1 四个通道

| 通道 | 形态 | 本次实测 | 边界 |
| --- | --- | --- | --- |
| **CH-0 原生** | `& $py -B scripts/<x>.py` | 纯静态 4 项可行（`check_templates` / `check_migration_heads` / `check_properties` / `check_model_refs`） | **不可**作为「脚本已通过」的唯一依据 |
| **CH-1 只读连接** | `sqlite3.connect('file:app.db?mode=ro', uri=True)` | ✅ 可用 | 只能读 |
| **CH-2 副本夹具** | 探针 `.py` + `_test_bootstrap.make_app()`，或 `_env.db_copy(tag)` | ✅ 可用 | 是**唯一**能做数据级测试（写入/造夹具/差分）的通道 |
| **CH-3 垫片** | `& $py -B scripts/_sandbox_compat.py scripts/<x>.py` | ✅ 依赖 `mkdtemp` 或子进程管道的脚本**必须**走这条 | 只放宽「临时目录 mode」与「子进程输出通道」，**不能让「覆盖写已存在文件」变可能** |

**垫片的两个硬限制**（`scripts/_sandbox_compat.py`，第1轮已踩）：
1. **只接受脚本文件路径，不接受 `-c`**（`FileNotFoundError: ...\-c`）；
2. **会 `os.chdir(dirname(被测脚本))`**（`_sandbox_compat.py:82`）⇒ 被测脚本里相对路径的基准 = **脚本所在目录**，不是 shell 的 cwd。**不要**把脚本复制到别处再跑（`_test_bootstrap.ROOT` 会跟着变 ⇒ `FileNotFoundError: <新目录>\app.db`）。

### 2.2 ⭐ 第2轮的证据落盘 API（`_env.save_evidence`）——**唯一合法写法**

```python
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))     # harness/ 或探针目录
sys.path.insert(0, r'D:\workspace\wage_management_system - bak\test-reports-2026-10\harness')
import _env

p = _env.save_evidence('my-run-verdict.json', json.dumps(obj, ensure_ascii=False, indent=1))
# 落点：test-reports-2026-10/evidence/harness/<HARNESS_RUN_ID>/my-run-verdict.json
# 目标已存在 => 自动改名 <name>.<run_id>.json（绝不覆盖），并向同目录 evidence_journal.jsonl 追加一行
```

| 项 | 规则 |
| --- | --- |
| `RUN_ID` 来源 | 环境变量 `HARNESS_RUN_ID`；**未设则取时间戳 `run-YYYYmmdd-HHMMSS`**（`_env.py:36`）⇒ 实测任务必须显式设，否则 run 目录不可预期 |
| 默认落点 | `evidence/harness/<RUN_ID>/`；`subdir=` 可指到 `evidence/harness/<subdir>/`（**仍不在平铺层**） |
| 绝不覆盖 | `guard_write()`：目标已存在 ⇒ 写 `<base>.<run_id><ext>`，必要时 `.1` `.2`；**原文件一字不动** |
| 审计流水 | 每次落盘向同目录 `evidence_journal.jsonl` **追加**一行（`ts` / `requested` / `written` / `renamed_by_guard` / `bytes` / `sha256`） |
| 历史平铺层 | `evidence/harness/*.json`（t2–t5 制片）是**只读**层，新写入不得落在这一层 |

**本契约【已实测】**（探针 `harness/t6_runbook_selftest.py`，`HARNESS_RUN_ID=r2t6-runbook`）：

| 断言 | 实测结果 | 证据 |
| --- | --- | --- |
| 同名第二次落盘被改名 | 第 1 次 → `.../r2t6-runbook/t6-guard-probe.txt`；第 2 次 → `.../t6-guard-probe.r2t6-runbook.txt` | `evidence/harness/r2t6-runbook/t6-guard-probe.txt` + `.r2t6-runbook.txt` |
| 第 1 次内容**未被覆盖** | 第 1 个文件内容仍为 `first write\n` | 同上 |
| 审计流水每写一次追加一行 | `journal_lines = 2`，第 2 行 `renamed_by_guard = true` | `evidence/harness/r2t6-runbook/evidence_journal.jsonl` |
| 守卫零副作用（真实库） | 前后 SHA256 均 = 钉死值，`real_db_unchanged = true` | 探针 stdout（`real_db_before/after`） |
| 平铺层未被触碰 | `evidence/harness/t6-guard-probe.txt` **不存在** | `legacy_layer_untouched = true` |

复跑命令（**一条，含前置环境变量**）：
```powershell
$py = 'F:\Miniconda\envs\wage\python.exe'
$env:HARNESS_RUN_ID = 'r2t6-runbook'
Set-Location 'D:\workspace\wage_management_system - bak'
& $py -B test-reports-2026-10\harness\t6_runbook_selftest.py    # exit 0 = 五项断言全过
```

### 2.3 ⚠ 三条环境事实（会静默毁掉证据，逐条实测）

| # | 事实 | 判据 / 实测 | 处置 |
| --- | --- | --- | --- |
| **E-1** | 沙箱**禁止覆盖写已存在文件**（无论路径归属） | `smoke_test.py` / `permission_matrix.py` 收尾写仓库根已存在 JSON ⇒ `PermissionError`；最小探针 `open('../<新名>.json','w')` **成功** ⇒ 否决「相对路径算错」 | 一切落盘走 `save_evidence`（新文件或自动改名）；请求型脚本一律 `--no-dump` |
| **E-2** | 沙箱**拒绝 shell 在 `docs/` 子树落盘** | `Set-Content` / `Add-Content` / `Out-File` / `New-Item` 在 `docs/` 下 `Access denied`，同命令在 `.analysis-scratch/` 正常 | 第2轮产出**一律写 `test-reports-2026-10/`**，不再写 `docs/` 树（`00-编号登记册` §4-7）；证据走 §2.2 API |
| **E-3** | ✅ **`evidence/` 已被 gitignore** | `.gitignore:41-42` = `/test-reports-2026-10/.tmp/`、`/test-reports-2026-10/evidence/`；`git ls-files test-reports-2026-10/.tmp` = **0** 条 | 证据不污染 `git status`；但**也不受 git 保护** ⇒ 归档必须自证（`save_evidence` + 审计流水 + `artifact_hashes.json`）。第1轮「证据在 `docs/` 下属跟踪范围」的说法**在第2轮不成立** |

> ⚠️ **E-3 的直接影响**：`git status` 干净**不能**证明「没有产出证据」。第2轮的「污染检查」要分两问：
> ① `git status --short` 里是否只有**有意**的生产面/文档改动；② `evidence/harness/<RUN_ID>/` 是否**只增不改**（看 `evidence_journal.jsonl` 的 `renamed_by_guard` 与 `bytes`）。

---

## 3. 命令级 Runbook（逐条：命令 / 期望 / 失败判读 / 采数）

### 3.1 开工前置（每次开工先跑，60 秒）【已实测】

```powershell
$py = 'F:\Miniconda\envs\wage\python.exe'          # R-4：绝对路径
Set-Location 'D:\workspace\wage_management_system - bak'
$env:HARNESS_RUN_ID = '<本任务的 run_id>'          # 如 r2-exec-w6-c01
$env:PYTHONIOENCODING = 'utf-8'

# ① 解释器自检（不要用 `python -V`）
& $py -c "import flask, sqlalchemy; print(flask.__version__, sqlalchemy.__version__)"   # 期望 3.1.2 2.0.44
# ② 生产面冻结（与 t1 冻结值恒等）
git rev-parse HEAD:app        # 期望 c8f7d4abca1567b6219dbd77f22c82722f877ad6
# ③ 真实库指纹（开工）
& $py -c "import sys;sys.path.insert(0,r'test-reports-2026-10/harness');import _env;print(_env.assert_real_db_untouched('开工'))"
# ④ 工作区（只应有本批有意改动）
git status --short
```

| 实测值（2026-10-07，本机） | |
| --- | --- |
| HEAD | `10d06173674013115b98ce9743b4b601f79ad111` |
| `HEAD:app` tree | `c8f7d4abca1567b6219dbd77f22c82722f877ad6`（**= t1 冻结值**） |
| `app.db` | `2531328 B` / `F5DA2306…0E0F065` |
| 解释器 | `F:\Miniconda\envs\wage\python.exe`（`flask 3.1.2` `sqlalchemy 2.0.44`，exit 0） |
| 裸 `python` | `C:\Users\Richard Zhang\.conda\pkgs\python-3.9.21-h8205438_1\python.exe` ← **错误解释器** |

> ⚠️ **HEAD 是测量时点，不是基线**。t1 期间 HEAD 被推进 18 次；本轮 2026-10-07 实测期间亦从 `6fe8603` → `10d0617`。
> **凡「未漂移」的断言一律用 `HEAD:<path>` tree 与文件级 SHA256，不要用 HEAD。** 理由与依据见 `27` 的终态冻结节。

### 3.2 静态门禁 6 项（全批次必跑）

| # | 命令 | 期望输出（逐字） | 失败判读 |
| --- | --- | --- | --- |
| 1 | `& $py -B scripts/check_templates.py` | `parsed 87 files` / `44 declared / 40 used in templates / 44 used on routes` / `landing 5` / `RESULT: OK`，**exit 0** | 有违规 ⇒ 先修模板/权限，**不许改期望值** |
| 2 | `& $py -B scripts/check_migration_heads.py` | `HEADS=['p1nonctarget']` / `head_count=1` / `revisions=35`，**exit 0** | 多 head ⇒ 迁移链被破坏 |
| 3 | `& $py -B scripts/check_properties.py` | `已扫描 23 个文件，模型类 74 个` / `RESULT: OK`，**exit 0** | 命中即「`@property`/不存在的列当列用」 |
| 4 | `& $py -B scripts/check_model_refs.py` | `[model_refs] scanned 23 files, name_query_refs 602, violations 0` / `RESULT: OK`，**exit 0** | ⚠ **勿钉 `name_query_refs` 计数**（TL-01 判据只挂 `violations 0` + `RESULT: OK`）【已实测】 |
| 5 | `& $py -B scripts/_sandbox_compat.py scripts/route_inventory.py` | `total rules=271` / `duplicate (method,path) registrations=0` / `GET no-arg=… GET with-arg=… non-GET=…`，**exit 0** | 数字漂移 ⇒ 路由新增/丢失；`duplicate>0` ⇒ 端点重复注册 |
| 6 | `& $py -B scripts/_sandbox_compat.py scripts/check_db_bootstrap.py` | `64 账号` / `直接拷贝 6712 行，跳过 0 张表` / `OK: 空库自举、幂等、无种子库跳过、整表无遗漏 均通过`，**exit 0** | `跳过 N 张表` ⇒ 整表插入失败；`首次 64 / 再次 64` 不等 ⇒ 幂等被破坏 |

**编号 1–4 原生与垫片均可**（纯静态、不建临时目录）；**编号 5–6 必须垫片**（`make_app()` → `mkdtemp` 0o700）。

### 3.3 ⭐ 单一入口：`ci_gates.py`（第2轮**首选**，替代逐条手工敲）

```powershell
$py = 'F:\Miniconda\envs\wage\python.exe'
$env:HARNESS_RUN_ID = '<run_id>'
Set-Location 'D:\workspace\wage_management_system - bak'
& $py -B test-reports-2026-10\harness\ci_gates.py --phase first --json test-reports-2026-10\.tmp\<run_id>\ci_gates_first.json
$rc = $LASTEXITCODE     # 不接管道（R-5）
```

**退出码语义**（`ci_gates.py` docstring）：`0` = 全部 blocking 通过；`1` = 有 blocking 失败**或**仓库根 JSON 被写；`2` = 仅 report-only 失败。

**【已实测】第2轮开工读数（2026-10-07，`HARNESS_RUN_ID=r2t6-runbook`）：exit 0，11/11 步 OK**

| 分组 | 步骤（checks） | 结果 |
| --- | --- | --- |
| **blocking(8)** | `check_templates`(5/5) · `check_migration_heads`(4/4) · `check_properties`(3/3) · `check_db_bootstrap`(4/4) · `run_gates`(4/4) · `functional_test`(2/2) · `permission_matrix`(3/3) · `coverage_drift`(2/2) | 全 OK |
| **report-only(3)** | `smoke_test`(3/3) · `route_inventory`(3/3) · `measure_coverage`(1/1) | 全 OK |
| 汇总 | `blocking_failed = []` · `report_only_failed = []` · `root_json_untouched = true` | exit **0** |

原始输出归档（`save_evidence` 自动落盘）：`evidence/harness/ci-r2t6-runbook/ci_gates_first.console.txt`。

> ⚠️ **【已实测】两处必须点名的口径**（第2轮开工即发现，执行者**不得**读错）：
> 1. **`run_gates` 自身 exit = 1**，而 `ci_gates` 判它 `OK`（4/4）。**这是 A-62 的预期行为，不是失败**：`run_gates` 的退出码含环境依赖探针，blocking 判据取 `gates.json` 的非环境依赖部分。
> 2. **`route_inventory_native_probe: native_exit=0 expected=1 verdict=unexpected`** ⇒ **A-62 的「原生必失败」探针在第2轮开工时已被环境漂移推翻**（第1轮该探针 native_exit=1）。**处置见 §8-C-3**：登记为环境态变化，**禁止**重基线化（A-62 明令），**禁止**据此改判任何门禁。

### 3.4 请求型 / 功能型脚本（`--no-dump` 已落地）

| # | 命令 | 期望 | 采数要点 |
| --- | --- | --- | --- |
| 7 | `& $py -B scripts/_sandbox_compat.py scripts/functional_test.py` | `结果：109 通过 / 0 失败`，**exit 0** | exit 可信 |
| 8 | `& $py -B scripts/_sandbox_compat.py scripts/permission_matrix.py --no-dump` | `[OK] 匿名可访问 = 0`，**exit 0**，且**不出现** `[WARN] 落盘失败` | 缺席断言：出现 `[WARN] 落盘失败` ⇒ **不是「绿」而是「没红」** |
| 9 | `& $py -B scripts/_sandbox_compat.py scripts/smoke_test.py --no-dump` | `无 5xx / 异常 / 重定向死循环`，**exit 0**，且**不出现** `[WARN] 落盘失败` | 同上；`smoke_test` 在 `--phase first` 为 **report-only** |

**硬规则（A-11）**：进链的请求型脚本**必须** `--no-dump`；**禁止**让「写仓库根 JSON」参与退出码。`ci_gates` 已强制。

### 3.5 报告型脚本（退出码不作判据，产物交由判据层）

| 脚本 | 命令 | 产物 | 判据层 |
| --- | --- | --- | --- |
| `route_inventory.py` | 见 §3.2 编号 5 | stdout | `coverage_drift --routes-stdout` 的 D-8 |
| `measure_coverage.py` | `& $py -B test-reports-2026-10\harness\measure_coverage.py --no-request-probes --out <run_dir>\coverage.json` | `coverage.json` | `coverage_drift --coverage <run_dir>\coverage.json` |
| `coverage_drift.py` | `& $py -B test-reports-2026-10\harness\coverage_drift.py --selftest` | `9/9 通过` | 自检即判据【已实测 exit 0】 |

> **报告型的正确读法**：`measure_coverage` 产出的 `coverage.json` 是**度量结果**，**不是**「新增覆盖」。`28` §2.1 明令把它从「已做」的证据域中排除。

### 3.6 回归复验专用：`regression_preflight.py`（**复跑前必跑 preflight**）

```powershell
$py = 'F:\Miniconda\envs\wage\python.exe'
& $py -B test-reports-2026-10\harness\regression_preflight.py preflight   # 归档 evidence/** + 写 manifest
# ... 执行业务复跑 ...
& $py -B test-reports-2026-10\harness\regression_preflight.py verify      # 任一 modified/deleted 即 exit 1
```

| 项 | 事实 |
| --- | --- |
| 归档落点 | `evidence/_phaseB-prefreeze/<YYYYmmdd-HHMMSS>/`（**每次 preflight 一个新目录**，绝不覆盖） |
| 指针 | `evidence/_phaseB-prefreeze/LATEST.txt`（verify 默认取它指向的 manifest） |
| 判据 | `modified` / `deleted` 非空 ⇒ exit 1；`added` 只报告不失败 |
| 副作用 | **只读原件**；仅写归档目录与 manifest |

> ⚠️ **第2轮新增注意（本文实测发现，见 §8-C-2）**：`_phaseB-prefreeze/` 自身就在 `evidence/**` 之内 ⇒ **每跑一次 `preflight` 都会让上一次的归档「被新增」**，而 `evidence_hash.py` 会把**归档目录也纳入索引**。两者的交互已在 `evidence_hash` 上产生了**陈旧违规**。⇒ 见 §8-C-2 的处置建议（**报告型起步，不得直接进 blocking**）。

### 3.7 反面 Runbook（把「不要踩的坑」也写成可执行判据）

| 现象 | **正确处置** | **错误处置（已发生过）** |
| --- | --- | --- |
| 请求型脚本打印全绿却 exit 1 | 加 `--no-dump`；或按 stdout 结论段判读并记 `PARTIAL` | ❌ 当代码回归去改生产代码；❌ 改脚本输出路径 |
| `%TEMP%` 下 `PermissionError` 指向 `wms_test_*` | 加垫片 `scripts/_sandbox_compat.py` | ❌ 改 `_test_bootstrap.py` 的 `mkdtemp`（会改动回归网本身） |
| `.verify_scratch/app.db` 找不到 | 认「复制脚本到别处」的形态错了（垫片 `chdir`），改回把探针放原目录 | ❌ 往新目录也拷一份 `app.db`，制造第二个「看似正确」的形态 |
| 中文输出乱码 | 子进程 `PYTHONIOENCODING=utf-8`；父按 `utf-8` 解码；落盘后按 UTF-8 读 | ❌ 凭控制台乱码「翻译」结论 |
| 想把 `evidence/harness/coverage.json` 当「新增覆盖」 | 它只是**度量产物**；覆盖类必须给**前后两个数 + 产生它的文件** | ❌ 把旧 JSON 的 mtime/内容当本轮成果 |
| 判定脚本扫到了**自己** | 声明搜索域 + `EXCLUDE_BASENAMES`（把自己和 `captain_r2_*.py` / `improve_plan.py` / `analysis_ledger.py` 排除） | ❌ 报 `HIT`（A-74：5 个真缺口被报成已做） |
| 想把 `_phaseB-prefreeze` 当成「证据新增」 | 它是**归档副本**，不是新证据 | ❌ 计入「证据只增不减」的增量 |

---

## 4. 台账规范（`<RUN_ID>-ledger.json`，字段冻结）

### 4.1 文件与命名

| 项 | 规则 |
| --- | --- |
| 文件 | `evidence/harness/<RUN_ID>/<RUN_ID>-ledger.json`（机读，**唯一权威**）+ 同名 `.md`（人读，由 JSON 生成） |
| 版本 | `ledger_version` = **`2.0`**（第2轮）；`1.0` 指第1轮 `phase1-snapshot/07` §5.2 的骨架 |
| 落盘 | **必须**经 `_env.save_evidence()`；出现改名（`renamed_by_guard=true`）⇒ 说明同 run 写了两次同名 ledger ⇒ **按下一行的裁决规则处理**，并在 `notes` 说明哪次是终稿 |
| ⚠ **「同 run 两版 ledger」的唯一裁决规则** | 一次 run 内**只允许一份权威 ledger**。若确实落了两次：① 判定顺序**只认 `evidence_journal.jsonl`**（后写者=终稿）；② 终稿 `provenance.superseded_by` 必须写明被取代件的**文件名 + SHA256**；③ 并在 `gaps` 登记一条 `asset_defect`；④ **未被选为终稿的那一份应删除**（唯一允许删 `evidence/**` 的情形，见 §5.2 第 7 条）。**否则**就是 `§8-C-1` 那个「两份互斥台账、都叫 `t9-rega-final`」的翻版（**本轮自查中复现过一次**：`r2t6-runbook-ledger.r2t6-runbook.json`，已按本规则裁决删除，留唯一权威件） |
| 与第1轮的关系 | 第1轮 `verdict` 四值（`通过`/`部分`/`失败`/`不可判定`）**作废**，改 `28` §1 的四档（`HIT`/`PARTIAL`/`NOT_DONE`/`MISS`）。`evidence_level`（`E-1`…`E-4`）**保留但降为旁证**：判定可信度改由 `evidence_kind` 承担 |

### 4.2 字段冻结表（**新增字段只能追加，不得改义**）

**顶层**

| 字段 | 类型 | 规则 |
| --- | --- | --- |
| `ledger_version` | `"2.0"` | 固定 |
| `run_id` | string | = `HARNESS_RUN_ID`；**一份台账一个 run_id** |
| `task_id` / `attempt_id` | string | 必填（追溯用） |
| `operator` | string | 必填 |
| `started_at` / `finished_at` | ISO8601 +08:00 | 必填 |
| `env` | object | `workdir` / `git_head` / **`app_tree`（`HEAD:app` tree SHA1，第2轮新增，替代用 HEAD 做基线）** / `python`（绝对路径 + 版本） / `sandbox` / `temp_run_root` |
| `db_invariant` | object | `sha256_before` / `sha256_after` / `verdict`；**两者必须相等且 = 钉死值** |
| `production_freeze` | object | `files[]`：`{path, bytes, lines, sha256}` —— 被测生产面文件级冻结（对应 t1 的 7 个 app 文件 + 11 个 scripts/config 文件） |
| `anchor_readings` | array | `28` §4 的 7 个基线锚点：`{path, bytes, sha256, matches_captain}`；`matches_captain=false` ⇒ 该轮结论**不得**声称「未回归」 |
| `results` | array | 见下 |
| `gaps` | array | 显式登记未验证项（R-6） |
| `artifact_index` | array | `{path, bytes, sha256}` —— 本 run 落盘的全部证据文件（**路径必须真实存在**） |

**`results[]`（核心）**

| 字段 | 类型 | 规则 |
| --- | --- | --- |
| `id` | string | `C-01` / `TL-04` / `REG-uat` …（**跨批次按 id 对齐做漂移差分**） |
| `wave` | string | `W6` / `W7` / `REG`（回归复验） |
| `title` | string | 一句话 |
| **`evidence_kind`** | enum | `file_exists` \| `content_mention` \| `content_implementation` \| `behavior_verified` —— **`verdict=HIT` 只允许后两者** |
| `verdict` | enum | `HIT` \| `PARTIAL` \| `NOT_DONE` \| `MISS` |
| `criterion` | string | 该条的**可判定判据**（不是「做了什么」） |
| `command` | string | 照抄可跑（含插值后的变量） |
| `exit_code` | int \| null | `null` 必须配 `notes` 写原因 |
| `expected` / `observed` | string | 逐字期望 vs 逐字实测 |
| `criterion_digest` | string | `k=v,k=v`（**凡输出含计数/数字必填**）—— 跨批次漂移检测唯一抓手 |
| **`reproducible`** | bool | 判据：**同 run 同命令再跑一次能否得到同一 `observed`**；`false` 必须在 `notes` 写原因 |
| **`search_domain`**（新增） | object | `{dirs:[], match:"filename"\|"content", exclude_basenames:[]}` —— **第2轮强制**，`exclude_basenames` **必须含判定脚本自身** |
| **`behavior_flip_test`**（新增） | object | `{question, answer, red_when_removed}` —— 回答「**删掉它什么会变红**」；答不出 ⇒ `verdict` 必须是 `NOT_DONE` |
| **`coverage_delta`**（新增，覆盖类必填） | object | `{metric, before, after, produced_by}` —— **前后两个数 + 产生它的文件** |
| **`provenance`**（新增） | object | `{source, source_sha256, source_verdict, superseded_by}` —— 引用他人结论时写明取证方与原始判定；`superseded_by` 用来说明「本证据取代了哪一份」（文件名 + SHA256），无则填 `null` |
| `postfix_verdict` / `rewrite_verdict` | string | 回归复验三档（沿用 t9 词汇） |
| `class` | enum | 回归归类：`unchanged_pass` \| `red_to_green` \| `still_red_asset` \| `asset_defect_flip` \| `expected_flip` \| `criterion_invalidated` \| `improved` \| `unchanged` \| `WORSE` \| **`REGRESSION`** \| `not_rerun` \| `probe_only` |
| `class_basis` | string | `class` 的**裁定依据**（引条款/裁定号）。**无依据者一律按 `REGRESSION` 报出**（不得批量豁免） |
| `postfix_evidence` | string | 指向**本 run** 的证据路径（相对仓库根，以 `/` 分隔） |
| `notes` | string | 自由文本；`exit_code=null`、`reproducible=false`、`PARTIAL`/`NOT_DONE` **必须**写缺口 |

**`gaps[]`**

| 字段 | 规则 |
| --- | --- |
| `id` | `GAP-<run>-n` |
| `item` / `state` | `state` ∈ `blocked` \| `unexecuted` \| `not_covered` \| `asset_defect` \| `env_drift` |
| `reason` / `action` | 写清「为什么」与「交给哪一波次」 |
| `owner_wave` | 承接波次（如 `阶段B / C-11`）；**`state != 已解决` 者不得计入通过数** |

### 4.3 校验规则（越界即该台账**无效**）

**可执行校验器**：`harness/t6_ledger_check.py`（8 条规则 + 8 反例/1 正例自检，**已实测**）。

```powershell
$py = 'F:\Miniconda\envs\wage\python.exe'
& $py -B test-reports-2026-10\harness\t6_ledger_check.py --selftest                       # 期望 exit 0（9/9）
& $py -B test-reports-2026-10\harness\t6_ledger_check.py test-reports-2026-10\40-第2轮实测台账模板.json
& $py -B test-reports-2026-10\harness\t6_ledger_check.py test-reports-2026-10\evidence\harness\<RUN_ID>\<RUN_ID>-ledger.json
```

| 规则号 | 判据 |
| --- | --- |
| **R-1** | `verdict=HIT` 而 `evidence_kind ∈ {file_exists, content_mention}` ⇒ **无效** |
| **R-2** | `verdict=HIT` 而无 `behavior_flip_test.red_when_removed` ⇒ **无效** |
| **R-3** | 覆盖类条目（`id` 匹配 `C-01…C-11`）缺 `coverage_delta` ⇒ **无效** |
| **R-4** | `search_domain` 缺失、或 `exclude_basenames` 为空、或不含判定脚本自身 ⇒ **无效** |
| **R-5** | `verdict ∈ {PARTIAL, NOT_DONE}` 而未在 `gaps` 里出现 ⇒ **无效** |
| **R-6** | `artifact_index` 里填写了**不存在的路径** ⇒ 该行降级为 `NOT_DONE` |
| **R-7** | `db_invariant.sha256_before != sha256_after` 或 ≠ 钉死值 ⇒ **整份台账作废**并立即停工排查 |
| **R-8** | `command` 里出现裸 `python` / `python3` / `py` ⇒ 该行**无效**（R-4 铁律） |

**实测结论（2026-10-07）**：`--selftest` = `判定 OK（9/9）`（8 个反例逐一被对应规则抓到 + 1 个正例零 ERROR）；模板 `40-第2轮实测台账模板.json` = `判定 OK`（`results=1 gaps=1 artifacts=1`）。

### 4.4 人读版（贴进任意交付文档）

| ID | 波次 | 检查项 | `evidence_kind` | 判定 | 期望 | 实测 | exit | 「删掉它什么会变红」 | 证据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C-01 | W6 | 审计写入断言面 | `behavior_verified` | HIT | … | … | 0 | `audit_probe.py#assert_audit_row` | `manifest#C-01` |
| C-11 | W6 | 不可判定项用例 | `content_implementation` | PARTIAL | … | … | 0 | — | `manifest#C-11` |

> **人读表的字段必须与 JSON 一一对应**；任一处手工补充都要两处同写，**冲突以 JSON 为准**。
> 证据引用统一写 `<ledger_filename>#<id>`（比写文件名稳：文件会搬家，`id` 不会），必要时再附相对路径。

### 4.5 跨批次漂移差分（台账存在的真正价值）

```powershell
# 对两个 run 的 ledger 做 criterion_digest 差分（字段已机器可比）
$py = 'F:\Miniconda\envs\wage\python.exe'
& $py -B -c @"
import json,sys
sys.stdout.reconfigure(encoding='utf-8',errors='replace')
a=json.load(open(r'<old-ledger>',encoding='utf-8'))['results']
b=json.load(open(r'<new-ledger>',encoding='utf-8'))['results']
m={r['id']:r for r in a}
for r in b:
    o=m.get(r['id'])
    if o and o.get('criterion_digest')!=r.get('criterion_digest'):
        print('DRIFT',r['id'],o.get('criterion_digest'),'->',r.get('criterion_digest'))
"@
```

**必须报漂移的字段**（与 `coverage_drift.py` 的 8 条判据对齐）：

`rules=271` · `templates=87` · `capabilities=44` · `head_count=1` · `revisions=35` · `rows=6712` · `accounts=64` · `functional_pass=109` · `anon_open=0` · `no_guard_views=5` · `non_get_rules=153` · `method_level_non_get=155` · `writable_literal=108` · `writable_any=116` · `uncovered_writable=0` · `smoke_plan=148` · `duplicate=0`

> ⚠ **V-16/N-1 同步（2026-10-07）**：上表三处是 **V-06/C-05 按 A-70 有意更新**后的值 ——
> `writable_literal` `6 → 108`、`writable_any` `14 → 116`、`uncovered_writable` `101 → 0`。
> 本轮之前的台账/报告若仍写 `6/14/101`，即为**陈旧口径**（差分时会被判为漂移，需按 A-70 三步处理）。

**`coverage_drift.py` 的输入语义（N-1 处置，V-16 报出 / captain 裁定）**

* 本工具**必须显式传 `--coverage <本次 run 产物>`**；**缺参 ⇒ `exit 2`（用法错误，不是回归）**，
  stdout 明写该语义，并打印冻结锚点的留档读数（bytes/SHA256，仅历史留档、**不参与判据**）。
* 为什么不能拿锚点当默认输入：`evidence/harness/coverage.json`（`29` §4 声明锚点、V-14 G1 判定 unchanged）
  记录的是 **V-06 之前**的 `6/14/101`，而 `LOCKED` 已是 `108/116/0` ⇒ 两者语义互斥 ⇒
  「直跑默认路径」必然假红（旧行为实测 = `判据 5/8 通过 => exit 1`，原始 stdout 见
  `test-reports-2026-10/.tmp/r2t14/n1_before.txt`）。
* 复算（三条，仓库根目录）：
  ① 直跑（无参）⇒ **exit 2**；
  ② `measure_coverage.py --no-request-probes --out <run>/coverage.json` 后
     `coverage_drift.py --coverage <run>/coverage.json` ⇒ **exit 0**；
  ③ 同 ② 加 `--probes-exclude r2_c05_write_probe`（回落稿）⇒ **exit 1**（判据仍敏感）。
* 回退（A-70 三步）：把 `--coverage` 默认值改回 `DEFAULT_COVERAGE` + 删除 exit 2 分支 + 重跑 ①②③ 登记。
* 受影响的历史引用（**未由本任务改动，需各自维护者同步**）：`reconcile_r2.py:555`（断言「漂移判据 exit 0」、
  实为无参调用 ⇒ 今日已是红）与 `r2_v14_ledgerbook.py:259` 的 `criteria` 记录（写了无参命令 + `exit_code: 0`）。

任一项变化 ⇒ **先判定「是有意变更还是回归」**，再继续；不做这一步的批次结论不得进 DoD。

### 4.6 度量口径（数字必须带「工具 + 口径 + 值」三要素）

| 数字 | 必须写成 | 反例（**不得写**） |
| --- | --- | --- |
| 表数 | `tables=75(含 alembic_version)` / `tables=74(metadata)` | `75 张表` |
| 行数 | `rows=6712(check_db_bootstrap,business-tables)` / `rows=6713(mode=ro,all-tables)` | `6713 行` |
| 无校验视图 | `no_guard_views=5(current,source-scope)` | `无校验 5 个` |
| 非 GET 端点 | `non_get_rules=153` / `method_level_non_get=155` / `non_get_without_any_hit=141`（**三个量纲不得互替**） | `非 GET 端点 155 个` |
| 覆盖 | `writable_literal_covered_by_functional=6` / `writable_any_covered_by_all=14` | `覆盖了 14 个` |
| 行数（文件） | **Python `splitlines()`**（A-23 裁定）；写「总行数 N（非空 M）」 | PowerShell `Get-Content` 的计数 |

> 口径不明的数字**一律不进台账**——这是本项目历史上最贵的返工来源（已因计数漂移付过 **5 次**代价：69 vs 83、45 vs 49、24 vs 31、459 vs 595、138 vs 104）。

---

## 5. 证据归档规范

### 5.1 归档落点（第2轮权威）

```text
test-reports-2026-10/
  40-第2轮实测Runbook与台账规范.md        # 本文（规范本身）
  40-第2轮实测台账模板.json               # 字段冻结 + 1 条样例（机器可读契约）
  50-第2轮证据归档索引.md                 # 归档索引（谁写了什么、在哪、怎么复跑）
  evidence/                              # ← gitignore（E-3）；只增不改
    harness/<RUN_ID>/                    #   本次 run 的落点（新写入唯一合法位置）
      <RUN_ID>-ledger.json / .md         #   机读 + 人读台账
      evidence_journal.jsonl             #   落盘审计流水（只追加）
      <脚本>.<后缀>                      #   各步骤原始输出
    harness/                             #   历史平铺层（t2–t5）：**只读**，新写入不得落这一层
    uat/ api/ analysis/ final/           #   分域制品（uat_chains / write_suite / assertion_ledger …）
    _phaseB-prefreeze/<stamp>/           #   regression_preflight 的归档副本（**不是新证据**，见 §8-C-2）
```

### 5.2 硬规矩

1. **只增不改**：同一次实测**不许覆盖**任何已有证据；重跑就换 `RUN_ID`。覆盖会让「当时到底跑出什么」永久丢失。
2. **写入必须过 `_env.save_evidence()`**（`guard=True, journal=True`）。直接 `open(...,'w')` 写 `evidence/**` 视为**违规归档**。
3. **不许把脚本自己写的产物当证据**：仓库根 `_smoke_results.json` / `_permission_matrix.json`（gitignore）**只是旁证**；结论以 stdout 段为准（第1轮 §3.2 口径，第2轮继续有效）。
4. **每条结论都要能指回证据**：优先 `<ledger_filename>#<id>`；确需指向文件时写**相对路径 + 小节编号**（不要只写行号，会随编辑漂移）。
5. **`artifact_index` 里的路径必须真实存在**。填了不存在的路径 ⇒ 该行降级为 `NOT_DONE`（**不许**填假路径充数）。
6. **大体积原始输出如实登记**：若某次输出过大不适合搬运，在 `notes` 写明「原文在 `<tmp 路径>`，本环境不自动归档」，**不要**只留一句「已归档」。
7. **离场清理**：`.tmp/<RUN_ID>/` 下的临时脚本与中间产物可在采数后删除；**已落 `evidence/**` 的一律不得删**（例外：**同一 run 内误落的重复 ledger** 可由本人裁决后删除，但必须①在终稿 `provenance.superseded_by` 写明被删件的文件名 + SHA256，②在 `gaps` 登记 `asset_defect`。**本文已按此执行一次**）。

### 5.3 ⚠ 两条「证据归档」的自引用约束（本轮实测踩到，必须写进规范）

| # | 约束 | 实测证据 | 正确做法 |
| --- | --- | --- | --- |
| **S-1** | **台账不能给自己的 `evidence_journal.jsonl` 记指纹** | 台账落盘 ⇒ journal 追加一行 ⇒ 字节/哈希立刻变；再算一次写进台账 ⇒ journal 又变。自引用无解（本文实测：journal 从 2953 → 3310 → 3679 B，每次落盘都变） | `artifact_index` 里的 journal 条目**只标注身份与自引用未解**（`bytes=null` / `sha256=null` / `note` 写明原因），**不要**填一个立刻过期的数字 |
| **S-2** | **台账不能给自己的 SHA256 记准确值** | 同上（写入即改变自身） | 台账内**不记自己的哈希**；对外引用时由调用方在**写完之**后另算（`(Get-FileHash …).Hash`） |

### 5.4 归档自证（每个 run 收尾必做）

```powershell
$py = 'F:\Miniconda\envs\wage\python.exe'
& $py -B test-reports-2026-10\harness\evidence_hash.py --selftest        # 1 阳性 + 5 阴性 + A-50 回归，应全过
& $py -B test-reports-2026-10\harness\evidence_hash.py --json           # 归档完整性读数（见 §8-C-2：当前非 0，属陈旧违规）
```

| 工具 | 用途 | 备注 |
| --- | --- | --- |
| `_env.save_evidence` | 落盘 + 改名守卫 + 审计流水 | **强制** |
| `evidence_hash.py --freeze` | 为证据建立/扩展**只追加**索引快照 | ⚠ **当前 `--freeze` 返回 exit 1**（33 条陈旧违规），见 §8-C-2 |
| `evidence_hash.py --selftest` | 对抗自检（证明工具本身能报红） | 作为 TL-04 的**能力**证据，不是**基线**证据 |

---

## 6. 第2轮执行排程（把 `30` §6 的 B1→B5 落成可跑的批次）

| 批次 | 靶子 | 建议 `RUN_ID` | 命中工具 | 产出证据 |
| --- | --- | --- | --- | --- |
| **B1** | TL-01 / TL-02 / TL-04（注释变实 + 新建接入） | `r2-exec-b1-tl` | `ci_gates.py` + `Jenkinsfile` | `ci_gates` 前后两次 JSON + 注入破坏实验输出 |
| **B2** | C-07 应用级硬闸 / C-02 并发事务 | `r2-exec-b2-hard` | 新增探针（CH-2 副本） | 探针 stdout + 阳性/阴性对照 |
| **B3** | C-01 审计 / C-04 链 A / C-05 写端点 | `r2-exec-b3-blind` | `uat_chains.py` / `write_suite.py` / 新增审计探针 | `uat_chains.json` 前后差分 + `coverage_delta` |
| **B4** | C-06 / C-03 / C-08 / C-09 / C-10 / C-11 | `r2-exec-b4-crit` | `negative_matrix.py` / 导入导出探针 | 状态码 + 机读标记（**不断文案**，A-69） |
| **B5** | TL-05 / TL-06 / TL-07 + 回归复验 + 新改进报告 | `r2-exec-b5-close` | `regression_preflight.py` + `t9_ledger.py` | 回归台账（`class` 全覆盖）+ 7 锚点比对 |

**每批 DoD**（缺一不得进下一批）：
1. `ci_gates --phase first` exit 0（或失败项已在 `gaps` 登记并有承接波次）；
2. `<RUN_ID>-ledger.json` 落盘（`save_evidence`），字段过 §4.3 八条校验；
3. `db_invariant` 前后一致（R-1）；
4. `artifact_index` 全部路径真实存在；
5. `gaps` 覆盖全部 `PARTIAL`/`NOT_DONE`。

---

## 7. 本轮（t6）自证记录

> 本文档族按 §4.2 的「证据包」要求留证；机读台账 `evidence/harness/r2t6-runbook/r2t6-runbook-ledger.json`。

### 7.1 环境与冻结读数【已实测】

| 项 | 值 |
| --- | --- |
| HEAD（开工 / 收尾） | `10d06173674013115b98ce9743b4b601f79ad111` / `db9f5c40bae1cf742db56c8fb3725a0b857a83e6` —— **测量期间被推进 2 次**，故 HEAD **不是**基线 |
| `HEAD:app`（开工 / 收尾） | **`c8f7d4abca1567b6219dbd77f22c82722f877ad6` / 同上**（= t1 冻结值，**零漂移**） |
| 解释器自检 | `flask 3.1.2` / `sqlalchemy 2.0.44`，exit 0 |
| 裸 `python` | `C:\Users\Richard Zhang\.conda\pkgs\python-3.9.21-h8205438_1\python.exe`（R-4 反例） |
| 真实库 | `2531328 B` / `F5DA2306…0E0F065`，开工与收尾各一次，**未变** |
| `evidence/` gitignore | `.gitignore:41-42` 命中；`git ls-files test-reports-2026-10/.tmp` = 0 |

### 7.2 基线锚点复算（7/7 与 `29` §4 **逐位相符**）【已实测】

| 锚点 | 字节 | SHA256（本文复算） | 与 captain 一致 | 与 t1 一致 |
| --- | --- | --- | --- | --- |
| `evidence/uat/uat_chains.json` | 33318 | `360A8570BC0080A2984A59AD945B2C837AD96ACF7B55E6242AE7E2C6417DD23A` | ✅ | ✅ |
| `evidence/harness/negative_matrix.json` | 24424 | `B743C73F86F5EB5C0FBA38410119D8D3A6BDE5FBACDF214CFA0DB409EF5B7479` | ✅ | ✅ |
| `evidence/analysis/assertion_ledger.json` | 60937 | `C7C312734DD8E02486D26C3639D8D074CCFCD59BCEB002C13C7CC9587AC94092` | ✅ | ✅ |
| `evidence/api/write_suite.json` | 73293 | `B608117EBDCA2A6F74595F0DB4A010187D8834715CD5E70D5C1AAD85F4A3F403` | ✅ | ✅ |
| `evidence/harness/coverage.json` | 236893 | `5E2C9D4315971B31C83AFD7833C310501199C34F61BFD868EF07A6AEEF7BF1F0` | ✅ | ✅ |
| `evidence/api/api_matrix.json` | 1342834 | `8451BB6738CCB25C41794E7B9548969D0EDDC8FE6EAE855DCC5F1D1CC746CB86` | ✅ | ✅ |
| `26-阶段A收口-复核读数.json` | 11994 | `CF0E2B14581D82072E087617B0CE3DBC1F4676897787DB6B14D6C6FA43D37319` | ✅ | ✅ |

⇒ **第2轮开工基线可用，无需重建锚点。**（第8项 `t9-rega-final/ledger.json` 两侧均不存在，见 §8-C-1。）

### 7.3 命令实况【已实测】

| 命令 | exit | 结果 |
| --- | --- | --- |
| `ci_gates.py --phase first --json …` | **0** | 11/11 步 OK；`blocking_failed=[]`；`report_only_failed=[]`；`root_json_untouched=true` |
| `check_model_refs.py` | **0** | `scanned 23 files, name_query_refs 602, violations 0` / `RESULT: OK` |
| `coverage_drift.py --selftest` | **0** | `判据 9/9 通过` |
| `t6_runbook_selftest.py` | **0** | 五项守卫/流水/真实库断言全过（§2.2） |
| `t6_ledger_check.py --selftest` | **0** | `判定 OK（9/9）`：8 反例逐一被 R-1…R-8 抓到 + 1 正例零 ERROR |
| `t6_ledger_check.py 40-第2轮实测台账模板.json` | **0** | `判定 OK（results=1 gaps=1 artifacts=1）` |
| `evidence_hash.py --freeze` | **1** | **VIOLATION**：`modified=9 deleted=20 phantom_entry=4`（**陈旧**，见 §8-C-2） |
| `evidence_hash.py --no-strict-coverage` | **1** | 同上 ⇒ **非 strict 开关所致** |
| `evidence_hash.py --selftest` | 见台账 | 工具自检（能力证据） |

### 7.4 本轮产出

1. **本文** `test-reports-2026-10/40-第2轮实测Runbook与台账规范.md` —— Runbook（§2–§3）+ 纪律（§1）+ 台账规范（§4）+ 归档规范（§5）+ 排程（§6）。
2. `test-reports-2026-10/40-第2轮实测台账模板.json` —— §4.2 字段冻结的**可机器校验**实例（含 1 条 `HIT` 样例）。
3. `test-reports-2026-10/50-第2轮证据归档索引.md` —— 归档索引与复跑入口。
4. `test-reports-2026-10/harness/t6_runbook_selftest.py` —— §2.2 证据通道契约的**行为级**自证探针（新文件，不改既有脚本）。
5. `test-reports-2026-10/harness/t6_ledger_check.py` —— §4.3 八条规则的可执行校验器（新文件，自带 8 反例/1 正例自检）。
6. 证据：`evidence/harness/r2t6-runbook/`（`t6-guard-probe*.txt` + `evidence_journal.jsonl` + 6 个 `gate_*.txt` + `r2t6-runbook-ledger.json`，共 16 条 `artifact_index`）+ `evidence/harness/ci-r2t6-runbook/`（`ci_gates_first.console.txt`）。
7. 本 run 台账校验：`t6_ledger_check.py r2t6-runbook-ledger.json` ⇒ **判定 OK（results=5 gaps=6 artifacts=16）**。

**未修改**：`app/**`、模板、配置、`scripts/**` 既有脚本、迁移链；真实库 SHA256 前后一致。
**未清残余（按 §5.2 第 7 条例外处理）**：`evidence/harness/r2t6-runbook/r2t6-runbook-ledger.r2t6-runbook.json` —— 误落的重复件，**已删除**并在本 run 台账 `gaps` 登记 `asset_defect`。

---

## 8. 本轮新发现（第1轮 Runbook 未覆盖 / 已过时）

### 8-C-1 ⚠ `t9-rega-final/` 存在**两份互斥的回归台账**，且都自称 `run_id = t9-rega-final`

| 项 | 文件 A | 文件 B |
| --- | --- | --- |
| 路径 | `evidence/harness/t9-rega-final/t9-regression-ledger.json` | `…/t9-regression-ledger.t9-rega-final.json` |
| 字节 / SHA256 | 118314 / `6C43167E7244E787B9F8B8B2E8C734D555EE6B11CAC88763CDEC28D04CE78410` | 119007 / `A609B0D78D350B49CF9B4ADC70A84FB8CAE1AF2D375F55308B3C1F07D49921E8` |
| mtime | 2026-10-07 14:39:**26** | 2026-10-07 14:39:**47** |
| `run_id` / `baseline.sha256` | `t9-rega-final` / `C7C31273…`（**相同**） | `t9-rega-final` / `C7C31273…`（**相同**） |
| `counts_by_class` | 含 **`REGRESSION: 1`**、`WORSE: 1`、`not_rerun: 1` | **无 `REGRESSION`/`WORSE`**；改出 `criterion_invalidated: 2`、`asset_defect_flip: 6` |

**判定顺序由审计流水唯一确定**（`evidence_journal.jsonl` 逐行）：

```text
14:39:26  t9-regression-ledger.json                  renamed_by_guard=false  sha256=6C43167E…  bytes=118314
14:39:47  t9-regression-ledger.t9-rega-final.json    renamed_by_guard=true   sha256=A609B0D7…  bytes=119007
```

⇒ **文件 B（`.t9-rega-final.json`）是后写的、即终稿**（`REGRESSION=0` / `asset_defect_flip=6` / `criterion_invalidated=2`）。
文件 A 是**同一 run 内较早的一次**，且**同时存在**，其 `class` 数里含 `REGRESSION: 1` 与 `not_rerun: 1`。

| 影响 | 处置（第2轮强制） |
| --- | --- |
| 任何「第2轮回归基线 = t9 台账」的引用，**若按文件名取 `t9-regression-ledger.json`，会取到 `REGRESSION=1` 的那一份** ⇒ 与阶段A 收口「`REGRESSION=0`」矛盾，属**引用事故**，不是回归 | ① 引用**必须**显式写全名 `t9-regression-ledger.t9-rega-final.json` **并附 SHA256**；② 台账 `provenance` 必须填 `source_sha256`；③ 判定顺序**只认 `evidence_journal.jsonl`**，不认文件名，也不认 mtime 单独作证 |
| 结构缺口：`guard_write` 改名后，**新名字里不再能区分「哪次是终稿」**（`run_id` 与 `baseline` 都相同） | **第2轮新增字段 `provenance.superseded_by`**（见 §4.2 `provenance`）：若某证据被同 run 的后续落盘取代，**必须**在新证据里写明取代了哪一份（路径 + SHA256）。这是本文对第1轮台账格式的**唯一结构性增补**，已写入 §4.2 与 `40-第2轮实测台账模板.json` |

### 8-C-2 ⚠ `evidence_hash` 与 `regression_preflight` 存在**交互缺陷**：`--freeze` 必然报 33 条陈旧违规

**【已实测】** 2026-10-07：

```text
$ & $py -B test-reports-2026-10\harness\evidence_hash.py --json
exit=1   verdict=violation
counts = {"baseline_files":2747,"current_files":2727,"modified":9,"deleted":20,
          "journal_broken":0,"added":0,"index_missing":0,"coverage_gap":0,
          "phantom_entry":4,"baseline_tampered":0,"dirs_conform":416,"dirs_total":416}
violations = 33  (by_kind: deleted=20, modified=9, phantom_entry=4)
```

`--freeze` 与 `--no-strict-coverage` 两种形态**均为 exit 1**（⇒ 不是 strict 开关造成）。

**根因（读源码 + 读数可解释）**：

1. `evidence_hash` 的**索引基线**建立于 2026-10-06（FBB56663… 时代），而 `regression_preflight` 之后**三次**把 `evidence/**` 克隆进 `_phaseB-prefreeze/<stamp>/`（`20261007-132253`、`20261007-142403`、`20261007-172654`）；
2. 归档目录**也在 `evidence/**` 之内**（`regression_preflight.py:36` 只排除 `_phaseB-prefreeze` 目录自身，**不排除它里面的内容**）⇒ 被索引一并收纳；
   - 20 条 `deleted` = 基线里 `baseline-prefix/e01-*.txt`、`idx-*.txt` 等**当时存在、后被清掉**的文件（其中 3 组 ×5 条来自 3 份归档，另 1 组 ×5 条来自平铺层）；
   - 4 条 `phantom_entry` = 索引快照列了 `baseline-prefix/` 里**并不存在**的 5 个文件名；
   - 9 条 `modified` = `LATEST.txt` 与归档内被**再次改写**的少数文件；
3. `LATEST.txt` 每跑一次 `preflight` 就变 ⇒ 「修改」不可能收敛。

| 影响 | 处置（第2轮） |
| --- | --- |
| TL-04 的接入位**当前不可能拿到 exit 0**（`ci_gates.py:111-112` 的预留注释里写的就是 `--strict-index`） | ① **不得**为让它变绿而重基线化（会永久掩盖真篡改）；② **不得**直接按 blocking 接入；③ 按 `30` §2.2 原定「**report-only 起步**」接入，并在台账 `gaps` 以 `state=asset_defect` 登记；④ 修法建议（属 W7 范围，本文只登记）：让 `evidence_hash` **默认排除 `_phaseB-prefreeze/**`**，或让 `regression_preflight` 把归档写到 `evidence/` **之外** |
| `--freeze` 不能作为「归档完整性通过」的证据 | 归档自证改用 §5.4 的 `--selftest`（证明**工具能报红**）+ 逐 run 的 `artifact_index` + `evidence_journal.jsonl` |

### 8-C-3 ⚠ A-62 的「原生必失败」探针在**第2轮开工时已被环境漂移推翻**

| 项 | 第1轮（2026-10-06/07） | **第2轮（2026-10-07，本文实测）** |
| --- | --- | --- |
| `route_inventory` **原生**（无垫片） | exit **1**（`PermissionError` on `%TEMP%\dsh-*\wms_test_*\app.db`，栈顶 `_test_bootstrap.py:25` 的 `shutil.copy2`） | — |
| `run_gates` 环境探针 | `native_exit=1 expected=1` ⇒ `verdict=matched` | **`native_exit=0 expected=1 verdict=unexpected`** |

**判读**：这不是「有人修了代码」，而是**沙箱对 `mkdtemp` 0o700 目录的写入许可属环境态**（第1轮 `phase1-snapshot/07` §8-I-1 已把这条机理写清）。

| 处置 | 理由 |
| --- | --- |
| **禁止**把 `expected` 改成 0 来「消红」 | A-62 明令：环境依赖探针**不得重基线化** |
| 台账把该行记为 `class=expected_flip`？**不可以** | 它不在 `EXPECTED_FLIPS` 的裁定清单里；按 §4.3 规则，**无裁定依据者一律按 `REGRESSION` 报出**。此处应在 `gaps` 以 `state=env_drift` 登记，并写明「`ci_gates` 的 blocking 判据不含该探针，故不改判任何门禁」 |
| **这条本身就是第2轮要取证的第一手材料** | 证明「环境态可变」⇒ 任何把环境探针写进 blocking 判据的做法都必须重新论证 |

### 8-C-4 ✅ `evidence/` 已被 gitignore（第1轮「属跟踪范围」的说法作废）

`.gitignore:41-42`、`git ls-files test-reports-2026-10/.tmp` = 0 条。**结论**：证据不污染 `git status`，但**也不受 git 保护** ⇒ 见 §2.3 E-3 与 §5.2。

### 8-C-5 ✅ `--no-dump` 已落地（第1轮 P-1 待办关闭）

`ci_gates.py` 的 `permission_matrix` / `smoke_test` 步骤**强制** `--no-dump`，且 `root_json_untouched` 断言仓库根两 JSON 哈希前后一致（本次实测 `true`）。
⇒ 第1轮 §3.2「exit code 不可信、须 grep stdout」的**临时口径退役**，改按 §3.4 判读。

---

## 附录 A：一批实测的收尾检查块（可整段复制）

```powershell
$py = 'F:\Miniconda\envs\wage\python.exe'
Set-Location 'D:\workspace\wage_management_system - bak'
$env:PYTHONIOENCODING = 'utf-8'
$env:HARNESS_RUN_ID   = '<run_id>'          # 全批次复用一个
$tmp = "test-reports-2026-10\.tmp\$env:HARNESS_RUN_ID"
New-Item -ItemType Directory -Force -Path $tmp | Out-Null

# ① 开工：真库指纹 + 生产面 tree
& $py -c "import sys;sys.path.insert(0,r'test-reports-2026-10/harness');import _env;print(_env.assert_real_db_untouched('开工'))"
git rev-parse HEAD:app          # 期望 c8f7d4abca1567b6219dbd77f22c82722f877ad6

# ② 回归复跑前：归档证据（每批只需一次）
& $py -B test-reports-2026-10\harness\regression_preflight.py preflight

# ③ 门禁单一入口（blocking + report-only 一次跑完）
& $py -B test-reports-2026-10\harness\ci_gates.py --phase first --json "$tmp\ci_gates_first.json" > "$tmp\ci_gates.console.txt" 2>&1
$rc = $LASTEXITCODE                                     # 不接管道（R-5）；期望 0
Write-Output "ci_gates exit=$rc"

# ④ 业务复跑（按批次靶子选跑；全部经垫片/绝对路径）
# & $py -B test-reports-2026-10\harness\uat_chains.py   ...
# & $py -B test-reports-2026-10\harness\write_suite.py  ...
# & $py -B test-reports-2026-10\harness\negative_matrix.py ...
# & $py -B test-reports-2026-10\harness\measure_coverage.py --no-request-probes --out "$tmp\coverage.json"

# ⑤ 复跑后：完整性校验 + 归档自检道具
& $py -B test-reports-2026-10\harness\regression_preflight.py verify     # 期望 0（modified=0 deleted=0）
& $py -B test-reports-2026-10\harness\evidence_hash.py --selftest        # 期望全过

# ⑥ 收尾：真库指纹复核 + 工作区
& $py -c "import sys;sys.path.insert(0,r'test-reports-2026-10/harness');import _env;print(_env.assert_real_db_untouched('收尾'))"
git status --short

# ⑦ 台账：用 40-第2轮实测台账模板.json 填充 -> _env.save_evidence('<run_id>-ledger.json', ...)
#    再跑 §4.5 的漂移差分
```

> ⚠️ **不要把 `Tee-Object` 指向 `evidence/**` 充当归档**：归档一律走 §2.2 的 `save_evidence` API。`Docs/` 子树更是整树拒绝 shell 落盘（E-2）。

## 附录 B：本文引用的实测坐标

| 坐标 | 文件 |
| --- | --- |
| 证据落点 / 守卫 / 流水 | `harness/_env.py:36`（RUN_ID）、`:64-77`（`evidence_dir`）、`:80-95`（`guard_write`）、`:272-291`（`save_evidence`）、`:184-191`（真库闸） |
| 垫片限制 | `scripts/_sandbox_compat.py:32-41`（mkdtemp 0o700→777）、`:46-72`（子进程通道）、`:80-84`（chdir + sys.path） |
| 门禁单一入口与分组 | `harness/ci_gates.py:51-113`（步骤表）、`:108-113`（三个预留接入位）、`:125-200`（判定） |
| 归档工具与交互缺陷 | `harness/regression_preflight.py:24-38`（BASE/ARCHIVE_ROOT/iter_files）、`:41-62`（preflight） |
| 回归台账生成器 | `harness/t9_ledger.py:240-310`（build）、`:353-358`（`save_evidence` 落盘） |
| 覆盖漂移判据 | `harness/coverage_drift.py`（8 条不许退化 + `--selftest`，自检 9/9） |
| 台账校验器 | `harness/t6_ledger_check.py`（R-1…R-8 + `--selftest` 8 反例/1 正例） |
| 证据通道自证探针 | `harness/t6_runbook_selftest.py`（守卫改名 / journal / 真库零副作用） |
| 本文实测台账 | `evidence/harness/r2t6-runbook/r2t6-runbook-ledger.json`（`results=5 gaps=6 artifacts=16`，校验 OK） |
| 基线锚点 | `29-第2轮事实底盘.md` §4 |
| 判定口径 | `28-第2轮执行纪律.md` §1–§3、§5 |
| 批次排期 | `30-第2轮测试方案.md` §6 |

## 附录 C：本轮交付物清单

| # | 路径 | 说明 |
| --- | --- | --- |
| 1 | `test-reports-2026-10/40-第2轮实测Runbook与台账规范.md` | 本文（Runbook + 台账规范 + 归档规范 + 第2轮执行排程） |
| 2 | `test-reports-2026-10/40-第2轮实测台账模板.json` | 字段冻结的机器可读契约（§4.2 + §4.3 校验器可读） |
| 3 | `test-reports-2026-10/50-第2轮证据归档索引.md` | 归档索引（落点、命名、复跑入口、只读层清单） |
| 4 | `test-reports-2026-10/harness/t6_runbook_selftest.py` | §2.2 证据通道契约的行为级自证探针（**新文件**） |
| 5 | `test-reports-2026-10/harness/t6_ledger_check.py` | §4.3 八条规则的可执行校验器（**新文件**，8 反例 + 1 正例自检） |
| 6 | `test-reports-2026-10/evidence/harness/r2t6-runbook/` | 本节自证证据（`t6-guard-probe*.txt` + `evidence_journal.jsonl` + 台账） |
| 7 | `test-reports-2026-10/evidence/harness/ci-r2t6-runbook/` | `ci_gates --phase first` 原始输出 |
