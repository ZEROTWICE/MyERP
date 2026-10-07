# -*- coding: utf-8 -*-
"""只读探针 C：模型类与表的口径对拍（AST vs SQLAlchemy metadata vs 副本库）。"""
import ast
import collections
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

# --- AST 侧：无导入，纯静态 ---
ast_classes = []
for p in sorted((ROOT / 'app').rglob('*.py')):
    if '__pycache__' in str(p):
        continue
    try:
        tree = ast.parse(p.read_text(encoding='utf-8', errors='replace'))
    except SyntaxError as e:
        print(f'PARSE-FAIL {p.as_posix()}: {e}')
        continue
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            bases = [getattr(b, 'id', getattr(b, 'attr', '')) for b in node.bases]
            tn = None
            for st in node.body:
                if isinstance(st, ast.Assign) and any(getattr(t, 'id', '') == '__tablename__' for t in st.targets):
                    try:
                        tn = ast.literal_eval(st.value)
                    except Exception:  # noqa: BLE001
                        tn = '<non-literal>'
            ast_classes.append((p.relative_to(ROOT).as_posix(), node.name, bases, tn, node.lineno))

with_tn = [c for c in ast_classes if c[3]]
print(f'AST: 全部 ClassDef = {len(ast_classes)}')
print(f'AST: 声明 __tablename__ 的类 = {len(with_tn)}（去重表名 = {len({c[3] for c in with_tn})}）')
print(f'AST: 含 db.Model 基类 = {len([c for c in ast_classes if any("Model" in b for b in c[2])])}')
print('AST: 含 Model 基类但无 __tablename__ 的类:')
for c in ast_classes:
    if any('Model' in b for b in c[2]) and not c[3]:
        print(f'   {c[0]}:{c[4]} {c[1]} bases={c[2]}')

# --- SQLAlchemy metadata 侧 ---
from _test_bootstrap import make_app  # noqa: E402

app, _ = make_app()
from app import db  # noqa: E402
from app import models  # noqa: E402,F401

md_tables = sorted(db.metadata.tables)
print(f'\nSA metadata 表数 = {len(md_tables)}')
from app.models import (  # noqa: E402
    AuditLog, BonusPenalty, CodeGenerationLog, CodeRule, Consumable, ConsumableCategory,
    Customer, CustomerAddress, Employee, Equipment, FinishedProduct, InspectionRecord,
    InspectionTask, InspectionTemplate, NonconformityRecord, Notification, ProcessPrice,
    Product, ProductBOM, ProductionBatch, ProductionBatchItem, ProductionOrder,
    ProductionRecord, PurchaseOrder, RawMaterial, SalesOrder, SalesOrderItem, SerialNumber,
    Shipment, Supplier, SystemConfig, TaskAssignment, User, Workpiece,
)
print('抽查 34 个模型类可导入 OK')

with app.app_context():
    insp = db.inspect(db.engine)
    db_tables = sorted(insp.get_table_names())
print(f'副本库表数 = {len(db_tables)}')
print(f'metadata - db = {sorted(set(md_tables) - set(db_tables))}')
print(f'db - metadata = {sorted(set(db_tables) - set(md_tables))}')
