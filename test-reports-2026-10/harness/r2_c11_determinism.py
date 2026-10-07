"""r2_c11_determinism.py — V-08 产物的**语义确定性**复核（`40` §4.2 `reproducible` 判据）。

背景：`assertion_ledger.c11.json` 内嵌 `provenance.generated_at` 与 `ledger_delta` 的时间戳字段，
**逐字节哈希必然随两次运行变化**。`reproducible` 的正确口径是「同 run 同命令再跑一次能否得到同一
`observed`」⇒ 必须比对**语义字段**，不是整文件哈希。

比对方式：对两份产物（A = 已落盘件，B = 本 run 重算件）逐字段做规范化 JSON 比对，
排除 `provenance.generated_at` / `provenance.run_id` 等时间戳字段。

用法（仓库根）：

    F:\\Miniconda\\envs\\wage\\python.exe -B test-reports-2026-10/harness/r2_c11_determinism.py

退出码：0 = 语义逐位相同；1 = 有语义差异（逐条打印路径）。
"""
import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import _env  # noqa: E402

REPO_ROOT = _env.REPO_ROOT
RUN = _env.RUN_ID
SHIPPED = os.path.join(REPO_ROOT, 'test-reports-2026-10', 'evidence', 'harness', RUN,
                       'assertion_ledger.c11.json')
RECOMPUTED = os.path.join(_env.tmp_dir('ledger'), 'assertion_ledger.c11.json')

VOLATILE = ('provenance.generated_at', 'provenance.run_id')


def canon(obj, path=''):
    """规范化：排除时间戳字段。"""
    if isinstance(obj, dict):
        return {k: canon(v, '%s.%s' % (path, k)) for k, v in sorted(obj.items())
                if ('%s.%s' % (path, k)).lstrip('.') not in VOLATILE}
    if isinstance(obj, list):
        return [canon(v, '%s[%d]' % (path, i)) for i, v in enumerate(obj)]
    return obj


def main():
    if not (os.path.isfile(SHIPPED) and os.path.isfile(RECOMPUTED)):
        print('缺件：shipped=%s recomputed=%s' % (os.path.isfile(SHIPPED), os.path.isfile(RECOMPUTED)))
        return 2
    a = json.load(open(SHIPPED, encoding='utf-8'))
    b = json.load(open(RECOMPUTED, encoding='utf-8'))
    ca, cb = canon(a), canon(b)

    print('=== r2_c11_determinism（语义确定性）===')
    print('A（已落盘）= %s' % os.path.relpath(SHIPPED, REPO_ROOT).replace('\\', '/'))
    print('B（本 run 重算）= %s' % os.path.relpath(RECOMPUTED, REPO_ROOT).replace('\\', '/'))
    print('排除的易变字段 = %s' % (VOLATILE,))
    print()
    print('A 字节/SHA256 = %d / %s' % (os.path.getsize(SHIPPED), _env.sha256_file(SHIPPED)))
    print('B 字节/SHA256 = %d / %s' % (os.path.getsize(RECOMPUTED), _env.sha256_file(RECOMPUTED)))
    print('（整文件哈希不同属预期：内嵌 generated_at 时间戳）')
    print()

    diffs = []
    if ca != cb:
        # 逐路径定位差异
        def walk(x, y, path=''):
            if type(x) is not type(y):
                diffs.append('%s: 类型 %s vs %s' % (path, type(x).__name__, type(y).__name__))
                return
            if isinstance(x, dict):
                for k in sorted(set(x) | set(y)):
                    if k not in x or k not in y:
                        diffs.append('%s.%s: 仅在单侧' % (path, k))
                    else:
                        walk(x[k], y[k], '%s.%s' % (path, k))
            elif isinstance(x, list):
                if len(x) != len(y):
                    diffs.append('%s: 长度 %d vs %d' % (path, len(x), len(y)))
                for i, (u, v) in enumerate(zip(x, y)):
                    walk(u, v, '%s[%d]' % (path, i))
            elif x != y:
                diffs.append('%s: %r vs %r' % (path, x, y))
        walk(ca, cb)

    keys = ('totals', 'ledger_delta.before', 'ledger_delta.after', 'ledger_delta.delta')
    print('--- 关键读数（两侧）---')
    for k in keys:
        head, _, tail = k.partition('.')
        va = a.get(head) if not tail else (a.get(head) or {}).get(tail)
        vb = b.get(head) if not tail else (b.get(head) or {}).get(tail)
        st = 'SAME' if va == vb else 'DIFF'
        print('  %-22s A=%s  B=%s  %s' % (k, va, vb, st))
    ids_a = [e['ac_id'] for e in a['entries'] if str(e.get('suite')) == 'c11']
    ids_b = [e['ac_id'] for e in b['entries'] if str(e.get('suite')) == 'c11']
    print('  %-22s A=%s' % ('c11 ac_ids', ids_a))
    print('  %-22s B=%s' % ('c11 ac_ids', ids_b))
    print()
    for d in diffs[:20]:
        print('  [DIFF] %s' % d)
    if len(diffs) > 20:
        print('  ... 另有 %d 处' % (len(diffs) - 20))
    verdict = 'OK（语义逐位相同）' if not diffs else 'VIOLATION（%d 处语义差异）' % len(diffs)
    print('判定 = %s' % verdict)
    return 0 if not diffs else 1


if __name__ == '__main__':
    sys.exit(main())
