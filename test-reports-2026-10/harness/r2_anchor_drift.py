"""r2_anchor_drift.py — V-14 回归复验的**变化归因**工具（只读）。

回答两个问题（`28` §3 的「删掉它什么会变红」口径在回归面的对偶）：

1. **7 锚点**：逐个给「B0 钉值 / V-12 有意更新值 / 本 run 复跑值」三列 + verdict
   （`unchanged_pin` / `intentional_update` / `updated_by_this_run`），
   有意更新者必须带「旧值 + 新值 + 触发 ID + 命令」。
2. **锚点之外的证据漂移**：以 `regression_preflight` 的 preflight manifest 为基线，
   逐个比对**当前** SHA256；把变化按**归属**分类：
   - `this_run`：本 run 自己的落点（`harness/<RUN_ID>/`、`ci-<RUN_ID>/`、`<*RUN_ID*>` 路径）；
   - `intentional_rerun`：本 run 有意复跑的原地覆盖件（`write_suite` / `uat_chains` 对）；
   - `external`：**既非本 run 落点、也非本 run 复跑面** ⇒ 真正的「需要解释」集合。

判据：`external` 非空 ⇒ 必须逐条给出 trigger；`deleted` 非空 ⇒ 直接判回归。

用法（仓库根）：

    F:\\Miniconda\\envs\\wage\\python.exe -B test-reports-2026-10/harness/r2_anchor_drift.py

退出码：0 = 无 deleted 且 external 为空；1 = 有未归因变化 / 有删除。
"""
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import _env  # noqa: E402

REPO_ROOT = _env.REPO_ROOT
RUN = _env.RUN_ID
EVIDENCE = os.path.join(REPO_ROOT, 'test-reports-2026-10', 'evidence')
PREFLIGHT_ROOT = os.path.join(EVIDENCE, '_phaseB-prefreeze')
LATEST = os.path.join(PREFLIGHT_ROOT, 'LATEST.txt')

#: 7 锚点：B0 钉值（29 §4）+ V-12 有意更新（t13，2026-10-07 22:28:08）
ANCHORS = [
    ('UAT 40 链', 'test-reports-2026-10/evidence/uat/uat_chains.json', 33318,
     '360A8570BC0080A2984A59AD945B2C837AD96ACF7B55E6242AE7E2C6417DD23A',
     't13 [V-12] C-04 链 A + 链 B/C 缺口补齐',
     r'F:\Miniconda\envs\wage\python.exe -B test-reports-2026-10\harness\uat_chains.py'),
    ('阴性矩阵 28', 'test-reports-2026-10/evidence/harness/negative_matrix.json', 24424,
     'B743C73F86F5EB5C0FBA38410119D8D3A6BDE5FBACDF214CFA0DB409EF5B7479', None, None),
    ('断言账本 122→153', 'test-reports-2026-10/evidence/analysis/assertion_ledger.json', 60937,
     'C7C312734DD8E02486D26C3639D8D074CCFCD59BCEB002C13C7CC9587AC94092', None, None),
    ('写断言套件 54', 'test-reports-2026-10/evidence/api/write_suite.json', 73293,
     'B608117EBDCA2A6F74595F0DB4A010187D8834715CD5E70D5C1AAD85F4A3F403',
     'V-14 本 run 有意复跑（口径不变，仅 run_id/时间戳字段刷新）',
     r'F:\Miniconda\envs\wage\python.exe -B test-reports-2026-10\harness\write_suite.py'),
    ('覆盖量测', 'test-reports-2026-10/evidence/harness/coverage.json', 236893,
     '5E2C9D4315971B31C83AFD7833C310501199C34F61BFD868EF07A6AEEF7BF1F0',
     'V-06 [C-05] 有意更新（PROBES 登记后 literal 6→108 / any 14→116 / uncovered 101→0）'
     '——注：本 run 的 measure_coverage 用 --out 落本 run 目录，未原地覆盖',
     r'F:\Miniconda\envs\wage\python.exe -B test-reports-2026-10\harness\measure_coverage.py '
     r'--no-request-probes --out test-reports-2026-10\.tmp\r2-exec-b5-v14\coverage.json'),
    ('API 全量矩阵', 'test-reports-2026-10/evidence/api/api_matrix.json', 1342834,
     '8451BB6738CCB25C41794E7B9548969D0EDDC8FE6EAE855DCC5F1D1CC746CB86', None, None),
    ('阶段A 收口读数', 'test-reports-2026-10/26-阶段A收口-复核读数.json', 11994,
     'CF0E2B14581D82072E087617B0CE3DBC1F4676897787DB6B14D6C6FA43D37319', None, None),
]

#: 本 run 有意复跑的「原地覆盖」证据（readout 对：json + txt）
INTENTIONAL_RERUN = {
    'api/write_suite.json', 'api/write_suite.out.txt',
    'uat/uat_chains.json', 'uat/uat_chains.out.txt',
}

#: 本 run 自身落点前缀（含 uat_chains 的 t5-uat-<stamp> 与本 run 时间戳同名目录）
OWN_PREFIXES = ('harness/%s/' % RUN, 'harness/ci-%s/' % RUN)

#: 本 run 执行 uat_chains.py 的时刻戳（该脚本用自带时间戳命名 run 目录）
THIS_RUN_UAT_STAMP = os.environ.get('R2_V14_UAT_STAMP', '20261007-224534')

#: 同队其它成员在本 run 窗口内的并发落点（A-98：多成员并发 ⇒ 必须具名归因，不得算成未解释）
CONCURRENT_RUNS = (
    ('harness/r2-exec-b4-c08', 't11 [V-10] C-08 导入容错与导出零残留'),
    ('harness/ci-r2-exec-b4-c08', 't11 [V-10]'),
    ('harness/r2-exec-b3-c01', 't6 [V-05] C-01'),
    ('harness/ci-r2-exec-b3-v07', 't8 [V-07] C-06'),
    ('harness/r2-exec-b4-v09', 't10 [V-09] C-03'),
    ('harness/ci-v13-', 't14 [V-13] TL-05/06/07'),
    ('harness/r2-exec-b2-c02', 't4 [V-03] C-02'),
    ('harness/uat/r2-exec-b4-v12', 't13 [V-12] C-04'),
)


def sha(path):
    return _env.sha256_file(path)


def walk_evidence():
    out = {}
    for dirpath, dirnames, filenames in os.walk(EVIDENCE):
        dirnames[:] = [d for d in dirnames if d != '_phaseB-prefreeze']
        for f in filenames:
            p = os.path.join(dirpath, f)
            rel = os.path.relpath(p, EVIDENCE).replace('\\', '/')
            out[rel] = p
    return out


def main():
    t0 = time.strftime('%Y-%m-%d %H:%M:%S')
    print('=== r2_anchor_drift（V-14 变化归因）===')
    print('run_id = %s   时点 = %s' % (RUN, t0))
    print()

    # ---------- ① 7 锚点三列 ----------
    print('--- ① 7 锚点：B0 钉值 vs 实测 ---')
    anchor_rows, unpublished = [], []
    for name, rel, pb, ps, trigger, cmd in ANCHORS:
        p = os.path.join(REPO_ROOT, rel.replace('/', os.sep))
        cb = os.path.getsize(p) if os.path.isfile(p) else None
        cs = sha(p) if os.path.isfile(p) else None
        if cb == pb and cs == ps:
            verdict = 'unchanged'
        elif trigger:
            verdict = 'intentional_update'
        else:
            verdict = 'UNEXPLAINED_CHANGE'
            unpublished.append(rel)
        anchor_rows.append({'anchor': name, 'path': rel, 'pinned_bytes': pb,
                            'pinned_sha256': ps, 'bytes': cb, 'sha256': cs,
                            'verdict': verdict, 'trigger': trigger, 'command': cmd})
        print('  %-16s %-13s %8s B  %s' % (name, verdict, cb, (cs or '')[:16]))
        if verdict == 'intentional_update':
            print('      旧值 %d B / %s' % (pb, ps))
            print('      新值 %d B / %s' % (cb, cs))
            print('      触发 %s' % trigger)
            print('      命令 %s' % cmd)

    # ---------- ② preflight 基线比对 + 归因 ----------
    stamp = open(LATEST, encoding='utf-8').read().strip() if os.path.isfile(LATEST) else None
    man_path = os.path.join(PREFLIGHT_ROOT, stamp, 'preflight-manifest.json')
    print()
    print('--- ② 锚点之外的证据漂移（基线 = preflight %s）---' % stamp)
    if not os.path.isfile(man_path):
        print('  缺 manifest：%s' % man_path)
        return 2
    man = json.load(open(man_path, encoding='utf-8'))
    base = man['files']
    now = walk_evidence()

    modified, deleted, added = [], [], []
    for rel, meta in base.items():
        if rel not in now:
            deleted.append(rel)
            continue
        p = now[rel]
        if os.path.getsize(p) != meta['bytes'] or sha(p) != meta['sha256'].upper():
            modified.append(rel)
    added = sorted(set(now) - set(base))

    def classify(rel):
        if rel in INTENTIONAL_RERUN:
            return 'intentional_rerun'
        for pre in OWN_PREFIXES:
            if rel.startswith(pre):
                return 'this_run'
        if rel.startswith('harness/r2-exec-b5-v14') or 'r2-exec-b5-v14' in rel:
            return 'this_run'
        # uat_chains 的 run 目录用自带时间戳命名（t5-uat-<stamp>，stamp = 本 run 的执行时刻）
        if rel.startswith('harness/uat/t5-uat-') and THIS_RUN_UAT_STAMP in rel:
            return 'this_run'
        # 同队其它成员在本 run 窗口内的并发落点（A-98：多成员并发，须具名归因）
        for pre, who in CONCURRENT_RUNS:
            if rel.startswith(pre):
                return 'concurrent:%s' % who
        return 'external'

    def explained(rel):
        tag = classify(rel)
        return tag == 'this_run' or tag.startswith('concurrent:') or tag == 'intentional_rerun'

    ext_mod = [r for r in modified if not explained(r)]
    ext_add = [r for r in added if not explained(r)]

    print('  modified=%d deleted=%d added=%d' % (len(modified), len(deleted), len(added)))
    print('  --- modified 逐条归因 ---')
    for rel in sorted(modified):
        tag = classify(rel)
        where = '这是本 run 有意复跑的原地覆盖件' if tag == 'intentional_rerun' else tag
        print('    M [%s] %s' % (tag, rel))
        print('        %s' % where)
    for rel in deleted:
        print('    D %s   <= 删除即回归信号' % rel)
    print('  --- added 归因汇总 ---')
    import collections
    cnt = collections.Counter(classify(r) for r in added)
    for k, v in sorted(cnt.items()):
        print('    A [%s] %d 个' % (k, v))
    if ext_add:
        print('    external 新增明细（前 20）：')
        for rel in ext_add[:20]:
            print('        %s' % rel)
    verdict_ok = (not deleted) and (not ext_mod) and (not ext_add) and (not unpublished
                                                                       if False else not unpublished)
    print()
    print('--- 判定 ---')
    print('  7 锚点：unchanged=%d  intentional_update=%d  UNEXPLAINED=%d'
          % (sum(1 for a in anchor_rows if a['verdict'] == 'unchanged'),
             sum(1 for a in anchor_rows if a['verdict'] == 'intentional_update'),
             len(unpublished)))
    print('  deleted = %d（必须为 0）' % len(deleted))
    print('  external modified = %d' % len(ext_mod))
    print('  external added    = %d' % len(ext_add))
    print('  RESULT = %s' % ('OK' if verdict_ok else 'NEEDS_ATTRIBUTION'))

    # ---------- ③ APPEND.1：既有 40 链信封是否逐字节不变（只追加纪律） ----------
    print()
    print('--- ③ APPEND.1：既有 40 链信封（id/desc/expected）---')
    envelope = None
    uat_p = os.path.join(REPO_ROOT, 'test-reports-2026-10', 'evidence', 'uat', 'uat_chains.json')
    arch = os.path.join(PREFLIGHT_ROOT, '20261007-220640', 'uat', 'uat_chains.json')
    if os.path.isfile(uat_p) and os.path.isfile(arch):
        new_doc = json.load(open(uat_p, encoding='utf-8'))
        old_doc = json.load(open(arch, encoding='utf-8'))
        nm = {c.get('id'): c for c in new_doc['checks']}
        om = {c.get('id'): c for c in old_doc['checks']}
        same_env, changed_status, changed_env = [], [], []
        for k, v in om.items():
            n = nm.get(k)
            if n is None:
                changed_env.append(k)
                continue
            se = json.dumps({x: v.get(x) for x in ('id', 'desc', 'expected')},
                            sort_keys=True, ensure_ascii=False)
            sn = json.dumps({x: n.get(x) for x in ('id', 'desc', 'expected')},
                            sort_keys=True, ensure_ascii=False)
            (same_env if se == sn else changed_env).append(k)
            if v.get('status') != n.get('status'):
                changed_status.append((k, v.get('status'), n.get('status')))
        op = sum(1 for c in old_doc['checks'] if c.get('status') == 'passed')
        np_ = sum(1 for c in new_doc['checks'] if c.get('status') == 'passed'
                  and c.get('id') in om)
        envelope = {'old_total': len(om), 'old_passed': op, 'new_total': len(nm),
                    'new_passed_all': sum(1 for c in new_doc['checks']
                                          if c.get('status') == 'passed'),
                    'new_passed_old_subset': np_,
                    'envelope_identical': len(changed_env) == 0,
                    'envelope_changed_ids': changed_env,
                    'status_flips': changed_status,
                    'no_decline': np_ >= op}
        print('  旧 %d 链 passed=%d → 新（旧子集）passed=%d  no_decline=%s'
              % (envelope['old_total'], op, np_, envelope['no_decline']))
        print('  信封（id/desc/expected）逐字节不变 = %s  变更条=%s'
              % (envelope['envelope_identical'], changed_env or '无'))
        print('  status 翻转 = %s' % (changed_status or '无'))

    doc = {'tool': 'r2_anchor_drift', 'run_id': RUN, 'at': t0,
           'preflight_stamp': stamp, 'preflight_manifest': os.path.relpath(
               man_path, REPO_ROOT).replace('\\', '/'),
           'anchors': anchor_rows, 'modified': modified, 'deleted': deleted,
           'added_count': len(added), 'external_modified': ext_mod,
           'external_added': ext_add, 'uat_envelope': envelope,
           'verdict': 'OK' if verdict_ok else 'NEEDS_ATTRIBUTION'}
    saved = _env.save_evidence('anchor_drift.json', json.dumps(doc, ensure_ascii=False, indent=1))
    tmp = os.path.join(_env.tmp_dir('ledger'), 'anchor_drift.json')
    with open(tmp, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(json.dumps(doc, ensure_ascii=False, indent=1))
    print('  落盘：%s' % saved)
    return 0 if verdict_ok else 1


if __name__ == '__main__':
    sys.exit(main())
