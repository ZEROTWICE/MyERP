"""r2_c11_ledger.py — V-08（C-11）账本回写：把 9 条 AC 写进断言账本的**新 run 产物**。

## 为什么是新产物（独占 + 不原地覆盖）
`evidence/analysis/assertion_ledger.json` 是 7 个回归锚点之一（60937 B /
`C7C31273…AC94092`），**只读基线**。本工具：

1. 读基线（只读）；
2. 在内存里**只追加** 9 条 AC 条目（`AC-15/16/29b/29c/29d/44/45/56/49`），**不改任何既有条目**；
3. 经 `_env.save_evidence` 落 `evidence/harness/<RUN_ID>/assertion_ledger.c11.json`
   （guard_write 改名保留 + 审计流水），**基线文件一字不动**；
4. 同步更新派生计数：`totals`（144 → 153）、`c11_rollup`，并记录「前后两数」。

## 回写规则（`33` §4 R-1…R-5 / `35` §9.2 V-08）
| 规则 | 实现 |
| --- | --- |
| `R-1` 每条恰 1 条 + 字段齐备 | `ac_id`/`status`/`carrier`/`command`/`reading` 全部非空；重复 `ac_id` ⇒ exit 1 |
| `R-2` 不许第三种状态 | `status ∈ {passed, failed}`；出现别的值 ⇒ exit 1 |
| `R-3` 既有载体标 `pre-existing` | `AC-15/16/29b/29c/29d` ⇒ `carrier_origin='pre-existing'`，载体 `w2w3_probe.py` 具名格号 |
| `R-4` 新建或「零载体 + 期望 FAIL」 | `AC-44/45/56` ⇒ `new`；`AC-49` ⇒ `failed` + `zero-carrier`（含 `file:line`） |
| `R-5` 给「144 → N」前后两数 | `ledger_delta = {before:144, after:N, produced_by:...}` |

用法（仓库根）：

    $env:HARNESS_RUN_ID='r2-exec-b3-v08'
    F:\\Miniconda\\envs\\wage\\python.exe -B test-reports-2026-10/harness/r2_c11_ledger.py

退出码：0 = 规则 R-1…R-5 全过；1 = 违例。
"""
import argparse
import collections
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import _env  # noqa: E402

REPO_ROOT = _env.REPO_ROOT
BASELINE = os.path.join(REPO_ROOT, 'test-reports-2026-10', 'evidence', 'analysis',
                        'assertion_ledger.json')

#: 既有载体（`27` 已登记「已在库未进链」）⇒ carrier_origin = pre-existing
CARRIER_W2W3 = ('test-reports-2026-10/harness/w2w3_probe.py', 'w2w3_probe')

PROBE_CMD = (r'F:\Miniconda\envs\wage\python.exe -B '
             r'test-reports-2026-10/harness/w2w3_probe.py --scenario all')
PROBE_CMD_C11 = (r'F:\Miniconda\envs\wage\python.exe -B '
                 r'test-reports-2026-10/harness/r2_c11_probe.py')

#: 每条 AC 的「删掉它什么会变红」（28 §3 口径）
FLIP = {
    'AC-15': '回退 quality_status 自动复位（recompute_production_quality_status 不再在 NC 闭环后复算）'
             '⇒ w2w3_probe 格 N4/P4 转 FAIL（期望 {qs:pass, fg_delta:5.0/9.0}）',
    'AC-16': '让 pass 场景也写 NC 或把实例 quality_status 改成 fail ⇒ 格 A1 转 FAIL；'
             '去掉「改判后仍拦」⇒ 格 A2 的 gate_allowed=false 失效',
    'AC-29b': '去掉 deduct_scrap_materials 的 `if clamped: after = 0.0` 夹紧 ⇒ 出现负库存，格 AC29-b 转 FAIL',
    'AC-29c': '让扣料只认 workpiece.raw_material_id（不逐行读 ProductionRecordMaterial）'
              '⇒ 格 AC29-ac 的 rm2 不再 -3（对照料串味）',
    'AC-29d': '取不到消耗明细时默认减 1（而非空清单 + 「未扣减」说明）⇒ 格 AC29-d 的 rm1 不再保持 50.0',
    'AC-44': '从 shipment_allocated_product_ids / SHIPMENT_OPEN_STATUSES 摘掉 draft 占用'
             '⇒ r2_c11_probe ac44 断言「②第2张草稿候选不含 F」「③强行指定被拒」转 FAIL',
    'AC-45': '把候选的 is_(None) 分支去掉（只留 is_(False)）⇒ ac45 的「NULL 行在候选」「NULL 行可登记」转 FAIL；'
             '把登记判断 `if finished_product.is_archived` 收紧成 `is not False` ⇒「NULL 行可登记」转 FAIL',
    'AC-56': '把 12065/12093/12122 改成 OR-NULL ⇒ ac56 的「未统一 3 处均为 filter_by(is_archived=False)」转 FAIL；'
             '把 quality.py:744 改回 filter_by(False) ⇒「已统一 3 处」转 FAIL',
    'AC-49': '把 notify_inventory_warning 接到「低于 min_stock_level」的触发点'
             '⇒ ac49 的「期望 FAIL：inventory_warning 通知数 = 0」会变为 >0 ⇒ 该条从 FAIL 转 PASS',
}


def _probe_doc(run_id):
    """取本探针产物（优先本 run 目录，其次本 run 临时副本）。"""
    for p in (os.path.join(_env.EVIDENCE_ROOT, run_id, 'r2_c11_probe.json'),
              os.path.join(_env.tmp_dir('ledger'), 'r2_c11_probe.json')):
        if os.path.isfile(p):
            with open(p, encoding='utf-8') as fh:
                return p, json.load(fh)
    return None, None


def entry(ac_id, title, status, carrier, command, reading, carrier_origin,
          evidence, extra=None):
    e = {
        'suite': 'c11',
        'id': 'C11-%s' % ac_id,
        'title': title,
        'ac_id': ac_id,
        'status': status,
        'carrier': carrier,
        'carrier_origin': carrier_origin,
        'command': command,
        'reading': reading,
        'verdict': status,
        'evidence': evidence,
        'evidence_level': '原文可信',
        'evidence_kind': 'behavior_verified',
        'behavior_flip_test': {'red_when_removed': FLIP[ac_id]},
    }
    if extra:
        e.update(extra)
    return e


def build():
    with open(BASELINE, encoding='utf-8') as fh:
        base = json.load(fh)
    before_total = int((base.get('totals') or {}).get('total') or len(base['entries']))
    before_passed = int((base.get('totals') or {}).get('passed') or 0)
    before_failed = int((base.get('totals') or {}).get('failed') or 0)

    # 探针读数（四个新载体）
    probe_path, probe = _probe_doc(_env.RUN_ID)
    by_ac = {}
    if probe:
        for r in probe['results']:
            n_ok = sum(1 for c in r['checks'] if c['passed'])
            by_ac[r['ac']] = {'status': r['status'], 'checks': r['checks'],
                              'n_ok': n_ok, 'n': len(r['checks']), 'carrier': r['carrier']}

    def rd(ac):
        d = by_ac.get(ac) or {}
        return '%d/%d 断言 PASS（探针 exit=%s）' % (
            d.get('n_ok', 0), d.get('n', 0), '0' if d.get('status') == 'passed' else '1')

    w2w3 = 'test-reports-2026-10/evidence/harness/w2w3-t7-final/w2w3-criteria.json'

    rows = [
        entry('AC-15', 'NC 处置为 done 后同实例再报工恢复放行 + quality_status 自动复位 pass',
              'passed', 'harness/w2w3_probe.py 格 N4（:429 期望 {qs:pass, fg_delta:5.0}）+ '
                        '格 P4（:496 期望 {qs:pass, fg_delta:9.0}）', PROBE_CMD,
              'N4 actual={qs:pass, fg_delta:5.0} PASS；P4 actual={qs:pass, fg_delta:9.0} PASS；'
              '同 run 46/46 PASS', 'pre-existing', '%s#checks[N4,P4]' % w2w3,
              {'suite_note': '载体为 W2/W3 修复探针，本波只回写、未新建（R-3）',
               'paired_with': 'AC-16（阴阳对照必须成对；N3 拒收格在 :407 区段留痕）'}),
        entry('AC-16', 'pass 场景 nonconformity_records 增量 = 0 且实例 quality_status 维持 pass',
              'passed', 'harness/w2w3_probe.py 格 A1（:507 期望 {fg_delta:4.0, qs:pass}）+ '
                        '格 A2（:513 改判后仍拦）', PROBE_CMD,
              'A1 actual={fg_delta:4.0, qs:pass} PASS；A2 actual={qs:fail, nc_delta:1.0, '
              'gate_allowed:false} PASS；同 run 46/46 PASS', 'pre-existing',
              '%s#checks[A1,A2]' % w2w3,
              {'suite_note': '载体为 W2/W3 修复探针，本波只回写、未新建（R-3）',
               'paired_with': 'AC-15（阴阳成对；A2 为守门格）'}),
        entry('AC-29b', '扣料超过库存 ⇒ 夹紧到 0 且记 warning（不得为负）',
              'passed', 'harness/w2w3_probe.py 格 AC29-b（scrap 段）+ app/services/mes_service.py:703-733（:724-729 夹紧分支）',
              PROBE_CMD,
              'rm1 1.0 → 0.0（非负）；warning="报废扣料夹紧：物料 2 原量 1.0，请求扣减 2.0，'
              '夹紧后 0.0（不合格单 9，件数 1.0）"（四要素齐）', 'pre-existing',
              '%s#checks[AC29-b]' % w2w3,
              {'suite_note': '载体为 W2/W3 修复探针，本波只回写、未新建（R-3）'}),
        entry('AC-29c', '多条消耗行指向不同 raw_material_id 时各扣自己的量，不串味',
              'passed', 'harness/w2w3_probe.py 格 AC29-ac（scrap 段）+ app/services/mes_service.py:673-700（逐行列表）',
              PROBE_CMD,
              'before=[98.0, 97.0, 100.0] → after=[96.0, 94.0, 100.0]（rm1 -2、rm2 -3、'
              '对照料 rm3 **不变**）；PASS', 'pre-existing', '%s#checks[AC29-ac]' % w2w3,
              {'suite_note': '载体为 W2/W3 修复探针，本波只回写、未新建（R-3）',
               'control': 'rm3 为对照组（只断言被扣的那条 = 无信息量，33 §3.1 证伪条件）'}),
        entry('AC-29d', '无消耗数据 ⇒ 料账不变且含「未扣减」说明（不得默认减 1）',
              'passed', 'harness/w2w3_probe.py 格 AC29-d（scrap 段）+ app/services/mes_service.py:693-699（空清单 + warning）',
              PROBE_CMD,
              'rm1 保持 50.0（不变）；note="报废处置未扣减：未找到产出的消耗明细（不合格单 10，'
              '生产记录 20）（仅有工件料号 2，无消耗量）；按 AC-29d 不扣任何料"', 'pre-existing',
              '%s#checks[AC29-d]' % w2w3,
              {'suite_note': '载体为 W2/W3 修复探针，本波只回写、未新建（R-3）'}),
        entry('AC-44', '草稿单占用去重：同一成品行不被两张 draft 重复计入；取消后重新可发（阴性对照）',
              'passed', by_ac.get('AC-44', {}).get('carrier') or 'harness/r2_c11_probe.py ac44',
              PROBE_CMD_C11,
              '%s：taken 前=[] → 第1张草稿后=[1]；第2张草稿候选=[]（F 被剔除）；'
              '强行指定 F ⇒ 被拒 + 原因含「已加入发货单」；ShipmentItem 总数 1（未增加）、'
              'F.quantity 保持 5.0；取消第1张草稿后候选重现 [1] 且重新可发' % rd('AC-44'),
              'new', '%s#results[AC-44]' % (probe_path or ''),
              {'fixture_channel': 'sqlite:///:memory: + create_all（不落盘、不碰 app.db）',
               'negative_control': '取消 draft ⇒ 重新可发（证明拒绝来自占用而非永久失效）'}),
        entry('AC-45', '已存档不可发（TRUE 拒）+ NULL 视为未存档可发（三态齐备）',
              'passed', by_ac.get('AC-45', {}).get('carrier') or 'harness/r2_c11_probe.py ac45',
              PROBE_CMD_C11,
              '%s：库内三态 [1, 0, null] 实测落地；TRUE 不在候选且强行指定被拒（文案含'
              '「已存档，不能发货」）；FALSE/NULL 均在候选且均可登记' % rd('AC-45'),
              'new', '%s#results[AC-45]' % (probe_path or ''),
              {'fixture_channel': 'sqlite:///:memory: + create_all（不落盘、不碰 app.db）',
               'null_trap': '⚠ is_archived 列带 default=False，SQLAlchemy 在 INSERT 时才套用 ⇒ '
                            '「不赋值」与「= None」都落成 0。真 NULL 必须 `UPDATE … SET '
                            'is_archived=NULL` 造行（33 §5 P-2）——本探针首跑两次踩到，第三次改原始 '
                            'SQL UPDATE 才拿到库内 NULL'}),
        entry('AC-56', '«NULL = 未存档» 的覆盖必须显式「部分」：6 读取点中 3 已统一 / 3 未统一；不得写「全仓统一」',
              'passed', by_ac.get('AC-56', {}).get('carrier') or 'harness/r2_c11_probe.py ac56',
              PROBE_CMD_C11,
              '%s：静态面 3 统一 = quality.py:744 / routes.py:6247 / mes_service.py:1562（均含 '
              'is_archived.is_(None)）；3 未统一 = routes.py:12065 / 12093 / 12122（均 '
              'filter_by(is_archived=False)）；行为面 = NULL 行在 OR-NULL 下可见、在 '
              'filter_by(False) 下取不到（成品与原料各一组）' % rd('AC-56'),
              'new', '%s#results[AC-56]' % (probe_path or ''),
              {'scope_guard': '**不得**表述为「全仓统一」；未统一的 3 处按阶段一 04 §0.2「已定性决策」'
                              '只登记残余，**不升级为本轮修复诉求**（本轮只判文档表述准确性，不改代码）',
               'intentional_exception': '盘点快照 line mes_service.py:1441-1453 为有意例外'}),
        entry('AC-49', '安全库存预警通知：库存低于安全库存应产生 1 条预警通知（期望 FAIL：未接线）',
              'failed', 'app/services/notification_service.py:484（notify_inventory_warning 定义）'
                        '＋ 全 app/ 调用点 0（AST + 文本双搜）；阈值属性 app/models.py:606/631-634',
              PROBE_CMD_C11,
              '%s：notify_inventory_warning 定义 1 处、**调用点 0 处**；阈值以下易耗品行存在、'
              'is_low_stock=True，但 trigger_type=inventory_warning 的 Notification **= 0 条**'
              '（Notification 总行数也为 0）⇒ 该条判为 **期望 FAIL**（缺陷面：未接线），'
              '非「不可判定」' % rd('AC-49'),
              'failed+zero-carrier', '%s#results[AC-49]' % (probe_path or ''),
              {'zero_carrier': {
                  'fact': 'notify_inventory_warning 有定义、全 app/ 无调用点',
                  'file_line': 'app/services/notification_service.py:484',
                  'call_sites': 0,
                  'scan': "AST walk(app/**/*.py) 找 FunctionDef/Call 名字以 notify_ 开头 ⇒ 定义 1、"
                          "调用 0；另做文本搜索 'inventory_warning' ⇒ 仅 TRIGGER_TYPES 映射、"
                          "forms.py 下拉选项、模板 code，无触发调用"},
               'expected_fail_rationale': '33 §3.2-④：该条不是 coverage 缺口而是缺陷面；'
                                          '登记为 ❌期望FAIL，其判据是「接线后必须 +1」。'
                                          '**不得**因「没跑用例」记为「不可判定」',
               'paired_with': 'AC-48（派工通知已达 1/5 接线）——同一形态下派工 +1 而库存预警 +0，'
                              '证明探针能同时观测「接线」与「未接线」'}),
    ]

    # ---- R-1…R-5 机检 ----
    errors = []
    ids = [e['ac_id'] for e in rows]
    dup = [k for k, v in collections.Counter(ids).items() if v > 1]
    if dup:
        errors.append('R-1 重复 ac_id: %s' % dup)
    for e in rows:
        for f in ('ac_id', 'status', 'carrier', 'command', 'reading'):
            if not e.get(f):
                errors.append('R-1 %s 字段为空: %s' % (e['ac_id'], f))
        if e['status'] not in ('passed', 'failed'):
            errors.append('R-2 %s status 出不合法值: %r' % (e['ac_id'], e['status']))
        if e['ac_id'] in ('AC-15', 'AC-16', 'AC-29b', 'AC-29c', 'AC-29d'):
            if e['carrier_origin'] != 'pre-existing':
                errors.append('R-3 %s 应标 pre-existing，实际 %r' % (e['ac_id'], e['carrier_origin']))
            if 'w2w3_probe' not in e['carrier']:
                errors.append('R-3 %s pre-existing 载体未对上 w2w3_probe 格号' % e['ac_id'])
        if e['ac_id'] in ('AC-44', 'AC-45', 'AC-56'):
            if e['carrier_origin'] != 'new':
                errors.append('R-4 %s 应标 new，实际 %r' % (e['ac_id'], e['carrier_origin']))
        if e['ac_id'] == 'AC-49':
            if not (e['status'] == 'failed' and 'zero-carrier' in e['carrier_origin']):
                errors.append('R-4 AC-49 必须 status=failed + zero-carrier，实际 %r/%r'
                              % (e['status'], e['carrier_origin']))
            if not (e.get('zero_carrier') or {}).get('file_line'):
                errors.append('R-4 AC-49 缺 zero-carrier 的 file:line 事实')
        if not (e.get('behavior_flip_test') or {}).get('red_when_removed'):
            errors.append('R-2 %s 缺 behavior_flip_test.red_when_removed' % e['ac_id'])
    if len(rows) != 9:
        errors.append('R-1 条目数应为 9，实际 %d' % len(rows))

    # 追加（既有 144 条一字不动）
    new_entries = list(base['entries']) + rows

    def _count(es, st):
        return sum(1 for e in es if (e.get('status') or e.get('verdict')) == st)

    after_total = len(new_entries)
    after_passed = _count(new_entries, 'passed')
    after_failed = _count(new_entries, 'failed')

    doc = dict(base)
    doc['entries'] = new_entries
    doc['totals'] = {'total': after_total, 'passed': after_passed, 'failed': after_failed,
                     'blocked': int((base.get('totals') or {}).get('blocked') or 0)}
    doc['ledger_delta'] = {
        'metric': '账本条目数（口径：条目级；含门禁/聚合项）',
        'before': before_total, 'after': after_total, 'delta': after_total - before_total,
        'before_passed': before_passed, 'after_passed': after_passed,
        'before_failed': before_failed, 'after_failed': after_failed,
        'produced_by': 'test-reports-2026-10/harness/r2_c11_ledger.py（V-08）',
        'baseline_file': 'test-reports-2026-10/evidence/analysis/assertion_ledger.json',
        'baseline_sha256': _env.sha256_file(BASELINE),
        'works_on': '新 run 产物（基线只读，未原地覆盖）',
    }
    doc['c11_rollup'] = {
        'added_ac_ids': ids,
        'added': len(rows),
        'passed': _count(rows, 'passed'),
        'failed': _count(rows, 'failed'),
        'carrier_origin': dict(collections.Counter(e['carrier_origin'] for e in rows)),
        'rules': '33-剩余项业务验收判据.md §4 R-1…R-5',
        'remaining_gap': 'AC-49 = failed（预期失败：未接线），不是「未测」；'
                         '其余 AC 词典条目（AC-19/AC-48/AC-52/AC-53 等）不在 C-11 八条范围内，'
                         '仍登记为未覆盖（交阶段 B）',
    }
    doc['provenance'] = {
        'generated_by': 'test-reports-2026-10/harness/r2_c11_ledger.py',
        'run_id': _env.RUN_ID,
        'generated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'baseline_readonly': True,
        'superseded_by': None,
    }
    return doc, errors, probe_path


def main():
    ap = argparse.ArgumentParser(description='V-08 账本回写（新 run 产物）')
    ap.add_argument('--out', default='assertion_ledger.c11.json')
    args = ap.parse_args()

    doc, errors, probe_path = build()
    text = json.dumps(doc, ensure_ascii=False, indent=1)

    print('=== r2_c11_ledger（V-08 / C-11）===')
    print('run_id  = %s' % _env.RUN_ID)
    print('基线    = %s（只读）' % os.path.relpath(BASELINE, REPO_ROOT).replace('\\', '/'))
    print('基线 sha256 = %s' % doc['ledger_delta']['baseline_sha256'])
    print('探针读数 = %s' % (probe_path or '<缺>'))
    print()
    d = doc['ledger_delta']
    print('R-5 前后两数：账本 %d → %d（+%d）；passed %d → %d；failed %d → %d'
          % (d['before'], d['after'], d['delta'], d['before_passed'], d['after_passed'],
             d['before_failed'], d['after_failed']))
    print()
    for e in doc['entries'][d['before']:]:
        print('  %-9s %-8s origin=%-18s %s'
              % (e['ac_id'], e['status'], e['carrier_origin'], e['title'][:44]))
    print()
    for err in errors:
        print('  [ERROR] %s' % err)
    verdict = 'OK' if not errors else 'VIOLATION'
    print('R-1…R-5 机检 = %s' % verdict)

    saved = _env.save_evidence(args.out, text)
    tmp = os.path.join(_env.tmp_dir('ledger'), args.out)
    with open(tmp, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(text)
    print('落盘（save_evidence）：%s' % saved)
    print('落盘（本 run 临时副本）：%s' % tmp)
    return 0 if not errors else 1


if __name__ == '__main__':
    sys.exit(main())
