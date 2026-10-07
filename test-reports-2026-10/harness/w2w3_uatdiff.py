"""w2w3_uatdiff.py — 用**树副本**做 `uat_chains` 40 条链的「修复前 / 修复后」逐条 diff。

## 为什么用树副本（关键工程约束）
`uat_chains.py` **直接写** `<repo>/test-reports-2026-10/evidence/uat/uat_chains.json`（未经
`_env.save_evidence`，A-58 已登记）⇒ 在真实仓库里复跑会**原地覆盖** t5 时代的冻结证据（`modified` 违规，
不可恢复）。本脚本因此把 `app/ + scripts/ + config.py + app.db + harness/` 复制到
`.tmp/<RUN_ID>/tree-*/`，在两个副本里各跑一次 ⇒ **真实 evidence 树零写入**。

## 两棵树的构造与「只差 t7」的证明
- `tree-after` = 当前工作树副本（含 t6/t8 已完成修复 + t7 本次修复）；
- `tree-before` = 同一副本，**只把 t7 的 5 处改动逐字回退**（`mes_service.py` 用
  `git show <PRE_FIX_REV>:` 整文件回退——该文件在 t7 前与**钉死的修复前提交**逐字节相同；
  `routes.py`/`models.py`/`stock.py` 用精确反向替换，保留 t6 的第 6 行导入与
  t8 的 P-08/P-09/P-12/P-13 标记）。
- 构造后**逐项断言**两棵树的 t6/t8 标记仍在位、t7 标记已消失（见 `--verify-only`），并把结论落证据。

## ⚠ 为什么钉**显式提交号**（A-70：本类系统性资产缺陷的第 1 例）

本脚本原先用 `git show HEAD:app/services/mes_service.py` 整文件回退 `mes_service.py`
（当时成立的理由是「该文件在 t7 前与 `HEAD` 逐字节相同」）。**t7 的修复一旦被提交
（`fd51023`）⇒ `HEAD` 就含 t7 的改动 ⇒ 回退变成 no-op ⇒ `tree-before` 与 `tree-after`
在 `mes_service.py` 上完全相同 ⇒ 本 diff 的「修复前/修复后」判据**空转**且不可复算**
（t9 F-3 实测登记）。

**修正（只改「从哪个提交取回退源文件」，UD-0…UD-5 的期望值与 SPEC_DEFECTS/KNOWN_FLIPS
一字未动）**：
- `PRE_FIX_REV` = `2c6dbfd66a43aebf6733500b5579436f7e8d8da0`（= t7/阶段A 修复前最后一个提交；
  `fd51023 == `修复提交` ⇒ `2c6dbfd == fd51023^`），可用 `WMS_PREFIX_REV` 覆盖；
- 代码里不再出现 `HEAD:` 取回退源；
- 新增**可复算性前置（precondition，不是新判据、不改口径）**：钉住的 `mes_service.py` blob
  必须与 `HEAD` 的同名 blob **不同**，否则回退是 no-op、判据空转 ⇒ 该前置报红。

## 判据
1. `tree-before` 的红链集合 == 冻结基线（`evidence/uat/uat_chains.json`）的红链集合（说明回退干净）；
2. `tree-after` 中基线红链全部转绿，且基线绿链**一条都不变红**；
3. 已知**预期翻转**单独列出（DEC-1 §1.4 序 3 改判 / §1.4 序 1 生效），不计入「变红」：
   `P0-2.5`（pending 无在办单据 ⇒ 由「拒收」改为「放行」，DEC-1 §1.6 P1 / A-45）、
   `P0-3.3`（静态佐证「开关零读取点」⇒ 修复后必然变成「有读取点」，该断言本身在断言缺陷）、
   `P0-2.1`（该实例在 fail 落地后按 §1.4 序 1 必须拒收，其「放行」前提已被 DEC-1 取代）。

## 用法（仓库根目录；A-40：复跑换 `HARNESS_RUN_ID`）
    $env:HARNESS_RUN_ID='w2w3-uatdiff-1'
    python -B test-reports-2026-10/harness/w2w3_uatdiff.py
    python -B test-reports-2026-10/harness/w2w3_uatdiff.py --verify-only   # 只构造并验证两棵树
    python -B test-reports-2026-10/harness/w2w3_uatdiff.py --baseline <PATH>  # 诊断：换基线来源（阴性对照）

## ⚠ 冻结基线来源：「锚点与产物必须分离」（A-70 三步登记，触发项 V-15/F1）

**旧来源（已废弃，本脚本自 V-18 起【不再读取】）**：`test-reports-2026-10/evidence/uat/uat_chains.json`

- **病根**：该文件**既是**本判据的「冻结基线」**又是** `uat_chains.py` 会**原地写出**的活产物
  （`uat_chains.py` 直接写该路径，不经 `_env.save_evidence`，A-58 已登记）。V-12 在本轮下游
  复跑 uat_chains 时把它从 **33318 B / `360A8570…7DD23A`**（`run_id=t5-uat-final`，40 链
  34 通过 / 6 红）覆盖成 **128432 B / `8BCF0150…`**（84 链全绿）。
- **后果**：`frozen_reds` 变空 ⇒ `UD-0 / UD-1a / UD-1b / UD-3` 在**改前改后都红**，
  「红链集合一致」「仍红者 == SPEC_DEFECTS」「预期翻转 == KNOWN_FLIPS」全部失去可比对象。
  该缺陷与 A-70/A-79 的「修复前树钉显式提交号」修正**无关**（V-15/t16 报出）。
- **通用纪律（captain 裁定）**：凡「既是冻结基线、又是会被脚本原地写出的活产物」的文件，
  判据**必须从不可变归档快照读取**，不得从 live 路径读取。同族病史：A-89（归档自反馈环）、
  A-110（`write_suite.py` 无 `--out`）、N-1（锚点与 `LOCKED` 语义互斥）。
- **方案 (b) 已否决**：按新基线（84 链全绿）重写 `UD-0…UD-4` 期望值 = 让判据拿「新全绿状态」
  比它自己 ⇒ 判据丧失意义、变相不可证伪（A-106/A-107 同族）。

**新来源（唯一合法来源）**：不可变预冻结归档副本

    test-reports-2026-10/evidence/_phaseB-prefreeze/20261007-220640/uat/uat_chains.json

- **钉值（现场复算，A-91）**：`bytes == 33318` 且
  `SHA256 == 360A8570BC0080A2984A59AD945B2C837AD96ACF7B55E6242AE7E2C6417DD23A`（= t1 锚点值）。
- **可复算命令**：
  `python -c "import hashlib;d=open(r'test-reports-2026-10/evidence/_phaseB-prefreeze/20261007-220640/uat/uat_chains.json','rb').read();print(len(d), hashlib.sha256(d).hexdigest().upper())"`
- **回退步骤**（仅当 captain 重新裁定基线来源时）：
  `git checkout -- test-reports-2026-10/harness/w2w3_uatdiff.py` 即可回到「读 live 路径」的旧行为；
  回退后 `UD-0/UD-1a/UD-1b/UD-3/UD-4` 会重新变红（V-15/F1 复现），**不得**把红当作回归。
- **不变量**：`UD-0/UD-1a/UD-1b/UD-3/UD-4` 的**期望值一字未改**（见下表）；本修正只改「基线从哪读」。

### 改动前后：UD-0…UD-4 期望值逐条对照（证明只改了来源路径）

| 判据 | 期望表达式（改动前 = 改动后，**逐字未变**） | 基线来源：改前 → 改后 |
| --- | --- | --- |
| `UD-0` | `before_reds == frozen_reds` | `evidence/uat/uat_chains.json`（live）→ 归档副本 |
| `UD-1a` | `{'P0-1.7','P0-1.8','P0-4.2','P0-4.4'}.issubset(set(red_to_green))` | 同上 |
| `UD-1b` | `set(still_red) == set(SPEC_DEFECTS) and not unexplained_reds` | 同上 |
| `UD-3` | `set(green_to_red) == set(KNOWN_FLIPS)` | 同上 |
| `UD-4` | `len(v_after) == len(frozen_v) == 40` | 同上（`frozen_v` 由该来源读出） |
| `UD-PIN` | 「修复前树」取源 = 钉死提交（V-15 新增，非本次改动） | — |
| `UD-BASE` | **本次新增的可复算性前置**：基线来源 = 归档副本且 bytes+SHA256 == t1 钉值 | — |

> 说明：`UD-BASE` 是**前置**（precondition），不是新判据口径 —— 上述 5 条的期望值一字未动，
> 它只保证这 5 条**不是拿无效基线在比**（基线缺失/哈希不符时前置报红，绝不静默回落 live）。

## ⚠ 双跑一致性的判定口径（F3，方法纪律）

`uat_chains.py` 会在产物里写入**自己的** `run_id` 与起止时间戳 ⇒ 同一命令两次跑出的
`uat_chains.before.json / .after.json` **逐字节必然不同**。故「双跑一致」一律按
**【红集 / 实质读数 / 判据集合】逐条比对**判定，**不得**用文件 SHA256 判「双跑不一致」。

## ⚠ 已登记的残余局限（V-18 / F1b；**如实登记，不得伪装通过**）

本脚本在 V-18 完成基线来源分离后，**仍有 4 条判据为红且结构性不可满足**：
`UD-0`（`before_reds == frozen_reds`）、`UD-1b`（`still_red == SPEC_DEFECTS`）、
`UD-3`（`green_to_red == KNOWN_FLIPS`）、`UD-4`（`len(v_after) == len(frozen_v) == 40`）。
**退出码仍为 1** —— 这些红**不**被豁免、**不**自动通过（代码里没有任何「已知红 ⇒ 放行」的分支）。

**根因 = 两条「已授权」的资产演进晚于冻结基线**（与 V-15 的钉修、与 V-18 的基线来源分离
**均无关**）：

| # | 演进 | 授权 | 对本脚本的影响 |
| --- | --- | --- | --- |
| ① | t9 重写 **15 处冻结断言**（含 uat 的 `P0-1.6`/`P0-3.1` 与 `P0-2.1`/`P0-2.5`/`P0-3.3`） | **A-66 / A-68** | 这 5 条在当前语料下**全部 `passed`** ⇒ `still_red` 变空、`green_to_red` 变空 ⇒ `UD-1b`/`UD-3` 的旧前提（「仍红」/「预期变红」）已不存在。**属进展，不是回归。** |
| ② | V-12（t13/A-105）把语料由 **40 链扩到 84 链**（纯追加，既有 40 条期望值逐字节不变） | A-105 | 本次比较运行的是**当前语料**（after 84 / before 76），而基线记录的是 **40 链** ⇒ `UD-0` 的集合相等与 `UD-4` 的 `== 40` 不可满足（before 的 11 条红里有 **5 条在基线里根本不存在**：`APPEND.1`/`B7`/`FLIP.SUM`/`P0-3.ERR`/`V12-链B-ERR`）。 |

**读法纪律（下游必须遵守）**：
1. **不得**把 `UD-0/UD-1b/UD-3/UD-4` 当作绿；
2. **不得**把其红点归因到 V-15（`UD-PIN` 钉修）或 V-18（`UD-BASE` 基线分离）的资产修正；
3. 那两条修正的效果**可单独验证**：`UD-PIN`、`UD-BASE` 以及 `UD-1a`（本次由红转绿）均 PASS。

**后续归属**：由 captain 另立任务处理（截至本次检查，`t20` 已用于 V-19/write_suite 白名单面，
语料/UD-* 重定的后续任务 id 以 captain 指派为准）。候选方案：把**语料**也钉到同一不可变时代
（A-70 式钉显式提交）；**不得**按新语料重写期望值（那会使判据不可证伪，A-106/A-107 同族）。

**运行期如实标注**：当且仅当失败集恰为上述 4 条时，脚本会额外打印
`[residual]` 一行并在证据里写 `residual_registered`（含实测根因读数），**仅作标注**——
不改变任何判据的 `ok`、不改变退出码。
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPORTS_ROOT = os.path.dirname(HERE)
REPO_ROOT = os.path.dirname(REPORTS_ROOT)
SCRIPTS_DIR = os.path.join(REPO_ROOT, 'scripts')
sys.path.insert(0, HERE)

from _env import (  # noqa: E402
    REAL_DB, REAL_DB_SHA256_EXPECTED, RUN_ID, ensure_dir, run_child, save_evidence,
    sha256_file, tmp_dir,
)

#: ── 冻结基线来源：不可变归档副本（A-70 三步登记；触发项 V-15/F1，见模块 docstring）──────
#: 旧来源（已废弃，**本脚本自 V-18 起不再读取**）：evidence/uat/uat_chains.json
#:   —— 它既是冻结基线又是 uat_chains.py 原地写出的活产物 ⇒ 被下游覆盖后判据失去可比对象。
FROZEN_UAT_LIVE_SUPERSEDED = os.path.join(REPORTS_ROOT, 'evidence', 'uat', 'uat_chains.json')
FROZEN_UAT_ARCHIVE = os.path.join(REPORTS_ROOT, 'evidence', '_phaseB-prefreeze',
                                  '20261007-220640', 'uat', 'uat_chains.json')
#: 唯一合法来源 = 归档副本（`--baseline` 可换成诊断用路径，默认恒为归档副本）。
#: 保留 `FROZEN_UAT` 这个名字只作 **compat 别名**，它现在指向归档副本（不再是 live 路径）。
FROZEN_UAT = FROZEN_UAT_ARCHIVE
#: 归档副本的钉值（现场复算；= t1 锚点值）。缺失/不符 ⇒ 前置 UD-BASE 报红，绝不回落 live。
FROZEN_UAT_BYTES = 33318
FROZEN_UAT_SHA256 = ('360A8570BC0080A2984A59AD945B2C837AD96ACF7B55E6242AE7E2C6417DD23A')
TREES_ROOT = os.path.join(tmp_dir('trees'))
TREE_BEFORE = os.path.join(TREES_ROOT, 'before')
TREE_AFTER = os.path.join(TREES_ROOT, 'after')

#: ── A-70：「修复前树」钉**显式提交号**，不得依赖移动的 HEAD ────────────────────────────
#: 修复前最后一个提交 = 阶段A 一次性修复提交 fd51023 的唯一父提交（`fd51023^`）。
#: 严禁改回 `HEAD:` —— t7 修复一旦被提交，`HEAD` 就含 t7，「修复前树」必失真（t9 F-3）。
PRE_FIX_REV = '2c6dbfd66a43aebf6733500b5579436f7e8d8da0'
PRE_FIX_REV_SHORT = PRE_FIX_REV[:7]
FIX_COMMIT_REV = 'fd5102360b3777d8ec2a0fb2610b2abbc2119df6'
PRE_FIX_REV_ENV = 'WMS_PREFIX_REV'
#: 回退源文件（t7 前与钉死的修复前提交逐字节相同 ⇒ 可整文件回退）
REVERT_SOURCE_FILE = 'app/services/mes_service.py'

#: ── 已登记的残余局限（V-18/F1b）：「结构性不可满足」的判据集合 ───────────────────────────
#: 仅用于**如实标注**（见模块 docstring 与 `residual_registered`）；**不参与判据、不改退出码**。
#: 根因 = A-66/A-68 授权 t9 重写 15 处冻结断言 + V-12/A-105 授权语料 40→84 链（纯追加）。
KNOWN_RESIDUAL = ('UD-0', 'UD-1b', 'UD-3', 'UD-4')

KNOWN_FLIPS = {
    'P0-2.5': 'pending 无在办单据 ⇒ 改判为放行（DEC-1 §1.6 P1 / §1.4 序 3 / A-45）',
    'P0-3.3': '静态佐证断言「开关零读取点」= 在断言缺陷本身；修复后必有读取点（AC-04-e）',
    'P0-2.1': '该实例 fail 落地后按 §1.4 序 1 必须拒收（「NULL ⇒ 放行」前提已被 DEC-1 取代）',
}

#: 冻结链里**断言本身写错**、任何正确实现都不可能使其转绿的两格（不掩盖：逐条给出机读理由与
#: 「同一业务含义在本轮的替代证据」）。它们不是产品缺陷，也不能算产品通过 —— 属 t9/资产侧待改。
SPEC_DEFECTS = {
    'P0-1.6': {
        'why': '断言点在 p0_1_report_and_fail 内（uat_chains.py:335-340），即「报工后、任何质检结论'
               '落库**之前**」；DEC-1 §1.2 规定此刻 `quality_status` 必须仍是 NULL（N1/AC-18-NEG/RC-4）'
               ' ⇒ 期望「已写 fail」与 DEC-1 直接冲突，任何正确实现都不会转绿。',
        'covered_by': '链内 P0-1.8（同一实例、结论落库后由 NULL 变 fail，本轮已转绿）'
                      ' + 本任务 w2w3_probe 的 AC18-1/AC18-2/AC18-3（含定位断言）',
    },
    'P0-3.1': {
        'why': '夹具按 `notes` 标记（`_uat 返工记录`）造「返工记录」，而 DEC-2 §2.2 **明确否决** notes'
               ' 标记（报工链不写 notes），选定 R1∨R2（NC.rework_task_id / global_sn）；且断言用的是'
               '链内**自己重算**的 `piecework_formula`（uat_chains.py:566-587 与 :608），不是产品路径'
               ' ⇒ 夹具与断言双重与 DEC-2 冲突，任何正确实现都不会转绿。',
        'covered_by': '本任务 w2w3_probe 的 amounts 段（DEC-2 §2.2 合规夹具：NC.rework_task_id + '
                      'global_sn 关联）：AC26-a（两态差 ≠ 0）、AC25-a（false 剔除额 == 返工贡献）、'
                      'AC04-d-http（S1 真端点页面 >60.00< / >360.00<）、AC04-d（S1 == S2）',
    },
}

#: t7 的改动（文件 → 反向替换对）；mes_service.py 用**钉死的修复前提交**整文件回退（A-70）
REVERSE_EDITS = {
    'app/main/routes.py': (
        (
            'from app.services.search_service import SearchService\n'
            '# DEC-2 §2.5：计件金额的**唯一**口径函数（S1/S3/S4 与 models.Employee.total_salary 同源；\n'
            '# 返工是否计入由 SystemConfig(\'quality.rework_counts_piecework\') 在该函数内唯一决定）\n'
            'from app.services.mes_service import piecework_amount\n',
            'from app.services.search_service import SearchService\n',
        ),
        (
            '    daily_piecework = piecework_amount(daily_production)',
            '    daily_piecework = sum(record.quantity * record.process.price '
            'for record in daily_production)',
        ),
        (
            '    monthly_piecework = piecework_amount(monthly_production)',
            '    monthly_piecework = sum(record.quantity * record.process.price '
            'for record in monthly_production)',
        ),
        (
            '            piecework = piecework_amount(production_records)',
            '            piecework = sum(record.quantity * record.process.price '
            'for record in production_records)',
        ),
        (
            '                    if (bi.status or \'\') == \'scrapped\':\n'
            '                        # DEC-1 §1.3：报废是**终态** —— 后续报工不得把它改回 completed/in_progress\n'
            '                        # （否则 quality_status 复位成 pass 后该产出会被放行，违反 RC-5/RC-11）\n'
            '                        current_app.logger.warning(\n'
            '                            f\'实例 {bi.product_code} 已报废（终态），本次报工不同步实例状态\')\n'
            '                    elif task.status == \'completed\' and bi.status != \'completed\':\n',
            '                    if task.status == \'completed\' and bi.status != \'completed\':\n',
        ),
    ),
    'app/models.py': (
        (
            '        # 计件工资计算（口径唯一：app.services.mes_service.piecework_amount —— '
            '返工记录是否计入由\n'
            '        # SystemConfig(\'quality.rework_counts_piecework\') 决定；本属性不得再写一份过滤，\n'
            '        # 否则会出现「主表变了、员工总工资没变」的不一致，见 07b DEC-2 §2.5 / AC-04-d）\n'
            '        from app.services.mes_service import piecework_amount  '
            '# 函数内导入：避免 models ↔ services 循环依赖\n'
            '        piecework = piecework_amount(list(self.production_records))\n',
            '        # 计件工资计算\n'
            '        piecework = sum(record.quantity * record.process.price '
            'for record in self.production_records)\n',
        ),
    ),
    'app/main/stock.py': (
        (
            '        # DEC-2 §2.3/§2.4：返工件数与报废件数是**两个独立可选入参**（`16` §11 补记：不得合并）。\n'
            '        # 缺省即各自走默认口径；非法值（0/负数/非整数）由 mes_service 抛 ValueError ⇒ 下方 400。\n'
            '        rework_qty = data.get(\'rework_quantity\')\n'
            '        scrap_qty = data.get(\'scrap_quantity\')\n',
            '',
        ),
        (
            '            rework_quantity=int(rework_qty) if rework_qty not in (None, \'\') else None,\n'
            '            scrap_quantity=int(scrap_qty) if scrap_qty not in (None, \'\') else None,\n',
            '',
        ),
    ),
}

#: t6/t8 的标记（回退后必须仍然在位）
KEEP_MARKERS = (
    ('app/main/routes.py', 'WorkCenter, Consumable, ConsumableCategory', 't6 P-01 导入'),
    ('app/main/routes.py', 'def _reraise_http', 't8 P-09'),
    ('app/main/routes.py', "task.notes = data.get('notes'", 't8 P-08'),
    ('app/main/quality.py', 'def _reraise_http', 't8 P-09'),
    ('app/__init__.py', 'errorhandler(HTTPException)', 't8 P-12/P-13'),
)
#: t7 的标记（回退后必须消失）
T7_MARKERS = (
    ('app/services/mes_service.py', 'def apply_production_record_result', 't7 P-02/P-03'),
    ('app/services/mes_service.py', 'def reset_quality_status_after_disposal', 't7 P-07b'),
    ('app/services/mes_service.py', 'def piecework_amount', 't7 P-04'),
    ('app/services/mes_service.py', 'def scrap_material_plan', 't7 P-06'),
    ('app/main/routes.py', 'piecework_amount', 't7 P-04 接线'),
    ('app/models.py', 'piecework_amount', 't7 S2 接线'),
    ('app/main/stock.py', 'rework_quantity', 't7 入参透传'),
)


def read(path):
    with open(path, encoding='utf-8', errors='replace') as fh:
        return fh.read()


def baseline_guard(path, explicit=False):
    """**可复算性前置**（A-70：锚点与产物分离；触发项 V-15/F1）。

    基线来源必须是**不可变归档副本**，且现场复算的 bytes+SHA256 == 钉值。返回 `(ok, info)`：
    `ok=False` ⇒ 前置报红（`UD-BASE`）。**绝不**静默回落到 live 路径。
    """
    rel = os.path.relpath(path, REPO_ROOT).replace('\\', '/')
    info = {'path': rel, 'explicit': bool(explicit),
            'expected_bytes': FROZEN_UAT_BYTES, 'expected_sha256': FROZEN_UAT_SHA256,
            'default_source': os.path.relpath(FROZEN_UAT_ARCHIVE, REPO_ROOT).replace('\\', '/'),
            'live_superseded': os.path.relpath(FROZEN_UAT_LIVE_SUPERSEDED,
                                               REPO_ROOT).replace('\\', '/'),
            'live_read': False, 'bytes': None, 'sha256': None, 'status': None}
    if not os.path.exists(path):
        info['status'] = 'missing'
        return False, info
    b = open(path, 'rb').read()
    info['bytes'] = len(b)
    info['sha256'] = hashlib.sha256(b).hexdigest().upper()
    same_bytes = info['bytes'] == FROZEN_UAT_BYTES
    same_hash = info['sha256'] == FROZEN_UAT_SHA256
    info['status'] = 'ok' if (same_bytes and same_hash) else 'hash-mismatch'
    if not (same_bytes and same_hash):
        info['why'] = ('bytes %s != %s' % ('ok' if same_bytes else 'DIFF', FROZEN_UAT_BYTES))
        info['why'] += ' ; sha256 %s' % ('ok' if same_hash else 'DIFF')
    return (same_bytes and same_hash), info


def live_superseded_info():
    """记录 live 路径（已废弃来源）的**当前**状态 —— 仅作取证，**不参与**任何判据。"""
    p = FROZEN_UAT_LIVE_SUPERSEDED
    out = {'path': os.path.relpath(p, REPO_ROOT).replace('\\', '/'), 'read_as_baseline': False,
           'role': '已废弃的旧基线来源（本脚本不再读取；若它再次被下游覆盖，本判据不受影响）'}
    if os.path.exists(p):
        b = open(p, 'rb').read()
        out['bytes'] = len(b)
        out['sha256'] = hashlib.sha256(b).hexdigest().upper()
        out['t1_pin_bytes'] = FROZEN_UAT_BYTES
        out['matches_t1_pin'] = (len(b) == FROZEN_UAT_BYTES
                                 and out['sha256'] == FROZEN_UAT_SHA256)
    else:
        out['status'] = 'missing'
    return out


def write(path, text):
    with open(path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(text)


def pre_fix_rev():
    """「修复前树」要用的**显式提交号**（A-70）。默认 `PRE_FIX_REV`，可被 `WMS_PREFIX_REV` 覆盖。"""
    rev = (os.environ.get(PRE_FIX_REV_ENV) or '').strip() or PRE_FIX_REV
    return {'rev': rev,
            'source': 'env:%s' % PRE_FIX_REV_ENV if os.environ.get(PRE_FIX_REV_ENV) else 'const'}


def git_rev_parse(spec):
    """`git rev-parse <spec>` ⇒ 对象名（用于「回退源与 HEAD 是否真有差异」的前置）。"""
    proc = subprocess.run(['git', 'rev-parse', '--verify', spec], cwd=REPO_ROOT,
                          capture_output=True, text=True)
    return proc.stdout.strip() if proc.returncode == 0 else ''


def git_show(rel, dest, rev=None):
    """从**钉死的显式提交**取文件字节（A-70：绝不 `HEAD:`）。"""
    rev = rev or pre_fix_rev()['rev']
    ensure_dir(os.path.dirname(dest))
    with open(dest, 'wb') as fh:
        proc = subprocess.run(['git', 'show', '%s:%s' % (rev, rel)], cwd=REPO_ROOT, stdout=fh,
                              stderr=subprocess.DEVNULL)
    return proc.returncode


def build_tree(dest, revert_t7):
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    ensure_dir(dest)
    shutil.copytree(os.path.join(REPO_ROOT, 'app'), os.path.join(dest, 'app'),
                    ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copytree(os.path.join(REPO_ROOT, 'scripts'), os.path.join(dest, 'scripts'),
                    ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copy2(os.path.join(REPO_ROOT, 'config.py'), os.path.join(dest, 'config.py'))
    shutil.copy2(REAL_DB, os.path.join(dest, 'app.db'))
    harness_dest = os.path.join(dest, 'test-reports-2026-10', 'harness')
    ensure_dir(os.path.dirname(harness_dest))
    shutil.copytree(HERE, harness_dest, ignore=shutil.ignore_patterns('__pycache__'))
    ensure_dir(os.path.join(dest, 'test-reports-2026-10', 'evidence', 'uat'))
    ensure_dir(os.path.join(dest, 'test-reports-2026-10', '.tmp'))
    if not revert_t7:
        return {'tree': dest, 'reverted': False}
    # mes_service.py：t7 前与**钉死的修复前提交**逐字节相同 ⇒ 整文件回退（A-70：不用 HEAD）
    pin = pre_fix_rev()
    rc = git_show(REVERT_SOURCE_FILE,
                  os.path.join(dest, 'app', 'services', 'mes_service.py'), pin['rev'])
    #: 可复算性前置：钉住的 blob 必须与 HEAD 的同名 blob **不同**，否则回退是 no-op、判据空转
    pin_blob = git_rev_parse('%s:%s' % (pin['rev'], REVERT_SOURCE_FILE))
    head_blob = git_rev_parse('HEAD:%s' % REVERT_SOURCE_FILE)
    pin_distinct = bool(pin_blob) and bool(head_blob) and pin_blob != head_blob
    applied = {REVERT_SOURCE_FILE: {
        'mode': 'git-show-pinned-rev',
        'mode_renamed_from': 'git-show-HEAD',
        'rev': pin['rev'],
        'rev_source': pin['source'],
        'git_show_exit': rc,
        'pinned_blob': pin_blob,
        'head_blob': head_blob,
        'pin_distinct_vs_head': pin_distinct}}
    print('[tree-before] mes_service.py <- pinned rev %s (exit=%s) ; pin_distinct_vs_head=%s '
          '(pinned blob=%s / HEAD blob=%s)'
          % (pin['rev'][:12], rc, pin_distinct, (pin_blob or '?')[:12], (head_blob or '?')[:12]))
    if not pin_distinct:
        print('[tree-before] !!! 可复算性前置失败：钉住的 mes_service.py 与 HEAD 版本**相同** ⇒ '
              '整文件回退是 no-op、UD-0/UD-5 空转（A-70 类缺陷复发）')
    for rel, pairs in REVERSE_EDITS.items():
        path = os.path.join(dest, rel)
        text = read(path)
        rows = []
        for old, new in pairs:
            if old not in text:
                rows.append({'replaced': False, 'needle_head': old.splitlines()[0][:80]})
                continue
            text = text.replace(old, new, 1)
            rows.append({'replaced': True, 'needle_head': old.splitlines()[0][:80]})
        write(path, text)
        applied[rel] = rows
    return {'tree': dest, 'reverted': True, 'applied': applied}


def marker_report(tree):
    rows = []
    for rel, needle, why in KEEP_MARKERS:
        path = os.path.join(tree, rel)
        rows.append({'file': rel, 'needle': needle, 'why': why, 'kind': 'keep',
                     'present': needle in read(path) if os.path.exists(path) else False})
    for rel, needle, why in T7_MARKERS:
        path = os.path.join(tree, rel)
        rows.append({'file': rel, 'needle': needle, 'why': why, 'kind': 't7',
                     'present': needle in read(path) if os.path.exists(path) else False})
    return rows


def run_uat(tree):
    res = run_child([os.path.join(tree, 'test-reports-2026-10', 'harness', 'uat_chains.py')],
                    cwd=tree, timeout=3600, label='uat-' + os.path.basename(tree))
    out_path = os.path.join(tree, 'test-reports-2026-10', 'evidence', 'uat', 'uat_chains.json')
    data = None
    if os.path.exists(out_path):
        with open(out_path, encoding='utf-8') as fh:
            data = json.load(fh)
    return {'exit_code': res['exit_code'], 'stdout_tail': res['stdout'][-2500:],
            'stderr_tail': res['stderr'][-1200:], 'json_path': out_path, 'data': data,
            'real_db_unchanged': res['real_db_unchanged']}


def verdicts(data):
    if not data:
        return {}
    return {c['id']: c['status'] for c in data.get('checks', [])}


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError, OSError):
        pass
    parser = argparse.ArgumentParser(description='uat_chains 40-chain pre/post diff on tree copies')
    parser.add_argument('--verify-only', action='store_true')
    parser.add_argument('--baseline', default=None,
                        help='基线来源路径（默认 = 不可变归档副本 %s）。'
                             '显式指定时进入**诊断模式**：前置 UD-BASE 会如实报红但仍继续评估，'
                             '用于阴性对照（如喂 live 文件或篡改副本）。'
                             % os.path.relpath(FROZEN_UAT_ARCHIVE, REPO_ROOT).replace('\\', '/'))
    args = parser.parse_args(argv)

    baseline_path = os.path.abspath(args.baseline) if args.baseline else FROZEN_UAT_ARCHIVE
    baseline_ok, baseline_info = baseline_guard(baseline_path, explicit=bool(args.baseline))
    live_info = live_superseded_info()

    started = time.strftime('%Y-%m-%d %H:%M:%S')
    print('=' * 78)
    print('[uatdiff] RUN_ID=%s started=%s' % (RUN_ID, started))
    print('[uatdiff] frozen baseline = %s (%s bytes, sha256=%s)'
          % (baseline_info['path'], baseline_info['bytes'],
             (baseline_info['sha256'] or '-')[:16]))
    print('[uatdiff] baseline pin      : %d bytes / %s'
          % (FROZEN_UAT_BYTES, FROZEN_UAT_SHA256[:16] + '...'))
    print('[uatdiff] baseline status   : %s (explicit=%s)'
          % (baseline_info['status'], baseline_info['explicit']))
    print('[uatdiff] live(旧来源,已废弃): %s %s bytes, read_as_baseline=%s'
          % (live_info.get('bytes'), live_info.get('sha256', '-')[:16],
             live_info.get('read_as_baseline')))
    print('[uatdiff] real db sha256 = %s' % sha256_file(REAL_DB))
    print('=' * 78)

    #: 默认来源失效（缺失/哈希不符）⇒ **如实报红并报错退出**，绝不静默回落到 live 路径。
    if not baseline_ok and not baseline_info['explicit']:
        print('[uatdiff] FAIL 基线来源不可用：%s（status=%s）' % (baseline_info['path'],
                                                                 baseline_info['status']))
        print('[uatdiff] A-70：锚点与产物必须分离 —— 归档副本缺失/被改 ⇒ 无有效基线，'
              '拒绝运行（不得回落 live 路径 %s）' % live_info['path'])
        save_evidence('w2w3-uatdiff-baseline-invalid.json',
                      json.dumps({'run_id': RUN_ID, 'baseline': baseline_info,
                                  'live_superseded': live_info,
                                  'verdict': 'FAIL', 'reason': 'baseline-unavailable'},
                                 ensure_ascii=False, indent=1, default=str))
        print('[verdict] FAIL')
        return 1
    if not baseline_ok:
        print('[uatdiff] WARN 诊断模式（--baseline 显式指定）：前置 UD-BASE 将报红 —— %s'
              % baseline_info.get('why'))

    with open(baseline_path, encoding='utf-8') as fh:
        frozen = json.load(fh)
    frozen_v = verdicts(frozen)
    frozen_summary = frozen.get('summary')

    before = build_tree(TREE_BEFORE, revert_t7=True)
    after = build_tree(TREE_AFTER, revert_t7=False)
    before_markers = marker_report(TREE_BEFORE)
    after_markers = marker_report(TREE_AFTER)

    keep_ok_before = all(r['present'] for r in before_markers if r['kind'] == 'keep')
    t7_gone_before = all(not r['present'] for r in before_markers if r['kind'] == 't7')
    print('[tree-before] t6/t8 标记全在位=%s ; t7 标记全消失=%s' % (keep_ok_before, t7_gone_before))
    for r in before_markers:
        flag = ('OK' if ((r['present'] and r['kind'] == 'keep')
                         or (not r['present'] and r['kind'] == 't7')) else 'MISMATCH')
        print('   [%s] %-8s %-34s %s' % (flag, r['kind'], r['file'], r['why']))
    print('[tree-after] t6/t8/t7 标记全在位=%s'
          % all(r['present'] for r in after_markers))

    result = {'run_id': RUN_ID, 'started': started, 'frozen_summary': frozen_summary,
              'frozen_verdicts': frozen_v, 'before_tree': before, 'after_tree': after,
              'before_markers': before_markers, 'after_markers': after_markers,
              'keep_markers_ok_in_before': keep_ok_before,
              't7_markers_gone_in_before': t7_gone_before}
    #: A-70 可复算性前置（precondition）①：冻结基线来源 = 不可变归档副本（V-15/F1）
    base_check = ('UD-BASE 冻结基线来源 = 不可变归档副本且 bytes+SHA256 == t1 钉值'
                  '（缺失/不符即报红，不回落 live）',
                  baseline_ok,
                  'path=%s status=%s bytes=%s sha256=%s expected=%d/%s explicit=%s'
                  % (baseline_info['path'], baseline_info['status'],
                     baseline_info['bytes'],
                     (baseline_info['sha256'] or '?')[:16],
                     FROZEN_UAT_BYTES, FROZEN_UAT_SHA256[:16], baseline_info['explicit']))
    result['baseline'] = {'info': baseline_info, 'check': base_check[0], 'ok': baseline_ok,
                          'evidence': base_check[2], 'live_superseded': live_info}
    print('  [%s] %s -- %s' % ('PASS' if baseline_ok else 'FAIL', base_check[0], base_check[2]))
    #: A-70 可复算性前置（precondition）：回退源必须来自**钉死的显式提交**且与 HEAD 真有差异
    pin_info = (before.get('applied') or {}).get(REVERT_SOURCE_FILE) or {}
    pin_ok = bool(pin_info.get('pin_distinct_vs_head')) and pin_info.get('git_show_exit') == 0
    pin_check = ('UD-PIN 「修复前树」回退源的取源 = %s（rev_source=%s）且与 HEAD 版本**不同**'
                 % (pin_info.get('rev') or PRE_FIX_REV, pin_info.get('rev_source')),
                 pin_ok,
                 'rev=%s source=%s pinned_blob=%s head_blob=%s distinct=%s git_show_exit=%s'
                 % ((pin_info.get('rev') or '?')[:12], pin_info.get('rev_source'),
                    (pin_info.get('pinned_blob') or '?')[:12],
                    (pin_info.get('head_blob') or '?')[:12],
                    pin_info.get('pin_distinct_vs_head'), pin_info.get('git_show_exit')))
    result['pin'] = {'rev': PRE_FIX_REV, 'rev_env': PRE_FIX_REV_ENV,
                     'revert_source_file': REVERT_SOURCE_FILE, 'check': pin_check[0],
                     'ok': pin_ok, 'evidence': pin_check[2]}
    print('  [%s] %s -- %s' % ('PASS' if pin_ok else 'FAIL', pin_check[0], pin_check[2]))
    if args.verify_only:
        result['checks'] = [{'id': base_check[0], 'ok': baseline_ok, 'evidence': base_check[2]},
                            {'id': pin_check[0], 'ok': pin_ok, 'evidence': pin_check[2]}]
        result['verdict'] = 'PASS' if (baseline_ok and pin_ok) else 'FAIL'
        save_evidence('w2w3-uatdiff-verify.json',
                      json.dumps(result, ensure_ascii=False, indent=1, default=str))
        print('[verify-only] 两棵树已构造并验证；未跑 uat_chains')
        return 0 if (baseline_ok and pin_ok) else 1

    run_before = run_uat(TREE_BEFORE)
    run_after = run_uat(TREE_AFTER)
    v_before = verdicts(run_before['data'])
    v_after = verdicts(run_after['data'])
    result['run_before'] = {k: v for k, v in run_before.items() if k != 'data'}
    result['run_after'] = {k: v for k, v in run_after.items() if k != 'data'}
    result['run_before']['summary'] = (run_before['data'] or {}).get('summary')
    result['run_after']['summary'] = (run_after['data'] or {}).get('summary')
    result['verdicts_before'] = v_before
    result['verdicts_after'] = v_after

    frozen_reds = {k for k, v in frozen_v.items() if v != 'passed'}
    before_reds = {k for k, v in v_before.items() if v != 'passed'}
    after_reds = {k for k, v in v_after.items() if v != 'passed'}
    red_to_green = sorted(frozen_reds & {k for k in v_after if v_after[k] == 'passed'})
    green_to_red = sorted({k for k, v in frozen_v.items() if v == 'passed'
                           and v_after.get(k) != 'passed'})
    expected_flips = sorted(k for k in green_to_red if k in KNOWN_FLIPS)
    unexpected_red = sorted(k for k in green_to_red if k not in KNOWN_FLIPS)
    still_red = sorted(frozen_reds - set(red_to_green))
    spec_defect_reds = sorted(k for k in still_red if k in SPEC_DEFECTS)
    unexplained_reds = sorted(k for k in still_red if k not in SPEC_DEFECTS)
    after_raw = (run_after['data'] or {}).get('raw', {})
    before_raw = (run_before['data'] or {}).get('raw', {})
    substantive = {
        'quality_status_after_fail': {
            'before': (before_raw.get('p0_1_after_fail') or {}).get('batch_item_quality_status'),
            'after': (after_raw.get('p0_1_after_fail') or {}).get('batch_item_quality_status')},
        'nc_total_after_fail': {
            'before': (before_raw.get('p0_1_after_fail') or {}).get('nc_total'),
            'after': (after_raw.get('p0_1_after_fail') or {}).get('nc_total')},
        'rework_task_quantity': {
            'before': ((before_raw.get('p0_4') or {}).get('rework') or {}).get('rework_quantity'),
            'after': ((after_raw.get('p0_4') or {}).get('rework') or {}).get('rework_quantity')},
        'scrap_deducted': {
            'before': ((before_raw.get('p0_4') or {}).get('scrap') or {}).get('deducted'),
            'after': ((after_raw.get('p0_4') or {}).get('scrap') or {}).get('deducted')},
        'switch_read_sites': {
            'before': (before_raw.get('p0_3') or {}).get('switch_read_sites', {}).get(
                'read_sites', {}).get('quality.rework_counts_piecework'),
            'after': (after_raw.get('p0_3') or {}).get('switch_read_sites', {}).get(
                'read_sites', {}).get('quality.rework_counts_piecework')},
        'quality_status_before_any_conclusion': {
            'before': ((before_raw.get('p0_1_entities') or {}).get('batch_item') or {}).get(
                'quality_status'),
            'after': ((after_raw.get('p0_1_entities') or {}).get('batch_item') or {}).get(
                'quality_status')},
    }
    result.update({'frozen_reds': sorted(frozen_reds), 'before_reds': sorted(before_reds),
                   'after_reds': sorted(after_reds), 'red_to_green': red_to_green,
                   'green_to_red': green_to_red, 'expected_flips': expected_flips,
                   'unexpected_red': unexpected_red, 'still_red': still_red,
                   'spec_defect_reds': spec_defect_reds, 'unexplained_reds': unexplained_reds,
                   'spec_defects': SPEC_DEFECTS, 'substantive_deltas': substantive,
                   'after_total': len(v_after), 'frozen_total': len(frozen_v)})

    print('')
    print('[frozen baseline] total=%s passed=%s failed=%s'
          % ((frozen_summary or {}).get('total'), (frozen_summary or {}).get('passed'),
             (frozen_summary or {}).get('failed')))
    print('[run before] exit=%s total=%s passed=%s failed=%s'
          % (run_before['exit_code'], (run_before['data'] or {}).get('summary', {}).get('total'),
             (run_before['data'] or {}).get('summary', {}).get('passed'),
             (run_before['data'] or {}).get('summary', {}).get('failed')))
    print('[run after ] exit=%s total=%s passed=%s failed=%s'
          % (run_after['exit_code'], (run_after['data'] or {}).get('summary', {}).get('total'),
             (run_after['data'] or {}).get('summary', {}).get('passed'),
             (run_after['data'] or {}).get('summary', {}).get('failed')))
    print('[diff] frozen_reds=%s' % sorted(frozen_reds))
    print('[diff] red_to_green=%s' % red_to_green)
    print('[diff] green_to_red=%s (expected_flips=%s unexpected=%s)'
          % (green_to_red, expected_flips, unexpected_red))
    print('[diff] still_red=%s (spec_defects=%s unexplained=%s)'
          % (still_red, spec_defect_reds, unexplained_reds))
    print('[diff] substantive deltas = %s' % json.dumps(substantive, ensure_ascii=True,
                                                         sort_keys=True))
    print('[diff] before_reds == frozen_reds ? %s ; after_total == frozen_total ? %s'
          % (before_reds == frozen_reds, len(v_after) == len(frozen_v)))

    red_to_green_ok = {'P0-1.7', 'P0-1.8', 'P0-4.2', 'P0-4.4'}.issubset(set(red_to_green))
    substantive_ok = (
        substantive['quality_status_after_fail']['before'] is None
        and substantive['quality_status_after_fail']['after'] == 'fail'
        and (substantive['nc_total_after_fail']['before'] or 0) == 0
        and (substantive['nc_total_after_fail']['after'] or 0) == 1
        and substantive['rework_task_quantity'] == {'before': 1, 'after': 10}
        and substantive['scrap_deducted'] == {'before': 1.0, 'after': 2.0}
        and not substantive['switch_read_sites']['before']
        and len(substantive['switch_read_sites']['after'] or []) == 1
    )
    checks = [
        ('UD-0 冻结基线与 before 树红链集合一致（回退干净）', before_reds == frozen_reds,
         'frozen=%s before=%s' % (sorted(frozen_reds), sorted(before_reds))),
        ('UD-1a 可判定的 4 条基线红链全部转绿（P0-1.7/1.8/4.2/4.4）', red_to_green_ok,
         'red_to_green=%s' % red_to_green),
        ('UD-1b 其余 2 条基线红链是**断言/夹具写错**且已逐条给出理由（不掩盖、不改资产）',
         set(still_red) == set(SPEC_DEFECTS) and not unexplained_reds,
         'still_red=%s spec_defects=%s unexplained=%s' % (still_red, spec_defect_reds,
                                                          unexplained_reds)),
        ('UD-1c 同一业务含义的**实质读数**在链内 RAW 里也发生预期变化（字段/增量/件数/扣量/读取点）',
         substantive_ok, json.dumps(substantive, ensure_ascii=True, sort_keys=True)),
        ('UD-2 基线绿链无**非预期**变红', not unexpected_red, 'unexpected=%s' % unexpected_red),
        ('UD-3 预期翻转与 DEC-1 一致（P0-2.5/P0-3.3/P0-2.1）', set(green_to_red) == set(KNOWN_FLIPS),
         'green_to_red=%s' % green_to_red),
        ('UD-4 链总数不变（40 条）', len(v_after) == len(frozen_v) == 40,
         'after=%d frozen=%d' % (len(v_after), len(frozen_v))),
        ('UD-5 before 树不含 t7 改动、after 树含（t6/t8 标记两树都在位）',
         t7_gone_before and keep_ok_before, 't7_gone=%s keep_ok=%s' % (t7_gone_before, keep_ok_before)),
        pin_check,
        base_check,
    ]
    for cid, ok, ev in checks:
        print('  [%s] %s -- %s' % ('PASS' if ok else 'FAIL', cid, ev))
    result['checks'] = [{'id': cid, 'ok': bool(ok), 'evidence': ev} for cid, ok, ev in checks]
    failed = [cid for cid, ok, _ in checks if not ok]
    result['verdict'] = 'PASS' if not failed else 'FAIL'

    #: ── 已登记的残余局限标注（V-18/F1b）──────────────────────────────────────────────
    #: **仅作如实标注**：不改变任何判据的 ok、不改变退出码（下方仍 return 1）。当且仅当失败集
    #: 恰为 KNOWN_RESIDUAL 时打印一行，并把实测根因读数写进证据，防止下游把红点误读成回归。
    residual_hit = sorted(cid.split()[0] for cid in failed)
    residual_expected = (set(residual_hit) == set(KNOWN_RESIDUAL))
    aft_chains = len(v_after)
    base_chains = len(frozen_v)
    stale_chain_status = {k: v_after.get(k) for k in ('P0-1.6', 'P0-3.1', 'P0-2.1', 'P0-2.5',
                                                      'P0-3.3')}
    result['residual_registered'] = {
        'expected_residual_set': list(KNOWN_RESIDUAL),
        'observed_failed': residual_hit,
        'matches': residual_expected,
        'cause': '链语料漂移（同族更深缺陷）：A-66/A-68 授权 t9 重写 15 处冻结断言 + '
                 'V-12/A-105 授权语料 40→84 链（纯追加）⇒ 本基线下这 4 条结构性不可满足',
        'readings': {'baseline_chains': base_chains, 'after_chains': aft_chains,
                     'before_reds_not_in_baseline':
                         sorted(set(before_reds) - set(frozen_v)),
                     'stale_expectation_chains_status_in_after': stale_chain_status},
        'reading_discipline': ['不得把 UD-0/UD-1b/UD-3/UD-4 当作绿',
                               '不得把其红点归因到 V-15（UD-PIN）或 V-18（UD-BASE）的资产修正',
                               'UD-PIN / UD-BASE / UD-1a PASS 可单独证明上述两项修正已生效'],
        'follow_up': 'captain 另立任务（方案：4 条按 A-70 标 superseded + 新立可证伪的替代判据集；'
                     '明确否决「按新语料重写期望值」与「把语料钉回 t5 时代」）',
    }
    print('  [residual] 已登记的残余局限：observed_failed=%s matches_expected_set=%s '
          '(baseline_chains=%d / after_chains=%d)' % (residual_hit, residual_expected,
                                                      base_chains, aft_chains))
    print('  [residual] 根因 = 链语料漂移（A-66/A-68 断言重写 + V-12/A-105 扩链）⇒ 退出码仍为 1；'
          '**不得当绿、不得归因 V-15/V-18**，后续归属 = captain 另立任务')

    saved = [save_evidence('w2w3-uatdiff-result.json',
                           json.dumps(result, ensure_ascii=False, indent=1, default=str))]
    for tag, run in (('before', run_before), ('after', run_after)):
        if run['data'] is not None:
            saved.append(save_evidence(
                'uat_chains.%s.json' % tag,
                json.dumps(run['data'], ensure_ascii=False, indent=1, default=str)))
    real_after = sha256_file(REAL_DB)
    print('[real-db] %s -> %s unchanged=%s'
          % (REAL_DB_SHA256_EXPECTED[:12], real_after[:12], real_after == REAL_DB_SHA256_EXPECTED))
    for path in saved:
        print('[evidence] -> %s' % os.path.relpath(path, REPO_ROOT).replace('\\', '/'))
    print('[verdict] %s' % result['verdict'])
    return 0 if result['verdict'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
