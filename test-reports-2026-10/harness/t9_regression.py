# -*- coding: utf-8 -*-
"""t9 修复后回归编排器：在**树副本**里复跑会直接写盘的 suite，在真实仓库里复跑守卫型探针。

## 为什么分两类（A-58）
`uat_chains.py` / `write_suite.py` / `api_matrix.py` / `measure_coverage.py` **直接写** `evidence/**`
（未走 `_env.save_evidence`）=> 在真实仓库复跑会**原地覆盖冻结证据**。本编排器把仓库复制到
`.tmp/<RUN_ID>/tree/`（含 `app/` `scripts/` `migrations/` `harness/` `config.py` `app.db`），
在这棵树里跑这四个 suite => **真实 evidence 树零写入**（`--- preflight verify` 的 `modified/deleted = 0`）。

`w1_p01_probe.py` / `w2w3_probe.py` / `w4_probe.py` 已走 `_env.save_evidence`（分 run 目录 + 守卫），
直接在真实仓库跑即可 => 证据落 `evidence/harness/<RUN_ID>/`。

## 用法（仓库根目录）
    $env:HARNESS_RUN_ID = 't9-rega-b1'
    python -B test-reports-2026-10/harness/t9_regression.py --stage suites
    python -B test-reports-2026-10/harness/t9_regression.py --stage probes
    python -B test-reports-2026-10/harness/t9_regression.py --stage ledger

## 判据
* 每一步记 argv / exit_code / 输出尾部 / 真实库 SHA 前后；
* 真实库 `app.db` 全程必须等于钉死 SHA（`_env.REAL_DB_SHA256_EXPECTED`），否则 exit 9；
* 任一步真实退出码非 0 也要留痕（不中断），由 ledger 阶段逐条判定。
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
sys.path.insert(0, HERE)

from _env import (  # noqa: E402
    REAL_DB, REAL_DB_SHA256_EXPECTED, RUN_ID, ensure_dir, run_child, save_evidence,
    sha256_file, tmp_dir,
)

TREE = os.path.join(tmp_dir('tree'), 'after')
TREE_REPORTS = os.path.join(TREE, 'test-reports-2026-10')
TREE_HARNESS = os.path.join(TREE_REPORTS, 'harness')
TREE_EVID = os.path.join(TREE_REPORTS, 'evidence')
TREE_RUN = os.path.join(TREE_EVID, 'harness', RUN_ID)

IGNORE = shutil.ignore_patterns('__pycache__', '*.pyc', '.tmp')
SKIP_TOP = {'.git', '.tmp', '.idea', '.vscode', 'node_modules', '__pycache__'}
SKIP_REPORTS = {'evidence', 'phase1-snapshot', '.tmp'}


def build_tree(dest):
    """整树复制（排除 .git/.tmp/__pycache__/evidence 与顶层报告 md/txt）。"""
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    ensure_dir(dest)
    for name in sorted(os.listdir(REPO_ROOT)):
        if name in SKIP_TOP:
            continue
        src = os.path.join(REPO_ROOT, name)
        dst = os.path.join(dest, name)
        if not os.path.isdir(src):
            shutil.copy2(src, dst)
            continue
        if name == 'test-reports-2026-10':
            ensure_dir(dst)
            for sub in sorted(os.listdir(src)):
                if sub in SKIP_REPORTS or sub.lower().endswith(('.md', '.txt')):
                    continue
                s2, d2 = os.path.join(src, sub), os.path.join(dst, sub)
                if os.path.isdir(s2):
                    shutil.copytree(s2, d2, ignore=IGNORE)
                else:
                    shutil.copy2(s2, d2)
        else:
            shutil.copytree(src, dst, ignore=IGNORE)
    for sub in ('uat', 'api', 'harness', 'analysis'):
        ensure_dir(os.path.join(TREE_EVID, sub))
    ensure_dir(TREE_RUN)
    return dest


# ---------------------------------------------------------------- 步骤定义
def tree_steps(tree_root=None):
    """树内步骤表。`tree_root` 决定 `--out` 落点（**必须**与被测树一致，否则会写坏另一棵树的证据）。"""
    reports = os.path.join(tree_root or TREE, 'test-reports-2026-10') \
        if tree_root else TREE_REPORTS
    run_dir = os.path.join(reports, 'evidence', 'harness', RUN_ID)
    shim = 'scripts/_sandbox_compat.py'
    return [
        ('functional_test', [shim, 'scripts/functional_test.py'], False),
        ('check_templates', ['scripts/check_templates.py'], False),
        ('check_migration_heads', ['scripts/check_migration_heads.py'], False),
        ('check_properties', ['scripts/check_properties.py'], False),
        ('route_inventory', ['scripts/route_inventory.py'], False),
        ('check_model_refs', ['scripts/check_model_refs.py'], False),
        ('check_db_bootstrap', ['scripts/check_db_bootstrap.py'], False),
        ('negative_matrix', ['test-reports-2026-10/harness/negative_matrix.py',
                             '--out', os.path.join(run_dir, 'negative_matrix.json')], False),
        ('write_suite', ['test-reports-2026-10/harness/write_suite.py'], False),
        ('api_matrix', ['test-reports-2026-10/harness/api_matrix.py'], False),
        ('uat_chains', ['test-reports-2026-10/harness/uat_chains.py'], True),
        ('run_gates', ['test-reports-2026-10/harness/run_gates.py', '--self-test',
                       '--out', os.path.join(run_dir, 'gates.json')], False),
        ('measure_coverage', ['test-reports-2026-10/harness/measure_coverage.py',
                              '--out', os.path.join(run_dir, 'coverage.json'),
                              '--copy-tag', 't9'], False),
    ]


def probe_steps():
    return [
        ('w1_p01_probe', ['test-reports-2026-10/harness/w1_p01_probe.py', '--scenario', 'all'],
         REPO_ROOT, {}),
        ('w2w3_probe', ['test-reports-2026-10/harness/w2w3_probe.py', '--scenario', 'all'],
         REPO_ROOT, {}),
        ('w4_probe_post', ['test-reports-2026-10/harness/w4_probe.py', '--phase', 'post',
                           '--scenario', 'all',
                           '--json', os.path.join(tmp_dir('w4'), 'w4_post_all.json')],
         REPO_ROOT, {}),
    ]


def run_step(label, args, cwd, with_uat_id):
    env = {}
    if with_uat_id:
        env['UAT_RUN_ID'] = '%s-uat' % RUN_ID
    before = sha256_file(REAL_DB)
    res = run_child(args, cwd=cwd, timeout=3600, extra_env=env, label='t9-' + label)
    after = sha256_file(REAL_DB)
    console = (
        '=' * 96 + '\n'
        '[t9] step=%s\n[t9] RUN_ID=%s\n[t9] cwd=%s\n[t9] argv=%s\n'
        '[t9] exit_code=%s duration_s=%s evidence_level=%s\n'
        '[t9] real_db before=%s after=%s unchanged=%s\n'
        '[t9] interpreter=%s\n' % (
            label, RUN_ID, cwd, res['argv_display'], res['exit_code'], res['duration_s'],
            res['evidence_level'], before, after, before == after == REAL_DB_SHA256_EXPECTED,
            sys.executable)
        + '=' * 96 + '\n--- stdout ---\n' + res['stdout']
        + '\n--- stderr ---\n' + res['stderr'] + '\n')
    path = save_evidence('step-%s.console.txt' % label, console)
    return {
        'label': label, 'cwd': cwd, 'argv': res['argv_display'], 'exit_code': res['exit_code'],
        'duration_s': res['duration_s'], 'evidence_level': res['evidence_level'],
        'stdout_tail': res['stdout'][-3000:], 'stderr_tail': res['stderr'][-1500:],
        'real_db_before': before, 'real_db_after': after,
        'real_db_unchanged': before == after == REAL_DB_SHA256_EXPECTED,
        'console_evidence': os.path.relpath(path, REPO_ROOT).replace('\\', '/'),
    }


def stage_suites(only):
    build_tree(TREE)
    rows = []
    for label, args, with_uat_id in tree_steps(TREE):
        if only and label not in only:
            continue
        print('[t9] === tree step %s ===' % label, flush=True)
        row = run_step(label, args, TREE, with_uat_id)
        print('[t9] %s exit=%s (%.1fs)' % (label, row['exit_code'], row['duration_s']), flush=True)
        rows.append(row)
    out = {'stage': 'suites', 'run_id': RUN_ID, 'tree': TREE, 'started': time.strftime('%Y-%m-%d %H:%M:%S'),
           'steps': rows}
    path = save_evidence('t9-suite-steps.json', json.dumps(out, ensure_ascii=False, indent=1))
    print('[t9] suites evidence -> %s' % os.path.relpath(path, REPO_ROOT).replace('\\', '/'))
    return 0


def stage_probes(only):
    rows = []
    for label, args, cwd, _env_extra in probe_steps():
        if only and label not in only:
            continue
        print('[t9] === probe step %s ===' % label, flush=True)
        row = run_step(label, args, cwd, False)
        print('[t9] %s exit=%s (%.1fs)' % (label, row['exit_code'], row['duration_s']), flush=True)
        rows.append(row)
    out = {'stage': 'probes', 'run_id': RUN_ID, 'started': time.strftime('%Y-%m-%d %H:%M:%S'),
           'steps': rows}
    path = save_evidence('t9-probe-steps.json', json.dumps(out, ensure_ascii=False, indent=1))
    print('[t9] probes evidence -> %s' % os.path.relpath(path, REPO_ROOT).replace('\\', '/'))
    return 0


def stage_before(only):
    """在**修复前的树副本**里复跑重写后的判据（可证伪性证据）。

    重写后的断言必须**对修复敏感**：在修复前树上必须报红，否则新判据本身就是恒真
    （"让基线变绿"而非"断言正确语义"）。

    ⚠ 为什么不用 `w2w3_uatdiff.build_tree(revert_t7=True)`：该工具的回退基准是 `git show HEAD:`，
    而阶段A的修复**已被 captain 提交**（`fd51023` / `3113f90`）⇒ `HEAD` 现在**已含** t7 的改动，
    该回退**不再生效**（实测：回退树里 `mes_service.py` 仍含 `piecework_amount`/
    `rework_counts_piecework`）。⇒ 本函数改为按**提交 `2c6dbfd`（阶段A修复前最后提交）**
    覆盖 5 个生产文件，重建「修复前」的这 5 个面（其余文件保持 HEAD，故本树只用于
    **这 5 个文件修复面**的可证伪性判定，不作历史树使用）。
    """
    base_rev = os.environ.get('T9_BASE_REV', '2c6dbfd')
    tree_before = os.path.join(tmp_dir('tree'), 'before-prefix-' + base_rev)
    build_tree(tree_before)
    overlaid = []
    for rel in ('app/services/mes_service.py', 'app/main/routes.py', 'app/models.py',
                'app/main/stock.py', 'app/main/quality.py'):
        dest = os.path.join(tree_before, rel.replace('/', os.sep))
        with open(dest, 'wb') as fh:
            proc = subprocess.run(['git', 'show', '%s:%s' % (base_rev, rel)], cwd=REPO_ROOT,
                                  stdout=fh, stderr=subprocess.DEVNULL)
        overlaid.append({'file': rel, 'git_show_exit': proc.returncode})
    print('[t9] before-tree = HEAD + %s 覆盖 %d 个文件' % (base_rev, len(overlaid)), flush=True)
    rows = []
    for label, args, with_uat_id in tree_steps(tree_before):
        if label not in (only or {'uat_chains', 'negative_matrix', 'write_suite'}):
            continue
        print('[t9] === before-prefix step %s ===' % label, flush=True)
        row = run_step(label, args, tree_before, with_uat_id)
        print('[t9] %s exit=%s (%.1fs)' % (label, row['exit_code'], row['duration_s']), flush=True)
        rows.append(row)
    out = {'stage': 'before-prefix', 'run_id': RUN_ID, 'tree': tree_before, 'base_rev': base_rev,
           'overlaid': overlaid, 'started': time.strftime('%Y-%m-%d %H:%M:%S'), 'steps': rows}
    path = save_evidence('t9-beforeprefix-steps.json',
                         json.dumps(out, ensure_ascii=False, indent=1))
    print('[t9] before-prefix evidence -> %s' % os.path.relpath(path, REPO_ROOT).replace('\\', '/'))
    return 0


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError, OSError):
        pass
    ap = argparse.ArgumentParser(description='t9 regression orchestrator')
    ap.add_argument('--stage', required=True, choices=('suites', 'probes', 'tree', 'ledger', 'before-prefix'))
    ap.add_argument('--only', default='', help='逗号分隔的步骤 label 过滤')
    args = ap.parse_args(argv)
    only = {x.strip() for x in args.only.split(',') if x.strip()}

    print('=' * 96)
    print('[t9] RUN_ID=%s stage=%s cwd=%s' % (RUN_ID, args.stage, os.getcwd()))
    print('[t9] real_db sha256 = %s (pinned %s)' % (sha256_file(REAL_DB), REAL_DB_SHA256_EXPECTED))
    print('=' * 96)

    if args.stage == 'suites':
        rc = stage_suites(only)
    elif args.stage == 'probes':
        rc = stage_probes(only)
    elif args.stage == 'tree':
        build_tree(TREE)
        print('[t9] tree built at %s' % TREE)
        rc = 0
    elif args.stage == 'before-prefix':
        rc = stage_before(only)
    else:
        import t9_ledger
        rc = t9_ledger.main([])

    real_after = sha256_file(REAL_DB)
    print('[t9] real_db after = %s unchanged=%s' % (real_after, real_after == REAL_DB_SHA256_EXPECTED))
    return 9 if real_after != REAL_DB_SHA256_EXPECTED else rc


if __name__ == '__main__':
    sys.exit(main())
