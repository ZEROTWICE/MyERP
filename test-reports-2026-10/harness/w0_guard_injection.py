#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""w0_guard_injection.py —— E-01 判据 ④ 的注入探针：**同名写入必须改名保留，绝不覆盖**。

背景（D-5 实证）：历史上任何复跑都以**同一文件名**直接覆盖 ``evidence/harness/*``，
t2 的 6 个原件因此被 t3 的复跑抹掉。本探针做两件事：

1. **干跑（不写盘）**：对 D-5 的 6 个平铺原件逐个调用 ``_env.guard_write``，
   要求返回值**全部是改名后的路径**（绝不是原件路径）⇒ 证明「想覆盖原件」会被守卫拦下。
2. **真实同名写入**：在本次 run 目录里对同名文件再落一次盘（走 ``_env.save_evidence``），
   要求：原件字节与哈希**都不变**，且新内容落到 ``<name>.<run_id>.<ext>``。

用法（仓库根目录）：:

    set HARNESS_RUN_ID=w0-e01-A
    F:\\Miniconda\\envs\\wage\\python.exe -B test-reports-2026-10/harness/w0_guard_injection.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:  # A-14
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

import _env  # noqa: E402

#: D-5 / T-01 实测被覆盖的 6 个文件（t2 原件所在：evidence/harness/ 平铺层）
D5_FILES = [
    'negative_case1_real_db_guard.txt',
    'negative_case2_fake_switch.txt',
    'negative_case3_qc_gate.txt',
    'negative_case4_fixture_scale.txt',
    'negative_case5_shipment_prerequisite.txt',
    'negative_matrix.json',
]


def main():
    lines = []
    ok_all = True

    def emit(text=''):
        lines.append(text)
        print(text)

    emit(f'[guard-injection] run_id={_env.RUN_ID}')
    emit(f'[guard-injection] 平铺原件目录（只读层）{_env.EVIDENCE_ROOT}')
    emit(f'[guard-injection] 本次落点（run 层）    {_env.EVIDENCE_DIR}')

    emit('')
    emit('== 1) 干跑：对 D-5 的 6 个平铺原件尝试「同名写入」⇒ 守卫必须给出改名路径，不动原件 ==')
    dry_ok = True
    for name in D5_FILES:
        original = os.path.join(_env.EVIDENCE_ROOT, name)
        before_sha = _env.sha256_file(original) if os.path.exists(original) else None
        target, renamed = _env.guard_write(original, run_id=_env.RUN_ID)   # 只问决策，不写盘
        kept = (before_sha == _env.sha256_file(original)) if before_sha else False
        good = bool(renamed) and os.path.abspath(target) != os.path.abspath(original) and kept
        dry_ok &= good
        emit(f'  [{"PASS" if good else "FAIL"}] {name}')
        emit(f'         请求写入 → 守卫实际目标 = {os.path.basename(target)}（改名={renamed}）')
        emit(f'         原件哈希 {str(before_sha)[:16]}… 干跑后不变={kept}')
    emit(f'  ⇒ 干跑结论：{"全部被改名拦下，原件不可能被同名写入命中" if dry_ok else "存在可覆盖路径（缺陷）"}')
    ok_all &= dry_ok

    emit('')
    emit('== 2) 真实同名写入（在本次 run 目录）：原件字节/哈希不变，新内容落到改名文件 ==')
    real_ok = True
    for name in D5_FILES:
        first = _env.save_evidence(name, f'FIRST run_id={_env.RUN_ID} file={name}\n')
        first_bytes = open(first, 'rb').read()
        first_sha = _env.sha256_file(first)
        second = _env.save_evidence(name, f'SECOND run_id={_env.RUN_ID} file={name}\n')
        kept = os.path.exists(first) and open(first, 'rb').read() == first_bytes
        renamed = os.path.basename(second) != os.path.basename(first)
        good = kept and renamed
        real_ok &= good
        emit(f'  [{"PASS" if good else "FAIL"}] {name}')
        emit(f'         第一次 → {os.path.basename(first)}（{first_sha[:16]}…）')
        emit(f'         第二次 → {os.path.basename(second)}（改名={renamed}，第一次内容不变={kept}）')
    emit(f'  ⇒ 同名写入结论：{"改名保留生效" if real_ok else "发生覆盖（缺陷）"}')
    ok_all &= real_ok

    emit('')
    emit(f'[guard-injection] 汇总：{"PASS" if ok_all else "FAIL"}'
         f'（干跑 {len(D5_FILES)} 项 + 同名写入 {len(D5_FILES)} 项）')
    emit(f'[guard-injection] 真实库 app.db SHA256 = {_env.sha256_file(_env.REAL_DB)}'
         f'（钉死值 {"一致" if _env.sha256_file(_env.REAL_DB) == _env.REAL_DB_SHA256_EXPECTED else "偏离！"}）')

    out = _env.save_evidence('w0_guard_injection.out.txt', '\n'.join(lines) + '\n')
    print(f'[guard-injection] 原始输出已落盘 {out}')
    return 0 if ok_all else 1


if __name__ == '__main__':
    sys.exit(main())
