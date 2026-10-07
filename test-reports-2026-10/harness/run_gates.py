"""5 项静态门禁的沙箱安全编排（机读 JSON + 人读摘要）。

**为什么需要本编排**（`08` §5.1 / §5.2 三类伪门禁）：

* `route_inventory.py:38` 与 `permission_matrix.py:132` **无条件 `return 0`** ⇒ 退出码零信息量；
* `smoke_test.py:186` / `permission_matrix.py:129` 写仓库根 JSON ⇒ 沙箱下**断言全绿也 exit 1**（「狼来了」）；
* 凡走 `_test_bootstrap.make_app()` 的脚本**原生必失败**（0o700 `mkdtemp` 不可写，A-8/E-7）。

⇒ 本编排**不把退出码当唯一判据**：对每项门禁同时记录
①**退出码**、②从 stdout **解析出的实际计数**、③与「锁死期望值」的**逐项比对**、④**退出码可信度**标签。
被标为 `exit_code_informative=False` 的项（route_inventory）只作清单，**不进闸门链**。

**退出码语义（E-02 修复 D-6 / T-02 / T-03）**：`exit 0` ⟺
① `summary['fail'] == 0` ∧ ② `summary['probe_unexpected'] == 0`（取证型探针与**锁定期望值**
不一致 ⇒ A-1「原生形态必被沙箱拒绝」这一环境事实被破坏）∧ ③（未跑 `--self-test` 或
`summary['sensitivity_ok'] is True`）。三者任一不成立即 `exit 1`；
`probe_unexpected` 与敏感性判决都在 stdout **显式一行**（旧实现只留在 JSON 里 ⇒ 静默绿灯）。
敏感性自检里 `'EXC …'` 这类**非 int 退出码必须计入未通过**（旧实现用
`isinstance(exit_code, int)` 静默过滤 ⇒ 一个「一跑就崩」的门禁会被判为敏感性通过）。

用法（仓库根目录）：

    F:\\Miniconda\\envs\\wage\\python.exe -B test-reports-2026-10/harness/run_gates.py
    F:\\Miniconda\\envs\\wage\\python.exe -B test-reports-2026-10/harness/run_gates.py --self-test
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _env import (EVIDENCE_DIR, HARNESS_DIR, REPO_ROOT, SCRIPTS_DIR, ensure_dir,
                  guard_write, line_count, real_db_status, run_child,
                  save_evidence, tmp_dir)

# 期望值单一存放点（GAP-29/30 的口径）：任何一项对不上即 fail。
EXPECTED = {
    'templates_files': 87,
    'capabilities_declared': 44,
    'capabilities_used_templates': 40,
    'capabilities_used_routes': 44,
    'landing_endpoints': 5,
    'migration_heads': ['p1nonctarget'],
    'migration_head_count': 1,
    'migration_revisions': 35,
    'properties_files': 23,
    'model_classes': 74,
    'routes_total_rules': 271,
    'routes_get_no_arg': 104,
    'routes_get_with_arg': 56,
    'routes_non_get': 110,
    'routes_static': 1,
    'routes_dup_method_path': 0,
    'bootstrap_accounts': 64,
    'bootstrap_copied_rows': 6712,
    'bootstrap_skipped_tables': 0,
    'functional_passed': 109,
    'functional_failed': 0,
}

# 每项门禁：脚本 / 是否必须 shim / 退出码可信度 / stdout 解析器
GATES = [
    {
        'name': 'check_templates',
        'script': 'check_templates.py',
        'shim': False,
        'exit_code_informative': True,
        'gate_semantics': '真闸门（模板语法 + 能力登记一致性 + 落地端点存在性）',
        'patterns': {
            'templates_files': r'\[templates\]\s+parsed\s+(\d+)\s+files',
            'capabilities_declared': r'\[permissions\]\s+(\d+)\s+declared',
            'capabilities_used_templates': r'declared\s*/\s*(\d+)\s+used in templates',
            'capabilities_used_routes': r'(\d+)\s+used on routes',
            'landing_endpoints': r'\[landing\]\s+(\d+)\s+role landing endpoints',
        },
        'expect_exit': 0,
    },
    {
        'name': 'check_migration_heads',
        'script': 'check_migration_heads.py',
        'shim': False,
        'exit_code_informative': True,
        'gate_semantics': '真闸门（单 head + 修订数）',
        'patterns': {
            'migration_heads': r"HEADS=\(?\[?['\"]?([A-Za-z0-9_]+)['\"]?\]?\)?",
            'migration_head_count': r'head_count=(\d+)',
            'migration_revisions': r'revisions=(\d+)',
        },
        'expect_exit': 0,
    },
    {
        'name': 'check_properties',
        'script': 'check_properties.py',
        'shim': False,
        'exit_code_informative': True,
        'gate_semantics': '真闸门（@property / 不存在列当列用；有语义盲区）',
        'patterns': {
            'properties_files': r'已扫描\s*(\d+)\s*个文件',
            'model_classes': r'模型类\s*(\d+)\s*个',
        },
        'expect_exit': 0,
    },
    {
        'name': 'route_inventory',
        'script': 'route_inventory.py',
        'shim': True,
        'exit_code_informative': False,   # 只返回 0（route_inventory.py:38）
        'gate_semantics': '报告型伪门禁（无条件 return 0）⇒ 只作清单，不进闸门链',
        'patterns': {
            'routes_total_rules': r'total rules=(\d+)',
            'routes_dup_method_path': r'duplicate \(method,path\) registrations=(\d+)',
            'routes_get_no_arg': r'GET no-arg=(\d+)',
            'routes_get_with_arg': r'GET with-arg=(\d+)',
            'routes_non_get': r'non-GET=(\d+)',
        },
        'expect_exit': 0,
    },
    {
        # 原生形态：**只用于取证**（A-1/E-7 说它必失败），不参与判定。
        'name': 'route_inventory_native_probe',
        'script': 'route_inventory.py',
        'shim': False,
        'probe_only': True,
        'exit_code_informative': False,
        'gate_semantics': '原生形态取证：mkdtemp(0o700) 不可写 ⇒ PermissionError（A-1/E-7）'
                          '；若实际退出码 ≠ 锁定期望值 ⇒ 记 probe_unexpected 并计入退出码（E-02）',
        'patterns': {},
        'expect_exit': 1,
    },
    {
        'name': 'check_db_bootstrap',
        'script': 'check_db_bootstrap.py',
        'shim': True,
        'exit_code_informative': True,
        'gate_semantics': '真闸门（空库自举 / 幂等 / 整表无遗漏）',
        'patterns': {
            'bootstrap_accounts': r'种子库账号数[^=]*=\s*(\d+)',
            'bootstrap_copied_rows': r'直接拷贝\s*(\d+)\s*行',
            'bootstrap_skipped_tables': r'跳过\s*(\d+)\s*张表',
        },
        'expect_exit': 0,
    },
]


def _parse(text, patterns):
    found = {}
    for key, rx in patterns.items():
        m = re.search(rx, text)
        found[key] = m.group(1) if m else None
    return found


def _compare(name, found):
    """把解析值转成与 EXPECTED 同型的比较；返回逐项比对结果。"""
    checks = []
    for key, value in found.items():
        if value is None:
            checks.append({'fact': key, 'expected': EXPECTED.get(key), 'actual': None,
                           'status': 'failed', 'note': 'stdout 未解析到该计数'})
            continue
        if key not in EXPECTED:
            checks.append({'fact': key, 'expected': None, 'actual': value,
                           'status': 'passed', 'note': '无锁死期望值（仅记录）'})
            continue
        exp = EXPECTED[key]
        if key == 'migration_heads':
            actual = [h.strip().strip("'\"") for h in value.split(',') if h.strip()]
        else:
            actual = int(value)
        checks.append({'fact': key, 'expected': exp, 'actual': actual,
                       'status': 'passed' if actual == exp else 'failed'})
    return checks


def run_gate(spec, run_id):
    if spec['shim']:
        args = ['_sandbox_compat.py', spec['script']]
        cwd = SCRIPTS_DIR
    else:
        args = [os.path.join('scripts', spec['script'])]
        cwd = REPO_ROOT
    label = f'gate_{spec["name"]}_{"shim" if spec["shim"] else "native"}'
    res = run_child(args, cwd=cwd, timeout=1800, label=label)
    found = _parse(res['stdout'] + res['stderr'], spec['patterns'])
    checks = _compare(spec['name'], found)
    hard_failed = [c for c in checks if c['status'] == 'failed'
                   and c['fact'] in EXPECTED]
    verdict = 'pass'
    if spec.get('probe_only'):
        # 取证型：只记录退出码与原文，不参与判定（A-1 的失败是**预期事实**，不是闸门失败）
        verdict = 'probe'
        return {
            'gate': spec['name'], 'script': f'scripts/{spec["script"]}', 'mode': 'native',
            'command': res['argv_display'], 'cwd': res['cwd'], 'exit_code': res['exit_code'],
            'expected_exit_code': spec['expect_exit'], 'exit_code_informative': False,
            'probe_only': True, 'gate_semantics': spec['gate_semantics'],
            'parsed': found, 'checks': [],
            'verdict': 'probe' if res['exit_code'] == spec['expect_exit'] else 'unexpected',
            'evidence_level': res['evidence_level'], 'duration_s': res['duration_s'],
            'real_db_sha256_before': res['real_db_sha256_before'],
            'real_db_sha256_after': res['real_db_sha256_after'],
            'real_db_unchanged': res['real_db_unchanged'],
            'stdout_tail': res['stdout'][-1500:], 'stderr_tail': res['stderr'][-1500:],
            '_raw_stdout': res['stdout'], '_raw_stderr': res['stderr'],
        }
    if spec['exit_code_informative'] and res['exit_code'] != spec['expect_exit']:
        verdict = 'fail'
    if hard_failed:
        verdict = 'fail'
    if not res['real_db_unchanged']:
        verdict = 'fail'
    if not spec['exit_code_informative'] and res['exit_code'] != 0 and not found:
        verdict = 'fail'
    return {
        'gate': spec['name'],
        'script': f'scripts/{spec["script"]}',
        'mode': 'shim' if spec['shim'] else 'native',
        'command': res['argv_display'],
        'cwd': res['cwd'],
        'exit_code': res['exit_code'],
        'expected_exit_code': spec['expect_exit'],
        'exit_code_informative': spec['exit_code_informative'],
        'gate_semantics': spec['gate_semantics'],
        'parsed': found,
        'checks': checks,
        'verdict': verdict,
        'evidence_level': res['evidence_level'],
        'duration_s': res['duration_s'],
        'real_db_sha256_before': res['real_db_sha256_before'],
        'real_db_sha256_after': res['real_db_sha256_after'],
        'real_db_unchanged': res['real_db_unchanged'],
        'stdout_tail': res['stdout'][-1500:],
        'stderr_tail': res['stderr'][-1500:],
        '_raw_stdout': res['stdout'],
        '_raw_stderr': res['stderr'],
    }


# ---------------------------------------------------------------- 负向自检（阳性对照）
SENSITIVITY = """
# 门禁敏感性自检：故意制造违规，要求门禁退出码 != 0（证明门禁不是恒真）。
# 全程只改内存对象 / 只读本 run 的隔离目录，不写仓库、不改任何既有脚本。
import contextlib, importlib.util, io, json, os, shutil, sys
ROOT = r'{root}'
SCRIPTS = r'{scripts}'
TMP = r'{tmp}'
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, ROOT)
results = {{}}
os.makedirs(TMP, exist_ok=True)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(func):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            rc = func()
        except SystemExit as e:
            rc = e.code
        except Exception as e:  # 门禁自身抛异常也算非零（但要留痕区分）
            rc = 'EXC %s: %s' % (e.__class__.__name__, e)
    return rc, buf.getvalue()


# 1) check_templates：注入未登记 capability -> 必须非 0
tpl = _load('ct_inj', os.path.join(SCRIPTS, 'check_templates.py'))
tpl.used_capabilities = lambda: {{'__hv_unknown_capability__': ['<injected>:1']}}
rc, out = _run(tpl.main)
results['check_templates_inject_unknown_capability'] = {{
    'exit_code': rc, 'expected_nonzero': True,
    'stdout_tail': out[-400:]}}

# 2) check_templates 基线（同一次进程内，证明注入前是 0）
tpl2 = _load('ct_base', os.path.join(SCRIPTS, 'check_templates.py'))
rc, out = _run(tpl2.main)
results['check_templates_baseline'] = {{
    'exit_code': rc, 'expected_nonzero': False, 'stdout_tail': out[-200:]}}

# 3) check_properties：在隔离目录种一个「类级访问不存在的列 / @property」-> 必须非 0
tpl3 = _load('cp_inj', os.path.join(SCRIPTS, 'check_properties.py'))
plant = os.path.join(TMP, 'planted')
os.makedirs(plant, exist_ok=True)
with open(os.path.join(plant, 'planted_violation.py'), 'w', encoding='utf-8') as fh:
    fh.write('from app.models import FinishedProduct, RawMaterial\\n\\n\\n'
             'def hv_probe():\\n'
             '    # A 类违规：RawMaterial.material_name 是 @property\\n'
             '    return (RawMaterial.material_name.like("%x%"),\\n'
             '            # B 类违规：FinishedProduct.current_stock 根本不存在\\n'
             '            FinishedProduct.current_stock > 0)\\n')
sys.argv = ['check_properties.py', '--root', plant]
rc, out = _run(tpl3.main)
results['check_properties_planted_violation'] = {{
    'exit_code': rc, 'expected_nonzero': True, 'stdout_tail': out[-500:]}}

# 3b) 同一违规文件改名成 .bak 后缀 -> 门禁按既定口径跳过（证明「跳过表」也是活的）
with open(os.path.join(plant, 'planted_violation.py.bak'), 'w', encoding='utf-8') as fh:
    fh.write(open(os.path.join(plant, 'planted_violation.py'), encoding='utf-8').read())
os.remove(os.path.join(plant, 'planted_violation.py'))
tpl3b = _load('cp_inj_bak', os.path.join(SCRIPTS, 'check_properties.py'))
sys.argv = ['check_properties.py', '--root', plant]
rc, out = _run(tpl3b.main)
results['check_properties_planted_violation_with_bak_suffix_skipped'] = {{
    'exit_code': rc, 'expected_nonzero': False, 'stdout_tail': out[-300:],
    'note': 'SKIP_SUFFIXES 口径：.bak 一律跳过（既有约定，非本次新增）'}}
shutil.rmtree(plant, ignore_errors=True)

# 4) check_properties：基线（扫描真实 app/，必须 0）
tpl4 = _load('cp_base', os.path.join(SCRIPTS, 'check_properties.py'))
sys.argv = ['check_properties.py', '--root', os.path.join(ROOT, 'app')]
rc, out = _run(tpl4.main)
results['check_properties_baseline'] = {{
    'exit_code': rc, 'expected_nonzero': False, 'stdout_tail': out[-200:]}}

# 5) check_migration_heads：把 get_heads 打成两个 head -> 必须非 0
mh = _load('mh_inj', os.path.join(SCRIPTS, 'check_migration_heads.py'))
_real = mh.ScriptDirectory.get_heads


def _two_heads(self):
    return ['__hv_fake_a__', '__hv_fake_b__']


mh.ScriptDirectory.get_heads = _two_heads
rc, out = _run(mh.main)
results['check_migration_heads_inject_two_heads'] = {{
    'exit_code': rc, 'expected_nonzero': True, 'stdout_tail': out[-300:]}}
mh.ScriptDirectory.get_heads = _real

# 6) check_migration_heads 基线
mh2 = _load('mh_base', os.path.join(SCRIPTS, 'check_migration_heads.py'))
rc, out = _run(mh2.main)
results['check_migration_heads_baseline'] = {{
    'exit_code': rc, 'expected_nonzero': False, 'stdout_tail': out[-200:]}}

print('__SENSITIVITY__' + json.dumps(results, ensure_ascii=False))
""".format(root=REPO_ROOT.replace('\\', '\\\\'),
           scripts=SCRIPTS_DIR.replace('\\', '\\\\'),
           tmp=os.path.join(tmp_dir('sensitivity_plant')).replace('\\', '\\\\'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--self-test', action='store_true', help='额外跑门禁敏感性自检')
    ap.add_argument('--out', default=os.path.join(EVIDENCE_DIR, 'gates.json'))
    args = ap.parse_args()

    # A-14：本机控制台默认 GBK（cp936）。stdout 显式行含非 GBK 字符时 `print` 会抛
    # UnicodeEncodeError ⇒ 「修复生效的 exit 1」与「崩溃的 exit 1」无法区分（captain 实测踩过）。
    # 只放宽 errors，不改 encoding：控制台中文仍可读，重定向到文件时仍按 UTF-8 落盘（子进程由
    # `_env.run_child` 强制 PYTHONIOENCODING=utf-8，证据原文不受影响）。
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(errors='replace')
        except Exception:
            pass

    run_id = os.environ.get('HARNESS_RUN_ID', 'adhoc')
    before = real_db_status()
    results = [run_gate(spec, run_id) for spec in GATES]
    after = real_db_status()

    out = {
        'harness': 'run_gates.py',
        'run_id': run_id,
        'interpreter': sys.executable,
        'repo_root': REPO_ROOT,
        'expected_lock': EXPECTED,
        'gates': results,
        'real_db': {'before': before, 'after': after,
                    'unchanged': before['sha256'] == after['sha256']},
        'summary': {
            'total': len(results),
            'pass': sum(1 for r in results if r['verdict'] == 'pass'),
            'fail': sum(1 for r in results if r['verdict'] == 'fail'),
            'probe_only': sum(1 for r in results if r.get('probe_only')),
            'probe_unexpected': sum(1 for r in results if r['verdict'] == 'unexpected'),
            'exit_code_informative': sum(1 for r in results if r['exit_code_informative']),
            'in_gate_chain': [r['gate'] for r in results if r['exit_code_informative']],
            'report_only': [r['gate'] for r in results
                            if not r['exit_code_informative'] and not r.get('probe_only')],
            'evidence_only': [r['gate'] for r in results if r.get('probe_only')],
            #: E-02：敏感性自检判决（False ⇒ 退出码 1）；未跑 --self-test 时为 None
            'sensitivity_ok': None,
        },
    }
    summary = out['summary']          # E-02：出口条件只读这一份（与 JSON 同源）

    if args.self_test:
        path = os.path.join(tmp_dir('inline'), 'gate_sensitivity.py')
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write("import sys;sys.stdout.reconfigure(encoding='utf-8',errors='replace')\n")
            fh.write(SENSITIVITY)
        res = run_child([path], cwd=REPO_ROOT, timeout=1200, label='gate_sensitivity')
        marker = [l for l in res['stdout'].splitlines() if l.startswith('__SENSITIVITY__')]
        parsed = json.loads(marker[0][len('__SENSITIVITY__'):]) if marker else None
        injections_ok = None
        baselines_ok = None
        injections_errored = []
        baselines_errored = []
        if parsed:
            injections = {k: v for k, v in parsed.items() if not k.endswith('_baseline')
                          and v.get('expected_nonzero')}
            baselines = {k: v for k, v in parsed.items() if not v.get('expected_nonzero')}
            # E-02（D-6 的另一半 / T-03）：非 int 退出码（`'EXC …'` / None）**必须计入未通过**。
            # 旧实现 `all(int(v['exit_code']) != 0 for v in ….values() if isinstance(…, int))`
            # 把抛异常的门禁直接**过滤掉** ⇒ 一个「一跑就崩」的门禁被判为敏感性通过。
            injections_errored = sorted(k for k, v in injections.items()
                                        if not isinstance(v.get('exit_code'), int))
            baselines_errored = sorted(k for k, v in baselines.items()
                                       if not isinstance(v.get('exit_code'), int))
            injections_ok = not injections_errored and all(
                int(v['exit_code']) != 0 for v in injections.values()
                if isinstance(v.get('exit_code'), int))
            baselines_ok = not baselines_errored and all(
                int(v['exit_code']) == 0 for v in baselines.values()
                if isinstance(v.get('exit_code'), int))
        out['sensitivity'] = {'probe_exit_code': res['exit_code'], 'parsed': parsed,
                              'injections_all_nonzero': injections_ok,
                              'baselines_all_zero': baselines_ok,
                              'injections_errored': injections_errored,
                              'baselines_errored': baselines_errored,
                              'evidence_level': res['evidence_level'],
                              'stdout_tail': res['stdout'][-800:]}

    # ---------------------------------------------------------- E-02：退出码判据
    # 旧实现（D-6 / T-02）只看 `summary['fail']`：
    #   ① `probe_unexpected > 0`（A-1 环境事实被破坏：原生 route_inventory 居然成功）
    #   ② 敏感性自检未通过（T-03 / F3，且非 int 退出码曾被静默过滤）
    # 都只落在 JSON 里而编排静默绿灯。现在三者一并并入出口条件，且在 stdout 显式打印。
    if args.self_test:
        sens = out['sensitivity']
        summary['sensitivity_ok'] = (sens.get('injections_all_nonzero') is True
                                     and sens.get('baselines_all_zero') is True)
    exit_reasons = []
    if summary['fail']:
        exit_reasons.append(f"fail={summary['fail']}")
    if summary['probe_unexpected']:
        exit_reasons.append(f"probe_unexpected={summary['probe_unexpected']}")
    if summary['sensitivity_ok'] is False:
        exit_reasons.append('sensitivity 未通过')
    exit_code = 1 if exit_reasons else 0
    out['exit_code_semantics'] = {
        'code': exit_code,
        'reasons': exit_reasons,
        'rule': ("exit 0 ⟺ summary['fail']==0 ∧ summary['probe_unexpected']==0 ∧ "
                 "(未跑 --self-test ∨ summary['sensitivity_ok'] is True)"),
        'inputs': {'fail': summary['fail'],
                   'probe_unexpected': summary['probe_unexpected'],
                   'sensitivity_ok': summary['sensitivity_ok']},
    }

    # 原始输出落盘（人读证据）
    for res in results:
        lines = [
            f'# gate={res["gate"]} mode={res["mode"]} exit_code={res["exit_code"]} '
            f'verdict={res["verdict"]} evidence_level={res["evidence_level"]}',
            f'# command: {res["command"]}',
            f'# cwd: {res["cwd"]}',
            f'# real_db unchanged: {res["real_db_unchanged"]}',
            '--- stdout ---',
            res.pop('_raw_stdout'),
            '--- stderr ---',
            res.pop('_raw_stderr'),
        ]
        save_evidence(f'gate_{res["gate"]}_{res["mode"]}.txt', '\n'.join(lines))

    ensure_dir(os.path.dirname(args.out) or '.')
    out_path, renamed = guard_write(args.out)      # E-01：目标已存在则改名保留，绝不覆盖
    with open(out_path, 'w', encoding='utf-8', newline='\n') as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    if renamed:
        print(f'[run_gates] 写入守卫：目标已存在 => 改名保留（原文件一字不动）-> {out_path}')

    print(f'[run_gates] run_id={run_id}  {out["summary"]["pass"]}/{out["summary"]["total"]} 项 pass')
    print(f'[run_gates] probe_unexpected = {summary["probe_unexpected"]}'
          f'   (取证型探针与锁定期望值不一致的条数；>0 => 退出码 1)')
    if args.self_test:
        print(f'[run_gates] sensitivity: injections_all_nonzero='
              f'{out["sensitivity"]["injections_all_nonzero"]} '
              f'baselines_all_zero={out["sensitivity"]["baselines_all_zero"]} '
              f'errored={out["sensitivity"]["injections_errored"] + out["sensitivity"]["baselines_errored"]}')
    for r in results:
        bad = [c for c in r['checks'] if c['status'] == 'failed']
        flag = 'OK  ' if r['verdict'] == 'pass' else ('EVID' if r['verdict'] == 'probe'
                                                      else 'FAIL')
        note = ''
        if r.get('probe_only'):
            note = ('  [取证型：退出码与锁定期望值一致 => 记 probe，不计失败]'
                    if r['verdict'] == 'probe' else
                    '  [取证型：退出码与锁定期望值不一致 => 计入 probe_unexpected => 退出码 1]')
        elif not r['exit_code_informative']:
            note = '  [报告型：退出码无信息量]'
        print(f'  {flag} {r["gate"]:<28} exit={r["exit_code"]} mode={r["mode"]:<6} '
              f'checks={len(r["checks"]) - len(bad)}/{len(r["checks"])}{note}')
        for c in bad:
            print(f'         !! {c["fact"]}: 期望 {c["expected"]}  实际 {c["actual"]}')
    print(f'[run_gates] real.db unchanged = {out["real_db"]["unchanged"]} ({before["sha256"][:16]}…)')
    print(f'[run_gates] exit = {exit_code}  原因={exit_reasons if exit_reasons else "无（全绿）"}')
    print(f'[run_gates] JSON -> {out_path}')
    return exit_code


if __name__ == '__main__':
    sys.exit(main())
