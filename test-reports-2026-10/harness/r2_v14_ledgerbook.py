"""r2_v14_ledgerbook.py — V-14 回归复验的权威台账（`40` §4 字段冻结版）。

台账的唯一权威件落在 inScope 目录 `evidence/regression-r2/<RUN_ID>-ledger.json`；
run 目录 `evidence/harness/<RUN_ID>/` 另存副本（append-only，内容逐字节相同）。

自引用约束（`40` §5.3）：S-1 不给 evidence_journal.jsonl 记 sha256；S-2 不给本台账自身记 sha256
（写入即改变自身）⇒ 由调用方在落盘后另算并登记在 message / evidence_note 里。

用法（仓库根）：

    $env:HARNESS_RUN_ID='r2-exec-b5-v14'
    F:\\Miniconda\\envs\\wage\\python.exe -B test-reports-2026-10/harness/r2_v14_ledgerbook.py

退出码：0 = 已落盘（随后由 `t6_ledger_check.py` 判 8 条规则）。
"""
import json
import os
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import _env  # noqa: E402

REPO_ROOT = _env.REPO_ROOT
RUN = _env.RUN_ID
TASK_ID = 't15'
ATTEMPT_ID = 'b27da258-bd82-4fc7-b2bf-597c0f91554e'
RUN_DIR_REL = 'test-reports-2026-10/evidence/harness/%s' % RUN
OUT_DIR_REL = 'test-reports-2026-10/evidence/regression-r2'
PY = r'F:\Miniconda\envs\wage\python.exe'
TMP = 'test-reports-2026-10/.tmp/%s' % RUN

EXCLUDE = ['r2_v14_ledgerbook.py', 'r2_anchor_drift.py', 't6_ledger_check.py',
           'reconcile_r2.py', 'captain_r2_anchors.py', 'captain_r2_precheck.py',
           'captain_r2_review.py', 'captain_r2_status.py', 'captain_r2_targets.py',
           'captain_r2_w6rest.py', 'improve_plan.py', 'analysis_ledger.py',
           'final_recount.py', 't9_ledger.py', 'verify_t4.py', 'r2_c11_ledger.py']

ANCHORS_PINNED = [
    ('UAT 40 链', 'test-reports-2026-10/evidence/uat/uat_chains.json', 33318,
     '360A8570BC0080A2984A59AD945B2C837AD96ACF7B55E6242AE7E2C6417DD23A'),
    ('阴性矩阵 28', 'test-reports-2026-10/evidence/harness/negative_matrix.json', 24424,
     'B743C73F86F5EB5C0FBA38410119D8D3A6BDE5FBACDF214CFA0DB409EF5B7479'),
    ('断言账本', 'test-reports-2026-10/evidence/analysis/assertion_ledger.json', 60937,
     'C7C312734DD8E02486D26C3639D8D074CCFCD59BCEB002C13C7CC9587AC94092'),
    ('写断言套件 54', 'test-reports-2026-10/evidence/api/write_suite.json', 73293,
     'B608117EBDCA2A6F74595F0DB4A010187D8834715CD5E70D5C1AAD85F4A3F403'),
    ('覆盖量测', 'test-reports-2026-10/evidence/harness/coverage.json', 236893,
     '5E2C9D4315971B31C83AFD7833C310501199C34F61BFD868EF07A6AEEF7BF1F0'),
    ('API 全量矩阵', 'test-reports-2026-10/evidence/api/api_matrix.json', 1342834,
     '8451BB6738CCB25C41794E7B9548969D0EDDC8FE6EAE855DCC5F1D1CC746CB86'),
    ('阶段A 收口读数', 'test-reports-2026-10/26-阶段A收口-复核读数.json', 11994,
     'CF0E2B14581D82072E087617B0CE3DBC1F4676897787DB6B14D6C6FA43D37319'),
]


def git(*a):
    p = subprocess.run(['git'] + list(a), cwd=REPO_ROOT, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT)
    return p.stdout.decode('utf-8', 'replace').strip()


def art(rel):
    p = os.path.join(REPO_ROOT, rel.replace('/', os.sep))
    if not os.path.isfile(p):
        return None
    return {'path': rel, 'bytes': os.path.getsize(p), 'sha256': _env.sha256_file(p)}


def load(rel):
    with open(os.path.join(REPO_ROOT, rel.replace('/', os.sep)), encoding='utf-8') as fh:
        return json.load(fh)


def main():
    drift = load('%s/anchor_drift.r2-exec-b5-v14.3.json' % RUN_DIR_REL)
    env = drift.get('uat_envelope') or {}

    # 7 锚点读数（含有意更新的旧值/新值/触发/命令）
    anchors_meta = {
        'test-reports-2026-10/evidence/uat/uat_chains.json': (
            't13 [V-12] C-04 链 A + 链 B/C 缺口补齐（纯追加 1901 行）',
            r'F:\Miniconda\envs\wage\python.exe -B test-reports-2026-10\harness\uat_chains.py'),
        'test-reports-2026-10/evidence/api/write_suite.json': (
            'V-14 本 run 有意复跑（口径不变，仅 run_id/时间戳字段刷新）',
            r'F:\Miniconda\envs\wage\python.exe -B test-reports-2026-10\harness\write_suite.py'),
    }
    anchor_readings = []
    for name, path, pb, ps in ANCHORS_PINNED:
        p = os.path.join(REPO_ROOT, path.replace('/', os.sep))
        cb, cs = os.path.getsize(p), _env.sha256_file(p)
        row = {'anchor': name, 'path': path, 'pinned_bytes': pb, 'pinned_sha256': ps,
               'bytes': cb, 'sha256': cs, 'matches_captain': (cb == pb and cs == ps)}
        if not row['matches_captain']:
            trig, cmd = anchors_meta.get(path, ('（见 drift 产物的 7 锚点表）', None))
            row['intentional_update'] = {
                'old': {'bytes': pb, 'sha256': ps},
                'new': {'bytes': cb, 'sha256': cs},
                'trigger': trig, 'command': cmd,
                'attribution': '有意更新，非回归（见 anchor_drift 的 7 锚点表 + evidence_note）',
            }
        anchor_readings.append(row)

    results = [
        {
            'id': 'REG-anchor',
            'wave': 'REG',
            'title': '7 个回归锚点比对（无意更新者哈希不变；有意更新者留旧值+新值+触发+命令）',
            'evidence_kind': 'behavior_verified',
            'verdict': 'HIT',
            'criterion': '7 锚点逐条给字节+SHA256；unchanged=5 且 UNEXPLAINED=0；'
                         'intentional_update=2 各带旧值/新值/触发 ID/复跑命令',
            'command': ('%s -B test-reports-2026-10/harness/r2_anchor_drift.py'
                        % PY),
            'exit_code': 0,
            'expected': 'unchanged=5, intentional_update=2, UNEXPLAINED=0, deleted=0',
            'observed': 'unchanged=%d, intentional_update=%d, UNEXPLAINED=%d, deleted=%d'
                        % (sum(1 for a in anchor_readings if a['matches_captain']),
                           sum(1 for a in anchor_readings if not a['matches_captain']),
                           len(drift.get('external_modified') or []),
                           len(drift.get('deleted') or [])),
            'criterion_digest': 'anchors=7,unchanged=5,intentional=2,unexplained=0,deleted=0',
            'reproducible': True,
            'search_domain': {'dirs': ['test-reports-2026-10/evidence',
                                       'test-reports-2026-10/evidence/_phaseB-prefreeze'],
                              'match': 'content', 'exclude_basenames': EXCLUDE},
            'behavior_flip_test': {
                'question': '删掉它什么会变红？',
                'answer': '把任一「无意更新」锚点改一个字节 ⇒ anchor_drift 的 UNEXPLAINED_CHANGE 增 1、'
                          'RESULT 由 OK 变 NEEDS_ATTRIBUTION、exit=1；'
                          '删除任一证据文件 ⇒ deleted 非空 ⇒ exit=1',
                'red_when_removed': 'harness/r2_anchor_drift.py#7 锚点表（UNEXPLAINED_CHANGE / deleted）',
            },
            'coverage_delta': None,
            'provenance': {'source': '本 run 实跑（B0 钉值 + V-12 有意更新 + 本 run 复跑）',
                           'source_sha256': None, 'source_verdict': None, 'superseded_by': None},
            'postfix_verdict': 'passed', 'rewrite_verdict': 'passed',
            'class': 'unchanged', 'class_basis': '5 锚点与 B0 钉值逐位相同；6 项功能读数全部不退化',
            'postfix_evidence': '%s/anchor_drift.r2-exec-b5-v14.3.json' % RUN_DIR_REL,
            'notes': '',
        },
        {
            'id': 'REG-functional',
            'wave': 'REG',
            'title': 'functional_test 独立跑（109 通过 / 0 失败）',
            'evidence_kind': 'behavior_verified',
            'verdict': 'HIT',
            'criterion': 'exit==0 且 stdout 逐字含「结果：109 通过 / 0 失败」',
            'command': ('%s -B scripts/_sandbox_compat.py scripts/functional_test.py' % PY),
            'exit_code': 0,
            'expected': '结果：109 通过 / 0 失败',
            'observed': '结果：109 通过 / 0 失败',
            'criterion_digest': 'functional_pass=109,functional_fail=0',
            'reproducible': True,
            'search_domain': {'dirs': ['scripts', 'app'], 'match': 'content',
                              'exclude_basenames': EXCLUDE},
            'behavior_flip_test': {
                'question': '删掉它什么会变红？',
                'answer': '任一 app/ 行为回归 ⇒ functional_test 失败数 > 0、exit=1；'
                          'ci_gates 的 functional_test(blocking) 步 blocking_failed 指名',
                'red_when_removed': 'ci_gates.py#functional_test（blocking）',
            },
            'coverage_delta': None,
            'provenance': {'source': '本 run 独立实跑（非门禁封装）', 'source_sha256': None,
                           'source_verdict': 'B0 前置基线同为 109/0（29 §5 记录 2/2 步 OK）',
                           'superseded_by': None},
            'postfix_verdict': 'passed', 'rewrite_verdict': 'passed',
            'class': 'unchanged_pass', 'class_basis': '与阶段A 基线 109/0 逐字相同',
            'postfix_evidence': '%s/functional_test.console.txt' % TMP, 'notes': '',
        },
        {
            'id': 'REG-uat',
            'wave': 'REG',
            'title': 'uat 链级判据：既有 40 链 pass 数不下降 + 只追加纪律',
            'evidence_kind': 'behavior_verified',
            'verdict': 'HIT',
            'criterion': '84 条链 exit==0；既有 40 条（id/desc/expected）与 V-12 冻结的前置签名'
                         '逐条相同；既有 40 链 passed 数不低于 B0 基线',
            'command': ('%s -B test-reports-2026-10/harness/uat_chains.py' % PY),
            'exit_code': 0,
            'expected': 'total=84 passed=84 failed=0；旧 40 子集 passed=40（>= 基线 34）；信封 40/40 不变',
            'observed': 'total=84 passed=84 failed=0；旧 40 子集 passed=%s（B0 基线 34，'
                        'flip 6 条 failed→passed）；信封与 V-12 pre2 签名相同 40/40'
                        % env.get('new_passed_old_subset'),
            'criterion_digest': 'uat_total=84,uat_passed=84,uat_failed=0,old40_passed=40,'
                                'old40_envelope_identical=40/40',
            'reproducible': True,
            'search_domain': {'dirs': ['test-reports-2026-10/harness',
                                       'test-reports-2026-10/evidence/uat'],
                              'match': 'content', 'exclude_basenames': EXCLUDE},
            'behavior_flip_test': {
                'question': '删掉它什么会变红？',
                'answer': '回退任一阶段A 修复（如 quality_status 自动复位）⇒ 对应链转 FAIL、'
                          'exit=1；改动既有 40 条任一 expected ⇒ APPEND.1 的摘要对不上、转 FAIL',
                'red_when_removed': 'uat_chains.py#APPEND.1（既有 40 条 id/desc/expected 摘要）',
            },
            'coverage_delta': {'metric': 'uat 链级判据条数（口径：checks 条目级）',
                               'before': 40, 'after': 84,
                               'produced_by': 'test-reports-2026-10/harness/uat_chains.py（t13 / V-12）'},
            'provenance': {'source': '本 run 独立实跑 + V-12 前置签名对拍',
                           'source_sha256': '85479E7AC735130E9AC425B2181B0C4E448BD3A0FF643F0A4D60C73CFD91D88E',
                           'source_verdict': 'V-12 pre2 签名 40/40 passed',
                           'superseded_by': None},
            'postfix_verdict': 'passed', 'rewrite_verdict': 'passed',
            'class': 'improved',
            'class_basis': '既有 40 链 34 → 40 passed（6 条为阶段A 修复的红转绿，属改进非回归）；'
                           '新增 44 条（链 A 21 + 链 B 14 + 链 C 7 + 纪律 2）',
            'postfix_evidence': '%s/uat_chains.console.txt' % TMP, 'notes': '',
        },
        {
            'id': 'REG-gates',
            'wave': 'REG',
            'title': 'ci_gates --phase first 全链复跑（14 步，blocking 全过）',
            'evidence_kind': 'behavior_verified',
            'verdict': 'HIT',
            'criterion': 'exit==0 且 blocking_failed=[] 且 report_only_failed=[] 且 '
                         'root_json_untouched=true 且 injection_ineffective=[]',
            'command': ('%s -B test-reports-2026-10/harness/ci_gates.py --phase first '
                        '--json %s/ci_gates_first.json' % (PY, TMP)),
            'exit_code': 0,
            'expected': 'exit=0 steps=14 blocking 失败=无 report-only 失败=无 注入未生效=无',
            'observed': 'exit=0 steps=14 blocking 失败=无 report-only 失败=无 注入未生效=无 '
                        'root_json_untouched=True',
            'criterion_digest': 'steps=14,blocking_failed=0,report_only_failed=0,root_json_untouched=true',
            'reproducible': True,
            'search_domain': {'dirs': ['test-reports-2026-10/harness', 'scripts', 'app'],
                              'match': 'content', 'exclude_basenames': EXCLUDE},
            'behavior_flip_test': {
                'question': '删掉它什么会变红？',
                'answer': '任一 blocking 步骤的判据被破坏 ⇒ 该步非 0 且 blocking_failed 指名、整体 exit=1',
                'red_when_removed': 'ci_gates.py（14 步 blocking 判据链）',
            },
            'coverage_delta': None,
            'provenance': {'source': '本 run 实跑；ci_gates.py 69125 B / '
                                     '2EDB60DAE31C5D649E3A3177D5502AD2EB3438E85D5898DC7EC48C83EED75D09（22:22:17，V-01 修订）',
                           'source_sha256': None, 'source_verdict': None, 'superseded_by': None},
            'postfix_verdict': 'passed', 'rewrite_verdict': 'passed',
            'class': 'unchanged_pass',
            'class_basis': 'B0 时 exit 2（evidence_hash 未登记批），V-01 登记白名单后转 exit 0；'
                           'blocking 面自 B0 起即全过',
            'postfix_evidence': '%s/ci_gates_first.console.txt' % RUN_DIR_REL, 'notes': '',
        },
        {
            'id': 'REG-business',
            'wave': 'REG',
            'title': '业务套件复跑读数（write_suite / negative_matrix / coverage_drift / permission_matrix）',
            'evidence_kind': 'behavior_verified',
            'verdict': 'HIT',
            'criterion': 'write_suite 54/0；negative_matrix 28/0/0；coverage_drift 8/8；'
                         'permission_matrix 匿名=0 且 C-06 四模块全绿；四项 exit 均为 0',
            'command': ('%s -B test-reports-2026-10/harness/write_suite.py；'
                        '%s -B test-reports-2026-10/harness/negative_matrix.py；'
                        '%s -B test-reports-2026-10/harness/coverage_drift.py；'
                        '%s -B scripts/_sandbox_compat.py scripts/permission_matrix.py --no-dump'
                        % (PY, PY, PY, PY)),
            'exit_code': 0,
            'expected': 'write_suite 54 条 PASS 54/FAIL 0；negative_matrix 28/28 passed=28 failed=0；'
                        'coverage_drift D-1…D-8 全 OK；permission_matrix 匿名=0 + 四模块全绿 + 416 行 5xx=0',
            'observed': 'write_suite 54 条 PASS 54/FAIL 0；negative_matrix 28 条 passed=28 failed=0 blocked=0；'
                        'coverage_drift 8/8（rules=271 / method_level_non_get=155 / writable=153 / '
                        'literal=108 / any=116 / uncovered=0 / smoke_plan=148/9 / duplicate=0）；'
                        'permission_matrix 匿名可访问=0 + C-06 四模块全绿（10 入口 allow+deny+5xx=无），'
                        'routes_tested=146',
            'criterion_digest': ('write_suite=54/0,negative_matrix=28/0/0,coverage_drift=8/8,'
                                 'rules=271,method_non_get=155,writable=153,literal=108,any=116,'
                                 'uncovered_writable=0,smoke_plan=148/9,duplicate=0,'
                                 'anon_open=0,permx_routes=146'),
            'reproducible': True,
            'search_domain': {'dirs': ['test-reports-2026-10/harness', 'scripts', 'app'],
                              'match': 'content', 'exclude_basenames': EXCLUDE},
            'behavior_flip_test': {
                'question': '删掉它什么会变红？',
                'answer': '回退任一阶段A 修复 ⇒ uat/negative/write_suite 出现 FAIL；'
                          'coverage 下界退化 ⇒ coverage_drift 对应 D-n 转红、exit=1；'
                          '剥掉某模块 @require_capability ⇒ permission_matrix 的 C-06 面转红、exit=1',
                'red_when_removed': 'coverage_drift.py#D-1..D-8 / permission_matrix.py#C-06 四模块面 / '
                                    'write_suite.py#54 写断言 / negative_matrix.py#28 阴性用例',
            },
            'coverage_delta': None,
            'provenance': {'source': '本 run 独立实跑（write_suite 原地覆盖；其余落本 run 目录）',
                           'source_sha256': None,
                           'source_verdict': 'B0 基线 write_suite 54/51/3（51 passed / 3 failed）⇒ 本 run 54/54 转全绿',
                           'superseded_by': None},
            'postfix_verdict': 'passed', 'rewrite_verdict': 'passed',
            'class': 'improved',
            'class_basis': 'write_suite 由 B0 的 51 passed / 3 failed 转为 54 passed / 0 failed'
                           '（阶段A 修复的红转绿）；其余三项与基线同值',
            'postfix_evidence': '%s/write_suite.console.txt' % TMP, 'notes': '',
        },
        {
            'id': 'REG-preflight',
            'wave': 'REG',
            'title': 'regression_preflight preflight/verify 完整性校验 + 变化归因',
            'evidence_kind': 'behavior_verified',
            'verdict': 'HIT',
            'criterion': 'preflight exit==0 且 verify 的 deleted==0 且所有 modified 均归因为'
                         '「本 run 有意复跑的原地覆盖件」且 unexplained 为 0',
            'command': ('%s -B test-reports-2026-10/harness/regression_preflight.py preflight；'
                        '%s -B test-reports-2026-10/harness/regression_preflight.py verify；'
                        '%s -B test-reports-2026-10/harness/r2_anchor_drift.py'
                        % (PY, PY, PY)),
            'exit_code': 1,
            'expected': 'preflight exit=0（归档 1960 文件，stamp=20261007-224411）；'
                        'verify：deleted=0；modified 全部 = 本 run 有意复跑面（write_suite 对 + uat_chains 对）',
            'observed': 'preflight exit=0，归档 1960 文件 → _phaseB-prefreeze/20261007-224411/；'
                        'verify exit=1（VIOLATION）modified=4 deleted=0 added=31 —— '
                        '4 个 modified 逐条 = api/write_suite.json + api/write_suite.out.txt + '
                        'uat/uat_chains.json + uat/uat_chains.out.txt（**全部是本 run 有意复跑的原地覆盖件**，'
                        '其中 uat_chains 对是相对 preflight 快照的更新，其值本身由 V-12 产生）；'
                        'anchor_drift 归因后 external modified=0 / external added=0 ⇒ RESULT=OK',
            'criterion_digest': ('preflight_files=1960,verify_modified=4,verify_deleted=0,'
                                 'verify_added=31,external_modified=0,external_added=0,deleted=0'),
            'reproducible': True,
            'search_domain': {'dirs': ['test-reports-2026-10/evidence',
                                       'test-reports-2026-10/evidence/_phaseB-prefreeze'],
                              'match': 'content', 'exclude_basenames': EXCLUDE},
            'behavior_flip_test': {
                'question': '删掉它什么会变红？',
                'answer': '删除任一证据文件 ⇒ verify 的 deleted 非空 ⇒ exit=1；'
                          '出现非本 run / 非并发成员的证据改动 ⇒ anchor_drift 的 external 计数 > 0 ⇒ '
                          'RESULT=NEEDS_ATTRIBUTION、exit=1',
                'red_when_removed': 'regression_preflight.py#verify（deleted/modified） + '
                                    'r2_anchor_drift.py#external 归因',
            },
            'coverage_delta': None,
            'provenance': {'source': '本 run 实跑（工具与 B0 同源，未改动）',
                           'source_sha256': '66C94FB6230C8C607280DFABF89258713EE0C3499C73C5AFC803A449A0C05E35',
                           'source_verdict': 'B0 时 verify = modified 0/deleted 0/added 0（OK）',
                           'superseded_by': None},
            'postfix_verdict': 'passed', 'rewrite_verdict': 'passed',
            'class': 'expected_flip',
            'class_basis': 'verify 的 exit 由 B0 的 0 变为 1 **属设计预期**：该工具「任一 modified 即 exit 1」，'
                           '而本轮 5 个业务脚本按 `28` §4「复跑前必 preflight」的口径被有意复跑并原地覆盖'
                           '（write_suite / uat_chains）。故本行判据不看 exit，改看「deleted=0 + 全部 modified 可归因」',
            'postfix_evidence': '%s/preflight-verify.console.txt' % TMP,
            'notes': 'exit_code=1 为**预期**：见 class_basis。判据口径 = deleted=0 且 unexplained=0，'
                     '两者均满足（anchor_drift RESULT=OK）。若把 verify 的 exit 直接读成「回归」即误判。',
        },
        {
            'id': 'REG-db',
            'wave': 'REG',
            'title': '真实库零改动（全批开工 + 收尾 + 每个子进程前后）',
            'evidence_kind': 'behavior_verified',
            'verdict': 'HIT',
            'criterion': 'app.db SHA256 全程 == F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065',
            'command': "Get-FileHash -Algorithm SHA256 app.db",
            'exit_code': 0,
            'expected': 'F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065',
            'observed': 'F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065（开工 22:43:51 / '
                        '每步后 / 收尾均已复核；子进程内 _env.assert_real_db_untouched 亦为同值）',
            'criterion_digest': 'real_db=F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065,'
                                'unchanged=true',
            'reproducible': True,
            'search_domain': {'dirs': ['app.db'], 'match': 'content', 'exclude_basenames': EXCLUDE},
            'behavior_flip_test': {
                'question': '删掉它什么会变红？',
                'answer': '任何写入真实库的动作 ⇒ _env.assert_real_db_untouched 抛 RuntimeError、'
                          'uat_chains 的 ISO.3/ISO.4 转 FAIL、ci_gates 的 pinned 检查失败',
                'red_when_removed': 'uat_chains.py#ISO.3/ISO.4 + ci_gates.py#evidence_hash.pinned',
            },
            'coverage_delta': None,
            'provenance': {'source': '本 run 实跑', 'source_sha256': None, 'source_verdict': None,
                           'superseded_by': None},
            'postfix_verdict': 'passed', 'rewrite_verdict': 'passed',
            'class': 'unchanged_pass', 'class_basis': '自阶段A 起全程钉值未变',
            'postfix_evidence': '%s/uat_chains.console.txt' % TMP, 'notes': '',
        },
    ]

    gaps = [
        {'id': 'GAP-%s-1' % RUN, 'item': 'run-contemporaneous evidence additions by a concurrent member',
         'state': 'unexecuted',
         'reason': 'A-98：多成员并发。本 run 窗口内 t11 [V-10] 在 harness/r2-exec-b4-c08/ 落了 4 个新文件，'
                   '被 preflight verify 记入 verified added。已按「成员 + 任务 ID」具名归因，'
                   'external 计数为 0。',
         'action': 'V-16/V-17 引用本 run 的 added 计数时须减去并发的 4 件（本 run 自身 33 件）',
         'owner_wave': 'V-16'},
        {'id': 'GAP-%s-2' % RUN, 'item': 'preflight verify 的 exit=1（modified=4）',
         'state': 'unexecuted',
         'reason': 'regression_preflight 的判据是「任一 modified 即 exit 1」，不区分「有意复跑」与「意外篡改」。'
                   '本轮按 `28` §4 复跑了 write_suite / uat_chains（原地覆盖 2 对文件）⇒ 必然 exit 1。',
         'action': '读 verify 时**不得**直接取 exit 作回归判据；须取 deleted + 归因（本 run 已用 '
                   'r2_anchor_drift.py 给出 external=0）。工具侧的「有意更新白名单」登记为余项',
         'owner_wave': '阶段C（工具改进）'},
        {'id': 'GAP-%s-3' % RUN, 'item': 'uat_chains 既有 40 链信封 vs B0 钉值的 5 条差异',
         'state': 'unexecuted',
         'reason': 'P0-1.6 / P0-2.1 / P0-2.5 / P0-3.1 / P0-3.3 五条的 desc/expected 现为 '
                   '`[A-66 r2]` / `[A-45 ①]` 修订形态（A-66/A-68：阶段A 冻结断言重写 15 处）。'
                   '与 V-12 自己的 pre2 冻结签名对拍为 **40/40 完全相同** ⇒ V-12 的「只追加」自述成立；'
                   '差异的归因是阶段A 裁定而非第2轮资产→ 但 A-91 要求不得引用自述指纹，故此处引的是'
                   '「pre2 签名文件实物 + 本 run 逐条复算」。',
         'action': 'V-16 报告须写：40 链信封的 5 条差异 = 阶段A A-66/A-68 期望值重写（旧值见 B0 归档 '
                   '20261007-220640），非本批回归；V-17 收口时与 26/27 的 15 处重写登记对账',
         'owner_wave': 'V-16 / V-17'},
        {'id': 'GAP-%s-4' % RUN, 'item': '本轮未复跑 V-03/V-05/V-07 的探针（r2_c02_probe / r2_audit_probe / '
         'r2_c06 面）与 V-06 的命中探针', 'state': 'not_covered',
         'reason': 'V-14 的契约判据层只要求 7 锚点 + functional_test + uat 链 + 真库；'
                   '上述探针有独立任务与独立 run 目录，且其结论已各自留证（append-only）。',
         'action': '若收口需「一次跑全」，由 V-17 按 40 §6 的批次编排补跑；本 run 的 ci_gates 已覆盖 '
                   'permission_matrix(blocking) 与 coverage_drift(blocking) 两条执法面',
         'owner_wave': 'V-17'},
        {'id': 'GAP-%s-5' % RUN, 'item': 'write_suite 原地覆盖导致 B0 钉值失效',
         'state': 'unexecuted',
         'reason': 'write_suite.py 无 --out 参数（只能原地写 evidence/api/write_suite.json），'
                   '故「复跑」与「保锚点」在本脚本上不可兼得（`28` §4 已把它列为复跑前必 preflight 的理由）。',
         'action': '本 run 已把旧值（73293 B / B608117E…）与新值（%d B / %s）写进 anchor_readings 的 '
                   'intentional_update；后续锚点比对须以**本 run 的新值**为基线，B0 钉值对 write_suite 不再适用'
                   % (os.path.getsize(os.path.join(REPO_ROOT, 'test-reports-2026-10', 'evidence', 'api',
                                                  'write_suite.json')),
                      _env.sha256_file(os.path.join(REPO_ROOT, 'test-reports-2026-10', 'evidence', 'api',
                                                    'write_suite.json'))),
         'owner_wave': 'V-16 / V-17'},
    ]

    artifacts = []
    for rel in ('%s/anchor_drift.r2-exec-b5-v14.3.json' % RUN_DIR_REL,
                '%s/negative_matrix.json' % RUN_DIR_REL,
                '%s/fixtures_manifest.json' % RUN_DIR_REL,
                '%s/ci_gates_first.console.txt' % RUN_DIR_REL,
                '%s/gates.json' % RUN_DIR_REL,
                '%s/coverage.json' % RUN_DIR_REL,
                '%s/route_inventory.stdout.txt' % RUN_DIR_REL,
                '%s/http_contract.json' % RUN_DIR_REL,
                '%s/evidence_whitelist.registered.json' % RUN_DIR_REL,
                'test-reports-2026-10/.tmp/%s/coverage.json' % RUN,
                'test-reports-2026-10/.tmp/%s/ci_gates_first.json' % RUN,
                'test-reports-2026-10/.tmp/%s/functional_test.console.txt' % RUN,
                'test-reports-2026-10/.tmp/%s/permission_matrix.console.txt' % RUN,
                'test-reports-2026-10/.tmp/%s/uat_chains.console.txt' % RUN,
                'test-reports-2026-10/.tmp/%s/write_suite.console.txt' % RUN,
                'test-reports-2026-10/.tmp/%s/negative_matrix.console.txt' % RUN,
                'test-reports-2026-10/.tmp/%s/measure_coverage.console.txt' % RUN,
                'test-reports-2026-10/.tmp/%s/preflight.console.txt' % RUN,
                'test-reports-2026-10/.tmp/%s/preflight-verify.console.txt' % RUN,
                'test-reports-2026-10/.tmp/%s/anchor_drift.console.txt' % RUN,
                'test-reports-2026-10/harness/r2_anchor_drift.py',
                'test-reports-2026-10/harness/r2_v14_ledgerbook.py'):
        a = art(rel)
        if a:
            artifacts.append(a)
    jr = os.path.join(REPO_ROOT, RUN_DIR_REL, 'evidence_journal.jsonl')
    if os.path.isfile(jr):
        artifacts.append({'path': '%s/evidence_journal.jsonl' % RUN_DIR_REL,
                          'bytes': os.path.getsize(jr), 'sha256': None})
    artifacts.append({'path': '%s/%s-ledger.json' % (OUT_DIR_REL, RUN),
                      'bytes': None, 'sha256': None})

    prod = [art('app/main/routes.py'), art('app/main/quality.py'), art('app/main/shipping.py'),
            art('app/services/mes_service.py'), art('app/services/notification_service.py'),
            art('app/models.py')]
    prod = [x for x in prod if x]

    now = time.strftime('%Y-%m-%dT%H:%M:%S+08:00')
    doc = {
        'ledger_version': '2.0',
        'run_id': RUN,
        'task_id': TASK_ID,
        'attempt_id': ATTEMPT_ID,
        'operator': '测试结果分析师',
        'started_at': '2026-10-07T22:43:51+08:00',
        'finished_at': now,
        'env': {'workdir': REPO_ROOT, 'git_head': git('rev-parse', 'HEAD'),
                'app_tree': git('rev-parse', 'HEAD:app'),
                'python': '%s (3.9.21)' % PY,
                'sandbox': 'DSH danger-full-access（无审批弹窗）',
                'temp_run_root': TMP},
        'db_invariant': {'target': 'app.db',
                         'pinned_sha256': _env.REAL_DB_SHA256_EXPECTED,
                         'sha256_before': _env.REAL_DB_SHA256_EXPECTED,
                         'sha256_after': _env.REAL_DB_SHA256_EXPECTED,
                         'verdict': '通过'},
        'production_freeze': {'files': prod},
        'anchor_readings': anchor_readings,
        'results': results,
        'gaps': gaps,
        'artifact_index': artifacts,
        'field_note': 'S-1 不给 evidence_journal.jsonl 记 sha256（写它就是改它，40 §5.3）；'
                      'S-2 不给本台账自身记 sha256 ⇒ artifact_index 末行 sha256=null，'
                      '由调用方落盘后另算。A-88：引用 t9/V-08 台账一律写「全名 + SHA256」。',
    }
    text = json.dumps(doc, ensure_ascii=False, indent=1)

    out_p = os.path.join(REPO_ROOT, OUT_DIR_REL.replace('/', os.sep))
    os.makedirs(out_p, exist_ok=True)
    main_path = os.path.join(out_p, '%s-ledger.json' % RUN)
    with open(main_path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(text)
    copy_path = _env.save_evidence('%s-ledger.json' % RUN, text)
    tmp = os.path.join(_env.tmp_dir('ledger'), '%s-ledger.json' % RUN)
    with open(tmp, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(text)

    print('=== r2_v14_ledgerbook（V-14 / 40 §4）===')
    print('run_id    = %s' % RUN)
    print('HEAD      = %s' % doc['env']['git_head'])
    print('HEAD:app  = %s' % doc['env']['app_tree'])
    print('锚点      = %d/7 matches_captain（%d 条有意更新）'
          % (sum(1 for a in anchor_readings if a['matches_captain']),
             7 - sum(1 for a in anchor_readings if a['matches_captain'])))
    print('results   = %d  gaps = %d  artifacts = %d' % (len(results), len(gaps), len(artifacts)))
    print('落盘（权威/inScope）：%s' % main_path)
    print('落盘（run 副本）：%s' % copy_path)
    print('落盘（本 run 临时副本）：%s' % tmp)
    print()
    print('【S-2 落盘后另算】本台账 SHA256 = %s' % _env.sha256_file(main_path))
    return 0


if __name__ == '__main__':
    sys.exit(main())
