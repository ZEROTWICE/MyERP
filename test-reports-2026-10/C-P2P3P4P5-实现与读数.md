# C 组 P2/P3/P4/P5 导入容错面 —— 实现与读数（t5）

- 任务：taskc-product-face / t5（attempt 0b53e90a-f760-4d49-973d-15868f3badce）
- 执行：impl-p2（2026-10-12，HEAD 基线 9f28baa）
- 权威定位依据：`test-reports-2026-10/C-落点与在册项盘点.md`（sha256 D60BA590…F7AA）+ `test-reports-2026-10/C-落点与在册项盘点-勘误附录.md`（§2）
- 解释器：`/opt/wage-venv/bin/python`（3.11.2）；工作目录 `/root/code/MyERP`
- 改动文件：仅 `app/main/routes.py`（inScope 内）；本登记件为新建，不覆盖任何既有文件
- 复核方式：副本库（`scripts/_test_bootstrap.make_app()` fresh 副本 + Flask test_client + `login_as('_t_admin')`），真实 `app.db` 全程只读

---

## §1 P2（f-string 前缀缺失）—— 现场已修，本轮零改动

任务书 v2 预判正确：P2 已在前序批次入库，本轮**未改任何代码**。

静态读数（判据 = `grep -n '第{index' app/main/routes.py` 无未加 `f` 前缀的字面量）：

```
$ grep -n '第{index' app/main/routes.py
5505:                error_messages.append(f'第{index+2}行导入失败，请稍后重试或联系管理员')
5598:                error_messages.append(f'第{index+2}行导入失败，请稍后重试或联系管理员')
```

命中恰 2 处、均带 `f` 前缀、无裸字面量 ⇒ 判据满足。实际报错文案读数：

| 站点 | def 行号（本轮实测） | 文案（逐字） |
| --- | --- | --- |
| `import_finished_products`（route `/inventory/finished/import`） | :5435 附近（载体现 :5505） | `f'第{index+2}行导入失败，请稍后重试或联系管理员'` |
| `import_raw_materials`（route `/inventory/raw_materials/import`） | :5524 附近（载体现 :5598） | `f'第{index+2}行导入失败，请稍后重试或联系管理员'` |

> 该文案属 except 兜底分支（`routes.py:5504`），触发条件为行级入库异常（如约束冲突），非本轮新增行为；行号口径 = `enumerate(...)` 0 基 + 2 = Excel 实际行号，与本轮 P5 统一口径一致。

---

## §2 P3（整批拒绝破坏行级容错）—— `import_process_prices` 已改

### 改动点（文件 `app/main/routes.py`，def `import_process_prices` @:2436，route `/process_prices/import` @:2433）

1. **删除整批拒绝块**（原 :2533-2539）：`如果有验证错误，直接返回` + `jsonify(success=False, message='数据验证失败，共发现N个错误…')` 早退整段移除。
2. **删除文件外重复早退**（原 :2544）：`if duplicate_codes: return` 移除。
3. 验证循环 `for i, data in enumerate(process_data, 1)`：坏行记 `error_messages.append(f'第{i+1}行数据错误：{"; ".join(row_errors)}')` 后跳过，好行进 `pending_rows`。
4. 文件内去重：`seen_row_by_code` 字典，重复行记 `第{row_no}行工序编号 {code} 在文件中重复（首次出现在第{seen_row_by_code[code]}行）` 后跳过，幸存者进 `process_data_final`（口径同 `import_employees` 工号去重）。
5. 后续循环改吃 `process_data_final`（元组 `(row_no, data)`）：existing_codes 检查、普通工序第一遍、小计工序第二遍、`'total_processed': len(process_data_final)` 全部改用 row_no 文案。
6. commit 语义：`success_count > 0` 时提交（好行照常入库）。

### 修前/修后实测（副本库，命令 = `/opt/wage-venv/bin/python -B test-reports-2026-10/.tmp/p2p3p4p5/after_observations.py`，前置 = `git stash` 前基线另存）

**修前（整批拒绝形态，2026-10-12 实测）**：

- 输入：3 好行 + 2 坏行（坏行 = 空生效日期 / 负单价）
- HTTP 200 / `success=False` / message=`'数据验证失败，共发现2个错误：\n第5行数据错误：生效日期不能为空\n第6行数据错误：单价不能为负数'`
- **GX_ROWS DELTA=0**（3 条好行全部不入库）⇒ 整批拒绝确认

**修后（A 场景，同一 xlsx）**：

- `success=True` / `delta_target=3` / `good_rows_saved=['GX-OK-1','GX-OK-2','GX-OK-3']`
- message=`'成功导入 3 条记录\n失败：2 条记录导入失败\n\n错误详情：\n第5行数据错误：生效日期不能为空\n第6行数据错误：单价不能为负数'`
- 无 500、无整批 reject ⇒ 判据满足

**修后（B 场景：文件内重复 DUP-1×2 + UNIQ-1）**：`success=True` / DUP-1 存 1 行且 `is_current=1`（重复行只跳过）/ 文案含 `第3行工序编号 DUP-1 在文件中重复（首次出现在第2行）`。

### 判据读数

```
$ grep -c "如果有验证错误，直接返回" app/main/routes.py
0
```

（修前 = 1；批次15 `d809e68` 已删 `import_employees` 的同族块，本轮删除 `import_process_prices` 的最后一处 ⇒ 全仓归零。）

---

## §3 P4（上传残留清理）—— `import_products` + `save_temp_file` 已改

### 改动点（文件 `app/main/routes.py`）

1. `import_products`（route `/products/import` @:8321 / def @:8324）：
   - `temp_path = save_temp_file(file)`（现 :8328）后补注释；
   - **finally（现 :8541 附近）改为 `if temp_path: shutil.rmtree(os.path.dirname(temp_path), ignore_errors=True)`** + 保留 `cleanup_temp_files()` 兜底历史残留（`save_temp_file` 建的是 TEMP_FOLDER 下 `mkdtemp` 子目录 ⇒ rmtree 整目录，形态同合金导入 :2799/:2848）。
2. `save_temp_file`（def @:5645，唯一调用方 = `import_products`）补 try/except：`file.save(temp_path)` 失败 ⇒ `shutil.rmtree(temp_dir, ignore_errors=True); raise`（落盘半途失败也不留半空目录）。

### AST 复核（判据 = finally 内出现 os.remove/rmtree）

```
finally calls = ['shutil.rmtree(os.path.dirname(temp_path), ignore_errors=True)',
                 'os.path.dirname(temp_path)',
                 'cleanup_temp_files()']
```

（读数出自 p4_exception_path.py 场景 G，AST 遍历 `ast.parse(open('app/main/routes.py').read())`。）

### 实测（副本库 + Flask test_client；命令 = `/opt/wage-venv/bin/python -B test-reports-2026-10/.tmp/p2p3p4p5/p4_exception_path.py`）

- **E'（正常路径）**：官方模板同构 xlsx（`ExcelGenerator.create_product_template` 形态：sheet `产品信息` 11 列）⇒ HTTP 200 / `success=True` / message=`'成功导入 1 个产品'` / `T5-P-E1 rows 0->1`（产品真实入库）/ **TEMP entries=[]**（导入完成后无任何 mkdtemp 残留）。
- **F'（异常路径）**：损坏文件（非 zip 字节）⇒ HTTP 200 / `success=False` / message=`'导入失败，请稍后重试或联系管理员'` / **TEMP entries=[]**（解析异常路径下 finally rmtree 生效，无残留）。
- 两次实测均无 500。

### 既有缺陷声明（非本轮引入，零折算）

`/products/import` 存在**在案既有缺陷**：`app/main/forms.py:216` `ProductImportForm.file = MultipleFileField` ⇒ `form.file.data` 是 list ⇒ `routes.py:8323` `allowed_file(file.filename)` 抛 `'list' object has no attribute 'filename'`，任何真实 POST（多文件表单负载）都会被外层 except 吞成 200/success=False，**到不了 save_temp_file**；另有 `form.update_existing.data`（:8359）字段不存在（ProductImportForm 只有 file/submit）。两处已在案：`test-reports-2026-10/90-新DSH交接-批次12-14收口与恢复点.md:346` + `test-reports-2026-10/B17-登记.md:187`（后者明确「不在本批 inScope，属 B17-08 邻近面既有缺陷」）。

**处置**：P4 实测采用**仅测试侧垫片**——p4_exception_path.py 内把 `R.ProductImportForm` 替换为单文件 FileField 子类（csrf=False），模拟 `app/templates/products.html:896-898` 前端模态实际发送的单文件负载；`app/**` 零改动。P4 的验收（finally 清理 + 异常路径无残留）在该垫片下完整实测通过。**表单层既有缺陷的修复（MultipleFileField→FileField 或 data[0] 取首）不在 t5 inScope，留 captain 排期**（如需处置，属 B17-08 邻近面单列任务）。

---

## §4 P5（错误信息行号口径）—— 4 处已改 + 1 处复核已带

任务书标记 5 处，现场复核后实际改 4 处：

| 站点 | def 行号（本轮实测） | 改动 | 行号公式 |
| --- | --- | --- | --- |
| `import_employees` | :2096 | **零改动**（任务书标记 :2231 实测已带 `f'第{row_no}行工号 … 在文件中重复…'`） | 去重循环 row_no |
| `import_production_records` | :2919 | 日期错误（原 :2956）→ `f"第 {index + 2} 行：{date_error}（原值：…）"` | `enumerate(record_data)` 0 基 + 2 |
| `import_production_records` | :2919 | 取价未找到（原 :2963）→ `f"第 {index + 2} 行：未找到工序 … 的价格"` | 同上 |
| `import_production_records` | :2919 | 处理失败（原 :2985）→ `f"第 {index + 2} 行：处理记录时出错: …"` | 同上 |
| `import_bonus_penalties` | :4136 | 处理失败（原 :4192）→ `f"第 {index + 2} 行：处理记录时出错: …"` | 同上 |

三站点公式一致（`enumerate(..., start=0)` + 2 = Excel 数据行号，表头第 1 行不计），措辞与 `import_tasks`（:4283/:4289/:4296/:4312）逐字同族。

### 实测读数（副本库，同 §2 命令）

- 生产记录（C 场景：2 好行 + 2 坏行；前置 fixture `ProcessPrice(effective_date=date(2026,1,5), process_code='C-PROC-1', …)`）：
  - `delta=2`（好行入库）/ message=`'成功导入 2 条记录，2 条记录导入失败：\n第 3 行：日期格式错误（不是日期）（原值：不是日期）\n第 4 行：员工工号 NO-SUCH-EMP 不存在'`
  - **坏行行号 == Excel 实际行号**：fixture xlsx 第 3/4 行为坏行（表头第 1 行），读数逐字吻合。
- 奖惩（D 场景：1 好行 + 1 坏行）：`bonus delta=1` / 文案含 `第 3 行：员工工号 NO-SUCH-EMP 不存在`（坏行在 xlsx 第 3 行）✓。

---

## §5 verify 三命令读数

| # | 命令 | 读数 | 状态 |
| --- | --- | --- | --- |
| 1 | `/opt/wage-venv/bin/python -B test-reports-2026-10/harness/ci_gates.py --phase first` | steps=20 / blocking 失败 = `['check_doc_claims']` / report-only 失败 = `['evidence_hash'（历史遗留，同 t8）]` / exit=**1**（run ci-run-20261012-061030） | **未达 exit 0，见 §6 blocked 项** |
| 2 | `/opt/wage-venv/bin/python -B scripts/check_templates.py` | `87 templates / 44 declared / 40 used in templates / 44 used on routes / landing 5` → `RESULT: OK` / exit 0 | 通过 |
| 3 | `/opt/wage-venv/bin/python -B -m py_compile app/main/routes.py` | 无输出 / exit 0 | 通过 |

行尾纪律（C7）：`git diff --ignore-cr-at-eol --numstat -- app/main/routes.py` = `51 32`（与普通 numstat 一致 ⇒ 无 CRLF 漂移）。

---

## §6 blocked / 未处置项与解除条件（不折算 pass）

### 6.1 `check_doc_claims` 钉值漂移（**blocked**，本轮代码改动的直接后果）

- **状态**：ci_gates --phase first exit=1，唯一 blocking 失败 = `check_doc_claims`（29 键中 28 键相等，`routes_py_lines` 钉值 12806 ≠ 源值 12825）。
- **根因**：本轮 t5 在 inScope 的 `app/main/routes.py` 净 +19 行（51/32），使 `scripts/check_doc_claims.py:158` 的 `routes_py_lines` 钉值过期。**该脚本在 scripts/** 属 t5 out-of-scope，成员无权改；且按硬约束 ⑤ 改钉值必须走 A-70 三步（旧值留档 → 阴性对照先转红 → 改值 + 复跑绿 + 登记件），同样超出单任务 inScope。
- **阴性对照现状**（满足 A-70 第②步的「先红」）：本读数 `check_doc_claims` 在改码后**实测已红**（12 violations 原始输出，其中 11 条为缺 `--coverage` 参的非回归、1 条为 routes_py_lines 真漂移；带 `--coverage test-reports-2026-10/evidence/harness/ci-run-20261012-060651/coverage.json` 后 = 28/29 相等，唯一红 = routes_py_lines）。`--selftest` 26/26 通过（DC-N9 阴性对照存在）。
- **解除条件**：由 captain/verify 线走 A-70 三步把 `scripts/check_doc_claims.py:158` 的 `routes_py_lines` 由 12806 改为 **12825**（并按需同步其文档口径），复跑 `ci_gates.py --phase first` 至 exit 0（evidence_hash report-only 红另按 §6.2 处置）+ 登记件留档。
- **临时复核口径**：在钉值更新前，本轮正确性可由 §5 #2/#3 + 副本库四场景（A/B/C/D + E'/F'/G）独立复算。

### 6.2 `evidence_hash` report-only 红（**blocked，历史遗留非本轮引入**）

同 t8 登记口径：`b17-verify/probe_permission_matrix.txt`（1664B44B…→F81525C2…，9627→11234 B）与 `b17-verify/probe_smoke_test.txt`（59A7E5F0…→DA0C377D…）两条 modified，mtime 2026-10-12 04:45:16/04:45:29 早于本轮开工（05:5x）⇒ 历史遗留。解除条件 = A-70 三步重冻结（`evidence_hash.py --freeze`）或恢复原件字节；详见 `test-reports-2026-10/C-写盘守卫-实现与读数.md` §3。

### 6.3 `/products/import` 表单层既有缺陷（**blocked（B17-08 邻近面在案），非本轮引入、非本轮处置**）

见 §3 既有缺陷声明：MultipleFileField list 语义 + `update_existing` 字段不存在 ⇒ 真实多文件 POST 恒走外层 except。解除条件 = 单列任务修 `app/main/forms.py:216`（FileField 或取 `data[0]`）+ `routes.py:8359`（字段对齐或删引用），配副本库复测。本轮 P4 验收已用仅测试侧垫片完整覆盖（正常 + 异常路径无残留）。

---

## §7 真实库 app.db 三值核对（全程只读）

| 时点 | sha256 | bytes | mtime (UTC) |
| --- | --- | --- | --- |
| 开工 | `34e48e7a21163db390eebda4f2030343f3609afedc65d8c6e909d6eb5a49177e` | 2531328 | 2026-10-12 04:25:37.128430119 |
| 中途（06:07 复核） | 同上 | 同上 | 同上 |
| 收工（06:12 实测） | `34e48e7a21163db390eebda4f2030343f3609afedc65d8c6e909d6eb5a49177e` | 2531328 | 2026-10-12 04:25:37.128430119 |

三时点逐字恒等 ⇒ 只读性成立。

---

## §8 attempt 2 复跑读数（2026-10-12 06:23 UTC，captain A-70 重基线后）

背景：attempt 1 因 `check_doc_claims` 的 `routes_py_lines` 钉值 12806≠12825（本轮 routes.py 净 +19 行的直接后果）把 verify 命令 1 记为失败。captain 已走 A-70 三步重基线（`scripts/check_doc_claims.py:158` 12806→12825，复跑绿 run `ci-run-20261012-062047`），并澄清 verify 判据口径 = **blocking 失败=无**；report-only 的 `evidence_hash` 红为入册 blocked（04:45 `b17-verify/` 探针产物历史遗留，与 t8 同源，解除条件已登记），不构成 verify 失败。

### attempt 2 复跑命令与读数（工具+口径+值）

1. `/opt/wage-venv/bin/python -B test-reports-2026-10/harness/ci_gates.py --phase first`
   - 读数（run `ci-run-20261012-062312`，console 落盘该 run 目录）：**steps=20 / blocking 失败 = 无 / report-only 失败 = ['evidence_hash']（入册 blocked，见 §6.2）/ 注入未生效 = 无 / 仓库根两 JSON 未被触碰 = True（A-11）/ exit = 2**（退出码语义 = 仅 report-only 失败）。
   - `check_doc_claims` 步：exit=0 checks 5/5（29/29 相等，A-70 重基线后绿）。
   - 判据（blocking 失败=无）✅。
2. `/opt/wage-venv/bin/python -B scripts/check_templates.py`
   - 读数：`87 templates / 44 declared / 40 used in templates / 44 used on routes / landing 5` → `RESULT: OK`，exit 0 ✅。
3. `/opt/wage-venv/bin/python -B -m py_compile app/main/routes.py`
   - 读数：无输出，exit 0（COMPILE_EXIT=0）✅。

### attempt 2 代码零改动声明

attempt 2 **未改任何代码**（routes.py 与 attempt 1 定稿逐字节一致：staged diff 51/32 不变；`git diff --cached --ignore-cr-at-eol --numstat` = `51 32 app/main/routes.py`，C7 无 CRLF 漂移）。全部改动与读数均在 attempt 1 完成并已登记 §1–§7。

### attempt 2 副本库复测（两组实测脚本均按原样复跑）

- `after_observations.py`（A/B/C/D 四场景）：TOTAL=20 PASS=19 FAIL=1 —— 唯一 FAIL = 场景 E（`/products/import` 直接 POST 多文件表单负载）`success=False`，**正是 §6.3 在案既有缺陷的预期表现**（MultipleFileField ⇒ list 无 filename 属性 ⇒ 外层 except 吞成 200/success=False；B17-登记.md:187 明示不属本批 inScope）；该场景的 P4 正确形态由垫片版 E' 覆盖（见下）。其余 19 项（A 好行入库+第5/6行文案、B 去重+第3行文案、C 第 3/4 行行号、D 奖惩行号、E/F 的 TEMP 无残留、F 无 500）全 PASS。
- `p4_exception_path.py`（E'/F'/G 垫片版）：TOTAL=7 PASS=7 FAIL=0 —— E'（官方模板 xlsx）success=True + '成功导入 1 个产品' + T5-P-E1 rows 0->1 + TEMP entries=[]；F'（损坏文件）200/success=False + TEMP entries=[]；G AST finally calls 含 rmtree。

### attempt 2 真库三值复核（06:23 UTC）

`34e48e7a21163db390eebda4f2030343f3609afedc65d8c6e909d6eb5a49177e` / 2531328 B / 2026-10-12 04:25:37.128430119 +0000 —— 与 §7 三时点及硬约束②开工值逐字恒等 ✅（全程只读）。

---

本登记件指纹（末行自指不可行，给可复算口径）：`head -n -1 <本文件> | sha256sum` = **202 行 / 16893 B / sha256 `ceb4dd61d7732bd6122a7a3448cd16d9444e816918f30681fb925e751d8e2ef0`**（2026-10-12 06:23 UTC，attempt 2 追加 §8 后定稿；attempt 1 定稿口径 168 行/13768 B/fe09f43f…d809cf 已被 §8 追加取代，历史读数保留于 git 暂存区 attempt 1 版本）。
