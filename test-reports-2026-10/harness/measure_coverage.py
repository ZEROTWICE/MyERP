"""端点覆盖量测：现有测试脚本**实际打到哪些端点** × 全量路由清单。

口径（`00b` 增补纪律 13：任何计数必须给「工具 + 口径 + 值」）：

* **分母（路由）**：`app.url_map.iter_rules()` **重算**（工具：Flask `url_map` 内省）；
  * 规则总数 **271**（含 `static` 1 条）= GET 无参 104 + GET 带参 56 + 非 GET 110 + `static` 1；
  * 方法级（一条规则可有多方法）：GET **161**（`url_map` 重算；⚠ `08` §2 记 160 —— A-25 分歧已登记）
    / POST 123 / DELETE 20 / PUT 12；**非 GET 方法级 155（两法一致）**。
* **分子（覆盖）**：AST 扫测试脚本里的 HTTP 调用字面量 URL（工具：`ast` 解析源码）；
  * `literal` 口径 = URL 里不含插值/变量；`dynamic` 口径 = f-string / `%` 格式化 / 变量拼接，
    **只能匹配到前缀**，单独统计、不与 literal 合并。
* 动态 URL 的匹配按「字面量前缀 + 参数段」比对，逐行标注 `literal` / `dynamic`。

**退出码语义（E-03 分类：报告型 ⇒ 恒 `exit 0`，不得进 CI 门禁链）**

本脚本 stdout 全是**度量值**、无判据语义 ⇒ `main()` 恒 `return 0` 是**有意设计**（A-30 / T-09）。
**判据不在退出码里**：由 `test-reports-2026-10/harness/coverage_drift.py`（TL-03）解析本脚本产出的
`coverage.json` 做漂移检测（例：`summary.writable_literal_covered_by_all` 由 6 变 5 ⇒ 判失败）。
CI 链里**不得**出现本脚本的退出码（A-62 的 report-only 集）。

用法（仓库根目录）：

    F:\\Miniconda\\envs\\wage\\python.exe -B test-reports-2026-10/harness/measure_coverage.py
"""
import argparse
import ast
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:  # 中文/符号输出在 GBK 控制台下会直接抛 UnicodeEncodeError（A-14）
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from _env import EVIDENCE_DIR, REPO_ROOT, ensure_dir, real_db_status

# 被量测的「探针脚本」（只读扫描，不执行）
# `exit_code_credible` 为 **E-03 后的现状**（t4 修改：smoke_test / permission_matrix 已转正；报告型仍不可信）
PROBES = [
    {'file': 'scripts/smoke_test.py', 'kind': 'request-probe（GET 广度）',
     'exit_code_credible': True,
     'why': 'E-03：写盘与退出码解耦（默认落 .tmp/<RUN_ID>/，--no-dump 可跳过）⇒ 退出码只反映断言'},
    {'file': 'scripts/permission_matrix.py', 'kind': 'request-probe（权限矩阵）',
     'exit_code_credible': True,
     'why': 'E-03：已补失败出口（anon_open != 0 => exit 1）＋ 写盘解耦'},
    {'file': 'scripts/functional_test.py', 'kind': '功能断言（写端点唯一来源）',
     'exit_code_credible': True, 'why': '不写仓库根 JSON，exit 0 可信'},
    {'file': 'scripts/route_inventory.py', 'kind': '路由清单',
     'exit_code_credible': False,
     'why': 'E-03：报告型（无判据语义 ⇒ 恒 0）⇒ 不得进链；判据由 harness/coverage_drift.py 解析'},
    {'file': 'scripts/check_db_bootstrap.py', 'kind': '空库自举', 'exit_code_credible': True,
     'why': ''},
    {'file': 'scripts/check_templates.py', 'kind': '静态门禁', 'exit_code_credible': True, 'why': ''},
    {'file': 'scripts/check_properties.py', 'kind': '静态门禁', 'exit_code_credible': True, 'why': ''},
    {'file': 'scripts/check_migration_heads.py', 'kind': '静态门禁', 'exit_code_credible': True,
     'why': ''},
]

HTTP_METHODS = ('get', 'post', 'put', 'delete', 'patch', 'head', 'options')
URL_TOKEN = re.compile(r'^(/[^\s"\']*)')


class UrlCollector(ast.NodeVisitor):
    """收集 `client.get('/x')` / `c.post(f'/x/{y}')` 形态的 URL 与所属函数名。"""

    def __init__(self):
        self.calls = []
        self._func = []

    def visit_FunctionDef(self, node):
        self._func.append(node.name)
        self.generic_visit(node)
        self._func.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node):
        func = node.func
        method = None
        if isinstance(func, ast.Attribute) and func.attr in HTTP_METHODS:
            method = func.attr.upper()
        if method and node.args:
            kind, text = _literal_url(node.args[0])
            if text is not None:
                self.calls.append({
                    'method': method,
                    'line': node.lineno,
                    'function': self._func[-1] if self._func else '<module>',
                    'kind': kind,
                    'raw': text,
                })
        self.generic_visit(node)


def _literal_url(node):
    """返回 ``(kind, text)``：``literal`` / ``dynamic`` / ``None``（非 URL 字面量）。"""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        v = node.value
        if v.startswith('/'):
            return ('literal', v)
        return (None, None)
    if isinstance(node, ast.JoinedStr):  # f-string
        parts = []
        for v in node.values:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                parts.append(v.value)
            else:
                parts.append('<var>')
        text = ''.join(parts)
        if 'url_for' in text:
            return (None, None)
        return ('dynamic', text) if text.startswith('/') else (None, None)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
        # '/x/%s' % y
        if isinstance(node.left, ast.Constant) and isinstance(node.left.value, str):
            text = node.left.value
            return ('dynamic', text) if text.startswith('/') else (None, None)
    return (None, None)


def normalise(path):
    """把 ``<int:id>`` / ``<id>`` / ``<var>`` / 具体数字统一成 ``<_>``，用于形状比对。"""
    path = path.split('?')[0]
    path = re.sub(r'<\s*(?:int:|string:|float:|path:|uuid:)?\w+\s*>', '<_>', path)
    path = re.sub(r'<var>', '<_>', path)
    path = re.sub(r'/\d+', '/<_>', path)
    path = re.sub(r'/[0-9a-fA-F]{8,}', '/<_>', path)
    if len(path) > 1:
        path = path.rstrip('/')
    return path


def route_inventory_and_rules(copy_tag='cover'):
    """用 ``fixtures`` 的副本隔离启动应用，返回路由清单（每条规则的 methods / arguments）。"""
    import fixtures
    app, path = fixtures.make_isolated_app(copy_tag)
    rules = []
    for r in app.url_map.iter_rules():
        methods = sorted(set(r.methods or set()) - {'HEAD', 'OPTIONS'})
        rules.append({
            'rule': str(r),
            'endpoint': r.endpoint,
            'methods': methods,
            'arguments': sorted(r.arguments),
            'path_shape': normalise(str(r)),
            'is_static': r.endpoint == 'static',
        })
    return app, path, rules


def collect_probes():
    out = []
    for p in PROBES:
        full = os.path.join(REPO_ROOT, p['file'])
        if not os.path.exists(full):
            out.append(dict(p, exists=False, calls=[]))
            continue
        src = open(full, encoding='utf-8').read()
        tree = ast.parse(src, filename=full)
        col = UrlCollector()
        col.visit(tree)
        out.append(dict(p, exists=True, calls=col.calls,
                        literals=sum(1 for c in col.calls if c['kind'] == 'literal'),
                        dynamics=sum(1 for c in col.calls if c['kind'] == 'dynamic')))
    return out


def probe_run_plan():
    """**静态**复现 smoke_test 的目标解析逻辑（不执行请求），得出它会打多少条。

    逐条复刻 `scripts/smoke_test.py` 的规则：
      * 只看 ``GET`` 且端点非 ``static``；
      * ``str(rule) in SKIP``（``/auth/logout`` / ``/auth/register`` / ``/bootstrap/static/<path:filename>``）跳过；
      * 带参规则经 ``resolve_args`` 从库取 id；``PATH_MODEL`` 未覆盖的参数 -> ``无法确定模型``。
    """
    import fixtures
    app, path = fixtures.make_isolated_app('coverplan')
    fixtures.seed_all(app)
    sys.path.insert(0, os.path.join(REPO_ROOT, 'scripts'))
    import smoke_test as st
    ids = st.first_ids(app)
    targets, unresolved = [], []
    for rule in app.url_map.iter_rules():
        if rule.endpoint == 'static' or 'GET' not in rule.methods:
            continue
        if str(rule) in st.SKIP:
            continue
        if rule.arguments:
            url, why = st.resolve_url(rule, ids)
            if url is None:
                unresolved.append({'rule': str(rule), 'endpoint': rule.endpoint, 'why': why})
                continue
            targets.append({'rule': str(rule), 'endpoint': rule.endpoint, 'url': url})
        else:
            targets.append({'rule': str(rule), 'endpoint': rule.endpoint, 'url': str(rule)})
    return {'ids': {k: list(v) for k, v in ids.items()}, 'targets': targets,
            'unresolved': unresolved, 'db_copy': path}


def run_request_probes(do_run=True):
    """实跑两条请求型探针（经 shim），抓 stdout 结论段；退出码**只登记不判定**。"""
    from _env import run_child, SCRIPTS_DIR
    out = {}
    if not do_run:
        return {'skipped': '--no-request-probes'}
    for name in ('smoke_test.py', 'permission_matrix.py'):
        res = run_child(['_sandbox_compat.py', name], cwd=SCRIPTS_DIR, timeout=3600,
                        label=f'probe_{name.replace(".py", "")}')
        text = res['stdout'] + res['stderr']
        record = {
            'script': f'scripts/{name}',
            'command': res['argv_display'],
            'exit_code': res['exit_code'],
            # E-03 后的现状：两条请求型脚本都已转正（补失败出口 / 写盘与退出码解耦）
            'exit_code_credible': True,
            'exit_code_note': ('E-03：已补失败出口（匿名可访问 != 0 => exit 1）＋ 写盘与退出码解耦'
                               if name == 'permission_matrix.py' else
                               'E-03：写盘与退出码解耦（默认落 .tmp/<RUN_ID>/）⇒ 只反映断言'),
            'evidence_level': res['evidence_level'],
            'real_db_unchanged': res['real_db_unchanged'],
        }
        for key, rx in (
            ('plan_testable_get_routes', r'\[plan\]\s*可测 GET 路由\s*(\d+)\s*条'),
            ('plan_skipped_get_routes', r'跳过\s*(\d+)\s*条'),
            ('anonymous_accessible', r'匿名可访问（应为 0，登录页/静态资源除外）'),
            ('no_validation_views', r'源码上完全没有权限校验的视图'),
        ):
            m = re.search(rx, text)
            record[key] = (m.group(1) if m and m.groups() else bool(m))
        record['exception_summary_present'] = '异常汇总' in text
        record['stdout_conclusion_tail'] = '\n'.join(
            [l for l in text.splitlines() if l.strip()][-40:])
        # 原始输出落盘（人读证据，按 A-14 已按 utf-8 解码）
        ev = os.path.join(EVIDENCE_DIR, f'probe_{name.replace(".py", "")}.txt')
        with open(ev, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(f'# command: {res["argv_display"]}\n# cwd: {res["cwd"]}\n'
                     f'# exit_code: {res["exit_code"]}\n'
                     f'# evidence_level: {res["evidence_level"]}\n'
                     f'# real_db_unchanged: {res["real_db_unchanged"]}\n'
                     '--- stdout ---\n' + res['stdout'] + '\n--- stderr ---\n' + res['stderr'])
        record['evidence_file'] = os.path.relpath(ev, REPO_ROOT).replace('\\', '/')
        out[name] = record
    return out


def build_coverage(rules, probes):
    """逐路由标注：哪些探针用 literal / dynamic 打到它（分方法级不再拆分，方法级另算）。"""
    by_shape = {}
    for r in rules:
        by_shape.setdefault(r['path_shape'], []).append(r)
    hits = {r['rule']: {} for r in rules}
    unmatched = {p['file']: [] for p in probes}

    for p in probes:
        for call in p.get('calls', []):
            shape = normalise(call['raw'])
            matched = by_shape.get(shape, [])
            if not matched and call['kind'] == 'dynamic':
                prefix = normalise(call['raw'].split('<var>')[0]).rstrip('/')
                matched = [r for r in rules
                           if prefix and r['path_shape'].startswith(prefix)]
            for r in matched:
                slot = hits[r['rule']].setdefault(
                    p['file'], {'literal': False, 'dynamic': False, 'methods': set()})
                slot[call['kind']] = True
                slot['methods'].add(call['method'])
            if not matched:
                unmatched.setdefault(p['file'], []).append(call)

    for r in rules:
        r['covered_by'] = hits[r['rule']]
        for slot in r['covered_by'].values():
            slot['methods'] = sorted(slot['methods'])
    return unmatched


def summarise(rules, probes):
    def non_get_methods(r):
        return [m for m in r['methods'] if m != 'GET']

    def hit(r, files=None, kind=None, method=None):
        for f, v in r['covered_by'].items():
            if files and f not in files:
                continue
            if kind and not v.get(kind):
                continue
            if method and method not in v.get('methods', []):
                continue
            return True
        return False

    writable = [r for r in rules if non_get_methods(r) and not r['is_static']]
    readable = [r for r in rules if r['methods'] == ['GET'] and not r['is_static']]
    functional = ['scripts/functional_test.py']

    def method_level(rules_, method, files=None, kind=None):
        n_covered = 0
        for r in rules_:
            if r['is_static'] or method not in r['methods']:
                continue
            if hit(r, files=files, kind=kind, method=method):
                n_covered += 1
        return n_covered

    non_get_ml = {m: sum(1 for r in rules for x in r['methods'] if x == m)
                  for m in ('POST', 'DELETE', 'PUT', 'PATCH')}
    return {
        'rules_total': len(rules),
        'rules_static': sum(1 for r in rules if r['is_static']),
        'rules_get_no_arg': sum(1 for r in rules if 'GET' in r['methods'] and not r['arguments']
                                and not r['is_static']),
        'rules_get_with_arg': sum(1 for r in rules if 'GET' in r['methods'] and r['arguments']
                                  and not r['is_static']),
        'rules_non_get': sum(1 for r in rules if 'GET' not in r['methods']),
        'rules_get_only': len(readable),
        'method_level_total': sum(len(r['methods']) for r in rules),
        'method_level_GET': sum(1 for r in rules if 'GET' in r['methods']),
        'method_level_POST': non_get_ml['POST'],
        'method_level_DELETE': non_get_ml['DELETE'],
        'method_level_PUT': non_get_ml['PUT'],
        'method_level_non_get_total': sum(non_get_ml.values()),
        # 口径 B（与 08/06 的 155 同源还是另源，见 conventions.reference_155）
        'method_level_non_get_via_multi_method_rules': sum(
            len(non_get_methods(r)) for r in rules if non_get_methods(r)),
        'writable_rules_non_get': len(writable),
        'writable_literal_covered_by_functional': sum(
            1 for r in writable if hit(r, files=functional, kind='literal')),
        'writable_literal_covered_by_all': sum(1 for r in writable if hit(r, kind='literal')),
        'writable_any_covered_by_functional': sum(
            1 for r in writable if hit(r, files=functional)),
        'writable_any_covered_by_all': sum(1 for r in writable if hit(r)),
        'function_writes_literal_covered_method_level': sum(
            1 for m in ('POST', 'DELETE', 'PUT')
            for r in writable if m in r['methods']
            and hit(r, files=functional, kind='literal', method=m)),
        'function_writes_method_level_total': sum(
            1 for m in ('POST', 'DELETE', 'PUT') for r in writable if m in r['methods']),
        'readable_rules_get_only': len(readable),
        'readable_any_covered_by_all': sum(1 for r in readable if hit(r)),
    }


def method_matrix(rules):
    """逐「规则 × 方法」的覆盖行（口径明确到方法级）。"""
    rows = []
    for r in rules:
        if r['is_static']:
            continue
        for m in r['methods']:
            files_lit = sorted(f for f, v in r['covered_by'].items() if v['literal'])
            files_dyn = sorted(f for f, v in r['covered_by'].items() if v['dynamic'])
            rows.append({
                'rule': r['rule'], 'endpoint': r['endpoint'], 'method': m,
                'literal_covered_by': files_lit, 'dynamic_covered_by': files_dyn,
                'literal_covered': bool(files_lit),
                'dynamic_only': bool(files_dyn) and not files_lit,
                'covered_any': bool(files_lit or files_dyn),
            })
    return rows


def uncovered_list(rules):
    out = []
    for r in rules:
        if r['is_static'] or not r['covered_by']:
            out.append({'rule': r['rule'], 'endpoint': r['endpoint'],
                        'methods': r['methods'],
                        'reason': '无任何被测脚本的字面量/动态 URL 命中'})
    return out


def probe_call_summary(probes):
    rows = []
    for p in probes:
        rows.append({
            'file': p['file'],
            'kind': p['kind'],
            'exit_code_credible': p['exit_code_credible'],
            'why_exit_code_unreliable': p['why'],
            'url_call_sites': len(p.get('calls', [])),
            'literal': p.get('literals', 0),
            'dynamic': p.get('dynamics', 0),
            'distinct_literal_urls': sorted({c['raw'] for c in p.get('calls', [])
                                             if c['kind'] == 'literal'}),
            'helper_resolved': p['file'] in (
                'scripts/smoke_test.py', 'scripts/permission_matrix.py'),
            'helper_resolved_note': (
                'URL 由 resolve_url(first_ids) 从 url_map 动态解析 ⇒ AST 扫不到字面量，'
                '只能由「实跑结论段」量测' if p['file'] in (
                    'scripts/smoke_test.py', 'scripts/permission_matrix.py') else ''),
        })
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(EVIDENCE_DIR, 'coverage.json'))
    ap.add_argument('--copy-tag', default='cover')
    ap.add_argument('--no-request-probes', action='store_true',
                    help='跳过实跑 smoke_test / permission_matrix（默认会跑，产物只落本 run 隔离目录）')
    args = ap.parse_args()

    before = real_db_status()
    app, copy_path, rules = route_inventory_and_rules(args.copy_tag)
    probes = collect_probes()
    unmatched = build_coverage(rules, probes)
    summary = summarise(rules, probes)
    matrix = method_matrix(rules)

    plan = probe_run_plan()
    probe_runs = run_request_probes(do_run=not args.no_request_probes)
    smoke = probe_runs.get('smoke_test.py', {})
    plan_from_run = smoke.get('plan_testable_get_routes')
    plan_from_static = len(plan['targets'])
    plan_skipped_static = len(plan['unresolved'])

    out = {
        'harness': 'measure_coverage.py',
        'run_id': os.environ.get('HARNESS_RUN_ID', 'adhoc'),
        'interpreter': sys.executable,
        'isolation': {'db_copy': copy_path, 'uri': app.config['SQLALCHEMY_DATABASE_URI']},
        'conventions': {
            'route_denominator': 'app.url_map.iter_rules() 重算（工具=Flask url_map 内省）',
            'rule_count': '271 = GET 无参 104 + GET 带参 56 + 非 GET 110 + static 1',
            'method_level_GET': 'url_map 重算 = 161；08 §2 记 160（A-25 分歧，须写方法与口径）',
            'method_level_POST_DELETE_PUT': 'url_map 重算 = 123 / 20 / 12',
            'reference_155': ('08 §2 / 06 §4.2 的「非 GET 方法级端点 155」：本工具按'
                              '「method ∈ rule.methods 的 (method, rule) 计数」得 155；'
                              '本文件 summary.method_level_non_get_via_multi_method_rules '
                              '是同一事实的另一写法，两者必须同时引用（见 comparison）'),
            'coverage_numerator': ('ast 解析测试脚本里的 HTTP 调用字面量 URL；'
                                   'literal 与 dynamic 分开统计，不合并'),
            'dynamic_caveat': 'dynamic（f-string/格式化）只按前缀匹配，可能高估；已在行的 dynamic 字段标注',
            'smoke_plan': 'smoke_test 的目标集合是 url_map 动态解析的，AST 扫不到 ⇒ 其覆盖由实跑结论段量测',
        },
        'summary': summary,
        'method_matrix': matrix,
        'probes': probe_call_summary(probes),
        'unmatched_calls': {k: [{'method': c['method'], 'raw': c['raw'], 'kind': c['kind'],
                                 'file_line': f"{k}:{c['line']}"} for c in v]
                            for k, v in unmatched.items() if v},
        'smoke_test_plan': {
            'static_reproduction_targets': plan_from_static,
            'static_reproduction_unresolved': plan_skipped_static,
            'unresolved_detail': plan['unresolved'],
            'run_reported_targets': plan_from_run,
            'consistent_with_run': (str(plan_from_static) == str(plan_from_run)
                                    if plan_from_run is not None else None),
        },
        'request_probe_runs': probe_runs,
        'routes': rules,
        'uncovered_writable': [r for r in uncovered_list(rules) if 'GET' not in r['methods']],
        'uncovered_get_only': [r for r in uncovered_list(rules) if r['methods'] == ['GET']],
        'uncovered_multi_method_with_get': [r for r in uncovered_list(rules)
                                            if 'GET' in r['methods'] and r['methods'] != ['GET']],
        'real_db': {'before': before, 'checked_at_end': real_db_status()},
    }
    out['real_db']['unchanged'] = out['real_db']['before']['sha256'] == \
        out['real_db']['checked_at_end']['sha256']
    out['comparison'] = {
        'non_get_method_level_calc_A_len_of_list': summary['method_level_non_get_total'],
        'non_get_method_level_calc_B_sum_multi_method': summary[
            'method_level_non_get_via_multi_method_rules'],
        'reference_08_says': 155,
        'matches_A': summary['method_level_non_get_total'] == 155,
        'matches_B': summary['method_level_non_get_via_multi_method_rules'] == 155,
    }

    ensure_dir(os.path.dirname(args.out))
    with open(args.out, 'w', encoding='utf-8', newline='\n') as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)

    s = summary
    print(f'[coverage] 路由（url_map 重算）：{s["rules_total"]} 条规则 = '
          f'GET 无参 {s["rules_get_no_arg"]} + GET 带参 {s["rules_get_with_arg"]} + '
          f'非 GET {s["rules_non_get"]} + static {s["rules_static"]}')
    print(f'[coverage] 方法级：GET {s["method_level_GET"]}（08 记 160）/ POST {s["method_level_POST"]} / '
          f'DELETE {s["method_level_DELETE"]} / PUT {s["method_level_PUT"]}；'
          f'非 GET 计数A={s["method_level_non_get_total"]} 计数B={s["method_level_non_get_via_multi_method_rules"]}'
          f'（08 记 155，matchesA={out["comparison"]["matches_A"]} matchesB={out["comparison"]["matches_B"]}）')
    print(f'[coverage] 写端点（非 GET 规则）{s["writable_rules_non_get"]} 条；'
          f'functional_test 字面量覆盖 {s["writable_literal_covered_by_functional"]} 条 '
          f'（{s["writable_literal_covered_by_functional"] / max(s["writable_rules_non_get"], 1) * 100:.1f}%）；'
          f'全部探针字面量覆盖 {s["writable_literal_covered_by_all"]} 条；'
          f'含动态命中 {s["writable_any_covered_by_all"]} 条')
    print(f'[coverage] 只读端点（仅 GET 规则）{s["readable_rules_get_only"]} 条；'
          f'AST 字面量/动态命中 {s["readable_any_covered_by_all"]} 条；'
          f'smoke_test 实跑计划覆盖 {plan_from_run} 条（静态复现 {plan_from_static} 条，'
          f'跳过 {plan_skipped_static} 条）')
    print(f'[coverage] 未被任何 AST 命中的写端点 {len(out["uncovered_writable"])} 条，'
          f'仅 GET 端点 {len(out["uncovered_get_only"])} 条，'
          f'GET+其他方法端点 {len(out["uncovered_multi_method_with_get"])} 条')
    print(f'[coverage] JSON -> {args.out}；real.db unchanged = {out["real_db"]["unchanged"]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
