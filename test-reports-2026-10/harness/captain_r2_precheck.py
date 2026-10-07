import io
import json
import os
import sys

p = os.path.join("test-reports-2026-10", "evidence", "harness", "r2t1-reconcile", "r2-38item-reconcile.json")
d = json.load(open(p, encoding="utf-8"))
buf = io.StringIO()


def w(*a):
    print(*a, file=buf)


w("=== 顶层键 ===")
w(str(list(d.keys())))
w("")
# 找条目列表
items = None
for k, v in d.items():
    if isinstance(v, list) and v and isinstance(v[0], dict) and any(
            x in v[0] for x in ("id", "待办", "wave", "搜索域", "search_domain", "domain")):
        items = v
        w("条目列表键 = %r，条数 = %d" % (k, len(v)))
        break
if items is None:
    for k, v in d.items():
        if isinstance(v, list):
            w("候选列表 %r: len=%d；首元素类型=%s" % (k, len(v), type(v[0]).__name__ if v else "-"))
    # 打印结构摘要
    for k, v in d.items():
        if isinstance(v, (dict, list)):
            w("  %s: %s len=%s" % (k, type(v).__name__, len(v)))
        else:
            w("  %s = %r" % (k, str(v)[:80]))
else:
    w("")
    w("=== 首条样例（判断是否含搜索域）===")
    w(json.dumps(items[0], ensure_ascii=False, indent=1)[:1200])
    w("")
    # 统计搜索域字段覆盖
    dom_keys = [k for k in items[0].keys() if any(t in str(k).lower() for t in ("domain", "搜索", "scope", "域"))]
    w("搜索域相关键: %s" % dom_keys)
    if dom_keys:
        dk = dom_keys[0]
        have = sum(1 for it in items if it.get(dk))
        w("含搜索域的条目: %d / %d" % (have, len(items)))
    w("")
    w("=== 逐条 ID / 结论 / 搜索域 ===")
    concl = [k for k in items[0].keys() if any(t in str(k).lower() for t in ("concl", "结论", "status", "verdict", "result"))]
    ck = concl[0] if concl else None
    for it in items:
        w("  %-8s %-10s %s" % (it.get("id"), str(it.get(ck))[:18] if ck else "-",
                               str(it.get(dom_keys[0]))[:56] if dom_keys else "(无搜索域)"))

out = buf.getvalue()
o = os.path.join("test-reports-2026-10", "evidence", "captain-verification", "r2-t1-precheck.txt")
open(o, "w", encoding="utf-8").write(out)
print(out[:6000])
print("...written ->", o)
