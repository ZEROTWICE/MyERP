"""B0 前置探针（t1 / V-00）：锚点再冻结 + 生产面 tree 复核 + 真库开工复核。

严格只读：不写任何生产文件、不动 evidence/** 原件；只
  1) 计算 7 个回归锚点的 字节 + SHA256（大写）；
  2) 复核 `git rev-parse HEAD:app` == 冻结值 `c8f7d4ab…`（HEAD 只是测量时点，不作基线）；
  3) 复核真实库 `app.db` SHA256 == 钉值 `F5DA2306…0E0F065`（开工 + 收尾各一次）；
  4) 把读数经 `_env.save_evidence` 落 `evidence/harness/<RUN_ID>/`（绝不覆盖），
     并把同一份 JSON 另写 `.tmp/<RUN_ID>/` 供后续批次直接引用。

用法（仓库根）：
  $env:HARNESS_RUN_ID='r2-exec-b0'
  python -B test-reports-2026-10/harness/r2_b0_anchor_freeze.py

退出码：0 = 三项全部相符；1 = 任一不符（逐项打印差异）。
"""
import json
import os
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import _env  # noqa: E402

REPO_ROOT = _env.REPO_ROOT

APP_TREE_EXPECTED = 'c8f7d4abca1567b6219dbd77f22c82722f877ad6'

# (锚点名, 仓库相对路径, 期望字节, 期望 SHA256 大写)  —— 29-第2轮事实底盘.md §4
ANCHORS = [
    ('UAT 40 链', 'test-reports-2026-10/evidence/uat/uat_chains.json',
     33318, '360A8570BC0080A2984A59AD945B2C837AD96ACF7B55E6242AE7E2C6417DD23A'),
    ('阴性矩阵 28', 'test-reports-2026-10/evidence/harness/negative_matrix.json',
     24424, 'B743C73F86F5EB5C0FBA38410119D8D3A6BDE5FBACDF214CFA0DB409EF5B7479'),
    ('断言账本 122', 'test-reports-2026-10/evidence/analysis/assertion_ledger.json',
     60937, 'C7C312734DD8E02486D26C3639D8D074CCFCD59BCEB002C13C7CC9587AC94092'),
    ('写断言套件 54', 'test-reports-2026-10/evidence/api/write_suite.json',
     73293, 'B608117EBDCA2A6F74595F0DB4A010187D8834715CD5E70D5C1AAD85F4A3F403'),
    ('覆盖量测', 'test-reports-2026-10/evidence/harness/coverage.json',
     236893, '5E2C9D4315971B31C83AFD7833C310501199C34F61BFD868EF07A6AEEF7BF1F0'),
    ('API 全量矩阵', 'test-reports-2026-10/evidence/api/api_matrix.json',
     1342834, '8451BB6738CCB25C41794E7B9548969D0EDDC8FE6EAE855DCC5F1D1CC746CB86'),
    ('阶段A 收口读数', 'test-reports-2026-10/26-阶段A收口-复核读数.json',
     11994, 'CF0E2B14581D82072E087617B0CE3DBC1F4676897787DB6B14D6C6FA43D37319'),
]


def git(*args):
    p = subprocess.run(['git'] + list(args), cwd=REPO_ROOT,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return p.returncode, p.stdout.decode('utf-8', 'replace').strip()


def main():
    ts = time.strftime('%Y-%m-%d %H:%M:%S')
    rid = _env.RUN_ID
    print('=== B0 前置（锚点再冻结 + HEAD:app + 真实库）===')
    print('run_id   = %s' % rid)
    print('时点     = %s' % ts)
    print('python   = %s   %s' % (sys.executable, sys.version.split()[0]))
    print()

    # --- 真库开工读数 -------------------------------------------------
    db_before = _env.real_db_status()
    print('[0-c 开工] app.db = %d B / %s' % (db_before['bytes'], db_before['sha256']))
    print('           期望     = %s' % _env.REAL_DB_SHA256_EXPECTED)

    # --- 生产面 tree --------------------------------------------------
    rc_head, head = git('rev-parse', 'HEAD')
    rc_tree, tree = git('rev-parse', 'HEAD:app')
    rc_diff, diff_out = git('diff', '--stat', '--', 'app')
    print()
    print('[0-a] HEAD          = %s   (rc=%d；测量时点，非基线)' % (head, rc_head))
    print('[0-a] HEAD:app tree = %s   (rc=%d)' % (tree, rc_tree))
    print('[0-a] 期望（t1 冻结）= %s' % APP_TREE_EXPECTED)
    print('[0-a] git diff --stat -- app = %r' % (diff_out,))
    tree_ok = (tree.lower() == APP_TREE_EXPECTED.lower())

    # --- 7 个锚点 -----------------------------------------------------
    print()
    rows = []
    anchor_ok = True
    for name, rel, exp_bytes, exp_sha in ANCHORS:
        ap = os.path.join(REPO_ROOT, rel)
        exists = os.path.isfile(ap)
        got_bytes = os.path.getsize(ap) if exists else None
        got_sha = _env.sha256_file(ap) if exists else None
        ok = bool(exists and got_bytes == exp_bytes
                  and got_sha.lower() == exp_sha.lower())
        anchor_ok = anchor_ok and ok
        rows.append({'anchor': name, 'path': rel.replace('\\', '/'),
                     'exists': exists, 'bytes': got_bytes, 'sha256': got_sha,
                     'expected_bytes': exp_bytes, 'expected_sha256': exp_sha,
                     'match': ok,
                     'bytes_match': got_bytes == exp_bytes,
                     'sha256_match': (got_sha or '').lower() == exp_sha.lower()})
        print('[0-a] %-14s %s  %s B (期望 %s)  %s'
              % (name, 'OK ' if ok else 'MISMATCH', got_bytes, exp_bytes, got_sha))

    # --- 真库收尾读数 -------------------------------------------------
    try:
        db_after_sha = _env.assert_real_db_untouched('收尾')
    except RuntimeError as e:
        db_after_sha = 'DEVIATED: %s' % e
    db_after = _env.real_db_status()
    print()
    print('[0-c 收尾] app.db = %d B / %s' % (db_after['bytes'], db_after['sha256']))
    db_ok = (db_before['sha256'].lower() == _env.REAL_DB_SHA256_EXPECTED.lower()
             and db_after['sha256'].lower() == _env.REAL_DB_SHA256_EXPECTED.lower())

    all_ok = bool(tree_ok and anchor_ok and db_ok)
    print()
    print('=== 判定 ===')
    print('  0-a HEAD:app 冻结恒等      = %s' % ('OK' if tree_ok else 'FAIL'))
    print('  0-a 7 锚点全部逐位相符     = %s' % ('OK' if anchor_ok else 'FAIL'))
    print('  0-c 真实库钉值（开工+收尾）= %s' % ('OK' if db_ok else 'FAIL'))
    print('  RESULT = %s' % ('OK' if all_ok else 'VIOLATION'))

    doc = {
        'probe': 'r2_b0_anchor_freeze',
        'run_id': rid,
        'time_local': ts,
        'python': sys.executable,
        'python_version': sys.version.split()[0],
        'anchors': rows,
        'app_tree': {'head': head, 'head_app_tree': tree,
                     'expected': APP_TREE_EXPECTED, 'match': tree_ok,
                     'git_diff_stat_app': diff_out},
        'real_db': {'path': db_before['path'],
                    'before': {'bytes': db_before['bytes'], 'sha256': db_before['sha256'],
                               'mtime_ns': db_before['mtime_ns']},
                    'after': {'bytes': db_after['bytes'], 'sha256': db_after['sha256'],
                              'mtime_ns': db_after['mtime_ns']},
                    'pinned': _env.REAL_DB_SHA256_EXPECTED,
                    'match': db_ok,
                    'assert_real_db_untouched_after': db_after_sha},
        'verdict': 'OK' if all_ok else 'VIOLATION',
        'rule': '哈希一律大写十六进制；比对大小写不敏感（28 §5-5 / A-51）',
    }
    text = json.dumps(doc, ensure_ascii=False, indent=2)

    saved = _env.save_evidence('b0-anchor-freeze.json', text)
    tmp_path = os.path.join(_env.tmp_dir('ledger'), 'b0-anchor-freeze.json')
    with open(tmp_path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(text)
    print('落盘（save_evidence）：%s' % saved)
    print('落盘（本 run 临时副本）：%s' % tmp_path)
    return 0 if all_ok else 1


if __name__ == '__main__':
    sys.exit(main())
