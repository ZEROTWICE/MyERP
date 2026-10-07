"""w2w3_uatdiff.py — 用**树副本**做 `uat_chains` 40 条链的「修复前 / 修复后」逐条 diff。

## 为什么用树副本（关键工程约束）
`uat_chains.py` **直接写** `<repo>/test-reports-2026-10/evidence/uat/uat_chains.json`（未经
`_env.save_evidence`，A-58 已登记）⇒ 在真实仓库里复跑会**原地覆盖** t5 时代的冻结证据（`modified` 违规，
不可恢复）。本脚本因此把 `app/ + scripts/ + config.py + app.db + harness/` 复制到
`.tmp/<RUN_ID>/tree-*/`，在两个副本里各跑一次 ⇒ **真实 evidence 树零写入**。

## 两棵树的构造与「只差 t7」的证明
- `tree-after` = 当前工作树副本（含 t6/t8 已完成修复 + t7 本次修复）；
- `tree-before` = 同一副本，**只把 t7 的 5 处改动逐字回退**（`mes_service.py` 用 `git show HEAD:` 整 файл
  回退——该文件在 t7 前与 HEAD 逐字节相同；`routes.py`/`models.py`/`stock.py` 用精确反向替换，保留
  t6 的第 6 行导入与 t8 的 P-08/P-09/P-12/P-13 标记）。
- 构造后**逐项断言**两棵树的 t6/t8 标记仍在位、t7 标记已消失（见 `--verify-only`），并把结论落证据。

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
"""
import argparse
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

FROZEN_UAT = os.path.join(REPORTS_ROOT, 'evidence', 'uat', 'uat_chains.json')
TREES_ROOT = os.path.join(tmp_dir('trees'))
TREE_BEFORE = os.path.join(TREES_ROOT, 'before')
TREE_AFTER = os.path.join(TREES_ROOT, 'after')

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

#: t7 的改动（文件 → 反向替换对）；mes_service.py 用 git HEAD 整файл回退
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


def write(path, text):
    with open(path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(text)


def git_show(rel, dest):
    ensure_dir(os.path.dirname(dest))
    with open(dest, 'wb') as fh:
        proc = subprocess.run(['git', 'show', 'HEAD:' + rel], cwd=REPO_ROOT, stdout=fh,
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
    # mes_service.py：t7 前与 HEAD 逐字节相同 ⇒ 整文件回退
    rc = git_show('app/services/mes_service.py',
                  os.path.join(dest, 'app', 'services', 'mes_service.py'))
    applied = {'app/services/mes_service.py': {'mode': 'git-show-HEAD', 'git_show_exit': rc}}
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
    args = parser.parse_args(argv)

    started = time.strftime('%Y-%m-%d %H:%M:%S')
    print('=' * 78)
    print('[uatdiff] RUN_ID=%s started=%s' % (RUN_ID, started))
    print('[uatdiff] frozen baseline = %s (sha256=%s)'
          % (os.path.relpath(FROZEN_UAT, REPO_ROOT).replace('\\', '/'), sha256_file(FROZEN_UAT)))
    print('[uatdiff] real db sha256 = %s' % sha256_file(REAL_DB))
    print('=' * 78)

    with open(FROZEN_UAT, encoding='utf-8') as fh:
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
    if args.verify_only:
        save_evidence('w2w3-uatdiff-verify.json',
                      json.dumps(result, ensure_ascii=False, indent=1, default=str))
        print('[verify-only] 两棵树已构造并验证；未跑 uat_chains')
        return 0

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
    ]
    for cid, ok, ev in checks:
        print('  [%s] %s -- %s' % ('PASS' if ok else 'FAIL', cid, ev))
    result['checks'] = [{'id': cid, 'ok': bool(ok), 'evidence': ev} for cid, ok, ev in checks]
    failed = [cid for cid, ok, _ in checks if not ok]
    result['verdict'] = 'PASS' if not failed else 'FAIL'

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
