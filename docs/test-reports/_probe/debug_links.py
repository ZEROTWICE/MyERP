# -*- coding: utf-8 -*-
"""调试：为什么相对链接目标被判为 MISSING。"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
DOC = ROOT / 'docs' / 'test-reports' / '2026-10' / '01-基线事实清单.md'
print('__file__ =', __file__)
print('ROOT =', ROOT)
print('DOC exists =', DOC.exists())
print('DOC.parent =', DOC.parent)

targets = ['../开发与测试规划-2026-10-06.md', '../../AGENTS.md', '../../app/permissions.py',
           '../../scripts/smoke_test.py', '_probe/verify_corrections.py',
           'docs/test-reports/_probe/verify_corrections.py']
for t in targets:
    p = DOC.parent / t
    print(f'  {t!r:55s} joined={str(p)[-70:]!r}')
    print(f'        exists={p.exists()}  resolved={p.resolve()} resolved_exists={p.resolve().exists()}')

print('\n实际列出 docs/ :')
for x in sorted((ROOT / 'docs').iterdir())[:12]:
    print('  ', x.name)
