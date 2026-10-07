"""captain：提取 fix_plan.json 中 W6/W7 剩余项的精确定义（供 t2/t3/t5 使用）。只读。"""
import io
import json
import os

p = os.path.join("test-reports-2026-10", "evidence", "improve", "fix_plan.json")
d = json.load(open(p, encoding="utf-8"))
out = io.StringIO()


def w(*a):
    print(*a, file=out)


w("# 第2轮靶子：W6 / W7 剩余项的精确定义（captain 提取，供 t2/t3/t5）")
w("")
w("来源：`test-reports-2026-10/evidence/improve/fix_plan.json`（第一轮改进报告的机读清单）")
w("说明：以下为 `07` 原始定义的**原文摘录**，未经改写；captain 标注的「已完成」以阶段A 提交（HEAD 7e0a995）为准。")
w("")
w("## 波次定义")
for wv in d.get("waves", []):
    w("- **%s** %s ｜ 出厂条件：%s" % (wv.get("id"), wv.get("name"), wv.get("gate")))
w("")
w("## W6 剩余项（覆盖补强，11 条）")
w("")
for it in d.get("items", []):
    if it.get("wave") != "W6":
        continue
    w("### %s ｜ %s ｜ %s" % (it.get("id"), it.get("level"), it.get("title")))
    if it.get("problem_ref"):
        w("- 关联问题：%s" % ", ".join(str(x) for x in it["problem_ref"]))
    w("- **修复动作**：")
    for a in it.get("fix_action", []):
        w("  - %s" % a)
    w("- **可验证判据**：%s" % it.get("verify_judge", "—"))
    w("- 工作量：%s ｜ 依赖：%s" % (it.get("effort"), it.get("deps")))
    if it.get("regression"):
        w("- 回归方式：%s" % it["regression"])
    w("")
w("## W7 剩余项（工具链，7 条，标注阶段A 状态）")
w("")
for it in d.get("items", []):
    if it.get("wave") != "W7":
        continue
    mark = {
        "TL-01": "阶段A 已交付 `scripts/check_model_refs.py`，**未进 CI 链**（`ci_gates.py:109` 预留位）",
        "TL-02": "阶段A 已交付 `harness/w4_http_contract.py`（t8 的 P-09 判据），**未作为独立门禁进链**",
        "TL-03": "阶段A 已交付 `harness/coverage_drift.py`，**已进 blocking 集**",
        "TL-04": "阶段A 已交付 `harness/evidence_hash.py`，**未进 CI 链**",
        "TL-05": "未做",
        "TL-06": "未做",
        "TL-07": "未做",
    }.get(it.get("id"), "")
    w("### %s ｜ %s ｜ %s" % (it.get("id"), it.get("level"), it.get("title")))
    w("- **阶段A 状态**：%s" % mark)
    if it.get("problem_ref"):
        w("- 关联问题：%s" % ", ".join(str(x) for x in it["problem_ref"]))
    w("- **修复动作**：")
    for a in it.get("fix_action", []):
        w("  - %s" % a)
    w("- **可验证判据**：%s" % it.get("verify_judge", "—"))
    w("- 工作量：%s ｜ 依赖：%s" % (it.get("effort"), it.get("deps")))
    w("")
w("## 门禁判据（`gates`，共 %d 条，第2轮需复核是否已模板化）" % len(d.get("gates", [])))
w("")
for g in d.get("gates", []):
    w("- **%s** ｜ 判据：%s" % (g.get("id"), g.get("judge")))
    w("  - 实现：%s" % g.get("impl"))
    w("  - 期望失败形态：%s" % g.get("expected_fail"))
    w("  - 当前：%s" % g.get("current"))
w("")
w("## non_goals（第2轮仍适用）")
for n in d.get("non_goals", []):
    w("- %s" % n)

os.makedirs(os.path.join("test-reports-2026-10", "evidence", "captain-verification"), exist_ok=True)
o = os.path.join("test-reports-2026-10", "evidence", "captain-verification", "r2-w6w7-targets.md")
open(o, "w", encoding="utf-8").write(out.getvalue())
print("written ->", o, len(out.getvalue()), "chars")
