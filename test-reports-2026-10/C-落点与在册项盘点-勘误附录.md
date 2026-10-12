# C 组 · 落点勘误附录（P2/P3/P4/P5 行号锚不可用 · 函数名定位替代）

| 项 | 值 |
| --- | --- |
| 盘点者 | `recon-c`（阶段C C 组**只读**盘点者，非实现者） |
| 触发 | captain 驳回自查：t5 任务书正文 `P3 改位置 routes.py:2061-2066` / `P4 routes.py:4000-4006（员工导入）` 与 `C-落点与在册项盘点.md` 的现场读数矛盾 |
| 时点 / HEAD | 2026-10-12（UTC）/ `9f28baa2f4c402b0baa2cddd1bdc95139747936e` |
| 方法 | 只读：`awk`/`sed -n`（现场）+ `git show <rev>:app/main/routes.py`（历史树逐字比对）+ `ast`（结构化计数）＋ `grep -c` |
| 真库三值（本轮开工） | sha256 `34E48E7A21163DB390EEBDA4F2030343F3609AFEDC65D8C6E909D6EB5A49177E` / `2531328` B / mtime `2026-10-12 04:25:37.128430119 +0000` |
| 真库三值（本轮收工） | 与开工**三项恒等**（零漂移）：同上 |
| 新增/改动 | **只新增本件**；未改 `C-落点与在册项盘点.md`、未改任何受跟踪文件；未 `git add`/commit/push |

**为什么不「追加」进 `C-落点与在册项盘点.md`**：该件末行是指纹行，逐字自述「**本件共 313 行（末行即本行）**」。
在其下追加任何内容 ⇒ ① 该句当场变成假话；② 已对外登记的 `313 行 / 45051 B / sha256 D60BA590…F7AA` 立刻成为**过期读数**（正是 N-D4 一类漂移）。
按 append-only 纪律，订正**新建件**；本件与正件的交叉引用写在上面这张表里。若 captain 要求单文件，请在阶段C 收口时把两件合并**并重打指纹**，不要就地追加。

---

## 1. 直接回答 captain 的提问

### (1a) 两个区间各是什么函数？员工导入入口到底是哪一个？

| 区间（今日） | 归属 | 全文（逐字） |
| --- | --- | --- |
| `routes.py:2055-2075` | `view_audit_logs`（route `@bp.route('/audit_logs', methods=['GET','POST'])` @`:2029`，def @`:2033`） | `:2062 return render_template('main/audit_logs.html',` → `:2065 pagination=pagination)`；随后 `:2067 @bp.route('/employees/template')`、`:2070 def download_employee_template():` |
| `routes.py:2295-2330` | `import_employees`（route `@bp.route('/employees/import', methods=['POST'])` @`:2093`，def @`:2096`） | 收尾段：`:2296 except`→`:2298` 保存失败文案；`:2300-2316` 拼消息；`:2319-2322 return jsonify({'success': success_count > 0, ...})`；`:2327 finally:`+`:2330-2334 os.remove(temp_path)` |

**员工导入入口 = `import_employees`（route `@bp.route('/employees/import', methods=['POST'])` @`routes.py:2093`，def @`:2096`，end @`:2335` 前）**。
`routes.py:2061-2066` 今日**属于审计日志页 `view_audit_logs`**，与员工导入无关。

### (1b) `:2061-2066` 今天是否仍是「整批 reject」语义？

**不是。** 今日 `:2061-2066` = `view_audit_logs` 的 `return render_template('main/audit_logs.html', …)`（分页渲染）。三证：

1. 现场逐字（上文表）与历史树逐字**完全一致**：`git show 1a3850f^:app/main/routes.py` 的同区间、同内容（⇒ 该区间**不因 1a3850f 漂移**）。
2. 今日 `import_employees`（`:2096-2335`）内 `if error_messages:` **仅 1 处 = `:2308`**，且它位于 `:2283 try: if success_count > 0: db.session.commit()` **之后**，只做「失败：N 条记录导入失败」文案拼装（`:2308-2314`），**不是**早退。
3. 今日全 `app/main/routes.py` 内该整批拒绝形态的**唯一存活点** = `:2533-2539`（属 `import_process_prices`，见 §3），不在 `:2061-2066`。

### (1c) 漂移后的 `raise`/`return` 整批拒绝代码在哪一行？

**在 `import_employees` 里已不存在（被删除，不是平移）。** 历史定位（`git show` 逐字）：

- 阶段A 树 `fd51023`（`fix(phaseA): 修复 13 项产品缺陷（P-01..P-13）`）`app/main/routes.py:2059-2066`：
  ```
  2060:         # 如果有验证错误，直接返回
  2061:         if error_messages:
  2062:             return jsonify({
  2063:                 'success': False,
  2064:                 'message': f'数据验证失败，共发现{len(error_messages)}个错误：\n' + …
  ```
  ⇒ **t5 任务书 `P3 改位置 :2061-2066` 在那棵树上是「逐字属实」的**：它就是 `import_employees` 的整批拒绝块。t5 的锚点不是抄错，是**时点过期**。
- 删除它的提交 = 批次15 `d809e68`（`feat(b15): 批次15 导入体验与原子性收口（B15-01…08 + RF-1 真库锚点重基线 + RF-2 类型守卫）`，2026-10-09）：`git log -S "如果有验证错误，直接返回" -- app/main/routes.py` 的**删除侧**；该短语在 `fd51023`/`a09b6c8` 树各命中 2 次，`d809e68` 起降为 1 次。
- **漂移后不存在「整批拒绝代码」可改** ⇒ 不要改 `:2061-2066`（那是审计日志页，改它会引入无关回归）。

### (2) `:3990-4010` 与 `:8300-8340` 各属哪个导入端点？

| 区间（今日） | 归属 | 关键行 |
| --- | --- | --- |
| `routes.py:3990-4010` | **`update_task_status`**（route `@bp.route('/tasks/<int:id>/update_status', methods=['POST'])` @`:3530`，def @`:3533`）——**不是**导入端点 | `:4000 elif reason:`、`:4006-4012 db.session.add(AuditLog(...))`（末道产出入库日志分支）；紧随其后 `:4044 @bp.route('/tasks/<int:id>', methods=['DELETE'])` / `:4047 def delete_task(id):` |
| `routes.py:8300-8345` | `download_product_template` 收尾（route `:8285`/def `:8288`）+ **`import_products`**（route `@bp.route('/products/import', methods=['POST'])` @`:8310`，def @`:8313`）头部 | `:8326 temp_path = save_temp_file(file)`、`:8328 try:`（内层）、`:8333 if import_data['errors']:`（解析错误整批返回） |

⇒ **`routes.py:4000-4006` 在任何树上都指不到「员工导入落盘」**。历史树上它属 `import_tasks`（见 §4 表），今日它属 `update_task_status`。

---

## 2. P2/P3/P4/P5 勘误表（函数名 + 当前 def 行号 + 关键行为行号）

| 项 | 任务书/正件旧锚 | 旧树实况（`git show` 逐字核对） | **今日以函数名定位（权威）** | 状态 |
| --- | --- | --- | --- | --- |
| **P2** 缺 f-string 前缀 | `routes.py:4945` / `:5036` | 未做历史树比对（**未核**，不在本次驳回范围） | `import_finished_products`：route `/inventory/finished/import` @`:5429` / def @`:5432` ⇒ 载体 `:5499`；`import_raw_materials`：route `/inventory/raw/import` @`:5518` / def @`:5521` ⇒ 载体 `:5592`（两处均**带** `f` 前缀） | 已修 |
| **P3** 整批拒绝 | 改位置 `routes.py:2061-2066` | `fd51023:2059-2066` = `import_employees` 的 `if error_messages: return jsonify({...数据验证失败...})`（整批 400，早于任何 commit） | `import_employees`：route `/employees/import` @`:2093` / def @`:2096`；**整批拒绝已删**（`d809e68` 批次15）；现行 = 逐行累加 `:2255-2280` + `:2283 if success_count > 0: commit()` + `:2319-2322 success_count > 0` | 已修（同族残留见 §3-E1） |
| **P4** 上传残留 | `routes.py:2171-2176`（清理只在 except / 早退不经 except）+ `routes.py:4000-4006`（`os.remove` 在 try 内、无 finally） | 旧 `:2171-2176` → `fd51023` 树属 `import_employees`（def `:1935`）；旧 `:4000-4006` → `fd51023:4003 file.save(temp_path)` / `:4006 os.remove(temp_path)  # 删除临时文件`（在 `:4000 try:` 内、无 `finally`）属 **`import_tasks`**（route `/tasks/import` @`:3984` / def @`:3987`）——**不是员工导入** | `import_employees`：save `:2112-2113`，清理 `finally` `:2327-2334`（`os.remove` `:2332`）⇒ 已修；`import_tasks`：route `/tasks/import` @`:4251` / def @`:4254`，AST `try×3 / with_finally=1 / os.remove@:4341` ⇒ 已修；**唯一无效点 = `import_products`**（route @`:8310` / def @`:8313`，save `:8326`，`finally` `:8530-8532` 仅调 `cleanup_temp_files()` 阈值 300s，全函数 `os.remove`/`rmtree` **0 处**） | 部分修（1/10 无效） |
| **P5** 行号覆盖 | `routes.py:4016`（员工工号…不存在）/ `:4022`（工序编号…不存在）无行号 | `fd51023:4016` = `error_messages.append(f"员工工号 {data['employee_id']} 不存在")`、`:4020 # 查找工序` —— 属 **`import_tasks`**（该树 def `:3987`），**不是**员工导入 | `import_tasks`（def @`:4254`）已改带行号（`:4283`/`:4289`/`:4296`/`:4312` 均在正件「带行号」集合内）；**现残余 5 处**：`import_employees`@`:2096` → `:2231`；`import_production_records`（route `/production_records/import` @`:2914` / def @`:2917`）→ `:2956`/`:2963`/`:2985`；`import_bonus_penalties`（route `/bonus_penalties/import` @`:4128` / def @`:4131`）→ `:4192` | 部分修（残余 5 处） |

**自订正（我对上一份报告的更正）**：正件与完成报告写「`import_products` def `:8313` **无 `finally`/remove**」。准确表述应为：**有 `finally`（`:8530-8532`），但其中只有 `cleanup_temp_files()`（阈值 300s），对刚落盘的文件不产生清理效果；全函数 `os.remove`/`shutil.rmtree` 调用 0 处**。
⇒ 「9/10」的比值不变，理由需按本行更正（正件已冻结、不回改；以本件为准）。

---

## 3. 新增在册项（P3 同族残留，读码证据，非实测）

**E1 · `/process_prices/import` 仍是整批拒绝（与 P3 同形）**

| 项 | 内容 |
| --- | --- |
| 现状 | `import_process_prices`：route `@bp.route('/process_prices/import', ...)` @`app/main/routes.py:2433` / def @`:2436`；`:2530-2531` 逐行累加 `error_messages`，`:2533-2539`「`# 如果有验证错误，直接返回` / `if error_messages: return jsonify({...'数据验证失败，共发现 N 个错误'})`」——**早于任何 `commit`**；`:2544 if duplicate_codes: return jsonify({...})` 亦为整批拒绝 |
| 判据（可复跑，只读） | `awk 'NR>=2530 && NR<=2545' app/main/routes.py` ⇒ 期望见到 `:2534 if error_messages:` 与 `:2535 return jsonify({`；`grep -c "如果有验证错误，直接返回" app/main/routes.py` ⇒ 期望 `1`（今日实测 `1`，落点 `:2533`） |
| 变红条件 | 若把「行级容错」定义为**导入面通用口径**：3 好 + 2 坏提交该文件 ⇒ 期望 `delta_target ≥ 1`，现状按读码推定为 `0`（整批 400、无 commit）⇒ **当前即红**。⚠ 该推定为**读码结论**，未实跑（禁请求型脚本）；实测解除条件 = 在 `_test_bootstrap.make_app()` 副本库上跑一次该端点并读 `delta_target` |
| 建议归属 | 本批（与 P3 同族，同改法可复用 `import_employees` 的现行形态）或显式登记为「P3 修复面 = 单端点」并写清口径 |

⚠ 状态口径：本项 = **读码证伪 + `not_measured`（未实跑）**，**不得折算 pass**，也不得据此直接判「已修/未修」以外的结论。

---

## 4. 行号锚为何不可算术平移（实测漂移史）

`git log --format=%h -22 -- app/main/routes.py` 逐提交取 `def` 行号（只读 `git show`）：

| 提交 | 主题（截断） | `def import_employees` | `def import_products` | `@bp.route('/audit_logs'` |
| --- | --- | --- | --- | --- |
| `fd51023` | fix(phaseA): 修复 13 项产品缺陷（P-01..P-13） | **1935** | 7685 | 1855 |
| `a09b6c8` | 批次12–14 收口 | 2103 | 8305 | 2023 |
| `d809e68` | 批次15 导入体验与原子性 | 2103 | 8323 | 2023 |
| `2b562b3` | 批次16 前端资产与契约 | 2107 | 8371 | 2027 |
| `5d1dcb4` | 批次17 工程治理与门禁 | **2094** | 8272 | 2027 |
| `090ce53` | fix(security): 安全审计剩余发现 | 2096 | 8274 | 2029 |
| `1a3850f` | 批次18-C 阶段C 产品面收口 | 2096 | **8313** | 2029 |
| `HEAD 9f28baa` | 批次18 收尾（B13-02） | 2096 | 8313 | 2029 |

**结论**：① 单点偏移量在 `fd51023 → HEAD` 期间为 `+161`（1935→2096），但**非单调**（2094→2096 与 2107→2094 反向），⇒ 任何「旧锚 + 常数」的平移都会错；② doc-70（V-17 时点）与 B18-05（2026-10-10 时点）的行号**落在不同树**上，混用即出现本轮的「差 4300 行」观感（`:2061` 属 `view_audit_logs`、`:4000` 属 `import_tasks`→今日 `update_task_status`）。

---

## 5. t5 任务书锚点的可执行改法（按函数名定位，禁按行号）

```bash
cd /root/code/MyERP
# P3：员工导入（整批拒绝已删；同族残留在工序价格导入）
grep -n "^@bp.route('/employees/import'\|^def import_employees" app/main/routes.py          # 期望 2093 / 2096
grep -n "^@bp.route('/process_prices/import'\|^def import_process_prices" app/main/routes.py # 期望 2433 / 2436（E1）
# P4：落盘/清理面（10 端点逐点，AST 口径 = /opt/wage-venv/bin/python -B 见正件 §6）
grep -n "^def import_employees\|^def import_tasks\|^def import_products" app/main/routes.py  # 期望 2096 / 4254 / 8313
grep -n "finally:\|os.remove\|shutil.rmtree\|cleanup_temp_files()" app/main/routes.py | sed -n '1,40p'
# P5：行号覆盖残余集合（期望 {2231,2956,2963,2985,4192}）
grep -n "error_messages.append" app/main/routes.py | grep -v "第"
```

**给 t5 的两条硬提示**：① `P3` 的 `:2061-2066` **今日是审计日志页**，禁止在该区间做 P3 改动（会引入无关回归）；员工导入的整批拒绝**已不存在**，若 t5 的验收是「3 好 + 2 坏 ⇒ `delta_target ≥ 1`」，改点应落在 **E1（`/process_prices/import`）** 或改为登记口径。② `P4` 的两处旧锚（员工导入 `:2171-2176`、任务导入 `:4000-4006`）**均已修**，唯一未修 = `import_products`（def `:8313`，清理 `:8530-8532` 无效），改点在那里，不在 `:4000-4006`。

---

## 6. 复现命令（全只读；供验证者 C9 复核）

```bash
cd /root/code/MyERP
sha256sum app.db && stat -c '%s %y' app.db            # 三值核对
awk 'NR>=2055 && NR<=2075' app/main/routes.py          # (1a) 2061 区间真实归属
awk 'NR>=2295 && NR<=2335' app/main/routes.py          # (1a) import_employees 收尾
git show 1a3850f^:app/main/routes.py | awk 'NR>=2055 && NR<=2075'   # 旧树同区间（证「不因 1a3850f 漂移」）
git show fd51023:app/main/routes.py | awk 'NR>=2055 && NR<=2070'    # (1c) 整批拒绝逐字原文
git show fd51023:app/main/routes.py | awk 'NR>=3995 && NR<=4012'    # (2) 旧 :4000-4006 真身
git log --format='%h %ad %s' --date=short -S "如果有验证错误，直接返回" -- app/main/routes.py  # 删除提交
for c in $(git log --format=%h -22 -- app/main/routes.py); do \
  printf "%s %s\n" "$c" "$(git show $c:app/main/routes.py | grep -n '^def import_employees' | cut -d: -f1)"; done  # §4 漂移史
awk 'NR>=2530 && NR<=2545' app/main/routes.py          # E1 同族残留
awk 'NR>=8525 && NR<=8537' app/main/routes.py          # P4 import_products 无效 finally
```

判据口径：本件所有「已修/未修」均为**读码级**证据；请求型判据一律 `not_measured`（见正件 §4）。
- **指纹（末行；自指不可行 ⇒ `head -n -1` 口径 = 本行之前的全部内容）**：本件共 **150 行**（末行即本行）；`head -n -1` 输出 **149 行**、字节 = **14849**、SHA256 = **`96BEC726CEBA3DC6F1474CE83C5623706C9047CCEB62735A24046CE62E30524D`**。复算：`head -n -1 test-reports-2026-10/C-落点与在册项盘点-勘误附录.md | sha256sum`（期望 `96bec726ceba3dc6f1474ce83c5623706c9047cceb62735a24046ce62e30524d`）、`… | wc -c`（期望 14849）、`wc -l < …`（期望 150）。
