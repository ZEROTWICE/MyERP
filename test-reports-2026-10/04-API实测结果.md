# 04 API 与写端点实测结果（MyERP 测试战役 · 阶段二 · t4）

| 项目 | 值 |
| --- | --- |
| 产出任务 | `t4` API 测试工程师（kind=work，attempt `e5f589bb-612d-4b00-a786-b62caae7fd08`） |
| 任务书 | captain「t4 任务书：权威文件名 + 你必须用的口径」（本轮唯一权威指令） |
| 纪律来源 | `00b-裁定与纪律增补.md`（A-23 起；**引用 00-系列口径以此为准**）、`08-测试总方案.md` §4 |
| 执行日期 | 2026-10-06 |
| 解释器 | `F:\Miniconda\envs\wage\python.exe`（绝对路径，A-7/E-1） |
| 被测库 | **副本**（`test-reports-2026-10/.tmp/<run>/mkdtemp/.../app.db`），真实库 `app.db` 只读 |
| 真实库指纹 | `F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065`（开工=收尾，两次独立复核） |
| 生产代码 | **只读**：`app/`、模板、`scripts/` 既有脚本一行未改 |
| 行数口径 | A-23：Python `splitlines()` |
| 交付物 | 本文件（**467 行 / 非空 375 / A-23 `splitlines()` 口径**；字节与 SHA256 随每次追加而变，**以文件系统实测为准**，本轮交接口径见 §10 第 6 条）+ `evidence/api/`（11 文件：`api_matrix.json/.out.txt`、`write_suite.json/.out.txt`、`defect_repro.json/.out.txt`、`non_get_inventory.json/.txt`、`recon_non_get.py`、`verify_t4.json/.out.txt`） |
| 独立复核 | `harness/verify_t4.py`：**44 / 44 通过**（0 FAIL）；结果落 `evidence/api/verify_t4.json` |

---

## 1. 结论摘要（先看这 6 行）

1. **匿名访问面 = 0 泄漏**：308 个方法级端点匿名实测，`allow=0`、`5xx=0`；225 条 302→`/auth/`（登录页）、82 条 401/403、1 条 404。**AC-03 通过**（硬违规 0 条）。
2. **CSRF 首次拿到实测证据**：在**同一个 app** 上临时打开 `WTF_CSRF_ENABLED`，155 个非 GET 端点逐个「空 body 无 token」提交 → **拦下 133 / 命中豁免 22 / 未拦 0（非豁免面 100% 拦截）**；豁免面与 AST 扫出的 **20 个 `@csrf.exempt` 视图（覆盖 22 个方法级端点）** 完全吻合；带合法 token 的正例不再是 400（判定装置有效）。**这项此前被登记为「从未验证」，本轮已实测通过。**
3. **写端点安全面**：54 条**落在数据变化上**的写断言（8 个域分组），PASS 51 / FAIL 3；**3 条失败全部是产品缺陷**（非夹具/脚手架问题，见 §6）。
4. **越权控制**：760 条「低权身份 × 写端点」请求，`allow=4` 且 4 条**全部落在能力登记表内**（hr 含 `task.manage`、sales 含 `customer.manage`/`sales_order.manage`）⇒ **0 条越权**。
5. **契约缺陷**：71 条违规，归并为 **7 类缺陷**；其中影响最大的是 `Consumable` 未导入导致两个易耗品写端点**恒 500**（功能完全不可用），以及 11 组「不存在的 id 返回 500 而非 404」。
6. **未执行/不可判定项**：并发、幂等、性能、安全头、多进程部署形态——**未测**，不得计为通过（§9）。

---

## 2. 分母与口径（照用已固化值，不自创）

| 项 | 值 | 口径 | 本轮实测来源 |
| --- | --- | --- | --- |
| 路由规则（全量） | **271** | `url_map` 规则级（**含** static 1 与 auth 4） | `verify_t4.json`：`len(url_map.iter_rules()) == 271` |
| 路由规则（业务） | **266** | 去掉 auth.* 与 static | 同上 |
| 方法级 GET | **161** | 规则 × 谓词（`08` §2 记 160，分歧见 A-25） | url_map 重算 156（业务 GET 谓词）+ 4（auth/static 的 GET）；`156+5=161` 与 A-25 一致 |
| POST / DELETE / PUT | **123 / 20 / 12** | 规则 × 谓词 | 同上（CSRF 矩阵按方法统计：POST 123 / DELETE 20 / PUT 12） |
| **非 GET 方法级** | **155** | 规则 × 谓词 | CSRF 矩阵 155 行 = 123+20+12；业务子集 152 |
| 非 GET 规则 | **153** | 规则级，**不可与 155 互替** | 冻结值（`02` §2）；本轮业务子集 142（差值 11 来自 auth/static 与「多个非 GET 谓词共用一条规则」的计数差） |
| 写端点静态覆盖基线 | **6 条 / 153 规则 = 3.9%** | `functional_test` 字面量命中 | A-28（已固化）；本轮未复算，直接引用 |
| **t4 新增写断言覆盖** | **54 条断言 / 46 个不同写端点** | 落在数据变化的真实写调用 | §7（`verify_t4.json` 校验 54/51/3 与 3 条失败均为已知缺陷） |
| 写端点执行覆盖（本轮探针） | **152 / 152 方法级 = 100%** | 每个非 GET 谓词至少被一种探针形态命中 | `api_matrix.json.coverage` |
| 带参端点「不存在 id」覆盖 | **148 条**（其中 121 条正确 404） | 哨兵 id = `999999999` | §5.3（`verify_t4.json` 复核 148/121/15） |
| CSRF 探针覆盖 | **155 / 155 非 GET 方法级 = 100%** | 缺 token 是否被拦 | §5.6（`verify_t4.json` 复核 `not_enforced=0`） |

> ⚠ 口径纪律：`271`（全量规则）/ `266`（业务规则）/ `155`（非 GET 方法级）/ `153`（非 GET 规则）
> 四个数**不能混用**；本文每个数字都标了量纲。⚠ 引用 `08` §2 的 160 时**必须**同时写明
> A-25（本轮 url_map 重算为 161）。

---

## 3. 执行方式（可复跑）

### 3.1 三条命令

```powershell
# ① 写端点数据变化断言（8 组 / 54 条）—— 每组一条独立副本，组内按序
F:\Miniconda\envs\wage\python.exe -B test-reports-2026-10/harness/write_suite.py
# ② HTTP 契约 × 权限 × CSRF 矩阵（6 个矩阵）
F:\Miniconda\envs\wage\python.exe -B test-reports-2026-10/harness/api_matrix.py
# ③ 两条缺陷的最小复现（独立副本、独立前置）
F:\Miniconda\envs\wage\python.exe -B test-reports-2026-10/harness/repro_defects.py
```

| 命令 | 退出码 | 结论 |
| --- | --- | --- |
| `write_suite.py` | **0** | 54 断言：PASS 51 / FAIL 3（3 条为产品缺陷，脚本自身无基础设施错误） |
| `api_matrix.py` | **0** | 6 矩阵跑完；71 条违规；CSRF 非豁免面 133/133 被拦（豁免 22 条） |
| `repro_defects.py` | **0** | 两条缺陷获最小复现（含 file:line 与原始 SQL 对照） |

退出码语义：这两个脚本**退出码本身不表示「测试通过」**——它们把结论写进 `evidence/api/*.json`，退出码只表示「执行完成、无基础设施级异常」（本轮实测 0）。判据读 JSON/结论段，不读退出码（对齐 `08` §5.2 对「伪门禁」的处置）。

### 3.2 沙箱隔离（**不依赖应用层保护**）

增补纪律 15 明确：**本仓不存在「应用级拒绝连真实库」的硬闸**，`_test_bootstrap.py` 只是脚本级守卫。因此本轮每一步都做了独立复核：

| 闸 | 做法 | 实测值 |
| --- | --- | --- |
| ① 副本隔离 | `fixtures.make_isolated_app()` → `_test_bootstrap.make_app(fresh=True)` 拷 `app.db` 到 `.tmp/<run>/mkdtemp/.../app.db` | `samefile(真实库)=False`（逐组打印） |
| ② URI 复核 | 每个 app 打印 `SQLALCHEMY_DATABASE_URI` 并断言不含真实库路径 | 见 `write_suite.out.txt` 组头 |
| ③ 真实库指纹 | `_env.assert_real_db_untouched()` 在每次建副本前后、每组收尾、开工/收尾各一次 | 全部 `F5DA2306…0E0F065` |
| ④ 组间状态隔离 | 每组开始把「含 7 账号 + 样本数据的原始副本」拷回，并 `db.session.remove()` + `engine.dispose()` | 每组基线行数逐组打印（`task_assignment`=18） |
| ⑤ 磁盘副作用 | 记录 `uploads/temp` 文件清单前后 | 0 文件 → 0 文件（未变） |

> **踩坑记录（供 t5/t6 复用）**：`flask_sqlalchemy 3.x` 的全局 `db` 只能 `init_app` 到一个 app ——
> 同一进程里交替使用两个 app 的 `app_context()` 会抛
> `RuntimeError: The current Flask app is not registered with this 'SQLAlchemy' instance`；
> 且 `_test_bootstrap.make_app()` 会清 `sys.modules` 里的 `app*`，因此
> **「先建 app，再 `from app import db`，再构建断言闭包」**这个顺序不能变（否则断言里的模型绑到旧实例）。
> CSRF 矩阵过去被认为「必须另起一个 app」，实际 `WTF_CSRF_ENABLED` 是**请求时读**的配置，
> 同一 app 内临时改即可 —— 这解开了「CSRF 无法在同进程实测」的死结。

---

## 4. 权限边界实测

### 4.1 匿名访问面（AC-03）——**通过**

| 类别 | 条数 | 说明 |
| --- | --- | --- |
| `allow`（匿名拿到 2xx 业务响应） | **0** | 判据核心 |
| 302 → `/auth/`（登录页） | 225 | 页面与表单型端点的正确形态 |
| 401 / 403 | 82 | JSON/写端点的正确形态（`_wants_json()`：`/api/` 前缀、`Accept: application/json`、DELETE/PUT/PATCH） |
| 404 | 1 | `/stock/__t4_probe__`（哨兵路径，未命中路由） |
| **硬违规** | **0** | —— |

**取证注意（新发现 O-1）**：Flask-Login 的登录跳转实际是 **`/auth/?next=...`**，不是 `/auth/login`。
`app/auth/routes.py:9` 把 login 同时挂在 `/login` 与 `/` 上，`login_view='auth.login'` 生成的是 `url_for` 结果 `/auth/`。
⇒ 任何**按 `'/auth/login'` 子串判断「是否跳登录页」的脚本都会误判**（本轮第一版实现即如此，把 225 条合法跳转记成违规）。
判据应写 `loc.startswith('/auth/')`。这解释了为什么本轮 `permission_matrix` 的「匿名可访问=0」与我的结论一致，但它的判据更弱（按正文判定）。

### 4.2 低权角色 × 写端点（AC-04）——**0 条越权**

| 分类 | 条数 | 判据 |
| --- | --- | --- |
| 请求总数（5 角色 × 152 写端点） | 760 | `user/sales/accountant/inspector/hr` |
| `deny`（401/403/400） | 240 | 正确拒绝 |
| `redirect`（flash+302，表单型拒绝） | 492 | 正确拒绝（AGENTS.md：页面用 flash，JSON 用 401/403） |
| `notfound` | 10 | 正确 |
| **`allow`（放行）** | **4** | **全部为设计意图**：`hr` 写 `/tasks/<id>/update_status`（含 `my_tasks.use`）、`hr` 删 `/tasks/<id>`（`task.manage`）、`sales` 删客户地址（`customer.manage`）、`sales` 删销售订单行（`sales_order.manage`）——逐一比对 `permissions.CAPABILITIES`（本轮载入 44 项）确认角色在册 |
| **越权违规** | **0** | 判据：放行者**不在**该端点所需能力登记表内才算违规 |
| `5xx` | 3 | **产品缺陷**（见 §6 缺陷 E-6：415 被包成 500） |

> 判据设计说明：不能把「低权角色被放行」一律当越权——`hr`/`sales` 在能力表里确有对应能力。
> 因此判据是「**该端点声明的 capability → 允许角色集**（运行时读 `app.permissions.CAPABILITIES`）
> 是否包含该角色」，这样才既不误报也不漏报。

### 4.3 内联 `current_user.role` 的 15 处（captain 指定必测）

captain 点名的 `routes.py:330/333/343/647/5967` + `quality.py` 10 处，逐处结论：

| # | 位置 | 性质 | 本轮实测/复核 |
| --- | --- | --- | --- |
| 1 | `routes.py:330` | 首页按角色选模板（`admin/manager` → 管理台） | `index` 匿名→302；7 角色 GET `/` 全部 200（t1 已核 265 视图无 `@login_required` 缺失） |
| 2 | `routes.py:333` | 角色→落地端点映射（`ROLE_LANDING_ENDPOINTS`） | 落地端点 5 个；`landing` 一致性由 `check_templates.py` 门禁锁（87/44/40/44/landing 5） |
| 3 | `routes.py:343` | 仅 `logger.debug` 打印（**非权限判断**） | 无权限语义；不计入「内联 role 判断」的有效集 |
| 4 | `routes.py:647` | 编辑员工时仅 `admin` 可改他人角色 | 写端点实测：`/employees/<id>/edit` 在低权矩阵中对 hr/user/sales 均拒绝（`deny`） |
| 5 | `routes.py:5967` | 手写 role 判断 | 同上：落在 `deny` 侧 |
| 6–15 | `quality.py` 10 处 | 质检员只能操作**分配给本人**的任务/记录（`start_inspection:792`、`submit_inspection_record:879` 等） | `inspector` 角色对 `/api/quality/tasks/<id>/start-inspection`、`/api/quality/records/<id>/submit` 命中 500（缺陷 E-6），但**未出现越权放行**：两条请求在到达 role 判断之前就因 415 失败，故「inspector 只能改本人任务」这一判据**本轮未取到有效断言** ⇒ 登记为**未验证**（不得计为通过） |

> 诚实标注：第 6–15 处（质检员归属校验）本轮**只测到「拒绝」的间接证据**（全仓 265 视图无匿名可达），
> **没有**构造「A 质检员的记录被 B 质检员提交 → 应 403」的归属用例。这一条属**未验证**，交 t5（UAT）承接。

---

## 5. HTTP 契约与安全矩阵（6 个矩阵逐条）

### 5.1 矩阵 A：匿名（见 §4.1）

### 5.2 矩阵 B：低权越权（见 §4.2）

### 5.3 矩阵 C：带参端点的畸形/不存在资源 —— AC-10

| 结果 | 条数 | 说明 |
| --- | --- | --- |
| 请求总数（带参端点 × 谓词，哨兵 id=999999999） | 148 | 真实 id 全部可解析（0 条退化） |
| 契约符合 | 133 | —— |
| **正确返回 404** | **121** | `get_or_404` 正常工作 |
| **返回 500** | **13** | 缺陷 E-3（`get_or_404` 的 404 被 `except Exception` 吞成 500） |
| 抛异常 | 2 | 缺陷 E-1（`NameError`）、E-6b（`TypeError`） |
| 违规合计 | 15 | JSON 12 / HTML 1 / 异常 2 |

### 5.4 矩阵 D：写端点载荷形态（空体 / 类型混淆 / 不存在的 id）—— 禁 5xx

| 结果 | 条数 | 说明 |
| --- | --- | --- |
| 请求总数 | 456 | = 152 写端点 × 3 形态 |
| `allow`（放行） | 25 | 空体/错类型下仍被接受——已抽样复核，均为「幂等的状态转移」或「校验后无副作用返回 success=false 但 2xx」，未发现数据越权（详见 JSON `matrix_d_payload.rows`） |
| **5xx** | **29** | 缺陷 E-1/E-3/E-4/E-6 的集中体现 |
| **响应正文泄漏异常类名/SQL 语句** | **12** | 缺陷 E-5：`{"message":"删除失败：(sqlite3.IntegrityError) NOT NULL constraint failed: inspection_records.task_id\n[SQL: UPDATE ...]"}` —— **原始 SQL 与异常类名回显给客户端** |
| 违规合计 | 52 | —— |
| 载荷前后逐表行数变化 | **13 张表** | 全部落在副本内（真实库未变）：`audit_log 82→110`、`purchase_requisitions 0→3`、`work_centers 0→1`、`finished_product 2→1`、`inspection_templates 1→0`、`product_bom 1→0`、`raw_material 1→0`、`raw_material_categories 1→0`、`sales_order_items 8→2`、`sales_orders 4→3`、`product_processes 3→2`、`process_assignment_rules 1→2`、`code_generation_log 25→27` |

> 上表这 13 张表的行数变化**本身就是「写端点真的在写库」的旁证**（且全部发生在副本内）。

### 5.5 矩阵 E：JSON 契约面

| 结果 | 条数 | 说明 |
| --- | --- | --- |
| `/api/` 端点 | 47 | —— |
| 可解析 JSON | 34 | —— |
| 契约违规 | **1** | `/api/quality/records/<id>/print` 200 返回 HTML（**设计即打印页**，但路径带 `/api/` 前缀 ⇒ 命名/契约不一致，判 medium） |
| 非 JSON 设计观测 | 3 | `/api/quality/records/export`、`/api/quality/tasks/export`、`/api/quality/tasks/template` —— 返回 xlsx（`vnd.openxmlformats-…sheet`），**导出端点本就非 JSON**，登记为观测不计违规 |
| 405（GET 打到了仅 POST 的端点） | 6 | Flask 默认行为，符合预期 |

> 判据明确化（本轮新增口径，供 t6 引用）：**「JSON API 不得返回 HTML」的判据应按「载体语义」分档**：
> ① 200 且 xlsx/octet-stream/pdf ⇒ 二进制下载端点，**不判违规**；
> ② 200 且 `text/html` ⇒ 判违规（契约不一致）；
> ③ 非 200 且 HTML ⇒ 看是否 5xx（5xx 归缺陷，4xx 的 HTML 错误页可接受）。
> 一刀切「/api/ 下非 JSON 即违规」会把 3 条导出端点误报成缺陷。

### 5.6 矩阵 F：CSRF 防护 —— **本轮首次实测通过**

| 项 | 值 |
| --- | --- |
| 装置 | 同一 app 内把 `app.config['WTF_CSRF_ENABLED']` 临时置 True（**请求时读取**），测完还原 |
| 正例（不变量） | `GET /tasks` = 200（CSRF 只作用于非安全方法） |
| 正例（判定装置有效性） | 从 `/system_configs` 表单页抽 `csrf_token` 后提交 ⇒ **不再 400**（实测 302） |
| 探针 | **155 个非 GET 方法级端点 × 空 body 无 token**（POST 123 / DELETE 20 / PUT 12） |
| 结果 | **被拦 133 / 豁免 22 / 未拦 0**（缺 token 的拦截形态：400 + CSRF 提示） |
| 与 AST 一致 | 20 个 `@csrf.exempt` 视图（routes 10 / quality 6 / production_center 3 / equipment 1；`stock.py:81` 的 1 处是**注释里说明「已删除」**，不是装饰器）覆盖 **22 个方法级端点**（`manage_template`、`manage_task` 各为 PUT+DELETE 双谓词）⇒ 155 = 133 拦 + 22 豁免；**豁免清单无超发、非豁免面零遗漏** |
| 违规 | **0** |

> 这一条直接闭合 `08` §5.3 的「CSRF 从未验证」缺口与 t2 的 O-2（blocked）。
> 结论措辞限定：**证明的是「缺 token 时非 GET 请求被拒」**；不证明「交叉站点全场景防御」（同站点 cookie、SameSite、token 重放等未测，见 §9）。
> 附一条方法学证据：`/tasks` 页面的 HTML 里**没有** `name="csrf_token"` 隐藏域（692 KB 页面实测 0 处），
> 说明表单页走的是 `base.html` 的 `$.ajaxSetup` **请求头注入** token —— 这也解释了为什么
> `@csrf.exempt` 只白名单了 JSON/AJAX 端点，而纯 HTML 表单端点仍受保护。

### 5.7 独立复核（第三方可复跑）—— `harness/verify_t4.py`

为满足「结论不得只有作者自证」的要求，本轮额外写了一个**只读复核脚本**：它**不依赖** `api_matrix`/`write_suite` 的中间结论，只读交付文档、两个 JSON、生产源码与真实库指纹，并**另起一个副本 app 独立重算**分母与 CSRF 正例。

| 项 | 值 |
| --- | --- |
| 复核项数 | **44** |
| 通过 | **44 / 44** |
| 复核内容 | ① 真实库 SHA256；② 交付文档行数/字节/SHA256（A-23 `splitlines` 口径）；③ `api_matrix.json` 的 71/0/3/148-121-15/456-29-12/1/155 逐项；④ `write_suite.json` 的 54/51/3 与「3 条失败 id == 已知缺陷」；⑤ 5 条源码 `file:line` 断言（含 `routes.py` 顶部 import 无 `Consumable`、`quality.py:408`、`mes_service.py:326`）；⑥ 独立 CSRF 正例（`/system_configs` 取真 token → 提交 302；缺 token → 400）+ AST 豁免面互证；⑦ 分母独立重算（271 / 266 / 156 / 152 / 142） |
| 复核产物 | `evidence/api/verify_t4.json` |

> 本节数字为 `verify_t4.py` 的执行结果（44/44）；文档尾部仅追加了本节与索引，
> 不影响任何被复核的数字。最终版行数/字节/SHA256 见文首「交付物」行（A-23 口径：467 行 / 42,836 B）。

| # | 原引用 | 复核实测 | 处置 |
| --- | --- | --- | --- |
| V-1 | 「CSRF 豁免 21 处（含 stock 1 处）」 | 装饰器实为 **20 处**；`stock.py:81` 的那处是**注释里说明「已删除」**（grep 命中但非装饰器） | 已按 20 视图 / 22 方法级端点改写（§5.6） |
| V-2 | 矩阵 D「载荷前后仅 1 张表行数变化」 | 实测 **13 张表** | 已在 §5.4 逐表列出 |
| V-3 | 文档中「delta 证据覆盖率 52/54」隐含「全为字段级对照」 | 实测字段级对照 21 条、新建/删除型 31 条（值来自库查询） | 已在 §7 分列两种证据形态 |

---

## 6. 缺陷清单（分级 + 归属 + 判别依据）

**判级口径**：`blocker` 端点恒不可用或安全面失守；`high` 功能在常见路径上不可用/错误的成功语义；`medium` 契约不一致或可读性缺陷；`low` 命名/提示类。每条都给出「为什么不是夹具/脚手架问题」。

### E-1 `Consumable` 未导入 ⇒ 两个易耗品写端点**恒 500**（功能完全不可用）

| 项 | 内容 |
| --- | --- |
| 级别 | **blocker** |
| 证据（HTTP） | `POST /consumables/<id>/use` → **500**（`defect_repro.out.txt`：库存 10.0 → 10.0 **未扣**）；`DELETE /consumables/<id>` → **500** |
| 证据（源码） | `app/main/routes.py:10943` `consumable = Consumable.query.get_or_404(id)` —— 该函数作用域内**没有** `Consumable`；模块顶部 import（`:6`）的清单里**没有** `Consumable`，只有 `:10555`/`:10683`/`:10786` **三处函数内**导入 |
| 证据（traceback） | `NameError: name 'Consumable' is not defined`（`repro_defects.out.txt` 完整栈） |
| 判别依据 | **产品缺陷**：副本内可复现；`direct view call` 同样抛出；与夹具无关（前置行由夹具显式建好且 `quantity=10/50`）；拒绝时未产生半成品（守恒成立）——**是「端点根本没有可能成功」，不是数据问题 |
| 影响面 | 易耗品「领用扣减 / 删除」两条主路径不可用；`/consumables/inbound`、`PUT /consumables/<id>` 正常（它们有自己的函数内导入） |
| 建议 | 与 GAP 体系对齐：新增 `REQ-O-*`（工程正确性）项；修复＝在 `routes.py` 顶部 import 补 `Consumable`（**或**在 `use_consumable`/`delete_consumable` 内显式导入，与同文件其他 3 处保持一致） |

### E-2 `/tasks/<id>/edit` 的 `notes` 入参被静默丢弃，且审计 old/new 相同

| 项 | 内容 |
| --- | --- |
| 级别 | **high** |
| 证据（HTTP） | `POST /tasks/<id>/edit`（body 含 `"notes": "NEW_NOTES"`）→ 200 `{"success":true}`；`quantity`、`status`、`target_date` 均正确落库 |
| 证据（库内） | 原始 SQL 直读：`notes='OLD_NOTES'`（**未变**）；`defect_repro.json.cases.edit_notes.db_notes_after_edit='OLD_NOTES'` |
| 证据（源码） | `routes.py:4502-4506` 只赋值 `target_date`/`employee_id`/`process_id`/`quantity` ——**没有任何 `task.notes = ...`**；而 `:4497`（old_data）与 `:4532`（new_data）都把 `task.notes` 当「已更新的值」写进审计 ⇒ `new_data.notes == old_data.notes == 'OLD_NOTES'` |
| 判别依据 | **产品缺陷**：响应 `success:true` 却无对应落库（「静默成功」）；审计回滚数据因此与事实不符（回滚会「回滚到同一个值」）。**不是 ORM 问题**：同一进程直接 `row.notes = 'DIRECT_SET'` + commit 后读回正确（repro 输出最后一行） |
| 影响面 | 任务备注无法编辑；`AuditLog` 的 `can_rollback=True` 回滚元数据失真 |
| 建议 | 修复＝补 `task.notes = data.get('notes', task.notes)`；并加一条「响应声明成功 ⇒ 该字段必须变化」的断言（本文件 §7 已提供用例形态） |

### E-3 `get_or_404` 的 404 被 `except Exception` 吞成 **500**（11 组端点）

| 项 | 内容 |
| --- | --- |
| 级别 | **high**（JSON API 语义错误：客户端无法区分「资源不存在」与「服务器故障」） |
| 证据 | `PUT/DELETE /api/quality/templates/<id>`、`PUT/DELETE /api/quality/tasks/<id>`、`POST /api/quality/tasks/<id>/start-inspection`、`POST /api/quality/records/<id>/submit`、`GET /api/quality/records/<id>`、`GET /api/quality/records/<id>/print`、`POST /api/production_center/items/<id>/tech_decomposition`、`GET /api/production_center/items/<id>/detail`、`POST /api/production_center/items/<id>/execute_operation`、`POST /api/process_assignment/<id>` 全部 **500**，正文形如 `{"message":"操作失败：404 Not Found: The requested URL was not found…"}` |
| 证据（源码） | `app/main/quality.py:336/773/871/993/1040/1225`、`app/main/production_center.py:178/225/304`、`app/main/routes.py:184` 的 `get_or_404` 处在 `try/except Exception` 内；`app/main/routes.py` 有 `_reraise_http(e)` 这类正确写法（如 `:8148`），但这 11 处**没有调用** |
| 判别依据 | **产品缺陷**：`GET /api/quality/records/999999999`（**GET，无副作用、无 body**）也返回 500，排除「载荷/夹具」因素；副本内稳定复现 |
| 对照 | 121 条带参端点**正确**返回 404 ⇒ 说明这是一个**可修的选择性缺陷**，不是框架限制 |
| 建议 | 对齐 `_reraise_http` 模式：`except HTTPException: raise`（或统一装饰器） |

### E-4 `DELETE /api/quality/tasks/<id>` 触发 NOT NULL 约束 ⇒ 500 + 回显原始 SQL

| 项 | 内容 |
| --- | --- |
| 级别 | **high** |
| 证据（HTTP） | 500，正文：`{"message":"删除失败：(sqlite3.IntegrityError) NOT NULL constraint failed: inspection_records.task_id\n[SQL: UPDATE inspection_records SET task_id=? WHERE inspection_records.id = ?\n[parameters: (None, 1)]", "success":false}` |
| 证据（源码） | `quality.py:1024` `db.session.delete(task)`；`inspection_records.task_id` 是 NOT NULL；关联记录未先删 ⇒ SQLAlchemy 试图置 NULL |
| 判别依据 | **产品缺陷**：触发条件是「**已存在关联质检记录**的任务被删除」——这是正常业务操作（本组断言先 `start-inspection` 生成了记录再删），不是畸形输入；且 `status='pending'` 的任务按 `:997` 的规则**是允许删除的**，实现却删不掉 |
| 附带问题 | 把 `sqlite3.IntegrityError`、完整 SQL、绑定参数回显给客户端 ⇒ 缺陷 E-5 |
| 建议 | 删任务前先删/拒绝关联记录，并返回 400 可读原因；错误响应统一脱敏 |

### E-5 错误响应泄漏异常类名 / 原始 SQL（信息泄漏面）

| 项 | 内容 |
| --- | --- |
| 级别 | **medium**（安全面信息泄漏；同属「契约」而非「功能」） |
| 证据 | 矩阵 D：456 条请求中 **12 条**响应正文命中 `(sqlite3.*Error\|NOT NULL constraint\|[SQL:\|IntegrityError)`；模板：`{"success":false,"message":"…失败：(sqlite3.IntegrityError) NOT NULL constraint failed: xxx.yyy\n[SQL: UPDATE …]\n[parameters: …]"}` |
| 判别依据 | **产品缺陷**（一致的错误处理缺失）：多条 `except Exception as e: return jsonify({'message': f'…：{str(e)}'})` 模式（如 `quality.py:1034`、`routes.py:4446`）直接拼接底层异常 |
| 建议 | 统一错误出口：对外只给「可读原因 + 错误码」，异常详情只进 `current_app.logger`；并加一条「响应正文不得含 `sqlite3.`/`[SQL:`」的可自动化断言（本轮矩阵 D 的 `error_text_leak` 判据可直接复用，t6 可将其并入门禁） |

### E-6 把 4xx 语义的异常包成 **500**（415 / KeyError 两类）

| 子项 | 证据 | 级别 |
| --- | --- | --- |
| **E-6a 415 → 500** | 对仅接受 JSON 的端点发 `Content-Type: application/x-www-form-urlencoded`（矩阵 D1 空表单体）⇒ `get_json()` 抛 415，被 `except Exception` 包成 **500** + `{"message":"…失败：415 Unsupported Media Type…"}`。命中：`/tasks/add`、`/api/quality/{templates,tasks}`、`/api/quality/records/<id>/submit`、`/api/quality/tasks/<id>/start-inspection`、`/api/quality/tasks/<id>`、`/api/process_assignment/<id>`、`/api/process_assignment/bulk`、`/api/production_center/{create_instances,items/<id>/tech_decomposition,items/<id>/execute_operation}`、`/audit_logs/rollback/<id>`（共 15 条唯一组合，矩阵 B 的 3 条 5xx 亦属此类） | **medium** |
| **E-6b KeyError → 500** | ① `PUT /api/quality/templates/<id>` **部分字段更新**（只给 `{"is_active": false}`）⇒ 500 `操作失败：'template_code'`（`quality.py:408-410` 用 `data['template_code']` 下标取值）；**库未被改动**（`is_active` 仍 True，行数不变）——即「拒绝是对的，但出口错」。② `POST /api/quality/tasks` 带 `{"type": "x"}` ⇒ 500 `创建失败：'type'`（`quality.py:588` `data['type']`） | **medium** |
| 判别依据 | **产品缺陷**：客户端发的是**合法 HTTP 请求**（只是字段不全/类型不对），期望 4xx + 可读原因；实测 500 + 异常 repr。端点的「拒绝意图」在 E-6b① 里已被证明存在（库不变），所以不是「业务允许」的问题 |
| 建议 | ① JSON 端点统一 `request.get_json(silent=True)` + 空 body 校验（返回 400/415 而非 500）；② 改为 `data.get('template_code', template.template_code)` 之类「部分更新」语义，或显式 400 声明必填 |

### E-7 路径/载体契约不一致（low）

| 子项 | 证据 | 级别 |
| --- | --- | --- |
| `/api/quality/records/<id>/print` 200 返回 `text/html` | 矩阵 E；但它是「打印页」设计 ⇒ 属命名/契约不一致 | low |
| `/api/quality/{records,tasks}/export`、`/api/quality/tasks/template` 在 `/api/` 下返回 xlsx | 矩阵 E（登记为观测，不计违规） | low（观测） |
| `/api/quality/records/<id>/print` 还会把 404 吞成 500 | 同 E-3 | high（已并入 E-3） |

---

## 7. 写断言台账（54 条，全部落在数据变化上）

**判据形态**：每条断言自己记录请求前后的**库内字段值**（`Δ label.field: before -> after`），
`check()` 判的是**库里的值**（`status`/`quantity`/`is_active`/`result`/行数增减…），
状态码只作辅助证据。证据落 `evidence/api/write_suite.json`（含每条 `checks[]`、`db_delta`、`response`）。

| 域 | 断言 id | 断言 | 结果 | 关键 Δ（库存值） |
| --- | --- | --- | --- | --- |
| tasks | W-TASK-1 | `POST /tasks/add` 新增任务 | PASS | 新行 `quantity=7 status=pending target_date=2026-12-31`；审计新增 |
| tasks | W-TASK-2 | `POST /tasks/<id>/update_status` 完工 | PASS | `status: pending→completed`；`completed_at` 回填；`production_record` 按 `global_sn` 落库 |
| tasks | W-TASK-3 | `POST /tasks/<id>/edit` | **FAIL** | **E-2**：`notes` 未落库（`quantity`/`status` 正常） |
| tasks | W-TASK-4 | `DELETE /tasks/<id>` | PASS | `task_assignment` 行数 −1 |
| tasks | W-TASK-5 | 不存在的任务 → 404 JSON | PASS | 无副作用 |
| tasks | W-TASK-6 | 超量 9999 → 400 且库不变 | PASS | `status/quantity` 未变 |
| inventory | W-INV-1 | `POST /inventory/finished/add` | PASS | 新成品行 `status=in_stock` |
| inventory | W-INV-2 | `PUT /inventory/finished/<id>` | PASS | `quantity: 5→9`；`status: in_stock→shipped` |
| inventory | W-INV-3 | `POST /inventory/raw/add` | PASS | `quantity=12.5`；`category_id` 落库 |
| inventory | W-INV-4 | `PUT /inventory/raw/<id>` | PASS | `quantity: 12.5→3.25` |
| inventory | W-INV-5 | `POST /inventory/raw/<id>/archive` | PASS | `is_archived: False→True` |
| inventory | W-INV-6 | `DELETE /inventory/raw/<id>` | PASS | `raw_material` 行数 −1 |
| inventory | W-INV-7 | `POST /consumables/<id>/use` | **FAIL** | **E-1**：`quantity` 10→10（未扣）+ 500 |
| inventory | W-INV-8 | `PUT /consumables/<id>` | PASS | `specification`、`unit_price: →7.5` |
| inventory | W-INV-9 | `POST /inventory/raw-material/categories/add` | PASS | 品类新行 |
| inventory | W-INV-10 | 领用 → 发料 | PASS | 易耗品 `quantity: 50→48`；领用单 `status: approved→completed` |
| inventory | W-INV-11 | `POST /inventory/raw-material/inbound` 批量入库 | PASS | 新原料行 `quantity=4.0` |
| quality | W-QLT-1 | `POST /api/quality/templates` | PASS | 模板 + 基础项各落 1 行 |
| quality | W-QLT-2 | `PUT /api/quality/templates/<id>` 全字段 | PASS | `is_active: True→False`；`name` 更新 |
| quality | W-QLT-3 | ★ 部分字段 PUT | **FAIL** | **E-6b①**：500；`is_active` 未变（拒绝但出口错） |
| quality | W-QLT-4 | `DELETE` 未被引用的模板 | PASS | 模板行 −1 |
| quality | W-QLT-5 | `POST /api/quality/tasks` | PASS | 任务 `status=pending priority=2 inspector_id` 落库 |
| quality | W-QLT-6 | `PUT /api/quality/tasks/<id>` | PASS | `notes` 落库；`status` 被该端点忽略（实现如此） |
| quality | W-QLT-7 | `start-inspection` | PASS | 任务 `pending→in_progress`；质检记录落库 |
| quality | W-QLT-8 | `records/<id>/submit` | PASS | 记录 `result: pending→pass`；任务 `→completed` |
| quality | W-QLT-9 | `DELETE /api/quality/tasks/<id>` | PASS | 任务行 −1（本探针的任务未产生质检记录） |
| quality | W-QLT-10 | 阴性：重复 `template_code` | PASS | 400 且模板行数不变 |
| production | W-PRD-1 | `POST /production_orders/add` | PASS | 新生产单 `planned_quantity=5 status=pending` |
| production | W-PRD-2 | `POST /production_orders/<id>/batches/add` | PASS | 批次 `batch_quantity=5` |
| production | W-PRD-3 | `PUT /production_batches/<id>/status` | PASS | `status: →in_progress` |
| production | W-PRD-4 | `PUT /production_batch_items/<id>/update` | PASS | `quality_status: pending→fail`（**唯一写入点** `routes.py:8899`） |
| production | W-PRD-5 | `DELETE /production_orders/<id>` | PASS | 生产单行 −1 |
| purchase | W-PUR-1 | `POST /suppliers/save` | PASS | 供应商新行 |
| purchase | W-PUR-2 | `POST /purchase_requisitions/save` | PASS | 请购单新行 |
| purchase | W-PUR-3 | `POST /purchase_requisitions/<id>/approve` | PASS | `status` 变化 |
| purchase | W-PUR-4 | `POST /purchase_orders/save` | PASS | 采购单 + 明细各落库；`supplier_id` 正确 |
| purchase | W-PUR-5 | `POST /purchase_orders/<id>/receive` | PASS | `goods_receipt` 行 +1 |
| shipping | W-SHP-1 | `POST /shipments/create` | PASS | 发货单新行 `status=draft` |
| shipping | W-SHP-2 | `POST /shipments/<id>/add_item` | PASS | 发货明细行 +1 |
| shipping | W-SHP-3 | `POST /shipments/<id>/ship` | PASS | 发货单 `status: draft→shipped` |
| shipping | W-SHP-4 | `POST /shipments/<id>/sign` | PASS | `ShipmentReceipt` 行 +1；`signed_by_name` 落库；`status→signed` |
| equipment | W-EQP-1 | `POST /equipment/save` 新建 | PASS | 设备新行（`length_mm=1000`） |
| equipment | W-EQP-2 | `POST /equipment/save` 带 id 更新 | PASS | `name`、`status: →idle` 落库 |
| equipment | W-EQP-3 | `POST /equipment/<id>/downtime` | PASS | `status→maintenance`；停机记录 +1 |
| equipment | W-EQP-4 | `POST /equipment/<id>/resume` | PASS | `status→running` |
| equipment | W-EQP-5 | `POST /heat_lots/create` | PASS | 炉次新行 |
| equipment | W-EQP-6 | `POST /heat_lots/<id>/fire` | PASS | 炉次 `status` 变化 |
| misc | W-MSC-1 | `POST /customer/add` | PASS | 客户新行（`customer_name` 落库） |
| misc | W-MSC-2 | `POST /products/add` | PASS | 产品新行（`unit=件`） |
| misc | W-MSC-3 | `PUT /products/<id>` | PASS | `product_name`、`specification` 落库 |
| misc | W-MSC-4 | `POST /products/<id>/bom/add` | PASS | `product_bom` 行 +1 |
| misc | W-MSC-5 | `POST /products/<id>/processes/add` | PASS | `product_process` 行 +1 |
| misc | W-MSC-6 | `POST /code_rules/add` | PASS | 编码规则新行（`prefix` 落库） |
| misc | W-MSC-7 | `POST /notifications/<id>/read` | PASS | `notification_receivers.status: unread→read` + `read_at` 回填 |

**覆盖统计（口径：不同写端点规则数）**

| 项 | 值 |
| --- | --- |
| 断言条数 | **54** |
| 覆盖的不同写端点（规则） | **46**（命中 URL 去重后 50 个） |
| 覆盖的写域 | 8 组（tasks / inventory / quality / production / purchase / shipping / equipment / misc） |
| 其中「数据变化」被显式证明 | **52 / 54**；判据证据形态两分：**21 条**走「同对象字段前后对照」（`Δ label.field: before -> after`），**31 条**走「新建/删除后的库内值 + 行数」（`checks` 内的 `库内出现该行`/`quantity=…`/`行数减少 1` 等，值来自库查询而非响应体） |
| 每条的 check 条数 | 合计 **176** 条 check（54 条断言） |
| 相对基线（`functional_test` 字面量 6 条 / 153 规则） | 本轮把「有数据变化断言」的写端点从 **6 → 46**（+40 个） |

> captain 要求「≥30 条真实写断言」：**54 条通过执行、46 个端点**，达标。

---

## 8. 与阶段一/阶段二既有结论的对账

| 既有结论 | 本轮实测 | 关系 |
| --- | --- | --- |
| `08` §5.3「CSRF 从未验证」、t2 O-2「blocked」 | 非豁免面 133/133 被拦 + 22 条命中豁免白名单，未拦 0 | **闭合**（口径限定见 §5.6） |
| `08` §5.3「非 GET 方法级 155」 | 重算 155（152 有写谓词 + 3 只在 GET/POST 混合规则里）| **一致** |
| A-25「方法级 GET 161 vs 08 记 160」 | 本轮 161 | **一致（以 161 为准并标注）** |
| A-11「写仓库根 JSON 被拒 ⇒ exit 1 非断言失败」 | 本轮脚本全部改写到 `test-reports-2026-10/`，**未触碰仓库根 JSON**（`git status` 无新改写） | **遵守** |
| 登记册 A-3「门禁有多重拒绝路径但缺触发数据」 | 本轮复证 `mes_service.py:326` 实参只有 `batch_item`/`workpieces`（**无 `production_record`**）| **一致**（`defect_repro.out.txt` 第 ③ 段） |
| `permission_matrix`「匿名可访问=0」 | 一致（0 条），但其判据按正文匹配，**未覆盖 401/403 的 JSON 形态**；本轮按状态码 + 形态分类 | **加强** |
| 02 §8「写端点分母 155/153，字面覆盖 6 条」 | 一致；本轮把「有真实数据变化的断言」覆盖推到 46 个端点 | **加强（补上分母缺口）** |

---

## 9. 未执行 / 未验证 / 不可判定（**不得计为通过**）

| # | 项 | 状态 | 原因与交接 |
| --- | --- | --- | --- |
| U-1 | 质检员**归属**校验（A 质检员提交 B 的记录应 403） | **未验证** | 请求先因 E-6a（415→500）失败，未走到 role 判断；需先修 E-6 或改用正确 JSON 形态复测 → t5 |
| U-2 | 并发 / 幂等（同一写端点串发两次） | **未测** | 单线程 test_client；属 02 §8 P2-5，未在本任务范围 |
| U-3 | 性能 / 超时 / 大载荷 | **未测** | 同上 |
| U-4 | 安全头（CSP/HSTS/X-Frame-Options） | **未测** | 未在任务书范围；`smoke_test` 也不测 |
| U-5 | CSRF 全场景（SameSite、token 重放、跨站表单实际浏览器行为） | **部分** | 本轮只证明「缺 token 被拒」；不证明端到端浏览器场景 |
| U-6 | 生产部署形态（多进程 / WSGI 分叉 / 反向代理路径重写） | **未测** | 只在 `app.test_client()` 与单进程 app 内实测；`/auth/` 重定向形态（O-1）在反向代理下可能不同 |
| U-7 | 前后端 JS 的 `$.ajaxSetup` CSRF 头链路 | **未测** | 需浏览器/JS 环境；本轮为后端视角 |
| U-8 | 文件上传类端点（`*/import`）的人工坏行容错 | **未测** | 需要真实 xlsx 载荷；属 K 域（`functional_test` 有部分覆盖，本轮不复算） |
| U-9 | `/api/quality/records/export` 等 3 个二进制下载端点的内容正确性 | **未测** | 本轮只判载体类型（观测），未校验 xlsx 内容 |
| U-10 | E-3 的 11 组 500 中，「目标行确实不存在时」的**客户端可恢复性** | **未判定** | 是否所有调用方都能容忍 500 需要前端取证；本轮只判「语义应为 404」 |
| U-11 | `/tasks/add` 的**表单页**行为 | **不适用** | 实测 `GET /tasks/add` = **405**（该端点是 JSON-only，表单页在 `GET /tasks`）；若前端某处按「表单页」链接它，是前端契约问题，本轮未查前端 |
| U-12 | 前端 `$.ajaxSetup` CSRF 头注入的端到端链路 | **未测** | 已取证「HTML 里无 hidden token ⇒ 靠请求头注入」，但未在浏览器环境验证该头确实被带上 |

---

## 10. 复跑与独立复核指引

1. **复跑三条命令**（§3.1）→ 比对 `write_suite.json.passed/failed`＝51/3、`api_matrix.json.violations_total`＝71、CSRF `not_enforced=0`。
2. **真实库零改动**：`Get-FileHash app.db -Algorithm SHA256` 应为 `F5DA2306…0E0F065`（本轮开工/收尾两次均如此，脚本内还有 8 次自动复核）。
3. **逐条复算任一写断言**：在 `write_suite.json.results[i].probe_prefix`（如 `t410062233_quality`）下，于同组副本内按该断言 `response.url` + `checks[]` 复核库内值。
4. **复核 E-1/E-2**：跑 `harness/repro_defects.py`，看 `[①] 原始 SQL: … notes='OLD_NOTES'` 与 `[②] POST /consumables/2/use -> HTTP 500` + `NameError` 栈。
5. **复核 CSRF**：`api_matrix.json.matrix_f_csrf.summary` 应为 `{probed:155, enforced_or_exempt:155, not_enforced:0}`，且 `positive_control.verdict` 为「判定装置有效」。
6. **一条命令复核全部数字**：`F:\Miniconda\envs\wage\python.exe -B test-reports-2026-10/harness/verify_t4.py`
   ⇒ 应输出 `独立复核：44/44 通过`，并落 `evidence/api/verify_t4.json`（0 条 FAIL）。

### 证据文件索引

| 文件 | 内容 | 字节 |
| --- | --- | --- |
| `evidence/api/api_matrix.json` | 机读全量：端点清单 + A–F 六矩阵逐行 + 违规 + 覆盖分母 | 1,342,834 |
| `evidence/api/api_matrix.out.txt` | 人读日志（含每组汇总与 71 条违规摘要） | 8,195 |
| `evidence/api/write_suite.json` | 54 条写断言的 `checks`/`db_delta`/`response` + 每组逐表行数 | 73,292 |
| `evidence/api/write_suite.out.txt` | 人读日志（逐条 PASS/FAIL + Δ） | 23,028 |
| `evidence/api/defect_repro.json` / `.out.txt` | E-1/E-2 最小复现 + 真实库指纹 + 门禁调用点 AST 取证 | 1,346 / 4,205 |
| `evidence/api/non_get_inventory.json` / `.txt` | 152 个非 GET 视图的 `file:line` + 守卫 + 读取的请求键（选型依据） | 48,720 / 24,092 |
| `evidence/api/verify_t4.json` | 独立复核 44 项逐条（含分母重算与 CSRF 正例） | 见文件 |
| `evidence/api/recon_non_get.py` | 上述清单的生成脚本（只读 AST） | 4,405 |

### 本轮新增脚本（均在 `test-reports-2026-10/harness/`，未改 `scripts/` 既有脚本）

| 文件 | 作用 |
| --- | --- |
| `harness/api_matrix.py` | A–F 六矩阵（匿名 / 低权越权 / 畸形 URL / 载荷安全 / JSON 契约 / CSRF） |
| `harness/write_suite.py` | 54 条数据变化写断言（8 组，组间文件级副本重置） |
| `harness/repro_defects.py` | E-1/E-2 最小复现 |
| `harness/verify_t4.py` | 独立复核（44 项；只读交付物 + 另起副本重算分母与 CSRF 正例） |
| `harness/preflight_fields.py` | 断言用到的模型字段/关系预检（防拼错字段导致假失败） |

---

## 11. 给下游（t5 / t6 / t7）的接口

| 下游 | 可直接引用 |
| --- | --- |
| **t5（UAT）** | ① 写断言台账 §7 的 8 组夹具形态与「Δ 判据」写法可直接复用（`harness/write_suite.py:prepare_env` 提供每域前置）；② U-1（质检员归属）必须由端到端补；③ 三条链（采购/发货/料账）的**前置夹具**已在本轮验证可用（`stock_kind='fg'` 注入后发货候选可见） |
| **t6（分析/分级）** | 7 类缺陷（§6）已带 `blocker/high/medium/low` 判级、`file:line`、判别依据与「为什么不是夹具问题」；`api_matrix.json.violations` 提供 71 条可机读原始条目（含 `severity`/`kind`） |
| **t7（改进）** | 修复建议已逐条给出（E-1 补 import；E-2 补一行赋值；E-3 统一 `HTTPException` 直抛；E-4 先删关联记录；E-5 统一错误脱敏；E-6 用 `get_json(silent=True)` + 显式 400）。另建议把「响应正文不得含 `sqlite3.`/`[SQL:`」「JSON 端点空体应 4xx 不应 5xx」两条并入**可自动化门禁**（判据已在本轮矩阵 D 实现） |
| **t8（总报告）** | §1 结论摘要 6 行可直接入总报告；口径三要素（271/155/153）与「行数用 `splitlines()`」须随文标注 |

---

*本文件所有数字均来自本轮实跑（2026-10-06），不含转述；凡「未测/未验证」项已在 §9 显式登记，未计为通过。*
