# C 组 P2/P3/P4/P5 —— 非作者复核（t12，round 1）

| 项 | 值 |
| --- | --- |
| 复核者 | `recon-c`（**非作者**；被复核实现者 = `impl-p2` / task `t5`，attempt `0b53e90a-f760-4d49-973d-15868f3badce`） |
| 任务 | `t12`（attempt `9ef82eb9-19eb-41da-9839-beacc6044e31`），kind=review，round 1 |
| 被复核件 | `test-reports-2026-10/C-P2P3P4P5-实现与读数.md`（203 行；件内自述 `head -n -1` = 202 行 / 16893 B / sha256 `ceb4dd61…e2ef0`）＋ `app/main/routes.py` 暂存改动（`git diff --cached --numstat` = **51 / 32**） |
| 时点 / HEAD | 2026-10-12（UTC）/ `9f28baa2f4c402b0baa2cddd1bdc95139747936e`；工作树 = HEAD + t5 暂存改动（**未提交**，`M ` 已 staged） |
| 方法 | 只读：`git diff --cached`、`grep -n`/`awk` 现场取值、`ast` 结构取证；**独立复跑** t5 的行为脚本（print-only，无写盘：`grep -n "open(\|json.dump" .tmp/p2p3p4p5/*.py` = 0 命中）与 `ci_gates.py --phase first` |
| 真库三值（复核开工 06:32 / 收工 06:36） | `34E48E7A21163DB390EEBDA4F2030343F3609AFEDC65D8C6E909D6EB5A49177E` / `2531328` B / `2026-10-12 04:25:37.128430119 +0000` —— 两次逐字恒等；与 t5 件内 §7 三时点亦恒等 |
| 本件性质 | **新建件**（未改 `app/**`、未改 t5 件、未 `git add`/commit/push）；复核期新增产物仅 `evidence/harness/ci-run-20261012-063230/`（本地留档，`.gitignore` 覆盖） |

**暂存区构成说明（防误判归属）**：`git status --porcelain` 的 staged 集合含其他成员件（`scripts/check_doc_claims.py`、`test-reports-2026-10/harness/measure_coverage.py`、`52-V13-…md`、`B18-登记.md`、3 个 `C-*.md`）。**t5 自述改动面 = 仅 `app/main/routes.py` + 本件**；我按 `git diff --cached -U2 -- app/main/routes.py` 逐 hunk 核对，**全部 8 个 hunk 只落在 P2/P3/P4/P5 相关函数内**（`import_process_prices` / `import_production_records` / `import_bonus_penalties` / `import_products`），无越界改动。✅

---

## §1 逐条判定（验收项 → 交付件位置 → 命令 → 实测值 → 判定）

| # | 验收项 | 交付件位置 | 命令（我执行） | 实测值（我读数） | 判定 |
| --- | --- | --- | --- | --- | --- |
| 1 | P2：无未加 `f` 前缀的字面量 | §1:16-31 | `grep -n '第{index' app/main/routes.py` | `5505` / `5598`，两处**均带** `f` 前缀；其余同类（`.format()` 形态）合法 | **passed** |
| 2 | P3：3 好 + 2 坏 ⇒ 好行入库（行级容错） | §2:48-58、§8:194 | `/opt/wage-venv/bin/python -B test-reports-2026-10/.tmp/p2p3p4p5/after_observations.py` | `PASS A.success_true` / `PASS A.delta_target GX rows 0->3 delta=3` / `PASS A.bad_row_numbered msg=…第5行…生效日期不能为空…第6行…单价不能为负数` / `PASS A.no_whole_batch_reject` | **passed** |
| 3 | P3：改点落在正确载体（E1 = `import_process_prices`，`import_employees` 的整批拒绝批次15 已删） | §2:39-45、§6 | `grep -c "如果有验证错误，直接返回" app/main/routes.py` | **0**（契约期望 1）——`git diff --cached` 显示该块（原 `:2533-2539`）与 `if duplicate_codes: return`（原 `:2544`）**已在本轮删除**；改后语义 = 坏行跳过 + `seen_row_by_code` 去重 + `success_count > 0` 提交 | **passed（实质）**；判据文本过期见 F3 |
| 4 | P3：文件内重复编号不整单拒绝 | §2:60 | 同上脚本 | `PASS B.success_true` / `PASS B.dup_only_once DUP-1 is_current rows=1` / `PASS B.uniq_saved total DUP+UNIQ rows=2` / `PASS B.dup_numbered` | **passed** |
| 5 | P4：正常路径 + 异常路径均无 TEMP 残留 | §3:92-96、§8:195 | `/opt/wage-venv/bin/python -B test-reports-2026-10/.tmp/p2p3p4p5/p4_exception_path.py` | `PASS E'.success`（`成功导入 1 个产品`）/ `PASS E'.product_saved T5-P-E1 rows 0->1` / `PASS E'.no_temp_leftover entries=[]` / `PASS F'.status_200` / `PASS F'.fail_handled` / `PASS F'.no_temp_leftover entries=[]`；`TOTAL=7 PASS=7 FAIL=0` | **passed** |
| 6 | P4：口径 = 「有 `finally` 但无有效清理」（**非**「无 `finally`」） | §3:75-90 | `ast` 遍历 `app/main/routes.py`（我的脚本，见 §3） | `import_products` def **:8324** / end **:8556**；`try@8343-8551` 的 `finalbody = ['if temp_path:\n shutil.rmtree(os.path.dirname(temp_path), ignore_errors=True)', 'cleanup_temp_files()']`；函数内 `os.remove` 计数 **0**、`shutil.rmtree` 计数 **1（@:8550）**；对照 `save_temp_file` def **:5645**，`:5649-5654` 为 `try: file.save(...) / except: shutil.rmtree(temp_dir) + raise`（rmtree@**:5653**） | **passed**（改前口径描述与实况一致：原 `finally` 只调 `cleanup_temp_files()`，阈值 300s ⇒ 对刚落盘文件无效） |
| 7 | P5：错误文案行号口径（含 4 处本次改动 + 1 处既有） | §4:106-118 | `grep -n '第 {index + 2} 行' app/main/routes.py`；`grep -n "error_messages.append" app/main/routes.py \| grep -v "第"` | 改动 4 处到位：`:2959`（日期）/`:2967`（取价）/`:2990`（处理失败）/`:4198`（奖惩处理失败）；同族既有：`:2949`/`:4166`/`:4172`/`:4289`/`:4295`/`:4302`/`:4318`。残余 grep = **{2231, 2544}** 两处，均为**多行 `append(`**、`第 N 行` 在续行（`:2232` / `:2545`）⇒ 实际无「缺行号」文案 | **passed** |
| 8 | P5：坏行行号 == Excel 实际行号 | §4:120-125 | 同 §1-#2 脚本（C/D 场景） | `PASS C.date_row_numbered msg=…第 3 行：日期格式错误…第 4 行：员工工号 NO-SUCH-EMP 不存在`（fixture 第 3/4 行为坏行）/ `PASS D.row_numbered msg=…第 3 行：员工工号 NO-SUCH-EMP 不存在` | **passed** |
| 9 | verify 1：`ci_gates.py --phase first` ⇒ `blocking 失败=无` | §5:133、§8:179-182 | `/opt/wage-venv/bin/python -B test-reports-2026-10/harness/ci_gates.py --phase first`（**我独立跑**） | run `ci-run-20261012-063230`：`steps=20` / `blocking 失败 = 无` / `report-only 失败 = ['evidence_hash']` / `注入未生效 = 无` / `仓库根两 JSON 未被触碰 = True（A-11）` / **`exit = 2`**（语义 = 仅 report-only 失败）；`check_doc_claims` 步 `OK … checks 5/5` | **passed** |
| 10 | verify 2：四个 def 行号与交付件所载一致 | §2/§3/§4 表 | `grep -n "^def import_employees\|^def import_products\|^def import_process_prices\|^def import_tasks\|^def save_temp_file" app/main/routes.py` | `import_employees` **:2096**（件载 :2096 ✅）/ `import_process_prices` **:2436**（✅）与 route **:2433**（✅）/ `import_production_records` **:2919**（件载 :2919 ✅）/ `import_bonus_penalties` **:4136**（件载 :4136 ✅）/ `import_products` **:8324**（件载 :8324 ✅）/ `save_temp_file` **:5645**（件载 :5645 ✅） | **passed** |
| 11 | verify 3：`grep -c "如果有验证错误，直接返回"` 期望 1 | §2:62-69 | 同 §1-#3 | **0**（修前 1，本轮删除最后一处）⇒ 判据期望值与现况不符（**因修复而失效**，非缺陷） | **passed（实质）** + F3 |
| 12 | report-only 红须处于 blocked 登记态 | §6.2:151-153 | 读我 run 的 `evidence/harness/ci-run-20261012-063230/evidence_hash.gate.json` | `verdict=violation`，`violations=` **两条 modified**：`harness/b17-verify/probe_permission_matrix.txt`（9627→11234 B）与 `harness/b17-verify/probe_smoke_test.txt`（3186 B，sha 变）；`stat` 实测 mtime = **04:45:29 / 04:45:16**，早于 t5 开工（05:5x）⇒ 历史遗留、非本轮引入；件内 §6.2 已写 blocked + 解除条件（A-70 三步重冻结或恢复原件字节） | **passed** |
| 13 | C7 行尾纪律 | §5:137、§8:190 | `git diff --cached --numstat` vs `git diff --cached --ignore-cr-at-eol --numstat` | 两者**逐字相同**（`51 32 app/main/routes.py`）⇒ 无 CRLF 漂移 | **passed** |
| 14 | 真库只读 + 全程未跑 `flask db *` | §7:161-169 | `sha256sum app.db` / `stat -c '%s %y'` 开工与收工 | 两次恒等（值见表头）；复核期未见迁移动作 | **passed** |

**判定汇总：14/14 实质 passed；其中 2 条（#3/#11）因「判据期望值写在修复前」而与字面期望不符（F3），实质证据强于字面（有 `git diff` 删除证 + 修前/修后读数）。**

---

## §2 复核独立性声明与未独立复算项（C9）

- **非作者**：本件全部读数由 `recon-c` 现场重取；t5 件仅作**被核对象**引用，其自述不作为判定依据。
- **我独立执行、我读数**：`after_observations.py`（TOTAL=20 PASS=19 FAIL=1）、`p4_exception_path.py`（TOTAL=7 PASS=7 FAIL=0）、`ci_gates.py --phase first`（exit=2）、`grep`/`awk`/`ast` 全部静态读数、`evidence_hash.gate.json` 与两条 probe 的 `stat`。
- **复跑副作用核验**：脚本均为 print-only（`open(...)/json.dump` 0 命中）；`.tmp/p2p3p4p5/` 复跑后仍为原 3 个脚本（无新增/覆盖）；`uploads/temp` 空；`git status --porcelain` 复跑前后**集合不变**（无新增 `??`、无新增 `M`）。
- **未独立复算（明确登记，不折算 pass）**：
  1. 「修前」读数（`§2:48-52` 的 `DELTA=0` 整批拒绝）——需回到未打补丁的树；本轮以 `git diff --cached` 的**删除 hunk** + `grep -c` 修前 1→修后 0 作替代证据，属**静态**证伪。若需行为级修前读数，须在 `git stash` 副本上另跑一次（本复核未做）。
  2. 场景 E 的 `FAIL`（`/products/import` 真实多文件 POST ⇒ `'list' object has no attribute 'filename'`）——我在复跑中**复现**了同一报错（`ERROR in routes: 产品导入失败：'list' object has no attribute 'filename'`），并核对在案引用属实（`app/main/forms.py:218 file = MultipleFileField(...)`、`app/main/routes.py:8374 if form.update_existing.data:`；在案件 `B17-登记.md:187` 与 `90-新DSH交接-批次12-14收口与恢复点.md:346` 逐字命中）；**该缺陷非本轮引入、非本轮 inScope**，t5 用「仅测试侧垫片」覆盖 P4 正确形态并显式声明，**不折算 pass**。
  3. A-70 重基线（`routes_py_lines` 12806→12825）由 captain 执行：我只核**结果**——`wc -l < app/main/routes.py` = **12825** 与 `check_doc_claims --list-constants` 的 `routes_py_lines 钉值=12825 源值=12825 OK` 相等，且我 run 的该步 `OK checks 5/5`。

---

## §3 P4 结构取证（我自己的 AST 脚本口径，可复跑）

```bash
/opt/wage-venv/bin/python -B - <<'PY'
import ast
t=ast.parse(open('app/main/routes.py',encoding='utf-8').read())
for n in t.body:
    if isinstance(n,ast.FunctionDef) and n.name in ('import_products','save_temp_file'):
        print(n.name, 'def', n.lineno, 'end', n.end_lineno,
              'os.remove', [x.lineno for x in ast.walk(n) if isinstance(x,ast.Call) and getattr(x.func,'attr','')=='remove'],
              'rmtree', [x.lineno for x in ast.walk(n) if isinstance(x,ast.Call) and getattr(x.func,'attr','')=='rmtree'])
        for x in ast.walk(n):
            if isinstance(x,ast.Try) and x.finalbody:
                print('  try@%d-%d finalbody=%s' % (x.lineno,x.end_lineno,[ast.unparse(s)[:80] for s in x.finalbody]))
PY
```

实测输出（逐字）：
```
import_products def 8324 end 8556 os.remove [] rmtree [8550]
  try@8343-8551 finalbody=['if temp_path:\n    shutil.rmtree(os.path.dirname(temp_path), ignore_errors=True)', 'cleanup_temp_files()']
save_temp_file def 5645 end 5655 os.remove [] rmtree [5653]
```
⇒ **口径成立**：改动前该 `finally` 的 finalbody 仅 `cleanup_temp_files()`（阈值 300s，对刚落盘文件无效），改动后新增 `shutil.rmtree(os.path.dirname(temp_path), ignore_errors=True)` 无条件整目录回收；`save_temp_file` 落盘失败路径亦 rmtree 后 `raise`。

---

## §4 findings（**低危，不影响 verdict**）

| id | 位置 | severity | problem（实测） | requiredFix |
| --- | --- | --- | --- | --- |
| **F1** | `C-P2P3P4P5-实现与读数.md:29` | low | `import_raw_materials` 的 route 写成 `/inventory/raw_materials/import`；实测 = **`/inventory/raw/import`**（`app/main/routes.py:5524`） | 文案级更正为实际 path（其余同表行号与结论不受影响） |
| **F2** | 同件 `:28`、`:78-79`、`:100` | low | 三处行号为「附近」或偏移：`import_finished_products` def 实测 **:5438**（件写「:5435 附近」，`:5435` 实为 route 行）；`temp_path = save_temp_file(file)` 实测 **:8337**（件写「现 :8328」）；`import_products` 的 `finally` 实测 **:8545** / rmtree **:8550**（件写「:8541 附近」）；`forms.py` `MultipleFileField` 实测 **:218**（件写 `:216`，`:216` 为 class 行）；`update_existing` 引用实测 `routes.py:8374`（件写 `:8359`） | 按实测行号更正（或统一标「行号以本次实测为准」并给出实测值） |
| **F3** | t12 契约 verify 第 2 条（`grep -c "如果有验证错误，直接返回"` 期望 **1**） | low | 实测 **0** —— 因 t5 **修好了** E1（在册项）而失效；t5 件内 §2/§6 已如实登记「修前 1 → 修后 0」并写明口径边界 | 判据文本改为「期望 **0**（E1 已修）」或写明「修前 1 / 修后 0」；**不改判 t5** |

---

## §5 verdict

**verdict = pass**（round 1）。

- 14 条判定实质全过；每条均有「命令 + 我实测值」，无一条以作者说明代替实测。
- P2/P5 现场行号按**函数名**定位复核一致（`:2096` / `:2436` / `:2919` / `:4136` / `:8324` / `:5645`），未使用阶段A 旧行号算术平移。
- P4 口径为「**有 `finally` 且改前无有效清理**」，非「无 `finally`/`remove`」；改后 `rmtree` 生效（AST 计数 + 副本库 E'/F' 双路径 `TEMP entries=[]`）。
- P3 覆盖面已闭合到 `import_process_prices`（E1）：`grep -c` = 0，改点落在正确载体；`import_employees` 的整批拒绝仍保持批次15 的删除态（本轮未回退）。
- `ci_gates --phase first`（我独立跑，run `ci-run-20261012-063230`）：`steps=20 / blocking 失败=无 / report-only=['evidence_hash'] / exit=2`；report-only 红为**两条 04:45 历史遗留 probe modified**，已由 t5 §6.2 登记 blocked + 解除条件 ⇒ 不构成 verify 失败。
- 3 条 findings 全为 low（文案/行号精度 + 判据文本过期），不影响本轮判定；建议随收口一并处理，**不需要 t5 返工**。
- **指纹（末行；自指不可行 ⇒ `head -n -1` 口径 = 本行之前的全部内容）**：本件共 **99 行**（末行即本行）；`head -n -1` 输出 **98 行**、字节 = **14288**、SHA256 = **`4483D8C59521018046459F07C546ED82F20B65FD6D7FC1B1BF28F04AD9F337F9`**。复算：`head -n -1 test-reports-2026-10/C-P2P3P4P5-非作者复核.md | sha256sum`（期望 `4483d8c59521018046459f07c546ed82f20b65fd6d7fc1b1bf28f04ad9f337f9`）、`… | wc -c`（期望 14288）、`wc -l < …`（期望 99）。
