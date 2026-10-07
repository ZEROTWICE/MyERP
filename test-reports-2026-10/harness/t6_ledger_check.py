"""t6 台账校验器：把 `40-第2轮实测Runbook与台账规范.md` §4.3 的 8 条规则做成可执行判据。

用法（仓库根）：

    $py = 'F:\Miniconda\envs\wage\python.exe'
    & $py -B test-reports-2026-10/harness/t6_ledger_check.py test-reports-2026-10/40-第2轮实测台账模板.json
    & $py -B test-reports-2026-10/harness/t6_ledger_check.py --selftest

退出码：0 = 全部规则通过（仅报 ERROR 级）；1 = 有 ERROR；2 = 参数/读取失败。

规则（与 §4.3 一一对应）：

    R-1  verdict=HIT 而 evidence_kind in {file_exists, content_mention}
    R-2  verdict=HIT 而无 behavior_flip_test.red_when_removed
    R-3  覆盖类条目（id 以 C-0/C-1 开头，即 W6 的 C-01…C-11）缺 coverage_delta
    R-4  search_domain.exclude_basenames 为空 / 未声明 / 不含判定脚本自身
    R-5  verdict in {PARTIAL, NOT_DONE} 而未在 gaps 登记
    R-6  artifact_index 里的路径不存在（模板里的 <...> 占位不算）
    R-7  db_invariant.sha256_before != sha256_after 或 != 钉死值
    R-8  command 里出现裸 python / py / python3

`--selftest`：对内置的 8 个反例逐一断言「必须被 R-n 抓到」（阴性对照），再加 1 个正例。
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPORTS_ROOT = os.path.dirname(HERE)
REPO_ROOT = os.path.dirname(REPORTS_ROOT)

#: 真实库钉死哈希（与 _env.REAL_DB_SHA256_EXPECTED 同源；下方 _selftest 前会交叉断言）
PINNED_DB_SHA = 'F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065'

WEAK_KINDS = ('file_exists', 'content_mention')
COVERAGE_CLASS_IDS = re.compile(r'^C-(0[1-9]|1[01])$')
BARE_PYTHON = re.compile(r'(?<![\w.\-\\/])(python|python3|py)(?![\w.])')
PLACEHOLDER = re.compile(r'^<.*>$')

REQUIRED_TOP = ('ledger_version', 'run_id', 'task_id', 'attempt_id', 'operator',
                'started_at', 'finished_at', 'env', 'db_invariant', 'anchor_readings',
                'results', 'gaps', 'artifact_index')


def _placeholder(value):
    return isinstance(value, str) and ('<' in value or value == '')


def check(doc, repo_root=REPO_ROOT):
    """返回 (errors, warnings)，每条 error 形如 'R-n ...'。"""
    errors, warnings = [], []

    for key in REQUIRED_TOP:
        if key not in doc:
            errors.append('TOP 缺少顶层字段: %s' % key)
    if errors:
        return errors, warnings

    if doc.get('ledger_version') != '2.0':
        errors.append('TOP ledger_version 必须为 "2.0"（当前 %r）' % doc.get('ledger_version'))

    # R-7 真实库不变量
    dbi = doc.get('db_invariant') or {}
    before, after = dbi.get('sha256_before'), dbi.get('sha256_after')
    if before != after:
        errors.append('R-7 db_invariant 前后不一致: %s -> %s' % (before, after))
    for label, val in (('before', before), ('after', after)):
        if val and val.upper() != PINNED_DB_SHA:
            errors.append('R-7 db_invariant.sha256_%s != 钉死值 %s（实测 %s）'
                          % (label, PINNED_DB_SHA, val))

    # R-6 证据路径真实存在（占位符跳过）
    for i, art in enumerate(doc.get('artifact_index') or []):
        p = (art or {}).get('path')
        if not p or _placeholder(p):
            continue
        if not os.path.exists(os.path.join(repo_root, p.replace('/', os.sep))):
            errors.append('R-6 artifact_index[%d] 路径不存在: %s' % (i, p))

    # 逐条 results
    hit_by_id, weak_by_id = {}, {}
    for i, r in enumerate(doc.get('results') or []):
        rid = r.get('id') or 'results[%d]' % i
        kind = r.get('evidence_kind')
        verdict = r.get('verdict')
        if kind not in WEAK_KINDS + ('content_implementation', 'behavior_verified'):
            errors.append('R-1 %s evidence_kind 非法: %r' % (rid, kind))
        if verdict not in ('HIT', 'PARTIAL', 'NOT_DONE', 'MISS'):
            errors.append('R-5 %s verdict 非法: %r' % (rid, verdict))
        if verdict == 'HIT':
            hit_by_id[rid] = r
            if kind in WEAK_KINDS:
                errors.append('R-1 %s verdict=HIT 但 evidence_kind=%s（弱证据不得判 HIT）'
                              % (rid, kind))
        if kind in WEAK_KINDS:
            weak_by_id[rid] = kind
        if verdict == 'HIT':
            flip = r.get('behavior_flip_test') or {}
            if not (flip.get('red_when_removed') or '').strip():
                errors.append('R-2 %s verdict=HIT 缺 behavior_flip_test.red_when_removed' % rid)
        # R-3 覆盖类
        if COVERAGE_CLASS_IDS.match(str(rid)) and r.get('coverage_delta') is None:
            errors.append('R-3 %s 覆盖类条目缺 coverage_delta（须给 metric/before/after/produced_by）'
                          % rid)
        # R-4 搜索域
        sd = r.get('search_domain') or {}
        ex = [e for e in (sd.get('exclude_basenames') or []) if e]
        if not sd:
            errors.append('R-4 %s 缺 search_domain' % rid)
        elif not ex:
            errors.append('R-4 %s search_domain.exclude_basenames 为空（必须排除判定脚本自身）' % rid)
        else:
            script = _script_of(r.get('command') or '')
            if script and os.path.basename(script) not in ex:
                warnings.append('R-4w %s exclude_basenames 未包含命令对应的脚本 %s（若该脚本是「被判定对象」'
                                '而非「核验脚本」，请显式排除以消除自指性，A-74）'
                                % (rid, os.path.basename(script)))
        # R-8 裸 python
        cmd = r.get('command') or ''
        if cmd and not _placeholder(cmd):
            for m in BARE_PYTHON.finditer(cmd):
                frag = cmd[max(0, m.start() - 12):m.end() + 12]
                errors.append('R-8 %s command 出现裸 %r: ...%s...' % (rid, m.group(0), frag))
                break
        if r.get('exit_code') is None and not (r.get('notes') or '').strip():
            warnings.append('W-exit %s exit_code=null 但 notes 为空' % rid)

    # R-5 PARTIAL/NOT_DONE 必须在 gaps 登记
    registered = set()
    for g in doc.get('gaps') or []:
        txt = ' '.join(str(g.get(k, '')) for k in ('id', 'item', 'reason', 'action'))
        registered.add(txt)
    for i, r in enumerate(doc.get('results') or []):
        rid = r.get('id') or 'results[%d]' % i
        if r.get('verdict') in ('PARTIAL', 'NOT_DONE'):
            if not any(rid in t for t in registered):
                errors.append('R-5 %s verdict=%s 但 gaps 里无对应登记' % (rid, r.get('verdict')))

    return errors, warnings


def _script_of(command):
    for tok in re.findall(r'[^\s"]+\.py', command):
        if token_is_path(tok):
            return tok
    return None


def token_is_path(tok):
    return ('/' in tok or '\\' in tok)


def load(path):
    with open(path, encoding='utf-8') as fh:
        return json.load(fh)


# ------------------------------------------------------------------ selftest
def _base():
    return {
        'ledger_version': '2.0', 'run_id': 'r', 'task_id': 't', 'attempt_id': 'a',
        'operator': 'o', 'started_at': 'x', 'finished_at': 'y',
        'env': {}, 'anchor_readings': [], 'artifact_index': [], 'gaps': [],
        'db_invariant': {'sha256_before': PINNED_DB_SHA, 'sha256_after': PINNED_DB_SHA},
        'results': [{
            'id': 'TL-01', 'wave': 'W7', 'evidence_kind': 'behavior_verified', 'verdict': 'HIT',
            'command': r'F:\Miniconda\envs\wage\python.exe -B scripts/check_model_refs.py',
            'exit_code': 0,
            'search_domain': {'dirs': ['scripts'], 'match': 'content',
                              'exclude_basenames': ['check_model_refs.py']},
            'behavior_flip_test': {'red_when_removed': 'ci_gates.py#check_model_refs'},
        }],
    }


def selftest():
    # 常量同源交叉断言：防止本文档工具与 _env 的真实库钉死值各写一份而漂移
    sys.path.insert(0, HERE)
    import _env  # noqa: E402
    assert PINNED_DB_SHA == _env.REAL_DB_SHA256_EXPECTED, (
        'PINNED_DB_SHA 与 _env.REAL_DB_SHA256_EXPECTED 不一致：%s vs %s'
        % (PINNED_DB_SHA, _env.REAL_DB_SHA256_EXPECTED))

    cases = []

    def case(name, mutate, expect_rule):
        d = _base()
        mutate(d)
        errs, _ = check(d, repo_root=os.path.join(REPO_ROOT, '__no_such_root__'))
        hit = [e for e in errs if e.startswith(expect_rule)]
        cases.append((name, expect_rule, bool(hit), errs[:2]))

    # 正例
    errs, _ = check(_base(), repo_root=os.path.join(REPO_ROOT, '__no_such_root__'))
    ok_pos = not [e for e in errs if e.startswith(('R-', 'TOP'))]
    cases.append(('POSITIVE 合法台账（无 ERROR）', '-', ok_pos, errs[:2]))

    case('N-1 弱证据判 HIT',
         lambda d: d['results'][0].update(evidence_kind='content_mention'), 'R-1')
    case('N-2 HIT 无变红回答',
         lambda d: d['results'][0]['behavior_flip_test'].clear(), 'R-2')
    case('N-3 覆盖类缺 coverage_delta',
         lambda d: d['results'][0].update(id='C-05'), 'R-3')
    case('N-4 搜索域排除为空',
         lambda d: d['results'][0]['search_domain'].update(exclude_basenames=[]), 'R-4')
    case('N-5 PARTIAL 未登记 gaps',
         lambda d: d['results'][0].update(verdict='PARTIAL'), 'R-5')
    case('N-6 证据路径不存在（真实路径形态）',
         lambda d: d.update(artifact_index=[{'path': 'test-reports-2026-10/__nope__.json'}]),
         'R-6')
    case('N-7 真库指纹被改',
         lambda d: d['db_invariant'].update(sha256_after='DEADBEEF'), 'R-7')
    case('N-8 裸 python',
         lambda d: d['results'][0].update(command='python -B scripts/check_model_refs.py'),
         'R-8')

    print('[t6_ledger_check] --selftest')
    fails = 0
    for name, rule, ok, sample in cases:
        print('  [%s] %-34s expect=%s%s'
              % ('PASS' if ok else 'FAIL', name, rule,
                 '' if ok else '  样本=%s' % (sample,)))
        fails += 0 if ok else 1
    print('[t6_ledger_check] 判定 = %s（%d/%d）'
          % ('OK' if not fails else 'VIOLATION', len(cases) - fails, len(cases)))
    return 0 if not fails else 1


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    ap = argparse.ArgumentParser(description='第2轮台账 §4.3 八条校验')
    ap.add_argument('ledger', nargs='?', help='台账 JSON 路径')
    ap.add_argument('--selftest', action='store_true', help='8 反例 + 1 正例的阴性/阳性对照')
    ap.add_argument('--repo-root', default=REPO_ROOT, help='解析 artifact_index 相对路径的根')
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    if not args.ledger:
        ap.print_help()
        return 2
    try:
        doc = load(args.ledger)
    except Exception as e:
        print('[t6_ledger_check] 读取失败: %s: %s' % (e.__class__.__name__, e))
        return 2

    errors, warnings = check(doc, repo_root=args.repo_root)
    for w in warnings:
        print('  [WARN] %s' % w)
    for e in errors:
        print('  [ERROR] %s' % e)
    verdict = 'OK' if not errors else 'VIOLATION'
    print('[t6_ledger_check] %s -> 判定 = %s（results=%d gaps=%d artifacts=%d）'
          % (os.path.relpath(args.ledger, REPO_ROOT).replace('\\', '/'), verdict,
             len(doc.get('results') or []), len(doc.get('gaps') or []),
             len(doc.get('artifact_index') or [])))
    return 0 if not errors else 1


if __name__ == '__main__':
    sys.exit(main())
