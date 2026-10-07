"""coverage_drift.py — 报告型脚本的**判据层**（TL-03 雏形，E-03/t4 交付）。

**为什么需要它**：`scripts/route_inventory.py` 与 `harness/measure_coverage.py` 属**报告型**
（stdout 全是度量值、无判据语义 ⇒ 恒 `exit 0`，A-30 / T-09）——它们的退出码**永久不可作判据**。
判据必须落在**解析它们的产物**上：本脚本读 `coverage.json`（`measure_coverage.py --out`）与
可选的路由清单 stdout（`route_inventory.py`），按**锁死期望值**判「覆盖是否退化」，并给出失败出口。

**锁死期望值（来源：`08`/`06` + A-28/A-31 + `run_gates.EXPECTED`，全部为「不许退化」型）**

| id | 判据 | 期望 |
| --- | --- | --- |
| D-1 | `summary.rules_total` | `== 271`（路由总数，口径：`url_map.iter_rules()`） |
| D-2 | `summary.method_level_non_get_total` | `>= 155`（非 GET 方法级，A-28：与方法级 155 同源） |
| D-3 | `summary.writable_rules_non_get` | `== 153`（可写规则级，`153 != 155` 不可互替） |
| D-4 | `summary.writable_literal_covered_by_all` | `>= 6`（字面量覆盖，G-05 不许退化） |
| D-5 | `summary.writable_any_covered_by_all` | `>= 14`（含动态覆盖，G-05 不许退化） |
| D-6 | `len(uncovered_writable)` | `<= 101`（无命中写端点不得增加） |
| D-7 | `smoke_test_plan.static_reproduction_targets` / `_unresolved` | `== 148` / `== 9` |
| D-8 | `--routes-stdout`：`total rules` / `duplicate (method,path) registrations` | `== 271` / `== 0` |

用法（仓库根目录）——**CI 里报告型脚本与判据层的正确接法**：

    # 1) 报告型：跑，但**忽略**其退出码（A-62 的 report-only 集）
    python -B test-reports-2026-10/harness/measure_coverage.py --out <run>/coverage.json
    python -B scripts/_sandbox_compat.py scripts/route_inventory.py > <run>/route_inventory.txt
    # 2) 判据层：只看这一条命令的退出码（blocking）
    python -B test-reports-2026-10/harness/coverage_drift.py \
        --coverage <run>/coverage.json --routes-stdout <run>/route_inventory.txt

`--selftest` 对抗自检：用合成文档做 1 阳性 + 8 阴性注入，证明「漂移必被判失败」（不读活体文件 ⇒
不受并发写入影响）。`--json` 额外打印机读 JSON。

退出码：`0` = 全部判据通过；`1` = 任一判据失败（含文件缺失 / 不可解析 / 自检不敏感）。
"""
import argparse
import json
import os
import re
import sys

# A-14：本机控制台默认 GBK；print 非 GBK 字符不得把「判据失败」与「崩溃」混为一谈。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors='replace')
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
REPORTS_ROOT = os.path.dirname(HERE)
DEFAULT_COVERAGE = os.path.join(REPORTS_ROOT, 'evidence', 'harness', 'coverage.json')

#: 锁死期望值（单一存放点；改这里 = 改判据，必须与 08/06/A-28/A-31 同步）
LOCKED = {
    'rules_total': ('==', 271),
    'method_level_non_get_total': ('>=', 155),
    'writable_rules_non_get': ('==', 153),
    'writable_literal_covered_by_all': ('>=', 6),
    'writable_any_covered_by_all': ('>=', 14),
}
UNCOVERED_WRITABLE_MAX = 101
SMOKE_TARGETS = 148
SMOKE_UNRESOLVED = 9
ROUTE_RULES = 271
ROUTE_DUP = 0


def _cmp(actual, op, expected):
    if actual is None:
        return False
    if op == '==':
        return actual == expected
    if op == '>=':
        return actual >= expected
    if op == '<=':
        return actual <= expected
    raise ValueError(op)


def evaluate(doc, routes_text=None):
    """对 coverage.json（+ 可选的路由清单 stdout）逐条判据；返回 checks 列表。"""
    checks = []

    def add(cid, judge, expected, actual, status):
        checks.append({'id': cid, 'judge': judge, 'expected': expected,
                       'actual': actual, 'status': status})

    summary = (doc or {}).get('summary') or {}
    for key, (op, expected) in LOCKED.items():
        actual = summary.get(key)
        add(f'D-{list(LOCKED).index(key) + 1}', f'summary.{key} {op} {expected}',
            f'{op} {expected}', actual,
            'passed' if _cmp(actual, op, expected) else 'failed')

    uncovered = (doc or {}).get('uncovered_writable')
    n_uncovered = len(uncovered) if isinstance(uncovered, list) else None
    add('D-6', f'len(uncovered_writable) <= {UNCOVERED_WRITABLE_MAX}',
        f'<= {UNCOVERED_WRITABLE_MAX}', n_uncovered,
        'passed' if isinstance(n_uncovered, int) and n_uncovered <= UNCOVERED_WRITABLE_MAX
        else 'failed')

    plan = (doc or {}).get('smoke_test_plan') or {}
    t = plan.get('static_reproduction_targets')
    u = plan.get('static_reproduction_unresolved')
    add('D-7', 'smoke_test_plan 静态复现 148 / 未解析 9',
        f'== {SMOKE_TARGETS} / == {SMOKE_UNRESOLVED}', f'{t} / {u}',
        'passed' if (t == SMOKE_TARGETS and u == SMOKE_UNRESOLVED) else 'failed')

    if routes_text is None:
        add('D-8', 'route_inventory stdout（未提供 --routes-stdout）', 'skipped', None, 'skipped')
    else:
        m_rules = re.search(r'\[routes\]\s*total rules=(\d+)', routes_text)
        m_dup = re.search(r'duplicate \(method,path\) registrations=(\d+)', routes_text)
        rules = int(m_rules.group(1)) if m_rules else None
        dup = int(m_dup.group(1)) if m_dup else None
        add('D-8', f'route_inventory: total rules == {ROUTE_RULES} 且 duplicate == {ROUTE_DUP}',
            f'== {ROUTE_RULES} / == {ROUTE_DUP}', f'{rules} / {dup}',
            'passed' if (rules == ROUTE_RULES and dup == ROUTE_DUP) else 'failed')
    return checks


def synthetic_doc():
    """自检用合成文档（**不读活体文件**，避免并发写入干扰阳性对照）。"""
    return {
        'summary': {
            'rules_total': 271, 'method_level_non_get_total': 155,
            'writable_rules_non_get': 153, 'writable_literal_covered_by_all': 6,
            'writable_any_covered_by_all': 14,
        },
        'uncovered_writable': [{'rule': f'/x{i}'} for i in range(101)],
        'smoke_test_plan': {'static_reproduction_targets': 148,
                            'static_reproduction_unresolved': 9},
    }


def selftest():
    """1 阳性 + 8 阴性注入：漂移必须被判失败（门禁敏感性）。"""
    routes_ok = '[routes] total rules=271\nduplicate (method,path) registrations=0\n'
    results = []

    def case(cid, doc, routes, must_fail):
        checks = evaluate(doc, routes)
        failed = [c['id'] for c in checks if c['status'] == 'failed']
        got = bool(failed)
        results.append({'id': cid, 'must_fail': must_fail, 'got_fail': got,
                        'failed_ids': failed,
                        'status': 'passed' if got == must_fail else 'failed'})

    case('CD-P1 阳性对照：合成基线必须全过', synthetic_doc(), routes_ok, False)
    d = synthetic_doc(); d['summary']['writable_literal_covered_by_all'] = 5
    case('CD-N1 字面量覆盖 6→5', d, routes_ok, True)
    d = synthetic_doc(); d['summary']['writable_any_covered_by_all'] = 13
    case('CD-N2 含动态覆盖 14→13', d, routes_ok, True)
    d = synthetic_doc(); d['summary']['method_level_non_get_total'] = 154
    case('CD-N3 非 GET 方法级 155→154', d, routes_ok, True)
    d = synthetic_doc(); d['summary']['writable_rules_non_get'] = 152
    case('CD-N4 可写规则级 153→152', d, routes_ok, True)
    d = synthetic_doc(); d['summary']['rules_total'] = 272
    case('CD-N5 路由总数 271→272', d, routes_ok, True)
    d = synthetic_doc(); d['uncovered_writable'] = d['uncovered_writable'] + [{'rule': '/new'}]
    case('CD-N6 无命中写端点 101→102', d, routes_ok, True)
    d = synthetic_doc(); d['smoke_test_plan']['static_reproduction_targets'] = 147
    case('CD-N7 smoke 计划 148→147', d, routes_ok, True)
    case('CD-N8 路由清单 duplicate 0→1', synthetic_doc(),
         routes_ok.replace('registrations=0', 'registrations=1'), True)

    for r in results:
        print(f"  [{'PASS' if r['status'] == 'passed' else 'FAIL'}] {r['id']}"
              f"{'  (判失败项: ' + ','.join(r['failed_ids']) + ')' if r['failed_ids'] else ''}")
    n = sum(1 for r in results if r['status'] == 'passed')
    all_ok = n == len(results)
    print(f'[coverage_drift] 自检结果 {n}/{len(results)} 通过'
          f" => {'敏感性 OK' if all_ok else '门禁不敏感'}")
    return 0 if all_ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(
        description='报告型脚本产物的判据层（E-03/TL-03）：解析 coverage.json / 路由清单出判据')
    ap.add_argument('--coverage', default=DEFAULT_COVERAGE,
                    help=f'coverage.json 路径（默认 {DEFAULT_COVERAGE}）')
    ap.add_argument('--routes-stdout', default=None,
                    help='route_inventory.py 的 stdout 落盘文件（判 D-8）')
    ap.add_argument('--selftest', action='store_true', help='对抗自检（1 阳性 + 8 阴性注入）')
    ap.add_argument('--json', action='store_true', help='额外打印机读 JSON')
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()

    reasons = []
    if not os.path.isfile(args.coverage):
        print(f'[FAIL] coverage.json 不存在：{args.coverage}')
        print(f'[coverage_drift] exit = 1  原因=[coverage.json 缺失]')
        return 1
    try:
        with open(args.coverage, encoding='utf-8') as fh:
            doc = json.load(fh)
    except (OSError, ValueError) as e:
        print(f'[FAIL] coverage.json 不可解析：{e.__class__.__name__}: {e}')
        print(f'[coverage_drift] exit = 1  原因=[coverage.json 不可解析]')
        return 1

    routes_text = None
    if args.routes_stdout:
        if not os.path.isfile(args.routes_stdout):
            print(f'[FAIL] --routes-stdout 不存在：{args.routes_stdout}')
            reasons.append('routes-stdout 缺失')
        else:
            with open(args.routes_stdout, encoding='utf-8', errors='replace') as fh:
                routes_text = fh.read()

    checks = evaluate(doc, routes_text)
    print(f'[coverage_drift] coverage={args.coverage}')
    if args.routes_stdout:
        print(f'[coverage_drift] routes_stdout={args.routes_stdout}')
    for c in checks:
        if c['status'] == 'skipped':
            print(f"  [SKIP] {c['id']} {c['judge']}")
            continue
        flag = 'OK  ' if c['status'] == 'passed' else 'FAIL'
        print(f"  [{flag}] {c['id']} {c['judge']}  实际={c['actual']}")
        if c['status'] == 'failed':
            reasons.append(f"{c['id']}({c['judge']} 实际={c['actual']})")

    failed = [c['id'] for c in checks if c['status'] == 'failed']
    code = 1 if (failed or reasons) else 0
    print(f'[coverage_drift] 判据 {len(checks) - len(failed)}/{len(checks)} 通过'
          f"  => exit {code}  原因={reasons if reasons else '无（全绿）'}")
    print('[e03] exit_code_semantics=' + json.dumps({
        'script': 'test-reports-2026-10/harness/coverage_drift.py',
        'class': '真闸门（报告型产物的判据层，TL-03 雏形）',
        'rule': 'all checks passed -> exit 0; any failed -> exit 1',
        'inputs': {'failed_checks': failed, 'coverage': args.coverage,
                   'routes_stdout': args.routes_stdout},
        'code': code,
    }, ensure_ascii=False))
    if args.json:
        print(json.dumps({'checks': checks, 'exit_code': code, 'reasons': reasons},
                         ensure_ascii=False, indent=1))
    return code


if __name__ == '__main__':
    sys.exit(main())
