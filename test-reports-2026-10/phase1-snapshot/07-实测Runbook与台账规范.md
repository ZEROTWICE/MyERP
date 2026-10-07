# 07 实测 Runbook、证据留存规范与结果台账格式（MyERP 阶段一 · t7）

| 项目 | 值 |
| --- | --- |
| 产出任务 | `t7` 实测 runbook、结果台账规范与流程改进设计（attempt `06e9f3c9-252a-4ab1-83c5-c860da3599ad`） |
| 产出人 | 测试流程优化工程师 |
| 产出时间 | 2026-10-06（本机） |
| 工作目录 | `D:\workspace\wage_management_system - bak` |
| 仓库 HEAD | `f60a54d07cfea3aa7c21111a7efa70c267b4b1c2`（`main`） |
| 真实库 `app.db` | SHA256 `F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065`（2531328 B），**本文全部实跑前后各复核一次，未变** |
| Python | `F:\Miniconda\envs\wage\python.exe` = Python 3.9.21 |
| 只读声明 | 本文**未修改任何生产代码/模板/配置/脚本**；实跑产物只新建在 `.analysis-scratch/`（已 gitignore）内，收尾已删除；真实库仅以 `mode=ro` 只读连接或 `make_app()` 副本访问 |
| 上位输入 | [01-基线事实清单.md](01-基线事实清单.md)（t1）、[开发与测试规划-2026-10-06.md](../开发与测试规划-2026-10-06.md) v1.1（§0.2–§0.5、§3、§4、§5） |

> **本文的定位**：`01-基线事实清单.md` 回答「事实是什么」；本文回答「**怎么跑、跑出的东西怎么留、留成什么样才算数**」。
> 本文所有命令都是 **PowerShell 7（pwsh）** 可直接粘贴执行的形态，每条都实测过或明确标注未实测。

---

## 0. 五条铁律（先读，违反其中任何一条则该批结论作废）

| # | 铁律 | 判据（可判定） | 违反后果（本项目已发生过的真实事故） |
| --- | --- | --- | --- |
| **R-1** | **真实库零改动** | 每批**开始前**与**全部命令跑完后**各执行一次 `(Get-FileHash app.db -Algorithm SHA256).Hash`，两次都必须等于 `F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065` | 历史上真实库 SHA256 曾由 `BD18DA81…B0CCC` 变为 `F5DA2306…0E0F065`（`create_app()` 启动自愈写到当前库） |
| **R-2** | **一切数据级验证只走三类授权通道**（§2.2）：① `make_app()` 副本 ② `file:app.db?mode=ro` 只读连接 ③ 作业临时目录 | 命令里出现 `sqlite:///` 或任何写操作时，**必须能指出**它落在副本/临时目录上；`make_app()` 自带最后一道闸（[_test_bootstrap.py:40-45](../../../scripts/_test_bootstrap.py#L40-L45)），URI 未落在副本就抛异常 | 见 R-1 |
| **R-3** | **禁止 `flask db migrate`**；`flask db *` 前先把 `DATABASE_URL` 指向目标库 | 命令历史里不得出现 `flask db migrate`；跑 `flask db *` 的命令块第一行必须是显式 `$env:DATABASE_URL=...` | 自动生成迁移会把 31 张不在迁移历史里的表全部纳入，产生与线上库冲突的脚本 |

> `D-1`～`D-10`（规划 §0.4）是**每批 DoD** 的清单；`R-1`～`R-5` 是**每次敲命令**的底线。两者不重复：`R-*` 管「怎么敲」，`D-*` 管「一批交付算不算完」。

### R-4（执行纪律，captain 本轮同步，已并入本 Runbook）：**脚本一律加 `scripts/_sandbox_compat.py` 前缀，不区分「原生可跑 / 需垫片」**

| 项 | 内容 |
| --- | --- |
| 规则 | 所有 `scripts/` 下脚本统一写成 `& $py -B scripts/_sandbox_compat.py scripts/<x>.py`；**唯一例外**是 3 个纯静态脚本（`check_templates` / `check_migration_heads` / `check_properties`），标注「**原生与垫片均可**」 |
| 为什么「不区分」 | `route_inventory` 的原生成败**随会话环境变化**（§8-I-1：t1 原生 exit 0，captain 与我本轮原生均 exit 1）。按脚本分档写 Runbook ⇒ 换一个会话就翻车，且失败信息看起来像代码缺陷 |
| 双重取证 | `route_inventory` 与 `check_db_bootstrap` 的**原生失败**由 captain 与本文各自独立复现（同一条 `PermissionError` → `shutil.copy2` → `%TEMP%\dsh-*\wms_test_*\app.db`），故「必须垫片」不再是单一来源结论 |
| 副作用 | 垫片会 `chdir` 到被测脚本目录（§2.4-②），且**不能**让「覆盖写已存在文件」变可能（§2.3）⇒ 输出落点规则见 §4.4 |

### R-5（全战役纪律，captain 2026-10-06 升级为全战役要求）：**解释器只写绝对路径 `F:\Miniconda\envs\wage\python.exe`，永不用裸 `python`**

| 项 | 内容 |
| --- | --- |
| 规则 | 所有命令一律 `$py = 'F:\Miniconda\envs\wage\python.exe'` 再用 `& $py ...`；**禁止**裸 `python` / `py` / `python3` |
| 为什么 | PATH 上的 `python` 指向**另一个解释器**（本轮实测 = `C:\Users\<user>\.conda\pkgs\python-3.9.21-h8205438_1\python.exe`），**同版本号但无项目依赖**（`import flask` → `ModuleNotFoundError`，exit 1） |
| ⚠ **最阴的坑（本轮实测，务必记进台账 `notes`）** | 裸 `python -V` **成功**并打印 `Python 3.9.21`，与目标解释器**版本号完全相同** ⇒ **任何「先看版本号」的自检都发现不了问题**；只有真正 `import` 才暴露 |
| 正确自检（替代「`python -V` 就算通过」） | `& $py -c "import flask, sqlalchemy; print(flask.__version__, sqlalchemy.__version__)"` → 期望 `3.1.2 / 2.0.44`，exit 0 |
| 判据 | 台账 `env.python` **必须**填绝对路径；`commandsRun` 里出现裸 `python` ⇒ 该行**判无效**（证据等级降为 `E-4`） |

---

## 1. 前置检查（每次开工先跑，60 秒）

```powershell
$py = 'F:\Miniconda\envs\wage\python.exe'          # ⚠ 必须绝对路径（R-5）；PATH 上的 python 是别的解释器
Set-Location 'D:\workspace\wage_management_system - bak'

# ① 解释器与产物根（⚠ 不要用 `python -V` 自检：它会打印同样的 3.9.21 却 import 不了 flask）
& $py -c "import flask, sqlalchemy; print(flask.__version__, sqlalchemy.__version__)"   # 期望 3.1.2 2.0.44
New-Item -ItemType Directory -Force -Path '.analysis-scratch' | Out-Null

# ② 真实库基线（开工前）
(Get-FileHash app.db -Algorithm SHA256).Hash        # 期望 F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065

# ③ 工作区干净度（只应有本批有意修改/新增）
git status --short
```

**实测环境事实（本轮）**：

| 项 | 实测值 | 说明 |
| --- | --- | --- |
| `app.db` | 2531328 B / 75 表 / 6713 行 / 0 视图 / `alembic_version=f179636cecf0` | 见 §2.2 CH-1 输出 |
| `.tmp_probe/wms_test_l8phjjio/` | 存在且**不可读、不可删** | `git status` 的 `warning: could not open directory` 来源；属**仓库卫生观察项**，非本批产物 |
| PATH 上的 `python` | **存在但是另一个解释器**（`.conda\pkgs\python-3.9.21-h8205438_1\python.exe`）：`python -V` = 3.9.21 ✅、`import flask` = `ModuleNotFoundError` ❌ | 见 R-5；**这是全环境最易上当的一处** |
| 控制台中文 | 直接 `& $py ...` 输出的中文**可能是乱码**（GBK/UTF-8 混用） | ⇒ 需要**逐字引用**的输出一律 `> file 2> file` 落盘，再 `Get-Content -Encoding UTF8` 读；或先 `$env:PYTHONIOENCODING='utf-8'` |

---

## 2. 通道矩阵（决定「这条命令能不能这么跑」）

### 2.1 三类通道与它们的边界

| 通道 | 形态 | 本轮实测 | 边界 |
| --- | --- | --- | --- |
| **CH-0 原生** | `& $py -B scripts/<x>.py` | 纯静态脚本可行；**依赖应用/临时目录的脚本会失败**（§2.3） | 不可作为「脚本已通过」的唯一依据 |
| **CH-1 只读连接** | `sqlite3.connect('file:app.db?mode=ro', uri=True)` | ✅ 可用（§2.2） | 只能读；不能建副本、不能造夹具 |
| **CH-2 副本夹具** | 新建 `.py` 文件 + `& $py -B scripts/_sandbox_compat.py .analysis-scratch/<x>.py` | ✅ 可用：副本可写、可建表（§2.2） | 是**唯一**能做数据级测试（写入/造夹具/差分）的通道 |
| **CH-3 垫片** | `& $py -B scripts/_sandbox_compat.py scripts/<x>.py` | ✅ 静态/可跑脚本全通 | 只放宽 `mkdtemp` mode 与子进程输出通道；**不能**让「覆盖写已存在文件」变可能 |

### 2.2 两条数据通道的实测证据（可直接复跑）

**CH-1 只读快照**（新建文件后运行；`-c` 内联见 §2.4 警告）：

```python
# .analysis-scratch/ch1_probe.py
import sqlite3
con = sqlite3.connect('file:app.db?mode=ro', uri=True)
print('alembic_version =', con.execute('select version_num from alembic_version').fetchall())
print('tables =', con.execute("select count(*) from sqlite_master where type='table'").fetchone()[0])
names = [r[0] for r in con.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'")]
print('total_rows =', sum(con.execute('select count(*) from "%s"' % n).fetchone()[0] for n in names))
print('views =', con.execute("select count(*) from sqlite_master where type='view'").fetchone()[0])
con.close()
```

```text
$ & $py -B .analysis-scratch/ch1_probe.py
alembic_version = [('f179636cecf0',)]
tables = 75
total_rows = 6713
views = 0
```

**CH-2 可写副本夹具**：

```python
# .analysis-scratch/ch2_probe.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts'))
from _test_bootstrap import make_app
app, copy_path = make_app(fresh=True)
print('copy =', copy_path)
print('copy exists =', os.path.exists(copy_path), 'writable =', os.access(copy_path, os.W_OK))
from app import db
from app.models import SystemConfig
with app.app_context():
    print('system_configs rows =', SystemConfig.query.count())
    db.session.execute(db.text("CREATE TABLE _probe_write_check (id INTEGER PRIMARY KEY)"))
    db.session.commit()
    print('DDL on copy OK')
```

```text
$ & $py -B scripts/_sandbox_compat.py .analysis-scratch/ch2_probe.py     # exit 0
copy = C:\Users\...\Temp\dsh-OJxwOK\wms_test_abnerwtw\app.db
copy exists = True writable = True
system_configs rows = 5
DDL on copy OK
(Get-FileHash app.db).Hash → F5DA2306…0E0F065   # 未变
```

⇒ **结论**：`make_app(fresh=True)` 是数据级测试的唯一入口；副本落在 `%TEMP%\dsh-<会话>\wms_test_<随机>\app.db`，**每次会话路径不同**。

### 2.3 沙箱写盘策略（本轮用正/负用例实测，是「请求型脚本为什么 exit 1」的根因）

| 动作 | 实测结果 | 证据 |
| --- | --- | --- |
| 工作区内**新建**文件（Python `open(...,'w')`，路径在会话内新目录） | ✅ 允许 | `.analysis-scratch/_new1.json` 写入成功 |
| 工作区内**新建**文件（Python，仓库根，`_python_new_probe.json`） | ✅ 允许 | 写入成功 |
| 工作区内**覆盖写已存在**文件（Python，仓库根，`_permission_matrix.json`） | ❌ `PermissionError: [Errno 13]` | 与 `smoke_test.py:186` / `permission_matrix.py:129` 同型 |
| 工作区内**覆盖写已存在**文件（PowerShell `Add-Content`） | ❌ `Access to the path ... is denied.` | 非 Python 特有，是**沙箱策略** |
| **父目录**写入（`open('../x.json','w')`，目标在会话内、原本不存在） | ✅ 允许 | `.verify_scratch/_reloc_probe.json` 写入成功 |
| `%TEMP%` 下 `mkdtemp` 默认 mode 0o700 后写入 | ❌ 被拒 | 需垫片（`_sandbox_compat.py`） |

⇒ **沙箱判据是「目标文件是否已存在」，不是「路径在不在工作区」**。这解释了：`route_inventory` 原生失败（`shutil.copy2` 要往 0o700 目录写）、`smoke_test`/`permission_matrix` 即使加垫片仍 exit 1（要**覆盖**仓库根已存在的 JSON）。

### 2.4 垫片的两个硬限制（本轮踩到，写下来省一次返工）

1. **`_sandbox_compat.py` 只接受脚本文件路径，不接受 `-c`**

   ```text
   $ & $py -B scripts/_sandbox_compat.py -c "print(1)"
   FileNotFoundError: [Errno 2] No such file or directory: '...\-c'
   ```

   ⇒ 内联代码要先写成 `.analysis-scratch/<name>.py` 再喂给垫片（见 §2.2 的形态）。

2. **垫片会 `os.chdir(dirname(被测脚本))`**（[_sandbox_compat.py:82](../../../scripts/_sandbox_compat.py#L82)）

   ⇒ 被测脚本里**相对路径的基准目录 = 该脚本所在目录**，不是你的 shell cwd。
   - 好处：把探针脚本放在 `.analysis-scratch/`，它写的 `../<file>` 自然落在**仓库根**（这正是 `route_inventory` 依赖 `ROOT/app.db` 能工作的原因）；
   - 陷阱：把脚本**复制**到别处再跑，`_test_bootstrap.ROOT` 会跟着变，报
     `FileNotFoundError: ...\.verify_scratch\app.db`。**不要用「复制脚本到别处」来重定位输出路径**。

---

## 3. 命令级 Runbook（逐条：命令 / 期望 / 超时 / 失败判读 / 采数）

### 3.1 静态 5 项（全批次必跑，规划 §3.2 已定名）

| # | 命令 | 期望输出（逐字） | 失败判读 |
| --- | --- | --- | --- |
| 1 | `& $py -B scripts/check_templates.py` | `parsed 87 files` / `44 declared / 40 used in templates / 44 used on routes` / `landing 5` / `RESULT: OK`，**exit 0** | 有违规 → 先修模板/权限，**不许改期望值** |
| 2 | `& $py -B scripts/check_migration_heads.py` | `HEADS=['p1nonctarget']` / `head_count=1  revisions=35` / `OK: 单一 head`，**exit 0** | 出现多 head → 迁移链被破坏 |
| 3 | `& $py -B scripts/check_properties.py` | `已扫描 23 个文件，模型类 74 个` / `RESULT: OK`，**exit 0** | 命中即「把 `@property`/不存在的列当列用」 |
| 4 | `& $py -B scripts/_sandbox_compat.py scripts/route_inventory.py` | `total rules=271` / `duplicate=0` / `GET no-arg=104 GET with-arg=56 non-GET=110`，**exit 0** | 数字漂移 → 有路由新增/丢失；`duplicate>0` → 端点重复注册 |
| 5 | `& $py -B scripts/_sandbox_compat.py scripts/check_db_bootstrap.py` | `64 账号` / `6712 行，跳过 0 张表` / `OK: 空库自举、幂等、无种子库跳过、整表无遗漏 均通过`，**exit 0** | `跳过 N 张表` → **整表插入失败**（曾因 DATETIME 裸 SQL 读成字符串让 24 张业务表全军覆没）；`首次 64 / 再次 64` 不等 → 幂等被破坏 |

**编号 1–3 另可原生跑**（本轮实测原生即 exit 0）：`check_templates.py` / `check_migration_heads.py` / `check_properties.py` 三项纯静态、不建临时目录 ⇒ 标注「**原生与垫片均可**」，其余脚本**一律加垫片**（R-4）。

**本轮实测（2026-10-06，逐条亲自跑）**：5 项**全 exit 0**，输出与上表逐字一致（编号 4/5 经垫片）。

> ⚠ **编号 4 的原生命令本轮实测 exit 1**，不是「本来就该加垫片」的传闻：
> `PermissionError: [Errno 13] ... \wms_test_vtfyb1hh\app.db`，栈顶是
> [_test_bootstrap.py:25](../../../scripts/_test_bootstrap.py#L25) 的 `shutil.copy2`。
> **与 t1（其记录为「原生 exit 0」）不一致**，冲突登记见 §8-I-1；处置：**一律用垫片**。
> **captain 本轮原生复跑得到同一失败**（`%TEMP%\dsh-*\wms_test_*\app.db`）⇒ 两条独立取证，R-4 成立。

### 3.2 请求型 / 功能型 4 项

| # | 命令 | 期望 | 本轮实测 | 结论可信度 |
| --- | --- | --- | --- | --- |
| 6 | `& $py -B scripts/_sandbox_compat.py scripts/functional_test.py` | `================ 结果：109 通过 / 0 失败 ================`，**exit 0** | ✅ 一致，`FAIL` 行 0 条，**exit 0** | **可信**（不写仓库根；[_test_bootstrap.py:501](../../../scripts/functional_test.py#L501) 附近写的是系统 TEMP 内 `child.py`） |
| 7 | `& $py -B scripts/_sandbox_compat.py scripts/smoke_test.py` | **（当前不可能拿到 exit 0）** | ✅ 8 身份 × 148 条 GET、`无 5xx / 异常 / 重定向死循环`，**exit 1** | **exit code 不可信**：断言全绿，随后 `:186` 覆盖写被拒 |
| 8 | `& $py -B scripts/_sandbox_compat.py scripts/permission_matrix.py` | **（同上）** | ✅ `匿名可访问 = 无（0）`、无校验视图 = 既有 5 个（`api_notification_stats`/`api_recent_notifications`/`manage_notifications`/`my_tasks`/`user_dashboard`），**exit 1** | 同上（`:129`） |
| 9 | 手工：`git status --short` + 真实库 SHA256 | 无新增污染 / SHA 不变 | ✅ 仅 `docs/test-reports/` 与两份未跟踪规划文档；SHA 未变 | — |

**编号 7/8 的判定口径（B3-01 完成前，唯一诚实的做法）**：

1. **不得**用 `$LASTEXITCODE` 判定这两条脚本；exit 1 在当前环境是**预期**，不是缺陷。
2. **必须**用「打印出的结论段」判定：把 stdout 落盘后 grep 关键行。
   - `smoke_test`：`无 5xx / 异常 / 重定向死循环` **且** 无 `[HTTP 5xx]` / `[EXCEPTION]` / `[REDIRECT_LOOP]` 行，**且** 8 个 `[done] <actor>: 148 条` 齐全。
   - `permission_matrix`：`=== 匿名可访问 ===` 下为 `无` **且** 「无校验视图」清单**不新增**（当前 5 个，逐名可比）。
3. **必须**在台账里把该行标为「**部分**：断言绿灯 / exit code 不可用」，并注明「待 B3-01 后改判 exit 0」。
4. **不得**把 `_smoke_results.json` / `_permission_matrix.json` 的内容当作"本轮产物"引用——它们 mtime 停在 `2026-10-06 10:13:00` / `20:39:57`，本轮**没有被写过**。矩阵数字的权威来源是**脚本 stdout 段**。

```powershell
# 采数模板（编号 7/8）：一切需要逐字引用的输出都落盘
$env:PYTHONIOENCODING='utf-8'
& $py -B scripts/_sandbox_compat.py scripts/smoke_test.py > .analysis-scratch/smoke.out 2> .analysis-scratch/smoke.err
$smokeExit = $LASTEXITCODE
& $py -B scripts/_sandbox_compat.py scripts/permission_matrix.py > .analysis-scratch/pm.out 2> .analysis-scratch/pm.err
$pmExit = $LASTEXITCODE
Get-Content .analysis-scratch/smoke.out -Encoding UTF8 | Select-String '无 5xx|\[HTTP|\[EXCEPTION|\[REDIRECT|\[done\]'
Get-Content .analysis-scratch/pm.out    -Encoding UTF8 | Select-String '匿名|guards=' 
# 记台账时同时写：$smokeExit = 1（预期，写盘被拒）/ $pmExit = 1（预期）
```

### 3.3 沙箱内**等价复核通道**（captain 本轮指定；本文实测其**当前受限形态**与**可用形态**）

`smoke_test` / `permission_matrix` 收尾要把结果写回**仓库根已存在**的 JSON，受限沙箱拒绝覆盖写（§2.3）⇒ 直接跑只能拿到 exit 1。
captain 指定「**复制现 JSON 到会话内新目录 + 哈希/diff 对比**」作为等价复核通道。本文按「四条纪律」把它写全，并**补齐一个实测发现**：

**通道 A（captain 指定：改由「写到新路径」取得等价结论）**

```powershell
$py = 'F:\Miniconda\envs\wage\python.exe'
Set-Location 'D:\workspace\wage_management_system - bak'
$env:PYTHONIOENCODING = 'utf-8'

# ① 先取「基准副本」到会话内新目录（沙箱允许新建文件）
New-Item -ItemType Directory -Force -Path '.analysis-scratch/baseline' | Out-Null
Copy-Item '_smoke_results.json'      '.analysis-scratch/baseline/_smoke_results.before.json'      -Force
Copy-Item '_permission_matrix.json'  '.analysis-scratch/baseline/_permission_matrix.before.json'  -Force

# ② 记录基准哈希（SHA256 = 报告内容的指纹，不是「跑成功的证明」）
Get-FileHash '.analysis-scratch/baseline/_smoke_results.before.json'     -Algorithm SHA256 | Select-Object Hash
Get-FileHash '.analysis-scratch/baseline/_permission_matrix.before.json' -Algorithm SHA256 | Select-Object Hash

# ③ 产物必须落到「新路径」再比：脚本目前**没有** --out / --no-dump（三条都没有，t1 读源码确认、本文 §2.4 实测确认）
#    ⇒ 在 B3-01 落地前，第 ④ 步的「新产物」在当前环境**取不到**；此通道只能用于「留基准 + 断言未改写」
#    落地后（预期形态）：
#    & $py -B scripts/_sandbox_compat.py scripts/smoke_test.py        --no-dump --out .analysis-scratch/new/_smoke_results.json
#    & $py -B scripts/_sandbox_compat.py scripts/permission_matrix.py --no-dump --out .analysis-scratch/new/_permission_matrix.json

# ④ 判据（B3-01 落地后生效）：新产物 vs ① 的基准副本 **SHA256 相同** / diff 为空 ⇒ 重跑未改变任何结论
```

**通道 A 的实测结论（必须照实写进台账，别把基准哈希当通过证据）**

| 观察 | 本轮实测 |
| --- | --- |
| 「脚本 cwd 重定位 ⇒ `../<report>.json` 落到新文件 ⇒ exit 0」 | ❌ **不可复现**。两种形态都试了：`Push-Location` 新目录 + 原脚本；把脚本**复制**到新目录再跑（后者还先被垫片的 `chdir` 打到 `FileNotFoundError: ...\.verify_scratch\app.db`）。最终都停在 `open('../_smoke_results.json','w')` 的同一 `PermissionError` |
| 根因（已用正/负用例定位） | 该通道要落地的目标**就是**仓库根那两个**已存在**文件；`../` 从会话内新目录解析回**仓库根**（垫片按**脚本所在目录**定基准，§2.4-②），于是撞上 §2.3 的「禁止覆盖写已存在文件」 |
| 反证（排除「相对路径算错」） | 同环境最小探针 `open('../<新名>.json','w')` **成功**（父目录写**新文件**是允许的）⇒ 失败点确定是「目标已存在」，不是路径解析 |
| 沙箱自证 | 本轮全部实跑结束后，`_smoke_results.json` mtime 仍为 `2026-10-06 20:39:57`、`_permission_matrix.json` 仍为 `2026-10-06 10:13:00` ⇒ 两文件**从未被改写**（与 t1 记录一致） |

**通道 B（本文推荐：受限沙箱内唯一能拿到「当前判定」的形态）**

1. **判定取自 stdout 结论段**（§3.2：`无 5xx / 异常 / 重定向死循环`、8×148、`匿名可访问 = 无`、无校验视图 5 个不新增），**不**取自 exit code、**不**取自根 JSON；
2. **用通道 A 的 ① + ④ 做「未改写」断言**：基准哈希在跑完后**仍等于**根文件哈希 ⇒ 证明这次实跑没有污染仓库产物（本轮成立）；
3. 台账标 `verdict=部分` + `evidence_level=E-1` + `exit_code=1` + `notes="exit 1 = 写盘被拒，非断言失败；判据取自 stdout"`。

**通道 C（t1 的结论如何引用）**：t1 记录「重定位后 exit 0，且产物与根 JSON SHA256 相同（`D301835F…`）」——**本轮无法复现其 exit 0**（上文）。⇒ 按 §4.1 记 `E-3 归因`，写清取证方，**禁止**升格为「可复跑」。
（附：根目录 `_smoke_results.json` 当前 SHA256 = `D301835F077D2EDFFCB5DA4469C87A23C594D1E9EC75010594C3A812466A9762`，与 t1 记录一致；这只能证明「文件没变」，不能证明「脚本跑绿了」。）

**根治**：B3-01 `--no-dump`（外加 `--out` 更彻底）一旦落地，判定立即升级为「exit code + 哈希对比」双判据，§3.2 的 grep 判读退役为回归保护。**不要**为了绕过它去改脚本输出路径（污染仓库语义，规划已明令禁止）。

### 3.4 反面 Runbook（把「不要踩的坑」也写成可执行判据）

| 现象 | **正确处置** | **错误处置（本项目已发生过）** |
| --- | --- | --- |
| `smoke_test` / `permission_matrix` 打印全绿却 exit 1 | 按 §3.2 口径判读 + 记「部分」 | ❌ 当代码回归去改生产代码；❌ 去改脚本输出路径（污染仓库语义） |
| `.verify_scratch/app.db` 找不到 | 认「复制脚本到别处」的形态错了（垫片 chdir），改回 §2.2 的 `.analysis-scratch/<probe>.py` | ❌ 往新目录里也拷一份 `app.db`，制造第二个「看似正确」的形态 |
| `%TEMP%` 下 `PermissionError` 指向 `wms_test_*` | 加垫片：`scripts/_sandbox_compat.py` | ❌ 改 `_test_bootstrap.py` 的 `mkdtemp`（会改动回归网本身） |
| 需要逐字引用中文输出时出现乱码 | `> file 2> file` 落盘 + `Get-Content -Encoding UTF8`；或先 `$env:PYTHONIOENCODING='utf-8'` | ❌ 凭记忆/凭控制台乱码「翻译」结论 |
| 想把 `_smoke_results.json` 当证据采集 | 采**脚本 stdout 结论段**（§3.2） | ❌ 把 mtime 未变的旧 JSON 当本轮产物 |

---

## 4. 证据留存规范

### 4.1 证据等级（四档，**只在台账里出现**，不得混用）

| 等级 | 含义 | 可写「结论」吗 | 例（本轮） |
| --- | --- | --- | --- |
| **E-1 实测** | 本轮亲自跑命令取得的**原始输出**（含 exit code） | ✅ 可直接引用 | 静态 5 项 exit 0；`functional_test` 109/0；`smoke_test` 148×8 + 无问题但 exit 1 |
| **E-2 源码级** | 只读源码/静态扫描得出，**未运行** | ✅ 但必须写「未运行」 | 「`quality_status` 唯一写入点是人 `PUT`」 |
| **E-3 归因** | 由**他人**（含前序任务/他人会话）实测，本轮未复现 | ⚠ 引用必须写取证方 | `smoke_test` 的 exit 0（归因 t1，本轮不可复现） |
| **E-4 未实测** | 明确未做，写清原因 | ❌ 不得当结论 | `check_db_bootstrap` **原生**是否失败（本轮直接用垫片） |

> 与 t1 的「实测 / 源码级 / 未实测」三档兼容；**本文新增 E-3**，专治本项目反复出现的「引用他人结论时丢失取证方」。

### 4.2 一次实跑的「证据包」构成（缺一不可）

| # | 内容 | 形态 | 说明 |
| --- | --- | --- | --- |
| 1 | **命令原文** | 文本（照抄可跑，含 `$py` 全路径、`Set-Location`） | 不接受「跑了一下 smoke」这类描述 |
| 2 | **stdout / stderr** | 文件落盘（UTF-8）→ 关键行贴进台账 | 逐字引用必须来自落盘文件 |
| 3 | **exit code** | 数字（**或**明确写「不可用 + 原因」） | 见 §3.2 口径 |
| 4 | **真库 SHA256（前后各一次）** | 两个 64 位十六进制 | 满足 `R-1` |
| 5 | **环境指纹** | HEAD、Python 版本、`%TEMP%` 会话路径（若涉及副本） | 副本路径**每次会话不同**，缺了就无法解释「为什么别人跑不出来」 |
| 6 | **判定** | `通过` / `部分` / `失败` / `不可判定` | 只允许四值；「部分」「不可判定」必须写**缺口项** |
| 7 | **基准副本 + 哈希**（涉请求型脚本时必加） | `_evidence/.../baseline/*.before.json` + 两个 SHA256 | 跑前把根 JSON 复制到会话内新目录并记哈希；跑后复核根文件哈希未变 ⇒ 证明「未污染」（≠「跑绿了」，§3.3 通道 A/B） |

### 4.3 留存目录与命名（只新增、不覆盖；全程 gitignore-safe）

```text
docs/test-reports/
  2026-10/
    01-基线事实清单.md            # t1 结论性交付物
    07-实测Runbook与台账规范.md    # 本文（规范 + t7 自证记录）
    _evidence/                    # ← 运行证据，只增不改
      2026-10-06-t7/               # 命名：<日期>-<任务号或批次号>
        00-run-manifest.json       #   本次实跑台账（§5.2 的 JSON 骨架，必交）
        README.md                  #   可选：本次证据包索引 + 复跑说明
        <命令名>.out / .txt         #   原始输出（能落盘就落盘，见 §4.5 通道限制）
        <sha-before>.txt           #   真库 SHA256 前/后
  _probe/                          # 只读探针（t1 建，供复用）
```

**硬规矩**

1. **只增不改**：同一批次的证据**不许覆盖**；要重跑就新建 `2026-10-07-<批次>/`。覆盖会让「当时到底跑出什么」永久丢失。
2. **不落 gitignore 之外**：`_evidence/` 在 `docs/` 下，**属跟踪范围**——所以 **只放文本/JSON**；`app.db` 副本、`*.xlsx`、`%TEMP%` 截图一律不放（`app.db` 本身已有 `.bak` 先例，不要再多一个）。
3. **不许把脚本自己写的产物当证据**：`_smoke_results.json` / `_permission_matrix.json`（根目录、已 gitignore）**只**可作为「脚本确实跑过」的旁证；结论以 stdout 段为准。
4. **每条结论都要能指回证据**：优先写 `manifest#<ID>`（§5.3）；确需指向具体文件时写 `<相对路径>` + 小节编号，**不要**只写行号（会随编辑漂移，如 `smoke_test.py:186` 这类代码行号除外）。
5. **离场清理**：`.analysis-scratch/` 里的临时脚本与输出可在采数后删除（本轮已删）；但**已归档进 `_evidence/` 的是证据，不得删**。

### 4.4 沙箱内「输出落点」规则（与 R-4 的垫片前缀配套，一条都不能省）

| 场景 | 正确落点 | 实测依据 |
| --- | --- | --- |
| 需要**逐字引用**的 stdout/stderr | `> .analysis-scratch/<name>.out 2> <name>.err`，再 `Get-Content -Encoding UTF8` | 控制台中文会乱码（§1 环境表） |
| 探针/夹具脚本自身 | `.analysis-scratch/<name>.py`（垫片会 `chdir` 到这里，其 `../x` 落**仓库根**） | §2.2 CH-2；§2.4-② |
| **不要**把脚本复制到别处再跑 | — | 垫片按脚本目录定 `ROOT` ⇒ `FileNotFoundError: ...\<新目录>\app.db`（§2.4-②） |
| 请求型脚本的 `_smoke_results.json` / `_permission_matrix.json` | **改不了落点**（硬编码 `../`，当前无 `--out`）⇒ 判定走 stdout；跑前/跑后比哈希证明未改写 | §3.3 通道 A/B |
| 证据归档 | `docs/test-reports/2026-10/_evidence/<日期>-<批次>/`，**只增不改** | §4.3 |

### 4.5 ⚠ 本环境实测限制：**shell 无法在 `docs/` 子树下落盘**（影响「重定向式归档」）

| 写入方式 | `.analysis-scratch/` | `docs/` 及其子目录 | 判定 |
| --- | --- | --- | --- |
| `Set-Content` / `Add-Content` / `Out-File` / `New-Item` | ✅ 成功 | ❌ `Access to the path '...' is denied` | **按目录树分档，不是按「文件是否已存在」** |
| `cmd /c echo x > file` | ✅ 成功 | ❌ `Access is denied.` | 同上 |
| 结构化写入通道（`write` 类工具） | ✅ 成功 | ✅ 成功 | 与上行**不一致** ⇒ 归档须走此通道 |
| ACL 对比 | `.analysis-scratch` 与 `docs/test-reports/2026-10` 的 ACE 列表**逐项相同** | 同上 | ⇒ 差异来自**沙箱策略**，不是目录权限本身 |

**因此本 Runbook 的归档纪律（覆盖 `Tee-Object` 写法）**：

1. 采数阶段把 stdout/stderr 落 `.analysis-scratch/`（**可以**正常重定向），用于**当场判读**；
2. 需要长期留存的**结构化证据**（台账 JSON、结论摘要、SHA 前后值）用**结构化写入通道**写进 `_evidence/`；
3. **不要**把「`Tee-Object $ev/xxx.txt`」写成纪律——本环境会静默失败（`Set-Content ... denied`），只剩控制台输出，
   而控制台中文还会乱码 ⇒ 等于没留证据。附录 A 的命令块已按此改写（输出先落 `.analysis-scratch/`，再人工归档关键行）；
4. 若某批次**必须**留下大体积原始输出（如 `smoke_test` 8×148 条明细 ≈ 250KB），**标注**「本环境不可自动化归档」，
   并在 `00-run-manifest.json` 的 `artifacts_note` 写清原因 —— **不得**写一个不存在的 `artifact` 路径充数。

> 这条与 §2.3 是**两条独立**的环境规则：§2.3 管「目标文件已存在 ⇒ 拒绝覆盖」，本节管「`docs/` 子树 ⇒ 整个拒绝」。
> 两者叠加的结果是：**请求型脚本的根 JSON 改不动、证据输出也不能直接落进证据目录**。
> **副产物**：本轮验证这条规则时留下的 0 字节 `_writer_probe.txt` **连删除也被拒**（`Remove-Item → Access denied`）⇒ 已登记为台账 `GAP-8`，并在 `artifacts_note` 说明它不是交付内容。**这就是「证据目录只增不减」在本环境的真实含义**。

---

## 5. 结果台账格式（`00-run-manifest.json` + 人读版）

### 5.1 为什么是两张表

- **人读表**（Markdown）进交付文档：一屏看清「哪条过了、哪条没跑、卡在哪」；
- **机读表**（JSON）进 `_evidence/`：字段固定，便于跨批次 diff（「上次 271、这次 272」这种漂移必须能被机器发现）。

**两者的字段必须一一对应**；任何手工补充都要同时写两处，否则以 JSON 为准。

### 5.2 机读台账骨架（字段冻结，新增字段只能追加）

```json
{
  "manifest_version": "1.0",
  "run_id": "2026-10-06-t7",
  "task_id": "t7",
  "attempt_id": "06e9f3c9-252a-4ab1-83c5-c860da3599ad",
  "operator": "测试流程优化工程师",
  "started_at": "2026-10-06T00:00:00+08:00",
  "finished_at": "2026-10-06T00:00:00+08:00",
  "env": {
    "workdir": "D:\\workspace\\wage_management_system - bak",
    "git_head": "f60a54d07cfea3aa7c21111a7efa70c267b4b1c2",
    "python": "F:\\Miniconda\\envs\\wage\\python.exe (3.9.21)",
    "sandbox": "DSH workspace-write",
    "temp_session_root": "C:\\Users\\<user>\\AppData\\Local\\Temp\\dsh-<session>"
  },
  "db_invariant": {
    "target": "app.db",
    "sha256_before": "F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065",
    "sha256_after": "F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065",
    "verdict": "通过"
  },
  "results": [
    {
      "id": "G4",
      "name": "route_inventory",
      "channel": "CH-3 垫片",
      "command": "& $py -B scripts/_sandbox_compat.py scripts/route_inventory.py",
      "exit_code": 0,
      "expected": "total rules=271 / duplicate=0 / 104+56+110",
      "observed": "total rules=271 / duplicate (method,path) registrations=0 / GET no-arg=104 GET with-arg=56 non-GET=110",
      "verdict": "通过",
      "evidence_level": "E-1",
      "criterion_digest": "counts:rules=271,dup=0,get0=104,getarg=56,nonget=110",
      "reproducible": true,
      "duration_s": 12,
      "notes": "",
      "blocked_by": null
    }
  ],
  "gaps": [
    {
      "id": "GAP-1",
      "item": "smoke_test / permission_matrix 的 exit code",
      "state": "不可用",
      "reason": "沙箱禁止覆盖写仓库根已存在文件（脚本 :186 / :129）",
      "action": "判据改用 stdout 结论段；根治见 B3-01 --no-dump",
      "owner": "批次3"
    }
  ]
}
```

**字段规则（越界即视为台账无效）**

| 字段 | 取值 | 规则 |
| --- | --- | --- |
| `verdict` | `通过` / `部分` / `失败` / `不可判定` | **只四值**；`部分` 与 `不可判定` **必须**同时出现在 `gaps` 里 |
| `evidence_level` | `E-1` / `E-2` / `E-3` / `E-4` | `E-3` 必须写清取证方（`notes` 里写「归因 t1」）；`E-4` 不得进 `通过` |
| `exit_code` | 整数 **或** `null` | `null` **必须**配 `notes` 写原因；**禁止**用退出码推断结论（§3.2） |
| `criterion_digest` | `k=v,k=v` 机器可比对 | **凡命令输出含计数/数字的都必须填**——这是跨批次漂移检测的唯一抓手 |
| `env.python` | **绝对路径**（本战役固定为 `F:\Miniconda\envs\wage\python.exe (3.9.21)`） | **R-5 强制**：只允许绝对路径；填裸 `python` 的台账判无效。阶段二所有实测任务复用本字段冻结 |
| `channel` | `CH-0`～`CH-3`（§2.1） | 决定这条结论在别人机器上能否复现 |
| `reproducible` | 布尔 | 判据：**同会话同命令再跑一次能否得到同一 `observed`**。`false` 必须在 `notes` 写原因（如「依赖外部库行数」「t1 取证、本环境不可复现」） |
| `artifact` | 相对路径 | 若填写，**必须真实存在**；填写了不存在的 `artifact` 即该行降级为 `不可判定`。**本轮建议一律留空**并把原始输出并入 `00-run-manifest.json`——理由见 §4.5（本环境 `docs/` 子树不接受 shell 重定向落盘，而 `smoke_test` 原文约 250KB 不适合经结构化写入通道搬运） |

### 5.3 人读台账（贴进任意交付文档）

| ID | 检查项 | 通道 | 期望 | 实测 | exit | 判定 | 等级 | 证据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| G1 | `check_templates` | CH-0 | `RESULT: OK` / 87-44-40-44-landing5 | 逐字一致 | 0 | 通过 | E-1 | `manifest#G1` |
| G2 | `check_migration_heads` | CH-0 | 单 head / 35 修订 | 逐字一致 | 0 | 通过 | E-1 | `manifest#G2` |
| G3 | `check_properties` | CH-0 | 23 文件 / 74 模型 / `OK` | 逐字一致 | 0 | 通过 | E-1 | `manifest#G3` |
| G4 | `route_inventory` | CH-3 | 271 / 0 / 104+56+110 | 逐字一致（原生命令另跑一次 = exit 1） | 0 | 通过 | E-1 | `manifest#G4` |
| G5 | `check_db_bootstrap` | CH-3 | 64 账号 / 6712 行 / 跳过 0 | 逐字一致 | 0 | 通过 | E-1 | `manifest#G5` |
| F1 | `functional_test` | CH-3 | 109/0 | 109 通过 / 0 失败，`FAIL` 行 0 | 0 | 通过 | E-1 | `manifest#F1` |
| F2 | `smoke_test` | CH-3 | 0 问题 | 8 身份 × 148 条 / `无 5xx / 异常 / 重定向死循环` | **1** | **部分** | E-1 | `manifest#F2` |
| F3 | `permission_matrix` | CH-3 | 匿名 0 / 无校验不新增 | 匿名 `无`；无校验 5 个（同名） | **1** | **部分** | E-1 | `manifest#F3` |
| F4 | `smoke_test` exit 0 | CH-3 重定位 | exit 0 | **`../` 落回仓库根已存在文件 → PermissionError** | 1 | **不可判定** | E-4 | `manifest#F4` |
| C1–C5 | 三条通道 + 写盘正负用例 + 解释器纪律 | CH-1/CH-2/CH-3/CH-0 | 见 §2.2 / §2.3 / §0 R-5 | 逐条一致 | 0/1 | 通过 | E-1 | `manifest#C1`…`#C5` |
| I1 | 真库 SHA256 | CH-0 | `F5DA2306…0E0F065` | 3 次复核（开工/首轮后/归档后）均相同 | — | 通过 | E-1 | `manifest#I1` |
| I2 | 工作区污染 | CH-0 | 仅本批有意新增 | 仅 `docs/test-reports/` + 2 份既有未跟踪文档 | 0 | 通过 | E-1 | `manifest#I2` |

> 证据引用统一写 `manifest#<ID>`（指向 `_evidence/<run>/00-run-manifest.json` 的 `results[].id`）——**比写文件名更稳**：文件会重命名/搬家，`id` 不会；且 §5.4 的漂移差分正是按 `id` 对齐的。

> **F2/F3 的「部分」是本表的重点**：这类行**最容易被误读成「跑绿了」**。规则是——只要 `exit` 与 `verdict` 方向不一致，就必须在 `notes` 写一行「exit 1 = 写盘被拒，非断言失败；判据取自 stdout」。
> **F4 是「无法复现的别人结论」的标准记法**：`不可判定 + E-4 + 写明阻断命令`，绝不写成「通过」。

### 5.4 跨批次漂移检测（台账存在的真正价值）

```powershell
# 对同批次的两份 manifest 做 criterion_digest 差分（人工也行，字段已机器可比）
$new = (Get-Content '.analysis-scratch/manifest-new.json' -Encoding UTF8 | ConvertFrom-Json).results
$old = (Get-Content '.analysis-scratch/manifest-old.json' -Encoding UTF8 | ConvertFrom-Json).results
foreach ($n in $new) {
  $o = $old | Where-Object { $_.id -eq $n.id }
  if ($o -and $o.criterion_digest -ne $n.criterion_digest) { "DRIFT $($n.id): $($o.criterion_digest) -> $($n.criterion_digest)" }
}
```

**必须报漂移的字段**：`rules=271`、`templates=87`、`capabilities=44`、`head_count=1`、`revisions=35`、`rows=6712`、`accounts=64`、`functional_pass=109`、`anon_open=0`、`no_guard_views=5`。
任一项变化 ⇒ **先判定「是有意变更还是回归」**，再继续；不做这一步的批次结论不得进入 DoD。

### 5.5 度量口径（沿用 §8.5 的「不得互替」）

台账里凡出现 `75` / `5` / `15+2` / `6713` / `6712` / `74` / `75`（表数）**必须带口径后缀**，例如：

- `no_guard_views=5(current,source-scope)` 而不是 `无校验=5`；
- `rows=6712(check_db_bootstrap,business-tables)` vs `rows=6713(mode=ro,all-tables)`——差 1 行是 `alembic_version`；
- `tables=75(含 alembic_version)` vs `tables=74(metadata)`。

**口径不明的数字一律不进台账**（这是本项目历史上最贵的返工来源）。

---

## 6. 流程改进设计（按「先做最省事的、收益最广的」排序）

| # | 改进项 | 现状（本轮实测） | 成本 | 收益 | 验收判据 | 对应既有条目 |
| --- | --- | --- | --- | --- | --- | --- |
| **P-1** | **落地 `--no-dump`**（三条请求型脚本） | **一条都没实现**（`sys.argv` 无解析）：`smoke_test`/`permission_matrix` exit 1 掩盖绿灯；`functional_test` 暂可信但无保护 | S–M | 让 `exit code` 重新成为判据；§3.2 的 grep 判读（脆弱、需人读）可退役 | ① 无失败=exit 0；② 故意改坏一条断言=非 0；③ `--no-dump` 下根 JSON **mtime 不变** | 规划 B3-01 |
| **P-2** | **把「通道」写进脚本用法**（每个脚本 docstring 标注 CH-0/CH-3 与是否需垫片） | 现在只能靠 AGENTS.md 一段话 + 口口相传；t1 与本文对同一命令给出相反结论（§8-I-1） | S | 消除「同一命令两种结论」 | 5 个静态 + 4 个请求型脚本 docstring 均含 `通道:` 行 | 新增（本文建议） |
| **P-3** | **`check_db_bootstrap` 原生失败也登记**（本轮只测了垫片通道） | 原生命令状态未知（t1 也标「未实测」） | S | 补齐 `E-4` 缺口 | 原生跑一次，记录 exit + 首行错误 | §7.2 未实测项 |
| **P-4** | **台账自动化**：把 §5.2 的 `manifest.json` 生成动作脚本化（跑完门禁自动填 `verdict/exit/criterion_digest`） | 全靠手工抄，易漏 `exit_code` 与 `channel` | M | 每批省 0.3–0.5 人日；漂移检测可常态化 | 一条命令产出 manifest 且字段完整；人工只填 `notes` | 新增（配合 B3-01 同批做最省力） |
| **P-5** | **把 `_evidence/` 纳入批次 DoD**（每批必须有 `00-run-manifest.json`） | 目前证据散在文档叙述里，跨批无法 diff | S | 「凡已修结论必须可复跑」（D-9）有了载体 | 批次交付物清单含 `_evidence/<日期>-<批次>/00-run-manifest.json` | 规划 §4/§5 |
| **P-6** | **`flake8`/`pyflakes` 类语法闸门缺位** | 静态 5 项里没有语法/未定义名检查（`check_properties` 只查属性误用） | S–M | 抓 `NameError` 级问题（历史上靠踩坑发现） | 新增脚本进 §3.2 表格并 exit 0 | 本文建议（与 T-H 同族盲区） |
| **P-7** | **`tests/` 单元层规划**（当前 0 个用例） | §6.2 实测：仅空目录 | L | 有回归保护网 | 不在本轮范围；仅登记 | t2/t6 归口 |

> **优先级判据**：P-1 是「其他所有结论都要打折」的根因（规划 §1.0 依据-4 已定性），**先做**；
> P-2/P-3/P-5 是**零风险文档级**改动，可与 P-1 同批；P-4 与 P-1 同批做最省力（都要动请求型脚本的收尾段）；P-6/P-7 归后续批次。

### 6.1 长期建议（不属本轮 inScope，仅登记）

1. `.tmp_probe/wms_test_l8phjjio/` 不可读不可删 → 请在有权限环境执行一次清理，并考虑把 `.tmp_probe/` 加入 `.gitignore`（现 `git status` 每跑都告警）。
2. 沙箱「禁止覆盖写已存在文件」是**环境约束**不是代码缺陷：所有「脚本收尾写固定路径」的形态都应改成**写新文件**（时间戳/`--out` 参数），这与 P-1 同向。
3. `app.db.bak-20260811_133143` 仍在仓库根：建议按「证据归档」而非「散落根目录」处理（`_evidence/` 只放文本，此处建议移出仓库或明确归档位置）。

---

## 7. 本轮（t7）自证记录

> 本文档本身按 §4.2 的「证据包」要求留证；机读台账见 `docs/test-reports/2026-10/_evidence/2026-10-06-t7/00-run-manifest.json`（16 条 `results` + 8 条 `gaps`）。

| 项 | 值 |
| --- | --- |
| HEAD | `f60a54d07cfea3aa7c21111a7efa70c267b4b1c2` |
| Python | `F:\Miniconda\envs\wage\python.exe` 3.9.21（**绝对路径，R-5**）；PATH 上的裸 `python` 是同版本号但无依赖的另一解释器（见 C5） |
| 真库 SHA256（开工） | `F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065` |
| 真库 SHA256（首轮实跑后） | 同上（未变） |
| 真库 SHA256（归档复跑后） | 同上（未变）⇒ **3 次复核** |
| 实跑批次 | 3 轮（首轮逐条验证 13 条命令；第二轮归档复跑 7 条门禁命令；第三轮 R-5 解释器差分，输出与前轮一致） |
| 判定 | 静态 5 项**通过**；`functional_test` **通过**；`smoke_test`/`permission_matrix` **部分**（止损于写盘）；`check_db_bootstrap` 原生 **未实测（E-4）**；cwd 重定位通道 **不可判定** |
| 污染 | `git status --short` 仅 `docs/test-reports/`（本文与 `_evidence/`）与两份既有未跟踪规划文档；`.analysis-scratch/` 临时脚本与输出已删除 |
| 证据归档 | 仅 `00-run-manifest.json` 结构化落盘；逐条 stdout 原文**未**归档（§4.5 环境限制 + `smoke_test` 原文 ≈250KB），`artifacts_note` 已写明 |
| 未清残余 | `_evidence/.../_writer_probe.txt`（0 字节，**删除被沙箱拒绝**）⇒ 台账 `GAP-8`；`.analysis-scratch/` 与仓库根的 `_write_probe.txt` 等**其他队友**的中间文件未动（不越界清理） |

---

## 8. 本轮新发现（与 t1 基线的差异 / 补充）

### 8-I-1 `route_inventory` **原生**命令：本轮 exit 1（与 t1「原生 exit 0」冲突）

| 项 | 内容 |
| --- | --- |
| t1 记录 | §6.7：「`route_inventory` ✅ **本轮原生也可跑**」，并据此登记 §8 冲突项 X-13，反驳规划 D20 |
| 本轮实测 | `& $py -B scripts/route_inventory.py` → **exit 1**，`PermissionError: [Errno 13] ... \Temp\dsh-OJxwOK\wms_test_vtfyb1hh\app.db`，栈顶 [_test_bootstrap.py:25](../../../scripts/_test_bootstrap.py#L25) `shutil.copy2`；同一命令加垫片 → **exit 0** |
| 根因（可解释两者的分歧） | `make_app()` 写的是 **`%TEMP%\dsh-<会话>\wms_test_<随机>\app.db`**——**会话级临时根，每次会话不同**（本轮为 `dsh-OJxwOK`）。沙箱对 `mkdtemp` 生成的 0o700 目录的写入许可是**环境态**，不是代码态 |
| 结论 | **规划 D20「原生必失败」在本轮成立**；t1 与本文的差异属**环境差异**，不属谁写错。⇒ **处置：一律用垫片**；台账 `channel` 必须记 `CH-3` |
| 影响 | 若下游按 t1「原生可跑」写 Runbook，会在别的会话上 100% 失败（且失败点看起来像代码问题） |

### 8-I-2 `_sandbox_compat.py` 的两个未登记限制（§2.4）

① 不接受 `-c`；② 会 `chdir` 到被测脚本目录。两者都会让「按直觉写的命令」失败，且失败信息不指向真正原因。

### 8-I-3 沙箱写盘判据 = 「目标文件是否已存在」（§2.3）

正/负用例各两条（Python + PowerShell 双证）。这条把 t1 §6.6/§6.7 的「写盘被拒」从「现象」升级为**可判定的环境规则**，也是 §3.3「t1 的重定位通道本轮不可复现」的直接解释。

### 8-I-4 解释器：PATH 上的 `python` 是另一个解释器，且**同名版本号使版本自检失效**（R-5 / `manifest#C5`）

| 项 | 内容 |
| --- | --- |
| 现象 | `GET-Command python` → `C:\Users\<user>\.conda\pkgs\python-3.9.21-h8205438_1\python.exe`，**与 `F:\Miniconda\envs\wage\python.exe` 同为 3.9.21** |
| 危害 | 裸 `python -V` → `Python 3.9.21` **exit 0**（自检「通过」）；裸 `python -c "import flask"` → `ModuleNotFoundError` **exit 1**。⇒ 任何「先看版本号」的前置检查都发现不了，错误会在真正 import 项目代码时才炸 |
| 正确自检 | `& $py -c "import flask, sqlalchemy; print(flask.__version__, sqlalchemy.__version__)"` → `3.1.2 2.0.44`，exit 0 |
| 处置 | §0 **R-5** 定为全战役纪律（captain 2026-10-06 升级）；§1 前置检查已改为 import 自检；台账 `env.python` 强制绝对路径，`commandsRun` 出现裸 `python` 即该行判无效（E-4） |

### 8-I-5 `tests/` 与请求型脚本的 exit code 缺口，本轮**未**获得新证据推翻 t1

`tests/` 仍无测试文件；`--no-dump` 仍未实现（本文 §6 P-1）。二者与 t1 结论一致。

### 8-I-6 新增环境规则：**shell 在 `docs/` 子树下落盘被整体拒绝**（§4.5）

| 项 | 内容 |
| --- | --- |
| 现象 | `pwsh` 的 `Set-Content` / `Add-Content` / `Out-File` / `New-Item` / `cmd /c echo >` 在 `docs/` 及其子目录下**一律** `Access denied`；同样命令在 `.analysis-scratch/` 正常 |
| 反证 | 结构化写入通道（`write`）在同一 `docs/.../_evidence/...` 目录下**成功**创建文件 ⇒ 差异来自**沙箱策略**而非目录 ACL（`Get-Acl` 两处 ACE 逐项相同） |
| 影响 | ① 附录 A 原「`Tee-Object $ev/xxx.txt`」写法会**静默失败**，只剩控制台输出（还会乱码）⇒ 等于没留证据；② 大体积原始输出（`smoke_test` ≈250KB）无法自动化归档 ⇒ 台账 `artifacts_note` 必须写明，**不许**填假路径 |
| 处置 | 采数落 `.analysis-scratch/`；结构化证据走证据写入通道；Runbook 归档纪律按 §4.5 三条执行 |
| 与 §2.3 的关系 | **两条独立规则**：§2.3 = 「目标文件已存在 ⇒ 拒绝覆盖」；§4.5 = 「`docs/` 子树 ⇒ 整树拒绝」 |

---

## 附录 A：可整段复制的「一批收尾」检查块

```powershell
$py = 'F:\Miniconda\envs\wage\python.exe'
Set-Location 'D:\workspace\wage_management_system - bak'
$env:PYTHONIOENCODING = 'utf-8'
$ev = 'docs/test-reports/2026-10/_evidence/' + (Get-Date -Format 'yyyy-MM-dd') + '-<批次或任务号>'
New-Item -ItemType Directory -Force -Path $ev, '.analysis-scratch' | Out-Null

# ① 真库基线（前）
(Get-FileHash app.db -Algorithm SHA256).Hash | Tee-Object '.analysis-scratch/db-sha-before.txt'

# ② 静态 5 项（全批次必跑；1–3 原生与垫片均可，4–5 必须垫片）
#    逐条落 .analysis-scratch/（可写）；需要归档的关键行再走证据写入通道搬进 _evidence/
& $py -B scripts/check_templates.py          2>&1 | Tee-Object '.analysis-scratch/static-gates.txt'
Write-Output "check_templates exit=$LASTEXITCODE"
& $py -B scripts/check_migration_heads.py    2>&1 | Tee-Object '.analysis-scratch/static-gates.txt' -Append
Write-Output "check_migration_heads exit=$LASTEXITCODE"
& $py -B scripts/check_properties.py         2>&1 | Tee-Object '.analysis-scratch/static-gates.txt' -Append
Write-Output "check_properties exit=$LASTEXITCODE"
& $py -B scripts/_sandbox_compat.py scripts/route_inventory.py 2>&1 | Tee-Object '.analysis-scratch/static-gates.txt' -Append
Write-Output "route_inventory exit=$LASTEXITCODE"
& $py -B scripts/_sandbox_compat.py scripts/check_db_bootstrap.py 2>&1 | Tee-Object '.analysis-scratch/static-gates.txt' -Append
Write-Output "check_db_bootstrap exit=$LASTEXITCODE"

# ③ 功能 1 项（exit code 可信）
& $py -B scripts/_sandbox_compat.py scripts/functional_test.py 2>&1 | Tee-Object '.analysis-scratch/functional_test.out'
Write-Output "functional_test exit=$LASTEXITCODE   # 期望 0，且输出含 109 通过 / 0 失败"

# ④ 请求 2 项（exit code 不可用：记录它，但按 stdout 判读）
& $py -B scripts/_sandbox_compat.py scripts/smoke_test.py 2>&1 | Tee-Object '.analysis-scratch/smoke_test.out'
Write-Output "smoke_test exit=$LASTEXITCODE          # 当前预期 1（写盘被拒），判据取 stdout 结论段"
& $py -B scripts/_sandbox_compat.py scripts/permission_matrix.py 2>&1 | Tee-Object '.analysis-scratch/permission_matrix.out'
Write-Output "permission_matrix exit=$LASTEXITCODE   # 当前预期 1，判据取 stdout 结论段"

# ⑤ 真库基线（后）+ 工作区
(Get-FileHash app.db -Algorithm SHA256).Hash | Tee-Object '.analysis-scratch/db-sha-after.txt'
Get-ChildItem _smoke_results.json,_permission_matrix.json | Select-Object Name,LastWriteTime   # 期望 mtime 未变
git status --short

# ⑥ 用证据写入通道产出 _evidence/<...>/00-run-manifest.json（§5.2 骨架），再跑 §5.4 漂移差分
```

> ⚠ `Tee-Object` 只落盘**该次**输出；同一文件多次 `-Append` 会让「命令 ↔ 输出」对应关系变模糊。**逐字引用前请给每段加一行 `=== <命令> ===` 分隔**，或分文件保存。
> ⛔ **不要**把 `Tee-Object` 直接指向 `_evidence/...`：本环境 `docs/` 子树拒绝 shell 落盘（§4.5），会静默只剩控制台输出。

## 附录 B：本文引用的实测坐标（便于复核）

| 坐标 | 文件 |
| --- | --- |
| `make_app()` / 隔离最后一道闸 | [_test_bootstrap.py:20-46](../../../scripts/_test_bootstrap.py#L20-L46) |
| 垫片放宽 `mkdtemp` / 子进程通道 / `chdir` | [_sandbox_compat.py:32-38](../../../scripts/_sandbox_compat.py#L32-L38)、[:46-75](../../../scripts/_sandbox_compat.py#L46-L75)、[:80-84](../../../scripts/_sandbox_compat.py#L80-L84) |
| `smoke_test` 收尾写盘 | [smoke_test.py:186-190](../../../scripts/smoke_test.py#L186-L190) |
| `permission_matrix` 收尾写盘 + 无条件 `return 0` | [permission_matrix.py:129-132](../../../scripts/permission_matrix.py#L129-L132) |
| `functional_test` 结论出口 | [functional_test.py:613](../../../scripts/functional_test.py#L613)（`return 1 if FAIL else 0`） |
| 静态 5 项期望值 | [01-基线事实清单.md](01-基线事实清单.md) §6.5 |
| DoD / 批次门禁组合 | [开发与测试规划-2026-10-06.md](../开发与测试规划-2026-10-06.md) §0.4 / §3.2 / §4 |
| `--no-dump` 条目 | 同上 §批次3 B3-01 |

## 附录 C：本文交付物

1. 本文 `docs/test-reports/2026-10/07-实测Runbook与台账规范.md` —— Runbook（§2–§3）+ 执行纪律（§0 R-1～R-4）+ 证据留存规范（§4）+ 台账格式（§5）+ 流程改进（§6）+ 自证与新发现（§7–§8）。
2. `docs/test-reports/2026-10/_evidence/2026-10-06-t7/00-run-manifest.json` —— §5.2 骨架的**实例填充**：16 条 `results`（含命令/exit code/期望/实测/`criterion_digest`/`reproducible`）+ 8 条 `gaps`。
3. **未修改任何生产代码 / 模板 / 配置 / 脚本**；真实库 `app.db` SHA256 三次复核均为 `F5DA2306…0E0F065`；`.analysis-scratch/` 临时脚本与输出已删除；`_permission_matrix.json` / `_smoke_results.json` mtime 未变。
