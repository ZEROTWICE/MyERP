"""ci_lint.py — E-04：CI 配置的静态校验（语法有效 + 不引用不存在的脚本）。

对应 `21-E04精确修法与验收判据.md` §4 的 **E-04-c**（语法有效）与 **E-04-d**（路径存在）。

**校验内容**

| 项 | 手段 |
| --- | --- |
| workflow YAML 语法 | 若 `yaml` 可导入 ⇒ **`yaml.safe_load`** 真解析 + 结构断言；否则退化为**子集 lint**（缩进/制表符/关键键/结构标记），并在输出里如实标注用的是哪一种 |
| workflow 结构 | `jobs.gate` 存在、`gate` 步骤调用 `ci_gates.py`；第一阶段 `build-and-push` 无 `needs: gate` 且 `gate` 为 `continue-on-error: true`（第二阶段相反） |
| `Jenkinsfile` 语法 | 结构化 lint：括号/引号配平、声明式必需块（`pipeline`/`agent`/`stages`/`post`）、`stage(...)` 清单、无制表符；**本机无 Groovy/JVM ⇒ 无法做真正的 Pipeline 解析，此限制如实登记** |
| `Jenkinsfile` 门禁 stage | 含 `ci_gates.py`、`--phase`、`--json`、绝对路径解释器变量 `PY_EXE`；第一阶段为 `UNSTABLE` 且第二阶段 `error(...)` 以**注释**形式在旁（或已启用） |
| E-04-d 路径 | 从 Jenkinsfile / workflow / `ci_gates.py` 的步骤表里抽取**仓库相对路径**，逐个 `isfile` 校验（跳过 `F:\\Miniconda\\…` 这类机器绝对路径）；并校验 `--no-dump` 已由 t4 的脚本提供 |

用法（仓库根目录）：

    python -B test-reports-2026-10/harness/ci_lint.py [--phase first|second] [--json OUT]
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPORTS_ROOT = os.path.dirname(HERE)
REPO_ROOT = os.path.dirname(REPORTS_ROOT)

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors='replace')
    except Exception:
        pass

WORKFLOW = os.path.join(REPO_ROOT, '.github', 'workflows', 'docker-deploy.yml')
JENKINSFILE = os.path.join(REPO_ROOT, 'Jenkinsfile')
CI_GATES = os.path.join(HERE, 'ci_gates.py')

REPO_PATH_RX = re.compile(r'(?<![\w:/\\])((?:scripts|test-reports-2026-10|harness)/[A-Za-z0-9_./-]+\.(?:py|json|yml|txt))')
#: 清单里允许出现的仓库相对脚本（E-04-d 的判据口径）
REQUIRED_PATHS = [
    'scripts/check_templates.py', 'scripts/check_migration_heads.py',
    'scripts/check_properties.py', 'scripts/check_db_bootstrap.py',
    'scripts/functional_test.py', 'scripts/permission_matrix.py',
    'scripts/smoke_test.py', 'scripts/route_inventory.py', 'scripts/_sandbox_compat.py',
    'test-reports-2026-10/harness/run_gates.py',
    'test-reports-2026-10/harness/measure_coverage.py',
    'test-reports-2026-10/harness/coverage_drift.py',
    'test-reports-2026-10/harness/ci_gates.py',
]


def check_balance(text):
    """括号/引号配平（忽略 // 注释与 ' " ''' 字符串），返回 (ok, detail)。"""
    stack = []
    pairs = {')': '(', ']': '[', '}': '{'}
    i, n = 0, len(text)
    line = 1
    state = None            # None | "'" | '"' | '"""' | "'''" | 'line-comment' | 'block-comment'
    while i < n:
        ch = text[i]
        nxt3 = text[i:i + 3]
        if ch == '\n':
            line += 1
            if state in ("'", '"', 'line-comment'):
                if state == 'line-comment':
                    state = None
        if state == 'line-comment':
            i += 1
            continue
        if state == 'block-comment':
            if text[i:i + 2] == '*/':
                state = None
                i += 2
                continue
            i += 1
            continue
        if state in ("'", '"'):
            if ch == '\\':
                i += 2
                continue
            if ch == state:
                state = None
            i += 1
            continue
        if state in ('"""', "'''"):
            if nxt3 == state:
                state = None
                i += 3
                continue
            i += 1
            continue
        if text[i:i + 2] == '//':
            state = 'line-comment'
            i += 2
            continue
        if text[i:i + 2] == '/*':
            state = 'block-comment'
            i += 2
            continue
        if nxt3 in ('"""', "'''"):
            state = nxt3
            i += 3
            continue
        if ch in ("'", '"'):
            state = ch
            i += 1
            continue
        if ch in '([{':
            stack.append((ch, line))
        elif ch in ')]}':
            if not stack or stack[-1][0] != pairs[ch]:
                return False, f'第 {line} 行出现不配对的 {ch!r}'
            stack.pop()
        i += 1
    if state in ('"""', "'''"):
        return False, f'字符串 {state} 未闭合'
    if stack:
        return False, '括号未闭合：' + ', '.join('%s@%d' % (c, l) for c, l in stack[:5])
    return True, '括号/引号配平'


def subset_yaml_lint(path):
    """无 PyYAML 时的兜底：缩进/制表符/关键键/结构标记的子集校验。"""
    text = open(path, encoding='utf-8').read()
    problems = []
    if '\t' in text:
        problems.append('文件含制表符（YAML 禁止）')
    if not text.endswith('\n'):
        problems.append('文件末尾缺少换行')
    for key in ('name:', 'on:', 'jobs:'):
        if not re.search(r'^%s' % re.escape(key), text, re.M):
            problems.append('缺少顶层键 %s' % key)
    for job in ('build-and-push:', 'gate:'):
        if not re.search(r'^  %s' % re.escape(job), text, re.M):
            problems.append('缺少 job %s' % job)
    for m in re.finditer(r'^( +)\S', text, re.M):
        if len(m.group(1)) % 2:
            problems.append('第 %d 行缩进为奇数' % (text[:m.start()].count('\n') + 1))
            break
    # 结构标记：steps 列表项与映射键的缩进关系（本文件固定 2 空格步进）
    if not re.search(r'^      - (uses|name|run):', text, re.M):
        problems.append('steps 列表项缩进不符合预期（期望 6 空格 + "- "）')
    return (not problems), problems


def lint_workflow(phase):
    checks = []
    text = open(WORKFLOW, encoding='utf-8').read()
    validator = 'subset-lint'
    doc = None
    try:
        import yaml                                    # noqa: F401
        doc = yaml.safe_load(text)
        validator = 'yaml.safe_load (PyYAML %s)' % yaml.__version__
    except ImportError:
        validator = 'subset-lint（本机未安装 PyYAML，A-6 环境事实）'

    def add(cid, desc, ok, detail=''):
        checks.append({'id': cid, 'desc': desc, 'status': 'passed' if ok else 'failed',
                       'detail': detail})

    if doc is not None:
        jobs = doc.get('jobs') or {}
        gate = jobs.get('gate') or {}
        build = jobs.get('build-and-push') or {}
        steps = gate.get('steps') or []
        run_text = '\n'.join(str(s.get('run', '')) for s in steps if isinstance(s, dict))
        # PyYAML 按 YAML 1.1 把顶层键 `on` 解析成布尔 True
        triggers = doc.get('on', doc.get(True))
        add('L-W1', 'yaml.safe_load 解析成功且含 name/on/jobs',
            bool(doc.get('name') and triggers and jobs), 'jobs=%s' % list(jobs))
        add('L-W2', 'gate job 调用 ci_gates.py', 'ci_gates.py' in run_text,
            'run=%r' % run_text[:160])
        add('L-W3', 'gate job 上传 ci_gates.json 产物',
            any('upload-artifact' in str(s.get('uses', '')) for s in steps if isinstance(s, dict)),
            'steps=%d' % len(steps))
        if phase == 'first':
            add('L-W4', '第一阶段：build-and-push 无 needs（gate 不阻塞发布）',
                'needs' not in build, 'needs=%r' % build.get('needs'))
            add('L-W5', '第一阶段：gate 为 continue-on-error: true（report-only）',
                gate.get('continue-on-error') is True,
                'continue-on-error=%r' % gate.get('continue-on-error'))
        else:
            add('L-W4', '第二阶段：build-and-push needs gate',
                build.get('needs') == 'gate', 'needs=%r' % build.get('needs'))
            add('L-W5', '第二阶段：gate 不 continue-on-error',
                not gate.get('continue-on-error'),
                'continue-on-error=%r' % gate.get('continue-on-error'))
    else:
        ok, problems = subset_yaml_lint(WORKFLOW)
        add('L-W1', '子集 lint（无 PyYAML 兜底）', ok, '; '.join(problems) or 'ok')
        add('L-W2', 'gate job 调用 ci_gates.py', 'ci_gates.py' in text, '')
        add('L-W3', 'gate job 上传 ci_gates.json 产物', 'upload-artifact' in text, '')
        if phase == 'first':
            add('L-W4', '第一阶段：build-and-push 无 needs',
                not re.search(r'^  build-and-push:[\s\S]{0,400}?^    needs:', text, re.M), '')
            add('L-W5', '第一阶段：gate 为 continue-on-error: true',
                bool(re.search(r'^  gate:[\s\S]{0,400}?continue-on-error: true', text, re.M)), '')
        else:
            add('L-W4', '第二阶段：build-and-push needs gate',
                bool(re.search(r'^  build-and-push:[\s\S]{0,400}?^    needs: gate', text, re.M)), '')
            add('L-W5', '第二阶段：gate 不 continue-on-error',
                not re.search(r'^  gate:[\s\S]{0,400}?continue-on-error: true', text, re.M), '')
    return checks, validator


def lint_jenkinsfile(phase):
    checks = []
    text = open(JENKINSFILE, encoding='utf-8').read()

    def add(cid, desc, ok, detail=''):
        checks.append({'id': cid, 'desc': desc, 'status': 'passed' if ok else 'failed',
                       'detail': detail})

    ok, detail = check_balance(text)
    add('L-J1', '括号/引号/注释配平（结构化 lint）', ok, detail)
    add('L-J2', '声明式必需块齐备（pipeline/agent/stages/post）',
        all(k in text for k in ('pipeline {', 'agent {', 'stages {', 'post {')),
        '')
    add('L-J3', '无制表符', '\t' not in text, '')
    stages = re.findall(r"stage\('([^']+)'\)", text)
    add('L-J4', '存在 E-04 门禁 stage', any('E-04' in s for s in stages), 'stages=%s' % stages)
    add('L-J5', '解释器变量 PY_EXE 已声明且为绝对路径',
        bool(re.search(r"PY_EXE\s*=\s*'[A-Za-z]:\\\\", text)), '')

    e04 = ''
    m = re.search(r"stage\('([^']*E-04[^']*)'\)\s*\{([\s\S]*?)\n        \}", text)
    if m:
        e04 = m.group(2)
    add('L-J6', 'E-04 stage 调用 ci_gates.py 且带 --phase/--json',
        'ci_gates.py' in e04 and '--phase' in e04 and '--json' in e04, 'len(e04)=%d' % len(e04))
    add('L-J7', 'E-04 stage 使用绝对路径解释器（A-7）',
        '"${PY_EXE}"' in e04 or '${PY_EXE}' in e04, '')
    add('L-J8', 'E-04 stage 解释评分支（0/1/2）并归档 JSON',
        'ciRc' in e04 and 'archiveArtifacts' in e04, '')
    if phase == 'first':
        add('L-J9', '第一阶段：blocking 失败记 UNSTABLE 且 error() 在注释中（第二阶段启用位）',
            "currentBuild.result = 'UNSTABLE'" in e04
            and re.search(r'//\s*error\(', e04) is not None, '')
    else:
        add('L-J9', '第二阶段：blocking 失败即 error()（阻塞构建）',
            re.search(r'^\s*error\(', e04, re.M) is not None, '')
    add('L-J10', 'E-04 stage 不写仓库根 JSON（A-11）',
        not any(x in e04 for x in ('_smoke_results.json', '_permission_matrix.json')), '')
    return checks


def strip_comments(path):
    """去掉注释行后返回正文（路径抽取只看「真引用」；预留接入位的注释不算引用）。"""
    keep = []
    for line in open(path, encoding='utf-8').read().splitlines():
        s = line.strip()
        if s.startswith('#') or s.startswith('//') or s.startswith('*'):
            continue
        keep.append(line)
    return '\n'.join(keep)


def lint_paths():
    checks = []

    def add(cid, desc, ok, detail=''):
        checks.append({'id': cid, 'desc': desc, 'status': 'passed' if ok else 'failed',
                       'detail': detail})

    missing = [p for p in REQUIRED_PATHS if not os.path.isfile(os.path.join(REPO_ROOT, p))]
    add('L-P1', '清单里每个仓库相对脚本都存在（%d 个）' % len(REQUIRED_PATHS),
        not missing, '缺失=%s' % (missing or '无'))

    # 从三处配置里抽出的相对路径也必须存在（**注释行不计**：ci_gates 里的 W7 预留接入位是注释）
    found = set()
    for path in (WORKFLOW, JENKINSFILE, CI_GATES):
        found |= set(REPO_PATH_RX.findall(strip_comments(path)))
    bad = sorted(p for p in found if not os.path.isfile(os.path.join(REPO_ROOT, p)))
    add('L-P2', '三处配置真引用的相对路径都存在（%d 个）' % len(found), not bad,
        '缺失=%s' % (bad or '无'))
    src_lines = open(CI_GATES, encoding='utf-8').read().splitlines()
    reserved = [p for p in ('check_model_refs', 'check_http_contract')
                if any(('#' in ln and p in ln) for ln in src_lines)]
    add('L-P4', '预留接入位（W7：check_model_refs/check_http_contract）以注释形式登记在 ci_gates.py',
        len(reserved) == 2, 'found=%s' % reserved)

    # --no-dump 必须已由 t4 交付（E-04-d 的下半句）
    nd = {}
    for name in ('permission_matrix.py', 'smoke_test.py'):
        src = open(os.path.join(REPO_ROOT, 'scripts', name), encoding='utf-8').read()
        nd[name] = "'--no-dump'" in src
    add('L-P3', 't4 已提供 --no-dump（permission_matrix / smoke_test）', all(nd.values()),
        str(nd))
    return checks


def main(argv=None):
    ap = argparse.ArgumentParser(description='E-04：CI 配置静态校验（E-04-c / E-04-d）')
    ap.add_argument('--phase', default='first', choices=('first', 'second'))
    ap.add_argument('--json', default=None)
    args = ap.parse_args(argv)

    checks = []
    wf_checks, validator = lint_workflow(args.phase)
    checks += wf_checks + lint_jenkinsfile(args.phase) + lint_paths()
    failed = [c for c in checks if c['status'] == 'failed']
    code = 1 if failed else 0

    print('[ci_lint] workflow = %s' % os.path.relpath(WORKFLOW, REPO_ROOT).replace('\\', '/'))
    print('[ci_lint] YAML 校验手段 = %s' % validator)
    print('[ci_lint] Jenkinsfile = %s（本机无 Groovy/JVM => 结构化 lint；真解析限制已登记）'
          % os.path.relpath(JENKINSFILE, REPO_ROOT).replace('\\', '/'))
    for c in checks:
        print('  [%s] %s %s%s' % ('OK  ' if c['status'] == 'passed' else 'FAIL', c['id'], c['desc'],
                                  ('  -- ' + c['detail']) if c['detail'] else ''))
    print('[ci_lint] 判定 = %s（%d/%d 项通过）' % ('OK' if code == 0 else 'FAIL',
                                                 len(checks) - len(failed), len(checks)))
    print('[ci_lint] exit_code_semantics=' + json.dumps({
        'script': 'test-reports-2026-10/harness/ci_lint.py',
        'rule': 'all checks passed -> exit 0; any failed -> exit 1',
        'inputs': {'failed_checks': [c['id'] for c in failed], 'phase': args.phase,
                   'yaml_validator': validator},
        'code': code,
    }, ensure_ascii=False))
    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
        with open(args.json, 'w', encoding='utf-8', newline='\n') as fh:
            json.dump({'phase': args.phase, 'yaml_validator': validator, 'checks': checks,
                       'exit_code': code}, fh, ensure_ascii=False, indent=2)
        print('[ci_lint] JSON -> %s' % args.json)
    return code


if __name__ == '__main__':
    sys.exit(main())
