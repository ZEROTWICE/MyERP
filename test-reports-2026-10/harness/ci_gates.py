# -*- coding: utf-8 -*-
"""ci_gates.py — E-04：CI 等价门禁入口（本地可跑，Jenkins 与 GitHub Actions 共用）。

> **必须保留上面这行编码声明（V-01 实测）**：本文件含中文、体积 > 64 KB，在本机
> CPython 3.9（Windows，`fgets` 缓冲 512 B）下曾触发**假** SyntaxError
> `Non-UTF-8 code starting with '\\xe4' ... but no encoding declared`（多字节字符被
> 分词器读缓冲截断）。声明 `coding: utf-8` 后走「显式编码」解码分支即消失；
> 删掉它 ⇒ `python -B ci_gates.py` 直接 SyntaxError（这就是它的 behavior_flip_test）。

**为什么需要它**：`Jenkinsfile` 原先对 4 项真闸门 + 请求型脚本的调用次数 = **0**，AGENTS.md 的
「必跑门禁表」是纯手工纪律。本脚本把 `21-E04精确修法与验收判据.md` §2 的命令清单变成**单一入口**，
CI 配置只调用它（配置薄、逻辑可离线验证）。

**分组（A-62 + A-63 + A-85 接线，**勿合并或扩大**）**

| 组 | 成员 | 说明 |
| --- | --- | --- |
| **blocking** | `check_templates` / `check_migration_heads` / `check_properties` / `check_db_bootstrap`(shim) / `functional_test`(shim) / `permission_matrix --no-dump`(shim) / `coverage_drift.py` / **`run_gates.py` 的非环境依赖部分** / **`check_model_refs`（TL-01）** / **`check_http_contract`（TL-02）** / **`chain_count_consistency`（B15-07，件数守恒对拍）** / **`negative_matrix`（B17-15，四类必交 + 阳性对照）** / **`check_is_archived_policy`（B17-07）** / **`check_doc_claims`（B17-16，口径守卫）** | permx 判据单一确定（匿名可访问 = 0）⇒ 直接 blocking |
| **report-only** | `smoke_test --no-dump`(shim)（A-63 第一步先观测 1 轮）/ `route_inventory` 与 `measure_coverage` 的**退出码**（报告型 A-30）/ `route_inventory_native_probe`（**环境依赖探针，A-62 明令不得重基线化**）/ **`evidence_hash`（TL-04：白名单制）** | 二者失败只记录、不阻塞；晋升方式见 `--phase second` |

**A-85 接线（B1：把 W7 三个「预留接入位」由注释变实装）**

| 步骤 | 归属 | 接法 | 判据口径（**勿改**） |
| --- | --- | --- | --- |
| `check_model_refs` | TL-01 | **blocking** | `expects` **只钉** `'violations 0'` + `'RESULT: OK'`。**严禁钉 `name_query_refs` 计数**——实测 574/575/602 已三次漂移（它随测试资产自增，非判据）。另钉 `known_bad_absent`（P-01 的两个端点函数名）。 |
| `check_http_contract` | TL-02 | **blocking** | 落点登记为「**已由 `harness/w4_http_contract.py` 承担**」，**不迁移**到 `scripts/`（A-85 裁定）。基线口径 **B** = `--scope app --expect 10`：P-12 的 10 个 `get_json()` 残留站点**具名登记**（`--scope doc` 只含 17 个 P-09 函数、**看不见 P-12**，故不可作防复发判据）。**`--selftest` 统计行不得进 `expects`**（该行历史实现漏调 `visit()`，曾恒报 2/5）。 |
| `evidence_hash` | TL-04 | **report-only** + **白名单** | 白名单登记 33 条 **captain 侧既有违规**（A-52/A-55）+ **1 条通配规则**（A-89，见下）。**不**带 `--strict-index`（`index_missing` 恒 > 0 ⇒ 会恒 exit 1）。判据 = ① 无**未登记**违规；② 白名单条目**零陈旧**（防悄悄缩小约束）；③ 通配规则**也**纳入陈旧判定（匹配 0 条 ⇒ 失败）；④ `real_db_matches_pinned` 为真。**新违规 ⇒ 本步失败（report-only ⇒ 整体 exit 2）**。 |

> 三接入位的技术条件由 t5 裁定（TL-01 `READY_NOW`／TL-02 `CANNOT_ENABLE_AS_WRITTEN` → 已按 A-85 定落点与口径／TL-04 `REPORT_ONLY_ONLY`）。
> **生效条件不在本脚本内**：A-85④ 的第二步晋升（`Jenkinsfile:112/122` 解除 `error()` 注释 + GH 去 `continue-on-error` + 加 `needs: gate`）**本轮未实施** ⇒ 这些步骤红灯目前只记 `UNSTABLE`。
> 该缺口在机读产物里**显式登记为 `blocked`**（`BUILD_LAYER_BLOCKED`，随 `gaps[]` 落盘，**不计入通过数**）。

**TL-04 白名单通配（V-01 追加，A-89）**

`regression_preflight.py` 把归档写进 `evidence/_phaseB-prefreeze/<stamp>/`（`ARCHIVE_ROOT`），而
`evidence_hash` 索引 `evidence/**` ⇒ **每跑一次 preflight 都给 evidence_hash 加一批新文件**
（stamp 名不可预知，形态恒为 5 `deleted` + 2 `modified` + 1 `phantom_entry`）⇒ 逐条枚举**必然追不上**。
处置（captain 裁定 A-89）：

* 白名单语义从「逐条枚举」改为「**精确 33 条（不动） + `_phaseB-prefreeze/**` 通配 1 条**」；
* 通配规则**同样**纳入「陈旧即失败」：匹配到 **0** 条违规 ⇒ 该规则 stale ⇒ 本步失败；
* **严禁重基线化**（A-85②/A-62 明令）：只追加，不删既有条目；
* 该规则是根因正解 (a)「`evidence_hash` 默认排除 `_phaseB-prefreeze/**`」的**白名单侧等效实现**；
  若将来实现 (a) 或把归档移出 `evidence/`（正解 (b)），本规则必须同步删除 —— 不得两套机制并存。

**V-01 追加块 `violations_appended`（只登记、不裁决）**：V-01 复跑时检出 2 条**非本任务**的
未登记违规 —— `modified|uat/uat_chains.json`、`modified|uat/uat_chains.out.txt`（冻结锚点 1
在 2026-10-07 22:18:31 被 UAT 链任务**原地重写**，33318 B ⇒ 46051 B）。处置：以
`violations_appended` 单独登记（**主块 33 条一字不动**，报数分开：`registered` / 
`registered_appended` / `registered_total`），并同样纳入「陈旧即失败」；合法性由 V-14 的
7 锚点比对裁定（28 §4），TL-04 只表示「已知且已归属」，**不表示被接受**。

**逐步注入破坏（V-01 追加，判据形态 ⑦）：`--inject-step <id>`**

`INJECTIONS` 表为**每一个**步骤声明 1 次注入，三种机制**都只改「输入路径」，不动判据**：

| 机制 | 含义 | 落在哪些步 |
| --- | --- | --- |
| `real_input` | 把该步读的**输入树/产物路径**指向受控合成坏树（脚本副本按原脚本的相对深度放置，故其自解析 ROOT = 合成树根） | `check_templates` / `check_migration_heads` / `check_properties` / `coverage_drift` / `check_model_refs` / `check_http_contract` / `evidence_hash` / `check_notification_triggers` / `chain_count_consistency`（`--perturb` 合成件数偏差声明） / `check_is_archived_policy`（`--root` 合成树 + 1 处未登记读点） / `check_doc_claims`（`--coverage` 归档锚点副本，口径源 −1） |
| `judge_artifact` | 把该步**判据层读的机读产物**换成合成的降级产物（本步程序照常真跑） | `run_gates`（`gates.json`） |
| `script_fixture` | 该步的脚本**无任何输入路径参数**（跑真 app/真库）⇒ 把「要跑的程序」这一输入路径换成合成夹具（故意打印与期望值不符的行 + 非 0 退出） | `check_db_bootstrap` / `functional_test` / `permission_matrix` / `smoke_test` / `route_inventory` / `measure_coverage` / `negative_matrix`（后者默认即跑四类必交 + 阳性对照，无参数可指） |

**判据未变是机检的**：注入前后各算一次 `criterion_fingerprint`（`expects` / `expect_absent` /
`expect_exit` / `known_bad_absent` / `mode` / `hook` 的 SHA256），两值必须相等并作为一条 `checks`
落盘；**注入若没能让该步转红，本入口自己报失败**（`injection_ineffective`，exit 1）—— 防「假注入」。

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
    python -B test-reports-2026-10/harness/ci_gates.py --inject-step <id>  # 判据形态 ⑦：该步注入破坏（须转红并被指名）
    python -B test-reports-2026-10/harness/ci_gates.py --selfcheck         # 本清单自身的 8 条不变量
"""
import argparse
import fnmatch
import hashlib
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPORTS_ROOT = os.path.dirname(HERE)
REPO_ROOT = os.path.dirname(REPORTS_ROOT)
SCRIPTS_DIR = os.path.join(REPO_ROOT, 'scripts')
sys.path.insert(0, HERE)

from _env import (RUN_ID, TMP_ROOT, guard_write, interpreter, run_child,  # noqa: E402
                  save_evidence, sha256_file)

ROOT_JSON = ('_smoke_results.json', '_permission_matrix.json')

#: TL-04 白名单登记件（A-52/A-55 的 captain 侧既有违规；只登记，不洗白）
DEFAULT_EVIDENCE_WHITELIST = os.path.join(HERE, 't8-evidence-whitelist.json')

#: A-89：归档根的展示名（通配规则写成 `<ARCHIVE_ROOT_GLOB>`），仅用于打印/断言
ARCHIVE_ROOT_GLOB = '_phaseB-prefreeze/**'

#: A-63 第二步的晋升注记（晋升时把下面这行改成实际日期）
SMOKE_PROMOTION_NOTE = 'smoke_test 自 <待晋升日期> 起升为 blocking（A-63 第二步：观测 1 轮构建后）'

#: 构建层阻塞的**显式登记**（V-01 判据 ⑤）：不计入任何通过数，随 gaps[] 落盘。
#: 判据：本入口红灯目前只记 `UNSTABLE`；真正的「构建层阻塞」要等 A-63 第二步。
BUILD_LAYER_BLOCKED = {
    'id': 'A-63-STEP2-BUILD-GATE',
    'state': 'blocked',
    'object': '构建层阻塞（Jenkinsfile / GitHub Actions 的门禁晋升）',
    'blocked_reason': ('A-63 第二步未实施：Jenkinsfile:112 与 :122 的 error() 仍是注释'
                       '（ciRc==3 / ciRc==1 只置 UNSTABLE）；'
                       '.github/workflows/docker-deploy.yml:19 continue-on-error: true 未删、'
                       ':58 的 build-and-push 未加 needs: gate'),
    'evidence': ['Jenkinsfile:110-125', '.github/workflows/docker-deploy.yml:15-19,54-58',
                 'ci_gates.py:BUILD_LAYER_BLOCKED'],
    'condition_to_unblock': ('A-63 第二步：解注释 Jenkinsfile:112/122 + GH 去 continue-on-error '
                             '+ build-and-push 加 needs: gate，再观测 1 轮全绿'),
    'owner': 'captain（A-85④ / A-63 明令 captain 独占）',
    'not_counted_as_passed': True,
    'verified_by': 'ci_gates.py --selfcheck（断言该登记存在且 state=blocked）',
}

#: check_templates.py 的 ROUTE_FILES（合成树注入用；与其源码保持一致）
TEMPLATE_ROUTE_FILES = (
    'app/main/routes.py',
    'app/main/quality.py',
    'app/main/production_center.py',
    'app/main/equipment.py',
    'app/main/purchase.py',
    'app/main/shipping.py',
    'app/main/stock.py',
)

#: 无输入路径参数的那几步用的合成夹具输出（**故意**与 expects 不符 ⇒ 判据层必须报红）
FIXTURE_LINES = {
    'check_db_bootstrap': ['种子库账号数（经自举导入到空库）= 63',
                           '直接拷贝 6711 行，跳过 1 张表',
                           'OK: (v01 注入夹具：非合规实现)'],
    'functional_test': ['结果：108 通过 / 1 失败'],
    'permission_matrix': ['[FAIL] 匿名可访问 = 3'],
    'smoke_test': ['[FAIL] 5xx / 异常 / 重定向死循环 = 2'],
    'route_inventory': ['[routes] total rules=270',
                        'duplicate (method,path) registrations=1'],
    'measure_coverage': ['[measure_coverage] FAIL: coverage probe aborted (v01 注入夹具)'],
    'negative_matrix': ['[negative_matrix] 合计 3 条：passed=1 failed=2 blocked=0',
                        '[negative_matrix] 真实库异常？ 是——立即停止',
                        '[negative_matrix] 基础设施级问题：副本库 bootstrap 失败'],
}

#: 合成夹具模板（ASCII 安全：控制台只回显夹具自己的行，由 run_child 以 utf-8 解码）
FIXTURE_TEMPLATE = '''# -*- coding: utf-8 -*-
"""V-01 注入夹具（判据形态 7）：替代 %(step)s 的**非合规实现**。

只替换「该步要跑的程序」这一输入路径；ci_gates 的判据（expects / expect_absent / expect_exit）
由 criterion_fingerprint 机检证明一字未改。夹具故意打印与期望值不符的行并以非 0 退出。
"""
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

for _line in %(lines)r:
    print(_line)
raise SystemExit(%(code)d)
'''


def _rel(path):
    return os.path.relpath(path, REPO_ROOT).replace('\\', '/')


# ------------------------------------------------------------------ 白名单（TL-04）
def load_whitelist(path):
    """读 TL-04 白名单（只读；缺失或不可解析 ⇒ 视为「无白名单」并给原因）。

    返回 ``(reg, rules, reason, doc)``：

    * ``reg`` = **精确**登记集 ``{(kind, path)}``（33 条，V-01 不得删改）；
    * ``rules`` = **通配**规则 ``[{'id', 'glob', 'kinds'}]``（A-89：归档 stamp 不可枚举）；
    * ``reason`` = 缺失/不可解析的原因（成功时为空串）。
    """
    if not path or not os.path.isfile(path):
        return set(), [], 'whitelist missing: %s' % path, None
    try:
        with open(path, encoding='utf-8') as fh:
            doc = json.load(fh)
    except Exception as e:
        return set(), [], 'whitelist unparsable: %s: %s' % (type(e).__name__, e), None
    reg = set()
    for it in doc.get('violations', []):
        if isinstance(it, dict) and it.get('path'):
            reg.add((it.get('kind'), it['path']))
    # 追加块（V-01）：与主块**分开报数**（registered 仍等于主块的 33），但仍纳入
    # 「未登记 / 陈旧」双侧判定 —— 只登记不裁决，不改变主块与对称差集语义。
    for it in doc.get('violations_appended', []):
        if isinstance(it, dict) and it.get('path'):
            reg.add((it.get('kind'), it['path']))
    rules = []
    for it in doc.get('wildcard_rules', []):
        if not isinstance(it, dict) or not it.get('glob'):
            continue
        kinds = it.get('kinds', '*')
        rules.append({'id': it.get('id') or it['glob'], 'glob': it['glob'],
                      'kinds': kinds if kinds == '*' else set(kinds)})
    return reg, rules, '', doc


def registration_counts(doc):
    """白名单的报数口径：主块（33，A-52/A-55）与 V-01 追加块**分开**报（只登记不裁决）。"""
    doc = doc or {}
    base = [it for it in doc.get('violations', []) if isinstance(it, dict) and it.get('path')]
    appended = [it for it in doc.get('violations_appended', [])
                if isinstance(it, dict) and it.get('path')]
    return {
        'registered': len(base),
        'registered_appended': len(appended),
        'registered_total': len(base) + len(appended),
        'appended_paths': ['%s|%s' % (it.get('kind'), it['path']) for it in appended],
        'appended_meta': doc.get('violations_appended_meta'),
    }


def rule_matches(rule, kind, path):
    """通配规则是否覆盖某条违规（`kinds='*'` ⇒ 任意 kind 都覆盖）。"""
    if rule['kinds'] != '*' and kind not in rule['kinds']:
        return False
    return fnmatch.fnmatchcase(path, rule['glob'])


def match_whitelist(violation_pairs, reg, rules):
    """把违规集与白名单（精确 + 通配）对拍（纯函数，hook 与 --selfcheck 共用）。

    语义（A-95 的对称差集语义推广到通配）：

    * **精确**条目在报告里消失 ⇒ `stale_exact`（防有人偷偷缩小约束）；
    * **通配**规则匹配 0 条 ⇒ `stale_rules`（防「归档被删掉后约束被悄悄放宽」）；
    * 命中通配规则的不再算 `unregistered`；`reg` 与通配命中都不覆盖的才算 `unregistered`。
    """
    actual = set(violation_pairs)
    hit = set()
    rule_hits = {}
    for rule in rules:
        n = 0
        for kind, path in actual:
            if (kind, path) in reg:
                continue
            if rule_matches(rule, kind, path):
                n += 1
                hit.add((kind, path))
        rule_hits[rule['id']] = n
    return {
        'unregistered': sorted(actual - (reg | hit)),
        'stale_exact': sorted(reg - actual),
        'stale_rules': [r['id'] for r in rules if not rule_hits[r['id']]],
        'rule_hits': rule_hits,
        'covered_by_rules': sorted(hit),
        'registered': len(reg),
        'registered_rules': len(rules),
    }


def evidence_hash_whitelist(res, step, run_dir):
    """TL-04 的判据：把 evidence_hash 的违规集与白名单对拍（只登记既有违规，不洗白）。

    返回 ``(checks, extra)``；``checks`` 里任一项 ``failed`` ⇒ 本步失败。
    """
    checks = []
    extra = {}
    jpath = step.get('json_path')
    reg, rules, reason, wdoc = load_whitelist(step.get('whitelist'))

    if not jpath or not os.path.isfile(jpath):
        checks.append({'kind': 'json', 'needle': 'evidence_hash --out JSON present',
                       'status': 'failed'})
        extra['whitelist'] = {'path': step.get('whitelist'), 'registered': None,
                              'reason': reason or ('json not written: %s' % jpath)}
        return checks, extra

    with open(jpath, encoding='utf-8') as fh:
        rep = json.load(fh)
    violations = rep.get('violations') or []
    pairs = [(v.get('kind'), v.get('path')) for v in violations if v.get('path')]
    m = match_whitelist(pairs, reg, rules)
    counts = registration_counts(wdoc)
    pinned = bool(rep.get('real_db_matches_pinned'))

    extra['evidence_hash'] = {
        'verdict': rep.get('verdict'),
        'counts': rep.get('counts'),
        'violations_total': len(violations),
        'real_db_matches_pinned': pinned,
        'report_json': _rel(jpath),
    }
    extra['whitelist'] = {
        'path': step.get('whitelist'),
        'registered': counts['registered'],
        'registered_declared': (wdoc or {}).get('registered_count'),
        'registered_source': (wdoc or {}).get('registered_source'),
        'registered_appended': counts['registered_appended'],
        'registered_total': counts['registered_total'],
        'appended_paths': counts['appended_paths'],
        'appended_meta': counts['appended_meta'],
        'registered_rules': m['registered_rules'],
        'wildcard_rules': [{'id': r['id'], 'glob': r['glob'], 'hits': m['rule_hits'][r['id']]}
                           for r in rules],
        'unregistered_count': len(m['unregistered']),
        'unregistered_first10': ['%s|%s' % kp for kp in m['unregistered'][:10]],
        'stale_count': len(m['stale_exact']) + len(m['stale_rules']),
        'stale_exact_count': len(m['stale_exact']),
        'stale_rule_ids': m['stale_rules'],
        'stale_first10': ['%s|%s' % kp for kp in m['stale_exact'][:10]],
        'covered_by_rules_count': len(m['covered_by_rules']),
        'a89_note': ('A-89/V-01：%s 由通配规则表达（不逐条枚举）；'
                     '通配规则匹配 0 条即 stale' % ARCHIVE_ROOT_GLOB),
    }
    # 白名单条目清单随报告落盘（供审计：这条约束当前到底由哪些条目构成）
    if wdoc is not None:
        mpath, _renamed = guard_write(os.path.join(run_dir, 'evidence_whitelist.registered.json'))
        with open(mpath, 'w', encoding='utf-8', newline='\n') as fh:
            json.dump(wdoc, fh, ensure_ascii=False, indent=1)
        extra['whitelist']['manifest'] = _rel(mpath)

    checks.append({'kind': 'whitelist', 'needle': 'no unregistered violation',
                   'status': 'passed' if not m['unregistered'] else 'failed'})
    checks.append({'kind': 'whitelist', 'needle': 'whitelist has no stale exact entry',
                   'status': 'passed' if not m['stale_exact'] else 'failed'})
    checks.append({'kind': 'whitelist', 'needle': 'wildcard rule(s) match >=1 violation',
                   'status': 'passed' if not m['stale_rules'] else 'failed'})
    checks.append({'kind': 'pinned', 'needle': 'real_db_matches_pinned == true',
                   'status': 'passed' if pinned else 'failed'})
    return checks, extra


# ------------------------------------------------------------------ 注入破坏夹具（形态 ⑦）
def _inj_ctx(python_exe):
    root = os.path.join(TMP_ROOT, 'inject')
    os.makedirs(root, exist_ok=True)
    return {'python': python_exe, 'root': root}


def _inj_fresh(ctx, name):
    d = os.path.join(ctx['root'], name)
    if os.path.isdir(d):
        shutil.rmtree(d)
    os.makedirs(d)
    return d


def _inj_mkdirs(path):
    if path and not os.path.isdir(path):
        os.makedirs(path)
    return path


def _inj_copy(src, dst):
    _inj_mkdirs(os.path.dirname(dst))
    shutil.copy2(src, dst)
    return dst


def _inj_write(path, text):
    _inj_mkdirs(os.path.dirname(path))
    with open(path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(text)
    return path


def _inj_fixture(ctx, step_id):
    d = _inj_fresh(ctx, step_id)
    path = os.path.join(d, 'fixture_%s.py' % step_id)
    return _inj_write(path, FIXTURE_TEMPLATE % {'step': step_id,
                                               'lines': FIXTURE_LINES[step_id], 'code': 1})


def _inj_check_templates(ctx):
    """合成树 = 真 app/ 的 templates + permissions + 7 个 route 文件 + **1 个模板注入未登记能力**。

    脚本副本放在 `<syn>/scripts/check_templates.py` ⇒ 其 `ROOT = dirname(dirname(__file__)) = <syn>`
    ⇒ 扫描合成树（与 E-04-b「坏树副本」同一手法）。
    """
    syn = _inj_fresh(ctx, 'check_templates')
    shutil.copytree(os.path.join(REPO_ROOT, 'app', 'templates'),
                    os.path.join(syn, 'app', 'templates'))
    _inj_copy(os.path.join(REPO_ROOT, 'app', 'permissions.py'),
              os.path.join(syn, 'app', 'permissions.py'))
    for rel in TEMPLATE_ROUTE_FILES:
        _inj_copy(os.path.join(REPO_ROOT, rel), os.path.join(syn, rel))
    script = _inj_copy(os.path.join(SCRIPTS_DIR, 'check_templates.py'),
                       os.path.join(syn, 'scripts', 'check_templates.py'))
    tpls = []
    for dirpath, _dirs, files in os.walk(os.path.join(syn, 'app', 'templates')):
        for fn in files:
            if fn.endswith('.html'):
                tpls.append(os.path.join(dirpath, fn))
    tpls.sort()
    target = tpls[0]
    with open(target, 'a', encoding='utf-8', newline='\n') as fh:
        fh.write("\n{# V-01 注入：未登记能力 #}\n"
                 "{% if can('__v01_injected_unknown_capability__') %}<!-- x -->{% endif %}\n")
    return {'kind': 'real_input', 'replace_script': script,
            'fixtures': [_rel(syn), _rel(target)],
            'evidence': {'tree': _rel(syn), 'templates_total': len(tpls),
                         'degradation': '在 %s 追加 can(%r) ⇒ 未登记能力 ⇒ RESULT: FAIL'
                                        % (_rel(target), '__v01_injected_unknown_capability__')}}


def _inj_check_migration_heads(ctx):
    """合成树 = 真脚本副本 + 2 个互不为祖先的 revision ⇒ head_count=2 ≠ 1。"""
    syn = _inj_fresh(ctx, 'check_migration_heads')
    script = _inj_copy(os.path.join(SCRIPTS_DIR, 'check_migration_heads.py'),
                       os.path.join(syn, 'scripts', 'check_migration_heads.py'))
    vers = os.path.join(syn, 'migrations', 'versions')
    _inj_mkdirs(vers)
    for rev in ('aaaa0001', 'bbbb0002'):
        _inj_write(os.path.join(vers, '%s_x.py' % rev),
                   "revision = '%s'\ndown_revision = None\nbranch_labels = None\n"
                   "depends_on = None\n\n\ndef upgrade():\n    pass\n\n\n"
                   "def downgrade():\n    pass\n" % rev)
    return {'kind': 'real_input', 'replace_script': script, 'fixtures': [_rel(syn)],
            'evidence': {'tree': _rel(syn), 'degradation': '2 个独立 head（aaaa0001 / bbbb0002）'}}


def _inj_check_properties(ctx):
    """合成树 = 真 app/models.py 副本 + 1 个类级访问 @property 的文件（A 类违规）。"""
    syn = _inj_fresh(ctx, 'check_properties')
    _inj_copy(os.path.join(REPO_ROOT, 'app', 'models.py'), os.path.join(syn, 'models.py'))
    bad = _inj_write(os.path.join(syn, 'bad_ref.py'),
                     'from models import Employee\n\n\ndef bad():\n'
                     "    return Employee.query.filter(Employee.status == 'active').all()\n")
    return {'kind': 'real_input', 'append_argv': ['--root', syn], 'fixtures': [_rel(bad)],
            'evidence': {'tree': _rel(syn),
                         'degradation': 'Employee.status 是 @property 却作类级访问（A 类违规）'}}


def _inj_check_model_refs(ctx):
    """合成坏树 = 1 个 `Widget.query`（大写名未绑定）⇒ violations >= 1。"""
    syn = _inj_fresh(ctx, 'check_model_refs')
    bad = _inj_write(os.path.join(syn, 'main', 'bad.py'),
                     'def bad_endpoint(item_id):\n'
                     '    row = Widget.query.get_or_404(item_id)\n'
                     "    return {'id': row.id}\n")
    return {'kind': 'real_input', 'append_argv': ['--root', syn], 'fixtures': [_rel(bad)],
            'evidence': {'tree': _rel(syn),
                         'degradation': 'Widget.query（无绑定的大写名）⇒ violations 1'}}


def _inj_check_http_contract(ctx):
    """合成树 = 1 个裸捕 `request.get_json()` 的站点 ⇒ sites=1 ≠ 基线 10。"""
    syn = _inj_fresh(ctx, 'check_http_contract')
    bad = _inj_write(os.path.join(syn, 'main', 'bad.py'),
                     'from flask import request, jsonify\n\n\ndef bad_json():\n'
                     '    try:\n        data = request.get_json()\n'
                     '    except Exception as e:\n'
                     "        return jsonify({'message': str(e)}), 500\n")
    return {'kind': 'real_input', 'append_argv': ['--roots', syn], 'fixtures': [_rel(bad)],
            'evidence': {'tree': _rel(syn),
                         'degradation': 'get_json() 被 except Exception 吞掉 ⇒ sites 1（期望 10）'}}


def _inj_evidence_hash(ctx):
    """合成证据树：先 `--freeze` 建索引，再篡改 1 个文件 ⇒ 必须报 `modified`（新违规 ⇒ 失败）。

    注意：该篡改**不在** `_phaseB-prefreeze/**` 之下 ⇒ 通配规则不得把它吞掉
    （顺带证明 A-89 的通配规则没有放宽任何其它路径的约束）。
    """
    syn = _inj_fresh(ctx, 'evidence_hash')
    ev = os.path.join(syn, 'ev')
    _inj_mkdirs(os.path.join(ev, 'sub'))
    target = _inj_write(os.path.join(ev, 'sub', 'a.txt'), 'original\n')
    res = run_child(['-B', os.path.join(HERE, 'evidence_hash.py'),
                     '--evidence-root', ev, '--freeze'],
                    cwd=REPO_ROOT, timeout=600, label='v01_inj_eh_freeze')
    if res['exit_code'] != 0:
        raise RuntimeError('注入夹具准备失败：合成证据树 --freeze exit=%s' % res['exit_code'])
    with open(target, 'a', encoding='utf-8', newline='\n') as fh:
        fh.write('tampered-by-v01-injection\n')
    return {'kind': 'real_input', 'append_argv': ['--evidence-root', ev], 'fixtures': [_rel(syn)],
            'evidence': {'tree': _rel(syn), 'freeze_exit': res['exit_code'],
                         'degradation': 'freeze 后篡改 %s（位于通配规则覆盖范围之外）' % _rel(target)}}


def _inj_coverage_drift(ctx):
    """把评判用的 coverage.json 换成「LOCKED 下界被下调 1」的副本 ⇒ 「不许退化」判据必须报红。"""
    src = os.path.join(REPORTS_ROOT, 'evidence', 'harness', 'coverage.json')
    if not os.path.isfile(src):
        raise RuntimeError('注入夹具准备失败：找不到锚点 coverage.json：%s' % src)
    with open(src, encoding='utf-8') as fh:
        doc = json.load(fh)
    summary = doc.get('summary') or {}
    key = 'writable_any_covered_by_all'
    if key not in summary:
        raise RuntimeError('注入夹具准备失败：coverage.json summary 无 %s' % key)
    before = summary[key]
    summary[key] = before - 1
    syn = _inj_fresh(ctx, 'coverage_drift')
    path = _inj_write(os.path.join(syn, 'coverage_degraded.json'),
                      json.dumps(doc, ensure_ascii=False, indent=1))
    return {'kind': 'real_input', 'set_flag': ('--coverage', path), 'fixtures': [_rel(path)],
            'evidence': {'source': _rel(src), 'degraded': {key: [before, before - 1]},
                         'degradation': 'LOCKED 是不许退化的下界：%s %s => %s'
                                        % (key, before, before - 1)}}


def _inj_run_gates(ctx):
    """`judge_artifact`：本步程序照常真跑，但**判据层读的 gates.json** 换成合成的降级产物。"""
    syn = _inj_fresh(ctx, 'run_gates')
    doc = {
        'harness': 'run_gates.py',
        'run_id': 'v01-injection',
        'repo_root': REPO_ROOT,
        'gates': [{
            'gate': '__v01_injected_degraded_gate__',
            'script': '<injected>',
            'mode': 'native',
            'command': '<injected degraded artifact>',
            'exit_code': 1, 'expected_exit_code': 0, 'exit_code_informative': True,
            'checks': [{'fact': 'v01_injection', 'expected': 0, 'actual': 1,
                        'status': 'failed'}],
            'verdict': 'fail', 'evidence_level': 'synthetic', 'real_db_unchanged': True,
        }],
        'summary': {'total': 1, 'pass': 0, 'fail': 1, 'probe_only': 0, 'probe_unexpected': 0,
                    'exit_code_informative': 1,
                    'in_gate_chain': ['__v01_injected_degraded_gate__']},
        'exit_code_semantics': {'code': 1, 'rule': 'synthetic degraded artifact (V-01 injection)'},
    }
    path = _inj_write(os.path.join(syn, 'gates.degraded.json'),
                      json.dumps(doc, ensure_ascii=False, indent=1))
    return {'kind': 'judge_artifact', 'judge_artifact': {'gates_json': path},
            'fixtures': [_rel(path)],
            'evidence': {'degraded_artifact': _rel(path),
                         'degradation': 'summary.fail=1 + 1 个进链门禁 verdict=fail ⇒ 判据层必须报红'}}


def _inj_script_fixture(ctx, step_id):
    path = _inj_fixture(ctx, step_id)
    return {'kind': 'script_fixture', 'replace_script': path, 'fixtures': [_rel(path)],
            'evidence': {'fixture': _rel(path),
                         'degradation': '该步无输入路径参数（跑真 app/真库）⇒ 把「要跑的程序」'
                                        '换成故意不合规的夹具：%s' % FIXTURE_LINES[step_id][0]}}


#: B13-09 注入用的调用点正则（只认 `notify_*` **调用**，不认 `def notify_*` 定义与非调用引用）
_NOTIFY_CALL_RE = re.compile(
    r'(?<![\w.])notify_(?:process_change|spec_change|inventory_warning|task_assignment'
    r'|raw_substitution)\s*\(')


def _inj_check_notification_triggers(ctx):
    """合成树 = 真 `notification_service.py` + 真 `routes.py` 副本，并把其中**全部触发器调用点注释掉**。

    与真树当前是否已接线无关（注入树恒为 wired=0 < expect 4）⇒ `--expect 4` 下该步必红，
    即「把接线调用点注释掉 ⇒ 门禁报红」的注入自证。
    """
    syn = _inj_fresh(ctx, 'check_notification_triggers')
    app = os.path.join(syn, 'app')
    fixtures, commented = [], 0
    for rel in ('app/services/notification_service.py', 'app/main/routes.py'):
        dst = _inj_copy(os.path.join(REPO_ROOT, rel.replace('/', os.sep)),
                        os.path.join(app, rel.replace('/', os.sep)))
        with open(dst, encoding='utf-8') as fh:
            lines = fh.readlines()
        out = []
        for line in lines:
            stripped = line.lstrip()
            if (not stripped.startswith(('def ', 'async def '))
                    and _NOTIFY_CALL_RE.search(line)):
                out.append('# [V-01 注入] ' + line)
                commented += 1
            else:
                out.append(line)
        with open(dst, 'w', encoding='utf-8', newline='\n') as fh:
            fh.writelines(out)
        fixtures.append(_rel(dst))
    return {'kind': 'real_input', 'append_argv': ['--root', app], 'fixtures': fixtures,
            'evidence': {'tree': _rel(app), 'call_sites_commented': commented,
                         'degradation': '通知触发器调用点全部注释掉（%d 处）⇒ wired 0 ≠ expect 4'
                                        % commented}}


def _inj_chain_count_consistency(ctx):
    """合成「判据输入声明」：宣称报工链一侧多 1 件 ⇒ 脚本必须 exit 1 且指名侧别。

    只改**输入路径**（`--perturb` 的 JSON 声明），不碰判据、不写任何库：脚本读到「A 侧 = 报工件数 + 1」
    就必红（C-B15-07.a 的相等判据），并按归因规则指出偏离侧 = `report`。
    """
    payload = {'side': 'report', 'delta': 1,
               'reason': 'V-01 注入（B15-07）：合成「报工链件数合计 +1」的判据输入声明'}
    return {'kind': 'real_input', 'append_argv': ['--perturb', json.dumps(payload, ensure_ascii=False)],
            'fixtures': [],
            'evidence': {'perturbation': payload,
                         'degradation': '报工链件数合计按声明 +1 ⇒ C-B15-07.a 必红、exit 1、'
                                        '指名侧别 report（台账一字未动：只改判据输入）'}}


#: B17-16/B17-19：`check_doc_claims.py --coverage` 的注入源 = **不可变归档锚点**。
#: A-114（挂点与产物分离）：判据必须从归档快照读，`evidence/harness/coverage.json` 是会被
#: 「原地写出」的活路径 ⇒ 注入夹具以归档 run 目录里的那份为源（缺失即夹具准备失败）。
COVERAGE_ARCHIVE_ANCHOR = os.path.join(REPORTS_ROOT, 'evidence', 'harness',
                                       'ci-run-20261009-054416', 'coverage.json')


def _inj_check_is_archived(ctx):
    """合成 `app/` 树 = 真树里**本脚本扫描面**（`*.py` / `*.html`）的副本 + 1 处**未登记**读取点。

    只改 `--root`（判据不动）⇒ 合成树比真树多 1 处 `BARE_FALSE` 读点，登记表必须报「未登记读取点」
    并以 exit 1 转红。
    """
    syn = _inj_fresh(ctx, 'check_is_archived')
    copied = 0
    for dirpath, dirnames, filenames in os.walk(os.path.join(REPO_ROOT, 'app')):
        dirnames[:] = [d for d in dirnames if d != '__pycache__']
        for name in filenames:
            if not name.endswith(('.py', '.html')):
                continue
            src = os.path.join(dirpath, name)
            _inj_copy(src, os.path.join(syn, os.path.relpath(src, REPO_ROOT)))
            copied += 1
    dst = os.path.join(syn, 'app', 'main', 'routes.py')
    with open(dst, 'a', encoding='utf-8', newline='\n') as fh:
        fh.write('\n_zz_v01_probe = RawMaterial.query.filter('
                 'RawMaterial.is_archived == False).count()\n')
    return {'kind': 'real_input', 'append_argv': ['--root', syn], 'fixtures': [_rel(dst)],
            'evidence': {'tree': _rel(syn), 'files_copied': copied,
                         'degradation': '合成树 %s 末尾追加 1 处未登记读取点（BARE_FALSE：裸 '
                                        'is_archived == False）⇒ 登记表必须报 exit 1' % _rel(dst)}}


def _inj_check_doc_claims(ctx):
    """`--coverage` 指向归档锚点副本（`summary.writable_any_covered_by_all` 下调 1）⇒ 必红。

    只改输入路径（argv 里 `--coverage` 的后一个值）：该键漂移 1 会同时打断派生键
    `non_get_uncovered_method_level` ⇒ 「钉常量 vs 权威源」至少报 2 条 violation。
    """
    src = COVERAGE_ARCHIVE_ANCHOR
    if not os.path.isfile(src):
        raise RuntimeError('注入夹具准备失败：找不到归档锚点 coverage.json：%s' % src)
    with open(src, encoding='utf-8') as fh:
        doc = json.load(fh)
    summary = doc.get('summary') or {}
    key = 'writable_any_covered_by_all'
    if key not in summary:
        raise RuntimeError('注入夹具准备失败：锚点 coverage.json summary 无 %s' % key)
    before = summary[key]
    summary[key] = before - 1
    syn = _inj_fresh(ctx, 'check_doc_claims')
    path = _inj_write(os.path.join(syn, 'coverage_drifted.json'),
                      json.dumps(doc, ensure_ascii=False, indent=1))
    return {'kind': 'real_input', 'set_flag': ('--coverage', path), 'fixtures': [_rel(path)],
            'evidence': {'source': _rel(src), 'degraded': {key: [before, before - 1]},
                         'degradation': '口径源被下调 1（%s %s => %s）⇒ 钉常量 vs 权威源必报漂移'
                                        % (key, before, before - 1)}}


#: 每步 1 次注入（形态 ⑦：只改输入路径，不动判据）——判据 ② 的机读依据
INJECTIONS = {
    'check_templates': {'kind': 'real_input', 'builder': _inj_check_templates,
                        'how': '合成树副本（真 templates + permissions + 7 route 文件）+ 1 个模板注入未登记能力'},
    'check_migration_heads': {'kind': 'real_input', 'builder': _inj_check_migration_heads,
                              'how': '脚本副本按原相对深度放置 + 2 个独立 head 的合成 migrations/versions'},
    'check_properties': {'kind': 'real_input',
                         'builder': lambda ctx: _inj_check_properties(ctx),
                         'how': '--root 指向合成树（models.py 副本 + 类级访问 @property 的违规文件）'},
    'check_db_bootstrap': {'kind': 'script_fixture',
                           'builder': lambda ctx: _inj_script_fixture(ctx, 'check_db_bootstrap'),
                           'how': '换掉被跑的脚本为不合规夹具（该步无输入路径参数）'},
    'run_gates': {'kind': 'judge_artifact', 'builder': _inj_run_gates,
                  'how': '本步真跑；判据层读的 gates.json 换成合成降级产物（summary.fail=1）'},
    'functional_test': {'kind': 'script_fixture',
                        'builder': lambda ctx: _inj_script_fixture(ctx, 'functional_test'),
                        'how': '换掉被跑的脚本为不合规夹具（该步无输入路径参数）'},
    'permission_matrix': {'kind': 'script_fixture',
                          'builder': lambda ctx: _inj_script_fixture(ctx, 'permission_matrix'),
                          'how': '换掉被跑的脚本为不合规夹具（该步无输入路径参数）'},
    'smoke_test': {'kind': 'script_fixture',
                   'builder': lambda ctx: _inj_script_fixture(ctx, 'smoke_test'),
                   'how': '换掉被跑的脚本为不合规夹具（该步无输入路径参数）'},
    'route_inventory': {'kind': 'script_fixture',
                        'builder': lambda ctx: _inj_script_fixture(ctx, 'route_inventory'),
                        'how': '换掉被跑的脚本为不合规夹具（该步无输入路径参数）'},
    'measure_coverage': {'kind': 'script_fixture',
                         'builder': lambda ctx: _inj_script_fixture(ctx, 'measure_coverage'),
                         'how': '换掉被跑的脚本为不合规夹具（该步无输入路径参数）'},
    'coverage_drift': {'kind': 'real_input', 'builder': _inj_coverage_drift,
                       'how': '--coverage 指向 LOCKED 下界被下调 1 的合成 coverage.json'},
    'check_model_refs': {'kind': 'real_input', 'builder': _inj_check_model_refs,
                         'how': '--root 指向合成坏树（Widget.query 未绑定）'},
    'check_http_contract': {'kind': 'real_input', 'builder': _inj_check_http_contract,
                            'how': '--roots 指向合成树（裸捕 get_json() 的 1 个站点）'},
    'evidence_hash': {'kind': 'real_input', 'builder': _inj_evidence_hash,
                      'how': '--evidence-root 指向「freeze 后篡改 1 个文件」的合成证据树'},
    'check_notification_triggers': {
        'kind': 'real_input', 'builder': _inj_check_notification_triggers,
        'how': '--root 指向合成树（真 notification_service.py + 真 routes.py 副本，'
               '其中全部 notify_* 调用点被注释掉）⇒ wired 0 ≠ expect 4'},
    'chain_count_consistency': {
        'kind': 'real_input', 'builder': _inj_chain_count_consistency,
        'how': '--perturb 合成「报工链件数合计 +1」的判据输入声明（不碰判据/不写库）⇒ '
               'C-B15-07.a 必红、exit 1、指名侧别 report'},
    # ---- B17-15 / B17-07 / B17-16（2026-10-09，追加末位 17/18/19）----------------------
    'negative_matrix': {
        'kind': 'script_fixture',
        'builder': lambda ctx: _inj_script_fixture(ctx, 'negative_matrix'),
        'how': '换掉被跑的脚本为不合规夹具（该步无输入路径参数：默认就跑四类必交 + 阳性对照）'},
    'check_is_archived_policy': {
        'kind': 'real_input', 'builder': _inj_check_is_archived,
        'how': '--root 指向合成 app 树（真树扫描面副本 + 末尾 1 处未登记 is_archived 读取点）'},
    'check_doc_claims': {
        'kind': 'real_input', 'builder': _inj_check_doc_claims,
        'how': '--coverage 指向归档锚点副本（summary.writable_any_covered_by_all 下调 1）'
               '⇒ 口径源漂移、exit 1'},
}


def build_injection(step_id, ctx):
    """按表构造注入（返回 dict；`builder` 抛异常即为夹具准备失败 —— 不得静默跳过）。"""
    spec = INJECTIONS.get(step_id)
    if spec is None:
        raise RuntimeError('未知步骤（INJECTIONS 表未声明）：%s' % step_id)
    out = dict(spec['builder'](ctx))
    out['step'] = step_id
    out.setdefault('fixtures', [])
    out.setdefault('evidence', {})
    out['how'] = spec['how']
    out['declared_kind'] = spec['kind']
    return out


def criterion_fingerprint(step):
    """判据指纹：注入前后必须相等（形态 ⑦「只改输入路径、不改判据」的机检）。"""
    payload = {
        'id': step['id'], 'mode': step.get('mode'), 'hook': step.get('hook'),
        'expects': step.get('expects'), 'expect_absent': step.get('expect_absent'),
        'expect_exit': step.get('expect_exit'), 'known_bad_absent': step.get('known_bad_absent'),
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode('utf-8')
    return hashlib.sha256(blob).hexdigest().upper()


def _script_index(argv_step):
    """argv 里「被跑的脚本」位置：最后一个 `.py` 参数（shim 场景下 shim 在前、目标在后）。"""
    for i in range(len(argv_step) - 1, -1, -1):
        if str(argv_step[i]).endswith('.py'):
            return i
    return None


# ------------------------------------------------------------------ 步骤表
def spec_steps(python_exe, check_templates_script=None,
               evidence_whitelist=DEFAULT_EVIDENCE_WHITELIST):
    """§2 的九条命令 + 判据层链路 + A-85 三接入位（分组见模块 docstring）。"""
    exe = python_exe
    shim = os.path.join('scripts', '_sandbox_compat.py')
    return [
        {'id': 'check_templates', 'group': 'blocking',
         'argv': [exe, '-B', check_templates_script or os.path.join('scripts', 'check_templates.py')],
         'expect_exit': 0,
         'expects': ['[templates] parsed 86 files',
                     '[permissions] 44 declared / 40 used in templates / 44 used on routes',
                     '[landing] 5 role landing endpoints', 'RESULT: OK']},
        {'id': 'check_migration_heads', 'group': 'blocking',
         'argv': [exe, '-B', os.path.join('scripts', 'check_migration_heads.py')],
         'expect_exit': 0,
         'expects': ["HEADS=['p1nonctarget']", 'head_count=1', 'revisions=35']},
        # 【B17-16 重基线（A-70 三步，2026-10-09）】needle 26 → 25：B17-01 删掉死文件
        # app/main/sales_routes.py（1 字节空文件，无模型类）⇒ check_properties 扫到的文件数 26 → 25，
        # 模型类 74 不变。四处同改（run_gates.EXPECTED.properties_files / 本 needle /
        # check_doc_claims.PINNED / AGENTS.md 门禁表），改前/改后与阴性对照读数见
        # test-reports-2026-10/B17-登记.md §B17-16。
        {'id': 'check_properties', 'group': 'blocking',
         'argv': [exe, '-B', os.path.join('scripts', 'check_properties.py'), '--selftest'],
         'expect_exit': 0,
         # [G] 加性 --selftest：自检统计行必须出现，且**扫描面判据一字未动**（`--root` 注入仍有效）。
         'expects': ['已扫描 25 个文件，模型类 74 个', 'RESULT: OK', '[check_properties] 自检 22/22 通过']},
        # B14-R1（2026-10-09）：回退 ALLOY-IMPORT-02 真库导入造成的期望漂移 —— 导入期曾把本步
        # 期望串与 run_gates 的 bootstrap_copied_rows 一起抬到 10172（真库 +1080 产品 / +1728 BOM
        # 明细等）。真实库已还原为导入前锚点（2531328 B / F5DA2306…0F065），故两处一起回退到
        # 干净库现场实测值 6712（run ci-run-20261009-005619 的 ci_check_db_bootstrap.out:4）。
        # 【B15/RF-1 重基线（2026-10/批次15，append-only 订正上一条）】用户拍板「真库重基线」后，
        # 真实 app.db 由 t2 完成首启播种：inspection_templates +2（production_record / goods_receipt）
        # + inspection_items +7 ⇒ bootstrap business 行数 6712 → 6721。旧 needle 在新锚点下报红
        # （`!! expects 直接拷贝 6712 行，跳过 0 张表`，run cf. evidence rf1-before-red.txt），
        # 故按 A-70 三步重基线到 6721；数值来源 = 本步子进程自报的 `直接拷贝 6721 行，跳过 0 张表`。
        # 【严禁】在此基础上再抬数：真库只此一次重基线（RF-1 经用户拍板），此后本 needle 与真库
        # 字节锚定（real_db_sha256 B4FB980C…EABE / 2531328 B）同源。
        {'id': 'check_db_bootstrap', 'group': 'blocking',
         'argv': [exe, '-B', shim, os.path.join('scripts', 'check_db_bootstrap.py')],
         'expect_exit': 0,
         'expects': ['种子库账号数（经自举导入到空库）= 64', '直接拷贝 6721 行，跳过 0 张表',
                     'OK: 空库自举、幂等、无种子库跳过、整表无遗漏 均通过']},
        {'id': 'run_gates', 'group': 'blocking', 'mode': 'run_gates',
         'argv': [exe, '-B', os.path.join('test-reports-2026-10', 'harness', 'run_gates.py')],
         'expect_exit': None,          # A-62：环境依赖探针不匹配时退出码为 1，属预期
         'expects': ['[run_gates] probe_unexpected = ']},
        {'id': 'functional_test', 'group': 'blocking',
         'argv': [exe, '-B', shim, os.path.join('scripts', 'functional_test.py')],
         'expect_exit': 0,
         'expects': ['结果：127 通过 / 0 失败']},
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
         'expects': ['[routes] total rules=272', 'duplicate (method,path) registrations=0'],
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
        # B13-09（blocking）：通知触发器**真的**被接线吗（AST：每个 `def notify_*` 至少 1 个
        # 非定义处调用点）。目标态 = 5 个触发器里 4 个接线：
        #   * `notify_inventory_warning` —— 按 §7.2 拍板项 6（min_stock 数据源仓库内不存在，
        #     零 schema 变更的 SystemConfig 值由业务给）**永久豁免**，锚点 = 81-:860（同行共现
        #     `notify_inventory_warning` + `只登记`）；
        #   * 另 3 个由 t9/B13-06 接线，落线前用 `--pending-wiring` 显式登记（落线后自动消费、
        #     不报红）⇒ **B13-06 落线前本步为红是正确读数**（plan :177「未接线 ⇒ exit 1」），
        #     落线后 wired 4 == expect 4 自动转绿，无需再改本步。
        # 【严禁】把 `--expect` 写成 5 或去掉 `--allow-unwired`：那会逼出「为凑数接线一个没有
        # 数据源的触发器」的不诚实结果；也严禁为了变绿而放宽任何判据。
        {'id': 'check_notification_triggers', 'group': 'blocking',
         'argv': [exe, '-B', os.path.join('scripts', 'check_notification_triggers.py'),
                  '--expect', '4',
                  '--allow-unwired', 'notify_inventory_warning',
                  '--pending-wiring', 'notify_process_change',
                  '--pending-wiring', 'notify_spec_change',
                  '--pending-wiring', 'notify_task_assignment'],
         'expect_exit': 0,
         'expects': ['triggers=5 wired=4 unwired=1 expect=4',
                     'allow-unwired (permanent) anchor=test-reports-2026-10/81-',
                     'RESULT: OK'],
         'expect_absent': ['UNREGISTERED-TRIGGER'],
         'note': 'B13-09 / G-11：通知触发器接线门禁（AST 调用点，非人读代码）。豁免与待办'
                 '都在仓库内有可见锚点；永久豁免无法匿名、临时豁免被禁（UNREGISTERED-EXEMPTION）。'},
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
                 '（精确 33 条 + %s 通配 1 条，A-89）+ 通配规则匹配数 > 0 + real_db 钉值未变。'
                 '--no-strict-coverage 的理由见上方注释（allowlist 语义 + 去噪声）。'
                 % ARCHIVE_ROOT_GLOB},
        # ---- B15-07（I5，blocking）：报工链 / 工件链 fg **件数合计**守恒对拍 ---------------
        # 判据（口径勿动）：① 脚本在**副本库**里同一批次实例上把两条链各跑一次，读
        #   件数合计（`SUM(finished_product.quantity)` / `SUM(production_record.quantity)`）
        #   而不是行数 ⇒ 期望「两侧相等且等于报工件数」；② 自带「A 1 行 N 件 vs B N 行 1 件」
        #   的构造，证明判据与行数**解耦**（若改读行数 ⇒ 1 != 3 假红）；③ 判据不满足或缺参
        #   ⇒ 脚本 exit 1/2（exit 0 只表示 6 条判据全过）。脚本自报行见 expects。
        # 分组理由：件数守恒是**确定性**判据（不依赖环境探针、不写真实库），且注入必须能把它
        # 打成红（见 INJECTIONS 的 --perturb 注入）⇒ 进 blocking，不用 report-only 蒙过。
        # 耗时说明：本步真建副本库 + 两链各跑一次（在办质检任务按实测顺序后建），单步约 1~2 分钟。
        {'id': 'chain_count_consistency', 'group': 'blocking',
         'argv': [exe, '-B', os.path.join('test-reports-2026-10', 'harness',
                                          'chain_count_consistency.py')],
         'extra_argv': [{'tail': ['--out', '{json}'],
                         'json_name': 'chain_count_consistency.json'}],
         'expect_exit': 0,
         'expects': ['[cc] 口径 = SUM(finished_product.quantity) 件数合计（禁止用行数）',
                     '[OK] C-B15-07.a 两侧件数守恒',
                     '[OK] C-B15-07.a2 行数与件数不同构',
                     '[OK] C-B15-07.b 两侧基数均 > 0',
                     '[cc] 判据：6 条通过 / 0 条失败 / 0 条阻断',
                     '[cc] RESULT: OK'],
         'expect_absent': ['[FAIL] C-B15-07'],
         'note': 'B15-07 / I5：双链 fg 件数守恒（件数合计口径，禁止行数）。判据语义与退出码'
                 '（0=6 条全过 / 1=判据不满足 / 2=用法或参数错）见脚本 docstring；'
                 '注入形态 ⑦：`--perturb` 合成「一侧件数 ±1」的输入声明 ⇒ 必红并指名侧别。'},
        # ================= B17（批次17，2026-10-09）：追加末位 17/18/19 =====================
        # 为什么追加**末位**：既有 16 步的 id/顺序/判据一字不动（A-70「只增步」），新步只能加在
        # 尾部；`--list` 是步骤表的机器可读源，改完必须重取原文对照。
        # 【B17-15】negative_matrix 原先只在 test-reports 里裸跑、**不在任何门禁链**。
        # 分组理由：四类必交阴性用例是全链的**元判据**（真实库防误写 / 假开关差分 / 门禁阴性
        # 与阳性对照 / 夹具尺度），确定性、不依赖环境探针（t1 实测 28 条全 passed、7.5 s、
        # 真库 SHA256 未变）⇒ 进 blocking。
        # 判据口径（**勿改**）：该脚本**只在基础设施级问题**时才非 0（自跑完 = 0）⇒ 退出码不足以
        # 表示「全绿」，必须钉 `failed=0` 这条汇总行；`blocked=0` 一并钉（阻断=未真正执行）。
        # `合计 28 条`是**计数钉值**：用例族增减 ⇒ 本步报红并按 A-70 三步重基线
        # （登记见 test-reports-2026-10/B17-登记.md §B17-15）。
        {'id': 'negative_matrix', 'group': 'blocking',
         'argv': [exe, '-B', os.path.join(REPORTS_ROOT, 'harness', 'negative_matrix.py')],
         'extra_argv': [{'tail': ['--out', '{json}'], 'json_name': 'negative_matrix.json'}],
         'expect_exit': 0,
         'expects': ['[negative_matrix] 合计 28 条：passed=28 failed=0 blocked=0',
                     '[negative_matrix] 真实库异常？ 否（SHA256 未变）',
                     '[negative_matrix] 基础设施级问题：无'],
         'expect_absent': ['[FAILED ]'],
         'note': 'B17-15：阴性矩阵（四类必交 + 阳性对照）进链，blocking。范围 = 脚本默认族 '
                 'NV-1.x/NV-2.x/NV-3.x/NV-4.x/NV-5.x；`--out` 落本 run 目录（不写仓库根）。'
                 '⛔ 不得只靠退出码判绿：该脚本自跑完即 0，判据靠 `failed=0` / `blocked=0` 汇总行。'
                 '注入形态 ⑦：脚本无输入路径参数 ⇒ 换程序为不合规夹具（合计 3 条 failed=2 + '
                 '真库异常「是」）。'},
        # 【B17-07】is_archived 统一谓词的执法脚本：全仓读取点逐个登记
        # （UNIFIED = `or_(X.is_archived.is_(False), X.is_archived.is_(None))` / EXCEPTION = 带
        # 盘点快照与理由的非统一读法）。未登记的新增读点 ⇒ exit 1。
        # 扫描面写死在脚本头：`<root>/app/**/*.py` + `<root>/app/**/*.html`（模板面 10 处真值读）。
        {'id': 'check_is_archived_policy', 'group': 'blocking',
         'argv': [exe, '-B', os.path.join('scripts', 'check_is_archived_policy.py')],
         'expect_exit': 0,
         'expects': ['[is_archived] 登记表与现场逐组一致（无未登记新增、无计数漂移、无陈旧登记）',
                     'RESULT: OK'],
         'note': 'B17-07：`is_archived` 读取点逐个登记为 UNIFIED / EXCEPTION（带理由）；'
                 'EXCEPTION 必须带盘点快照（`app/services/mes_service.py` 加料预警 3 处裸 '
                 '`filter_by(is_archived=False)` = 唯一例外，真库无 NULL 行、行为不变）。'
                 '判据 = 未登记新增 / 组内计数漂移 / 陈旧登记（现场 0 处）/ 缺理由 / EXCEPTION 缺快照 '
                 '⇒ exit 1；行号漂移只 WARN（防行号漂移造成假红）。'
                 '注入形态 ⑦：`--root` 指向「真树扫描面副本 + 1 处未登记读点」的合成树 ⇒ 必红。'},
        # 【B17-16】口径守卫进链（blocking）：钉常量 ↔ 权威源 ↔ 报告口径表三级对拍的唯一消费者。
        # 判据输入：`--coverage <本 run 的 coverage.json>`（第 10 步 measure_coverage --out 的产物）
        # —— A-114 挂点与产物分离：**不得**改默认路径、**不得**读 live 覆盖写路径。
        # `--selftest` 不并在本步（该开关提前 return，会把口径面短路）⇒ 由验证命令单独跑 16/16。
        {'id': 'check_doc_claims', 'group': 'blocking',
         'argv': [exe, '-B', os.path.join('scripts', 'check_doc_claims.py')],
         'extra_argv': [{'tail': ['--coverage', '{json}'], 'json_name': 'coverage.json'}],
         'expect_exit': 0,
         'expects': ['[check_doc_claims] 钉常量 vs 权威源：20/20 相等',
                     '[check_doc_claims] 文档：扫描 4 份、带口径表 1 份',
                     '[check_doc_claims] RESULT: OK（violations=0）'],
         'expect_absent': ['[check_doc_claims] [VIOLATION]'],
         'note': 'B17-16：TL-06 口径守卫 + TL-07 依赖钉版一致性。判据 = ① 20 条钉常量逐条与权威源'
                 '实读相等（9 条 coverage 派生键从本 run 产物读）；② 扫描面 `5*.md`/`6*.md` 的口径表'
                 '逐键相等；③ `requirements.lock` 精确钉版 / 锁头 sha256 / 环境匹配（'
                 '`DEFAULT_ENV_EXCEPTIONS` = psycopg2-binary + pywin32）。'
                 '计数钉值（20/20、扫描 4 份带口径表 1 份）增减 ⇒ 本步报红并按 A-70 三步重基线。'
                 '注入形态 ⑦：`--coverage` 指向归档锚点副本（writable_any_covered_by_all −1）⇒ 必红。'},
    ]


def root_json_state():
    state = {}
    for name in ROOT_JSON:
        p = os.path.join(REPO_ROOT, name)
        state[name] = {'exists': os.path.exists(p),
                       'sha256': sha256_file(p) if os.path.exists(p) else None}
    return state


# ------------------------------------------------------------------ --selfcheck
def selfcheck(python_exe, whitelist=DEFAULT_EVIDENCE_WHITELIST, run_dir=None):
    """门禁清单自身的 8 条不变量（缺一 ⇒ 失败）。返回 ``(exit_code, report)``。"""
    steps = spec_steps(python_exe, evidence_whitelist=whitelist)
    ids = [s['id'] for s in steps]
    checks = []

    def add(name, ok, detail=''):
        checks.append({'check': name, 'status': 'passed' if ok else 'failed', 'detail': detail})

    add('step_count >= 14', len(steps) >= 14, 'step_count=%d' % len(steps))

    missing = sorted(set(ids) - set(INJECTIONS))
    extra = sorted(set(INJECTIONS) - set(ids))
    add('every step declares an injection (INJECTIONS covers all step ids)',
        not missing and not extra,
        'missing=%s extra=%s' % (missing or '[]', extra or '[]'))

    http = [s for s in steps if s['id'] == 'check_http_contract']
    bad_needles = [n for n in (http[0].get('expects') or []) if '自检' in n] if http else ['<no step>']
    add('check_http_contract expects must NOT contain the --selftest statistic line',
        http and not bad_needles, 'expects=%s' % ((http[0].get('expects') if http else None),))

    mr = [s for s in steps if s['id'] == 'check_model_refs']
    bad_cnt = [n for n in (mr[0].get('expects') or []) if 'name_query_refs' in n] if mr else ['<no step>']
    add('check_model_refs expects must NOT pin name_query_refs count',
        mr and not bad_cnt, 'expects=%s' % ((mr[0].get('expects') if mr else None),))

    eh = [s for s in steps if s['id'] == 'evidence_hash']
    eh_ok = bool(eh) and eh[0]['group'] == 'report-only' \
        and '--no-strict-coverage' in eh[0]['argv'] and '--strict-index' not in eh[0]['argv']
    add('TL-04 (evidence_hash) is report-only and does not use --strict-index',
        eh_ok, 'group=%s argv=%s' % (eh[0]['group'] if eh else None, eh[0]['argv'] if eh else None))

    reg, rules, reason, wdoc = load_whitelist(whitelist)
    counts = registration_counts(wdoc)
    add('whitelist loads with exact 33 base entries (appended block reported separately)',
        counts['registered'] == 33 and not reason,
        'registered=%d registered_appended=%d registered_total=%d reason=%s'
        % (counts['registered'], counts['registered_appended'], counts['registered_total'],
           reason or '-'))

    # 通配规则的 4 个对抗用例（证明「任意 stamp 覆盖」+「陈旧即失败」+「精确集不缩水」+「不越界」）
    reg_list = sorted(reg)
    case_new = reg_list + [('deleted', '_phaseB-prefreeze/20990101-000000/baseline-prefix/x.txt'),
                           ('modified', '_phaseB-prefreeze/20990101-000000/harness/y.json'),
                           ('phantom_entry', '_phaseB-prefreeze/20990101-000000/dir')]
    m_new = match_whitelist(case_new, reg, rules)
    ok_new = (not m_new['unregistered']) and (not m_new['stale_exact']) and (not m_new['stale_rules'])
    add('W-1 wildcard covers ANY stamp under %s' % ARCHIVE_ROOT_GLOB,
        ok_new, 'unregistered=%d stale_exact=%d stale_rules=%s hits=%s'
                % (len(m_new['unregistered']), len(m_new['stale_exact']),
                   m_new['stale_rules'], m_new['rule_hits']))

    m_gone = match_whitelist(reg_list, reg, rules)
    add('W-2 wildcard rule with 0 matches is reported stale (no silent widening)',
        bool(m_gone['stale_rules']), 'stale_rules=%s' % (m_gone['stale_rules'],))

    m_shrunk = match_whitelist(reg_list[1:], reg, rules)
    add('W-3 dropping an exact entry is reported stale (A-95 symmetric difference kept)',
        bool(m_shrunk['stale_exact']), 'stale_exact=%d' % len(m_shrunk['stale_exact']))

    m_look = match_whitelist(reg_list + [('modified', '_phaseB-prefreezeX/a.json')], reg, rules)
    add('W-4 look-alike dir outside the archive root is still a violation (glob not over-broad)',
        len(m_look['unregistered']) == 1, 'unregistered=%s'
        % ['%s|%s' % kp for kp in m_look['unregistered']])

    # 追加块（V-01）：登记后不算未登记；但同样纳入陈旧判定（只登记不裁决，不改变对称差集语义）
    base_list = sorted((it.get('kind'), it['path'])
                       for it in (wdoc or {}).get('violations', [])
                       if isinstance(it, dict) and it.get('path'))
    app_pairs = [it for it in (wdoc or {}).get('violations_appended', [])
                 if isinstance(it, dict) and it.get('path')]
    app_ok = True
    app_detail = 'appended=0'
    if app_pairs:
        ap = [(it.get('kind'), it['path']) for it in app_pairs]
        arch = ('deleted', '_phaseB-prefreeze/20990101-000000/baseline-prefix/x.txt')
        m_app = match_whitelist(base_list + ap + [arch], reg, rules)
        dropped = match_whitelist(base_list + ap[:-1] + [arch], reg, rules)
        app_ok = ((not m_app['unregistered']) and (not m_app['stale_exact'])
                  and (not m_app['stale_rules']) and len(dropped['stale_exact']) == 1)
        app_detail = ('appended=%d unregistered=%d stale_exact=%d stale_rules=%d '
                      'drop-one->stale_exact=%d'
                      % (len(ap), len(m_app['unregistered']), len(m_app['stale_exact']),
                         len(m_app['stale_rules']), len(dropped['stale_exact'])))
    add('W-5 appended block: registered (no unregistered) AND still subject to stale',
        app_ok, app_detail)

    add('build-layer blocking registered as blocked (A-63 step 2 pending)',
        BUILD_LAYER_BLOCKED.get('state') == 'blocked'
        and BUILD_LAYER_BLOCKED.get('not_counted_as_passed') is True,
        'id=%s owner=%s' % (BUILD_LAYER_BLOCKED['id'], BUILD_LAYER_BLOCKED['owner']))

    failed = [c['check'] for c in checks if c['status'] == 'failed']
    report = {
        'harness': 'ci_gates.py --selfcheck',
        'run_id': RUN_ID,
        'interpreter': python_exe,
        'step_count': len(steps),
        'step_ids': ids,
        'checks': checks,
        'failed': failed,
        'whitelist': {'path': whitelist, 'registered': len(reg), 'registered_declared':
                      (wdoc or {}).get('registered_count'), 'rules': rules},
        'gaps': [BUILD_LAYER_BLOCKED],
        'code': 1 if failed else 0,
    }
    for c in checks:
        print('[selfcheck] %-6s %s%s' % ('OK' if c['status'] == 'passed' else 'FAIL',
                                         c['check'], ('  -- %s' % c['detail']) if c['detail'] else ''))
    print('[selfcheck] step_count=%d failed=%s' % (len(steps), failed or '无'))
    if run_dir:
        path, _renamed = guard_write(os.path.join(run_dir, 'ci_gates.selfcheck.json'))
        with open(path, 'w', encoding='utf-8', newline='\n') as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
        report['path'] = _rel(path)
        print('[selfcheck] JSON -> %s' % _rel(path))
    return report['code'], report


# ------------------------------------------------------------------ 主流程
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
    ap.add_argument('--inject-step', default=None,
                    help='判据形态 ⑦：对某一步做 1 次注入破坏（只改输入路径；该步必须转红并被指名）')
    ap.add_argument('--selfcheck', action='store_true',
                    help='只跑「本清单自身」的不变量检查（步骤数 / 注入覆盖 / 统计行 / 白名单通配语义）')
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
    if args.inject_step and not args.only:
        args.only = args.inject_step
    if args.inject_step and args.only != args.inject_step:
        print('[ci_gates] --inject-step 与 --only 冲突：%s vs %s' % (args.inject_step, args.only))
        return 1
    if args.only:
        steps = [s for s in steps if s['id'] == args.only]
        if not steps:
            print('[ci_gates] 未知步骤: %s' % args.only)
            return 1
    if args.inject_step and args.inject_step not in INJECTIONS:
        print('[ci_gates] 未知注入步骤（INJECTIONS 表未声明）: %s' % args.inject_step)
        return 1

    run_name = RUN_ID if RUN_ID.startswith('ci-') else 'ci-%s' % RUN_ID
    run_dir = os.path.join(REPORTS_ROOT, 'evidence', 'harness', run_name)
    os.makedirs(run_dir, exist_ok=True)

    if args.selfcheck:
        code, _report = selfcheck(exe, whitelist=args.evidence_whitelist, run_dir=run_dir)
        return code

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
            inj = INJECTIONS.get(s['id'], {})
            print('[ci_gates] %-22s %-11s %s' % (s['id'], s['group'], ' '.join(argv)))
            print('[ci_gates]   inject: kind=%-15s %s' % (inj.get('kind', '-'),
                                                          inj.get('how', '-')))
        print('[ci_gates] phase=%s interpreter=%s steps=%d' % (args.phase, exe, len(steps)))
        return 0

    before = root_json_state()
    inj_ctx = _inj_ctx(exe) if args.inject_step else None

    results = []
    ineffective = []
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

        # ---- V-01 逐步注入破坏：只改输入路径，判据由指纹机检保持不变 ----
        injection = None
        if args.inject_step and s['id'] == args.inject_step:
            fp_before = criterion_fingerprint(s)
            injection = build_injection(s['id'], inj_ctx)
            if injection.get('replace_script'):
                idx = _script_index(argv_step)
                if idx is None:
                    raise RuntimeError('注入失败：argv 里找不到脚本参数：%s' % argv_step)
                argv_step[idx] = injection['replace_script']
            if injection.get('set_flag'):
                flag, value = injection['set_flag']
                if flag not in argv_step:
                    raise RuntimeError('注入失败：argv 里没有 %s：%s' % (flag, argv_step))
                argv_step[argv_step.index(flag) + 1] = value
            argv_step += list(injection.get('append_argv') or [])
            if injection.get('judge_artifact'):
                s['judge_artifact'] = injection['judge_artifact']
            fp_after = criterion_fingerprint(s)
            injection['criterion_sha256_before'] = fp_before
            injection['criterion_sha256_after'] = fp_after
            injection['criterion_unchanged'] = (fp_before == fp_after)

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
            jread = (s.get('judge_artifact') or {}).get('gates_json') or out_path
            gates = None
            if not os.path.isfile(jread):
                checks.append({'kind': 'gates_json',
                               'needle': 'gates.json 存在（run_gates --out）', 'status': 'failed'})
                extra = {'gates_json': _rel(jread), 'error': 'missing'}
            else:
                try:
                    with open(jread, encoding='utf-8') as fh:
                        gates = json.load(fh)
                except Exception as e:
                    checks.append({'kind': 'gates_json',
                                   'needle': 'gates.json 可解析', 'status': 'failed'})
                    extra = {'gates_json': _rel(jread),
                             'error': '%s: %s' % (type(e).__name__, e)}
            if gates is not None:
                summary = gates['summary']
                in_chain = [g for g in gates['gates'] if g['exit_code_informative']]
                probes = [g for g in gates['gates'] if g.get('probe_only')]
                fail_ok = summary['fail'] == 0
                chain_ok = all(g['verdict'] == 'pass' for g in in_chain)
                checks_ok = all(all(c['status'] == 'passed' for c in g['checks'])
                                for g in in_chain)
                checks.append({'kind': 'gates_json', 'needle': 'summary.fail == 0',
                               'status': 'passed' if fail_ok else 'failed'})
                checks.append({'kind': 'gates_json', 'needle': '4 项进链门禁全 pass',
                               'status': 'passed' if chain_ok else 'failed'})
                checks.append({'kind': 'gates_json', 'needle': '进链门禁逐项 checks 全过',
                               'status': 'passed' if checks_ok else 'failed'})
                extra = {
                    'gates_json': _rel(jread),
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
            extra = {'coverage_json': _rel(os.path.join(run_dir, 'coverage.json'))}

        status = 'passed' if all(c['status'] == 'passed' for c in checks) else 'failed'

        # ---- 注入的自我取证 + 「假注入」兜底：注入必须让该步转红，且判据指纹必须未变 ----
        if injection is not None:
            checks.append({'kind': 'injection',
                           'needle': 'criterion fingerprint unchanged (%s)'
                                     % injection['criterion_sha256_before'][:16],
                           'status': 'passed' if injection['criterion_unchanged'] else 'failed'})
            checks.append({'kind': 'injection', 'needle': 'injection turned the step red',
                           'status': 'passed' if status == 'failed' else 'failed'})
            if status != 'failed' or not injection['criterion_unchanged']:
                ineffective.append(s['id'])
            status = 'passed' if all(c['status'] == 'passed' for c in checks) else 'failed'
            extra['injection'] = injection

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
                 ('checks %d/%d' % (sum(1 for c in checks if c['status'] == 'passed'), len(checks)))))
        for c in checks:
            if c['status'] == 'failed':
                print('[ci_gates]      !! %s %s' % (c['kind'], c['needle']))
        if injection is not None:
            print('[ci_gates]      inject kind=%s criterion_unchanged=%s'
                  % (injection['kind'], injection['criterion_unchanged']))

    after = root_json_state()
    root_ok = all(before[n] == after[n] for n in ROOT_JSON)
    blocking_fail = [r['id'] for r in results if r['group'] == 'blocking' and r['status'] != 'passed']
    report_fail = [r['id'] for r in results if r['group'] == 'report-only' and r['status'] != 'passed']
    code = 1 if (blocking_fail or not root_ok or ineffective) else (2 if report_fail else 0)

    out = {
        'harness': 'ci_gates.py',
        'run_id': RUN_ID,
        'phase': args.phase,
        'interpreter': exe,
        'repo_root': REPO_ROOT,
        'step_count': len(results),
        'steps': results,
        'blocking_failed': blocking_fail,
        'report_only_failed': report_fail,
        'injection_ineffective': ineffective,
        'injection': next((r['injection'] for r in results if r.get('injection')), None),
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
            'rule': ('0 = 全部 blocking 通过; 1 = 有 blocking 失败（或仓库根 JSON 被写 / 注入未生效）; '
                     '2 = 仅 report-only 失败'),
            'inputs': {'blocking_failed': blocking_fail, 'report_only_failed': report_fail,
                       'root_json_untouched': root_ok, 'injection_ineffective': ineffective},
        },
        'promotion_note': SMOKE_PROMOTION_NOTE,
        'gaps': [BUILD_LAYER_BLOCKED],
    }

    print('[ci_gates] steps=%d blocking 失败 = %s' % (len(results), blocking_fail or '无'))
    print('[ci_gates] report-only 失败 = %s' % (report_fail or '无'))
    print('[ci_gates] 注入未生效 = %s' % (ineffective or '无'))
    print('[ci_gates] 仓库根两 JSON 未被触碰 = %s（A-11）' % root_ok)
    print('[ci_gates] gaps: %s = %s（不计入通过数）'
          % (BUILD_LAYER_BLOCKED['id'], BUILD_LAYER_BLOCKED['state']))
    print('[ci_gates] exit = %d  phase=%s' % (code, args.phase))
    print('[ci_gates] exit_code_semantics=' + json.dumps(out['exit_code_semantics'],
                                                         ensure_ascii=False))

    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
        path, renamed = guard_write(args.json)
        with open(path, 'w', encoding='utf-8', newline='\n') as fh:
            json.dump(out, fh, ensure_ascii=False, indent=2)
        print('[ci_gates] JSON -> %s%s' % (path, '（写入守卫改名保留）' if renamed else ''))
    text = ('=' * 88 + '\n[ci_gates] run_id=%s phase=%s interpreter=%s steps=%d\n'
            % (RUN_ID, args.phase, exe, len(results))
            + json.dumps(out, ensure_ascii=False, indent=1) + '\n')
    saved = save_evidence('ci_gates_%s.console.txt' % args.phase, text, subdir=run_name)
    print('[ci_gates] 原始输出已落盘（写入守卫 + 台账）-> %s' % saved)
    return code


if __name__ == '__main__':
    sys.exit(main())
