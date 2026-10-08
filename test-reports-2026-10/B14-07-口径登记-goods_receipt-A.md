# B14-07 口径登记：`goods_receipt` 统一为一等检验类型（方案 A）

- **登记件性质**：**append-only 口径登记件**。已写入的条目不再改写；后续订正/异议一律以「追加条目」形式落在文末。
- **拍板来源**：团队目标「拍板项 4 = **方案 A：统一为 `goods_receipt`**」，用户 **2026-10-08** 明确选择。
- **本批落实面**：`app/main/quality.py`、`app/templates/main/quality/templates.html`、`app/templates/main/quality/tasks.html`、`app/templates/main/quality/records.html`（批次14 / 任务 t2）。
- **口径一句话**：`goods_receipt`（来料检）与 `production_record` / `product` / `material` **同级**，是**一等检验类型**；`app/main/quality.py` 的类型白名单、名映射、导入列常量、界面枚举与 JS 名映射表全部收录它。

---

## 1. 现场代码事实（修复前，2026-10-08 实测工作树）

1. **模板/任务类型三元组**为 `('product', 'production_record', 'material')`：
   - `app/main/quality.py:628`（修复前行号）`create_task` 的硬编码白名单 `if data.get('type') not in ('product', 'production_record', 'material'):`，否则 400，消息 `'type 取值不合法（应为 product / production_record / material）'`；
   - `app/main/quality.py:1531` `_VALID_TASK_TYPES = ('product', 'production_record', 'material')`（导入行级校验 `:1679-1680` 消费）；
   - `app/main/quality.py:1519` `TASK_IMPORT_COL_TYPE = '检验类型(product/production_record/material)'`；`:1471`/`:1529` 两张名映射表均只有 3 个键；
   - 3 处 UI 枚举（`templates.html:26/28` 与 `:104/106`、`tasks.html:26/28` 与 `:122/124`、`records.html:28/30`）与 3 张 JS 名映射表（`templates.html:299`、`tasks.html:368`、`records.html:259`）同样只有 `material`，全仓模板 **零** `goods_receipt` 命中。
2. **`goods_receipt` 只作为 `target_type` 存在**：`app/main/quality.py:1006`（修复前行号，实测占位 `:1008`）入库分支
   `if task and task.target_type == 'goods_receipt' and record.result == 'pass':` → 局部 `from app.models import GoodsReceipt` → `putaway_goods_receipt(...)`。
   即：**业务侧确实存在「来料检任务（`target_type='goods_receipt'`）」，但质检模板/任务类型域里没有它** —— 这是本批要消掉的口径分裂。
3. **`create_template` 不校验 `type` 取值**（`app/main/quality.py:237-306` 只校验 `required_fields = ['template_code','name','type']` 的存在性），`GET /api/quality/templates` 也不带 `type` 白名单。⇒ 后端**本来就能**建/筛 `type='goods_receipt'` 的模板；P7 的实际锁点在**界面枚举**与**`create_task` 白名单**，不在模板 CRUD。这条事实决定了「只放宽后端校验、不补 UI」不足以闭环（见 §3 状态 X）。
4. **`app/main/quality.py:862` 的 `if template.type != task.target_type:` 保持严格相等**（拍板项 4 第 ④ 条）：本批**不为 `material` 造特例放行**，也不收紧为白名单。
   由此得到一条必须钉住的现场事实：对**同类型对** `(task.target_type='goods_receipt', template.type='goods_receipt')`，`:862` 修复前后**都放行**。所以「修复前的 400」**不在 `:862`**，而在上一步 `create_task` 白名单 —— 修复前 `POST /api/quality/tasks {"type":"goods_receipt"}` 直接 400，用户**根本走不到**绑模板这一步。把 400 归到 `:862` 属误判，本登记件以此条为纠正口径。
5. **`InspectionRecord.nonconformity_records` 是 `lazy='dynamic'` 关系**（`app/models.py:886`，`NonconformityRecord` 见 `app/models.py:919-964`）：真值判断恒为真、下标取空集抛 `IndexError` ⇒ 消费侧**必须** `.first()`（`print_record.html:167-196` 的既有写法即如此）。这条是 B14-06 实现时的硬约束。

## 2. 方案 A 的落实点（本批改动清单）

`app/main/quality.py`（7 处；均**未**新增列、**未**新增路由、未动 `:862`）：

| # | 位置 | 改动 |
| --- | --- | --- |
| 1 | `create_task` | 白名单改为消费模块级 `_VALID_TASK_TYPES`；400 消息由 `' / '.join(_VALID_TASK_TYPES)` 生成（**单一口径来源**，消除两处白名单漂移） |
| 2 | `get_inspection_target_name` | 新增 `elif task.target_type == 'goods_receipt':` → 局部 import `GoodsReceipt`，返回 `f'到货单：{receipt.receipt_no}'` / `'到货单：未知'` |
| 3 | `_VALID_TASK_TYPES` | `('product','production_record','material','goods_receipt')` |
| 4 | `_TASK_TYPE_NAMES` | 新增 `'goods_receipt': '来料质检'` |
| 5 | `TASK_IMPORT_COL_TYPE` | `'检验类型(product/production_record/material/goods_receipt)'`（导入模板生成与解析共用该常量 ⇒ 两端一致） |
| 6 | 导入行级校验错误串 | 改为 `' / '.join(_VALID_TASK_TYPES)` 动态生成 |
| 7 | `export_inspection_records` 的局部 `type_names` | 新增 `'goods_receipt': '来料质检'` |

模板（3 个）：筛选下拉 + 模态框/任务表单枚举各新增 `<option value="goods_receipt">来料质检</option>`；3 张 JS 名映射表各新增 `'goods_receipt': '来料质检'`；`tasks.html` 的 4 个 `switch/case`（`loadInspectionTargets` 的 url 分支与 options 分支、`loadInspectionTargetsForEdit` 的同两处）各新增 `case 'goods_receipt':`，url 分支以「到货单请到到货单页面发起检验」的 info 提示 + 提前 `return` 收口（**先于 fetch 出口**，避免 `url=''` 把 `GET /quality/tasks` 当数据源请求）。

> 说明：`tasks.html` 的 `goods_receipt` 分支**不拉取检验对象列表**。原因是全仓**没有**「到货单列表」JSON API（`app/main/purchase.py` 只有 HTML 页面与 `/<id>/putaway`、`/<id>/nonconformity`），而本批受 `harness/coverage_drift.py` 的路由锁（`rules_total == 271`）约束**不得新增路由**。⇒ 来料检任务的检验对象由到货单页面侧提供，质检页只给出口提示。这是**已知的产品化缺口**，登记在此，交后续批次决策（要么新增只读 API 并同步解锁路由锁，要么在采购面提供发起入口）。

## 3. 修复前/后读数（三态对照，全部在 `app.db` 副本 + 夹具树内完成）

驱动：`test-reports-2026-10/.tmp/run-b14/t4_goods_receipt_controls.py`（P/X/F 三态分别建 `states/<label>/` 夹具树，反向还原后跑同一探针 `probe_t4_goods_receipt.py`）。
> 为什么用夹具树而不是原地改真实文件：团队并行作业，原地改共享文件会让其他成员的门禁假红。

| 状态 | 含义 | 探针结论 | 关键读数 |
| --- | --- | --- | --- |
| **F** 全量修复 | 4 个文件均为修复后 | **PASS**（exit 0） | `ui_goods_receipt_option=true`；`POST /api/quality/tasks type=goods_receipt` → **200**；`goods_receipt` 任务 + `goods_receipt` 模板 `start-inspection` → **200**；`material` 模板 + `goods_receipt` 任务 → **400**（`:862` 严格相等仍生效）；`production_record` 任务既有绑定 → **200** |
| **X** 只改后端、UI 未补 | `quality.py` 修复后 + 3 模板还原 | **FAIL**，且**全部失败项都在 UI 侧**，后端校验面无回归 | `ui_goods_receipt_option=**false**` ⇒ 负例成立（「只放宽 `:862`/白名单而不补 UI」**判不通过**）；后端侧 8 项（建任务/建模板/绑模板/反例 400/既有 200/NC 键）**全部通过** |
| **P** 修复前 | `quality.py` 7 处 + 3 模板全部还原 | **FAIL** | `GET /api/quality/records/<id>` 的 `record_data` **无 `nonconformity` 键**；模板处置分支显示判定**不为 `block`**（死分支）；`POST /api/quality/tasks type=goods_receipt` → **400**（`type 取值不合法…`）；三页 UI `goods_receipt` 枚举数 **0** |

**B14-06 浏览器侧判定**（`test-reports-2026-10/.tmp/run-b14/nc_branch_check.js`，node v24.21.0 直接执行页面真内联 JS + 自建 DOM stub，非源码文本猜测）：

- 有 NC 的真 JSON 渲染 ⇒ 容器 `display: block`，容器内 HTML 同时含处置类型/处理人/处理日期/处理结果/处理说明 5 项（`fields_in_html` 全 true，`info_len=861`）；
- 同一 DOM 紧接着渲染「无 NC」记录 ⇒ 容器 `display: none` **且** `innerHTML` 被清空（`info_len_after=0`）⇒ **阴性对照成立**（不显示空块、也不残留上一条记录的处置内容）。

**B14-06 死分支根因留档**：修复前 `get_inspection_record_detail` 组装的 `record_data` 只有 `id/record_code/type/inspection_target/inspector_name/inspection_time/result/notes/items/base_items`（`app/main/quality.py:1337-1348`，修复前行号），**没有 `nonconformity` 键** ⇒ `records.html` 里 `if (record.nonconformity)` 恒为假，处置分支（原 `:404-430`）**从未执行过**。这也解释了为什么该分支里的旧键名（`handling_method`/`handling_time`/`handling_notes`，与模型列 `type`/`handling_date`/`notes` 不一致）长期无人发现。修复后按模型口径输出 7 键（`id/type/handler_name/handling_date/handling_result/notes/status`），无处置单时返回 `null`。

## 4. 需求文档 `04` §2.1 A4 原句定位与订正声明

- **live 文档存在**：`docs/test-reports/2026-10/04-业务验收标准与端到端判据.md:75`，原句（逐字）：

  > `| A4 | 到货单 + 启用的 `type='material'` 质检模板 | 走完来料检 | **`inspection_records` +1**，`task.target_type='goods_receipt'` | ⚠ 模板**不随初始化数据下发**（附录 B G-M）→ **A4 必须先造模板** |`

- **同句在冻结快照**中亦存在：`test-reports-2026-10/phase1-snapshot/04-业务验收标准与端到端判据.md:75`。
- **订正声明（方案 A）**：该行「前置」列的 `type='material'` 与「期望」列的 `task.target_type='goods_receipt'` 构成**自相矛盾的口径**（来料检任务的模板类型被写成原材料检模板），按拍板项 4 应订正为 **`type='goods_receipt'`**。
- **实际文档订正移交批次18 文档收口**：`docs/**` 不在本任务 `inScope`，本批**不改动任何需求文档**，仅以本登记件（append-only）登记口径。**批次18 需把 `docs/test-reports/2026-10/04-业务验收标准与端到端判据.md:75` 的 `type='material'` 订正为 `type='goods_receipt'`，并同步冻结快照副本。**
- 附带影响（同属批次18 或 harness 收口）：`test-reports-2026-10/harness/uat_chains.py:1508-1537` 的 V-12 探针 `CA4a` **期望 `ui_goods_receipt_option=False`** ⇒ 与方案 A **直接冲突**（方案 A 生效后该期望恒红）。`CA4N`（用 `material` 模板开始来料检期望 400）与 `CA4b`（用 `goods_receipt` 模板期望 200）与方案 A **一致，无需改**。`test-reports-2026-10/harness/**` 不在本任务 `inScope`，**本批不改**，在此申报。

## 5. 标签口径

- 新增枚举/映射的显示名统一取 **`来料质检`**（与既有 `生产记录质检`/`成品质检`/`原材料质检` 的「XX质检」后缀一致，且与「来料**检**」这一业务动宾结构不冲突）。
- 注意与既有 **`NonconformityRecord.target_label`** 的 `goods_receipt → '来料检'`（`app/models.py:957`）**并存但不等同**：前者是「质检类型名」，后者是「不合格单的关联对象类型名」。本批不统一这两个字串（改 `target_label` 会动 `app/models.py`，不在本任务 `inScope`），登记为已知的用词差异。

## 6. 复现命令（全部在仓库根执行；Python = `F:\Miniconda\envs\wage\python.exe`）

```powershell
# 三态对照（P 修复前 / X 只改后端 / F 全量修复）——夹具树，不写真实 app.db
& 'F:\Miniconda\envs\wage\python.exe' -B test-reports-2026-10/.tmp/run-b14/t4_goods_receipt_controls.py
# 单跑 F 夹具态探针（产物落 .tmp/run-b14/artifacts/）
& 'F:\Miniconda\envs\wage\python.exe' -B test-reports-2026-10/.tmp/run-b14/probe_t4_goods_receipt.py `
    --app-root test-reports-2026-10/.tmp/run-b14/states/F `
    --out 'D:\workspace\wage_management_system - bak\test-reports-2026-10\.tmp\run-b14\probe_t4_F.json' --label F
# 模板/权限静态门禁（期望 87/44/40/44/landing 5 + RESULT: OK）
& 'F:\Miniconda\envs\wage\python.exe' -B scripts/check_templates.py
```

---

## 追加条目

（append-only：后续订正/异议请在此行下方追加，不要改动以上任何段落。）
