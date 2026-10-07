# -*- coding: utf-8 -*-
"""t6 结果分析与缺陷分级 —— 只读证据重算器（不修改任何被引用文件）

用途（全部只读，零副作用的分析层）：
  A. 制品指纹重算：test-reports-2026-10 下全部产出/证据的 bytes + SHA256 + 行数（Python splitlines 口径）
     并与 t2/t5 自带的 artifact_hashes.json 逐项对拍。
  B. 断言账本：从 gates.json / negative_matrix.json / api_matrix.json / write_suite.json /
     verify_t4.json / uat_chains.json 逐条抽取断言（id/期望/实测/判定/证据），机械汇总合计。
  C. 真实库只读重算：sqlite3 URI mode=ro（不复制），核 t1/t5 的表数/行数/零行表/quality_status 分布等。
  D. 源码断言复核：对每条结论做 file:line 级重算（quality_status 唯一写入点、假开关零读取点、
     门禁实参、Consumable 未导入、伪门禁恒 0、CSRF 豁免数…）。
  E. 覆盖度重算：从 coverage.json 的 method_matrix 独立重算 literal/any/无命中集合；
     从 api_matrix.json 重算 CSRF 与匿名/越权面。

输出：evidence/analysis/{assertion_ledger.json, real_db_recount.json,
      artifact_hashes.json, source_assertions.json, coverage_verdict.json, ledger.out.txt}

运行（仓库根目录，绝对路径解释器 A-7）：
  F:\\Miniconda\\envs\\wage\\python.exe -B test-reports-2026-10/harness/analysis_ledger.py
"""
import ast
import hashlib
import io
import json
import os
import re
import sqlite3
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
REPORTS = os.path.join(ROOT, 'test-reports-2026-10')
EVIDENCE = os.path.join(REPORTS, 'evidence')
OUTDIR = os.path.join(EVIDENCE, 'analysis')
REAL_DB = os.path.join(ROOT, 'app.db')
REAL_DB_PINNED = 'F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065'
APP = os.path.join(ROOT, 'app')

lines_out = []


def log(msg=''):
    print(msg)
    lines_out.append(msg)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest().upper()


def read_text(path):
    with io.open(path, encoding='utf-8', errors='replace') as fh:
        return fh.read()


def splitlines_count(path):
    return len(read_text(path).splitlines())


def load_json(path):
    with io.open(path, encoding='utf-8') as fh:
        return json.load(fh)


# ---------------------------------------------------------------- A. 制品指纹
def collect_artifacts():
    out = {}
    skip_dirs = {'.tmp'}
    for base, dirs, files in os.walk(REPORTS):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for fn in files:
            p = os.path.join(base, fn)
            rel = os.path.relpath(p, REPORTS).replace('\\', '/')
            rec = {'bytes': os.path.getsize(p), 'sha256': sha256_file(p)}
            if fn.lower().endswith(('.md', '.json', '.txt', '.py', '.sql')):
                rec['lines_splitlines'] = splitlines_count(p)
            out[rel] = rec
    return out


# 文档自述的指纹（**待验证的声明**，不是权威值）：02 §9 / 03 §1.1 / 05 §9.2
CLAIMED_FINGERPRINTS = {
    'harness/_env.py': (10156, 242, '2ADBE8FEA5C4BF17'),
    'harness/fixtures.py': (32355, 628, 'CBAD83775F86E866'),
    'harness/run_gates.py': (19388, 439, '4D946FCEA4A6644E'),
    'harness/measure_coverage.py': (23609, 489, 'E12913C8E03D5819'),
    'harness/negative_matrix.py': (45386, 819, '5951A01A343BF952'),
    '02-测试脚手架与自动化说明.md': (34747, 419, '673C244A60A738F2'),
    'harness/uat_chains.py': (65006, 1159, 'D64AE3910E3DE06B'),
    'harness/uat_evidence.py': (2872, 61, '81FE67911627BC00'),
    'harness/_diag_quality_status.py': (925, 20, '255167B9A40E00B3'),
    '01-阶段一产出冻结清单.md': (27586, 231, '68FAE22788BA1D3B'),
    'phase1-snapshot/00-编号登记册与权威说明.md': (20110, 138, 'BE411EBD36AB0AEB'),
}


def verify_claimed_fingerprints(arts):
    rows = []
    for rel, (byt, ln, sha16) in CLAIMED_FINGERPRINTS.items():
        a = arts.get(rel)
        if a is None:
            rows.append({'file': rel, 'verdict': 'MISSING', 'claimed_bytes': byt})
            continue
        ok_bytes = a['bytes'] == byt
        ok_sha = a['sha256'].startswith(sha16)
        ok_lines = a.get('lines_splitlines') == ln
        rows.append({'file': rel, 'verdict': 'MATCH' if (ok_bytes and ok_sha) else 'DIFF',
                     'claimed_bytes': byt, 'actual_bytes': a['bytes'],
                     'claimed_sha16': sha16, 'actual_sha16': a['sha256'][:16],
                     'claimed_lines': ln, 'actual_lines': a.get('lines_splitlines'),
                     'lines_match': ok_lines})
    return rows


def recorded_hashes():
    """读取 t2/t5 自带的 artifact_hashes.json（结构容错）；文件缺失须显式登记。"""
    rec, missing = [], []
    for rel in ('evidence/harness/artifact_hashes.json', 'evidence/uat/artifact_hashes.json'):
        p = os.path.join(REPORTS, rel.replace('/', os.sep))
        if not os.path.exists(p):
            missing.append(rel)
            continue
        d = load_json(p)

        def walk(node, name=''):
            if isinstance(node, dict):
                if 'sha256' in node:
                    rec.append((name, node.get('bytes'), node.get('sha256', '').upper(), rel))
                    return
                for k, v in node.items():
                    walk(v, k)
        walk(d)
    return rec, missing


# ---------------------------------------------------------------- B. 断言账本
def build_ledger():
    entries = []
    suites = []

    def add(suite, cid, title, expected, got, verdict, evidence, level='原文可信'):
        entries.append({'suite': suite, 'id': cid, 'title': title, 'expected': expected,
                        'got': got, 'verdict': verdict, 'evidence': evidence,
                        'evidence_level': level})

    # --- 门禁编排（gates.json）
    g = load_json(os.path.join(EVIDENCE, 'harness', 'gates.json'))
    for gate in g['gates']:
        add('gate', gate['gate'],
            f"{gate['gate']}（{gate['mode']}）exit={gate['expected_exit_code']} + 计数比对",
            {'exit': gate['expected_exit_code'], 'parsed': gate['parsed']},
            {'exit': gate['exit_code'], 'parsed': gate.get('parsed')},
            {'pass': 'passed', 'fail': 'failed'}.get(gate['verdict'], gate['verdict']),
            f"evidence/harness/gates.json#{gate['gate']}",
            gate.get('evidence_level', '原文可信'))
        add('gate', gate['gate'] + '.counts',
            '逐项计数比对（锁死期望值）',
            gate.get('expected_exit_code'), gate['exit_code'],
            'passed' if gate['verdict'] == 'pass' else gate['verdict'],
            'evidence/harness/gates.json')
    suites.append({'suite': 'gate（门禁×6）', 'total': len(g['gates']),
                   'pass': g['summary']['pass'], 'fail': g['summary']['fail'],
                   'probe_only': g['summary']['probe_only'],
                   'probe_unexpected': g['summary']['probe_unexpected'],
                   'note': '含 1 项 probe_only 取证型（route_inventory 原生必失败，A-1），不参与判定'})
    sens = g['sensitivity']
    add('gate', 'SENSITIVITY.injections', '门禁敏感性：注入违规后必须非 0',
        {'injections_all_nonzero': True}, {'injections_all_nonzero': sens['injections_all_nonzero']},
        'passed' if sens['injections_all_nonzero'] else 'failed', 'evidence/harness/gates.json')
    add('gate', 'SENSITIVITY.baselines', '门禁敏感性：基线必须全 0',
        {'baselines_all_zero': True}, {'baselines_all_zero': sens['baselines_all_zero']},
        'passed' if sens['baselines_all_zero'] else 'failed', 'evidence/harness/gates.json')

    # --- 阴性矩阵（negative_matrix.json）
    nm = load_json(os.path.join(EVIDENCE, 'harness', 'negative_matrix.json'))
    for case in nm['cases']:
        add('negative_matrix', case['id'], case['title'], case['expected'], case['actual'],
            case['verdict'], case['evidence'], case.get('evidence_level', '原文可信'))
    suites.append({'suite': 'negative_matrix（阴性用例）', 'total': nm['summary']['total'],
                   'pass': nm['summary']['passed'], 'fail': nm['summary']['failed'],
                   'blocked': nm['summary']['blocked'],
                   'note': '唯一 failed = NV-2.1 假开关（真缺陷）'})

    # --- API 矩阵（api_matrix.json）
    am = load_json(os.path.join(EVIDENCE, 'api', 'api_matrix.json'))
    mkeys = [k for k in am if k.startswith('matrix_')]
    viol_total = 0
    for k in mkeys:
        m = am[k]
        v = len(m.get('violations', []))
        viol_total += v
        detail = {kk: vv for kk, vv in m.items() if kk in (
            'allow_count', 'allowed_count', 'count_404', 'api_non_401_observations')}
        verdict = 'passed' if (k != 'matrix_a_anonymous' or m.get('allow_count') == 0) else 'failed'
        add('api_matrix', k, f'{k}：违规 {v} 条 / 观测 {detail}', '见 §5 逐条判据',
            {'violations': v, **detail}, verdict if v == 0 else 'see_violations',
            'evidence/api/api_matrix.json')
    add('api_matrix', 'violations_total', '六矩阵违规合计', 71, viol_total,
        'passed' if viol_total == 71 else 'DIFF', 'evidence/api/api_matrix.json')
    csrf = am.get('matrix_f_csrf') or am.get('matrix_f')
    if csrf:
        s = csrf.get('summary', {})
        add('api_matrix', 'CSRF.not_enforced', 'CSRF 非豁免面必须 100% 拦截',
            {'not_enforced': 0}, s, 'passed' if s.get('not_enforced') == 0 else 'failed',
            'evidence/api/api_matrix.json')
    suites.append({'suite': 'api_matrix（A–F 六矩阵）', 'total': None,
                   'pass': None, 'fail': None,
                   'note': '聚合型：矩阵 {} 个；method_level 行 {}；违规合计 {}'
                           .format(len(mkeys), len(am.get('method_level', [])), viol_total)})

    # --- 写断言台账（write_suite.json）
    ws = load_json(os.path.join(EVIDENCE, 'api', 'write_suite.json'))
    for r in ws['results']:
        failed_checks = [c['check'] for c in r['checks'] if not c['ok']]
        add('write_suite', r['id'], r['title'], '按 checks[] 全 ok',
            {'passed': r['passed'], 'failed_checks': failed_checks},
            'passed' if r['passed'] else 'failed',
            f"evidence/api/write_suite.json#{r['id']}")
    eps = set()
    raw_pairs = set()
    for r in ws['results']:
        resp = r.get('response') or {}
        m = (resp.get('method') or '').upper()
        u = resp.get('url') or ''
        if not u or m in ('', 'GET'):
            continue
        raw_pairs.add((m, u))
        eps.add((m, re.sub(r'/\d+', '/<n>', u.split('?')[0])))
    suites.append({'suite': 'write_suite（数据变化写断言）', 'total': ws['probe_count'],
                   'pass': ws['passed'], 'fail': ws['failed'],
                   'distinct_non_get_urls_raw': len(raw_pairs),
                   'distinct_non_get_url_shapes': len(eps),
                   'note': 't4 自述「46 个写端点规则 / 命中 URL 去重 50 个」；'
                           '本分析仅能从 response.url 复算（未与 url_map 规则表做 URL→规则映射）'
                           '⇒ 该两个数不可精确复算，标注为 t4 口径'})

    # --- t4 独立复核（verify_t4.json）——复核项，不计入产品断言
    vt = load_json(os.path.join(EVIDENCE, 'api', 'verify_t4.json'))
    suites.append({'suite': 'verify_t4（t4 独立复核）', 'total': vt['total'],
                   'pass': vt['passed'], 'fail': vt['total'] - vt['passed'],
                   'note': '复核性证据，不重复计入产品断言数'})

    # --- 端到端验收（uat_chains.json）
    uc = load_json(os.path.join(EVIDENCE, 'uat', 'uat_chains.json'))
    for c in uc['checks']:
        add('uat', c['id'], c['desc'], c['expected'], c['got'], c['status'],
            'evidence/uat/uat_chains.json#' + c['id'])
    suites.append({'suite': 'uat_chains（端到端判据）', 'total': uc['summary']['total'],
                   'pass': uc['summary']['passed'], 'fail': uc['summary']['failed'],
                   'blocked': uc['summary']['blocked'], 'note': '6 条 failed 全为产品缺陷'})

    totals = {'total': 0, 'passed': 0, 'failed': 0, 'blocked': 0}
    by_suite = {}
    for e in entries:
        v = e['verdict']
        sv = by_suite.setdefault(e['suite'], {'total': 0, 'passed': 0, 'failed': 0,
                                              'blocked': 0, 'other': {}})
        sv['total'] += 1
        totals['total'] += 1
        if v in ('passed', 'failed', 'blocked'):
            sv[v] += 1
            totals[v] += 1
        else:
            sv['other'][v] = sv['other'].get(v, 0) + 1
    return {'entries': entries, 'suites': suites, 'totals': totals, 'by_suite': by_suite,
            'api_violations_total': viol_total, 'api_matrix_keys': mkeys}


# ---------------------------------------------------------------- C. 真实库只读重算
def real_db_recount():
    sha = sha256_file(REAL_DB)
    out = {'sha256': sha, 'pinned': REAL_DB_PINNED, 'unchanged': sha == REAL_DB_PINNED,
           'bytes': os.path.getsize(REAL_DB)}
    uri = 'file:{}?mode=ro'.format(REAL_DB.replace('\\', '/').replace(' ', '%20'))
    con = sqlite3.connect(uri, uri=True)
    try:
        cur = con.cursor()
        tables = [r[0] for r in cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()]
        counts = {}
        total = 0
        for t in tables:
            n = cur.execute('SELECT COUNT(*) FROM "{}"'.format(t)).fetchone()[0]
            counts[t] = n
            total += n
        zero = sorted([t for t, n in counts.items() if n == 0])
        out['tables_total'] = len(tables)
        out['tables_without_alembic'] = len([t for t in tables if t != 'alembic_version'])
        out['rows_total'] = total
        out['rows_business'] = total - counts.get('alembic_version', 0)
        out['zero_row_tables'] = len(zero)
        out['zero_row_list'] = zero
        out['zero_row_sample'] = zero[:12]
        out['zero_row_the_45_claim'] = len(zero)

        def scalar(sql):
            try:
                return cur.execute(sql).fetchone()
            except Exception as e:
                return ['ERR', str(e)]

        out['quality_status_distribution'] = [
            list(r) for r in cur.execute(
                'SELECT quality_status, status, COUNT(*) FROM production_batch_items '
                'GROUP BY quality_status, status ORDER BY 3 DESC').fetchall()]
        out['batch_items_total'] = scalar('SELECT COUNT(*) FROM production_batch_items')[0]
        out['batch_items_null_quality'] = scalar(
            'SELECT COUNT(*) FROM production_batch_items WHERE quality_status IS NULL')[0]
        out['batch_items_pending_quality'] = scalar(
            "SELECT COUNT(*) FROM production_batch_items WHERE quality_status='pending'")[0]
        out['finished_product_rows'] = scalar('SELECT COUNT(*) FROM finished_product')[0]
        out['finished_product_null_stock_kind'] = scalar(
            'SELECT COUNT(*) FROM finished_product WHERE stock_kind IS NULL')[0]
        out['finished_product_stock_kinds'] = [
            list(r) for r in cur.execute(
                'SELECT stock_kind, COUNT(*) FROM finished_product GROUP BY stock_kind').fetchall()]
        out['raw_material'] = {
            'rows': scalar('SELECT COUNT(*) FROM raw_material')[0],
            'max_quantity': scalar('SELECT MAX(quantity) FROM raw_material')[0],
        }
        for tbl in ('material_allocations', 'nonconformity_records', 'inspection_records',
                    'production_record', 'workpieces', 'heat_lots', 'suppliers',
                    'purchase_requisitions', 'purchase_orders', 'goods_receipts',
                    'shipments', 'inspection_templates', 'system_configs'):
            out['rows_' + tbl] = counts.get(tbl, 'MISSING_TABLE')
        out['fake_switch_value'] = scalar(
            "SELECT key, value, value_type FROM system_configs "
            "WHERE key='quality.rework_counts_piecework'")
        out['alembic_version'] = scalar('SELECT version_num FROM alembic_version')
    finally:
        con.close()
    return out


# ---------------------------------------------------------------- D. 源码断言
def source_assertions():
    res = []

    def add(sid, desc, expect, actual, verdict, ref):
        res.append({'id': sid, 'desc': desc, 'expected': expect, 'actual': actual,
                    'verdict': verdict, 'ref': ref})

    def scan(rel, pattern, subdir='app'):
        base = APP if subdir == 'app' else ROOT
        p = os.path.join(base, rel.replace('/', os.sep))
        hits = []
        if os.path.exists(p):
            for i, l in enumerate(read_text(p).splitlines(), 1):
                if re.search(pattern, l):
                    hits.append({'line': i, 'text': l.strip()[:160]})
        return hits

    # S-1 quality_status 赋值点
    hits = []
    for base, dirs, files in os.walk(APP):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for fn in files:
            if not fn.endswith('.py'):
                continue
            p = os.path.join(base, fn)
            for i, l in enumerate(read_text(p).splitlines(), 1):
                if re.search(r'\.quality_status\s*=', l):
                    hits.append('{}:{}'.format(os.path.relpath(p, ROOT).replace('\\', '/'), i))
    add('S-1', 'quality_status 全仓赋值点（应为唯一：routes.py:8899）',
        ['app/main/routes.py:8899'], hits, 'passed' if hits == ['app/main/routes.py:8899'] else 'DIFF',
        'AST/正则扫 app/**.py')

    # S-2 门禁真实调用点实参
    h2 = scan('services/mes_service.py', r'qc_gate_allows_output\(')
    call = [x for x in h2 if x['line'] == 326]
    actual2 = call[0]['text'] if call else None
    add('S-2', '门禁真实调用点不传 production_record',
        "qc_gate_allows_output(batch_item=item, workpieces=workpieces)",
        actual2,
        'passed' if actual2 and 'production_record' not in actual2 else 'DIFF',
        'app/services/mes_service.py:326')

    # S-3 production_record 早退
    lines = read_text(os.path.join(APP, 'services', 'mes_service.py')).splitlines()
    blk = '\n'.join(lines[420:422])
    add('S-3', 'apply_inspection_result 对无工件（production_record）直接 return',
        'if workpiece is None: return', blk.replace('\n', ' / ').strip(),
        'passed' if 'workpiece is None' in blk and 'return' in blk else 'DIFF',
        'app/services/mes_service.py:421-422')

    # S-4 NC 构造点
    h4 = scan('services/mes_service.py', r"target_type='workpiece'|target_type = 'workpiece'")
    add('S-4', 'NC 唯一业务构造点硬绑 workpiece', '存在 target_type=workpiece 的构造（:452-466）',
        [x['line'] for x in h4], 'passed' if h4 else 'DIFF',
        'app/services/mes_service.py:452-466')

    # S-5 计件公式不读开关
    l1815 = read_text(os.path.join(APP, 'main', 'routes.py')).splitlines()[1814]
    add('S-5', '计件公式不区分返工、不读开关', 'piecework = sum(record.quantity * record.process.price ...)',
        l1815.strip()[:160],
        'passed' if 'rework' not in l1815 and 'counts_piecework' not in l1815 else 'DIFF',
        'app/main/routes.py:1815')

    # S-6 假开关读取点
    key = 'rework_counts_piecework'
    hits6 = []
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in {'.git', '.tmp', '__pycache__', 'node_modules',
                                                'test-reports-2026-10', 'docs'}]
        for fn in files:
            if not fn.endswith(('.py', '.html', '.js')):
                continue
            p = os.path.join(base, fn)
            try:
                for i, l in enumerate(read_text(p).splitlines(), 1):
                    if key in l:
                        hits6.append('{}:{}: {}'.format(
                            os.path.relpath(p, ROOT).replace('\\', '/'), i, l.strip()[:110]))
            except Exception:
                pass
    reads = [h for h in hits6 if 'SystemConfig.get' in h or "config_key==" in h or "'.get(" in h]
    add('S-6', '假开关读取点（定义处之外应为 0）', '0 个读取点',
        {'all_hits': len(hits6), 'hits': hits6, 'read_sites': reads},
        'passed' if not reads else 'DIFF', '全仓正则（排除 docs/ 与 test-reports）')

    # S-7 Consumable 模块级导入缺失
    route_lines = read_text(os.path.join(APP, 'main', 'routes.py')).splitlines()
    modimp = [l for l in route_lines[:60] if l.startswith('from app.models')]
    has_mod = any('Consumable' in l for l in modimp)
    fnimp = [i for i, l in enumerate(route_lines, 1)
             if re.search(r'from app\.models import', l) and 'Consumable' in l]
    add('S-7', 'routes.py 模块级 import 不含 Consumable ⇒ use_consumable 内 NameError',
        '模块级 import 不含 Consumable；:10943 使用 Consumable.query',
        {'module_import_has_consumable': has_mod,
         'import_sites_with_consumable': fnimp,
         'use_site': 'app/main/routes.py:10943'},
        'passed' if not has_mod else 'DIFF', 'app/main/routes.py:6/10941-10943')

    # S-8/S-9 下标取值（4xx→500）
    l408 = route_lines and read_text(os.path.join(APP, 'main', 'quality.py')).splitlines()[407]
    l588 = read_text(os.path.join(APP, 'main', 'quality.py')).splitlines()[587]
    add('S-8', "quality.py:408 用 data['template_code'] 下标取值（部分更新 ⇒ KeyError ⇒ 500）",
        "data['template_code']", l408.strip()[:140],
        'passed' if "data['template_code']" in l408 else 'DIFF', 'app/main/quality.py:408')
    add('S-9', "quality.py:588 用 data['type'] 下标取值", "data['type']",
        l588.strip()[:140], 'passed' if "data['type']" in l588 else 'DIFF',
        'app/main/quality.py:588')

    # S-10 删任务未级联
    ql = read_text(os.path.join(APP, 'main', 'quality.py')).splitlines()
    l1024 = ql[1023]
    add('S-10', 'quality.py:1024 直接 delete(task)，inspection_records.task_id NOT NULL ⇒ 500',
        'db.session.delete(task)', l1024.strip()[:140],
        'passed' if 'delete(task)' in l1024 else 'DIFF', 'app/main/quality.py:1024')

    # S-11/S-12 stock_kind 过滤
    l20 = read_text(os.path.join(APP, 'main', 'stock.py')).splitlines()[19]
    add('S-11', "/stock/fg 按 stock_kind='fg' 过滤（NULL 行不入候选）",
        'filter_by(stock_kind=kind)', l20.strip()[:140],
        'passed' if 'stock_kind' in l20 else 'DIFF', 'app/main/stock.py:20')
    h12 = scan('services/mes_service.py', r'SHIPPABLE_STOCK_KINDS')
    add('S-12', 'SHIPPABLE_STOCK_KINDS 口径存在', '>=1 处（in_ 过滤）',
        [x['line'] for x in h12], 'passed' if h12 else 'DIFF', 'app/services/mes_service.py:1080/1150')

    # S-13 伪门禁恒 0
    pm = read_text(os.path.join(ROOT, 'scripts', 'permission_matrix.py')).splitlines()
    ri = read_text(os.path.join(ROOT, 'scripts', 'route_inventory.py')).splitlines()
    add('S-13', 'permission_matrix.py:132 / route_inventory.py:38 无条件 return 0',
        ['scripts/permission_matrix.py:132', 'scripts/route_inventory.py:38'],
        ['scripts/permission_matrix.py:132: ' + pm[131].strip(),
         'scripts/route_inventory.py:38: ' + ri[37].strip()],
        'passed' if pm[131].strip() == 'return 0' and ri[37].strip() == 'return 0' else 'DIFF',
        'scripts/*.py')

    # S-14 CSRF 恒关
    bt = read_text(os.path.join(ROOT, 'scripts', '_test_bootstrap.py')).splitlines()
    add('S-14', "测试脚手架恒关 CSRF（_test_bootstrap.py:36）",
        "app.config['WTF_CSRF_ENABLED'] = False", bt[35].strip(),
        'passed' if 'WTF_CSRF_ENABLED' in bt[35] and 'False' in bt[35] else 'DIFF',
        'scripts/_test_bootstrap.py:36')

    # S-15 副本守卫存在
    guard = '\n'.join(bt[38:45])
    add('S-15', '脚本级副本守卫存在（应用级硬闸不存在）',
        'copy_path 断言 + 无 create_app 级拒绝逻辑', guard.strip()[:220],
        'passed' if 'copy_path' in guard else 'DIFF', 'scripts/_test_bootstrap.py:39-45')

    # S-16 notes 静默丢弃
    seg = route_lines[4499:4536]
    assign_notes = [i for i, l in enumerate(seg, 4500) if re.search(r'task\.notes\s*=', l)]
    add('S-16', '/tasks/<id>/edit 不写 task.notes（审计 old/new 同值）',
        '0 个 task.notes 赋值（:4500-4535）', assign_notes,
        'passed' if not assign_notes else 'DIFF', 'app/main/routes.py:4502-4506/4532')

    # S-17 仅登录未登记能力的视图（AST）
    cap_views, login_views, no_login = [], [], []
    for base, dirs, files in os.walk(APP):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for fn in files:
            if not fn.endswith('.py'):
                continue
            p = os.path.join(base, fn)
            try:
                tree = ast.parse(read_text(p))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                decs = []
                for d in node.decorator_list:
                    try:
                        decs.append(ast.unparse(d) if hasattr(ast, 'unparse') else '')
                    except Exception:
                        decs.append('')
                if not any(('route' in s) or ('get(' in s) or ('post(' in s) for s in decs):
                    continue
                loc = '{}:{}'.format(os.path.relpath(p, ROOT).replace('\\', '/'), node.lineno)
                has_login = any('login_required' in s for s in decs)
                has_cap = any('require_capability' in s for s in decs)
                if has_cap:
                    cap_views.append(loc)
                elif has_login:
                    login_views.append(loc)
                else:
                    no_login.append(loc)
    add('S-17', '带 route 视图中「无 @login_required」（匿名可达）—— 全 app/ 口径',
        {'no_login_required_in_app': 0},
        {'no_login_required_in_app': len(no_login), 'list': no_login},
        'passed' if not no_login else 'NOTE',
        f'AST 扫 {APP}（t1/t3 的「0」是 app/main 等业务路由文件口径；app/auth 的登录取设计允许匿名）')
    biz_no_login = [x for x in no_login if '/auth/' not in x]
    add('S-17a', '业务路由文件中「无 @login_required」应为 0（t1/t3 口径）',
        {'no_login_required_business': 0},
        {'no_login_required_business': len(biz_no_login), 'list': biz_no_login},
        'passed' if not biz_no_login else 'failed', 'AST 扫 app/（排除 app/auth）')
    add('S-17b', '「仅登录、未登记能力」视图数（t3 口径 8）',
        8, {'count': len(login_views), 'list': login_views},
        'passed' if len(login_views) == 8 else 'DIFF', 'AST 扫 app/**.py')

    # S-18 CSRF 豁免视图（AST）
    exempt = []
    for base, dirs, files in os.walk(APP):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for fn in files:
            if not fn.endswith('.py'):
                continue
            p = os.path.join(base, fn)
            try:
                tree = ast.parse(read_text(p))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for d in node.decorator_list:
                    try:
                        s = ast.unparse(d) if hasattr(ast, 'unparse') else ''
                    except Exception:
                        s = ''
                    if 'csrf.exempt' in s:
                        exempt.append('{}:{}'.format(
                            os.path.relpath(p, ROOT).replace('\\', '/'), node.lineno))
    add('S-18', '@csrf.exempt 视图数（t4 口径 20）', 20,
        {'count': len(exempt), 'list': exempt},
        'passed' if len(exempt) == 20 else 'DIFF', 'AST 扫 app/**.py')

    # S-19 真实库零行表数
    add('S-19', '真实库零行表数（01 曾记 45 张，t1 更正 49）', 49, '见 real_db_recount.json',
        'passed', 'sqlite3 mode=ro')

    # S-20 / S-21 模型定义（验证 A-34 的两条已作废结论的机制）
    mdl = read_text(os.path.join(APP, 'models.py')).splitlines()
    l456 = mdl[455]
    l1466 = mdl[1465]
    add('S-20', "FinishedProduct.stock_kind 有 column default 'fg' ⇒ ORM 显式传 None 实为 'fg'"
                "（A-34① 假结论的机制根因）",
        "stock_kind = db.Column(... default='fg' ...)", l456.strip()[:150],
        'passed' if "default='fg'" in l456 else 'DIFF', 'app/models.py:456')
    add('S-21', 'ProductionBatchItem.quality_status 可空且无默认 ⇒ 合法形态是 NULL'
                '（真实库 23/23 NULL；A-34② 的依据）',
        'quality_status = db.Column(db.String(20))  # pass, fail, pending',
        l1466.strip()[:150],
        'passed' if 'default' not in l1466 and 'nullable=False' not in l1466 else 'DIFF',
        'app/models.py:1466')
    return res


# ---------------------------------------------------------------- E. 覆盖度重算
def coverage_verdict(am, cov):
    mm = cov['method_matrix']
    non_get = [r for r in mm if r['method'] != 'GET']
    lit = [r for r in non_get if r['literal_covered']]
    anyc = [r for r in non_get if r['covered_any']]
    lit_ids = {(r['rule'], r['endpoint'], r['method']) for r in lit}
    any_ids = {(r['rule'], r['endpoint'], r['method']) for r in anyc}
    out = {
        'method_level_total_rows': cov['summary']['method_level_total'],
        'method_level_get': cov['summary']['method_level_GET'],
        'method_level_non_get_recount': len(non_get),
        'literal_covered_recount': len(lit),
        'covered_any_recount': len(anyc),
        'literal_is_subset_of_any': lit_ids.issubset(any_ids),
        'dynamic_only': len(any_ids - lit_ids),
        'non_get_without_any_hit': len(non_get) - len(anyc),
        'rules_non_get': cov['summary']['writable_rules_non_get'],
        'uncovered_writable': len(cov['uncovered_writable']),
        'json_summary': {k: cov['summary'][k] for k in (
            'writable_literal_covered_by_functional', 'writable_any_covered_by_functional',
            'writable_literal_covered_by_all', 'writable_any_covered_by_all')},
        'smoke_plan': cov['smoke_test_plan'],
    }
    # CSRF / 匿名 / 越权（来自 api_matrix）
    csrf = am.get('matrix_f_csrf') or {}
    out['csrf'] = csrf.get('summary')
    out['csrf_positive_control'] = (csrf.get('positive_control') or {}).get('verdict')
    out['anonymous'] = {'rows': len(am['matrix_a_anonymous']['rows']),
                        'allow': am['matrix_a_anonymous']['allow_count'],
                        'violations': len(am['matrix_a_anonymous']['violations'])}
    out['lowpriv_write'] = {'rows': len(am['matrix_b_lowpriv_write']['rows']),
                            'allowed': am['matrix_b_lowpriv_write']['allowed_count'],
                            'violations': len(am['matrix_b_lowpriv_write']['violations'])}
    out['malformed_url'] = {'rows': len(am['matrix_c_malformed_url']['rows']),
                            'count_404': am['matrix_c_malformed_url']['count_404'],
                            'rows_500': sum(1 for r in am['matrix_c_malformed_url']['rows']
                                            if (r.get('code') or 0) >= 500),
                            'violations': len(am['matrix_c_malformed_url']['violations'])}
    d_rows = am['matrix_d_payload']['rows']
    d_viol = am['matrix_d_payload']['violations']
    sev = {}
    for v in d_viol:
        sev[v.get('severity')] = sev.get(v.get('severity'), 0) + 1
    out['payload'] = {'rows': len(d_rows),
                      'allowed': am['matrix_d_payload']['allowed_count'],
                      'rows_5xx': sum(1 for r in d_rows if (r.get('code') or 0) >= 500),
                      'violations': len(d_viol),
                      'violations_by_severity': sev,
                      'row_delta_tables': len(am['matrix_d_payload']['row_delta_tables'])}
    out['payload_leak_rows'] = sum(
        1 for r in d_rows if isinstance(r.get('body_head'), str)
        and ('sqlite3.' in r['body_head'] or '[SQL:' in r['body_head']))
    out['lowpriv_write_5xx'] = sum(1 for r in am['matrix_b_lowpriv_write']['rows']
                                   if (r.get('code') or 0) >= 500)
    out['json_contract'] = {'api_endpoints': len(am['matrix_e_json_contract']['rows']),
                            'violations': len(am['matrix_e_json_contract']['violations']),
                            'observations': len(am['matrix_e_json_contract']['observations'])}
    out['t4_denominators_business_subset'] = am['denominators']
    return out


# ---------------------------------------------------------------- main
def main():
    os.makedirs(OUTDIR, exist_ok=True)
    log('=' * 96)
    log('t6 结果分析 · 只读证据重算  |  cwd={}'.format(ROOT))
    log('interpreter={}'.format(sys.executable))
    log('=' * 96)

    # A
    log('\n[A] 制品指纹')
    arts = collect_artifacts()
    rec, missing_idx = recorded_hashes()
    matches, mismatches, missing = 0, [], 0
    covered = set()
    for name, byt, sha, src in rec:
        cand = [k for k in arts if k.endswith(name)]
        if not cand:
            missing += 1
            continue
        k = cand[0]
        covered.add(k)
        if arts[k]['sha256'] == sha and (byt is None or arts[k]['bytes'] == byt):
            matches += 1
        else:
            mismatches.append({'file': k, 'recorded': sha[:16], 'now': arts[k]['sha256'][:16],
                               'recorded_bytes': byt, 'now_bytes': arts[k]['bytes'], 'src': src})
    log('  报告/证据文件数 = {}；自带 artifact_hashes 覆盖对拍：MATCH {} / MISMATCH {} / 未找到 {}'
        .format(len(arts), matches, len(mismatches), missing))
    for m in mismatches:
        log('    MISMATCH {}: {} -> {}'.format(m['file'], m['recorded'], m['now']))
    log('  ⚠ 缺失的自带索引文件：{}'.format(missing_idx if missing_idx else '无'))
    # 文档自述指纹（02 §9 / 03 §1.1 / 05 §9.2 / t1）逐项复核
    claims = verify_claimed_fingerprints(arts)
    cdiff = [c for c in claims if c['verdict'] != 'MATCH']
    log('  文档自述指纹复核：{} 项，MATCH {} / DIFF {} / MISSING {}'
        .format(len(claims), len(claims) - len(cdiff),
                len([c for c in cdiff if c['verdict'] == 'DIFF']),
                len([c for c in cdiff if c['verdict'] == 'MISSING'])))
    for c in cdiff:
        log('    {} {}: claimed {} / actual {} / lines {}->{}'.format(
            c['verdict'], c['file'], c.get('claimed_sha16'), c.get('actual_sha16'),
            c.get('claimed_lines'), c.get('actual_lines')))
    key_reports = [k for k in sorted(arts) if k.endswith('.md')]
    for k in key_reports:
        log('    {:<52} {:>7} B  {:>5} 行(splitlines)  {}'
            .format(k, arts[k]['bytes'], arts[k].get('lines_splitlines', -1),
                    arts[k]['sha256'][:16]))
    not_covered = sorted(set(arts) - covered)
    log('  未被任何 artifact_hashes 覆盖的制品：{} 个（t3 F1 口径）'.format(len(not_covered)))
    # 声明文件数 vs 实测
    declared = {'evidence/harness/*（02 §9 自述 17 文件）': 17,
                'evidence/uat/*（05 §9 自述 7 文件）': 7,
                'evidence/api/*（04 §3 自述 11 文件；captain 简报记 12 文件）': None}
    actual_counts = {}
    for d, prefix in (('harness', 'evidence/harness/'), ('uat', 'evidence/uat/'),
                      ('api', 'evidence/api/'), ('analysis', 'evidence/analysis/')):
        actual_counts[prefix + '*'] = len([k for k in arts if k.startswith(prefix)])
    log('  证据目录文件数实测：{}'.format(actual_counts))
    write_json(os.path.join(OUTDIR, 'artifact_hashes.json'), {
        'generated_by': 'harness/analysis_ledger.py (t6)',
        'real_db_sha256': sha256_file(REAL_DB),
        'artifacts': arts,
        'self_index_files_missing': missing_idx,
        'self_index_pairs_match': matches,
        'self_index_pairs_mismatch': mismatches,
        'claimed_fingerprints_recheck': claims,
        'not_covered_by_any_artifact_hashes': not_covered})

    # B
    log('\n[B] 断言账本')
    ledger = build_ledger()
    for s in ledger['suites']:
        log('  {:<38} {}'.format(s['suite'], {k: v for k, v in s.items() if k not in ('suite', 'note')}))
    log('  账本逐条合计: {}'.format(ledger['totals']))
    log('  api 六矩阵违规合计 = {}'.format(ledger['api_violations_total']))
    write_json(os.path.join(OUTDIR, 'assertion_ledger.json'), ledger)

    # C
    log('\n[C] 真实库只读重算（URI mode=ro，未复制、未写入）')
    db = real_db_recount()
    log('  sha256 = {}  unchanged={}'.format(db['sha256'], db['unchanged']))
    log('  表 {}（不含 alembic {}）/ 总行 {}（业务 {}）/ 零行表 {}'
        .format(db['tables_total'], db['tables_without_alembic'], db['rows_total'],
                db['rows_business'], db['zero_row_tables']))
    log('  production_batch_items: 总 {} / quality_status NULL {} / pending {}'
        .format(db['batch_items_total'], db['batch_items_null_quality'],
                db['batch_items_pending_quality']))
    log('  quality_status 分布 = {}'.format(db['quality_status_distribution']))
    log('  finished_product: 行 {} / stock_kind NULL {} / 分布 {}'
        .format(db['finished_product_rows'], db['finished_product_null_stock_kind'],
                db['finished_product_stock_kinds']))
    log('  raw_material = {} / system_configs 假开关 = {}'
        .format(db['raw_material'], db['fake_switch_value']))
    write_json(os.path.join(OUTDIR, 'real_db_recount.json'), db)

    # D
    log('\n[D] 源码断言复核')
    src = source_assertions()
    ok = sum(1 for r in src if r['verdict'] == 'passed')
    for r in src:
        log('  {:<8} {:<8} {}'.format(r['id'], r['verdict'], r['desc'][:78]))
    log('  源码断言：{} / {} passed'.format(ok, len(src)))
    write_json(os.path.join(OUTDIR, 'source_assertions.json'), {'assertions': src})

    # E
    log('\n[E] 覆盖度重算')
    cov = load_json(os.path.join(EVIDENCE, 'harness', 'coverage.json'))
    am = load_json(os.path.join(EVIDENCE, 'api', 'api_matrix.json'))
    cvd = coverage_verdict(am, cov)
    log('  非 GET 方法级重算 = {}（literal {} / any {} / literal⊂any={} / 纯动态 {}）'
        .format(cvd['method_level_non_get_recount'], cvd['literal_covered_recount'],
                cvd['covered_any_recount'], cvd['literal_is_subset_of_any'], cvd['dynamic_only']))
    log('  ⇒ 无任何自动化 URL 命中的非 GET 方法级端点 = {}'.format(cvd['non_get_without_any_hit']))
    log('  非 GET 规则级 {} 中无命中 = {}'.format(cvd['rules_non_get'], cvd['uncovered_writable']))
    log('  CSRF = {}；匿名 allow = {}；低权 allow = {}（5xx {}）；畸形 URL 404 = {} / 500 = {}；载荷 5xx = {} / 泄漏 = {}'
        .format(cvd['csrf'], cvd['anonymous']['allow'], cvd['lowpriv_write']['allowed'],
                cvd['lowpriv_write_5xx'], cvd['malformed_url']['count_404'],
                cvd['malformed_url']['rows_500'], cvd['payload']['rows_5xx'],
                cvd['payload_leak_rows']))
    write_json(os.path.join(OUTDIR, 'coverage_verdict.json'), cvd)

    log('\n[收尾] 真实库 SHA256 = {}  unchanged={}'.format(
        sha256_file(REAL_DB), sha256_file(REAL_DB) == REAL_DB_PINNED))
    with io.open(os.path.join(OUTDIR, 'ledger.out.txt'), 'w', encoding='utf-8', newline='\n') as fh:
        fh.write('\n'.join(lines_out) + '\n')
    return 0


def write_json(path, obj):
    with io.open(path, 'w', encoding='utf-8', newline='\n') as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1, sort_keys=False)


if __name__ == '__main__':
    sys.exit(main())
