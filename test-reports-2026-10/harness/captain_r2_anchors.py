"""captain：独立计算第2轮回归基线锚点（供与 t1 的冻结值交叉核对）。只读。"""
import hashlib
import io
import json
import os

ANCHORS = [
    ("UAT 回归基线", "test-reports-2026-10/evidence/uat/uat_chains.json"),
    ("阴性矩阵", "test-reports-2026-10/evidence/harness/negative_matrix.json"),
    ("断言账本（122 条）", "test-reports-2026-10/evidence/analysis/assertion_ledger.json"),
    ("写断言套件（54 条）", "test-reports-2026-10/evidence/api/write_suite.json"),
    ("覆盖量测", "test-reports-2026-10/evidence/harness/coverage.json"),
    ("API 全量矩阵", "test-reports-2026-10/evidence/api/api_matrix.json"),
    ("阶段A 收口复核读数", "test-reports-2026-10/26-阶段A收口-复核读数.json"),
    ("前后对照（t9 账本）", "test-reports-2026-10/evidence/harness/t9-rega-final/ledger.json"),
]
EXTRA = [
    "test-reports-2026-10/evidence/harness/t9-rega-final/",
    "test-reports-2026-10/evidence/harness/w2w3-uatdiff-final/",
]

buf = io.StringIO()


def w(*a):
    print(*a, file=buf)


w("# 第2轮回归基线锚点（captain 独立计算，HEAD e3c6269）")
w("")


def sha(p):
    with open(p, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest().upper()


w("| 锚点 | 路径 | 字节 | SHA256 |")
w("| --- | --- | --- | --- |")
found = 0
for label, p in ANCHORS:
    if os.path.isfile(p):
        found += 1
        h = sha(p)
        n = hashlib.sha256(open(p, "rb").read()).hexdigest()
        w("| %s | `%s` | %d | `%s` |" % (label, p, os.path.getsize(p), h))
        # 大小写不敏感自证（A-51 教训）
        assert h == n.upper(), "大小写逻辑错误"
    else:
        w("| %s | `%s` | — | **缺失** |" % (label, p))
w("")
w("命中 %d / %d" % (found, len(ANCHORS)))
w("")
w("## 目录级锚点（如以目录为基准，需整目录指纹）")
for d in EXTRA:
    if os.path.isdir(d):
        files = sorted(f for f in os.listdir(d) if os.path.isfile(os.path.join(d, f)))
        tot = sum(os.path.getsize(os.path.join(d, f)) for f in files)
        w("- `%s`：%d 文件 / %d 字节" % (d, len(files), tot))
        for f in files[:6]:
            w("  - `%s` %d B `%s`" % (f, os.path.getsize(os.path.join(d, f)), sha(os.path.join(d, f))[:16]))
    else:
        w("- `%s`：不存在" % d)
w("")
w("## 口径说明（A-23/A-51）")
w("- 哈希一律**大写十六进制**（与 `evidence_hash.py` 的 `.upper()` 一致）；比对时**大小写不敏感**。")
w("- 本表为 captain 在 t1 交付**之前**计算的独立读数，用于交叉核对 t1 的冻结值；若两者不一致，须查清是**文件已变**还是**口径不同**。")

o = os.path.join("test-reports-2026-10", "evidence", "captain-verification", "r2-baseline-anchors.md")
os.makedirs(os.path.dirname(o), exist_ok=True)
open(o, "w", encoding="utf-8").write(buf.getvalue())
print(buf.getvalue())
print("written ->", o)
