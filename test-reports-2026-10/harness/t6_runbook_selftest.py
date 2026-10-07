"""t6 自证探针：验证 Runbook「证据通道」契约（_env 落盘守卫 / 审计流水 / 真实库只读）。

用途：为 `40-第2轮实测Runbook与台账规范.md` §2「证据通道」与 §5「归档规范」
提供**行为级**（behavior_verified）证据，而不是「文档里写了」。

只读真实库；只写本 run 的证据目录与 `.tmp/` 隔离目录。
用法（仓库根）：

    $env:HARNESS_RUN_ID='r2t6-runbook'
    F:\Miniconda\envs\wage\python.exe -B test-reports-2026-10/harness/t6_runbook_selftest.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))          # test-reports-2026-10/harness
REPORTS_ROOT = os.path.dirname(HERE)                        # test-reports-2026-10
sys.path.insert(0, HERE)

import _env  # noqa: E402


def main():
    out = {
        'run_id': _env.RUN_ID,
        'evidence_dir': os.path.relpath(_env.evidence_dir(), _env.REPO_ROOT).replace('\\', '/'),
        'tmp_root': os.path.relpath(_env.TMP_ROOT, _env.REPO_ROOT).replace('\\', '/'),
        'interpreter': _env.interpreter(),
    }

    # ① 真实库指纹（写前）
    out['real_db_before'] = _env.real_db_status()

    # ② 同名两次落盘：第二次必须被 guard 改名保留，绝不覆盖
    p1 = _env.save_evidence('t6-guard-probe.txt', 'first write\n')
    p2 = _env.save_evidence('t6-guard-probe.txt', 'second write\n')
    out['write1'] = os.path.relpath(p1, _env.REPO_ROOT).replace('\\', '/')
    out['write2'] = os.path.relpath(p2, _env.REPO_ROOT).replace('\\', '/')
    out['write2_renamed'] = os.path.basename(p1) != os.path.basename(p2)
    out['write1_content_preserved'] = open(p1, encoding='utf-8').read() == 'first write\n'
    out['write2_content'] = open(p2, encoding='utf-8').read()

    # ③ 审计流水：每写一次追加一行（只追加，不重写）
    journal = os.path.join(os.path.dirname(p1), _env.EVIDENCE_JOURNAL_NAME)
    rows = [json.loads(l) for l in open(journal, encoding='utf-8') if l.strip()]
    out['journal_path'] = os.path.relpath(journal, _env.REPO_ROOT).replace('\\', '/')
    out['journal_lines'] = len(rows)
    out['journal_last_two'] = [
        {'written': r['written'], 'renamed_by_guard': r['renamed_by_guard'],
         'sha256_prefix': r['sha256'][:16], 'bytes': r['bytes']} for r in rows[-2:]]

    # ④ 真实库指纹（写后）——守卫函数零副作用
    out['real_db_after'] = _env.real_db_status()
    out['real_db_unchanged'] = (
        out['real_db_before']['sha256'] == out['real_db_after']['sha256']
        == _env.REAL_DB_SHA256_EXPECTED)

    # ⑤ run 隔离性：guard 只改本 run 目录内的名字，不动历史原件
    out['legacy_layer_untouched'] = not os.path.exists(
        os.path.join(_env.EVIDENCE_ROOT, 't6-guard-probe.txt'))

    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0 if (out['write2_renamed'] and out['write1_content_preserved']
                 and out['real_db_unchanged'] and out['legacy_layer_untouched']) else 1


if __name__ == '__main__':
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    sys.exit(main())
