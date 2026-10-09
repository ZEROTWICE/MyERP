"""列出全部路由，按是否带参数、方法分类，并检测重复注册。

**退出码语义（E-03 分类：报告型 ⇒ 恒 0，不得进 CI 门禁链）**

本脚本 stdout 全是**度量值**、无判据语义 ⇒ `return 0` 是**有意设计**（A-30）：
即便 `duplicate (method,path) registrations > 0` 也不会失败。因此**消费方不得读它的退出码**，
应改为解析其 stdout / JSON 做漂移检测 —— 判据落在
`test-reports-2026-10/harness/coverage_drift.py`（TL-03），CI 链里**不得**出现本脚本的退出码。
"""
import collections
import json
import sys

from _test_bootstrap import make_app


def a14_reconfigure():
    """A-14：本机控制台 GBK，print 非 GBK 字符不得把「跑完」伪装成「崩溃 exit 1」。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors='replace')
        except Exception:
            pass


def main():
    a14_reconfigure()
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

    # ---- B17-14：GET+写 多方法 face（报告型：只度量，不改退出码；判据由 coverage_drift 消费）----
    # 同一 path 上 GET 与写方法并存 ⇒ 「GET 页面面通过」不代表写面被执法（门禁盲区 face 补位）。
    write_methods = sorted(r.methods - {'GET', 'HEAD', 'OPTIONS'})
    multi_method = sorted(
        (str(r), r.endpoint, sorted(r.methods - {'GET', 'HEAD', 'OPTIONS'}))
        for r in rules
        if r.endpoint != 'static' and 'GET' in r.methods
        and (r.methods - {'GET', 'HEAD', 'OPTIONS'}))
    print(f'[multi] GET+写 多方法规则={len(multi_method)}'
          f'（判据由 harness/coverage_drift.py 消费本段计数与逐条列表；'
          f'measure_coverage 的同名 face 是其中「未被任何探针命中」的子集）')
    for p, ep, ms in multi_method:
        print(f'  MULTI {"+".join(["GET"] + ms)} {p} -> {ep}')
    print('[e03] exit_code_semantics=' + json.dumps({
        'script': 'scripts/route_inventory.py',
        'class': '报告型（无判据语义 => 恒 exit 0，E-03/A-30）',
        'in_gate_chain': False,
        'consumer': 'test-reports-2026-10/harness/coverage_drift.py（解析 stdout/JSON 做漂移检测）',
        'code': 0,
    }, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
