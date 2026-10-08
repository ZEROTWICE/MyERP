# recon-arch.md · W1/t2 架构与工程纪律对账（批次3/8/9/10/11 + 阶段C 构建层与门禁卫生）

| 项 | 值 |
| --- | --- |
| 产出任务 | `t2`（kind=`work`，W1） |
| attempt_id | `171c31dc-9c44-4c3b-8dd2-c14fda76ac25`（attempt 6；attempt 5 为同一交付物的前序尝试） |
| 产出人 | 软件架构师2（架构/工程纪律/门禁链对账） |
| 产出时点 | **2026-10-08（+08:00）**；各条读数时点见条目内 |
| 工作目录 | `D:\workspace\wage_management_system - bak` |
| 解释器 | `F:\Miniconda\envs\wage\python.exe`（Python 3.9.21） |
| 统一前置 | `$env:PYTHONIOENCODING='utf-8'`；`$py='F:\Miniconda\envs\wage\python.exe'` |
| git HEAD（本次实测） | `534ce70b204c767feee551e8fd04e538374b1de8` |
| 权威输入 | `docs/开发与测试规划-2026-10-06.md` §1 批次3/8/9/10/11；`test-reports-2026-10/70-第2轮收口与阶段C移交.md` §9/§10；`AGENTS.md` 门禁表；`test-reports-2026-10/reconcile-2026-10-08/00-共享事实底盘.md`（W0 基线） |
| 只读声明 | **未修改任何既有文件**；本次唯一新增 = 本文件 + `probe_arch_docs.py` + `probe_arch_docs.output.json`（同目录）。`git status --short` 中受跟踪文件修改数 = **0** |

## 0. 一页结论

| # | 结论 | 依据 |
| --- | --- | --- |
| 1 | **批次3：1/6 已实现、5/6 未实现** —— B3-01 ✅ 已实现；B3-02/B3-03/B3-04/B3-05/B3-06 **全部未实现** | §1 |
| 2 | **批次8：0/12 已实现，2 条是「文档/脚本未落地」，其余 10 条代码面全是原状或行号漂移** | §2 |
| 3 | **批次9：0/16 已改**（文档漂移类条目**只判「文档是否已改」**，逐条实测文档均未改） | §3 |
| 4 | **批次10：仅 B10-01a 已实现**（具名 UNIQUE 已在位且早于本战役）；B10-01b/B10-02/B10-03/B10-04 未实现；B10-05/B10-06 不可在本机做（与计划自陈一致） | §4 |
| 5 | **批次11：0/6 已实现**；`docs/验收记录-*` **0 个文件** | §5 |
| 6 | **阶段C §10.1 构建层仍 blocked**：`Jenkinsfile` 生效 `error()` = **0**（`:112`/`:122` 仍是 `//` 注释）；GH `continue-on-error: true` **仍在** `:19`；`needs: gate` **仍未加**；blocking echo 清单**未含** `check_model_refs`/`check_http_contract`/`evidence_hash` | §6.1 |
| 7 | **§10.2 C-07 硬闸未实现**；`r2_c07_probe.py` 仍是 `blocked_no_guard`；`ci_gates.BUILD_LAYER_BLOCKED.state='blocked'`、`not_counted_as_passed=True` | §6.2 |
| 8 | **§10.8 工具卫生 8 条：1 条部分、7 条未改** | §6.3 |
| 9 | **§10.10 归档与卫生：`.tmp_v15_*` **0** 个（G-22 已消失）；但 `.tmp/`=**18555 文件 / 1.88 GiB**、`evidence/`=**13266 文件 / 312 MiB**（G-18 的「仍在增长」已兑现为磁盘占用） | §6.4 |
| 10 | **门禁 6 项静态读数全部 exit 0 且与 W0 基线逐字一致**；真库 SHA256 全程未变 | §7 |
| 11 | **本次新增排雷**：`c02604883c72`（0 字节）与 `python`（0 字节）**两个垃圾文件处于 git 跟踪状态**；`docs/` 有 2 个未跟踪文档；`_permission_matrix.json`/`_smoke_results.json` 仍在仓库根（已被 `.gitignore` 遮盖、mtime 未变，但**落点语义与 `--no-dump` 纪律的边界需登记**） | §6.4 / §8 |

---

## 1. 批次3 —— 测试资产与工程纪律加固（计划原文 §1 第 158–200 行）

> 计划抬头：**「最先做，成本最低、收益最广」**。逐条对账如下。

| 编号 | 计划原文要求（摘要） | 实测状态 | 证据（file:line / 命令+读数） | 剩余工作 | 置信度 |
| --- | --- | --- | --- | --- | --- |
| **B3-01** | 三条请求型脚本统一加 `--no-dump`/cwd 重定位：**不写仓库根 JSON 时 exit code 必须反映断言结果** | **已实现** | ① `scripts/smoke_test.py:90-91` `def default_out()` 返回 `.tmp/<RUN_ID>/` 并注明「绝对路径，与 cwd 无关 —— 不再是 cwd 相对的 `../`」；`:264-266` `--out`/`--no-dump` 已加；`:243` 落盘走 `out_path or default_out()`；`:112` 写盘。② `scripts/permission_matrix.py:82-84` `default_out()` 同形态；`:402-411` `--out`/`--no-dump`/`--out-modules`/`--inject-module`；`:117-127` `dump_matrix` 失败返回 `[WARN] 落盘失败（不影响退出码）`；`:376` `code = 1 if (anon_open or face_failures) else 0`。③ **`scripts/functional_test.py` 不落盘**：全文件 `json.dump` 仅出现在 `:342`（行内构造数据）与 `:489` `print('__RESULT__' + json.dumps(out))`（stdout），**无仓库根 JSON 写盘** ⇒ 该脚本本就无需 `--no-dump` | 无（本项收口） | **实测** |
| **B3-02** | `git rm` 掉 `app/main/sales_routes.py`（**1 字节、0 路由、0 引用**） | **未实现** | `(Get-Item app\main\sales_routes.py).Length` ⇒ **1**；`git ls-files app/main` ⇒ **10 个文件**，含 `app/main/sales_routes.py`（即**仍被 git 跟踪**） | 仍须删除；删除后同步 `B9-03`/`B9-16`/`B11-03` 的文档表述 | **实测** |
| **B3-03** | 给 `flask db *` 加**前置校验**：`DATABASE_URL` 未指向副本/未显式允许时拒跑 | **未实现**（且**无替代落点**） | ① `scripts/check_db_url_guard.py` **不存在**；② 全仓 `app/**`+`scripts/**` 的 `@app.cli.command` 只有 `app/__init__.py:238` `init-db`（`:242-255` 仅 `db.create_all()` + 建管理员，**无任何 URI 断言**）；③ `app/__init__.py:156-224` 的启动链**无闸**（`_ensure_schema` 定义在 `:103`，`db.create_all()` 在 `:107`，无守卫插入点）；④ 唯一的「参考实现」是**探针内注入**：`test-reports-2026-10/harness/r2_c07_probe.py:153` `def _r2_c07_guard(...)`、`:183-184` 拒绝文案、`:192` 注入调用点——**探针不改生产代码**（自查 docstring `:18-22` 自陈「生产面本轮冻结 ⇒ 探针把参考实现…」） | 真正的闸须落到 `app/__init__.py`（§10.2）。当前只有「建议 + 探针」 | **实测** |
| **B3-04** | 把 `docs/交付说明-P0P1.md §6.2 第 9 项` 的老库升级命令做成**一次性脚本** | **未实现** | 全仓 `*upgrade*` 过滤（排除 `migrations/versions`）仅命中 `merge_and_upgrade.py`（仓库根，2024 老物）；`scripts/` 下**无**老库升级一次性脚本。已有的 `scripts/migrate_sqlite_to_postgres.py` 是 **SQLite→PG 迁移**（`:1-9` docstring），**不是**「启动自愈 + `flask db stamp p1nonctarget`」那条老库升级路径 | 新建脚本或明确登记「不做」 | **实测** |
| **B3-05** | 在 `permission_matrix.py` 增「内联 role 计数 ≤ 白名单（15+2 带行号）」断言 | **未实现** | `scripts/permission_matrix.py` 全文：`:156-157` 只做**分类标记** `kinds.append('inline_role_check')`；`:376` 退出码**只**由 `anon_open` + C-06 `face_failures` 决定；`:377-384` 的两个 `[FAIL]` 分支**均不含** inline role 计数。⇒ **有探测、无白名单断言、不进判据**。另：本次独立实测内联 role = **Python 15 处 + 模板 2 处**（见下） | 新增白名单常量（含行号）+ 越界即失败 | **实测** |
| **B3-06** | 把「31 张 create_all 表」与「13 文件无条件 create_table」作为**脚本化对拍** | **未实现** | ① `scripts/`+`harness/` 全量 grep `create_all|create_table`：**唯一**涉及 `create_all` 判据的是 `r2_c07_probe.py`（`create_all_calls` 计数，判的是 **C-07 抛错点位置**，与 31 表无关）；`check_migration_heads.py` 只数 head（`:31-34`），**不数表**；② 我按计划 §3.4 口径**手工复算**：`migrations/versions` 文件 **35**（与 `revisions=35` 互证）；**含 `create_table` 的迁移文件：字面表名口径 = 13、AST 调用口径 = 14**（我本次独立计数得 14，与 §8.1 的口径差一致，非矛盾——见下注）；`create_table` 调用总数 **54**；**含守卫 if（引用 `has_table`/`get_table_names`）的文件仅 3 个**（`b1a01`=2、`da_add_process_assignment_tables`=4、`p0p2messtables_add_create_all_tables`=1），其余 **11 个文件守卫数 = 0**（即「无条件 create_table」）；`p0p2messtables_add_create_all_tables.py:815-817` 的 `upgrade()` 走 `for name in _CREATION_ORDER: _ensure_table(name, _TABLES[name])`（**幂等模式样板**）；③ 模型类 **74**（AST `db.Model` 子类） | 把「总表/迁移建/差 31」固化为对拍脚本 | **实测** |

> **注（口径澄清，防与同目录其它探针冲突）**：同目录另有 `probe_migration_guard.output.txt`（非本任务产出）给出「含字面表名 `create_table` 的文件 = 13 / AST = 14 / 调用总数 = 54」。我本次的独立计数**与其完全一致**——差异**只来自口径**（正则字面表名 vs AST 调用节点），**不是数据不一致**。因此计划写的「**13 文件**」是**正则口径**；若按「AST 调用」口径应为 **14**。**本项的两条数字都要带口径引用**，与 W0 §5-7 的纪律一致。

### 1.1 B3-05 的独立复核（内联 role 精确名单，供白名单直接引用）

**口径**：全仓 `current_user.role` 文本命中（`.py` 逐文件计数 + `templates/**/*.html`）。

| 范围 | 处数 | 精确行号 |
| --- | --- | --- |
| `app/main/routes.py` | **5** | `:337`（`in ('admin','manager')`，landing 分流）、`:340`（`ROLE_LANDING_ENDPOINTS.get(...)`）、`:350`（**日志文本**，非判据）、`:654`（`if current_user.role == 'admin'`，**可映射**）、`:5983`（`not in ['admin','hr']`，**可映射**） |
| `app/main/quality.py` | **10** | `:46`、`:82`、`:104`、`:120`、`:529`、`:822`、`:911`、`:1217`、`:1277`、`:1347` |
| `app/templates/main/quality/tasks.html` | **1** | `:340` `{% if current_user.role in ['admin', 'manager', 'inspector'] %}` |
| `app/templates/main/quality/task_detail.html` | **1** | `:13` `{% if task.status == 'pending' and (current_user.role in [...] or (current_user.role == 'inspector' and ...)) %}` |
| **Python 合计** | **15** | ✅ 与 W0 §6「15 + 2」逐字一致 |
| **模板合计** | **2** | ✅ 同上；**与计划 B8-06/B9-02 的行号 `:340`/`:13` 一致**（B9-02 已订正过的行号是对的） |

⚠ **口径声明**：`app/permissions.py:7` 的 docstring 也含 `current_user.role` 字样（**非判据**），故「全 app 文本命中 = 16」；**权威计数是 15 + 2**（`00-共享事实底盘.md` §6）。

⚠ **B9-02 的行号订正只完成了一半**：`quality/tasks.html:340` 实测正确，但 `docs/继续开发准备报告.md:50` **仍写 `quality/tasks.html:337`**（见 §3）。

### 1.2 B3-02 的连带影响（文档三层同时失真）

`sales_routes.py` 未删 ⇒ `AGENTS.md` 的「`app/main` 下现只有 `routes.py` 一个路由模块」表述**仍与实测冲突**（实测 8 个含 `@bp.route` 的模块），而计划要求的订正句式是「**已删除**」——**前提（删除）未成立，故订正也不能落**。

---

## 2. 批次8 —— 口径收口与残余清理（计划原文 §1 第 379–418 行）

| 编号 | 计划原文要求（摘要） | 实测状态 | 证据（file:line 原文片段） | 剩余工作 | 置信度 |
| --- | --- | --- | --- | --- | --- |
| **B8-01** | 库存列表页两处谓词统一为「NULL = 未存档」（计划记 `routes.py:4781`/`:4792`） | **未实现** | 实测行号**已漂移**到 `routes.py:4797` / `:4808`：`:4795-4797` `if not show_archived:` → `query = query.filter(RawMaterial.is_archived.is_(False))`（**仍排除 NULL**）；`:4807-4808` `query = query.filter_by(is_archived=False)`（**仍排除 NULL**） | 两处改为 `or_(is_(False), is_(None))` | **实测** |
| **B8-02** | 物料搜索 API 三处谓词统一（计划记 `routes.py:12037`/`:12065`/`:12094`） | **未实现** | 实测 `routes.py:12065` `raw_query = RawMaterial.query.filter_by(is_archived=False)`；`:12093` `consumable_query = Consumable.query.filter_by(is_archived=False)`；`:12122` `finished_query = FinishedProduct.query.filter_by(is_archived=False)`——**三处全是 `filter_by(is_archived=False)`**，均排除 NULL | 三处统一 | **实测** |
| **B8-03** | `Consumable` 列表第 4 处统一（计划记 `routes.py:6109`） | **未实现** | 实测漂移到 `routes.py:6125`：`get_available_consumables()` 内 `query = Consumable.query.filter_by(is_archived=False)`（`:6121` 是该函数 `def`） | 统一 + 进文档口径表 | **实测** |
| **B8-04** | **例外登记脚本**：把「刻意保留 `== False`」写进白名单常量，越界即失败 | **未实现** | `scripts/check_is_archived_policy.py` **不存在**；`AGENTS.md` 门禁表**无**该脚本条目（grep `check_is_archived_policy` ⇒ 0 命中） | 新建脚本 + 进门禁表 | **实测** |
| **B8-05** | 内联 `current_user.role` **15 处**逐处复核：可映射的映射、对象级归属**加注释固化** | **部分实现**（清单与实测一致；「可映射」的两处**未映射**；「加注释固化」**只落了一处普通说明性注释，非契约豁免**） | ① 清单命中：plan 列 `routes.py:647`/`:5967`；**实测该两处均为 `routes.py:654` / `:5983`**（`649-654` `# 如果设置了新密码` → `if form.password.data:` → `if current_user.role == 'admin':`；`:5982` `# 检查权限：管理员可以查看所有任务，普通用户只能查看自己的任务` → `:5983` `if current_user.role not in ['admin', 'hr']:`）——**行号漂移，判定逻辑未改**；② landing 三处 `:337`/`:340`/`:350` 抽查**无 inline-role 相关注释**（`:332-336` 的 docstring 讲的是重定向死循环，与 role 判据无关；`:350` 本身在日志 f-string 内）；③ `quality.py` 的 10 处实测 `:46/82/104/120/529/822/911/1217/1277/1347`，逐处上文**无「契约豁免/故意保留」注释**（逻辑本身多为对象级归属 `record.inspector_id != current_user.id`，合理但**注释未固化**） | 两处可映射的改 `can()`；其余按「契约豁免 + 行号」逐处注释（与 B3-05 白名单同源） | **实测** |
| **B8-06** | 模板剩余 **2 处**固化为契约豁免**并加注释** | **未实现**（行号对，注释无） | `app/templates/main/quality/tasks.html:340` 与 `task_detail.html:13` 上文各 8 行内**无任何豁免注释**（`tasks.html:336-339` 是 `<div class="btn-group btn-group-sm">` + 查看按钮；`task_detail.html:9-12` 是返回按钮） | 加注释（计划判据 4 要求「且都带豁免注释」） | **实测** |
| **B8-07** | 分页白名单残余盘点 + 锁死（`per_page ∈ {20,50,100}`） | **已实现（静态面）** | `routes.py:293` `def handle_pagination_args(f)`；`:304-305` `if per_page not in [20, 50, 100]: per_page = 20` | 若要「锁死」还需把白名单提为常量/加断言；就「残余盘点+锁定」的字面要求，**代码面已在位** | **实测** |
| **B8-08** | 搜索「条/件」文案：**默认不改** | **按计划「不改」（=正确状态）** | `global_search.html:47` 仍「共 N 条结果」；`advanced_search.html:155` 仍「N 条结果」；`:210` 仍「N 条{{ category }}记录」（计划记 `:47/282`、`:155/210`，`:282` 未命中，`:47`/`:155`/`:210` 命中） | 无（计划明确「默认不改」） | **实测** |
| **B8-09** | `advanced_search.html` 分类名未汉化的既有文案缺口 | **未实现** | `advanced_search.html:162-170` 仍只给 `employees`/`process_prices`/`products`/`customers` **4 个中文标签**；`:208-212` 仍是 `{% else %}` 兜底的「找到 N 条{{ category }}记录」（`inventory` 等分类名直接落英文） | 补分类名映射 | **实测** |
| **B8-10** | `download_product_template` 的**死清理块**（`temp_path=None` 后仍清理） | **未实现** | 实测漂移：`def download_product_template()` 在 `routes.py:7647`；`:7650` `temp_path = None`；`:7667-7674` `except` 块内 `if temp_path and os.path.exists(temp_path): os.remove(...)`；`:7675-7681` `finally` 块**同样**判断 `temp_path`——**`temp_path` 全函数从未被赋非 None 值**（模板走 `io.BytesIO()` `:7654-7656`）⇒ 两块恒为死代码 | 删除两块（计划判据 6a：`temp_path = None` 后仍存在清理块的端点 = 0） | **实测** |
| **B8-11** | `save_temp_file()` 的**目录泄漏**（`mkdtemp()` 建目录、`cleanup_temp_files()` 只删文件不删目录） | **未实现**（按计划的两条轨**都未做**） | 实测漂移：`routes.py:5083` `def save_temp_file(file: FileStorage) -> str:`；`:5085` `temp_dir = tempfile.mkdtemp()`；`cleanup_temp_files()` 在 `:2180`，`:2187-2199` 只 `os.listdir` + `os.path.isfile` + `os.remove(file)`——**无 `os.rmdir`/`shutil.rmtree`，目录永不回收**；唯一调用点 `:7698`（`import_products`）。⚠ 计划判据 6b 给的两条轨（轨一改钩子清理 / 轨二非沙箱计数）**均未见任何实现** | 选一条轨实施并写明（轨二须标「需非沙箱环境」） | **实测** |
| **B8-12** | `/api/quality/tasks/import` **不落盘**（直接 `pd.read_excel(file)`）→ 文档表述需收窄为「7 个落盘 + 1 个内存流」 | **代码已实现 / 文档未改** | 代码：`app/main/quality.py:1615` `def import_inspection_tasks():`；`:1634` `df = pd.read_excel(file)`（**传 file 对象、非路径**）。文档：`AGENTS.md:49` 仍写「**仅上传解析必须落盘**」（无「除 `/api/quality/tasks/import` 外」的例外）、`AGENTS.md:293` recipe 标题仍「Excel 导入（**必须落盘** + 行级容错）」 | 改 `AGENTS.md:49` 与 `:293`（**注意：`AGENTS.md:79-81` 不是 import 块**，见 §3 B9-09 勘误） | **实测** |

### 2.1 批次8 验收标准 4 的直读结论

计划判据 4：**「模板 `current_user.role` 命中数 = 2（且都带豁免注释）；模板/JS 硬编码 `/api/` 命中数 = 0」**。

- 前半：命中数 = **2** ✅，**豁免注释 = 0 处** ❌（B8-06 未做）。
- 后半：**`/api/` 前缀硬编码 = 0** —— 但我抽查到**非 `/api/` 前缀的硬编码 URL 6 处**（`consumable_categories.html:196` `/consumables/categories/add`、`inventory.html:937` `/inventory/auto-archive`、`products.html:439/604` `/code_rules/available/product`、`:665/714` `/products/import`）。**若判据按「硬编码 URL」口径读，则不为 0**；按「`/api/` 前缀」口径读则为 0。**该判据口径需澄清**（我按字面判「`/api/` 前缀口径 ⇒ 通过；硬编码 URL 广义口径 ⇒ 不通过」）。
- ⚠ 这 6 处属 W3/t4（模板与前端）范围，此处**只作口径澄清**，不重复 t4 的判定。

---

## 3. 批次9 —— 文档纠偏（**文档漂移类条目只判「文档是否已改」**）

> **判定纪律**：本批次**不判代码**（代码归批次3/8/10）；只回答一个问题：**计划要求改的那份文档，改了没有？**
> 实测工具：`test-reports-2026-10/reconcile-2026-10-08/probe_arch_docs.py`（只读，stdout JSON；产物 `probe_arch_docs.output.json`）。

| 编号 | 计划要求（摘要） | 状态 | 实测证据（file:line 原文片段） | 置信度 |
| --- | --- | --- | --- | --- |
| **B9-01** | D1/D2/D3：`docs/继续开发准备报告.md:14/24/57/67/96/97/272` 订正「261 视图 / 102 inline role / 194 路由 / 2 个 head」 | **未改** | `:14` `261 个 main 视图 = 150 装饰器 + 102 inline role + 9 仅 login_required`；`:24` `194 路由`；`:21`/`:57`/`:67` `2 个 head`；`:38` `102 个 inline current_user.role 端点`；`:97`/`:105` 亦含 `102 inline`。**旧数字全部原样在位** | **实测** |
| **B9-02** | D4/D13：「31 模板 77 处硬编码 role」订正为「模板 2 处 + Python 15 处」，并修正 `tasks.html:337` → `:340` | **未改** | `:20` `31 模板 77 处硬编码 role`；`:50` `31 模板 77 处硬编码 current_user.role …（`task_detail.html:13`、`quality/tasks.html:337`…）`——**`:337` 仍在**；`:273` 表格行写「**仅 2 处**」但**未给行号**；全文件 **`quality/tasks.html:340` 0 命中** ⇒ **行号修正未落** | **实测** |
| **B9-03** | D7：`app/main` 模块清单补 `sales_routes.py`（并在批次3 删除后写成「已删除」） | **未改** | `sales_routes` 在 `docs/开发进度与交接.md`、`docs/交付说明-P0P1.md`、`docs/业务流程现状与缺口.md`、`docs/继续开发准备报告.md` **四份全部 0 命中**。（⇒ 既没「登记」也没「已删除」；因 B3-02 未做，「已删除」也不可能写） | **实测** |
| **B9-04** | D8：删除「3 个后缀型残留其实被 git 跟踪，原记录有误」这处**错误的自订正** | **无法静态确证（需人工判读）** | 反证已实测：`git ls-files` 对 `*.bak`/`*.new`/`*.backup` 命中 **0**；`.gitignore:36-38` 为 `*.bak` / `*.new` / `*.backup`（与计划所述 `:36/38/37` 顺序不同，**内容一致**）⇒ 「本就被忽略」成立。但「文档里那句错误的订正**删没删**」需要逐句语义判读，**文本 grep 无法给出唯一答案** | **不可核** |
| **B9-05** | D9：「删除 4 个遗留备份文件」订正为**同一提交删了 7 个** | **无法确证（需 git 历史）** | 该条判据是 `git show --stat HEAD` 的历史事实；本次 HEAD = `534ce70b…`，**不是**计划里那条删除提交 ⇒ 静态树上不可复核。仅可证「今日 `app/main` 无这 7 个文件」 | **不可核** |
| **B9-06** | D15：把 `继续开发准备报告.md` §二/§四 的 4 个已拍板 ❓ 标注为「已决（见 §六）」，并把 T3 Q1/Q2/Q8 提到待拍板清单顶部 | **未改** | `:30` 仍是图例 `❓需业务确认`；`:35`/`:45`/`:46`/`:47`/`:52` 仍带 ❓；`:102-104` 的 P1-1/P1-2/P1-3 仍以 「❓…」作待拍板项。**全文件「已决」0 命中** | **实测** |
| **B9-07** | D10：交接指针 `148d8a5` → 现 HEAD `f60a54d`；D5：`_ENSURED_COLUMNS` → 10 表 43 列 | **未改（且情况更糟：真实 HEAD 已到 `534ce70b`）** | `docs/开发进度与交接.md:305` `远端 github/main == 本地 HEAD == 148d8a5`；`:315` 提交表第 7 行 `148d8a5`；`docs/继续开发准备报告.md:233`/`:243` 同。**两文件 `f60a54d` 均 0 命中**；而本次实测 `git rev-parse HEAD` = **`534ce70b204c767feee551e8fd04e538374b1de8`** ⇒ 三个指针（文档 `148d8a5`、计划要求写 `f60a54d`、真实 `534ce70b`）**全不相同** | **实测** |
| **B9-08** | D20：更新 `docs/交付说明-P0P1.md` §7 与 `docs/开发进度与交接.md` §8.2 的**复现命令**（受限环境须写清 shim / cwd 重定位 / `--no-dump`），并补 t6 F12 的独立复核通道 | **无法静态确证（部分反证）** | 反证：两份文档中「`_sandbox_compat`」的上下文未在本次逐节读全。**未取得可直接判「已改/未改」的坐标** ⇒ 归入下轮（见「剩余工作」） | **不可核** |
| **B9-09** | D21：把「导入端点必须落盘」收窄；**⚠ t6 F7 必须点名同步 `AGENTS.md:79-81`**；t5 勘误：真实落点是 `:48-50` 与 `:282` | **未改（且 t6 的点名本身是错的——本次勘定）** | ① `AGENTS.md:49` 仍「**仅上传解析必须落盘**」；`:293` recipe 标题仍「5) Excel 导入（**必须落盘** + 行级容错）」。② **行号勘定（本次实测，纠正 t5 与计划双方）**：`AGENTS.md:79-81` **不是 import 代码块**，而是**门禁表三行**——`:79` `check_migration_heads` 行、`:80` `check_properties` 行、`:81` `route_inventory` 行；`:282` **不是 recipe 标题**，而是 API recipe 代码块内的 `data = [{`；recipe 5 标题实测在 **`:293`**。⇒ **`AGENTS.md:79-81` 与 `:282` 两个锚点都需要订正，且 `:79` 处不需要「保留检索锚点」（它没有承担过政策锚点）** | **实测** |
| **B9-10** | D24：统一「无校验」口径为 **75=历史基线 / 5=当前无校验视图 / 15=当前内联 role 行数** | **未改** | `docs/测试报告-2026-08-11.md` 仍保留原口径：`:220` `全量清点…为 75 条`；`:301` `无校验路由 75 → 15`；`:433` `无角色校验的路由 75 → 15`；`:568` `降到 6 条`。**未见「三量纲不得互替」的统一表述** | **实测** |
| **B9-11** | D23：「5 个 head 已收敛」改为「（历史）曾多 head，现单一 head」 | **未改** | `docs/开发进度与交接.md:108` `**当前状态（2026-09-18 实测）**：5 个 head 已收敛为**单一 head `p1nonctarget`**`（**仍是「5 个 head 已收敛」句式**）；`:260` `~~收敛 5 个 head~~ —— **已完成**` | **实测** |
| **B9-12** | D5：`_ENSURED_COLUMNS` 数字统一为 **10 表 43 列** | **未改** | `docs/开发进度与交接.md` 的 `_ENSURED_COLUMNS` 命中（`:115`/`:118`/`:125`/`:249`/`:357`/`:391`/`:499`）**无一处给出「10 表 43 列」**；`docs/继续开发准备报告.md:59` 仍写「`_ENSURED_COLUMNS` 盲区」旧口径；`docs/交付说明-P0P1.md:47` 仍写「28 行」（旧）。**「10 表 43 列」在两个主文档 0 命中** | **实测** |
| **B9-13** | D22：`routes.py` 行数口径统一（12126 换行 / 12127 行） | **部分改（未写清两种口径，实际仅一种且与真实不符）** | `docs/继续开发准备报告.md:271` `**12126** 行`；`docs/开发进度与交接.md:341` `**12126 行**`。两处都只写一种值、**均未写口径**；另：**真实行数本次未复算**（`routes.py` 我未数行；W0/t5 记录 `12126 换行 / 12127 行`） | **实测（不完整）** |
| **B9-14** | 其余订正 D6/D11/D12/D14/D16/D17/D18/D19（含 `_ENSURED_COLUMNS`、`.gitignore`、`is_archived` 表、`globals()`、门禁 exit code、落盘/目录清理、死清理块、**13 文件无条件 create_table**） | **未改（至少 D19 的「13 文件」与实测不符）** | ① `AGENTS.md` 仍无 `check_is_archived_policy` / `check_notification_triggers` 条目（D16/D4 相关表述未补）；② **D19 数字对拍**：我实测「含 `create_table` 的迁移文件 = **14 个**」（计划写 13 文件 / 12 修订）；`c02604883c72` 的 `create_table` = **24 处** ✅ 与计划一致；③ `.gitignore` 实测 **42 行**（D6 要求订正「3 行」说法——现文件已是 42 行，说明**文件本身改过**，但文档是否同步未逐处读全） | **部分实测 / 部分不可核** |
| **B9-15** | **「质检能力已实现」整体降级**：`docs/业务流程现状与缺口.md` §一 与 `docs/开发进度与交接.md` 把「质检门禁与不合格处置」由【完整】改为「**部分实现**」 | **未改** | `docs/业务流程现状与缺口.md:51` `| 不合格品处置 NonconformityRecord | **完整** | 返工=新建任务、报废入报废库并扣料…`（**仍【完整】**）；`:50` 的 `InspectionTask/InspectionRecord` 是「部分」；**全文件「部分实现」0 命中**；`docs/开发进度与交接.md:20` 仍写 `质检入库 | 质检门禁、不合格处置… | **已完成**`，且该文件「部分实现」0 命中 | **实测** |
| **B9-16** | `AGENTS.md` 表述订正：补「`app/main` 有 **8 个含 `@bp.route`** 的模块」；门禁表补新脚本；修正 `:48-50` 与 `:282` 的「导入必须落盘」 | **未改** | ① `AGENTS.md` 中「8 个含 `@bp.route`」**0 命中**（`AGENTS_eight_modules_claim` = `[]`）⇒ **模块表述订正未落**；② 门禁表**未补** `check_is_archived_policy` / `check_notification_triggers`；③ `:49`/`:293` 的落盘表述**未收窄**（同 B9-09） | **实测** |

### 3.1 批次9 的净结论

**0/16 已改。** 逐条可归为三类：

1. **纯未改（8 条）**：B9-01、B9-02、B9-03、B9-06、B9-07、B9-10、B9-11、B9-12、B9-15、B9-16 —— 文档原文与旧数字**逐字仍在位**。
2. **前提未成立（1 条）**：B9-03（依赖 B3-02 删除）。
3. **静态不可核（4 条）**：B9-04（需语义判读）、B9-05（需 git 历史）、B9-08（未取得可判坐标）、B9-14（部分）。
4. **本次新增勘定（1 条）**：**B9-09 的两个锚点行号都错**（`AGENTS.md:79-81` = 门禁表三行；`:282` = `data = [{`；recipe 5 标题实测 `:293`）。

---

## 4. 批次10 —— 治理与外部环境（计划原文 §1 第 465–484 行；计划自陈「多数不可在本机完成」）

| 编号 | 计划原文要求（摘要） | 实测状态 | 证据（file:line / 命令+读数） | 剩余工作 | 置信度 |
| --- | --- | --- | --- | --- | --- |
| **B10-01a** | 匿名 UNIQUE 具名化，使**未来由 `create_all()` 新建**的表带具名约束 | **已实现（且在位已久）** | `app/models.py` 的 `db.UniqueConstraint(..., name=...)` 逐处命中：`:84` `uq_process_price_global_sn`、`:110` `uq_process_price_group_global_sn`、`:111` `uq_subtotal_process`、`:145` `uq_employee_global_sn`、`:242` `uq_bonus_penalty_global_sn`、`:314` `uq_task_assignment_global_sn`、`:394` `uq_salary_history_global_sn`、`:424` `uq_coefficient_history_global_sn`、`:466` `uq_finished_product_serial_number`、`:467` `uq_finished_product_global_sn` | ⚠ **与本计划的关系需澄清**：计划把 10a 列为「待做」，但具名约束**已在生产源码中**；需确认是「早于本战役已完成」还是「计划立项时已存在但被误列为待做」。**对既有库无效**（`create_all()` 不重建已存在表）这一点计划已自陈 | **实测** |
| **B10-01b** | 补 **31 张表**为正式、幂等迁移（沿用「表缺失才建表」模式） | **未实现（无法从静态树证「已完成」；且缺对拍脚本）** | 迁移文件 **35** 个；`revisions=35`；单 head ✅。但**无任何脚本**做「总表 75 / 迁移建 49 / 差 31」的对拍（同 B3-06）。`p0p2messtables_add_create_all_tables.py:27` 的 docstring 仍是**登记说明**（提及 `delivery_schedules`/`sales_order_delivery_batches` 只在……），**非 31 表的完整补齐** | 新建幂等迁移 + 对拍脚本 | **实测（未完成侧）/ 不可核（完成侧）** |
| **B10-01c** | 既有库匿名约束处置：**默认路径本轮不做**，仅登记限制 | **按计划「不做」= 正确状态** | 计划明文「默认不做」；`docs/开发进度与交接.md:108` 一带仍有 C-1 章程相关表述 | 无（保持登记） | **实测** |
| **B10-01-边界** | 明确不承诺「全链重放」；真实库仍靠「启动自愈 + `flask db stamp p1nonctarget`」（不撤除） | **未撤除（=符合边界要求）** | `app/__init__.py:103` `_ensure_schema` 定义、`:107` `db.create_all()`、`:224` 调用点、`:21-…` `_ENSURED_COLUMNS` 均在位；`check_migration_heads.py` exit 0 | 无 | **实测** |
| **B10-02** | 迁移碎片清理：`delivery_schedules` / `sales_order_delivery_batches`（create→alter→drop，无模型无表） | **未实现（碎片仍在）** | `migrations/versions/011e395c1aa4_add_sales_order_management_tables.py`：`:21` `op.create_table('delivery_schedules'`、`:38` `op.drop_table('sales_order_delivery_batches')`、`:146` `op.create_table('sales_order_delivery_batches'`、`:164` `op.drop_table('delivery_schedules')`（**同一文件内 create+drop 对**）；另 `a3f28e475446_add_sales_order_management_tables.py:71`/`:107` 又来一轮；`83bfde43921e…:21`/`:43` 对 `sales_order_delivery_batches` 做 `batch_alter_table` | 清理或显式登记「保留」 | **实测** |
| **B10-03** | 部署配置复核：`.env` 硬写 sqlite + 弱 `SECRET_KEY` | **未实现** | 实测（行号有漂移，**问题仍在**）：`scripts/deploy.bat:178` `echo SECRET_KEY=your-secret-key-here >> .env`、`:179` `echo DATABASE_URL=sqlite:///app.db >> .env`；`Jenkinsfile:295`/`:296` 同两句（计划记 `Jenkinsfile:252-253`）；`deploy.config.yml:35` `DATABASE_URL: "sqlite:///app.db"`（计划记 `:34-35`） | 改为必填校验 / 生成随机密钥 | **实测** |
| **B10-04** | `my_tasks.use` 已登记但**无路由使用** → 补装饰器或从 `CAPABILITIES` 删除 | **计划前提已被源码证伪 ⇒ 本项应销项（文档漂移）** | `app/permissions.py:96` 登记 `my_tasks.use`；**已有使用点**：`app/main/routes.py:3287` `@require_capability('task.manage', 'my_tasks.use')`（`update_task_status`）；`:356` `if not can_any('my_tasks.use', 'production_order.view', 'quality.view'):`（`user_dashboard` 分流）。`require_capability` 是 **OR 语义**（`app/permissions.py:151-152` docstring「具备任意一个能力即放行」、`:161` `if not can_any(*capabilities)`；`can_any` 在 `:132-134`）⇒ `my_tasks.use` **确为有效能力**。另 `check_templates.py` 报 `44 used on routes`（与 `44 declared` 相等，**无「declared - used 非空」**） | **撤销该条目**或改写为「已在使用（`routes.py:3287`/`:356`）」 | **实测**（**与计划相反**） |
| **B10-05** | C-2 PG 主从 failover 演练 + `pg_dump` 例行备份 | **不可在本机做（与计划一致）** | 计划自陈「`docker`/`pg_dump`/`psql` 均不在 PATH；无可连 Postgres 服务」。本次未复测 PATH（无必要，且不作为判据） | 登记「需外部环境」 | **不可核** |
| **B10-06** | C-3 断网多主 | **不立项（与计划一致）** | 计划明文「本期明确不做」 | 无 | **实测** |
| **B10-07** | `delivery_batches` 与发货**无关联**（计划依据：`shipping.py`/`mes_service.py` 中 `delivery_batches` 无命中） | **未做（既有缺口仍在，未修亦未登记）** | 本次未复测该 grep（属业务后端范围）；仅确认 `delivery_schedules`/`sales_order_delivery_batches` 的迁移碎片在（B10-02） | 待 T3 Q6-A 拍板 | **不可核** |
| **B10-08** | 客户删除未校验关联订单 | **未做** | 计划标注 t5 未逐读该路由（⏳）；本次未复核（属业务后端范围） | 待做 | **不可核** |
| **B10-09** | 编码规则/流水号日志查询页 | **未做** | 同上（需产品确认字段） | 待产品确认 | **不可核** |
| **B10-10** | 计件工资是否与质检结果挂钩（需先拍板） | **未做（须先拍板）** | 计划「✅ 可做，须先拍板」 | 待拍板 | **不可核** |
| **B10-11** | `/production_center` 实例完工不入库（与报工路径不一致，须先拍板） | **未做（须先拍板）** | 计划「✅ 可做，须先拍板」 | 待拍板 | **不可核** |

### 4.1 批次10 的净结论

**1 项已实现（B10-01a，且存疑「本就在位」）、1 项销项（B10-04 前提被证伪）、2 项按计划正确不动（B10-01c/B10-06）、2 项不可在本机做（B10-05/B10-06 类）、其余 5 项（B10-01b/B10-02/B10-03/B10-07~B10-09）为「可做而未做」，3 项（B10-10/B10-11 + B10-07）阻塞于拍板。**

---

## 5. 批次11 —— 最终收口（计划原文 §1 第 488–509 行）

| 编号 | 计划原文要求（摘要） | 实测状态 | 证据 | 剩余工作 | 置信度 |
| --- | --- | --- | --- | --- | --- |
| **B11-01** | 四份文档同步：`开发进度与交接.md`（总体进度、§七、§八提交表、`_ENSURED_COLUMNS` → 10 表 43 列、HEAD 指针、C-1 章程状态） | **未实现** | ① `_ENSURED_COLUMNS` 的「10 表 43 列」**0 命中**（同 B9-12）；② HEAD 指针仍 `148d8a5`（`:305`/`:315`），**真实 `534ce70b`**（同 B9-07） | 同 B9-07/B9-12 | **实测** |
| **B11-02** | `交付说明-P0P1.md` + `业务流程现状与缺口.md` 同步：已闭合项标「已闭合」；§6.7 `is_archived` 表补 `routes.py:6109`；「质检门禁与不合格处置」改**部分实现** | **未实现** | ① `业务流程现状与缺口.md:51` 仍【完整】（同 B9-15）；② 该文件 `:432` 的 `is_archived` 口径表行写「质检成品下拉 `get_finished_products`（`app/main/quality.py`，谓词 `:714`）」，**未补 `routes.py:6109`**（且实测 Consumable 谓词在 `routes.py:6125`）；③ 全文件「部分实现」0 命中 | 逐处订正 | **实测** |
| **B11-03** | `AGENTS.md` 数字与表述更新：门禁表补 `check_notification_triggers.py`/`check_is_archived_policy.py`；`app/main` 模块表述订正；`:48-50`/`:282` 落盘表述收窄 | **未实现** | ① 两脚本在 `AGENTS.md` **0 命中**；② 「8 个含 `@bp.route`」**0 命中**；③ `:49`/`:293` 落盘表述未收窄（同 B9-09/B9-16）。**门禁期望值本身正确**：`AGENTS.md:78` `87 templates / 44 declared / 40 used in templates / 44 used on routes / landing 5`、`:79` `HEADS=['p1nonctarget'], head_count=1, revisions=35`、`:80` `已扫描 23 个文件，模型类 74 个`、`:81` `total rules=271, duplicate…=0`、`:82` `violations 0`——**本次逐项实跑全部逐字相符**（§7） | 按 B9-09/B9-16 一并改 | **实测** |
| **B11-04** | 仓库卫生 + 推送核对：`git ls-files uploads` = 0、`git ls-files '*.pyc'` = 0、`git status --short` **干净（无未跟踪残留）**、`github/main...HEAD` = `0 0` | **部分实现** | ✅ `git ls-files uploads` = **0**；✅ `git ls-files '*.pyc'` = **0**；✅ `git rev-list --left-right --count github/main...HEAD` = **`0 0`**；❌ `git status --short` **不干净**（4 条未跟踪，见 §6.4） | 清理未跟踪残留并提交/忽略 | **实测** |
| **B11-05** | 各批次验收记录归档：`docs/验收记录-批次N-YYYY-MM-DD.md`（含未在沙箱执行项的显式标注） | **未实现** | `Get-ChildItem docs -Filter '验收记录*'` ⇒ **0 个文件** | 新建归档件 | **实测** |
| **B11-06** | 本规划文件自身定稿：去草稿标记，回填各批次实际结果与 T6 findings 销项状态 | **未实现** | `docs/开发与测试规划-2026-10-06.md` 内仍为**计划态**（批次条目全部以「待做」句型书写；无「实际结果」回填栏）。本文件（t2）恰是其所需的实测输入 | 待 81-规划出来后回填 | **实测** |

---

## 6. 阶段C —— 构建层、C-07、工具卫生、归档（`70-第2轮收口与阶段C移交.md` §10）

### 6.1 §10.1 ⛔ 构建层晋升（captain 独占）—— **全部未做**

| 计划动作 | 实测 | 证据 |
| --- | --- | --- |
| ① `Jenkinsfile:111/112/121/122` 解除 `error()` 注释 | **未做** | 生效 `error(` = **0** 行（`JENKINS_error_active` = `[]`）；注释态：`Jenkinsfile:112` `// error('[E-04] 门禁入口缺失：请先把 test-reports-2026-10/harness/** 纳入版本控制')`、`:122` `// error("[E-04] blocking 门禁失败: 4 项真闸门 / functional_test / permission_matrix / coverage_drift")`。⚠ **行号订正**：`error()` 文字位于 `:112`/`:122`；`:111`/`:121` 是其**上文注释行**（`// 第二阶段（A-63 第二步）…`）⇒ 计划「`:111/112/121/122`」是「注释行+代码行」四行，指代可接受但应写明 |
| ② GH `:19` 去 `continue-on-error`、`:57` 加 `needs: gate` | **未做** | `.github/workflows/docker-deploy.yml:19` `continue-on-error: true`（生效）；`:15-16` 注释自陈「第一阶段（当前）：report-only」；`:57-58` `build-and-push:` 下注释「第二阶段：在此加 `needs: gate`（当前不加 ⇒ gate 不阻塞发布）」，**无生效 `needs: gate`** |
| ③ blocking 步骤 echo 清单补 `check_model_refs`/`check_http_contract`/`evidence_hash` | **未做** | `Jenkinsfile:97` 生效 echo 清单原文：`'[E-04] blocking: check_templates/check_migration_heads/check_properties/check_db_bootstrap/functional_test/permission_matrix/coverage_drift/run_gates(非环境依赖部分)'`；三者在 `Jenkinsfile` 全文件 **0 命中**（`JENKINS_mentions_new_gates` 全空） |
| 前置 P-3「真实 CI 观测 ≥1 轮全绿」 | **0 轮（不可核）** | 无 CI 运行日志入口；`ci_gates.py:117-132` `BUILD_LAYER_BLOCKED.state='blocked'`、`not_counted_as_passed=True`、`blocked_reason` 逐字指向上述三处 |

**⇒ 构建层 = `blocked`，与 `70-` C-12 一致；**不得折算 pass**（A-93）。**

### 6.2 §10.2 C-07 实现（应用级真实库硬闸）—— **未实现**

| 项 | 实测 |
| --- | --- |
| 落点 | `app/__init__.py:156-224` 之间 —— 实测该区段**无任何闸**（`_ensure_schema` 在 `:103`、`db.create_all()` 在 `:107`、`:224` 是 `_ensure_schema(app)` 调用点） |
| 探针现状 | `test-reports-2026-10/harness/r2_c07_probe.py:758` `cur_state = 'blocked_no_guard'`；`:1267` docstring「且 state = blocked_no_guard（规格层仍全过，因为闸由探针注入）」；`:1288` 期望表含 `('absent-repo', 'absent', 'inject', 'blocked_no_guard', 0, False)` |
| 判据（计划） | `--guard-source present` ⇒ `create_all_calls` 由 **1 → 0**，且 `--strict-current-guard` 通过 —— **未执行**（需注入，属 Modification 面，超出本任务只读范围） |
| 登记 | `ci_gates.py:127-128` `condition_to_unblock` 与 §10.1 同一条件 |

### 6.3 §10.8 工具与口径卫生（8 条）—— **1 条部分、7 条未改**

| # | 项 | 实测状态 | 证据 | 置信度 |
| --- | --- | --- | --- | --- |
| 1 | `reconcile_r2.py:555` 重指 `--coverage <run 产物>`（判据：不再是「无参假绿」） | **未改（仍是无参调用，且断言与真实语义不符）** | `reconcile_r2.py:555` 原文：`chk_subprocess([PY, '-B', 'test-reports-2026-10/harness/coverage_drift.py'], '漂移判据 exit 0')` —— **无 `--coverage`**。而本次实测 `coverage_drift.py` 无参 ⇒ **exit 2**（见下），故该断言的 `expect_exit=0` 与真实行为**相反** ⇒ **项必然报红**（即 G-16 残留 1/2 仍在） | **实测** |
| 2 | `r2_v14_ledgerbook.py:259-262` 的 `command` 补 `--coverage`（判据：`exit_code` 与实际一致） | **未改** | `r2_v14_ledgerbook.py:257-261` 的 `command` 拼串仍为 `'%s -B …/coverage_drift.py；… % (PY, PY, PY, PY)'`（**无 `--coverage`**），而 `:262` `'exit_code': 0` ⇒ **记录与真实（无参 = exit 2）矛盾** | **实测** |
| 3 | `40` §4.5 工作区版**提交**（判据：`git status` 不再显示 `M 40-…`） | **已实现** | `git status --short -- "test-reports-2026-10/40-第2轮实测Runbook与台账规范.md"` ⇒ **空**（无 `M`）⇒ 已提交或已还原。文件 56294 B / mtime `2026-10-07 23:02:53`（与 `70-` G-17 记的「工作区 56294 B」**同字节**，且工作区已干净 ⇒ **工作区版已入库**）；`:367` 含 `writable_literal 6 → 108、writable_any 14 → 116、uncovered_writable 101 → 0` | **实测** |
| 4 | `analysis_ledger` claim / `improve_plan` 行号 / `final_recount` 101·141 / 文档 `6/14/101` 同步 | **未改** | `final_recount.py:313-314` 仍 `("non_get_without_any_hit", 141), ("rules_non_get", 153), ("uncovered_writable", 101), ("method_level_get", 161)`；`:378` 同。⇒ **101/141 仍在**（`LOCKED` 已按 A-70 为 `108/116/0`） | **实测** |
| 5 | `api_matrix.py:808-809` 的 24 条 CSRF 文案判据**删除或重指**（判据：同一 CSRF 面只剩一个分母 `133/133`） | **未改** | `test-reports-2026-10/harness/api_matrix.py:808-809` 原文仍是文案判据：`csrf_blocked = r.status_code == 400 and ('csrf' in body.lower() or '令牌' in body or 'Token' in body)`；`:814` `if exempt or csrf_blocked:`、`:821` why 文案。文件 804 行 / mtime `2026-10-06 22:44:30`（**本战役期间未改**） | **实测** |
| 6 | `ci_gates` 加**运行锁**（N-6/A-98；判据：并发跑两次不再伪 blocking 失败） | **未改** | `ci_gates.py` 全文 **无** `lock`/`flock`/`msvcrt`/`O_EXCL`/`acquire` 任何实现（唯一命中是 docstring 里的无关词） | **实测** |
| 7 | `regression_preflight verify` 增**有意复跑白名单**（N-5） | **未改** | `regression_preflight.py` 全文 `whitelist`/`WHITELIST`/`intentional`/`有意` **0 命中** | **实测** |
| 8 | 锚点 #5 加 `superseded_by`（V-16 §6-N-1 建议 a） | **未改（锚点侧无该字段）** | `70-` 指定的「锚点 #5」= `<run>/coverage.json` 冻结锚点；本次在 `harness/` 内 `superseded_by` 命中仅**台账脚本自建字段**（`r2_c11_ledger.py:295`、`r2_v14_ledgerbook.py:142/172/209/242/289/335/369`、`uat_chains.py:2787/2833`，值全为 `None`）与 `w2w3_uatdiff.py:869`（`superseded_by_task`，**另一对象**）。**冻结锚点 `evidence/harness/coverage.json` 未获新字段** | **实测（部分推断）** |

### 6.4 §10.10 归档与卫生 + 仓库卫生实测

| 项 | 实测读数 | 说明 |
| --- | --- | --- |
| `test-reports-2026-10/evidence/` | **13266 文件 / 327,580,714 B（312.41 MiB）** | `.gitignore:42` `/test-reports-2026-10/evidence/` **已忽略** ✅ |
| `test-reports-2026-10/.tmp/` | **18555 文件 / 2,015,360,185 B（1.88 GiB）** | `.gitignore:41` `/test-reports-2026-10/.tmp/` **已忽略** ✅ |
| 仓库根 `.tmp_v15_*`（G-22） | **0 个**（`hygiene_repo_root_tmp_v15` = `[]`） | **G-22 已消失**（已被清理或改名）——与 `70-` 的 6 个污染件不符 ⇒ **该缺陷已闭合（或已迁移）** |
| `.gitignore` 覆盖 `uploads/temp` | `:32` `/uploads/temp/` ✅ | B11-04 要求满足 |
| `.gitignore` 覆盖 `.tmp` | `:41` `/test-reports-2026-10/.tmp/` ✅ | ⚠ **仅覆盖 `test-reports-2026-10/.tmp/`**；仓库根 `.tmp/` 与 `_probe_tmp/` **未被忽略** |
| `.gitignore` 行数 | **42 行** | D6 要求订正「3 行」旧说法——**文件本身已是 42 行** |
| `git status --short` | **4 条未跟踪**：① `_probe_tmp/`（含 `gate-baseline.txt` 24704 B）② `docs/交接提示词-批次3开工-2026-10-06.md` ③ `docs/开发与测试规划-2026-10-06.md` ④ `test-reports-2026-10/reconcile-2026-10-08/`（本次战役产物目录） | ❌ B11-04 的「无未跟踪残留」**不满足**。其中 **②③ 是本次规划的权威输入文档却未入库**；① 是**未知来源**的残留（非本任务创建） |
| `git ls-files uploads` | **0** ✅ | |
| `git ls-files '*.pyc'` | **0** ✅ | |
| `github/main...HEAD` | **`0 0`** ✅ | 与远端一致 |
| 仓库根垃圾（**本次新增排雷**） | `c02604883c72`（**0 B，TRACKED**）、`python`（**0 B，TRACKED**）、`test_batch_process_demo.html`（**1 B，TRACKED**） | 三个 `git ls-files` 命中 ⇒ **已入库的垃圾文件**，B11-04 未覆盖此口径 |
| 仓库根跑测试残留（已忽略） | `_permission_matrix.json`（33679 B，mtime `2026-10-06 10:13:00`）、`_smoke_results.json`（135512 B，mtime `2026-10-06 20:39:57`） | 二者 `.gitignore:25-26` 已忽略、且 **mtime 均早于 B3-01 收口**（改后不再产生）⇒ **不构成 B3-01 回归**；但「落点纪律」的边界应登记（见 §8） |

**⇒ 门禁链与仓库卫生的净结论**：`.tmp/` 与 `evidence/` 的**体量（合计 ≈ 2.19 GiB）**是当前最实的卫生风险；G-18「改动面仍在增长」已从「文件在写」演进为「磁盘被占」。

---

## 7. 门禁链独立复跑（本次实测，全部只读）

> 统一前置：`$env:PYTHONIOENCODING='utf-8'`；`$py='F:\Miniconda\envs\wage\python.exe'`；cwd = 仓库根。

| # | 门禁 | 命令 | 实测读数（逐字） | exit | 与 W0 基线 |
| --- | --- | --- | --- | --- | --- |
| G1 | `check_templates` | `& $py -B scripts\check_templates.py` | `[templates] parsed 87 files` / `[permissions] 44 declared / 40 used in templates / 44 used on routes` / `[landing] 5 role landing endpoints` / `RESULT: OK` | **0** | 一致 |
| G2 | `check_migration_heads` | `& $py -B scripts\check_migration_heads.py` | `HEADS=['p1nonctarget']` / `head_count=1  revisions=35` / `OK: 单一 head p1nonctarget` | **0** | 一致 |
| G3 | `check_properties` | `& $py -B scripts\check_properties.py` | `已扫描 23 个文件，模型类 74 个` / `RESULT: OK（未发现把 @property / 不存在的列当数据库列用）` | **0** | 一致 |
| G4 | `check_model_refs` | `& $py -B scripts\check_model_refs.py` | `[model_refs] scanned 23 files, name_query_refs 602, violations 0` / `RESULT: OK` | **0** | 一致（计数勿钉） |
| G5 | `route_inventory` | `& $py -B scripts\route_inventory.py` | `[routes] total rules=271` / `duplicate (method,path) registrations=0` / `GET no-arg=104 GET with-arg=56 non-GET=110` / `[e03] … "class": "报告型（无判据语义 => 恒 exit 0…）"` | **0** | 一致（**报告型，退出码不进判据链**） |
| G6 | `check_db_bootstrap` | `& $py -B scripts\check_db_bootstrap.py` | `种子库账号数（经自举导入到空库）= 64` / `首次启动导入 64 个账号，再次启动后 64 个` / `无种子库时账号数 = 0` / `直接拷贝 6712 行，跳过 0 张表` / `OK: 空库自举、幂等、无种子库跳过、整表无遗漏 均通过` | **0** | 一致 |
| G7 | `ci_gates --list`（**只列不跑**） | `& $py -B test-reports-2026-10\harness\ci_gates.py --list` | 尾行 `[ci_gates] phase=first interpreter=F:\Miniconda\envs\wage\python.exe steps=14` | **0** | 一致（14 步 = blocking 10 + report-only 4） |
| G8 | `coverage_drift`（无参，**用法错误出口**） | `& $py -B test-reports-2026-10\harness\coverage_drift.py` | `[e03] exit_code_semantics={… "rule": "no --coverage -> exit 2（用法错误，不是回归）…" …  "code": 2}` | **2** | 与 `70-` C-9/§5「已按 fail loud 落地」**一致**（**不是回归**） |
| G9 | `coverage_drift --selftest` | `& $py -B test-reports-2026-10\harness\coverage_drift.py --selftest` | `[coverage_drift] 自检结果 9/9 通过 => 敏感性 OK` | **0** | 一致 |
| G10 | 真库不变量（**开工/收尾两次**） | `(Get-FileHash app.db -Algorithm SHA256).Hash` 等 | 两次均 `F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065` / `2531328` / `2026-09-18 12:50:55` | — | 一致（**本次全程未写库**） |
| G11 | 受跟踪文件修改数 | `git status --porcelain --untracked-files=no` | **0 行** | — | 一致（**只读纪律成立**） |

⚠ **G5 口径纪律**（照抄 W0 §2）：`route_inventory` 属**报告型**，退出码恒 0、**无判据语义**，不得写入任何 blocking 判据；`harness/run_gates.py` 的 `route_inventory_native_probe` 属**环境依赖探针**，同样不得写入 blocking 判据。

---

## 8. 剩余工作清单（按「阻塞下游」排序）

| 优先级 | 项 | 落点 | 说明 |
| --- | --- | --- | --- |
| **P0-1** | **批次9 整体未动（0/16）** + `AGENTS.md` 表述未订正 | `docs/开发与测试规划-2026-10-06.md` §1 批次9/11 | 文档层与源码差距是「规划 ≠ 现实」的根因；且**本规划文件本身也未入库**（未跟踪） |
| **P0-2** | 构建层晋升（A-63 第二步） | `Jenkinsfile:112/122`、`.github/workflows/docker-deploy.yml:19`/`:58` | captain 独占；判据 `AC-63-1…7` 不变 |
| **P0-3** | C-07 应用级真实库硬闸 | `app/__init__.py:156-224` 区段 | 与 B3-03 同一件事，**建议合并为一项**（计划把它们拆成 B3-03 与 §10.2 两处） |
| **P1-1** | B3-02 删除 `app/main/sales_routes.py`（1 B） | `app/main/` | 连带解锁 B9-03/B9-16/B11-03 的表述订正 |
| **P1-2** | B8-01/02/03 六处 `is_archived` 谓词统一 + B8-04 例外登记脚本 | `routes.py:4797/4808/12065/12093/12122/6125` | 六处全是 `filter_by(is_archived=False)` 或 `is_(False)` |
| **P1-3** | B8-06 模板豁免注释（2 处）+ B8-05 可映射两处改 `can()` | `quality/tasks.html:340`、`task_detail.html:13`；`routes.py:654`/`:5983` | 判据要求「带行号的白名单」 |
| **P1-4** | B8-10 死清理块删除 + B8-11 目录回收（选一条轨） | `routes.py:7667-7681`；`routes.py:5083-5085`/`:2180-2201` | 判据 6a 可静态判；6b 轨二**须标「需非沙箱环境」** |
| **P1-5** | B3-05 内联 role 白名单断言（可直接用 §1.1 的 15+2 名单） | `scripts/permission_matrix.py` | 现在只有分类标记、无判据 |
| **P1-6** | B3-06 / B10-01b 的「31 表对拍」脚本化 | `scripts/` | 本次已给出可复算口径（迁移 35 文件、含 `create_table` **14** 文件、模型 74 类），但**「总表 75 / 迁移建 49 / 差 31」未复算**（需读库） |
| **P2-1** | §10.8 的 1/2/4/5/6/7/8（7 条） | `harness/reconcile_r2.py:555`、`r2_v14_ledgerbook.py:257-261`、`final_recount.py:313-314/378`、`api_matrix.py:808-814`、`ci_gates.py`、`regression_preflight.py`、冻结锚点 | 零生产代码风险 |
| **P2-2** | 仓库卫生：`.tmp/` 1.88 GiB + `evidence/` 312 MiB 体量治理；`c02604883c72`/`python` 两个 0 B 跟踪垃圾；`_probe_tmp/` 与两份 `docs/` 未跟踪件 | 仓库根 / `test-reports-2026-10/` | B11-04 的「无未跟踪残留」判据当前**不满足** |
| **P2-3** | B10-03 部署配置（`SECRET_KEY=your-secret-key-here` ×3 文件） | `scripts/deploy.bat:178`、`Jenkinsfile:295`、`deploy.config.yml:35` | 计划标「✅ 可做」 |
| **P3** | B10-04 **撤销/改写**（前提已被源码证伪） | `docs/开发与测试规划-2026-10-06.md` | `my_tasks.use` 在 `routes.py:3287`/`:356` **已在使用** |

### 8.1 计划文本自身需要订正的坐标（供 81-规划采信）

| 计划原文坐标 | 本次勘定 | 差异类型 |
| --- | --- | --- |
| `AGENTS.md:79-81` = import 代码块（B9-09 的 t6 F7 点名） | **实为门禁表三行**（`:79` heads / `:80` properties / `:81` route_inventory） | **行号错误** |
| `AGENTS.md:282` = recipe 5 标题 | **实为 `data = [{`**；recipe 5 标题在 **`:293`** | **行号错误** |
| `routes.py:4781`/`:4792`（B8-01） | **`:4797`/`:4808`** | 行号漂移 |
| `routes.py:12037`/`:12065`/`:12094`（B8-02） | **`:12065`/`:12093`/`:12122`** | 行号漂移 |
| `routes.py:6109`（B8-03/B11-02） | **`:6125`** | 行号漂移 |
| `routes.py:7619`/`:7622`/`:7640-7651`（B8-10） | **`:7647`/`:7650`/`:7667-7681`** | 行号漂移 |
| `routes.py:5067`/`:5069`/`:2173-2194`（B8-11） | **`:5083`/`:5085`/`:2180-2201`** | 行号漂移 |
| `Jenkinsfile:252-253`（B10-03） | **`:295`/`:296`** | 行号漂移 |
| `Jenkinsfile:111/112/121/122`（§10.1） | `error()` 文字在 **`:112`/`:122`**（`:111`/`:121` 是上文注释） | 指代含糊 |
| `deploy.config.yml:34-35`（B10-03） | `DATABASE_URL` 在 **`:35`** | 行号微漂 |

---

## 9. 本文件的边界与不可核项

1. **本文件不含业务功能实现度判定**（批次4/5/6/7 的质检语义、阶段C P1–P12）——归 t11/`recon-backend.md`。
2. **本文件不含需求条目状态**（REQ/GAP/AC）——归 t5/`recon-requirements.md`。
3. **模板层细节（批次6 UI、P7 下拉、前端资产）不在本文件范围**——归 t4/`recon-frontend.md`（本次仅作为 B8-06/B9-02 的行号证据使用）。
4. **未执行任何会发请求的脚本**（`smoke_test`/`permission_matrix`/`functional_test`/`run_gates`/`ci_gates` 整链）——属 W0 §2 的边界；本文件只跑**静态/自举型**门禁（G1–G6、G8–G9、G7 只列不跑）。
5. **「真实 CI 观测轮数」（P-3 = 0 轮）**为 `70-` 的既有结论，本次**无 CI 日志入口可复核** ⇒ 标**不可核**，不作独立判定。
6. **显式不可核项（需非本任务通道）**：B9-04（需语义判读）、B9-05（需 git 历史 `git show`）、B9-08（未取得可判坐标）、B9-13（未复算 `routes.py` 真实行数）、B10-05（需 PG 环境）、B10-07~B10-11（需上游拍板或业务后端复核）。
7. **无浏览器/无 GUI**：本任务全部结论来自源码与静态资产判读；任何「渲染正确性/交互行为」类断言一律标**无法核实（需浏览器）**。

## 10. 引用纪律（照抄 W0 §5，本文件遵守）

1. **『文件存在』≠『已实现』** —— 本文件对 B3-03/B3-04/B8-04 均判「**未实现（脚本不存在）**」而非停留于「文件存在」。
2. **每条判定给坐标**：`file:line` 或 `命令 + 读数`，二者必居其一。
3. **不引用转述**：计划/captain/t6 的说法一律作**待验证线索**，回源验证后才写；本次已**纠正两处转述错误**（`AGENTS.md:79-81`/`:282` 的行号；B10-04 的「无路由使用」）。
4. **源码为唯一事实来源**：文档与源码冲突时以源码为准，并登记为「文档漂移」（§3 全表）。
5. **行号以本次实测为准**：本文件所有行号均为 **2026-10-08 本次实测**；任何后续改动都会再次漂移，引用前请复跑 §7 命令。
6. 状态词表：`已实现` / `部分实现` / `未实现` / `文档漂移` / `无法核实（需浏览器）` / `不可核`；置信度：`实测` / `推断` / `不可核`。
7. **数字必须带口径**（如「模板内联 role」写明 = 文本命中口径、排除 `permissions.py:7` docstring）。
