#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""B13-02 存量污染整治脚本 —— **默认只读；需显式授权方可执行（DEFAULT=READ-ONLY）**

整治对象（真实 `app.db`.`audit_log`）：
    count(target_id IS NULL AND can_rollback = 1) = 10
    id = [7, 8, 12, 15, 24, 29, 40, 44, 68, 73]   （全部 rollback_type='add'）
默认处置口径 = §7.2 拍板项 5 默认路径：置 `can_rollback=False`（诚实标记；不改历史数据语义、
只去掉「假按钮」）；**不回填 target_id**（需推断）。

写库的前置条件（缺一即拒绝执行，见 §5.3 例外条款四条前置）：
  1. `--apply` / `--revert` 显式动作（默认动作 = `--check`，只读）；
  2. 目标库必须是**真实库** `<repo>/app.db`（副本一律拒绝写 —— 副本只允许 `--check`）；
  3. `--i-have-authorization "<授权人>" "<时点>"`：授权必须在执行前取得并留档；
     §5.3 第 4 条：**未取得授权时，连默认路径也不得执行，只能登记**；
  4. B17-02 前置闸门处于**生效态**（`--gate-evidence <文件>` 或
     `scripts/check_db_url_guard.py --expect reject` 通过）；
  5. `--backup <备份文件>`：备份必须已存在且其 SHA256 == 当前库 SHA256（先备份、后整治）；
  6. 目标行 id 清单 + 前后计数断言全部成立（整治前 = 10，整治后 = 0）。

本脚本**不得**进入门禁链（§5.3 前置 ④：不写入任何 blocking 步骤、不由 `ci_gates.py`
编排、不进 CI）—— `--check` 会自查 `ci_gates.py` 对本脚本文件名的引用数并打印。

用法：
    python -B scripts/_remediate_b13_02_audit_log.py --check          # 只读复核（默认）
    python -B scripts/_remediate_b13_02_audit_log.py --apply ...      # 需全部前置
    python -B scripts/_remediate_b13_02_audit_log.py --revert ...     # 逆向还原
退出码：0=OK / 1=只读核对不一致 / 2=环境或文件错误 / 3=前置拒绝（授权·闸门·备份·目标库）
        / 4=目标行断言失败（id 清单或计数不符）
"""

import argparse
import hashlib
import os
import re
import sqlite3
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace')

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
REAL_DB = os.path.join(REPO_ROOT, 'app.db')

TARGET_IDS = [7, 8, 12, 15, 24, 29, 40, 44, 68, 73]
# 目标行的身份指纹（整治前实测）：id -> (rollback_type, target_model)
EXPECTED_ROWS = {
    7: ('add', 'CodeRule'),
    8: ('add', 'Product'),
    12: ('add', 'Product'),
    15: ('add', 'RawMaterial'),
    24: ('add', 'TaskAssignment'),
    29: ('add', 'TaskAssignment'),
    40: ('add', 'TaskAssignment'),
    44: ('add', 'CodeRule'),
    68: ('add', 'TaskAssignment'),
    73: ('add', 'InspectionTask'),
}
EXPECTED_TOTAL = 73
EXPECTED_NULL = 40
PRE_COUNT = 10
POST_COUNT = 0
# §5.3 前置 ③ 的「整治前」锚点（原值，append-only 留档，不得被覆盖）
PRE_ANCHOR = {
    'size': 2531328,
    'sha256': 'F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065',
    'mtime': '2026-09-18 12:50:55',
    'mtime_ns': 1789707055016880300,
}
COUNT_SQL = 'SELECT COUNT(*) FROM audit_log WHERE target_id IS NULL AND can_rollback = 1'
IDS_SQL = 'SELECT id FROM audit_log WHERE target_id IS NULL AND can_rollback = 1 ORDER BY id'
_EXEMPT_CLAUSE = 'target_id IS NULL AND can_rollback = 1'
REMEDIATION_SQL = ('UPDATE audit_log SET can_rollback = 0 WHERE id IN (%s) AND %s'
                   % (', '.join(str(i) for i in TARGET_IDS), _EXEMPT_CLAUSE))
REVERT_SQL = ('UPDATE audit_log SET can_rollback = 1 WHERE id IN (%s) AND target_id IS NULL AND can_rollback = 0'
              % ', '.join(str(i) for i in TARGET_IDS))


def out(msg):
    print('[b13-02] %s' % msg)


def fail(msg, code):
    out('REFUSED: %s' % msg)
    sys.exit(code)


def file_sig(path):
    st = os.stat(path)
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return {'size': st.st_size, 'sha256': h.hexdigest().upper(), 'mtime_ns': st.st_mtime_ns,
            'mtime': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(st.st_mtime))}


def fmt_sig(sig):
    return 'size=%d sha256=%s mtime=%s mtime_ns=%d' % (
        sig['size'], sig['sha256'], sig['mtime'], sig['mtime_ns'])


def connect_ro(path):
    """只读连接：URI mode=ro + PRAGMA query_only=1（双保险，写操作必失败）。"""
    con = sqlite3.connect('file:%s?mode=ro' % path.replace('\\', '/'), uri=True)
    con.execute('PRAGMA query_only = 1')
    return con


def read_state(con):
    cur = con.cursor()
    state = {}
    state['columns'] = [r[1] for r in cur.execute('PRAGMA table_info(audit_log)')]
    state['total'] = cur.execute('SELECT COUNT(*) FROM audit_log').fetchone()[0]
    state['nulls'] = cur.execute('SELECT COUNT(*) FROM audit_log WHERE target_id IS NULL').fetchone()[0]
    state['count'] = cur.execute(COUNT_SQL).fetchone()[0]
    state['ids'] = [r[0] for r in cur.execute(IDS_SQL)]
    state['rows'] = {r[0]: (r[1], r[2]) for r in cur.execute(
        'SELECT id, rollback_type, target_model FROM audit_log WHERE id IN (%s)'
        % ', '.join(str(i) for i in TARGET_IDS))}
    state['can'] = {r[0]: r[1] for r in cur.execute(
        'SELECT id, can_rollback FROM audit_log WHERE id IN (%s)'
        % ', '.join(str(i) for i in TARGET_IDS))}
    state['null_can0'] = cur.execute(
        'SELECT COUNT(*) FROM audit_log WHERE target_id IS NULL AND (can_rollback = 0 '
        'OR can_rollback IS NULL)').fetchone()[0]
    state['rollback_types'] = list(cur.execute(
        'SELECT rollback_type, COUNT(*) FROM audit_log GROUP BY rollback_type ORDER BY rollback_type'))
    return state


def assert_target_rows(state):
    """目标行断言：id 清单 + 计数 + 行身份指纹三者必须全部吻合。"""
    problems = []
    if state['count'] != PRE_COUNT:
        problems.append('pre count = %d, expected %d' % (state['count'], PRE_COUNT))
    if state['ids'] != TARGET_IDS:
        problems.append('target ids = %s, expected %s' % (state['ids'], TARGET_IDS))
    for tid in TARGET_IDS:
        got = state['rows'].get(tid)
        want = EXPECTED_ROWS[tid]
        if got != want:
            problems.append('row id=%d identity = %r, expected %r' % (tid, got, want))
    return problems


def gate_status(args):
    """B17-02 前置闸门是否生效（§5.3 前置 ④ 的执行前确认）。"""
    if args.gate_evidence:
        p = os.path.abspath(args.gate_evidence)
        if not os.path.exists(p) or os.path.getsize(p) == 0:
            return False, 'gate evidence file missing or empty: %s' % p
        return True, 'operator-recorded gate evidence: %s (%s)' % (p, fmt_sig(file_sig(p)))
    guard = os.path.join(HERE, 'check_db_url_guard.py')
    if os.path.exists(guard):
        try:
            proc = subprocess.run([sys.executable, '-B', guard, '--expect', 'reject'],
                                  cwd=REPO_ROOT, capture_output=True, timeout=600)
        except Exception as exc:  # noqa: BLE001
            return False, 'guard run failed: %r' % (exc,)
        if proc.returncode == 0:
            return True, 'scripts/check_db_url_guard.py --expect reject => exit 0'
        return False, 'scripts/check_db_url_guard.py --expect reject => exit %d' % proc.returncode
    return False, ('B17-02 guard absent (scripts/check_db_url_guard.py not found) '
                   '=> gate INACTIVE (B17-02 = blocked / production frozen)')


def ci_gates_refs():
    """自查：本脚本文件名是否被 ci_gates.py 引用（前置 ④ 的机械自证）。"""
    path = os.path.join(REPO_ROOT, 'test-reports-2026-10', 'harness', 'ci_gates.py')
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        text = f.read()
    return len(re.findall(r'_remediate_b13_02', text))


def want_real_db(args):
    """写库动作只允许真实库；副本只允许 --check。"""
    target = os.path.abspath(args.db)
    return os.path.exists(target) and os.path.realpath(target) == os.path.realpath(REAL_DB)


def write_guards(args, action):
    """写库前的全部前置检查；任何一项不满足即拒绝（exit 3）。"""
    out('action=%s DEFAULT=READ-ONLY is lifted only by the checks below' % action)
    if not os.path.exists(os.path.abspath(args.db)):
        fail('db not found: %s' % args.db, 2)
    if not want_real_db(args):
        fail('%s refused: target is not the real database (%s); copies are read-only'
             % (action, REAL_DB), 3)
    out('precondition 2 OK: target == real db (%s)' % REAL_DB)

    if not args.authorization:
        fail('%s refused: missing --i-have-authorization "<authorizer>" "<timestamp>" '
             '(section 5.3 rule 4: without authorization even the default path must not run)' % action, 3)
    authorizer, when = args.authorization
    if not authorizer.strip() or not when.strip():
        fail('%s refused: --i-have-authorization needs a non-empty authorizer AND timestamp' % action, 3)
    out('precondition 3 OK: authorization = %r @ %r' % (authorizer, when))

    ok, detail = gate_status(args)
    if not ok:
        fail('%s refused: B17-02 precondition gate is NOT active -- %s' % (action, detail), 3)
    out('precondition 4 OK: B17-02 gate active -- %s' % detail)

    if not args.backup:
        fail('%s refused: missing --backup <path> (section 5.3 rule 1: back up app.db first)' % action, 3)
    backup = os.path.abspath(args.backup)
    if not os.path.exists(backup):
        fail('%s refused: backup file not found: %s' % (action, backup), 3)
    b_sig = file_sig(backup)
    cur_sig = file_sig(os.path.abspath(args.db))
    if b_sig['sha256'] != cur_sig['sha256']:
        fail('%s refused: backup sha256 %s != current db sha256 %s (stale or partial backup)'
             % (action, b_sig['sha256'], cur_sig['sha256']), 3)
    out('precondition 1 OK: backup %s (%s)' % (backup, fmt_sig(b_sig)))
    return cur_sig


def check_mode(args):
    db = os.path.abspath(args.db)
    if not os.path.exists(db):
        fail('db not found: %s' % db, 2)
    before = file_sig(db)
    out('mode=check read_only=1 expect_state=%s db=%s' % (args.expect_state, db))
    out('pre_settlement_anchor %s' % fmt_sig(PRE_ANCHOR))
    out('current_sig %s' % fmt_sig(before))

    con = connect_ro(db)
    try:
        state = read_state(con)
    finally:
        con.close()

    out('audit_log columns=%d %s' % (len(state['columns']), ','.join(state['columns'])))
    out('audit_log total=%d target_id_null=%d null_and_can_rollback_1=%d null_and_can_rollback_0=%d'
        % (state['total'], state['nulls'], state['count'], state['null_can0']))
    out('expected_count=%d expected_ids=%s' % (PRE_COUNT, TARGET_IDS))
    out('actual_count=%d actual_ids=%s' % (state['count'], state['ids']))
    for tid in sorted(state['rows']):
        rt, tm = state['rows'][tid]
        out('target_row id=%d rollback_type=%s target_model=%s can_rollback=%s target_id=NULL'
            % (tid, rt, tm, state['can'].get(tid)))
    out('rollback_type_distribution=%s' % state['rollback_types'])
    out('remediation_sql=%s' % REMEDIATION_SQL)
    out('revert_sql=%s' % REVERT_SQL)

    if args.expect_state == 'pre':
        problems = assert_target_rows(state)
        out('expect_state=pre assertions: count==%d ids==%s row-identity all match' % (PRE_COUNT, TARGET_IDS))
    else:
        problems = []
        out('expect_state=post assertions: count==%d and all %d rows still present with can_rollback=0'
            % (POST_COUNT, len(TARGET_IDS)))
        if state['count'] != POST_COUNT:
            problems.append('post count = %d, expected %d' % (state['count'], POST_COUNT))
        for tid in TARGET_IDS:
            if state['rows'].get(tid) != EXPECTED_ROWS[tid]:
                problems.append('post row id=%d identity = %r, expected %r'
                                % (tid, state['rows'].get(tid), EXPECTED_ROWS[tid]))
            if state['can'].get(tid) != 0:
                problems.append('post row id=%d can_rollback = %r, expected 0'
                                % (tid, state['can'].get(tid)))
    if state['total'] != EXPECTED_TOTAL:
        problems.append('audit_log total = %d, expected %d' % (state['total'], EXPECTED_TOTAL))
    if state['nulls'] != EXPECTED_NULL:
        problems.append('target_id IS NULL = %d, expected %d' % (state['nulls'], EXPECTED_NULL))

    refs = ci_gates_refs()
    out('precondition 4 (not-in-ci-gates) self-check: ci_gates_refs=%s (must be 0)' % refs)
    if refs not in (0, None):
        problems.append('ci_gates.py references this script %d time(s): precondition 4 violated' % refs)

    out('preflight_status: authorization=NOT GIVEN backup=NOT GIVEN post_anchor=NOT REGISTERED '
        'gate=%s' % ('ACTIVE' if gate_status(args)[0] else 'INACTIVE'))
    out('executability=NOW-BLOCKED reason="no explicit authorization for B13-02 (section 5.3 rule 4)" '
        'AND "B17-02 gate inactive (blocked / production frozen)"')

    after = file_sig(db)
    unchanged = (before == after)
    out('zero_write_self_check before==after: %s (%s)' % (unchanged, fmt_sig(after)))
    if not unchanged:
        fail('read-only mode changed the database! before=%s after=%s'
             % (fmt_sig(before), fmt_sig(after)), 2)

    if problems:
        for p in problems:
            out('MISMATCH: %s' % p)
        out('RESULT: FAIL')
        return 1
    out('CHECK CONSISTENT expect_state=%s (total/null/count/ids/row-identity all match)'
        % args.expect_state)
    out('RESULT: OK')
    return 0


def apply_mode(args):
    cur_sig = write_guards(args, '--apply')
    db = os.path.abspath(args.db)
    con = connect_ro(db)
    try:
        state = read_state(con)
    finally:
        con.close()
    problems = assert_target_rows(state)
    if state['total'] != EXPECTED_TOTAL or state['nulls'] != EXPECTED_NULL:
        problems.append('audit_log total/null mismatch: %d / %d' % (state['total'], state['nulls']))
    if problems:
        for p in problems:
            out('MISMATCH: %s' % p)
        fail('--apply refused: target-row assertions failed (exit 4)', 4)
    out('precondition 6 OK: pre count=%d ids=%s row-identity all match' % (state['count'], state['ids']))
    out('planned_sql=%s' % REMEDIATION_SQL)

    con = sqlite3.connect(db)
    try:
        con.execute('PRAGMA foreign_keys = OFF')
        cur = con.cursor()
        cur.execute(REMEDIATION_SQL)
        changed = cur.rowcount  # 本语句命中行数（不可用 Connection.total_changes：它累计本连接全部 DML）
        con.commit()
        post = cur.execute(COUNT_SQL).fetchone()[0]
        post_rows = {r[0]: r[1] for r in cur.execute(
            'SELECT id, can_rollback FROM audit_log WHERE id IN (%s)'
            % ', '.join(str(i) for i in TARGET_IDS))}
        integrity = cur.execute('PRAGMA integrity_check').fetchone()[0]
    finally:
        con.close()

    out('rows_changed=%d expected=%d' % (changed, PRE_COUNT))
    out('post_count=%d expected=%d' % (post, POST_COUNT))
    out('post_can_rollback=%s' % post_rows)
    out('integrity_check=%s' % integrity)
    ok = (changed == PRE_COUNT and post == POST_COUNT and integrity == 'ok'
          and all(v == 0 for v in post_rows.values()))
    new_sig = file_sig(db)
    out('PRE_ANCHOR (append-only, must be preserved as 整治前) %s' % fmt_sig(PRE_ANCHOR))
    out('PREVIOUS_SIG %s' % fmt_sig(cur_sig))
    out('NEW_ANCHOR (register as 整治后, append-only) %s' % fmt_sig(new_sig))
    out('executed_sql=%s' % REMEDIATION_SQL)
    out('executor=%s authorized_by=%r at=%r' % (os.environ.get('USERNAME', '?'), args.authorization[0],
                                                args.authorization[1]))
    if not ok:
        out('RESULT: FAIL (post-conditions not satisfied; restore from backup)')
        return 1
    out('RESULT: OK (remediated %d rows)' % changed)
    return 0


def revert_mode(args):
    cur_sig = write_guards(args, '--revert')
    db = os.path.abspath(args.db)
    if not args.from_anchor:
        fail('--revert refused: missing --from-anchor <sha256 of the remediated db>', 3)
    if args.from_anchor.upper() != cur_sig['sha256']:
        fail('--revert refused: --from-anchor %s != current db sha256 %s'
             % (args.from_anchor.upper(), cur_sig['sha256']), 3)
    out('precondition 5 OK: from-anchor matches current db (%s)' % cur_sig['sha256'])

    con = connect_ro(db)
    try:
        state = read_state(con)
        cur = con.cursor()
        flags = {r[0]: r[1] for r in cur.execute(
            'SELECT id, can_rollback FROM audit_log WHERE id IN (%s)'
            % ', '.join(str(i) for i in TARGET_IDS))}
    finally:
        con.close()
    if state['count'] != POST_COUNT:
        fail('--revert refused: count(NULL AND can_rollback=1) = %d, expected %d (not remediated?)'
             % (state['count'], POST_COUNT), 4)
    if not all(flags.get(i) == 0 for i in TARGET_IDS):
        fail('--revert refused: target rows are not all can_rollback=0 (%s)' % flags, 4)
    for tid in TARGET_IDS:
        if tid not in state['rows']:
            fail('--revert refused: target row id=%d vanished' % tid, 4)
    out('revert preconditions OK: post count=0, all 10 rows still present with can_rollback=0')
    out('planned_sql=%s' % REVERT_SQL)

    con = sqlite3.connect(db)
    try:
        cur = con.cursor()
        cur.execute(REVERT_SQL)
        changed = cur.rowcount  # 同上：逐语句计数，避免累计值造成假比对
        con.commit()
        back = cur.execute(COUNT_SQL).fetchone()[0]
        integrity = cur.execute('PRAGMA integrity_check').fetchone()[0]
    finally:
        con.close()
    new_sig = file_sig(db)
    out('rows_changed=%d expected=%d' % (changed, PRE_COUNT))
    out('restored_count=%d expected=%d' % (back, PRE_COUNT))
    out('integrity_check=%s' % integrity)
    out('PREVIOUS_SIG (pre-revert) %s' % fmt_sig(cur_sig))
    out('NEW_ANCHOR (register as 还原后, append-only) %s' % fmt_sig(new_sig))
    out('executed_sql=%s' % REVERT_SQL)
    ok = (changed == PRE_COUNT and back == PRE_COUNT and integrity == 'ok')
    if not ok:
        out('RESULT: FAIL (revert post-conditions not satisfied)')
        return 1
    out('RESULT: OK (restored %d rows)' % changed)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description='B13-02 audit_log 存量污染整治（默认只读；写库需显式授权 + B17-02 闸门生效 + 先备份）')
    ap.add_argument('--db', default=REAL_DB, help='目标库（默认真实库 <repo>/app.db）')
    ap.add_argument('--check', action='store_true', help='只读复核（默认动作）')
    ap.add_argument('--expect-state', dest='expect_state', choices=('pre', 'post'), default='pre',
                    help='--check 的期望状态：pre=整治前（10 行待整治，默认）/ post=整治后（0 行待整治）')
    ap.add_argument('--apply', action='store_true', help='执行整治（置 can_rollback=0）')
    ap.add_argument('--revert', action='store_true', help='逆向还原（置 can_rollback=1）')
    ap.add_argument('--backup', help='整治前的 app.db 备份（SHA256 必须等于当前库）')
    ap.add_argument('--i-have-authorization', dest='authorization', nargs=2, metavar=('AUTHORIZER', 'WHEN'),
                    help='显式授权（授权人 + 时点）；未传则拒绝任何写库动作')
    ap.add_argument('--gate-evidence', help='记录 B17-02 闸门生效态的证据文件（替代 guard 脚本探测）')
    ap.add_argument('--from-anchor', help='--revert 用：整治后库的 SHA256（防还原错镜像）')
    args = ap.parse_args(argv)

    actions = [a for a in ('check', 'apply', 'revert') if getattr(args, a)]
    if len(actions) > 1:
        fail('choose exactly one of --check / --apply / --revert', 2)
    action = actions[0] if actions else 'check'

    if action == 'check':
        return check_mode(args)
    if action == 'apply':
        return apply_mode(args)
    return revert_mode(args)


if __name__ == '__main__':
    sys.exit(main())
