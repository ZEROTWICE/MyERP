Rule Name: project-rules

Description:
面向 ZEROTWICE/MyERP（Flask + SQLAlchemy + Jinja2）的项目级约束与可复用片段，统一接口/风格/安全/分页/导出等，实现与现有代码与 DeepWiki 描述一致，降低幻觉。参考规范：`https://cursor.com/cn/docs/context/rules#project-rules`。

---

Scope:
- Applies to this repository（后端 Python、Jinja2 模板、前端 JS 交互、部署脚本相关改动）

---

Guidelines:
- 架构与分层
  - 蓝图路由：`app/main/routes.py`（任务/生产/库存/销售/产品等）与 `app/main/quality.py`（质量）。模板/静态：`app/templates`, `app/static`。ORM：`app/models.py`。
  - 全局流水号：统一使用 `SerialNumber.get_next_number()`（Employee/Task/ProductionRecord/Inspection 等）。
  - 权限：`Flask-Login` + `current_user.role`（admin/hr/manager/inspector/user）。模板菜单与后端路由均需校验。

- 路由/端点规范
  - 必须通过 `url_for('main.xxx')` 生成链接；端点名与函数名保持一致；页面路由返回模板，JSON API 使用 `/api/...` 前缀。
  - 导出/下载：`send_file` + `download_name`（可含中文）。用 `@after_this_request` 清理临时文件。
  - 任务模块端点保持既有：
    - GET/POST `/tasks`；GET `/tasks/<id>`；DELETE `/tasks/<id>`；POST `/tasks/<id>/edit`；POST `/tasks/<id>/update_status`
    - GET `/tasks/template`；POST `/tasks/import`；GET/POST `/export_tasks`（双支持，勿破坏）。
  - 库存 API 返回：`{'success': True, 'data': [...]}`；字段含 `id, name/specification/quantity` 等（Select2 兼容）。
  - 质量 API 固定前缀 `/api/quality/...`；必要 JSON POST 使用 `@csrf.exempt`，其余走 CSRF 头（见 base.html 中 jQuery `$.ajaxSetup`）。

- 数据/事务/日志/审计
  - 使用 SQLAlchemy；复杂查询用 `db.func/join/subquery`；失败必须 `db.session.rollback()` 并 `current_app.logger.error(...)`。
  - 重要写操作记录 `AuditLog`（含 `can_rollback/rollback_type`），遵循现有模式。

- Excel 导入/导出
  - 逻辑封装在 `app/utils/excel_generator.py`；路由只负责查询与文件清理；临时文件放 `current_app.config['TEMP_FOLDER']`，处理完成删除。

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

- 提交前检查
  - 路由与模板/JS 一致性；linter 通过；导出/下载验证文件名与临时文件清理；必要处补充审计日志。

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

2) 导出（GET/POST 双支持 + 清理临时文件）

```python
from flask import request, send_file, after_this_request, redirect, url_for, flash, current_app
from app import db
from app.utils.excel_generator import ExcelGenerator
import os, tempfile

@bp.route('/export_example', methods=['GET', 'POST'])
@login_required
def export_example():
    if current_user.role not in ['admin', 'hr']:
        flash('权限不足', 'danger')
        return redirect(url_for('main.index'))
    try:
        p = request.args if request.method == 'GET' else request.form
        query = db.session.query(YourModel)
        if p.get('search'):
            like = f"%{p.get('search')}%"
            query = query.filter(YourModel.name.like(like))
        rows = query.all()

        excel = ExcelGenerator()
        wb = excel.generate_your_excel(rows)  # 请在 utils 中实现

        temp_dir = tempfile.mkdtemp()
        temp_file = os.path.join(temp_dir, '导出示例.xlsx')
        wb.save(temp_file)

        @after_this_request
        def cleanup(response):
            try:
                os.remove(temp_file)
                os.rmdir(temp_dir)
            except Exception as e:
                current_app.logger.error(f'删除临时文件失败: {str(e)}')
            return response

        return send_file(
            temp_file,
            as_attachment=True,
            download_name='导出示例.xlsx',
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        current_app.logger.error(f'导出失败: {str(e)}')
        flash('导出失败，请重试', 'danger')
        return redirect(url_for('main.index'))
```

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

---

Execution Notes (减少幻觉):
- 新增端点/字段前先在仓库与 DeepWiki 检索同义实现与命名，尽量对齐复用。
- 任何“猜测”字段/结构，一律回看模型/模板/既有 API，避免凭空增删改名。
- 始终使用 `url_for('main.xxx')`；发现硬编码 URL 先整改再扩展。

Reference:
- Cursor Rules 文档：`https://cursor.com/cn/docs/context/rules#project-rules`

### ZEROTWICE/MyERP 项目 Cursor 规则约束

用于约束后续全 AI 开发，统一风格、接口与约定，最大程度降低幻觉与偏离。新增/修改功能前，先全文检索并对齐既有实现与命名。

- 基本定位
  - 架构：Flask + SQLAlchemy + Jinja2；蓝图路由（`app/main/routes.py`, `app/main/quality.py`）+ 模型（`app/models.py`）+ 模板/静态（`app/templates`, `app/static`）。
  - 数据：SQLite 默认；全局流水号使用 `SerialNumber.get_next_number()`（Employee/Task/ProductionRecord/Inspection 等）。
  - 权限：`Flask-Login` + `current_user.role`（admin/hr/manager/inspector/user）。

- 路由与端点
  - 蓝图统一：`url_for('main.xxx')` 与函数名一致；页面路由返回模板，JSON API 使用 `/api/...` 前缀。
  - 导出/下载：返回 `send_file`，中文 `download_name`；用 `@after_this_request` 清理临时文件。
  - 任务端点（保持一致）：`/tasks`（GET/POST）、`/tasks/<id>`（GET/DELETE）、`/tasks/<id>/edit`（POST）、`/tasks/<id>/update_status`（POST）、`/tasks/template`（GET）、`/tasks/import`（POST）、`/export_tasks`（GET/POST）。
  - 库存 API：固定 `{'success': True, 'data': [...]}`，字段包含 `id, name/specification/quantity` 等；兼容 Select2。
  - 质量模块 API：前缀 `/api/quality/...`；JSON POST 端点需要时 `@csrf.exempt`，保持与现有端点一致。

- 鉴权与安全
  - 模板菜单与权限由 `current_user.role` 控制；后端路由重复校验权限。
  - CSRF：全局 meta 注入 + jQuery `$.ajaxSetup`；仅对必要 JSON API 豁免 CSRF，禁止大面积豁免。

- 数据访问与事务
  - 使用 SQLAlchemy；复杂查询用 `db.func/join/subquery`；提交失败必须 `db.session.rollback()` 并 `current_app.logger.error(...)`。
  - 审计：重要新增/修改/删除记录 `AuditLog`，含 `can_rollback/rollback_type`，遵循既有模式。

- Excel 导入/导出
  - 统一封装在 `app/utils/excel_generator.py`；路由侧仅做查询/落库/文件清理。
  - 临时文件：`current_app.config['TEMP_FOLDER']`，处理完成删除。

- 前端模板与交互
  - 基于 `base.html`（Bootstrap5/jQuery/Select2/SweetAlert2/Toastr）；移动端优化 `mobile-optimization.js` 与 `mobile-components.css`。
  - 列表页参数：`page/per_page/search/status/direction/sort/start_date/end_date`；分页参数由 `handle_pagination_args` 校验注入。
  - Select2 异步：API 返回结构与字段保持现有实现；前端格式化映射统一在模板 JS。

- 命名与风格（Python）
  - 函数名用动词短语；变量使用完整英文单词；优先早返回，避免深嵌套。
  - 日志与错误：所有失败点必须有日志；用户提示与日志分离（`flash`/JSON vs logger）。
  - 禁止随意吞错或凭空新增/改名字段；字段名与模板/JS严格对应。

- 模块边界
  - 质量相关在 `app/main/quality.py`；任务/生产/库存/销售/产品等在 `app/main/routes.py`，同类功能就近归类并分段注释。
  - 复杂搜索/筛选抽到 `app/services/search_service.py`。

- 兼容性与约束
  - 变更端点/字段前先全局搜索模板/JS引用；若改动，提供兼容期（保留旧字段别名或双路径）。
  - 新增 GET 下载不破坏现有 POST 行为（如 `/export_tasks`）。

- 文档与注释
  - 注释仅保留关键维护信息（边界/性能/安全/非显然逻辑），禁止冗余；外部文档更新 README/docs，并与 DeepWiki 保持一致。

- 部署与环境
  - Jenkins/Windows 服务流程稳定：备份→依赖→迁移→健康检查→回滚；新增步骤要幂等，不破坏路径/变量。
  - 配置优先 `config.py`/环境变量；上传/临时目录集中配置。

- 变更流程
  - 提交前：本地 linter、核对路由与模板/JS一致性；涉及导出/下载务必实测文件名与清理。
  - 回滚：重要数据写操作产生日志与回滚信息，遵循 `AuditLog`。

- 禁止事项
  - 禁止在 JSON API 返回 HTML；禁止在路由里写样式常量；禁止跨模块直接操作他处数据层（请走模型/服务层）。

---

### 可复用代码片段模板

以下片段可直接粘贴并按需替换变量名与字段，确保与既有约定一致。

#### 1) 新增 API（JSON 成功/失败统一，含鉴权与回滚）

```python
from flask import request, jsonify, current_app
from flask_login import login_required, current_user
from app import db, csrf
from . import bp

@bp.route('/api/example/resource', methods=['POST'])
@login_required
@csrf.exempt  # 仅当为 JSON API 且需要时才豁免
def create_example_resource():
    if current_user.role not in ['admin', 'manager']:
        return jsonify({'success': False, 'message': '权限不足'}), 403
    try:
        data = request.get_json() or {}
        # TODO: 参数校验与业务逻辑 ...
        # db.session.add(...)
        db.session.commit()
        return jsonify({'success': True, 'message': '创建成功', 'data': {'id': 123}})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'创建失败: {str(e)}')
        return jsonify({'success': False, 'message': f'创建失败：{str(e)}'}), 500
```

#### 2) 导出 GET/POST 双支持（含清理临时文件）

```python
from flask import request, send_file, after_this_request, redirect, url_for, flash
from app import db
from app.utils.excel_generator import ExcelGenerator
import os, tempfile

@bp.route('/export_example', methods=['GET', 'POST'])
@login_required
def export_example():
    if current_user.role not in ['admin', 'hr']:
        flash('权限不足', 'danger')
        return redirect(url_for('main.index'))
    try:
        # GET：读查询参数；POST：读表单字段
        p = request.args if request.method == 'GET' else request.form

        # 组装查询（参考 tasks 列表对齐 search/status/date/sort 参数）
        query = db.session.query(YourModel)
        if p.get('search'):
            like = f"%{p.get('search')}%"
            query = query.filter(YourModel.name.like(like))
        # 可选：状态、日期范围等 ...

        rows = query.all()

        # 生成 Excel
        excel = ExcelGenerator()
        wb = excel.generate_your_excel(rows)  # 自行实现，或参考现有生成函数

        temp_dir = tempfile.mkdtemp()
        temp_file = os.path.join(temp_dir, '导出示例.xlsx')
        wb.save(temp_file)

        @after_this_request
        def cleanup(response):
            try:
                os.remove(temp_file)
                os.rmdir(temp_dir)
            except Exception as e:
                current_app.logger.error(f'删除临时文件失败: {str(e)}')
            return response

        return send_file(
            temp_file,
            as_attachment=True,
            download_name='导出示例.xlsx',
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        current_app.logger.error(f'导出失败: {str(e)}')
        flash('导出失败，请重试', 'danger')
        return redirect(url_for('main.index'))
```

#### 3) 分页/筛选列表样例（与全局参数约定保持一致）

```python
from flask import request, render_template, flash
from app import db
from . import bp
from functools import wraps

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
    # 基础查询
    query = db.session.query(YourModel)

    # 搜索
    if request.args.get('search'):
        like = f"%{request.args.get('search')}%"
        query = query.filter(YourModel.name.like(like))

    # 状态筛选（默认展示某状态，如 pending）
    status = request.args.get('status', 'pending')
    if status:
        query = query.filter(YourModel.status == status)

    # 日期范围
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

    # 排序
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

    # 分页
    pagination = query.paginate(page=request.validated_page, per_page=request.validated_per_page)
    items = pagination.items

    return render_template('main/example_list.html', items=items, pagination=pagination,
                           current_sort=sort_column, current_direction=sort_direction)
```

#### 4) Select2 异步接口响应（与现有库存接口一致）

```python
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

---

### 执行要点（减少幻觉）

- 新增端点/字段前先在仓库与 DeepWiki 搜索是否已有同义实现与命名，尽量复用与对齐。
- 凡“猜测”字段/结构，一律停下并回看模型、模板与现有 API，避免凭空改名或添加。
- 始终使用 `url_for('main.xxx')` 生成链接；发现硬编码 URL 先整改再扩展。


