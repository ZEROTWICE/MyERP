"""captain 预取证：P-01 blocker 的修复验证（不改生产代码、不改真实库）。

做法：把 app/ 复制到 .tmp 沙箱，在副本的 routes.py 模块级导入里补 Consumable /
ConsumableCategory，然后以该沙箱为 sys.path 首选项建立 Flask test client，
对两个易耗品端点做「修前 / 修后」对照。

只读约束：
  - 真实 app.db 不打开（仅 SHA256 指纹前后复核）
  - 仅写 test-reports-2026-10/.tmp/ 与 evidence/ 下的证据
"""
import hashlib
import io
import json
import os
import shutil
import sys
import time

ROOT = os.getcwd()
TMP = os.path.join("test-reports-2026-10", ".tmp", "captain-p01-verify")
EVID = os.path.join("test-reports-2026-10", "evidence", "captain-verification")
PY = r"F:\Miniconda\envs\wage\python.exe"

buf = io.StringIO()


def w(*a):
    print(*a, file=buf)


def sha256_file(p):
    with open(p, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


real_db = os.path.join(ROOT, "app.db")
before = sha256_file(real_db)
w("真实库 SHA256 开工 = %s" % before)

# ---------- 1. 沙箱副本 ----------
if os.path.isdir(TMP):
    shutil.rmtree(TMP)
os.makedirs(TMP, exist_ok=True)
shutil.copytree(os.path.join(ROOT, "app"), os.path.join(TMP, "app"))
w("沙箱副本已建：%s（app/ 复制）" % TMP)

routes_py = os.path.join(TMP, "app", "main", "routes.py")
src = open(routes_py, encoding="utf-8").read()

anchor = "from app.models import "
idx = src.index(anchor)
line_end = src.index("\n", idx)
model_line = src[idx:line_end]
w("模块级模型导入行长度 = %d 字符" % len(model_line))
w("  含 Consumable: %s / 含 ConsumableCategory: %s" % ("Consumable " in model_line or ", Consumable," in model_line,
                                                      "ConsumableCategory" in model_line))

patched = src[:line_end] + ", Consumable, ConsumableCategory" + src[line_end:]
open(routes_py, "w", encoding="utf-8").write(patched)
w("沙箱内已补导入：`, Consumable, ConsumableCategory`")

# ---------- 2. 端点可达性对照（沙箱优先） ----------
probe = r'''
import os, sys, json, io
sys.path.insert(0, os.path.join(os.getcwd(), "test-reports-2026-10", ".tmp", "captain-p01-verify"))
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(os.getcwd(), "test-reports-2026-10", ".tmp",
                                                         "captain-p01-verify", "copy.db").replace("\\", "/")
import shutil
src = os.path.join(os.getcwd(), "app.db")
dst = os.path.join(os.getcwd(), "test-reports-2026-10", ".tmp", "captain-p01-verify", "copy.db")
if not os.path.isfile(dst):
    shutil.copy2(src, dst)
out = {}
try:
    from app import create_app, db
    from app.models import Consumable
    app = create_app()
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["TESTING"] = True
    with app.app_context():
        c = Consumable.query.first()
        out["consumable_rows"] = Consumable.query.count()
        out["sample_id"] = c.id if c else None
        out["sample_qty"] = float(c.quantity) if c else None
    client = app.test_client()
    with client.session_transaction() as s:
        s["_user_id"] = "1"
    resp = client.post("/consumables/1/use", json={"usage_quantity": 1})
    out["POST_/consumables/1/use"] = {"status": resp.status_code, "body_head": resp.get_data(as_text=True)[:200]}
    out["module_has_Consumable"] = hasattr(sys.modules["app.main.routes"], "Consumable")
except Exception as exc:
    out["EXCEPTION"] = "%s: %s" % (type(exc).__name__, exc)
print("__PROBE__" + json.dumps(out, ensure_ascii=False))
'''

probe_py = os.path.join(TMP, "probe.py")
open(probe_py, "w", encoding="utf-8").write(probe)
w("")
w("沙箱 probe 已写：%s" % probe_py)
w("（实际运行在本脚本外部以隔离解释器，见 evidence 输出的 run 段）")

# ---------- 3. 收尾 ----------
after = sha256_file(real_db)
w("真实库 SHA256 收尾 = %s" % after)
w("真实库未变 = %s" % (before == after))

os.makedirs(EVID, exist_ok=True)
stamp = time.strftime("%Y%m%d-%H%M%S")
txt = os.path.join(EVID, "p01-sandbox-prep-%s.txt" % stamp)
open(txt, "w", encoding="utf-8").write(buf.getvalue())
print(buf.getvalue())
print("written ->", txt)
