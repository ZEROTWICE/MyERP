"""列出全部路由，按是否带参数、方法分类，并检测重复注册。"""
import collections
import sys

from _test_bootstrap import make_app


def main():
    app, _ = make_app()
    rules = list(app.url_map.iter_rules())

    by_rule = collections.defaultdict(list)
    for r in rules:
        for m in sorted(r.methods - {'HEAD', 'OPTIONS'}):
            by_rule[(m, str(r))].append(r.endpoint)

    dup = {k: v for k, v in by_rule.items() if len(v) > 1}
    print(f'[routes] total rules={len(rules)}')
    print(f'[routes] duplicate (method,path) registrations={len(dup)}')
    for (m, p), eps in sorted(dup.items()):
        print(f'  DUP {m} {p} -> {eps}')

    simple_get = sorted(str(r) for r in rules
                        if 'GET' in r.methods and not r.arguments and r.endpoint != 'static')
    param_get = sorted(f'{r} <- {sorted(r.arguments)}' for r in rules
                       if 'GET' in r.methods and r.arguments and r.endpoint != 'static')
    post_only = sorted(str(r) for r in rules if 'GET' not in r.methods)

    print(f'[routes] GET no-arg={len(simple_get)} GET with-arg={len(param_get)} non-GET={len(post_only)}')
    for p in simple_get:
        print(f'  GET  {p}')
    print('--- GET with args ---')
    for p in param_get:
        print(f'  GET  {p}')
    print('--- non-GET ---')
    for p in post_only:
        print(f'  ---  {p}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
