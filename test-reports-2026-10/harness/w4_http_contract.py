"""w4_http_contract.py — P-09-c 的机读判据：统计「会吞成静默出口的 HTTP 站点」。

口径（与 `17-W4W5修复验收判据.md` §2.4 `P-09-c` / `07` §5 G-09 对齐）：
一个**源站点** = 某个 `try` 块体内**直接**出现下列之一，而其 `except Exception`（或 `except` 裸捕）
处理器**没有**在任何位置调用 `_reraise_http(...)` / `raise`：

* `.get_or_404(` / `.first_or_404(`  —— HTTPException(404) 会被吞成 500/200（P-09）；
* `request.get_json()`（未加 `silent=True`）—— HTTPException(415/400) 会被吞成 500（P-12）。

输出：站点清单（file:line:函数名:模式）+ 计数；`--json` 给机读；`--expect N` 断言计数；
`--selftest` 用受控合成源码做阳性/阴性对照（证明判据不是恒真）。

退出码：0 = 计数符合 `--expect`（缺省 0）；1 = 不符合；2 = 参数错误。
用法：
    python -B test-reports-2026-10/harness/w4_http_contract.py --roots app/main
    python -B test-reports-2026-10/harness/w4_http_contract.py --expect 17   # 修前基线
"""
import argparse
import ast
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
DEFAULT_ROOTS = ['app']
HTTP_CALLS = ('get_or_404', 'first_or_404')
RE_RAISE = ('_reraise_http',)

#: `17-W4W5修复验收判据.md` §2.3 的**站点口径**（P-09-c 的「当前 17」= 这 17 处源站点所在函数）。
#: 判定只统计这些函数里的站点 ⇒ 与文档口径可逐条对齐；其余模块的同类模式属 §9 第 4 项（阶段 B）。
DOC_SCOPE = {
    'app/main/quality.py': ('create_template', 'manage_template', 'start_inspection',
                            'submit_inspection_record', 'delete_inspection_task', 'update_task',
                            'get_inspection_record_detail', 'print_inspection_record'),
    'app/main/production_center.py': ('api_create_instances', 'api_save_tech_decomposition',
                                      'api_item_detail', 'api_execute_operation'),
    'app/main/routes.py': ('get_product_bom_item', 'update_product_bom_item',
                           'delete_product_bom_item', 'delete_product_process',
                           'update_product_process', 'get_product_process'),
}


class SiteVisitor(ast.NodeVisitor):
    def __init__(self, path, lines):
        self.path = path
        self.lines = lines
        self.sites = []
        self.func = '<module>'

    # --- 逐函数记录当前函数名
    def visit_FunctionDef(self, node):
        prev = self.func
        self.func = node.name
        self.generic_visit(node)
        self.func = prev

    visit_AsyncFunctionDef = visit_FunctionDef

    def _patterns(self, node):
        found = set()
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                fn = sub.func
                if isinstance(fn, ast.Attribute):
                    if fn.attr in HTTP_CALLS:
                        found.add(fn.attr)
                    if fn.attr == 'get_json':
                        kw = {k.arg for k in sub.keywords}
                        if 'silent' not in kw:
                            found.add('get_json()')
        return found

    @staticmethod
    def _handler_reraises(handler):
        """处理器是否重抛（调用 _reraise_http 或 raise）。"""
        for sub in ast.walk(handler):
            if isinstance(sub, ast.Raise):
                return True
            if isinstance(sub, ast.Call):
                fn = sub.func
                name = fn.id if isinstance(fn, ast.Name) else getattr(fn, 'attr', '')
                if name in RE_RAISE:
                    return True
        return False

    def visit_Try(self, node):
        found = self._patterns(node)
        if found:
            # 只有「会捕获 HTTPException 的处理器**全部**不重抛」才算吞掉：
            # `except HTTPException: raise` 这类正确写法必须判为**非**站点。
            catchers = []
            for h in node.handlers:
                if h.type is None:
                    catchers.append(h)
                    continue
                tnode = h.type
                names = []
                if isinstance(tnode, ast.Name):
                    names = [tnode.id]
                elif isinstance(tnode, ast.Tuple):
                    names = [e.id for e in tnode.elts if isinstance(e, ast.Name)]
                elif isinstance(tnode, ast.Attribute):
                    names = [tnode.attr]
                if set(names) & {'Exception', 'BaseException', 'HTTPException', 'HTTPError'}:
                    catchers.append(h)
            swallowing = [h for h in catchers if not self._handler_reraises(h)]
            if catchers and len(swallowing) == len(catchers):
                self.sites.append({
                    'file': self.path, 'line': node.lineno, 'func': self.func,
                    'patterns': sorted(found),
                    'handler_lines': [h.lineno for h in swallowing],
                    'snippet': (self.lines[node.lineno - 1] or '').strip()[:100],
                })
        self.generic_visit(node)


def scan(roots, scope=None):
    """scope='doc' ⇒ 只统计 `DOC_SCOPE` 里的函数（P-09-c 的 17 处口径）；否则全量。"""
    sites = []
    seen = set()
    for root in roots:
        base = os.path.join(REPO_ROOT, root)
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in ('__pycache__', 'templates', 'static')]
            for fn in sorted(filenames):
                if not fn.endswith('.py'):
                    continue
                path = os.path.join(dirpath, fn)
                rel = os.path.relpath(path, REPO_ROOT).replace('\\', '/')
                if rel in seen:
                    continue
                seen.add(rel)
                try:
                    src = open(path, encoding='utf-8').read()
                    tree = ast.parse(src)
                except SyntaxError:
                    continue
                v = SiteVisitor(rel, src.splitlines())
                v.visit(tree)
                found = v.sites
                if scope == 'doc':
                    allowed = DOC_SCOPE.get(rel, ())
                    found = [s for s in found if s['func'] in allowed]
                sites.extend(found)
    return sites


SELFTEST_GOOD = '''
def ok():
    try:
        row = M.query.get_or_404(1)
    except Exception as e:
        db.session.rollback()
        _reraise_http(e)
        return jsonify({'message': 'x'}), 500
'''

SELFTEST_GOOD2 = '''
def ok2():
    try:
        row = M.query.first_or_404()
    except HTTPException:
        raise
    except Exception as e:
        return jsonify({'message': 'x'}), 500
'''

SELFTEST_BAD1 = '''
def bad1():
    try:
        row = M.query.get_or_404(1)
    except Exception as e:
        return jsonify({'message': str(e)}), 500
'''

SELFTEST_BAD2 = '''
def bad2():
    try:
        data = request.get_json()
    except Exception as e:
        return jsonify({'message': str(e)}), 500
'''

SELFTEST_BAD3 = '''
def bad3():
    try:
        row = M.query.first_or_404()
    except:
        return jsonify({'message': 'x'}), 200
'''


def selftest():
    cases = [('WT-P1 有 _reraise_http ⇒ 不算站点', SELFTEST_GOOD, 0),
             ('WT-P2 独立 except HTTPException: raise ⇒ 不算站点', SELFTEST_GOOD2, 0),
             ('WT-N1 get_or_404 被裸捕 ⇒ 算站点', SELFTEST_BAD1, 1),
             ('WT-N2 get_json() 被裸捕 ⇒ 算站点', SELFTEST_BAD2, 1),
             ('WT-N3 first_or_404 + 裸 except ⇒ 算站点', SELFTEST_BAD3, 1)]
    ok_all = True
    n_ok = 0
    for name, src, expect in cases:
        v = SiteVisitor('<selftest>', src.splitlines())
        v.visit(ast.parse(src))
        got = len(v.sites)
        ok = got == expect
        ok_all = ok_all and ok
        n_ok += 1 if ok else 0
        print('  [%s] %s（期望 %d，实测 %d）%s' % ('PASS' if ok else 'FAIL', name, expect, got,
                                                 '' if ok else '  <- 判据不敏感/误报'))
    # 统计行必须复用上面的循环结果。历史实现另起一个 `len(SiteVisitor(...).sites)` 表达式且
    # **漏调 visit()** ⇒ sites 恒空 ⇒ 恒报 2/5（与判据是否敏感无关）。见 t5/t8 的取证。
    print('[w4_http_contract] 自检 %d/%d 通过' % (n_ok, len(cases)))
    return 0 if ok_all else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--roots', nargs='*', default=DEFAULT_ROOTS)
    ap.add_argument('--expect', type=int, default=0)
    ap.add_argument('--scope', default='doc', choices=('doc', 'app'),
                    help='doc = 17 处站点口径（P-09-c）；app = 全量（信息项，§9 第 4 项）')
    ap.add_argument('--json', default=None)
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors='replace')
        except Exception:
            pass
    if args.selftest:
        return selftest()
    sites = scan(args.roots, scope=None if args.scope == 'app' else 'doc')
    print('[w4_http_contract] 扫描根 = %s  口径 = %s' % (', '.join(args.roots), args.scope))
    for st in sites:
        print('  [SITE] %s:%d %s()  patterns=%s  处理器行=%s'
              % (st['file'], st['line'], st['func'], st['patterns'], st['handler_lines']))
    print('[w4_http_contract] 会吞成静默出口的站点 = %d（期望 %d）' % (len(sites), args.expect))
    code = 0 if len(sites) == args.expect else 1
    print('[w4_http_contract] exit_code_semantics=' + json.dumps({
        'rule': 'sites == --expect -> exit 0 else 1', 'sites': len(sites),
        'expected': args.expect, 'code': code}, ensure_ascii=False))
    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
        with open(args.json, 'w', encoding='utf-8', newline='\n') as fh:
            json.dump({'sites': sites, 'count': len(sites), 'expected': args.expect,
                       'code': code}, fh, ensure_ascii=False, indent=1)
    return code


if __name__ == '__main__':
    sys.exit(main())
