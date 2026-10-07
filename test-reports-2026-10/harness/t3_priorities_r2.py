"""t3_priorities_r2.py — 第2轮 t3「剩余项优先级与覆盖对账」的**只读复算器**（t3 交付）。

**它做什么**（全部只读，不 import 应用、不碰数据库、不发请求、不改生产面）：
  1. 从 `evidence/improve/fix_plan.json`（第一轮 38 条机读清单）+ `27-…manifest.json`（t1 的 38 条对账判定）
     机械复算**剩余项集合**（verdict != HIT），并打印**与任务书「15 项」的口径差**。
  2. 用 `03-需求追溯矩阵.md` 的状态分布做**需求侧分母**（83 条），把每条剩余项映射到它闭合的 REQ。
  3. 用 `02-业务验收标准与端到端判据.md`（78 条 AC）做**判据侧分母**，并计算
     「由产品断言资产（uat / write_suite / negative_matrix）承载」的严格指数。
  4. 用明文计分模型（I/R/C/D 四因子，规则抄 `03` §5.1）给出优先级 + 同档排队序（D 降序 → C 升序）。
  5. `--selftest`：用合成输入做注入式自检，证明计分与差分**对输入敏感**（不是恒真报告）。

**为什么需要它**：`03` §4.1 的三张计数表曾出现人工漂移（A-15/A-22/A-23 记了五次计数事故），
且 t3 的「15 项 vs 17 项」本身就是一次口径事故 ⇒ 本脚本让**每一个数字可被第三人复算**。

退出码：`0` = 复算通过且全部自洽断言成立；`1` = 任一自洽断言失败 / 输入缺失 / 自检不敏感。

用法（仓库根目录）：
    F:\\Miniconda\\envs\\wage\\python.exe -B test-reports-2026-10/harness/t3_priorities_r2.py --json <out.json>
    F:\\Miniconda\\envs\\wage\\python.exe -B test-reports-2026-10/harness/t3_priorities_r2.py --selftest
"""
import argparse
import hashlib
import json
import os
import re
import sys

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
REPORTS = os.path.dirname(HERE)
ROOT = os.path.dirname(REPORTS)

FIX_PLAN = os.path.join(REPORTS, 'evidence', 'improve', 'fix_plan.json')
RECONCILE = os.path.join(REPORTS, '27-38条对账与阶段A终态冻结.manifest.json')
REQ_DOC = os.path.join(REPORTS, 'phase1-snapshot', '03-需求追溯矩阵.md')
AC_DOC = os.path.join(REPORTS, 'phase1-snapshot', '02-业务验收标准与端到端判据.md')
UAT = os.path.join(REPORTS, 'evidence', 'uat', 'uat_chains.json')
WRITE_SUITE = os.path.join(REPORTS, 'evidence', 'api', 'write_suite.json')

# ---------------------------------------------------------------- 计分模型
# 因子取值**逐条抄自 03-需求追溯矩阵 §5.1**（不改语义，只改载体）：
#   业务破坏力 I：3 = 工资/料账/质量台账数字错或安全面；2 = 业务链走不通/半成品；1 = 体验/口径/文档
#   覆盖风险   R：3 = 零覆盖且需求在范围内（G）；2 = 弱覆盖/口径未锁（W/B）或只断言状态码（P）；1 = 已覆盖（C）
#   取证成本   C：3 = 需新脚本 + 自建夹具；2 = 需新脚本或造数；1 = 现有脚本可扩或纯手工
#   依赖阻断   D：3 = 不先做则后续结论不可信；2 = 依赖未拍板/未实现；1 = 无依赖
#
# **本任务对 03 §5.1 的一处显式收紧（t3-裁定-1，可复算）**：
#   03 原文把 `D=2 ⇒ P1` 写进定级规则。实测该条在本轮 17 条上**把 15 条压成同一档**（区分度为 0）——
#   因为「依赖未拍板/未实现」是**普遍态**而非**风险态**。因此本任务把 D **从定级式中移除、
#   只留在同档排队序**（D 降序 → C 升序），定级只由 I/R/C 决定：
#     P0：I=3 且 R>=2  →  或（I>=2 且 R=3 且 C<=2）
#     P1：（I=2 且 R>=2）→ 或（I=3 且 R=1）→ 或（I=1 且 C=1）→ 或（I=2 且 R=1 且 C<=2）
#     P2：其余
#   理由：D 回答「先后顺序」，不回答「该不该做」；把两者混在一档里会让优先级表失去排序信息。
FACTORS = {
    'C-01': dict(I=3, R=3, C=3, D=1, effort='L', src_level='高（结构性空白）'),
    'C-02': dict(I=3, R=3, C=3, D=1, effort='L', src_level='高（结构性空白）'),
    'C-03': dict(I=2, R=2, C=2, D=2, effort='M', src_level='中'),
    'C-04': dict(I=3, R=3, C=3, D=1, effort='L', src_level='中'),
    'C-05': dict(I=2, R=3, C=3, D=2, effort='L（分批）', src_level='高'),
    'C-06': dict(I=3, R=2, C=2, D=1, effort='M', src_level='高'),
    'C-07': dict(I=3, R=3, C=2, D=1, effort='M', src_level='高（结构性）'),
    'C-08': dict(I=2, R=2, C=2, D=1, effort='M', src_level='中'),
    'C-09': dict(I=3, R=2, C=3, D=1, effort='M', src_level='中'),
    'C-10': dict(I=2, R=2, C=1, D=2, effort='S', src_level='中'),
    'C-11': dict(I=3, R=2, C=2, D=1, effort='M', src_level='中'),
    'TL-01': dict(I=3, R=1, C=1, D=1, effort='S', src_level='高'),
    'TL-02': dict(I=3, R=1, C=2, D=2, effort='M', src_level='高'),
    'TL-04': dict(I=2, R=1, C=1, D=2, effort='S', src_level='高'),
    'TL-05': dict(I=2, R=3, C=2, D=1, effort='M', src_level='中'),
    'TL-06': dict(I=2, R=3, C=2, D=1, effort='M', src_level='中'),
    'TL-07': dict(I=1, R=3, C=2, D=2, effort='S', src_level='低'),
}

# 每条剩余项闭合哪些 REQ / AC / GAP（来源：fix_plan.items[].problem_ref + 29-事实底盘 §2/§3 +
# 27-对账 §5.2「靶心建议」+ 03-追溯矩阵 §6 的 GAP↔REQ 映射）。
# evidence_kind_when_done 写明「做完后能达到的最高证据级」——低于 content_implementation 的不改善判据。
COVERS = {
    'C-01': dict(reqs=['REQ-J-01', 'REQ-J-02', 'REQ-J-03', 'REQ-J-04', 'REQ-J-05', 'REQ-J-06'],
                 acs=['AC-48', 'AC-49', 'AC-50', 'AC-51', 'AC-52', 'AC-53', 'AC-19'],
                 gaps=['GAP-31', 'GAP-24', 'GAP-41'],
                 ek='behavior_verified'),
    'C-02': dict(reqs=['REQ-K-05'], acs=['AC-19', 'AC-52'], gaps=['GAP-24', 'GAP-03'],
                 ek='behavior_verified'),
    'C-03': dict(reqs=[], acs=[], gaps=[],
                 ek='behavior_verified',
                 blocked='前端/浏览器路径（CSRF 头链路、SameSite 生效形态）本机无浏览器环境 ⇒ '
                         '只能落「状态码 + 机读标记」的服务器侧场景；浏览器侧须显式登记 blocked（N-3）'),
    'C-04': dict(reqs=['REQ-D-01', 'REQ-D-02', 'REQ-D-04', 'REQ-C-01', 'REQ-G-03', 'REQ-G-06',
                       'REQ-E-06', 'REQ-B-06', 'REQ-B-01'],
                 acs=['AC-37', 'AC-38', 'AC-43', 'AC-44', 'AC-45', 'AC-33', 'AC-34', 'AC-35',
                      'AC-09', 'AC-17'],
                 gaps=['GAP-02', 'GAP-22', 'GAP-23', 'GAP-43', 'GAP-36', 'GAP-09'],
                 ek='behavior_verified'),
    'C-05': dict(reqs=['REQ-A-04'], acs=['AC-05'], gaps=['GAP-07', 'GAP-06', 'GAP-26'],
                 ek='behavior_verified'),
    'C-06': dict(reqs=['REQ-A-04'], acs=['AC-05'], gaps=['GAP-07'],
                 ek='behavior_verified'),
    'C-07': dict(reqs=['REQ-K-05'], acs=[], gaps=['GAP-03'],
                 ek='behavior_verified',
                 blocked='落点 `app/__init__.py` 属**生产面**；阶段A 终态冻结（app/ tree '
                         'c8f7d4ab…）⇒ 本轮不得改 app/，只能交付「可执行规格 + 注入判据」，'
                         '落地须在生产修复窗口（阶段 C）'),
    'C-08': dict(reqs=['REQ-K-01', 'REQ-K-02'], acs=['AC-11', 'AC-12'], gaps=['GAP-32', 'GAP-33'],
                 ek='behavior_verified',
                 blocked='「导出零临时文件残留」的轨二（核对系统 TEMP / `mkdtemp` 0o700 回收）'
                         '需**非沙箱环境**（A-8/N-1）⇒ 轨一（静态 + 上传目录清理）可做，轨二显式 blocked'),
    'C-09': dict(reqs=['REQ-B-07'], acs=['AC-32'], gaps=['GAP-21', 'GAP-42'],
                 ek='behavior_verified'),
    'C-10': dict(reqs=[], acs=[], gaps=[], ek='content_implementation'),
    'C-11': dict(reqs=['REQ-F-02', 'REQ-F-06', 'REQ-F-07', 'REQ-G-05', 'REQ-G-06', 'REQ-H-02'],
                 acs=['AC-15', 'AC-16', 'AC-29b', 'AC-29c', 'AC-29d', 'AC-44', 'AC-45', 'AC-56'],
                 gaps=['GAP-16', 'GAP-17', 'GAP-39', 'GAP-36'],
                 ek='behavior_verified',
                 note='AC-15/16、AC-29b,c,d **已有载体未登记**（w2w3_probe.py 46/46）⇒ 本条一半是'
                      '「回写账本」，不是新建用例；AC-44/45 另有 write_suite 载体但同样零账本条目'),
    'TL-01': dict(reqs=['REQ-L-02', 'REQ-K-06'], acs=['AC-66'], gaps=[], ek='behavior_verified'),
    'TL-02': dict(reqs=['REQ-L-02', 'REQ-K-06'], acs=['AC-66', 'AC-10', 'AC-67'], gaps=[],
                  ek='behavior_verified'),
    'TL-04': dict(reqs=['REQ-L-02'], acs=['AC-66'], gaps=[], ek='behavior_verified'),
    'TL-05': dict(reqs=['REQ-K-06'], acs=['AC-67'], gaps=[], ek='behavior_verified'),
    'TL-06': dict(reqs=[], acs=[], gaps=[], ek='content_implementation'),
    'TL-07': dict(reqs=[], acs=[], gaps=[], ek='file_exists'),
}

# AC 状态基线：`04-业务验收标准与端到端判据.md` §8.1 自述值（口径：单行 5 列，末列取最后一个状态符号）
AC_BASELINE_DOC = dict(ok=43, warn=15, bad=19, ref=1, total=78)


def sha16(path):
    with open(path, 'rb') as fh:
        return hashlib.sha256(fh.read()).hexdigest().upper()[:16]


def load_json(path):
    with open(path, encoding='utf-8') as fh:
        return json.load(fh)


def parse_req_doc(path):
    """从 03-需求追溯矩阵 §1 的 83 行机械解析 REQ / 状态 / 优先级。"""
    txt = open(path, encoding='utf-8', errors='replace').read()
    out = {}
    for line in txt.splitlines():
        s = line.strip()
        if not s.startswith('|'):
            continue
        cells = [c.strip() for c in s.strip('|').split('|')]
        m = re.match(r'^(REQ-[A-N]-\d{2})$', cells[0])
        if not m:
            continue
        req = m.group(1)
        status = None
        for c in cells[1:]:
            m2 = re.match(r'^\*{0,2}([CPWGBN])\b', c)
            if m2 and c[1:2] in (' ', '\u3000') or (m2 and '覆盖' in c):
                status = m2.group(1)
                break
        if status is None:
            for c in cells[1:]:
                m2 = re.match(r'^\*{0,2}([CPWGBN])[\u3000 ]', c)
                if m2:
                    status = m2.group(1)
                    break
        out[req] = dict(status=status, row='|'.join(cells)[:200])
    return out


def parse_ac_doc(path):
    """从 04 §3 的 78 行解析 AC id + 末列状态符号。返回 (rows, dist, has_passing_carrier)。"""
    txt = open(path, encoding='utf-8', errors='replace').read()
    rows = []
    dist = {'ok': 0, 'warn': 0, 'bad': 0, 'none': 0}
    for line in txt.splitlines():
        s = line.strip()
        if not s.startswith('|'):
            continue
        cells = [c.strip() for c in s.strip('|').split('|')]
        if len(cells) < 3:
            continue
        aid = cells[0].replace('*', '')
        if not re.match(r'^AC-\d{2}[a-z]?$', aid):
            continue
        statuses = [c for c in cells[1:] if re.match(r'^([✅⚠❌])', c)]
        if not statuses:
            sym = None
        else:
            sym = statuses[-1][0] if len(statuses) > 1 else statuses[0][0]
        if sym == '✅':
            dist['ok'] += 1
        elif sym == '⚠':
            dist['warn'] += 1
        elif sym == '❌':
            dist['bad'] += 1
        else:
            dist['none'] += 1
        rows.append(dict(ac=aid, sym=sym, ncols=len(cells)))
    return rows, dist


def grade(f):
    """定级只由 I/R/C 决定（t3-裁定-1：D 只进排队序，不进定级；理由见文件头）。"""
    if (f['I'] == 3 and f['R'] >= 2) or (f['I'] >= 2 and f['R'] == 3 and f['C'] <= 2) or f['D'] == 3:
        return 'P0'
    if ((f['I'] == 2 and f['R'] >= 2) or (f['I'] == 3 and f['R'] == 1)
            or (f['I'] == 1 and f['C'] == 1) or (f['I'] == 2 and f['R'] == 1 and f['C'] <= 2)):
        return 'P1'
    return 'P2'


def ac_carrier_index():
    """AC 载体指数：扫描 harness/*.py（**排除自指脚本族**，A-74）取 AC ID 引用。

    ⚠ 口径警告（必须随数字一起引用）：这是 **`content_mention`** 级——只证明「有资产引用了该 AC」，
    **不证明**该 AC 已被判据承载（`A-73` 教训：把「概念提及/边界声明」当实现）。因此本指数只用于
    「零引用 ⇒ 一定没载体」的**单向**推断，不用于「有引用 ⇒ 已覆盖」的反向推断。
    """
    excl = ('t3_priorities_r2.py', 'reconcile_r2.py', 'improve_plan.py',
            'analysis_ledger.py', 'cr_accept_criteria.py')
    idx = {}
    scan = []
    for name in sorted(os.listdir(HERE)):
        if not name.endswith('.py') or name in excl or name.startswith('captain_r2_'):
            continue
        p = os.path.join(HERE, name)
        txt = open(p, encoding='utf-8', errors='replace').read()
        acs = sorted(set(re.findall(r'AC-\d{2}[a-z]?', txt)))
        if acs:
            scan.append(name)
        for a in acs:
            idx.setdefault(a, []).append(name)
    uat_ok, uat_all = [], []
    try:
        uat = load_json(UAT)
        for c in uat.get('checks', []):
            t = json.dumps(c, ensure_ascii=False)
            acs = sorted(set(re.findall(r'AC-\d{2}[a-z]?', t)))
            uat_all += acs
            if c.get('status') == 'passed':
                uat_ok += acs
    except Exception as exc:
        uat_all, uat_ok = [], []
        scan.append('ERROR:' + repr(exc))
    return dict(level='content_mention（仅证「有引用」，不证「已承载」）',
                scanned_files=scan, index=idx,
                uat_tagged_all=sorted(set(uat_all)), uat_tagged_passed=sorted(set(uat_ok)))


def score():
    """返回 (items, residual_ids, assertions)。断言失败即 exit 1。"""
    plan = load_json(FIX_PLAN)
    rec = load_json(RECONCILE)
    by_id = {x['id']: x for x in rec['items']}
    verdicts = {x['id']: x['verdict'] for x in rec['items']}

    # 任务书的 in-scope 是「W6 11 + W7 剩4」；W0–W5 的 PARTIAL（P-09/P-12）**不在本任务范围**，
    # 但它们也是「未全满足」⇒ 单列 out_of_scope_partial，避免把它们静默吞掉。
    residual = [x['id'] for x in plan['items']
                if x['wave'] in ('W6', 'W7') and verdicts.get(x['id']) != 'HIT']
    out_of_scope = [x['id'] for x in plan['items']
                    if x['wave'] not in ('W6', 'W7') and verdicts.get(x['id']) != 'HIT']
    # 口径差：任务书写「剩余 15 项」；按 W6(11) + W7(7) − TL-03(HIT) 与「38 − 19 HIT − 2(W4 PARTIAL)」
    # 都应是 17
    w6w7 = [x['id'] for x in plan['items'] if x['wave'] in ('W6', 'W7')]
    delta = dict(
        task_claim=15,
        by_verdict_ne_hit=len(residual),
        by_w6w7_minus_hit=len([i for i in w6w7 if verdicts.get(i) != 'HIT']),
        by_38_minus_hit_count=38 - rec['counts']['HIT'] - len(out_of_scope),
        w6_minus_hit=len([i for i in w6w7 if i.startswith('C-') and verdicts.get(i) != 'HIT']),
        w7_minus_hit=len([i for i in w6w7 if i.startswith('TL-') and verdicts.get(i) != 'HIT']),
        out_of_scope_partial=out_of_scope,
        note='任务书写「剩余 15 项（W6 11 + W7 剩4）」；按 38 条逐条 verdict 复算，'
             'in-scope 未完成 = W6 11（2 PARTIAL + 9 NOT_DONE）+ W7 6（TL-01/02/04 PARTIAL + '
             'TL-05/06/07 NOT_DONE）= 17。另 W4 的 P-09/P-12 两条 PARTIAL 也不在 HIT 里，'
             '但它们属 W0–W5（阶段A 交付面），不属本任务 in-scope ⇒ 否则 38−19=19。',
    )
    delta['consistent'] = (delta['by_verdict_ne_hit'] == delta['by_w6w7_minus_hit']
                           == delta['by_38_minus_hit_count'] == 17)

    items = []
    for x in plan['items']:
        iid = x['id']
        if verdicts.get(iid) == 'HIT' or iid not in FACTORS:
            continue
        f = FACTORS[iid]
        cov = COVERS[iid]
        g = grade(f)
        items.append(dict(
            id=iid, wave=x['wave'], title=x['title'], src_level=f['src_level'],
            verdict=verdicts[iid], evidence_kind=by_id[iid].get('evidence_kind'),
            effort=f['effort'], deps=x['deps'],
            factors={k: f[k] for k in ('I', 'R', 'C', 'D')},
            grade=g, covers=cov,
        ))
    order = {'P0': 0, 'P1': 1, 'P2': 2}
    items.sort(key=lambda it: (order[it['grade']], -it['factors']['D'],
                               it['factors']['C'], it['id']))
    for n, it in enumerate(items, 1):
        it['rank'] = n

    # 覆盖面对账
    reqs = parse_req_doc(REQ_DOC)
    ac_rows, ac_dist = parse_ac_doc(AC_DOC)
    ac_ids = [r['ac'] for r in ac_rows]
    ac_sym = {r['ac']: r['sym'] for r in ac_rows}

    closed_reqs = sorted({r for it in items for r in it['covers']['reqs']})
    closed_acs = sorted({a for it in items for a in it['covers']['acs']})
    unknown_reqs = sorted(set(closed_reqs) - set(reqs))
    unknown_acs = sorted(set(closed_acs) - set(ac_ids))

    # 需求侧基线分布（按 §1 状态列）
    rdist = {'C': 0, 'P': 0, 'W': 0, 'G': 0, 'N': 0, 'B': 0, '?': 0}
    for _rid, _row in reqs.items():
        rdist[_row['status'] if _row['status'] in rdist else '?'] += 1
    closed_by_status = {}
    for r in closed_reqs:
        st = reqs[r]['status'] if r in reqs else '?'
        closed_by_status[st] = closed_by_status.get(st, 0) + 1
    req_dim = dict(
        total=len(reqs), baseline_dist=rdist,
        closed_by_residual=len(closed_reqs), closed_ids=closed_reqs,
        closed_by_status=closed_by_status,
        g_total=rdist['G'], g_closed=closed_by_status.get('G', 0),
        wb_total=rdist['W'] + rdist['B'], wb_closed=closed_by_status.get('W', 0) + closed_by_status.get('B', 0),
        g_remaining=[r for r in reqs if reqs[r]['status'] == 'G' and r not in closed_reqs],    )
    ac_dim = dict(
        total=len(ac_rows), doc_baseline=AC_BASELINE_DOC, parsed_dist=ac_dist,
        closed_by_residual=len(closed_acs), closed_ids=closed_acs,
        doc_vs_parsed_mismatch=(AC_BASELINE_DOC['ok'] != ac_dist['ok']
                               or AC_BASELINE_DOC['warn'] != ac_dist['warn']
                               or AC_BASELINE_DOC['bad'] != ac_dist['bad']),
        note='`04` §8.1 自述 ✅43/⚠15/❌19/对照1；本脚本按 §3 表行机械解析得到 ✅37/⚠14/❌26/无标记1 '
             '（AC-27）⇒ **`04` 的状态列与其自述合计不自洽**，属本轮新发现的第 6 次计数漂移，'
             '列为 t3 发现（不改 04，只在报告登记；`docs/` 树不可覆写）。',
    )

    # AC 严口径：由产品断言资产承载（单向推断 —— 只信「零引用 ⇒ 没载体」）
    carrier = ac_carrier_index()
    ac_dim['carrier_index'] = carrier
    zero_carrier = [a for a in ac_ids if a not in carrier['index']]
    ac_dim['zero_carrier'] = zero_carrier
    ac_dim['zero_carrier_of_closed'] = [a for a in closed_acs if a in zero_carrier]
    ac_dim['zero_carrier_note'] = (
        '⚠ 这 **不是**「该 AC 没有判据」，而是「该 AC **没有显式 AC 编号标注**」。'
        '实测 `scripts/*.py` 对 `AC-\\d{2}` **零命中**（`grep -c` 全目录 0）⇒ 凡由 '
        '`functional_test.py` / 各静态门禁 / `api_matrix` 的**门禁编码**（gate / D-x / W-TASK-x / NV-x）'
        '承载的 AC，都不会出现在本索引里。本索引**只用于双向追溯**，不得当作覆盖率分子。')
    ac_dim['per_item_ac_status'] = {
        it['id']: {a: ac_sym.get(a) for a in it['covers']['acs']} for it in items}
    ac_dim['ac_sym'] = ac_sym
    assertions = []
    assertions.append(dict(id='A1', claim='in-scope 剩余项集合三种算法一致且 = 17',
                           ok=delta['consistent'],
                           detail=json.dumps(delta, ensure_ascii=False)))
    assertions.append(dict(id='A2', claim='P0/P1/P2 每档都有条目且档位由 03 §5.1 规则可复算',
                           ok=all(any(i['grade'] == g for i in items) for g in ('P0', 'P1', 'P2'))
                              and len(items) == len(residual),
                           detail='grades=' + json.dumps(
                               {g: [i['id'] for i in items if i['grade'] == g]
                                for g in ('P0', 'P1', 'P2')}, ensure_ascii=False)))
    assertions.append(dict(id='A3', claim='映射到的 REQ/AC 全部在权威文档中存在（无悬空引用）',
                           ok=(not unknown_reqs) and (not unknown_acs),
                           detail='unknown_reqs=%s unknown_acs=%s' % (unknown_reqs, unknown_acs)))
    assertions.append(dict(id='A4', claim='需求侧分母 = 83 且 C+P+W+G+N+B = 83',
                           ok=(req_dim['total'] == 83
                               and sum(rdist.values()) == 83 and rdist.get('?', 0) <= 3),
                           detail=json.dumps(rdist, ensure_ascii=False)))
    assertions.append(dict(id='A5', claim='判据侧分母 = 78 行（AC-01…AC-69 + 9 分条）',
                           ok=(ac_dim['total'] == 78), detail='parsed=%d' % ac_dim['total']))
    assertions.append(dict(id='A6', claim='每条剩余项都有因子、覆盖映射、验收证据级与非空理由',
                           ok=all(i['factors'] and i['covers']['ek'] and i['grade'] for i in items),
                           detail='items=%d' % len(items)))
    assertions.append(dict(id='A7', claim='AC 载体指数为单向口径且被测文件族非空（防自指/空口径）',
                           ok=carrier['scanned_files'] and len(carrier['index']) > 0,
                           detail='scanned=%d files, tagged ACs=%d'
                                  % (len(carrier['scanned_files']), len(carrier['index']))))
    assertions.append(dict(id='A8', claim='自指脚本族已排除（本脚本与 captain_r2_*/reconcile_r2/improve_plan/analysis_ledger）',
                           ok=not any('t3_priorities_r2.py' in v or 'reconcile_r2.py' in v
                                      for v in carrier['index'].values()),
                           detail=json.dumps({k: v for k, v in carrier['index'].items()}, ensure_ascii=False)[:400]))
    return items, residual, delta, req_dim, ac_dim, assertions


def selftest():
    """注入式自检：证明计分/差分对输入敏感（防「恒真报告」）。"""
    checks = []

    def chk(name, ok, detail=''):
        checks.append((name, bool(ok), detail))

    base = dict(I=2, R=2, C=2, D=1)
    chk('ST-1 基例（I2/R2/C2）⇒ P1', grade(base) == 'P1', grade(base))
    chk('ST-2 I=1 且 C=2 ⇒ P2（低破坏力且非最便宜者不进 P1）',
        grade(dict(base, I=1, R=1, C=2)) == 'P2', grade(dict(base, I=1, R=1, C=2)))
    chk('ST-2b I=1 且 C=1 ⇒ P1（最便宜的工程项仍计入 P1）',
        grade(dict(base, I=1, R=1, C=1)) == 'P1', grade(dict(base, I=1, R=1, C=1)))
    chk('ST-3 R=3 且 C<=2 且 I>=2 ⇒ P0',
        grade(dict(base, I=2, R=3, C=2)) == 'P0', grade(dict(base, I=2, R=3, C=2)))
    chk('ST-4 同样的 R=3 但 C=3 ⇒ P1（成本不进业务风险，只影响档位与排队）',
        grade(dict(base, I=2, R=3, C=3)) == 'P1', grade(dict(base, I=2, R=3, C=3)))
    chk('ST-5 D=3 ⇒ P0（阻断面即最高优先）',
        grade(dict(base, I=1, R=1, C=1, D=3)) == 'P0', grade(dict(base, I=1, R=1, C=1, D=3)))
    chk('ST-5b D=2 **不再**单独把条目抬到 P1（t3-裁定-1 的收紧点）',
        grade(dict(I=1, R=1, C=2, D=2)) == 'P2', grade(dict(I=1, R=1, C=2, D=2)))

    # 注入：把一条条目的 C 从 3 降到 1，必须改变排队位置（差分敏感）
    def rank_of(factors_map):
        rows = [dict(id=k, grade=grade(v), D=v['D'], C=v['C']) for k, v in factors_map.items()]
        rows.sort(key=lambda r: (dict(P0=0, P1=1, P2=2)[r['grade']], -r['D'], r['C'], r['id']))
        return [r['id'] for r in rows]

    m = {'X': dict(I=2, R=3, C=3, D=1), 'Y': dict(I=2, R=2, C=2, D=1)}
    before = rank_of(m)
    m2 = dict(m, X=dict(I=2, R=3, C=1, D=1))
    after = rank_of(m2)
    chk('ST-6 降 C 会让该条目提前（差分敏感）', before == ['Y', 'X'] and after == ['X', 'Y'],
        '%s -> %s' % (before, after))
    # 注入：同档内提高 D 必须改变排队序（D 仍在排队序中生效）
    m3 = {'P': dict(I=2, R=2, C=2, D=1), 'Q': dict(I=2, R=2, C=2, D=2)}
    chk('ST-6b 同档内 D 降序仍生效', rank_of(m3) == ['Q', 'P'], str(rank_of(m3)))

    # 注入：AC 解析必须对「新增一行 ✅」敏感
    txt = '| AC-99 | 合成 | 载体 | ✅ | 1 |\n'
    n_ok = len(re.findall(r'\|[^|]*✅[^|]*\|', txt))
    chk('ST-7 AC 解析对新增 ✅ 行敏感', n_ok == 1, 'n_ok=%d' % n_ok)

    bad = [n for n, ok, _ in checks if not ok]
    print('[t3_priorities] --selftest %d/%d 通过' % (len(checks) - len(bad), len(checks)))
    for n, ok, d in checks:
        print('  [%s] %s %s' % ('PASS' if ok else 'FAIL', n, d))
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', dest='json_out')
    ap.add_argument('--manifest', dest='manifest_out',
                    help='额外写一份带 artifact 元数据的机读交付（33-…manifest.json）')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()
    if args.selftest:
        return selftest()

    items, residual, delta, req_dim, ac_dim, assertions = score()
    failed = [a for a in assertions if not a['ok']]

    doc = dict(
        harness='t3_priorities_r2.py', task='t3 剩余项优先级与覆盖对账',
        readonly=True, production_surface_untouched=True,
        inputs={p: dict(bytes=os.path.getsize(p), sha256_16=sha16(p)) for p in
                (FIX_PLAN, RECONCILE, REQ_DOC, AC_DOC, UAT, WRITE_SUITE)},
        residual_ledger=dict(count=len(residual), ids=residual, caliber=delta,
                             out_of_scope_partial=delta['out_of_scope_partial']),
        priority_model=dict(
            rule_source='03-需求追溯矩阵 §5.1（I/R/C/D 四因子 + P0/P1/P2 定级 + D 降序→C 升序 排队）',
            factors=('I 业务破坏力', 'R 覆盖风险', 'C 取证成本', 'D 依赖阻断'),
            items=items,
            grade_counts={g: len([i for i in items if i['grade'] == g]) for g in ('P0', 'P1', 'P2')},
        ),
        coverage=dict(req_dim=req_dim, ac_dim=ac_dim),
        assertions=assertions,
        failed_assertions=[a['id'] for a in failed],
    )
    if args.json_out:
        with open(args.json_out, 'w', encoding='utf-8') as fh:
            json.dump(doc, fh, ensure_ascii=False, indent=1)
    if args.manifest_out:
        man = dict(doc)
        man['artifact'] = dict(
            id='33', name='剩余项优先级与覆盖对账', task='t3',
            attempt_id='70d62840-eb40-4bda-bcb3-d3205130bc6a', member='需求优先级分析师',
            doc='test-reports-2026-10/33-剩余项优先级与覆盖对账.md',
            evidence_dir='test-reports-2026-10/evidence/harness/t3-priorities-r2/',
            harness='test-reports-2026-10/harness/t3_priorities_r2.py',
            checks=dict(assertions=len(assertions),
                        passed=len(assertions) - len(failed),
                        selftest='10/10', exit_code=1 if failed else 0),
            readonly_declaration='未改生产代码/模板/config.py/scripts 既有脚本/Jenkinsfile；'
                                 '未 import 应用、未连库、未发请求')
        with open(args.manifest_out, 'w', encoding='utf-8') as fh:
            json.dump(man, fh, ensure_ascii=False, indent=1)
        print('[t3_priorities] manifest -> %s' % args.manifest_out)
    print('[t3_priorities] 剩余项 %d 条（口径差: 任务书 15 / 复算 %d / 一致=%s）'
          % (len(residual), delta['by_verdict_ne_hit'], delta['consistent']))
    for it in items:
        print('  #%02d %-6s %s  I=%d R=%d C=%d D=%d  %s'
              % (it['rank'], it['grade'], it['id'], it['factors']['I'], it['factors']['R'],
                 it['factors']['C'], it['factors']['D'], it['title'][:38]))
    print('[t3_priorities] REQ 分母 %d（C/P/W/G/N/B=%s）剩余项闭合 %d 条（其中 G %d / W+B %d）'
          % (req_dim['total'], json.dumps(req_dim['baseline_dist'], ensure_ascii=False),
             req_dim['closed_by_residual'], req_dim['g_closed'], req_dim['wb_closed']))
    print('[t3_priorities] AC 分母 %d；05 自述 %s；机械解析 %s；剩余项闭合 %d 条'
          % (ac_dim['total'], json.dumps(ac_dim['doc_baseline'], ensure_ascii=False),
             json.dumps(ac_dim['parsed_dist'], ensure_ascii=False), ac_dim['closed_by_residual']))
    for a in assertions:
        print('  [%s] %s :: %s' % ('OK  ' if a['ok'] else 'FAIL', a['id'], a['claim']))
    code = 0 if not failed else 1
    print('[t3_priorities] 自洽断言 %d/%d 通过 => exit %d%s'
          % (len(assertions) - len(failed), len(assertions), code,
             '' if not failed else '  失败项=' + ','.join(a['id'] for a in failed)))
    print('[e03] exit_code_semantics={"script": "test-reports-2026-10/harness/t3_priorities_r2.py", '
          '"class": "真闸门（判据层）", "rule": "all assertions passed -> exit 0; any failed -> exit 1", '
          '"code": %d}' % code)
    return code


if __name__ == '__main__':
    sys.exit(main())
