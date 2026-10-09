"""is_archived 读取点登记执法（B17-07）。

背景
    ``is_archived`` 的 NULL 语义是这套代码的历史坑：``is_archived=False`` 与
    ``is_archived IS NULL`` 是两回事，而早期写法（``filter_by(is_archived=False)``）
    只认前者 ⇒ NULL 行既不出现在「未存档」列表里，也不出现在「已存档」列表里，
    等于**凭空消失**。B17-06 把可见性面上的读取点统一成
    ``db.or_(X.is_archived.is_(False), X.is_archived.is_(None))``（NULL ⇒ 未存档）。
    本脚本是这条口径的**执法位**：任何新增/改动的 is_archived 读取点都必须在这张
    登记表里显式出现，否则说明口径被绕过了。

口径（出现点 = 文件 + 归一化行文本 + 形状）
    扫描面：``<root>/app/**/*.py`` 与 ``<root>/app/**/*.html``（模板面也只有
    Python/Jinja 两种读取形式）。跳过 ``__pycache__``。行文本取 ``strip()`` 后把
    连续空白折叠成单空格 —— 判等用**文本**，行号只作为现场盘点读数打印（行号会漂移，
    故登记表里记的快照行号只用于对照提示，不参与判等）。

    形状（按顺序判定，先特殊后一般）：
      SCHEMA          ``is_archived = db.Column(...)``（模型列定义）
      AUDIT_DICT      ``'is_archived': old_archived``（审计 dict 字面键）
      WRITE_ASSIGN    ``X.is_archived = <expr>``（赋值/写）
      BARE_FALSE      ``filter_by(is_archived=False)`` / ``X.is_archived == False`` ⇒ **例外形状**
      KWARG           ``is_archived=<expr>``（构造/更新时透传）
      UNIFIED_PAIR    同一行同时含 ``.is_archived.is_(False)`` 与 ``.is_archived.is_(None)``
      UNIFIED_PARTIAL 同一谓词跨行（只含其中一半）
      READ_TRUTHY     裸 ``X.is_archived`` 真值读（None 为假 ⇒ 语义与统一谓词一致）
      OTHER           未分类 ⇒ 必须带理由显式登记为 EXCEPTION 才放行

    类别（kind）：``UNIFIED``（读取语义与统一谓词一致）/ ``EXCEPTION``（偏离，须带理由 +
    盘点快照）/ ``NON_FILTER``（写、审计、schema、透传 —— 不是读取判定）。形状与类别
    一一对应，登记成别的类别即违规（禁止把 BARE_FALSE 登记成 UNIFIED 来消声）。

判据（逐组判等：``(文件, 形状) → 处数``）
    1. 现场有、登记表没有 ⇒ 未登记新增 ⇒ exit 1；
    2. 处数与登记不符 ⇒ 计数漂移（新增/删除读取点）⇒ exit 1；
    3. 登记表有、现场 0 处 ⇒ 陈旧登记（改了码没改登记）⇒ exit 1；
    4. 条目 reason 为空、或 EXCEPTION 缺盘点快照 ⇒ exit 1；
    5. 形状默认类别与登记类别不符 ⇒ exit 1。

用法（仓库根目录）
    python -B scripts/check_is_archived_policy.py              # 执法
    python -B scripts/check_is_archived_policy.py --inventory  # 只打印现场盘点（建表用）
    python -B scripts/check_is_archived_policy.py --root DIR   # 扫 DIR/app/**（注入/阴性对照）
    python -B scripts/check_is_archived_policy.py --selftest   # 判等引擎的 6 条合成对照

退出码：0 = 登记表与现场逐组一致；1 = 上述任一违规；2 = 用法/环境错。
"""

import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SCAN_DIR = 'app'
SCAN_EXT = ('.py', '.html')

# ---------------------------------------------------------------- 形状判定

_RE_SCHEMA = re.compile(r'is_archived\s*=\s*db\.Column')
_RE_AUDIT = re.compile(r"'is_archived'\s*:")
_RE_WRITE = re.compile(r'\.is_archived\s*=(?!=)')
_RE_KWARG = re.compile(r'(?<![\w.])is_archived\s*=(?!=)')
_RE_BARE_FALSE = re.compile(r'filter_by\(is_archived\s*=\s*False|\.is_archived\s*==\s*False')
_RE_READ = re.compile(r'\.is_archived')

# 形状 → (默认类别, 角色)。读取判定只有 UNIFIED / EXCEPTION 两种；其余是写/审计/schema。
SHAPE_KIND = {
    'SCHEMA': ('NON_FILTER', 'schema'),
    'AUDIT_DICT': ('NON_FILTER', 'audit'),
    'WRITE_ASSIGN': ('NON_FILTER', 'write'),
    'KWARG': ('NON_FILTER', 'kwarg'),
    'BARE_FALSE': ('EXCEPTION', 'filter'),
    'UNIFIED_PAIR': ('UNIFIED', 'filter'),
    'UNIFIED_PARTIAL': ('UNIFIED', 'filter'),
    'READ_TRUTHY': ('UNIFIED', 'read_value'),
    'OTHER': (None, None),
}


def normalize(line):
    """归一化行文本：去首尾空白 + 连续空白折叠成单空格。判等用文本，行号只做盘点读数。"""
    return re.sub(r'\s+', ' ', line.strip())


def classify(text):
    """按有序规则判形状；OTHER = 未分类（必须显式登记为 EXCEPTION 才放行）。"""
    if _RE_SCHEMA.search(text):
        return 'SCHEMA'
    if _RE_AUDIT.search(text):
        return 'AUDIT_DICT'
    if _RE_WRITE.search(text):
        return 'WRITE_ASSIGN'
    if _RE_BARE_FALSE.search(text):
        return 'BARE_FALSE'
    if _RE_KWARG.search(text):
        return 'KWARG'
    has_false = '.is_archived.is_(False)' in text
    has_none = '.is_archived.is_(None)' in text
    if has_false and has_none:
        return 'UNIFIED_PAIR'
    if has_false or has_none:
        return 'UNIFIED_PARTIAL'
    if _RE_READ.search(text):
        return 'READ_TRUTHY'
    return 'OTHER'


def records_from_lines(relpath, lines):
    """行序列 → 出现点记录（供 --selftest 免盘构造）。"""
    out = []
    for i, line in enumerate(lines, 1):
        if 'is_archived' not in line:
            continue
        text = normalize(line)
        shape = classify(text)
        out.append({'file': relpath, 'line': i, 'text': text, 'shape': shape,
                    'kind': SHAPE_KIND[shape][0]})
    return out


def scan(root):
    """扫 ``<root>/app/**``，返回现场出现点记录（按 文件/行号 排序）。"""
    base = os.path.join(root, SCAN_DIR)
    if not os.path.isdir(base):
        raise SystemExit('[is_archived] 用法错：扫描面不存在 %s' % base)
    records = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if d != '__pycache__')
        for name in sorted(filenames):
            if not name.endswith(SCAN_EXT):
                continue
            path = os.path.join(dirpath, name)
            with open(path, encoding='utf-8') as fh:
                records.extend(records_from_lines(os.path.relpath(path, root).replace('\\', '/'),
                                                  fh.read().splitlines()))
    return records


# ---------------------------------------------------------------- 登记表
# 键 = (文件, 形状)；值 = (处数, 类别, 理由, 快照行号[, 盘点快照说明])
# 理由必须写「为什么这个形状在这个文件里是合规的」；EXCEPTION 另须给盘点快照（含现场重取行号）。
REGISTRY = {
    # --- 模型层：列定义（非读取） ---
    ('app/models.py', 'SCHEMA'): (
        3, 'NON_FILTER',
        'RawMaterial/Consumable/FinishedProduct 的 is_archived 列定义（Boolean, default=False），'
        'NULL 只可能来自历史数据，故读取面必须显式判空。',
        [457, 526, 610]),

    # --- 统一谓词（NULL ⇒ 未存档），B17-06 口径 ---
    ('app/main/quality.py', 'UNIFIED_PAIR'): (
        1, 'UNIFIED',
        '成品质检列表的非存档谓词，本就是统一形（is_(False) or is_(None)）。',
        [775]),
    ('app/main/routes.py', 'UNIFIED_PAIR'): (
        8, 'UNIFIED',
        '库存/看板各实体列表的「未存档」谓词，统一形：db.or_(X.is_archived.is_(False), '
        'X.is_archived.is_(None))（B17-06 六处新增 + 两处既有）。',
        [5308, 5319, 6703, 6837, 6844, 12669, 12697, 12726]),
    ('app/services/mes_service.py', 'UNIFIED_PARTIAL'): (
        2, 'UNIFIED',
        '同一条 or_ 跨两行（:1728 收 is_(False)、:1729 收 is_(None)），合起来即统一谓词。',
        [1728, 1729]),

    # --- 真值读（None 为假 ⇒ 与统一谓词同向：NULL 视为未存档） ---
    ('app/main/routes.py', 'READ_TRUTHY'): (
        4, 'UNIFIED',
        '存档/取消存档端点里的真值读：old_archived = X.is_archived 与 '
        "'存档' if X.is_archived else '取消存档'。None 为假 ⇒ 与统一谓词同向（NULL = 未存档），"
        '且只用于写前的审计记录，不参与过滤。',
        [6743, 6745, 6785, 6787]),
    ('app/services/mes_service.py', 'READ_TRUTHY'): (
        1, 'UNIFIED',
        'if finished_product.is_archived: —— 真值判定，None 为假 ⇒ NULL 视为未存档，'
        '与统一谓词同向。',
        [1809]),
    ('app/templates/main/inventory.html', 'READ_TRUTHY'): (
        10, 'UNIFIED',
        '库存页模板的展示标记 {% if item.is_archived %}（徽标/按钮态）：Jinja 里 None 为假 '
        '⇒ NULL 视为未存档，与统一谓词同向；模板不做过滤，只做展示。',
        [95, 121, 131, 133, 134, 163, 189, 199, 201, 202]),

    # --- 写 / 审计 / 透传（非读取判定） ---
    ('app/main/routes.py', 'WRITE_ASSIGN'): (
        4, 'NON_FILTER',
        '存档/取消存档端点的赋值写回（X.is_archived = not X.is_archived / True），走 ORM 落库。',
        [6744, 6786, 6851, 6856]),
    ('app/main/routes.py', 'AUDIT_DICT'): (
        4, 'NON_FILTER',
        '审计日志 old_data/new_data 里的字面键，透传原值（不判 NULL）。',
        [6756, 6757, 6798, 6799]),
    ('app/services/mes_service.py', 'KWARG'): (
        1, 'NON_FILTER',
        'is_archived=fp.is_archived 构造/透传参数，不做判定。',
        [1783]),

    # --- 例外（偏离统一谓词，必须带理由 + 盘点快照） ---
    ('app/services/mes_service.py', 'BARE_FALSE'): (
        3, 'EXCEPTION',
        '加料预警数据源用裸 filter_by(is_archived=False, status=...)：NULL 行不可见。'
        '保留理由：预警的「在库」口径要求**显式**非存档，NULL 属历史脏数据，是否纳入预警面'
        '要另立判据（属 B17-07 例外，本脚本只登记不放宽；改语义需单独提案）。',
        [1607, 1613, 1619],
        '盘点快照：规划期行号 app/services/mes_service.py:1441/1447/1453 已漂移，'
        '现场重取 = :1607/:1613/:1619（B17-00 契约 §2-B17-07）。'),
}


# ---------------------------------------------------------------- 判等引擎

def groups(records):
    """出现点记录 → {(file, shape): {'count', 'lines', 'texts'}}。"""
    out = {}
    for r in records:
        g = out.setdefault((r['file'], r['shape']),
                           {'count': 0, 'lines': [], 'texts': []})
        g['count'] += 1
        g['lines'].append(r['line'])
        if r['text'] not in g['texts']:
            g['texts'].append(r['text'])
    return out


def check(records, registry):
    """返回 (violations, notes)；notes = 行号漂移一类只提示不判红的信息。"""
    live = groups(records)
    viol, notes = [], []
    for key, entry in sorted(registry.items()):
        fpath, shape = key
        count, kind, reason = entry[0], entry[1], entry[2]
        snapshot = entry[3] if len(entry) > 3 else []
        note = entry[4] if len(entry) > 4 else ''
        default_kind = SHAPE_KIND.get(shape, (None, None))[0]
        if not reason or not reason.strip():
            viol.append('登记缺理由：%s/%s' % (fpath, shape))
        if kind == 'EXCEPTION' and not (snapshot and note.strip()):
            viol.append('EXCEPTION 缺盘点快照：%s/%s（须给快照行号 + 说明）' % (fpath, shape))
        if default_kind is not None and kind != default_kind:
            viol.append('形状与登记类别不符：%s/%s 形状默认 %s，登记 %s'
                        % (fpath, shape, default_kind, kind))
        g = live.get(key)
        if g is None:
            viol.append('陈旧登记：%s 的 %s 现场 0 处（登记 %d 处）⇒ 改了码没改登记表'
                        % (fpath, shape, count))
            continue
        if g['count'] != count:
            viol.append('计数漂移：%s 的 %s 登记 %d 处 / 现场 %d 处（现场行号 %s）'
                        % (fpath, shape, count, g['count'], g['lines']))
        if sorted(snapshot) != sorted(g['lines']):
            notes.append('行号漂移（按文本判等，不判红）：%s 的 %s 登记快照 %s / 现场 %s'
                         % (fpath, shape, snapshot, g['lines']))
    for key, g in sorted(live.items()):
        if key not in registry:
            viol.append('未登记%s：%s 的 %s 共 %d 处（首个 %s:%d）'
                        % ('（未分类形状，须带理由登记）' if key[1] == 'OTHER' else '读取点',
                           key[0], key[1], g['count'], key[0], g['lines'][0]))
    return viol, notes


# ---------------------------------------------------------------- selftest

def selftest():
    """判等引擎的合成对照（不读盘）：每组红的成因必须能被单独触发。"""
    reg = {
        ('app/main/x.py', 'UNIFIED_PAIR'): (1, 'UNIFIED', '统一谓词', [10]),
        ('app/main/x.py', 'BARE_FALSE'): (1, 'EXCEPTION', '裸 False 判定', [11], '快照 11'),
    }
    good = [
        "q = q.filter(db.or_(P.is_archived.is_(False), P.is_archived.is_(None)))",  # :1
        "rows = P.query.filter_by(is_archived=False).all()",                        # :2
    ]
    cases = []

    def run(lines, registry=reg):
        return check(records_from_lines('app/main/x.py', lines), registry)

    cases.append(('登记表与现场一致 ⇒ 无违规', not run(good)[0]))
    cases.append(('新增未登记读取点（新形状）⇒ 红',
                  any('未登记' in v for v in run(good + ['if p.is_archived:'])[0])))
    cases.append(('同形状处数 +1 ⇒ 计数漂移红',
                  any('计数漂移' in v for v in run(good + [good[0]])[0])))
    cases.append(('陈旧登记（现场删光）⇒ 红',
                  any('陈旧登记' in v for v in run([])[0])))
    bad_reg = dict(reg)
    bad_reg[('app/main/x.py', 'BARE_FALSE')] = (1, 'EXCEPTION', '', [11], '')
    cases.append(('EXCEPTION 缺理由/快照 ⇒ 红',
                  any('缺盘点快照' in v or '缺理由' in v for v in run(good, bad_reg)[0])))
    bad_reg2 = dict(reg)
    bad_reg2[('app/main/x.py', 'BARE_FALSE')] = (1, 'UNIFIED', '想蒙混', [11], '快照 11')
    cases.append(('把例外形状登记成 UNIFIED ⇒ 红',
                  any('形状与登记类别不符' in v for v in run(good, bad_reg2)[0])))

    bad = [name for name, ok in cases if not ok]
    print('[is_archived] selftest %d/%d 通过%s'
          % (len(cases) - len(bad), len(cases),
             '' if not bad else '；FAIL=' + ' / '.join(bad)))
    return 1 if bad else 0


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description='is_archived 读取点登记执法（B17-07）')
    ap.add_argument('--root', default=REPO, help='仓库根（扫 <root>/app/**）')
    ap.add_argument('--inventory', action='store_true', help='只打印现场盘点')
    ap.add_argument('--selftest', action='store_true', help='判等引擎合成对照')
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    records = scan(args.root)
    live = groups(records)
    counts = {}
    for r in records:
        counts[r['kind']] = counts.get(r['kind'], 0) + 1

    if args.inventory:
        for key, g in sorted(live.items()):
            print('[is_archived] %s | %s | %d 处 | 行 %s'
                  % (key[0], key[1], g['count'], g['lines']))
            for t in g['texts']:
                print('[is_archived]     %s' % t)
        print('[is_archived] 扫描面 %s/%s/**：%d 文件、%d 处出现点、%d 组；类别 %s'
              % (args.root, SCAN_DIR, len(set(r['file'] for r in records)), len(records),
                 len(live), ' / '.join('%s %d 处' % kv for kv in sorted(counts.items()))))
        return 0

    viol, notes = check(records, REGISTRY)
    for n in notes:
        print('[is_archived][WARN] %s' % n)
    for v in viol:
        print('[is_archived][VIOLATION] %s' % v)
    n_py = len(set(r['file'] for r in records if r['file'].endswith('.py')))
    n_html = len(set(r['file'] for r in records if r['file'].endswith('.html')))
    print('[is_archived] 扫描面 %s/%s/**：py %d 文件 + html %d 文件、出现点 %d 处、登记组 %d 组；'
          '类别 %s' % (args.root, SCAN_DIR, n_py, n_html, len(records), len(live),
                    ' / '.join('%s %d 处' % kv for kv in sorted(counts.items()))))
    if viol:
        print('[is_archived] 登记表与现场不一致（violations=%d）' % len(viol))
        return 1
    print('[is_archived] 登记表与现场逐组一致（无未登记新增、无计数漂移、无陈旧登记）')
    print('RESULT: OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
