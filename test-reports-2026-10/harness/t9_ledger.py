# -*- coding: utf-8 -*-
"""t9 断言账本回归比对器：把「修复后实测」逐条对到 t6 冻结基线 `assertion_ledger.json`。

## 数据面
* 基线（只读）：`evidence/analysis/assertion_ledger.json`（t6，144 条：128 passed / 10 failed /
  4 see_violations / 2 probe）+ 各 suite 的冻结产物（`evidence/{harness,api,uat}/*.json`）。
* 修复后（本 run）：树副本 `.tmp/<RUN_ID>/tree/after/` 里复跑的
  `negative_matrix.json` / `gates.json` / `api_matrix.json` / `write_suite.json` /
  `uat_chains.json` / `coverage.json`，以及真实仓库里守卫型探针的
  `w1-p01-criteria.json` / `w2w3-criteria.json` / `w4_post_*`。

## 归类（一条断言只能落一格）
* `unchanged_pass` 基线通过、修复后仍通过
* `red_to_green`   基线失败、修复后通过（= 修复生效）
* `still_red`      仍失败 —— 再分「资产写错」与「产品未修」
* `expected_flip`  基线通过、修复后失败，且**有 DEC/裁定依据的语义演进**（必须引用条款）
* `REGRESSION`     基线通过、修复后失败且**无依据** => 必须按阻断项报出

## 用法
    $env:HARNESS_RUN_ID='t9-rega-b1'
    python -B test-reports-2026-10/harness/t9_ledger.py [--postfix-run t9-rega-b2] [--markdown]
"""
import argparse
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPORTS_ROOT = os.path.dirname(HERE)
REPO_ROOT = os.path.dirname(REPORTS_ROOT)
sys.path.insert(0, HERE)

from _env import EVIDENCE_ROOT, RUN_ID, save_evidence, sha256_file  # noqa: E402

BASELINE_LEDGER = os.path.join(REPORTS_ROOT, 'evidence', 'analysis', 'assertion_ledger.json')
FROZEN_UAT = os.path.join(REPORTS_ROOT, 'evidence', 'uat', 'uat_chains.json')
TMP_ROOT = os.path.join(REPORTS_ROOT, '.tmp')

#: 基线通过 -> 修复后失败，且有**明确依据**的语义演进（不是产品回归）。
#: 每条必须给出引用条款；无条款者一律按 REGRESSION 报出（A-45 的纪律：不得批量豁免）。
EXPECTED_FLIPS = {
    'uat:P0-2.5': ('A-45 + DEC-1 §1.4 序 3 / §1.6 P1：`pending` 且**无在办单据**由「拒收（死锁）」'
                   '改判为「放行」；本条与 P0-2.4（fg +4 必须不变）成对常驻'),
    'uat:P0-2.1': ('DEC-1 §1.4 序 1：该实例在本链内已落 `fail`（P0-1.7/P0-1.8 转绿的直接后果）'
                   '⇒ 门禁必须拒收；原断言「NULL 实例放行」的前提已被 DEC-1 取代'),
    'negative_matrix:NV-3.5b': ('A-67 + DEC-1 §1.4 序 3：`pending` 且**无在办单据**由「一律拒收（死锁）」'
                                '改判为「放行」；原断言把 pending 实例的拒收当成正确（同 P0-2.5 同源）。'
                                '配对格（pending 且确有在办单据 ⇒ 拒）见 uat P0-2.5(b) 与 w2w3_probe cells'),
}

#: 基线失败、修复后仍失败，且属于**冻结资产写错**（A-66 裁定由 t9 重写 + t9 本轮新发现）。
ASSET_DEFECTS = {
    'uat:P0-1.6': 'A-66①：断言点在「报工后、结论落库前」，DEC-1 §1.2 规定此刻必须 NULL',
    'uat:P0-3.1': 'A-66②：夹具用 notes 标记造返工（DEC-2 §2.2 已否决）+ 断言用链内自算公式',
    'negative_matrix:NV-2.1': 'A-66③：同 notes 标记理由（DEC-2 §2.2 选定 R1∨R2）',
    'negative_matrix:NV-2.3': 'A-66⑤：断言的就是缺陷本身（期望「开关零读取点」）',
    'negative_matrix:NV-2.4': 'A-66④：计数写死（期望恰 4 个开关有读取点）',
    'negative_matrix:NV-3.3': 'A-66④：行号写死（期望门禁调用点恰在 :326）',
    'negative_matrix:NV-3.9': 'A-66⑤：断言的就是缺陷本身（期望「不回写 quality_status」）',
    'negative_matrix:NV-3.10': 'A-66⑤：断言的就是缺陷本身（期望「赋值点只有人工 PUT 一处」）',
    # t9 本轮新发现（A-66 未列入，属同一纪律；已按 A-29 重写并登记越界理由）
    'uat:P0-3.3': 't9 新发现（A-66 同源⑤/AC-04-e）：期望「开关零读取点」= NV-2.3 的 uat 孪生',
    'write_suite:W-TASK-3': 't9 新发现：断言「notes 被丢弃 + 审计 old==new」（P-08 缺陷形态）'
                            '+ 脚手架在 app_context 外查审计表抛 RuntimeError',
    'write_suite:W-INV-7': 't9 新发现：断言「失败时库存守恒」与「成功必须扣 3」自相矛盾'
                           '（原实现恒 500 时该断言才成立）',
    'write_suite:W-QLT-3': 't9 新发现：断言「部分更新必须 4xx + 库不变」——把 KeyError⇒500 当正确；'
                           '`17` P-12-b 口径是部分更新 ∈ {200,400}',
}

#: 基线**通过**、修复后失败，且该「通过」本身就是「断言了缺陷形态」的资产缺陷（A-66 纪律）。
ASSET_FLIPS = {
    'negative_matrix:NV-2.3': 'A-66 ⑤：原期望「零读取点」正是缺陷（假开关）',
    'negative_matrix:NV-2.4': 'A-66 ④：原把「有读取点的开关数」写死为 4',
    'negative_matrix:NV-3.3': 'A-66 ④：原把门禁调用点行号写死为 326',
    'negative_matrix:NV-3.9': 'A-66 ⑤：原期望「不回写 quality_status」正是缺陷（GAP-14）',
    'negative_matrix:NV-3.10': 'A-66 ⑤：原期望「赋值点只有人工 PUT 一处」正是缺陷',
    'uat:P0-3.3': 't9 新发现（A-66 同源⑤/AC-04-e）：原期望「开关零读取点」= NV-2.3 的 uat 孪生',
}

#: 基线通过、修复后失败，且属**判据本身失效**（产品行为演进的副作用，安全属性未变）。
CRITERION_INVALIDATED = {
    'api_matrix:matrix_f_csrf': (
        't9 新发现（D-1/D-2/D-3 三方判别）：`api_matrix.py:808-809` 的 csrf_blocked 判据要求'
        ' 400 正文含 csrf/令牌/Token 标记；W4/P-12 统一 `errorhandler(HTTPException)` 后，'
        'JSON 面的 CSRF 400 正文变成 `请求参数有误`（`app/__init__.py:193`）⇒ 24 条被判 not_enforced。'
        '**拦截仍在**（三方判别：无 token=框架级 400 且视图未执行；带 token / 关 CSRF=视图级 400），'
        '故不是 CSRF 失效，而是**判据失效 + 诊断信息被替换**（findings F-1）'),
}

#: 探针判据（t6/t7/t8 的自证件）在合并终态上的重跑：id -> (期望条数, 依赖结果自述值)
PROBE_EXPECT = {
    'w1_p01_probe': ('t6 终态轮 reverify2 27/27', 'criteria'),
    'w2w3_probe': ('t7 run w2w3-t7-final 46/46', 'checks'),
    'w4_probe_post': ('t8 39/39', 'checks'),
}


def load_json(path):
    with io.open(path, encoding='utf-8') as fh:
        return json.load(fh)


def tree_root(postfix_run):
    return os.path.join(TMP_ROOT, postfix_run, 'tree', 'after')


def load_postfix(postfix_run):
    tree = tree_root(postfix_run)
    ev = os.path.join(tree, 'test-reports-2026-10', 'evidence')
    run = os.path.join(ev, 'harness', postfix_run)
    out = {}
    paths = {
        'gates': os.path.join(run, 'gates.json'),
        'negative_matrix': os.path.join(run, 'negative_matrix.json'),
        'coverage': os.path.join(run, 'coverage.json'),
        'api_matrix': os.path.join(ev, 'api', 'api_matrix.json'),
        'write_suite': os.path.join(ev, 'api', 'write_suite.json'),
        'uat': os.path.join(ev, 'uat', 'uat_chains.json'),
    }
    for key, path in paths.items():
        if os.path.exists(path):
            out[key] = {'path': os.path.relpath(path, REPO_ROOT).replace('\\', '/'),
                        'sha256': sha256_file(path), 'bytes': os.path.getsize(path),
                        'data': load_json(path)}
        else:
            out[key] = {'path': os.path.relpath(path, REPO_ROOT).replace('\\', '/'),
                        'missing': True, 'data': None}
    return out


def postfix_verdicts(post):
    """把各 suite 的修复后产物压成 `'<suite>:<id>' -> {verdict, got}`。"""
    v = {}
    g = post.get('gates', {}).get('data')
    if g:
        for gate in g.get('gates', []):
            verdict = {'pass': 'passed', 'fail': 'failed'}.get(gate.get('verdict'),
                                                              gate.get('verdict'))
            v['gate:' + gate['gate']] = {'verdict': verdict, 'got': {
                'exit': gate.get('exit_code'), 'expected_exit': gate.get('expected_exit_code'),
                'parsed': gate.get('parsed')}}
            v['gate:' + gate['gate'] + '.counts'] = {
                'verdict': 'passed' if verdict == 'passed' else verdict,
                'got': {'exit': gate.get('exit_code')}}
        s = g.get('sensitivity', {})
        v['gate:SENSITIVITY.injections'] = {
            'verdict': 'passed' if s.get('injections_all_nonzero') else 'failed',
            'got': {'injections_all_nonzero': s.get('injections_all_nonzero')}}
        v['gate:SENSITIVITY.baselines'] = {
            'verdict': 'passed' if s.get('baselines_all_zero') else 'failed',
            'got': {'baselines_all_zero': s.get('baselines_all_zero')}}
    nm = post.get('negative_matrix', {}).get('data')
    if nm:
        for case in nm.get('cases', []):
            v['negative_matrix:' + case['id']] = {'verdict': case.get('verdict'),
                                                  'got': case.get('actual')}
    ws = post.get('write_suite', {}).get('data')
    if ws:
        for row in ws.get('results', []):
            v['write_suite:' + row['id']] = {
                'verdict': 'passed' if row.get('passed') else 'failed',
                'got': {'failed_checks': [c.get('check') for c in row.get('checks', [])
                                          if not c.get('ok')]}}
    uc = post.get('uat', {}).get('data')
    if uc:
        for c in uc.get('checks', []):
            v['uat:' + c['id']] = {'verdict': c.get('status'), 'got': c.get('got')}
    return v


def postfix_api_matrix(post):
    am = post.get('api_matrix', {}).get('data') or {}
    out = {}
    for key, val in am.items():
        if not key.startswith('matrix_'):
            continue
        viol = val.get('violations') or []
        detail = {kk: vv for kk, vv in val.items()
                  if kk in ('allow_count', 'allowed_count', 'count_404',
                            'api_non_401_observations')}
        out[key] = {'violations': len(viol), **detail}
    csrf = am.get('matrix_f_csrf') or am.get('matrix_f') or {}
    out['CSRF.not_enforced'] = (csrf.get('summary') or {})
    return out


def api_violation_of(am, cid):
    """从 api_matrix 文档里取某个 ledger 条目的「违规数」（口径见 analysis_ledger.py）。

    兼容两种形状：原始 api_matrix（`violations` 是列表）与 `postfix_api_matrix` 的压平结果
    （`violations` 已是整数）。
    """
    if not am:
        return None

    def n_of(node):
        if not isinstance(node, dict):
            return None
        viol = node.get('violations')
        if isinstance(viol, int):
            return viol
        return len(viol or [])

    if cid == 'violations_total':
        return sum(n_of(am.get(k)) or 0 for k in am if k.startswith('matrix_'))
    if cid == 'CSRF.not_enforced':
        node = am.get('CSRF.not_enforced')
        if isinstance(node, dict) and 'not_enforced' in node:
            return node['not_enforced']
        csrf = am.get('matrix_f_csrf') or am.get('matrix_f') or {}
        return (csrf.get('summary') or {}).get('not_enforced')
    return n_of(am.get(cid))


def classify(suite, cid, base_verdict, post_verdict, post_present):
    key = '%s:%s' % (suite, cid)
    if not post_present:
        return 'not_rerun'
    if base_verdict in ('probe', 'see_violations', 'DIFF'):
        return 'probe_only' if base_verdict == 'probe' else 'aggregate'
    if base_verdict == 'passed' and post_verdict == 'passed':
        return 'unchanged_pass'
    if base_verdict == 'failed' and post_verdict == 'passed':
        return 'red_to_green'
    if base_verdict == 'failed' and post_verdict != 'passed':
        return 'still_red_asset' if key in ASSET_DEFECTS else 'still_red_product'
    if base_verdict == 'passed' and post_verdict != 'passed':
        if key in EXPECTED_FLIPS:
            return 'expected_flip'
        if key in ASSET_FLIPS:
            return 'asset_defect_flip'
        if key in CRITERION_INVALIDATED:
            return 'criterion_invalidated'
        return 'REGRESSION'
    return 'other'


def build(postfix_run, rewrite_run=None):
    base = load_json(BASELINE_LEDGER)
    post = load_postfix(postfix_run)
    v_post = postfix_verdicts(post)
    v_rewrite = postfix_verdicts(load_postfix(rewrite_run)) if rewrite_run else {}
    am_post = postfix_api_matrix(post)
    am_base = load_json(os.path.join(REPORTS_ROOT, 'evidence', 'api', 'api_matrix.json'))

    entries = []
    for e in base['entries']:
        suite, cid = e['suite'], e['id']
        key = '%s:%s' % (suite, cid)
        row = {'suite': suite, 'id': cid, 'title': e['title'],
               'baseline_verdict': e['verdict'], 'baseline_got': e.get('got'),
               'baseline_evidence': e.get('evidence')}
        if suite == 'api_matrix':
            bviol = api_violation_of(am_base, cid)
            pm = am_post.get(cid) or {}
            pviol = api_violation_of(am_post, cid)
            key_am = 'api_matrix:%s' % cid
            row.update({'baseline_violations': bviol, 'postfix_violations': pviol,
                        'postfix_got': pm})
            if pviol is None:
                row['class'] = 'not_rerun'
            elif cid in ('CSRF.not_enforced', 'matrix_f_csrf'):
                row['class'] = 'criterion_invalidated'
                row['class_basis'] = CRITERION_INVALIDATED.get('api_matrix:matrix_f_csrf', '')
            elif bviol == pviol:
                row['class'] = 'unchanged'
            elif pviol < bviol:
                row['class'] = 'improved'
            else:
                row['class'] = 'WORSE'
            row.setdefault('class_basis', '违规数（越小越好）')
        elif key in v_post:
            pv = v_post[key]['verdict']
            row.update({'postfix_verdict': pv, 'postfix_got': v_post[key]['got'],
                        'class': classify(suite, cid, e['verdict'], pv, True),
                        'postfix_evidence': post.get(
                            {'gate': 'gates', 'negative_matrix': 'negative_matrix',
                             'write_suite': 'write_suite', 'uat': 'uat'}.get(suite, ''),
                            {}).get('path')})
            if key in v_rewrite:
                row['rewrite_verdict'] = v_rewrite[key]['verdict']
                row['rewrite_got'] = v_rewrite[key]['got']
        else:
            row.update({'class': 'not_rerun', 'postfix_verdict': None})
        if row.get('class') == 'still_red_asset':
            row['class_basis'] = ASSET_DEFECTS[key]
        elif row.get('class') == 'expected_flip':
            row['class_basis'] = EXPECTED_FLIPS[key]
        elif row.get('class') == 'asset_defect_flip':
            row['class_basis'] = ASSET_FLIPS[key]
        elif row.get('class') == 'criterion_invalidated':
            row['class_basis'] = CRITERION_INVALIDATED.get(key, '')
        elif row.get('class') == 'REGRESSION':
            row['class_basis'] = '无 DEC/裁定依据 => 必须按阻断项报出'
        entries.append(row)

    counts = {}
    for r in entries:
        counts[r.get('class') or 'unknown'] = counts.get(r.get('class') or 'unknown', 0) + 1
    return {'run_id': RUN_ID, 'postfix_run': postfix_run, 'rewrite_run': rewrite_run,
            'baseline': {'path': os.path.relpath(BASELINE_LEDGER, REPO_ROOT).replace('\\', '/'),
                         'sha256': sha256_file(BASELINE_LEDGER),
                         'totals': base['totals'], 'suites': base['suites']},
            'postfix_sources': {k: {kk: vv for kk, vv in v.items() if kk != 'data'}
                                for k, v in post.items()},
            'counts_by_class': counts, 'entries': entries,
            'expected_flips': EXPECTED_FLIPS, 'asset_defects': ASSET_DEFECTS,
            'asset_flips': ASSET_FLIPS, 'criterion_invalidated': CRITERION_INVALIDATED}


def md_table(ledger):
    lines = ['| suite | 用例 ID | 基线 | 修复后 | 重写资产后 | 归类 | 依据 / 备注 |',
             '| --- | --- | --- | --- | --- | --- | --- |']
    for r in ledger['entries']:
        if r['suite'] == 'api_matrix':
            lines.append('| %s | %s | 违规 %s | 违规 %s | — | %s | %s |' % (
                r['suite'], r['id'], r.get('baseline_violations'), r.get('postfix_violations'),
                r.get('class'), r.get('class_basis') or ''))
            continue
        lines.append('| %s | %s | %s | %s | %s | %s | %s |' % (
            r['suite'], r['id'], r['baseline_verdict'], r.get('postfix_verdict'),
            r.get('rewrite_verdict', '—'), r.get('class'), r.get('class_basis') or ''))
    return '\n'.join(lines)


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError, OSError):
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument('--postfix-run', default=RUN_ID)
    ap.add_argument('--rewrite-run', default=os.environ.get('T9_REWRITE_RUN'))
    ap.add_argument('--markdown', action='store_true')
    args = ap.parse_args(argv)

    ledger = build(args.postfix_run, args.rewrite_run)
    print('[ledger] baseline totals = %s' % json.dumps(ledger['baseline']['totals'],
                                                       ensure_ascii=True))
    print('[ledger] postfix sources = %s' % json.dumps(
        {k: v.get('path') for k, v in ledger['postfix_sources'].items()}, ensure_ascii=True))
    print('[ledger] class counts = %s' % json.dumps(ledger['counts_by_class'],
                                                    ensure_ascii=True, sort_keys=True))
    for r in ledger['entries']:
        if r.get('class') in ('red_to_green', 'still_red_asset', 'still_red_product',
                              'expected_flip', 'asset_defect_flip', 'criterion_invalidated',
                              'REGRESSION', 'improved', 'WORSE'):
            print('  [%s] %s:%s  base=%s post=%s' % (
                r['class'], r['suite'], r['id'], r['baseline_verdict'],
                r.get('postfix_verdict', r.get('postfix_violations'))))
    p1 = save_evidence('t9-regression-ledger.json',
                       json.dumps(ledger, ensure_ascii=False, indent=1, default=str))
    print('[ledger] -> %s' % os.path.relpath(p1, REPO_ROOT).replace('\\', '/'))
    if args.markdown:
        p2 = save_evidence('t9-regression-ledger.md', md_table(ledger) + '\n')
        print('[ledger] -> %s' % os.path.relpath(p2, REPO_ROOT).replace('\\', '/'))
    hard = [r for r in ledger['entries'] if r.get('class') in ('REGRESSION', 'WORSE',
                                                              'still_red_product')]
    print('[ledger] hard findings = %d' % len(hard))
    return 0


if __name__ == '__main__':
    sys.exit(main())
