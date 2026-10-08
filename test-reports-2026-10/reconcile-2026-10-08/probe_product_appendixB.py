# -*- coding: utf-8 -*-
"""t6（产品经理）附录 B 逐组口径取证 —— 纯静态只读（不连库、不写盘除自身 output）。

覆盖：
  G-M 质检模板是否随初始化数据下发（`InspectionTemplate(` 构造点 / seed 函数）
  D21 全仓「落盘写调用」清点（`file.save(` / `save_temp_file(`），用于证「落盘只在 routes.py」
  G-H `is_archived` 谓词清单（含 `routes.py:6109` 等）
  G-D 编码规则日志（`CodeGenerationLog`）是否有查询页
  G-B `delivery_batches` 是否驱动发货（写入点 vs 读取点）
  G-A `purchase.full_workflow_enabled` / `purchase.settlement_enabled` 读取点
"""
import json
import os
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = {}


def py_files():
    for root, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in
                   ('.git', '__pycache__', 'node_modules', 'evidence', '.tmp',
                    'test-reports-2026-10')]
        for f in files:
            if f.endswith('.py'):
                yield pathlib.Path(root) / f


def grep(pattern, files=None):
    rx = re.compile(pattern)
    hits = []
    for p in (files or py_files()):
        try:
            t = p.read_text(encoding='utf-8', errors='replace')
        except Exception:  # noqa: BLE001
            continue
        for i, l in enumerate(t.splitlines(), 1):
            if rx.search(l):
                hits.append(f'{p.relative_to(ROOT).as_posix()}:{i}: {l.strip()[:120]}')
    return hits


OUT['D21_disk_write_calls'] = {
    'rule': r"grep 全 app/**/*.py：`file.save(` 或 `save_temp_file(`",
    'hits': grep(r'file\.save\(|save_temp_file\(',
                 [p for p in py_files() if str(p).replace('\\', '/').endswith('.py')
                  and 'app' in p.as_posix()]),
}
OUT['G_M_inspection_template'] = {
    'rule': 'grep `InspectionTemplate(` 与 `def <seed/init>`（全仓非 test 目录）',
    'template_ctor': grep(r'InspectionTemplate\('),
    'seed_funcs': grep(r'def\s+\w*(seed|init_default|bootstrap)\w*\s*\('),
    'active_query': grep(r'InspectionTemplate\.query'),
}
OUT['G_H_is_archived'] = {
    'rule': 'grep `is_archived`（app/**）',
    'hits': grep(r'is_archived', [p for p in py_files() if 'app' in p.as_posix()]),
}
OUT['G_D_code_rule_log'] = {
    'rule': 'grep `CodeGenerationLog`（构造点 / 查询点）与相关路由',
    'hits': grep(r'CodeGenerationLog'),
}
OUT['G_B_delivery_batches'] = {
    'rule': 'grep `delivery_batches`（模型属性 / 路由 / 发货侧读取）',
    'hits': grep(r'delivery_batches'),
}
OUT['G_A_purchase_switches'] = {
    'rule': 'grep `full_workflow_enabled` / `settlement_enabled`',
    'hits': grep(r'full_workflow_enabled|settlement_enabled'),
}
OUT['G_E_customer_delete'] = {
    'rule': 'grep 客户删除路由与关联订单校验',
    'hits': grep(r"def delete_customer|customer.*sales_orders|has_orders|销售订单.*客户"),
}

p = pathlib.Path(__file__).with_suffix('.output.json')
p.write_text(json.dumps(OUT, ensure_ascii=False, indent=1), encoding='utf-8')
print(json.dumps(OUT, ensure_ascii=False, indent=1))
