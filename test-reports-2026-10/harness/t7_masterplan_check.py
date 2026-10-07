#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""t7 / 第2轮测试总方案定稿 —— 只读输入对拍探针（read-only inputs reconciliation）。

用途：总方案定稿（`35-第2轮测试总方案（定稿）.md`）必须对**每一个被整合的输入**给出
可复算的身份（bytes / 行数 / SHA256）与**测量时点**，否则「整合了 t2–t6 的结论」是
不可核验的主张。本探针只做三件事：

  1. **输入指纹对拍**：把 t1/t2/t3/t4/t5/t6 的交付物逐个算 bytes / splitlines 行数 / SHA256，
     并与**其自述值**并列（自述值写在 SELF_REPORTS 里，来自各任务的 output 文本），
     任何不一致 ⇒ 打印 `SELF_REPORT_DRIFT`（本战役第 7 类事故：计数/字节自述与实物不符）。
  2. **不变量复核**：`HEAD:app` tree SHA1、7 个回归锚点哈希、真实库 SHA256、生产面 diff。
  3. **执法面直读**（A-82：凡结论依赖语义，必须直读内容，不得用体积/文件名推断）：
     `Jenkinsfile` 的 `error()` 是否仍是注释、GitHub workflow 的 `continue-on-error` /
     `needs: gate`、`ci_gates.py` 的步骤表成员（blocking / report-only 分组）。

**边界（不得读成已测）**：
  * 不 import 应用、不连任何库、不发 HTTP 请求、不重跑任何会产生证据的脚本（A-40）；
  * 不修改任何文件——唯一的写动作是 `_env.save_evidence()` 落本 run 的证据目录；
  * 真实库只做「读字节算哈希」，不做任何 SQL。

用法：
    set HARNESS_RUN_ID=r2t7-masterplan
    python -B test-reports-2026-10/harness/t7_masterplan_check.py            # 人读
    python -B test-reports-2026-10/harness/t7_masterplan_check.py --json <path>
"""
import argparse
import hashlib
import io
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPORTS_ROOT = os.path.dirname(HERE)
REPO_ROOT = os.path.dirname(REPORTS_ROOT)
sys.path.insert(0, HERE)

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:                                     # pragma: no cover
    pass

import _env                                          # noqa: E402

R = lambda *p: os.path.join(REPO_ROOT, *p)           # noqa: E731
T = lambda *p: os.path.join(REPORTS_ROOT, *p)        # noqa: E731

_CAPTURE = []                                        # 控制台原文（用于归档）


class _Tee(object):
    """把 stdout 原样落到内存缓冲，收尾时经 ``_env.save_evidence`` 归档。"""

    def __init__(self, stream):
        self._stream = stream

    def write(self, s):
        _CAPTURE.append(s)
        return self._stream.write(s)

    def flush(self):
        return self._stream.flush()

    def __getattr__(self, name):
        return getattr(self._stream, name)

# ---------------------------------------------------------------- 输入清单
# (标签, 仓库相对路径, 承担任务, 自述值或 None)
# 自述值来自各任务 completed output / 补充说明（append-only），**不改写**，只并列比对。
INPUTS = [
    ('t1 对账（主文档）', 'test-reports-2026-10/27-38条对账与阶段A终态冻结.md', 't1',
     {'bytes': 50996, 'lines': 456, 'sha256_prefix': 'A8EA2CA3'}),
    ('t1 对账（机读 manifest）', 'test-reports-2026-10/27-38条对账与阶段A终态冻结.manifest.json', 't1',
     {'bytes': 161607, 'lines': None, 'sha256_prefix': None}),
    ('纪律书', 'test-reports-2026-10/28-第2轮执行纪律.md', 'captain',
     {'bytes': 7745, 'lines': None, 'sha256_prefix': None}),
    ('事实底盘', 'test-reports-2026-10/29-第2轮事实底盘.md', 'captain', None),
    ('方案初稿', 'test-reports-2026-10/30-第2轮测试方案.md', 'captain', None),
    ('建队计划', 'test-reports-2026-10/31-第2轮实测队建队计划.md', 'captain', None),
    ('改进报告', 'test-reports-2026-10/32-第2轮改进报告.md', 'captain', None),
    ('t4 业务验收判据', 'test-reports-2026-10/33-剩余项业务验收判据.md', 't4',
     {'bytes': 33460, 'lines': 222, 'sha256_prefix': '514C781A'}),
    ('t3 优先级与覆盖对账', 'test-reports-2026-10/33-剩余项优先级与覆盖对账.md', 't3',
     {'bytes': 25618, 'lines': None, 'sha256_prefix': None}),
    ('t3 机读 manifest', 'test-reports-2026-10/33-剩余项优先级与覆盖对账.manifest.json', 't3',
     {'bytes': 26422, 'lines': None, 'sha256_prefix': None}),
    ('t2 分层策略与判据契约', 'test-reports-2026-10/34-第2轮分层策略与判据契约.md', 't2',
     {'bytes': 64258, 'lines': 572, 'sha256_prefix': '55A3BB55'}),
    ('t6 runbook', 'test-reports-2026-10/40-第2轮实测Runbook与台账规范.md', 't6',
     {'bytes': 54074, 'lines': 663, 'sha256_prefix': None}),
    ('t6 台账模板', 'test-reports-2026-10/40-第2轮实测台账模板.json', 't6',
     {'bytes': 6355, 'lines': None, 'sha256_prefix': None}),
    ('t6 归档索引', 'test-reports-2026-10/50-第2轮证据归档索引.md', 't6',
     {'bytes': 9340, 'lines': None, 'sha256_prefix': None}),
    ('t5 工具链裁定（人读）', 'test-reports-2026-10/t5-工具链评估与三接入位裁定.md', 't5', None),
    ('t5 工具链裁定（机读）', 'test-reports-2026-10/t5-工具链评估与三接入位裁定.json', 't5', None),
    ('t6 台账校验器', 'test-reports-2026-10/harness/t6_ledger_check.py', 't6', {'bytes': 11691}),
    ('t6 证据通道探针', 'test-reports-2026-10/harness/t6_runbook_selftest.py', 't6', {'bytes': 3244}),
    ('t4 载体探针', 'test-reports-2026-10/harness/cr_accept_criteria.py', 't4', None),
    ('t3 复算器', 'test-reports-2026-10/harness/t3_priorities_r2.py', 't3', None),
    ('t1 复算器', 'test-reports-2026-10/harness/reconcile_r2.py', 't1', None),
]

# ---------------------------------------------------------------- 回归锚点（29 §4）
ANCHORS = [
    ('evidence/uat/uat_chains.json', 33318,
     '360A8570BC0080A2984A59AD945B2C837AD96ACF7B55E6242AE7E2C6417DD23A'),
    ('evidence/harness/negative_matrix.json', 24424,
     'B743C73F86F5EB5C0FBA38410119D8D3A6BDE5FBACDF214CFA0DB409EF5B7479'),
    ('evidence/analysis/assertion_ledger.json', 60937,
     'C7C312734DD8E02486D26C3639D8D074CCFCD59BCEB002C13C7CC9587AC94092'),
    ('evidence/api/write_suite.json', 73293,
     'B608117EBDCA2A6F74595F0DB4A010187D8834715CD5E70D5C1AAD85F4A3F403'),
    ('evidence/harness/coverage.json', 236893,
     '5E2C9D4315971B31C83AFD7833C310501199C34F61BFD868EF07A6AEEF7BF1F0'),
    ('evidence/api/api_matrix.json', 1342834,
     '8451BB6738CCB25C41794E7B9548969D0EDDC8FE6EAE855DCC5F1D1CC746CB86'),
    ('26-阶段A收口-复核读数.json', 11994,
     'CF0E2B14581D82072E087617B0CE3DBC1F4676897787DB6B14D6C6FA43D37319'),
]

PROD_PATHS = ['app', 'scripts', 'Jenkinsfile', '.github', 'requirements.txt', 'templates']
FREEZE_DIFF_BASE = '7e0a995'


def read_text(path):
    with io.open(path, 'r', encoding='utf-8', errors='replace') as fh:
        return fh.read()


def fp(path):
    """bytes / splitlines 行数 / SHA256 / mtime（A-23：行数口径 = Python splitlines）。"""
    with open(path, 'rb') as fh:
        raw = fh.read()
    import time
    mtime = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(os.path.getmtime(path)))
    return {
        'bytes': len(raw),
        'lines': len(read_text(path).splitlines()),
        'sha256': hashlib.sha256(raw).hexdigest().upper(),
        'mtime': mtime,
    }


def git(*args):
    try:
        p = subprocess.run(['git'] + list(args), cwd=REPO_ROOT, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT)
        return p.returncode, p.stdout.decode('utf-8', 'replace').strip()
    except Exception as e:                            # pragma: no cover
        return 1, 'git failed: %s' % e


def section(title):
    print('')
    print('=' * 78)
    print('== %s' % title)
    print('=' * 78)


def check_manifest(path):
    """定稿机读 manifest 的自洽与实物对拍（`--check-manifest`）。

    这是**真检查**（不是恒真报告）：分母算术、层记账、rank 集合、任务图、
    blocked 登记、以及与**实物文件**的指纹对拍，任一条不成立 ⇒ FAILED / exit 1。
    """
    section('6. 定稿 manifest 自洽 + 与实物对拍')
    fails = []
    with io.open(path, encoding='utf-8') as fh:
        m = json.load(fh)

    def chk(name, ok, detail=''):
        print('%-64s %s%s' % (name, 'OK' if ok else 'FAILED',
                              ('  <- %s' % detail) if (detail and not ok) else ''))
        if not ok:
            fails.append(name)
        return ok

    d = m['denominators']
    tb = d['total_breakdown']
    chk('D1 38 = HIT+PARTIAL+NOT_DONE+MISS',
        sum(tb.values()) == d['total_items'] == 38, str(tb))
    chk('D2 补齐分母 19 = NOT_DONE 12 + PARTIAL 7',
        d['fill_gap_denominator'] == tb['NOT_DONE'] + tb['PARTIAL'] == 19)
    chk('D3 in-scope 17 = W6 11 + W7 6',
        d['in_scope_residual'] == d['in_scope_breakdown']['W6'] + d['in_scope_breakdown']['W7'] == 17)
    rids = d['w6_ids'] + d['w7_residual_ids']
    chk('D4 rank 目标集合 = W6 ∪ W7 且 17 条唯一', len(rids) == len(set(rids)) == 17)
    chk('D5 out_of_scope = [P-09, P-12] 且与 17 条不相交',
        d['out_of_scope_partial'] == ['P-09', 'P-12'] and not set(d['out_of_scope_partial']) & set(rids))
    chk('D6 19 = 17 + 2（补齐分母 = in-scope + out_of_scope）',
        d['fill_gap_denominator'] == d['in_scope_residual'] + len(d['out_of_scope_partial']))

    la = m['layer_accounting']
    by = la['by_layer']
    chk('L1 层记账合计 = 19 = L1+L3+L4+L5+L6',
        sum(by.values()) == 19 == by['L1'] + by['L3'] + by['L4'] + by['L5'] + by['L6'], str(by))
    chk('L2 L0 = 0（结论而非疏漏，且有理由）', by['L0'] == 0 and bool(la['l0_zero_reason']))
    chk('L3 去重 16 = 19 − 跨层 3 条', la['dedup_items'] == 19 - len(la['cross_layer']) == 16)

    pr = m['priorities']
    rank = pr['rank_order']
    chk('P1 rank 序 = 17 条唯一且集合等于 W6∪W7',
        len(rank) == 17 and set(rank) == set(rids) and len(set(rank)) == 17)
    chk('P2 档位分布 P0 9 / P1 7 / P2 1 且与逐条 grade 一致',
        pr['grade_counts'] == {'P0': 9, 'P1': 7, 'P2': 1}
        and len(pr['grades']) == 17
        and all(pr['grades'][k] == v for k, v in pr['grades'].items()))
    from collections import Counter
    chk('P3 逐条 grade 计数 = grade_counts（复算）',
        dict(Counter(pr['grades'].values())) == pr['grade_counts'])

    tasks = m['tasks']
    tids = [t['id'] for t in tasks]
    chk('T1 任务 id 唯一且形如 V-nn', len(tids) == len(set(tids))
        and all(t.startswith('V-') for t in tids))
    chk('T2 每任务 inScope 非空', all(t.get('inScope') for t in tasks))
    chk('T3 kind ∈ {implementation, verification, work}',
        all(t['kind'] in ('implementation', 'verification', 'work') for t in tasks))
    chk('T4 批次 ∈ {B0..B5}', all(t['batch'] in ('B0', 'B1', 'B2', 'B3', 'B4', 'B5') for t in tasks))
    bad_dep = [t['id'] for t in tasks if any(x not in tids for x in t.get('depends', []))]
    chk('T5 依赖全部指向存在的任务', not bad_dep, str(bad_dep))
    chk('T6 每任务有 acceptance 与 verify',
        all(t.get('acceptance') and t.get('verify') for t in tasks))
    minset = m['minimal_deliverable_set']
    allref = sum([minset[k] for k in ('must', 'second_cut', 'third_cut', 'last_cut')], [])
    bad_ref = [x for x in allref if x not in tids and x != 'B0']
    chk('T7 最小可交付集的引用都在任务表内（B0 除外）', not bad_ref, str(bad_ref))

    bl = m['blocked_register']
    chk('B1 blocked 登记非空且每条含 reason + owner_wave',
        len(bl) > 0 and all(b.get('reason') and b.get('owner_wave') for b in bl))
    chk('B2 blocked 条数 ≥ 10（本战役未覆盖面规模）', len(bl) >= 10, str(len(bl)))

    iv = m['invariants']
    rc, tree = git('rev-parse', 'HEAD:app')
    chk('I1 manifest 的 app_tree_sha1 = 实测 HEAD:app',
        iv['app_tree_sha1'] == tree, '%s vs %s' % (iv['app_tree_sha1'], tree))
    dbf = fp(R('app.db'))
    chk('I2 manifest 的 real_db.sha256 = 实测 app.db', iv['real_db']['sha256'] == dbf['sha256'])
    rc, out = git('diff', '--stat', '%s..HEAD' % FREEZE_DIFF_BASE, '--', *PROD_PATHS)
    chk('I3 manifest 声称生产面 diff 为空 = 实测', iv['production_diff_empty'] and out == '')

    fpv = m['input_fingerprints']
    bad = []
    for it in fpv['items']:
        rel = it['path'].split('|')[0]
        p = R(*(rel.split('/')))
        if not os.path.isfile(p):
            bad.append('%s(MISSING)' % rel)
            continue
        f = fp(p)
        if it.get('bytes') is not None and it['bytes'] != f['bytes']:
            bad.append('%s(bytes %s!=%s)' % (rel, it['bytes'], f['bytes']))
        if it.get('lines') is not None and it['lines'] != f['lines']:
            bad.append('%s(lines %s!=%s)' % (rel, it['lines'], f['lines']))
        if it.get('sha256') and it['sha256'] != f['sha256']:
            bad.append('%s(sha256)' % rel)
    chk('F1 input_fingerprints 与实物逐项一致（%d 项）' % len(fpv['items']), not bad, str(bad))
    bad2 = []
    for dr in fpv['drifts']:
        p = R(*(dr['path'].split('/')))
        if not os.path.isfile(p):
            bad2.append('%s(MISSING)' % dr['path'])
            continue
        f = fp(p)
        actual = f['sha256'] if dr['field'] == 'sha256' else f['bytes']
        if actual != dr['measured']:
            bad2.append('%s(%s 实测 %s != measured %s)' % (dr['path'], dr['field'], actual, dr['measured']))
    chk('F2 已登记漂移的 measured 值 = 当前实物（漂移未"修复"也未恶化）', not bad2, str(bad2))

    print('')
    if fails:
        print('MANIFEST RESULT: FAILED (%d 项)' % len(fails))
        for f in fails:
            print('    - %s' % f)
    else:
        print('MANIFEST RESULT: OK（全部断言通过）')
    return fails


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', dest='json_out', default=None)
    ap.add_argument('--check-manifest', dest='manifest', default=None,
                    help='校验定稿机读 manifest（自洽 + 与实物对拍）')
    ap.add_argument('--no-archive', action='store_true',
                    help='不落 evidence/harness/<RUN_ID>/（默认落盘）')
    args = ap.parse_args()

    sys.stdout = _Tee(sys.stdout)

    doc = {'run_id': _env.RUN_ID, 'probe': 't7_masterplan_check.py',
           'readonly': True, 'inputs': [], 'anchors': [], 'findings': []}

    section('0. 环境与测量时点')
    print('python      = %s' % sys.version.split()[0])
    print('interpreter = %s' % sys.executable)
    print('REPO_ROOT   = %s' % REPO_ROOT)
    print('RUN_ID      = %s' % _env.RUN_ID)
    rc, head = git('rev-parse', 'HEAD')
    rc2, tree = git('rev-parse', 'HEAD:app')
    doc['env'] = {'python': sys.version.split()[0], 'interpreter': sys.executable,
                  'run_id': _env.RUN_ID, 'git_head': head, 'app_tree': tree}
    print('HEAD        = %s' % head)
    print('HEAD:app    = %s   (期望 c8f7d4abca1567b6219dbd77f22c82722f877ad6)' % tree)

    # ------------------------------------------------------------ 1. 输入指纹
    section('1. 输入指纹对拍（bytes / splitlines 行数 / SHA256，含自述值比对）')
    print('%-26s %9s %7s %8s  %s' % ('标签', 'bytes', 'lines', 'mtime', '判定'))
    drifts = []
    for label, rel, owner, self_rep in INPUTS:
        p = R(*(rel.split('/')))
        if not os.path.isfile(p):
            print('%-26s %9s %7s %8s  MISSING' % (label, '-', '-', '-'))
            doc['inputs'].append({'label': label, 'path': rel, 'owner': owner,
                                  'exists': False})
            doc['findings'].append({'id': 'MISSING_INPUT', 'path': rel, 'owner': owner})
            continue
        f = fp(p)
        note = 'ok'
        if self_rep:
            if self_rep.get('bytes') is not None and self_rep['bytes'] != f['bytes']:
                note = 'SELF_REPORT_DRIFT(bytes %s->%s)' % (self_rep['bytes'], f['bytes'])
                drifts.append((rel, 'bytes', self_rep['bytes'], f['bytes']))
            if self_rep.get('lines') is not None and self_rep['lines'] != f['lines']:
                note = (note if note != 'ok' else '') + ' SELF_REPORT_DRIFT(lines %s->%s)' \
                    % (self_rep['lines'], f['lines'])
                drifts.append((rel, 'lines', self_rep['lines'], f['lines']))
            pref = self_rep.get('sha256_prefix')
            if pref and not f['sha256'].startswith(pref.upper()):
                note = (note if note != 'ok' else '') + ' SELF_REPORT_DRIFT(sha256 %s!=%s)' \
                    % (pref, f['sha256'][:8])
                drifts.append((rel, 'sha256', pref, f['sha256'][:8]))
        print('%-26s %9d %7d %8s  %s' % (label, f['bytes'], f['lines'], f['mtime'], note))
        doc['inputs'].append({'label': label, 'path': rel, 'owner': owner, 'exists': True,
                              'bytes': f['bytes'], 'lines': f['lines'], 'sha256': f['sha256'],
                              'mtime': f['mtime'], 'note': note})

    if drifts:
        print('')
        print('[!] SELF_REPORT_DRIFT 共 %d 处（自述值 vs 实物）—— 引用时必须用实物值并写明测量时点：'
              % len(drifts))
        for rel, kind, claimed, actual in drifts:
            print('    - %s  %s: 自述 %s / 实测 %s' % (rel, kind, claimed, actual))
            doc['findings'].append({'id': 'SELF_REPORT_DRIFT', 'path': rel, 'field': kind,
                                    'claimed': claimed, 'measured': actual})
    else:
        print('\n[OK] 全部有自述值的输入与实物逐项一致。')

    # ------------------------------------------------------------ 2. 不变量
    section('2. 不变量复核（生产面 / 真实库 / 回归锚点）')
    rc, out = git('diff', '--stat', '%s..HEAD' % FREEZE_DIFF_BASE, '--', *PROD_PATHS)
    prod_clean = (rc == 0 and out == '')
    print('git diff --stat %s..HEAD -- %s => %s' % (
        FREEZE_DIFF_BASE, ' '.join(PROD_PATHS), 'EMPTY(零漂移)' if prod_clean else out))
    doc['production_diff_empty'] = prod_clean

    db = R('app.db')
    dbf = fp(db)
    db_ok = dbf['sha256'] == _env.REAL_DB_SHA256_EXPECTED
    print('app.db      = %d B / %s  %s' % (dbf['bytes'], dbf['sha256'],
                                           'OK' if db_ok else '!!! 与钉值不符'))
    doc['real_db'] = {'bytes': dbf['bytes'], 'sha256': dbf['sha256'], 'matches_pinned': db_ok}

    rc, st = git('status', '--porcelain')
    tracked_mod = [ln for ln in st.splitlines() if ln[:2].strip() and not ln.startswith('??')]
    print('git status  = 已跟踪改动 %d 项：%s' % (len(tracked_mod), tracked_mod or '[]'))
    doc['tracked_modified'] = tracked_mod

    print('')
    print('%-46s %9s %8s  %s' % ('锚点', 'bytes', '字节', 'SHA256 与 29 §4'))
    for rel, exp_b, exp_h in ANCHORS:
        p = T(*(rel.split('/'))) if not rel.startswith('26-') else T(rel)
        if not os.path.isfile(p):
            print('%-46s %9s %8s  MISSING' % (rel, '-', 'MISSING'))
            doc['anchors'].append({'path': rel, 'exists': False})
            continue
        f = fp(p)
        ok = (f['bytes'] == exp_b) and (f['sha256'] == exp_h)
        print('%-46s %9d %8s  %s' % (rel, f['bytes'], 'OK' if f['bytes'] == exp_b else 'DIFF',
                                     'MATCH' if ok else '!!! 不一致'))
        doc['anchors'].append({'path': rel, 'exists': True, 'bytes': f['bytes'],
                               'sha256': f['sha256'], 'expected_bytes': exp_b,
                               'expected_sha256': exp_h, 'matches': ok})

    # ------------------------------------------------------------ 3. 执法面直读
    section('3. 执法面直读（A-82：不看体积，只看内容）')
    jf = R('Jenkinsfile')
    jtext = read_text(jf)
    jlines = jtext.splitlines()
    calls = [(i + 1, l.strip()) for i, l in enumerate(jlines) if 'ci_gates' in l]
    commented_err = [(i + 1, l.strip()) for i, l in enumerate(jlines)
                     if l.strip().startswith('//') and 'error(' in l]
    live_err = [(i + 1, l.strip()) for i, l in enumerate(jlines)
                if l.strip().startswith('error(')]
    unstable = [(i + 1, l.strip()) for i, l in enumerate(jlines) if 'UNSTABLE' in l]
    print('Jenkinsfile 提及 ci_gates 行 = %d' % len(calls))
    for ln, txt in calls:
        print('    :%-4d %s' % (ln, txt[:110]))
    print('Jenkinsfile 被注释的 error() = %d 行：%s' % (len(commented_err),
                                                      [a for a, _ in commented_err]))
    print('Jenkinsfile 生效的   error() = %d 行：%s' % (len(live_err),
                                                      [a for a, _ in live_err]))
    print('Jenkinsfile UNSTABLE（第一阶段信号）= %d 行：%s' % (len(unstable),
                                                             [a for a, _ in unstable]))
    doc['jenkinsfile'] = {'ci_gates_lines': [a for a, _ in calls],
                          'commented_error_lines': [a for a, _ in commented_err],
                          'live_error_lines': [a for a, _ in live_err],
                          'unstable_lines': [a for a, _ in unstable]}

    wf = R('.github', 'workflows', 'docker-deploy.yml')
    if os.path.isfile(wf):
        wlines = read_text(wf).splitlines()
        coe = [(i + 1, l.strip()) for i, l in enumerate(wlines) if 'continue-on-error' in l]
        needs = [(i + 1, l.strip()) for i, l in enumerate(wlines) if 'needs:' in l]
        cg = [(i + 1, l.strip()) for i, l in enumerate(wlines) if 'ci_gates' in l]
        print('')
        print('docker-deploy.yml 行数 = %d' % len(wlines))
        print('    continue-on-error 行 = %s' % [a for a, _ in coe])
        print('    needs: 行            = %s' % [(a, t[:40]) for a, t in needs])
        print('    ci_gates 调用行       = %s' % [a for a, _ in cg])
        doc['github_workflow'] = {'lines': len(wlines),
                                  'continue_on_error_lines': [a for a, _ in coe],
                                  'needs_lines': [a for a, _ in needs],
                                  'ci_gates_lines': [a for a, _ in cg]}
    else:
        print('\n[!] .github/workflows/docker-deploy.yml 不存在')
        doc['github_workflow'] = {'exists': False}

    cg_path = T('harness', 'ci_gates.py')
    cgf = fp(cg_path)
    print('')
    print('ci_gates.py = %d B / %d 行 / %s   (mtime %s)'
          % (cgf['bytes'], cgf['lines'], cgf['sha256'][:16], cgf['mtime']))
    try:
        p = subprocess.run([sys.executable, '-B', cg_path, '--list'], cwd=REPO_ROOT,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        listing = p.stdout.decode('utf-8', 'replace')
        steps = [l for l in listing.splitlines()
                 if l.startswith('[ci_gates]') and not l.startswith('[ci_gates] phase=')]
        blocking = [l for l in steps if l.strip().endswith('blocking') or ' blocking ' in l]
        report_only = [l for l in steps if 'report-only' in l]
        print('ci_gates --list => exit %d；步骤 %d 条（blocking %d / report-only %d）'
              % (p.returncode, len(steps), len(blocking), len(report_only)))
        for l in steps:
            print('    %s' % l.replace('F:\\Miniconda\\envs\\wage\\python.exe', '$py')[:120])
        doc['ci_gates'] = {'bytes': cgf['bytes'], 'lines': cgf['lines'],
                           'sha256': cgf['sha256'], 'mtime': cgf['mtime'],
                           'list_exit': p.returncode, 'steps': len(steps),
                           'blocking': len(blocking), 'report_only': len(report_only),
                           'step_ids': [l.split(']')[1].strip().split()[0] for l in steps]}
    except Exception as e:                            # pragma: no cover
        print('[!] ci_gates --list 失败：%s' % e)
        doc['ci_gates'] = {'error': str(e)}

    # ------------------------------------------------------------ 4. 27 manifest counts
    section('4. t1 机读 manifest 的分母（唯一权威计数来源）')
    mpath = T('27-38条对账与阶段A终态冻结.manifest.json')
    if os.path.isfile(mpath):
        m = json.loads(read_text(mpath))
        counts = m.get('counts')
        print('counts = %s' % json.dumps(counts, ensure_ascii=False))
        fr = m.get('freeze') or {}
        print('freeze.app_tree_sha1 = %s' % fr.get('app_tree_sha1'))
        items = m.get('items') or []
        print('items 条数 = %d' % len(items))
        doc['manifest'] = {'counts': counts, 'app_tree_sha1': fr.get('app_tree_sha1'),
                           'items': len(items)}
        if fr.get('app_tree_sha1') and tree and fr['app_tree_sha1'] != tree:
            doc['findings'].append({'id': 'TREE_DRIFT', 'manifest': fr.get('app_tree_sha1'),
                                    'measured': tree})
    else:
        print('[!] manifest 不存在')
        doc['manifest'] = {'exists': False}

    # ------------------------------------------------------------ 5. 结论
    section('5. 结论（本探针的断言）')
    asserts = [
        ('A1 生产面 diff 为空（%s..HEAD）' % FREEZE_DIFF_BASE, prod_clean),
        ('A2 HEAD:app = c8f7d4ab…（t1 冻结值）',
         tree == 'c8f7d4abca1567b6219dbd77f22c82722f877ad6'),
        ('A3 app.db SHA256 = 钉值', db_ok),
        ('A4 7 个回归锚点全部与 29 §4 逐位一致',
         all(a.get('matches') for a in doc['anchors'])),
        ('A5 ci_gates 步骤表 ≥ 11 条且可列举', doc.get('ci_gates', {}).get('steps', 0) >= 11),
    ]
    all_ok = True
    for name, ok in asserts:
        print('%-52s %s' % (name, 'OK' if ok else 'FAILED'))
        doc.setdefault('assertions', []).append({'name': name, 'ok': bool(ok)})
        all_ok = all_ok and bool(ok)
    print('')
    print('RESULT: %s' % ('OK' if all_ok else 'FAILED'))

    if args.manifest:
        mfails = check_manifest(args.manifest)
        doc['manifest_check'] = {'path': args.manifest, 'failed': mfails}
        all_ok = all_ok and not mfails
        print('')
        print('FINAL RESULT: %s' % ('OK' if all_ok else 'FAILED'))

    if args.json_out:
        outp = args.json_out
        os.makedirs(os.path.dirname(os.path.abspath(outp)), exist_ok=True)
        txt = json.dumps(doc, ensure_ascii=False, indent=1)
        p, renamed = _env.guard_write(outp)
        with io.open(p, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(txt + '\n')
        print('json written: %s (renamed_by_guard=%s)' % (p, renamed))

    if not args.no_archive:
        _stream = getattr(sys.stdout, '_stream', sys.stdout)
        report = ''.join(_CAPTURE)
        pa = _env.save_evidence('t7-masterplan-check.txt', report)
        pb = _env.save_evidence('t7-inputs.json',
                                json.dumps(doc, ensure_ascii=False, indent=1) + '\n')
        print('archived via save_evidence:')
        print('    %s' % pa)
        print('    %s' % pb)
        _stream.write('archived: %s ; %s\n' % (pa, pb))

    return 0 if all_ok else 1


if __name__ == '__main__':
    sys.exit(main())
