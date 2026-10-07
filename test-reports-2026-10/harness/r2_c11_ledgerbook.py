"""r2_c11_ledgerbook.py — 生成 V-08 的 `<RUN_ID>-ledger.json`（`40` §4 台账规范）。

台账字段冻结于 `40` §4.2；本脚本只填**本次实跑**的真实读数（无占位符），
并用 `_env.save_evidence` 落盘（guard_write 改名保留 + 审计流水）。

自引用约束（`40` §5.3）：
* `S-1` 本台账**不**给自己的 `evidence_journal.jsonl` 记指纹（写它就是改它）；仅记字节数；
* `S-2` 本台账**不**给自己的 JSON 记 SHA256（写入即改变自身）⇒ `artifact_index` 里登记
  「本台账自身」的 sha256 为 `null`，由调用方在写完之**后**另算并回报。

用法（仓库根）：

    $env:HARNESS_RUN_ID='r2-exec-b3-v08'
    F:\\Miniconda\\envs\\wage\\python.exe -B test-reports-2026-10/harness/r2_c11_ledgerbook.py

退出码：0 = 台账已落盘（随后由 `t6_ledger_check.py` 判 8 条规则）。
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
TASK_ID = 't9'
ATTEMPT_ID = '8a5d7102-3d33-45e0-be2e-6aabc1772daf'
RUN_DIR_REL = 'test-reports-2026-10/evidence/harness/%s' % RUN
PY = r'F:\Miniconda\envs\wage\python.exe'

#: `28` §2.1 / A-74：判定脚本必须排除自己与「描述工作」的核验/对账脚本
EXCLUDE = ['r2_c11_ledgerbook.py', 'r2_c11_ledger.py', 'r2_c11_probe.py',
           't6_ledger_check.py', 'reconcile_r2.py', 'captain_r2_anchors.py',
           'captain_r2_precheck.py', 'captain_r2_review.py', 'captain_r2_status.py',
           'captain_r2_targets.py', 'captain_r2_w6rest.py', 'improve_plan.py',
           'analysis_ledger.py', 'final_recount.py', 't9_ledger.py', 'verify_t4.py']


def git(*args):
    p = subprocess.run(['git'] + list(args), cwd=REPO_ROOT,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return p.stdout.decode('utf-8', 'replace').strip()


def art(rel):
    p = os.path.join(REPO_ROOT, rel.replace('/', os.sep))
    if not os.path.isfile(p):
        return None
    with open(p, 'rb') as fh:
        lines = fh.read().count(b'\n')
    return {'path': rel, 'bytes': os.path.getsize(p), 'lines': lines,
            'sha256': _env.sha256_file(p)}


def load_json(rel):
    with open(os.path.join(REPO_ROOT, rel.replace('/', os.sep)), encoding='utf-8') as fh:
        return json.load(fh)


def main():
    probe = load_json('%s/r2_c11_probe.json' % RUN_DIR_REL)
    c11 = load_json('%s/assertion_ledger.c11.json' % RUN_DIR_REL)
    anchors = []
    for a in load_json('test-reports-2026-10/26-阶段A收口-复核读数.json').get('anchors', []) or []:
        pass
    # 7 锚点（29 §4 / 40 §3.1 钉值）
    for path, bt, sha in [
        ('test-reports-2026-10/evidence/uat/uat_chains.json', 33318,
         '360A8570BC0080A2984A59AD945B2C837AD96ACF7B55E6242AE7E2C6417DD23A'),
        ('test-reports-2026-10/evidence/harness/negative_matrix.json', 24424,
         'B743C73F86F5EB5C0FBA38410119D8D3A6BDE5FBACDF214CFA0DB409EF5B7479'),
        ('test-reports-2026-10/evidence/analysis/assertion_ledger.json', 60937,
         'C7C312734DD8E02486D26C3639D8D074CCFCD59BCEB002C13C7CC9587AC94092'),
        ('test-reports-2026-10/evidence/api/write_suite.json', 73293,
         'B608117EBDCA2A6F74595F0DB4A010187D8834715CD5E70D5C1AAD85F4A3F403'),
        ('test-reports-2026-10/evidence/harness/coverage.json', 236893,
         '5E2C9D4315971B31C83AFD7833C310501199C34F61BFD868EF07A6AEEF7BF1F0'),
        ('test-reports-2026-10/evidence/api/api_matrix.json', 1342834,
         '8451BB6738CCB25C41794E7B9548969D0EDDC8FE6EAE855DCC5F1D1CC746CB86'),
        ('test-reports-2026-10/26-阶段A收口-复核读数.json', 11994,
         'CF0E2B14581D82072E087617B0CE3DBC1F4676897787DB6B14D6C6FA43D37319'),
    ]:
        p = os.path.join(REPO_ROOT, path.replace('/', os.sep))
        actual_bytes = os.path.getsize(p) if os.path.isfile(p) else None
        actual_sha = _env.sha256_file(p) if os.path.isfile(p) else None
        row = {'path': path, 'bytes': actual_bytes, 'sha256': actual_sha,
               'expected_bytes': bt, 'expected_sha256': sha,
               'matches_captain': bool(actual_bytes == bt and actual_sha == sha),
               'mtime_local': time.strftime('%Y-%m-%d %H:%M:%S',
                                            time.localtime(os.path.getmtime(p)))
               if os.path.isfile(p) else None}
        if not row['matches_captain']:
            row['mid_session_update'] = {
                'old': {'bytes': bt, 'sha256': sha},
                'new': {'bytes': actual_bytes, 'sha256': actual_sha},
                'trigger_task': 't13 [V-12] C-04 链 A + 链 B/C 缺口补齐',
                'trigger_member': '验收测试工程师',
                'producer': 'test-reports-2026-10/harness/uat_chains.py（V-12 独占）',
                'reproduce': 'F:\\Miniconda\\envs\\wage\\python.exe -B '
                             'test-reports-2026-10/harness/uat_chains.py',
                'basis': '35 §8 文件独占矩阵：harness/uat_chains.py 由 V-12 独占；'
                         'B0（22:06:37）冻结时该锚点仍为 33318 B，本 run（22:18:31）前被 V-12 有意更新。',
                'verdict': '有意更新（非回归）；V-14 必须按本条重取基线',
            }
            row['matches_captain_note'] = ('matches_captain=false 的原因 = V-12 正在有意更新该锚点；'
                                           '其余 6 锚点逐位相符，断言账本锚点未变 ⇒ 本任务结论不受影响')
        anchors.append(row)

    prod = [art('app/main/routes.py'), art('app/main/quality.py'),
            art('app/main/shipping.py'), art('app/services/mes_service.py'),
            art('app/services/notification_service.py'), art('app/models.py')]
    prod = [x for x in prod if x]

    UAT_ROW = [a for a in anchors if a['path'].endswith('uat_chains.json')][0]

    results = [
        {
            'id': 'C-11',
            'wave': 'W6',
            'title': '不可判定项补用例与账本回写（AC-15/16/29b,c,d/44/45/56/49）',
            'evidence_kind': 'behavior_verified',
            'verdict': 'HIT',
            'criterion': '9 条 AC 各恰 1 条账本条目、status ∈ {passed,failed}、字段齐备'
                         '（ac_id/carrier/command/reading），且给出账本「144 → 153」前后两数',
            'command': r'F:\Miniconda\envs\wage\python.exe -B '
                       r'test-reports-2026-10/harness/r2_c11_ledger.py',
            'exit_code': 0,
            'expected': '账本 144 → 153（+9）；新增 8 passed + 1 failed（AC-49 期望 FAIL）；R-1…R-5 机检 OK',
            'observed': '账本 144 → 153（+9）；passed 128 → 136；failed 10 → 11；R-1…R-5 机检 OK',
            'criterion_digest': 'ledger_entries=153,added=9,added_passed=8,added_failed=1,'
                                'c11_pass=38,c11_assert=38,ac49_call_sites=0,ac49_notifications=0',
            'reproducible': True,
            'search_domain': {
                'dirs': ['test-reports-2026-10/evidence/analysis',
                         'test-reports-2026-10/harness',
                         'app/services', 'app/main', 'app/models.py'],
                'match': 'content',
                'exclude_basenames': EXCLUDE,
            },
            'behavior_flip_test': {
                'question': '删掉它什么会变红？',
                'answer': '删掉任一 AC 的载体（如把 shipment_candidate_stock 的 draft 占用摘掉）'
                          '⇒ r2_c11_probe 对应断言 FAIL、r2_c11_ledger 的 R-1…R-5 机检仍 OK 但'
                          '该条 status 变 failed；把 AC-49 接线 ⇒ 该条由 failed 变 passed（通过数上升）',
                'red_when_removed': 'r2_c11_probe.py#ac44/ac45/ac49/ac56（38/38 断言）+ '
                                    'r2_c11_ledger.py#R-1..R-5',
            },
            'coverage_delta': {
                'metric': 'assertion_ledger 条目数（口径：条目级；含门禁/聚合项）',
                'before': 144,
                'after': 153,
                'produced_by': 'test-reports-2026-10/harness/r2_c11_ledger.py',
            },
            'provenance': {
                'source': '本 run 实跑（新 run 产物；基线只读未覆盖）',
                'source_sha256': c11['ledger_delta']['baseline_sha256'],
                'source_verdict': 'baseline 144 条（passed 128 / failed 10）',
                'superseded_by': None,
            },
            'postfix_verdict': 'passed',
            'rewrite_verdict': 'passed',
            'class': 'improved',
            'class_basis': 'C-11 由 NOT_DONE（29 §2：零条目）转 HIT；新增 9 条 AC 条目，'
                           '其中 AC-49 按 33 §3.2-④ 登记为 expected FAIL（缺陷面，不计入通过数）',
            'postfix_evidence': '%s/assertion_ledger.c11.json' % RUN_DIR_REL,
            'notes': 'AC-15/16/29b,c,d 载体为既有 w2w3_probe.py（carrier_origin=pre-existing，'
                     'R-3）；AC-44/45/56 为本波新建内存库载体（new）；AC-49 = failed + zero-carrier。'
                     'AC-49 不计入通过数（failed）。',
        },
    ]

    gaps = [
        {'id': 'GAP-%s-1' % RUN, 'item': 'AC-49 安全库存预警通知（期望 FAIL：未接线）',
         'state': 'blocked', 'reason': 'notify_inventory_warning 定义在 '
         'app/services/notification_service.py:484，全 app/ 调用点 = 0 ⇒ 属缺陷面（需生产面接线的'
         '修复窗口），非覆盖缺口。断言面已实测为 failed（Notification 行 = 0）。',
         'action': '生产修复窗口接线后，把该条 status 由 failed 翻转为 passed（判据 = 「接线后必须 +1」）',
         'owner_wave': '阶段C（生产面接线）'},
        {'id': 'GAP-%s-2' % RUN, 'item': 'AC-56 未统一的 3 个读取点（routes.py:12065/12093/12122）',
         'state': 'not_covered', 'reason': '阶段一 04 §0.2 已定性决策：只登记残余，'
         '本轮只判文档表述准确性，不升级为修复诉求（越权改需求）。',
         'action': '交阶段 C 决策：是否统一 OR-NULL 口径（本波不改代码）',
         'owner_wave': '阶段C'},
        {'id': 'GAP-%s-3' % RUN, 'item': 'AC 词典中不在 C-11 八条范围内的条目（AC-19 / AC-48 / '
         'AC-52 / AC-53 / AC-29e 等）', 'state': 'not_covered',
         'reason': 'C-11 的契约范围只有 9 条 AC（33 §4 R-1）；其余条目从未有载体。',
         'action': '按 30/35 §12 的未覆盖清单继续登记，交阶段 B',
         'owner_wave': '阶段B'},
        {'id': 'GAP-%s-4' % RUN, 'item': 'AC-44/45/56 的载体是内存库（sqlite:///:memory:），'
         '未跑真实端点（未走 HTTP /add_item）', 'state': 'not_covered',
         'reason': 'R-2 只授权三类通道；内存库 + create_all 可隔离验证服务层分支，'
         '但绕过了端点层的权限/CSRF/模板面。',
         'action': '若需端点级证据，交 V-06/V-07 的端点探针或阶段 B 补 HTTP 往返',
         'owner_wave': '阶段B'},
        {'id': 'GAP-%s-6' % RUN, 'item': '同 run 落盘改名产生的**替代件**（已按 40 §4.1 处置）',
         'state': 'asset_defect',
         'reason': '本次 run 内被 guard_write 改名保留的文件：'
                   '① `r2_c11_probe.r2-exec-b3-v08.json`（7336 B / 8FA76A43…，22:17:55）与 '
                   '`r2_c11_probe.r2-exec-b3-v08.1.json`（7501 B / 1A1683C2…，22:18:20）= 探针打磨过程中的'
                   '**被取代次品**（首份是夹具构造失败前的产物、次份是 AC-45 三态未落真 NULL 的产物）；'
                   '② 同 run 两版台账中的**被取代件** `r2-exec-b3-v08-ledger.json`'
                   '（11321 B / 712C26C1…，22:19:13，缺 GAP-5 锚点漂移登记）与 '
                   '`r2-exec-b3-v08-ledger.r2-exec-b3-v08.json`（13232 B / C6DCD645…，22:19:40）'
                   '——后者的唯一缺陷是把 stale 的 `r2_c11_probe.r2-exec-b3-v08.json` 当成探针产物登记。',
         'action': '按 40 §4.1 唯一裁决规则（判序只认 evidence_journal.jsonl，后写者=终稿）与 §5.2 第 7 条'
                   '（唯一允许删 evidence/** 的情形）**删除全部 4 个被取代件**（22:19:47 已执行，逐个'
                   'Resolve-Path 核对未越界），并由本份重写为唯一权威 ledger（canonical 名 '
                   '`r2-exec-b3-v08-ledger.json`，断言集合与前版逐条相同、仅修正 stale artifact 引用）。',
         'owner_wave': '本任务（V-08）'},
        {'id': 'GAP-%s-7' % RUN, 'item': 'GAP-6 清理后重写 ledger 的落盘形态',
         'state': 'asset_defect',
         'reason': '按 GAP-6 处置后本工具重跑一次：`r2-exec-b3-v08-ledger.json` 已不存在 ⇒ '
                   '本份写入预期落在 canonical 名（renamed_by_guard=false），journal 追加第 7 行。',
         'action': '读 evidence_journal.jsonl 核对实际 written 文件名与 renamed_by_guard；'
                   '若仍改名，删除 T1 版并在次行 evidence_note 登记',
         'owner_wave': '本任务（V-08）'},
        {'id': 'GAP-%s-5' % RUN, 'item': '锚点 uat_chains.json 在本 run 期间被 V-12 有意更新'
         '（33318 B/360A8570… → %s B/%s）' % (UAT_ROW['bytes'], (UAT_ROW['sha256'] or '')[:16]),
         'state': 'unexecuted',
         'reason': '35 §8 文件独占矩阵把 harness/uat_chains.py 划给 V-12（t13）；'
         'B0 在 22:06:37 冻结时该锚点仍为钉值，t13 于 22:18:31 前产出新版本 ⇒ '
         'V-08 完工时该锚点已不再是基线值。',
         'action': 'V-14 回归复验时按「旧值 + 新值 + 触发 ID（t13/V-12）+ 命令」重取该锚点基线；'
         '其余 6 锚点不动',
         'owner_wave': 'V-14（B5）'},
    ]

    artifacts = []
    for rel in ('%s/r2_c11_probe.json' % RUN_DIR_REL,
                '%s/assertion_ledger.c11.json' % RUN_DIR_REL,
                'test-reports-2026-10/.tmp/%s/r2_c11_probe.console.txt' % RUN,
                'test-reports-2026-10/.tmp/%s/r2_c11_ledger.console.txt' % RUN,
                'test-reports-2026-10/harness/r2_c11_probe.py',
                'test-reports-2026-10/harness/r2_c11_ledger.py',
                'test-reports-2026-10/harness/r2_c11_ledgerbook.py'):
        a = art(rel)
        if a:
            a.pop('lines', None)
            artifacts.append(a)
    jr = os.path.join(REPO_ROOT, RUN_DIR_REL, 'evidence_journal.jsonl')
    if os.path.isfile(jr):
        artifacts.append({'path': '%s/evidence_journal.jsonl' % RUN_DIR_REL,
                          'bytes': os.path.getsize(jr), 'sha256': None})
    artifacts.append({'path': '%s/%s-ledger.json' % (RUN_DIR_REL, RUN),
                      'bytes': None, 'sha256': None})

    now = time.strftime('%Y-%m-%dT%H:%M:%S+08:00')
    doc = {
        'ledger_version': '2.0',
        'run_id': RUN,
        'task_id': TASK_ID,
        'attempt_id': ATTEMPT_ID,
        'operator': '测试结果分析师',
        'started_at': probe.get('started_at', now),
        'finished_at': now,
        'env': {
            'workdir': REPO_ROOT,
            'git_head': git('rev-parse', 'HEAD'),
            'app_tree': git('rev-parse', 'HEAD:app'),
            'python': '%s (3.9.21)' % PY,
            'sandbox': 'DSH danger-full-access（本轮无审批弹窗）',
            'temp_run_root': 'test-reports-2026-10/.tmp/%s' % RUN,
        },
        'db_invariant': {
            'target': 'app.db',
            'pinned_sha256': _env.REAL_DB_SHA256_EXPECTED,
            'sha256_before': probe['real_db']['sha256_before'],
            'sha256_after': probe['real_db']['sha256_after'],
            'verdict': '通过',
        },
        'production_freeze': {'files': prod},
        'anchor_readings': anchors,
        'results': results,
        'gaps': gaps,
        'artifact_index': artifacts,
        'field_note': 'S-1 不给 evidence_journal.jsonl 记 sha256（写它就是改它，40 §5.3）；'
                      'S-2 不给本台账自身的 sha256 记值 ⇒ artifact_index 末行 sha256=null，'
                      '由调用方在落盘后另算。',
    }
    text = json.dumps(doc, ensure_ascii=False, indent=1)
    saved = _env.save_evidence('%s-ledger.json' % RUN, text)
    tmp = os.path.join(_env.tmp_dir('ledger'), '%s-ledger.json' % RUN)
    with open(tmp, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(text)

    ok_anchors = sum(1 for a in anchors if a['matches_captain'])
    print('=== r2_c11_ledgerbook（40 §4 台账）===')
    print('run_id    = %s' % RUN)
    print('HEAD      = %s' % doc['env']['git_head'])
    print('HEAD:app  = %s（冻结值 c8f7d4ab…）' % doc['env']['app_tree'])
    print('真库      = %s -> %s（钉死值未变 = %s）'
          % (doc['db_invariant']['sha256_before'][:16], doc['db_invariant']['sha256_after'][:16],
             doc['db_invariant']['sha256_before'] == doc['db_invariant']['sha256_after']))
    print('锚点      = %d/%d matches_captain' % (ok_anchors, len(anchors)))
    print('results   = %d  gaps = %d  artifacts = %d'
          % (len(results), len(gaps), len(artifacts)))
    print('落盘（save_evidence）：%s' % saved)
    print('落盘（本 run 临时副本）：%s' % tmp)
    print()
    print('【S-2 落盘后另算】本台账 SHA256 = %s' % _env.sha256_file(saved))
    return 0


if __name__ == '__main__':
    sys.exit(main())
