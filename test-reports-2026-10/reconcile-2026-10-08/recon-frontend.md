# 模板与前端对账（t4 / W3）— 模板资产 · 权限渲染 · 批次6 UI 需求 · P7 下拉选项

| 项目 | 值 |
| --- | --- |
| 任务 | `t4`（kind=work，attempt 6，attempt_id `e6c40414-3924-4a27-96d1-237642b08524`） |
| 执行者 | 前端开发者（成员 `前端开发者2`，队 `myerp-reconcile-plan`） |
| 产出时间 | 2026-10-08（本机） |
| 工作目录 | `D:\workspace\wage_management_system - bak` |
| 解释器 | `F:\Miniconda\envs\wage\python.exe` = Python 3.9.21（绝对路径） |
| 唯一事实来源 | 当前工作区**源码与静态资产**（`app/templates/**`、`app/static/**`、`app/main/*.py`、`app/permissions.py`） |
| 权威需求文档 | `docs/开发与测试规划-2026-10-06.md`（批次6 AC4.1–AC4.4/AC3.2/AC7.1、批次4 B4-04、批次9 B9-02/B9-15）· `docs/test-reports/2026-10/04-业务验收标准与端到端判据.md`（AC-20/21/22/23/24/40…）· `AGENTS.md` 前端交互约定 · `test-reports-2026-10/70-第2轮收口与阶段C移交.md` §4-P7 |
| 上游交叉证据 | `test-reports-2026-10/reconcile-2026-10-08/00-共享事实底盘.md`（W0）· `recon-backend.md`（W2，本报告对其 P7/B6-*/B4-04 结论**做了独立复核**并补充前端侧证据） |
| 产出纪律 | 本报告为**新建文件**。仓库内 `app/`、`app/templates/`、`app/static/`、`scripts/`、`docs/` **全部只读**，未修改任何既有文件。 |
| 真实库不变量 | `app.db` = `2531328 B` / `F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065` / mtime `2026-09-18 12:50:55` —— **开工与收尾两次复核逐位一致**；本任务**未连接数据库**，不可能写入。 |
| git HEAD | `534ce70b204c767feee551e8fd04e538374b1de8` |

> **证据规则（沿用 W0 §5）**：①「文件/资源存在」≠「已实现」；② 每条判定必须给 `file:line` 或「命令 + 读数」；③ 不引用转述；④ 文档与源码冲突以源码为准；⑤ **文档行号一律不得复制，本报告所有行号均为本次实测**；⑥ 状态词只用 `已实现 / 部分实现 / 未实现 / 文档漂移 / 无法核实`。
>
> **本任务的静态边界（重要）**：沙箱内**无浏览器**。凡「真实 DOM 渲染结果 / Select2 下拉实际弹出内容 / SweetAlert 是否阻塞 / CSRF 头部在浏览器中的最终形态」等**只能在浏览器里确认**的结论，本报告一律显式标注 **`无法核实（需浏览器）`**，**不写成通过**。

---

## 0. 一页结论

| # | 结论 | 依据（本次实测） |
| --- | --- | --- |
| **K-1 模板规模** | 模板 **87** 个（`.html` 87 个，且 `app/templates` 下**非 html 文件 0 个** ⇒ 文件总数同为 87）；4 个一级目录（`auth/ main/ production/ quality/`… 见 §1.1）。与 captain 实测 `parsed 87 files` **一致** | §1.1 |
| **K-2 权限渲染** | 模板内 `can('cap')` 调用点 **101 处 / 32 个模板**；另有 `can_any(...)` **7 处**（6 处导航 + 1 处注释）。**模板侧出现的能力 = 40 个**，与门禁 `check_templates` 的 `44 declared / 40 used in templates` **互证一致**（独立算法，非转述） | §1.2 |
| **K-3 内联 `current_user.role`** | **仍为 2 处，且行号与文档完全一致**：`quality/tasks.html:340`、`quality/task_detail.html:13`。**未改成 `can()`** ⇒ D4/B9-02 的「模板 2 处」口径**成立**，`tasks.html:337 → :340` 的行号订正**也成立** | §1.3 |
| **K-4 批次6 UI（AC4.1–AC4.4/AC3.2/AC7.1）** | **6 条判据全部不满足**：`nonconformities.html` **仍是 33 行最小页**（`type`/`status` 直接渲染英文枚举、目标列只认工件、三按钮对任何未闭环单都可见、无筛选控件）；`quality/records.html` 的处置信息块**仍恒隐藏**（接口 `record_data` 无 `nonconformity` 键） | §2 |
| **K-5 P7（本报告最重要的一条）** | 不只是「下拉缺 `goods_receipt`」，而是**三角死锁**：`pick_template()` 对 `goods_receipt` **兜底绑了 `production_record` 模板**（`mes_service.py:93-94`）⇒ 检验员提交时 `quality.py:838` 的严格相等校验**必然 400**。界面侧 `goods_receipt` **在 3 处枚举里全部缺席**（模板类型下拉、任务类型下拉、类型筛选），且 3 个 JS 显示名映射表也不含它 ⇒ **来料检在 UI 上无法被完成** | §3 |
| **K-6 前端资产** | `base.html` 的 Bootstrap5（`bootstrap.load_css/js`）/jQuery 3.6.0/Select2/SweetAlert2/Toastr/**jsQR** 全部经 `url_for` 引入；`$.ajaxSetup` 统一注入 `X-CSRFToken`（仅覆盖 jQuery 面）；`mobile-optimization.js` 与 `mobile-components.css` **均被 `base.html` 引用**。**无外链 CDN** | §4.1–§4.2 |
| **K-7 Select2 契约** | 库存三接口（原材料/成品/易耗品）返回结构**一致且合规**：`{'success': True, 'data': [{id,name,specification,quantity,…}]}`。**但发现 1 个新增的前后端契约缺口**：`get_available_raw_materials` **不读 `search`**（`routes.py:6030-6058` 只读 `only_available`），而 `tasks.html:416`/`my_tasks.html:181`/`production_batch_detail.html:356` **都发 `search: params.term`**（注：三处均在 `app/templates/main/` 下；`app/templates/main/quality/tasks.html` **不属此例**，它走客户端 `matcher`） ⇒ **服务端搜索静默失效** | §4.3 |
| **K-8 硬编码 URL** | 模板内**未用 `url_for` 的根相对 URL 共 9 处**（`products.html` 4 处、`quality/inspection.html` 1 处、`quality/task_detail.html` 1 处、`inventory.html` 1 处、`consumable_categories.html` 1 处，另 `products.html:779` 为表单 action） | §5.1 |
| **K-9 CSRF 头缺口（新增发现）** | `base.html:573` 的 `$.ajaxSetup` **只覆盖 jQuery `$.ajax/$ .post/$ .get`（27 处）**；**7 个模板里 15 个原生 `fetch()` 非 GET 站点未带 `X-CSRFToken`**（已逐点复核）。这些请求会命中 `CSRFProtect` ⇒ 400「请求参数有误」，前端统一落到 `.catch` 的通用报错 | §5.2 |
| **K-10 死分支 / 不可达 UI** | ① `records.html:406-430` 处置信息块**恒隐藏**（死分支）；② `records.html:159` 弹窗「打印」**零实参调用** `printRecord()`（定义要求 `id`）⇒ 打印必然失败（全仓唯一命中）；③ `quality/index.html:50` 「质检模板」入口**无 `can()` 守卫** ⇒ **inspector 可见但 403**（违反 REQ-A-04 不变式） | §6 |
| **K-11 与后端报告的一致性** | 本报告独立复核 `recon-backend.md` 的 P7/B6-01…B6-06/B4-04 结论**全部成立**，并补充了它未覆盖的前端侧证据（3 处枚举缺席、3 张 JS 名映射表缺失、`recon-backend` 记的「模板 33 行/`:12/:13/:14/:17-23`」与实测**逐行一致**） | §2/§3 |

---

## 1. 模板规模与权限渲染

### 1.1 规模（口径写明）

| 项 | 实测值 | 复跑命令 |
| --- | --- | --- |
| `.html` 模板数 | **87** | `(Get-ChildItem app\templates -Recurse -File -Filter *.html).Count` |
| `app/templates` 下**全部**文件数 | **87**（⇒ 非 html 文件 **0** 个） | `(Get-ChildItem app\templates -Recurse -File).Count` |
| 一级目录 | `auth` / `main` / `production` / `quality` | `Get-ChildItem app\templates -Directory` |
| 门禁互证 | `[templates] parsed 87 files` / `[permissions] 44 declared / 40 used in templates / 44 used on routes` / `[landing] 5 role landing endpoints` / `RESULT: OK`，**exit 0** | `& $py -B scripts/check_templates.py` |

> ⚠ **口径纪律**：`87` 有两种写法（`.html` 计数 / 全文件计数），本次实测**两者相同**（因为非 html 文件 0 个）；引用时写清口径即可，不存在分歧。

### 1.2 `can()` 使用点数与能力数（独立算法，非转述）

复跑命令（只读、不连库、不写仓库产物；脚本落点见 §8）：

```powershell
$env:PYTHONIOENCODING='utf-8'
& 'F:\Miniconda\envs\wage\python.exe' -B .analysis-scratch/t4_tpl_scan.py
```

| 项 | 实测值 | 说明 |
| --- | --- | --- |
| 出现 `can('cap')` 的模板数 | **32** | `can()` 直接调用 |
| `can('cap')` 调用点总数 | **101** | 正则 `\bcan\(\s*'([A-Za-z_.]+)'` |
| 模板侧**不同能力数** | **40** | 与门禁 `40 used in templates` **互证一致** |
| `can_any(...)` 调用点 | **7 处** | `base.html:268/286/324/387/417/432`（6 处父级菜单显隐）+ `welcome.html:24`（注释） |
| 非能力形态的 `can(` 命中 | **2 处**（均为注释） | `base.html:550`、`welcome.html:24` ⇒ 解释掉「raw grep 110 vs 101」的 9 处差额（110 = 101 + 6×`can_any(` + 2 注释 + 1 个 `can()` 字样） |

**导航权限渲染实测（`base.html`，"入口可见 ⟺ 端点有能力"的实现面）**

| 位置 | 原文片段 | 判定 |
| --- | --- | --- |
| `base.html:268` | `{% if can_any('employee.view', 'bonus.manage', 'salary.view') %}` | 人事菜单父级 |
| `base.html:286` | `{% if can_any('process.view', 'process_assignment.manage', 'production_record.view', 'task.manage', 'production_order.view', 'production_center.use', 'equipment.manage') %}` | 生产菜单父级 |
| `base.html:324` | `{% if can_any('inventory.view', 'inventory.manage') %}` | 库存菜单父级 |
| `base.html:387` | `{% if can_any('customer.manage', 'sales_order.manage', 'shipment.manage') %}` | 销售菜单父级 |
| `base.html:417` | `{% if can_any('quality.view', 'quality.inspect') %}` | 质量菜单父级 |
| `base.html:427` | `<li><a class="dropdown-item" href="{{ url_for('main.manage_nonconformities') }}">不合格处置</a></li>`（外层 `:426 {% if can('quality.view') %}`） | 不合格处置入口 |
| `base.html:550` | `{# 移动端侧边栏的元数据：URL 全部由 url_for 生成，菜单项本身复用 #mainNavMenu（can() 过滤后的服务端渲染结果） #}` | 移动端导航**不重建**菜单，只搬运（与 `mobile-optimization.js:3-7` 注释一致） |

> **结论**：导航侧的 `can()`/`can_any()` 渲染**结构上已成体系**，`REQ-A-04`「入口可见 ⟺ 端点有能力」在**导航面**成立；但在**页面内按钮面**仍有 2 处失配（见 §6.2）。

### 1.3 内联 `current_user.role`（文档记 2 处 → 实测逐位一致）

| # | 实测坐标 | 原文片段（截断） | 与文档比对 | 判定 |
| --- | --- | --- | --- | --- |
| 1 | `app/templates/main/quality/tasks.html:340` | `{% if current_user.role in ['admin', 'manager', 'inspector'] %}` | 文档 `D13` 记「模板 role 在 `tasks.html:337`」→ **订正为 `:340` 成立** | **仍是内联 role，未改成 `can()`** |
| 2 | `app/templates/main/quality/task_detail.html:13` | `{% if task.status == 'pending' and (current_user.role in ['admin', 'manager'] or (current_user.role == 'inspector' and task.inspector_id == current_user.id)) %}` | 文档 `D4`/`B9-02` 记「模板 **2 处**」 | **仍是内联 role**（且该处是「角色 + 对象归属」复合条件，按 `REQ-N-03` **契约豁免**） |

- 扫描命令：`grep -n "current_user.role" app/templates/**/*.html` ⇒ **全仓仅 2 行命中**（本次实测）。
- 与 `AC-06`「内联 role = **15（Python）+ 2（模板）**」**一致**；与 `B9-02` 的订正目标（「31 模板 77 处」→「模板 2 处 + Python 15 处」）**一致**。
- **建议（不作为缺陷报）**：`:340` 处建议改 `{% if can('quality.inspect') %}`，理由是它守护的 `startInspection()` → `POST /api/quality/tasks/<id>/start-inspection` 的能力**恰为 `quality.inspect`**（`quality.py:796-800`），改成 `can()` 后与后端**同源**、且 whitelist 化不再依赖 role 字面量。`:13` 处属契约豁免，可不动。

---

## 2. 批次6 逐条 UI 判定（AC4.1–AC4.4 / AC3.2 / AC7.1）

**对账表**（格式：条目 | 文档要求 | 实测（file:line 原文片段） | 状态 | 剩余工作 | 置信度）

### 2.1 总体：`nonconformities.html` 仍是 33 行最小页

| 项 | 实测 |
| --- | --- |
| 文件行数 | **33 行**（`{% extends %}`…`{% endblock %}` 完整），**与 `recon-backend.md` §3 抬头「仍是 33 行」逐位一致** |
| 结构 | 仅一张 6 列表格（`ID / 类型 / 状态 / 工件 / 结果 / 操作`）+ 一个三按钮表单；**无筛选表单、无分页控件、无 JS 块、无 `can()` 调用** |
| 扫描命令 | `read app/templates/main/stock/nonconformities.html`（全文 33 行） |

### 2.2 B6-01 / AC4.1 —— 类型与状态显示中文

| 条目 | 文档要求 | 实测（file:line 原文片段） | 状态 | 剩余工作 | 置信度 |
| --- | --- | --- | --- | --- | --- |
| **B6-01 / AC4.1** | 列表页 DOM **可见文案**不出现 `open` / `pending_approval` / `rework` / `scrap` / `accept`（可留在 `value`/`data-*`） | `nonconformities.html:7` `<thead><tr><th>ID</th><th>类型</th><th>状态</th><th>工件</th><th>结果</th><th>操作</th></tr></thead>`；`:12 <td>{{ nc.type }}</td>`；`:13 <td>{{ nc.status }}</td>` ⇒ **可见文案直接是英文枚举** | **未实现** | 后端已有可复用的人读口径 `NonconformityRecord.target_label`（`app/models.py:955`，含 `:928` 的 NULL 兼容说明）与 `mes_service.INCOMING_NC_LABELS`；模板 `:12/:13` 改用它（或加 Jinja 过滤器），并让英文只留在 `value`/`hidden` | 高（取行级确定） |
| **AC4.1 备注** | — | `:15 <td>{{ nc.handling_result }}</td>` 同样是**原始字段**（处置结果未中文化）——文档 AC4.1 未点名，但**同属「可见文案不得英文」** 的口径面 | **未实现（超文档要求，建议一并做）** | `handling_result` 一并映射 | 高 |

> **注**：`recon-backend.md` §3-B6-01 的结论与本次一致。本次补充：**`:15` 的 `handling_result` 也是未中文化字段**（后端报告未点名）。

### 2.3 B6-02 / AC4.2 —— 来料检不合格行可跳转到到货单/采购单

| 条目 | 文档要求 | 实测（file:line 原文片段） | 状态 | 剩余工作 | 置信度 |
| --- | --- | --- | --- | --- | --- |
| **B6-02 / AC4.2** | 造一条 `target_type='goods_receipt'` 的 NC，页面出现**可点击的到货单入口** | `nonconformities.html:14` `<td>{% if nc.workpiece_id %}<a href="{{ url_for('main.workpiece_detail', id=nc.workpiece_id) }}">{{ nc.workpiece_id }}</a>{% else %}-{% endif %}</td>` ⇒ **只认工件**；来料检 NC 的 `workpiece_id` 为 NULL ⇒ 该列恒显示 `-` | **未实现** | 按 `target_type` 分支渲染：`goods_receipt` → `url_for('main.goods_receipt_detail', …)`（或采购单）；`production_record` → 生产记录链接（与 B4-04 同一处改动）。`mes_service.nonconformity_target`（`mes_service.py:819`）已提供 `(target_type, target_id)`，模板可直接用 | 高（取行级确定） |

### 2.4 B6-03 / AC4.3 —— 返工必须有工序 + 员工必填下拉与可读校验提示

| 条目 | 文档要求 | 实测（file:line 原文片段） | 状态 | 剩余工作 | 置信度 |
| --- | --- | --- | --- | --- | --- |
| **B6-03 / AC4.3** | 返工表单出现**工序与员工两个必填下拉**；不选提交 → **可读校验提示**（不是 500 / 静默指派） | `nonconformities.html:18-23`：`<form class="d-inline" method="post" action="{{ url_for('main.dispose_nonconformity_api', id=nc.id) }}">` + `:19` 仅 `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">` + `:20-22` 三个 `<button name="action" value="rework|scrap|accept">` ⇒ **表单里没有任何 `rework_process_id` / `employee_id` / `rework_quantity` / `scrap_quantity` 输入** | **未实现** | 补 2 个必填下拉（工序/员工），数据源**已存在且能力足够**：`/api/quality/processes`（`quality.py:696`，`quality.view`）与 `/api/quality/inspectors`（`quality.py:669`，`quality.view`）——两者对 inspector **同样开放**，不会引入新的 403。另注意：`rework_quantity`/`scrap_quantity` 是 `stock.py:93-94` 的**独立可选入参**（`07b` DEC-2 §2.3/§2.4：不得合并），UI 若不给输入框，后端会走缺省口径（返工件数取来源生产记录 `quantity`，见 `recon-backend.md` D 组实测） | 高（取行级确定） |

> **旁证（前端侧补充）**：`stock.py:89-102` 已支持 `rework_process_id` / `employee_id` / `rework_quantity` / `scrap_quantity` 四个入参的透传与 `int()` 转换、非法值由 `mes_service` 抛 `ValueError` ⇒ 端点 400（`stock.py:110-112`）⇒ **只缺前端表单与必填校验**。这与 `recon-backend.md` §3-B6-03 一致。

### 2.5 B6-04 / AC4.4 —— 不适用动作不提供按钮或给明确说明

| 条目 | 文档要求 | 实测（file:line 原文片段） | 状态 | 剩余工作 | 置信度 |
| --- | --- | --- | --- | --- | --- |
| **B6-04 / AC4.4** | 对来料检单页面**不显示**「返工」按钮，或点击前给出明确说明 | `nonconformities.html:17` `{% if nc.status in ('open', 'pending_approval') %}` ⇒ **对所有未闭环单都显示三按钮**（含来料检）；`mes_service.py:946-947`：`if action not in INCOMING_NC_ACTIONS: raise ValueError('来料检不合格仅支持退货/让步接收/报废处置')` ⇒ 来料检点「返工」= **HTTP 400** | **未实现** | 模板按 `nc.target_type` **条件渲染动作集**（`goods_receipt` 只给退货/让步接收/报废）；后端已有明确文案可继续兜底 | 高（取行级确定） |
| **附带（新增发现）** | — | `nonconformities.html:18-23` 的处置表单**没有任何 `can()` 守卫**。当前不构成「可见即 403」，因为页面端点 `manage_nonconformities` 用 `quality.view`（`stock.py:119-121`）、处置端点 `dispose_nonconformity_api` 用 `quality.inspect`（`stock.py:74-76`），而 `app/permissions.py:75-76` 两者**恰好都是 `('admin','manager','inspector')`** ⇒ 今天不暴露 | **部分实现（潜在失配）** | 建议补 `{% if can('quality.inspect') %}`：一旦这两个能力的角色集**分叉**（例如把 `quality.view` 开给只读角色），该页面立刻变成「看得到、点不动、报 403」，违反 `REQ-A-04` 不变式。**属预防性加固，不是当前缺陷** | 高（cap 取值与角色集为取行级确定） |

### 2.6 B6-05 / AC3.2 —— 让步审批人可按「待审批」筛选

| 条目 | 文档要求 | 实测（file:line 原文片段） | 状态 | 剩余工作 | 置信度 |
| --- | --- | --- | --- | --- | --- |
| **B6-05 / AC3.2** | 让步后状态 `pending_approval`，审批人用「待审批」筛选**只**看到该行 | 路由 `app/main/stock.py:122-124`：`def manage_nonconformities():` → `:123 items = NonconformityRecord.query.order_by(NonconformityRecord.id.desc()).limit(200).all()` → `:124 return render_template('main/stock/nonconformities.html', items=items)` ⇒ **路由完全不读 `request.args`**；模板 `nonconformities.html` **无 `<form>` 筛选控件、无 `status` 参数** ⇒ **无筛选入口**（也就无所谓「只看该行」） | **未实现** | 路由加 `status`（≤白名单）筛选参数 + 模板加筛选控件；按计划「不改二次点击审批机制本身」 | 高（取行级确定） |

### 2.7 B6-06 / AC7.1 —— 质检记录详情弹窗显示处置信息（消除死分支）

| 条目 | 文档要求 | 实测（file:line 原文片段） | 状态 | 剩余工作 | 置信度 |
| --- | --- | --- | --- | --- | --- |
| **B6-06 / AC7.1** | 已有 NC 的质检记录详情中，**处置类型/处置人/时间/结果/备注可见** | **模板侧（请求方）**：`quality/records.html:404-405` `const nonconformityContainer = document.getElementById('nonconformityContainer');` / `const nonconformityInfo = document.getElementById('nonconformityInfo');`；`:406 if (record.nonconformity) {` → `:407 nonconformityContainer.style.display = 'block';` … `:412/416/420/424` 读 `record.nonconformity.handling_method / handler_name / handling_time / handling_notes`；`:428-429 else { nonconformityContainer.style.display = 'none'; }`；**容器初值**：`:143 <div id="nonconformityContainer" style="display: none;">` | **未实现（恒走 else 分支）** | **接口侧**：`get_inspection_record_detail`（`quality.py:1271`）的 `record_data`（实测 `:1313-1324`）键为 `id / record_code / type / inspection_target / inspector_name / inspection_time / result / notes / items / base_items` —— **无 `nonconformity` 键**（`jsonify` 在 `:1326-1329`）⇒ `record.nonconformity` **恒 `undefined`**。补键时须**按模板已用的字段名对齐**：`handling_method / handler_name / handling_time / handling_notes` | 高（两端取行级确定） |
| **交叉证据（强对照）** | — | 同仓的 `quality/print_record.html:167-196` **已经正确**实现了同一功能：`:167 {# nonconformity_records 是 lazy='dynamic' 关系，直接做真值判断恒为真、[0] 在空集上会抛 IndexError #}`、`:168 {% set nonconformity = record.nonconformity_records.first() %}`、`:169 {% if nonconformity %}` … `:178 {{ nonconformity.type }}` / `:182 {{ nonconformity.handler.username if nonconformity.handler else '未知' }}` / `:186 {{ nonconformity.handling_date.strftime('%Y-%m-%d') }}` / `:192 {{ nonconformity.handling_result }}` / `:196 {{ nonconformity.notes or '无' }}` | **已实现（打印页已可用）** | ⇒ 「记录详情弹窗缺处置信息」**不是数据模型缺能力，而是详情接口漏了键**；可**照抄 `print_record.html` 的取数口径**（关系是 `record.nonconformity_records`，`lazy='dynamic'` ⇒ 必须 `.first()`，**不得**直接真值判断） | 高 |

> ⚠ **实现提示（防复发）**：`NonconformityRecord` 关系名是 **`nonconformity_records`**（`models.py:886` `nonconformity_records = db.relationship('NonconformityRecord', backref='record', lazy='dynamic')`），**不是** `record.nonconformity`。`print_record.html:167` 的注释已经把「直接真值判断恒为真」这个坑写明了 —— 补接口时若在 Python 侧取，需注意同一语义。

### 2.8 `nonconformities.html` 逐行原文（全 33 行，供下游直接引用）

```jinja
 1  {% extends "base.html" %}
 2  {% block title %}不合格处置{% endblock %}
 3  {% block content %}
 4  <div class="container mt-4">
 5      <h2>不合格处置</h2>
 6      <table class="table table-hover">
 7          <thead><tr><th>ID</th><th>类型</th><th>状态</th><th>工件</th><th>结果</th><th>操作</th></tr></thead>
 8          <tbody>
 9          {% for nc in items %}
10              <tr>
11                  <td>{{ nc.id }}</td>
12                  <td>{{ nc.type }}</td>
13                  <td>{{ nc.status }}</td>
14                  <td>{% if nc.workpiece_id %}<a href="{{ url_for('main.workpiece_detail', id=nc.workpiece_id) }}">{{ nc.workpiece_id }}</a>{% else %}-{% endif %}</td>
15                  <td>{{ nc.handling_result }}</td>
16                  <td>
17                      {% if nc.status in ('open', 'pending_approval') %}
18                      <form class="d-inline" method="post" action="{{ url_for('main.dispose_nonconformity_api', id=nc.id) }}">
19                          <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
20                          <button class="btn btn-sm btn-outline-primary" name="action" value="rework">返工</button>
21                          <button class="btn btn-sm btn-outline-danger" name="action" value="scrap">报废</button>
22                          <button class="btn btn-sm btn-outline-success" name="action" value="accept">让步</button>
23                      </form>
24                      {% endif %}
25                  </td>
26              </tr>
27          {% else %}
28              <tr><td colspan="6" class="text-muted">暂无不合格记录</td></tr>
29          {% endfor %}
30          </tbody>
31      </table>
32  </div>
33  {% endblock %}
```

---

## 3. P7 —— 质检任务模板下拉的 `goods_receipt` 选项与类型校验（**三角死锁**）

### 3.1 后端侧（复核 `recon-backend.md` §5-P7 / `70-` §4-P7，结论成立）

| 项 | 实测坐标与原文 | 判定 |
| --- | --- | --- |
| 模板类型校验 | `app/main/quality.py:837` `# 检查模板类型是否匹配` → `:838 if template.type != task.target_type:` → `:839 return jsonify({'success': False, 'message': '质检模板类型与任务类型不匹配'}), 400` | **仍 400**（严格相等，无兼容分支） |
| `goods_receipt` 模板兜底 | `app/services/mes_service.py:90 def create_inspection_task(target_type, target_id, notes='')` → `:91 template = pick_template(target_type)` → `:92 # 模板类型可能只有 production_record/material/product，工件/炉次复用最近的生产记录模板` → `:93 if template is None and target_type in ('workpiece', 'heat_lot', 'goods_receipt'):` → `:94 template = pick_template('production_record') or pick_template('material') or pick_template('product')` | **会绑上一个类型不匹配的模板** |
| 兜底取模板定义 | `mes_service.py:85 def pick_template(target_type):` → `:87 return InspectionTemplate.query.filter_by(type=target_type, is_active=True).first()` | 「有 `goods_receipt` 模板就用它」的路径**存在**，但创建侧永远先试兜底 ⇒ 只要库里没有 `goods_receipt` 模板（界面根本造不出来，见 3.2），任务必然带的是 `production_record` 系模板 |
| 到货检任务创建点 | `app/main/purchase.py:379` `task = mes_service.create_inspection_task('goods_receipt', receipt.id, notes=f'到货 {receipt.receipt_no} 来料检验')` | 来料检任务**确实会被自动创建**，`target_type='goods_receipt'` |

### 3.2 前端侧（**本报告新增的关键证据**）—— `goods_receipt` 在 3 处 UI 枚举里全部缺席

| # | 位置 | 实测原文 | 影响 |
| --- | --- | --- | --- |
| ① | `app/templates/main/quality/templates.html:103-107` | `<select class="form-select" id="templateType" name="type" required>` / `<option value="production_record">生产记录质检</option>` / `<option value="product">成品质检</option>` / `<option value="material">原材料质检</option>` / `</select>` | **无法创建 `type='goods_receipt'` 的质检模板** ⇒ 3.1 的兜底**必然触发** |
| ② | `app/templates/main/quality/tasks.html:121-125` | `<select class="form-select" id="taskType" name="type" required onchange="loadInspectionTargets()">` / `<option value="production_record">生产记录质检</option>` / `<option value="product">成品质检</option>` / `<option value="material">原材料质检</option>` | **无法手工建来料检任务** |
| ③ | `app/templates/main/quality/tasks.html:24-29` | `<select class="form-select" id="type" name="type">` / `<option value="">全部类型</option>` / `<option value="production_record">生产记录质检</option>` / `<option value="product">成品质检</option>` / `<option value="material">原材料质检</option>` | **无法按「来料检」筛出这类任务**（列表里会显示为 raw `goods_receipt`） |

**同一口径的三张 JS 显示名映射表也全部不含 `goods_receipt`**：

| 位置 | 原文 | 后果 |
| --- | --- | --- |
| `tasks.html:363-371` | `function getTaskTypeName(type) { const types = { 'production_record': '生产记录质检', 'product': '成品质检', 'material': '原材料质检' }; return types[type] \|\| type; }` | 列表「任务类型」列对来料检显示 **`goods_receipt`** |
| `records.html:255-262` | `function getRecordTypeName(type) { const types = { …同上三项… }; return types[type] \|\| type; }` | 质检记录列表「类型」列同理 |
| `app/main/quality.py:1502-1506` | `_TASK_TYPE_NAMES = { 'product': '成品质检', 'production_record': '生产记录质检', 'material': '原材料质检', }` | 导出 CSV 的「检验类型」列同理（`:1521` `'检验类型': _TASK_TYPE_NAMES.get(task.target_type, task.target_type or '')`） |

**后端白名单同样不含它**：`app/main/quality.py:1507` `_VALID_TASK_TYPES = ('product', 'production_record', 'material')` ⇒ 导入校验 `quality.py:1655 if target_type not in _VALID_TASK_TYPES:` 会**拒绝**来料检类型的导入行。

### 3.3 P7 结论（升级表述）

| 项 | 判定 | 依据 |
| --- | --- | --- |
| **形态** | **三角死锁（三处口径互斥）**：① 业务口径（`04` §2.1 A4 写「启用的 `type='material'` 质检模板」）② 实现口径（`quality.py:838` 要求 `template.type == 'goods_receipt'`）③ **界面可选项**（3 处枚举都没有 `goods_receipt`） | §3.1 + §3.2 |
| **可观测后果（源码级推断，`推断`置信度）** | 来料检出 `pending_inspection` → 自动建 `goods_receipt` 任务 → 任务携带一个 `production_record/product/material` 模板 → 检验员在 Modal 里**选中该模板提交** → `:838` 类型不等 ⇒ **400「质检模板类型与任务类型不匹配」**。即使检验员按 ② 去找 `goods_receipt` 模板，① 也造不出来（下拉没有该选项） | `purchase.py:379` + `mes_service.py:87/93-94` + `quality.py:838` + `templates.html:103-107` |
| **未复核（不写成通过）** | 上述末端的 **400 断言**未由本任务复跑（无浏览器、且复跑需发请求）——`70-` §4-P7 记 V-12 探针 `CA4N` 实测 400、`CA4a` 实测 `ui_goods_receipt_option = False`，**本报告只确认其两处载体（`quality.py:838`、3 处枚举）仍在位** | — |
| **修法（两条路，须先拍板，属 `70-` §513⑦）** | **A**：`04` 文档口径改 `goods_receipt`，并给 3 处 UI 枚举 + 3 张 JS 名映射表 + `_VALID_TASK_TYPES` 补 `goods_receipt`，同时允许创建该类模板；**B**：实现接受 `material` 作为来料检模板类型（放宽 `:838`），界面仍补 `goods_receipt` 选项以免混淆 | — |
| **⚠ 反身提醒** | 若只做 B 的「放宽校验」而不补 UI 选项，**会隐藏**问题（校验不再报错，但界面仍无该类型模板，用户无法主动建来料检模板）⇒ **无论选哪条路，3 处 UI 枚举都必须补**（这正是 `70-` §513 ⑦ 括号里那句「**并给界面加 `goods_receipt` 选项**」的实质） | — |

---

## 4. 前端资产一致性与风险

### 4.1 `base.html` 资产引入（全部经 `url_for`，**无 CDN 外链**）

| 资产 | 坐标 | 原文（截断） | 判定 |
| --- | --- | --- | --- |
| Bootstrap 5 | `base.html:9` / `:544` | `{{ bootstrap.load_css() }}` / `{{ bootstrap.load_js() }}`（`flask_bootstrap`） | 已引入 |
| jQuery 3.6.0 | `:545` | `<script src="{{ url_for('static', filename='vendor/jquery/jquery-3.6.0.min.js') }}"></script>`（**在 Select2/SweetAlert2 之前**，顺序正确） | 已引入 |
| Toastr | `:14`（css）/ `:546`（js） | `vendor/toastr/toastr.min.css` / `.min.js` | 已引入 |
| Select2 | `:15-16`（css）/ `:547`（js） | `vendor/select2/select2.min.css` + `select2-bootstrap-5-theme.min.css` / `select2.min.js` | 已引入（含 bootstrap-5 主题） |
| SweetAlert2 | `:17`（css）/ `:548`（js） | `vendor/sweetalert2/sweetalert2.min.css` / `.min.js` | 已引入 |
| jsQR（扫码） | `:549` | `vendor/jsqr/jsQR.min.js` | 已引入（`AGENTS.md` 未列，属项目自有能力） |
| FontAwesome / Bootstrap Icons | `:10-13` | `vendor/fontawesome/all.min.css` + `vendor/bootstrap-icons/bootstrap-icons.css`，另有 `:10-11` 的 `rel="preload"` 字体 | 已引入 |
| 项目自有 CSS | `:18-20` | `css/style.css` / `css/responsive.css` / **`css/mobile-components.css`** | 已引入 |
| 项目自有 JS | `:567-568` | **`js/mobile-optimization.js`** / `js/pagination.js` | 已引入 |
| CSRF meta | `:7` | `<meta name="csrf-token" content="{{ csrf_token() }}">` | 已引入 |
| 移动端导航元数据 | `:550`（注释）/ `:552-566`（两个 `#mobileNavMeta` 分支） | `#mobileNavMeta`（`{% if current_user.is_authenticated %}` 两分支，URL **全部 `url_for`** 生成） | 已引入 |
| 外链 CDN | — | 全 `base.html` 扫描 `http://` / `https://` 引入：**无** | 无 CDN 依赖 |

### 4.2 `$.ajaxSetup` CSRF 与移动端资产

| 项 | 实测 | 判定 |
| --- | --- | --- |
| CSRF 统一注入 | `base.html:571-579` `$.ajaxSetup({ beforeSend: function(xhr, settings) { if (!/^(GET\|HEAD\|OPTIONS\|TRACE)$/i.test(settings.type) && !this.crossDomain) { xhr.setRequestHeader("X-CSRFToken", $('meta[name="csrf-token"]').attr('content')); } } });` | 已实现，**但只覆盖 jQuery 的 `$.ajax/$ .post/$ .get`**（实测 **27 处**）；**原生 `fetch()` 不经过它** ⇒ 见 §5.2 |
| `mobile-optimization.js` 被引用 | `base.html:567` | 已引用 |
| `mobile-components.css` 被引用 | `base.html:20` | 已引用 |
| 移动端 JS 契约 | `mobile-optimization.js:3-7`（注释）：侧边栏**不再由该文件重建**，只做「结构搬运 + CSS class 映射」，**不含硬编码 URL / 角色判断**；少量非权限信息由 `#mobileNavMeta` 注入 | 与 `base.html:550-566` **口径一致**（已核对，无矛盾） |
| 移动端 class 的实际使用面 | 模板内 `mobile-*` 字样 **30 次 / 仅 2 个模板**：`mobile-table` 23、`mobile-status-badge` 5、`mobile-filters` 2（出现在 `main/customers.html`、`main/products.html`）。`mobile-components.css` 顶层定义 **46 个 class** | **口径说明（防误读）**：其余 class（`mobile-sidebar*` / `mobile-nav*` / `mobile-loading*` / `mobile-empty-*` / `mobile-stats-card` …）由 **`mobile-optimization.js` 在运行时生成/挂载**，故**不可能**出现在模板源文本里。⇒ 「模板里只有 3 个 mobile-* class」**不等于**「CSS 有 43 个死类」；本任务**不做**死类判定（需浏览器 DOM，`无法核实（需浏览器）`） |
| 移动端真实行为（断点、侧边栏开合、表格横向滚动） | `mobile-optimization.js:11` `const isMobile = window.innerWidth <= 768;`、`:9 DOMContentLoaded`、`:227 document.getElementById('mainNavMenu')`（搬运对象存在，已被 `base.html:266` 的 `<ul class="navbar-nav me-auto" id="mainNavMenu">` 提供） | **静态一致；实际渲染行为 `无法核实（需浏览器）`** |

### 4.3 Select2 异步契约与后端一致性（含 1 个新增缺口）

**契约基准（AGENTS.md 库存 API 约定）**：`{'success': True, 'data': [...]}`，字段含 `id, name/specification/quantity`。

| 端点 | 坐标 | 实测返回构造 | 契约 |
| --- | --- | --- | --- |
| `/api/inventory/raw-materials` | `routes.py:6028-6058`（`def get_available_raw_materials` @`:6030`；`@require_capability('material.lookup')` @`:6029`） | `:6044-6053` 每行 `{id, name, material_name, specification, quantity, supplier, melt_number, internal_number}` → `:6055-6058 return jsonify({'success': True, 'data': materials_list})` | **合规**（`name`/`quantity`/`specification` 齐备，且保留 `material_name` 别名） |
| `/api/inventory/finished-products` | `routes.py:6065-6116`（`def` @`:6068`；`product.view` @`:6067`） | `:6092-6106` 每行 `{id, name, product_number, drawing_number, model, serial_number, specification, unit, quantity, status, inspector, production_date}`；`:6099` 注释明写「Select2 契约与 `/api/inventory/raw-materials` 对齐：id/name/specification/quantity」 | **合规** |
| `/api/inventory/consumables` | `routes.py:6118-6141`（`def` @`:6121`；`inventory.manage` @`:6120`） | `:6123` 注释「结构与原材料接口一致」；`:6129-6138` 同字段族；`:6139 return jsonify({'success': True, 'data': data})` | **合规** |
| 搜索参数 | 三端点**只读 `only_available`**（`:6040` / `:6078` / `:6126`），**均不读 `search`** | — | **见下方缺口** |

**前端消费侧（抽样，全部按 `data.data` 取数组、`data.success` 判成败）**

| 模板 | 坐标 | 原文（截断） |
| --- | --- | --- |
| `tasks.html` | `:410`（url）/ `:416`（`search: params.term`）/ `:428` / `:434` | `if (!data.data \|\| !Array.isArray(data.data)) { … }` → `const filteredData = data.data.filter(item => !selectedMaterials.has(item.id.toString()));` |
| `my_tasks.html` | `:175` / `:181` / `:193` / `:199` | 同上（且 `:188` 先判 `!data.success`） |
| `production_batch_detail.html` | `:350` / `:356` / `:367` / `:373` | 同上 |
| `quality/tasks.html` | `:526` / `:553-554` / `:769` / `:804-805` | `options += data.data.map(material => \`<option value="${material.id}">${material.internal_number} - ${material.material_name \|\| ''}</option>\`)` |
| `product_bom.html` | `:408/:410` / `:425-426` / `:443` | `if (data.success && data.data && data.data.length > 0) { data.data.forEach(material => { …` |
| `material_requisition_form.html` | `:274-276`（url 三选一）/ `:296` | `(resp.data \|\| []).forEach(function(r) { …` |

> ✅ **契约一致性结论**：前端一律读 `data.data`（数组）或 `data.data.items`（分页对象），与后端 `jsonify({'success':…, 'data':…})` **一致**；未发现「前端读 `data.results`」「后端返回裸数组」之类的结构性错配。
>
> ✅ **Select2 分页对象的写法也是对的**：`quality/tasks.html:964` / `quality/task_detail.html:396` 的 `fetch("{{ url_for('main.get_templates') }}?type=" + encodeURIComponent(taskType) + "&is_active=true")` 配 `:971-972 if (data.data && data.data.items) { data.data.items.forEach(…) }` ⇒ 与 `get_templates` 的分页返回（`quality.py:174-179`，`:178 'pages': pagination.pages`）**形状匹配**。

**⚠ 新增缺口 F-1：Select2 服务端搜索静默失效（3 个模板 / 7 处）**

| 项 | 实测 |
| --- | --- |
| 前端发送 | `app/templates/main/tasks.html:413-418`（`data: function(params){ return { only_available: true, search: params.term }; }`，`search` 在 `:416`）、`app/templates/main/my_tasks.html:178-183`（同形，`search` 在 `:181`）、`app/templates/main/production_batch_detail.html:353-357`（同形，`search` 在 `:356`） |
| 后端实现 | `get_available_raw_materials`（`routes.py:6030-6058`）函数体内**只出现** `request.args.get('only_available', 'false')`（`:6040`）——**全函数无 `search`**。同类两接口（`:6068` 成品 / `:6121` 易耗品）同样无 `search` |
| 全仓 `search` 读取点对照 | `grep request.args.get('search')`：`routes.py` 有 `:1326/:1553/:3144/:4080/:4779/:6979/:7986/:9096/:9514/:9563/:10130` 等 **十余处**，`quality.py:134/510/1167/1376/1543`、`production_center.py:34`、`equipment.py:337` ⇒ **该端点属于少数「收 `search` 却不用」的例外**（`customers/search` `:9514` 就实现正确） |
| 可观测后果（`推断`置信度） | Select2 输入关键字 → 请求带上 `search=` → 后端忽略 → 返回**与首次加载完全相同**的列表 → `processResults` 只按「已选」过滤 ⇒ **用户看到「搜了没变化」**。`tasks.html`（任务派工要选原料）与 `my_tasks.html`（员工手机端选料，数据量最大）**受影响最重** |
| 静态边界 | Select2 的 `params.term` 是否真的被填入、下拉是否真的「没有过滤」属**运行时行为** ⇒ `无法核实（需浏览器）`；但「后端不读 `search`」是**取行级确定** |
| 建议 | 二选一：① 三端点补 `search`（按 `name`/`internal_number`/`specification` 模糊匹配，与 `:1553-1554` 既有写法对齐）；② 前端撤掉 `search:` 参数并**明确改为客户端过滤**（但当前 `processResults` 只过滤「已选」，需另加 `matcher`）。①更符合 `AGENTS.md` 的「Select2 异步接口…与现有实现保持一致」 |

---

## 5. 硬编码 URL 与 CSRF 头缺口

### 5.1 未用 `url_for` 的硬编码根相对 URL（全仓 **9 处 / 6 个模板**）

| # | 坐标 | 原文（截断） | 对应端点与能力 | 风险 |
| --- | --- | --- | --- | --- |
| 1 | `main/consumable_categories.html:196` | `fetch('/consumables/categories/add', {` | `/consumables/categories/add`（**端点定义** `routes.py:11042`，**视图函数** `routes.py:11045 def add_consumable_category()`，`inventory.manage`） | 蓝图为 `main` 蓝图（无 `url_prefix`，`app/__init__.py:235`）⇒ 今天可用；**一旦加前缀即全断**（`AGENTS.md`「必须通过 `url_for('main.xxx')` 生成链接」） |
| 2 | `main/inventory.html:937` | `fetch('/inventory/auto-archive', {` | `/inventory/auto-archive`（`routes.py:6231`，`inventory.manage`） | 同上 |
| 3 | `main/products.html:439` | `fetch('/code_rules/available/product')` | `/code_rules/available/product`（`routes.py:5541`，`product.view`） | 同上 |
| 4 | `main/products.html:604` | `fetch('/code_rules/available/product')` | 同上 | 同上 |
| 5 | `main/products.html:665` | `fetch('/products/import', {` | `/products/import`（`routes.py:7685`，`product.import`） | 同上 |
| 6 | `main/products.html:714` | `fetch('/products/import', {` | 同上 | 同上 |
| 7 | `main/products.html:779` | `hiddenForm.action = '/products/export';` | `/products/export`（**端点定义** `routes.py:7909`，**视图函数** `routes.py:7912 def export_products()`，`product.view`） | 同上 |
| 8 | `main/quality/inspection.html:284` | `window.location.href = '/quality/tasks';` | `/quality/tasks`（`quality.py:69`，`quality.view`） | 同上 |
| 9 | `main/quality/task_detail.html:482` | `window.location.href = '/quality/tasks';` | 同上 | 同上 |

- **未命中即通过的部分（也算结论）**：`grep` 全模板的 `href="/…` / `action="/…"` 形式 ⇒ **零件命中**（`(href|action)="/[a-z]` → No matches）；上面 9 处**全是 JS 里的字符串**（`fetch(...)` / `location.href=` / `hiddenForm.action=`）。⇒ **HTML 属性面已 100% 使用 `url_for`**，欠债集中在 **JS 字面量**。
- 参考坐标（`url_for` 正确用法）举例：`quality/tasks.html:301/649/660/673/691/901/964/1001`、`quality/records.html:201/309/329/444`、`quality/templates.html:194/316/383/748` —— 同一批文件里**既有正确也有硬编码**，属**局部遗留**而非系统性缺失。

### 5.2 原生 `fetch()` 非 GET 站点缺 `X-CSRFToken`（**新增发现，15 处 / 7 个模板**）

**背景**：`base.html:573` 的 `$.ajaxSetup` 只对 jQuery 生效；原生 `fetch()` 必须**逐点**带令牌（正确样例：`inventory.html:939-942` 就是 `fetch` + `'X-CSRFToken': '{{ csrf_token() }}'`）。

**扫描口径**：`fetch(` 站点总数 **118**；其中非 GET **73**；「非 GET 且调用点 420 字符内无 `X-CSRFToken`/`csrf_token`」**19**；逐点 `read` 复核（取 `fetch` 行起 11 行）后**确认真阳性 15 处**：

| # | 坐标 | 方法 | 端点（由 `url_for`/字面量还原） | 端点能力 |
| --- | --- | --- | --- | --- |
| 1 | `quality/tasks.html:627` | `DELETE` | `/api/quality/tasks/<id>`（`quality.py:654-658`，`manage_task`） | `quality.task.manage` |
| 2 | `quality/tasks.html:1001` | `POST` | `/api/quality/tasks/<id>/start-inspection`（`quality.py:796-800`） | `quality.inspect` |
| 3 | `quality/task_detail.html:433` | `POST` | 同上 | `quality.inspect` |
| 4 | `quality/task_detail.html:475` | `DELETE` | `/api/quality/tasks/<id>` | `quality.task.manage` |
| 5 | `quality/inspection.html:272` | `POST` | `/api/quality/records/<id>/submit`（`quality.py:896-900`） | `quality.inspect` |
| 6 | `production_center_item.html:171` | `POST` | `api_save_tech_decomposition` | 见 `production_center.py` |
| 7 | `production_center_item.html:204` | `POST` | `api_execute_operation` | 见 `production_center.py` |
| 8 | `production_center.html:92` | `POST` | `api_create_instances` | 见 `production_center.py` |
| 9 | `consumables.html:540` | `PUT` | 易耗品更新 | `inventory.manage` |
| 10 | `consumables.html:585` | `POST` | 易耗品新增 | `inventory.manage` |
| 11 | `consumables.html:610` | `DELETE` | 易耗品删除 | `inventory.manage` |
| 12 | `consumable_categories.html:247` | `PUT` | 易耗品品类更新 | `inventory.manage` |
| 13 | `consumable_categories.html:272` | `DELETE` | 易耗品品类删除 | `inventory.manage` |
| 14 | `delivery_batches.html:289` | `POST` | 交付批次保存 | 见 `routes.py` |
| 15 | `process_assignment_bulk.html:107` | `POST` | `save_process_assignment_bulk`（`routes.py`） | 见 `process_assignment.manage` |

**后果链（`推断`置信度，但每一环都有取行级证据）**：
`fetch` 无 `X-CSRFToken` → `CSRFProtect`（`app/__init__.py:16 csrf = CSRFProtect()`、`:169 csrf.init_app(app)`）判定令牌缺失 ⇒ 抛 `CSRFError`（**400**）→ `app/__init__.py:205 @app.errorhandler(HTTPException)` → `:213 if permissions._wants_json():`（`:139-148` 的 `_wants_json`：路径以 `/api/` 开头**即**真）→ `:215 return jsonify({'success': False, 'message': '请求参数有误'}), 400` → 前端 `.then(response => response.json())` 拿到 `success:false` → 走 `else` 分支弹「**请求参数有误**」或 `.catch` 弹「操作失败」。

> ✅ **一个反面澄清（防误读）**：`_wants_json` 的第 ④ 条（`request.method in ('DELETE','PUT','PATCH')` ⇒ 真）保证**即使路径不是 `/api/`**，这类请求也拿到 **JSON** 而不是 HTML。⇒ 该缺陷**不会**表现为「前端解析 HTML 报错」，而表现为**功能静默失败 + 通用提示**（`AGENTS.md` 的 `D-9`「凡文档说已修不算通过」同理：这里应记「**功能不可用**」而非「报错难懂」）。

**静态边界**：令牌是否真的「在浏览器中最终没带上」属运行时事实；本任务确认的是**调用点源码里没有该头/该字段**（同时这些站点**没有** `@csrf.exempt`——已逐点用 AST 检查：上表端点的 `csrf_exempt` 均为 `False`）。⇒ 标 `高（取行级确定）`，但**「实际 400」未经请求型复跑**。

**建议**：把 `base.html:571-579` 的 `$.ajaxSetup` 思路原生化 —— 抽一个 `window.apiFetch(url, opts)`（内部从 `meta[name=csrf-token]` 注入 `X-CSRFToken` 并统一错误提示），然后把这 15 处（外加 `products.html:665` 等同类）改调它。**不建议**在 15 处各贴一次 header（会再次漂移）。

---

## 6. 死分支 / 不可达 UI

### 6.1 已证死分支与不可达调用

| # | 坐标 | 现象 | 判定 | 依据 |
| --- | --- | --- | --- | --- |
| 1 | `quality/records.html:406-430`（容器 `:143`） | `if (record.nonconformity) { … } else { display='none' }` **恒走 else**：`get_inspection_record_detail` 的 `record_data`（`quality.py:1313-1324`）**无 `nonconformity` 键**；`records.html:333 renderRecordDetail(data.data)` 传的就是它 | **死分支（已证）** | 两端取行级确定；同仓 `print_record.html:167-196` 有可用的正确实现（强对照） |
| 2 | `quality/records.html:159` | `<button type="button" class="btn btn-primary" onclick="printRecord()">打印</button>` —— 弹窗底部「打印」**零实参**；而 `printRecord` 定义在 `:434`：`function printRecord(id) { window.open("{{ url_for('main.get_inspection_records') }}" + '/' + id + '/print', '_blank'); }` ⇒ 实际打开 `…/undefined/print` | **不可达/必失败（已证）** | 全仓扫描「同文件内定义有必填形参、调用点零实参」⇒ **唯一命中就是它**（`:240` 的列表内按钮**写对了**：`printRecord(${record.id})`） |
| 3 | `quality/index.html:50` | `<a href="{{ url_for('main.quality_templates') }}" class="btn btn-outline-success">` —— 「质检模板」快捷入口**无 `can()` 守卫**；而 `quality_templates` 端点要求 `quality.template.manage`（`quality.py:58-61`，角色 **admin/manager**），本页页面端点 `quality_management` 只要 `quality.view`（`quality.py:38-41`，角色 **admin/manager/inspector**） | **违反 REQ-A-04 不变式（已证）** | 同一「快捷操作」组里 `:56-58` 的「不合格处置」与 `:47-49`/`:53-55` 三项能力恰好包含 inspector，**只有 `:50` 这一项会 403** |
| 4 | `quality/task_detail.html` 的模板详情用法 | 该模板调 `url_for('main.get_templates')`（`:396`，`quality.view`）而**未**调 `get_template_detail` ⇒ **inspector 不会踩到 `quality.template.manage`** | **不构成问题（澄清）** | 交叉核对：`task_detail.html` 的 4 个被调端点对其页面能力**零差集**（§1 方法复跑） |

### 6.2 页面内「可见即 403」的失配清单（AC-02 / REQ-A-04）

**方法**：对每个质检页模板，取其页面端点的能力角色集，与页内 `url_for('main.X')` 命中的每个端点的能力角色集求**差集**（脚本见 §8）。

| 页面（模板） | 页面端点能力 → 角色 | 失配端点 | 端点角色 | 差集 | 模板是否已守卫 | 判定 |
| --- | --- | --- | --- | --- | --- | --- |
| `quality/index.html` | `quality.view` → admin/manager/inspector | `quality_templates` | admin/manager | **inspector** | **否**（`:50` 无 `can()`） | **真失配**（见 6.1-3） |
| `quality/records.html` | `quality.view` → admin/manager/inspector | `export_inspection_records` | admin/manager | inspector | **是**（`:10 {% if can('quality.export') %}`） | ✅ 已守卫，**符合不变式** |
| `quality/records.html` | 同上 | `print_inspection_record` | `quality.view` | — | `:239 {% if can('quality.view') %}` | ✅ |
| `quality/tasks.html` | 同上 | `export_inspection_tasks` / `download_inspection_task_template` | `quality.export` → admin/manager | inspector | **是**（`:59`、`:65` 两处 `can('quality.export')` / `can('quality.task.manage')`） | ✅ |
| `quality/tasks.html` | 同上 | `import_inspection_tasks` | `quality.task.manage` → admin/manager | inspector | **是**（`:64 {% if can('quality.task.manage') %}`） | ✅ |
| `quality/tasks.html:340` | 同上 | `start_inspection` | `quality.inspect` → admin/manager/inspector | — | 用**内联 role**（`:340`）而非 `can()`；**今天角色集相同** | ⚠ 潜在（见 §1.3 建议） |
| `app/templates/main/stock/nonconformities.html` | `quality.view` → admin/manager/inspector | `dispose_nonconformity_api` | `quality.inspect` → admin/manager/inspector | — | **无 `can()` 守卫**（`:18-23`） | ⚠ 潜在（今天角色集相同；见 §2.5） |
| 其余质检页（`inspection.html` / `task_detail.html` / `templates.html`） | — | — | — | **零差集** | — | ✅ |

> **小结**：AC-02「可见即不会 403」在**导航面**成立、在**质检页内按钮面**有 **1 处真失配（`quality/index.html:50`）**+ **2 处潜在失配（内联 role / 缺 `can()`，今天恰好等价）**。

---

## 7. 全量对账总表（批次6 + P7 + 前端资产）

> 状态词：`已实现` / `部分实现` / `未实现` / `文档漂移` / `无法核实`。置信度：`高`=取行级确定；`中`=需运行级复核；`无法核实（需浏览器）`=静态不可判。

| 条目 | 文档要求 | 实测（file:line 原文片段） | 状态 | 剩余工作 | 置信度 |
| --- | --- | --- | --- | --- | --- |
| 模板规模 | — | 87 个 `.html`（非 html 0 个）；`check_templates` `parsed 87 files`，exit 0 | **已实现一致** | 无 | 高 |
| `can()` 渲染面 | 入口可见 ⟺ 端点有能力（AC-02/REQ-A-04） | 101 处 `can()` + 7 处 `can_any()`（`base.html:268/286/324/387/417/432`）；模板侧 40 个能力 = 门禁 `40 used in templates` | **已实现（导航面）** | 补 `quality/index.html:50` + 2 处潜在失配 | 高 |
| 内联 role（模板 2 处） | D4/B9-02：模板 2 处 + Python 15 处；`tasks.html:337`→`:340` | `tasks.html:340`、`task_detail.html:13`（**仍是内联 role**） | **已实现一致（未清零，契约允许）** | `:340` 建议改 `can('quality.inspect')` | 高 |
| **B6-01 / AC4.1** | 可见文案不出现英文枚举 | `nonconformities.html:12 {{ nc.type }}` / `:13 {{ nc.status }}` /（另 `:15 {{ nc.handling_result }}`） | **未实现** | 用 `models.py:955 target_label` / `mes_service.INCOMING_NC_LABELS` 中文化 | 高 |
| **B6-02 / AC4.2** | 来料检行可跳转到货单/采购单 | `nonconformities.html:14` 只认 `nc.workpiece_id` | **未实现** | 按 `target_type` 分支（`goods_receipt`/`production_record`） | 高 |
| **B6-03 / AC4.3** | 返工可选工序 + 员工（必填）+ 可读校验 | `nonconformities.html:18-23` 表单**只有 csrf + 3 个 action 按钮**；`stock.py:89-102` 已支持四入参透传 | **未实现（仅缺前端+必填校验）** | 补 2 必填下拉（数据源 `quality.py:669/696` 已具备） | 高 |
| **B6-04 / AC4.4** | 不适用动作不给按钮或明确说明 | `nonconformities.html:17` 对所有未闭环单显示三按钮；`mes_service.py:946-947` 来料检点返工 ⇒ ValueError ⇒ `stock.py:110-112` 400 | **未实现** | 按 `target_type` 条件渲染动作集 | 高 |
| **B6-05 / AC3.2** | 「待审批」筛选只看该行 | `stock.py:122-124`（`:123` `limit(200)`、**不读 args`）；模板无筛选控件 | **未实现** | 路由加 `status` 白名单筛选 + 模板控件 | 高 |
| **B6-06 / AC7.1** | 记录详情显示处置信息 | `records.html:143/404-430` 恒隐藏；`quality.py:1313-1324` 无 `nonconformity` 键；**对照 `print_record.html:167-196` 已正确** | **未实现（死分支）** | 详情接口补键（字段名对齐 `handling_method/handler_name/handling_time/handling_notes`） | 高 |
| **B4-04（模板部分）** | 列表能看出对应哪张生产记录 | `nonconformities.html:14` 同 B6-02（`production_record` 路径也只显示 `-`） | **未实现** | 与 B6-02 同一处改动 | 高 |
| **P7 / AC-24** | 来料检可用 | `quality.py:838` 仍 400；`mes_service.py:93-94` 兜底绑错类型；**`goods_receipt` 在 3 处 UI 枚举 + 3 张 JS 名映射表 + `_VALID_TASK_TYPES`(`quality.py:1507`) 全部缺席** | **未实现（三角死锁）** | ②口径二选一 + **必须补 3 处 UI 枚举**（§3.3） | 高 |
| `AC4.1–AC4.4` 的端到端 | — | 上述 6 条全红 ⇒ 批次6 的「M6 里程碑」（规划 §5-3/§5-4）**不满足** | **未实现** | 见上 | 高 |
| 资产引入 | Bootstrap5/jQuery/Select2/SweetAlert2/Toastr/CSRF | `base.html:9-20/545-549/567-568/7/573-579`；**无 CDN** | **已实现** | 无 | 高 |
| 移动端资产 | `mobile-optimization.js` / `mobile-components.css` | `base.html:20`、`:567` 均引用；`mobile-optimization.js:3-7` 声明不重建菜单、无硬编码 URL/role | **已实现** | 真实渲染 `无法核实（需浏览器）` | 高（静态）/ 无法核实（运行时） |
| Select2 契约 | `{'success':True,'data':[…]}` | `routes.py:6055-6058`（`return jsonify({` 在 `:6055`，`'success': True` 在 `:6056`）/ `:6108-6111` / `:6139` 三端点形状一致；前端一律读 `data.data` | **已实现** | 无 | 高 |
| **Select2 搜索（F-1，新增）** | `AGENTS.md`「Select2 异步接口…与现有实现保持一致」 | 前端 `app/templates/main/tasks.html:416` / `my_tasks.html:181` / `production_batch_detail.html:356` 发 `search`；后端 `routes.py:6030-6058` **不读 `search`** | **未实现（静默失效）** | 后端补 `search` 或前端改客户端过滤（§4.3） | 高（静态）/ 无法核实（浏览器观感） |
| 硬编码 URL | 一律 `url_for` | HTML 属性面 **0 处**；JS 字面量 **9 处**（§5.1） | **部分实现** | 9 处改 `url_for` | 高 |
| **CSRF 头（F-2，新增）** | `$.ajaxSetup` + JSON API CSRF 头 | `base.html:573-579` 只覆盖 jQuery（27 处）；**15 个原生 `fetch` 非 GET 站点无令牌**（§5.2） | **部分实现** | 抽 `apiFetch()` 统一注入（15 处） | 高（静态）/ 中（实际 400 未复跑） |
| 死分支/不可达 | — | §6.1 三处（`records.html:406-430` / `:159` / `index.html:50`） | **未实现** | 逐条修 | 高 |

---

## 8. 自检与边界（**我没有做什么**）

### 8.1 只读与产物

1. **只读**：未修改任何既有文件。改动面仅**新增**：① 本报告；② `.analysis-scratch/t4_tpl_scan.py`、`t4_cap_cross.py`、`t4_cap_gap.py`、`t4_csrf_split.py`、`t4_js_calls.py`（**只读分析器**，落在既有未跟踪目录 `.analysis-scratch/` 内）。
2. **真实库零改动**：`app.db` 在开工与收尾两次复核均为 `2531328 B` / `F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065` / `2026-09-18 12:50:55`。**本任务未连接数据库**（无 sqlite/flask 调用），不可能写入。
3. **未跑** `flask db *`、未跑任何请求型脚本（`smoke_test` / `permission_matrix` / `functional_test` / `w2w3_probe` 均**未复跑**，只读其历史产物与文档）。唯一执行的既有脚本是 **`scripts/check_templates.py`**（静态、只读、不改工作区文件）与 `Get-FileHash`。

### 8.2 复跑入口（仓库根目录，copy-paste）

```powershell
$env:PYTHONIOENCODING='utf-8'
$py = 'F:\Miniconda\envs\wage\python.exe'

# ① 模板规模 + 权限渲染面（can()/can_any()/内联 role）
(Get-ChildItem app\templates -Recurse -File -Filter *.html).Count
(Get-ChildItem app\templates -Recurse -File).Count
& $py -B .analysis-scratch/t4_tpl_scan.py

# ② 门禁互证（期望：parsed 87 files / 44 declared / 40 used in templates / 44 used on routes / RESULT: OK）
& $py -B scripts/check_templates.py

# ③ 页面端点能力 vs 数据源端点能力（差集）
& $py -B .analysis-scratch/t4_cap_cross.py
& $py -B .analysis-scratch/t4_cap_gap.py

# ④ CSRF：jQuery vs 原生 fetch 分流
& $py -B .analysis-scratch/t4_csrf_split.py

# ⑤ JS 零实参调用（期望：唯一命中 records.html:159 printRecord()）
& $py -B .analysis-scratch/t4_js_calls.py

# ⑥ 关键取行（本报告引用的行号，可逐条肉眼复核）
Select-String -Path app/templates/main/quality/tasks.html        -Pattern "current_user\.role"        # 期望 :340
Select-String -Path app/templates/main/quality/task_detail.html  -Pattern "current_user\.role"        # 期望 :13
Select-String -Path app/templates/main/quality/records.html      -Pattern "record\.nonconformity|printRecord\(\)"
Select-String -Path app/templates/main/stock/nonconformities.html -Pattern "."                        # 全 33 行
Select-String -Path app/main/quality.py                          -Pattern "_VALID_TASK_TYPES|template\.type != task\.target_type"
Select-String -Path app/services/mes_service.py                  -Pattern "pick_template|'goods_receipt'"

# ⑦ 真实库不变量（期望三值不变）
(Get-Item app.db).Length; (Get-FileHash app.db -Algorithm SHA256).Hash
(Get-Item app.db).LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss')
```

### 8.3 明确**未做**（不得当成已做）

1. **未用浏览器**：所有「DOM 最终渲染 / Select2 下拉实际内容 / SweetAlert 阻塞 / 移动端断点行为 / CSS 死类判定」**均未验证**，已在正文逐处标注 `无法核实（需浏览器）`。
2. **未发任何 HTTP 请求**：因此 §3.3 的 400、§5.2 的 CSRF 400、§4.3 的「搜索无变化」都是**源码链推断**，标 `推断`/`中`置信度；其**判据核心（载体仍在位 / 调用点确无令牌）**是取行级确定。
3. **未做** `AC-06` 的**Python 侧 15 处**内联 role 的逐处复核（属后端/权限面，非本任务 in-scope）；本报告只用它的**模板侧 2 处**。
4. **未评估** 46 个 `mobile-*` class 中哪些在运行时**真的被挂载**（需浏览器 DOM 快照）。
5. **未改** `docs/` 下任何文档（含 `docs/业务流程现状与缺口.md` 与 `04-业务验收标准与端到端判据.md` 的 `doc/` 口径冲突）——`docs/` 树**不可覆写**；§3.3 的「文档口径 ↔ 实现口径 ↔ 界面可选项」三方冲突**只登记，不修文档**。
6. **未复核** `recon-backend.md` 的其它条目（批次4/5/7、P1–P12）：本报告只**独立复核**了与模板/前端直接相关的 **P7 / B6-01…B6-06 / B4-04**，其余**引用其结论并标注来源**。
7. **未复核** 组件库版本号（`app/static/vendor/**` 内部版本声明）与 `bootstrap-5.3.3-dist/` 顶层目录是否与 `app/static/bootstrap/` 重复（属仓库卫生，W1/W2 面）。

---

## 9. 证据索引

| 类别 | 落点 |
| --- | --- |
| 本报告（主交付） | `test-reports-2026-10/reconcile-2026-10-08/recon-frontend.md` |
| 只读分析器 ①（模板 can()/can_any()/role） | `.analysis-scratch/t4_tpl_scan.py` |
| 只读分析器 ②（端点能力 ↔ 模板使用） | `.analysis-scratch/t4_cap_cross.py` |
| 只读分析器 ③（页面 vs 数据源能力差集） | `.analysis-scratch/t4_cap_gap.py` |
| 只读分析器 ④（jQuery vs 原生 fetch 的 CSRF 分流） | `.analysis-scratch/t4_csrf_split.py` |
| 只读分析器 ⑤（JS 零实参调用） | `.analysis-scratch/t4_js_calls.py` |
| 门禁读数（互证） | `& $py -B scripts/check_templates.py` ⇒ `87 / 44 declared / 40 used in templates / 44 used on routes / landing 5`，`RESULT: OK`，exit 0 |
| 上游交叉 | `test-reports-2026-10/reconcile-2026-10-08/00-共享事实底盘.md`（W0）· `recon-backend.md`（W2） |
| 需求侧权威 | `docs/开发与测试规划-2026-10-06.md` §1 批次4/6/9、§3.2、§5-3/5-4 · `docs/test-reports/2026-10/04-业务验收标准与端到端判据.md` §3.2/§3.7 · `docs/test-reports/2026-10/03-需求追溯矩阵.md` §1.F/§1.N · `test-reports-2026-10/70-第2轮收口与阶段C移交.md` §4-P7、§513 |

---

*本报告所有读数均为 2026-10-08 本次实测；所有行号均为本次实测行号。凡静态不可判定者已标注 `无法核实（需浏览器）`，凡经推断者已标注置信度，**均未计入「已实现」**。*
