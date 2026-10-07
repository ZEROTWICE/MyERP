# -*- coding: utf-8 -*-
"""只读探针 E：导出内存生成点、导入落盘点、page/per_page、TEMP_FOLDER、配置开关读取点。"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
APP = ROOT / 'app'
FILES = [p for p in APP.rglob('*.py') if '__pycache__' not in str(p)]


def scan(pred, label):
    print(f'\n=== {label} ===')
    n = 0
    for p in FILES:
        for i, l in enumerate(p.read_text(encoding='utf-8', errors='replace').splitlines(), 1):
            if pred(l):
                print(f'  {p.relative_to(ROOT).as_posix()}:{i}  {l.strip()[:120]}')
                n += 1
    if n == 0:
        print('  (无命中)')
    return n


scan(lambda l: 'io.BytesIO' in l, 'io.BytesIO（导出/模板内存生成）')
scan(lambda l: 'TEMP_FOLDER' in l, 'TEMP_FOLDER 使用点')
scan(lambda l: 'file.save(' in l or '.save(temp_path' in l or "save_temp_file(" in l, '上传落盘点（file.save / save_temp_file）')
scan(lambda l: 'pd.read_excel' in l, 'pd.read_excel（导入解析）')

# 导入端点定位：找到 @bp.route 后紧跟 def，函数名含 import
print('\n=== 含 "import" 的路由端点 ===')
for p in FILES:
    cur_route = None
    for i, l in enumerate(p.read_text(encoding='utf-8', errors='replace').splitlines(), 1):
        s = l.strip()
        if s.startswith('@bp.route'):
            cur_route = (i, s)
        elif s.startswith('def ') and cur_route and 'import' in s:
            print(f'  {p.relative_to(ROOT).as_posix()}  route@{cur_route[0]} {cur_route[1][:80]}  -> def@{i} {s[:60]}')
        elif s.startswith('@') or s.startswith('def '):
            pass

# SystemConfig.get 读取点（业务口径配置 vs 采购开关）
print('\n=== SystemConfig.get 读取点 ===')
for p in FILES:
    for i, l in enumerate(p.read_text(encoding='utf-8', errors='replace').splitlines(), 1):
        if 'SystemConfig.get(' in l:
            m = re.search(r"SystemConfig\.get\(\s*'([^']+)'", l)
            print(f'  {p.relative_to(ROOT).as_posix()}:{i}  key={m.group(1) if m else "?"}')

# 配置 key 清点
print('\n=== SystemConfig.DEFAULT_CONFIGS 里的 key ===')
mj = (APP / 'models.py').read_text(encoding='utf-8', errors='replace')
for m in re.finditer(r"'key':\s*'([^']+)'", mj):
    print(f'  {m.group(1)}')

# per_page 白名单
print('\n=== per_page 处理点 ===')
cnt = 0
for p in FILES:
    t = p.read_text(encoding='utf-8', errors='replace')
    c = t.count('_validated_per_page') + t.count('validated_per_page')
    if c:
        print(f'  {p.relative_to(ROOT).as_posix()}: {c}')
        cnt += c
print(f'  合计 {cnt}')
