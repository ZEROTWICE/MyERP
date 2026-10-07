"""ci_gates.py — E-04：CI 等价门禁入口（本地可跑，Jenkins 与 GitHub Actions 共用）。

**为什么需要它**：`Jenkinsfile` 原先对 4 项真闸门 + 请求型脚本的调用次数 = **0**，AGENTS.md 的
「必跑门禁表」是纯手工纪律。本脚本把 `21-E04精确修法与验收判据.md` §2 的命令清单变成**单一入口**，
CI 配置只调用它（配置薄、逻辑可离线验证）。

**分组（A-62 + A-63 + A-85 接线，**勿合并或扩大**）**

| 组 | 成员 | 说明 |
| --- | --- | --- |
| **blocking** | `check_templates` / `check_migration_heads` / `check_properties` / `check_db_bootstrap`(shim) / `functional_test`(shim) / `permission_matrix --no-dump`(shim) / `coverage_drift.py` / **`run_gates.py` 的非环境依赖部分** / **`check_model_refs`（TL-01）** / **`check_http_contract`（TL-02）** | permx 判据单一确定（匿名可访问 = 0）⇒ 直接 blocking |
| **report-only** | `smoke_test --no-dump`(shim)（A-63 第一步先观测 1 轮）/ `route_inventory` 与 `measure_coverage` 的**退出码**（报告型 A-30）/ `route_inventory_native_probe`（**环境依赖探针，A-62 明令不得重基线化**）/ **`evidence_hash`（TL-04：白名单制）** | 二者失败只记录、不阻塞；晋升方式见 `--phase second` |

**A-85 接线（B1：把 W7 三个「预留接入位」由注释变实装）**

| 步骤 | 归属 | 接法 | 判据口径（**勿改**） |
| --- | --- | --- | --- |
| `check_model_refs` | TL-01 | **blocking** | `expects` **只钉** `'violations 0'` + `'RESULT: OK'`。**严禁钉 `name_query_refs` 计数**——实测 574/575/602 已三次漂移（它随测试资产自增，非判据）。另钉 `known_bad_absent`（P-01 的两个端点函数名）。 |
| `check_http_contract` | TL-02 | **blocking** | 落点登记为「**已由 `harness/w4_http_contract.py` 承担**」，**不迁移**到 `scripts/`（A-85 裁定）。基线口径 **B** = `--scope app --expect 10`：P-12 的 10 个 `get_json()` 残留站点**具名登记**（`--scope doc` 只含 17 个 P-09 函数、**看不见 P-12**，故不可作防复发判据）。**`--selftest` 统计行不得进 `expects`**（该行历史实现漏调 `visit()`，曾恒报 2/5）。 |
| `evidence_hash` | TL-04 | **report-only** + **白名单** | 白名单登记 33 条 **captain 侧既有违规**（A-52/A-55）。**不**带 `--strict-index`（`index_missing` 恒 > 0 ⇒ 会恒 exit 1）。判据 = ① 无**未登记**违规；② 白名单条目**零陈旧**（防悄悄缩小约束）；③ `real_db_matches_pinned` 为真。**新违规 ⇒ 本步失败（report-only ⇒ 整体 exit 2）**。 |

> 三接入位的技术条件由 t5 裁定（TL-01 `READY_NOW`／TL-02 `CANNOT_ENABLE_AS_WRITTEN` → 已按 A-85 定落点与口径／TL-04 `REPORT_ONLY_ONLY`）。
> **生效条件不在本脚本内**：A-85④ 的第二步晋升（`Jenkinsfile:112/122` 解除 `error()` 注释 + GH 去 `continue-on-error` + 加 `needs: gate`）**本轮未实施** ⇒ 这些步骤红灯目前只记 `UNSTABLE`。

**注入破坏（判据形态 ⑦）用的两个只读开关**：`--inject-evidence-root`（把 `evidence_hash` 的校验根指向合成树）与
`--evidence-whitelist`（替换白名单路径）。二者只改**输入路径**，不改任何判据 ⇒ 用于证明「注入 ⇒ 本入口非零」。

**三条硬要求**
1. 进链的请求型脚本**必须** `--no-dump`（A-11：禁止让仓库根写盘参与退出码）；
2. **「绿」必须来自断言段**：每个步骤都做**期望值逐项相等**检查，且请求型步骤额外断言
   `[WARN] 落盘失败` **不出现**（否则是「没红」而不是「绿」）；
3. `run_gates.py` 的退出码在环境依赖探针不匹配时为 1（A-62 的正确行为）⇒ 其 **blocking 判据取
   `gates.json` 的非环境依赖部分**（`summary.fail == 0` ∧ 4 项进链门禁全 `pass` ∧ 逐项 checks 全过），
   并把探针的 `native_exit` 与 `expected` **同时打印**（让「环境变了」可见）。

退出码：`0` = 全部 blocking 通过；`1` = 有 blocking 失败；`2` = 无 blocking 失败但有 report-only 失败
（便于第一阶段在 Jenkins 记 `UNSTABLE` 而不阻塞）。

用法（仓库根目录）：

    python -B test-reports-2026-10/harness/ci_gates.py                     # 第一阶段（smoke 观测）
    python -B test-reports-2026-10/harness/ci_gates.py --phase second      # 第二阶段（smoke 转 blocking）
    python -B test-reports-2026-10/harness/ci_gates.py --only check_templates --check-templates-script <坏树副本>
"""
import argparse
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPORTS_ROOT = os.path.dirname(HERE)
REPO_ROOT = os.path.dirname(REPORTS_ROOT)
SCRIPTS_DIR = os.path.join(REPO_ROOT, 'scripts')
sys.path.insert(0, HERE)

from _env import RUN_ID, guard_write, interpreter, run_child, save_evidence, sha256_file  # noqa: E402

ROOT_JSON = ('_smoke_results.json', '_permission_matrix.json')

#: TL-04 白名单登记件（A-52/A-55 的 captain 侧既有违规；只登记，不洗白）
DEFAULT_EVIDENCE_WHITELIST = os.path.join(HERE, 't8-evidence-whitelist.json')

#: A-63 第二步的晋升注记（晋升时把下面这行改成实际日期）
SMOKE_PROMOTION_NOTE = 'smoke_test 自 <待晋升日期> 起升为 blocking（A-63 第二步：观测 1 轮构建后）'


def load_whitelist(path):
    """读 TL-04 白名单（只读；缺失或不可解析 ⇒ 视为「无白名单」并给原因）。

    返回 ``(registered_set, reason, doc)``：``registered_set`` 为 ``{(kind, path)}``。
    """
    if not path or not os.path.isfile(path):
        return set(), 'whitelist missing: %s' % path, None
    try:
        with open(path, encoding='utf-8') as fh:
            doc = json.load(fh)
    except Exception as e:
        return set(), 'whitelist unparsable: %s: %s' % (type(e).__name__, e), None
    reg = set()
    for it in doc.get('violations', []):
        if isinstance(it, dict) and it.get('path'):
            reg.add((it.get('kind'), it['path']))
    return reg, '', doc


def spec_steps(python_exe, check_templates_script=None,
               evidence_whitelist=DEFAULT_EVIDENCE_WHITELIST):
    """§2 的九条命令 + 判据层链路 + A-85 三接入位（分组见模块 docstring）。"""
    exe = python_exe
    shim = os.path.join('scripts', '_sandbox_compat.py')
    return [
        {'id': 'check_templates', 'group': 'blocking',
         'argv': [exe, '-B', check_templates_script or os.path.join('scripts', 'check_templates.py')],
         'expect_exit': 0,
         'expects': ['[templates] parsed 87 files',
                     '[permissions] 44 declared / 40 used in templates / 44 used on routes',
                     '[landing] 5 role landing endpoints', 'RESULT: OK']},
        {'id': 'check_migration_heads', 'group': 'blocking',
         'argv': [exe, '-B', os.path.join('scripts', 'check_migration_heads.py')],
         'expect_exit': 0,
         'expects': ["HEADS=['p1nonctarget']", 'head_count=1', 'revisions=35']},
        {'id': 'check_properties', 'group': 'blocking',
         'argv': [exe, '-B', os.path.join('scripts', 'check_properties.py')],
         'expect_exit': 0,
         'expects': ['已扫描 23 个文件，模型类 74 个', 'RESULT: OK']},
        {'id': 'check_db_bootstrap', 'group': 'blocking',
         'argv': [exe, '-B', shim, os.path.join('scripts', 'check_db_bootstrap.py')],
         'expect_exit': 0,
         'expects': ['种子库账号数（经自举导入到空库）= 64', '直接拷贝 6712 行，跳过 0 张表',
                     'OK: 空库自举、幂等、无种子库跳过、整表无遗漏 均通过']},
        {'id': 'run_gates', 'group': 'blocking', 'mode': 'run_gates',
         'argv': [exe, '-B', os.path.join('test-reports-2026-10', 'harness', 'run_gates.py')],
         'expect_exit': None,          # A-62：环境依赖探针不匹配时退出码为 1，属预期
         'expects': ['[run_gates] probe_unexpected = ']},
        {'id': 'functional_test', 'group': 'blocking',
         'argv': [exe, '-B', shim, os.path.join('scripts', 'functional_test.py')],
         'expect_exit': 0,
         'expects': ['结果：109 通过 / 0 失败']},
        {'id': 'permission_matrix', 'group': 'blocking', 'request': True,
         'argv': [exe, '-B', shim, os.path.join('scripts', 'permission_matrix.py'), '--no-dump'],
         'expect_exit': 0,
         'expects': ['[OK] 匿名可访问 = 0'], 'expect_absent': ['[WARN] 落盘失败'],
         'note': 'A-63：判据单一确定（匿名可访问 = 0）=> 第一步即 blocking'},
        {'id': 'smoke_test', 'group': 'report-only', 'request': True,
         'argv': [exe, '-B', shim, os.path.join('scripts', 'smoke_test.py'), '--no-dump'],
         'expect_exit': 0,
         'expects': ['无 5xx / 异常 / 重定向死循环'], 'expect_absent': ['[WARN] 落盘失败'],
         'note': SMOKE_PROMOTION_NOTE},
        {'id': 'route_inventory', 'group': 'report-only', 'capture_stdout': True,
         'argv': [exe, '-B', shim, os.path.join('scripts', 'route_inventory.py')],
         'expect_exit': 0,
         'expects': ['[routes] total rules=271', 'duplicate (method,path) registrations=0'],
         'note': '报告型（A-30）：退出码不作为判据；stdout 交给 coverage_drift 的 D-8'},
        {'id': 'measure_coverage', 'group': 'report-only', 'mode': 'coverage_json',
         'argv': [exe, '-B', os.path.join('test-reports-2026-10', 'harness', 'measure_coverage.py'),
                  '--no-request-probes'],
         'expect_exit': 0,
         'note': '报告型（T-09/A-30）：退出码不作为判据；产出 coverage.json 给 coverage_drift'},
        {'id': 'coverage_drift', 'group': 'blocking', 'mode': 'coverage_drift',
         'argv': [exe, '-B', os.path.join('test-reports-2026-10', 'harness', 'coverage_drift.py')],
         'expect_exit': 0,
         'expects': ['判据 8/8 通过'],
         'note': '报告型脚本产物的判据层（A-63：直接进 blocking）'},
        # ---- A-85 接线：W7 三接入位（TL-01 / TL-02 / TL-04）由注释变实装 ------------
        # TL-01（blocking）。判据 = 违规数 0 + RESULT: OK + 两个已知坏点缺席。
        # 【严禁】把 name_query_refs 计数写进 expects —— 实测 574/575/602 三次漂移。
        {'id': 'check_model_refs', 'group': 'blocking',
         'argv': [exe, '-B', os.path.join('scripts', 'check_model_refs.py')],
         'expect_exit': 0,
         'expects': ['violations 0', 'RESULT: OK'],
         'known_bad_absent': [('app/main/routes.py', 'delete_consumable'),
                              ('app/main/routes.py', 'use_consumable')],
         'note': 'TL-01 / G-08：P-01 类「名字未绑定」门禁。expects 勿钉 name_query_refs 计数。'},
        # TL-02（blocking）。落点 = harness/w4_http_contract.py（A-85：不迁移到 scripts/）。
        # 基线口径 B = 全 app 口径 10 个 P-12 残留站点（具名登记）；doc 口径看不见 P-12。
        # 【严禁】把 --selftest 统计行写进 expects（历史实现漏调 visit()，恒报 2/5）。
        {'id': 'check_http_contract', 'group': 'blocking', 'mode': 'args_only',
         'argv': [exe, '-B', os.path.join('test-reports-2026-10', 'harness', 'w4_http_contract.py'),
                  '--roots', 'app', '--scope', 'app', '--expect', '10'],
         'extra_argv': [{'tail': ['--json', '{json}'], 'json_name': 'http_contract.json'}],
         'expect_exit': 0,
         'expects': ['[w4_http_contract] 会吞成静默出口的站点 = 10',
                     '"sites": 10', '"expected": 10'],
         'note': 'TL-02 / G-09：P-09/P-12「静默出口」门禁。基线口径 B（10 处 P-12 残留，'
                 '具名登记：routes.py:1720/5367/5420/6233/7026/8067/10080/10834/10976/11138）。'},
        # TL-04（report-only + 白名单）。不带 --strict-index（index_missing 恒 > 0 ⇒ 恒 exit 1）；
        # 带 --no-strict-coverage：只追加模式下「未登记的新增」本就是**允许**项，而该判据在本轮
        # 会被队友沿途新增的根目录文件（如 r2t4-*.out.txt）持续打成 coverage_gap ⇒ 恒红噪声。
        # 真正要守的是「既有文件被改写/删除」——那两类不受该开关影响。
        {'id': 'evidence_hash', 'group': 'report-only', 'mode': 'args_only',
         'argv': [exe, '-B', os.path.join('test-reports-2026-10', 'harness', 'evidence_hash.py'),
                  '--no-strict-coverage'],
         'extra_argv': [{'tail': ['--out', '{json}'], 'json_name': 'evidence_hash.gate.json'}],
         'expect_exit': None,
         'hook': 'evidence_hash_whitelist',
         'whitelist': evidence_whitelist,
         'note': 'TL-04 / G-10：evidence/** 只追加防篡改。判据 = 无未登记违规 + 白名单零陈旧 '
                 '+ real_db 钉值未变；登记 33 条 captain 侧既有违规（A-52/A-55）。'
                 '--no-strict-coverage 的理由见上方注释（allowlist 语义 + 去噪声）。'},
    ]


def evidence_hash_whitelist(res, step, run_dir):
    """TL-04 的判据：把 evidence_hash 的违规集与白名单对拍（只登记既有违规，不洗白）。

    返回 ``(checks, extra)``；``checks`` 里任一项 ``failed`` ⇒ 本步失败。
    """
    checks = []
    extra = {}
    jpath = step.get('json_path')
    reg, reason, wdoc = load_whitelist(step.get('whitelist'))

    if not jpath or not os.path.isfile(jpath):
        checks.append({'kind': 'json', 'needle': 'evidence_hash --out JSON present',
                       'status': 'failed'})
        extra['whitelist'] = {'path': step.get('whitelist'), 'registered': None,
                              'reason': reason or ('json not written: %s' % jpath)}
        return checks, extra

    with open(jpath, encoding='utf-8') as fh:
        rep = json.load(fh)
    violations = rep.get('violations') or []
    actual_set = {(v.get('kind'), v.get('path')) for v in violations if v.get('path')}
    unregistered = sorted(actual_set - reg)
    stale = sorted(reg - actual_set)
    pinned = bool(rep.get('real_db_matches_pinned'))

    extra['evidence_hash'] = {
        'verdict': rep.get('verdict'),
        'counts': rep.get('counts'),
        'violations_total': len(violations),
        'real_db_matches_pinned': pinned,
        'report_json': os.path.relpath(jpath, REPO_ROOT).replace('\\', '/'),
    }
    extra['whitelist'] = {
        'path': step.get('whitelist'),
        'registered': len(reg),
        'registered_declared': (wdoc or {}).get('registered_count'),
        'registered_source': (wdoc or {}).get('registered_source'),
        'unregistered_count': len(unregistered),
        'unregistered_first10': ['%s|%s' % (k, p) for k, p in unregistered[:10]],
        'stale_count': len(stale),
        'stale_first10': ['%s|%s' % (k, p) for k, p in stale[:10]],
    }
    # 白名单条目清单随报告落盘（供审计：这条约束当前到底由哪些条目构成）
    if wdoc is not None:
        mpath, _renamed = guard_write(os.path.join(run_dir, 'evidence_whitelist.registered.json'))
        with open(mpath, 'w', encoding='utf-8', newline='\n') as fh:
            json.dump(wdoc, fh, ensure_ascii=False, indent=1)
        extra['whitelist']['manifest'] = os.path.relpath(mpath, REPO_ROOT).replace('\\', '/')

    checks.append({'kind': 'whitelist', 'needle': 'no unregistered violation',
                   'status': 'passed' if not unregistered else 'failed'})
    checks.append({'kind': 'whitelist', 'needle': 'whitelist has no stale entry',
                   'status': 'passed' if not stale else 'failed'})
    checks.append({'kind': 'pinned', 'needle': 'real_db_matches_pinned == true',
                   'status': 'passed' if pinned else 'failed'})
    return checks, extra


def root_json_state():
    state = {}
    for name in ROOT_JSON:
        p = os.path.join(REPO_ROOT, name)
        state[name] = {'exists': os.path.exists(p),
                       'sha256': sha256_file(p) if os.path.exists(p) else None}
    return state


def main(argv=None):
    ap = argparse.ArgumentParser(
        description='E-04 CI 等价门禁入口（blocking/report-only 分组见模块 docstring）')
    ap.add_argument('--phase', default='first', choices=('first', 'second'),
                    help='first = smoke_test 先 report-only（A-63）；second = smoke_test 转 blocking')
    ap.add_argument('--python-exe', default=interpreter(),
                    help='子进程解释器（默认 _env.interpreter()：有 F:\\Miniconda\\envs\\wage\\python.exe 用它，'
                         '否则回退 sys.executable，便于 Linux runner）')
    ap.add_argument('--json', default=None, help='机读结果落点（写入守卫：已存在则改名保留）')
    ap.add_argument('--only', default=None, help='只跑某一步（id），用于破坏实验')
    ap.add_argument('--check-templates-script', default=None,
                    help='覆盖第 1 步的 check_templates 脚本路径（E-04-b 破坏实验用合成树副本）')
    ap.add_argument('--check-model-refs-root', default=None,
                    help='注入破坏（判据形态 ⑦）：把 TL-01 的 --root 指向合成坏树')
    ap.add_argument('--check-http-contract-roots', default=None,
                    help='注入破坏（判据形态 ⑦）：把 TL-02 的 --roots 指向合成树（逗号分隔）')
    ap.add_argument('--inject-evidence-root', default=None,
                    help='注入破坏（判据形态 ⑦）：把 TL-04 的校验根指向合成树')
    ap.add_argument('--evidence-whitelist', default=DEFAULT_EVIDENCE_WHITELIST,
                    help='TL-04 白名单登记件路径（默认 harness/t8-evidence-whitelist.json）')
    ap.add_argument('--list', action='store_true', help='只打印命令清单与分组')
    args = ap.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors='replace')
        except Exception:
            pass

    exe = args.python_exe
    steps = spec_steps(exe, args.check_templates_script,
                       evidence_whitelist=args.evidence_whitelist)
    if args.phase == 'second':
        for s in steps:
            if s['id'] == 'smoke_test':
                s['group'] = 'blocking'
    # 注入破坏开关（只改输入路径，不改判据）：把 TL-04 的校验根指向合成树
    if args.inject_evidence_root:
        for s in steps:
            if s['id'] == 'evidence_hash':
                s.setdefault('extra_argv', []).append(
                    {'tail': ['--evidence-root', args.inject_evidence_root]})
    if args.only:
        steps = [s for s in steps if s['id'] == args.only]
        if not steps:
            print('[ci_gates] 未知步骤: %s' % args.only)
            return 1

    if args.list:
        # 把注入破坏开关也展开出来（让「实际会跑什么」可见，便于复现与审计）
        for s in steps:
            argv = list(s['argv'])
            if args.check_model_refs_root and s['id'] == 'check_model_refs':
                argv += ['--root', args.check_model_refs_root]
            if args.check_http_contract_roots and s['id'] == 'check_http_contract':
                i = argv.index('--roots')
                argv = argv[:i + 1] + args.check_http_contract_roots.split(',') + argv[i + 2:]
            for spec_extra in s.get('extra_argv', []):
                argv += [a.replace('{json}', '<run_dir>/%s' % spec_extra.get('json_name'))
                         for a in spec_extra.get('tail', [])]
            print('[ci_gates] %-22s %-11s %s' % (s['id'], s['group'], ' '.join(argv)))
        print('[ci_gates] phase=%s interpreter=%s' % (args.phase, exe))
        return 0

    run_name = RUN_ID if RUN_ID.startswith('ci-') else 'ci-%s' % RUN_ID
    run_dir = os.path.join(REPORTS_ROOT, 'evidence', 'harness', run_name)
    os.makedirs(run_dir, exist_ok=True)
    before = root_json_state()

    results = []
    for s in steps:
        argv_step = list(s['argv'])
        out_path = None
        if s.get('mode') == 'run_gates':
            out_path = os.path.join(run_dir, 'gates.json')
            argv_step += ['--out', out_path]
        if s.get('mode') == 'coverage_json':
            out_path = os.path.join(run_dir, 'coverage.json')
            argv_step += ['--out', out_path]
        if s.get('mode') == 'coverage_drift':
            routes_file = os.path.join(run_dir, 'route_inventory.stdout.txt')
            if not os.path.isfile(routes_file):
                routes_file = None
            argv_step += ['--coverage', os.path.join(run_dir, 'coverage.json')]
            if routes_file:
                argv_step += ['--routes-stdout', routes_file]
        # A-85：新接入的步骤用 extra_argv 声明「落在本 run 目录里的机读产物」。
        # 注意：只有声明了 json_name 的条目才设置 json_path —— 否则后面的纯参数条目
        # （例：注入破坏追加的 --evidence-root）会把先前的 json_path 覆盖成 None。
        for spec_extra in s.get('extra_argv', []):
            jname = spec_extra.get('json_name')
            jpath = os.path.join(run_dir, jname) if jname else None
            if jpath:
                s['json_path'] = jpath
            tail = list(spec_extra.get('tail', []))
            if jpath:
                arg_i = tail.index('{json}') if '{json}' in tail else -1
                if arg_i >= 0:
                    tail[arg_i] = jpath
            argv_step += tail
        # 注入破坏（判据形态 ⑦）：TL-01 的 --root 指向合成坏树
        if args.check_model_refs_root and s['id'] == 'check_model_refs':
            argv_step += ['--root', args.check_model_refs_root]
        # 注入破坏（判据形态 ⑦）：TL-02 的 --roots 指向合成树（原值在 --roots 之后、--scope 之前）
        if args.check_http_contract_roots and s['id'] == 'check_http_contract':
            new_roots = args.check_http_contract_roots.split(',')
            i = argv_step.index('--roots')
            argv_step = argv_step[:i + 1] + new_roots + argv_step[i + 2:]
        if s.get('capture_stdout'):
            s['stdout_file'] = os.path.join(run_dir, 'route_inventory.stdout.txt')

        # 去掉解释器（run_child 自己会加，且遵守 _env.interpreter() 的绝对路径规则）
        res = run_child(argv_step[1:], cwd=REPO_ROOT, timeout=3600, label='ci_%s' % s['id'])
        text = res['stdout'] + res['stderr']
        if s.get('stdout_file'):
            with open(s['stdout_file'], 'w', encoding='utf-8', newline='\n') as fh:
                fh.write(text)

        checks = []
        for needle in s.get('expects', []):
            ok = needle in text
            checks.append({'kind': 'expects', 'needle': needle, 'status': 'passed' if ok else 'failed'})
        for needle in s.get('expect_absent', []):
            ok = needle not in text
            checks.append({'kind': 'expect_absent', 'needle': needle,
                           'status': 'passed' if ok else 'failed'})
        # A-85 / TL-01：P-01 的两个端点不得再出现在违规清单里（反向判据，防「修好的又回来」）。
        # 口径：只在**违规段**（"found N violation(s):" 之后）匹配 `<basename>:<line>` 与函数名，
        # 避免命中汇总行 / source 行造成的假阳性。
        for bad_file, bad_func in s.get('known_bad_absent', []):
            short = os.path.basename(bad_file)
            viol_text = text.split('found ', 1)[1] if 'found ' in text else ''
            hit_line = re.search(r'%s:\d+' % re.escape(short), viol_text) is not None
            hit_func = bad_func in viol_text
            checks.append({'kind': 'known_bad_absent',
                           'needle': '%s / %s absent from violations' % (short, bad_func),
                           'status': 'passed' if not (hit_line or hit_func) else 'failed'})
        if s['expect_exit'] is not None:
            ok = res['exit_code'] == s['expect_exit']
            checks.append({'kind': 'exit', 'needle': 'exit == %s' % s['expect_exit'],
                           'status': 'passed' if ok else 'failed'})

        extra = {}
        if s.get('hook'):
            hook_checks, hook_extra = globals()[s['hook']](res, s, run_dir)
            checks.extend(hook_checks)
            extra.update(hook_extra)
        if s.get('mode') == 'run_gates':
            # A-62：blocking 判据 = 非环境依赖部分
            with open(out_path, encoding='utf-8') as fh:
                gates = json.load(fh)
            summary = gates['summary']
            in_chain = [g for g in gates['gates'] if g['exit_code_informative']]
            probes = [g for g in gates['gates'] if g.get('probe_only')]
            fail_ok = summary['fail'] == 0
            chain_ok = all(g['verdict'] == 'pass' for g in in_chain)
            checks_ok = all(all(c['status'] == 'passed' for c in g['checks']) for g in in_chain)
            checks.append({'kind': 'gates_json', 'needle': 'summary.fail == 0',
                           'status': 'passed' if fail_ok else 'failed'})
            checks.append({'kind': 'gates_json', 'needle': '4 项进链门禁全 pass',
                           'status': 'passed' if chain_ok else 'failed'})
            checks.append({'kind': 'gates_json', 'needle': '进链门禁逐项 checks 全过',
                           'status': 'passed' if checks_ok else 'failed'})
            extra = {
                'gates_json': os.path.relpath(out_path, REPO_ROOT).replace('\\', '/'),
                'summary': summary,
                'exit_code_semantics': gates.get('exit_code_semantics'),
                'in_chain': {g['gate']: g['verdict'] for g in in_chain},
                'probe_env_dependent': [
                    {'gate': g['gate'], 'native_exit': g['exit_code'],
                     'expected': g['expected_exit_code'], 'verdict': g['verdict']}
                    for g in probes],
                'note': 'A-62：环境依赖探针留在 report-only；其 native_exit 与 expected 同时打印',
            }
            print('[ci_gates]   run_gates exit=%s（A-62：环境依赖探针不匹配时为 1，属预期）'
                  % res['exit_code'])
            for p in extra['probe_env_dependent']:
                print('[ci_gates]   env-probe %s: native_exit=%s expected=%s verdict=%s'
                      % (p['gate'], p['native_exit'], p['expected'], p['verdict']))
        if s.get('mode') == 'coverage_drift':
            extra = {'coverage_json': os.path.relpath(os.path.join(run_dir, 'coverage.json'),
                                                      REPO_ROOT).replace('\\', '/')}

        status = 'passed' if all(c['status'] == 'passed' for c in checks) else 'failed'
        results.append({
            'id': s['id'], 'group': s['group'], 'command': res['argv_display'],
            'exit_code': res['exit_code'], 'expected_exit': s['expect_exit'],
            'status': status, 'checks': checks,
            'evidence_level': res['evidence_level'],
            'real_db_unchanged': res['real_db_unchanged'],
            'stdout_tail': '\n'.join([l for l in text.splitlines() if l.strip()][-12:]),
            'note': s.get('note', ''),
            **extra,
        })
        flag = 'OK  ' if status == 'passed' else 'FAIL'
        print('[ci_gates] %s %-22s group=%-11s exit=%s %s'
              % (flag, s['id'], s['group'], res['exit_code'],
                 ('checks %d/%d' % (sum(1 for c in checks if c['status'] == 'passed'), len(checks)))) )
        for c in checks:
            if c['status'] == 'failed':
                print('[ci_gates]      !! %s %s' % (c['kind'], c['needle']))

    after = root_json_state()
    root_ok = all(before[n] == after[n] for n in ROOT_JSON)
    blocking_fail = [r['id'] for r in results if r['group'] == 'blocking' and r['status'] != 'passed']
    report_fail = [r['id'] for r in results if r['group'] == 'report-only' and r['status'] != 'passed']
    code = 1 if (blocking_fail or not root_ok) else (2 if report_fail else 0)

    out = {
        'harness': 'ci_gates.py',
        'run_id': RUN_ID,
        'phase': args.phase,
        'interpreter': exe,
        'repo_root': REPO_ROOT,
        'steps': results,
        'blocking_failed': blocking_fail,
        'report_only_failed': report_fail,
        'root_json_untouched': {
            'ok': root_ok,
            'before': before, 'after': after,
            'frozen_reference': {'_smoke_results.json':
                                 'D301835F077D2EDFFCB5DA4469C87A23C594D1E9EC75010594C3A812466A9762',
                                 '_permission_matrix.json':
                                 '999A01209A8A56BBE7CF1FB5842FE4991762A91683DF97621650B11068B67C19'},
            'note': 'A-11：CI 里禁止跑会写仓库根 JSON 的形态；请求型步骤一律 --no-dump'},
        'exit_code_semantics': {
            'code': code,
            'rule': ('0 = 全部 blocking 通过; 1 = 有 blocking 失败（或仓库根 JSON 被写）; '
                     '2 = 仅 report-only 失败'),
            'inputs': {'blocking_failed': blocking_fail, 'report_only_failed': report_fail,
                       'root_json_untouched': root_ok},
        },
        'promotion_note': SMOKE_PROMOTION_NOTE,
    }

    print('[ci_gates] blocking 失败 = %s' % (blocking_fail or '无'))
    print('[ci_gates] report-only 失败 = %s' % (report_fail or '无'))
    print('[ci_gates] 仓库根两 JSON 未被触碰 = %s（A-11）' % root_ok)
    print('[ci_gates] exit = %d  phase=%s' % (code, args.phase))
    print('[ci_gates] exit_code_semantics=' + json.dumps(out['exit_code_semantics'],
                                                         ensure_ascii=False))

    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
        path, renamed = guard_write(args.json)
        with open(path, 'w', encoding='utf-8', newline='\n') as fh:
            json.dump(out, fh, ensure_ascii=False, indent=2)
        print('[ci_gates] JSON -> %s%s' % (path, '（写入守卫改名保留）' if renamed else ''))
    text = ('=' * 88 + '\n[ci_gates] run_id=%s phase=%s interpreter=%s\n' % (RUN_ID, args.phase, exe)
            + json.dumps(out, ensure_ascii=False, indent=1) + '\n')
    saved = save_evidence('ci_gates_%s.console.txt' % args.phase, text, subdir=run_name)
    print('[ci_gates] 原始输出已落盘（写入守卫 + 台账）-> %s' % saved)
    return code


if __name__ == '__main__':
    sys.exit(main())
