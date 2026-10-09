Rule Name: project-rules

Description:
面向 ZEROTWICE/MyERP（Flask + SQLAlchemy + Jinja2）的项目级约束与可复用片段，统一接口/风格/安全/分页/导出等，实现与现有代码一致，降低幻觉。DeepWiki 仅作辅助检索，冲突时以本地源码为准，协议见 `.cursor/rules/deepwiki-workflow.mdc`。参考规范：`https://cursor.com/cn/docs/context/rules#project-rules`。

---

Scope:
- Applies to this repository（后端 Python、Jinja2 模板、前端 JS 交互、部署脚本相关改动）

---

开始开发前必读（跨会话交接）:
- `docs/开发进度与交接.md` — 当前进度、批次1 交付内容、批次2 已确认的业务决策，以及 Python 环境位置、迁移与仓库卫生等操作要点。
- `docs/业务流程现状与缺口.md` — 全量功能盘点、端到端业务流程、缺口清单。
- `docs/交付说明-P0P1.md` — P0/P1 交付验收、遗留项清单、**老库升级路径（启动自愈 + `flask db stamp`）与复现命令**。
- 权限改动只在 `app/permissions.py` 的 CAPABILITIES 登记一次，模板用 `can()`、路由用 `@require_capability`；改完跑 `scripts/check_templates.py`。
- **禁止 `flask db migrate`**：schema 事实来源是 `db.create_all()` + `app/__init__.py` 的 `_ENSURED_COLUMNS`/`_ensure_schema()` 启动自愈（31 张表不在迁移历史里），自动生成迁移会把它们全部纳入并产生与线上库冲突的脚本。新增表/列请**手写迁移 + 存在性判断 + 在 `_ENSURED_COLUMNS` 登记**。迁移链已收敛为单一 head `p1nonctarget`，但**全链重放不可行**，老库/新库统一走「启动自愈 + `flask db stamp p1nonctarget`」，细节见 `docs/交付说明-P0P1.md` §6.2 第 9 项。⚠ 跑任何 `flask db *` 前必须先把 `DATABASE_URL` 指向目标库，否则 `create_app()` 的启动自愈会写到当前库上（本项目已因此误写过真实 `app.db`）。
- 新增路由默认加 `@require_capability`；确实所有角色都要用的，才只留 `@login_required`。未登录的 JSON 401 由 `app/__init__.py` 的 `login.unauthorized_handler` 统一处理，不要在端点里自己判断——注意 `@login_required` 是外层装饰器，未登录请求到不了它下面的 `@require_capability`。

---

Guidelines:
- 架构与分层
  - 蓝图路由：`app/main/routes.py`（任务/生产/库存/销售/产品等）与 `app/main/quality.py`（质量）。模板/静态：`app/templates`, `app/static`。ORM：`app/models.py`。
  - 全局流水号：统一使用 `SerialNumber.get_next_number()`（Employee/Task/ProductionRecord/Inspection 等）。
  - 权限：`Flask-Login` + `current_user.role`。系统内**实际只有 7 个角色**（`app/permissions.py` 的 `ROLES`）：`admin` / `manager` / `hr` / `accountant` / `inspector` / `sales` / `user`。模板菜单与后端路由均需校验；判断一律走 `can()` / `@require_capability`，不要新写 `role in [...]`。

- 模块边界
  - 质量相关在 `app/main/quality.py`；任务/生产/库存/销售/产品等在 `app/main/routes.py`，同类功能就近归类并分段注释。
  - 复杂搜索/筛选抽到 `app/services/search_service.py`。

- 路由/端点规范
  - 必须通过 `url_for('main.xxx')` 生成链接；端点名与函数名保持一致；页面路由返回模板，JSON API 使用 `/api/...` 前缀。
  - 导出/下载：`send_file` + `download_name`（可含中文）。**优先用 `io.BytesIO` 内存生成**（`wb.save(buf)` + `buf.seek(0)` + `send_file(buf, ...)`），**不要**再写临时文件 + `@after_this_request` —— 仓库现有 13 处已是内存生成模式，且 `send_file` 之后临时文件在 Windows 上仍被占用，清理必然抛 `WinError 32` 并被静默吞掉（历史包袱）。
  - 任务模块端点保持既有：
    - GET/POST `/tasks`；GET `/tasks/<id>`；DELETE `/tasks/<id>`；POST `/tasks/<id>/edit`；POST `/tasks/<id>/update_status`
    - GET `/tasks/template`；POST `/tasks/import`；GET/POST `/export_tasks`（双支持，勿破坏）。
  - 库存 API 返回：`{'success': True, 'data': [...]}`；字段含 `id, name/specification/quantity` 等（Select2 兼容）。
  - 质量 API 固定前缀 `/api/quality/...`；必要 JSON POST 使用 `@csrf.exempt`，其余走 CSRF 头（见 base.html 中 jQuery `$.ajaxSetup`）；仅对必要 JSON API 豁免，禁止大面积豁免。

- 数据/事务/日志/审计
  - 使用 SQLAlchemy；复杂查询用 `db.func/join/subquery`；失败必须 `db.session.rollback()` 并 `current_app.logger.error(...)`。
  - 重要写操作记录 `AuditLog`（含 `can_rollback/rollback_type`），遵循现有模式。

- Excel 导入/导出
  - 逻辑封装在 `app/utils/excel_generator.py`；路由只负责查询与文件清理。
  - **导出/模板下载：用 `io.BytesIO` 内存生成**，不落盘（见上「路由/端点规范」）。
  - **需真实路径时才落盘**：`ExcelGenerator.parse_*` 需要真实路径，因此导入端点才写 `current_app.config['TEMP_FOLDER']`（`file.save(temp_path)`），由 `cleanup_temp_files()` + `finally` 清理；辅助函数 `save_temp_file()`（`app/main/routes.py:5600`）用 `tempfile.mkdtemp(dir=TEMP_FOLDER)`，空目录由同一清理钩子按过期时间回收。当前 **11 个导入端点 = 10 落盘 + 1 内存流**：10 落盘 = 5 个直接写 `TEMP_FOLDER` + 2 个 `tempfile.gettempdir()` + 1 个 `save_temp_file()` + 2 个 `save_upload_files()`（`app/main/routes.py:2776` `import_alloy_process_prices`、`:2825` `import_alloy_bom`；helper 定义 `app/main/routes.py:5606`，落系统 temp、由调用方 `finally shutil.rmtree` 回收）；1 内存流 = `app/main/quality.py:1707` `import_inspection_tasks` 走 `pd.read_excel(file)` 不落盘。历史件（`B17-00-契约冻结.md:97`、`phase1-snapshot/**`、`reconcile-2026-10-08/**`、`33/80/81`）保留当时读数 9/8/1，不追改。
  - 导入必须**行级容错**：坏行只记「第 N 行：…」并跳过，绝不整体 500；文本日期用 `pd.to_datetime` 兜底（参考 `import_tasks`、`import_inspection_tasks`）。

- 前端交互约定（模板/JS）
  - 依赖 `base.html`（Bootstrap 5、jQuery、Select2、SweetAlert2、Toastr），移动端优化 `mobile-optimization.js`、`mobile-components.css`。
  - 列表通用参数：`page/per_page/search/status/direction/sort/start_date/end_date`；`handle_pagination_args` 统一校验分页参数。
  - Select2 异步接口返回结构与字段名与现有实现保持一致，前端本地格式化映射。

- 命名与代码风格（Python）
  - 函数名用动词短语；变量用完整英文单词；优先守卫式早返回；日志与用户提示分离（logger vs flash/JSON）。
  - 禁止随意改名/新增字段；如需重命名，后端短期兼容旧字段别名（如 `name/material_name`）。

- 兼容性/变更约束
  - 任何端点/字段改动前先全局搜索模板/JS引用；如需变更，提供迁移期（保留旧别名/双端点）。
  - 新增 GET 下载不能破坏既有 POST 表单导出（参考 `/export_tasks`）。

- 文档与注释
  - 注释仅保留关键维护信息（边界/性能/安全/非显然逻辑），禁止冗余；外部文档更新 README/docs，并与 DeepWiki 保持一致。

- 部署与环境
  - Jenkins/Windows 服务流程稳定：备份→依赖→迁移→健康检查→回滚；新增步骤要幂等，不破坏路径/变量。
  - 配置优先 `config.py`/环境变量；上传/临时目录集中配置。

- 提交前检查
  - 路由与模板/JS 一致性；linter 通过；导出/下载验证文件名（导出**不应**再产生临时文件）；必要处补充审计日志。
  - **必跑门禁**（Python：`F:\Miniconda\envs\wage\python.exe`，仓库根目录执行）：

    | 命令 | 期望结果 |
    | --- | --- |
    | `python -B scripts/check_templates.py` | `87 templates / 44 declared / 40 used in templates / 44 used on routes / landing 5` → `RESULT: OK` |
    | `python -B scripts/check_migration_heads.py` | `HEADS=['p1nonctarget']`，`head_count=1`，`revisions=35` → exit 0 |
    | `python -B scripts/check_properties.py` | `已扫描 25 个文件，模型类 74 个` → `RESULT: OK`（**新增闸门**，专治第 5 次复发的「`@property`/不存在列当列用」）。⚠ 2026-10-09 批次17（B17-16，A-70 重基线）由 23 → **25**：B17-01 删除死文件 `app/main/sales_routes.py` 后 `app/**/*.py` 少一个文件；**模型类 74 不变**；四处同改 = 本行 / `harness/run_gates.py:48` / `harness/ci_gates.py` 第 3 步 needle / `scripts/check_doc_claims.py` 的 PINNED（登记见 `test-reports-2026-10/B17-登记.md` §B17-16） |
    | `python -B scripts/route_inventory.py` | `total rules=273`，`duplicate (method,path) registrations=0`（2026-10-09 批次17 B17-10 口径重基线 271 → **273**，源 = 现场 `route_inventory.py` 读数 + `harness/run_gates.py` `EXPECTED['routes_total_rules']`） |
    | `python -B scripts/check_model_refs.py` | `scanned 23 files` / `name_query_refs`（计数勿钉，已漂移过 574/575/602）/ `violations 0` → `RESULT: OK`（**新增闸门**，专治 P-01 类「模型名未导入」NameError）；判据只钉 `violations 0` + `RESULT: OK` |
    | `python -B test-reports-2026-10/harness/w4_http_contract.py --roots app --scope app --expect 10` | 10 个 P-12 站点（`get_json()` 维，具名登记见脚本 docstring）→ exit 0 |

    模板/权限/迁移/property/模型引用/HTTP 契约六项都要求 exit 0；有违规就必须先修，不要靠改期望值过关。

    **单一入口（推荐）**：以上各项已由 `python -B test-reports-2026-10/harness/ci_gates.py --phase first` 统一编排（当前 **19 步**：blocking 15 / report-only 4；读数 2026-10-09，`ci_gates.py` SHA256 `54D8371B…16C680`，批次17 追加末位 17 `negative_matrix` / 18 `check_is_archived_policy` / 19 `check_doc_claims`），退出码语义 `0=全部 blocking 通过 / 1=有 blocking 失败 / 2=仅 report-only 失败 / 3=入口缺失`。
    > ⚠ 引用 `ci_gates` 的步骤数时必须带**「步骤数 + SHA256 + 时点」**：该文件在本战役期间从 11 步增至 14 步（**阶段A 基线**）、批次17 收口为 **19 步**；「11 步 / 14 步」都只能当**当时时点**的基线引用，不得当现状。
    > ⚠ `route_inventory.py` 与 `harness/measure_coverage.py` 属**报告型**（stdout 全是度量值，无判据语义）⇒ **其退出码不进闸门链**，判据改由 `harness/coverage_drift.py` 消费其 JSON 产出。
    > ⚠ `harness/run_gates.py` 内的 `route_inventory_native_probe` 属**环境依赖探针**：其退出码随沙箱环境态变化，**不得写入任何 blocking 判据**。
    > `check_properties.py` 的跳过表有**两类**：① `SKIP_FILENAMES` 里的 4 个名字（`routes_backup.py` / `routes_original.py` / `routes_full.py` / `routes_with_duplicates.py`）——这 4 个**遗留备份文件已于 2026-09-18 第 8 批从仓库删除**（约 1.99 MB，全仓引用 0 处），**名字保留作防御**（这类超大副本可能带语法错误，若被误恢复，跳过比让脚本崩在 `ast.parse` 更好）；② `SKIP_SUFFIXES`（`.bak` / `.new` / `.backup`），跳过 `app/main/routes.py.backup`、`routes.py.bak`、`routes.py.new` 这 3 个后缀型残留（**其实被 git 跟踪**，原记录有误；已于第 8 批一并删除）。**结论：`app/main` 下现只有 `routes.py` 一个路由模块；不要再按「包内有语法错误的备份文件」的说法去处理。**
  - **会发请求的脚本**：`smoke_test.py`、`permission_matrix.py`、`functional_test.py`。
    **⚠ 原「它们会重写根目录 `_permission_matrix.json` / `_smoke_results.json`」的说法已作废（E-03 / t4 交付，2026-10-07）**：`permission_matrix.py` 与 `smoke_test.py` 的落盘已默认改到 **`test-reports-2026-10/.tmp/<RUN_ID>/`**（绝对路径、与 cwd 无关），并新增 `--out` / `--no-dump`；**写盘失败只打 `[WARN] 落盘失败（不影响退出码）`** ⇒ **退出码与写盘已解耦**（「断言全绿却 exit 1」的旧病已消除）。CI 与复跑请一律带 `--no-dump`。沙箱内需加垫片：`python -B scripts/_sandbox_compat.py scripts/smoke_test.py`。
    **`permission_matrix.py` 现在同时执法两类判据**：① **匿名可访问面**（`anon_open` 非空 ⇒ exit 1）；② **C-06 四模块权限面**（`--out-modules` / `--inject-module`；10 个入口**逐入口** allow+deny，角色集取自 `app.permissions.roles_for`）⇒ 其失败**计入退出码**，故 `ci_gates` 的 `permission_matrix`(**blocking**) 步**永久执法 C-06**。⚠ 该工具按设计**只扫 GET**，故 C-06 覆盖四模块**页面面**；**四模块写端点的 deny 断言仍是余项**（补打时须在同一工具内加方法参数化 face，**不得新起并行工具**）。
    ✅ **原「它们会删掉 `uploads/temp/` 下 6 个受跟踪的 Excel 模板」的警告已作废（2026-09-18 第 7 批，已修复）**：根因是 `cleanup_temp_files()` 作为 `@bp.before_request` 钩子（`app/main/routes.py:2196-2200`）在**每个请求**删除 `TEMP_FOLDER`（= `uploads/temp`，见 `app/__init__.py:161-163`）中 **mtime 超过 5 分钟**的文件，而该目录当时同时存放着 6 个**受跟踪**的模板文件——导出改内存生成（第 6 批）之后已没有任何代码重建它们。
    第 7 批的修法：确认**全仓无任何代码读取** `uploads/temp/*.xlsx` 后，把这些 `*_template.xlsx` 当**旧导出实现的遗留产物**处理——取消跟踪并删除（`git ls-files uploads` 现为 **0**），`.gitignore` 增加 `/uploads/temp/`。
    现状：`uploads/temp` 是**纯运行时临时目录**（只有导入端点把上传文件写进去，由 `finally` / 钩子清理），启动时由 `os.makedirs(..., exist_ok=True)`（`app/__init__.py:158/162`）自动重建；**「每个请求清理 mtime>5 分钟的文件」是预期行为，不再是缺陷**。
    ⛔ **不再需要**「跑会发请求的脚本前备份、跑完 `git checkout -- uploads/temp/` 恢复」这套规避步骤——现在没有可恢复的对象，该命令会因路径不存在而报错。
    只做静态检查时优先跑不发请求的 5 个脚本（`check_templates` / `check_migration_heads` / `check_properties` / `route_inventory` / `check_db_bootstrap`）。
  - 一切验证都用 **`app.db` 副本**（`DATABASE_URL` 指向副本，或直接用 `scripts/_test_bootstrap.make_app()`）。跑完复核真实 `app.db` 的 SHA256 未变。
    ⚠ **`harness/coverage_drift.py` 必须显式传 `--coverage <本次 run 产物>`**：**缺参 = `exit 2`（用法错误），不是回归**（V-16/N-1，2026-10-07）。原因：默认路径指向的是一份**历史冻结锚点**，其读数（`6/14/101`）与 `LOCKED` 全局阈值（`108/116/0`，V-06 后）**语义互斥**；若静默用锚点当输入，直跑必得 `exit 1`，极易被误读成「回归」。退出码语义：`0` = 判据 8/8 通过；`1` = 判据失败（真敏感）；`2` = **未提供产物**；`9/9 --selftest` ⇒ `0`。已同步 `40-第2轮实测Runbook与台账规范.md` §4.5。
    ⚠ **通用纪律（挂点与产物分离）**：凡「**既是冻结基线、又是会被脚本原地写出的活产物**」的文件（如 `evidence/uat/uat_chains.json`、`evidence/api/write_suite.json`），**判据必须从不可变归档快照读取，不得从 live 路径读取**。同族病史：A-89（preflight 归档进 `evidence/` 而 `evidence_hash` 索引 `evidence/` ⇒ 每跑一次就多一批未登记违规）、`write_suite.py` 无 `--out`（复跑与保锚点不可兼得）、N-1（锚点与 `LOCKED` 互斥）、F1（`uat_chains.json` 被下游覆盖 ⇒ `w2w3_uatdiff` 的 `UD-0/1a/1b/3/4` 改前改后都红）。

  - 回滚：重要数据写操作产生日志与回滚信息，遵循 `AuditLog`。

- 禁止事项
  - 禁止 JSON API 返回 HTML；禁止在路由写样式/前端常量；禁止跨模块直接操作他处数据层（走模型/服务层）。

---

Recipes (copy-paste ready):

1) 新增 JSON API（含权限/回滚/统一返回）

```python
from flask import request, jsonify, current_app
from flask_login import login_required, current_user
from app import db, csrf
from . import bp

@bp.route('/api/example/resource', methods=['POST'])
@login_required
@csrf.exempt  # 仅在需要时豁免（纯 JSON）
def create_example_resource():
    if current_user.role not in ['admin', 'manager']:
        return jsonify({'success': False, 'message': '权限不足'}), 403
    try:
        data = request.get_json() or {}
        # TODO: 参数校验 & 业务逻辑
        # db.session.add(...)
        db.session.commit()
        return jsonify({'success': True, 'message': '创建成功', 'data': {'id': 123}})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'创建失败: {str(e)}')
        return jsonify({'success': False, 'message': f'创建失败：{str(e)}'}), 500
```

2) 导出 / 模板下载（GET/POST 双支持 + **内存生成，不落盘**）

```python
from io import BytesIO

from flask import request, send_file, redirect, url_for, flash, current_app
from flask_login import current_user
from app import db
from app.permissions import require_capability
from app.utils.excel_generator import ExcelGenerator

@bp.route('/export_example', methods=['GET', 'POST'])
@login_required
@require_capability('your.capability')   # 能力已在 app/permissions.py 登记
def export_example():
    try:
        p = request.args if request.method == 'GET' else request.form
        query = db.session.query(YourModel)
        if p.get('search'):
            like = f"%{p.get('search')}%"
            query = query.filter(YourModel.name.like(like))
        rows = query.all()

        excel = ExcelGenerator()
        wb = excel.generate_your_excel(rows)  # 请在 utils 中实现

        # 内存生成：不写临时文件，也就没有 Windows 上 WinError 32 的清理问题
        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)

        return send_file(
            buf,
            as_attachment=True,
            download_name='导出示例.xlsx',
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        current_app.logger.error(f'导出失败: {str(e)}')
        flash('导出失败，请重试', 'danger')
        return redirect(url_for('main.index'))
```

> 反例（**不要照抄**）：`tempfile.mkdtemp()` / `mkstemp()` 写盘 + `wb.save(temp_file)` +
> `@after_this_request` 清理。`send_file` 返回后文件在 Windows 上仍被占用，`os.remove()`
> 必然抛 `WinError 32` 并被 `except` 静默吞掉，临时文件永久残留；仓库已把 13 处导出
> 全部改成上面的内存形态。

3) 分页/筛选（与全局参数约定一致）

```python
from flask import request, render_template, flash
from app import db
from . import bp
from functools import wraps
from flask_login import login_required

def handle_pagination_args(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        try:
            page = request.args.get('page', 1, type=int)
            per_page = int(request.args.get('per_page', '20'))
            if page < 1: page = 1
            if per_page not in [20, 50, 100]: per_page = 20
            request.validated_page = page
            request.validated_per_page = per_page
        except (ValueError, TypeError):
            flash('分页参数无效，已使用默认值', 'warning')
            request.validated_page = 1
            request.validated_per_page = 20
        return f(*args, **kwargs)
    return decorated

@bp.route('/example_list', methods=['GET'])
@login_required
@handle_pagination_args
def example_list():
    query = db.session.query(YourModel)

    if request.args.get('search'):
        like = f"%{request.args.get('search')}%"
        query = query.filter(YourModel.name.like(like))

    status = request.args.get('status', 'pending')
    if status:
        query = query.filter(YourModel.status == status)

    if request.args.get('start_date'):
        try:
            from datetime import datetime
            start_date = datetime.strptime(request.args.get('start_date'), '%Y-%m-%d')
            query = query.filter(YourModel.date >= start_date)
        except (ValueError, TypeError):
            pass
    if request.args.get('end_date'):
        try:
            from datetime import datetime
            end_date = datetime.strptime(request.args.get('end_date'), '%Y-%m-%d')
            query = query.filter(YourModel.date <= end_date)
        except (ValueError, TypeError):
            pass

    sort_column = request.args.get('sort', 'created_at')
    sort_direction = request.args.get('direction', 'desc')
    mapping = {
        'created_at': YourModel.created_at,
        'name': YourModel.name,
        'status': YourModel.status,
    }
    if sort_column in mapping:
        col = mapping[sort_column]
        if sort_direction == 'desc':
            col = col.desc()
        query = query.order_by(col)
    else:
        query = query.order_by(YourModel.created_at.desc())

    pagination = query.paginate(page=request.validated_page, per_page=request.validated_per_page)
    items = pagination.items
    return render_template('main/example_list.html', items=items, pagination=pagination,
                           current_sort=sort_column, current_direction=sort_direction)
```

4) Select2 异步接口（与现有库存接口一致）

```python
from flask import request, jsonify
from flask_login import login_required

@bp.route('/api/example/select2')
@login_required
def example_select2():
    try:
        only_available = request.args.get('only_available', 'false').lower() == 'true'
        search = request.args.get('search', '').strip()
        query = db.session.query(YourModel)
        if only_available:
            query = query.filter(YourModel.quantity > 0)
        if search:
            like = f"%{search}%"
            query = query.filter(YourModel.name.like(like))
        rows = query.limit(50).all()
        data = [{
            'id': r.id,
            'name': r.name,
            'specification': r.spec,
            'quantity': r.quantity,
        } for r in rows]
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'message': f'加载失败: {str(e)}'}), 500
```

5) Excel 导入（需真实路径时才落盘 + 行级容错）

```python
@bp.route('/import_example', methods=['POST'])
@login_required
@require_capability('your.capability')
def import_example():
    """从 xlsx 导入。行级容错：坏行只记「第 N 行：…」并跳过，不整体 500。"""
    file = request.files.get('file')
    if file is None or not file.filename:
        flash('请选择要导入的 Excel 文件', 'warning')
        return redirect(url_for('main.example_list'))

    # 解析器要真实路径才落盘；能走内存流的（如 pd.read_excel(file)）不要落盘
    temp_path = os.path.join(current_app.config['TEMP_FOLDER'], secure_filename(file.filename))
    file.save(temp_path)
    try:
        rows = ExcelGenerator.parse_example_data(temp_path)  # 或 pd.read_excel(temp_path)
        errors = []
        for idx, row in enumerate(rows, start=2):   # 第 1 行是表头
            try:
                # TODO: 逐行校验 & db.session.add(...)
                pass
            except Exception as e:
                errors.append(f'第 {idx} 行：{e}')
        db.session.commit()
    finally:
        cleanup_temp_files()          # app/main/routes.py:2334
    if errors:
        flash('部分行未导入：' + '；'.join(errors[:5]), 'warning')
    else:
        flash('导入成功', 'success')
    return redirect(url_for('main.example_list'))
```

> 也可以用辅助函数 `save_temp_file(file)`（`app/main/routes.py:5600`，内部 `tempfile.mkdtemp(dir=TEMP_FOLDER)`）——
> 目录开在 `TEMP_FOLDER` 下，由 `cleanup_temp_files()` 按过期时间整个回收；调用方能自己 `finally` 删掉更好。

---

Execution Notes (减少幻觉):
- DeepWiki 查询与交叉验证协议见 `.cursor/rules/deepwiki-workflow.mdc`；新增端点/字段前按该协议执行，并在仓库内检索同义实现与命名，尽量对齐复用。
- 任何“猜测”字段/结构，一律回看模型/模板/既有 API，避免凭空增删改名。
- 始终使用 `url_for('main.xxx')`；发现硬编码 URL 先整改再扩展。

Reference:
- Cursor Rules 文档：`https://cursor.com/cn/docs/context/rules#project-rules`
