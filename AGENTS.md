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
  - **仅上传解析必须落盘**：`ExcelGenerator.parse_*` / `pd.read_excel` 需要真实路径，因此导入端点才写 `current_app.config['TEMP_FOLDER']`（`file.save(temp_path)`），由 `cleanup_temp_files()` + `finally` 清理；辅助函数 `save_temp_file()`（`app/main/routes.py:5067`）用 `tempfile.mkdtemp()`。当前 `routes.py` 有 8 个导入端点属于这种形态。
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
    | `python -B scripts/check_properties.py` | `已扫描 23 个文件，模型类 74 个` → `RESULT: OK`（**新增闸门**，专治第 5 次复发的「`@property`/不存在列当列用」） |
    | `python -B scripts/route_inventory.py` | `total rules=271`，`duplicate (method,path) registrations=0` |

    模板/权限/迁移/property 四项都要求 exit 0；有违规就必须先修，不要靠改期望值过关。
    > `check_properties.py` 的跳过表有**两类**：① `SKIP_FILENAMES` 里的 4 个名字（`routes_backup.py` / `routes_original.py` / `routes_full.py` / `routes_with_duplicates.py`）——这 4 个**遗留备份文件已于 2026-09-18 第 8 批从仓库删除**（约 1.99 MB，全仓引用 0 处），**名字保留作防御**（这类超大副本可能带语法错误，若被误恢复，跳过比让脚本崩在 `ast.parse` 更好）；② `SKIP_SUFFIXES`（`.bak` / `.new` / `.backup`），跳过 `app/main/routes.py.backup`、`routes.py.bak`、`routes.py.new` 这 3 个后缀型残留（**其实被 git 跟踪**，原记录有误；已于第 8 批一并删除）。**结论：`app/main` 下现只有 `routes.py` 一个路由模块；不要再按「包内有语法错误的备份文件」的说法去处理。**
  - **会发请求的脚本**：`smoke_test.py`、`permission_matrix.py`、`functional_test.py`。
    它们会重写根目录 `_permission_matrix.json` / `_smoke_results.json`（已 gitignore，不影响 `git status`）。沙箱内需加垫片：`python -B scripts/_sandbox_compat.py scripts/smoke_test.py`。
    ✅ **原「它们会删掉 `uploads/temp/` 下 6 个受跟踪的 Excel 模板」的警告已作废（2026-09-18 第 7 批，已修复）**：根因是 `cleanup_temp_files()` 作为 `@bp.before_request` 钩子（`app/main/routes.py:2196-2200`）在**每个请求**删除 `TEMP_FOLDER`（= `uploads/temp`，见 `app/__init__.py:161-163`）中 **mtime 超过 5 分钟**的文件，而该目录当时同时存放着 6 个**受跟踪**的模板文件——导出改内存生成（第 6 批）之后已没有任何代码重建它们。
    第 7 批的修法：确认**全仓无任何代码读取** `uploads/temp/*.xlsx` 后，把这些 `*_template.xlsx` 当**旧导出实现的遗留产物**处理——取消跟踪并删除（`git ls-files uploads` 现为 **0**），`.gitignore` 增加 `/uploads/temp/`。
    现状：`uploads/temp` 是**纯运行时临时目录**（只有导入端点把上传文件写进去，由 `finally` / 钩子清理），启动时由 `os.makedirs(..., exist_ok=True)`（`app/__init__.py:158/162`）自动重建；**「每个请求清理 mtime>5 分钟的文件」是预期行为，不再是缺陷**。
    ⛔ **不再需要**「跑会发请求的脚本前备份、跑完 `git checkout -- uploads/temp/` 恢复」这套规避步骤——现在没有可恢复的对象，该命令会因路径不存在而报错。
    只做静态检查时优先跑不发请求的 5 个脚本（`check_templates` / `check_migration_heads` / `check_properties` / `route_inventory` / `check_db_bootstrap`）。
  - 一切验证都用 **`app.db` 副本**（`DATABASE_URL` 指向副本，或直接用 `scripts/_test_bootstrap.make_app()`）。跑完复核真实 `app.db` 的 SHA256 未变。
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

5) Excel 导入（**必须落盘** + 行级容错）

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

    # 解析器要真实路径，这里是唯一允许落盘的场景
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
        cleanup_temp_files()          # app/main/routes.py:2173
    if errors:
        flash('部分行未导入：' + '；'.join(errors[:5]), 'warning')
    else:
        flash('导入成功', 'success')
    return redirect(url_for('main.example_list'))
```

> 也可以用辅助函数 `save_temp_file(file)`（`app/main/routes.py:5067`，内部 `tempfile.mkdtemp()`），
> 但**必须**在 `finally` 里清掉，否则空目录会在系统 TEMP 下无限堆积。

---

Execution Notes (减少幻觉):
- DeepWiki 查询与交叉验证协议见 `.cursor/rules/deepwiki-workflow.mdc`；新增端点/字段前按该协议执行，并在仓库内检索同义实现与命名，尽量对齐复用。
- 任何“猜测”字段/结构，一律回看模型/模板/既有 API，避免凭空增删改名。
- 始终使用 `url_for('main.xxx')`；发现硬编码 URL 先整改再扩展。

Reference:
- Cursor Rules 文档：`https://cursor.com/cn/docs/context/rules#project-rules`
