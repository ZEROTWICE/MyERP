# -*- coding: utf-8 -*-
"""修正文档内相对链接基数（原写少一层 `../`）：`../X` -> `../../X`，`_probe/X` -> `../_probe/X`。

只改 Markdown 链接目标 `](...)`，并对每个新目标做 exists() 断言；有任何未命中即拒绝写盘。
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
DOC = ROOT / 'docs' / 'test-reports' / '2026-10' / '01-基线事实清单.md'
t = DOC.read_text(encoding='utf-8')

pat = re.compile(r'(\[[^\]]+\]\()([^)\s]+)(\))')


def repl(m):
    label, url, close = m.group(1), m.group(2), m.group(3)
    if url.startswith(('http://', 'https://', '#')):
        return m.group(0)
    frag = ''
    base, _, rest = url.partition('#')
    if rest:
        frag = '#' + rest
    if base.startswith('../'):
        new = '../' + base
    elif base.startswith('_probe/'):
        new = '../' + base
    else:
        print(f'!! 未预期目标，中止：{url}')
        sys.exit(1)
    target = (DOC.parent / new).resolve()
    if not target.exists():
        print(f'!! 新目标不存在，中止：{new} -> {target}')
        sys.exit(1)
    return label + new + frag + close


new_t, n = pat.subn(repl, t)

# 复核：替换后所有相对目标必须 exists()
bad = []
for _label, url, _close in pat.findall(new_t):
    if url.startswith(('http://', 'https://', '#')):
        continue
    base = url.split('#')[0]
    if not (DOC.parent / base).resolve().exists():
        bad.append(url)
print(f'处理前链接实例 = {len(pat.findall(t))}；替换 = {n} 处；替换后失配 = {bad}')
if bad:
    sys.exit(1)

DOC.write_text(new_t, encoding='utf-8')
print('已写盘：', DOC)
print('行数 =', len(new_t.splitlines()))
