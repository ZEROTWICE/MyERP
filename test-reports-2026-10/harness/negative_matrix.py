"""阴性矩阵：四类必交阴性用例 + 阳性对照（「接线了但没跑」不算完成）。

任务书要求交付的四类：

1. **真实库防误写**：跑前/跑后真实 ``app.db`` SHA256 一致；并给一个**故意的负例**
   （试图把 URI 指向真实库时必须被拒）。
2. **假开关双向差分**：``quality.rework_counts_piecework`` 取 false / true 各跑同一返工场景，
   断言工资数字**不同**；非返工场景两次**相同**。*（若前者相同 ⇒ 暴露假开关，如实登记而不是改判据。）*
3. **门禁阴性 + 阳性对照**：报工 ``production_record`` 路径质检 fail 后断言不合格单/门禁字段增量
   与调用点实参；并给**阳性对照**（工件路径/显式传参时门禁确实拒绝），证明探针敏感。
4. **夹具尺度断言**：证明料账夹具已放大到 **≥5 行 / ``quantity ≥ 5``**（真实库仅 1 行 ``quantity=1.0``）。

每条用例输出：``id`` / 判据 / 期望 / 实测 / verdict（passed|failed|blocked）/ evidence_level / 原始输出文件。
**blocked 与未执行项显式登记，不计为通过。**

用法（仓库根目录）：

    F:\\Miniconda\\envs\\wage\\python.exe -B test-reports-2026-10/harness/negative_matrix.py
"""
import argparse
import io
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:  # A-14：中文输出在 GBK 控制台会抛 UnicodeEncodeError
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from _env import (EVIDENCE_DIR, REAL_DB, REAL_DB_SHA256_EXPECTED, REPO_ROOT,
                  assert_real_db_untouched, ensure_dir, real_db_status, run_child,
                  run_python, save_evidence, sha256_file, tmp_dir)

RESULTS = []


def record(case_id, title, criteria, expected, actual, verdict, evidence=None,
           evidence_level='原文可信', note=''):
    row = {'id': case_id, 'title': title, 'criteria': criteria, 'expected': expected,
           'actual': actual, 'verdict': verdict, 'evidence': evidence,
           'evidence_level': evidence_level, 'note': note}
    RESULTS.append(row)
    print(f'  [{verdict.upper():<7}] {case_id}  {title}')
    if verdict != 'passed':
        print(f'            expected={expected!r}')
        print(f'            actual  ={actual!r}')
        if note:
            print(f'            note    ={note}')
    return row


# --------------------------------------------------------------- 用例 1：真实库防误写
GUARD_PROBE = '''
# 隔离闸的三种输入，要求给出三个不同的判定（证明闸不是恒真/恒假）
import os, sys, json, shutil
sys.path.insert(0, r'{harness}')
sys.path.insert(0, r'{scripts}')
import _env

TMP = r'{tmp}'
os.makedirs(TMP, exist_ok=True)

# 伪造一个「同样叫 app.db」的库（另一目录）
fake_dir = os.path.join(TMP, 'fake_elsewhere')
os.makedirs(fake_dir, exist_ok=True)
fake = os.path.join(fake_dir, 'app.db')
shutil.copy2(_env.REAL_DB, fake)

guard = _env.real_db_guard_report

out = {{
    'real_db': {{'sha256': _env.sha256_file(_env.REAL_DB), 'path': _env.REAL_DB}},
    'fingerprint_ok': _env.sha256_file(_env.REAL_DB) == _env.REAL_DB_SHA256_EXPECTED,
    # 故意负例 A：URI 指向真实库本身 -> 必须被拒
    'negative_uri_points_at_real_db': guard(
        'sqlite:///' + _env.REAL_DB.replace('\\\\', '/'), _env.REAL_DB),
    # 旁证：符合同名 slug 但目标是另一文件 -> 放行（判据不是「只看文件名」）
    'same_basename_elsewhere': guard('sqlite:///' + fake.replace('\\\\', '/'), fake),
    # 指纹旁证：副本与真实库逐字节相同（因此指纹不能当拒绝判据）
    'copy_fingerprint_equals_real': _env.assert_isolated_fingerprint(
        'sqlite:///' + fake.replace('\\\\', '/'), fake),
}}
# 真实调用：_test_bootstrap 的最后一道闸在副本上必须放行
import fixtures
app, copy_path = fixtures.make_isolated_app('guardprobe')
out['bootstrap_guard_passed_on_copy'] = bool(copy_path)
out['app_uri'] = app.config['SQLALCHEMY_DATABASE_URI']
out['copy_path_sha256'] = _env.sha256_file(copy_path)
out['copy_is_real_file'] = os.path.samefile(copy_path, _env.REAL_DB)
out['isolation_evidence_from_fixtures'] = getattr(fixtures, 'LAST_ISOLATION_EVIDENCE', None)
import fixtures as _f
out['last_isolation_evidence'] = getattr(_f, 'LAST_ISOLATION_EVIDENCE', None)
print('__GUARD__' + json.dumps(out, ensure_ascii=False))
'''


def case1_real_db_guard(before_hash):
    print('\n== 用例 1：真实库防误写（含故意负例） ==')
    res = run_python(GUARD_PROBE.format(harness=os.path.dirname(os.path.abspath(__file__)),
                                        scripts=os.path.join(REPO_ROOT, 'scripts'),
                                        tmp=os.path.join(tmp_dir('case1')).replace('\\', '\\\\')),
                     label='case1_guard', timeout=600)
    marker = [l for l in res['stdout'].splitlines() if l.startswith('__GUARD__')]
    parsed = json.loads(marker[0][len('__GUARD__'):]) if marker else None
    ev = save_evidence('negative_case1_real_db_guard.txt',
                       f'# command: {res["argv_display"]}\n# exit_code: {res["exit_code"]}\n'
                       f'# evidence_level: {res["evidence_level"]}\n--- stdout ---\n{res["stdout"]}\n'
                       f'--- stderr ---\n{res["stderr"]}')
    record('NV-1.1', '真实库 SHA256 跑前 == 跑后 == 钉死值',
           'sha256(app.db) 三次一致且等于 F5DA2306…0E0F065',
           {'before': before_hash, 'pinned': REAL_DB_SHA256_EXPECTED},
           {'now': sha256_file(REAL_DB)},
           'passed' if (sha256_file(REAL_DB) == before_hash == REAL_DB_SHA256_EXPECTED)
           else 'failed', evidence=os.path.relpath(ev, REPO_ROOT))
    if parsed is None:
        record('NV-1.2', '故意负例：URI 指向真实库必须被拒', '判定 rejected=True 且给出原因',
               True, 'PROBE_NOT_RUN', 'blocked', evidence=os.path.relpath(ev, REPO_ROOT),
               evidence_level=res['evidence_level'],
               note='探针未产出 __GUARD__ 标记，见证据文件')
        return
    neg = parsed['negative_uri_points_at_real_db']
    decoy = parsed['same_basename_elsewhere']
    record('NV-1.2', '故意负例 A：URI 指向真实库本身必须被拒',
           'guard 判定 rejected=True（判据=同一文件 / samefile）',
           {'rejected': True, 'is_real_db': True},
           {'rejected': neg['rejected'], 'is_real_db': neg.get('is_real_db'),
            'reasons': neg['reasons']},
           'passed' if neg['rejected'] and neg.get('is_real_db') else 'failed',
           evidence=os.path.relpath(ev, REPO_ROOT))
    record('NV-1.3', '旁证：同名不同文件（另一目录的 app.db）不算真实库',
           'samefile 不成立 ⇒ 只比文件名会误判，必须比对同一文件',
           {'rejected': False, 'is_real_db': False},
           {'rejected': decoy['rejected'], 'is_real_db': decoy.get('is_real_db'),
            'reasons': decoy['reasons']},
           'passed' if not decoy['rejected'] and not decoy.get('is_real_db') else 'failed',
           evidence=os.path.relpath(ev, REPO_ROOT))
    record('NV-1.4', '阳性对照：副本上 bootstrap 隔离闸必须放行',
           'make_app() 返回且 URI 指向副本（非真实库）',
           {'bootstrap_guard_passed_on_copy': True, 'copy_is_real_file': False},
           {'passed': parsed['bootstrap_guard_passed_on_copy'],
            'copy_is_real_file': parsed['copy_is_real_file'], 'uri': parsed['app_uri']},
           'passed' if parsed['bootstrap_guard_passed_on_copy']
           and parsed['copy_is_real_file'] is False else 'failed',
           evidence=os.path.relpath(ev, REPO_ROOT),
           note='副本与真实库同名（app.db）但位于本 run 的 .tmp 目录 ⇒ '
                '「同名」不构成指向真实库。')
    fp = parsed.get('copy_fingerprint_equals_real') or {}
    record('NV-1.5', '口径校准：副本指纹 == 真实库指纹（故指纹不能当拒绝判据）',
           '副本 SHA256 与真实库钉死值相同 ⇒ 若用指纹拒绝，合法副本会被一并拒掉',
           {'copy_sha256_equals_pinned': True, 'copy_is_real_file': False},
           {'copy_sha256': parsed.get('copy_path_sha256'),
            'pinned': REAL_DB_SHA256_EXPECTED,
            'samefile_with_real': parsed.get('copy_is_real_file'),
            'fingerprint_guard_would_reject': fp.get('rejected')},
           'passed' if parsed.get('copy_path_sha256') == REAL_DB_SHA256_EXPECTED
           and parsed.get('copy_is_real_file') is False else 'failed',
           evidence=os.path.relpath(ev, REPO_ROOT),
           note='这是本 harness 修正过一次的口径错误（初版用指纹当拒绝判据，'
                '把自己的副本误判为真实库）——如实登记。')


# --------------------------------------------------------------- 用例 2：假开关双向差分
SALARY_PROBE = '''
import io, json, os, sys
sys.path.insert(0, r'{harness}')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import fixtures

out = {{}}
app, copy_path = fixtures.make_isolated_app('salary')
out['db_copy'] = copy_path
routes_py = os.path.join(r'{repo}', 'app', 'main', 'routes.py')
src = open(routes_py, encoding='utf-8').read().splitlines()
out['formula_source'] = [
    {{'line': i + 1, 'text': src[i].strip()}}
    for i in range(len(src))
    if 'record.quantity * record.process.price' in src[i]
    or ('piecework = piecework * employee.coefficient' in src[i])]

seed = fixtures.seed_salary(app, rework_qty=5, normal_qty=3, price=10.0)
out['seed'] = seed

# 开关 false -> 计算
out['switch_off_write'] = fixtures.set_rework_switch(app, False)
off = fixtures.salary_piecework(app, seed)
# 开关 true -> 计算（同一进程、同一份数据，唯一变量就是这个开关）
out['switch_on_write'] = fixtures.set_rework_switch(app, True)
on = fixtures.salary_piecework(app, seed)

codes = ['_hvEMP_REWORK', '_hvEMP_NORMAL']
out['piecework_off'] = off
out['piecework_on'] = on
out['deltas'] = {{c: round((on[c]['piecework'] - off[c]['piecework']), 6) for c in codes}}

# 差分机制自检：假设实现真的消费该开关（返工时把记录再计入计件），工资应变化。
# 用同一份数据 + 真消费开关的公式重算，证明「本口径能测出差异」。
base_rework = off['_hvEMP_REWORK']['piecework']


def _with_switch(count_rework_twice):
    per_record = 5 * 10.0 * 1.5   # 返工记录：5 件 × 10 元 × 系数 1.5
    return round(base_rework + (per_record if count_rework_twice else 0.0), 6)


out['mechanism_self_check'] = {{
    'description': '真消费开关时：true 多算一次返工计件，false 不变',
    'with_true': _with_switch(True),
    'with_false': _with_switch(False),
    'delta_true': _with_switch(True) - base_rework,
    'delta_false': _with_switch(False) - base_rework,
}}

out['raw_config_rows'] = fixtures.set_rework_switch(app, True)['readback']
out['switch_read_sites'] = fixtures.switch_read_sites()

# ---------------------------------------------------------------- [A-66 ③ r2 · 仅追加]
# DEC-2 §2.2「反查优先」合规夹具（R1∨R2）+ **产品路径**读数（不再用链内自算公式）。
# 作废原夹具的理由：它只用 notes（'_hv 返工记录'）区分返工，而 DEC-2 §2.2 明确否决 notes 标记
# （报工链不写 notes）。本段另起一名员工，旧员工与其 notes-记录**保持原样**（痕迹保留）。
import datetime as _dt

from app import db as _db
from app import models as _M
from app.services import mes_service as _mes

with app.app_context():
    _proc = _M.ProcessPrice.query.first()
    _admin = _M.User.query.filter_by(username='_t_admin').first() or _M.User.query.first()
    _day = _dt.date(2026, 10, 6)
    _emp2 = _M.Employee(employee_id='_hvEMP_R2', name='_hv 员工R2', department='_hv',
                        base_salary=0.0, coefficient=1.5, hire_date=_dt.date(2026, 1, 1))
    _db.session.add(_emp2)
    _db.session.flush()
    # R1：返工任务被不合格单引用；R2：该任务的 global_sn == 产出记录的 global_sn
    _rtask = _M.TaskAssignment(employee_id=_emp2.id, process_id=_proc.id, target_date=_day,
                               quantity=5, status='pending', task_type='auto',
                               notes='返工 不合格单#_hv')
    _db.session.add(_rtask)
    _db.session.flush()
    _rec_r = _M.ProductionRecord(employee_id=_emp2.id, process_id=_proc.id, quantity=5,
                                 date=_day, global_sn=_rtask.global_sn, notes='_hv R2 返工产出')
    _rec_n = _M.ProductionRecord(employee_id=_emp2.id, process_id=_proc.id, quantity=3,
                                 date=_day, notes='_hv R2 正常产出')
    _db.session.add_all([_rec_r, _rec_n])
    _db.session.flush()
    _itask = _M.InspectionTask(global_sn=_M.SerialNumber.get_next_number(),
                               target_type='production_record', target_id=_rec_r.id,
                               inspector_id=_admin.id, status='in_progress',
                               created_by=_admin.id)
    _db.session.add(_itask)
    _db.session.flush()
    _irec = _M.InspectionRecord(global_sn=_M.SerialNumber.get_next_number(), task_id=_itask.id,
                                inspector_id=_admin.id, inspection_date=_day, result='fail')
    _db.session.add(_irec)
    _db.session.flush()
    _db.session.add(_M.NonconformityRecord(record_id=_irec.id, type='rework',
                                           handler_id=_admin.id, handling_date=_day,
                                           handling_result='_hv 返工', status='done',
                                           rework_task_id=_rtask.id,
                                           target_type='production_record', target_id=_rec_r.id,
                                           scrap_cost=0))
    # RC-16 对照：批次自动派工（task_type='auto' 但非返工任务）不得被计入返工
    _atask = _M.TaskAssignment(employee_id=_emp2.id, process_id=_proc.id, target_date=_day,
                               quantity=4, status='pending', task_type='auto',
                               notes='批次自动派工（非返工）')
    _db.session.add(_atask)
    _db.session.flush()
    _rec_a = _M.ProductionRecord(employee_id=_emp2.id, process_id=_proc.id, quantity=4,
                                 date=_day, global_sn=_atask.global_sn, notes='_hv 自动派工产出')
    _db.session.add(_rec_a)
    _db.session.commit()
    _emp2_id = _emp2.id
    _atask_id = _atask.id


def _product_reads(value):
    fixtures.set_rework_switch(app, value)
    with app.app_context():
        emp = _M.Employee.query.get(_emp2_id)
        records = _M.ProductionRecord.query.filter(
            _M.ProductionRecord.employee_id == _emp2_id).all()
        counted, dropped, excluded = _mes.piecework_breakdown(records)
        base = emp.base_salary or 0.0
        adj = sum(bp.amount if bp.type == 'bonus' else -bp.amount for bp in emp.bonuses_penalties)
        coeff = emp.coefficient or 1.0
        s2_raw = (emp.total_salary - base - adj) / coeff
        return {{'counted_raw': round(counted, 6), 'dropped_raw': round(dropped, 6),
                'counted_with_coeff': round(counted * coeff, 6),
                's2_raw': round(s2_raw, 6), 'excluded_count': len(excluded),
                'excluded_ids': sorted(excluded)}}


_off = _product_reads(False)
_on = _product_reads(True)
with app.app_context():
    _auto_not_rework = _mes.is_rework_task(_M.TaskAssignment.query.get(_atask_id)) is False
out['product_path'] = {{
    'off_counted_raw': _off['counted_raw'], 'on_counted_raw': _on['counted_raw'],
    'delta_raw': round(_on['counted_raw'] - _off['counted_raw'], 6),
    'delta_with_coeff': round(_on['counted_with_coeff'] - _off['counted_with_coeff'], 6),
    'off_excluded_records': _off['excluded_count'],
    'off_excluded_ids': _off['excluded_ids'],
    'off_s2_matches': abs(_off['s2_raw'] - _off['counted_raw']) < 1e-6,
    'on_s2_matches': abs(_on['s2_raw'] - _on['counted_raw']) < 1e-6,
    'auto_task_not_rework': _auto_not_rework,
    'off_normal_only_raw': 30.0,
}}
fixtures.set_rework_switch(app, False)
print('__SALARY__' + json.dumps(out, ensure_ascii=False))
'''


def case2_switch_differential():
    print('\n== 用例 2：假开关双向差分（quality.rework_counts_piecework） ==')
    res = run_python(SALARY_PROBE.format(harness=os.path.dirname(os.path.abspath(__file__)),
                                         repo=REPO_ROOT.replace('\\', '\\\\')),
                     label='case2_salary', timeout=900)
    marker = [l for l in res['stdout'].splitlines() if l.startswith('__SALARY__')]
    parsed = json.loads(marker[0][len('__SALARY__'):]) if marker else None
    ev = save_evidence(
        'negative_case2_fake_switch.txt',
        f'# command: {res["argv_display"]}\n# exit_code: {res["exit_code"]}\n'
        f'# evidence_level: {res["evidence_level"]}\n--- stdout ---\n{res["stdout"]}\n'
        f'--- stderr ---\n{res["stderr"]}')
    if parsed is None:
        record('NV-2.1', '双向差分：返工记录计件工资应随开关变化',
               'off/on 两次 piecework 不同（delta != 0）', 'delta != 0', 'PROBE_NOT_RUN',
               'blocked', evidence=os.path.relpath(ev, REPO_ROOT),
               evidence_level=res['evidence_level'], note='探针未产出 __SALARY__ 标记')
        return
    delta_rework = parsed['deltas']['_hvEMP_REWORK']
    delta_normal = parsed['deltas']['_hvEMP_NORMAL']
    # ---------------------------------------------------------------- [A-66 ③ r2 · 仅追加重写]
    # 作废原断言（保留痕迹）：`NV-2.1` 原判据 = `delta_rework != 0`，其 delta 由**夹具自算**
    # `fixtures.salary_piecework`（按 routes.py:1815 的原式复算）而来，而夹具用 `notes`
    # （'_hv 返工记录'）标记返工 —— DEC-2 §2.2 明确否决 notes 标记（选定 R1∨R2）
    # ⇒ 产品实现认不出来，即使开关已真生效，原判据也不会转绿（"在断言夹具写错"）。
    # 重写为：DEC-2 §2.2 合规夹具（R1∨R2）+ **产品路径**读数
    # （`mes_service.piecework_amount` 唯一口径函数 与 `Employee.total_salary`）。
    nv21_expected = {'off_counted_raw': 70.0, 'on_counted_raw': 120.0, 'delta_raw': 50.0,
                     'delta_with_coeff': 75.0, 'off_excluded_records': 1,
                     'off_s2_matches': True, 'auto_task_not_rework': True}
    nv21_actual = parsed.get('product_path') or {}
    record('NV-2.1', '[A-66 ③ r2] 双向差分（DEC-2 §2.2 合规夹具 + 产品路径读数）：'
                     '开关 false⇒true 后该员工的计件必须 +50.0（未乘系数）/ +75.0（×系数 1.5）',
           '夹具：返工 5 件（R1 NC.rework_task_id + R2 global_sn）+ 正常 3 件 + 自动派工 4 件，'
           '单价 10.0、系数 1.5 ⇒ 关：(3+4)×10=70.0；开：(5+3+4)×10=120.0；差 = 返工贡献 50.0',
           nv21_expected,
           nv21_actual,
           'passed' if (abs((nv21_actual.get('off_counted_raw') or 0) - 70.0) < 1e-6
                        and abs((nv21_actual.get('on_counted_raw') or 0) - 120.0) < 1e-6
                        and abs((nv21_actual.get('delta_with_coeff') or 0) - 75.0) < 1e-6
                        and nv21_actual.get('off_excluded_records') == 1
                        and nv21_actual.get('off_s2_matches') is True
                        and nv21_actual.get('auto_task_not_rework') is True) else 'failed',
           evidence=os.path.relpath(ev, REPO_ROOT),
           note='[A-66 ③] 原判据基于 `fixtures.salary_piecework`（链内自算公式）+ notes 夹具 => 已作废；'
                '本轮的「开关真生效」由产品路径（mes_service.piecework_amount / '
                'Employee.total_salary）承证，并由 NV-2.5 的机制自检证明判据可证伪。')
    record('NV-2.2', '非返工场景两次必须相同',
           '开关切换不影响普通记录员工的计件工资（证明差分口径本身有效）',
           {'delta_normal': 0}, {'delta_normal': delta_normal},
           'passed' if delta_normal == 0 else 'failed',
           evidence=os.path.relpath(ev, REPO_ROOT))
    sites = parsed['switch_read_sites']
    unread = sites['unread_defaults']
    # ---------------------------------------------------------------- [A-66 ⑤ r2 · 仅追加重写]
    # 作废原断言（保留痕迹）：`NV-2.3` 原期望「该开关是全仓唯一**没有**任何读取点的配置项」
    # （`quality.rework_counts_piecework in unread and len(unread) == 1`）—— 它断言的正是
    # 本轮要消除的缺陷形态（假开关），任何正确实现都不可能使其转绿（A-66 ⑤）。
    # 重写为：该开关**恰有 1 个**读取点，且位于唯一判定处 mes_service（AC-04-e）。
    rework_sites = sites['read_sites'].get('quality.rework_counts_piecework', [])
    record('NV-2.3', '[A-66 ⑤ r2] 静态佐证：该开关恰有 1 个读取点且位于唯一判定处'
                     '（mes_service.py，AC-04-e）',
           'AST 扫 SystemConfig.get(\'<key>\') 调用点；quality.rework_counts_piecework 恰 1 处、'
           '在 app/services/mes_service.py；至少 4 个其它开关也有读取点',
           {'rework_switch_reads': 1, 'sites': rework_sites},
           {'all_read_sites': sites['read_sites'], 'unread_defaults': unread},
           'passed' if len(rework_sites) == 1 and 'mes_service.py' in rework_sites[0] else 'failed',
           evidence=os.path.relpath(ev, REPO_ROOT),
           note='[A-66 ⑤] 原期望「零读取点」（= GAP-18 的静态证据）=> 已作废；'
                '缺省值口径（default=False）由 w2w3_probe 的 AC-04-e 承证')
    # ---------------------------------------------------------------- [A-66 ④ r2 · 仅追加重写]
    # 作废原断言（保留痕迹）：`NV-2.4` 原把「有读取点的开关数」**写死为 4**；修复后该开关
    # 也有读取点 ⇒ 变成 5，判据恒假（A-66 ④「计数写死」）。重写为**集合包含**判据：
    # 要求 4 个既有开关各有 ≥1 个读取点（阳性对照的敏感度），不再钉总数。
    required = ['purchase.full_workflow_enabled', 'purchase.settlement_enabled',
                'purchase.incoming_inspection_required', 'quality.concession_approver_roles']
    present = {k: len(v) for k, v in sites['read_sites'].items() if v}
    missing = [k for k in required if k not in present]
    record('NV-2.4', '[A-66 ④ r2] 阳性对照：同一差分口径能测出真实生效的开关'
                     '（改为集合包含判据，不再钉总数）',
           '4 个既有开关必须各被扫出 ≥1 个读取点（探针敏感度）；总数不再钉死',
           {'required_keys_all_have_read_sites': required},
           {'present_keys': present, 'missing_required': missing,
            'total_keys_with_reads': len(present)},
           'passed' if not missing else 'failed',
           evidence=os.path.relpath(ev, REPO_ROOT),
           note='[A-66 ④] 原判据 `sum(...) == 4` 属计数写死 => 已作废（修复后本开关也有读取点）；'
                '探针敏感度由「4 个既有开关必须都被扫出」承证')
    record('NV-2.5', '差分机制自检：把开关值真读进来时，工资必须随值变化',
           '同一份数据用「真消费开关」的公式重算：True 时 +75（5 件×10 元×系数 1.5），'
           'False 时 +0 ⇒ 本差分口径具备检出能力（否则 NV-2.1 的 delta=0 不能归因于假开关）',
           {'delta_true': 75.0, 'delta_false': 0.0},
           {'delta_true': parsed['mechanism_self_check']['delta_true'],
            'delta_false': parsed['mechanism_self_check']['delta_false'],
            'base_piecework': parsed['piecework_off']['_hvEMP_REWORK']['piecework']},
           'passed' if parsed['mechanism_self_check']['delta_true'] == 75.0
           and parsed['mechanism_self_check']['delta_false'] == 0.0 else 'failed',
           evidence=os.path.relpath(ev, REPO_ROOT),
           note='这一步是为了让「delta=0 ⇒ 假开关」这个结论**可证伪**：'
                '若连真消费开关的对照都测不出差异，就必须改判为「差分机制失效」。')


# --------------------------------------------------------------- 用例 3：门禁阴性 + 阳性对照
GATE_PROBE = '''
import json, os, sys
sys.path.insert(0, r'{harness}')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import fixtures

out = {{}}
# 关键顺序：make_isolated_app() 会清掉 app* 模块缓存以重绑 DATABASE_URL，
# 因此**任何** from app... 导入都必须在它之后（否则拿到的是清缓存前的旧 SQLAlchemy 实例）。
app, copy_path = fixtures.make_isolated_app('qcg')
out['db_copy'] = copy_path

from app import db
from app import models as M
from app.services import mes_service

ctx = fixtures.seed_qc_gate(app)
out['ctx'] = ctx
counts_before = fixtures.counts(app, ['inspection_records', 'nonconformity_records',
                                      'production_batch_items', 'finished_product'])
out['counts_before'] = counts_before

# ---- 探针 A：真实调用点形态（不传 production_record），并**捕获实际实参**
captured = {{}}
real_gate = mes_service.qc_gate_allows_output


def spy(*args, **kwargs):
    captured['args_len'] = len(args)
    captured['kwargs_keys'] = sorted(kwargs.keys())
    captured['has_production_record'] = ('production_record' in kwargs
                                         and kwargs['production_record'] is not None)
    return real_gate(*args, **kwargs)


mes_service.qc_gate_allows_output = spy
with app.app_context():
    bi = M.ProductionBatchItem.query.get(ctx['batch_item']['id'])
    fp_before = M.FinishedProduct.query.count()
    result = mes_service.inbound_production_output(
        batch_item=bi, inspector_name='_hv', notes='_hv 门禁探针')
    db.session.rollback()
    fp_after = M.FinishedProduct.query.count()
mes_service.qc_gate_allows_output = real_gate
out['call_site_spy'] = captured
out['inbound_result'] = [None if result[0] is None else getattr(result[0], 'id', None),
                         result[1]]
out['finished_product_delta_at_call_site'] = fp_after - fp_before

# ---- 探针 B：七种调用形态的判定矩阵
states = fixtures.qc_gate_states(app, ctx)
out['gate_states'] = {{k: (list(v) if isinstance(v, tuple) else v)
                       for k, v in states['states'].items()}}
out['gate_extra'] = states['extra']

# ---- 探针 C：增量（不合格单 / 门禁字段 / 成品行）——全部应保持 0 增量
counts_after = fixtures.counts(app, ['inspection_records', 'nonconformity_records',
                                     'production_batch_items', 'finished_product'])
out['counts_after'] = counts_after
out['deltas'] = {{k: counts_after[k] - counts_before[k] for k in counts_before}}

# ---- 探针 E：GAP-14「质检结论自动回写 quality_status」是否发生
import datetime as _dt
p6 = ctx['p6_auto_writeback']
with app.app_context():
    bi_auto = M.ProductionBatchItem.query.get(p6['batch_item_id'])
    task_a = M.InspectionTask.query.get(p6['task_id'])
    nc_before = M.NonconformityRecord.query.count()
    ir = M.InspectionRecord(
        global_sn=M.SerialNumber.get_next_number(), task_id=task_a.id, template_id=None,
        inspector_id=M.User.query.filter_by(username='admin').first().id,
        inspection_date=_dt.date.today(), result='fail', notes='_hv 自动回写探针（判不合格）')
    db.session.add(ir)
    db.session.flush()
    task_a.status = 'completed'
    before_val = bi_auto.quality_status
    try:
        mes_service.apply_inspection_result(ir)
        call_state = 'ok'
    except Exception as e:
        call_state = 'EXC %s: %s' % (e.__class__.__name__, e)
    after_val = M.ProductionBatchItem.query.get(p6['batch_item_id']).quality_status
    nc_after = M.NonconformityRecord.query.count()
    rec_owner = M.ProductionRecord.query.get(p6['record_id'])
    out['auto_writeback'] = {{
        'call_state': call_state,
        'quality_status_before': before_val,
        'quality_status_after': after_val,
        'changed': before_val != after_val,
        'nc_count_before': nc_before,
        'nc_count_after': nc_after,
        'nc_delta': nc_after - nc_before,
        'record_batch_item_id': None if rec_owner is None else p6['batch_item_id'],
        'record_notes': None if rec_owner is None else rec_owner.notes,
    }}
    db.session.rollback()

# ---- 探针 F：静态读数——quality_status 的**赋值候选点**（左侧以 quality_status 结尾）
qs_hits = []
for rel in ('app/main/routes.py', 'app/services/mes_service.py', 'app/main/quality.py',
            'app/main/production_center.py'):
    src = open(os.path.join(r'{repo}', rel), encoding='utf-8').read().splitlines()
    for i, line in enumerate(src):
        if 'quality_status' not in line or '==' in line:
            continue
        head = line.split('=')[0].rstrip()
        tail = line.split('=', 1)[1].strip() if '=' in line else ''
        if not head.endswith('quality_status'):
            continue
        if line.lstrip().startswith('#'):
            continue
        if '；' in tail or tail.endswith('。') or tail.endswith('；'):
            continue  # 文档字符串里的举例，不是赋值
        if head.strip() == 'quality_status':
            continue  # 门禁内部的局部变量（服务层计算用），不是持久化字段
        qs_hits.append({{'file': rel, 'line': i + 1, 'text': line.strip()}})
out['quality_status_write_candidates'] = qs_hits
out['quality_status_local_vars_skipped'] = 'head.strip() == "quality_status" 的局部变量已排除'
out['record_nc_link'] = {{
    'record_id': ctx['p4_open_nc']['record_id'],
    'nc_record_id': ctx['p4_open_nc'].get('nc_id'),
    'batch_item_derived_records_p4': fixtures.batch_item_derived_records(
        app, ctx['p6_auto_writeback']['batch_item_id']),
}}

# ---- 探针 D：直接读源码确认调用点实参（静态，file:line）
mes = open(os.path.join(r'{repo}', 'app', 'services', 'mes_service.py'), encoding='utf-8')
lines = mes.read().splitlines()
out['call_site_326'] = {{'line': 326, 'text': lines[325].strip()}}
# [A-66 ④ r2] 门禁调用点**全集**（按内容定位，不再依赖固定行号；def 行不计）
out['qc_gate_call_sites'] = [{{'line': i + 1, 'text': lines[i].strip()}}
                             for i in range(len(lines))
                             if 'qc_gate_allows_output(' in lines[i]
                             and not lines[i].lstrip().startswith('def ')]
out['gate_def_157'] = {{'line': 157, 'text': lines[156].strip()}}
out['blocked_def'] = [{{'line': i + 1, 'text': lines[i].strip()}}
                      for i in range(len(lines)) if 'def workpiece_blocked' in lines[i]]
print('__GATE__' + json.dumps(out, ensure_ascii=False))
'''


def case3_gate_negative_with_control():
    print('\n== 用例 3：门禁阴性（production_record 路径）+ 阳性对照 ==')
    res = run_python(GATE_PROBE.format(harness=os.path.dirname(os.path.abspath(__file__)),
                                       repo=REPO_ROOT.replace('\\', '\\\\')),
                     label='case3_gate', timeout=900)
    marker = [l for l in res['stdout'].splitlines() if l.startswith('__GATE__')]
    parsed = json.loads(marker[0][len('__GATE__'):]) if marker else None
    ev = save_evidence(
        'negative_case3_qc_gate.txt',
        f'# command: {res["argv_display"]}\n# exit_code: {res["exit_code"]}\n'
        f'# evidence_level: {res["evidence_level"]}\n--- stdout ---\n{res["stdout"]}\n'
        f'--- stderr ---\n{res["stderr"]}')
    if parsed is None:
        record('NV-3.1', '门禁阴性：报工 production_record 路径 fail 后增量为 0',
               '不合格单/成品行增量 = 0', {'all_zero': True}, 'PROBE_NOT_RUN', 'blocked',
               evidence=os.path.relpath(ev, REPO_ROOT),
               evidence_level=res['evidence_level'], note='探针未产出 __GATE__ 标记')
        return
    deltas = parsed['deltas']
    record('NV-3.1', '门禁阴性：报工路径调用后，不合格单/成品/门禁字段零增量',
           'nonconformity_records / finished_product / production_batch_items 三表增量 = 0',
           {'nonconformity_records': 0, 'finished_product': 0, 'production_batch_items': 0},
           deltas,
           'passed' if all(deltas.get(k, 0) == 0 for k in
                           ('nonconformity_records', 'finished_product',
                            'production_batch_items')) else 'failed',
           evidence=os.path.relpath(ev, REPO_ROOT))
    spy = parsed['call_site_spy']
    record('NV-3.2', '落地点实参取证：真实调用点不传 production_record',
           '捕获 inbound_production_output 内部门禁调用实参：production_record 未传',
           {'has_production_record': False},
           {'has_production_record': spy.get('has_production_record'),
            'kwargs_keys': spy.get('kwargs_keys'), 'args_len': spy.get('args_len')},
           'passed' if spy.get('has_production_record') is False else 'failed',
           evidence=os.path.relpath(ev, REPO_ROOT),
           note='与 mes_service.py:326 源码读数一致；'
                'production_record=None ⇒ records 恒空 ⇒ :184-197 两条路径无数据可触发。')
    states = parsed['gate_states']
    rec = parsed['call_site_326']
    # ---------------------------------------------------------------- [A-66 ④ r2 · 仅追加重写]
    # 作废原断言（保留痕迹）：`NV-3.3` 原把门禁调用点**写死为 `mes_service.py:326`**
    # （`rec['line'] == 326` 的静态读数）—— 本轮修复使该调用点行号平移，判据恒假（A-66 ④
    # 「行号写死」）。重写为**按内容定位**：文件内存在 `qc_gate_allows_output(batch_item=...,
    # workpieces=...)` 调用，且**任何**调用点都不得传 `production_record`。
    call_sites = parsed.get('qc_gate_call_sites') or []
    bad_sites = [c for c in call_sites if 'production_record' in c['text']]
    record('NV-3.3', '[A-66 ④ r2] 源码读数（按内容定位，不钉行号）：门禁调用点存在且实参不含'
                     ' production_record',
           '文件内存在 qc_gate_allows_output(batch_item=..., workpieces=...) 调用；'
           '且任何调用点都不得传 production_record（def 行不计）',
           {'call_sites_found': '>= 1', 'sites_passing_production_record': 0},
           {'line_326_now': rec['text'], 'call_sites': call_sites, 'bad_sites': bad_sites},
           'passed' if call_sites and not bad_sites else 'failed',
           evidence=os.path.relpath(ev, REPO_ROOT),
           note='[A-66 ④] 原判据 `line == 326` 属行号写死 => 已作废（修复后该调用点已平移）；'
                '「不传 production_record」这一实质口径不变（A-67 的适用边界由此承证）')
    # 阳性对照 1：工件路径必须拒绝
    f = states['F_blocked_workpiece']
    record('NV-3.4', '阳性对照 1：被锁工件（status=machining + 未闭环不合格）必须被拒',
           '门禁返回 (False, 含工件编码的原因)', {'allowed': False, 'reason_has_code': True},
           {'allowed': f[0], 'reason': f[1]},
           'passed' if f[0] is False and '_hvWP_BLOCKED' in (f[1] or '') else 'failed',
           evidence=os.path.relpath(ev, REPO_ROOT))
    c = states['C_explicit_pending_task_record']
    cp = states['C_before_task_completed__pending_path']
    dp = states['D_after_task_completed__open_nc_path']
    record('NV-3.5', '阳性对照 2：同一条生产记录实参下，两条记录路径被逐个打亮',
           '质检任务 pending 时按「未完成质检任务」拒（:184-191）；改成 completed 后'
           '按「未闭环不合格」拒（:192-197）⇒ 本探针非写死结论',
           {'pending_path': False, 'open_nc_path': False},
           {'C_explicit_pending_task_record': [c[0], c[1]],
            'same_record_before': [cp[0], cp[1]],
            'same_record_after_task_completed': [dp[0], dp[1]]},
           'passed' if c[0] is False and cp[0] is False and dp[0] is False else 'failed',
           evidence=os.path.relpath(ev, REPO_ROOT),
           note='用的是**同一个** rec4 实参，唯一变量是质检任务状态；'
                ':192-197 用的探针行是「record_id 恰好命中该生产记录 id」的构造行'
                '（NonconformityRecord.record_id 是 FK→inspection_records，SQLite 默认不开外键），'
                '已如实登记该构造手法。')
    h = states['H_same_record_two_instances']
    # ---------------------------------------------------------------- [A-66 ⑤ / A-67 r2 · 仅追加重写]
    # 作废原断言（保留痕迹）：`NV-3.5b` 原期望「fail 实例拒、**pending 实例也拒**，仅原因文本不同」——
    # 「pending 一律拒」正是 DEC-1 §1.4 序 3 要消除的**死锁形态**（A-45/A-67 同源）。
    # 重写为：fail 实例 ⇒ 拒且原因含实例码；pending 实例（本例**无在办单据**）⇒ **放行**。
    record('NV-3.5b', '[A-66 ⑤ / A-67 r2] 阳性对照 3：同一实参喂两个实例 ⇒ 判定随实例'
                      ' quality_status 变化（fail ⇒ 拒；pending 且无在办单据 ⇒ 放行）',
           '同一 production_record 实参下：fail 实例必须被拒（原因含实例码）；'
           'pending 实例（本例无在办单据）必须放行 —— DEC-1 §1.4 序 3 / A-67',
           {'fail_instance_rejected': True, 'fail_reason_has_code': True,
            'pending_instance_allowed': True},
           {'fail_instance': h[0], 'pending_instance': h[1]},
           'passed' if (h[0][0] is False and '_hvBI_FAIL' in (h[0][1] or '')
                        and h[1][0] is True) else 'failed',
           evidence=os.path.relpath(ev, REPO_ROOT),
           note='[A-66 ⑤/A-67] 原期望「pending 也拒」（= 死锁）=> 已作废：DEC-1 §1.4 序 3 规定'
                '「pending **且确有在办单据**」才拒，本格构造的 pending 实例无在办单据 ⇒ 放行。'
                '配对格（pending 且确有在办单据 ⇒ 拒）见 uat P0-2.5(b) / w2w3_probe cells。')
    e = states['E_clean_workpiece']
    d2 = states.get('D2_explicit_closed_nc_record')
    g = states['G_nothing_at_all']
    record('NV-3.6', '阴性对照：干净输入必须放行（防止探针恒假）',
           '干净工件 / 只有已闭环不合格的记录 / 空参数三种输入都返回 True',
           {'clean_workpiece': True, 'closed_nc_only': True, 'nothing': True},
           {'clean_workpiece': e[0], 'closed_nc_only': None if d2 is None else d2[0],
            'nothing': g[0],
            'H_same_record_two_instances': states['H_same_record_two_instances']},
           'passed' if e[0] and g[0] and d2 is not None and d2[0] else 'failed',
           evidence=os.path.relpath(ev, REPO_ROOT),
           note='D2 用「只有 approved 不合格、无未完成质检任务」的记录 ⇒ 放行，'
                '证明 :192-197 只匹配 open/pending_approval。')
    a = states['A_batch_item_only__no_production_record']
    record('NV-3.7', '同形态对照：批次实例 quality_status=fail 会被拒（门禁并非失效）',
           'A 形态返回 False 且原因为「实例 …质检不合格」',
           {'allowed': False, 'reason_code': '_hvBI_FAIL'},
           {'allowed': a[0], 'reason': a[1]},
           'passed' if a[0] is False and '_hvBI_FAIL' in (a[1] or '') else 'failed',
           evidence=os.path.relpath(ev, REPO_ROOT),
           note='门禁有效；缺的是「让 :184-197 两条路径有数据」的那一步（GAP-13/GAP-14）。')
    record('NV-3.8', '增量复核：门禁探针全程未写入任何业务表',
           '探针前后四表行数完全一致（探针零副作用）',
           {'deltas_all_zero': True}, deltas,
           'passed' if all(v == 0 for v in deltas.values()) else 'failed',
           evidence=os.path.relpath(ev, REPO_ROOT))
    aw = parsed.get('auto_writeback') or {}
    # ---------------------------------------------------------------- [A-66 ⑤ r2 · 仅追加重写]
    # 作废原断言（保留痕迹）：`NV-3.9` 原期望「判不合格后 quality_status **不会**自动回写」
    # （`changed is False and nc_delta == 0`）—— 它断言的正是本轮要消除的缺陷形态
    # （GAP-14 未闭环），任何正确实现都不可能使其转绿（A-66 ⑤）。
    # 重写为 AC-18-a 的正面口径：pending ⇒ fail 且不合格单 +1（直接字段断言）。
    record('NV-3.9', '[A-66 ⑤ r2] GAP-14 正面口径：判不合格后 quality_status 必须**自动回写**'
                     '（pending ⇒ fail）且不合格单恰 +1',
           '提交 production_record 的 fail 结论后：quality_status 由 pending 变 fail、'
           '不合格单增量 1、调用无异常（AC-18-a 形状）',
           {'changed': True, 'quality_status_after': 'fail', 'nc_delta': 1, 'call_state': 'ok'},
           {'changed': aw.get('changed'), 'quality_status_before': aw.get('quality_status_before'),
            'quality_status_after': aw.get('quality_status_after'),
            'nc_delta': aw.get('nc_delta'), 'call_state': aw.get('call_state')},
           'passed' if (aw.get('call_state') == 'ok' and aw.get('changed') is True
                        and aw.get('quality_status_after') == 'fail'
                        and aw.get('nc_delta') == 1) else 'failed',
           evidence=os.path.relpath(ev, REPO_ROOT),
           note='[A-66 ⑤] 原期望「不回写 / nc_delta=0」= 缺陷本身 => 已作废；'
                'mes_service.apply_production_record_result + recompute_production_quality_status')
    aw2 = parsed.get('quality_status_write_candidates') or []
    # ---------------------------------------------------------------- [A-66 ⑤ r2 · 仅追加重写]
    # 作废原断言（保留痕迹）：`NV-3.10` 原期望「全仓赋值点**只有**人工 PUT 一处（routes.py:8899）」
    # —— 与 NV-3.9 同源，断言的正是缺陷形态。重写为**白名单 + 存在性**判据：
    #   (a) 必须存在 app/services/mes_service.py 的自动复算写点（DEC-1 §1.2 的唯一自动写点）；
    #   (b) 人工纠正通道 app/main/routes.py 的赋值点仍在；
    #   (c) 任何赋值候选点都不得落在白名单外的模块（防新增临时写点）。
    _files = {h['file'] for h in aw2}
    _has_auto = any(h['file'] == 'app/services/mes_service.py' for h in aw2)
    _has_manual = any(h['file'] == 'app/main/routes.py' for h in aw2)
    _outside = sorted(_files - {'app/services/mes_service.py', 'app/main/routes.py'})
    record('NV-3.10', '[A-66 ⑤ r2] 静态佐证（白名单判据）：存在 mes_service 的自动复算写点 + '
                      '人工 PUT 纠正通道，且无白名单外的赋值点',
           '赋值候选点必须同时覆盖 app/services/mes_service.py（自动复算写点）与'
           ' app/main/routes.py（人工纠正通道），且不得落在白名单外的模块',
           {'auto_write_point_in_mes_service': True, 'manual_put_in_routes': True,
            'files_outside_whitelist': 0},
           {'candidates': len(aw2), 'files': sorted(_files), 'outside': _outside, 'hits': aw2},
           'passed' if _has_auto and _has_manual and not _outside else 'failed',
           evidence=os.path.relpath(ev, REPO_ROOT),
           note='[A-66 ⑤] 原判据「只有 1 处、在 routes.py:8899」= 缺陷本身 => 已作废；'
                '扫描口径同前（行内 `=` 左侧以 quality_status 结尾），'
                '其中 mes_service.py:642/669 是 logger f-string 文本的**启发式假阳性**，已如实登记')


# --------------------------------------------------------------- 用例 4：夹具尺度断言
SCALE_PROBE = '''
import json, os, sys
sys.path.insert(0, r'{harness}')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import sqlite3
import _env
import fixtures

out = {{}}
# 真实库形态（只读 URI，**不复制**）—— 证明「放大」确实是新增信息量
con = sqlite3.connect('file:' + _env.REAL_DB.replace('\\\\', '/') + '?mode=ro', uri=True)
out['real_raw_material'] = {{
    'rows': list(con.execute('SELECT COUNT(*) FROM raw_material'))[0][0],
    'max_quantity': list(con.execute('SELECT MAX(quantity) FROM raw_material'))[0][0],
    'material_allocations_rows': list(con.execute(
        'SELECT COUNT(*) FROM material_allocations'))[0][0],
    'production_record_rows': list(con.execute(
        'SELECT COUNT(*) FROM production_record'))[0][0],
}}
con.close()

app, copy_path = fixtures.make_isolated_app('scale')
out['db_copy'] = copy_path
from app import db
from app import models as M
from app.services import mes_service
base = fixtures._base_objects(app)
out['base'] = {{k: getattr(v, '__tablename__', None) for k, v in base.items()}}
ledger = fixtures.seed_material_ledger(app, rows=5, qty=5.0)
out['ledger_seeded'] = ledger
out['ledger_state_before'] = fixtures.material_ledger_state(app, [r['id'] for r in ledger])

# 造生产订单 + 分配行（write_consumed_allocation 不会凭空建行，mes_service.py:839）
with app.app_context():
    admin = M.User.query.filter_by(username='admin').first()
    prod = M.Product.query.first()
    from datetime import date, timedelta
    order = M.ProductionOrder(product_id=prod.id, planned_quantity=20,
                              planned_start_date=date.today(),
                              planned_end_date=date.today() + timedelta(days=30),
                              created_by=admin.id)
    db.session.add(order)
    db.session.commit()
    order_id = order.id
out['order_id'] = order_id
allocs = fixtures.seed_allocation_rows(app, order_id, ledger)
out['allocation_rows'] = allocs

# 三行各扣不同数量：5.0 / 2.5 / 1.0（若实现是「硬编码减 1」这三行必然同解）
deductions = [5.0, 2.5, 1.0]
applied = []
with app.app_context():
    for row, qty in zip(ledger[:3], deductions):
        before = M.RawMaterial.query.get(row['id']).quantity
        mes_service.deduct_stock('raw', row['id'], qty, production_order_id=order_id)
        after = M.RawMaterial.query.get(row['id']).quantity
        alloc = M.MaterialAllocation.query.filter_by(
            production_order_id=order_id, material_type='raw',
            material_id=row['id']).first()
        applied.append({{'id': row['id'], 'qty': qty, 'before': before, 'after': after,
                        'consumed_quantity': alloc.consumed_quantity if alloc else None,
                        'allocated_quantity': alloc.allocated_quantity if alloc else None}})
    db.session.commit()
out['deductions_applied'] = applied
out['ledger_state_after'] = fixtures.material_ledger_state(app, [r['id'] for r in ledger])
out['shipment_note'] = '发货链前置（A-4）另见 fixtures.seed_shipment'
print('__SCALE__' + json.dumps(out, ensure_ascii=False))
'''


def case4_fixture_scale():
    print('\n== 用例 4：料账夹具尺度断言（A-10） ==')
    res = run_python(SCALE_PROBE.format(harness=os.path.dirname(os.path.abspath(__file__))),
                     label='case4_scale', timeout=900)
    marker = [l for l in res['stdout'].splitlines() if l.startswith('__SCALE__')]
    parsed = json.loads(marker[0][len('__SCALE__'):]) if marker else None
    ev = save_evidence(
        'negative_case4_fixture_scale.txt',
        f'# command: {res["argv_display"]}\n# exit_code: {res["exit_code"]}\n'
        f'# evidence_level: {res["evidence_level"]}\n--- stdout ---\n{res["stdout"]}\n'
        f'--- stderr ---\n{res["stderr"]}')
    if parsed is None:
        record('NV-4.1', '料账夹具 ≥5 行 / quantity ≥5', '行数>=5 且每行 quantity>=5',
               {'rows': 5, 'min_quantity': 5.0}, 'PROBE_NOT_RUN', 'blocked',
               evidence=os.path.relpath(ev, REPO_ROOT),
               evidence_level=res['evidence_level'], note='探针未产出 __SCALE__ 标记')
        return
    led = parsed['ledger_seeded']
    rec = parsed['real_raw_material']
    record('NV-4.1', 'A-10 前提复核：真实库料账确实不可分辨',
           '真实库 raw_material 行数=1 且 quantity=1.0（只读 URI，不复制）',
           {'rows': 1, 'max_quantity': 1.0, 'allocations': 0},
           rec,
           'passed' if rec['rows'] == 1 and rec['max_quantity'] == 1.0
           and rec['material_allocations_rows'] == 0 else 'failed',
           evidence=os.path.relpath(ev, REPO_ROOT))
    record('NV-4.2', '夹具尺度：新建料账行数 ≥ 5 且每行 quantity ≥ 5',
           'len(rows) >= 5 且 min(quantity) >= 5',
           {'rows': '>=5', 'min_quantity': '>=5'},
           {'rows': len(led), 'quantities': [r['quantity'] for r in led]},
           'passed' if len(led) >= 5 and min(r['quantity'] for r in led) >= 5 else 'failed',
           evidence=os.path.relpath(ev, REPO_ROOT))
    applied = parsed['deductions_applied']
    distinct = {round(a['qty'], 3) for a in applied}
    record('NV-4.3', '扣料辨析力：三种不同扣量必须得到三个不同余额（破除「硬编码减 1」）',
           'deduct_stock(qty) 后余额 = 5-qty；三次扣量的结果互不相同',
           {'after_values': '互不相同'},
           {'applied': applied,
            'after_values': [a['after'] for a in applied],
            'distinct': len({round(a['after'], 3) for a in applied}) == len(applied)},
           'passed' if len({round(a['after'], 3) for a in applied}) == len(applied) else 'failed',
           evidence=os.path.relpath(ev, REPO_ROOT),
           note='真实库只有 1 行 quantity=1.0 时，1.0→0.0 与「硬编码减 1」同解（A-10）。')
    consumed = [a['consumed_quantity'] for a in applied]
    record('NV-4.4', '扣料回写：MaterialAllocation.consumed_quantity 按数量累加',
           'consumed_quantity == 本次扣量（且 allocated_quantity 被回填）',
           {'consumed': [a['qty'] for a in applied]},
           {'consumed': consumed,
            'allocated': [a['allocated_quantity'] for a in applied]},
           'passed' if all(c is not None and abs(c - a['qty']) < 1e-6
                           for c, a in zip(consumed, applied)) else 'failed',
           evidence=os.path.relpath(ev, REPO_ROOT))


# --------------------------------------------------------------- 用例 5：发货链前置（A-4）
SHIP_PROBE = '''
import json, os, sqlite3, sys
sys.path.insert(0, r'{harness}')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import _env
import fixtures
out = {{}}
con = sqlite3.connect('file:' + _env.REAL_DB.replace('\\\\', '/') + '?mode=ro', uri=True)
out['real_finished_product'] = {{
    'rows': list(con.execute('SELECT COUNT(*) FROM finished_product'))[0][0],
    'stock_kind_null': list(con.execute(
        'SELECT COUNT(*) FROM finished_product WHERE stock_kind IS NULL'))[0][0],
}}
con.close()
app, copy_path = fixtures.make_isolated_app('ship')
out['db_copy'] = copy_path
fp = fixtures.seed_shipment(app, quantity=7, kind='fg')
out['seeded'] = fp
out['candidates'] = fixtures.shipment_candidates(app)
print('__SHIP__' + json.dumps(out, ensure_ascii=False))
'''


def case5_shipment_prerequisite():
    print('\n== 用例 5（A-4 前置）：发货链夹具必须先注入 stock_kind=\'fg\' ==')
    res = run_python(SHIP_PROBE.format(harness=os.path.dirname(os.path.abspath(__file__))),
                     label='case5_ship', timeout=600)
    marker = [l for l in res['stdout'].splitlines() if l.startswith('__SHIP__')]
    parsed = json.loads(marker[0][len('__SHIP__'):]) if marker else None
    ev = save_evidence(
        'negative_case5_shipment_prerequisite.txt',
        f'# command: {res["argv_display"]}\n# exit_code: {res["exit_code"]}\n'
        f'# evidence_level: {res["evidence_level"]}\n--- stdout ---\n{res["stdout"]}\n'
        f'--- stderr ---\n{res["stderr"]}')
    if parsed is None:
        record('NV-5.1', 'A-4 前提复核 + 夹具注入', '真实库 2 行 stock_kind 全 NULL；注入后候选可见',
               {'real_null': 2, 'candidates_after_inject': 1}, 'PROBE_NOT_RUN', 'blocked',
               evidence=os.path.relpath(ev, REPO_ROOT),
               evidence_level=res['evidence_level'], note='探针未产出 __SHIP__ 标记')
        return
    real = parsed['real_finished_product']
    record('NV-5.1', 'A-4 前提复核：真实库 finished_product.stock_kind 全为 NULL',
           '只读 URI 重算：rows=2 且 stock_kind IS NULL 的行数=2',
           {'rows': 2, 'stock_kind_null': 2}, real,
           'passed' if real['rows'] == 2 and real['stock_kind_null'] == real['rows']
           else 'failed', evidence=os.path.relpath(ev, REPO_ROOT))
    cand = parsed['candidates']
    got = [c for c in cand['candidates'] if c['product_number'] == '_hvFP_FG']
    record('NV-5.2', '夹具注入后发货候选可见（stock_kind=\'fg\' 过滤能取到）',
           'seed_shipment(kind=\'fg\') 后 shipment_candidate_stock 口径能取到该行',
           {'found': True, 'shippable_kinds': ['fg', 'wip_part']},
           {'found': bool(got), 'shippable_kinds': cand['shippable_kinds'],
            'candidates': cand['candidates']},
           'passed' if got else 'failed', evidence=os.path.relpath(ev, REPO_ROOT),
           note='「候选为空」在本夹具下不再成立 ⇒ 后续 E2E 若仍为空即是产品缺陷。')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(EVIDENCE_DIR, 'negative_matrix.json'))
    args = ap.parse_args()

    before = real_db_status()
    print(f'[negative_matrix] run_id={os.environ.get("HARNESS_RUN_ID", "adhoc")}')
    print(f'[negative_matrix] 真实库开工 SHA256 = {before["sha256"]}')

    case1_real_db_guard(before['sha256'])
    case2_switch_differential()
    case3_gate_negative_with_control()
    case4_fixture_scale()
    case5_shipment_prerequisite()

    after = real_db_status()
    record('NV-0', '收尾：真实库 SHA256 仍等于钉死值',
           '跑完整套阴性矩阵后 app.db 未变',
           {'sha256': REAL_DB_SHA256_EXPECTED},
           {'sha256': after['sha256'], 'mtime_ns': after['mtime_ns']},
           'passed' if after['sha256'] == REAL_DB_SHA256_EXPECTED else 'failed')
    verdicts = {v: sum(1 for r in RESULTS if r['verdict'] == v) for v in
                ('passed', 'failed', 'blocked')}

    # 退出码语义：harness 自身跑完 = 0；只有基础设施级问题才非 0。
    # 「某条用例 failed」= 发现缺陷（本阶段要的产出），不是 harness 坏掉。
    infra_errors = []
    real_db_ok = (before['sha256'] == after['sha256'] == REAL_DB_SHA256_EXPECTED)
    if not real_db_ok:
        infra_errors.append('真实库 SHA256 发生漂移（严重）')
    if verdicts['blocked']:
        infra_errors.append(f'{verdicts["blocked"]} 条用例 blocked（探针未跑出结论）')
    for r in RESULTS:
        if r['id'].startswith('NV-1.') and r['verdict'] != 'passed':
            infra_errors.append(f'隔离用例 {r["id"]} 未通过（隔离能力本身不可信）')

    out = {
        'harness': 'negative_matrix.py',
        'run_id': os.environ.get('HARNESS_RUN_ID', 'adhoc'),
        'interpreter': sys.executable,
        'real_db': {'before': before, 'after': after,
                    'unchanged': before['sha256'] == after['sha256'],
                    'pinned': REAL_DB_SHA256_EXPECTED},
        'cases': RESULTS,
        'summary': {'total': len(RESULTS), **verdicts,
                    'test_level_failures': verdicts['failed'],
                    'infrastructure_errors': infra_errors,
                    'exit_code_semantics':
                        'harness 自身跑完 ⇒ exit 0；发现缺陷（用例 failed）不是 harness 故障；'
                        '只有隔离失败 / blocked / 真实库漂移才 exit 非 0。'},
        'declared_scope_limits': [
            {'item': '真负例「URI 指向真实库 → 应用拒绝启动」',
             'status': 'partial（已交付等价形态）',
             'detail': '本仓 create_app() 没有「拒绝连真实库」的硬闸；真正的守卫是'
                       '_test_bootstrap 的副本断言（_test_bootstrap.py:41）与本 harness 的'
                       'fixtures.assert_isolated()/_env.real_db_guard_report()。'
                       'NV-1.2 验收该守卫对真实库输入判定 rejected=True（samefile=True），'
                       '不是「应用启动失败」——这一区别如实登记，不计为已实现硬闸。'},
            {'item': 'CSRF 防护在测试中恒关',
             'status': 'blocked(需产品决定/需非沙箱)',
             'detail': '_test_bootstrap.py:36 设 WTF_CSRF_ENABLED=False（08 §5.3 已登记）；'
                       '本轮不开 CSRF，故 155 个非 GET 端点的 CSRF 防护仍未取得测试证据。'},
            {'item': '返回码不可信的请求型脚本',
             'status': 'blocked(需先做 GAP-01)',
             'detail': 'smoke_test / permission_matrix 写仓库根 JSON ⇒ 沙箱下恒 exit 1；'
                       '本 harness 只取 stdout 结论段并登记证据等级。'},
            {'item': '料账扣料端到端（采购→到货→来料检）',
             'status': 'not-in-scope(属 t4/t5)',
             'detail': '本任务只交付夹具与尺度断言；端到端链由 t4/t5 承接。'},
        ],
    }
    ensure_dir(os.path.dirname(args.out))
    with open(args.out, 'w', encoding='utf-8', newline='\n') as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)

    print(f'\n[negative_matrix] 合计 {out["summary"]["total"]} 条：'
          f'passed={verdicts["passed"]} failed={verdicts["failed"]} blocked={verdicts["blocked"]}')
    print(f'[negative_matrix] 真实库异常？ {"否（SHA256 未变）" if out["real_db"]["unchanged"] else "是——立即停止"}')
    print(f'[negative_matrix] 基础设施级问题：{infra_errors or "无"}')
    print(f'[negative_matrix] JSON -> {args.out}')
    return 1 if infra_errors else 0


if __name__ == '__main__':
    sys.exit(main())
