# recon-docs.md — 文档漂移对账（D1–D24 + AGENTS.md 门禁表 + 全部关键数字）

> **任务**：t7 [W6]（执行者：技术文档工程师2）。**性质**：只读对账 + 可直接照抄的**订正清单**（不修改 `docs/`、`AGENTS.md` 及任何既有文件）。
> **权威口径**：源码/脚本**现场实测**（本文件所有读数为 2026-10-08 01:0x–01:2x 本人实测，命令见 §7）。
> **本文件的定位**：按 `test-reports-2026-10/70-第2轮收口与阶段C移交.md:520` 的裁定（「`docs/` 树**不可覆写** ⇒ **只能新建订正件**」，同 `:526` §10.6），本文件的 §4「文档订正执行清单」即为**订正件的输入**，执行者照抄即可。

---

## 0. 元信息与硬口径（引用本文件时必须连口径一起引）

| 项 | 值 | 命令 / 口径 |
| --- | --- | --- |
| 实测时点 | `2026-10-08 01:03:18` ~ `01:2x`（本机本地时间） | `Get-Date -Format 'yyyy-MM-dd HH:mm:ss'` ⇒ `2026-10-08 01:12:07` 等 |
| 仓库根 | `D:\workspace\wage_management_system - bak` | `Get-Location` |
| 解释器 | `F:\Miniconda\envs\wage\python.exe` = Python **3.9.21** (MSC v.1929 64bit)；Flask 3.1.2 / SQLAlchemy 2.0.44 | `& $py -c "import sys,flask,sqlalchemy;…"` |
| git HEAD | `534ce70b204c767feee551e8fd04e538374b1de8` | `git rev-parse HEAD` |
| 真实库不变量（开工/收尾两次同值） | `app.db` = **2531328 B / SHA256 `F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065` / mtime `2026-09-18 12:50:55`** | `(Get-Item app.db).Length`、`(Get-FileHash app.db -Algorithm SHA256).Hash` |
| `app.db` 内 `alembic_version`（只读） | `f179636cecf0`（**未** stamp 到 `p1nonctarget`，属预期） | `sqlite3.connect('file:app.db?mode=ro',uri=True)` ⇒ `SELECT * FROM alembic_version` |
| `ci_gates.py` 指纹 | **69125 B / SHA256 `2EDB60DAE31C5D649E3A3177D5502AD2EB3438E85D5898DC7EC48C83EED75D09` / mtime `2026-10-07 22:22:17`** | `(Get-FileHash test-reports-2026-10/harness/ci_gates.py -Algorithm SHA256).Hash` |
| 沙箱模式（**重要边界**） | 本次会话 = **`danger-full-access`** ⇒ **无法复现**「受限沙箱（workspace-write 且禁写既有文件）下 PermissionError」这一类现象 | DSH 运行时约束；D14/D20 的沙箱侧只能登记口径、不能现场复证 |
| 本轮写盘 | **只新建** `test-reports-2026-10/reconcile-2026-10-08/` 下的文件（`recon-docs.md` + 2 个探针 + 2 个探针输出）；`git status --porcelain` 未出现任何既有文件被改 | §7.4 |

### 0.1 证据规则（本文件自守）

1. 每个数字给「**工具 + 口径 + 值**」三要素；不给转述值。
2. 行号**一律为本次实测**行号（文档行号已整体漂移；已验证样例：`AGENTS.md` 引 `routes.py:5067` 的 `save_temp_file`，实测 `:5083`）。
3. 同一对象多口径时口径写进括号（如 `271`=url_map 规则数 / `269`=装饰器数 / `265`=main 蓝图层）。
4. 文档与源码冲突 ⇒ 登记为漂移条目；**结论以源码为准**。
5. 无法实测的项明确标 `无法核实`（不猜）。

---

## 1. D1–D24 逐条现状表

> 口径来源：`docs/开发与测试规划-2026-10-06.md` **附录 E**（`:894-921`，D1–D24 原始表述 + 订正目标值）。
> 「今天是否仍漂移」判据：**该订正是否已落到当前仓库的文档文本里**（`docs/` 4 份背景文档 + `AGENTS.md` + 交接提示词），**不**判其结论值对不对。

| # | 原漂移内容（附录 E 原文） | 今天是否仍漂移 | 实测证据（file:line / 命令读数） | 逐字改法（原句 → 新句） |
| --- | --- | --- | --- | --- |
| **D1** | 「261 视图 / 102 inline role」→ 路由 271、内联 role **15 处**、无能力装饰器的 main 路由 8 个 | **是**（源文档未改） | `scripts/route_inventory.py` ⇒ `total rules=271`、`duplicate=0`；AST ⇒ `@bp.route` **269**（main 265 + auth 4）；main 视图 **265** = `@require_capability` **257** + 仅 `@login_required` **8**、无守卫 **0**；内联 `current_user.role` Python **15**（`routes.py` 5 / `quality.py` 10）+ 模板 **2** | `继续开发准备报告.md:14`：`44 能力/7 角色；261 个 main 视图 = 150 装饰器 + 102 inline role + 9 仅 login_required；0 无登录守卫` → `44 能力/7 角色；265 个 main 视图 = 257 个 @require_capability + 8 个仅 @login_required（无能力装饰器的 main 路由 8 个）；Python 内联 current_user.role 15 处（routes.py 5 + quality.py 10）+ 模板 2 处（契约豁免）；0 无登录守卫` |
| **D2** | 「194 路由 / routes.py 11557 行」→ 271（0 重复）/ **12127 行** | **已部分修正**：271/0 已确认；**12127 今天已过时**（见 D22） | `route_inventory` ⇒ 271 / duplicate 0；`routes.py` = 511969 B、`splitlines()`=**12155**、`\n`=12155、末行有换行、无 BOM、无 CRLF | `继续开发准备报告.md:24`：``routes.py` 约 1.1–1.2 万行 / 194 路由（两个成员分别实测 12214 与 11557 行，差异为统计口径）` → ``routes.py` **12155 行**（splitlines=12155 / LF=12155 / 末行有换行 / 无 BOM）；路由 **271**（`duplicate (method,path) registrations=0`）` |
| **D3** | 「2 个 head 待收敛」→ 单一 head `p1nonctarget` / 35 修订 | **已部分修正**（`继续开发准备报告.md:274` 已改「1 个」，但 `:21`/`:57`/`:67` 仍写 2 个 head） | `check_migration_heads.py` ⇒ `HEADS=['p1nonctarget']`、`head_count=1  revisions=35`、exit 0 | `继续开发准备报告.md:21`：`**2 个 head**（c2mespg001 / f179636cecf0）` → `**单一 head `p1nonctarget`（35 修订）**`（历史曾 2 head）；`:57`：`收敛 2 个 head（c2mespg001 / f179636cecf0）为单 head` → `（已完成）**单 head `p1nonctarget`（35 修订）**` |
| **D4** | 「31 模板 77 处 role」→ 模板 **2 处** + Python **15 处** | **已部分修正**（`:273` 已改；`:20`/`:50`/`:97`/`:105` 仍写 31 模板 77 处 / 102 inline） | AST 模板扫描 ⇒ `app/templates/main/quality/tasks.html:340`、`app/templates/main/quality/task_detail.html:13` = **2 处**；Python **15**（同 D1） | `继续开发准备报告.md:20`：`31 模板 77 处硬编码 role` → `模板 2 处 + Python 15 处内联 current_user.role`；`:50`：`31 模板 77 处硬编码 current_user.role` → `模板 2 处硬编码 current_user.role（quality/task_detail.html:13、quality/tasks.html:340）；Python 内联残留 15 处` |
| **D5** | 「`_ENSURED_COLUMNS` 8 表 23 列」→ **10 表 43 列** | **是** | AST 读 `app/__init__.py:21` 模块级 dict ⇒ **tables=10 / cols=43**，逐表 `sales_order_items=6 task_assignment=9 production_orders=6 production_batches=6 products=1 product_processes=2 finished_product=3 nonconformity_records=8 raw_material_categories=1 consumable_categories=1` | `继续开发准备报告.md:21`：``_ENSURED_COLUMNS` 覆盖 8 表 23 列` → ``_ENSURED_COLUMNS` 覆盖 **10 表 43 列**`` |
| **D6** | 「57 个 `.pyc` 跟踪 + `.gitignore` 3 行」→ `.pyc` **0**、`.gitignore` 已扩（`:32` 与 `:36-38`） | **已部分修正**（`继续开发准备报告.md:68`/`:275` 仍写 57 个；`:68` 仍写「`.gitignore` 仅 3 行」） | `git ls-files '*.pyc'` ⇒ **0**；`.gitignore` = **42 行**，`/uploads/temp/` 在 `:32`、`*.bak`/`*.new`/`*.backup` 在 `:36-38` | `继续开发准备报告.md:68`：`约 57 个 .pyc 已跟踪 + .gitignore 仅 3 行` → ``*.pyc` 已跟踪数 **0**（原 57 个已 `git rm --cached`）；`.gitignore` 已扩为 **42 行**（`/uploads/temp/` 在 :32，`*.bak/*.new/*.backup` 在 :36-38）` |
| **D7** | 「`app/main` 只有 `routes.py`」→ **8 个含路由的模块 / 10 个跟踪文件，漏列 `sales_routes.py`** | **是**（`AGENTS.md:91` + 交接文档仍未改） | AST `@bp.route` 模块：`app/main/routes.py` 192、`quality.py` 27、`equipment.py` 15、`purchase.py` 13、`production_center.py` 7、`shipping.py` 6、`stock.py` 5 = **main 7 个 / 265 条**；`app/auth/routes.py` 4 ⇒ **合计 8 模块 / 269 条**；`app/main` 跟踪文件 **10 个**（`__init__.py`/`forms.py`/7 路由模块/`sales_routes.py`）；`sales_routes.py` = **1 字节**、AST 路由 **0**、被 git 跟踪 | `AGENTS.md:91`：`**结论：`app/main` 下现只有 `routes.py` 一个路由模块；不要再按「包内有语法错误的备份文件」的说法去处理。**` → `**结论：`app/main` 下含 `@bp.route` 的路由模块共 7 个（`routes.py` 192 / `quality.py` 27 / `equipment.py` 15 / `purchase.py` 13 / `production_center.py` 7 / `shipping.py` 6 / `stock.py` 5 = 265 条），另有 1 字节死文件 `app/main/sales_routes.py`（被 git 跟踪、0 路由、0 引用，待删）。**` |
| **D8** | 「3 个后缀型残留其实被跟踪，原记录有误」→ **该订正本身错误**（`.gitignore:36-38` 本就忽略） | **D8 的结论本身不成立**（详见 §5 N-1） | `git ls-tree -l f60a54d^ -- app/main/routes.py.backup app/main/routes.py.bak app/main/routes.py.new` ⇒ **三个全部被跟踪**（blob `03227d3f…` 455184 B / `757d65ee…` 98687 B / `e69de29b…` 0 B）；`git show --name-status f60a54d` ⇒ 三者以 `D` 删除；`git show f60a54d^:.gitignore` ⇒ **无** `*.bak/*.new/*.backup`（这三条是 f60a54d **同一提交**新增） | 保留 `AGENTS.md:91` 原句（「**其实被 git 跟踪**」**是对的**）。把附录 E 的 D8 行改为：`「3 个后缀型残留其实被跟踪」→ **实测成立**：`git ls-tree f60a54d^` 命中三个文件，`git show --name-status f60a54d` 显示三者以 D 删除；`*.bak/*.new/*.backup` 是**删除它们的同一提交**才加入 `.gitignore` ⇒ 原「原记录有误」的**订正动作应撤回**` |
| **D9** | 「删 4 个备份文件」→ 同一提交删 **7 个** | **已部分修正**（`继续开发准备报告.md:220` 仍写「第 8 批（删除 4 个遗留备份文件…）」） | `git show --name-status f60a54d` ⇒ **7 个 `D`**（`routes.py.backup`/`routes.py.bak`/`routes.py.new` + `routes_backup.py`/`routes_full.py`/`routes_original.py`/`routes_with_duplicates.py`）；7 个 blob 合计 **2543015 B**（= 2.54 MB 十进制 / 2.43 MiB；其中 4 名字型 = 1989144 B = 1.99 MB 十进制 / 1.90 MiB） | `继续开发准备报告.md:220`：`第 8 批（删除 4 个遗留备份文件 + 统一 is_archived 两处 NULL 口径）` → `第 8 批（**同一提交删除 7 个遗留备份文件**，共 2543015 B = 2.54 MB 十进制 + 统一 is_archived 两处 NULL 口径）` |
| **D10** | 「HEAD == `148d8a5`」→ **`f60a54d`** | **两值都过时**（今天 `534ce70…`）；`交接提示词:8` 仍写 `f60a54d` | `git rev-parse HEAD` ⇒ `534ce70b204c767feee551e8fd04e538374b1de8`；`git log --oneline` 显示 `f60a54d`、`148d8a5` 均为其祖先 | `交接提示词-批次3开工-2026-10-06.md:8`：`仓库 HEAD = `f60a54d`，工作区干净` → `仓库 HEAD = `534ce70b204c767feee551e8fd04e538374b1de8`（2026-10-08 实测；本文写于 f60a54d 时点）` |
| **D11** | 「新增 4 端点」→ 路由清单实为 **5 个**（含 `/api/quality/records/export`） | **是** | `quality.py:1368 /api/quality/records/export`、`:1533 /api/quality/tasks/export`、`:1579 /api/quality/tasks/template`、`:1612 /api/quality/tasks/import`；`production_center.py:400 /api/production/generate-codes` ⇒ **5 个** | `开发进度与交接.md:345`：`**新增 4 个端点**` → `**新增 5 个端点**`；并在其清单补一行：`GET /api/quality/records/export（app/main/quality.py:1368，能力 quality.export）；` |
| **D12** | 「审计回滚用 `globals()` 反射」→ 已改 `getattr(app.models, …)`；**级联仍未处理** | **是**（`继续开发准备报告.md:281` 仍把 `globals()` 列为「仍未做」） | `routes.py:4182 def _resolve_audit_model`、`:4186 model_class = getattr(models_module, model_name or '', None)`；全仓 `globals()` 在 `routes.py` **仅** `:4183` 的 docstring（说明「用 globals() 取不到未 import 的模型」） | `继续开发准备报告.md:281`：`2. 审计回滚 `globals()[target_model]` 反射 + 不处理级联。` → `2. 审计回滚**已改为 `getattr(app.models, name)`**（routes.py:4182-4189，仅 docstring 保留 globals() 的历史说明）；**级联仍未处理**（delete 分支）。` |
| **D13** | 「模板 role 在 `tasks.html:337`」→ **`:340`** | **已部分修正**（`继续开发准备报告.md:50` 仍写 `:337`） | `app/templates/main/quality/tasks.html:340` 命中 `current_user.role` | `继续开发准备报告.md:50`：`quality/tasks.html:337` → `quality/tasks.html:340` |
| **D14** | 「门禁全部 exit 0 可复跑」→ 三条请求型脚本在受限环境 exit 1（写盘被拒） | **已修正于 `AGENTS.md`（`:92-94`）；docs 侧仍漂移** | 本环境实测：`smoke_test.py --no-dump` ⇒ `targets 148 / actors 8 / errors 0`、**exit 0**；`permission_matrix.py --no-dump` ⇒ 匿名 0 / 无校验 5 / C-06 四模块全绿、**exit 0**；源码 `smoke_test.py:246,266`、`permission_matrix.py:365,404` 证实 `--no-dump` 与 `.tmp/<RUN_ID>/` 落盘；`functional_test.py:497-502` 只写 `tempfile.mkdtemp()` 临时目录 ⇒ 不写仓库根 | `开发进度与交接.md:337`：`这几个脚本仍会重写根目录 `_permission_matrix.json` / `_smoke_results.json`（已 gitignore）。` → `E-03 后（2026-10-07，t4 交付）：`smoke_test.py` / `permission_matrix.py` 落盘已默认改到 `test-reports-2026-10/.tmp/<RUN_ID>/`（绝对路径、与 cwd 无关）并新增 `--no-dump`；**写盘失败只打 `[WARN] 落盘失败（不影响退出码）`** ⇒ 退出码与写盘已解耦。**复跑请一律带 `--no-dump`；上文「需经沙箱垫片」的说法同时作废**（本环境 danger-full-access 下原生命令 exit 0）。` |
| **D15** | `继续开发准备报告` §二/§四 的 **4 个** ❓ 已拍板而未勘误 | **是**；且「4 个」本身与实测不符 | 实测 §二 **5 处** ❓（`:35` 实扣归集口径、`:45` 报工路径是否入库、`:46` 请购断链性质、`:47` 来料检 fail 处置、`:52` 移动端入口）；§四 **3 处** ❓（`:102`/`:103`/`:104`）= **合计 8 处** | 逐处加标记：`:35/:45/:46/:47` → 句尾追加 `（**已决**：见 §六 / 交接提示词 §五 Q-1…Q-4）`；`:52`（移动端入口）与 `:120-122` 的「6 个问题」中**仍未决**的三项保留 ❓ 并在 §二 顶部加一行：`⚠ 时效：本节 ❓ 已按 2026-10-06 业务方裁定部分关闭，未决项见 §六 与交接提示词 §五。` |
| **D16** | `is_archived` 口径表漏 `routes.py:6109` | **是**（`交付说明-P0P1.md:250-252` 清单缺易耗品列表一处，且行号已整体漂移） | 实测 `is_archived` 未统一点：`routes.py:4797`（原材料）/`:4808`（成品）、**`:6125`**（易耗品 `Consumable.query.filter_by(is_archived=False)`）、`:12065`/`:12093`/`:12122`（`api_search_materials` 三处）；已统一点：`routes.py:6247`/`:6254`、`quality.py:744`、`mes_service.py:1562-1563`；有意例外：`mes_service.py:1441/1447/1453` | `交付说明-P0P1.md:251-252`：`manage_inventory 库存列表页（`routes.py:4781` 原材料 / `:4792` 成品…）与 api_search_materials 物料搜索 API（`routes.py:12037` / `:12065` / `:12094`…）` → ``manage_inventory` 库存列表页（`routes.py:4797` 原材料 / `:4808` 成品）、**易耗品列表（`routes.py:6125`，原文漏列 `:6109`）** 与 `api_search_materials` 物料搜索 API（`routes.py:12065` / `:12093` / `:12122`）` |
| **D17** | 「导入落盘由 `cleanup_temp_files()` + `finally` 清理」→ 仅 **7 个直写端点**成立；`import_products` 的 `mkdtemp` 目录无人回收 | **是** | `routes.py` 导入端点 **8 个**：`import_employees:1935`、`import_process_prices:2284`、`import_production_records:2681`、`import_bonus_penalties:3861`、`import_tasks:3987`（以上 5 个 `file.save` 到 `TEMP_FOLDER`，`temp_path` 在 `:1951/2300/2696/3876/4002`）、`import_finished_products:4880`、`import_raw_materials:4967`（2 个落 `tempfile.gettempdir()`，`:4892/4979`，各由自身 `finally` `os.remove`，`:4959-4962/:5050-5053`）、`import_products:7685`（走 `save_temp_file()` `:5083`→`tempfile.mkdtemp()` `:5085`，调用点 `:7698`）；`cleanup_temp_files()` `:2180` **只删文件不删目录**（`:2187-2199`），且只覆盖 `TEMP_FOLDER` | `业务流程现状与缺口.md:446`：`由 `cleanup_temp_files()` + `finally` 清理` → `其中 5 个落 `TEMP_FOLDER`（由 `cleanup_temp_files()` + `finally` 清理）、**2 个落 `tempfile.gettempdir()`（由各自 `finally` `os.remove` 清理，不经 `cleanup_temp_files()`）**、`import_products` 走 `save_temp_file()` 的 `mkdtemp()` 目录**无人回收**（`cleanup_temp_files()` 只删文件不删目录）` |
| **D18** | 「临时文件与清理钩子整体移除」→ `download_product_template` 仍留死清理块 | **是** | `routes.py:7647 def download_product_template`、`:7650 temp_path = None`（此后**从未赋值**）、`:7668-7681` 两处 `if temp_path and os.path.exists(temp_path)` 死分支（恒 False）；同函数 `:7654-7656` 已是 `io.BytesIO` 内存生成 | `交付说明-P0P1.md:258`：`临时文件与清理钩子整体移除，该文件 `after_this_request` 归零。` → `临时文件清理路径整体移除，该文件 `after_this_request` 归零；**但 `download_product_template`（`routes.py:7647`）仍留死清理块**：`:7650` 的 `temp_path = None` 之后再未赋值，`:7668-7681` 两处 `os.path.exists(temp_path)` 恒 False（属死代码，B8-10 待清）。` |
| **D19** | 「15 个修订无条件 `create_table` / `c02604883c72` 建 23 张表」→ **13 文件（12 修订）** / 该修订无条件 **24 处** | **部分成立**：24 处 ✅；**「12 修订」不可复现**；且漏计 `p0p2messtables` | AST：含 `create_table` 调用的修订文件 **14 个**；字面表名正则口径 **13 个文件 = 13 个修订**（01-基线 §3.4 的「13 个」对应此口径）；有 `has_table` 守卫的 **3 个**（`b1a01` 2 处守卫、`da_add_process_assignment_tables` 4 处、`p0p2messtables` 1 处）⇒ **无守卫（「无条件」）= 11 个文件**；`c02604883c72` = **24 处、0 守卫** ✅ | `开发与测试规划-2026-10-06.md:95`：`**13 个文件（12 个修订）**；`c02604883c72` 无条件 **24 处**` → `**字面表名口径 13 个文件 / 13 个修订**（含 `p0p2messtables_add_create_all_tables.py` 的「`_ensure_table()` + `has_table` 守卫」形式则为 **14 个修订文件**）；**无守卫（即『无条件』）者 11 个文件**；`c02604883c72` 无条件 **24 处**` |
| **D20** | 「文档复现命令可直接跑」→ 受限沙箱下 `route_inventory`/`check_db_bootstrap` 原生必失败；`smoke_test`/`permission_matrix` 纯垫片仍失败 → 需 cwd 重定位或 `--no-dump` | **已修正于 `AGENTS.md`（`:92-99`）；docs 侧仍漂移**；沙箱侧**本环境无法复证** | 本环境（danger-full-access）：`check_db_bootstrap.py` 原生 **exit 0**（64 账号 / 6712 行 / 跳过 0 表）、`route_inventory.py` 原生 **exit 0**（271/0）、`smoke_test.py --no-dump` **exit 0**、`permission_matrix.py --no-dump` **exit 0** | `开发进度与交接.md:331`：`后 4 项需经沙箱垫片运行：` → `后 3 项（smoke_test / permission_matrix / functional_test）在 **DSH 受限沙箱**（workspace-write 且禁写既有文件）下需 `scripts/_sandbox_compat.py`；**在 danger-full-access 下可原生直跑（2026-10-08 实测 exit 0）**；`route_inventory`/`check_db_bootstrap` 原生亦可（实测 exit 0）。` |
| **D21** | 「导入端点必须落盘」→ **非普遍规律**：8 个落盘端点在 `routes.py`；`/api/quality/tasks/import` 内存流解析不落盘 | **是** | `quality.py:1615 def import_inspection_tasks`、`:1634 df = pd.read_excel(file)`（**内存流，不落盘**）；对照 `routes.py` 8 个落盘端点（见 D17）；全仓导入端点 **9 个** | `AGENTS.md:49`：`**仅上传解析必须落盘**：…因此导入端点才写 `current_app.config['TEMP_FOLDER']`（`file.save(temp_path)`）…当前 `routes.py` 有 8 个导入端点属于这种形态。` → `**仅上传解析需要真实路径**：`routes.py` 的 8 个导入端点落盘（其中 5 个写 `current_app.config['TEMP_FOLDER']`、2 个写 `tempfile.gettempdir()`、1 个走 `save_temp_file()` 的 `mkdtemp()`）；**`/api/quality/tasks/import`（`app/main/quality.py:1615`，`:1634` `pd.read_excel(file)`）从内存流解析、不落盘** ⇒ 「导入必须落盘」不是普遍规律。`；`AGENTS.md:293` recipe 5 标题 `5) Excel 导入（**必须落盘** + 行级容错）` → `5) Excel 导入（**需真实路径时落盘** + 行级容错；内存流可实现则不落盘）` |
| **D22** | `routes.py` 行数两值并存（12126 换行 / 12127 行） | **是**（且两值都已过时） | HEAD 版：`bytes=511969`、`splitlines()=12155`、`\n` 计数 `12155`、末行**有**换行、无 BOM、无 CRLF；对照 `f60a54d` 版：`bytes=506769`、`splitlines=12127`、`\n=12126`、**末行无换行** | `交付说明-P0P1.md:286`：`长度 **12126** 行` → `长度 **12155** 行（口径：splitlines()=12155、`\n` 计数=12155、末行有换行；对照 f60a54d 时点为 12127/12126 且末行无换行）`；`开发进度与交接.md:341`：`**12126 行**` → `**12155 行**`；`继续开发准备报告.md:271`：`**12126** 行` → `**12155** 行` |
| **D23** | 「5 个 head 已收敛」→ 应写「（历史）曾多 head，现单一 head」 | **是** | `check_migration_heads.py` ⇒ `head_count=1`、`HEADS=['p1nonctarget']`；`开发进度与交接.md:108`、`:260` 原文见右列 | `开发进度与交接.md:108`：`**当前状态（2026-09-18 实测）**：5 个 head 已收敛为**单一 head `p1nonctarget`（35 个修订）**。` → `**当前状态（2026-10-08 实测）**：（历史）曾为多个 head（峰值 5 个），**现为单一 head `p1nonctarget`（35 个修订）**。`；`:260`：`~~收敛 5 个 head~~ —— **已完成**：单一 head…` → `~~（历史）收敛 5 个 head~~ —— **已完成**：单一 head…` |
| **D24** | 「无校验 15 个」**量纲混用**（75 / 5 / 15） | **是** | `测试报告-2026-08-11.md:301` 仍写 `无校验路由 75 → 15`、`:568` `降到 6 条`；**今天实测**：`permission_matrix.py --no-dump` ⇒ 「源码上完全没有权限校验的视图」= **5**（`api_notification_stats`/`api_recent_notifications`/`manage_notifications`/`my_tasks`/`user_dashboard`）、匿名可访问 **0**；内联 role = **15+2**；历史基线 **75**（2026-08-11，不可与今日混用） | `测试报告-2026-08-11.md:301`：`无校验路由 75 → 15` → `无校验路由 **75（2026-08-11 历史基线）→ 5（当前「源码上完全无权限校验」视图数）**；另：内联 `current_user.role` **15（Python）+ 2（模板）** —— 三个数**量纲不同，不得互替**（见 规划 §0.5）`；`:568`：`降到 6 条` → `降到 **5** 条（2026-10-08 复测；另 6 为 2026-08-11 口径，属历史读数）` |

**D1–D24 汇总**：仍漂移 **15**（D1/D5/D7/D11/D12/D15/D16/D17/D18/D22/D23/D24 + D6/D14/D20 的 docs 侧）
+ 已部分修正 **6**（D2/D3/D4/D9/D13/D19）
+ **D8 的订正目标本身不成立**（1）
+ D10（值两代过时）（1）
⇒ 合计 24 条，**无一条可判「无需处理」**。

---

## 2. AGENTS.md 专章

### 2.1 门禁表逐项对账（`AGENTS.md:74-91`）

| AGENTS.md 期望值（原文） | 实测（工具 + 口径 + 值） | 一致？ |
| --- | --- | --- |
| `check_templates.py` = `87 templates / 44 declared / 40 used in templates / 44 used on routes / landing 5` → `RESULT: OK` | `python -B scripts/check_templates.py` ⇒ `[templates] parsed 87 files` / `[permissions] 44 declared / 40 used in templates / 44 used on routes` / `[landing] 5 role landing endpoints` / `RESULT: OK`，**exit 0** | ✅ **逐字一致** |
| `check_migration_heads.py` = `HEADS=['p1nonctarget']`、`head_count=1`、`revisions=35` → exit 0 | 同上 ⇒ `HEADS=['p1nonctarget']` / `head_count=1  revisions=35` / `OK: 单一 head p1nonctarget`，**exit 0** | ✅ 一致 |
| `check_properties.py` = `已扫描 23 个文件，模型类 74 个` → `RESULT: OK` | 同上 ⇒ `已扫描 23 个文件，模型类 74 个` / `RESULT: OK（未发现把 @property / 不存在的列当数据库列用）`，**exit 0** | ✅ 一致 |
| `check_model_refs.py` = `scanned 23 files` / `name_query_refs`（勿钉）/ `violations 0` → `RESULT: OK`（判据只钉 `violations 0` + `RESULT: OK`） | 同上 ⇒ `[model_refs] scanned 23 files, name_query_refs 602, violations 0` / `RESULT: OK`，**exit 0** | ✅ 一致（`602` 与原文列举的「574/575/602」末值相符） |
| `w4_http_contract.py --roots app --scope app --expect 10` → 10 个 P-12 站点 → exit 0 | 同上 ⇒ 逐个打印 **10 条** `[SITE]`（`routes.py:1720 add_bonus_penalty()` … `:11138 update_consumable_category()`），`会吞成静默出口的站点 = 10（期望 10）`，**exit 0** | ✅ 一致 |
| `ci_gates.py --phase first` = 当前 **14 步**：blocking 10 / report-only 4 | `ci_gates.py --list` ⇒ 尾行 `[ci_gates] phase=first interpreter=… steps=14`；逐步 group 计数 = blocking **10**（check_templates / check_migration_heads / check_properties / check_db_bootstrap / run_gates / functional_test / permission_matrix / coverage_drift / check_model_refs / check_http_contract）+ report-only **4**（smoke_test / route_inventory / measure_coverage / evidence_hash）；文件指纹 69125 B / `2EDB60DA…` / mtime `2026-10-07 22:22:17` | ✅ 一致（步骤数须连 SHA256 + 时点引用，AGENTS.md 自己的纪律） |
| 退出码语义 `0=全部 blocking 通过 / 1=有 blocking 失败 / 2=仅 report-only 失败 / **3=入口缺失**` | `ci_gates.py:1138` = `code = 1 if (blocking_fail or not root_ok or ineffective) else (2 if report_fail else 0)`；全文**无 `return 3` / `sys.exit(3)`**（`grep "return 3\|exit(3)"` ⇒ 0 命中）；`grep "入口缺失"` 全仓 ⇒ **0 命中** | ❌ **`3=入口缺失` 与源码不符**（详见 §5 N-3） |
| `route_inventory.py` = `total rules=271`、`duplicate (method,path) registrations=0`（**报告型，退出码不进链**） | 同上 ⇒ `[routes] total rules=271` / `[routes] duplicate (method,path) registrations=0`，**exit 0**；`[e03]` 自述 `报告型（无判据语义 => 恒 exit 0…）` | ✅ 一致 |
| `harness/coverage_drift.py`：缺参 = `exit 2`（用法错误）；`0`=判据 8/8；`9/9 --selftest ⇒ 0` | 原生无参 ⇒ **exit 2**（`[USAGE] exit 2 = 未提供产物（用法错误）`）；`--selftest` ⇒ `自检结果 9/9 通过 => 敏感性 OK`，**exit 0** | ✅ 一致 |
| `check_properties.py` 跳过表 = `SKIP_FILENAMES` 4 名字 + `SKIP_SUFFIXES`（`.bak`/`.new`/`.backup`） | `scripts/check_properties.py:79` = 4 名字 ✅；`:81 SKIP_SUFFIXES = ('.bak', '.new', '.backup', '.pyc')` ⇒ **实际 4 项，原文漏列 `.pyc`** | ⚠ **需订正**（漏 `.pyc`） |
| 「4 个遗留备份文件已于 2026-09-18 第 8 批删除（约 **1.99 MB**）」 | 7 个被删 blob 实测合计 **2543015 B**（2.54 MB 十进制 / 2.43 MiB）；其中 4 个名字型 = 315734+655343+455184+562883 = **1989144 B = 1.99 MB 十进制**（**该 1.99 MB 只对应 4 名字型，口径需写明**） | ⚠ **口径需补**（不是错，但须写明是 4 名字型还是 7 个文件） |

**结论**：门禁表里**唯一的硬错**是 `3=入口缺失`；另有 2 处口径需补注（`.pyc` / 1.99 MB 的范围）。

### 2.2 AGENTS.md 中**仍与源码冲突**的表述（逐条）

| # | 位置 | 原文（节选） | 实测 | 建议 |
| --- | --- | --- | --- | --- |
| A1 | `AGENTS.md:91` | 「**结论：`app/main` 下现只有 `routes.py` 一个路由模块**」 | 含 `@bp.route` 的模块 **7 个**（routes 192 / quality 27 / equipment 15 / purchase 13 / production_center 7 / shipping 6 / stock 5 = 265 条）；另有 1 字节死文件 `sales_routes.py` | **必改**（captain 已确认的第一处；改法见 §4-C1） |
| A2 | `AGENTS.md:25` | 「蓝图路由：`app/main/routes.py`（任务/生产/库存/销售/产品等）与 `app/main/quality.py`（质量）」 | 同上 7 个模块；`equipment.py`/`purchase.py`/`production_center.py`/`shipping.py`/`stock.py` 各承载一个域 | **必改**（§4-C2） |
| A3 | `AGENTS.md:30` | 「质量相关在 `app/main/quality.py`；任务/生产/库存/销售/产品等在 `app/main/routes.py`」 | 同上；`routes.py` 单文件 12155 行 / 192 条路由，域已外移 5 个模块 | **必改**（§4-C3） |
| A4 | `AGENTS.md:87` | 「退出码语义 `… / 3=入口缺失`」 | 源码只有 0/1/2（`:1138`）；全仓无「入口缺失」字样 | **必改或补实装**（§4-C5 / §5 N-3） |
| A5 | `AGENTS.md:49` | 「…因此导入端点才写 `current_app.config['TEMP_FOLDER']`（`file.save(temp_path)`），…当前 `routes.py` 有 8 个导入端点属于这种形态」 | 8 个落盘端点中**只有 5 个**写 `TEMP_FOLDER`（`temp_path` 在 `routes.py:1951/2300/2696/3876/4002`）；另 **2 个**写 `tempfile.gettempdir()`（`:4892/4979`）、**1 个**走 `save_temp_file()` 的 `mkdtemp()`（`:5083/:5085`，调用点 `:7698`） | **必改**（§4-C6） |
| A6 | `AGENTS.md:49`、`:328` | 「`save_temp_file()`（`app/main/routes.py:5067`）」 | 实测 `def save_temp_file` 在 **`routes.py:5083`**（`mkdtemp()` 在 `:5085`） | **必改**（行号漂移，§4-C7） |
| A7 | `AGENTS.md:35`、`:184` | 「仓库现有 **13 处**已是内存生成模式」/「仓库已把 13 处导出全部改成上面的内存形态」 | `routes.py` 的 `BytesIO()` = **13 处** ✅（`:1903/2226/2253/2622/2649/2786/2838/3829/3955/4115/4164/7654/7950`）；但 `quality.py` 另有 **3 处**（`:1465` 质检记录导出 / `:1561` 任务导出 / `:1596` 导入模板）、`app/utils/excel_generator.py:612` 1 处 ⇒ **全仓 `BytesIO()` = 17 处；导出/模板端点内存生成至少 16 处** | **必改**（口径限定到 `routes.py` 或改为 16/17，§4-C8） |
| A8 | `AGENTS.md:95` | 「根因是 `cleanup_temp_files()` 作为 `@bp.before_request` 钩子（`app/main/routes.py:2196-2200`）在**每个请求**删除 `TEMP_FOLDER`…」 | 行为 ✅（`:2194` `current_time - file_time > 300` 删文件）；行号**已漂移**：`def cleanup_temp_files` 在 **`:2180`**、`@bp.before_request` 在 **`:2203-2204`**、`os.remove` 在 **`:2196`** | **必改行号**（§4-C9） |
| A9 | `AGENTS.md:91` | 「② `SKIP_SUFFIXES`（`.bak` / `.new` / `.backup`）」 | `check_properties.py:81` = `('.bak', '.new', '.backup', '.pyc')` | 补 `.pyc`（§4-C10） |
| A10 | `AGENTS.md:91` | 「（约 **1.99 MB**，全仓引用 0 处）」（指 4 个名字型备份） | 4 名字型被删 blob = **1989144 B = 1.99 MB 十进制**；7 个文件合计 **2543015 B = 2.54 MB 十进制** | 补口径（§4-C11） |
| A11 | `AGENTS.md:99` | 「只做静态检查时优先跑不发请求的 **5 个**脚本（`check_templates` / `check_migration_heads` / `check_properties` / `route_inventory` / `check_db_bootstrap`）」 | 同文件门禁表（`:78-83`）已列 **6** 条命令；其中 `check_model_refs`（blocking）与 `w4_http_contract`（blocking）**不在**这 5 个里；另有 2026-10-07 新增的 `scripts/check_doc_claims.py`（实测 `RESULT: OK（violations=0）`，exit 0）**未进 `ci_gates` 14 步链、AGENTS.md 全文未提** | 补列（§4-C12 / §5 N-4） |
| A12 | `AGENTS.md:91` | 「**其实被 git 跟踪**，原记录有误」 | ✅ **原文正确**（f60a54d^ 三文件确被跟踪）；反而是**规划附录 E 的 D8 订正目标有误** | **保留原文**；撤回 D8 的订正动作（§1-D8 / §5 N-1） |

> **未发现冲突的 AGENTS.md 表述（抽样已核）**：`7 个角色`（`app/permissions.py:16` AST Tuple len=7）✅；`44 能力`（`:27` AST Dict len=44）✅；`31 张表不在迁移历史里`（真库 75 表含 `alembic_version`，业务表 ∉ 迁移 `create_table` = **31**）✅；「单 head `p1nonctarget` / 全链重放不可行」✅；「`permission_matrix` 10 个入口逐入口 allow+deny」✅（实跑：equipment 4 + purchase_orders 3 + shipments 1 + stock 2 = 10）；「落盘改到 `test-reports-2026-10/.tmp/<RUN_ID>/` + `--no-dump`」✅（源码级）。

---

## 3. 数字总表（全仓文档 vs 实测）

> 「文档值」= 出现在 `docs/` 4 份背景文档 / `AGENTS.md` / 交接提示词里的值；同值多文件时省略到代表处。
> **凡标注「需订正」**，即该数字在当前仓库文本中与实测不一致，建议值见末列。

| 指标 | 文档值（代表位置） | 实测值（工具 + 口径） | 结论 | 建议值 |
| --- | --- | --- | --- | --- |
| 模板数 | 87（`AGENTS.md:78`；`开发进度与交接:322`） | **87**（`check_templates.py` `parsed 87 files`；`(Get-ChildItem app/templates -Recurse -File -Filter *.html).Count`） | ✅ 一致 | 87（口径：`app/templates` 下 `.html`；该目录非 html 文件 0 ⇒ 全部文件数亦 87） |
| 声明能力数 | 44（多处） | **44**（AST `app/permissions.py:27` Dict len=44；`check_templates` `44 declared`） | ✅ 一致 | 44（口径：AST 模块级 Dict 字面量；另存在「43 used」/「43 正则」口径，**勿混**） |
| 角色数 | 7（`AGENTS.md:27`） | **7**（AST `app/permissions.py:16` Tuple len=7：admin/manager/hr/accountant/inspector/sales/user） | ✅ 一致 | 7 |
| 模型类数 | 74（`AGENTS.md:80`） | **74**（`check_properties` `模型类 74 个`；`app/models.py` ClassDef=74；`db.metadata.tables`=74） | ✅ 一致 | 74 |
| 路由数 | 271（`AGENTS.md:81`）；旧值 194/261（`继续开发准备报告:14/24/272`） | **271**（`route_inventory` `total rules=271`，url_map 口径）；AST `@bp.route` = **269**；蓝图层 `main`=**265** / `auth`=4 / `static`=1 / `bootstrap`=1 | ⚠ **旧值需订正**；271 本身 ✅ | 271（url_map）/ 269（装饰器）/ 265（main）；「261」「194」需订正 |
| 无能力装饰器的 main 视图 | 旧文表述「150 装饰器 + 102 inline role + 9 仅 login_required」 | **8**（AST：main 265 = `require_capability` 257 + 仅 `login_required` 8 + 无守卫 0） | ⚠ **需订正** | 8 |
| capability 数（使用侧） | 43（多份报告） | **44 declared / 43 used?**（`check_templates` 输出 = `44 declared / 40 used in templates / 44 used on routes`） | ⚠ 口径需注明 | 「44 declared（AST）」；引用 43 必须写「正则/使用侧口径」 |
| `_ENSURED_COLUMNS` 表数/列数 | 8 表 23 列（`继续开发准备报告:21`）/ 48 列（T4 旧值） | **10 表 / 43 列**（AST `app/__init__.py:21`；逐表 6/9/6/6/1/2/3/8/1/1） | ⚠ **需订正** | 10 表 43 列 |
| 迁移 head 数 | 2（`继续开发准备报告:21/57`）/ 5（`开发进度与交接:108/260`） | **1**（`check_migration_heads` `head_count=1`） | ⚠ **需订正**（措辞 + 值） | 单一 head `p1nonctarget`；措辞改「（历史）曾多 head」 |
| 迁移修订数 | 35（多处） | **35**（`revisions=35`；`migrations/versions/*.py` = 35 个文件，每文件 1 个 `revision`） | ✅ 一致 | 35 |
| 迁移文件数 | 32（`继续开发准备报告:21`） | **35** | ⚠ **需订正** | 35 |
| 迁移建表数 / 差集 | 「迁移建 49 / 不在任何迁移 31」（规划 §0.2/附录 A） | **迁移字面表名 = 49**（正则 `create_table('name')` 去重）；**真库业务表 ∉ 迁移 = 31**（`app.db` 只读：`sqlite_master` 75 表，剔 `alembic_version` 后 74，与迁移名集合差 **31**）；`db.metadata.tables` = 74，差集同为 31 | ✅ 一致 | 75 表（含 `alembic_version`）/ 74 业务表 / 迁移建 49 / 差集 31 |
| 无条件 `create_table` | 15 个修订 / `c02604883c72` 建 23 张表（`交付说明:183`、`开发进度与交接:120/417`） | **14 个修订文件含 `create_table` 调用**；字面口径 **13 文件 / 13 修订**；**无守卫（无条件）= 11 文件**；`c02604883c72` = **24 处**（0 守卫） | ⚠ **需订正** | 「13 文件（字面口径，= 13 修订）/ 14 文件（含 p0p2messtables）；无条件者 11 文件；c02604883c72 24 处」 |
| 内联 `current_user.role`（Python） | 102（`继续开发准备报告:14/38/97`）/ 「约 70」/ 「16」 | **15**（AST `Attribute(attr='role', value=Name('current_user'))`：`routes.py` 5 = `:337/340/350/654/5983`，`quality.py` 10 = `:46/82/104/120/529/822/911/1217/1277/1347`） | ⚠ **需订正** | 15（Python）+ 2（模板） |
| 内联 role（模板） | 31 模板 77 处（`继续开发准备报告:20/50/105`） | **2 处**（`quality/tasks.html:340`、`quality/task_detail.html:13`） | ⚠ **需订正** | 2 处（契约豁免） |
| 导出/模板 `io.BytesIO` | 13（`AGENTS.md:35/184`、`交付说明:260/286`、`业务流程:444`、`开发进度与交接:341`） | **`routes.py` = 13** ✅；**全仓 = 17**（+`quality.py` 3 = `:1465/1561/1596`，+`excel_generator.py:612` 1） | ⚠ **口径需订正** | 「`routes.py` 13 处；全仓导出/模板端点 ≥16；`BytesIO()` 全仓 17」 |
| 落盘导入端点数 | 8（`AGENTS.md:49`、`业务流程:446`）/ 9（`01-基线事实清单:41`、`02-测试分层:48` 记「9 个（8 落盘）」） | **全仓 9 个导入端点**：`routes.py` **8 个落盘**（5 个 `TEMP_FOLDER` + 2 个 OS temp + 1 个 `mkdtemp`）+ `quality.py` **1 个不落盘** | ⚠ **需写明口径** | 「9 个导入端点；8 个落盘（全在 `routes.py`）；1 个内存流（`/api/quality/tasks/import`）」 |
| 无校验视图（运行时） | 5（多处）/ 75（历史）/ 15（量纲混用） | **5**（`permission_matrix.py --no-dump`：`api_notification_stats`/`api_recent_notifications`/`manage_notifications`/`my_tasks`/`user_dashboard`）；**匿名可访问 = 0** | ✅ 5 一致；⚠ 旧文的「15」需订正 | 5（运行时口径）；8（AST 口径「仅登录未登记能力」）；75（2026-08-11 历史基线）——**三者不得互替** |
| `routes.py` 行数 | 11557 / 12214（`继续开发准备报告:24/67`）、12126 / 12127（`开发进度与交接:341`、`交付说明:286`、规划 §0.2） | **12155**（`splitlines()=12155`、`\n`=12155、末行有换行、无 BOM/CRLF、511969 B） | ⚠ **需订正**（全部旧值过时） | 12155 |
| `models.py` 行数 | 约 2770–3092（`继续开发准备报告:24`） | **2983** | ✅ 落在区间内（无需改） | 2983 |
| 已跟踪 `.pyc` | 57（`继续开发准备报告:68/275`、`交付说明:271`） | **0**（`git ls-files '*.pyc'`） | ⚠ **需订正**（新旧口径应并存） | 0（原 57） |
| `.gitignore` 行数/规则数 | 「仅 3 行」（`继续开发准备报告:68`）、「补齐为 14 条规则」（`交付说明:274`） | **42 行**；关键规则 `:12-13 __pycache__/ *.pyc`、`:21-22 /app.db, /app.db.bak-*`、`:25-26` 两个根 JSON、`:32 /uploads/temp/`、`:36-38 *.bak/*.new/*.backup` | ⚠ **需订正** | 42 行（可用 `git check-ignore -v` 逐条复核） |
| smoke 目标数 | 148（多处） | **148**（`smoke_test.py --no-dump`：`[plan] 可测 GET 路由 148 条，跳过 9 条`、`8 身份 × 148`、0 问题）；`check_doc_claims` 钉 `smoke_targets=148`、`smoke_unresolved=9` | ✅ 一致 | 148（+9 跳过） |
| functional_test 通过数 | 109 通过 / 0 失败 | **未重跑**（`check_doc_claims.py` 钉常量 `functional_passed=109` 与源值相等 ⇒ 值自洽） | ✅（口径来源为 `run_gates.EXPECTED`） | 109 / 0 |
| HEAD | `148d8a5` → `f60a54d` | **`534ce70b204c767feee551e8fd04e538374b1de8`** | ⚠ **需订正** | 534ce70… |
| 真实库不变量 | `F5DA2306…0E0F065`（多处） | **2531328 B / `F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065` / mtime 2026-09-18 12:50:55**；`alembic_version=f179636cecf0` | ✅ 一致 | 不变 |
| 死端点/死模块 | 「删 2 个死端点 + `app/decorators.py`」 | `route_inventory` 已无 `/upload/raw-materials`、`/upload/finished-products`；`app/decorators.py` 不存在（`Test-Path` False） | ✅ 一致 | 不变 |
| `check_doc_claims` 口径键（**新权威源**） | 未被任何背景文档登记 | `scripts/check_doc_claims.py --list-constants` ⇒ **20 条全部 OK**（含 `rules_total=271`、`templates_files=87`、`model_classes=74`、`properties_files=23`、`migration_revisions=35`、`capabilities_declared=44`、`routes_get_no_arg=104`/`with_arg=56`/`non_get=110`、`smoke_targets=148`、`functional_passed=109`、`method_level_non_get_total=155`…） | ⚠ **未登记**（见 §5 N-4） | 建议把该表作为「文档数字的机器可读权威源」，AGENTS.md 门禁表登记该脚本 |

---

## 4. 文档订正执行清单（**只给清单，不执行**）

> 用法：作为 §10.4/§10.6 式「订正件」的输入。每行 = `文件 → 行/章节 → 原句 → 新句`。
> **优先级**：P0 = 会实质误导排期/实现（D1/D2/D3/D4/D7/D8/D15/D20/D21/D24 + AGENTS.md 门禁表硬错）；P1 = 数字订正；P2 = 措辞/行号。

### 4.A `docs/继续开发准备报告.md`

| 优先级 | 行 | 原句 | 新句 |
| --- | --- | --- | --- |
| P0 | `:14` | `44 能力/7 角色；261 个 main 视图 = 150 装饰器 + 102 inline role + 9 仅 login_required；0 无登录守卫` | `44 能力/7 角色；265 个 main 视图 = 257 个 @require_capability + 8 个仅 @login_required；Python 内联 current_user.role 15 处（routes.py 5 + quality.py 10）+ 模板 2 处；0 无登录守卫` |
| P0 | `:20` | `31 模板 77 处硬编码 role、3 组 role 与能力表不一致、6 孤儿模板、8 处 JS 硬编码 URL；url_for 断链 0 处` | `模板 2 处 + Python 15 处内联 role、3 组 role 与能力表不一致、6 孤儿模板、8 处 JS 硬编码 URL；url_for 断链 0 处` |
| P0 | `:21` | `32 迁移文件、**2 个 head**（c2mespg001 / f179636cecf0），app.db 停 f179636cecf0；31 表靠 create_all 不在迁移史；_ENSURED_COLUMNS 覆盖 8 表 23 列` | `35 迁移文件、**单一 head p1nonctarget（35 修订）**（历史曾 2 head），app.db 的 alembic_version 仍停 f179636cecf0；31 张业务表靠 create_all 不在迁移史；_ENSURED_COLUMNS 覆盖 **10 表 43 列**` |
| P0 | `:24` | `routes.py 约 1.1–1.2 万行 / 194 路由（两个成员分别实测 12214 与 11557 行，差异为统计口径）` | `routes.py **12155 行**（splitlines=12155 / LF=12155 / 末行有换行 / 无 BOM，511969 B）/ 路由 **271**（duplicate=0）` |
| P1 | `:38` | `102 个 inline current_user.role 端点迁移到 @require_capability（routes.py 88 + quality.py 14）` | `15 处 inline current_user.role（routes.py 5 + quality.py 10；模板另 2 处属契约豁免）迁移到 @require_capability` |
| P0 | `:50` | `31 模板 77 处硬编码 current_user.role 迁移 can()（…quality/tasks.html:337…）` | `模板 2 处硬编码 current_user.role（quality/task_detail.html:13、**quality/tasks.html:340**）迁移 can()；Python 内联残留 15 处（…）` |
| P1 | `:57` | `收敛 2 个 head（c2mespg001 / f179636cecf0）为单 head` | `（已完成）**单一 head p1nonctarget（35 修订）**（历史曾 2 head）` |
| P2 | `:67` | `文档漂移：37→44 capability、5→2 head、停在 0e97d0ec34b4→f179636cecf0、routes.py 11557 行` | `文档漂移：37→44 capability、曾多 head→现单 head、alembic_version 停在 f179636cecf0、routes.py **12155 行**` |
| P1 | `:68` | `约 57 个 .pyc 已跟踪 + .gitignore 仅 3 行；…` | `已跟踪 *.pyc = **0**（原 57 个已 git rm --cached）；.gitignore 已扩为 **42 行**（/uploads/temp/ 在 :32，*.bak/*.new/*.backup 在 :36-38）；…` |
| P1 | `:97` | `权限收口（102 inline 端点 + 3 组模板按钮错位 + 不合格处置导航）` | `权限收口（15 处 Python 内联 role 端点 + 3 组模板按钮错位 + 不合格处置导航）` |
| P1 | `:105` | `前端一致性批量收口（77 处 role、8 处 JS、成品 Select2 字段、mobile 对齐、分页白名单、清 6 孤儿模板）` | `前端一致性批量收口（模板 2 处 role、8 处 JS、成品 Select2 字段、mobile 对齐、分页白名单、清 6 孤儿模板）` |
| P1 | `:271` | `| app/main/routes.py 行数 | 约 1.1–1.2 万行 | **12126** 行 |` | `| app/main/routes.py 行数 | 约 1.1–1.2 万行 | **12155** 行（splitlines=12155 / LF=12155 / 末行有换行） |` |
| P0 | `:281` | `2. 审计回滚 globals()[target_model] 反射 + 不处理级联。` | `2. 审计回滚**已改为 getattr(app.models, name)**（routes.py:4182-4189）；**级联仍未处理**（delete 分支）。` |
| P0 | `§二` 顶部 | （无时效警示） | 新增一行：`> ⚠ 时效：本节 ❓ 已按 2026-10-06 业务方裁定部分关闭（见 §六 与交接提示词 §五 Q-1…Q-4）；仍未决项保留 ❓。` |
| P0 | `:35/:45/:46/:47` | `❓实扣归集口径待定。` / `❓报工路径是否也应末道入库。` / `❓未启用还是缺陷。` / `❓处置方式。` | 逐句尾追加 `（**已决**：见 §六）` |
| P0 | `:52` | `❓移动端是否补产销一体入口。` | 保留 ❓，并注明 `（**未决**，见 §五 第 5 问）` |

### 4.B `docs/开发进度与交接.md`

| 优先级 | 行 | 原句 | 新句 |
| --- | --- | --- | --- |
| P0 | `:108` | `**当前状态（2026-09-18 实测）**：5 个 head 已收敛为**单一 head p1nonctarget（35 个修订）**。` | `**当前状态（2026-10-08 实测）**：（历史）曾为多个 head（峰值 5 个），**现为单一 head p1nonctarget（35 个修订）**。` |
| P1 | `:120` | `1. 15 个修订里有无条件 create_table（c02604883c72 一个就建 23 张表）…` | `1. **含 create_table 的修订文件 14 个**（字面表名口径 13 个文件 = 13 个修订；**无 has_table 守卫者 11 个文件**），c02604883c72 单个文件无条件 **24 处**…` |
| P1 | `:260` | `~~补齐历史缺失的 Alembic 迁移、收敛 5 个 head~~ —— **已完成**：单一 head p1nonctarget（35 修订）。` | `~~（历史）收敛 5 个 head~~ —— **已完成**：单一 head p1nonctarget（35 修订）。` |
| P1 | `:337` | `这几个脚本仍会重写根目录 _permission_matrix.json / _smoke_results.json（已 gitignore）。` | `E-03 后（2026-10-07）：smoke_test.py / permission_matrix.py 落盘已默认改到 test-reports-2026-10/.tmp/<RUN_ID>/（绝对路径），并支持 --no-dump；写盘失败只打 [WARN]，**不改变退出码**。CI/复跑一律带 --no-dump。` |
| P1 | `:341` | `app/main/routes.py：**12126 行**；after_this_request **0** 处、tempfile.mkstemp **0** 处、buf = io.BytesIO() **13** 处。` | `app/main/routes.py：**12155 行**；after_this_request **0** 处、tempfile.mkstemp **0** 处、buf = io.BytesIO() **13 处（routes.py 口径；全仓 17 处，另 quality.py 3 + excel_generator.py 1）**。` |
| P0 | `:345` | `- **新增 4 个端点**（此前前端是「待实现」禁用占位，现已恢复可用）：` | `- **新增 5 个端点**（此前前端是「待实现」禁用占位，现已恢复可用）：`；并在条列中补 `- GET /api/quality/records/export — app/main/quality.py:1368，能力 quality.export；` |
| P1 | `:331` | `后 4 项需经沙箱垫片运行：` | `后 3 项（smoke_test / permission_matrix / functional_test）在 DSH 受限沙箱下需 scripts/_sandbox_compat.py；在 danger-full-access 下可原生直跑（2026-10-08 实测 exit 0）。` |
| P1 | `:417` | `3. **15 个修订有无条件 create_table**（c02604883c72 一个就建 23 张表）…` | `3. **14 个修订文件含 create_table**（无条件者 11 个文件；c02604883c72 单文件 24 处）…` |

### 4.C `AGENTS.md`

| 优先级 | 行 | 原句 | 新句 |
| --- | --- | --- | --- |
| **P0 / C1** | `:91` 末句 | `**结论：app/main 下现只有 routes.py 一个路由模块；不要再按「包内有语法错误的备份文件」的说法去处理。**` | `**结论：app/main 下含 @bp.route 的路由模块共 7 个**（routes.py 192 / quality.py 27 / equipment.py 15 / purchase.py 13 / production_center.py 7 / shipping.py 6 / stock.py 5 = 265 条），另有 1 字节死文件 app/main/sales_routes.py（被 git 跟踪、0 路由、0 引用，待 `git rm`）；不要再按「包内有语法错误的备份文件」的说法去处理。` |
| **P0 / C2** | `:25` | `  - 蓝图路由：app/main/routes.py（任务/生产/库存/销售/产品等）与 app/main/quality.py（质量）。模板/静态：app/templates, app/static。ORM：app/models.py。` | `  - 蓝图路由（app/main 下 7 个模块）：routes.py（任务/生产/库存/销售/产品等）、quality.py（质量）、equipment.py（设备/工件/炉次）、purchase.py（采购/供应商）、production_center.py（生产中心）、shipping.py（发货）、stock.py（库存页）。模板/静态：app/templates, app/static。ORM：app/models.py。` |
| **P0 / C3** | `:30` | `  - 质量相关在 app/main/quality.py；任务/生产/库存/销售/产品等在 app/main/routes.py，同类功能就近归类并分段注释。` | `  - 质量相关在 app/main/quality.py；设备/采购/生产中心/发货/库存页分别在 equipment.py / purchase.py / production_center.py / shipping.py / stock.py；任务/生产/库存/销售/产品其余功能在 app/main/routes.py，同类功能就近归类并分段注释。` |
| **P0 / C4** | `:91` | `（**其实被 git 跟踪**，原记录有误；已于第 8 批一并删除）` | **保留不改**（实测成立）；若要更明确：`（**实测：删除前确被 git 跟踪**——`git ls-tree f60a54d^` 命中三文件，`git show --name-status f60a54d` 显示以 D 删除；`*.bak/*.new/*.backup` 为同一提交新增；已于第 8 批一并删除）` |
| **P0 / C5** | `:87` | `退出码语义 0=全部 blocking 通过 / 1=有 blocking 失败 / 2=仅 report-only 失败 / 3=入口缺失` | `退出码语义 0=全部 blocking 通过 / 1=有 blocking 失败（或仓库根 JSON 被写 / 注入未生效）/ 2=仅 report-only 失败`（**源码仅有 0/1/2**，见 ci_gates.py:1138；如需 3 须先实装） |
| **P0 / C6** | `:49` | `**仅上传解析必须落盘**：ExcelGenerator.parse_* / pd.read_excel 需要真实路径，因此导入端点才写 current_app.config['TEMP_FOLDER']（file.save(temp_path)），由 cleanup_temp_files() + finally 清理；…当前 routes.py 有 8 个导入端点属于这种形态。` | `**仅上传解析需要真实路径**：routes.py 的 8 个导入端点落盘——5 个写 current_app.config['TEMP_FOLDER']（temp_path 在 :1951/2300/2696/3876/4002，由 cleanup_temp_files() + finally 清理）、2 个写 tempfile.gettempdir()（:4892/4979，由各自 finally os.remove 清理）、1 个走 save_temp_file() 的 mkdtemp()（调用点 :7698，目录无人回收）；**/api/quality/tasks/import（app/main/quality.py:1615，:1634 pd.read_excel(file)）从内存流解析、不落盘**。` |
| **P1 / C7** | `:49`、`:328` | `save_temp_file()（app/main/routes.py:5067）` | `save_temp_file()（app/main/routes.py:**5083**）`（`mkdtemp()` 在 `:5085`） |
| **P1 / C8** | `:35`、`:184` | `仓库现有 13 处已是内存生成模式` / `仓库已把 13 处导出全部改成上面的内存形态` | `仓库现有 16 处导出/模板端点已是内存生成模式（routes.py 13 + quality.py 3），全仓 BytesIO() 17 处（另 excel_generator.py:612 1 处）` |
| **P1 / C9** | `:95` | `cleanup_temp_files() 作为 @bp.before_request 钩子（app/main/routes.py:2196-2200）` | `cleanup_temp_files()（def 在 app/main/routes.py:**2180**；@bp.before_request 在 **:2203-2204**；删 mtime>300s 文件在 :2194-2196）` |
| **P2 / C10** | `:91` | `② SKIP_SUFFIXES（.bak / .new / .backup）` | `② SKIP_SUFFIXES（.bak / .new / .backup / **.pyc**）`（`check_properties.py:81`） |
| **P2 / C11** | `:91` | `（约 1.99 MB，全仓引用 0 处）` | `（4 名字型合计 1989144 B = 1.99 MB 十进制；连同 3 个后缀型则 7 文件合计 2543015 B = 2.54 MB 十进制；全仓引用 0 处）` |
| **P2 / C12** | `:99` | `只做静态检查时优先跑不发请求的 5 个脚本（check_templates / check_migration_heads / check_properties / route_inventory / check_db_bootstrap）。` | `只做静态检查时优先跑不发请求的脚本（check_templates / check_migration_heads / check_properties / check_model_refs / route_inventory / check_db_bootstrap / w4_http_contract / check_doc_claims）。` |
| **P0 / C13** | `:293` recipe 5 标题 | `5) Excel 导入（**必须落盘** + 行级容错）` | `5) Excel 导入（**需真实路径时落盘** + 行级容错；可用内存流则不落盘）` |
| **P2 / C14** | `:320` | `cleanup_temp_files()          # app/main/routes.py:2173` | `cleanup_temp_files()          # app/main/routes.py:2180` |

### 4.D `docs/交付说明-P0P1.md`

| 优先级 | 行 | 原句 | 新句 |
| --- | --- | --- | --- |
| P1 | `:183` | `- **① 重复创建**：15 个修订里有无条件 create_table（c02604883c72 一个就建 23 张表），` | `- **① 重复创建**：含 create_table 的修订文件 14 个（无 has_table 守卫者 11 个），`c02604883c72` 单文件无条件 **24 处**，` |
| P1 | `:250-252` | `…下列位置**仍是 is_archived == False**…manage_inventory 库存列表页（routes.py:4781 原材料 / :4792 成品…）与 api_search_materials 物料搜索 API（routes.py:12037 / :12065 / :12094…）` | `…下列位置**仍是 is_archived == False**…manage_inventory 库存列表页（routes.py:**4797** 原材料 / **:4808** 成品）、**易耗品列表（routes.py:6125，原文漏列 :6109）** 与 api_search_materials 物料搜索 API（routes.py:**12065** / **:12093** / **:12122**…）` |
| P0 | `:258` | `临时文件与清理钩子整体移除，该文件 after_this_request 归零。` | `临时文件清理路径整体移除，该文件 after_this_request 归零；**但 download_product_template（routes.py:7647）仍留死清理块**（:7650 的 temp_path = None 后再未赋值，:7668-7681 两处判断恒 False）。` |
| P1 | `:260`、`:286` | `buf = io.BytesIO() = **13** 处` / `长度 **12126** 行` | `buf = io.BytesIO() = **13 处（routes.py 口径；全仓 17 处）**` / `长度 **12155** 行` |
| P1 | `:115`、`:289` | `cleanup_temp_files() 作为 @bp.before_request 钩子（app/main/routes.py:2196-2200）` | `cleanup_temp_files()（def 在 :2180；@bp.before_request 在 :2203-2204）` |
| P2 | `:103` | ``| python -B scripts/_sandbox_compat.py scripts/permission_matrix.py | exit 0：匿名可访问 0；无校验视图 5 个（无新增） |`` | 追加列注：`（2026-10-08 复测：加 --no-dump 后 danger-full-access 下原生直跑亦 exit 0；写盘已解耦）` |

### 4.E `docs/业务流程现状与缺口.md`

| 优先级 | 行 | 原句 | 新句 |
| --- | --- | --- | --- |
| P0 | `:446` | `- **导入仍必须落盘**（ExcelGenerator.parse_* / pd.read_excel 需要真实路径）：routes.py 现有 8 个导入端点属于这种形态，由 cleanup_temp_files() + finally 清理。` | `- **导入需要真实路径时落盘**（ExcelGenerator.parse_* / pd.read_excel）：routes.py 现有 8 个导入端点落盘（5 个落 TEMP_FOLDER、2 个落 tempfile.gettempdir()、1 个走 save_temp_file() 的 mkdtemp()），由 cleanup_temp_files() / 各自 finally 清理；**/api/quality/tasks/import（quality.py:1615 → :1634）从内存流解析、不落盘**。` |
| P1 | `:444` | `（io.BytesIO，routes.py 现有 13 处）` | `（io.BytesIO，routes.py 现有 13 处；全仓 17 处）` |
| P1 | `:447` | `它是 @bp.before_request 钩子（routes.py:2196-2200）` | `它是 @bp.before_request 钩子（def 在 routes.py:2180，钩子在 :2203-2204）` |

### 4.F `docs/交接提示词-批次3开工-2026-10-06.md`

| 优先级 | 行 | 原句 | 新句 |
| --- | --- | --- | --- |
| P0 | `:8` | `仓库 HEAD = f60a54d，工作区干净（只有 1 个未跟踪的规划文档，属正常）。` | `仓库 HEAD = 534ce70b204c767feee551e8fd04e538374b1de8（2026-10-08 实测；本文写于 f60a54d 时点）。` |
| P1 | `:31` | `导出/模板 13 处 io.BytesIO；落盘导入 8 个（全在 routes.py）。` | `导出/模板 16 处内存生成（routes.py 13 + quality.py 3；全仓 BytesIO() 17 处）；落盘导入 8 个（全在 routes.py），另 /api/quality/tasks/import 不落盘（全仓导入端点 9 个）。` |
| P1 | `:38` | `实为 8 个含 @bp.route 的模块（265 条规则）` | `实为 **app/main 下 7 个**含 @bp.route 的模块（共 265 条；全仓 8 个模块 / 269 条装饰器 / url_map 271 条）`（该句「8 个」指全仓、结论正确，但需写明口径以免与 `AGENTS.md:91` 的「7 个」冲突） |
| P0 | `:39` | `而 /api/quality/tasks/import（app/main/quality.py:1559 → :1581 pd.read_excel(file)）从内存流解析、不落盘` | `行号改为 app/main/quality.py:**1615** → **:1634**` |
| P2 | `:41` | `_ENSURED_COLUMNS **是 10 表 43 列**` | 保留 ✅（实测一致） |
| P2 | `:57` | `需 scripts/_sandbox_compat.py；smoke_test / permission_matrix 仅加垫片仍失败（要覆盖写根目录已存在的 JSON），需 cwd 重定位（批次3 就是来修这个的）` | `**已修（E-03，2026-10-07）**：二者落盘改到 test-reports-2026-10/.tmp/<RUN_ID>/ 并支持 --no-dump；本环境 danger-full-access 下原生直跑 exit 0。` |

---

## 5. 本轮**新发现**（不在 D1–D24 内，均为实测可复核）

| # | 发现 | 证据 | 建议归属 |
| --- | --- | --- | --- |
| **N-1** | **D8 的订正目标本身是错的**：附录 E 说「『其实被 git 跟踪，原记录有误』→ 该订正本身错误（`.gitignore:36-38` 本就忽略）」，但实测三文件在 `f60a54d^` 确被跟踪，且三条忽略规则是同一次提交才加入 | `git ls-tree -l f60a54d^` ⇒ 3 blob 命中；`git show --name-status f60a54d` ⇒ 3 行 `D`；`git show f60a54d^:.gitignore` ⇒ 无 `*.bak/*.new/*.backup`；`git show f60a54d:.gitignore` ⇒ 新增 3 条（现 `:36-38`） | 撤回 D8；`AGENTS.md:91` 保留 |
| **N-2** | `开发进度与交接.md:337` 的「仍会重写根目录 `_permission_matrix.json`/`_smoke_results.json`」**已被 E-03 作废**（`AGENTS.md:93` 已记录作废，docs 未同步） | `smoke_test.py:9-17,246,266`、`permission_matrix.py:14-21,365,404`；实跑 `--no-dump` 两脚本 exit 0 且输出 `[--no-dump] 已跳过落盘` | 并入 D14 订正 |
| **N-3** | `AGENTS.md:87` 的 **`3=入口缺失`** 在 `ci_gates.py` 中**不存在** | `ci_gates.py:1138`；`grep -n "return 3\|exit(3)\|入口缺失" test-reports-2026-10/harness/ci_gates.py` ⇒ 0 命中；全仓 `grep "入口缺失"` ⇒ 0 命中 | 订正文档或实装出口（二者选一，须留证） |
| **N-4** | 2026-10-07 交付的 **`scripts/check_doc_claims.py`（TL-06/07「口径守卫」）未进 `ci_gates` 14 步链，且 `AGENTS.md` 全文未登记**；它自带 **20 条**钉常量（含 `rules_total=271`、`templates_files=87`、`model_classes=74`、`migration_revisions=35`、`capabilities_declared=44`、`smoke_targets=148`、`functional_passed=109`）与「作废口径值扫描」 | `scripts/check_doc_claims.py --list-constants` ⇒ 20/20 `OK`；`python -B scripts/check_doc_claims.py` ⇒ `RESULT: OK（violations=0）` exit 0；`ci_gates.py --list` 的 14 步中**无**该步 | 建议把 §3 的「数字总表」交给它机器校验（避免第 7 次计数漂移） |
| **N-5** | `AGENTS.md:99` 的「5 个静态脚本」清单与 `:78-83` 的门禁表**自相矛盾**（漏 `check_model_refs`、`w4_http_contract`） | 两处行文见 §2.2 A11 | 并入 §4-C12 |
| **N-6** | 真实库不变量里的 **`alembic_version` 仍为 `f179636cecf0`**（未 stamp 到 `p1nonctarget`），`继续开发准备报告:265` 的说法仍成立 —— 提醒：**迁移链「已收敛」与「库已 stamp」是两件事** | 只读 `SELECT * FROM alembic_version` ⇒ `f179636cecf0` | 供阶段 C 迁移条目引用时写明 |
| **N-7** | 沙箱口径复核：**`check_db_bootstrap.py`、`route_inventory.py` 在本环境原生 exit 0**（无需垫片），与 D14/D20 的旧描述相反 | 实跑读数见 §2.1/§7 | 并入 D14/D20 订正 |

---

## 6. 与「其他队友交付物」的接口（避免出现第二套数字）

| 来源（本战役 W0 交付） | 本文件是否与其一致 | 说明 |
| --- | --- | --- |
| `test-reports-2026-10/reconcile-2026-10-08/00-共享事实底盘.md`（t1） | **一致**：`87/44/40/44/landing 5`、`HEADS/1/35`、`23/74`、`violations 0`、`route_inventory 271/0`、`check_db_bootstrap exit 0`、`ci_gates 14 步`、`@bp.route` 269（main 265）、`_ENSURED_COLUMNS 10/43`、`ROLES 7 / CAPABILITIES 44` | 本文件在其基础上**补**：D1–D24 逐条、门禁表逐项、`3=入口缺失` 硬错、D8 反证、`lines=12155`（t1 未给）、迁移守卫分类（14/13/11）、`BytesIO 17`、`TEMP_FOLDER 5/8` |
| 该底盘 §4.1 的 `269` / §4.4 的 `10/43` / §4.3 的 `44` | **本文件独立复跑一致**（§7 命令） | 引用时**必须带口径**（269=装饰器 / 271=url_map / 265=main） |
| `00-共享事实底盘.md` §6「三个量纲」`75/5/15` | **一致**（本文件另用 `permission_matrix` 运行时复证得 `5`） | 引用须连语义 |

---

## 7. 复跑附录（命令 + 本次读数；全部只读，除探针输出文件）

### 7.1 门禁（仓库根、`$py='F:\Miniconda\envs\wage\python.exe'`、`$env:PYTHONIOENCODING='utf-8'`）

```powershell
& $py -B scripts/check_templates.py          # 87 / 44 / 40 / 44 / landing 5 → RESULT: OK  (exit 0)
& $py -B scripts/check_migration_heads.py    # HEADS=['p1nonctarget'] head_count=1 revisions=35 (exit 0)
& $py -B scripts/check_properties.py         # 已扫描 23 个文件，模型类 74 个 → RESULT: OK (exit 0)
& $py -B scripts/check_model_refs.py         # scanned 23 files, name_query_refs 602, violations 0 → OK (exit 0)
& $py -B scripts/route_inventory.py          # total rules=271 / duplicate=0 (报告型，exit 0)
& $py -B scripts/check_db_bootstrap.py       # 64 账号 / 6712 行 / 跳过 0 张表 → OK (exit 0)
& $py -B test-reports-2026-10/harness/w4_http_contract.py --roots app --scope app --expect 10   # 10 站点 (exit 0)
& $py -B test-reports-2026-10/harness/ci_gates.py --list    # steps=14 (blocking 10 + report-only 4) (exit 0)
& $py -B scripts/smoke_test.py --no-dump     # 148 targets × 8 actors / errors 0 (exit 0)
& $py -B scripts/permission_matrix.py --no-dump   # 匿名 0 / 无校验 5 / C-06 四模块全绿 (exit 0)
& $py -B test-reports-2026-10/harness/coverage_drift.py            # 缺参 ⇒ exit 2（用法错误）
& $py -B test-reports-2026-10/harness/coverage_drift.py --selftest # 9/9 ⇒ exit 0
& $py -B scripts/check_doc_claims.py --list-constants   # 20 条口径键 20/20 OK
& $py -B scripts/check_doc_claims.py                    # RESULT: OK（violations=0） exit 0
```

### 7.2 规模事实（AST / 字节口径）

```powershell
# ② @bp.route 装饰器（AST）：269 = main 265 + auth 4
& $py -B test-reports-2026-10/reconcile-2026-10-08/probe_docs_numbers.py   # 见 §1/§3 全部读数
# ③ 内联 current_user.role（AST）：Python 15 / 模板 2
# ④ io.BytesIO()（文本）：routes 13 / quality 3 / excel_generator 1 = 17
# ⑤ _ENSURED_COLUMNS（AST）：10 表 43 列
# ⑥ metadata 表 = 74；真库表 = 75（含 alembic_version）；迁移唯一表名 = 49；差集 = 31
# ⑦ routes.py：bytes=511969 splitlines=12155 LF=12155 末行有换行 无 BOM 无 CRLF
# ⑧ migrations/versions：35 文件；含 create_table 调用 14 文件；字面口径 13；无守卫 11
& $py -B test-reports-2026-10/reconcile-2026-10-08/probe_migration_guard.py
# ⑨ main 蓝图层 url_map = 265（总 271 = main 265 + auth 4 + static 1 + bootstrap 1）
# ⑩ git：HEAD=534ce70…；git ls-files '*.pyc'=0；git ls-tree f60a54d^ 三个后缀文件命中
```

### 7.3 探针与产物（本任务新建，均在 `test-reports-2026-10/reconcile-2026-10-08/`）

| 文件 | 用途 |
| --- | --- |
| `probe_docs_numbers.py` / `.output.txt` | 迁移表集合、`_ENSURED_COLUMNS`、模型类、落盘导入、BytesIO、内联 role、`@bp.route`、模板数、routes.py 字节口径、`app/main` 文件清单 |
| `probe_migration_guard.py` / `.output.txt` | 迁移 `create_table` 的**守卫分类**（14 文件 / 13 字面 / 11 无条件）+ `p0p2messtables` 的 `upgrade()` 体 |
| `recon-docs.md` | 本文件 |

### 7.4 只读性自证

- 本文件全部动作 = `read` + `git` 只读命令 + 上表 2 个探针（**只写自己的输出文件**）+ 3 个门禁脚本（`--no-dump` / `--list` / `--selftest`，均不写仓库根 JSON）+ 1 次只读打开 `app.db`。
- 收尾复核：`app.db` = `2531328 / F5DA2306…0E0F065 / 2026-09-18 12:50:55`（与开工逐字相同）；`git status --porcelain` 仅出现未跟踪的既有规划文档与 `reconcile-2026-10-08/`，**无任何既有文件被改**。

---

## 8. 结论（一句话版）

**D1–D24 里 15 条仍漂移、6 条部分修正、1 条（D8）订正方向本身错误、1 条（D10）值两代过时**；
`AGENTS.md` 门禁表的期望读数**六项逐字一致 + 14 步一致**，唯一硬错是**退出码 `3=入口缺失` 与 `ci_gates.py:1138` 不符**，另有 12 处与源码冲突/口径需收紧（最要紧的是 **「`app/main` 只有 `routes.py` 一个路由模块」实为 7 个模块 265 条**）；
关键数字今天应为：**模板 87 / 路由 271（main 265，装饰器 269）/ 能力 44 / 角色 7 / 模型类 74 / `_ENSURED_COLUMNS` 10 表 43 列 / 单 head `p1nonctarget` 35 修订 / 内联 role 15+2 / `routes.py` 12155 行 / 导出内存生成 16（BytesIO 17）/ 落盘导入 8（全仓导入端点 9）/ 真库 75 表（业务 74）/ 迁移建 49 / 差集 31 / 无条件 `create_table` 11 文件（`c02604883c72` 24 处）**。
