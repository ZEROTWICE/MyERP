"""captain 独立核验：第一轮改进报告 38 条待办的真实状态。

只读：不 import 应用、不建库连接、不写任何被测文件。
判据：对每条待办取一个「代码中可检索的特征标记」，看它是否已落地。
"""
import io
import json
import os
import re
import subprocess
import sys

ROOT = os.getcwd()
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

out = io.StringIO()


def w(*a):
    print(*a, file=out)


def read(p):
    try:
        return open(p, encoding="utf-8").read()
    except OSError:
        return ""


ROUTES = read(os.path.join("app", "main", "routes.py"))
MES = read(os.path.join("app", "services", "mes_service.py"))
QUAL = read(os.path.join("app", "main", "quality.py"))
INIT = read(os.path.join("app", "__init__.py"))
MODELS = read(os.path.join("app", "models.py"))
STOCK = read(os.path.join("app", "main", "stock.py"))

# 每条：(待办ID, 波次, 判据描述, 已落地的特征标记（任一命中即视为已修）)
CHECKS = [
    ("E-01", "W0", "证据只追加（run_id 分目录 + 守卫）", ["guard_write", "EVIDENCE_ROOT"]),
    ("E-02", "W0", "run_gates 出口含 probe_unexpected", ["probe_unexpected"]),
    ("E-03", "W0", "permission_matrix 有失败出口", ["anon_open"]),
    ("E-04", "W0", "门禁进 CI", ["ci_gates"]),
    ("E-05", "W0", "环境三件套固化", ["reconfigure"]),
    ("P-01", "W1", "Consumable 模块级导入", ["Consumable"]),
    ("P-03", "W2", "quality_status 回写（recompute）", ["recompute_production_quality_status"]),
    ("P-07", "W2", "门禁顺序改判", ["pending"]),
    ("P-02", "W2", "production_record 分支", ["apply_production_record_result"]),
    ("P-04", "W3", "计件开关真读取", ["rework_counts_piecework"]),
    ("P-05", "W3", "返工件数优先级", ["rework_quantity"]),
    ("P-06", "W3", "逐料扣减", ["ProductionRecordMaterial"]),
    ("P-09", "W4", "_reraise_http 透传", ["_reraise_http"]),
    ("P-12", "W4", "4xx 语义校验", ["HttpException", "errorhandler"]),
    ("P-11", "W4", "正文脱敏", ["logger"]),
    ("P-10", "W4", "拒删守卫", ["存在关联", "不可删除", "拒删"]),
    ("P-08", "W5", "notes 真写", ["task.notes = data.get('notes'"]),
    ("P-13", "W5", "载体登记册", ["carrier", "载体"]),
]
# W6/W7 特征（应「未做」）
W67 = [
    ("C-01", "W6", "J 域通知审计断言", []),
    ("C-02", "W6", "并发/事务资产", []),
    ("C-03", "W6", "CSRF 全场景", []),
    ("C-04", "W6", "链级未覆盖补齐", []),
    ("C-05", "W6", "写端点命中补强", []),
    ("C-06", "W6", "四模块双层盲区", []),
    ("C-07", "W6", "应用级真实库硬闸", []),
    ("C-08", "W6", "导入容错/导出残留", []),
    ("C-09", "W6", "工价版本取值", []),
    ("C-10", "W6", "夹具幂等记账", []),
    ("C-11", "W6", "不可判定项补用例", []),
    ("TL-01", "W7", "check_model_refs 进链", ["check_model_refs"]),
    ("TL-02", "W7", "check_http_contract", ["check_http_contract", "w4_http_contract"]),
    ("TL-03", "W7", "coverage_drift 进链", ["coverage_drift"]),
    ("TL-04", "W7", "evidence_hash 门禁", ["evidence_hash"]),
    ("TL-05", "W7", "check_properties 扩展", []),
    ("TL-06", "W7", "口径守卫", []),
    ("TL-07", "W7", "依赖可复现钉版", []),
]

ALL_SRC = ROUTES + MES + QUAL + INIT + MODELS + STOCK
HARNESS_DIR = os.path.join("test-reports-2026-10", "harness")
SCRIPTS_DIR = "scripts"
HARNESS_FILES = set(os.listdir(HARNESS_DIR)) if os.path.isdir(HARNESS_DIR) else set()
SCRIPT_FILES = set(os.listdir(SCRIPTS_DIR)) if os.path.isdir(SCRIPTS_DIR) else set()

w("=== 阶段A 声称已修的 18 项（W0-W5）特征核验 ===")
w("%-7s %-4s %-42s %s" % ("ID", "波次", "待办", "特征命中"))
done = notdone = 0
for tid, wave, desc, marks in CHECKS:
    hit = [m for m in marks if m in ALL_SRC or m in " ".join(HARNESS_FILES) or m in " ".join(SCRIPT_FILES)]
    ok = bool(hit)
    done += ok
    notdone += (not ok)
    w("%-7s %-4s %-42s %s" % (tid, wave, desc[:40], ("OK " + str(hit[:1])) if ok else "**未命中**"))
w("  命中 %d / 未命中 %d" % (done, notdone))

w("")
w("=== W6/W7 剩余项（预期多数未做）===")
w("%-7s %-4s %-42s %s" % ("ID", "波次", "待办", "特征命中"))
for tid, wave, desc, marks in W67:
    hit = [m for m in marks if m in " ".join(SCRIPTS_DIR and SCRIPT_FILES) or m in " ".join(HARNESS_FILES)]
    w("%-7s %-4s %-42s %s" % (tid, wave, desc[:40], ("已在库 " + str(hit)) if hit else "未做"))

w("")
w("=== 关键产物是否在库（提交后应存在）===")
for p in ("scripts/check_model_refs.py", "test-reports-2026-10/harness/ci_gates.py",
          "test-reports-2026-10/harness/coverage_drift.py", "test-reports-2026-10/harness/evidence_hash.py",
          "test-reports-2026-10/harness/regression_preflight.py", "test-reports-2026-10/07-测试与工程改进报告.md",
          "test-reports-2026-10/26-阶段A收口报告.md", "test-reports-2026-10/26-修复后回归与断言账本.md"):
    w("  %-58s %s" % (p, "在" if os.path.isfile(p) else "缺失"))

res = subprocess.run(["git", "log", "--oneline", "-1"], capture_output=True, text=True, encoding="utf-8")
w("")
w("=== git HEAD ===")
w("  " + (res.stdout or "").strip())

os.makedirs(os.path.join("test-reports-2026-10", "evidence", "captain-verification"), exist_ok=True)
p = os.path.join("test-reports-2026-10", "evidence", "captain-verification", "r2-38item-status.txt")
open(p, "w", encoding="utf-8").write(out.getvalue())
print("written ->", p)
