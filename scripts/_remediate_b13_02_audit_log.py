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
    python -B scripts/_remediate_b13_02_audit_log.py --revert ...     # 逆向还原（锚点式）
    python -B scripts/_remediate_b13_02_audit_log.py --rollback <before.json> ...
                                       # 按 before 快照还原（B18-C 裁决：对称 b18 脚本形态）
B18-C（2026-10 批次18 队 t3）新增的 b18 对称形态三件：
    ① 写前落 before 快照（--out 可指定；默认落 test-reports-2026-10/evidence/b18c/）；
       快照只经 sqlite3 mode=ro 直连（绝不经 create_app——否则 _ensure_schema 补列 DDL 先跑，
       「只读」就变成写库，见 _remediate_b18_pg_weak_accounts.py docstring 的同坑订正）；
    ② --apply 在同一事务内 UPDATE + 插入一条 audit_log 审计留痕行（action='update'，
       details 以「B13-02 存量整治」开头；append-only：--revert/--rollback 只还原 10 行
       的 can_rollback，不删审计行）；
    ③ --rollback <before.json> 按 before 快照还原（只还原快照记录为 can_rollback=1
       且当前为 0 的行——「本来就被前人清过的行不误动」）。
退出码：0=OK / 1=只读核对不一致 / 2=环境或文件错误 / 3=前置拒绝（授权·闸门·备份·目标库）
        / 4=目标行断言失败（id 清单或计数不符）
"""

import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime

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
# B18-C（t3）新增：before 快照默认落点 + 审计留痕行识别
EVIDENCE_DIR = os.path.join(REPO_ROOT, 'test-reports-2026-10', 'evidence', 'b18c')
AUDIT_MARKER = 'B13-02 存量整治'
AUDIT_COUNT_SQL = ("SELECT COUNT(*) FROM audit_log WHERE action = 'update' AND details LIKE ?")
AUDIT_COUNT_ARG = (AUDIT_MARKER + '%',)
# --apply 审计留痕行落库后的全表期望（73+1 行 / 40+1 个 target_id NULL——留痕行自身 target_id IS NULL
# 且 can_rollback=0，不污染 count 口径）
POST_TOTAL = EXPECTED_TOTAL + 1
POST_NULLS = EXPECTED_NULL + 1
AUDIT_INSERT_SQL = ('INSERT INTO audit_log (user_id, action, timestamp, details, can_rollback, '
                    'rollback_type, target_model, target_id, old_data, new_data, rolled_back, '
                    'rolled_back_by, rolled_back_at) '
                    "VALUES (NULL, 'update', ?, ?, 0, NULL, NULL, NULL, NULL, ?, 0, NULL, NULL)")


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
    state['audit_rows'] = cur.execute(AUDIT_COUNT_SQL, AUDIT_COUNT_ARG).fetchone()[0]
    return state


def take_snapshot(db):
    """before 快照（只读）：全表指纹 + 10 个目标行的整行转储。

    只经 sqlite3 mode=ro 直连——**绝不经 create_app**（其 _ensure_schema 会先跑补列 DDL，
    「只读快照」就变成写库；同坑订正见 _remediate_b18_pg_weak_accounts.py docstring）。
    """
    con = connect_ro(db)
    try:
        cur = con.cursor()
        columns = [r[1] for r in cur.execute('PRAGMA table_info(audit_log)')]
        state = read_state(con)
        target_rows = {}
        for r in cur.execute('SELECT %s FROM audit_log WHERE id IN (%s) ORDER BY id'
                             % (', '.join(columns), ', '.join(str(i) for i in TARGET_IDS))):
            target_rows[r[0]] = dict(zip([c for c in columns if c != 'id'], r[1:]))
        fp = hashlib.sha256()
        for r in cur.execute('SELECT * FROM audit_log ORDER BY id'):
            fp.update(repr(r).encode('utf-8'))
        table_fingerprint = fp.hexdigest().upper()
    finally:
        con.close()
    return {
        'script': 'scripts/_remediate_b13_02_audit_log.py',
        'taken_at_utc': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S.%f'),
        'db': os.path.realpath(db),
        'db_sig': file_sig(db),
        'snapshot_mode': 'sqlite3 mode=ro + PRAGMA query_only（不经 create_app，不触发 _ensure_schema）',
        'columns': columns,
        'total': state['total'],
        'target_id_null': state['nulls'],
        'null_and_can_rollback_1': state['count'],
        'ids': state['ids'],
        'audit_marker_rows': state['audit_rows'],
        'target_rows': target_rows,
        'table_fingerprint': table_fingerprint,
    }


def persist_snapshot(path, snap):
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(snap, f, ensure_ascii=False, indent=2)
    out('snapshot_written=%s' % os.path.abspath(path))


def default_snapshot_path():
    return os.path.join(EVIDENCE_DIR, 't3-b13-02-before-%s.json'
                        % datetime.utcnow().strftime('%Y%m%d-%H%M%S'))


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

    if args.out:
        persist_snapshot(args.out, take_snapshot(db))

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
    # 全表口径（B18-C t3 起 --apply 会插入一条 append-only 审计留痕行，须按状态分别断言）：
    #   pre  允许两种：从未整治（73/40/无留痕行）或 整治后已还原（74/41/恰好 1 条留痕行
    #   且 10 行 can_rollback 全部回到 1）；
    #   post 必须：74/41/恰好 1 条留痕行（B18-C 裁决形态）。
    if args.expect_state == 'pre':
        pristine = (state['total'] == EXPECTED_TOTAL and state['nulls'] == EXPECTED_NULL
                    and state['audit_rows'] == 0)
        restored = (state['total'] == POST_TOTAL and state['nulls'] == POST_NULLS
                    and state['audit_rows'] == 1
                    and all(state['can'].get(i) == 1 for i in TARGET_IDS))
        if not (pristine or restored):
            problems.append('pre table state = total %d / null %d / audit-marker %d / flags %s '
                            '(expected pristine 73/40/0 or restored %d/%d/1 with flags=1)'
                            % (state['total'], state['nulls'], state['audit_rows'],
                               [state['can'].get(i) for i in TARGET_IDS],
                               POST_TOTAL, POST_NULLS))
        out('pre table state: total=%d nulls=%d audit_marker_rows=%d (pristine=%s restored=%s)'
            % (state['total'], state['nulls'], state['audit_rows'], pristine, restored))
    else:
        if state['total'] != POST_TOTAL:
            problems.append('audit_log total = %d, expected %d (+1 audit trail row)' % (state['total'], POST_TOTAL))
        if state['nulls'] != POST_NULLS:
            problems.append('target_id IS NULL = %d, expected %d (+1 audit trail row)' % (state['nulls'], POST_NULLS))
        if state['audit_rows'] != 1:
            problems.append('audit marker rows = %d, expected exactly 1' % state['audit_rows'])
        out('post table state: total=%d nulls=%d audit_marker_rows=%d' % (state['total'], state['nulls'], state['audit_rows']))

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
    if state['audit_rows'] != 0:
        problems.append('audit marker rows = %d, expected 0 (already remediated before? '
                        'restore from backup instead of re-applying)' % state['audit_rows'])
    if problems:
        for p in problems:
            out('MISMATCH: %s' % p)
        fail('--apply refused: target-row assertions failed (exit 4)', 4)
    out('precondition 6 OK: pre count=%d ids=%s row-identity all match' % (state['count'], state['ids']))
    out('planned_sql=%s' % REMEDIATION_SQL)

    # B18-C t3（b18 对称形态①）：写库前先落 before 快照（只读直连，不经 create_app）
    snap_path = args.out or default_snapshot_path()
    snap = take_snapshot(db)
    persist_snapshot(snap_path, snap)
    snap_sha = file_sig(snap_path)['sha256']

    authorizer, when = args.authorization
    audit_details = ('%s：置 can_rollback=0（诚实标记，不回填 target_id），%d 行 id=%s；授权=%r @ %r'
                     % (AUDIT_MARKER, len(TARGET_IDS), TARGET_IDS, authorizer, when))
    audit_new_data = json.dumps({'ids': TARGET_IDS, 'change': 'can_rollback: 1 -> 0',
                                 'target_id': '保持 NULL（不回填，B18-C 裁决）',
                                 'authorization': [authorizer, when]}, ensure_ascii=False)

    con = sqlite3.connect(db)
    try:
        con.execute('PRAGMA foreign_keys = OFF')
        cur = con.cursor()
        cur.execute(REMEDIATION_SQL)
        changed = cur.rowcount  # 本语句命中行数（不可用 Connection.total_changes：它累计本连接全部 DML）
        # B18-C t3（b18 对称形态②）：同一事务内追加审计留痕行（append-only，还原动作不删它）
        cur.execute(AUDIT_INSERT_SQL, (datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S.%f'),
                                       audit_details, audit_new_data))
        con.commit()
        post = cur.execute(COUNT_SQL).fetchone()[0]
        post_rows = {r[0]: r[1] for r in cur.execute(
            'SELECT id, can_rollback FROM audit_log WHERE id IN (%s)'
            % ', '.join(str(i) for i in TARGET_IDS))}
        post_audit = cur.execute(AUDIT_COUNT_SQL, AUDIT_COUNT_ARG).fetchone()[0]
        post_total = cur.execute('SELECT COUNT(*) FROM audit_log').fetchone()[0]
        integrity = cur.execute('PRAGMA integrity_check').fetchone()[0]
    finally:
        con.close()

    out('rows_changed=%d expected=%d' % (changed, PRE_COUNT))
    out('post_count=%d expected=%d' % (post, POST_COUNT))
    out('post_can_rollback=%s' % post_rows)
    out('post_audit_marker_rows=%d expected=1' % post_audit)
    out('post_total=%d expected=%d' % (post_total, POST_TOTAL))
    out('integrity_check=%s' % integrity)
    ok = (changed == PRE_COUNT and post == POST_COUNT and integrity == 'ok'
          and all(v == 0 for v in post_rows.values())
          and post_audit == 1 and post_total == POST_TOTAL)
    new_sig = file_sig(db)
    out('PRE_ANCHOR (append-only, must be preserved as 整治前) %s' % fmt_sig(PRE_ANCHOR))
    out('PREVIOUS_SIG %s' % fmt_sig(cur_sig))
    out('before_snapshot=%s sha256=%s' % (os.path.abspath(snap_path), snap_sha))
    out('NEW_ANCHOR (register as 整治后, append-only) %s' % fmt_sig(new_sig))
    out('executed_sql=%s' % REMEDIATION_SQL)
    out('audit_trail_row: action=update details=%r' % audit_details)
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


def rollback_mode(args):
    """B18-C t3（b18 对称形态③）：按 before 快照还原。

    只还原「快照记录为 can_rollback=1 且当前为 0」的目标行——若某行在本脚本整治之前
    就已被前人置 0（快照里本来就是 0），不误动（b18 --rollback 同款防误清逻辑）。
    审计留痕行是 append-only 历史，不删除。
    """
    write_guards(args, '--rollback')
    db = os.path.abspath(args.db)
    snap_path = os.path.abspath(args.rollback)
    if not os.path.exists(snap_path):
        fail('--rollback refused: before snapshot not found: %s' % snap_path, 2)
    try:
        with open(snap_path, 'r', encoding='utf-8') as f:
            snap = json.load(f)
    except (OSError, ValueError) as exc:
        fail('--rollback refused: cannot read snapshot %s: %r' % (snap_path, exc), 2)
    for key in ('script', 'ids', 'target_rows', 'table_fingerprint'):
        if key not in snap:
            fail('--rollback refused: snapshot missing key %r (not a before-snapshot?)' % key, 2)
    snap_ids = sorted(int(i) for i in snap['ids'])
    if snap_ids != sorted(TARGET_IDS):
        fail('--rollback refused: snapshot ids %s != expected target ids %s'
             % (snap_ids, sorted(TARGET_IDS)), 4)
    # 防误清：只还原快照中 can_rollback=1（= 本脚本整治动作真实翻过的行）的目标
    to_restore = [i for i in TARGET_IDS
                  if snap['target_rows'].get(str(i), {}).get('can_rollback') == 1]
    out('before_snapshot=%s (ids=%s, restore=%s)' % (snap_path, snap_ids, to_restore))
    if not to_restore:
        out('nothing to restore (snapshot shows no can_rollback=1 targets) — no write performed')
        out('RESULT: OK (0 rows)')
        return 0

    con = connect_ro(db)
    try:
        state = read_state(con)
    finally:
        con.close()
    for i in to_restore:
        if state['can'].get(i) != 0:
            fail('--rollback refused: row id=%d currently can_rollback=%r, expected 0 '
                 '(not in remediated state?)' % (i, state['can'].get(i)), 4)
    if state['audit_rows'] != 1:
        fail('--rollback refused: audit marker rows = %d, expected 1 (was --apply really run?)'
             % state['audit_rows'], 4)

    restore_sql = ('UPDATE audit_log SET can_rollback = 1 WHERE id IN (%s) '
                   'AND target_id IS NULL AND can_rollback = 0'
                   % ', '.join(str(i) for i in to_restore))
    out('planned_sql=%s' % restore_sql)
    con = sqlite3.connect(db)
    try:
        cur = con.cursor()
        cur.execute(restore_sql)
        changed = cur.rowcount
        con.commit()
        back = cur.execute(COUNT_SQL).fetchone()[0]
        integrity = cur.execute('PRAGMA integrity_check').fetchone()[0]
    finally:
        con.close()
    new_sig = file_sig(db)
    out('rows_changed=%d expected=%d' % (changed, len(to_restore)))
    out('restored_count=%d expected=%d' % (back, len(to_restore)))
    out('integrity_check=%s' % integrity)
    out('audit_marker_rows=1 (append-only: the --apply audit trail row is preserved, not deleted)')
    out('NEW_ANCHOR (register as 还原后, append-only) %s' % fmt_sig(new_sig))
    ok = (changed == len(to_restore) and back == len(to_restore) and integrity == 'ok')
    if not ok:
        out('RESULT: FAIL (rollback post-conditions not satisfied)')
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
    ap.add_argument('--apply', action='store_true', help='执行整治（置 can_rollback=0；同一事务追加审计留痕行）')
    ap.add_argument('--revert', action='store_true', help='逆向还原（锚点式，见 --from-anchor）')
    ap.add_argument('--rollback', metavar='BEFORE_JSON',
                    help='按 before 快照还原（B18-C b18 对称形态；只还原快照记录为 1 的行，不删审计留痕行）')
    ap.add_argument('--out', metavar='PATH',
                    help='before 快照落盘路径（--apply 必落，默认 test-reports-2026-10/evidence/b18c/；'
                         '--check 可选加 --out 落只读快照）')
    ap.add_argument('--backup', help='整治前的 app.db 备份（SHA256 必须等于当前库）')
    ap.add_argument('--i-have-authorization', dest='authorization', nargs=2, metavar=('AUTHORIZER', 'WHEN'),
                    help='显式授权（授权人 + 时点）；未传则拒绝任何写库动作')
    ap.add_argument('--gate-evidence', help='记录 B17-02 闸门生效态的证据文件（替代 guard 脚本探测）')
    ap.add_argument('--from-anchor', help='--revert 用：整治后库的 SHA256（防还原错镜像）')
    args = ap.parse_args(argv)

    actions = [a for a in ('check', 'apply', 'revert', 'rollback') if getattr(args, a)]
    if len(actions) > 1:
        fail('choose exactly one of --check / --apply / --revert / --rollback', 2)
    action = actions[0] if actions else 'check'

    if action == 'check':
        return check_mode(args)
    if action == 'apply':
        return apply_mode(args)
    if action == 'revert':
        return revert_mode(args)
    return rollback_mode(args)


if __name__ == '__main__':
    sys.exit(main())
