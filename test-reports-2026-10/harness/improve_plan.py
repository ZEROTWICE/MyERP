"""t7 只读重算器：为《07-测试与工程改进报告》提供可逐条复算的证据。

设计约束（严格遵守本战役裁定）：

* **只读**：不修改 `app/`、模板、配置、`scripts/` 既有脚本、任何他人交付物；不写 `docs/` 树。
* **不重跑会产生证据的脚本（A-40）**：本脚本**不调用** `run_gates.py` / `negative_matrix.py` /
  `measure_coverage.py` / `api_matrix.py` / `write_suite.py` / `uat_chains.py`，
  只**读取**它们已落盘的机读 JSON 并重算派生量。
* **不 import 应用**：`create_app()` 会触发启动自愈并可能写库 ⇒ 本脚本不导入 `app`，
  一切源码事实用 `ast` / 正则**读文本**得出。
* **不覆盖既有证据**：写出的文件若已存在，则自动改名（加 `.<run_id>` 后缀）并如实登记，
  这就是本报告 P-0 改进项「证据只追加、不覆盖」的自我实现。
* 行数口径 = Python `splitlines()`（A-23）；解释器 = `F:\\Miniconda\\envs\\wage\\python.exe`（A-7）。

用法：

    F:\\Miniconda\\envs\\wage\\python.exe -B test-reports-2026-10/harness/improve_plan.py
    F:\\Miniconda\\envs\\wage\\python.exe -B test-reports-2026-10/harness/improve_plan.py --finalize
    # 调试可用 --out-dir <dir> 把产出改到临时目录
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import sys
import time

HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))
REPORTS_ROOT = os.path.dirname(HARNESS_DIR)
REPO_ROOT = os.path.dirname(REPORTS_ROOT)
APP_DIR = os.path.join(REPO_ROOT, 'app')
SCRIPTS_DIR = os.path.join(REPO_ROOT, 'scripts')
EVIDENCE_ROOT = os.path.join(REPORTS_ROOT, 'evidence')
EVID_DIR = os.path.join(EVIDENCE_ROOT, 'improve')

REAL_DB = os.path.join(REPO_ROOT, 'app.db')
REAL_DB_SHA256_EXPECTED = 'F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065'

REPORT_DOC = os.path.join(REPORTS_ROOT, '07-测试与工程改进报告.md')
SELF = os.path.abspath(__file__)

RUN_ID = os.environ.get('HARNESS_RUN_ID') or time.strftime('t7-improve-%Y%m%d-%H%M%S')

# 声明式指针：evidence/improve/ 下要参与哈希基线的制品（artifact_hashes.json 自身除外）
HASH_TARGETS = [
    '07-测试与工程改进报告.md',
    'harness/improve_plan.py',
    'evidence/improve/improve_plan.json',
    'evidence/improve/improve_plan.out.txt',
    'evidence/improve/fix_plan.json',
]

results = {'checks': [], 'counts': [], 'recount': {}, 'notes': []}


# --------------------------------------------------------------------------- 输出
class Tee:
    def __init__(self, path):
        self.path = path
        self.lines = []
        self.fh = None
        if path:
            self.fh = open(path, 'w', encoding='utf-8', newline='\n')

    def write(self, text=''):
        self.lines.append(text)
        print(text)
        if self.fh:
            self.fh.write(text + '\n')

    def close(self):
        if self.fh:
            self.fh.close()
            self.fh = None


def guard_write(path):
    """写前守卫：目标已存在 ⇒ 绝不覆盖，改名并登记（P-0 改进项的自我实现）。"""
    if not os.path.exists(path):
        return path, False
    base, ext = os.path.splitext(path)
    alt = f'{base}.{RUN_ID}{ext}'
    n = 1
    while os.path.exists(alt):
        alt = f'{base}.{RUN_ID}.{n}{ext}'
        n += 1
    return alt, True


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path


# --------------------------------------------------------------------------- 基础
def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest().upper()


def fingerprint(path):
    if not os.path.exists(path):
        return {'path': rel(path), 'exists': False}
    with open(path, encoding='utf-8', errors='replace') as fh:
        text = fh.read()
    return {
        'path': rel(path),
        'exists': True,
        'bytes': os.path.getsize(path),
        'total_lines': len(text.splitlines()),
        'nonempty_lines': sum(1 for l in text.splitlines() if l.strip()),
        'sha256': sha256_file(path),
    }


def rel(path):
    return os.path.relpath(path, REPO_ROOT).replace('\\', '/')


_LINE_CACHE = {}


def lines_of(path):
    if path not in _LINE_CACHE:
        with open(path, encoding='utf-8', errors='replace') as fh:
            _LINE_CACHE[path] = fh.read().split('\n')
    return _LINE_CACHE[path]


def check(cid, desc, path, line, needle, expect=True, window=0):
    """断言 path 的第 line 行（±window）是否包含/不包含 needle。行号以实测为准并回写。"""
    item = {'id': cid, 'desc': desc, 'file': rel(path), 'line_requested': line,
            'needle': needle, 'expect_present': expect, 'window': window}
    try:
        if not os.path.exists(path):
            item.update({'ok': False, 'found_line': None, 'found_text': None,
                         'reason': '文件不存在'})
        else:
            ls = lines_of(path)
            lo = max(1, line - window)
            hi = min(len(ls), line + window)
            hit_line, hit_text = None, None
            for n in range(lo, hi + 1):
                text = ls[n - 1]
                if needle in text:
                    hit_line, hit_text = n, text.strip()
                    break
            present = hit_line is not None
            item.update({'ok': present == expect, 'found_line': hit_line,
                         'found_text': (hit_text[:200] if hit_text else None),
                         'line_text_requested': ls[line - 1].strip()[:200] if line <= len(ls) else None})
            if not item['ok']:
                item['reason'] = (f'期望{"包含" if expect else "不包含"} {needle!r}，'
                                  f'实测{"命中" if present else "未命中"}')
    except Exception as e:  # 环境层失败不静默
        item.update({'ok': False, 'reason': f'{e.__class__.__name__}: {e}'})
    results['checks'].append(item)
    return item


def count_in_file(path, pattern, label, flags=0):
    """在单文件里正则计数（读文本，不执行）。"""
    item = {'label': label, 'file': rel(path), 'pattern': pattern}
    try:
        with open(path, encoding='utf-8', errors='replace') as fh:
            text = fh.read()
        item['count'] = len(re.findall(pattern, text, flags))
    except Exception as e:
        item['count'] = None
        item['error'] = f'{e.__class__.__name__}: {e}'
    results['counts'].append(item)
    return item


def count_in_tree(root, pattern, label, flags=0):
    item = {'label': label, 'root': rel(root), 'pattern': pattern, 'per_file': {}}
    total = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ('__pycache__', '.git')]
        for name in filenames:
            if not name.endswith('.py'):
                continue
            p = os.path.join(dirpath, name)
            try:
                with open(p, encoding='utf-8', errors='replace') as fh:
                    text = fh.read()
            except Exception:
                continue
            n = len(re.findall(pattern, text, flags))
            if n:
                item['per_file'][rel(p)] = n
                total += n
    item['count'] = total
    results['counts'].append(item)
    return item


# ------------------------------------------------------------------- AST 保护分析
def enclosure_map(path):
    """返回 list of (func_name, start_line, end_line, has_except_http, has_reraise, has_except_broad)。"""
    with open(path, encoding='utf-8', errors='replace') as fh:
        src = fh.read()
    tree = ast.parse(src)
    out = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            seg = ast.get_source_segment(src, node) or ''
            has_http = bool(re.search(r'except\s+HTTPException', seg))
            has_reraise = ('_reraise_http' in seg) or bool(re.search(r'except\s+HTTPException\s*:\s*\n\s*raise', seg))
            has_broad = bool(re.search(r'except\s+Exception', seg))
            out.append({
                'func': node.name,
                'start': node.lineno,
                'end': getattr(node, 'end_lineno', node.lineno),
                'has_except_http': has_http,
                'has_reraise': has_reraise or has_http,
                'has_except_broad': has_broad,
            })
    return out


def enclosing(map_, line):
    best = None
    for m in map_:
        if m['start'] <= line <= m['end']:
            if best is None or (m['end'] - m['start']) < (best['end'] - best['start']):
                best = m
    return best


def scan_undefined_model_refs():
    """候选静态门禁：`X.query` 中的大写 `X` 是否在本模块可解析（P-01 那一类 NameError）。

    保守判据（宁缺勿滥）：只查 `<Name>.query` 形态且 `<Name>` 首字母大写的引用；
    可解析来源 = 模块级 import / 模块级赋值 / 函数参数 / 函数内 import / 函数内赋值 /
    局部 for-comprehension 变量 / 全仓 import 名 / 内置名。落到 else 分支的即为**候选未定义引用**。
    """
    import builtins
    known_module_names = set(dir(builtins))
    # 全仓 import 名（跨模块也算「仓内已知」，避免把 app.models 之外的名字误报）
    repo_imports = set()
    for dirpath, dirnames, filenames in os.walk(APP_DIR):
        dirnames[:] = [d for d in dirnames if d != '__pycache__']
        for name in filenames:
            if not name.endswith('.py'):
                continue
            try:
                with open(os.path.join(dirpath, name), encoding='utf-8', errors='replace') as fh:
                    tree = ast.parse(fh.read())
            except SyntaxError:
                continue
            for node in tree.body:
                if isinstance(node, ast.ImportFrom):
                    for a in node.names:
                        repo_imports.add(a.asname or a.name)
                elif isinstance(node, ast.Import):
                    for a in node.names:
                        repo_imports.add((a.asname or a.name).split('.')[0])
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    repo_imports.add(node.name)
    candidates = []
    for dirpath, dirnames, filenames in os.walk(APP_DIR):
        dirnames[:] = [d for d in dirnames if d != '__pycache__']
        for name in sorted(filenames):
            if not name.endswith('.py'):
                continue
            path = os.path.join(dirpath, name)
            with open(path, encoding='utf-8', errors='replace') as fh:
                src = fh.read()
            try:
                tree = ast.parse(src)
            except SyntaxError:
                continue
            module_level = set(known_module_names)
            for node in tree.body:
                if isinstance(node, ast.ImportFrom):
                    for a in node.names:
                        module_level.add(a.asname or a.name)
                elif isinstance(node, ast.Import):
                    for a in node.names:
                        module_level.add((a.asname or a.name).split('.')[0])
                elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    module_level.add(node.name)
                elif isinstance(node, ast.Assign):
                    for t in node.targets:
                        if isinstance(t, ast.Name):
                            module_level.add(t.id)
                elif isinstance(node, ast.Try):
                    for sub in ast.walk(node):
                        if isinstance(sub, ast.ImportFrom):
                            for a in sub.names:
                                module_level.add(a.asname or a.name)
                        elif isinstance(sub, ast.Import):
                            for a in sub.names:
                                module_level.add((a.asname or a.name).split('.')[0])
            for fn in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
                # 判据严格限定在「本模块可解析」：模块级名 + 函数自身 import/参数/赋值 + 内置名。
                # 跨模块的仓内类名**不算**可解析（否则本门禁对 P-01 失效）。
                local = set(module_level)
                for a in fn.args.args + fn.args.kwonlyargs + fn.args.posonlyargs:
                    local.add(a.arg)
                if fn.args.vararg:
                    local.add(fn.args.vararg.arg)
                if fn.args.kwarg:
                    local.add(fn.args.kwarg.arg)
                for sub in ast.walk(fn):
                    if isinstance(sub, ast.ImportFrom):
                        for a in sub.names:
                            local.add(a.asname or a.name)
                    elif isinstance(sub, ast.Import):
                        for a in sub.names:
                            local.add((a.asname or a.name).split('.')[0])
                    elif isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store):
                        local.add(sub.id)
                    elif isinstance(sub, ast.arg):
                        local.add(sub.arg)
                for sub in ast.walk(fn):
                    if isinstance(sub, ast.Attribute) and sub.attr == 'query' and isinstance(sub.value, ast.Name):
                        nm = sub.value.id
                        if nm[:1].isupper() and nm not in local:
                            candidates.append({'file': rel(path), 'line': sub.value.lineno,
                                               'func': fn.name, 'name': nm,
                                               'module_imported': nm in module_level,
                                               'text': (lines_of(path)[sub.value.lineno - 1].strip()[:160]
                                                        if sub.value.lineno - 1 < len(lines_of(path)) else '')})
    dedup = []
    seen = set()
    for c in candidates:
        k = (c['file'], c['line'], c['name'])
        if k not in seen:
            seen.add(k)
            dedup.append(c)
    return dedup


def scan_csrf_exempt():
    """AST 口径：被 `@csrf.exempt` 装饰的视图数 + 这些视图的方法级端点数（对比正则出现次数口径）。"""
    views = []
    for dirpath, dirnames, filenames in os.walk(APP_DIR):
        dirnames[:] = [d for d in dirnames if d != '__pycache__']
        for name in sorted(filenames):
            if not name.endswith('.py'):
                continue
            path = os.path.join(dirpath, name)
            with open(path, encoding='utf-8', errors='replace') as fh:
                src = fh.read()
            if 'csrf.exempt' not in src:
                continue
            try:
                tree = ast.parse(src)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.FunctionDef):
                    continue
                decs = [ast.unparse(d) for d in node.decorator_list] if hasattr(ast, 'unparse') else []
                if not any('csrf.exempt' in d for d in decs):
                    continue
                methods = []
                for d in node.decorator_list:
                    seg = ast.unparse(d)
                    if seg.startswith('bp.route') or seg.startswith('route'):
                        for m in re.findall(r"methods=\[([^\]]*)\]", seg):
                            methods += [x.strip().strip("'\"").upper() for x in m.split(',') if x.strip()]
                views.append({'file': rel(path), 'line': node.lineno, 'func': node.name,
                              'methods': methods or ['GET'],
                              'endpoint': f'{rel(path)}::{node.name}'})
    method_level = sum(len(v['methods']) for v in views)
    regex_occurrences = 0
    for dirpath, dirnames, filenames in os.walk(APP_DIR):
        for name in filenames:
            if name.endswith('.py'):
                p = os.path.join(dirpath, name)
                with open(p, encoding='utf-8', errors='replace') as fh:
                    regex_occurrences += len(re.findall(r'@csrf\.exempt', fh.read()))
    return {'view_count': len(views), 'method_level_endpoints': method_level,
            'regex_occurrences': regex_occurrences, 'views': views}


def try_region_map(path):
    """返回 {line: [region...]}，region 描述包含该行的 `try:` 体及其处理器形态（由内到外）。

    只把「`try` 的 body 语句行范围」计入区域；`except`/`else`/`finally` 不计。
    ``broad`` = 该 try 有 `except Exception`；``http`` = 该 try 有 `except HTTPException`
    （或有 `_reraise_http` 调用）。
    """
    with open(path, encoding='utf-8', errors='replace') as fh:
        src = fh.read()
    tree = ast.parse(src)
    regions = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        body_lines = []
        for st in node.body:
            body_lines.append((st.lineno, getattr(st, 'end_lineno', st.lineno)))
        if not body_lines:
            continue
        start = min(b[0] for b in body_lines)
        end = max(b[1] for b in body_lines)
        handler_srcs = []
        broad = http = reraise = False
        for h in node.handlers:
            seg = ast.get_source_segment(src, h) or ''
            handler_srcs.append(seg.split('\n', 1)[0].strip()[:80])
            if h.type is None:
                broad = True
            else:
                tname = ast.unparse(h.type) if hasattr(ast, 'unparse') else ''
                if 'HTTPException' in tname:
                    http = True
                if 'Exception' in tname:
                    broad = True
            if '_reraise_http' in seg:
                reraise = True
        regions.append({'start': start, 'end': end, 'broad': broad,
                        'http': http or reraise, 'handlers': handler_srcs})
    out = {}
    for r in regions:
        for line in range(r['start'], r['end'] + 1):
            out.setdefault(line, []).append(r)
    for line in out:
        out[line].sort(key=lambda r: (r['end'] - r['start']))
    return out


def scan_http404_swallowed():
    """精确枚举：`get_or_404` / `first_or_404` 落在「会吞异常的 try」体内。

    判据（可逐条复核）：
      1. 该调用行位于某个 `try:` 的 body 行范围内（最内层那个 try）；
      2. 该 try 的处理器里有 `except Exception`（broad）；
      3. 且该 try **没有** `except HTTPException` / `_reraise_http` 透传。
    ⇒ 该 404（HTTPException）会被吞成 500。
    """
    sites = []
    for dirpath, dirnames, filenames in os.walk(APP_DIR):
        dirnames[:] = [d for d in dirnames if d != '__pycache__']
        for name in sorted(filenames):
            if not name.endswith('.py'):
                continue
            path = os.path.join(dirpath, name)
            with open(path, encoding='utf-8', errors='replace') as fh:
                src = fh.read()
            if 'get_or_404' not in src and 'first_or_404' not in src:
                continue
            try:
                regions = try_region_map(path)
                map_ = enclosure_map(path)
            except SyntaxError as e:
                results['notes'].append(f'AST 跳过 {rel(path)}：SyntaxError {e}')
                continue
            for i, line in enumerate(src.split('\n'), start=1):
                m = re.search(r'(get_or_404|first_or_404)\s*\(', line)
                if not m:
                    continue
                enc = enclosing(map_, i)
                innermost = None
                for r in regions.get(i, []):
                    if innermost is None or (r['end'] - r['start']) < (innermost['end'] - innermost['start']):
                        innermost = r
                swallowed = bool(innermost and innermost['broad'] and not innermost['http'])
                sites.append({
                    'file': rel(path), 'line': i, 'call': m.group(1),
                    'func': enc['func'] if enc else None,
                    'in_try_body': bool(innermost),
                    'try_lines': f"{innermost['start']}-{innermost['end']}" if innermost else None,
                    'try_handlers': innermost['handlers'] if innermost else None,
                    'has_broad_except': bool(innermost and innermost['broad']),
                    'has_http_passthrough': bool(innermost and innermost['http']),
                    'swallowed_404_to_500': swallowed,
                    'text': line.strip()[:160],
                })
    return sites


def scan_get_json_without_silent():
    """全仓枚举：`get_json()` 未用 `silent=True` 的调用点（P-12/E-6a 修复面）。"""
    sites = []
    pat = re.compile(r'get_json\(\s*\)')
    for dirpath, dirnames, filenames in os.walk(APP_DIR):
        dirnames[:] = [d for d in dirnames if d != '__pycache__']
        for name in sorted(filenames):
            if not name.endswith('.py'):
                continue
            path = os.path.join(dirpath, name)
            with open(path, encoding='utf-8', errors='replace') as fh:
                src = fh.read()
            if 'get_json(' not in src:
                continue
            try:
                map_ = enclosure_map(path)
            except SyntaxError:
                map_ = []
            for i, line in enumerate(src.split('\n'), start=1):
                if pat.search(line):
                    enc = enclosing(map_, i)
                    sites.append({
                        'file': rel(path), 'line': i,
                        'func': enc['func'] if enc else None,
                        'has_http_passthrough': enc['has_reraise'] if enc else None,
                        'text': line.strip()[:160],
                    })
    return sites


def scan_bracket_subscript_in_quality():
    """P-12/E-6b：`data['x']` 下标取值（本报告只统计 `app/main/quality.py` 与 `routes.py`）。"""
    out = []
    pat = re.compile(r"\bdata\[['\"]")
    for rel_path in ('app/main/quality.py', 'app/main/routes.py'):
        path = os.path.join(REPO_ROOT, *rel_path.split('/'))
        with open(path, encoding='utf-8', errors='replace') as fh:
            for i, line in enumerate(fh.read().split('\n'), start=1):
                if pat.search(line):
                    out.append({'file': rel_path, 'line': i, 'text': line.strip()[:160]})
    return out


# ------------------------------------------------------------------ JSON 证据重算
INTEREST_KEYS = (
    'run_id', 'total', 'passed', 'failed', 'blocked', 'checks', 'probe_count',
    'violations_total', 'violations', 'severity', 'rules_total', 'duplicate_rules',
    'method_level_get', 'method_level_non_get_total', 'non_get_rules_total',
    'literal_covered', 'covered_any', 'uncovered_writable', 'smoke_ok', 'smoke_skipped',
    'csrf_enforced', 'csrf_exempt_hits', 'csrf_not_enforced', 'anon_allowed',
    'methods_probed_non_get', 'real_db_unchanged', 'exit_code_informative',
    'probe_unexpected', 'probe_only', 'pass', 'fail', 'assertions', 'expected',
    'actual', 'verdict', 'injections_all_nonzero', 'baselines_all_zero',
)


def collect_keys(obj, names, path='$', out=None, limit=40):
    if out is None:
        out = []
    if len(out) >= limit:
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f'{path}.{k}'
            if k in names and not isinstance(v, (dict, list)):
                out.append({'path': p, 'value': v})
            elif k in names and isinstance(v, list):
                out.append({'path': p, 'value': f'<list len={len(v)}>'})
            collect_keys(v, names, p, out, limit)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:8]):
            collect_keys(v, names, f'{path}[{i}]', out, limit)
    return out


def load_evidence(name):
    path = os.path.join(EVIDENCE_ROOT, *name.split('/'))
    info = {'path': rel(path), 'exists': os.path.exists(path)}
    if info['exists']:
        info['bytes'] = os.path.getsize(path)
        info['sha256'] = sha256_file(path)
        try:
            with open(path, encoding='utf-8', errors='replace') as fh:
                data = json.load(fh)
            info['keys_of_interest'] = collect_keys(data, set(INTEREST_KEYS))
        except Exception as e:
            info['parse_error'] = f'{e.__class__.__name__}: {e}'
    return info


def dir_stat(rel_dir, exclude=()):
    path = os.path.join(REPORTS_ROOT, *rel_dir.split('/'))
    files = []
    if os.path.isdir(path):
        for dirpath, dirnames, filenames in os.walk(path):
            for name in sorted(filenames):
                if name in exclude:
                    continue
                p = os.path.join(dirpath, name)
                files.append({'name': rel(p), 'bytes': os.path.getsize(p)})
    return {'dir': rel_dir, 'file_count': len(files), 'bytes_total': sum(f['bytes'] for f in files),
            'files': files}


# ------------------------------------------------------------------------ 主流程
def run_checks():
    # ---- A 类：环境与基线
    results['real_db_before'] = {
        'path': rel(REAL_DB), 'sha256': sha256_file(REAL_DB),
        'bytes': os.path.getsize(REAL_DB), 'mtime_ns': os.stat(REAL_DB).st_mtime_ns,
        'pinned': REAL_DB_SHA256_EXPECTED,
        'matches_pinned': sha256_file(REAL_DB) == REAL_DB_SHA256_EXPECTED,
    }
    for name in ('_permission_matrix.json', '_smoke_results.json'):
        p = os.path.join(REPO_ROOT, name)
        results.setdefault('repo_root_json', {})[name] = fingerprint(p) if os.path.exists(p) else {'exists': False}

    # ---- B 类：修复点源码断言（P-01…P-13）
    r = os.path.join(APP_DIR, 'main', 'routes.py')
    mes = os.path.join(APP_DIR, 'services', 'mes_service.py')
    ql = os.path.join(APP_DIR, 'main', 'quality.py')
    models = os.path.join(APP_DIR, 'models.py')

    check('P-01a', '模块级 import 行不含 Consumable（P-01 根因）', r, 6, 'Consumable', expect=False)
    check('P-01b', 'P-01 失败点使用 Consumable', r, 10943, 'Consumable', expect=True)
    check('P-01c', '同文件函数内导入先例 1', r, 10555, 'Consumable', expect=True)
    check('P-01d', '同文件函数内导入先例 2', r, 10683, 'Consumable', expect=True)
    check('P-01e', '同文件函数内导入先例 3', r, 10786, 'Consumable', expect=True)

    check('P-02a', '门禁调用点实参不含 production_record', mes, 326, 'production_record', expect=False)
    check('P-02b', '门禁调用点实参形态（batch_item + workpieces）', mes, 326,
          'qc_gate_allows_output(batch_item=item', expect=True)
    check('P-02c', 'M-1 早返回分支', mes, 421, 'if workpiece is None', expect=True)
    check('P-02d', 'M-1 早返回', mes, 422, 'return', expect=True)
    check('P-02e', 'apply_inspection_result 分派：workpiece', mes, 409, "task.target_type == 'workpiece'", expect=True)
    check('P-02f', 'apply_inspection_result 分派：heat_lot', mes, 411, "task.target_type == 'heat_lot'", expect=True)
    check('P-02g', 'apply_inspection_result 分派：goods_receipt', mes, 416, "task.target_type == 'goods_receipt'", expect=True)
    check('P-02h', 'NC 唯一业务构造点只在 fail 分支（workpiece 路径）', mes, 454, 'NonconformityRecord(', expect=True)

    check('P-03a', 'quality_status 唯一写入点（人工 PUT）', r, 8899, 'item.quality_status = data', expect=True)

    check('P-04a', '开关定义处（models.py）', models, 2603, 'quality.rework_counts_piecework', expect=True)
    check('P-04b', '计件公式（未读开关、未过滤返工）', r, 1815, 'piecework = sum(', expect=True)
    check('P-04c', '计件公式上下 8 行内无 rework 字样', r, 1815, 'rework', expect=False, window=8)

    check('P-05a', '返工任务件数硬编码 quantity=1', mes, 708, 'quantity=1', expect=True)
    check('P-06a', '报废扣料硬编码 -1', mes, 732, 'max(0, mat.quantity - 1)', expect=True)
    check('P-06b', '报废库入库数量硬编码（inbound_workpiece）', mes, 225, 'quantity=1', expect=True)
    check('P-07a', '门禁把 pending 归入拒绝（死锁根因）', mes, 172,
          "('pending', 'pending_inspection')", expect=True)
    check('P-07b', '门禁拒绝原因可读', mes, 173, '质检未出结果', expect=True)

    check('P-08a', 'edit 端点赋值段（quantity 行）', r, 4506, "task.quantity = data.get('quantity')", expect=True)
    check('P-08b', 'edit 端点整段无 task.notes 赋值（4502-4536）', r, 4519, 'task.notes =', expect=False, window=17)
    check('P-08c', '审计 new_data 把 notes 当新值', r, 4532, "'notes': task.notes", expect=True)
    check('P-10a', '删任务未清关联记录', ql, 1024, 'db.session.delete(task)', expect=True)
    check('P-12a', '部分更新用下标取值（templates）', ql, 408, "data['template_code']", expect=True)
    check('P-12b', '下标取值（tasks type）', ql, 588, "data['type']", expect=True)
    check('P-11a', '错误响应拼接底层异常（quality）', ql, 1034, 'str(e)', expect=True)
    check('P-11b', '错误响应拼接底层异常（routes 4446）', r, 4446, 'str(e)', expect=True)
    check('P-11c', '同仓正确写法先例 _reraise_http', r, 8148, '_reraise_http(e)', expect=True)

    # ---- C 类：脚手架与工具链缺陷（T-01…T-10）
    h = os.path.join(REPORTS_ROOT, 'harness')
    check('T-02a', 'run_gates 退出码只看 fail', os.path.join(h, 'run_gates.py'), 435,
          'return 0', expect=True)
    check('T-02b', 'run_gates 退出码行不含 probe_unexpected', os.path.join(h, 'run_gates.py'), 435,
          'probe_unexpected', expect=False)
    check('T-02c', 'probe_unexpected 在汇总处出现', os.path.join(h, 'run_gates.py'), 367,
          'probe_unexpected', expect=True)
    check('T-03a', '敏感性自检用 isinstance(exit_code, int) 过滤', os.path.join(h, 'run_gates.py'), 391,
          'isinstance', expect=True, window=3)
    check('T-01a', '证据落盘函数固定写 EVIDENCE_DIR', os.path.join(h, '_env.py'), 27,
          'EVIDENCE_DIR', expect=True)
    check('T-01b', 'save_evidence 未参数化 run_id 子目录', os.path.join(h, '_env.py'), 207,
          'save_evidence', expect=True)
    check('T-04a', '夹具料账固定 internal_number（非幂等）', os.path.join(h, 'fixtures.py'), 179,
          'internal_number', expect=True)

    check('T-06a', 'permission_matrix 恒 return 0（伪门禁）',
          os.path.join(SCRIPTS_DIR, 'permission_matrix.py'), 132, 'return 0', expect=True)
    check('T-06b', 'route_inventory 恒 return 0（报告型）',
          os.path.join(SCRIPTS_DIR, 'route_inventory.py'), 38, 'return 0', expect=True)
    check('T-09a', 'measure_coverage 恒 return 0（报告型）',
          os.path.join(h, 'measure_coverage.py'), 485, 'return 0', expect=True)
    check('T-07a', 'smoke_test 无条件写仓库根 JSON',
          os.path.join(SCRIPTS_DIR, 'smoke_test.py'), 186, '_smoke_results.json', expect=True)
    check('T-07b', 'permission_matrix 无条件写仓库根 JSON',
          os.path.join(SCRIPTS_DIR, 'permission_matrix.py'), 129, '_permission_matrix.json', expect=True)
    check('BL-2', '测试 bootstrap 恒关 CSRF',
          os.path.join(SCRIPTS_DIR, '_test_bootstrap.py'), 36, 'WTF_CSRF_ENABLED', expect=True)
    check('BL-7', 'check_properties 只认「类名.属性名」口径',
          os.path.join(SCRIPTS_DIR, 'check_properties.py'), 33, '类名', expect=True)

    # ---- D 类：CI / 工具链现状（本报告新增可复算项）
    jenkins = os.path.join(REPO_ROOT, 'Jenkinsfile')
    for gate in ('check_templates', 'check_properties', 'check_migration_heads',
                 'check_db_bootstrap', 'route_inventory', 'negative_matrix',
                 'functional_test', 'smoke_test', 'pytest'):
        c = count_in_file(jenkins, re.escape(gate), f'Jenkinsfile 是否调用 {gate}')
        c['expect'] = 0
    count_in_file(jenkins, r'py_compile', 'Jenkinsfile 实际质检动作（py_compile）')
    wf = os.path.join(REPO_ROOT, '.github', 'workflows', 'docker-deploy.yml')
    count_in_file(wf, r'(?m)^\s*-\s*(run|uses):', 'GitHub workflow 步骤数')
    count_in_file(wf, r'pytest|python|check_', 'GitHub workflow 测试动作')

    tests_dir = os.path.join(REPO_ROOT, 'tests')
    results['tests_dir'] = {'exists': os.path.isdir(tests_dir)}
    if os.path.isdir(tests_dir):
        py = [f for f in os.listdir(tests_dir) if f.endswith('.py')]
        results['tests_dir'].update({'py_files': len(py), 'files': sorted(os.listdir(tests_dir))})

    req = os.path.join(REPO_ROOT, 'requirements.txt')
    results['requirements'] = fingerprint(req)
    count_in_file(req, r'(?im)^\s*pytest', 'requirements.txt 是否声明 pytest')
    count_in_file(req, r'(?m)^\s*[A-Za-z0-9_.\-]+\s*$', 'requirements.txt 无版本约束行数')
    count_in_file(req, r'==', 'requirements.txt 精确钉版本（==）行数')
    count_in_file(req, r'(?m)^\s*[A-Za-z0-9_.\-]+\s*[><]=', 'requirements.txt 区间约束（>=）行数')

    # ---- E 类：全仓枚举（P-09 / P-12 修复面）
    sites = scan_http404_swallowed()
    results['http404_swallowed'] = {
        'scanned_sites': len(sites),
        'swallowed_count': sum(1 for s in sites if s['swallowed_404_to_500']),
        'swallowed': [s for s in sites if s['swallowed_404_to_500']],
        'protected_count': sum(1 for s in sites if s['in_try_body'] and not s['swallowed_404_to_500']),
        'not_in_try_count': sum(1 for s in sites if not s['in_try_body']),
    }
    results['http404_by_file'] = {}
    for s in results['http404_swallowed']['swallowed']:
        results['http404_by_file'][s['file']] = results['http404_by_file'].get(s['file'], 0) + 1
    gj = scan_get_json_without_silent()
    results['get_json_without_silent'] = {'count': len(gj), 'sites': gj}
    results['data_bracket_subscript'] = scan_bracket_subscript_in_quality()
    results['csrf_exempt'] = scan_csrf_exempt()
    results['undefined_model_refs'] = scan_undefined_model_refs()

    count_in_tree(APP_DIR, r'AuditLog\(', 'AuditLog( 构造点（app/**.py）')
    count_in_tree(APP_DIR, r'Notification\(', 'Notification( 构造点（app/**.py）')
    count_in_tree(APP_DIR, r'\.rollback\(\)', 'rollback() 调用点（app/**.py）')
    gnn = count_in_tree(APP_DIR, r'get_next_number\(', 'get_next_number( 出现次数（app/**.py，含 def 行）')
    results['notes'].append(
        f'get_next_number 出现 {gnn["count"]} 次（含 `def get_next_number(` 定义 1 处）；'
        f'与 t3 记的「93 处调用」相差的正是定义行 ⇒ 调用 93 处')
    count_in_tree(APP_DIR, r'@csrf\.exempt', '@csrf.exempt 正则出现次数（app/**.py）')
    count_in_tree(APP_DIR, r'current_user\.role', '内联 current_user.role（app/**.py）')
    count_in_tree(APP_DIR, r'_reraise_http\(', '_reraise_http( 正确先例（app/**.py）')
    count_in_tree(APP_DIR, r'except HTTPException', 'except HTTPException（app/**.py）')
    count_in_tree(APP_DIR, r'get_json\(silent=True\)', 'get_json(silent=True) 正确先例（app/**.py）')
    tpl_dir = os.path.join(APP_DIR, 'templates')
    item = {'label': '内联 current_user.role（模板 *.html）', 'root': 'app/templates'}
    total, per = 0, {}
    for dirpath, dirnames, filenames in os.walk(tpl_dir):
        for name in filenames:
            if not name.endswith('.html'):
                continue
            p = os.path.join(dirpath, name)
            with open(p, encoding='utf-8', errors='replace') as fh:
                n = len(re.findall(r'current_user\.role', fh.read()))
            if n:
                per[rel(p)] = n
                total += n
    item.update({'count': total, 'per_file': per})
    results['counts'].append(item)

    # ---- F 类：既有证据重算（只读 JSON，不重跑脚本）
    for name in ('harness/gates.json', 'harness/negative_matrix.json', 'harness/coverage.json',
                 'api/api_matrix.json', 'api/write_suite.json', 'api/verify_t4.json',
                 'uat/uat_chains.json', 'analysis/assertion_ledger.json',
                 'analysis/coverage_verdict.json', 'analysis/real_db_recount.json',
                 'analysis/source_assertions.json'):
        results['recount'][name] = load_evidence(name)

    results['evidence_dirs'] = {
        'harness': dir_stat('evidence/harness'),
        'api': dir_stat('evidence/api'),
        'uat': dir_stat('evidence/uat'),
        'analysis': dir_stat('evidence/analysis'),
        'improve': dir_stat('evidence/improve'),
    }
    results['artifact_hash_index_existence'] = {
        'evidence/harness/artifact_hashes.json': os.path.exists(
            os.path.join(EVIDENCE_ROOT, 'harness', 'artifact_hashes.json')),
        'evidence/uat/artifact_hashes.json': os.path.exists(
            os.path.join(EVIDENCE_ROOT, 'uat', 'artifact_hashes.json')),
        'evidence/analysis/artifact_hashes.json': os.path.exists(
            os.path.join(EVIDENCE_ROOT, 'analysis', 'artifact_hashes.json')),
    }
    # 回归基线锚点（t5 的 40 条判据账本）
    baseline = os.path.join(EVIDENCE_ROOT, 'uat', 'uat_chains.json')
    results['uat_regression_baseline'] = fingerprint(baseline) if os.path.exists(baseline) else {'exists': False}

    # 派生量（**显式读 coverage.json.summary**，不用泛化 key 搜索，避免误取布尔标记）
    try:
        with open(os.path.join(EVIDENCE_ROOT, 'harness', 'coverage.json'), encoding='utf-8') as fh:
            covdoc = json.load(fh)
        s = covdoc.get('summary', {})
        uw = covdoc.get('uncovered_writable') or []
        non_get = s.get('method_level_non_get_total')
        any_cov = s.get('writable_any_covered_by_all')
        lit_cov = s.get('writable_literal_covered_by_functional')
        rules = s.get('writable_rules_non_get')
        results['derived'] = {
            'source': 'evidence/harness/coverage.json（run_id=%s）' % covdoc.get('run_id'),
            'non_get_method_level': non_get,
            'covered_any': any_cov,
            'literal_covered': lit_cov,
            'no_hit_method_level_ge': (non_get - any_cov) if (non_get and any_cov) else None,
            'non_get_rules': rules,
            'uncovered_writable_rules_len': len(uw),
            'literal_subset_of_any': (lit_cov or 0) <= (any_cov or 0),
        }
    except Exception as e:
        results['derived'] = {'error': f'{e.__class__.__name__}: {e}'}

    results['real_db_after'] = {
        'sha256': sha256_file(REAL_DB),
        'bytes': os.path.getsize(REAL_DB),
        'matches_pinned': sha256_file(REAL_DB) == REAL_DB_SHA256_EXPECTED,
        'unchanged': True,
    }


def do_finalize(tee):
    """--finalize：把 t7 全部制品与回归基线锚点写入 artifact_hashes.json（不含自身）。"""
    entries = []
    for t in HASH_TARGETS:
        fp = os.path.join(REPORTS_ROOT, *t.split('/'))
        entries.append(fingerprint(fp))
    baseline = os.path.join(EVIDENCE_ROOT, 'uat', 'uat_chains.json')
    baseline_fp = fingerprint(baseline)
    doc = {
        'run_id': RUN_ID,
        'generated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'producer': 't7 测试流程优化工程师 / harness/improve_plan.py --finalize',
        'scope': 't7 交付物与证据的防篡改基线（t8 可逐项复算）',
        'self_excluded': '本文件 artifact_hashes.json 自身不列入（写入自身哈希会自相矛盾）',
        'artifacts': entries,
        'uat_regression_baseline': baseline_fp,
        't8_instructions': [
            '对上述每个 path 复算 bytes / splitlines() 行数 / SHA256，与本节逐项比对',
            '回归门禁：修复后重跑 uat_chains 时必须换 UAT_RUN_ID，并与 uat_regression_baseline 逐条 diff',
            '若某文件 bytes 与本节不符，先查是否为 append-only 追加段（A-29 规则），再判是否被改写',
        ],
    }
    out, renamed = guard_write(os.path.join(EVID_DIR, 'artifact_hashes.json'))
    ensure_dir(EVID_DIR)
    with open(out, 'w', encoding='utf-8', newline='\n') as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
    tee.write(f'[finalize] 写入 {rel(out)}（改名={renamed}），制品 {len(entries)} 项')
    for e in entries:
        tee.write(f'  - {e["path"]}: {e.get("bytes")} B / {e.get("total_lines")} 行 / {str(e.get("sha256"))[:16]}…')
    tee.write(f'  - 回归基线 {baseline_fp.get("path")}: {baseline_fp.get("sha256")}')
    return out


def main():
    # A-14 编码铁律：父进程 stdout 也必须强制 UTF-8，否则中文/符号会以 GBK 抛 UnicodeEncodeError
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    argv = sys.argv[1:]
    finalize = '--finalize' in argv
    out_dir = None
    if '--out-dir' in argv:
        out_dir = argv[argv.index('--out-dir') + 1]
    global EVID_DIR
    if out_dir:
        EVID_DIR = os.path.abspath(out_dir)
    ensure_dir(EVID_DIR)

    tee = Tee(None)
    tee_path, tee_renamed = guard_write(os.path.join(EVID_DIR, 'improve_plan.out.txt'))
    tee.close()
    tee = Tee(tee_path)

    started = time.time()
    tee.write('=' * 78)
    tee.write(f'[t7] improve_plan.py  只读重算器   run_id={RUN_ID}')
    tee.write(f'[t7] 解释器 {sys.executable}')
    tee.write(f'[t7] 仓库根 {REPO_ROOT}')
    tee.write(f'[t7] 控制台原文 {rel(tee_path)}（改名={tee_renamed}）')
    tee.write('=' * 78)

    out_json = None
    if not finalize:
        run_checks()
        # 断言汇总
        checks = results['checks']
        failed = [c for c in checks if not c['ok']]
        tee.write(f'[源码断言] 共 {len(checks)} 条：passed={len(checks) - len(failed)} failed={len(failed)}')
        for c in failed:
            tee.write(f'  ✗ {c["id"]} {c["desc"]}: 期望第 {c["line_requested"]} 行'
                      f'（±{c["window"]}）{"含" if c["expect_present"] else "不含"} {c["needle"]!r}；'
                      f'{c.get("reason") or ""}')
        tee.write('')
        tee.write('[全仓枚举] get_or_404 / first_or_404 落在「会吞 404 的 try」内（P-09 修复面）：'
                  f'swallowed={results["http404_swallowed"]["swallowed_count"]} / '
                  f'扫描到调用点 {results["http404_swallowed"]["scanned_sites"]} / '
                  f'已保护 {results["http404_swallowed"]["protected_count"]} / '
                  f'不在 try 内 {results["http404_swallowed"]["not_in_try_count"]}')
        tee.write('  按文件：' + json.dumps(results['http404_by_file'], ensure_ascii=False))
        for s in results['http404_swallowed']['swallowed']:
            tee.write(f'  - {s["file"]}:{s["line"]}  def {s["func"]}()  try@ {s["try_lines"]} '
                      f'handlers={s["try_handlers"]}')
        tee.write(f'[全仓枚举] get_json() 无 silent 调用点：{results["get_json_without_silent"]["count"]}')
        tee.write(f'[全仓枚举] @csrf.exempt：视图 {results["csrf_exempt"]["view_count"]} 个 / '
                  f'方法级端点 {results["csrf_exempt"]["method_level_endpoints"]} / '
                  f'正则出现 {results["csrf_exempt"]["regex_occurrences"]} 次')
        tee.write(f'[全仓枚举] quality.py+routes.py 的 data[\'x\'] 下标取值：'
                  f'{len(results["data_bracket_subscript"])} 处')
        tee.write(f'[全仓枚举] `<Name>.query` 且 Name 在本模块不可解析（P-01 同类，候选新门禁）：'
                  f'{len(results["undefined_model_refs"])} 处')
        for s in results['undefined_model_refs']:
            tee.write(f'  - {s["file"]}:{s["line"]}  def {s["func"]}()  {s["name"]}  |  {s["text"][:80]}')
        tee.write('')
        tee.write('[计数]')
        for c in results['counts']:
            tee.write(f'  - {c["label"]}: {c["count"]}')
        tee.write('')
        tee.write('[证据重算]')
        for name, info in results['recount'].items():
            tee.write(f'  - {name}: exists={info["exists"]}'
                      f'{" bytes=" + str(info.get("bytes")) + " sha=" + str(info.get("sha256"))[:16] if info["exists"] else ""}')
        tee.write('')
        tee.write('[证据目录] ' + '; '.join(
            f'{k}={v["file_count"]} 文件/{v["bytes_total"]} B'
            for k, v in results['evidence_dirs'].items()))
        tee.write('[哈希索引存在性] ' + json.dumps(
            results['artifact_hash_index_existence'], ensure_ascii=False))
        tee.write('')
        tee.write('[真实库] 开工 ' + results['real_db_before']['sha256'][:16] + '…  '
                  + ('MATCH 钉死值' if results['real_db_before']['matches_pinned'] else '偏离钉死值 ⚠'))
        tee.write('[真实库] 收尾 ' + results['real_db_after']['sha256'][:16] + '…  '
                  + ('MATCH 钉死值' if results['real_db_after']['matches_pinned'] else '偏离钉死值 ⚠')
                  + f'（本次耗时 {time.time() - started:.1f}s）')

        results['run_id'] = RUN_ID
        results['generated_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
        results['interpreter'] = sys.executable
        results['totals'] = {
            'source_assertions': len(checks),
            'source_assertions_failed': len(failed),
            'http404_swallowed_sites': results['http404_swallowed']['swallowed_count'],
            'get_json_without_silent_sites': results['get_json_without_silent']['count'],
            'evidence_scripts_rerun': 0,
            'evidence_scripts_rerun_note': 'A-40：本脚本只读既有 JSON，未重跑任何会产生证据的脚本',
        }
        out_json, renamed = guard_write(os.path.join(EVID_DIR, 'improve_plan.json'))
        with open(out_json, 'w', encoding='utf-8', newline='\n') as fh:
            json.dump(results, fh, ensure_ascii=False, indent=2)
        tee.write(f'[产出] {rel(out_json)}（改名={renamed}）')
        tee.write(f'[RESULT] {"OK" if not failed and results["real_db_after"]["matches_pinned"] else "FAIL"}')
        rc = 0 if (not failed and results['real_db_after']['matches_pinned']) else 1
    else:
        do_finalize(tee)
        rc = 0

    tee.close()
    return rc


if __name__ == '__main__':
    sys.exit(main())
