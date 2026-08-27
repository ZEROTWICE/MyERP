"""全角色 GET 路由冒烟测试。

对每个角色（含匿名）访问所有 GET 路由，记录状态码、重定向链、服务端异常。
带参数的路由用库里真实存在的 ID 填充；取不到 ID 的路由跳过并单独列出。
"""
import collections
import json
import sys
import traceback

from _test_bootstrap import make_app, ensure_role_users, login_as, seed_fixtures, ROLES

SKIP = {'/auth/logout', '/auth/register', '/bootstrap/static/<path:filename>'}

# 带参路由的参数 -> 取值来源（模型名, 主键列）
ID_SOURCES = {
    'customer_id': ('Customer', 'id'),
    'address_id': ('CustomerAddress', 'id'),
    'process_id': ('ProcessPrice', 'id'),
    'item_id': None,          # 多义，按路由前缀区分，见 resolve_args
    'record_id': None,
    'task_id': None,
    'template_id': ('InspectionTemplate', 'id'),
    'order_id': None,
    'id': None,
    'rule_id': ('CodeRule', 'id'),
    'category_id': None,
    'employee_id': ('Employee', 'id'),
    'batch_id': ('ProductionBatch', 'id'),
    'product_id': ('Product', 'id'),
    'bom_item_id': ('ProductBOM', 'id'),
    'process_item_id': ('ProductProcess', 'id'),
    'notification_id': ('Notification', 'id'),
    'log_id': ('AuditLog', 'id'),
}

# 按路由路径前缀消歧
PATH_MODEL = [
    ('/api/production_center/items/', 'ProductionBatchItem'),
    ('/production_center/items/', 'ProductionBatchItem'),
    ('/api/quality/records/', 'InspectionRecord'),
    ('/api/quality/tasks/', 'InspectionTask'),
    ('/quality/inspection/', 'InspectionRecord'),
    ('/quality/tasks/', 'InspectionTask'),
    ('/api/sales_orders/', 'SalesOrder'),
    ('/sales_order_item/', 'SalesOrderItem'),
    ('/sales_order/', 'SalesOrder'),
    ('/bonus_penalties/', 'BonusPenalty'),
    ('/consumables/categories/', 'ConsumableCategory'),
    ('/consumables/', 'Consumable'),
    ('/inventory/finished/', 'FinishedProduct'),
    ('/inventory/raw-material/categories/', 'RawMaterialCategory'),
    ('/inventory/raw/', 'RawMaterial'),
    ('/material_requisitions/', 'MaterialRequisition'),
    ('/process_prices/', 'ProcessPrice'),
    ('/production_orders/', 'ProductionOrder'),
    ('/products/', 'Product'),
    ('/employees/', 'Employee'),
    ('/tasks/assignment/', 'TaskAssignment'),
    ('/tasks/', 'TaskAssignment'),
]


def first_ids(app):
    """预取每个模型的第一个 id。"""
    from app import models
    ids = {}
    with app.app_context():
        names = {m for _, m in PATH_MODEL}
        names |= {v[0] for v in ID_SOURCES.values() if v}
        for name in sorted(names):
            model = getattr(models, name, None)
            if model is None:
                ids[name] = ('MISSING_MODEL', None)
                continue
            try:
                row = model.query.order_by(model.id.asc()).first()
                ids[name] = ('ok', row.id if row else None)
            except Exception as e:
                ids[name] = (f'ERR {e.__class__.__name__}', None)
    return ids


def resolve_url(rule, ids):
    path = str(rule)
    for arg in rule.arguments:
        model = None
        for prefix, m in PATH_MODEL:
            if path.startswith(prefix):
                model = m
                break
        src = ID_SOURCES.get(arg)
        if src:
            model = src[0]
        if model is None:
            return None, f'无法确定 {arg} 的模型'
        state, value = ids.get(model, ('UNKNOWN', None))
        if value is None:
            return None, f'{model} 无数据({state})'
        path = path.replace(f'<int:{arg}>', str(value))
    if '<' in path:
        return None, '存在未替换的参数'
    return path, None


def run():
    app, db_path = make_app()
    users, password = ensure_role_users(app)
    seeded = seed_fixtures(app)
    print(f'[seed] 补齐样本数据: {seeded}')
    ids = first_ids(app)

    print('[ids] 参数取值来源:')
    for k, (state, v) in sorted(ids.items()):
        print(f'   {k:26s} {state:16s} id={v}')

    targets = []
    unresolved = []
    for rule in app.url_map.iter_rules():
        if rule.endpoint == 'static' or 'GET' not in rule.methods:
            continue
        if str(rule) in SKIP:
            continue
        if rule.arguments:
            url, why = resolve_url(rule, ids)
            if url is None:
                unresolved.append((str(rule), why))
                continue
            targets.append((f'{rule} [{rule.endpoint}]', url, rule.endpoint))
        else:
            targets.append((f'{rule} [{rule.endpoint}]', str(rule), rule.endpoint))
    targets.sort()

    print(f'\n[plan] 可测 GET 路由 {len(targets)} 条，跳过 {len(unresolved)} 条')
    for r, why in sorted(unresolved):
        print(f'   SKIP {r}  ({why})')

    results = collections.defaultdict(dict)
    errors = []

    actors = [('anonymous', None)] + [(r, users[r]) for r in ROLES]

    for actor, username in actors:
        client = app.test_client()
        if username:
            resp = login_as(client, username, password)
            if resp.status_code != 302:
                print(f'!! 登录失败 {actor}: {resp.status_code}')
                continue
        for rule_str, url, endpoint in targets:
            try:
                r = client.get(url, follow_redirects=False)
                code = r.status_code
                loc = r.headers.get('Location', '')
                # 跟随重定向，检测死循环
                hops = 0
                cur = r
                seen = []
                while cur.status_code in (301, 302, 303, 307, 308) and hops < 12:
                    nxt = cur.headers.get('Location', '')
                    seen.append(nxt)
                    cur = client.get(nxt, follow_redirects=False)
                    hops += 1
                final = cur.status_code
                looped = hops >= 12
                results[actor][rule_str] = (code, final, hops, looped, loc)
                if looped:
                    errors.append((actor, rule_str, 'REDIRECT_LOOP', ' -> '.join(seen[:6])))
                if final >= 500:
                    body = cur.get_data(as_text=True)
                    errors.append((actor, rule_str, f'HTTP {final}', body[-400:].replace('\n', ' ')))
            except Exception as e:
                tb = traceback.format_exc()
                results[actor][rule_str] = ('EXC', e.__class__.__name__, 0, False, '')
                errors.append((actor, rule_str, 'EXCEPTION',
                               f'{e.__class__.__name__}: {e} || ' + tb.strip().splitlines()[-1]))
        print(f'[done] {actor}: {len(results[actor])} 条')

    print('\n================ 异常汇总 ================')
    if not errors:
        print('无 5xx / 异常 / 重定向死循环')
    for actor, rule_str, kind, detail in errors:
        print(f'  [{kind}] {actor:10s} {rule_str}')
        print(f'          {detail}')

    with open('../_smoke_results.json', 'w', encoding='utf-8') as f:
        json.dump({a: {k: list(v) for k, v in d.items()} for a, d in results.items()},
                  f, ensure_ascii=False, indent=1)
    print(f'\n明细已写入 _smoke_results.json（{len(errors)} 个问题）')
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(run())
