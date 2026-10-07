"""「本模块不可解析的 `<Name>.query`」长期闸门（只读静态检查，不导入应用、不连数据库）。

## 为什么存在（P-01，blocker）
`app/main/routes.py` 的 `delete_consumable`（`:10887`）与 `use_consumable`（`:10939`）直接调用
`Consumable.query.get_or_404(id)`，而该模块的**模块级导入不含** `Consumable`、两个函数也**没有**
函数内导入 ⇒ 任何请求都 `NameError: name 'Consumable' is not defined`，又被 `except Exception`
兜成 500：**两个易耗品写端点恒不可用**（`POST /consumables/<id>/use`、`DELETE /consumables/<id>`；
t4 实测 W-INV-7：库存 10→10 未扣、正文为 NameError）。全仓另有 ≥10 处**函数内**导入
`Consumable` 的先例，所以同一文件里只有这两个函数坏掉，肉眼与常规测试都不易发现。

`check_properties.py` 只认 `类名.属性名`（属性存不存在），**看不见「名字本身不存在」**这一类 ⇒
需要本闸门把「P-01 类 NameError」变成可自动发现（`07` §2.4 / `08` §5.2 G-08 / TL-01）。

## 检查什么
用 `ast` 静态分析，**不导入应用、不连数据库**：只认 `<Name>.query` 形态、且 `<Name>` 首字母大写。

对每个函数，把下列来源合并成「本函数可解析的名字集」：

1. 内置名（`dir(builtins)`）；
2. **模块级**绑定：`import` / `from ... import ...`（含模块级 `try:` 块内的 import）、模块级赋值、
   模块级 `def` / `class` 名；
3. 函数形参（含 `*args` / `**kwargs` / 仅关键字参数）；
4. **函数体内**的绑定：`import` / `from ... import ...`、赋值（含 `for` 目标、`with ... as`、
   推导式目标、walrus）、`except ... as <name>`、嵌套 `def` / `class` 名、嵌套函数形参。

`<Name>` 首字母大写且不在该集合内 ⇒ 违规。
`M.Consumable.query`（`import app.models as M`）是**属性链**，不是 Name 引用，不在判据内。

## 为什么判据限定「本模块」，而不是全仓
跨模块的仓内类名**不算**可解析。若按全仓放行，把某模块的 import 删掉也不会报红 —— 那本闸门对
P-01 就完全失效（P-01 的根因正是「本模块没有这个绑定」）。

## 用法
    python -B scripts/check_model_refs.py                 # 扫 app/
    python -B scripts/check_model_refs.py --root <dir>    # 扫指定目录（注入/对照用）
    python -B scripts/check_model_refs.py --verbose       # 额外打印扫描统计
    python -B scripts/check_model_refs.py --json          # stdout 末尾追加一行机读 JSON
    python -B scripts/check_model_refs.py --selftest      # 合成用例：2 阳性 + 11 阴性（不落盘）

退出码：无违规 0；有违规 1；环境错误（目录不存在）2。

**输出编码（A-14/A-60）**：控制台行一律 **ASCII 安全**（本机 stdout 可能是 GBK），
中文只出现在本 docstring 与机读 JSON 的转义串里。

## 边界（有意为之，宁缺勿滥）
- 只认 `<Name>.query`。`db.session.query(...)`、`Model.query`（Model 已绑定）、`self.x.query`
  都不在判据内；类体中（而非函数中）的 `<Name>.query` 也不查。
- **不做数据流/闭包分析**：一律保守取宽（宁可漏报，不误报）。因此嵌套 `def`/`class` 名、
  `except ... as` 别名等**只要同名被绑定过**就放行。
- 无法 `ast.parse` 的文件**计为违规**（不是静默跳过）：`app/` 下的源码必须可解析，
  解析失败本身就是必须修的问题。
- 备份文件（`*.bak` / `*.new` / `*.backup` / `*.pyc`）与 `__pycache__` 跳过；`SKIP_FILENAMES`
  里的 4 个名字是 `check_properties.py` 同款**防御性**保留（这些遗留副本已于 2026-09-18 删除，
  名字留作防御：若被误恢复，跳过比让脚本崩在 `ast.parse` 更好）。
"""
import argparse
import ast
import builtins
import json
import os
import sys

# 备份文件 / 生成物：不参与检查（与 check_properties.py 同口径）
SKIP_FILENAMES = {
    'routes_backup.py', 'routes_original.py', 'routes_full.py', 'routes_with_duplicates.py',
}
SKIP_SUFFIXES = ('.bak', '.new', '.backup', '.pyc')

QUERY_ATTR = 'query'


def _reconfigure_stdout():
    """A-14/A-60：GBK 控制台下 print 不得崩溃（输出行本身已 ASCII 安全）。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError, OSError):
            pass


def _is_skip_file(name):
    return name in SKIP_FILENAMES or name.endswith(SKIP_SUFFIXES)


def _import_names(node, into):
    """`import a.b` / `from x import y as z` 绑定的名字（与运行时一致：import 取顶层名）。"""
    if isinstance(node, ast.ImportFrom):
        for alias in node.names:
            into.add(alias.asname or alias.name)
    elif isinstance(node, ast.Import):
        for alias in node.names:
            into.add((alias.asname or alias.name).split('.')[0])


def _assign_target_names(target, into):
    for sub in ast.walk(target):
        if isinstance(sub, ast.Name):
            into.add(sub.id)


def _module_stmt_names(node, into):
    """模块级语句引入的绑定（判据 2）。"""
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        _import_names(node, into)
    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        into.add(node.name)
    elif isinstance(node, ast.Assign):
        for target in node.targets:
            _assign_target_names(target, into)
    elif isinstance(node, ast.AnnAssign):
        _assign_target_names(node.target, into)
    elif isinstance(node, ast.Try):
        # 模块级 try/except ImportError 兜底导入（本项目 models 导入即为这种形态）
        for sub in ast.walk(node):
            if isinstance(sub, (ast.Import, ast.ImportFrom)):
                _import_names(sub, into)
            elif isinstance(sub, ast.Assign):
                for target in sub.targets:
                    _assign_target_names(target, into)
            elif isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                into.add(sub.name)


def module_level_names(tree):
    """模块级可解析名字集 = 内置名 + 模块级绑定。"""
    names = set(dir(builtins))
    for node in tree.body:
        _module_stmt_names(node, names)
    return names


def function_local_names(fn, module_names):
    """该函数内可解析名字集 = 模块级名 + 形参 + 函数体内绑定。"""
    local = set(module_names)
    args = fn.args
    for arg in list(args.args) + list(args.kwonlyargs) + list(getattr(args, 'posonlyargs', [])):
        local.add(arg.arg)
    if args.vararg:
        local.add(args.vararg.arg)
    if args.kwarg:
        local.add(args.kwarg.arg)

    for sub in ast.walk(fn):
        if isinstance(sub, (ast.Import, ast.ImportFrom)):
            _import_names(sub, local)
        elif isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store):
            local.add(sub.id)
        elif isinstance(sub, ast.arg):
            local.add(sub.arg)
        elif isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            local.add(sub.name)
        elif isinstance(sub, ast.ExceptHandler) and sub.name:
            local.add(sub.name)
    return local


def check_source(source, filename, counters=None):
    """检查一份源码，返回违规列表；每条为 dict（file/line/func/name/text/reason）。"""
    violations = []
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as exc:
        violations.append({
            'file': filename, 'line': exc.lineno or 0, 'func': '<module>', 'name': '?',
            'text': '', 'reason': 'syntax error, unparsable: %s' % exc.msg,
        })
        return violations

    module_names = module_level_names(tree)
    lines = source.splitlines()

    def line_text(lineno):
        return lines[lineno - 1].strip() if 0 < lineno <= len(lines) else ''

    functions = [n for n in ast.walk(tree)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    for fn in functions:
        local = function_local_names(fn, module_names)
        for sub in ast.walk(fn):
            if not (isinstance(sub, ast.Attribute) and sub.attr == QUERY_ATTR
                    and isinstance(sub.value, ast.Name)):
                continue
            name = sub.value.id
            if not name[:1].isupper():
                continue  # 判据只覆盖大写名（模型类命名约定）
            if counters is not None:
                counters['name_query_refs'] = counters.get('name_query_refs', 0) + 1
            if name in local:
                continue
            violations.append({
                'file': filename, 'line': sub.value.lineno, 'func': fn.name, 'name': name,
                'text': line_text(sub.value.lineno)[:160],
                'reason': 'no binding for "%s" in this module (not a module-level import/'
                          'assignment/def, not a parameter, not bound inside the function)' % name,
            })
    return violations


def _dedup(violations):
    seen = set()
    out = []
    for v in violations:
        key = (v['file'], v['line'], v['name'])
        if key in seen:
            continue
        seen.add(key)
        out.append(v)
    return out


def scan_root(root):
    """扫描目录下全部 .py，返回 (violations, scanned_files, counters)。"""
    violations = []
    counters = {'name_query_refs': 0}
    scanned = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != '__pycache__']
        for name in sorted(filenames):
            if not name.endswith('.py') or _is_skip_file(name):
                continue
            path = os.path.join(dirpath, name)
            scanned += 1
            with open(path, encoding='utf-8', errors='replace') as fh:
                src = fh.read()
            violations.extend(check_source(src, path, counters))
    return _dedup(violations), scanned, counters


# ------------------------------------------------------------------ 自检（不落盘）
#: (case id, expected violation count, source)。阳性 = 本模块不可解析的 <Name>.query；
#: 阴性 = 各种合法绑定形态（模块级/函数内 import、形参、赋值、属性链、大小写、嵌套 def）。
SELFTEST_CASES = [
    ('P1 missing-binding (P-01 original form)', 1, '''\
def delete_consumable(id):
    consumable = Consumable.query.get_or_404(id)
    return consumable
'''),
    ('P2 class method with unbound capitalized name', 1, '''\
class Repo:
    def get(self, oid):
        return Widget.query.get(oid)
'''),
    ('N1 module-level import binds the name', 0, '''\
from app.models import Consumable


def delete_consumable(id):
    return Consumable.query.get_or_404(id)
'''),
    ('N2 function-level import (existing precedent form)', 0, '''\
def delete_consumable(id):
    from app.models import Consumable
    return Consumable.query.get_or_404(id)
'''),
    ('N3 parameter binding', 0, '''\
def use(Consumable):
    return Consumable.query.get(1)
'''),
    ('N4 local assignment binding', 0, '''\
def use():
    Consumable = lookup_model()
    return Consumable.query.get(1)
'''),
    ('N5 module-level assignment binding', 0, '''\
Widget = object


def use():
    return Widget.query.get(1)
'''),
    ('N6 module-level class name binding', 0, '''\
class Widget:
    pass


def use():
    return Widget.query.get(1)
'''),
    ('N7 module-level try/except fallback import', 0, '''\
try:
    from app.models import Consumable
except ImportError:
    Consumable = None


def use():
    return Consumable.query.get(1)
'''),
    ('N8 aliased import (as C)', 0, '''\
from app.models import Consumable as C


def use():
    return C.query.get(1)
'''),
    ('N9 attribute chain M.Consumable.query (not a Name ref)', 0, '''\
import app.models as M


def use():
    return M.Consumable.query.get(1)
'''),
    ('N10 lowercase name x.query (rule is capitalized only)', 0, '''\
def use(x):
    return x.query.all()
'''),
    ('N11 nested def name is a local binding', 0, '''\
def outer():
    def Widget():
        pass
    return Widget.query
'''),
]


def run_selftest():
    print('[selftest] synthetic cases (in-memory sources, no filesystem writes): %d'
          % len(SELFTEST_CASES))
    passed = 0
    for idx, (title, expected, src) in enumerate(SELFTEST_CASES, 1):
        got = _dedup(check_source(src, '<case%d.py>' % idx, None))
        ok = len(got) == expected
        passed += 1 if ok else 0
        print('  [%s] %s -- expected %d / got %d'
              % ('PASS' if ok else 'FAIL', title, expected, len(got)))
        if not ok:
            for v in got:
                print('        hit: %s:%s [%s] %s' % (v['file'], v['line'], v['func'], v['name']))
    print('[selftest] result %d/%d %s'
          % (passed, len(SELFTEST_CASES), 'all passed' if passed == len(SELFTEST_CASES) else 'FAILED'))
    return 0 if passed == len(SELFTEST_CASES) else 1


def main(argv=None):
    _reconfigure_stdout()
    parser = argparse.ArgumentParser(
        description='check "<Name>.query" whose Name is unresolvable in this module '
                    '(long-term gate for P-01 class NameError)')
    parser.add_argument('--root', default='app', help='source dir to scan (default: app)')
    parser.add_argument('--verbose', action='store_true', help='print scan statistics')
    parser.add_argument('--json', action='store_true', help='append one machine-readable JSON line')
    parser.add_argument('--selftest', action='store_true',
                        help='run synthetic cases (no repo reads, no writes)')
    args = parser.parse_args(argv)

    if args.selftest:
        return run_selftest()

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print('[model_refs] not a directory: %s' % root)
        print('RESULT: ERROR')
        return 2

    violations, scanned, counters = scan_root(root)
    refs = counters.get('name_query_refs', 0)
    print('[model_refs] scanned %d files, name_query_refs %d, violations %d'
          % (scanned, refs, len(violations)))
    if args.verbose:
        print('[model_refs] root=%s (capitalized <Name>.query only; module-local resolvability)'
              % os.path.relpath(root))

    if violations:
        violations.sort(key=lambda v: (v['file'], v['line']))
        print('found %d violation(s):' % len(violations))
        for v in violations:
            print('  %s:%s  [%s]  %s.query -- %s'
                  % (os.path.relpath(v['file']), v['line'], v['func'], v['name'], v['reason']))
            if v['text']:
                print('        source: %s' % v['text'])
        print('RESULT: FAIL')
        code = 1
    else:
        print('RESULT: OK')
        code = 0

    if args.json:
        print('__JSON__' + json.dumps({
            'root': os.path.relpath(root).replace('\\', '/'),
            'scanned_files': scanned,
            'name_query_refs': refs,
            'violation_count': len(violations),
            'violations': [{k: v[k] for k in ('file', 'line', 'func', 'name', 'text', 'reason')}
                           for v in violations],
            'exit_code': code,
        }, ensure_ascii=True))
    return code


if __name__ == '__main__':
    sys.exit(main())
