# -*- coding: utf-8 -*-
"""列出文档内全部相对链接 + 修正方案（先只看，不改）。"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[3]
DOC = ROOT / 'docs' / 'test-reports' / '2026-10' / '01-基线事实清单.md'
t = DOC.read_text(encoding='utf-8')

pat = re.compile(r'\[([^\]]+)\]\(([^)\s]+)\)')
seen = {}
for i, line in enumerate(t.splitlines(), 1):
    for label, url in pat.findall(line):
        if url.startswith(('http://', 'https://', '#')):
            continue
        base = url.split('#')[0]
        if base not in seen:
            seen[base] = []
        seen[base].append(i)

print(f'不同相对链接目标 = {len(seen)}；链接实例 = {sum(len(v) for v in seen.values())}\n')
fixed = {}
for base in sorted(seen):
    if base.startswith('../'):
        new = '../' + base
    elif base.startswith('_probe/'):
        new = '../' + base
    else:
        new = '??UNKNOWN?? ' + base
    fixed[base] = new
    p_new = (DOC.parent / new).resolve()
    print(f'  L{seen[base][0]:>4}  {base:55s} -> {new:58s} exists={p_new.exists()}')

bad = [b for b, n in fixed.items() if n.startswith('??')]
print(f'\n无法自动判定的目标 = {bad}')
pathlib.Path(ROOT / 'docs' / 'test-reports' / '_probe' / '_linkmap.txt').write_text(
    '\n'.join(f'{k}\t{v}' for k, v in fixed.items()), encoding='utf-8')
