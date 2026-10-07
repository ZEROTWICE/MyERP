# -*- coding: utf-8 -*-
"""只读自检：从 docs/test-reports/2026-10/03-需求追溯矩阵.md 的 §1 表格里
机械统计 REQ / 状态 / 优先级，并检查 §2/§6 的引用是否有悬空 ID。

用法：F:\\Miniconda\\envs\\wage\\python.exe -B docs/test-reports/_probe/check_trace_matrix.py
只读：只用 pathlib.read_text，不写任何文件。
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
DOC = ROOT / 'docs' / 'test-reports' / '2026-10' / '03-需求追溯矩阵.md'
text = DOC.read_text(encoding='utf-8')
lines = text.splitlines()

# ---- 先切出 §1 区段（"## 1. 需求清单" 到 "## 2. 测试用例清单"）----
try:
    i1 = next(i for i, ln in enumerate(lines) if ln.startswith('## 1. 需求清单'))
    i2 = next(i for i, ln in enumerate(lines) if ln.startswith('## 2. 测试用例清单'))
except StopIteration:
    print('无法定位 §1/§2 边界'); sys.exit(2)
sec1 = lines[i1:i2]
print('§1 区段行范围 = %d..%d（共 %d 行）' % (i1 + 1, i2, i2 - i1))

# ---- 先数「所有以 | REQ- 开头的行」，再按 §1 各子表表头分段 ----
hdr = [(i, ln) for i, ln in enumerate(sec1) if re.match(r'^### 1\.[A-N] ', ln)]
print('§1 子表标题数 =', len(hdr))
all_rows = [ln for ln in lines if re.match(r'^\|\s*REQ-[A-N]-\d\d\s*\|', ln)]
print('全文以 | REQ- 开头的行数 =', len(all_rows))

# ---- 只扫 §1 的表格行（以 | REQ- 开头）----
rows = []
for ln in sec1:
    m = re.match(r'^\|\s*(REQ-[A-N]-\d\d)\s*\|', ln)
    if not m:
        continue
    cells = [c.strip() for c in ln.strip().strip('|').split('|')]
    rows.append({'id': m.group(1), 'cells': cells, 'line': ln})

ids = [r['id'] for r in rows]
dup = {i for i in ids if ids.count(i) > 1}

# 状态列 = 含「已覆盖/部分覆盖/弱覆盖/缺口/不测/待复核」的那一列
# ⚠ 判定顺序：用「最长标签优先」避免「已覆盖」被「覆盖率」之类误伤；
#   且每个 REQ 行**只取一个**状态（N > B > W > G > P > C，取最强者）。
STAT = [('N 本阶段不测', 'N'), ('B 待复核定范围', 'B'), ('W 弱覆盖', 'W'),
        ('G 缺口', 'G'), ('P 部分覆盖', 'P'), ('C 已覆盖', 'C')]
state = {}
for r in rows:
    joined = ' '.join(r['cells'][3:5])
    hit = None
    for label, code in STAT:
        if label in joined:
            hit = code
            break
    r['state'] = hit
    state.setdefault(hit, []).append(r['id'])

# 优先级 = 最后一列的 P0/P1/P2
prio = {}
for r in rows:
    p = None
    for c in reversed(r['cells']):
        mm = re.search(r'\*{0,2}(P[012])\*{0,2}', c)
        if mm:
            p = mm.group(1)
            break
    r['prio'] = p
    prio.setdefault(p, []).append(r['id'])

print('=== §1 机械统计 ===')
print('REQ 行数 =', len(rows))
print('重复 ID  =', sorted(dup) or '无')
print('状态分布 =', {k: len(v) for k, v in sorted(state.items(), key=lambda x: str(x[0]))})
print('状态为 None 的（未能机械识别，需人工看）=', [r['id'] for r in rows if r['state'] is None])
print('优先级分布 =', {k: len(v) for k, v in sorted(prio.items(), key=lambda x: str(x[0]))})
print('优先级为 None 的 =', [r['id'] for r in rows if r['prio'] is None])
print('G 状态清单 =', ', '.join(state.get('G', [])))
print('P0 需求清单 =', ', '.join(prio.get('P0', [])))

# ---- 悬空检查：§2/§6 里引用的 REQ / TC ----
defined = set(ids)
referenced = set(re.findall(r'REQ-[A-N]-\d\d', text)) - defined
print('\n=== 引用但未定义的 REQ（应为空）===')
print(sorted(referenced) or '无')

tc_def = set(re.findall(r'^\|\s*(TC-[A-Za-z0-9\-①-⑨]+)\s*\|', text, re.M))
tc_ref = set(re.findall(r'`?(TC-[A-Za-z0-9\-]+)`?', text))
print('\n=== §2 表格里定义的 TC（%d 个）===' % len(tc_def))
print(sorted(tc_def))
print('\n=== 被引用但未在 §2 表格行首定义的 TC（需人工确认是否仅叙述性提及）===')
print(sorted(tc_ref - tc_def))

gap_def = set(re.findall(r'^\|\s*(GAP-\d+)\s*\|', text, re.M))
gap_ref = set(re.findall(r'(GAP-\d+)', text))
print('\n=== GAP 定义数 =', len(gap_def), '最大编号 =', max(int(g[4:]) for g in gap_def) if gap_def else 0)
print('=== GAP 引用但未定义 ===')
print(sorted(gap_ref - gap_def) or '无')

sys.exit(0)
