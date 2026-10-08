# -*- coding: utf-8 -*-
"""check_notification_triggers.py — B13-09：通知触发器「是否真的被接线」的 AST 门禁（只读静态检查）。

## 为什么存在（B13-09 ← 原计划批次7「验证命令」+ `recon-backend.md` §6.2 T-A）
`app/services/notification_service.py` 里定义了 5 个模块级触发器
（`notify_process_change` / `notify_spec_change` / `notify_inventory_warning` /
`notify_task_assignment` / `notify_raw_substitution`），但**定义 ≠ 接线**：
`80-`/`recon-verification.md` 的现场取行显示「全仓非定义处调用点 = 1」
（只有 `routes.py` 的 `notify_raw_substitution(` 在替用分支里真被调用）。
「有没有接线」此前只能靠人读代码；本脚本把它变成**可执行门禁**。

## 检查什么（AST，不导入应用、不连数据库）
1. 扫 `--root`（默认 `app/`）下全部 `*.py`，抓**模块级** `def notify_*` ⇒ 触发器清单；
2. 每个触发器必须至少有一处**非定义处调用点**：`notify_x(...)` 或 `<obj>.notify_x(...)`
   （`ast.Call` 形态）。**只被 `import` 引用、只在注释/字符串里出现、只在自己函数体内递归
   调用，都不算接线**（import-only 会打成 `WARN import-only ...`，但不计接线）；
3. `--expect N` = **期望已接线的触发器数**（严格相等），缺参即视为用法错误（exit 2），
   不得「不检查」或静默通过；
4. 「只登记、不接线」必须走**显式登记**，且每条登记必须在仓库内**指向一处可见锚点**
   （`anchor.file` + 同行 `needles`）。锚点读不到 ⇒ 该登记失效 ⇒ 报红。
   两种登记语义（都写在脚本内的表里，CLI 只能引用、不能凭空豁免）：
   * `--allow-unwired <name>`：**永久豁免**（`UNWIRED_REGISTRY`）。防洗白：若该触发器
     **后来被接线** ⇒ 陈旧豁免 ⇒ 报红（永久豁免不得比它的理由活得更久）；
   * `--pending-wiring <name>`：**待接线登记**（`PENDING_REGISTRY`），登记「由哪个任务落线」；
     落线后自动被消费（打印 `wired-pending ... consumed`，不报红 —— 不惩罚进展），
     未落线时报文里指名 owner/任务，且未落线时锚点同样必须可见。
5. 抓到 0 个触发器 ⇒ 报红（防空跑恒绿）；`--root` 不存在 ⇒ exit 2。

## 判据（B13-09 验收）
* 接线后：`--expect <已接线数>` ⇒ `RESULT: OK` ⇒ exit 0；
* 阴性对照：把某触发器的调用点注释掉 ⇒ `UNREGISTERED-TRIGGER` + `EXPECT-MISMATCH` ⇒ exit 1；
* 未接线且未登记 ⇒ exit 1；陈旧永久豁免 ⇒ exit 1；登记锚点失效 ⇒ exit 1。

## 当前实测（2026-10-08，批次13 现场；行号随工作树漂移，脚本每次现场取行）
* 触发器 5 个；**已接线 1 个**（`notify_raw_substitution`，调用点 `app/main/routes.py`）；
* 因此 `--expect 5` **不可达**（`notify_inventory_warning` 按拍板项 6 永久豁免），
  可达上限 = 5 - 1 = **4**；新值 `--expect 4` 即 `ci_gates` 里固化的目标值（B13-06 落线后自动转绿）；
* 未接线 4 个的登记：1 条永久（拍板项 6）+ 3 条 `--pending-wiring`（t9 / B13-06）。

## 合法更新程序（新增/接线触发器时，照 A-70 式三步，勿直接改数字）
1. 先出新证据（跑本脚本把 `definition` / `wired` / `unwired` 行落档）；
2. 再改**期望值与登记表**，并写明「前值 → 新值 → 依据 → 时点」（`--expect`、`UNWIRED_REGISTRY`、
   `PENDING_REGISTRY`、`ci_gates.py` 的 `expects` 针脚都可能需要同步）；
3. 最后证明判据仍会红：把某调用点注释掉（或 `--expect` 报一个旧值稿）必须 exit 1。

## 用法
    python -B scripts/check_notification_triggers.py --expect 4 \
        --allow-unwired notify_inventory_warning \
        --pending-wiring notify_process_change --pending-wiring notify_spec_change \
        --pending-wiring notify_task_assignment
    python -B scripts/check_notification_triggers.py --root <dir> --expect N   # 注入/对照组用
    python -B scripts/check_notification_triggers.py --selftest                # 合成用例（不读仓库）
    python -B scripts/check_notification_triggers.py --json                    # 机读 JSON 一行

退出码：判据全过 0；有违规（未接线未登记 / expect 不符 / 陈旧豁免 / 锚点失效 / 0 触发器 / 语法错）1；
环境或用法错误（`--root` 不存在、缺 `--expect`）2。

## 输出编码（A-14/A-60）
控制台行的**判据字段一律 ASCII**（针脚：`triggers=` / `wired=` / `unwired=` / `expect=` /
`reason_code=` / `owner=` / `wiring_task=` / 错误码），中文只出现在本 docstring、`--json` 的转义串
与仓库内登记锚点文本里；stdout/stderr 另做 `utf-8 + backslashreplace` 护栏，避免 GBK 控制台
`UnicodeEncodeError` 把后续判据行吞掉（批次13 的同类病史，见 B13-00 复核）。
"""
import argparse
import ast
import json
import os
import sys

#: 仓库根（本脚本在 `<repo>/scripts/` 下）——锚点一律按仓库相对路径解析，与 cwd 无关
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TRIGGER_PREFIX = 'notify_'
DEFAULT_ROOT = 'app'

PASS_LINE = 'RESULT: OK'
FAIL_LINE = 'RESULT: FAIL'
ERROR_LINE = 'RESULT: ERROR'

#: 备份/生成物副本不参与检查（与 check_model_refs.py / check_properties.py 同口径）
SKIP_FILENAMES = {
    'routes_backup.py', 'routes_original.py', 'routes_full.py', 'routes_with_duplicates.py',
}
SKIP_SUFFIXES = ('.bak', '.new', '.backup', '.pyc')

#: 「只登记、不接线」的**永久**豁免登记表（CLI 的 `--allow-unwired` 只能引用本表内的名字）。
#: 每条必须带 `anchor`：仓库内可见登记（`file` + 同行 `needles`），脚本每次运行都实测可见性。
UNWIRED_REGISTRY = {
    'notify_inventory_warning': {
        'reason_code': 'decision-6-min-stock-source-missing',
        'owner': 'captain-decision-6',
        'reason': '拍板项 6（`test-reports-2026-10/81-后续开发与测试规划.md` §7.2 第 860 行）：'
                  '`min_stock` 数据源当前仓库内**不存在**（无该列、无该配置项）⇒ 默认路径 = '
                  '先加 `SystemConfig` 配置项（零 schema 变更），值由业务给；未给则**不接线**该触发器'
                  '（只登记）。用户至今未给值 ⇒ 该触发器**合法地**保持未接线。',
        'anchor': {
            'file': 'test-reports-2026-10/81-后续开发与测试规划.md',
            'needles': ['notify_inventory_warning', '只登记'],
        },
    },
}

#: 「待接线」登记表（CLI 的 `--pending-wiring` 只能引用本表内的名字）：落线后自动消费、不报红。
PENDING_REGISTRY = {
    'notify_task_assignment': {
        'reason_code': 'pending-B13-06-task-assignment',
        'owner': 'notify-dev',
        'wiring_task': 't9-B13-06',
        'reason': 'B13-06（`81-`:158）要求在派工落点接线（`routes.py` 的 add_task / manage_tasks / '
                  '生产中心派工）；由 t9 落线后本门禁自动消费该登记。',
        'anchor': {
            'file': 'test-reports-2026-10/81-后续开发与测试规划.md',
            'needles': ['B13-06', 'notify_task_assignment'],
        },
    },
    'notify_process_change': {
        'reason_code': 'pending-B13-06-process-change',
        'owner': 'notify-dev',
        'wiring_task': 't9-B13-06',
        'reason': 'B13-06（`81-`:158）要求在工序变更落点接线；由 t9 落线后本门禁自动消费该登记。',
        'anchor': {
            'file': 'test-reports-2026-10/81-后续开发与测试规划.md',
            'needles': ['B13-06', 'notify_process_change'],
        },
    },
    'notify_spec_change': {
        'reason_code': 'pending-B13-06-spec-change',
        'owner': 'notify-dev',
        'wiring_task': 't9-B13-06',
        'reason': 'B13-06（`81-`:158）要求在规格变更落点接线；由 t9 落线后本门禁自动消费该登记。',
        'anchor': {
            'file': 'test-reports-2026-10/81-后续开发与测试规划.md',
            'needles': ['B13-06', 'notify_spec_change'],
        },
    },
}


# ------------------------------------------------------------------ 基础工具
def _reconfigure_stdout():
    """A-14/A-60 + B13-00 复核：GBK 控制台下 print 不得崩溃、不得吞掉后续判据行。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='backslashreplace')
        except (AttributeError, ValueError, OSError):
            pass


def _rel(path):
    """仓库相对 POSIX 路径（便于机读与跨平台打印）。"""
    try:
        rel = os.path.relpath(path, REPO_ROOT)
    except ValueError:                                    # 不同盘符
        return str(path).replace('\\', '/')
    return rel.replace('\\', '/')


def _is_skip_file(name):
    return name in SKIP_FILENAMES or name.endswith(SKIP_SUFFIXES)


def iter_py_files(root):
    """按确定顺序遍历 `*.py`（跳过 `__pycache__` 与备份副本）。"""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d != '__pycache__')
        for name in sorted(filenames):
            if name.endswith('.py') and not _is_skip_file(name):
                yield os.path.join(dirpath, name)


# ------------------------------------------------------------------ 扫描（AST）
def _walk_calls(node, owner, rel, out, text_of):
    """收集触发器调用点；`owner` = 最近的函数名（用于剔除「自己递归调用自己」）。"""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _walk_calls(child, child.name, rel, out, text_of)
            continue
        if isinstance(child, ast.Call):
            fn = child.func
            name = None
            if isinstance(fn, ast.Name):
                name = fn.id
            elif isinstance(fn, ast.Attribute):
                name = fn.attr
            if name and name.startswith(TRIGGER_PREFIX):
                out.append({'name': name, 'file': rel, 'line': child.lineno,
                            'in_function': owner, 'text': text_of(child.lineno)})
        _walk_calls(child, owner, rel, out, text_of)


def scan_sources(sources):
    """扫「{相对路径: 源码}」⇒ 定义 / 调用点 / import 引用 / 语法错（纯函数，自检复用）。"""
    definitions, calls, import_refs, syntax_errors = [], [], [], []
    for rel in sorted(sources):
        src = sources[rel]
        try:
            tree = ast.parse(src, filename=rel)
        except SyntaxError as exc:
            syntax_errors.append({'file': rel, 'line': exc.lineno or 0, 'msg': exc.msg})
            continue
        lines = src.splitlines()

        def text_of(lineno, _lines=lines):
            return _lines[lineno - 1].strip()[:160] if 0 < lineno <= len(_lines) else ''

        for node in tree.body:                            # 模块级 def 才算触发器
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                    and node.name.startswith(TRIGGER_PREFIX):
                definitions.append({'name': node.name, 'file': rel, 'line': node.lineno})
        _walk_calls(tree, None, rel, calls, text_of)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    name = alias.asname or alias.name
                    if isinstance(node, ast.Import):
                        name = name.split('.')[0]
                    if name.startswith(TRIGGER_PREFIX):
                        import_refs.append({'name': name, 'file': rel, 'line': node.lineno,
                                            'text': text_of(node.lineno)})
    return {'files': len(sources), 'definitions': definitions, 'calls': calls,
            'import_refs': import_refs, 'syntax_errors': syntax_errors}


def scan_tree(root):
    """读目录下全部 `*.py` 后走 `scan_sources`（相对路径一律相对仓库根）。"""
    sources = {}
    for path in iter_py_files(root):
        with open(path, encoding='utf-8', errors='replace') as fh:
            sources[_rel(path)] = fh.read()
    return scan_sources(sources)


# ------------------------------------------------------------------ 登记锚点
def check_anchor(anchor):
    """登记锚点可见性：`anchor['file']` 存在且 `anchor['needles']` 在**同一行**共现。"""
    if not anchor or not anchor.get('file'):
        return False, 0, 'no anchor declared'
    path = os.path.join(REPO_ROOT, anchor['file'])
    if not os.path.isfile(path):
        return False, 0, 'anchor file not found: %s' % anchor['file']
    with open(path, encoding='utf-8', errors='replace') as fh:
        lines = fh.read().splitlines()
    needles = list(anchor.get('needles') or [])
    for lineno, line in enumerate(lines, 1):
        if all(n in line for n in needles):
            return True, lineno, 'needles co-located'
    return False, 0, 'needles not co-located on one line: %s' % needles


# ------------------------------------------------------------------ 判据（纯函数）
def evaluate(scan, expect, allow_unwired=None, pending_wiring=None, anchor_checker=None):
    """按扫描结果判据；返回机器可读报告（`ok` = 无 problem）。"""
    anchor_checker = anchor_checker or check_anchor
    allow = list(dict.fromkeys(allow_unwired or []))
    pend = list(dict.fromkeys(pending_wiring or []))

    definitions = sorted({d['name'] for d in scan['definitions']})
    definition_sites = {}
    for d in scan['definitions']:
        definition_sites.setdefault(d['name'], d)

    call_sites = {}
    for name in definitions:
        call_sites[name] = sorted({(c['file'], c['line']) for c in scan['calls']
                                   if c['name'] == name and c.get('in_function') != name})
    wired = {n: bool(call_sites[n]) for n in definitions}
    wired_count = sum(1 for n in definitions if wired[n])
    unwired = [n for n in definitions if not wired[n]]

    problems, notes, exemptions = [], [], []

    def problem(code, detail, trigger=None):
        problems.append({'code': code, 'detail': detail, 'trigger': trigger})

    if not definitions:
        problem('NO-TRIGGERS',
                'no module-level "def %s*" found under the scanned root '
                '(vacuous scan: the gate must not pass silently)' % TRIGGER_PREFIX)

    for name in allow:
        if name not in UNWIRED_REGISTRY:
            problem('UNREGISTERED-EXEMPTION',
                    '--allow-unwired "%s" is not declared in UNWIRED_REGISTRY '
                    '(ad-hoc waivers are forbidden)' % name, name)
        if name not in definitions:
            problem('STALE-EXEMPTION-NO-TRIGGER',
                    '--allow-unwired "%s" has no matching trigger definition' % name, name)
    for name in pend:
        if name not in PENDING_REGISTRY:
            problem('UNREGISTERED-PENDING',
                    '--pending-wiring "%s" is not declared in PENDING_REGISTRY' % name, name)
        if name not in definitions:
            problem('STALE-PENDING-NO-TRIGGER',
                    '--pending-wiring "%s" has no matching trigger definition' % name, name)

    for name in allow:
        entry = UNWIRED_REGISTRY.get(name) or {}
        anchor = entry.get('anchor') or {}
        ok, line, detail = anchor_checker(anchor)
        is_wired = wired.get(name)
        exemptions.append({'trigger': name, 'kind': 'allow-unwired', 'permanent': True,
                           'reason_code': entry.get('reason_code', ''),
                           'owner': entry.get('owner', ''),
                           'reason': entry.get('reason', ''),
                           'anchor_file': anchor.get('file'), 'anchor_line': line if ok else None,
                           'anchor_ok': bool(ok), 'anchor_detail': detail, 'wired': is_wired})
        if name in definitions and is_wired:
            problem('STALE-PERMANENT-EXEMPTION',
                    '--allow-unwired "%s" is stale: the trigger IS wired now => remove the '
                    'permanent exemption (a waiver must not outlive its reason)' % name, name)
        if name in definitions and not ok:
            problem('ANCHOR-NOT-VISIBLE',
                    '--allow-unwired "%s": registration anchor not visible in repo (%s -> %s)'
                    % (name, anchor.get('file'), detail), name)

    for name in pend:
        entry = PENDING_REGISTRY.get(name) or {}
        anchor = entry.get('anchor') or {}
        ok, line, detail = anchor_checker(anchor)
        is_wired = wired.get(name)
        exemptions.append({'trigger': name, 'kind': 'pending-wiring', 'permanent': False,
                           'reason_code': entry.get('reason_code', ''),
                           'owner': entry.get('owner', ''),
                           'wiring_task': entry.get('wiring_task', ''),
                           'reason': entry.get('reason', ''),
                           'anchor_file': anchor.get('file'), 'anchor_line': line if ok else None,
                           'anchor_ok': bool(ok), 'anchor_detail': detail, 'wired': is_wired,
                           'consumed': bool(is_wired)})
        if name in definitions and is_wired:
            notes.append({'code': 'PENDING-CONSUMED',
                          'detail': 'pending-wiring "%s" is now wired (%s:%s) => registered debt '
                                    'settled, no failure (update --expect to the new count)'
                                    % (name, call_sites[name][0][0], call_sites[name][0][1])})
        elif name in definitions and not ok:
            problem('ANCHOR-NOT-VISIBLE',
                    '--pending-wiring "%s": registration anchor not visible in repo (%s -> %s)'
                    % (name, anchor.get('file'), detail), name)

    for name in unwired:
        if name not in allow and name not in pend:
            problem('UNREGISTERED-TRIGGER',
                    'trigger "%s" is NOT wired (no call site outside its own definition) and NOT '
                    'registered: use --allow-unwired (permanent record) or --pending-wiring '
                    '(owned by a wiring task)' % name, name)

    reachable_max = len(definitions) - len([n for n in allow if n in definitions])
    if expect is not None:
        if expect != wired_count:
            problem('EXPECT-MISMATCH',
                    'expect %d wired, got %d (short by %d)' % (expect, wired_count,
                                                               expect - wired_count))
        if expect > reachable_max:
            notes.append({'code': 'EXPECT-UNREACHABLE',
                          'detail': 'expect %d exceeds reachable max %d (definitions %d - permanent '
                                    'exemptions %d): unreachable while the registered permanent '
                                    'exemption stands' % (expect, reachable_max, len(definitions),
                                                          len(definitions) - reachable_max)})
    for e in scan['syntax_errors']:
        problem('SYNTAX-ERROR', '%s:%s unparsable: %s' % (e['file'], e['line'], e['msg']))

    return {'definitions': definitions, 'definition_sites': definition_sites,
            'call_sites': {k: [list(x) for x in v] for k, v in call_sites.items()},
            'wired': wired, 'wired_count': wired_count, 'unwired': unwired,
            'expect': expect, 'reachable_max': reachable_max,
            'exemptions': exemptions, 'notes': notes, 'problems': problems,
            'ok': not problems}


# ------------------------------------------------------------------ 打印
def print_report(rep, scan, root_display, out=print):
    out('[notify_triggers] root=%s scanned=%d triggers=%d wired=%d unwired=%d expect=%s'
        % (root_display, scan['files'], len(rep['definitions']), rep['wired_count'],
           len(rep['unwired']), rep['expect'] if rep['expect'] is not None else 'none'))
    for name in rep['definitions']:
        site = rep['definition_sites'][name]
        out('[notify_triggers] definition %s @ %s:%d' % (name, site['file'], site['line']))
    for name in rep['definitions']:
        if rep['wired'][name]:
            file_, line_ = rep['call_sites'][name][0]
            out('[notify_triggers] wired %s @ %s:%d (call sites=%d)'
                % (name, file_, line_, len(rep['call_sites'][name])))
    for item in rep['exemptions']:
        if item['kind'] == 'allow-unwired':
            out('[notify_triggers] unwired %s -- allow-unwired (permanent) anchor=%s:%s '
                'reason_code=%s owner=%s'
                % (item['trigger'], item['anchor_file'], item['anchor_line'] or '?',
                   item['reason_code'], item['owner']))
        else:
            state = 'wired-pending(consumed)' if item.get('consumed') else 'unwired'
            out('[notify_triggers] %s %s -- pending-wiring owner=%s wiring_task=%s anchor=%s:%s'
                % (state, item['trigger'], item['owner'], item.get('wiring_task') or '?',
                   item['anchor_file'], item['anchor_line'] or '?'))
    wired_names = {n for n in rep['definitions'] if rep['wired'][n]}
    for ref in scan['import_refs']:
        if ref['name'] not in wired_names:
            out('[notify_triggers] WARN import-only %s @ %s:%d (import alone does NOT count as '
                'wiring)' % (ref['name'], ref['file'], ref['line']))
    for note in rep['notes']:
        out('[notify_triggers] NOTE %s: %s' % (note['code'], note['detail']))
    for prob in rep['problems']:
        out('[notify_triggers] FAIL %s: %s' % (prob['code'], prob['detail']))
    out(PASS_LINE if rep['ok'] else FAIL_LINE)


# ------------------------------------------------------------------ 自检（不读仓库）
SELFTEST_TRIGGER_DEF = 'def notify_alpha(x):\n    return x\n'


def _stub_anchor(ok):
    """自检用的锚点桩：自检**不读仓库**（`check_anchor` 由现场运行与对照组行使）。"""
    return lambda anchor: ((True, 1, 'stub: needles co-located') if ok
                           else (False, 0, 'stub: anchor hidden'))


def _selftest_cases():
    """(id, sources, kwargs, expected_ok, expected_problem_codes)；
    `kwargs['anchor_ok']` = 桩锚点可见性（自检不读仓库）。"""
    allow_inv = ['notify_inventory_warning']
    pend_task = ['notify_task_assignment']
    return [
        ('S1 1 def + 1 call => wired (expect 1 ok)',
         {'a.py': 'def notify_alpha(x):\n    return x\n\n\ndef use():\n    return notify_alpha(1)\n'},
         {'expect': 1}, True, []),
        ('S2 def with no call => unregistered + expect mismatch',
         {'a.py': SELFTEST_TRIGGER_DEF}, {'expect': 1}, False,
         ['UNREGISTERED-TRIGGER', 'EXPECT-MISMATCH']),
        ('S3 import-only does NOT count as wiring',
         {'a.py': SELFTEST_TRIGGER_DEF,
          'b.py': 'from a import notify_alpha\n'}, {'expect': 1}, False,
         ['UNREGISTERED-TRIGGER', 'EXPECT-MISMATCH']),
        ('S4 self-recursion does NOT count as wiring',
         {'a.py': 'def notify_alpha(x):\n    return notify_alpha(x)\n'}, {'expect': 1}, False,
         ['UNREGISTERED-TRIGGER', 'EXPECT-MISMATCH']),
        ('S5 attribute call <obj>.notify_alpha() counts',
         {'a.py': SELFTEST_TRIGGER_DEF,
          'b.py': 'import a\n\n\ndef use():\n    return a.notify_alpha(1)\n'}, {'expect': 1}, True, []),
        ('S6 permanent exemption with visible anchor + expect 0',
         {'a.py': 'def notify_inventory_warning(m, c, s):\n    return None\n'},
         {'expect': 0, 'allow_unwired': allow_inv, 'anchor_ok': True}, True, []),
        ('S7 permanent exemption with hidden anchor => red',
         {'a.py': 'def notify_inventory_warning(m, c, s):\n    return None\n'},
         {'expect': 0, 'allow_unwired': allow_inv, 'anchor_ok': False}, False,
         ['ANCHOR-NOT-VISIBLE']),
        ('S8 stale permanent exemption (trigger wired now) => red',
         {'a.py': 'def notify_inventory_warning(m, c, s):\n    return None\n'
                  '\n\ndef use():\n    return notify_inventory_warning(1, 2, 3)\n'},
         {'expect': 1, 'allow_unwired': allow_inv, 'anchor_ok': True}, False,
         ['STALE-PERMANENT-EXEMPTION']),
        ('S9 pending-wiring consumed once wired => ok (no failure)',
         {'a.py': 'def notify_task_assignment(e, n, b=None):\n    return None\n'
                  '\n\ndef use():\n    return notify_task_assignment(1, 2)\n'},
         {'expect': 1, 'pending_wiring': pend_task, 'anchor_ok': True}, True,
         ['NOTE:PENDING-CONSUMED']),
        ('S10 pending-wiring, still unwired (owned by a task) => ok with expect 0',
         {'a.py': 'def notify_task_assignment(e, n, b=None):\n    return None\n'},
         {'expect': 0, 'pending_wiring': pend_task, 'anchor_ok': True}, True, []),
        ('S11 zero triggers => red (anti vacuous-green)',
         {'a.py': 'def other(x):\n    return x\n'}, {'expect': 0}, False, ['NO-TRIGGERS']),
        ('S12 two triggers wired, expect 1 => red',
         {'a.py': 'def notify_alpha(x):\n    return x\n\n\ndef notify_beta(x):\n    return x\n'
                  '\n\ndef use():\n    return notify_alpha(1) + notify_beta(2)\n'},
         {'expect': 1}, False, ['EXPECT-MISMATCH']),
        ('S13 ad-hoc exemption not declared in the registry => red',
         {'a.py': 'def notify_zeta(x):\n    return x\n'},
         {'expect': 0, 'allow_unwired': ['notify_zeta']}, False,
         ['UNREGISTERED-EXEMPTION']),
        ('S14 commented-out call does NOT count as wiring',
         {'a.py': SELFTEST_TRIGGER_DEF,
          'b.py': 'from a import notify_alpha\n\n\ndef use():\n    # return notify_alpha(1)\n'
                  '    return None\n'}, {'expect': 1}, False,
         ['UNREGISTERED-TRIGGER', 'EXPECT-MISMATCH']),
        ('S15 unparsable file => red',
         {'a.py': 'def notify_alpha(x:\n    return x\n'}, {'expect': 0}, False, ['SYNTAX-ERROR']),
        ('S16 expect above reachable max (permanent exemption) => red + NOTE',
         {'a.py': 'def notify_inventory_warning(m, c, s):\n    return None\n',
          'b.py': 'def notify_alpha(x):\n    return x\n\n\ndef use():\n    return notify_alpha(1)\n'},
         {'expect': 2, 'allow_unwired': allow_inv, 'anchor_ok': True}, False,
         ['EXPECT-MISMATCH', 'NOTE:EXPECT-UNREACHABLE']),
    ]


def run_selftest():
    cases = _selftest_cases()
    print('[selftest] synthetic cases (in-memory sources, no repo reads, no writes): %d'
          % len(cases))
    passed = 0
    for idx, (title, sources, kw, want_ok, want_codes) in enumerate(cases, 1):
        scan = scan_sources(sources)
        kwargs = dict(kw)
        anchor_ok = kwargs.pop('anchor_ok', True)
        kwargs['anchor_checker'] = _stub_anchor(anchor_ok)
        rep = evaluate(scan, **kwargs)
        got_codes = {p['code'] for p in rep['problems']}
        got_codes |= {'NOTE:' + n['code'] for n in rep['notes']}
        ok = (rep['ok'] == want_ok) and set(want_codes) <= got_codes
        passed += 1 if ok else 0
        print('  [%s] %s -- expect ok=%s codes=%s / got ok=%s codes=%s'
              % ('PASS' if ok else 'FAIL', title, want_ok, sorted(want_codes) or '[]',
                 rep['ok'], sorted(got_codes) or '[]'))
        if not ok:
            for p in rep['problems']:
                print('        hit: %s -- %s' % (p['code'], p['detail']))
    print('[selftest] result %d/%d %s'
          % (passed, len(cases), 'all passed' if passed == len(cases) else 'FAILED'))
    return 0 if passed == len(cases) else 1


# ------------------------------------------------------------------ 主流程
def main(argv=None):
    _reconfigure_stdout()
    parser = argparse.ArgumentParser(
        description='gate: every module-level "def notify_*" must have >=1 call site outside '
                    'its own definition (B13-09), with explicit registration for knowingly '
                    'unwired triggers')
    parser.add_argument('--root', default=DEFAULT_ROOT,
                        help='source dir to scan (default: %s)' % DEFAULT_ROOT)
    parser.add_argument('--expect', type=int, default=None,
                        help='expected number of WIRED triggers (strict equality; required)')
    parser.add_argument('--allow-unwired', action='append', default=[], metavar='NAME',
                        help='permanent exemption (must be declared in UNWIRED_REGISTRY)')
    parser.add_argument('--pending-wiring', action='append', default=[], metavar='NAME',
                        help='registered-as-pending wiring (must be declared in PENDING_REGISTRY)')
    parser.add_argument('--json', action='store_true',
                        help='append one machine-readable JSON line (__JSON__...)')
    parser.add_argument('--verbose', action='store_true', help='print scan statistics')
    parser.add_argument('--selftest', action='store_true',
                        help='run synthetic cases (no repo reads, no writes)')
    args = parser.parse_args(argv)

    if args.selftest:
        return run_selftest()

    root = os.path.abspath(args.root)
    root_display = _rel(root)
    if not os.path.isdir(root):
        print('[notify_triggers] not a directory: %s' % root_display)
        print(ERROR_LINE)
        return 2

    if args.expect is None:
        print('[notify_triggers] --expect N is required (N = expected number of WIRED triggers; '
              'strict equality). Example for this batch: --expect 4 '
              '--allow-unwired notify_inventory_warning '
              '--pending-wiring notify_process_change --pending-wiring notify_spec_change '
              '--pending-wiring notify_task_assignment')
        print(ERROR_LINE)
        return 2

    scan = scan_tree(root)
    rep = evaluate(scan, args.expect, args.allow_unwired, args.pending_wiring)
    if args.verbose:
        print('[notify_triggers] scanned files=%d calls=%d import_refs=%d'
              % (scan['files'], len(scan['calls']), len(scan['import_refs'])))
    print_report(rep, scan, root_display)

    code = 0 if rep['ok'] else 1
    if args.json:
        doc = {
            'harness': 'check_notification_triggers.py', 'b13': 'B13-09',
            'root': root_display, 'scanned_files': scan['files'],
            'trigger_count': len(rep['definitions']), 'wired_count': rep['wired_count'],
            'unwired': rep['unwired'], 'expect': rep['expect'],
            'reachable_max': rep['reachable_max'],
            'definitions': rep['definition_sites'],
            'call_sites': rep['call_sites'],
            'exemptions': rep['exemptions'], 'notes': rep['notes'],
            'problems': rep['problems'], 'ok': rep['ok'],
            'exit_code': code,
        }
        print('__JSON__' + json.dumps(doc, ensure_ascii=True))
    return code


if __name__ == '__main__':
    sys.exit(main())
