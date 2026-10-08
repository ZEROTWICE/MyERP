# Captain 仲裁件（跨领域稿冲突的裁定）

> 作者：captain（主理人）｜时点：2026-10-08｜工作目录：`D:\workspace\wage_management_system - bak`
> 用途：`recon-arch.md` / `recon-backend.md` / `recon-frontend.md` / `recon-requirements.md` / `recon-product.md` / `recon-docs.md` 之间出现**互相矛盾**的结论时，以本文件为准。
> 规则：本件每条裁定都必须给**可复核的源码证据链**；凡不能裁定的（属业务口径）一律标「须用户拍板」，**不由 agent 代替拍板**。
> 本件**不得**被用作新增事实来源——它只是冲突的裁定与口径钉死。

---

## A-1 Bootstrap 5 是否走 CDN？（裁定：**走 CDN**；`recon-frontend.md` §K-4「无 CDN」在此点上不成立）

**冲突**：`recon-frontend.md` §K-4 写「base.html 经 url_for 引入 Bootstrap5(:9,:544) …… **无 CDN**」；撤销件架构师取证写「`Bootstrap5()` 走 CDN（`BOOTSTRAP_SERVE_LOCAL` 全仓未设）」。

**裁定：架构师取证正确，`recon-frontend.md` 此处应视为已订正。**

**证据链（三层，逐层可复跑）**：

1. 全仓 grep `BOOTSTRAP_SERVE_LOCAL` → **命中 0 处**（`app/**/*.py`、`config.py` 均无）；
2. `flask_bootstrap/__init__.py:76`：`app.config.setdefault('BOOTSTRAP_SERVE_LOCAL', False)` —— 扩展在导入期即把默认值置为 `False`；
3. `flask_bootstrap/__init__.py:102` 读取该配置 → `:108 if serve_local:`（**本地分支**，走 `url_for('bootstrap.static', ...)`）→ `:114 else:`（**CDN 分支**，`base_path = f'{CDN_BASE}/bootstrap@{version}/dist/css'`，`:119` 拼出 CDN URL）；`:173` 的 `... and serve_local is False` 进一步印证默认态即 CDN。

**结论与影响**：`base.html:9 {{ bootstrap.load_css() }}` 与 `base.html:544 {{ bootstrap.load_js() }}` 会输出 **jsdelivr CDN** 链接 ⇒ **Bootstrap 5 核心 CSS/JS 依赖公网可达**。
`base.html` 中**确实**走 `url_for` 的是**其它**资产：bootstrap-icons（`:11`/`:13`）、select2 主题（`:16`）、jQuery 3.6.0（`:545`）、Toastr/Select2/SweetAlert2（`:546-548`）、jsQR（`:549`）。
⇒ 「无 CDN」的说法只对这些资产成立，**对 Bootstrap 核心不成立**。
⇒ **必须登记为内网/离线部署风险**（离线环境下页面将丢失 Bootstrap 核心样式与 JS），不得据 `recon-frontend.md` §K-4 判为无风险。

---

## A-2 模板能力调用数到底是多少？（裁定：**`can('cap')` 101 处 / 32 文件；`can_any(` 7 处 / 2 文件**）

**冲突**：`recon-frontend.md` §K-1 写「`can('cap')` 101 处 / 32 模板，`can_any()` 7 处」；撤销件架构师取证写「`can(` 110 处 / 28 文件」。

**裁定：`recon-frontend.md` 正确。「110 / 28」不得进入最终交付。**

**证据（`-AllMatches` 精确计数，避免按行计数与子串污染）**：

| 口径 | 真实出现 | 文件数 |
| --- | --- | --- |
| `can('`（Jinja 字符串字面量参数） | **101** | **32** |
| `can("` | 0 | 0 |
| `can_any(` | **7** | 2 |
| `can(`（宽松正则） | 110 | 34 —— **含假阳性** |

**假阳性来源（为什么 110/34 是错的）**：`can(` 会命中 JS 函数名 `openQrScan(` / `stopQrScan(`（如 `my_tasks.html:96/129/147/363/437/451/501`），以及 `base.html:550` 的注释文本 「`can() 过滤后的服务端渲染结果`」。
⇒ 引用模板能力调用数时**必须**写成：「`can('cap')` **101 处 / 32 个模板** + `can_any()` **7 处**（口径：Jinja 字符串字面量参数）」，并与门禁口径 `44 declared / 40 used in templates / 44 used on routes` 分开表述（**两者不是同一量纲**）。

---

## A-3 ⚠ 须用户拍板，agent 不得代替决定：报工路径是否补传 `production_record`

**冲突**：`recon-backend.md`（B4-02 结构发现）建议「报工路径补传 `production_record`」以让「有在办质检任务 / 未闭环 NC」两条拒绝路径在报工链可达；`recon-requirements.md` 指出这会**直接违反 `REQ-E-07` 的既有口径**——「本次报工自建的质检任务**不作**本次入库门禁依据」（该口径今日实测成立：`routes.py:3705-3717` 调用门禁时**不传** `production_record`，`:3705-3717` + `mes_service.py:351`）。

**裁定：不裁定。这是业务口径二选一，属用户决策项。**

- 现状口径（`REQ-E-07`）下：报工链的门禁**只能**依赖 `quality_status` 回写（即 B4-03 的路子），该路子今日实测**已成立**（fail 回写 ⇒ 门禁拒；处置 done ⇒ 恢复放行）。
- 若改为补传 `production_record`：会**静默打破** `REQ-E-07` 第二句，且需同步改 `04-业务验收标准与端到端判据.md` 的口径。
- ⇒ 规划（`81-`）必须以「**须拍板项**」列出，并给出默认路径（维持现状口径 + `quality_status` 回写），**不得**由任一领域稿单方面建议即视为结论。

---

## A-4 一处数字笔误（不影响结论，供 `80-`/`81-` 引用时订正）

`recon-frontend.md` 只读纪律段落写 `app.db 3521328→2531328`，其中 `3521328` 为笔误；真库正确值为 **2531328** 字节 / `F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065` / mtime `2026-09-18 12:50:55`（与 `00-共享事实底盘.md` §1 逐字一致，三次复核未变）。

---

## A-5 引用纪律（对 `80-`/`81-`/复核件的强制要求）

1. **同一事实不得出现两个数**：凡涉及「路由数 / 模板数 / 能力数 / 内联 role 数 / `can()` 数 / `_ENSURED_COLUMNS` 列数 / create_all 表数」等，**必须连口径一起写**（口径分歧的历史见 `00-共享事实底盘.md` §6）。
2. **`file_exists` 级证据不判「已实现」**（沿用第二轮 70- 的判定档位）。
3. **不得把 `blocked` 折算为 pass**（A-63 第二步构建层晋升、C-07 实现）。
4. 领域稿之间的任何冲突，**以本件为准**；本件未覆盖的新冲突，由 captain 追加 A-6… 而非由下游稿各行其是。

---

## A-6 `app/main` 含 `@bp.route` 的模块数（裁定：**7 个模块 / 265 条**；计划 B9-16 要求的订正值「8 个」**本身是错的**）

**冲突**：`recon-arch.md` §1.2 写「8 个」；`recon-docs.md` 写「7 个」；`80-` 登记为 N-A1。

**裁定：`app/main` = 7 个模块 / 265 条**（captain 本轮 AST 独立复算，与 `80-` 的实测一致）：

| 模块 | `@bp.route` 条数 |
| --- | --- |
| `routes.py` | 192 |
| `quality.py` | 27 |
| `equipment.py` | 15 |
| `purchase.py` | 13 |
| `production_center.py` | 7 |
| `shipping.py` | 6 |
| `stock.py` | 5 |
| **合计** | **265（7 个模块）** |

- 「**8 个模块 / 269 条**」是**全仓**口径：`app/main` 7 个（265）+ `app/auth`（4）= 269。
- 「**8**」这个数另有来源：把 1 字节死文件 `app/main/sales_routes.py`（**0 路由、0 引用**）也算作「一个模块」⇒ 8 个**文件**、其中只有 7 个含路由。
- ⇒ **B9-16 拟定写进 `AGENTS.md` 的「`app/main` 有 8 个模块」是错的，`81-` 不得照抄**；正确表述 = 「`app/main` 下含 `@bp.route` 的模块 **7 个 / 265 条**（另有 1 字节死文件 `sales_routes.py` 待删）」。

## A-7 N-A2：批次8 的计数（裁定：批次8 = 已实现 **0** / 部分实现 **1** / 计划内不改 **1** / 未实现 **10**，合计 12）

`recon-arch.md` 汇总写「批次8 = 0/12」，同稿 B8-07 行又写「代码面已在位（静态面）」。两者并非矛盾，而是**档位没写清**：
- **B8-07 = 部分实现**（代码面已在位，但缺验收载体）；
- **B8-08 = 计划内不改**（正确状态，不计为未实现）。
⇒ 引用批次8 时必须写「**0 已实现 / 1 部分 / 1 不改 / 10 未实现 = 12**」，不得只写「0/12」（会把「不改」误算成欠账）。

## A-8 N-A3：B7-06 的档位（裁定：**未实现**）

`recon-arch.md` 把 B7-06 记为「已实现（未新增）」，另一稿记为「未开始」。裁定：**未实现**。
理由：批次7 的验收判据是「触发器**有真实业务调用点**」；「净增 0」只是**对现状的描述**（因为未接线故无从新增），**不是完成证据**。⇒ 不得以「净增 0」判 B7-06 已实现。

## A-9 N-A4：`BytesIO` 构造点（裁定：**`app/` = 17**（`routes.py` 13 + `quality.py` 3 + `excel_generator.py` 1）；**`app/main` = 16**；**`routes.py` = 13**）

**冲突**：`AGENTS.md` 写「13 处」；`recon-docs.md` 给 13/16/17；`recon-product.md` 给「15 处」。`80-` 登记为 N-A4，且该数会影响 `81-` 的数字表。

**captain 本轮 AST 独立复算（口径：`ast.Call` 且函数名为/属性名为 `BytesIO`，遍历 `app/`，排除 `.tmp`、`__pycache__`）**：

| 文件 | 构造点 |
| --- | --- |
| `app/main/routes.py` | 13 |
| `app/main/quality.py` | 3 |
| `app/utils/excel_generator.py` | 1 |
| **`app/` 合计** | **17** |

裁定：
- **`routes.py` = 13** —— `AGENTS.md` 的「13 处」**不错，但口径最窄**（它说的是 routes.py 的导出改造面）；
- **`app/main` = 16**（13 + 3）；
- **`app/` = 17**（再 + `excel_generator.py` 的 1）；`AGENTS.md` 若仍写「全仓 13」需订正为 **17**；
- **「15 处」无任何口径来源，作废；不得进入 80- / 81- 正文。**

## A-10 N-A5：P11 的终态（裁定：**部分关闭**；本轮新增的一处残留系 **captain 自己造成，已由我清除**）

- **原载体**（仓库根 `.tmp_v15_*.{out,err}` 6 个）：已清理 ✅。
- **本轮发现的同族残留**：`_probe_tmp/gate-baseline.txt`（24704 B，mtime 2026-10-08 0:43）——**这是 captain 本轮跑门禁基线时自己写的侦察残留**，**已由 captain 删除**（删前已核验绝对路径与内容，目录内仅此一个文件）。
- **`scripts/_probe_seed.py`（496 B，mtime 2026-08-27 15:59）先于本轮战役**，**不属本轮污染**，不并入 P11；另案登记。
- ⇒ P11 档位 = **部分关闭**：原载体已清、captain 残留已清；`scripts/_probe_seed.py` 的历史归属待单独确认。

## A-11 N-A6：「10 条」与「11 条」（裁定：**两数都对，属不同口径，不得互替**）

- **10 条** = `70-第2轮收口与阶段C移交.md` §10.3 的**具名产品清单**（P1–P10）；
- **11 条** = **今日实测仍存在**的产品问题（P1–P10 + **P12**；P11 原载体已清，见 A-10）。
⇒ 引用时必须写成「阶段C §10.3 具名 10 条 / 今日实测仍存在 11 条（含 P12）」。

## A-12 N-A7：`create_all` 差集 31 vs 32（裁定：**权威值 31**）

- **31** = **业务表口径**（**排除** `alembic_version`）——与本项目既有权威表述（规划附录 A「31 张」）一致，**以 31 为准**；
- **32** = 含 `alembic_version` 的口径。
⇒ 80- / 81- 一律写 **31（不含 `alembic_version`）**，并在括注里说明另一种口径为 32。

## A-13 待裁定池已清空（`80-` §6.3 的 N-A1…N-A7 全部裁定完毕）

`81-` 可直接据本件落数字表，**无需再标「待裁定」**。以下口径已作废，**禁止出现在 80- / 81- 正文**：
① 「`can()` 110 处 / 28 文件」→ 用 A-2 的 **101 / 32**；
② 「`app/main` 8 个模块」→ 用 A-6 的 **7 个 / 265 条**；
③ 「`BytesIO` 15 处」→ 用 A-9 的 **13 / 16 / 17**（按口径选）；
④ 「全仓 `BytesIO` 13 处」→ 订正为 **17**；
⑤ 「批次8 = 0/12」→ 用 A-7 的 **0/1/1/10 = 12**；
⑥ 「B7-06 已实现（未新增）」→ 用 A-8 的 **未实现**。

---

## A-14 ⚠ 撤回：「`AGENTS.md:87` 的 `3=入口缺失` 是硬错」这一定性**不成立**（captain 自我订正）

**触发**：独立复核员2（t14，verdict=`needs_revision`）的 **F-1（high）**。**裁定：复核员正确，`recon-docs.md` 的该条结论与 `80-` 的照抄均需订正。**

**事实（captain 本轮亲自取源复核）**：`exit 3` = 「入口缺失」是**真实实现**，位置在 **CI 封装层**，不在 `ci_gates.py` 内：

| 落点 | 内容 |
| --- | --- |
| `Jenkinsfile:102` | `echo [E-04] 门禁入口缺失: test-reports-2026-10/harness/ci_gates.py 不在工作区` |
| `Jenkinsfile:104` | **`exit /b 3`** |
| `Jenkinsfile:109` | `echo "[E-04] ci_gates exit=${ciRc} (0=all green; 2=report-only failed; 1=blocking failed; 3=entry missing)"` |
| `Jenkinsfile:110` | **`if (ciRc == 3) { … }`**（第一阶段置 `UNSTABLE`，`error()` 被注释即 A-63 第二步待晋升项） |
| `.github/workflows/docker-deploy.yml:34-36` | `if [ ! -f …/ci_gates.py ]; then … exit 3; fi` |
| `ci_gates.py:122` | 其 `BUILD_LAYER_BLOCKED.blocked_reason` 明写 **`ciRc==3 / ciRc==1`** |

⇒ **正确表述**：`ci_gates.py` **脚本自身**只发 `0/1/2`；而「`0/1/2/3`」是**CI 门禁入口（封装层）**的契约，`3` 由 Jenkins/GH 包装脚本在「门禁入口文件缺失」时发出，并被 `ci_gates.py` 引用。
⇒ `AGENTS.md:87` 的语义**对 CI 入口成立**，只是把「由 `ci_gates.py` 编排」与「退出码 3」并置时**归属表述不够精确** ⇒ 应定性为「**口径需补注**」，**不是「硬错」**。

**captain 复核缺口（诚实记录）**：我先前"复核"该条时只查了 ① `ci_gates.py` 内有无 `exit 3`／`入口缺失`、② `AGENTS.md:87` 的文本 —— **漏查 CI 封装层**（`Jenkinsfile` / `docker-deploy.yml`），因此**错误地确认了 t7 的结论**。复核员的 F-1 是对我的纠正。⇒ 教训：**「某数字/语义在脚本里不存在」≠「该语义不存在」，必须连同调用它的封装层一起查。**

**对下游的两条强制改法**（`80-` 与 `81-` 都要落）：
1. `80-`（含其 §5 的 AGENTS.md 专章与 §1 的一页结论）：把「`AGENTS.md` **1 处硬错**」改为「**0 处硬错 + 1 处表述需补注**（`exit 3` 语义由 CI 封装层实现，脚本自身只发 `0/1/2`）」，**以 append-only 订正声明追加**（其正文原值保留不删，沿用 `80-` §0.5 的既有规则）。
2. `81-` 的 **B18-02**：把「退出码只留 `0/1/2`」（该做法会**删掉一条正确表述**）改为「**补注 `3` 的来源（CI 封装层）+ 明确脚本自身只发 `0/1/2`**」。
3. 附注：`AGENTS.md:91`「`app/main` 下现只有 `routes.py` 一个路由模块」**仍然是错的**（见 A-6，实为 7 个 / 265 条）—— 该条不受本条影响，仍应订正。

## A-15 引用外部依赖行号的口径（复核员非 finding 提示，采纳）

`flask_bootstrap` **不在本仓库内**（site-packages）。故 A-1 与 `81-` 引用的 `flask_bootstrap/__init__.py:76/108/114-119/173` 属**环境相关行号**，随 site-packages 版本漂移、**不可由本仓库复现**。
**裁定**：A-1 的**结论不变**（Bootstrap 走 CDN），但**引用时必须同时给出仓库侧可复现证据** = ① 全仓 `BOOTSTRAP_SERVE_LOCAL` 命中 0 处；② `base.html:9` / `:544` 的 `bootstrap.load_css()/load_js()` 调用点。
⇒ 下游引用 A-1 时，**以这两条仓库内证据为主**，site-packages 行号只作辅助旁证并标注「环境相关、不可由本仓库复现」。
