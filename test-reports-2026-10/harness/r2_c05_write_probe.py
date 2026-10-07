"""r2_c05_write_probe.py — C-05「写端点命中补强」探针（V-06 / B3，文件独占：本任务新增）。

**为什么需要它**：`measure_coverage.py` 的覆盖分子只统计 **`PROBES` 白名单内**脚本的
`client.<method>('<字面量 URL>')` 调用（A-83：白名单是写死的 8 个文件）。实测基线：
`writable_literal_covered_by_all = 6` / `writable_any_covered_by_all = 14` /
`len(uncovered_writable) = 101`（即 **101 条写端点零命中**）。本探针把 101 条逐条真发一次请求，
并把「站点 → 真实状态码」全部留证。

**口径（必须与 `measure_coverage.py` 的 AST 口径一致）**：URL 必须出现在**显式调用点**上
（`c.post('/x/1')` / `c.post(f'/x/{rid}')`），不能放在列表里循环 —— 后者 AST 扫不到，等于没覆盖。
本文件因此对 103 个 (方法, 规则) 站点逐条写死调用点：
* **literal**（`'/x/1'`）：保证字面量口径命中（`writable_literal_covered_by_all`）；
* **dynamic**（`f'/x/{rid}'`）：真 id 复核行为（`writable_any_covered_by_all`），仅用于状态相关链路。

**只读与隔离**：一切请求打在 `fixtures.make_isolated_app()` 的**副本库**上（CH-2），
真实库 `app.db` 前后各复核一次 SHA256；破坏性端点（DELETE/archive/delete…）的副作用只落副本。

**命中 ≠ 断言（C-05 的「不能证明什么」，见 `35` §4）**：本探针只证明「端点被真实请求到且返回了
某个状态码」；状态码分布（含 4xx/5xx）逐条留证，**不并入 HIT**。端点行为正确性归 `V-05`/`V-10`/`V-14`
的断言面。

运行（仓库根目录，绝对路径解释器；A-7）：

    $env:HARNESS_RUN_ID='r2-exec-b3-v06'
    & 'F:\\Miniconda\\envs\\wage\\python.exe' -B test-reports-2026-10\\harness\\r2_c05_write_probe.py
"""
import argparse
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

for _stream in (sys.stdout, sys.stderr):   # A-14：GBK 控制台下不得把「判据失败」与「崩溃」混为一谈
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from _env import EVIDENCE_DIR, REPO_ROOT, ensure_dir, real_db_status, save_evidence   # noqa: E402
import fixtures   # noqa: E402  必须在 make_isolated_app() 之前 import 模块本身（app.* 延迟导入）

RUN_ID = os.environ.get('HARNESS_RUN_ID') or 'adhoc-c05'

#: 通用 JSON 体（覆盖常见键名；端点自会忽略多余键）
J = {
    'name': '_c05', 'code': '_c05', 'title': '_c05', 'description': '_c05',
    'template_name': '_c05', 'template_code': '_c05', 'type': 'production_record',
    'quantity': 1, 'status': 'pending', 'notes': '_c05 写端点命中探针',
    'price': 1, 'version': 1, 'unit': '件', 'spec': '_c05',
    'drawing_number': '_c05', 'model': '_c05', 'production_date': '2026-10-07',
    'inspector': '_c05', 'product_number_type': 'manual', 'product_number': '_c05PN',
    'material_type': 'raw', 'reason': '_c05', 'amount': 1, 'data': {}, 'items': [],
    'ids': [], 'employee_ids': [1], 'process_id': 1, 'order_id': 1, 'id': 1,
}
#: 通用表单体
F = {
    'name': '_c05', 'code': '_c05', 'title': '_c05', 'notes': '_c05 写端点命中探针',
    'quantity': '1', 'status': 'pending', 'price': '1', 'version': '1', 'unit': '件',
    'spec': '_c05', 'process_code': '_c05P1', 'process_name': '_c05 工序',
    'drawing_number': '_c05', 'model': '_c05', 'production_date': '2026-10-07',
    'inspector': '_c05', 'product_number_type': 'manual', 'product_number': '_c05PN',
    'employee_id': '1', 'product_id': '1', 'customer_id': '1', 'order_id': '1',
    'material_type': 'raw', 'reason': '_c05', 'amount': '1', 'id': '1',
}
#: 上传体（导入端点：解析必然失败，但请求形状与落盘路径被真实走到）
UPLOAD_BODY = b'_c05 not-a-real-xlsx'


def upload():
    """**每次调用返回新的文件对象**：`io.BytesIO` 被上一次请求消费后会关闭
    （实测症状：`ValueError: I/O operation on closed file` 被记成 8 条假异常）。"""
    return {'file': (io.BytesIO(UPLOAD_BODY), '_c05.xlsx')}

#: 表 -> 主键（真 id 复核用；表不存在或为空 => None）
ID_TABLES = (
    ('product', 'products'), ('bom', 'product_bom'), ('pp', 'process_price'),
    ('employee', 'employee'), ('customer', 'customers'), ('address', 'customer_addresses'),
    ('so', 'sales_orders'), ('soi', 'sales_order_items'), ('po', 'production_orders'),
    ('batch', 'production_batches'), ('item', 'production_batch_items'),
    ('raw', 'raw_material'), ('fp', 'finished_product'), ('rmcat', 'raw_material_categories'),
    ('cons', 'consumables'), ('conscat', 'consumable_categories'), ('wp', 'workpieces'),
    ('itask', 'inspection_tasks'), ('irec', 'inspection_records'), ('nc', 'nonconformity_records'),
    ('tpl', 'inspection_templates'), ('notif', 'notifications'), ('alog', 'audit_log'),
    ('rule', 'code_rule'), ('preq', 'purchase_requisitions'), ('pord', 'purchase_orders'),
    ('gr', 'goods_receipts'), ('ship', 'shipments'), ('wc', 'work_centers'),
    ('equip', 'equipment'), ('bp', 'bonus_penalty'), ('mreq', 'material_requisitions'),
    ('mret', 'material_returns'), ('icnt', 'inventory_counts'), ('heat', 'heat_lots'),
    ('prec', 'production_record'), ('parule', 'process_assignment_rules'),
    ('pitem', 'purchase_order_items'), ('pproc', 'product_processes'),
)


class Recorder:
    """把 ``test_client`` 包一层：记录 (方法, 路径, 状态码, 响应片段) 并原样返回响应。

    * 类内部的 ``getattr(self._c, method)`` **不是** ``<obj>.<http_method>(...)`` 形态 ⇒
      `measure_coverage` 的 AST 收集器不会把包装器自身算成命中（无自指假阳性）。
    * 400/415（内容类型不符）时**自动换另一种内容类型重试一次**并同样留痕：
      不逐 handler 研究 form/json 也能让请求走到真实分支。
    """

    def __init__(self, client, log=()):
        self._c = client
        self.calls = list(log)

    def _do(self, method, url, **kw):
        resp = None
        try:
            resp = getattr(self._c, method)(url, **kw)
            status, body = resp.status_code, resp.get_data(as_text=True)[:160]
        except Exception as exc:                    # 探针不得因单条请求整体崩
            status, body = 'EXC:' + exc.__class__.__name__, str(exc)[:160]
        self.calls.append({'method': method.upper(), 'url': url, 'status': status, 'body': body})
        # 只在 **415（内容类型不符）** 时换另一种内容类型重试一次：400/422 是「内容类型对了、
        # 载荷被校验拒绝」⇒ 已在真实分支上，再试一次只会把最终状态污染成 415。
        if isinstance(status, int) and status == 415:
            alt = {'data': F} if 'json' in kw else {'json': J}
            if 'data' in kw and 'file' in (kw.get('data') or {}):
                return resp                            # 上传体不换内容类型
            try:
                resp2 = getattr(self._c, method)(url, **alt)
                self.calls.append({'method': method.upper(), 'url': url + ' [alt-content-type]',
                                   'status': resp2.status_code,
                                   'body': resp2.get_data(as_text=True)[:160]})
            except Exception as exc:
                self.calls.append({'method': method.upper(), 'url': url + ' [alt-content-type]',
                                   'status': 'EXC:' + exc.__class__.__name__, 'body': str(exc)[:160]})
        return resp

    def get(self, url, **kw):
        return self._do('get', url, **kw)

    def post(self, url, **kw):
        return self._do('post', url, **kw)

    def put(self, url, **kw):
        return self._do('put', url, **kw)

    def delete(self, url, **kw):
        return self._do('delete', url, **kw)


def copy_ids(app):
    """从副本库取各类首行主键（真 id 复核用）。"""
    from app import db
    out = {}
    with app.app_context():
        for key, table in ID_TABLES:
            try:
                row = db.session.execute(
                    db.text('SELECT id FROM "%s" ORDER BY id LIMIT 1' % table)).fetchone()
                out[key] = int(row[0]) if row and row[0] is not None else None
            except Exception:
                out[key] = None
    return out


def sweep(c, i):
    """**103 个 (方法, 规则) 站点逐条写死调用点** —— 顺序：新建/更新在前，破坏性在后。

    ``i`` = 副本里的真主键字典；缺失（None）时该条 f-string 复核调用跳过（判据只看字面量站点）。
    """
    # ================= A. /api/*（14 规则 / 16 站点，JSON 面） =================
    c.post('/api/quality/templates', json=J)
    c.put('/api/quality/templates/1', json=J)
    if i.get('tpl'):
        c.put(f"/api/quality/templates/{i['tpl']}", json=J)
    c.post('/api/quality/tasks', json=J)
    c.put('/api/quality/tasks/1', json=J)
    if i.get('itask'):
        c.put(f"/api/quality/tasks/{i['itask']}", json=J)
        c.post(f"/api/quality/tasks/{i['itask']}/start-inspection", json=J)
    c.post('/api/quality/tasks/1/start-inspection', json=J)
    c.post('/api/quality/records/1/submit', json=J)
    if i.get('irec'):
        c.post(f"/api/quality/records/{i['irec']}/submit", json=J)
    c.post('/api/quality/tasks/import', data=upload(), content_type='multipart/form-data')
    c.post('/api/quality/nonconformities/1/dispose', json=J)
    if i.get('nc'):
        c.post(f"/api/quality/nonconformities/{i['nc']}/dispose", json=J)
    c.post('/api/production_center/create_instances', json=J)
    c.post('/api/production_center/items/1/tech_decomposition', json=J)
    c.post('/api/production_center/items/1/execute_operation', json=J)
    if i.get('item'):
        c.post(f"/api/production_center/items/{i['item']}/tech_decomposition", json=J)
        c.post(f"/api/production_center/items/{i['item']}/execute_operation", json=J)
    c.post('/api/production/generate-codes', json=J)
    c.post('/api/process_assignment/1', json=J)
    c.post('/api/process_assignment/bulk', json=J)
    if i.get('pp'):
        c.post(f"/api/process_assignment/{i['pp']}", json=J)

    # ================= B. /inventory/*（14 规则 / 14 站点，JSON 面） =================
    c.post('/inventory/finished/add', json=J)
    c.post('/inventory/raw/add', json=J)
    c.put('/inventory/finished/1', json=J)
    c.put('/inventory/raw/1', json=J)
    if i.get('raw'):
        c.put(f"/inventory/raw/{i['raw']}", json=J)
    if i.get('fp'):
        c.put(f"/inventory/finished/{i['fp']}", json=J)
    c.post('/inventory/auto-archive', json=J)
    c.post('/inventory/raw-material/categories/add', json=J)
    c.put('/inventory/raw-material/categories/1', json=J)
    if i.get('rmcat'):
        c.put(f"/inventory/raw-material/categories/{i['rmcat']}", json=J)
    c.post('/inventory/finished/import', data=upload(), content_type='multipart/form-data')
    c.post('/inventory/raw/import', data=upload(), content_type='multipart/form-data')
    c.post('/inventory/finished/1/archive', json=J)
    c.post('/inventory/raw/1/archive', json=J)
    if i.get('raw'):
        c.post(f"/inventory/raw/{i['raw']}/archive", json=J)
    if i.get('fp'):
        c.post(f"/inventory/finished/{i['fp']}/archive", json=J)
    c.delete('/inventory/raw/1')
    c.delete('/inventory/finished/1')
    c.delete('/inventory/raw-material/categories/1')

    # ================= C. /products/*（10 规则 / 10 站点） =================
    c.post('/products/add', data=F)
    c.put('/products/1', data=F)
    if i.get('product'):
        c.put(f"/products/{i['product']}", data=F)
    c.post('/products/1/bom/add', data=F)
    c.put('/products/1/bom/1', data=F)
    c.post('/products/1/processes/add', data=F)
    c.put('/products/1/processes/1', data=F)
    c.post('/products/import', data=upload(), content_type='multipart/form-data')
    if i.get('product') and i.get('bom'):
        c.put(f"/products/{i['product']}/bom/{i['bom']}", data=F)
    if i.get('product') and i.get('pproc'):
        c.put(f"/products/{i['product']}/processes/{i['pproc']}", data=F)
    c.delete('/products/1/bom/1')
    c.delete('/products/1/processes/1')
    c.delete('/products/1')

    # ================= D. /consumables/*（6 规则 / 6 站点） =================
    c.post('/consumables/categories/add', data=F)
    c.put('/consumables/categories/1', data=F)
    if i.get('conscat'):
        c.put(f"/consumables/categories/{i['conscat']}", data=F)
    c.put('/consumables/1', data=F)
    if i.get('cons'):
        c.put(f"/consumables/{i['cons']}", data=F)
        c.post(f"/consumables/{i['cons']}/use", data=F)
    c.post('/consumables/1/use', data=F)
    c.delete('/consumables/1')
    c.delete('/consumables/categories/1')

    # ================= E. 制造/采购/发货/库存域（equipment/purchase/shipment/heat_lot/stock 面） ===
    c.post('/equipment/save', json=J)
    c.post('/equipment/1/downtime', json=J)
    c.post('/equipment/1/resume', json=J)
    if i.get('equip'):
        c.post(f"/equipment/{i['equip']}/downtime", json=J)
        c.post(f"/equipment/{i['equip']}/resume", json=J)
    c.post('/work_centers/save', json=J)
    c.post('/heat_lots/create', json=J)
    c.post('/heat_lots/1/charge', json=J)
    c.post('/heat_lots/1/fire', json=J)
    c.post('/heat_lots/1/unload', json=J)
    c.post('/suppliers/save', json=J)
    c.post('/purchase_requisitions/save', json=J)
    c.post('/purchase_requisitions/1/approve', json=J)
    c.post('/purchase_requisitions/1/convert', json=J)
    c.post('/purchase_orders/save', json=J)
    c.post('/purchase_orders/1/receive', json=J)
    if i.get('pord'):
        c.post(f"/purchase_orders/{i['pord']}/receive", json=J)
        c.post(f"/purchase_orders/{i['pord']}/settle", json=J)
    c.post('/purchase_orders/1/settle', json=J)
    c.post('/goods_receipts/1/putaway', json=J)
    c.post('/goods_receipts/1/nonconformity', json=J)
    c.post('/shipments/create', json=J)
    c.post('/shipments/1/add_item', json=J)
    c.post('/shipments/1/ship', json=J)
    c.post('/shipments/1/sign', json=J)
    if i.get('ship'):
        c.post(f"/shipments/{i['ship']}/add_item", json=J)
        c.post(f"/shipments/{i['ship']}/ship", json=J)
        c.post(f"/shipments/{i['ship']}/sign", json=J)

    # ================= F. 其余域（原「其余 43 条」，按组登记抽样率） =================
    c.post('/bonus_penalties/add', data=F)
    c.post('/bonus_penalties/1/edit', data=F)
    c.post('/bonus_penalties/1/update', data=F)
    c.post('/employees/import', data=upload(), content_type='multipart/form-data')
    c.post('/process_prices/import', data=upload(), content_type='multipart/form-data')
    c.post('/production_records/import', data=upload(), content_type='multipart/form-data')
    c.post('/bonus_penalties/import', data=upload(), content_type='multipart/form-data')
    c.post('/tasks/import', data=upload(), content_type='multipart/form-data')
    c.post('/add_salary_change', data=F)
    c.post('/delete_salary_change', data=F)
    c.post('/audit_logs/rollback/1', data=F)
    c.post('/tasks/1/edit', data=F)
    c.post('/code_rules/1/generate', data=F)
    c.post('/code_rules/1/delete', data=F)
    c.put('/production_batch_items/1/update', data=F)
    c.put('/production_batches/1/status', data=F)
    if i.get('item'):
        c.put(f"/production_batch_items/{i['item']}/update", data=F)
    if i.get('batch'):
        c.put(f"/production_batches/{i['batch']}/status", data=F)
    c.post('/production_orders/1/batches/add', data=F)
    if i.get('po'):
        c.post(f"/production_orders/{i['po']}/batches/add", data=F)
    c.post('/sales_order/1/create_production_order', data=F)
    c.post('/sales_order_item/1/create_production_order', data=F)
    if i.get('so'):
        c.post(f"/sales_order/{i['so']}/create_production_order", data=F)
    if i.get('soi'):
        c.post(f"/sales_order_item/{i['soi']}/create_production_order", data=F)
    c.post('/customer/1/address/1/set_primary', data=F)
    if i.get('customer') and i.get('address'):
        c.post(f"/customer/{i['customer']}/address/{i['address']}/set_primary", data=F)
    c.post('/notifications/1/read', data=F)
    c.post('/material_requisitions/1/approve', data=F)
    c.post('/material_requisitions/1/reject', data=F)
    c.post('/material_requisitions/1/cancel', data=F)
    if i.get('mreq'):
        c.post(f"/material_requisitions/{i['mreq']}/approve", data=F)
        c.post(f"/material_requisitions/{i['mreq']}/reject", data=F)
        c.post(f"/material_requisitions/{i['mreq']}/cancel", data=F)
    c.post('/material_returns/1/confirm', data=F)
    c.post('/material_returns/1/reject', data=F)
    c.post('/inventory_counts/1/cancel', data=F)
    # --- 破坏性：放在最后（副作用只落副本）；**先删被依赖行，再删员工/工价** ——
    #     否则「先删 employee 再删引用它的奖惩行」会造出假异常（`record.employee.name` -> NoneType）
    c.delete('/bonus_penalty/1')
    c.delete('/delete_production_record/1')
    c.delete('/process_price/1')
    c.delete('/production_orders/1')
    c.delete('/customer/1/delete')
    c.delete('/customer/1/address/1/delete')
    c.delete('/sales_order/1/delete')
    c.delete('/sales_order_item/1/delete')
    if i.get('prec'):
        c.delete(f"/delete_production_record/{i['prec']}")
    c.delete('/employee/1')
    if i.get('employee'):
        c.delete(f"/employee/{i['employee']}")


def summarise(calls):
    """状态分布 / 5xx 清单 / 逐前缀计数 / 每站点**最终**状态（人读 + 机读两用）。"""
    dist, fivexx, by_prefix, final = {}, [], {}, {}
    for row in calls:
        key = str(row['status'])
        dist[key] = dist.get(key, 0) + 1
        url = row['url'].replace(' [alt-content-type]', '')
        final[url] = row['status']          # 同名站点后发者覆盖 => 最终状态
        if isinstance(row['status'], int) and row['status'] >= 500:
            fivexx.append({'method': row['method'], 'url': row['url'], 'status': row['status'],
                           'body': row['body']})
        seg = url.split('?')[0].split('/')
        prefix = '/' + (seg[1] if len(seg) > 1 and seg[1] else '')
        by_prefix[prefix] = by_prefix.get(prefix, 0) + 1
    exc = {u: s for u, s in final.items() if isinstance(s, str)}
    unresolved = {u: s for u, s in final.items() if s == 415}
    return {'requests': len(calls), 'distinct_urls': len(final),
            'status_distribution': dict(sorted(dist.items())),
            'http_5xx_count': len(fivexx), 'http_5xx': fivexx,
            'exception_count': len(exc), 'exceptions': exc,
            'unresolved_415_count': len(unresolved), 'unresolved_415': unresolved,
            'by_prefix': dict(sorted(by_prefix.items()))}


def main():
    ap = argparse.ArgumentParser(description='C-05 写端点命中探针（V-06）')
    ap.add_argument('--copy-tag', default='c05write')
    args = ap.parse_args()

    before = real_db_status()
    app, copy_path = fixtures.make_isolated_app(args.copy_tag)
    fixtures.seed_all(app)
    fixtures._base_objects(app)
    fixtures.seed_material_ledger(app, rows=3, qty=5.0)
    fixtures.seed_shipment(app, quantity=7, kind='fg')
    fixtures.seed_purchase_order(app, items=2)
    fixtures.seed_qc_gate(app)
    fixtures.seed_salary(app)
    ids = copy_ids(app)

    client = app.test_client()
    log = []
    client.post('/auth/login', data={'username': '_t_admin', 'password': 'test_pw_123'})
    c = Recorder(client, log=log)
    sweep(c, ids)

    summary = summarise(c.calls)
    after = real_db_status()
    payload = {
        'harness': 'r2_c05_write_probe.py',
        'run_id': RUN_ID,
        'interpreter': sys.executable,
        'isolation': {'db_copy': copy_path, 'uri': app.config['SQLALCHEMY_DATABASE_URI']},
        'target_sites': 103,
        'note': ('字面量调用点 = measure_coverage 的 literal 口径；f-string 调用点 = dynamic 口径。'
                 '命中 ≠ 断言：状态码分布逐条留证，行为正确性归 V-05/V-10/V-14'),
        'ids_used': ids,
        'summary': summary,
        'calls': c.calls,
        'real_db': {'before': before, 'after': after,
                    'unchanged': before['sha256'] == after['sha256']},
    }
    ensure_dir(EVIDENCE_DIR)
    path = save_evidence('r2_c05_write_probe.json',
                         json.dumps(payload, ensure_ascii=False, indent=1))

    print(f"[c05] RUN_ID={RUN_ID} copy={copy_path}")
    print(f"[c05] 站点请求={summary['requests']}（去重 URL {summary['distinct_urls']}）"
          f" 状态分布={summary['status_distribution']}")
    print(f"[c05] 5xx={summary['http_5xx_count']} 异常={summary['exception_count']} "
          f"最终仍 415={summary['unresolved_415_count']}；real.db unchanged="
          f"{payload['real_db']['unchanged']}")
    print(f"[c05] 逐前缀计数={summary['by_prefix']}")
    print(f"[c05] 证据 -> {path}")
    print('[c05] RESULT: %s' % ('OK' if summary['requests'] >= 103 and payload['real_db']['unchanged']
                                else 'FAILED'))
    return 0 if (summary['requests'] >= 103 and payload['real_db']['unchanged']) else 1


if __name__ == '__main__':
    sys.exit(main())
