#!/usr/bin/env python
"""批次16 前端契约**非作者**验证载体（verifier 自写，不复用实现者脚本/命令）。

口径来源：test-reports-2026-10/B16-00-契约冻结.md §5 的 G4/G5/G6/G7/G8/G10/G11。
每个检查项**各带独立退出码**（`--check <id>` 直接返回该项退出码）：

    0 = PASS           读数满足契约终态
    1 = FAIL           读数既不满足终态、也不等于修复前基线（部分实现/回归）
    2 = ERROR          该项在本环境不可判定（blocked，**不得折算 pass**）
    4 = UNIMPLEMENTED  读数**恰等于修复前基线** ⇒ 判定「未实现」

用法（仓库根执行；`--out` 类参数一律绝对路径）：
    python -B test-reports-2026-10/harness/b16_frontend_contract.py            # 全部检查
    python -B test-reports-2026-10/harness/b16_frontend_contract.py --list
    python -B test-reports-2026-10/harness/b16_frontend_contract.py --check g5-notoken
    python -B test-reports-2026-10/harness/b16_frontend_contract.py --baseline HEAD   # 静态度量对修复前树
    python -B test-reports-2026-10/harness/b16_frontend_contract.py --selftest        # 敏感度自检

`--baseline REV` 用 `git show REV:<path>` 取修复前内容复跑静态检查 ⇒ 修复前必须报
UNIMPLEMENTED/FAIL，修复后必须报 PASS（判据可判定性由这条对照保证）。
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PASS, FAIL, ERROR, UNIMPL = 0, 1, 2, 4
CODENAME = {0: 'PASS', 1: 'FAIL', 2: 'ERROR', 4: 'UNIMPLEMENTED'}

MAIN = 'app/templates/main'
# 契约 §5-G5 钉死的 inScope 文件集：11 具名 + quality/*.html(7) + advanced_search = 19
INSCOPE_NAMES = ['tasks', 'my_tasks', 'production_batch_detail', 'consumables',
                 'consumable_categories', 'delivery_batches', 'process_assignment_bulk',
                 'products', 'inventory', 'production_center', 'production_center_item']

# ---- 修复前基线（本载体在 `--baseline HEAD` 上实测复现，见报告 §2/§3）----
BASE_A = 9              # A 桶：静态全字面量根相对 URL
BASE_NOTOKEN = 19       # inScope 内非 GET 且无令牌的 fetch( 站点
BASE_APIFETCH = 0       # 修复前 apiFetch( 站点
BASE_INLINE_ROLE = 2    # 模板内联 current_user.role 命中
BASE_PRINT_ZEROARG = 1  # 零实参 printRecord()
BASE_SEARCH_KEYS = 4    # advanced_search.html 已汉化的 key 数（8 个中）


class Src:
    """源码提供者：rev=None 读工作树；rev='HEAD' 读 `git show HEAD:<path>`（修复前树）。"""

    def __init__(self, root, rev=None):
        self.root = root
        self.rev = rev

    def read(self, rel):
        if self.rev:
            p = subprocess.run(['git', 'show', '%s:%s' % (self.rev, rel)], cwd=self.root,
                               capture_output=True, text=True)
            if p.returncode != 0:
                raise FileNotFoundError('%s:%s' % (self.rev, rel))
            return p.stdout
        with open(os.path.join(self.root, rel), encoding='utf-8') as f:
            return f.read()

    def exists(self, rel):
        if self.rev:
            return subprocess.run(['git', 'cat-file', '-e', '%s:%s' % (self.rev, rel)],
                                  cwd=self.root, capture_output=True).returncode == 0
        return os.path.isfile(os.path.join(self.root, rel))

    def list_templates(self):
        if self.rev:
            p = subprocess.run(['git', 'ls-tree', '-r', '--name-only', self.rev, '--', 'app/templates'],
                               cwd=self.root, capture_output=True, text=True)
            return sorted(x for x in p.stdout.splitlines() if x.endswith('.html'))
        out = []
        for d, _, fs in os.walk(os.path.join(self.root, 'app/templates')):
            for f in fs:
                if f.endswith('.html'):
                    out.append(os.path.relpath(os.path.join(d, f), self.root).replace('\\', '/'))
        return sorted(out)


class R:
    """单项检查读数：code + 逐行原始读数 + 结构化数据。"""

    def __init__(self):
        self.code = PASS
        self.lines = []
        self.data = {}

    def say(self, msg):
        self.lines.append(msg)

    def set(self, code, msg):
        if code > self.code or self.code == PASS:
            self.code = code
        self.say(msg)


CHECKS = {}


def check(name, kind='static'):
    def deco(fn):
        CHECKS[name] = (kind, fn)
        return fn
    return deco


# ---- 口径：契约 §5-G5（A 桶 / NOTOKEN）与 B16-05 分桶，逐字面量复刻口径、代码自写 ----
CTX = re.compile(r"(fetch\(|location\.href\s*=|\.action\s*=|window\.open\(|\$\.(get|post|ajax)\()")
LIT = re.compile(r"""['"`](/[a-zA-Z][\w\-/.:$]*)""")
TOKEN = re.compile(r"X-CSRFToken|csrf_token")
METH_GET = re.compile(r"method:\s*['\"]GET")


def inscope_files(src):
    fs = {MAIN + '/%s.html' % n for n in INSCOPE_NAMES}
    fs |= {p for p in src.list_templates() if p.startswith(MAIN + '/quality/')}
    fs.add(MAIN + '/search/advanced_search.html')
    return sorted(p for p in fs if src.exists(p))


def scan(src, files):
    """返回 (A 桶命中, NOTOKEN 命中, apiFetch 命中)；窗口 = fetch( 起 12 行。"""
    a, nt, af = [], [], []
    for rel in files:
        lines = src.read(rel).splitlines()
        for i, line in enumerate(lines, 1):
            if CTX.search(line) and LIT.search(line) and 'url_for' not in line \
                    and '{{' not in line and '${' not in line:
                a.append((rel, i, line.strip()[:100]))
            if 'fetch(' in line and 'apiFetch' not in line:      # 大小写敏感 ⇒ apiFetch( 天然不计
                win = '\n'.join(lines[i - 1:i + 12])
                if 'method:' in win and not METH_GET.search(win) and not TOKEN.search(win):
                    nt.append((rel, i, line.strip()[:100]))
            if 'apiFetch(' in line:
                af.append((rel, i, line.strip()[:100]))
    return a, nt, af


@check('g5-get-sites')
def c_get_sites(src, args):
    """阴性对照②：GET 站点不得被套上 apiFetch（只有非 GET 才需要令牌）。

    列出**仍是原生 fetch(** 的 GET 站点（窗口内无 method: 或 method: 'GET'），并要求
    所有 apiFetch 站点都不是 GET ⇒ 未被「一刀切」加 header。
    """
    r = R()
    files = inscope_files(src)
    raw_get, conv_get = [], []
    for rel in files:
        lines = src.read(rel).splitlines()
        for i, line in enumerate(lines, 1):
            win = '\n'.join(lines[i - 1:i + 12])
            is_get = ('method:' not in win) or bool(METH_GET.search(win))
            if not is_get:
                continue
            if 'fetch(' in line and 'apiFetch' not in line:
                raw_get.append((rel, i, line.strip()[:100]))
            if 'apiFetch(' in line:
                conv_get.append((rel, i, line.strip()[:100]))
    r.data = {'raw_get': ['%s:%d' % (p, i) for p, i, _ in raw_get],
              'apifetch_on_get': ['%s:%d' % (p, i) for p, i, _ in conv_get]}
    r.say('仍为原生 fetch( 的 GET 站点 = %d 处（未被强加 header）' % len(raw_get))
    r.lines += ['  GET ' + x for x in fmt(raw_get)]
    r.say('apiFetch 站点中 method 为 GET/缺省 = %d 处（期望 0）' % len(conv_get))
    r.lines += ['  被套上 apiFetch 的 GET ' + x for x in fmt(conv_get)]
    r.code = PASS if raw_get and not conv_get else FAIL
    if not raw_get:
        r.say('仓内 GET 站点为 0 与常识不符 ⇒ 判据输入异常')
    return r


@check('g5-residual-ledger', kind='audit')
def c_residual_ledger(src, args):
    """口径外残留台账：**全仓模板**（不只 inScope）的非 GET 无令牌站点 + A/B/C/D 分桶。

    断言可失败：若 `sales_order_detail.html` 的挂账点消失，说明台账过期（该残留被修掉或
    口径变动）⇒ FAIL 要求重新登记，杜绝「已清零」式表述。
    """
    r = R()
    a, b, c, d, nt_all = [], [], [], [], []
    for rel in src.list_templates():
        lines = src.read(rel).splitlines()
        for i, line in enumerate(lines, 1):
            if CTX.search(line) and LIT.search(line):
                hit = (rel, i, line.strip()[:100])
                if 'url_for' not in line and '{{' not in line and '${' not in line:
                    a.append(hit)
                elif '${' in line:
                    b.append(hit)
                elif '{{' in line:
                    d.append(hit)
                else:
                    c.append(hit)
            if 'fetch(' in line and 'apiFetch' not in line:
                win = '\n'.join(lines[i - 1:i + 12])
                if 'method:' in win and not METH_GET.search(win) and not TOKEN.search(win):
                    nt_all.append((rel, i, line.strip()[:100]))
    r.data = {'repo_templates': len(src.list_templates()), 'notoken_all': len(nt_all),
              'a': len(a), 'b': len(b), 'c': len(c), 'd': len(d),
              'notoken_files': sorted({p for p, _, _ in nt_all})}
    r.say('全仓模板 %d 个；非 GET 无令牌 fetch( = %d 处（inScope 内已归零，口径外残留见下）'
          % (len(src.list_templates()), len(nt_all)))
    r.lines += ['  RESIDUAL ' + x for x in fmt(nt_all, 40)]
    r.say('分桶（全仓 CTX+LIT）：A(静态字面量)=%d  B(`${` 插值)=%d  C(其余)=%d  D({{ }})=%d'
          % (len(a), len(b), len(c), len(d)))
    r.lines += ['  A ' + x for x in fmt(a, 10)]
    stale = [p for p, _, _ in nt_all if p.endswith('sales_order_detail.html')]
    if not nt_all:
        r.code = FAIL
        r.say('全仓非 GET 无令牌 = 0：与契约 §3④(b)「不可达」结论冲突 ⇒ 台账过期，须重新登记')
    elif not stale:
        r.code = FAIL
        r.say('sales_order_detail.html 的挂账点已消失 ⇒ 台账过期，须重新登记')
    else:
        r.code = PASS
        r.say('台账与现场一致：sales_order_detail.html 挂账点仍在（%s）；'
              '「JS 字面量清零」仅限 A 桶（inScope）口径' % '/'.join(sorted(set(stale))))
    return r


STATIC = ['g5-notoken', 'g5-a-bucket', 'g5-apifetch', 'g5-get-sites', 'g7-inline-role',
          'g8-search-i18n', 'g10-print-record']
AUDIT = ['g5-residual-ledger']
# 不变量/阴性对照项：修复前后都应 PASS，不参与「修复前必须 UNIMPLEMENTED」的敏感度判定
INVARIANT = {'g5-get-sites'}
LIVE = ['g6-bootstrap-local', 'g11-entry-guard', 'g4-inventory-search']


def agg(codes):
    for c in (FAIL, ERROR, UNIMPL):
        if c in codes:
            return c
    return PASS


def selftest(root):
    """敏感度自检：把某条检查项的输入退化成「未实现/回归」形态，该检查必须如实报红。

    只碰 tempfile 目录；不启动 app（live 检查的敏感度由 `--root <修复前树>` 复跑覆盖）。
    """
    import shutil
    base = os.path.join(tempfile.mkdtemp(prefix='b16_selftest_'), 'tree')
    rels = inscope_files(Src(root)) + ['app/permissions.py', 'app/static/js/api-fetch.js',
                                       'app/templates/base.html']
    for rel in rels:
        d = os.path.join(base, rel)
        os.makedirs(os.path.dirname(d), exist_ok=True)
        shutil.copy2(os.path.join(root, rel), d)
    print('[selftest] fixture = %s (%d 文件)' % (base, len(rels)))

    def run_static(tree, rev=None):
        s = Src(tree, rev)
        return {n: CHECKS[n][1](s, None).code for n in STATIC}

    ok_all = True

    def case(title, ok, detail):
        nonlocal ok_all
        ok_all = ok_all and ok
        print('[selftest] %-4s %s | %s' % ('OK' if ok else 'SENSOR-FAIL', title, detail))

    codes = run_static(base)
    case('S1 干净 fixture：6 项静态检查应全 PASS',
         all(c == PASS for c in codes.values()),
         ' '.join('%s=%s' % (k, CODENAME[v]) for k, v in codes.items()))

    def mutate(fname, mutate_fn, targets):
        d = os.path.join(base, fname)
        orig = open(d, encoding='utf-8').read()
        new = mutate_fn(orig)
        if new == orig:
            case('注入 %s' % fname, False, '注入未生效（fixture 内容不符预期）')
            return
        open(d, 'w', encoding='utf-8').write(new)
        codes2 = run_static(base)
        bad = [t for t in targets if codes2[t] == PASS]
        case('注入 %s ⇒ %s 必须报红' % (fname, '/'.join(targets)), not bad,
             ' '.join('%s=%s' % (t, CODENAME[codes2[t]]) for t in targets))
        open(d, 'w', encoding='utf-8').write(orig)

    mutate('app/templates/main/inventory.html',
           lambda t: t + '\nfetch("/products/import", { method: "POST", body: fd });\n',
           ['g5-notoken', 'g5-a-bucket'])
    mutate('app/templates/main/quality/records.html',
           lambda t: t + '\n<a onclick="printRecord()">x</a>\n<a onclick="printRecord()">y</a>\n',
           ['g10-print-record'])
    mutate('app/templates/main/quality/tasks.html',
           lambda t: t + "\n{% if current_user.role in ['admin'] %}a{% endif %}"
                       "\n{% if current_user.role in ['admin'] %}b{% endif %}\n",
           ['g7-inline-role'])
    mutate('app/templates/main/search/advanced_search.html',
           lambda t: t + '\n{{ category }}\n',
           ['g8-search-i18n'])
    mutate('app/templates/main/products.html',
           lambda t: t.replace('apiFetch(', 'fetch('), ['g5-notoken', 'g5-apifetch'])

    # S3：同一批检查对修复前 rev 必须报 UNIMPLEMENTED（区分「通过」与「未实现」）
    head = subprocess.run(['git', 'rev-parse', '--verify', 'HEAD'], cwd=root,
                          capture_output=True, text=True)
    if head.returncode == 0:
        hc = {k: v for k, v in run_static(root, 'HEAD').items() if k not in INVARIANT}
        detail = ' '.join('%s=%s' % (k, CODENAME[v]) for k, v in hc.items())
        if all(v == PASS for v in hc.values()):
            print('[selftest] SKIP S3：HEAD 已含全部修复（commit 后再跑本用例不适用）| ' + detail)
        else:
            case('S3 修复前 rev=HEAD：修复指示项应为 UNIMPLEMENTED（非 PASS）| 不变量项 %s 已排除'
                 % ','.join(sorted(INVARIANT)),
                 all(v != PASS for v in hc.values()) and UNIMPL in hc.values(), detail)
    else:
        print('[selftest] SKIP S3：不是 git 仓库')
    print('[selftest] 汇总：%s' % ('全部敏感度断言通过' if ok_all else '存在 SENSOR-FAIL'))
    return PASS if ok_all else FAIL


def main(argv=None):
    ap = argparse.ArgumentParser(description='批次16 前端契约非作者验证载体')
    ap.add_argument('--root', default=REPO, help='源码树根（默认仓库根；修复前树可复跑 live 检查）')
    ap.add_argument('--rev', default=None, help='静态度量取该 rev（如 HEAD = 修复前）')
    ap.add_argument('--check', action='append', default=[], help='只跑指定检查项（可重复）')
    ap.add_argument('--list', action='store_true', help='列出检查项')
    ap.add_argument('--selftest', action='store_true', help='敏感度自检')
    ap.add_argument('--json-out', default=None, help='结构化读数落盘（绝对路径）')
    args = ap.parse_args(argv)
    if args.list:
        for n, (kind, _) in CHECKS.items():
            print('%-22s %s' % (n, kind))
        return PASS
    if args.selftest:
        return selftest(os.path.abspath(args.root))
    src = Src(os.path.abspath(args.root), args.rev)
    names = args.check or (STATIC + LIVE)
    unknown = [n for n in names if n not in CHECKS]
    if unknown:
        print('[b16] 未知检查项 %s（--list 查看）' % unknown)
        return 3
    print('[b16] root=%s rev=%s 检查项=%d' % (src.root, src.rev or '(工作树)', len(names)))
    db = os.path.join(src.root, 'app.db')
    if os.path.isfile(db):
        import hashlib
        with open(db, 'rb') as f:
            print('[b16] app.db sha256=%s' % hashlib.sha256(f.read()).hexdigest())
    results, payload = {}, {}
    for n in names:
        kind, fn = CHECKS[n]
        try:
            r = fn(src, args)
        except Exception as e:
            r = R()
            r.code = ERROR
            r.say('检查项异常：%s: %s' % (type(e).__name__, e))
        results[n] = r.code
        payload[n] = {'code': r.code, 'name': CODENAME[r.code], 'kind': kind,
                      'lines': r.lines, 'data': r.data}
        print('[%-13s] %s (%s)' % (CODENAME[r.code], n, kind))
        for line in r.lines:
            print('    %s' % line)
    n_pass = sum(1 for v in results.values() if v == PASS)
    print('[b16] 汇总：checks=%d pass=%d fail=%d error=%d unimplemented=%d exit=%d'
          % (len(results), n_pass, sum(1 for v in results.values() if v == FAIL),
             sum(1 for v in results.values() if v == ERROR),
             sum(1 for v in results.values() if v == UNIMPL), agg(list(results.values()))))
    if args.json_out:
        payload['_summary'] = {'results': results, 'exit': agg(list(results.values()))}
        with open(args.json_out, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print('[b16] 读数已落盘 %s' % args.json_out)
    return agg(list(results.values()))


def fmt(hits, limit=30):
    return ['%s:%d | %s' % h for h in hits[:limit]] + \
           ([] if len(hits) <= limit else ['… 共 %d 处' % len(hits)])


# 修复前 NOTOKEN 逐点分布（本载体 --baseline HEAD 实测；post-fix 的 apiFetch 逐点应与之一一对应）
BASE_NOTOKEN_BY_FILE = {
    'consumable_categories.html': 3, 'consumables.html': 3, 'delivery_batches.html': 1,
    'inventory.html': 1, 'process_assignment_bulk.html': 1, 'production_center.html': 1,
    'production_center_item.html': 2, 'products.html': 1, 'quality/inspection.html': 1,
    'quality/task_detail.html': 2, 'quality/tasks.html': 3,
}


@check('g5-notoken')
def c_notoken(src, args):
    r = R()
    files = inscope_files(src)
    a, nt, af = scan(src, files)
    r.data = {'files': len(files), 'a': len(a), 'notoken': len(nt), 'apifetch': len(af)}
    r.say('inScope 文件=%d  A桶=%d  NOTOKEN=%d（基线 %d）  apiFetch=%d'
          % (len(files), len(a), len(nt), BASE_NOTOKEN, len(af)))
    r.lines += ['  NOTOKEN ' + x for x in fmt(nt)]
    if not nt:
        r.code = PASS
        r.say('终态达成：inScope 内非 GET 且无令牌的 fetch( 站点 = 0')
    elif len(nt) == BASE_NOTOKEN:
        r.code = UNIMPL
        r.say('NOTOKEN=%d 恰等于修复前基线 ⇒ 判定「未实现」' % len(nt))
    else:
        r.code = FAIL
        r.say('NOTOKEN=%d 既非 0 也非基线 %d ⇒ 部分实现/回归' % (len(nt), BASE_NOTOKEN))
    return r


@check('g5-a-bucket')
def c_a_bucket(src, args):
    r = R()
    files = inscope_files(src)
    a, nt, af = scan(src, files)
    r.data = {'a': len(a), 'hits': ['%s:%d' % (p, i) for p, i, _ in a]}
    r.say('inScope A 桶（静态全字面量根相对 URL）= %d（基线 %d）' % (len(a), BASE_A))
    r.lines += ['  A ' + x for x in fmt(a)]
    if not a:
        r.code = PASS
        r.say('终态达成：A 桶 = 0（仅限 A 口径；B/D 桶见报告 §4 挂账）')
    elif len(a) == BASE_A:
        r.code = UNIMPL
        r.say('A=%d 恰等于修复前基线 ⇒ 判定「未实现」' % len(a))
    else:
        r.code = FAIL
        r.say('A=%d 既非 0 也非基线 %d' % (len(a), BASE_A))
    return r


@check('g5-apifetch')
def c_apifetch(src, args):
    r = R()
    files = inscope_files(src)
    a, nt, af = scan(src, files)
    by = {}
    for p, i, _ in af:
        rel = p[len(MAIN) + 1:]
        by[rel] = by.get(rel, 0) + 1
    r.data = {'total': len(af), 'by_file': by}
    r.say('apiFetch( 站点 = %d（期望 %d，= 修复前 NOTOKEN 逐点数）' % (len(af), BASE_NOTOKEN))
    bad = []
    for rel in sorted(set(list(by) + list(BASE_NOTOKEN_BY_FILE))):
        exp = BASE_NOTOKEN_BY_FILE.get(rel, 0)
        if by.get(rel, 0) != exp:
            bad.append('%s: apiFetch=%d 基线该文件 NOTOKEN=%d' % (rel, by.get(rel, 0), exp))
    if bad:
        r.say('逐点不一致：')
        r.lines += ['  ' + x for x in bad]
    else:
        r.say('19 处逐点一一对应（11 个文件，逐文件计数与修复前 NOTOKEN 分布相同）')
    # 封装件本体与接线（没有它，19 处改名只是把令牌换成未定义函数）
    wrap = 'app/static/js/api-fetch.js'
    w = src.read(wrap) if src.exists(wrap) else ''
    ok_wrap = ('window.apiFetch' in w) and ('X-CSRFToken' in w) and ("csrf-token" in w)
    base = src.read('app/templates/base.html')
    wired = bool(re.search(r"<script[^>]+js/api-fetch\.js", base))
    r.data.update({'wrapper_ok': ok_wrap, 'wired_in_base': wired, 'by_total': len(af)})
    r.say('封装件 %s 存在且注入 X-CSRFToken=%s；base.html 引入=%s' % (wrap, ok_wrap, wired))
    if bad or not ok_wrap or not wired:
        r.code = FAIL if af else UNIMPL
        if not af:
            r.say('apiFetch( 站点 = 0 ⇒ 恰等于修复前基线，判定「未实现」')
    else:
        r.code = PASS
    if r.code == PASS:
        r.say('终态达成：19 处逐点已改名，封装件与引入齐备')
    return r


@check('g7-inline-role')
def c_inline_role(src, args):
    r = R()
    hits = []
    for rel in src.list_templates():
        for i, line in enumerate(src.read(rel).splitlines(), 1):
            if 'current_user.role' in line:
                hits.append((rel, i, line.strip()))
    r.data = {'hits': ['%s:%d' % (p, i) for p, i, _ in hits]}
    r.say('模板内联 current_user.role 命中 = %d（基线 %d，期望 1）' % (len(hits), BASE_INLINE_ROLE))
    r.lines += ['  ' + x for x in fmt(hits)]
    if len(hits) == 1:
        rel, i, line = hits[0]
        exempt = ('B16-08' in line) and ('豁免' in line)
        r.data['exempt_comment'] = exempt
        r.say('唯一命中 %s:%d 带豁免注释=%s' % (rel, i, exempt))
        # 被替换的那处必须走能力判定，且能力集与内联集合逐元素相等（口径 §3③）
        q = src.read(MAIN + '/quality/tasks.html')
        r.data['tasks_uses_can'] = bool(re.search(r"can\('quality\.inspect'\)", q))
        r.data['tasks_has_inline'] = 'current_user.role' in q
        r.say("quality/tasks.html 改用 can('quality.inspect')=%s；残留内联=%s"
              % (r.data['tasks_uses_can'], r.data['tasks_has_inline']))
        r.code = PASS if (rel.endswith('quality/task_detail.html') and exempt
                          and r.data['tasks_uses_can'] and not r.data['tasks_has_inline']) else FAIL
    elif len(hits) == BASE_INLINE_ROLE:
        r.code = UNIMPL
        r.say('命中 = %d 恰等于修复前基线 ⇒ 判定「未实现」' % len(hits))
    else:
        r.code = FAIL
    return r


def search_keys(src):
    body = src.read('app/permissions.py')
    m = re.search(r'SEARCH_TYPE_CAPABILITIES\s*=\s*\{(.*?)\n\}', body, re.S)
    return re.findall(r"'([a-z_]+)'\s*:", m.group(1)) if m else []


@check('g8-search-i18n')
def c_search_i18n(src, args):
    r = R()
    keys = search_keys(src)
    rel = MAIN + '/search/advanced_search.html'
    tpl = src.read(rel)
    covered = [k for k in keys if re.search(r"['\"]%s['\"]\s*:" % re.escape(k), tpl)]
    branches = re.findall(r"category\s*==\s*'([a-z_]+)'", tpl)
    bare = re.findall(r'\{\{\s*category\s*\}\}', tpl)
    fallback = 'category_meta.get(' in tpl and '其他类型' in tpl
    r.data = {'keys': keys, 'covered': covered, 'branches': branches,
              'bare_category_output': len(bare), 'fallback': fallback}
    r.say("SEARCH_TYPE_CAPABILITIES key=%d；category_meta 映射覆盖=%d；"
          "category == 具名分支=%d 出现 / %d 去重（契约基线口径=4）"
          % (len(keys), len(covered), len(branches), len(set(branches))))
    r.say('{{ category }} 直出 = %d（期望 0）；未知分类兜底=%s' % (len(bare), fallback))
    if len(keys) != 8:
        r.code = ERROR
        r.say('permissions.py 解析出的 key 数≠8 ⇒ 该项不可判定')
    elif len(covered) == len(keys) and not bare and fallback:
        r.code = PASS
        r.say('终态达成：8/8 中文映射 + 兜底，无英文 key 直出')
    elif not covered and len(set(branches)) == BASE_SEARCH_KEYS and bare:
        r.code = UNIMPL
        r.say('无映射、具名分支=%d、且仍有 {{ category }} 直出 ⇒ 恰等于修复前基线，判定「未实现」'
              % len(branches))
    else:
        r.code = FAIL
    return r


# ------------------------------------------------------------------ live 检查
def boot(root, fresh=True):
    """在 root 这棵源码树上启动 app（库只碰 app.db 副本，由 _test_bootstrap 隔离）。

    root 需同时有 app.db 与 scripts/_test_bootstrap.py；`--root <修复前树>` 即可复跑
    同一批 live 检查拿修复前读数（阴性对照）。
    """
    if not os.path.isfile(os.path.join(root, 'app.db')):
        raise RuntimeError('live 检查需要 %s/app.db（副本源）——当前树没有' % root)
    sys.path.insert(0, os.path.join(root, 'scripts'))
    cwd = os.getcwd()
    os.chdir(root)
    try:
        import importlib
        tb = importlib.import_module('_test_bootstrap')
        importlib.reload(tb)
        app, copy = tb.make_app(fresh=fresh)
    finally:
        os.chdir(cwd)
    return app, copy


def login_roles(app, roles):
    from _test_bootstrap import ensure_role_users, login_as
    ensure_role_users(app)
    out = {}
    for role in roles:
        c = app.test_client()
        resp = login_as(c, '_t_' + role)
        loc = resp.headers.get('Location', '')
        if resp.status_code not in (301, 302, 303) or '/auth/login' in loc:
            raise RuntimeError('登录失败 role=%s status=%s loc=%s' % (role, resp.status_code, loc))
        out[role] = c
    return out


@check('g6-bootstrap-local', kind='live')
def c_bootstrap_local(src, args):
    r = R()
    app, copy = boot(src.root)
    bs = (app.extensions.get('bootstrap') or app.jinja_env.globals.get('bootstrap'))
    if bs is None:
        r.code = ERROR
        r.say('flask_bootstrap 未注册到 extensions/jinja 全局 ⇒ load_css()/load_js() 不可取，不可判定')
        return r
    with app.test_request_context('/'):
        css, js = str(bs.load_css()), str(bs.load_js())
    cfg = app.config.get('BOOTSTRAP_SERVE_LOCAL')
    r.say('config BOOTSTRAP_SERVE_LOCAL = %r' % cfg)
    r.say('load_css() = %s' % css.strip().replace('\n', ' ')[:160])
    r.say('load_js()  = %s' % js.strip().replace('\n', ' ')[:160])
    cdn = [x for x in (css, js) if 'cdn.jsdelivr.net' in x]
    loc = [x for x in (css, js) if '/bootstrap/static/' in x]
    r.data = {'serve_local': cfg, 'cdn_in_css_js': len(cdn), 'local_in_css_js': len(loc)}
    # 真页面 HTML（端到端：模板里实际吐出来的是什么）
    cl = app.test_client()
    pages = {}
    for path in ('/auth/login', '/'):
        resp = cl.get(path)
        html = resp.get_data(as_text=True)
        pages[path] = (resp.status_code, html.count('cdn.jsdelivr.net'),
                       html.count('/bootstrap/static/'))
    r.data['pages'] = pages
    for p, v in pages.items():
        r.say('GET %s -> %s  cdn=%d  local=%d' % (p, v[0], v[1], v[2]))
    r.say('蓝图 static 前缀 = %r' % ('/bootstrap' + app.static_url_path,))
    # 静态资源本体：200 + 版本 5.3.5
    path = '/bootstrap/static/css/bootstrap.min.css'
    resp = cl.get(path)
    body = resp.get_data(as_text=True)
    ver = re.findall(r'Bootstrap\s+v(\d+\.\d+\.\d+)', body)
    r.data['asset'] = {'path': path, 'status': resp.status_code, 'bytes': len(body), 'version': ver[:1]}
    r.say('GET %s -> %s  %d 字节  版本=%s' % (path, resp.status_code, len(body), ver[:1]))
    if cdn:
        r.code = UNIMPL
        r.say('页面/资源仍引用 cdn.jsdelivr.net ⇒ 恰等于修复前基线，判定「未实现」')
    elif not loc:
        r.code = FAIL
        r.say('无 cdn 引用但也未改用 /bootstrap/static/ ⇒ FAIL')
    elif resp.status_code != 200 or ver[:1] != ['5.3.5']:
        r.code = FAIL
        r.say('本地静态路径状态码/版本不符（期望 200 + 5.3.5）')
    elif pages['/auth/login'][1] or pages['/'][1] or not pages['/auth/login'][2]:
        r.code = FAIL
        r.say('页面 HTML 与 load_css() 结论不一致（页面仍引 CDN 或无本地引用）')
    else:
        r.code = PASS
        r.say('终态达成：BOOTSTRAP_SERVE_LOCAL 生效，load_css()/load_js() 与页面均指向本地 5.3.5')
    return r


@check('g11-entry-guard', kind='live')
def c_entry_guard(src, args):
    r = R()
    app, copy = boot(src.root)
    cl = login_roles(app, ('admin', 'manager', 'inspector'))
    entry, status = {}, {}
    for role, c in cl.items():
        html = c.get('/quality').get_data(as_text=True)
        entry[role] = html.count('/quality/templates')
        status[role] = c.get('/quality/templates').status_code
    r.data = {'entry': entry, 'status': status}
    r.say('首页内「质检模板」入口出现次数 = %s' % entry)
    r.say('GET /quality/templates 状态码 = %s' % status)
    bad = []
    if entry.get('inspector'):
        bad.append('inspector 首页仍有入口（第 34/53 行守卫未生效）')
    if status.get('inspector') == 200:
        bad.append('inspector 直连 /quality/templates 返回 200（只藏链接、后端未守）')
    for role in ('admin', 'manager'):
        if not entry.get(role):
            bad.append('%s 首页入口消失（过度收紧）' % role)
        if status.get(role) != 200:
            bad.append('%s 直连 /quality/templates = %s（期望 200）' % (role, status.get(role)))
    if bad:
        r.lines += ['  ' + x for x in bad]
        # 两类根因分开：守卫完全缺失 = 未实现；只藏链接 = 回归/越界
        r.code = UNIMPL if entry.get('inspector') else FAIL
    else:
        r.code = PASS
        r.say('终态达成：inspector 首页无入口且直连非 200（实测 %s）；admin/manager 有入口且 200'
              % status.get('inspector'))
    return r


EPS = [('raw-materials', '/api/inventory/raw-materials'),
       ('finished-products', '/api/inventory/finished-products'),
       ('consumables', '/api/inventory/consumables')]


def _rows(client, url):
    resp = client.get(url)
    body = resp.get_data()
    try:
        j = resp.get_json()
    except Exception:
        j = None
    rows = j.get('data') if isinstance(j, dict) else j
    if not isinstance(rows, list):
        rows = []
    return resp.status_code, body, rows


def _sha(body):
    import hashlib
    return hashlib.sha256(body).hexdigest()[:16]


@check('g4-inventory-search', kind='live')
def c_inv_search(src, args):
    """三库存接口 search：空/缺参不回归 + nohit 严格收缩 + 至少一个真实列命中。

    修复前读数由 `--root <修复前树>` 复跑本项取得（同脚本同口径），报告 §3① 逐项对照。
    """
    from urllib.parse import quote
    r = R()
    app, copy = boot(src.root)
    c = login_roles(app, ('admin',))['admin']
    plain = {name: _rows(c, url) for name, url in EPS}
    if any(not v[2] for v in plain.values()):
        from _test_bootstrap import seed_fixtures
        made = seed_fixtures(app)
        r.say('空表 ⇒ seed_fixtures（仅写副本库 %s）：%s' % (copy, made))
        plain = {name: _rows(c, url) for name, url in EPS}
    r.say('副本库 = %s' % copy)
    verdicts = []
    for name, url in EPS:
        c0, b0, rows0 = plain[name]
        c1, b1, rows1 = _rows(c, url + '?search=')
        c2, b2, rows2 = _rows(c, url + '?search=ZZZ_NOHIT_zzz')
        ids0 = {row.get('id') for row in rows0}
        r.say('[%s] plain code=%s len=%d sha=%s rows=%d' % (name, c0, len(b0), _sha(b0), len(rows0)))
        r.say('[%s] search= code=%s len=%d sha=%s rows=%d  同 plain 逐字节=%s'
              % (name, c1, len(b1), _sha(b1), len(rows1), b1 == b0))
        r.say('[%s] nohit  code=%s len=%d sha=%s rows=%d' % (name, c2, len(b2), _sha(b2), len(rows2)))
        hits = {}
        for field in sorted({k for row in rows0 for k, v in row.items()
                             if isinstance(v, str) and v.strip()}):
            term = max(re.split(r'[\s,;]+', rows0[0].get(field) or ''), key=len)
            if not term:
                continue
            c3, b3, rows3 = _rows(c, url + '?search=' + quote(term))
            ids3 = {row.get('id') for row in rows3}
            if rows3 and ids3 <= ids0:
                hits[field] = {'term': term, 'rows': len(rows3), 'code': c3, 'subset': True}
        r.data[name] = {'plain': [c0, len(b0), _sha(b0), len(rows0)],
                        'empty': [c1, len(b1), _sha(b1), len(rows1)],
                        'nohit': [c2, len(b2), _sha(b2), len(rows2)],
                        'hits': hits}
        r.say('[%s] 命中列样本：%s' % (name, hits if hits else '（无）'))
        if not rows0:
            verdicts.append((name, ERROR, 'plain 返回 0 行（表空且 seed 未补上）⇒ 不可判定'))
        elif b1 != b0:
            verdicts.append((name, FAIL, '空 search 与缺参返回体不一致 ⇒ 空参回归'))
        elif len(rows2) == len(rows0) and b2 == b0:
            verdicts.append((name, UNIMPL, 'nohit 与 plain 逐字节相同 ⇒ 未识别 search（修复前基线形态）'))
        elif not rows2 and b2 != b0:
            verdicts.append((name, PASS if hits else FAIL,
                             'nohit 严格收缩到 0 行且返回体不同；命中列=%s' % sorted(hits)))
        else:
            verdicts.append((name, FAIL, 'nohit rows=%d 既非 0 也非 plain(%d) ⇒ 过滤语义可疑'
                             % (len(rows2), len(rows0))))
    for name, code, why in verdicts:
        r.say('判定 [%s] %s：%s' % (name, CODENAME[code], why))
    r.code = agg([c for _, c, _ in verdicts]) if verdicts else ERROR
    return r


@check('g10-print-record')
def c_print_record(src, args):
    r = R()
    rel = MAIN + '/quality/records.html'
    body = src.read(rel)
    zero = [(i, l.strip()[:100]) for i, l in enumerate(body.splitlines(), 1)
            if re.search(r'printRecord\s*\(\s*\)', l)]
    witharg = re.findall(r'printRecord\s*\(\s*[^)\s][^)]*\)', body)
    sig = re.findall(r'function\s+printRecord\s*\(\s*(\w+)', body)
    r.data = {'zero_arg': len(zero), 'with_arg': len(witharg), 'signature': sig[:3]}
    r.say('零实参 printRecord() = %d（基线 %d，期望 0）；带实参调用 = %d；定义签名 = %s'
          % (len(zero), BASE_PRINT_ZEROARG, len(witharg), sig[:3]))
    r.lines += ['  零实参 %d | %s' % (i, l) for i, l in zero]
    if len(zero) == BASE_PRINT_ZEROARG:
        r.code = UNIMPL
        r.say('零实参 = %d 恰等于修复前基线 ⇒ 判定「未实现」' % len(zero))
    elif not zero and witharg and sig:
        r.code = PASS
        r.say('终态达成：调用点全部传实参，定义为 printRecord(%s)' % sig[0])
    else:
        r.code = FAIL
    return r


if __name__ == '__main__':
    sys.exit(main())
