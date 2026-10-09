# -*- coding: utf-8 -*-
"""check_doc_claims.py — TL-06「口径守卫」+ TL-07「依赖钉版一致性」的单一入口（只读，除 --write-lock）。

## 为什么存在（TL-06）
本项目第 1 轮里**同一批数字反复漂移**至少 6 次（`35` §101：69 vs 83 / 45 vs 49 / 24 vs 31 /
459 vs 595 / 104 vs 138 / 43 vs 37），其中 `160`（方法级 GET，权威 `161`，A-25）、
`≥135` / `≥139`（写端点无命中计数，权威 `≥141`，A-31）、`「45 张」`（零行表，权威 `49 张`，A-2）
已成**作废口径**。`G-14` 要求「报告文本不得出现作废口径值」，`26` §243 要求「报告顶部口径表 +
关键数字机器校验」。本脚本就是那台机器。

## 检查什么
1. **口径表**（机器可读，放在报告顶部；见下）里的每个键：
   * 必须是**已登记口径键**（见 `--list-constants`）；未登记 ⇒ 违规；
   * 值必须等于**钉常量**，且钉常量必须与**权威源**逐条相等（源漂移 ⇒ 违规）—— 这就是「口径漂移警报」。
2. **作废口径值**：文档任意一行出现 `≥135` / `≥139` / 方法级 `160` / `45 张` ⇒ 违规；
   但**同一行带撤回标记**（`作废`/`已更正`/`前稿`/`推翻`/`❌`/`不得出现`/`禁止`/`retired` 等）
   视为「引用作废值说明其作废」⇒ 放行（防「引用历史必须重写报告」）。
3. **依赖钉版一致性**（TL-07 判据层）：`requirements.lock` 存在、全部精确 `==` 钉版、
   与 `requirements.txt` 一致（锁头记 `requirements.txt sha256`）、且与**当前环境**一致
   （`importlib.metadata` 逐条对拍；`# env-exceptions:` 列出的包降级为 WARN）。

## 口径表格式（报告顶部，注释形式，渲染不可见）
    <!-- caliber-table
    rules_total = 271
    method_level_GET = 161
    -->
支持 `=` 或 `:`；值必须是整数或纯 ASCII 标识符。一份文档可有多块（合并，重复键以先见为准并告警）。

## 用法
    python -B scripts/check_doc_claims.py                       # 默认扫第2轮报告（5x/6x）+ 依赖钉版
    python -B scripts/check_doc_claims.py --docs <path> ...      # 指定文档（支持 glob）
    python -B scripts/check_doc_claims.py --require-caliber      # 被扫文档必须带口径表
    python -B scripts/check_doc_claims.py --lock <p> --requirements <p>
    python -B scripts/check_doc_claims.py --list-constants       # 打印口径键登记表与权威源
    python -B scripts/check_doc_claims.py --write-lock           # 生成/刷新 requirements.lock（唯一的写操作）
    python -B scripts/check_doc_claims.py --selftest             # 受控对照（口径/作废值/lock 四类阳性+阴性）

退出码：0 = 全部通过；1 = 有违规；2 = 参数/环境错误。

## 边界（有意为之）
- 作废值只按**行**判定，且**数字类**作废值（`160`）要求同行出现度量语境词
  （路由/规则/端点/方法级/GET/覆盖/断言/rules…）⇒ `1600`、`160 元` 不会被误判。
- 默认扫描域 = **第2轮报告**（`5*.md` / `6*.md`）；第1轮语料（`0x`–`4x`）里大量「引用作废值」的
  历史段落不在默认域内（用 `--docs` 显式扫描；已知 `00` §6 仍有一处陈旧「45 张」，见交付登记）。
- 口径表的**采用**由各报告作者完成（本脚本不改别人的文档）；`--require-caliber` 用于把
  「最终报告必须带口径表」变成可执行判据。
- `--write-lock` 是唯一写操作，只写 `requirements.lock`，且写入前打印 diff 摘要。
"""
import argparse
import ast
import glob
import hashlib
import importlib.metadata as md
import json
import os
import platform
import re
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORTS_ROOT = os.path.join(REPO_ROOT, 'test-reports-2026-10')
HARNESS_DIR = os.path.join(REPORTS_ROOT, 'harness')
COVERAGE_JSON = os.path.join(REPORTS_ROOT, 'evidence', 'harness', 'coverage.json')

#: 归档锚点留档读数（A-70 第①步留档 / B17-16）：本 run 的 coverage 产物缺失时打印，
#: 用来把「锚点没传/没生成」与「口径真的漂移了」区分开（缺产物仍判 hard fail）。
#: 来源：`test-reports-2026-10/evidence/harness/ci-run-20261009-054416/coverage.json`
#: （246076 B，sha256 58BF844628402AE6D87F6A0F0336049D313463E83C28DFA448BBEFD9DB21E055）。
COVERAGE_ANCHOR_READINGS = {
    'anchor': 'test-reports-2026-10/evidence/harness/ci-run-20261009-054416/coverage.json',
    'sha256': '58BF844628402AE6D87F6A0F0336049D313463E83C28DFA448BBEFD9DB21E055',
    'values': {'rules_total': 273, 'method_level_GET': 161, 'method_level_non_get_total': 157,
               'writable_rules_non_get': 155, 'writable_any_covered_by_all': 118,
               'writable_literal_covered_by_all': 110, 'uncovered_writable': 0,
               'smoke_targets': 148, 'smoke_unresolved': 9},
}
RUN_GATES = os.path.join(HARNESS_DIR, 'run_gates.py')
COVERAGE_DRIFT = os.path.join(HARNESS_DIR, 'coverage_drift.py')
GH_WORKFLOW = os.path.join(REPO_ROOT, '.github', 'workflows', 'docker-deploy.yml')
DEFAULT_LOCK = os.path.join(REPO_ROOT, 'requirements.lock')
DEFAULT_REQUIREMENTS = os.path.join(REPO_ROOT, 'requirements.txt')
DEFAULT_DOC_GLOBS = ('test-reports-2026-10/5*.md', 'test-reports-2026-10/6*.md')

#: 口径键登记表：键 -> (钉值, 权威源说明, 备注)。**值由 `_verify_sources()` 逐条实读复核**。
#: B17-16（A-70 三步）：14 条陈旧钉值按现场重取更新；改前值留档在
#: `test-reports-2026-10/B17-登记.md` §B17-16（改前 = violations=16 / selftest 15/16）。
PINNED = {
    'rules_total': (273, 'coverage.json:summary.rules_total ∥ coverage_drift.LOCKED.rules_total',
                    '路由规则总数（route_inventory / coverage_drift 判据钉值）'),
    'method_level_GET': (161, 'coverage.json:summary.method_level_GET',
                         '方法级 GET（`08` §2 记 160 已作废，A-25）'),
    'method_level_non_get_total': (157, 'coverage.json:summary.method_level_non_get_total',
                                   '方法级非 GET 端点总数'),
    'writable_rules_non_get': (155, 'coverage.json:summary.writable_rules_non_get',
                               '可写（非 GET）规则数'),
    'writable_any_covered_by_all': (118, 'coverage.json:summary.writable_any_covered_by_all',
                                    '可写规则含动态命中的覆盖数'),
    'writable_literal_covered_by_all': (110, 'coverage.json:summary.writable_literal_covered_by_all',
                                        '可写规则字面量命中数'),
    'uncovered_writable_rules': (0, 'coverage.json:uncovered_writable 长度 ∥ '
                                    'coverage_drift.UNCOVERED_WRITABLE_MAX',
                                 '无任何命中的可写规则数（A-31 的规则级权威值）'),
    'non_get_uncovered_method_level': (39, '派生：method_level_non_get_total − '
                                           'writable_any_covered_by_all（157 − 118）',
                                       '无任何命中的非 GET 方法级端点（A-31 权威值；135/139 作废）'),
    'smoke_targets': (148, 'coverage.json:smoke_test_plan.static_reproduction_targets',
                      'smoke 静态复现目标数'),
    'smoke_unresolved': (9, 'coverage.json:smoke_test_plan.static_reproduction_unresolved',
                         'smoke 静态复现未解析数'),
    'templates_files': (87, 'run_gates.EXPECTED.templates_files', '模板文件数'),
    'capabilities_declared': (44, 'run_gates.EXPECTED.capabilities_declared', '已登记能力数'),
    'properties_files': (25, 'run_gates.EXPECTED.properties_files',
                         'check_properties 扫描文件数（TL-05 不得漂移；'
                         'B17-16 重基线 26→25 = B17-01 删 app/main/sales_routes.py 的后效）'),
    'model_classes': (74, 'run_gates.EXPECTED.model_classes',
                      '模型类数（TL-05 不得漂移）'),
    'migration_revisions': (35, 'run_gates.EXPECTED.migration_revisions', '迁移修订数'),
    'routes_get_no_arg': (104, 'run_gates.EXPECTED.routes_get_no_arg', '无参 GET 规则数'),
    'routes_get_with_arg': (56, 'run_gates.EXPECTED.routes_get_with_arg', '带参 GET 规则数'),
    'routes_non_get': (112, 'run_gates.EXPECTED.routes_non_get', '非 GET 规则数'),
    'functional_passed': (127, 'run_gates.EXPECTED.functional_passed', 'functional_test 通过数'),
    'gh_workflow_lines': (161, '.github/workflows/docker-deploy.yml splitlines() 行数',
                          'GH 工作流行数（28 §5-4：行数用 splitlines）'),
}

#: 作废口径值（G-14 / A-25 / A-31 / A-2）
RETIRED = (
    {'id': 'ge135', 'regex': r'[≥>=]{1,2}\s*135(?![0-9])',
     'why': '`≥135`：写端点无命中计数（A-31 已更正为 `≥141`）'},
    {'id': 'ge139', 'regex': r'[≥>=]{1,2}\s*139(?![0-9])',
     'why': '`≥139`：写端点无命中计数（同上，已作废）'},
    {'id': 'get160', 'regex': r'(?<![0-9])160(?![0-9])',
     'why': '`160`：方法级 GET（A-25 已更正为 161）',
     'context': r'(路由|规则|端点|方法级|GET|覆盖|断言|routes?|rules?|table|表)'},
    {'id': 'tables45', 'regex': r'(?<![0-9])45\s*张',
     'why': '「45 张」：零行表（A-2 已更正为 49 张）'},
)

#: 撤回/引用标记：同行出现即视为「在说明该值已作废」，放行
EXEMPT_MARKERS = ('作废', '不得出现', '禁止', '已更正', '更正', '前稿', '推翻', '❌',
                  '反例', '错例', 'retired', '口径注记', '已改')

#: 声明但未安装于 canonical env 的包 → 依赖钉版校验里降级为 WARN（不阻塞）
#: `pywin32`（B17-16）：win32 专有依赖，Linux 构建镜像装不上；`Dockerfile:44-56` 已在构建期
#: 过滤并明令「不改 lock 本体」，而写进 lock 头会被下一次 `--write-lock` 抹掉 ⇒ 走本表，
#: `requirements.lock` 保持字节不变（`git status --porcelain requirements.lock` 为空是硬判据）。
DEFAULT_ENV_EXCEPTIONS = ('psycopg2-binary', 'pywin32')

#: 未安装于本环境的**声明**依赖 → 生成 lock 时的版本兜底（来源：`pip download --no-deps`）
PYPI_FALLBACK = {'psycopg2-binary': '2.9.12'}

CALIBER_BLOCK_RE = re.compile(r'<!--\s*caliber-table(.*?)-->', re.S)
CALIBER_LINE_RE = re.compile(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*[:=]\s*([^\s#]+)\s*$')
EXC_RE = re.compile(r'^#\s*env-exceptions:\s*(.*)$', re.M)
REQ_SHA_RE = re.compile(r'^#\s*requirements\.txt sha256:\s*([0-9A-Fa-f]{64})\s*$', re.M)
PIN_RE = re.compile(r'^\s*([A-Za-z0-9._-]+)\s*==\s*([^\s;]+)\s*(;\s*.+)?$')


def _rel(path):
    try:
        return os.path.relpath(path, REPO_ROOT).replace('\\', '/')
    except ValueError:
        return path


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest().upper()


def _literal_assign(path, name):
    """读 Python 源码里 `name = <字面量>`（只 ast，不导入）。"""
    with open(path, encoding='utf-8') as fh:
        tree = ast.parse(fh.read(), filename=path)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == name:
                    try:
                        return ast.literal_eval(node.value)
                    except ValueError:
                        return None
    return None


# ------------------------------------------------------------------ 权威源复核
def read_sources(coverage_path=None):
    """实读全部权威源；返回 (values, errors)。缺失/不可解析 ⇒ errors。

    coverage 面：默认读归档锚点 ``COVERAGE_JSON``；**本 run 的产物必须用 ``--coverage``
    显式传入**（A-89/A-114 挂点与产物分离：默认路径是历史冻结锚点，不得被原地覆盖写）。
    产物缺失 ⇒ hard fail（不静默降级），并打印 `COVERAGE_ANCHOR_READINGS` 留档读数。
    """
    vals, errors = {}, []
    cov = coverage_path or COVERAGE_JSON
    if os.path.isfile(cov):
        try:
            with open(cov, encoding='utf-8') as fh:
                doc = json.load(fh)
            s = doc.get('summary') or {}
            for k in ('rules_total', 'method_level_GET', 'method_level_non_get_total',
                      'writable_rules_non_get', 'writable_any_covered_by_all',
                      'writable_literal_covered_by_all'):
                if k in s:
                    vals[k] = s[k]
            vals['uncovered_writable_rules'] = len(doc.get('uncovered_writable') or [])
            plan = doc.get('smoke_test_plan') or {}
            vals['smoke_targets'] = plan.get('static_reproduction_targets')
            vals['smoke_unresolved'] = plan.get('static_reproduction_unresolved')
            vals['_coverage_sha256'] = sha256_file(cov)
            vals['_coverage_bytes'] = os.path.getsize(cov)
            vals['_coverage_path'] = _rel(cov)
        except Exception as e:
            errors.append('coverage.json 不可解析：%s: %s' % (type(e).__name__, e))
    else:
        errors.append('权威源缺失：%s（coverage 判据输入；本 run 产物请 `--coverage <path>` '
                      '显式传入）' % _rel(cov))
        errors.append('锚点留档读数（%s，sha256 %s…）：%s'
                      % (COVERAGE_ANCHOR_READINGS['anchor'],
                         COVERAGE_ANCHOR_READINGS['sha256'][:12],
                         '、'.join('%s=%s' % kv
                                   for kv in sorted(COVERAGE_ANCHOR_READINGS['values'].items()))))
    if os.path.isfile(RUN_GATES):
        exp = _literal_assign(RUN_GATES, 'EXPECTED')
        if isinstance(exp, dict):
            for k in ('templates_files', 'capabilities_declared', 'properties_files',
                      'model_classes', 'migration_revisions', 'routes_get_no_arg',
                      'routes_get_with_arg', 'routes_non_get', 'functional_passed',
                      'routes_total_rules'):
                if k in exp:
                    vals['rules_total' if k == 'routes_total_rules' else k] = exp[k]
        else:
            errors.append('run_gates.EXPECTED 不可解析')
    else:
        errors.append('权威源缺失：%s' % _rel(RUN_GATES))
    if os.path.isfile(COVERAGE_DRIFT):
        locked = _literal_assign(COVERAGE_DRIFT, 'LOCKED')
        if isinstance(locked, dict):
            for k, v in locked.items():
                if isinstance(v, (tuple, list)) and len(v) == 2:
                    vals['_locked_%s' % k] = v[1]
            vals['_locked_uncovered_writable_rules'] = _literal_assign(
                COVERAGE_DRIFT, 'UNCOVERED_WRITABLE_MAX')
        else:
            errors.append('coverage_drift.LOCKED 不可解析')
    else:
        errors.append('权威源缺失：%s' % _rel(COVERAGE_DRIFT))
    if os.path.isfile(GH_WORKFLOW):
        with open(GH_WORKFLOW, encoding='utf-8', errors='replace') as fh:
            vals['gh_workflow_lines'] = len(fh.read().splitlines())
    else:
        errors.append('权威源缺失：%s' % _rel(GH_WORKFLOW))
    # 派生值
    if (isinstance(vals.get('method_level_non_get_total'), int)
            and isinstance(vals.get('writable_any_covered_by_all'), int)):
        vals['non_get_uncovered_method_level'] = (vals['method_level_non_get_total']
                                                 - vals['writable_any_covered_by_all'])
    return vals, errors


def verify_sources(coverage_path=None):
    """钉常量 vs 权威源：返回 (checks, errors)。任一不等 ⇒ 该键 violation（口径源已漂移）。"""
    vals, errors = read_sources(coverage_path)
    checks = []
    for key, (value, source, note) in sorted(PINNED.items()):
        got = vals.get(key)
        ok = (got == value)
        checks.append({'key': key, 'pinned': value, 'source_value': got, 'ok': ok,
                       'source': source, 'note': note})
    return checks, errors


# ------------------------------------------------------------------ 文档检查
def parse_caliber_blocks(text):
    """返回 (declared, problems)：declared = {key: value}。"""
    declared = {}
    problems = []
    for block in CALIBER_BLOCK_RE.findall(text):
        for raw in block.splitlines():
            line = raw.strip()
            if not line or line.startswith('#'):
                continue
            m = CALIBER_LINE_RE.match(line)
            if not m:
                problems.append('口径表行无法解析：%r' % line[:80])
                continue
            key, val = m.group(1), m.group(2)
            if key in declared and str(declared[key]) != val:
                problems.append('口径键重复且取值不一致：%s=%s vs %s'
                                % (key, declared[key], val))
            declared[key] = val
    return declared, problems


def check_doc(path, require_caliber=False):
    """检查一份文档：返回 (violations, warnings, info)。"""
    violations, warnings = [], []
    with open(path, encoding='utf-8', errors='replace') as fh:
        text = fh.read()
    lines = text.splitlines()
    declared, problems = parse_caliber_blocks(text)
    for p in problems:
        violations.append('%s：%s' % (_rel(path), p))
    if require_caliber and not declared:
        violations.append('%s：缺少口径表（<!-- caliber-table ... -->，--require-caliber 要求）'
                          % _rel(path))
    for key, val in sorted(declared.items()):
        if key not in PINNED:
            violations.append('%s：口径键未登记：%s=%s（用 --list-constants 查已登记键）'
                              % (_rel(path), key, val))
            continue
        want = PINNED[key][0]
        if str(want) != str(val):
            violations.append('%s：口径值漂移：%s=%s（钉常量 %s；源：%s）'
                              % (_rel(path), key, val, want, PINNED[key][1]))
    # 作废口径值（逐行，带撤回标记豁免；数字类值还要求**就近**出现度量语境词）
    for i, line in enumerate(lines, 1):
        if any(mk in line for mk in EXEMPT_MARKERS):
            continue
        for rule in RETIRED:
            for m in re.finditer(rule['regex'], line):
                if rule.get('context'):
                    win = line[max(0, m.start() - 12):m.end() + 12]
                    if not re.search(rule['context'], win):
                        continue
                violations.append('%s:%d：出现作废口径值 %s —— %s'
                                  % (_rel(path), i, rule['id'], rule['why']))
                break
    return violations, warnings, {'caliber_keys': len(declared), 'lines': len(lines)}


# ------------------------------------------------------------------ 依赖钉版（TL-07）
def parse_declared(requirements_path):
    out = []
    with open(requirements_path, encoding='utf-8') as fh:
        for ln in fh.read().splitlines():
            s = ln.strip()
            if not s or s.startswith('#'):
                continue
            out.append(s)
    return out


def parse_lock(lock_path):
    """解析 lock：返回 (pins, sha, exceptions, problems)。"""
    pins, sha, exceptions, problems = {}, None, set(DEFAULT_ENV_EXCEPTIONS), []
    with open(lock_path, encoding='utf-8') as fh:
        text = fh.read()
    m = REQ_SHA_RE.search(text)
    if m:
        sha = m.group(1).upper()
    m = EXC_RE.search(text)
    if m:
        for tok in re.split(r'[,\s]+', m.group(1).strip()):
            tok = tok.strip()
            if tok:
                exceptions.add(re.split(r'\s+#', tok)[0].strip())
    for i, raw in enumerate(text.splitlines(), 1):
        s = re.sub(r'\s+#\s.*$', '', raw).strip()     # 去掉行尾 `# via x` 注释
        if not s or s.startswith('#'):
            continue
        m = PIN_RE.match(s)
        if not m:
            problems.append('lock:%d 非精确钉版（要求 name==version）：%s' % (i, raw.strip()[:80]))
            continue
        pins[m.group(1)] = m.group(2)
    return pins, sha, exceptions, problems


def canonical(name):
    return re.sub(r'[-_.]+', '-', name).lower()


def check_lock(lock_path, requirements_path):
    """TL-07 判据层：存在 / 精确钉版 / 与 requirements.txt 一致 / 与当前环境一致。"""
    violations, warnings, info = [], [], {}
    if not os.path.isfile(lock_path):
        violations.append('requirements.lock 不存在：%s（TL-07：删 lock ⇒ 非 0）'
                          % _rel(lock_path))
        return violations, warnings, info
    if not os.path.isfile(requirements_path):
        violations.append('requirements.txt 不存在：%s' % _rel(requirements_path))
        return violations, warnings, info
    pins, sha, exceptions, problems = parse_lock(lock_path)
    violations.extend(problems)
    declared = parse_declared(requirements_path)
    info['lock_pins'] = len(pins)
    info['declared'] = len(declared)
    info['required_sha256'] = sha
    info['actual_sha256'] = sha256_file(requirements_path)
    if sha is None:
        violations.append('lock 缺少 `# requirements.txt sha256: <HEX>` 锁头 ⇒ 无法证明与 '
                          'requirements.txt 一致')
    elif sha != info['actual_sha256']:
        violations.append('lock 与 requirements.txt 不一致：锁头 %s… ≠ 实测 %s…'
                          % (sha[:12], info['actual_sha256'][:12]))
    declared_names = set()
    for spec in declared:
        name = re.split(r'[\[<>=!;]', spec, 1)[0].strip()
        declared_names.add(canonical(name))
        if canonical(name) not in {canonical(k) for k in pins}:
            violations.append('声明依赖未进 lock：%s' % name)
    # 环境对拍
    env_ok, env_bad, env_skip = 0, [], []
    for name, ver in sorted(pins.items()):
        if name in exceptions or canonical(name) in {canonical(e) for e in exceptions}:
            env_skip.append('%s==%s' % (name, ver))
            continue
        try:
            installed = md.version(name)
        except md.PackageNotFoundError:
            env_bad.append('%s==%s（未安装）' % (name, ver))
            continue
        if canonical(installed) == canonical(ver) or installed == ver:
            env_ok += 1
        else:
            env_bad.append('%s==%s（环境 %s）' % (name, ver, installed))
    info['env_ok'] = env_ok
    info['env_exceptions'] = env_skip
    info['env_mismatch'] = env_bad
    if env_bad:
        violations.append('lock 与当前环境不一致：%s' % '；'.join(env_bad[:6]))
    for s in env_skip:
        warnings.append('env-exception（按 lock 安装才满足）：%s' % s)
    return violations, warnings, info


def build_lock_content(requirements_path):
    """按 requirements.txt 生成「精确 == + 传递闭包」的 lock 文本。"""
    from packaging.requirements import Requirement
    from packaging.markers import default_environment
    try:
        from packaging.utils import canonicalize_name
    except Exception:                                     # pragma: no cover
        canonicalize_name = canonical

    installed = {}
    for dist in md.distributions():
        name = dist.metadata['Name']
        if name:
            installed[canonicalize_name(name)] = dist
    env = default_environment()
    resolved, queue, seen = {}, [], set()
    for spec in parse_declared(requirements_path):
        r = Requirement(spec)
        queue.append((canonicalize_name(r.name), r.marker, 'declared'))
    while queue:
        key, marker, parent = queue.pop(0)
        if marker is not None and not marker.evaluate(env):
            continue
        if key in seen:
            continue
        seen.add(key)
        dist = installed.get(key)
        if dist is None:
            resolved[key] = (PYPI_FALLBACK.get(key), parent)
            continue
        resolved[key] = (dist.version, parent)
        for reqline in (dist.requires or []):
            try:
                rr = Requirement(reqline)
            except Exception:
                continue
            if rr.marker is not None and not rr.marker.evaluate(env):
                continue
            queue.append((canonicalize_name(rr.name), None, key))
    exceptions = sorted(k for k, (v, _p) in resolved.items()
                        if k in [canonical(e) for e in DEFAULT_ENV_EXCEPTIONS])
    header = [
        '# requirements.lock — TL-07 依赖可复现钉版（全部 `==` 精确钉版 + 传递闭包）',
        '# 生成工具：python -B scripts/check_doc_claims.py --write-lock（勿手改）',
        '# 生成时点：%s (+08:00)' % time.strftime('%Y-%m-%d %H:%M:%S'),
        '# 解释器：%s' % sys.executable,
        '# 平台：%s / Python %s' % (sys.platform, platform.python_version()),
        '# 口径：requirements.txt 的全部声明 + importlib.metadata 递归（packaging 标记求值）；',
        '#       标记在**本平台**求值 ⇒ 本 lock 是平台相关件（Windows 交付/CI 用）。',
        '# requirements.txt sha256: %s' % sha256_file(requirements_path),
        '# env-exceptions: %s' % (', '.join(exceptions) if exceptions else '(none)'),
        '# 说明：`env-exceptions` 列出的包未安装于 canonical env（本机 SQLite-only 运行），',
        '#       按本 lock 安装后即满足；其版本来源：`pip download --no-deps` 实测。',
        '',
    ]
    body = []
    for name in sorted(resolved):
        ver, parent = resolved[name]
        note = ''
        if ver is None:
            note = '  # 版本未解析（未安装且无 PyPI 兜底）'
            ver = '0.0.0-UNRESOLVED'
        elif parent != 'declared':
            note = '  # via %s' % parent
        body.append('%s==%s%s' % (name, ver, note))
    return '\n'.join(header + body) + '\n'


# ------------------------------------------------------------------ 自检
def selftest(lock_path=DEFAULT_LOCK, requirements_path=DEFAULT_REQUIREMENTS):
    base = os.path.join(REPORTS_ROOT, '.tmp', 'r2t13-selftest')
    os.makedirs(base, exist_ok=True)

    def write(name, text):
        safe = re.sub(r'[^0-9A-Za-z_.-]+', '_', name)[:60]
        if not safe.endswith(('.md', '.lock')):
            safe += '.md'
        p = os.path.join(base, safe)
        with open(p, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(text)
        return p

    good_block = '\n'.join('%s = %s' % (k, v[0]) for k, v in sorted(PINNED.items()))
    cases = []

    def doc_case(name, text, expect, require_caliber=False):
        p = write('doc_' + name, text)
        v, _w, _i = check_doc(p, require_caliber=require_caliber)
        got = 'fail' if v else 'pass'
        cases.append((name, expect, got, v[:1]))
        return p
    doc_case('DC-P1 正确口径表 + 干净正文', '<!-- caliber-table\n%s\n-->\n\n正文。\n' % good_block,
             'pass')
    doc_case('DC-N1 出现 ≥135', '<!-- caliber-table\n%s\n-->\n\n覆盖 ≥135 条。\n' % good_block,
             'fail')
    doc_case('DC-N2 出现方法级 160（度量语境）',
             '<!-- caliber-table\n%s\n-->\n\n方法级 GET 160 条。\n' % good_block, 'fail')
    doc_case('DC-N3 出现「45 张」',
             '<!-- caliber-table\n%s\n-->\n\n零行表 45 张。\n' % good_block, 'fail')
    doc_case('DC-N4 口径表值写错（rules_total=270）',
             '<!-- caliber-table\n%s\nrules_total = 270\n-->\n\n正文。\n' % good_block, 'fail')
    doc_case('DC-N5 口径键未登记（foo=1）',
             '<!-- caliber-table\n%s\nfoo = 1\n-->\n\n正文。\n' % good_block, 'fail')
    doc_case('DC-N6 误报对照：1600 / 160 元 / 无度量语境的 160',
             '<!-- caliber-table\n%s\n-->\n\n金额 1600 元；备件 160 件已入库；编号 160。\n'
             % good_block, 'pass')
    doc_case('DC-N7 撤回标记对照：前稿 ≥135 已更正为 ≥141',
             '<!-- caliber-table\n%s\n-->\n\n前稿 ≥135 已更正为 ≥141。\n' % good_block, 'pass')
    doc_case('DC-N8 --require-caliber 且无口径表', '正文，无口径表。\n', 'fail', True)
    p_n8 = doc_case('DC-N8b 无口径表但不要求', '正文，无口径表。\n', 'pass', False)
    cases.append(('DC-N8-b 同形态文档不带 --require-caliber ⇒ 放行', 'pass',
                  'pass' if not check_doc(p_n8)[0] else 'fail', None))

    # ---- lock 四类
    v, w, i = check_lock(lock_path, requirements_path)
    cases.append(('DC-L1 真实 lock + requirements ⇒ 通过', 'pass',
                  'pass' if not v else 'fail', v[:1]))
    v2, _w, _i = check_lock(os.path.join(base, 'no_such.lock'), requirements_path)
    cases.append(('DC-L2 lock 缺失 ⇒ 违规（TL-07：删 lock ⇒ 非 0）', 'fail',
                  'fail' if v2 else 'pass', v2[:1]))
    if os.path.isfile(lock_path):
        with open(lock_path, encoding='utf-8') as fh:
            real = fh.read()
        bad_sha = real.replace(REQ_SHA_RE.search(real).group(1), '0' * 64)
        p = write('lock_bad_sha.lock', bad_sha)
        v3, _w, _i = check_lock(p, requirements_path)
        cases.append(('DC-L3 lock 与 requirements.txt 不一致 ⇒ 违规', 'fail',
                      'fail' if v3 else 'pass', v3[:1]))
        loose = re.sub(r'^([A-Za-z0-9._-]+)==([^\s]+)', r'\1>=\2', real, count=1, flags=re.M)
        p2 = write('lock_loose.lock', loose)
        v4, _w, _i = check_lock(p2, requirements_path)
        cases.append(('DC-L4 非精确钉版（>=）⇒ 违规', 'fail',
                      'fail' if v4 else 'pass', v4[:1]))
        mismatch = re.sub(r'^([A-Za-z0-9._-]+)==([^\s]+)', r'\1==0.0.1', real, count=1, flags=re.M)
        p3 = write('lock_env_mismatch.lock', mismatch)
        v5, _w, _i = check_lock(p3, requirements_path)
        cases.append(('DC-L5 lock 与当前环境不一致 ⇒ 违规', 'fail',
                      'fail' if v5 else 'pass', v5[:1]))

    ok_all, n_ok = True, 0
    for name, expect, got, detail in cases:
        ok = got == expect
        ok_all = ok_all and ok
        n_ok += 1 if ok else 0
        print('  [%s] %s（期望 %s，实测 %s）%s'
              % ('PASS' if ok else 'FAIL', name, expect, got,
                 '' if ok else '  <- %s' % (detail,)))
    print('[check_doc_claims] 自检 %d/%d 通过' % (n_ok, len(cases)))
    print('[check_doc_claims] 自检夹具目录：%s' % _rel(base))
    return 0 if ok_all else 1


# ------------------------------------------------------------------ main
def main(argv=None):
    ap = argparse.ArgumentParser(description='TL-06 口径守卫 + TL-07 依赖钉版一致性')
    ap.add_argument('--docs', nargs='*', default=None,
                    help='要检查的文档（支持 glob；缺省 = %s）' % ' '.join(DEFAULT_DOC_GLOBS))
    ap.add_argument('--require-caliber', action='store_true',
                    help='被扫文档必须带口径表（用于最终报告）')
    ap.add_argument('--lock', default=DEFAULT_LOCK)
    ap.add_argument('--requirements', default=DEFAULT_REQUIREMENTS)
    ap.add_argument('--check-sources', action='store_true', default=True,
                    help='钉常量 vs 权威源逐条复核（默认开）')
    ap.add_argument('--no-check-sources', dest='check_sources', action='store_false')
    ap.add_argument('--skip-lock', action='store_true', help='只跑口径面')
    ap.add_argument('--coverage', default=None,
                    help='coverage.json 判据输入（缺省 = 归档锚点；本 run 产物请显式传入）')
    ap.add_argument('--list-constants', action='store_true')
    ap.add_argument('--write-lock', action='store_true', help='生成/刷新 requirements.lock')
    ap.add_argument('--selftest', action='store_true')
    ap.add_argument('--json', action='store_true', help='stdout 末尾追加机读 JSON')
    args = ap.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors='replace')
        except Exception:
            pass

    if args.selftest:
        return selftest(args.lock, args.requirements)

    if args.list_constants:
        checks, errors = verify_sources(args.coverage)
        print('[check_doc_claims] 口径键登记表（%d 条；权威源逐条实读复核）' % len(PINNED))
        for c in checks:
            print('  %-32s 钉值=%-8s 源值=%-8s %s  %s'
                  % (c['key'], c['pinned'], c['source_value'],
                     'OK ' if c['ok'] else 'DRIFT', c['source']))
        for e in errors:
            print('  !! %s' % e)
        return 0 if all(c['ok'] for c in checks) and not errors else 1

    if args.write_lock:
        text = build_lock_content(args.requirements)
        old = ''
        if os.path.isfile(args.lock):
            with open(args.lock, encoding='utf-8') as fh:
                old = fh.read()
        with open(args.lock, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(text)
        pins = len([l for l in text.splitlines() if l and not l.startswith('#')])
        print('[check_doc_claims] 已写入 %s：%d 条精确钉版（原 %d 行 → 新 %d 行）'
              % (_rel(args.lock), pins, len(old.splitlines()), len(text.splitlines())))
        return 0

    violations, warnings, info = [], [], {}
    # ① 钉常量 vs 权威源
    if args.check_sources:
        checks, errors = verify_sources(args.coverage)
        info['pinned_checks'] = len(checks)
        info['pinned_ok'] = sum(1 for c in checks if c['ok'])
        for e in errors:
            violations.append('权威源错误：%s' % e)
        for c in checks:
            if not c['ok']:
                violations.append('口径源漂移：%s 钉值 %s ≠ 源值 %s（源：%s）'
                                  % (c['key'], c['pinned'], c['source_value'], c['source']))
        print('[check_doc_claims] 钉常量 vs 权威源：%d/%d 相等'
              % (info['pinned_ok'], info['pinned_checks']))
    # ② 文档
    patterns = args.docs if args.docs else list(DEFAULT_DOC_GLOBS)
    files = []
    for pat in patterns:
        p = pat if os.path.isabs(pat) else os.path.join(REPO_ROOT, pat)
        files.extend(sorted(glob.glob(p)))
    files = sorted({os.path.abspath(p) for p in files if os.path.isfile(p)})
    info['docs_scanned'] = len(files)
    info['caliber_tables'] = 0
    for p in files:
        v, w, i = check_doc(p, require_caliber=args.require_caliber)
        violations.extend(v)
        warnings.extend(w)
        info['caliber_tables'] += 1 if i['caliber_keys'] else 0
    print('[check_doc_claims] 文档：扫描 %d 份、带口径表 %d 份%s'
          % (len(files), info['caliber_tables'],
             '（--require-caliber 生效）' if args.require_caliber else ''))
    # ③ 依赖钉版
    if not args.skip_lock:
        v, w, i = check_lock(args.lock, args.requirements)
        violations.extend(v)
        warnings.extend(w)
        info['lock'] = i
        if i:
            print('[check_doc_claims] lock：%s 条钉版 / 环境匹配 %s 条 / exception %s 条'
                  % (i.get('lock_pins'), i.get('env_ok'), len(i.get('env_exceptions') or [])))
    for w in warnings:
        print('[check_doc_claims] [WARN] %s' % w)
    for v in violations:
        print('[check_doc_claims] [VIOLATION] %s' % v)
    code = 1 if violations else 0
    print('[check_doc_claims] RESULT: %s（violations=%d）' % ('FAIL' if code else 'OK',
                                                             len(violations)))
    if args.json:
        print('[check_doc_claims] __JSON__' + json.dumps(
            {'violations': violations, 'warnings': warnings, 'info': info, 'code': code},
            ensure_ascii=False))
    return code


if __name__ == '__main__':
    sys.exit(main())
