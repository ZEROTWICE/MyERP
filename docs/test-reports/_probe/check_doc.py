# -*- coding: utf-8 -*-
"""文档自查：零行表声明值 vs 名单实体数；残留旧值扫描；链接目标存在性。"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[3]
DOC = ROOT / 'docs' / 'test-reports' / '2026-10' / '01-基线事实清单.md'
t = DOC.read_text(encoding='utf-8')

m = re.search(r'\*\*行数为 0 的表（(\d+) 张）\*\*：(.+?)。', t, re.S)
declared = int(m.group(1))
names = re.findall(r'`([a-z_]+)`', m.group(2))
print(f'§3.6 声明值 = {declared}')
print(f'§3.6 名单实体数 = {len(names)}')
print(f'一致 = {declared == len(names)}')

for bad in ('(45 张)', '（45 张）', '原生即 exit 0', '原生可跑', '原生也可跑'):
    hits = [i for i, l in enumerate(t.splitlines(), 1) if bad in l]
    # 允许出现在勘误/更正/留痕段落
    print(f'残留 "{bad}" 命中行 = {hits}')

print('\n=== 相对链接目标存在性 ===')
for label, target in re.findall(r'\[([^\]]+)\]\((\.[^)#]+?)(?:#[^)]*)?\)', t):
    p = (DOC.parent / target).resolve()
    if not p.exists():
        print(f'  MISSING  {label} -> {target}')
print('（无输出表示全部命中）')

print('\n=== 行数 ===')
print(len(t.splitlines()))
