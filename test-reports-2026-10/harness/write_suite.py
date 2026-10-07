"""t4 写端点安全实测套件：≥30 条**真实写断言**，每条都必须落在「数据变化」上。

设计要点（对齐 captain t4 任务书 §三.4）：

* **不看状态码判通过**：每条断言自己记录「请求前后的库内字段值」，
  ``check()`` 判的是 **库里的值**；状态码只作辅助证据。
* **副本隔离**：每个分组一条**独立的带时间戳副本**（``make_isolated_app``），
  从不与阶段其它任务共用副本；真实库 SHA256 每次建副本前后复核（``_env`` 已内建）。
  应用级「拒绝连真实库」硬闸本仓不存在（增补纪律 15），因此每建一个 app 都独立复核 URI。
* **探针对象自带唯一前缀**：``_t4_<RUN>_<n>``，便于第三人按前缀在副本里复核新增行。
* **失败归类**：``product`` / ``fixture`` / ``harness`` / ``env`` / ``undecidable``。

产出：``evidence/api/write_suite.json`` + ``write_suite.out.txt``。
"""
import json
import os
import re
import sys
import time
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _env  # noqa: E402
import fixtures  # noqa: E402
from _env import REAL_DB, assert_real_db_untouched, sha256_file  # noqa: E402

sys.path.insert(0, _env.HARNESS_DIR)
sys.path.insert(0, _env.SCRIPTS_DIR)
if _env.REPO_ROOT not in sys.path:
    sys.path.insert(0, _env.REPO_ROOT)

EVID = os.path.join(_env.REPORTS_ROOT, 'evidence', 'api')
TAG = 't4' + time.strftime('%m%d%H%M')
_LOG = []
_RESULTS = []


def log(msg=''):
    _LOG.append(str(msg))
    print(msg, flush=True)


class Ctx:
    """一次写断言的上下文：请求 + 库内前后对照。"""

    def __init__(self, app, client, group, name):
        self.app = app
        self.client = client
        self.group = group
        self.name = name
        self.checks = []
        self.before = {}
        self.after = {}
        self.resp = {}
        self.notes = []

    # -------------------------------------------------- 请求
    def req(self, method, url, **kw):
        r = self.client.open(url, method=method, **kw)
        self.resp = {'method': method, 'url': url, 'code': r.status_code,
                     'ctype': (r.headers.get('Content-Type') or '').split(';')[0],
                     'location': r.headers.get('Location', ''),
                     'body': r.get_data(as_text=True)[:300].replace('\n', ' ')}
        return r

    # -------------------------------------------------- 库内对照
    def snap(self, label, obj, fields):
        vals = {}
        for f in fields:
            try:
                v = getattr(obj, f)
            except Exception as e:
                v = f'ERR:{e.__class__.__name__}'
            if hasattr(v, 'isoformat'):
                v = v.isoformat()
            vals[f] = v
        self.before[label] = vals
        return vals

    def snap_after(self, label, obj, fields):
        vals = self.snap(label, obj, fields)   # 复用取值逻辑
        self.before.pop(label)
        self.after[label] = vals
        return vals

    def delta(self, label=None):
        out = {}
        for lab in self.after:
            if label and lab != label:
                continue
            out[lab] = {f: [self.before.get(lab, {}).get(f), self.after[lab][f]]
                        for f in self.after[lab]
                        if self.before.get(lab, {}).get(f) != self.after[lab][f]}
        return out

    def changed(self, label, field):
        b = (self.before.get(label) or {}).get(field)
        a = (self.after.get(label) or {}).get(field)
        self.checks.append({'check': f'{label}.{field} 变化', 'ok': b != a, 'before': b, 'after': a})
        return b != a

    def eq(self, check, ok, detail=None):
        self.checks.append({'check': check, 'ok': bool(ok), 'detail': detail})
        return bool(ok)

    # -------------------------------------------------- 便利
    def q(self, fn):
        with self.app.app_context():
            return fn()

    def one(self, model, **filters):
        with self.app.app_context():
            return model.query.filter_by(**filters).order_by(model.id.desc()).first()

    def by_id(self, model, pk):
        with self.app.app_context():
            return model.query.get(pk)

    def count(self, model, **filters):
        with self.app.app_context():
            if filters:
                return model.query.filter_by(**filters).count()
            return model.query.count()

    def fresh(self, model, pk):
        """脱离 session 重新取一行（避免 identity map 给出旧对象）。"""
        from app import db
        with self.app.app_context():
            db.session.expire_all()
            return model.query.get(pk)


def _audit_count(app, model_name, target_id=None):
    """审计行数（口径：target_model 精确匹配；有 target_id 时再叠加）。"""
    from app import models as M
    with app.app_context():
        q = M.AuditLog.query.filter_by(target_model=model_name)
        if target_id is not None:
            q = q.filter_by(target_id=target_id)
        return q.count()


def build_probes():
    """返回 [(group, probe_id, title, fn)]，fn(ctx, env) -> None（用 ctx.eq/changed 记断言）。"""
    from app import models as M
    P = []

    # ============================================================ T: 任务
    def t_add(c, e):
        emp, pp = e['employee'], e['process']
        r = c.req('POST', '/tasks/add', json={
            'employee_id': emp['id'], 'process_id': pp['id'], 'quantity': 7,
            'target_date': '2026-12-31', 'notes': e['tag'] + '_任务新增'})
        b = r.get_json() or {}
        c.eq('响应 success=true', b.get('success') is True, b.get('message'))
        row = c.one(M.TaskAssignment, notes=e['tag'] + '_任务新增')
        c.eq('库内出现该任务', row is not None)
        if row:
            c.snap('task', row, ['employee_id', 'process_id', 'quantity', 'status', 'target_date'])
            c.eq('quantity 落库=7', row.quantity == 7, row.quantity)
            c.eq('status 落库=pending', row.status == 'pending', row.status)
            c.eq('target_date 落库', str(row.target_date) == '2026-12-31', str(row.target_date))
            audit = _audit_count(c.app, 'TaskAssignment')
            c.eq('AuditLog 落库', audit >= 1, f'audit={audit}')

    def t_update_status(c, e):
        tid = e['seed']('task')
        r = c.req('POST', f'/tasks/{tid}/update_status',
                  json={'completed_quantity': 5, 'materials': []})
        b = r.get_json() or {}
        c.eq('响应 success=true', b.get('success') is True, b.get('message'))
        row = c.fresh(M.TaskAssignment, tid)
        c.snap_after('task', row, ['status', 'completed_quantity', 'completed_at'])
        c.changed('task', 'status')
        c.eq('status=completed', row.status == 'completed', row.status)
        c.eq('completed_quantity=5', float(row.completed_quantity or 0) == 5.0,
              row.completed_quantity)
        c.eq('completed_at 回填', row.completed_at is not None, str(row.completed_at))
        rec = c.one(M.ProductionRecord, global_sn=row.global_sn)
        c.eq('生产记录按任务 global_sn 落库', rec is not None,
              getattr(rec, 'global_sn', None))

    def t_edit(c, e):
        tid = e['seed']('task')
        notes = e['tag'] + '_任务编辑后'
        r = c.req('POST', f'/tasks/{tid}/edit', json={
            'employee_id': e['employee']['id'], 'process_id': e['process']['id'],
            'quantity': 11, 'target_date': '2026-11-30', 'status': 'completed',
            'notes': notes})
        b = r.get_json() or {}
        c.eq('响应 success=true', b.get('success') is True, b.get('message'))
        row = c.fresh(M.TaskAssignment, tid)
        c.snap_after('task', row, ['quantity', 'target_date', 'notes', 'status'])
        c.changed('task', 'quantity')
        c.eq('quantity=11', int(row.quantity) == 11, row.quantity)
        # ★ 缺陷探针：源码 routes.py:4502-4506 只赋值 target_date/employee_id/process_id/
        #   quantity，**没有 task.notes 赋值**，而 :4497/:4532 把 task.notes 当作已更新值
        #   写进审计 ⇒ 备注静默丢弃 + 审计 old/new 相同。
        c.eq('★ notes 入参被丢弃（期望落库，实测见 detail）', row.notes == notes,
              f'期望 {notes!r} 实测 {row.notes!r}')
        audit = (M.AuditLog.query.filter_by(target_model='TaskAssignment', target_id=tid)
                 .order_by(M.AuditLog.id.desc()).first())
        c.eq('★ 审计 old_data.notes == new_data.notes（都等于旧值）',
              (audit.old_data or {}).get('notes') == (audit.new_data or {}).get('notes')
              if audit else False,
              f'old={(audit.old_data or {}).get("notes")!r} '
              f'new={(audit.new_data or {}).get("notes")!r}')
        c.eq('status 按入参置 completed', row.status == 'completed', row.status)
        c.eq('审计行可回滚（can_rollback=True）',
              _audit_count(c.app, 'TaskAssignment') >= 1,
              _audit_count(c.app, 'TaskAssignment'))

    def t_delete(c, e):
        tid = e['seed']('task')
        n_before = c.count(M.TaskAssignment)
        r = c.req('DELETE', f'/tasks/{tid}')
        b = r.get_json() or {}
        c.eq('响应 success=true', b.get('success') is True, b.get('message'))
        n_after = c.count(M.TaskAssignment)
        c.eq('行数减少 1', n_after == n_before - 1, f'{n_before} -> {n_after}')
        c.eq('该行已不存在', c.by_id(M.TaskAssignment, tid) is None)

    def t_404(c, e):
        r = c.req('POST', '/tasks/999999999/update_status',
                  json={'completed_quantity': 1, 'materials': []})
        c.eq('不存在任务返回 404', r.status_code == 404, r.status_code)
        c.eq('404 为 JSON', 'json' in (r.headers.get('Content-Type') or ''), r.headers.get('Content-Type'))

    def t_overshoot(c, e):
        tid = e['seed']('task')
        r = c.req('POST', f'/tasks/{tid}/update_status',
                  json={'completed_quantity': 9999, 'materials': []})
        row = c.fresh(M.TaskAssignment, tid)
        c.snap_after('task', row, ['status', 'completed_quantity'])
        c.eq('超量被拒 400', r.status_code == 400, r.status_code)
        c.eq('库内状态未被改动', row.status == 'pending' and not row.completed_quantity,
              f'status={row.status} qty={row.completed_quantity}')

    P += [
        ('tasks', 'W-TASK-1', 'POST /tasks/add 新增任务（落库字段 + 审计）', t_add),
        ('tasks', 'W-TASK-2', 'POST /tasks/<id>/update_status 完工回写 status/completed_at', t_update_status),
        ('tasks', 'W-TASK-3', 'POST /tasks/<id>/edit 编辑任务（quantity/notes 落库）', t_edit),
        ('tasks', 'W-TASK-4', 'DELETE /tasks/<id> 删除任务（行消失）', t_delete),
        ('tasks', 'W-TASK-5', 'POST /tasks/<id>/update_status 不存在 id → 404 JSON', t_404),
        ('tasks', 'W-TASK-6', 'POST /tasks/<id>/update_status 超量 9999 → 400 且库不变', t_overshoot),
    ]

    # ============================================================ I: 库存
    def i_fp_add(c, e):
        r = c.req('POST', '/inventory/finished/add', json={
            'drawing_number': e['tag'] + '-DWG', 'model': 'T4MODEL',
            'production_date': '2026-10-06', 'inspector': '_t4',
            'product_number_type': 'manual', 'product_number': e['tag'] + '-FP1',
            'notes': e['tag']})
        b = r.get_json() or {}
        c.eq('响应 success=true', b.get('success') is True, b.get('message'))
        row = c.one(M.FinishedProduct, product_number=e['tag'] + '-FP1')
        c.eq('库内出现成品行', row is not None)
        if row:
            c.eq('status=in_stock', row.status == 'in_stock', row.status)
            c.eq('drawing_number 落库', row.drawing_number == e['tag'] + '-DWG', row.drawing_number)
            audit = _audit_count(c.app, 'FinishedProduct')
            c.eq('AuditLog 落库（target_model=FinishedProduct）', audit >= 1, f'audit={audit}')
            e['fp'] = row.id

    def i_fp_put(c, e):
        fid = e['fp']
        row0 = c.by_id(M.FinishedProduct, fid)
        c.snap('fp', row0, ['drawing_number', 'quantity', 'status', 'inspector'])
        r = c.req('PUT', f'/inventory/finished/{fid}', json={
            'drawing_number': e['tag'] + '-DWG2', 'model': 'T4MODEL2',
            'production_date': '2026-10-07', 'inspector': '_t4b', 'quantity': 9,
            'status': 'shipped', 'notes': e['tag']})
        b = r.get_json() or {}
        c.eq('响应 success=true', b.get('success') is True, b.get('message'))
        row = c.fresh(M.FinishedProduct, fid)
        c.snap_after('fp', row, ['drawing_number', 'quantity', 'status', 'inspector'])
        c.changed('fp', 'quantity')
        c.eq('quantity=9', row.quantity == 9, row.quantity)
        c.eq('status=shipped', row.status == 'shipped', row.status)
        c.eq('drawing_number 已改', row.drawing_number == e['tag'] + '-DWG2', row.drawing_number)

    def i_raw_add(c, e):
        r = c.req('POST', '/inventory/raw/add', json={
            'supplier': e['tag'] + '_供应商', 'category_id': e['raw_cat'],
            'supplier_number': e['tag'] + '-S1', 'storage_date': '2026-10-06',
            'quantity': 12.5, 'internal_number_type': 'manual',
            'internal_number': e['tag'] + '-RAW1', 'notes': e['tag']})
        b = r.get_json() or {}
        c.eq('响应 success=true', b.get('success') is True, b.get('message'))
        row = c.one(M.RawMaterial, internal_number=e['tag'] + '-RAW1')
        c.eq('库内出现原材料行', row is not None)
        if row:
            c.eq('quantity 落库=12.5', float(row.quantity) == 12.5, row.quantity)
            c.eq('category_id 落库', row.category_id == e['raw_cat'], row.category_id)
            e['raw'] = row.id

    def i_raw_put(c, e):
        rid = e['raw']
        row0 = c.by_id(M.RawMaterial, rid)
        c.snap('raw', row0, ['supplier', 'quantity', 'notes'])
        r = c.req('PUT', f'/inventory/raw/{rid}', json={
            'supplier': e['tag'] + '_供应商2', 'category_id': e['raw_cat'],
            'supplier_number': e['tag'] + '-S1', 'storage_date': '2026-10-06',
            'quantity': 3.25, 'notes': e['tag'] + '_改'})
        b = r.get_json() or {}
        c.eq('响应 success=true', b.get('success') is True, b.get('message'))
        row = c.fresh(M.RawMaterial, rid)
        c.snap_after('raw', row, ['supplier', 'quantity'])
        c.changed('raw', 'quantity')
        c.eq('quantity=3.25', abs(float(row.quantity) - 3.25) < 1e-9, row.quantity)

    def i_raw_archive(c, e):
        rid = e['raw']
        before = c.by_id(M.RawMaterial, rid)
        c.snap('raw', before, ['is_archived'])
        r = c.req('POST', f'/inventory/raw/{rid}/archive')
        row = c.fresh(M.RawMaterial, rid)
        c.snap_after('raw', row, ['is_archived'])
        c.eq('请求被处理（2xx/3xx）', r.status_code in (200, 302), r.status_code)
        c.changed('raw', 'is_archived')

    def i_raw_delete(c, e):
        rid = e['raw']
        n0 = c.count(M.RawMaterial)
        r = c.req('DELETE', f'/inventory/raw/{rid}')
        n1 = c.count(M.RawMaterial)
        c.eq('请求 2xx', r.status_code in (200, 204), r.status_code)
        c.eq('行数减少 1', n1 == n0 - 1, f'{n0} -> {n1}')
        c.eq('该行已删除', c.by_id(M.RawMaterial, rid) is None)

    def i_consumable_use(c, e):
        from app import models as M
        cons = c.one(M.Consumable, supplier_number=e['cons_sn'])
        c.eq('前置易耗品存在（本组夹具）', cons is not None, e['cons_sn'])
        if cons is None:
            return
        cid = cons.id
        row0 = c.by_id(M.Consumable, cid)
        c.snap('cons', row0, ['quantity', 'status'])
        r = c.req('POST', f'/consumables/{cid}/use',
                  json={'usage_quantity': 3, 'used_by': '_t4', 'usage_purpose': e['tag']})
        row = c.fresh(M.Consumable, cid)
        if row is None:
            c.eq('库内该行仍存在', False, '行不见了')
            return
        c.snap_after('cons', row, ['quantity', 'status'])
        # ★ 缺陷探针：routes.py:10939 use_consumable 直接用 Consumable，但该模块
        #   只在 :10555/:10683/:10786 三处**函数内**导入 Consumable ⇒ 本函数 NameError
        #   → 500；同时库存完全没扣（拒绝时不留半成品，但功能整体不可用）。
        c.eq('★ 使用易耗品成功（期望 quantity 减少 3；实测见 detail）',
              r.status_code == 200 and abs(float(row.quantity) - (float(row0.quantity) - 3)) < 1e-9,
              f'HTTP {r.status_code} quantity {row0.quantity} -> {row.quantity} '
              f'响应={r.get_data(as_text=True)[:120]}')
        c.eq('★ 失败时不得改动库存（守恒）', float(row.quantity) == float(row0.quantity),
              f'{row0.quantity} -> {row.quantity}')

    def i_consumable_put(c, e):
        from app import models as M
        cons = c.one(M.Consumable, supplier_number=e['cons_sn'])
        c.eq('前置易耗品存在（本组夹具）', cons is not None, e['cons_sn'])
        if cons is None:
            return
        cid = cons.id
        row0 = c.by_id(M.Consumable, cid)
        c.snap('cons', row0, ['specification', 'unit_price'])
        r = c.req('PUT', f'/consumables/{cid}',
                  json={'specification': e['tag'] + '-规格', 'unit_price': 7.5})
        b = r.get_json() or {}
        c.eq('响应 success=true', b.get('success') is True, b.get('message'))
        row = c.fresh(M.Consumable, cid)
        if row is None:
            c.eq('库内该行仍存在', False, '行不见了')
            return
        c.snap_after('cons', row, ['specification', 'unit_price'])
        c.changed('cons', 'specification')
        c.eq('unit_price=7.5', abs(float(row.unit_price or 0) - 7.5) < 1e-9, row.unit_price)

    def i_raw_cat_add(c, e):
        r = c.req('POST', '/inventory/raw-material/categories/add', json={
            'name': e['tag'] + '_品类', 'code': e['tag'] + 'CAT'})
        b = r.get_json() or {}
        c.eq('响应 success=true', b.get('success') is True, b.get('message'))
        row = c.one(M.RawMaterialCategory, code=e['tag'] + 'CAT')
        c.eq('库内出现品类行', row is not None, b)
        if row:
            c.eq('name 落库', row.name == e['tag'] + '_品类', row.name)

    def i_req_flow(c, e):
        """领用（表单型）→ 发料扣账：真实数据变化 + 状态机。"""
        cons = c.one(M.Consumable, supplier_number=e['cons_sn'])
        c.eq('前置易耗品存在（本组夹具）', cons is not None, e['cons_sn'])
        if cons is None:
            return
        mid = cons.id
        row0 = c.by_id(M.Consumable, mid)
        before_qty = float(row0.quantity)
        r = c.req('POST', '/material_requisitions/add', data={
            'employee_id': e['employee']['id'], 'purpose': e['tag'] + '_领用',
            'requisition_date': '2026-10-06', 'production_order_id': 0,
            'materials_data': json.dumps([{'material_type': 'consumable', 'material_id': mid,
                                           'quantity': 2, 'unit': '个', 'notes': e['tag']}]),
            'submit': '保存记录'})
        c.eq('创建领用单 3xx/2xx', r.status_code in (200, 302), r.status_code)
        req = c.one(M.MaterialRequisition, purpose=e['tag'] + '_领用')
        c.eq('库内出现领用单', req is not None)
        if not req:
            return
        e['requisition'] = req.id
        c.eq('状态 ∈ {approved, pending}（按品类审批口径）',
              req.status in ('approved', 'pending'), req.status)
        with c.app.app_context():
            item = M.MaterialRequisitionItem.query.filter_by(requisition_id=req.id).first()
        c.eq('明细 material_id 命中真实物料', item is not None and item.material_id == mid,
              getattr(item, 'material_id', None))
        if req.status == 'pending':
            c.req('POST', f'/material_requisitions/{req.id}/approve')
            req = c.fresh(M.MaterialRequisition, req.id)
            c.eq('审批后 status=approved', req.status == 'approved', req.status)
        r2 = c.req('POST', f'/material_requisitions/{req.id}/issue', json={})
        b2 = r2.get_json() or {}
        c.eq('发料 success=true', b2.get('success') is True, b2.get('message'))
        row1 = c.fresh(M.Consumable, mid)
        c.eq('库存减少 2', abs(float(row1.quantity) - (before_qty - 2)) < 1e-9,
              f'{before_qty} -> {row1.quantity}')
        req1 = c.fresh(M.MaterialRequisition, req.id)
        c.eq('领用单 status=completed', req1.status == 'completed', req1.status)

    def i_inbound(c, e):
        r = c.req('POST', '/inventory/raw-material/inbound', data={
            'supplier_0': e['tag'] + '_入库供应商', 'material_name_0': e['tag'] + '_入库品',
            'supplier_number_0': e['tag'] + '-IN1', 'quantity_0': '4',
            'storage_date_0': '2026-10-06', 'category_id_0': str(e['raw_cat']),
            'internal_number_0': e['tag'] + '-INRAW'})
        row = c.one(M.RawMaterial, internal_number=e['tag'] + '-INRAW')
        c.eq('批量入库行落库', row is not None,
              f'HTTP {r.status_code} body={r.get_data(as_text=True)[:120]}')
        if row:
            c.eq('quantity=4', float(row.quantity) == 4.0, row.quantity)

    P += [
        ('inventory', 'W-INV-1', 'POST /inventory/finished/add 新增成品（落库+审计）', i_fp_add),
        ('inventory', 'W-INV-2', 'PUT /inventory/finished/<id> 改字段（quantity/status 落库）', i_fp_put),
        ('inventory', 'W-INV-3', 'POST /inventory/raw/add 新增原材料（quantity/category 落库）', i_raw_add),
        ('inventory', 'W-INV-4', 'PUT /inventory/raw/<id> 改字段（quantity 落库）', i_raw_put),
        ('inventory', 'W-INV-5', 'POST /inventory/raw/<id>/archive 归档开关（is_archived 变化）', i_raw_archive),
        ('inventory', 'W-INV-6', 'DELETE /inventory/raw/<id> 删除（行消失）', i_raw_delete),
        ('inventory', 'W-INV-7', 'POST /consumables/<id>/use 领用扣减（quantity 变化）', i_consumable_use),
        ('inventory', 'W-INV-8', 'PUT /consumables/<id> 改规格与单价（字段落库）', i_consumable_put),
        ('inventory', 'W-INV-9', 'POST /inventory/raw-material/categories/add 新增品类（行落库）', i_raw_cat_add),
        ('inventory', 'W-INV-10', 'POST /material_requisitions/add → /issue 发料扣账（库存-2 + 状态机）', i_req_flow),
        ('inventory', 'W-INV-11', 'POST /inventory/raw-material/inbound 批量入库（行落库）', i_inbound),
    ]

    # ============================================================ Q: 质量
    def _mk_tpl(c, e, suffix='TPL'):
        """本探针自建模板（保证每个断言自带前置，不跨探针依赖顺序）。"""
        code = e['tag'] + suffix
        r = c.req('POST', '/api/quality/templates', json={
            'template_code': code, 'name': e['tag'] + '_模板' + suffix, 'type': 'product',
            'description': e['tag'], 'base_items': [
                {'name': '批次', 'input_type': 'text', 'is_required': True}]})
        b = r.get_json() or {}
        row = c.one(M.InspectionTemplate, template_code=code)
        return row, b, r

    def _mk_qtask(c, e, tpl_id, suffix='T'):
        r = c.req('POST', '/api/quality/tasks', json={
            'template_id': tpl_id, 'type': 'product', 'inspection_target_id': e['product'],
            'inspector_id': e['admin_id'], 'priority': 2,
            'planned_completion_time': '2026-12-31T10:00',
            'notes': e['tag'] + suffix})
        b = r.get_json() or {}
        return (b.get('data') or {}).get('id'), b

    def q_tpl_add(c, e):
        row, b, r = _mk_tpl(c, e, 'T1')
        c.eq('响应 success=true', b.get('success') is True, b.get('message'))
        c.eq('库内出现模板', row is not None, b)
        if row:
            e['tpl'] = row.id
            c.eq('type 落库', row.type == 'product', row.type)
            with c.app.app_context():
                n_base = M.InspectionBaseItem.query.filter_by(template_id=row.id).count()
            c.eq('基础项落库', n_base >= 1, f'base_items={n_base}')

    def q_task_add(c, e):
        tpl, b0, _ = _mk_tpl(c, e, 'T2')
        c.eq('前置模板已建', tpl is not None)
        if tpl is None:
            return
        tid, b = _mk_qtask(c, e, tpl.id, 'TA')
        c.eq('响应 success=true', b.get('success') is True, b.get('message'))
        c.eq('返回新任务 id', bool(tid), b)
        row = c.by_id(M.InspectionTask, tid) if tid else None
        c.eq('库内出现任务', row is not None)
        if row:
            e['qtask'] = row.id
            c.eq('status=pending 落库', row.status == 'pending', row.status)
            c.eq('inspector_id 落库', row.inspector_id == e['admin_id'], row.inspector_id)
            c.eq('priority=2 落库', int(row.priority) == 2, row.priority)

    def q_task_put(c, e):
        """PUT /api/quality/tasks/<id>：实现只认 template_id/inspector_id/target*/priority/
        deadline/notes，**不认 status**（``quality.py:1057-1084``）⇒ 用 notes 证明落库。"""
        tpl, _, _ = _mk_tpl(c, e, 'T3')
        tid, _ = _mk_qtask(c, e, tpl.id, 'TB') if tpl else (None, None)
        c.eq('前置任务已建', bool(tid))
        if not tid:
            return
        row0 = c.by_id(M.InspectionTask, tid)
        c.snap('qtask', row0, ['status', 'notes'])
        r = c.req('PUT', f'/api/quality/tasks/{tid}', json={
            'notes': e['tag'] + '_改', 'status': 'cancelled'})
        b = r.get_json() or {}
        c.eq('响应 success=true', b.get('success') is True, b.get('message'))
        row = c.fresh(M.InspectionTask, tid)
        c.snap_after('qtask', row, ['status', 'notes'])
        c.changed('qtask', 'notes')
        c.eq('notes 落库为新值', row.notes == e['tag'] + '_改', row.notes)
        c.eq('status 未被本端点消费（仍 pending）', row.status == 'pending', row.status)

    def q_start(c, e):
        """start-inspection：任务 pending → in_progress，且自动建质检记录。"""
        tpl, _, _ = _mk_tpl(c, e, 'T4')
        tid, ab = _mk_qtask(c, e, tpl.id, 'TC') if tpl else (None, None)
        c.eq('预备任务已建', bool(tid), ab)
        if not tid:
            return
        r2 = c.req('POST', f'/api/quality/tasks/{tid}/start-inspection',
                   json={'template_id': tpl.id, 'notes': e['tag']})
        b2 = r2.get_json() or {}
        c.eq('开始质检 success=true', b2.get('success') is True, b2.get('message'))
        row = c.fresh(M.InspectionTask, tid)
        c.eq('任务 status=in_progress', row.status == 'in_progress', row.status)
        rec = c.one(M.InspectionRecord, task_id=tid)
        c.eq('质检记录落库', rec is not None)
        if rec:
            c.eq('记录 result=pending', rec.result == 'pending', rec.result)
            e['qrec'] = rec.id

    def q_submit(c, e):
        tpl, _, _ = _mk_tpl(c, e, 'T9')
        tid, _ = _mk_qtask(c, e, tpl.id, 'TE') if tpl else (None, None)
        if not tid:
            c.eq('前置任务已建', False, '模板/任务未建成')
            return
        c.req('POST', f'/api/quality/tasks/{tid}/start-inspection',
              json={'template_id': tpl.id, 'notes': e['tag']})
        rec = c.one(M.InspectionRecord, task_id=tid)
        c.eq('前置质检记录已建（start-inspection 产物）', rec is not None)
        if rec is None:
            return
        rid = rec.id
        row0 = c.by_id(M.InspectionRecord, rid)
        c.snap('rec', row0, ['result', 'notes'])
        r = c.req('POST', f'/api/quality/records/{rid}/submit',
                  json={'result': 'pass', 'notes': e['tag'] + '_提交'})
        b = r.get_json() or {}
        c.eq('提交 success=true', b.get('success') is True, b.get('message'))
        row = c.fresh(M.InspectionRecord, rid)
        c.snap_after('rec', row, ['result', 'notes'])
        c.changed('rec', 'result')
        c.eq('result=pass 落库', row.result == 'pass', row.result)
        task = c.by_id(M.InspectionTask, row.task_id)
        c.eq('任务随之 completed', task.status == 'completed', task.status)

    def q_tpl_put(c, e):
        """PUT 全字段更新（实现要求 template_code/name/type 三个键都在，缺一即 500 —— 见 W-QLT-3）。"""
        tpl, _, _ = _mk_tpl(c, e, 'T5')
        c.eq('前置模板已建', tpl is not None)
        if tpl is None:
            return
        row0 = c.by_id(M.InspectionTemplate, tpl.id)
        c.snap('tpl', row0, ['is_active', 'name'])
        r = c.req('PUT', f'/api/quality/templates/{tpl.id}',
                  json={'template_code': tpl.template_code, 'name': e['tag'] + '_模板改',
                        'type': 'product', 'is_active': False})
        b = r.get_json() or {}
        c.eq('响应 success=true', b.get('success') is True, b.get('message'))
        row = c.fresh(M.InspectionTemplate, tpl.id)
        c.snap_after('tpl', row, ['is_active', 'name'])
        c.changed('tpl', 'is_active')
        c.eq('is_active=False', row.is_active is False, row.is_active)
        c.eq('name 落库为新值', row.name == e['tag'] + '_模板改', row.name)

    def q_tpl_partial_put(c, e):
        """★ 缺陷探针：PUT 只给 is_active（部分更新）→ 500 + 原文 'template_code'。

        实现（``quality.py:408-410``）用 ``data['template_code']`` / ``data['name']`` /
        ``data['type']`` 下标取值，缺键即 KeyError，被 ``except Exception`` 吞成
        ``500 {'success': false, 'message': "操作失败：'template_code'"}``。
        断言口径：**必须证明这次请求没有改动库**（行仍在、is_active 未变）。
        """
        tpl, _, _ = _mk_tpl(c, e, 'T6')
        c.eq('前置模板已建', tpl is not None)
        if tpl is None:
            return
        row0 = c.by_id(M.InspectionTemplate, tpl.id)
        c.snap('tpl', row0, ['is_active', 'name'])
        n0 = c.count(M.InspectionTemplate)
        r = c.req('PUT', f'/api/quality/templates/{tpl.id}', json={'is_active': False})
        b = r.get_json() or {}
        row = c.fresh(M.InspectionTemplate, tpl.id)
        c.snap_after('tpl', row, ['is_active'])
        c.eq('★ 部分更新被拒（期望 4xx，实测见 code）', r.status_code in (400, 422),
              f'实测 HTTP {r.status_code} message={b.get("message")!r}')
        c.eq('★ 拒绝时不得改动库（is_active 未变）', row.is_active == row0.is_active,
              f'{row0.is_active} -> {row.is_active}')
        c.eq('★ 模板行数未变', c.count(M.InspectionTemplate) == n0,
              c.count(M.InspectionTemplate))

    def q_tpl_delete(c, e):
        tpl, _, _ = _mk_tpl(c, e, 'T7')
        c.eq('前置模板已建（且无任务引用）', tpl is not None)
        if tpl is None:
            return
        n0 = c.count(M.InspectionTemplate)
        r = c.req('DELETE', f'/api/quality/templates/{tpl.id}')
        n1 = c.count(M.InspectionTemplate)
        c.eq('请求 2xx', r.status_code in (200, 204), r.status_code)
        c.eq('模板行数减少 1', n1 == n0 - 1, f'{n0} -> {n1}')
        c.eq('模板已删除', c.by_id(M.InspectionTemplate, tpl.id) is None)

    def q_task_delete(c, e):
        tpl, _, _ = _mk_tpl(c, e, 'T8')
        tid, _ = _mk_qtask(c, e, tpl.id, 'TD') if tpl else (None, None)
        c.eq('前置任务已建', bool(tid))
        if not tid:
            return
        n0 = c.count(M.InspectionTask)
        r = c.req('DELETE', f'/api/quality/tasks/{tid}')
        n1 = c.count(M.InspectionTask)
        c.eq('请求 2xx', r.status_code in (200, 204), r.status_code)
        c.eq('任务行数减少 1', n1 == n0 - 1, f'{n0} -> {n1}')
        c.eq('任务已删除', c.by_id(M.InspectionTask, tid) is None)

    def q_tpl_dup(c, e):
        """阴性对照：同 code 重复创建必须被拒且不新增行（与是否已删除无关）。"""
        with c.app.app_context():
            from app import db
            db.session.add(M.InspectionTemplate(template_code=e['tag'] + 'DUP',
                                                name=e['tag'] + '_dup', type='product',
                                                is_active=True, created_by=e['admin_id']))
            db.session.commit()
        n0 = c.count(M.InspectionTemplate)
        r = c.req('POST', '/api/quality/templates', json={
            'template_code': e['tag'] + 'DUP', 'name': 'dup', 'type': 'product'})
        b = r.get_json() or {}
        c.eq('重复 code 被拒 400', r.status_code == 400, f'{r.status_code} {b.get("message")}')
        c.eq('模板行数未增加', c.count(M.InspectionTemplate) == n0, c.count(M.InspectionTemplate))

    P += [
        ('quality', 'W-QLT-1', 'POST /api/quality/templates 建模板（模板+基础项落库）', q_tpl_add),
        ('quality', 'W-QLT-2', 'PUT /api/quality/templates/<id> 全字段更新（is_active/name 落库）', q_tpl_put),
        ('quality', 'W-QLT-3', '★ PUT 部分字段（仅 is_active）→ 500 而非 4xx，且库不变', q_tpl_partial_put),
        ('quality', 'W-QLT-4', 'DELETE /api/quality/templates/<id>（未被任务引用 → 行消失）', q_tpl_delete),
        ('quality', 'W-QLT-5', 'POST /api/quality/tasks 建任务（status/priority/inspector 落库）', q_task_add),
        ('quality', 'W-QLT-6', 'PUT /api/quality/tasks/<id> 更新（notes 落库；status 被忽略）', q_task_put),
        ('quality', 'W-QLT-7', 'POST /api/quality/tasks/<id>/start-inspection（任务状态 + 记录落库）', q_start),
        ('quality', 'W-QLT-8', 'POST /api/quality/records/<id>/submit（result 落库 + 任务闭环）', q_submit),
        ('quality', 'W-QLT-9', 'DELETE /api/quality/tasks/<id>（行消失）', q_task_delete),
        ('quality', 'W-QLT-10', '阴性：重复 template_code → 400 且不新增行', q_tpl_dup),
    ]

    # ============================================================ PR: 生产
    def p_order_add(c, e):
        r = c.req('POST', '/production_orders/add', json={
            'product_id': e['routed_product'], 'planned_quantity': 5,
            'planned_start_date': '2026-10-06', 'planned_end_date': '2026-10-31',
            'notes': e['tag']})
        b = r.get_json() or {}
        c.eq('响应 success=true', b.get('success') is True, b.get('message'))
        row = c.one(M.ProductionOrder, notes=e['tag'])
        c.eq('库内出现生产订单', row is not None, b)
        if row:
            e['order'] = row.id
            c.eq('planned_quantity=5', int(row.planned_quantity) == 5, row.planned_quantity)
            c.eq('status 初始 pending', row.status == 'pending', row.status)

    def p_batch_add(c, e):
        r = c.req('POST', f'/production_orders/{e["order"]}/batches/add', json={
            'batch_quantity': 5, 'notes': e['tag']})
        b = r.get_json() or {}
        c.eq('响应 success=true', b.get('success') is True, b.get('message'))
        row = c.one(M.ProductionBatch, production_order_id=e['order'])
        c.eq('库内出现批次', row is not None, b)
        if row:
            e['batch'] = row.id
            c.eq('batch_quantity=5', int(row.batch_quantity) == 5, row.batch_quantity)

    def p_batch_status(c, e):
        bid = e['batch']
        row0 = c.by_id(M.ProductionBatch, bid)
        c.snap('batch', row0, ['status'])
        r = c.req('PUT', f'/production_batches/{bid}/status', json={'status': 'in_progress'})
        b = r.get_json() or {}
        c.eq('响应 success=true', b.get('success') is True, b.get('message'))
        row = c.fresh(M.ProductionBatch, bid)
        c.snap_after('batch', row, ['status'])
        c.changed('batch', 'status')
        c.eq('status=in_progress', row.status == 'in_progress', row.status)

    def p_batch_item_put(c, e):
        """批次实例：先由 create_instances 建实例，再 PUT 改 quality_status（routes.py:8899 唯一写入点）。"""
        r = c.req('POST', '/api/production_center/create_instances', json={
            'batch_id': e['batch'], 'items': [{'sequence': 1, 'product_code': e['tag'] + 'BI'}]})
        body = r.get_json() or {}
        c.notes.append(f'create_instances HTTP {r.status_code} {str(body)[:160]}')
        bi = c.one(M.ProductionBatchItem, batch_id=e['batch'])
        if bi is None:
            # 接口形态不同：退回直接造一行（夹具补齐），以便验证 PUT 的落库
            with c.app.app_context():
                from app import db
                bi = M.ProductionBatchItem(batch_id=e['batch'], item_sequence=7001,
                                           product_code=e['tag'] + 'BI', status='in_progress',
                                           quality_status='pending')
                db.session.add(bi)
                db.session.commit()
            c.notes.append('实例由夹具补齐（接口形态与猜测不同，见 notes）')
        e['batch_item'] = bi.id
        c.snap('bi', bi, ['quality_status', 'status'])
        r2 = c.req('PUT', f'/production_batch_items/{bi.id}/update',
                   json={'quality_status': 'fail', 'notes': e['tag']})
        b2 = r2.get_json() or {}
        c.eq('响应 success=true', b2.get('success') is True, b2.get('message'))
        row = c.fresh(M.ProductionBatchItem, bi.id)
        c.snap_after('bi', row, ['quality_status'])
        c.changed('bi', 'quality_status')
        c.eq('quality_status=fail 落库', row.quality_status == 'fail', row.quality_status)

    def p_order_delete(c, e):
        """删除需要「无批次且状态 ∈ {pending, cancelled}」⇒ 本探针自建一条干净订单再删。"""
        with c.app.app_context():
            from app import db
            po = M.ProductionOrder(product_id=e['routed_product'], planned_quantity=2,
                                   planned_start_date=date(2026, 10, 6),
                                   planned_end_date=date(2026, 10, 31), status='pending',
                                   created_by=e['admin_id'], notes=e['tag'] + '_del')
            db.session.add(po)
            db.session.commit()
            del_id = po.id
        n0 = c.count(M.ProductionOrder)
        r = c.req('DELETE', f'/production_orders/{del_id}')
        b = r.get_json() or {}
        n1 = c.count(M.ProductionOrder)
        c.eq('响应 success=true', b.get('success') is True, b.get('message'))
        c.eq('订单行数减少 1', n1 == n0 - 1, f'{n0} -> {n1}')
        c.eq('该行已删除', c.by_id(M.ProductionOrder, del_id) is None)

    P += [
        ('production', 'W-PRD-1', 'POST /production_orders/add 建生产单（落库，含工艺路线前置）', p_order_add),
        ('production', 'W-PRD-2', 'POST /production_orders/<id>/batches/add 建批次（落库）', p_batch_add),
        ('production', 'W-PRD-3', 'PUT /production_batches/<id>/status 改批次状态（status 落库）', p_batch_status),
        ('production', 'W-PRD-4', 'PUT /production_batch_items/<id>/update 改质检状态（quality_status 落库）', p_batch_item_put),
        ('production', 'W-PRD-5', 'DELETE /production_orders/<id> 删除订单（行消失）', p_order_delete),
    ]

    # ============================================================ PU: 采购
    def pu_supplier(c, e):
        r = c.req('POST', '/suppliers/save', data={
            'code': e['tag'] + 'SUP', 'name': e['tag'] + '_供应商', 'contact': '_t4',
            'phone': '13800000000', 'address': '_t4 地址', 'is_active': 'on', 'notes': e['tag']})
        row = c.one(M.Supplier, code=e['tag'] + 'SUP')
        c.eq('供应商落库', row is not None, f'HTTP {r.status_code}')
        if row:
            c.eq('name 落库', row.name == e['tag'] + '_供应商', row.name)

    def pu_req_save(c, e):
        r = c.req('POST', '/purchase_requisitions/save', data={
            'item_name': [e['tag'] + '_物料'], 'item_qty': ['3'],
            'item_spec': e['tag'] + '_规格', 'notes': e['tag']})
        row = c.one(M.PurchaseRequisition, notes=e['tag'])
        c.eq('采购申请落库', row is not None, f'HTTP {r.status_code} {r.get_data(as_text=True)[:120]}')
        if row:
            e['preq'] = row.id
            c.eq('状态为待审批', row.status in ('pending', 'draft'), row.status)

    def pu_req_approve(c, e):
        row0 = c.by_id(M.PurchaseRequisition, e['preq'])
        c.snap('preq', row0, ['status'])
        r = c.req('POST', f'/purchase_requisitions/{e["preq"]}/approve',
                  data={'decision': 'approve', 'notes': e['tag']})
        row = c.fresh(M.PurchaseRequisition, e['preq'])
        c.snap_after('preq', row, ['status'])
        c.eq('请求 2xx/3xx', r.status_code in (200, 302), r.status_code)
        c.changed('preq', 'status')

    def pu_order_save(c, e):
        sup = c.one(M.Supplier, code=e['tag'] + 'SUP')
        c.eq('前置供应商存在（W-PUR-1 产物）', sup is not None)
        if sup is None:
            return
        r = c.req('POST', '/purchase_orders/save', data={
            'supplier_id': sup.id, 'item_name': [e['tag'] + '_物料'],
            'item_qty': ['3'], 'item_price': ['10'], 'item_type': ['raw'],
            'notes': e['tag']})
        row = c.one(M.PurchaseOrder, notes=e['tag'])
        c.eq('采购订单落库', row is not None,
              f'HTTP {r.status_code} {r.get_data(as_text=True)[:100]}')
        if row:
            e['porder'] = row.id
            c.eq('supplier_id 落库', row.supplier_id == sup.id, row.supplier_id)
            with c.app.app_context():
                n_items = M.PurchaseOrderItem.query.filter_by(po_id=row.id).count()
            c.eq('订单明细落库', n_items >= 1, f'items={n_items}')

    def pu_order_receive(c, e):
        row0 = c.by_id(M.PurchaseOrder, e['porder'])
        c.snap('porder', row0, ['status'])
        n0 = c.count(M.GoodsReceipt)
        r = c.req('POST', f'/purchase_orders/{e["porder"]}/receive', data={'notes': e['tag']})
        row = c.fresh(M.PurchaseOrder, e['porder'])
        c.snap_after('porder', row, ['status'])
        c.eq('请求 2xx/3xx', r.status_code in (200, 302), r.status_code)
        c.eq('到货单新增', c.count(M.GoodsReceipt) > n0,
              f'{n0} -> {c.count(M.GoodsReceipt)}')

    P += [
        ('purchase', 'W-PUR-1', 'POST /suppliers/save 新增供应商（落库）', pu_supplier),
        ('purchase', 'W-PUR-2', 'POST /purchase_requisitions/save 建采购申请（落库）', pu_req_save),
        ('purchase', 'W-PUR-3', 'POST /purchase_requisitions/<id>/approve 审批（status 落库）', pu_req_approve),
        ('purchase', 'W-PUR-4', 'POST /purchase_orders/save 建采购订单（落库）', pu_order_save),
        ('purchase', 'W-PUR-5', 'POST /purchase_orders/<id>/receive 收货（到货单新增）', pu_order_receive),
    ]

    # ============================================================ SH: 发货
    def sh_create(c, e):
        r = c.req('POST', '/shipments/create', data={
            'sales_order_id': e['sales_order'], 'notes': e['tag']})
        row = c.one(M.Shipment, sales_order_id=e['sales_order'])
        c.eq('发货单落库', row is not None, f'HTTP {r.status_code} {r.get_data(as_text=True)[:120]}')
        if row:
            e['shipment'] = row.id
            c.eq('状态为草稿', row.status == 'draft', row.status)

    def sh_add_item(c, e):
        r = c.req('POST', f'/shipments/{e["shipment"]}/add_item', data={
            'finished_product_id': e['fg_stock'], 'quantity': 1})
        n0 = 0
        with c.app.app_context():
            n0 = M.ShipmentItem.query.filter_by(shipment_id=e['shipment']).count()
        c.eq('发货明细新增', n0 >= 1, f'items={n0} HTTP {r.status_code} '
                                     f'{r.get_data(as_text=True)[:100]}')

    def sh_ship(c, e):
        ship0 = c.by_id(M.Shipment, e['shipment'])
        c.snap('ship', ship0, ['status'])
        r = c.req('POST', f'/shipments/{e["shipment"]}/ship')
        ship = c.fresh(M.Shipment, e['shipment'])
        c.snap_after('ship', ship, ['status'])
        c.eq('请求 2xx/3xx', r.status_code in (200, 302), r.status_code)
        c.changed('ship', 'status')
        c.eq('status=shipped', ship.status == 'shipped', ship.status)

    def sh_sign(c, e):
        ship0 = c.by_id(M.Shipment, e['shipment'])
        c.snap('ship', ship0, ['status'])
        n0 = 0
        with c.app.app_context():
            n0 = M.ShipmentReceipt.query.filter_by(shipment_id=e['shipment']).count()
        r = c.req('POST', f'/shipments/{e["shipment"]}/sign',
                  data={'signed_by_name': e['tag'] + '_签收人', 'notes': e['tag']})
        ship = c.fresh(M.Shipment, e['shipment'])
        c.snap_after('ship', ship, ['status'])
        with c.app.app_context():
            n1 = M.ShipmentReceipt.query.filter_by(shipment_id=e['shipment']).count()
            rec = M.ShipmentReceipt.query.filter_by(shipment_id=e['shipment']).first()
        c.eq('请求 2xx/3xx', r.status_code in (200, 302), r.status_code)
        c.eq('签收记录新增', n1 == n0 + 1, f'{n0} -> {n1}')
        c.eq('签收人落库', rec is not None and rec.signed_by_name == e['tag'] + '_签收人',
              getattr(rec, 'signed_by_name', None))
        c.changed('ship', 'status')

    P += [
        ('shipping', 'W-SHP-1', 'POST /shipments/create 建发货单（落库，draft）', sh_create),
        ('shipping', 'W-SHP-2', 'POST /shipments/<id>/add_item 加入明细（明细行新增）', sh_add_item),
        ('shipping', 'W-SHP-3', 'POST /shipments/<id>/ship 出库（status 落库 + 成品行状态）', sh_ship),
        ('shipping', 'W-SHP-4', 'POST /shipments/<id>/sign 签收（signed_by_name 落库）', sh_sign),
    ]

    # ============================================================ EQ: 设备
    def eq_save(c, e):
        r = c.req('POST', '/equipment/save', data={
            'code': e['tag'] + 'EQ', 'name': e['tag'] + '_设备', 'kind': 'machine',
            'status': 'running', 'length_mm': '1000', 'height_mm': '500', 'notes': e['tag']})
        row = c.one(M.Equipment, code=e['tag'] + 'EQ')
        c.eq('设备落库', row is not None, f'HTTP {r.status_code}')
        if row:
            e['equipment'] = row.id
            c.eq('name 落库', row.name == e['tag'] + '_设备', row.name)
            c.eq('length_mm=1000 落库', float(row.length_mm or 0) == 1000.0, row.length_mm)

    def eq_put(c, e):
        r = c.req('POST', '/equipment/save', data={
            'id': e['equipment'], 'code': e['tag'] + 'EQ', 'name': e['tag'] + '_设备改',
            'kind': 'machine', 'status': 'idle', 'notes': e['tag']})
        row = c.fresh(M.Equipment, e['equipment'])
        c.eq('名称已改', row.name == e['tag'] + '_设备改', row.name)
        c.eq('status=idle', row.status == 'idle', row.status)

    def eq_downtime(c, e):
        eq = c.by_id(M.Equipment, e['equipment'])
        c.snap('eq', eq, ['status'])
        r = c.req('POST', f'/equipment/{e["equipment"]}/downtime', data={'reason': e['tag']})
        eq2 = c.fresh(M.Equipment, e['equipment'])
        c.snap_after('eq', eq2, ['status'])
        c.eq('请求 2xx/3xx', r.status_code in (200, 302), r.status_code)
        c.eq('status=maintenance', eq2.status == 'maintenance', eq2.status)
        c.eq('停机记录落库', c.count(M.EquipmentDowntime, equipment_id=e['equipment']) >= 1)

    def eq_resume(c, e):
        r = c.req('POST', f'/equipment/{e["equipment"]}/resume')
        eq2 = c.fresh(M.Equipment, e['equipment'])
        c.eq('status=running', eq2.status == 'running', eq2.status)

    def eq_heat_lot(c, e):
        r = c.req('POST', '/heat_lots/create', data={
            'equipment_id': e['equipment'], 'recipe_notes': e['tag']})
        row = c.one(M.HeatLot, equipment_id=e['equipment'])
        c.eq('炉次落库', row is not None, f'HTTP {r.status_code} {r.get_data(as_text=True)[:100]}')
        if row:
            e['heat_lot'] = row.id

    def eq_heat_fire(c, e):
        if not e.get('heat_lot'):
            c.eq('炉次前置存在', False, 'create 未产出')
            return
        row0 = c.by_id(M.HeatLot, e['heat_lot'])
        c.snap('lot', row0, ['status'])
        r = c.req('POST', f'/heat_lots/{e["heat_lot"]}/fire')
        row = c.fresh(M.HeatLot, e['heat_lot'])
        c.snap_after('lot', row, ['status'])
        c.eq('请求 2xx/3xx', r.status_code in (200, 302), r.status_code)
        c.changed('lot', 'status')

    P += [
        ('equipment', 'W-EQP-1', 'POST /equipment/save 建设备（落库含尺寸）', eq_save),
        ('equipment', 'W-EQP-2', 'POST /equipment/save 带 id 更新设备（name/status 落库）', eq_put),
        ('equipment', 'W-EQP-3', 'POST /equipment/<id>/downtime 停机（status + 停机记录落库）', eq_downtime),
        ('equipment', 'W-EQP-4', 'POST /equipment/<id>/resume 恢复（status 落库）', eq_resume),
        ('equipment', 'W-EQP-5', 'POST /heat_lots/create 建炉次（落库）', eq_heat_lot),
        ('equipment', 'W-EQP-6', 'POST /heat_lots/<id>/fire 点火（status 落库）', eq_heat_fire),
    ]

    # ============================================================ MS: 杂项/主数据
    def ms_customer(c, e):
        """客户表单型端点：先 GET 表单页取隐藏字段/CSRF，再按表单口径 POST。"""
        page = c.req('GET', '/customer/add')
        hidden = dict(re.findall(r'<input[^>]*type="hidden"[^>]*name="([^"]+)"[^>]*value="([^"]*)"',
                                 page.get_data(as_text=True)))
        payload = {'customer_code': e['tag'] + 'CUS', 'customer_name': e['tag'] + '_客户',
                   'customer_type': 'enterprise', 'contact_person': '_t4',
                   'contact_phone': '13800000000', 'contact_email': '',
                   'credit_limit': '0', 'payment_terms': '', 'industry': '',
                   'company_size': '', 'website': '', 'status': 'active', 'notes': e['tag']}
        payload.update(hidden)
        r = c.req('POST', '/customer/add', data=payload)
        body = r.get_data(as_text=True)
        errs = re.findall(r'<span[^>]*class="[^"]*invalid-feedback[^"]*"[^>]*>(.*?)</span>',
                          body, re.S)[:4]
        row = c.one(M.Customer, customer_code=e['tag'] + 'CUS')
        c.eq('客户落库', row is not None,
              f'HTTP {r.status_code} loc={r.headers.get("Location", "")} '
              f'hidden={sorted(hidden)} form_errors={errs}')
        if row:
            e['customer'] = row.id
            c.eq('customer_name 落库', row.customer_name == e['tag'] + '_客户', row.customer_name)

    def ms_product(c, e):
        r = c.req('POST', '/products/add', json={
            'product_code': e['tag'] + 'P1', 'product_name': e['tag'] + '_产品',
            'drawing_number': 'D1', 'model': 'M1', 'unit': '件'})
        b = r.get_json() or {}
        c.eq('响应 success=true', b.get('success') is True, b.get('message'))
        row = c.one(M.Product, product_code=e['tag'] + 'P1')
        c.eq('产品落库', row is not None, b)
        if row:
            e['product2'] = row.id
            c.eq('unit=件', row.unit == '件', row.unit)

    def ms_product_put(c, e):
        row0 = c.by_id(M.Product, e['product2'])
        c.snap('prod', row0, ['product_name', 'specification'])
        r = c.req('PUT', f'/products/{e["product2"]}',
                  json={'product_name': e['tag'] + '_产品改', 'specification': e['tag'] + '-SPEC'})
        b = r.get_json() or {}
        c.eq('响应 success=true', b.get('success') is True, b.get('message'))
        row = c.fresh(M.Product, e['product2'])
        c.snap_after('prod', row, ['product_name', 'specification'])
        c.changed('prod', 'product_name')
        c.eq('specification 落库', row.specification == e['tag'] + '-SPEC', row.specification)

    def ms_bom(c, e):
        raw = c.one(M.RawMaterial, internal_number=e['tag_raw'])
        c.eq('前置原材料存在（本组夹具）', raw is not None, e['tag_raw'])
        if raw is None:
            return
        n0 = 0
        with c.app.app_context():
            n0 = M.ProductBOM.query.filter_by(product_id=e['product2']).count()
        r = c.req('POST', f'/products/{e["product2"]}/bom/add', json={
            'material_type': 'raw', 'material_id': raw.id,
            'quantity': 2.0, 'unit': '件', 'unit_cost': 5.0})
        with c.app.app_context():
            n1 = M.ProductBOM.query.filter_by(product_id=e['product2']).count()
        c.eq('BOM 行新增', n1 > n0, f'{n0} -> {n1} HTTP {r.status_code} '
                                    f'{r.get_data(as_text=True)[:100]}')

    def ms_process(c, e):
        n0 = 0
        with c.app.app_context():
            n0 = M.ProductProcess.query.filter_by(product_id=e['product2']).count()
        r = c.req('POST', f'/products/{e["product2"]}/processes/add', json={
            'process_id': e['process']['id'], 'sequence': 1, 'quantity': 1, 'unit_price': 10.0})
        with c.app.app_context():
            n1 = M.ProductProcess.query.filter_by(product_id=e['product2']).count()
        c.eq('工艺路线行新增', n1 > n0, f'{n0} -> {n1} HTTP {r.status_code} '
                                       f'{r.get_data(as_text=True)[:100]}')

    def ms_code_rule(c, e):
        r = c.req('POST', '/code_rules/add', json={
            'name': e['tag'] + '_规则', 'code_type': 'product', 'prefix': e['tag'],
            'format_pattern': '{prefix}{YYYYMM}{seq}', 'sequence_length': 4,
            'reset_frequency': 'never'})
        b = r.get_json() or {}
        row = c.one(M.CodeRule, name=e['tag'] + '_规则')
        c.eq('编码规则落库', row is not None,
              f'HTTP {r.status_code} {b.get("message")}')
        if row:
            c.eq('prefix 落库', row.prefix == e['tag'], row.prefix)

    def ms_notification_read(c, e):
        """POST /notifications/<id>/read（仅 login_required，无能力校验 —— 8 处之一）。

        已读在 ``notification_receivers`` 行上：``status`` unread→read + ``read_at`` 回填。
        """
        with c.app.app_context():
            from app import db
            n = M.Notification(title=e['tag'] + '_通知', content='_t4', status='unread',
                               notification_type='system', trigger_type='manual',
                               priority='normal')
            db.session.add(n)
            db.session.flush()
            recv = M.NotificationReceiver(notification_id=n.id, user_id=e['admin_id'],
                                          status='unread')
            db.session.add(recv)
            db.session.commit()
            nid, rid, before = n.id, recv.id, recv.status
        r = c.req('POST', f'/notifications/{nid}/read')
        b = r.get_json() or {}
        with c.app.app_context():
            from app import db
            db.session.expire_all()
            recv = M.NotificationReceiver.query.get(rid)
        c.snap_after('recv', recv, ['status', 'read_at'])
        c.eq('响应 success=true', b.get('success') is True, b.get('message'))
        c.eq('接收行 status=read', recv.status == 'read', f'{before} -> {recv.status}')
        c.eq('read_at 回填', recv.read_at is not None, str(recv.read_at))

    P += [
        ('misc', 'W-MSC-1', 'POST /customer/add 新增客户（落库）', ms_customer),
        ('misc', 'W-MSC-2', 'POST /products/add 新增产品（落库）', ms_product),
        ('misc', 'W-MSC-3', 'PUT /products/<id> 改产品字段（落库）', ms_product_put),
        ('misc', 'W-MSC-4', 'POST /products/<id>/bom/add 加 BOM 行（行新增）', ms_bom),
        ('misc', 'W-MSC-5', 'POST /products/<id>/processes/add 加工序（行新增）', ms_process),
        ('misc', 'W-MSC-6', 'POST /code_rules/add 建编码规则（落库）', ms_code_rule),
        ('misc', 'W-MSC-7', 'POST /notifications/<id>/read 标记已读（is_read 变化）', ms_notification_read),
    ]
    return P


# ============================================================ 环境准备
def prepare_env(app, copy_path, tag):
    """在副本里准备写断言需要的基础对象；全部打 ``tag`` 前缀，可逐条复核。"""
    from app import db
    from app import models as M
    from datetime import date
    env = {'tag': tag, 'copy': copy_path}
    with app.app_context():
        admin = M.User.query.filter_by(username='_t_admin').first() or M.User.query.first()
        emp = M.Employee.query.first()
        proc = M.ProcessPrice.query.first()
        cat = M.RawMaterialCategory.query.first()
        product = M.Product.query.first()
        routed = M.Product.query.join(M.ProductProcess, M.ProductProcess.product_id == M.Product.id)\
            .first()
        if proc is None:
            proc = M.ProcessPrice(process_code=tag + 'C1', process_name=tag + '_工序',
                                  price=10.0, version=1)
            db.session.add(proc)
            db.session.flush()
        if cat is None:
            cat = M.RawMaterialCategory(name=tag + '_品类', code=tag + 'CAT0')
            db.session.add(cat)
            db.session.flush()
        if product is None:
            product = M.Product(product_code=tag + 'P0', product_name=tag + '_产品0',
                                status='active', created_by=admin.id)
            db.session.add(product)
            db.session.flush()
        if routed is None:                       # 生产单需要工艺路线
            routed = M.Product(product_code=tag + 'RP0', product_name=tag + '_有路线产品',
                               status='active', created_by=admin.id)
            db.session.add(routed)
            db.session.flush()
            db.session.add(M.ProductProcess(product_id=routed.id, process_id=proc.id, sequence=1,
                                            quantity=1, unit_price=10.0))
        # 易耗品（带库存，供领用/使用）
        cc = M.ConsumableCategory.query.first()
        if cc is None:
            cc = M.ConsumableCategory(name=tag + '_易耗品类', code=tag + 'CC0', is_active=True)
            db.session.add(cc)
            db.session.flush()
        cons = M.Consumable(supplier=tag + '_易耗供应商', category_id=cc.id,
                            supplier_number=tag + 'CS1', specification=tag + '-SPEC',
                            internal_number=tag + 'CI0',
                            quantity=50, unit='个', unit_price=2.0, status='in_stock')
        db.session.add(cons)
        # 本组专属原材料（供 BOM/归档等断言，不跨组依赖）
        raw = M.RawMaterial(supplier=tag + '_基准供应商', category_id=cat.id,
                            supplier_number=tag + 'RS0', internal_number=tag + 'RAW0',
                            melt_number=tag + '-M0',
                            quantity=8.0, storage_date=date(2026, 10, 1), status='in_stock',
                            is_archived=False, notes=tag)
        db.session.add(raw)
        # 顾客 + 销售订单 + 在库成品（发货链）
        cust = M.Customer(customer_code=tag + 'CUS0', customer_name=tag + '_销售客户',
                          customer_type='enterprise', created_by=admin.id)
        db.session.add(cust)
        db.session.flush()
        so = M.SalesOrder(customer_id=cust.id, order_number=tag + 'SO1', created_by=admin.id,
                          order_source='_t4', year_month='2026-10')
        db.session.add(so)
        db.session.flush()
        db.session.add(M.SalesOrderItem(sales_order_id=so.id, product_id=product.id, quantity=5))
        fp = M.FinishedProduct(product_number=tag + 'FG1', production_date=date(2026, 10, 1),
                               drawing_number='_t4', model='_t4', inspector='_t4',
                               quantity=5, status='in_stock', stock_kind='fg',
                               product_id=product.id, notes=tag)
        db.session.add(fp)
        db.session.commit()
        env.update({
            'admin_id': admin.id, 'employee': {'id': emp.id, 'name': emp.name},
            'process': {'id': proc.id, 'name': proc.process_name},
            'raw_cat': cat.id, 'product': product.id, 'routed_product': routed.id,
            'consumable': cons.id, 'sales_order': so.id, 'fg_stock': fp.id, 'customer': cust.id,
            'tag_raw': tag + 'RAW0', 'raw_seed': raw.id, 'cons_sn': tag + 'CS1',
            'fixture_counts': {
                'consumables': M.Consumable.query.count(),
                'raw_material': M.RawMaterial.query.count(),
                'customers': M.Customer.query.count(),
            },
        })
    return env


def seed_task(app, tag, n):
    """任务写断言的独立探针对象（避免断言之间互相污染）。"""
    from app import db
    from app import models as M
    from datetime import date
    with app.app_context():
        emp = M.Employee.query.first()
        proc = M.ProcessPrice.query.first()
        t = M.TaskAssignment(global_sn=M.SerialNumber.get_next_number(), employee_id=emp.id,
                             process_id=proc.id, quantity=5, status='pending',
                             assigned_date=date.today(), target_date=date(2026, 12, 31),
                             notes=f'{tag}_seed{n}')
        db.session.add(t)
        db.session.commit()
        return t.id


def _model_user():
    """取 admin 行（在 app 上下文中调用）。"""
    from app import models as M
    return M.User.query.filter_by(username='_t_admin').first() or M.User.query.first()


def main():
    started = time.time()
    sha0 = sha256_file(REAL_DB)
    log('=' * 78)
    log('t4 写端点实测套件（写断言必须落在数据变化上）')
    log(f'run tag = {TAG}（探针对象自带 tag 前缀，可在副本内逐条复核）')
    log(f'[真实库] 开工 SHA256 = {sha0} 未变={sha0 == _env.REAL_DB_SHA256_EXPECTED}')
    assert_real_db_untouched('write_suite 开工')

    # **单 app 架构**：flask_sqlalchemy 3.x 的全局 db 只能 init_app 到一个 app
    # （多 app 交替 app_context 会抛 "not registered with this SQLAlchemy instance"）。
    # ⇒ 只建 1 个 app + 1 份副本；每个分组开始前把**原始副本**拷回来（文件级重置），
    #   这样「组间状态隔离」靠文件而不是靠多 app。
    # ⚠ 断言工厂必须在建 app **之后**调用：app/__init__.py 在模块导入时就建 SQLAlchemy，
    #   早于 make_app() 的「清 sys.modules 再重建」会让断言闭包里的模型绑到旧实例。
    import _test_bootstrap
    import shutil
    app, copy_path = fixtures.make_isolated_app('write')
    from app import db
    _db = db
    probes = build_probes()
    groups = []
    for g, _, _, _ in probes:
        if g not in groups:
            groups.append(g)
    log(f'[断言] {len(probes)} 条 / {len(groups)} 组 {groups}')
    copy_path = os.path.normpath(copy_path)
    real_path = os.path.normpath(REAL_DB)
    ok_iso = os.path.normcase(copy_path) != os.path.normcase(real_path)
    if not ok_iso:
        raise AssertionError(f'副本隔离失败：{copy_path} 与真实库同文件')
    pristine = os.path.join(os.path.dirname(os.path.dirname(copy_path)),
                            'pristine_' + os.path.basename(copy_path))
    log(f'[副本] URI={app.config.get("SQLALCHEMY_DATABASE_URI")}')
    log(f'[副本] 文件={copy_path}')
    log(f'[副本] 与真实库同文件={os.path.samefile(copy_path, real_path)} '
        f'（应用级硬闸在本仓不存在，故此处独立复核）')

    from _test_bootstrap import login_as
    users, pw = _test_bootstrap.ensure_role_users(app)
    _test_bootstrap.seed_fixtures(app)
    log(f'[身份] admin={users["admin"]} / 7 角色已建（{", ".join(users.values())}）')
    # ⚠ 重置源必须在**建好 7 个测试账号与样本数据之后**再拷：
    #   否则每次分组重置会把测试账号一起回滚掉，登录态失效（实测 401「请先登录」）。
    with app.app_context():
        _db.session.remove()
        _db.engine.dispose()
    shutil.copy2(copy_path, pristine)
    log(f'[副本] 重置源={pristine}（含 7 账号 + 样本数据）')

    groups_result = {}
    for g in groups:
        # ---- 分组级重置：把原始副本拷回来（先断开连接池）
        with app.app_context():
            _db.session.remove()
            _db.engine.dispose()
        shutil.copy2(pristine, copy_path)
        with app.app_context():
            n_rules = db.session.execute(db.text(
                'SELECT COUNT(*) FROM task_assignment')).scalar()
        assert_real_db_untouched(f'write_suite 组 {g} 重置后')
        # 重置后必须重新登录：整库回滚会重建 user 行，旧 session 的 user_id 可能已失效
        client = app.test_client()
        with app.app_context():
            admin_user = _model_user()
            admin_name = admin_user.username
        r_login = login_as(client, admin_name, pw)
        login_ok = r_login.status_code == 302
        probe_ok = client.get('/tasks').status_code
        if login_ok and probe_ok != 200:
            log(f'  !! 登录后 GET /tasks = {probe_ok}（会话未生效，本组断言无效）')
        tag = f'{TAG}_{g}'
        env = prepare_env(app, copy_path, tag)
        env['tag'] = tag
        log(f'  夹具计数（建完 env 后）：{env.get("fixture_counts")}')
        _n_seed = {'n': 0}

        def _seed(kind, _app=app, _tag=tag):
            _n_seed['n'] += 1
            if kind == 'task':
                return seed_task(_app, _tag, _n_seed['n'])
            raise KeyError(kind)

        env['seed'] = _seed
        log('')
        log(f'--- 组 {g}（副本已重置为原始副本；task_assignment 基线行数={n_rules}；'
            f'重新登录={login_ok}）')
        for gg, pid, title, fn in probes:
            if gg != g:
                continue
            c = Ctx(app, client, g, pid)
            t0 = time.time()
            try:
                fn(c, env)
            except Exception as ex:
                import traceback
                c.eq('断言执行未抛异常', False, f'{ex.__class__.__name__}: {ex}')
                c.notes.append(traceback.format_exc()[-400:])
            passed = all(ch['ok'] for ch in c.checks) and bool(c.checks)
            rec = {
                'id': pid, 'group': g, 'title': title, 'passed': passed,
                'checks': c.checks, 'db_delta': c.delta(), 'response': c.resp,
                'notes': c.notes, 'duration_s': round(time.time() - t0, 2),
                'probe_prefix': tag,
            }
            _RESULTS.append(rec)
            log(f'  [{"PASS" if passed else "FAIL"}] {pid} {title}')
            log(f'         HTTP {c.resp.get("code")} {c.resp.get("method")} {c.resp.get("url")}')
            for ch in c.checks:
                mark = 'ok' if ch['ok'] else 'NG'
                log(f'         - {mark}: {ch["check"]}'
                    + (f'  ({ch.get("detail")})' if ch.get('detail') is not None else ''))
            for lab, d in c.delta().items():
                for f, (b, a) in d.items():
                    log(f'         Δ {lab}.{f}: {b!r} -> {a!r}')
            for n in c.notes:
                log(f'         note: {n}')
        with app.app_context():
            counts = {}
            q = db.session.execute(db.text(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")).fetchall()
            for (tname,) in q:
                try:
                    n = db.session.execute(db.text(f'SELECT COUNT(*) FROM {tname}')).scalar()
                except Exception:
                    n = None
                counts[tname] = n
        groups_result[g] = {'copy': copy_path, 'row_counts_after_group': counts}
        assert_real_db_untouched(f'write_suite 组 {g} 收尾')

    sha1 = sha256_file(REAL_DB)
    n_pass = sum(1 for r in _RESULTS if r['passed'])
    out = {
        'task': 't4', 'suite': 'write_suite', 'run_tag': TAG,
        'started_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'probe_count': len(_RESULTS), 'passed': n_pass, 'failed': len(_RESULTS) - n_pass,
        'real_db_sha256_before': sha0, 'real_db_sha256_after': sha1,
        'real_db_unchanged': sha1 == _env.REAL_DB_SHA256_EXPECTED,
        'groups': groups_result, 'results': _RESULTS,
        'duration_s': round(time.time() - started, 1),
    }
    log('')
    log('=' * 78)
    log(f'写断言合计 {len(_RESULTS)} 条：PASS {n_pass} / FAIL {len(_RESULTS) - n_pass}')
    log(f'真实库收尾 SHA256 = {sha1} 未变={out["real_db_unchanged"]}')
    log(f'耗时 {out["duration_s"]}s')
    os.makedirs(EVID, exist_ok=True)
    with open(os.path.join(EVID, 'write_suite.json'), 'w', encoding='utf-8', newline='\n') as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(EVID, 'write_suite.out.txt'), 'w', encoding='utf-8', newline='\n') as fh:
        fh.write('\n'.join(_LOG) + '\n')
    log(f'[落盘] {EVID}/write_suite.json + write_suite.out.txt')
    return 0


if __name__ == '__main__':
    sys.exit(main())
