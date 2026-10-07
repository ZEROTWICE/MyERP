"""captain：独立核验剩余 5 条 W6（C-01/C-02/C-03/C-04/C-07）。只读，排除搜索脚本。"""
import io
import os
import re
import glob

HARN = os.path.join("test-reports-2026-10", "harness")
EXCL = re.compile(r"reconcile_r2|captain_r2")
files = [f for f in glob.glob(os.path.join(HARN, "*.py")) if not EXCL.search(os.path.basename(f))]

buf = io.StringIO()


def w(*a):
    print(*a, file=buf)


def count_in(paths, pat):
    n = 0
    hits = []
    for p in paths:
        try:
            for i, l in enumerate(open(p, encoding="utf-8").read().splitlines(), 1):
                if re.search(pat, l):
                    n += 1
                    if len(hits) < 3:
                        hits.append("%s:%d" % (os.path.basename(p), i))
        except OSError:
            pass
    return n, hits


w("=== C-01 J 域通知与审计 ===")
app_files = [p for p in glob.glob("app/**/*.py", recursive=True)]
n, _ = count_in(app_files, r"AuditLog\(")
w("  app/ 中 AuditLog( 调用行数 = %d" % n)
n, hits = count_in(files, r"AuditLog|Notification")
w("  harness（排除搜索脚本）中 Audit/Notification 相关行数 = %d  %s" % (n, hits))
w("  ⇒ 若 harness 侧接近 0 ⇒ C-01 NOT_DONE")

w("")
w("=== C-02 并发与事务原子性 ===")
n, hits = count_in(files, r"threading|Thread\(|concurrent\.futures")
w("  harness 中线程/并发用例行数 = %d  %s" % (n, hits))
n2, _ = count_in(app_files, r"rollback\(\)")
w("  app/ 中 rollback() 行数 = %d（对照，说明事务面很大）" % n2)
w("  ⇒ 若 harness 侧 = 0 ⇒ C-02 NOT_DONE")

w("")
w("=== C-03 CSRF 全场景 ===")
n, hits = count_in(files, r"SameSite|csrf_token|CSRFError|csrf\.exempt")
w("  harness 中 CSRF 相关行数 = %d  %s" % (n, hits))
w("  ⚠ 注意 A-69：api_matrix 的 CSRF 判据已因 W4 统一 errorhandler 替换文案而失效")

w("")
w("=== C-04 链级未覆盖（链 A 采购链等）===")
p = os.path.join(HARN, "uat_chains.py")
if os.path.isfile(p):
    t = open(p, encoding="utf-8").read()
    w("  uat_chains.py 含 'chain_a'/'链A'/采购 相关: %s" % bool(re.search(r"chain_a|链A|purchase_requisition", t)))
    chs = sorted(set(re.findall(r"chain[_ ]?([a-zA-Z])", t)))[:12]
    w("  出现的链标识: %s" % chs)

w("")
w("=== C-07 应用级「拒绝连真实库」硬闸 ===")
n, hits = count_in(app_files, r"app\.db|拒绝连|REAL_DB|real_db")
w("  app/ 中真实库守卫相关行数 = %d  %s" % (n, hits))
gs = [f for f in glob.glob(os.path.join(HARN, "*.py")) if "guard" in os.path.basename(f) or "bootstrap" in os.path.basename(f)]
w("  harness 中守卫类脚本: %s" % [os.path.basename(x) for x in gs])
w("  ⇒ 若 app/ 侧 = 0 ⇒ C-07 的「应用级硬闸」面 NOT_DONE（脚本级守卫不计）")

o = os.path.join("test-reports-2026-10", "evidence", "captain-verification", "r2-w6-remaining.txt")
os.makedirs(os.path.dirname(o), exist_ok=True)
open(o, "w", encoding="utf-8").write(buf.getvalue())
print(buf.getvalue())
