"""captain 终审：检查 t1 最新 manifest 是否落实 A-73/A-74/A-75 三项要求。只读。"""
import io
import json
import os

CAND = [
    "test-reports-2026-10/27-38条对账与阶段A终态冻结.manifest.r2t1-reconcile4.json",
    "test-reports-2026-10/27-38条对账与阶段A终态冻结.manifest.json",
]
p = next((c for c in CAND if os.path.isfile(c)), None)
buf = io.StringIO()


def w(*a):
    print(*a, file=buf)


w("manifest = %s" % p)
d = json.load(open(p, encoding="utf-8"))
w("顶层键 = %s" % list(d.keys()))
w("")

# 1) evidence_kind / EXCLUDE
blob = json.dumps(d, ensure_ascii=False)
w("=== ① evidence_kind 是否引入 ===")
w("  文中出现 'evidence_kind': %s（%d 次）" % ("evidence_kind" in blob, blob.count("evidence_kind")))
w("=== ② EXCLUDE 列表是否给出 ===")
for k in ("EXCLUDE_BASENAMES", "exclude_basenames", "excluded", "排除"):
    if k in blob:
        w("  命中关键字 %r（%d 次）" % (k, blob.count(k)))

# 2) 找 items
items = d.get("items")
if items is None:
    for k, v in d.items():
        if isinstance(v, list) and v and isinstance(v[0], dict) and "id" in v[0]:
            items = v
            w("items 键 = %r (%d 条)" % (k, len(v)))
            break
if items:
    w("")
    w("=== ③ 六条可疑项的当前判定 ===")
    w("%-7s %-11s %-16s %s" % ("ID", "verdict", "evidence_kind", "hits 文件（前2个）"))
    for it in items:
        if it.get("id") in ("C-05", "C-06", "C-08", "C-09", "C-10", "TL-05", "C-01", "C-02", "C-07", "C-11"):
            hs = []
            for c in it.get("checks", []):
                for h in c.get("hits", []):
                    f = h.get("file") if isinstance(h, dict) else h
                    if f and f not in hs:
                        hs.append(os.path.basename(str(f)))
            w("%-7s %-11s %-16s %s" % (it.get("id"), str(it.get("verdict")),
                                       str(it.get("evidence_kind"))[:14], ", ".join(hs[:2])))
    w("")
    w("=== ④ 全 38 条 verdict 分布 ===")
    from collections import Counter
    w("  " + str(Counter(str(it.get("verdict")) for it in items)))
    w("=== ⑤ 全 38 条 evidence_kind 分布 ===")
    w("  " + str(Counter(str(it.get("evidence_kind")) for it in items)))
    w("")
    w("=== ⑥ 仍把 reconcile_r2/captain_r2 当 hits 的条目（自匹配残留）===")
    bad = []
    for it in items:
        for c in it.get("checks", []):
            for h in c.get("hits", []):
                f = str((h.get("file") if isinstance(h, dict) else h) or "")
                if "reconcile_r2" in f or "captain_r2" in f:
                    bad.append((it.get("id"), os.path.basename(f)))
    w("  残留 %d 处: %s" % (len(bad), bad[:8]))

o = "test-reports-2026-10/evidence/captain-verification/r2-t1-final-review.txt"
os.makedirs(os.path.dirname(o), exist_ok=True)
open(o, "w", encoding="utf-8").write(buf.getvalue())
print(buf.getvalue())
