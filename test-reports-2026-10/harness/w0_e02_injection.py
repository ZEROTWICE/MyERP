"""w0_e02_injection.py — E-02（门禁退出码可信化 / D-6）对抗注入与不变式自检。

**为什么需要本探针**：D-6 的形态是「异常状态被记进 `gates.json` 却仍 exit 0」
（`summary.probe_unexpected=1` 而 `fail=0` ⇒ 编排绿灯）。因此本探针**不读**工具自己报的
结论，而是从原始读数重算「真值」，再逐条比对退出码语义。

**不变式（全部机械可判，pre-fix 必失败 / post-fix 必通过）**

| id | 判据 |
| --- | --- |
| I1 | 出口码语义：`exit == 0` ⟺ (`fail==0` ∧ **真值** `probe_unexpected==0` ∧ **真值**敏感性通过) |
| I2 | `summary.probe_unexpected` 必须等于 `gates[].verdict=='unexpected'` 的条数（自洽） |
| I3 | `probe_unexpected` 必须出现在 **stdout** 显式一行（不能只留在 JSON 里） |
| I4 | 敏感性自检：任何「非 int 退出码」（`'EXC …'`）必须计入未通过，并在 `injections_errored`/`baselines_errored` 单列 |
| I5 | 既有 4 项真闸门的 `exit_code/verdict/parsed/checks` 与 `expected_lock` 相对 `--golden` 一字不变 |
| I6 | `sensitivity` 既有结构 `probe_exit_code` / `parsed` 不被破坏（captain 口径） |

**用法（仓库根目录；A-40：复跑必须换 `HARNESS_RUN_ID`）**

```powershell
$py = 'F:\\Miniconda\\envs\\wage\\python.exe'
$env:HARNESS_RUN_ID = 'w0-e02-t3-natural'
& $py -B test-reports-2026-10/harness/w0_e02_injection.py --scenario natural --self-test `
      --out test-reports-2026-10/evidence/harness/$env:HARNESS_RUN_ID/gates.json
```

`--scenario`：

* `natural`  —— 原样（真实锁定期望值）跑 6 项门禁；
* `matched`  —— 把取证型探针的 `expect_exit` **临时**改成它的实际退出码（内存内改，不动仓库文件）
  ⇒ 期望 `probe_unexpected=0`、整体 exit 0（证明「不是无条件失败」）；
* `mismatch` —— 把 `expect_exit` 改成 `-999`（任何子进程都不可能返回）⇒ 等价于「锁定期望值与实际观察值
  不匹配」（即 captain 的 A-42 / t3 的「原生居然成功」方向）⇒ 必须 `probe_unexpected=1` 且 exit 1；
* `exc`      —— `matched` + 往敏感性自检里注入一个「一跑就崩」的门禁 ⇒ 敏感性必须判**未通过**、
  整体 exit 1（与 D-6 的另一半同源）。

退出码：默认 `0` = 全部不变式通过、`1` = 有不变式不成立（修复前即此态，正是 D-6 的机械刻画）。
加 `--exit-code-from-gates` 时，进程退出码 = **被测 run_gates 的退出码**（便于用
`$LASTEXITCODE` 直接取证「真实退出码」；不变式判决仍打印在 stdout 与证据文件里）。

> A-14：本机控制台 `sys.stdout.encoding=gbk`（cp936），往控制台 print 非 GBK 字符会抛
> `UnicodeEncodeError` —— 那会让「判据生效的 exit 1」与「崩溃的 exit 1」混为一谈。
> 本探针与 `run_gates.py` 都在 `main()` 开头 `reconfigure(errors='replace')` 兜底。
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
sys.path.insert(0, HERE)

from _env import RUN_ID, save_evidence, sha256_file  # noqa: E402

SCENARIOS = ('natural', 'matched', 'mismatch', 'exc')

#: 注入「一跑就崩」的门禁（插在 `__SENSITIVITY__` 打印之前）
EXC_EXTRA = """
# 7) E-02 注入：一个「一跑就崩」的门禁 —— 必须计入未通过（D-6 的另一半）
def _hv_crash_gate():
    raise RuntimeError('hv_injected_crashing_gate')


rc, out = _run(_hv_crash_gate)
results['injected_crashing_gate'] = {'exit_code': rc, 'expected_nonzero': True,
                                     'note': 'E-02 注入：门禁自身抛异常',
                                     'stdout_tail': out[-200:]}
"""


def load_module(path):
    """按路径加载被测 run_gates 模块（便于对「修复前副本」做同一套判决）。"""
    spec = importlib.util.spec_from_file_location('run_gates_under_e02_test', path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules['run_gates_under_e02_test'] = mod
    spec.loader.exec_module(mod)
    return mod


def split_sensitivity(parsed):
    """把敏感性自检原始读数分成 注入组 / 基线组，并给出『真值』。"""
    if not parsed:
        return {'injections': {}, 'baselines': {}, 'ok': None,
                'errored': [], 'wrong_direction': []}
    inj = {k: v for k, v in parsed.items() if v.get('expected_nonzero')}
    base = {k: v for k, v in parsed.items() if not v.get('expected_nonzero')}
    errored = [k for k, v in list(inj.items()) + list(base.items())
               if not isinstance(v.get('exit_code'), int)]
    wrong = [k for k, v in inj.items()
             if isinstance(v.get('exit_code'), int) and int(v['exit_code']) == 0]
    wrong += [k for k, v in base.items()
              if isinstance(v.get('exit_code'), int) and int(v['exit_code']) != 0]
    return {'injections': inj, 'baselines': base,
            'ok': not (errored or wrong), 'errored': errored,
            'wrong_direction': wrong}


def check_invariants(out, stdout, golden):
    """从 gates.json + stdout 重算真值并逐条判不变式。"""
    inv = []
    summary = out['summary']
    gates = out['gates']

    # ---- 真值：probe_unexpected ----
    probe_unexp_truth = sum(1 for g in gates if g['verdict'] == 'unexpected')
    unexpected_gates = [g['gate'] for g in gates if g['verdict'] == 'unexpected']
    bad_probe_direction = [g['gate'] for g in gates
                           if g['verdict'] == 'unexpected'
                           and g['exit_code'] == g['expected_exit_code']]

    # ---- 真值：敏感性 ----
    sens = out.get('sensitivity')
    sens_truth = split_sensitivity(sens.get('parsed') if sens else None)
    sens_truth_ok = None if sens is None else sens_truth['ok']

    # I1 出口码语义
    expected_exit = 0 if (summary['fail'] == 0 and probe_unexp_truth == 0
                          and (sens_truth_ok in (None, True))) else 1
    inv.append({
        'id': 'I1', 'desc': 'exit==0 iff fail==0 and probe_unexpected==0 and 敏感性真值通过',
        'status': 'passed' if out.get('_exit_code') == expected_exit else 'failed',
        'detail': f"expected_exit={expected_exit} actual_exit={out.get('_exit_code')} "
                  f"fail={summary['fail']} probe_unexpected(真值)={probe_unexp_truth} "
                  f"sensitivity_truth_ok={sens_truth_ok}"})

    # I2 自洽
    inv.append({
        'id': 'I2', 'desc': 'summary.probe_unexpected == verdict=="unexpected" 条数',
        'status': 'passed' if summary['probe_unexpected'] == probe_unexp_truth
                  and not bad_probe_direction else 'failed',
        'detail': f"summary={summary['probe_unexpected']} 真值={probe_unexp_truth} "
                  f"unexpected_gates={unexpected_gates} 方向异常={bad_probe_direction}"})

    # I3 stdout 显式
    m = re.search(r'probe_unexpected\s*=\s*(\d+)', stdout)
    inv.append({
        'id': 'I3', 'desc': 'probe_unexpected 在 stdout 显式一行且与 JSON 相等',
        'status': 'passed' if m and int(m.group(1)) == summary['probe_unexpected']
                  else 'failed',
        'detail': f"stdout_match={m.group(0) if m else None} "
                  f"json={summary['probe_unexpected']}"})

    # I4 敏感性 EXC 计入未通过 + 单列
    detail = 'sensitivity 块缺失（未跑 --self-test）'
    status = 'skipped'
    if sens is not None:
        inj_err = [k for k, v in sens_truth['injections'].items()
                   if not isinstance(v.get('exit_code'), int)]
        base_err = [k for k, v in sens_truth['baselines'].items()
                    if not isinstance(v.get('exit_code'), int)]
        rep_inj_ok = sens.get('injections_all_nonzero')
        rep_base_ok = sens.get('baselines_all_zero')
        truth_inj_ok = not inj_err and not any(
            isinstance(v.get('exit_code'), int) and int(v['exit_code']) == 0
            for v in sens_truth['injections'].values())
        truth_base_ok = not base_err and not any(
            isinstance(v.get('exit_code'), int) and int(v['exit_code']) != 0
            for v in sens_truth['baselines'].values())
        listed_inj = set(sens.get('injections_errored') or [])
        listed_base = set(sens.get('baselines_errored') or [])
        problems = []
        if rep_inj_ok != truth_inj_ok:
            problems.append(f'injections_all_nonzero 报 {rep_inj_ok} 真值 {truth_inj_ok}')
        if rep_base_ok != truth_base_ok:
            problems.append(f'baselines_all_zero 报 {rep_base_ok} 真值 {truth_base_ok}')
        if inj_err and not set(inj_err) <= listed_inj:
            problems.append(f'injections_errored 未单列 {inj_err}')
        if base_err and not set(base_err) <= listed_base:
            problems.append(f'baselines_errored 未单列 {base_err}')
        if 'injections_errored' not in sens:
            problems.append('缺少 injections_errored 键')
        if 'baselines_errored' not in sens:
            problems.append('缺少 baselines_errored 键')
        status = 'passed' if not problems else 'failed'
        detail = ('非 int 退出码=' + str(sorted(inj_err + base_err))
                  + f' injections_all_nonzero={rep_inj_ok}/{truth_inj_ok}'
                  + f' baselines_all_zero={rep_base_ok}/{truth_base_ok}'
                  + (' 问题=' + '; '.join(problems) if problems else ' 无问题'))
    inv.append({'id': 'I4', 'desc': '非 int 退出码（EXC）计入未通过并单列', 'status': status,
                'detail': detail})

    # I5 既有真闸门一字不变（相对 golden）
    if golden is None:
        inv.append({'id': 'I5', 'desc': '4 项真闸门与 expected_lock 相对 golden 不变',
                    'status': 'skipped', 'detail': '未提供 --golden'})
    else:
        diffs = []
        if out['expected_lock'] != golden['expected_lock']:
            diffs.append('expected_lock 变化')
        gmap = {g['gate']: g for g in golden['gates']}
        for g in gates:
            ref = gmap.get(g['gate'])
            if ref is None:
                continue
            if not ref['exit_code_informative']:
                continue
            for key in ('exit_code', 'verdict', 'parsed', 'checks'):
                if g.get(key) != ref.get(key):
                    diffs.append(f"{g['gate']}.{key}")
        inv.append({'id': 'I5', 'desc': '4 项真闸门与 expected_lock 相对 golden 不变',
                    'status': 'passed' if not diffs else 'failed',
                    'detail': ('一致' if not diffs else '差异=' + ', '.join(diffs))})

    # I6 sensitivity 既有结构保持
    if sens is None:
        inv.append({'id': 'I6', 'desc': 'sensitivity 结构 probe_exit_code/parsed 保持',
                    'status': 'skipped', 'detail': '未跑 --self-test'})
    else:
        missing = [k for k in ('probe_exit_code', 'parsed', 'injections_all_nonzero',
                               'baselines_all_zero', 'evidence_level', 'stdout_tail')
                   if k not in sens]
        inv.append({'id': 'I6', 'desc': 'sensitivity 结构 probe_exit_code/parsed 保持',
                    'status': 'passed' if not missing else 'failed',
                    'detail': '键齐全' if not missing else '缺键=' + ','.join(missing)})
    return inv


def main():
    # A-14：本机控制台默认 GBK；往控制台 print 非 GBK 字符会抛 UnicodeEncodeError，
    # 那会让「判决」与「崩溃」的退出码混为一谈。只放宽 errors，不改 encoding：
    # 落盘走 `_env.save_evidence`（UTF-8），证据原文不受影响。
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(errors='replace')
        except Exception:
            pass

    ap = argparse.ArgumentParser()
    ap.add_argument('--module', default=os.path.join(HERE, 'run_gates.py'),
                    help='被测 run_gates.py（默认本目录；可指向修复前副本做 A/B）')
    ap.add_argument('--scenario', default='natural', choices=SCENARIOS)
    ap.add_argument('--self-test', action='store_true')
    ap.add_argument('--out', required=True)
    ap.add_argument('--golden', default=None, help='对照基线 gates.json（判 I5）')
    ap.add_argument('--exit-code-from-gates', action='store_true',
                    help='进程退出码用被测 run_gates 的退出码（便于 $LASTEXITCODE 取证）')
    args = ap.parse_args()

    rg = load_module(os.path.abspath(args.module))
    probe = [s for s in rg.GATES if s.get('probe_only')][0]
    patch_note = '未注入（原样）'
    if args.scenario in ('matched', 'exc'):
        actual = rg.run_gate(probe, RUN_ID)['exit_code']
        probe['expect_exit'] = actual
        patch_note = (f'内存内把 {probe["name"]} 的 expect_exit 改为实际退出码 {actual}'
                      f'（不动仓库文件）')
    elif args.scenario == 'mismatch':
        probe['expect_exit'] = -999
        patch_note = (f'内存内把 {probe["name"]} 的 expect_exit 改为 -999（子进程不可能返回该值'
                      f' => 等价于「锁定期望值与实际观察值不匹配」）')
    if args.scenario == 'exc':
        patched = rg.SENSITIVITY.replace("print('__SENSITIVITY__'",
                                         EXC_EXTRA + "print('__SENSITIVITY__'", 1)
        if patched == rg.SENSITIVITY:
            raise SystemExit('注入点未命中：SENSITIVITY 打印行未找到')
        rg.SENSITIVITY = patched
        patch_note += ' + 敏感性自检追加「一跑就崩」门禁注入'

    argv = [os.path.abspath(args.module), '--out', os.path.abspath(args.out)]
    if args.self_test:
        argv.append('--self-test')
    rg_argv_backup = list(sys.argv)
    sys.argv = argv
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            rc = rg.main()
    finally:
        sys.argv = rg_argv_backup
    stdout = buf.getvalue()

    with open(args.out, encoding='utf-8') as fh:
        out = json.load(fh)
    out['_exit_code'] = rc
    golden = None
    if args.golden:
        with open(args.golden, encoding='utf-8') as fh:
            golden = json.load(fh)

    inv = check_invariants(out, stdout, golden)
    verdict = 'PASS' if all(i['status'] in ('passed', 'skipped') for i in inv) else 'FAIL'

    lines = [
        '=' * 78,
        f'[e02] scenario={args.scenario}  run_id={RUN_ID}',
        f'[e02] module={os.path.abspath(args.module)}',
        f'[e02] module_sha256={sha256_file(os.path.abspath(args.module))}',
        f'[e02] 注入：{patch_note}',
        f'[e02] gates.json -> {os.path.abspath(args.out)}',
        '-' * 78,
        stdout.rstrip(),
        '-' * 78,
        f'[e02] run_gates 退出码 = {rc}',
        f"[e02] summary = {json.dumps(out['summary'], ensure_ascii=False)}",
    ]
    if out.get('sensitivity') is not None:
        s = out['sensitivity']
        lines.append('[e02] sensitivity = ' + json.dumps(
            {k: v for k, v in s.items() if k not in ('parsed', 'stdout_tail')},
            ensure_ascii=False))
        lines.append('[e02] sensitivity.parsed = ' + json.dumps(s.get('parsed'),
                                                                ensure_ascii=False))
    for i in inv:
        lines.append(f"  [{i['status'].upper()}] {i['id']} {i['desc']}")
        lines.append(f"        {i['detail']}")
    lines.append(f'[e02] 不变式判决 = {verdict}'
                 f'（{sum(1 for i in inv if i["status"] == "passed")} passed / '
                 f'{sum(1 for i in inv if i["status"] == "failed")} failed / '
                 f'{sum(1 for i in inv if i["status"] == "skipped")} skipped）')
    text = '\n'.join(lines) + '\n'
    path = save_evidence(f'e02_{args.scenario}.console.txt', text)
    print(text, end='')
    print(f'[e02] 原始输出已落盘（写入守卫 + 台账）-> {path}')
    if args.exit_code_from_gates:
        return rc                     # 真实进程退出码 = 被测 run_gates 的退出码
    return 0 if verdict == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
