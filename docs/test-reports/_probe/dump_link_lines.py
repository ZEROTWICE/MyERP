# -*- coding: utf-8 -*-
"""按行号列出所有相对链接的确切行文本与修正后文本（供 edit 工具逐行替换）。"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[3]
DOC = ROOT / 'docs' / 'test-reports' / '2026-10' / '01-基线事实清单.md'
lines = DOC.read_text(encoding='utf-8').splitlines()

pat = re.compile(r'(\[[^\]]+\]\()([^)\s]+)(\))')
n = 0
for i, line in enumerate(lines, 1):
    if not pat.search(line):
        continue
    def repl(m):
        label, url, close = m.group(1), m.group(2), m.group(3)
        if url.startswith(('http://', 'https://', '#')):
            return m.group(0)
        base, _, rest = url.partition('#')
        new = ('../' + base) if (base.startswith('../') or base.startswith('_probe/')) else base
        return label + new + ('#' + rest if rest else '') + close
    newline = pat.sub(repl, line)
    n += 1
    print(f'--- LINE {i} (len={len(line)}) ---')
    print('OLD: ' + line)
    print('NEW: ' + newline)
print(f'\n共 {n} 行含相对链接')
