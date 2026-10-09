"""reconcile_r2.py — 第2轮 t1：`07` 的 38 条待办 × 实际代码/仓库状态 逐条对账 + 阶段A终态冻结（**只读**）。

## 性质与纪律
* **只读**：不 import 应用、不调 `create_app()`、不打开任何数据库（真实库只做 SHA256/字节/mtime 指纹）、
  不发 HTTP 请求、不重跑任何会产生 evidence 的脚本（A-40）。允许的子进程只有**纯静态**门禁（AST/stdout，零落盘）。
* **每条对账显式声明搜索域**（A-71）：`search_domain` 写明「哪些目录/文件、搜文件名还是搜文件内容」。
* **自指性假阳性防护**（captain 第 2 次反馈 §三.1）：判据脚本**不得**把「自己」与「同为核验工具的脚本」当资产证据。
  见 `EXCLUDE_PATTERNS`（按**族**排除，因 captain 会在会话中新增核验脚本）；交付文档必须列出实际被排除的文件与理由。`evidence/**` 是**度量产物/冻结基线**，
  不作为「新增用例」的证据。
* **`evidence_kind` 四值**：`file_exists` / `content_mention` / `content_implementation` / `behavior_verified`。
  **只有 `content_implementation` / `behavior_verified` 才够 HIT**；`content_mention` 一律 PARTIAL/NOT_DONE。
* **判定口径（captain §四）**：「如果把这些工作删掉，会有什么测试变红？」答不出 ⇒ NOT_DONE。
* 行数一律 Python `splitlines()`（A-23）；计数一律「工具 + 口径 + 值」；哈希大写（A-51，比对大小写不敏感）。
* 编码：本机 stdout 为 GBK ⇒ 自身 `reconfigure(utf-8)`，print 行 **ASCII 安全**（`=>` 而非 `⇒`）。
* 落盘：`evidence/harness/<RUN_ID>/`（E-01 守卫：目标已存在则改名保留，绝不覆盖）。

## 判定值域
`HIT`（有实现/行为证据且全部子项通过）· `PARTIAL`（有实现证据但子项未全通过，或**前提部分成立**）·
`NOT_DONE`（零实现证据：只有提及/声明/度量输出，或什么都没有）· `MISS`（探测本身失效，无法判定）。
`VERDICT_OVERRIDE` 只用于「自动引擎口径不足、需人工按 A-23 口径修正」的少数条目，
每条必须带 `reason` + **可复算命令**；`verdict_auto` 始终保留在机读里，不隐藏。

## 用法
    F:\\Miniconda\\envs\\wage\\python.exe -B test-reports-2026-10/harness/reconcile_r2.py
    ... --no-gates                 # 跳过子进程门禁
    ... --json <path>              # 额外落一份机读摘要（同一守卫语义）

退出码：0 = 本脚本自身执行成功（**0 不代表「38 条都已做」**，结论见各条 verdict）。
"""
import argparse
import ast
import builtins
import hashlib
import json
import os
import re
import subprocess
import sys
import time

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
REPORTS = os.path.dirname(HERE)
REPO = os.path.dirname(REPORTS)
PY = r'F:\Miniconda\envs\wage\python.exe'

SKIP_DIRS = {'.git', '__pycache__', '.tmp', 'node_modules', '.venv', 'venv'}

#: 自指性假阳性防护（captain 第 2 次反馈 §三.1 + 28-第2轮执行纪律 §2.1）：这些**不是被测资产**。
#: 按**族**排除（captain 会在会话中新增核验脚本 ⇒ 不能靠固定文件名清单）。
EXCLUDE_PATTERNS = {
    'reconcile_r2.py': 't1 本任务的搜索脚本自身（自指）——运行期再按 __file__ 兜底',
    'captain_r2_*.py': 'captain 的核验/对账脚本**族**（正文含 38 条条目名与判据正则 ⇒ 必然自命中）',
    'improve_plan.py': 't7 的清单生成器（38 条条目名的来源）',
    'analysis_ledger.py': 't6 的账本生成器（「描述工作」而非「验证工作」）',
}
_SELF_BASENAME = os.path.basename(os.path.abspath(__file__))


def is_excluded_name(fn):
    import fnmatch
    if fn == _SELF_BASENAME:
        return True
    return any(fnmatch.fnmatch(fn, pat) for pat in EXCLUDE_PATTERNS)

#: 唯一允许的额外写盘：TL-05 的**行为探针**源码（落在 .tmp/<RUN_ID>/，gitignored）。
#: 用途：用「注入实例属性误用 ⇒ 门禁是否变红」证明 TL-05 的盲区是否真的存在（28-第2轮执行纪律 §3）。
PROBE_RUN_ID = os.environ.get('HARNESS_RUN_ID') or 'r2t1-reconcile'
PROBE_DIR_REL = 'test-reports-2026-10/.tmp/%s/tl05probe' % PROBE_RUN_ID
PROBE_SRC = ('class Employee:\n'
             '    pass\n'
             '\n'
             '\n'
             'def f():\n'
             '    e = Employee()\n'
             '    return e.not_a_column\n')


def ensure_tl05_probe():
    """写探针源码（不含 BOM —— BOM 会让 ast.parse 报 SyntaxError，制造假红）。"""
    d = os.path.join(REPO, PROBE_DIR_REL.replace('/', os.sep))
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, 'probe.py')
    with open(p, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(PROBE_SRC)
    return PROBE_DIR_REL

REAL_DB = os.path.join(REPO, 'app.db')
#: RF-1（2026-10-09，批次15 I1，用户拍板）：真库锚点重基线。本处读**现场**真库（`real_db_fp()`
#: 的 `equals_frozen`，见 :814 / :1014），旧值不随前移即报 equals_frozen=False。
REAL_DB_SHA = 'B4FB980C5D1B25B3C3A0EADC12ECF01C75B36EBD213B109E5DD190C617EEAABE'
PHASE_A_FIRST_COMMIT = '590b688'          # 26-阶段A收口报告 §3.2：590b688 起为阶段A 提交序列

#: 自动引擎口径不足时的显式修正（stricter-or-equal，且必须可复算）
VERDICT_OVERRIDE = {
    'P-09': {
        'verdict': 'PARTIAL',
        'reason': ('404 吞 500 的**吞咽面**已全清（doc 口径 17->0、全 app 404 维 0 处、w4_probe 18/18 均 404），'
                   '但 P-09-a 第 2 款「404 必须是 JSON 载体」在其自己的残留项上未满足：'
                   'R1/R6 的 GET 404 仍返回 HTML（26-阶段A收口报告 §5.3 第 7 项「残留 + 需口径裁定」）'),
        'command': r'python -B test-reports-2026-10/harness/w4_http_contract.py --scope doc --expect 0'
                   r'  # 吞咽面=0；载体面见 26-阶段A收口报告.md §5.3-7'},
    'C-06': {
        'verdict': 'PARTIAL',
        'reason': ('C-06 的**前提本身已过时**（07 写「既无权限断言也无可达性命中」，但可达性命中早已存在）⇒ '
                   '「可达性」面成立、「权限断言」面无判据 ⇒ 按 captain 独立读数判 PARTIAL；'
                   '自动引擎给 NOT_DONE 是因为「C-06 自己的新增用例 = 0」——两种口径都在机读里保留'),
        'command': r'grep -n "purchase_orders/save" test-reports-2026-10/harness/write_suite.py'
                   r' ; grep -n "/shipments/create" test-reports-2026-10/harness/uat_chains.py'},
    'C-10': {
        'verdict': 'PARTIAL',
        'reason': ('幂等面成立（夹具库按 `<RUN_ID>` 命名、每 run 独立副本）；记账面未做'
                   '（既有 `fixtures_manifest` 只是 RAW 键、非台账产物；T-04 的 internal_number RUN_ID 后缀未加）'),
        'command': r'grep -n "RUN_ID" test-reports-2026-10/harness/fixtures.py'
                   r' ; grep -n "internal_number=" test-reports-2026-10/harness/fixtures.py'
                   r' ; ls test-reports-2026-10/**/fixtures_manifest*.json  # 不存在'},
}

#: captain 在 `evidence/captain-verification/r2-baseline-anchors.md` 的独立读数（交叉核对用）
CAPTAIN_ANCHORS = {
    'test-reports-2026-10/evidence/uat/uat_chains.json': (33318, '360A8570BC0080A2984A59AD945B2C837AD96ACF7B55E6242AE7E2C6417DD23A'),
    'test-reports-2026-10/evidence/harness/negative_matrix.json': (24424, 'B743C73F86F5EB5C0FBA38410119D8D3A6BDE5FBACDF214CFA0DB409EF5B7479'),
    'test-reports-2026-10/evidence/analysis/assertion_ledger.json': (60937, 'C7C312734DD8E02486D26C3639D8D074CCFCD59BCEB002C13C7CC9587AC94092'),
    'test-reports-2026-10/evidence/api/write_suite.json': (73293, 'B608117EBDCA2A6F74595F0DB4A010187D8834715CD5E70D5C1AAD85F4A3F403'),
    'test-reports-2026-10/evidence/harness/coverage.json': (236893, '5E2C9D4315971B31C83AFD7833C310501199C34F61BFD868EF07A6AEEF7BF1F0'),
    'test-reports-2026-10/evidence/api/api_matrix.json': (1342834, '8451BB6738CCB25C41794E7B9548969D0EDDC8FE6EAE855DCC5F1D1CC746CB86'),
    'test-reports-2026-10/26-阶段A收口-复核读数.json': (11994, 'CF0E2B14581D82072E087617B0CE3DBC1F4676897787DB6B14D6C6FA43D37319'),
    'test-reports-2026-10/evidence/harness/t9-rega-final/ledger.json': (None, None),   # captain 记「缺失」
}


# --------------------------------------------------------------------------- 基础工具
def rel(p):
    return os.path.relpath(p, REPO).replace('\\', '/')


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest().upper()


def file_fp(path):
    p = os.path.join(REPO, path) if not os.path.isabs(path) else path
    if not os.path.exists(p):
        return {'path': rel(p), 'exists': False}
    st = os.stat(p)
    with open(p, 'rb') as fh:
        raw = fh.read()
    text = raw.decode('utf-8', errors='replace')
    return {'path': rel(p), 'exists': True, 'bytes': st.st_size,
            'lines': len(text.splitlines()),
            'nonblank': len([x for x in text.splitlines() if x.strip()]),
            'sha256': hashlib.sha256(raw).hexdigest().upper(),
            'mtime': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(st.st_mtime))}


def walk_files(root, exts=('.py',), skip_self=True):
    base = os.path.join(REPO, root)
    out = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in sorted(filenames):
            if exts and not fn.endswith(tuple(exts)):
                continue
            if skip_self and is_excluded_name(fn):
                continue
            out.append(os.path.join(dirpath, fn))
    return out


def read_text(path):
    with open(path, 'rb') as fh:
        return fh.read().decode('utf-8', errors='replace')


def content_hits(target, regex, exts=('.py',), limit=12, skip_self=True):
    p = os.path.join(REPO, target)
    files = [p] if os.path.isfile(p) else walk_files(target, exts, skip_self=skip_self)
    rx = re.compile(regex)
    hits = []
    for f in files:
        try:
            lines = read_text(f).splitlines()
        except OSError:
            continue
        for i, ln in enumerate(lines, 1):
            if rx.search(ln):
                hits.append({'file': rel(f), 'line': i, 'text': ln.strip()[:160]})
                if len(hits) >= limit:
                    return hits
    return hits


def glob_targets(pattern):
    import fnmatch
    out = []
    pat = pattern.replace('\\', '/')
    if '**' in pat:
        prefix = pat.split('**')[0].rstrip('/')
        tail = pat.split('**', 1)[1].lstrip('/')
    else:
        prefix, tail = os.path.dirname(pat), os.path.basename(pat)
    base = os.path.join(REPO, prefix) if prefix else REPO
    if not os.path.isdir(base):
        return out
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if is_excluded_name(fn):
                continue
            if fnmatch.fnmatch(fn, tail or '*'):
                out.append(rel(os.path.join(dirpath, fn)))
    return out


# --------------------------------------------------------------------------- 检查原语
def chk_content(file, regex, label=None, expect=True, kind='content_implementation', pre=False):
    hits = content_hits(file, regex)
    ok = bool(hits) is expect
    return {'kind': 'content', 'evidence_kind': kind, 'pre_existing': pre,
            'target': file, 'regex': regex, 'label': label,
            'expect': 'hit' if expect else 'absent', 'ok': ok,
            'hits': hits[:3], 'hit_count': len(hits)}


def chk_tree(root, regex, exts=('.py',), expect=True, label=None,
             kind='content_implementation', pre=False):
    hits = content_hits(root, regex, exts=exts)
    ok = bool(hits) is expect
    return {'kind': 'tree_content', 'evidence_kind': kind, 'pre_existing': pre,
            'target': root, 'exts': list(exts), 'regex': regex, 'label': label,
            'expect': 'hit' if expect else 'absent', 'ok': ok,
            'hits': hits[:3], 'hit_count': len(hits)}


def chk_file(path, label=None, expect=True, pre=False):
    p = os.path.join(REPO, path)
    exists = os.path.exists(p) and os.path.isfile(p)
    ok = exists is expect
    return {'kind': 'file_exists', 'evidence_kind': 'file_exists', 'pre_existing': pre,
            'target': path, 'label': label, 'expect': 'exists' if expect else 'absent',
            'ok': ok,
            'hits': ([{'file': path, 'line': None, 'text': 'bytes=%d' % os.path.getsize(p)}]
                     if exists else [])}


def chk_glob(pattern, label=None, expect=True, pre=False):
    got = glob_targets(pattern)
    ok = bool(got) is expect
    return {'kind': 'glob_exists', 'evidence_kind': 'file_exists', 'pre_existing': pre,
            'target': pattern, 'label': label, 'expect': 'exists' if expect else 'absent',
            'ok': ok, 'hits': [{'file': g, 'line': None, 'text': ''} for g in got[:3]],
            'hit_count': len(got)}


def chk_subprocess(argv, label=None, expect_exit=0, kind='behavior_verified', pre=False):
    env = dict(os.environ)
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUTF8'] = '1'
    try:
        pr = subprocess.run(argv, cwd=REPO, env=env, capture_output=True)
        code = pr.returncode
        out = (pr.stdout or b'').decode('utf-8', errors='replace')
        err = (pr.stderr or b'').decode('utf-8', errors='replace')
    except OSError as e:
        code, out, err = None, '', 'OSError: %s' % e
    tail = [l.strip() for l in out.strip().splitlines() if l.strip()][-4:]
    ok = None if code is None else (code == expect_exit)
    return {'kind': 'subprocess', 'evidence_kind': kind, 'pre_existing': pre,
            'target': ' '.join(['python'] + argv[1:]), 'label': label,
            'expect': 'exit %s' % expect_exit, 'ok': ok, 'cmd': argv,
            'exit_code': code, 'hits': [{'file': '', 'line': None, 'text': t} for t in tail],
            'stderr_tail': err.strip().splitlines()[-2:]}


# ---- 复用已验收的 404 吞 500 判据（harness/w4_http_contract.py，AST，零落盘），不另造口径
_W4 = {}


def w4_site_counts():
    if 'v' in _W4:
        return _W4['v']
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    import w4_http_contract as w4
    full = w4.scan(['app'], scope=None)
    doc = w4.scan(['app'], scope='doc')
    c404 = [s for s in full if any(p in ('get_or_404', 'first_or_404') for p in s['patterns'])]
    cjson = [s for s in full if 'get_json()' in s['patterns']]
    _W4['v'] = {'tool': 'harness/w4_http_contract.py::scan（AST，try 块 × 处理器不重抛）',
                'sites_total': len(full), 'sites_doc_scope': len(doc),
                'sites_404_dimension': len(c404), 'sites_getjson_dimension': len(cjson),
                'site_404_list': [{'file': s['file'], 'line': s['line'], 'func': s['func']}
                                  for s in c404],
                'site_getjson_list': [{'file': s['file'], 'line': s['line'], 'func': s['func']}
                                      for s in cjson]}
    return _W4['v']


def chk_w4(key, label, expect=0):
    got = w4_site_counts()[key]
    ok = got == expect
    return {'kind': 'w4_site_count', 'evidence_kind': 'behavior_verified', 'pre_existing': False,
            'target': 'harness/w4_http_contract.py::scan(app)', 'label': label,
            'expect': '== %s' % expect, 'ok': ok, 'hits': [], 'value': got}


# --------------------------------------------------------------------------- 38 条待办
ENV = 'test-reports-2026-10/harness/_env.py'
W4C = 'test-reports-2026-10/harness/w4_http_contract.py'
CI_G = 'test-reports-2026-10/harness/ci_gates.py'
WS = 'test-reports-2026-10/harness/write_suite.py'
UAT = 'test-reports-2026-10/harness/uat_chains.py'
FIX = 'test-reports-2026-10/harness/fixtures.py'
COVERAGE_DRIFT = 'test-reports-2026-10/harness/coverage_drift.py'


def run_coverage_artifact():
    """B17-11 / A-114：`coverage_drift.py` 必须显式 `--coverage <run 产物>`。

    缺参 = **exit 2（用法错误，不是回归）**：`--coverage` 的 `default` 是冻结锚点
    （`evidence/harness/coverage.json`，与 `LOCKED 108/116/0` 语义互斥）。
    取值顺序：`HARNESS_COVERAGE` 环境变量 → `evidence/harness/*/coverage.json` 中 mtime 最新者
    → 不可变归档快照 `ci-run-20261009-054416/coverage.json`（A-114：不读 live 路径）。
    """
    explicit = os.environ.get('HARNESS_COVERAGE')
    if explicit:
        return explicit
    base = os.path.join(REPORTS, 'evidence', 'harness')
    cands = []
    for name in (sorted(os.listdir(base)) if os.path.isdir(base) else []):
        p = os.path.join(base, name, 'coverage.json')
        if os.path.isfile(p):
            cands.append((os.path.getmtime(p), p))
    if cands:
        return max(cands)[1]
    return os.path.join(base, 'ci-run-20261009-054416', 'coverage.json')


ITEM_CHECKS = [
    # ============================== W0 可信度前置（captain 已复核 HIT）
    ('E-01', 'W0',
     '文件名(递归): test-reports-2026-10/harness/*.py 找 evidence_hash.py；'
     '文件内容: harness/_env.py；文件名(递归): evidence/**/evidence_journal.jsonl',
     [chk_content(ENV, r'EVIDENCE_DIR = os\.path\.join\(EVIDENCE_ROOT, RUN_ID\)', 'run_id 分目录'),
      chk_content(ENV, r'def guard_write\(', '写前守卫'),
      chk_content(ENV, r'def _append_journal\(', '只追加台账'),
      chk_content(ENV, r'def save_evidence\(', 'save_evidence'),
      chk_file('test-reports-2026-10/harness/evidence_hash.py', '哈希基线脚本'),
      chk_glob('test-reports-2026-10/evidence/**/evidence_journal.jsonl', '台账已产生')]),

    ('E-02', 'W0', '文件内容: harness/run_gates.py',
     [chk_content('test-reports-2026-10/harness/run_gates.py',
                  r'exit_reasons\.append\(f"probe_unexpected=', 'probe_unexpected 入退出码'),
      chk_content('test-reports-2026-10/harness/run_gates.py', r'injections_errored', 'EXC 单列'),
      chk_content('test-reports-2026-10/harness/run_gates.py',
                  r"'sensitivity_ok': summary\[.sensitivity_ok.\]", '敏感性进语义块')]),

    ('E-03', 'W0',
     '文件内容: scripts/permission_matrix.py, scripts/smoke_test.py, scripts/route_inventory.py',
     [chk_content('scripts/permission_matrix.py', r'code = 1 if anon_open else 0', '伪门禁失败出口'),
      chk_content('scripts/permission_matrix.py', r'\[FAIL\] 匿名可访问视图', '失败文案'),
      chk_content('scripts/permission_matrix.py', r"\.tmp' / run_id\(\)", '.tmp/<RUN_ID> 落点'),
      chk_content('scripts/smoke_test.py', r'--no-dump', 'smoke --no-dump'),
      chk_content('scripts/smoke_test.py', r'不影响退出码', '落盘失败不影响退出码'),
      chk_content('scripts/route_inventory.py', r'^\s*return 0', '报告型保持恒 0')]),

    ('E-04', 'W0',
     '文件内容: Jenkinsfile, .github/workflows/docker-deploy.yml；文件名: harness/ci_gates.py, ci_lint.py',
     [chk_content('Jenkinsfile', r"stage\('门禁检查\(E-04\)'\)", 'Jenkins stage'),
      chk_content('Jenkinsfile', r'ci_gates\.py --phase first', 'Jenkins 调用入口'),
      chk_content('.github/workflows/docker-deploy.yml', r'^\s*gate:', 'GH gate job'),
      chk_content('.github/workflows/docker-deploy.yml', r'continue-on-error: true', '第一阶段 report-only'),
      chk_file('test-reports-2026-10/harness/ci_gates.py', 'CI 等价入口'),
      chk_file('test-reports-2026-10/harness/ci_lint.py', 'CI 配置自检')]),

    ('E-05', 'W0',
     '文件内容: harness/_env.py；文件内容: docs/test-reports/2026-10/07-实测Runbook与台账规范.md',
     [chk_content(ENV, r"PY_EXE = r'F:\\Miniconda\\envs\\wage\\python\.exe'", '绝对解释器'),
      chk_content(ENV, r'def interpreter\(\)', 'interpreter()'),
      chk_content(ENV, r"env\['PYTHONIOENCODING'\] = 'utf-8'", '子进程编码'),
      chk_content(ENV, r"env\['PYTHONUTF8'\] = '1'", 'PYTHONUTF8'),
      chk_content(ENV, r"'evidence_level': level", 'evidence_level'),
      chk_content('docs/test-reports/2026-10/07-实测Runbook与台账规范.md', r'_sandbox_compat',
                  'runbook shim 纪律')]),

    # ============================== W1 blocker
    ('P-01', 'W1', '文件内容: app/main/routes.py（第 6 行模块级 import）',
     [chk_content('app/main/routes.py', r'^from app\.models import .*\bConsumable\b', '模块级导入 Consumable'),
      chk_content('app/main/routes.py', r'\bConsumableCategory\b', '同批 ConsumableCategory'),
      chk_content('app/main/routes.py', r'def delete_consumable\(', 'delete_consumable'),
      chk_content('app/main/routes.py', r'def use_consumable\(', 'use_consumable'),
      chk_subprocess([PY, '-B', 'scripts/check_model_refs.py'], 'check_model_refs violations=0')]),

    # ============================== W2 质检闭环
    ('DEC-1', 'W2',
     '文件内容: 07b（判定表）+ **harness/w2w3_probe.py**（acceptance_matrix 机读）；'
     '（预检误判 PARTIAL 之因：搜索域只写 evidence/harness，漏搜 harness/ —— A-71 同类）',
     [chk_content('test-reports-2026-10/07b-DEC-1-DEC-2-业务口径决策单.md', r'N1', '判定表 N1'),
      chk_content('test-reports-2026-10/07b-DEC-1-DEC-2-业务口径决策单.md', r'F3', '判定表 F3'),
      chk_tree('test-reports-2026-10/harness', r'acceptance_matrix', exts=('.py', '.json'),
               label='acceptance_matrix 机读')]),

    ('P-03', 'W2', '文件内容: app/services/mes_service.py',
     [chk_content('app/services/mes_service.py', r'def recompute_production_quality_status\(', '回写函数'),
      chk_content('app/services/mes_service.py', r'batch_item\.quality_status = value', '字段写入点'),
      chk_content('app/services/mes_service.py', r'def apply_production_record_result\(', '报工结果入口')]),

    ('P-07', 'W2', '文件内容: app/services/mes_service.py（门禁顺序/复位路径）',
     [chk_content('app/services/mes_service.py', r'def qc_gate_allows_output\(', '门禁函数'),
      chk_content('app/services/mes_service.py', r'def reset_quality_status_after_disposal\(', '自动复位'),
      chk_content('app/services/mes_service.py', r'scrapped', 'scrapped 语义')]),

    ('P-02', 'W2', '文件内容: app/services/mes_service.py（production_record 分支）',
     [chk_content('app/services/mes_service.py', r"target_type='production_record'", '报工维度 NC'),
      chk_content('app/services/mes_service.py', r'def create_inspection_task\(', 'NC 构造点')]),

    # ============================== W3 金额与料账
    ('DEC-2', 'W3', '文件内容: 07b（R1/R2 口径裁决）',
     [chk_content('test-reports-2026-10/07b-DEC-1-DEC-2-业务口径决策单.md', r'R1', '返工识别 R1'),
      chk_content('test-reports-2026-10/07b-DEC-1-DEC-2-业务口径决策单.md', r'is_rework', '未采用新增列')]),

    ('P-04', 'W3', '文件内容: app/services/mes_service.py + app/models.py',
     [chk_content('app/services/mes_service.py',
                  r"SystemConfig\.get\('quality\.rework_counts_piecework'", '唯一读取点'),
      chk_content('app/services/mes_service.py', r'def rework_counts_piecework\(\)', '共享口径函数'),
      chk_content('app/models.py', r'rework_counts_piecework', 'S2 同口径')]),

    ('P-05', 'W3', '文件内容: app/services/mes_service.py',
     [chk_content('app/services/mes_service.py', r'def rework_quantity_for\(', '件数取值'),
      chk_content('app/services/mes_service.py', r'explicit', '显式参数优先')]),

    ('P-06', 'W3', '文件内容: app/services/mes_service.py + app/main/stock.py',
     [chk_content('app/services/mes_service.py', r'def scrap_material_plan\(', '逐料计划'),
      chk_content('app/services/mes_service.py', r'def deduct_scrap_materials\(', '逐料扣减'),
      chk_content('app/main/stock.py', r'scrap_quantity', 'stock 入参')]),

    # ============================== W4 异常出口
    ('P-09', 'W4',
     '文件内容: app/__init__.py + 三模块 _reraise_http；'
     '行为: harness/w4_http_contract.py::scan（doc 口径与 **404 维全量**）',
     [chk_content('app/__init__.py', r'@app\.errorhandler\(HTTPException\)', '统一 handler'),
      chk_content('app/main/quality.py', r'_reraise_http', 'quality 助手'),
      chk_content('app/main/production_center.py', r'_reraise_http', 'production_center 助手'),
      chk_w4('sites_doc_scope', 'doc 口径站点（P-09-c 的 17 处）== 0', 0),
      chk_w4('sites_404_dimension', '全 app 的 404 维站点 == 0', 0),
      chk_subprocess([PY, '-B', W4C, '--scope', 'doc', '--expect', '0'],
                     'w4_http_contract doc 口径 exit 0'),
      chk_subprocess([PY, '-B', W4C, '--selftest'], '判据自检（阴性用例非恒真）')]),

    ('P-12', 'W4',
     '文件内容: app/main/quality.py（显式 400）+ app/__init__.py（handler）；'
     '行为: w4_http_contract get_json 维站点数',
     [chk_content('app/main/quality.py', r'请求数据为空', '显式 400 文案'),
      chk_content('app/__init__.py', r'HTTPException', '统一 handler 兜 415'),
      chk_w4('sites_getjson_dimension', 'get_json 维站点（静态修复面）== 0', 0)]),

    ('P-11', 'W4', '文件内容: 三模块（详情进 logger，正文脱敏）',
     [chk_content('app/main/quality.py', r'current_app\.logger\.(error|exception|warning)', 'quality logger'),
      chk_content('app/main/routes.py', r'current_app\.logger\.(error|exception|warning)', 'routes logger'),
      chk_content('app/main/production_center.py', r'current_app\.logger\.(error|exception|warning)',
                  'production_center logger')]),

    ('P-10', 'W4', '文件内容: app/main/quality.py 拒删守卫',
     [chk_content('app/main/quality.py', r'拒删', '拒删守卫'),
      chk_content('app/main/quality.py', r'inspection_records', '关联记录检查')]),

    # ============================== W5 契约与静默成功
    ('P-08', 'W5', '文件内容: app/main/routes.py edit_task',
     [chk_content('app/main/routes.py', r"task\.notes = data\.get\('notes'", 'notes 真写')]),

    ('P-13', 'W5', '文件名+内容: 24-W4载体登记册.json',
     [chk_file('test-reports-2026-10/24-W4载体登记册.json', '载体登记册'),
      chk_content('test-reports-2026-10/24-W4载体登记册.json', r'"', '登记册内容可解析')]),

    # ============================== W6 覆盖补强（口径：删掉这些工作，哪个测试会变红？）
    ('C-01', 'W6',
     '文件内容: harness/**.py（**排除** reconcile_r2/captain_r2_*/improve_plan）搜 J 域断言构造；'
     '不含 evidence/**（度量产物不算资产）',
     [chk_tree('test-reports-2026-10/harness', r'audit_delta|AuditLog 增量|audit.*increment',
               label='J 域审计增量断言'),
      chk_glob('test-reports-2026-10/harness/j_audit*.py', 'J 域专用 harness'),
      chk_tree('test-reports-2026-10/harness', r'通知.*幂等|重复推送|notification.*idempot',
               label='通知幂等断言')]),

    ('C-02', 'W6', '文件内容: harness/**.py 搜并发用例构造（排除自指脚本）',
     [chk_tree('test-reports-2026-10/harness', r'\bthreading\b|\bThread\(', label='并发用例'),
      chk_glob('test-reports-2026-10/harness/*concurren*.py', '并发专用 harness')]),

    ('C-03', 'W6', '文件内容: harness/**.py + app/**.py 搜 SameSite/token 重放（排除自指脚本）',
     [chk_tree('test-reports-2026-10/harness', r'SameSite|samesite|SESSION_COOKIE|token.*重放',
               label='CSRF 全场景用例'),
      chk_tree('app', r'SameSite|samesite', exts=('.py',), label='应用侧 SameSite')]),

    ('C-04', 'W6',
     '文件内容: harness/**.py 搜链 A / C1C2C4C5 / B0B1B2B6B7 的**新增用例**'
     '（用例总数口径见 payload.uat_baseline_summary，基线 40）',
     [chk_tree('test-reports-2026-10/harness', r'CHAIN_A|chain_a', label='链 A 用例载体'),
      chk_tree('test-reports-2026-10/harness', r'\bB0B1B2B6B7\b', label='链 B 缺口用例')]),

    ('C-05', 'W6',
     '文件名(递归): harness/*.py 找**新增命中补强探针**；覆盖数前后对照见 payload.coverage_artifacts '
     '（`coverage.json` 是**上一轮的度量输出**，不作为「新增覆盖」的证据）',
     [chk_glob('test-reports-2026-10/harness/c05*.py', 'C-05 专用探针'),
      chk_glob('test-reports-2026-10/harness/*hit*.py', '命中补强探针（*hit*.py）'),
      chk_glob('test-reports-2026-10/harness/*endpoint_coverage*.py', '端点覆盖探针')]),

    ('C-06', 'W6',
     '文件内容: harness/write_suite.py + uat_chains.py（**可达性命中**的面）+ harness/*blind*.py（新增用例）',
     [chk_content(WS, r"req\('POST', '/purchase_orders/save'", '写套件已命中 /purchase_orders/save',
                  kind='content_implementation', pre=True),
      chk_content(WS, r"req\('POST', '/equipment/save'", '写套件已命中 /equipment/save',
                  kind='content_implementation', pre=True),
      chk_content(UAT, r'/shipments/create', '端到端已命中 /shipments/create',
                  kind='content_implementation', pre=True),
      chk_glob('test-reports-2026-10/harness/c06*.py', 'C-06 专用探针'),
      chk_glob('test-reports-2026-10/harness/*blind*.py', '盲区探针（*blind*.py）')]),

    ('C-07', 'W6',
     '文件内容: app/**.py（应用级硬闸）+ harness/fixtures.py（夹具正向判据）',
     [chk_tree('app', r'assert_real_db|real_db_guard|拒绝连真实库|is_production_db', exts=('.py',),
               label='应用级硬闸'),
      chk_content(FIX, r'assert.*\.tmp.*run_id|\.tmp.*run_id.*assert', '夹具正向判据（落在 .tmp/<run_id>）')]),

    ('C-08', 'W6',
     '文件名(递归): harness/*.py 找导入容错/导出残留**新增用例**；内容: 排除自指脚本',
     [chk_glob('test-reports-2026-10/harness/*import*.py', '导入容错探针'),
      chk_tree('test-reports-2026-10/harness', r'坏行|行级容错|逐行容错', label='坏行容错用例'),
      chk_tree('test-reports-2026-10/harness', r'残留文件|leftover|temp.*残余', label='导出零残留用例')]),

    ('C-09', 'W6',
     '文件名(递归): harness/*.py 找 GAP-21/GAP-42 判据；内容: 排除自指脚本与 captain 脚本',
     [chk_glob('test-reports-2026-10/harness/*price*.py', '工价版本探针'),
      chk_tree('test-reports-2026-10/harness', r'GAP-21|GAP-42|三策略', label='GAP-21/42 判据')]),

    ('C-10', 'W6',
     '文件内容: harness/fixtures.py（幂等面：RUN_ID 副本命名；记账面：internal_number 后缀 / '
     'fixtures_manifest 台账产物）',
     [chk_content(FIX, r'RUN_ID', '幂等面：夹具库按 <RUN_ID> 命名',
                  kind='content_implementation', pre=True),
      chk_content(FIX, r"internal_number=f'_hvRAW\{i \+ 1\}'",
                  'T-04 未修：料账仍用固定编号（无 RUN_ID/序号后缀）'),
      chk_glob('test-reports-2026-10/**/fixtures_manifest*.json', 'manifest 台账**产物**'),
      chk_content(UAT, r"RAW\['fixtures_manifest'\]", 'manifest 只是 RAW 键（pre-existing）',
                  kind='content_mention', pre=True)]),

    ('C-11', 'W6',
     '文件内容: evidence/analysis/*.json（账本条目，**度量产物不算资产**，此处只用于确认「条目是否登记」）',
     [chk_tree('test-reports-2026-10/evidence/analysis', r'AC-44|AC-45|AC-56', exts=('.json',),
               label='AC-44/45/56 账本条目'),
      chk_tree('test-reports-2026-10/evidence/analysis', r'AC-15|AC-16', exts=('.json',),
               label='AC-15/16 账本条目')]),

    # ============================== W7 工具链
    ('TL-01', 'W7',
     '文件名: scripts/check_model_refs.py；内容: harness/ci_gates.py（接入位是否**取消注释**）',
     [chk_file('scripts/check_model_refs.py', '门禁脚本'),
      chk_subprocess([PY, '-B', 'scripts/check_model_refs.py'], '门禁实跑 exit 0'),
      chk_content(CI_G, r"^\s*\{'id': 'check_model_refs',\s*'group': 'blocking'", '已进 CI 链（启用）')]),

    ('TL-02', 'W7',
     '文件名: scripts/check_http_contract.py（07 的落点）；文件名: harness/w4_http_contract.py（等价实现）；'
     '内容: ci_gates.py 接入位',
     [chk_file('scripts/check_http_contract.py', '07 规定落点'),
      chk_file(W4C, '等价静态实现（harness）'),
      chk_content(W4C, r'HTTP_CALLS = ', '404 站点判据实现'),
      chk_content(CI_G, r"^\s*\{'id': 'check_http_contract',\s*'group': 'blocking'", '已进 CI 链（启用）')]),

    ('TL-03', 'W7',
     '文件名: harness/coverage_drift.py；内容: ci_gates.py 第 11 步（blocking）；行为: 实跑 exit 0',
     [chk_file('test-reports-2026-10/harness/coverage_drift.py', '漂移门禁'),
      chk_content(CI_G, r"'id': 'coverage_drift', 'group': 'blocking'", '已进 blocking'),
      chk_subprocess([PY, '-B', COVERAGE_DRIFT, '--coverage', run_coverage_artifact()],
                     '漂移判据 exit 0（B17-11：显式 --coverage <run 产物>；缺参 = exit 2 用法错误）')]),

    ('TL-04', 'W7',
     '文件名+内容: harness/evidence_hash.py；内容: ci_gates.py 接入位是否启用',
     [chk_file('test-reports-2026-10/harness/evidence_hash.py', '哈希门禁'),
      chk_content('test-reports-2026-10/harness/evidence_hash.py',
                  r"def freeze_target|'--strict-index'|def selftest", '实现（freeze/strict-index/selftest）'),
      chk_content(CI_G, r"^\s*\{'id': 'evidence_hash'", '已进 CI 链（启用）')]),

    ('TL-05', 'W7',
     '文件内容: scripts/check_properties.py（`:32-33` 是**「有意不检查实例属性」的边界声明** ⇒ 恰是 TL-05 要消除的盲区）；'
     '行为: 注入 `e = Employee(); e.not_a_column` 后跑门禁（`.tmp/<RUN_ID>/tl05probe/`，gitignored）——'
     '**TL-05 完成后该注入必须 exit 1**',
     [chk_content('scripts/check_properties.py', r'instance\.property.*无法静态判定', '边界声明（提及）',
                  kind='content_mention'),
      chk_subprocess([PY, '-B', 'scripts/check_properties.py', '--root', ensure_tl05_probe()],
                     '实例属性误用被门禁检出（要求 exit 1）', expect_exit=1)]),

    ('TL-06', 'W7',
     '文件名: scripts/check_doc_claims.py；文件名(递归): harness/*.py 找口径守卫实现（排除自指脚本）',
     [chk_file('scripts/check_doc_claims.py', '07 规定落点'),
      chk_tree('test-reports-2026-10/harness', r'check_doc_claims|口径守卫', label='口径守卫实现'),
      chk_tree('scripts', r'check_doc_claims|口径守卫', label='口径守卫实现')]),

    ('TL-07', 'W7', '文件名: requirements.lock；文件内容: requirements.txt（现状计数）',
     [chk_file('requirements.lock', 'lock 文件'),
      chk_content('requirements.txt', r'==', '唯一的 == 是环境标记（现状）',
                  kind='content_mention', pre=True)]),
]


def merge_item_meta():
    plan = json.load(open(os.path.join(REPORTS, 'evidence', 'improve', 'fix_plan.json'),
                          encoding='utf-8'))
    return {it['id']: it for it in plan['items']}


# --------------------------------------------------------------------------- 独立重算
def get_json_without_silent(roots=('app',)):
    """t7 口径：`get_json()` 调用点未带 `silent=` 关键字（AST，逐调用点）。"""
    sites = []
    for root in roots:
        for f in walk_files(root, ('.py',)):
            try:
                src = read_text(f)
                tree = ast.parse(src)
            except SyntaxError:
                continue
            lines = src.splitlines()
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                fn = node.func
                if isinstance(fn, ast.Attribute) and fn.attr == 'get_json':
                    if 'silent' not in {k.arg for k in node.keywords}:
                        sites.append({'file': rel(f), 'line': node.lineno,
                                      'text': (lines[node.lineno - 1] or '').strip()[:120]})
    return sites


def undefined_model_refs():
    """与 `scripts/check_model_refs.py` 同口径的保守复算（独立实现，用于交叉核对）。"""
    def module_names(tree):
        names = set()
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for a in node.names:
                    names.add((a.asname or a.name).split('.')[0])
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        names.add(t.id)
        return names

    hits = []
    for f in walk_files('app', ('.py',)):
        try:
            src = read_text(f)
            tree = ast.parse(src)
        except SyntaxError:
            continue
        lines = src.splitlines()
        mod = module_names(tree)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            local = set(mod) | {a.arg for a in node.args.args + node.args.kwonlyargs}
            for sub in ast.walk(node):
                if isinstance(sub, (ast.Import, ast.ImportFrom)):
                    for a in sub.names:
                        local.add((a.asname or a.name).split('.')[0])
                if isinstance(sub, ast.Assign):
                    for t in sub.targets:
                        if isinstance(t, ast.Name):
                            local.add(t.id)
                if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) \
                        and sub.func.attr == 'query' and isinstance(sub.func.value, ast.Name):
                    nm = sub.func.value.id
                    if nm[:1].isupper() and nm not in local and nm not in set(dir(builtins)):
                        hits.append({'file': rel(f), 'line': sub.lineno, 'name': nm,
                                     'text': (lines[sub.lineno - 1] or '').strip()[:120]})
    return hits


def coverage_artifacts():
    """列出仓库内全部覆盖率量测产物（排除 .tmp / 自指脚本），给出「前后两个数」的证据。"""
    out = []
    for p in glob_targets('test-reports-2026-10/**/coverage*.json'):
        try:
            d = json.load(open(os.path.join(REPO, p), encoding='utf-8'))
        except Exception:
            continue
        s = d.get('summary') or {}
        if 'writable_literal_covered_by_all' not in s and 'literal_covered' not in s:
            continue
        out.append({'path': p, 'run_id': d.get('run_id'),
                    'mtime': file_fp(p).get('mtime'),
                    'literal_covered': s.get('writable_literal_covered_by_all',
                                             s.get('literal_covered')),
                    'covered_any': s.get('writable_any_covered_by_all', s.get('covered_any')),
                    'uncovered_writable': (len(d.get('uncovered_writable') or [])
                                           or s.get('uncovered_writable')),
                    'method_level_non_get': s.get('method_level_non_get_total'),
                    'probe_files_with_url_sites': [pr.get('file') for pr in (d.get('probes') or [])
                                                   if pr.get('url_call_sites')]})
    return out


def uat_case_total():
    p = os.path.join(REPORTS, 'evidence', 'uat', 'uat_chains.json')
    try:
        return json.load(open(p, encoding='utf-8')).get('summary')
    except Exception as e:
        return {'error': repr(e)}


# --------------------------------------------------------------------------- 冻结
APP_FILES = ['app/main/routes.py', 'app/services/mes_service.py', 'app/main/quality.py',
             'app/__init__.py', 'app/main/production_center.py', 'app/models.py',
             'app/main/stock.py']
SCRIPT_FILES = ['scripts/check_model_refs.py', 'scripts/permission_matrix.py',
                'scripts/smoke_test.py', 'scripts/route_inventory.py',
                'scripts/check_templates.py', 'scripts/check_migration_heads.py',
                'scripts/check_properties.py', 'scripts/check_db_bootstrap.py',
                'requirements.txt', 'Jenkinsfile', '.github/workflows/docker-deploy.yml']
HARNESS_FILES = ['test-reports-2026-10/harness/_env.py',
                 'test-reports-2026-10/harness/run_gates.py',
                 'test-reports-2026-10/harness/ci_gates.py',
                 'test-reports-2026-10/harness/ci_lint.py',
                 'test-reports-2026-10/harness/coverage_drift.py',
                 'test-reports-2026-10/harness/evidence_hash.py',
                 'test-reports-2026-10/harness/regression_preflight.py',
                 'test-reports-2026-10/harness/t9_regression.py',
                 'test-reports-2026-10/harness/t9_ledger.py',
                 'test-reports-2026-10/harness/t9_newfindings_probe.py',
                 'test-reports-2026-10/harness/uat_chains.py',
                 'test-reports-2026-10/harness/negative_matrix.py',
                 'test-reports-2026-10/harness/write_suite.py',
                 'test-reports-2026-10/harness/api_matrix.py',
                 'test-reports-2026-10/harness/measure_coverage.py',
                 'test-reports-2026-10/harness/fixtures.py',
                 'test-reports-2026-10/harness/w1_p01_probe.py',
                 'test-reports-2026-10/harness/w2w3_probe.py',
                 'test-reports-2026-10/harness/w4_probe.py',
                 'test-reports-2026-10/harness/w4_http_contract.py']
BASELINE_FILES = ['test-reports-2026-10/evidence/uat/uat_chains.json',
                  'test-reports-2026-10/evidence/harness/negative_matrix.json',
                  'test-reports-2026-10/evidence/analysis/assertion_ledger.json',
                  'test-reports-2026-10/evidence/api/write_suite.json',
                  'test-reports-2026-10/evidence/api/api_matrix.json',
                  'test-reports-2026-10/evidence/harness/coverage.json',
                  'test-reports-2026-10/evidence/harness/gates.json',
                  'test-reports-2026-10/evidence/improve/fix_plan.json',
                  'test-reports-2026-10/evidence/improve/improve_plan.json',
                  'test-reports-2026-10/26-阶段A收口-复核读数.json',
                  'test-reports-2026-10/evidence/harness/t9-rega-final/t9-regression-ledger.json',
                  'test-reports-2026-10/evidence/harness/t9-rega-final/'
                  't9-regression-ledger.t9-rega-final.json',
                  'test-reports-2026-10/evidence/harness/w2w3-uatdiff-final/uat_chains.before.json',
                  'test-reports-2026-10/evidence/harness/w2w3-uatdiff-final/uat_chains.after.json',
                  'test-reports-2026-10/07-测试与工程改进报告.md',
                  'test-reports-2026-10/26-阶段A收口报告.md',
                  'test-reports-2026-10/26-修复后回归与断言账本.md',
                  'test-reports-2026-10/00b-裁定与纪律增补.md',
                  'test-reports-2026-10/07b-DEC-1-DEC-2-业务口径决策单.md',
                  'test-reports-2026-10/24-W4载体登记册.json']


def git(args):
    try:
        pr = subprocess.run(['git'] + args, cwd=REPO, capture_output=True)
        return (pr.stdout or b'').decode('utf-8', errors='replace').strip()
    except OSError:
        return ''


def git_changed_files():
    span = '%s^..HEAD' % PHASE_A_FIRST_COMMIT
    added = [l for l in git(['log', '--diff-filter=A', '--name-only', '--format=', span]
                            ).splitlines() if l.strip()]
    allf = [l for l in git(['log', '--name-only', '--format=', span]).splitlines() if l.strip()]
    return {'added': sorted(set(added)),
            'added_harness_or_scripts': sorted(set(f for f in added
                                                   if f.startswith(('test-reports', 'scripts')))),
            'changed_total': sorted(set(allf))}


def freeze_block():
    head = git(['rev-parse', 'HEAD'])
    commits = [l for l in git(['log', '--format=%H|%ad|%s', '--date=iso',
                               '%s^..HEAD' % PHASE_A_FIRST_COMMIT]).splitlines() if l.strip()]
    status = [l for l in git(['status', '--porcelain']).splitlines() if l.strip()]
    return {
        'head': head, 'head_short': head[:7],
        'app_tree_sha1': git(['rev-parse', 'HEAD:app']),
        'phase_a_commit_span': '%s..HEAD' % PHASE_A_FIRST_COMMIT,
        'phase_a_commits': commits, 'phase_a_commit_count': len(commits),
        'worktree_status_rows': status,
        'worktree_dirty_paths': [l[3:] for l in status],
        'app_tree_clean_vs_head': not [l for l in status if l[3:].startswith('app/')],
        'tags': [t for t in git(['tag']).splitlines() if t.strip()],
        'app_files': [file_fp(f) for f in APP_FILES],
        'script_config_files': [file_fp(f) for f in SCRIPT_FILES],
        'harness_files': [file_fp(f) for f in HARNESS_FILES],
        'baseline_anchors': [file_fp(f) for f in BASELINE_FILES],
        'harness_py_total': len(glob_targets('test-reports-2026-10/harness/*.py')),
        'harness_tracked': len([l for l in git(['ls-files', 'test-reports-2026-10/harness']
                                                ).splitlines() if l.strip()]),
    }


def anchor_cross_check():
    rows = []
    for path, (exp_bytes, exp_sha) in CAPTAIN_ANCHORS.items():
        fp = file_fp(path)
        row = {'path': path, 'captain_bytes': exp_bytes, 'captain_sha256': exp_sha,
               'measured_bytes': fp.get('bytes'), 'measured_sha256': fp.get('sha256'),
               'exists': fp.get('exists')}
        if not fp.get('exists'):
            row['verdict'] = 'MISSING_BOTH' if exp_bytes is None else 'MISMATCH_MISSING'
        elif exp_bytes is None:
            row['verdict'] = 'MISMATCH_UNEXPECTED_EXISTS'
        elif fp['bytes'] == exp_bytes and fp['sha256'] == (exp_sha or '').upper():
            row['verdict'] = 'MATCH'
        else:
            row['verdict'] = 'MISMATCH'
        rows.append(row)
    return rows


def real_db_fp():
    if not os.path.exists(REAL_DB):
        return {'exists': False}
    st = os.stat(REAL_DB)
    sha = sha256_file(REAL_DB)
    return {'exists': True, 'sha256': sha, 'bytes': st.st_size,
            'mtime': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(st.st_mtime)),
            'equals_frozen': sha == REAL_DB_SHA}


# --------------------------------------------------------------------------- 主流程
def verdict_auto(checks):
    if any(c.get('ok') is None for c in checks):
        return 'MISS'
    impl = [c for c in checks
            if c['evidence_kind'] in ('content_implementation', 'behavior_verified')
            and not c['pre_existing']]
    impl_ok = [c for c in impl if c['ok']]
    impl_fail = [c for c in impl if not c['ok']]
    mention_ok = all(c['ok'] for c in checks
                     if c['evidence_kind'] in ('content_mention', 'file_exists'))
    if impl_ok and not impl_fail and mention_ok:
        return 'HIT'
    if impl_ok:
        return 'PARTIAL'
    return 'NOT_DONE'


def excluded_files_found():
    """运行期实际命中的被排除文件（证明排除规则生效，供交付文档逐条列出）。"""
    import fnmatch
    out = []
    for root in ('test-reports-2026-10/harness', 'scripts'):
        for dirpath, dirnames, filenames in os.walk(os.path.join(REPO, root)):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for fn in sorted(filenames):
                for pat, why in EXCLUDE_PATTERNS.items():
                    if fnmatch.fnmatch(fn, pat) or fn == _SELF_BASENAME and pat == 'reconcile_r2.py':
                        out.append({'file': rel(os.path.join(dirpath, fn)),
                                    'matched_pattern': pat, 'reason': why})
                        break
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description='t1：38 条对账 + 阶段A终态冻结（只读）')
    ap.add_argument('--no-gates', action='store_true', help='跳过子进程门禁')
    ap.add_argument('--json', default=None, help='额外落一份机读摘要（守卫语义）')
    ap.add_argument('--run-id', default=os.environ.get('HARNESS_RUN_ID') or 'r2t1-reconcile')
    args = ap.parse_args(argv)

    t0 = time.time()
    db_before = real_db_fp()
    git_status_before = git(['status', '--porcelain'])

    meta = merge_item_meta()
    RANK = {'behavior_verified': 4, 'content_implementation': 3, 'file_exists': 2,
            'content_mention': 1}
    results = []
    for item_id, wave, domain, checks in ITEM_CHECKS:
        if args.no_gates:
            checks = [c for c in checks if c['kind'] != 'subprocess']
        rows = [dict(c) for c in checks]
        auto = verdict_auto(rows)
        ov = VERDICT_OVERRIDE.get(item_id)
        it = meta.get(item_id, {})
        passed = [c for c in rows if c['ok']]
        strongest = (max((c['evidence_kind'] for c in passed), key=lambda k: RANK[k])
                     if passed else None)
        impl_pass = any(c['evidence_kind'] in ('content_implementation', 'behavior_verified')
                        and c['ok'] and not c['pre_existing'] for c in rows)
        results.append({'id': item_id, 'wave': wave, 'level': it.get('level', ''),
                        'title': it.get('title', ''), 'verify_judge': it.get('verify_judge', ''),
                        'search_domain': domain,
                        # 条目级汇总（下游可直接引用；与 checks[].evidence_kind 同义）
                        'evidence_kind': strongest,
                        'evidence_kind_supports_hit': bool(impl_pass),
                        'evidence_kind_rule': '取该条 checks 中「通过」项的最强级；'
                                              '仅 content_implementation/behavior_verified 可支撑 HIT',
                        'verdict': (ov or {}).get('verdict', auto),
                        'verdict_auto': auto,
                        'verdict_override': ov or None,
                        'checks_passed': sum(1 for r in rows if r['ok']),
                        'checks_total': len(rows), 'checks': rows})

    wave = {}
    for r in results:
        d = wave.setdefault(r['wave'], {})
        d[r['verdict']] = d.get(r['verdict'], 0) + 1

    payload = {
        'task': 't1 / reconcile / 38 条待办对账与阶段A终态冻结',
        'run_id': args.run_id,
        'generated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'repo_root': REPO,
        'readonly_declaration': ('no app import, no create_app(), no DB open, no HTTP request, '
                                 'no evidence-producing script rerun (A-40); static gates only'),
        'writes': {
            'evidence': 'evidence/harness/<RUN_ID>/r2-38item-reconcile.json（E-01 守卫，只追加）',
            'tmp_probe': PROBE_DIR_REL + '/probe.py（TL-05 行为探针源码，gitignored；本项目 .tmp/ 为纯运行时目录）',
            'note': '除上述两者与可选的 --json 摘要外，本脚本不写任何文件（未原地覆盖任何既有文件）'},
        'verdict_semantics': {
            'HIT': '有 content_implementation/behavior_verified 证据且全部子项通过',
            'PARTIAL': '有实现证据但子项未全通过，或前提只部分成立',
            'NOT_DONE': '零实现证据（只有 content_mention/file_exists/度量输出）',
            'MISS': '探测本身失效（子进程 OSError 等），无法判定'},
        'self_match_guard': {
            'rule': '判据脚本不得把「自己」与「同为核验工具的脚本」当资产证据',
            'excluded_patterns': EXCLUDE_PATTERNS,
            'excluded_files_found': excluded_files_found(),
            'excluded_from_evidence': 'evidence/**（度量产物/冻结基线）不作为「新增用例」的证据'},
        'freeze': freeze_block(),
        'anchor_cross_check': anchor_cross_check(),
        'phase_a_file_delta': git_changed_files(),
        'coverage_artifacts': coverage_artifacts(),
        'uat_baseline_summary': uat_case_total(),
        'real_db_before': db_before,
        'ast_recount': {
            'get_json_without_silent': {
                'tool': 'reconcile_r2.get_json_without_silent()（AST，逐调用点）',
                't7_baseline': 39, 'now': len(get_json_without_silent()), 'sites': []},
            'undefined_model_refs': {
                'tool': 'reconcile_r2.undefined_model_refs()（与 check_model_refs 同口径的独立实现）',
                't7_baseline': 2, 'now': None, 'sites': []},
            'http_contract_sites': w4_site_counts(),
        },
        'items': results,
        'verdict_by_wave': wave,
        'counts': {'items': len(results),
                   'HIT': sum(1 for r in results if r['verdict'] == 'HIT'),
                   'PARTIAL': sum(1 for r in results if r['verdict'] == 'PARTIAL'),
                   'NOT_DONE': sum(1 for r in results if r['verdict'] == 'NOT_DONE'),
                   'MISS': sum(1 for r in results if r['verdict'] == 'MISS')},
    }
    jr = get_json_without_silent()
    payload['ast_recount']['get_json_without_silent']['sites'] = jr[:5]
    ur = undefined_model_refs()
    payload['ast_recount']['undefined_model_refs']['now'] = len(ur)
    payload['ast_recount']['undefined_model_refs']['sites'] = ur[:5]

    # ---- 控制台（ASCII 安全）
    print('=' * 84)
    print('[reconcile_r2] run_id=%s' % args.run_id)
    print('[reconcile_r2] HEAD=%s  app_tree=%s  phaseA commits=%d  dirty rows=%d  app==HEAD:%s'
          % (payload['freeze']['head_short'], payload['freeze']['app_tree_sha1'][:8],
             payload['freeze']['phase_a_commit_count'],
             len(payload['freeze']['worktree_status_rows']),
             payload['freeze']['app_tree_clean_vs_head']))
    print('[reconcile_r2] real app.db == frozen: %s (%s)'
          % (db_before.get('equals_frozen'), db_before.get('sha256')))
    print('[reconcile_r2] anchor cross-check: %s'
          % json.dumps([(r['path'].split('/')[-1], r['verdict'])
                        for r in payload['anchor_cross_check']], ensure_ascii=False))
    print('[reconcile_r2] w4 site counts: %s' % json.dumps(
        {k: v for k, v in w4_site_counts().items() if not k.endswith('_list')}, ensure_ascii=False))
    for w in sorted(wave):
        print('[reconcile_r2] %s: %s' % (w, json.dumps(wave[w], ensure_ascii=False)))
    print('-' * 84)
    for r in results:
        mark = '' if r['verdict'] == r['verdict_auto'] else ' (override; auto=%s)' % r['verdict_auto']
        print('%-7s %-4s %-9s %2d/%-2d  %s%s' % (r['id'], r['wave'], r['verdict'],
                                                 r['checks_passed'], r['checks_total'],
                                                 r['title'][:44], mark))
        for c in r['checks']:
            if not c['ok']:
                h = (c.get('hits') or [{}])[0]
                print('        [FAIL] %-16s %-30s %s' % (c['kind'], (c.get('label') or '')[:30],
                                                         '%s:%s' % (h.get('file', ''),
                                                                    h.get('line', ''))))
    print('-' * 84)
    print('[reconcile_r2] get_json w/o silent: t7=39  now=%d'
          % payload['ast_recount']['get_json_without_silent']['now'])
    print('[reconcile_r2] unresolved <Name>.query: t7=2  now=%d'
          % payload['ast_recount']['undefined_model_refs']['now'])
    print('[reconcile_r2] verdicts: %s' % json.dumps(payload['counts'], ensure_ascii=False))
    print('[reconcile_r2] elapsed %.1fs' % (time.time() - t0))

    # ---- 落盘（E-01 守卫）
    out_paths = []
    text = json.dumps(payload, ensure_ascii=False, indent=1)
    try:
        if HERE not in sys.path:
            sys.path.insert(0, HERE)
        import _env
        written = _env.save_evidence('r2-38item-reconcile.json', text,
                                     subdir=args.run_id, guard=True, journal=True)
        out_paths.append(rel(str(written)))
        print('[reconcile_r2] evidence -> %s' % out_paths[-1])
    except Exception as e:
        print('[reconcile_r2][WARN] evidence 落盘失败（不影响对账结论）: %r' % (e,))
    if args.json:
        try:
            import _env
            target = os.path.join(REPO, args.json)
            if os.path.exists(target):
                target, _renamed = _env.guard_write(target, run_id=args.run_id)
            with open(target, 'w', encoding='utf-8', newline='\n') as fh:
                fh.write(text)
            out_paths.append(rel(target))
            print('[reconcile_r2] json -> %s' % out_paths[-1])
        except Exception as e:
            print('[reconcile_r2][WARN] json 落盘失败: %r' % (e,))

    db_after = real_db_fp()
    git_status_after = git(['status', '--porcelain'])
    print('[reconcile_r2] real_db before==after: %s (== frozen: %s)'
          % (db_before.get('sha256') == db_after.get('sha256'),
             db_before.get('sha256') == REAL_DB_SHA == db_after.get('sha256')))
    print('[reconcile_r2] git status unchanged: %s' % (git_status_before == git_status_after))
    print('[reconcile_r2] output: %s' % ', '.join(out_paths))
    print('=' * 84)
    return 0


if __name__ == '__main__':
    sys.exit(main())
