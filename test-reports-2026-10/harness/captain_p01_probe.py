"""captain 预取证：P-01 的「缺名 ⇒ NameError」与「补名 ⇒ 正常」对照（不改任何文件）。

原理：`use_consumable` / `delete_consumable` 的函数体引用全局名 `Consumable`。
 - 未注入：模块 globals 无该名 ⇒ NameError（= 线上 500）
 - 注入 `Consumable`（等价于补模块级 import）⇒ 正常走到 get_or_404 / 业务逻辑
全程只读真实 app.db（仅复制副本），不修改任何生产文件。
"""
import json
import os
import shutil
import sys

ROOT = os.getcwd()
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
TMP = os.path.join(ROOT, "test-reports-2026-10", ".tmp", "captain-p01-ns")
os.makedirs(TMP, exist_ok=True)
COPY_DB = os.path.join(TMP, "copy.db")
if not os.path.isfile(COPY_DB):
    shutil.copy2(os.path.join(ROOT, "app.db"), COPY_DB)
os.environ["DATABASE_URL"] = "sqlite:///" + COPY_DB.replace("\\", "/")

out = {}
from app import create_app, db
from app.models import Consumable, ConsumableCategory
import app.main.routes as R

out["routes_file"] = R.__file__
out["module_has_Consumable_before"] = hasattr(R, "Consumable")

application = create_app()
application.config["WTF_CSRF_ENABLED"] = False
application.config["TESTING"] = True

with application.app_context():
    c = Consumable.query.first()
    if c is None:
        from datetime import datetime as _dt
        c = Consumable(quantity=10.0, status="in_stock", supplier="captain-probe",
                       category_id=1, supplier_number="PN-1",
                       storage_date=_dt.now(), unit="pcs")
        db.session.add(c)
        db.session.commit()
    cid = c.id
    out["consumable_id"] = cid
    out["qty_before"] = float(c.quantity)
    out["rows"] = Consumable.query.count()

client = application.test_client()
with client.session_transaction() as sess:
    sess["_user_id"] = "1"

# ---- A. 未注入：应 NameError ----
out["A_without_name"] = {}
try:
    resp = client.post("/consumables/%d/use" % cid, json={"usage_quantity": 1})
    out["A_without_name"] = {"status": resp.status_code, "body_head": resp.get_data(as_text=True)[:120]}
except NameError as exc:
    out["A_without_name"] = {"raised": "NameError", "detail": str(exc)}
except Exception as exc:
    out["A_without_name"] = {"raised": type(exc).__name__, "detail": str(exc)[:120]}

# ---- B. 注入等价于补模块级 import ----
R.Consumable = Consumable
out["module_has_Consumable_after"] = hasattr(R, "Consumable")
out["B_with_name"] = {}
try:
    resp = client.post("/consumables/%d/use" % cid, json={"usage_quantity": 1})
    out["B_with_name"] = {"status": resp.status_code, "body_head": resp.get_data(as_text=True)[:160]}
except Exception as exc:
    out["B_with_name"] = {"raised": type(exc).__name__, "detail": str(exc)[:160]}

with application.app_context():
    db.session.expire_all()
    c2 = Consumable.query.get(cid)
    out["qty_after"] = float(c2.quantity) if c2 else None
    out["qty_changed"] = out["qty_after"] != out["qty_before"]

# ---- C. DELETE 同型 ----
out["C_delete"] = {}
try:
    resp = client.delete("/consumables/%d" % cid)
    out["C_delete"] = {"status": resp.status_code, "body_head": resp.get_data(as_text=True)[:160]}
except Exception as exc:
    out["C_delete"] = {"raised": type(exc).__name__, "detail": str(exc)[:160]}

print("__PROBE__" + json.dumps(out, ensure_ascii=False, indent=1))
