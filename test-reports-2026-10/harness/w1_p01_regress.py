"""w1_p01_regress.py — P-01 修复的「六条回归」机械判据 + 证据落盘（只读真实库）。

## 为什么需要它
captain 的 t6 任务书 §四给了六条回归要求；「逐项不变」不能靠人读输出，必须让脚本断言：

| id | 判据 |
| --- | --- |
| R1 | `scripts/functional_test.py`（经 `_sandbox_compat.py` shim）exit 0 且 `结果：109 通过 / 0 失败`（`--run-heavy` 时才真跑；否则复用 `--functional-txt`） |
| R2 | `scripts/check_templates.py` exit 0 且 `parsed 87 files` / `44 declared / 40 used in templates / 44 used on routes` / `landing 5` / `RESULT: OK` |
| R3 | `scripts/check_migration_heads.py` exit 0 且 `HEADS=['p1nonctarget']` / `head_count=1` / `revisions=35` |
| R4 | `scripts/check_properties.py` exit 0 且 `已扫描 23 个文件，模型类 74 个` / `RESULT: OK` |
| R5 | `scripts/check_model_refs.py`（新增门禁）exit 0 且 `violations 0` / `RESULT: OK` |
| R6 | `scripts/route_inventory.py`（shim）exit 0 且 `total rules=271` / `duplicate (method,path) registrations=0` |
| R7 | `scripts/check_db_bootstrap.py`（shim）exit 0 且 `账号数（经自举导入到空库）= 64` / `直接拷贝 6712 行，跳过 0 张表`（补导入后启动自愈必须仍然成功） |
| R8 | `harness/run_gates.py` 的 **`expected_lock` / `summary` / 每个 gate 的 checks 逐项 / 退出码语义** 与 E-04 基线 `w0-e04-t5-final/gates.json` **完全相同**（A-62 的 `probe_unexpected=1` 属环境依赖探针的既有预期） |
| R9 | 真实库 `app.db` 全程钉死 `F5DA2306…`；仓库根两个历史 JSON 一字不改 |

## 用法（仓库根目录；A-40：复跑换 `HARNESS_RUN_ID`）
    $env:HARNESS_RUN_ID='w1-p01-t6-regress'
    # 复用已产出的重活输出（默认）：
    python -B test-reports-2026-10/harness/w1_p01_regress.py \
        --functional-txt .tmp/.../functional_test.txt --gates-json .tmp/.../gates.json
    # 或自己把重活也跑一遍：
    python -B test-reports-2026-10/harness/w1_p01_regress.py --run-heavy
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPORTS_ROOT = os.path.dirname(HERE)
REPO_ROOT = os.path.dirname(REPORTS_ROOT)
SCRIPTS_DIR = os.path.join(REPO_ROOT, 'scripts')
sys.path.insert(0, HERE)

from _env import (  # noqa: E402
    REAL_DB, RUN_ID, assert_real_db_untouched, run_child, save_evidence, sha256_file,
)

GOLDEN_GATES = os.path.join(REPORTS_ROOT, 'evidence', 'harness', 'ci-w0-e04-t5-final',
                            'gates.json')
ROOT_JSON = ('_smoke_results.json', '_permission_matrix.json')
SHIM = os.path.join('scripts', '_sandbox_compat.py')

STATIC_GATES = (
    ('check_templates', [os.path.join('scripts', 'check_templates.py')],
     ['[templates] parsed 87 files',
      '[permissions] 44 declared / 40 used in templates / 44 used on routes',
      '[landing] 5 role landing endpoints', 'RESULT: OK']),
    ('check_migration_heads', [os.path.join('scripts', 'check_migration_heads.py')],
     ["HEADS=['p1nonctarget']", 'head_count=1', 'revisions=35']),
    ('check_properties', [os.path.join('scripts', 'check_properties.py')],
     ['已扫描 23 个文件，模型类 74 个', 'RESULT: OK']),
    ('check_model_refs', [os.path.join('scripts', 'check_model_refs.py'), '--root', 'app'],
     ['violations 0', 'RESULT: OK']),
    ('route_inventory', [SHIM, os.path.join('scripts', 'route_inventory.py')],
     ['[routes] total rules=271', 'duplicate (method,path) registrations=0']),
    ('check_db_bootstrap', [SHIM, os.path.join('scripts', 'check_db_bootstrap.py')],
     ['种子库账号数（经自举导入到空库）= 64', '直接拷贝 6712 行，跳过 0 张表']),
)


def root_json_state():
    state = {}
    for name in ROOT_JSON:
        path = os.path.join(REPO_ROOT, name)
        state[name] = {'exists': os.path.exists(path),
                       'sha256': sha256_file(path) if os.path.exists(path) else None}
    return state


def run_static_gate(name, argv, expects):
    res = run_child([os.path.join(REPO_ROOT, argv[0])] + list(argv[1:]), cwd=REPO_ROOT,
                    timeout=1200, label='regress-' + name)
    body = res['stdout'] + res['stderr']
    missing = [e for e in expects if e not in body]
    return {'gate': name, 'argv': argv, 'exit_code': res['exit_code'],
            'expects': expects, 'missing': missing,
            'ok': res['exit_code'] == 0 and not missing,
            'stdout_tail': res['stdout'][-2500:], 'stderr_tail': res['stderr'][-1200:]}


def compare_gates(new_path, golden_path):
    with open(golden_path, encoding='utf-8') as fh:
        gold = json.load(fh)
    with open(new_path, encoding='utf-8') as fh:
        new = json.load(fh)
    by_gold = {g['gate']: g for g in gold['gates']}
    facts = {}
    all_same = True
    for g in new['gates']:
        old = by_gold.get(g['gate'])
        old_checks = [(c['fact'], c['expected'], c['actual'], c['status'])
                      for c in (old or {}).get('checks', [])]
        new_checks = [(c['fact'], c['expected'], c['actual'], c['status'])
                      for c in g.get('checks', [])]
        same = old_checks == new_checks and (old or {}).get('verdict') == g.get('verdict') \
            and (old or {}).get('exit_code') == g.get('exit_code')
        all_same = all_same and same
        facts[g['gate']] = {'exit_code': g['exit_code'], 'verdict': g.get('verdict'),
                            'checks': [{'fact': c[0], 'expected': c[1], 'actual': c[2],
                                        'status': c[3]} for c in new_checks],
                            'identical_to_golden': same}
    return {
        'golden': os.path.relpath(golden_path, REPO_ROOT).replace('\\', '/'),
        'new': os.path.relpath(new_path, REPO_ROOT).replace('\\', '/'),
        'expected_lock_identical': gold['expected_lock'] == new['expected_lock'],
        'summary_identical': gold['summary'] == new['summary'],
        'exit_code_semantics_identical':
            gold.get('exit_code_semantics') == new.get('exit_code_semantics'),
        'summary': new['summary'],
        'new_exit_code': new.get('exit_code'),
        'gates': facts,
        'all_gates_identical': all_same,
        'verdict': 'pass' if (all_same and gold['expected_lock'] == new['expected_lock']
                              and gold['summary'] == new['summary']
                              and gold.get('exit_code_semantics') == new.get('exit_code_semantics'))
                   else 'fail',
    }


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError, OSError):
        pass

    ap = argparse.ArgumentParser(description='P-01 six-regression mechanical criteria')
    ap.add_argument('--functional-txt', default=None,
                    help='reuse an existing scripts/functional_test.py output file')
    ap.add_argument('--functional-exit', type=int, default=None,
                    help='exit code of that reused functional_test run')
    ap.add_argument('--gates-json', default=None,
                    help='reuse an existing run_gates.py --out JSON (default: run it now)')
    ap.add_argument('--run-heavy', action='store_true',
                    help='run scripts/functional_test.py here instead of reusing --functional-txt')
    args = ap.parse_args(argv)

    lines = []
    out = {'run_id': RUN_ID, 'repo_root': REPO_ROOT}
    real_before = sha256_file(REAL_DB)
    json_before = root_json_state()

    def log(text=''):
        print(text)
        lines.append(text)

    log('=' * 78)
    log('[w1_p01_regress] RUN_ID=%s run_heavy=%s' % (RUN_ID, args.run_heavy))
    log('[w1_p01_regress] real db sha256 before = %s' % real_before)
    log('=' * 78)

    criteria = []

    # ---- R1 functional_test
    if args.run_heavy:
        res = run_child([os.path.join(REPO_ROOT, SHIM), os.path.join(REPO_ROOT,
                        'scripts', 'functional_test.py')], cwd=REPO_ROOT, timeout=3600,
                        label='regress-functional_test')
        ft_text, ft_exit = res['stdout'] + res['stderr'], res['exit_code']
        ft_source = 'run-now'
    elif args.functional_txt:
        with open(args.functional_txt, encoding='utf-8', errors='replace') as fh:
            ft_text = fh.read()
        ft_exit = args.functional_exit if args.functional_exit is not None else 0
        ft_source = os.path.relpath(args.functional_txt, REPO_ROOT).replace('\\', '/')
    else:
        ft_text, ft_exit, ft_source = '', None, 'not provided'
    ft_ok = ft_exit == 0 and '109 通过 / 0 失败' in ft_text
    criteria.append(('R1 functional_test: exit 0 and "109 通过 / 0 失败"',
                     ft_ok, 'source=%s exit=%s tail=%s'
                     % (ft_source, ft_exit, ft_text.strip().splitlines()[-1][:90]
                        if ft_text.strip() else '')))
    out['functional_test'] = {'source': ft_source, 'exit_code': ft_exit, 'ok': ft_ok,
                              'tail': ft_text[-1500:]}

    # ---- R2..R7 static gates
    out['static_gates'] = []
    for name, gargv, expects in STATIC_GATES:
        rec = run_static_gate(name, gargv, expects)
        out['static_gates'].append(rec)
        criteria.append(('R static gate %s: exit 0 and all expected lines' % name,
                         rec['ok'], 'exit=%s missing=%s' % (rec['exit_code'], rec['missing'])))
        log('')
        log('[static:%s] exit=%s ok=%s missing=%s'
            % (name, rec['exit_code'], rec['ok'], rec['missing']))
        log(rec['stdout_tail'].rstrip())

    # ---- R8 run_gates vs golden
    gates_path = args.gates_json
    if not gates_path:
        gates_path = os.path.join(REPORTS_ROOT, '.tmp', RUN_ID, 'gates.json')
        res = run_child([os.path.join(HERE, 'run_gates.py'), '--out', gates_path],
                        cwd=REPO_ROOT, timeout=3600, label='regress-run_gates')
        out['run_gates_exit_code'] = res['exit_code']
    else:
        out['run_gates_exit_code'] = None
    cmp = compare_gates(gates_path, GOLDEN_GATES)
    out['run_gates_comparison'] = cmp
    log('')
    log('[run_gates] summary=%s' % json.dumps(cmp['summary'], ensure_ascii=True, sort_keys=True))
    for name, rec in cmp['gates'].items():
        log('  %-30s exit=%-2s verdict=%-10s checks=%d identical_to_golden=%s'
            % (name, rec['exit_code'], rec['verdict'], len(rec['checks']),
               rec['identical_to_golden']))
    criteria.append(('R8 run_gates expected_lock/summary/per-gate checks identical to golden',
                     cmp['verdict'] == 'pass',
                     'expected_lock=%s summary=%s semantics=%s per_gate=%s'
                     % (cmp['expected_lock_identical'], cmp['summary_identical'],
                        cmp['exit_code_semantics_identical'], cmp['all_gates_identical'])))

    # ---- R9 real db + root json
    real_after = assert_real_db_untouched('w1_p01_regress 收尾')
    json_after = root_json_state()
    json_same = json_before == json_after
    criteria.append(('R9 real app.db unchanged and repo-root JSONs byte-identical',
                     real_after == real_before and json_same,
                     'db %s -> %s ; root_json_same=%s'
                     % (real_before[:12], real_after[:12], json_same)))
    out['real_db_sha256_before'] = real_before
    out['real_db_sha256_after'] = real_after
    out['root_json'] = {'before': json_before, 'after': json_after, 'identical': json_same}

    log('')
    log('--- regression criteria ---')
    for c, ok, ev in criteria:
        log('  [%s] %s' % ('PASS' if ok else 'FAIL', c))
        log('         %s' % ev)
    failed = [c for c, ok, _ in criteria if not ok]
    verdict = 'PASS' if not failed else 'FAIL'
    log('')
    log('[verdict] criteria=%d failed=%d => %s' % (len(criteria), len(failed), verdict))
    for c in failed:
        log('  FAILED: %s' % c)
    out['criteria'] = [{'criterion': c, 'passed': bool(ok), 'evidence': ev}
                       for c, ok, ev in criteria]
    out['verdict'] = verdict

    transcript = '\n'.join(lines) + '\n'
    saved = [save_evidence('w1-p01-regress-criteria.json',
                           json.dumps(out, ensure_ascii=False, indent=1, default=str)),
             save_evidence('w1-p01-regress-transcript.txt', transcript),
             save_evidence('w1-p01-run-gates-comparison.json',
                           json.dumps(cmp, ensure_ascii=False, indent=1, default=str))]
    if os.path.exists(gates_path):
        with open(gates_path, encoding='utf-8', errors='replace') as fh:
            saved.append(save_evidence('w1-p01-run-gates.json', fh.read()))
    log('')
    for path in saved:
        log('[evidence] -> %s' % os.path.relpath(path, REPO_ROOT).replace('\\', '/'))
    print(transcript)
    return 0 if verdict == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
