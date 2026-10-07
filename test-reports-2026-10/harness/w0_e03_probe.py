"""w0_e03_probe.py — E-03（三类退出码分流）的对抗注入与不变式自检。

**为什么需要本探针**：E-03 的三类处置各有判据，且**必须互相区分**（A-9/A-30）：
伪门禁型要「有失败出口」，写盘污染型要「退出码与写盘解耦」，报告型要「退出码仍 0 但判据在解析器」。

**不变式（机械可判；修复前必失败 / 修复后必通过）**

| id | 判据 |
| --- | --- |
| I1 | 伪门禁型：注入「匿名可访问」视图后 `permission_matrix` 必须 **exit 1** 且 stdout 含 `[FAIL]`＋数量 |
| I2 | 写盘污染型：落盘失败（目标不可写）时 `permission_matrix` / `smoke_test` 仍 **exit 0**（绿断言）并打印 `[WARN]` |
| I3 | 既有断言语义未被改动：`smoke_test` 注入一次请求异常 ⇒ **exit 1**（断言驱动） |
| I4 | 结论段逐项一致：修复前/后 stdout 的**结论段完全相等**（只动退出码与落盘，不动判据） |
| I5 | 报告型：`route_inventory` / `measure_coverage` 退出码仍 0，但其产物被 `coverage_drift.py` 消费出判据（漂移注入 ⇒ exit 1） |
| I6 | 落盘位置：默认落 `test-reports-2026-10/.tmp/<RUN_ID>/`，**仓库根两个历史 JSON 一字不改** |
| I7 | `--no-dump` 不产生任何落盘文件，退出码不变 |

用法（仓库根目录；A-40：复跑必须换 `HARNESS_RUN_ID`）：

    $env:HARNESS_RUN_ID='w0-e03-t4-<场景>'
    python -B test-reports-2026-10/harness/w0_e03_probe.py --scenario permx_anon_inject --exit-code-from-target
"""
import argparse
import contextlib
import importlib.util
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPORTS_ROOT = os.path.dirname(HERE)
REPO_ROOT = os.path.dirname(REPORTS_ROOT)
SCRIPTS_DIR = os.path.join(REPO_ROOT, 'scripts')
sys.path.insert(0, HERE)

from _env import RUN_ID, run_child, save_evidence, sha256_file  # noqa: E402

FROZEN_ROOT_JSON = {
    '_smoke_results.json': 'D301835F077D2EDFFCB5DA4469C87A23C594D1E9EC75010594C3A812466A9762',
    '_permission_matrix.json': '999A01209A8A56BBE7CF1FB5842FE4991762A91683DF97621650B11068B67C19',
}
SCENARIOS = ('permx_normal', 'permx_anon_inject', 'permx_write_denied', 'permx_dump_default',
             'smoke_normal', 'smoke_write_denied', 'smoke_error_inject', 'smoke_dump_default',
             'route_inventory_capture', 'drift_baseline', 'drift_selftest', 'drift_inject',
             'conclusion_ab')


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def root_json_state():
    out = {}
    for name in FROZEN_ROOT_JSON:
        p = os.path.join(REPO_ROOT, name)
        out[name] = {'exists': os.path.exists(p),
                     'sha256': sha256_file(p) if os.path.exists(p) else None}
    return out


def run_real(script, args=(), label=''):
    env = {'PYTHONPATH': os.pathsep.join([SCRIPTS_DIR, REPO_ROOT, HERE])}
    res = run_child([os.path.join(SCRIPTS_DIR, script)] + list(args), cwd=REPO_ROOT,
                    timeout=3600, extra_env=env, label=label)
    return res['exit_code'], res['stdout'] + res['stderr']


class _FlakyClient:
    """把 test_client 包一层：第 3 次 GET 抛异常（模拟请求级故障，证明失败出口还活着）。"""

    def __init__(self, client):
        self._client = client
        self._n = 0

    def get(self, *a, **kw):
        self._n += 1
        if self._n == 3:
            raise RuntimeError('E03 注入：请求级故障')
        return self._client.get(*a, **kw)

    def __getattr__(self, name):
        return getattr(self._client, name)


def make_anon_injected_app(mod):
    real_make_app = mod.make_app

    def wrapped():
        app, db_path = real_make_app()

        @app.route('/__e03_anon_probe__')
        def _e03_anon_probe():
            return 'E03-ANON-OK'
        return app, db_path
    return wrapped


def make_flaky_app(mod):
    real_make_app = mod.make_app

    def wrapped():
        app, db_path = real_make_app()
        real_client = app.test_client

        def flaky_client(*a, **kw):
            return _FlakyClient(real_client(*a, **kw))
        app.test_client = flaky_client
        return app, db_path
    return wrapped


def run_inproc(mod_name, patch, call):
    """进程内调用目标 run()，返回 (code, stdout)。"""
    os.chdir(REPO_ROOT)
    mod = load_module(os.path.join(SCRIPTS_DIR, mod_name + '.py'), mod_name)
    if patch:
        mod.make_app = patch(mod)
    buf = io.StringIO()
    code = None
    with contextlib.redirect_stdout(buf):
        try:
            code = call(mod)
        except SystemExit as e:
            code = e.code
        except Exception as e:                       # 崩溃也要如实记录（≠ 判据失败）
            code = f'EXC {e.__class__.__name__}: {e}'
    return code, buf.getvalue()


def body_of(text):
    """取「结论段」= 去掉尾部落盘/退出语义行之前的全部 stdout（用于 A/B 逐项比对）。"""
    stop = ('明细已写入', '完整矩阵已写入', '[WARN] 落盘失败', '[--no-dump]',
            '[e03]', '[OK] 匿名可访问', '[FAIL] 匿名可访问')
    keep = []
    for line in text.splitlines():
        if any(line.startswith(s) for s in stop):
            break
        keep.append(line)
    return '\n'.join(keep).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--scenario', required=True, choices=SCENARIOS)
    ap.add_argument('--prefix-dir', default=os.path.join(REPORTS_ROOT, '.tmp', 'w0-e03-t4',
                                                        'prefix-ab'),
                    help='修复前 A/B 产物目录（含 prefix_*.out.txt）')
    ap.add_argument('--coverage', default=os.path.join(REPORTS_ROOT, 'evidence', 'harness',
                                                       'coverage.json'))
    ap.add_argument('--shared-dir', default=os.path.join(REPORTS_ROOT, '.tmp',
                                                         'w0-e03-t4-shared'),
                    help='跨场景共享产物目录（route_inventory stdout、注入用 coverage.json）')
    ap.add_argument('--exit-code-from-target', action='store_true',
                    help='进程退出码 = 目标脚本的退出码（便于 $LASTEXITCODE 直接取证）')
    args = ap.parse_args()

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors='replace')
        except Exception:
            pass

    before_root = root_json_state()
    tmp_run = os.path.join(REPORTS_ROOT, '.tmp', RUN_ID)
    os.makedirs(tmp_run, exist_ok=True)
    shared = args.shared_dir
    os.makedirs(shared, exist_ok=True)
    blocked_dir = os.path.join(tmp_run, '_e03_blocked_target')      # 目标是「目录」⇒ 写盘必失败
    os.makedirs(blocked_dir, exist_ok=True)

    target_code = None
    target_out = ''
    extra = {}

    if args.scenario in ('permx_normal', 'permx_dump_default'):
        argv = [] if args.scenario.endswith('dump_default') else ['--no-dump']
        target_code, target_out = run_real('permission_matrix.py', argv, label=args.scenario)
    elif args.scenario == 'permx_anon_inject':
        target_code, target_out = run_inproc(
            'permission_matrix', make_anon_injected_app,
            lambda mod: mod.run(dump=False))
    elif args.scenario == 'permx_write_denied':
        target_code, target_out = run_real('permission_matrix.py',
                                           ['--out', blocked_dir], label=args.scenario)
    elif args.scenario in ('smoke_normal', 'smoke_dump_default'):
        argv = [] if args.scenario.endswith('dump_default') else ['--no-dump']
        target_code, target_out = run_real('smoke_test.py', argv, label=args.scenario)
    elif args.scenario == 'smoke_write_denied':
        target_code, target_out = run_real('smoke_test.py', ['--out', blocked_dir],
                                           label=args.scenario)
    elif args.scenario == 'smoke_error_inject':
        target_code, target_out = run_inproc('smoke_test', make_flaky_app,
                                             lambda mod: mod.run(dump=False))
    elif args.scenario == 'route_inventory_capture':
        target_code, target_out = run_real('route_inventory.py', [], label=args.scenario)
        extra['routes_file'] = os.path.join(shared, 'route_inventory.stdout.txt')
        with open(extra['routes_file'], 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(target_out)
    elif args.scenario in ('drift_baseline', 'drift_selftest', 'drift_inject'):
        cov = args.coverage
        if args.scenario == 'drift_selftest':
            argv = ['--selftest']
        else:
            if args.scenario == 'drift_inject':
                with open(args.coverage, encoding='utf-8') as fh:
                    doc = json.load(fh)
                doc['summary']['writable_literal_covered_by_all'] = 5      # 注入漂移 6 -> 5
                cov = os.path.join(shared, 'coverage.drifted.json')
                with open(cov, 'w', encoding='utf-8', newline='\n') as fh:
                    json.dump(doc, fh, ensure_ascii=False)
            routes = os.path.join(shared, 'route_inventory.stdout.txt')
            argv = ['--coverage', cov]
            if os.path.isfile(routes):
                argv += ['--routes-stdout', routes]
        res = run_child([os.path.join(HERE, 'coverage_drift.py')] + argv, cwd=REPO_ROOT,
                        timeout=1800, label=args.scenario)
        target_code, target_out = res['exit_code'], res['stdout'] + res['stderr']
    elif args.scenario == 'conclusion_ab':
        pairs = (('permx', 'permission_matrix.py', ['--no-dump']),
                 ('smoke', 'smoke_test.py', ['--no-dump']))
        inv = []
        for tag, script, argv in pairs:
            pre_path = os.path.join(args.prefix_dir, f'prefix_{tag}_baseline.out.txt')
            pre_text = open(pre_path, encoding='utf-8').read()
            pre_body = body_of(pre_text.split('--- stdout ---\n', 1)[1].split('\n--- stderr ---')[0])
            code, post_text = run_real(script, argv, label=f'ab_{tag}')
            post_body = body_of(post_text)
            same = pre_body == post_body
            extra.setdefault('ab', []).append({'tag': tag, 'pre_exit': 0,
                                               'post_exit': code, 'identical': same,
                                               'pre_lines': len(pre_body.splitlines()),
                                               'post_lines': len(post_body.splitlines())})
            if not same:
                import difflib
                diff = list(difflib.unified_diff(pre_body.splitlines(),
                                                 post_body.splitlines(), lineterm=''))[:40]
                extra.setdefault('ab_diff', []).extend(diff)
            inv.append(same)
        target_code = 0 if all(inv) else 1
        target_out = json.dumps(extra.get('ab'), ensure_ascii=False)

    after_root = root_json_state()

    # ------------------------------------------------ 不变式
    inv = []

    def check(cid, desc, ok, detail):
        inv.append({'id': cid, 'desc': desc,
                    'status': 'passed' if ok else 'failed', 'detail': detail})

    root_ok = all(before_root[n]['sha256'] == FROZEN_ROOT_JSON[n]
                  and after_root[n]['sha256'] == before_root[n]['sha256']
                  for n in FROZEN_ROOT_JSON)
    check('I6', '仓库根两个历史 JSON 一字不改（且等于冻结值）', root_ok,
          f"before={ {k: (v['sha256'] or '-')[:16] for k, v in before_root.items()} } "
          f"after={ {k: (v['sha256'] or '-')[:16] for k, v in after_root.items()} }")

    if args.scenario in ('permx_normal', 'smoke_normal'):
        check('I4/I5', '正常数据 ⇒ 目标 exit 0', target_code == 0, f'actual={target_code}')
        check('I6', '--no-dump 不落盘（.tmp 下无本次产物）',
              not any(f.startswith('_smoke_results') or f.startswith('_permission_matrix')
                      for f in os.listdir(tmp_run)),
              f'files={sorted(os.listdir(tmp_run))}')
    elif args.scenario in ('permx_write_denied', 'smoke_write_denied'):
        check('I2', '落盘失败 ⇒ 仍 exit 0 且打印 [WARN]',
              target_code == 0 and '[WARN] 落盘失败' in target_out,
              f'exit={target_code} warn={"[WARN] 落盘失败" in target_out}')
    elif args.scenario == 'permx_anon_inject':
        has_fail = '[FAIL] 匿名可访问视图 1 个' in target_out
        check('I1', '注入匿名可访问 ⇒ exit 1 且 [FAIL] 带数量',
              target_code == 1 and has_fail, f'exit={target_code} has_fail_line={has_fail}')
    elif args.scenario == 'smoke_error_inject':
        m = re.search(r'问题数 = (\d+) => exit (\d)', target_out)
        n = int(m.group(1)) if m else 0
        check('I3', '请求级异常注入 ⇒ exit 1 且由「问题数」驱动（非写盘）',
              target_code == 1 and n >= 1 and (m.group(2) == '1' if m else False),
              f'exit={target_code} 问题数={n}')
    elif args.scenario.endswith('dump_default'):
        name = ('_smoke_results.json' if args.scenario.startswith('smoke')
                else '_permission_matrix.json')
        landed = os.path.isfile(os.path.join(tmp_run, name))
        check('I6', f'默认落盘位置 = .tmp/{RUN_ID}/{name}',
              target_code == 0 and landed, f'exit={target_code} landed={landed}')
    elif args.scenario == 'route_inventory_capture':
        check('I5', '报告型 route_inventory 仍 exit 0 且自述不进链',
              target_code == 0 and '"in_gate_chain": false' in target_out,
              f'exit={target_code} 自述={"in_gate_chain" in target_out}')
    elif args.scenario == 'drift_baseline':
        check('I5', '解析器消费报告型产物 ⇒ 判据 exit 0',
              target_code == 0 and '判据' in target_out, f'exit={target_code}')
    elif args.scenario == 'drift_selftest':
        check('I5', '解析器敏感性自检 9/9 通过',
              target_code == 0 and '9/9 通过' in target_out, f'exit={target_code}')
    elif args.scenario == 'drift_inject':
        check('I5', '产物漂移（literal 6→5）⇒ 解析器 exit 1',
              target_code == 1 and 'D-4' in target_out, f'exit={target_code} D-4命中={"D-4" in target_out}')
    elif args.scenario == 'conclusion_ab':
        for row in extra.get('ab', []):
            check('I4', f"{row['tag']}: 结论段与修复前逐项一致", row['identical'],
                  f"lines {row['pre_lines']} vs {row['post_lines']} identical={row['identical']}")

    verdict = 'PASS' if all(i['status'] == 'passed' for i in inv) else 'FAIL'
    targets = {
        'probe_sha256': sha256_file(os.path.abspath(__file__)),
        'permission_matrix.py': sha256_file(os.path.join(SCRIPTS_DIR, 'permission_matrix.py')),
        'smoke_test.py': sha256_file(os.path.join(SCRIPTS_DIR, 'smoke_test.py')),
        'route_inventory.py': sha256_file(os.path.join(SCRIPTS_DIR, 'route_inventory.py')),
        'coverage_drift.py': sha256_file(os.path.join(HERE, 'coverage_drift.py')),
    }
    lines = [
        '=' * 82,
        f'[e03] scenario={args.scenario}  run_id={RUN_ID}',
        f'[e03] 目标退出码（真实进程 / 进程内 return）= {target_code}',
        '[e03] 指纹（探针 + 被测脚本，供复算）:',
    ]
    for k, v in targets.items():
        lines.append(f'[e03]   {k} = {v}')
    lines += [
        '-' * 82,
        target_out.rstrip()[-4000:],
        '-' * 82,
        f'[e03] 目标退出码 = {target_code}',
    ]
    for i in inv:
        lines.append(f"  [{i['status'].upper()}] {i['id']} {i['desc']}")
        lines.append(f"        {i['detail']}")
    if extra.get('ab_diff'):
        lines.append('[e03] A/B diff（前 40 行）:')
        lines.extend('   ' + d for d in extra['ab_diff'])
    lines.append(f'[e03] 不变式判决 = {verdict}'
                 f"（{sum(1 for i in inv if i['status'] == 'passed')} passed / "
                 f"{sum(1 for i in inv if i['status'] == 'failed')} failed）")
    text = '\n'.join(lines) + '\n'
    path = save_evidence(f'e03_{args.scenario}.console.txt', text)
    print(text, end='')
    print(f'[e03] 原始输出已落盘（写入守卫 + 台账）-> {path}')
    if args.exit_code_from_target and isinstance(target_code, int):
        return target_code
    return 0 if verdict == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
